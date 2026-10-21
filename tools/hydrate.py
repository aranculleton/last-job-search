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
import html
import json
import os
import re
import subprocess  # noqa: F401  tests stand in for subprocess.run through this module
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


def paced_done(skill: str, clock=time.monotonic) -> None:
    """A paced fetch has ended: the board's next request waits its crawl-delay from now,
    as the scrape's sweep waits after each request. Spaced only start to start, a fetch
    slower than the delay had the next one sent while it was still running."""
    with _PACE_GUARD:
        got = _PACE.get(skill)
    if got:
        lock, times = got
        with lock:
            times[0] = clock()


# Requirements sit at the END of a posting. A 9,000-character cap cut the
# requirements off bodies in a round, which is exactly the text the screen and
# the scorers read.
#
# The one cap on a posting's body, wherever it is read: the scrape (freehire and a
# person's own boards), the employer boards (tools/ats_boards.py), job alerts and the
# detail fetch here. freehire and person-board bodies used to arrive uncapped, so the
# text screen read words that fit and opportunity, which stop at this many, never saw.
BODY_CAP = 20_000


# ------------------------------------------------------------- what no reader sees
#
# A posting is third-party text, read next to the person's own data. A sentence a
# browser never shows (an element styled display:none, a comment, a script) or that
# renders as nothing at all (zero-width and bidi control characters, and the Unicode
# tag characters U+E0000-U+E007F, a second alphabet a model reads as ASCII and a
# person cannot see) is a channel to whoever reads the text next, and never a fact
# about the job. So it is taken out here, before the screen or anyone else reads the
# body. What is seen is left exactly as it was: no whitespace is folded, no markup a
# reader sees is touched, and a body with none of these comes back unchanged.
#
# The character sets, the hidden-style rules and the element walk are adapted from
# tools/posting_guard.py in MadsLorentzen/ai-job-search (MIT; its notice is in this
# repo's LICENSE), which reports these and returns visible text; this keeps the markup
# and cuts only what is hidden.
ZERO_WIDTH = "\u200b\u200c\u200d\u2060\u2061\u2062\u2063\u2064"
BIDI = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
SOFT_HYPHEN, BOM = "\u00ad", "\ufeff"
TAG_CHARS = "".join(chr(c) for c in range(0xE0000, 0xE0080))
_INVISIBLE = {ord(c): None for c in ZERO_WIDTH + BIDI + SOFT_HYPHEN + BOM + TAG_CHARS}
# The one use of tag characters a posting may have: the England, Scotland and Wales
# flags, kept whole.
_TAG_FLAG = re.compile("\U0001F3F4\U000E0067\U000E0062(?:\U000E0065\U000E006E\U000E0067"
                       "|\U000E0073\U000E0063\U000E0074|\U000E0077\U000E006C\U000E0073)"
                       "\U000E007F")
_INVISIBLE_ANY = re.compile("[%s]" % re.escape(ZERO_WIDTH + BIDI + SOFT_HYPHEN + BOM)
                            + "|[\U000E0000-\U000E007F]")

# Markup worth walking: a body that carries none of these elements is plain text.
_LOOKS_HTML = re.compile(r"<\s*/?\s*(?:p|div|span|li|ul|ol|br|h[1-6]|section|table|tr|td|"
                         r"strong|em|b|i|u|a|font|small|body|html|article|header|footer)\b",
                         re.I)
_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_DROP_BLOCKS = re.compile(r"<(script|style|noscript|svg|template)\b[^>]*>.*?(?:</\1\s*>|\Z)",
                          re.I | re.S)
_TAG = re.compile(r"<(/?)([a-zA-Z][\w:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
_ATTR = re.compile(r"([^\s=/\"'>]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>\"']+)))?")
_VOID = {"br", "img", "input", "meta", "link", "hr", "wbr", "source", "area", "base", "col",
         "embed", "param", "track"}
_BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section",
          "article", "header", "footer", "table", "thead", "tbody", "blockquote", "pre", "dd",
          "dt", "dl", "nav", "main", "aside", "figure", "form", "fieldset", "legend",
          "address", "hr", "td", "th", "option"}
