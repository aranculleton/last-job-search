"""A change of LinkedIn plan reaches the checks of a process already running.

The limits were set once, when the module was first read: a long-running process (the page's
helper, a chat drafting a round) kept the old plan's limits after the person changed theirs on
the page, so a note sized for Premium passed on a free account (the audit of 2026-11-10, NW-30).
`schema.limits_now()` reads them again whenever profile/networking.py has changed, and the
checks call it.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import compose  # noqa: E402
import person  # noqa: E402
import schema  # noqa: E402

NOTE = ("Hi Ivo, hope you're well. I'm an analyst in Manchester who builds forecasting models "
        "for stock and transport, which I imagine is close to the planning work at Quayside. "
        "I'd love to hear what you're working on at the moment.")


def _too_long(text):
    return [v for v in compose.validate(text, "connection", name="Ivo Marsh")
            if "character" in v.text.lower() or v.rule in ("too_long", "length")]


def test_switching_to_free_holds_a_note_to_the_free_limit_at_once(tmp_path, monkeypatch):
    assert 200 < len(NOTE) <= 300
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    monkeypatch.setenv(person.ENV, str(prof))
    person.reset()
    try:
        assert schema.limits_now()["connection_note_chars"] == 300       # the example: Premium
        assert not _too_long(NOTE)
        path = prof / "networking.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            'LINKEDIN_PLAN = "premium"', 'LINKEDIN_PLAN = "free"'), encoding="utf-8")
        assert schema.limits_now()["connection_note_chars"] == 200
        assert _too_long(NOTE), "a 250-character note on a free plan"
        assert compose.KIND_LIMITS["connection"]["chars"] == 200
    finally:
        monkeypatch.undo()
        person.reset()
        schema.limits_now()
    assert schema.LIMITS["connection_note_chars"] == 300
    assert not _too_long(NOTE)
    assert compose.KIND_LIMITS["connection"]["chars"] == 300


def test_a_new_limit_of_unanswered_messages_reaches_a_running_process(tmp_path, monkeypatch):
    """The review of 2026-11-11: the plan's limits followed a change, but the person's own limit
    of unanswered messages (MAX_UNANSWERED, and the follow-ups it leaves) stayed as read."""
    import state
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    monkeypatch.setenv(person.ENV, str(prof))
    person.reset()
    try:
        schema.limits_now()
        assert schema.MAX_UNANSWERED == 2
        assert state.waiting_action(2) == state.FOLLOW_UP_STOP.format(n=2, s="s")
        path = prof / "networking.py"
        path.write_text(path.read_text(encoding="utf-8") + "\nMAX_UNANSWERED = 3\n",
                        encoding="utf-8")
        assert state.waiting_action(2).startswith("Follow up after"), state.waiting_action(2)
        assert schema.CONTACT_NUDGES == schema.MAX_NUDGES == 2
    finally:
        monkeypatch.undo()
        person.reset()
        schema.limits_now()
    assert schema.MAX_UNANSWERED == 2 and schema.CONTACT_NUDGES == 1


def test_the_length_check_a_draft_is_saved_with_reads_the_plan_now(monkeypatch):
    # `reading.py draft` checks a note's length alone (length_findings), and it used the limits
    # the last full check had left: after one check on another plan (60 characters, in a test
    # on Windows), every later draft was refused as too long (Platforms, 2026-11-11). It reads
    # the plan as the settings say now, as the full check does.
    import compose
    monkeypatch.setitem(compose.KIND_LIMITS["connection"], "chars", 60)
    note = "Hi Wren, hope you're well. I plan inbound loads for a regional grocer and keep its forecasts honest. Would be great to hear how the team works."
    assert 60 < len(note) <= compose.schema.limits_now()["connection_note_chars"]
    assert compose.length_findings(note, "connection") == []
