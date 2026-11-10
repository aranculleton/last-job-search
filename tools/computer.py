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
     message between chats (claude_surfaces: session-approvals), and the cloud chat that
     started it archives it once its work is finished (`finished`);
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

    python3 tools/computer.py beat <dump> --name <computer> [--browser shown|hidden|none]
        [--linkedin in|out|unknown] [--cookies on|off|unknown] [--read ok|stopped|none]
    python3 tools/computer.py state <dump> [--envs FILE]       # the page's one line, as JSON
    python3 tools/computer.py waiting <dump>                   # computer work and its chats
    python3 tools/computer.py route <dump> --chat ID [--envs FILE] [--folders FILE] [--tools T]
    python3 tools/computer.py started <dump> --work ID --session ID --env ID --computer NAME
    python3 tools/computer.py archived <dump> --work ID
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
# Computer work waiting this long with nothing to start it puts one card on To do.
CARD_AFTER_S = 10 * 60
# A chat started on the computer is believed to be at work for this long (its claim's lease
# then says the rest): no second one is started for the same work meanwhile.
STARTED_S = 30 * 60
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
    "forgets": ("Claude's browser on your computer forgets LinkedIn each time the app quits: "
                "keep its sign-in once."),
    "paused": "LinkedIn asked Claude to slow down: reading starts again tomorrow, by itself.",
    "no_bridge": "Claude can't start on your computer yet: switch it on once in the Claude app there.",
    "not_set_up": "Claude doesn't use your computer yet. Set it up once to read LinkedIn profiles there.",
    "no_computer": "No computer for this: paste each person's profile on their card instead.",
}
# The registry entry whose steps each action shows, and its button's words.
ACTION = {
    "off": None,
    "gone": ("remote-control-settings", "Set it up again"),
    "signed_out": ("browser-pane-stay-signed-in", "Sign in once"),
    "forgets": ("browser-pane-stay-signed-in", "Stay signed in"),
    "no_bridge": ("remote-control-settings", "Switch it on"),
    "not_set_up": ("remote-control-settings", "Set it up"),
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
    "forgets": "{what} because Claude's browser forgets your LinkedIn sign-in when the app "
               "quits. Keep the sign-in once.",
    "no_bridge": "{what} until Claude is switched on for your computer. Switch it on once in "
                 "the Claude app there.",
    "not_set_up": "{what} until Claude is set up on your computer. Set it up once.",
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


# ------------------------------------------------------------------ the heartbeat


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


def beat_fields(name: str, now: dt.datetime, browser: str = "none", linkedin: str = "unknown",
                cookies: str = "unknown", read: str = "none", version: str = "",
                task: bool | None = None, chat: str = "") -> dict:
    """The heartbeat a computer writes: what it is, as it measured it, never a guess."""
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
    w = page_db.Writes(out_dir)
    w.add("set", "chats", did, fields, if_version=mine["version"] if mine else None)
    if dump_dir:
        page_db._keep_dump(dump_dir, "chats", did, fields,
                           int(mine["version"] or 1) + 1 if mine else 1)
    return w.save("computer")


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
        if status in page_db.FINISHED:
            if sess.get("id") and not sess.get("archived_at"):
                finished.append({"work": wid, "session": sess["id"]})
            continue
        at = _time(sess.get("at"))
        if (status == "queued" or lapsed(d, now, work)) and not d.get("stop_asked"):
            if sess.get("id") and at and (now - at).total_seconds() < STARTED_S:
                started[wid] = sess["id"]
            else:
                queued.append(wid)
    return {"queued": queued, "started": started, "finished": finished}


def state(db: dict, now: dt.datetime, envs=None, version: str = "",
          works_on: str = "") -> dict:
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
    elif age is not None and age >= GONE_S:
        key = "gone"
    elif age is not None and age >= OFF_S and not has_bridge:
        key = "off"
    elif beat_.get("linkedin") == "out":
        key = "signed_out"
    elif beat_.get("last_read") and not beat_["last_read"].get("ok"):
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
    act = ACTION.get(key)
    action = None
    if act:
        import claude_surfaces
        action = {"label": act[1], "id": act[0],
                  "steps": [ln for ln in claude_surfaces.steps(act[0], page=True)
                            if ln[:1].isdigit()]}
    needs_them = key in ("off", "gone", "signed_out", "forgets", "no_bridge", "not_set_up")
    return {"state": key, "line": SAY[key], "action": action,
            "card": bool(w["queued"]) and needs_them and waited >= CARD_AFTER_S,
            "computer": beat_.get("computer") or "", "seen_at": beat_.get("seen_at"),
            "waiting": len(w["queued"]) + len(w["started"]),
            # What waits, oldest first: the card names it (WAITING_SAY).
            "titles": [t for _, t in sorted(asked)],
            "behind": bool(version and beat_.get("version") and beat_["version"] != version)}


def seen(db: dict, now: dt.datetime) -> dict | None:
    """The computer's state from the page's database, as the page is drawn with it (`app.py
    view`) and a tap on its card is checked against it (app_actions.Index), or None where it
    cannot be read: the page then shows what it showed before."""
    try:
        works_on = _works_on()
        st = state(db, now, version=app_version(), works_on=works_on)
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


def card(st: dict) -> dict | None:
    """The one To do card, in the shape of the page's other setup cards
    (tools/app_setup.py outside_item), or None when the person is not needed."""
    if not st.get("card"):
        return None
    import app_model
    said = WAITING_SAY.get(st["state"])
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
        "the collections work, holds, beats, screen, meta and addr, each with out_dir $D and "
        "limit 1000.",
        "4. python3 tools/app.py next \"$D\" --chat <your id> --kind computer --computer-only "
        "--on \"<your model>\" --claim-out \"$D/claim\", and send its claim batch (refused: "
        "another chat has it, stop).",
        "5. Say how this computer is: look at Claude's browser (tabs_context, and whether a "
        "LinkedIn page shows the person signed in), then python3 tools/computer.py beat \"$D\" "
        "--name \"<this computer's name>\" --browser <shown|hidden> --linkedin "
        "<in|out|unknown>, and send the batch it prints (ArtifactData batch). LinkedIn signed "
        "out: put it on their page with python3 tools/app.py done \"$D\" --work <its id> --chat "
        "<your id> --kind computer --question \"LinkedIn is signed out in Claude's browser on "
        "your computer. Sign in there once, then tap Done.\" and send its batch; then go to "
        "step 7. Never ask in this chat.",
        "6. Follow the `steps` step 4 printed, in order. Reading LinkedIn: only the pages the "
        "work names, one at a time, as tools/network/pace.py PACE_RULE says; say what you do "
        "as you do it, and nothing about waiting you do not do. Where its steps did not measure "
        "it, before each finish: python3 tools/computer.py measure \"$D\" --work <its id> "
        "--chat <your id>, and send its batch.",
        "7. At the end: python3 tools/computer.py beat \"$D\" --name \"<this computer's name>\" "
        "--browser <shown|hidden> --linkedin <in|out|unknown> --read <ok|stopped|none>, and "
        "send its batch. Never make a scheduled task: the cloud starts a chat here when work "
        "waits (COMPUTER.md, section 6, step 5). Then put away this computer's earlier chats of "
        "the app's (claude_surfaces: computer-chat-archive): list the desktop app's other chats "
        "here, asked in plain words, save what it shows as JSON ([{\"title\", \"status\"}]) to "
        "\"$D/chats.json\", run python3 tools/computer.py archivable \"$D/chats.json\", and "
        "archive each chat it names. Where this chat cannot list them, skip it and say nothing "
        "about it.",
        "8. Your last message says what was done in a few plain words, and nothing about saving, "
        "pull requests, merging or chats put away: the page shows how it went. Then stop: the "
        "chat that started you archives this one.",
    ])


