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
                          "we freed.", "prompts": [q["id"] for q in d["questions"][:1]]}]
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
    # The follow-ups after any story are the part's, written once there (the screen review,
    # 2026-11-11: they stood under every question told with a story).
    for p in d["parts"]:
        for f in p.get("follow") or []:
            f["simple"] = ("I owned the model and the error tracking by site. The planners owned "
                           "the decisions it fed.")
    # A part for a problem worked aloud holds the problem as it is set, as Claude adds it.
    for i, p in enumerate(p for p in d["parts"] if p["kind"] == "technical"):
        d["questions"].append({
            "id": "problem%d" % (i + 1), "part": p["id"], "who": "technical",
            "q": "Given weekly demand and forecasts by site, write a function that returns the sites "
                 "whose forecast error is above a threshold.",
            "also": [], "story": None, "known": None, "draft": False, "from": [], "follow": [],
            "simple": ("I'd say it back first, so we agree the error is the gap as a share of actual "
                       "demand. Then I'd write a plain loop that skips any site with no demand, and "
                       "check it by hand on a few rows."),
            "detailed": ("I'd say it back first, so we agree the error is the gap as a share of actual "
                         "demand, and ask what the data looks like. Then I'd write a plain loop that skips "
                         "any site with no demand, and check it by hand on a few rows before tidying it.")})
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
    assert [p["kind"] for p in doc["parts"]] == ["opening", "technical", "probes", "close"]
    assert sum(p["minutes"] for p in doc["parts"]) <= doc["minutes"] == 60
    assert doc["company"] == COMPANY and doc["role"] == ROLE
    # Each question sits in a part, with who is likely to ask it, and the story it is told with.
    assert doc["questions"] and all(q["part"] in {p["id"] for p in doc["parts"]} for q in doc["questions"])
    assert all(q["who"] in L.PERSONAS for q in doc["questions"])
    told = [q for q in doc["questions"] if q["story"]]
    # Their follow-ups by who asks: those after any story said once in the part it is told in
    # (the screen review, 2026-11-11), each with who asks it.
    assert told and all(f["who"] in L.PERSONAS for q in told for f in q["follow"])
    assert all(p["follow"] and all(f["who"] in L.PERSONAS for f in p["follow"])
               for p in doc["parts"] if any(q["part"] == p["id"] for q in told))
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


