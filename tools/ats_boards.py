#!/usr/bin/env python3
"""Employer job boards, read straight from the ATS, keyed by employer.

The biggest input gap in a search is source coverage. A job portal or two is
enabled, and the profile names the target employers that the pipeline would
otherwise have no way to act on: they are a preference stated in prose, and a
keyword search on a portal is a poor proxy for "show me everything this
employer has open in my city".

The reading is openroles (tools/openroles/, vendored, never edited here), the
library this file grew into: one reader per applicant tracking system, polite by
construction (robots.txt, two requests per host, a host's Crawl-delay), and the
place every fix to a reader is made, once. Every system openroles reads is read
here, with no list of them kept in this file: `python3 tools/openroles/cli.py
--help` names them, and openroles' README says what each costs in requests.

What stays here is what is the search's own: which places the person can work in
(`_wanted`, `_choose`), which posting bodies are worth a request where the listing
has none (Workday, Rippling, Polymer: the free title and location gates decide),
which careers-site pages are already ruled out, the country a Workday board is
narrowed to, the row every later stage reads, and the map of employers
(profile/boards.py).

Workday is the one large employers run: they are often visible only through a
portal until their board is read here, so a posting the portal ranked low or
never indexed did not exist for the search, and those are often the best-paid
roles on the list.

WHAT THIS IS NOT. It is not complete and does not pretend to be. Employers on
SuccessFactors, Oracle and the other systems openroles' README lists as not
supported publish no open endpoint, so they still come through the portals,
unless their careers site publishes its jobs for search engines, which
`careersite` reads. Some Workday employers' robots.txt disallows the very board
this would read, and SmartRecruiters' robots.txt closes its posting API to every
crawler except LinkedIn's: see REFUSED. This adds a source; it does not replace one.

ROBOTS. A board is read only where the host's robots.txt allows it, re-checked
on every run, because a policy is a fact that changes and a board added last
quarter should stop being read the week its owner says no. Where the vendor
documents the endpoint as a public API an explicit Disallow stops the read;
elsewhere (Workday, Ashby, Homerun, ClearCompany, a careers site) the policy
must be readable and must allow it. Each reader in tools/openroles/providers/
says which, and quotes the vendor.

THE MAP IS THE WORK. An employer is only here once its token has been verified
to return jobs, because a wrong token returns an empty list that is
indistinguishable from an employer with no openings, which is the exact failure
the scrape canary exists to catch. `--probe` re-checks every token and reports
the ones that have gone quiet, so the map can be repaired rather than rotting
into silence. It re-checks the refused ones too, and says when a rule lifts.

Usage:
    python3 tools/ats_boards.py --out ats.json
    python3 tools/ats_boards.py --find "<Employer>"           # or its careers page URL
    python3 tools/ats_boards.py --probe
    python3 tools/ats_boards.py --add greenhouse <board>    # verify then print
    python3 tools/ats_boards.py --add personio <name>        # any system openroles reads
    python3 tools/ats_boards.py --add careersite careers.<employer>.com
    python3 tools/ats_boards.py --add workday https://<tenant>.wd3.myworkdayjobs.com/<Site>
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import places as _places  # noqa: E402
import openroles  # noqa: E402
from openroles import BoardError  # noqa: E402
from openroles.models import systems as _systems  # noqa: E402
from openroles.providers import READERS  # noqa: E402
from openroles.providers import workday as _wd  # noqa: E402
try:
    from prefilter import location_verdict, title_verdict  # noqa: E402
    NO_PROFILE = False
except person.NoProfile:
    # /setup looks for each target employer's board (`--find`) while the profile is still
    # being written, in parallel with the rest. With no profile there are no places or
    # titles to judge against: every role counts, and --find says none was judged. It
    # crashed with a NoProfile traceback before (2026-10-25).
    NO_PROFILE = True

    def location_verdict(location, title=""):  # noqa: D103
        return ("PASS", "no profile yet")

    def title_verdict(title):  # noqa: D103
        return ("PASS", "no profile yet")

UA = "last-job-search/1.0 (personal job search; contact via GitHub)"
# Checked for every agent a rule could be written for: everyone, the token
# WebFetch sends (robots_check reads the same pair), and this tool's own. An
# agent with no group of its own falls back to "*", so "*" goes first and a
# refusal names the rule that was actually written.
ROBOTS_AGENTS = ("*", "Claude-User", "last-job-search")
openroles.configure(user_agent=UA, robots_agents=ROBOTS_AGENTS)

# ------------------------------------------------------------ what no reader sees
#
# openroles leaves out of a board's text what a browser never shows (a hidden element, a
# comment, a script) since 0.4.0, so the words come from its rule alone. What it took out
# is still worth saying: a posting that hides text from its readers may be talking to a
# machine, and the shortlist warns about it (row["posting_guard"], tools/hydrate.py's
# words). So the converter each reader calls is wrapped to note what hydrate finds hidden
# in the markup, and nothing else: openroles is never edited here, and each reader looks
# the converter up by name when it runs.
import openroles.models as _or_models  # noqa: E402
import hydrate as _hydrate  # noqa: E402

_TO_TEXT = _or_models.html_to_text


class _Cleaned(str):
    """A board's text that had something hidden taken out of its markup, and what."""
    found: dict = {}


