#!/usr/bin/env python3
"""One command from portals to a ranked shortlist.

    python3 tools/run_round.py --out rounds/r1 [--pages 5] [--jobage 14]
    python3 tools/run_round.py --out rounds/r2 --from-scraped rounds/r1/00_scrape/kept.json

Runs every free stage in order and stops at the shortlist, which is where a
person decides. Nothing here spends model tokens. The stages and why each one
exists are in .claude/skills/job-scraper/manual-round.md and 11-cost-model.md; this
file just makes the order impossible to get wrong, because it was got wrong:
one round ranked 70 postings that had never been hydrated, another wrote a
one-row shortlist because --top truncated the --out file upstream, and the
first version of this file handed scrape_wide's output DIRECTORY to hydrate
as if it were a file and prefilter's dict to text_screen as if it were a list.

  scrape_wide   every portal that is on, paginated, the profile's locations, remote
                locations and title queries (search.py SCRAPE_*),
                plus the employer boards in ats_boards.py (every system the
                vendored openroles reads)
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
import argparse, datetime, json, os, re, shutil, subprocess, sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "tools")
sys.path.insert(0, T)
import person  # noqa: E402
import local_path  # noqa: E402

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


class StageTimeout(Exception):
    """A stage ran past its budget and was stopped."""


# Every stage writes UTF-8, whatever the computer's own default. On Windows that default
# is cp1252: a stage's stderr carrying an accented place name arrived as bytes the round
# decoded as UTF-8, and the replacement character it got could not be written to a log
# opened in cp1252, so the thread draining the pipe died and the stage hung until its
# budget ran out. The round's own log and output are UTF-8 for the same reason (main).
STAGE_ENCODING = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _stream(cmd, log, budget):
    """(exit code, stdout, stderr) for one stage, its stderr passed on as it arrives.

    A stage's output was captured and shown only when it ended, so a chat running a
    45-minute round in the background could not say how far along it was, or tell
    a slow round from a hung one. Each stderr line (scrape_wide's progress lines among
    them) now goes to this process's stderr and to round.log the moment it is written."""
    import threading
    with tempfile.TemporaryFile("w+", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, cwd=ROOT, text=True, stdout=out, stderr=subprocess.PIPE,
                             encoding="utf-8", errors="replace",
                             env={**os.environ, **STAGE_ENCODING})
        lines = []

        def pump():
            # Every line is read whatever happens to it after. A line this process could
            # not write (a log or a console in another encoding) killed the thread, and
            # with nothing reading the pipe the stage blocked until its budget ran out.
            for line in p.stderr:
                lines.append(line)
                try:
                    print(line, end="", file=sys.stderr, flush=True)
                except Exception:
                    pass
                try:
                    log.write(line)
                    log.flush()
                except Exception:
                    pass

        th = threading.Thread(target=pump, daemon=True)
        th.start()
        try:
            p.wait(timeout=budget)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            th.join(5)
            out.seek(0)
            raise StageTimeout(out.read() + "".join(lines)) from None
        th.join(5)
        out.seek(0)
        return p.returncode, out.read(), "".join(lines)


# The scrape a round has finished, for the line a later stage's timeout prints: the
# stages after it read files, so the round can go on from it with --from-scraped
# rather than scraping again.
RESUME: dict = {}

# What a stage that runs out of time can still keep, by its script's name: called
# instead of stopping the round, and its return value is the stage's exit code. Kept
# beside run(), never an argument to it, so anything that stands in for run() (a test,
# a person's own) keeps working.
ON_TIMEOUT: dict = {}


