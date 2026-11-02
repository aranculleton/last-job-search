#!/usr/bin/env python3
"""One short line at the end of a reply, now and then, on how to get more out of this.

The first time a person does a kind of work (a search, an application, a round of people
to write to, an interview pack), the first result is the one least fitted to them, and
nothing told them so or that saying what is off makes the next one better. After that,
someone using it every day never learned that a draft can be redone in one word, or that
a reaction sticks. A line every reply would be noise, so this decides when:

- the first time a kind of work is done: one line saying the first go may be off, and how
  to say so, and no more than two of those in a day (setup's own day says two: the first
  shortlist and the first application);
- after that, now and then: one tip, never two days running, and the same kind of work at
  most once a week; each tip once, in order, and none once they are all used;
- never, once the person said no more tips (`off`).

It is counting and dates, no model call. What has been shown is kept in
`profile/tips.json`, so a new chat does not say a first-time line again.

    python3 tools/tips.py <area>       # the line to end the reply with, or nothing
    python3 tools/tips.py tour         # "show me around": what they can say, short
    python3 tools/tips.py tour <topic> # "how do I ...?": one thing, in a few lines
    python3 tools/tips.py off          # the person said no more tips
    python3 tools/tips.py on           # they want them back

The tour is never pushed on anyone: setup's last message offers it in one line, a tip
offers it once later to someone who never took it, and Claude runs it when they ask what
the app can do or how to use a part of it. What the tour showed is not tipped again.

Areas: search, apply, networking, reply, interview, prep, brief, general.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import person  # noqa: E402
import local_path  # noqa: E402

FILE = "tips.json"
AREAS = ("search", "apply", "networking", "reply", "interview", "prep", "brief", "general")
GAP_DAYS = 2            # at most one line in this many days, a first-time line aside
AREA_DAYS = 7           # and the same kind of work at most once in this many
FIRSTS_A_DAY = 2        # first-time lines in one day; a third waits for its next time

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
    ("tour", ("general",),
     "Tip: say \"show me around\" for a short tour of what else I can do."),
    ("pin", ("general",),
     "Tip: say \"pin my page\" and I'll pin your job search page to your sidebar, one tap away."),
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
    ("build-resume", ("apply", "search"),
     "Tip: say \"build my resume\" for a fresh one-page resume, made with you step by step."),
    ("look", ("apply",),
     "Tip: say how you want your resume to look (\"navy\", \"bigger text\") and it sticks."),
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
# Said once, after the first tip (never a first-time line), so nobody has to wonder how to
# stop them.
OFF_HINT = " Say \"no more tips\" to stop these."
# A tip the tour already covered is not tipped again; the tour tip itself is skipped once
# they have taken the tour.
COVERED_BY = {"owe": "owe", "paste-link": "apply", "build-resume": "resume", "look": "look",
              "why-person": "people", "score-why": "jobs", "mock": "interview"}

# "Show me around": one line a topic, in the words they would say. Each detail is a few
# short lines on one thing, never a manual. Each says a thing the app does today.
TOUR = (
    ("jobs", "\"find me jobs\": a scored shortlist of new roles, with links",
     "Say \"find me jobs\" and I search the job sites and employers' own careers pages, "
     "score every role out of 100 against what you want, and show you the best, with links. "
     "Nothing is applied for: you choose. Tell me what's off (\"too junior\") and the next "
     "search learns from it."),
    ("apply", "paste a job link: a resume and cover letter written for it",
     "Paste a job link or the posting's text. I score it first; if you want it, I write a "
     "resume and cover letter for that job, check every claim against what you told me, and "
     "give you both. You send them yourself."),
    ("resume", "\"build my resume\": a fresh one-page resume, made with you",
     "Say \"build my resume\" and we make one together: I start from your LinkedIn where I "
     "can, then ask a few short questions about each job. You get a one-page resume for the "
     "work you want, and every tailored one starts from it."),
    ("people", "\"who should I talk to at <employer>?\": people worth writing to",
     "Ask \"who should I talk to at <employer>?\" and I find people there worth writing to, "
     "say why each one, and draft a short first note asking for a chat, not a job. You send "
     "it; tell me when you have, and I keep track."),
    ("replies", "paste a reply you got: I draft yours and time the follow-up",
     "When someone writes back, paste their message. I draft your reply in your voice, keep "
     "the conversation on record, and tell you when a follow-up is due."),
    ("interview", "\"I've got an interview at <employer>\": a prep pack and a mock interview",
     "Tell me you've got an interview and where. I build a prep pack: the questions they're "
     "likely to ask with your best examples, what to ask them, and facts about the employer "
     "with their sources. Ask for a mock interview and I'll play the interviewer."),
    ("owe", "\"what do I owe?\": replies and follow-ups that are due",
     "Ask \"what do I owe?\" for everything due: replies, follow-ups on applications that "
     "have gone quiet, and anything you said you'd do."),
    ("look", "\"make my resume navy\" or \"bigger text\": how your documents look",
     "Say how you want your documents to look: \"make my resume navy\", \"bigger text\", "
     "\"centre my name\". It sticks for every one after, and a kind of employer can have "
     "a look of its own."),
    ("brief", "\"move my brief\": change when your brief arrives",
     "Your brief arrives on its days with what's due and news that matters to your search. "
     "Say \"move my brief\" to change the days or the time."),
)
# The same, on the page: one short card a tab, each pointing at its one button, and the
# first-time lines in the page's words ("Say what's off in Chat"), never a chat's ("tell
# me"). Nothing here runs unasked: the tour opens from Settings, a tip shows once at the end
# of its tab (CAPABILITY_MAP G15).
# The page's walkthrough: it opens each section in turn and says what it is for, following
# one job from found to applied, then the people and the interviews (2026-10-28). `tab` is
# the page's own section id.
PAGE_TOUR = (
    {"key": "brief", "tab": "brief", "title": "Brief",
     "text": "Your day at a glance: what is booked, the next three things to do, who is "
             "waiting on you, the best new jobs, news that matters to your search and your "
             "numbers. Tap any line to go to it."},
    {"key": "todo", "tab": "todo", "title": "To do",
     "text": "What needs you, five at a time, most urgent first: a question, a follow-up "
             "that is due, an interview coming up. Each card has one button, and a bin."},
    {"key": "jobs", "tab": "jobs", "title": "Jobs",
     "text": "Every role from found to applied. Found: scored out of 100 for how well it "
             "fits you; tap Draft this on one you like. Drafts: your resume and letter, "
             "checked; get the files, apply on the employer's site, tap I have applied. "
             "Applied: each one tracked, its follow-ups back in To do."},
    {"key": "contacts", "tab": "contacts", "title": "Contacts",
     "text": "Why people: someone inside who puts your name forward gets you far more "
             "interviews than applying cold. Claude finds who to write to and drafts a short "
             "note; you send it on LinkedIn yourself. Messages holds the notes ready to send. "
             "Tap a name to see everything about that person."},
    {"key": "interviews", "tab": "interviews", "title": "Coming up",
     "text": "Everything booked or due, by day: interviews, calls, tests and closing days. "
             "Add any of it to your calendar in a tap, and add anything else with Add "
             "something. Interviews shows each one's prep: what they will ask, your answers, "
             "your questions."},
    {"key": "settings", "tab": "settings", "title": "Settings",
     "text": "Your profile is the first thing here: your jobs, skills, education and "
             "certificates. Change them any time, and every new resume picks from them."},
    {"key": "chat", "tab": "chat", "title": "Chat",
     "text": "Ask anything, or paste a link, a message or a screenshot and say what you want. "
             "Claude does it, and the result shows up where it belongs."},
)
# The same lines on the page, in its own words: a button where the page has one, Chat only
# where it has none. A chat's tip with no page version is not shown there (asking "what do I
# owe?" is what To do already shows). A pattern over the chat's words garbled these
# ("Type "shorter" in Chat, "warmer" or ...", 2026-10-29).
PAGE_FIRST = {
    # Plain sentences a first-time reader gets at once: "a job that's off ... the next search
    # learns" read as shorthand nobody could parse (the maintainer, 2026-10-30).
    "search": "These are your first results, so the order may be a bit off. Tap the bin on any "
              "job that's wrong for you and say why, and the next search will do better.",
    "apply": "Your first application. Tap Edit on the resume or the letter to change the "
             "wording, and the next one will use your changes.",
    "networking": "Your first messages, so some may be a bit off. Tap Edit to change how one "
                  "reads, or bin someone you wouldn't contact. Claude remembers both.",
    "reply": "If a reply doesn't sound like you, change it before you send it, then paste what "
             "you sent in Chat so Claude learns how you write.",
    "interview": "Your first interview prep. Tap Edit to change what it covers, and the next one "
                 "will fit you better.",
    "prep": "Your first call prep. After the call, tell Claude in Chat how it went.",
    "brief": "Your first brief. Tap Edit the brief to get more or less of anything.",
    "general": "You can change anything Claude makes: tap Edit on it, and Claude remembers for "
               "next time.",
}
PAGE_TIPS = {
    "rephrase": "Tap Edit on anything Claude writes to make it shorter, warmer or reworded. "
                "Claude learns your style from your changes.",
    "tour": "For a short tour of the page, go to Settings, then Help, then Show me around.",
    "reaction-sticks": "When you bin a job, Claude asks why. Your answer applies to every "
                       "future search until you change your mind.",
    "tell-me": "When you hear back, tap I heard back on the application, or paste their message "
               "under Got a message. Claude updates your records and reminds you to follow up.",
    "paste-link": "Paste any job link into Add a job on Jobs. Claude scores it and can write "
                  "the application.",
    "sent-words": "If you change a message before you send it, paste what you sent in Chat so "
                  "Claude learns how you write.",
    "mock": "Ask for a practice interview in Chat. Claude asks the questions, you answer, and it "
            "tells you what went well.",
    "questions-asked": "After an interview, tell Claude in Chat which questions they asked. "
                       "Your next prep will use them.",
    # Pinning is the page's own offer (app_listen.pin_due) and its button in Settings, so it
    # is not a tip as well.
}


def for_page(text: str) -> str:
    """A tip in the page's words (PAGE_FIRST, PAGE_TIPS), or "" when the page has no version
    of it and shows none."""
    for area, first in FIRST.items():
        if text == first:
            return PAGE_FIRST[area]
    said = text.replace(OFF_HINT, "")
    key = next((k for k, _, t in TIPS if t == said), "")
    return PAGE_TIPS.get(key, "")


TOUR_OPEN = "Here's what you can say:"
TOUR_CLOSE = ("Say \"tell me more about\" any of these for a few lines on it, or just ask "
              "how to do something.")


def _path() -> str:
    return person.path(FILE)


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _on_master() -> dict:
    """The copy another chat has already landed, so two chats open the same day (the
    cloud and the computer, or the brief's own) do not each give a tip. Read from the last
    fetch, no network; nothing when the file is not in the repo or git is missing."""
    rel = local_path.rel(_path(), ROOT)
    if rel.startswith(".."):
        return {}
    try:
        out = subprocess.run(["git", "-C", ROOT, "show", "origin/master:" + rel.replace(os.sep, "/")],
                             capture_output=True, encoding="utf-8", errors="replace",
                             timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode:
        return {}
    try:
        got = json.loads(out.stdout)
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def _merge(a: dict, b: dict) -> dict:
    """Both chats' records as one: the earliest a thing was first shown, the latest a line
    was given, and the later of their on/off choices."""
    out = dict(a)
    for key, pick in (("first", min), ("shown", min), ("areas", max)):
        mine, theirs = a.get(key) or {}, b.get(key) or {}
        if isinstance(mine, dict) and isinstance(theirs, dict):
            merged = {}
            for k in set(mine) | set(theirs):
                got = [str(v) for v in (mine.get(k), theirs.get(k)) if v]
                if got:
                    merged[k] = pick(got)
            out[key] = merged
    for key, pick in (("last", max), ("toured", min)):
        got = [str(v) for v in (a.get(key), b.get(key)) if v]
        if got:
            out[key] = pick(got)
    seen = set(a.get("tour_seen") or []) | set(b.get("tour_seen") or [])
    if seen:
        out["tour_seen"] = sorted(seen)
    if a.get("told_off") or b.get("told_off"):
        out["told_off"] = True
    choices = [x for x in (a, b) if "off" in x]
    if choices:
        latest = max(choices, key=lambda x: str(x.get("off_set") or ""))
        out["off"] = bool(latest.get("off"))
        if latest.get("off_set"):
            out["off_set"] = latest["off_set"]
    return out


def load() -> dict:
    return _merge(_read(_path()), _on_master())


def local() -> dict:
    """This copy's own tips file, without what another chat has landed."""
    return _read(_path())


def save(state: dict) -> None:
    """Keep what was said, except in the app's example person: run there, as the app's tests
    and a chat in the app do, it wrote profile.example/tips.json, which learned.py refuses
    for the same reason (networking audit, 2026-10-25)."""
    if person.in_example(_path()):
        return
    with open(_path(), "w", encoding="utf-8", newline="\n") as fh:
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
    import csv_store
    try:
        return any(str(r.get("direction") or "").strip() == "out"
                   and str(r.get("scenario") or "").strip() in scenarios
                   for r in csv_store.dict_rows(person.state("network_threads.csv"),
                                                refuse=False))
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
        if done_before(area):
            firsts[area] = today.isoformat()
        elif sum(str(v)[:10] == today.isoformat() for v in firsts.values()) >= FIRSTS_A_DAY:
            # Setup's day already said its two (the first shortlist, the first application):
            # this kind of work hears its line the next time it is done, not on top.
            return ""
        else:
            firsts[area] = state["last"] = today.isoformat()
            return FIRST[area]
    last = _day(state.get("last"))
    if last and (today - last).days < GAP_DAYS:
        return ""
    areas = state.setdefault("areas", {})
    here = _day(areas.get(area))
    if here and (today - here).days < AREA_DAYS:
        return ""
    shown = state.setdefault("shown", {})
    seen = set(state.get("tour_seen") or [])
    for tip_id, suits, text in TIPS:
        if tip_id in shown or not (area in suits or "general" in suits):
            continue
        if (tip_id == "tour" and state.get("toured")) or COVERED_BY.get(tip_id) in seen:
            continue
        shown[tip_id] = today.isoformat()
        areas[area] = state["last"] = today.isoformat()
        if not state.get("told_off"):
            state["told_off"] = True
            text += OFF_HINT
        return text
    return ""


def tour(topic: str = "", today: dt.date | None = None, state: dict | None = None) -> str:
    """What "show me around" says, or the few lines on one topic. Never refuses: a topic it
    does not know gets the list, so the person sees what there is."""
    today = today or dt.date.today()
    state = load() if state is None else state
    want = (topic or "").strip().lower()
    match = [t for t in TOUR if want and (want == t[0] or want in t[1].lower())]
    seen = set(state.get("tour_seen") or [])
    state.setdefault("toured", today.isoformat())
    if match:
        key, _, detail = match[0]
        state["tour_seen"] = sorted(seen | {key})
        return detail
    state["tour_seen"] = sorted(seen | {t[0] for t in TOUR})
    return "\n".join([TOUR_OPEN] + [f"- {menu}" for _, menu, _ in TOUR] + [TOUR_CLOSE])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if not person.exists("person.json"):
        return 0                      # the app itself, or a repo not set up: nothing to say
    if argv[0] == "tour":
        state = load()
        print(tour(" ".join(argv[1:]), state=state))
        save(state)
        return 0
    if argv[0] in ("off", "on"):
        state = load()
        state["off"] = argv[0] == "off"
        state["off_set"] = dt.datetime.now().isoformat(timespec="seconds")
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
