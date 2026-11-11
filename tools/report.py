#!/usr/bin/env python3
"""A fault in the app, carried to its makers only when the person chooses to, and a copy
stuck in one state for days, noticed.

A stranger has no line to the app's makers but GitHub's public issues, and before this the
only way there was one row deep in the page's Settings: a chat that met a crash or a landing
that never went green was told to say nothing, and a copy could sit unpublished or half set
up for days with nobody hearing (the stranger audit, 2026-11-03). Two things here:

- `link()`: the address of a new issue on the app's public page, filled in with what went
  wrong in the app's own words only: the version, the command (the tool and its subcommand,
  never an argument), the kind of error (its class name) and the names of the stuck states.
  Nothing of the person's can reach it: every part is checked against a fixed shape, so a
  name, a path or a message never passes. It is a link: nothing is ever sent. The person
  opens it and writes what happened, or does not.
- `stuck()`: each state a copy can sit in that the person or the app's makers should hear
  about, with the day it began, read from what the copy already holds (when setup started,
  when the last answer came, the oldest commit of work waiting to land), so a copy that has
  been stuck for days is told on its first chat after the update, not days later.
  `app.py start` and the page's To do say each once (`app.py told report-<state>`).

    python3 tools/report.py link [--command "tools/app.py view"] [--error KeyError] [--state page]
    python3 tools/report.py stuck            # the stuck states, oldest first, as JSON
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

ROOT = os.path.dirname(_HERE)
ISSUES = "https://github.com/aranculleton/last-job-search/issues/new"
# How old a state is before it is worth a word: a day.
STUCK_DAYS = 1
# The states, each with what the person is told (plain, one line) and the issue's words.
STATES = {
    "page": ("Your job search page has not been made yet.",
             "the page was never published"),
    "setup": ("Your setup stopped part-way, with every answer in.",
              "setup stopped after every answer was given"),
    "waiting": ("Some of Claude's work has not been saved into your search yet.",
                "work waits on a branch and never landed"),
}
_COMMAND = re.compile(r"^(?:python3? )?(?:\./)?tools/[a-z_]+\.(?:py|sh)(?: [a-z][a-z_-]{0,30})?$")
_ERROR = re.compile(r"^[A-Z][A-Za-z]{2,40}(?:Error|Exception|Exit|Failed|Refused)?$")
_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def _clean_command(command: str) -> str:
    """The tool and its subcommand only ("tools/app.py view"), or "" for anything else."""
    words = str(command or "").split()
    words = [w for w in words if not w.startswith("-")][:3]
    if words and words[0] in ("python", "python3"):
        words = words[1:]
    got = " ".join(words[:2])
    return got if _COMMAND.match(got) else (words[0] if words and _COMMAND.match(words[0])
                                            else "")


def _version() -> str:
    try:
        import release
        secs = release.sections()
        v = str(secs[0]["version"]) if secs else ""
    except Exception:  # noqa: BLE001  no changelog to read: no version said
        v = ""
    return v if _VERSION.match(v) else ""


def _where() -> str:
    import place
    return "a cloud chat" if place.in_cloud() \
        else "a chat on a computer"


def link(command: str = "", error: str = "", states=(), version: str | None = None) -> str:
    """A new issue on the app's public page, carrying the app's own words only."""
    version = _version() if version is None else (version if _VERSION.match(str(version)) else "")
    command = _clean_command(command)
    error = error if _ERROR.match(str(error or "")) else ""
    states = [s for s in dict.fromkeys(states or ()) if s in STATES]
    what = (STATES[states[0]][1] if states else f"{error} in {command}" if error and command
            else error or command or "something looks wrong")
    title = f"From a copy: {what}" + (f" (version {version})" if version else "")
    body = [f"Version: {version or 'not known'}", f"Where: {_where()}"]
    if command:
        body.append(f"Command: {command}")
    if error:
        body.append(f"Error: {error}")
    for s in states:
        body.append(f"Stuck: {STATES[s][1]}")
    body += ["", "What happened (this page is public: no names, please):", ""]
    return f"{ISSUES}?title={quote(title)}&body={quote(chr(10).join(body))}"


# ------------------------------------------------------------------ what has been stuck, since when


def _git(*args) -> str:
    try:
        r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _oldest(*days) -> dt.date | None:
    got = [d for d in days if d]
    return min(got) if got else None


def _setup_began() -> dt.date | None:
    import app_setup
    mark = (app_setup.read_json(os.path.join(app_setup.profile_dir(), "place.json"), {})
            .get("setup") or {})
    stamps = [_day(v.get("at")) for v in app_setup.answers().values() if isinstance(v, dict)]
    return _oldest(_day(mark.get("started")), *stamps)


def _last_answer() -> dt.date | None:
    import app_setup
    got = [_day(v.get("at")) for v in app_setup.answers().values() if isinstance(v, dict)]
    got = [d for d in got if d]
    return max(got) if got else None


def stuck(today: dt.date | None = None, st: dict | None = None) -> list[dict]:
    """[{"state", "since", "days", "say", "link"}], oldest first: each state the copy has sat
    in for STUCK_DAYS or more. `st` is app_setup.state() where the caller has read it."""
    import app_setup
    today = today or dt.date.today()
    out = []
    try:
        st = st or app_setup.state()
    except Exception:  # noqa: BLE001  no copy to read: nothing stuck that can be said
        return []
    if st["repo"]["kind"] not in ("private", "unknown", "copy"):
        return []
    page = st.get("page") or {}
    if not page.get("url") and not app_setup._no_page_recently(page, today):
        out.append(("page", _setup_began()))
    if app_setup._setup_open(st) and st["setup"]["state"] not in ("going", "landed", "branch"):
        if all((st["answers"].get(s) or {}) for s in app_setup.STEP_IDS):
            out.append(("setup", _last_answer()))
    try:
        import land
        refs = land.waiting(ROOT)
    except Exception:  # noqa: BLE001
        refs = []
    if refs:
        days = [_day(_git("log", "--reverse", "--format=%as", "origin/master.." + r).split("\n")[0])
                for r in refs]
        out.append(("waiting", _oldest(*days)))
    got = []
    for state, since in out:
        if not since:
            continue
        days = (today - since).days
        if days >= STUCK_DAYS:
            got.append({"state": state, "since": since.isoformat(), "days": days,
                        "say": STATES[state][0], "link": link(states=[state])})
    return sorted(got, key=lambda x: x["since"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("link", help="a new issue on the app's page, carrying nothing of theirs")
    p.add_argument("--command", default="")
    p.add_argument("--error", default="")
    p.add_argument("--state", action="append", default=[])
    sub.add_parser("stuck", help="the states this copy has been stuck in, as JSON")
    a = ap.parse_args(argv)
    if a.cmd == "link":
        print(link(a.command, a.error, a.state))
        return 0
    print(json.dumps(stuck(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
