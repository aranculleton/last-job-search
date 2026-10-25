#!/usr/bin/env python3
"""One short line at the end of a reply, now and then, on how to get more out of this.

The first time a person does a kind of work (a search, an application, a round of people
to write to, an interview pack), the first result is the one least fitted to them, and
nothing told them so or that saying what is off makes the next one better. After that,
someone using it every day never learned that a draft can be redone in one word, or that
a reaction sticks. A line every reply would be noise, so this decides when:

- the first time a kind of work is done: one line saying the first go may be off, and how
  to say so;
- after that, now and then: one tip, never two days running, and the same kind of work at
  most once a week; each tip once, in order, and none once they are all used;
- never, once the person said no more tips (`off`).

It is counting and dates, no model call. What has been shown is kept in
`profile/tips.json`, so a new chat does not say a first-time line again.

    python3 tools/tips.py <area>       # the line to end the reply with, or nothing
    python3 tools/tips.py off          # the person said no more tips
    python3 tools/tips.py on           # they want them back

Areas: search, apply, networking, reply, interview, prep, brief, general.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import person  # noqa: E402

FILE = "tips.json"
AREAS = ("search", "apply", "networking", "reply", "interview", "prep", "brief", "general")
GAP_DAYS = 2            # at most one line in this many days, a first-time line aside
AREA_DAYS = 7           # and the same kind of work at most once in this many

# The first time each kind of work is done.
FIRST = {
    "search": "This is your first search here, so the ranking won't be perfect yet. Tell me "
              "what's off (\"too junior\", \"not this kind of company\") and the next one "
              "learns from it.",
    "apply": "This is your first application here. Tell me anything you'd change in the "
             "wording or what it leads with, and it sticks for the next one.",
    "networking": "This is your first round of people and notes, so some may be off. Tell me "
                  "who you wouldn't contact or what you'd say differently, and it sticks.",
    "reply": "If my reply doesn't sound like you, say how you'd put it; I learn your voice "
             "from what you change.",
    "interview": "This is your first interview pack. Tell me which questions felt wrong or "
                 "missing, and the next one fits you better.",
    "prep": "This is your first call prep. After the call, tell me how it went and what was "
            "missing, and the next one is better for it.",
    "brief": "This is your first brief. Tell me what you'd want more or less of, and the "
             "next one changes.",
    "general": "Anything I make for you can be changed: say what's off and it sticks.",
}

# (id, the areas it suits, the line). "general" suits every area. Each says a thing the app
# does today, in plain words.
TIPS = (
    ("rephrase", ("general", "apply", "networking", "reply"),
     "Tip: say \"shorter\", \"warmer\" or \"rephrase this\" on anything I write. I learn your "
     "style from what you change."),
    ("reaction-sticks", ("general", "search", "networking"),
     "Tip: a reaction like \"not this kind of company\" or \"too formal\" sticks for every "
     "later round, until you change your mind."),
    ("owe", ("general", "networking", "reply", "brief"),
     "Tip: ask \"what do I owe?\" any time for the replies and follow-ups that are due."),
    ("tell-me", ("general", "apply", "interview", "networking"),
     "Tip: tell me when something happens (\"they replied\", \"I got an interview\", \"I "
     "sent it\") and I keep the record and time the follow-ups."),
    ("paste-link", ("general", "search", "apply"),
     "Tip: you can paste any job link or posting and I'll score it and write the "
     "application."),
    ("sent-words", ("networking", "reply"),
     "Tip: if you change a note before sending it, paste me what you sent. Your edits teach "
     "me how you write."),
    ("why-person", ("networking",),
     "Tip: ask \"why this person?\" and I'll say what makes them worth writing to."),
    ("score-why", ("search",),
     "Tip: ask why a job scored what it did; every score comes with its reasons."),
    ("mock", ("interview", "prep"),
     "Tip: ask for a mock interview. I ask the questions, you answer, and I tell you what "
     "landed."),
    ("questions-asked", ("interview",),
     "Tip: after an interview, tell me the questions they asked. The next pack uses them."),
)


def _path() -> str:
    return person.path(FILE)


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def save(state: dict) -> None:
    with open(_path(), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _day(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# Work the message log shows was done before, whatever tips.json says. Each chat keeps its
# own copy of that file until its work lands, and a repo older than the file has none, so
# a person on their thirteenth round of notes that day was told it was their first
# (2026-10-24). A first note or a reply that went is in the log for good; what a round
# drafts and has not sent yet is not, so the first round still hears the first line.
DONE_BEFORE = {
    # A first note that went, by the names the log has used for one. A bare request is
    # not a note anyone drafted.
    "networking": ("connection_note", "first_message", "first_note"),
    "reply": ("reply",),
}


def done_before(area: str) -> bool:
    """Has the person done this kind of work before, by the message log?"""
    scenarios = DONE_BEFORE.get(area)
    if not scenarios:
        return False
    try:
        with open(person.state("network_threads.csv"), newline="", encoding="utf-8") as fh:
            return any(str(r.get("direction") or "").strip() == "out"
                       and str(r.get("scenario") or "").strip() in scenarios
                       for r in csv.DictReader(fh))
    except (OSError, csv.Error):
        return False


def line(area: str, today: dt.date | None = None, state: dict | None = None) -> str:
    """The line for this reply, or "", and `state` updated to say it was shown."""
    today = today or dt.date.today()
    area = area if area in AREAS else "general"
    state = load() if state is None else state
    if state.get("off"):
        return ""
    firsts = state.setdefault("first", {})
    if area not in firsts:
        firsts[area] = today.isoformat()
        if not done_before(area):
            state["last"] = today.isoformat()
            return FIRST[area]
    last = _day(state.get("last"))
    if last and (today - last).days < GAP_DAYS:
        return ""
    areas = state.setdefault("areas", {})
    here = _day(areas.get(area))
    if here and (today - here).days < AREA_DAYS:
        return ""
    shown = state.setdefault("shown", {})
    for tip_id, suits, text in TIPS:
        if tip_id not in shown and (area in suits or "general" in suits):
            shown[tip_id] = today.isoformat()
            areas[area] = state["last"] = today.isoformat()
            return text
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if not person.exists("person.json"):
        return 0                      # the app itself, or a repo not set up: nothing to say
    if argv[0] in ("off", "on"):
        state = load()
        state["off"] = argv[0] == "off"
        save(state)
        print("tips: " + ("none from now on" if state["off"] else "back on, now and then"))
        return 0
    state = load()
    said = line(argv[0], state=state)
    if said:
        save(state)
        print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main())
