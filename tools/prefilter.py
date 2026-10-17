#!/usr/bin/env python3
"""Tier 1 mechanical pre-filter for the job-search pipeline.

The scrape pipeline in `.claude/skills/job-scraper/SKILL.md` describes a Tier 1
"mechanical pre-filter. Title and location regex. No model tokens." Until this
file existed that filter was improvised per run, and an improvised version
dropped a genuinely good posting ("Manager, Demand Modelling & Analytics,
Forecasting") on the bare word "Manager" - directly contradicting
`10-triage-blockers.md`, which states that "Manager" without direct reports is
NOT a knockout. A filter that costs nothing but silently discards real
opportunities is the most expensive thing in the pipeline.

So this is the filter, in code, with every drop logged and a reason attached.

Design rule: **Tier 1 drops only what a title or location settles on its own.**
Anything requiring judgment goes through to Tier 2 triage, which costs a few
thousand tokens and reads the posting's actual requirements. A false negative
here costs one cheap triage pass; a false positive is invisible and permanent.

## The cross-run gate, and why it moved here

`--seen job_scraper/seen_jobs.json` also drops postings this search has already
ruled out. That check used to happen only in `throttle.py`, which runs last,
six stages after `hydrate.py` has spent one HTTP call on every survivor. So
every round re-fetched the body of every posting it had already excluded, then
screened it, scored its opportunity and scored its fit, and threw all of it
away at the end.

Measured against a long-lived `seen_jobs.json`, a sizeable share of the
postings that passed this filter's own gates were already ruled out, and a
round scrapes far more postings than it finds new ones, so the repeat rate is
the normal case rather than an unlucky run.

The gate is `throttle.ruled_out()` itself, imported rather than reimplemented,
so it is by construction the same decision the throttle would make later and
the shortlist cannot change. That matters more than the saving: a second
implementation of "have we seen this" would drift, and the direction it drifts
is dropping a role that should have surfaced. Everything the throttle does that
is NOT a pure function of `seen_jobs.json` (the company throttle, one role per
employer, warm-route notes) stays where it is, because those depend on scores
this stage does not have yet.

Nothing is lost by moving it. `ruled_out` reads only the URL and the
(title, employer) pair, both present from the scrape, and its exclusions
already carry their reason and date in `seen_jobs.json`; the throttle's
write-back would only refresh a `skipped_date` that nothing reads.

Usage:
    python3 tools/prefilter.py new.json --out kept.json --dropped dropped.json
    python3 tools/prefilter.py new.json --explain          # print the decisions

Input is a JSON list (or an object keyed by posting id) whose rows carry at
least `title`, `company` and `location`. A list in is a list out.

    python3 tools/prefilter.py new.json --out kept.json --jobage 14 --today YYYY-MM-DD
    python3 tools/prefilter.py new.json --out kept.json --seen job_scraper/seen_jobs.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from dates import days_since  # noqa: E402

# --- Freshness -------------------------------------------------------------
# HARD RULE: a posting older than 14 days is out, no exceptions. Stale postings
# are the most expensive kind of false positive in this pipeline - they survive
# every tier, get fully scored, get drafted for, and the role is already filled.
# Within the window, newer is better and the report orders by it.
MAX_AGE_DAYS = 14

# --- Location -------------------------------------------------------------
# The gate is this algorithm; the market is the profile's (search.py LOCATION):
# the home country, its regions and the home region, the home metro that
# passes, the on-site places outside it that fail, the one neighbouring country
# treated differently, places and regions flagged rather than failed, and the
# rest of the world. The home metro passes; remote, the home country alone and
# the home region alone pass; flagged places and unknown home-region cities are
# a FLAG for a later reader; everything on-site elsewhere fails.
#
# The first version matched substrings, so a town passed on a metro name
# inside it, a US city passed on a home-region word inside its name, and every
# "City, Region, Country" whose city was not on the outside list passed as
# "country-wide": on-site roles reached a round's ranking that way.
# Tokens and word boundaries now, never substrings.
_S = person.module("search")
_LOC = _S.LOCATION
_NB = _LOC.get("neighbour") or {}
_NEVER = re.compile(r"(?!x)x")
METRO = list(_LOC.get("metro", []))
REGIONS = dict(_LOC.get("regions", {}))
NEIGHBOUR_STATES = set(_NB.get("states", ()))
NEIGHBOUR_WORDS = _NB.get("words", _NEVER)
NEIGHBOUR_METROS = _NB.get("metros", _NEVER)
OTHER_COUNTRIES = list(_LOC.get("other_countries", []))
OUTSIDE = list(_LOC.get("outside", []))
_HOME = _LOC.get("home_country", "")
_HOME_RX = _LOC.get("home_country_rx", _NEVER)
_HOME_ALONE = [x.lower() for x in _LOC.get("home_country_alone", [])]
_HOME_REGION = _LOC.get("home_region")
_CC = person.country().lower()
_METRO = _LOC.get("metro_name", "home metro")
_FLAG_PLACES = list(_LOC.get("flag_places", []))
_FLAG_REGIONS = dict(_LOC.get("flag_regions", {}))


_SPLIT = re.compile(r"\s*(?:,|\||/|&|\(|\)|\s[-\u2013]\s)\s*")
_MODE = re.compile(r"\b(hybrid|on[- ]?site|in[- ]office|flexible)\b")


def _parts(low: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(low) if p and p.strip()]


def _has(low: str, term: str) -> bool:
    """Containment anchored at a word start; the term may be a prefix ("trois-rivi")."""
    return re.search(r"(?<![a-z\u00e0-\u00ff])" + re.escape(term), low) is not None


def location_verdict(loc: str, title: str = "") -> tuple[str, str]:
    low = _MODE.sub(" ", (loc or "").lower()).strip()
    low = re.sub(r"\s+", " ", low).strip(" -,")
    tl = (title or "").lower()
    parts = _parts(low)
    prov = next((REGIONS[p] for p in parts if p in REGIONS), None)
    home = _HOME_RX.search(low) is not None or prov is not None
    # A two-letter state that is also the home country's code is the country
    # when a home region or city is beside it: Dayforce, SmartRecruiters and
    # Workday write "<City>, ON, CA", and "CA" read as California failed every
    # such posting as on-site abroad. Alone ("San Diego, CA") it is still a state.
    # A home-region token is the evidence, not a home city: a town name shared by
    # both countries, alone with "CA", is California as often as not; with the
    # home region beside it, it is not.
    states = [p for p in parts if p in NEIGHBOUR_STATES
              and not (p == _CC and home)]
    abroad = (bool(NEIGHBOUR_WORDS.search(low)) or bool(NEIGHBOUR_METROS.search(low))
              or bool(states))
    # A word, not a substring, and in the title only as a work mode: "Remote
    # Sensing Analyst" is a geospatial job title, and the substring test sent
    # an on-site posting outside the home metro down the explicitly-remote branch.
    remote = (re.search(r"\bremote\b", low) is not None
              or re.search(r"\bremote\b(?!\s+sens)", tl) is not None)

    # "Remote" wins over the city name: portals stamp remote postings with a
    # nominal office (a real case: a "| Remote" listing against a city two
    # hours away). A remote role anchored in the neighbouring country is a FLAG,
    # not a pass: it passes only when the employer explicitly hires from home,
    # which a location string cannot show.
    if remote:
        if abroad and not home:
            return "FLAG", _NB.get("remote_reason", "remote but anchored abroad")
        # A named country other than home is not a nominal office. The remote
        # branch short-circuited every country check below it, so "Remote,
        # Brazil", "Remote - India" and "City, Country (Remote)" all returned
        # PASS and reached the scorer. Remote does not mean remote-from-home,
        # and relocation abroad is a stated deal-breaker.
        if not home:
            for c in OTHER_COUNTRIES:
                if c in parts:
                    return "FAIL", (f"remote but anchored outside {_HOME} ({c}); "
                                    f"relocation abroad is a deal-breaker")
        return "PASS", "explicitly remote; the stated city is a nominal office"
    if not low:
        return "FLAG", "no location stated; Tier 2 decides"
    for rx, why in _FLAG_PLACES:
        if rx.search(low):
            return "FLAG", why
    if abroad:
        # "United States, Canada": a list that names home as well is not a
        # posting abroad. Tier 2 reads the body.
        if home:
            return "FLAG", f"lists {_HOME} and another country; Tier 2 decides"
        return "FAIL", _NB.get("onsite_reason", "on-site in another country")
    for c in OTHER_COUNTRIES:
        if c in parts:
            return "FAIL", f"outside {_HOME} ({c}); relocation abroad is a deal-breaker"
    # A home-metro city counts only when the region token is the home region
    # or absent: a city of the same name in another country is not it.
    if prov in (None, _HOME_REGION):
        for g in METRO:
            if re.search(r"\b" + re.escape(g) + r"\b", low):
                return "PASS", f"{_METRO} ({g})"
    for o in OUTSIDE:
        if _has(low, o):
            return "FAIL", f"on-site outside the {_METRO} ({o})"
    if len(parts) == 1 and parts[0] in _HOME_ALONE:
        return "PASS", f"country-wide ({parts[0]}), includes remote"
    if parts in _LOC.get("home_region_alone", []):
        return "PASS", _LOC.get("home_region_reason", "home region, includes remote")
    if prov and all(p in REGIONS or p in _HOME_ALONE for p in parts):
        # "<Region>, <REGION CODE>, <Country>": the home region written twice is still home.
        if prov == _HOME_REGION:
            return "PASS", _LOC.get("home_region_reason", "home region, includes remote")
        if prov in _FLAG_REGIONS:
            return "FLAG", _FLAG_REGIONS[prov][0]
        return "FAIL", (f"{_LOC.get('region_word', 'region')}-wide outside "
                        f"{_LOC.get('home_region_name', 'the home region')} ({prov})")
    if home:
        # "City, Region, Country" with a city on neither list.
        if prov in (None, _HOME_REGION):
            return "FLAG", (f"{_LOC.get('home_region_name', 'Home-region')} city not on the "
                            f"{_METRO} list; Tier 2 decides")
        if prov in _FLAG_REGIONS:
            return "FLAG", _FLAG_REGIONS[prov][1]
        return "FAIL", f"on-site outside the {_METRO} ({prov})"
    return "FLAG", "location not recognized; Tier 2 decides"


# --- Title ----------------------------------------------------------------
# A POSITIVE gate: the title must look like the candidate's job family. This is
# safer than a negative blocklist, because a blocklist has to anticipate every
# wrong job family while a positive list only has to recognize the right one.
# Both lists are the profile's (search.py POSITIVE, NEGATIVE): the family is
# the person's, and so are the few title shapes that are conclusive on their
# own (a title in a language they do not work in, a different profession that
# happens to share a word). NEGATIVE is deliberately tiny, because a wrong
# entry there is an invisible loss.
POSITIVE = list(_S.POSITIVE)
NEGATIVE = list(getattr(_S, "NEGATIVE", []))


def title_verdict(title: str) -> tuple[str, str]:
    low = (title or "").lower()
    if not low:
        return "FLAG", "no title; Tier 2 decides"
    for pat, why in NEGATIVE:
        if re.search(pat, low):
            return "FAIL", why
    for pat in POSITIVE:
        if re.search(pat, low):
            return "PASS", f"matches {pat!r}"
    return "FAIL", "title matches none of the role families in profile/search.py POSITIVE"


def age_days(job: dict, today: _dt.date | None = None) -> int | None:
    """Days since the posting was published, or None when the portal gave no date.

    Only an ISO date is read. A relative string ("2 weeks ago"), an epoch or a
    US-format date is treated as no date, which keeps the posting (absence of a
    date is not evidence of age) but means the hard rule cannot act on it.
    """
    return days_since(job.get("date") or job.get("posted_date"), today, iso_only=True)


# An employer's own careers board is a different kind of source from an
# aggregator. A LinkedIn listing 40 days old may well have been filled and
# never taken down, which is what the age limit is for. A Greenhouse or Lever
# board is the system the employer runs its own hiring in: if the posting is
# still on it, the requisition is still open, and a `updated_at` from six
# weeks ago means nobody edited the description, not that nobody is hiring.
#
# Applying the aggregator's age limit to them cost a large share of a pass's
# postings, every one of them live.
#
# Workday and Ashby are the same kind of source, read by tools/ats_boards.py
# from the employer's own ATS. A Workday posting's date is the day it went up,
# and a requisition an employer opened in July and is still interviewing for is
# still listed because it is still open.
LIVE_BOARDS = {"greenhouse", "lever", "workday", "ashby"}


# Workday serves an employer's internal job site from the same host as its
# public one, and portals index both. A requisition on the internal site cannot
# be applied to from outside: one surfaced at fit 98 from a "/Privileged/" URL
# and was absent from the employer's "/External/" site. Only site names seen on
# real scrapes go here; a profile adds its employers' own (search.py
# WORKDAY_INTERNAL_SITES) once a round has shown one.
WORKDAY_INTERNAL_SITES = {"privileged"} | {
    str(x).lower() for x in getattr(_S, "WORKDAY_INTERNAL_SITES", ())}
_LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")


def workday_internal_site(url: str) -> str:
    """The internal Workday site a posting URL sits on, or "".

    https://<tenant>.wd3.myworkdayjobs.com/[<locale>/]<site>/job/... names the
    site in its first path segment after an optional locale.
    """
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if not parts.hostname or not parts.hostname.lower().endswith("myworkdayjobs.com"):
        return ""
    segs = [p for p in parts.path.split("/") if p]
    if segs and _LOCALE.match(segs[0]):
        segs = segs[1:]
    site = segs[0] if segs else ""
    return site if site.lower() in WORKDAY_INTERNAL_SITES else ""


def decide(job: dict, today: _dt.date | None = None,
           max_age: int = MAX_AGE_DAYS) -> tuple[bool, str]:
    site = workday_internal_site(job.get("url"))
    if site:
        return False, f"eligibility: internal Workday site ({site})"
    age = age_days(job, today)
    live = (job.get("portal") or "") in LIVE_BOARDS
    if age is not None and age > max_age and not live:
        return False, f"age: posted {age} days ago, past the {max_age}-day hard limit"
    lv, lwhy = location_verdict(job.get("location", ""), job.get("title", ""))
    if lv == "FAIL":
        return False, f"location: {lwhy}"
    tv, twhy = title_verdict(job.get("title", ""))
    if tv == "FAIL":
        return False, f"title: {twhy}"
    if age is None:
        agestr = "no date from the portal"
    elif live and age > max_age:
        agestr = f"{age}d old, kept: still listed on the employer's own board"
    else:
        agestr = f"{age}d old"
    return True, f"{agestr}; location {lv} ({lwhy}); title {tv} ({twhy})"


def annotate(job: dict, today: _dt.date | None = None,
             max_age: int = MAX_AGE_DAYS) -> tuple[bool, dict]:
    """The decision plus the row carrying it: reason, location verdict, age."""
    ok, why = decide(job, today, max_age)
    lv, lwhy = location_verdict(job.get("location", ""), job.get("title", ""))
    return ok, dict(job, prefilter_reason=why, location_verdict=lv,
                    location_reason=lwhy, age_days=age_days(job, today))


def already_ruled_out(seen_path: str):
    """A predicate over a posting: has this search already ruled it out?

    Returns `lambda job -> reason or ""`. A missing or unreadable seen file
    yields a predicate that never fires, because a cross-run gate that fails
    closed would silently empty a round.

    The decision is `throttle.ruled_out`, imported rather than restated, so
    this can only ever drop what the throttle would drop anyway.
    """
    try:
        with open(seen_path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return lambda job: ""
    entries = data.get("seen") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        entries = data if isinstance(data, dict) else {}
    try:
        from throttle import ruled_out
        from throttle import load_do_not_target, referral_holds
        from company_key import key as company_key
        from lookup_score import norm
    except ImportError:
        return lambda job: ""
    urls, pairs = ruled_out(entries)
    # The employer-level holds the throttle applies live: a referral in flight,
    # and an employer recorded as having no relevant presence until its review
    # date. ruled_out() no longer reads their old copies in seen_jobs.json,
    # because those outlived the hold; checked live here, they still cost
    # hydrate nothing, and they lift the day the hold does.
    try:
        live = {**referral_holds(), **load_do_not_target()}
    except Exception:                    # no contact book or do_not_target yet
        live = {}
    if not urls and not pairs and not live:
        return lambda job: ""

    def check(job) -> str:
        k = company_key(job.get("company"))
        if k and k in live:
            return live[k]
        n = norm(job.get("url") or "")
        if n and n in urls:
            return urls[n]
        t = (job.get("title") or "").strip().lower()
        if t and k and (t, k) in pairs:
            return pairs[(t, k)]
        return ""

    return check


def load_jobs(path: str) -> tuple[list, bool]:
    """Every stage reads a list or an id-keyed dict; returns (rows, was_dict)."""
    data = json.load(open(path))
    if isinstance(data, dict):
        if "seen" in data and isinstance(data["seen"], dict):
            data = data["seen"]
        return [dict(v, _key=k) if isinstance(v, dict) and "_key" not in v else v
                for k, v in data.items()], True
    return list(data), False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out")
    ap.add_argument("--dropped")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--jobage", type=int, default=MAX_AGE_DAYS,
                    help="hard freshness rule, days (default 14)")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--seen", default=None,
                    help="seen_jobs.json; also drop postings this search has "
                         "already ruled out, before hydrate pays for their bodies")
    a = ap.parse_args()
    today = _dt.date.fromisoformat(a.today) if a.today else _dt.date.today()

    rows, was_dict = load_jobs(a.infile)
    ruled = already_ruled_out(a.seen) if a.seen else (lambda job: "")
    kept, dropped = [], []
    n_seen = 0
    for job in rows:
        ok, row = annotate(job, today, a.jobage)
        # Checked after the intrinsic gates so `prefilter_reason` names the
        # cheapest true reason: a stale posting reads as stale whether or not
        # it was also excluded last week.
        if ok:
            why = ruled(job)
            if why:
                ok = False
                row["prefilter_reason"] = why
                n_seen += 1
        (kept if ok else dropped).append(row)
        if a.explain:
            mark = "KEEP" if ok else "DROP"
            print(f"{mark}  {str(job.get('company'))[:26]:26} "
                  f"{str(job.get('title'))[:46]:46} {row['prefilter_reason']}")

    print(f"\nTier 1: {len(kept)} kept, {len(dropped)} dropped, "
          f"{len(kept) + len(dropped)} in", file=sys.stderr)
    if a.seen:
        print(f"        {n_seen} of the dropped were already ruled out in "
              f"{os.path.basename(a.seen)}; hydrate no longer fetches them",
              file=sys.stderr)

    # The shape in is the shape out: a list stays a list (what every later
    # stage reads), an id-keyed dict stays keyed.
    def shape(items):
        if not was_dict:
            return [{k: v for k, v in r.items() if k != "_key"} for r in items]
        return {str(r.get("_key", i)): {k: v for k, v in r.items() if k != "_key"}
                for i, r in enumerate(items)}

    if a.out:
        json.dump(shape(kept), open(a.out, "w"), indent=1)
    if a.dropped:
        json.dump(shape(dropped), open(a.dropped, "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
