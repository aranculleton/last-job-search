#!/usr/bin/env python3
"""One command from portals to a ranked shortlist.

    python3 tools/run_round.py --out rounds/r1 [--pages 5] [--jobage 14]
    python3 tools/run_round.py --out rounds/r2 --from-scraped rounds/r1/00_scrape/kept.json

Runs every free stage in order and stops at the shortlist, which is where a
person decides. Nothing here spends model tokens. The stages and why each one
exists are in .claude/skills/job-scraper/SKILL.md and 11-cost-model.md; this
file just makes the order impossible to get wrong, because it was got wrong:
one round ranked 70 postings that had never been hydrated, another wrote a
one-row shortlist because --top truncated the --out file upstream, and the
first version of this file handed scrape_wide's output DIRECTORY to hydrate
as if it were a file and prefilter's dict to text_screen as if it were a list.

  scrape_wide   every portal that is on, paginated, the profile's locations, remote
                locations and title queries (search.py SCRAPE_*),
                plus the employer boards in ats_boards.py (Greenhouse, Lever,
                Ashby, Workday)
                -> 00_scrape/kept.json (past the scraper's own prefilter)
  prefilter     hard gates: age, location, language, junior/senior titles, plus
                the cross-run gate (--seen): anything throttle.ruled_out() would
                drop at the end is dropped here, before hydrate pays for it
  hydrate       fetch every surviving body; a posting with no text cannot be screened
  text_screen   stated-fact knockouts (10-triage-blockers.md); flags, never cuts silently;
                its cuts are recorded in seen_jobs.json so no later round fetches them
  opportunity   how good is the job (comp signals, employer, seniority band)
  fit           would they call back (title band, family, stack, years, location)
  throttle      company throttle, one role per employer, cross-run dedupe (the
                last of which prefilter has usually already applied)

Every intermediate file is kept in --out so a stage can be re-run alone, and
every one of them is a JSON list.
"""
import argparse, datetime, json, os, shutil, subprocess, sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "tools")
sys.path.insert(0, T)
import person  # noqa: E402

STAGES = ("01_prefiltered", "02_hydrated", "03_screened", "04_opportunity",
          "05_ranked", "06_shortlist")


# A whole-round ceiling, and a per-stage one.
#
# Not one of the seven stages was given a timeout. A portal CLI that hangs on a
# socket, or a fetch that never returns, hangs the round for as long as the
# container lives, and these run in ephemeral cloud containers: the session is
# reclaimed, the ~55MB of stage files are deleted by design, and the whole
# search is lost with nothing written down. Nothing said what happened.
#
# The scrape is allowed the most because it is thousands of requests; the
# stages after it are reading files that already exist. Every stage also gets
# whatever is left of the round budget, whichever is smaller, so a slow-but-not-
# hung pipeline cannot spend the ceiling one stage at a time.
ROUND_BUDGET_SEC = 60 * 60
STAGE_BUDGET_SEC = {
    "scrape_wide.py": 45 * 60,
    "hydrate.py": 30 * 60,
}
DEFAULT_STAGE_SEC = 10 * 60


def _stage_budget(cmd, deadline):
    """Seconds this stage may take: its own budget, capped by what is left."""
    name = os.path.basename(cmd[1]) if len(cmd) > 1 else ""
    own = STAGE_BUDGET_SEC.get(name, DEFAULT_STAGE_SEC)
    if deadline is None:
        return own
    return max(1, min(own, int(deadline - time.monotonic())))


def run(cmd, log, deadline=None):
    print("+", " ".join(cmd), flush=True)
    budget = _stage_budget(cmd, deadline)
    try:
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                           timeout=budget)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        err = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", "replace")
        log.write("\n$ " + " ".join(cmd) + "\n" + out + err
                  + f"\n[timed out after {budget}s]\n")
        log.flush()
        sys.exit(f"stage timed out after {budget}s: {os.path.basename(cmd[1])}. "
                 "A hung portal or fetch would otherwise hold the round until "
                 "the container is reclaimed and the whole search is lost.")
    log.write("\n$ " + " ".join(cmd) + "\n" + r.stdout + r.stderr)
    log.flush()
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
        sys.exit(f"stage failed: {os.path.basename(cmd[1])} (exit {r.returncode})")
    tail = [l for l in (r.stdout + "\n" + r.stderr).strip().splitlines() if l.strip()][-3:]
    for l in tail:
        print("   ", l)


