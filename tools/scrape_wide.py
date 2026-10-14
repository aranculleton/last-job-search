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
    python3 tools/scrape_wide.py --out DIR [--pages 5] [--jobage 14]

`--out` is a DIRECTORY: it receives scraped.json (everything), kept.json (past
the prefilter) and dropped.json. Exit 2 when more than a quarter of the portal
requests failed, after the files are written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import portals  # noqa: E402
from prefilter import annotate, age_days  # noqa: E402

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
# other portal that is on and has a CLI is called through the portal contract
# (`contract_search` below): a person's own board, built by /add-portal, is
# searched by every round without anyone wiring it in.
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
# ("Toronto, ON" where LinkedIn wants "Toronto, Ontario, Canada"). A portal not
# named searches the first of SCRAPE_LOCATIONS.
PORTAL_LOCATIONS = {str(k): list(v) for k, v in
                    dict(getattr(_S, "PORTAL_LOCATIONS", {}) or {}).items()}


def run(cmd: list[str], timeout: int = 90) -> tuple[dict | None, str | None]:
    """(parsed JSON, None) on success; (None, reason) on any failure.

    Failures used to vanish: a blocked or rate-limited portal just produced a
    smaller file with exit 0 and nothing said so. Every failure now has a
    reason, and main() counts them per portal and refuses to look healthy
    when more than a quarter of the requests failed.

    ## Why stdout goes to a FILE and not a pipe

    A live round reported `freehire: 327/441 requests failed` with
    `JSONDecodeError: Unterminated string starting at: line 363`. Run one at a
    time the same queries succeed every time; run ten at once and all ten fail,
    each returning 65,381 or 65,443 or 65,203 bytes. That is 64 KiB, a pipe
    buffer.

    Node writes to stdout ASYNCHRONOUSLY when stdout is a pipe and
    SYNCHRONOUSLY when it is a regular file. A CLI that calls `process.exit()`
    after writing therefore loses whatever has not drained, and under
    concurrency nothing drains: one query's 160 KB of JSON arrives as the
    first 64 KB, cut mid-string. Exit status is 0, because as far as the
    process is concerned it wrote and exited.

    The failure is silent in the worst way. A truncated body is not an error
    the portal reported, it is a portal that looks slow, and three quarters of
    one of the two enabled sources was being thrown away every round.

    A temporary file costs nothing and removes the buffer entirely. The fix is
    on this side on purpose: the portal CLIs are plug-ins, `/add-portal`
    scaffolds more of them, and every one written the same way would carry the
    same bug.
    """
    env = dict(os.environ, NODE_USE_ENV_PROXY="1")
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8") as fh:
            p = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                               text=True, timeout=timeout, env=env)
            fh.seek(0)
            out = fh.read()
        if p.returncode != 0:
            err = (p.stderr or "").strip().splitlines()
            return None, f"exit {p.returncode}: {err[-1][:120] if err else 'no stderr'}"
        if not out.strip():
            return None, "empty output"
        return json.loads(out), None
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def linkedin(q: str, loc: str, page: int, jobage: int,
             remote: bool = False) -> tuple[list[dict], str | None]:
    cmd = ["node", "--no-warnings", LINKEDIN(), "search", "-q", q, "-l", loc,
           "--jobage", str(jobage), "--page", str(page), "--format", "json"]
    if remote:
        cmd += ["--remote", "remote"]
    d, err = run(cmd)
    out = []
    for r in (d or {}).get("results", []):
        out.append({"id": r.get("id"), "title": r.get("title"),
                    "company": r.get("company"), "url": r.get("url"),
                    "location": r.get("location"), "date": (r.get("date") or "")[:10],
                    "portal": "linkedin", "desc": None})
    return out, err


def freehire(q: str, page: int, jobage: int) -> tuple[list[dict], str | None]:
    d, err = run(["node", "--no-warnings", FREEHIRE(), "search", "-q", q,
                  "--country", PORTAL_COUNTRY, "--jobage", str(jobage), "--limit", "25",
                  "--page", str(page), "--format", "json"])
    out = []
    for r in (d or {}).get("results", []):
        out.append({"id": str(r.get("id")), "title": r.get("title"),
                    "company": r.get("company"), "url": r.get("url"),
                    "location": r.get("location"), "date": (r.get("date") or "")[:10],
                    "portal": "freehire", "desc": r.get("description")})
    return out, err


