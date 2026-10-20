"""A round of messages is personal to each reader, and plain.

From the builder notes of one networking round (2026-10-20): each item below needed a
rewrite by hand after validate() and advise() had passed the draft. A pair of InMails built
the same way, a close with nothing to answer, a guess at what someone sees from their level,
praise from a stranger, comparisons that never said how, inferences written as fact, a fact
from their page and the close warned as inferences, a length warning that ignored what the
person asked for, a word said twice, a voice with no shorthand, and the reactions recorded
that round that nothing enforced. Invented people and employers only; the example person
is Morgan Ellis.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import advice  # noqa: E402
import compose  # noqa: E402
import learned  # noqa: E402

FOUND = compose.how_found_line("people_page", company="Larkspur")
WORK = "At Brindle & Hart I cut forecast error from 22% to 14%"


def rules(found):
    return {a.rule for a in found}


# ------------------------------------------------------------ 1. a round built alike

def test_inmails_in_one_round_sharing_a_subject_an_order_or_a_close_are_found():
    a = compose.inmail("Juno Castellan", how_found=FOUND, evidence=WORK, title="Head of Data",
                       variant_key="c", team="the forecasting team")
    b = compose.inmail("Bo Venn", how_found="I found you on Fernhill's people page",
                       evidence=WORK, title="Head of Data", variant_key="c",
                       team="the forecasting team")
    found = {what: ids for what, _detail, ids in compose.round_alike({"a": a, "b": b})}
    assert found == {"same subject": ["a", "b"], "same paragraph order": ["a", "b"],
                     "same close": ["a", "b"]}
    # Built for each reader, the same two are not alike. One template with the team swapped
    # is still one close.
    b2 = compose.inmail("Bo Venn", how_found="I found you on Fernhill's people page",
                        evidence=WORK, title="Head of Data", variant_key="c",
                        team="the planning team", order="me_and_them",
                        subject="Forecasting at Oakmere, now Brindle & Hart")
    assert [w for w, _d, _i in compose.round_alike({"a": a, "b": b2})] == ["same close"]
    b3 = compose.inmail("Bo Venn", how_found="I found you on Fernhill's people page",
                        evidence=WORK, title="Head of Data", variant_key="c",
                        question="How do the planners and the data team split the depot "
                                 "forecasts between them", order="me_and_them",
                        subject="Forecasting at Oakmere, now Brindle & Hart",
                        ask="Would you have 15 minutes for a call one week?")
    assert compose.round_alike({"a": a, "b": b3}) == []
    # Connection notes are alike()'s, where the person's own ASK is theirs to repeat.
    n1 = compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst", variant_key="a")
    n2 = compose.first_note("Bo Venn", how_found="I found you on Fernhill's people page",
                            title="Data Analyst", variant_key="a")
    assert compose.round_alike({"x": n1, "y": n2}) == []


def test_the_drafting_path_runs_the_round_check():
    import reading
    a = compose.inmail("Juno Castellan", how_found=FOUND, evidence=WORK, title="Head of Data",
                       variant_key="c")
    b = compose.inmail("Bo Venn", how_found="I found you on Fernhill's people page",
                       evidence=WORK, title="Head of Data", variant_key="c")
    # As reading.py batch reads them: the draft files, a "Subject:" line first.
    found = reading.alike({"a": str(a), "b": str(b)})
    assert ("same subject", a.subject, ["a", "b"]) in found


def test_an_inmail_is_built_for_its_reader_and_names_the_employer_they_share():
    to_head = compose.inmail("Juno Castellan", how_found=FOUND, evidence=WORK,
                             title="Head of Data", variant_key="x")
    to_peer = compose.inmail("Ana Rook", common_ground="We both worked at Oakmere Foods",
                             evidence=WORK, title="Data Analyst", variant_key="x")
    roles = [compose.paragraph_role(p) for p in to_head.body.split("\n\n")]
    assert [r for r in roles if r] == ["me", "work", "them"]
    assert to_peer.body.split("\n\n")[1].startswith("We both worked at Oakmere Foods")
    # The subject leads with the employer they share, not the same line for everyone.
    assert to_peer.subject == "Senior Operations Analyst, ex-Oakmere and Saltmarsh Analytics"
    shared = compose.inmail("Ana Rook", common_ground="We both worked at Saltmarsh Analytics",
                            evidence=WORK, title="Data Analyst", variant_key="x")
    assert shared.subject == "Senior Operations Analyst, ex-Saltmarsh Analytics and Oakmere"
    with pytest.raises(ValueError, match="order"):
        compose.inmail("Ana Rook", how_found=FOUND, evidence=WORK, order="sideways")


# ------------------------------------------------------------ 2. a bare close

def test_a_close_that_asks_nothing_about_their_work_is_bare():
    bare = ("Hi Juno,\n\nI work in supply-chain analytics.\n\n" + WORK + ".\n\n" + FOUND
            + ". I'd love to join your team, or just learn more about it.\n\nThanks,\nMorgan")
    found = [a for a in advice.check(bare, "inmail") if a.rule == "bare_close"]
    assert found and "working on at the moment" in found[0].fix
    asked = bare.replace("I'd love to join your team, or just learn more about it.",
                         "What is the forecasting team working on at the moment, and what do "
                         "you look for in people joining?")
    assert "bare_close" not in rules(advice.check(asked, "inmail"))
    # A connection note may close on a plain ask: the skill says so.
    assert "bare_close" not in rules(advice.check(
        "Hi Ana, " + FOUND + ". Would you have 15 minutes sometime?", "connection"))


def test_the_composer_closes_on_a_question_about_their_team():
    m = compose.inmail("Juno Castellan", how_found=FOUND, evidence=WORK, title="Head of Data",
                       variant_key="x", team="the forecasting team")
    assert "the forecasting team" in m.body
    assert "bare_close" not in rules(compose.advise(m, "inmail"))
    assert "repeated_word" not in rules(compose.advise(m, "inmail"))
    assert compose.validate(m, "inmail") == []
    # Named in the sentence just before, the team is not named twice running.
    said = compose.inmail("Ana Rook", how_found="I found you while looking at Larkspur's "
                          "forecasting team", evidence=WORK, title="Data Analyst",
                          variant_key="x", team="Larkspur's forecasting team", order="me_first")
    assert said.body.count("Larkspur's forecasting team") == 1
    assert "What are they" in said.body


# ------------------------------------------------------------ 3. a guess from their level

def test_guessing_what_they_see_from_their_level_is_warned():
    text = "Hi Ana, you've probably seen a fair few of the Manchester teams from a Staff role."
    found = [a for a in advice.check(text, "connection") if a.rule == "guesses_from_their_level"]
    assert found and "ask it" in found[0].fix
    asked = "Hi Ana, how do the Manchester teams tend to set up their forecasting?"
    assert "guesses_from_their_level" not in rules(advice.check(asked, "connection"))
    assert "guesses_from_their_level" not in rules(advice.check(
        "Hi Ana, I saw the Staff role at Larkspur.", "connection"))


# ------------------------------------------------------------ 4. praise from a stranger

@pytest.mark.parametrize("praise", [
    "Your ads economics work at Larkspur really interested me.",
    "It's exactly the kind of work I'd like to do more of.",
    "I was fascinated by your depot forecasting.",
    "Your move into pricing is impressive.",
])
def test_praise_from_a_stranger_is_refused_with_the_plain_link_as_the_fix(praise):
    found = [v for v in compose.validate(f"Hi Ana, {praise} Would you have 15 minutes?",
                                         "connection") if v.rule == "flattery"]
    assert found and "plain link" in found[0].text
    # Inside a live thread it is their conversation, not a cold note.
    assert "flattery" not in {v.rule for v in compose.validate(f"Thanks Ana. {praise}", "reply")}


# ------------------------------------------------------------ 5. comparisons that say how

@pytest.mark.parametrize("text", [
    "Your work goes a lot further than what I do.",
    "Larkspur would be a step on from my work at Brindle & Hart.",
    "It's where I'd like to take my work next.",
])
def test_a_comparison_that_never_says_how_is_warned(text):
    found = [a for a in advice.check(f"Hi Ana, {text}", "connection")
             if a.rule == "vague_comparison"]
    assert found and "bigger" in found[0].fix


def test_a_comparison_that_says_how_is_not_warned():
    text = "Hi Ana, your forecasting goes further than mine, at ten times the volume."
    assert "vague_comparison" not in rules(advice.check(text, "connection"))


# ------------------------------------------------------------ 6. hedged by default

def test_an_inference_about_them_comes_out_hedged_once():
    note = compose.first_note("Ana Rook", parallel="You moved into Larkspur from logistics",
                              title="Data Analyst", variant_key="z")
    assert "you moved into Larkspur from logistics" in note
    assert "You moved into" not in note
    assert not {"unhedged_inference", "stacked_hedge"} & rules(compose.advise(note, "connection"))
    plain = compose.first_note("Ana Rook", parallel="You moved into Larkspur from logistics",
                               title="Data Analyst", variant_key="z", hedged=False)
    assert "You moved into Larkspur" in plain
    # What their page says is said plainly; a hedged one is not hedged twice.
    r = {"headline": "Forecasting lead at Larkspur", "about": "I moved into Larkspur from "
         "logistics after six years.", "items": [], "experience": []}
    stated = compose.first_note("Ana Rook", parallel="You moved into Larkspur from logistics",
                                title="Data Analyst", variant_key="z", reading=r)
    assert "You moved into Larkspur" in stated
    m = compose.inmail("Ana Rook", common_ground="Your team builds the depot forecasts",
                       evidence=WORK, title="Data Analyst", variant_key="z")
    assert "your team builds the depot forecasts" in m.body
    assert compose.hedge("It looks like you moved into Larkspur") == \
        "It looks like you moved into Larkspur."


# ------------------------------------------------------------ 7. not inferences

def test_a_fact_read_off_their_page_and_the_close_are_not_inferences():
    r = {"headline": "", "about": "", "items": [],
         "experience": [{"employer": "QMX", "title": "Economist"},
                        {"employer": "KMB", "title": "Economist"}]}
    fact = "I noticed you started out as an economist before QMX and KMB."
    assert advice.provenance(fact, r) == advice.STATED
    assert "unhedged_inference" not in rules(advice.check(fact, "connection", reading=r))
    close = "I'd love to join your team at Larkspur, or just hear more about what you do."
    assert "unhedged_inference" not in rules(advice.check(
        "Hi Ana, " + FOUND + ". " + close, "connection"))
    # A claim written as fact is still one.
    assert "unhedged_inference" in rules(advice.check(
        "You started in logistics before moving into software.", "connection", reading=r))


# ------------------------------------------------------------ 8. the length they asked for

LONG = " ".join(["Forecasting at depot level is the work I do every week."] * 13)


def test_the_length_they_asked_for_moves_the_inmail_warning(monkeypatch):
    assert "longer_than_this_reader_needs" in rules(compose.advise(LONG, "inmail",
                                                                   reader="peer"))
    row = {"date": "2026-10-20", "area": "messages", "said": "slightly longer, more substance",
           "rule": "InMails run to about 170 words", "status": "active",
           "length": learned.parse_lengths(["inmail=170"])}
    monkeypatch.setattr(learned, "entries", lambda area=None: [row])
    assert learned.length("inmail", "peer") == 170
    assert compose.inmail_words("peer") == 170
    assert "longer_than_this_reader_needs" not in rules(compose.advise(LONG, "inmail",
                                                                       reader="peer"))
    # One reader only, where they said so.
    row["length"] = learned.parse_lengths(["inmail:recruiter=200"])
    assert compose.inmail_words("peer") == compose.INMAIL_WORDS_FOR["peer"]
    with pytest.raises(SystemExit):
        learned.parse_lengths(["inmail=longer"])


def test_the_length_setting_and_an_override_are_followed(monkeypatch):
    monkeypatch.setattr(compose, "INMAIL_WORDS_FOR", dict(compose.INMAIL_WORDS_FOR, peer=200))
    assert "longer_than_this_reader_needs" not in rules(compose.advise(LONG, "inmail",
                                                                       reader="peer"))
    monkeypatch.undo()
    monkeypatch.setattr(learned, "overrides", lambda: {"longer_than_this_reader_needs"})
    found = rules(compose.advise(LONG, "inmail", reader="peer"))
    assert "longer_than_this_reader_needs" not in found and "your_rule_outranks" in found


# ------------------------------------------------------------ 9. a word said twice

@pytest.mark.parametrize("text, word", [
    ("Hi Ana, I'm a data scientist in consulting, with four years across Oakmere and "
     "consulting work.", "consulting"),
    ("Hi Ana, I'm in Manchester now. I work on depot forecasts now.", "now"),
])
def test_a_word_said_twice_is_warned(text, word):
    found = [a for a in advice.check(text, "connection") if a.rule == "repeated_word"]
    assert found and f'"{word}"' in found[0].text


def test_names_and_small_words_said_twice_are_not_repeats():
    text = ("Hi Ana, we both worked at Larkspur. I was at Larkspur for two years and it was "
            "where I learned the most.")
    assert "repeated_word" not in rules(advice.check(text, "connection"))


# ------------------------------------------------------------ 10. the person's voice

def test_the_persons_voice_is_written_by_the_composers_and_checked(monkeypatch):
    text = "Hi Ana, I am an analyst at Saltmarsh Analytics. I studied macroeconomics."
    assert "stiff_full_form" not in rules(advice.check(text, "connection"))   # no setting
    monkeypatch.setattr(advice, "_NET", types.SimpleNamespace(VOICE={
        "contractions": True,
        "shorthand": {"Saltmarsh Analytics": "Saltmarsh", "macroeconomics": "macro"}}))
    found = {a.text: a.fix for a in advice.check(text, "connection") if a.rule == "stiff_full_form"}
    assert set(found) == {"I am", "Saltmarsh Analytics", "macroeconomics"}
    assert '"I\'m"' in found["I am"] and '"macro"' in found["macroeconomics"]
    note = compose.first_note("Ana Rook", how_found=FOUND, title="Data Analyst",
                              about_me="I am an analyst who studied macroeconomics",
                              variant_key="v")
    assert "I'm an analyst who studied macro." in note
    # Their employer stays as written: the shorthand is the sender's own.
    assert advice.spoken("I found you on the Saltmarsh Analytics people page",
                         keep=("Saltmarsh Analytics",)) == \
        "I found you on the Saltmarsh Analytics people page"
    assert compose.employers_early("Hi Ana, I was at Saltmarsh for a year.",
                                   ["Saltmarsh Analytics"]) == []


def test_the_voice_setting_has_a_safe_default_and_is_in_the_example():
    import profile_upgrades
    assert "networking.VOICE" in profile_upgrades.SAFE_DEFAULTS
    with open(os.path.join(ROOT, "profile.example", "networking.py"), encoding="utf-8") as fh:
        assert "VOICE = " in fh.read()
    assert advice.voice() == {"contractions": False, "shorthand": {}}


# ------------------------------------------------------------ 11. what that round recorded

def test_a_cv_recital_of_their_path_is_warned():
    text = "Hi Ana, you started in logistics, then moved to retail, then forecasting at Larkspur."
    assert "cv_recital" in rules(advice.check(text, "connection"))
    one_step = "Hi Ana, it looks like you moved into forecasting from logistics."
    assert "cv_recital" not in rules(advice.check(one_step, "connection"))


def test_congratulations_followed_by_a_jobs_ask_is_warned():
    text = ("Hi Juno, congrats on launching the depot planner. Would love to hear if you have "
            "anything coming up.")
    assert "congratulations_then_a_jobs_ask" in rules(advice.check(text, "connection"))
    assert "congratulations_then_a_jobs_ask" not in rules(advice.check(
        "Hi Juno, congrats on launching the depot planner. How long did it take?", "connection"))
    # The composer leaves the looking clause out beside their news.
    note = compose.first_note("Juno Castellan", "Congrats on launching the depot planner at "
                              "Larkspur", title="Data Analyst", variant_key="a",
                              their=("Larkspur",))
    assert "looking for my next role" not in note


def test_a_metric_dump_is_warned_and_one_change_counts_once():
    dump = ("Hi Ana, I cut error from 22% to 14% across 2,400 SKUs and 40k+ accounts. Would you "
            "have 15 minutes?")
    found = [a for a in advice.check(dump, "connection") if a.rule == "metric_dump"]
    assert found and "22% to 14%" in found[0].text
    one = "Hi Ana, I cut forecast error from 22% to 14%. Would you have 15 minutes?"
    assert "metric_dump" not in rules(advice.check(one, "connection"))


@pytest.mark.parametrize("line", ["No worries at all.", "Totally fine if not.",
                                  "No worries if you're not around.",
                                  "If now isn't a good time, that's fine."])
def test_the_exit_lines_that_round_sent_are_warned(line):
    text = f"Would you have 15 minutes sometime? {line}"
    assert "soft_exit" in rules(advice.check(text, "connection"))


def test_i_came_across_your_profile_is_warned_and_never_written_by_the_composer():
    found = [a for a in advice.check("Hi Ana, I came across your profile while looking at "
                                     "Larkspur.", "connection") if a.rule == "ai_tell"]
    assert found and "found you" in found[0].fix
    for kind, fields in (("team_search", {"company": "Larkspur", "team": "forecasting"}),
                         ("search", {"company": "Larkspur"})):
        assert "came across" not in compose.how_found_line(kind, **fields)


def _dislike(monkeypatch, phrase):
    row = {"date": "2026-10-20", "area": "messages", "said": "never say that", "rule": "x",
           "never_say": [phrase], "status": "active"}
    monkeypatch.setattr(learned, "entries", lambda area=None: [row])


def test_a_phrase_they_said_never_to_use_is_refused_by_every_composer(monkeypatch):
    _dislike(monkeypatch, "here now and moving quickly")
    said = "I'm here now and moving quickly on it"
    assert "person_dislikes" in {v.rule for v in compose.validate(f"Hi Ana, {said}.", "nudge")}
    with pytest.raises(compose.ReadsAsGenerated):
        compose.nudge("Ana Rook", said)
    with pytest.raises(compose.ReadsAsGenerated):
        compose.referral_ask("Ana Rook", f"thanks for the chat, {said}", "Planning Analyst",
                             "https://example.com/job/1")
    with pytest.raises(compose.ReadsAsGenerated):
        compose.email("Ana Rook", "Our chat", "Thanks for the chat on Tuesday", said, "")
    with pytest.raises(compose.ReadsAsGenerated):
        compose.warm_intro("Bo Venn", "Ana Rook", f"Bo suggested I get in touch. {said}")


def test_a_phrase_typed_with_a_curly_apostrophe_is_still_found(monkeypatch):
    _dislike(monkeypatch, "what I’m enjoying most")
    text = "Hi Ana, what I'm enjoying most is the depot work."
    assert "person_dislikes" in {v.rule for v in compose.validate(text, "connection")}
