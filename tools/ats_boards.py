#!/usr/bin/env python3
"""Employer job boards, read straight from the ATS, keyed by employer.

The biggest input gap in a search is source coverage. A job portal or two is
enabled, and the profile names the target employers that the pipeline would
otherwise have no way to act on: they are a preference stated in prose, and a
keyword search on a portal is a poor proxy for "show me everything this
employer has open in my city".

Four applicant tracking systems publish the board their own careers page reads,
as JSON, with no key and no HTML to parse:

    greenhouse   one request a board, posting bodies included
    lever        one request a board, posting bodies included
    ashby        one request a board, bodies and any posted pay included
    workday      a paged listing, then one request per posting body

Workday is the one large employers run: they are often visible only through a
portal until their board is read here, so a posting the portal ranked low or
never indexed did not exist for the search, and those are often the best-paid
roles on the list.
A careers site at https://<tenant>.<wdN>.myworkdayjobs.com/<site> is backed by
the endpoint its own front end calls, POST /wday/cxs/<tenant>/<site>/jobs, and
GET /wday/cxs/<tenant>/<site>/job/<path> returns one posting's body.

WHAT THIS IS NOT. It is not complete and does not pretend to be. Employers on
SuccessFactors, Oracle or their own careers site publish no equivalent open
endpoint, so they still come through the portals. Some Workday employers'
robots.txt disallows the very board this would read, and SmartRecruiters'
robots.txt closes its posting API to every crawler except LinkedIn's: see
REFUSED. This adds a source; it does not replace one.

ROBOTS. A Workday or Ashby board is read only where the host's robots.txt
allows it, re-checked on every run, because a policy is a fact that changes
and a board added last quarter should stop being read the week its owner says
no. The rules are `robots_check.allowed`, the same longest-match, Disallow-wins
parser the browser-header retry uses. Greenhouse and Lever predate the gate:
their robots.txt allows the API paths when checked, so their one-request path
is unchanged.

THE MAP IS THE WORK. An employer is only here once its token has been verified
to return jobs, because a wrong token returns an empty list that is
indistinguishable from an employer with no openings, which is the exact failure
the scrape canary exists to catch. `--probe` re-checks every token and reports
the ones that have gone quiet, so the map can be repaired rather than rotting
into silence. It re-checks the refused ones too, and says when a rule lifts.

Usage:
    python3 tools/ats_boards.py --out ats.json
    python3 tools/ats_boards.py --probe
    python3 tools/ats_boards.py --add greenhouse <board>    # verify then print
    python3 tools/ats_boards.py --add ashby <board>
    python3 tools/ats_boards.py --add workday https://<tenant>.wd3.myworkdayjobs.com/<Site>
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import http.client
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import robots_check  # noqa: E402
from prefilter import location_verdict, title_verdict  # noqa: E402

# `content=true` returns every posting's body in the SAME request. One call
# per board instead of one per posting, so a round costs one fetch per board
# and hydrate has nothing left to do for these rows. Without it every
# Greenhouse posting reached the scorer with an empty description, which is
# precisely the failure `tools/hydrate.py` was written to stop: the score is
# then made on the title alone and nothing says so.
GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/{token}?mode=json"
# `includeCompensation` puts the posted pay band in the same response. Most
# postings state no salary, and when one does it is the only number
# the salary flag in text_screen.py can act on.
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
ASHBY_HOST = "api.ashbyhq.com"

UA = "last-job-search/1.0 (personal job search; contact via GitHub)"
TIMEOUT = 20

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
# rather than honouring it. `robots_allows` checks the site path for exactly
# this reason, and `--probe` re-checks these so the day a rule lifts is noticed.
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

# A location that says the job is remote and names no geography at all.
# "Remote" on its own is kept; "Remote - <city>" is caught by PLACES above and
# "Remote - SF Bay Area" is caught by neither, which is the point.
BARE_REMOTE = re.compile(r"^\W*(fully |100% )?remote\W*$", re.I)


_TAG = re.compile(r"<[^>]+>")
BODY_CAP = 20_000



def _epoch_ms_date(ms) -> str:
    """Lever's createdAt (milliseconds since 1970) as YYYY-MM-DD, or "" when absent."""
    try:
        import datetime as _d
        return _d.datetime.fromtimestamp(int(ms) / 1000, _d.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""

def _text(content: str) -> str:
    """Greenhouse hands back HTML, entity-encoded, sometimes twice.

    Unescaping runs until it stops changing so "&amp;lt;p&amp;gt;" arrives as
    text rather than as visible markup in the middle of a requirement.
    """
    s = content or ""
    for _ in range(3):
        un = html.unescape(s)
        if un == s:
            break
        s = un
    s = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = _TAG.sub(" ", s)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()[:BODY_CAP]


# ------------------------------------------------------------------ fetching
#
# The politeness budget: never more than PER_HOST requests in flight to one
# host, and a timeout on every call. Held here rather than by each caller's
# thread pool, because the pools are per board and two boards can share a host:
# every Greenhouse board is boards-api.greenhouse.io, and a Workday board's
# listing and its bodies run in separate pools against the same tenant.
PER_HOST = 2
_SLOTS: dict[str, threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def _slot(host: str) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        return _SLOTS.setdefault(host.lower(), threading.BoundedSemaphore(PER_HOST))


def _request(url: str, payload: dict | None = None) -> tuple[object | None, str | None]:
    """(parsed JSON, None), or (None, why). GET, or a JSON POST with `payload`."""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    host = urllib.parse.urlsplit(url).netloc
    try:
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        with _slot(host):
            with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
                raw = fh.read()
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    # HTTPException covers a body cut off mid-read (IncompleteRead), which is
    # not an OSError and would otherwise escape as a crash.
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError,
            ValueError) as e:
        return None, type(e).__name__
    try:
        return json.loads(raw.decode("utf-8", "replace")), None
    except ValueError:
        return None, "the response was not JSON"


def _get(url: str) -> object | None:
    return _request(url)[0]


# ------------------------------------------------------------------ robots
#
# Checked for every agent a rule could be written for: everyone, the token
# WebFetch sends (robots_check reads the same pair), and this tool's own. An
# agent with no group of its own falls back to "*", so "*" goes first and a
# refusal names the rule that was actually written.
ROBOTS_AGENTS = ("*", "Claude-User", "last-job-search")

# Statuses that mean no policy is published. robots_check.gate() accepts only a
# 404, because it decides whether to retry past a firewall with a browser's
# headers, the one case where caution about a missing file matters most. This
# is an honest client asking first, so it follows RFC 9309 section 2.3.1.3: an
# unavailable robots.txt is no restriction. api.ashbyhq.com answers every path
# but its public posting API with 401, robots.txt included.
#
# A 403 is left out on purpose, although the RFC would allow it: on robots.txt
# it is usually a firewall refusing an unknown client, and pushing past one is
# what robots_check exists to prevent. A 429, a 5xx or no answer at all means
# the policy could not be read, and the RFC says to assume complete disallow.
NO_POLICY = {401, 404, 410}

_ROBOTS: dict[str, tuple[int, str]] = {}
_ROBOTS_LOCK = threading.Lock()


def _robots_txt(host: str) -> tuple[int, str]:
    """(HTTP status, body) for https://<host>/robots.txt, fetched once per run.

    Status 0 means no answer at all. Cached for the life of the process, so a
    round reads each host's policy once however many boards share the host.
    """
    key = host.lower()
    with _ROBOTS_LOCK:
        if key in _ROBOTS:
            return _ROBOTS[key]
    req = urllib.request.Request(f"https://{key}/robots.txt",
                                 headers={"User-Agent": UA, "Accept": "text/plain,*/*"})
    try:
        with _slot(key):
            with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
                got = (fh.status, fh.read(512_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        got = (e.code, "")
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError,
            ValueError):
        got = (0, "")
    with _ROBOTS_LOCK:
        _ROBOTS[key] = got
    return got


def robots_allows(host: str, paths) -> tuple[bool, str]:
    """(may these paths be read, why), from the host's robots.txt."""
    status, body = _robots_txt(host)
    if status == 200:
        if not robots_check.is_robots_body(body):
            return False, ("robots.txt answered 200 with something that is not a "
                           "robots file, so permission is unconfirmed")
        for path in paths:
            for agent in ROBOTS_AGENTS:
                if not robots_check.allowed(body, agent, path):
                    return False, f"robots.txt disallows {path} for {agent}"
        return True, "robots.txt allows it"
    if status in NO_POLICY:
        return True, f"no robots.txt (HTTP {status}), which RFC 9309 reads as no restriction"
    return False, ("robots.txt could not be read (%s), so permission is unconfirmed"
                   % (f"HTTP {status}" if status else "no answer"))


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
    return bool(PLACES.search(loc) or BARE_REMOTE.match(loc))


def _with_country(label: str, country: str) -> str:
    """A bare "Remote" borrows the country the ATS recorded for the posting.

    `_wanted` keeps a bare "Remote" because the string has not said no. Workday
    and Ashby have said where, in a structured field: a posting on one Ashby
    board lists a San Francisco address with a bare "Remote" beside it, and
    without the country it would reach the scorer as remote-from-anywhere.
    """
    label = " ".join(str(label or "").split())
    country = " ".join(str(country or "").split())
    if country and BARE_REMOTE.match(label):
        return f"{label}, {country}"
    return label


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
    unchanged.

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
    wanted = [c for c in cands if _wanted(c)]
    if not wanted:
        return "", "FAIL"
    judged = [(_RANK[location_verdict(c, title)[0]], c) for c in wanted]
    best = min(r for r, _ in judged)
    keep = [c for r, c in judged if r == best]
    joined = "; ".join(keep)
    if len(keep) > 1 and all(k.startswith("Remote - ") for k in keep):
        joined = "Remote - " + "; ".join(k[len("Remote - "):] for k in keep)
    # Two sites that each pass can still read worse joined, so the string that
    # leaves here is checked the way prefilter will read it.
    if len(keep) > 1 and _RANK[location_verdict(joined, title)[0]] > best:
        joined = keep[0]
    return joined, next(v for v, r in _RANK.items() if r == best)


# ---------------------------------------------------------------- greenhouse

def greenhouse(employer: str, token: str) -> tuple[list[dict], str | None]:
    data = _get(GREENHOUSE.format(token=token))
    if not isinstance(data, dict) or "jobs" not in data:
        return [], "no jobs key in the response"
    out = []
    for j in data.get("jobs") or []:
        loc = ((j.get("location") or {}).get("name") or "").strip()
        if not _wanted(loc):
            continue
        out.append({
            "id": f"gh-{j.get('id')}",
            "title": (j.get("title") or "").strip(),
            "company": employer,
            "url": j.get("absolute_url"),
            "location": loc,
            # First published, not updated: Greenhouse bumps updated_at on every
            # edit, so a role first posted months ago read as new to a 7-day
            # round. updated_at only when the board gives nothing else.
            "date": (j.get("first_published") or j.get("updated_at") or "")[:10],
            "portal": "greenhouse",
            "desc": _text(j.get("content") or "") or None,
            "deadline": (j.get("application_deadline") or "")[:10] or None,
        })
    return out, None


def lever(employer: str, token: str) -> tuple[list[dict], str | None]:
    data = _get(LEVER.format(token=token))
    if not isinstance(data, list):
        # Lever answers a bad token with {"ok": false, ...} rather than a 404,
        # which len() would happily report as "2 jobs".
        return [], "not a posting list (probably a bad board token)"
    out = []
    for j in data:
        loc = ((j.get("categories") or {}).get("location") or "").strip()
        if not _wanted(loc):
            continue
        out.append({
            "id": f"lv-{j.get('id')}",
            "title": (j.get("text") or "").strip(),
            "company": employer,
            "url": j.get("hostedUrl"),
            "location": loc,
            "date": _epoch_ms_date(j.get("createdAt")),
            "portal": "lever",
            "desc": j.get("descriptionPlain") or None,
        })
    return out, None


# --------------------------------------------------------------------- ashby

def _ashby_address(entry: dict) -> dict:
    addr = entry.get("address")
    post = addr.get("postalAddress") if isinstance(addr, dict) else None
    return post if isinstance(post, dict) else {}


def _ashby_label(entry: dict, fallback_country: str = "") -> str:
    """One Ashby location as text, from the structured address where it has one.

    The display name is whatever the employer typed, and some of them carry no
    geography at all: one writes its own name and a country code, another
    "Remote - Multiple Locations". The postal address beside it is where the job is.
    """
    name = " ".join(str(entry.get("location") or "").split())
    post = _ashby_address(entry)
    city, region, country = (" ".join(str(post.get(k) or "").split())
                             for k in ("addressLocality", "addressRegion", "addressCountry"))
    if city:
        label = ", ".join(x for x in (city, region, country) if x)
        return f"Remote - {label}" if "remote" in name.lower() else label
    if country and country.lower() not in name.lower():
        return f"{name}, {country}" if name else country
    return _with_country(name, fallback_country)


def _ashby_pay(job: dict) -> str:
    comp = job.get("compensation") if isinstance(job.get("compensation"), dict) else {}
    for key in ("scrapeableCompensationSalarySummary", "compensationTierSummary"):
        val = " ".join(str(comp.get(key) or "").split())
        if val:
            return val
    return ""


def _ashby_rows(employer: str, data: object) -> tuple[list[dict], str | None]:
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return [], "no jobs list in the response (probably a bad board name)"
    out = []
    for j in data["jobs"]:
        if not isinstance(j, dict) or j.get("isListed") is False:
            continue
        title = " ".join(str(j.get("title") or "").split())
        home = str(_ashby_address(j).get("addressCountry") or "")
        labels = [_ashby_label(j)]
        labels += [_ashby_label(s, home) for s in j.get("secondaryLocations") or []
                   if isinstance(s, dict)]
        remote = str(j.get("workplaceType") or "").strip().lower() == "remote"
        location, _ = _choose(labels, title, remote)
        if not location:
            continue
        desc = (str(j.get("descriptionPlain") or "").strip()
                or _text(str(j.get("descriptionHtml") or "")))
        pay = _ashby_pay(j)
        if pay:
            # A line text_screen's salary reader recognises: a cue word and
            # the range. It is the employer's own structured field, and the
            # body is cut first so the cap can never cut it off.
            line = f"Compensation (as posted on the board): {pay}"
            desc = f"{desc[:BODY_CAP - len(line) - 2]}\n\n{line}".strip()
        out.append({
            "id": f"ab-{j.get('id')}",
            "title": title,
            "company": employer,
            "url": j.get("jobUrl"),
            "location": location,
            "date": str(j.get("publishedAt") or "")[:10],
            "portal": "ashby",
            "desc": desc[:BODY_CAP] or None,
        })
    return out, None


def ashby(employer: str, token: str) -> tuple[list[dict], str | None]:
    ok, why = robots_allows(ASHBY_HOST, [f"/posting-api/job-board/{token}"])
    if not ok:
        return [], why
    data, err = _request(ASHBY.format(token=urllib.parse.quote(token, safe="")))
    if err:
        return [], f"the board did not answer ({err})"
    return _ashby_rows(employer, data)


# ------------------------------------------------------------------- workday
#
# How much of a board is read. Workday serves at most 20 postings a page and
# stops paging at an offset of 2,000.
#
# A board up to PAGE_ALL_MAX postings is paged whole, after narrowing it to
# the profile's country with the board's own country facet, and filtered here. Anything
# bigger is searched instead, once per title variant in scrape_wide.QUERIES,
# so a round does not page through a thousand branch and call-centre roles to
# find the analytics ones, and so a board past Workday's 2,000 cap is read at
# all. Measured on one large national board: paging found nearly everything
# the title search found past the title and location gates, and the few the
# search missed were in unrelated functions. Counting
# the bodies, the two cost about the same, so searching is not a saving at
# that size; it is aimed.
#
# In search mode a term's next page is read only while its titles keep
# matching, because Workday ranks by relevance over the whole description and
# page three of "pricing" is postings that mention pricing once.
PAGE = 20
PAGE_ALL_MAX = 1000
MAX_OFFSET = 2000
SEARCH_PAGES = 5
SATURATED = 15

# The country a Workday board is narrowed to: (Workday's facet value id, the
# value's name), from profile/boards.py. Workday's identifier for a country is
# the same on every tenant seen; the facet's own name is not (locationCountry,
# Country, Location_Country), so the facet is found by its value. No country
# set means no narrowing, and the location filter does it all.
COUNTRY_ID, COUNTRY_NAME = getattr(_B, "WORKDAY_COUNTRY", ("", ""))

WORKDAY_TOKEN = re.compile(r"^(?P<tenant>[a-z0-9][a-z0-9-]*)\.(?P<dc>wd\d{1,3})/"
                           r"(?P<site>[A-Za-z0-9][A-Za-z0-9_-]*)$")
WORKDAY_URL = re.compile(r"^https?://(?P<tenant>[a-z0-9][a-z0-9-]*)\.(?P<dc>wd\d{1,3})"
                         r"\.myworkdayjobs\.com/(?:[a-z]{2}-[a-z]{2}/)?"
                         r"(?P<site>[a-z0-9][a-z0-9_-]*)", re.I)
MULTI = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)
# A posting's path inside its board, and nothing else. It comes from the
# listing's structured `externalPath`, never from posting text, and anything
# that could point the request somewhere other than this board is refused.
_WD_PATH = re.compile(r"^/job/[^\s?#\\]+$")
_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)(\+)?\s+days?\s+ago)", re.I)


