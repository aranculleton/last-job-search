#!/usr/bin/env python3
"""Profile upgrades: what an app feature needs on the person's side, for people who set up before it.

/setup runs once. When the app later adds something /setup writes, or something
only an action on the person's side switches on (a portal built with
/add-portal, a profile name with no safe default, a portal rebuilt to a new
contract), `tools/sync_app.py` brings the code and nothing else: an older repo
never gets the new part, nobody can tell, and every round quietly runs without
it. A CHANGELOG line saying "run X" is printed once and then lost.

So every such action is registered here. Each upgrade checks the person's repo
itself for the trace the action leaves (a profile name, a dated record, a
portal folder, a frontmatter line), never a ledger, so it cannot drift: it is
pending exactly while the trace is missing. An empty but dated answer ("looked,
nothing worth building") counts as done.

    python3 tools/profile_upgrades.py            # the pending ones, with what runs each
    python3 tools/profile_upgrades.py --line     # one line for a round summary ("" when none)
    python3 tools/profile_upgrades.py --all      # every upgrade, done or pending, and why
    python3 tools/profile_upgrades.py --after-sync   # sync_app.py: run the instant ones, then list
    python3 tools/profile_upgrades.py --plan     # JSON, most urgent first: what /upgrade works through
    python3 tools/profile_upgrades.py --check boards  # one upgrade: "done" or what is missing
    python3 tools/profile_upgrades.py --no <id>  # their no to a question: kept, dated, asked
                                                 # again when it changes or after REASK_DAYS

Exit 0 always, except --check while its upgrade is pending: a pending upgrade never
blocks a sync, a round or a session.

**Nobody has to remember these.** A list a person has to read and act on is a list
nobody acts on, so almost every upgrade is `needs="nobody"`: at the start of a session
Claude starts a background agent that runs `/upgrade`, which works through them from
the profile and research while the person's own request goes ahead, commits each on
its own and reports what it wrote and how to undo it. Only an upgrade that needs the
person's answer or consent (`needs="you"`, with its `ask`) is put to them, once, at the
end. The twice-weekly shortlist does the same before its round.

`tools/sync_app.py` runs `--after-sync` after every sync, "up to date"
included; `tools/run_round.py` prints `--line` with its MET or MISSED summary;
CLAUDE.md "Start of every session" says what the session does with them.

Costs:
  instant   a re-render of a derived file, no web, no questions. Run by the
            sync itself and committed on its own, touching only the personal
            paths the upgrade names, or not at all.
  edit      a mechanical change to the person's own files the session makes on
            a yes. Never automatic: those files are the person's record.
  question  asks the person something; minutes.
  research  web research, sometimes a portal build; the time is given.

Adding a feature that needs any of this is not done until it is registered
here: tests/test_profile_upgrades.py fails on a new profile name with no
upgrade and no stated safe default, and on a CHANGELOG entry that tells
existing users to do something without naming its upgrade.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COSTS = ("instant", "edit", "question", "research")


@dataclass(frozen=True)
class Upgrade:
    id: str
    added: str                      # YYYY-MM-DD the feature shipped
    gives: str                      # one line, in the person's terms
    pending: Callable[[], str]      # "" when done, else what is missing
    run: str                        # what the session runs
    cost: str                       # instant | question | research
    time: str = ""                  # "~5 min"
    names: tuple = ()               # profile names it covers (module.NAME)
    conditional: bool = False       # pending only for some people (a country, a field)
    command: tuple = ()             # instant only: argv, from the repo root
    paths: tuple = field(default=())  # instant only: the personal path globs it may touch
    # 1 something fails until it is done, 2 results are silently worse, 3 a part
    # of the app the person is missing, 4 polish. The order /upgrade works in.
    priority: int = 3
    # "nobody": Claude does it alone, from the profile and research, and says
    # what it wrote. "you": it needs the person's answer or consent (`ask`), so
    # it is asked, never guessed. Nearly everything is "nobody": a list a person
    # has to read and act on is a list nobody acts on.
    needs: str = "nobody"
    # A question is asked short and plain first (`ask`: 40 words at most, no jargon, a
    # yes-or-not-now the person can answer at once). Only a yes brings `steps` (five
    # lines at most, one action each), and only "why?" brings `why` (one sentence). A
    # paragraph pasted at someone who never asked for it is what nobody reads.
    ask: str = ""
    steps: Callable[[], str] | None = None
    why_ask: str = ""
    # A no is an answer for now, never for ever: a question someone said no to comes
    # back when what it offers has changed (ask_version moves on and `changed` says
    # how) or once REASK_DAYS have passed, saying when they said no (`again()`).
    ask_version: int = 1
    changed: str = ""


# ------------------------------------------------------------------ helpers

def _surface_steps(eid: str) -> list[str]:
    """A path from the dated, sourced registry (tools/claude_surfaces.json)."""
    import claude_surfaces
    return claude_surfaces.steps(eid)


def _mod(name: str):
    """profile/<name>.py, or None where there is no profile or no such file."""
    try:
        return person.module(name)
    except person.NoProfile:
        return None


def _dated(value) -> bool:
    try:
        dt.date.fromisoformat(str(value or "")[:10])
        return True
    except ValueError:
        return False


def _missing(module: str, *names: str) -> list[str]:
    m = _mod(module)
    if m is None:
        return []
    return [n for n in names if not hasattr(m, n)]


# ------------------------------------------------------------------ a no, for now

ASKED_FILE = "asked.json"     # in profile/: {upgrade id: {"no": "YYYY-MM-DD", "version": n}}
REASK_DAYS = 30
# The whole answer to a no: one line, and it is true (REASK_DAYS).
NO_REPLY = "No problem, I'll ask again in a month."


def _asked_path() -> str:
    return person.path(ASKED_FILE)


def asked() -> dict:
    """Every no on record, by upgrade id."""
    try:
        import json
        with open(_asked_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, person.NoProfile):
        return {}


def record_no(uid: str, today: dt.date | None = None) -> str:
    """Their no to one question, dated, with the version of the question it answered."""
    import json
    u = by_id(uid)
    got = asked()
    got[uid] = {"no": (today or dt.date.today()).isoformat(), "version": u.ask_version}
    p = _asked_path()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(got, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return p


def again(uid: str, version: int, changed: str, today: dt.date | None = None) -> str:
    """Why a question they said no to is asked again now, or "" while their no stands.

    A recorded no stands until the question changes or REASK_DAYS pass. A no with no
    record (given before this was kept) answered the question's first version, no earlier
    than the day it shipped (`added`): asked again at once only when it has changed since, and
    otherwise REASK_DAYS after that day, so a no given last week is not asked again now.
    """
    today = today or dt.date.today()
    rec = asked().get(uid)
    if rec is None:
        known = next((u for u in REGISTRY if u.id == uid), None)
        rec, when, said = {"version": 1}, known.added if known else "", "you said no before"
    else:
        when = rec.get("no", "")
        said = f"you said no on {when}" if when else "you said no before"
    try:
        since = (today - dt.date.fromisoformat(when)).days if when else None
    except ValueError:
        since = None
    if int(rec.get("version") or 0) < version:
        return f"{said}, and it has changed since: {changed}" if changed else f"{said}"
    if since is not None and since >= REASK_DAYS:
        ago = f", {since} days ago" if said != "you said no before" else ""
        return f"{said}{ago}; it is asked once more in case that has changed"
    return ""


def _probe(code: str) -> str:
    """Run `code` in a fresh interpreter against this profile and return what it
    prints. The tools read the profile when imported, so a check that needs one
    of them runs it apart. A probe that fails reports nothing, never noise."""
    prelude = ("import sys; sys.path[:0] = [%r, %r]\n"
               % (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")))
    try:
        r = subprocess.run([sys.executable, "-c", prelude + code], cwd=ROOT, env=os.environ,
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


# Countries whose working week does not end on Saturday and Sunday. A country
# missing here keeps the Saturday and Sunday default, as every repo had before
# WEEKEND existed; one listed by mistake costs a question.
OTHER_WEEKEND = {"AF", "BD", "BH", "BN", "DJ", "DZ", "EG", "IL", "IQ", "IR", "JO", "KW", "LY",
                 "MV", "NP", "OM", "QA", "SA", "SD", "SY", "YE"}
# Markets whose postings are written in English. Elsewhere the English defaults
# for internal-only vacancies and the portal probe word match nothing.
ENGLISH_MARKETS = {"GB", "US", "CA", "AU", "NZ", "IE", "IN", "SG", "ZA", "PH", "MY", "HK",
                   "NG", "KE", "GH", "PK", "JM", "TT"}
# Resume headings written in English: a profile whose headings are not all in
# this set writes its documents in another language.
ENGLISH_HEADINGS = {"summary", "profile", "professional summary", "experience",
                    "professional experience", "work experience", "employment", "skills",
                    "technical skills", "key skills", "education", "certifications",
                    "qualifications", "languages", "projects", "references", "interests"}


# ------------------------------------------------------------------ checks

def _boards() -> str:
    s = _mod("search")
    if s is None:
        return ""
    if not hasattr(s, "PORTALS"):
        return ("you were never told what LinkedIn's robots.txt says about the search every "
                "round sends it, and no boards were researched for you")
    if not hasattr(s, "PORTAL_RESEARCH"):
        return ("profile/search.py has no PORTAL_RESEARCH: nobody has looked for the job "
                "boards that serve your market, so rounds search LinkedIn and freehire only")
    rows = [r for r in (s.PORTAL_RESEARCH or []) if isinstance(r, dict)]
    if not any(_dated(r.get("checked")) for r in rows):
        return "PORTAL_RESEARCH holds no dated look at your job boards"
    return ""


def _alerts() -> str:
    if _missing("search", "JOB_ALERT_QUERY"):
        return ("nobody has asked whether rounds should read your LinkedIn job alerts "
                "(profile/search.py has no JOB_ALERT_QUERY)")
    if not str(getattr(_mod("search"), "JOB_ALERT_QUERY", "") or "").strip():
        u = by_id("job-alerts")
        return again("job-alerts", u.ask_version, u.changed)
    return ""


def _learned_choices() -> str:
    try:
        import learned
    except ImportError:
        return ""
    waiting = learned.offers()
    if not waiting:
        return ""
    return "%d app improvement(s) would change something you chose: %s" % (
        len(waiting), "; ".join(learned.question(o) for _, o in waiting[:3]))


def _linkedin_plan() -> str:
    if _missing("networking", "LINKEDIN_PLAN"):
        return ("nobody has asked whether you pay for LinkedIn Premium (profile/networking.py "
                "has no LINKEDIN_PLAN), so notes are kept to a free account's 200 characters "
                "and no InMail is drafted")
    return ""


def _profile_never_say() -> str:
    import learned
    got = learned.unadopted()
    if got:
        return ("profile/CLAUDE.md says never to write " + ", ".join('"%s"' % p for p, _ in got[:4])
                + (" and more" if len(got) > 4 else "") + ", and nothing checks a draft for it")
    return ""


def _public_holidays() -> str:
    """Pending where no rules cover the person's country and their own list has no date
    in the coming year: follow-ups would count every public holiday as a working day."""
    import datetime
    import holidays
    country, _region, extra = holidays._settings()
    if not country or country in holidays.RULES:
        return ""
    year = datetime.date.today().year + 1
    if any(str(d)[:4] == str(year) for d in extra):
        return ""
    return (f"no public holidays on file for {country} for {year} (profile/search.py "
            "PUBLIC_HOLIDAYS), so follow-ups count them as working days")


def _profile_reads() -> str:
    if _missing("networking", "PROFILE_READS"):
        return ("nobody has asked whether Claude may read the LinkedIn profile of each person "
                "about to be messaged in your own browser (profile/networking.py has no "
                "PROFILE_READS), so a note rests on what you paste and on their public work")
    if str(getattr(_mod("networking"), "PROFILE_READS", "") or "") == "paste":
        u = by_id("profile-reads")
        return again("profile-reads", u.ask_version, u.changed)
    return ""


def _people_sources() -> str:
    if _mod("networking") is not None and _missing("networking", "PEOPLE_SOURCES"):
        return ("/network searches the same default places for everyone (profile/networking.py "
                "has no PEOPLE_SOURCES), not the places people in your field, level and country "
                "are actually named")
    return ""


def _rulings_review() -> str:
    if _mod("search") is None:
        return ""
    n = _probe("import exclude; print(len(exclude.unreviewed()))").strip()
    if n.isdigit() and int(n):
        return (f"{n} postings are ruled out on reasons that say nothing about the rules they "
                "rest on, so they never lapse when your rules change, and some may be wrong "
                "by the rules as they are now")
    return ""


def _alumni_text() -> str:
    """The plan's alumni line names the employer they work at now, which is never searched."""
    if _mod("networking") is None:
        return ""
    code = ("import reading\n"
            "net = reading._NET\n"
            "lines = [str(r[1]) for r in (getattr(net, 'PEOPLE_SOURCES', None) or ())\n"
            "         if r and r[0] == 'alumni_employer' and len(r) > 1]\n"
            "h = reading.history()\n"
            "now = [n for names in h['employers'] if names[0] in h['current'] for n in names]\n"
            "print(sorted({n for n in now for t in lines if reading._has(n, t)}))")
    got = _probe(code).strip()
    if got and got != "[]":
        return (f"the alumni line in PEOPLE_SOURCES names {got.strip('[]')}, where you work "
                "now: alumni searches never search a current employer, so the line says "
                "something the plan does not do")
    return ""