def test_the_questions_to_ask_are_said_as_a_person_says_them():
    # The pack shows where a question came from ('The research says "..."'); read aloud in the
    # minutes before, that was no question anyone asks (the review, 2026-11-10).
    asks = [a["q"] for a in _built(stage="Recruiter screen")["ask"]]
    assert not [a for a in asks if "research says" in a.lower() or '"' in a], asks
    assert "I saw you opened a cross-dock in Warrington in January 2026, so what has that changed " \
           "for your team?" in asks
    assert L.said_ask('The research says "Fernhill Freight runs fourteen sites". Is that still how '
                      'the team is set up?') == ("I read that Fernhill Freight runs fourteen sites, so "
                                                 "is that still how the team is set up?")
    # The pack itself still says where each came from, as its checks require.
    assert any('The research says "' in ln for ln in P.ask_lines(_ctx(stage="Recruiter screen")))
    # Each part has a short name for its chip.
    assert all(p["short"] and len(p["short"]) <= 15 for p in _built()["parts"])


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
        d["parts"][0]["say"] = [{"t": " ".join(["and the forecast held up across the sites"] * 250) + ".",
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


# ------------------------------------------------------------------ every kind of interview, one sitting each

def _shaped(monkeypatch, stage, fmt="", consulting=False, **kw):
    """A prep built for one interview of the kind its own words say. The employer is the
    invented one of this file; `consulting` makes it read as a consulting firm."""
    if consulting:
        monkeypatch.setattr(P, "employer_type", lambda ctx: "consulting")
    ctx = _ctx(**kw)
    ctx["stage"], ctx["format"] = stage, fmt
    return L.build(ctx)


def _kinds(doc):
    return [p["kind"] for p in doc["parts"]]


@pytest.mark.parametrize("stage, fmt, consulting, shape, kinds", [
    ("Recruiter screen", "", False, "screen", ["opening", "motivation", "experience", "basics", "close"]),
    ("Hiring manager interview", "", False, "manager", ["opening", "experience", "behaviour", "motivation", "close"]),
    ("Technical interview", "SQL and statistics", False, "technical", ["opening", "technical", "probes", "close"]),
    ("Online assessment", "a timed numerical reasoning test", False, "assessment", ["format", "approach", "pacing", "practice"]),
    ("Second round", "case interview and personal experience interview", True, "case",
     ["opening", "personal", "case", "maths", "synthesis", "close"]),
    ("Case interview", "", False, "case_only", ["opening", "case", "maths", "synthesis", "close"]),
    ("Personal experience interview", "", True, "personal", ["opening", "personal", "close"]),
    ("Take-home review", "present back your analysis", False, "take_home", ["opening", "presenting", "technical", "close"]),
    ("Panel interview", "", False, "panel", ["opening", "experience", "behaviour", "technical", "motivation", "close"]),
    ("Final round", "", False, "final", ["opening", "motivation", "behaviour", "experience", "close"]),
])
def test_each_kind_of_interview_has_its_own_stages(monkeypatch, stage, fmt, consulting, shape, kinds):
    doc = _shaped(monkeypatch, stage, fmt, consulting)
    assert doc["shape"] == shape and _kinds(doc) == kinds, (doc["shape"], _kinds(doc))
    assert sum(p["minutes"] for p in doc["parts"]) <= doc["minutes"]
    assert not doc["assumed"], "the round's own words say what it is"


def test_a_technical_round_runs_warm_up_problem_probes_and_their_questions(monkeypatch):
    doc = _shaped(monkeypatch, "Technical interview, 45 minutes", "live SQL and Python")
    assert [p["title"] for p in doc["parts"]] == ["Warm-up, and your background", "A problem, worked aloud",
                                                  "The follow-up probes and trade-offs", "Your questions for them"]
    assert doc["minutes"] == 45 and sum(p["minutes"] for p in doc["parts"]) == 45
    # The problem worked aloud is the longest stop.
    assert max(doc["parts"], key=lambda p: p["minutes"])["kind"] == "technical"


def test_an_assessment_is_practised_not_talked_through(monkeypatch):
    doc = _shaped(monkeypatch, "Online assessment", "a timed problem-solving test, 70 minutes")
    assert doc["shape"] == "assessment" and doc["minutes"] == 70
    assert _kinds(doc) == ["format", "approach", "pacing", "practice"]
    # Nothing in it asks them about themselves: only items to practise, said by the test.
    practice = next(p for p in doc["parts"] if p["kind"] == "practice")
    assert all(q["part"] == practice["id"] and q["who"] == "test" for q in doc["questions"])
    assert not any("about yourself" in q["q"].lower() for q in doc["questions"])
    # How it works, how to take each item and the pacing are said even with no question in them.
    found = [w for w, _why in L.problems(doc)]
    for title in ("How the test works", "How to take each kind of item", "Pacing against the time"):
        assert any(title in w for w in found), title


def test_a_case_with_a_personal_experience_interview_is_one_sitting(monkeypatch):
    doc = _shaped(monkeypatch, "Second round", "personal experience interview, then a case", consulting=True)
    assert doc["shape"] == "case" and doc["shape_name"] == "A case interview with a personal experience interview"
    assert _kinds(doc) == ["opening", "personal", "case", "maths", "synthesis", "close"]
    assert sum(p["minutes"] for p in doc["parts"]) == doc["minutes"] == 60


def test_a_personal_story_and_live_coding_in_one_sitting_run_in_that_order(monkeypatch):
    # The maintainer's own round (2026-11-10): "personal story plus technical HackerRank
    # stuff, Python etc", at an invented consulting firm.
    doc = _shaped(monkeypatch, "Second round", "personal experience, technical coding (HackerRank, Python), 60 minutes",
                  consulting=True)
    assert doc["shape"] == "combined:personal+technical"
    assert doc["shape_name"] == "A personal experience interview and a technical interview in one sitting"
    assert _kinds(doc) == ["opening", "personal", "technical", "probes", "close"]
    assert sum(p["minutes"] for p in doc["parts"]) == 60 and not doc["assumed"]
    # The other order is the other sitting.
    other = _shaped(monkeypatch, "Second round", "live coding, then a personal experience interview", consulting=True)
    assert _kinds(other) == ["opening", "technical", "probes", "personal", "close"]


def test_a_skill_or_a_certificate_is_asked_where_the_work_is_tested_never_in_the_story(monkeypatch):
    # The maintainer's review of the HackerRank round (2026-11-10): "What is your experience with
    # SAP?" and a certificate question sat in "Your story", the one story told in depth.
    doc = _shaped(monkeypatch, "Second round", "personal experience, technical coding (HackerRank, Python), 60 minutes",
                  consulting=True)
    kind = {p["id"]: p["kind"] for p in doc["parts"]}
    skills = [q for q in doc["questions"] if L.kind_of(q["q"]) == "skill"]
    assert skills, [q["q"] for q in doc["questions"]]
    assert all(kind[q["part"]] == "technical" for q in skills), [(q["q"], kind[q["part"]]) for q in skills]
    for text in ("What is your experience with SAP?", "Do you hold the dbt certification?",
                 "How familiar are you with Power BI?", "Have you used Airflow?"):
        assert L._place(L.kind_of(text), _kinds(doc)) == "technical", text
    # With no technical part it is asked with the rest of the experience; only a personal
    # experience interview on its own leaves the story as the place for it.
    assert L._place("skill", ["opening", "experience", "behaviour", "motivation", "close"]) == "experience"
    assert L._place("skill", ["opening", "personal", "close"]) == "personal"


def test_a_requirement_reads_inside_a_sentence_and_a_name_keeps_its_capital():
    # "Tell me about your experience with Demand forecasting." (the maintainer's screen, 2026-11-10)
    seen = "Strong SQL and Python\nDemand forecasting for our network\nPower BI reporting"
    assert P.mid_sentence("Demand forecasting", seen) == "demand forecasting"
    assert P.mid_sentence("Stakeholder management", "") == "stakeholder management"
    # Written small elsewhere in what was read, so an ordinary word.
    assert P.mid_sentence("Inventory planning", "you will own inventory levels") == "inventory planning"
    for name in ("Python scripting", "Power BI reporting", "SQL", "Excel modelling", "Google Analytics"):
        assert P.mid_sentence(name, seen) == name
    questions = [q["q"] for q in L.build(_ctx())["questions"]]
    assert "Tell me about your experience with demand forecasting." in questions, questions
    assert not any(" with Demand " in q for q in questions), questions


def test_an_acronym_nobody_spelled_out_is_never_read_as_a_kind(monkeypatch):
    # "PSA" at a consulting firm: the closest kind is chosen and said to be assumed.
    doc = _shaped(monkeypatch, "PSA", "", consulting=True)
    assert doc["shape"] == "case" and doc["assumed"]
    # Said in so many words, the format decides it.
    said = _shaped(monkeypatch, "PSA", "a timed problem-solving test", consulting=True)
    assert said["shape"] == "assessment" and not said["assumed"]


def test_a_short_round_prepares_fewer_questions_than_a_long_one(monkeypatch):
    short = _shaped(monkeypatch, "Recruiter screen, 20 minutes")
    long = _shaped(monkeypatch, "Hiring manager interview, 60 minutes")
    assert short["minutes"] == 20 and len(short["questions"]) < len(long["questions"])


def test_the_line_to_end_a_part_on_is_kept_counted_and_checked(ready_doc):
    d = copy.deepcopy(ready_doc)
    d["parts"][0]["bridge"] = "Which is why the planning role here caught my eye."
    doc = L.merge(L.build(_ctx()), d)
    assert doc["parts"][0]["bridge"] == "Which is why the planning role here caught my eye."
    assert doc["timing"]["parts"][doc["parts"][0]["id"]]["words"] > L.finish(copy.deepcopy(ready_doc))["timing"]["parts"][doc["parts"][0]["id"]]["words"]
    got = _one(ready_doc, lambda x: x["parts"][0].update(bridge="As we discussed, the planning role."))
    assert any("assumes you have spoken before" in w for w in got)


def test_one_phrase_opens_one_term(ready_doc):
    def two(d):
        d["terms"]["demand-forecast"]["match"] = ["forecast"]
        d["terms"]["volume-forecast"] = dict(d["terms"]["demand-forecast"], name="Volume forecast", match=["forecast"])
    assert any("one phrase for one term" in w for w in _one(ready_doc, two))


def test_words_explained_for_one_role_at_an_employer_start_the_next(tmp_path):
    ctx = _ctx()
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found
    other = dict(ctx, folder=os.path.join(os.path.dirname(ctx["folder"]), os.path.basename(ctx["folder"]) + "_Other_Role"))
    os.makedirs(other["folder"])
    assert "demand-forecast" in L.build(other)["terms"]


# ------------------------------------------------------------------ words a person can say aloud

@pytest.mark.parametrize("text, refused", [
    ("Their care history. Their frailty. Then the rest of it came together over the following weeks.", True),
    ("They were wary at first. Seeing the error by site won them over.", True),
    ("I rebuilt the weekly forecast in Python and SQL, with promotions and seasonality in it, and "
     "error came down from 22% to 14%. That released about £1.1M of safety stock.", False),
    ("I owned the model and the error tracking by site.", False),
])
def test_clipped_fragments_are_not_flowing_sentences(text, refused):
    assert L.choppy(text) is refused


def test_an_answer_or_a_beat_written_as_fragments_is_refused(ready_doc):
    def clip_answer(d):
        d["questions"][0]["simple"] = "I rebuilt it. Error fell. The planners released about £1.1M of safety stock afterwards."
    got = _one(ready_doc, clip_answer)
    assert any("write this as flowing sentences, joined with commas and \"and\"" in w for w in got), got

    def clip_beat(d):
        d["parts"][0]["say"][0]["t"] = "Thanks for the time. Glad to be here. The planning work is why."
    assert any("flowing sentences" in w for w in _one(ready_doc, clip_beat))
    # The basics are short on purpose, and a question to ask them is a question.
    assert not any("flowing sentences" in w for w in _one(ready_doc, lambda d: None))


def test_every_part_has_something_to_say_first(ready_doc):
    got = _one(ready_doc, lambda d: d["parts"][1].update(say=[]))
    assert any("nothing to say first yet" in w for w in got)


def test_a_known_question_is_marked_on_a_beat_by_its_words(ready_doc):
    d = copy.deepcopy(ready_doc)
    text = "How do you get depot managers to trust a forecast?"
    d["known"] = [{"text": text, "from": "the recruiter"}]
    d["questions"].append({"id": "mine", "part": d["parts"][1]["id"], "who": "manager", "q": text, "also": [],
                           "simple": d["questions"][0]["simple"], "detailed": d["questions"][0]["detailed"], "follow": []})
    d["parts"][1]["say"].append({"t": "Trust usually comes up first with a forecast, so I will take it head on.",
                                 "prompts": ["mine"], "known": text})
    doc = L.merge(L.build(_ctx()), d)
    k = doc["known"][-1]
    beat = doc["parts"][1]["say"][-1]
    assert beat["known"] == k["id"] and beat["prompts"] == [k["question"]]
    assert not any("known to ask" in w for _where, w in L.problems(doc, _ctx()))


# ------------------------------------------------------------------ the words invites and recruiters use

def _round(monkeypatch, stage, fmt="", consulting=False):
    """A prep built the way the command builds it, from the round's name and its format."""
    if consulting:
        monkeypatch.setattr(P, "employer_type", lambda ctx: "consulting")
    return L.build(_ctx(stage=stage, format_=fmt))


# (stage, format, consulting, shape, a guess?) from the review of 2026-11-10 and the words
# recruiters and calendar invites really use. A round whose words do not say its kind is a
# guess, and says so; one whose words do is never one.
@pytest.mark.parametrize("stage, fmt, consulting, shape, guess", [
    ("Second round", "", False, "manager", True),
    ("Second interview", "", False, "manager", True),
    ("Interview 2", "", False, "manager", True),
    ("Stage 2", "", False, "manager", True),
    ("Second round", "", True, "case", True),
    ("Second round", "PEI and a HackerRank Python exercise, 60 mins", True, "combined:personal+technical", False),
    ("Second round", "PEI and a HackerRank Python exercise, 60 mins", False, "combined:personal+technical", False),
    ("Online assessment", "HackerRank, 90 minutes", False, "assessment", False),
    ("OA", "CodeSignal, 70 minutes", False, "assessment", False),
    ("Coding challenge", "CodeSignal", False, "assessment", False),
    ("Second round", "HackerRank", False, "assessment", True),
    ("Technical screen", "", False, "tech_screen", False),
    ("Phone screen", "SQL and Python questions", False, "tech_screen", False),
    ("Case and PEI", "", False, "combined:case+personal", False),
    ("Second round", "case interview and PEI", True, "case", False),
    ("Technical interview, then a PEI", "", True, "combined:technical+personal", False),
    ("Technical interview/PSA", "", True, "technical", False),
    ("Behavioural interview", "", False, "behavioural", False),
    ("Behavioural interview", "", True, "behavioural", False),
    ("Values interview", "", False, "behavioural", False),
    ("Superday", "", False, "superday", False),
    ("Virtual onsite", "", False, "superday", False),
    ("Assessment centre", "", False, "superday", False),
    ("Onsite", "coding, system design and behavioural", False, "day:technical+behaviour", False),
    ("Final round", "onsite with the hiring manager, 60 minutes", False, "final", False),
    ("Video interview", "recorded, HireVue", False, "recorded", False),
    ("Final round", "", False, "final", False),
    ("Final round", "", True, "case", True),
    ("Partner round", "", True, "case", True),
    ("Panel", "", False, "panel", False),
    ("Recruiter screen", "", False, "screen", False),
    ("Hiring manager interview", "", False, "manager", False),
    ("Take-home presentation", "", False, "take_home", False),
    # The review of the fixes (2026-11-10): the format given decides whether anyone is in the
    # room, whatever the stage's label says; a test is a test; a day is a day however its
    # interviews are counted; "onsite" says where, not what.
    ("Technical interview", "CodeSignal General Coding Assessment, 70 minutes", False, "assessment", False),
    ("Technical interview", "HackerRank online assessment, 90 minutes", False, "assessment", False),
    ("Second interview", "online test", False, "assessment", False),
    ("Interview 2", "OA", False, "assessment", False),
    ("Stage 2 interview", "OA", False, "assessment", False),
    ("Second round", "technical test", False, "assessment", True),
    ("Second round", "Python test", False, "assessment", True),
    ("Second round", "SQL test, 45 minutes", False, "assessment", True),
    ("Assessment day", "", False, "superday", False),
    ("Final round", "4 x 45 min", False, "superday", False),
    ("Final round", "three 45-minute interviews", False, "superday", False),
    ("Onsite", "60 minutes with the hiring manager", False, "manager", False),
])
def test_the_words_recruiters_and_invites_use_are_read_as_the_round_they_name(
        monkeypatch, stage, fmt, consulting, shape, guess):
    doc = _round(monkeypatch, stage, fmt, consulting)
    assert doc["shape"] == shape, (stage, fmt, doc["shape"], doc["assumed"])
    assert bool(doc["assumed"]) is guess, (stage, fmt, doc["assumed"])
    # The parts take the round's minutes, no more and no fewer.
    assert sum(p["minutes"] for p in doc["parts"]) == doc["minutes"], (stage, doc["minutes"])
    # Every question sits in a part of this round.
    ids = {p["id"] for p in doc["parts"]}
    assert all(q["part"] in ids for q in doc["questions"])


def test_a_test_taken_alone_has_no_hello_and_no_questions_for_them(monkeypatch):
    # "Online assessment" with "HackerRank, 90 minutes" was a live interview with a warm-up and
    # "Your questions for them", for a test with nobody in the room (the review, 2026-11-10).
    doc = _round(monkeypatch, "Online assessment", "HackerRank, 90 minutes")
    assert _kinds(doc) == ["format", "approach", "pacing", "practice"] and doc["minutes"] == 90
    assert all(q["who"] == "test" for q in doc["questions"])
    assert not doc["ask"], "nobody is there to ask"
    # A recorded video interview has nobody to ask either, and its questions are recorded ones.
    rec = _round(monkeypatch, "Video interview", "recorded, HireVue")
    assert "close" not in _kinds(rec) and not rec["ask"]
    assert {q["who"] for q in rec["questions"]} == {"recorded"} and "recorded" in L.PERSONAS


def test_several_interviews_back_to_back_are_timed_as_the_day(monkeypatch):
    day = _round(monkeypatch, "Onsite", "4 interviews, 45 minutes each: coding, system design and behavioural")
    assert day["shape"] == "day:technical+behaviour" and day["minutes"] == 180
    assert day["shape_name"].startswith("Several interviews back to back")
    assert _kinds(day)[0] == "opening" and _kinds(day)[-1] == "close"
    assert sum(p["minutes"] for p in day["parts"]) == 180
    assert _round(monkeypatch, "Final round", "technical and behavioural, 2 hours")["minutes"] == 120
    assert _round(monkeypatch, "Superday", "")["minutes"] == 180
    # A technical screen is a shorter technical round.
    assert _round(monkeypatch, "Technical screen", "")["minutes"] == 45


@pytest.mark.parametrize("requirement, question", [
    # The review of 2026-11-10: each read "Tell me about your experience with <the line>".
    ("Familiarity with dbt", "Tell me about your experience with dbt."),
    ("Proficiency in SQL", "Tell me about your experience with SQL."),
    ("Experience building dashboards", "Tell me about your experience building dashboards."),
    ("Excellent communication skills", "Give me an example of your communication skills at work."),
    ("Inventory optimization", "Tell me about your experience with inventory optimization."),
    ("Strong stakeholder management", "Tell me about your experience with stakeholder management."),
    ("5+ years of experience in analytics", "Tell me about your experience with analytics."),
    ("Ability to work under pressure", "Tell me about a time you had to work under pressure."),
    ("Solid knowledge of Python and SQL", "Tell me about your experience with Python and SQL."),
    ("Demand forecasting", "Tell me about your experience with demand forecasting."),
    ("Power BI reporting", "Tell me about your experience with Power BI reporting."),
    ("SQL experience", "Tell me about your experience with SQL."),
    ("Proven track record of delivering models", "Tell me about your experience delivering models."),
    ("A degree in statistics", "How has what you studied helped in your work?"),
    # The review of the fixes (2026-11-10): a trait, a qualifier, a degree said another way and
    # a line written to "you" still read badly. "" is a line no interviewer asks about.
    ("A passion for data", "What draws you to data?"),
    ("Comfortable with ambiguity", "Tell me about a time you dealt with ambiguity."),
    ("Self-starter", ""),
    ("Fluent in English", ""),
    ("Docker and Kubernetes is a plus", "Tell me about your experience with Docker and Kubernetes."),
    ("Experience with financial services is desirable", "Tell me about your experience with financial services."),
    ("Masters or PhD in Computer Science or a related field", "How has what you studied helped in your work?"),
    ("You have shipped production code.", "When have you shipped production code?"),
    ("You will own the weekly forecast", ""),
])
def test_a_line_of_the_posting_reads_as_a_question_a_person_would_ask(requirement, question):
    assert P.requirement_question(requirement, "") == question
    if question.startswith("What draws you"):
        assert L.kind_of(question) == "motivation"


def test_a_credential_is_asked_as_whether_you_hold_it_never_your_experience_with_it():
    # "What is your experience with Chartered procurement?" was in the real example prep, in the
    # live coding part. The posting says "CIPS membership is required".
    ctx = _ctx()
    qs = [q["question"] for q in P.likely_questions(ctx)]
    assert "Are you a member of CIPS?" in qs, qs
    assert not any("Chartered procurement" in q for q in qs), qs
    assert L.kind_of("Are you a member of CIPS?") == "skill"
    # A skill the profile does not hold is still asked as experience, its name as written, though
    # the same sentence of the posting asks for a membership too.
    assert "What is your experience with SAP?" in qs and not any("member of SAP" in q for q in qs), qs
    for q in L.build(ctx)["questions"]:
        assert not P.re.search(r"experience with (?:experience|familiarity|proficiency|knowledge|"
                                r"excellent|strong)\b", q["q"], P.re.I), q["q"]


def test_the_notes_for_you_read_as_sentences_and_say_each_gap_once():
    # The review of 2026-11-10: "...ending a daily two-hour reconciliation Name the work that is
    # the same job...", "Never claim Chartered procurement: A credential, not a skill. Do not
    # claim it. Ask Claude for an example and it drafts one for you to check.", and the same gap
    # again as a bullet of its own.
    ctx = _ctx()
    ctx["role"] = "Demand Planning Scientist"
    priv = L.private_notes(ctx)
    titled = next(w for w in priv["weaknesses"] if w["what"].startswith("Your title says"))
    assert not P.re.search(r"[a-z0-9] (?:Name|Say|From) ", titled["frame"]), titled["frame"]
    assert titled["frame"].startswith("Name the work that is the same job"), titled["frame"]
    # Each gap once: the credential is a note of its own, never also a line of what not to say.
    # A qualification is named in the posting's own words ("CIPS membership"), not the label
    # the profile's map files it under.
    gaps = [w for w in priv["weaknesses"] if "CIPS" in w["what"] or "Chartered procurement" in w["what"]]
    assert len(gaps) == 1 and gaps[0]["what"] == "CIPS membership", priv["weaknesses"]
    assert not any("Chartered procurement" in x for x in priv["not_to_say"]), priv["not_to_say"]
    assert "never claim" in gaps[0]["frame"].lower() and "example" not in gaps[0]["frame"]
    # In the pack, a credential is never claimed, said once, with no example offered for it.
    line = next(x for x in P.do_not_say(ctx, never_say=[]) if "Chartered procurement" in x)
    assert line.lower().count("claim") == 1 and "Ask Claude for an example" not in line, line


def _words(doc):
    """Only the words Claude writes, keyed by part and question, as `live --fill` takes them."""
    d = _fill(doc)
    return {"parts": {p["id"]: {"say": p["say"], "follow": p.get("follow") or []} for p in d["parts"]},
            "questions": {q["id"]: {k: q[k] for k in ("simple", "detailed", "follow")} for q in d["questions"]},
            "ask": {a["id"]: a["follow"] for a in d["ask"]},
            "terms": d["terms"]}


def test_the_fill_is_only_the_words_and_code_puts_them_in(tmp_path):
    # The efficiency audit, 2026-11-10: Claude re-wrote the whole built file to fill it, 37k
    # characters of which about 20k were what the engine had already written.
    out = tmp_path / "live.json"
    run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), *a],
                                    capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))
    assert run("live", COMPANY, "--role", ROLE, "--out", str(out)).returncode == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    words = _words(doc)
    full = json.dumps(_fill(doc))
    assert len(json.dumps(words)) < 0.75 * len(full)
    wf = tmp_path / "words.json"
    # A question can be named by its words as well as its id; a new one names its part by kind.
    first = doc["questions"][0]
    words["questions"][first["q"]] = words["questions"].pop(first["id"])
    kind = doc["parts"][1]["kind"]
    words["new"] = [{"part": kind, "who": "manager", "q": "What would you change with more data?",
                     "simple": "I'd add the promotions calendar as its own input, and test it against the last "
                               "quarter before trusting it. Then I'd ask the planners which lines matter most.",
                     "detailed": "I'd add the promotions calendar as its own input, and test it against the last "
                                 "quarter before trusting it, because that is where the error was largest. Then "
                                 "I'd ask the planners which lines matter most, so the work goes where it pays.",
                     "follow": []}]
    wf.write_text(json.dumps(words), encoding="utf-8")
    ok = run("live", COMPANY, "--role", ROLE, "--fill", str(wf), "--write")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    kept = L.load(_ctx()["folder"])
    assert kept and kept["questions"][0]["simple"] == _fill(doc)["questions"][0]["simple"]
    added = next(q for q in kept["questions"] if q["q"] == "What would you change with more data?")
    assert next(p for p in kept["parts"] if p["id"] == added["part"])["kind"] == kind
    assert all(p["say"] for p in kept["parts"]) and kept["terms"]["demand-forecast"]["name"] == "Demand forecast"
    # A later fill of a few words changes those and keeps the rest.
    later = tmp_path / "later.json"
    later.write_text(json.dumps({"parts": {"opening": {"bridge": "Which is why this role caught my eye."}}}),
                     encoding="utf-8")
    assert run("live", COMPANY, "--role", ROLE, "--fill", str(later), "--write").returncode == 0
    again = L.load(_ctx()["folder"])
    assert again["parts"][0]["bridge"] == "Which is why this role caught my eye."
    assert again["questions"][0]["simple"] == kept["questions"][0]["simple"]


