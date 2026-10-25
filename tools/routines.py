#!/usr/bin/env python3
"""The scheduled-task registry (profile/routines.json): check it, and print each
task's prompt.

A scheduled task's stored prompt is a short stub that reads its instructions
from master. A wrong path, a cron with no time zone or a pasted id with a typo
fails at seven in the morning with nobody watching, so this checks the registry
whenever ci_local.sh runs, and the app's tests check the example's.

    python3 tools/routines.py check [path]   # exit 0 clean, 1 with every problem listed
    python3 tools/routines.py stub <key>     # the exact prompt to store for that task
    python3 tools/routines.py brief [--triggers <listing.json>]...
                                             # is there a brief already? never make a second;
                                             # in a cloud chat, the calls that make one
    python3 tools/routines.py default        # the brief's days, time and zone, and the line
    python3 tools/routines.py record --session <id> --trigger <id> [--cron "<cron>"]
                                             # write the brief made into profile/routines.json

Three set-ups are recognised (`setup` in the registry; automation/README.md
walks through the first two):

  chat_per_briefing  chats created with the repo, each task bound to one (its
                     own, or one shared by both); the chat's reply is the briefing
  routines_screen    each task created as a routine (claude_surfaces: routines-cloud) with
                     the repo ticked and notifications on; every run is a new chat
  ops_relay          the older shape: every task fires into one ops chat, which
                     hands its message to a fresh-session relay task for push
                     and email. A chat created now cannot make that hand-off.
                     A registry with an `ops_session` and no `setup` is this one.
"""
from __future__ import annotations

import datetime
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


def _at_most_daily(cron: str) -> bool:
    """One minute of one hour: never `*`, a step, a range or a list in either field. An
    hourly pickup would cost about 12M tokens a day, each run paying the whole chat again
    (the cost audit of 2026-10-25)."""
    fields = cron.split()[1:3]
    return len(fields) == 2 and all(f.isdigit() for f in fields)


def check(reg: dict, root: str = ROOT) -> list[str]:
    """Every problem with the registry, as one line each; [] when it is clean."""
    out = []
    if not reg.get("routines") and "ops_session" not in reg:
        # Nothing scheduled yet is a state, not a fault: a registry written before the brief
        # was made failed every local check until it was (2026-10-25).
        return []
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
        elif not _at_most_daily(cron):
            out.append(f"{name}: cron {cron!r} runs more than once a day; every run is a whole "
                       f"chat's worth of tokens, so a task runs on one minute of one hour")
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
                (relays[0].get("notifications") or {}).get("push") is not True:
            # Push is what reaches the phone; email is never required (no email, 2026-10-25).
            out.append("the relay runs on no schedule and notifies by push")
    return out


BRIEF_FILE = "automation/prompts/morning_brief.md"
_BRIEFISH = re.compile(r"\bbrief", re.I)


def _is_brief(r: dict) -> bool:
    return r.get("key") == "morning_brief" or r.get("prompt_file") == BRIEF_FILE


def listing(got) -> tuple[list, bool]:
    """The account's scheduled tasks, from what list_triggers returned (its raw
    {"data": [...], "has_more": ...}, an older {"triggers": [...]}, or a bare list), each
    as {id, name, prompt, enabled, last_run}, and whether more pages remain. The prompt is
    under derived_state.prompt in the raw shape: read only at "prompt", a brief stored
    under another name was "none", and a second one was made (2026-10-25)."""
    more = False
    if isinstance(got, dict):
        more = bool(got.get("has_more"))
        got = got.get("data", got.get("triggers", []))
    out = []
    for t in got or []:
        if not isinstance(t, dict):
            continue
        prompt = t.get("prompt") or (t.get("derived_state") or {}).get("prompt") or ""
        out.append({"id": t.get("id", ""), "name": t.get("name", ""), "prompt": prompt,
                    "enabled": t.get("enabled", True), "last_run": t.get("last_run") or {},
                    "cron": t.get("cron_expression", ""),
                    "session": t.get("persistent_session_id") or ""})
    return out, more


