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
                                    "Planning Analyst role", "https://example.com/jobs/1")
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
    # A banned document noun is a word choice, not a spelling.
    found = {v.rule for v in tone.check("I have attached my resume for context.")}
    assert "document_noun" in found and "british_spelling" not in found
