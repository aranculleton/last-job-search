#!/usr/bin/env python3
"""Wide, paginated, multi-portal scrape. The free top of the funnel.

## Why this exists

Rounds 7 and 8 surfaced almost nothing and the cause was not the scoring, it
was reach. Three bugs, all in the scrape:

1. `--limit 25` on the LinkedIn CLI is a CLIENT-SIDE CAP, and a page is 10
   results. Every query in rounds 7-8 returned at most 10 postings while the
   run believed it was getting 25, and nothing ever paginated. 52 queries
   returned 489 postings where they should have returned several thousand.
2. `freehire-search` is installed and `enabled: true`, returns 25 per page
   AND ships the full description inline (no detail fetch needed). It went
   completely unused.
3. Only one location string (the home city) was searched, so postings
   LinkedIn files under the neighbouring municipalities or region-wide were
   invisible.

Scraping and prefiltering cost ZERO model tokens. The expensive stage is the
weighted scoring, and that is capped by selection, not by how much was
scraped. So the correct shape is: scrape as wide as the portals allow, filter
hard for free, and spend the model budget only on survivors.

Usage:
    python3 tools/scrape_wide.py --out DIR [--pages 5] [--jobage <days>]

`--out` is a DIRECTORY: it receives scraped.json (everything), kept.json (past
the prefilter), dropped.json and sources.json (what each source read and what failed, the
employers' own job sites it could not read among them). Exit 2 when more than a quarter
of the portal requests failed, or more than a quarter of those job sites could not be
read, after the files are written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import os
import re
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import portals  # noqa: E402
from hydrate import BODY_CAP  # noqa: E402
from prefilter import annotate, age_days, stamp_copies  # noqa: E402
from lookup_score import strip_language_tag  # noqa: E402

# --------------------------------------------------------------- portal CLIs
#
# tools/portals.py finds or builds each portal's CLI (one resolver for this file
# and hydrate.py), and says which portals are on.
portal_cli = portals.cli
# Resolved on first use, not at import. A build failure should stop a scrape,
# not stop anything that merely imports this module.
LINKEDIN = functools.partial(portal_cli, "linkedin-search", "LINKEDIN_CLI")
FREEHIRE = functools.partial(portal_cli, "freehire-search", "FREEHIRE_CLI")
# The app's two portals, called here with their own request shapes. Every
# other portal that is on, has a CLI and declares `contract: 1` is called
# through the portal contract (`contract` below): a person's own board, built
# by /add-portal, is searched by every round without anyone wiring it in.
WIRED = {"linkedin-search": "linkedin", "freehire-search": "freehire"}

# What is searched is the person's: profile/search.py's SCRAPE_* names the
# locations (portals file a posting under whichever municipality the employer
# typed, so the home city alone misses the rest of the pass set), the
# locations searched with the remote filter on (a different result set from
# the same location without it), the employers worth asking for by name (a
# title search finds the role the market happens to be posting; a company
# search finds the roles at the companies the candidate actually wants, and
# being on that list changes nothing about scoring, only whether the posting
# is ever seen), and the titles the profile actually competes for.
_S = person.module("search")
LOCATIONS = list(getattr(_S, "SCRAPE_LOCATIONS", ()))
REMOTE_LOCATIONS = list(getattr(_S, "SCRAPE_REMOTE_LOCATIONS", ()))
EMPLOYERS = list(getattr(_S, "SCRAPE_EMPLOYERS", ()))
# Paired with each employer name. Kept short: LinkedIn's free-text search
# matches the company field, so the title half only has to be broad enough to
# catch the function without excluding a role that words it differently.
EMPLOYER_QUERIES = list(getattr(_S, "SCRAPE_EMPLOYER_QUERIES", ()))
EMPLOYER_LOCATIONS = list(getattr(_S, "SCRAPE_EMPLOYER_LOCATIONS", ()))
EMPLOYER_REMOTE = list(getattr(_S, "SCRAPE_EMPLOYER_REMOTE", ()))
QUERIES = list(getattr(_S, "SCRAPE_QUERIES", ()))
# The location prefix searched to the full --pages depth; the rest go two deep.
DEEP = getattr(_S, "SCRAPE_DEEP", LOCATIONS[0] if LOCATIONS else "")
PORTAL_COUNTRY = getattr(_S, "PORTAL_COUNTRY", "")
# The places passed to a person's own portal, as that board writes them
# ("Austin, TX" where LinkedIn wants "Austin, Texas, United States"). A portal not
# named searches the first of SCRAPE_LOCATIONS.
PORTAL_LOCATIONS = {str(k): list(v) for k, v in
                    dict(getattr(_S, "PORTAL_LOCATIONS", {}) or {}).items()}
# The minutes the person gives one of their own boards in a round, by its name with or without
# "-search": {"cityboard": 10}. Their time stands whatever the board has found (board_share);
# a board not named gets the time its jobs on the list have earned it.
PORTAL_MINUTES = {str(k): v for k, v in dict(getattr(_S, "PORTAL_MINUTES", {}) or {}).items()}

# Where a round runs decides how hard it leans on the portals. A cloud container is
# a throwaway address; a person's own computer is the address their own LinkedIn
# account signs in from, and a round of thousands of requests from it is a risk to
# them (the linkedin-search skill says keep volume low). So off the cloud a round
# asks for fewer pages, with fewer at once, and at most LOCAL_MAX_REQUESTS of each
# app portal, unless profile/search.py sets its own (SCRAPE_PAGES, SCRAPE_WORKERS,
# SCRAPE_MAX_REQUESTS): the person's trade-off to make, never the app's.
def _in_cloud() -> bool:
    """place.in_cloud: the flag and the cloud container's own markers, never the flag alone.
    A copy too old to have place.py (this file is brought in first by an update) reads the
    flag, as before."""
    try:
        import place
        return place.in_cloud()
    except Exception:  # noqa: BLE001
        return os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"


CLOUD = _in_cloud()
CLOUD_PAGES, CLOUD_WORKERS = 5, 10
LOCAL_PAGES, LOCAL_WORKERS, LOCAL_MAX_REQUESTS = 2, 4, 300


def defaults(cloud: bool | None = None) -> tuple:
    """(pages, workers, the most requests a round sends to each app portal or None)."""
    cloud = CLOUD if cloud is None else cloud
    pages = getattr(_S, "SCRAPE_PAGES", None) or (CLOUD_PAGES if cloud else LOCAL_PAGES)
    workers = getattr(_S, "SCRAPE_WORKERS", None) or (CLOUD_WORKERS if cloud else LOCAL_WORKERS)
    cap = getattr(_S, "SCRAPE_MAX_REQUESTS", None)
    if cap is None and not cloud:
        cap = LOCAL_MAX_REQUESTS
    return int(pages), int(workers), (int(cap) if cap else None)


def run(cmd: list[str], timeout: int = 90) -> tuple[dict | None, str | None]:
    """(parsed JSON, None) on success; (None, reason) on any failure.

    tools/portals.py run_cli, the one runner for a portal's CLI (hydrate.py uses
    it too): stdout goes to a file, not a pipe, because Node writes
    to a pipe asynchronously and a CLI that exits after writing loses what has not
    drained, so ten at once came back cut at 64 KiB mid-string with exit 0; and a line
    where a board refused is kept wherever it falls in stderr. Kept here by name,
    because tests and a person's own tests stand in for it here."""
    return portals.run_cli(cmd, timeout)


# ------------------------------------------------------- why a request failed
#
# "progress: freehire 300/300 sent, 300 failed" said nothing about why. freehire had
# answered every request with 403 Forbidden, and a board of the person's own had said
# it was being redirected to a page its robots.txt disallows. A failure is now named by
# its cause, and a cause that will not change within a round (a refusal) is caught by
# the probe, before any sweep time is spent on that portal. What counts as a refusal
# is portals.REFUSAL_LINE.
_REFUSAL = portals.REFUSAL_LINE
_EXIT = portals.EXIT_PREFIX
_refusal = portals.refusal
# An HTTP status where an error names one: after "HTTP", "status" or "failed:", or
# followed by its reason phrase. Never any three digits: a truncated body's
# JSONDecodeError says "line 363 column 412".
_STATUS = re.compile(r"(?:\b(?:HTTP|[Ss]tatus|failed:?)\s*(\d{3})\b|\b(\d{3})(?=\s+[A-Z][a-z]))"
                     r"((?:\s+[A-Z][A-Za-z]*)*)")
# The answers that will not change within a round: refused credentials, forbidden,
# a proxy that will not carry the request, unavailable for legal reasons, and the 999
# LinkedIn sends a machine it is refusing. A 429 or a 5xx is worth asking again later.
REFUSING_STATUS = (401, 403, 407, 451, 999)


def _status(err: str | None) -> tuple[int, str] | None:
    """(code, "403 Forbidden") for the first HTTP error status an error names."""
    for m in _STATUS.finditer(str(err or "")):
        code = int(m.group(1) or m.group(2))
        if 400 <= code <= 599 or code == 999:
            return code, f"{code}{m.group(3)}".strip()
    return None


def cause(err: str | None) -> str:
    """What a failed request comes down to, short enough for a progress line:
    "403 Forbidden", "429 Too Many Requests", "timeout", or what a board said."""
    if not err:
        return ""
    said = _refusal(err)
    if said:
        return said
    status = _status(err)
    if status:
        return status[1]
    low = err.lower()
    if "timeout" in low or "timed out" in low:
        return "timeout"
    text = _EXIT.sub("", err.strip())
    try:
        body = json.loads(text)
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])[:60]
    except ValueError:
        pass
    named = re.match(r"([A-Z]\w*(?:Error|Exception))\b", text)
    return named.group(1) if named else (text[:60] or "failed")


def refused(err: str | None) -> str:
    """The cause when a failure is an answer that will not change within the round
    (REFUSING_STATUS, or a board's own refusal), else "": a timeout, a 429 or a 5xx
    is worth asking again."""
    said = _refusal(err)
    if said:
        return said
    status = _status(err)
    return status[1] if status and status[0] in REFUSING_STATUS else ""


def _remote_mark(location, remote: bool):
    """A row from a remote-filtered search says so in its location.

    The card carries only a city, so every US-remote row from a search for remote
    roles read as on-site in that city and the location gate failed it, which
    emptied the remote searches the boards were asked to run.
    """
    loc = str(location or "")
    if remote and "remote" not in loc.lower():
        return (loc + " (Remote)").strip()
    return location


# What a board prints after a title on its card, which a reader of the card's text takes
# as part of it: "Senior Analytics Engineer New Toronto, Ontario, Canada". Only a badge
# no title ends in is here: "Applied" ("Research Scientist, Applied") and "Hot" are not,
# and "New" is a badge only where nothing before it makes it a word of the title
# ("Brand New", "What's New"). The texts are LinkedIn's and Indeed's card labels.
_BADGE = re.compile(
    r"(?:^|[\s,;:|·•(\[-]+)(?:"
    r"new!?|promoted(?: by hirer)?|actively (?:hiring|recruiting|reviewing applicants)|"
    r"easy apply|reposted(?: \d+ \w+ ago)?|be an early applicant|early applicant|"
    r"be among the first \d+ applicants|urgently hiring|hiring urgently|urgent hire|"
    r"featured|top applicant|with verification|just posted|"
    r"(?:posted )?\d+ (?:minutes?|hours?|days?|weeks?|months?) ago|"
    r"(?:over )?\d+ applicants|\d+ (?:school )?alumni works? here|"
    r"\d+ connections? works? here|in your network|your profile matches this job|"
    r"responses managed off linkedin"
    r")[)\]]?\s*$", re.I)
_NEW_IN_TITLE = re.compile(r"\b(?:brand|what'?s|what’s|something|anything)\s+new!?[)\]]?\s*$", re.I)
# Words a location is written with beyond its own, so "Toronto, Ontario, Canada" after a
# title is still the row's own place when the row says "Toronto, ON". Never "remote" or
# "hybrid": a title that says so where its location does not is telling the gate something.
_PLACE_FILLER = {"greater", "area", "metropolitan", "metro", "region", "canada", "ca", "usa",
                 "us", "uk", "united", "states", "kingdom"}
# A title cut so it ends on one of these was never ended by a place ("Teacher of Reading").
_DANGLING = {"of", "for", "in", "at", "and", "&", "the", "to", "with", "on", "a", "an"}
_SEPARATORS = " \t,;:|-–—·•/("


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'’.-]*", s.lower())


