"""A recruiter or hiring manager the employer names is who the letter is addressed to.

The research stage of the drafting workflow collects `named_contact` and
`req_id` from the posting, but the draft object had neither field, so every
letter went to "<Company> hiring team", the tracker's `contact_person` stayed
empty (and with it the follow-up's addressee), and the requisition was lost.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import record_drafts  # noqa: E402
import render_application as R  # noqa: E402


def _draft(**kw):
    return dict({
        "company": "Acme Analytics", "role": "Senior Data Analyst", "abbr": "AcmeAnalytics",
        "summary": "Analyst who builds weekly demand forecasts that move stock.",
        "tools": "SQL", "posting": "Forecast demand with SQL.",
        "p1": "Demand moves weekly. At Brindle & Hart I forecast it by depot.",
        "p2": "Acme Analytics serves retailers.", "lead": "Where I would start:",
        "cl_bullets": [{"label": "Forecasting", "text": "Weekly depot forecasts."}],
        "p4": "I am based in Manchester.",
    }, **kw)


def test_the_letter_is_addressed_to_the_named_person(tmp_path, monkeypatch):
    d = R.build(_draft(contact_person="Shirin Example", req_id="AA-2231"))
    assert d["salutation"] == "Shirin Example" and d["req_id"] == "AA-2231"
    monkeypatch.setattr(R.gen.docpaths, "letter_tex", lambda abbr: str(tmp_path / "l.tex"))
    R.letter(d)
    tex = (tmp_path / "l.tex").read_text()
    assert "Dear Shirin Example," in tex and "(requisition AA-2231)" in tex.splitlines()[1]
    assert R.build(_draft())["salutation"] == "Acme Analytics" + R._SALUTATION_SUFFIX


def test_the_workflow_carries_both_fields_into_the_draft():
    with open(os.path.join(ROOT, ".claude", "workflows", "draft-applications.js"),
              encoding="utf-8") as fh:
        text = fh.read()
    props = text.split("const DRAFT_PROPS", 1)[1].split("\n}\n", 1)[0]
    assert "contact_person:" in props and "req_id:" in props
    assert "- contact_person: the research's named_contact" in text


def test_a_named_contact_and_the_requisition_reach_the_row():
    row = record_drafts._row_for(_draft(contact_person="Shirin Example", req_id="AA-2231"),
                                 {"fit": 70}, "2026-10-19", "r1")
    assert row["contact_person"] == "Shirin Example"
    assert "Req AA-2231." in row["notes"]
    plain = record_drafts._row_for(_draft(), {"fit": 70}, "2026-10-19", "r1")
    assert plain["contact_person"] == "" and "Req" not in plain["notes"]