def workday_board(token: str) -> tuple[str, str, str] | None:
    """(host, tenant, site) for a "tenant.wdN/Site" token, or None."""
    m = WORKDAY_TOKEN.match(token or "")
    if not m:
        return None
    return f"{m['tenant']}.{m['dc']}.myworkdayjobs.com", m["tenant"], m["site"]


def workday_token(text: str) -> str | None:
    """A map token from a token or from a careers-site URL pasted as seen."""
    text = (text or "").strip()
    if WORKDAY_TOKEN.match(text):
        return text
    m = WORKDAY_URL.match(text)
    if not m:
        return None
    return f"{m['tenant'].lower()}.{m['dc'].lower()}/{m['site']}"


def workday_paths(tenant: str, site: str) -> list[str]:
    """What robots.txt must allow: the listing, the bodies, and the board itself.

    A robots.txt path is case-sensitive and a Workday site name is not, so a
    rule written as /external/ still covers the board spelt /External/.
    """
    paths = [f"/wday/cxs/{tenant}/{site}/jobs", f"/wday/cxs/{tenant}/{site}/job/",
             f"/{site}/"]
    return paths + ([f"/{site.lower()}/"] if site != site.lower() else [])


def _valid_path(path) -> bool:
    return (isinstance(path, str) and bool(_WD_PATH.match(path))
            and ".." not in path and "//" not in path)


