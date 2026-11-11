#!/usr/bin/env python3
"""The computer side: the one thing the person's own computer is needed for, a LinkedIn read
in the Claude desktop app's own browser, done without them having to think about where.

Work that needs a LinkedIn read is sent to the computer (`to: computer`, tools/page_db.py
computer_only): no cloud chat claims, finishes or fails it. It is done in the best place
there is, tried in this order (`route`), and the page says which in one line:

  1. a chat already working on the computer takes it (`computer chat`);
  2. a cloud chat starts a chat on the computer itself (`computer session`): the computer
     shows in list_environments as a bridge environment once its settings allow it
     (claude_surfaces: remote-control-settings, computer-bridge); create_session there, in
     Auto, named "Job search · <job> · <computer>", with a prompt complete from the start.
     Its results come back through the page's database and the person's copy, never a
     message between chats (claude_surfaces: session-approvals), and the starter chat, "Job
     search: starts chats on your computer", archives it once its work is finished
     (`finished`), whichever chat answers the page by then;
  3. the scheduled task on the computer (claude_surfaces: routines-local) takes it on its
     next run, while the desktop app is open there (`computer task`);
  4. a folder the computer offers to cloud chats (claude_surfaces: folder-attach), where it
     does (`computer folder`);
  5. a cloud chat lent the computer's browser (claude_surfaces: cloud-linked-browser) does it
     itself, as a computer chat (`linked browser`);
  6. nothing reaches the computer: the page says so in one line, with one action, and the
     person can paste the profiles instead (`paste`).

The computer says how it is in a heartbeat (`beat`), the page's `chats` record
`computer~<name>`: when it was last seen, which computer, whether Claude's browser is showing
and signed in to LinkedIn, whether it keeps its sign-in after the app quits, how the last
read went, the scheduled task, and the app's version there. From it `state` makes the one
line the page shows and, only while computer work waits and the person is needed, one To do
card. `check` is what the day's sync and the brief say about it.

Every computer run is measured from its own transcript (`measure`): the time each stage
took, tool calls by tool, LinkedIn pages by kind, web searches, tokens and an estimated cost
(claude_surfaces: session-usage), kept on the work item and in documents/computer_runs.json,
whose trend the brief reports (`trend`).

    python3 tools/computer.py beat <dump> [--browser shown|hidden|none]
        [--linkedin in|out|unknown] [--cookies on|off|unknown] [--read ok|stopped|none]
    python3 tools/computer.py state <dump> [--envs FILE]       # the page's one line, as JSON
    python3 tools/computer.py waiting <dump>                   # computer work and its chats
    python3 tools/computer.py route <dump> --chat ID [--envs FILE] [--folders FILE] [--tools T]
    python3 tools/computer.py started <dump> --work ID --session ID --env ID --computer NAME
    python3 tools/computer.py archived <dump> --work ID
    python3 tools/computer.py starter-woke <dump>              # the starter answered a wake
    python3 tools/computer.py starter-seen <dump> --status S   # get_session's word on a silent one
    python3 tools/computer.py saved-here <dump> --chat ID     # its save kept here: said on the page
    python3 tools/computer.py tidy-folders [<dump>]           # the chats' merged, clean folders removed
    python3 tools/computer.py signed-in <dump> --work ID          # its own sign-in question, answered
    python3 tools/computer.py signin-wait <dump> --work ID --url A [--every S]  # one look at the sign-in
    python3 tools/computer.py measure <dump> --work ID --chat ID [--transcript FILE]
    python3 tools/computer.py check <dump> [--envs FILE]       # the sync's and the brief's lines
    python3 tools/computer.py trend [--days 7]
    python3 tools/computer.py memory                           # chat memory that disagrees with profile/, removed
    python3 tools/computer.py archivable <saved list>           # the app's earlier chats here to archive
    python3 tools/computer.py shell "<command>"                # does it run the same in zsh and bash?

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# The heartbeat's record in the page's `chats`: one per computer, kept across its chats.
BEAT_PREFIX = "computer~"
# Seen this recently: Claude is open there now.
FRESH_S = 20 * 60
# Not seen for this long: the computer is off, or Claude is closed on it.
OFF_S = 2 * 3600
# Not seen for this long while it was set up: its chat, folder or task may have been deleted.
GONE_S = 7 * 24 * 3600
# A LinkedIn sign-in that held this long, between two looks, after one was lost: the browser
# keeps it now (cookies_seen).
SIGNIN_HELD_S = 20 * 3600
# Computer work waiting this long with nothing to start it puts one card on To do.
CARD_AFTER_S = 10 * 60
# A chat started on the computer is believed to be at work for this long (its claim's lease
# then says the rest): no second one is started for the same work meanwhile.
STARTED_S = 30 * 60
# A chat on the computer that found LinkedIn signed out opens the sign-in page in Claude's
# browser, puts the Sign in to LinkedIn card on the page and looks again by itself for this
# long, carrying on the moment they are signed in (`signin-wait`). Meanwhile it is at work,
# never put away; after it, it ends, and a fresh one carries on once they sign in. Stopped at
# once, the job was parked and its chat put away the minute LinkedIn was found signed out,
# and a sign-in made then started nothing for half an hour (the maintainer, 2026-11-10).
SIGNIN_WAIT_S = 15 * 60
# One look every three minutes, each one command that reads the work item afresh and the
# sign-in tab's address (`signin-wait --url`): a look a minute, three calls each at the chat's
# full context, was up to 45 calls, and it read the copy of the page taken before the wait, so
# a sign-in made on the page or a Stop tapped there was never seen (the efficiency audit,
# 2026-11-10, E-10).
SIGNIN_LOOK_S = 3 * 60
SIGNIN_LOOK = ("tabs_context for the sign-in tab's address, then ArtifactData query, url {url}, "
               "collection work, out_dir \"$D\", limit 1000 (the item as the page holds it "
               "now), then python3 tools/computer.py signin-wait \"$D\" --work {wid} --url "
               "<that address>, as a Bash call with timeout 240000 (it waits three minutes "
               "between looks)")
# The name of every chat the app starts on the computer: recognisable, and safe to delete.
SESSION_TITLE = "Job search · {job} · {computer}"
# The scheduled task on the computer that takes waiting work while no cloud chat is awake
# (claude_surfaces: routines-local): a fresh chat each run, in the copy's folder, in Auto. It
# is the fallback, not the way: a chat started from the cloud takes work within a minute, so
# the task runs hourly, and a run with nothing waiting stops at its first step, costing little.
TASK_NAME = "job-search-computer"
TASK_EVERY_MIN = 60
TASK_PROMPT = ("Take the work waiting for this computer on my job search page: run python3 "
               "tools/computer.py task-check and do exactly what it prints. With nothing "
               "waiting it stops at its second step, saying nothing.")
RUNS_FILE = ("documents", "computer_runs.json")
RUNS_KEEP_DAYS = 90
BROWSER = ("shown", "hidden", "none")
LINKEDIN = ("in", "out", "unknown")
COOKIES = ("on", "off", "unknown")
READS = ("ok", "stopped", "none")

# What the person sees: one line a state, and at most one action (templates/app/DESIGN.md).
# The steps of an action come from tools/claude_surfaces.json, never written here.
SAY = {
    "ready": "Your computer is ready: Claude reads LinkedIn there when it needs to.",
    "working": "Claude is reading LinkedIn on your computer now.",
    "off": ("Your computer is off or Claude isn't open on it: open Claude there and this "
            "starts by itself."),
    "gone": ("Claude hasn't been able to start on your computer for a week: set it up again "
             "once and it starts by itself."),
    "signed_out": "LinkedIn is signed out in Claude's browser on your computer: sign in there once.",
    "signed_out_lost": ("LinkedIn signed out in Claude's browser on your computer: sign in again "
                        "and keep the sign-in this time."),
    "forgets": ("Claude's browser on your computer forgets LinkedIn each time the app quits: "
                "keep its sign-in once."),
    "paused": "LinkedIn asked Claude to slow down: reading starts again tomorrow, by itself.",
    "no_bridge": "Claude can't start on your computer yet: switch it on once in the Claude app there.",
    "not_set_up": "Claude doesn't use your computer yet. Set it up once to read LinkedIn profiles there.",
    "no_computer": "No computer for this: paste each person's profile on their card instead.",
    "signin_unsure": ("You signed in to LinkedIn on your page; Claude checks the browser on your "
                      "computer the next time it reads there."),
    "starter_waits": ("Claude's chat that starts work on your computer is waiting for you: open "
                      "it in the Claude app and approve what it asks, once."),
    "starter_silent": ("Claude's chat that starts work on your computer isn't answering: open it "
                       "in the Claude app once."),
}
# The registry entry whose steps each action shows, and its button's words.
ACTION = {
    "off": None,
    "gone": ("remote-control-settings", "Set it up again"),
    "signed_out": ("browser-pane-stay-signed-in", "Sign in once"),
    "signed_out_lost": ("browser-pane-stay-signed-in", "Sign in again"),
    "forgets": ("browser-pane-stay-signed-in", "Stay signed in"),
    "no_bridge": ("remote-control-settings", "Switch it on"),
    "not_set_up": ("remote-control-settings", "Set it up"),
    "starter_waits": None,
    "starter_silent": None,
    "signin_unsure": None,
}
# The To do card's words: one plain sentence naming the work that waits and what it waits
# for, then its one step. "Waiting for your computer: LinkedIn is signed out in Claude's
# browser on your computer: sign in there once." said "your computer" twice, had two colons and
# never said what was waiting (the screen review, 2026-11-09).
WAITING_SAY = {
    "off": "{what} until Claude is open on your computer. Open Claude there and it starts by "
           "itself.",
    "gone": "{what} because Claude has not started on your computer for a week. Set it up "
            "again once.",
    "signed_out": "{what} until you sign in to LinkedIn in Claude's browser. Open LinkedIn and "
                  "sign in once.",
    "signed_out_lost": "{what} because LinkedIn signed out in Claude's browser. Sign in again, "
                       "and keep the sign-in this time.",
    "forgets": "{what} because Claude's browser forgets your LinkedIn sign-in when the app "
               "quits. Keep the sign-in once.",
    "no_bridge": "{what} until Claude is switched on for your computer. Switch it on once in "
                 "the Claude app there.",
    "not_set_up": "{what} until Claude is set up on your computer. Set it up once.",
    "starter_waits": "{what} until you approve one step in Claude's chat that starts work on "
                     "your computer. Open that chat in the Claude app and approve what it asks.",
    "starter_silent": "{what} because Claude's chat that starts work on your computer is not "
                      "answering. Open that chat in the Claude app once.",
}
# Where the card's one step is a page LinkedIn opens in Claude's own browser, it is on the
# card's face, as the LinkedIn setup card's is (tools/app_setup.py outside_item).
LINKEDIN_LOGIN = {"label": "Open LinkedIn", "url": "https://www.linkedin.com/login"}


def waiting_words(titles: list) -> str:
    """'“People at Harbourline Bank” waits', '“...” and 2 more wait', or
    'Your LinkedIn work waits' where the work has no title."""
    first = next((t for t in titles if t), "")
    if not first:
        return ("Your LinkedIn work waits" if len(titles) < 2 else
                f"{len(titles)} pieces of LinkedIn work wait")
    more = len(titles) - 1
    return f"“{first}” waits" if not more else f"“{first}” and {more} more wait"


def _stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _time(s) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _now(given: str | None = None) -> dt.datetime:
    return _time(given) if given else dt.datetime.now(dt.timezone.utc)


def _plain_name(name: str) -> str:
    """A computer's name as the person calls it: "Mac" from a bridge's "Mac:Documents:4ba6"."""
    name = " ".join(str(name or "").split())
    return (name.split(":")[0].strip() or name)[:40] or "your computer"


def runs_there(computer: str) -> str:
    """Said up front where a chat is started on the person's computer for a job: the route's
    line and the step its work card shows while it runs (the maintainer, 2026-11-10: a chat
    appeared on the computer with nothing on the page saying so)."""
    name = _plain_name(computer)
    where = name if name == "your computer" else "your " + name
    return f"This runs in a chat on {where}, which you can delete when it's done."


# ------------------------------------------------------------------ the computer starter

# The one chat that holds the computer approval (confirm_repository_trust) and does nothing but
# start the chats on the person's computer and put them away. Approving ties a chat to the
# person's own devices for good: from then on no chat could archive it, itself included, no
# scheduled task could fire into it and no other chat's message reached it. When the page's
# helper held it, every daily hand-over left an old "Job search page (finishing up)" chat in
# the sidebar for the person to delete by hand (the maintainer, 2026-11-10). So the helpers
# never approve: they stay ordinary chats, carry the work, and archive themselves.
#
# Nothing a person taps rings it, and no chat may message it, so it is woken the one way
# that needs nobody's approval: it publishes a tiny page of its own (the bell) and watches
# it, and any chat that has computer work for it republishes the bell ("this session is
# woken with a new turn when the watched artifact is republished elsewhere": the Artifact
# watch). Its record is the page's `meta/computer_starter`: {chat, bell, made_at, rung_at}.
STARTER_DOC = ("meta", "computer_starter")
STARTER_TITLE = "Job search: starts chats on your computer"
# A starter asked for and not ready (no bell yet) this long: made again.
STARTER_WAIT_S = 30 * 60
# A ring answered by nothing this long is rung again.
RING_S = 10 * 60
BELL_TITLE = "Job search computer bell"
# Rung this many times in a row with nothing answering (no chat started or put away since,
# no wake of its own): it is looked at with get_session before it is rung again. Rung for good,
# a starter the person had deleted, or one waiting on their approval in a chat they never
# open, left the work "ready" on the page with the bell ringing every ten minutes (the builder
# audit, 2026-11-10, CC-6). Looked at alive this many times and still not answering: the
# person is asked, on a To do card, to open it.
STARTER_SILENT_RINGS = 2
STARTER_SILENT_CHECKS = 2
# What get_session says of a starter that is no more: made again. Waiting on the person (an
# approval card): never made again, the card asks them instead (CC-14).
STARTER_GONE = ("gone", "archived", "deleted", "not_found", "not found", "missing")
STARTER_BLOCKED = ("blocked", "waiting", "needs_approval", "requires_action")


def starter(db: dict) -> dict:
    """The computer starter's record on the page, or {}."""
    doc = ((db.get(STARTER_DOC[0]) or {}).get(STARTER_DOC[1]) or {})
    return dict(doc.get("data") or {}) if isinstance(doc, dict) else {}


def is_starter(db: dict, chat: str) -> bool:
    return bool(chat) and str(starter(db).get("chat") or "") == chat


