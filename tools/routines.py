#!/usr/bin/env python3
"""The scheduled-task registry (profile/routines.json): check it, and print each
task's prompt.

A scheduled task's stored prompt is a short stub that reads its instructions
from master. A wrong path, a cron with no time zone or a pasted id with a typo
fails at seven in the morning with nobody watching, so this checks the registry
whenever ci_local.sh runs, and the app's tests check the example's.

    python3 tools/routines.py check [path]   # exit 0 clean, 1 with every problem listed
    python3 tools/routines.py stub <key>     # the exact prompt to store for that task
    python3 tools/routines.py brief [--triggers <listing.json>]
                                             # is there a brief already? never make a second

Three set-ups are recognised (`setup` in the registry; automation/README.md
walks through the first two):

  chat_per_briefing  chats created with the repo, each task bound to one (its
                     own, or one shared by both); the chat's reply is the briefing
  routines_screen    each task created in the Claude app's Routines screen with
                     the repo ticked and notifications on; every run is a new chat
  ops_relay          the older shape: every task fires into one ops chat, which
                     hands its message to a fresh-session relay task for push
                     and email. A chat created now cannot make that hand-off.
                     A registry with an `ops_session` and no `setup` is this one.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

SETUPS = ("chat_per_briefing", "routines_screen", "ops_relay")
TRIGGER_ID = re.compile(r"trig_[A-Za-z0-9]+")
SESSION_ID = re.compile(r"session_[A-Za-z0-9]+")
TIMEZONE = re.compile(r"[A-Za-z]+(?:/[A-Za-z0-9_+-]+)+")
COMMON = "automation/prompts/_common.md"

# The stored prompt every work task gets, with its own label and file. It names
# the files rather than carrying the instructions, so changing what a task does
# is a pull request and never an edit to the task. A registry may override it
# with its own `stub`.
DEFAULT_STUB = (
    "Scheduled run: {label}. Run `git fetch origin master`, then read "
    "`" + COMMON + "` and `{prompt_file}` as they are on origin/master "
    "(`git show origin/master:<path>`) and follow them exactly. If either cannot "
    "be read, reply with one line saying which file and why.")


def setup_of(reg: dict) -> str:
    return reg.get("setup") or ("ops_relay" if "ops_session" in reg else "")


def work(reg: dict) -> list[dict]:
    """The tasks that do the work: everything but an ops_relay relay."""
    return [r for r in reg.get("routines", []) if r.get("mode") != "fresh_session"]


def stub(reg: dict, key: str) -> str:
    """The exact prompt to store for the task called `key`."""
    r = next(x for x in reg["routines"] if x["key"] == key)
    label = key.replace("_", " ")
    relay = next((x.get("trigger_id", "") for x in reg["routines"]
                  if x.get("mode") == "fresh_session"), "")
    return reg.get("stub", DEFAULT_STUB).format(
        label=label, Label=label.capitalize(), prompt_file=r["prompt_file"], relay_id=relay)


def check(reg: dict, root: str = ROOT) -> list[str]:
    """Every problem with the registry, as one line each; [] when it is clean."""
    out = []
    setup = setup_of(reg)
    if setup not in SETUPS:
        return [f"`setup` is {reg.get('setup')!r}; it must be one of {', '.join(SETUPS)}"]
    tz = reg.get("timezone", "")
    if not TIMEZONE.fullmatch(tz or ""):
        out.append(f"`timezone` {tz!r} is not an IANA zone like Europe/London")
    routines = reg.get("routines") or []
    if not work(reg):
        out.append("no work tasks in `routines`")
    if not os.path.isfile(os.path.join(root, COMMON)):
        out.append(f"{COMMON} is missing")
    for field in ("key", "name"):
        vals = [r.get(field) for r in routines]
        dup = sorted({v for v in vals if vals.count(v) > 1})
        if dup or None in vals:
            out.append(f"every task needs a unique `{field}`: {dup or 'one is missing'}")
    ids = [r["trigger_id"] for r in routines if r.get("trigger_id")]
    for i in ids:
        if not TRIGGER_ID.fullmatch(i):
            out.append(f"trigger id {i!r} is not well formed (trig_ then letters and digits)")
    if len(ids) != len(set(ids)):
        out.append("two tasks share a trigger id")
    for r in work(reg):
        name = r.get("key") or r.get("name") or "?"
        pf = r.get("prompt_file") or ""
        if not pf.startswith("automation/prompts/") or not os.path.isfile(os.path.join(root, pf)):
            out.append(f"{name}: prompt_file {pf!r} does not exist under automation/prompts/")
        cron = r.get("cron") or ""
        if not cron.startswith(f"CRON_TZ={tz} ") or len(cron.split()) != 6:
            out.append(f"{name}: cron {cron!r} must be `CRON_TZ={tz} ` and five fields, "
                       f"or it fires in UTC")
        if setup != "routines_screen" and not r.get("trigger_id"):
            out.append(f"{name}: no trigger_id; a chat-bound task is created from a chat, "
                       f"which reports the id")
        if setup == "routines_screen" and r.get("notifications", {}).get("push") is not True:
            out.append(f"{name}: a Routines-screen task needs notifications on "
                       f'("notifications": {{"push": true}}) or nobody hears from it')
    s = reg.get("stub", DEFAULT_STUB)
    if COMMON not in s or "{prompt_file}" not in s:
        out.append(f"`stub` must name {COMMON} and {{prompt_file}}")
    if setup == "chat_per_briefing":
        # Two tasks may share a chat (one chat to scroll); each must name a real one.
        for r in work(reg):
            sid = (r.get("chat") or {}).get("session_id", "")
            if not SESSION_ID.fullmatch(sid or ""):
                out.append(f"{r.get('key')}: chat.session_id {sid!r} is not well formed "
                           f"(session_ then letters and digits)")
    if setup == "ops_relay":
        sid = (reg.get("ops_session") or {}).get("id", "")
        if not SESSION_ID.fullmatch(sid or ""):
            out.append(f"ops_session.id {sid!r} is not well formed")
        relays = [r for r in routines if r.get("mode") == "fresh_session"]
        if len(relays) != 1:
            out.append(f"an ops_relay registry has exactly one relay task, not {len(relays)}")
        elif relays[0].get("cron") is not None or \
                relays[0].get("notifications") != {"push": True, "email": True}:
            out.append("the relay runs on no schedule and notifies by push and email")
    return out


BRIEF_FILE = "automation/prompts/morning_brief.md"
_BRIEFISH = re.compile(r"\bbrief", re.I)


def _is_brief(r: dict) -> bool:
    return r.get("key") == "morning_brief" or r.get("prompt_file") == BRIEF_FILE


def existing_brief(reg: dict | None, triggers=None) -> dict:
    """Whether a brief already exists, found by the registry or by a task's own prompt.

    Never by its title: a person's brief may be called "Job search: brief (Mon and
    Thu)" or anything else, and a second brief is two messages every morning.
    `triggers` is the account's scheduled tasks as a listing gives them (each with
    `id`, `name` and the stored `prompt`), when the session can list them.
    Returns {"state": "registered" | "found" | "ask" | "none", "id", "name", "say"}.
    """
    triggers = triggers or []
    mine = [r for r in work(reg or {}) if _is_brief(r)]
    if mine:
        r = mine[0]
        live = next((t for t in triggers if t.get("id") == r.get("trigger_id")), None)
        if triggers and r.get("trigger_id") and live is None:
            return {"state": "ask", "id": r.get("trigger_id", ""), "name": r.get("name", ""),
                    "say": f"profile/routines.json names the brief {r.get('name')!r} "
                           f"({r.get('trigger_id')}), and no scheduled task with that id is "
                           "listed: ask the person before making another"}
        return {"state": "registered", "id": r.get("trigger_id") or "", "name": r.get("name", ""),
                "say": f"the brief is set up: {r.get('name')!r}"
                       + (f" ({r['trigger_id']})" if r.get("trigger_id") else "")
                       + ", in profile/routines.json. Attach to it; never create a second"}
    for t in triggers:
        if BRIEF_FILE in (t.get("prompt") or "") or "Scheduled run: morning brief" in (t.get("prompt") or ""):
            return {"state": "found", "id": t.get("id", ""), "name": t.get("name", ""),
                    "say": f"a brief already exists as {t.get('name')!r} ({t.get('id')}), not yet "
                           "in profile/routines.json: record it there; never create a second"}
    named = [t for t in triggers if _BRIEFISH.search(t.get("name") or "")
             and "job" in (t.get("name") or "").lower()]
    if named:
        t = named[0]
        return {"state": "ask", "id": t.get("id", ""), "name": t.get("name", ""),
                "say": f"{t.get('name')!r} ({t.get('id')}) is named like a brief but its prompt "
                       "is not the brief's: ask the person before making another"}
    return {"state": "none", "id": "", "name": "",
            "say": "no brief yet: create one (automation/README.md)"}


def load(path: str | None = None) -> dict:
    if path is None:
        import person
        path = person.path("routines.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("check", "stub", "brief"):
        print(__doc__.split("\n\n")[1])
        return 2
    if argv[0] == "brief":
        triggers = []
        if "--triggers" in argv:
            with open(argv[argv.index("--triggers") + 1], encoding="utf-8") as fh:
                got = json.load(fh)
            triggers = got.get("triggers", got) if isinstance(got, dict) else got
        try:
            reg = load()
        except (OSError, ValueError):
            reg = None
        found = existing_brief(reg, triggers)
        print(f"{found['state']}: {found['say']}")
        import place
        if place.surface() == "local":
            # A chat on their computer never makes a local task for the brief: those run
            # only while the app is open. The brief is the cloud's, and they are told so.
            print("tell them: " + (place.BRIEF_LOCAL if found["state"] in ("registered", "found")
                                   else "Your brief will run in the cloud, so it arrives when "
                                        "your computer is off. Nothing to do on your computer."))
        return 0
    if argv[0] == "stub":
        if len(argv) < 2:
            print("usage: routines.py stub <key>", file=sys.stderr)
            return 2
        print(stub(load(), argv[1]))
        return 0
    path = argv[1] if len(argv) > 1 else None
    problems = check(load(path))
    for p in problems:
        print(f"routines.json: {p}")
    if not problems:
        print("routines.json: clean")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
