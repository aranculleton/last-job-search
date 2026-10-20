"""A reaction is recorded in code, not remembered: a turn cannot end with one unrecorded.

One chat redrafted nine times on the person's corrections ("rude", "identical in
structure", "too long", "that's not how I found him") and recorded none of them until
asked, because recording them was only an instruction. Now the hook the app ships holds
the turn, drafting refuses while one waits, an edit before sending records itself, and a
new rule says which earlier ones it contradicts. Synthetic transcripts and words only.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import learned  # noqa: E402
import person  # noqa: E402


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _line(kind, **kw):
    if kind == "user":
        return {"type": "user", "message": {"role": "user", "content": kw["text"]}}
    if kind == "tool":
        return {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": kw["command"]}}]}}
    if kind == "result":
        return {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}
    return {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn",
            "content": [{"type": "text", "text": kw.get("text", "Here they are.")}]}}


def _transcript(tmp_path, lines):
    path = tmp_path / "transcript.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return str(path)


def _stop(path):
    return learned.hook({"hook_event_name": "Stop", "transcript_path": path,
                         "stop_hook_active": False})


TURN_ONE = [_line("user", text="Draft first notes for the three people we found."),
            _line("tool", command="python3 tools/network/compose.py first-note ..."),
            _line("result"), _line("end")]


def test_a_drafting_turn_cannot_end_with_an_unrecorded_reaction(profile, tmp_path):
    turn = TURN_ONE + [
        _line("user", text="These are all identical in structure and way too formal."),
        _line("tool", command="python3 tools/network/compose.py first-note ..."),
        _line("result")]
    held = _stop(_transcript(tmp_path, turn))
    assert held["decision"] == "block"
    assert "identical in structure" in held["reason"] and "learned.py record" in held["reason"]
    # Drafting again refuses too, while it waits.
    assert "1 reaction(s) from the person not recorded" in learned.refuse_over_pending("compose")
    # Recorded, in their words, and the turn may end.
    learned.record("voice", "These are all identical in structure and way too formal.",
                   "vary the structure note to note; plain, not formal", today="2026-10-20")
    turn += [_line("tool", command="python3 tools/learned.py record --area voice ..."),
             _line("result")]
    assert _stop(_transcript(tmp_path, turn)) == {}
    assert learned.refuse_over_pending("compose") == ""


def test_a_reaction_that_sets_no_rule_is_skipped_with_its_reason(profile, tmp_path):
    got = learned.hook({"hook_event_name": "UserPromptSubmit",
                        "prompt": "that's not how I found him, I searched the team page"})
    assert "learned.py record" in got["hookSpecificOutput"]["additionalContext"]
    assert len(learned.pending()) == 1
    learned.skip("that's not how I found him", "a fact about one contact, fixed on the row")
    assert learned.pending() == []
    assert learned._data()["skipped"][0]["why"].startswith("a fact about one contact")


def test_an_ordinary_instruction_and_an_old_reaction_hold_nothing(profile, tmp_path):
    assert learned.reaction("Move the call to Monday and draft the follow-up.") == ""
    assert learned.reaction("<task-notification>too formal</task-notification>") == ""
    old = [_line("user", text="too formal, all of them"), _line("end")]
    later = old + [_line("user", text="Now find people at the second employer."),
                   _line("tool", command="python3 tools/network/sources.py ..."), _line("result")]
    assert _stop(_transcript(tmp_path, later)) == {}       # last turn's, not this one's


def test_a_turn_is_held_a_few_times_then_let_go_with_a_warning(profile, tmp_path):
    path = _transcript(tmp_path, TURN_ONE + [_line("user", text="this reads like a robot")])
    for _ in range(learned.HOLD_LIMIT):
        assert _stop(path)["decision"] == "block"
    assert "let go unrecorded" in _stop(path)["systemMessage"]
    assert learned.pending() == []


def test_the_app_itself_is_never_held(tmp_path, monkeypatch):
    monkeypatch.setattr(learned, "_path", lambda: None)
    path = _transcript(tmp_path, TURN_ONE + [_line("user", text="too formal")])
    assert _stop(path) == {}


def test_a_new_rule_names_the_earlier_ones_it_contradicts_with_their_dates(profile):
    learned.record("voice", "never say recently moved", "never \"recently moved\"",
                   never_say=["recently moved"], today="2026-09-16")
    e = learned.record("messages", "open with: I just moved from Lisbon to Leeds",
                       "open with where they moved from and to", today="2026-10-20")
    assert [(n, old["date"]) for n, old, _why in e["conflicts"]] == [(1, "2026-09-16")]
    assert "recently moved" in e["conflicts"][0][2]
    # Once the person chose the new one, the old one is retired and nothing conflicts.
    e2 = learned.record("messages", "keep the move line", "open with the move",
                        replaces=[1], today="2026-10-20")
    assert e2["conflicts"] == []
    assert learned.load()[0]["status"] == "retired"


def test_a_rule_can_outrank_a_check_by_name(profile):
    learned.record("voice", "I'm is fine, I always write I'm", "contractions are fine",
                   overrides=["sentence_starts_with_contraction"], today="2026-10-20")
    assert learned.overrides() == {"sentence_starts_with_contraction"}


def test_an_edit_before_sending_is_recorded_by_itself(profile):
    draft = "Hi Ana, I am a data analyst in Leeds. I would love to hear how your team works."
    sent = "Hi Ana, I'm a data analyst in Leeds. Would love to hear how your team works."
    e = learned.record_edit(draft, sent, where="first note to one contact", today="2026-10-20")
    assert '"am" became "\'m"' not in e["rule"]            # whole words, not letters
    assert "I'm" in e["rule"] and e["sent"] == sent and e["draft"] == draft
    assert learned.record_edit(draft, draft + "  ") is None
    assert e["rule"] in learned.brief("messages")


def test_the_cli_shows_the_rule_back_in_one_line(profile, capsys):
    assert learned.main(["record", "--area", "voice", "--said", "too long, cut it",
                         "--rule", "first notes under 200 characters"]) == 0
    out = capsys.readouterr().out
    assert "From now on, first notes under 200 characters (you said: \"too long, cut it\")" in out


def test_the_turns_own_final_message_already_written_does_not_hide_the_reaction(profile,
                                                                                tmp_path):
    turn = TURN_ONE + [_line("user", text="too long, and identical in structure"),
                       _line("tool", command="python3 tools/network/compose.py ..."),
                       _line("result"), _line("end", text="Redrafted.")]
    assert _stop(_transcript(tmp_path, turn))["decision"] == "block"


def test_a_long_transcript_is_read_from_its_end(profile, tmp_path, monkeypatch):
    monkeypatch.setattr(learned, "TAIL_BLOCK", 512)
    old = [_line("user", text=f"Older prompt {i}, too formal") for i in range(400)]
    turn = old + [_line("end")] + [_line("user", text="Now find people at the second employer.")]
    path = _transcript(tmp_path, turn)
    lines = learned._tail_lines(path)
    assert len(lines) < 10                       # the last finished turn on, not the file
    assert _stop(path) == {}
