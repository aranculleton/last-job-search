"""An interview's live prep: built in the order the interview runs, and checked before it is shown.

The living document is read the night before; the live prep is held in the minutes before
and practised from. The engine (`tools/interview_live.py`) builds its parts from the round's
real shape, the questions and stories from the records, and the private notes from the
profile; Claude writes the words to say into a copy and passes it back, and nothing is
written until every check passes. These pin the shape, the merge and each check.

Every person, employer and role here is invented: the candidate is the example person, and
the application is the made-up one `tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_live as L  # noqa: E402
import interview_pack as P  # noqa: E402
from test_interview_pack import COMPANY, ROLE, _ctx, app  # noqa: E402,F401


# The example person's invented application, on disk for every test here.
pytestmark = pytest.mark.usefixtures("app")


def _fill(doc):
    """What Claude writes into the copy: an opening for every part, every answer said aloud,
    its follow-ups, the terms and what to ask next. Every figure is the example person's own."""
    d = copy.deepcopy(doc)
    for p in d["parts"]:
        p["say"] = [{"t": "Thanks for making the time, and I'm glad to be talking about the "
                          "planning work at Fernhill Freight.", "prompts": []},
                    {"t": "The thread through my work is turning messy [[demand-forecast|forecasts]] "
                          "into numbers planners trust, and the clearest case is the safety stock "
                          "we freed.", "prompts": [d["questions"][0]["id"]]}]
    for q in d["questions"]:
        q["simple"] = ("I rebuilt the weekly forecast in Python and SQL, with promotions and "
                       "seasonality in it. Error came down from 22% to 14% across 2,400 SKUs. "
                       "That released about £1.1M of safety stock.")
        q["detailed"] = ("Forecast error sat at 22% across 2,400 SKUs, and planners were covering it "
                         "with extra safety stock. I rebuilt the weekly forecast in Python and SQL, "
                         "with promotions and seasonality as features. Error came down to 14%, and "
                         "about £1.1M of safety stock was released.")
        for f in q["follow"]:
            f["simple"] = ("I owned the model and the error tracking by site. The planners owned "
                           "the decisions it fed.")
    for a in d["ask"]:
        a["follow"] = [{"if": "it is mostly forecasting", "then": "Which part of it moves "
                                                                   "stock most?"}]
    d["terms"] = {"demand-forecast": {
        "name": "Demand forecast",
        "here": "At Fernhill Freight, how many pallets each cross-dock will move next week.",
        "example": "If a site moved 1,000 pallets last week and a promotion starts, the forecast "
                   "might say 1,150.",
        "plain": "A best guess at how much will be needed, made from what happened before.",
        "technical": "A time-series model of volume by site and week."}}
    return d


def _built(**kw):
    return L.build(_ctx(**kw))


# ------------------------------------------------------------------ the shape follows the round

def test_the_engine_builds_the_rounds_own_shape_from_the_records():
    doc = _built()
    # outcome.md books a technical interview next, with the head of planning.
    assert doc["shape"] == "technical" and doc["shape_name"] == "A technical interview"
    assert [p["kind"] for p in doc["parts"]] == ["opening", "experience", "technical", "close"]
    assert sum(p["minutes"] for p in doc["parts"]) <= doc["minutes"] == 60
    assert doc["company"] == COMPANY and doc["role"] == ROLE
    # Each question sits in a part, with who is likely to ask it, and the story it is told with.
    assert doc["questions"] and all(q["part"] in {p["id"] for p in doc["parts"]} for q in doc["questions"])
    assert all(q["who"] in L.PERSONAS for q in doc["questions"])
    told = [q for q in doc["questions"] if q["story"]]
    assert told and all(f["who"] in L.PERSONAS for q in told for f in q["follow"])
    # The story bank: each of the person's stories once, with what it proves and where it is used.
    titles = [s["title"] for s in doc["stories"]]
    assert len(titles) == len(set(titles)) == 4
    assert any(s["questions"] for s in doc["stories"])
    assert all(s["proves"] for s in doc["stories"])
    # The private notes come from the profile: notice, where they are, what not to say.
    priv = doc["private"]
    assert priv["notice"] == "One month." and priv["based"]
    assert any("CIPS" in x or "SAP" in x or "parcel" in x for x in priv["not_to_say"])
    assert priv["red_flags"]
    # The questions to ask end on the close.
    assert doc["ask"][-1]["q"] == P.CLOSE_QUESTION
    # Timing from the words, at the person's own speed.
    assert doc["timing"]["wpm"] == 150 and set(doc["timing"]["parts"]) == {p["id"] for p in doc["parts"]}


