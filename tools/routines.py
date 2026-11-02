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
    python3 tools/routines.py record --session <id> --trigger <id> [--cron "<cron>"] [--own-chat]
                                             # write the brief made into profile/routines.json
    python3 tools/routines.py move --days weekdays --time 07:38
                                             # the brief's new days and time, written here
    python3 tools/routines.py pause --until <YYYY-MM-DD> | resume
                                             # a break: the brief and every follow-up held
    python3 tools/routines.py off | on       # the brief alone turned off, or on again
    python3 tools/routines.py calls | called <n> [--id <trig_...>]
                                             # the scheduled-task calls a chat still owes

Code cannot change a scheduled task: only a chat can (update_trigger, create_trigger). So
`move`, `pause`, `resume`, `off` and `on` write the registry and the state files, and keep
the calls a chat owes in the registry (`owed`) until `called` says each was made. The page
queues the change (its actions brief.move, brief.pause, brief.resume, brief.off, brief.on);
the chat that applies them, or the next one that starts, makes the calls. Nobody gets a
brief they did not ask for: it is made only when the person turns it on (the bell on their
Brief, or Settings), every day at 7:38 their time unless they choose other days.

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
if os.path.join(ROOT, "tools", "network") not in sys.path:
    sys.path.insert(1, os.path.join(ROOT, "tools", "network"))

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


# A task that runs in a cloud chat can land in a chat with no copy of the files: its chat
# was deleted and the task woke a new, empty one ("Morning brief could not start: no git
# repo", 2026-10-31, two days of no brief). Its stored prompt says how to get the copy, so it
# runs in whichever chat it lands in, and moving it (tools/tidy.py) is tidiness, never a fix.
COPY_MARK = "If this chat has no copy of "
COPY_LINE = (COPY_MARK + "{repo} (a folder with `" + COMMON + "` in it), get one first: "
             "add_repo (owner {owner}, repo {name}, access push), clone it as add_repo says, "
             "and do everything below in that folder. ")


def with_copy(text: str, repo: str) -> str:
    """`text`, a stored prompt, with the line that gets the copy when the chat has none, put
    after its first sentence. Unchanged without a repo ("owner/name") or with the line in."""
    if not text or COPY_MARK in text or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo or ""):
        return text
    owner, name = repo.split("/", 1)
    head, sep, rest = text.partition(". ")
    if not sep:
        return text
    return head + sep + COPY_LINE.format(repo=repo, owner=owner, name=name) + rest


def setup_of(reg: dict) -> str:
    return reg.get("setup") or ("ops_relay" if "ops_session" in reg else "")


def work(reg: dict) -> list[dict]:
    """The tasks that do the work: everything but an ops_relay relay."""
    return [r for r in reg.get("routines", []) if r.get("mode") != "fresh_session"]


def stub(reg: dict, key: str, own_chat: bool = False) -> str:
    """The exact prompt to store for the task called `key`. In the older ops set-up, a task
    that runs in a chat of its own (`own_chat`, or a `chat` in its entry) gets the plain
    stub: the registry's own one says "You are in the Job search ops session"."""
    r = next(x for x in reg["routines"] if x["key"] == key)
    label = key.replace("_", " ")
    relay = next((x.get("trigger_id", "") for x in reg["routines"]
                  if x.get("mode") == "fresh_session"), "")
    plain = setup_of(reg) == "ops_relay" and (own_chat or bool(r.get("chat")))
    return (DEFAULT_STUB if plain else reg.get("stub", DEFAULT_STUB)).format(
        label=label, Label=label.capitalize(), prompt_file=r["prompt_file"], relay_id=relay)


def at_most_daily(cron: str) -> bool:
    """One minute of one hour: never `*`, a step, a range or a list in either field. An
    hourly pickup would cost about 12M tokens a day, each run paying the whole chat again
    (the cost audit of 2026-10-25)."""
    fields = cron.split()[1:3]
    return len(fields) == 2 and all(f.isdigit() for f in fields)


_at_most_daily = at_most_daily  # the module's own name for it; other modules call at_most_daily


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
# What a chat on the person's computer says to "set up my brief": the bell does it, in the cloud.
BRIEF_BELL = ("Your morning brief is ready to start: press the bell on your Brief once. It "
              "comes from Claude's helper in the cloud, so it arrives when your computer is off.")
BRIEF_DAYS = (0, 1, 2, 3, 4, 5, 6)      # every day: one short read each morning (the maintainer, 2026-10-29)
DAY_NAMES = {1: "Mondays", 2: "Tuesdays", 3: "Wednesdays", 4: "Thursdays", 5: "Fridays",
             6: "Saturdays", 0: "Sundays", 7: "Sundays"}