def _quote_path(path: str) -> str:
    return urllib.parse.quote(path, safe="/-_.~%")


def _posted_on(text, today: dt.date) -> str:
    """ISO date from Workday's "Posted 3 Days Ago", or "" when it is a floor."""
    m = _POSTED.search(str(text or ""))
    if not m:
        return ""
    word = m.group(1).lower()
    if word == "today":
        days = 0
    elif word == "yesterday":
        days = 1
    elif m.group(3):                  # "Posted 30+ Days Ago" is a floor, not a date
        return ""
    else:
        days = int(m.group(2))
    return (today - dt.timedelta(days=days)).isoformat()


def _remote(remote_type) -> bool:
    return str(remote_type or "").strip().lower() == "remote"


def _country_facet(facets) -> tuple[dict, int | None]:
    """({facetParameter: [the country]}, how many) when the board has a country facet."""
    stack = [f for f in facets or [] if isinstance(f, dict)]
    while stack:
        facet = stack.pop()
        param = str(facet.get("facetParameter") or "")
        for v in facet.get("values") or []:
            if not isinstance(v, dict):
                continue
            if isinstance(v.get("values"), list):          # a group, e.g. a
                stack.append(v)                            # locationMainGroup
                continue
            name = str(v.get("descriptor") or "").strip().lower()
            if "country" in param.lower() and v.get("id") and (COUNTRY_ID or COUNTRY_NAME) and (
                    v.get("id") == COUNTRY_ID or name == COUNTRY_NAME):
                return {param: [v["id"]]}, v.get("count")
    return {}, None


