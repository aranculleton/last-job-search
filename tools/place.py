#!/usr/bin/env python3
"""Is this chat the right place for what the person set up? Checked once per chat.

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
that day, and prints it once per chat (the record of who was told is kept in
.git, so it is never committed and never dirties the tree).
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

PLACE_FILE = "place.json"           # in profile/: {"works_on": ..., "asked": date}
TOLD_FILE = "ljs-place.json"        # in .git/: the chats already told, never committed
ANSWERS = ("computer", "phone", "both")
BROWSERS = {"browser", "chrome", "enable"}

QUESTION = "Will you mostly work on a computer, or on your phone or the web?"
TRADE_OFF = (
    "On a computer, in the Claude desktop app, Claude can read people's LinkedIn profiles "
    "in the app's own browser and your files sit on your disk; a few free tools go on "
    "once, and one or two ask for your computer's password. On a phone or the web nothing "
    "is installed and it works anywhere, but you send a screenshot or a paste of each "
    "profile you want read.")
RECOMMEND = "If you have a computer you can use for this, choose the computer: it does more for you."

PHONE_WEB = "On a phone or in a browser, send screenshots or a paste for each profile."
# When the chat's tools were not named, a line carries this condition for Claude to
# test first. It is never said to the person.
IF_NO_BROWSER = ("[only if this chat has no browser tool: no Claude_Browser tools, no "
                 "enable__mcp__remote-devices__Claude_Browser, no Claude in Chrome] ")
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


def _folder(owner: str, name: str) -> str:
    where = f"github.com/{owner}/{name}" if owner else "your copy's page on GitHub"
    return (f"If {name} is not on your computer yet: on {where}, click Code, then Open with "
            "GitHub Desktop, and save it there first.")


def _open_locally(owner: str, name: str, then: str) -> str:
    return (f"Close this chat. Open the Claude desktop app, click the Code tab, choose the "
            f"folder {name} and say \"{then}\". {_folder(owner, name)}")


def check(where: str, setting: str, tools=None, signed_in: bool = False, fixes=(),
          owner: str = "", name: str = "my-job-search", employer: str = "") -> list:
    """What to tell the person, once, about this chat's place. [] when it is right.

    `tools` is the browser tools this chat has (browser, chrome, chrome-off, enable),
    or None when unknown, which asks the chat to look before it says anything.
    `fixes` is env_check.local_fixes(): what this computer is missing.
    """
    out = []
    have = None if tools is None else {str(t).lower() for t in tools} & BROWSERS
    if setting == "browser":
        if where in ("phone", "web", "unknown"):
            out.append(PHONE_WEB)
        elif where == "desktop-cloud" and not have:
            then = f"find me people at {employer}" if employer else "find me people at <employer>"
            line = ("Your setting reads LinkedIn profiles in the browser on your computer, and "
                    "this chat runs in the cloud without it. " + _open_locally(owner, name, then)
                    + " Or say \"paste\" and send each profile here instead, this time.")
            out.append(line if have is not None else IF_NO_BROWSER + line)
        elif where == "local" and have is not None and not have:
            out.append("This chat has no browser to read LinkedIn profiles in. "
                       + _open_locally(owner, name, "find me people at <employer>")
                       + " Or say \"paste\" and send each profile here instead, this time.")
        elif where in ("local", "desktop-cloud") and not signed_in:
            out.append("The first time a profile is read, LinkedIn's sign-in page opens in the "
                       "browser pane in the Claude desktop app: sign in there yourself, once. "
                       "The pane remembers it after that, until LinkedIn signs you out.")
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
        return _open_locally(owner, name, "set me up")
    if works_on == "phone" and where == "local":
        return (f"Carry on here. On your phone, open claude.ai/code (or the Claude app's Code "
                f"tab) and choose {name}: both work on your copy on GitHub.")
    if works_on == "both":
        return ("Carry on here. Chats on your computer and on your phone or the web work on "
                "the same copy on GitHub, so start one wherever you are.")
    return "Carry on here: this is the right place."


# ------------------------------------------------------------------ state

def _profile_file() -> str:
    import person
    return person.path(PLACE_FILE)


def works_on() -> str:
    try:
        with open(_profile_file(), encoding="utf-8") as fh:
            return str(json.load(fh).get("works_on") or "")
    except Exception:  # no profile, no file, or a bad one: unknown
        return ""


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
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"works_on": answer, "asked": (today or datetime.date.today()).isoformat()},
                  fh, indent=2)
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


def told(chat: str) -> bool:
    try:
        with open(_told_path(), encoding="utf-8") as fh:
            return chat in json.load(fh).get("chats", [])
    except (OSError, ValueError):
        return False


def mark_told(chat: str) -> None:
    p = _told_path()
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    chats = [c for c in got.get("chats", []) if c != chat][-49:] + [chat]
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"chats": chats}, fh)
    except OSError:
        pass


def this_chat(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("CLAUDE_CODE_REMOTE_SESSION_ID") or env.get("CLAUDE_CODE_SESSION_ID") or ""


def report(tools=None, employer: str = "", once: bool = False, env=None) -> str:
    """The check as the sync prints it: "" when there is nothing to say, or already said."""
    chat = this_chat(env)
    if once and chat and told(chat):
        return ""
    where = surface(env)
    fixes = ()
    if where == "local":
        try:
            import env_check
            fixes = env_check.local_fixes()
        except Exception:
            fixes = ()
    owner, name = repo()
    lines = check(where, setting(), tools, signed_in_ever(), fixes, owner, name, employer)
    if once and chat:
        mark_told(chat)
    if not lines:
        return ""
    return ("Place check (Claude: tell the person this once in this chat, in these words, "
            "at the end of your reply; never apply a choice for them. A [bracketed] condition "
            "is yours to test, never said):\n"
            + "\n".join("  " + l.replace("\n", "\n  ") for l in lines))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="check", choices=("check", "ask", "record", "next"))
    ap.add_argument("answer", nargs="?", default="")
    ap.add_argument("--tools", default=None,
                    help="the browser tools this chat has: browser, chrome, chrome-off, enable, none")
    ap.add_argument("--employer", default="")
    ap.add_argument("--works-on", default="")
    ap.add_argument("--once", action="store_true", help="say nothing if this chat was told")
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
    out = report(tools, a.employer, a.once)
    print(out or "place: this chat is the right place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
