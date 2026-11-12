"""A live prep is written for the call itself: the points to glance at, the script to read
aloud, the follow-ups three deep, and every hard word explained on the spot.

The maintainer, 2026-11-11: Simple and Detailed were nearly the same answer twice, so neither
helped mid-call; follow-ups stopped a level short; and words a data scientist would know, and
the employer's own, went unexplained. An answer written the live way (its points a list) is
now held to it: three to five points of ten words at most that never copy the script, the
same numbers in both, a script in the person's own spoken voice that opens on the point,
follow-ups two or three, then three, then two,
at least one line of them three deep, a coding part with its steps, and a term for every hard
word with plain words, what it means here and an everyday likeness. A prep written before,
its answers one string, is held to the rules it was written for. Each check is run on the
real prep the page draws (`interview_live_filled.json`, built and merged the way `live
--fill` keeps it), broken one way at a time. Every person, employer and word is invented.

The maintainer, 2026-11-12, on a real prep: "all the content could be better". Every script
had to end on a sentence sharing words with the first follow-up and the last point had to lead
into it, so unrelated answers ended on lines added only to name it; points could not share five words in a row with the script yet had to share most of
its words, so they came out as pieces cut from its sentences ("Every new forecast gets"); and
no two points could start alike. The page offers the follow-ups as choices, so an answer no
longer sets one up and points may start alike. A point may share three words in a row with
the script, never four, may sum it up in words of its own, and reads as a whole phrase, never
stopping on a word like "gets", "under", "so" or "the".
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_live as L  # noqa: E402
import person  # noqa: E402
from test_a_beginner_is_told_in_plain_words import _plain  # noqa: E402
from test_interview_pack import _ctx, app  # noqa: E402,F401
from test_the_live_prep_on_the_page import REAL, _real_ctx  # noqa: E402

pytestmark = pytest.mark.usefixtures("app")


@pytest.fixture
def kept():
    """The real prep as `live --fill` keeps it: built from the records, the words merged in."""
    ctx = _real_ctx()
    with open(REAL, encoding="utf-8") as fh:
        doc = L.merge(L.build(ctx), json.load(fh))
    assert L.problems(doc, ctx) == [], L.problems(doc, ctx)
    return doc, ctx


def _q(doc, qid="q13"):
    return next(q for q in doc["questions"] if q["id"] == qid)


def _part(doc, pid="p3"):
    return next(p for p in doc["parts"] if p["id"] == pid)


def _broken(kept, change):
    doc, ctx = kept
    d = copy.deepcopy(doc)
    change(d)
    got = [w for _where, w in L.problems(L.finish(d), ctx)]
    for w in got:
        _plain(w)
    return got


def _has(got, *bits):
    assert any(all(b in w for b in bits) for w in got), got


# ------------------------------------------------------------------ the real prep

def test_the_real_prep_is_written_the_live_way_and_passes(kept):
    doc, _ctx_ = kept
    q = _q(doc)
    assert isinstance(q["simple"], list) and 3 <= len(q["simple"]) <= 5
    assert L.live_way(doc)
    depths = [d for _f, d, _w in L._nodes(q)]
    assert max(depths) == L.MAX_DEPTH, "one line of follow-ups goes three deep"
    assert all(L._t(t.get("like")) for t in doc["terms"].values()), "every term has a likeness"
    assert _part(doc)["steps"] and _part(doc)["code"], "the coding part keeps its steps and code"


# ------------------------------------------------------------------ the points

def test_too_few_or_too_many_points_are_refused(kept):
    _has(_broken(kept, lambda d: _q(d).update(simple=_q(d)["simple"][:2])), "2 points", "3 to 5")
    _has(_broken(kept, lambda d: _q(d)["follow"][0].update(simple=["Hand-checkable cases first"])),
         "1 point", "2 to 4")


def test_a_point_is_short_with_no_full_stop(kept):
    long = "Return the SKUs with forecast error over the threshold they set"
    _has(_broken(kept, lambda d: _q(d)["simple"].__setitem__(0, long)), "runs to 11 words")
    _has(_broken(kept, lambda d: _q(d)["simple"].__setitem__(1, "Say it back: error as share of actual.")),
         "ends with a full stop")


def test_two_points_may_start_alike(kept):
    # A rule of 2026-11-11 the maintainer took out on 2026-11-12: points made to start each its
    # own way came out re-worded oddly, and the eye finds them by their place on the page.
    assert _broken(kept, lambda d: _q(d)["simple"].__setitem__(2, "Say: missing weeks, share or units")) == []


def test_a_point_lifted_from_the_script_is_refused(kept):
    _has(_broken(kept, lambda d: _q(d)["simple"].__setitem__(3, "skips any SKU with no actual demand")),
         "the point \"skips any SKU with no actual demand\" copies the script", "three in a row")
    # Three words in a row from the script are a point's own, never a copy.
    assert _broken(kept, lambda d: _q(d)["simple"].__setitem__(3, "A plain loop, no actual demand skipped")) == []


@pytest.mark.parametrize("point, stop", [
    ("All the hand-worked tests it gets", "gets"),
    ("Used under, the threshold they set", "under"),
    ("Plain loop first, and so", "so"),
    ("Skip zero demand, then the", "the"),
])
def test_a_point_that_stops_mid_phrase_is_refused(kept, point, stop):
    # Points cut from the script's sentences stopped on a word that needs more after it (a real
    # prep, 2026-11-12, here invented: "Every new forecast gets", "Used under, the depot's sign-off rules").
    _has(_broken(kept, lambda d: _q(d)["simple"].__setitem__(3, point)), "stops on \"%s\"" % stop,
         "a whole phrase")


def test_a_point_ending_on_a_word_a_phrase_ends_on_naturally_passes():
    assert L.dangles("The teams I worked with") == ""
    assert L.dangles("Where the risk is") == ""
    assert L.dangles("Every new forecast gets") == "gets"
    assert L.dangles("Used under, the depot's sign-off rules") == "under"


def test_the_points_and_the_script_hold_the_same_numbers(kept):
    _has(_broken(kept, lambda d: _q(d)["simple"].__setitem__(2, "Ask: 2,400 lines, share or units")),
         "different numbers")


def test_a_point_may_sum_the_script_up_in_words_of_its_own(kept):
    # A rule of 2026-11-11 the maintainer took out on 2026-11-12: points made to share most of
    # the script's words, never five in a row, came out as pieces of its sentences. A point is
    # the idea in a few words; the numbers check and the profile's still hold it to the facts.
    assert _broken(kept, lambda d: _q(d)["simple"].__setitem__(3, "Simple version before anything clever")) == []


def test_the_last_point_need_not_lead_into_the_first_follow_up(kept):
    # A rule of 2026-11-11 the maintainer took out on 2026-11-12: the page offers the follow-ups
    # as choices, so the last point no longer has to set one up.
    assert _broken(kept, lambda d: _q(d)["simple"].__setitem__(4, "Hand over once it all looks right")) == []


# ------------------------------------------------------------------ the script

def test_a_script_too_short_or_too_long_is_refused(kept):
    _has(_broken(kept, lambda d: _q(d).update(detailed="So I'd return every SKU whose forecast error "
                                                       "is over the threshold, and I'd test it by hand.")),
         "the script is", "80 to 200")
    _has(_broken(kept, lambda d: _q(d).update(detailed=(_q(d)["detailed"] + " ") * 3)), "80 to 200")


def test_a_script_must_sound_said_not_written(kept):
    def formal(d):
        q = _q(d)
        q["detailed"] = (q["detailed"].replace("I'd", "I would").replace("I'll", "I will")
                         .replace("that's", "that is").replace("it's", "it is"))
    _has(_broken(kept, formal), "reads as written, not said")
    _has(_broken(kept, lambda d: _q(d).update(detailed=_q(d)["detailed"].replace(
        "Before I type", "Furthermore, before I type"))), "\"furthermore\" is a written word")


def test_a_script_opens_on_the_point(kept):
    _has(_broken(kept, lambda d: _q(d).update(detailed="Well, that's a good one to start with. "
                                                       + _q(d)["detailed"])),
         "does not open on the point")


def test_a_script_ends_where_the_answer_ends_and_sets_up_no_follow_up(kept):
    # A rule of 2026-11-11 the maintainer took out on 2026-11-12: every script had to end on a
    # sentence sharing words with the first follow-up, and a real prep ended unrelated answers
    # on lines added only for that (here invented: "That's why the routing tool matters to me,
    # and how it ties to my work is easy to explain"). An answer that
    # ends on its own last point passes, with no hook to "How would you test it?".
    def plain_end(d):
        q = _q(d)
        q["detailed"] = q["detailed"].replace(
            " And I'd want a few small tests I can work out by hand, so we both trust what it flags.",
            " Then I'd hand it over with a short note on what it skips and why, so nobody's "
            "surprised later.")
        assert q["detailed"].endswith("surprised later.")
        q["simple"][4] = "Hand over with a note on what's skipped"
    assert _broken(kept, plain_end) == []
    # A follow-up's own answer is free the same way.
    def follow_end(d):
        f = _q(d)["follow"][0]
        f["detailed"] = f["detailed"].replace(", because that's where it'd break.",
                                              ", which is the case I'd most expect to go wrong.")
        assert f["detailed"].endswith("go wrong.")
    assert _broken(kept, follow_end) == []
    # Still never an offer to say more: the answer ends, and they ask.
    _has(_broken(kept, lambda d: _q(d).update(detailed=_q(d)["detailed"] + " I'm happy to go into more "
                                                                           "detail if you'd like.")),
         "ends on an offer to say more")


# ------------------------------------------------------------------ the opening

def test_the_opening_is_said_once_as_the_answer_to_tell_me_about_yourself(kept):
    # The maintainer, 2026-11-12: a prep's first part said the introduction as its lines to say
    # first, again as the answer to "Tell me about yourself", and the page showed it a third
    # time at a glance. Where the opening holds that question, its answer is the opening.
    doc, ctx = kept
    opening = _part(doc, "p1")
    intro = L.intro_question(doc, opening)
    assert opening["kind"] == "opening" and intro and intro["q"] == "Tell me about yourself."
    assert opening["say"] == [] and L._said(intro), "said once, as the answer"
    assert not [w for w in _broken(kept, lambda d: None) if "nothing to say first" in w]
    # The introduction written again as the part's lines is refused, in plain words.
    def twice(d):
        _part(d, "p1")["say"] = [{"t": "I'm an operations analyst with seven years turning warehouse "
                                       "and supplier data into forecasts.", "prompts": [intro["id"]]}]
    _has(_broken(kept, twice), "the answer to \"Tell me about yourself.\" is how you open",
         "leave this part's lines to say first empty")
    # A part that opens with no such question still needs its lines to say first.
    assert L.intro_question(doc, _part(doc, "p2")) is None
    _has(_broken(kept, lambda d: _part(d, "p2").update(say=[])), "nothing to say first yet")


def test_a_known_tell_me_about_yourself_is_answered_by_the_opening():
    ctx = _real_ctx()
    with open(REAL, encoding="utf-8") as fh:
        filled = json.load(fh)
    filled["known"] = list(filled["known"]) + [{"text": "Tell me about yourself.", "from": "the recruiter"}]
    doc = L.merge(L.build(ctx), filled)
    k = next(k for k in doc["known"] if k["text"] == "Tell me about yourself.")
    assert k["question"] == L.intro_question(doc, _part(doc, "p1"))["id"]
    assert L.problems(doc, ctx) == [], "answering it is how the interview opens"


# ------------------------------------------------------------------ the follow-ups

def test_follow_ups_are_two_or_three_and_one_line_goes_three_deep(kept):
    _has(_broken(kept, lambda d: _q(d).update(follow=_q(d)["follow"][:1])), "1 follow-up", "2 or 3")
    _has(_broken(kept, lambda d: _q(d)["follow"][0]["follow"][0].update(follow=[])),
         "no line of its follow-ups goes 3 deep")


def test_a_follow_up_is_put_as_they_would_ask_it(kept):
    _has(_broken(kept, lambda d: _q(d)["follow"][1].update(
        q="Can you think of any way at all that you could make the function run faster?")),
        "the follow-up runs to 16 words")


def test_a_follow_up_script_is_half_a_minute(kept):
    _has(_broken(kept, lambda d: _q(d)["follow"][1].update(detailed="Yes, it can be faster with pandas.")),
         "30 to 90")


# ------------------------------------------------------------------ the terms

def test_a_term_needs_an_everyday_likeness_of_its_own(kept):
    _has(_broken(kept, lambda d: d["terms"]["sku"].pop("like")), "add what it is like")
    _has(_broken(kept, lambda d: d["terms"]["sku"].update(like=d["terms"]["sku"]["plain"])),
         "repeats what it means")


def test_a_term_is_explained_without_another_hard_word(kept):
    _has(_broken(kept, lambda d: d["terms"]["sku"].update(plain="One line of a demand forecast.")),
         "without another hard word (\"demand forecast\")")
    _has(_broken(kept, lambda d: d["terms"]["sku"].update(like="Like an EAN on a tin of beans.")),
         "without another hard word (\"EAN\")")


def test_every_hard_word_said_is_explained(kept):
    _has(_broken(kept, lambda d: _q(d).update(detailed=_q(d)["detailed"].replace(
        "So I'd return", "Using MAPE, I'd return"))), "\"MAPE\" is not explained")
    # Explained once in the terms, it passes.
    def add(d):
        _q(d).update(detailed=_q(d)["detailed"].replace("So I'd return", "Using MAPE, I'd return"))
        d["terms"]["mape"] = {"name": "MAPE", "match": ["MAPE"],
                              "plain": "The average miss, as a share of what really happened.",
                              "here": "At Fernhill Freight, how far each site's pallet forecast was out, on average.",
                              "like": "Like averaging how late each bus was, as a share of its journey."}
    assert not [w for w in _broken(kept, add) if "MAPE" in w]


def test_an_older_prep_keeps_its_own_rules():
    """A prep whose answers are one string each is held to the two to four sentences it was
    written for, and is never asked for points, a likeness or a hook."""
    with open(REAL, encoding="utf-8") as fh:
        old = json.load(fh)
    for q in old["questions"]:
        for f, _d, _w in [(q, 0, "")] + list(L._nodes(q)):
            if isinstance(f.get("simple"), list):
                f["simple"] = " ".join(c + "." for c in f["simple"])
    for p in old["parts"]:
        for k in L.CODING:
            p.pop(k, None)
    for t in old["terms"].values():
        t.pop("like", None)
    ctx = _real_ctx()
    doc = L.merge(L.build(ctx), old)
    assert not L.live_way(doc)
    said = " ".join(w for _x, w in L.problems(doc, ctx))
    assert "points" not in said and "what it is like" not in said and "not explained" not in said


# ------------------------------------------------------------------ a coding part

def test_a_coding_part_holds_its_steps_and_each_is_short(kept):
    _has(_broken(kept, lambda d: _part(d).update(steps=_part(d)["steps"][:2])), "2 steps to take", "4 to 7")
    _has(_broken(kept, lambda d: _part(d)["more"].__setitem__(0, "Add tests for the awkward weeks.")),
         "starts \"With more time I'd\"")
    _has(_broken(kept, lambda d: _part(d)["code"][0].update(c="x = " + "1 + " * 30 + "1")),
         "one line of 80 characters at most")
    _has(_broken(kept, lambda d: _part(d)["steps"][0].update(say="I'll start typing the loop straight away.")),
         "first step is saying the task back")


def test_a_question_about_your_past_is_never_asked_while_you_code(kept):
    def add(d):
        d["questions"].append({"id": "x1", "part": "p3", "who": "manager",
                               "q": "Tell me about a time you disagreed with your manager.",
                               "also": [], "simple": "", "detailed": "", "story": None,
                               "known": None, "draft": False, "from": [], "follow": []})
    _has(_broken(kept, add), "belongs in the part where you tell your story")


def test_the_words_file_takes_a_coding_part_and_refuses_one_written_as_one_value(kept):
    doc, _ctx_ = kept
    got = L.words_into(doc, {"parts": {"p3": {"stuck": ["Can I think aloud for a moment?",
                                                        "Let me get a slow version working first."]}}})
    assert _part(got)["stuck"][0] == "Can I think aloud for a moment?"
    with pytest.raises(ValueError) as e:
        L.words_into(doc, {"parts": {"p3": {"steps": "Say it back, then write the loop"}}})
    _plain(str(e.value))
    assert "write it as a list" in str(e.value)


# ------------------------------------------------------------------ what reads the points

def test_the_points_are_read_as_words_by_the_timing_and_the_brief(kept):
    doc, _ctx_ = kept
    top = next(x for x in L.likely(doc, n=20) if x["question"].startswith("Given weekly demand"))
    assert top["answer"].startswith("Return SKUs with forecast error over threshold.") and "[" not in top["answer"]
    said = [t for where, t, _d, _q in L.spoken(doc) if where.endswith(L.POINTS)]
    assert said and all(isinstance(t, str) for t in said)
    assert doc["timing"]["parts"]["p3"]["words"] > 0


def test_each_answer_shows_the_points_first_unless_the_person_says_script(kept, monkeypatch):
    # The live review, 2026-11-11: on a call the points lead and the script sits under them. The
    # page draws what the writer says, so both read the same default and the same setting.
    doc, _ctx_ = kept
    assert L.build(_ctx())["lead"] == "cues" == L.LEAD
    doc["checked"] = {"on": "2026-03-11", "problems": 0, "drafts": 0}
    assert L.for_page(doc)["lead"] == "cues"
    real = person.get
    monkeypatch.setattr(person, "get", lambda k, d=None: "script" if k == "interview.lead" else real(k, d))
    assert L.build(_ctx())["lead"] == "script"
    # A setting changed after the prep was made reaches the page without making it again.
    assert L.for_page(doc)["lead"] == "script"
    # A word the page does not know is the default.
    monkeypatch.setattr(person, "get", lambda k, d=None: "bullets" if k == "interview.lead" else real(k, d))
    assert L.for_page(doc)["lead"] == "cues"


def test_a_story_brings_its_five_probes_in_order():
    assert [w for w, _q in L.STORY_FOLLOW] == ["manager", "technical", "technical", "senior", "senior"]
    assert L.STORY_FOLLOW[1][1] == "What didn't work?"


def test_the_command_refuses_a_point_copied_from_the_script_in_plain_words(tmp_path):
    """The real path: `interview_pack.py live --fill <words> --write`, as /interview Step 3b
    runs it, keeps nothing while a point copies the script, and says so in plain words."""
    import subprocess
    from test_interview_pack import COMPANY, ROLE
    run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), *a],
                                    capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))
    out = tmp_path / "live.json"
    assert run("live", COMPANY, "--role", ROLE, "--out", str(out)).returncode == 0
    qid = json.loads(out.read_text(encoding="utf-8"))["questions"][0]["id"]
    script = ("I'd start with the forecast, because that's where most of my work has been. "
              "I rebuilt the weekly forecast in Python with promotions in it, and the planners "
              "could see where it held.")
    words = tmp_path / "words.json"
    words.write_text(json.dumps({"questions": {qid: {"simple": [
        "Forecast first", "I rebuilt the weekly forecast in Python", "Planners saw where it held"],
        "detailed": script}}}), encoding="utf-8")
    got = run("live", COMPANY, "--role", ROLE, "--fill", str(words), "--write")
    assert got.returncode == 1
    assert "copies the script" in got.stdout, got.stdout
    _plain(got.stdout.split("copies the script")[0][-200:])