def contract(skill: str, q: str, loc: str | None, page: int,
             jobage: int) -> tuple[list[dict], str | None]:
    """One search on a portal that follows the portal contract (/add-portal).

    A search result's `description` is kept as `snippet`, not as the body:
    most boards return a teaser there, and a teaser would stop hydrate.py
    fetching the real posting. Where the board's posting pages may not be
    fetched (`detail: false`), the snippet is all there is, and it is the body.
    """
    cmd = (["node", "--no-warnings", portal_cli(skill), "search", "-q", q]
           + (["-l", loc] if loc else [])
           + ["--jobage", str(jobage), "--page", str(page), "--format", "json"])
    d, err = run(cmd)
    whole = not portals.has_detail(skill)
    out = []
    for r in (d or {}).get("results", []):
        text = r.get("description") or None
        out.append({"id": None if r.get("id") is None else str(r.get("id")),
                    "title": r.get("title"), "company": r.get("company"),
                    "url": r.get("url"), "location": r.get("location"),
                    "date": (r.get("date") or "")[:10], "portal": portals.short(skill),
                    "desc": text if whole else None, "snippet": text})
    return out, err


def contract_portals(on: dict[str, bool]) -> list[str]:
    """Every portal that is on, is not one of the app's two, and has a CLI."""
    return [n for n, v in sorted(on.items())
            if v and n not in WIRED and portals.has_cli(n)]


def portal_locations(skill: str) -> list[str | None]:
    if not portals.takes_location(skill):
        return [None]
    return PORTAL_LOCATIONS.get(skill) or LOCATIONS[:1]


def sweep(skill: str, tasks: list[tuple], jobage: int,
          sleep=time.sleep) -> tuple[list[dict], int, list[str]]:
    """Every request for one person's portal, one at a time, `crawl-delay` apart.

    Its own thread, so a board that asks for five seconds between requests
    takes its time without holding a worker the app's portals need. It waits
    before the first request too: the health probe has just asked.
    """
    delay, rows, failed = portals.crawl_delay(skill), [], []
    for _, q, loc, pg in tasks:
        if delay:
            sleep(delay)
        try:
            got, err = contract(skill, q, loc, pg, jobage)
        except Exception as e:
            got, err = [], f"{type(e).__name__}: {str(e)[:120]}"
        if err:
            failed.append(err)
        rows += got
    return rows, len(tasks), failed


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


class PortalDown(RuntimeError):
    """A portal answered, without error, and returned nothing at all."""


def canary(jobage: int = CANARY_JOBAGE,
           on: dict[str, bool] | None = None) -> dict[str, tuple[bool, str]]:
    """One broad probe per enabled portal. {portal: (healthy, detail)}."""
    on = portals.enabled() if on is None else on
    out: dict[str, tuple[bool, str]] = {}
    probes = [
        ("linkedin", lambda: linkedin(CANARY_QUERY, CANARY_LOCATION, 1, jobage)),
        ("freehire", lambda: freehire(CANARY_QUERY, 1, jobage)),
    ]
    wanted = {short for skill, short in WIRED.items() if on.get(skill)}
    for skill in contract_portals(on):
        loc = portal_locations(skill)[0]
        probes.append((portals.short(skill),
                       functools.partial(contract, skill, CANARY_QUERY, loc, 1, jobage)))
        wanted.add(portals.short(skill))
    for name, fn in probes:
        if name not in wanted:
            continue
        try:
            rows_, err = fn()
        except Exception as e:                      # a build or resolve failure
            out[name] = (False, f"{type(e).__name__}: {str(e)[:150]}")
            continue
        if err:
            # An error IS diagnosable downstream, and the existing failure
            # fraction already covers it. Not the canary's job.
            out[name] = (True, f"probe errored ({err[:80]}), left to the scrape")
        elif not rows_:
            out[name] = (False, f'0 results for "{CANARY_QUERY}" in '
                                f'{CANARY_LOCATION if name in WIRED.values() else "its search"} '
                                f'over {jobage} days')
        else:
            out[name] = (True, f"{len(rows_)} results")
    return out