def starter_prompt(url: str, copy: str) -> str:
    """What the computer starter is told once, complete: every wake does the same few steps."""
    return "\n".join([
        "This chat starts the chats on my computer for my job search, and nothing else. It "
        f"never answers my page, never publishes it and never messages another chat. Its copy "
        f"is {copy or 'the one attached'}; my page is {url}. Say nothing to me unless a step "
        "below says to.",
        "First, once: python3 tools/sync_app.py --if-stale --on \"<your model>\" --tools none "
        "(nothing else of the start command: this chat is not the page's). Then python3 "
        "tools/computer.py bell-file \"<your scratchpad>/bell.html\" and publish that file with "
        f"the Artifact tool (icon: bell, a new page, no url): publishing it is what lets other "
        "chats wake this one. Then read the page's meta into a fresh folder $D (ArtifactData "
        f"query, url {url}, collection meta, out_dir $D, limit 1000) and run python3 "
        "tools/computer.py starter-ready \"$D\" --chat <your id> --bell <the bell's url>, and "
        "send its batch (ArtifactData batch).",
        "Then, now and every time this chat is woken (the bell republished): read the page's "
        "work, beats and meta into a fresh folder $D (one ArtifactData query each, out_dir $D, "
        "limit 1000). python3 tools/computer.py starter-woke \"$D\" and send its batch (it "
        "says this chat answered). python3 tools/computer.py waiting \"$D\": under `finished`, "
        "archive_session each session (get_session on it first: archived already, it is done, "
        "never archived again), then python3 tools/computer.py archived \"$D\" --work "
        "<its id> and send the batch, whatever archive_session answered (not found or already "
        "archived count as put away: unrecorded, it was rung for again at every wake), except "
        "a refusal because that chat is still at work: then the same command with --refused, "
        "and it is asked again later; then python3 tools/land.py in the background "
        "(run_in_background) and the GitHub calls it prints: it brings the work the chat on "
        "the computer saved to master, which no chat there may merge. Under `queued`: list_environments, saved to a file, then "
        "python3 tools/computer.py route \"$D\" --chat <your id> --envs <that file> --tools "
        "\"<this chat's tool names, comma separated>\", and do what it prints: a `call` exactly "
        "as printed, then its `then`. Then end the turn with nothing said.",
    ])


# The page's data tools a chat the app starts is given pre-approved, as app.py CHILD_TOOLS.
STARTER_TOOLS = ("ArtifactData", "ArtifactComments")


def starter_call(url: str, copy: str, owner: str, name: str) -> dict:
    """The create_session that makes the computer starter, from the person's copy."""
    import app_listen
    return {"title": STARTER_TITLE, "prompt": starter_prompt(url, copy),
            "source_url": f"https://github.com/{owner}/{name}",
            "extra_allowed_tools": list(STARTER_TOOLS),
            "permission_mode": app_listen.SESSION_MODE}


def bell_html(now: dt.datetime) -> str:
    """The bell page: a few plain words, and the moment it was rung, so each publish differs."""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport"
            "\" content=\"width=device-width,initial-scale=1\"><title>" + BELL_TITLE + "</title>"
            "<style>:root{--bg:#fbfaf7;--fg:#2b2a27}@media (prefers-color-scheme:dark){:root:not("
            "[data-theme=\"light\"]){--bg:#1c1b19;--fg:#ecebe6}}:root[data-theme=\"dark\"]{--bg:"
            "#1c1b19;--fg:#ecebe6}body{background:var(--bg);color:var(--fg);font:16px/1.5 "
            "system-ui,sans-serif;margin:0;padding:24px 16px}</style></head><body><p>This page "
            "wakes the chat that starts Claude on your computer for your job search. Nothing "
            "to do here.</p><p><small>" + _stamp(now) + "</small></p></body></html>\n")


def write_bell(path: str, now: dt.datetime) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(bell_html(now))
    return path


def _starter_set(db: dict, fields: dict, out_dir: str, dump_dir: str = "",
                 label: str = "starter") -> list[str]:
    import page_db
    doc = (db.get(STARTER_DOC[0]) or {}).get(STARTER_DOC[1])
    w = page_db.Writes(out_dir)
    if doc:
        w.add("update", *STARTER_DOC, fields, if_version=doc.get("version"))
        new = dict(doc.get("data") or {}, **fields)
    else:
        w.add("set", *STARTER_DOC, fields)
        new = dict(fields)
    if dump_dir:
        page_db._keep_dump(dump_dir, *STARTER_DOC, new,
                           int((doc or {}).get("version") or 0) + 1)
    return w.save(label)


def starter_made(db: dict, session: str, now: dt.datetime, out_dir: str,
                 dump_dir: str = "") -> list[str]:
    """A new computer starter was asked for: kept, with no bell yet."""
    return _starter_set(db, {"chat": session, "bell": "", "made_at": _stamp(now),
                             "rung_at": None}, out_dir, dump_dir)


def starter_ready(db: dict, chat: str, bell: str, now: dt.datetime, out_dir: str,
                  dump_dir: str = "") -> list[str]:
    """The starter published its bell and watches it: any chat can wake it now."""
    return _starter_set(db, {"chat": chat, "bell": bell, "ready_at": _stamp(now)}, out_dir,
                        dump_dir)


def answered_since(db: dict, since: dt.datetime | None) -> bool:
    """Has the starter done anything since `since`: a chat started on the computer, or one put
    away (work's computer_session), or its own wake or bell. Read from what it writes anyway,
    so a starter made before this was known still answers."""
    if since is None:
        return False
    rec = starter(db)
    for k in ("woke_at", "ready_at"):
        t = _time(rec.get(k))
        if t and t >= since:
            return True
    for doc in (db.get("work") or {}).values():
        sess = ((doc or {}).get("data") or {}).get("computer_session")
        if not isinstance(sess, dict):
            continue
        for k in ("at", "archived_at"):
            t = _time(sess.get(k))
            if t and t >= since:
                return True
    return False


def unanswered(db: dict) -> int:
    """How many rings in a row the starter has not answered (0 once it has)."""
    rec = starter(db)
    if answered_since(db, _time(rec.get("rung_at"))):
        return 0
    return int(rec.get("rings") or 0)


def starter_stuck(db: dict) -> str:
    """"waits" (the starter is waiting on the person: get_session said so, and it has not
    answered since), "silent" (looked at alive STARTER_SILENT_CHECKS times and still not
    answering), or "" when nothing is known to be wrong with it."""
    rec = starter(db)
    if not rec.get("chat"):
        return ""
    checked = _time(rec.get("checked_at"))
    if answered_since(db, checked):
        return ""
    if rec.get("waits_on_person"):
        return "waits"
    if int(rec.get("silent") or 0) >= STARTER_SILENT_CHECKS:
        return "silent"
    return ""


def rung(db: dict, now: dt.datetime, out_dir: str, dump_dir: str = "") -> list[str]:
    """The bell was republished: kept, with how many rings in a row went unanswered."""
    rec = starter(db)
    rings = 1 if answered_since(db, _time(rec.get("rung_at"))) or not rec.get("rung_at") \
        else int(rec.get("rings") or 0) + 1
    return _starter_set(db, {"rung_at": _stamp(now), "rings": rings}, out_dir, dump_dir,
                        "starter-rung")


def starter_woke(db: dict, now: dt.datetime, out_dir: str, dump_dir: str = "") -> list[str]:
    """The starter was woken and is at work: no ring is unanswered, and nothing waits on the
    person for it."""
    return _starter_set(db, {"woke_at": _stamp(now), "rings": 0, "silent": 0,
                             "waits_on_person": None}, out_dir, dump_dir, "starter-woke")


def starter_seen(db: dict, status: str, now: dt.datetime, out_dir: str,
                 dump_dir: str = "") -> list[str]:
    """What get_session said of a starter that did not answer (`check starter`): gone, its
    record is cleared so the next route makes a new one; waiting on the person, a To do card
    asks them (starter_stuck); at work or idle, it is left, and looked at again later."""
    rec = starter(db)
    said = " ".join(str(status or "").lower().replace("-", "_").split())
    at = _stamp(now)
    if said in STARTER_GONE or any(w in said for w in ("archiv", "not found", "deleted")):
        fields = {"chat": "", "bell": "", "made_at": None, "rung_at": None, "rings": 0,
                  "silent": 0, "waits_on_person": None, "checked_at": at, "checked": said,
                  "gone": {"chat": rec.get("chat") or "", "at": at}}
    elif said in STARTER_BLOCKED:
        fields = {"checked_at": at, "checked": said, "waits_on_person": at}
    else:
        fields = {"checked_at": at, "checked": said or "unknown", "rings": 0,
                  "waits_on_person": None, "silent": int(rec.get("silent") or 0) + 1}
    return _starter_set(db, fields, out_dir, dump_dir, "starter-seen")


def ring_steps(bell: str, path: str) -> str:
    """How any chat wakes the computer starter: the bell republished, its own watch on the bell
    stopped (a publish can start one, and the starter's next ring would wake this chat too)."""
    return (f"Artifact publish with file_path {path} and url {bell} (read it first only if the "
            "publish is refused; never a new page), then ArtifactComments watch with url "
            f"{bell} and on: false, then python3 tools/computer.py rung <dump> and send its "
            "batch. Say nothing about it to the person.")


def _starter_check(rec: dict, wid: str, line: str, w: dict) -> dict:
    """The starter did not answer, or is not ready long after it was asked for: looked at."""
    return {"route": "check starter", "work": wid, "line": line,
            "call": {"session_id": rec.get("chat") or ""},
            "then": ("get_session with this call, then python3 tools/computer.py starter-seen "
                     "<dump> --status <its status_bucket, or gone where it says the chat is "
                     "not found or archived>, and send its batch, then route again. Never "
                     "send_message it, and say nothing about it to the person: where it waits "
                     "on them, their page asks them."),
            "waiting": w}


def _starter_route(db: dict, now: dt.datetime, wid: str, w: dict, url: str, copy: str,
                   line: str) -> dict:
    """For any chat but the starter: wake the computer starter, or make it once."""
    rec = starter(db)
    item = ((db.get("work") or {}).get(wid) or {}).get("data") or {}
    asked = _time(item.get("asked_at"))
    checked = _time(rec.get("checked_at"))
    looked_lately = bool(checked and (now - checked).total_seconds() < STARTER_WAIT_S)
    stuck = starter_stuck(db)
    if rec.get("chat") and stuck and looked_lately:
        # It waits on the person, or is not answering: the page's To do card asks them
        # (state, card); ringing it again or making another changes nothing (CC-6, CC-14).
        return {"route": "starter waits", "work": wid, "line": line, "waiting": w}
    if rec.get("chat") and rec.get("bell"):
        last = _time(rec.get("rung_at"))
        if last and (now - last).total_seconds() < RING_S and not (asked and asked > last):
            return {"route": "starter rung", "work": wid, "line": line, "waiting": w}
        if unanswered(db) >= STARTER_SILENT_RINGS and not looked_lately:
            return _starter_check(rec, wid, line, w)
        return {"route": "ring starter", "work": wid, "line": line, "bell": rec["bell"],
                "then": ("python3 tools/computer.py bell-file <your scratchpad>/bell.html, then "
                         + ring_steps(rec["bell"], "<your scratchpad>/bell.html")),
                "waiting": w}
    made = _time(rec.get("made_at"))
    if rec.get("chat") and made and (now - made).total_seconds() < STARTER_WAIT_S:
        return {"route": "starter starting", "work": wid, "line": line, "waiting": w}
    if rec.get("chat") and not looked_lately:
        # Asked for and still not ready: looked at before another is made. A slow first run
        # (the update, the Auto switch, the approval card waiting on the person) made a second
        # starter, and an approved one can never be put away (CC-14).
        return _starter_check(rec, wid, line, w)
    if rec.get("chat"):
        return {"route": "starter starting", "work": wid, "line": line, "waiting": w}
    try:
        import app_setup
        owner, name = app_setup.origin()
    except Exception:  # noqa: BLE001  no address to start it from
        owner, name = "", ""
    if not owner or not name:
        return {"route": "none", "line": "", "waiting": w}
    import app_listen
    return {"route": "make starter", "work": wid, "line": line,
            "call": starter_call(url, copy, owner, name),
            "then": ("create_session with this call, from this chat, unasked." +
                     app_listen.MODE_REFUSED + " Started: python3 tools/computer.py "
                     "starter-made <dump> --session <its id>, and send its batch. It starts the "
                     "chat on the computer itself; this chat never approves computer access. "
                     "Say nothing about it to the person."),
            "waiting": w}


# ------------------------------------------------------------------ the heartbeat


def this_computer(typed: str = "") -> str:
    """This computer's name, worked out here rather than typed: the name the computer gives
    itself (macOS's ComputerName, else its host name), else the one the setup kept
    (profile/place.json computer_name), and a typed one only where neither is known. Typed,
    "Mac" made a second record beside the real one (the builder audit, 2026-11-10, CC-21);
    place.json first, every computer of the person's wrote under the one name kept there,
    which travels with the copy (the independent review, 2026-11-11)."""
    own = ""
    if sys.platform == "darwin":
        try:
            import subprocess
            own = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=5).stdout.strip()
        except Exception:  # noqa: BLE001  not answered: the host name
            own = ""
    if not own:
        import platform
        own = platform.node().split(".")[0].strip()
    if own:
        return own
    try:
        import place
        kept = str(place.place_record().get("computer_name") or "").strip()
    except Exception:  # noqa: BLE001  no profile here
        kept = ""
    return kept or str(typed or "").strip() or "your computer"


def beat_id(name: str) -> str:
    import page_db
    return page_db.safe_id(BEAT_PREFIX + re.sub(r"[^A-Za-z0-9]+", "-", _plain_name(name)).strip("-").lower())


def app_version() -> str:
    """The app's version in this copy: the newest CHANGELOG section, as the page says it."""
    try:
        import release
        secs = release.sections()
        return str(secs[0]["version"]) if secs else ""
    except Exception:  # noqa: BLE001  no changelog to read: unknown, said as nothing
        return ""


