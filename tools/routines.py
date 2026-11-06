#!/usr/bin/env python3
"""The scheduled-task registry (profile/routines.json): check it, and print each
task's prompt.

A scheduled task's stored prompt is a short stub that reads its instructions
from master. A wrong path, a cron with no time zone or a pasted id with a typo
fails at seven in the morning with nobody watching, so this checks the registry
whenever ci_local.sh runs, and the app's tests check the example's.

    python3 tools/routines.py check [path]   # exit 0 clean, 1 with every problem listed
    python3 tools/routines.py stub <key>     # the exact prompt to store for that task
    python3 tools/routines.py brief [--triggers <listing.json>]... [--chat <id>] [--page-chat <id>]
                                             # is there a brief already? never make a second;
                                             # in a cloud chat, the calls that make one; one
                                             # firing in a chat that handed the page on is moved
                                             # to the chat that answers it (--page-chat, else
                                             # the one this copy last saw)
    python3 tools/routines.py default        # the brief's days, time and zone, and the line
    python3 tools/routines.py record --session <id> --trigger <id> [--cron "<cron>"] [--asked HH:MM] [--own-chat]
                                             # write the brief made into profile/routines.json
    python3 tools/routines.py move --days weekdays --time 08:00
                                             # the brief's new days and time, written here,
                                             # the time kept to the minute
    python3 tools/routines.py pause --until <YYYY-MM-DD> | resume
                                             # a break: the brief and every follow-up held
    python3 tools/routines.py off | on       # the brief alone turned off, or on again
    python3 tools/routines.py calls | called <n> [--id <trig_...>]
                                             # the scheduled-task calls a chat still owes
    python3 tools/routines.py remind | reminded --trigger <id>
                                             # the one setup reminder, while setup waits
    python3 tools/routines.py mended         # every task's prompt now gets its files

Code cannot change a scheduled task: only a chat can (update_trigger, create_trigger). So
`move`, `pause`, `resume`, `off` and `on` write the registry and the state files, and keep
the calls a chat owes in the registry (`owed`) until `called` says each was made. The page
queues the change (its actions brief.move, brief.pause, brief.resume, brief.off, brief.on);
the chat that applies them, or the next one that starts, makes the calls. `calls` first
mends what code can (heal: a break whose day passed, a zone this computer does not know, a
brief that did not come). Setup turns the brief on, every day at 7:38 their time unless they
choose other days (the app's own default, moved off 8:00 and said so); the bell on their
Brief, or Settings, changes it or turns it off, and a time picked there is kept to the minute.
The page shows when it really comes (real_time): the scheduler's late start where a listing
reports one (saw), and why, in one line.

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
        # A Routines-screen task that reports to the person notifies by itself (the brief run
        # then sends no push of its own: brief_pushes_itself). The silent daily upkeep reports
        # to nobody and needs none: requiring it turned the local check red for good once the
        # upkeep was made, and nothing was saved again (X-33).
        if setup == "routines_screen" and r.get("key") != UPKEEP_KEY \
                and r.get("notifications", {}).get("push") is not True:
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
                    "next_run_at": t.get("next_run_at") or "",
                    "session": t.get("persistent_session_id") or ""})
    return out, more


def _is_brief_prompt(prompt: str) -> bool:
    if str(prompt or "").startswith(REMIND_STUB_HEAD):
        return False                      # the one setup reminder, never a brief
    return BRIEF_FILE in (prompt or "") or "Scheduled run: morning brief" in (prompt or "")


def _is_app_prompt(prompt: str) -> bool:
    """A stored prompt the app made: its stub, naming a prompt file under automation/prompts."""
    p = str(prompt or "")
    return p.startswith("Scheduled run:") and "automation/prompts/" in p


def mend(triggers, repo: str) -> list[dict]:
    """The update_trigger calls that give each of the app's tasks that is on the line that
    gets the copy where its chat has none (the brief, the job round, a welcome-back brief):
    a task whose chat was deleted wakes a new, empty one, and without the line every run
    replied "could not read the file" there (X-43). Any chat can make these, not only the one
    that answers the page."""
    out = []
    for t in triggers or []:
        prompt = str(t.get("prompt") or "")
        fixed = with_copy(prompt, repo)
        if t.get("id") and t.get("enabled") is not False and _is_app_prompt(prompt) \
                and fixed != prompt:
            out.append({"tool": "update_trigger", "args": {"trigger_id": t["id"], "prompt": fixed},
                        "why": f"{t.get('name') or 'a scheduled task'} gets its files in any chat "
                               "it lands in"})
    return out


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


def _at(stamp) -> datetime.datetime | None:
    try:
        got = datetime.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=datetime.timezone.utc)


def no_copy(reg: dict, r: dict, live: dict | None, now: datetime.datetime | None = None,
            days_on_file=None, here: str = "") -> str:
    """The day of a brief that ran in a chat without the person's files, or "": that day's
    brief did not come (`overdue`), and its task fired at or after its time, or now wakes (or
    last ran in) another chat than the one it was bound to. Its chat had been made again
    empty, so the run could only say it could not read the files, wrote no record and sent
    nothing, while `brief` said it was set up (the maintainer, 2026-11-04). Never for this
    chat itself, which has the files."""
    if not live or live.get("enabled") is False:
        return ""
    day = overdue(reg, now, days_on_file)
    got = read_cron(r.get("cron") or "")
    if not day or not got or not zone_ok(got.get("zone", "")):
        return ""
    bound = str((r.get("chat") or {}).get("session_id") or "")
    run = live.get("last_run") or {}
    woke = str(live.get("session") or "")
    ran_in = str(run.get("session_id") or "")
    if here and here in (woke or bound, ran_in):
        return ""
    if bound and any(s and s != bound for s in (woke, ran_in)):
        return day
    import zoneinfo
    d = datetime.date.fromisoformat(day)
    h, m = (int(x) for x in got["time"].split(":"))
    due = datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=zoneinfo.ZoneInfo(got["zone"]))
    fired = _at(run.get("fired_at"))
    return day if fired is not None and fired >= due - datetime.timedelta(minutes=5) else ""


def move_here(reg: dict, r: dict, live: dict, day: str, here: str, repo: str,
              today: datetime.date | None = None) -> dict:
    """The calls that move a brief whose chat cannot open the copy into `here` (the chat that
    answers the page), in order, as tidy.py moves one whose chat is gone: the new task first,
    so a refusal leaves the old one running; the registry; then the old task turned off,
    never deleted. Then that day's brief runs here, as the helper did by hand (2026-11-04)."""
    calls = move_calls(reg, r, live, here, repo)
    d = datetime.date.fromisoformat(day)
    when = "this morning" if d == (today or person_today()) else "on " + _short(d)
    return {"calls": calls,
            "then": "then run the brief that did not come, here and now: follow "
                    "automation/prompts/_common.md and automation/prompts/morning_brief.md as "
                    "its scheduled run would",
            "tell": f"Your brief didn't come {when}: the chat it ran in had lost your files. "
                    "It comes from this chat from now on."}