def shown_text(content) -> str:
    """openroles' text of a board's HTML, noting what was hidden in it."""
    s = content if isinstance(content, str) else ""
    for _ in range(3):                     # as html_to_text reads it: some boards encode twice
        un = html.unescape(s)
        if un == s:
            break
        s = un
    found = _hydrate.strip_hidden(s)[1] if "<" in s else {}
    if not found:
        return _TO_TEXT(content)
    text = _Cleaned(_TO_TEXT(content))
    text.found = found
    return text


for _name, _mod in list(sys.modules.items()):
    if ((_name == "openroles.models" or _name.startswith("openroles.providers."))
            and getattr(_mod, "html_to_text", None) is _TO_TEXT):
        _mod.html_to_text = shown_text

# The map is the person's: profile/boards.py names the employers, the token
# each one's careers page reads, and the boards checked and refused. Every
# token there was verified to return in-range jobs, and `--probe` re-checks
# them. A wrong token returns an empty list that is indistinguishable from an
# employer with no openings, which is the exact failure the scrape canary
# exists to catch, so nothing goes in unverified.
_B = person.module("boards") if person.exists("boards.py") else None
BOARDS: dict[str, tuple[str, str]] = dict(getattr(_B, "BOARDS", {}))

# Boards checked and deliberately not read, with the rule that says no. A
# Workday board whose robots.txt disallows its careers site is refused even
# though the /wday/cxs/ API is not named in the file: it is the same board
# through a different URL, and reading it would be working around a Disallow
# rather than honouring it. `--probe` re-checks these so the day a rule lifts is noticed.
REFUSED: dict[str, tuple[str, str, str]] = dict(getattr(_B, "REFUSED", {}))


# A whole ATS refused: api.smartrecruiters.com/robots.txt reads
# "User-agent: LinkedInBot / Allow: /v1/companies/ / User-agent: * /
# Disallow: /". Its posting API is documented as public and it is still closed
# to every crawler but one, so there is no SmartRecruiters reader here.
REFUSED_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "smartrecruiters": ("api.smartrecruiters.com", "/v1/companies/example/postings",
                        "robots.txt: User-agent: * / Disallow: / (only LinkedInBot "
                        "is allowed /v1/companies/)"),
}

# Where the candidate can actually work, as places an ATS location string may
# name: profile/boards.py's PLACES. Matched against free text that varies
# wildly by employer ("Remote - <city>", "<city>, <region> - <country>;
# <city>, ...", "US / <country>"), so it is a list of places, not a parser.
# No profile list means nothing is wanted but a bare "Remote".
PLACES = getattr(_B, "PLACES", None) or re.compile(r"(?!x)x")

# And the places the person's search already names: the home metro and the home
# country (profile/search.py LOCATION, through tools/places.py). PLACES alone missed
# them: a board's posting in a metro town PLACES did not list ("Bolton", "Wigan")
# never reached the round, though prefilter passes it.
_METRO_RX = (re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(m) for m in _places.METRO), re.I)
             if _places.METRO else re.compile(r"(?!x)x"))

# A location that says the job is remote and names no geography at all.
# "Remote" on its own is kept; "Remote - <city>" is caught by PLACES above and
# "Remote - SF Bay Area" is caught by neither, which is the point.
BARE_REMOTE = re.compile(r"^\W*(fully |100% )?remote\W*$", re.I)
# A label's own leading "Remote -", so anchoring a bare "Remote" never says it twice.
_REMOTE_WORD = re.compile(r"^\W*(?:fully |100% )?remote\W*(?:[-:(]\W*)?", re.I)

from hydrate import BODY_CAP  # noqa: E402  the one cap on a posting's body