# CLAUDE.md, Job Search Behaviour: "Yield target: at least 5 postings scoring
# 60+, of which 2 score 75+. A run that misses it expands the search and goes
# again, up to 3 rounds." None of that was in code. The round printed stage
# counts and stopped, so a run that surfaced two roles looked exactly like a run
# that surfaced twenty, and the target was something a person had to remember to
# check against a number nobody printed.
YIELD_60, YIELD_75, MAX_ROUNDS = 5, 2, 3

# What a finished round leaves behind.
#
# A round writes about 55MB across its ten stage files: the scrape, the
# hydrated bodies, the screened and scored sets. Every byte of it is derived,
# reproducible from seen_jobs.json plus a re-run, and thick with third-party
# posting text. Committing that is what CLAUDE.md means by build noise, and
# leaving it uncommitted trips the stop hook on every single round.
#
# So the round prunes itself. What survives is the part somebody would actually
# reread: the top of the shortlist without the posting bodies, at about 30KB,
# written outside `rounds/` so it commits with a plain `git add` rather than
# needing a .gitignore negation (which `tools/security_guards.py` rejects
# unless it is in a reviewed allowlist).
KEEP_TOP = 60
SUMMARY_DIR = "documents/rounds"
# Fields worth keeping. `desc` is deliberately absent: it is the whole reason
# the stage files are large, and it is on the posting's own page.
# `first_seen` and `age_days` because the portal's `date` is a relist date as often
# as not: the age is the earlier of the two.
SUMMARY_FIELDS = ("priority", "fit", "opportunity", "title", "company", "location",
                  "date", "first_seen", "age_days", "url", "portal", "bar", "bar_reason",
                  "warm_route_note", "outreach_pending_note", "throttle_override_note",
                  "drafted_note")


def write_summary(shortlist_path, out_dir, name):
    """The compact shortlist, and where it was written."""
    try:
        rows = json.load(open(shortlist_path))
    except Exception:
        return None
    rows = rows if isinstance(rows, list) else list(rows.values())
    rows.sort(key=lambda r: -(r.get("priority") or 0))
    out = [{k: r.get(k) for k in SUMMARY_FIELDS if r.get(k) not in (None, "")}
           for r in rows[:KEEP_TOP]]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.json" % name)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    return path


# The files the MISSED message tells you to read. A round that hit its target
# needs none of them; a round that missed needs all three, because they are the
# three places a posting can disappear: the free gates, the stated-fact screen,
# and the throttle.
#
# They used to be deleted a dozen lines before the message that names them. The
# advice was printed over an empty directory, and on `--expand` every widened
# round pruned its own too, so three rounds of diagnosis left nothing to
# diagnose. What made them big was never the metadata, it was `desc`: the full
# posting body, capped at BODY_CAP per record and multiplied by a thousand
# records. Strip that and the three files that answer "where did everything go"
# cost a few hundred KB between them.
DIAGNOSTICS = ("01_dropped.json", "03_screened_all.json", "06_skipped.json")
BODY_FIELD = "desc"


def slim(path):
    """Rewrite a stage file without the posting bodies. Returns bytes saved."""
    try:
        before = os.path.getsize(path)
        rows = json.load(open(path))
    except Exception:
        return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    out = [{k: v for k, v in r.items() if k != BODY_FIELD} if isinstance(r, dict) else r
           for r in rows]
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    return max(0, before - os.path.getsize(path))


# The file drafting starts from. `tools/stage_picks.py` reads each picked
# posting's body out of it, and the prune deleted it on every round that met its
# target, so "draft 1 and 3" from the shortlist that had just been presented
# failed on a missing file. It stays, cut to the KEEP_TOP rows anybody is shown,
# with their bodies: rounds/ is gitignored, so the bodies never reach a commit.
SHORTLIST = "06_shortlist.json"


