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

THE READING IS OPENROLES. Fetching and parsing every board is the vendored copy of
openroles (tools/openroles/, github.com/aranculleton/openroles), the open source
library this file grew into. What stays here is the search's own: where the person
can work, which titles are worth a Workday body request, the map, and the probe.

Usage:
    python3 tools/ats_boards.py --out ats.json
    python3 tools/ats_boards.py --find "<Employer>"           # or its careers page URL
    python3 tools/ats_boards.py --probe
    python3 tools/ats_boards.py --add greenhouse <board>    # verify then print
    python3 tools/ats_boards.py --add ashby <board>
    python3 tools/ats_boards.py --add workday https://<tenant>.wd3.myworkdayjobs.com/<Site>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from openroles import BoardError  # noqa: E402
from openroles import _http as _net  # noqa: E402
from openroles import detect as _detect  # noqa: E402
from openroles.models import html_to_text  # noqa: E402
from openroles.providers import ashby as _ashby  # noqa: E402
from openroles.providers import greenhouse as _greenhouse  # noqa: E402
from openroles.providers import lever as _lever  # noqa: E402
from openroles.providers import workday as _workday  # noqa: E402
from prefilter import location_verdict, title_verdict  # noqa: E402

GREENHOUSE = _greenhouse.URL
LEVER = _lever.HOSTS[0] + _lever.PATH
ASHBY = _ashby.URL
ASHBY_HOST = _ashby.HOST

UA = "last-job-search/1.0 (personal job search; contact via GitHub)"
TIMEOUT = 20

# Checked for every agent a rule could be written for: everyone, the token WebFetch
# sends (robots_check reads the same pair), this tool's own, and the library's. An
# agent with no group of its own falls back to "*".
ROBOTS_AGENTS = ("*", "Claude-User", "last-job-search", "openroles")

# The library's requests go out as this app, under this app's robots.txt agents.
_net.USER_AGENT = UA
_net.AGENTS = ROBOTS_AGENTS
_net.TIMEOUT = TIMEOUT
PER_HOST = _net.PER_HOST

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
# wildly by employer, so it is a list of places, not a parser. No profile list
# means nothing is wanted but a bare "Remote".
PLACES = getattr(_B, "PLACES", None) or re.compile(r"(?!x)x")

# A location that says the job is remote and names no geography at all.
BARE_REMOTE = re.compile(r"^\W*(fully |100% )?remote\W*$", re.I)

BODY_CAP = 20_000

# Kept for callers and tests that read them from here.
_epoch_ms_date = _lever._epoch_ms_date
_with_country = _workday.with_country


def _text(content: str) -> str:
    return html_to_text(content)[:BODY_CAP]


def _why(err: Exception) -> str:
    """The library's message without its "ats:token: " prefix: the caller names the board."""
    msg = str(err)
    head, sep, rest = msg.partition(": ")
    return rest if sep and ":" in head and " " not in head else msg


def robots_allows(host: str, paths) -> tuple[bool, str]:
    """(may these paths be read, why), from the host's robots.txt."""
    return _net.robots_allows(host, paths)


# ------------------------------------------------------------------ location

def _wanted(location: str) -> bool:
    """Could the candidate actually take this job. Positive evidence only.

    A wanted place wins outright, because a multi-site posting that includes the
    candidate's city is one they can take whatever else it lists. Everything else is
    out, and the default is deliberately the strict one: a filter that kept anything
    not naming a foreign place let an employer's "Hybrid", "Distributed" and
    "In-Office" postings through by the hundred, none of them shown to be anywhere the
    candidate could work. A whitelist is wrong only in the direction that costs recall,
    on one source among several.
    """
    loc = (location or "").strip()
    if not loc:
        return False
    return bool(PLACES.search(loc) or BARE_REMOTE.match(loc))


_RANK = {"PASS": 0, "FLAG": 1, "FAIL": 2}