# How much of a Workday board is read. A board up to PAGE_ALL_MAX postings (after
# narrowing it to the profile's country with the board's own facet) is paged whole and
# filtered here. Anything bigger is searched instead, once per title variant in
# scrape_wide.QUERIES, so a round does not page through a thousand branch and
# call-centre roles to find the analytics ones, and a board past Workday's 2,000 cap is
# read at all. Measured on one large national board: paging found nearly everything the
# title search found past the title and location gates, and the two cost about the
# same counting the bodies, so searching is not a saving at that size; it is aimed.
PAGE_ALL_MAX = 1000

# The country a Workday board is narrowed to: (Workday's facet value id, the
# value's name), from profile/boards.py. Workday's identifier for a country is
# the same on every tenant seen; the facet's own name is not, so the facet is
# found by its value. No country set means no narrowing, and the location
# filter does it all.
COUNTRY_ID, COUNTRY_NAME = getattr(_B, "WORKDAY_COUNTRY", ("", ""))


def __getattr__(name: str):
    """A name not here (PEP 562). A private one is named for what it is: a person's test
    that reached into this module's private parts broke by the dozen when 3.5.0 moved the
    reading into openroles, and the bare AttributeError told nobody what to do."""
    hint = (". Names starting with an underscore are private to the app and change between "
            "releases (3.5.0 moved the board reading into tools/openroles). A person's own test "
            "fakes a board with tools/offline_boards.py; `python3 tools/sync_app.py --own-tests` "
            "says what to do." if name.startswith("_") and not name.startswith("__") else "")
    raise AttributeError(f"module 'ats_boards' has no attribute {name!r}{hint}")


# ------------------------------------------------------------------ robots

def robots_allows(host: str, paths) -> tuple[bool, str]:
    """(may these paths be read, why), from the host's robots.txt, as openroles reads it."""
    return openroles.robots_allows(host, paths)


# ------------------------------------------------------------------ location

def _wanted(location: str) -> bool:
    """Could the candidate actually take this job. Positive evidence only.

    A wanted place wins outright, because a multi-site posting that includes
    the candidate's city is one they can take whatever else it lists: "US /
    <country>" and "<city>; New York" are both yes.

    Everything else is out, and the default is deliberately the strict one.
    Two versions of this filter defaulted to keeping. The first matched a bare
    "remote" and excluded only "Remote - US", which let "Remote Poland" and
    "Remote Spain" through. The second kept anything that did not name a
    foreign place, which is worse: one employer writes its locations as
    "Hybrid", "Distributed" and "In-Office" with the city recorded elsewhere,
    and contributed hundreds of postings to a round, none of which could be
    shown to be anywhere the candidate could work.

    A world-city blocklist would have to be exhaustive to work, and it would
    rot. A whitelist is wrong only in the direction that costs recall, on one
    source among several, and a posting skipped here still reaches the round
    through LinkedIn.
    """
    loc = (location or "").strip()
    if not loc:
        return False
    if NO_PROFILE:                 # no places to judge against yet: every role counts
        return True
    return bool(PLACES.search(loc) or _METRO_RX.search(loc)
                or _places.HOME_COUNTRY_RX.search(loc.lower()) or BARE_REMOTE.match(loc))


_RANK = {"PASS": 0, "FLAG": 1, "FAIL": 2}


def _choose(labels, title: str = "", remote: bool = False) -> tuple[str, str]:
    """(the locations the candidate could take the job in, as one string, their verdict).

    A multi-site posting is one they can take if any site is one they can work
    from, but prefilter reads the location as ONE string, and a string that
    names two places reads as the worse of them. A role posted in the home city
    and in a flagged one is, joined, FLAGged as the second and fit.py takes
    points it should not. "<home city>; New York, New York" is worse, it FAILs
    as a US on-site role. So every site is judged alone with prefilter's own
    gate, and only the best-judged ones are kept. ("", "FAIL") when none of
    them is a wanted place at all, which is `_wanted`'s positive-evidence rule
    unchanged. Every board's postings go through here: a Greenhouse office or a
    Lever second location is a site like any other.

    `remote` is the ATS's own flag. prefilter already reads "Remote" as
    beating a nominal office; this only makes sure the word is in the string.
    """
    cands: list[str] = []
    for lab in labels:
        lab = " ".join(str(lab or "").split())
        if not lab:
            continue
        if remote and "remote" not in lab.lower():
            lab = f"Remote - {lab}"
        if lab not in cands:
            cands.append(lab)
    # A bare "Remote" listed beside places none of which the gate passes is remote in
    # those places: "Remote" with offices in two US cities is a US remote role, and
    # judged alone it read as remote from anywhere. It is kept, anchored, for prefilter's
    # gate to read ("remote but US-anchored" is a flag, not a cut). The gate decides, not
    # PLACES, which can match a foreign city by a word it shares with a home one.
    others = [c for c in cands if not BARE_REMOTE.match(c)]
    anchored = ""
    if (others and len(others) < len(cands)
            and not any(location_verdict(c, title)[0] == "PASS" for c in others)):
        where = [_REMOTE_WORD.sub("", c) or c for c in others]
        anchored = "Remote - " + "; ".join(dict.fromkeys(where))
        cands = [anchored if BARE_REMOTE.match(c) else c for c in cands]
        cands = list(dict.fromkeys(cands))
    wanted = [c for c in cands if c == anchored or _wanted(c)]
    if not wanted:
        return "", "FAIL"
    judged = [(_RANK[location_verdict(c, title)[0]], c) for c in wanted]
    best = min(r for r, _ in judged)
    keep = [c for r, c in judged if r == best]
    # "Toronto" beside "Toronto, ON" is one place written twice: the fuller one stays.
    keep = [c for c in keep if not any(o != c and o.lower().startswith(c.lower() + ",") for o in keep)]
    joined = "; ".join(keep)
    if len(keep) > 1 and all(k.startswith("Remote - ") for k in keep):
        joined = "Remote - " + "; ".join(k[len("Remote - "):] for k in keep)
    # Two sites that each pass can still read worse joined, so the string that
    # leaves here is checked the way prefilter will read it.
    if len(keep) > 1 and _RANK[location_verdict(joined, title)[0]] > best:
        joined = keep[0]
    return joined, next(v for v, r in _RANK.items() if r == best)