def canary_report(health: dict[str, tuple[bool, str]]) -> tuple[str, bool]:
    """A human line per portal, and whether every portal is usable."""
    lines, ok = [], True
    for name, (healthy, detail) in sorted(health.items()):
        lines.append(f"  {'OK  ' if healthy else 'DOWN'} {name}: {detail}")
        ok = ok and healthy
    if not ok:
        lines.append("A portal returning nothing to a deliberately broad query is "
                     "broken, not evidence of a thin market. Fix the portal before "
                     "reading this round's yield.")
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


def build_tasks(on: dict[str, bool], pages: int) -> list[tuple]:
    """(kind, query, location, page) for every request, for the portals that are on.

    `kind` is "li", "lir" or "fh" for the app's two portals, and the portal's
    own name for a person's portal, whose requests come last and are sent by
    `sweep`, paced."""
    li, fh = on.get("linkedin-search"), on.get("freehire-search")
    tasks = []
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
    for emp in EMPLOYERS:
        for t in EMPLOYER_QUERIES:
            q = f"{emp} {t}"
            if li:
                for loc in EMPLOYER_LOCATIONS:
                    tasks.append(("li", q, loc, 1))
                for loc in EMPLOYER_REMOTE:
                    tasks.append(("lir", q, loc, 1))
            if fh:
                tasks.append(("fh", q, None, 1))
    # A person's own portals: every query at each of its places, as deep as it
    # says (`pages:`, capped by --pages), and the named employers on page one at
    # its first place.
    for skill in contract_portals(on):
        places = portal_locations(skill)
        depth = min(pages, portals.pages(skill))
        for q in QUERIES:
            for loc in places:
                for pg in range(1, depth + 1):
                    tasks.append((skill, q, loc, pg))
        for emp in EMPLOYERS:
            for t in EMPLOYER_QUERIES:
                tasks.append((skill, f"{emp} {t}", places[0], 1))
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--jobage", type=int, default=14)
    ap.add_argument("--today", default=None)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--skip-canary", action="store_true",
                    help="skip the pre-flight portal probe (offline replays)")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    if not (QUERIES and LOCATIONS):
        print("scrape_wide: profile/search.py names no SCRAPE_QUERIES or "
              "SCRAPE_LOCATIONS, so there is nothing to search: run /setup",
              file=sys.stderr)
        return 1
    os.makedirs(a.out, exist_ok=True)

    on = portals.enabled()
    for name in portals.unknown():
        print(f"portals: PORTALS in profile/search.py names {name!r}, which is not "
              f"an installed portal, so it switches nothing", file=sys.stderr)
    print("portals: " + ", ".join(f"{n} {'on' if v else 'off'}" for n, v in on.items()))
    for name in sorted(n for n, v in on.items() if v and n not in WIRED
                       and not portals.has_cli(n)):
        print(f"portals: {name} is on but has no CLI, so a round cannot call it; "
              f"/scrape runs it from its SKILL.md")

    # One broad probe per portal that is on, before the sweep. A portal that has
    # gone quiet is reported as broken here rather than as a thin market three
    # widenings later. It does not abort the round: the other sources' results
    # are still worth having, and a round that says so beats a round that stops.
    if not a.skip_canary:
        health = canary(a.jobage, on)
        report, ok = canary_report(health)
        print("portal health:")
        print(report)
        if not ok:
            down = [n for n, (h, _) in health.items() if not h]
            json.dump({"portals_down": down, "detail": {k: v[1] for k, v in health.items()}},
                      open(os.path.join(a.out, "00_portal_health.json"), "w"), indent=1)

    tasks = build_tasks(on, a.pages)
    if not tasks:
        print("portals: none of the portals this scrape can call is on, so this "
              "round is the employer boards alone (python3 tools/portals.py)")

    seen: dict[str, dict] = {}
    sent: dict[str, int] = {}
    failed: dict[str, list[str]] = {}
    mine: dict[str, list[tuple]] = {}
    for task in tasks:
        if task[0] not in ("li", "lir", "fh"):
            mine.setdefault(task[0], []).append(task)
    paced = ThreadPoolExecutor(max_workers=max(1, len(mine)))
    sweeps = {paced.submit(sweep, skill, ts, a.jobage): portals.short(skill)
              for skill, ts in mine.items()}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {}
        for kind, q, loc, pg in tasks:
            if kind in mine:
                continue
            portal = "freehire" if kind == "fh" else "linkedin"
            sent[portal] = sent.get(portal, 0) + 1
            if kind == "li":
                futs[ex.submit(linkedin, q, loc, pg, a.jobage)] = portal
            elif kind == "lir":
                futs[ex.submit(linkedin, q, loc, pg, a.jobage, True)] = portal
            else:
                futs[ex.submit(freehire, q, pg, a.jobage)] = portal
        for f in as_completed(futs):
            portal = futs[f]
            try:
                rows_, err = f.result()
            except Exception as e:
                rows_, err = [], f"{type(e).__name__}: {str(e)[:120]}"
            if err:
                failed.setdefault(portal, []).append(err)
            for r in rows_:
                if r.get("url"):
                    seen.setdefault(r["url"], r)
    for f in as_completed(sweeps):
        portal = sweeps[f]
        try:
            rows_, n, errs = f.result()
        except Exception as e:
            rows_, n, errs = [], 1, [f"{type(e).__name__}: {str(e)[:120]}"]
        sent[portal] = n
        if errs:
            failed.setdefault(portal, []).extend(errs)
        for r in rows_:
            if r.get("url"):
                seen.setdefault(r["url"], r)
    paced.shutdown()

    # Employer boards, straight from the ATS: Greenhouse, Lever, Ashby and
    # Workday. No key, no HTML, and keyed by EMPLOYER rather than by keyword,
    # which is the one thing a portal search cannot do: the profile names the
    # target employers and until then they were a preference stated in prose.
    # One analytics engineering role that scored 86 was invisible to both
    # portals, and the employers that run Workday were visible only when
    # LinkedIn happened to index them.
    #
    # Additive and best-effort. A board that stops resolving is reported, never
    # fatal, and the portals still carry the round.
    try:
        from ats_boards import fetch_all as _ats_fetch
        ats_notes: dict[str, str] = {}
        ats_rows, ats_quiet = _ats_fetch(notes=ats_notes)
        for r in ats_rows:
            if r.get("url"):
                seen.setdefault(r["url"], r)
        ats_by: dict[str, int] = {}
        for r in ats_rows:
            ats_by[r.get("portal")] = ats_by.get(r.get("portal"), 0) + 1
        print(f"ats boards: {len(ats_rows)} in-range postings "
              f"({', '.join(f'{k} {v}' for k, v in sorted(ats_by.items()))})")
        for employer, why in sorted(ats_quiet.items()):
            print(f"  quiet: {employer}: {why}")
        for employer, why in sorted(ats_notes.items()):
            print(f"  partial: {employer}: {why}")
    except Exception as e:            # a new source must never break a round
        print(f"ats boards: skipped ({type(e).__name__}: {e})", file=sys.stderr)

    rows = list(seen.values())
    kept, dropped = [], []
    for j in rows:
        ok, row = annotate(j, today, a.jobage)
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

    json.dump(kept, open(f"{a.out}/kept.json", "w"), indent=1)
    # LinkedIn's search endpoint returns no body, so `desc` is None for every
    # LinkedIn row here. Anything downstream that reads a posting - the text
    # screen, the knockout stage, the extractor - is blind until
    # tools/hydrate.py fills them in, and it fails quietly rather than loudly.
    # Say so, loudly, rather than letting a caller assume these are readable.
    blind = sum(1 for j in kept if not (j.get("desc") or "").strip())
    if blind:
        print(f"WARNING: {blind}/{len(kept)} kept postings have NO description. "
              f"Run `python3 tools/hydrate.py {a.out}/kept.json --out "
              f"{a.out}/hydrated.json` before ranking, screening or extracting, "
              f"or every one of them reaches the model blind.")
    json.dump(dropped, open(f"{a.out}/dropped.json", "w"), indent=1)
    json.dump(rows, open(f"{a.out}/scraped.json", "w"), indent=1)
    print(f"{len(tasks)} requests -> {len(rows)} unique postings {by_portal}")
    print(f"prefilter kept {len(kept)}, dropped {len(dropped)}; age {buckets}")
    report, bad = failure_report(sent, failed)
    print(report)
    return 2 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