def _choose(labels, title: str = "", remote: bool = False) -> tuple[str, str]:
    """(the locations the candidate could take the job in, as one string, their verdict).

    A multi-site posting is one they can take if any site is one they can work from,
    but prefilter reads the location as ONE string, and a string that names two places
    reads as the worse of them. So every site is judged alone with prefilter's own gate,
    and only the best-judged ones are kept. ("", "FAIL") when none is a wanted place.
    `remote` is the ATS's own flag: it only makes sure the word is in the string.
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
    # Two sites that each pass can still read worse joined.
    if len(keep) > 1 and _RANK[location_verdict(joined, title)[0]] > best:
        joined = keep[0]
    return joined, next(v for v, r in _RANK.items() if r == best)


# ------------------------------------------------- greenhouse, lever, ashby

def _row(employer: str, job, location: str, portal: str, desc=None, deadline=None) -> dict:
    row = {"id": job.id, "title": job.title, "company": employer, "url": job.url or None,
           "location": location, "date": job.posted, "portal": portal,
           "desc": (desc if desc is not None else job.description or "")[:BODY_CAP] or None}
    if deadline is not False:
        row["deadline"] = deadline or None
    return row


def _greenhouse_rows(employer: str, jobs) -> list[dict]:
    return [_row(employer, j, j.location, "greenhouse", deadline=j.deadline)
            for j in jobs if _wanted(j.location)]


def _lever_rows(employer: str, jobs) -> list[dict]:
    # The body is the intro, the requirement lists and the closing text: the intro
    # alone (all this read before openroles) left a posting's requirements out.
    return [_row(employer, j, j.location, "lever", deadline=False)
            for j in jobs if _wanted(j.location)]


def _ashby_rows(employer: str, jobs) -> list[dict]:
    out = []
    for j in jobs:
        location, _ = _choose(j.locations, j.title, j.remote is True)
        if not location:
            continue
        desc = j.description or ""
        if j.compensation:
            # A line text_screen's salary reader recognises: a cue word and the range.
            # The body is cut first so the cap can never cut it off.
            line = f"Compensation (as posted on the board): {j.compensation}"
            desc = f"{desc[:BODY_CAP - len(line) - 2]}\n\n{line}".strip()
        out.append(_row(employer, j, location, "ashby", desc=desc, deadline=False))
    return out


def greenhouse(employer: str, token: str) -> tuple[list[dict], str | None]:
    try:
        return _greenhouse_rows(employer, _greenhouse.fetch(token)), None
    except BoardError as e:
        return [], _why(e)


def lever(employer: str, token: str) -> tuple[list[dict], str | None]:
    try:
        return _lever_rows(employer, _lever.fetch(token)), None
    except BoardError as e:
        return [], _why(e)


def ashby(employer: str, token: str) -> tuple[list[dict], str | None]:
    try:
        return _ashby_rows(employer, _ashby.fetch(token)), None
    except BoardError as e:
        return [], _why(e)


# ------------------------------------------------------------------- workday
#
# A board up to PAGE_ALL_MAX postings is paged whole, after narrowing it to the
# profile's country with the board's own country facet, and filtered here. Anything
# bigger is searched instead, once per title variant in scrape_wide.QUERIES, so a
# round does not page through a thousand branch and call-centre roles to find the
# analytics ones, and so a board past Workday's 2,000 cap is read at all.
PAGE_ALL_MAX = 1000

# The country a Workday board is narrowed to: (Workday's facet value id, the value's
# name), from profile/boards.py. No country set means no narrowing.
COUNTRY_ID, COUNTRY_NAME = getattr(_B, "WORKDAY_COUNTRY", ("", ""))

WORKDAY_TOKEN = _workday.TOKEN
MULTI = _workday.MULTI
workday_token = _workday.token_from


def workday_board(token: str) -> tuple[str, str, str] | None:
    """(host, tenant, site) for a "tenant.wdN/Site" token, or None."""
    m = WORKDAY_TOKEN.match(token or "")
    if not m:
        return None
    return f"{m['tenant']}.{m['dc']}.myworkdayjobs.com", m["tenant"], m["site"]


def workday_paths(tenant: str, site: str) -> list[str]:
    """What robots.txt must allow: the listing, the bodies, and the board itself."""
    paths = [f"/wday/cxs/{tenant}/{site}/jobs", f"/wday/cxs/{tenant}/{site}/job/", f"/{site}/"]
    return paths + ([f"/{site.lower()}/"] if site != site.lower() else [])


def _remote(remote_type) -> bool:
    return str(remote_type or "").strip().lower() == "remote"


def _summarise(errors: list[str]) -> str:
    counts: dict[str, int] = {}
    for e in errors:
        counts[e] = counts.get(e, 0) + 1
    return ", ".join(f"{n}x {e}" for e, n in sorted(counts.items(), key=lambda x: -x[1])[:3])


def _wd_listing(board, queries=None):
    """(listing, country count or None, errors), after robots and the first page."""
    board.check_robots()
    first = board.first()
    facets, in_country = board.country_facet(first.get("facets"), COUNTRY_NAME, COUNTRY_ID)
    total = int((in_country if in_country is not None else first.get("total")) or 0)
    if total > PAGE_ALL_MAX:
        if queries is None:
            from scrape_wide import QUERIES as queries
        listing = board.search(facets, queries)
    else:
        listing = board.all_postings(facets, total, None if facets else first["jobPostings"])
    return listing, first, facets, in_country


def workday(employer: str, token: str, queries=None,
            today: dt.date | None = None) -> tuple[list[dict], str | None]:
    """Rows from a Workday board, fetching a body only where the free gates say it could matter.

    A body costs one request, so it is fetched for a posting prefilter would keep: a
    title its gate passes, in a place its gate does not fail. A posting that fails
    either is still emitted, without a body, so prefilter drops it with the reason and
    the funnel stays readable. A listing that says only "3 Locations" names no place at
    all: its body is fetched to find out where when the title is worth it.
    """
    today = today or dt.date.today()
    try:
        board = _workday.WorkdayBoard(token)
    except BoardError:
        return [], f"not a Workday token (want tenant.wdN/Site): {token!r}"
    try:
        listing, *_ = _wd_listing(board, queries)
    except BoardError as e:
        return [], _why(e)
    errors = list(board.errors)
    rows, fetch, seen = [], [], set()
    for p in listing:
        job = board.job(p, today)
        if job is None or p["externalPath"] in seen:
            continue
        seen.add(p["externalPath"])
        where = str(p.get("locationsText") or "")
        title_ok = title_verdict(job.title)[0] != "FAIL"
        if MULTI.match(where):
            if title_ok:
                fetch.append((p, job))
            continue
        location, verdict = _choose([where], job.title, _remote(p.get("remoteType")))
        if not location:
            continue
        if title_ok and verdict != "FAIL":
            fetch.append((p, job))
        else:
            rows.append(_row(employer, job, location, "workday", desc="", deadline=None))
    failed = []
    pages = _workday._parallel(lambda pj: board.detail(pj[0]["externalPath"]), fetch)
    for (p, job), (detail, err) in zip(fetch, pages, strict=True):
        info = detail.get("jobPostingInfo") if isinstance(detail, dict) else None
        if err or not isinstance(info, dict):
            failed.append(err or "a posting page that was not a posting")
            continue
        board.detailed(job, p, detail, today)
        location, _ = _choose(job.locations, job.title,
                              _remote(info.get("remoteType") or p.get("remoteType")))
        if location:
            rows.append(_row(employer, job, location, "workday", deadline=job.deadline))
    notes = []
    if errors:
        notes.append(f"{len(errors)} listing page(s) failed ({_summarise(errors)})")
    if failed:
        notes.append(f"{len(failed)} of {len(fetch)} posting bodies failed ({_summarise(failed)}) "
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
    try:
        board = _workday.WorkdayBoard(token)
    except BoardError:
        return f"NOT A WORKDAY TOKEN ({token!r})"
    try:
        board.check_robots()
        first = board.first()
    except BoardError as e:
        return (f"REFUSED ({_why(e)})" if "robots.txt" in str(e) else f"NO JOBS ({_why(e)})")
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


_READERS = {"greenhouse": (_greenhouse, _greenhouse_rows), "lever": (_lever, _lever_rows),
            "ashby": (_ashby, _ashby_rows)}


def probe(boards=None) -> dict[str, str]:
    """{employer: verdict}. A token that stops resolving is a repair, not news."""
    boards = BOARDS if boards is None else boards
    out = {}
    for employer, (kind, token) in sorted(boards.items()):
        if kind == "workday":
            out[employer] = _probe_workday(token)
            continue
        reader, rows_of = _READERS[kind]
        try:
            jobs = reader.fetch(token)
        except BoardError as e:
            out[employer] = (f"REFUSED ({_why(e)})" if "robots.txt" in str(e)
                             else f"NO JOBS ({_why(e)})")
            continue
        out[employer] = (f"{len(jobs)} open, {len(rows_of(employer, jobs))} in range" if jobs
                         else "NO JOBS (token may be wrong)")
    for employer, (kind, token, why) in sorted(REFUSED.items()):
        host, tenant, site = workday_board(token) or ("", "", "")
        out[f"{employer} [refused]"] = _probe_refused(
            host, workday_paths(tenant, site), why, f"{kind} {token}")
    for kind, (host, path, why) in sorted(REFUSED_PROVIDERS.items()):
        out[f"{kind} [refused]"] = _probe_refused(host, [path], why, f"{kind} <board>")
    return out


def find(target: str) -> list[tuple[str, str, int, int]]:
    """[(kind, token, open roles, in range)] for an employer's name or careers page.

    How a board gets into the map in the first place: openroles tries the names an
    employer is likely to use on Greenhouse, Lever and Ashby, or reads a careers page
    for the board it links to. Workday cannot be guessed from a name: give its URL.
    """
    out = []
    for board in _detect(target):
        if board.ats == "workday":
            rows, _err = workday(target, board.token)
            out.append((board.ats, board.token, -1, len(rows)))
            continue
        reader, rows_of = _READERS[board.ats]
        try:
            jobs = reader.fetch(board.token)
        except BoardError:
            continue
        out.append((board.ats, board.token, len(jobs), len(rows_of(target, jobs))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="write the rows as JSON")
    ap.add_argument("--probe", action="store_true", help="re-check every token")
    ap.add_argument("--find", metavar="EMPLOYER_OR_URL",
                    help="find an employer's board from its name or careers page")
    ap.add_argument("--add", nargs=2, metavar=("PROVIDER", "TOKEN"),
                    help="verify one board before adding it to the map; for "
                         "workday, TOKEN may be the careers site's URL")
    a = ap.parse_args()

    if a.find:
        found = find(a.find)
        for kind, token, total, in_range in found:
            seen = f"{total} open, " if total >= 0 else ""
            print(f"{kind}/{token}: {seen}{in_range} in range")
            print(f'  map entry: "<Employer>": ("{kind}", "{token}"),')
        if not found:
            print(f"ats_boards: no Greenhouse, Lever or Ashby board found for {a.find!r}; "
                  "for Workday, give the careers site's URL", file=sys.stderr)
        return 0 if found else 1

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
