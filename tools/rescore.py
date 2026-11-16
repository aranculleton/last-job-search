#!/usr/bin/env python3
"""Score the jobs the page lists again, after how jobs are scored has changed.

Jobs keeps each earlier search's rows for CARRY_DAYS (app_model.carried), with the scores
they had when that search ran. A change to how jobs are scored, the person's own (employer
tiers, leverage, job families) or the app's, reached none of them, and nothing could: a
search kept the posting text of only the top 60 of its own working folder, which a new chat
does not have, so ranking a saved search again dropped every job its list held below those
60, with no word that it had (2026-11-16).

So a search keeps the posting text of every job its list holds (`keep`, called by
run_round.write_summary: documents/rounds/bodies/<round>.json, beside the lists, those jobs
only, and only while the page lists them, `prune`), and this scores those jobs again by the
round's own path: opportunity.score, then fit.blend, then the bar's verdict. Each row stays in
its place in its list, so a draft asked for by its rank still finds it, and each is scored as
of the day its search ran, so its age moves nothing: only the rules do.

    python3 tools/rescore.py            the page's jobs scored again, from their kept text
    python3 tools/rescore.py --fetch    and the text of any with none kept fetched, one
                                        request each
    python3 tools/rescore.py --check    why the page's jobs are due to be scored again, exit 1,
                                        or nothing, exit 0

The `jobs-rescored` profile upgrade runs it after every sync while `due()` says so: the
scoring has changed since the page's jobs were scored (`fingerprint`: the app's scoring code
and the person's own scoring settings), or a search's own folder on this computer holds text
not kept yet. A job whose text is kept nowhere keeps its score, and is counted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import person  # noqa: E402

BODIES = "bodies"
# What a score is worked out from, the app's half: a change to any of them may change a score,
# this file's own way of scoring again among them.
SCORING_FILES = ("opportunity.py", "fit.py", "text_screen.py", "prefilter.py", "places.py",
                 "bar.py", "sector.py", "company_key.py", "rescore.py")
# And the person's half: their scoring words, employer lists and places.
PROFILE_FILES = ("search.py", "employers.py", "place.json")
# Where a search's own folder keeps posting text, read in this order (run_round.prune keeps
# the shortlist; the rest only when kept for a closer look).
WORK_FILES = ("06_shortlist.json", "05_ranked.json", "04_opportunity.json", "03_screened.json",
              "02_hydrated.json")
# What scoring a job again changes on its row: the rest is what the search found.
SCORED = ("opportunity", "fit", "fit_why", "priority", "near", "bar", "bar_reason")


def summary_dir() -> str:
    return person.state("documents", "rounds")


def bodies_path(name: str, where: str | None = None) -> str:
    return os.path.join(where or summary_dir(), BODIES, f"{name}.json")


def _text(path: str) -> bytes:
    """A file's bytes with Windows line ends read as plain ones, so a copy on Windows and one
    in the cloud agree; b"" when there is none."""
    try:
        with open(path, "rb") as fh:
            return fh.read().replace(b"\r\n", b"\n")
    except OSError:
        return b""


def fingerprint() -> str:
    """How jobs are scored, as one short hash: the app's scoring code and the person's own
    scoring settings. Two copies of one app and one profile agree on it."""
    h = hashlib.sha1()
    for f in SCORING_FILES:
        h.update(f.encode() + b"\0" + _text(os.path.join(TOOLS, f)) + b"\0")
    for f in PROFILE_FILES:
        try:
            p = person.path(f)
        except person.NoProfile:
            p = ""
        h.update(f.encode() + b"\0" + (_text(p) if p else b"") + b"\0")
    return h.hexdigest()[:16]


def _norm(url) -> str:
    from lookup_score import norm
    return norm(str(url or "")) or ""


def read_kept(name: str, where: str | None = None) -> dict:
    """{"scored_with": <fingerprint>, "bodies": {link: text}} kept for a search, or {}."""
    try:
        with open(bodies_path(name, where), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _write(path: str, data, indent=None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def keep(where: str, name: str, rows: list[dict], scored_with: str | None = None) -> str:
    """Keep the posting text of each job in a search's list (`rows`, with their `desc`), beside
    the list, merged with what was kept for it before; the path written."""
    before = read_kept(name, where).get("bodies") or {}
    bodies = {}
    for r in rows:
        u = _norm(r.get("url"))
        d = r.get("desc")
        if u and isinstance(d, str) and d.strip():
            bodies[u] = d
        elif u and isinstance(before.get(u), str):
            bodies[u] = before[u]
    path = bodies_path(name, where)
    _write(path, {"scored_with": scored_with or fingerprint(), "bodies": bodies})
    return path


def listed(today: dt.date) -> list[str]:
    """The searches whose jobs the page lists today: the newest, then each earlier one it
    carries (app_model.carried)."""
    import app_model
    newest = app_model.newest_round()
    if not newest:
        return []
    names = [os.path.splitext(os.path.basename(newest))[0]]
    for rname, _rank, _row in app_model.carried(today, newest):
        if rname not in names:
            names.append(rname)
    return names


def _rows(name: str) -> list:
    try:
        with open(os.path.join(summary_dir(), f"{name}.json"), encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def _local_bodies(name: str, want: set) -> dict:
    """{link: text} for the links in `want`, from the search's own folder on this computer
    (rounds/<name>), where it still is."""
    work = person.state("rounds", name)
    out: dict = {}
    for f in WORK_FILES:
        if not want - out.keys():
            break
        try:
            with open(os.path.join(work, f), encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError):
            continue
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        for r in rows if isinstance(rows, list) else ():
            if not isinstance(r, dict) or r.get("hydrate_error"):
                continue
            u, d = _norm(r.get("url")), r.get("desc")
            if u in want and u not in out and isinstance(d, str) and d.strip():
                out[u] = d
    return out


def due(today: dt.date | None = None) -> str:
    """Why the page's jobs are due to be scored again, or "": a search on it was scored by
    other rules than today's, or this computer holds text of its jobs not kept yet."""
    try:
        names = listed(today or person.today())
        fp = fingerprint() if names else ""
    except Exception:  # noqa: BLE001  no profile or no searches: nothing to score
        return ""
    stale, here = 0, 0
    for name in names:
        rec = read_kept(name)
        if rec.get("scored_with") != fp:
            stale += 1
            continue
        kept = rec.get("bodies") or {}
        want = {_norm(r.get("url")) for r in _rows(name) if isinstance(r, dict)} - set(kept) - {""}
        if want and _local_bodies(name, want):
            here += 1
    if stale:
        return (f"{stale} of the searches on your page {'was' if stale == 1 else 'were'} "
                "scored before how jobs are scored last changed")
    if here:
        return "this computer holds the text of jobs on your page that is not kept yet"
    return ""


