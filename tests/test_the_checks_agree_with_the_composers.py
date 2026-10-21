"""The checks agree with the composers, and each finding is said once, under its own name.

From an audit of compose.py, advice.py, tone.py, voice_check.py, learned.py, reading.py and
outreach.py (2026-10-20): a sentence with "your" in it read as a claim about the reader,
the person's work-authorization line counted as a batch sharing a sentence, a composed
"connected" note refused by the length its own shape allows, the sender's own interests
refused as flattery, a request for a pointer refused as a job ask with itself as the fix, a
follow-up refused for "hope you're well", one finding reported three times under a name no
override could lift, fix texts that offered wording the person's own voice check refuses, a
question and an offer warned as stacked hedges, the topic of the message warned as a
repeat, an email after a call warned for its exit, an error that sent the writer to a note
validate() refuses, an outreach check that ran half of validate(), and four composers that
ran a quarter of it. Invented people and employers only; the example person is Morgan
Ellis.
"""
from __future__ import annotations

import os
import pickle
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import advice  # noqa: E402
import compose  # noqa: E402
import learned  # noqa: E402
import outreach  # noqa: E402
import reading  # noqa: E402
import reply  # noqa: E402
import tone  # noqa: E402

DASH = chr(0x2014)
GREET = "Hi Wren, we both worked at Oakmere Foods."


def rules(found):
    """Every rule name a finding answers to: its own, and for a draft that reads as
    generated, voice_check's name for the check inside it ("house-style")."""
    return ({getattr(a, "rule", None) for a in found}
            | {compose._check_of(a) for a in found if hasattr(a, "text")}) - {""}


def _entries(monkeypatch, **row):
    base = {"date": "2026-10-20", "area": "messages", "said": "x", "rule": "x",
            "status": "active"}
    monkeypatch.setattr(learned, "entries", lambda area=None: [dict(base, **row)])


# ------------------------------------------------------------ 1. a "your" is not a claim

def test_a_sentence_about_the_senders_feeling_is_no_inference_about_the_reader():
    for s in ("Your talk on forecasting stock levels stuck with me.",
              "I'm a big fan of your team's markdown work."):
        assert advice.provenance(s) == "", s
        assert "unhedged_inference" not in rules(advice.check(f"Hi Sasha, {s}", "connection"))
    # The reader as the subject is still an inference, and still hedged by the composer.
    assert advice.provenance("You moved into pricing from economics.") == advice.INFERRED
    assert "unhedged_inference" in rules(advice.check(
        "Hi Sasha, we met once. You moved into pricing from economics.", "connection"))
    assert compose.hedge("Your talk on forecasting stuck with me") == \
        "Your talk on forecasting stuck with me."
    assert compose.hedge("You moved into pricing from economics") != \
        "You moved into pricing from economics."


def test_the_composers_hedge_reads_the_same_test_as_provenance(monkeypatch):
    assert not hasattr(compose, "_READER_SUBJECT")
    monkeypatch.setattr(advice, "reader_is_subject", lambda s: False)
    assert compose.hedge("You moved into pricing from economics") == \
        "You moved into pricing from economics."
    assert advice.provenance("You moved into pricing from economics.") == ""


# ------------------------------------------------------------ 2. their own lines in a batch

def test_a_batch_sharing_the_persons_work_authorization_line_is_not_alike():
    reasons = {"a1": {"how_found": "I found you while looking at Larkspur's pricing team"},
               "a2": {"how_found": "I found you on Fernhill's people page"},
               "a3": {"common_ground": "We both worked at Oakmere Foods"},
               "a4": {"how_found": compose.how_found_line("event", event="the depot summit")}}
    names = {"a1": "Ana Rook", "a2": "Bo Venn", "a3": "Juno Castellan", "a4": "Wren Halloway"}
    notes = {cid: compose.first_note(names[cid], reader="decision_maker", variant_key=cid, **kw)
             for cid, kw in reasons.items()}
    line = compose.work_auth_line("senior")
    assert all(line in n for n in notes.values())        # the line is in every note
    found = reading.alike(notes)
    assert not [f for f in found if "sponsorship" in str(f[1])], found