def task_present(home: str | None = None) -> bool:
    """Is the app's scheduled task on this computer? The desktop app keeps each task's prompt
    at ~/.claude/scheduled-tasks/<task-name>/SKILL.md (claude_surfaces: routines-local)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home or os.path.expanduser("~"), ".claude")
    return os.path.isfile(os.path.join(base, "scheduled-tasks", TASK_NAME, "SKILL.md"))


def stop_here() -> dict | None:
    """Today's LinkedIn stop on this computer (a check, an error 999 or 429 page, a sign-out
    out of turn), from its own reading ledger, as the heartbeat carries it to the cloud and the
    page: {"on", "kind", "why"}, or None. The ledger is a cache on each machine, so the cloud
    read it empty, said nothing was paused, and queued a new read for the computer that same
    day, each one starting a chat that met the same stop (the builder audit, 2026-11-10, CC-9)."""
    try:
        sys.path.insert(0, os.path.join(_HERE, "network"))
        import reading
        got = reading._stop_today()
        if not got:
            return None
        kind = str(got.get("kind") or reading._signal_kind(got.get("reason")))
    except Exception:  # noqa: BLE001  no ledger to read here: nothing measured
        return None
    day = str(got.get("date") or "")
    # The stop holds to the end of the computer's own day, where it was recorded: carried as a
    # moment (`until`), so the cloud never compares the computer's date with the person's,
    # which in another zone is a day apart (the independent review, 2026-11-11: two clocks).
    try:
        end = dt.datetime.combine(dt.date.fromisoformat(day) + dt.timedelta(days=1),
                                  dt.time(0)).astimezone()
        until = _stamp(end)
    except ValueError:
        until = None
    return {"on": day, "until": until, "kind": kind,
            "why": " ".join(str(got.get("reason") or "").split())[:200]}


def stopped_today(beat_: dict, now: dt.datetime) -> dict | None:
    """The stop the computer's heartbeat says holds on the person's day `now`, or None: one
    from an earlier day is over (reads start again by themselves the next day)."""
    stop = beat_.get("stop") if isinstance(beat_.get("stop"), dict) else None
    if not stop:
        last = beat_.get("last_read") if isinstance(beat_.get("last_read"), dict) else None
        # A run that ended with its reads stopped (`--read stopped`) and no stop measured.
        if last and last.get("ok") is False and _time(last.get("at")):
            stop = {"on": _day(_time(last["at"])), "kind": "check", "why": ""}
    if not stop:
        return None
    until = _time(stop.get("until"))
    if until is not None:
        return dict(stop) if now < until else None
    if str(stop.get("on") or "") < _day(now):
        return None
    return dict(stop)


def _day(t: dt.datetime) -> str:
    try:
        import person
        return person.today(t).isoformat()
    except Exception:  # noqa: BLE001  no profile: the day in UTC
        return t.astimezone(dt.timezone.utc).date().isoformat()


def beat_fields(name: str, now: dt.datetime, browser: str = "none", linkedin: str = "unknown",
                cookies: str = "unknown", read: str = "none", version: str = "",
                task: bool | None = None, chat: str = "", stop: dict | None = None) -> dict:
    """The heartbeat a computer writes: what it is, as it measured it, never a guess. `stop`:
    today's LinkedIn stop on this computer (stop_here), carried so the cloud sees it."""
    for value, allowed in ((browser, BROWSER), (linkedin, LINKEDIN), (cookies, COOKIES),
                           (read, READS)):
        if value not in allowed:
            raise ValueError(f"{value!r} is not one of {', '.join(allowed)}")
    return {"kind": "computer", "title": f"Your computer ({_plain_name(name)})",
            "computer": _plain_name(name), "seen_at": _stamp(now),
            # Not a chat listening for the page's rings: the page's computerListening counts
            # only those. This record says the computer can be reached.
            "watching": False, "can": [], "busy": None,
            "browser": browser, "linkedin": linkedin, "keep_cookies": cookies,
            "last_read": {"at": _stamp(now), "ok": read == "ok"} if read != "none" else None,
            "version": version or app_version(),
            "task": bool(task_present() if task is None else task),
            "stop": dict(stop) if stop else None,
            **({"chat": chat} if chat else {})}


def beat(db: dict, name: str, now: dt.datetime, out_dir: str, dump_dir: str = "",
         **facts) -> list[str]:
    """The batch that writes this computer's heartbeat, pinned to the version read."""
    import page_db
    did = beat_id(name)
    mine = (db.get("chats") or {}).get(did)
    old = (mine or {}).get("data") or {}
    fields = beat_fields(name, now, **facts)
    if fields["last_read"] is None and old.get("last_read"):
        fields["last_read"] = old["last_read"]          # nothing read this time: kept
    fields.update(cookies_seen(old, fields))
    w = page_db.Writes(out_dir)
    w.add("set", "chats", did, fields, if_version=mine["version"] if mine else None)
    if dump_dir:
        page_db._keep_dump(dump_dir, "chats", did, fields,
                           int(mine["version"] or 1) + 1 if mine else 1)
    batches = w.save("computer")
    if facts.get("linkedin") == "in":
        # LinkedIn seen signed in: every job waiting on that sign-in goes back to work by
        # itself, each in a batch of its own after the heartbeat, so a refusal never holds the
        # heartbeat back. A chat that saw the sign-in still left the job parked until the
        # person found its card (the audit of 2026-11-10, CC-3).
        for wid, doc in sorted((db.get("work") or {}).items()):
            if waits_on_signin((doc or {}).get("data") or {}):
                batches += signed_in(db, wid, now, os.path.join(out_dir, "signed-in",
                                                                page_db.body_name(wid)),
                                     dump_dir=dump_dir)
    return batches


def cookies_seen(old: dict, new: dict) -> dict:
    """Whether the browser keeps sign-ins (browser-pane-stay-signed-in), by its effect: no chat can read the browser's menu, so a LinkedIn sign-in
    seen (`in`) and then lost (`out`) by the next look says the browser did not keep it (it was
    signed in one day and signed out the next morning, and a job stopped with nothing read:
    the maintainer, 2026-11-10). Kept off until a later look finds the sign-in held across a
    gap of SIGNIN_HELD_S; never guessed on, said by the person or measured otherwise."""
    if new.get("keep_cookies") in ("on", "off"):
        return {}
    was, now_ = old.get("linkedin"), new.get("linkedin")
    out: dict = {}
    if now_ == "in":
        if was != "in" or not old.get("signed_in_at"):
            out["signed_in_at"] = new.get("seen_at")
        else:
            out["signed_in_at"] = old["signed_in_at"]
    if was == "in" and now_ == "out":
        out["keep_cookies"] = "off"
        out["signin_lost"] = {"in_at": old.get("signed_in_at") or old.get("seen_at"),
                              "out_at": new.get("seen_at")}
    elif old.get("keep_cookies") == "off" and now_ != "in":
        out["keep_cookies"] = "off"
    elif old.get("keep_cookies") == "off" and now_ == "in":
        start = _time(out.get("signed_in_at"))
        seen = _time(new.get("seen_at"))
        held = start and seen and (seen - start).total_seconds() >= SIGNIN_HELD_S
        out["keep_cookies"] = "unknown" if held else "off"
    return out


def heartbeat(db: dict) -> dict:
    """The newest computer heartbeat in the page's database, or {}."""
    best: dict = {}
    for did, doc in (db.get("chats") or {}).items():
        d = (doc or {}).get("data") or {}
        if not str(did).startswith(BEAT_PREFIX.rstrip("~")) or d.get("kind") != "computer":
            continue
        if not best or str(d.get("seen_at") or "") > str(best.get("seen_at") or ""):
            best = dict(d, id=did)
    return best


def bridges(envs) -> list[dict]:
    """The person's computers a cloud chat can start a chat on: list_environments' active
    bridge environments, as [{id, computer, folder}] (claude_surfaces: computer-bridge)."""
    # The tool's answer as it came: {"environments": [...]}, a page wrapped as {"ccr": {...}}
    # or {"data": [...]}, or a plain list. Wrapped, it read as no computer at all, and work
    # for the computer waited while the Mac was on (a person's copy, 2026-11-10).
    for _ in range(3):
        if isinstance(envs, dict) and isinstance(envs.get("ccr"), (dict, list)):
            envs = envs["ccr"]
        if isinstance(envs, dict):
            envs = envs.get("environments") or envs.get("data") or []
    out = []
    for e in envs or []:
        if not isinstance(e, dict) or str(e.get("kind") or "") != "bridge" \
                or str(e.get("state") or "") != "active":
            continue
        name = str(e.get("name") or "")
        m = re.search(r"\(([^)]+)\)", str(e.get("description") or ""))
        parts = name.split(":")
        out.append({"id": str(e.get("environment_id") or e.get("id") or ""),
                    "computer": _plain_name(m.group(1) if m else parts[0]),
                    "folder": parts[1] if len(parts) > 1 else ""})
    return [b for b in out if b["id"]]


def pick_bridge(found: list[dict], db: dict, now: dt.datetime) -> list[dict]:
    """The person's computers, best first: the one whose heartbeat is fresh and signed in to
    LinkedIn, then the one the setup was tested on (place.json computer_name), then the rest
    as listed. The first listed was always used, with no fallback, though it could be the
    one signed out or set up in another folder (the builder audit, 2026-11-10, CC-22)."""
    beats = {}
    for doc in (db.get("chats") or {}).values():
        d = (doc or {}).get("data") or {}
        if d.get("kind") == "computer" and d.get("computer") and _time(d.get("seen_at")):
            name = _plain_name(d["computer"]).lower()
            if name not in beats or d["seen_at"] > beats[name]["seen_at"]:
                beats[name] = d
    try:
        import place
        tested = _plain_name(place.place_record().get("computer_name") or "").lower()
    except Exception:  # noqa: BLE001
        tested = ""

    def rank(pair):
        n, b = pair
        d = beats.get(_plain_name(b["computer"]).lower()) or {}
        seen = _time(d.get("seen_at"))
        fresh = bool(seen and (now - seen).total_seconds() < OFF_S)
        return (0 if fresh and d.get("linkedin") != "out" else 1 if fresh else 2,
                0 if tested and _plain_name(b["computer"]).lower() == tested else 1, n)
    return [b for _, b in sorted(enumerate(found), key=rank)]


# ------------------------------------------------------------------ the one line


def lapsed(item: dict, now: dt.datetime, work: dict | None = None) -> bool:
    """Work for the computer whose chat stopped (its claim not moved on for a lease) and that
    `page_db.next_item` starts again: it waits as queued work does. Only a computer chat may
    take it again, so counted as running it sat "running" for good when the computer's chat
    died: nothing started a new one, and the scheduled task saw nothing (the release review,
    2026-11-09). One tried AUTO_TRIES times is failed in plain words instead (page_db.stranded)."""
    import page_db
    return (str(item.get("status") or "") in page_db.ACTIVE
            and not page_db._live_claim(item, now, work)
            and int(item.get("attempt") or 1) < page_db.AUTO_TRIES and not item.get("in_chat"))


# A chat on the computer whose work is done still has its last steps to run (the save's wait,
# land.SAVE_WAIT_S, the earlier chats, the folders, its last heartbeat): it is put away only
# once that heartbeat is newer than its work's end, or this long after it. Listed finished the
# moment its work was done, the starter could archive it mid-save (the independent review,
# 2026-11-11).
END_WAIT_S = 13 * 60


def _refused_lately(sess: dict, now: dt.datetime) -> bool:
    """Was its archive refused lately because it was still at work? Asked again after
    END_WAIT_S, never at every wake meanwhile."""
    t = _time(sess.get("archive_refused"))
    return bool(t and (now - t).total_seconds() < END_WAIT_S)


def _ending(db: dict, d: dict, sess: dict, now: dt.datetime) -> bool:
    """Is the chat on the computer for this work still in its last steps?"""
    import page_db
    sid = str(sess.get("id") or "")
    for doc in (db.get("work") or {}).values():
        o = (doc or {}).get("data") or {}
        if str(o.get("claimed_by") or "") == sid and str(o.get("status") or "") in page_db.ACTIVE:
            return True                      # another job of the same chat still going
    if str(d.get("status") or "") == "needs_you":
        asked = _time(d.get("asked_you_at"))
        ref = asked + dt.timedelta(seconds=SIGNIN_WAIT_S) if asked else None
    else:
        ref = _time(d.get("finished_at"))
    if ref is None or (now - ref).total_seconds() >= END_WAIT_S:
        return False
    for doc in (db.get("chats") or {}).values():
        b = (doc or {}).get("data") or {}
        seen = _time(b.get("seen_at"))
        if b.get("kind") == "computer" and str(b.get("chat") or "") == sid and seen and seen > ref:
            return False                     # its last heartbeat came: its steps are done
    return True


def waiting(db: dict, now: dt.datetime) -> dict:
    """{"queued": [ids], "started": {id: session}, "finished": [{work, session}]}: the work
    sent to the computer that nobody has started, the chats started for it on the computer,
    and the ones whose work is over, to be archived."""
    import page_db
    queued, started, finished = [], {}, []
    work = db.get("work") or {}
    for wid, doc in sorted(work.items()):
        d = (doc or {}).get("data") or {}
        if not page_db.computer_only(d, "cloud"):
            continue
        status = str(d.get("status") or "")
        sess = d.get("computer_session") if isinstance(d.get("computer_session"), dict) else {}
        # Stopped for the person (LinkedIn signed out: app.py done --question): its chat on the
        # computer is put away at once, like a finished one, and a fresh one is started only
        # once they answer, which queues the work again. The stopped chat sat in their sidebar
        # while the page waited on them (the maintainer, 2026-11-10).
        # Its chat waiting for a sign-in (SIGNIN_WAIT_S) is at work, never put away; one put
        # away (`archived_at`) is at work no longer, whenever it started: a sign-in made on the
        # page then queued the work again, and it waited half an hour, counted as started.
        live = bool(sess.get("id")) and not sess.get("archived_at")
        # Answered, the question's time is kept as `last_asked_at` (page_db.answered).
        asked_you = _time(d.get("asked_you_at") or d.get("last_asked_at"))
        waits = live and bool(asked_you) and (now - asked_you).total_seconds() < SIGNIN_WAIT_S
        if status in page_db.FINISHED or status == "needs_you":
            if status == "needs_you" and waits and waits_on_signin(d):
                started[wid] = sess["id"]
            elif live and (_ending(db, d, sess, now) or _refused_lately(sess, now)):
                started[wid] = sess["id"]
            elif live:
                finished.append({"work": wid, "session": sess["id"]})
            continue
        at = _time(sess.get("at"))
        if (status == "queued" or lapsed(d, now, work)) and not d.get("stop_asked"):
            if live and ((at and (now - at).total_seconds() < STARTED_S) or waits):
                started[wid] = sess["id"]
            else:
                queued.append(wid)
    return {"queued": queued, "started": started, "finished": finished}


def page_signed_in_at() -> str:
    """When the person's page last saw LinkedIn signed in (its own reader: a check that passed,
    or a profile read; profile/... page_reader.json, kept from the page's taps), or ""."""
    try:
        import place
        rec = place.page_reads_record()
    except Exception:  # noqa: BLE001
        return ""
    if not rec.get("ok"):
        return ""
    got = [str(rec.get(k) or "") for k in ("checked_at", "last_read_at") if rec.get(k)]
    return max(got) if got else ""


