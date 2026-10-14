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
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# Resolved on first use, not at import: see the note on `portal_cli`.
CLI = {"linkedin": functools.partial(portal_cli, "linkedin-search", "LINKEDIN_CLI"),
       "freehire": functools.partial(portal_cli, "freehire-search", "FREEHIRE_CLI")}

# Requirements sit at the END of a posting. A 9,000-character cap cut the
# requirements off bodies in a round, which is exactly the text the screen and
# the scorers read.
BODY_CAP = 20_000


def fetch(job: dict, timeout: int = 60) -> dict:
    """Return the job with `desc` filled in where it was missing, or `hydrate_error` set."""
    if (job.get("desc") or "").strip():
        return job
    portal = job.get("portal") or ""
    resolve = CLI.get(portal)
    if not resolve:
        return {**job, "hydrate_error": f"no detail CLI for portal {portal!r}"}
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