_IMPLIED_END = {"p", "li", "dd", "dt", "tr", "td", "th", "option"}
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d]*[1-9])"
    r"|font-size\s*:\s*0(?:\.0+)?(?:px|pt|em|rem|%)?(?![\d.])|color\s*:\s*transparent"
    r"|clip\s*:\s*rect\(\s*0|clip-path\s*:\s*inset\(\s*100%"
    r"|(?:left|top|text-indent)\s*:\s*-\d{4,}px", re.I)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_COLLAPSED = re.compile(r"\b(?:max-)?(?:height|width)\s*:\s*0(?:\.0+)?(?:px|em|rem|%|pt)?(?![\d.])",
                        re.I)
_CLIPPED = re.compile(r"\boverflow(?:-[xy])?\s*:\s*hidden\b", re.I)


def _is_hidden(raw_attrs: str) -> bool:
    attrs = {}
    for m in _ATTR.finditer(raw_attrs):
        value = next((g for g in m.groups()[1:] if g is not None), "")
        attrs[m.group(1).lower()] = value
    if "hidden" in attrs or attrs.get("aria-hidden", "").strip().lower() == "true":
        return True
    # The style as a browser reads it: entities decoded, CSS comments gone.
    style = _CSS_COMMENT.sub("", html.unescape(attrs.get("style", "")))
    return bool(_HIDDEN_STYLE.search(style)
                or (_COLLAPSED.search(style) and _CLIPPED.search(style)))


def _hidden_spans(markup: str) -> list[tuple[int, int]]:
    """Where the hidden elements are: each from its opening tag to the end of its
    closing one, or to the sibling that closes it, or to the end, as a browser reads it."""
    spans, stack = [], []
    hidden_at, began = None, 0

    def pop_to(index, end):
        nonlocal hidden_at
        del stack[index:]
        if hidden_at is not None and hidden_at >= len(stack):
            spans.append((began, end))
            hidden_at = None

    for m in _TAG.finditer(markup):
        closing, name = m.group(1), m.group(2).lower()
        if closing:
            index = next((i for i in range(len(stack) - 1, -1, -1) if stack[i] == name), None)
            if index is not None:
                pop_to(index, m.end())
            continue
        if name in _VOID:
            continue
        if name in _IMPLIED_END and stack and stack[-1] == name:
            pop_to(len(stack) - 1, m.start())
        elif name in _BLOCK and stack and stack[-1] == "p":
            pop_to(len(stack) - 1, m.start())
        stack.append(name)
        if hidden_at is None and _is_hidden(m.group(3)):
            hidden_at, began = len(stack) - 1, m.start()
    if hidden_at is not None:
        spans.append((began, len(markup)))
    return spans


def clean_body(text: str | None) -> tuple[str | None, dict]:
    """(the body without what no reader sees, {what was taken out: how much}).

    Hidden elements, comments and script or style blocks where the body is markup;
    zero-width and bidi control characters, soft hyphens and the byte-order mark; and
    Unicode tag characters other than a whole England, Scotland or Wales flag. A body
    with none of them is returned as it came."""
    if not isinstance(text, str) or not text:
        return text, {}
    found: dict[str, int] = {}
    out = text
    if _LOOKS_HTML.search(out) or "<!--" in out:
        n = 0
        for rx in (_COMMENT, _DROP_BLOCKS):
            out, k = rx.subn("", out)
            n += k
        if n:
            found["comments and scripts"] = n
        spans = _hidden_spans(out)
        if spans:
            found["hidden elements"] = len(spans)
            for start, end in reversed(spans):
                out = out[:start] + out[end:]
    if _INVISIBLE_ANY.search(out):
        pieces, last = [], 0
        for m in _TAG_FLAG.finditer(out):
            pieces.append(out[last:m.start()].translate(_INVISIBLE))
            pieces.append(m.group(0))
            last = m.end()
        pieces.append(out[last:].translate(_INVISIBLE))
        cleaned = "".join(pieces)
        tags = sum(1 for ch in _TAG_FLAG.sub("", out) if "\U000E0000" <= ch <= "\U000E007F")
        if tags:
            found["tag characters"] = tags
        others = len(out) - len(cleaned) - tags
        if others:
            found["invisible characters"] = others
        out = cleaned
    return out, found