def busy_there(db: dict, now: dt.datetime, w: dict | None = None) -> str:
    """The session of a chat the app started on the computer that is at work now (started
    lately, waiting on a sign-in, or holding a live claim), or ""."""
    import page_db
    w = w if w is not None else waiting(db, now)
    if w["started"]:
        return next(iter(w["started"].values()))
    work = db.get("work") or {}
    for doc in work.values():
        d = (doc or {}).get("data") or {}
        if str(d.get("status") or "") not in page_db.ACTIVE or not page_db._live_claim(d, now, work):
            continue
        sess = d.get("computer_session") if isinstance(d.get("computer_session"), dict) else {}
        if sess.get("id") and not sess.get("archived_at"):
            return str(sess["id"])
        # A read held by any chat using the computer's browser: one the person opened there,
        # or a cloud chat lent the browser (claimed as a computer chat's). Counted only by a
        # chat the app started there, it let a second chat move the same browser (the
        # independent review, 2026-11-11, CC-8).
        if str(d.get("claimed_as") or "") == "computer" and \
                str(d.get("kind") or "") in page_db.READS_ON_COMPUTER:
            return str(d.get("claimed_by") or "a chat on the computer")
    # The person signing in to LinkedIn on the page, in its own reading panel, which shares
    # the browser and keeps no claim: a chat started meanwhile moved the browser and took the
    # sign-in away from them (the independent review, 2026-11-11, CC-8). Held while the
    # question is fresh (SIGNIN_WAIT_S), never longer.
    for doc in work.values():
        d = (doc or {}).get("data") or {}
        needs = d.get("needs") if isinstance(d.get("needs"), dict) else {}
        asked = _time(d.get("asked_you_at"))
        if needs.get("signin") == "linkedin" and waits_on_signin(d) and asked \
                and (now - asked).total_seconds() < SIGNIN_WAIT_S:
            return SIGNING_IN
    return ""


SIGNING_IN = "your LinkedIn sign-in on the page"


def state(db: dict, now: dt.datetime, envs=None, version: str = "",
          works_on: str = "", page_signin: str = "") -> dict:
    """The computer as the page shows it: {state, line, action, card, computer, seen_at,
    waiting}. `action` is {label, steps} or None; `card` is True only while computer work
    waits past CARD_AFTER_S and only the person can move it. `envs`: list_environments' answer
    where the chat asked (None: not known). `works_on`: profile/place.json's answer."""
    beat_ = heartbeat(db)
    w = waiting(db, now)
    seen = _time(beat_.get("seen_at"))
    age = (now - seen).total_seconds() if seen else None
    has_bridge = None if envs is None else bool(bridges(envs))
    if not beat_ and works_on == "phone":
        key = "no_computer"
    elif not beat_ and not has_bridge:
        key = "not_set_up"
    elif has_bridge is False and (age is None or age >= OFF_S):
        key = "gone" if age is not None and age >= GONE_S else "no_bridge"
    elif age is not None and age >= GONE_S and not has_bridge:
        # Never "gone" on the check-in alone while the person's own list shows the computer
        # on: a Mac connected that day read as gone on a check-in from the day before (the
        # maintainer's copy, 2026-11-11).
        key = "gone"
    elif age is not None and age >= OFF_S and not has_bridge:
        key = "off"
    elif w["queued"] and starter_stuck(db):
        # Nothing can start on the computer until the person opens the chat that starts it
        # there (CC-6): said, with the work that waits, never "ready".
        key = "starter_" + starter_stuck(db)
    elif beat_.get("linkedin") == "out" and _time(page_signin) and seen and \
            _time(page_signin) > seen:
        # Signed in since on the page (`page_signin`): "signed out" stayed on the computer's
        # row until the next chat ran there (the builder audit, 2026-11-10, CC-24). The page's
        # reader may be another browser, so softened, never cleared: unsure until a chat there
        # looks (the independent review, 2026-11-11).
        key = "signin_unsure"
    elif beat_.get("linkedin") == "out":
        key = "signed_out"
    elif stopped_today(beat_, now):
        # Only on the day LinkedIn stopped the reads: "paused" from a read that stopped once
        # stayed for good, the next day's reads and all.
        key = "paused"
    elif beat_.get("keep_cookies") == "off":
        key = "forgets"
    elif w["started"]:
        key = "working"
    else:
        key = "ready"
    oldest = None
    asked = []
    for wid in w["queued"]:
        d = ((db.get("work") or {}).get(wid) or {}).get("data") or {}
        t = _time(d.get("asked_at"))
        oldest = t if oldest is None or (t and t < oldest) else oldest
        asked.append((str(d.get("asked_at") or ""), str(d.get("title") or "").strip()))
    waited = (now - oldest).total_seconds() if oldest else 0
    # The words for a sign-in that did not last (cookies_seen): the same state, a truer line.
    say = "signed_out_lost" if key == "signed_out" and beat_.get("signin_lost") else key
    act = ACTION.get(say)
    action = None
    if act:
        import claude_surfaces
        action = {"label": act[1], "id": act[0],
                  "steps": [ln for ln in claude_surfaces.steps(act[0], page=True)
                            if ln[:1].isdigit()]}
    needs_them = key in ("off", "gone", "signed_out", "forgets", "no_bridge", "not_set_up",
                         "starter_waits", "starter_silent")
    return {"state": key, "line": SAY[say], "action": action, "say": say,
            "card": bool(w["queued"]) and needs_them and waited >= CARD_AFTER_S,
            "computer": beat_.get("computer") or "", "seen_at": beat_.get("seen_at"),
            # Today's LinkedIn stop on the computer: the page's reading row and the reads the
            # cloud queues for the computer both follow it (app_model, app.computer_reads).
            "stopped": stopped_today(beat_, now),
            "waiting": len(w["queued"]) + len(w["started"]),
            # What waits, oldest first: the card names it (WAITING_SAY).
            "titles": [t for _, t in sorted(asked)],
            "behind": older(beat_.get("version"), version)}


def _vkey(v) -> tuple | None:
    """A release number as numbers ("4.14.0" -> (4, 14, 0)), or None where it is not one."""
    parts = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in parts[:4]) if parts and re.match(r"^\s*v?\d", str(v)) else None


def older(theirs, ours) -> bool:
    """Is the computer's app (`theirs`) older than this copy's (`ours`)? Any difference was
    "behind", a newer computer too, and the brief promised an update that would not come (the
    builder audit, 2026-11-10, CC-23)."""
    a, b = _vkey(theirs), _vkey(ours)
    return bool(a and b and a < b)


def seen(db: dict, now: dt.datetime) -> dict | None:
    """The computer's state from the page's database, as the page is drawn with it (`app.py
    view`) and a tap on its card is checked against it (app_actions.Index), or None where it
    cannot be read: the page then shows what it showed before."""
    try:
        works_on = _works_on()
        st = state(db, now, version=app_version(), works_on=works_on,
                   page_signin=page_signed_in_at())
    except Exception:  # noqa: BLE001  the page is drawn whatever the computer's record holds
        return None
    # Someone who never said they have a computer, with nothing waiting for one, keeps the
    # row as it was: nothing about a computer is pressed on a person without one. Nor on one
    # whose computer was set up and tested (`computer_ready`) and has not written to this page
    # yet: "Set it up once" was untrue for them.
    if st["state"] in ("not_set_up", "no_computer") and not st["waiting"] \
            and (works_on not in ("computer", "both") or _ready_said()):
        return None
    return st


def _ready_said() -> bool:
    """Was the computer side set up and tested here (`ready`, profile/place.json)?"""
    try:
        import place
        return bool(place.place_record().get("computer_ready"))
    except Exception:  # noqa: BLE001
        return False


def reads_there(rec: dict, st: dict, now: dt.datetime) -> bool:
    """Is the person's computer known ready to read LinkedIn, so work that reads it is sent
    there (`to: computer`, the page's peopleTo)? They work on a computer, and its setup was
    tested (`computer_ready` in profile/place.json, written by `ready`) or it wrote a heartbeat
    lately (`st`: `state`'s answer). Otherwise it is sent anywhere, where the page reads the
    profiles itself: sent to a computer with no bridge, no scheduled task and its setup put
    off, it waited for good, since no cloud chat may take it (the release review, 2026-11-09)."""
    if str(rec.get("works_on") or "") not in ("computer", "both"):
        return False
    if rec.get("computer_ready"):
        return True
    seen = _time((st or {}).get("seen_at"))
    return bool(seen and (now - seen).total_seconds() < OFF_S)


def networking_there(db: dict, now: dt.datetime) -> bool:
    """Does a networking run go to the person's computer, the whole run done there with its
    profile reads in Claude's browser (the page's peopleTo, for one asked in a chat too)? Their
    computer is known ready (reads_there, from profile/place.json and the page's heartbeat)
    and they have profiles read in the browser, not pasted or left alone."""
    try:
        import place
        sys.path.insert(0, os.path.join(_HERE, "network"))
        import reading
        if reading.reads_now() != "browser":
            return False
        return reads_there(place.place_record(), heartbeat(db), now)
    except Exception:  # noqa: BLE001  nothing to read: not known ready
        return False


def card(st: dict) -> dict | None:
    """The one To do card, in the shape of the page's other setup cards
    (tools/app_setup.py outside_item), or None when the person is not needed."""
    if not st.get("card"):
        return None
    import app_model
    said = WAITING_SAY.get(st.get("say") or st["state"]) or WAITING_SAY.get(st["state"])
    body = said.format(what=waiting_words(st.get("titles") or [])) if said else st["line"]
    # Its one obvious next step on its face; Done only where there is something the person did
    # to confirm (signed in, switched it on). With the computer off, its own heartbeat says
    # when Claude is open again, so nothing is tapped (the screen review, 2026-11-09: the
    # card's face held only "Done").
    item = {"id": "q-setup-computer", "kind": "setup", "title": "Your computer, for LinkedIn",
            "body": body, "steps": (st.get("action") or {}).get("steps") or [],
            "options": [{"label": "Done", "action": "setup.done"}] if st.get("action") else [],
            "about": {"step": "computer"}, "rev": app_model.rev_of("computer", st["state"], body)}
    if st["state"] == "signed_out":
        item["browser"] = dict(LINKEDIN_LOGIN)
    if st.get("action"):
        import claude_surfaces
        e = claude_surfaces.entry(st["action"]["id"])
        item["link"] = claude_surfaces.official(e)
        item["checked"] = e.get("verified_on", "")
    return item


# ------------------------------------------------------------------ where it is done


def session_title(job: str, computer: str) -> str:
    job = " ".join(str(job or "work for your computer").split())[:50].rstrip()
    return SESSION_TITLE.format(job=job, computer=_plain_name(computer))


def session_prompt(wid: str, title: str, url: str, copy: str) -> str:
    """The whole of what a chat started on the computer is told, complete from the start: it
    never needs another chat, and nothing it does waits on a message between chats."""
    return "\n".join([
        f"Do the work waiting for this computer on the person's job search page: \"{title}\" "
        f"(work item {wid}), then anything else waiting for this computer, without asking them "
        "anything in this chat. Never message another chat: the page and their copy carry "
        "everything back. Run every command below as written: they work in zsh and bash alike.",
        "1. Find their copy: the folder you are in, or the one inside it holding tools/app.py "
        f"(the copy of {copy}): find . -maxdepth 3 -path '*/tools/app.py' -print. Work there.",
        "2. python3 tools/app.py start --on \"<your model>\" --tools browser --work " + wid +
        ", and do what it prints.",
        "3. Load ArtifactData (ToolSearch, select:ArtifactData). Read the page's database into "
        f"a fresh folder in your scratchpad, $D: ArtifactData query, url {url}, once for each of "
        "the collections work, holds, beats and meta, each with out_dir $D and limit 1000. The "
        "page's screens are read only where a step brings the page up to date.",
        "4. python3 tools/app.py next \"$D\" --chat <your id> --kind computer --computer-only "
        "--on \"<your model>\" --claim-out \"$D/claim\", and send its claim batch (refused: "
        "another chat has it, stop).",
        "5. Say how this computer is: look at Claude's browser (tabs_context, and whether a "
        "LinkedIn page shows the person signed in), then python3 tools/computer.py beat \"$D\" "
        "--chat <your id> --browser <shown|hidden> --linkedin "
        "<in|out|unknown>, and send the batch it prints (ArtifactData batch). LinkedIn signed "
        f"out (now, or at any profile later): open {LINKEDIN_LOGIN['url']} in Claude's browser, "
        "in a tab of its own, so the sign-in is there when they look; put it on their page with "
        "python3 tools/app.py done \"$D\" --work <its id> --chat <your id> --kind computer "
        "--signin linkedin --question \"LinkedIn is signed out in Claude's browser.\" and send "
        "its batch (the Sign in to LinkedIn card: the page signs them in inside the Claude app). "
        "Then wait for it yourself, never parking the job, one look at a time, each look: "
        + SIGNIN_LOOK.format(url=url, wid="<its id>") + ". Do what it prints: `look` is the "
        "same three calls again; `signed-in`, `answered` and `stopped` say what next; `stop` "
        "is step 7 (a fresh chat carries on once they sign in). Look only at the sign-in tab's "
        "address, never the page. Never ask in this chat.",
        "Signed in (any look shows LinkedIn signed in, or the person says so here) while a job "
        "of yours waits on its sign-in: python3 tools/computer.py signed-in \"$D\" --work <its "
        "id> and send its batch (refused, or it says it is not waiting: the page sent the work "
        "back already, and there is nothing to send), write the heartbeat with --linkedin in, read the page's work again (step 3), "
        "then step 4 again and carry on from step 6. Never tell them to tap anything on the "
        "page for it.",
        "The person answers a question of the page's here, or asks this chat to do work the page "
        "holds for the computer (\"just read them here\"): python3 tools/app.py resume \"$D\" "
        "--work <its id> --chat <your id> --kind computer (with --answer \"<their words>\" for a "
        "question), send its batch, then carry on from step 6. Never read for it before that: the "
        "work is started again elsewhere and read twice.",
        "6. Follow the `steps` step 4 printed, in order. Reading LinkedIn: only the pages the "
        "work names, one at a time, as tools/network/pace.py PACE_RULE says; say what you do "
        "as you do it, and nothing about waiting you do not do. Where its steps did not measure "
        "it, before each finish: python3 tools/computer.py measure \"$D\" --work <its id> "
        "--chat <your id>, and send its batch.",
        "7. At the end, first make sure your save left this computer: python3 tools/land.py "
        "--wait-saved, as a Bash call with timeout 600000 (it waits for the save running in "
        "the background, and saves any change not saved yet), and do what it prints: `not "
        "sent yet` means the work is kept here until the next save sends it, and its cards say "
        "so (computer.py saved-here), never left silent. Never make a scheduled task: the "
        "cloud starts a chat here when work waits (COMPUTER.md, section 6, step 5). Then put "
        "away this computer's earlier chats of "
        "the app's (claude_surfaces: computer-chat-archive): list the desktop app's other chats "
        "here, asked in plain words, save what it shows as JSON ([{\"title\", \"status\", \"updated_at\"}]) to "
        "\"$D/chats.json\", run python3 tools/computer.py archivable \"$D/chats.json\", and "
        "archive each chat it names. Where this chat cannot list them, skip it and say nothing "
        "about it. Then python3 tools/computer.py tidy-folders \"$D\": it removes the folders "
        "earlier chats here made whose work is on master, and says nothing to the person. "
        "Last, your final heartbeat, which tells the chat that started you this one may be put "
        "away: python3 tools/computer.py beat \"$D\" --chat <your id> "
        "--browser <shown|hidden> --linkedin <in|out|unknown> --read <ok|stopped|none>, and "
        "send its batch.",
        "8. Wake the chat that started you, so it puts this one away now: python3 "
        "tools/computer.py ring \"$D\" --file \"<your scratchpad>/bell.html\", and do what it "
        "prints where the Artifact tool is among yours (nothing to do where it says so). "
        "Publishing is not among the tools this chat was given ahead: where it asks for an "
        "approval, or is refused, skip it and say nothing; the chat that started you puts "
        "this one away at its next wake all the same.",
        "9. Your last message says what was done in a few plain words, and nothing about saving, "
        "pull requests, merging or chats put away: the page shows how it went. Then stop: the "
        "chat that started you archives this one.",
        "After a compaction, or wherever you lose your place: python3 tools/computer.py prompt "
        f"--work {wid} prints these steps again with the id the work was claimed under; never "
        "claim it again under a new id.",
    ])