def _distinct_terms(queries) -> list[str]:
    """The title variants, less any that only add words to a shorter one.

    Workday matches every word of a search, so "senior data analyst" can only
    find what "data analyst" already found.
    """
    terms = list(dict.fromkeys(" ".join(q.lower().split()) for q in queries if q.strip()))
    words = {t: frozenset(t.split()) for t in terms}
    return [t for t in terms if not any(words[o] < words[t] for o in terms)]


def _two_at_a_time(fn, items) -> list:
    """fn over items, PER_HOST at a time, results in input order, never raising."""
    def safe(item):
        try:
            return fn(item)
        except Exception as exc:                            # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"
    with ThreadPoolExecutor(max_workers=PER_HOST) as ex:
        return list(ex.map(safe, items))


class _Board:
    """One Workday board's calls. Stops sending the moment it is told to slow down."""

    def __init__(self, token: str):
        self.host, self.tenant, self.site = workday_board(token) or ("", "", "")
        self.api = f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"
        self.halt = threading.Event()

    def call(self, url: str, payload: dict | None = None):
        if self.halt.is_set():
            return None, "not sent: the board asked to slow down"
        data, err = _request(url, payload)
        if err in ("HTTP 429", "HTTP 503"):
            self.halt.set()
        return data, err

    def page(self, facets: dict, search: str, offset: int):
        return self.call(f"{self.api}/jobs", {"appliedFacets": facets, "limit": PAGE,
                                              "offset": offset, "searchText": search})

    def body(self, path: str):
        return self.call(f"{self.api}{_quote_path(path)}")

    def public_url(self, path: str) -> str:
        return f"https://{self.host}/{self.site}{_quote_path(path)}"


