#!/usr/bin/env python3
"""Fetch a page a 403 refused to WebFetch, the way 09-web-research.md allows, and read it.

    python3 tools/fetch_page.py '<URL>' --text [--company <employer>]
    python3 tools/fetch_page.py '<URL>' --out "$SCRATCHPAD/page.html"

The retry it replaces was a documented `curl -L` with a browser's headers and an inline
tag-stripper, after `robots_check.py` had read the first address's policy. Two things were
wrong with that:

  - `-L` followed every redirect to wherever it led, another host included, and that
    host's own robots.txt was never read. This goes through the app's one fetcher of an
    employer's pages (`company_research._Run.page`): each address, the first and every
    redirect, has its host's robots.txt read first (a Content-Signal ai-input=no refusing
    too), a redirect is followed only to a web address, a host is asked no faster than its
    crawl delay, the employer's daily request budget is shared with research, a bot check
    is told from the page, and LinkedIn is never fetched.
  - the stripper kept the words of every element, a hidden one's too: a sentence styled
    display:none, which no reader of the page ever sees, reached the chat as the page's.
    `--text` reads it through the app's one rule for what a page hides
    (`hydrate.strip_hidden`, openroles' `html_to_text`, then `hydrate.clean_body` for the
    invisible characters), and prints it inside the untrusted-data fence (`untrusted.fence`).

Only GET, with no cookies, no form and no body. Nothing is written into the repo: `--out`
goes to the scratchpad. Adapted from ai-job-search's tools/fetch_page.py (#642, #680, #690,
#764).

Exit 0 fetched, 1 refused (robots.txt, LinkedIn, this chat's own cloud settings) and nothing
asked of that address, 2 a usage error, 3 the site answered with an error, a bot check, or
could not be reached.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CHARS = 6000


class Refused(Exception):
    """robots.txt, LinkedIn or this chat's own settings said no; nothing was asked of it.
    `url` is the address it stopped at, after any redirects."""

    def __init__(self, message: str, url: str = ""):
        super().__init__(message)
        self.url = url


class Failed(Exception):
    """The site answered with an error or a bot check, or could not be reached."""


# What a web page is sent as. A PDF, an image or a download printed its raw bytes, control
# characters included, inside the fence as if they were the page's words.
_PAGE_TYPE = re.compile(r"^\s*(?:text/[\w.+-]+|[\w.+-]+/(?:[\w.-]+\+)?(?:html|xml|json))\s*(?:;|$)",
                        re.I)


def not_a_page(kind: str, body: str) -> str:
    """Why a response is not a web page to read, or "": sent as something other than text,
    HTML, XML or JSON, or holding a zero byte, which no page's text has."""
    if kind and not _PAGE_TYPE.match(kind):
        return f"not a web page ({kind.split(';')[0].strip()})"
    if "\x00" in body:
        return "not a web page (it holds binary data)"
    return ""


def fetch(url: str, company: str | None = None, run=None) -> tuple:
    """(the final address, the Content-Type, the page) through company_research's fetcher,
    the employer's budget counted under `company` (the host when none is named). A response
    that is not a web page (`not_a_page`) is Failed."""
    import company_research as cr
    if run is None:
        run = cr._Run(company or urlsplit(url).hostname or url, cr._today(None), None, None,
                      None, None, cr.FETCH_BUDGET)
    state, why, resp = run.page(url)
    if state in ("refused", "disallowed"):
        at = (resp or {}).get("url") or url
        raise Refused(f"{at}: {why}", at)
    if state != "ok":
        raise Failed(f"{url}: {state}, {why}")
    kind = (resp.get("headers") or {}).get("content-type", "")
    body = resp.get("body") or ""
    other = not_a_page(kind, body)
    if other:
        raise Failed(f"{resp['url']}: {other}")
    return resp["url"], kind, body


def visible_text(markup: str) -> tuple:
    """(the words a reader of the page sees, {what was taken out: how many})."""
    import hydrate
    from openroles.models import html_to_text
    shown, found = hydrate.strip_hidden(markup)
    text, more = hydrate.clean_body(html_to_text(shown))
    for what, n in more.items():
        found[what] = found.get(what, 0) + n
    return text or "", found


def _in_repo(path: str) -> bool:
    here = os.path.realpath(path)
    return here == ROOT or here.startswith(ROOT + os.sep)


def main(argv=None, run=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url")
    ap.add_argument("--out", help="save the page's HTML here (the scratchpad, never the repo)")
    ap.add_argument("--text", action="store_true", help="print the words a reader sees, fenced")
    ap.add_argument("--company", help="the employer whose daily request budget it counts in")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS,
                    help="with --text, print at most this many characters (0: all)")
    a = ap.parse_args(argv)
    if not (a.out or a.text):
        ap.error("say --text, --out <file> or both")
    if a.out and _in_repo(a.out):
        print(f"fetch_page: --out {a.out}: write to the scratchpad, never into the repo",
              file=sys.stderr)
        return 2
    try:
        final, _kind, markup = fetch(a.url, a.company, run)
    except Refused as e:
        print(f"REFUSED - {e}")
        if "could not be read" in str(e):
            import robots_check
            said = robots_check.cloud_block(e.url or a.url)
            if said:
                print("BLOCKED BY THIS CHAT'S CLOUD SETTINGS - tell the person, in these "
                      "words:\n" + said)
        return 1
    except Failed as e:
        print(f"FAILED - {e}")
        return 3
    print(f"HTTP 200 {final}")
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(markup)
    if a.text:
        import hydrate
        import untrusted
        text, found = visible_text(markup)
        cut = bool(a.max_chars) and len(text) > a.max_chars
        if found:
            print(hydrate.said(found))
        print(untrusted.fence(text[:a.max_chars] if cut else text,
                              label=f"web page ({urlsplit(final).hostname})"))
        if cut:
            print(f"(cut at {a.max_chars} of {len(text)} characters; --max-chars 0 for all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