# The chats on the computer the app may put away: the ones it starts there (SESSION_TITLE), and,
# once the computer is set up, the setup chat, which the desktop app names from the line the
# person pasted into it ("Open my job search on this computer...", place.computer_paste). The
# one on a Mac on 2026-11-10 found none: the person had deleted the earlier chat by hand, and
# that one, the setup chat, did not carry the app's name either.
APP_CHAT = re.compile(r"^\s*Job search\s+\u00b7\s+\S.*\s+\u00b7\s+\S.*$", re.I)
_RUNNING = ("running", "working", "busy", "active", "progress", "streaming", "waiting",
            "requires", "blocked", "paused", "input", "permission")
# The states that say a chat has finished, as whole words ("incomplete" is not "complete").
# No state, or one not known here, keeps the chat: a list of titles alone, or one waiting on a
# permission prompt, was put away (audit HC-2; review of fix/helpers, item 7).
_FINISHED = ("idle", "complete", "completed", "done", "finished", "stopped", "ended")
# Used this lately (the listing's last-activity time), a chat is kept: one idle between the
# person's turns was put away.
ARCHIVE_QUIET_S = 3 * 3600


def _setup_title(title: str) -> bool:
    """Is this the setup chat's own title: the first sentence of the line pasted into it
    (place.computer_paste), exactly? A pattern matched a chat the person had named."""
    words = re.sub(r"[^a-z ]+", " ", title.lower()).split()
    return words == "open my job search on this computer".split()


def _chat_rows(listing) -> list[dict]:
    """The chats as the desktop app listed them, saved as JSON ([{title, id, status}], or
    titles alone) or as plain lines of titles."""
    if isinstance(listing, str):
        try:
            listing = json.loads(listing)
        except ValueError:
            listing = [ln.strip(" -*\t") for ln in listing.splitlines() if ln.strip()]
    if isinstance(listing, dict):
        listing = listing.get("sessions") or listing.get("chats") or []
    rows = []
    for x in listing or []:
        rows.append({"title": str(x)} if not isinstance(x, dict) else
                    {"title": str(x.get("title") or x.get("name") or ""),
                     "id": str(x.get("id") or x.get("session_id") or ""),
                     "status": str(x.get("status") or x.get("state") or ""),
                     "used": str(x.get("updated_at") or x.get("last_activity_at")
                                 or x.get("last_used") or "")})
    return rows


def archivable(listing, set_up: bool, now: dt.datetime | None = None) -> list[dict]:
    """The chats to archive on this computer, of those the desktop app listed (this chat is
    never among them): every finished one the app started there, and the setup chat once the
    computer is set up (`set_up`, profile/place.json computer_ready). Only one whose listed state
    says it has finished: one still running or waiting, one with no state or a state not known
    here, and any other the person keeps, is left."""
    import app_model
    now = now or dt.datetime.now(dt.timezone.utc)
    out = []
    for r in _chat_rows(listing):
        t = r["title"].strip()
        words = set(re.findall(r"[a-z]+", r.get("status", "").lower().replace("_", " ")))
        if not t or words & set(_RUNNING) or not words & set(_FINISHED):
            continue
        used = app_model.parse_time(r.get("used"))
        if used is not None and (now - used).total_seconds() < ARCHIVE_QUIET_S:
            continue
        if APP_CHAT.match(t) or (set_up and _setup_title(t)):
            out.append(r)
    return out


def ready(name: str, today: dt.date) -> str:
    """Write, dated, that the computer side is set up and its test read worked, in
    profile/place.json (`computer_ready`, `computer_name`): the trace the computer-linkedin
    upgrade looks for. Only into a profile that exists."""
    import person
    import place
    if not person.exists("person.json"):
        return "ready: no profile here, nothing written"
    got = dict(place.place_record(), computer_ready=today.isoformat(),
               computer_name=_plain_name(name))
    path = person.path(place.PLACE_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2)
        fh.write("\n")
    return f"ready: {_plain_name(name)} set up and tested on {today.isoformat()}"


def task_spec(root: str) -> dict:
    """The scheduled task as a chat on the computer makes it (claude_surfaces: routines-local):
    Local, in the copy's folder, hourly, in Auto, with a prompt that stops at once when nothing
    waits."""
    return {"name": TASK_NAME, "where": "Local (only on this computer)", "folder": root,
            "schedule": f"every {TASK_EVERY_MIN} minutes" if TASK_EVERY_MIN < 60 else "hourly",
            "permission_mode": "Auto", "prompt": TASK_PROMPT}


def task_steps(url: str) -> list[str]:
    """What a run of the scheduled task does: one read of the page's work, and nothing more
    when nothing waits for this computer."""
    return [
        "1. Load ArtifactData (ToolSearch, select:ArtifactData). ArtifactData query, url "
        f"{url}, collection work, out_dir a fresh folder in your scratchpad, $D, limit 1000.",
        "2. python3 tools/computer.py waiting \"$D\". It prints nothing: stop now and say nothing.",
        "3. Otherwise, for the first id under \"queued\", follow from step 2 the steps that "
        "python3 tools/computer.py prompt --work <that id> prints, in this chat.",
    ]


def route(db: dict, now: dt.datetime, chat: str = "", envs=None, folders=None,
          tools=(), url: str = "", copy: str = "", works_on: str = "") -> dict:
    """Where the work waiting for the computer is done now, the first that works of the
    chain in this module's notes: {route, line, call?, steps?, first?}. `envs`:
    list_environments' answer; `folders`: list_computer_folders'; `tools`: the tool names
    this chat has (create_session, request_computer_folder, the computer's browser)."""
    import app_listen
    w = waiting(db, now)
    tools = {str(t) for t in tools or ()}
    st = state(db, now, envs=envs, works_on=works_on)
    if not w["queued"]:
        # A chat on the computer whose work is over (or waits on the person) is put away by the
        # starter, the one chat whose approval reaches the computer: woken for it here.
        if w["finished"] and chat and starter(db).get("bell") and not is_starter(db, chat) \
                and app_listen.chat_kind() == "cloud":
            return _starter_route(db, now, w["finished"][0]["work"], w, url, copy, "")
        return {"route": "none", "line": "", "waiting": w}
    wid = w["queued"][0]
    item = (db["work"][wid] or {}).get("data") or {}
    chats = db.get("chats") or {}
    live = [d for d in ((doc or {}).get("data") or {} for doc in chats.values())
            if d.get("kind") == "computer" and d.get("watching") is not False
            and _time(d.get("seen_at")) and (now - _time(d["seen_at"])).total_seconds() < FRESH_S]
    # This chat is on the computer, with Claude's browser: it takes the work itself. A chat the
    # person opened there, with no list of computers to ask and no heartbeat yet, was routed
    # to "paste", and its page said the computer was off while it sat open on it.
    here = app_listen.chat_kind() == "computer" and any(
        t in ("browser", "enable") or t.startswith("mcp__Claude_Browser") for t in tools)
    if live or here:
        out = {"route": "computer chat", "work": wid,
               "line": "Your computer's chat takes it.", "waiting": w}
        if here:
            out["then"] = ("this chat is on the computer and has Claude's browser: take it here, "
                           "python3 tools/app.py next <dump> --chat <your id> --kind computer "
                           "--on \"<your model>\" --claim-out <dump>/claim, send its claim "
                           "batch, and follow the steps it prints.")
        return out
    # One chat at a time on the computer: they share one browser pane. While one the app
    # started there is at work (claimed and moving, or just started), the next piece of work
    # waits for it, and it takes it next (`next --computer-only`). Two jobs started two chats
    # moving one browser, and a read could be saved under the wrong person (the builder audit,
    # 2026-11-10, CC-8).
    busy = busy_there(db, now, w)
    if busy:
        return {"route": "computer busy", "work": wid,
                "line": ("It starts once you are signed in to LinkedIn." if busy == SIGNING_IN
                         else "Your computer's chat takes it next."), "waiting": w}
    found = pick_bridge(bridges(envs), db, now)
    can_start = "create_session" in tools
    # A chat that cannot start one itself (a page helper's own agent has no create_session)
    # still rings the starter that can: it said the computer was off and that nothing in the
    # cloud could start it, while the person's list showed the Mac on (2026-11-11).
    helper = bool(found) and bool(chat) and not is_starter(db, chat) \
        and app_listen.chat_kind() == "cloud" and (can_start or bool(starter(db).get("bell")))
    if helper:
        # Any cloud chat but the starter wakes the starter (or makes it once): the approval a
        # chat on the computer needs ties the approving chat to the person's devices for good,
        # and a helper that held it could not archive itself (the maintainer, 2026-11-10).
        got = _starter_route(db, now, wid, w, url, copy, runs_there(found[0]["computer"]))
        # No starter can be made from here (no copy to start it from, or no create_session to
        # make it with): the rest of the chain still works, a folder or the browser the
        # computer lends this chat. "none" here left the work waiting with both on offer.
        if got["route"] != "none" and (can_start or got["route"] != "make starter"):
            return got
    if found and "create_session" in tools and not helper:
        b = found[0]
        title = session_title(item.get("title") or item.get("kind"), b["computer"])
        call = {"environment_id": b["id"], "title": title,
                "prompt": session_prompt(wid, item.get("title") or item.get("kind") or "", url,
                                         copy or "their job search"),
                # The page's data tools, pre-approved as a cloud job's chat gets them (app.py
                # CHILD_TOOLS): without them each read and write of the page asked the person,
                # in a chat on their computer they never open, and its last steps (the
                # heartbeat, waking the starter that puts it away) never ran, so it was left
                # open (the second audit, 2026-11-10, C6).
                "extra_allowed_tools": list(STARTER_TOOLS),
                "permission_mode": app_listen.SESSION_MODE}
        return {"route": "computer session", "work": wid, "computer": b["computer"],
                "line": runs_there(b["computer"]), "call": call,
                "then": (f"create_session with this call.{app_listen.MODE_REFUSED} Refused as "
                         "elevated_session_untrusted_device: list_triggers, saved to a file, then "
                         "python3 tools/computer.py trust-check --chat <your id> --triggers <that "
                         "file>, and do what it prints: approving ties this chat to the person's "
                         "own devices for good, and a scheduled task bound to it then fails, so "
                         "each is moved to a chat of its own with the copy attached first. Then "
                         "confirm_repository_trust with the content_digest the refusal gave (one "
                         "card for the person, once, and only ever in this chat, the one that "
                         "starts chats on their computer), python3 tools/computer.py trusted "
                         "--chat <your id>, and the same create_session again. Started: "
                         f"python3 tools/computer.py started <dump> --work {wid} --session <its "
                         f"id> --env {b['id']} --computer \"{b['computer']}\", and send its "
                         "batch. Never send_message it, and set no reminder or check-in for "
                         "it (each is one more prompt for the person): it reports through the "
                         "page."),
                "waiting": w}
    beat_ = heartbeat(db)
    seen = _time(beat_.get("seen_at"))
    if beat_.get("task") and seen and (now - seen).total_seconds() < OFF_S:
        return {"route": "computer task", "work": wid,
                "line": "Your computer takes it within the hour, while Claude is open there.",
                "waiting": w}
    usable = [f for f in ((folders or {}).get("folders") or []) if f.get("online", True)] \
        if isinstance(folders, dict) else []
    if usable and "request_computer_folder" in tools:
        f = usable[0]
        return {"route": "computer folder", "work": wid,
                "line": f"Using your {_plain_name(f.get('computer_name'))}.",
                "call": {k: f.get(k) for k in ("environment_id", "computer_name", "folder")},
                "then": ("request_computer_folder with this call; attached: claim it here with "
                         "python3 tools/app.py next <dump> --chat <id> --kind computer "
                         "--computer-only --lent and do it here, with --kind computer on every "
                         "app.py done."), "waiting": w}
    if any(t.startswith("mcp__remote-devices__Claude_Browser") or
           t == "enable__mcp__remote-devices__Claude_Browser" for t in tools):
        return {"route": "linked browser", "work": wid,
                "line": "Reading it with your computer's browser.",
                "then": ("this chat has the computer's browser: claim it with python3 "
                         "tools/app.py next <dump> --chat <id> --kind computer --computer-only "
                         "--lent and do it here, with --kind computer on every app.py done."),
                "waiting": w}
    # Never "the computer is off" on an old check-in alone: with no list of the person's
    # computers given, the chat asks for it first. Judged by the Mac's last check-in, a Mac
    # that was on and listed read as off, and the work waited (a person's copy, 2026-11-10).
    if envs is None and "create_session" in tools:
        return {"route": "ask", "work": wid, "line": "",
                "then": ("list_environments first, save its answer to a file, then run "
                         "python3 tools/computer.py route again with --envs <that file>: "
                         "whether the computer is on is what that list says, never its last "
                         "check-in alone."), "waiting": w}
    if found:
        # On, by the person's own list, and this chat cannot start Claude there: the chat that
        # answers the page can, so it is handed there, never "your computer is off".
        name = found[0]["computer"]
        return {"route": "on, start it elsewhere", "work": wid, "computer": name,
                "line": f"Your {name} is on: Claude starts there from the chat that answers your page.",
                "then": ("this chat has no create_session to start Claude on the computer: ask the "
                         "chat that answers the page (it has create_session) to run python3 "
                         "tools/computer.py route with --envs and --tools create_session, and do "
                         "what it prints. Never tell the person the computer is off."),
                "waiting": w}
    out = {"route": "paste", "work": wid, "line": st["line"], "action": st["action"],
           "paste": True, "waiting": w}
    if st["state"] == "ready":
        out["line"] = SAY["off"]
    return out


