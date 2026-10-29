#!/usr/bin/env python3
"""The brief, gathered by code in one command, so a scheduled run reads it once.

Everything the morning brief says comes from the state files: what is due today and
overdue (both halves of `open_actions.py --due`), the replies owed, the application nudges
with who they go to, the follow-ups drafted by code (`tools/followup_drafts.py`, through
compose's gate), the counts since the last brief, where the search is, three things to do
before the next one, the LinkedIn download and own-profile reminders, an update waiting,
and the news searches to run. The model's part of a run is the news and the message.

    python3 tools/brief.py                     # the brief, as text for a chat (under 2,500 characters)
    python3 tools/brief.py --write             # also the day's upkeep and records (below)
    python3 tools/brief.py --start --on "<model>" --write   # a scheduled run's whole start
    python3 tools/brief.py --write --page-applied           # after the page's ticks are applied
    python3 tools/brief.py news < items.txt    # the news reader's items, into today's record

--write does what the brief has always done to the state: closes the applications gone
quiet (`followups.py --close-quiet`), rebuilds the call preps gone stale (`prep.py
--stale-only`), writes the follow-up pack (documents/network/followup_pack_<today>.md) and
the brief's own record (documents/briefs/<today>.md), and takes the tip line. Without it,
nothing is written.

--start is a scheduled run's first step, so the model makes one call where it made four:
the day's update check (`sync_app.py --if-stale`), the container's Python side
(`setup_env.sh --python`) and the earlier runs' unsaved work, all run here with their
output kept in a file; then the brief is gathered by a fresh process, so an update the
sync just took is the code that runs. What the sync printed reaches the brief as lines
already decided: an update waiting (said once: left out when the last brief said it),
job sites blocked, upgrades to run, questions for the end. Nothing is pasted twice.

Where the person has a page (profile/app.json `url`), the brief is the page's too. What
they ticked there changes what is owed, so `--start` stops before gathering and prints the
steps that apply those ticks first (`app.py apply`, code alone); `--page-applied` then
gathers. The message links the page's To do rather than a file on GitHub, its questions are
on the page as To do cards, and the run brings the page up to date (`app.py view`) after it
lands. It runs in the chat that answers the page (tools/app_listen.py), so it never
publishes the page again and never starts a watch: `app.py view` is all it sends. A break the person took (`routines.py pause`) holds the brief: a run
during it says so in one line, and the run on the day it ends lifts it.

Plain Python, standard library, no network of its own (the sync in --start fetches). The
same state files and --today always print the same text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person                                         # noqa: E402
import local_path  # noqa: E402
from company_key import key as company_key            # noqa: E402

ROOT = os.path.dirname(_HERE)
BRIEFS = ("documents", "briefs")
TEXT_MAX = 2500
RECORD_OWED = 30       # the record lists this many owed; the pack holds every one
NEWS_MAX = 5           # in the record; the message carries at most three
MESSAGE_NEWS = 3
QUERIES_MAX = 6
# The person's own settings for the brief (person.json `brief`, set from the page's Tweak
# panel): how many owed items the message lists (B1), how many news items (B2), which news
# searches run (B3, never the work-rights one), and which parts it shows (B5, never Owed).
LENGTHS = {"short": 2, "standard": 4, "long": 6}
NEWS_CHOICES = (0, 1, 3, 5)
NEWS_GROUPS = ("employers", "rights", "market", "bank", "targets")
NEVER_OFF = ("rights",)
PARTS = ("since", "next_three", "tip")


def setting(name: str):
    """One of the person's brief settings, checked; the app's default when unset or unknown."""
    got = person.get(f"brief.{name}", None)
    if name == "length":
        return got if got in LENGTHS else "standard"
    if name == "news":
        return got if got in NEWS_CHOICES else MESSAGE_NEWS
    if name == "leave_out":
        return [g for g in (got or []) if g in NEWS_GROUPS and g not in NEVER_OFF]
    if name == "hide":
        return [p for p in (got or []) if p in PARTS]
    return got
QUIET_DAYS = 14        # nothing sent for this long: "little going out" leads
UNCONFIRMED_DAYS = (7, 45)   # drafted this long and not marked sent: ask whether it went
DEFAULT_SINCE_DAYS = 7
SYNC_LOG = "ljs-brief-sync.txt"
NEWS_HOLD = re.compile(r"\b(?:lay ?offs?|laid off|job cuts|cuts? \d+|hiring freeze|freez\w*|"
                       r"restructur\w*|redundanc\w*|shut\w* down|closing|closure)\b", re.I)
_LINK = re.compile(r"https?://[^\s)>\]]+")
_DATE_IN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# The central bank whose decisions move a market, by the person's country.
CENTRAL_BANK = {"CA": "Bank of Canada", "GB": "Bank of England", "UK": "Bank of England",
                "US": "Federal Reserve", "AU": "Reserve Bank of Australia",
                "NZ": "Reserve Bank of New Zealand", "IN": "Reserve Bank of India",
                "CH": "Swiss National Bank", "JP": "Bank of Japan"}
EURO = {"IE", "FR", "DE", "NL", "ES", "IT", "PT", "BE", "AT", "FI", "LU", "GR", "SK", "SI",
        "EE", "LV", "LT", "MT", "CY", "HR"}
COUNTRY = {"CA": "Canada", "GB": "UK", "UK": "UK", "US": "US", "AU": "Australia",
           "NZ": "New Zealand", "IE": "Ireland", "IN": "India", "SG": "Singapore",
           "DE": "Germany", "FR": "France", "NL": "Netherlands", "ES": "Spain"}
WHAT_COUNTS = ("employers the person is in process with or has a live thread at; their target "
               "employers, in their market; their market for the roles they want (hiring or "
               "layoff waves, a central-bank decision, sector earnings, a big funding round at a "
               "local company in their field); any change to their work authorization, which "
               "outranks everything else")


# ---------------------------------------------------------------- reading the state

def _today(value=None) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _d(value):
    m = _DATE_IN.search(str(value or ""))
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def brief_path(day: str) -> str:
    return person.state(*BRIEFS, "%s.md" % day)


def earlier_briefs(today: dt.date) -> list[str]:
    """The brief records before today, oldest first."""
    out = []
    for p in glob.glob(person.state(*BRIEFS, "*.md")):
        d = _d(os.path.basename(p))
        if d and d < today and os.path.basename(p) == "%s.md" % d.isoformat():
            out.append(p)
    return sorted(out)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def first_name(name) -> str:
    try:
        import tone
        return tone.greeting_name(name) or str(name or "")
    except Exception:
        return str(name or "").split(" ")[0]


def _status(row) -> str:
    return str(row.get("status") or "").strip().lower()


def counts_since(tracker, threads, since: dt.date, today: dt.date) -> dict:
    """What happened between the last brief and today, from the tracker and the message log."""
    import open_actions
    import throttle
    from network import state

    def inside(d):
        return d is not None and since < d <= today

    sent = sum(1 for r in tracker if _status(r) and _status(r) not in throttle.UNSENT
               and not throttle.is_process(r) and inside(_d(throttle.applied_on(r))))
    replies = sum(1 for r in threads if state._direction(r) == "in" and state.said_something(r)
                  and not state.is_auto_reply(r) and inside(_d(r.get("date"))))
    interviews = 0
    for r in tracker:
        if _status(r) in throttle.FINAL and _status(r) != "rejected" or _status(r) in throttle.UNSENT:
            continue
        _f, _files, stages = open_actions._stages(r)
        interviews += sum(1 for st in stages if inside(_d(st.get("date"))))

    def last_word(r):
        days = [d for d in (_d(x) for x in _DATE_IN.findall(str(r.get("notes") or "")))
                if d and d <= today]
        days.append(_d(throttle.applied_on(r)))
        days = [d for d in days if d]
        return max(days) if days else None

    offers = sum(1 for r in tracker if "offer" in _status(r) and inside(last_word(r)))
    rejections = sum(1 for r in tracker if _status(r) == "rejected" and inside(last_word(r)))
    return {"sent": sent, "replies": replies, "interviews": interviews, "offers": offers,
            "rejections": rejections}


def live_counts(tracker) -> dict:
    import throttle
    live = set(throttle.LIVE_PROCESS)
    processes = [r for r in tracker if _status(r) in live]
    apps = [r for r in tracker if (_status(r) == "applied" or _status(r) in live)
            and not throttle.is_process(r)]
    return {"applications": len(apps), "interviews": len(processes), "processes": processes}


def next_stage(row, today: dt.date) -> dict:
    import open_actions
    _f, _files, stages = open_actions._stages(row)
    ahead = [st for st in stages if not st.get("done") and _d(st.get("date"))
             and _d(st.get("date")) >= today]
    return min(ahead, key=lambda st: st["date"]) if ahead else {}


def unconfirmed(tracker, today: dt.date) -> list[dict]:
    """Drafted between 7 and 45 days ago and never marked sent or not sent."""
    import throttle
    lo, hi = UNCONFIRMED_DAYS
    out = []
    for r in tracker:
        if _status(r) not in throttle.UNSENT or str(r.get("confirmed_by") or "").strip():
            continue
        d = _d(r.get("date"))
        if d and lo < (today - d).days <= hi:
            out.append(r)
    return sorted(out, key=lambda r: r.get("date") or "")


# ---------------------------------------------------------------- the news searches

def _section(text: str, heading: str) -> str:
    """The body of the markdown section whose heading contains `heading`, or ""."""
    m = re.search(r"^(#{2,4})\s+[^\n]*" + re.escape(heading) + r"[^\n]*\n", text, re.M | re.I)
    if not m:
        return ""
    level = len(m.group(1))
    rest = text[m.end():]
    end = re.search(r"^#{2,%d}\s" % level, rest, re.M)
    return rest[:end.start()] if end else rest


def target_names(claude_md: str) -> tuple[list[str], list[str]]:
    """(named employers, sectors) from the profile summary's Target Sectors."""
    body = _section(claude_md, "Target Sectors")
    names, sectors = [], []
    for line in body.splitlines():
        if not line.startswith("- "):
            continue
        line = re.sub(r"\([^)]*\)", "", line[2:])
        line = re.sub(r"\*\*", "", line)
        if ":" in line:
            head, tail = line.split(":", 1)
            sectors.append(head.strip())
            first = re.split(r"\.\s", tail, maxsplit=1)[0]
            for n in first.split(","):
                n = n.strip(" .;")
                if n and n[:1].isupper() and len(n) <= 40 and len(n.split()) <= 4:
                    names.append(n)
        else:
            sectors.append(line.split(".")[0].strip())
    return list(dict.fromkeys(names)), [s for s in sectors if s]


