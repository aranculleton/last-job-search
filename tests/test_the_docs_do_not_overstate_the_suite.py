"""A test count quoted in prose must be a floor the repo actually clears.

A hard number in prose rots on the next commit. It said "1,330 tests across 48
files" and was wrong within a morning, three times, which is how a README stops
being read: not because any one number is important, but because a reader who
catches one stale figure stops trusting the rest of the page.

So the docs state a floor ("over 1,400") and this checks every doc that
quotes one. The claim can
never overstate, and adding tests never breaks the build. It only fails when
somebody writes a number the repo does not reach, or deletes enough tests to
fall below the one already written, and both of those are worth a red run.

Counted by asking pytest to collect, because that is the number the reader sees
when they run the command the README tells them to run. `--collect-only`
imports the test modules and runs nothing, so calling it from inside a test does
not recurse, and it costs about 0.4 seconds.

An AST parse is the fallback for an environment where the subprocess cannot
run. It is a strict undercount, because it counts a `parametrize`d function
once where pytest counts every case, so falling back can only make the guard
more conservative and never let a false claim through. That gap is exactly what
this file caught on its first run: 1,288 by parse against 1,411 collected.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_FILES = sorted(ROOT.glob("tests/test_*.py"))

# Every doc that quotes the suite size. ARCHITECTURE.md started carrying the
# same claim when the README's depth moved there, and a guard that reads only
# one of two files holding the same number is a guard with a hole in it.
CLAIMANTS = ("README.md", "ARCHITECTURE.md", "RUNBOOK.md", "SETUP.md")

# "over 1,400" / "1,400+" / "at least 1400"
CLAIM = re.compile(r"(?:over|at least|more than)\s+([\d,]{3,7})\s*(?:green|tests|,)|"
                   r"\b([\d,]{3,7})\+\s*tests", re.I)
FILE_CLAIM = re.compile(r"\b(\d{1,3})\s+test files\b", re.I)


COLLECTED = re.compile(r"^(\d+) tests? collected", re.M)


def count_by_parsing() -> int:
    """Lower bound: one per `def test_*`, ignoring parametrize expansion."""
    n = 0
    for path in TEST_FILES:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test"):
                n += 1
    return n


def count_tests() -> int:
    """What `pytest tests -q` reports, or a strict undercount if it cannot run."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stdout
        m = COLLECTED.search(out)
        if m:
            return int(m.group(1))
    except (OSError, subprocess.SubprocessError):
        pass
    return count_by_parsing()


class TestTheClaimedFloorIsReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = count_tests()
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.docs = {name: (ROOT / name).read_text(encoding="utf-8")
                    for name in CLAIMANTS if (ROOT / name).is_file()}

    def test_the_counter_finds_a_plausible_number(self):
        """A counter that silently returns 0 would make every other check pass."""
        # The app's own suite, run on the example person (a person's repo runs
        # their own profile/tests/ beside it, uncounted here).
        self.assertGreater(self.actual, 450,
                           "the test count collapsed; the floor checks below are "
                           "meaningless until this is right")

    def test_the_fallback_never_exceeds_the_real_count(self):
        """The fallback has to be an undercount or it could pass a false claim."""
        self.assertLessEqual(count_by_parsing(), self.actual)

    def test_the_readme_states_a_floor_rather_than_an_exact_count(self):
        self.assertRegex(self.readme, CLAIM,
                         "state the suite size as a floor (\"over 1,400\"), because "
                         "an exact count is stale on the next commit")

    def test_every_claimed_floor_is_cleared(self):
        checked = 0
        for name, text in self.docs.items():
            for m in CLAIM.finditer(text):
                checked += 1
                claimed = int((m.group(1) or m.group(2)).replace(",", ""))
                with self.subTest(doc=name, claimed=claimed):
                    self.assertLessEqual(
                        claimed, self.actual,
                        f"{name} claims over {claimed:,} tests; the suite has "
                        f"{self.actual:,}. Lower the claim or write the tests.")
        self.assertGreater(checked, 1, "no suite-size claims found to check")

    def test_the_claimed_file_count_is_not_above_what_exists(self):
        for name, text in self.docs.items():
            for m in FILE_CLAIM.finditer(text):
                claimed = int(m.group(1))
                with self.subTest(doc=name, claimed=claimed):
                    self.assertLessEqual(claimed, len(TEST_FILES),
                                         f"{name} claims {claimed} test files; "
                                         f"there are {len(TEST_FILES)}")

    def test_the_runbook_agrees_with_the_readme(self):
        """Two documents quoting different numbers is worse than either being stale."""
        runbook = (ROOT / "RUNBOOK.md").read_text(encoding="utf-8")
        readme_floors = {int((m.group(1) or m.group(2)).replace(",", ""))
                         for m in CLAIM.finditer(self.readme)}
        for m in CLAIM.finditer(runbook):
            claimed = int((m.group(1) or m.group(2)).replace(",", ""))
            with self.subTest(claimed=claimed):
                self.assertIn(claimed, readme_floors,
                              "RUNBOOK quotes a suite size the README does not")


if __name__ == "__main__":
    unittest.main()