def test_one_test_of_two_lines_being_the_same(monkeypatch):
    monkeypatch.setattr(compose, "_same_words", lambda a, b: True)
    assert reading._same("one line", "a different line")
    monkeypatch.undo()
    assert compose._same_words("Zoé ran the depot forecasts", "Zoe ran the depot forecasts")


# ------------------------------------------------------------ 3. a note carries its shape

def test_a_connected_note_is_checked_against_its_own_length():
    note = compose.first_note(
        "Wren Halloway", common_ground="We both worked at Oakmere Foods, you in the Leeds "
        "planning team and me in Manchester, a few years apart",
        question="How did the move from planning into the pricing team at Saltmarsh come "
                 "about, and what does the team look after day to day",
        shape="connected", how_found="I found you while looking at Saltmarsh's pricing team",
        variant_key="x1", hedged=False)
    assert note.shape == "connected" and len(note) > compose.schema.LIMITS["connection_note_chars"]
    assert "too_long" not in rules(compose.validate(note, "connection", name="Wren Halloway"))
    assert "too_long" in rules(compose.validate(str(note), "connection", name="Wren Halloway"))
    longer = compose.Note(" ".join([str(note)] * 2), note.reader, note.recruiter, "connected")
    assert "too_long" in rules(compose.validate(longer, "connection"))
    assert pickle.loads(pickle.dumps(note)).shape == "connected"
    assert compose.note_chars("connected") == compose.CONNECTED_CHARS
    assert compose.note_chars("shared") == compose.schema.LIMITS["connection_note_chars"]


# ------------------------------------------------------------ 4. praise is to them

@pytest.mark.parametrize("about_me", [
    "I'm looking for more interesting work in demand forecasting, ideally in fresh food.",
    "A meetup talk on shelf-life forecasting is what inspired me to move into pricing.",
    "I've been fascinated by markdown pricing since a project there.",
])
def test_the_senders_own_interest_is_not_flattery(about_me):
    text = f"{GREET} {about_me} Would you have 15 minutes for a few questions sometime?"
    assert "flattery" not in rules(compose.validate(text, "connection", name="Wren Halloway"))


@pytest.mark.parametrize("praise", [
    "Larkspur's markdown work is impressive.",
    "It's exactly the kind of work I'd like to do more of.",
    "Your move into pricing really interested me.",
])
def test_praise_of_them_is_still_refused(praise):
    text = f"{GREET} {praise} Would you have 15 minutes?"
    assert "flattery" in rules(compose.validate(text, "connection", name="Wren Halloway"))


# ------------------------------------------------------------ 5. a pointer is not a job ask

def test_asking_who_to_speak_to_is_not_a_job_ask_and_a_job_ask_still_is():
    ask = f"{GREET} Who should I speak to about demand forecasting at Saltmarsh?"
    assert "asks_for_the_job" not in rules(compose.validate(ask, "connection", reader="peer"))
    for job in ("Is the team hiring at the moment?", "Who hires for it?",
                "Do you have any openings on your team?"):
        found = compose.validate(f"{GREET} {job}", "connection", reader="peer")
        assert "asks_for_the_job" in rules(found), job


# ------------------------------------------------------------ 6. warmth in a follow-up

def test_hope_youre_well_is_allowed_in_every_follow_up(monkeypatch):
    text = "Hi Wren, hope you're well. Any word back from the hiring manager?"
    assert compose.validate(text, "nudge", name="Wren Halloway") == []
    assert compose.validate(text, "intro", name="Wren Halloway") == []
    assert "house-style" not in rules(compose.validate(text, "email", name="Wren Halloway"))
    assert compose.nudge("Wren Halloway", "hope you're well. Any word back from the hiring "
                         "manager?").startswith("Hi Wren, hope you're well.")
    # Changed 2026-10-21: the person's own words outrank the app's default in every kind of
    # message, a cold one too (their OWN_VOICE has the phrase, and it is their OPENER).
    assert "house-style" not in rules(compose.validate(text, "message", name="Wren Halloway"))
    # With no OWN_VOICE and no OPENER of their own, a cold message still refuses it.
    import re
    monkeypatch.setattr(compose, "_OWN_VOICE", re.compile(r"(?!x)x"))
    monkeypatch.setattr(compose, "OPENER", "")
    assert "house-style" in rules(compose.validate(text, "message", name="Wren Halloway"))