def _work_place() -> str:
    """No answer yet to where they will mostly work (tools/place.py, /setup's question)."""
    if not person.exists("person.json"):
        return ""
    try:
        import json
        with open(person.path("place.json"), encoding="utf-8") as fh:
            if json.load(fh).get("works_on"):
                return ""
    except (OSError, ValueError):
        pass
    return ("set up before the app asked where you will mostly work, so it cannot say when "
            "a chat is in the wrong place for your settings")


def _ruling_parts() -> str:
    if _mod("search") is None:
        return ""
    n = _probe("import exclude; print(sum(len(es) for _, es in exclude.unnamed()))").strip()
    if n.isdigit() and int(n):
        return (f"{n} postings ruled out by your rules say nothing of which rule they rest on, "
                "so changing any one rule, one number even, puts every one of them back to be "
                "screened again")
    return ""


def _connections_export() -> str:
    if _mod("networking") is None:
        return ""
    root = os.environ.get("LJS_STATE") or ROOT
    root = root if os.path.isabs(root) else os.path.join(ROOT, root)
    if os.path.exists(os.path.join(root, "documents", "linkedin", "Connections.csv")):
        return ""
    if not os.environ.get("LJS_STATE") and os.path.exists(
            person.local_state("documents", "linkedin", "Connections.csv")):
        return ""                                   # in the main checkout, read from a worktree
    if getattr(_mod("networking"), "CONNECTIONS_EXPORT", None) == "declined":
        u = by_id("connections-export")
        return again("connections-export", u.ask_version, u.changed)
    return ("every networking run starts from strangers, because the people you already know "
            "on LinkedIn are not on file (documents/linkedin/Connections.csv)")


def _contract() -> str:
    try:
        import portals
        on = portals.enabled()
        old = [n for n, v in on.items() if v and n not in portals.APP_PORTALS
               and portals.has_cli(n) and not portals.follows_contract(n)]
    except Exception:
        return ""
    if old:
        return (f"{', '.join(old)} {'is' if len(old) == 1 else 'are'} on but not built to the "
                f"portal contract (no `contract: 1`), so rounds skip {'it' if len(old) == 1 else 'them'}")
    return ""


def _unknown_portal() -> str:
    try:
        import portals
        gone = portals.unknown()
    except Exception:
        return ""
    if gone:
        return (f"profile/search.py PORTALS names {', '.join(gone)}, which this repo no longer "
                f"has, so it searches nothing")
    return ""


def _skills_headings() -> str:
    k = _mod("skills")
    if k is None:
        return ""
    labels = list(getattr(k, "LABELS", ()) or ())
    if not labels:
        return "profile/skills.py has no LABELS, so no resume renders (no Skills headings)"
    lines = {line for line, _ in labels} | set(getattr(k, "MERGE", {}) or {})
    lost = sorted({row[0] for row in getattr(k, "ITEMS", ()) or ()} - lines)
    if lost:
        return (f"skills in {', '.join(lost)} sit under no Skills line (LABELS or MERGE), "
                f"so they never print")
    return ""


def _fit_missing_shape() -> str:
    s = _mod("search")
    bad = [e for e in getattr(s, "FIT_MISSING", []) or [] if len(e) != 3] if s else []
    if bad:
        return (f"{len(bad)} FIT_MISSING entr{'y' if len(bad) == 1 else 'ies'} in the old "
                f"two-part shape, so scoring stops at the first posting")
    return ""


NETWORKING_NAMES = ("TITLE_SETS", "FUNCTION_TITLE", "HANDS_ON_TITLE", "HIRING_ROLE_NOUNS",
                    "HIRING_HEADLINE_NOUNS", "OTHER_FUNCTIONS", "OTHER_FUNCTIONS_MOVED",
                    "OWN_FUNCTION_WORDS")


def _networking() -> str:
    n = _mod("networking")
    if n is None:
        return ""
    gone = [x for x in NETWORKING_NAMES if not hasattr(n, x)]
    groups = dict(getattr(n, "TITLE_SETS", {}) or {})
    empty = [g for g in ("hiring_authority", "senior_ic", "function", "recruiting")
             if not groups.get(g)]
    if gone or empty:
        return ("/network has no titles of your own to search for ("
                + ", ".join(gone + [f"TITLE_SETS[{g!r}]" for g in empty if "TITLE_SETS" not in gone])
                + ")")
    return ""


