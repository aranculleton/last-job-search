#!/usr/bin/env python3
"""Fill in posting descriptions before any model or free screen reads them.

## Why this exists

`scrape_wide.py` gets a full description inline from freehire but only a title
and URL from LinkedIn, whose search endpoint does not return the body. That
shipped a round where **most postings reached the model with an empty
description**. Every one of them came back "Description unavailable -
insufficient information for knockout determination":

  - the free text screen could not cut on a stated fact, so nothing was
    filtered for free
  - the knockout stage could not knock out, so ineligible roles survived
  - the extractor returned nulls, so the mechanical screen had nothing to
    screen on
  - `fit.py` scored on the title alone for those rows

The failure is quiet: every stage still "succeeds" and returns plausible
records, so the round just gets worse without anything erroring. This tool
closes the gap, and `--require` makes the gap loud instead of quiet. A row
whose fetch fails keeps its place and carries `hydrate_error` saying why, so a
thin body downstream can be told from a genuinely short posting.

Hydration belongs AFTER the free filters (prefilter, dedupe, throttle) and
BEFORE ranking, screening and extraction: it costs one HTTP call per posting
and no model tokens, so it should run on everything that survives for free,
and nothing that does not.

Usage:
    python3 tools/hydrate.py candidates.json --out hydrated.json
    python3 tools/hydrate.py candidates.json --out hydrated.json --require 0.9
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portals  # noqa: E402

# --------------------------------------------------------------- portal CLIs
#
# tools/portals.py finds or builds each portal's CLI (one resolver for this file
# and scrape_wide.py), says which are on, and maps a posting's `portal` field
# back to its folder. Any portal that follows the contract can be hydrated: the
# app's two, and every portal a person built with /add-portal.
portal_cli = portals.cli
# Resolved on first use, not at import: see tools/portals.py `cli`.
CLI = {"linkedin": functools.partial(portal_cli, "linkedin-search", "LINKEDIN_CLI"),
       "freehire": functools.partial(portal_cli, "freehire-search", "FREEHIRE_CLI")}
# A portal that is off is sent nothing, a detail fetch included
# (tools/portals.py).
SKILL = {"linkedin": "linkedin-search", "freehire": "freehire-search"}

# One clock per paced portal: a board whose robots.txt asks for five seconds
# between requests gets five seconds between detail fetches too, whatever the
# number of workers.
#
# And a budget: at five seconds a fetch, 400 postings from one board is over
# half an hour, past this stage's time limit in run_round.py, and a stage that
# times out loses the whole round. Past the budget a posting keeps its search
# snippet and says why.
_PACE: dict[str, tuple[threading.Lock, list[float]]] = {}
_PACE_GUARD = threading.Lock()
PACE_BUDGET = 15 * 60


def pace(skill: str, sleep=time.sleep, clock=time.monotonic) -> bool:
    """Wait this portal's turn. False once its paced fetches have had their budget."""
    delay = portals.crawl_delay(skill)
    if not delay:
        return True
    with _PACE_GUARD:
        lock, times = _PACE.setdefault(skill, (threading.Lock(), [0.0, 0.0]))
    with lock:
        now = clock()
        if not times[1]:
            times[1] = now
        if now - times[1] > PACE_BUDGET:
            return False
        wait = times[0] + delay - now
        if wait > 0:
            sleep(wait)
        times[0] = clock()
    return True


# Requirements sit at the END of a posting. A 9,000-character cap cut the
# requirements off bodies in a round, which is exactly the text the screen and
# the scorers read.
BODY_CAP = 20_000


def fetch(job: dict, timeout: int = 60) -> dict:
    """Return the job with `desc` filled in where it was missing, or `hydrate_error` set.

    A posting from a person's portal may carry the board's search `snippet`.
    When the full body cannot be had, the snippet stands in for it, and
    `hydrate_error` still says why, so a thin body can be told from a short
    posting.
    """
    if (job.get("desc") or "").strip():
        return job
    out = _fetch(job, timeout)
    if not (out.get("desc") or "").strip() and (job.get("snippet") or "").strip():
        out = {**out, "desc": job["snippet"][:BODY_CAP]}
    return out


