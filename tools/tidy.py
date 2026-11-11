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

The brief runs in a chat of its own, "Job search: morning brief", made with the person's copy
attached (routines.own_chat_calls, 2026-11-10), and is never carried from helper to helper. A
brief in a chat not made for it (the chat that answers the page, an old helper, a fresh chat
each run) moves into one, and so does one whose own chat is gone, archived or approved
computer access: a new chat, a task bound to it on the same days and time, the old task
turned off (kept a week, then deleted by a later tidy-up: routines.cleanup), and then the old
chat archived where it is the app's. The
shortlist moves into the chat that answers the page. A brief in the older ops chat moves only
once that chat is gone (not listed, and the task now names the empty chat it woke instead).
Not while the brief is off or resting, never for a routine the person made (each run its
own chat: the run chats are archived, the routine kept). list_sessions never lists a chat a
scheduled task started, so each run's chat is read from list_triggers' last run and
remembered (profile/tidy.json `runs`) until it is old enough to tidy.

    python3 tools/tidy.py due                        exit 0 when today's tidy-up is due
    python3 tools/tidy.py plan --dump <dir> --sessions <file>... --triggers <file>...
                               [--details <file>...] [--chat <id>] [--today YYYY-MM-DD]
    python3 tools/tidy.py done [<session id>...] [--titles <json>] [--dump <dir>]
    python3 tools/tidy.py close <session id> --work <id> --dump <dir> --details <file>
                               [--now <time>]
    python3 tools/tidy.py closed <session id>...     once archive_session has taken it
    python3 tools/tidy.py retire --dump <dir> --stdin  the helper just taken over from, from one get_session
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
# A chat started on the person's computer is "Job search · <job> · <computer>"
# (tools/computer.py SESSION_TITLE), so the tidy-up knows it too.
APP_TITLE = re.compile(r"^(?:[^\w\s]{1,3}\s*)?Job search(?::\s*\S.{0,60}|\s+(?:helper|page)\b.{0,60}"
                       r"|\s+\u00b7\s+\S.{0,60}\s+\u00b7\s+\S.{0,40})$",
                       re.I)
# The page's helper, under its name since 4.10 ("Job search page", app_listen.HELPER_CHAT_TITLE)
# and every older one ("Job search helper", "... (finishing up)"). Only the live one, the chat
# meta/listen names, is kept: the rest are put away as soon as their work is on master, never
# kept for being used lately (the maintainer, 2026-11-04: at most two such chats, the person's
# own and the live page helper; a heavy user's renewals had stacked up several).
# The computer starter (tools/computer.py STARTER_TITLE), kept for good.
STARTER_NAME = re.compile(r"^(?:[^\w\s]{1,3}\s*)?Job search:\s+starts chats on your computer\b", re.I)
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
        # The job's own chat (`run_by`, page_db.run_by): it works under the id of the chat that
        # started it, so its job was counted to that chat (the second audit, C2).
        who = str(d.get("run_by") or d.get("claimed_by") or "")
        if not who.startswith("session_") or who == skip:
            continue
        status = str(d.get("status") or "")
        ended = status in page_db.FINISHED
        at = str(d.get("finished_at") or "") if ended else ""
        if status in ("needs_you", "queued"):
            # Its chat stopped on a question to the person (or the answer put it back in the
            # queue): that chat is done with it, and a fresh one takes it up. Counted as holding,
            # a job chat that asked was never finished (the review of 2026-11-11, item 3).
            ended = True
            at = str(d.get("answered_at") or d.get("asked_you_at") or d.get("claimed_at") or "")
        was = held.get(who, "")
        if not ended or was is None:
            held[who] = None
        elif at > was:
            held[who] = at
    return {k: v for k, v in held.items() if v}


def retiring(listener: dict | None, now: dt.datetime | None = None) -> str:
    """The helper the chat that answers the page took it over from, while it is still to be
    put away: one the app started (never the person's own chat), not recorded as archived yet,
    within 24 hours of the hand-over and on its own day in the person's zone (given `now`).
    "" when there is none."""
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
    # A later day in the person's own zone than the hand-over's ends it too: an old helper put
    # away by hand leaves no record here, and its open hand-over held the next morning's
    # renewal for the rest of 24 hours (the maintainer's copy, 2026-11-06). The day's tidy-up
    # puts away any old helper still there by its name.
    if now is not None:
        try:
            import app_listen
            if app_listen.new_day(mine, now):
                return ""
        except Exception:  # noqa: BLE001  no zone known: the 24 hours alone decide
            pass
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
        got = {}
    if not isinstance(got, dict):
        got = {}
    # The day's tidy as the page says it (page_mark, kept on its record of who answers it):
    # a fresh container's own git folder holds no mark, and ran the whole tidy again though
    # another chat had tidied that day (the second audit, 2026-11-10, D5).
    on_page = (listener or {}).get("tidied") if isinstance(listener, dict) else None
    if isinstance(on_page, dict) and on_page.get("on") == today and \
            on_page.get("sweep") == SWEEP and (got.get("checked") != today
                                                or str(on_page.get("at") or "") > str(got.get("at") or "")):
        got = {"checked": today, "at": on_page.get("at"), "sweep": SWEEP}
    if got.get("checked") != today or got.get("sweep") != SWEEP:
        # The day's mark on the page (meta/tidy): another chat, in another container, may have
        # run it today; kept only in this git folder, every fresh container ran it again
        # (second audit D5, E4).
        mark = meta_mark(db)
        if mark.get("checked") != today or mark.get("sweep") != SWEEP:
            return True
        got = mark
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
    asked = app_model.parse_time(got.get("retire_at")) if "retire_at" in got else \
        app_model.parse_time(_checked().get("retire_at"))
    if asked is not None and asked > last:
        last = asked              # retire asked about it then: half an hour on, again
    if retiring(mine, now) and since is not None and (
            since > last or (now is not None and (now - last).total_seconds() >= RETIRE_AGAIN_S)):
        return True
    for chat, at in finished_jobs(db, skip).items():
        t = app_model.parse_time(at)
        if chat not in gone and t is not None and t > last:
            return True
    return False