def test_saying_plainly_you_do_not_hold_it_is_never_refused_as_a_claim(ready_doc):
    # "No, I'm not a member of CIPS" was refused as naming a skill the profile does not hold, so
    # the only way through was to talk round it ("the chartered procurement institute").
    def say(text):
        return lambda d: d["questions"][0].update(simple=text, detailed="")
    honest = ("No, I'm not a member of CIPS, and I'd rather say that plainly. My route into planning "
              "has been through the data, rather than through procurement.")
    assert not any("CIPS" in w for w in _one(ready_doc, say(honest)))
    claimed = ("Yes, I'm a member of CIPS, and it shapes how I plan. My route into planning has been "
               "through the data as well as procurement.")
    assert any("CIPS" in w for w in _one(ready_doc, say(claimed)))
    # The negation has to govern the name, not sit anywhere in the sentence (the review of the
    # fixes, 2026-11-10): "no doubt" after a claim made it pass.
    sly = ("I hold CIPS membership, and I have no doubt it helps when I talk to buyers. My route into "
           "planning has been through the data as well.")
    assert any("CIPS" in w for w in _one(ready_doc, say(sly)))
    for honest in ("I don't hold CIPS membership, and I'd rather say so plainly. My route into planning "
                   "has been through the data instead.",
                   "I have never been a member of CIPS, and I'd rather say so plainly. My route into "
                   "planning has been through the data instead."):
        assert not any("CIPS" in w for w in _one(ready_doc, say(honest))), honest