def _strip_place(title: str, location: str) -> str:
    """`title` without a trailing copy of the row's own `location`, or as it is."""
    place = [w.strip(".") for w in _words(location)]
    if not place:
        return title
    city = _words(location.split(",")[0].split("(")[0])
    if not city:
        return title
    allowed = set(place) | _PLACE_FILLER
    # "Toronto, ON" and "Toronto, Ontario" are one place: a code brings its name in, and
    # a name its code (places.py's own tables).
    from places import SUBDIVISION_PAIRS
    for code, name in SUBDIVISION_PAIRS:
        if code in place or all(w in place for w in name.split()):
            allowed |= {code, *name.split()}
    # The last place in the title where the city starts, as whole words.
    lower = title.lower()
    for m in reversed(list(re.finditer(r"(?<![\w])" + re.escape(" ".join(city)) + r"(?![\w])",
                                       re.sub(r"\s+", " ", lower)))):
        tail = re.sub(r"\s+", " ", lower)[m.start():]
        if not all(w.strip(".") in allowed for w in _words(tail)):
            return title
        head = re.sub(r"\s+", " ", title)[:m.start()]
        # "Greater Toronto Area": the filler before the city goes with it.
        head = re.sub(r"(?:\bgreater|\bthe)\s*$", "", head, flags=re.I)
        head = head.rstrip(_SEPARATORS + ")").rstrip()
        if head.endswith("(") or not _words(head) or _words(head)[-1] in _DANGLING:
            return title
        return head
    return title


def clean_title(title, location="") -> str:
    """A board's title with the badges, a language tag before it and the repeat of the
    row's own place cut off.

    Rows from a card read as text carry what the card shows after the title ("New",
    "Promoted", "Actively hiring", the location again), and the title then failed every
    match on it: a dedupe, the tracker's own role, a search of the employer's board.
    Nothing that is a word of the title is cut ("Software Engineer, New Grad").
    """
    if not isinstance(title, str):
        return title
    t = re.sub(r"\s+", " ", title).strip()
    loc = str(location or "")
    for _ in range(6):
        before = t
        t = strip_language_tag(t)
        if loc:
            t = _strip_place(t, loc)
        m = _BADGE.search(t)
        if m and not (m.group(0).strip(" ([").lower().startswith("new")
                      and _NEW_IN_TITLE.search(t)):
            head = t[:m.start()].rstrip(_SEPARATORS).rstrip()
            if _words(head):
                t = head
        # A card that prints its title twice ("Data Analyst Data Analyst with verification").
        words = t.split(" ")
        half = len(words) // 2
        if len(words) % 2 == 0 and half and words[:half] == words[half:]:
            t = " ".join(words[:half])
        if t == before:
            break
    return t


def clean_row(row: dict) -> dict:
    """The row with its title cleaned (clean_title); the board's own kept as `title_seen`."""
    title = row.get("title")
    clean = clean_title(title, row.get("location") or "")
    if isinstance(title, str) and clean != title.strip():
        row = {**row, "title": clean, "title_seen": row.get("title_seen") or title}
    return row


def linkedin(q: str, loc: str, page: int, jobage: int,
             remote: bool = False) -> tuple[list[dict], str | None]:
    cmd = [*portals.runtime(), LINKEDIN(), "search", "-q", q, "-l", loc,
           "--jobage", str(jobage), "--page", str(page), "--format", "json"]
    if remote:
        cmd += ["--remote", "remote"]
    d, err = run(cmd)
    out = []
    for r in (d or {}).get("results", []):
        out.append({"id": r.get("id"), "title": r.get("title"),
                    "company": r.get("company"), "url": r.get("url"),
                    "location": _remote_mark(r.get("location"), remote),
                    "date": (r.get("date") or "")[:10],
                    "portal": "linkedin", "desc": None})
    return out, err


def _capped(text):
    """A body cut to as much as any stage reads (hydrate.BODY_CAP); anything else as it is."""
    return text[:BODY_CAP] if isinstance(text, str) else text


def freehire(q: str, page: int, jobage: int) -> tuple[list[dict], str | None]:
    d, err = run([*portals.runtime(), FREEHIRE(), "search", "-q", q,
                  "--country", PORTAL_COUNTRY, "--jobage", str(jobage), "--limit", "25",
                  "--page", str(page), "--format", "json"])
    out = []
    for r in (d or {}).get("results", []):
        out.append({"id": str(r.get("id")), "title": r.get("title"),
                    "company": r.get("company"), "url": r.get("url"),
                    "location": r.get("location"), "date": (r.get("date") or "")[:10],
                    "portal": "freehire", "desc": _capped(r.get("description"))})
    return out, err


def contract(skill: str, q: str, loc: str | None, page: int,
             jobage: int, remote: bool = False) -> tuple[list[dict], str | None]:
    """One search on a portal that follows the portal contract (/add-portal).

    A search result's `description` is kept as `snippet`, not as the body:
    most boards return a teaser there, and a teaser would stop hydrate.py
    fetching the real posting. Where the board's posting pages may not be
    fetched (`detail: false`), the snippet is all there is, and it is the body.
    """
    cmd = ([*portals.runtime(), portal_cli(skill), "search", "-q", q]
           + (["-l", loc] if loc else [])
           + (["--remote"] if remote else [])
           + ["--jobage", str(jobage), "--page", str(page), "--format", "json"])
    d, err = run(cmd)
    whole = not portals.has_detail(skill)
    out = []
    for r in (d or {}).get("results", []):
        text = _capped(r.get("description") or None)
        out.append({"id": None if r.get("id") is None else str(r.get("id")),
                    "title": r.get("title"), "company": r.get("company"),
                    "url": r.get("url"), "location": _remote_mark(r.get("location"), remote),
                    "date": (r.get("date") or "")[:10], "portal": portals.short(skill),
                    "desc": text if whole else None, "snippet": text})
    return out, err


def contract_portals(on: dict[str, bool]) -> list[str]:
    """Every portal that is on, is not one of the app's two, has a CLI and says
    it follows the contract. One that does not (the Danish boards, restored by
    hand, take none of these flags) would fail every request it was sent."""
    return [n for n, v in sorted(on.items())
            if v and n not in WIRED and portals.has_cli(n) and portals.follows_contract(n)]


def portal_locations(skill: str) -> list[str | None]:
    """Every place the person searches, as this board writes them where it differs.

    It used to be the first of SCRAPE_LOCATIONS alone, so a board built for a
    person searched their home city and nothing else: not the towns around it,
    not the region, not the country, while LinkedIn searched all of them.
    """
    if not portals.takes_location(skill):
        return [None]
    places = PORTAL_LOCATIONS.get(skill) or LOCATIONS
    return list(dict.fromkeys(places))


# A person's portal gets this long in a round, and stops after this many
# failures in a row. A board that is blocked or down fails every request, and
# each can take run()'s 90-second timeout: without a stop, 60 of them outlast
# the scrape stage's whole budget and the round is lost, LinkedIn and all.
SWEEP_BUDGET = 20 * 60
SWEEP_MAX_FAILS = 3

# And it never holds the round. Two rounds one evening waited 20 minutes for their scrape,
# LinkedIn and freehire done after under seven: the paced boards spent the last 13 adding about
# 1% of what reached the list and nothing at fit 75 or more, while one board that did find
# strong roles needed three minutes of requests (issue 301). The order of a board's requests is
# the order of value (page one of every search at the first place first, the cursor carrying
# the rest to the next round), so a board stops PACED_AFTER_POOL seconds after LinkedIn and
# freehire finish, though never before PACED_MIN into the scrape. Where neither of those is
# searched the board is the search, and keeps SWEEP_BUDGET.
PACED_AFTER_POOL = 60
PACED_MIN = 3 * 60
PACED_STOP = "LinkedIn and freehire had finished, and a slow board does not hold the round"
# And a board's time follows what it has done for the person (board_share). The same evening's
# four boards put 1, 19, 2 and 79 postings on the list, the strong ones all from the last, and
# each was given the same minute (issue 327). So each round keeps, in the board's place in the
# cursor (record_yield), how many of its jobs reached the list scoring LISTED_AT or more and
# passing every rule, over its last YIELD_ROUNDS rounds. A board that pays goes on
# PACED_PER_LISTED more after LinkedIn and freehire for each such job in an average round, up
# to its whole SWEEP_BUDGET; one with none in its last YIELD_DRY rounds is tried for its first
# PACED_FLOOR only, so one that starts paying is still noticed; a board with fewer rounds to
# judge it by keeps PACED_AFTER_POOL. Alone, with LinkedIn and freehire not searched, it keeps
# SWEEP_BUDGET, and a time the person set (PORTAL_MINUTES) stands.
LISTED_AT = 60
YIELD_ROUNDS = 5
YIELD_DRY = 3
PACED_FLOOR = 60
PACED_PER_LISTED = 60
# An employer a board was asked for by name and had nothing from (no posting at that employer
# in its answer) is not asked for on that board again for this many days. One board answered
# 59 such searches in a round with nothing new; the four answered 400 with 24 (issue 301).
EMPTY_DAYS = 30

# How long one paced request takes, its crawl-delay included, decides how many fit the
# budget. One board at a crawl-delay of 5 seconds managed about 7 a minute, so its
# 20 minutes held about 150 of its 243 requests whatever happened, and nothing said so.
# The round measures it (save_cursor keeps it for the next round), takes the health
# probe's time where nothing was measured yet, and guesses this much where neither is.
DEFAULT_REQUEST_SECONDS = 3.0
# {portal's short name: seconds its probe took}, filled by canary().
PROBE_SECONDS: dict[str, float] = {}


def request_seconds(skill: str) -> float:
    """Seconds one request to a paced board takes, its wait included."""
    delay = portals.crawl_delay(skill)
    last = (_cursor().get(skill) or {}).get("secs")
    if isinstance(last, (int, float)) and not isinstance(last, bool) and last > 0:
        return max(float(last), delay)
    probe = PROBE_SECONDS.get(portals.short(skill))
    return delay + (probe if probe is not None else DEFAULT_REQUEST_SECONDS)


def describe(task: tuple) -> str:
    """One request as a person reads it: "demand planner" (Next Town, page 2)."""
    q, loc, pg = task[1:4]
    where = loc or ("remote" if len(task) > 4 and task[4] else "")
    return f'"{q}" ({where + ", " if where else ""}page {pg})'