# ------------------------------------------------------------------ rows

def _desc(job) -> str | None:
    """The body, with any posted pay as a line text_screen's salary reader recognises.

    The pay is the employer's own structured field, and the body is cut first so the
    cap can never cut it off."""
    body = str(job.description or "").strip()
    if job.compensation:
        line = f"Compensation (as posted on the board): {job.compensation}"
        body = f"{body[:BODY_CAP - len(line) - 2]}\n\n{line}".strip()
    return body[:BODY_CAP] or None


def _row(employer: str, job, location: str, desc: str | None) -> dict:
    row = {
        "id": job.id,
        "title": job.title,
        "company": employer,
        "url": job.url,
        "location": location,
        "date": job.posted,
        "portal": job.ats,
        "desc": desc,
        "deadline": job.deadline or None,
    }
    found = getattr(job.description, "found", None)
    if found and desc:
        row["posting_guard"] = _hydrate.said(found)
    return row


# A posting's own location that names no place: the job is wherever its offices are.
_NOT_A_PLACE = re.compile(r"^\s*(?:hybrid|remote|anywhere|flexible|multiple locations|various"
                          r"(?: locations)?|(?:[a-z]+\s+)*time\s*zones?|(?:utc|gmt)\s*[+-]?\s*\d*)\s*$",
                          re.I)
# Systems whose extra places are internal office tags, not sites the job is open at.
OFFICE_TAGS = frozenset({"greenhouse", "gem"})


def _labels(job) -> list[str]:
    """Where a posting can be done. A Greenhouse posting's offices are the employer's own
    tags: Figma filed a role open in San Francisco, New York or remote in the United States
    under "Canada" and "US", and the office tag passed it as a Canada role (2026-10-30). So a
    posting that names its own place is judged by that place, and its offices only where it
    names none ("Hybrid", a time zone, nothing)."""
    own = str(job.location or "").strip()
    if getattr(job, "ats", "") in OFFICE_TAGS and own and not _NOT_A_PLACE.match(own):
        return [own]
    return list(job.locations) or ([own] if own else [])


def _worth(job) -> bool:
    """Is a posting's body worth a request: a title prefilter's gate passes, in a place
    its gate does not fail. The free gates, asked before anything is spent. With no
    profile yet nothing can be judged, so no body is worth a request."""
    if NO_PROFILE or title_verdict(job.title)[0] == "FAIL":
        return False
    location, verdict = _choose(_labels(job), job.title, job.workplace == "remote")
    return bool(location) and verdict != "FAIL"


# Systems whose listing carries no body: each posting's own record is a request, asked
# only for the postings `_worth` passes (openroles caps them a board besides).
DETAILED = frozenset({"rippling", "polymer"})


def _rows(employer: str, jobs, skip=()) -> list[dict]:
    """The rows in range, every posting judged at each place it lists."""
    out = []
    for job in jobs:
        if job.id in skip:
            continue
        location, _ = _choose(_labels(job), job.title, job.workplace == "remote")
        if location:
            out.append(_row(employer, job, location, _desc(job)))
    return out


