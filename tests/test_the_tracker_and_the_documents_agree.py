"""The tracker and the documents on disk are checked against each other, and nothing is
deleted.

The 2026-11-10 audit (NW-23): eight rows drafted one day named a resume and no cover letter,
though each one's letter was on disk; a few dozen letters and resumes had no row at all, and
nothing said so. `python3 tools/record_drafts.py check` names a letter on disk that its row
does not, a document no row names, and a row naming a document that is not there, and moves
or deletes nothing. Every person and employer is invented.
"""
from __future__ import annotations

import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import csv_store  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402
import record_drafts  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    tracker = person.state("job_search_tracker.csv")
    rows = [{"date": "2026-11-04", "company": "Ottergate Foods", "role": "Pricing Analyst",
             "status": "applied", "cv_file": docpaths.resume_rel("Ottergate"),
             "cover_letter_file": ""},
            {"date": "2026-11-04", "company": "Quillfeather Bank", "role": "Risk Analyst",
             "status": "applied", "cv_file": docpaths.resume_rel("Quillfeather"),
             "cover_letter_file": docpaths.letter_rel("Quillfeather")}]
    csv_store.write_rows(tracker, rows, record_drafts.HEADER)
    for rel in (docpaths.resume_rel("Ottergate"), docpaths.letter_rel("Ottergate"),
                docpaths.resume_rel("Quillfeather"), docpaths.letter_rel("Ashgrove"),
                docpaths.resume_rel("General", ".pdf")):
        p = person.state(*rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x")
    return tracker


def test_each_disagreement_is_named_and_nothing_is_deleted(state, capsys):
    got = record_drafts.unrecorded(state)
    assert got["letters"] == ["Ottergate Foods | Pricing Analyst: "
                              + docpaths.letter_rel("Ottergate")]
    assert got["files"] == [os.path.splitext(docpaths.letter_rel("Ashgrove"))[0]]
    assert got["missing"] == ["Quillfeather Bank | Risk Analyst: "
                              + docpaths.letter_rel("Quillfeather")]
    assert record_drafts.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "Ottergate" in out and "Ashgrove" in out and "Quillfeather" in out
    assert os.path.isfile(person.state(*docpaths.letter_rel("Ashgrove").split("/")))


# The independent review of NW-23 (2026-11-11): the app's own templates, in every person's
# copy, were listed as documents with no row, so the check always failed.
def test_the_apps_own_templates_are_never_a_document_with_no_row(state, capsys):
    for rel in ("cv/main_example.tex", "cover_letters/cover_example.tex",
                "cover_letters/cover.cls"):
        p = person.state(*rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x")
    files = record_drafts.unrecorded(state)["files"]
    assert not [f for f in files if "example" in f or "cover.cls" in f], files
