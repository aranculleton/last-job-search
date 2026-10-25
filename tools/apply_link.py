#!/usr/bin/env python3
"""The link a person clicks, checked right before a card shows it.

    python3 tools/apply_link.py <url> [--company <employer> --title <role>]
    python3 tools/apply_link.py --file <rows.json> [--write]

A posting's link reached the person as the board gave it: tracking on the end, sometimes
wrapped in a redirect, sometimes a page that asks them to sign in or a site that only
lists other sites' jobs, and never checked as still open. `shown()` is what a card shows:

- the link with the parts that say where the click came from taken off (utm_*, refId,
  trackingId, trk and the rest of lookup_score.norm's list), every part that names the
  job kept, so the posting's key (lookup_score.norm) is the same before and after; the
  link as it came is kept as `url_seen`;
- a redirect that carries its target in the link itself unwrapped (Google's /url?q=,
  LinkedIn's /redir/redirect?url= and /safety/go?url=, Outlook's safe links, Facebook's
  l.php?u=, Slack's link?url=), only to a web address: the shapes the ClearURLs rules
  unwrap (https://gitlab.com/ClearURLs/rules, merge request 88 for LinkedIn's). Nothing
  is fetched to unwrap one;
- what kind of page it is (`link_kind`): LinkedIn, a sign-in wall, a site that lists
  other sites' jobs, an employer's hiring system, or the employer's own site;
- where the employer's board is on file (profile/boards.py, read through
  tools/ats_boards.py and openroles), the posting found on it by its own link or by
  title, stored as `apply_url` with "checked <date> <time>"; a posting from that board
  that is no longer listed is "closed". Each board is read once however many cards ask.

LinkedIn is never fetched: a LinkedIn link is kept as it is and says "not checked". A
check that cannot be made says why, and never says "closed": a false "closed" throws a
live posting away, where a false "open" costs one look (tools/still_open.py's rule).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lookup_score import _ATS_ID_PARAM, _TRACKING, norm  # noqa: E402

# Parts of a query that name the job, kept even where the tracking list would take them:
# lookup_score's own job ids, LinkedIn's id on a search page and Indeed's job key.
_KEEP = frozenset(_ATS_ID_PARAM) | {"currentjobid", "jk", "vjk"}

# (host, path) of a redirect, and the parameter that holds where it goes.
_WRAPPERS = (
    (re.compile(r"(?:^|\.)google\.[a-z.]{2,6}$"), re.compile(r"^/url$"), ("q", "url")),
    (re.compile(r"(?:^|\.)linkedin\.com$"), re.compile(r"^/(?:redir/redirect|safety/go)/?$"), ("url",)),
    (re.compile(r"(?:^|\.)safelinks\.protection\.outlook\.com$"), re.compile(r"^/?$"), ("url",)),
    (re.compile(r"^l\.facebook\.com$"), re.compile(r"^/l\.php$"), ("u",)),
    (re.compile(r"^slack-redir\.net$"), re.compile(r"^/link$"), ("url",)),
)

# Sites whose posting page asks the person to sign in before it shows the way to apply.
LOGIN_WALLS = re.compile(
    r"(?:^|\.)(?:glassdoor\.[a-z.]{2,6}|wellfound\.com|angel\.co|welcometothejungle\.com|"
    r"otta\.com|hired\.com|joinhandshake\.com|builtin\.com|builtin[a-z]+\.(?:com|org))$")
# Sites that list other sites' jobs, so the employer's own listing is a click further on.
AGGREGATORS = re.compile(
    r"(?:^|\.)(?:indeed\.[a-z.]{2,6}|ziprecruiter\.[a-z.]{2,6}|simplyhired\.[a-z.]{2,6}|"
    r"jooble\.org|adzuna\.[a-z.]{2,6}|talent\.com|monster\.[a-z.]{2,6}|careerjet\.[a-z.]{2,6}|"
    r"eluta\.ca|jobrapido\.com|freehire\.me)$")
# Hiring systems an employer's jobs are posted on (openroles reads most of them).
BOARD_HOSTS = re.compile(
    r"(?:^|\.)(?:greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|myworkdaysite\.com|"
    r"workable\.com|smartrecruiters\.com|teamtailor\.com|jobs\.personio\.[a-z.]{2,6}|"
    r"recruitee\.com|bamboohr\.com|jobvite\.com|icims\.com|taleo\.net|oraclecloud\.com|"
    r"successfactors\.[a-z.]{2,6}|rippling\.com|polymer\.co|gem\.com|homerun\.co|"
    r"applytojob\.com|careers-page\.com|clearcompany\.com)$")

KINDS = {"linkedin": "LinkedIn", "login wall": "asks you to sign in",
         "aggregator": "lists other sites' jobs", "board": "the employer's hiring system",
         "employer": "the employer's own site", "": "no link"}


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def unwrap(url):
    """The address a redirect in `url` goes to, read from the link itself; `url` otherwise."""
    if not isinstance(url, str) or not url.strip():
        return url
    u = url.strip()
    for _ in range(3):                     # a wrapped wrapper, never a loop
        try:
            parts = urlsplit(u)
        except ValueError:
            return u
        host, path = (parts.hostname or "").lower(), parts.path or "/"
        target = None
        for host_rx, path_rx, names in _WRAPPERS:
            if host_rx.search(host) and path_rx.search(path):
                q = dict((k.lower(), v) for k, v in parse_qsl(parts.query, keep_blank_values=True))
                target = next((q[n] for n in names if q.get(n)), None)
                break
        if not target:
            return u
        target = unquote(target) if re.match(r"^https?%3A", target, re.I) else target
        if not re.match(r"^https?://", target, re.I):
            return u                       # only to a web address (ClearURLs MR 89)
        u = target
    return u


def clean(url):
    """`url` without the query parts that say where the click came from.

    Hand-split, so every part kept is kept exactly as it was written, and the posting's key
    (lookup_score.norm) does not move: only what norm already ignores is taken off."""
    if not isinstance(url, str) or "?" not in url:
        return url.strip() if isinstance(url, str) else url
    u = url.strip()
    head, _, rest = u.partition("?")
    query, hash_, fragment = rest.partition("#")
    kept = []
    for part in query.split("&"):
        if not part:
            continue
        name = part.partition("=")[0].strip()
        if name.lower() in _KEEP or not _TRACKING.match(name):
            kept.append(part)
    return head + ("?" + "&".join(kept) if kept else "") + (hash_ + fragment if hash_ else "")


def kind(url) -> str:
    """What the page at `url` is: linkedin, login wall, aggregator, board or employer."""
    host = _host(url) if isinstance(url, str) else ""
    if not host:
        return ""
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    if LOGIN_WALLS.search(host):
        return "login wall"
    if AGGREGATORS.search(host):
        return "aggregator"
    if BOARD_HOSTS.search(host):
        return "board"
    return "employer"


def _stamp(now) -> str:
    return (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")


def board_for(company):
    """(employer as boards.py names it, kind, token) of the employer's board on file, or None."""
    try:
        import ats_boards
        from company_key import key as company_key
    except Exception:                                          # noqa: BLE001
        return None
    want = company_key(company or "")
    if not want:
        return None
    for employer, (board_kind, token) in ats_boards.BOARDS.items():
        if company_key(employer) == want:
            return employer, board_kind, token
    return None