def plan_line(skill: str, total: int, delay: float, budget: float | None = None) -> str:
    """Said before a paced sweep that will not fit its budget, or ""."""
    budget = SWEEP_BUDGET if budget is None else budget
    per = request_seconds(skill)
    fits = int(budget // per) if per > 0 else total
    if fits >= total:
        return ""
    return (f"portals: {portals.short(skill)} plans {total} requests, {delay:g}s apart and "
            f"about {per:.1f}s each, so about {fits} fit its {_minutes(budget)} this round: "
            "page one of every search at its first place goes first and the places "
            "further out last, and later rounds reach the rest")


def _minutes(secs: float) -> str:
    """Seconds as whole minutes in words: "1 minute", "20 minutes"."""
    n = max(1, int(secs / 60 + 0.5))
    return f"{n} minute{'' if n == 1 else 's'}"


class Share(NamedTuple):
    """One paced board's time in a round (board_share)."""
    most: float               # seconds from the start of its searches it never goes past
    after: float | None       # seconds it goes on after LinkedIn and freehire finish, or None
    least: float              # seconds from the start it has, whatever finished first
    why: str                  # its time and why, in plain words, for the round's summary
    stop: str                 # what its stopped line says when its time was up


def listed(entry) -> list[int]:
    """How many of a board's jobs reached the list in each of its last YIELD_ROUNDS rounds,
    the newest last, from its place in the cursor (record_yield)."""
    got = (entry or {}).get("yield") if isinstance(entry, dict) else None
    out = []
    for y in got if isinstance(got, list) else []:
        n = y.get("listed") if isinstance(y, dict) else None
        if isinstance(n, int) and not isinstance(n, bool) and n >= 0:
            out.append(n)
    return out[-YIELD_ROUNDS:]


def _own_minutes(skill: str) -> float | None:
    """The minutes the person gave this board (PORTAL_MINUTES), or None."""
    for name in (skill, portals.short(skill)):
        v = PORTAL_MINUTES.get(name)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    return None


def board_share(skill: str, pooled: bool, cursor: dict | None = None) -> Share:
    """The time one of the person's own boards has in this round, and why: the time the person
    set for it; its whole budget where LinkedIn and freehire are not searched; its first
    PACED_FLOOR where none of its jobs reached the list in its last YIELD_DRY rounds; a minute
    after LinkedIn and freehire, and PACED_PER_LISTED more for each of its jobs that reached
    the list in an average recent round, where it has found some; and, with fewer rounds to
    judge it by, the minute after them every board had before (issue 327)."""
    own = _own_minutes(skill)
    if own is not None:
        most = min(own * 60, SWEEP_BUDGET)
        said = _minutes(most)
        return Share(most, None, 0, f"{said}, the time you set for it"
                     + (", the most a board is given" if own * 60 > SWEEP_BUDGET else ""),
                     f"the {said} you set for it {'was' if said == '1 minute' else 'were'} up")
    if not pooled:
        return Share(SWEEP_BUDGET, None, 0,
                     f"its whole {_minutes(SWEEP_BUDGET)}: LinkedIn and freehire are not "
                     "searched, so it is the search", "")
    rec = listed((cursor if cursor is not None else _cursor()).get(skill))
    first = "first minute" if _minutes(PACED_FLOOR) == "1 minute" else \
        f"first {_minutes(PACED_FLOOR)}"
    least = _minutes(PACED_MIN)
    if len(rec) >= YIELD_DRY and not any(rec[-YIELD_DRY:]):
        return Share(PACED_FLOOR, None, 0,
                     f"its {first} only: none of its jobs reached your list in its last "
                     f"{YIELD_DRY} searches, and it is still tried each search, so a board "
                     "that starts finding them is noticed",
                     f"its {first} was up: none of its jobs reached your list in its last "
                     f"{YIELD_DRY} searches")
    if any(rec):
        avg = sum(rec) / len(rec)
        after = min(SWEEP_BUDGET, PACED_AFTER_POOL + PACED_PER_LISTED * avg)
        each = f"{avg:.1f}".rstrip("0").rstrip(".")
        return Share(SWEEP_BUDGET, after, PACED_MIN,
                     f"{_minutes(after)} after LinkedIn and freehire finish ({least} at "
                     "least): a minute, and a minute more for each of its jobs scoring "
                     f"{LISTED_AT} or more that reached your list in an average search "
                     f"({each} over its last {len(rec)})",
                     "LinkedIn and freehire had finished, and the time its jobs on your list "
                     "earn it was up")
    judged = ("no searches of it to judge by yet" if not rec else
              f"only {len(rec)} search{'' if len(rec) == 1 else 'es'} of it to judge by so far")
    return Share(SWEEP_BUDGET, PACED_AFTER_POOL, PACED_MIN,
                 f"a minute after LinkedIn and freehire finish ({least} at least), as for any "
                 f"new board: {judged}", PACED_STOP)


def share_stop(share: Share, began: float, pool_ended: list, clock=time.monotonic):
    """The `stop` a board's sweep asks before each request: its Share's reason once LinkedIn
    and freehire have finished (`pool_ended` holds when) and its time after them is up, never
    before `share.least` from `began`; "" until then, and always for a share with no `after`
    (its own budget stops it)."""
    def stop() -> str:
        if share.after is None or not pool_ended:
            return ""
        return share.stop if clock() >= max(pool_ended[0] + share.after,
                                            began + share.least) else ""
    return stop


def unsent_line(name: str, rest: list[tuple], total: int, why: str, show: int = 3) -> str:
    """What a stopped sweep did not send: the count, the first few, and why."""
    first = "; ".join(describe(t) for t in rest[:show])
    more = f"; and {len(rest) - show} more" if len(rest) > show else ""
    return (f"portals: {name} stopped, {why}: {len(rest)} of {total} requests not sent, "
            f"the first: {first}{more}. Later rounds reach them (documents/rounds/.sweep/).")


_REQUESTS_LOCK = threading.Lock()


def request_line(skill: str, task: tuple, got: int, new: int | None, err: str | None,
                 secs: float, at: str | None = None) -> str:
    """One paced request as a line of the round's log: when, which board, what it asked,
    what came back and how long it took. Short, because a round sends hundreds."""
    at = at or dt.datetime.now().strftime("%H:%M:%S")
    what = f"failed ({cause(err)})" if err else (
        f"{got} row{'' if got == 1 else 's'}" + (f", {new} new" if new is not None else ""))
    return f"{at} request {portals.short(skill)} {describe(task)}: {what}, {secs:.1f}s"


def _log_request(path: str | None, line: str) -> None:
    if not path:
        return
    try:
        with _REQUESTS_LOCK, open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class PageWalk:
    """Which deeper pages of a search are worth asking for: none past a page that came back
    empty, or with nothing on it the search's own earlier pages did not already have.

    The skill's rule 12 is to walk a search's pages until one comes back empty or wholly
    duplicated. The pages were a plan, every one sent whatever page one said: a search
    with one posting on page one still sent pages two to five, to LinkedIn among others,
    whose volume the skill asks to keep low and which counts toward the cap on a
    person's own computer. A page is judged only once it has answered, so a deeper page
    already in flight is still sent."""

    def __init__(self):
        self.ended: dict = {}
        self.found: dict = {}
        self.lock = threading.Lock()

    def past_end(self, search, page) -> bool:
        with self.lock:
            return search in self.ended and page > self.ended[search]

    def answered(self, search, page, rows) -> None:
        from lookup_score import norm
        rows = [r for r in rows or () if isinstance(r, dict)]
        keys = {norm(r["url"]) or r["url"] for r in rows if r.get("url")}
        with self.lock:
            prior = self.found.setdefault(search, set())
            if not rows or (keys and keys <= prior):
                self.ended[search] = min(self.ended.get(search, page), page)
            prior |= keys


def sweep(skill: str, tasks: list[tuple], jobage: int, sleep=time.sleep,
          clock=time.monotonic, tally: "Tally | None" = None,
          on_rows=None, log=None, requests=None,
          covered=None, kept=None, stop=None, budget: float | None = None,
          over: str = "") -> tuple[list[dict], int, list[str]]:
    """Every request for one person's portal, one at a time, `crawl-delay` apart.

    Its own thread, so a board that asks for five seconds between requests
    takes its time without holding a worker the app's portals need. It waits
    before the first request too: the health probe has just asked. After that a
    request starts a crawl-delay after the last one started, never while it runs:
    waiting the whole delay after each one ended added every request's own time
    to every gap, so the board got its requests further apart than it asked and the
    sweep took that much longer. It says up
    front when the requests will not all fit its budget, stops at SWEEP_BUDGET or
    SWEEP_MAX_FAILS failures in a row, and names what it did not send and why.

    `requests`, a file, gets one line per request (request_line), with how many of
    its rows were new to the round when `on_rows` says so by returning a count.

    `covered`, given an employer's key, says whether that employer's own board was read this
    round: its search here (NAMED) is then not sent, and counts as gone through.

    `kept` holds what the board answered in the last PACED_TTL: a request it answered then is
    not sent again (it counts as gone through, in `tally.kept`), and every answer is kept.

    `stop`, asked before each request, says why the sweep should stop now ("" to go on):
    LinkedIn and freehire have finished and the board's time after them is up (share_stop).
    An employer searched for by name is recorded in `tally.named` as whether the board had
    anything at that employer.

    `budget`, its seconds in all (SWEEP_BUDGET unless its Share gives it less), and `over`,
    what its stopped line says when they run out.
    """
    budget = SWEEP_BUDGET if budget is None else budget
    delay, rows, failed = portals.crawl_delay(skill), [], []
    start, streak, sent, last, why = clock(), 0, 0, "", ""
    began = None
    plan = plan_line(skill, len(tasks), delay, budget)
    if plan:
        _say(plan, log)
    if tally is not None:
        tally.ends = start + budget
    walk, at, ended, skipped, reused = PageWalk(), 0, 0, 0, 0
    for at, task in enumerate(tasks):
        q, loc, pg = task[1:4]
        remote = len(task) > 4 and task[4]
        search = (q, loc, bool(remote))
        if walk.past_end(search, pg):
            ended += 1                        # its search ran out on an earlier page
            if tally is not None:
                tally.ended = ended
            continue
        employer = NAMED.get((skill, q))
        if employer and covered is not None and covered(employer):
            skipped += 1                      # its own board was read this round
            if tally is not None:
                tally.covered = skipped
            continue
        had = kept.get(paced_key(skill, task, jobage), PACED_TTL) if kept is not None else None
        if had is not None:
            reused += 1                       # answered in the last PACED_TTL: not sent again
            walk.answered(search, pg, had)
            rows += had
            if on_rows and had:
                on_rows(list(had))
            if tally is not None:
                tally.kept = reused
            continue
        if streak >= SWEEP_MAX_FAILS:
            why = f"{streak} failures in a row ({last})"
            failed.append(f"stopped after {streak} failures in a row; "
                          f"{len(tasks) - at} requests not sent ({last})")
            break
        if clock() - start > budget:
            why = over or f"its {budget // 60:g}-minute budget ran out"
            break
        why = stop() if stop is not None else ""
        if why:
            break
        if delay:
            wait = delay if began is None else began + delay - clock()
            if wait > 0:
                sleep(wait)
        began = clock()
        try:
            got, err = (contract(skill, q, loc, pg, jobage, remote=True) if remote
                        else contract(skill, q, loc, pg, jobage))
        except Exception as e:
            got, err = [], f"{type(e).__name__}: {str(e)[:120]}"
        sent += 1
        streak = streak + 1 if err else 0
        if err:
            failed.append(err)
            last = cause(err)
        else:
            walk.answered(search, pg, got)
            if kept is not None:
                kept.put(paced_key(skill, task, jobage), list(got))
            if employer and tally is not None:
                tally.named[q] = any(_employer_key(r.get("company")) == employer for r in got)
        rows += got
        new = None
        if on_rows and got:
            new = on_rows(list(got))
        if requests:
            _log_request(requests, request_line(
                skill, task, len(got), new if isinstance(new, int) else (0 if not got else None),
                err, clock() - began))
        if tally is not None:
            tally.sent = sent
            if err:
                tally.failure(err)
            else:
                tally.success()
    else:
        at = len(tasks)                       # every task gone through
    rest = tasks[at:] if why else []
    if rest:
        _say(unsent_line(portals.short(skill), rest, len(tasks), why), log)
    if tally is not None:
        tally.sent = sent
        tally.per = (clock() - start) / sent if sent else None
        if rest:
            tally.stopped = why
        tally.finished = True
    return rows, sent, failed


# ------------------------------------------------------------------ the pool
#
# LinkedIn and freehire go through a pool of workers, and the pool had no clock of
# its own. On a person's own computer, rate-limited by LinkedIn, it ran into the
# scrape stage's 45-minute limit; the stage was killed with everything it had found
# in memory, and the round was lost, 45 minutes of it, with nothing written and
# nothing in the log about LinkedIn or freehire at all. So the pool stops at
# POOL_BUDGET, well inside the stage limit, writes what it has, and says what it
# did not send; it backs off a portal that answers 429 (Retry-After when the error
# carries one), halves that portal's share of the workers, and stops it after
# POOL_MAX_LIMITED in a row; and it prints a portal's progress line as it changes
# (progress_lines), so a chat can tell a slow round from a hung one.
POOL_BUDGET = 20 * 60
POOL_MAX_LIMITED = 3
# How long after the scrape starts an employer board whose site asked to slow down is waited
# for, to be read once more (ats_boards.fetch_all, issue 302): a host that answers 429 with no
# Retry-After is held ten minutes, and the stage then ends a few minutes after the rest.
BOARD_RETRY_SECONDS = 15 * 60
# A portal that gives the same failure this many times running, with no success
# between, is stopped: freehire answered 403 Forbidden to all 300 of one round's
# requests and the pool sent every one. Five, where a paced board stops at three
# (SWEEP_MAX_FAILS), because the pool has several requests in flight at once (four on
# a person's own computer) and one bad moment can fail those together; five identical
# failures running is more than that. A 429 keeps its own, gentler rule above.
POOL_MAX_FAILS = 5
BACKOFF_SECONDS = 60
PROGRESS_SECONDS = 60
# A portal still sending whose line has not changed in this long is said again, so a
# hung one is told from a slow one; every other line is printed only when it changes.
HEARTBEAT_SECONDS = 5 * 60
_RETRY_AFTER = re.compile(r"retry[- ]after[\"':= ]+(\d{1,5})", re.I)


def rate_limited(err: str | None) -> bool:
    return bool(err) and (" 429" in err or "429 " in err or "too many requests" in err.lower())


def retry_after(err: str | None) -> int | None:
    m = _RETRY_AFTER.search(err or "")
    return int(m.group(1)) if m else None


class Tally:
    """One portal's requests in a round: what went, what failed and why, and whether it
    stopped. Shared by the pool, the paced sweeps and the progress line."""

    def __init__(self, name: str, total: int, limit: int = 1, cap: int | None = None):
        self.name, self.total, self.limit, self.cap = name, total, max(1, limit), cap
        self.sent = self.active = self.limited = self.timeouts = self.streak = 0
        self.failed: list[str] = []
        self.until = 0.0
        self.stopped = ""
        self.capped = 0
        self.ended = 0                    # deeper pages not sent: their search had run out
        self.covered = 0                  # employer searches not sent: its own site was read
        self.kept = 0                     # requests not sent: answered a short while ago
        self.named: dict[str, bool] = {}  # an employer's search: did the board have it there
        # Failed requests, counted as they land with their causes. `failed` also
        # carries the note a stopped portal leaves, which is not a request.
        self.errors = 0
        self.causes: Counter = Counter()
        self.same, self.last = 0, ""      # the run of identical failures, and its cause
        self.queued = 0                   # the pool's requests for it not yet taken
        self.finished = False             # nothing more will be sent
        self.ends: float | None = None    # when its budget runs out, on its own clock
        self.per: float | None = None     # seconds a paced request took, wait included

    def failure(self, err: str) -> None:
        c = cause(err) or "failed"
        self.failed.append(err)
        self.errors += 1
        self.causes[c] += 1
        self.same = self.same + 1 if c == self.last else 1
        self.last = c
        self.limited += int(rate_limited(err))
        self.timeouts += int("timeout" in str(err).lower())

    def success(self) -> None:
        self.same, self.last = 0, ""

    def _failures(self) -> str:
        said = f"{self.errors} failed"
        if not self.causes:
            return said
        top = self.causes.most_common(2)
        if len(self.causes) == 1:
            return f"{said} ({top[0][0]})"
        return (f"{said} (" + ", ".join(f"{n}x {c}" for c, n in top)
                + (", and others" if len(self.causes) > 2 else "") + ")")

    def line(self, left: float | None = None) -> str:
        bits = [f"{self.sent}/{self.total} sent", self._failures()]
        if self.limited or self.timeouts:
            bits.append(f"{self.limited} rate-limited (429), {self.timeouts} timed out")
        if self.capped:
            bits.append(f"{self.capped} deeper page(s) left by the round's cap")
        if self.ended:
            bits.append(f"{self.ended} deeper page(s) not needed, their search had run out")
        if self.covered:
            bits.append(f"{self.covered} employer search(es) not needed, the employer's own "
                        "job site was read")
        if self.kept:
            bits.append(f"{self.kept} answered a short while ago, not asked again")
        if self.stopped:
            bits.append(f"stopped: {self.stopped}")
        elif self.finished:
            bits.append("done")
        elif left is not None:
            bits.append(f"{max(0, int(left // 60))} min left")
        return f"progress: {self.name} " + ", ".join(bits)


def progress_lines(tallies: list[Tally], shown: dict, now: float,
                   quiet: float | None = None) -> list[str]:
    """The progress lines worth printing now.

    Every portal's line was printed every minute, finished or not, each finished one
    with a countdown that meant nothing to it, so after 77 lines one round's log was
    mostly repeats. A line is printed when it changes, once more when the portal
    finishes ("done" or "stopped: <why>"), and, for a portal still sending that has not
    moved, again after HEARTBEAT_SECONDS. Only a portal still sending has a countdown.
    `shown` is the caller's memory between calls."""
    quiet = HEARTBEAT_SECONDS if quiet is None else quiet
    out = []
    for t in tallies:
        seen = shown.setdefault(t.name, {"line": None, "at": None, "closed": False})
        if seen["closed"]:
            continue
        line = t.line()
        stale = not t.finished and seen["at"] is not None and now - seen["at"] >= quiet
        if line == seen["line"] and not stale:
            continue
        sending = not (t.finished or t.stopped)
        out.append(t.line(t.ends - now if sending and t.ends is not None else None))
        seen.update(line=line, at=now, closed=t.finished)
    return out


def _say(line: str, log=None) -> None:
    print(line, file=sys.stderr, flush=True)
    if log:
        try:
            with open(log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def pool(jobs: list[tuple], workers: int, budget: float = POOL_BUDGET, cap: int | None = None,
         clock=time.monotonic, sleep=time.sleep, tallies: dict | None = None,
         on_rows=None, on_sent=None, page_of=None, on_answer=None) -> tuple[list[dict], dict]:
    """Run [(portal, fn, args)] on `workers` threads until done or `budget` runs out.

    Each portal gets a Tally (in `tallies`, shared with the progress line). A 429
    halves that portal's share of the workers and pauses it (Retry-After, else
    BACKOFF_SECONDS times the run of 429s); POOL_MAX_LIMITED in a row stops it, and
    POOL_MAX_FAILS identical failures in a row of any kind stop it too. `cap`
    is the most requests a portal may send. `on_rows` sees each batch of rows as it
    lands, which is how a partial scrape survives a stage that is killed, and
    `on_sent` each job that was answered without an error, and `on_answer` each such job
    with its rows. `page_of` gives a job's (search, page), and a page past where its search
    ran out (PageWalk) is not sent.
    Returns (rows, tallies)."""
    tallies = {} if tallies is None else tallies
    start = clock()
    mine = list(dict.fromkeys(j[0] for j in jobs))
    planned: dict[str, int] = {}
    for portal in mine:
        n = planned[portal] = sum(1 for j in jobs if j[0] == portal)
        t = tallies.setdefault(portal, Tally(portal, min(n, cap) if cap else n, workers, cap))
        t.queued, t.ends = n, start + budget
    walk = PageWalk()

    def past_end(job) -> bool:
        where = page_of(job) if page_of else None
        return bool(where) and walk.past_end(*where)
    # One queue a portal, each in the order given, every job numbered by its place in
    # that order. A single queue was walked from the front on every take, past every
    # job of a portal that had stopped or reached its cap, which grows with the square
    # of the queue: the next job is the lowest-numbered head among portals that may
    # send, which is the same job, found by looking at one head a portal.
    queues: dict[str, deque] = {portal: deque() for portal in mine}
    for n, job in enumerate(jobs):
        queues[job[0]].append((n, job))
    rows, lock = [], threading.Lock()

    def drop_ended(portal, heads_only=False):
        """Take out the portal's queued pages that are past where their search ran out:
        the next ones to send, or, once sending is over, every one, so what is reported
        unsent is what was worth sending."""
        q, t = queues[portal], tallies[portal]
        keep = deque()
        while q:
            n, job = q.popleft()
            if not past_end(job):
                keep.append((n, job))
                if heads_only:
                    break
                continue
            t.queued -= 1
            t.ended += 1
            planned[portal] -= 1
            t.total = min(planned[portal], t.cap) if t.cap else planned[portal]
        q.extendleft(reversed(keep))

    def take():
        now = clock()
        if now - start >= budget:
            return "done", None
        waits, best = [], None
        for portal, q in queues.items():
            t = tallies[portal]
            drop_ended(portal, heads_only=True)
            if not q:
                continue
            if t.stopped or (t.cap and t.sent + t.active >= t.cap):
                continue
            if t.until > now:
                waits.append(t.until - now)          # backing off after a 429
                continue
            if t.active >= t.limit:
                waits.append(0.2)                    # its share of the workers is busy
                continue
            if best is None or q[0][0] < queues[best][0][0]:
                best = portal
        if best is not None:
            _n, job = queues[best].popleft()
            t = tallies[best]
            t.active += 1
            t.queued -= 1
            return "go", job
        return ("wait", max(0.2, min(waits))) if waits else ("done", None)

    def worker():
        while True:
            with lock:
                what, job = take()
            if what == "done":
                return
            if what == "wait":
                sleep(min(job, 5.0))
                continue
            portal, fn, args = job
            try:
                got, err = fn(*args)
            except Exception as e:  # noqa: BLE001  one request never ends the pool
                got, err = [], f"{type(e).__name__}: {str(e)[:120]}"
            with lock:
                t = tallies[portal]
                t.active -= 1
                t.sent += 1
                if err:
                    t.failure(err)
                    if rate_limited(err):
                        t.streak += 1
                        t.limit = max(1, t.limit // 2)
                        t.until = clock() + (retry_after(err) or BACKOFF_SECONDS * t.streak)
                        if t.streak >= POOL_MAX_LIMITED:
                            t.stopped = (f"rate-limited {t.streak} times in a row (HTTP 429); "
                                         "the portal is asking for less")
                    if t.same >= POOL_MAX_FAILS and not t.stopped:
                        t.stopped = f"{t.same} failures in a row, each {t.last}"
                else:
                    t.streak = 0
                    t.success()
                    where = page_of(job) if page_of else None
                    if where:
                        walk.answered(*where, got)
                    rows.extend(got or ())
                    if on_rows and got:
                        on_rows(list(got))
                    if on_sent:
                        on_sent(job)
                    if on_answer:
                        on_answer(job, list(got or ()))
                if not t.active and (t.stopped or not t.queued
                                     or (t.cap and t.sent >= t.cap)):
                    t.finished = True

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    for portal in queues:
        drop_ended(portal)
    for portal, t in tallies.items():
        left = len(queues.get(portal, ()))
        if not left or t.stopped:
            if left:
                t.failed.append(f"{left} request(s) not sent: {t.stopped}")
            continue
        if clock() - start >= budget:
            t.stopped = f"its {int(budget // 60)}-minute budget ran out"
            t.failed.append(f"{left} request(s) not sent: {t.stopped}")
        elif t.cap:
            # The cap is the plan, not a failure: the deep pages it leaves are what a
            # gentler round chose not to ask for.
            t.capped = left
    for portal in mine:
        tallies[portal].finished = True
    return rows, tallies


# ------------------------------------------------------------------ canary
#
# A portal that BREAKS is loud. A portal that goes quiet is not, and quiet is
# the failure mode that actually happens: a board restyles its markup, the
# extractor stops matching, every request returns HTTP 200 with an empty list,
# and the round reports a thin local market. Nothing above catches it,
# because `failure_report` counts requests that errored and none of these did.
#
# The cost of getting this wrong is the whole point of the repo. A round that
# says MISSED spends three widenings, reports the market as thin, and the
# candidate reads a true-sounding sentence about a quiet week while an entire
# job board has been invisible for days.
#
# So each enabled portal is probed once, before the sweep, with a query so
# broad that zero results cannot be the market's fault. Zero results with no
# error is the signal: the portal answered, and had nothing to say about
# "data" in the whole country, which is not a thing that is true.
# A word every board in the person's market has thousands of postings for. The
# default suits an English-language board; a board in another language, or a
# field where "data" is rare, names its own (search.py CANARY_QUERY).
CANARY_QUERY = getattr(_S, "CANARY_QUERY", "data")
CANARY_LOCATION = getattr(_S, "CANARY_LOCATION", LOCATIONS[-1] if LOCATIONS else "")
# A generous age window, so the probe is not measuring how recently anyone
# posted. Wider than any real round would use.
CANARY_JOBAGE = 30


# A probe whose error will not change within the round (refused()) marks the portal
# down with this before what it said, and main() sends it nothing more. It used to be
# "left to the scrape": freehire's 403 Forbidden went on to fail all 300 requests, and a
# board's THROTTLED (it was redirecting searches to /sandbox, which its robots.txt
# disallows) was learned only mid-sweep, after its sweep time was spent.
REFUSED = "refused the probe, so nothing more is sent to it this round: "


def not_searched(health: dict[str, tuple[bool, str]]) -> dict[str, str]:
    """{portal: what it said} for every portal the probe found refusing."""
    return {n: d[len(REFUSED):] for n, (h, d) in health.items()
            if not h and d.startswith(REFUSED)}


def canary(jobage: int = CANARY_JOBAGE,
           on: dict[str, bool] | None = None) -> dict[str, tuple[bool, str]]:
    """One broad probe per enabled portal. {portal: (healthy, detail)}.

    Down is either silent (no results and no error: a broken extractor) or refusing
    (`REFUSED`, then what the portal said). Any other error is left to the scrape."""
    on = portals.enabled() if on is None else on
    out: dict[str, tuple[bool, str]] = {}
    probes = [
        ("linkedin", lambda: linkedin(CANARY_QUERY, CANARY_LOCATION, 1, jobage)),
        ("freehire", lambda: freehire(CANARY_QUERY, 1, jobage)),
    ]
    wanted = {short for skill, short in WIRED.items() if on.get(skill)}
    # A person's board is probed with its own word (`canary-query:`, a board for
    # nurses has few postings saying "data") over CANARY_JOBAGE, not the round's
    # window: a field board can go a week without a new posting.
    for skill in contract_portals(on):
        loc = portal_locations(skill)[0]
        word = portals.meta(skill).get("canary-query") or CANARY_QUERY
        probes.append((portals.short(skill),
                       functools.partial(contract, skill, word, loc, 1,
                                         max(jobage, CANARY_JOBAGE))))
        wanted.add(portals.short(skill))
    probes = [(name, fn) for name, fn in probes if name in wanted]

    def ask(fn):
        began = time.monotonic()
        try:
            rows_, err = fn()
        except Exception as e:                      # a build or resolve failure
            return None, f"{type(e).__name__}: {str(e)[:150]}", None
        return rows_, err, time.monotonic() - began

    # Every portal at once: one request each, to hosts of their own, and the round
    # waited for each in turn (one board's probe alone took up to half a minute).
    # The answers are read in the order the probes are listed, as before.
    with ThreadPoolExecutor(max_workers=max(1, len(probes))) as ex:
        answers = list(ex.map(lambda p: ask(p[1]), probes))
    for (name, _fn), (rows_, err, took) in zip(probes, answers):
        if took is None:
            out[name] = (False, err)
            continue
        PROBE_SECONDS[name] = took
        if err and refused(err):
            out[name] = (False, REFUSED + refused(err))
        elif err:
            # A timeout, a 429 or a 5xx may not happen again, and the pool's backoff,
            # its streak stop and the failure fraction cover it if it does.
            out[name] = (True, f"probe errored ({err[:80]}), left to the scrape")
        elif not rows_:
            out[name] = (False, f'0 results for the probe query in '
                                f'{CANARY_LOCATION if name in WIRED.values() else "its search"}')
        else:
            out[name] = (True, f"{len(rows_)} results")
    return out


def blocked_say(refusing: dict[str, str]) -> str:
    """In a cloud chat, when a portal refused because this chat's cloud settings block its
    site: the plain words and the fix for the person (tools/env_check.py), else "". The
    round said "DOWN linkedin: refused the probe" and the chat told a beginner the boards
    were "blocked from this environment", which said nothing they could act on."""
    if not refusing or not CLOUD:
        return ""
    try:
        import env_check
        names = env_check.blocked_names()
        return env_check.blocked_say(names) if names else ""
    except Exception:  # noqa: BLE001  a message must never break a round
        return ""


def blocked_notes() -> list[str]:
    """The line for Claude beside `blocked_say`, never said to the person: the fix's steps
    are old enough to re-check (env_check.blocked_notes). [] when they are fresh."""
    try:
        import env_check
        return env_check.blocked_notes()
    except Exception:  # noqa: BLE001  a note must never break a round
        return []


def canary_report(health: dict[str, tuple[bool, str]]) -> tuple[str, bool]:
    """A human line per portal, and whether every portal is usable."""
    lines, ok, silent = [], True, False
    for name, (healthy, detail) in sorted(health.items()):
        lines.append(f"  {'OK  ' if healthy else 'DOWN'} {name}: {detail}")
        ok = ok and healthy
        silent = silent or (not healthy and not detail.startswith(REFUSED))
    if silent:
        lines.append("A portal returning nothing to a deliberately broad query is "
                     "broken, not evidence of a thin market. Fix the portal before "
                     "reading this round's yield.")
    if not_searched(health):
        lines.append("A portal that refuses the probe would refuse its sweep too, so it is "
                     "sent nothing more, and this round is not a full picture of the market "
                     "without it.")
    return "\n".join(lines), ok


# More than this fraction of requests failing means the round is not a picture
# of the market, whatever the file size says.
MAX_FAILED_FRACTION = 0.25


def failure_report(sent: dict[str, int], failed: dict[str, list[str]]) -> tuple[str, bool]:
    """A per-portal failure summary and whether the round should be trusted."""
    lines = []
    total = sum(sent.values())
    nfail = sum(len(v) for v in failed.values())
    for portal, n in sorted(sent.items()):
        f = failed.get(portal, [])
        line = f"{portal}: {len(f)}/{n} requests failed"
        if f:
            from collections import Counter
            top = Counter(r[:60] for r in f).most_common(2)
            line += " (" + "; ".join(f"{c}x {r}" for r, c in top) + ")"
        lines.append(line)
    bad = total > 0 and nfail / total > MAX_FAILED_FRACTION
    if bad:
        lines.append(f"FAIL: {nfail}/{total} requests failed, above "
                     f"{MAX_FAILED_FRACTION:.0%}; the scrape is not a picture of the market")
    return "\n".join(lines), bad


# What a person's portal did not reach last round, so the next round starts there:
# {portal: {"mode": "tail" or "all", "next": an index into what rotates, "sent": the
# requests it sent, "date": the round}}. "tail" while the board gets through its
# core each round; "all" once it did not, so a board too slow even for its core
# still reaches every request over successive rounds.
#
# Under documents/rounds, which every session commits, in a folder of its own. It was
# documents/rounds/.sweep.json, beside the summaries, on the reasoning that a dotfile is
# out of the way: a person's own test reads every documents/rounds/*.json and requires
# each to be named like a round (r19), pathlib's glob matches dotfiles, and every
# repo's local CI failed after its first round. Nothing a round writes at the top of
# documents/rounds is anything but a round summary now. The old file is read until a
# round (save_cursor) or the sync (`--move-cursor`, the sweep-cursor-moved upgrade)
# moves it. Read at call time; a test sets SWEEP_STATE to a path of its own.
SWEEP_STATE: str | None = None


def _sweep_paths() -> tuple[str, str]:
    """(where the cursor lives, where 3.7.0 put it, or "" for a test's own path)."""
    if SWEEP_STATE:
        return SWEEP_STATE, ""
    return (person.state("documents", "rounds", ".sweep", "cursor.json"),
            person.state("documents", "rounds", ".sweep.json"))


# This round's plan per person portal: (mode, core requests, rotating length, offset).
PLAN: dict[str, tuple[str, int, int, int]] = {}
# This round's employer searches on a person's portals: {(portal, query): the employer's key}.
# One whose own board is on file is sent only if that board was not read (`sweep`'s
# `covered`), and one the board had nothing from is remembered (`save_cursor`, EMPTY_DAYS).
NAMED: dict[tuple[str, str], str] = {}


def _employer_key(name) -> str:
    try:
        from company_key import key
    except Exception:  # pragma: no cover
        return str(name or "").lower()
    return key(name)


def _covered_by_ats() -> set:
    """Employers whose jobs a round reads from their own ATS (profile boards.py)."""
    try:
        from company_key import key
        boards = person.module("boards") if person.exists("boards.py") else None
        return {key(e) for e in dict(getattr(boards, "BOARDS", {}) or {})}
    except Exception:
        return set()


def broadest(queries) -> list:
    """The queries no broader query in the list already covers, in their order.

    A keyword board answers "data scientist" with the senior and lead roles too,
    so on a board with a crawl-delay "senior data scientist" spends a request on
    postings the broader one returns. A query is dropped only when another one's
    words are a strict subset of its own.
    """
    import re as _re
    words = [(q, frozenset(_re.findall(r"[a-z0-9+#]+", str(q).lower()))) for q in queries]
    return [q for q, w in words if not any(ow and ow < w for _, ow in words)]


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _cursor() -> dict:
    """The cursor, read from where it lives and from where 3.7.0 put it, the newer
    winning: an old file a move could not remove loses nothing it still holds."""
    new, old = _sweep_paths()
    return {**_load(old), **_load(new)}


def _write_cursor(state: dict) -> bool:
    """Write the cursor where it lives, then remove the old one. False if it could not."""
    new, old = _sweep_paths()
    try:
        os.makedirs(os.path.dirname(new), exist_ok=True)
        with open(new, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
            fh.write("\n")
    except OSError:
        return False
    try:
        os.remove(old)
    except OSError:
        pass
    return True


def move_cursor() -> str:
    """Move a cursor from where 3.7.0 put it into its own folder; what happened, in words."""
    new, old = _sweep_paths()
    if not os.path.exists(old):
        return "nothing to move"
    if not _write_cursor(_cursor()):
        return f"could not write {new}"
    return f"moved {old} to {new}"


def save_cursor(sent_by_skill: dict, today: str, secs_by_skill: dict | None = None,
                named_by_skill: dict | None = None) -> None:
    """Where each person portal's tail starts next round, from what this one sent, and how
    long one of its requests took (`secs`, for the next round's plan). `named_by_skill`:
    {portal: {employer search: whether the board had anything at that employer}}, kept as
    `empty` (the day each came back with nothing), for EMPTY_DAYS."""
    if not PLAN and not os.path.exists(_sweep_paths()[1]):
        return
    state = _cursor()
    for skill, (mode, core, rotating, offset) in PLAN.items():
        if skill not in sent_by_skill:
            continue
        last = state.get(skill) if isinstance(state.get(skill), dict) else {}
        sent = sent_by_skill[skill]
        done = sent if mode == "all" else max(0, sent - core)
        state[skill] = {"mode": mode, "next": (offset + done) % rotating if rotating else 0,
                        "sent": sent, "date": today}
        secs = (secs_by_skill or {}).get(skill)
        if secs:
            state[skill]["secs"] = round(float(secs), 1)
        empty = {q: d for q, d in dict(last.get("empty") or {}).items()
                 if q in _still_empty({"empty": {q: d}}, dt.date.fromisoformat(today))}
        for q, found in ((named_by_skill or {}).get(skill) or {}).items():
            if found:
                empty.pop(q, None)
            else:
                empty[q] = today
        if empty:
            state[skill]["empty"] = dict(sorted(empty.items()))
        if last.get("yield"):
            state[skill]["yield"] = last["yield"]       # what it earned (record_yield)
    _write_cursor(state)


def record_yield(got: dict, today: str, name: str) -> None:
    """Keep, in each of the person's own boards' place in the cursor, how many of its jobs
    reached this round's list ({board's short name: count}, LISTED_AT or more and passing
    every rule: run_round.record_board_yield), for the time board_share gives it in the rounds
    after. The round's own record (`name`) replaces one it already left; YIELD_ROUNDS are kept,
    the newest last. A board with no place in the cursor (LinkedIn, freehire) is left out."""
    state = _cursor()
    changed = False
    for skill, entry in state.items():
        short = portals.short(skill)
        if not isinstance(entry, dict) or short not in got:
            continue
        kept = [y for y in entry.get("yield") or []
                if isinstance(y, dict) and y.get("round") != name]
        kept.append({"date": today, "round": name, "listed": int(got[short] or 0)})
        entry["yield"] = kept[-YIELD_ROUNDS:]
        changed = True
    if changed:
        _write_cursor(state)


def _still_empty(last: dict, today: dt.date | None) -> set:
    """The employer searches a board had nothing from within EMPTY_DAYS of `today`."""
    day = today or person.today()
    out = set()
    for q, when in dict(last.get("empty") or {}).items():
        try:
            if (day - dt.date.fromisoformat(str(when))).days < EMPTY_DAYS:
                out.add(q)
        except ValueError:
            continue
    return out


def turned_down():
    """A function from an employer's name to why the person turned it down, by name or by kind
    (tools/wants.py, the settings as they stand now), or "". A round asked for the Workday
    boards and name searches of six employers the person had declined, four of them weeks
    before, and every request was spent for rows the bar then cut (issue 307)."""
    try:
        import wants
        return wants.out_fn()
    except Exception:  # noqa: BLE001  no profile to read: nobody is turned down
        return lambda name: ""


def searched_employers(out=None) -> list:
    """SCRAPE_EMPLOYERS without the employers the person turned down."""
    out = out or turned_down()
    return [e for e in EMPLOYERS if not out(e)]


def build_tasks(on: dict[str, bool], pages: int, today: dt.date | None = None) -> list[tuple]:
    """(kind, query, location, page) for every request, for the portals that are on.

    `kind` is "li", "lir" or "fh" for the app's two portals, and the portal's
    own name for a person's portal, whose requests come last and are sent by
    `sweep`, paced. An employer the person turned down is never asked for by name."""
    li, fh = on.get("linkedin-search"), on.get("freehire-search")
    tasks = []
    employers = searched_employers()
    # LinkedIn: every query against the home city deep, the rest shallow.
    if li:
        for q in QUERIES:
            for loc in LOCATIONS:
                depth = pages if loc.startswith(DEEP) else 2
                for pg in range(1, depth + 1):
                    tasks.append(("li", q, loc, pg))
        for q in QUERIES:
            for loc in REMOTE_LOCATIONS:
                for pg in range(1, 3):
                    tasks.append(("lir", q, loc, pg))
    if fh:
        for q in QUERIES:
            for pg in range(1, pages + 1):
                tasks.append(("fh", q, None, pg))
    # The named-employer pass. Shallow, because a company search that needs
    # five pages is not finding that company, it is finding the query words.
    for emp in employers:
        for t in EMPLOYER_QUERIES:
            q = f"{emp} {t}"
            if li:
                for loc in EMPLOYER_LOCATIONS:
                    tasks.append(("li", q, loc, 1))
                for loc in EMPLOYER_REMOTE:
                    tasks.append(("lir", q, loc, 1))
            if fh:
                tasks.append(("fh", q, None, 1))
    # A person's own portals, the way LinkedIn is searched: every query at its
    # first place as deep as it says (`pages:`, capped by --pages) is the core,
    # sent first in every round. Then the tail: the named employers on page one
    # there, remote postings where the board can filter for them (`remote: true`,
    # sent as `--remote` and a 5th element), every other place two pages. A paced
    # board runs out of its budget long before its tail: on one, 368 requests
    # against room for about 56, so the same tail was dropped round after round
    # and its named employers never ran. Three things fix that. The tail starts
    # where the last round stopped (the cursor), so successive rounds cover all
    # of it. A query a broader one covers is not sent (`broadest`). And an employer
    # whose own ATS board a round already reads is not searched for here.
    #
    # The order is the order of value, because a budget cuts from the end: page one of
    # every search before anyone's page two, the first place before the rest, the
    # places further out last, each in the order the person lists them. It was every
    # page of the first search before page one of the second, so a board whose budget
    # held about 150 of its 243 requests lost whole searches to an accident of order.
    #
    # An employer whose own board is on file is still planned here, and its search is passed
    # over when it comes up only if that board was read this round (`sweep`'s `covered`): it
    # was left out of the plan up front, so a board the site asked to slow down lost its
    # employer both ways (issue 302).
    cursor = _cursor()
    PLAN.clear()
    NAMED.clear()
    try:
        from company_key import key as _key
    except Exception:  # pragma: no cover
        def _key(x):
            return x
    for skill in contract_portals(on):
        places = portal_locations(skill)
        depth = min(pages, portals.pages(skill))
        qs = broadest(QUERIES)
        core = [(skill, q, places[0], pg) for pg in range(1, depth + 1) for q in qs]
        tail = [(skill, f"{emp} {t}", places[0], 1) for emp in employers
                for t in EMPLOYER_QUERIES]
        # An employer this board had nothing from in the last EMPTY_DAYS is not asked for.
        empty = _still_empty(cursor.get(skill) or {}, today)
        tail = [t for t in tail if t[1] not in empty]
        NAMED.update({(skill, f"{emp} {t}"): _key(emp) for emp in employers
                      for t in EMPLOYER_QUERIES})
        for pg in range(1, min(depth, 2) + 1):
            if portals.takes_remote(skill):
                tail += [(skill, q, None, pg, True) for q in qs]
            tail += [(skill, q, loc, pg) for loc in places[1:] for q in qs]
        last = cursor.get(skill) or {}
        # A board that last time sent fewer requests than its core rotates through
        # everything; otherwise the core runs first and only the tail rotates.
        whole = isinstance(last.get("sent"), int) and last["sent"] < len(core)
        mode, ring = ("all", core + tail) if whole else ("tail", tail)
        start = int(last.get("next", 0) or 0) if last.get("mode", "tail") == mode else 0
        offset = start % len(ring) if ring else 0
        PLAN[skill] = (mode, len(core), len(ring), offset)
        rotated = ring[offset:] + ring[:offset]
        tasks += rotated if mode == "all" else core + rotated
    return tasks


def named_tasks(on: dict[str, bool], pages: int, employers) -> list[tuple]:
    """The requests of a search limited to employers the person named (run_round.py
    --employers), in build_tasks' shape: each name searched with the profile's employer
    queries (SCRAPE_EMPLOYER_QUERIES, else the name alone) at its employer places (else its
    places), the first place two pages deep at most and the rest one, as the named-employer
    pass already searches. On a person's own portals, page one at the first place, for an
    employer whose own board a round does not already read. Far fewer requests than a whole
    search: the whole search filtered afterwards cost every request of a round. The paced
    boards' cursor is left where it is: this is not their round."""
    li, fh = on.get("linkedin-search"), on.get("freehire-search")
    out = turned_down()
    names = [str(e).strip() for e in employers or () if str(e).strip() and not out(e)]
    asks = [t for t in EMPLOYER_QUERIES if str(t).strip()]
    places = EMPLOYER_LOCATIONS or LOCATIONS
    remote = EMPLOYER_REMOTE or REMOTE_LOCATIONS
    tasks: list[tuple] = []
    PLAN.clear()
    queries = [f"{emp} {t}" if t else emp for emp in names for t in (asks or [""])]
    for q in queries:
        if li:
            for loc in places:
                depth = min(pages, 2) if loc.startswith(DEEP) else 1
                tasks += [("li", q, loc, pg) for pg in range(1, depth + 1)]
            tasks += [("lir", q, loc, 1) for loc in remote]
        if fh:
            tasks.append(("fh", q, None, 1))
    covered = _covered_by_ats()
    NAMED.clear()
    try:
        from company_key import key as _key
    except Exception:  # pragma: no cover
        def _key(x):
            return x
    for skill in contract_portals(on):
        first = portal_locations(skill)[0]
        for emp in names:
            for t in (asks or [""]):
                q = f"{emp} {t}" if t else emp
                tasks.append((skill, q, first, 1))
                if _key(emp) in covered:
                    NAMED[(skill, q)] = _key(emp)
    # A search the person limited to these employers asks for them whatever a board had before,
    # and teaches nothing: only an ordinary round's employer searches are remembered.
    return tasks


def named_boards(employers, boards: dict | None = None) -> tuple[dict, list[str]]:
    """({employer: board} for the employers named that have their own board on file, in
    profile/boards.py, matched as the app matches employer names; [the names with none])."""
    from company_key import key as _key
    import ats_boards
    boards = ats_boards.BOARDS if boards is None else boards
    by_key = {_key(e): e for e in boards}
    mine, none = {}, []
    for n in employers or ():
        e = by_key.get(_key(n))
        if e:
            mine[e] = boards[e]
        else:
            none.append(n)
    return mine, none


PARTIAL = "partial_rows.json"


def _write_partial(out: str, seen: dict) -> None:
    """Everything found so far, written over itself: what a killed stage leaves."""
    tmp = os.path.join(out, PARTIAL + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(list(seen.values()), fh)
        os.replace(tmp, os.path.join(out, PARTIAL))
    except OSError:
        pass


# A widening asks for more pages of the same searches. It used to send every request of the
# round before again from page one: at twice the pages, nine in ten of its LinkedIn requests
# repeated the first round's, and on a computer, under its cap, it sent the same 300 again.
# Each scrape now writes the requests that were answered (SENT) beside its postings, and a
# widened round given that folder (--before) carries the postings over, before anything else
# lands, and sends only what was not answered yet. A request that failed is asked again,
# as it would have been before. The person's paced boards and the employer boards are read
# as they always were: the paced boards already go on from where the last round stopped,
# and an employer's careers site can page on between rounds.
SENT = "sent.json"


def request_key(job: tuple) -> str:
    """One pool job as the request it sends: the portal, the query, the place, the page and
    the freshness window, so a wider round never counts a different request as sent."""
    _portal, fn, args = job
    if fn is linkedin:
        q, loc, pg, jobage = args[:4]
        kind = "lir" if len(args) > 4 and args[4] else "li"
    else:
        q, pg, jobage = args[:3]
        kind, loc = "fh", None
    return json.dumps([kind, q, loc, pg, jobage])


def search_page(job: tuple) -> tuple[str, int]:
    """(the search a pool job's request belongs to, its page): `request_key` without the
    page, so every page of one search is one search."""
    kind, q, loc, pg, jobage = json.loads(request_key(job))
    return json.dumps([kind, q, loc, jobage]), int(pg)


# What each search was answered, kept a while beside the rounds (run_round passes --cache:
# rounds/.cache, which git ignores and no save takes), so a round run again soon after asks
# for nothing it was just answered. A round pruned its scrape and kept nothing, so a search
# run again nine minutes later, with only how jobs are scored changed, sent its 5,910
# requests again and took 24 minutes (issue 309). An answer is known by its request
# (request_key: the site, the words, the place, the page and how recent the jobs must be), so
# a search or a place added since is simply asked, and another window is another search. It
# is used for REQUEST_TTL on LinkedIn and freehire, which answer the same search much the
# same within hours, and PACED_TTL on a person's own board that asks to be sent less (its
# crawl-delay); never past it, and a failed request is never kept. `--fresh` asks again.
REQUEST_TTL = 6 * 3600
PACED_TTL = 12 * 3600
_wall = time.time            # the clock answers are dated by; a test sets its own


class Kept:
    """The answers kept in `folder` (hydrate.Kept, dated on this file's clock, and nothing
    older than any site keeps one): `get` gives a request's rows, `put` keeps them."""

    def __init__(self, folder: str):
        from hydrate import Kept as _Kept
        self.kept = _Kept(folder, oldest=max(REQUEST_TTL, PACED_TTL), clock=lambda: _wall())

    def get(self, key: str, ttl: float) -> list | None:
        got = self.kept.get(key, ttl)
        return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else None

    def put(self, key: str, rows: list) -> None:
        self.kept.put(key, list(rows))


class _Fresh:
    """Kept answers for a round asked to ask again (--fresh): none read, every answer kept."""

    def __init__(self, kept):
        self.put = kept.put

    def get(self, key: str, ttl: float) -> None:
        return None


def paced_key(skill: str, task: tuple, jobage: int) -> str:
    """A person's own board's request, as `request_key` says one of the app's two."""
    q, loc, pg = task[1:4]
    return json.dumps([skill, q, loc, pg, bool(len(task) > 4 and task[4]), jobage])


def before(folder: str | None) -> tuple[list[dict], set[str]]:
    """(the postings, the requests answered) of the scrape in `folder`, the round before a
    widening; ([], set()) where there is none, and the round then sends everything."""
    if not folder:
        return [], set()
    try:
        rows = json.load(open(os.path.join(folder, "scraped.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return [], set()
    try:
        sent = json.load(open(os.path.join(folder, SENT), encoding="utf-8"))
    except (OSError, ValueError):
        sent = []
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    return rows, {k for k in sent if isinstance(k, str)} if isinstance(sent, list) else set()


# What each source read and what failed, beside the scrape's files, for the round to report
# (run_round.say_sources). A round said "a quarter of portal requests failed" when one portal
# request in 5,760 had, and said nothing of 17 employer boards it never read (2026-11-16).
SOURCES = "sources.json"


def write_sources(out: str, rows: list, kept: list, sent: dict, failed: dict,
                  partial: str = "", boards: dict | None = None,
                  times: dict | None = None) -> None:
    """SOURCES: each site searched (requests sent and failed, with the commonest reasons,
    postings found and kept by the search's own gates, and for each of the person's own boards
    its time this round and why: `times`, from board_share), the employer boards (how many
    were read, and each that returned nothing with why, or left something out), and what
    stopped the scrape short."""
    from collections import Counter
    found = Counter(r.get("portal") for r in rows)
    passed = Counter(r.get("portal") for r in kept)
    boards = boards or {}
    systems = set(boards.get("systems") or ())
    sites = []
    for name in sorted(set(sent) | {p for p in found if p and p not in systems}):
        errs = failed.get(name, [])
        sites.append({"source": name, "requests": sent.get(name, 0), "failed": len(errs),
                      "why": [f"{n}x {w}" for w, n in Counter(e[:60] for e in errs).most_common(2)],
                      "found": found.get(name, 0), "kept": passed.get(name, 0),
                      **({"time": times[name]} if (times or {}).get(name) else {})})
    report = {"sites": sites,
              "boards": {"read": int(boards.get("read") or 0),
                         "found": {p: found.get(p, 0) for p in sorted(systems)},
                         "quiet": dict(boards.get("quiet") or {}),
                         "partial": dict(boards.get("partial") or {}),
                         # which could not be read, which were asked again (boards_unread)
                         **{k: boards[k] for k in ("boards", "not_read", "slowed", "retried",
                                                   "recovered", "line", "cut_short")
                            if k in boards}},
              "stopped": partial}
    with open(os.path.join(out, SOURCES), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def finish(out: str, seen: dict, today: dt.date, jobage: int, n_tasks: int,
           sent: dict, failed: dict, partial: str = "", boards: dict | None = None,
           times: dict | None = None) -> int:
    """The scrape's files from what was found: scraped, kept and dropped. Exit 2 when
    more than a quarter of the requests failed, or when the scrape was cut short."""
    # Copies of one posting from several sources are as old as the oldest of them.
    rows = stamp_copies(list(seen.values()), today)
    kept, dropped = [], []
    for j in rows:
        ok, row = annotate(j, today, jobage)
        (kept if ok else dropped).append({**row, "prefilter": row["prefilter_reason"]})

    buckets = {"0-3": 0, "4-7": 0, "8-14": 0}
    for j in kept:
        d = age_days(j, today)
        if d is None:
            continue
        buckets["0-3" if d <= 3 else ("4-7" if d <= 7 else "8-14")] += 1
    by_portal: dict[str, int] = {}
    for j in rows:
        by_portal[j["portal"]] = by_portal.get(j["portal"], 0) + 1

    json.dump(kept, open(f"{out}/kept.json", "w", encoding="utf-8", newline="\n"), indent=1)
    # LinkedIn's search endpoint returns no body, so `desc` is None for every
    # LinkedIn row here. Anything downstream that reads a posting - the text
    # screen, the knockout stage, the extractor - is blind until
    # tools/hydrate.py fills them in, and it fails quietly rather than loudly.
    # Say so, loudly, rather than letting a caller assume these are readable.
    blind = sum(1 for j in kept if not (j.get("desc") or "").strip())
    if blind:
        print(f"WARNING: {blind}/{len(kept)} kept postings have NO description. "
              f"Run `python3 tools/hydrate.py {out}/kept.json --out "
              f"{out}/hydrated.json` before ranking, screening or extracting, "
              f"or every one of them reaches the model blind.")
    json.dump(dropped, open(f"{out}/dropped.json", "w", encoding="utf-8", newline="\n"), indent=1)
    json.dump(rows, open(f"{out}/scraped.json", "w", encoding="utf-8", newline="\n"), indent=1)
    try:
        write_sources(out, rows, kept, sent, failed, partial, boards, times)
    except (OSError, TypeError, ValueError) as e:     # a report must never break a round
        print(f"sources: not written ({e})", file=sys.stderr)
    try:
        os.remove(os.path.join(out, PARTIAL))
    except OSError:
        pass
    print(f"{n_tasks} requests -> {len(rows)} unique postings {by_portal}")
    print(f"prefilter kept {len(kept)}, dropped {len(dropped)}; age {buckets}")
    report, bad = failure_report(sent, failed)
    print(report)
    if partial:
        print(f"PARTIAL: {partial}")
    return 2 if bad or partial else 0


def _employer_boards(today: dt.date, seen: str | None = None,
                     keep_ruled_out: bool = False, employers=None, report: dict | None = None,
                     cache_dir: str | None = None, retry_until: float | None = None,
                     ) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """(rows, {employer: why it was quiet}, {employer: what it left out}) from every
    employer board in profile/boards.py (tools/ats_boards.py). An error is raised to
    whoever waits for the answer, which reports it and carries on. `seen` and
    `keep_ruled_out` are the round's own: a replayed round, or one run with
    --no-seen-read, judged careers-site pages against the repo's file instead. With
    `employers` (a search limited to them), only their boards are read. `report`,
    `cache_dir` and `retry_until` are fetch_all's own: what was read and retried, where a
    host's robots.txt is kept for a day, and how long a board asked to slow down is waited
    for."""
    import ats_boards
    _ats_fetch = ats_boards.fetch_all
    notes: dict[str, str] = {}
    # Passed only when given, and only where the reader takes it, so a stand-in for fetch_all
    # written before they existed (a person's own tests have one) still works for a round.
    extra = dict(({"seen": seen} if seen else {}),
                 **({"keep_ruled_out": True} if keep_ruled_out else {}))
    if employers is not None:
        mine, _ = named_boards(employers)
        if not mine:
            return [], {}, {}
        extra["boards"] = mine
    # An employer the person turned down has its own job site read no more: every request
    # there was spent on rows the bar cuts (issue 307).
    mine = boards_to_read(extra.get("boards"))
    if mine is not None:
        if not mine:
            return [], {}, {}
        extra["boards"] = mine
    newer = {"report": report, "cache_dir": cache_dir, "retry_until": retry_until}
    try:
        import inspect
        takes = inspect.signature(_ats_fetch).parameters
        anything = any(p.kind is p.VAR_KEYWORD for p in takes.values())
    except (TypeError, ValueError):
        takes, anything = {}, False
    extra.update({k: v for k, v in newer.items()
                  if v is not None and (anything or k in takes)})
    rows, quiet = _ats_fetch(notes=notes, today=today, **extra)
    return rows, quiet, notes


def boards_to_read(boards: dict | None = None) -> dict | None:
    """The employer boards a round reads: `boards` (else profile/boards.py's) without those of
    employers the person turned down, or None where none of them is."""
    import ats_boards
    boards = ats_boards.BOARDS if boards is None else boards
    out = turned_down()
    kept = {e: b for e, b in boards.items() if not out(e)}
    return kept if len(kept) != len(boards) else None


# The employer boards a round could not read, in SOURCES, for the round to say before its
# prune (run_round._boards_unread). A "quiet:" line deep in round.log was all that said 17 of
# the person's target employers were never read, and the scrape still ended as complete
# (issue 302). A board counts as not read when its site asked to slow down, did not answer or
# answered with an error; not when it was read and had nothing in range, nor where its
# robots.txt says no (a standing rule `ats_boards.py --probe` names, not news of a round).
UNREAD = re.compile(r"\bHTTP (?:429|5\d\d)\b|\bslow down\b|\bno answer\b|\btimed? ?out\b|"
                    r"\b\w*(?:Error|Disconnected|IncompleteRead)\b|\bconnection\b", re.I)
MAX_UNREAD_FRACTION = 0.25


def boards_unread(quiet: dict, total: int, report: dict | None = None) -> dict:
    """What the round's own employer boards came to: how many there were, which could not be
    read and why, which the site asked to slow down, which were asked again and read then,
    and the line the round says (`line`, "" when every board was read)."""
    import ats_boards
    report = report or {}
    unread = {e: why for e, why in sorted(quiet.items()) if UNREAD.search(str(why or ""))}
    slowed = [e for e in unread if ats_boards.SLOWED.search(unread[e])]
    retried, recovered = list(report.get("retried") or ()), list(report.get("recovered") or ())
    line = ""
    if unread:
        names = ", ".join(list(unread)[:6]) + (f" and {len(unread) - 6} more"
                                               if len(unread) > 6 else "")
        why = []
        if slowed:
            why.append(f"{len(slowed)} asked us to slow down")
        if len(unread) > len(slowed):
            why.append(f"{len(unread) - len(slowed)} did not answer")
        line = (f"employer job sites not read: {len(unread)} of {total} ({names}): "
                + " and ".join(why)
                + f"; tried again after the pause they asked for: {len(retried)}, "
                  f"read then: {len(recovered)}")
    elif recovered:
        line = (f"employer job sites: every one read; {len(recovered)} asked us to slow down "
                "and were read once their pause was over")
    return {"boards": total, "not_read": unread, "slowed": slowed, "retried": retried,
            "recovered": recovered, "line": line,
            "cut_short": bool(total) and len(unread) / total > MAX_UNREAD_FRACTION}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="the directory the scrape's files go in (required)")
    ap.add_argument("--move-cursor", dest="move_cursor", action="store_true",
                    help="no requests: move documents/rounds/.sweep.json, where 3.7.0 kept "
                         "the slow boards' resume point, to documents/rounds/.sweep/cursor.json")
    ap.add_argument("--pages", type=int, default=None,
                    help=f"default {CLOUD_PAGES} in the cloud, {LOCAL_PAGES} on a person's own "
                         "computer (profile/search.py SCRAPE_PAGES sets their own)")
    ap.add_argument("--jobage", type=int, default=None,
                    help="how old a posting may be, in days (default: the person's own, "
                         "search.py JOB_AGE_DAYS, else 14)")
    ap.add_argument("--today", default=None)
    ap.add_argument("--seen", default=None,
                    help="the round's seen_jobs.json, for the employer boards (default: the repo's)")
    ap.add_argument("--keep-ruled-out", dest="keep_ruled_out", action="store_true",
                    help="employer boards keep postings already ruled out (run_round --no-seen-read)")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"default {CLOUD_WORKERS} in the cloud, {LOCAL_WORKERS} on their own "
                         "computer (SCRAPE_WORKERS)")
    ap.add_argument("--max-requests", dest="max_requests", type=int, default=None,
                    help="the most requests each app portal sends this round (default none "
                         f"in the cloud, {LOCAL_MAX_REQUESTS} on their own computer)")
    ap.add_argument("--budget", type=int, default=POOL_BUDGET,
                    help="seconds the LinkedIn and freehire requests may take, in all")
    ap.add_argument("--log", default=None, help="a file the progress lines are appended to")
    ap.add_argument("--request-log", dest="request_log", default=None,
                    help="a file that gets one line per request a paced board sends")
    ap.add_argument("--finish", action="store_true",
                    help="no requests: write the scrape's files from what a killed run left "
                         f"in {PARTIAL}, and exit 2")
    ap.add_argument("--skip-canary", action="store_true",
                    help="skip the pre-flight portal probe (offline replays)")
    ap.add_argument("--before", default=None,
                    help="a widening: the round before's scrape folder; its postings are "
                         "carried over and the requests it had answered are not sent again")
    ap.add_argument("--cache", default=None,
                    help="a folder beside the rounds, never saved with the person's files, "
                         "where what the search was answered is kept a short while: each "
                         f"search's answer for {REQUEST_TTL // 3600} hours "
                         f"({PACED_TTL // 3600} on a board that asks to be sent less) and each "
                         "employer site's robots.txt for a day")
    ap.add_argument("--fresh", action="store_true",
                    help="ask every site again, whatever answers --cache keeps (they are "
                         "still kept for the next search)")
    ap.add_argument("--employers-file", dest="employers_file", default=None,
                    help="a search limited to these employers (run_round.py --employers writes "
                         "the file): their own boards and searches by their names alone")
    a = ap.parse_args()
    if a.move_cursor:
        said = move_cursor()
        print(f"scrape_wide: {said}")
        return 1 if said.startswith("could not") else 0
    if not a.out:
        ap.error("the following arguments are required: --out")
    if a.jobage is None:
        from prefilter import own_window
        a.jobage = own_window()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    pages, workers, cap = defaults()
    pages = a.pages or pages
    workers = a.workers or workers
    cap = a.max_requests if a.max_requests is not None else cap
    if a.finish:
        try:
            got = json.load(open(os.path.join(a.out, PARTIAL), encoding="utf-8"))
        except (OSError, ValueError):
            got = []
        seen = {r["url"]: r for r in got if isinstance(r, dict) and r.get("url")}
        return finish(a.out, seen, today, a.jobage, 0, {}, {},
                      partial=(f"the scrape stage ran out of time; {len(seen)} postings had "
                               "arrived and are kept, the rest of the requests never went"))
    if not (QUERIES and LOCATIONS):
        print("scrape_wide: profile/search.py names no SCRAPE_QUERIES or "
              "SCRAPE_LOCATIONS, so there is nothing to search: run /setup",
              file=sys.stderr)
        return 1
    os.makedirs(a.out, exist_ok=True)

    on = portals.enabled()
    # Nothing to run a portal's CLI with is not a thin market: say what is missing and stop,
    # rather than probe every portal into a FileNotFoundError and end the round on exit 2.
    if any(v and portals.has_cli(n) for n, v in on.items()):
        try:
            portals.runtime()
        except portals.NoRuntime as e:
            print(f"scrape_wide: {e}", file=sys.stderr)
            return 1
    for name in portals.unknown():
        print(f"portals: PORTALS in profile/search.py names {name!r}, which is not "
              f"an installed portal, so it switches nothing", file=sys.stderr)
    print("portals: " + ", ".join(f"{n} {'on' if v else 'off'}" for n, v in on.items()))
    print(f"pace: {pages} pages, {workers} at once"
          + (f", at most {cap} requests a portal" if cap else "")
          + (" (a cloud session)" if CLOUD else " (this computer: gentler, the person's own address)"))
    for name in sorted(n for n, v in on.items() if v and n not in WIRED
                       and not (portals.has_cli(n) and portals.follows_contract(n))):
        why = "has no CLI" if not portals.has_cli(name) else "does not declare contract: 1"
        print(f"portals: {name} is on but {why}, "
              f"so a round cannot call it; /scrape runs it by hand, /add-portal rebuilds it")

    # One broad probe per portal that is on, before the sweep. A portal that has
    # gone quiet is reported as broken here rather than as a thin market three
    # widenings later. It does not abort the round: the other sources' results
    # are still worth having, and a round that says so beats a round that stops.
    #
    # The report goes where the progress lines go, as it is written: stderr, which
    # run_round passes on and writes to round.log the moment it arrives, and --log.
    # On stdout it reached the round's log only when the scrape stage had ended, so a
    # portal answering 403 and a board redirecting to a sandbox were named after
    # their sweeps rather than before. A portal that refused is sent nothing more.
    from run_round import took
    began = time.monotonic()

    def timing(what: str, since: float) -> None:
        # Where a round's time goes, in the round's log: the pool, the paced boards and
        # the employer boards run side by side, and the stage's total says nothing of which
        # one it waited for.
        _say(f"timing: {what} {took(time.monotonic() - since)}", a.log)

    health: dict[str, tuple[bool, str]] = {}
    if not a.skip_canary:
        health = canary(a.jobage, on)
        timing("the health probes took", began)
        report, ok = canary_report(health)
        _say("portal health:", a.log)
        for line in report.splitlines():
            _say(line, a.log)
        if not ok:
            down = [n for n, (h, _) in health.items() if not h]
            say = blocked_say(not_searched(health))
            if say:
                _say("Tell the person, in these words, once:", a.log)
                for line in say.splitlines():
                    _say("  " + line, a.log)
                for note in blocked_notes():              # yours, never said
                    _say("Claude, not for them: " + note, a.log)
            json.dump({"portals_down": down, "detail": {k: v[1] for k, v in health.items()},
                       "not_searched": not_searched(health), "say": say},
                      open(os.path.join(a.out, "00_portal_health.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    skipped = not_searched(health)
    for skill in [k for k, v in on.items() if v and portals.short(k) in skipped]:
        on[skill] = False

    employers = None
    if a.employers_file:
        from run_round import named_employers
        employers = named_employers(a.employers_file)
        _, no_board = named_boards(employers)
        out = turned_down()
        down = [e for e in employers if out(e)]
        if down:
            print("employers: not searched, as you turned them down: " + ", ".join(down))
        print(f"employers: searching {len(employers)} named employers by name"
              + (f"; no board of their own on file for {', '.join(no_board)} "
                 "(tools/ats_boards.py --find \"<employer>\" finds one)" if no_board else ""))
    tasks = (named_tasks(on, pages, employers) if employers is not None
             else build_tasks(on, pages, today))
    if not tasks:
        print("portals: none of the portals this scrape can call is on, so this "
              "round is the employer boards alone (python3 tools/portals.py)")

    seen: dict[str, dict] = {}
    sent: dict[str, int] = {}
    failed: dict[str, list[str]] = {}
    mine: dict[str, list[tuple]] = {}
    lock = threading.Lock()

    from lookup_score import norm as _norm

    def landed(rows_):
        """Add rows to the round, the first copy of a posting kept; how many were new.

        A posting is its address as lookup_score.norm reads it, the key every later
        stage matches on: LinkedIn gives one posting under www. and a country's
        subdomain, bare and with a slug, and both copies were fetched and scored."""
        new = 0
        with lock:
            for r in rows_:
                url = r.get("url")
                key = (_norm(url) or url) if url else None
                if key and key not in seen:
                    seen[key] = clean_row(r)
                    new += 1
        return new

    carried, answered = before(a.before)
    if carried:
        landed(carried)
    for task in tasks:
        if task[0] not in ("li", "lir", "fh"):
            mine.setdefault(task[0], []).append(task)
    tallies: dict[str, Tally] = {portals.short(k): Tally(portals.short(k), len(ts))
                                 for k, ts in mine.items()}
    # What the employer boards have read so far, filled as each is read: a person's portal
    # searches an employer by name only while that employer's own board has not been read.
    board_report: dict = {"read": set()}
    from company_key import key as _ckey

    def covered(employer_key: str) -> bool:
        return any(_ckey(e) == employer_key for e in list(board_report["read"]))
    # What each search was answered a short while ago, kept beside the rounds (Kept).
    kept = Kept(os.path.join(a.cache, "requests")) if a.cache else None
    reuse = None if a.fresh else kept
    # A paced board's time follows what its jobs on the list have earned it: a while after
    # LinkedIn and freehire finish, longer for a board that pays, its first minute for one that
    # has not in several rounds, its whole budget where neither is searched, and the person's
    # own minutes where they set them (issue 301, issue 327). Said for each board, here and in
    # the round's summary (SOURCES).
    paced_from, pool_ended = time.monotonic(), []
    pooled = any(t[0] in ("li", "lir", "fh") for t in tasks)
    place = _cursor() if mine else {}
    shares = {skill: board_share(skill, pooled, place) for skill in mine}
    for skill, share in shares.items():
        _say(f"portals: {portals.short(skill)}'s time: {share.why}", a.log)
    paced = ThreadPoolExecutor(max_workers=max(1, len(mine)))
    sweeps = {paced.submit(sweep, skill, ts, a.jobage, tally=tallies[portals.short(skill)],
                           on_rows=landed, log=a.log, requests=a.request_log,
                           covered=covered, kept=_Fresh(kept) if a.fresh and kept else kept,
                           stop=share_stop(shares[skill], paced_from, pool_ended),
                           budget=shares[skill].most,
                           over=shares[skill].stop if shares[skill].after is None else ""):
              portals.short(skill)
              for skill, ts in mine.items()}
    jobs = []
    for task in tasks:
        kind, q, loc, pg = task[:4]
        if kind in mine:
            continue
        if kind == "li":
            jobs.append(("linkedin", linkedin, (q, loc, pg, a.jobage)))
        elif kind == "lir":
            jobs.append(("linkedin", linkedin, (q, loc, pg, a.jobage, True)))
        else:
            jobs.append(("freehire", freehire, (q, pg, a.jobage)))
    # Broadest first: page one of every search before anyone's page two, the home
    # city before the rest. Under a cap, or a budget that runs out, what goes unsent
    # is the deep pages, never a query or a place that was never asked at all.
    jobs.sort(key=lambda j: (j[2][2] if j[1] is linkedin else j[2][1],
                             0 if j[1] is not linkedin or str(j[2][1]).startswith(DEEP) else 1))
    if answered:
        planned = len(jobs)
        jobs = [j for j in jobs if request_key(j) not in answered]
        print(f"widening: {len(carried)} postings carried over from the round before, and "
              f"{planned - len(jobs)} of its {planned} LinkedIn and freehire requests not "
              "sent again")
    sent_now: set[str] = set(answered)
    if reuse is not None and jobs:
        # Answered in the last REQUEST_TTL: its postings land as they were, and a deeper page
        # of a search an answered page ended is not asked for either (PageWalk).
        walk, ask, had_n = PageWalk(), [], 0
        for j in jobs:
            had = reuse.get(request_key(j), REQUEST_TTL)
            if had is None:
                ask.append(j)
                continue
            had_n += 1
            landed(had)
            sent_now.add(request_key(j))
            walk.answered(*search_page(j), had)
        planned, jobs = len(jobs), [j for j in ask if not walk.past_end(*search_page(j))]
        if had_n:
            print(f"kept answers: {had_n} of {planned} LinkedIn and freehire searches were "
                  f"answered in the last {REQUEST_TTL // 3600} hours and are not asked again"
                  + (f"; {len(ask) - len(jobs)} deeper page(s) not needed"
                     if len(ask) > len(jobs) else ""))

    def answered_now(job):
        with lock:
            sent_now.add(request_key(job))

    def keep_answer(job, rows_):
        if kept is not None:
            kept.put(request_key(job), rows_)
    done = threading.Event()
    shown: dict = {}

    def progress():
        while not done.wait(PROGRESS_SECONDS):
            for line in progress_lines(list(tallies.values()), shown, time.monotonic()):
                _say(line, a.log)
            with lock:
                _write_partial(a.out, seen)

    ticker = threading.Thread(target=progress, daemon=True)
    ticker.start()
    # The employer boards are read while the portals are searched, on hosts of their
    # own, and their rows are added below where they always were, after every portal's.
    boards = ThreadPoolExecutor(max_workers=1)
    searching = time.monotonic()
    boards_took: list = []

    def read_boards():
        newer = {"report": board_report, "cache_dir": a.cache,
                 "retry_until": searching + BOARD_RETRY_SECONDS}
        try:
            if employers is not None:
                return _employer_boards(today, a.seen, a.keep_ruled_out, employers, **newer)
            return _employer_boards(today, a.seen, a.keep_ruled_out, **newer)
        finally:
            boards_took.append(time.monotonic() - searching)
    employer_boards = boards.submit(read_boards)
    boards.shutdown(wait=False)
    _, pool_tallies = pool(jobs, workers, budget=a.budget, cap=cap, tallies=tallies,
                           on_rows=landed, on_sent=answered_now, page_of=search_page,
                           on_answer=keep_answer)
    pool_ended.append(time.monotonic())
    with open(os.path.join(a.out, SENT), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(sorted(sent_now), fh)
    if jobs:
        timing("LinkedIn and freehire finished after", searching)
    swept: dict[str, int] = {}
    for f in as_completed(sweeps):
        portal = sweeps[f]
        try:
            rows_, n, errs = f.result()
        except Exception as e:
            rows_, n, errs = [], 1, [f"{type(e).__name__}: {str(e)[:120]}"]
        sent[portal] = n
        # Where the next round's tail starts: past every task gone through, a page not
        # needed because its search had run out included.
        swept.update({k: n + tallies[portal].ended + tallies[portal].covered
                      + tallies[portal].kept for k in mine if portals.short(k) == portal})
        if errs:
            failed.setdefault(portal, []).extend(errs)
        landed(rows_)
    paced.shutdown()
    if mine:
        timing("the paced boards finished after", searching)
    done.set()
    ticker.join()
    for name, t in pool_tallies.items():
        if name in sent:
            continue
        sent[name] = t.sent
        if t.failed:
            failed.setdefault(name, []).extend(t.failed)
    # Each portal's last line, unless the ticker has already said it.
    for t in tallies.values():
        t.finished = True
    for line in progress_lines(list(tallies.values()), shown, time.monotonic()):
        _say(line, a.log)
    for t in tallies.values():
        if t.stopped and t.name in ("linkedin", "freehire"):
            _say(f"portals: {t.name} stopped, {t.stopped}; {t.total - t.sent} of {t.total} "
                 "requests not sent", a.log)
    save_cursor(swept, today.isoformat(),
                {k: tallies[portals.short(k)].per for k in mine},
                {k: tallies[portals.short(k)].named for k in mine})
    _write_partial(a.out, seen)

    # Employer boards, straight from the ATS: every system openroles reads, and
    # careers sites. No key, and keyed by EMPLOYER rather than by keyword,
    # which is the one thing a portal search cannot do: the profile names the
    # target employers and until then they were a preference stated in prose.
    # One analytics engineering role that scored 86 was invisible to both
    # portals, and the employers that run Workday were visible only when
    # LinkedIn happened to index them.
    #
    # Additive and best-effort. A board that stops resolving is reported, never
    # fatal, and the portals still carry the round.
    #
    # They are read on their own thread from the moment the portals start
    # (_employer_boards), and used to be read only now, after every paced board had
    # spent its budget: minutes of a round spent waiting for requests that need
    # nothing from the portals. Their rows still join here, after every portal's, so
    # where one posting comes from two sources the portal's copy is still the one kept.
    boards: dict = {}
    boards_cut = ""
    try:
        waiting = time.monotonic()
        ats_rows, ats_quiet, ats_notes = employer_boards.result()
        boards = {"quiet": ats_quiet, "partial": ats_notes,
                  "systems": sorted({r.get("portal") for r in ats_rows if r.get("portal")}),
                  "read": len({r.get("company") for r in ats_rows}) + len(ats_quiet)}
        _say(f"timing: the employer boards finished after {took(boards_took[0])}, "
             f"waited for {took(time.monotonic() - waiting)} here", a.log)
        landed(ats_rows)
        ats_by: dict[str, int] = {}
        for r in ats_rows:
            ats_by[r.get("portal")] = ats_by.get(r.get("portal"), 0) + 1
        print(f"ats boards: {len(ats_rows)} in-range postings "
              f"({', '.join(f'{k} {v}' for k, v in sorted(ats_by.items()))})")
        for employer, why in sorted(ats_quiet.items()):
            print(f"  quiet: {employer}: {why}")
        for employer, why in sorted(ats_notes.items()):
            print(f"  partial: {employer}: {why}")
        import ats_boards
        planned = named_boards(employers)[0] if employers is not None else ats_boards.BOARDS
        kept_boards = boards_to_read(planned)
        total = len(planned if kept_boards is None else kept_boards)
        unread = boards_unread(ats_quiet, total, board_report)
        boards.update(unread)                 # into SOURCES, for the round to say
        if unread["line"]:
            _say(unread["line"], a.log)
        if unread["cut_short"]:
            boards_cut = (f"{len(unread['not_read'])} of {total} employer job sites were not "
                          "read")
    except Exception as e:            # a new source must never break a round
        print(f"ats boards: skipped ({type(e).__name__}: {e})", file=sys.stderr)

    cut = [t for t in pool_tallies.values() if t.stopped and t.name in ("linkedin", "freehire")]
    notes = [f"{t.name} stopped ({t.stopped}) with {t.total - t.sent} of its "
             f"{t.total} requests unsent" for t in cut]
    if boards_cut:
        notes.append(boards_cut)
    notes += [f"{name} not searched (it refused the probe: {why})"
              for name, why in sorted(skipped.items())]
    partial = "; ".join(notes)
    return finish(a.out, seen, today, a.jobage, len(tasks), sent, failed, partial=partial,
                  boards=boards, times={portals.short(k): v.why for k, v in shares.items()})

if __name__ == "__main__":
    raise SystemExit(main())