# The chats on the computer the app may put away: the ones it starts there (SESSION_TITLE), and,
# once the computer is set up, the setup chat, which the desktop app names from the line the
# person pasted into it ("Open my job search on this computer...", place.computer_paste). The
# one on a Mac on 2026-11-10 found none: the person had deleted the earlier chat by hand, and
# that one, the setup chat, did not carry the app's name either.
APP_CHAT = re.compile(r"^\s*Job search\s+\u00b7\s+\S.*\s+\u00b7\s+\S.*$", re.I)
SETUP_CHAT = re.compile(r"^\s*(?:open|set\s*up|setup|start)\b.*\bjob\s+search\b.*\b(?:this\s+)?"
                        r"(?:computer|mac|laptop|pc)\b", re.I)
_RUNNING = ("running", "working", "busy", "active", "in progress", "streaming")


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
                     "status": str(x.get("status") or x.get("state") or "")})
    return rows


def archivable(listing, set_up: bool) -> list[dict]:
    """The chats to archive on this computer, of those the desktop app listed (this chat is
    never among them): every finished one the app started there, and the setup chat once the
    computer is set up (`set_up`, profile/place.json computer_ready). A chat still running, or
    any other the person keeps, is left."""
    out = []
    for r in _chat_rows(listing):
        t = r["title"].strip()
        if not t or any(w in r.get("status", "").lower() for w in _RUNNING):
            continue
        if APP_CHAT.match(t) or (set_up and SETUP_CHAT.match(t)):
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
        return {"route": "none", "line": "", "waiting": w}
    wid = w["queued"][0]
    item = (db["work"][wid] or {}).get("data") or {}
    chats = db.get("chats") or {}
    live = [d for d in ((doc or {}).get("data") or {} for doc in chats.values())
            if d.get("kind") == "computer" and d.get("watching") is not False
            and _time(d.get("seen_at")) and (now - _time(d["seen_at"])).total_seconds() < FRESH_S]
    if live:
        return {"route": "computer chat", "work": wid,
                "line": "Your computer's chat takes it.", "waiting": w}
    found = bridges(envs)
    if found and "create_session" in tools:
        b = found[0]
        title = session_title(item.get("title") or item.get("kind"), b["computer"])
        call = {"environment_id": b["id"], "title": title,
                "prompt": session_prompt(wid, item.get("title") or item.get("kind") or "", url,
                                         copy or "their job search"),
                "permission_mode": app_listen.SESSION_MODE}
        return {"route": "computer session", "work": wid, "computer": b["computer"],
                "line": runs_there(b["computer"]), "call": call,
                "then": (f"create_session with this call.{app_listen.MODE_REFUSED} Refused as "
                         "elevated_session_untrusted_device: list_triggers, saved to a file, then "
                         "python3 tools/computer.py trust-check --chat <your id> --triggers <that "
                         "file>, and do what it prints: approving ties this chat to the person's "
                         "own devices for good, and a scheduled task bound to it then fails, so "
                         "each is moved to a fresh chat a run first. Then "
                         "confirm_repository_trust with the content_digest the refusal gave (one "
                         "card for the person, once), python3 tools/computer.py trusted --chat "
                         "<your id>, and the same create_session again. Started: "
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


def archived(db: dict, wid: str, now: dt.datetime, out_dir: str) -> list[str]:
    """The batch that notes its computer chat was archived (archive_session)."""
    import page_db
    doc = (db.get("work") or {}).get(page_db.safe_id(wid))
    if doc is None:
        raise KeyError(f"no work {wid!r} in the dump; read work again")
    sess = dict(doc["data"].get("computer_session") or {}, archived_at=_stamp(now))
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
    tok = helper_usage.totals(file)
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
    try:
        import app_setup
        owner, name = app_setup.origin()
    except Exception:  # noqa: BLE001  no address: the step says to find it
        owner, name = "", ""
    source = f"https://github.com/{owner}/{name}" if owner and name else "<the copy's GitHub address>"
    home = {"title": "Job search: scheduled runs", "source_url": source,
            "prompt": "This chat runs the job search's scheduled tasks. Nothing to do now."}
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
        out.append(f"move {t.get('id')}: create_trigger {json.dumps(call, ensure_ascii=False)}, "
                   f"then update_trigger {{\"trigger_id\": \"{t.get('id')}\", \"enabled\": "
                   "false}} (turned off and kept, never deleted)" +
                   (", then python3 tools/routines.py record --trigger <the new id> --cron "
                    f"\"{t['cron_expression']}\" --setup routines_screen"
                    if "brief" in str(t.get("name") or "").lower() and t.get("cron_expression")
                    else ""))
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
        import app_model
        settings = {"profile/person.json app_updates": app_model.setting_values().get("app_updates")}
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


def memory_line(conflicts: list[dict]) -> str:
    """The start command's line about them, for Claude."""
    if not conflicts:
        return ""
    names = "; ".join(f"{os.path.basename(c['file'])} says {c['setting'].split()[-1]} is "
                      f"{c['memory_says']}, the setting is {c['setting_says']}" for c in conflicts[:3])
    return ("A note in this chat's own memory disagrees with the person's settings in profile/ "
            f"({names}). The settings win: follow profile/, never the note. Leave the note as "
            "it is (a chat rewriting its own memory is refused, and should be) and tell the "
            "person once, in one line, that an old note on this computer says otherwise and "
            "their setting is what counts.")


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
    p.add_argument("--name", required=True)
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
    p = sub.add_parser("started")
    p.add_argument("dump")
    for k in ("--work", "--session", "--env", "--computer"):
        p.add_argument(k, required=True)
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("archived")
    p.add_argument("dump")
    p.add_argument("--work", required=True)
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
    p.add_argument("--name", required=True)
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
            print(session_prompt(a.work, a.title or a.work, url,
                                 f"github.com/{owner}/{name}" if owner else "their job search"))
        elif a.cmd == "ready":
            print(ready(a.name, person.today()))
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
    now = _now(a.now)
    db = page_db.load(a.dump)
    out = getattr(a, "out", "") or os.path.join(a.dump, "out")
    if a.cmd == "beat":
        print(json.dumps({"batches": beat(db, a.name, now, out, dump_dir=a.dump,
                                          browser=a.browser, linkedin=a.linkedin,
                                          cookies=a.cookies, read=a.read, chat=a.chat)}))
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
            batches = archived(db, a.work, now, out)
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
    except KeyError as e:
        print(f"computer: {e.args[0]}", file=sys.stderr)
        return 2
    print(json.dumps({"batches": batches}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
