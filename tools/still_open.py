#!/usr/bin/env python3
"""Are the drafted-but-unsent applications still open? Ask the posting, not the calendar.

    python3 tools/still_open.py                 # every `drafted` row with a source URL
    python3 tools/still_open.py --status applied --status drafted
    python3 tools/still_open.py --json

A drafted application is documents nobody has sent, and the only clock on it is
the employer's. Rows can sit at `drafted` for weeks; a records audit could only
guess from their age which were worth sending, and one could have passed a
deadline stated in its own posting. The posting page says whether it is still
taking applications, so this asks it.

A page that cannot be fetched, or that fetches without the closure line, reads
as `unknown` or `open`, never as closed: a false "closed" throws away a live
application, and a false "open" costs one look. Closure is only claimed on the
posting's own top card phrase, because the same words appear in the "similar
jobs" rail of a live posting.

It asks the way every other fetcher in the app asks: as itself, never as a
browser; nothing to a portal the person has switched off (tools/portals.py);
nothing a site's robots.txt disallows (tools/robots_check.py); and no faster
than a portal's declared crawl-delay. Where one of those says no, the verdict is
`unknown`, with the reason. It used to send a browser's user agent to every
page, LinkedIn included when the person had switched LinkedIn off.

Read-only. It changes no file; `/outcome` or the tracker edit is the person's.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
import portals  # noqa: E402
import robots_check  # noqa: E402

TRACKER = person.state("job_search_tracker.csv")
# The app's own name, as tools/ats_boards.py sends it.
UA = "last-job-search/1.0 (personal job search; contact via GitHub)"
# The hosts of the app's two portals, whose SKILL.md names no `url:`; a person's
# portal names its own.
APP_HOSTS = {"linkedin-search": "linkedin.com", "freehire-search": "freehire.me"}

# The phrases a closed posting prints about itself. LinkedIn's is in the top
# card ("No longer accepting applications"); ATS pages say the job is gone.
CLOSED = re.compile(
    r"no longer accepting applications|this job is no longer available|"
    r"job (?:posting )?has expired|position has been filled|"
    r"this (?:job|position|posting) (?:is )?no longer (?:open|active|available)", re.I)
# Where the phrase has to sit to be about THIS posting and not a neighbour.
TOP_CARD = re.compile(r"top-card|topcard|job-header|posting-header|jobs-unified-top-card", re.I)


def verdict(html: str) -> str:
    """open, closed, or unknown, from a fetched posting page."""
    if not html or len(html) < 2000:
        return "unknown"
    for m in CLOSED.finditer(html):
        window = html[max(0, m.start() - 1500):m.end() + 500]
        if TOP_CARD.search(window):
            return "closed"
    # An ATS page with no top-card markup: a closure phrase in the first part of
    # the document, before any list of other jobs, is about this one.
    head = html[: max(4000, len(html) // 5)]
    if CLOSED.search(head) and not re.search(r"similar jobs|more jobs|other jobs", head, re.I):
        return "closed"
    return "open"


def _host(url: str) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def portal_of(url: str) -> str | None:
    """The installed portal a posting URL belongs to, or None."""
    host = _host(url)
    for name in portals.defaults():
        base = APP_HOSTS.get(name) or _host(portals.url(name))
        if base and host and (host == base or host.endswith("." + base)):
            return name
    return None


def blocked(url: str) -> str:
    """Why this page may not be asked for, or "" when it may."""
    name = portal_of(url)
    if name and not portals.is_enabled(name):
        return f"{name} is switched off (python3 tools/portals.py), so nothing is sent to it"
    code, why = robots_check.gate(url)
    return "" if code == 0 else f"robots.txt: {why}"


_LAST: dict[str, float] = {}


def pace(url: str, sleep=time.sleep, clock=time.monotonic) -> None:
    """Wait out a portal's declared crawl-delay since the last request to its host."""
    name = portal_of(url)
    delay = portals.crawl_delay(name) if name else 0.0
    host = _host(url)
    wait = _LAST.get(host, -1e9) + delay - clock()
    if delay and wait > 0:
        sleep(wait)
    _LAST[host] = clock()


def fetch(url: str, timeout: int = 20) -> str:
    """The page, or "" when it could not be had. The gates are the caller's: `blocked`."""
    pace(url)
    try:
        out = subprocess.run(["curl", "-sSL", "--max-time", str(timeout), "-A", UA, "--", url],
                             capture_output=True, text=True, timeout=timeout + 10,
                             encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout if out.returncode == 0 else ""


def check(statuses: set[str], path: str = TRACKER) -> list[dict]:
    import csv_store
    rows = [r for r in csv_store.dict_rows(path) if (r.get("status") or "").strip() in statuses]
    out = []
    for r in rows:
        url = (r.get("source") or "").strip()
        why = blocked(url) if url.startswith("http") else ""
        if not url.startswith("http"):
            v = "no source url"
        elif why:
            v = "unknown"
        else:
            v = verdict(fetch(url))
        out.append({"company": r.get("company"), "role": r.get("role"), "status": r.get("status"),
                    "date": r.get("date"), "deadline": r.get("deadline") or "", "verdict": v,
                    "url": url, "why": why})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--status", action="append", help="tracker status to check (default: drafted)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(TRACKER):
        print("still_open: no job_search_tracker.csv yet, so there is nothing to check")
        return 0
    got = check(set(a.status or ["drafted"]))
    if a.json:
        print(json.dumps(got, indent=1))
        return 0
    for g in got:
        print(f"{g['verdict']:<14} {g['date']}  {g['company']} | {g['role']}"
              + (f"  ({g['why']})" if g.get("why") else ""))
    closed = [g for g in got if g["verdict"] == "closed"]
    if closed:
        print(f"\n{len(closed)} closed: close them out with /outcome, or send nothing there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
