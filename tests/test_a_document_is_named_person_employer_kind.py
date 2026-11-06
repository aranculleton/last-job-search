"""A made document is named the person, the employer, then the kind of document.

The maintainer, 2026-11-06: "can documents be name_place_document not name_document_place".
A resume was <Prefix>_CV_<ABBR> and a letter <Prefix>_Cover_Letter_<ABBR>; now they are
<Prefix>_<ABBR>_CV and <Prefix>_<ABBR>_Cover_Letter, for the kept source and for the PDF the
person downloads and uploads. A document made in the old order keeps its name (it may have
gone to an employer under it), and every reader still finds it. The candidate is the example
person, whose word for the document is "CV"; every employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import docpaths  # noqa: E402

NEW = {"cv": "cv/Morgan_Ellis_Wrenfield_CV.tex",
       "letter": "cover_letters/Morgan_Ellis_Wrenfield_Cover_Letter.tex"}
OLD = {"cv": "cv/Morgan_Ellis_CV_Wrenfield.tex",
       "letter": "cover_letters/Morgan_Ellis_Cover_Letter_Wrenfield.tex"}
ORDERS = pytest.mark.parametrize("names", [NEW, OLD], ids=["new order", "old order"])


@pytest.fixture
def st(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    for d in ("cv", "cover_letters"):
        (tmp_path / d).mkdir()
    return tmp_path


def _touch(root, rel, ext=".tex"):
    p = root / (os.path.splitext(rel)[0] + ext)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return p


def _row(names, status="applied", role="Planner"):
    return {"date": "2026-10-01", "company": "Wrenfield", "role": role, "status": status,
            "cv_file": names["cv"], "cover_letter_file": names["letter"]}


# ------------------------------------------------------------------ a new document


def test_a_new_draft_is_named_person_employer_kind(st):
    assert docpaths.resume_rel("Wrenfield") == NEW["cv"]
    assert docpaths.letter_rel("Wrenfield") == NEW["letter"]
    assert docpaths.resume_rel("Wrenfield_Planner", ".pdf") == \
        "cv/Morgan_Ellis_Wrenfield_Planner_CV.pdf"
    assert os.path.basename(docpaths.resume_tex("Wrenfield")) == "Morgan_Ellis_Wrenfield_CV.tex"
    assert os.path.basename(docpaths.letter_pdf("Wrenfield")) == \
        "Morgan_Ellis_Wrenfield_Cover_Letter.pdf"


def test_the_tracker_row_names_the_new_order(st):
    import record_drafts
    draft = {"company": "Wrenfield", "role": "Planner", "abbr": "Wrenfield", "summary": "s",
             "p1": "A letter."}
    row = record_drafts._row_for(draft, {}, "2026-11-06", "r1")
    assert row["cv_file"] == NEW["cv"]
    assert row["cover_letter_file"] == NEW["letter"]


def test_the_download_is_named_person_employer_kind(st):
    for names in (NEW, OLD):
        assert docpaths.send_name(names["cv"].replace(".tex", ".pdf"), "Wrenfield Freight & Co.") \
            == "Morgan_Ellis_Wrenfield_Freight_CV.pdf"
        assert docpaths.send_name(names["letter"].replace(".tex", ".pdf"), "Wrenfield") \
            == "Morgan_Ellis_Wrenfield_Cover_Letter.pdf"
    assert docpaths.send_name("documents/cv/my own.pdf", "Wrenfield") == "my own.pdf"


def test_a_resume_for_no_employer_keeps_its_word_last(st):
    # documents/cv/<Prefix>_CV_current.pdf: no employer sits between the person and the
    # document, so the one already kept is still the one found.
    import general_resume
    pdf, _txt = general_resume.keep_paths()
    assert os.path.basename(pdf) == "Morgan_Ellis_CV_current.pdf"


# ------------------------------------------------------------------ an old document


def test_an_old_document_keeps_its_name_when_redrafted(st):
    _touch(st, OLD["cv"], ".pdf")
    _touch(st, OLD["letter"])
    assert docpaths.resume_rel("Wrenfield") == OLD["cv"]
    assert docpaths.letter_rel("Wrenfield") == OLD["letter"]
    # Once a new-order file is there, it is the one.
    _touch(st, NEW["cv"])
    assert docpaths.resume_rel("Wrenfield") == NEW["cv"]


@ORDERS
def test_the_name_patterns_read_both_orders(names):
    assert docpaths.resume_name_rx().search(names["cv"]).group(1) == "Wrenfield"
    assert docpaths.letter_name_rx().search(names["letter"]).group(1) == "Wrenfield"
    assert not docpaths.resume_name_rx().search(names["letter"])
    assert docpaths.doc_abbr(names["cv"]) == "Wrenfield"
    assert docpaths.doc_abbr(names["letter"]) == "Wrenfield"
    two = names["cv"].replace("Wrenfield", "Wrenfield_Planner")
    assert docpaths.doc_abbr(two) == "Wrenfield_Planner"


@ORDERS
def test_the_tracker_abbreviation_is_read_in_either_order(st, names):
    import confirm
    import csv_store
    assert confirm.abbr(_row(names)) == "Wrenfield"
    path = st / "job_search_tracker.csv"
    row = dict(_row(names), sector="", role_type="", channel="", contact_person="",
               fit_rating="", notes="", source="", deadline="")
    csv_store.write_rows(str(path), [row], list(row))
    docpaths.forget_abbreviations()
    assert docpaths._abbr_on_file("Wrenfield", "Planner") == "Wrenfield"


@ORDERS
def test_a_name_already_used_is_known_in_either_order(st, names):
    import doc_name
    import stage_picks
    rows = [_row(names)]
    assert doc_name.owners("Wrenfield", rows) == rows
    with pytest.raises(FileExistsError):
        doc_name.check_free("Wrenfield", "Wrenfield", "Planner", rows)
    _touch(st, names["cv"])
    assert stage_picks.file_taken("Wrenfield", str(st))


@ORDERS
def test_the_follow_up_finds_the_note_in_either_order(st, names):
    import followups
    docs = st / "documents" / "applications"
    folder = docs / docpaths.slug("Wrenfield", "Planner", "Wrenfield_Planner", _always=True)
    folder.mkdir(parents=True)
    (folder / "outreach.md").write_text("note", encoding="utf-8")
    row = _row({k: v.replace("Wrenfield", "Wrenfield_Planner") for k, v in names.items()})
    assert followups.outreach_note(row, str(docs)) == str(folder / "outreach.md")


@ORDERS
def test_saving_pairs_a_resume_and_its_letter_in_either_order(names):
    import land
    assert land._doc_abbr(os.path.splitext(os.path.basename(names["cv"]))[0]) == "Wrenfield"
    assert land._doc_abbr(os.path.splitext(os.path.basename(names["letter"]))[0]) == "Wrenfield"


@ORDERS
def test_a_letter_is_told_by_its_name_in_either_order(st, names):
    import check_claims
    import design_check
    import draft_pack
    import interview_pack
    letter = names["letter"].replace("cover_letters/", "elsewhere/")
    assert design_check.is_letter(letter) and check_claims.is_letter(letter)
    assert not design_check.is_letter(names["cv"].replace("cv/", "elsewhere/"))
    made = _touch(st, names["letter"])
    assert draft_pack.letter_paths() == [str(made)]
    resume = os.path.basename(names["cv"])
    assert interview_pack._file_words(resume) == "your CV"
    assert interview_pack._file_words(os.path.basename(names["letter"])) == "your cover letter"


@ORDERS
def test_a_logged_attachment_is_known_in_either_order(st, names):
    import state
    folder = st / "documents" / "applications" / "wrenfield_planner"
    folder.mkdir(parents=True)
    (folder / "draft.json").write_text(json.dumps({"abbr": "Wrenfield"}), encoding="utf-8")
    kept = state._kept_outputs(str(st))
    assert names["cv"].replace(".tex", ".pdf") in kept
    assert names["letter"] in kept
    pdf = names["cv"].replace(".tex", ".pdf").replace("Wrenfield", "Larchmoor")
    assert state.resolve_attachment(pdf, str(st)) == pdf
    letter = names["letter"].replace("Wrenfield", "Larchmoor")
    assert state.resolve_attachment(letter, str(st)) == letter