# ------------------------------------------------------------ 7. one finding, its own name

def test_a_voice_check_finding_is_under_its_own_name_and_an_override_lifts_it(monkeypatch):
    # A stock phrase that is not the person's own (theirs are lifted in every kind since
    # 2026-10-21): "would welcome a conversation".
    text = f"{GREET} I would welcome a conversation if you have anything coming up."
    found = compose.validate(text, "message", name="Wren Halloway")
    # One rule name a person's own tests look for, with the check's own name inside it.
    assert {v.rule for v in found if compose._check_of(v) == "house-style"} == \
        {"reads_as_generated"}
    _entries(monkeypatch, overrides=["house-style"])
    assert "house-style" not in rules(compose.validate(text, "message", name="Wren Halloway"))
    assert "your_rule_outranks" in rules(compose.advise(text, "message", name="Wren Halloway"))


def test_a_phrase_a_dash_and_a_never_say_are_each_reported_once(monkeypatch):
    def hits(text, word, kind="nudge"):
        return [v for v in compose.validate(text, kind, name="Wren Halloway")
                if word.lower() in v.text.lower()]
    assert [v.rule for v in hits(f"{GREET} Happy to circle back next month.", "circle back")] \
        == ["banned_phrase"]
    assert [v.rule for v in hits(f"Hi Wren, we both worked at Oakmere {DASH} years apart.",
                                 DASH)] == ["em_dash"]
    _entries(monkeypatch, never_say=["moving quickly"])
    assert [v.rule for v in hits(f"{GREET} I'm moving quickly on it.", "moving quickly")] \
        == ["person_dislikes"]


# ------------------------------------------------------------ 8. a fix the check passes

def test_the_fix_texts_offer_the_open_ask_the_persons_voice_passes(monkeypatch):
    monkeypatch.setattr(advice, "_NET", None)               # no OWN_VOICE: "love to" refused
    monkeypatch.setattr(compose, "_OWN_VOICE", __import__("re").compile(r"(?!x)x"))
    plain = advice.open_ask()
    assert plain == advice.OPEN_ASK_PLAIN
    bad = f"{GREET} How would someone like me get hired onto your team?"
    fixes = [a.fix for a in compose.advise(bad, "connection", reader="decision_maker")
             if a.rule == "ai_tell"]
    assert fixes and plain in fixes[0] and "love to" not in fixes[0].lower()
    asks = compose.first_note_findings(f"{GREET} Is the team hiring?", reader="peer")
    assert asks and plain in asks[0].text and "love to" not in asks[0].text.lower()
    taken = f"{GREET} {plain}"
    assert not {"house-style", "reads_as_generated"} & rules(
        compose.validate(taken, "connection", reader="decision_maker"))


# ------------------------------------------------------------ 9. hedges in questions, offers

def test_a_question_and_an_offer_are_not_stacked_hedges():
    for s in ("Would you know anyone I could speak to who might know the pricing team?",
              "If you think it might help, I can send over the forecasting write-up."):
        assert "stacked_hedge" not in rules(advice.check(f"{GREET} {s}", "connection")), s
    assert "stacked_hedge" in rules(advice.check(
        f"{GREET} I think your team might be rebuilding the forecasts.", "connection"))


# ------------------------------------------------------------ 10. the subject said twice