def _wd_page_all(board: _Board, facets: dict, total: int, first=None):
    """Every posting on the (country slice of the) board."""
    got = [p for p in first or [] if isinstance(p, dict)]
    offsets = list(range(PAGE if first is not None else 0, min(total, MAX_OFFSET), PAGE))
    errors = []
    for data, err in _two_at_a_time(lambda off: board.page(facets, "", off), offsets):
        if err or not isinstance(data, dict):
            errors.append(err or "a page that was not a listing")
            continue
        got.extend(p for p in data.get("jobPostings") or [] if isinstance(p, dict))
    return got, errors


def _wd_search(board: _Board, facets: dict, queries=None):
    """The postings the title variants find, each term paged while it keeps matching."""
    if queries is None:
        from scrape_wide import QUERIES as queries
    terms = _distinct_terms(queries)

    def one(term):
        stems = [w[:5] for w in term.split()]
        found, errs = [], []
        for n in range(SEARCH_PAGES):
            data, err = board.page(facets, term, n * PAGE)
            if err or not isinstance(data, dict):
                errs.append(err or "a page that was not a listing")
                break
            posts = [p for p in data.get("jobPostings") or [] if isinstance(p, dict)]
            found.extend(posts)
            hits = sum(1 for p in posts
                       if all(s in str(p.get("title") or "").lower() for s in stems))
            if hits < SATURATED or (n + 1) * PAGE >= int(data.get("total") or 0):
                break
        return found, errs

    listing, errors = [], []
    for found, errs in _two_at_a_time(one, terms):
        listing.extend(found or [])
        errors.extend([errs] if isinstance(errs, str) else errs or [])
    return listing, errors