LEVEL_NAMES = ("FIT_BELOW_LEVEL", "OPP_BELOW_LEVEL", "OPP_ABOVE_LEVEL")


def _level() -> str:
    gone = _missing("search", *LEVEL_NAMES)
    if gone:
        return (f"profile/search.py has no {', '.join(gone)}: no title is ranked down for "
                f"being above or below your level")
    return ""


def _themes() -> str:
    out = _probe("import allocate; print(', '.join(allocate.uncued_themes()))")
    return f"bullet themes no posting word matches: {out}" if out else ""


def _scoring() -> str:
    out = _probe("import prefilter\n"
                 "S = prefilter.person.module('search')\n"
                 "print(', '.join(q for q in getattr(S, 'SCRAPE_QUERIES', ())\n"
                 "                if prefilter.title_verdict(q)[0] == 'FAIL'))")
    if out:
        return (f"your own search titles fail your own title gate ({out}): the scoring "
                f"vocabulary is not yours")
    return ""


def _role_headings() -> str:
    out = _probe("import profile_facts as F\n"
                 "lines = F._read()\n"
                 "bad = [h for h in F._experience_headings(F.sections(lines), lines)\n"
                 "       if not F._ROLE_HEADING.match(h)]\n"
                 "print('; '.join(sorted(bad)))")
    if out:
        return (f"role headings the tools cannot read ({out[:120]}), so call-prep "
                f"documents carry none of your employers")
    return ""


def _statement_templates() -> str:
    if not person.exists("CLAUDE.md"):
        return ""
    with open(person.path("CLAUDE.md"), encoding="utf-8") as fh:
        heads = [ln for ln in fh if ln.lstrip().startswith("#")]
    if not any(re.search(r"statement", h, re.I) for h in heads):
        return "profile/CLAUDE.md has no profile statement templates of your own"
    return ""


def _dropped_rows() -> str:
    """Contacts closed only because a queue was set aside before anything went: they read as
    dead ends, and discovery hid their employers as "already covered"."""
    found = _probe("import state; print(len(state.closed_but_dropped(state.load_contacts(), "
                   "state.load_threads())))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) closed when a queue was set aside, though nothing was ever sent to "
            "them" % n) if n else ""


def _read_break() -> str:
    """Browser reads pause between bursts; how long is the person's call, so it is written
    into their profile where they can see and change it, at the app's value."""
    net = _mod("networking")
    if net is None or str(getattr(net, "PROFILE_READS", "") or "").lower() != "browser":
        return ""
    if hasattr(net, "PROFILE_READ_BREAK_MINUTES"):
        return ""
    return ("profile/networking.py has no PROFILE_READ_BREAK_MINUTES: the break between bursts "
            "of profile reads is the app's, not yours to see or change")


def _move_and_area() -> str:
    """identity.moved and identity.area: an interview pack prepares honest small talk for
    someone who moved in the last year, and asks nothing of anyone else."""
    if not person.exists("person.json"):
        return ""
    ident = person.data("person").get("identity") or {}
    missing = [k for k in ("moved", "area") if k not in ident]
    if missing:
        return ("person.json has no identity.%s: an interview pack cannot tell whether you moved "
                "recently, or where you live" % " or identity.".join(missing))
    # A marker where the date goes: the first version of this upgrade had no form for a
    # profile that only confirms they were there by a date, and wrote one.
    moved = str(ident.get("moved") or "").strip()
    if not re.fullmatch(r"none|just arrived|(?:by\s+)?\d{4}-\d{2}(?:-\d{2})?", moved, re.I):
        return ("person.json identity.moved is %r, not a date or \"none\": the interview pack's "
                "small talk for someone who moved recently stays off" % moved[:60])
    return ""


def _work_auth_employer() -> str:
    """WORK_AUTH["employer"]: the wording a recruiter or employer hears. Without it a call
    prep falls back to the senior networking line, which is not always the person's own
    employer-facing sentence."""
    net = _mod("networking")
    if net is None:
        return ""
    auth = getattr(net, "WORK_AUTH", None)
    if isinstance(auth, dict) and "employer" in auth:
        return ""
    return ("profile/networking.py WORK_AUTH has no \"employer\" line: a recruiter would hear "
            "the networking wording rather than your employer-facing one")


def _interview_prep() -> str:
    if person.exists() and not person.exists("07-interview-prep.md"):
        return "profile/07-interview-prep.md is missing: /interview has no STAR examples of yours"
    return ""


def _interview_tags() -> str:
    if not person.exists("07-interview-prep.md"):
        return ""
    found = _probe("import interview_pack; print('\\n'.join(interview_pack.untagged()))")
    bare = [t for t in found.splitlines() if t.strip()]
    if not bare:
        return ""
    return (f"{len(bare)} STAR stor{'y' if len(bare) == 1 else 'ies'} in "
            "profile/07-interview-prep.md say which questions they answer nowhere, so an "
            "interview pack cannot match them: " + "; ".join(bare[:3])
            + (f"; {len(bare) - 3} more" if len(bare) > 3 else ""))


def _process_postings() -> str:
    """A process folder with no job_posting.md: 3.7.0's `process` wrote none, and the app's
    folder test then failed the person's own CI, so they could not land work."""
    found = _probe("import interview_pack as p; print(len(p.missing_postings()))")
    n = int(found) if found.isdigit() else 0
    return ("%d hiring process folder(s) with no job_posting.md: the folder check in your own "
            "CI fails until each has one" % n) if n else ""


def _campaign_notes() -> str:
    """Notes kept by hand for an employer with a hiring process, from before its living prep
    document existed: what was decided in them is lost to the next chat until it is folded
    in."""
    if not person.exists():
        return ""
    found = _probe("import json, interview_pack as p; print(json.dumps(p.handkept_notes()))")
    try:
        rows = json.loads(found) if found else []
    except ValueError:
        return ""
    if not rows:
        return ""
    return ("%d note file(s) kept by hand for a hiring process that its prep document has not "
            "folded in: %s" % (len(rows), "; ".join("%s (%s)" % (r["path"], r["company"])
                                                      for r in rows[:3])))


def _profile_consistency() -> str:
    """Facts a screen checks first, said differently in two places of the profile."""
    if not person.exists():
        return ""
    found = _probe("import json, profile_consistency as c; print(json.dumps(c.findings()))")
    try:
        rows = json.loads(found) if found else []
    except ValueError:
        return ""
    if not rows:
        return ""
    return ("your profile says %s differently in %d place(s): %s" % (
        " and ".join(sorted({r["fact"] for r in rows})), len(rows),
        "; ".join("%s:%s says \"%s\"" % (r["file"], r["line"], r["said"]) for r in rows[:3]
                  if r["said"])))


def _country() -> str:
    if person.exists("person.json") and not person.get("identity.country", ""):
        return ("person.json has no identity.country: paper size, working week and "
                "market language cannot follow it")
    return ""


def _market_week() -> str:
    if person.country() in OTHER_WEEKEND and _missing("search", "WEEKEND"):
        return "follow-up dates count Saturday and Sunday as the weekend, not yours"
    return ""


def _market_language() -> str:
    c = person.country()
    if c and c not in ENGLISH_MARKETS:
        gone = _missing("search", "INTERNAL_ONLY", "INTERNAL_ONLY_TITLE", "CANARY_QUERY")
        if gone:
            return (f"{', '.join(gone)} still in English, so internal-only vacancies in your "
                    f"market's language are not cut and the portal probe may misfire")
    return ""


def _letter_language() -> str:
    if not person.exists("person.json"):
        return ""
    heads = person.get("documents.headings", {}) or {}
    values = heads.values() if isinstance(heads, dict) else heads
    other = [v for v in values if isinstance(v, str) and v.strip().lower() not in ENGLISH_HEADINGS]
    if other and (person.get("documents.salutation_prefix", None) is None
                  or person.get("documents.page_label", None) is None):
        return "your letters print 'Dear' and 'Page' in a document written in another language"
    return ""


# What /setup, /upgrade or anyone else could not ground is written `[CONFIRM: what]`
# in the profile, never guessed. Each one is a question only the person can answer.
CONFIRM = re.compile(r"\[CONFIRM(?::\s*([^\]]*))?\]")
_SKIP_DIRS = {"tests", "__pycache__"}