# Read one board a check: careers sites are read page by page at the pace their robots.txt
# asks, minutes a site, which is a round's work and never a card's.
UNCHECKABLE = frozenset({"careersite"})


def _read_board(employer: str, board_kind: str, token: str):
    """(rows, why it returned none) of one board, the way a round reads it."""
    import ats_boards
    return ats_boards.FETCH[board_kind](employer, token)


def _board_named(url) -> tuple | None:
    """(system, token lower-cased) of the employer board a link is on, as openroles reads
    a board's address, or None for a link that names none."""
    try:
        from openroles.discover import parse
        board = parse(str(url or ""))
    except Exception:                                          # noqa: BLE001
        return None
    return (board.ats, str(board.token).lower()) if board else None


class Checker:
    """Checks links against the employers' boards, each board read once."""

    def __init__(self, now=None, read=None, boards=None):
        self.now = now
        self.read = read or _read_board
        self.boards = boards            # {employer: (kind, token)}, or None for boards.py
        self._listings: dict = {}

    def _board(self, company):
        if self.boards is None:
            return board_for(company)
        from company_key import key as company_key
        want = company_key(company or "")
        for employer, (board_kind, token) in self.boards.items():
            if want and company_key(employer) == want:
                return employer, board_kind, token
        return None

    def _listing(self, employer, board_kind, token):
        at = (board_kind, token)
        if at not in self._listings:
            try:
                got = self.read(employer, board_kind, token)
            except Exception as exc:                          # noqa: BLE001
                got = ([], f"{type(exc).__name__}: {exc}")
            rows, err = got if isinstance(got, tuple) else (got, None)
            # (rows, why none, whether the listing is whole): a board that answered with a
            # note left postings out (a body that would not fetch), so none is "closed".
            self._listings[at] = (list(rows or []), None if rows else (err or "nothing listed"),
                                  not err)
        return self._listings[at]

    def shown(self, row: dict) -> dict:
        """`row` as a card shows it: url, url_seen, link_kind, apply_url, link_status, link_check."""
        seen = row.get("url_seen") or row.get("url")
        url = clean(unwrap(seen)) if isinstance(seen, str) else seen
        k = kind(url)
        out = dict(row, url=url, link_kind=k, link_status="unknown")
        if isinstance(seen, str) and url != seen.strip():
            out["url_seen"] = seen
        board = self._board(row.get("company"))
        title = row.get("title") or ""
        tail = ""
        if k == "linkedin":
            tail = "; the LinkedIn link is not checked: LinkedIn is never fetched"
        if not board or board[1] in UNCHECKABLE:
            out["link_check"] = {
                "linkedin": "not checked: LinkedIn is never fetched",
                "login wall": f"not checked: {_host(url)} asks you to sign in; the employer's "
                              "own listing is the one to use",
                "aggregator": f"not checked: {_host(url)} lists other sites' jobs; the "
                              "employer's own listing is the one to use",
                "": "no link",
            }.get(k, "not checked")
            return out
        employer, board_kind, token = board
        listing, err, whole = self._listing(employer, board_kind, token)
        stamp = _stamp(self.now)
        if err:
            out["link_check"] = f"not checked: {employer}'s own board did not answer ({err}){tail}"
            return out
        key = norm(url) if isinstance(url, str) else None
        own = [r for r in listing if key and norm(r.get("url")) == key]
        if own:
            out.update(apply_url=clean(own[0].get("url")), link_status="open",
                       link_check=f"open on {employer}'s own board, checked {stamp}")
            return out
        from throttle import same_title
        # Closed only where the posting was this board's own (its link names the board, or
        # a round read it from a board of this kind and the link names none) and the whole
        # listing no longer has it. The token was looked for anywhere in the link, so a
        # posting on a sibling board ("acmeuk" beside "acme") read as closed.
        named = _board_named(url)
        if whole and (named == (board_kind, str(token).lower()) if named
                      else row.get("portal") == board_kind):
            out.update(link_status="closed",
                       link_check=f"closed: no longer on {employer}'s own board, checked {stamp}")
            return out
        matches = [r for r in listing if same_title(r.get("title"), title)]
        if len(matches) > 1:
            here = [r for r in matches if str(r.get("location") or "").lower()
                    == str(row.get("location") or "").lower()]
            matches = here if len(here) == 1 else matches
        if len(matches) == 1:
            out.update(apply_url=clean(matches[0].get("url")), link_status="open",
                       link_check=f"open on {employer}'s own board (matched by title), "
                                  f"checked {stamp}")
        elif matches:
            out["link_check"] = (f"{len(matches)} roles of that title on {employer}'s own "
                                 f"board, checked {stamp}{tail}")
        else:
            out["link_check"] = (f"not on {employer}'s own board by that title, checked "
                                 f"{stamp}{tail}")
        return out


