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
    python3 tools/place.py state                     # is the search set up here, landed, on
                                                     # another chat's branch, or still being set up?
    python3 tools/place.py started | finished        # /setup marks its own run, so other chats know
    python3 tools/place.py auto                      # /setup: record where this chat can tell, else
                                                     # print the one short question to ask
    python3 tools/place.py ask                       # that question, with its one-line why
    python3 tools/place.py record computer|phone|both  # their answer, into profile/place.json
    python3 tools/place.py next [--works-on computer|phone|both]   # the step after it

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

# Asked once, at the end of /setup, and only where the chat cannot tell: a chat on the
# computer is "computer", and a cloud chat started from the desktop app is "both". It
# used to come first and stop a cloud chat with no profile written, telling the person to
# start again on their computer (2026-10-25): setup works the same everywhere, so it never
# stops, and the computer chat is offered once, at the end.
QUESTION = "Will you also use Claude on a computer, in its desktop app?"
TRADE_OFF = ("Everything works here. On a computer it can also read people's LinkedIn "
             "profiles before you write to them.")
RECOMMEND = "If you have one you can use, say yes."
# The set-up that works for nearly everyone with a computer, said where a person decides
# where to work (/setup's question, its next step) and in the check a cloud chat on a
# computer gives. Told only "a computer does more", people kept every chat in the cloud and
# found out at their first networking run that profiles cannot be read there.
TWO_CHATS = ("Two chats work best: one on your computer for everything you do, and your brief "
             "in the cloud, which arrives even when your computer is off.")
# The one message a computer chat starts from: it names the person's copy and the page that
# takes an empty folder to a copy that is set up (COMPUTER.md, the app's). The words are
# the registry's (claude_surfaces local-chat, its last step), so a doc and a chat say one thing.
COMPUTER_PAGE = "github.com/aranculleton/last-job-search/blob/master/COMPUTER.md"
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
# while the app is open there (claude_surfaces: cloud-linked-browser, which records that
# Anthropic's skill describes it and its docs do not yet). The person is told what works,
# in a sentence, and no caveat: a reply that warned and warned before reading anything was
# what the person had to wade through (2026-10-25).
CLOUD_LINK_NOW = ("This chat reads profiles in the Claude desktop app's browser on your "
                  "computer, while the app stays open there.")
CLOUD_LINK_NOT = ("This chat can't reach that browser just now; the chat on your computer can.")
PASTE_TOP = ("Or paste the profile of the one or two who matter most, here, and I'll write "
             "to them from it.")
# When the chat's tools were not named, a line carries this condition for Claude to
# test first. It is never said to the person.
IF_NO_BROWSER = ("[only if this chat has no browser tool: no Claude_Browser tools, no "
                 "enable__mcp__remote-devices__Claude_Browser, no Claude in Chrome] ")
