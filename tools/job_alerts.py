#!/usr/bin/env python3
"""Postings from the LinkedIn job alerts a person already gets, for the next round.

LinkedIn's guest search, which every round runs, is a keyword search. A LinkedIn
job alert is LinkedIn's own match for the person, from their profile and saved
searches, and it carries roles a keyword search can rank out of reach. Those
emails sat in the person's inbox and no round read them.

Python cannot reach the inbox; the session can, through the Gmail connector, and
only when the person has asked for it (profile/search.py `JOB_ALERT_QUERY`). So
the work is split:

1. The session runs that Gmail query, reads each message's full body, and writes
   the messages to a JSON file:
       [{"id": "<message id>", "date": "YYYY-MM-DD", "body": "<html or text>"}, ...]
2. This takes the LinkedIn job ids out of every link in them
   (`linkedin.com/jobs/view/<id>`, `/comm/jobs/view/<id>`, with or without a slug)
   and fills each posting from LinkedIn's own posting page with the
   linkedin-search CLI: title, employer, location and the whole body. Nothing but
   the id is read from the email, so a redesigned email cannot put a wrong title
   on a posting.
3. `run_round.py --alerts <the output>` adds them to the round before the free
   filters, so they are screened, scored and throttled like every other posting.

A posting LinkedIn shows as closed is dropped, and the count says so. The
email's date stands in for the posting date, which the posting page does not
give; an alert goes out within a day or two of the posting.

If the person has switched linkedin-search off, nothing is fetched: reading
their alerts is not a reason to send LinkedIn the requests they turned off.

    python3 tools/job_alerts.py --query --days 8     # the Gmail query, or exit 1: alerts are off
    python3 tools/job_alerts.py messages.json --out alerts.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import portals  # noqa: E402

SKILL = "linkedin-search"
JOB_LINK = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[\w%.-]*?-)?(\d{6,})(?![\d])", re.I)
BODY_CAP = 20_000
# Few and gentle: an alert batch is tens of postings, not thousands.
WORKERS = 3


def job_ids(body: str) -> list[str]:
    """The LinkedIn job ids linked from one message, in order, once each."""
    out: list[str] = []
    for m in JOB_LINK.finditer(body or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def collect(messages: list[dict]) -> dict[str, str]:
    """{job id: the date of the earliest alert that carried it}."""
    found: dict[str, str] = {}
    for msg in messages:
        date = str(msg.get("date") or "")[:10]
        for jid in job_ids(str(msg.get("body") or "")):
            if jid not in found or (date and date < found[jid]):
                found[jid] = date
    return found


def detail(jid: str, timeout: int = 60) -> tuple[dict | None, str | None]:
    """LinkedIn's posting page for one id, through the linkedin-search CLI."""
    try:
        cli = portals.cli(SKILL)
        with tempfile.TemporaryFile("w+", encoding="utf-8") as fh:   # a file, not a pipe: see scrape_wide.run
            p = subprocess.run(["node", "--no-warnings", cli, "detail", jid, "--format", "json"],
                               stdout=fh, stderr=subprocess.PIPE, text=True, timeout=timeout,
                               env=dict(os.environ, NODE_USE_ENV_PROXY="1"))
            fh.seek(0)
            raw = fh.read()
        if p.returncode != 0 or not raw.strip():
            err = (p.stderr or "").strip().splitlines()
            return None, f"detail exit {p.returncode}: {err[-1][:120] if err else 'no output'}"
        return json.loads(raw), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def row(jid: str, date: str, d: dict) -> dict:
    return {"id": jid, "title": d.get("title"), "company": d.get("company"),
            "url": f"https://www.linkedin.com/jobs/view/{jid}",
            "location": d.get("location"), "date": date, "portal": "linkedin",
            "desc": (d.get("description") or "")[:BODY_CAP] or None, "source": "job alert"}


def fill(found: dict[str, str], fetch=detail, workers: int = WORKERS,
         pause: float = 0.5) -> tuple[list[dict], dict[str, str]]:
    """(rows, {id: why it was left out}) for every id found."""
    rows: list[dict] = []
    left: dict[str, str] = {}

    def one(item):
        jid, date = item
        if pause:
            time.sleep(pause)
        return jid, date, *fetch(jid)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for jid, date, d, err in ex.map(one, sorted(found.items())):
            if err or not d:
                left[jid] = err or "no detail"
            elif d.get("isActive") is False:
                left[jid] = "closed: LinkedIn shows it no longer accepting applications"
            elif not d.get("title") or d.get("title") == "(untitled)":
                left[jid] = "the posting page gave no title"
            else:
                rows.append(row(jid, date, d))
    return rows, left


def query(days: int) -> str:
    """The Gmail search for the person's alerts over the last `days`, or "" when
    they have not asked for alerts to be read (profile/search.py JOB_ALERT_QUERY)."""
    try:
        base = str(getattr(person.module("search"), "JOB_ALERT_QUERY", "") or "").strip()
    except person.NoProfile:
        return ""
    return f"{base} newer_than:{days}d" if base else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("messages", nargs="?",
                    help="JSON list of {id, date, body} the session read from the inbox")
    ap.add_argument("--out")
    ap.add_argument("--query", action="store_true",
                    help="print the Gmail search for the person's alerts; exit 1 if they are off")
    ap.add_argument("--days", type=int, default=8)
    a = ap.parse_args(argv)
    if a.query:
        q = query(a.days)
        print(q or "job alerts are off: profile/search.py sets no JOB_ALERT_QUERY")
        return 0 if q else 1
    if not (a.messages and a.out):
        ap.error("give the messages file and --out, or --query")
    with open(a.messages, encoding="utf-8") as fh:
        messages = json.load(fh)
    found = collect(messages if isinstance(messages, list) else [])
    if not portals.is_enabled(SKILL):
        print(f"job alerts: {len(found)} posting(s) in {len(messages)} message(s), none fetched: "
              f"{SKILL} is off (python3 tools/portals.py)")
        rows, left = [], {}
    else:
        rows, left = fill(found)
        print(f"job alerts: {len(found)} posting(s) in {len(messages)} message(s); "
              f"{len(rows)} added, {len(left)} left out")
        for jid, why in sorted(left.items())[:10]:
            print(f"  {jid}: {why}")
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