def shown(row: dict, now=None, read=None, boards=None) -> dict:
    """One row as a card shows it (Checker.shown), for a caller with one card."""
    return Checker(now=now, read=read, boards=boards).shown(row)


def shown_all(rows: list[dict], now=None, read=None, boards=None) -> list[dict]:
    """Every row as a card shows it, each employer's board read once."""
    c = Checker(now=now, read=read, boards=boards)
    return [c.shown(r) if isinstance(r, dict) else r for r in rows]


def line(row: dict) -> str:
    """The one line a card or a chat prints under the role."""
    link = row.get("apply_url") or row.get("url") or "no link"
    return f"{link} ({row.get('link_check') or 'not checked'})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The link a person clicks, checked before it is "
                                             "shown.")
    ap.add_argument("url", nargs="?", help="one posting's link")
    ap.add_argument("--company", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--file", help="a JSON list of rows (a round's shortlist, apps_in.json)")
    ap.add_argument("--write", action="store_true", help="write the checked rows back to --file")
    a = ap.parse_args(argv)
    if not a.url and not a.file:
        ap.print_usage()
        print("apply_link: give a link, or --file with a list of rows.")
        return 2
    if a.file:
        try:
            with open(a.file, encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"apply_link: cannot read {a.file}: {e}")
            return 2
        if isinstance(rows, dict) and isinstance(rows.get("rows"), list):
            doc, rows = rows, rows["rows"]
        else:
            doc = None
        if not isinstance(rows, list):
            print(f"apply_link: {a.file} holds no list of rows.")
            return 2
        out = shown_all(rows)
        for r in out:
            if isinstance(r, dict):
                print(f"{r.get('company', '')} | {r.get('title', '')}: {line(r)}")
        if a.write:
            with open(a.file, "w", encoding="utf-8") as fh:
                json.dump(dict(doc, rows=out) if doc is not None else out, fh, indent=1,
                          ensure_ascii=False)
        return 0
    r = shown({"url": a.url, "company": a.company, "title": a.title})
    print(line(r))
    if r.get("url_seen"):
        print(f"as it came: {r['url_seen']}")
    print(f"kind: {KINDS.get(r['link_kind'], r['link_kind'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