def handed_over(reg: dict, chat: str) -> bool:
    """Has `chat`, a brief's task fires in it while another chat answers the page, handed the
    page on? Every chat the app bound a brief to answered the page when it did (`plan` binds
    it there), except the older ops chat, which relays to the phone and keeps its brief."""
    ops = str((reg.get("ops_session") or {}).get("id") or "")
    return bool(chat) and not (ops and chat == ops)


def move_calls(reg: dict, r: dict, live: dict, here: str, repo: str) -> list[dict]:
    """The calls that move a brief's task into `here`, in order: the new task first, so a
    refusal leaves the old one running; the registry; then the old task turned off, never
    deleted."""
    cron = r.get("cron") or ""
    prompt = with_copy(stub(reg, r.get("key") or "morning_brief", own_chat=True), repo)
    return [
        {"tool": "create_trigger", "args": {
            "name": r.get("name") or BRIEF_NAME, "persistent_session_id": here,
            "cron_expression": cron, "prompt": prompt,
            "initiation": "own_followup"},
         "why": "the brief runs in this chat, which has the files, from now on"},
        {"run": f"python3 tools/routines.py record --session {here} --trigger <the new task's "
                f"id> --cron \"{cron}\"" + (" --own-chat" if setup_of(reg) == "ops_relay" else ""),
         "why": "the registry names the new task and its chat"},
        {"tool": "update_trigger", "args": {"trigger_id": live.get("id") or r.get("trigger_id"),
                                            "enabled": False},
         "why": "the old task is turned off, never deleted"}]


def person_today() -> datetime.date:
    try:
        import person
        return person.today()
    except Exception:  # noqa: BLE001  no profile: the machine's day
        return datetime.date.today()


def existing_brief(reg: dict | None, triggers=None, now: datetime.datetime | None = None,
                   days_on_file=None, here: str = "", repo: str | None = None,
                   page: str = "") -> dict:
    """Whether a brief already exists, found by the registry or by a task's own prompt.

    Never by its title: a person's brief may be called "Job search: brief (Mon and
    Thu)" or anything else, and a second brief is two messages every morning.
    `triggers` is the account's scheduled tasks as `listing` gives them, or None when the
    session cannot list them. An empty listing is a listing: a registry entry missing from
    it is asked about, never read as set up. A registered brief whose chat cannot open the
    copy (`no_copy`) is "lost", with the calls that move it into `here`. One whose task
    fires in a chat that has handed the page on, while `page` answers it now, is
    "elsewhere", with the calls that move it into `page`.
    Returns {"state": "registered" | "lost" | "elsewhere" | "found" | "ask" | "none", "id",
    "name", "say"}.
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
        lost = no_copy(reg, r, live, now, days_on_file, here) if live else ""
        if lost:
            what = (f"the brief {r.get('name')!r} ({live.get('id')}) ran in a chat that cannot "
                    f"open the person's files: the brief due {lost} left no record. ")
            if not here:
                return {"state": "lost", "id": live.get("id", ""), "name": r.get("name", ""),
                        "calls": [], "say": what + "Move it into this chat: this chat's id "
                        "could not be read; get_session with no session_id gives it, then run "
                        "this again with --chat <its id>"}
            got = move_here(reg, r, live, lost, here, _repo() if repo is None else repo,
                            today=now.date() if now else None)
            return dict(got, state="lost", id=live.get("id", ""), name=r.get("name", ""),
                        say=what + "Move it into this chat, with the calls below, in order, "
                        "stopping at the first that fails.")
        # Where its task fires, by the listing: "set up" said over a brief still bound to a
        # chat that had handed the page on, so the helper took it as moved (the maintainer's
        # copy, 2026-11-05). `page` is the chat that answers the page now.
        woke = str((live or {}).get("session") or "")
        if live and live.get("enabled") is not False and page and woke and woke != page \
                and r.get("cron") and handed_over(reg or {}, woke):
            return {"state": "elsewhere", "id": live.get("id", ""), "name": r.get("name", ""),
                    "calls": move_calls(reg or {}, r, live, page,
                                        _repo() if repo is None else repo),
                    "then": "it has moved only once a new list_triggers shows its task firing "
                            f"in {page}: never say it moved before",
                    "tell": "",
                    "say": f"the brief {r.get('name')!r} ({live.get('id')}) still fires in "
                           f"{woke}, a chat that has handed the page on, not in the chat that "
                           f"answers the page ({page}): it has not moved. Move it there with "
                           "the calls below, in order, stopping at the first that fails"}
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
# The same, with no page and so no bell (X-37): the page comes first, made by this chat.
BRIEF_NO_PAGE_LOCAL = ("make their page first: python3 tools/app.py start, and do what it prints "
                       "(it publishes the page); then tell them: " + BRIEF_BELL)
# The one reminder made when the page goes up and setup is not finished: nothing else is
# scheduled before setup's last step, and a stranger who answered nothing that first sitting
# was never contacted again (X-23).
REMIND_NAME = "Job search: setup reminder"
REMIND_STUB_HEAD = "Scheduled run: setup reminder."
REMIND_HOURS = 24
# The scheduler's own slow window: "Runs that start between 6 AM and 9 AM Pacific time ...
# can be delayed. If the user named no time, choose one outside those hours" (create_trigger).
SLOW_ZONE, SLOW_FROM, SLOW_TO = "America/Los_Angeles", 6, 9
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


def _back(name: str = BRIEF_NAME) -> int:
    """How many minutes before the hour Claude's scheduling guidance moves a task called
    `name`: the letters in its name, mod 29, plus 1 (create_trigger). 22 for the brief."""
    return sum(c.isalpha() for c in name) % 29 + 1


def brief_minute(name: str = BRIEF_NAME, hour: int = 8) -> tuple[int, int]:
    """(hour, minute) for the app's own default brief meant for `hour` o'clock: moved off the
    hour by Claude's scheduling guidance (letters in the task's name, mod 29, plus 1, minutes
    earlier), because a run set on the hour can start several minutes late (code.claude.com
    docs/en/routines, "Runs on the hour"). 8:00 is 7:38. Only the app's default is moved: a
    time the person picks is kept to the minute (cron_for), and the page says why a moved
    one comes when it does (real_time)."""
    return (hour - 1, 60 - _back(name))


def home_zone() -> str:
    """The person's own zone, where the profile says it (networking.py TIMEZONE or
    HOME_CITY); "" when it does not."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        import reading
        return reading.home_zone() or ""
    except Exception:  # no profile yet, or a profile without the setting
        return ""