def day_words(days) -> str:
    """"Every day", "Weekdays", "Weekends" or "Mondays and Thursdays", for days Sunday 0."""
    d = sorted({int(x) % 7 for x in days})
    if d == list(range(7)):
        return "Every day"
    if d == [1, 2, 3, 4, 5]:
        return "Weekdays"
    if d == [0, 6]:
        return "Weekends"
    names = [DAY_NAMES[x] for x in d]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def in_sentence(when: str) -> str:
    """"Every day at 7:38" as it reads mid-sentence: "every day at 7:38"; day names keep
    their capital."""
    first = when.split(" ", 1)[0]
    return when[:1].lower() + when[1:] if first in ("Every", "Weekdays", "Weekends") else when


def _cron_days(days) -> str:
    """The cron's day field: "*" for every day, else the days, Sunday 0."""
    d = sorted({int(x) % 7 for x in days})
    return "*" if d == list(range(7)) else ",".join(str(x) for x in d)


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
    """The brief as it is first made, with no questions: every day at 7:38 their time."""
    zone = zone or home_zone()
    h, m = brief_minute(hour=hour)
    named = day_words(days)
    return {"zone": zone, "cron": f"CRON_TZ={zone} {m} {h} * * {_cron_days(days)}" if zone else "",
            "when": f"{named} at {h}:{m:02d}",
            "say": f"Your brief is on: {in_sentence(named)} at {h}:{m:02d}. Change it or turn it "
                   f"off from the bell on your Brief."}


def plan(owner: str, name: str, zone: str = "", now: datetime.datetime | None = None,
         chat: str = "") -> dict:
    """The exact calls a cloud chat makes to set the brief up with no questions: a task
    bound to the chat that answers the page (`chat`, this one by default), so the brief
    starts no chat of its own, and one first run a few minutes on (never fire_trigger, which
    starts a new chat with no copy in it). No chat is ever made for it: where this chat's id
    cannot be read, `chat` is empty and the caller asks get_session for it first."""
    d = default(zone)
    stub_text = with_copy(DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                              prompt_file=BRIEF_FILE, relay_id=""),
                          f"{owner}/{name}" if owner and name else "")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    first = (now + datetime.timedelta(minutes=5)).replace(microsecond=0)
    if not chat:
        import app_listen
        chat = app_listen.this_chat()
    chat = chat if str(chat).startswith("session_") else ""
    sid = chat or "<the session id>"
    out = {
        "create_trigger": {"name": BRIEF_NAME, "persistent_session_id": sid,
                           "cron_expression": d["cron"], "prompt": stub_text,
                           "connectors": [], "initiation": "human_request"},
        "first_brief": {"name": "Job search: first brief", "persistent_session_id": sid,
                        "run_once_at": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "prompt": stub_text, "connectors": [], "initiation": "human_request"},
        "record": (f"python3 tools/routines.py record --session {sid} --trigger "
                   f"<the task's id> --cron \"{d['cron']}\""),
        "say": d["say"], "zone": d["zone"], "chat": chat}
    return out


def record(session: str, trigger: str, cron: str = "", path: str | None = None,
           setup: str = "chat_per_briefing", title: str = "", own_chat: bool = False) -> str:
    """Write the brief just made into profile/routines.json, keeping every other task. The
    chat it runs in is named only when it was made for it; bound to the chat that answers
    the page, it is that chat's id alone. In the older ops set-up it is named only with
    `own_chat` (the brief moved out of a lost ops chat): a chat recording a re-listed id
    names itself, and a `chat` there would stop the relay to the phone."""
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
    # An older ops registry stays one (its relay and other tasks are checked as one); the
    # brief alone names the chat it moved into.
    reg["setup"] = setup_of(reg) or setup
    reg["timezone"] = (m.group(1) if m else "") or reg.get("timezone", "")
    keep = [r for r in reg.get("routines") or [] if not _is_brief(r)]
    entry = {"key": "morning_brief", "name": BRIEF_NAME,
             "trigger_id": trigger, "cron": cron, "prompt_file": BRIEF_FILE,
             "what": "Each morning: what is owed, the counts since the last brief, three things "
                     "to do, and the news that matters."}
    was = next((r for r in reg.get("routines") or [] if _is_brief(r)), None) or {}
    if was.get("off"):
        entry["off"] = True
    ops = (reg.get("ops_session") or {}).get("id", "")
    if reg["setup"] == "chat_per_briefing" or (
            reg["setup"] == "ops_relay" and own_chat and session and session != ops):
        entry["chat"] = {"session_id": session, **({"title": title} if title else {})}
    reg["routines"] = [entry] + keep
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path