def test_a_question_to_ask_them_fits_any_role():
    # "Is there room to grow into more architectural or strategic decisions?" was asked by a
    # demand planning analyst: the guide's own question was a software engineer's.
    asks = [a["q"] for a in L.build(_ctx(stage="Second round"))["ask"]]
    assert not any("architectural" in q for q in asks), asks
    assert "Is there room to grow into bigger, more strategic decisions?" in asks, asks


def test_a_simple_answer_is_short_lines_to_glance_at(ready_doc):
    # The UX review of 2026-11-10 (U-5): simple answers ran to sentences of 30 to 44 words, which
    # cannot be taken in at a glance mid-interview. Each sentence of a simple answer is a line of
    # its own on the page, and a long one is refused; the detailed answer stays prose.
    long = ("I rebuilt the weekly forecast in Python and SQL with promotions and seasonality as features "
            "and tracked the error by distribution centre every week so the planners could see where it "
            "held and where it did not hold. Error came down from 22% to 14% across 2,400 SKUs.")
    got = _one(ready_doc, lambda d: d["questions"][0].update(simple=long))
    assert any("shorter sentences" in w for w in got), got
    assert not any("shorter sentences" in w for w in _one(ready_doc, lambda d: None))


def test_the_changelog_promises_only_what_the_live_prep_does():
    # The review of 2026-11-10 (R1-5): the release notes promised a bar that stays at the top,
    # pay and notice at the top, and Hide the answers behind Start with a timer, none of which
    # the page has, and a second entry described the same prep differently.
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    # The section that carries the live prep's entry: [Unreleased] until it ships, then its
    # release's (4.15.0), which the release's rename leaves [Unreleased] empty above.
    sections = ["## [" + part for part in text.split("\n## [")[1:]]
    unreleased = next(sec for sec in sections if "- **Your interview prep" in sec)
    added = unreleased.split("### Added", 1)[1]
    for gone in ("stays in reach however far down", "pay and notice lines are at the top", "behind Start",
                 "small timer", "one calm page"):
        assert gone not in unreleased, gone
    entries = [ln for ln in added.splitlines() if ln.startswith("- **Your interview prep")]
    assert len(entries) == 1, entries
    for said in ("At a glance", "Hidden", "Not this kind of interview?", "a test you take alone"):
        assert said in entries[0], said


