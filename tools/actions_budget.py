#!/usr/bin/env python3
"""What this repo's CI has actually cost, from the runs themselves.

## Why this exists

A 2,000-minute Actions allowance can run out with no warning:
nothing in the repo could have told you it was coming. The billing page shows a
percentage after the fact; what nobody had was the per-run number, and that is
the one that explains it.

**GitHub bills per JOB, rounded UP to the nearest minute.** A job that runs for
six seconds bills a full minute. That single rule is why an 18-job workflow
doing four minutes of work cost 22, and why the cost was invisible in a file
where every job looks cheap.

This reads the workflow runs through the ordinary API, with no billing scope
and no personal token, and applies that rule itself. It is an estimate of
billed minutes, not a billing statement, and it will run slightly high where a
job was cancelled or skipped.

Usage:
    python3 tools/actions_budget.py                 this billing cycle
    python3 tools/actions_budget.py --days 7        the last week
    python3 tools/actions_budget.py --budget 5      minutes left in a $5 budget

Needs GH_TOKEN or GITHUB_TOKEN in the environment (a plain read token is
enough). Without one it explains that and exits 2 rather than guessing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
# Standard Ubuntu 2-core runner, the only kind this workflow uses.
USD_PER_MINUTE = 0.008
INCLUDED_MINUTES = 2000


def _repo() -> str:
    """owner/name from the git remote, so this works in any fork."""
    import subprocess
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True,
                             encoding="utf-8", errors="replace").stdout.strip()
    except Exception:
        return ""
    url = url.removesuffix(".git")
    if url.startswith("git@"):
        url = url.split(":", 1)[-1]
    return "/".join(url.split("/")[-2:])


def _get(path: str, token: str):
    req = urllib.request.Request(
        API + path,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "last-job-search/actions_budget"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        return json.loads(fh.read().decode("utf-8", "replace"))


def cycle_start(today: dt.date) -> dt.date:
    """GitHub's allowance resets on the 1st."""
    return today.replace(day=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=None,
                    help="the last N days INCLUDING today, instead of the cycle")
    ap.add_argument("--budget", type=float, default=None,
                    help="dollar budget set on top of the included minutes")
    ap.add_argument("--repo", default=None, help="owner/name (default: git remote)")
    a = ap.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("actions_budget: set GH_TOKEN or GITHUB_TOKEN (a read token is "
              "enough; no billing scope needed).", file=sys.stderr)
        return 2
    repo = a.repo or _repo()
    if not repo:
        print("actions_budget: could not read owner/name from the git remote; "
              "pass --repo owner/name", file=sys.stderr)
        return 2

    today = dt.date.today()
    # `--days 1` means TODAY, not today and yesterday. The first version
    # subtracted a full day from today and so reported two days as one,
    # which produced "44 runs today" when today was 22 and the real spike had
    # been five days earlier. A tool that exists to give you the number is
    # worse than useless when the number is wrong.
    since = (today - dt.timedelta(days=a.days - 1)) if a.days else cycle_start(today)
    label = (f"the last {a.days} day{'s' if a.days > 1 else ''} (from {since})"
             if a.days else f"this billing cycle (from {since})")

    runs, page = [], 1
    while page <= 10:
        try:
            batch = _get(f"/repos/{repo}/actions/runs?per_page=100&page={page}", token)
        except urllib.error.HTTPError as e:
            print(f"actions_budget: {e.code} from the API for {repo}", file=sys.stderr)
            return 2
        got = batch.get("workflow_runs") or []
        if not got:
            break
        runs += got
        oldest = got[-1].get("created_at", "")[:10]
        if oldest and dt.date.fromisoformat(oldest) < since:
            break
        page += 1

    runs = [r for r in runs
            if r.get("created_at") and dt.date.fromisoformat(r["created_at"][:10]) >= since]
    if not runs:
        print(f"actions_budget: no runs in {label}")
        return 0

    total, by_wf, counted = 0, {}, 0
    by_day: dict[str, list[int]] = {}
    by_event: dict[str, int] = {}
    by_branch: dict[str, int] = {}
    for r in runs:
        try:
            jobs = (_get(f"/repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100",
                         token).get("jobs") or [])
        except urllib.error.HTTPError:
            continue
        mins = 0
        for j in jobs:
            s, c = j.get("started_at"), j.get("completed_at")
            if not (s and c):
                continue
            secs = (dt.datetime.fromisoformat(c.replace("Z", "+00:00"))
                    - dt.datetime.fromisoformat(s.replace("Z", "+00:00"))).total_seconds()
            # The rule that explains everything: per job, rounded UP.
            mins += max(1, math.ceil(secs / 60))
        total += mins
        counted += 1
        by_wf[r.get("name", "?")] = by_wf.get(r.get("name", "?"), 0) + mins
        day = r["created_at"][:10]
        acc = by_day.setdefault(day, [0, 0])
        acc[0] += 1
        acc[1] += mins
        ev = r.get("event", "?")
        by_event[ev] = by_event.get(ev, 0) + mins
        br = r.get("head_branch") or "?"
        by_branch[br] = by_branch.get(br, 0) + mins

    print(f"\nactions_budget: {repo}, {label}\n")
    print(f"  {counted} runs, about {total} billed minutes "
          f"(${total * USD_PER_MINUTE:.2f})")
    if counted:
        print(f"  {total / counted:.1f} billed minutes per run on average")
    for wf, m in sorted(by_wf.items(), key=lambda x: -x[1]):
        print(f"    {m:6d} min  {wf}")

    # The per-day view is the one that explains a cap. A monthly total says
    # you spent it; this says which three days did, and whether it is a
    # pattern or one bad afternoon. One busy day can take half the allowance,
    # and no average would show that.
    if len(by_day) > 1:
        print(f"\n  {'date':12} {'runs':>5} {'billed':>7} {'min/run':>8}")
        for day in sorted(by_day):
            n, m = by_day[day]
            flag = "   <- " + f"{m * 100 // INCLUDED_MINUTES}% of the allowance" \
                if m * 10 >= INCLUDED_MINUTES else ""
            print(f"  {day:12} {n:5d} {m:7d} {m / n:8.1f}{flag}")

    if by_event:
        print("\n  by event:   " + "   ".join(
            f"{m} min {e}" for e, m in sorted(by_event.items(), key=lambda x: -x[1])))
    if by_branch:
        top = sorted(by_branch.items(), key=lambda x: -x[1])[:4]
        print("  by branch:  " + "   ".join(f"{m} min {b}" for b, m in top))

    if not a.days:
        left = INCLUDED_MINUTES - total
        print(f"\n  included allowance: {INCLUDED_MINUTES} min, "
              f"{'about %d left' % left if left > 0 else 'SPENT, %d over' % -left}")
        if a.budget is not None:
            paid = max(0, -left)
            budget_min = int(a.budget / USD_PER_MINUTE)
            print(f"  ${a.budget:.2f} budget: {budget_min} paid minutes, "
                  f"about {budget_min - paid} left "
                  f"({(budget_min - paid) / (total / counted):.0f} more runs "
                  f"at the current average)" if counted else "")
    print("\n  GitHub bills per JOB, rounded up to the nearest minute. A job\n"
          "  that runs six seconds bills one. Fewer, fatter jobs are cheaper\n"
          "  than many thin ones doing the same work.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