def _fetch(rows: list[dict]) -> dict:
    """{link: text} fetched from each posting's board, as a search fetches it."""
    import hydrate
    got = hydrate.hydrate_all([dict(r) for r in rows], workers=4, budget=10 * 60)
    out = {}
    for r in got:
        r = hydrate.guarded(r)
        d = r.get("desc")
        if not r.get("hydrate_error") and isinstance(d, str) and d.strip():
            out[_norm(r.get("url"))] = d
    return out


def _clean(row: dict) -> dict:
    """A row as a saved list keeps it (run_round.write_summary): nothing empty."""
    return {k: v for k, v in row.items() if v not in (None, "")}


def run(today: dt.date, fetch: bool = False) -> dict:
    """Score again every job the page lists whose text is kept (or found here, or with `fetch`
    fetched), each in its place; {"searches", "scored", "changed", "unread"}."""
    import app_model
    import bar
    import fit
    import opportunity
    fp = fingerprint()
    names = listed(today)
    done = {"searches": len(names), "scored": 0, "changed": 0, "unread": 0}
    for name in names:
        rows = _rows(name)
        if not rows:
            continue
        rec = read_kept(name)
        kept = {u: b for u, b in (rec.get("bodies") or {}).items() if isinstance(b, str)}
        links = [_norm(r.get("url")) if isinstance(r, dict) else "" for r in rows]
        want = {u for u in links if u} - kept.keys()
        if want:
            kept.update(_local_bodies(name, want))
        if fetch:
            missing = [r for r, u in zip(rows, links) if u and u not in kept]
            if missing:
                kept.update(_fetch(missing))
        day = app_model.round_day(os.path.join(summary_dir(), f"{name}.json")) or today
        todo = [(i, dict(r, desc=kept[u])) for i, (r, u) in enumerate(zip(rows, links))
                if u in kept]
        ranked = fit.blend([opportunity.score(j, day) for _, j in todo])
        out = list(rows)
        for (i, j), got in zip(todo, ranked):
            verdict, why = bar.verdict(got.get("company"), j.get("desc") or "")
            new = dict(rows[i])
            for k, v in zip(SCORED, (got.get("opportunity"), got.get("fit"), got.get("fit_why"),
                                     got.get("priority"), got.get("near"), verdict, why)):
                new[k] = v
            new = _clean(new)
            if new != rows[i]:
                out[i] = new
                done["changed"] += 1
            done["scored"] += 1
        done["unread"] += sum(1 for u in links if u and u not in kept)
        if out != rows:
            _write(os.path.join(summary_dir(), f"{name}.json"), out, indent=1)
        bodies = {u: kept[u] for u in links if u in kept}
        if rec.get("scored_with") != fp or (rec.get("bodies") or {}) != bodies:
            _write(bodies_path(name), {"scored_with": fp, "bodies": bodies})
    prune(names)
    return done


def prune(names, where: str | None = None) -> list[str]:
    """Take away the kept text of every search the page no longer lists (`names` are those it
    does): only while a job is on the page is its text kept. The files taken away."""
    if not names:
        return []
    d = os.path.join(where or summary_dir(), BODIES)
    try:
        files = os.listdir(d)
    except OSError:
        return []
    gone = []
    for f in files:
        if f.endswith(".json") and f[:-5] not in names:
            try:
                os.remove(os.path.join(d, f))
                gone.append(f)
            except OSError:
                pass
    return gone


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score the jobs on the page again.")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch the text of any job with none kept, one request each")
    ap.add_argument("--check", action="store_true",
                    help="say why the page's jobs are due to be scored again; exit 1 if so")
    ap.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    today = dt.date.fromisoformat(a.today) if a.today else person.today()
    if a.check:
        why = due(today)
        if why:
            print(why)
        return 1 if why else 0
    done = run(today, a.fetch)
    if not done["searches"]:
        print("No search on your page to score again.")
        return 0
    n = done["scored"]
    print(f"Scored again: {n} {'job' if n == 1 else 'jobs'} from {done['searches']} "
          f"{'search' if done['searches'] == 1 else 'searches'}, {done['changed']} changed.")
    if done["unread"]:
        u = done["unread"]
        print(f"{u} {'keeps its' if u == 1 else 'keep their'} score: the posting's text is not "
              "kept here. Run it again with --fetch to fetch "
              f"{'it' if u == 1 else 'them'} from the job sites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