def _read(kind: str):
    """A reader for one ATS: (employer, token) -> (rows in range, why it returned none)."""
    def read(employer: str, token: str) -> tuple[list[dict], str | None]:
        report: dict = {}
        try:
            if kind in DETAILED:
                jobs = READERS[kind].fetch(token, details=_worth, report=report)
            else:
                jobs = READERS[kind].fetch(token)
        except BoardError as e:
            return [], str(e).split(": ", 1)[-1]
        failed = report.get("detail_errors") or {}
        out = _rows(employer, jobs, failed)
        note = (f"{len(failed)} of {report.get('details_asked', 0)} posting bodies failed "
                f"({_summarise(failed.values())}) and those postings were left out") if failed else None
        return out, note
    read.__name__ = kind
    return read


# ---------------------------------------------------------------- careersite

def _queries():
    """The round's title variants (scrape_wide.QUERIES), or None with no profile yet.

    scrape_wide reads the profile when it is imported, so --find for a Workday board or a
    careers site crashed with no profile, the case NO_PROFILE above exists for. With no
    titles to search by, a board is read whole and a careers site's pages are not
    narrowed."""
    if NO_PROFILE:
        return None
    from scrape_wide import QUERIES
    return QUERIES


# Job pages read from one careers site a round. Each is a request at the pace the site's
# robots.txt asks, so a site that asks for ten seconds costs a few minutes at this cap,
# and the next round moves on to the pages this one did not reach.
CAREERSITE_PAGES = 20


def careersite(employer: str, token: str, queries=None,
               skip=None) -> tuple[list[dict], str | None]:
    """A careers site with no job API, read from the job pages it publishes for search
    engines. Pages whose address names a job none of the title variants asks for are not
    read, nor pages the search has already ruled out (`skip`, given the page's URL)."""
    if queries is None:
        queries = _queries()
    report: dict = {}
    ruled: list[str] = []

    def skipped(url: str) -> bool:
        if skip and skip(url):
            ruled.append(url)
            return True
        return False
    try:
        jobs = READERS["careersite"].fetch(token, queries=queries, limit=CAREERSITE_PAGES,
                                           skip=skipped, report=report)
    except BoardError as e:
        return [], str(e).split(": ", 1)[-1]
    out = _rows(employer, jobs)
    errors = report.get("page_errors") or {}
    notes = []
    if errors:
        notes.append(f"{len(errors)} of {report.get('pages_read', 0)} pages had no posting "
                     f"({_summarise(errors.values())})")
    rest = report.get("pages_listed", 0) - report.get("pages_read", 0) - len(ruled)
    if rest > 0:
        notes.append(f"{rest} more pages listed, read in later rounds")
    return out, "; ".join(notes) or None


def _ruled_out_pages(seen: str | None = None, keep_ruled_out: bool = False,
                     today: dt.date | None = None):
    """A function from an employer to its careers-site skip: has this search already ruled
    out the page at a URL, by the URL or the employer? No request is spent on one that it
    has (prefilter's own check, read before the fetch).

    Built once for the round, from the round's own seen file and its --no-seen-read
    (`keep_ruled_out`: no past ruling is read, only the live holds). It was rebuilt for
    every careers-site employer from the repo's seen file, so a round that asked to judge
    everything again still never fetched a page it had once ruled out."""
    try:
        from prefilter import already_ruled_out
        from throttle import SEEN
        ruled = already_ruled_out(seen or SEEN, keep_ruled_out, today)
    except Exception:                      # no seen file yet: nothing is ruled out
        return lambda employer: None

    def for_employer(employer: str):
        return lambda url: bool(ruled({"url": url, "company": employer, "title": ""}))
    return for_employer


# ------------------------------------------------------------------- workday

def workday_board(token: str) -> tuple[str, str, str] | None:
    """(host, tenant, site) for a "tenant.wdN/Site" token, or None."""
    m = _wd.TOKEN.match(token or "")
    if not m:
        return None
    return f"{m['tenant']}.{m['dc']}.myworkdayjobs.com", m["tenant"], m["site"]


def workday_token(text: str) -> str | None:
    """A map token from a token or from a careers-site URL pasted as seen (either host)."""
    return _wd.token_from(text)


def _summarise(errors) -> str:
    counts: dict[str, int] = {}
    for e in errors:
        counts[e] = counts.get(e, 0) + 1
    return ", ".join(f"{n}x {e}" for e, n in sorted(counts.items(), key=lambda x: -x[1])[:3])