def test_a_question_to_ask_them_reads_as_said_with_no_slash():
    # "What does the development/project lifecycle look like, from idea to production?" was
    # offered in a real round's prep (2026-11-10): a slash is written, never said.
    import interview_pack
    cats = interview_pack._guide_categories()
    for q in [q for qs in cats.values() for q in qs if "[" not in q]:
        assert "/" not in q, q


# The parts a person answers questions in; the rest Claude fills with the problem, the case or
# the items to practise.
_ASKED = {"opening", "motivation", "basics", "experience", "behaviour", "technical", "probes",
          "personal", "presenting"}


@pytest.mark.parametrize("stage, fmt, consulting", [
    ("Recruiter screen", "", False), ("Second round", "", False), ("Technical screen", "", False),
    ("Behavioural interview", "", False), ("Video interview", "recorded, HireVue", False),
    ("Superday", "", False), ("Final round", "", False), ("Panel", "", False),
    ("Take-home presentation", "", False), ("Case interview", "", False),
    ("Second round", "PEI and a HackerRank Python exercise", True),
    ("Onsite", "coding, system design and behavioural", False),
])
def test_every_part_a_person_answers_in_has_its_questions_and_each_is_asked_where_it_belongs(
        monkeypatch, stage, fmt, consulting):
    # A manager interview's "Times you did it" and "Why this role" were empty while six questions
    # sat in "Your work"; a technical screen put pay, notice and sponsorship in its warm-up; a
    # take-home's "What did you leave out?" sat in the hello; a case asked "What is your
    # experience with SAP?" as the case (2026-11-10).
    doc = _round(monkeypatch, stage, fmt, consulting)
    kind = {p["id"]: p["kind"] for p in doc["parts"]}
    for p in doc["parts"]:
        if p["kind"] in _ASKED:
            assert p["questions"], (stage, p["kind"], [(q["q"], kind[q["part"]]) for q in doc["questions"]])
    for q in doc["questions"]:
        k = kind[q["part"]]
        if L.kind_of(q["q"]) == "basics" and "basics" in kind.values():
            assert k == "basics", (stage, q["q"], k)
        assert k not in ("case", "maths", "synthesis"), (stage, q["q"], k)
        if "leave out" in q["q"]:
            assert k == "presenting", (stage, q["q"], k)
    opening = next(p for p in doc["parts"] if p["kind"] == "opening")
    assert len(opening["questions"]) <= 2, (stage, [q["q"] for q in doc["questions"] if q["part"] == opening["id"]])