def what_counts(claude_md: str) -> str:
    body = _section(claude_md, "This search's automation")
    for line in body.splitlines():
        if re.search(r"what counts", line, re.I):
            return re.sub(r"\*\*", "", line.lstrip("- ")).strip()[:600]
    return WHAT_COUNTS


def _profile_text(name: str) -> str:
    try:
        return person.text(name)
    except Exception:
        return ""


def _net(attr: str, default=""):
    try:
        return getattr(person.module("networking"), attr, default) or default
    except Exception:
        return default


def queries(today: dt.date, live_employers: list[str], claude_md: str) -> list[str]:
    """At most six searches, in the order the brief values them: the employers in play,
    the person's work authorization, their market, their central bank, then their targets
    (a different pair each run, so every target is looked at over a few weeks)."""
    month = today.strftime("%B %Y")
    country_code = person.country()
    country = COUNTRY.get(country_code, country_code)
    city = str(_net("HOME_CITY", "") or str(person.get("identity.location", "") or "").split(",")[0]).strip()
    names, sectors = target_names(claude_md)
    off = set(setting("leave_out"))
    out = ["%s news %s" % (n, month) for n in live_employers[:2]] if "employers" not in off else []
    status = str(_net("STATUS_NAME", "") or "").strip()
    if status and not re.search(r"citizen", status, re.I):
        out.append("%s %s rule changes %s" % (status, country, today.year))
    field = re.split(r",|;", sectors[0])[0].strip() if sectors else "data and analytics"
    if city and "market" not in off:
        out.append("%s %s hiring or layoffs %s" % (city, field.lower(), month))
    bank = "European Central Bank" if country_code in EURO else CENTRAL_BANK.get(country_code, "")
    if bank and "bank" not in off:
        out.append("%s interest rate decision %s" % (bank, month))
    targets = [n for n in names if company_key(n) not in {company_key(x) for x in live_employers}
               ] if "targets" not in off else []
    room = max(QUERIES_MAX - len(out), 1 if targets else 0)
    if targets:
        start = (today.toordinal() // 3) % len(targets)
        pick = [targets[(start + i) % len(targets)] for i in range(min(room, len(targets)))]
        out += ["%s news %s" % (n, month) for n in pick]
    return list(dict.fromkeys(out))[:QUERIES_MAX]


def links_sent(paths: list[str]) -> list[str]:
    """Every link the news sections of the last two briefs carried, so none is sent twice."""
    out = []
    for p in paths[-2:]:
        out += _LINK.findall(_section(_read(p), "News"))
    return list(dict.fromkeys(u.rstrip(".,;") for u in out))


# ---------------------------------------------------------------- the sync's output

def _git_dir() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True,
                           capture_output=True, timeout=10, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    import tempfile
    return tempfile.gettempdir()


def sync_log_path() -> str:
    return os.environ.get("LJS_BRIEF_SYNC") or os.path.join(_git_dir(), SYNC_LOG)


def read_sync(today: dt.date, path: str | None = None) -> dict:
    """What today's start printed, decided into lines: {} when it did not run today."""
    text = _read(path or sync_log_path())
    if not text.startswith("date: %s\n" % today.isoformat()):
        return {}
    head, _, out = text.partition("\n---\n")
    meta = dict(ln.split(": ", 1) for ln in head.splitlines() if ": " in ln)
    lines = out.splitlines()
    got = {"exit": int(meta.get("exit", "0") or 0), "earlier": [b for b in meta.get("earlier", "").split() if b],
           "setup": meta.get("setup", ""), "update": "", "blocked": [], "changed": [],
           "upgrades": [], "questions": [], "first": "", "for_claude": []}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("An update is waiting:"):
            got["update"] = s
        elif s.startswith("Job sites blocked"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  "):
                    break
                got["blocked"].append(nxt.strip())
        elif s.startswith("What changed"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  - "):
                    break
                got["changed"].append(nxt[4:].strip())
    for i, ln in enumerate(lines):
        # What the sync says to Claude alone: their own tests an update broke (bringing them
        # in line is this run's job), and a CLAUDE.md that changed under a chat kept open.
        if ln.startswith("Claude, not for the person:"):
            more = [x.strip() for x in lines[i + 1:i + 6] if x.startswith("  ")]
            got["for_claude"].append(" ".join([ln.split(":", 1)[1].strip()] + more)[:400])
        elif ln.startswith("Claude: ") and " changed. " in ln:
            got["for_claude"].append(ln[len("Claude: "):].split(". ", 1)[0] + ": read it again "
                                     "before any work beyond this brief in this chat")
    mode = ""
    for ln in lines:
        s = ln.strip()
        if s.startswith("Claude applies these itself"):
            mode = "alone"
        elif s.startswith("These need you"):
            mode = "you"
        elif s.startswith("- ") and mode:
            got["upgrades" if mode == "alone" else "questions"].append(s[2:])
        elif mode and not s.startswith("(asked again"):
            mode = ""
    if got["exit"]:
        got["first"] = next((ln.strip() for ln in lines if ln.strip()
                             and not ln.startswith("note:")), "")
    return got


def start(argv: list[str], model: str) -> int:
    """The scheduled run's start: the update check, the Python side, the earlier runs' work,
    all kept in one file; then the brief, gathered by a fresh process."""
    today = dt.date.today()
    py = sys.executable
    r = subprocess.run([py, os.path.join(_HERE, "sync_app.py"), "--if-stale", "--on", model],
                       cwd=ROOT, text=True, capture_output=True, encoding="utf-8",
                       errors="replace")
    setup = ""
    script = os.path.join(_HERE, "setup_env.sh")
    if os.name == "posix" and os.path.isfile(script):
        s = subprocess.run(["bash", script, "--python"], cwd=ROOT, text=True,
                           capture_output=True, encoding="utf-8", errors="replace")
        if s.returncode:
            setup = ((s.stderr or s.stdout or "").strip().splitlines() or ["failed"])[-1][:200]
    earlier = subprocess.run(["git", "branch", "-r", "--no-merged", "origin/master", "--list",
                              "origin/claude/ops-*"], cwd=ROOT, text=True, capture_output=True,
                             encoding="utf-8", errors="replace")
    branches = " ".join(b.strip() for b in (earlier.stdout or "").splitlines() if b.strip())
    with open(sync_log_path(), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("date: %s\nexit: %d\nearlier: %s\nsetup: %s\n---\n%s%s"
                 % (today.isoformat(), r.returncode, branches, setup, r.stdout or "",
                    r.stderr or ""))
    url = page_url()
    if url and "--page-applied" not in argv:
        sys.stdout.write(page_first(url, argv))
        return 0
    return subprocess.run([py, os.path.abspath(__file__)] + argv, cwd=ROOT).returncode


def page_url() -> str:
    """The person's page (profile/app.json `url`), or "" when none is published."""
    try:
        with open(person.path("app.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except (person.NoProfile, OSError, ValueError):
        return ""
    url = str(got.get("url") or "") if isinstance(got, dict) else ""
    return url if url.startswith("https://claude.ai/") else ""


def page_first(url: str, argv: list[str]) -> str:
    """What a run with a page does before the brief is gathered: the ticks made on the page
    are applied (code, exactly once, with receipts), so the brief never lists as owed what
    the person already marked done there. Then the brief itself."""
    keep = []
    for flag in ("--write", "--today"):
        if flag in argv:
            i = argv.index(flag)
            keep += argv[i:i + (2 if flag == "--today" else 1)]
    rest = " ".join(keep + ["--page-applied"])
    return "\n".join([
        "PAGE FIRST, FOR CLAUDE (the person's ticks on their page change what is owed):",
        "1. ArtifactData query, url %s, collection actions, then collection receipts, each "
        "with out_dir <D> (a new folder in your scratchpad) and query.limit 1000." % url,
        "2. python3 tools/app.py apply <D> --chat brief --claim, then send the batch it names "
        "(ArtifactData batch). Refused: another chat is applying them; go to 4.",
        "3. python3 tools/app.py apply <D> --chat brief, then send every batch it prints.",
        "4. python3 tools/brief.py %s (the brief itself), and carry on with the prompt's "
        "step 1 from what it prints. Keep <D> for the page's refresh in step 4." % rest,
        ""])


# ---------------------------------------------------------------- the brief

def gather(today: dt.date, write: bool = False) -> dict:
    """Everything the brief says, as one dict. With `write`, the day's upkeep is done and
    recorded (closing the quiet applications, the stale preps, the pack, the tip)."""
    import followup_drafts
    with followup_drafts.FoldersOnce():
        return _gather(today, write)


def _gather(today: dt.date, write: bool) -> dict:
    import followup_drafts
    import followups
    import open_actions
    import throttle
    from network import state

    iso = today.isoformat()
    contacts, threads = state.load_contacts(), state.load_threads()
    tracker = open_actions._tracker()
    earlier = earlier_briefs(today)
    since = _d(os.path.basename(earlier[-1])) if earlier else today - dt.timedelta(days=DEFAULT_SINCE_DAYS)
    last_text = _read(earlier[-1]) if earlier else ""

    # The day's upkeep first, so everything below reads the state it leaves.
    closed = followups.close_quiet(today=today, write=write)
    if closed and write:
        tracker = open_actions._tracker()
    preps = _preps(iso) if write else {"line": "", "rebuilt": 0, "research": []}

    items = open_actions.due_items(contacts, threads, tracker, today)
    got = followup_drafts.drafts(items, contacts, threads, tracker, iso)
    pack = followup_drafts.write_pack(iso, got, contacts) if write else ""

    live = [i for i in got if not i.get("held") and not i.get("quiet") and not i.get("old")
            and i.get("kind") != "request_pending"]
    asks = [i for i in got if i.get("kind") == "request_pending" and not i.get("held")]
    old = [i for i in got if i.get("old")]
    held = [i for i in got if i.get("held") and not i.get("quiet")]
    replies = [i for i in live if i.get("half") == "contact" and i.get("kind") in ("reply", "resume")]
    nudges_due = [i for i in live if i.get("half") == "application" and i.get("kind") != "interview"]
    counts = live_counts(tracker)
    since_counts = counts_since(tracker, threads, since, today)

    # Where the search is.
    sent_lately = any(_d(throttle.applied_on(r)) and (today - _d(throttle.applied_on(r))).days <= QUIET_DAYS
                      for r in tracker if _status(r) and _status(r) not in throttle.UNSENT
                      and not throttle.is_process(r))
    warm = _warm_routes(contacts, threads)
    owned = open_actions.campaigns(tracker)
    lead = _lead(counts, replies, nudges_due, sent_lately, warm, owned, today)

    sync = read_sync(today)
    brk = _break(today, write)
    update = sync.get("update", "")
    if update and update in last_text:
        update = ""                         # said in the last brief: once is enough
    lines = []
    if sync.get("blocked"):
        lines.append(" ".join(sync["blocked"]))
    if sync.get("exit"):
        lines.append("Today's check for app updates did not finish; the next run tries again.")
    if sync.get("changed"):
        more = len(sync["changed"]) - 1
        lines.append("Updated: %s%s." % (sync["changed"][0].rstrip(". "),
                                         ", and %d more" % more if more > 0 else ""))
    if brk.get("over"):
        lines.append(brk["over"])
    if closed:
        lines.append("%s as no reply: %s. Say if any is still open." % (
            "Closing" if write else "Would close", "; ".join(
                "%s (%s)" % (it["company"], it["role"] or "role not recorded") for it in closed[:3])
            + (" and %d more" % (len(closed) - 3) if len(closed) > 3 else "")))
    ww = _what_works(tracker, today)
    if ww:
        lines.append(ww)
    if update:
        lines.append(update)

    export_line, profile_line = _export_due(today, threads), _own_profile_due(today, contacts, threads)
    three = _next_three(got, counts, replies, unconfirmed(tracker, today), preps, export_line,
                        profile_line, sent_lately, warm, today)

    live_names = _live_employers(tracker, contacts, threads, today)
    claude_md = _profile_text("CLAUDE.md")
    b = {
        "date": iso, "weekday": today.strftime("%A"), "since": since.isoformat(),
        "counts": {"owed": len(live), **{k: v for k, v in counts.items() if k != "processes"}},
        "since_counts": since_counts, "lead": lead,
        "owed": [_owed_line(i) for i in live],
        "set_aside": _set_aside(asks, old, held),
        "lines": lines, "next_three": three,
        "drafts": got, "pack": pack, "closed": closed, "preps": preps,
        "queries": queries(today, live_names, claude_md),
        "what_counts": what_counts(claude_md), "skip_links": links_sent(earlier),
        "sync": sync, "export_line": export_line, "profile_line": profile_line,
        "write_here": followup_drafts.to_write_here(got),
        "url": _brief_url(iso), "page": page_url(), "tip": "", "written": write,
        "paused": brk.get("until", "") if brk and brk.get("until", "") > iso else "",
    }
    if write:
        b["tip"] = _tip(today)
        write_record(b)
    return b


def _break(today: dt.date, write: bool) -> dict:
    """A break the person took on the page (routines.py pause): {"until"} while it runs; on
    or after its last day, with `write`, it is lifted here ("over" says so) and the calls
    that turn the brief back on are left for the run to make."""
    try:
        import routines
        got = routines.paused()
    except Exception:  # noqa: BLE001  no profile or no registry: no break
        return {}
    if not got:
        return {}
    if got["until"] > today.isoformat() or not write:
        return got
    try:
        routines.resume(today.isoformat())
    except Exception:  # noqa: BLE001  the next run tries again
        return got
    return {"over": "Welcome back: your break is over, and everything below is what is "
                    "waiting for you."}


def _preps(iso: str) -> dict:
    """The call preps gone stale, rebuilt: {"line", "rebuilt", "research": [...]}."""
    import contextlib
    import io
    try:
        import prep
    except Exception:
        return {"line": "", "research": []}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            prep.main(["--stale-only", "--today", iso])
    except (Exception, SystemExit):
        return {"line": "", "research": []}
    out = buf.getvalue().splitlines()
    head = next((ln for ln in out if "prep documents" in ln), "")
    n = re.match(r"(\d+)", head)
    research = [ln for ln in out if "RESEARCH NEXT" in ln or ln.split(":", 1)[-1].strip().startswith("RESEARCH")]
    return {"line": head, "rebuilt": int(n.group(1)) if n else 0, "research": research}


def _warm_routes(contacts, threads) -> list[dict]:
    import throttle
    from network import state
    index = state.by_contact(threads) if threads else {}
    out = []
    for c in contacts:
        st = state.effective_status(c, index.get(str(c.get("contact_id") or "").strip(), ()))
        if st in throttle.RESPONDED and st not in ("closed", "gone_cold"):
            out.append({"name": c.get("name") or "", "company": c.get("company") or "", "status": st})
    return out


def _live_employers(tracker, contacts, threads, today) -> list[str]:
    """The employers in play, nearest an outcome first: a live process, a live thread, an
    application out and not gone quiet."""
    import throttle
    seen, out = set(), []

    def add(name):
        k = company_key(name)
        if name and k and k not in seen:
            seen.add(k)
            out.append(name.strip())

    for r in tracker:
        if _status(r) in set(throttle.LIVE_PROCESS):
            add(r.get("company"))
    for w in _warm_routes(contacts, threads):
        add(w["company"])
    for r in tracker:
        d = _d(throttle.applied_on(r))
        if _status(r) == "applied" and d and (today - d).days <= throttle.SILENCE_DAYS:
            add(r.get("company"))
    return out


def _lead(counts, replies, nudges_due, sent_lately, warm, owned, today) -> str:
    procs = counts["processes"]
    if procs:
        r = procs[0]
        company = (r.get("company") or "").strip()
        k = company_key(company)
        if k in owned:
            return "%s is live, and its own chat (%s) has the prep." % (company, owned[k])
        st = next_stage(r, today)
        more = " (and %d more)" % (len(procs) - 1) if len(procs) > 1 else ""
        nxt = (": the %s is on %s" % (st.get("label") or "next stage", st["date"])) if st else ""
        return "Your %s process is live%s%s. /interview %s prepares it." % (
            company, more, nxt, company)
    if replies:
        i = replies[0]
        who = first_name(i.get("name", "").split(" (")[0])
        n = len(replies)
        return ("%s %s waiting on you: %s%s has waited %d days." % (
            n, "person is" if n == 1 else "people are", who,
            " (%s)" % i["name"].split(" (", 1)[1].rstrip(")") if " (" in i.get("name", "") else "",
            max(i.get("late") or 0, 0)))
    if nudges_due or (counts["applications"] and sent_lately):
        return ("%d application%s out and waiting%s." % (
            counts["applications"], " is" if counts["applications"] == 1 else "s are",
            "; %d follow-up%s due" % (len(nudges_due), "" if len(nudges_due) == 1 else "s")
            if nudges_due else ""))
    if not sent_lately:
        routes = ", ".join("%s (%s)" % (first_name(w["name"]), w["company"]) for w in warm[:2])
        return ("Nothing has gone out in %d days.%s A fresh shortlist is one \"find me jobs\" away."
                % (QUIET_DAYS, " Warm routes already in your contacts: %s." % routes if routes else ""))
    return "Nothing is owed today."


def _owed_line(i: dict) -> dict:
    """One owed item, as the brief says it: who, what, and where its draft stands."""
    d = i["draft"]
    late = max(i.get("late") or 0, 0)
    if i.get("half") == "contact":
        what = {"reply": "reply owed", "resume": "%s owed" % _noun(), "nudge": "nudge due",
                "first_message": "first message owed", "action_due": "your date"}.get(i.get("kind"), "owed")
        if i.get("kind") == "reply" and "owed to" in (i.get("what") or "") and _noun() in i.get("what", ""):
            what = "%s owed" % _noun()
    elif i.get("kind") == "interview":
        what = i.get("what") or "interview"
        what = what.split(":")[0]
    else:
        what = "follow-up %s" % ((i.get("what") or "").split(",")[0].replace("nudge ", "")) \
            + (" %s" % i["to"].replace("to: ", "to ").split(" (")[0] if i.get("to") else "")
    status = {"ready": "draft ready", "check": "draft ready, check it first",
              "write": ("%s to write" % ("reply" if d.get("kind") == "reply" else "draft"))
              if d.get("who") == "here" else "needs you",
              "none": ""}[d["status"]]
    return {"text": "%s: %s%s%s" % (i.get("name"), what, ", %dd" % late if late else "",
                                     "; " + status if status else ""),
            "id": i.get("id"), "status": d["status"], "kind": i.get("kind"),
            "half": i.get("half")}


def _noun() -> str:
    return str(person.get("documents.noun", "resume") or "resume")


def _set_aside(asks, old, held) -> list[str]:
    out = []
    if asks:
        out.append("%d connection request%s nobody accepted: withdraw them on LinkedIn"
                   % (len(asks), "" if len(asks) == 1 else "s"))
    if old:
        out.append("%d owed over 45 days with nothing done, set aside" % len(old))
    if held:
        out.append("%d held for now (an interview, a referral or your own note)" % len(held))
    return out


def _what_works(tracker, today) -> str:
    try:
        import what_works
        got = what_works.brief_search(tracker, today)
    except Exception:
        return ""
    diffs = [ln[2:] for ln in got.splitlines() if ln.startswith("- ")]
    return ("What works: " + diffs[0]) if diffs else ""


def _export_due(today, threads) -> str:
    try:
        import export
        return export.due(today, threads) or export.waiting_line(
            today, [_read(p) for p in earlier_briefs(today)
                    if os.path.basename(p)[:10] >= str(export.load_record().get(
                        "requested_on") or "")]) or ""
    except Exception:
        return ""


def _own_profile_due(today, contacts, threads) -> str:
    try:
        import own_profile
        return own_profile.due(today, contacts, threads) or ""
    except Exception:
        return ""


def _next_three(got, counts, replies, drafted, preps, export_line, profile_line, sent_lately,
                warm, today) -> list[str]:
    """Exactly three things to do before the next brief, most valuable first, each one line
    and under half an hour."""
    out: list[str] = []
    seen: set = set()

    def add(key, text):
        if key not in seen and len(out) < 3:
            seen.add(key)
            out.append(text)

    live = [i for i in got if not i.get("held") and not i.get("quiet") and not i.get("old")]
    for i in live:
        if i.get("kind") == "interview" and "no pack yet" in (i.get("what") or ""):
            add(i.get("key"), "Prepare for your interview at %s, %s." % (
                i["name"].split(" (")[0], i["what"].split(" (")[0].replace("interview ", "", 1)))
    for i in replies:
        who = i.get("name", "")
        if _noun() + " owed" in (i.get("what") or "") or i.get("kind") == "resume":
            add(i.get("key"), "Send %s the %s they asked for." % (who, _noun()))
        elif i["draft"]["status"] in ("ready", "check"):
            add(i.get("key"), "Send your reply to %s: it is drafted for you." % who)
        else:
            add(i.get("key"), "Reply to %s." % who)
    for i in live:
        if i.get("kind") == "interview" and "thank-you" in (i.get("what") or ""):
            add(i.get("key"), "Send the thank-you after your interview at %s."
                % i["name"].split(" (")[0])
    for i in live:
        if i["draft"]["status"] in ("ready", "check") and i.get("kind") in ("nudge", "first_message") \
                and i.get("half") == "contact":
            add(i.get("key"), "Send the nudge to %s: it is drafted for you." % i.get("name"))
    for i in live:
        if i.get("half") == "application" and i["draft"]["status"] in ("ready", "check"):
            add(i.get("key"), "Send the follow-up on %s: it is drafted for you." % i.get("name"))
    if drafted:
        names = "; ".join("%s, %s" % (r.get("company"), r.get("role") or "role not recorded")
                          for r in drafted[:3])
        add("unconfirmed", "Did these go? %s. Mark each one applied or not." % names)
    for ln in (preps or {}).get("research", [])[:1]:
        name = ln.split(":", 1)[0].strip()
        add("research:" + name, "Read the prep before your call with %s." % name)
    if profile_line:
        m = re.search(r"\"([^\"]+)\"", profile_line)
        if m:
            add("own_profile", m.group(1))
    if export_line and export_line.startswith("Your LinkedIn download was asked for on"):
        add("export_wait", export_line)
    elif export_line and "asked for on" not in export_line:
        m = re.search(r"(\d+) days old", export_line)
        add("export", "Ask LinkedIn for a new copy of your data%s; ask Claude for the steps."
            % (" (yours is %s days old)" % m.group(1) if m else ""))
    for i in live:
        if i.get("kind") == "nudge" and i["draft"]["status"] == "write":
            add(i.get("key"), "Tell me one new thing to say to %s and I'll draft the nudge."
                % i.get("name"))
    if not sent_lately:
        for w in warm[:1]:
            add("warm", "Ask %s (%s) about the team there: a warm route you already have."
                % (first_name(w["name"]), w["company"]))
        add("search", "Find new jobs: Jobs, Find jobs.")
    if counts.get("applications"):
        add("outcome", "Heard back from anyone? Mark it on the application.")
    add("search", "Find new jobs: Jobs, Find jobs.")
    add("network", "Find people at an employer you want: Contacts, Find people.")
    add("targets", "Watch an employer you would love to work at (Jobs, Change the search), and "
        "Claude reads its own jobs every search.")
    return out


def _tip(today) -> str:
    try:
        import tips
        state_ = tips.load()
        said = tips.line("brief", today, state_)
        if said:
            tips.save(state_)
        return said or ""
    except Exception:
        return ""


def _brief_url(iso: str) -> str:
    """Where the message sends the person: their page's To do, else the day's record."""
    url = page_url()
    if url:
        return url + "#todo"
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True,
                           capture_output=True, timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", (r.stdout or "").strip())
    if r.returncode or not m:
        return ""
    return "https://github.com/%s/%s/blob/master/documents/briefs/%s.md" % (m.group(1), m.group(2), iso)


# ---------------------------------------------------------------- what it says

def headline(b: dict) -> str:
    c = b["counts"]
    return "%s brief: %d owed · %d application%s live · %d interview%s" % (
        b["weekday"], c["owed"], c["applications"], "" if c["applications"] == 1 else "s",
        c["interviews"], "" if c["interviews"] == 1 else "s")


def since_line(b: dict) -> str:
    s = b["since_counts"]
    extra = "".join(", %d %s" % (s[k], w) for k, w in (("offers", "offers"), ("rejections", "rejections"))
                    if s[k])
    return "Since %s: %d sent, %d replies, %d interviews%s" % (
        _short_date(b["since"]), s["sent"], s["replies"], s["interviews"], extra)


def _short_date(iso: str) -> str:
    d = _d(iso)
    return "%d %s" % (d.day, d.strftime("%b")) if d else iso


def message_lines(b: dict, owed_max: int = 4) -> list[str]:
    """The message as a phone shows it, news left for the model to put in."""
    if b.get("paused"):
        return ["Your search is paused until %s. Nothing is chased meanwhile." % _short_date(
            b["paused"])] + (["Your page: " + b["url"]] if b.get("page") else [])
    out = [headline(b), b["lead"], "", "Owed"]
    owed = b["owed"]
    out += ["- " + o["text"] for o in owed[:owed_max]] or ["Nothing owed"]
    if len(owed) > owed_max:
        out.append("- and %d more in the full brief" % (len(owed) - owed_max))
    out += ["- " + s for s in b["set_aside"]]
    hide = set(setting("hide"))
    if "since" not in hide:
        out += ["", since_line(b)]
    out += b["lines"]
    if "next_three" not in hide:
        out += ["", "Next three"] + ["%d. %s" % (n, t) for n, t in enumerate(b["next_three"], 1)]
    if setting("news"):
        out += ["", "News", "<NEWS>"]
    asks = len((b.get("sync") or {}).get("questions") or [])
    if b.get("page") and asks:
        out += ["", "%d question%s wait%s for you on your page." % (
            asks, "" if asks == 1 else "s", "s" if asks == 1 else "")]
    if b["url"]:
        out += ["", ("Your page: " if b.get("page") else "Full brief: ") + b["url"]]
    if b["tip"] and "tip" not in hide:
        out += [b["tip"]]
    return out


def _tidy_due() -> str:
    """The day's tidy of the app's own old chats, done in the brief's run when the brief runs
    in the chat that answers the page and nothing has done it yet today: one daily pass, not
    two (tools/tidy.py)."""
    try:
        import app_listen
        import tidy
        here = app_listen.this_chat()
        if app_listen.chat_kind() != "cloud" or not here.startswith("session_"):
            return ""
        if (app_listen.seen().get("listener") or {}).get("chat") != here or not tidy.due():
            return ""
    except Exception:  # noqa: BLE001  no git folder, no record: nothing to tidy from here
        return ""
    return ("tidy, before the final reply (the message is the last thing this run says): "
            "list_sessions (mine: true) and list_triggers, "
            "every page, each saved to a file; python3 tools/tidy.py plan --sessions <each> "
            "--triggers <each>; do what it prints (the app skill, \"Once a day\")")


def claude_lines(b: dict) -> list[str]:
    """For the model only: what it acts on. Never in the message."""
    s = b["sync"] or {}
    out = []
    if b.get("paused"):
        return ["paused until %s: the message is the line above, as it is; no news search, no "
                "drafts, nothing else to do or save" % b["paused"]]
    if not s and b.get("written"):
        out.append("the start did not run today: run python3 tools/brief.py --start --on "
                   "\"<model>\" --write")
    if s.get("blocked"):
        out.append("job sites are blocked: the message opens with the line above about it")
    if s.get("exit"):
        out.append("the update check stopped (exit %d): %s" % (s["exit"], s.get("first", "")[:160]))
    if s.get("setup"):
        out.append("setting up the Python side failed: %s" % s["setup"])
    for br in s.get("earlier", []):
        out.append("an earlier run's work is not saved (%s): land it as _common.md step 3 says" % br)
    out += s.get("for_claude", [])
    if s.get("upgrades"):
        out.append("run /upgrade 20 now (%d waiting); one plain line per change it made goes at "
                   "the end of the message" % len(s["upgrades"]))
    if s.get("questions") and b.get("page"):
        out.append("the questions are on the page as To do cards: ask none in the message, "
                   "which says how many wait there")
    elif s.get("questions"):
        out.append("at most three questions at the end of the message, each as written: "
                   + " | ".join(q for q in s["questions"][:3]))
    if b["write_here"]:
        import followup_drafts
        n, most = len(b["write_here"]), followup_drafts.WRITE_HERE_MAX
        out.append("%d draft%s this run can write or rewrite from the thread%s: python3 "
                   "tools/followup_drafts.py context --due, write them, then "
                   "followup_drafts.py check - --pack" % (
                       n, "" if n == 1 else "s",
                       " (the first %d; the rest wait in the pack)" % most if n > most else ""))
    if b["profile_line"]:
        out.append("own profile question: a yes runs python3 tools/network/own_profile.py check")
    tidy_line = _tidy_due()
    if tidy_line:
        out.append(tidy_line)
    n = setting("news")
    out.append("news: the news-reader agent, given these searches: %s; at most %d item%s in the "
               "message (the person's setting)" % (" | ".join(b["queries"]), n, "" if n == 1 else "s")
               if n else "news: none in the message, by the person's setting: run no news search")
    out.append("since %s; links already sent: %s" % (
        b["since"], " ".join(b["skip_links"][:10]) or "none"))
    out.append("what counts: " + b["what_counts"])
    if b.get("page"):
        out.append("the page, after landing (step 4): ArtifactData query, url %s, collections "
                   "view and meta, out_dir <D>; python3 tools/app.py view <D>/view --dump <D> "
                   "--chat brief; send every batch it prints. Never republish the page: this chat already "
                   "answers it"
                   % b["page"])
    try:
        import routines
        owed = routines.calls()
    except Exception:  # noqa: BLE001
        owed = []
    if owed:
        out.append("scheduled-task changes the page asked for: python3 tools/routines.py calls "
                   "lists %d; make each, then routines.py called <n>" % len(owed))
    if b["pack"]:
        out.append("wrote " + local_path.rel(b["pack"], person.state()).replace(os.sep, "/"))
    try:
        import bar
        names = bar.unjudged_contacts()
    except Exception:  # noqa: BLE001  no profile or no contact book: nothing to judge
        names = []
    if names:
        # Judged once, an employer that clears nothing stops filling the person's To do.
        out.append("judge each employer once, from what you know of it (pay, prestige, signal "
                   "or none), with python3 tools/bar.py judge \"<employer>\" <verdict> \"<why>\": "
                   + "; ".join(names[:8]) + ("; and %d more (bar.py unjudged --contacts)"
                                              % (len(names) - 8) if len(names) > 8 else ""))
    return out


def render_text(b: dict) -> str:
    """The brief for a chat, under TEXT_MAX characters: the message, then the lines for Claude."""
    start = LENGTHS[setting("length")]
    for owed_max in [n for n in (6, 4, 3, 2) if n <= start] or [2]:
        body = "\n".join(message_lines(b, owed_max))
        tail = "\n".join(["", "FOR CLAUDE, never in the message:"] + ["- " + x for x in claude_lines(b)])
        text = body + "\n" + tail + "\n"
        if len(text) <= TEXT_MAX:
            return text
    return text[:TEXT_MAX - 40].rsplit("\n", 1)[0] + "\n... (cut at %d characters)\n" % TEXT_MAX


# ---------------------------------------------------------------- the record

NEWS_HOLDER = "Searching: the news is added when the search is back."
# Said once above the items: the news reader searches and opens no page, so a line is only
# ever what its search result said, and the record says so.
NEWS_SOURCE = "From search results; no page was opened, so each line says only what its result said."


def record_text(b: dict, news: list[str] | None = None) -> str:
    """documents/briefs/<date>.md: the same layout every time, so the briefs read as one record."""
    out = ["# Brief, %s (%s)" % (b["date"], b["weekday"]), "",
           "Since %s. Gathered by tools/brief.py; the news by the news reader." % b["since"], "",
           "## Where the search is", "", headline(b), "", b["lead"], "", "## Owed", ""]
    owed = b["owed"]
    if not owed:
        out.append("Nothing owed.")
    by_id = {i["id"]: i for i in b["drafts"]}
    for o in owed[:RECORD_OWED]:
        out.append("- " + o["text"])
        d = (by_id.get(o["id"]) or {}).get("draft") or {}
        if d.get("status") in ("ready", "check"):
            out.append("")
            out += ["  > " + ln for ln in d["text"].splitlines()]
            out += ["  Check: " + w for w in d.get("warnings") or []]
            out.append("")
    if len(owed) > RECORD_OWED:
        out.append("- and %d more, each in today's follow-up pack" % (len(owed) - RECORD_OWED))
    out += ["- " + s for s in b["set_aside"]]
    out += ["", "## Since the last brief", "", since_line(b) + "."]
    out += ["- " + ln for ln in b["lines"]]
    if b["preps"].get("rebuilt"):
        out.append("- Call preps rebuilt: %d, each for a conversation that changed since it was "
                   "written." % b["preps"]["rebuilt"])
    out += ["", "## Next three", ""] + ["%d. %s" % (n, t) for n, t in enumerate(b["next_three"], 1)]
    out += ["", "## News", ""]
    out += (news if news is not None else [NEWS_HOLDER])
    return "\n".join(out).rstrip() + "\n"


def write_record(b: dict, news: list[str] | None = None) -> str:
    path = brief_path(b["date"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(record_text(b, news))
    return path


def take_news(text: str, today: dt.date) -> dict:
    """The news reader's items into today's record: at most NEWS_MAX, none whose link an
    earlier brief carried, and a dated note on a live application's row for a freeze or
    layoffs at that employer. {"kept", "dropped", "noted", "path"}."""
    items = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.lower().startswith(("quiet week", "none", "no news")):
            continue
        s = s.lstrip("-*• ").strip()
        if s:
            items.append(s)
    seen = set(links_sent(earlier_briefs(today) + [brief_path(today.isoformat())]))
    kept, dropped = [], []
    for s in items:
        links = [u.rstrip(".,;") for u in _LINK.findall(s)]
        if links and any(u in seen for u in links):
            dropped.append(s)
            continue
        if len(kept) < NEWS_MAX:
            kept.append(s)
    path = brief_path(today.isoformat())
    body = _read(path)
    news = ([NEWS_SOURCE, ""] + ["- " + s for s in kept]) if kept else ["Quiet week."]
    if body:
        head = body.split("\n## News", 1)[0].rstrip()
        new = head + "\n\n## News\n\n" + "\n".join(news) + "\n"
    else:
        new = "# Brief, %s\n\n## News\n\n%s\n" % (today.isoformat(), "\n".join(news))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    noted = _note_news(kept, today)
    return {"kept": kept, "dropped": dropped, "noted": noted, "path": path}


def _note_news(kept: list[str], today: dt.date) -> list[str]:
    """A dated line on each live application's row whose employer a freeze or layoffs item names."""
    import csv_store
    import throttle
    path = person.state("job_search_tracker.csv")
    if not kept or not os.path.exists(path):
        return []
    rows = csv_store.read_rows(path)
    live = set(throttle.LIVE_PROCESS) | {"applied"}
    noted = []
    for r in rows:
        company = str(r.get("company") or "").strip()
        if _status(r) not in live or not company:
            continue
        rx = re.compile(r"\b" + re.escape(company) + r"\b", re.I)
        for s in kept:
            if rx.search(s) and NEWS_HOLD.search(s):
                note = "%s: news: %s (the brief, from a search result)" % (
                    today.isoformat(), " ".join(s.split())[:180])
                if note not in str(r.get("notes") or ""):
                    r["notes"] = ((r.get("notes") or "").rstrip() + " | " + note).strip(" |")
                    noted.append(company)
    if noted:
        csv_store.write_rows(path, rows, csv_store.header(path))
    return list(dict.fromkeys(noted))


# ---------------------------------------------------------------- the command

def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _utf8()
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["news"]:
        ap = argparse.ArgumentParser(prog="brief.py news")
        ap.add_argument("--file", help="the items, one a line; stdin without it")
        ap.add_argument("--today", default="")
        a = ap.parse_args(argv[1:])
        text = _read(a.file) if a.file else sys.stdin.read()
        got = take_news(text, _today(a.today))
        print("news: %d kept%s%s" % (
            len(got["kept"]),
            "; %d left out, already sent in an earlier brief" % len(got["dropped"]) if got["dropped"] else "",
            "; noted on the tracker for %s" % ", ".join(got["noted"]) if got["noted"] else ""))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="do the day's upkeep and write the records")
    ap.add_argument("--start", action="store_true", help="a scheduled run's start, then the brief")
    ap.add_argument("--on", default="", help="with --start: the model this run is on")
    ap.add_argument("--today", default="")
    ap.add_argument("--page-applied", dest="page_applied", action="store_true",
                    help="the page's ticks are applied: gather the brief")
    a = ap.parse_args(argv)
    if a.start:
        rest = [x for x in argv if x != "--start"]
        return start(rest, a.on)
    if not person.exists():
        print("No profile yet, so there is no brief: set the search up first.")
        return 1
    today = _today(a.today)
    b = gather(today, write=a.write)
    sys.stdout.write(render_text(b))
    return 0


if __name__ == "__main__":
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:       # a merge left markers: say which file, read nothing
        print("brief: %s" % e, file=sys.stderr)
        raise SystemExit(1) from None
