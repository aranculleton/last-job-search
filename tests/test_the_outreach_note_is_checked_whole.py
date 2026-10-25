"""A drafted outreach body is checked as it is sent: after its opening line.

The workflow's drafter and auditor ran `outreach.py --check-note "<outreach_body>"`,
but the note that goes out is the fixed opening line ("Hi [name], I've just
applied for the <role> role at <Company>.") and then the body, and the 80-word
limit is for all of it. A 70-word body passed the check and was refused when
`outreach.py` built the note. `--company` and `--role` put the opening in front.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import outreach  # noqa: E402

COMPANY, ROLE = "Wrenfield Freight Ltd", "Senior Supply Chain Analyst"
BODY = ("Chilled and ambient volumes behave differently, and a forecast that treats them "
        "as one stream fills the wrong trailers and leaves the depot short by Thursday. "
        "At Brindle & Hart I forecast both, by depot and by week, for the planners who "
        "load the trailers, and the planning team now builds its weekly loads from those "
        "numbers. Happy to answer anything the application leaves open, whenever suits.")
TOOL = [sys.executable, os.path.join(ROOT, "tools", "outreach.py"), "--check-note"]


def test_a_body_that_fits_alone_is_refused_with_its_opening():
    assert 66 <= len(BODY.split()) < outreach.MAX_NOTE_WORDS
    alone = subprocess.run(TOOL + [BODY], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert alone.returncode == 0, alone.stdout
    whole = subprocess.run(TOOL + ["--company", COMPANY, "--role", ROLE, BODY],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert whole.returncode == 1 and "words" in whole.stdout


def test_the_check_and_the_built_note_agree():
    with pytest.raises(ValueError):
        outreach.outreach_note({"company": COMPANY, "role": ROLE, "outreach_body": BODY})
    short = "At Brindle & Hart I forecast chilled and ambient stock by depot. Happy to talk."
    note = outreach.outreach_note({"company": COMPANY, "role": ROLE, "outreach_body": short})
    assert note == outreach.whole_note(COMPANY, ROLE, short)
    assert note.startswith(outreach.OPENING.format(role=ROLE, company="Wrenfield Freight"))


def test_the_drafting_audit_checks_the_body_with_its_opening():
    # Updated 2026-10-21: this read the workflow's prompts for "--check-note --company",
    # run by the drafter and again by the auditor agent. The check now runs in code, in
    # the drafting audit (tools/draft_audit.py), on the note as it is sent.
    import draft_audit
    d = {"company": COMPANY, "role": ROLE, "outreach_body": BODY}
    found = [f for f in draft_audit.rule_findings(
        dict(d, summary="s", tools="SQL", p1="a.", p2="b.", lead="c", p4="d.",
             cl_bullets=[{"label": "x", "text": "y"}], requirement_map=[{"requirement": "r",
                                                                          "evidence": "e"}]),
        {}, "")[0] if f["rule"] == "outreach"]
    assert found and "words" in found[0]["text"]