# Nothing about signing in to LinkedIn is said here: the reading step itself sees when the
# browser is signed out and asks them to sign in, once, saying what signing in shows
# (tools/network/reading.py). Said here as well, with its caveats, it came before any reading
# and in a muddle of warnings (2026-10-25).


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
SHORT_LINK_NOW = CLOUD_LINK_NOW
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
                             capture_output=True, timeout=10,
                             encoding="utf-8", errors="replace").stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        url = ""
    m = re.search(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    return (m.group(1), m.group(2)) if m else ("", os.path.basename(ROOT))


def _say(eid: str, owner: str, name: str, goal: bool = True) -> str:
    import claude_surfaces
    return claude_surfaces.say(eid, name=name, owner=owner, goal=goal)


def computer_paste(owner: str = "", name: str = "my-job-search") -> str:
    """The message a new chat on their computer starts from (the last of local-chat's steps)."""
    import claude_surfaces
    return claude_surfaces.steps("local-chat", name=name, owner=owner)[-1].split(
        "Paste this there: ", 1)[-1]


def _continue_locally(owner: str, name: str, then: str) -> str:
    """The way there, as numbered steps from the registry: a new empty folder in the desktop
    app, and one message that makes their copy there and sets it up (COMPUTER.md). A person
    who had only ever used the cloud could not follow one long sentence of destinations
    (2026-10-20); GitHub Desktop, which this once began with, is not needed at all."""
    import claude_surfaces
    return ("\n".join(claude_surfaces.steps("local-chat", name=name, owner=owner))
            + f"\nOnce it is set up, say \"{then}\" there.\n{claude_surfaces.CLOSING}")


def linux_kind(platform: str | None = None, release: str | None = None,
               os_release: str | None = None) -> str:
    """"wsl", "debian" (Ubuntu, Debian and their kin: the desktop app's beta), "other"
    (Fedora, Arch and the rest: the terminal version), or "" off Linux (claude_surfaces:
    linux-computer)."""
    import platform as _p
    platform = sys.platform if platform is None else platform
    if not platform.startswith("linux"):
        return ""
    release = _p.release() if release is None else release
    if "microsoft" in release.lower():
        return "wsl"
    if os_release is None:
        try:
            with open("/etc/os-release", encoding="utf-8") as fh:
                os_release = fh.read()
        except OSError:
            os_release = ""
    ids = " ".join(v.strip().strip('"').lower() for k, _, v in
                   (ln.partition("=") for ln in os_release.splitlines())
                   if k in ("ID", "ID_LIKE"))
    return "debian" if any(w in ids.split() for w in ("debian", "ubuntu")) else "other"


def check(where: str, setting: str, tools=None, signed_in: bool = False, fixes=(),
          owner: str = "", name: str = "my-job-search", employer: str = "",
          detail: bool = False, works: str = "", has_local: bool = False,
          os_name: str = "") -> list:
    """What to tell the person about this chat's place. [] when it is right.

    `tools` is the browser tools this chat has (browser, chrome, chrome-off, enable),
    or None when unknown, which asks the chat to look before it says anything.
    `fixes` is env_check.local_fixes(): what this computer is missing. By default each
    message is two or three short sentences with no links; `detail` gives the steps,
    each path dated with its official page, for a person who asked how. `has_local` is
    True once a chat has run on their computer: nobody is asked to move who already has.
    `os_name` is the computer's (sys.platform), given by the command, so a Windows or Linux
    computer is told the way that works there; "" says nothing particular to one.
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
            elif where == "local" and linux_kind(os_name or "none") in ("other", "wsl"):
                # No desktop app here (Fedora, Arch: claude_surfaces linux-computer), and in
                # WSL no Claude in Chrome either: the way that works, said first.
                kind = linux_kind(os_name)
                way = (_say("linux-computer", owner, name, False) if kind == "other"
                       else "In WSL, Claude in Chrome does not work: use the Claude desktop app "
                            "on Windows itself for reading profiles.")
                line = ("Finding people works in this chat. Reading their profiles before writing "
                        f"to them needs a browser this chat can use. {way} {PASTE_TOP}")
            elif where == "local" and os_name == "win32":
                line = ("Finding people works in this chat. Reading their profiles before writing "
                        "to them needs a browser this chat can use: the Claude desktop app has "
                        f"its own. {_say('windows-computer', owner, name, False)} {PASTE_TOP}")
            elif where == "local":
                # The desktop app's own browser is the default, whatever browser the person
                # uses; Claude in Chrome only for someone already on Chrome or Edge who wants
                # their own sign-in. Nobody is told to install Chrome (claude_surfaces: chrome).
                line = ("Finding people works in this chat. Reading their profiles before writing "
                        "to them needs a browser this chat can use: the Claude desktop app has "
                        f"its own, whatever browser you use. {_say('local-chat', owner, name, False)}"
                        " If you already use Chrome or Edge and want your own sign-in there, "
                        f"Claude in Chrome does it from a terminal: {_say('chrome', owner, name, False)}"
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
        # Claude runs every one: a person was once sent to Terminal (and on Windows to
        # PowerShell) to paste commands they could not read (2026-10-25). A mark says only what
        # may come up on their screen while it runs.
        lines = ["This computer is missing a few things. I install them myself, one at a time; "
                 "a mark says what may come up on your screen while I do:"]
        mark = {"password": "  [a window may ask for your computer's password]",
                "sign-in": "  [a page opens in your browser to sign in to GitHub]",
                "dialog": "  [a window asks to install Apple's developer tools: choose Install]",
                "yours": "  [this one needs your password, so it is yours: paste it into a "
                         "terminal window, then tell me]"}
        for what, cmd, whose in fixes:
            lines.append(f"  - {what}: {cmd}{mark.get(whose, '')}")
        out.append("\n".join(lines))
    return out


def next_step(works_on: str, where: str, owner: str = "", name: str = "my-job-search") -> str:
    """The step after /setup's question, said at the end of setup. It never stops a chat:
    the profile is written wherever the person is, and a computer chat is offered once, with
    the one message that sets it up (2026-10-25)."""
    if works_on in ("computer", "both") and where != "local":
        return (f"{TWO_CHATS} When you are at your computer, open the Claude desktop app on a new "
                f"empty folder (Local, under the message box) and paste this: "
                f"{computer_paste(owner, name)} Ask me for the steps if you want them.")
    if works_on == "phone" and where == "local":
        return (f"Carry on here. On your phone, open claude.ai/code and choose {name}: both "
                "work on your copy on GitHub.")
    if works_on in ("computer", "both"):
        return "Carry on here: this is the right place. " + BRIEF_LOCAL
    return "Carry on here: this is the right place."


def auto_answer(where: str) -> str:
    """Where the person will work, when this chat can tell without asking: a chat on the
    computer is "computer", and a cloud chat the desktop app started is "both". "" means ask
    QUESTION once, at the end of setup."""
    return {"local": "computer", "desktop-cloud": "both"}.get(where, "")


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


# ------------------------------------------------------------------ is it set up?
#
# A chat on the computer, opened while the cloud chat was still writing the profile, saw no
# profile, ran /setup and asked for a resume the other chat already had (2026-10-25). So
# before any chat decides there is no profile, it looks: here, on master, on another chat's
# unlanded branch; and /setup marks its own run in profile/place.json ("setup": started,
# finished), so a chat that finds a profile still being written waits rather than starts.

STILL_GOING = "Your setup is still going in your other chat; I'll be ready here once it's done."
STOPPED = ("Your setup stopped part-way in another chat. Say \"carry on\" and I'll finish it "
           "here.")
SET_UP_HERE = "Your search is already set up; this computer is ready for it too."
SET_UP = "Your search is already set up."
# A setup whose profile has had no new commit for this long has stopped, not slowed.
STALLED_HOURS = 6


def _git(*args, timeout: int = 30) -> str:
    try:
        r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _at(ref: str, rel: str) -> str | None:
    """A file's text at a ref, or None when it is not there."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:{rel}"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _setup_mark(text: str | None) -> dict:
    try:
        got = json.loads(text or "{}")
    except ValueError:
        return {}
    mark = got.get("setup") if isinstance(got, dict) else None
    return mark if isinstance(mark, dict) else {}


def _going(mark: dict, last_commit: float | None, now: float, chat: str = "") -> str:
    """"" for a setup that finished (or a profile from before the mark), "self" when this
    chat is the one setting up, "going" or "stopped" otherwise."""
    if not mark.get("started") or mark.get("finished"):
        return ""
    if chat and mark.get("chat") == chat:
        return "self"
    if last_commit is not None and now - last_commit > STALLED_HOURS * 3600:
        return "stopped"
    return "going"


def setup_state(now: float | None = None, chat: str | None = None, fetch: bool = True) -> dict:
    """Where the person's search stands, for a chat about to decide whether to run /setup.

    {"state", "ref", "say", "do"}: "here" (a profile in this folder), "self" (this chat is
    the one setting it up), "landed" (on master, not yet here), "branch" (on another chat's
    branch that never reached master), "going" (being written by another chat now),
    "stopped" (written part-way, nothing new for STALLED_HOURS), or "none" (nowhere: run
    /setup). `say` is the one line for the person, or ""."""
    import time
    now = time.time() if now is None else now
    chat = this_chat() if chat is None else chat

    def last(ref: str) -> float | None:
        got = _git("log", "-1", "--format=%ct", ref, "--", "profile").strip()
        return float(got) if got.isdigit() else None

    here = os.path.join(ROOT, "profile")
    if os.path.isfile(os.path.join(here, "person.json")):
        try:
            with open(os.path.join(here, PLACE_FILE), encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = None
        going = _going(_setup_mark(text), last("HEAD"), now, chat)
        if going:
            return {"state": going, "ref": "HEAD", "say": {"self": "", "going": STILL_GOING,
                                                          "stopped": STOPPED}[going],
                    "do": {"self": "carry on with /setup where it is",
                           "going": "start nothing: another chat is writing the profile",
                           "stopped": "on \"carry on\", finish /setup from what is written"}[going]}
        return {"state": "here", "ref": "HEAD", "say": "", "do": "set up: never run /setup "
                "again here; it is not a reset"}
    if fetch:
        _git("fetch", "-q", "origin", timeout=60)
    found = []
    if _at("origin/master", "profile/person.json") is not None:
        found.append("origin/master")
    unlanded = [b.strip() for b in _git("branch", "-r", "--no-merged", "origin/master").splitlines()
                if b.strip() and "->" not in b]
    found += [b for b in unlanded if _at(b, "profile/person.json") is not None]
    for ref in found:
        going = _going(_setup_mark(_at(ref, f"profile/{PLACE_FILE}")), last(ref), now, chat)
        if going in ("going", "stopped"):
            return {"state": going, "ref": ref,
                    "say": STILL_GOING if going == "going" else STOPPED,
                    "do": ("start nothing: another chat is writing the profile" if going == "going"
                           else f"on \"carry on\", bring in {ref} (git merge {ref}) and finish "
                                "/setup from what is written")}
    if found:
        ref = found[0]
        how = ("python3 tools/sync_app.py --pull" if ref == "origin/master"
               else f"git merge {ref}, as a command of its own, then land it on master")
        return {"state": "landed" if ref == "origin/master" else "branch", "ref": ref, "say": "",
                "do": f"bring it in ({how}): the search is set up; never run /setup again"}
    return {"state": "none", "ref": "", "say": "", "do": "no profile anywhere: run /setup"}


def mark_setup(event: str, today: datetime.date | None = None) -> str:
    """/setup's own mark in profile/place.json: "started" with the first profile commit,
    "finished" at its end."""
    import person
    if event not in ("started", "finished"):
        raise SystemExit("place: started or finished")
    if not person.exists("person.json"):
        raise SystemExit("place: write profile/person.json first; the mark goes beside it")
    got = _place()
    mark = dict(got.get("setup") or {})
    day = (today or datetime.date.today()).isoformat()
    if event == "started":
        mark = {"started": mark.get("started") or day, "chat": this_chat()}
    else:
        mark = dict(mark, finished=day)
    got["setup"] = mark
    p = _profile_file()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(got, fh, indent=2)
        fh.write("\n")
    return p


def default_profile_reads(where: str) -> str:
    """PROFILE_READS written without asking: "browser" on a computer, or in a cloud chat the
    desktop app started (it reads in the desktop app's browser); "" (unset, so a paste) on a
    phone or the web. A question and its warnings came first before (2026-10-25)."""
    return "browser" if where in ("local", "desktop-cloud") else ""


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
                           capture_output=True, timeout=10,
                           encoding="utf-8", errors="replace").stdout.strip()
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
                  works=works_on(), has_local=has_local(), os_name=sys.platform)
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
                    choices=("check", "how", "ask", "record", "next", "auto", "state", "started",
                             "finished"))
    ap.add_argument("answer", nargs="?", default="")
    ap.add_argument("--tools", default=None,
                    help="the browser tools this chat has: browser, chrome, chrome-off, enable, none")
    ap.add_argument("--employer", default="")
    ap.add_argument("--works-on", default="")
    ap.add_argument("--once", action="store_true",
                    help="say nothing if this chat was told these words in the last week")
    a = ap.parse_args(argv)
    if a.cmd == "ask":
        print(f"{QUESTION} {TRADE_OFF} {RECOMMEND}")
        return 0
    if a.cmd == "state":
        got = setup_state()
        print(f"state: {got['state']}" + (f" ({got['ref']})" if got["ref"] else ""))
        if got["say"]:
            print(f"say: {got['say']}")
        print(f"do: {got['do']}")
        return 0
    if a.cmd in ("started", "finished"):
        print(f"place: setup {a.cmd}, in {os.path.relpath(mark_setup(a.cmd), ROOT)}")
        return 0
    if a.cmd == "auto":
        got = auto_answer(surface())
        if not got:
            print(f"ask, once, at the end of setup: {QUESTION} {TRADE_OFF} {RECOMMEND}")
            return 0
        print(f"place: recorded {got} in {os.path.relpath(record(got), ROOT)} (not asked: "
              "this chat can tell)")
        reads = default_profile_reads(surface())
        if reads:
            print(f"profile reads: write PROFILE_READS = \"{reads}\" in profile/networking.py, "
                  "asking nothing")
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
                      a.employer, detail=True, works=works_on(), has_local=has_local(),
                      os_name=sys.platform)
        print("\n".join(lines) or "place: this chat is the right place")
        return 0
    out = report(tools, a.employer, a.once)
    print(out or "place: this chat is the right place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