def trim(path, top=KEEP_TOP):
    """Keep the first `top` rows of a shortlist, bodies and all. Returns bytes saved.

    A shortlist that will not parse is no use to stage from, and staging falls
    back to `documents/rounds/<round>.json` when it is absent, so it is deleted.
    """
    try:
        before = os.path.getsize(path)
        rows = json.load(open(path))
    except Exception:
        try:
            size = os.path.getsize(path)
            os.remove(path)
            return size
        except OSError:
            return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    with open(path, "w") as fh:
        json.dump(rows[:top], fh, indent=1)
        fh.write("\n")
    return max(0, before - os.path.getsize(path))


def prune(out_dir, keep=(), hold=()):
    """Delete the stage files, keeping the round directory, its log, the shortlist and `keep`.

    The log is small, is already gitignored as `*.log`, and is the funnel
    record somebody reads when a round looks wrong. The shortlist is what a
    draft is staged from. Anything named in `keep` is slimmed rather than deleted,
    and anything in `hold` is left as it is, for the caller to delete later.
    """
    freed = 0
    for name in os.listdir(out_dir):
        if name == "round.log" or name in hold:
            continue
        path = os.path.join(out_dir, name)
        if name == SHORTLIST:
            freed += trim(path)
            continue
        if name in keep:
            freed += slim(path)
            continue
        try:
            if os.path.isdir(path):
                freed += sum(os.path.getsize(os.path.join(path, f))
                             for f in os.listdir(path))
                shutil.rmtree(path)
            else:
                freed += os.path.getsize(path)
                os.remove(path)
        except OSError:
            pass
    return freed

# A thin market and a broken pipeline are different answers and used to share
# exit 1 with `sys.exit("stage failed: ...")`. A caller that cannot tell them
# apart either ignores both or re-runs a pipeline that is working fine.
EXIT_YIELD_MISSED = 2

# The widenings this script can actually perform: more pages per query. The rest
# of the documented sequence, more title variants, the remaining priority
# categories, wider PASS-set locations, adjacent sectors and named employers,
# lives in scrape_wide's own constants and in judgement, so it is printed as the
# next thing to do rather than pretended at.
#
# Never the freshness rule. Each widening used to stretch --jobage too (14, then
# 21, then 42), and a posting six weeks old is the most expensive false positive
# the pipeline has: "never relax a gate to hit the number" covers that one.
WIDENINGS = (2.0, 3.0)
# What a widened round reuses from the one before it, so it does not fetch the
# same bodies again: the hydrated file, held back from the prune until it has run.
HYDRATED = "02_hydrated.json"


def yield_of(path):
    """(count scoring 60+, count scoring 75+) on the shortlist, by the 0-100 score.

    The score is `fit`. `priority` is only the order (fit times opportunity), and
    counted as the score a posting with no stated salary and no date in the last
    five days topped out at 69 for the example profile, so it could never be one of
    the "2 at 75+" however well it fitted, though an unstated salary costs nothing.
    A row with no fit, from before fit.py, is counted by its priority.
    """
    try:
        rows = json.load(open(path))
    except Exception:
        return 0, 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    scores = [(r.get("fit") if r.get("fit") is not None else r.get("priority")) or 0
              for r in rows if isinstance(r, dict)]
    return sum(1 for s in scores if s >= 60), sum(1 for s in scores if s >= 75)


def count(path):
    try:
        d = json.load(open(path))
        return len(d) if isinstance(d, list) else len(d.get("jobs", d))
    except Exception:
        return "?"


