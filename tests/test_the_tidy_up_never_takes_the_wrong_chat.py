"""The daily tidy-up never puts away a chat it should keep, and never leaves one it should not.

A review of `tidy.plan` against chat lists an install could hold after any run of versions
(2026-11-18) found: a chat the person started, titled like "Job search page not updating", put
away as an old page chat an hour after they stopped using it; the brief's own chat put away while
the brief was off, so the brief came back on in an archived chat; an older page chat put away
with work done after its last save; a chat recorded as put away whose archive never took,
skipped for good; the old ops chat of the 3.x setup kept for good once the brief left it; and
the computer starter named on the page by a name it no longer had after a later rename was
refused. Every chat, task and branch here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import computer  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 18)
NOW = dt.datetime(2026, 11, 18, 18, 10, tzinfo=dt.timezone.utc)
LIVE = "session_EXAMPLELIVEPAGE"
PAGE = tidy.APP_NAME + " · Page"


def _chat(sid, title, used, made="2026-11-10T08:00:00Z", origin="claude_code_mcp_seed",
          status="SESSION_STATUS_IDLE"):
    return {"id": sid, "title": title, "session_status": status, "created_at": made,
            "updated_at": used, "origin": origin}


def _detail(c, branch=""):
    return {"id": c["id"], "title": c["title"], "session_status": c["session_status"],
            "updated_at": c["updated_at"],
            "session_context": {"sources": [{"git_repository": {"url": "https://github.com/" + REPO}}]},
            "external_metadata": {"current_branches": {"": branch} if branch else {}}}


def _plan(chats, branches=None, tips=None, reg=None, triggers=(), listener=None, done=(),
          monkeypatch=None):
    branches = branches or {}
    if monkeypatch is not None:
        monkeypatch.setattr(tidy, "TIPS", {b: dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
                                           .timestamp() for b, t in (tips or {}).items()})
    listener = listener or {"chat": LIVE, "kind": "cloud", "helper": True,
                            "since": "2026-11-18T08:00:00Z", "took_from_helper": True}
    everything = [_chat(LIVE, PAGE, "2026-11-18T18:00:00Z", made="2026-11-18T08:00:00Z")] + list(chats)
    info = {c["id"]: _detail(c, branches.get(c["id"], "")) for c in everything}
    return tidy.plan(everything, [dict(t, session=t.get("persistent_session_id")) for t in triggers],
                     info, reg or {}, listener, LIVE, REPO, TODAY, set(), set(), set(done),
                     now=NOW, on_github=set(branches.values()))


def _gone(got):
    return {c["id"] for c in got["archive"]}


# ------------------------------------------------------------------ the person's own chats


@pytest.mark.parametrize("title", ["Job search page not updating", "Job search helper script questions",
                                   "Job search page notes"])
def test_a_chat_the_person_started_with_a_helper_like_title_is_never_put_away(title):
    mine = _chat("session_EXAMPLEMINE", title, "2026-11-18T15:40:00Z", origin="desktop_app")
    assert "session_EXAMPLEMINE" not in _gone(_plan([mine]))


@pytest.mark.parametrize("title", ["Job search page", "Job search helper", "Job search page (finishing up)",
                                   "Job search helper (finishing up)", "Job search: Claude's helper (keep this)",
                                   PAGE, PAGE + " (finishing up)"])
def test_every_name_a_page_chat_ever_had_is_known(title):
    assert tidy.HELPER_NAME.match(title), title


# ------------------------------------------------------------------ the brief's own chat


def test_the_briefs_own_chat_stays_while_the_brief_is_off():
    brief = _chat("session_EXAMPLEBRIEF", routines.BRIEF_CHAT_TITLE, "2026-11-12T08:05:00Z")
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEBRIEF",
         "cron": "CRON_TZ=Europe/London 0 8 * * *", "prompt_file": routines.BRIEF_FILE, "off": True,
         "chat": {"session_id": "session_EXAMPLEBRIEF", "title": routines.BRIEF_CHAT_TITLE, "own": True}}]}
    task = {"id": "trig_EXAMPLEBRIEF", "name": routines.BRIEF_NAME, "enabled": False,
            "persistent_session_id": "session_EXAMPLEBRIEF", "cron_expression": "CRON_TZ=Europe/London 0 8 * * *",
            "created_at": "2026-11-01T08:00:00Z", "prompt": routines.with_copy("Scheduled run: morning brief.", REPO)}
    got = _plan([brief], reg=reg, triggers=[task])
    assert "session_EXAMPLEBRIEF" not in _gone(got), got["archive"]


# ------------------------------------------------------------------ saved work


def test_an_older_page_chat_used_after_its_last_save_waits_for_it(monkeypatch):
    # Handed on this morning, then used until 17:00, its last save at 13:00: what it did after
    # may be only where it ran. Kept until that is saved or it has been quiet a day.
    older = _chat("session_EXAMPLEOLDERPAGE", PAGE, "2026-11-18T17:00:00Z", made="2026-11-17T08:00:00Z")
    got = _plan([older], branches={older["id"]: "claude/land-older"},
                tips={"claude/land-older": "2026-11-18T13:00:00Z"}, monkeypatch=monkeypatch,
                listener={"chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-18T08:00:00Z",
                          "took_from": "session_EXAMPLEANOTHER", "took_from_helper": True,
                          "helpers": [older["id"]]})
    assert older["id"] not in _gone(got), got["archive"]
    # Saved after its last use: it goes.
    got = _plan([older], branches={older["id"]: "claude/land-older"},
                tips={"claude/land-older": "2026-11-18T16:58:00Z"}, monkeypatch=monkeypatch,
                listener={"chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-18T08:00:00Z",
                          "took_from": "session_EXAMPLEANOTHER", "took_from_helper": True,
                          "helpers": [older["id"]]})
    assert older["id"] in _gone(got), got["keep"]


# ------------------------------------------------------------------ an archive that never took


def test_a_chat_recorded_as_put_away_but_still_open_is_judged_again():
    rows = [{"id": "session_EXAMPLESTUCK", "title": "Job search: drafts", "on": "2026-11-15"},
            {"id": "session_EXAMPLEBACK", "title": "Job search: notes", "on": "2026-11-15"},
            {"id": "session_EXAMPLEGONE", "title": "Job search: old", "on": "2026-11-15"}]
    listed = [_chat("session_EXAMPLESTUCK", "Job search: drafts", "2026-11-14T10:00:00Z"),
              # Brought back and used by the person after it was put away: theirs now.
              _chat("session_EXAMPLEBACK", "Job search: notes", "2026-11-17T10:00:00Z"),
              _chat("session_EXAMPLEGONE", "Job search: old", "2026-11-14T10:00:00Z",
                    status="SESSION_STATUS_ARCHIVED")]
    assert tidy.archive_failed(rows, listed) == {"session_EXAMPLESTUCK"}
    done = {r["id"] for r in rows} - tidy.archive_failed(rows, listed)
    got = _plan([listed[0], listed[1]], done=done)
    assert _gone(got) == {"session_EXAMPLESTUCK"}, got["archive"]
    # A listing cut down to ids and titles says nothing of its state: nothing is judged again.
    bare = [{"id": c["id"], "title": c["title"], "updated_at": c["updated_at"]} for c in listed]
    assert tidy.archive_failed(rows, bare) == set()


# ------------------------------------------------------------------ the old ops chat


OPS = "session_EXAMPLEOPS"


def test_the_old_ops_chat_goes_once_nothing_of_the_search_runs_in_it():
    ops = _chat(OPS, "Job search ops (scheduled routines run here)", "2026-11-01T08:00:00Z",
                made="2026-10-14T08:00:00Z")
    got = _plan([ops], reg={"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": []})
    assert OPS in _gone(got), got["keep"]


def test_the_old_ops_chat_stays_while_the_setup_or_a_paused_task_still_uses_it():
    ops = _chat(OPS, "Job search ops (scheduled routines run here)", "2026-11-01T08:00:00Z",
                made="2026-10-14T08:00:00Z")
    named = {"setup": "ops_relay", "timezone": "Europe/London", "ops_session": {"id": OPS}, "routines": []}
    assert OPS not in _gone(_plan([ops], reg=named))
    paused = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "job_round", "name": "Job search: job round", "trigger_id": "trig_EXAMPLEROUND"}]}
    task = {"id": "trig_EXAMPLEROUND", "name": "Job search: job round", "enabled": False,
            "persistent_session_id": OPS, "cron_expression": "CRON_TZ=Europe/London 52 6 * * 1,4",
            "created_at": "2026-10-14T08:00:00Z"}
    assert OPS not in _gone(_plan([ops], reg=paused, triggers=[task]))


# ------------------------------------------------------------------ the starter's name on the page


def test_a_refused_rename_leaves_the_page_naming_the_starter_as_it_is_called(tmp_path, monkeypatch):
    monkeypatch.setattr(tidy, "_record_path", lambda: str(tmp_path / "tidy.json"))
    sid = "session_EXAMPLESTARTER"
    long_name = computer.OLD_STARTER_TITLES[1]
    tidy._note_renamed({sid: long_name})                          # made
    tidy._note_renamed({sid: computer.STARTER_TITLE}, refused=[sid])   # refused later
    assert tidy.renamed(made=True)[sid] == long_name
    assert computer.starter_title({"chat": sid, "title": computer.OLD_STARTER_TITLE}) == long_name
    # Never asked for again.
    assert tidy.renamed()[sid] == computer.STARTER_TITLE
    rec = json.load(open(tmp_path / "tidy.json", encoding="utf-8"))
    assert sid in rec["rename_refused"]


# ------------------------------------------------------------------ the computer's own chat


def test_the_computers_own_chat_is_never_renamed_from_the_cloud():
    # Its name lives in the Claude app on the computer: a rename from the cloud changed only
    # Claude's side, and the page then named it by a name the person's list did not show
    # (the maintainer, 2026-11-18).
    assert tidy.new_name("session_EXAMPLECOMPUTER", "Job search: on your computer",
                         computer_chat="session_EXAMPLECOMPUTER") == ""


def test_the_computers_own_chat_renames_itself_there_once(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from datetime import timedelta

    from test_a_computer_chat_is_seen_to_its_end import T, _apply, _as
    from test_the_computers_own_chat_takes_work_with_no_tap import LISTENER, _db, _with
    _as(monkeypatch, "computer", tmp_path)
    me = LISTENER["chat"]
    # Made before its name was set (no title on record), or under the name before #289.
    for title in ("", "Job search: on your computer"):
        db = _with(_db(), LISTENER, title=title, kept_at=app_model_stamp(T))
        got = computer.listener_woke(db, me, T, str(tmp_path / ("a" + title[:3])))
        assert got["next"].startswith("rest:"), got["next"]
        assert f"rename this chat to “{computer.LISTENER_TITLE}”" in got["next"], got["next"]
        assert "never the person" in got["next"]
        # Once: the next wake does not ask again.
        woke = _apply(db, got["batches"])
        again = computer.listener_woke(woke, me, T + timedelta(minutes=1), str(tmp_path / "b"))
        assert "rename this chat" not in again["next"], again["next"]
    # Under its name already: never asked.
    db = _with(_db(), LISTENER, title=computer.LISTENER_TITLE, kept_at=app_model_stamp(T))
    assert "rename this chat" not in computer.listener_woke(db, me, T, str(tmp_path / "c"))["next"]


def app_model_stamp(t):
    import app_model
    return app_model.stamp(t)