def workday(employer: str, token: str, queries=None,
            today: dt.date | None = None) -> tuple[list[dict], str | None]:
    """A Workday board, reading a posting's body only where the free gates say it could
    matter: a title prefilter's gate passes, in a place its gate does not fail. A posting
    that fails either is still emitted, without a body, so prefilter drops it with the
    reason and the funnel stays readable. A listing that says only "3 Locations" names no
    place: its body is fetched to find out where when the title is worth it, and the
    posting is skipped when it is not. A body that would not fetch leaves its posting out,
    with a note, rather than send it to the scorer with a title alone."""
    if not workday_board(token):
        return [], f"not a Workday token (want tenant.wdN/Site): {token!r}"
    if queries is None:
        queries = _queries()
    asked: set = set()

    def worth(job) -> bool:
        if NO_PROFILE:              # nothing can be judged, so no body is worth a request
            return False
        title_ok = title_verdict(job.title)[0] != "FAIL"
        if _wd.more_places(job):
            ok = title_ok
        else:
            location, verdict = _choose([job.location], job.title, job.workplace == "remote")
            ok = bool(location) and title_ok and verdict != "FAIL"
        if ok:
            asked.add(job.id)
        return ok

    report: dict = {}
    try:
        jobs = _wd.fetch(token, country=COUNTRY_NAME, country_id=COUNTRY_ID, details=worth,
                         today=today or dt.date.today(), large_queries=queries,
                         page_all_max=PAGE_ALL_MAX, report=report, strict_country=False)
    except BoardError as e:
        return [], str(e).split(": ", 1)[-1]
    failed = report.get("detail_errors") or {}
    rows = []
    for job in jobs:
        if job.id in failed:
            continue
        if job.id in asked:
            location, _ = _choose(_labels(job), job.title, job.workplace == "remote")
            if location:
                rows.append(_row(employer, job, location, _desc(job)))
        elif NO_PROFILE or not _wd.more_places(job):
            location, _ = _choose([job.location], job.title, job.workplace == "remote")
            if location:
                rows.append(_row(employer, job, location, None))
    notes = []
    if report.get("listing_errors"):
        errs = report["listing_errors"]
        notes.append(f"{len(errs)} listing page(s) failed ({_summarise(errs)})")
    if failed:
        notes.append(f"{len(failed)} of {report.get('details_asked', 0)} posting bodies failed "
                     f"({_summarise(failed.values())}) and those postings were left out")
    return rows, "; ".join(notes) or None


# One reader per system openroles reads, taken from openroles rather than listed here.
FETCH = {kind: _read(kind) for kind in READERS}
FETCH["workday"] = workday
FETCH["careersite"] = careersite
greenhouse, lever, ashby = FETCH["greenhouse"], FETCH["lever"], FETCH["ashby"]


def fetch_all(boards=None, workers: int = 16, notes: dict | None = None,
              today: dt.date | None = None, seen: str | None = None,
              keep_ruled_out: bool = False) -> tuple[list[dict], dict[str, str]]:
    """(rows, {employer: why it returned nothing}) across every board.

    `notes`, when given, collects what a board that DID return rows left out,
    a Workday body that would not fetch, which is worth saying and is not the
    same thing as a board gone quiet. The worker count is across boards; the
    politeness budget per host is held by openroles. `today` dates Workday's
    "Posted N days ago", so a replayed round (scrape_wide.py --today) dates its
    postings from its own day and not the day it is replayed. `seen` and
    `keep_ruled_out` are the round's seen_jobs.json and its --no-seen-read, for the
    careers-site pages already ruled out.
    """
    boards = BOARDS if boards is None else boards
    rows: list[dict] = []
    quiet: dict[str, str] = {}
    pages = (_ruled_out_pages(seen, keep_ruled_out, today)
             if any(kind == "careersite" for kind, _ in boards.values()) else None)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        def submit(employer, kind, token):
            if kind == "workday":
                return ex.submit(FETCH[kind], employer, token, today=today)
            if kind == "careersite":
                return ex.submit(FETCH[kind], employer, token, skip=pages(employer))
            return ex.submit(FETCH[kind], employer, token)
        futs = {submit(employer, kind, token): employer
                for employer, (kind, token) in boards.items() if kind in FETCH}
        for employer, (kind, _token) in boards.items():
            if kind not in FETCH:
                quiet[employer] = f"no reader for {kind!r}"
        for f in as_completed(futs):
            employer = futs[f]
            try:
                got, err = f.result()
            except Exception as exc:                    # noqa: BLE001
                got, err = [], f"{type(exc).__name__}: {exc}"
            if err and got:
                if notes is not None:
                    notes[employer] = err
            elif err:
                quiet[employer] = err
            elif not got:
                quiet[employer] = "resolved, but nothing matching the location filter"
            rows.extend(got)
    return rows, quiet


# -------------------------------------------------------------------- probe

