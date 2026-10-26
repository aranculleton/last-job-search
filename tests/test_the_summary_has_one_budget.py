"""The summary has one budget, and the audit, the pack, the renderer and the guide all read it.

`draft_audit.SUMMARY_WORDS` was (40, 48) and the drafting pack asked for 40 to 48, while the
renderer kept 36 to 52 and 05-cv-templates.md said "36 to 52 words": a 50-word summary the
page took was a budget finding that kept the draft from being assembled (the drafting
audit, 2026-10-25).
"""
from __future__ import annotations

import copy
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import render_application as R  # noqa: E402

GUIDE = os.path.join(ROOT, ".claude", "skills", "job-application-assistant", "05-cv-templates.md")


def test_every_copy_says_the_same_budget():
    lo, hi = draft_audit.SUMMARY_WORDS
    assert (R.MIN_SUMMARY_WORDS, R.MAX_SUMMARY_WORDS) == (lo, hi)
    assert f"- summary: {lo} to {hi} words" in draft_pack.CONTRACT
    with open(GUIDE, encoding="utf-8") as fh:
        guide = fh.read()
    said = set(re.findall(r"(\d+)(?: to |-)(\d+) words", guide))
    assert said == {(str(lo), str(hi))}, said
    with open(os.path.join(ROOT, "RUNBOOK.md"), encoding="utf-8") as fh:
        assert "40 to 48 words" not in fh.read()


def test_a_summary_the_page_takes_is_not_a_budget_finding():
    from test_one_drafting_call_per_posting import FIXTURE
    d = copy.deepcopy(FIXTURE["draft"])
    words = d["summary"].split()
    fifty = " ".join((words * 3)[:50]).rstrip(".") + "."
    assert len(R.cap_summary(fifty).split()) == 50              # the page keeps every word
    d["summary"] = fifty
    budget = [f for f in draft_audit.rule_findings(d, {}, FIXTURE["posting"])[0] if f["rule"].startswith("budget")
              and f["field"] == "summary"]
    assert budget == []
    d["summary"] = " ".join((words * 3)[:60])
    assert [f for f in draft_audit.rule_findings(d, {}, FIXTURE["posting"])[0] if f["rule"].startswith("budget")
            and f["field"] == "summary"]
