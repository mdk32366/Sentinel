"""Issue and check register numbers: D- (decisions), F- (findings), A- (assumptions).

D-0096. Numbers used to be issued by reading the register by eye. Three
numbers went missing that way (D-0072 cited in shipped code with no entry;
F-0107 named as a "candidate"; F-0108 skipped without a word) and finding them
cost days. The register is now the only issuer and this tool is how it is read.

    python tools/register.py next D      # the number to put on the next decision
    python tools/register.py status      # range, count, VOIDs and gaps per register
    python tools/register.py check       # every rule below; exit 1 on any violation

`next` takes the highest number headed in the working tree OR in `origin/master`,
plus one. A VOID heading counts as issued. Reading `origin/master` too means a
branch cut before someone else merged a number does not hand that number out
again. Run `git fetch` first; the tool does not touch the network.

`check` enforces:
  1. No ID heads more than one entry.
  2. No gaps: every number from the lowest to the highest has a heading. A
     number that was never used gets a `VOID, NEVER ISSUED` heading (D-0021).
  3. Every ID cited anywhere in the tracked tree (code, tests, docs, and test
     *filenames* like `test_dgs30_d0016.py`) has a heading.
  4. No candidate is referenced by number. A candidate is unnumbered until the
     Builder appends it (D-0034).
  5. A numbered testplan heading `T-NNNN` is keyed to an existing decision.
  6. No ID was headed both on this branch and on `origin/master` since they
     diverged - two PRs that took the same next number.

`tests/test_register_integrity.py` runs the same checks in CI.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REGISTERS = {
    "D": "docs/decisions.md",
    "F": "docs/findings.md",
    "A": "docs/assumptions.md",
}
TESTPLAN = "docs/testplan.md"

# A heading's ID and title. Both " — " and " - " separators are in use.
HEADING = re.compile(r"^#{2,4} +([DFA])-(\d{4})\b[ \t]*[—-]?[ \t]*(.*)$", re.M)
T_HEADING = re.compile(r"^#{2,4} +T-(\d{4})[a-z]?\b", re.M)
CITATION = re.compile(r"(?<![A-Za-z0-9])([DFA])-(\d{4})(?![0-9])")
FILENAME_CITATION = re.compile(r"_([dfa])(\d{4})(?![0-9])")
CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9])([DFA]-\d{4})[`*\s]{0,4}candidate"
    r"|candidate[:`*\s]{0,4}([DFA]-\d{4})",
    re.I,
)

TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".yml", ".yaml", ".toml",
    ".sql", ".txt", ".html", ".css", ".cfg", ".ini", ".sh", ".ps1",
}
# The checker and its test hold IDs as fixtures - deliberate defects - not as
# citations.
SKIP_FILES = {
    "ui/package-lock.json",
    "tools/register.py",
    "tests/test_register_integrity.py",
}

# Mentions that are not citations. Each entry is (path, ID) with the reason.
# Keep it short: every line here is a place the gate does not look.
MENTIONS = {
    ("docs/decisions.md", "D-0001"):
        "D-0021's rejected option, 'Restart at D-0001'. Names a number that "
        "was deliberately never used.",
}


def _git(*args, cwd=ROOT):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout if result.returncode == 0 else None


def read_text(path, ref=None, root=ROOT):
    """A file from the working tree, or from `ref` if given. None if absent."""
    if ref is None:
        p = Path(root) / path
        return p.read_text(encoding="utf-8") if p.exists() else None
    return _git("show", f"{ref}:{path}", cwd=root)


def headings(text, letter):
    """[(number, title)] for every `letter` heading in a register's text."""
    return [
        (int(num), title.strip())
        for found, num, title in HEADING.findall(text or "")
        if found == letter
    ]


def register_numbers(letter, ref=None, root=ROOT):
    return [n for n, _ in headings(read_text(REGISTERS[letter], ref, root), letter)]


def next_number(letter, root=ROOT, remote="origin/master"):
    """Highest number headed locally or on `remote`, plus one."""
    issued = register_numbers(letter, root=root)
    if remote and _git("rev-parse", "--verify", "-q", remote, cwd=root):
        issued += register_numbers(letter, ref=remote, root=root)
    return max(issued, default=0) + 1


def fmt(letter, number):
    return f"{letter}-{number:04d}"


# --- checks. Each returns a list of human-readable violations. ---------------

def duplicate_headings(registers):
    out = []
    for letter, text in registers.items():
        seen = {}
        for number, _ in headings(text, letter):
            seen[number] = seen.get(number, 0) + 1
        out += [
            f"{fmt(letter, n)} heads {c} entries in {REGISTERS[letter]}"
            for n, c in sorted(seen.items()) if c > 1
        ]
    return out