def guarded(job: dict) -> dict:
    """The posting with clean_body applied to its body, and what was taken out said
    in `posting_guard`, so a body that changed can be told from one that did not."""
    if not isinstance(job, dict):
        return job
    body, found = clean_body(job.get("desc"))
    if not found:
        return job
    said = ", ".join(f"{n} {what}" for what, n in found.items())
    return {**job, "desc": body, "posting_guard": f"removed from the body: {said}"}


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


def _no_body(d: dict) -> bool:
    return not (d.get("description") or d.get("descriptionText"))


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
        # portals.run_cli, the runner every portal call goes through: stdout to a
        # file, not a pipe (a body cut at 64 KiB mid-string, with exit 0, under
        # this module's workers), and a board's refusal (THROTTLED, robots.txt)
        # kept wherever it falls in stderr, where only the last line was kept.
        try:
            d, err = portals.run_cli(
                ["node", "--no-warnings", cli, "detail", str(ident), "--format", "json"],
                timeout=timeout, empty=_no_body)
        finally:
            paced_done(skill)
        if err:
            return {**job, "hydrate_error": f"detail {err}"}
        if not isinstance(d, dict):
            return {**job, "hydrate_error": "detail returned no posting"}
        body = d.get("description") or d.get("descriptionText") or ""
        if not body.strip():
            return {**job, "hydrate_error": "detail returned an empty description"}
        return {**job, "desc": body[:BODY_CAP]}
    except Exception as e:  # timeout, bad JSON, missing node: all recorded, none fatal
        return {**job, "hydrate_error": f"{type(e).__name__}: {str(e)[:160]}"}


def cached_bodies(path: str | None) -> dict[str, str]:
    """{normalised URL: body} from an earlier round's hydrated file, or {}.

    A widened round (run_round.py --expand) searches deeper and finds mostly the
    postings the round before it already fetched. Their bodies are reused rather
    than fetched again; a body that stood in for a failed fetch is not.
    """
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        from lookup_score import norm
    except (OSError, ValueError, ImportError):
        return {}
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    out = {}
    for r in rows if isinstance(rows, list) else ():
        if not isinstance(r, dict) or r.get("hydrate_error"):
            continue
        n = norm(r.get("url") or "")
        if n and (r.get("desc") or "").strip():
            out[n] = r["desc"]
    return out


def paced_portal(job: dict) -> str | None:
    """The portal a posting's fetch waits a crawl-delay for, or None: a posting that
    already has its body, or one from a portal with no crawl-delay (the app's two)."""
    if (job.get("desc") or "").strip():
        return None
    portal = job.get("portal") or ""
    if portal in CLI:
        return None
    skill = portals.skill_of(portal)
    return skill if skill and portals.crawl_delay(skill) else None


# A line this often while the stage runs, so a slow stage is told from a hung one.
PROGRESS_SECONDS = 60