def zone_ok(zone: str) -> bool:
    """A time zone this computer knows by name. "EST/EDT" has the shape of one and is not:
    a brief made in it is refused or runs at the wrong hour (X-66)."""
    if not TIMEZONE.fullmatch(str(zone or "")):
        return False
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(zone)
        return True
    except Exception:  # noqa: BLE001  unknown here, or no zone data at all
        return False


def city_of(zone: str) -> str:
    """"New York" for America/New_York: how the person says their own clock."""
    return str(zone or "").rsplit("/", 1)[-1].replace("_", " ")


def _slow(zone: str, h: int, m: int) -> bool:
    """Does h:m in `zone` start inside the scheduler's slow window (6 to 9 AM Pacific), in
    winter or in summer?"""
    try:
        import zoneinfo
        here, there = zoneinfo.ZoneInfo(zone), zoneinfo.ZoneInfo(SLOW_ZONE)
    except Exception:  # noqa: BLE001
        return False
    year = datetime.date.today().year
    for month in (1, 7):
        t = datetime.datetime(year, month, 15, h, m, tzinfo=here).astimezone(there)
        if SLOW_FROM <= t.hour < SLOW_TO:
            return True
    return False


def has_page() -> bool:
    """Does the person have a page (profile/app.json `url`)? Without one there is no Brief
    and no bell, and everything said about the brief names the chat instead (X-11)."""
    try:
        import person
        with open(person.path("app.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except Exception:  # noqa: BLE001  no profile, no page record
        return False
    return isinstance(got, dict) and str(got.get("url") or "").startswith("https://claude.ai/")


def default(zone: str = "", days=BRIEF_DAYS, hour: int = 8, page: bool | None = None) -> dict:
    """The brief as it is first made, with no questions: every day at 7:38 their time, or
    5:38 where 7:38 falls in the scheduler's slow window (US Pacific and Mountain, X-69). Its
    line says where it comes and in whose time: the page's Brief, or with no page this chat,
    which the person can change by saying so (X-11, X-1), and why it is not 8:00, since the
    app moved it (the maintainer, 2026-11-06: "the app turns 8:00 into 7:38 without saying
    so"). `asked` is the time it stands for, recorded beside the one set (record)."""
    zone = zone or home_zone()
    if zone and not zone_ok(zone):
        zone = ""
    h, m = brief_minute(hour=hour)
    if zone and _slow(zone, h, m):
        h = next((x for x in (h - 2, h + 2) if not _slow(zone, x, m)), h)
    named = day_words(days)
    page = has_page() if page is None else page
    asked = f"{hour:02d}:00"
    why = "It comes " + moved_why(asked, f"{h:02d}:{m:02d}") + "."
    at = f"{in_sentence(named)} at {h}:{m:02d}" + (f", {city_of(zone)} time" if zone else "")
    say = (f"Your brief is on: {at}, on your page's Brief. {why} Change it or turn it off "
           f"from the bell there." if page else
           f"Your morning brief comes to this chat {at}. {why} Say \"move my brief\" or \"stop "
           f"my brief\" in any chat to change it.")
    return {"zone": zone, "cron": f"CRON_TZ={zone} {m} {h} * * {_cron_days(days)}" if zone else "",
            "when": f"{named} at {h}:{m:02d}", "say": say, "asked": asked}


def _page_chat() -> str:
    """The chat that answers the page, as this checkout last saw it, or ""."""
    try:
        import app_listen
        got = str((app_listen.seen().get("listener") or {}).get("chat") or "")
    except Exception:  # noqa: BLE001  no record here
        return ""
    return got if got.startswith("session_") else ""


def plan(owner: str, name: str, zone: str = "", now: datetime.datetime | None = None,
         chat: str = "", initiation: str = "human_request") -> dict:
    """The exact calls a cloud chat makes to set the brief up with no questions: a task
    bound to the chat that answers the page where there is one, else this chat (`chat`
    overrides both), so the brief starts no chat of its own and never lands in whichever chat
    a background upgrade happened to run in (X-11), and one first run a few minutes on (never
    fire_trigger, which starts a new chat with no copy in it). No chat is ever made for it:
    where this chat's id cannot be read, `chat` is empty and the caller asks get_session for
    it first. `initiation` is own_initiative where nobody asked (the brief-daily upgrade)."""
    d = default(zone)
    stub_text = with_copy(DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                              prompt_file=BRIEF_FILE, relay_id=""),
                          f"{owner}/{name}" if owner and name else "")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    first = (now + datetime.timedelta(minutes=5)).replace(microsecond=0)
    if not chat and has_page():
        chat = _page_chat()
    if not chat:
        import app_listen
        chat = app_listen.this_chat()
    chat = chat if str(chat).startswith("session_") else ""
    sid = chat or "<the session id>"
    out = {
        "create_trigger": {"name": BRIEF_NAME, "persistent_session_id": sid,
                           "cron_expression": d["cron"], "prompt": stub_text,
                           "initiation": initiation},
        "first_brief": {"name": "Job search: first brief", "persistent_session_id": sid,
                        "run_once_at": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "prompt": stub_text, "initiation": initiation},
        "record": (f"python3 tools/routines.py record --session {sid} --trigger "
                   f"<the task's id> --cron \"{d['cron']}\" --asked {d['asked']}"),
        "say": d["say"], "zone": d["zone"], "chat": chat}
    return out


def where_line(reg: dict) -> str:
    """Where the brief comes, when, and how to change it, in one plain line, or "" with no
    brief on. Never a promise of a push: the reply is the record."""
    r = _brief(reg)
    if not r or r.get("off") or reg.get("pause"):
        return ""
    got = read_cron(r.get("cron") or "")
    if not got.get("when"):
        return ""
    real = real_time(r)
    got["when"] = real.get("when") or got["when"]
    zone = got.get("zone", "")
    city = f", {city_of(zone)} time" if zone_ok(zone) else ""
    page = has_page()
    where = ("as a new chat each time" if setup_of(reg) == "routines_screen" else "to this chat")
    where += " and to your page's Brief" if page else ""
    change = ("Change it from the bell on your Brief." if page else
              "Say \"move my brief\" or \"stop my brief\" in any chat to change it.")
    why = (" " + real["said"]) if real.get("said") else ""
    return f"Your brief comes {where} {in_sentence(got['when'])}{city}.{why} {change}"


def where_once(write: bool = False, path: str | None = None) -> str:
    """where_line, once: the first brief after this update says where it comes (a brief made
    before was posted into a chat nobody reopened, and nothing said so: X-1). Recorded with
    `write`, so it is never said again."""
    path = _path(path)
    try:
        reg = load(path)
    except (OSError, ValueError):
        return ""
    if reg.get("told_where"):
        return ""
    line = where_line(reg)
    if line and write:
        reg["told_where"] = datetime.date.today().isoformat()
        _save(reg, path)
    return line


def remind_plan(owner: str, name: str, chat: str = "",
                now: datetime.datetime | None = None) -> dict:
    """The one setup reminder: a run a day from now, bound to this chat, whose brief says only
    that setup waits on the page and sends that line as a push (tools/brief.py). Made when the
    page first goes up with setup unfinished; never a second (`remind_due`)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    at = (now + datetime.timedelta(hours=REMIND_HOURS)).replace(microsecond=0)
    if not chat:
        import app_listen
        chat = app_listen.this_chat()
    chat = chat if str(chat).startswith("session_") else ""
    prompt = with_copy(DEFAULT_STUB.format(label="setup reminder", Label="Setup reminder",
                                           prompt_file=BRIEF_FILE, relay_id=""),
                       f"{owner}/{name}" if owner and name else "")
    return {"create_trigger": {"name": REMIND_NAME, "persistent_session_id": chat or
                               "<the session id>", "run_once_at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "prompt": prompt, "initiation": "own_initiative"},
            "record": "python3 tools/routines.py reminded --trigger <the task's id>",
            "chat": chat}


def remind_due(path: str | None = None) -> bool:
    """Is the setup reminder still to make: a page, setup not finished, and neither a brief
    nor a reminder on file?"""
    try:
        import app_setup
        if not has_page() or app_setup._finished():
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        reg = load(_path(path))
    except Exception:  # noqa: BLE001  no registry yet: nothing made
        reg = {}
    return not reg.get("reminder") and _brief(reg) is None


def reminded(trigger: str, path: str | None = None) -> str:
    path = _path(path)
    try:
        reg = load(path)
    except (OSError, ValueError):
        reg = {}
    reg["reminder"] = {"trigger_id": trigger, "made": datetime.date.today().isoformat()}
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    return _save(reg, path)


def record(session: str, trigger: str, cron: str = "", path: str | None = None,
           setup: str = "chat_per_briefing", title: str = "", own_chat: bool = False,
           asked: str = "") -> str:
    """Write the brief just made into profile/routines.json, keeping every other task. The
    chat it runs in is named only when it was made for it; bound to the chat that answers
    the page, it is that chat's id alone. In the older ops set-up it is named only with
    `own_chat` (the brief moved out of a lost ops chat): a chat recording a re-listed id
    names itself, and a `chat` there would stop the relay to the phone. `asked` is the time
    the app's default stood for ("08:00" for 7:38, plan() passes it), kept beside the cron so
    the page says why it comes when it does; a brief moved to another chat on the same
    schedule keeps what was asked before."""
    if path is None:
        import person
        path = person.path("routines.json")
    try:
        reg = load(path)
    except (OSError, ValueError):
        reg = {}
    reg.pop("_about", None) if reg.get("_about", "").startswith("The example person's") else None
    if not cron:
        d = default()
        cron, asked = d["cron"], asked or d["asked"]
    m = re.match(r"CRON_TZ=(\S+) ", cron)
    if m and not zone_ok(m.group(1)):
        raise ValueError(f"{m.group(1)!r} is not a time zone this computer knows; make the task "
                         f"again in the zone routines.py default names")
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
    if re.fullmatch(r"\d{1,2}:\d{2}", asked or ""):
        h, m = _clock(asked)
        entry["asked"] = {"time": f"{h:02d}:{m:02d}", "by": "app"}
    elif isinstance(was.get("asked"), dict) and was.get("cron") == cron:
        entry["asked"] = was["asked"]
    # The day it was made, so a brief due before it existed is never read as one that did not
    # come (overdue); and its prompt is the stub with the line that gets the copy (plan()).
    entry["made"] = was.get("made") or datetime.date.today().isoformat()
    entry["copy"] = True
    reg["told_where"] = reg.get("told_where") or entry["made"]   # its maker said where it comes
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
    """Is the brief on, with a task, every day of the week? Then it keeps things current. A
    Routines-screen task may carry no id (the README says it is optional): its cron is read
    all the same, or the upkeep was made beside a daily routine (X-33)."""
    r = _brief(reg)
    if not r or r.get("off") or not (r.get("trigger_id") or setup_of(reg) == "routines_screen"):
        return False
    return read_cron(r.get("cron") or "").get("days") == list(range(7))


def needs_upkeep(reg: dict) -> bool:
    return not brief_every_day(reg)


def upkeep_cron(reg: dict) -> str:
    """Once a day, before the person is up: 5-something in their zone, off the hour, and only
    on the days the brief does not run, since a brief does the same (X-38)."""
    zone = reg.get("timezone") or home_zone()
    if not zone:
        return ""
    h, m = brief_minute(UPKEEP_NAME, hour=6)
    r = _brief(reg)
    on = set(read_cron((r or {}).get("cron") or "").get("days") or []) \
        if r and not r.get("off") else set()
    rest = [d for d in range(7) if d not in on]
    return f"CRON_TZ={zone} {m} {h} * * {_cron_days(rest or range(7))}"


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


def rebind(key: str, session: str, trigger: str, path: str | None = None) -> str:
    """A task other than the brief (the job round) made again in another chat: its entry names
    the new task and chat, and keeps its days, time and prompt file (tools/tidy.py)."""
    path = _path(path)
    reg = load(path)
    r = next((x for x in reg.get("routines") or [] if x.get("key") == key), None)
    if r is None:
        raise ValueError(f"no task {key!r} in the registry")
    r["trigger_id"] = trigger
    r["chat"] = {"session_id": session}
    r["copy"] = True
    return _save(reg, path)


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
    """The cron for the brief on these days at exactly this time, in their zone, and the words
    for it. A time the person picks is kept to the minute, on the hour too: the app moved 8:00
    to 7:38 without saying so, and the person's choice wins over the scheduling guidance
    (the maintainer, 2026-11-06). Only the app's own default is moved (brief_minute)."""
    d = _days(days)
    if not d:
        raise ValueError("name at least one day")
    h, m = _clock(time)
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


def _hm(hhmm: str) -> tuple[int, int]:
    h, m = str(hhmm).split(":")
    return int(h), int(m)


def _say_time(hhmm: str) -> str:
    """"07:38" as a person says it: "7:38"."""
    h, m = _hm(hhmm)
    return f"{h}:{m:02d}"


def moved_why(asked: str, set_at: str) -> str:
    """Why the app set `set_at` for a brief asked for at `asked` ("HH:MM"), as the end of a
    sentence: a few minutes before the hour or half hour, or hours earlier, out of the
    scheduler's slow morning window, or hours later where both earlier times fall in it
    (Alaska: 9:38)."""
    ah, am = _hm(asked)
    sh, sm = _hm(set_at)
    gap = (ah * 60 + am) - (sh * 60 + sm)       # signed: the brief's times stay within one day
    if gap >= 60 or gap < 0:
        return (f"{'earlier' if gap > 0 else 'later'} than {_say_time(asked)}, outside the "
                "hours when the service often starts late")
    return ("a few minutes before the " + ("half hour" if am == 30 else "hour")
            + ", when the service is less busy")


def asked_of(r: dict | None) -> dict:
    """What the brief's time was asked for, {time, by}: "person" for a time picked on the page
    or in a chat, kept to the minute; "app" for the app's own default, moved off the hour.
    Recorded beside the cron (`asked`); a copy made before it was recorded is read from the
    minute itself, since only the app's rule ever set :38 or :08 (8:00 and 8:30 moved 22
    minutes earlier). {} where nothing is known."""
    r = r or {}
    got = r.get("asked")
    if isinstance(got, dict) and re.fullmatch(r"\d{2}:\d{2}", str(got.get("time") or "")):
        return {"time": got["time"], "by": "app" if got.get("by") == "app" else "person"}
    sched = read_cron(r.get("cron") or "")
    if not sched:
        return {}
    h, m = _hm(sched["time"])
    if m == 60 - _back():
        return {"time": f"{(h + 1) % 24:02d}:00", "by": "app"}
    if m == 30 - _back():
        return {"time": f"{h:02d}:30", "by": "app"}
    return {}


def _late(stamp, zone: str, hhmm: str) -> int:
    """How many minutes after `hhmm` in `zone` the instant `stamp` falls, where that is 2 to
    59 (the scheduler's own late start); else 0."""
    at = _at(stamp)
    if at is None or not zone_ok(zone):
        return 0
    import zoneinfo
    local = at.astimezone(zoneinfo.ZoneInfo(zone))
    h, m = _hm(hhmm)
    gap = ((local.hour * 60 + local.minute) - (h * 60 + m)) % 1440
    return gap if 2 <= gap < 60 else 0


def real_time(r: dict | None, zone: str = "") -> dict:
    """When the brief really comes: {set, time, when, why, said}. `set` is the stored schedule's own
    time; `time` is that, or later where the scheduler reports it starts the run late (its
    next_run_at, or the time the last run fired, as `saw` recorded them against this same
    schedule; the docs: "if you schedule a run exactly on the hour, such as 9:00, it can start
    several minutes late", code.claude.com/docs/en/routines). `why` is one plain line where the
    time is not the one asked for: the scheduler's delay, or the app's own move off the hour;
    "" where it is the time the person picked. `said` is the same reason as a sentence of its
    own, for a line that has already named the time."""
    r = r or {}
    sched = read_cron(r.get("cron") or "")
    if not sched:
        return {}
    zone = sched.get("zone") or zone
    out = {"set": sched["time"], "time": sched["time"], "when": sched["when"], "why": "",
           "said": ""}
    seen = r.get("seen") or {}
    late = 0
    if isinstance(seen, dict) and seen.get("cron") == r.get("cron"):
        late = max(_late(seen.get("next_run_at"), zone, sched["time"]),
                   _late(seen.get("fired_at"), zone, sched["time"]))
    if late:
        h, m = _hm(sched["time"])
        t = (h * 60 + m + late) % 1440
        out["time"] = f"{t // 60:02d}:{t % 60:02d}"
        out["when"] = (day_words(sched["days"]) if sched["days"] else "") + \
            f" at {_say_time(out['time'])}"
        out["said"] = (f"The service starts it a few minutes after {_say_time(sched['time'])}, "
                       "the time it is set for.")
        out["why"] = f"Comes at about {_say_time(out['time'])}: t" + out["said"][1:]
        if m == 0:
            out["why"] += " A time a few minutes past the hour starts on time."
        return out
    asked = asked_of(r)
    if asked.get("by") == "app" and asked["time"] != sched["time"]:
        why = moved_why(asked["time"], sched["time"])
        out["why"] = f"Comes at {_say_time(sched['time'])}: {why}."
        out["said"] = f"It comes {why}."
    return out


def saw(triggers, path: str | None = None) -> bool:
    """Keep what the scheduler reports of the brief's task (its next_run_at and the time its
    last run fired, from a list_triggers listing as `listing` gives it) beside the schedule it
    was seen against, so the page shows the time the brief really comes (real_time). True when
    the registry changed."""
    path = _path(path)
    try:
        reg = load(path)
    except (OSError, ValueError):
        return False
    r = _brief(reg)
    if not r:
        return False
    live = next((t for t in triggers or [] if r.get("trigger_id") and t.get("id") == r["trigger_id"]),
                None)
    if live is None:
        return False
    run = live.get("last_run") or {}
    got = {"cron": r.get("cron") or "",
           **({"next_run_at": live["next_run_at"]} if live.get("next_run_at") else {}),
           **({"fired_at": run["fired_at"]} if run.get("fired_at") else {})}
    if len(got) == 1:
        return False
    old = r.get("seen") or {}
    if old.get("cron") == got["cron"]:
        got = {**{k: v for k, v in old.items() if k in ("next_run_at", "fired_at")}, **got}
    if got == old:
        return False
    r["seen"] = got
    _save(reg, path)
    return True


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


def brief_pushes_itself(reg: dict) -> bool:
    """Does the brief reach the person's phone without the run sending a push itself? A
    Routines-screen task does (notifications on, which `check` requires), and so does an
    older ops-chat brief with no chat of its own (the relay pushes). A brief bound to a chat
    does not: create_trigger's notifications apply only to a task that starts a new chat on
    each run, so the run sends its own (claude_surfaces: chat-push). A chat-only person's
    brief posted into a chat nobody was looking at for days (2026-11-03)."""
    setup = setup_of(reg)
    if setup == "routines_screen":
        return True
    brief = _brief(reg) or {}
    return setup == "ops_relay" and not brief.get("chat")


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


def calls(path: str | None = None, mend_first: bool = True, today: str = "") -> list[dict]:
    """The scheduled-task calls a chat still owes, oldest first; [] with no registry. Every
    chat that asks (a start, a wake, the brief) first has heal() mend what code can see is
    wrong, so what it owes is here to make."""
    if mend_first:
        try:
            heal(path, today=today)
        except Exception:  # noqa: BLE001  a registry that cannot be mended is read as it is
            pass
    try:
        return list(load(_path(path)).get("owed") or [])
    except (OSError, ValueError):
        return []


def _repo() -> str:
    try:
        import place
        owner, name = place.repo()
        return f"{owner}/{name}" if owner and name else ""
    except Exception:  # noqa: BLE001
        return ""


LATE_GRACE_H = 2        # a run may start late; past this, the brief has not come


def _brief_days_on_file() -> set[str]:
    try:
        import person
        folder = person.state("documents", "briefs")
        return {f[:10] for f in os.listdir(folder) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", f)}
    except Exception:  # noqa: BLE001  no folder yet
        return set()


def overdue(reg: dict, now: datetime.datetime | None = None, days_on_file=None) -> str:
    """The day (YYYY-MM-DD) of the latest brief that was due and did not come, or "": its
    time on one of its days passed more than LATE_GRACE_H hours ago, in its own zone, and no
    record of that day or a later one is in documents/briefs/. Never for a brief that is off,
    resting, made after that day, or with no record at all and no day it was made (an older
    registry: nothing to measure from). The brief's silence was the only alarm, and a person
    who never got a push did not know one was expected (X-10)."""
    r = _brief(reg)
    if not r or r.get("off") or reg.get("pause"):
        return ""
    got = read_cron(r.get("cron") or "")
    if not got or not got.get("days") or not zone_ok(got.get("zone", "")):
        return ""
    import zoneinfo
    tz = zoneinfo.ZoneInfo(got["zone"])
    now = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    h, m = (int(x) for x in got["time"].split(":"))
    have = _brief_days_on_file() if days_on_file is None else set(days_on_file)
    made = str(r.get("made") or "")
    if not made and not have:
        return ""
    for back in range(8):
        day = now.date() - datetime.timedelta(days=back)
        if (day.isoweekday() % 7) not in got["days"]:
            continue
        due = datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
        if now < due + datetime.timedelta(hours=LATE_GRACE_H):
            continue
        iso = day.isoformat()
        if (made and iso <= made) or iso <= str(reg.get("back_on") or "") \
                or any(d >= iso for d in have):
            return ""
        return iso
    return ""


def late_line(day: str, today: datetime.date | None = None) -> str:
    """The plain line the page and a chat say for a brief that did not come."""
    try:
        d = datetime.date.fromisoformat(day)
    except ValueError:
        return ""
    when = "this morning" if d == (today or datetime.date.today()) else f"on {_short(d)}"
    return f"Your brief didn't come {when}. Claude is looking into it."


def heal(path: str | None = None, today: str = "", now: datetime.datetime | None = None) -> list[str]:
    """What code can mend in the registry by itself, at any start, wake or brief, with the
    scheduled-task calls each needs kept owed for the chat: a break whose day has passed is
    lifted (a welcome-back run that failed left the brief off for good while the page showed it
    on, X-9); a time zone this computer does not know is rewritten to the person's own (X-66);
    and a brief that did not come owes one look at the scheduled tasks, once for that day
    (X-10). Returns plain lines for the person, one per change."""
    path = _path(path)
    try:
        reg = load(path)
    except (OSError, ValueError):
        return []
    if today and now is None:
        d = datetime.date.fromisoformat(today)
        now = datetime.datetime(d.year, d.month, d.day, 12, tzinfo=datetime.timezone.utc)
    today = today or datetime.date.today().isoformat()
    said = []
    p = reg.get("pause") or {}
    if p.get("until") and p["until"] <= today:
        got = resume(today, path)
        if got.get("resumed"):
            said.append("Your break ended on %s, and your brief is on again." % _short(
                datetime.date.fromisoformat(p["until"])))
        reg = load(path)
    tz = reg.get("timezone") or ""
    if tz and _brief(reg) is not None and not zone_ok(tz):
        home = home_zone()
        if zone_ok(home):
            try:
                got = move(zone=home, path=path)
                said.append(f"Your brief now comes {in_sentence(got['when'])}, "
                            f"{city_of(home)} time.")
            except ValueError:
                pass
            reg = load(path)
    day = overdue(reg, now)
    if day and reg.get("late_checked") != day:
        reg["late_checked"] = day
        _owe(reg, {"tool": "list_triggers", "for": "late", "args": {},
                   "why": "the brief due %s has not come: list every page, then python3 "
                          "tools/routines.py brief --triggers <each page> says what is wrong "
                          "and the calls that mend it; tell the person in one line what was "
                          "wrong" % day})
        _save(reg, path)
    return said


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


def move(days=None, time=None, cron: str = "", path: str | None = None, zone: str = "",
         asked: dict | None = None) -> dict:
    """New days and a new time for the brief: written into the registry, and the one call
    that moves the task itself kept until a chat makes it. `cron` sets it outright (an undo,
    with the `asked` it had). `zone` moves it to another time zone, the page's own choice
    (2026-10-30). A time the person picks is kept to the minute and recorded as theirs
    (`asked`), so nothing moves it again; the same time sent back with new days leaves what
    was asked as it was."""
    path = _path(path)
    reg = load(path)
    r = _brief(reg)
    if r is None:
        raise ValueError("there is no brief yet to move")
    old = r.get("cron") or ""
    old_asked = r.get("asked")
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
        if isinstance(asked, dict) and asked.get("time"):
            r["asked"] = asked
        else:
            r.pop("asked", None)
    else:
        was = read_cron(old)
        new = cron_for(days if days not in (None, "", []) else was.get("days") or BRIEF_DAYS,
                       time or was.get("time") or "08:00", zone)
        if time and new["time"] != was.get("time"):
            r["asked"] = {"time": new["time"], "by": "person"}
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
            "undo": {"action": "brief.move", "value": {"cron": old, "asked": old_asked}}
            if old else None,
            "old_asked": old_asked, "calls": reg.get("owed") or []}


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
    reg["back_on"] = datetime.date.today().isoformat()
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
        # With the line that gets the copy: the chat it is bound to may be archived or deleted
        # by the day it fires, and a welcome-back that fails is the one thing that lifts the
        # break on its day (X-9, X-43). A start, a wake or a brief lifts it too (heal()).
        back = {"name": "Job search: welcome back",
                "run_once_at": _instant(end, (read_cron(r.get("cron")) or {}).get("time", ""),
                                        reg.get("timezone") or ""),
                "prompt": with_copy(stub(reg, r["key"]), _repo()),
                "initiation": "human_request"}
        # The chat the brief runs in. A task that starts a new chat on firing gets no copy of
        # the files and no add_repo to fetch one (seen 12, 29 and 31 Oct 2026), so it never
        # makes one: an older ops brief comes back in the ops chat, and a routine's in the
        # chat that asked for the break, which holds the copy.
        sid = (r.get("chat") or {}).get("session_id") or (
            (reg.get("ops_session") or {}).get("id") if setup_of(reg) == "ops_relay" else "")
        if not sid:
            import app_listen
            sid = app_listen.this_chat()
        back["persistent_session_id"] = (sid if str(sid).startswith("session_") else
                                         "<this chat's id: get_session with no session_id>")
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
    reg["back_on"] = today              # a brief due while it rested never reads as late
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


def page_part(path: str | None = None, now: datetime.datetime | None = None,
              today: datetime.date | None = None) -> dict:
    """What the page shows of the brief (its bell, and Settings' "Your brief"), and the
    actions that change it: on or off, its days and time in words, a break in force, and how
    many changes still wait for a chat. `now` and `today`: the page's own clock (the model's),
    else this computer's."""
    try:
        reg = load(_path(path))
    except Exception:  # noqa: BLE001  no profile or no registry: no brief yet
        reg = {}
    r = _brief(reg)
    got = read_cron((r or {}).get("cron") or "")
    real = real_time(r) if got else {}
    p = reg.get("pause") or {}
    try:
        late = late_line(overdue(reg, now) or "", today)
    except Exception:  # noqa: BLE001  never breaks the page
        late = ""
    # `when` is the time it really comes (the scheduler's late start where it reports one);
    # `time` is the time it is set for, which the sheet edits; `why` says in one line why
    # they differ, or why the app's own default is not on the hour (the maintainer,
    # 2026-11-06: "The page should show the real time").
    return {"set_up": r is not None, "off": bool((r or {}).get("off")),
            **({"late": late} if late else {}),
            "when": real.get("when") or got.get("when", ""), "days": got.get("days", []),
            "time": got.get("time", ""), "real_time": real.get("time", ""),
            "why": real.get("why", ""),
            "zone": got.get("zone") or reg.get("timezone", ""),
            "paused": {"until": p["until"], "since": p.get("since", "")} if p else None,
            "waiting": len(reg.get("owed") or []),
            # The run sends its own phone notification (brief.push_due), so Settings offers
            # the person's choice; a Routines-screen task's comes from the task itself.
            "push_here": r is not None and not brief_pushes_itself(reg),
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
                                   "upkeep-record", "upkeep-forget", "remind", "reminded",
                                   "mended", "rebind"):
        print(__doc__.split("\n\n")[1])
        return 2
    if argv[0] in ("move", "pause", "resume", "off", "on", "calls", "called"):
        return _schedule_cli(argv)
    if argv[0] == "remind":
        if not remind_due():
            print("remind: nothing to make (setup is finished, or a brief or a reminder is on file)")
            return 0
        import place
        owner, name = place.repo()
        got = remind_plan(owner, name)
        if not got["chat"]:
            print("chat: this chat's id could not be read: get_session with no session_id gives it")
            return 1
        print("make it now, asking nothing (one run tomorrow, in this chat; it says only that "
              "setup waits on their page):")
        print(f"  create_trigger: {json.dumps(got['create_trigger'], ensure_ascii=False)}")
        print(f"  then: {got['record']}, and say nothing about it")
        return 0
    if argv[0] == "reminded":
        trig = argv[argv.index("--trigger") + 1] if "--trigger" in argv[:-1] else ""
        print(reminded(trig))
        return 0
    if argv[0] == "mended":
        path = _path(None)
        reg = load(path)
        for r in work(reg):
            if r.get("trigger_id"):
                r["copy"] = True
        _save(reg, path)
        print("routines.json: every task's prompt gets its files in any chat")
        return 0
    if argv[0] == "upkeep-record":
        got = {argv[i][2:]: argv[i + 1] for i in range(1, len(argv) - 1, 2) if argv[i].startswith("--")}
        print(record_upkeep(got.get("session", ""), got.get("trigger", ""), got.get("cron", "")))
        return 0
    if argv[0] == "upkeep-forget":
        print(forget_upkeep())
        return 0
    if argv[0] == "rebind":
        got = {argv[i][2:]: argv[i + 1] for i in range(2, len(argv) - 1, 2) if argv[i].startswith("--")}
        try:
            print(rebind(argv[1] if len(argv) > 1 else "", got.get("session", ""), got.get("trigger", "")))
        except (ValueError, OSError) as e:
            print(f"routines.json: nothing changed: {e}")
            return 1
        return 0
    if argv[0] == "brief":
        triggers, more, chat_arg, page_arg = None, False, "", ""
        for i, a in enumerate(argv):
            if a == "--chat" and i + 1 < len(argv):
                chat_arg = argv[i + 1]
            if a == "--page-chat" and i + 1 < len(argv):
                page_arg = argv[i + 1]
            if a == "--triggers" and i + 1 < len(argv):
                with open(argv[i + 1], encoding="utf-8") as fh:
                    page, more = listing(json.load(fh))
                triggers = (triggers or []) + page
        try:
            reg = load()
        except Exception:  # no profile yet (setup), no registry, or a bad one: none on file
            reg = None
        here = chat_arg or (_page_chat() if has_page() else "")
        if not here:
            import app_listen
            here = app_listen.this_chat()
        here = here if str(here).startswith("session_") else ""
        # The chat that answers the page now (meta/listen's, as this checkout last saw it):
        # the brief belongs there, whichever chat asks.
        page_chat = page_arg or (_page_chat() if has_page() else "")
        found = existing_brief(reg, triggers, here=here,
                               page=page_chat if str(page_chat).startswith("session_") else "")
        print(f"{found['state']}: {found['say']}")
        # What the scheduler reports of its time (next_run_at, the last run's fired_at), kept
        # so the page shows when the brief really comes, never only the time it is set for.
        if found["state"] == "registered" and triggers:
            try:
                if saw(triggers):
                    print("saw: the brief's real time from the scheduler is kept in "
                          "profile/routines.json; commit it with the rest, and say nothing")
            except Exception:  # noqa: BLE001  never stops the check over a record
                pass
        if found["state"] == "elsewhere" and found.get("calls"):
            for i, c in enumerate(found["calls"], 1):
                print(f"move {i}: " + (f"{c['tool']} {json.dumps(c['args'], ensure_ascii=False)}"
                                       if c.get("tool") else c["run"]) + f" ({c['why']})")
            print(f"move: {found['then']}; commit and land it, and say nothing about it to the "
                  "person")
            return 0
        if found["state"] == "lost" and found.get("calls"):
            import place
            if place.surface() == "local":
                print("tell them: " + BRIEF_BELL)
                return 0
            for i, c in enumerate(found["calls"], 1):
                print(f"move {i}: " + (f"{c['tool']} {json.dumps(c['args'], ensure_ascii=False)}"
                                       if c.get("tool") else c["run"]) + f" ({c['why']})")
            print(f"move: {found['then']}; commit and land it. Tell the person only, as it is: "
                  f"\"{found['tell']}\"")
            return 0
        if more:
            print("more: the listing has another page (has_more); list it too and pass every "
                  "page with --triggers before deciding")
        import place
        mends = mend(triggers, _repo()) if triggers is not None and not more else []
        for i, c in enumerate(mends, 1):
            print(f"mend {i}: update_trigger {json.dumps(c['args'], ensure_ascii=False)} ({c['why']})")
        if mends:
            print("mend: make these, then python3 tools/routines.py mended; say nothing about it")
        elif triggers is not None and not more and reg and any(
                r.get("trigger_id") and not r.get("copy") for r in work(reg)):
            print("mend: every task already gets its files: python3 tools/routines.py mended")
        if place.surface() == "local":
            # A chat on their computer never makes the brief: a task made here would run on
            # the computer, or start a new chat every morning. The bell on the page queues it
            # for the chat in the cloud that answers the page (tools/page_db.py runs a brief
            # only there), and starts that helper first where there is none. With no page there
            # is no bell: the page comes first (X-37).
            print("tell them: " + place.BRIEF_LOCAL if found["state"] in ("registered", "found")
                  else ("tell them: " + BRIEF_BELL) if has_page() else BRIEF_NO_PAGE_LOCAL)
        elif found["state"] == "none" and triggers is not None:
            # A cloud chat makes it itself, asking nothing: a task bound to the chat that
            # answers the page, or with no page this chat, and a first run in a few minutes
            # (automation/README.md (a)). Never a chat of its own.
            owner, name = place.repo()
            got = plan(owner, name, chat=chat_arg,
                       initiation="own_initiative" if "--own-initiative" in argv else "human_request")
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
                                                    "--title", "--asked")
               if k in argv and argv.index(k) + 1 < len(argv)}
        if not opt.get("--trigger") or (opt.get("--setup", "chat_per_briefing") ==
                                        "chat_per_briefing" and not opt.get("--session")):
            print("usage: routines.py record --session <id> --trigger <id> [--cron \"<cron>\"] "
                  "[--setup routines_screen]", file=sys.stderr)
            return 2
        try:
            path = record(opt.get("--session", ""), opt["--trigger"], opt.get("--cron", ""),
                          setup=opt.get("--setup", "chat_per_briefing"),
                          title=opt.get("--title", ""), own_chat="--own-chat" in argv,
                          asked=opt.get("--asked", ""))
        except ValueError as e:
            print(f"routines.json: nothing recorded: {e}")
            return 1
        problems = check(load(path))
        for p_ in problems:
            print(f"routines.json: {p_}")
        print("routines.json: recorded the brief" + ("" if problems else ", clean"))
        return 1 if problems else 0
    if argv[0] == "stub":
        if len(argv) < 2:
            print("usage: routines.py stub <key>", file=sys.stderr)
            return 2
        print(with_copy(stub(load(), argv[1]), _repo()))
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
            print(json.dumps(calls(today=a.today), ensure_ascii=False, indent=1))
            return 0
        if argv[0] == "called":
            hit = called(a.n, a.id)
            print(f"routines.json: call {a.n} ({hit.get('tool')}) made; "
                  f"{len(calls(today=a.today))} still owed")
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
