#!/usr/bin/env python3
"""What the Claude app and Claude Code can do, and how a person reaches each part: one
registry, dated and sourced, so the app's words cannot drift from the product.

The Claude app changes faster than any document that describes it. Every statement the
app makes about a surface (a chat on the computer, a cloud chat, a phone, the browser
pane, a scheduled task) lives in tools/claude_surfaces.json with the official page it
rests on, a quote from that page, the day it was checked and what it was checked
against. Messages take their words from here; docs carry them in marked blocks; a test
fails on a statement outside it; and an entry older than `stale_after_days` says so
every time it is used, so a session re-checks the page before relying on it.

    python3 tools/claude_surfaces.py check               # stale entries, as warnings (exit 0)
    python3 tools/claude_surfaces.py show <id>           # one entry, its sources and its age
    python3 tools/claude_surfaces.py say <id> [--name N] [--owner O]   # the words a person sees
    python3 tools/claude_surfaces.py sync-docs           # rewrite every marked block from here
    python3 tools/claude_surfaces.py watch [--strict]    # the maintainer's: quotes still on
                                                         # their pages? a newer release?

A person-facing path is written the one way the app allows: the goal first, then the
destination "at the time of writing", then the official page. It never tells anyone to
press, click, tap or find something, because those words name a screen that moves.
`watch` runs only in the app (.github/workflows/claude-surfaces-watch.yml), never in a
person's repo.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "tools", "claude_surfaces.json")
# The words that name a screen, which moves: never in a path a person follows. "Find" is
# only one of them when it sends the person looking ("find the setting"), never in the
# words they say to Claude ("find me people at ...").
BANNED = re.compile(r"\b(?:press(?:es)?|clicks?|taps?|shortcut|keystroke|finds?(?! me\b))\b",
                    re.I)
# A block names its entry, and "claim" after the id carries the claim rather than the path.
BLOCK = re.compile(r"^([ \t]*)<!-- claude-surface: ([a-z0-9-]+(?: claim)?) -->\n(.*?)\n[ \t]*"
                   r"<!-- /claude-surface -->", re.S | re.M)
# The docs a person reads, which carry the registry's words in marked blocks. Claude's
# own instructions point at an entry by id instead (`show <id>`).
DOCS = ("START_HERE.md", "README.md", "SETUP.md", "automation/README.md")
UA = {"User-Agent": "last-job-search-surfaces-watch/1 (+https://github.com/aranculleton/last-job-search)"}

_CACHE: dict = {}


def load(path: str = PATH) -> dict:
    if path not in _CACHE:
        with open(path, encoding="utf-8") as fh:
            _CACHE[path] = json.load(fh)
    return _CACHE[path]


def entry(eid: str, reg: dict | None = None) -> dict:
    for e in (reg or load())["entries"]:
        if e["id"] == eid:
            return e
    raise KeyError(f"claude_surfaces: no entry {eid!r}")


def official(e: dict) -> str:
    """The first official page an entry rests on: never a skill or an observation."""
    return next((s["url"] for s in e.get("sources", ()) if s["url"].startswith("http")), "")


def age(e: dict, today: datetime.date | None = None) -> int:
    return ((today or datetime.date.today()) - datetime.date.fromisoformat(e["verified_on"])).days


def stale(reg: dict | None = None, today: datetime.date | None = None) -> list:
    reg = reg or load()
    limit = int(reg.get("stale_after_days", 60))
    return [(e, age(e, today)) for e in reg["entries"] if age(e, today) > limit]


def warning(e: dict, today: datetime.date | None = None, reg: dict | None = None) -> str:
    """For Claude, never the person: "" while the entry is fresh."""
    limit = int((reg or load()).get("stale_after_days", 60))
    n = age(e, today)
    if n <= limit:
        return ""
    pages = ", ".join(s["url"] for s in e.get("sources", ()) if s["url"].startswith("http"))
    return (f"[claude_surfaces: {e['id']!r} was checked {e['verified_on']}, {n} days ago: "
            f"re-check {pages or 'its source'} before relying on it, then update "
            "tools/claude_surfaces.json]")


def say(eid: str, name: str = "your copy", owner: str = "", today=None, reg=None,
        goal: bool = True) -> str:
    """The words a person sees: the goal, the destination at the time of writing, the page.
    goal=False leaves the goal out, for a sentence that has already said it."""
    e = entry(eid, reg)
    fill = {"name": name, "owner": owner or "<you>"}
    how = e.get("how", "").format(**fill)
    goal = e.get("goal", "") if goal else ""
    if not how:
        return ""
    page = official(e)
    head = (goal[:1].upper() + goal[1:] + ". ") if goal else ""
    return f"{head}At the time of writing: {how}" + (f" (official page: {page})." if page else ".")


def vocabulary(reg=None) -> list:
    """The phrases only the registry may carry: the names of screens and the claims that
    move when the product does. Matched as whole words, case as written."""
    return list((reg or load()).get("vocabulary", ()))


def mentions(text: str, reg=None) -> list:
    """(phrase, offset) for each vocabulary phrase in `text`, whole words only."""
    out = []
    for ph in vocabulary(reg):
        for m in re.finditer(r"(?<![\w/])" + re.escape(ph) + r"(?![\w])", text):
            out.append((ph, m.start()))
    return out


def render(eid: str, reg=None) -> str:
    """An entry as a doc block carries it, for a reader who is not in a chat: the path,
    or the claim for "<id> claim" and for an entry with no path."""
    want_claim = eid.endswith(" claim")
    e = entry(eid.split()[0], reg)
    text = "" if want_claim else say(e["id"], name="of your copy", owner="you", reg=reg)
    return f"{text or e['claim']} Checked {e['verified_on']}."


def block(eid: str, indent: str = "", reg=None, width: int = 92) -> str:
    """A marked block as a doc carries it: the rendered entry, wrapped, at `indent`."""
    import textwrap
    body = textwrap.fill(render(eid, reg), width=width, initial_indent=indent,
                         subsequent_indent=indent, break_long_words=False, break_on_hyphens=False)
    return f"{indent}<!-- claude-surface: {eid} -->\n{body}\n{indent}<!-- /claude-surface -->"



def blocks(text: str) -> list:
    """(id, indent, the block as written) for each marked block in a doc."""
    return [(m.group(2), m.group(1), m.group(0)) for m in BLOCK.finditer(text)]


def sync_docs(root: str = ROOT, reg=None) -> list:
    """Rewrite every marked block in DOCS from the registry; the files it changed."""
    changed = []
    for rel in DOCS:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        text = open(p, encoding="utf-8").read()
        new = BLOCK.sub(lambda m: block(m.group(2), m.group(1), reg), text)
        if new != text:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(new)
            changed.append(rel)
    return changed


# ------------------------------------------------------------------ the watch

def normalise(text: str) -> str:
    t = html.unescape(text).replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"').replace(" ", " ")
    t = " ".join(t.split())
    t = re.sub(r"\s+([,.;:!?)])", r"\1", t)
    return re.sub(r"\(\s+", "(", t).lower()


def page_text(url: str, fetch=None) -> str:
    """The page's words, normalised the same way whether it came from the network or a test."""
    if fetch:
        t = fetch(url)
    else:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    return normalise(re.sub(r"<[^>]+>", " ", t))