@pytest.mark.parametrize("stage,company_type,shape", [
    ("Recruiter screen", "", "screen"),
    ("Hiring manager interview", "", "manager"),
    ("Take-home presentation", "", "take_home"),
    ("Panel interview", "", "panel"),
    ("Final round", "", "final"),
    ("Second interview", "consulting", "case"),
])
def test_each_kind_of_round_has_its_own_parts(stage, company_type, shape):
    ctx = _ctx(stage=stage)
    if company_type:
        ctx["row"] = dict(ctx["row"], sector="Management consulting")
    s, _why = L.shape_of(ctx)
    assert s == shape
    doc = L.build(ctx)
    kinds = [p["kind"] for p in doc["parts"]]
    assert kinds[0] == "opening" and kinds[-1] == "close"
    if shape == "case":
        assert "case" in kinds and "personal" in kinds and doc["assumed"]
    if shape == "screen":
        assert "basics" in kinds and doc["minutes"] == 30


def test_an_offer_is_not_built_as_an_interview():
    with pytest.raises(ValueError):
        L.build(_ctx(stage="Offer received"))


def test_a_faster_speaker_is_timed_at_their_own_speed(monkeypatch):
    import person
    real = person.get
    monkeypatch.setattr(person, "get", lambda k, d=None: 190 if k == "interview.words_per_minute" else real(k, d))
    assert L.build(_ctx())["timing"]["wpm"] == 190


# ------------------------------------------------------------------ Claude's words, kept and checked

def test_a_filled_prep_passes_every_check_and_is_written():
    ctx = _ctx()
    doc = _fill(L.build(ctx))
    path, found = L.write(ctx, doc)
    assert found == [], found
    assert path.endswith(L.LIVE) and os.path.exists(path)
    kept = L.load(os.path.dirname(path))
    assert kept and kept["checked"]["problems"] == 0
    # A rebuild keeps every word Claude wrote, matched by the question.
    again = L.merge(L.build(ctx), kept)
    assert [q["simple"] for q in again["questions"]] == [q["simple"] for q in kept["questions"]]
    assert again["terms"] == kept["terms"]
    assert again["parts"][1]["say"][1]["prompts"] == kept["parts"][1]["say"][1]["prompts"]
    # The page's copy leaves out what Claude wrote it from.
    page = L.for_page(kept)
    assert all("from" not in q for q in page["questions"])
    assert L.likely(kept)[0]["question"]


def test_an_empty_prep_says_what_to_write_in_plain_words():
    found = L.problems(L.build(_ctx()), _ctx())
    said = " ".join(w for _q, w in found)
    assert "not written yet" in said and "nothing to say first yet" in said
    assert "python3" not in said and ".json" not in said and ".py" not in said


def _one(doc, change):
    d = copy.deepcopy(doc)
    change(d)
    return [w for _where, w in L.problems(L.finish(d), _ctx())]


@pytest.fixture
def ready_doc():
    doc = _fill(L.build(_ctx()))
    assert L.problems(doc, _ctx()) == []
    return doc


def test_a_term_that_is_not_there_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["parts"][0]["say"].append({"t": "We use [[cross-dock]] sites.", "prompts": []}))
    assert any("no such term" in w for w in got)


def test_a_term_with_no_worked_example_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["terms"]["demand-forecast"].update(example=""))
    assert any("worked example" in w for w in got)


def test_a_term_not_explained_in_the_employers_own_work_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["terms"]["demand-forecast"].update(
        here="A guess at future volume.", example="If 100 boxes moved, next week might be 110."))
    assert any("own work" in w for w in got)


def test_a_one_line_simple_answer_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["questions"][0].update(simple="I rebuilt the forecast."))
    assert any("1 sentence" in w and "2 to 4" in w for w in got)


def test_a_simple_answer_of_five_sentences_is_caught(ready_doc):
    long = " ".join(["I rebuilt the forecast."] * 5)
    got = _one(ready_doc, lambda d: d["questions"][0].update(simple=long, detailed=long + " " + long[:60]))
    assert any("5 sentences" in w for w in got)


def test_a_detailed_answer_too_long_or_no_longer_is_caught(ready_doc):
    q = ready_doc["questions"][0]
    longer = _one(ready_doc, lambda d: d["questions"][0].update(detailed=(q["detailed"] + " ") * 2))
    assert any("keep it under" in w for w in longer)
    same = _one(ready_doc, lambda d: d["questions"][0].update(detailed=q["simple"]))
    assert any("no longer than the simple one" in w for w in same)


def test_a_long_dash_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["questions"][0].update(simple=d["questions"][0]["simple"].replace(
        ", with promotions", " — with promotions")))
    assert any("long dash" in w for w in got)


def test_words_that_assume_an_earlier_conversation_are_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["parts"][0]["say"].append(
        {"t": "As we discussed, the forecast is the heart of it, and I'd love to go deeper.", "prompts": []}))
    assert any("assumes you have spoken before" in w for w in got)


def test_an_opening_that_says_you_raised_it_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["parts"][1]["say"].append(
        {"t": "You raised the depots, so I'll start with how the forecast reached them.", "prompts": []}))
    assert any("assumes you have spoken before" in w for w in got)


def test_what_the_grounding_check_refuses_is_refused(ready_doc):
    # The example person's market says CV, never resume (person.json documents).
    def word(d):
        d["questions"][0]["simple"] = ("My resume has the detail on it. I rebuilt the weekly forecast "
                                       "in Python and SQL, and error came down from 22% to 14%.")
    got = _one(ready_doc, word)
    assert any("resume" in w.lower() for w in got), got