def test_a_test_taken_alone_practises_no_interview_questions(monkeypatch):
    doc = _round(monkeypatch, "Online assessment", "HackerRank, 90 minutes")
    assert not any("experience" in q["q"].lower() or "member of" in q["q"].lower() for q in doc["questions"]), \
        [q["q"] for q in doc["questions"]]


def test_a_test_taken_alone_is_not_kept_without_items_to_practise(monkeypatch):
    # A test taken alone has no questions from the records (2026-11-10): its items to practise
    # are Claude's to write, and a prep with none is not kept, as the page would have nothing
    # to practise from.
    doc = _fill(_round(monkeypatch, "Online assessment", "HackerRank, 90 minutes"))
    assert not doc["questions"]
    found = [w for _where, w in L.problems(L.finish(doc), _ctx())]
    assert any("items to practise" in w for w in found), found



def test_a_day_counted_any_way_is_timed_as_the_day_and_a_question_count_is_kept(monkeypatch):
    assert _round(monkeypatch, "Final round", "4 x 45 min")["minutes"] == 180
    assert _round(monkeypatch, "Final round", "three 45-minute interviews")["minutes"] == 135
    # "HireVue, 5 questions" prepared 7: the count the invite gives is the count prepared.
    rec = _round(monkeypatch, "Video interview", "HireVue, 5 questions")
    assert rec["shape"] == "recorded" and len(rec["questions"]) == 5, [q["q"] for q in rec["questions"]]


