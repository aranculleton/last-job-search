"""The interview-prep pipeline holds what the QA audit of issue 369 found broken.

Every person, employer and answer here is invented: the example person, and the made-up
application `tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import app  # noqa: E402
import app_model  # noqa: E402
import interview_live as L  # noqa: E402
import interview_pack as P  # noqa: E402
from test_an_interview_has_a_live_prep import _fill  # noqa: E402
from test_interview_pack import COMPANY, ROLE, _ctx, app as app_fixture  # noqa: E402,F401


def _live(ctx):
    P.write_pack(ctx)
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found
    return path


def _restamp(path, checks):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["checked"]["checks"] = checks
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh)


# ---------------------------------------------------------------- 1. checks grow stricter

@pytest.mark.usefixtures("app_fixture")
def test_a_live_prep_that_fails_stricter_checks_is_not_shown_as_ready(monkeypatch):
    ctx = _ctx()
    path = _live(ctx)
    folder, stage = os.path.dirname(path), {"label": ctx["stage"]}
    # Written under these checks: shown, with nothing to check again.
    assert L.recheck(folder) == []
    assert app_model._live_prep(folder, stage, []) is not None
    # The app updates and its checks grow stricter: this prep no longer passes them.
    _restamp(path, "older-checks")
    strict = L.problems

    def stricter(doc, ctx_=None):
        return strict(doc, ctx_) + [("what to say first", "a rule added since")]
    monkeypatch.setattr(L, "problems", stricter)
    assert L.recheck(folder)
    assert app_model._live_prep(folder, stage, []) is None
    assert app_model._live_unfit(folder, stage)
    said = app.live_behind_lines({"interviews": [{"company": COMPANY, "role": ROLE,
                                                  "next_stage": ctx["stage"], "live_unfit": True}]})
    assert said and "live-check" in said[0]


@pytest.mark.usefixtures("app_fixture")
def test_a_live_prep_from_older_checks_that_still_passes_stays_shown():
    ctx = _ctx()
    path = _live(ctx)
    _restamp(path, "older-checks")
    folder = os.path.dirname(path)
    assert L.recheck(folder) == []
    assert app_model._live_prep(folder, {"label": ctx["stage"]}, []) is not None


# ---------------------------------------------------------------- 2. outcome.md against the tracker

def test_outcome_md_resolved_ends_the_interview_the_tracker_still_calls_live(tmp_path):
    import what_works
    from test_a_tick_on_the_page_is_applied_once import Search
    assert what_works.outcome_status("# Outcome\n\n**Status:** withdrawn\n") == "withdrawn"
    assert what_works.outcome_status("**Status:** interview_only\n") == "withdrawn"
    assert what_works.outcome_status("**Status:** in_progress\n") == ""
    assert what_works.outcome_status("# Outcome\n") == ""
    search = Search(str(tmp_path))
    folder = os.path.join(search.state, "documents", "applications",
                          "thornbury_bank_risk_analyst_thornbury")
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Outcome\n\n**Status:** withdrawn\n\n## Interview stages reached\n\n"
                 "- [x] Phone screen (2026-10-15, with the recruiter)\n")
    got = next(i for i in search.model()["interviews"] if i["company"] == "Thornbury Bank")
    # The file's end holds: past, no invented next round, nothing waiting to hear.
    assert got["status"] == "withdrawn" and got["past"] is True and not got.get("had"), got
    assert got["tracker_status"] == "interview"
    said = app.live_behind_lines({"interviews": [got]})
    assert any("outcome.md says withdrawn" in s for s in said), said


# ---------------------------------------------------------------- 3. a stock answer not for them

NOTICE = {"question": "What is your notice period?", "alternatives": ["What is your notice period?"],
          "use_for": [], "answer": "Three months, and I would rather not leave early.",
          "source": "profile/answers.md", "suits": ("bank",), "not_for": (), "fill_in": "",
          "confirm": False}


def _fits(a):
    return not a.get("suits")


def test_a_stock_answer_that_works_against_them_is_never_offered():
    assert P._answer_for("What is your notice period?", [NOTICE], fits=_fits) is None
    assert P._answer_for("What is your notice period?", [NOTICE]) is NOTICE
    # One that fits is still taken over one that does not.
    other = dict(NOTICE, suits=(), answer="One month.")
    assert P._answer_for("What is your notice period?", [NOTICE, other], fits=_fits) is other


@pytest.mark.usefixtures("app_fixture")
def test_the_live_preps_notice_never_comes_from_an_answer_not_for_them(monkeypatch):
    ctx = _ctx()
    ctx["answers"] = [NOTICE]
    monkeypatch.setattr(P, "employer_type", lambda _ctx: "consulting")
    assert P.against_employer(NOTICE, ctx)
    assert "Three months" not in L.private_notes(ctx)["notice"]
    item = {"question": "What is your notice period?", "source": "the posting"}
    got = P.answer_for(item, ctx)
    text = "\n".join(got["lines"])
    assert "left out for" in text and "Prepared: Three months" not in text


# ---------------------------------------------------------------- 4. two roles, one folder

LONG = ("Senior Consultant, Supply Chain Planning and Inventory Optimisation Transformation "
        "Programme, %s")


def _rows(tmp_path, roles):
    import csv
    from test_interview_pack import ROW
    with open(tmp_path / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ROW))
        w.writeheader()
        for role in roles:
            w.writerow(dict(ROW, role=role))


@pytest.mark.usefixtures("app_fixture")
def test_two_long_titles_at_one_employer_get_a_folder_each(tmp_path):
    import docpaths
    first, second = LONG % "North", LONG % "South"
    # Before either is in the tracker, both names are cut to one.
    assert docpaths.app_folder(COMPANY, first) == docpaths.app_folder(COMPANY, second)
    _rows(tmp_path, [ROLE, first, second])
    docpaths.forget_abbreviations()
    a, b = docpaths.app_folder(COMPANY, first), docpaths.app_folder(COMPANY, second)
    assert a != b
    # The first keeps the name it always had, so a folder already on disk is found as before.
    assert os.path.basename(a) == docpaths.slug(COMPANY, first, "Fernhill")
    assert "_alt_" in os.path.basename(b)
    # Never read as one application's folder under another's name.
    os.makedirs(a)
    os.makedirs(b)
    assert docpaths.twin_folders() == []
    # A short title is never touched.
    assert "_alt_" not in docpaths.app_folder(COMPANY, ROLE)


@pytest.mark.usefixtures("app_fixture")
def test_a_role_two_applications_answer_to_is_refused_not_guessed(tmp_path):
    from test_interview_pack import ROW
    rows = [dict(ROW, role="Demand Planning Analyst (Hybrid)"),
            dict(ROW, role="Demand Planning Analyst (Remote)")]
    with pytest.raises(LookupError, match="names"):
        P._row(COMPANY, "Demand Planning Analyst", rows)
    assert P._row(COMPANY, "Demand Planning Analyst (Remote)", rows) is rows[1]


# ---------------------------------------------------------------- 5. a stage ticked by hand

@pytest.mark.parametrize("word", ["done", "held", "had", "held on"])
def test_a_stage_ticked_done_by_hand_keeps_its_day_who_and_length(word):
    import what_works
    text = ("## Interview stages reached\n\n- [x] Round 1 with the hiring manager (%s 2026-11-23 "
            "16:00 Europe/London, 60 min, with the head of planning)\n" % word)
    s, = what_works.outcome_stages(text, "2026-11-25")
    assert s["done"] and s["date"] == "2026-11-23" and s["time"] == "16:00"
    assert s["zone"] == "Europe/London" and s["minutes"] == 60
    assert s["with"] == "the head of planning" and not s["scheduled"]


# ---------------------------------------------------------------- 6. a checklist line is not a stage

NOTE = ("Round 2: the recruiter said it will be a case study with a partner and a senior "
        "manager, about an hour, on the pricing work they are doing for a retail client, and to "
        "bring a laptop in case they ask for a quick model")


def test_a_note_in_the_checklist_is_never_a_stage_and_one_round_is_one_line():
    import what_works
    text = ("## Interview stages reached\n\n"
            "- [x] Phone screen (2026-11-02, with the recruiter)\n"
            "- [x] Paused until the hiring manager knew the headcount\n"
            "- [ ] Round 2 (scheduled 2026-12-01 10:00 Europe/London, with a partner)\n"
            "- [ ] %s\n"
            "- [ ] Offer received\n" % NOTE)
    stages = what_works.outcome_stages(text, "2026-11-25")
    assert [s["label"] for s in stages] == ["Phone screen", "Round 2", "Offer received"]
    r2 = stages[1]
    assert r2["date"] == "2026-12-01" and r2["notes"] == [NOTE]
    # The furthest step reached is the screen, never a technical round held.
    assert [s["step"] for s in stages if s["done"]] == ["screen"]