# ------------------------------------------------------------------ the daily upkeep

# A person who opens only their page, never a chat, had a copy and a page nothing kept current:
# only a chat takes the app's updates and writes the page's data, and a page can wake a chat
# only from a tap (the maintainer, 2026-11-02: "it just hasnt updated... i need to go into chat
# myself or press a button"). The brief does it every morning it runs; where it does not run
# every day, this silent task, bound to the chat that answers the page, does it once a day.
# tools/tidy.py makes it, keeps it bound to that chat as it renews, and takes it away once a
# daily brief does the same.
UPKEEP_KEY = "upkeep"
UPKEEP_NAME = "Job search: daily upkeep"
UPKEEP_FILE = "automation/prompts/upkeep.md"


def upkeep_entry(reg: dict) -> dict | None:
    return next((r for r in reg.get("routines") or [] if r.get("key") == UPKEEP_KEY), None)


def brief_every_day(reg: dict) -> bool:
    """Is the brief on, with a task, every day of the week? Then it keeps things current."""
    r = _brief(reg)
    if not r or r.get("off") or not r.get("trigger_id"):
        return False
    return read_cron(r.get("cron") or "").get("days") == list(range(7))


def needs_upkeep(reg: dict) -> bool:
    return not brief_every_day(reg)


def upkeep_cron(reg: dict) -> str:
    """Once a day, before the person is up: 5-something in their zone, off the hour."""
    zone = reg.get("timezone") or home_zone()
    if not zone:
        return ""
    h, m = brief_minute(UPKEEP_NAME, hour=6)
    return f"CRON_TZ={zone} {m} {h} * * *"


def upkeep_stub(repo: str = "") -> str:
    return with_copy(DEFAULT_STUB.format(label="daily upkeep", Label="Daily upkeep",
                                         prompt_file=UPKEEP_FILE, relay_id=""), repo)


def record_upkeep(session: str, trigger: str, cron: str, path: str | None = None) -> str:
    """Write the upkeep task just made (or moved to a new chat) into profile/routines.json."""
    if path is None:
        import person
        path = person.path("routines.json")
    try:
        reg = load(path)
    except (OSError, ValueError):
        reg = {}
    m = re.match(r"CRON_TZ=(\S+) ", cron or "")
    reg["setup"] = setup_of(reg) or "chat_per_briefing"
    reg["timezone"] = reg.get("timezone") or (m.group(1) if m else "")
    keep = [r for r in reg.get("routines") or [] if r.get("key") != UPKEEP_KEY]
    keep.append({"key": UPKEEP_KEY, "name": UPKEEP_NAME, "trigger_id": trigger, "cron": cron,
                 "prompt_file": UPKEEP_FILE, "chat": {"session_id": session},
                 "what": "Once a day, silently: the app's updates, the page's data, and any "
                         "work still waiting. Only where the brief does not run every day."})
    reg["routines"] = keep
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def forget_upkeep(path: str | None = None) -> str:
    if path is None:
        import person
        path = person.path("routines.json")
    reg = load(path)
    reg["routines"] = [r for r in reg.get("routines") or [] if r.get("key") != UPKEEP_KEY]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


# ------------------------------------------------------------------ the brief's schedule

DAY_WORDS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
# Said with the date of a break, on contacts and on applications: the forms
# tools/network/state.py action_hold and tools/followups.py not_chased already read.
HOLD = "HOLD until {until} (search paused {since}): "
NOT_CHASED = "{since}: DO NOT CHASE until {until} (search paused)"
CHASE_AGAIN = "{today}: chase again (search resumed)"


def _days(value) -> list[int]:
    """Days of the week, Sunday 0: from "mon,thu", "1,4", "Mondays and Thursdays", "every
    day", "weekdays" or a list."""
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        items = re.findall(r"[A-Za-z]+|\d", str(value or ""))
    out = []
    for it in items:
        low = it.lower()
        if low.isdigit() and 0 <= int(low) <= 7:
            out.append(int(low) % 7)
        elif low in ("every", "daily"):
            out += list(range(7))
        elif low == "weekdays":
            out += [1, 2, 3, 4, 5]
        elif low == "weekends":
            out += [0, 6]
        elif low[:3] in DAY_WORDS and low not in ("and",):
            out.append(DAY_WORDS[low[:3]])
    return sorted(set(out))


