"""What the person says about the search's output is kept, enforced and never overwritten.

Defaults are how anyone starts. A reaction ("too formal", "never say 'reach out'",
"not recruiters") outranks them, and it was applied once in a chat and lost. It is now
kept in profile/learned.json: the settings it changed are locked against upgrades, its
never-say phrases are flagged in every draft, and an app improvement to something the
person chose is offered to them, never imposed.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import learned  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import tone  # noqa: E402
import voice_check  # noqa: E402


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def test_a_reaction_is_kept_and_read_back_before_drafting(profile):
    assert learned.brief() == ""
    learned.record("voice", "too formal for me", "plain and direct; no stock pleasantries",
                   applied_to=["profile/networking.py OPENER"], today="2026-10-15")
    assert "plain and direct" in learned.brief("voice")
    assert "plain and direct" not in learned.brief("jobs")
    assert learned.locked() == ["profile/networking.py OPENER"]


def test_a_never_say_phrase_is_flagged_in_messages_and_documents(profile):
    learned.record("voice", "I never say reach out", "never 'reach out'",
                   never_say=["reach out"], today="2026-10-15")
    assert any(v.rule == "person_dislikes" for v in tone.check("Happy to reach out next week."))
    assert any(f["rule"] == "person-dislikes"
               for f in voice_check.check("I would reach out to your team."))
    assert not [v for v in tone.check("Happy to talk next week.") if v.rule == "person_dislikes"]


def test_a_never_say_phrase_with_brackets_or_parentheses_is_flagged_too(profile):
    learned.record("voice", "never these", "never these",
                   never_say=["(remote)", "[sic]", "C++ guru", "it's a fit"], today="2026-10-19")
    for text in ("The role is fully (remote) for now.", "As written [sic] by them.",
                 "A real C++ guru.", "I think it's a fit."):
        assert learned.dislikes(text), text
    assert not learned.dislikes("The role is remote for now.")
    assert not learned.dislikes("A C++ developer.")


def test_changing_their_mind_retires_a_rule(profile):
    learned.record("people", "no recruiters", "never surface recruiters", today="2026-10-15")
    learned.retire(1)
    assert learned.entries() == [] and learned.load()[0]["status"] == "retired"


def test_an_app_improvement_to_their_choice_is_offered_once_never_imposed(profile):
    learned.record("voice", "too formal", "plain and direct",
                   applied_to=["profile/networking.py OPENER"], today="2026-10-15")
    o = learned.offer("profile/networking.py OPENER", "a warmer opener", "replies were higher",
                      "method-voice v3", today="2026-10-20")
    learned.offer("profile/networking.py OPENER", "a warmer opener", "replies were higher",
                  "method-voice v3")
    assert len(learned.offers()) == 1 and "too formal" in learned.question(o)
    assert "learned-choices" in {u.id for u, _ in U.pending()}
    learned.decide(1, "keep")
    assert learned.offers() == [] and learned.entries()[0]["rule"] == "plain and direct"
    assert U.by_id("learned-choices").pending() == ""


def test_switching_to_the_apps_way_makes_it_theirs(profile):
    learned.record("voice", "too formal", "plain and direct",
                   applied_to=["profile/networking.py OPENER"], today="2026-10-15")
    learned.offer("profile/networking.py OPENER", "a warmer opener", "replies were higher", "v3")
    learned.decide(1, "switch")
    assert [e["rule"] for e in learned.entries()] == ["a warmer opener"]
    assert learned.locked() == ["profile/networking.py OPENER"]


def test_the_wording_defaults_are_settings_the_person_can_change(profile, monkeypatch):
    (profile / "networking.py").write_text(
        (profile / "networking.py").read_text(encoding="utf-8")
        + '\nGREETING = "Hey"\nREFERRAL_LINE = "Your {role} is the one I mentioned"\n',
        encoding="utf-8")
    import compose
    try:
        compose = importlib.reload(compose)
        text = compose.referral_ask("Wren Halloway", "thanks for the chat on Tuesday",
                                    "Planning Analyst role", "https://example.com/jobs/1",
                                    thread=[{"direction": "in", "channel": "message", "full_text": "Happy to help."}])
        assert text.startswith("Hey Wren,") and "Your Planning Analyst role is the one" in text
    finally:
        monkeypatch.undo()
        person._modules.clear()
        person._data.clear()
        importlib.reload(compose)


def test_upgrades_and_redos_are_told_to_leave_the_persons_settings_alone():
    upgrade = open(os.path.join(ROOT, ".claude", "commands", "upgrade.md"), encoding="utf-8").read()
    setup = open(os.path.join(ROOT, ".claude", "commands", "setup.md"), encoding="utf-8").read()
    claude = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    assert "learned.py locked" in upgrade and "learned.py offer" in upgrade
    assert "learned.py locked" in setup
    assert "learned.py record" in claude and "learned.py brief" in claude


def test_a_later_never_say_overrules_an_earlier_rule_that_prescribes_the_phrase(profile):
    # Two reactions days apart: the first set a phrase, the second said never to use it.
    # Both stayed active, so the brief told a drafting step to do both.
    learned.record("messages", "sign off warmly", "every first note signs off with 'cheers'",
                   today="2026-10-12")
    learned.record("messages", "too casual", "never 'cheers'",
                   never_say=["cheers"], today="2026-10-14")
    learned.record("messages", "keep it short", "three sentences at most; never 'cheers' either",
                   never_say=["cheers"], today="2026-10-15")
    got = learned.brief("messages")
    assert "signs off with 'cheers'" not in got           # overruled, kept as history
    assert "never 'cheers'" in got and "three sentences at most" in got   # they agree: both stand
    assert len(learned.load()) == 3 and len(learned.superseded()) == 1


RULES_MD = """# The person

