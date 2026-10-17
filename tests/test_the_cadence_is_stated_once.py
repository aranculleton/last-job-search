"""No document may restate the follow-up cadence in numbers the code disagrees with.

`tools/network/schema.py` owns two numbers: `FOLLOWUP_BUSINESS_DAYS` and
`MAX_NUDGES`. Everything that waits, nudges or reports what is owed derives
from them.

`networking/connection_targets.md` had restated them as "7 days between touches"
and "3 touches maximum" against the code's 6 business days and 1 nudge. Neither
gap is cosmetic. Six business days from a Wednesday is the Thursday after next,
not the following Tuesday, so counting calendar days fires two days early and
reads as impatience, which is the exact failure `business_days_between` exists
to prevent. And three touches against one nudge is two extra messages on a
thread that has already gone quiet, which CLAUDE.md names as the message that
costs the relationship rather than the one that saves it. A session following
that file instead of the code would have sent both.

The rule is not that prose may never mention the cadence. `/threads`,
CLAUDE.md and the reply playbook all say "5 to 7 business days", which is a
readable way to describe 6 and is worth keeping. The rule is that a stated
window must contain the real number and a stated nudge count must not exceed
the real one, so prose can be approximate but never wrong.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))

import schema  # noqa: E402
from tests import repo_files  # noqa: E402

# `.claude/worktrees/` is where Claude Code puts an agent's isolated checkout,
# so a recursive glob over `.claude/` read whole second copies of the repo,
# generated contact prep documents included, and failed 22 subtests on
# 2026-09-24 over files that are not documentation and not in this tree.
# tests/repo_files.py leaves every nested checkout out.
DOCS = [p for p in repo_files.files("*.md", ".claude/**/*.md", "networking/*.md")
        if p.name != "CHANGELOG-upstream.md"]

# "5 to 7 business days", "5-7 business days"
WINDOW = re.compile(r"\b(\d+)\s*(?:to|-|–)\s*(\d+)\s+business days\b", re.I)
# "6 business days"
SINGLE = re.compile(r"\b(\d+)\s+business days\b", re.I)
# "3 touches maximum", "two nudges", "one nudge only"
NUDGES = re.compile(r"\b(\d+|one|two|three|four)\s+(?:nudges?|touches?)\b", re.I)
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}

# A doc that needs to quote the old, wrong numbers in order to explain them wraps
# that passage in these markers. Explicit and visible, rather than a keyword
# heuristic: a heuristic that exempts any line containing "said" would also
# exempt a real claim that happened to use the word, which is the failure mode
# of every clever exemption rule.
HISTORY_START = "cadence-history:start"
HISTORY_END = "cadence-history:end"


def live_lines(path: Path):
    """(line number, text) for every line the doc is asserting, markers excluded."""
    inside = False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if HISTORY_START in line:
            inside = True
        if not inside:
            yield n, line
        if HISTORY_END in line:
            inside = False


class TestTheDocsAgreeWithSchema(unittest.TestCase):
    def test_there_are_docs_to_check(self):
        self.assertGreater(len(DOCS), 10)

    def test_every_stated_window_contains_the_real_number(self):
        real = schema.FOLLOWUP_BUSINESS_DAYS
        for path in DOCS:
            for n, line in live_lines(path):
                for m in WINDOW.finditer(line):
                    lo, hi = int(m.group(1)), int(m.group(2))
                    with self.subTest(doc=path.name, line=n):
                        self.assertLessEqual(lo, real, f"{path.name}:{n}: {m.group(0)}")
                        self.assertGreaterEqual(hi, real, f"{path.name}:{n}: {m.group(0)}")

    def test_a_single_stated_day_count_is_the_real_one(self):
        real = schema.FOLLOWUP_BUSINESS_DAYS
        for path in DOCS:
            for n, line in live_lines(path):
                if WINDOW.search(line):
                    continue
                for m in SINGLE.finditer(line):
                    with self.subTest(doc=path.name, line=n):
                        self.assertEqual(real, int(m.group(1)),
                                         f"{path.name}:{n}: {m.group(0)} "
                                         f"but FOLLOWUP_BUSINESS_DAYS is {real}")

    def test_no_doc_promises_more_nudges_than_the_code_allows(self):
        real = schema.MAX_NUDGES
        for path in DOCS:
            for n, line in live_lines(path):
                for m in NUDGES.finditer(line):
                    raw = m.group(1).lower()
                    count = WORDS.get(raw, None)
                    if count is None:
                        count = int(raw)
                    with self.subTest(doc=path.name, line=n):
                        self.assertLessEqual(
                            count, real,
                            f"{path.name}:{n} promises {m.group(0)}, but MAX_NUDGES "
                            f"is {real}; an extra nudge on a quiet thread is the "
                            f"message that costs the relationship")


class TestTheGuardItselfFires(unittest.TestCase):
    """A doc guard that only ever passes is decoration.

    These run the same patterns over the exact strings that were in
    connection_targets.md before the fix, so the checks above are known to be
    capable of failing rather than merely observed not to.
    """

    def test_the_window_pattern_catches_a_wrong_range(self):
        m = WINDOW.search("nudge after 2 to 3 business days")
        self.assertIsNotNone(m)
        self.assertGreater(schema.FOLLOWUP_BUSINESS_DAYS, int(m.group(2)),
                           "this synthetic range must be one the real check rejects")

    def test_the_nudge_pattern_catches_the_line_that_was_wrong(self):
        m = NUDGES.search("- **3 touches maximum**, then move to someone else")
        self.assertIsNotNone(m)
        self.assertGreater(int(m.group(1)), schema.MAX_NUDGES)

    def test_the_nudge_pattern_reads_words_as_well_as_digits(self):
        m = NUDGES.search("And three touches against one nudge")
        self.assertEqual("three", m.group(1))
        self.assertGreater(WORDS[m.group(1)], schema.MAX_NUDGES)

    def test_a_correct_line_is_not_flagged(self):
        m = NUDGES.search("One nudge, after 5 to 7 business days.")
        self.assertLessEqual(WORDS[m.group(1).lower()], schema.MAX_NUDGES)
        w = WINDOW.search("One nudge, after 5 to 7 business days.")
        self.assertLessEqual(int(w.group(1)), schema.FOLLOWUP_BUSINESS_DAYS)
        self.assertGreaterEqual(int(w.group(2)), schema.FOLLOWUP_BUSINESS_DAYS)

    def test_the_history_markers_only_hide_what_is_between_them(self):
        import tempfile, os
        fh = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        fh.write("live one\n<!-- cadence-history:start -->\nhidden\n"
                 "<!-- cadence-history:end -->\nlive two\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        got = [line for _n, line in live_lines(Path(fh.name))]
        self.assertIn("live one", got)
        self.assertIn("live two", got)
        self.assertNotIn("hidden", got)


class TestTheStoreIsNamedOnce(unittest.TestCase):
    def test_nothing_in_code_reads_the_superseded_log(self):
        for path in repo_files.files("tools/**/*.py"):
            with self.subTest(tool=path.name):
                self.assertNotIn("outreach_log", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
