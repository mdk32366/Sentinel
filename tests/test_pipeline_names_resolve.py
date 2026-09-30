"""F-0103 — a pipeline entry point called a function it never imported.

`pipelines/gold_reserves.py` called `import_wgc_csv(db, csv_path=CSV_PATH)` and
imported no such name. Every run raised `NameError`: **35 of 35 in the log, and
the scheduled job has never once succeeded.**

Nothing noticed for two reasons. The watchdog reported `gold_reserves` as `ok`
because the *data* was fresh - `D-0076` fills that metric from the IMF, so the
World Gold Council backfill failing left no visible gap. And the failure is a
`NameError` inside a `try`, which the pipeline dutifully recorded as a `failed`
UpdateLog row that nobody read until the ADMIN log was inspected for another
reason.

This is the general form: **an entry point that references a name the module
does not provide**. Import-time checks miss it because the call is inside a
function; the test suite missed it because nothing calls these functions without
a database.
"""
import ast
import builtins
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parents[1] / "pipelines"

# Entry points the scheduler and the API routes call. A NameError in one of
# these is a job that cannot run.
ENTRY_PREFIXES = ("run_", "compute_", "persist_", "import_")


def module_level_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Try):
            # Imports guarded by try/except ImportError.
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        names.add(alias.asname or alias.name.split(".")[0])
    return names


def local_names(fn):
    """Everything bound inside the function: args, assignments, imports, loops."""
    names = {a.arg for a in fn.args.args}
    names |= {a.arg for a in fn.args.kwonlyargs}
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)
    for node in ast.walk(fn):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
        elif isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if hasattr(node, "name"):
                names.add(node.name)
            names |= {a.arg for a in node.args.args}
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            for sub in ast.walk(node.optional_vars):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
    return names


class TestEveryPipelineEntryPointResolves(unittest.TestCase):
    def test_no_entry_point_calls_an_undefined_name(self):
        builtin_names = set(dir(builtins))
        offenders = []

        for path in sorted(PIPELINES.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            module_names = module_level_names(tree)

            for fn in tree.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not fn.name.startswith(ENTRY_PREFIXES):
                    continue

                bound = module_names | local_names(fn) | builtin_names
                called = {
                    n.func.id for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                }
                for name in sorted(called - bound):
                    offenders.append(f"{path.name}:{fn.name} calls {name}()")

        self.assertEqual(
            offenders, [],
            "pipeline entry points calling names their module does not "
            f"provide: {offenders}",
        )

    def test_the_specific_regression_is_fixed(self):
        # gold_reserves.run_gold_reserves_fetch -> import_wgc_csv
        text = (PIPELINES / "gold_reserves.py").read_text(encoding="utf-8-sig")
        self.assertIn("from pipelines.gold_fetcher import import_wgc_csv", text)

    def test_the_check_would_have_caught_it(self):
        # A guard that cannot fail on the defect it was written for is
        # decoration. Reconstructed here rather than trusted.
        source = (
            "def run_x(db):\n"
            "    return missing_helper(db)\n"
        )
        tree = ast.parse(source)
        fn = tree.body[0]
        bound = module_level_names(tree) | local_names(fn) | set(dir(builtins))
        called = {
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        self.assertIn("missing_helper", called - bound)

    def test_it_does_not_fire_on_a_correctly_imported_name(self):
        source = (
            "from pipelines.gold_fetcher import import_wgc_csv\n"
            "def run_x(db):\n"
            "    return import_wgc_csv(db)\n"
        )
        tree = ast.parse(source)
        fn = tree.body[1]
        bound = module_level_names(tree) | local_names(fn) | set(dir(builtins))
        called = {
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        self.assertEqual(called - bound, set())

    def test_it_does_not_fire_on_a_function_local_import(self):
        # The shape of the fix: imported inside the function to keep a module
        # out of an import chain.
        source = (
            "def run_x(db):\n"
            "    from pipelines.gold_fetcher import import_wgc_csv\n"
            "    return import_wgc_csv(db)\n"
        )
        tree = ast.parse(source)
        fn = tree.body[0]
        bound = module_level_names(tree) | local_names(fn) | set(dir(builtins))
        called = {
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        self.assertEqual(called - bound, set())


if __name__ == "__main__":
    unittest.main()