- **Location:** Larkspur. Never write "moving to Larkspur", "relocating" or "currently moving"
  anywhere; the line is "I made the move".
- The word is "CV", never "resume" (a banned noun, checked already).
- Keep the informal self-description ("growth hacker") out of formal documents.
- In their words: *"never say I'm passionate"* about anything.
"""


def test_the_profiles_own_never_write_rules_are_checked_in_every_draft(profile):
    (profile / "CLAUDE.md").write_text(RULES_MD, encoding="utf-8")
    assert [p for p, _ in learned.profile_never_phrases()] == [
        "moving to Larkspur", "relocating", "currently moving"]
    assert U.by_id("profile-never-say").pending().startswith(
        'profile/CLAUDE.md says never to write "moving to Larkspur"')
    assert tone.check("I am relocating to Larkspur next month.") == [] or not any(
        v.rule == "person_dislikes" for v in tone.check("I am relocating to Larkspur next month."))
    assert learned.adopt_profile_rules(today="2026-10-19") == [
        "moving to Larkspur", "relocating", "currently moving"]
    assert any(v.rule == "person_dislikes" for v in tone.check("I am relocating to Larkspur."))
    assert any(f["rule"] == "person-dislikes" for f in voice_check.check(
        "I am currently moving to the city and keen to start."))
    assert U.by_id("profile-never-say").pending() == ""
    # Adopted once; a phrase they later retire is never adopted again.
    assert learned.adopt_profile_rules() == []
    learned.retire(1)
    assert learned.unadopted() == []


def test_a_contradiction_says_which_entry_each_command_retires(profile, capsys):
    # From a real round (2026-10-20): "Theirs is this one: retire 50; the earlier one:
    # retire 51" was read as "this one is 50", when 50 was the earlier rule.
    learned.main(["record", "--area", "messages", "--said", "open with the parallel",
                  "--rule", "open every note with the shared path",
                  "--applied-to", "networking.py OPENER"])
    capsys.readouterr()
    learned.main(["record", "--area", "messages", "--said", "open with a question",
                  "--rule", "open every note with a question about their team",
                  "--applied-to", "networking.py OPENER"])
    out = capsys.readouterr().out
    # The entry it may contradict is named with its number and date, and the chat judges it:
    # the person is never asked which stands (the maintainer, 2026-10-31).
    assert "MAY CONTRADICT entry 1 (" in out and "python3 tools/learned.py retire <n>" in out
    assert "Judge each yourself" in out and "Ask the person once which stands" not in out
    assert "python3 tools/learned.py ask <older> <newer> puts one question" in out
    assert "Theirs is this one" not in out


def test_a_rule_about_which_employers_to_pick_has_its_own_area(profile):
    learned.main(["record", "--area", "targets", "--said", "no more banks this week",
                  "--rule", "pick no new bank employers until next week"])
    assert "no new bank employers" in learned.brief("targets")


def test_a_rule_said_again_replaces_the_older_by_itself_and_keeps_what_it_held(profile, capsys):
    """Rules piled up side by side, said twice or more, while the person was asked which
    stood (the maintainer, 2026-10-31: "if it can be done in the background and it's not
    expensive, it's autonomous"). A rule said again retires the older for the newer, with the
    older's bans and settings carried over, and it can be brought back."""
    learned.main(["record", "--area", "messages", "--said", "don't name people we both know",
                  "--rule", "Never name mutual connections in a note.", "--never-say", "we both know",
                  "--applied-to", "networking.py OPENER"])
    capsys.readouterr()
    learned.main(["record", "--area", "messages", "--said", "again: no mutual connections",
                  "--rule", "Never name mutual connections in a note, ever."])
    out = capsys.readouterr().out
    assert "Replaced entry 1 (" in out and "it says the same" in out and "restore 1" in out
    rows = learned.load()
    assert rows[0]["status"] == "retired" and rows[0]["retired_why"] == "it says the same"
    assert rows[1]["never_say"] == ["we both know"] and rows[1]["applied_to"] == ["networking.py OPENER"]
    learned.main(["restore", "1"])
    assert learned.load()[0]["status"] == "active"


def test_a_rule_that_only_narrows_another_or_adds_to_a_list_is_its_own_rule(profile):
    """Words alone took "Adobe is out" for undoing "KPMG is out", and a rule that says "no
    odd phrasing ('the route I'm on')" for one that uses it (a dry run on 195 real rules,
    2026-10-31). Neither is a contradiction, and neither is a repeat."""
    learned.record("targets", "KPMG is out", "KPMG is out as an employer.",
                   applied_to=["profile/search.py BAR_DECLINED"], today="2026-10-20")
    e = learned.record("targets", "Adobe is out", "Adobe is out as an employer.",
                       applied_to=["profile/search.py BAR_DECLINED"], today="2026-10-21")
    assert e["conflicts"] == [] and e["replaced"] == []
    learned.record("voice", "odd phrase", "never \"the route I'm on\"", never_say=["the route I'm on"],
                   today="2026-10-22")
    e = learned.record("messages", "plain", "Lead with his own work; no odd phrasing ('the route I'm on').",
                       today="2026-10-23")
    assert e["conflicts"] == []
    narrow = learned.record("messages", "warm close", "Close warmly.", today="2026-10-24")
    wider = learned.record("messages", "warm close, about their team",
                           "Close warmly with a plain ask about their team and their work.", today="2026-10-25")
    assert narrow["replaced"] == [] and wider["replaced"] == []


def test_the_pile_made_before_is_tidied_once_and_contradictions_are_listed_to_judge(profile, capsys):
    learned.record("messages", "a", "Never name mutual connections in a note.", today="2026-10-01")
    rows = learned.load()
    rows.append(dict(rows[0], date="2026-10-05", said="b"))   # made before record merged repeats
    learned.save_entries(rows)
    assert [d["n"] for d in learned.tidy(dry=True)] == [1]
    assert learned.load()[0]["status"] == "active", "a dry run writes nothing"
    assert [d["for"] for d in learned.tidy()] == [2] and learned.tidy() == []
    learned.record("voice", "x", "Open with the move.", today="2026-10-06")
    learned.record("voice", "y", "never \"the move\"", never_say=["the move"], today="2026-10-07")
    got = learned.clashes()
    assert [(d["n"], d["later"]) for d in got] == [(3, 4)]
    assert learned.load()[2]["status"] == "active", "a contradiction is judged, never retired by words"
    assert learned.reviewed() == ""
    learned.main(["tidy", "--reviewed"])
    assert learned.reviewed()


def test_a_rule_that_says_never_where_the_older_did_not_is_never_merged_as_a_repeat(profile):
    """Careful (the maintainer, 2026-10-31): the same words with a "never" may be the
    opposite rule. Code never puts one away for that; the chat recording it judges."""
    learned.record("messages", "a", "Open every InMail with who he is.", today="2026-10-01")
    e = learned.record("messages", "b", "Never open every InMail with who he is.", today="2026-10-02")
    assert e["replaced"] == [] and learned.load()[0]["status"] == "active"


def test_one_question_about_the_rules_at_most_and_seldom(profile):
    """Nearly everything about the rules is decided by itself; where a chat truly cannot tell
    which of two stands, one question may reach the page, never a second while it waits, and
    not again within a fortnight (the maintainer, 2026-10-31: "ONE AT MOST AND AGAIN
    SPARSELY")."""
    learned.record("messages", "a", "Close with a question about their team.", today="2026-10-01")
    learned.record("messages", "b", "Close with the work-eligibility line.", today="2026-10-02")
    learned.record("messages", "c", "Open with the move.", today="2026-10-03")
    assert learned.ask(1, 2, today="2026-10-05") == ""
    q = learned.asked()
    assert q["older_rule"]["said"] == "a" and q["later_rule"]["said"] == "b"
    assert "already waiting" in learned.ask(1, 3, today="2026-10-05")
    assert learned.settle("later", today="2026-10-06") == "The newer rule stands."
    assert learned.load()[0]["status"] == "retired" and learned.load()[1]["status"] == "active"
    assert learned.asked() is None
    assert "asked on 2026-10-05" in learned.ask(2, 3, today="2026-10-10")
    assert learned.ask(2, 3, today="2026-10-20") == ""
    assert learned.settle("both") == "Both rules stand."
    assert [r["status"] for r in learned.load()] == ["retired", "active", "active"]
    assert "not two rules in force" in learned.ask(1, 2, today="2026-11-30")
