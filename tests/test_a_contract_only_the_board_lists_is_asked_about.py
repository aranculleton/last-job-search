"""A role the job board lists as a contract is asked about, though its text never says so.

Staging asks before drafting a contract for someone who wants a permanent job, and it read
the terms from the posting's words alone. LinkedIn's own "Employment type: Contract" line,
which the detail fetch already returns, was dropped, so a contract whose text never said
"contract" was "not stated" and drafted with no question. Now the board's type decides only
where the words say nothing, and the question says where it came from. The posting's own
words still win both ways, and "Full-time", which says nothing of how a job is held, is no
answer. From ai-job-search (#619). Every employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hydrate  # noqa: E402
import posting_profile as P  # noqa: E402
import run_round  # noqa: E402

TODAY = dt.date(2026, 11, 11)
SILENT = "We build demand forecasts for our depots. You know SQL and Python. Hybrid, Leeds."


def test_the_boards_type_decides_only_where_the_words_say_nothing():
    assert P.terms(SILENT, "Data Analyst", TODAY, "Contract")["kind"] == "contract"
    assert P.terms(SILENT, "Data Analyst", TODAY, "Temporary")["kind"] == "fixed-term"
    assert P.terms(SILENT, "Data Analyst", TODAY, "Internship")["kind"] == "fixed-term"
    for listed in (None, "", "Full-time", "Part-time", "Other"):
        assert P.terms(SILENT, "Data Analyst", TODAY, listed)["kind"] == "not stated", listed
    # The posting's own words win, whichever way they go.
    perm = SILENT + " This is a permanent, full-time role."
    assert P.terms(perm, "Data Analyst", TODAY, "Contract")["kind"] == "permanent"
    six = SILENT + " This is a 6-month fixed-term contract."
    got = P.terms(six, "Data Analyst", TODAY, "Full-time")
    assert got["kind"] == "fixed-term" and got["months"] == 6 and "source" not in got


def test_the_question_says_the_board_lists_it(monkeypatch):
    monkeypatch.setattr(P, "wants_contracts", lambda: False)
    row = {"company": "Kestrel Mutual", "title": "Data Analyst", "employment_type": "Contract",
           "url": "https://jobs.example/kestrel/1"}
    (q,) = [q for q in P.questions(P.read(row, SILENT, rows=[], today=TODAY), row)
            if q["id"] == "contract"]
    assert q["question"] == ("Data Analyst at Kestrel Mutual is a contract, the job board "
                             "lists it so, though the posting does not say. Do you still "
                             "want it drafted?")
    said = dict(row, employment_type="Full-time")
    assert not [q for q in P.questions(P.read(said, SILENT + " A 12-month contract.", rows=[],
                                              today=TODAY), said)
                if "job board" in q["question"]]


def test_linkedins_type_reaches_the_shortlist(monkeypatch):
    monkeypatch.setitem(hydrate.CLI, "linkedin", lambda: "cli.mjs")
    monkeypatch.setattr(hydrate.portals, "is_enabled", lambda skill: True)
    monkeypatch.setattr(hydrate.portals, "runtime", lambda: ("node",))
    monkeypatch.setattr(hydrate, "pace", lambda skill: True)
    monkeypatch.setattr(hydrate.portals, "run_cli", lambda cmd, timeout=60, empty=None: (
        {"id": "4012345678", "description": SILENT, "employmentType": "Contract"}, None))
    got = hydrate.fetch({"portal": "linkedin", "id": "4012345678", "url": "u"})
    assert got["employment_type"] == "Contract" and got["desc"] == SILENT
    assert "employment_type" in run_round.SUMMARY_FIELDS
