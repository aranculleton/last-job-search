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
  the page recorded as answering before;
- not on this copy (get_session names the copy each chat works on; unknown is kept);
- the chat that answers the page, or this chat;
- bound to a scheduled task that is on (the job round, an older ops chat that relays to the
  phone, which is never rebuilt), or the ops chat itself;
- a campaign chat for a process still live;
- running, or used in the last two days (seven when it is waiting on the person);
- or holding work that is not on master yet: a branch it pushed that master does not hold.
  The day's update lands such a branch; the chat is archived once it has.

A brief in a chat of its own (set-up (a), from before 4.3) moves into the chat that answers
the page first: a task bound to that chat on the same days and time, the old task turned off
(kept, never deleted), and then its chat archived. A brief in the older ops chat moves the
same way only once that chat is gone (not listed, and the task now names the empty chat it
woke instead). Not while the brief is off or resting, never for a routine (each run its own
chat, with the person's phone notification: the run chats are archived, the routine kept).

    python3 tools/tidy.py due                        exit 0 when today's tidy-up is due
    python3 tools/tidy.py plan --dump <dir> --sessions <file>... --triggers <file>...
                               [--details <file>...] [--chat <id>] [--today YYYY-MM-DD]
    python3 tools/tidy.py done [<session id>...] [--titles <json>]
    python3 tools/tidy.py undo                       the calls that bring them all back

`--sessions` takes what list_sessions returned (mine: true), every page; `--triggers` what
list_triggers returned, every page; `--details` what get_session returned for each chat
`plan` asks about. Pure code apart from one `git branch` read; it calls no tool itself.
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
APP_TITLE = re.compile(r"^Job search(?::\s*\S.{0,60}|\s+helper\b.{0,60})$", re.I)
IDLE_DAYS = 2           # quiet this long before it is tidied
WAITING_DAYS = 7        # quiet this long when it was waiting on the person
FILE = "tidy.json"      # in profile/: what was archived, so it can be brought back
CHECKED = "ljs-tidy.json"   # in the git folder, never committed: the day it last ran
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


def due(today: str = "") -> bool:
    """Is today's tidy-up still to do? Only once a day, and never where it cannot be kept."""
    today = today or dt.date.today().isoformat()
    path = _checked_path()
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("checked") != today
    except (OSError, ValueError, AttributeError):
        return True


def _mark_checked(today: str) -> None:
    path = _checked_path()
    if not path:
        return
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"checked": today}, fh)
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


# ------------------------------------------------------------------ reading what the tools gave


def _pages(paths) -> list:
    out = []
    for p in paths or []:
        with open(p, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


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
         branches: set[str] | None, done_before: set[str]) -> dict:
    """{"ask": [ids to read with get_session], "archive": [{id, title, why}],
    "keep": [{id, title, why}], "brief": [calls] or []}."""
    import routines
    live_ids = {listener.get("chat") or "", this_chat} - {""}
    known = {listener.get("took_from") or ""} - {""}
    bound_on = {t.get("session") for t in triggers if t.get("session") and t.get("enabled")}
    ops = str((reg.get("ops_session") or {}).get("id") or "")
    brief = next((r for r in reg.get("routines") or [] if routines._is_brief(r)), None) or {}
    brief_chat = str((brief.get("chat") or {}).get("session_id") or "")
    out: dict = {"ask": [], "archive": [], "keep": [], "brief": []}

    # The brief in a chat of its own moves into the chat that answers the page. A brief in
    # the older ops chat stays there while that chat lives (it relays to the phone); once
    # the chat is gone, the task wakes a new empty chat with no copy of the files every
    # morning ("Morning brief could not start: no git repo", 2026-10-31), so it moves too.
    adopt = ""
    helper = listener.get("chat") or ""
    setup = routines.setup_of(reg)
    home = brief_chat or (ops if setup == "ops_relay" else "")
    if (setup in ("chat_per_briefing", "ops_relay") and home and helper.startswith("session_")
            and home != helper and not brief.get("off") and not reg.get("pause")
            and brief.get("trigger_id") and brief.get("cron")):
        live = next((t for t in triggers if t.get("id") == brief["trigger_id"]), None)
        # Gone, for the ops chat: not among the person's chats, and the task itself now
        # names another chat, one that works on no copy at all (the empty one it woke
        # instead). All three, so a listing that missed a page never moves a brief whose ops
        # chat still relays, and a brief someone bound to a chat of their own stays there.
        listed_ids = {s.get("id") for s in chats}
        woke = str((live or {}).get("session") or "")
        gone = False
        if home == ops and home not in listed_ids and woke not in ("", home, helper):
            if woke not in listed_ids:
                gone = True
            elif woke not in info:
                out["ask"].append(woke)
            else:
                gone = not _repo_of(info[woke])
        if live and live.get("enabled") and (home != ops or gone):
            adopt = home
            stub = routines.stub(reg, brief["key"], own_chat=True)
            out["brief"] = [
                {"tool": "create_trigger", "args": {
                    "name": routines.BRIEF_NAME, "persistent_session_id": helper,
                    "cron_expression": brief["cron"], "prompt": stub, "connectors": [],
                    "initiation": "own_initiative"},
                 "why": "the brief runs in the chat that answers the page from now on"},
                {"run": f"python3 tools/routines.py record --session {helper} --trigger "
                        f"<the new task's id> --cron \"{brief['cron']}\""
                        + (" --own-chat" if setup == "ops_relay" else ""),
                 "why": "the registry names the new task and its chat"},
                {"tool": "update_trigger", "args": {"trigger_id": brief["trigger_id"],
                                                    "enabled": False},
                 "why": "the old task is turned off, never deleted"}]

    if adopt and adopt not in {s.get("id") for s in chats}:
        # Its chat was deleted: the task fails every morning, so it moves to the helper, and
        # there is nothing to archive.
        out["keep"].append({"id": adopt, "title": "", "why": "the brief's chat is gone; the "
                                                            "brief moves to the helper"})
    for s in chats:
        sid = s.get("id") or ""
        title = str(s.get("title") or "")
        def keep(why, sid=sid, title=title):
            out["keep"].append({"id": sid, "title": title, "why": why})
        if sid in done_before:
            continue
        if not (APP_TITLE.match(title) or sid in known):
            continue                                  # the person's own chat: never listed
        if sid in live_ids:
            keep("it answers the page" if sid == listener.get("chat") else "it is this chat")
            continue
        if sid == ops:
            keep("the older ops chat, which relays to the phone and is never rebuilt")
            continue
        if sid in bound_on and sid != adopt:
            keep("a scheduled task that is on runs in it")
            continue
        if sid in campaigns:
            keep("a live process has its own chat here")
            continue
        status = str(s.get("session_status") or "") + " " + str(s.get("status_bucket") or "")
        if "RUNNING" in status or "WORKING" in status:
            keep("it is running")
            continue
        quiet = _days_since(s.get("updated_at") or s.get("created_at") or "", today)
        waits = "REQUIRES_ACTION" in status or "BLOCKED" in status
        if sid != adopt and quiet < (WAITING_DAYS if waits else IDLE_DAYS):
            keep(f"used {quiet:.0f} day(s) ago")
            continue
        d = info.get(sid)
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
        why = ("the brief moved into the chat that answers the page" if sid == adopt else
               "a helper the page no longer uses" if sid in known or re.search(r"helper", title, re.I)
               else "a chat for one run or one job, finished")
        out["archive"].append({"id": sid, "title": title, "why": why})
    listed = {s.get("id") for s in chats}
    if adopt and adopt in listed and not any(a["id"] == adopt for a in out["archive"]):
        out["brief"] = []                             # its chat is kept: the brief stays put
    out["ask"] = list(dict.fromkeys(out["ask"]))
    if out["ask"]:
        out["brief"] = []                             # decided once every chat is read
    return out


