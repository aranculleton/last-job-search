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
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import portals  # noqa: E402
from prefilter import annotate, age_days, stamp_copies  # noqa: E402

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

# Where a round runs decides how hard it leans on the portals. A cloud container is
# a throwaway address; a person's own computer is the address their own LinkedIn
# account signs in from, and a round of thousands of requests from it is a risk to
# them (the linkedin-search skill says keep volume low). So off the cloud a round
# asks for fewer pages, with fewer at once, and at most LOCAL_MAX_REQUESTS of each
# app portal, unless profile/search.py sets its own (SCRAPE_PAGES, SCRAPE_WORKERS,
# SCRAPE_MAX_REQUESTS): the person's trade-off to make, never the app's.
CLOUD = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"
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
                    "location": _remote_mark(r.get("location"), remote),
                    "date": (r.get("date") or "")[:10],
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
             jobage: int, remote: bool = False) -> tuple[list[dict], str | None]:
    """One search on a portal that follows the portal contract (/add-portal).

    A search result's `description` is kept as `snippet`, not as the body:
    most boards return a teaser there, and a teaser would stop hydrate.py
    fetching the real posting. Where the board's posting pages may not be
    fetched (`detail: false`), the snippet is all there is, and it is the body.
    """
    cmd = (["node", "--no-warnings", portal_cli(skill), "search", "-q", q]
           + (["-l", loc] if loc else [])
           + (["--remote"] if remote else [])
           + ["--jobage", str(jobage), "--page", str(page), "--format", "json"])
    d, err = run(cmd)
    whole = not portals.has_detail(skill)
    out = []
    for r in (d or {}).get("results", []):
        text = r.get("description") or None
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


def sweep(skill: str, tasks: list[tuple], jobage: int, sleep=time.sleep,
          clock=time.monotonic, tally: "Tally | None" = None,
          on_rows=None) -> tuple[list[dict], int, list[str]]:
    """Every request for one person's portal, one at a time, `crawl-delay` apart.

    Its own thread, so a board that asks for five seconds between requests
    takes its time without holding a worker the app's portals need. It waits
    before the first request too: the health probe has just asked. It stops
    at SWEEP_BUDGET or SWEEP_MAX_FAILS failures in a row, and says so.
    """
    delay, rows, failed = portals.crawl_delay(skill), [], []
    start, streak, sent = clock(), 0, 0
    for task in tasks:
        q, loc, pg = task[1:4]
        remote = len(task) > 4 and task[4]
        if streak >= SWEEP_MAX_FAILS:
            failed.append(f"stopped after {streak} failures in a row; "
                          f"{len(tasks) - sent} requests not sent")
            break
        if clock() - start > SWEEP_BUDGET:
            print(f"portals: {skill} stopped at its {SWEEP_BUDGET // 60}-minute budget, "
                  f"{len(tasks) - sent} of {len(tasks)} requests not sent", file=sys.stderr)
            break
        if delay:
            sleep(delay)
        try:
            got, err = (contract(skill, q, loc, pg, jobage, remote=True) if remote
                        else contract(skill, q, loc, pg, jobage))
        except Exception as e:
            got, err = [], f"{type(e).__name__}: {str(e)[:120]}"
        sent += 1
        streak = streak + 1 if err else 0
        if err:
            failed.append(err)
        rows += got
        if on_rows and got:
            on_rows(list(got))
        if tally is not None:
            tally.sent, tally.failed = sent, list(failed)
            tally.limited += int(rate_limited(err))
            tally.timeouts += int(bool(err) and "timeout" in err.lower())
    if tally is not None:
        tally.sent, tally.failed = sent, list(failed)
        if sent < len(tasks):
            tally.stopped = (f"{streak} failures in a row" if streak >= SWEEP_MAX_FAILS
                             else f"its {SWEEP_BUDGET // 60}-minute budget ran out")
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
# POOL_MAX_LIMITED in a row; and it prints a line per portal every PROGRESS_SECONDS,
# so a chat can tell a slow round from a hung one.
POOL_BUDGET = 20 * 60
POOL_MAX_LIMITED = 3
BACKOFF_SECONDS = 60
PROGRESS_SECONDS = 60
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

    def line(self, left: float | None = None) -> str:
        bits = [f"{self.sent}/{self.total} sent", f"{len(self.failed)} failed"]
        if self.limited or self.timeouts:
            bits.append(f"{self.limited} rate-limited (429), {self.timeouts} timed out")
        if self.capped:
            bits.append(f"{self.capped} deeper page(s) left by the round's cap")
        if self.stopped:
            bits.append(f"stopped: {self.stopped}")
        elif left is not None:
            bits.append(f"{max(0, int(left // 60))} min left")
        return f"progress: {self.name} " + ", ".join(bits)