def _version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def watch(reg: dict | None = None, fetch=None, today=None) -> list:
    """What needs a maintainer's look: (entry id or "release", why). Fetches only the
    official pages the registry names; a skill or an observation is reported as
    unwatchable once, never fetched."""
    reg = reg or load()
    out, pages = [], {}
    for e in reg["entries"]:
        for s in e.get("sources", ()):
            url = s["url"]
            if not url.startswith("http"):
                continue
            try:
                if url not in pages:
                    pages[url] = page_text(url, fetch)
            except Exception as exc:  # noqa: BLE001  a page that will not load is a finding
                out.append((e["id"], f"{url} did not load ({exc})"))
                pages[url] = None
                continue
            if pages[url] is not None and normalise(s["quote"]) not in pages[url]:
                out.append((e["id"], f"the quote is no longer on {url}: {s['quote']!r}"))
    for e, n in stale(reg, today):
        out.append((e["id"], f"checked {e['verified_on']}, {n} days ago"))
    notes = reg.get("release_notes", "")
    if notes:
        try:
            text = page_text(notes, fetch)
            # The page lists its releases newest first, after "On this page": the first
            # release number there is the newest. A number anywhere else on the page (an
            # address, a dependency) is not a release.
            at = text.find("on this page")
            m = re.search(r"(?<![\d.])([0-9]\.\d{1,3}\.\d{1,4})(?![\d]|\.\d)",
                          text[at:] if at >= 0 else text)
            newest = m.group(1) if m else ""
            if newest and _version(newest) > _version(reg.get("checked_version", "0.0.0")):
                ids = ", ".join(e["id"] for e in reg["entries"] if e.get("ui_sensitive"))
                out.append(("release", f"Claude Code {newest} is out (checked against "
                            f"{reg.get('checked_version')}): review the paths in {ids}"))
        except Exception as exc:  # noqa: BLE001
            out.append(("release", f"{notes} did not load ({exc})"))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("check", "show", "say", "sync-docs", "watch"):
        print(__doc__.split("\n\n")[2])
        return 2
    cmd, rest = argv[0], argv[1:]
    opt = {k: rest[rest.index(k) + 1] for k in ("--name", "--owner") if k in rest}
    if cmd == "check":
        old = stale()
        for e, _n in old:
            print(warning(e))
        print(f"claude_surfaces: {len(load()['entries'])} entries, {len(old)} stale")
        return 0
    if cmd == "show":
        e = entry(rest[0])
        print(f"{e['id']} ({e['status']}, checked {e['verified_on']} against "
              f"{e['verified_against']}, {age(e)} days ago)\n  {e['claim']}")
        for s in e.get("sources", ()):
            print(f"  source: {s['url']}\n    \"{s['quote']}\"")
        if e.get("how"):
            print(f"  say: {say(e['id'], **{k[2:]: v for k, v in opt.items()})}")
        w = warning(e)
        if w:
            print(w)
        return 0
    if cmd == "say":
        e = entry(rest[0])
        print(say(rest[0], **{k[2:]: v for k, v in opt.items()}))
        w = warning(e)
        if w:
            print(w, file=sys.stderr)
        return 0
    if cmd == "sync-docs":
        changed = sync_docs()
        print("claude_surfaces: " + (f"rewrote {', '.join(changed)}" if changed else "docs match"))
        return 0
    found = watch()
    for eid, why in found:
        print(f"  {eid}: {why}")
    print(f"claude_surfaces watch: {len(found)} to review")
    return 1 if found and "--strict" in rest else 0


if __name__ == "__main__":
    sys.exit(main())
