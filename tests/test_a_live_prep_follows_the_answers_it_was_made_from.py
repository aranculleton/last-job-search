"""A live prep never shows answers the prep has since corrected, and goes as deep as a
technical interviewer digs (issue 363).

A chat corrected answers in interview_prep.md and brought the page up to date. The person
still saw the old wording: the live screen draws its questions, points and follow-ups from
interview_live.json, built earlier, and nothing told the chat the two had diverged. Every
question there had two follow-ups, three deep at most, where a technical interviewer goes
four or five, and a modelling answer could say what the model was written in and never the
model the profile records.

Every person, employer and answer here is invented: the example person, and the made-up
application `tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import copy
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

pytestmark = pytest.mark.usefixtures("app_fixture")

QUESTION = "Walk me through a project end to end."
FIRST = ("The clearest one is the weekly forecast I rebuilt, because planners were covering a 22% "
         "error with extra stock, and I brought it down to 14% across 2,400 SKUs.")
FIXED = ("The clearest one is the weekly forecast I rebuilt, because planners were covering a 22% "
         "error with extra safety stock, and I brought it down to 14%, which freed about £1.1M.")


def _answer(path, words):
    text = open(path, encoding="utf-8").read()
    head, rest = text.split("### %s\n" % QUESTION, 1)
    body, tail = rest.split("\n### ", 1)
    keep = [ln for ln in body.splitlines() if ln.startswith(P.INTENT_MARK)]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "### %s\n" % QUESTION + "\n".join(keep + [words, ""]) + "\n### " + tail)


def test_a_corrected_answer_takes_the_old_live_prep_off_the_page_and_says_so():
    ctx = _ctx()
    pack = P.write_pack(ctx)
    _answer(pack, FIRST)
    folder = os.path.dirname(pack)
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found
    stage = {"label": ctx["stage"]}
    assert app_model._live_prep(folder, stage, []) is not None
    assert not app_model._live_behind(folder, stage)
    # A rebuild of the document that changes no answer keeps the live prep current.
    P.write_pack(_ctx())
    assert L.behind(folder) is False
    # The chat corrects the answer in interview_prep.md only.
    _answer(pack, FIXED)
    assert L.behind(folder) is True
    # The page shows the prep as corrected, never the older live screen...
    assert app_model._live_prep(folder, stage, []) is None
    assert app_model._live_behind(folder, stage)
    # ...and the chat that draws the page is told to build it again, and how.
    said = app.live_behind_lines({"interviews": [{"company": COMPANY, "role": ROLE,
                                                  "next_stage": ctx["stage"], "live_behind": True}]})
    assert said and "interview_prep.md changed" in said[0] and "live --fill" in said[0]
    # Kept again with no words, it would claim to follow answers it does not say: refused.
    assert P.main(["live", COMPANY, "--role", ROLE, "--write"]) == 1
    assert L.behind(folder) is True
    # Built again with the words, it follows the prep again.
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found and L.behind(folder) is False
    assert app_model._live_prep(folder, stage, []) is not None


def test_a_live_prep_saved_before_it_kept_its_source_is_still_shown():
    ctx = _ctx()
    P.write_pack(ctx)
    path, _found = L.write(ctx, _fill(L.build(ctx)))
    import json
    doc = json.load(open(path, encoding="utf-8"))
    doc.pop("prep_sig")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh)
    folder = os.path.dirname(path)
    assert L.behind(folder) is None
    assert app_model._live_prep(folder, {"label": ctx["stage"]}, []) is not None


def _chain(n, who="technical"):
    """A line of follow-ups n deep, one at each level."""
    node = None
    for i in range(n, 0, -1):
        node = {"who": who, "q": "And then what, level %d?" % i, "simple": ["a point"],
                "detailed": "", "follow": [node] if node else []}
    return node


def _deep(doc, kind):
    return [(w, why) for w, why in L.problems(doc) if "deep" in why
            and any(q["q"] in w for q in doc["questions"]
                    if (dict((p["id"], p["kind"]) for p in doc["parts"]))[q["part"]] == kind)]


def test_a_technical_question_goes_four_deep_and_others_stay_three():
    ctx = _ctx()
    doc = _fill(L.build(ctx))
    kinds = {p["id"]: p["kind"] for p in doc["parts"]}
    tech = next(q for q in doc["questions"] if kinds[q["part"]] in L.TECH_PARTS
                and not q["id"].startswith("problem"))
    other = next(q for q in doc["questions"] if kinds[q["part"]] not in L.TECH_PARTS + ("close",))
    other["who"] = "manager"
    for q in (tech, other):
        q["simple"] = ["the forecast I rebuilt", "error down to 14%", "about £1.1M freed"]
        q["follow"] = [_chain(3), _chain(1)]
    three = copy.deepcopy(doc)
    found = [why for w, why in L.problems(three) if "deep" in why and tech["q"] in w]
    assert any("4 deep" in why for why in found), found
    assert not [why for w, why in L.problems(three) if "deep" in why and other["q"] in w
                and "then" not in w]
    # Four deep, with a fifth allowed: the technical one passes, and four follow-ups are allowed.
    tech["follow"] = [_chain(4), _chain(1), _chain(1), _chain(1)]
    assert not [why for w, why in L.problems(doc) if tech["q"] in w and (
        "deep" in why or "follow-up" in why)]
    tech["follow"] = [_chain(6), _chain(1)]
    assert any("five deep at most" in why for w, why in L.problems(doc) if tech["q"] in w)
    # The rest stay as they were: three deep at most.
    other["follow"] = [_chain(4), _chain(1)]
    assert any("three deep at most" in why for w, why in L.problems(doc) if other["q"] in w)


def test_a_modelling_answer_names_the_model_the_profile_records(tmp_path, monkeypatch):
    profile = tmp_path / "profile.md"
    profile.write_text("- Built weekly demand forecasts as gradient-boosted trees (LightGBM), "
                       "cutting forecast error from 22% to 14%\n", encoding="utf-8")
    real = P.person.file
    monkeypatch.setattr(P.person, "file", lambda key, default: str(profile)
                        if key == "candidate_profile" else real(key, default))
    ctx = _ctx()
    doc = _fill(L.build(ctx))
    told = [q for q in doc["questions"] if q.get("story") and P.technical(q["q"])]
    assert told, [q["q"] for q in doc["questions"]]
    found = [why for w, why in L.problems(doc) if "the model" in why]
    # The fill says "in Python and SQL" and never the model the profile records.
    assert found and "LightGBM" in found[0]
    for q in told:
        q["simple"] = q["simple"].replace("in Python and SQL", "as gradient-boosted trees")
        q["detailed"] = q["detailed"].replace("in Python and SQL", "as gradient-boosted trees")
    assert not [why for w, why in L.problems(doc) if "the model" in why]