def _say(line: str, log=None) -> None:
    print(line, file=sys.stderr, flush=True)
    if log:
        try:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def pool(jobs: list[tuple], workers: int, budget: float = POOL_BUDGET, cap: int | None = None,
         clock=time.monotonic, sleep=time.sleep, tallies: dict | None = None,
         on_rows=None) -> tuple[list[dict], dict]:
    """Run [(portal, fn, args)] on `workers` threads until done or `budget` runs out.

    Each portal gets a Tally (in `tallies`, shared with the progress line). A 429
    halves that portal's share of the workers and pauses it (Retry-After, else
    BACKOFF_SECONDS times the run of 429s); POOL_MAX_LIMITED in a row stops it. `cap`
    is the most requests a portal may send. `on_rows` sees each batch of rows as it
    lands, which is how a partial scrape survives a stage that is killed.
    Returns (rows, tallies)."""
    tallies = {} if tallies is None else tallies
    for portal in dict.fromkeys(j[0] for j in jobs):
        n = sum(1 for j in jobs if j[0] == portal)
        tallies.setdefault(portal, Tally(portal, min(n, cap) if cap else n, workers, cap))
    queue, rows, lock = deque(jobs), [], threading.Lock()
    start = clock()

    def take():
        now = clock()
        if now - start >= budget:
            return "done", None
        waits = []
        for i, job in enumerate(queue):
            t = tallies[job[0]]
            if t.stopped or (t.cap and t.sent + t.active >= t.cap):
                continue
            if t.until > now:
                waits.append(t.until - now)          # backing off after a 429
                continue
            if t.active >= t.limit:
                waits.append(0.2)                    # its share of the workers is busy
                continue
            del queue[i]
            t.active += 1
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
                    t.failed.append(err)
                    if rate_limited(err):
                        t.limited += 1
                        t.streak += 1
                        t.limit = max(1, t.limit // 2)
                        t.until = clock() + (retry_after(err) or BACKOFF_SECONDS * t.streak)
                        if t.streak >= POOL_MAX_LIMITED:
                            t.stopped = (f"rate-limited {t.streak} times in a row (HTTP 429); "
                                         "the portal is asking for less")
                    elif "timeout" in err.lower():
                        t.timeouts += 1
                else:
                    t.streak = 0
                    rows.extend(got or ())
                    if on_rows and got:
                        on_rows(list(got))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    for portal, t in tallies.items():
        left = sum(1 for j in queue if j[0] == portal)
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
            out[name] = (False, f'0 results for the probe query in '
                                f'{CANARY_LOCATION if name in WIRED.values() else "its search"}')
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


def merge_alerts(seen: dict[str, dict], alerts: list[dict]) -> int:
    """Add job-alert postings to the scrape's pool; how many were new.

    LinkedIn's search gives a slugged URL and an alert the bare one, so the
    same posting is matched on its LinkedIn id, not its URL."""
    have = {str(r.get("id")) for r in seen.values() if r.get("portal") == "linkedin"}
    added = 0
    for r in alerts:
        jid = str(r.get("id"))
        if r.get("url") and jid not in have and r["url"] not in seen:
            seen[r["url"]] = r
            have.add(jid)
            added += 1
    return added


# What a person's portal did not reach last round, so the next round starts there:
# {portal: {"mode": "tail" or "all", "next": an index into what rotates, "sent": the
# requests it sent, "date": the round}}. "tail" while the board gets through its
# core each round; "all" once it did not, so a board too slow even for its core
# still reaches every request over successive rounds.
# Beside the round summaries, which every session commits, and a dotfile so
# nothing that globs documents/rounds/*.json reads it as a round.
SWEEP_STATE = person.state("documents", "rounds", ".sweep.json")
# This round's plan per person portal: (mode, core requests, rotating length, offset).
PLAN: dict[str, tuple[str, int, int, int]] = {}


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


def _cursor() -> dict:
    try:
        with open(SWEEP_STATE, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cursor(sent_by_skill: dict, today: str) -> None:
    """Where each person portal's tail starts next round, from what this one sent."""
    if not PLAN:
        return
    state = _cursor()
    for skill, (mode, core, rotating, offset) in PLAN.items():
        if skill not in sent_by_skill:
            continue
        sent = sent_by_skill[skill]
        done = sent if mode == "all" else max(0, sent - core)
        state[skill] = {"mode": mode, "next": (offset + done) % rotating if rotating else 0,
                        "sent": sent, "date": today}
    try:
        os.makedirs(os.path.dirname(SWEEP_STATE), exist_ok=True)
        with open(SWEEP_STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
            fh.write("\n")
    except OSError:
        pass


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
    # A person's own portals, the way LinkedIn is searched: every query at its
    # first place as deep as it says (`pages:`, capped by --pages) is the core,
    # sent first in every round. Then the tail: the named employers on page one
    # there, remote postings where the board can filter for them (`remote: true`,
    # sent as `--remote` and a 5th element), every other place two pages. A paced
    # board runs out of its budget long before its tail: on one, 368 requests
    # against room for about 56, so the same tail was dropped round after round
    # and its named employers never ran. Three things fix that. The tail starts
    # where the last round stopped (SWEEP_STATE), so successive rounds cover all
    # of it. A query a broader one covers is not sent (`broadest`). And an employer
    # whose own ATS board a round already reads is not searched for here.
    covered = _covered_by_ats()
    cursor = _cursor()
    PLAN.clear()
    try:
        from company_key import key as _key
    except Exception:  # pragma: no cover
        def _key(x):
            return x
    for skill in contract_portals(on):
        places = portal_locations(skill)
        depth = min(pages, portals.pages(skill))
        qs = broadest(QUERIES)
        core = [(skill, q, places[0], pg) for q in qs for pg in range(1, depth + 1)]
        tail = [(skill, f"{emp} {t}", places[0], 1) for emp in EMPLOYERS
                if _key(emp) not in covered for t in EMPLOYER_QUERIES]
        if portals.takes_remote(skill):
            tail += [(skill, q, None, pg, True) for q in qs for pg in range(1, min(depth, 2) + 1)]
        tail += [(skill, q, loc, pg) for q in qs for loc in places[1:]
                 for pg in range(1, min(depth, 2) + 1)]
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


PARTIAL = "partial_rows.json"


def _write_partial(out: str, seen: dict) -> None:
    """Everything found so far, written over itself: what a killed stage leaves."""
    tmp = os.path.join(out, PARTIAL + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(list(seen.values()), fh)
        os.replace(tmp, os.path.join(out, PARTIAL))
    except OSError:
        pass


def finish(out: str, seen: dict, today: dt.date, jobage: int, n_tasks: int,
           sent: dict, failed: dict, partial: str = "") -> int:
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

    json.dump(kept, open(f"{out}/kept.json", "w"), indent=1)
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
    json.dump(dropped, open(f"{out}/dropped.json", "w"), indent=1)
    json.dump(rows, open(f"{out}/scraped.json", "w"), indent=1)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", type=int, default=None,
                    help=f"default {CLOUD_PAGES} in the cloud, {LOCAL_PAGES} on a person's own "
                         "computer (profile/search.py SCRAPE_PAGES sets their own)")
    ap.add_argument("--jobage", type=int, default=14)
    ap.add_argument("--today", default=None)
    ap.add_argument("--workers", type=int, default=None,
                    help=f"default {CLOUD_WORKERS} in the cloud, {LOCAL_WORKERS} on their own "
                         "computer (SCRAPE_WORKERS)")
    ap.add_argument("--max-requests", dest="max_requests", type=int, default=None,
                    help="the most requests each app portal sends this round (default none "
                         f"in the cloud, {LOCAL_MAX_REQUESTS} on their own computer)")
    ap.add_argument("--budget", type=int, default=POOL_BUDGET,
                    help="seconds the LinkedIn and freehire requests may take, in all")
    ap.add_argument("--log", default=None, help="a file the progress lines are appended to")
    ap.add_argument("--finish", action="store_true",
                    help="no requests: write the scrape's files from what a killed run left "
                         f"in {PARTIAL}, and exit 2")
    ap.add_argument("--skip-canary", action="store_true",
                    help="skip the pre-flight portal probe (offline replays)")
    ap.add_argument("--alerts", default=None,
                    help="postings from the person's job-alert emails (tools/job_alerts.py)")
    a = ap.parse_args()
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
    if not a.skip_canary:
        health = canary(a.jobage, on)
        report, ok = canary_report(health)
        print("portal health:")
        print(report)
        if not ok:
            down = [n for n, (h, _) in health.items() if not h]
            json.dump({"portals_down": down, "detail": {k: v[1] for k, v in health.items()}},
                      open(os.path.join(a.out, "00_portal_health.json"), "w"), indent=1)

    tasks = build_tasks(on, pages)
    if not tasks:
        print("portals: none of the portals this scrape can call is on, so this "
              "round is the employer boards alone (python3 tools/portals.py)")

    seen: dict[str, dict] = {}
    sent: dict[str, int] = {}
    failed: dict[str, list[str]] = {}
    mine: dict[str, list[tuple]] = {}
    lock = threading.Lock()

    def landed(rows_):
        with lock:
            for r in rows_:
                if r.get("url"):
                    seen.setdefault(r["url"], r)

    for task in tasks:
        if task[0] not in ("li", "lir", "fh"):
            mine.setdefault(task[0], []).append(task)
    tallies: dict[str, Tally] = {portals.short(k): Tally(portals.short(k), len(ts))
                                 for k, ts in mine.items()}
    paced = ThreadPoolExecutor(max_workers=max(1, len(mine)))
    sweeps = {paced.submit(sweep, skill, ts, a.jobage, tally=tallies[portals.short(skill)],
                           on_rows=landed): portals.short(skill)
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
    started = time.monotonic()
    done = threading.Event()

    def progress():
        while not done.wait(PROGRESS_SECONDS):
            left = a.budget - (time.monotonic() - started)
            for t in list(tallies.values()):
                _say(t.line(left), a.log)
            with lock:
                _write_partial(a.out, seen)

    ticker = threading.Thread(target=progress, daemon=True)
    ticker.start()
    _, pool_tallies = pool(jobs, workers, budget=a.budget, cap=cap, tallies=tallies,
                           on_rows=landed)
    swept: dict[str, int] = {}
    for f in as_completed(sweeps):
        portal = sweeps[f]
        try:
            rows_, n, errs = f.result()
        except Exception as e:
            rows_, n, errs = [], 1, [f"{type(e).__name__}: {str(e)[:120]}"]
        sent[portal] = n
        swept.update({k: n for k in mine if portals.short(k) == portal})
        if errs:
            failed.setdefault(portal, []).extend(errs)
        landed(rows_)
    paced.shutdown()
    done.set()
    for name, t in pool_tallies.items():
        if name in sent:
            continue
        sent[name] = t.sent
        if t.failed:
            failed.setdefault(name, []).extend(t.failed)
    for t in tallies.values():
        _say(t.line(), a.log)
        if t.stopped and t.name in ("linkedin", "freehire"):
            _say(f"portals: {t.name} stopped, {t.stopped}; {t.total - t.sent} of {t.total} "
                 "requests not sent", a.log)
    save_cursor(swept, today.isoformat())
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
    try:
        from ats_boards import fetch_all as _ats_fetch
        ats_notes: dict[str, str] = {}
        ats_rows, ats_quiet = _ats_fetch(notes=ats_notes, today=today)
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
    except Exception as e:            # a new source must never break a round
        print(f"ats boards: skipped ({type(e).__name__}: {e})", file=sys.stderr)

    # The person's job alerts, already filled from each posting page by
    # tools/job_alerts.py. A posting the search also found is kept once: the
    # same LinkedIn id under a slugged URL is the same posting.
    if a.alerts:
        try:
            alert_rows = json.load(open(a.alerts, encoding="utf-8"))
        except (OSError, ValueError) as e:
            alert_rows = []
            print(f"job alerts: skipped ({type(e).__name__}: {e})", file=sys.stderr)
        alert_rows = [r for r in alert_rows if isinstance(r, dict)] if isinstance(alert_rows, list) else []
        added = merge_alerts(seen, alert_rows)
        print(f"job alerts: {added} added, {len(alert_rows) - added} already found by the search")

    cut = [t for t in pool_tallies.values() if t.stopped and t.name in ("linkedin", "freehire")]
    partial = ("; ".join(f"{t.name} stopped ({t.stopped}) with {t.total - t.sent} of its "
                         f"{t.total} requests unsent" for t in cut))
    return finish(a.out, seen, today, a.jobage, len(tasks), sent, failed, partial=partial)

if __name__ == "__main__":
    raise SystemExit(main())