def _fetch(job: dict, timeout: int) -> dict:
    portal = job.get("portal") or ""
    skill = SKILL.get(portal) or portals.skill_of(portal)
    resolve = CLI.get(portal) or (skill and portals.has_cli(skill)
                                  and functools.partial(portal_cli, skill))
    if not resolve:
        return {**job, "hydrate_error": f"no detail CLI for portal {portal!r}"}
    if not portals.is_enabled(skill):
        return {**job, "hydrate_error": f"{skill} is off (python3 tools/portals.py)"}
    if portal not in CLI and not portals.has_detail(skill):
        return {**job, "hydrate_error": f"{skill} takes no detail fetch (detail: false in "
                                        f"its SKILL.md); the search text is the body"}
    try:
        cli = resolve()
    except (OSError, RuntimeError) as e:
        # Said "no detail CLI for portal 'linkedin'" whatever the reason, which
        # reads as an unsupported portal rather than a missing build. Every
        # posting in a round came back with that line and nothing said the path
        # it looked at belonged to a scratchpad from another session.
        return {**job, "hydrate_error": f"{portal} CLI unavailable: {e}"}
    ident = job.get("id") or job.get("url")
    try:
        if not pace(skill):
            return {**job, "hydrate_error": f"{skill}'s crawl-delay used its "
                                            f"{PACE_BUDGET // 60}-minute budget in this round; not fetched"}
        # A FILE, not a pipe. Node writes to stdout asynchronously when it is a
        # pipe and synchronously when it is a regular file, so a CLI that calls
        # process.exit() after writing loses whatever has not drained. Under
        # this module's ten workers nothing drains, and a posting body arrives
        # cut at 64 KiB mid-string with exit 0. `tools/scrape_wide.py` carries
        # the full account: it was throwing away three quarters of one portal.
        with tempfile.TemporaryFile("w+", encoding="utf-8") as fh:
            p = subprocess.run(
                ["node", "--no-warnings", cli, "detail", str(ident), "--format", "json"],
                stdout=fh, stderr=subprocess.PIPE, text=True, timeout=timeout,
                env=dict(os.environ, NODE_USE_ENV_PROXY="1"))
            fh.seek(0)
            raw = fh.read()
        if p.returncode != 0 or not raw.strip():
            err = (p.stderr or "").strip().splitlines()
            return {**job, "hydrate_error": f"detail exit {p.returncode}: {err[-1][:160] if err else 'no output'}"}
        d = json.loads(raw)
        body = d.get("description") or d.get("descriptionText") or ""
        if not body.strip():
            return {**job, "hydrate_error": "detail returned an empty description"}
        return {**job, "desc": body[:BODY_CAP]}
    except Exception as e:  # timeout, bad JSON, missing node: all recorded, none fatal
        return {**job, "hydrate_error": f"{type(e).__name__}: {str(e)[:160]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--require", type=float, default=None,
                    help="fail if the fraction with a description is below this")
    a = ap.parse_args()

    data = json.load(open(a.infile))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)
    before = sum(1 for j in jobs if (j.get("desc") or "").strip())
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(fetch, j) for j in jobs]
        for f in as_completed(futs):
            try:
                out.append(f.result())
            except Exception as e:
                print(f"worker error: {e}", file=sys.stderr)
    # Keep anything a worker dropped, so hydration can never lose a posting.
    got = {j.get("url") for j in out}
    out += [j for j in jobs if j.get("url") not in got]

    after = sum(1 for j in out if (j.get("desc") or "").strip())
    errors = [j for j in out if j.get("hydrate_error")]
    json.dump(out, open(a.out, "w"), indent=1)
    frac = after / len(out) if out else 0.0
    print(f"{len(out)} postings: {before} had a description, {after} now do "
          f"({frac:.0%}); {len(errors)} fetch errors", file=sys.stderr)
    if errors:
        from collections import Counter
        for reason, n in Counter(j["hydrate_error"][:60] for j in errors).most_common(5):
            print(f"  {n:4d}  {reason}", file=sys.stderr)
    if a.require is not None and frac < a.require:
        print(f"FAIL: only {frac:.0%} have a description, below the required "
              f"{a.require:.0%}. Every posting without one reaches the model "
              f"blind and cannot be screened, knocked out or extracted.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