def unconfirmed() -> list[tuple[str, str]]:
    """(profile file, what to confirm) for every `[CONFIRM: ...]` left in the profile."""
    try:
        root = person.directory()
    except person.NoProfile:
        return []
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in _SKIP_DIRS and not d.startswith("."))
        for f in sorted(fns):
            if not f.endswith((".md", ".py", ".json")):
                continue
            path = os.path.join(dp, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(path, os.path.dirname(root))
            out += [(rel, (m.group(1) or "").strip() or "a fact marked unconfirmed")
                    for m in CONFIRM.finditer(text)]
    return out


def _unconfirmed() -> str:
    found = unconfirmed()
    if not found:
        return ""
    shown = "; ".join(f"{what} ({where})" for where, what in found[:3])
    return (f"{len(found)} fact{'s' if len(found) != 1 else ''} in your profile only you can "
            f"confirm: {shown}{' ...' if len(found) > 3 else ''}")


def _screen_flags() -> str:
    gone = _missing("search", "SCREEN_WRONG_FAMILY", "SCREEN_HOMONYMS")
    if gone:
        return (f"profile/search.py has no {' or '.join(gone)}: the screen flags no posting "
                f"as the wrong job family for you")
    return ""


def _required() -> str:
    """Every name a tool reads with no default, that this profile lacks. Read
    off the code (tools/profile_names.py), so a new required name is caught the
    day it ships, with nothing to register."""
    if not person.exists():
        return ""
    try:
        import profile_names
        names = profile_names.collect()
        keys = profile_names.collect_person()
    except Exception:
        return ""
    gone = [] if person.exists("person.json") else ["profile/person.json"]
    for module, entries in sorted(names.items()):
        need = [n for n, e in entries.items() if e["required"]]
        if not need:
            continue
        if not person.exists(module + ".py"):
            gone.append(f"profile/{module}.py")
            continue
        gone += [f"{module}.{n}" for n in _missing(module, *need)]
    for key, e in sorted(keys.items()):
        if e["required"] and person.exists("person.json") and person.get(key, None) is None:
            gone.append(f"person.json {key}")
    if gone:
        return "needed by the tools and missing: " + ", ".join(gone[:8]) + (" ..." if len(gone) > 8 else "")
    return ""


# A line in the profile that tells a draft to use a phrase the person later said never to
# use: "in outbound messages say 'I made the move'" stayed in two profile files after the
# person's never-say for it, so every draft read both. Only a line that prescribes the
# phrase counts; one that forbids it, or a sentence of theirs that merely contains it,
# is left alone (tone.py and voice_check.py still flag it in anything drafted).
_PRESCRIBES = re.compile(r"\b(?:say|says|said as|line is|write|use|wording is|phrase is)"
                         r"\W{0,4}$", re.I)
_FORBIDS = re.compile(r"\b(?:never|not|don'?t|avoid|without|no)\b", re.I)


def _prescribed() -> list[str]:
    try:
        import learned
        phrases = learned.never_say()
        d = person.directory()
    except (ImportError, person.NoProfile):
        return []
    if not phrases:
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith((".md", ".py")):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            for phrase, rx in phrases:
                for m in rx.finditer(line):
                    before = line[max(0, m.start() - 40):m.start()].rstrip(" \"'\u201c\u2018")
                    if _PRESCRIBES.search(before) and not _FORBIDS.search(before):
                        out.append(f"profile/{name}:{n} ({phrase!r})")
    return out


def _never_said() -> str:
    found = _prescribed()
    if not found:
        return ""
    return ("your profile still tells drafts to use wording you said never to use: "
            + "; ".join(found[:4]) + (f"; {len(found) - 4} more" if len(found) > 4 else ""))


# ------------------------------------------------------------------ registry

REGISTRY: tuple[Upgrade, ...] = (
    Upgrade("unconfirmed-facts", "2026-10-15",
            "every fact in your profile confirmed by you, never guessed",
            _unconfirmed, "ask the person, at most three at the end of a session, and write "
            "each answer where its [CONFIRM] marker was", "question", "~1 min a fact",
            priority=2, needs="you"),
    Upgrade("required", "2026-10-15",
            "every setting the tools need and cannot default, written for you",
            _required, "/setup --section <the section that writes it>", "question", "~5 min",
            priority=1),
    Upgrade("boards", "2026-10-14",
            "the job boards that serve your market found, checked and built, so rounds search them",
            _boards, "/setup --section boards", "research", "~15 min a board",
            names=("search.PORTAL_RESEARCH", "search.PORTALS"),
            priority=2),
    Upgrade("portal-contract", "2026-10-15",
            "your own portals searched in every round, not only by hand",
            _contract, "/add-portal <the portal named>: check it takes the round's flags, "
            "then add `contract: 1`", "research", "~10 min a portal",
            priority=2),
    Upgrade("missing-portal", "2026-10-14",
            "no portal switched on that no longer exists",
            _unknown_portal, "/add-portal to build it again, or take it out of PORTALS",
            "question", "~2 min",
            priority=2),
    Upgrade("never-said", "2026-10-18",
            "no line in your profile telling a draft to use wording you said never to use",
            _never_said, "for each line listed, rewrite it so it no longer tells a draft to use "
            "the phrase: keep the fact, take the wording from the later rule that forbade it "
            "(python3 tools/learned.py list), change nothing else; one commit, and its git "
            "revert line in the reply", "research", "~2 min", priority=2),
    Upgrade("job-alerts", "2026-10-15",
            "your LinkedIn job alerts read into every round, if you want them",
            _alerts, "/setup --section boards; a no again is `python3 tools/profile_upgrades.py "
            "--no job-alerts`", "question", "~2 min",
            names=("search.JOB_ALERT_QUERY",),
            priority=3,
            needs="you",
            ask="Do you get LinkedIn job alerts by email? I can add those jobs to every search, "
                "reading only those emails, nothing else in your inbox. Yes, or not now?",
            why_ask="An alert often names a job before a search finds it."),
    Upgrade("learned-choices", "2026-10-15",
            "app improvements to things you chose, offered rather than imposed",
            _learned_choices, "ask each `python3 tools/learned.py offers` question; record the "
            "answer with `python3 tools/learned.py decide <n> keep|switch` and apply a switch",
            "question", "~1 min",
            priority=3,
            needs="you",
            ask="An update would change something you chose yourself. Want to hear the new way "
                "and decide, or keep yours for now?"),
    Upgrade("linkedin-plan", "2026-10-15",
            "connection notes and InMail sized to the LinkedIn account you actually have",
            _linkedin_plan, "write LINKEDIN_PLAN = \"free\" or \"premium\" in profile/networking.py "
            "from their answer", "question", "~1 min",
            names=("networking.LINKEDIN_PLAN",),
            priority=2,
            needs="you",
            ask="Do you pay for LinkedIn Premium?",
            why_ask="It decides how long your connection messages can be, and whether you can "
                    "message people you are not connected to."),
    Upgrade("people-sources", "2026-10-17",
            "people found where people in your field are actually named, not only by job title",
            _people_sources, "research and write PEOPLE_SOURCES in profile/networking.py as "
            "/setup's voice section says (its 'Where their people are named' step), and only "
            "that", "research", "~5 min",
            names=("networking.PEOPLE_SOURCES",),
            priority=2),
    Upgrade("rulings-review", "2026-10-17",
            "every posting still ruled out is ruled out by your rules as they are now",
            _rulings_review, "follow `python3 tools/exclude.py review`: judge each group "
            "against the four hard cuts (eligibility, language, a professional credential, a "
            "discipline the profile names as a different job) and the person's own "
            "deal-breakers in profile/CLAUDE.md. A group that is one of those: `exclude.py stamp "
            "\"<words>\" --basis rules`, with `--rests-on \"<part>\"` when it plainly rests on "
            "one part `exclude.py parts` lists, or `--basis person` where it is their own call. "
            "Any other "
            "(a salary, years, seniority, a degree, a score): `exclude.py lift \"<words>\" --why "
            "\"the current rules rank this, never cut it\"`. Report the count per group, and list "
            "the person's own calls so they can say if one has changed", "research", "~5 min",
            priority=2),
    Upgrade("alumni-text", "2026-10-18",
            "the plan's description of its alumni searches matches what they search",
            _alumni_text, "rewrite only the description of the alumni_employer entry in "
            "PEOPLE_SOURCES (profile/networking.py) to name the employers they have left, the "
            "one whose alumni reply most first (`python3 tools/network/sources.py` shows the "
            "order), and never the one they work at now; change nothing else", "edit", "~1 min",
            priority=4),
    Upgrade("public-holidays", "2026-10-19",
            "follow-ups that skip your country's public holidays, the way offices do",
            _public_holidays, "look up the person's country's public holidays (and their "
            "region's, from identity.location) for this year and next on its government's own "
            "page, and write them as ISO dates in profile/search.py PUBLIC_HOLIDAYS with the "
            "page's URL in a comment beside them; `python3 tools/holidays.py` then lists them",
            "research", "~5 min",
            names=("search.PUBLIC_HOLIDAYS",),
            conditional=True,
            priority=3),
    Upgrade("profile-never-say", "2026-10-19",
            "every phrase your own rules say never to write caught in every draft, not only "
            "when the drafting model remembers it",
            _profile_never_say, "python3 tools/learned.py adopt-profile-rules", "instant",
            command=("python3", "tools/learned.py", "adopt-profile-rules"),
            paths=("profile/learned.json",),
            priority=2),
    Upgrade("work-place", "2026-10-18",
            "told when a chat is in the wrong place for your settings, and where to go instead",
            _work_place, "ask its question with the session's other questions, as written; "
            "the trade-off `python3 tools/place.py ask` prints only if they ask why or are "
            "unsure; record the answer with `python3 tools/place.py record "
            "computer|phone|both` and give the one line it prints. Change no setting",
            "question", "~1 min",
            priority=4, needs="you",
            ask="Will you mostly use this on a computer, or on your phone or the web?",
            why_ask="Some things, like reading a profile in your own browser, only work in a "
                    "chat on your computer, so I set things up for where you will be."),
    Upgrade("ruling-parts", "2026-10-17",
            "a change to one of your rules puts back only the postings ruled out by that rule",
            _ruling_parts, "run `python3 tools/exclude.py cite`, then follow `python3 "
            "tools/exclude.py unnamed`: for each group, `exclude.py restamp \"<words>\" "
            "--rests-on \"<part>\"` where the reason plainly rests on one part `exclude.py parts` "
            "lists (a blocker row, a gate setting), and `--rests-on all` where it rests on more "
            "than one or it is not plain which. Never a part the reason does not plainly rest "
            "on: a wrong part keeps a posting out after the rule it really rests on changes. "
            "Report the count per part", "research", "~3 min",
            priority=3),
    Upgrade("connections-export", "2026-10-17",
            "every networking run starting from the people you already know",
            _connections_export, "save what they attach with `python3 tools/network/sources.py "
            "import-connections <file>` (a ZIP is read for Connections.csv alone, and the "
            "line it prints says so), or, if they would rather not, write "
            "CONNECTIONS_EXPORT = \"declined\" in profile/networking.py and run `python3 "
            "tools/profile_upgrades.py --no connections-export`. While the file is on its way, "
            "after giving the steps, offer once, in its words, what `python3 "
            "tools/network/sources.py while-you-wait` prints: one employer's 1st-degree "
            "people, pasted, go through `python3 tools/network/sources.py people-paste "
            "\"<employer>\" <file>`, and the steps for that, if they want them, are `python3 "
            "tools/claude_surfaces.py steps linkedin-people-at-employer`", "question", "~2 min",
            names=("networking.CONNECTIONS_EXPORT",),
            priority=3,
            needs="you",
            ask_version=2,
            changed="networking now finds people in bulk from any chat, and your own "
                    "connections are the first and strongest place it looks",
            ask="Want me to start from the people you already know on LinkedIn? That means "
                "requesting one file from LinkedIn, which arrives anything from ten minutes "
                "to a day later, and I'll walk you through it. Yes, or not now?",
            steps=lambda: "\n".join(_surface_steps("linkedin-connections")
                                    + ["I only read it. Nothing is sent to anyone."]),
            why_ask="People you already know can be messaged directly, with no connection "
                    "request, and they reply far more often than strangers."),
    Upgrade("profile-reads", "2026-10-17",
            "a note to each person built from their own profile, not a search snippet",
            _profile_reads, "write PROFILE_READS = \"browser\" or \"paste\" in "
            "profile/networking.py from their answer; \"paste\" again is also `python3 "
            "tools/profile_upgrades.py --no profile-reads`", "question", "~1 min",
            names=("networking.PROFILE_READS",),
            priority=2,
            needs="you",
            ask_version=2,
            changed="finding people no longer needs any read, and a read is now only of the best "
                    "ten a run finds, paced, in a chat on your computer",
            ask="Before writing to the best few people a search finds, should I read their "
                "LinkedIn profiles in your own browser? LinkedIn's terms forbid automated "
                "access, so that carries some risk to your account. Or you paste one or two. "
                "Which?",
            steps=lambda: ("Reading in your browser works in a chat on your computer in the Claude "
                           "desktop app. I read one profile at a time, at a person's pace, and "
                           "click nothing: the risk is lower with those limits, never nothing.\n"
                           "Pasting instead: open their profile, select all, copy, and paste it "
                           "here."),
            why_ask="A message that mentions something real about the person gets far more "
                    "replies than one built from a search result."),
    Upgrade("screen-flags", "2026-10-15",
            "postings from the wrong job family for you flagged, in your field's terms",
            _screen_flags, "/setup --section search", "question", "~5 min",
            names=("search.SCREEN_WRONG_FAMILY", "search.SCREEN_HOMONYMS"),
            priority=3),
    Upgrade("skills-headings", "2026-10-14",
            "a resume that renders, its Skills lines headed in your own words",
            _skills_headings, "/setup --section documents", "question", "~5 min",
            names=("skills.LABELS", "skills.MERGE"),
            priority=1),
    Upgrade("fit-missing-shape", "2026-10-14",
            "scoring that runs: each FIT_MISSING entry as (pattern, points, why)",
            _fit_missing_shape, "/setup --section search: rewrite each FIT_MISSING entry as "
            "(pattern, points, why); the example weighs one at -8", "edit", "~2 min",
            priority=1),
    Upgrade("networking-titles", "2026-10-14",
            "/network searching for your own colleagues and hiring managers, not a data team's",
            _networking, "/setup --section voice", "research", "~10 min",
            names=tuple(f"networking.{n}" for n in NETWORKING_NAMES),
            priority=1),
    Upgrade("level", "2026-10-14",
            "titles above or below your level ranked down in your terms",
            _level, "/setup --section search (and drop any junior-title bonus added to "
            "cancel the old built-in penalty)", "question", "~5 min",
            names=tuple(f"search.{n}" for n in LEVEL_NAMES),
            priority=2),
    Upgrade("bullet-themes", "2026-10-14",
            "resume bullets chosen for each posting by the words your field uses",
            _themes, "/setup --section history: add THEME_CUES in profile/bullets.py for "
            "each theme named", "research", "~10 min",
            names=("bullets.THEME_CUES", "bullets.CUE_WHOLE_WORD"),
            conditional=True,
            priority=3),
    Upgrade("scoring-vocabulary", "2026-10-14",
            "postings scored and gated on your field's words, not the example analyst's",
            _scoring, "/setup --section search: write the FIT_* and OPP_* vocabulary for "
            "your field, then score two or three invented postings", "research", "~20 min",
            priority=2),
    Upgrade("role-headings", "2026-10-14",
            "call-prep documents that carry your employers and their evidence",
            _role_headings, "/setup --section history: write each role heading as "
            "'Title - Employer (dates), City', then python3 tools/network/prep.py --all",
            "edit", "~2 min",
            priority=3),
    Upgrade("statement-templates", "2026-10-14",
            "resume summaries drafted from your own statement templates",
            _statement_templates, "/setup --section voice", "question", "~5 min",
            priority=3),
    Upgrade("interview-prep", "2026-10-14",
            "/interview working from your own STAR examples",
            _interview_prep, "/setup --section history", "question", "~10 min",
            priority=3),
    Upgrade("interview-tags", "2026-10-19",
            "each of your interview stories matched to the questions it answers",
            _interview_tags, "add one `Use for:` line to each STAR story listed, naming the "
            "interview questions it answers, read from the story's own words (setup.md's "
            "history section says how); change nothing else in the file", "edit", "~2 min",
            priority=2),
    Upgrade("profile-consistency", "2026-10-19",
            "your pay band, notice, sponsorship and permit answer said the same way everywhere",
            _profile_consistency, "python3 tools/profile_consistency.py, then ask the person "
            "which is right for each fact it lists and correct the other place(s); never pick "
            "for them", "question", "~2 min", priority=2, needs="you",
            ask="Your profile gives two different answers on something a recruiter checks "
                "first. Can I show you which, so you pick the right one?",
            why_ask="A form, a letter and an interview pack each read one of them, and a "
                    "recruiter remembers whichever they heard first."),
    Upgrade("process-postings", "2026-10-19",
            "every hiring process folder holds a job_posting.md, so your own checks stay green",
            _process_postings, "python3 tools/interview_pack.py postings", "instant",
            command=("python3", "tools/interview_pack.py", "postings"),
            paths=("documents/applications/*/job_posting.md",), priority=1, conditional=True),
    Upgrade("campaign-notes", "2026-10-19",
            "notes you kept by hand for an interview, before its prep document existed, "
            "folded into it so the next chat has them",
            _campaign_notes, "python3 -c \"import sys; sys.path[:0]=['tools','tools/network']; "
            "import json, interview_pack as p; print(json.dumps(p.handkept_notes(), indent=1))\""
            " lists each file and its prep document. For each, after a yes: build the document "
            "if it is missing (interview_pack.py pack \"<employer>\" --write); put each answer "
            "the file holds under its question in Your answers, and each decision in Notes, as "
            "it is written there; a fact about the person goes to profile/01-candidate-profile.md "
            "instead, and a stock answer to profile/07-interview-prep.md (interview_pack.py "
            "motive); then add to Notes \"- Folded in from <path> on <date>.\" Leave the file "
            "where it is", "question", "~5 min", priority=2, needs="you", conditional=True,
            ask="You kept notes for an interview before its prep document existed. Can I fold "
                "them into it, so the next chat has them?",
            why_ask="What was decided in them, like where you say you are based or why you "
                    "moved, is otherwise lost to the next chat."),
    Upgrade("dropped-rows", "2026-10-19",
            "people you set aside before writing, kept apart from real dead ends and easy to "
            "reopen",
            _dropped_rows, "python3 tools/network/state.py dropped-rows --apply", "instant",
            command=("python3", "tools/network/state.py", "dropped-rows", "--apply"),
            paths=("network_contacts.csv",), priority=2),
    Upgrade("read-break", "2026-10-19",
            "the pause between bursts of profile reads written in your profile, yours to change",
            _read_break, "add PROFILE_READ_BREAK_MINUTES = (5, 12) to profile/networking.py "
            "beside PROFILE_READS_PER_HOUR, with a comment: the break, in minutes, chosen at "
            "random in that range between bursts of browser reads; a shorter break raises the "
            "risk to their LinkedIn account. Change nothing else", "edit", "~1 min",
            names=("networking.PROFILE_READ_BREAK_MINUTES",), conditional=True, priority=3),
    Upgrade("move-and-area", "2026-10-19",
            "honest small talk prepared for an interview when you moved recently",
            _move_and_area, "read profile/01-candidate-profile.md and profile/CLAUDE.md; write "
            "person.json identity.moved as YYYY-MM or YYYY-MM-DD when they record when they moved "
            "in the last year, as \"by YYYY-MM-DD\" when the profile only confirms they were "
            "there by a date (\"in <city>, confirmed <date>\"), as \"just arrived\" when their "
            "own rule (learned.py brief interview) is to say only that, with no date, else "
            "\"none\"; and identity.area as the neighbourhood and city they give (else the "
            "location); invent nothing", "edit", "~1 min",
            names=("person.json:identity.moved", "person.json:identity.area"), priority=3),
    Upgrade("work-auth-employer", "2026-10-19",
            "recruiters hear your work authorization in your own employer-facing words",
            _work_auth_employer, "add WORK_AUTH[\"employer\"] to profile/networking.py: the "
            "sentence the profile says to use with employers and recruiters, in its own words "
            "(where it names none, the \"senior\" line), and extend WORK_AUTH_CLAUSE so it "
            "matches it; change nothing else", "edit", "~1 min",
            names=("networking.WORK_AUTH",), priority=2),
    Upgrade("country", "2026-10-14",
            "paper size, working week and market language that follow your country",
            _country, "/setup --section market", "question", "~1 min",
            names=("person.json:identity.country",),
            priority=3),
    Upgrade("market-week", "2026-10-14",
            "follow-up dates counted on your own working week",
            _market_week, "/setup --section market", "question", "~1 min",
            names=("search.WEEKEND",),
            conditional=True,
            priority=3),
    Upgrade("market-language", "2026-10-14",
            "internal-only vacancies cut and portals probed in your market's language",
            _market_language, "/setup --section market", "research", "~10 min",
            names=("search.INTERNAL_ONLY", "search.INTERNAL_ONLY_TITLE", "search.CANARY_QUERY"),
            conditional=True,
            priority=3),
    Upgrade("letter-language", "2026-10-14",
            "letters that greet and number pages in your document language",
            _letter_language, "/setup --section documents", "question", "~2 min",
            names=("person.json:documents.salutation_prefix", "person.json:documents.page_label"),
            conditional=True,
            priority=4),
)

# One upgrade per versioned method of the build (tools/build_versions.py): pending while
# a version this repo predates says what it made should be made again, and the repo
# holds something that method made. This is what carries a quiet improvement to
# everyone who set up before it: a better board search, a fixed prep document, a
# sharper eligibility question. Nobody has to know it happened. Methods a round or a
# /network run applies by itself (`by: "round"`, `by: "network"`) are not listed:
# there is nothing to run, and a chat that cannot do the work (rewriting a note needs
# the person read, which a cloud chat cannot do) was being told to do it.
def _method_check(name: str):
    def check() -> str:
        import build_versions as B
        late = B.behind(name)
        if not late or not B.applies(name):
            return ""
        # Said in the person's terms: what is better now. A version number means
        # nothing to them, and this line reaches them.
        return f"made the older way; now {late[-1][3]}"
    return check


def _method_upgrades() -> tuple:
    import build_versions as B
    out = []
    for name, m in B.METHODS.items():
        if m["by"] in ("round", "network"):
            continue
        rerun = [v for v in m["versions"] if v[2]]
        instant = m["by"] == "instant"
        run = m["run"] if instant else (
            f"{m['run']}, alone, on what is already there; then "
            f"python3 tools/build_versions.py record {name}")
        out.append(Upgrade(
            f"method-{name}", (rerun[-1][1] if rerun else B.FIRST_RELEASE), m["gives"],
            _method_check(name), run,
            "instant" if instant else "question" if m["by"] == "you" else "research",
            m.get("time", ""),
            command=("python3", "tools/build_versions.py", "redo", name) if instant else (),
            paths=(*m.get("paths", ()), f"profile/{B.RECORD}") if instant else (),
            priority=m["priority"],
            needs="you" if m["by"] == "you" else "nobody",
            ask=m.get("ask", "")))
    return tuple(out)


REGISTRY = REGISTRY + _method_upgrades()

# Profile names added since the first release that need no upgrade, and why. A
# new name goes here or in an upgrade's `names`; tests/test_profile_upgrades.py
# fails on one in neither.
SAFE_DEFAULTS: dict[str, str] = {
    # The reading dial and the limits it sets (tools/network/pace.py): absent, every one takes
    # the careful preset, which is the pace of the release before the dial, value for value.
    "networking.PROFILE_READ_RISK": "\"careful\": the pace before the dial existed; normal or "
    "fast only when the person writes it",
    "networking.PROFILE_PAGES_PER_HOUR": "4 list pages an hour at careful",
    "networking.PROFILE_PAGES_PER_DAY": "8 list pages a day at careful",
    "networking.PROFILE_LOADS_PER_HOUR": "8 page loads of any kind an hour at careful, the one "
    "shared cap there was before page kinds were counted apart",
    "networking.PROFILE_LOADS_PER_DAY": "15 page loads of any kind a day at careful, as before",
    "networking.PROFILE_READ_GAP_SECONDS": "45 to 240 seconds between pages at careful, as before",
    "networking.PROFILE_READ_GAP_MEDIAN": "90 seconds at careful, as before",
    "networking.PROFILE_READ_BREAK_AFTER": "a break after 3 to 7 pages at careful, as before",
    "networking.PROFILE_READ_DWELL_SECONDS": "20 to 60 seconds on a page read in full, as before",
    "networking.PROFILE_READ_CARD_DWELL_SECONDS": "20 to 60 seconds on a card at careful, the "
    "same as a full read, so nothing is shortened unless the person chooses it",
    "networking.PROFILE_READS_PER_RUN": "5 people on a day's short list at most, as before, and "
    "fewer when fewer requests can go that day",
    "networking.PROFILE_READ_UNPLACED": "2 people nothing has placed yet, as before",
    "networking.PROFILE_PASTE_TOP": "3 profiles offered for a paste, as before",
    "networking.PROFILE_READ_FRESH_DAYS": "a reading stands for 30 days, as before",
    "networking.PROFILE_READ_SKIP_SPARE": "3 reads beyond the requests left today, as before",
    "networking.PROFILE_READ_RAMP": "5 pages an hour until a clean day of reading, then 8: lower "
    "than before only on a first day, or after a signal",
    "networking.PROFILE_READ_BREAK_MINUTES": "a break of 5 to 12 minutes, chosen at random, "
                                             "between bursts of browser reads; shortening it "
                                             "raises the risk to their LinkedIn account, so only "
                                             "they set it",
    "networking.VARY_ABOUT_ME": "False: the line about themselves is theirs to repeat in every "
                                "note; True holds it to the same rule as anything else a batch "
                                "repeats",
    "search.SCRAPE_PAGES": "5 result pages a search in the cloud, 2 on their own computer, where "
                           "every request leaves from their own address",
    "search.SCRAPE_WORKERS": "10 searches at once in the cloud, 4 on their own computer",
    "search.SCRAPE_MAX_REQUESTS": "no cap in the cloud; 300 requests to each app portal a round on "
                                  "their own computer",
    "search.HOLIDAY_REGION": "read from identity.location (a province, a UK nation, a US "
                             "state); with none named, the country's common holidays",
    "search.HOURS_PER_YEAR": "2,080 hours, a full-time year of 40 hours a week, to read a band "
                             "stated by the hour as a year's pay; a market that works fewer "
                             "hours sets its own",
    "networking.PROFILE_READS_PER_DAY": "15 browser reads a day, and never more than the requests "
                                        "that can still go that day plus three; raising it raises "
                                        "the risk to their LinkedIn account",
    "networking.PROFILE_READS_PER_HOUR": "8 browser reads an hour with varied pauses around a "
                                            "minute and a half, the pace of writing to each",
    "networking.UNSUPPORTED_WHY": "the reason printed beside an unsupported-status finding in a "
                                  "resume or letter; unset, it says 'check it'",
    "networking.OPENALEX": "off: research papers find people only in fields that publish, and "
                           "/setup turns it on for one",
    "search.PORTAL_LOCATIONS": "defaults to every SCRAPE_LOCATION; /add-portal writes it "
                               "only when a board cannot read those names",
    "search.WORKDAY_INTERNAL_SITES": "the app drops Workday's 'Privileged' site already; a "
                                     "profile adds an employer's own internal site names "
                                     "once a round has shown one",
    "networking.GREETING": "'Hi' until the person says how they greet people",
    "networking.REFERRAL_LINE": "the app's sentence until the person says how they would ask",
    "networking.REFERRAL_CLOSE": "the app's sentence until the person says how they would ask",
    "networking.AUTHORITY_TITLE": "English management titles; a market in another language "
                                  "writes its own",
    "networking.SENIOR_IC_TITLE": "English seniority words; a market in another language, or a "
                                  "field where 'staff' is not senior, writes its own",
    "networking.HOME_COUNTRY": "discovery adds it to REGION_WORDS when present; the region "
                               "words alone decide without it",
    "networking.LINKEDIN_LIMITS": "the plan's own limits apply; set only for a plan with more "
                                  "InMail credits than Premium's",
    "search.OPP_SCALE": "computed from the profile's own opportunity weights when absent",
    "skills.MAX_PER_LINE": "six items a line unless the person wants another number",
    "skills.FAMILIES": "none: the app's own families of interchangeable tools apply "
                       "(tools/bridges.py); a field's own are added here",
    "skills.MIN_PER_CATEGORY": "one item makes a line worth printing; rarely changed",
    "networking.NOT_HIRING_REASON": "a neutral sentence any field reads correctly",
    "networking.NOT_HIRING_TITLES": "the built-in revenue titles, the same list every older "
                                    "repo used; None turns it off",
    "networking.SPAM_BULK_ROLES": "the built-in staffing-spam roles, the same list every older "
                                  "repo used",
    "person.json:documents.resume_pages": "one page, what every older repo printed; a long "
                                          "career sets two in /setup --section documents",
    "person.json:documents.section_order": "the standard order every older repo printed",
    "person.json:documents.letter_paper": "follows documents.paper, then the country",
    "search.MANAGES_PEOPLE": "no direct reports, what every older repo assumed; /setup "
                             "--section search sets it for someone who has managed people",
    "search.OPP_CONTRACT": "contract work docked, what every older repo did; /setup --section "
                           "search turns it off for someone who wants contract work",
}


def by_id(uid: str) -> Upgrade:
    for u in REGISTRY:
        if u.id == uid:
            return u
    raise KeyError(uid)


def pending() -> list[tuple[Upgrade, str]]:
    """[(upgrade, what is missing)] for every upgrade still pending, most urgent first."""
    out = []
    for u in sorted(REGISTRY, key=lambda u: (u.priority, u.added, u.id)):
        try:
            why = u.pending()
        except Exception as e:          # a check must never break a sync or a round
            why = ""
            print(f"profile upgrades: the {u.id} check failed ({type(e).__name__}: {e})",
                  file=sys.stderr)
        if why:
            out.append((u, why))
    return out


def block(rows: list[tuple[Upgrade, str]]) -> str:
    """What the sync prints. Each line is written to reach the person as it is: what they
    gain, and what they do (nothing, or one short question). The id in brackets is for
    Claude, never for them."""
    if not rows:
        return ""
    alone = [(u, why) for u, why in rows if u.needs == "nobody"]
    yours = [(u, why) for u, why in rows if u.needs != "nobody"]
    lines = [f"Improvements waiting for this repo ({len(rows)}):"]
    if alone:
        lines.append("  Claude applies these itself, in the background. Nothing for you to do:")
        for u, _why in alone:
            lines.append(f"    - {u.gives[:1].upper() + u.gives[1:]}.  [{u.id}]")
    if yours:
        lines.append("  These need you: one short question each, at the end of a session:")
        for u, why in yours:
            lines.append(f"    - {u.ask or why}  [{u.id}]")
            if why.startswith("you said no"):
                # Asked again: the person hears when they said no and what has changed.
                lines.append(f"      (asked again: {why})")
    # Said here as well as in CLAUDE.md: the session that runs the sync which brings
    # this in is still reading the CLAUDE.md from before it.
    lines.append("  Claude: "
                 + ("start a background agent now that follows .claude/commands/upgrade.md, "
                    "and carry on with the person's request. " if alone else "")
                 + "Never show an id, a version or the word upgrade. At the end of your reply "
                 + ("give one line per change it made, then " if alone else "")
                 + "ask at most three questions, each as written, short and alone. Only a yes "
                 "brings its steps and only \"why?\" its reason (`--plan` has both); a no gets "
                 f"\"{NO_REPLY}\", and `--no <id>` records it.")
    return "\n".join(lines)


def line(rows: list[tuple[Upgrade, str]] | None = None) -> str:
    rows = pending() if rows is None else rows
    if not rows:
        return ""
    alone = [u.id for u, _ in rows if u.needs == "nobody"]
    yours = [u.id for u, _ in rows if u.needs != "nobody"]
    parts = []
    if alone:
        parts.append(f"{len(alone)} Claude applies itself")
    if yours:
        parts.append(f"{len(yours)} short question{'s' if len(yours) != 1 else ''} for you")
    # The ids are for Claude (`--plan`): this line reaches the person.
    return "Improvements waiting: " + "; ".join(parts) + " (python3 tools/profile_upgrades.py)."


def plan(rows: list[tuple[Upgrade, str]] | None = None) -> list[dict]:
    """The pending upgrades as /upgrade works through them, most urgent first."""
    rows = pending() if rows is None else rows
    return [{"id": u.id, "priority": u.priority, "needs": u.needs, "ask": u.ask,
             "steps": u.steps() if u.steps else "", "why_ask": u.why_ask,
             "gives": u.gives, "why": why, "run": u.run, "cost": u.cost, "time": u.time}
            for u, why in rows]


# ------------------------------------------------------------------ instant

def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], text=True, capture_output=True, check=check)


