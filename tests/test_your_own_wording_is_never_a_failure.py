"""The person's own wording is never a failure, however the check is run.

"Hope you're well" and "I'd love to" are one person's opener and close, in their own
voice settings and in every message they approved as an example. validate() lifted them,
and voice_check run on its own (what an audit of a follow-up or an InMail runs) did not:
both came back HARD house style, and 11 of the 14 messages they had approved failed it
(2026-10-24). A phrase inside a message they approved is theirs too, whatever OWN_VOICE
says. A letter is still held to the house style. Every person and message is invented.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import compose  # noqa: E402
import learned  # noqa: E402
import voice_check  # noqa: E402

NUDGE = ("Hi Wren, hope you're well. Following on from my note last week, I'd love to hear "
         "how the planning team works, if you have 15 minutes sometime.")
APPROVED = {"date": "2026-10-20", "said": "send it", "channel": "message", "reader": "peer",
            "status": "active",
            "text": "Hi Juno, hope you're well. I work in supply-chain analytics, and I'd love "
                    "to hear how your team plans its stock."}


def _no_settings(monkeypatch):
    """A person whose settings name neither phrase: only what they approved can."""
    monkeypatch.setattr(compose, "_OWN_VOICE", re.compile(r"(?!x)x"))
    for name in ("OPENER", "ASK", "ABOUT_ME"):
        monkeypatch.setattr(compose, name, "")
    monkeypatch.setattr(compose, "TEMPLATES", {})


def _house_style(found):
    return [v for v in found if v.rule == "reads_as_generated" and "house-style" in v.text]


def test_a_phrase_from_a_message_they_approved_is_theirs(monkeypatch):
    _no_settings(monkeypatch)
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [])
    assert _house_style(compose.validate(NUDGE, "message", name="Wren"))   # the app's default
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [APPROVED])
    assert _house_style(compose.validate(NUDGE, "message", name="Wren")) == []
    # A stock phrase they never wrote is still the app's to refuse.
    other = NUDGE.replace("hope you're well", "hope all is well")
    assert _house_style(compose.validate(other, "message", name="Wren"))


def test_the_check_run_on_its_own_counts_their_wording_as_theirs(tmp_path, monkeypatch,
                                                                  capsys):
    _no_settings(monkeypatch)
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [APPROVED])
    note = tmp_path / "nudge.md"
    note.write_text(NUDGE, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["voice_check.py", str(note)])
    assert voice_check.main() == 0
    out = capsys.readouterr().out
    assert "HARD" not in out and "not counted, your own wording" in out
    assert "hope you're well" in out and "I'd love to" in out


def test_a_letter_is_still_held_to_the_house_style(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [APPROVED])
    letter = tmp_path / "Cover_Letter.tex"
    letter.write_text("\\lettercontent{I'd love to bring this to the planning team.}",
                      encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["voice_check.py", str(letter)])
    assert voice_check.main() == 1
    assert "HARD house-style" in capsys.readouterr().out


def test_with_no_networking_profile_nothing_is_lifted(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(voice_check, "own_wording", lambda: None)
    note = tmp_path / "nudge.md"
    note.write_text(NUDGE, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["voice_check.py", str(note)])
    assert voice_check.main() == 1
    assert "HARD house-style" in capsys.readouterr().out
