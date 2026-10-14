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
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from prefilter import annotate, age_days  # noqa: E402

# --------------------------------------------------------------- portal CLIs
#
# These pointed at one build in one session's scratchpad directory, named with
# that session's own UUID. A scratchpad does not survive the container, so on
# every fresh checkout the scrape resolved both paths to files that were not
# there and produced nothing, with no error saying why.
#
# The sources are in the repo and carry no runtime dependencies. This finds a
# build if one exists, makes one if bun is there, and says what to run if
# neither.
CLI_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".agents", "skills")


@functools.lru_cache(maxsize=None)
def portal_cli(skill: str, env_var: str) -> str:
    """The runnable CLI for a portal skill, built on demand.

    Returns a path to a bundled `.mjs`. Raises with the build command when the
    sources are present but nothing can build them, because a scrape that
    quietly returns nothing is the failure this whole module exists to avoid.
    """
    override = os.environ.get(env_var, "").strip()
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError("%s points at %s, which does not exist"
                                    % (env_var, override))
        return override
    dist = os.path.join(CLI_ROOT, skill, "cli", "dist", "cli.mjs")
    if os.path.exists(dist):
        return dist
    src = os.path.join(CLI_ROOT, skill, "cli", "src", "cli.ts")
    if not os.path.exists(src):
        raise FileNotFoundError(
            "no CLI for %s: neither a build nor %s. Is .agents/skills/%s present?"
            % (skill, src, skill))
    if not shutil.which("bun"):
        raise RuntimeError(
            "%s needs building and bun is not installed. Install bun, or build "
            "it elsewhere and point %s at the result." % (skill, env_var))
    os.makedirs(os.path.dirname(dist), exist_ok=True)
    build = subprocess.run(["bun", "build", src, "--target", "node",
                            "--outfile", dist],
                           capture_output=True, text=True)
    if build.returncode or not os.path.exists(dist):
        raise RuntimeError("bun build failed for %s:\n%s"
                           % (skill, (build.stderr or build.stdout)[:800]))
    return dist
# Resolved on first use, not at import. A build failure should stop a scrape,
# not stop anything that merely imports this module.
LINKEDIN = functools.partial(portal_cli, "linkedin-search", "LINKEDIN_CLI")
FREEHIRE = functools.partial(portal_cli, "freehire-search", "FREEHIRE_CLI")

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
CANARY_QUERY = "data"
CANARY_LOCATION = getattr(_S, "CANARY_LOCATION", LOCATIONS[-1] if LOCATIONS else "")
# A generous age window, so the probe is not measuring how recently anyone
# posted. Wider than any real round would use.
CANARY_JOBAGE = 30


class PortalDown(RuntimeError):
    """A portal answered, without error, and returned nothing at all."""


def canary(jobage: int = CANARY_JOBAGE) -> dict[str, tuple[bool, str]]:
    """One broad probe per enabled portal. {portal: (healthy, detail)}."""
    out: dict[str, tuple[bool, str]] = {}
    probes = (
        ("linkedin", lambda: linkedin(CANARY_QUERY, CANARY_LOCATION, 1, jobage)),
        ("freehire", lambda: freehire(CANARY_QUERY, 1, jobage)),
    )
    for name, fn in probes:
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
                                f'{CANARY_LOCATION} over {jobage} days')
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

    # Two broad probes, before ~3,300 requests. A portal that has gone quiet is
    # reported as broken here rather than as a thin market three widenings
    # later. It does not abort the round: the other portal's results are still
    # worth having, and a round that says so beats a round that stops.
    if not a.skip_canary:
        health = canary(a.jobage)
        report, ok = canary_report(health)
        print("portal health:")
        print(report)
        if not ok:
            down = [n for n, (h, _) in health.items() if not h]
            json.dump({"portals_down": down, "detail": {k: v[1] for k, v in health.items()}},
                      open(os.path.join(a.out, "00_portal_health.json"), "w"), indent=1)

    tasks = []
    # LinkedIn: every query against the home city deep, the rest shallow.
    for q in QUERIES:
        for loc in LOCATIONS:
            depth = a.pages if loc.startswith(DEEP) else 2
            for pg in range(1, depth + 1):
                tasks.append(("li", q, loc, pg))
    for q in QUERIES:
        for loc in REMOTE_LOCATIONS:
            for pg in range(1, 3):
                tasks.append(("lir", q, loc, pg))
    for q in QUERIES:
        for pg in range(1, a.pages + 1):
            tasks.append(("fh", q, None, pg))
    # The named-employer pass. Shallow, because a company search that needs
    # five pages is not finding that company, it is finding the query words.
    for emp in EMPLOYERS:
        for t in EMPLOYER_QUERIES:
            q = f"{emp} {t}"
            for loc in EMPLOYER_LOCATIONS:
                tasks.append(("li", q, loc, 1))
            for loc in EMPLOYER_REMOTE:
                tasks.append(("lir", q, loc, 1))
            tasks.append(("fh", q, None, 1))

    seen: dict[str, dict] = {}
    sent: dict[str, int] = {}
    failed: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {}
        for kind, q, loc, pg in tasks:
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