def _changed() -> set[str]:
    out = _git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {ln[3:].split(" -> ")[-1].strip('"') for ln in out if ln.strip()}


# ------------------------------------------------------------------ which chat

# Several chats run against one repo at once, each in its own container, and each one
# syncs when it starts work. Every one of them used to find the same new upgrades, start
# the same background /upgrade and ask the same questions. The chat whose own sync
# brought the update in owns it. A chat that got the update by merging master, where
# that chat landed it, stays quiet until the owner has had OWNER_MINUTES to finish, then
# takes over whatever is still pending. It was two hours, and a person who had closed the
# other chats was told by the only one left to do nothing for two hours. A background
# /upgrade takes minutes; twenty is room for it, and `--take` hands them over at once
# when the person says no other chat is open.
OWNER_MINUTES = 20
SYNC_SUBJECT = "^Sync from the app: "
MERGE_MASTER = "git fetch origin master && git merge origin/master"


def _marker() -> str:
    d = _git("rev-parse", "--git-common-dir").stdout.strip()
    return os.path.join(d if os.path.isabs(d) else os.path.join(ROOT, d), "ljs-upgrade-owner")


MASTER = "refs/remotes/origin/master"


def _personal_repo() -> bool:
    """A person's own repo, with its profile at the root: the only place another chat's work
    can be waiting on master. The app (and its tests) never fetches from here."""
    return os.path.isdir(os.path.join(ROOT, "profile"))