PAGE_MARK = "tidy"          # meta/tidy on the page: the day the tidy-up last ran, any chat


def meta_mark(db: dict | None) -> dict:
    """The day's tidy-up mark the page holds (meta/tidy), or {}. This copy's own, as the page's
    record of who answers it carries it, is `page_mark`."""
    rec = ((db or {}).get("meta") or {}).get(PAGE_MARK) or {}
    data = rec.get("data") if isinstance(rec, dict) else None
    return data if isinstance(data, dict) else {}


def page_mark_batch(dump: str, today: str, now: str = "") -> list[str]:
    """The batch that keeps the day's mark on the page (meta/tidy), pinned to the version read."""
    import page_db
    at = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        db = page_db.load(dump)
    except Exception:  # noqa: BLE001  nothing read: the mark is made fresh
        db = {}
    w = page_db.Writes(os.path.join(dump, "tidy-done"), db)
    w.add("set", "meta", PAGE_MARK, {"checked": today, "at": at, "sweep": SWEEP})
    return w.save("tidy-done")


def _mark_checked(today: str, now: str = "") -> None:
    path = _checked_path()
    if not path:
        return
    at = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = {k: v for k, v in _checked().items() if k in ("recheck", "completed", "retire_at")}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"checked": today, "at": at, "sweep": SWEEP, **keep}, fh)
        fh.write("\n")


def page_mark() -> dict:
    """This copy's own last tidy, as the page keeps it ({on, at, sweep}), or {} when none."""
    got = _checked()
    if not got.get("checked"):
        return {}
    return {"on": got["checked"], "at": got.get("at"), "sweep": got.get("sweep")}


def _checked() -> dict:
    path = _checked_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


COMPLETED_EVERY_DAYS = 7     # the tasks that have fired, asked for once a week


def completed_due(today: str, last: str | None = None) -> bool:
    """Is it the week's sweep that also asks list_triggers for the tasks that have fired
    (include_completed)? Every day added every fired one-off to the listing typed back by hand
    (review of fix/helpers, item 1)."""
    last = _checked().get("completed", "") if last is None else last
    try:
        return not last or (dt.date.fromisoformat(today) - dt.date.fromisoformat(last)).days \
            >= COMPLETED_EVERY_DAYS
    except ValueError:
        return True


def mark_completed(today: str) -> None:
    path = _checked_path()
    if not path:
        return
    got = _checked()
    got["completed"] = today
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh)
        fh.write("\n")


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


# A finished job chat whose work is neither on master nor waiting on any branch on GitHub: its
# save timed out, and its shortlist was in its container alone (the "Finding jobs" chat,
# 2026-11-06). It is asked once to save its work (land.py --keep, seconds, no check), then
# judged again when it answers, or SAVE_WAIT_S on with no answer: still not there, its work's
# own card says it was lost, with Try again (page_db.lose), once, and the chat is put away.
SAVE_WAIT_S = 30 * 60
SAVE_ANSWER_S = 60
# One message to the job chat, the only way to reach a chat that has finished; nothing comes
# back by message: the next tidy-up sees the work on GitHub, or says it was lost. A message
# between chats asks the person's approval each time, and the answer that was asked for here
# made two (the second audit of 2026-11-10, C3).
SAVE_ASK = ("[app] Save {work}: your work for it is not on GitHub yet, so the page cannot show "
            "it. Run python3 tools/land.py --keep (it saves your work to GitHub in a minute, "
            "with no check), and do nothing else: never message another chat, and never write "
            "to the person. The page's helper finds it saved by itself.")


def saves() -> dict:
    """{chat id: {work, asked, lost}}: the finished job chats asked to save their work."""
    try:
        with open(_record_path(), encoding="utf-8") as fh:
            got = json.load(fh).get("saves") or {}
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _note_save(sid: str, **fields) -> None:
    path = _record_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    rows = got.get("saves") if isinstance(got.get("saves"), dict) else {}
    rows[sid] = dict(rows.get(sid) or {}, **fields)
    got["saves"] = rows
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def unsaved(sid: str, now: dt.datetime, record: dict, answered: bool = False) -> str:
    """What is next for a finished job chat whose work never reached GitHub: "ask" (not asked
    yet), "wait" (asked lately), "lost" (asked, and it answered or SAVE_WAIT_S went by with the
    work still not there) or "said" (its card says so already)."""
    import app_model
    rec = (record or {}).get(sid) or {}
    asked = app_model.parse_time(rec.get("asked"))
    if asked is None:
        return "ask"
    if rec.get("lost"):
        return "said"
    age = (now - asked).total_seconds()
    return "lost" if age >= SAVE_WAIT_S or (answered and age >= SAVE_ANSWER_S) else "wait"


# Work done on the person's computer: its save is pushed from there and brought to master by
# the computer starter's land.py, so a branch GitHub does not hold yet is never its work lost.
# Said lost, a read finished on the Mac became "results lost, Try again" while the work was
# still on the Mac (the builder audit, 2026-11-10, CC-1).
ON_COMPUTER_KEPT = ("its work was saved on the person's computer; the chat that starts chats "
                    "there brings it to master")


def on_computer(d: dict) -> bool:
    """Was this work item done on the person's computer?"""
    return str(d.get("claimed_as") or "") == "computer" or isinstance(
        d.get("computer_session"), dict) and bool(d["computer_session"].get("id"))