def _listener(dump: str) -> dict:
    """The chat that answers the page: from this wake's dump, else what this checkout last
    saw (the brief's run has no dump)."""
    import app_listen
    if dump:
        import page_db
        try:
            rec, _ = app_listen.record(page_db.load(dump))
            if rec:
                return rec
        except Exception:  # noqa: BLE001  not a dump: what was seen
            pass
    return dict(app_listen.seen().get("listener") or {})


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


def run_plan(a) -> int:
    import routines
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    tasks: list = []
    for page in _pages(a.triggers):
        tasks += routines.listing(page)[0]
    try:
        reg = routines.load()
    except Exception:  # noqa: BLE001  no registry: no brief, no ops chat
        reg = {}
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
    got = plan(sessions(_pages(a.sessions)), tasks, details(_pages(a.details)), reg,
               listener, app_listen.this_chat(a.chat), repo, today,
               _campaign_chats(), unmerged(), {x["id"] for x in archived()})
    if got["ask"]:
        print("tidy: read these chats first, each with get_session, and run this again with "
              "--details <each file>: " + " ".join(got["ask"]))
        return 0
    for i, c in enumerate(got["brief"], 1):
        if c.get("tool"):
            print(f"brief {i}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
        else:
            print(f"brief {i}: {c['run']} ({c['why']})")
    if got["brief"]:
        print("brief: make these in order and stop at the first that fails; archive the old "
              "brief's chat only once all three are made")
    for c in got["archive"]:
        print(f"archive {c['id']}: {c['title']} ({c['why']})")
    if got["archive"]:
        ids = " ".join(c["id"] for c in got["archive"])
        titles = json.dumps({c["id"]: c["title"] for c in got["archive"]}, ensure_ascii=False)
        print(f"then: archive_session each, and python3 tools/tidy.py done <each one archived> "
              f"--titles '{titles}' (all of them: {ids}); commit it")
    else:
        print("tidy: nothing to tidy. python3 tools/tidy.py done")
    if a.verbose:
        for c in got["keep"]:
            print(f"keep {c['id']}: {c['title']} ({c['why']})")
    return 0


def run_done(ids: list[str], titles: dict, today: str) -> str:
    """Record what was archived (profile/tidy.json) and that today's tidy-up ran."""
    _mark_checked(today)
    if not ids:
        return "tidy: done for today"
    path = _record_path()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    have = {a.get("id") for a in got.get("archived") or []}
    got["archived"] = list(got.get("archived") or []) + [
        {"id": i, "title": titles.get(i, ""), "on": today} for i in ids if i not in have]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    n = len(ids)
    return "tell them, if they are in this chat: " + SAY_DONE.format(n=n, s="" if n == 1 else "s")


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
    p.add_argument("--chat", default="")
    p.add_argument("--today", default="")
    p.add_argument("--verbose", action="store_true")
    o = sub.add_parser("done")
    o.add_argument("ids", nargs="*")
    o.add_argument("--titles", default="{}")
    o.add_argument("--today", default="")
    sub.add_parser("undo")
    a = ap.parse_args(argv)
    if a.cmd == "due":
        return 0 if due(a.today) else 1
    if a.cmd == "plan":
        if not a.sessions:
            print("tidy: list the chats first (list_sessions, mine: true, every page) and pass "
                  "each page with --sessions", file=sys.stderr)
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