def fetch_master() -> None:
    """origin/master as it is now, so what another chat landed is seen before this one starts
    the same work. Best effort: offline, the last fetch stands."""
    try:
        subprocess.run(["git", "-C", ROOT, "fetch", "-q", "origin", "master"],
                       capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def done_on_master() -> set[str]:
    """The upgrades another chat applied and landed on master that this chat does not hold
    yet: a `Profile upgrade: <id>` commit on origin/master that HEAD does not contain. Two
    chats once applied the same four upgrades and the same own-test fixes, and merging
    master conflicted on five files with the same intent."""
    if _git("rev-parse", "-q", "--verify", MASTER).returncode != 0:
        return set()
    out = _git("log", "--format=%s", f"HEAD..{MASTER}", "--grep=^Profile upgrade: ").stdout
    return {ln.split(":", 1)[1].strip() for ln in out.splitlines()
            if ln.startswith("Profile upgrade: ") and ln.split(":", 1)[1].strip()}


def _landed_elsewhere(sha: str, parents: list[str]) -> int:
    """When another chat's sync brought the same update onto master first, the time its sync
    was made; else 0. Both chats sync the same app commit, each in its own commit: the one
    on master owns it, whichever chat claimed it locally."""
    app = parents[1] if len(parents) > 1 else ""
    if not app or _git("rev-parse", "-q", "--verify", MASTER).returncode != 0:
        return 0
    if _git("merge-base", "--is-ancestor", sha, MASTER).returncode == 0:
        return 0                                    # this chat's own sync is the one landed
    if _git("merge-base", "--is-ancestor", app, MASTER).returncode != 0:
        return 0                                    # master does not carry this update yet
    for ln in _git("log", "--merges", "--format=%H %ct %P", f"--grep={SYNC_SUBJECT}",
                   MASTER).stdout.splitlines():
        f = ln.split()
        if len(f) >= 3 and app in f[2:]:
            return int(f[1])
    return 0


def owner_elsewhere(now: float | None = None) -> str:
    """"" when this chat owns the pending upgrades, else the time another chat's turn ends."""
    import time
    r = _git("log", "-1", "--format=%H %ct %P", f"--grep={SYNC_SUBJECT}", "HEAD").stdout.split()
    if len(r) < 2:
        return ""
    sha, when = r[0], int(r[1])
    try:
        with open(_marker(), encoding="utf-8") as f:
            if f.read().strip() == "taken " + sha:
                return ""                           # handed over by --take: no other chat open
    except OSError:
        pass
    # Checked before this chat's own claim: two chats that synced the same update a minute
    # apart each claimed it, and both applied it. The one whose sync reached master first
    # owns it.
    theirs = _landed_elsewhere(sha, r[2:])
    if theirs:
        ends = theirs + OWNER_MINUTES * 60
        if (now if now is not None else time.time()) >= ends:
            return ""
        return time.strftime("%H:%M UTC", time.gmtime(ends))
    try:
        with open(_marker(), encoding="utf-8") as f:
            if f.read().strip() == sha:
                return ""                           # this chat claimed it earlier
    except OSError:
        pass
    master = "refs/remotes/origin/master"
    if _git("rev-parse", "-q", "--verify", master).returncode != 0:
        return ""
    if _git("merge-base", "--is-ancestor", sha, master).returncode != 0:
        return ""                                   # this chat's own sync, not landed yet
    ends = when + OWNER_MINUTES * 60
    if (now if now is not None else time.time()) >= ends:
        return ""
    return time.strftime("%H:%M UTC", time.gmtime(ends))


def claim(taken: bool = False) -> None:
    """Mark the update this chat's sync brought in as this chat's, for its background
    /upgrade too: worktrees share the git directory the marker lives in. `taken` is the
    person's word that no other chat is open (--take), which outranks a sync another chat
    landed first."""
    r = _git("log", "-1", "--format=%H", f"--grep={SYNC_SUBJECT}", "HEAD").stdout.strip()
    if r:
        try:
            with open(_marker(), "w", encoding="utf-8") as f:
                f.write(("taken " if taken else "") + r + "\n")
        except OSError:
            pass


def run_instant(rows: list[tuple[Upgrade, str]]) -> list[str]:
    """Run each pending instant upgrade and commit it on its own. An upgrade that
    touches anything outside its own personal paths is undone, never committed."""
    from personal_paths import is_personal
    notes = []
    if _changed():
        return ["instant upgrades not run: the repo has uncommitted changes"]
    for u, _why in rows:
        if u.cost != "instant" or not u.command:
            continue
        r = subprocess.run(list(u.command), cwd=ROOT, text=True, capture_output=True, timeout=600)
        touched = sorted(_changed())
        stray = [p for p in touched
                 if not is_personal(p) or not any(fnmatch.fnmatch(p, g) for g in u.paths)]
        if r.returncode != 0 or stray:
            _git("checkout", "--", ".")
            _git("clean", "-fdq", "--", *touched) if touched else None
            notes.append(f"{u.id}: not applied ("
                         + (f"exit {r.returncode}" if r.returncode else
                            f"it touched {', '.join(stray[:3])}, outside its own files") + ")")
            continue
        if touched:
            _git("add", "-f", "--", *touched)
            c = _git("commit", "-q", "-m", f"Profile upgrade: {u.id}", "-m", u.gives)
            if c.returncode != 0:
                # No git identity in this session, a hook, anything: undo rather
                # than leave the person's files changed and uncommitted.
                _git("reset", "-q", "--", *touched)
                _git("checkout", "--", ".")
                _git("clean", "-fdq", "--", *touched)
                why = ((c.stderr or c.stdout).strip().splitlines() or ["no error text"])[-1]
                notes.append(f"{u.id}: not applied (the commit failed: {why[:120]})")
                continue
            notes.append(f"{u.id}: applied, {len(touched)} file(s), committed")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--line", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--after-sync", dest="after", action="store_true")
    mode.add_argument("--plan", action="store_true",
                      help="the pending upgrades as JSON, most urgent first (/upgrade reads it)")
    mode.add_argument("--check", metavar="ID",
                      help="one upgrade: 'done', or what is missing; exit 1 while pending")
    mode.add_argument("--take", action="store_true",
                      help="this chat applies the pending upgrades now: no other chat is open")
    mode.add_argument("--no", metavar="ID",
                      help="record the person's no to one question, dated: it is asked again "
                           "when the question changes or after REASK_DAYS")
    a = ap.parse_args(argv)
    if not person.exists():
        return 0                                    # the app, or a repo before /setup
    if a.no:
        p = record_no(a.no)
        print(f"profile_upgrades: their no to {a.no} kept in {os.path.relpath(p, ROOT)}; asked "
              f"again when the question changes or after {REASK_DAYS} days. Say only: "
              f"\"{NO_REPLY}\"")
        return 0
    if a.take:
        claim(taken=True)
        print("profile_upgrades: this chat owns the pending upgrades now; apply them "
              "(`profile_upgrades.py --plan`, then /upgrade in the background)")
        return 0
    if a.check:
        # Right before an upgrade starts, master is checked: another chat may have landed it.
        if _personal_repo():
            fetch_master()
        if a.check in done_on_master():
            print(f"done on master by another chat: merge it ({MERGE_MASTER}), never apply "
                  "it again here")
            return 0
        why = by_id(a.check).pending()
        print(why or "done")
        return 1 if why else 0
    if _personal_repo() and (a.after or a.plan):
        fetch_master()
    rows = pending()
    landed = done_on_master() if rows else set()
    if landed:
        # Applied by another chat and on master already: this chat merges them, never makes
        # them again, so the two never meet as a conflict.
        rows = [(u, why) for u, why in rows if u.id not in landed]
        if not a.plan:
            print(f"Profile upgrades: {len(landed)} already applied on master by another chat "
                  f"({', '.join(sorted(landed))}): merge master ({MERGE_MASTER}); where one of "
                  "their files conflicts, take master's copy, since an upgrade makes the same "
                  "change wherever it runs.")
    if a.after:
        import merge_state
        merge_state.install(ROOT)
        # The copy of sync_app.py that ran this sync may predate the own-tests check; this
        # file is always the one the sync brought in, so the check runs from here too.
        import sync_app
        sync_app.own_tests_after_sync(ROOT)
    elsewhere = owner_elsewhere() if rows and (a.after or a.plan or a.line) else ""
    if elsewhere:
        # Another chat brought this update in and is applying it: say so once, start
        # nothing and ask nothing. The instant ones still run below; they are the same
        # commit everywhere, so they merge cleanly.
        if a.plan:
            print("[]")
            return 0
        if a.after:
            for note in run_instant(rows):
                print(f"profile upgrades: {note}")
            rows = pending()
        if rows and a.line:
            print(f"Profile upgrades: {len(rows)} pending, being applied by another chat "
                  f"until {elsewhere}.")
        elif rows:
            print(f"Profile upgrades: {len(rows)} pending. They belong to another chat on this "
                  f"repo, the one whose sync brought this update in, until {elsewhere}: this chat "
                  f"got the update by merging master, or synced it after that chat's sync landed. "
                  f"Claude: start nothing and ask nothing about them; merge master first "
                  f"({MERGE_MASTER}). After {elsewhere} the next sync hands what is still pending "
                  "to this chat. If the person says no other chat is open, take them now: "
                  "python3 tools/profile_upgrades.py --take")
        else:
            print("Profile upgrades: none pending.")
        return 0
    if a.after:
        claim()
    if a.plan:
        import json
        print(json.dumps(plan(rows), indent=1))
        return 0
    if a.line:
        text = line(rows)
        if text:
            print(text)
        return 0
    if a.all:
        open_ = {u.id: why for u, why in rows}
        for u in sorted(REGISTRY, key=lambda u: (u.added, u.id)):
            state = f"PENDING: {open_[u.id]}" if u.id in open_ else "done"
            print(f"  {u.id:16} ({u.added}) [{u.cost}] {state}")
        return 0
    if a.after:
        for note in run_instant(rows):
            print(f"profile upgrades: {note}")
        rows = pending()
    text = block(rows)
    print(text or "Profile upgrades: none pending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