def test_a_words_file_of_the_wrong_shape_or_a_reused_id_is_refused_in_plain_words(tmp_path):
    # The review of the fixes (2026-11-10): parts as a list with questions keyed, or a bare list,
    # crashed with a traceback; a new question given an id already a question's ("q3") quietly
    # repointed other parts' "Likely to prompt" links.
    out = tmp_path / "live.json"
    run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), *a],
                                    capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))
    assert run("live", COMPANY, "--role", ROLE, "--out", str(out)).returncode == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    bad = tmp_path / "bad.json"
    for shape in ({"parts": [{"say": []}], "questions": {}}, [{"q": "x"}], {"questions": [1, 2]},
                  {"parts": {doc["parts"][0]["id"]: "words"}}):
        bad.write_text(json.dumps(shape), encoding="utf-8")
        got = run("live", COMPANY, "--role", ROLE, "--fill", str(bad), "--write")
        assert got.returncode == 1 and "Traceback" not in got.stderr, (shape, got.stderr[-400:])
        assert "words" in got.stderr, got.stderr
    taken = doc["questions"][2]["id"]
    bad.write_text(json.dumps({"new": [{"id": taken, "part": doc["parts"][1]["id"], "who": "manager",
                                        "q": "What would you change?", "simple": "x"}]}), encoding="utf-8")
    got = run("live", COMPANY, "--role", ROLE, "--fill", str(bad), "--write")
    assert got.returncode == 1 and taken in got.stderr and "Traceback" not in got.stderr, got.stderr[-400:]