def started(db: dict, wid: str, session: str, env: str, computer: str, now: dt.datetime,
            out_dir: str, dump_dir: str = "") -> list[str]:
    """The batch that notes the chat started on the computer for `wid`, so no second one is
    started for it, its card says where it is done, and it is archived once over."""
    import page_db
    doc = (db.get("work") or {}).get(page_db.safe_id(wid))
    if doc is None:
        raise KeyError(f"no work {wid!r} in the dump; read work again")
    d = doc["data"]
    say = runs_there(computer)
    steps = list(d.get("steps") or [])[-5:] + [{"at": _stamp(now), "text": say}]
    # `say`: the work card keeps the line while the work runs, past the steps after it.
    fields = {"computer_session": {"id": session, "env": env, "computer": _plain_name(computer),
                                   "at": _stamp(now), "say": say}, "steps": steps}
    w = page_db.Writes(out_dir)
    w.add("update", "work", wid, fields, if_version=doc["version"])
    if dump_dir:
        page_db._keep_dump(dump_dir, "work", wid, dict(d, **fields), int(doc["version"] or 1) + 1)
    return w.save("computer-started")


SAVED_HERE_SAID = ("Saved on your computer, not yet in your copy: it goes in with the next "
                   "save there.")


def saved_here(db: dict, chat: str, now: dt.datetime, out_dir: str) -> list[str]:
    """The batch that says, on the card of each piece of work this chat on the computer
    finished, that its save is kept on the computer and not yet in the copy (land.py
    --wait-saved said not sent yet): still done, with `saved_here` and one line on its card.
    Never failed: Try again read the same LinkedIn profiles again while the work sat on the
    Mac, and the next save there sends it (land._push_left_behind; the independent review,
    2026-11-11). Silent, the page showed it done with nothing said (CC-1)."""
    import page_db
    w = page_db.Writes(out_dir)
    at = _stamp(now)
    for wid, doc in (db.get("work") or {}).items():
        d = (doc or {}).get("data") or {}
        if not chat or str(d.get("claimed_by") or "") != chat or \
                str(d.get("status") or "") != "done" or d.get("saved_here"):
            continue
        steps = list(d.get("steps") or [])[-5:] + [{"at": at, "text": SAVED_HERE_SAID}]
        w.add("update", "work", wid, {"saved_here": {"at": at}, "steps": steps},
              if_version=doc.get("version"))
    return w.save("computer-saved-here") if w.entries else []


