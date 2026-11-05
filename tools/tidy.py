#!/usr/bin/env python3
"""The app's own old chats, archived by themselves, with nothing lost.

Earlier versions made chats of their own: one for the brief, one for the job round, a helper
replaced by a newer one, a child chat for long work ("Job search: drafts"), and with a
routine, one chat per run. Since 4.3 everything runs in the one chat that answers the page
(the helper), so the rest are clutter (the maintainer, 2026-10-29: "we defo need to do
cleanup for existing installs ... THE USER SHOULD NOT HAVE TO DO ANYTHING"). Once a day that
chat lists the person's chats and scheduled tasks and runs this. It names the chats to
archive (archive_session: the chat is kept, read-only, and unarchive_session brings it back)
and keeps every chat that is:

- not one the app made: its title is not one the app gives its chats, and it is not a helper
  the page recorded as answering before; nor one the person started (list_sessions' origin),
  unless it carries the helper's name, has handed the page on and has not been used for an hour;
- not on this copy (get_session names the copy each chat works on; unknown is kept);
- the chat that answers the page, or this chat;
- bound to a scheduled task that is on (the job round, an older ops chat that relays to the
  phone, which is never rebuilt), or the ops chat itself;
- a campaign chat for a process still live;
- running, or used in the last two days (seven when it is waiting on the person), unless it
  ran one of the app's jobs and every work item it claimed has ended (done, failed or
  stopped) with none still going: a finished job's chat is put away at once, and the tidy-up
  is due again as soon as such a job ends (`due`), so it does not wait for tomorrow; or
  unless it is an old page helper (HELPER_NAME, or the one the live helper took over from):
  only the live one is ever kept, so the helper a hand-over replaced goes at once;
- or holding work that is not on master yet: a branch it pushed that master does not hold.
  The day's update lands such a branch; the chat is archived once it has.

A brief that works stays where it is, and so does its chat (the builder's decision of 3
November: a working brief is never moved, turned off or made again). Only a brief whose chat
no longer works moves into the chat that answers the page: a chat that was deleted, or a
helper the page no longer uses (its renewal archives it). It moves as a task bound to that
chat on the same days and time, the old task turned off (kept, never deleted), and then the
old chat archived. The shortlist moves by the same rule. A brief in the older ops chat moves
the same way only once that chat is gone (not listed, and the task now names the empty chat
it woke instead). Not while the brief is off or resting, never for a routine (each run its
own chat: the run chats are archived, the routine kept). list_sessions never lists a chat a
scheduled task started, so each run's chat is read from list_triggers' last run and
remembered (profile/tidy.json `runs`) until it is old enough to tidy.

    python3 tools/tidy.py due                        exit 0 when today's tidy-up is due
    python3 tools/tidy.py plan --dump <dir> --sessions <file>... --triggers <file>...
                               [--details <file>...] [--chat <id>] [--today YYYY-MM-DD]
    python3 tools/tidy.py done [<session id>...] [--titles <json>]
    python3 tools/tidy.py close <session id> --work <id> --dump <dir> --details <file>
    python3 tools/tidy.py closed <session id>...     once archive_session has taken it
    python3 tools/tidy.py undo                       the calls that bring them all back

`--sessions` takes what list_sessions returned (mine: true), every page; `--triggers` what
list_triggers returned, every page; `--details` what get_session returned for each chat
`plan` asks about. Pure code apart from one `git branch` read; it calls no tool itself.

A big job's chat is closed as soon as it reports back (send_message: "Finished <id>, on
master, in chat <its id>"), not at the next tidy-up: the chat that answers the page reads it
with get_session and runs `close`, which names the archive_session call only for one of the
app's own job chats on this copy whose job has ended and whose work is on master; `closed`
records it with the title it has now. The daily tidy-up stays the way out for a job chat
that never reported.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# The titles the app gives the chats it makes (routines.BRIEF_NAME, the job round, campaign
# chats, child chats of up to three words, and the helpers of every version). A chat the
# person named themself is never one of these unless they copied the app's own words.
# A chat a scheduled task starts carries a mark before its title ("⚡ Job search: morning
# brief"), and without it in the pattern every such chat was read as the person's own and kept.
APP_TITLE = re.compile(r"^(?:[^\w\s]{1,3}\s*)?Job search(?::\s*\S.{0,60}|\s+(?:helper|page)\b.{0,60})$",
                       re.I)
# The page's helper, under its name since 4.10 ("Job search page", app_listen.HELPER_CHAT_TITLE)
# and every older one ("Job search helper", "... (finishing up)"). Only the live one, the chat
# meta/listen names, is kept: the rest are put away as soon as their work is on master, never
# kept for being used lately (the maintainer, 2026-11-04: at most two such chats, the person's
# own and the live page helper; a heavy user's renewals had stacked up several).
HELPER_NAME = re.compile(r"^(?:[^\w\s]{1,3}\s*)?Job search\s+(?:helper|page)\b", re.I)
# Once after the update that brought that rule, the tidy-up is due even if it ran that day,
# so the helpers left over from before are put away by themselves (`due`). Moved on with
# 4.10.1, so the helper a brief was left in is put away, the brief moved first, that same day.
SWEEP = "helpers-2026-11-05"
# A chat the person started (the Claude app, the web, a phone) says so in list_sessions'
# `origin`; every chat the app starts is started by another chat (this origin). One of theirs is
# never put away, unless it carries the helper's name: the chat they set up in answers the page
# first and is named so, and once it has handed the page on it is an old helper like the rest,
# put away once they have not used it for STARTED_QUIET_S (the maintainer, 2026-11-05: "we have
# 3 when we should have 1", two of them "literally identical"; two only during a hand-over).
APP_ORIGINS = ("claude_code_mcp_seed",)
STARTED_QUIET_S = 60 * 60


def person_started(s: dict) -> bool:
    """Did the person start this chat themself? Only where the listing says so."""
    origin = str((s or {}).get("origin") or "")
    return bool(origin) and origin not in APP_ORIGINS
# After a hand-over the helper it replaced is put away at once (`retiring`): asked again at a
# check-in this long after the last try while it still runs or holds work not on master, for
# a day; after that the daily tidy-up has it.
RETIRE_AGAIN_S = 30 * 60
RETIRE_FOR_S = 24 * 3600
# What keeps an old helper only for now: once it has finished, the live helper's own check-in,
# a scheduled one, puts it away. Nothing rang the live helper again, so two "(finishing up)"
# chats stayed until the next morning (the maintainer's live run, 2026-11-05).
FOR_NOW = ("it was in use moments ago", "it is running", "they used it in the last hour",
           "its work is not on master yet", "its work is not on GitHub yet")
RECHECK_MIN = 31
# A check-in can fire after this chat has handed the page on again (seen 18 minutes on): then
# it does nothing, and the chat that answers now tidies what is left at its own take-over
# (`plan` judges every old helper and the brief's binding, not only the last hand-over's).
RECHECK = ("Scheduled check-in, after the hand-over: check in on the page as when it rings "
           "(the app skill) and do the tidy-up it prints, so the helper this chat took the page "
           "over from is put away once it has finished. Ask nobody and say nothing about it. If "
           "the check-in says another chat answers the page, do nothing else: end with the one "
           "line \"Another chat looks after the page now.\"")
# An old helper used this lately is still in use: kept until a later check-in.
RECENT_S = 10 * 60
RUN_TITLE = "⚡ Job search: a scheduled run"
IDLE_DAYS = 2           # quiet this long before it is tidied
WAITING_DAYS = 7        # quiet this long when it was waiting on the person
FILE = "tidy.json"      # in profile/: what was archived, so it can be brought back
CHECKED = "ljs-tidy.json"   # in the git folder, never committed: the day it last ran
# Also in the git folder: the chats `plan` or `close` named to archive, with their titles,
# so `done` and `closed` record the real title without the chat copying it back through the
# shell. Titles once came back only through `--titles '<json>'`, and on 3 November an
# interview prep's chat was recorded with none: the next tidy-up took it for a chat of the
# person's own and brought it back.
PLANNED = "ljs-tidy-planned.json"
SAY_DONE = ("Claude tidied away {n} old chat{s} it no longer used. Nothing in them was lost, "
            "and each can be brought back.")


def _git_dir() -> str:
    import person
    root = person.state()
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _checked_path() -> str:
    d = _git_dir()
    return os.path.join(d, CHECKED) if d else ""


def _planned_path() -> str:
    d = _git_dir()
    return os.path.join(d, PLANNED) if d else ""


def _planned() -> dict:
    """{session id: title} for the chats named to archive and not recorded yet."""
    try:
        with open(_planned_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return {str(k): str(v or "") for k, v in got.items()} if isinstance(got, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _plan_titles(titles: dict, drop=()) -> bool:
    """Keep these titles until `done` or `closed` records them, dropping the ones it has.
    False where there is no git folder to keep them in."""
    path = _planned_path()
    if not path:
        return False
    got = {k: v for k, v in _planned().items() if k not in set(drop)}
    got.update({k: v for k, v in titles.items() if k and v})
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh, ensure_ascii=False)
            fh.write("\n")
    except OSError:
        return False
    return True


def finished_jobs(db: dict, skip: str = "") -> dict:
    """{chat id: when its last job ended} for the chats whose claimed work items have all
    ended (done, failed, stopped) with none still going. `skip` is a chat to leave out (the
    one that answers the page, whose small work ends all day)."""
    import page_db
    held: dict = {}
    for doc in (db.get("work") or {}).values():
        d = doc.get("data") or {}
        who = str(d.get("claimed_by") or "")
        if not who.startswith("session_") or who == skip:
            continue
        ended = str(d.get("status") or "") in page_db.FINISHED
        at = str(d.get("finished_at") or "") if ended else ""
        was = held.get(who, "")
        if not ended or was is None:
            held[who] = None
        elif at > was:
            held[who] = at
    return {k: v for k, v in held.items() if v}


def retiring(listener: dict | None, now: dt.datetime | None = None) -> str:
    """The helper the chat that answers the page took it over from, while it is still to be
    put away: one the app started (never the person's own chat), not recorded as archived yet,
    within a day of the hand-over. "" when there is none."""
    import app_model
    mine = listener or {}
    old = str(mine.get("took_from") or "")
    if not (mine.get("took_from_helper") and old.startswith("session_")
            and old != mine.get("chat")):
        return ""
    if old in {x.get("id") for x in archived()}:
        return ""
    since = app_model.parse_time(mine.get("since"))
    if since is None:
        return ""
    if now is not None and (now - since).total_seconds() >= RETIRE_FOR_S:
        return ""
    return old


def due(today: str = "", db: dict | None = None, skip: str = "",
        listener: dict | None = None, now: dt.datetime | None = None) -> bool:
    """Is a tidy-up still to do? Once a day; once more after the update that put away the
    helpers left over from before (SWEEP); at once after a hand-over, and again every
    RETIRE_AGAIN_S for a day while the helper it replaced is still there (given `now`); and
    when another chat's job has ended since the last one (`db`: the page's records), so its
    chat is put away soon after, not at tomorrow's. Never where it cannot be kept."""
    today = today or dt.date.today().isoformat()
    path = _checked_path()
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh) or {}
    except (OSError, ValueError, AttributeError):
        return True
    if got.get("checked") != today or got.get("sweep") != SWEEP:
        return True
    if db is None:
        return False
    import app_model
    last = app_model.parse_time(got.get("at"))
    if last is None:
        return False
    gone = {x.get("id") for x in archived()}
    # A hand-over to a fresh helper: the app's own old one is put away now, not tomorrow and
    # not two quiet days on (its work and brief are judged by plan as ever). Still running, or
    # its work not on master yet: asked again at a check-in half an hour on.
    mine = listener or {}
    since = app_model.parse_time(mine.get("since"))
    if retiring(mine, now) and since is not None and (
            since > last or (now is not None and (now - last).total_seconds() >= RETIRE_AGAIN_S)):
        return True
    for chat, at in finished_jobs(db, skip).items():
        t = app_model.parse_time(at)
        if chat not in gone and t is not None and t > last:
            return True
    return False