def test_a_question_to_ask_them_is_never_refused_as_a_figure(ready_doc):
    # The night-before run (2026-11-10): "what a good first six months looks like", leading into
    # a question to ask them, was refused as a number the profile does not hold. A time ahead,
    # or a question, is not a claim about the person's work.
    def close_beat(text):
        def change(d):
            next(p for p in d["parts"] if p["kind"] == "close")["say"][0]["t"] = text
        return change
    for text in ("Then my question on what a good first six months looks like here, and how the team would judge it.",
                 "Then my question, what does the team expect in the first 90 days here?"):
        got = _one(ready_doc, close_beat(text))
        assert not any("number your profile does not hold" in w for w in got), (text, got)
    # A figure claimed as the person's own is still refused.
    got = _one(ready_doc, close_beat("Before we finish, it's worth saying that I cut forecast error by 61% at my last job."))
    assert any("number your profile does not hold" in w for w in got), got


def test_a_question_said_another_way_finds_the_story_tagged_for_it():
    # The night-before run (2026-11-10): the story tagged "Tell me about a time you took
    # initiative" was not matched to "Tell me about a time you took something on without being
    # asked", so the answer was written with no story behind it.
    q = "Tell me about a time you took something on without being asked."
    story, _score = P.best_story(P._match_text(q), P.stories())
    assert story and story["title"] == "Ending a daily reconciliation", story
    doc = L.build(_ctx(stage="Behavioural interview"))
    got = next((x for x in doc["questions"] if x["q"] == q), None)
    titles = {s["id"]: s["title"] for s in doc["stories"]}
    assert got and titles.get(got["story"]) == "Ending a daily reconciliation", got


def test_the_problem_as_set_leads_its_part_and_a_follow_up_is_asked_once(monkeypatch):
    # The night-before run (2026-11-10): in the personal experience and coding sitting, "A
    # problem, worked aloud" led with "Walk me through some code you're proud of" and a hard bug,
    # the problem itself last; and "What would you do differently now?" was a coding probe and a
    # follow-up under three stories at once.
    doc = _round(monkeypatch, "Second round", "PEI and a HackerRank Python exercise", True)
    asked = [q["q"] for q in doc["questions"]]
    follows = {f["q"] for q in doc["questions"] for f in q["follow"]} | {f["q"] for p in doc["parts"] for f in p["follow"]}
    assert not [q for q in asked if q in follows], [q for q in asked if q in follows]
    tech = next(p for p in doc["parts"] if p["kind"] == "technical")
    # Not kept until the part has the problem they are likely to set.
    bare = _fill(doc)
    bare["questions"] = [q for q in bare["questions"] if not q["id"].startswith("problem")]
    found = [w for where, w in L.problems(L.finish(bare), _ctx()) if tech["title"] in where]
    assert any("the problem they are likely to set" in w for w in found), found
    # Added last, as Claude adds it, it leads its part.
    d = L.finish(_fill(doc))
    tech = next(p for p in d["parts"] if p["kind"] == "technical")
    first = next(q for q in d["questions"] if q["id"] == tech["questions"][0])
    assert first["q"].startswith("Given weekly demand") and len(tech["questions"]) > 1, tech["questions"]
    assert not any("the problem they are likely to set" in w for _where, w in L.problems(d, _ctx()))