def _git(root: str, *args: str):
    import subprocess
    # --no-optional-locks: a look never writes git's index, whose time says when a chat last
    # worked in a folder (_last_used); git status refreshes it otherwise.
    return subprocess.run(["git", "--no-optional-locks", "-C", root, *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _worktrees(root: str) -> list[dict]:
    """git worktree list, as [{path, branch, head}], the main folder first."""
    out, cur = [], {}
    for ln in (_git(root, "worktree", "list", "--porcelain").stdout or "").splitlines() + [""]:
        if not ln.strip():
            if cur.get("path"):
                out.append(cur)
            cur = {}
        elif ln.startswith("worktree "):
            cur["path"] = ln[len("worktree "):].strip()
        elif ln.startswith("HEAD "):
            cur["head"] = ln[len("HEAD "):].strip()
        elif ln.startswith("branch "):
            cur["branch"] = ln[len("branch "):].strip().replace("refs/heads/", "", 1)
    return out


def _build_noise(rel: str) -> bool:
    """An ignored file that is only build noise (save_state.NOISE: caches, LaTeX's leftovers),
    never one of the person's never-committed files (save_state.NEVER: the LinkedIn download,
    the salary data, the mail cursor), which git worktree remove would delete with the folder."""
    import fnmatch
    import save_state
    rel = rel.replace("\\", "/").rstrip("/")
    parts = rel.split("/")
    if any(p in ("__pycache__", ".pytest_cache") for p in parts):
        return True
    if any(fnmatch.fnmatch(rel, k) or fnmatch.fnmatch(parts[-1], k) for k in save_state.NEVER):
        return False
    return any(fnmatch.fnmatch(rel, pat) for pat in save_state.NOISE)


def _ignored(path: str) -> list[str]:
    """The ignored files and folders in a checkout, as git lists them."""
    st = _git(path, "status", "--porcelain", "--ignored=matching", "--untracked-files=all")
    out = []
    for ln in (st.stdout or "").splitlines():
        if ln.startswith("!! "):
            p = ln[3:].strip()
            if p.startswith('"') and p.endswith('"'):
                p = p[1:-1]
            out.append(p)
    return out


def _last_used(path: str) -> float:
    """When a chat last worked in this folder: its git folder's index, HEAD and HEAD log."""
    gd = (_git(path, "rev-parse", "--absolute-git-dir").stdout or "").strip()
    times = []
    for name in ("index", "HEAD", os.path.join("logs", "HEAD")):
        try:
            times.append(os.path.getmtime(os.path.join(gd, name)))
        except OSError:
            pass
    return max(times) if times else float("inf")


def _chats_of(path: str) -> dict:
    """The chats this folder says it was started for (app_setup's ljs-job-chats.json in its
    own git folder), and the claims made from it (ljs-claims.json)."""
    gd = (_git(path, "rev-parse", "--absolute-git-dir").stdout or "").strip()
    got = {}
    for name in ("ljs-job-chats.json", "ljs-claims.json"):
        try:
            with open(os.path.join(gd, name), encoding="utf-8") as fh:
                rec = json.load(fh) or {}
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            got[name] = rec
    return got


def _put_away(db: dict | None, chats: dict) -> bool:
    """Is every chat this folder names known to be put away (its computer_session archived on
    the page), and every work it claimed ended? Unknown is never put away."""
    if not chats:
        return True
    if db is None:
        return False
    import page_db
    work = db.get("work") or {}
    sessions = {}
    for doc in work.values():
        sess = ((doc or {}).get("data") or {}).get("computer_session")
        if isinstance(sess, dict) and sess.get("id"):
            sessions[str(sess["id"])] = sess
    for key in (chats.get("ljs-job-chats.json") or {}):
        sess = sessions.get(str(key).replace("local-", "", 1)) or sessions.get(str(key))
        if not sess or not sess.get("archived_at") or sess.get("archive_refused"):
            return False
    for wid in (chats.get("ljs-claims.json") or {}):
        d = (work.get(page_db.safe_id(wid)) or {}).get("data")
        if d is None or str(d.get("status") or "") not in page_db.FINISHED:
            return False
    return True


def stale_worktrees(root: str, db: dict | None = None,
                    now: dt.datetime | None = None) -> list[dict]:
    """The folders of its own the app's chats made on this computer that are safe to remove.
    Each computer chat made one and none were removed (the builder audit, 2026-11-10, CC-17);
    the first try at removing them also took a folder a chat had just made, one holding a
    resume never committed, and the person's own folder (the independent review, 2026-11-11).
    Only a folder sync_app.worktree made (under <main>/.claude/worktrees, on a chat/ branch),
    never the main folder or this chat's own, whose branch is merged into origin/master, with
    nothing uncommitted or untracked, no ignored file but build noise, no save running, not
    used for MAIN_CHAT_HOURS, and every chat it names known to be put away (`db`)."""
    import land
    import sync_app
    trees = _worktrees(root)
    if not trees:
        return []
    main = os.path.realpath(trees[0].get("path") or "")
    allowed = os.path.join(main, sync_app.WORKTREES)
    here = {main, os.path.realpath(root), os.path.realpath(os.getcwd())}
    quiet = sync_app.MAIN_CHAT_HOURS * 3600
    out = []
    import time
    for t in trees[1:]:
        path, name = t.get("path") or "", t.get("branch") or ""
        real = os.path.realpath(path) if path else ""
        if not real or not name.startswith("chat/") or not os.path.isdir(real) or real in here:
            continue
        if os.path.dirname(real) != os.path.realpath(allowed):
            continue
        if time.time() - _last_used(real) < quiet:
            continue
        if _git(root, "merge-base", "--is-ancestor", t.get("head") or name,
                "origin/master").returncode != 0:
            continue
        if (_git(real, "status", "--porcelain", "--untracked-files=all").stdout or "").strip():
            continue
        if any(not _build_noise(p) for p in _ignored(real)):
            continue
        if land.landing(real) or land.wanted(real):
            continue
        if not _put_away(db, _chats_of(real)):
            continue
        # In the computer's own form: git says D:/a/b on Windows, and the folder was then
        # named one way to the person and compared another (the suite on Windows, 2026-11-11).
        out.append({"path": os.path.normpath(path), "branch": name})
    return out


def remove_worktrees(root: str, trees: list[dict]) -> list[str]:
    """Each folder removed the safe way (git refuses one with changes) and its merged branch
    deleted the safe way (git refuses one not merged); what was removed."""
    done = []
    for t in trees:
        if _git(root, "worktree", "remove", t["path"]).returncode == 0:
            _git(root, "branch", "-d", t["branch"])
            done.append(t["path"])
    return done


SIGNED_IN_SAID = "Signed in to LinkedIn"


class NotWaiting(KeyError):
    """The work is there but not waiting on a sign-in: already handled, nothing to send. Said
    as an error (exit 2, the id quoted), a chat read "already handled" as a failure (the builder
    audit, 2026-11-10, CC-26)."""


def waits_on_signin(item: dict) -> bool:
    """Is this work stopped on a LinkedIn sign-in only (app.py done --signin linkedin, or a
    question from before that said it was signed out)?"""
    if str(item.get("status") or "") != "needs_you":
        return False
    needs = item.get("needs") if isinstance(item.get("needs"), dict) else {}
    if needs.get("signin") == "linkedin":
        return True
    return str(item.get("to") or "") == "computer" and \
        "signed out" in str(item.get("note") or "").lower()


def signed_in(db: dict, wid: str, now: dt.datetime, out_dir: str, dump_dir: str = "") -> list[str]:
    """The batch that answers a job's own sign-in question once a chat on the computer has seen
    LinkedIn signed in, and puts the job back in the queue for that chat to carry on with. A
    chat that saw the sign-in work still told the person to tap Done on the page, and the job
    stayed parked (the maintainer, 2026-11-10). Its chat there is kept as at work, so no second
    one is started for it meanwhile."""
    import page_db
    doc = (db.get("work") or {}).get(page_db.safe_id(wid))
    if doc is None:
        raise KeyError(f"no work {wid!r} in the dump; read work again")
    d = doc["data"]
    if not waits_on_signin(d):
        raise NotWaiting("it is not waiting on a sign-in now (the page sent it back already, "
                         "or it never was): nothing to send; carry on as it is")
    # The page's own answer, as its Signed in tap writes it (page_db.answered).
    fields = page_db.answered(d, SIGNED_IN_SAID, _stamp(now))
    sess = d.get("computer_session") if isinstance(d.get("computer_session"), dict) else {}
    if sess.get("id"):
        fields["computer_session"] = dict(sess, at=_stamp(now))
    w = page_db.Writes(out_dir)
    w.add("update", "work", wid, fields, if_version=doc["version"])
    if dump_dir:
        page_db._keep_dump(dump_dir, "work", wid, dict(d, **fields), int(doc["version"] or 1) + 1)
    return w.save("computer-signed-in")


def signin_wait(item: dict, now: dt.datetime) -> tuple[str, int]:
    """("look" | "stop" | "answered", seconds left): whether a chat on the computer that found
    LinkedIn signed out goes on looking for the sign-in (SIGNIN_WAIT_S from its question)."""
    if not waits_on_signin(item):
        return "answered", 0
    asked = _time(item.get("asked_you_at")) or now
    left = int(SIGNIN_WAIT_S - (now - asked).total_seconds())
    return ("look", left) if left > 0 else ("stop", 0)


def archived(db: dict, wid: str, now: dt.datetime, out_dir: str,
             refused: bool = False) -> list[str]:
    """The batch that notes its computer chat was archived (archive_session), or, `refused`,
    that archive_session refused because the chat is still at work: then it is not put away,
    so no second chat starts beside it (busy_there), and it is asked again later. Recorded as
    put away, a chat still running let a second one start on the same browser (the
    independent review, 2026-11-11)."""
    import page_db
    doc = (db.get("work") or {}).get(page_db.safe_id(wid))
    if doc is None:
        raise KeyError(f"no work {wid!r} in the dump; read work again")
    sess = dict(doc["data"].get("computer_session") or {})
    if refused:
        sess["archive_refused"] = _stamp(now)
    else:
        sess["archived_at"] = _stamp(now)
        sess.pop("archive_refused", None)
    w = page_db.Writes(out_dir)
    w.add("update", "work", wid, {"computer_session": sess}, if_version=doc["version"])
    return w.save("computer-archived")


# ------------------------------------------------------------------ measured, never guessed

_PAGE_KINDS = (("experience", re.compile(r"linkedin\.com/in/[^/]+/details/experience")),
               ("education", re.compile(r"linkedin\.com/in/[^/]+/details/education")),
               ("profile", re.compile(r"linkedin\.com/in/[^/?#]+/?(?:[?#]|$)")),
               ("people search", re.compile(r"linkedin\.com/search/results/people")),
               ("company", re.compile(r"linkedin\.com/company/")),
               ("sign-in", re.compile(r"linkedin\.com/(?:login|authwall|checkpoint|uas/login)")))
_STAGE = re.compile(r"app\.py pin .*?--stage[ =]\"?([\w-]+)")
# Where a run pinned no stage, its own steps mark them (network.md "The run, in order"): a
# people search or candidates.py is `find`, a profile read is `read`, saving notes is
# `write`, the InMail choice is `check`. A run's time was one number, so nobody could tell
# whether the searching or the reading took it (2026-11-10).
_NET_STAGE = ((re.compile(r"candidates\.py\s+(?:order|search|check|employers)\b"), "find"),
              (re.compile(r"reading\.py\s+(?:next|read|people|extractor)\b"), "read"),
              (re.compile(r"reading\.py\s+(?:drafts?|batch)\b"), "write"),
              (re.compile(r"inmail_pick\.py\b"), "check"))
_PAGE_STAGE = {"people search": "find", "company": "find", "profile": "read",
               "experience": "read", "education": "read"}


def page_kind(url: str) -> str:
    for kind, rx in _PAGE_KINDS:
        if rx.search(str(url or "")):
            return kind
    return "linkedin, other" if "linkedin.com" in str(url or "") else "other site"


def measure(file: str, since: str = "") -> dict:
    """What a run took, counted from its own transcript (claude_surfaces: session-usage):
    {wall_s, stages: {stage: s}, tools: {name: n}, calls, pages: {kind: n}, web_searches,
    tokens: {...}, est_usd}. `since`: count only from this time (the work's claim)."""
    import helper_usage
    t0 = _time(since) if since else None
    first = last = None
    tools: dict = {}
    pages: dict = {}
    searches = 0
    marks: list = []
    steps: list = []                     # the stages a run's own steps mark, where none is pinned
    try:
        fh = open(file, encoding="utf-8", errors="replace")
    except OSError:
        return {}
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            at = _time(ev.get("timestamp"))
            if at is None or (t0 and at < t0):
                continue
            first = first or at
            last = at
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            for part in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "server_tool_use" and part.get("name") == "web_search":
                    searches += 1
                if part.get("type") != "tool_use":
                    continue
                name = str(part.get("name") or "")
                tools[name] = tools.get(name, 0) + 1
                inp = part.get("input") if isinstance(part.get("input"), dict) else {}
                if name == "WebSearch":
                    searches += 1
                step = ""
                if name.endswith("navigate") or name.endswith("__navigate"):
                    kind = page_kind(inp.get("url"))
                    pages[kind] = pages.get(kind, 0) + 1
                    step = _PAGE_STAGE.get(kind, "")
                cmd = str(inp.get("command") or "")
                m = _STAGE.search(cmd)
                if m:
                    marks.append((at, m.group(1)))
                step = step or next((st for rx, st in _NET_STAGE if rx.search(cmd)), "")
                if step and (not steps or steps[-1][1] != step):
                    steps.append((at, step))
    if first is None:
        return {}
    marks = marks or steps
    stages: dict = {}
    for i, (at, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else last
        stages[name] = stages.get(name, 0) + int((end - at).total_seconds())
    tok = helper_usage.totals(file, since)
    return {"wall_s": int((last - first).total_seconds()), "stages": stages,
            "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
            "calls": sum(tools.values()), "pages": pages,
            "linkedin_pages": sum(n for k, n in pages.items() if k != "other site"),
            "web_searches": searches,
            "tokens": {k: tok[k] for k in ("input", "cache_write", "cache_read", "output")},
            "est_usd": round(helper_usage.estimate(tok), 2)}


def runs_path() -> str:
    import person
    return os.path.join(person.state(), *RUNS_FILE)


def _runs() -> list:
    try:
        with open(runs_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return []
    runs = got.get("runs") if isinstance(got, dict) else None
    return [r for r in runs or [] if isinstance(r, dict)]


def record_run(wid: str, kind: str, usage: dict, now: dt.datetime) -> None:
    """Kept in documents/computer_runs.json ({"runs": [...]}, merged entry by entry by
    tools/merge_state.py), only ever added to, RUNS_KEEP_DAYS long."""
    path = runs_path()
    cut = _stamp(now - dt.timedelta(days=RUNS_KEEP_DAYS))
    runs = [r for r in _runs() if str(r.get("at") or "") >= cut and r.get("work") != wid]
    runs.append(dict(usage, work=wid, kind=kind, at=_stamp(now)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"runs": sorted(runs, key=lambda r: str(r.get("at") or ""))}, fh, indent=1,
                  ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def usage_line(u: dict) -> str:
    """The run in one plain line, for its card and the brief."""
    if not u:
        return ""
    mins = max(1, round(u.get("wall_s", 0) / 60))
    cost = f", about ${u['est_usd']:.2f}" if u.get("est_usd") else ""
    return (f"Took {mins} min: {u.get('calls', 0)} steps, {u.get('linkedin_pages', 0)} LinkedIn "
            f"pages, {u.get('web_searches', 0)} web searches{cost}.")


def trend(today: dt.date, days: int = 7) -> str:
    """The brief's line on the computer runs of the last `days`, against the week before."""
    runs = _runs()
    if not runs:
        return ""

    def window(lo: int, hi: int) -> list:
        a = (today - dt.timedelta(days=hi)).isoformat()
        b = (today - dt.timedelta(days=lo)).isoformat()
        return [r for r in runs if a < str(r.get("at") or "")[:10] <= b]
    now_, before = window(0, days), window(days, 2 * days)
    if not now_:
        return ""

    def med(rs, key):
        vals = [float(r.get(key) or 0) for r in rs]
        return statistics.median(vals) if vals else 0
    mins = round(med(now_, "wall_s") / 60)
    line = (f"Your computer did {len(now_)} LinkedIn run{'s' if len(now_) != 1 else ''} this "
            f"week: about {mins} min, {round(med(now_, 'calls'))} steps and "
            f"{round(med(now_, 'linkedin_pages'))} LinkedIn pages each")
    cost = med(now_, "est_usd")
    line += f", about ${cost:.2f} each" if cost else ""
    # Where the time went: the searching (`find`) against the profile reads (`read`).
    split = [(round(statistics.median([float((r.get("stages") or {}).get(st) or 0)
                                       for r in now_]) / 60), words)
             for st, words in (("find", "searching"), ("read", "reading profiles"))]
    if any(r.get("stages") for r in now_) and any(m for m, _w in split):
        line += ", " + " and ".join(f"{m} min {w}" for m, w in split)
    if before:
        was = round(med(before, "wall_s") / 60)
        if was and was != mins:
            line += f" ({'down' if mins < was else 'up'} from {was} min the week before)"
    return line + "."


# ------------------------------------------------------------------ the daily check


def _triggers(triggers) -> list[dict]:
    if isinstance(triggers, dict):
        triggers = triggers.get("triggers") or triggers.get("data") or []
    return [t for t in triggers or [] if isinstance(t, dict)]


def bound_to(chat: str, triggers) -> list[dict]:
    """The scheduled tasks that are on and fire into `chat` (list_triggers' answer)."""
    return [t for t in _triggers(triggers) if chat and t.get("persistent_session_id") == chat
            and t.get("enabled", True) is not False]


def trust_check(chat: str, triggers) -> list[str]:
    """Before a chat approves computer access (confirm_repository_trust), which ties it to the
    person's own devices for good: every scheduled task that fires into it is moved to a chat
    of its own made with the person's copy as its source, or it fails from then on with access
    denied, the person told only by a "routine failed" push (2026-11-09). Never a fresh chat a
    run: one a scheduled task starts has no copy attached, no add_repo and no way to clone it,
    and failed on its first run (a person's copy, 2026-11-10). The brief needs no connectors
    (claude_surfaces: routine-connectors), so the field is left out (some refuse it)."""
    tasks = bound_to(chat, triggers)
    if not tasks:
        return ["trust: ok, no scheduled task fires into this chat"]
    import routines
    brief = any(routines._is_brief_prompt(str(t.get("prompt") or "")) or
                "brief" in str(t.get("name") or "").lower() for t in tasks)
    # The brief's own chat (routines.brief_chat_call), which the rest join: one chat made.
    home = routines.brief_chat_call()
    if not brief:
        home = dict(home, title="Job search: scheduled runs",
                    prompt="This chat runs the job search's scheduled tasks. Nothing to do now.")
    out = [f"first, once: create_session {json.dumps(home, ensure_ascii=False)}; its id is "
           "<home> below (a chat of its own with the copy attached, never the one approving "
           "computer access)"]
    for t in tasks:
        call = {"name": t.get("name"), "prompt": t.get("prompt") or "<its prompt, as get_trigger "
                "shows it>", "persistent_session_id": "<home>",
                "initiation": "own_followup"}
        if t.get("cron_expression"):
            call["cron_expression"] = t["cron_expression"]
        elif t.get("run_once_at"):
            call["run_once_at"] = t["run_once_at"]
        is_brief = (routines._is_brief_prompt(str(t.get("prompt") or "")) or
                    "brief" in str(t.get("name") or "").lower()) and t.get("cron_expression")
        out.append(f"move {t.get('id')}: create_trigger {json.dumps(call, ensure_ascii=False)}, "
                   f"then update_trigger {{\"trigger_id\": \"{t.get('id')}\", \"enabled\": "
                   "false}} (turned off and kept, never deleted)" +
                   (", then python3 tools/routines.py record --session <home> --trigger <the new "
                    f"id> --cron \"{t['cron_expression']}\" --own-chat" if is_brief else ""))
    return out


def trusted(chat: str, today: dt.date) -> str:
    """Kept, dated, in profile/place.json: the chat that approved computer access, so the daily
    check can see a scheduled task bound to it later."""
    import person
    import place
    if not person.exists("person.json"):
        return "trusted: no profile here, nothing written"
    got = dict(place.place_record(), computer_trusted_chat=chat,
               computer_trusted_on=today.isoformat())
    with open(person.path(place.PLACE_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2)
        fh.write("\n")
    return f"trusted: {chat} on {today.isoformat()}"


def check(db: dict, now: dt.datetime, envs=None, version: str = "", triggers=None,
          locked: str = "") -> list[str]:
    """What the day's sync and the brief say about the computer, for Claude: each line names
    what is wrong and the one way back, or nothing at all when there is nothing to do.
    `triggers`: list_triggers' answer; `locked`: the chat that approved computer access."""
    st = state(db, now, envs=envs, version=version)
    beat_ = heartbeat(db)
    out = []
    for t in bound_to(locked, triggers):
        out.append(f"computer: the scheduled task {t.get('name')!r} fires into a chat that "
                   "approved computer access, so it fails; move it: python3 tools/computer.py "
                   f"trust-check --chat {locked} --triggers <list_triggers saved>, and do what "
                   "it prints.")
    if st["state"] == "signed_out":
        # First in the brief, whatever waits: a sign-out found only when a job stopped was
        # found by the maintainer checking, hours later (2026-11-10).
        out.append("computer: first line of the message, before the headline, in these words: "
                   f"\"{st['line']}\"")
    if st["card"]:
        out.append(f"computer: work waits for the computer and the person is needed: "
                   f"{st['line']} The page's To do card says so; say it in one line.")
    elif st["waiting"] and st["state"] not in ("ready", "working"):
        out.append(f"computer: work waits for the computer: {st['line']}")
    if beat_ and st["state"] == "gone":
        out.append("computer: not seen for a week; its chat, folder or scheduled task may have "
                   "been deleted. The one way back: python3 tools/claude_surfaces.py steps "
                   "remote-control-settings, then the next work for the computer starts a "
                   "new chat there by itself.")
    # No scheduled task is made or asked for: one started a Claude run every hour the app was
    # open, waiting work or not, for what the cloud already starts on the computer when work
    # waits (the maintainer, 2026-11-09: "this sounds like it could be incredibly expensive").
    if st.get("behind"):
        out.append("computer: the computer's copy is on an older version: its next chat takes "
                   "the update when it starts.")
    return out


# ------------------------------------------------------------------ memory and shells


def memory_files(root: str, home: str | None = None) -> list[str]:
    """The auto memory a chat in this copy may load (code.claude.com/docs/en/memory: each
    project's at ~/.claude/projects/<project>/memory/), for this folder and the folders above
    it a chat may have been started in."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home or os.path.expanduser("~"), ".claude")
    names = set()
    path = os.path.abspath(root)
    while True:
        names.add(re.sub(r"[^A-Za-z0-9]", "-", path))
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    out = []
    for name in sorted(names):
        out += sorted(glob.glob(os.path.join(base, "projects", name, "memory", "*.md")))
    local = os.path.join(root, "CLAUDE.local.md")
    return out + ([local] if os.path.isfile(local) else [])


def memory_conflicts(root: str, home: str | None = None, settings: dict | None = None) -> list[dict]:
    """Each chat memory that says otherwise than the person's settings in profile/, which win:
    [{file, setting, memory_says, setting_says}]. Read only: an old note on a computer ("only
    update when I say") was obeyed over the person's current setting, and rewriting it from a
    chat was blocked (2026-11-09); the start step now removes it (memory_remove)."""
    import learned
    if settings is None:
        # Only what the person wrote: with no app_updates in person.json (a computer's copy not
        # yet up to date with it) the page reads "auto", and a note saying updates come when
        # they say, which was their choice, was taken for one that disagrees and removed
        # (the maintainer's Mac, 2026-11-11).
        import person
        try:
            written = str(person.get("app_updates", "") or "").strip().lower()
        except Exception:  # noqa: BLE001  no profile here: nothing to compare with
            written = ""
        settings = {"profile/person.json app_updates": written} if written in ("auto", "when_asked") else {}
    out = []
    for f in memory_files(root, home):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for para in re.split(r"\n\s*\n|\n(?=[-*] )", text):
            for name, value in learned.known_settings("other", para, ""):
                have = settings.get(name)
                if have is not None and value != have:
                    out.append({"file": f, "setting": name, "memory_says": value,
                                "setting_says": have})
    seen, unique = set(), []
    for c in out:
        k = (c["file"], c["setting"])
        if k not in seen:
            seen.add(k)
            unique.append(c)
    return unique


# A setting in plain words, for the one line the person hears when a note about it is removed.
PLAIN_SETTINGS = {
    "profile/person.json app_updates": {"when_asked": "updates come only when you say",
                                        "auto": "updates come by themselves"},
}
_FRONT = re.compile(r"\A---\n.*?\n---\n?", re.S)


def _plain(setting: str, value) -> str:
    return PLAIN_SETTINGS.get(setting, {}).get(value, "") or f"{setting.split()[-1]} is {value}"


def _substance(text: str) -> str:
    """What a memory file says once its frontmatter and headings are set aside."""
    body = _FRONT.sub("", text or "", count=1)
    return "\n".join(ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#"))


def memory_remove(conflicts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Take each note that disagrees with the person's settings out of the chat memory that
    holds it, once, as the start step finds it: (removed, still there). A note kept and only
    reported was met again by every chat on the computer (the maintainer's computer,
    2026-11-10). Only the note goes: the rest of the file stays as it was, and a file left
    with nothing but its heading or frontmatter goes with its line in MEMORY.md, the folder's
    index (code.claude.com/docs/en/memory: "Auto memory files are plain markdown you can edit
    or delete at any time"). Where the file cannot be written, the note is still there."""
    import learned
    removed, left = [], []
    by_file: dict[str, list[dict]] = {}
    for c in conflicts:
        by_file.setdefault(c["file"], []).append(c)
    for f, cs in by_file.items():
        wrong = {(c["setting"], c["memory_says"]) for c in cs}
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            parts = re.split(r"(\n\s*\n|\n(?=[-*] ))", text)
            keep = []
            for i in range(0, len(parts), 2):
                para, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
                if set(learned.known_settings("other", para, "")) & wrong:
                    continue
                keep.append(para + sep)
            rest = "".join(keep)
            if not _substance(rest):
                os.remove(f)
                index = os.path.join(os.path.dirname(f), "MEMORY.md")
                name = os.path.basename(f)
                if name != "MEMORY.md" and os.path.isfile(index):
                    with open(index, encoding="utf-8", errors="replace") as fh:
                        lines = fh.read().splitlines(keepends=True)
                    kept = [ln for ln in lines if name not in ln]
                    if kept != lines:
                        with open(index, "w", encoding="utf-8", newline="") as fh:
                            fh.write("".join(kept))
            else:
                with open(f, "w", encoding="utf-8", newline="") as fh:
                    fh.write(rest.rstrip("\n") + "\n")
            removed += cs
        except OSError:
            left += cs
    return removed, left


def memory_said(removed: list[dict], left: list[dict], told_before: bool = False) -> str:
    """The start step's line about the notes memory_remove took out or could not: for Claude,
    with the one line the person hears, in plain words, once."""
    if not removed and not left:
        return ""
    c = (left or removed)[0]
    old, now = _plain(c["setting"], c["memory_says"]), _plain(c["setting"], c["setting_says"])
    if left:
        if told_before:
            return ("An old note in this chat's memory still disagrees with the person's settings "
                    "in profile/, and could not be removed here. The settings win: follow "
                    "profile/, never the note. The person was told how to remove it: say nothing.")
        try:
            import claude_surfaces
            how = " " + claude_surfaces.say("memory-remove-note")
        except Exception:  # noqa: BLE001  the line goes without the steps
            how = ""
        return ("An old note in this chat's memory disagrees with the person's settings in "
                "profile/, and it could not be removed here. The settings win: follow profile/, "
                "never the note. Tell the person once, in one line: \"An old note in Claude's "
                f"memory on this computer says {old}, but your setting says {now}, and your "
                f"setting is what counts.{how}\"")
    return ("An old note in this chat's memory disagreed with the person's settings in profile/ "
            "and is removed now. Follow profile/. Tell the person once, in one line: \"I removed "
            f"an old note on this computer that said {old}: your setting says {now}.\"")


# Patterns that run differently in zsh, the Mac's shell, and bash: unquoted words zsh does not
# split, bash-only builtins and arrays. A loop of fifty fixes all "failed" on a Mac because
# `set -- $kv` kept the whole pair in $1 (2026-11-09).
SHELL_TRAPS = (
    (re.compile(r"\bset\s+--\s+\$\w"), "set -- $var splits words in bash only"),
    (re.compile(r"\bfor\s+\w+\s+in\s+\$\{?\w+\}?\s*;"), "for x in $var splits words in bash only"),
    (re.compile(r"\$\{?\w+\[0\]"), "arrays count from 1 in zsh"),
    (re.compile(r"\b(?:read\s+-a|mapfile|readarray|declare\s+-A|shopt)\b"), "bash-only builtin"),
    (re.compile(r"\becho\s+-e\b"), "echo -e differs between shells"),
)


def shell_problems(cmd: str) -> list[str]:
    """Why `cmd` would not run the same in zsh and bash, or [] (one wrapped in bash -c is
    fine)."""
    text = str(cmd or "")
    if re.match(r"\s*bash\s+-c\s", text):
        return []
    return [why for rx, why in SHELL_TRAPS if rx.search(text)]


# ------------------------------------------------------------------ the command line


def _load_json(path: str):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _works_on() -> str:
    try:
        import place
        return place.works_on()
    except Exception:  # noqa: BLE001
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("beat")
    p.add_argument("dump")
    p.add_argument("--name", default="", help="kept for callers that pass it: the computer's "
                                               "own name is worked out here (this_computer)")
    p.add_argument("--browser", default="none", choices=BROWSER)
    p.add_argument("--linkedin", default="unknown", choices=LINKEDIN)
    p.add_argument("--cookies", default="unknown", choices=COOKIES)
    p.add_argument("--read", default="none", choices=READS)
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    for name in ("state", "waiting", "check"):
        p = sub.add_parser(name)
        p.add_argument("dump")
        p.add_argument("--envs", default="", help="list_environments' answer, saved to a file")
        p.add_argument("--triggers", default="", help="list_triggers' answer, saved to a file")
        p.add_argument("--now", default=None)
    p = sub.add_parser("route")
    p.add_argument("dump")
    p.add_argument("--chat", default="")
    p.add_argument("--envs", default="")
    p.add_argument("--folders", default="", help="list_computer_folders' answer, saved")
    p.add_argument("--tools", default="", help="this chat's tool names, comma separated")
    p.add_argument("--now", default=None)
    p = sub.add_parser("bell-file", help="write the computer starter's bell page")
    p.add_argument("path")
    p.add_argument("--now", default=None)
    p = sub.add_parser("starter-made", help="a computer starter was asked for")
    p.add_argument("dump")
    p.add_argument("--session", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("starter-ready", help="the starter published its bell")
    p.add_argument("dump")
    p.add_argument("--chat", required=True)
    p.add_argument("--bell", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("rung", help="the starter's bell was republished")
    p.add_argument("dump")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("starter-woke", help="the starter was woken and is at work")
    p.add_argument("dump")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("starter-seen", help="what get_session said of a starter not answering")
    p.add_argument("dump")
    p.add_argument("--status", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("ring", help="wake the starter, where one is ready (a chat on the computer)")
    p.add_argument("dump")
    p.add_argument("--file", required=True)
    p.add_argument("--now", default=None)
    p = sub.add_parser("tidy-folders", help="remove this computer's merged, clean chat folders")
    p.add_argument("dump", nargs="?", default="")
    p = sub.add_parser("saved-here", help="this chat's save is kept on the computer, not yet sent")
    p.add_argument("dump")
    p.add_argument("--chat", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("signed-in", help="a job's own sign-in question, answered once seen")
    p.add_argument("dump")
    p.add_argument("--work", required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("signin-wait", help="LinkedIn signed out: one look, then wait for the next")
    p.add_argument("dump")
    p.add_argument("--work", required=True)
    p.add_argument("--url", default="", help="the sign-in tab's address, as tabs_context says")
    p.add_argument("--every", type=float, default=SIGNIN_LOOK_S, help="seconds to wait")
    p.add_argument("--now", default=None)
    p = sub.add_parser("started")
    p.add_argument("dump")
    for k in ("--work", "--session", "--env", "--computer"):
        p.add_argument(k, required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("archived")
    p.add_argument("dump")
    p.add_argument("--work", required=True)
    p.add_argument("--refused", action="store_true",
                   help="archive_session refused: the chat is still at work")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("measure")
    p.add_argument("dump")
    p.add_argument("--work", required=True)
    p.add_argument("--chat", default="")
    p.add_argument("--transcript", default="", help="this chat's own session file (default: "
                                                     "the newest under ~/.claude/projects)")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("trend")
    p.add_argument("--days", type=int, default=7)
    sub.add_parser("memory")
    p = sub.add_parser("archivable")
    p.add_argument("listing", help="the desktop app's list of its other chats, saved to a file")
    p = sub.add_parser("shell")
    p.add_argument("command")
    sub.add_parser("task", help="is the scheduled task on this computer, and how to make it")
    sub.add_parser("task-check", help="what a run of the scheduled task does")
    p = sub.add_parser("prompt", help="the whole prompt of a chat on the computer for one item")
    p.add_argument("--work", required=True)
    p.add_argument("--title", default="")
    p = sub.add_parser("ready", help="the computer side set up and tested: dated in place.json")
    p.add_argument("--name", default="", help="used only where the computer's own name cannot "
                                               "be worked out (this_computer)")
    p = sub.add_parser("trust-check", help="before computer access is approved in this chat")
    p.add_argument("--chat", required=True)
    p.add_argument("--triggers", required=True, help="list_triggers' answer, saved to a file")
    p = sub.add_parser("trusted", help="this chat approved computer access: kept, dated")
    p.add_argument("--chat", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "trust-check":
        print("\n".join(trust_check(a.chat, _load_json(a.triggers))))
        return 0
    import page_db
    if a.cmd == "trusted":
        import person
        print(trusted(a.chat, person.today()))
        return 0
    if a.cmd in ("task", "task-check", "prompt", "ready"):
        import app_setup
        import person
        url = app_setup.page_record().get("url", "") or "<url>"
        if a.cmd == "task":
            if task_present():
                print("task: the scheduled task is on this computer")
            else:
                print("task: missing. Make it: " + json.dumps(task_spec(person.state()),
                                                              ensure_ascii=False))
        elif a.cmd == "task-check":
            print("\n".join(task_steps(url)))
        elif a.cmd == "prompt":
            owner, name = app_setup.origin()
            claim = app_setup.claimed_as(a.work)
            if claim:
                print(f"Claimed here as {claim}: pass --chat {claim} on every pin and done for "
                      f"{a.work}, read the page's work again (step 3) and carry on from its stage.")
            print(session_prompt(a.work, a.title or a.work, url,
                                 f"github.com/{owner}/{name}" if owner else "their job search"))
        elif a.cmd == "ready":
            print(ready(this_computer(a.name), person.today()))
        return 0
    if a.cmd == "trend":
        import person
        print(trend(person.today(), a.days))
        return 0
    if a.cmd == "archivable":
        import place
        try:
            with open(a.listing, encoding="utf-8") as fh:
                listing = fh.read()
        except OSError:
            listing = ""
        got = archivable(listing, bool(place.place_record().get("computer_ready")))
        print("\n".join(f"archive: {r['title']}" + (f" ({r['id']})" if r.get("id") else "")
                        for r in got) or "archivable: none")
        return 0
    if a.cmd == "memory":
        import person
        removed, left = memory_remove(memory_conflicts(person.state()))
        print(memory_said(removed, left) or "memory: nothing disagrees")
        return 0
    if a.cmd == "shell":
        got = shell_problems(a.command)
        print("\n".join(got) or "shell: runs the same in zsh and bash")
        return 1 if got else 0
    if a.cmd == "tidy-folders":
        root = os.path.dirname(_HERE)
        _git(root, "fetch", "-q", "origin")
        db = page_db.load(a.dump) if a.dump and os.path.isdir(a.dump) else None
        gone = remove_worktrees(root, stale_worktrees(root, db))
        print("\n".join(f"removed: {p}" for p in gone) or "folders: none to remove")
        return 0
    now = _now(a.now)
    if a.cmd == "bell-file":
        print("bell: " + write_bell(a.path, now))
        return 0
    db = page_db.load(a.dump)
    out = getattr(a, "out", "") or os.path.join(a.dump, "out")
    if a.cmd == "signin-wait":
        doc = (db.get("work") or {}).get(page_db.safe_id(a.work))
        if doc is None:
            print(f"computer: no work {a.work!r} in the dump; read work again", file=sys.stderr)
            return 2
        item = doc["data"]
        said, left = signin_wait(item, now)
        if item.get("stop_asked") or str(item.get("status") or "") in page_db.FINISHED:
            print("stopped: they stopped it on the page, or it ended. Nothing to send for it: "
                  "go to step 7.")
            return 0
        if said == "look" and a.url:
            sys.path.insert(0, os.path.join(_HERE, "network"))
            import reading
            if reading.url_kind(a.url) == "signed-in":
                reading.mark_signed_in()
                print(f"signed-in: python3 tools/computer.py signed-in \"$D\" --work {a.work} and "
                      "send its batch, write the heartbeat with --linkedin in, read the page's "
                      "work again (step 3), then step 4 and carry on from step 6.")
                return 0
        if said == "look":
            import time
            wait = max(0.0, min(float(a.every), float(left)))
            time.sleep(wait)
            left = max(0, int(left - wait))
            url = ""
            try:
                import app_setup
                url = app_setup.page_record().get("url", "")
            except Exception:  # noqa: BLE001
                pass
            print(f"look: not signed in yet ({max(1, left // 60)} min left). The next look: "
                  + SIGNIN_LOOK.format(url=url or "<the page's url>", wid=a.work) + ".")
        elif said == "stop":
            print(f"stop: not signed in after {SIGNIN_WAIT_S // 60} minutes. Go to step 7: the "
                  "card stays on their page, and a fresh chat carries on once they sign in there.")
        else:
            print("answered: it is not waiting on a sign-in now. Read the page's work again "
                  "(step 3), then step 4.")
        return 0
    if a.cmd == "saved-here":
        batches = saved_here(db, a.chat, now, out)
        print(json.dumps({"batches": batches}) if batches else
              "saved-here: none of this chat's finished work is in the folder; read work again")
        return 0
    if a.cmd == "ring":
        rec = starter(db)
        if not rec.get("bell"):
            print("ring: no starter yet; nothing to do")
            return 0
        write_bell(a.file, now)
        print("ring: " + ring_steps(rec["bell"], a.file))
        return 0
    if a.cmd in ("starter-made", "starter-ready", "rung", "starter-woke", "starter-seen"):
        if a.cmd == "starter-made":
            batches = starter_made(db, a.session, now, out, dump_dir=a.dump)
        elif a.cmd == "starter-ready":
            batches = starter_ready(db, a.chat, a.bell, now, out, dump_dir=a.dump)
        elif a.cmd == "starter-woke":
            batches = starter_woke(db, now, out, dump_dir=a.dump)
        elif a.cmd == "starter-seen":
            batches = starter_seen(db, a.status, now, out, dump_dir=a.dump)
        else:
            batches = rung(db, now, out, dump_dir=a.dump)
        print(json.dumps({"batches": batches}))
        return 0
    if a.cmd == "beat":
        print(json.dumps({"batches": beat(db, this_computer(a.name), now, out, dump_dir=a.dump,
                                          browser=a.browser, linkedin=a.linkedin,
                                          cookies=a.cookies, read=a.read, chat=a.chat,
                                          stop=stop_here())}))
        return 0
    if a.cmd == "state":
        print(json.dumps(state(db, now, envs=_load_json(a.envs), version=app_version(),
                               works_on=_works_on()), ensure_ascii=False))
        return 0
    if a.cmd == "waiting":
        w = waiting(db, now)
        if any(w.values()):
            print(json.dumps(w))
        return 0
    if a.cmd == "check":
        try:
            import place
            locked = str(place.place_record().get("computer_trusted_chat") or "")
        except Exception:  # noqa: BLE001
            locked = ""
        for line in check(db, now, envs=_load_json(a.envs), version=app_version(),
                          triggers=_load_json(a.triggers), locked=locked):
            print(line)
        return 0
    if a.cmd == "route":
        import app_setup
        owner, name = app_setup.origin()
        got = route(db, now, chat=a.chat, envs=_load_json(a.envs), folders=_load_json(a.folders),
                    tools=[t.strip() for t in a.tools.split(",") if t.strip()],
                    url=app_setup.page_record().get("url", "") or "<url>",
                    copy=f"github.com/{owner}/{name}" if owner else "", works_on=_works_on())
        print(json.dumps(got, ensure_ascii=False))
        return 0
    try:
        if a.cmd == "started":
            batches = started(db, a.work, a.session, a.env, a.computer, now, out, dump_dir=a.dump)
        elif a.cmd == "archived":
            batches = archived(db, a.work, now, out, refused=a.refused)
        elif a.cmd == "signed-in":
            batches = signed_in(db, a.work, now, out, dump_dir=a.dump)
        else:
            import helper_usage
            doc = (db.get("work") or {}).get(page_db.safe_id(a.work))
            if doc is None:
                raise KeyError(f"no work {a.work!r} in the dump; read work again")
            u = measure(a.transcript or helper_usage.session_file(),
                        since=str(doc["data"].get("claimed_at") or ""))
            record_run(a.work, str(doc["data"].get("kind") or ""), u, now)
            w = page_db.Writes(out)
            w.add("update", "work", a.work, {"usage": u, "usage_line": usage_line(u)},
                  if_version=doc["version"])
            page_db._keep_dump(a.dump, "work", a.work,
                               dict(doc["data"], usage=u, usage_line=usage_line(u)),
                               int(doc["version"] or 1) + 1)
            batches = w.save("computer-measure")
            print(usage_line(u), file=sys.stderr)
    except NotWaiting as e:
        print(f"signed-in: {e.args[0]}")
        return 0
    except KeyError as e:
        print(f"computer: {e.args[0]}", file=sys.stderr)
        return 2
    print(json.dumps({"batches": batches}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