def _clock(value) -> tuple[int, int]:
    """(hour, minute) from "07:38", "7.38", "8", "8am" or "6pm"."""
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm)?\s*", str(value or ""), re.I)
    if not m:
        raise ValueError(f"{value!r} is not a time of day")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3):
        h = h % 12 + (12 if m.group(3).lower() == "pm" else 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValueError(f"{value!r} is not a time of day")
    return h, mi


def cron_for(days, time, zone: str, name: str = BRIEF_NAME) -> dict:
    """The cron for the brief on these days at this time, in their zone, and the words for
    it. A time on the hour or half hour moves a few minutes earlier, by the scheduler's own
    rule (brief_minute), because tasks on the hour start late."""
    d = _days(days)
    if not d:
        raise ValueError("name at least one day")
    h, m = _clock(time)
    back = sum(c.isalpha() for c in name) % 29 + 1
    if m == 0 and h != 0:                       # midnight is left as asked
        h, m = h - 1, 60 - back
    elif m == 30:
        m = 30 - back
    return {"cron": f"CRON_TZ={zone} {m} {h} * * {_cron_days(d)}",
            "when": f"{day_words(d)} at {h}:{m:02d}", "days": d, "time": f"{h:02d}:{m:02d}"}


def read_cron(cron: str) -> dict:
    """{zone, days, time, when} from a brief's cron, or {} when it is not one this reads."""
    m = re.fullmatch(r"CRON_TZ=(\S+) (\d+) (\d+) \* \* (\S+)", str(cron or "").strip())
    if not m:
        return {}
    days: list[int] = []
    for part in m.group(4).split(","):
        if part == "*":
            days = list(range(7))
            break
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                days += list(range(int(a), int(b) + 1))
        elif part.isdigit():
            days.append(int(part))
    days = sorted({x % 7 for x in days})
    h, mi = int(m.group(3)), int(m.group(2))
    return {"zone": m.group(1), "days": days, "time": f"{h:02d}:{mi:02d}",
            "when": (day_words(days) if days else "") + f" at {h}:{mi:02d}"}


def _path(path: str | None) -> str:
    if path is None:
        import person
        return person.path("routines.json")
    return path


def _save(reg: dict, path: str) -> str:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def _brief(reg: dict) -> dict | None:
    return next((r for r in work(reg) if _is_brief(r)), None)


def _owe(reg: dict, call: dict) -> None:
    """Keep a scheduled-task call a chat must make; a newer one for the same task and the
    same kind of change replaces an older one."""
    def task(c):
        return (c.get("args") or {}).get("trigger_id")
    # The same task: a zone move owes one update for the brief and one for the job round.
    owed = [c for c in reg.get("owed") or []
            if not (c.get("tool") == call.get("tool") and c.get("for") == call.get("for")
                    and task(c) == task(call))]
    owed.append(call)
    for n, c in enumerate(owed, 1):
        c["n"] = n
    reg["owed"] = owed


def calls(path: str | None = None) -> list[dict]:
    """The scheduled-task calls a chat still owes, oldest first; [] with no registry."""
    try:
        return list(load(_path(path)).get("owed") or [])
    except (OSError, ValueError):
        return []


def called(n: int, trigger: str = "", path: str | None = None) -> dict:
    """A call was made: it leaves the list. A one-off brief made for the end of a break
    keeps its id, so resuming early can take it away again."""
    path = _path(path)
    reg = load(path)
    owed = reg.get("owed") or []
    hit = next((c for c in owed if c.get("n") == n), None)
    if hit is None:
        raise ValueError(f"no call {n} is owed")
    if hit.get("for") == "back" and trigger and reg.get("pause"):
        reg["pause"]["back_trigger"] = trigger
    reg["owed"] = [c for c in owed if c is not hit]
    for i, c in enumerate(reg["owed"], 1):
        c["n"] = i
    _save(reg, path)
    return hit


def _task_ref(r: dict, reg: dict) -> dict:
    out = {"trigger_id": r.get("trigger_id") or None}
    if not r.get("trigger_id"):
        out["where"] = ("the brief's own routine (RemoteTrigger where this chat has it, else its "
                        "page under claude.ai/code/routines)")
    return out


def move(days=None, time=None, cron: str = "", path: str | None = None, zone: str = "") -> dict:
    """New days and a new time for the brief: written into the registry, and the one call
    that moves the task itself kept until a chat makes it. `cron` sets it outright (an undo).
    `zone` moves it to another time zone, the page's own choice (2026-10-30)."""
    path = _path(path)
    reg = load(path)
    r = _brief(reg)
    if r is None:
        raise ValueError("there is no brief yet to move")
    old = r.get("cron") or ""
    if zone:
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(zone)
        except Exception:  # noqa: BLE001  not a zone this computer knows
            raise ValueError(f"{zone!r} is not a time zone") from None
        moved_from = reg.get("timezone") or ""
        reg["timezone"] = zone
        # Every scheduled task runs on the one zone, at the same clock time as before: the
        # job round at 06:52 stays 06:52 where the person now is.
        for other in reg.get("routines") or []:
            c = str(other.get("cron") or "")
            if other is r or not c.startswith("CRON_TZ="):
                continue
            new_c = f"CRON_TZ={zone} " + c.split(" ", 1)[1]
            if new_c != c:
                other["cron"] = new_c
                if moved_from != zone and other.get("trigger_id"):
                    _owe(reg, {"tool": "update_trigger", "for": "move",
                               "args": {**_task_ref(other, reg), "cron_expression": new_c},
                               "why": f"{other.get('name') or other.get('key')} keeps its time in {zone}"})
    zone = reg.get("timezone") or home_zone()
    if not zone:
        raise ValueError("the profile names no time zone")
    if cron:
        got = read_cron(cron)
        if not got:
            raise ValueError(f"{cron!r} is not a brief's schedule")
        new = {"cron": cron, **got}
    else:
        was = read_cron(old)
        new = cron_for(days if days not in (None, "", []) else was.get("days") or BRIEF_DAYS,
                       time or was.get("time") or "08:00", zone)
    r["cron"] = new["cron"]
    if new["cron"] != old:
        _owe(reg, {"tool": "update_trigger", "for": "move",
                   "args": {**_task_ref(r, reg), "cron_expression": new["cron"]},
                   "why": f"the brief now comes {in_sentence(new['when'])}"})
    problems = check(reg)
    if problems:
        raise ValueError("; ".join(problems))
    _save(reg, path)
    return {"cron": new["cron"], "when": new["when"], "old": old,
            "say": f"Your brief comes {in_sentence(new['when'])} from now on.",
            "undo": {"action": "brief.move", "value": {"cron": old}} if old else None,
            "calls": reg.get("owed") or []}


def off(path: str | None = None) -> dict:
    """The brief turned off, kept on file: its task is disabled (a call kept for a chat) and
    nothing else changes, so turning it on again brings back the same days and time."""
    path = _path(path)
    reg = load(path)
    r = _brief(reg)
    if r is None:
        raise ValueError("there is no brief to turn off")
    if r.get("off"):
        return {"changed": False, "say": "Your brief is off already.", "undo": None,
                "calls": reg.get("owed") or []}
    r["off"] = True
    reg["owed"] = [c for c in reg.get("owed") or [] if c.get("for") != "on"]
    _owe(reg, {"tool": "update_trigger", "for": "off",
               "args": {**_task_ref(r, reg), "enabled": False},
               "why": "the person turned the brief off"})
    _save(reg, path)
    return {"changed": True, "say": "Your brief is off. Nothing else stops.",
            "undo": {"action": "brief.on"}, "calls": reg.get("owed") or []}


def on(path: str | None = None) -> dict:
    """The brief turned on again, on its old days and time; during a break it waits for
    the break to end (resume turns it on then)."""
    path = _path(path)
    reg = load(path)
    r = _brief(reg)
    if r is None:
        raise ValueError("there is no brief yet to turn on")
    if not r.get("off"):
        return {"changed": False, "say": "Your brief is on already.", "undo": None,
                "calls": reg.get("owed") or []}
    r.pop("off", None)
    reg["owed"] = [c for c in reg.get("owed") or [] if c.get("for") != "off"]
    p = reg.get("pause") or {}
    if not p:
        _owe(reg, {"tool": "update_trigger", "for": "on",
                   "args": {**_task_ref(r, reg), "enabled": True},
                   "why": "the person turned the brief on again"})
    _save(reg, path)
    when = in_sentence((read_cron(r.get("cron") or "") or {}).get("when") or "on its days")
    return {"changed": True,
            "say": (f"Your brief is on again from {_short(datetime.date.fromisoformat(p['until']))}, "
                    f"{when}." if p else f"Your brief is on again: {when}."),
            "undo": {"action": "brief.off"}, "calls": reg.get("owed") or []}


def _live_contacts(contacts: list, threads: list, today: str) -> list:
    """The contacts a dated follow-up or a reply could fall due on: anyone with a next action
    or a date for it, and anyone owed something, who is not closed."""
    import schema
    import state
    owed = {o["contact_id"] for o in state.owed(contacts, threads, today)}
    out = []
    for c in contacts:
        if str(c.get("status") or "") in schema.TERMINAL:
            continue
        if c.get("next_action") or c.get("next_action_due") or c.get("contact_id") in owed:
            out.append(c)
    return out


def pause(until: str, today: str = "", path: str | None = None) -> dict:
    """A break until a date: the brief held (turned off, with one brief on the day they come
    back) and every follow-up held with it. Each contact's next action opens "HOLD until
    <date>" and each live application carries "DO NOT CHASE until <date>", the forms the due
    list and the nudges already read, so nothing falls due meanwhile; what they held before
    is kept, so resuming puts each back exactly."""
    import person
    import state
    import csv_store
    import throttle
    path = _path(path)
    today = today or datetime.date.today().isoformat()
    try:
        end = datetime.date.fromisoformat(str(until))
    except ValueError:
        raise ValueError(f"{until!r} is not a date (YYYY-MM-DD)") from None
    if end <= datetime.date.fromisoformat(today):
        raise ValueError("a break ends after today")
    try:
        reg = load(path)
    except (OSError, ValueError):
        reg = {}
    was = reg.get("pause") or {}
    held = dict(was.get("contacts") or {})
    contacts_path = person.state("network_contacts.csv")
    if os.path.exists(contacts_path):
        contacts = state.load_contacts(contacts_path)
        threads_path = person.state("network_threads.csv")
        threads = state.load_threads(threads_path) if os.path.exists(threads_path) else []
        for c in _live_contacts(contacts, threads, today):
            cid = c.get("contact_id") or ""
            before = held.get(cid, c.get("next_action") or "")
            if cid not in held and state.action_hold(before, today):
                continue                     # already held by their own hold
            held[cid] = before
            state.set_contact(contacts, threads, cid, next_action=HOLD.format(
                until=end.isoformat(), since=was.get("since") or today) + (before or
                                                                           "nothing set"))
        state.save_contacts(contacts, contacts_path)
    apps = [list(a) for a in was.get("applications") or []]
    tracker = person.state("job_search_tracker.csv")
    if os.path.exists(tracker):
        rows = csv_store.read_rows(tracker)
        live = set(throttle.LIVE_PROCESS) | {"applied"}
        note = NOT_CHASED.format(since=today, until=end.isoformat())
        for row in rows:
            if str(row.get("status") or "").strip().lower() not in live:
                continue
            row["notes"] = ((row.get("notes") or "").rstrip() + " | " + note).strip(" |")
            key = [row.get("date") or "", row.get("company") or "", row.get("role") or ""]
            if key not in apps:
                apps.append(key)
        csv_store.write_rows(tracker, rows, csv_store.header(tracker))
    reg["pause"] = {"until": end.isoformat(), "since": was.get("since") or today,
                    "contacts": held, "applications": apps,
                    "back_trigger": was.get("back_trigger") or ""}
    r = _brief(reg)
    if r is not None:
        _owe(reg, {"tool": "update_trigger", "for": "pause",
                   "args": {**_task_ref(r, reg), "enabled": False},
                   "why": f"the brief rests until {end.isoformat()}"})
        back = {"name": "Job search: welcome back",
                "run_once_at": _instant(end, (read_cron(r.get("cron")) or {}).get("time", ""),
                                        reg.get("timezone") or ""),
                "prompt": stub(reg, r["key"]), "connectors": [], "initiation": "human_request"}
        # The chat the brief runs in: a new one on firing has no copy of the files, so an
        # older ops brief comes back in the ops chat.
        sid = (r.get("chat") or {}).get("session_id") or (
            (reg.get("ops_session") or {}).get("id") if setup_of(reg) == "ops_relay" else "")
        if sid:
            back["persistent_session_id"] = sid
        else:
            back["create_new_session_on_fire"] = True
        _owe(reg, {"tool": "create_trigger", "for": "back", "args": back,
                   "why": "one brief on the day they come back, which turns the brief on again"})
    if path and os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    _save(reg, path)
    return {"until": end.isoformat(), "contacts": len(held), "applications": len(apps),
            "say": f"Your search is paused until {_short(end)}. Nothing is chased meanwhile.",
            "undo": {"action": "brief.resume"}, "calls": reg.get("owed") or []}


def _instant(day: datetime.date, hhmm: str, zone: str) -> str:
    """The brief's usual time on `day`, in its zone, as the RFC 3339 time in UTC that
    create_trigger's run_once_at takes; noon UTC when the zone or time is not known."""
    try:
        from zoneinfo import ZoneInfo
        h, m = (int(x) for x in hhmm.split(":"))
        at = datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=ZoneInfo(zone))
        at = at.astimezone(datetime.timezone.utc)
    except Exception:  # noqa: BLE001  no zone data, no time: noon UTC that day
        at = datetime.datetime(day.year, day.month, day.day, 12, 0, tzinfo=datetime.timezone.utc)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(day: datetime.date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def resume(today: str = "", path: str | None = None) -> dict:
    """The break is over, on its day or earlier: every hold the break wrote is taken off
    again (a next action someone changed since is left as they left it), the applications
    say "chase again", and the brief is turned back on."""
    import person
    import state
    import csv_store
    path = _path(path)
    today = today or datetime.date.today().isoformat()
    reg = load(path)
    p = reg.get("pause")
    if not p:
        return {"resumed": False, "say": "", "calls": reg.get("owed") or []}
    early = today < p.get("until", "")
    put_back = 0
    contacts_path = person.state("network_contacts.csv")
    if os.path.exists(contacts_path) and p.get("contacts"):
        contacts = state.load_contacts(contacts_path)
        threads_path = person.state("network_threads.csv")
        threads = state.load_threads(threads_path) if os.path.exists(threads_path) else []
        prefix = HOLD.format(until=p["until"], since=p["since"])
        for c in contacts:
            cid = c.get("contact_id") or ""
            if cid in p["contacts"] and str(c.get("next_action") or "").startswith(prefix):
                old = p["contacts"][cid]
                state.set_contact(contacts, threads, cid,
                                  next_action=old if old and old != "nothing set" else "")
                put_back += 1
        state.save_contacts(contacts, contacts_path)
    tracker = person.state("job_search_tracker.csv")
    if early and os.path.exists(tracker) and p.get("applications"):
        rows = csv_store.read_rows(tracker)
        keys = {tuple(k) for k in p["applications"]}
        for row in rows:
            if (row.get("date") or "", row.get("company") or "", row.get("role") or "") in keys:
                row["notes"] = ((row.get("notes") or "").rstrip() + " | "
                                + CHASE_AGAIN.format(today=today)).strip(" |")
        csv_store.write_rows(tracker, rows, csv_store.header(tracker))
    r = _brief(reg)
    reg["owed"] = [c for c in reg.get("owed") or [] if c.get("for") not in ("pause", "back")]
    if r is not None and not r.get("off"):
        _owe(reg, {"tool": "update_trigger", "for": "resume",
                   "args": {**_task_ref(r, reg), "enabled": True},
                   "why": "the brief comes again"})
        if early and p.get("back_trigger"):
            _owe(reg, {"tool": "delete_trigger", "for": "back-gone",
                       "args": {"trigger_id": p["back_trigger"]},
                       "why": "the welcome-back brief is not needed now"})
    reg.pop("pause", None)
    _save(reg, path)
    return {"resumed": True, "early": early, "contacts": put_back,
            "say": "Welcome back: your search is running again.",
            "undo": {"action": "brief.pause", "value": {"until": p["until"]}} if early else None,
            "calls": reg.get("owed") or []}


def paused(today: str = "", path: str | None = None) -> dict:
    """The break in force: {"until", "since"}, or {} when there is none."""
    try:
        p = load(_path(path)).get("pause") or {}
    except (OSError, ValueError):
        return {}
    return {"until": p.get("until", ""), "since": p.get("since", "")} if p else {}


def page_part(path: str | None = None) -> dict:
    """What the page shows of the brief (its bell, and Settings' "Your brief"), and the
    actions that change it: on or off, its days and time in words, a break in force, and how
    many changes still wait for a chat."""
    try:
        reg = load(_path(path))
    except Exception:  # noqa: BLE001  no profile or no registry: no brief yet
        reg = {}
    r = _brief(reg)
    got = read_cron((r or {}).get("cron") or "")
    p = reg.get("pause") or {}
    return {"set_up": r is not None, "off": bool((r or {}).get("off")),
            "when": got.get("when", ""), "days": got.get("days", []),
            "time": got.get("time", ""), "zone": got.get("zone") or reg.get("timezone", ""),
            "paused": {"until": p["until"], "since": p.get("since", "")} if p else None,
            "waiting": len(reg.get("owed") or []),
            "actions": {"move": "brief.move", "pause": "brief.pause", "resume": "brief.resume",
                        "off": "brief.off", "on": "brief.on"}}


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
    if not argv or argv[0] not in ("check", "stub", "brief", "default", "record", "move",
                                   "pause", "resume", "off", "on", "calls", "called",
                                   "upkeep-record", "upkeep-forget"):
        print(__doc__.split("\n\n")[1])
        return 2
    if argv[0] in ("move", "pause", "resume", "off", "on", "calls", "called"):
        return _schedule_cli(argv)
    if argv[0] == "upkeep-record":
        got = {argv[i][2:]: argv[i + 1] for i in range(1, len(argv) - 1, 2) if argv[i].startswith("--")}
        print(record_upkeep(got.get("session", ""), got.get("trigger", ""), got.get("cron", "")))
        return 0
    if argv[0] == "upkeep-forget":
        print(forget_upkeep())
        return 0
    if argv[0] == "brief":
        triggers, more, chat_arg = None, False, ""
        for i, a in enumerate(argv):
            if a == "--chat" and i + 1 < len(argv):
                chat_arg = argv[i + 1]
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
        import place
        if place.surface() == "local":
            # A chat on their computer never makes the brief: a task made here would run on
            # the computer, or start a new chat every morning. The bell on the page queues it
            # for the chat in the cloud that answers the page (tools/page_db.py runs a brief
            # only there), and starts that helper first where there is none.
            print("tell them: " + (place.BRIEF_LOCAL if found["state"] in ("registered", "found")
                                   else BRIEF_BELL))
        elif found["state"] == "none" and triggers is not None:
            # A cloud chat makes it itself, asking nothing: a task bound to this chat and a
            # first run in a few minutes (automation/README.md (a)). Never a chat of its own.
            owner, name = place.repo()
            got = plan(owner, name, chat=chat_arg)
            if not got["zone"]:
                print("zone: the profile names no time zone (networking.py TIMEZONE or "
                      "HOME_CITY): set it from where they live, then run this again")
                return 1
            if not got["chat"]:
                print("chat: this chat's id could not be read: get_session with no session_id "
                      "gives it; run this again with --chat <its id>. Never make a chat for it.")
                return 1
            print("make it now, asking nothing, with these calls in this order (it runs in "
                  "this chat, so no chat is made for it):")
            for call in ("create_trigger", "first_brief"):
                print(f"  create_trigger ({call}): {json.dumps(got[call], ensure_ascii=False)}")
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
        opt = {k: argv[argv.index(k) + 1] for k in ("--session", "--trigger", "--cron", "--setup",
                                                    "--title")
               if k in argv and argv.index(k) + 1 < len(argv)}
        if not opt.get("--trigger") or (opt.get("--setup", "chat_per_briefing") ==
                                        "chat_per_briefing" and not opt.get("--session")):
            print("usage: routines.py record --session <id> --trigger <id> [--cron \"<cron>\"] "
                  "[--setup routines_screen]", file=sys.stderr)
            return 2
        path = record(opt.get("--session", ""), opt["--trigger"], opt.get("--cron", ""),
                      setup=opt.get("--setup", "chat_per_briefing"),
                      title=opt.get("--title", ""), own_chat="--own-chat" in argv)
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


def _schedule_cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog=f"routines.py {argv[0]}")
    if argv[0] == "move":
        ap.add_argument("--days", default="")
        ap.add_argument("--time", default="")
        ap.add_argument("--cron", default="")
    elif argv[0] == "pause":
        ap.add_argument("--until", required=True)
    elif argv[0] == "called":
        ap.add_argument("n", type=int)
        ap.add_argument("--id", default="", help="the new task's id, for a one-off brief")
    ap.add_argument("--today", default="")
    a = ap.parse_args(argv[1:])
    try:
        if argv[0] == "calls":
            print(json.dumps(calls(), ensure_ascii=False, indent=1))
            return 0
        if argv[0] == "called":
            hit = called(a.n, a.id)
            print(f"routines.json: call {a.n} ({hit.get('tool')}) made; "
                  f"{len(calls())} still owed")
            return 0
        got = (move(a.days or None, a.time or None, a.cron) if argv[0] == "move" else
               pause(a.until, a.today) if argv[0] == "pause" else
               off() if argv[0] == "off" else on() if argv[0] == "on" else resume(a.today))
    except (ValueError, KeyError, OSError) as e:
        print(f"routines.py {argv[0]}: nothing changed: {e}")
        return 1
    print(f"tell them: {got['say']}" if got.get("say") else "routines.py: no break to end")
    for c in got.get("calls") or []:
        print(f"call {c['n']}: {c['tool']} {json.dumps(c['args'], ensure_ascii=False)} "
              f"({c['why']}); then python3 tools/routines.py called {c['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