def test_the_messages_subject_may_be_said_twice_and_other_repeats_are_warned():
    def said_twice(text):
        return [a.text for a in advice.check(text, "connection") if a.rule == "repeated_word"]
    topic = (f"{GREET} It looks like you moved from planning into pricing, which is the move "
             "I'm hoping to make. I've spent three years on pricing models for fresh food. "
             "Would you have 15 minutes for a few questions sometime?")
    assert said_twice(topic) == []
    # Within one sentence, always.
    assert any('"consulting"' in t for t in said_twice(
        "Hi Ana, I'm a data scientist in consulting, with four years across Oakmere and "
        "consulting work."))
    # "now" in two sentences side by side, always.
    assert any('"now"' in t for t in said_twice(
        "Hi Ana, I'm in Manchester now. I work on depot forecasts now."))
    # A word the subject does not name, in two sentences side by side.
    assert any('"pipeline"' in t for t in said_twice(
        "Hi Ana, I built the depot pipeline at Oakmere. The pipeline cut forecast errors by a "
        "third. Would you have 15 minutes sometime?"))


# ------------------------------------------------------------ 11. an email is asked for

def test_an_email_after_a_call_is_not_warned_for_its_easy_no():
    em = compose.email(
        "Wren Halloway", "My CV, as promised",
        "Thanks for the call on Tuesday and for offering to pass my details to the pricing lead.",
        "At Oakmere I rebuilt the weekly demand forecast for 1,200 stores, cutting error from "
        "22% to 14%.", "If the timing is wrong for the team, totally fine if not")
    assert "email" not in advice.FIRST_CONTACT
    assert "soft_exit" not in rules(compose.advise(em, "email", name="Wren Halloway"))
    assert "soft_exit" in rules(advice.check(
        f"{GREET} Would you have 15 minutes? Totally fine if not.", "connection"))


# ------------------------------------------------------------ 12. the error's own advice

def test_the_unconfirmed_reading_error_never_sends_the_writer_to_a_refused_note():
    with pytest.raises(compose.UnconfirmedReading) as e:
        compose.first_note("Wren Halloway", common_ground="I read your post on markdown "
                           "pricing for fresh food", variant_key="c9", reader="peer")
    assert "name what they said or made" in str(e.value)
    assert "not that you read or saw it" in str(e.value)
    # What it says to write instead passes.
    told = (f"{GREET} Your point that markdown should follow shelf life stuck with me. "
            "Would you have 15 minutes for a few questions sometime?")
    assert compose.validate(told, "connection", name="Wren Halloway") == []


# ------------------------------------------------------------ 13. one gate for outreach

@pytest.mark.parametrize("said", ["I've just applied", "I have just applied",
                                  "I just applied", "I've applied for"])
def test_saying_you_applied_is_a_job_ask_in_every_form(said):
    assert compose.JOB_ASK.search(f"Hi Wren, {said} the Demand Planner role at Oakmere.")


def test_applying_a_method_is_not_applying_for_a_job():
    for s in ("I like to apply statistics to markdown.",
              "I've applied machine learning to depot forecasts."):
        assert not compose.JOB_ASK.search(s), s


def test_the_outreach_note_runs_validate_for_a_message():
    clean = ("At Saltmarsh Analytics I rebuilt the weekly demand forecast for 1,200 stores and "
             "cut forecast error from 22% to 14%. Happy to answer anything the application "
             "leaves open.")
    note = outreach.whole_note("Oakmere Foods", "Demand Planner", clean)
    assert outreach.check_note(note) == []
    sent = note.replace("[name]", "Wren")
    assert compose.validate(sent, "message", reader="decision_maker") == []
    assert "asks_for_the_job" in rules(compose.validate(sent, "connection",
                                                        reader="decision_maker"))
    praised = outreach.whole_note("Oakmere Foods", "Demand Planner", clean.replace(
        "Happy to", "Your team's markdown work really interested me. Happy to"))
    assert any(p.startswith("flattery") for p in outreach.check_note(praised))
    # A message has no length of its own: the note's own word limit is check_note's.
    assert "too_long" not in rules(compose.validate(" ".join([sent] * 8), "message"))