def _wd_row(employer: str, board: _Board, path: str, title: str, location: str,
            date: str, desc: str | None = None, deadline: str | None = None) -> dict:
    return {
        "id": f"wd-{board.tenant}-{path.rsplit('/', 1)[-1]}",
        "title": title,
        "company": employer,
        "url": board.public_url(path),
        "location": location,
        "date": date,
        "portal": "workday",
        "desc": desc or None,
        "deadline": deadline or None,
    }


def _wd_detail_row(employer: str, board: _Board, posting: dict, detail,
                   today: dt.date) -> dict | None:
    info = detail.get("jobPostingInfo") if isinstance(detail, dict) else None
    if not isinstance(info, dict):
        return None
    title = " ".join(str(info.get("title") or posting.get("title") or "").split())
    place = info.get("country")
    country = str(place.get("descriptor") or "") if isinstance(place, dict) else ""
    labels = [_with_country(info.get("location") or posting.get("locationsText"), country)]
    labels += [_with_country(a, country) for a in info.get("additionalLocations") or []
               if isinstance(a, str)]
    remote = _remote(info.get("remoteType") or posting.get("remoteType"))
    location, _ = _choose(labels, title, remote)
    if not location:
        return None
    date = str(info.get("startDate") or "")[:10] or _posted_on(posting.get("postedOn"), today)
    return _wd_row(employer, board, posting["externalPath"], title, location, date,
                   desc=_text(str(info.get("jobDescription") or "")),
                   deadline=str(info.get("endDate") or "")[:10])