def _probe_workday(token: str) -> str:
    """Robots and the first page only: a probe is not a round."""
    if not workday_board(token):
        return f"NOT A WORKDAY TOKEN ({token!r})"
    board = _wd.WorkdayBoard(token)
    ok, why = robots_allows(board.host, board.robots_paths())
    if not ok:
        return f"REFUSED ({why})"
    try:
        first = board.first()
    except BoardError as e:
        return f"NO JOBS ({str(e).split(': ', 1)[-1]})"
    facets, in_country = board.country_facet(first.get("facets"), COUNTRY_NAME, COUNTRY_ID)
    total = int(first.get("total") or 0)
    if not total:
        return "NO JOBS (token may be wrong)"
    where = (f"{in_country or 0} in {COUNTRY_NAME.title()}" if facets
             else "no country facet, the location filter does it all")
    return f"{total} open, {where}"


def _probe_refused(host: str, paths, why: str, add: str) -> str:
    ok, now = robots_allows(host, paths)
    if ok:
        return f"robots.txt now allows it ({now}): verify with --add {add} before adding"
    return f"still refused: {now} (recorded: {why})"


def _probe_one(employer: str, kind: str, token: str) -> str:
    """One board's verdict for `probe`."""
    if kind == "workday":
        return _probe_workday(token)
    if kind not in READERS:
        return f"NO READER ({kind!r})"
    try:
        if kind == "careersite":
            # Its sitemap only: reading the pages is a round's work, not a probe's.
            if not READERS[kind].exists(token):
                return "NO JOBS (robots.txt says no, or the sitemap lists no job pages)"
            return f"{len(READERS[kind].job_pages(token))} job pages listed"
        jobs = READERS[kind].fetch(token)        # one read; bodies are not asked for
    except BoardError as e:
        return f"NO JOBS ({str(e).split(': ', 1)[-1]})"
    return (f"{len(jobs)} open, {len(_rows(employer, jobs))} in range" if jobs
            else "NO JOBS (token may be wrong)")


def probe(boards=None, workers: int = 16) -> dict[str, str]:
    """{employer: verdict}. A token that stops resolving is a repair, not news.

    The boards are read side by side, as a round reads them (fetch_all), and openroles still
    holds each host to its own few at once: one after another, 92 boards took minutes."""
    boards = BOARDS if boards is None else boards
    items = sorted(boards.items())
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        verdicts = list(ex.map(lambda kv: _probe_one(kv[0], *kv[1]), items))
    out = dict(zip((employer for employer, _ in items), verdicts))
    for employer, (kind, token, why) in sorted(REFUSED.items()):
        board = _wd.WorkdayBoard(token) if workday_board(token) else None
        if board is None:
            out[f"{employer} [refused]"] = f"recorded: {why}"
            continue
        out[f"{employer} [refused]"] = _probe_refused(
            board.host, board.robots_paths(), why, f"{kind} {token}")
    for kind, (host, path, why) in sorted(REFUSED_PROVIDERS.items()):
        out[f"{kind} [refused]"] = _probe_refused(host, [path], why, f"{kind} <board>")
    return out


# A board guessed from a company's name with fewer roles than this is more often a small
# organisation that took the name first than the employer's own board.
SMALL_BOARD = 10


def find(target: str) -> list[dict]:
    """The boards behind an employer's name or careers page, each read the way a round reads it.

    {kind, token, in_range, why, how, open, titles}. `how` is how it was found: "named"
    (a board URL or ats:token), "linked" (the careers page links to it) or "guessed"
    (a board with a name the employer might use exists). A guess is not the employer's
    until their own careers page says so: guessing two large employers' short names on
    every system openroles reads found three-role boards belonging to strangers, and they
    were presented as the employers' own. `titles` is a few of its roles, for that check.
    """
    from openroles import detect
    from openroles.discover import parse
    target = target.strip()
    how = ("named" if parse(target) else
           "linked" if re.match(r"^(https?://|www\.)|^[a-z0-9-]+(\.[a-z0-9-]+)+/", target, re.I)
           else "guessed")
    out = []
    for board in detect(target):
        if board.ats in ("workday", "careersite") or board.ats in DETAILED:
            rows, err = FETCH[board.ats](target, board.token)
            total, titles = len(rows), [r["title"] for r in rows[:4]]
        else:                                   # one read: every role, then the ones in range
            try:
                jobs, err = READERS[board.ats].fetch(board.token), None
            except BoardError as e:
                jobs, err = [], str(e).split(": ", 1)[-1]
            rows, total, titles = _rows(target, jobs), len(jobs), [j.title for j in jobs[:4]]
        out.append({"kind": board.ats, "token": board.token, "in_range": len(rows), "why": err,
                    "how": how, "open": total, "titles": titles})
    return out