def job_items(db: dict) -> dict:
    """{chat id: {"all": [work ids], "done": [the ids done], "computer": bool}}, by the chat
    that ran each: its own (`run_by`), else the one it was claimed by; `computer` when any was
    done on the person's computer."""
    out: dict = {}
    for wid, doc in sorted((db.get("work") or {}).items()):
        d = doc.get("data") or {}
        who = str(d.get("run_by") or d.get("claimed_by") or "")
        if not who.startswith("session_"):
            continue
        got = out.setdefault(who, {"all": [], "done": [], "computer": False})
        got["all"].append(wid)
        got["computer"] = got["computer"] or on_computer(d)
        if str(d.get("status") or "") == "done":
            got["done"].append(wid)
    return out


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
    """{session id: get_session's record}, from records alone, each wrapped as {"ccr": ...},
    a page of them ({"data": [...]}), or a plain list of them. A plain list was dropped
    without a word, so `plan` asked for the same chats again and again (2026-11-09)."""
    out = {}

    def take(got) -> None:
        if isinstance(got, list):
            for g in got:
                take(g)
            return
        if not isinstance(got, dict):
            return
        got = got.get("ccr", got)
        if isinstance(got, dict) and not got.get("id") and isinstance(got.get("data"), list):
            take(got["data"])
        elif isinstance(got, list):
            take(got)
        elif isinstance(got, dict) and got.get("id"):
            out[got["id"]] = got

    for got in pages:
        take(got)
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
         on_github: set[str] | None = None, saves: dict | None = None,
         job_items: dict | None = None) -> dict:
    """{"ask": [ids to read with get_session], "archive": [{id, title, why}],
    "keep": [{id, title, why}], "brief": [calls] or [], "save": [{id, title, work}],
    "lost": [{id, title, work: [ids]}]}. `jobs` is finished_jobs(): a chat in it is not kept
    for being used lately. `now` (else noon of `today`) times recent use; `on_github`, every
    branch GitHub holds, tells a branch never pushed from one merged. With `job_items`
    (job_items(), the page's records) and `saves` (the record of asks), a finished job chat
    whose work never reached GitHub is asked to save it once ("save"), then its work said lost
    ("lost") and the chat put away (unsaved)."""
    jobs = jobs or {}
    import routines
    now = now or dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    live_ids = {listener.get("chat") or "", this_chat} - {""}
    # The helper this chat just took the page over from is judged whatever list was passed: a
    # list cut down by hand lacked it, and the tidy-up said "nothing to tidy" with it still open
    # (H-1). Not in the list: read with get_session, then judged from that record.
    ret = retiring(listener, now)
    pending_ask = []
    if ret and ret not in {c.get("id") for c in chats} and ret not in done_before:
        d = info.get(ret)
        if d is None:
            pending_ask.append(ret)
        else:
            chats = list(chats) + [{k: v for k, v in dict(d, id=ret).items()
                                    if k in ("id", "title", "status", "session_status",
                                             "status_bucket", "updated_at", "created_at",
                                             "last_activity_at")}]
    # The chat the page was taken from is put away only where the app started it: one the
    # person writes in, whatever its title, is theirs (the stranger audit, X-4).
    known = ({listener.get("took_from") or ""} - {""}) if listener.get("took_from_helper") else set()
    # Every chat the page's record says answered it as a helper (app_listen.helpers_after):
    # a helper is what it did, never how it was started or what it is called. One the person
    # started from the page ("Look after my job search page from now on.") keeps the name the
    # app gave its first message, and the tidy-up said "nothing to tidy" for it, a third
    # helper beside the live one (the maintainer's copy, 2026-11-05).
    helped = (({str(x) for x in listener.get("helpers") or () if x} | known)
              - {listener.get("chat") or ""})
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
    out: dict = {"ask": pending_ask, "archive": [], "keep": [], "brief": [], "save": [],
                 "lost": [], "retiring": ret, "gone": []}

    # The brief runs in a chat of its own, made with create_session and the copy attached
    # (routines.own_chat_calls; the maintainer, 2026-11-10). Bound to the chat that answers the
    # page, it failed once that chat approved computer access, and it was carried from helper
    # to helper as the page renewed: never again. A brief in a chat not made for it moves into
    # one of its own (whichever chat that was, the live helper included), and so does one whose
    # own chat is gone, archived or approved computer access, saying nothing to the person. A
    # brief in the older ops chat stays there while that chat lives (it relays to the phone);
    # once the chat is gone, the task wakes a new empty chat with no copy of the files every
    # morning ("Morning brief could not start: no git repo", 2026-10-31), so it moves too. The
    # job round moves into the chat that answers the page by its own rule (X-50).
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
    started_helpers |= started & helped
    mine_only = started - started_helpers             # theirs, never a helper: never listed
    old_helpers = ({sid for sid, t in titles.items() if HELPER_NAME.match(t.strip())} | helped) \
        - live_ids - mine_only - {theirs, ""}

    # The chat that handed the page to the live helper, by the page's own record: a brief
    # still firing in it has not moved, whatever its title (the maintainer's copy, 2026-11-05).
    handed = {str(listener.get("handed_by") or "")} - {"", helper}

    def gone(sid: str) -> bool:
        """Gone by get_session's word, never by a listing that lacks it: a listing cut down by
        hand moved the brief to a new chat (second audit B1)."""
        return sid not in listed_ids and bool((info.get(sid) or {}).get("gone"))

    def retired(sid: str) -> bool:
        return bool(sid) and sid != helper and (
            gone(sid) or sid in helped or sid in old_helpers or sid in handed
            or bool(re.search(r"\bhelper\b", titles.get(sid, ""), re.I)))

    def old_helper(sid: str) -> bool:
        """One of the app's helpers the page no longer uses, this chat included."""
        return bool(sid) and sid != helper and sid not in mine_only and sid != theirs and (
            sid in helped or bool(HELPER_NAME.match(titles.get(sid, "").strip())))

    # Where the brief runs is where its task fires, by the listing, never the registry alone:
    # a registry that already named the new chat while the task still fired in the old one let
    # the helper report the brief moved when it had not (the maintainer's copy, 2026-11-05). A
    # registry naming a task the listing lacks is read by the brief's own prompt instead.
    live_brief = next((t for t in triggers if brief.get("trigger_id")
                       and t.get("id") == brief.get("trigger_id")), None) or (next(
                           (t for t in triggers if t.get("enabled") is not False
                            and routines._is_brief_prompt(str(t.get("prompt") or ""))), None)
                           if brief else None) or {}
    tid = str(live_brief.get("id") or brief.get("trigger_id") or "")
    fired_in = str(live_brief.get("session") or live_brief.get("persistent_session_id") or "")
    if fired_in and fired_in != home and (not home or home == helper or (
            fired_in in listed_ids and old_helper(fired_in))):
        home = fired_in
    out["brief_fires"] = fired_in
    out["brief_own"] = brief_chat if routines.owns_chat(brief) else ""

    if (setup in ("chat_per_briefing", "ops_relay", "routines_screen") and live_brief
            and live_brief.get("enabled") is not False and not brief.get("off")
            and not reg.get("pause") and tid and brief.get("cron")):
        trusted = routines.trusted_chat()
        why = routines.needs_own_chat(reg, brief, live_brief, trusted)
        where = fired_in or home
        if why and where and where not in listed_ids and where not in info:
            out["ask"].append(where)                 # read before it is judged gone
            why = ""
        if why and not routines.owns_chat(brief) and fired_in \
                and fired_in not in (helper, ops, trusted) and not retired(fired_in):
            # Its task already fires in a chat made for it (create_session named it so), which
            # the registry never recorded: that chat is recorded as its own, never a new one
            # made every day (audit BT-1; second audit B1).
            d = info.get(fired_in) or {}
            name = titles.get(fired_in) or str(d.get("title") or "")
            # Any "Job search: ... brief ..." title, not only the exact one (review of
            # fix/helpers, item 19: "Job search: brief (daily)" was given yet another chat).
            made_for_it = bool(routines._BRIEF_TITLE.match(name.strip()))
            if made_for_it and fired_in not in info:
                out["ask"].append(fired_in)          # its copy is read before it is recorded
                why = ""
            elif made_for_it and routines.adoptable(dict(d, title=name), repo) and \
                    "archived" not in _status(
                        next((c for c in chats if c.get("id") == fired_in), None), d):
                out["brief"] = [{"run": f"python3 tools/routines.py record --session {fired_in} "
                                        f"--trigger {tid} --cron \"{brief.get('cron')}\" --own-chat",
                                 "why": "the chat made for the brief, where its task already "
                                        "fires, is recorded as its own"}]
                why = ""
        if why and not routines.owns_chat(brief) and setup != "routines_screen" \
                and not ((fired_in or home) and (retired(fired_in or home)
                                                 or (fired_in or home) == trusted)):
            # A working brief in a chat not made for it (the live helper's, a chat of the
            # person's) is moved by its profile upgrade (brief-own-chat), never here: here only
            # one whose chat no longer works, a helper the page no longer uses or one that
            # approved computer access.
            why = ""
        if not why and routines.owns_chat(brief) and home:
            chat_rec = next((c for c in chats if c.get("id") == home), None)
            if chat_rec is None and home not in info:
                out["ask"].append(home)              # missing from the listing: asked, not gone
            elif gone(home):
                why = "its own chat is gone"
            elif "archived" in _status(chat_rec, info.get(home)):
                why = "its own chat was archived"
        # Gone, for the ops chat: not among the person's chats, and the task itself now
        # names another chat, one that works on no copy at all (the empty one it woke
        # instead). All three, so a listing that missed a page never moves a brief whose ops
        # chat still relays.
        woke = str(live_brief.get("session") or "")
        brief_home = brief_chat or (ops if setup == "ops_relay" else "")
        if not why and setup == "ops_relay" and brief_home == ops and ops not in listed_ids \
                and woke not in ("", ops):
            if woke not in listed_ids:
                why = "the older ops chat is gone"
            elif woke not in info:
                out["ask"].append(woke)
            elif not _repo_of(info[woke]):
                why = "the older ops chat is gone"
        if why:
            adopt = home if home and home != helper else ""
            out["brief"] = routines.own_chat_calls(
                reg, brief, tid, repo, "the brief runs in a chat of its own from now on (" + why + ")")
            out["brief_why"] = why

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
                                                            "brief gets a chat of its own"})
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
        if not (APP_TITLE.match(title) or sid in helped) or sid == theirs or sid in mine_only:
            continue                                  # the person's own chat: never listed
        if sid in live_ids:
            keep("it answers the page" if sid == listener.get("chat") else "it is this chat")
            continue
        if sid == ops:
            keep("the older ops chat, which relays to the phone and is never rebuilt")
            continue
        if STARTER_NAME.match(title):
            # The one chat that holds the computer approval: it can be archived by no chat,
            # and it is woken again for the next work on the computer (tools/computer.py).
            keep("it starts the chats on the person's computer")
            continue
        if fires.get(sid, set()) - moving:
            keep("a scheduled task that is on runs in it")
            continue
        if sid in campaigns:
            keep("a live process has its own chat here")
            continue
        if sid in old_helpers and sid not in helped and _after(s.get("created_at"),
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
        if "archived" in status:
            # Put away already (by another chat, or by itself): archiving it again hung a chat
            # for nearly two minutes (H-8). Recorded as put away, so the tidy-up rests and Undo
            # knows it: only the tidy-up's own archives were (second audit A2, A5).
            keep("it is archived already")
            # Only this copy's own: the helper taken over from, the page's job chats and
            # helpers, or a chat of this copy used within the week. Another copy's chats and ones
            # archived months ago were recorded, and Undo would bring them back (review of
            # fix/helpers, item 3).
            ours = sid == ret or sid in jobs or sid in helped or (
                d is not None and _repo_of(d) == repo.lower()
                and _days_since(_last_used(s, d), today) <= 7)
            if ours:
                out["gone"].append({"id": sid,
                                    "title": title or str((d or {}).get("title") or "")})
            continue
        if _running(status):
            keep("it is running")
            continue
        last = _last_used(s, d)
        quiet = _days_since(last, today)
        waits = "requires_action" in status or "blocked" in status
        if sid == ret and _ago_s(last, now) < RETIRE_QUIET_S:
            # The helper just taken over from owns its own archive (decided, review of
            # fix/helpers item 2): only it can see whether its work reached GitHub (app.py
            # retired). Put away here only after a day of quiet.
            keep("it puts itself away once its work is saved")
            continue
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
        if local and job_items is not None and (job_items.get(sid) or {}).get("computer"):
            keep(ON_COMPUTER_KEPT)
            continue
        if local and sid in jobs and job_items is not None:
            # Finished, not landed, nothing pushed: asked once, then said (unsaved).
            items = job_items.get(sid) or {}
            next_step = unsaved(sid, now, saves or {})
            if next_step == "ask":
                out["save"].append({"id": sid, "title": title,
                                    "work": (items.get("all") or [""])[0]})
                keep("its work is not on GitHub yet; it is asked once to save it")
                continue
            if next_step == "wait":
                keep("it was asked to save its work a short while ago")
                continue
            if next_step == "lost":
                out["lost"].append({"id": sid, "title": title, "work": items.get("done") or []})
            out["archive"].append({"id": sid, "title": title,
                                   "why": "its job finished, but its work never reached GitHub "
                                          "and is lost; its card on the page says so"})
            continue
        if local and quiet < IDLE_DAYS:
            keep("its work is not on GitHub yet (" + ", ".join(local) + ")")
            continue
        why = ("the brief moved into a chat of its own" if sid == adopt else
               "the shortlist moved into the chat that answers the page" if sid in moved_from else
               "a helper the page no longer uses" if sid in old_helpers or sid in helped
               or re.search(r"helper", title, re.I)
               else "a chat for one run or one job, finished")
        out["archive"].append({"id": sid, "title": title, "why": why})
    listed = {s.get("id") for s in chats}
    if rchat in moved_from and rchat in listed and not any(a["id"] == rchat for a in out["archive"]):
        out["moves"] = []                             # its chat is kept: the round stays put
    out["ask"] = list(dict.fromkeys(out["ask"]))
    # Run by the live helper within a day of its hand-over, with an old helper kept only for
    # now: it asks for its own check-in, as nothing else may ring it before tomorrow's brief.
    took = _after(now.strftime("%Y-%m-%dT%H:%M:%SZ"), listener.get("since")) and \
        _ago_s(listener.get("since"), now) < RETIRE_FOR_S
    # Any old helper kept, for whatever reason: only "for now" reasons asked for one, and a
    # helper kept because git could not say whether its work was on master (its save still
    # landing as the new helper took over) stayed in their list all day, the day's tidy-up
    # already marked done (the maintainer's copy, 2026-11-07).
    out["recheck"] = bool(this_chat and this_chat == helper and took and not out["ask"] and any(
        k["id"] in old_helpers for k in out["keep"]))
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
    # Old tasks that can no longer run: turned-off briefs another replaced, a one-off long past
    # its time, a check-in bound to the chat that approved computer access (BT-9, H-5). Never
    # mended as well: a test check-in carries the brief's prompt.
    out["clean"] = [] if out["ask"] else [
        c for c in routines.cleanup(reg, triggers, now, routines.trusted_chat(), repo=repo)
        if c["args"]["trigger_id"] not in moving | skip]
    cleaned = {c["args"]["trigger_id"] for c in out["clean"]}
    out["mend"] = [] if out["ask"] else [
        c for c in routines.mend(triggers, repo, named=routines.named_ids(reg))
        if c["args"]["trigger_id"] not in skip | cleaned]
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
        # The brief's real time as the scheduler reports it (a late start on the hour), kept
        # for the page each day the listing is read (routines.saw).
        routines.saw(tasks)
    except Exception:  # noqa: BLE001  never stops the tidy-up over a record
        pass
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
    pagedb: dict | None = None
    if a.dump:
        try:
            import page_db
            pagedb = page_db.load(a.dump)
            jobs = finished_jobs(pagedb, listener.get("chat") or "")
        except Exception:  # noqa: BLE001  not a dump: no finished jobs known, the days rule holds
            jobs, pagedb = {}, None
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
               _campaign_chats(), unmerged(), done, jobs, now=now, on_github=on_github(),
               saves=saves(), job_items=job_items(pagedb) if pagedb is not None else None)
    if got["ask"]:
        print("tidy: read these chats first, each with get_session, and run this again with "
              "what each returned under \"details\" in the same standard input (or --details "
              "<each file>); for one get_session cannot find, {\"id\": \"<its id>\", \"gone\": "
              "true}: " + " ".join(got["ask"]))
        return 0
    at = now or dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    # The day's mark goes onto the page too, so a chat in a fresh container skips it (E4).
    mark = f" --dump \"{a.dump}\", and send the batch it prints" if a.dump else ""
    if got.get("gone"):
        # Archived elsewhere (by itself, another chat or by hand): recorded here, said to nobody.
        _record([c["id"] for c in got["gone"]], {c["id"]: c["title"] for c in got["gone"]},
                today.isoformat())
    import app_model
    for c in got.get("save") or []:
        ask = SAVE_ASK.format(work=c["work"] or "its job",
                              listener=listener.get("chat") or me or "<your chat id>")
        print(f"save {c['id']}: {c['title']} (its job finished, but its work never reached "
              f"GitHub): send_message {json.dumps({'session_id': c['id'], 'message': ask}, ensure_ascii=False)}, "
              "once, and keep the chat. Say nothing about it.")
        _note_save(c["id"], work=c["work"], asked=app_model.stamp(at))
    for c in got.get("lost") or []:
        import page_db
        paths = page_db.lose(pagedb or {}, c["work"], at,
                             os.path.join(a.dump, "lost", c["id"]))
        _note_save(c["id"], lost=app_model.stamp(at))
        if paths:
            print(f"lost {c['id']}: {c['title']} (its job finished, but its work never reached "
                  "GitHub and is lost): send this batch (ArtifactData batch), asking nobody; the "
                  "work's own card says so in plain words, with Try again. Say nothing else "
                  "about it.")
            for p in paths:
                print(p)
    if app_listen.nested(me):
        # This chat can make no scheduled task (chats nest only so deep, 2026-11-05): the
        # brief, the shortlist and the upkeep stay where they are and keep their chats, and
        # the fresh helper the brief's next run starts moves them. Never a dead end.
        moved = ("the brief moved", "the shortlist moved")
        if got["brief"] or got.get("moves") or got.get("upkeep"):
            print("tidy: this chat cannot make scheduled tasks, so the brief and the other "
                  "tasks stay where they are, and so do their chats; the fresh helper moves "
                  "them. Say nothing about it.")
        got["brief"], got["moves"], got["upkeep"], got["recheck"] = [], [], [], False
        got["archive"] = [c for c in got["archive"] if not c["why"].startswith(moved)]
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
    for i, c in enumerate(got.get("clean") or [], 1):
        print(f"clean {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
    if got.get("clean"):
        print("clean: make these, asking nobody and saying nothing about it; one refused is left "
              "for the next tidy-up")
    if got.get("upkeep"):
        print("upkeep: make these in order and stop at the first that fails; say nothing about it")
    if len(got["brief"]) > 1:
        print("brief: make these in order and stop at the first that fails, asking nobody and "
              "saying nothing to the person; archive the old brief's chat only once all are "
              "made. Never say the brief moved until a new list_triggers shows its task firing "
              "in its own new chat (this plan, run again on it, says so)")
    elif got["brief"]:
        print("brief: make this call, then carry on")
    fires = str(got.get("brief_fires") or "")
    own = str(got.get("brief_own") or "")
    if fires and fires == own and not got["brief"]:
        print("brief: the task listing shows the brief fires in its own chat")
    elif fires and got["brief"]:
        print(f"brief: the task listing shows the brief still fires in {fires}, not in a chat of "
              "its own: it has not moved, so never say it has")
    if got["brief"] or got.get("moves") or got.get("upkeep") or got.get("recheck"):
        print("nested: where a create_session or create_trigger is turned down because this "
              "chat cannot start any more chats or scheduled tasks: python3 tools/app.py nested "
              f"--chat {me or '<this chat id>'}, keep the chat that task is in (archive nothing "
              "for it) and carry on with the rest; the fresh helper the brief's next run "
              "starts moves it. Say nothing about it.")
    import app_setup
    rings = app_setup.doorbells_due(today)
    if rings:
        # Every day, not once: rings no wake resolved stayed unread in the Claude app, 18 of
        # them (the maintainer, 2026-11-05).
        print("rings: python3 tools/app.py doorbells, and do what it says (it resolves the "
              "page's open rings only). Say nothing about it.")
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
              f"{mark}"
              f"{more} (all of them: {ids}); commit it")
        # One refused (still finishing its last turn, most often) is tried again by a check-in,
        # never handed to the person: the live helper told them "you can archive it yourself"
        # (the maintainer's live run, 2026-11-05).
        print("then: an archive_session that is refused is left as it is, never mentioned and "
              "never asked of the person; the next tidy-up tries again (it is due again by "
              "itself, at the page's next check-in or the brief's next run). Set no reminder "
              "or check-in for it")
    elif got["brief"] or got.get("moves") or got.get("upkeep") or got.get("mend") \
            or got.get("clean") or rings:
        # Never "nothing to tidy" over calls still to make: the helper took it as the brief
        # already moved (the maintainer's copy, 2026-11-05).
        print("tidy: no chat to archive; make the calls above, then python3 tools/tidy.py done"
              + mark)
    else:
        print("tidy: nothing to tidy. python3 tools/tidy.py done" + mark)
    # The helper this chat took over from, kept only for now: said, so a run never reads as
    # "nothing to tidy" with it still open (H-1). The tidy-up is due again by itself (due()).
    for k in got["keep"]:
        if k["id"] == got.get("retiring"):
            print(f"tidy: the helper this chat took the page from, {k['id']}, is kept for now "
                  f"({k['why']}); the tidy-up is due again by itself and puts it away then. "
                  "Say nothing about it.")
    stamp = now or dt.datetime.combine(today, dt.time(12), tzinfo=dt.timezone.utc)
    if got.get("recheck") and recheck_due(stamp):
        # No send_later: a reminder this chat sets for itself never runs once it has approved
        # computer access (the maintainer, 2026-11-10). The tidy-up is due again by itself
        # (due(): every RETIRE_AGAIN_S while the old helper is still there), so the page's
        # next check-in or the brief's next run puts it away.
        mark_recheck(stamp)
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