def _wd_rows(employer: str, board: _Board, listing, today: dt.date):
    """Rows from a listing, fetching a body only where the free gates say it could matter.

    A body costs one request, so it is fetched for a posting prefilter would
    keep: a title its gate passes, in a place its gate does not fail. A posting
    that fails either is still emitted, without a body, so prefilter drops it
    with the reason and the funnel stays readable. A listing that says only
    "3 Locations" names no place at all: its body is fetched to find out where
    when the title is worth it, and the posting is skipped when it is not.
    """
    rows, fetch, seen = [], [], set()
    for p in listing:
        path = p.get("externalPath")
        title = " ".join(str(p.get("title") or "").split())
        if not title or not _valid_path(path) or path in seen:
            continue
        seen.add(path)
        where = str(p.get("locationsText") or "")
        title_ok = title_verdict(title)[0] != "FAIL"
        if MULTI.match(where):
            if title_ok:
                fetch.append(p)
            continue
        location, verdict = _choose([where], title, _remote(p.get("remoteType")))
        if not location:
            continue
        if title_ok and verdict != "FAIL":
            fetch.append(p)
        else:
            rows.append(_wd_row(employer, board, path, title, location,
                                _posted_on(p.get("postedOn"), today)))
    failed = []
    details = _two_at_a_time(lambda p: board.body(p["externalPath"]), fetch)
    for p, (detail, err) in zip(fetch, details, strict=True):
        if err:
            failed.append(err)
            continue
        row = _wd_detail_row(employer, board, p, detail, today)
        if row:
            rows.append(row)
    return rows, failed, len(fetch)


def _summarise(errors: list[str]) -> str:
    counts: dict[str, int] = {}
    for e in errors:
        counts[e] = counts.get(e, 0) + 1
    return ", ".join(f"{n}x {e}" for e, n in sorted(counts.items(), key=lambda x: -x[1])[:3])


def workday(employer: str, token: str, queries=None,
            today: dt.date | None = None) -> tuple[list[dict], str | None]:
    board = _Board(token)
    if not board.host:
        return [], f"not a Workday token (want tenant.wdN/Site): {token!r}"
    ok, why = robots_allows(board.host, workday_paths(board.tenant, board.site))
    if not ok:
        return [], why
    first, err = board.page({}, "", 0)
    if err:
        return [], f"the board did not answer ({err})"
    if not isinstance(first, dict) or not isinstance(first.get("jobPostings"), list):
        return [], "not a Workday board response (probably a wrong tenant or site)"
    facets, in_country = _country_facet(first.get("facets"))
    # A facet that came without its count is bounded by the whole board.
    total = int((in_country if in_country is not None else first.get("total")) or 0)
    if total > PAGE_ALL_MAX:
        listing, errors = _wd_search(board, facets, queries)
    else:
        listing, errors = _wd_page_all(board, facets, total,
                                       None if facets else first["jobPostings"])
    rows, failed, asked = _wd_rows(employer, board, listing, today or dt.date.today())
    notes = []
    if errors:
        notes.append(f"{len(errors)} listing page(s) failed ({_summarise(errors)})")
    if failed:
        notes.append(f"{len(failed)} of {asked} posting bodies failed ({_summarise(failed)}) "
                     f"and those postings were left out")
    return rows, "; ".join(notes) or None