def test_a_numbered_beat_is_caught(ready_doc):
    got = _one(ready_doc, lambda d: d["parts"][0]["say"].append(
        {"t": "1. First, the forecast, and second, the stock it freed.", "prompts": []}))
    assert any("number off the front" in w for w in got)


def test_too_many_words_for_the_parts_time_is_caught(ready_doc):
    def pad(d):
        d["parts"][0]["say"] = [{"t": " ".join(["and the forecast held up across the sites"] * 150) + ".",
                                 "prompts": []}]
    got = _one(ready_doc, pad)
    assert any("minutes to say at 150 words a minute" in w for w in got)


def test_a_known_question_must_be_placed_and_answered_in_an_opening():
    ctx = _ctx()
    doc = _fill(L.build(ctx))
    doc["known"] = [{"text": "How do you get depot managers to trust a forecast?", "from": "the recruiter"}]
    merged = L.merge(L.build(ctx), doc)
    k = merged["known"][0]
    assert k["question"], "the known question is placed on a question of its own"
    q = next(q for q in merged["questions"] if q["id"] == k["question"])
    assert q["known"] == k["id"]
    got = [w for _x, w in L.problems(merged, ctx)]
    assert any("answer it in what you say first" in w for w in got)
    # Marked in the opening of its part, it passes.
    part = next(p for p in merged["parts"] if p["id"] == q["part"])
    part["say"].append({"t": "Trust is usually the first thing people ask about, so I'll take it "
                             "head on: I show the error by site every week.", "prompts": [q["id"]],
                        "known": k["id"]})
    q["simple"] = ("I show the error by site every week, so the planners can see where it holds. "
                   "Then they trust it where it has earned it.")
    q["detailed"] = ("I show the error by site every week, so the planners can see where it holds "
                     "and where it does not. Then they trust it where it has earned it, and tell "
                     "me where it misses.")
    assert [w for _x, w in L.problems(L.finish(merged), ctx)] == []


def test_a_figure_the_profile_does_not_hold_is_refused_unless_it_is_a_draft(ready_doc):
    def bad(d):
        d["questions"][0]["simple"] = ("I rebuilt the weekly forecast in Python and SQL. Error came "
                                       "down by 40% across 2,400 SKUs. That freed stock.")
    got = _one(ready_doc, bad)
    assert any("40%" in w and "does not hold" in w for w in got)

    def drafted(d):
        bad(d)
        d["questions"][0]["draft"] = True
    got = _one(ready_doc, drafted)
    assert not any("40%" in w for w in got), "a draft they asked for is theirs to confirm"
    d = copy.deepcopy(ready_doc)
    drafted(d)
    assert L.drafts(d) == [d["questions"][0]["q"]]


def test_a_follow_up_four_deep_is_caught(ready_doc):
    def deep(d):
        node = {"who": "peer", "q": "And then?", "simple": "Then the planners took it on. They "
                                                         "still run it.", "follow": []}
        d["questions"][0]["follow"] = [dict(node, follow=[dict(node, follow=[dict(node, follow=[dict(node)])])])]
    assert any("three deep" in w for w in _one(ready_doc, deep))


def test_the_command_builds_checks_and_writes(tmp_path):
    env = dict(os.environ)
    out = tmp_path / "live.json"
    run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), *a],
                                    capture_output=True, text=True, encoding="utf-8", env=env)
    got = run("live", COMPANY, "--role", ROLE, "--out", str(out))
    assert got.returncode == 0, got.stderr
    assert "still to write" in got.stdout
    doc = json.loads(out.read_text(encoding="utf-8"))
    refused = run("live", COMPANY, "--role", ROLE, "--fill", str(out), "--write")
    assert refused.returncode == 1 and "not written" in refused.stdout
    out.write_text(json.dumps(_fill(doc)), encoding="utf-8")
    ok = run("live", COMPANY, "--role", ROLE, "--fill", str(out), "--write")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "written" in ok.stdout
    assert run("live-check", COMPANY, "--role", ROLE).returncode == 0


# ------------------------------------------------------------------ the page's copy, and older preps

def test_the_page_gets_the_live_prep_only_for_the_round_it_was_built_for():
    import app_model
    ctx = _ctx()
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found
    folder = os.path.dirname(path)
    got = app_model._live_prep(folder, {"label": ctx["stage"]}, [])
    assert got and got["parts"] and got["likely"] and got["personas"]["recruiter"] == "Recruiter"
    assert all("from" not in q for q in got["questions"])
    # A prep for another round is not this round's: the page draws the older reading until
    # /interview makes it again, never a prep for the wrong round.
    assert app_model._live_prep(folder, {"label": "Final round"}, []) is None
    # A file that is not one (cut short, or from a newer version) is never drawn.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"version": 99, "parts": [')
    assert app_model._live_prep(folder, {"label": ctx["stage"]}, []) is None