def _record(ids: list[str], titles: dict, today: str, gone: bool = False) -> None:
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
            rows.append({"id": i, "title": title, "on": today, **({"gone": True} if gone else {})})
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
          github: set[str] | None = None, now: dt.datetime | None = None,
          record: dict | None = None, fresh: bool = False) -> tuple[str, str]:
    """A big job's chat that reported back: ("archive", its title) when it is one of the app's
    own job chats on this copy, its job (and every item claimed with it) has ended and its
    work is on master; else ("keep", why). `info` is get_session's record of that chat, so the
    title judged and recorded is the one it has now. Still running is expected: its report is
    the last thing it does. `github`: every branch GitHub holds (on_github). Given `now` and
    `record` (saves()), a finished one whose work is on no branch GitHub holds is ("save",
    why) the first time and ("lost", its title) once it answers with the work still not
    there."""
    import page_db
    d = info.get(sid) or {}
    title = str(d.get("title") or "").strip()
    if not sid.startswith("session_") or not d:
        return "keep", "get_session has not said what that chat is"
    if sid in {listener.get("chat") or "", this_chat} - {""}:
        return "keep", "it answers the page"
    if "archived" in _status(None, d):
        # Put away already: never archived again, which hung a chat for 1m 45s (H-8).
        return "archived", title
    if not _is_apps(title):
        return "keep", "it is not one of the app's own chats"
    where = _repo_of(d)
    if not where or where != repo.lower():
        return "keep", "it works on another copy" if where else "its copy is not known"
    # A chat still running, or holding any other item it claimed that has not ended, is kept,
    # whatever --work says: a wrong id with --fresh archived a chat at work (review of
    # fix/helpers, item 4).
    # One waiting on an approval or a question is at work too, as `stale` reads it.
    status = _status(None, d)
    if _running(status) or "requires_action" in status or "blocked" in status:
        return "keep", "it is running"
    # The chat that ran it (`run_by`) as well as its claim, as finished_jobs reads both: a job's
    # chat runs its jobs under the id of the chat that started it, so one that reported a
    # first job while blocked part way through a second was put away at work (the engine
    # review, 2026-11-11).
    holding = sorted(k for k, v in (db.get("work") or {}).items()
                     if str((v.get("data") or {}).get("run_by")
                            or (v.get("data") or {}).get("claimed_by") or "") == sid
                     and str((v.get("data") or {}).get("status") or "") not in page_db.FINISHED)
    if holding:
        return "keep", "it still holds work (" + ", ".join(holding) + ")"
    items = {k: (v.get("data") or {}) for k, v in (db.get("work") or {}).items()
             if k == work or str((v.get("data") or {}).get("with") or "") == work}
    if work not in items and not fresh:
        # Never judged from an old read: a folder that holds only what changed since an earlier
        # read lacks a job finished before it, and a finished chat stayed in the sidebar for a
        # day (the maintainer, 2026-11-10). The page itself is read for it, then judged again;
        # a fresh read (`fresh`) that still lacks it means the page holds it no more: its job
        # has ended, never "read" again for good (audit HC-1).
        return "read", f"this folder does not hold the work item {work}"
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
    if local and any(on_computer(v) for v in items.values()):
        return "keep", ON_COMPUTER_KEPT
    if local and now is not None:
        # It reported, finished, with its work on no branch GitHub holds: asked once to save
        # it, and once it has answered with the work still not there, said lost (unsaved).
        step = unsaved(sid, now, record or {}, answered=True)
        if step == "ask":
            return "save", "its work is not on GitHub yet (" + ", ".join(local) + ")"
        if step == "wait":
            return "keep", "it was asked to save its work a short while ago"
        return ("lost" if step == "lost" else "archive"), title
    if local:
        return "keep", "its work is not on GitHub yet (" + ", ".join(local) + ")"
    return "archive", title


