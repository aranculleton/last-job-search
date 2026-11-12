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
    python3 tools/claude_surfaces.py say <id> [--name N] [--owner O] [--system S]   # the words a person sees
    python3 tools/claude_surfaces.py steps <id> [--name N] [--owner O] [--system S] # its steps, for a person who said yes
    python3 tools/claude_surfaces.py sync-docs           # rewrite every marked block from here
    python3 tools/claude_surfaces.py watch [--strict]    # the maintainer's: quotes still on
                                                         # their pages? a newer release?

A person-facing path is written the one way the app allows: the goal first, then the
destination, or numbered steps one action a line. It never tells anyone to press, click, tap
or find something, because those words name a screen that moves. The day an entry was
checked and its official page are for Claude, never the person (`source`, which `say` and
`steps` print on stderr, and a comment in a doc's block): "At the time of writing (checked
2026-10-20; official page: https://...)" headed every step a beginner was given, six times
in one page of START_HERE, and nobody it was for could use it (2026-10-25). A doc's steps end
on one line instead, CLOSING.

Where a screen differs between a Mac, Windows and Linux (the key that shows Claude's browser,
the menu that updates the app, Linux's terminal), an entry has one variant a system, with an
id of its own (`<id>-mac`, `<id>-windows`, `<id>-linux`), and the entry itself says all three
in one short line for when the computer is not known. `for_system` picks the variant from what
the computer reports (sys.platform there, as its heartbeat carries it: darwin, win32, linux);
`steps` and `say` take `system`, and the command takes `--system` (on the person's computer it
defaults to that computer's own, in a cloud chat to all three). Every step a Mac was given
named Cmd+Shift+B first and Windows second, and nothing said what Linux takes (2026-11-11).

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
# An empty block is allowed and filled: with the body's line required, an empty block's
# match ran on to the next block's end and the sync wrote one over the other (2026-10-20).
BLOCK = re.compile(r"^([ \t]*)<!-- claude-surface: ([a-z0-9-]+(?: claim)?) -->\n(.*?)\n?[ \t]*"
                   r"<!-- /claude-surface -->", re.S | re.M)
# The docs a person reads, which carry the registry's words in marked blocks. Claude's
# own instructions point at an entry by id instead (`show <id>`).
DOCS = ("START_HERE.md", "README.md", "HELP.md", "SETUP.md", "automation/README.md")
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


# The systems a person's computer reports (sys.platform there) and the suffix of each one's
# variant of an entry.
SYSTEMS = {"darwin": "mac", "win32": "windows", "linux": "linux"}
# The words for each, in what Claude is told (never the person: they know their computer).
SYSTEM_NAMES = {"darwin": "a Mac", "win32": "Windows", "linux": "Linux"}


def system_of(value) -> str:
    """"darwin", "win32" or "linux" for what a computer reported (sys.platform, or a word a
    list of computers carries: "macOS", "Windows", "Linux"), else "" where it says none of
    them. Windows' own shells (cygwin, msys) are Windows."""
    v = str(value or "").strip().lower()
    if not v:
        return ""
    if v in ("darwin", "mac", "macos", "osx", "mac os", "mac os x") or v.startswith("darwin"):
        return "darwin"
    if v.startswith(("win", "cygwin", "msys", "mingw")):
        return "win32"
    if v.startswith("linux"):
        return "linux"
    return ""


def this_system(platform: str | None = None, release: str | None = None) -> str:
    """The system whose Claude app this computer runs: sys.platform, except inside WSL, where
    Python says linux but the app on screen is the Windows one (code.claude.com/docs/en/
    desktop-linux: on Windows with WSL 2, the Windows desktop app is used), so its keys and
    menus are Windows'."""
    import platform as _p
    plat = sys.platform if platform is None else platform
    got = system_of(plat)
    if got == "linux":
        rel = _p.release() if release is None else release
        if "microsoft" in str(rel).lower():
            return "win32"
    return got


def here_system(env=None) -> str:
    """This computer's system where this chat runs on the person's computer, else "": a cloud
    chat runs on Linux in a container of its own, and its sys.platform says nothing about the
    person's computer."""
    try:
        import place
        if place.in_cloud(env):
            return ""
    except Exception:  # noqa: BLE001  no place module here: judged by the documented marker
        e = os.environ if env is None else env
        if str(e.get("CLAUDE_CODE_REMOTE", "")).lower() == "true":
            return ""
    return this_system()


def for_system(eid: str, system: str = "", reg: dict | None = None) -> str:
    """The id of `eid`'s variant for `system` (darwin, win32, linux, or any word system_of
    reads), where the registry has one; else `eid` itself, which says all three."""
    suffix = SYSTEMS.get(system_of(system))
    if not suffix:
        return eid
    want = f"{eid}-{suffix}"
    return want if any(e["id"] == want for e in (reg or load())["entries"]) else eid


def official(e: dict) -> str:
    """The official page for an entry: its own `official_page` where its sources are not
    the product's own pages (LinkedIn's help, which no session fetches), else the first
    page it rests on, never a skill or an observation."""
    return e.get("official_page") or next(
        (s["url"] for s in e.get("sources", ()) if s["url"].startswith("http")), "")


# Said once where a doc or a message ends on a path through another company's screens:
# the date and the page are Claude's, and the person is told what to do when a screen moved.
CLOSING = "Screens change; tell me if yours looks different."
# The same in a doc, which is read away from any chat.
CLOSING_DOC = "Screens change: if yours looks different, tell Claude what you see."


def _fill(text: str, name: str = "your copy", owner: str = "") -> str:
    owner = owner or "<you>"
    copy = f"github.com/{owner}/{name}" if owner != "<you>" else "your copy's address on GitHub"
    return text.format(name=name, owner=owner, copy=copy)


def _goal(e: dict) -> str:
    g = e.get("goal", "")
    return g[:1].upper() + g[1:] if g else ""


def source(eid: str, reg=None, system: str = "") -> str:
    """For Claude, never the person: the day an entry was checked and the page to check it
    against that day before passing it on (CLAUDE.md, "A step on another company's site")."""
    e = entry(for_system(eid, system, reg), reg)
    page = official(e)
    return (f"[claude_surfaces: {e['id']!r} checked {e['verified_on']}"
            + (f"; official page: {page}" if page else "") + "; check it today before giving it]")


def steps(eid: str, reg=None, today=None, name: str = "your copy", owner: str = "",
          page: bool = False, system: str = "") -> list:
    """An entry's steps for a person who said yes, one action a line, headed by what they are
    for: never shown before they asked. An entry with a path and no steps gives its path as
    the one step, and one with neither its claim: `steps` on eight entries printed only a
    dated header and nothing to do (2026-10-25).

    The person's lines only. The day it was checked and its page (`source`), and past
    `stale_after_days` the line telling Claude to re-check it (`warning`, `notes`), come
    apart from them: inside them, every message that passes steps on word for word carried
    a file path or a date, and grew past its length the day the entry aged.

    `system` (darwin, win32, linux) gives that computer's own variant where the entry has one
    (for_system); "" gives the entry, which says all three."""
    e = entry(for_system(eid, system, reg), reg)
    # On the page there is no "this chat": an entry used on a card carries steps worded for
    # it (`page_steps`, the helper chat named, Done being the card's own button).
    use_page = page and e.get("page_steps")
    goal = e.get("page_goal", "") if use_page else e.get("goal", "")
    body = [_fill(x, name, owner) for x in (e["page_steps"] if use_page else e.get("steps", ()))]
    if not body and e.get("how"):
        how = _fill(e["how"], name, owner)
        body = [how[:1].upper() + how[1:].rstrip(".") + "."]
    if not body:
        return [e["claim"]]
    return ([f"To {goal}:"] if goal else []) + [f"{i}. {x}" for i, x in enumerate(body, 1)]


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


def notes(*eids: str, today=None, reg=None) -> list:
    """The lines for Claude, never the person, for the entries a message drew on: one per
    entry past `stale_after_days`, none while they are fresh."""
    return [w for w in (warning(entry(eid, reg), today, reg) for eid in dict.fromkeys(eids))
            if w]


def say(eid: str, name: str = "your copy", owner: str = "", today=None, reg=None,
        goal: bool = True, system: str = "") -> str:
    """The words a person sees: the goal, then the destination, in one sentence. goal=False
    leaves the goal out, for a sentence that has already said it. The date and the official
    page are Claude's (`source`). `system`: as `steps` takes it."""
    e = entry(for_system(eid, system, reg), reg)
    how = _fill(e.get("how", ""), name, owner)
    if not how:
        return ""
    how = how.rstrip(".")
    if goal and e.get("goal"):
        return f"{_goal(e)}: {how}."
    return f"{how[:1].upper()}{how[1:]}."


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
    """An entry as a doc block carries it, for a reader who is not in a chat: a comment with
    the day it was checked and its page (for whoever maintains the doc, never shown), then its
    numbered steps where it has them, else the path, or the claim for "<id> claim" and for an
    entry with no path. A beginner given one long sentence of destinations did not know where
    to start (2026-10-20), so steps come one action a line, and end on CLOSING."""
    want_claim = eid.endswith(" claim")
    e = entry(eid.split()[0], reg)
    page = official(e)
    note = f"<!-- checked {e['verified_on']}" + (f"; {page}" if page else "") + " -->"
    if not want_claim and e.get("steps"):
        lines = steps(e["id"], reg, name="YOUR-COPY", owner="YOUR-NAME")
        return "\n".join([note] + lines + ["", CLOSING_DOC])
    text = "" if want_claim else say(e["id"], name="of your copy", owner="you", reg=reg)
    return "\n".join([note, text or e["claim"]])


def block(eid: str, indent: str = "", reg=None, width: int = 92) -> str:
    """A marked block as a doc carries it: the rendered entry, wrapped, at `indent`, each
    numbered step on its own line."""
    import textwrap
    out = []
    for line in render(eid, reg).split("\n"):
        numbered = re.match(r"\d+\. ", line)
        out.append(textwrap.fill(line, width=width, initial_indent=indent,
                                 subsequent_indent=indent + ("   " if numbered else ""),
                                 break_long_words=False, break_on_hyphens=False))
    body = "\n".join(out)
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
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
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
    hand = int(reg.get("hand_check_days", 30))
    for e in reg["entries"]:
        for s in e.get("sources", ()):
            url = s["url"]
            if not url.startswith("http"):
                continue
            if s.get("fetch") is False:
                # Never fetched (LinkedIn's pages: robots.txt, and a session never fetches
                # linkedin.com), so never known to have changed. Each is put to the
                # maintainer by hand once a month instead, before a person meets the change.
                n = age(e, today)
                if n > hand:
                    out.append((e["id"], f"check by hand: {url} is never fetched "
                                f"({s.get('why_not_fetched') or 'not fetched'}); last checked "
                                f"{e['verified_on']}, {n} days ago. Is this still on it: "
                                f"{s['quote']!r}?"))
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
    if not argv or argv[0] not in ("check", "show", "say", "steps", "sync-docs", "watch"):
        print(__doc__.split("\n\n")[2])
        return 2
    cmd, rest = argv[0], argv[1:]
    opt = {k: rest[rest.index(k) + 1] for k in ("--name", "--owner") if k in rest}
    # Which computer the steps are for: --system darwin|win32|linux, "all" for the entry that
    # says all three, and by default this computer's own where the chat runs on the person's
    # computer (here_system), all three in a cloud chat, whose own system is the container's.
    asked = rest[rest.index("--system") + 1] if "--system" in rest[:-1] else "here"
    system = here_system() if asked == "here" else "" if asked == "all" else system_of(asked)
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
        eid = for_system(rest[0], system)
        e = entry(eid)
        print(say(eid, **{k[2:]: v for k, v in opt.items()}))
        print(source(eid), file=sys.stderr)    # for Claude: never said
        w = warning(e)
        if w:
            print(w, file=sys.stderr)
        return 0
    if cmd == "steps":
        eid = for_system(rest[0], system)
        print("\n".join(steps(eid, **{k[2:]: v for k, v in opt.items()})))
        print(source(eid), file=sys.stderr)    # for Claude, as `say` gives it: never said
        for w in notes(eid):
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
