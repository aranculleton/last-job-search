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
from __future__ import annotations

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
# What hydrate leaves of its stage limit for the fetches still running when its own budget
# ends (each is cut off at 60 seconds) and for writing what it found.
HYDRATE_MARGIN_SEC = 2 * 60


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
                  "warm_route_note", "referral_note", "outreach_pending_note",
                  "throttle_override_note",
                  "drafted_note", "silent_application_note", "apply_url", "link_kind",
                  "link_status", "link_check", "near", "salary")
LINK_FIELDS = ("apply_url", "link_kind", "link_status", "link_check")


def link_checks(rows: list[dict], scraped: list[dict], now=None) -> list[dict]:
    """Each kept row with its apply link checked against the employers' own boards as this
    round read them (tools/apply_link.py), with no request of its own: a board the scrape
    read is its listing, so a LinkedIn posting is matched to the employer's own and a
    board's posting is open by being there. Only the link fields are added; the row's own
    `url` stays as it was found, since rulings are keyed on it."""
    check = link_checker(scraped, now)
    return [check(r) for r in rows]


def link_checker(scraped: list[dict], now=None):
    """`link_checks` for one row at a time: the boards indexed once, each row checked as
    the cut reaches it, so a posting found closed is passed over like any other."""
    import apply_link
    from company_key import key as company_key
    by_board: dict = {}
    for r in scraped or []:
        if isinstance(r, dict) and r.get("portal"):
            by_board.setdefault((str(r["portal"]), company_key(r.get("company") or "")), []).append(r)

    def read(employer, kind, token):
        got = by_board.get((kind, company_key(employer)))
        return (got, None) if got else ([], "this round did not read that board")
    checker = apply_link.Checker(now=now, read=read)

    def check(r: dict) -> dict:
        try:
            shown = checker.shown(r)
        except Exception:  # noqa: BLE001  a row the checker cannot read keeps no link fields
            return r
        return dict(r, **{k: shown[k] for k in LINK_FIELDS if shown.get(k)})
    return check


def pay_text(row: dict) -> str:
    """The pay range the posting states, as a card shows it ("CAD 110,000 to 135,000"), or
    "". Read by the one parser the bar and the score use (text_screen.salary_range): the
    round read every range and kept none, so every card said the pay was not stated
    beside a note quoting its midpoint (2026-11-03)."""
    if row.get("salary"):
        return str(row["salary"])
    try:
        import text_screen
        lo, hi, _ = text_screen.salary_range(row.get("desc") or "")
        code = getattr(person.module("search"), "CURRENCY_CODE", "") or ""
    except Exception:  # noqa: BLE001  no profile or no body: nothing stated to show
        return ""
    if not lo and not hi:
        return ""
    lo, hi = lo or hi, hi or lo
    said = f"{lo:,}" if lo == hi else f"{lo:,} to {hi:,}"
    return f"{code} {said}".strip()


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