def retire(old: str, d: dict | None, repo: str, branches: set[str] | None,
           now: dt.datetime) -> tuple[str, str]:
    """The helper this chat took the page over from, judged from one get_session of it (`d`),
    never a listing typed back by hand (H-4; second audit A6, R3): ("read", why) without it,
    ("gone", title) where get_session cannot find it, ("archived", title) when put away
    already, ("archive", title) only after a day of quiet, else ("keep", why). The old helper
    owns its own archive (decided, review of fix/helpers item 2): only it can see whether its
    work reached GitHub (app.py retired), and this chat archived one whose save GitHub never
    held, its work lost with its container."""
    if d is None:
        return "read", "its state is not known here yet"
    title = str(d.get("title") or "")
    if d.get("gone"):
        return "gone", title
    status = _status(None, d)
    if "archived" in status:
        return "archived", title
    if _running(status) or "requires_action" in status or "blocked" in status:
        return "keep", "it is still at work"
    where = _repo_of(d)
    if where and where != repo.lower():
        return "keep", "it works on another copy"
    if _ago_s(_last_used({}, d), now) < RETIRE_QUIET_S:
        return "keep", "it puts itself away once its work is saved"
    return "archive", title


RETIRE_QUIET_S = 24 * 3600     # an old helper quiet this long is put away by the new one


