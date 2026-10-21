#!/usr/bin/env python3
"""Is this chat the right place for what the person set up? Said once in a chat.

Where a chat runs decides what it can do. A cloud chat cannot use the browser on
the person's computer unless the desktop app lends it one, a phone has no browser
of theirs at all, and a chat on their own computer needs a few tools installed
once. This reads where the chat runs, the person's own setting
(profile/networking.py PROFILE_READS) and, on a computer, what is missing
(tools/env_check.py local_fixes), and says what to do in plain words. It never
changes a setting: where it offers a choice, the person makes it.

    python3 tools/place.py [--tools browser,chrome,chrome-off,enable,none] [--employer X]
    python3 tools/place.py ask                       # /setup's question, with the trade-off
    python3 tools/place.py record computer|phone|both  # their answer, into profile/place.json
    python3 tools/place.py next [--works-on computer|phone|both]   # the exact next step

`sync_app.py` runs the check after the day's sync and again in every later chat
that day. A chat hears it once, and again only when its words change, or after
RETELL_DAYS while the computer it runs on is still missing a tool the work needs. Told
weekly, a person who had already chosen heard "two chats work best, ask me how to move"
again and again for no reason (2026-10-20), so a choice is offered once. A person who
already has a chat on their computer is never asked to move. The record of who was told
is kept in .git, so it is never committed and never dirties the tree.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import local_path  # noqa: E402

# Look where a person's computer keeps TeX and Bun before saying either is missing: a
# chat's shell on a Mac lacks /Library/TeX/texbin, and this said "install LaTeX" to
# someone whose LaTeX compiled both example documents.
local_path.extend()

PLACE_FILE = "place.json"           # in profile/: {"works_on": ..., "asked": date}
TOLD_FILE = "ljs-place.json"        # in .git/: the chats already told, never committed
ANSWERS = ("computer", "phone", "both")
BROWSERS = {"browser", "chrome", "enable"}

QUESTION = "Will you mostly work on a computer, or on your phone or the web?"
TRADE_OFF = (
    "Finding people, searching for jobs and writing work the same everywhere. On a computer, "
    "in the Claude desktop app, Claude can also read each person's LinkedIn profile before "
    "writing to them, and your files sit on your disk; a few free tools go on once, and one or "
    "two ask for your computer's password. On a phone or the web nothing is installed, but "
    "profiles cannot be read there: you reach the chat on your computer from your phone.")
RECOMMEND = "If you have a computer you can use for this, choose the computer: it does more for you."
# The set-up that works for nearly everyone with a computer, said where a person decides
# where to work (/setup's question, its next step) and in the check a cloud chat on a
# computer gives. Told only "a computer does more", people kept every chat in the cloud and
# found out at their first networking run that profiles cannot be read there.
TWO_CHATS = ("Two chats work best. One on your computer, for everything you do: job searches, "
             "resumes, interview prep and networking. And your brief, in the cloud: it follows "
             "up for you and arrives even when your computer is off.")
SHORT_TWO_CHATS = ("Two chats work best: one on your computer for everything you do, and your "
                   "brief in the cloud. Ask me how to move.")
# Said instead to a person who already has a chat on their computer (place.json
# "computer_chat"): what this chat can do, with no move to make.
SHORT_HAS_LOCAL = ("Finding people works here. Their profiles are read in your chat on your "
                   "computer.")

# The one line a chat with no browser of the person's says about reading. Finding
# people never needs it (tools/network/sources.py, the ladder), so the line says what
# works here first, and nothing it says blocks the work.
FINDING_WORKS = ("Finding people works in this chat. Reading their profiles before writing "
                 "to them needs a browser of yours, which this chat cannot reach.")
# A cloud chat can reach the browser in the Claude desktop app on the person's computer
# while the app is open there (claude_surfaces: cloud-linked-browser). Anthropic's skill
# describes it and its docs do not yet, so the person is told so plainly, both when a
# chat can and when it cannot.
CLOUD_LINK_NOW = ("This chat reads profiles in the Claude desktop app's browser on your "
                  "computer, while the app stays open there. Anthropic's documentation does not "
                  "describe this yet, so it may change; if it stops working, the same reading "
                  "works in a chat on your computer.")
CLOUD_LINK_NOT = ("A cloud chat can sometimes reach that browser while the Claude desktop app "
                  "is open on your computer, but this one cannot, and Anthropic's documentation "
                  "does not describe that link yet, so the reliable place is a chat on your "
                  "computer.")
PASTE_TOP = ("Or paste the profile of the one or two who matter most, here, and I'll write "
             "to them from it.")
# When the chat's tools were not named, a line carries this condition for Claude to
# test first. It is never said to the person.
IF_NO_BROWSER = ("[only if this chat has no browser tool: no Claude_Browser tools, no "
                 "enable__mcp__remote-devices__Claude_Browser, no Claude in Chrome] ")
SIGN_IN_ONCE = ("The first time a profile is read, LinkedIn's sign-in page opens in the "
                "desktop app's own browser: sign in there yourself, once. It remembers it "
                "after that, until LinkedIn signs you out.")


# What a chat with no browser of the person's says by default: two or three short
# sentences and no links. The steps, with their dated paths and official pages, come only
# when the person asks how or says they want to move (`place.py how`): a block of 150 words
# and two URLs at the end of every reply was the part nobody read.
SHORT_REMOTE = ("Finding people works here. Reading their profiles before writing to them needs "
                "a chat on your computer, which you can also use from your phone.")
SHORT_CLOUD = ("Finding people works here, but reading their profiles before writing to them "
               "needs a chat on your computer.")
SHORT_LOCAL = ("Finding people works here. Reading their profiles before writing to them needs "
               "a browser this chat can use, such as the Claude desktop app's own.")
SHORT_PASTE = "Or paste the one or two who matter most. Ask me how if you want to move."
SHORT_LINK_NOW = ("This chat reads profiles in the Claude desktop app's browser on your "
                  "computer while the app stays open. Anthropic's documentation does not "
                  "describe this yet, so it may change.")
SHORT_SIGN_IN = ("The first time, LinkedIn's sign-in page opens in the desktop app's browser: "
                 "sign in there yourself, once.")
SHORT_WORDS = 60     # the most any one default message may run to (tests/test_place.py)


BRIEF_LOCAL = ("Your brief runs in the cloud, so it arrives when your computer is off. "
               "Nothing to do on your computer.")


def surface(env=None) -> str:
    """"phone", "web", "desktop-cloud", "local" or "unknown": where this chat runs.

    CLAUDE_CODE_REMOTE is documented ("true" in a cloud session). Which app
    started a cloud chat is not, so CLAUDE_CODE_ENTRYPOINT is read as a hint and
    anything it does not settle is "unknown", which is treated like the web: no
    instruction that needs a computer.
    """
    env = os.environ if env is None else env
    entry = str(env.get("CLAUDE_CODE_ENTRYPOINT", "")).lower()
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() != "true":
        return "local" if env.get("CLAUDECODE") else "unknown"
    if any(w in entry for w in ("mobile", "ios", "android", "phone")):
        return "phone"
    if "desktop" in entry:
        return "desktop-cloud"
    if "web" in entry:
        return "web"
    return "unknown"


def repo() -> tuple:
    """(owner, name) of the person's copy, from its origin; ("", folder) without one."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True,
                             capture_output=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        url = ""
    m = re.search(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    return (m.group(1), m.group(2)) if m else ("", os.path.basename(ROOT))


def _say(eid: str, owner: str, name: str, goal: bool = True) -> str:
    import claude_surfaces
    return claude_surfaces.say(eid, name=name, owner=owner, goal=goal)


def _continue_locally(owner: str, name: str, then: str) -> str:
    """The way there, as numbered steps from the registry, each part headed by the day it
    was checked: a person who had only ever used the cloud could not follow one long
    sentence of destinations (2026-10-20)."""
    import claude_surfaces
    return ("Two parts, once. First, put your copy on your computer.\n"
            + "\n".join(claude_surfaces.steps("clone-copy"))
            + "\nThen start a chat on it.\n" + "\n".join(claude_surfaces.steps("local-chat"))
            + f"\nOnce it is set up, say \"{then}\" there.")


def check(where: str, setting: str, tools=None, signed_in: bool = False, fixes=(),
          owner: str = "", name: str = "my-job-search", employer: str = "",
          detail: bool = False, works: str = "", has_local: bool = False) -> list:
    """What to tell the person about this chat's place. [] when it is right.

    `tools` is the browser tools this chat has (browser, chrome, chrome-off, enable),
    or None when unknown, which asks the chat to look before it says anything.
    `fixes` is env_check.local_fixes(): what this computer is missing. By default each
    message is two or three short sentences with no links; `detail` gives the steps,
    each path dated with its official page, for a person who asked how. `has_local` is
    True once a chat has run on their computer: nobody is asked to move who already has.
    """
    out = []
    have = None if tools is None else {str(t).lower() for t in tools} & BROWSERS
    then = f"find me people at {employer}" if employer else "find me people at <employer>"
    if setting == "browser":
        # By the tools the chat has, never by where it was started: a phone chat linked
        # to the computer reads profiles as well as a chat on it does (claude_surfaces:
        # cloud-linked-browser), and where a chat was started is not documented.
        if have:
            if where != "local" and have & {"browser", "enable"}:
                out.append(CLOUD_LINK_NOW if detail else SHORT_LINK_NOW)
            if not signed_in and have & {"browser", "enable"}:
                out.append(SIGN_IN_ONCE if detail else SHORT_SIGN_IN)
        elif has_local and where != "local":
            line = SHORT_HAS_LOCAL
            out.append(line if have is not None else IF_NO_BROWSER + line)
        elif not detail:
            line = ({"phone": SHORT_REMOTE + " " + SHORT_PASTE,
                     "web": SHORT_REMOTE + " " + SHORT_PASTE,
                     "local": SHORT_LOCAL + " Ask me how."}
                    .get(where, SHORT_CLOUD + " " + SHORT_TWO_CHATS))
            out.append(line if have is not None else IF_NO_BROWSER + line)
        else:
            if where in ("phone", "web"):
                line = (f"{FINDING_WORKS} The chat on your computer can do the reading, and you "
                        f"can use it from your phone. {_say('remote-control', owner, name, False)}"
                        f" {PASTE_TOP}")
            elif where == "local":
                line = ("Finding people works in this chat. Reading their profiles before writing "
                        "to them needs a browser this chat can use: the Claude desktop app has "
                        f"its own. {_say('local-chat', owner, name, False)} In a terminal, Claude "
                        f"in Chrome reads them in your own Chrome. {_say('chrome', owner, name, False)}"
                        f" {PASTE_TOP}")
            else:
                line = (f"{FINDING_WORKS} {CLOUD_LINK_NOT} {TWO_CHATS} "
                        f"{_continue_locally(owner, name, then)}")
            out.append(line if have is not None else IF_NO_BROWSER + line)
    elif works in ("computer", "both") and where != "local" and not has_local:
        # Not reading profiles in their browser, a person with a computer still does best
        # with two chats, and an existing one who set up in the cloud was never told.
        out.append((TWO_CHATS + " " + _continue_locally(owner, name, "carry on")) if detail
                   else SHORT_TWO_CHATS)
    if where == "local" and fixes:
        lines = ["This computer is missing a few things. Each is one command; I run the ones "
                 "without a mark myself. The marked ones are yours, once, pasted into Terminal "
                 "(PowerShell on Windows), because they ask for your computer's password or "
                 "sign you in:"]
        mark = {"password": "  [asks for your password]",
                "sign-in": "  [yours: it signs you in to GitHub in your web browser]"}
        for what, cmd, whose in fixes:
            lines.append(f"  - {what}: {cmd}{mark.get(whose, '')}")
        out.append("\n".join(lines))
    return out


def next_step(works_on: str, where: str, owner: str = "", name: str = "my-job-search") -> str:
    """The exact next step after /setup's question, for where this chat runs."""
    if works_on == "computer" and where != "local":
        return TWO_CHATS + " " + _continue_locally(owner, name, "set me up")
    if works_on == "phone" and where == "local":
        return (f"Carry on here. On your phone, open claude.ai/code (or the Claude app's Code "
                f"tab) and choose {name}: both work on your copy on GitHub.")
    if works_on == "both":
        return (TWO_CHATS + " Both work on the same copy on GitHub, and from your phone you "
                "can use the chat on your computer.")
    if works_on == "computer":
        return "Carry on here: this is the right place. " + TWO_CHATS
    return "Carry on here: this is the right place."


# ------------------------------------------------------------------ state

def _profile_file() -> str:
    import person
    return person.path(PLACE_FILE)


def _place() -> dict:
    try:
        with open(_profile_file(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except Exception:  # no profile, no file, or a bad one: unknown
        return {}


def works_on() -> str:
    return str(_place().get("works_on") or "")


def has_local() -> bool:
    """Has a chat ever run on the person's own computer? Then nobody asks them to move."""
    return bool(_place().get("computer_chat"))


def note_local(today: datetime.date | None = None) -> bool:
    """Record, once, that a chat has run on their computer: the date it was first seen, in
    profile/place.json beside their answer. Only into a profile that exists."""
    try:
        import person
        if has_local() or not person.exists("person.json"):
            return False
        got = dict(_place(), computer_chat=(today or datetime.date.today()).isoformat())
        path = _profile_file()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(got, fh, indent=2)
            fh.write("\n")
        _commit_place(path)
        return True
    except Exception:  # a check must never break the sync that runs it
        return False


def _commit_place(path: str) -> None:
    """Commit the one line just written, and only it. Left uncommitted, it stopped the next
    sync, which pulls master only into a clean folder: every chat on a computer was told to
    commit a file it had never touched (found by tools/rehearse_sync.py, 2026-10-21)."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    rel = os.path.relpath(path, root)
    try:
        if subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", rel],
                          capture_output=True, timeout=30).returncode:
            subprocess.run(["git", "-C", root, "add", "--", rel], capture_output=True,
                           timeout=30)
        subprocess.run(["git", "-C", root, "commit", "-q", "-m",
                        "Place: a chat on this computer, first seen", "--", rel],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def record(answer: str, today: datetime.date | None = None) -> str:
    """Write the answer to profile/place.json. Only into a profile that exists: an
    empty profile/ holding this alone would read as a finished setup."""
    import person
    if answer not in ANSWERS:
        raise SystemExit(f"place: the answer is one of {', '.join(ANSWERS)}")
    if not person.exists("person.json"):
        raise SystemExit("place: no profile yet; /setup records the answer when it writes "
                         "the profile (Step 3)")
    p = _profile_file()
    got = dict(_place(), works_on=answer, asked=(today or datetime.date.today()).isoformat())
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(got, fh, indent=2)
        fh.write("\n")
    return p


def setting() -> str:
    try:
        import person
        if not person.exists("networking.py"):
            return ""
        return str(getattr(person.module("networking"), "PROFILE_READS", "") or "").lower()
    except Exception:  # a check must never break the sync that runs it
        return ""


def signed_in_ever() -> bool:
    try:
        import person
        return os.path.exists(person.state("documents", "network", ".signed_in.json"))
    except Exception:
        return False


def _told_path() -> str:
    try:
        d = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, text=True,
                           capture_output=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        d = ""
    d = d or ".git"
    return os.path.join(d if os.path.isabs(d) else os.path.join(ROOT, d), TOLD_FILE)


def _digest(lines) -> str:
    import hashlib
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()[:12]


# Said again in the same chat after this many days while it still applies: often enough
# that a person who missed it, or who has since come round to the right chat, hears it
# again; rare enough never to nag. A change in the words is said at once.
RETELL_DAYS = 7


def told(chat: str, lines=None, today: datetime.date | None = None,
         retell: bool = False) -> bool:
    """Was this chat told these words? A chat told an older wording is told the new one at
    once. The same words come again only with `retell` (a computer still missing a tool),
    after RETELL_DAYS."""
    try:
        with open(_told_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return False
    said = got.get("said") or {}
    if lines is None:
        return chat in said or chat in got.get("chats", [])
    rec = said.get(chat)
    if isinstance(rec, str):          # a record from before the date was kept
        rec = {"digest": rec, "on": ""}
    if not isinstance(rec, dict) or rec.get("digest") != _digest(lines):
        return False
    if not retell:
        return True
    try:
        on = datetime.date.fromisoformat(rec.get("on") or "")
    except ValueError:
        return False
    return ((today or datetime.date.today()) - on).days < RETELL_DAYS


def _told_before(chat: str) -> bool:
    """Was this chat last told something that was not nothing?"""
    try:
        with open(_told_path(), encoding="utf-8") as fh:
            rec = (json.load(fh).get("said") or {}).get(chat)
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(rec, dict) and rec.get("digest") not in (None, _digest(()))


def mark_told(chat: str, lines=(), today: datetime.date | None = None) -> None:
    p = _told_path()
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    said = {k: v for k, v in (got.get("said") or {}).items() if k != chat}
    said = dict(list(said.items())[-49:])
    said[chat] = {"digest": _digest(lines),
                  "on": (today or datetime.date.today()).isoformat()}
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"said": said}, fh)
    except OSError:
        pass


def this_chat(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("CLAUDE_CODE_REMOTE_SESSION_ID") or env.get("CLAUDE_CODE_SESSION_ID") or ""


def report(tools=None, employer: str = "", once: bool = False, env=None,
           today: datetime.date | None = None) -> str:
    """The check as the sync prints it: "" when there is nothing to say, or already said."""
    chat = this_chat(env)
    where = surface(env)
    fixes = ()
    if where == "local":
        note_local(today)
        try:
            import env_check
            fixes = env_check.local_fixes()
        except Exception:
            fixes = ()
    owner, name = repo()
    lines = check(where, setting(), tools, signed_in_ever(), fixes, owner, name, employer,
                  works=works_on(), has_local=has_local())
    if once and chat:
        if not lines and _told_before(chat):
            # It had asked for something, and it is all here now: said once, so the
            # person who ran the commands hears it worked.
            mark_told(chat, (), today)
            return ("Place check (Claude: tell the person this once, in your own words): "
                    "everything it asked for is in place now; nothing more to do.")
        if told(chat, lines, today, retell=bool(fixes)):
            return ""
        mark_told(chat, lines, today)
    if not lines:
        return ""
    import claude_surfaces
    used = [e for e in claude_surfaces.load()["entries"]
            if e.get("how") and claude_surfaces.say(e["id"], name=name, owner=owner)
            and any(claude_surfaces.say(e["id"], name=name, owner=owner) in l for l in lines)]
    warn = [w for w in (claude_surfaces.warning(e) for e in used) if w]
    return ("Place check (Claude: tell the person this at the end of your reply, in these "
            "words; it is said once in a chat, and again only when it changes. If they ask how, "
            "or say they want to move, give them what `python3 tools/place.py how` prints. "
            "When they say they have run what it asks, check again at once with `python3 "
            "tools/place.py check`, rather than waiting for the next day's sync. "
            "Never apply a choice for them, and never hold back work that does not need it. A "
            "[bracketed] condition is yours to test, never said):\n"
            + "\n".join("  " + l.replace("\n", "\n  ") for l in lines)
            + "".join("\n  " + w for w in warn))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="check",
                    choices=("check", "how", "ask", "record", "next"))
    ap.add_argument("answer", nargs="?", default="")
    ap.add_argument("--tools", default=None,
                    help="the browser tools this chat has: browser, chrome, chrome-off, enable, none")
    ap.add_argument("--employer", default="")
    ap.add_argument("--works-on", default="")
    ap.add_argument("--once", action="store_true",
                    help="say nothing if this chat was told these words in the last week")
    a = ap.parse_args(argv)
    if a.cmd == "ask":
        print(f"{QUESTION}\n{TRADE_OFF}\n{RECOMMEND}")
        return 0
    if a.cmd == "record":
        print(f"place: recorded {a.answer} in {os.path.relpath(record(a.answer), ROOT)}")
        print(next_step(a.answer, surface(), *repo()))
        return 0
    if a.cmd == "next":
        print(next_step(a.works_on or works_on() or "both", surface(), *repo()))
        return 0
    tools = None if a.tools is None else [t for t in a.tools.split(",") if t.strip() not in ("", "none")]
    if a.cmd == "how":
        owner, name = repo()
        lines = check(surface(), setting(), tools, signed_in_ever(), (), owner, name,
                      a.employer, detail=True, works=works_on(), has_local=has_local())
        print("\n".join(lines) or "place: this chat is the right place")
        return 0
    out = report(tools, a.employer, a.once)
    print(out or "place: this chat is the right place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