# ------------------------------------------------------------ the composers' gate

@pytest.mark.parametrize("build", [
    lambda: compose.nudge("Wren Halloway", f"just checking in {DASH} did you get a chance to "
                          "look at my note?"),
    lambda: compose.nudge("Wren Halloway", "just checking in to see if you had a chance to "
                          "look at my note"),
    lambda: compose.email("Wren Halloway", "Our call", "Thanks for the call on Tuesday",
                          "Happy to circle back next month.", ""),
    lambda: compose.referral_ask("Wren Halloway", "thanks for the chat, happy to circle back",
                                 "Planning Analyst", "https://example.com/job/1"),
    lambda: compose.warm_intro("Bo Venn", "Wren Halloway", "Bo suggested I get in touch. I am "
                               "passionate about forecasting."),
])
def test_every_composer_refuses_what_validate_refuses_for_its_kind(build):
    with pytest.raises(compose.Refused) as e:
        build()
    assert isinstance(e.value, compose.ReadsAsGenerated)


# ------------------------------------------------------------ what was removed, what stays

def test_dead_code_is_gone_and_the_compatibility_aliases_stay():
    for mod, name in ((compose, "_never_said"), (advice, "claims"), (advice, "EXIT_FIX")):
        assert not hasattr(mod, name), name
    # Public names a person's own tests call stay, though nothing in the app uses them.
    for name in ("connection_note", "register", "DEFAULT_CLOSE", "DEFAULT_OPENER"):
        assert hasattr(compose, name), name
    assert compose.HookIsAboutTheSender is compose.NoteIsAllAboutTheSender
    assert tone.hook_reaches_them is tone.reaches_them


def test_one_list_of_check_in_phrases_and_one_stem():
    assert compose.CHECK_IN is tone.CHECK_IN
    # A chase of theirs reads every check-in phrase a draft of ours is refused for.
    assert reply._hits("Bump this when you get a moment.", reply.CHASING)
    assert reply._hits("Just checking whether you saw it.", reply.CHASING)   # as it always did
    for w in ("teams", "Larkspur's", "class", "plans"):
        assert advice._stem(w) == tone._stem(w, longer_than=4)


# ------------------------------------------------------------ the docs say what the code does

def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_the_docs_say_one_thing_about_warnings_and_lengths():
    for doc in (("CLAUDE.md",), (".claude", "commands", "network.md"),
                (".claude", "skills", "networking", "SKILL.md")):
        text = _read(*doc)
        assert "rewritten, not shown" not in text and "never shown with a warning" not in text
        assert "for the person to decide" in text, doc
    skill = _read(".claude", "skills", "networking", "SKILL.md")
    assert "about 150 words" not in skill and "about 170 words" in skill
    # The number the composer warns at is its own constant; a search of compose.py for a
    # stale "150 to 200" added nothing to it.
    assert compose.INMAIL_WORDS_FOR["decision_maker"] == 170
    auditor = _read(".claude", "agents", "grounding-auditor.md")
    rest = auditor.split("The rules that are not", 1)[1].split("5.", 1)[0]
    assert "em dash" not in rest and "documents.spelling" not in rest


def test_a_composer_refuses_what_a_first_note_does_and_leaves_the_rest_as_warnings():
    # Refused on every finding, an email with a "CV" file name could not even be composed to
    # be shown; a person's own test composes one and expects validate() to warn on it.
    text = compose.email("Wren Halloway", "Forecasting role", "Thanks for the call today.",
                         "Body paragraph.", "Happy to talk any afternoon next week.",
                         attachment="Morgan_Example_CV_KM.pdf")
    assert "Morgan_Example_CV_KM.pdf" in text
    assert compose.GATE_REFUSES >= {"reads_as_generated", "person_dislikes", "em_dash"}
    try:
        compose.nudge("Wren Halloway", "just checking in, did you get a chance to look?")
        raise AssertionError("a check-in was composed")
    except compose.Refused:
        pass