def _mark_checked(today: str, now: str = "") -> None:
    path = _checked_path()
    if not path:
        return
    at = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = {k: v for k, v in _checked().items() if k == "recheck"}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"checked": today, "at": at, "sweep": SWEEP, **keep}, fh)
        fh.write("\n")


def _checked() -> dict:
    path = _checked_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def recheck_due(now: dt.datetime) -> bool:
    """No check-in asked for in the last half hour: one at a time, never a pile of them."""
    import app_model
    last = app_model.parse_time(_checked().get("recheck"))
    return last is None or (now - last).total_seconds() >= RETIRE_AGAIN_S - 60


def mark_recheck(now: dt.datetime) -> None:
    path = _checked_path()
    if not path:
        return
    got = _checked()
    got["recheck"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh)
        fh.write("\n")


def _record_path() -> str:
    import person
    return person.path(FILE)


def archived() -> list[dict]:
    """The chats tidied away so far: [{id, title, on, why}], oldest first."""
    try:
        with open(_record_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return [a for a in got.get("archived") or [] if isinstance(a, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def _is_apps(title) -> bool:
    return bool(APP_TITLE.match(str(title or "").strip()))


def strangers(records: list[dict], live: dict) -> list[dict]:
    """The chats an earlier tidy-up put away that are the person's own (the stranger audit,
    X-4), to bring back once. `live` is {id: title} from today's list_sessions. One the app
    made is never among them, by its title now or the one stored: an empty stored title is
    not evidence of anything (3 November: an interview prep's chat recorded with no title was
    taken for the person's own and brought back)."""
    out = []
    for x in records:
        sid = str(x.get("id") or "")
        if not sid or x.get("restored"):
            continue
        stored, now = str(x.get("title") or "").strip(), str(live.get(sid) or "").strip()
        if _is_apps(stored) or _is_apps(now) or not (stored or now):
            continue
        out.append(x)
    return out


def brought_back_by_mistake(records: list[dict], live: dict) -> set[str]:
    """The app's own chats an older tidy-up brought back for having no stored title: listed
    again today under one of the app's titles. They are judged afresh like any other chat, so
    a finished one is put away again (and recorded, this time, with its title)."""
    return {str(x.get("id")) for x in records
            if x.get("id") and x.get("restored") and not str(x.get("title") or "").strip()
            and _is_apps(live.get(x.get("id")))}


# ------------------------------------------------------------------ reading what the tools gave


def _pages(paths) -> list:
    out = []
    for p in paths or []:
        with open(p, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _given(a) -> dict:
    """What the chat passed on standard input with --stdin: one JSON object holding what
    list_sessions, list_triggers and get_session returned, as they returned it
    ({"sessions": ..., "triggers": ..., "details": ...}; each a whole result, a list of
    results, or a bare list). The chat had typed each listing into a file by hand first (the
    maintainer's copy, 2026-11-05): one heredoc is one step, and no file."""
    if not getattr(a, "stdin", False):
        return {}
    raw = sys.stdin.read()
    try:
        got = json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise SystemExit("tidy: what was given on standard input is not JSON: pass "
                         "{\"sessions\": <list_sessions' result>, \"triggers\": "
                         "<list_triggers' result>} as the tools returned them") from None
    return got if isinstance(got, dict) else {}


def _as_pages(value) -> list:
    """One result, several pages of one, or a bare list, as a list of pages."""
    if value is None:
        return []
    if isinstance(value, list) and value and all(
            isinstance(v, dict) and any(k in v for k in ("data", "ccr", "triggers"))
            for v in value):
        return value
    return [value]


def sessions(pages) -> list[dict]:
    """Every chat in list_sessions' pages ({"ccr": {"data": [...]}} or {"data": [...]})."""
    out = []
    for got in pages:
        if isinstance(got, dict):
            got = got.get("ccr", got)
            got = got.get("data", []) if isinstance(got, dict) else got
        for s in got or []:
            if isinstance(s, dict) and str(s.get("id") or "").startswith("session_"):
                out.append(s)
    return out


def details(pages) -> dict:
    """{session id: get_session's record}."""
    out = {}
    for got in pages:
        if isinstance(got, dict):
            got = got.get("ccr", got)
        if isinstance(got, dict) and got.get("id"):
            out[got["id"]] = got
    return out


def _repo_of(d: dict) -> str:
    for src in ((d.get("session_context") or {}).get("sources") or []):
        url = str(((src or {}).get("git_repository") or {}).get("url") or "")
        m = re.search(r"github\.com[/:]([^/]+/[^/.]+)", url)
        if m:
            return m.group(1).lower()
    return ""


def _branches_of(d: dict) -> list[str]:
    out = []
    for o in ((d.get("session_context") or {}).get("outcomes") or []):
        out += list((((o or {}).get("git_repository") or {}).get("git_info") or {})
                    .get("branches") or [])
    cur = ((d.get("external_metadata") or {}).get("current_branches") or {})
    out += [b for b in cur.values() if b]
    return sorted({b for b in out if b and b not in ("master", "main")})


def unmerged() -> set[str] | None:
    """Branches on GitHub that master does not hold, or None when git cannot say (then every
    chat with a branch of its own is kept)."""
    import person
    root = person.state()
    try:
        subprocess.run(["git", "-C", root, "fetch", "--quiet", "origin"], capture_output=True,
                       text=True, encoding="utf-8", timeout=120)
        r = subprocess.run(["git", "-C", root, "branch", "-r", "--no-merged", "origin/master",
                            "--format=%(refname:short)"], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {ln.strip().removeprefix("origin/") for ln in r.stdout.splitlines() if ln.strip()}


def _status(s: dict, d: dict | None) -> str:
    """What the sessions list and get_session say of a chat's state, in small letters: the
    list's `session_status` and `status_bucket`, and the plain `status` a trimmed listing or
    get_session gives ("running", "working"). A live run read only `session_status` and took
    a helper get_session called running for an idle one (2026-11-05)."""
    out = []
    for rec in (s or {}, d or {}):
        for k in ("session_status", "status", "status_bucket"):
            if rec.get(k):
                out.append(str(rec[k]))
    return " ".join(out).lower()


def _running(status: str) -> bool:
    return "running" in status or "working" in status


def _last_used(s: dict, d: dict | None) -> str:
    """The latest time either record gives for the chat's last use."""
    import app_model
    best, got = None, ""
    for rec in (s or {}, d or {}):
        for k in ("updated_at", "last_activity_at", "last_event_at"):
            t = app_model.parse_time(rec.get(k))
            if t is not None and (best is None or t > best):
                best, got = t, str(rec.get(k))
    return got or str((s or {}).get("created_at") or "")


def _ago_s(stamp, now: dt.datetime) -> float:
    """Seconds since `stamp`; unknown counts as long ago."""
    import app_model
    t = app_model.parse_time(stamp)
    return float("inf") if t is None else (now - t).total_seconds()


def _after(stamp, since) -> bool:
    """Is `stamp` later than `since`? False when either cannot be read."""
    import app_model
    a, b = app_model.parse_time(stamp), app_model.parse_time(since)
    return a is not None and b is not None and a > b


def on_github() -> set[str] | None:
    """Every branch GitHub holds for this copy, as the last fetch saw it (unmerged() fetches
    first), or None when git cannot say."""
    import person
    try:
        r = subprocess.run(["git", "-C", person.state(), "branch", "-r",
                            "--format=%(refname:short)"], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {ln.strip().removeprefix("origin/") for ln in r.stdout.splitlines() if ln.strip()}


def _days_since(stamp: str, today: dt.date) -> float:
    try:
        at = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    now = dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    return (now - at).total_seconds() / 86400


# ------------------------------------------------------------------ the decision


def plan(chats: list[dict], triggers: list[dict], info: dict, reg: dict, listener: dict,
         this_chat: str, repo: str, today: dt.date, campaigns: set[str],
         branches: set[str] | None, done_before: set[str],
         jobs: dict | None = None, now: dt.datetime | None = None,
         on_github: set[str] | None = None) -> dict:
    """{"ask": [ids to read with get_session], "archive": [{id, title, why}],
    "keep": [{id, title, why}], "brief": [calls] or []}. `jobs` is finished_jobs(): a chat in
    it is not kept for being used lately. `now` (else noon of `today`) times recent use;
    `on_github`, every branch GitHub holds, tells a branch never pushed from one merged."""
    jobs = jobs or {}
    import routines
    now = now or dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    live_ids = {listener.get("chat") or "", this_chat} - {""}
    # The chat the page was taken from is put away only where the app started it: one the
    # person writes in, whatever its title, is theirs (the stranger audit, X-4).
    known = ({listener.get("took_from") or ""} - {""}) if listener.get("took_from_helper") else set()
    # Every task that is on, by the chat it fires into (a one-time reminder as much as the
    # brief): a chat a live task fires into is never archived, only one whose every such task
    # this same plan moves away (the maintainer's live run, 2026-11-05: two one-time tasks
    # fired into a helper the tidy-up named for archiving).
    fires: dict = {}
    for t in triggers:
        sid = str(t.get("session") or t.get("persistent_session_id") or "")
        if sid and t.get("enabled") is not False:
            fires.setdefault(sid, set()).add(str(t.get("id") or ""))
    ops = str((reg.get("ops_session") or {}).get("id") or "")
    brief = next((r for r in reg.get("routines") or [] if routines._is_brief(r)), None) or {}
    brief_chat = str((brief.get("chat") or {}).get("session_id") or "")
    out: dict = {"ask": [], "archive": [], "keep": [], "brief": []}

    # A brief stays where it works (the builder's decision, 2026-11-03: a working brief is
    # never moved, turned off or made again). It moves into the chat that answers the page
    # only when the chat it is bound to no longer works: deleted (not among the person's
    # chats), or a helper the page no longer uses, which its renewal archives. A brief in the
    # older ops chat stays there while that chat lives (it relays to the phone); once the
    # chat is gone, the task wakes a new empty chat with no copy of the files every morning
    # ("Morning brief could not start: no git repo", 2026-10-31), so it moves too. The job
    # round moves by the same rule, so the chat it runs in is never archived under it (X-50).
    adopt = ""
    helper = listener.get("chat") or ""
    setup = routines.setup_of(reg)
    home = brief_chat or (ops if setup == "ops_relay" else "")
    listed_ids = {s.get("id") for s in chats}
    titles = {s.get("id"): str(s.get("title") or "") for s in chats}
    # The page's old helpers: every chat under a helper's name but the live one, and the one
    # it took the page from. Never the person's own chat the page was taken from, whatever
    # its title (X-4): a record that says so (one from before the flag says nothing).
    theirs = str(listener.get("took_from") or "") if listener.get("took_from_helper") is False else ""
    started = {s.get("id") for s in chats if person_started(s)}
    started_helpers = {sid for sid in started if HELPER_NAME.match(titles.get(sid, "").strip())}
    mine_only = started - started_helpers             # theirs, never a helper: never listed
    old_helpers = ({sid for sid, t in titles.items() if HELPER_NAME.match(t.strip())} | known) \
        - live_ids - mine_only - {theirs, ""}

    def retired(sid: str) -> bool:
        return bool(sid) and sid != helper and (
            sid not in listed_ids or sid in known or sid in old_helpers
            or bool(re.search(r"\bhelper\b", titles.get(sid, ""), re.I)))

    def old_helper(sid: str) -> bool:
        """One of the app's helpers the page no longer uses, this chat included."""
        return bool(sid) and sid != helper and sid not in mine_only and sid != theirs and (
            sid in known or bool(HELPER_NAME.match(titles.get(sid, "").strip())))

    # Where the brief runs is where its task fires: a registry that names no chat, or the ops
    # chat, while the task wakes an old helper (the maintainer's live run, 2026-11-05: a brief
    # remade in the helper a hand-over had just replaced) kept that helper for good.
    live_brief = next((t for t in triggers if brief.get("trigger_id")
                       and t.get("id") == brief.get("trigger_id")), None) or {}
    fired_in = str(live_brief.get("session") or live_brief.get("persistent_session_id") or "")
    if fired_in and fired_in != home and fired_in in listed_ids and old_helper(fired_in):
        home = fired_in

    if (setup in ("chat_per_briefing", "ops_relay") and home and helper.startswith("session_")
            and home != helper and not brief.get("off") and not reg.get("pause")
            and brief.get("trigger_id") and brief.get("cron")):
        live = next((t for t in triggers if t.get("id") == brief["trigger_id"]), None)
        # Gone, for the ops chat: not among the person's chats, and the task itself now
        # names another chat, one that works on no copy at all (the empty one it woke
        # instead). All three, so a listing that missed a page never moves a brief whose ops
        # chat still relays, and a brief someone bound to a chat of their own stays there.
        woke = str((live or {}).get("session") or "")
        gone = False
        if home == ops and home not in listed_ids and woke not in ("", home, helper):
            if woke not in listed_ids:
                gone = True
            elif woke not in info:
                out["ask"].append(woke)
            else:
                gone = not _repo_of(info[woke])
        if live and live.get("enabled") and ((home != ops and retired(home)) or gone):
            adopt = home
            stub = routines.with_copy(routines.stub(reg, brief["key"], own_chat=True), repo)
            out["brief"] = [
                {"tool": "create_trigger", "args": {
                    "name": routines.BRIEF_NAME, "persistent_session_id": helper,
                    "cron_expression": brief["cron"], "prompt": stub,
                    "initiation": "own_initiative"},
                 "why": "the brief runs in the chat that answers the page from now on"},
                {"run": f"python3 tools/routines.py record --session {helper} --trigger "
                        f"<the new task's id> --cron \"{brief['cron']}\""
                        + (" --own-chat" if setup == "ops_relay" else ""),
                 "why": "the registry names the new task and its chat"},
                ({"tool": "delete_trigger", "args": {"trigger_id": brief["trigger_id"]},
                  "why": "the copy made for the helper this one replaced: one a day piled up "
                         "turned off in their list of scheduled tasks"}
                 if home == (listener.get("took_from") or "") and home != ops else
                 {"tool": "update_trigger", "args": {"trigger_id": brief["trigger_id"],
                                                     "enabled": False},
                  "why": "the old task is turned off, never deleted"})]

    moved_from = {adopt} - {""}
    out["moves"] = []
    rnd = next((r for r in routines.work(reg) if r.get("key") == "job_round"), None) or {}
    rchat = str((rnd.get("chat") or {}).get("session_id") or "")
    if (rnd.get("trigger_id") and rnd.get("cron") and not rnd.get("paused") and rchat
            and setup == "chat_per_briefing" and helper.startswith("session_")
            and not reg.get("pause") and retired(rchat)):
        live = next((t for t in triggers if t.get("id") == rnd["trigger_id"]), None)
        if live and live.get("enabled"):
            moved_from.add(rchat)
            out["moves"] = [
                {"tool": "create_trigger", "args": {
                    "name": rnd.get("name") or "Job search: shortlist",
                    "persistent_session_id": helper, "cron_expression": rnd["cron"],
                    "prompt": routines.with_copy(routines.stub(reg, "job_round", own_chat=True), repo),
                    "initiation": "own_initiative"},
                 "why": "the shortlist runs in the chat that answers the page from now on"},
                {"run": f"python3 tools/routines.py rebind job_round --session {helper} "
                        f"--trigger <the new task's id>",
                 "why": "the registry names the new task and its chat"},
                ({"tool": "delete_trigger", "args": {"trigger_id": rnd["trigger_id"]},
                  "why": "the copy made for the helper this one replaced"}
                 if rchat in known else
                 {"tool": "update_trigger", "args": {"trigger_id": rnd["trigger_id"],
                                                     "enabled": False},
                  "why": "the old task is turned off, never deleted"})]

    if adopt and adopt not in {s.get("id") for s in chats}:
        # Its chat was deleted: the task fails every morning, so it moves to the helper, and
        # there is nothing to archive.
        out["keep"].append({"id": adopt, "title": "", "why": "the brief's chat is gone; the "
                                                            "brief moves to the helper"})
    # The daily upkeep moves to the helper in this same run (made there, then the old one
    # deleted), so the chat it was bound to is not kept for it.
    up_calls = _upkeep_calls(reg, triggers, helper, listener, repo)
    up = routines.upkeep_entry(reg) or {}
    up_moves = bool(up.get("trigger_id")) and any(
        c.get("tool") == "delete_trigger" and c["args"].get("trigger_id") == up["trigger_id"]
        for c in up_calls)
    if up_moves:
        moved_from |= {str((up.get("chat") or {}).get("session_id") or "")} - {"", helper}
    # The tasks this plan moves away from their chats: only these stop keeping a chat.
    moving = ({brief.get("trigger_id")} if adopt and out["brief"] else set()) | \
        ({rnd.get("trigger_id")} if out["moves"] else set()) | \
        ({up.get("trigger_id")} if up_moves else set())
    moving -= {None, ""}
    for s in chats:
        sid = s.get("id") or ""
        title = str(s.get("title") or "")
        def keep(why, sid=sid, title=title):
            out["keep"].append({"id": sid, "title": title, "why": why})
        if sid in done_before:
            continue
        if not (APP_TITLE.match(title) or sid in known) or sid == theirs or sid in mine_only:
            continue                                  # the person's own chat: never listed
        if sid in live_ids:
            keep("it answers the page" if sid == listener.get("chat") else "it is this chat")
            continue
        if sid == ops:
            keep("the older ops chat, which relays to the phone and is never rebuilt")
            continue
        if fires.get(sid, set()) - moving:
            keep("a scheduled task that is on runs in it")
            continue
        if sid in campaigns:
            keep("a live process has its own chat here")
            continue
        if sid in old_helpers and sid not in known and _after(s.get("created_at"),
                                                               listener.get("since")):
            # Started since the live helper took the page: a fresh one its renewal asked for,
            # which may yet take it. Every helper from before was started earlier.
            keep("a helper started since this one took the page, which may yet take it")
            continue
        if sid == brief_chat and sid != adopt and brief.get("trigger_id") and sid in old_helpers:
            # Turned off or resting, the brief does not move (a working brief never does by
            # itself either): its chat is kept, so it never comes back on in an archived one.
            keep("the brief, turned off or resting, is bound to it")
            continue
        d = info.get(sid)
        status = _status(s, d)
        if _running(status):
            keep("it is running")
            continue
        last = _last_used(s, d)
        quiet = _days_since(last, today)
        waits = "requires_action" in status or "blocked" in status
        if sid in old_helpers and waits:
            keep("it is waiting on the person")
            continue
        if sid in old_helpers and _ago_s(last, now) < RECENT_S:
            # An old helper is not kept for two quiet days (its renewal used it minutes before
            # a hand-over), but never put away while it is still in use. Used moments ago, it
            # is read first, and one get_session calls idle is put away now: kept for a later
            # check-in, two helpers stayed for half an hour after every hand-over, and a
            # third came (the maintainer's copy, 2026-11-05).
            if d is None:
                out["ask"].append(sid)
                continue
            if not _status(None, d):
                keep("it was in use moments ago")
                continue
        if sid in started_helpers and _ago_s(last, now) < STARTED_QUIET_S:
            keep("they used it in the last hour")
            continue
        if (sid not in moved_from and sid not in jobs and sid not in old_helpers
                and quiet < (WAITING_DAYS if waits else IDLE_DAYS)):
            keep(f"used {quiet:.0f} day(s) ago")
            continue
        if d is None:
            out["ask"].append(sid)
            continue
        where = _repo_of(d)
        if not where or where != repo.lower():
            keep("it works on another copy" if where else "its copy is not known")
            continue
        own = _branches_of(d)
        if own and branches is None:
            keep("git could not say whether its work is on master")
            continue
        left = [b for b in own if branches is not None and b in branches]
        if left:
            keep("its work is not on master yet (" + ", ".join(left) + ")")
            continue
        # A branch GitHub has never held: its work may be only where that chat ran (a chat
        # on the person's computer). Merged branches stay on GitHub (land.py never deletes
        # them), so lately it is kept; one quiet for days is put away as before.
        local = [b for b in own if on_github is not None and b not in on_github]
        if local and quiet < IDLE_DAYS:
            keep("its work is not on GitHub yet (" + ", ".join(local) + ")")
            continue
        why = ("the brief moved into the chat that answers the page" if sid == adopt else
               "the shortlist moved into the chat that answers the page" if sid in moved_from else
               "a helper the page no longer uses" if sid in old_helpers or sid in known
               or re.search(r"helper", title, re.I)
               else "a chat for one run or one job, finished")
        out["archive"].append({"id": sid, "title": title, "why": why})
    listed = {s.get("id") for s in chats}
    if adopt and adopt in listed and not any(a["id"] == adopt for a in out["archive"]) \
            and not old_helper(adopt):
        # Its chat is kept: the brief stays put. Never where it is an old helper, kept only
        # until it finishes: the brief moves into the live helper in this same pass. Left
        # there, the plan said "nothing to tidy" and the brief waited half an hour for a
        # check-in in the helper being put away (the maintainer's copy, 2026-11-05).
        out["brief"] = []
    if rchat in moved_from and rchat in listed and not any(a["id"] == rchat for a in out["archive"]):
        out["moves"] = []                             # its chat is kept: the round stays put
    out["ask"] = list(dict.fromkeys(out["ask"]))
    # Run by the live helper within a day of its hand-over, with an old helper kept only for
    # now: it asks for its own check-in, as nothing else may ring it before tomorrow's brief.
    took = _after(now.strftime("%Y-%m-%dT%H:%M:%SZ"), listener.get("since")) and \
        _ago_s(listener.get("since"), now) < RETIRE_FOR_S
    out["recheck"] = bool(this_chat and this_chat == helper and took and not out["ask"] and any(
        k["id"] in old_helpers and k["why"].startswith(FOR_NOW) for k in out["keep"]))
    if out["ask"]:
        out["brief"] = []                             # decided once every chat is read
        out["moves"] = []
    out["upkeep"] = [] if out["ask"] else up_calls
    # A brief that stays where it is, stored before its prompt said how to get a copy of the
    # files, is given that line, so it runs in whichever chat it lands in (routines.with_copy;
    # two days of no brief, 2026-10-31). Once: the line it gets is how it is found next time.
    if not out["brief"] and not out["ask"] and brief.get("trigger_id") and not reg.get("pause"):
        live = next((t for t in triggers if t.get("id") == brief["trigger_id"]), None)
        prompt = str((live or {}).get("prompt") or "")
        fixed = routines.with_copy(prompt, repo)
        if live and live.get("enabled") and routines._is_brief_prompt(prompt) and fixed != prompt:
            out["brief"] = [{"tool": "update_trigger", "args": {"trigger_id": brief["trigger_id"],
                                                                "prompt": fixed},
                             "why": "the brief runs in any chat it lands in, getting the files "
                                    "first where they are missing"}]
    # Every other task of the app's that is on gets the same line (the job round, a welcome-back
    # brief), unless it is moving or the day's listing is still being read (X-43).
    skip = {brief.get("trigger_id")} | ({rnd.get("trigger_id")} if out["moves"] else set())
    out["mend"] = [] if out["ask"] else [
        c for c in routines.mend(triggers, repo) if c["args"]["trigger_id"] not in skip]
    return out


def _upkeep_calls(reg: dict, triggers: list[dict], helper: str, listener: dict,
                  repo: str) -> list[dict]:
    """The calls that keep the daily upkeep right (tools/routines.py "the daily upkeep"):
    made where nothing else keeps the copy and the page current every day, bound to the chat
    that answers the page and moved with it as it renews (the copy for the chat it replaced
    deleted, not piled up), and taken away once a daily brief does the same."""
    import routines
    up = routines.upkeep_entry(reg)
    live = next((t for t in triggers if up and t.get("id") == up.get("trigger_id")), None)
    if not routines.needs_upkeep(reg):
        if not up:
            return []
        return ([{"tool": "delete_trigger", "args": {"trigger_id": up["trigger_id"]},
                  "why": "the brief now runs every day and does the same"}] if live else []) + \
               [{"run": "python3 tools/routines.py upkeep-forget",
                 "why": "the registry no longer names it"}]
    if not helper.startswith("session_"):
        return []
    bound = str(((up or {}).get("chat") or {}).get("session_id") or "")
    # Only on the days the brief does not run (X-38): one made before that is corrected here.
    want = routines.upkeep_cron(reg)
    if up and live and live.get("enabled") is not False and bound == helper:
        if want and up.get("cron") and up["cron"] != want:
            return [{"tool": "update_trigger", "args": {"trigger_id": up["trigger_id"],
                                                        "cron_expression": want},
                     "why": "it runs only on the days the brief does not"},
                    {"run": f"python3 tools/routines.py upkeep-record --session {helper} --trigger "
                            f"{up['trigger_id']} --cron \"{want}\"",
                     "why": "the registry names its days"}]
        return []
    cron = want or (up or {}).get("cron")
    if not cron:
        return []
    out = [{"tool": "create_trigger", "args": {
               "name": routines.UPKEEP_NAME, "persistent_session_id": helper,
               "cron_expression": cron, "prompt": routines.upkeep_stub(repo),
               "initiation": "own_initiative"},
            "why": "once a day, silently, the copy and the page kept current"},
           {"run": f"python3 tools/routines.py upkeep-record --session {helper} --trigger "
                   f"<the new task's id> --cron \"{cron}\"",
            "why": "the registry names the task and its chat"}]
    if live:
        out.append({"tool": "delete_trigger", "args": {"trigger_id": live["id"]},
                    "why": "the copy made for the chat this one replaced"})
    return out


def _listener(dump: str) -> dict:
    """The chat that answers the page: from this wake's dump, else what this checkout last
    saw (the brief's run has no dump).

    A folder read before this chat's own check-in took the page holds the chat it took the
    page from: the start steps reuse that folder, and the first tidy-up bound the brief to the
    helper just replaced and deleted the task (the maintainer's copy, 2026-11-05). What this
    checkout wrote at that check-in (app_listen._remember) is newer, so it wins here."""
    import app_listen
    seen = dict(app_listen.seen().get("listener") or {})
    if dump:
        import page_db
        try:
            rec, _ = app_listen.record(page_db.load(dump))
        except Exception:  # noqa: BLE001  not a dump: what was seen
            rec = {}
        if rec:
            return seen if _newer(seen, rec) else rec
    return seen


def _newer(seen: dict, rec: dict) -> bool:
    """Is what this checkout saw a later hand-over than the record in the folder? Only a
    different chat that took the page after the folder's own did, with the hand-over's
    fields kept (a record from before they were kept is never trusted over the folder)."""
    import app_model
    if not seen.get("chat") or seen.get("chat") == rec.get("chat") or "took_from" not in seen:
        return False
    mine, theirs = app_model.parse_time(seen.get("since")), app_model.parse_time(rec.get("since"))
    return mine is not None and (theirs is None or mine > theirs)


def _campaign_chats() -> set[str]:
    try:
        import csv_store
        import open_actions
        import person
        rows = csv_store.read_rows(person.state("job_search_tracker.csv"))
        return set(open_actions.campaigns(rows).values())
    except Exception:  # noqa: BLE001  no tracker yet: no campaign
        return set()


def _repo() -> str:
    import place
    owner, name = place.repo()
    return f"{owner}/{name}" if owner and name else ""


def run_chats(tasks: list[dict], remembered: dict, done_before: set[str],
              listed: set[str]) -> tuple[dict, list[dict]]:
    """The chats the app's scheduled tasks started, one a run (a Routines-screen task, a
    relay): list_sessions never lists a chat a scheduled task started, and list_triggers names
    only each task's latest run, so each run's chat is remembered here (profile/tidy.json
    `runs`) until it is old enough to tidy. Returns (what to remember, chats to judge)."""
    import routines
    runs = {k: v for k, v in (remembered or {}).items() if k not in done_before}
    for t in tasks:
        last = t.get("last_run") or {}
        sid = str(last.get("session_id") or "")
        if (sid.startswith("session_") and not t.get("session")
                and routines._is_app_prompt(t.get("prompt"))):
            runs.setdefault(sid, str(last.get("fired_at") or last.get("finished_at") or ""))
    chats = [{"id": sid, "title": RUN_TITLE, "created_at": at, "updated_at": at}
             for sid, at in sorted(runs.items()) if sid not in listed and at]
    return runs, chats


def _remembered_runs() -> dict:
    try:
        with open(_record_path(), encoding="utf-8") as fh:
            got = json.load(fh).get("runs") or {}
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _remember_runs(runs: dict) -> None:
    path = _record_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    if (got.get("runs") or {}) == runs:
        return
    got["runs"] = runs
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def run_plan(a) -> int:
    import routines
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    given = _given(a)
    tasks: list = []
    for page in _pages(a.triggers) + _as_pages(given.get("triggers")):
        tasks += routines.listing(page)[0]
    try:
        reg = routines.load()
    except Exception:  # noqa: BLE001  no registry: no brief, no ops chat
        reg = {}
    # A chat of the person's own that an earlier tidy-up put away because a helper had taken
    # the page from it (the stranger audit, X-4): brought back once, before anything else.
    # Judged by the title it has now as well as the one stored, never by a missing one.
    listed = sessions(_pages(a.sessions) + _as_pages(given.get("sessions")))
    live = {s.get("id"): str(s.get("title") or "") for s in listed}
    records = archived()
    wrong = strangers(records, live)
    for x in wrong:
        print(f"restore {x['id']}: unarchive_session {json.dumps({'session_id': x['id']})} "
              f"({x.get('title') or 'a chat'}: a chat of the person's own, put away by mistake "
              "before; say nothing about it)")
    if wrong:
        _mark_restored([x["id"] for x in wrong])
    import app_listen
    listener = _listener(a.dump)
    if not listener.get("chat"):
        # Without knowing which chat answers the page, the helper itself could look idle.
        print("tidy: the chat that answers the page is not known here, so nothing is tidied "
              "today. python3 tools/tidy.py done")
        return 0
    repo = _repo()
    if not repo:
        print("tidy: this copy's address is not known, so nothing is tidied today. "
              "python3 tools/tidy.py done")
        return 0
    done = {x["id"] for x in archived()} - brought_back_by_mistake(records, live)
    runs, extra = run_chats(tasks, _remembered_runs(), done, {s.get("id") for s in listed})
    _remember_runs(runs)
    jobs: dict = {}
    if a.dump:
        try:
            import page_db
            jobs = finished_jobs(page_db.load(a.dump), listener.get("chat") or "")
        except Exception:  # noqa: BLE001  not a dump: no finished jobs known, the days rule holds
            jobs = {}
    import app_model
    now = app_model.parse_time(a.now) if a.now else None
    if now is None and not a.today:
        now = dt.datetime.now(dt.timezone.utc)
    elif now is not None and not a.today:
        today = now.date()
    me = app_listen.this_chat(a.chat)
    got = plan(listed + extra, tasks,
               details(_pages(a.details) + _as_pages(given.get("details"))), reg,
               listener, me, repo, today,
               _campaign_chats(), unmerged(), done, jobs, now=now, on_github=on_github())
    if got["ask"]:
        print("tidy: read these chats first, each with get_session, and run this again with "
              "what each returned under \"details\" in the same standard input (or --details "
              "<each file>): " + " ".join(got["ask"]))
        return 0
    for i, c in enumerate(got["brief"], 1):
        if c.get("tool"):
            print(f"brief {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
        else:
            print(f"brief {i}: {c['run']} ({c['why']})")
    for i, c in enumerate(got.get("upkeep") or [], 1):
        if c.get("tool"):
            print(f"upkeep {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
        else:
            print(f"upkeep {i}: {c['run']} ({c['why']})")
    for i, c in enumerate(got.get("moves") or [], 1):
        if c.get("tool"):
            print(f"shortlist {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
        else:
            print(f"shortlist {i}: {c['run']} ({c['why']})")
    if got.get("moves"):
        print("shortlist: make these in order and stop at the first that fails; say nothing about it")
    for i, c in enumerate(got.get("mend") or [], 1):
        print(f"mend {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
    if got.get("mend"):
        print("mend: make these, then python3 tools/routines.py mended; say nothing about it")
    if got.get("upkeep"):
        print("upkeep: make these in order and stop at the first that fails; say nothing about it")
    if len(got["brief"]) > 1:
        print("brief: make these in order and stop at the first that fails; archive the old "
              "brief's chat only once all three are made")
    elif got["brief"]:
        print("brief: make this call, then carry on")
    for c in got["archive"]:
        print(f"archive {c['id']}: {c['title']} ({c['why']})")
    if got["archive"]:
        ids = " ".join(c["id"] for c in got["archive"])
        titles = {c["id"]: c["title"] for c in got["archive"]}
        # Kept here, so `done` records each real title from the ids alone: a title copied back
        # through the shell was lost (an apostrophe in an employer's name ends the quoting).
        kept = _plan_titles(titles)
        more = "" if kept else f" --titles '{json.dumps(titles, ensure_ascii=False)}'"
        print(f"then: archive_session each, and python3 tools/tidy.py done <each one archived>"
              f"{more} (all of them: {ids}); commit it")
        # One refused (still finishing its last turn, most often) is tried again by a check-in,
        # never handed to the person: the live helper told them "you can archive it yourself"
        # (the maintainer's live run, 2026-11-05).
        print("then: an archive_session that is refused is left as it is, never mentioned and "
              "never asked of the person; " + (
                  f"if one is, send_later {json.dumps({'delay_minutes': RECHECK_MIN, 'message': RECHECK})} "
                  "once, and that check-in tries again"
                  if me and me == listener.get("chat") else "the next tidy-up tries again"))
    else:
        print("tidy: nothing to tidy. python3 tools/tidy.py done")
    stamp = now or dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    if got.get("recheck") and recheck_due(stamp):
        mark_recheck(stamp)
        print(f"check-in: send_later {json.dumps({'delay_minutes': RECHECK_MIN, 'message': RECHECK})} "
              "(once, asking nobody; the helper this chat took over from is still finishing, and "
              "it is put away at that check-in)")
    if a.verbose:
        for c in got["keep"]:
            print(f"keep {c['id']}: {c['title']} ({c['why']})")
    return 0


def _mark_restored(ids: list[str]) -> None:
    path = _record_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return
    for a in got.get("archived") or []:
        if isinstance(a, dict) and a.get("id") in ids:
            a["restored"] = True
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _record(ids: list[str], titles: dict, today: str) -> None:
    """Write the archived chats into profile/tidy.json, each with its real title: the one
    given, else the one `plan` or `close` kept. One brought back by mistake before is put
    away again under its old entry, its title filled in."""
    planned = _planned()
    path = _record_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    rows = [a for a in got.get("archived") or [] if isinstance(a, dict)]
    by_id = {a.get("id"): a for a in rows}
    for i in dict.fromkeys(ids):
        title = str(titles.get(i) or planned.get(i) or "")
        row = by_id.get(i)
        if row is None:
            rows.append({"id": i, "title": title, "on": today})
            by_id[i] = rows[-1]
            continue
        if row.get("restored"):
            row.pop("restored", None)
            row["on"] = today
        if title and not str(row.get("title") or "").strip():
            row["title"] = title
    got["archived"] = rows
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    _plan_titles({}, drop=ids)


def run_done(ids: list[str], titles: dict, today: str) -> str:
    """Record what was archived (profile/tidy.json) and that today's tidy-up ran."""
    _mark_checked(today)
    if not ids:
        return "tidy: done for today"
    _record(ids, titles, today)
    n = len(ids)
    return "tell them, if they are in this chat: " + SAY_DONE.format(n=n, s="" if n == 1 else "s")


def close(sid: str, work: str, db: dict, info: dict, listener: dict, this_chat: str,
          repo: str, branches: set[str] | None,
          github: set[str] | None = None) -> tuple[str, str]:
    """A big job's chat that reported back: ("archive", its title) when it is one of the app's
    own job chats on this copy, its job (and every item claimed with it) has ended and its
    work is on master; else ("keep", why). `info` is get_session's record of that chat, so the
    title judged and recorded is the one it has now. Still running is expected: its report is
    the last thing it does. `github`: every branch GitHub holds (on_github)."""
    import page_db
    d = info.get(sid) or {}
    title = str(d.get("title") or "").strip()
    if not sid.startswith("session_") or not d:
        return "keep", "get_session has not said what that chat is"
    if sid in {listener.get("chat") or "", this_chat} - {""}:
        return "keep", "it answers the page"
    if not _is_apps(title):
        return "keep", "it is not one of the app's own chats"
    where = _repo_of(d)
    if not where or where != repo.lower():
        return "keep", "it works on another copy" if where else "its copy is not known"
    items = {k: (v.get("data") or {}) for k, v in (db.get("work") or {}).items()
             if k == work or str((v.get("data") or {}).get("with") or "") == work}
    if work not in items:
        return "keep", f"the page has no work item {work}"
    going = [k for k, v in items.items() if str(v.get("status") or "") not in page_db.FINISHED]
    if going:
        return "keep", "its job is still going (" + ", ".join(sorted(going)) + ")"
    own = _branches_of(d)
    if own and branches is None:
        return "keep", "git could not say whether its work is on master"
    left = [b for b in own if branches is not None and b in branches]
    if left:
        return "keep", "its work is not on master yet (" + ", ".join(left) + ")"
    local = [b for b in own if github is not None and b not in github]
    if local:
        return "keep", "its work is not on GitHub yet (" + ", ".join(local) + ")"
    return "archive", title


def run_close(a) -> int:
    import app_listen
    import page_db
    try:
        db = page_db.load(a.dump)
    except Exception:  # noqa: BLE001  no dump: nothing can be judged
        db = {}
    what, said = close(a.id, a.work, db, details(_pages(a.details)), _listener(a.dump),
                       app_listen.this_chat(a.chat), _repo(), unmerged(), on_github())
    if what != "archive":
        print(f"keep {a.id}: {said}. Leave it: the daily tidy-up puts it away once it can. "
              "Say nothing about it.")
        return 0
    _plan_titles({a.id: said})
    print(f"archive {a.id}: {said} (its job is finished, saved and on the page)")
    print(f"then: archive_session {json.dumps({'session_id': a.id})}, and once it is taken, "
          f"python3 tools/tidy.py closed {a.id}; commit it with this turn's work. Say nothing "
          "about it.")
    return 0


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="tidy.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("due")
    d.add_argument("--today", default="")
    p = sub.add_parser("plan")
    p.add_argument("--dump", default="")
    p.add_argument("--sessions", action="append", default=[])
    p.add_argument("--triggers", action="append", default=[])
    p.add_argument("--details", action="append", default=[])
    p.add_argument("--stdin", action="store_true",
                   help='{"sessions": ..., "triggers": ..., "details": ...} on standard input')
    p.add_argument("--chat", default="")
    p.add_argument("--today", default="")
    p.add_argument("--now", default="")
    p.add_argument("--verbose", action="store_true")
    o = sub.add_parser("done")
    o.add_argument("ids", nargs="*")
    o.add_argument("--titles", default="{}")
    o.add_argument("--today", default="")
    c = sub.add_parser("close")
    c.add_argument("id")
    c.add_argument("--work", required=True)
    c.add_argument("--dump", required=True)
    c.add_argument("--details", action="append", default=[])
    c.add_argument("--chat", default="")
    k = sub.add_parser("closed")
    k.add_argument("ids", nargs="+")
    k.add_argument("--today", default="")
    sub.add_parser("undo")
    a = ap.parse_args(argv)
    if a.cmd == "close":
        return run_close(a)
    if a.cmd == "closed":
        # Recorded, so `undo` can bring it back, without counting as today's tidy-up.
        _record(a.ids, {}, a.today or dt.date.today().isoformat())
        print("tidy: recorded; nothing to say")
        return 0
    if a.cmd == "due":
        return 0 if due(a.today) else 1
    if a.cmd == "plan":
        if not a.sessions and not a.stdin:
            print("tidy: list the chats first (list_sessions, mine: true, every page) and pass "
                  "them with --stdin: {\"sessions\": ..., \"triggers\": ...} on standard "
                  "input", file=sys.stderr)
            return 2
        return run_plan(a)
    if a.cmd == "done":
        try:
            titles = json.loads(a.titles or "{}")
        except ValueError:
            titles = {}
        print(run_done(a.ids, titles if isinstance(titles, dict) else {},
                       a.today or dt.date.today().isoformat()))
        return 0
    gone = archived()
    if not gone:
        print("tidy: nothing was tidied away")
        return 0
    for x in gone:
        print(f"unarchive_session {json.dumps({'session_id': x['id']})} ({x.get('title') or 'a chat'}, "
              f"tidied {x.get('on')})")
    print("then: tell them their old chats are back; tidy.py keeps them archived no more "
          "(they are in profile/tidy.json, so they are not tidied again)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
