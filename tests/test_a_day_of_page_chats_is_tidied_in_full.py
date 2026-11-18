"""A copy's whole chat list after days with no tidy-up is put right by the next one, in full.

The maintainer's chat list on 2026-11-18, after the day's tidy-up had not run since the 16th
(issue #347): three page chats nested one inside the next (today's, yesterday's, which the
person had typed into after it handed the page on, and the day before's under its older
name), the brief's old chat beside the fresh one it moved into that morning, and the
computer's two chats under the names from before #289. Played through `tidy.plan` as the
day's tidy-up runs it in the chat that answers the page: the three old chats go, each with
its work on master; the live page chat, the brief's chat and the computer's two chats stay;
and the computer's two take their new names. Every chat, task and branch here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import computer  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 18)
NOW = dt.datetime(2026, 11, 18, 21, 30, tzinfo=dt.timezone.utc)

LIVE = "session_EXAMPLETODAYSPAGE"
YESTERDAY = "session_EXAMPLEYESTERDAYSPAGE"
DAY_BEFORE = "session_EXAMPLEDAYBEFORESPAGE"
BRIEF_NEW = "session_EXAMPLEBRIEFSOWNCHAT"
BRIEF_OLD = "session_EXAMPLEOLDBRIEFCHAT"
COMPUTER = "session_EXAMPLECOMPUTERCHAT"
STARTER = "session_EXAMPLECOMPUTERSTARTER"

# (id, title, created, last used, its own branch, when that branch's last save was made)
CHATS = [
    (LIVE, tidy.APP_NAME + " · Page", "2026-11-18T16:25:05Z", "2026-11-18T16:28:11Z", "", ""),
    (BRIEF_NEW, routines.BRIEF_CHAT_TITLE, "2026-11-18T08:05:09Z", "2026-11-18T08:06:33Z", "", ""),
    # Handed the page on at 16:25, then typed into by the person until 17:29, its last save
    # landed at 17:23.
    (YESTERDAY, tidy.APP_NAME + " · Page", "2026-11-17T14:14:06Z", "2026-11-18T17:29:35Z",
     "claude/land-yesterday", "2026-11-18T17:23:29Z"),
    (DAY_BEFORE, "Job search page", "2026-11-17T00:29:26Z", "2026-11-17T14:14:33Z",
     "claude/land-day-before", "2026-11-17T14:13:54Z"),
    (COMPUTER, "Job search: on your computer", "2026-11-16T21:54:06Z", "2026-11-17T01:43:54Z", "", ""),
    (BRIEF_OLD, "Job search: morning brief", "2026-11-15T08:13:36Z", "2026-11-18T08:07:01Z",
     "claude/ops-brief", "2026-11-18T08:06:44Z"),
    (STARTER, computer.OLD_STARTER_TITLE, "2026-11-14T08:16:28Z", "2026-11-16T21:57:32Z",
     "claude/land-starter", "2026-11-16T21:55:30Z"),
]
# As a brief's task is stored now: with the line that gets the copy's files first.
BRIEF_PROMPT = routines.with_copy(
    "Scheduled run: morning brief. Run `git fetch origin master`, then read "
    "`automation/prompts/_common.md` and `automation/prompts/morning_brief.md` as they are on "
    "origin/master and follow them exactly.", REPO)


def _stamp(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _plan(monkeypatch):
    chats = [{"id": sid, "title": title, "session_status": "SESSION_STATUS_IDLE",
              "status_bucket": "SESSION_STATUS_BUCKET_COMPLETED", "created_at": made,
              "updated_at": used, "origin": "claude_code_mcp_seed"}
             for sid, title, made, used, _b, _t in CHATS]
    info = {sid: {"id": sid, "title": title, "session_status": "SESSION_STATUS_IDLE",
                  "updated_at": used,
                  "session_context": {} if sid == COMPUTER else {"sources": [
                      {"git_repository": {"url": "https://github.com/" + REPO}}]},
                  "external_metadata": {"current_branches": {"": branch} if branch else {}}}
            for sid, title, _m, used, branch, _t in CHATS}
    branches = {branch for *_, branch, _t in CHATS if branch}
    # Every branch on GitHub and held by master (none unmerged), each with its last save.
    monkeypatch.setattr(tidy, "TIPS", {branch: _stamp(at) for *_, branch, at in CHATS if branch})
    reg = {"setup": "ops_relay", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEBRIEFNOW",
         "cron": "CRON_TZ=Europe/London 0 8 * * *", "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": BRIEF_NEW, "title": routines.BRIEF_CHAT_TITLE, "own": True}}]}
    triggers = [
        {"id": "trig_EXAMPLEBRIEFNOW", "name": routines.BRIEF_NAME, "enabled": True,
         "persistent_session_id": BRIEF_NEW, "cron_expression": "CRON_TZ=Europe/London 0 8 * * *",
         "created_at": "2026-11-18T08:05:18Z", "prompt": BRIEF_PROMPT},
        # The brief's task before it moved, turned off that morning.
        {"id": "trig_EXAMPLEBRIEFBEFORE", "name": routines.BRIEF_NAME, "enabled": False,
         "persistent_session_id": BRIEF_OLD, "cron_expression": "CRON_TZ=Europe/London 0 8 * * *",
         "created_at": "2026-11-15T08:13:45Z", "prompt": BRIEF_PROMPT,
         "last_run": {"fired_at": "2026-11-18T08:01:02Z", "finished_at": "2026-11-18T08:01:02Z"}}]
    triggers = [dict(t, session=t["persistent_session_id"]) for t in triggers]
    listener = {"chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-18T16:25:14Z",
                "answered_at": "2026-11-18T16:26:18Z", "handed_by": YESTERDAY,
                "took_from": YESTERDAY, "took_from_helper": True,
                "helpers": [DAY_BEFORE, YESTERDAY], "title": tidy.APP_NAME + " · Page"}
    return tidy.plan(chats, triggers, info, reg, listener, LIVE, REPO, TODAY, set(), set(), set(),
                     now=NOW, on_github=branches, computer_chat=COMPUTER)


def test_the_old_page_chats_and_the_briefs_old_chat_go_and_the_rest_stay(monkeypatch):
    got = _plan(monkeypatch)
    assert got["ask"] == [], got["ask"]
    gone = {c["id"]: c["why"] for c in got["archive"]}
    assert set(gone) == {YESTERDAY, DAY_BEFORE, BRIEF_OLD}, got["archive"]
    assert gone[BRIEF_OLD] == "the brief moved to a fresh chat of its own"
    assert gone[YESTERDAY] == gone[DAY_BEFORE] == "a helper the page no longer uses"
    kept = {c["id"] for c in got["keep"]}
    assert {LIVE, BRIEF_NEW, COMPUTER, STARTER} <= kept, got["keep"]
    # Nothing about the brief to change: it already runs in its own chat.
    assert got["brief"] == [], got["brief"]


def test_the_computers_two_chats_take_their_new_names(monkeypatch):
    got = _plan(monkeypatch)
    names = {r["id"]: r["to"] for r in got["rename"]}
    assert names == {COMPUTER: computer.LISTENER_TITLE, STARTER: computer.STARTER_TITLE}, \
        got["rename"]