def gaps(registers):
    out = []
    for letter, text in registers.items():
        numbers = {n for n, _ in headings(text, letter)}
        if not numbers:
            continue
        out += [
            f"{fmt(letter, n)} has no heading in {REGISTERS[letter]} "
            f"(write the entry, or head it 'VOID, NEVER ISSUED')"
            for n in range(min(numbers), max(numbers) + 1) if n not in numbers
        ]
    return out


def unheaded_citations(registers, files, mentions=MENTIONS):
    """`files` is {path: text}. Cites in a register's own headings don't count."""
    headed = {
        fmt(letter, n) for letter, text in registers.items()
        for n, _ in headings(text, letter)
    }
    out = []
    for path, text in sorted(files.items()):
        cites = {}
        for i, line in enumerate(text.splitlines(), 1):
            for letter, num in CITATION.findall(line):
                cites.setdefault(f"{letter}-{num}", i)
        for letter, num in FILENAME_CITATION.findall(Path(path).stem):
            cites.setdefault(f"{letter.upper()}-{num}", "filename")
        for ident, where in sorted(cites.items()):
            if ident not in headed and (path, ident) not in mentions:
                out.append(f"{path}:{where} cites {ident}, which has no heading")
    return out


def numbered_candidates(files):
    out = []
    for path, text in sorted(files.items()):
        for m in CANDIDATE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            ident = m.group(1) or m.group(2)
            out.append(
                f"{path}:{line} numbers a candidate ({ident}); candidates are "
                f"unnumbered until appended (D-0034)"
            )
    return out


def unkeyed_testplan(testplan_text, decisions_text):
    decisions = {n for n, _ in headings(decisions_text, "D")}
    return [
        f"{TESTPLAN} heads T-{num} but D-{num} has no heading"
        for num in T_HEADING.findall(testplan_text or "")
        if int(num) not in decisions
    ]


def collisions(root=ROOT, remote="origin/master"):
    """IDs headed on this branch AND on `remote` since they diverged."""
    if not _git("rev-parse", "--verify", "-q", remote, cwd=root):
        return []
    base = (_git("merge-base", "HEAD", remote, cwd=root) or "").strip()
    if not base:
        return []
    out = []
    for letter, path in REGISTERS.items():
        before = set(register_numbers(letter, ref=base, root=root))
        ours = set(register_numbers(letter, root=root)) - before
        theirs = set(register_numbers(letter, ref=remote, root=root)) - before
        out += [
            f"{fmt(letter, n)} was taken on this branch and on {remote}; "
            f"rebase and renumber yours with `next {letter}`"
            for n in sorted(ours & theirs)
        ]
    return out


def tracked_text_files(root=ROOT):
    listing = _git("ls-files", cwd=root)
    if listing is None:
        raise RuntimeError("git ls-files failed; the register check needs a git checkout")
    files = {}
    for rel in listing.splitlines():
        if rel in SKIP_FILES or Path(rel).suffix.lower() not in TEXT_SUFFIXES:
            continue
        p = Path(root) / rel
        if p.exists():
            files[rel] = p.read_text(encoding="utf-8", errors="replace")
    return files


def all_violations(root=ROOT, remote="origin/master"):
    registers = {letter: read_text(path, root=root) or "" for letter, path in REGISTERS.items()}
    files = tracked_text_files(root)
    return (
        duplicate_headings(registers)
        + gaps(registers)
        + unheaded_citations(registers, files)
        + numbered_candidates(files)
        + unkeyed_testplan(read_text(TESTPLAN, root=root), registers["D"])
        + collisions(root, remote)
    )


def status(root=ROOT):
    lines = []
    for letter, path in REGISTERS.items():
        entries = headings(read_text(path, root=root), letter)
        numbers = sorted({n for n, _ in entries})
        voids = [fmt(letter, n) for n, t in entries if t.upper().startswith("VOID")]
        missing = [
            fmt(letter, n) for n in range(numbers[0], numbers[-1] + 1) if n not in numbers
        ] if numbers else []
        lines.append(
            f"{letter}  {path:22} {fmt(letter, numbers[0])}..{fmt(letter, numbers[-1])}"
            f"  {len(entries)} headings  next {fmt(letter, next_number(letter, root))}"
            f"  void {', '.join(voids) or '-'}  gaps {', '.join(missing) or '-'}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    nxt = sub.add_parser("next", help="print the next number for a register")
    nxt.add_argument("letter", choices=sorted(REGISTERS), type=str.upper)
    sub.add_parser("status", help="range, VOIDs and gaps per register")
    sub.add_parser("check", help="every rule; exit 1 on a violation")
    args = parser.parse_args(argv)

    if args.command == "next":
        print(fmt(args.letter, next_number(args.letter)))
        return 0
    if args.command == "status":
        print(status())
        return 0
    violations = all_violations()
    for v in violations:
        print(v)
    print(f"{len(violations)} violation(s)" if violations else "register OK")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