def _find_lines(target: str, found: list[dict]) -> list[str]:
    """What --find prints: a map entry for a board the employer's own page or URL names,
    and for a guess the evidence to check it against, with the entry held back."""
    lines = []
    for b in found:
        head = (f"{b['kind']}/{b['token']}: {b['open']} open"
                + (" (no profile yet, so none judged in range)" if NO_PROFILE
                   else f", {b['in_range']} in range"))
        lines.append(head + (f" [{b['why']}]" if b["why"] else ""))
        entry = f'"<Employer>": ("{b["kind"]}", "{b["token"]}"),'
        if b["how"] != "guessed":
            lines.append(f"  found: {'named' if b['how'] == 'named' else 'linked from that page'}")
            lines.append(f"  map entry: {entry}")
            continue
        small = b["open"] < SMALL_BOARD
        lines.append(f"  found: guessed from the name {target!r}; nothing yet shows it is theirs"
                     + (f", and {b['open']} role(s) is small for an employer's own board" if small
                        else ""))
        if b["titles"]:
            lines.append("  its roles include: " + "; ".join(b["titles"]))
        lines.append("  confirm it on the employer's own careers page (--find <that page's "
                     "address> finds the board it links to); once confirmed, the map entry is "
                     + entry)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="write the rows as JSON")
    ap.add_argument("--probe", action="store_true", help="re-check every token")
    ap.add_argument("--find", metavar="EMPLOYER_OR_URL",
                    help="find an employer's board from its name or careers page")
    ap.add_argument("--add", nargs=2, metavar=("PROVIDER", "TOKEN"),
                    help="verify one board before adding it to the map; for "
                         "workday, TOKEN may be the careers site's URL")
    ap.add_argument("--seen", default=None,
                    help="seen_jobs.json whose rulings a careers site's pages are skipped on "
                         "(default: the repo's)")
    ap.add_argument("--keep-ruled-out", dest="keep_ruled_out", action="store_true",
                    help="skip no careers-site page for a past ruling, so every one is read "
                         "and judged again (run_round.py --no-seen-read)")
    a = ap.parse_args()

    if a.find:
        found = find(a.find)
        for line in _find_lines(a.find, found):
            print(line)
        if not found:
            print(f"ats_boards: no {_systems()} board found for {a.find!r}; "
                  "for Workday, give the careers site's URL", file=sys.stderr)
        return 0 if found else 1

    if a.add:
        kind, token = a.add
        if kind in REFUSED_PROVIDERS:
            print(f"ats_boards: {kind} is refused: {REFUSED_PROVIDERS[kind][2]}",
                  file=sys.stderr)
            return 2
        if kind not in FETCH:
            print(f"ats_boards: unknown provider {kind!r} (one of {', '.join(FETCH)})",
                  file=sys.stderr)
            return 2
        if kind == "workday":
            norm = workday_token(token)
            if not norm:
                print(f"ats_boards: not a Workday board: {token!r} (want "
                      "https://<tenant>.<wdN>.myworkdayjobs.com/<site> or "
                      "<tenant>.<wdN>/<site>)", file=sys.stderr)
                return 2
            token = norm
        rows, err = FETCH[kind](token, token)
        print(f"{kind}/{token}: {len(rows)} in-range job(s)"
              + (f" [{err}]" if err else ""))
        for r in rows[:10]:
            print(f"  {r['location'][:28]:28} {r['title'][:60]}")
        if rows:
            print(f'  map entry: "<Employer>": ("{kind}", "{token}"),')
        return 0 if rows else 1

    if a.probe:
        for employer, verdict in probe().items():
            print(f"  {employer:26} {verdict}")
        return 0

    notes: dict[str, str] = {}
    rows, quiet = fetch_all(notes=notes, seen=a.seen, keep_ruled_out=a.keep_ruled_out)
    by_portal: dict[str, int] = {}
    for r in rows:
        by_portal[r["portal"]] = by_portal.get(r["portal"], 0) + 1
    print(f"ats_boards: {len(rows)} in-range postings from "
          f"{len(BOARDS) - len(quiet)}/{len(BOARDS)} boards "
          f"({', '.join(f'{k} {v}' for k, v in sorted(by_portal.items()))})")
    for employer, why in sorted(quiet.items()):
        print(f"  quiet: {employer}: {why}")
    for employer, why in sorted(notes.items()):
        print(f"  partial: {employer}: {why}")
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rows, fh, indent=1)
        print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