def hydrate_all(jobs: list[dict], workers: int = 10, progress_every: float | None = None,
                say=None) -> list[dict]:
    """Every posting through `fetch`, written in the order it arrived.

    They were written in the order the fetches finished, and the stages after this
    break a full tie on that order: fit.py's sort keeps it, and the throttle keeps the
    first of two tied roles at one employer. So two runs over the same postings could
    rank tied postings differently, and keep a different one of a tied pair. A posting
    whose worker failed keeps its place, unfetched, so hydration never loses one.

    A board with a crawl-delay has a worker of its own. Its postings used to queue in
    the shared pool with everyone else's, and a worker that took one waited out the
    delay holding its place: the board's postings arrive last from the scrape, so the
    stage ended as one board's chain of five-second waits with every worker in it. They
    now wait in their own queue while the rest are fetched, one request at a time and a
    crawl-delay after the last one ended (`pace`, `paced_done`), as the scrape's sweep
    sends them: with as many workers as the shared pool, a fetch slower than the delay
    had the next request to the board sent while it was still running."""
    workers = max(1, workers)
    every = PROGRESS_SECONDS if progress_every is None else progress_every
    say = say or (lambda line: print(line, file=sys.stderr, flush=True))
    lanes: dict = {}
    by_portal: dict = {}                     # each portal's SKILL.md read once, not per row
    for i, job in enumerate(jobs):
        try:
            key = None if (job.get("desc") or "").strip() else (job.get("portal") or "")
            if key is not None and key not in by_portal:
                by_portal[key] = paced_portal(job)
            lane = by_portal.get(key)
        except Exception:                    # a row that cannot be read goes the usual way
            lane = None
        lanes.setdefault(lane, []).append(i)

    lock = threading.Lock()
    done = {lane: 0 for lane in lanes}
    failed = [0]

    def finished(lane, fut):
        with lock:
            done[lane] += 1
            try:
                failed[0] += bool(fut.result().get("hydrate_error"))
            except Exception:
                failed[0] += 1

    def line() -> str:
        with lock:
            total = sum(done.values())
            bits = [f"progress: hydrate {total}/{len(jobs)} done, {failed[0]} failed"]
            for lane in sorted(k for k in lanes if k):
                if done[lane] < len(lanes[lane]):
                    bits.append(f"{portals.short(lane)} {done[lane]}/{len(lanes[lane])}, "
                                f"{portals.crawl_delay(lane):g}s apart")
        return "; ".join(bits)

    stop = threading.Event()

    def ticker():
        while not stop.wait(every):
            say(line())

    pools = {lane: ThreadPoolExecutor(max_workers=1 if lane else workers) for lane in lanes}
    futs: list = [None] * len(jobs)
    tick = threading.Thread(target=ticker, daemon=True)
    tick.start()
    try:
        # The paced boards first, so their chains start at once.
        for lane in sorted(lanes, key=lambda k: (k is None, k or "")):
            for i in lanes[lane]:
                fut = pools[lane].submit(fetch, jobs[i])
                fut.add_done_callback(functools.partial(finished, lane))
                futs[i] = fut
        out: list[dict] = []
        for job, f in zip(jobs, futs):
            try:
                got = f.result()
            except Exception as e:
                print(f"worker error: {e}", file=sys.stderr)
                got = job
            # Before anything reads it: what no reader of the posting sees is taken out.
            out.append(guarded(got))
    finally:
        stop.set()
        for ex in pools.values():
            ex.shutdown(wait=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--require", type=float, default=None,
                    help="fail if the fraction with a description is below this")
    ap.add_argument("--cache", default=None,
                    help="an earlier round's hydrated file: its bodies are reused, not fetched")
    a = ap.parse_args()

    data = json.load(open(a.infile))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)
    cache = cached_bodies(a.cache)
    reused = 0
    if cache:
        from lookup_score import norm
        for i, j in enumerate(jobs):
            body = cache.get(norm(j.get("url") or "") or "")
            if body and not (j.get("desc") or "").strip():
                jobs[i] = {**j, "desc": body}
                reused += 1
    before = sum(1 for j in jobs if (j.get("desc") or "").strip())
    out = hydrate_all(jobs, a.workers)

    after = sum(1 for j in out if (j.get("desc") or "").strip())
    errors = [j for j in out if j.get("hydrate_error")]
    guarded_n = sum(1 for j in out if j.get("posting_guard"))
    json.dump(out, open(a.out, "w"), indent=1)
    frac = after / len(out) if out else 0.0
    print(f"{len(out)} postings: {before} had a description"
          + (f" ({reused} from the round before)" if reused else "")
          + f", {after} now do ({frac:.0%}); {len(errors)} fetch errors", file=sys.stderr)
    if errors:
        from collections import Counter
        for reason, n in Counter(j["hydrate_error"][:60] for j in errors).most_common(5):
            print(f"  {n:4d}  {reason}", file=sys.stderr)
    if guarded_n:
        print(f"{guarded_n} posting(s) carried text no reader sees (hidden markup, invisible "
              "characters); it was taken out before the screen, and each says what in "
              "posting_guard", file=sys.stderr)
    # Nothing to fetch is not a failed fetch. A round in which nothing survived the free
    # gates (every site blocked from the cloud, say) read 0 of 0 as 0% and ended here as a
    # broken stage, before it could say which portals were down and the person's fix.
    if a.require is not None and out and frac < a.require:
        print(f"FAIL: only {frac:.0%} have a description, below the required "
              f"{a.require:.0%}. Every posting without one reaches the model "
              f"blind and cannot be screened, knocked out or extracted.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