def retire_due(now: dt.datetime) -> bool:
    """Was the helper taken over from asked about over RETIRE_AGAIN_S ago (or never)?"""
    import app_model
    last = app_model.parse_time(_checked().get("retire_at"))
    return last is None or (now - last).total_seconds() >= RETIRE_AGAIN_S - 60


def mark_retire(now: dt.datetime) -> None:
    path = _checked_path()
    if not path:
        return
    got = _checked()
    got["retire_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh)
        fh.write("\n")


def run_retire(a) -> int:
    import app_model
    now = (app_model.parse_time(a.now) if a.now else None) or dt.datetime.now(dt.timezone.utc)
    listener = _listener(a.dump)
    old = retiring(listener, now)
    if not old:
        print("retire: no helper is waiting to be put away. Say nothing about it.")
        return 0
    got = details(_pages(a.details) + _as_pages(_given(a).get("details")))
    what, said = retire(old, got.get(old), _repo(), unmerged(), now)
    if what != "read":
        mark_retire(now)          # asked about again only RETIRE_AGAIN_S on (due)
    if what == "read":
        print(f"retire: get_session (session_id {old}), then python3 tools/tidy.py retire "
              f"--dump \"{a.dump}\" --stdin with {{\"details\": <what get_session returned>}} in "
              "a quoted heredoc (for a chat it cannot find, {\"details\": {\"id\": "
              f"\"{old}\", \"gone\": true}}}}). Say nothing about it.")
        return 0
    if what in ("archived", "gone"):
        # Gone (deleted): recorded as such, so the tidy-up rests and Undo never tries it.
        _record([old], {old: said}, now.date().isoformat(), gone=(what == "gone"))
        print(f"retire: {old} is put away already, and recorded. Nothing more; say nothing "
              "about it.")
        return 0
    if what == "keep":
        print(f"retire: the helper this chat took the page from, {old}, is kept for now "
              f"({said}); the next check-in tries again; archive nothing by hand, and say "
              "nothing about it.")
        return 0
    _plan_titles({old: said})
    print(f"retire: archive_session {json.dumps({'session_id': old})}, then python3 "
          f"tools/tidy.py closed {old}; commit it with this turn's work. Refused: leave it, the "
          "next check-in tries again. Say nothing about it.")
    return 0


def run_close(a) -> int:
    import app_listen
    import page_db
    try:
        db = page_db.load(a.dump)
    except Exception:  # noqa: BLE001  no dump: nothing can be judged
        db = {}
    import app_model
    now = app_model.parse_time(a.now) if a.now else None
    now = now or dt.datetime.now(dt.timezone.utc)
    listener = _listener(a.dump)
    me = app_listen.this_chat(a.chat)
    record = saves()
    what, said = close(a.id, a.work, db, details(_pages(a.details)), listener, me, _repo(),
                       unmerged(), on_github(), now=now, record=record,
                       fresh=bool(getattr(a, "fresh", False)))
    if what == "save":
        print(f"save {a.id}: {said}, and its job has finished: it is asked once to save it. "
              f"send_message {json.dumps({'session_id': a.id, 'message': SAVE_ASK.format(work=a.work, listener=listener.get('chat') or me or '<your chat id>')}, ensure_ascii=False)}. "
              "Keep the chat; nothing comes back by message: the next tidy-up (tidy.py plan) "
              "finds the work saved, or says it was lost. Say nothing about it.")
        _note_save(a.id, work=a.work, asked=app_model.stamp(now))
        return 0
    if what == "lost":
        ids = [k for k, v in (db.get("work") or {}).items()
               if k == a.work or str((v.get("data") or {}).get("with") or "") == a.work]
        paths = page_db.lose(db, ids, now, os.path.join(a.dump, "lost"))
        _note_save(a.id, lost=app_model.stamp(now))
        if paths:
            print(f"lost {a.id}: its job finished, but its work never reached GitHub and it "
                  "had nothing to save when asked, so it is lost. Send this batch "
                  "(ArtifactData batch), asking nobody: the work's own card says so in plain "
                  "words, with Try again. Say nothing else about it.")
            for p in paths:
                print(p)
        what = "archive"
    if what == "read":
        try:
            import app_setup
            url = app_setup.page_record().get("url", "") or "<the page's url>"
        except Exception:  # noqa: BLE001
            url = "<the page's url>"
        print(f"read {a.id}: {said}. Read the page's work as it is now: ArtifactData query, url "
              f"{url}, collection work, out_dir {a.dump}, limit 1000; then run this same "
              "command again with --fresh. Say nothing about it.")
        return 0
    if what == "archived":
        print(f"archived {a.id}: it is put away already, so nothing to archive: python3 "
              f"tools/tidy.py closed {a.id}. Say nothing about it.")
        return 0
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
    o.add_argument("--dump", default="", help="the folder the plan read: the day's mark goes "
                                              "onto the page too")
    r = sub.add_parser("retire", help="the helper this chat took the page over from, judged "
                                      "from one get_session of it")
    r.add_argument("--dump", default="")
    r.add_argument("--details", action="append", default=[])
    r.add_argument("--stdin", action="store_true")
    r.add_argument("--now", default="")
    c = sub.add_parser("close")
    c.add_argument("id")
    c.add_argument("--work", required=True)
    c.add_argument("--dump", required=True)
    c.add_argument("--details", action="append", default=[])
    c.add_argument("--chat", default="")
    c.add_argument("--now", default="")
    c.add_argument("--fresh", action="store_true",
                   help="the folder is a fresh read of the page's work, as `read` asked")
    k = sub.add_parser("closed")
    k.add_argument("ids", nargs="+")
    k.add_argument("--today", default="")
    sub.add_parser("undo")
    a = ap.parse_args(argv)
    if a.cmd == "retire":
        return run_retire(a)
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
        day = a.today or dt.date.today().isoformat()
        print(run_done(a.ids, titles if isinstance(titles, dict) else {}, day))
        if a.dump:
            paths = page_mark_batch(a.dump, day)
            if paths:
                print("then: send this batch (ArtifactData batch), asking nobody: it marks the "
                      "day's tidy-up on the page, so no other chat runs it again today")
                for p in paths:
                    print(p)
        return 0
    gone = [x for x in archived() if not x.get("gone")]      # a deleted chat cannot come back
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