def _is_brief_prompt(prompt: str) -> bool:
    return BRIEF_FILE in (prompt or "") or "Scheduled run: morning brief" in (prompt or "")


def _health(t: dict | None) -> str:
    """What is wrong with a brief that exists: turned off, or its last run failed."""
    if not t:
        return ""
    if t.get("enabled") is False:
        return (" It is turned off (enabled: false): ask the person whether to turn it back "
                "on; never make a second.")
    run = t.get("last_run") or {}
    if str(run.get("status") or "").upper() in ("FAILED", "ERROR", "ERRORED"):
        return (f" Its last run, {run.get('fired_at') or 'the latest'}, failed: read that run's "
                "chat before anything else.")
    return ""


def existing_brief(reg: dict | None, triggers=None) -> dict:
    """Whether a brief already exists, found by the registry or by a task's own prompt.

    Never by its title: a person's brief may be called "Job search: brief (Mon and
    Thu)" or anything else, and a second brief is two messages every morning.
    `triggers` is the account's scheduled tasks as `listing` gives them, or None when the
    session cannot list them. An empty listing is a listing: a registry entry missing from
    it is asked about, never read as set up.
    Returns {"state": "registered" | "found" | "ask" | "none", "id", "name", "say"}.
    """
    listed = triggers is not None
    triggers = triggers or []
    mine = [r for r in work(reg or {}) if _is_brief(r)]
    if mine:
        r = mine[0]
        live = next((t for t in triggers if r.get("trigger_id") and t.get("id") == r.get("trigger_id")),
                    None) or next((t for t in triggers if _is_brief_prompt(t.get("prompt"))), None)
        if listed and live is None:
            return {"state": "ask", "id": r.get("trigger_id", ""), "name": r.get("name", ""),
                    "say": f"profile/routines.json names the brief {r.get('name')!r}"
                           + (f" ({r.get('trigger_id')})" if r.get("trigger_id") else "")
                           + ", and no scheduled task like it is listed: ask the person before "
                           "making another"}
        moved = (f" The account lists it as {live['id']}: record that id (routines.py record)."
                 if live and live.get("id") and live["id"] != r.get("trigger_id") else "")
        return {"state": "registered", "id": r.get("trigger_id") or "", "name": r.get("name", ""),
                "say": f"the brief is set up: {r.get('name')!r}"
                       + (f" ({r['trigger_id']})" if r.get("trigger_id") else "")
                       + ", in profile/routines.json. Attach to it; never create a second."
                       + moved + _health(live)}
    for t in triggers:
        if _is_brief_prompt(t.get("prompt")):
            return {"state": "found", "id": t.get("id", ""), "name": t.get("name", ""),
                    "say": f"a brief already exists as {t.get('name')!r} ({t.get('id')}), not yet "
                           "in profile/routines.json: record it there (routines.py record); never "
                           "create a second." + _health(t)}
    named = [t for t in triggers if _BRIEFISH.search(t.get("name") or "")
             and "job" in (t.get("name") or "").lower()]
    if named:
        t = named[0]
        return {"state": "ask", "id": t.get("id", ""), "name": t.get("name", ""),
                "say": f"{t.get('name')!r} ({t.get('id')}) is named like a brief but its prompt "
                       "is not the brief's: ask the person before making another"}
    return {"state": "none", "id": "", "name": "",
            "say": "no brief yet: create one (automation/README.md)"}


# ------------------------------------------------------------------ making the brief

BRIEF_NAME = "Job search: morning brief"
BRIEF_DAYS = (1, 4)                     # Monday and Thursday: what suits most searches
DAY_NAMES = {1: "Mondays", 2: "Tuesdays", 3: "Wednesdays", 4: "Thursdays", 5: "Fridays",
             6: "Saturdays", 0: "Sundays", 7: "Sundays"}