def _read_json(path):
    """A file's JSON, the file closed before anything else happens, failure or not: left
    open by a failed json.load, a broken shortlist could not be removed on Windows, which
    deletes no file that is open (2026-10-25)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def shown(show) -> int:
    """How many of the shortlist a search brings back: the person's choice on the page (10,
    25, or 0 for every one that fits), never more than KEEP_TOP. A search brought back 60 and
    the list reached 215 (2026-10-30); None keeps every one, as before."""
    if show is None:
        return KEEP_TOP
    n = int(show)
    return KEEP_TOP if n <= 0 else min(n, KEEP_TOP)


SET_ASIDE_ON_PAGE = "set aside on your page"
# A recruitment or staffing agency's posting names no employer, so it clears none of pay,
# prestige or signal: the person's own agency lists (employers.py AGENCY, EXTRA_AGENCY) read
# by tools/sector.py. Four came back in one search of 20 (the maintainer, 2026-11-04).
AGENCY_WHY = "a recruitment or staffing agency, so the employer is not named"


def page_set_asides(dump_dir) -> tuple[set, set]:
    """The postings the person set aside on their page whose tap is not applied yet, from a
    page dump holding its `actions` and `receipts`: each Set aside with no receipt, not
    taken back by a later tap (Undo, Bring back). A round that ran while they set jobs aside
    listed them again (the helper chat's report, 2026-11-02). (links, revs): each tap's rev,
    the posting and where it stood as the person saw it (app_model.job_rev), which any row of
    the same posting has; and its link where it is found, by that rev in any saved round or
    among the jobs they added, else by its round and rank, normalized."""
    if not dump_dir or not os.path.isdir(dump_dir):
        return set(), set()
    import glob
    import page_db
    import app_model
    import added_jobs
    from lookup_score import norm
    db = page_db.load(dump_dir)
    receipts = db.get("receipts") or {}
    acts = [(str(d["data"].get("at") or ""), aid, d["data"])
            for aid, d in (db.get("actions") or {}).items() if aid not in receipts]
    undone = {str(a.get("undoes") or (a.get("value") or {}).get("undoes") or "")
              for _, _, a in acts if a.get("action") == "undo" and isinstance(a, dict)}
    last: dict = {}
    for _, aid, a in sorted(acts):
        if a.get("action") in ("job.dismiss", "job.bring_back") and aid not in undone:
            last[str(a.get("item") or "")] = a
    taps = [a for a in last.values() if a.get("action") == "job.dismiss"]
    if not taps:
        return set(), set()
    saved = {"added": added_jobs.load()}
    for f in glob.glob(person.state(SUMMARY_DIR, "*.json")):
        try:
            rows = _read_json(f)
        except Exception:  # noqa: BLE001  one unreadable round reads as none
            rows = []
        saved[os.path.splitext(os.path.basename(f))[0]] = rows if isinstance(rows, list) else []
    by_rev = {}
    for rows in saved.values():
        for r in rows:
            if isinstance(r, dict):
                u, c, t = str(r.get("url") or ""), str(r.get("company") or ""), str(r.get("title") or "")
                for st in ("new", "ready"):
                    by_rev.setdefault(app_model.job_rev(u, c, t, st), u)
    out = set()
    for a in taps:
        url = by_rev.get(str(a.get("rev_seen") or ""))
        if url is None:
            m = re.match(r"^(.+)-(\d+)$", str(a.get("item") or ""))
            rows = saved.get(m.group(1)) or [] if m else []
            n = int(m.group(2)) if m else 0
            url = str((rows[n - 1] or {}).get("url") or "") if 0 < n <= len(rows) and \
                isinstance(rows[n - 1], dict) else ""
        if url and norm(url):
            out.add(norm(url))
    return out, {str(a.get("rev_seen") or "") for a in taps} - {""}


def declined_now() -> dict:
    """The employers turned down by name as the profile holds them now (search.py
    BAR_DECLINED, keyed as bar.py looks them up), read from the file: bar.py keeps the copy
    the round read when it started, so a "No more roles from them" said on the page while it
    ran was never seen by its cut (2026-11-04)."""
    try:
        import profile_set
        got = profile_set.get("search.py", "BAR_DECLINED")
    except Exception:  # noqa: BLE001  no profile, or no such setting: none
        return {}
    # Not set at all is profile_set.MISSING, itself a dict ({"missing": True}): read as the
    # setting, it turned down an employer called Missing and named it in Your rules.
    if got is profile_set.MISSING or not isinstance(got, dict):
        return {}
    return {str(k): str(v) for k, v in got.items() if isinstance(v, str)}


def family(name: str) -> set:
    """The saved rounds one search wrote: "r9", and "r9_round2" and "r9_round3" when it
    widened. A widened round finds what the round before it found, and that is not a job
    already on the list."""
    base = re.sub(r"_round\d+$", "", str(name or ""))
    if not base:
        return set()
    try:
        names = os.listdir(person.state(SUMMARY_DIR))
    except OSError:
        names = []
    return {base} | {os.path.splitext(n)[0] for n in names
                     if re.fullmatch(re.escape(base) + r"_round\d+\.json", n)}


def already_had(name: str = "", today=None, tracker: str | None = None, own=(),
                listed: bool = True, drafts: bool = True):
    """A function from a ranked row to why the person already has it, or "": a role in their
    applications (drafted, applied or decided, the tracker), a draft saved for it
    (documents/applications), a job they added or kept, or one still on their Jobs list from
    an earlier search (app_model.carried, the page's own answer). Matched by the posting's
    link, or by the employer and the role, so another site's copy of it is the same job.
    A search asked for 20 brought back four of these (the maintainer, 2026-11-04). `name` is
    the round being cut, whose own rounds are never "earlier"; `own`, the links its last cut
    kept, which a cut made again keeps whatever was done with them since. `listed` False
    leaves out the earlier searches' rows: the page's own list (page_rules) is read row by
    row, and a row there is never a copy of itself; `drafts` False leaves out the drafts saved
    with no tracker row yet, the job a chat is drafting now, whose row the tracker soon marks
    drafted. The function's `links` are the links the person's own records hold, so a cut
    lists a copy under another link, never the job."""
    import glob
    import throttle
    from company_key import key as company_key
    from lookup_score import norm
    by_url: dict = {}
    by_role: dict = {}
    records = None

    def note(url, company, role, why):
        u = norm(str(url or ""))
        if u:
            by_url.setdefault(u, why)
        k = company_key(str(company or ""))
        if k and str(role or "").strip():
            by_role.setdefault(k, []).append((str(role), why))

    try:
        rows = throttle._tracker_rows(tracker or person.state("job_search_tracker.csv"))
    except Exception:  # noqa: BLE001  no tracker yet: nothing applied for
        rows = []
    for r in rows:
        status = str(r.get("status") or "").strip().lower()
        when = str(r.get("date") or "").strip() or "an unrecorded date"
        why = (f"already drafted: {r.get('role')}, {when}" if status in throttle.UNSENT
               else f"already in your applications: {r.get('role')} ({status or 'no status'}, "
                    f"{when})")
        src = str(r.get("source") or "")
        note(src if src.startswith("http") else "", r.get("company"), r.get("role"), why)
    for p in (glob.glob(person.state("documents", "applications", "*", "draft.json"))
              if drafts else ()):
        try:
            got = _read_json(p)
        except Exception:  # noqa: BLE001  one unreadable draft reads as none
            continue
        for d in (got if isinstance(got, list) else [got]):
            if isinstance(d, dict):
                note(d.get("url"), d.get("company"), d.get("role") or d.get("title"),
                     f"already drafted: {d.get('role') or d.get('title')}")
    try:
        import added_jobs
        import app_model
        for r in added_jobs.load():
            note(r.get("url"), r.get("company"), r.get("title"), "already on your list: you "
                                                                 "added it")
        for url, k in app_model.kept_jobs().items():
            k = k if isinstance(k, dict) else {}
            note(url, k.get("company"), k.get("title"), "already on your list: kept for later")
        records = set(by_url)
        day = datetime.date.fromisoformat(today) if isinstance(today, str) else today
        for rname, _rank, r in (app_model.carried(day or datetime.date.today(),
                                                  but=family(name)) if listed else ()):
            note(r.get("url"), r.get("company"), r.get("title"),
                 f"already on your list, from search {rname}")
    except Exception:  # noqa: BLE001  no saved searches yet: nothing on the list
        pass
    if records is None:
        records = set(by_url)
    mine = {norm(str(u or "")) for u in own} - {None, ""}

    def check(row) -> str:
        u = norm(str(row.get("url") or ""))
        if u and u in mine:
            return ""
        if u and u in by_url:
            return by_url[u]
        k = company_key(str(row.get("company") or ""))
        return next((why for role, why in by_role.get(k, ())
                     if throttle._same_title(row.get("title"), role)), "")
    check.links = records
    return check


def hires_from_home(text: str) -> str:
    """The sentence of a posting saying it hires from the person's own country, region or
    city (text_screen's own reading of a home place), or "". A remote role anchored in the
    one neighbouring country passes the location gate only when the employer explicitly
    hires from home (prefilter.py, the neighbour), which its place cannot show and its body
    can."""
    import text_screen
    for s in text_screen.sentences(text or ""):
        if _HIRES.search(s) and text_screen._names_home(s):
            return s[:220]
    return ""


_HIRES = re.compile(r"\b(?:remote|anywhere|based|located|locations?|resid\w*|hir\w*|work(?:ing)? "
                    r"from|eligible|open to|candidates? (?:in|from)|country|countries)\b", re.I)


def place_rule(row) -> str:
    """Why a row's place is outside the person's places today, or "": the location gate's own
    FAIL on the place it names (prefilter.location_verdict, read with today's profile, so a
    row an older round kept is judged again), and a remote role anchored in the neighbouring
    country whose posting, read here, never says it hires from home. Without its posting (a
    saved shortlist keeps none) that second one is left as the gate left it, ranked down."""
    import prefilter
    place, title = str(row.get("location") or ""), str(row.get("title") or "")
    verdict, why = prefilter.location_verdict(place, title)
    if verdict == "FAIL":
        return f"place: {why}"
    nb = getattr(prefilter, "_NB", None) or {}
    body = str(row.get("desc") or "")
    if (verdict == "FLAG" and nb and body
            and why == nb.get("remote_reason", "remote but anchored abroad")
            and not hires_from_home(body)):
        return (f"place: {why}, and the posting never says it hires from "
                f"{prefilter._HOME or 'where you are'}")
    return ""


def judged_none(company) -> str:
    """The bar's reason when a chat or the person judged this employer to clear none of pay,
    prestige or signal (bar.py judge ... none), where the person's own profile states that bar,
    or "". An employer nobody has judged is flagged, never cut: it is judged before drafting
    (stage_picks), and once judged none it is cut here like any other hard rule."""
    import bar
    if not bar.applies():
        return ""
    j = bar.judgement(company)
    if not j or j.get("verdict") != bar.NONE:
        return ""
    said = str(j.get("why") or "").strip().rstrip(".")
    return ("candidate's bar: clears none of pay, prestige or signal"
            + (f" ({said})" if said else ""))


def unscored(row) -> bool:
    """A row with no 0-100 score, read as the page reads one (its fit, else its priority).
    Never shown: a list of unranked links is a failed search."""
    s = row.get("fit") if row.get("fit") is not None else row.get("priority")
    return not isinstance(s, (int, float)) or isinstance(s, bool)


def hard_rules(jobage, today, seen=None, keep_ruled_out=False, dump=None, name="",
               tracker=None, own=(), window=True, listed=True, drafts=True):
    """A function from a ranked row to the hard rule it fails now, or "": no score, the
    search window, the candidate's bar (tools/bar.py, its hard rules, with the posting read,
    and a recruitment or staffing agency by the person's own lists, tools/sector.py), the
    stated-fact screen's hard cuts (tools/text_screen.py: a language, eligibility, a
    credential...), a ruling or a hold made since the row was ranked
    (prefilter.already_ruled_out: seen_jobs.json, a referral in flight, do_not_target.json),
    and a job the person already has (already_had: applied, drafted, added, kept or on the
    list), the person's places (place_rule: the location gate's FAIL, and a remote role in the
    neighbouring country that never says it hires from home) and an employer judged to clear
    none of the bar (judged_none). The shortlist is cut with it (write_summary), so a row failing
    one is passed over and the next row taken: the one path every row a search brings back goes
    through, the number asked for (--show) and a cut made again (--recut) alike, and the page's
    Found list (page_rules, `window` and `listed` False: the page keeps its own window and reads
    its own list row by row). Made when the shortlist is
    cut, so it reads every ruling as it stands then, a Set aside or an employer turned down
    while the round ran included (declined_now); the person's own rulings hold even with --no-seen-read, which only looks again
    at what a rule decided; and with `dump`, a page dump, the Set asides still waiting on the
    page (page_set_asides)."""
    import bar
    import prefilter
    import sector
    import text_screen
    day = datetime.date.fromisoformat(today) if isinstance(today, str) else today
    ruled = prefilter.already_ruled_out(seen, keep_ruled_out, day) if seen else (lambda job: "")
    mine = (lambda job: "")
    if seen and keep_ruled_out:
        theirs = {k: e for k, e in (prefilter._seen_entries(seen) or {}).items()
                  if isinstance(e, dict) and e.get("basis") == "person"}
        mine = prefilter.already_ruled_out(seen, False, day, entries=theirs) if theirs else mine
    waiting, revs = page_set_asides(dump)
    declined = declined_now()
    had = already_had(name, day, tracker, own, listed=listed, drafts=drafts)
    from company_key import key as company_key
    from lookup_score import norm

    def set_aside(row) -> bool:
        if norm(row.get("url") or "") in waiting:
            return True
        if not revs:
            return False
        import app_model
        u, c, t = (str(row.get(k) or "") for k in ("url", "company", "title"))
        return any(app_model.job_rev(u, c, t, st) in revs for st in ("new", "ready"))

    def check(row) -> str:
        if unscored(row):
            return "no score: a job is never shown unscored"
        age = prefilter.age_days(row, day) if window else None
        if age is not None and age > jobage:
            return f"age: {age} days old, past the {jobage}-day window"
        verdict, why = bar.verdict(row.get("company"), row.get("desc") or "")
        if verdict == bar.EXCLUDED:
            return f"candidate's bar: {why}"
        if verdict == bar.NONE:
            none = judged_none(row.get("company"))
            if none:
                return none
        k = company_key(str(row.get("company") or "")) if declined else ""
        if k and k in declined:
            return f"candidate's bar: {declined[k]}"
        if sector.is_agency(row.get("company")):
            return f"candidate's bar: {AGENCY_WHY}"
        place = place_rule(row)
        if place:
            return place
        cuts = text_screen.screen(row).get("cuts") or []
        if cuts:
            return f"screen: {cuts[0]}"
        if (waiting or revs) and set_aside(row):
            return SET_ASIDE_ON_PAGE
        return ruled(row) or mine(row) or had(row) or ""
    check.had = had
    return check


def page_rules(today, seen=None, tracker=None):
    """The one function deciding what reaches the page's Found list (app_model._jobs), the
    shortlist's own (hard_rules) read row by row down the list the page builds: the jobs the
    person added, the newest search, then the earlier ones it carries. `check(row)` is the hard
    rule a row fails, or "", and a copy of a row already listed (by its link, or by the employer
    and the role, the app's own matching) fails as "already on your list"; `note(row)` lists a
    row the page shows whatever its rules say (one added, kept, brought back, drafted or
    applied for), so a copy of it is caught too. The search window is the page's own
    (app_model._jobs), and its rulings it reads itself. A "find 20 more" left 18 of 37 rows on
    the page that its own drafting then refused: US-based, an employer failing the bar, a copy
    of a role already drafted or applied for (the maintainer, 2026-11-05)."""
    import throttle
    from company_key import key as company_key
    from lookup_score import norm
    rules = hard_rules(_job_age_days(), today, seen=seen, tracker=tracker,
                       window=False, listed=False, drafts=False)
    by_url: dict = {}
    by_role: dict = {}

    def listed(row) -> str:
        u = norm(str(row.get("url") or ""))
        if u and u in by_url:
            return by_url[u]
        k = company_key(str(row.get("company") or ""))
        return next((why for role, why in by_role.get(k, ())
                     if throttle._same_title(row.get("title"), role)), "")

    def note(row, where: str = "") -> None:
        why = "already on your list" + (f", {where}" if where else "")
        u = norm(str(row.get("url") or ""))
        if u:
            by_url.setdefault(u, why)
        k = company_key(str(row.get("company") or ""))
        if k and str(row.get("title") or "").strip():
            by_role.setdefault(k, []).append((str(row.get("title")), why))

    def check(row) -> str:
        why = rules(row)
        if why.startswith("already ") and norm(str(row.get("url") or "")) in rules.had.links:
            # The job itself, under its own link: the page shows where it stands (drafted,
            # applied), never a copy of it to leave out.
            why = ""
        return why or listed(row)
    check.note = note
    check.had = rules.had
    return check


ANOTHER_ROLE = "another role at {} is already on your list"


def _fit_and_priority(row) -> tuple[float, float]:
    """A row's 0-100 fit (else its priority) and its priority, for which of two fits better."""
    def num(x):
        return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else -1.0
    fit = row.get("fit") if row.get("fit") is not None else row.get("priority")
    return num(fit), num(row.get("priority"))


def extra_roles(rows) -> dict[int, str]:
    """{index: why} for each row that is a second open role at an employer among `rows`, the
    roles on Jobs nobody has decided on, in list order: at each employer (company_key) the one
    that fits best stays, its fit, then its priority, then its place in the list, and every
    other is set aside as another role there already on the list. throttle.py keeps one
    role per employer inside one search; this is the same limit over the whole list, where
    three searches put three roles at one employer on it (the maintainer, 2026-11-05). The
    page decides it on every read (app_model._jobs), so a role set aside comes back by itself
    once the one kept is drafted, applied for or set aside."""
    from company_key import key as company_key
    best: dict[str, int] = {}
    for i, r in enumerate(rows):
        k = company_key(str(r.get("company") or ""))
        if not k:
            continue
        if k not in best or _fit_and_priority(r) > _fit_and_priority(rows[best[k]]):
            best[k] = i
    out = {}
    for i, r in enumerate(rows):
        k = company_key(str(r.get("company") or ""))
        if k and best[k] != i:
            kept = rows[best[k]]
            out[i] = ANOTHER_ROLE.format(str(kept.get("company") or r.get("company")).strip())
    return out


def ruled_by(row, why: str, links=()) -> bool:
    """Whether a reason a search leaves a row out for goes on its left-out list: a fact about
    the posting or its employer that the person's own rules decide. Never a row with no score
    or past the search window (decided again for free every round), a tap still waiting on
    the page (the page applies it), nor the person's own job under its own link (`links`,
    already_had's): only a copy of it."""
    from lookup_score import norm
    if not why or why.startswith(("no score", "age:", SET_ASIDE_ON_PAGE)):
        return False
    # A second role at an employer is decided again on every read of the list (extra_roles),
    # and comes back once the one kept is decided: never a ruling, nor another search's list.
    if why.startswith(ANOTHER_ROLE.split("{}")[0]) and why.endswith(ANOTHER_ROLE.split("{}")[1]):
        return False
    if why.startswith("already "):
        u = norm(str(row.get("url") or ""))
        return bool(u) and u not in set(links)
    return True


def rule_word(why: str) -> str:
    """The few words a reason is grouped under on the page's left-out list."""
    if why.startswith("already "):
        return "already on your list or applied for"
    if why.startswith("place:"):
        return "location"
    import filtered
    return filtered.rule_of("shortlist", why)


def record_left_out(rows, seen_path: str, today: str) -> list[dict]:
    """Each row a search left out for a ruling, written as one in the same step
    (exclude.add_many, basis rules: it lapses when the rule it rests on changes) with its
    plain reason, so neither the page nor the Brief counts it and a later round passes it over
    before fetching it. Never over a ruling already there, or a posting the person brought
    back: theirs stands. Never a copy of a job they have ("already ..."): the page leaves a
    copy out by the same rules on every read, and a ruling on the posting itself would set
    aside the job a chat is drafting. `rows` carry their `skip_reason`. The rows written."""
    import exclude
    from lookup_score import norm
    try:
        data = exclude.load_seen(seen_path)
    except (OSError, ValueError):
        data = {"seen": {}}
    taken = {norm(str(e.get("url") or k)) or k for k, e in (data.get("seen") or {}).items()
             if isinstance(e, dict) and str(e.get("status") or "").lower() in ("excluded", "lifted")}
    out, seen = [], set()
    for r in rows or ():
        u = norm(str(r.get("url") or ""))
        why = str(r.get("skip_reason") or "").strip()
        if not u or u in taken or u in seen or not why or why.startswith("already "):
            continue
        seen.add(u)
        out.append({"url": r["url"], "reason": str(r["skip_reason"]).strip(),
                    "title": str(r.get("title") or ""), "company": str(r.get("company") or ""),
                    "location": str(r.get("location") or "")})
    if out:
        exclude.add_many(out, today, path=seen_path)
    return out


# A left-out row keeps what the page needs to list it and, brought back, to show it again
# with its score (tools/filtered.py back).
LEFT_FIELDS = ("title", "company", "location", "url", "portal", "date", "fit", "priority")


def left_entries(rows, stage: str) -> list[dict]:
    """The rows a search left out, as entries of its left-out list (tools/filtered.py)."""
    out = []
    for r in rows or ():
        why = str(r.get("skip_reason") or "").strip()
        e = {k: r.get(k) for k in LEFT_FIELDS if r.get(k) not in (None, "")}
        e.update(stage=stage, rule=rule_word(why), reason=why[:240])
        out.append(e)
    return out


def say_left(gone) -> None:
    """The line a search says for the rows it took off the person's list."""
    if gone:
        print(f"left out: {len(gone)} that fail a rule, taken off your Jobs list with their "
              "reasons (each on this search's left-out list, where Bring back undoes it): "
              + "; ".join(f"{r.get('title') or '?'}, {r.get('company') or '?'} "
                          f"({r['skip_reason']})" for r in gone[:5]))


def leave_out(passed, summary_dir: str, name: str, seen_path: str, today: str,
              links=(), page: bool = True, record: bool = True) -> list[dict]:
    """A search's cut, taken off the page in the same step: the rows it passed over for a
    ruling (`passed`, write_summary's report) and, with `page`, every row from an earlier
    search still on the person's Jobs list that fails the same rules now (app_model.left_out,
    the page's own answer), each recorded as a ruling with its plain reason (record_left_out)
    and put on this search's left-out list, where Bring back undoes it (tools/filtered.py back).
    The rows taken off."""
    import filtered
    mine = [r for r in passed or () if ruled_by(r, str(r.get("skip_reason") or ""), links)]
    old = []
    if page and os.path.abspath(summary_dir) == os.path.abspath(person.state(SUMMARY_DIR)):
        try:
            import app_model
            day = datetime.date.fromisoformat(today)
            old = [dict(r, skip_reason=why) for rname, _rank, r, why in app_model.left_out(day)
                   if rname != name and ruled_by(r, why, links)]
        except Exception as e:  # noqa: BLE001  the page's list unreadable: this round's own
            print(f"warning: the jobs already on your list were not checked again ({e})",
                  file=sys.stderr)
    if record:
        record_left_out(mine + old, seen_path, today)
    filtered.add(summary_dir, name, left_entries(mine, "shortlist")
                 + left_entries(old, "your list"))
    return mine + old


# A search limited to employers the person names ("search these 20 employers"). The round
# could not do it: its shortlist was the overall top 10, so the page showed other companies
# too, and the maintainer filtered the 20 by hand from 06_shortlist.json (2026-11-06). The
# names are kept in the round's own folder, so a widening and a --recut keep to them.
NAMED_FILE = "employers.json"
NAMED_SCRAPE = os.path.join("00_scrape", "named.json")


def named_employers(given) -> list[str]:
    """The employers a search is limited to (--employers): names separated by commas,
    semicolons or new lines, or a file holding them, one a line or a JSON list (a round's
    own employers.json too). Each employer once, as the app matches employer names
    (company_key.key: "Acme Ltd" and "Acme" are one), in the order given."""
    from company_key import key as company_key
    text = str(given or "")
    names: list = []
    if text and os.path.isfile(text):
        with open(text, encoding="utf-8") as fh:
            body = fh.read()
        try:
            got = json.loads(body)
        except ValueError:
            got = None
        if isinstance(got, dict):
            got = got.get("named")
        names = ([str(n) for n in got] if isinstance(got, list)
                 else body.splitlines())
    else:
        names = re.split(r"[,;\n]+", text)
    out, seen = [], set()
    for n in names:
        n = " ".join(str(n).split()).strip(" -*\t")
        k = company_key(n) if n else ""
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def named_keys(names) -> dict[str, str]:
    """{employer key: the name as the person gave it}."""
    from company_key import key as company_key
    return {company_key(n): n for n in names or () if company_key(n)}


def at_named(rows, names) -> list[dict]:
    """The rows at one of the employers named, in their order."""
    from company_key import key as company_key
    keys = named_keys(names)
    return [r for r in rows or () if isinstance(r, dict)
            and company_key(str(r.get("company") or "")) in keys]


def read_named(out_dir: str) -> tuple[list[str], set | None]:
    """The employers a round was limited to and the keys of those it found postings at (None
    when it never said), from its own folder; ([], None) for an ordinary round."""
    path = os.path.join(out_dir, NAMED_FILE)
    if not os.path.isfile(path):
        return [], None
    try:
        got = _read_json(path)
    except Exception:  # noqa: BLE001  unreadable: read as names, one a line
        return named_employers(path), None
    names = named_employers(path)
    found = got.get("found") if isinstance(got, dict) else None
    return names, (set(named_keys(found)) if isinstance(found, list) else None)


def write_named(out_dir: str, names, found=None) -> str:
    """The round's own record of the employers it was limited to, and those it found
    postings at. Its path."""
    path = os.path.join(out_dir, NAMED_FILE)
    data: dict = {"named": list(names)}
    if found is not None:
        data["found"] = list(found)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return path


def named_room(show, names) -> int:
    """How many a search limited to named employers keeps: the number asked for, or one for
    each employer named when that is more, so every named employer with a posting that passes
    every rule has a place even past 10. The throttle keeps one role per employer, so that is
    every one of them; write_summary still adds a named employer's best row if the room is full
    of second roles."""
    return max(shown(show), len(names or ()))


def say_named(names, rows, found=None, jobage=None) -> list[str]:
    """The lines a search limited to named employers says about the ones with nothing on its
    list: no posting found there at all, or postings found and none passing the rules."""
    from company_key import key as company_key
    on = {company_key(str(r.get("company") or "")) for r in rows or () if isinstance(r, dict)}
    missing = [n for n in names or () if company_key(n) not in on]
    if not missing:
        return []
    window = f" in the last {jobage} days" if jobage else ""
    if found is None:
        return [f"No open roles on this list at {', '.join(missing)}."]
    none = [n for n in missing if company_key(n) not in found]
    cut = [n for n in missing if company_key(n) in found]
    lines = []
    if none:
        lines.append(f"No open roles found at {', '.join(none)}{window}.")
    if cut:
        lines.append(f"Open roles found at {', '.join(cut)}, but none that passes your rules.")
    return lines


def write_summary(shortlist_path, out_dir, name, scraped_path=None, show=None, rules=None,
                  report=None, links=None, named=None):
    """The compact shortlist, and where it was written. With `scraped_path` (the round's
    scrape), each kept row's apply link is checked against what the round read
    (link_checks), so a card says where to apply and whether it is still listed; `links`
    ({url: link fields}) carries a row's link fields from an earlier cut of the same round.

    With `rules` (hard_rules), the shortlist keeps taking the next ranked row that passes
    every hard rule until it has the number asked for or runs out. It took the first N and
    nothing after: a search asked for 10, rows failing a rule were cut from those 10, and 7
    came back with good rows left below them (2026-11-03). `report`, a dict, is given the
    number asked for, the number found and the rows passed over, with why.

    With `named` (the employers a search is limited to, --employers), only rows at those
    employers are taken, the rest left as they are (never a ruling: the person did not ask
    about them), and the room is named_room: the number asked for, or one for each employer
    named when that is more. Once it is full, a named employer with nothing on the list yet
    still gets its best row that passes, so none is left off for a second role elsewhere."""
    try:
        rows = _read_json(shortlist_path)
    except Exception:
        return None
    rows = rows if isinstance(rows, list) else list(rows.values())
    rows.sort(key=lambda r: -(r.get("priority") or 0))
    want = shown(show)
    keys = named_keys(named) if named else {}
    taken: set = set()
    if keys:
        from company_key import key as company_key
        want = named_room(show, named)
        rows = [r for r in rows if company_key(str(r.get("company") or "")) in keys]
    links = links or {}
    check = None
    if scraped_path:
        try:
            scraped = _read_json(scraped_path)
            scraped = scraped if isinstance(scraped, list) else list(scraped.values())
        except Exception:
            scraped = []
        check = link_checker(scraped, datetime.datetime.now(datetime.timezone.utc))
    kept, passed = [], []
    for r in rows:
        if len(kept) >= want:
            if not keys:
                break
            if company_key(str(r.get("company") or "")) in taken:
                continue
        why = rules(r) if rules else ""
        if why:
            passed.append({**r, "skip_reason": why})
            continue
        # Its apply link, checked as the cut reaches it: a posting its employer's board no
        # longer lists is passed over and the next taken. Checked after the cut, a closed
        # one held one of the ten places with nothing to apply to (2026-11-03).
        if r.get("url") in links:
            r = dict(r, **links[r.get("url")])
        elif check:
            r = check(r)
        if str(r.get("link_status") or "").lower() == "closed":
            passed.append({**r, "skip_reason": "closed: its employer's own board no longer "
                                               "lists it"})
            continue
        kept.append(r)
        if keys:
            taken.add(company_key(str(r.get("company") or "")))
    if report is not None:
        report.update(asked=want, found=len(kept), passed_over=passed)
    out = [{k: (pay_text(r) if k == "salary" else r.get(k)) for k in SUMMARY_FIELDS}
           for r in kept]
    out = [{k: v for k, v in r.items() if v not in (None, "")} for r in out]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.json" % name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
        rows = _read_json(path)
    except Exception:
        return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    out = [{k: v for k, v in r.items() if k != BODY_FIELD} if isinstance(r, dict) else r
           for r in rows]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
        rows = _read_json(path)
    except Exception:
        try:
            size = os.path.getsize(path)
            os.remove(path)
            return size
        except OSError:
            return 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows[:top], fh, indent=1)
        fh.write("\n")
    return max(0, before - os.path.getsize(path))


def prune(out_dir, keep=(), hold=(), top=KEEP_TOP):
    """Delete the stage files, keeping the round directory, its log, the shortlist and `keep`.

    The log is small, is already gitignored as `*.log`, and is the funnel
    record somebody reads when a round looks wrong. The shortlist is what a
    draft is staged from, cut to `top` rows (None: every one, for a search limited to
    named employers, which holds only theirs). Anything named in `keep` is slimmed rather
    than deleted, and anything in `hold` is left as it is, for the caller to delete later.
    The employers a search was limited to (NAMED_FILE) stay, for a --recut.
    """
    freed = 0
    for name in os.listdir(out_dir):
        if name in ("round.log", NAMED_FILE) or name in hold:
            continue
        path = os.path.join(out_dir, name)
        if name == SHORTLIST:
            freed += trim(path, top)
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
        rows = _read_json(path)
    except Exception:
        return 0, 0
    rows = rows if isinstance(rows, list) else list(rows.values())
    scores = [(r.get("fit") if r.get("fit") is not None else r.get("priority")) or 0
              for r in rows if isinstance(r, dict)]
    return sum(1 for s in scores if s >= 60), sum(1 for s in scores if s >= 75)


def count(path):
    try:
        d = _read_json(path)
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


# A round's name: "r" and its number, and "_round<k>" on a widening it started itself. The
# person's own tests read rounds by it, and a chat that had to give --out made one up: a
# search saved as "2026-11-04-app" failed them (2026-11-04).
ROUND_NAME = re.compile(r"^r\d+(?:_round\d+)?$")


def _names_on_github(summary_dir: str) -> list[str]:
    """The file names in the same folder on master and on every branch on GitHub that master
    does not hold yet (a job chat's work waiting there), as the last fetch saw them. Two job
    chats are two fresh clones, and each counted only its own folder: both named their search
    r43 (the maintainer's copy, 2026-11-06). Read from this copy's own git, never fetched
    here; [] where the folder is in no copy or git cannot say."""
    import subprocess

    def run(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", top, *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.SubprocessError):
            return ""
        return r.stdout if r.returncode == 0 else ""

    top = os.path.abspath(summary_dir)
    while top and not os.path.isdir(top):
        top = os.path.dirname(top)
    if not top:
        return []
    root = run("rev-parse", "--show-toplevel").strip()
    if not root:
        return []
    import local_path
    rel = local_path.rel(os.path.abspath(summary_dir), root)
    if rel.startswith("..") or os.path.isabs(rel):     # outside this copy, or another drive
        return []
    top = root
    refs = ["origin/master"] if run("rev-parse", "-q", "--verify", "origin/master") else []
    if refs:
        refs += [x.strip() for x in run("for-each-ref", "--format=%(refname:short)",
                                        "--no-merged", "origin/master",
                                        "refs/remotes/origin/").splitlines() if x.strip()][:200]
    names: list[str] = []
    for ref in refs:
        names += [os.path.basename(p) for p in run("ls-tree", "--name-only", ref, "--",
                                                   rel + "/").splitlines()]
    return names


def next_round(summary_dir: str) -> str:
    """The next round's name: "r" and one more than the highest number saved, here or on
    GitHub (_names_on_github), so a new round never overwrites an earlier one's shortlist."""
    try:
        names = os.listdir(summary_dir)
    except OSError:
        names = []
    names = list(names) + _names_on_github(summary_dir)
    nums = [int(m.group(1)) for n in names
            for m in [re.match(r"^r(\d+)(?:_round\d+)?\.json$", n)] if m]
    return f"r{max(nums, default=0) + 1}"


def name_round(out: str | None, summary_dir: str, chosen: bool) -> str:
    """Where the round's files go, its name chosen here. No --out: `rounds/<next>` beside
    the person's files. An --out for a round saved among the person's own (`chosen` false:
    no --summary-dir, not a widening) keeps its folder and takes the next name when its
    name is not a round's, or is one whose shortlist is saved already: `--out
    "$SCRATCH/r1"`, as the instructions once said, saved over the person's own r1."""
    if not out:
        return os.path.join(person.state("rounds"), next_round(summary_dir))
    out = round_dir(out)
    name = os.path.basename(out)
    if chosen or (ROUND_NAME.match(name)
                  and not os.path.isfile(os.path.join(summary_dir, name + ".json"))):
        return out
    return os.path.join(os.path.dirname(out), next_round(summary_dir))


def round_stamp(name: str, work: str = "") -> str:
    """The lines a round writes into its round.log as it starts: its name, and the page's
    work item it is for. tools/page_db.py search_unsaved reads them, so a search is done
    only once its own round's shortlist is saved, whatever the files' times say."""
    return f"round: {name}\n" + (f"work: {work}\n" if str(work or "").strip() else "")


def round_dir(out: str) -> str:
    """--out as this computer names a folder: separators of either kind, no trailing one.
    `--out rounds\\r1\\` on Windows kept its trailing backslash, so the round's name came
    out empty and its shortlist was saved as documents/rounds/.json."""
    if os.sep == "/":
        out = out.replace("\\", "/")
    return os.path.normpath(out)


def say_cut(report: dict, show) -> list[str]:
    """The lines a cut says: the rows passed over for a rule and, when the person asked for a
    number and the round ran out first, how many it found."""
    lines = []
    passed = report.get("passed_over") or []
    if passed:
        lines.append(f"shortlist: passed over {len(passed)} that fail a rule now, and took the "
                     "next instead: " + "; ".join(
                         f"{r.get('title') or '?'}, {r.get('company') or '?'} ({r['skip_reason']})"
                         for r in passed[:5]))
    if show and int(show) > 0 and report.get("found", 0) < report.get("asked", 0):
        lines.append(f"shortlist: found {report['found']} of the {report['asked']} asked for "
                     "that pass every rule; the round had no more")
    return lines


def targets(show, names) -> tuple[int, int]:
    """The yield a round is held to: (how many at 60 or more, how many at 75 or more)."""
    # A search asked for N widens until N score 60 or more: a top-up of ten starts on one page
    # of each site (the app skill) and stopped at five (2026-11-03).
    want, want_75 = max(YIELD_60, min(show or 0, 60)), YIELD_75
    if names:
        # One role per employer: a search of three employers can never show five.
        want, want_75 = min(want, len(names)), min(YIELD_75, len(names))
    return want, want_75


# The table the person is shown at the end of a search asked for in the chat (the job-scraper
# skill, Step 5), printed here with --table. The chat built it from the shortlist's JSON,
# about 10k tokens a search (the 4.12 cost audit); printed, it is passed on as it is.
TABLE_HEAD = ("| # | Score | Verdict | Title | Company | Location | Salary | Deadline | Check | Apply |\n"
              "|---|-------|---------|-------|---------|----------|--------|----------|-------|-------|")
# The framework's bands (04-job-evaluation.md, Thresholds; /rank step 2).
VERDICTS = ((75, "Strong fit"), (60, "Good fit"), (45, "Moderate fit"), (30, "Weak fit"))
# The notes a row carries, in the order Check gives them: who to ask first, then what is
# already running at the employer. Each as throttle.py wrote it.
CHECK_NOTES = ("warm_route_note", "referral_note", "outreach_pending_note",
               "silent_application_note", "drafted_note", "throttle_override_note")
# A screen's note about its own reading, not something the person checks.
THIN_BODY = "posting body too short"


def score_of(row) -> int | None:
    """The 0-100 score a row is shown with, as the page shows it: its fit, else its priority."""
    s = row.get("fit") if row.get("fit") is not None else row.get("priority")
    return round(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None


def verdict_of(score) -> str:
    if score is None:
        return ""
    return next((name for floor, name in VERDICTS if score >= floor), "Poor fit")


def _cell(text) -> str:
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _short(text: str) -> str:
    """A screen's flag to its first clause: the quote and the reasoning after it stay in the
    round's files."""
    text = " ".join(str(text or "").split())
    cuts = [i for i in (text.find("; "), text.find(". "), text.find(': "')) if i > 0]
    return text[:min(cuts)] if cuts else text


def check_of(row, more=None) -> str:
    """What to check before applying: the row's warm route and what is already running at
    the employer, then what the round read in the posting (a place it only flagged, a stated
    range under the target, years or a degree asked) and a tool asked for that the person
    holds one like."""
    more = more or {}
    said = [str(row[k]).strip() for k in CHECK_NOTES if str(row.get(k) or "").strip()]
    if str(more.get("location_verdict") or "").upper() == "FLAG":
        said.append("location: " + _short(more.get("location_reason") or "only flagged"))
    said += [_short(f) for f in more.get("flags") or []
             if isinstance(f, str) and f.strip() and not f.startswith(THIN_BODY)]
    said += [f"asked for {x.get('asked')}, you have {x.get('have')}"
             for x in row.get("near") or [] if isinstance(x, dict) and x.get("asked")]
    return "; ".join(s.rstrip(". ") for s in said) or "nothing flagged"


def _rounds(n: int) -> str:
    return f"{n} round" if n == 1 else f"{n} rounds"


def table(summary_path, out_dir=None, show=None, names=None, rounds=1) -> str:
    """The counts line and the ranked table for the person, as the job-scraper skill's Step 5
    sets it out, from the round's saved shortlist: highest score first (the round's own order
    between equal scores), each row's warm route in its Check, and no row under the pass bar.
    `out_dir` is the round's own folder, whose shortlist still holds each posting's deadline
    and what its screen flagged; without it those read as not stated. Reads only."""
    try:
        rows = _read_json(summary_path)
    except Exception:
        return ""
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    more: dict = {}
    if out_dir:
        try:
            got = _read_json(os.path.join(out_dir, SHORTLIST))
        except Exception:
            got = []
        for r in got if isinstance(got, list) else []:
            if isinstance(r, dict) and r.get("url"):
                more.setdefault(r["url"], r)
    good, strong = yield_of(summary_path)
    want, want_75 = targets(show, names)
    met = good >= want and strong >= want_75
    lines = [f"**{good} of {len(rows)} cleared the pass bar (60+), {strong} of them strong "
             f"(75+); target {want} and {want_75}: "
             + ("met" if met else f"missed after {_rounds(rounds)}") + "**"]
    shown_rows = sorted((r for r in rows if (score_of(r) or 0) >= 60),
                        key=lambda r: -(score_of(r) or 0))
    if shown_rows:
        import apply_link
        lines += ["", TABLE_HEAD]
        for n, r in enumerate(shown_rows, 1):
            extra = more.get(r.get("url")) or {}
            score = score_of(r)
            link = r.get("apply_url") or apply_link.clean(r.get("url") or "") or ""
            lines.append("| " + " | ".join(_cell(c) for c in (
                n, score, verdict_of(score), r.get("title"), r.get("company"),
                r.get("location"), r.get("salary") or "not stated",
                extra.get("deadline") or "not stated", check_of(r, extra))) + " | "
                + (f"[Apply]({link})" if link else "no link") + " |")
    below = len(rows) - len(shown_rows)
    if below:
        lines += ["", f"{below} more scored under 60 and are left off this table."]
    return "\n".join(lines)


def say_table(text: str) -> None:
    if text:
        print("\ntable for the person (pass it on as it is, nothing added to its rows):")
        print(text)


def recut(a) -> int:
    """--recut: the round's shortlist cut again, nothing searched. A ruling or a judgement
    made since the round ran (exclude.py add, bar.py judge) is a hard rule the cut now
    applies, so the rows it rules out are passed over and the next rows fill the shortlist
    back to the number asked for. Dropped from the table by hand, they left it short."""
    short = os.path.join(a.out, SHORTLIST)
    if not os.path.isfile(short):
        sys.exit(f"--recut: there is no shortlist at {short}. Point --out at the round's own "
                 "folder, the one it was run with.")
    name = os.path.basename(os.path.abspath(a.out))
    where = a.summary_dir or person.state(SUMMARY_DIR)
    try:
        before = _read_json(os.path.join(where, "%s.json" % name))
    except Exception:
        before = []
    links = {r["url"]: {k: r[k] for k in LINK_FIELDS if r.get(k)}
             for r in (before if isinstance(before, list) else [])
             if isinstance(r, dict) and r.get("url")}
    scraped = os.path.join(a.out, SCRAPED, "kept.json")
    report: dict = {}
    seen = a.seen or person.state("job_scraper", "seen_jobs.json")
    # The employers the round was limited to, kept in its folder, or named now: a recut with
    # --employers limits an ordinary round's list to them, and keeps to them after.
    names, found = read_named(a.out)
    if a.employers:
        given = named_employers(a.employers)
        if not given:
            sys.exit("--employers names no employer: give their names, separated by commas.")
        if named_keys(given) != named_keys(names):
            names, found = given, None
            write_named(a.out, names)
    rules = hard_rules(a.jobage, a.today, seen, a.no_seen_read, dump=a.dump, name=name,
                       tracker=a.tracker, own=links)
    path = write_summary(short, where, name,
                         scraped_path=scraped if os.path.isfile(scraped) else None,
                         show=a.show, rules=rules, report=report, links=links, named=names)
    for line in say_cut(report, None if names else a.show):
        print(line)
    if names and path:
        for line in say_named(names, _read_json(path), found, a.jobage):
            print(line)
    say_left(leave_out(report.get("passed_over"), where, name, seen, a.today,
                       links=rules.had.links, record=not a.no_seen_write))
    if path:
        print(f"shortlist summary: {local_path.rel(path, ROOT)} ({report.get('found', 0)} "
              "rows) - commit this one")
        if a.table:
            m = re.search(r"_round(\d+)$", name)
            say_table(table(path, a.out, a.show, names, int(m.group(1)) if m else 1))
    return 0


# The longest search window a person may set: a year. Anything longer is no window.
JOB_AGE_MAX = 365


def job_age_ok(days) -> bool:
    """Whether `days` is a search window a person may set: a whole number of days, 1 to a
    year. The page offers 7, 14 and 30, and a person may ask for any other in their own
    words: 10 written to search.py was read as 14, silently (2026-11-03)."""
    return isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= JOB_AGE_MAX


def _job_age_days() -> int:
    """How old a posting may be: the person's own search window (JOB_AGE_DAYS, any whole
    number of days from 1 to a year: 7, 14 and 30 on the page, any other asked for in
    words), else the app's rule of 14. A 10 they asked for was read as 14, silently, and an
    11-day-old posting came back as fresh (engine audit 25, jobs_brief 1, 2026-11-03)."""
    try:
        got = int(getattr(person.module("search"), "JOB_AGE_DAYS", 14) or 14)
    except Exception:  # noqa: BLE001  no profile here, or a value that is not a number
        return 14
    return got if job_age_ok(got) else 14


def main():
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = _Parser()
    ap.add_argument("--out", default=None,
                    help="directory for this round's files (default: rounds/r<next number>, "
                         "named by the round itself; leave it off)")
    ap.add_argument("--pages", type=int, default=None,
                    help="default 5 in the cloud and 2 on a person's own computer "
                         "(scrape_wide.defaults; SCRAPE_PAGES in profile/search.py)")
    ap.add_argument("--jobage", type=int, default=_job_age_days(),
                    help="hard freshness rule, days (profile/search.py JOB_AGE_DAYS, else 14)")
    ap.add_argument("--workers", type=int, default=None,
                    help="default 10 in the cloud and 4 on their own computer (SCRAPE_WORKERS)")
    ap.add_argument("--top", type=int, default=40, help="shortlist length shown")
    ap.add_argument("--show", type=int, default=None,
                    help="how many of the strongest the search brings back to the page (0: all, up to 60)")
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
    ap.add_argument("--work", default="",
                    help="the page's work item this search is for (its id): named in "
                         "round.log, so the page marks the search done only once this "
                         "round's shortlist is saved")
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
    ap.add_argument("--dump", default=None,
                    help="a page dump holding its actions and receipts, read when the "
                         "shortlist is cut: a job set aside on the page and not yet applied "
                         "is passed over and the next taken")
    ap.add_argument("--employers", default=None,
                    help="search only these employers, as the person named them: names "
                         "separated by commas (\"A, B, C\"), or a file holding them, one a "
                         "line. Their own boards and searches by their names are what is "
                         "searched; the shortlist holds only them, one place for each at "
                         "least, and says which had no open roles")
    ap.add_argument("--recut", action="store_true",
                    help="search nothing: cut the round in --out again, every hard rule "
                         "applied as it stands now (a ruling or a judgement made since), "
                         "refilled from the next rows to --show")
    ap.add_argument("--table", action="store_true",
                    help="end by printing the counts line and the ranked table for the person "
                         "(the job-scraper skill, Step 5), warm routes in its Check, to pass "
                         "on as it is; with --recut, the round's table again. Writes nothing "
                         "more: the round's files are the same with or without it")
    a = ap.parse_args()
    if a.recut:
        if not a.out:
            ap.error("--recut needs --out, the round's own folder")
        a.out = round_dir(a.out)
    else:
        given = a.out
        a.out = name_round(a.out, a.summary_dir or person.state(SUMMARY_DIR),
                           chosen=bool(a.summary_dir) or a.round > 1)
        if not given or os.path.basename(a.out) != os.path.basename(round_dir(given)):
            print(f"round: {os.path.basename(a.out)}, its files in {a.out}")
    # A line this round cannot print in the console's own encoding is printed with a
    # stand-in character, never raised: an accented employer name ended the round.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if a.recut:
        return recut(a)
    names: list = []
    if a.employers:
        names = named_employers(a.employers)
        if not names:
            ap.error("--employers names no employer: give their names, separated by commas")
    import scrape_wide
    pages, workers, _ = scrape_wide.defaults()
    a.pages = a.pages or pages
    a.workers = a.workers or workers
    os.makedirs(a.out, exist_ok=True)
    f = lambda n: os.path.join(a.out, n)
    log = open(f("round.log"), "a", encoding="utf-8", errors="replace", newline="\n")
    log.write(round_stamp(os.path.basename(os.path.abspath(a.out)), a.work))
    log.flush()
    if names:
        write_named(a.out, names)
        print(f"employers: this search is limited to the {len(names)} named: "
              + ", ".join(names))
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
                   + (["--before", a.scrape_before] if a.scrape_before else [])
                   # Aimed at the employers named: their own boards and searches by their
                   # names, never the whole search filtered afterwards.
                   + (["--employers-file", f(NAMED_FILE)] if names else []),
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
    # A search limited to named employers goes on with their postings alone, before anything
    # is fetched, screened or ranked: filtered first, then ranked and cut.
    stage_in = scraped
    if names:
        try:
            got = _read_json(scraped)
            got = got if isinstance(got, list) else list(got.values())
        except Exception:  # noqa: BLE001  no scrape to read: the prefilter says so
            got = []
        mine = at_named(got, names)
        stage_in = f(NAMED_SCRAPE)
        with open(stage_in, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(mine, fh, indent=1)
            fh.write("\n")
        here = set(named_keys([str(r.get("company") or "") for r in mine]))
        write_named(a.out, names, [n for n in names if n and named_keys([n]).keys() & here])
        print(f"employers: {len(mine)} of the {len(got)} postings found are at the employers "
              "named, and only those go on")

    # `--seen` is what stops hydrate paying for postings this search already
    # ruled out. The check is throttle.ruled_out() either way; running it here
    # rather than only at the end saves one HTTP call plus four free stages per
    # repeat, and on the 2,910 postings in seen_jobs 16% of everything reaching
    # hydrate was in that state.
    prefilter = [sys.executable, f"{T}/prefilter.py", stage_in, "--out", f("01_prefiltered.json"),
                 "--dropped", f("01_dropped.json"), "--jobage", str(a.jobage),
                 "--today", a.today]
    # Read even with --no-seen-read: it is also when each posting was first seen.
    prefilter += ["--seen", a.seen or person.state("job_scraper", "seen_jobs.json")]
    if a.no_seen_read:
        prefilter += ["--keep-ruled-out"]
    run(prefilter, log, deadline)
    # Hydrate AFTER the free gates: one HTTP call per survivor, none for the rest. It is
    # given the time its stage limit leaves, less a fetch's own time to finish, so it stops
    # and writes what it fetched before the limit kills it with nothing written.
    hydrate = [sys.executable, f"{T}/hydrate.py", f("01_prefiltered.json"), "--out", f(HYDRATED),
               "--workers", str(a.workers), "--require", a.require]
    room = _stage_budget(hydrate, deadline)
    run(hydrate + ["--budget", str(room - min(HYDRATE_MARGIN_SEC, room // 2))]
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

    # Write the keeper, then drop the rest. Done before the expansion branch
    # below returns, so every exit path leaves the same small footprint.
    cut: dict = {}
    seen_path = a.seen or person.state("job_scraper", "seen_jobs.json")
    rules = hard_rules(a.jobage, a.today, seen_path, a.no_seen_read, dump=a.dump,
                       name=os.path.basename(os.path.abspath(a.out)), tracker=a.tracker)
    summary = write_summary(f("06_shortlist.json"),
                            a.summary_dir or person.state(SUMMARY_DIR),
                            os.path.basename(os.path.abspath(a.out)), scraped_path=scraped,
                            show=a.show, rules=rules, report=cut, named=names)
    # Counted on the list the person is shown, after the hard rules cut it: counted on the
    # ranked rows before the cut, 60 and more of them, a round met its target with rows the
    # cut then dropped, and never widened (the release review, 2026-11-03).
    good, strong = yield_of(summary) if summary else (0, 0)
    want, want_75 = targets(a.show, names)
    met =good >= want and strong >= want_75
    print(f"yield: {good} scoring 60+ (target {want}), "
          f"{strong} scoring 75+ (target {want_75}) -> {'MET' if met else 'MISSED'}")
    if partial:
        print(f"warning: {partial}")
    for line in say_cut(cut, None if names else a.show):
        print(line)
    if names and summary:
        for line in say_named(names, _read_json(summary), read_named(a.out)[1], a.jobage):
            print(line)
    if summary:
        print(f"shortlist summary: {local_path.rel(summary, ROOT)} "
              f"(top {KEEP_TOP}, no posting bodies) - commit this one")
    # What the round filtered out and why, kept every round before the prune deletes the
    # stage files that say it (tools/filtered.py; `filtered.py back` brings one back).
    import filtered
    left_out = filtered.write(a.out, a.summary_dir or person.state(SUMMARY_DIR),
                              os.path.basename(os.path.abspath(a.out)))
    if left_out:
        print(f"filtered out: {local_path.rel(left_out, ROOT)} (each with its reason; "
              "tools/filtered.py back brings one back)")
    # What the cut ruled out, taken off the page in the same step: never left on Jobs as a
    # fresh find for a chat to clear by hand (2026-11-05).
    say_left(leave_out(cut.get("passed_over"), a.summary_dir or person.state(SUMMARY_DIR),
                       os.path.basename(os.path.abspath(a.out)), seen_path, a.today,
                       links=rules.had.links, record=not a.no_seen_write))
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
    if a.table and summary and not widen:
        # Read before the prune: the round's own shortlist holds each posting's deadline.
        # A round about to widen prints none; the widest one prints the table.
        say_table(table(summary, a.out, a.show, names, a.round))
    if not a.keep:
        # The shortlist survives every prune, for drafting. A round that missed
        # is also read for exactly the files the MISSED message below names, so
        # those survive with their posting bodies stripped. A round
        # about to widen holds its hydrated bodies back for the next one.
        freed = prune(a.out, keep=() if met else DIAGNOSTICS,
                      hold=(HYDRATED, SCRAPED) if widen else (),
                      top=None if names else KEEP_TOP)
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
            # The number asked for: without it a widened top-up of ten kept KEEP_TOP rows.
            + (["--show", str(a.show)] if a.show is not None else [])
            + (["--tracker", a.tracker] if a.tracker else [])
            + (["--seen", a.seen] if a.seen else [])
            + (["--no-seen-write"] if a.no_seen_write else [])
            + (["--no-seen-read"] if a.no_seen_read else [])
            + (["--table"] if a.table else [])
            + (["--employers", f(NAMED_FILE)] if names else []))
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
    print(f"  got {good} at 60+ and {strong} at 75+; wanted {want if names else YIELD_60} and {want_75}")

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
    if names:
        print("  this search was limited to the employers named, so it widens no further "
              "than their own boards and searches by their names; those with no open roles "
              "are named above. An employer with no board on file: "
              "tools/ats_boards.py --find \"<employer>\" finds one.")
    else:
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