def _portals_down(out_dir: str) -> list[str]:
    """Portals the pre-flight probe found silent, if scrape_wide wrote the file.

    Fails open. A missing file means the probe did not run or was skipped,
    which is not the same as every portal being healthy, but it is not
    something to stop a round over either.
    """
    for path in (os.path.join(out_dir, "00_scrape", "00_portal_health.json"),
                 os.path.join(out_dir, "00_portal_health.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                return list(json.load(fh).get("portals_down") or [])
        except (OSError, ValueError, AttributeError):
            continue
    return []


def _upgrades_line() -> str:
    """The pending profile upgrades, one line, for the round's summary. Fails open."""
    try:
        import profile_upgrades
        return profile_upgrades.line()
    except Exception:
        return ""


def _boards_not_built() -> list[str]:
    """profile/search.py PORTAL_RESEARCH entries with no portal here. Fails open."""
    try:
        import portals
        return [f"{r.get('board', '?')} ({r.get('status', 'not built')})"
                for r in portals.not_built()]
    except Exception:
        return []


def main():
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="directory for this round's files")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--jobage", type=int, default=14, help="hard freshness rule, days")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--top", type=int, default=40, help="shortlist length shown")
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--require", default="0.9",
                    help="hydrate: fail below this fraction with a description")
    ap.add_argument("--from-scraped", dest="from_scraped",
                    help="skip the scrape; use this JSON list as 00_scrape/kept.json")
    ap.add_argument("--tracker", default=None, help="throttle: tracker CSV (default: the repo's)")
    ap.add_argument("--seen", default=None, help="throttle: seen_jobs.json (default: the repo's)")
    ap.add_argument("--no-seen-write", dest="no_seen_write", action="store_true",
                    help="throttle: do not record skips in seen_jobs.json")
    ap.add_argument("--no-seen-read", dest="no_seen_read", action="store_true",
                    help="prefilter: do not drop postings already ruled out. The "
                         "throttle still drops them at the end, so this costs a "
                         "round's worth of HTTP and buys a re-evaluation of "
                         "everything previously excluded")
    ap.add_argument("--expand", action="store_true",
                    help=f"re-run wider when the yield target is missed, up to "
                         f"{MAX_ROUNDS} rounds")
    ap.add_argument("--round", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--hydrate-cache", dest="hydrate_cache", default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--summary-dir", dest="summary_dir", default=None,
                    help="where the compact shortlist is written (default: "
                         "%s under the repo). A test pointing --out at a temp "
                         "directory must point this there too, or it writes "
                         "into the committed tree." % SUMMARY_DIR)
    ap.add_argument("--alerts", default=None,
                    help="scrape: postings from the person's job-alert emails "
                         "(tools/job_alerts.py output)")
    ap.add_argument("--keep-intermediates", dest="keep", action="store_true",
                    help="keep the stage files instead of pruning them; they are "
                         "reproducible, so this is for debugging a round that went wrong")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    f = lambda n: os.path.join(a.out, n)
    log = open(f("round.log"), "a")
    # One monotonic ceiling for the whole round. Every stage gets the
    # smaller of its own budget and what is left of this.
    deadline = time.monotonic() + ROUND_BUDGET_SEC
    scrape_dir = f("00_scrape")

    if a.from_scraped:
        os.makedirs(scrape_dir, exist_ok=True)
        dest = os.path.join(scrape_dir, "kept.json")
        # Re-running a round in place, `--from-scraped rounds/r17/00_scrape/kept.json
        # --out rounds/r17`, is a natural thing to type and used to die on an
        # unhandled shutil.SameFileError several frames deep. The right move is
        # a new --out, because this one is about to be pruned and the copy would
        # be pruning its own input.
        if os.path.exists(dest) and os.path.samefile(a.from_scraped, dest):
            sys.exit("--from-scraped is this round's own 00_scrape/kept.json. "
                     "Point --out at a new directory; re-running a round in place "
                     "would prune the file it is reading from.")
        shutil.copyfile(a.from_scraped, dest)
        print(f"+ (scrape skipped; {a.from_scraped} -> {scrape_dir}/kept.json)")
    else:
        # scrape_wide's --out is a DIRECTORY holding scraped/kept/dropped.json.
        run([sys.executable, f"{T}/scrape_wide.py", "--out", scrape_dir,
             "--pages", str(a.pages), "--jobage", str(a.jobage), "--today", a.today,
             "--workers", str(a.workers)] + (["--alerts", a.alerts] if a.alerts else []),
            log, deadline)
    scraped = os.path.join(scrape_dir, "kept.json")

    # `--seen` is what stops hydrate paying for postings this search already
    # ruled out. The check is throttle.ruled_out() either way; running it here
    # rather than only at the end saves one HTTP call plus four free stages per
    # repeat, and on the 2,910 postings in seen_jobs 16% of everything reaching
    # hydrate was in that state.
    prefilter = [sys.executable, f"{T}/prefilter.py", scraped, "--out", f("01_prefiltered.json"),
                 "--dropped", f("01_dropped.json"), "--jobage", str(a.jobage),
                 "--today", a.today]
    if not a.no_seen_read:
        prefilter += ["--seen", a.seen or person.state("job_scraper", "seen_jobs.json")]
    run(prefilter, log, deadline)
    # Hydrate AFTER the free gates: one HTTP call per survivor, none for the rest.
    run([sys.executable, f"{T}/hydrate.py", f("01_prefiltered.json"), "--out", f(HYDRATED),
         "--workers", str(a.workers), "--require", a.require]
        + (["--cache", a.hydrate_cache] if a.hydrate_cache else []), log, deadline)
    # The screen's cuts go to seen_jobs.json, so the next round drops them before
    # hydrate fetches them again.
    run([sys.executable, f"{T}/text_screen.py", f(HYDRATED), "--out", f("03_screened.json"),
         "--out-all", f("03_screened_all.json"), "--today", a.today]
        + ([] if a.no_seen_write
           else ["--seen", a.seen or person.state("job_scraper", "seen_jobs.json")]),
        log, deadline)
    run([sys.executable, f"{T}/opportunity.py", f("03_screened.json"), "--out", f("04_opportunity.json"),
         "--top", "100000", "--today", a.today], log, deadline)
    run([sys.executable, f"{T}/fit.py", f("04_opportunity.json"), "--out", f("05_ranked.json"),
         "--top", str(a.top)], log, deadline)
    throttle = [sys.executable, f"{T}/throttle.py", f("05_ranked.json"), "--out", f("06_shortlist.json"),
                "--skipped", f("06_skipped.json"), "--today", a.today]
    if a.tracker:
        throttle += ["--tracker", a.tracker]
    if a.seen:
        throttle += ["--seen", a.seen]
    if a.no_seen_write:
        throttle += ["--no-write"]
    run(throttle, log, deadline)

    print("\nround summary")
    print(f"  {'00_scrape/kept':16s} {count(scraped)}")
    for n in STAGES:
        print(f"  {n:16s} {count(f(n + '.json'))}")
    print(f"\nshortlist: {f('06_shortlist.json')}")

    good, strong = yield_of(f("06_shortlist.json"))
    met = good >= YIELD_60 and strong >= YIELD_75
    print(f"yield: {good} scoring 60+ (target {YIELD_60}), "
          f"{strong} scoring 75+ (target {YIELD_75}) -> {'MET' if met else 'MISSED'}")

    # Write the keeper, then drop the rest. Done before the expansion branch
    # below returns, so every exit path leaves the same small footprint.
    summary = write_summary(f("06_shortlist.json"),
                            a.summary_dir or person.state(SUMMARY_DIR),
                            os.path.basename(a.out.rstrip("/")))
    if summary:
        print(f"shortlist summary: {os.path.relpath(summary, ROOT)} "
              f"(top {KEEP_TOP}, no posting bodies) - commit this one")
    # Read before the prune below deletes 00_scrape/, or a portal that went
    # quiet is never reported and the MISSED message blames the market.
    down = _portals_down(a.out)
    if down:
        print(f"portal health: {', '.join(down)} DOWN (0 results to a deliberately broad probe)")
    widen = not met and a.expand and a.round < MAX_ROUNDS
    if not a.keep:
        # The shortlist survives every prune, for drafting. A round that missed
        # is also read for exactly the three files the MISSED message below
        # names, so those survive with their posting bodies stripped. A round
        # about to widen holds its hydrated bodies back for the next one.
        freed = prune(a.out, keep=() if met else DIAGNOSTICS,
                      hold=(HYDRATED,) if widen else ())
        print(f"pruned {freed // (1024 * 1024)}MB of reproducible stage files "
              f"(--keep-intermediates to retain them)"
              + ("" if met else f"; kept {', '.join(DIAGNOSTICS)} without bodies"))
    # Once per run: on the round that ends it, not on each widening.
    if met or not (a.expand and a.round < MAX_ROUNDS):
        pending_line = _upgrades_line()
        if pending_line:
            print(pending_line)
    if met:
        print("next: read the shortlist, confirm nothing already applied to "
              "directly, then draft.")
        return 0

    if widen:
        pages_x = WIDENINGS[a.round - 1]
        nxt = f"{a.out.rstrip('/')}_round{a.round + 1}"
        print(f"\nexpanding: round {a.round + 1} of {MAX_ROUNDS}, "
              f"pages {a.pages} -> {int(a.pages * pages_x)}, "
              f"jobage held at {a.jobage} (the freshness rule never widens) -> {nxt}")
        cache = f(HYDRATED)
        code = subprocess.call(
            [sys.executable, __file__, "--out", nxt,
             "--pages", str(int(a.pages * pages_x)),
             "--jobage", str(a.jobage),
             "--workers", str(a.workers), "--top", str(a.top), "--today", a.today,
             "--require", a.require, "--expand", "--round", str(a.round + 1)]
            + (["--hydrate-cache", cache] if os.path.exists(cache) else [])
            + (["--keep-intermediates"] if a.keep else [])
            + (["--alerts", a.alerts] if a.alerts else [])
            + (["--summary-dir", a.summary_dir] if a.summary_dir else [])
            + (["--tracker", a.tracker] if a.tracker else [])
            + (["--seen", a.seen] if a.seen else [])
            + (["--no-seen-write"] if a.no_seen_write else [])
            + (["--no-seen-read"] if a.no_seen_read else []))
        if not a.keep:
            try:
                os.remove(cache)
            except OSError:
                pass
        return code

    # CLAUDE.md: "If the target is still missed after 3 rounds, say so
    # explicitly with the count, what was tried, and the likely blocker. Never
    # pad a thin run with sub-60 postings, and never relax a gate or the
    # location filter to hit the number."
    print(f"\nYIELD TARGET MISSED after round {a.round}"
          f"{'' if a.expand else ' (no --expand, so no wider round was run)'}.")
    print(f"  got {good} at 60+ and {strong} at 75+; wanted {YIELD_60} and {YIELD_75}")

    # Before anything about the market, say whether a board was even answering.
    # A portal that has gone quiet produces exactly this message, and every
    # sentence below it about a thin local market would be a true-sounding lie.
    if down:
        print(f"  *** {', '.join(down)} returned nothing to the pre-flight probe. ***")
        print("  This round is NOT evidence about the market. Fix the portal and "
              "re-run before widening or concluding anything from the count.")
    print(f"  tried: {a.pages} pages per query, {a.jobage}-day freshness, "
          f"scrape_wide's full query and location set")
    print(f"  likely blocker: in {a.out}, check 06_skipped.json for what the throttle "
          "removed, 01_dropped.json for the location and age gates, and "
          "03_screened_all.json for the stated-fact knockouts. All three were kept "
          "(without posting bodies) precisely because this round missed.")
    print("  widen next, in this order: more title variants, the remaining priority "
          "categories, wider PASS-set locations, adjacent target sectors and named "
          "employers, then the WebSearch fallback.")
    # Coverage is the other lever. A board that serves this person's market and
    # has no portal here contributes nothing to any round, however wide.
    gaps = _boards_not_built()
    if gaps:
        print("  boards researched for you with no portal yet (each one is coverage "
              "no round has): " + "; ".join(gaps) + ". Building one is /add-portal.")
    print("  do NOT pad with sub-60 postings, and do NOT relax a gate to hit the number.")
    return EXIT_YIELD_MISSED


if __name__ == "__main__":
    sys.exit(main() or 0)