FETCH = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workday": workday}


def fetch_all(boards=None, workers: int = 16,
              notes: dict | None = None) -> tuple[list[dict], dict[str, str]]:
    """(rows, {employer: why it returned nothing}) across every board.

    `notes`, when given, collects what a board that DID return rows left out,
    a Workday body that would not fetch, which is worth saying and is not the
    same thing as a board gone quiet. The worker count is across boards; the
    politeness budget per host is held in `_request`.
    """
    boards = BOARDS if boards is None else boards
    rows: list[dict] = []
    quiet: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(FETCH[kind], employer, token): employer
                for employer, (kind, token) in boards.items()}
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
    board = _Board(token)
    if not board.host:
        return f"NOT A WORKDAY TOKEN ({token!r})"
    ok, why = robots_allows(board.host, workday_paths(board.tenant, board.site))
    if not ok:
        return f"REFUSED ({why})"
    first, err = board.page({}, "", 0)
    if err or not isinstance(first, dict) or not isinstance(first.get("jobPostings"), list):
        return f"NO JOBS ({err or 'not a Workday board response'})"
    facets, in_country = _country_facet(first.get("facets"))
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


def probe(boards=None) -> dict[str, str]:
    """{employer: verdict}. A token that stops resolving is a repair, not news."""
    boards = BOARDS if boards is None else boards
    out = {}
    for employer, (kind, token) in sorted(boards.items()):
        if kind == "workday":
            out[employer] = _probe_workday(token)
            continue
        if kind == "ashby":
            ok, why = robots_allows(ASHBY_HOST, [f"/posting-api/job-board/{token}"])
            if not ok:
                out[employer] = f"REFUSED ({why})"
                continue
            data, err = _request(ASHBY.format(token=urllib.parse.quote(token, safe="")))
            jobs = data.get("jobs") if isinstance(data, dict) else None
            total = len(jobs) if isinstance(jobs, list) else 0
            rows, perr = _ashby_rows(employer, data)
            out[employer] = (f"{total} open, {len(rows)} in range" if total
                             else f"NO JOBS ({err or perr or 'token may be wrong'})")
            continue
        url = (GREENHOUSE if kind == "greenhouse" else LEVER).format(token=token)
        data = _get(url)
        if kind == "greenhouse":
            total = len((data or {}).get("jobs") or []) if isinstance(data, dict) else 0
        else:
            total = len(data) if isinstance(data, list) else 0
        rows, err = FETCH[kind](employer, token)
        out[employer] = (f"{total} open, {len(rows)} in range" if total
                         else f"NO JOBS ({err or 'token may be wrong'})")
    for employer, (kind, token, why) in sorted(REFUSED.items()):
        board = _Board(token)
        out[f"{employer} [refused]"] = _probe_refused(
            board.host, workday_paths(board.tenant, board.site), why, f"{kind} {token}")
    for kind, (host, path, why) in sorted(REFUSED_PROVIDERS.items()):
        out[f"{kind} [refused]"] = _probe_refused(host, [path], why, f"{kind} <board>")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="write the rows as JSON")
    ap.add_argument("--probe", action="store_true", help="re-check every token")
    ap.add_argument("--add", nargs=2, metavar=("PROVIDER", "TOKEN"),
                    help="verify one board before adding it to the map; for "
                         "workday, TOKEN may be the careers site's URL")
    a = ap.parse_args()

    if a.add:
        kind, token = a.add
        if kind in REFUSED_PROVIDERS:
            print(f"ats_boards: {kind} is refused: {REFUSED_PROVIDERS[kind][2]}",
                  file=sys.stderr)
            return 2
        if kind not in FETCH:
            print(f"ats_boards: unknown provider {kind!r}", file=sys.stderr)
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
    rows, quiet = fetch_all(notes=notes)
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
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        print(f"  wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
