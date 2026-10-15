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
    ask: str = ""


# ------------------------------------------------------------------ helpers

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
    return ""


def _linkedin_plan() -> str:
    if _missing("networking", "LINKEDIN_PLAN"):
        return ("nobody has asked whether you pay for LinkedIn Premium (profile/networking.py "
                "has no LINKEDIN_PLAN), so notes are kept to a free account's 200 characters "
                "and no InMail is drafted")
    return ""


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


def _interview_prep() -> str:
    if person.exists() and not person.exists("07-interview-prep.md"):
        return "profile/07-interview-prep.md is missing: /interview has no STAR examples of yours"
    return ""


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
    Upgrade("job-alerts", "2026-10-15",
            "your LinkedIn job alerts read into every round, if you want them",
            _alerts, "/setup --section boards", "question", "~2 min",
            names=("search.JOB_ALERT_QUERY",),
            priority=3,
            needs="you",
            ask="Do you get LinkedIn job alerts by email, and should every round read them? It re"
                "ads only those emails, nothing else in your inbox."),
    Upgrade("linkedin-plan", "2026-10-15",
            "connection notes and InMail sized to the LinkedIn account you actually have",
            _linkedin_plan, "write LINKEDIN_PLAN = \"free\" or \"premium\" in profile/networking.py "
            "from their answer", "question", "~1 min",
            names=("networking.LINKEDIN_PLAN",),
            priority=2,
            needs="you",
            ask="Do you pay for LinkedIn Premium? It decides how long a connection note can be "
                "and whether InMail is there at all."),
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
# sharper eligibility question. Nobody has to know it happened. Methods a round
# applies by itself (`by: "round"`) are not listed: there is nothing to run.
def _method_check(name: str):
    def check() -> str:
        import build_versions as B
        late = B.behind(name)
        if not late or not B.applies(name):
            return ""
        have = B.recorded().get(name, 1)
        return (f"your {name} was made by version {have}; version "
                f"{late[-1][0]} does it better: {late[-1][3]}")
    return check


def _method_upgrades() -> tuple:
    import build_versions as B
    out = []
    for name, m in B.METHODS.items():
        if m["by"] == "round":
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
    "search.PORTAL_LOCATIONS": "defaults to every SCRAPE_LOCATION; /add-portal writes it "
                               "only when a board cannot read those names",
    "search.WORKDAY_INTERNAL_SITES": "the app drops Workday's 'Privileged' site already; a "
                                     "profile adds an employer's own internal site names "
                                     "once a round has shown one",
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
    if not rows:
        return ""
    alone = [(u, why) for u, why in rows if u.needs == "nobody"]
    yours = [(u, why) for u, why in rows if u.needs != "nobody"]
    lines = [f"Profile upgrades pending ({len(rows)}):"]
    if alone:
        lines.append("  Claude applies these itself, in the background (/upgrade), "
                     "most urgent first:")
        for u, why in alone:
            lines.append(f"    {u.id:20} {u.gives}")
            lines.append(f"    {'':20}   why: {why}")
    if yours:
        lines.append("  These need you (asked at the end of a session, a few at a time):")
        for u, why in yours:
            lines.append(f"    {u.id:20} {u.ask or why}")
    # Said here as well as in CLAUDE.md: the session that runs the sync which brings
    # this in is still reading the CLAUDE.md from before it.
    lines.append("  Claude: "
                 + ("start a background agent now that follows .claude/commands/upgrade.md, "
                    "and carry on with the person's request. " if alone else "")
                 + "At the end of your reply, give the person "
                 + ("its one line per change and " if alone else "")
                 + "at most three of the questions" + (" it returns." if alone else " above."))
    return "\n".join(lines)


def line(rows: list[tuple[Upgrade, str]] | None = None) -> str:
    rows = pending() if rows is None else rows
    if not rows:
        return ""
    alone = [u.id for u, _ in rows if u.needs == "nobody"]
    yours = [u.id for u, _ in rows if u.needs != "nobody"]
    parts = []
    if alone:
        parts.append(f"{len(alone)} Claude applies itself ({', '.join(alone)})")
    if yours:
        parts.append(f"{len(yours)} need{'s' if len(yours) == 1 else ''} you ({', '.join(yours)})")
    return "Profile upgrades: " + "; ".join(parts) + "."


def plan(rows: list[tuple[Upgrade, str]] | None = None) -> list[dict]:
    """The pending upgrades as /upgrade works through them, most urgent first."""
    rows = pending() if rows is None else rows
    return [{"id": u.id, "priority": u.priority, "needs": u.needs, "ask": u.ask,
             "gives": u.gives, "why": why, "run": u.run, "cost": u.cost, "time": u.time}
            for u, why in rows]


# ------------------------------------------------------------------ instant

def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], text=True, capture_output=True, check=check)


def _changed() -> set[str]:
    out = _git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {ln[3:].split(" -> ")[-1].strip('"') for ln in out if ln.strip()}


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
    a = ap.parse_args(argv)
    if not person.exists():
        return 0                                    # the app, or a repo before /setup
    if a.check:
        why = by_id(a.check).pending()
        print(why or "done")
        return 1 if why else 0
    rows = pending()
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
