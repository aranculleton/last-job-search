"""The page's helper hands the page to a fresh one once its history has grown, not only daily.

Issue #290: the helper was replaced once a day, or near the most a chat can hold (700,000
tokens). Every step of a chat re-reads its whole history, so on a busy day one helper grew to
about 560,000 tokens and cost an estimated USD 67 against about USD 5 the day before. A
helper now hands over at a quiet moment once its history has grown RENEW_GROWTH past where
its start-up left it, measured from its own session file, so its start-up alone (anything
from about 125,000 to 310,000 tokens in the maintainer's log) never renews it. Every other
gate stands: never in its first hour, never during its own hand-over, never with small work
of its own in hand. Invented ids; the session file is written the way Claude Code writes one.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_listen  # noqa: E402
import app_setup  # noqa: E402
import helper_usage  # noqa: E402

CHAT = "session_EXAMPLEBUSYHELPER"
NOW = dt.datetime(2026, 11, 16, 15, 0, tzinfo=dt.timezone.utc)


def _usage(n: int, size: int) -> dict:
    return {"type": "assistant", "message": {
        "id": f"msg_{n}", "role": "assistant",
        "content": [{"type": "tool_use", "id": f"toolu_{n}", "name": "Bash", "input": {}}],
        "usage": {"input_tokens": 3, "cache_creation_input_tokens": 500,
                  "cache_read_input_tokens": size - 503, "output_tokens": 200}}}


def _said(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _result(n: int) -> dict:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"toolu_{n}", "content": "ok"}]}}


def _session(tmp_path, monkeypatch, start_up: list[int], after: list[int] | None) -> None:
    """A helper's session file: the prompt it was started with, its start-up's turns, then
    (unless `after` is None) its first wake and the turns since."""
    home = tmp_path / "claude"
    folder = home / "projects" / "-home-user-example-copy"
    folder.mkdir(parents=True, exist_ok=True)
    rows, n = [_said(app_listen.WAKE_PROMPT)], 0
    for size in start_up:
        n += 1
        rows += [_usage(n, size), _result(n)]
    if after is not None:
        rows.append({"type": "user", "isMeta": True, "message": {"role": "user", "content": [
            {"type": "text", "text": "This session's worker process was restarted."}]}})
        rows.append(_said("[app] The page rang: a tap waits."))
        for size in after:
            n += 1
            rows += [_usage(n, size), _result(n)]
    (folder / "helper.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                                         encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))


def _db(since: str = "2026-11-16T08:20:00Z") -> dict:
    rec = {"chat": CHAT, "title": app_listen.HELPER_CHAT_TITLE, "kind": "cloud",
           "helper": True, "since": since, "answered_at": "2026-11-16T14:50:00Z"}
    return {"meta": {"listener": {"data": rec, "version": 7}}, "work": {}}


def _renews(db, tmp_path, name: str, now: dt.datetime = NOW) -> list[str]:
    got = app_listen.decide(db, CHAT, str(tmp_path / name), now)
    return [ln for ln in got["lines"] if ln.startswith("listen: renew:")]


def _setup(monkeypatch):
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "_zone", lambda: "UTC")
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "my-job-search"))


def test_a_busy_helper_hands_over_the_same_day_once_it_has_grown(tmp_path, monkeypatch):
    """Started at 08:20 with a start-up that left it at 130,000 tokens, by 15:00 the same day
    it is at 300,000: a day by the clock is hours away and 700,000 further still, so it kept
    every step at that size, and growing, until the next morning."""
    _setup(monkeypatch)
    _session(tmp_path, monkeypatch, [82_000, 110_000, 130_000],
             [150_000, 210_000, 300_000])
    assert app_listen.history_tokens() == 300_000
    got = _renews(_db(), tmp_path, "a")
    assert len(got) == 1, got
    assert helper_usage.startup_tokens() == 130_000
    call = json.loads(got[0].split("create_session ", 1)[1].split("}.", 1)[0] + "}")
    assert call["title"] == app_listen.HELPER_CHAT_TITLE and call["permission_mode"] == "auto"
    # The line says why in words the chat can act on, and still waits for its work to be saved.
    assert "grown" in got[0] and "Once this turn's work is saved" in got[0]


def test_a_heavy_start_up_alone_never_renews_a_helper(tmp_path, monkeypatch):
    """A start-up that read every page collection and a republish left one helper at 312,000
    tokens before it answered anything (the maintainer's log, 13 November). Measured from the
    end of its start-up, it has grown only 68,000 since: it stays, so a new helper never
    renews within the hour it took the page and chats never multiply."""
    _setup(monkeypatch)
    _session(tmp_path, monkeypatch, [82_000, 200_000, 312_000], [330_000, 380_000])
    assert not _renews(_db(), tmp_path, "a")


def test_a_helper_still_in_its_start_up_is_never_renewed_by_its_size(tmp_path, monkeypatch):
    """No wake yet: its first turn is all start-up, however large, and nothing has been
    measured to have grown."""
    _setup(monkeypatch)
    _session(tmp_path, monkeypatch, [82_000, 250_000, 480_000], None)
    assert helper_usage.startup_tokens() is None
    assert not _renews(_db(), tmp_path, "a")


def test_the_other_gates_still_hold_for_a_grown_helper(tmp_path, monkeypatch):
    """Grown past the mark, it still never hands over in its first hour on the page, nor
    with small work of its own in hand (never mid-job), nor from a chat on the computer."""
    _setup(monkeypatch)
    _session(tmp_path, monkeypatch, [82_000, 130_000], [200_000, 320_000])
    assert not _renews(_db(since="2026-11-16T14:30:00Z"), tmp_path, "first-hour")
    db = _db()
    db["work"] = {"talk~a": {"data": {
        "kind": "talk", "status": "running", "title": "Is my letter ok?",
        "claimed_by": CHAT, "claimed_at": "2026-11-16T14:58:00Z",
        "lease_until": "2026-11-16T15:20:00Z"}, "version": 3}}
    assert not _renews(db, tmp_path, "mid-job")
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    assert not _renews(_db(), tmp_path, "computer")


def test_the_page_says_which_chat_answers_it_and_roughly_what_that_cost_today(tmp_path,
                                                                              monkeypatch):
    """Issue #290 asks for the day's cost in one plain line on the page, and issue #289 for the
    page to say which chats run behind it and which are safe to delete: the row for Claude's
    helper in Settings says both, worked out in the engine from the usage log the wakes keep
    (helper_usage), never by the page."""
    import app_model
    import person
    state = tmp_path / "state"
    (state / "documents").mkdir(parents=True)
    (state / "documents" / "helper_usage.json").write_text(json.dumps({"entries": [
        {"at": "2026-11-15T20:00:00Z", "chat": "session_EXAMPLEYESTERDAY", "kind": "wake",
         "listener": 300_000, "agent_in": 1_000_000, "agent_out": 5_000, "est_usd": 9.0},
        {"at": "2026-11-16T09:00:00Z", "chat": CHAT, "kind": "wake", "listener": 150_000,
         "agent_in": 2_000_000, "agent_out": 8_000, "est_usd": 1.25},
        {"at": "2026-11-16T14:00:00Z", "chat": CHAT, "kind": "wake", "listener": 290_000,
         "agent_in": 3_000_000, "agent_out": 9_000, "est_usd": 2.15}]}), encoding="utf-8")
    monkeypatch.setenv(person.STATE_ENV, str(state))
    monkeypatch.setattr(app_listen, "seen", lambda: {"listener": {
        "chat": CHAT, "title": app_listen.HELPER_CHAT_TITLE, "kind": "cloud", "helper": True}})
    model, _ = app_model.build(NOW.date(), NOW, only=("where",))
    say = model["where"]["helper"]["say"]
    assert "“Last Job Search · Page”" in say, say
    assert "an older one is safe to delete" in say and "fresh one takes over" in say, say
    assert "Answering your page cost about $3.40 today" in say, say
    assert "$9" not in say                     # yesterday's helper is yesterday's
