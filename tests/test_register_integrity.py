"""D-0096 — register numbers are issued by the register and checked here.

Two halves. The rule tests feed each check a register that breaks it and assert
it is caught: a gate never seen red is a gate proved only by reading it. The
live test runs every check against the tree as committed, so a citation with no
heading, a skipped number or a numbered candidate fails CI instead of costing
someone a day of reconciliation later.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import register

ROOT = Path(__file__).resolve().parents[1]

DECISIONS = """# Decisions
### D-0016 — First
### D-0017 — VOID, NEVER ISSUED
### D-0018 - Hyphen separator
"""


class EachRuleCatchesItsDefect(unittest.TestCase):
    def regs(self, d=DECISIONS, f="### F-0001 — One\n", a="### A-0001 — One\n"):
        return {"D": d, "F": f, "A": a}

    def test_a_clean_register_passes_every_rule(self):
        regs = self.regs()
        files = {"api/x.py": "# D-0018: cited and headed\n"}
        self.assertEqual(register.duplicate_headings(regs), [])
        self.assertEqual(register.gaps(regs), [])
        self.assertEqual(register.unheaded_citations(regs, files), [])
        self.assertEqual(register.numbered_candidates(files), [])

    def test_a_number_heading_two_entries(self):
        regs = self.regs(d=DECISIONS + "### D-0018 — Taken twice\n")
        self.assertEqual(
            register.duplicate_headings(regs),
            ["D-0018 heads 2 entries in docs/decisions.md"],
        )

    def test_a_skipped_number(self):
        regs = self.regs(f="### F-0001 — One\n### F-0003 — Three\n")
        (gap,) = register.gaps(regs)
        self.assertTrue(gap.startswith("F-0002 has no heading"))

    def test_a_void_heading_closes_a_gap(self):
        regs = self.regs(f="### F-0001 — One\n### F-0002 — VOID, NEVER ISSUED\n### F-0003 — Three\n")
        self.assertEqual(register.gaps(regs), [])

    def test_a_citation_in_code_with_no_heading(self):
        files = {"api/routes.py": "x = 1\n# D-0072: the model was retired\n"}
        self.assertEqual(
            register.unheaded_citations(self.regs(), files),
            ["api/routes.py:2 cites D-0072, which has no heading"],
        )

    def test_a_citation_in_a_test_filename(self):
        files = {"tests/test_thing_d0099.py": ""}
        self.assertEqual(
            register.unheaded_citations(self.regs(), files),
            ["tests/test_thing_d0099.py:filename cites D-0099, which has no heading"],
        )

    def test_a_listed_mention_is_not_a_citation(self):
        files = {"docs/decisions.md": "Rejected: restart at D-0001.\n"}
        self.assertEqual(register.unheaded_citations(self.regs(), files), [])
        mentions = {}
        self.assertEqual(len(register.unheaded_citations(self.regs(), files, mentions)), 1)

    def test_a_numbered_candidate_either_way_round_and_across_a_line_break(self):
        files = {
            "a.md": "Held as\n  F-0107 candidate; this PR stays copy-only.\n",
            "b.md": "Candidate: `F-0200`, filed later.\n",
            "c.md": "The candidate observable is unchanged.\n",
        }
        found = register.numbered_candidates(files)
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0].startswith("a.md:2 numbers a candidate (F-0107)"))
        self.assertTrue(found[1].startswith("b.md:1 numbers a candidate (F-0200)"))

    def test_a_testplan_number_with_no_decision(self):
        plan = "### T-0016 - Keyed\n### T-0018b - Suffixed\n### T-0050 - Orphan\n### T — Unnumbered\n"
        self.assertEqual(
            register.unkeyed_testplan(plan, DECISIONS),
            ["docs/testplan.md heads T-0050 but D-0050 has no heading"],
        )


class NextNumber(unittest.TestCase):
    """`next` reads the working tree and origin/master, and two branches that
    took the same number are caught. Built in a scratch repo, not this one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "master")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(DECISIONS)
        for letter in "FA":
            p = self.root / register.REGISTERS[letter]
            p.write_text(f"### {letter}-0001 — One\n", encoding="utf-8")
        self.commit("base")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, text):
        p = self.root / register.REGISTERS["D"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_void_counts_as_issued(self):
        self.write("### D-0016 — First\n### D-0017 — VOID, NEVER ISSUED\n")
        self.assertEqual(register.next_number("D", root=self.root), 18)

    def test_a_number_already_taken_on_origin_master_is_not_handed_out(self):
        self.write(DECISIONS + "### D-0019 — Merged elsewhere\n")
        self.commit("someone else's decision")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")
        self.git("checkout", "-q", "-b", "mine", "HEAD~1")
        self.assertEqual(register.next_number("D", root=self.root, remote=None), 19)
        self.assertEqual(register.next_number("D", root=self.root), 20)

    def test_two_branches_taking_the_same_number_collide(self):
        self.git("checkout", "-q", "-b", "theirs")
        self.write(DECISIONS + "### D-0019 — Theirs\n")
        self.commit("theirs")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")
        self.git("checkout", "-q", "-b", "mine", "master")
        self.write(DECISIONS + "### D-0019 — Mine\n")
        self.commit("mine")
        (hit,) = register.collisions(root=self.root)
        self.assertTrue(hit.startswith("D-0019 was taken on this branch and on origin/master"))

    def test_no_collision_when_only_one_side_added_it(self):
        self.write(DECISIONS + "### D-0019 — Mine\n")
        self.commit("mine")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD~1")
        self.assertEqual(register.collisions(root=self.root), [])


class TheLiveRegister(unittest.TestCase):
    def test_the_committed_tree_has_no_register_violations(self):
        violations = register.all_violations(ROOT)
        self.assertEqual(violations, [], "\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