def took(seconds: float) -> str:
    """A duration as a person reads it: "22m 28s", "4s", "1h 3m"."""
    s = max(0, int(round(seconds)))
    hours, rest = divmod(s, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# (stage, seconds) for every stage run() ran in this round, in order. A round's log
# had no time in it at all, so where half an hour went could only be guessed at.
TIMES: list = []


def _stage_done(log, name: str, began: float, how: str) -> float:
    secs = time.monotonic() - began
    TIMES.append((name, secs))
    log.write(f"[{name} finished {_now()}, took {took(secs)}, {how}]\n")
    log.flush()
    return secs


# One line per request a paced board sent (scrape_wide.py --request-log): when, which
# board, what it asked, how many postings came back, how many were new to the round,
# how long it took. Written beside the scrape's files and copied into round.log, which
# survives the prune, so a later change can learn when a board stops finding anything
# new. Only the paced boards: LinkedIn's thousands of requests would bury the rest.
REQUEST_LOG = "requests.log"


def keep_requests(log, path: str) -> None:
    """The paced boards' request lines, added to the round's log once the scrape ends."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read()
    except OSError:
        return
    if lines.strip():
        log.write(f"[paced board requests, one line each: {lines.count(chr(10))}]\n{lines}")
        log.flush()


def run(cmd, log, deadline=None, ok=(0,)):
    """Run one stage; its exit code, which is one of `ok`, or the round stops.

    Its start, its end and how long it took go in the round's log."""
    print("+", " ".join(cmd), flush=True)
    budget = _stage_budget(cmd, deadline)
    name = os.path.basename(cmd[1]) if len(cmd) > 1 else ""
    began = time.monotonic()
    log.write("\n$ " + " ".join(cmd) + f"\n[{name} started {_now()}]\n")
    log.flush()
    try:
        code, stdout, stderr = _stream(cmd, log, budget)
    except StageTimeout as e:
        log.write(str(e)[-20000:] + f"\n[timed out after {budget}s]\n")
        _stage_done(log, name, began, "stopped: out of time")
        on_timeout = ON_TIMEOUT.pop(os.path.basename(cmd[1]) if len(cmd) > 1 else "", None)
        if on_timeout is not None:
            print(f"   stage timed out after {budget}s: {os.path.basename(cmd[1])}; "
                  "keeping what it had found", flush=True)
            return on_timeout()
        saved = RESUME.get("scrape", "")
        sys.exit(f"stage timed out after {budget}s: {os.path.basename(cmd[1])}. "
                 "A hung portal or fetch would otherwise hold the round until "
                 "the container is reclaimed and the whole search is lost."
                 + (f" The scrape it had finished is kept: to go on from it, run the round "
                    f"again with --from-scraped {saved} and a new --out."
                    if saved and name != "scrape_wide.py" and os.path.isfile(saved) else ""))

    import types
    # stderr is already in the log, line by line
    r = types.SimpleNamespace(returncode=code, stdout=stdout, stderr="")
    log.write(r.stdout)
    log.flush()
    secs = _stage_done(log, name, began, f"exit {r.returncode}")
    if r.returncode not in ok:
        print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
        sys.exit(f"stage failed: {os.path.basename(cmd[1])} (exit {r.returncode})")
    tail = [l for l in r.stdout.strip().splitlines() if l.strip()][-3:]
    for l in tail:
        print("   ", l)
    print(f"    ({name} took {took(secs)})")
    return r.returncode


# scrape_wide exits 2, after writing its files, when more than a quarter of the
# portal requests failed. The skill says a portal failing is logged and the search
# continues, and that exit stopped the round as a broken stage, losing what every
# other request had found. It is a warning the round carries to its summary.
SCRAPE_PARTIAL = 2


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
# fit_why rides along: the reasons behind the score, which an interview pack reads weeks
# later, after the round's own files are pruned.
SUMMARY_FIELDS = ("priority", "fit", "fit_why", "opportunity", "title", "company", "location",
                  "date", "first_seen", "age_days", "url", "portal", "bar", "bar_reason",
                  "warm_route_note", "outreach_pending_note", "throttle_override_note",
                  "drafted_note")


def round_order(path: str) -> tuple:
    """How saved rounds sort, oldest first: by the numbers in the round's name ("r3"
    before "r18", "r18" before "r18_round2"), then by when the file was written. A fresh
    clone gives every file the same time, so the time alone picked whichever round the
    folder happened to list last as "the newest"."""
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        written = os.path.getmtime(path)
    except OSError:
        written = 0.0
    return tuple(int(n) for n in re.findall(r"\d+", name)), written


def write_summary(shortlist_path, out_dir, name):
    """The compact shortlist, and where it was written."""
    try:
        rows = json.load(open(shortlist_path, encoding="utf-8"))
    except Exception:
        return None
    rows = rows if isinstance(rows, list) else list(rows.values())
    rows.sort(key=lambda r: -(r.get("priority") or 0))
    out = [{k: r.get(k) for k in SUMMARY_FIELDS if r.get(k) not in (None, "")}
           for r in rows[:KEEP_TOP]]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.json" % name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    return path


# The files the MISSED message tells you to read. A round that hit its target
# needs none of them; a round that missed needs all of them, because they are the
# places a posting can disappear: the free gates, the search's own past rulings,
# the stated-fact screen, and the throttle.
#
# They used to be deleted a dozen lines before the message that names them. The
# advice was printed over an empty directory, and on `--expand` every widened
# round pruned its own too, so three rounds of diagnosis left nothing to
# diagnose. What made them big was never the metadata, it was `desc`: the full
# posting body, capped at BODY_CAP per record and multiplied by a thousand
# records. Strip that and the files that answer "where did everything go" cost
# a few hundred KB between them.
#
# The free gates' drops are the scrape's own: scrape_wide applies the age, place
# and title gates before it writes kept.json, so they land in 00_scrape/dropped.json.
# 01_dropped.json holds only what prefilter drops after that, which is what this
# search had already ruled out. The message named 01_dropped.json for the location
# and age gates, and the file that answers it was deleted with the rest of 00_scrape.
SCRAPE_DROPPED = os.path.join("00_scrape", "dropped.json")
DIAGNOSTICS = (SCRAPE_DROPPED, "01_dropped.json", "03_screened_all.json", "06_skipped.json")
BODY_FIELD = "desc"


def slim(path):
    """Rewrite a stage file without the posting bodies. Returns bytes saved."""
    try:
        before = os.path.getsize(path)
        rows = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    out = [{k: v for k, v in r.items() if k != BODY_FIELD} if isinstance(r, dict) else r
           for r in rows]
    with open(path, "w", encoding="utf-8") as fh:
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
        rows = json.load(open(path, encoding="utf-8"))
    except Exception:
        try:
            size = os.path.getsize(path)
            os.remove(path)
            return size
        except OSError:
            return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    with open(path, "w", encoding="utf-8") as fh:
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
        inner = {k.split(os.sep, 1)[1] for k in keep if k.startswith(name + os.sep)}
        try:
            if os.path.isdir(path) and inner:
                # A directory one of whose files is kept: that file slimmed, the rest gone.
                for f in os.listdir(path):
                    p = os.path.join(path, f)
                    if f in inner:
                        freed += slim(p)
                    elif os.path.isfile(p):
                        freed += os.path.getsize(p)
                        os.remove(p)
            elif os.path.isdir(path):
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
# And so it does not send the same searches again: the scrape folder, whose postings it
# carries over and whose answered requests it skips (scrape_wide --before).
SCRAPED = "00_scrape"


def yield_of(path):
    """(count scoring 60+, count scoring 75+) on the shortlist, by the 0-100 score.

    The score is `fit`. `priority` is only the order (fit times opportunity), and
    counted as the score a posting with no stated salary and no date in the last
    five days topped out at 69 for the example profile, so it could never be one of
    the "2 at 75+" however well it fitted, though an unstated salary costs nothing.
    A row with no fit, from before fit.py, is counted by its priority.
    """
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 0, 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    scores = [(r.get("fit") if r.get("fit") is not None else r.get("priority")) or 0
              for r in rows if isinstance(r, dict)]
    return sum(1 for s in scores if s >= 60), sum(1 for s in scores if s >= 75)


def count(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
        return len(d) if isinstance(d, list) else len(d.get("jobs", d))
    except Exception:
        return "?"


def _health_file(out_dir: str) -> dict:
    for path in (os.path.join(out_dir, "00_scrape", "00_portal_health.json"),
                 os.path.join(out_dir, "00_portal_health.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                got = json.load(fh)
            if isinstance(got, dict):
                return got
        except (OSError, ValueError):
            continue
    return {}


def _portals_down(out_dir: str) -> list[str]:
    """Portals the pre-flight probe found silent or refusing, if scrape_wide wrote the file.

    Fails open. A missing file means the probe did not run or was skipped,
    which is not the same as every portal being healthy, but it is not
    something to stop a round over either.
    """
    return list(_health_file(out_dir).get("portals_down") or [])


def _down_detail(out_dir: str, name: str) -> str:
    """What the probe found for one portal that is down: silent, or what it said when it
    refused. Every down portal used to be reported as "0 results", the 403 ones too."""
    detail = (_health_file(out_dir).get("detail") or {}).get(name)
    return str(detail) if detail else "0 results to a deliberately broad probe"


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


class _Parser(argparse.ArgumentParser):
    """A mistyped option exits 1, a stage broke, as every other failure here does. argparse's
    own exit for it is 2, which this round keeps for "the yield target was missed": a typo
    read as a thin market, and the round widened on nothing."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def round_dir(out: str) -> str:
    """--out as this computer names a folder: separators of either kind, no trailing one.
    `--out rounds\\r1\\` on Windows kept its trailing backslash, so the round's name came
    out empty and its shortlist was saved as documents/rounds/.json."""
    if os.sep == "/":
        out = out.replace("\\", "/")
    return os.path.normpath(out)


def main():
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = _Parser()
    ap.add_argument("--out", required=True, help="directory for this round's files")
    ap.add_argument("--pages", type=int, default=None,
                    help="default 5 in the cloud and 2 on a person's own computer "
                         "(scrape_wide.defaults; SCRAPE_PAGES in profile/search.py)")
    ap.add_argument("--jobage", type=int, default=14, help="hard freshness rule, days")
    ap.add_argument("--workers", type=int, default=None,
                    help="default 10 in the cloud and 4 on their own computer (SCRAPE_WORKERS)")
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
                    help="drop nothing for a past ruling in seen_jobs.json, at the "
                         "prefilter or the throttle: everything previously excluded is "
                         "fetched, screened and scored again, for after the rules change. "
                         "Postings are still aged from when they were first seen")
    ap.add_argument("--expand", action="store_true",
                    help=f"re-run wider when the yield target is missed, up to "
                         f"{MAX_ROUNDS} rounds")
    ap.add_argument("--round", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--first-pages", dest="first_pages", type=int, default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--hydrate-cache", dest="hydrate_cache", default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--scrape-before", dest="scrape_before", default=None,
                    help=argparse.SUPPRESS)
    ap.add_argument("--summary-dir", dest="summary_dir", default=None,
                    help="where the compact shortlist is written (default: "
                         "%s under the repo). A test pointing --out at a temp "
                         "directory must point this there too, or it writes "
                         "into the committed tree." % SUMMARY_DIR)
    ap.add_argument("--keep-intermediates", dest="keep", action="store_true",
                    help="keep the stage files instead of pruning them; they are "
                         "reproducible, so this is for debugging a round that went wrong")
    a = ap.parse_args()
    a.out = round_dir(a.out)
    # A line this round cannot print in the console's own encoding is printed with a
    # stand-in character, never raised: an accented employer name ended the round.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    import scrape_wide
    pages, workers, _ = scrape_wide.defaults()
    a.pages = a.pages or pages
    a.workers = a.workers or workers
    os.makedirs(a.out, exist_ok=True)
    f = lambda n: os.path.join(a.out, n)
    log = open(f("round.log"), "a", encoding="utf-8", errors="replace")
    # One monotonic ceiling for the whole round. Every stage gets the
    # smaller of its own budget and what is left of this.
    started = time.monotonic()
    deadline = started + ROUND_BUDGET_SEC
    TIMES.clear()
    RESUME.clear()
    scrape_dir = f(SCRAPED)
    partial = ""

    if a.from_scraped:
        if not os.path.isfile(a.from_scraped):
            sys.exit(f"--from-scraped: there is no file at {a.from_scraped}. Point it at a "
                     "saved scrape, a round's 00_scrape/kept.json.")
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
        def keep_what_arrived():
            # The stage was killed: what it had found is in partial_rows.json, written
            # as it arrived. Turned into the scrape's files, the round goes on with it
            # and says so, rather than ending with nothing.
            nonlocal_partial.append(True)
            return run([sys.executable, f"{T}/scrape_wide.py", "--out", scrape_dir, "--finish",
                        "--jobage", str(a.jobage), "--today", a.today],
                       log, None, ok=(0, SCRAPE_PARTIAL))

        nonlocal_partial: list = []
        ON_TIMEOUT["scrape_wide.py"] = keep_what_arrived
        requests = os.path.join(scrape_dir, REQUEST_LOG)
        try:
            os.remove(requests)        # a round run again in the same place starts its own
        except OSError:
            pass
        code = run([sys.executable, f"{T}/scrape_wide.py", "--out", scrape_dir,
                    "--pages", str(a.pages), "--jobage", str(a.jobage), "--today", a.today,
                    "--workers", str(a.workers), "--request-log", requests]
                   # The employer boards read the repo's own seen file unless the round
                   # was given another.
                   + (["--seen", a.seen] if a.seen else [])
                   + (["--keep-ruled-out"] if a.no_seen_read else [])
                   + (["--before", a.scrape_before] if a.scrape_before else []),
                   log, deadline, ok=(0, SCRAPE_PARTIAL))
        ON_TIMEOUT.pop("scrape_wide.py", None)
        keep_requests(log, requests)
        if code == SCRAPE_PARTIAL:
            partial = ("the scrape stage ran out of time and kept only what had arrived"
                       if nonlocal_partial else
                       "more than a quarter of the portal requests failed, or a portal was "
                       "stopped short or refused the pre-flight probe (round.log names the "
                       "portals and why), so this round is not a full picture of the market")
    scraped = os.path.join(scrape_dir, "kept.json")
    RESUME["scrape"] = scraped

    # `--seen` is what stops hydrate paying for postings this search already
    # ruled out. The check is throttle.ruled_out() either way; running it here
    # rather than only at the end saves one HTTP call plus four free stages per
    # repeat, and on the 2,910 postings in seen_jobs 16% of everything reaching
    # hydrate was in that state.
    prefilter = [sys.executable, f"{T}/prefilter.py", scraped, "--out", f("01_prefiltered.json"),
                 "--dropped", f("01_dropped.json"), "--jobage", str(a.jobage),
                 "--today", a.today]
    # Read even with --no-seen-read: it is also when each posting was first seen.
    prefilter += ["--seen", a.seen or person.state("job_scraper", "seen_jobs.json")]
    if a.no_seen_read:
        prefilter += ["--keep-ruled-out"]
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
         "--top", str(a.top)] + (["--tracker", a.tracker] if a.tracker else []), log, deadline)
    throttle = [sys.executable, f"{T}/throttle.py", f("05_ranked.json"), "--out", f("06_shortlist.json"),
                "--skipped", f("06_skipped.json"), "--today", a.today]
    if a.tracker:
        throttle += ["--tracker", a.tracker]
    if a.seen:
        throttle += ["--seen", a.seen]
    if a.no_seen_write:
        throttle += ["--no-write"]
    if a.no_seen_read:
        throttle += ["--keep-ruled-out"]
    run(throttle, log, deadline)

    print("\nround summary")
    print(f"  {'00_scrape/kept':16s} {count(scraped)}")
    for n in STAGES:
        print(f"  {n:16s} {count(f(n + '.json'))}")
    if TIMES:
        # One entry a stage: a scrape that ran out of time and then kept what it had
        # found is two runs of scrape_wide, and was listed twice.
        by_stage: dict = {}
        for name, secs in TIMES:
            by_stage[name] = by_stage.get(name, 0) + secs
        spent = ", ".join(f"{name.rsplit('.', 1)[0]} {took(secs)}"
                          for name, secs in by_stage.items())
        line = f"time: {spent}; {took(time.monotonic() - started)} in all"
        print(line)
        log.write(line + "\n")
        log.flush()
    print(f"\nshortlist: {f('06_shortlist.json')}")

    good, strong = yield_of(f("06_shortlist.json"))
    met = good >= YIELD_60 and strong >= YIELD_75
    print(f"yield: {good} scoring 60+ (target {YIELD_60}), "
          f"{strong} scoring 75+ (target {YIELD_75}) -> {'MET' if met else 'MISSED'}")
    if partial:
        print(f"warning: {partial}")

    # Write the keeper, then drop the rest. Done before the expansion branch
    # below returns, so every exit path leaves the same small footprint.
    summary = write_summary(f("06_shortlist.json"),
                            a.summary_dir or person.state(SUMMARY_DIR),
                            os.path.basename(os.path.abspath(a.out)))
    if summary:
        print(f"shortlist summary: {local_path.rel(summary, ROOT)} "
              f"(top {KEEP_TOP}, no posting bodies) - commit this one")
    # What the round filtered out and why, kept every round before the prune deletes the
    # stage files that say it (tools/filtered.py; `filtered.py back` brings one back).
    import filtered
    left_out = filtered.write(a.out, a.summary_dir or person.state(SUMMARY_DIR),
                              os.path.basename(os.path.abspath(a.out)))
    if left_out:
        print(f"filtered out: {os.path.relpath(left_out, ROOT)} (each with its reason; "
              "tools/filtered.py back brings one back)")
    # Read before the prune below deletes 00_scrape/, or a portal that went
    # quiet is never reported and the MISSED message blames the market.
    down = _portals_down(a.out)
    for name in down:
        print(f"portal health: {name} DOWN ({_down_detail(a.out, name)})")
    blocked = str(_health_file(a.out).get("say") or "")
    if blocked:
        # The cloud chat's own settings block the sites: what fixes it is the person's,
        # in plain words, never "fix the portal" (env_check.blocked_say).
        print("Tell the person, in these words, once:")
        print("\n".join("  " + ln for ln in blocked.splitlines()))
    # A wider round searches more pages, which only a live scrape has, so from a saved
    # scrape it scrapes live. --expand is the asking: a round resumed from a timeout's kept
    # scrape (--from-scraped) is exactly the round that still owes its widening, and one
    # that never widened missed the yield rule's three rounds. It is said before it runs.
    widen = not met and a.expand and a.round < MAX_ROUNDS
    if not a.keep:
        # The shortlist survives every prune, for drafting. A round that missed
        # is also read for exactly the files the MISSED message below names, so
        # those survive with their posting bodies stripped. A round
        # about to widen holds its hydrated bodies back for the next one.
        freed = prune(a.out, keep=() if met else DIAGNOSTICS,
                      hold=(HYDRATED, SCRAPED) if widen else ())
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
        # Each widening is a multiple of the FIRST round's pages: 2x, then 3x. Applied to
        # the round before's, they compounded, and the third round searched 6x.
        first = a.first_pages or a.pages
        pages = int(first * WIDENINGS[a.round - 1])
        nxt = f"{a.out}_round{a.round + 1}"
        print(f"\nexpanding: round {a.round + 1} of {MAX_ROUNDS}, "
              f"pages {a.pages} -> {pages}, "
              f"jobage held at {a.jobage} (the freshness rule never widens) -> {nxt}")
        if a.from_scraped:
            print("  this round read a saved scrape; the wider round scrapes the portals live "
                  "for its extra pages")
        cache, scraped = f(HYDRATED), f(SCRAPED)
        code = subprocess.call(
            [sys.executable, __file__, "--out", nxt,
             "--pages", str(pages), "--first-pages", str(first),
             "--jobage", str(a.jobage),
             "--workers", str(a.workers), "--top", str(a.top), "--today", a.today,
             "--require", a.require, "--expand", "--round", str(a.round + 1)]
            + (["--hydrate-cache", cache] if os.path.exists(cache) else [])
            + (["--scrape-before", scraped] if os.path.isdir(scraped) else [])
            + (["--keep-intermediates"] if a.keep else [])
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
            shutil.rmtree(scraped, ignore_errors=True)
        return code

    # CLAUDE.md: "If the target is still missed after 3 rounds, say so
    # explicitly with the count, what was tried, and the likely blocker. Never
    # pad a thin run with sub-60 postings, and never relax a gate or the
    # location filter to hit the number."
    if not a.expand:
        why_not = " (no --expand, so no wider round was run)"
    else:
        why_not = ""
    print(f"\nYIELD TARGET MISSED after round {a.round}{why_not}.")
    print(f"  got {good} at 60+ and {strong} at 75+; wanted {YIELD_60} and {YIELD_75}")

    # Before anything about the market, say whether a board was even answering.
    # A portal that has gone quiet produces exactly this message, and every
    # sentence below it about a thin local market would be a true-sounding lie.
    if down:
        print(f"  *** {', '.join(down)} failed the pre-flight probe (portal health, above). ***")
        print("  This round is NOT evidence about the market. "
              + ("This chat's cloud settings block the sites: the person's fix is above. "
                 "Re-run" if blocked else "Fix the portal and re-run")
              + " before widening or concluding anything from the count.")
    if partial:
        print(f"  *** {partial}. ***")
    print(f"  tried: {a.pages} pages per query, {a.jobage}-day freshness, "
          f"scrape_wide's full query and location set")
    scrape_dropped = (f"{SCRAPE_DROPPED} for the age, location and title gates, "
                      if os.path.exists(f(SCRAPE_DROPPED)) else "")
    print(f"  likely blocker: in {a.out}, check 06_skipped.json for what the throttle "
          f"removed, {scrape_dropped}01_dropped.json for what was already ruled out "
          "or first seen too long ago, and 03_screened_all.json for the stated-fact "
          "knockouts. Each was kept (without posting bodies) precisely because this "
          "round missed.")
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