def brief_minute(name: str = BRIEF_NAME, hour: int = 8) -> tuple[int, int]:
    """(hour, minute) for a brief meant for `hour` o'clock: moved off the hour by the
    scheduler's own rule (letters in the task's name, mod 29, plus 1, minutes earlier),
    because most tasks start on the hour and those can start late. 8:00 is 7:38."""
    back = sum(c.isalpha() for c in name) % 29 + 1
    return (hour - 1, 60 - back)


def home_zone() -> str:
    """The person's own zone, where the profile says it (networking.py TIMEZONE or
    HOME_CITY); "" when it does not."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        import reading
        return reading.home_zone() or ""
    except Exception:  # no profile yet, or a profile without the setting
        return ""


def default(zone: str = "", days=BRIEF_DAYS, hour: int = 8) -> dict:
    """The brief nobody had to be asked about: Monday and Thursday at 7:38 their time."""
    zone = zone or home_zone()
    h, m = brief_minute(hour=hour)
    day_list = ",".join(str(d) for d in days)
    named = " and ".join(DAY_NAMES[d] for d in days)
    return {"zone": zone, "cron": f"CRON_TZ={zone} {m} {h} * * {day_list}" if zone else "",
            "when": f"{named} at {h}:{m:02d}",
            "say": f"Your brief is set up: {named} at {h}:{m:02d}, in the chat called "
                   f"{BRIEF_NAME}. Say 'move my brief' to change it."}


def plan(owner: str, name: str, zone: str = "", now: datetime.datetime | None = None) -> dict:
    """The exact calls a cloud chat makes to set the brief up with no questions: its own
    chat on the private copy, a task bound to that chat, and one first run a few minutes
    on (never fire_trigger, which starts a new chat with no copy in it)."""
    d = default(zone)
    stub_text = DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                    prompt_file=BRIEF_FILE, relay_id="")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    first = (now + datetime.timedelta(minutes=5)).replace(microsecond=0)
    return {
        "create_session": {"title": BRIEF_NAME,
                           "source_url": f"https://github.com/{owner}/{name}"},
        "create_trigger": {"name": BRIEF_NAME, "persistent_session_id": "<the session id>",
                           "cron_expression": d["cron"], "prompt": stub_text,
                           "connectors": [], "initiation": "human_request"},
        "first_brief": {"name": "Job search: first brief", "persistent_session_id":
                        "<the session id>", "run_once_at": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "prompt": stub_text, "connectors": [], "initiation": "human_request"},
        "record": (f"python3 tools/routines.py record --session <the session id> --trigger "
                   f"<the task's id> --cron \"{d['cron']}\""),
        "say": d["say"], "zone": d["zone"]}


def record(session: str, trigger: str, cron: str = "", path: str | None = None,
           setup: str = "chat_per_briefing") -> str:
    """Write the brief just made into profile/routines.json, keeping every other task."""
    if path is None:
        import person
        path = person.path("routines.json")
    try:
        reg = load(path)
    except (OSError, ValueError):
        reg = {}
    reg.pop("_about", None) if reg.get("_about", "").startswith("The example person's") else None
    cron = cron or default()["cron"]
    m = re.match(r"CRON_TZ=(\S+) ", cron)
    reg["setup"] = reg.get("setup") or setup
    reg["timezone"] = (m.group(1) if m else "") or reg.get("timezone", "")
    keep = [r for r in reg.get("routines") or [] if not _is_brief(r)]
    entry = {"key": "morning_brief", "name": BRIEF_NAME,
             "trigger_id": trigger, "cron": cron, "prompt_file": BRIEF_FILE,
             "what": "Twice a week: what is owed, the counts since the last brief, three things "
                     "to do, and the news that matters."}
    if reg["setup"] == "chat_per_briefing":
        entry["chat"] = {"title": BRIEF_NAME, "session_id": session}
    reg["routines"] = [entry] + keep
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def load(path: str | None = None) -> dict:
    if path is None:
        import person
        path = person.path("routines.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/routines.py check [<registry>] | stub <id> | brief | "
              "default | record\n\n"
              + __doc__.split("\n\n")[1])
        return 0
    if not argv or argv[0] not in ("check", "stub", "brief", "default", "record"):
        print(__doc__.split("\n\n")[1])
        return 2
    if argv[0] == "brief":
        triggers, more = None, False
        for i, a in enumerate(argv):
            if a == "--triggers" and i + 1 < len(argv):
                with open(argv[i + 1], encoding="utf-8") as fh:
                    page, more = listing(json.load(fh))
                triggers = (triggers or []) + page
        try:
            reg = load()
        except Exception:  # no profile yet (setup), no registry, or a bad one: none on file
            reg = None
        found = existing_brief(reg, triggers)
        print(f"{found['state']}: {found['say']}")
        if more:
            print("more: the listing has another page (has_more); list it too and pass every "
                  "page with --triggers before deciding")
        import claude_surfaces
        import place
        if place.surface() == "local":
            # A chat on their computer never makes a local task for the brief: those run on
            # the computer (claude_surfaces: routines-local). The brief is the cloud's.
            if found["state"] in ("registered", "found"):
                print("tell them: " + place.BRIEF_LOCAL)
            elif found["state"] == "none":
                print("make it in the cloud: with the RemoteTrigger tool where this chat has it "
                      "(claude_surfaces: remote-trigger), as set-up (b); never a desktop "
                      "scheduled task, and never a cloud chat started from this shell")
                print("otherwise tell them, once: Your brief will run in the cloud, so it arrives "
                      "when your computer is off. " + "\n".join(claude_surfaces.steps("routines-cloud")))
            for eid in ("routines-cloud", "remote-trigger", "routines-local", "cli-cloud"):
                w = claude_surfaces.warning(claude_surfaces.entry(eid))
                if w:
                    print(w)
        elif found["state"] == "none" and triggers is not None:
            # A cloud chat makes it itself, asking nothing: its own chat on the private copy,
            # a task bound to it, and a first run in a few minutes (automation/README.md (a)).
            owner, name = place.repo()
            got = plan(owner, name)
            if not got["zone"]:
                print("zone: the profile names no time zone (networking.py TIMEZONE or "
                      "HOME_CITY): set it from where they live, then run this again")
                return 1
            print("make it now, asking nothing, with these calls in this order:")
            for call in ("create_session", "create_trigger", "first_brief"):
                tool = "create_trigger" if call == "first_brief" else call
                print(f"  {tool} ({call}): {json.dumps(got[call], ensure_ascii=False)}")
            print(f"  then: {got['record']}, then commit and land it")
            print(f"  tell them: {got['say']}")
        elif found["state"] == "none":
            print("list the account's scheduled tasks first (list_triggers) and pass them with "
                  "--triggers: a brief under another name must never be made twice")
        return 0
    if argv[0] == "default":
        got = default()
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 0 if got["zone"] else 1
    if argv[0] == "record":
        opt = {k: argv[argv.index(k) + 1] for k in ("--session", "--trigger", "--cron", "--setup")
               if k in argv and argv.index(k) + 1 < len(argv)}
        if not opt.get("--trigger") or (opt.get("--setup", "chat_per_briefing") ==
                                        "chat_per_briefing" and not opt.get("--session")):
            print("usage: routines.py record --session <id> --trigger <id> [--cron \"<cron>\"] "
                  "[--setup routines_screen]", file=sys.stderr)
            return 2
        path = record(opt.get("--session", ""), opt["--trigger"], opt.get("--cron", ""),
                      setup=opt.get("--setup", "chat_per_briefing"))
        problems = check(load(path))
        for p_ in problems:
            print(f"routines.json: {p_}")
        print("routines.json: recorded the brief" + ("" if problems else ", clean"))
        return 1 if problems else 0
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
