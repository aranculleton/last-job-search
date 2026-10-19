#!/usr/bin/env python3
"""The interview pack for one stage of one tracked application.

/interview built its pack by hand from a page of instructions, while the call prep
for a networking thread (`tools/network/prep.py`) is code: every fact sourced or
left out, a band nobody looked up printed as "not researched", prohibitions before
facts, stale research said, banned phrases flagged. The interview pack goes in
front of the people deciding the hire and had none of it. This builds it from what
the search already holds, through prep.py's own functions, so both documents keep
one set of rules:

  the application's folder   the posting, the portal's answers (screening_answers.md,
                             form_fields.txt), outcome.md's stages and notes
  the draft it was sent from what the letter argued, its requirement map, any
                             concession (`what_works.draft_for`)
  the profile                the gaps and their honest framings (`profile_facts`,
                             `bridges`), the STAR stories and hard answers
                             (`profile/07-interview-prep.md`)
  the research cache         prohibitions first, then sourced facts
  the money                  what the form already said, and the band behind it
                             (`screening_answers`), sourced or not printed
  the question bank          what came up before, and which stories landed
  the contact book           a referrer to tell, an interviewer already known

Nothing here writes what the person will say: every answer is the profile's or the
record's own wording, placed against a question. The model's one job is to map
stories to the questions the `Use for:` tags do not already reach, and to add any
question earlier feedback raises; it passes both in with `--map`.

The pack leads with one screen (five likely questions with what to answer with,
three hooks, the money line, what not to say), then the detail.

    python3 tools/interview_pack.py pack "<Company>" [--role R] [--stage "Phone screen"]
            [--date YYYY-MM-DD] [--with "<name or title>"] [--map map.json] [--write]
    python3 tools/interview_pack.py asked --company C --role R --stage S --question "..."
            [--story "<story title>"] [--landed yes|partly|no] [--note "..."]
    python3 tools/interview_pack.py rework --company C --role R --stage S
            --question "..." --note "..."
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridges  # noqa: E402
import csv_store  # noqa: E402
import learned  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import profile_facts  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import untrusted  # noqa: E402
import voice_check  # noqa: E402
import what_works  # noqa: E402
from company_key import key as company_key  # noqa: E402

ROOT = os.path.dirname(_HERE)
GUIDES = os.path.join(ROOT, ".claude", "skills", "job-application-assistant")
APP_GUIDE = os.path.join(GUIDES, "07-interview-prep.md")
APP_EVALUATION = os.path.join(GUIDES, "04-job-evaluation.md")
STORIES_FILE = "07-interview-prep.md"
# The salary table screening_answers.py reads, named the same way it names it.
EVALUATION = person.file("evaluation", "04-job-evaluation.md")

SECTIONS = ("On one screen", "Your answers", "What they have been told", "Who you are meeting",
            "The format", "Likely questions", "Stories", "What the paper says", "Gaps and honest framing",
            "Money and eligibility", "The company", "Small talk", "Ask them", "Warm route",
            "Earlier stages", "To rework", "Notes")
# One living document per employer process, beside the application: every answer the person
# changes is changed here, and it is sent to them again each time. The material had lived in
# four places (a prep file per contact, a pack per stage, notes kept by hand, the chat), and
# a person asked for one. The sections the person writes in are kept across every rebuild.
LIVING = "interview_prep.md"
OWNED = ("Your answers", "To rework", "Notes")
FOUND_OUT = "### What you found out"
FOUND_EMPTY = "- Nothing yet: each line added here, with its source, stays."
NOTES_EMPTY = "- Nothing yet: anything you want kept, write it here."
TO_WRITE = "[to write: said aloud, first person, whole sentences, contractions welcome]"
LAST_UPDATED = re.compile(r"^Last updated (\d{4}-\d{2}-\d{2})\.", re.M)
_STAGES_MARK = re.compile(r"^<!-- stages: (.*?) -->$", re.M)

# One screen is what is read in the minutes before: five questions, three hooks,
# one money line, four things not to say. The detail below is for the night before.
ONE_SCREEN_QUESTIONS = 5
HOOKS = 3
MAX_DO_NOT = 4
MAX_QUESTIONS = 18
MAX_REQUIREMENTS = 3
MAX_FORM_LINES = 8
MAX_RECORD = 24   # lines of the person's own outcome record
RECORD_ITEM = 200
MAX_ASK = 6
MAX_NEVER_SAY = 5
MAX_GAP_NOTES = 3
# How close a question has to be to a story's `Use for:` tag for the tag to count.
MATCH = 0.34
# A story that landed for a like question before is a better bet, and one that fell
# flat a worse one; the bank moves the match by this much either way.
BANK_NUDGE = 0.25
# How much of the letter's evidence a story has to carry to be the story behind it.
EVIDENCE_MATCH = 0.3

# What each step is most likely to ask, before anything this application says.
# `{company}` is the employer's name.
STAGE_QUESTIONS = {
    "screen": ("Tell me about yourself.", "Why are you looking?", "Why {company}?",
               "What are your salary expectations?", "Do you need sponsorship?",
               "What is your notice period, and when could you start?",
               # What a recruiter's screen asks that the six above do not: written by hand
               # for a real screen because the pack lacked them.
               "Where are you based?", "Why are you leaving your current role?",
               "Walk me through your career, and the moves between jobs.",
               "Walk me through a project in sixty seconds.",
               "And one with a commercial result?",
               "Tell me about a time you led something.",
               "Are you interviewing anywhere else?"),
    "technical": ("Walk me through a project end to end.", "Tell me about yourself."),
    "final": ("Why {company}?", "Do you have any reservations about the role?",
              "Where do you see yourself in five years?", "What are your salary expectations?"),
    "offer": (),
}
# The app guide's question categories each step draws on (07-interview-prep.md,
# "Questions You Should Ask Interviewers"). The categories only: its answers and
# stories are the example person's.
STEP_CATEGORIES = {"screen": ("About the Role", "About the Team"),
                   "technical": ("About Tech & Growth", "About the Team"),
                   "final": ("About Culture",), "offer": ()}


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _rel(path) -> str:
    """A path in the person's state (documents/...), as the pack names it."""
    return os.path.relpath(path, person.state()).replace(os.sep, "/")


def _repo_rel(path) -> str:
    """A path in the repo (profile/..., .claude/...), as prep.PROFILE_SOURCE names one."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def _read(path) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def pack_name(stage) -> str:
    """`interview_prep_<stage>.md`, the name open_actions.py looks for."""
    return "interview_prep_%s.md" % (re.sub(r"[^a-z0-9]+", "_", _text(stage).lower()).strip("_")
                                     or "interview")


# ---------------------------------------------------------------- the person's stories

_HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
_STAR = re.compile(r"^(situation|task|action|result|s|t|a|r)\s*:\s*(.+)$", re.I)
_USE_FOR = re.compile(r"^use\s+for\s*:\s*(.*)$", re.I)
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")


def _flat(line) -> str:
    """A markdown line as words: no bullet, no emphasis."""
    return _text(re.sub(r"^\s*[-*]\s+", "", line).replace("**", "").replace("__", ""))


def _sections(text) -> list:
    out, current = [], None
    for line in str(text or "").splitlines():
        m = _HEADING.match(line)
        if m:
            current = (m.group(2).strip(), [])
            out.append(current)
        elif current is not None:
            current[1].append(line)
    return out


def _tags(text) -> list:
    quoted = [_text(q) for q in _QUOTED.findall(text)]
    return quoted or [t for t in (_text(x) for x in re.split(r"[,;]", text)) if t]


def stories(path=None) -> list:
    """Every STAR story in the person's file: {title, theme, star, use_for, source}.

    A story is a heading whose body has a Situation and a Result, in either of the
    two shapes the app writes (`- **Situation:** ...` or `**S:** ...`). `use_for`
    is empty for a story with no `Use for:` line, which `untagged` reports.
    """
    path = path or person.path(STORIES_FILE)
    out = []
    for heading, body in _sections(_read(path)):
        parts, use_for = {}, []
        for line in body:
            flat = _flat(line)
            m = _STAR.match(flat)
            if m:
                parts[m.group(1)[0].upper()] = m.group(2).strip()
                continue
            m = _USE_FOR.match(flat)
            if m:
                use_for = _tags(m.group(1))
        if "S" not in parts or "R" not in parts:
            continue
        title = re.sub(r"^(?:STAR\s*:\s*|\d+\.\s*)", "", heading, flags=re.I).strip()
        theme = ""
        m = re.match(r"^(.*?)\s*\(([^)]*)\)$", title)
        if m:
            title, theme = m.group(1), m.group(2)
        out.append({"title": title[:1].upper() + title[1:], "theme": theme, "star": parts,
                    "use_for": use_for, "source": _repo_rel(path)})
    return out


def untagged(path=None) -> list:
    """The titles of stories with no `Use for:` line, which no question can reach."""
    return [s["title"] for s in stories(path) if not s["use_for"]]


def hard_answers(path=None) -> list:
    """{question, answer, confirm, source} for each question heading with a quoted answer.

    An answer still holding a `[PLACEHOLDER` is not an answer and is left out; one
    marked `[CONFIRM` is kept and said to be unconfirmed.
    """
    path = path or person.path(STORIES_FILE)
    out = []
    for heading, body in _sections(_read(path)):
        if "?" not in heading and not heading.startswith(('"', "“")):
            continue
        quoted = [m.group(1) for m in (re.match(r"^\s*>\s?(.*)$", ln) for ln in body) if m]
        answer = _text(" ".join(quoted))
        if not answer or "[PLACEHOLDER" in answer:
            continue
        confirm = "[CONFIRM" in answer
        answer = _text(re.sub(r"`?\[CONFIRM:[^\]]*\]`?", "", answer).replace("**", ""))
        # "Suits: product, bank" and "Not for: consulting": the employers a stock answer is
        # for. Untagged, an answer is read for words that argue against the employer.
        tags = {}
        for ln in body:
            m = re.match(r"^\s*(suits|not for)\s*:\s*(.+)$", ln, re.I)
            if m:
                tags[m.group(1).lower()] = tuple(t.strip().lower() for t in m.group(2).split(",")
                                                 if t.strip())
        out.append({"question": heading.strip("\"“” "), "answer": answer,
                    "confirm": confirm, "source": _repo_rel(path),
                    "suits": tags.get("suits", ()), "not_for": tags.get("not for", ())})
    return out


# ---------------------------------------------------------------- matching

_STOP = frozenset("""a an the and or of to in on for with you your me my i about how what why when
where do does did is are was were have has had tell time this that it as at be by from walk
through give example describe us our we can could would will there their they them any some
one most""".split())


def _words(text) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if w in _STOP or len(w) < 3:
            continue
        if len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def similar(a, b) -> float:
    """Shared content words over all content words, 0 to 1."""
    x, y = _words(a), _words(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def best_story(question, story_list, bank_rows=()) -> tuple:
    """(story, score) whose `Use for:` tags best fit the question, or (None, 0)."""
    best, top = None, 0.0
    for st in story_list:
        score = max((similar(question, tag) for tag in st["use_for"]), default=0.0)
        for row in bank_rows:
            if _text(row.get("story")).lower() != st["title"].lower():
                continue
            if similar(row.get("question"), question) < 0.5:
                continue
            landed = _text(row.get("landed")).lower()
            score += BANK_NUDGE if landed == "yes" else -BANK_NUDGE if landed == "no" else 0
        if score > top:
            best, top = st, score
    return (best, top) if top >= MATCH else (None, 0.0)


def story_for_evidence(evidence, story_list) -> dict | None:
    """The story whose own words carry the letter's evidence, or None.

    Overlap over the evidence's words, not over both: a story is a paragraph and
    the evidence a line, so a share of the union would never clear the bar.
    """
    want = _words(evidence)
    best, top = None, 0.0
    for st in story_list:
        have = _words(" ".join([st["title"]] + list(st["star"].values())))
        score = len(want & have) / len(want) if want else 0.0
        if score > top:
            best, top = st, score
    return best if top >= EVIDENCE_MATCH else None


def _answer_for(question, answers) -> dict | None:
    hits = [(similar(question, a["question"]), a) for a in answers]
    hits = [h for h in hits if h[0] >= 0.5]
    return max(hits, key=lambda h: h[0])[1] if hits else None


# ---------------------------------------------------------------- the application

# A hiring process with no application in it: a referral that led to a recruiter's call,
# or a recruiter who came to the person. Applying through the portal as well would put a
# second, worse record of the same person in front of them, so there is no application to
# track; but the interview stages, the brief and the throttle all read the tracker. So the
# process gets a row of its own: status `interview`, its channel (referral, recruiter), no
# documents, its source the contact who led it, and a note saying it is not an application.
PROCESS_NOTE = throttle.PROCESS_NOTE
_LIVE_CONTACT = frozenset({"call_booked", "referral_in_progress", "replied_needs_response",
                           "in_conversation"})


is_process = throttle.is_process


def _row(company, role, tracker, contacts=None) -> dict:
    """The tracker row this pack is for: the employer's, the role's, live first."""
    k = company_key(company)
    rows = [r for r in tracker if k and company_key(r.get("company")) == k]
    if role:
        rows = [r for r in rows if throttle._same_title(role, r.get("role"))]
    live = [r for r in rows if _text(r.get("status")).lower() not in throttle.FINAL]
    pick = live or rows
    if not pick:
        # The strongest lead the search makes, a referral with a recruiter's call booked,
        # has no application, and /interview refused it: name the contacts behind it and
        # the one command that makes it a process the pack, /outcome and the brief can read.
        live_here = [c for c in (contacts or ()) if company_key(c.get("company")) == k
                     and _text(c.get("status")) in _LIVE_CONTACT]
        hint = ""
        if live_here:
            c = live_here[0]
            hint = (". A process runs there with no application: %s. Register it, once: "
                    "python3 tools/interview_pack.py process \"%s\" --contact %s --role \"<the "
                    "role>\" [--stage \"Recruiter screen\" --date YYYY-MM-DD --with \"<who>\"]"
                    % ("; ".join("%s [%s, %s]" % (_text(x.get("name")), _text(x.get("contact_id")),
                                                  _text(x.get("status"))) for x in live_here[:3]),
                       company, _text(c.get("contact_id"))))
        raise LookupError("no application at %r%s in the tracker%s" % (
            company, " for %r" % role if role else "",
            hint or ": /outcome %s registers one" % company))
    roles = sorted({_text(r.get("role")) for r in pick})
    if len(roles) > 1 and not role:
        raise LookupError("%s has %d applications (%s): name the role with --role"
                          % (company, len(roles), "; ".join(roles)))
    return pick[-1]


def _form_answers(text) -> list:
    """(question, answer) pairs from a screening_answers.md."""
    out, question = [], ""
    for line in str(text or "").splitlines():
        m = re.match(r"^###\s+(.*?)\s*(?:\*\*\(decide per application\)\*\*)?\s*$", line)
        if m:
            question = m.group(1).strip()
            continue
        m = re.match(r"^\*\*(.+)\*\*\s*$", line.strip())
        if m and question:
            out.append((question, m.group(1).strip()))
            question = ""
    return out


# The sections of outcome.md that are not the person's own words: the stage checklist,
# which the Held and Booked lines already carry.
_RECORD_SKIP = re.compile(r"^interview stages reached$", re.I)
_RECORD_HEAD = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_LABEL_LINE = re.compile(r"^\s*\*\*[^*]{1,40}:\*\*")      # "**Who:** ..." starts its own item
_LEAD = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")


def _gist(item) -> str:
    """One item of the record as a line: its bold headline when it opens with one ("The
    referral is confirmed."), the whole item when the bold is a label ("Who: ..."), and
    otherwise its first sentence."""
    item = _text(item)
    m = _LEAD.match(item)
    if m:
        lead, rest = m.group(1).strip(), m.group(2).strip()
        if lead.endswith((".", "!", "?")) and rest:
            return lead
        # A label ("Who:") or a headline the sentence runs on from ("Likely shape of the
        # two rounds**, from ...") is read with the rest.
        item = (lead + ("" if rest[:1] in ",;:." else " ") + rest).strip()
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", item, maxsplit=1)[0]
    return prep.clip(first.replace("**", ""), RECORD_ITEM)


def _record(text) -> list:
    """[(heading, line)]: what the person wrote in outcome.md, every section of it.

    The file /outcome writes keeps its notes under one Notes heading; a file written by
    hand has a heading per round with its own sections ("What was learned", "Owed"), and
    reading the Notes heading alone left all of that out of the pack. Everything before
    the first heading (the title and the status) and the stage checklist are skipped."""
    out, heading, item, skipping = [], "", [], True

    def flush():
        if item and not skipping:
            line = _gist(" ".join(item))
            if line and not line.startswith("<"):
                out.append((heading, line))
        item.clear()

    for raw in str(text or "").splitlines():
        m = _RECORD_HEAD.match(raw)
        if m:
            flush()
            heading = m.group(2).strip()
            skipping = bool(_RECORD_SKIP.match(heading))
            continue
        if not raw.strip() or raw.lstrip().startswith("<"):
            flush()
            continue
        if _ITEM.match(raw) or _LABEL_LINE.match(raw):
            flush()
            item.append(_ITEM.sub("", raw).strip())
        else:
            item.append(raw.strip())
    flush()
    return out


def _next_stage(stages, today="") -> dict:
    """The stage this pack is for, when none is named: the next one booked, else the next undone.
    A booked stage whose date has passed and nobody ticked was most likely held: it is passed
    over, as a held one would be."""
    past = [i for i, s in enumerate(stages) if s["scheduled"] and not s["done"]
            and today and s.get("date") and s["date"] < today]
    booked = [s for i, s in enumerate(stages) if s["scheduled"] and not s["done"] and i not in past]
    if booked:
        return booked[0]
    done = [i for i, s in enumerate(stages) if s["done"] or i in past]
    after = stages[(done[-1] + 1) if done else 0:]
    if after:
        return after[0]
    # Every stage on record held and none booked: the next is the next round, never the
    # "Phone screen" a pack assumes when nothing is on record at all.
    return {"label": "Round %d" % (len(stages) + 1), "date": "", "with": ""} if stages else {}


def register_process(company, contact_id, role, stage="", date="", with_="", today=None,
                     contacts=None) -> tuple:
    """Make a hiring process with no application something every reader can see: a
    tracker row (PROCESS_NOTE) and its folder with an outcome.md, the booked stage on it
    when given. Returns (row, folder, added). Run twice, it changes nothing."""
    import record_drafts
    today = _text(today) or dt.date.today().isoformat()
    # Read where gather() reads, at call time: the state root, not a path fixed at import.
    contacts = state.load_contacts(person.state("network_contacts.csv")) if contacts is None \
        else contacts
    c = state.already_contacted(contacts, contact_id=_text(contact_id))
    if c is None:
        raise LookupError("no contact %r in the contact book: the process is led by someone in it"
                          % contact_id)
    company = _text(company) or _text(c.get("company"))
    if company_key(company) != company_key(c.get("company")):
        raise ValueError("%s works at %s, not %s" % (_text(c.get("name")), _text(c.get("company")),
                                                     company))
    if not _text(role):
        raise ValueError("name the role this process is for (--role), as the recruiter or the "
                         "referral named it: the folder and every later stage are filed under it")
    name = state.person_name(c.get("name")) or _text(c.get("name"))
    for label, value in (("--date", date), ("--today", today)):
        if _text(value) and state.as_date(_text(value)) is None:
            raise ValueError("%s %r is not a date: write it YYYY-MM-DD" % (label, value))
    tracker_path = person.state("job_search_tracker.csv")
    rows = csv_store.read_rows(tracker_path, record_drafts.HEADER)
    k = company_key(company)
    have = next((r for r in rows if company_key(r.get("company")) == k
                 and throttle._same_title(role, r.get("role"))
                 and _text(r.get("status")).lower() not in throttle.FINAL), None)
    if have is not None and not is_process(have) \
            and _text(have.get("status")).lower() not in throttle.UNSENT:
        # An application went in for this role: this is its interview, not a process with no
        # application, and making it one would hide the application from every reader.
        raise ValueError("an application for %s at %s is already on record (%s, %s): this call "
                         "is that application's next stage. Record it with /outcome %s, then "
                         "build the prep with pack." % (_text(have.get("role")), company,
                                                        _text(have.get("status")),
                                                        _text(have.get("date")), company))
    referral = (_text(c.get("status")) == "referral_in_progress"
                or _text(c.get("route")).startswith("referral")
                or "referr" in _text(c.get("outcome")).lower())
    process = dict(status="interview",
                   channel="referral" if referral else ("recruiter" if prep.is_recruiter(c)
                                                       else "contact"),
                   contact_person=name, source="contact:%s" % _text(c.get("contact_id")))
    note = ("%s: led by %s (%s) %s; nobody applied through the portal, so this is the only "
            "record" % (PROCESS_NOTE, name, _text(c.get("contact_id")), today))
    added = have is None or not is_process(have)
    if have is None:
        have = {k_: "" for k_ in record_drafts.HEADER}
        have.update(date=today, company=company, role=_text(role), notes=note, **process)
        rows.append(have)
        csv_store.write_rows(tracker_path, rows, record_drafts.HEADER)
    elif not is_process(have):
        # Documents were drafted for this role and never sent: the row becomes the process,
        # so nothing reads it as an application waiting to go, or nudges it.
        have.update(process)
        have["notes"] = "; ".join(x for x in (_text(have.get("notes")), note + "; the drafted "
                                              "documents were never sent") if x)
        csv_store.write_rows(tracker_path, rows, record_drafts.HEADER)
    folder = outreach.app_folder(company, role)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "outcome.md")
    text = _read(out)
    screen_first = bool(_text(stage)) and what_works.stage_step(stage) == "screen"
    if not text:
        text = ("# Outcome: %s - %s\n\n**Status:** in_progress\n\n## Interview stages reached\n"
                "%s- [ ] Technical interview\n- [ ] Case interview\n- [ ] Final round\n"
                "- [ ] Offer received\n\n## Notes\n- %s: a process with no application, led "
                "by %s.\n" % (company, role, "" if screen_first else "- [ ] Phone screen\n",
                              today, name))
    if _text(stage):
        line = "- [ ] %s%s" % (stage, " (scheduled %s%s)" % (
            date, ", with %s" % with_ if _text(with_) else "") if _text(date) else "")
        # The same stage booked again (a new date, a new interviewer) replaces its line.
        same = re.compile(r"^- \[ \] %s(?:\s*\(.*\))?\s*$" % re.escape(stage), re.M | re.I)
        hits = list(same.finditer(text))
        if hits:
            # The first keeps its place with the new date; any later copies go, line and all.
            for m in reversed(hits[1:]):
                end = m.end() + 1 if text[m.end():m.end() + 1] == "\n" else m.end()
                text = text[:m.start()] + text[end:]
            text = text[:hits[0].start()] + line + text[hits[0].end():]
        else:
            text = text.replace("## Interview stages reached\n",
                                "## Interview stages reached\n%s\n" % line, 1)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    return have, folder, added


def gather(company, role="", stage="", date="", with_="", today=None, story_map=None,
           tracker=None, contacts=None, threads=None, format_="") -> dict:
    """Everything the pack is built from, read once."""
    root = person.state()
    today = _text(today) or dt.date.today().isoformat()
    tracker = what_works._csv(os.path.join(root, "job_search_tracker.csv")) if tracker is None \
        else tracker
    contacts = state.load_contacts(os.path.join(root, "network_contacts.csv")) \
        if contacts is None else contacts
    row = _row(company, role, tracker, contacts)
    company, role = _text(row.get("company")) or company, _text(row.get("role")) or role
    folder = outreach.app_folder(company, role)
    if not os.path.isdir(folder):
        # Built from a folder that is not there, a pack has no posting, no form and no
        # stages, and says nothing about it. A folder at this employer under another
        # name is the likely one: name them rather than guess.
        mine = {os.path.basename(outreach.app_folder(_text(r.get("company")), _text(r.get("role"))))
                for r in tracker if company_key(r.get("company")) == company_key(company)
                and r is not row}
        others = [f for f in outreach.employer_folders(company) if f not in mine]
        if others:
            raise LookupError(
                "no application folder %s for %s, %r; this employer has %s. Rename the one "
                "that is this application's to %s, or name the role as its folder does with "
                "--role" % (_rel(folder), company, role, ", ".join(others),
                            os.path.basename(folder)))
    outcome = _read(os.path.join(folder, "outcome.md"))
    stages = what_works.outcome_stages(outcome, today)
    if not stage:
        # Nothing on record yet means the first conversation, which is a screen
        # at nearly every employer; /interview asks, and passes --stage when not.
        found = _next_stage(stages, today)
        stage = found.get("label") or "Phone screen"
        date, with_ = date or found.get("date", ""), with_ or found.get("with", "")
    else:
        same = [s for s in stages if s["label"].lower() == stage.lower()]
        if same:
            date, with_ = date or same[0]["date"], with_ or same[0]["with"]
    posting = untrusted.unfence(_read(os.path.join(folder, "job_posting.md")))
    threads = state.load_threads(os.path.join(root, "network_threads.csv")) \
        if threads is None else threads
    return {
        "company": company, "role": role, "row": row, "folder": folder, "today": today,
        "stage": stage, "step": what_works.stage_step(stage), "date": date, "with": with_,
        "outcome": outcome, "stages": stages, "posting": posting,
        "form": _form_answers(_read(os.path.join(folder, "screening_answers.md"))),
        "form_fields": [ln.rstrip() for ln in _read(os.path.join(folder, "form_fields.txt"))
                        .splitlines() if ln.strip()],
        "outreach_sent": os.path.exists(os.path.join(folder, "outreach.md")),
        "draft": what_works.draft_for(row, what_works.drafts(root)),
        "research": prep.load_research(company, root),
        "facts": profile_facts.build(role=role, posting=posting),
        "gaps_hard": bridges.gaps(" ".join(x for x in (role, posting) if x)),
        "stories": stories(), "answers": hard_answers(),
        "bank": what_works.bank(root), "contacts": contacts, "threads": threads,
        "map": dict(story_map or {}),
        "earlier": sorted(f for f in _listdir(folder)
                          if f.startswith("interview_prep_") and f != pack_name(stage)),
        "rework": _rework_lines(_read(os.path.join(folder, LIVING))
                                or _read(os.path.join(folder, pack_name(stage)))),
        "living": _read(os.path.join(folder, LIVING)),
        "format": _text(format_),
        "process": is_process(row),
        "elsewhere": len({company_key(r.get("company")) for r in tracker
                          if company_key(r.get("company")) != company_key(company)
                          and _text(r.get("status")).lower() in throttle.LIVE_PROCESS}),
    }


def _listdir(folder) -> list:
    try:
        return os.listdir(folder)
    except OSError:
        return []


# ---------------------------------------------------------------- questions

def likely_questions(ctx) -> list:
    """[{question, why, source, framing, evidence}], in the order to prepare them.

    Earlier feedback the session read and mapped first, then what was asked here
    before, then by step: the standard opening questions for a screen, the
    requirements and gaps for a technical round, motivation and reservations for
    a final. A question the profile has nothing for is still asked; the answer
    line says a story has to be drafted.
    """
    company, step = ctx["company"], ctx["step"]
    k = company_key(company)
    out, seen = [], set()

    def add(question, why, source, **extra):
        q = _text(question)
        if q and what_works._norm(q) not in seen:
            seen.add(what_works._norm(q))
            out.append(dict({"question": q, "why": why, "source": source}, **extra))

    bank_src = "/".join(what_works.BANK)
    group = {
        "map": [],
        "here": [(r["question"], "%s (%s, %s)" % (
                      "reported by " + _text(r.get("source")) if _text(r.get("source"))
                      else "asked here before", _text(r.get("stage")) or "a stage",
                      _text(r.get("date")) or "undated"),
                  "%s, recorded in %s" % (_text(r.get("source")), bank_src)
                  if _text(r.get("source")) else bank_src, {}) for r in ctx["bank"]
                 if company_key(r.get("company")) == k and _text(r.get("question"))],
        "again": [],
        "stage": [(q.format(company=company), "what %s usually asks"
                   % what_works.STEP_WORDS.get(step, "an interview"), "the stage", {})
                  for q in STAGE_QUESTIONS.get(step, ())],
        "gaps": [], "reqs": [],
        "cond": [(q, why, "the screen", {}) for q, why in conditional_questions(ctx)],
        "format": [(q, "what %s usually asks" % FORMAT_NAMES[f].lower(), "the format", {})
                   for f in interview_formats(ctx)[0] for q in FORMAT_PREP[f]["questions"]],
    }
    draft = ctx["draft"] or {}
    gaps = [dict(g) for g in ctx["facts"].get("gaps") or []]
    for r in list(draft.get("requirement_map") or []):
        if not isinstance(r, dict) or not _text(r.get("requirement")):
            continue
        req, evidence = _text(r.get("requirement")).rstrip("."), _text(r.get("evidence"))
        # A requirement that is also a gap is one question, asked once: the gap's,
        # carrying what the letter answered it with.
        same = next((g for g in gaps if g["gap"].lower() in req.lower()
                     or similar(g["gap"], req) >= 0.5), None)
        if same is not None:
            same.setdefault("evidence", evidence)
        elif len(group["reqs"]) < MAX_REQUIREMENTS:
            group["reqs"].append(("Tell me about your experience with %s." % re.sub(
                                      r"^(?:(?:proven|strong|solid|demonstrable)\s+)?"
                                      r"experience (?:with|in|of)\s+", "", req, flags=re.I),
                                  "a stated requirement", _text(draft.get("_path")),
                                  {"evidence": evidence, "evidence_source": _text(draft.get("_path"))}))
    group["gaps"] = [("What is your experience with %s?" % g["gap"],
                      "the posting asks for it and the profile does not hold it as such",
                      g["source"], {"framing": g["framing"], "gap": True,
                                    "evidence": g.get("evidence", ""),
                                    "evidence_source": _text(draft.get("_path"))})
                     for g in gaps]
    elsewhere: dict[str, list] = {}
    for r in ctx["bank"]:
        if (company_key(r.get("company")) != k and what_works.stage_step(r.get("stage")) == step
                and not _text(r.get("source"))):
            elsewhere.setdefault(what_works._norm(r.get("question")), []).append(r)
    group["again"] = [(v[-1]["question"], "asked at %d other employers' %s"
                       % (len(v), what_works.STEP_WORDS.get(step, "interviews")), bank_src, {})
                      for v in sorted(elsewhere.values(), key=len, reverse=True) if len(v) > 1]
    # A mapped question nothing here would have asked is one the session read in
    # earlier feedback, and earlier feedback is the likeliest thing to come back.
    known = {what_works._norm(g[0]) for part in group.values() for g in part}
    group["map"] = [(q, "raised by an earlier stage", "the session's map", {})
                    for q in ctx["map"] if what_works._norm(q) not in known]
    stage = group["stage"]
    order = {
        "screen": ["map", "here", stage[:3], group["gaps"][:1], stage[3:6], "cond", "format",
                   stage[6:], "reqs", group["gaps"][1:], "again"],
        "technical": ["map", "here", "reqs", "gaps", "format", "stage", "again"],
        "final": ["map", "here", stage[:1], group["gaps"][:1], "format", stage[1:], "reqs",
                  group["gaps"][1:], "again"],
        "offer": ["map", "here"],
    }[step if step in STAGE_QUESTIONS else "technical"]
    for part in order:
        for question, why, source, extra in (group[part] if isinstance(part, str) else part):
            add(question, why, source, **extra)
    return out[:MAX_QUESTIONS]


# A question about pay, by whole word: "payments data" and "Payward" are not pay.
_PAY_Q = r"\bsalary\b|\bcompensation\b|\bpay\b|\bremuneration\b|\bexpected (?:base|package)\b"


def _form_value(ctx, pattern) -> tuple:
    """(question, answer) from the portal's form whose question matches, or ("", "")."""
    rx = re.compile(pattern, re.I)
    return next(((q, a) for q, a in ctx["form"] if rx.search(q)), ("", ""))


def answer_for(item, ctx) -> dict:
    """What to answer one question with: {kind, short, lines}. Sourced, never written here.

    kind is "story", "prepared", "say" or "none"; short is the one-screen phrase.
    """
    q = item["question"]
    folder = _rel(ctx["folder"])
    facts = ctx["facts"]
    prof = prep._profile_source(facts)
    lines = []
    mapped = ctx["map"].get(q)
    story = None
    if mapped:
        story = next((s for s in ctx["stories"] if s["title"].lower() == _text(mapped).lower()),
                     None)
    how = "mapped"
    if story is None and not mapped:
        story, _score = best_story(q, ctx["stories"], ctx["bank"])
        how = "matched by its Use for tags"
    if story is None and not mapped and item.get("evidence"):
        story = story_for_evidence(item["evidence"], ctx["stories"])
        how = "it carries the letter's evidence"
    prepared = _answer_for(q, ctx["answers"])
    if prepared is None and re.search(r"why are you leaving", q, re.I):
        # The same reason, asked from the other side: the prepared "why are you looking".
        prepared = _answer_for("Why are you looking?", ctx["answers"])
    why_us = bool(re.search(r"^why %s" % re.escape(ctx["company"]), q, re.I))
    if item.get("framing"):
        lines.append("Say: %s (source: %s)" % (item["framing"], item["source"]))
    if item.get("evidence"):
        lines.append("What the letter answered it with: %s (source: %s)"
                     % (item["evidence"], item.get("evidence_source") or item["source"]))
    if re.search(_PAY_Q, q, re.I):
        fq, fa = _form_value(ctx, _PAY_Q)
        if fa:
            lines.append("The form said: %s (source: %s/screening_answers.md). Say the same band."
                         % (fa, folder))
        else:
            target, _floor = _band()
            if target:
                lines.append("Your target band: %s (source: %s). Say it as a range; the floor "
                             "stays unsaid." % (target, _repo_rel(EVALUATION)))
    elif re.search(r"sponsor|right to work|visa", q, re.I):
        fq, fa = _form_value(ctx, r"sponsor")
        if fa:
            lines.append("The form said: %s (source: %s/screening_answers.md). Plainly, no caveat."
                         % (fa, folder))
        elif facts.get("work_authorization"):
            lines.append("%s (source: %s)" % (facts["work_authorization"], prof))
    elif re.search(r"notice", q, re.I):
        fq, fa = _form_value(ctx, r"notice")
        if fa:
            lines.append("The form said: %s (source: %s/screening_answers.md)" % (fa, folder))
    elif re.search(r"about yourself", q, re.I) and facts.get("summary"):
        # The profile's summary is written, not said: never the answer as it stands.
        lines.append("%s %s (source: %s)" % (prep.RAW_MARK, facts["summary"], prof))
    elif re.search(r"where are you based|how are you finding", q, re.I):
        if home_place():
            lines.append("You live in %s (source: profile/person.json)" % home_place())
        if newcomer(ctx):
            lines.append("You moved there %s: see Small talk, and tell nothing you have not "
                         "done." % newcomer(ctx))
    elif re.search(r"moves between jobs|walk me through your career", q, re.I):
        moves = ["%s (%s)" % (_text(e.get("company")), _text(e.get("dates")))
                 for e in facts.get("employers") or [] if isinstance(e, dict) and _text(e.get("company"))]
        if moves:
            lines.append("The moves, newest first: %s (source: %s). Say the one thread that "
                         "joins them, a line a move, ending on why this one." % ("; ".join(moves), prof))
    elif re.search(r"led something|leadership", q, re.I):
        led = [x for x in facts.get("strengths") or [] if re.search(
            r"\b(?:mentor|first|introduc|standard|train|onboard|set up|owned|led)\w*", _text(x), re.I)]
        lines += ["From your profile: %s (source: %s)" % (prep.clip(x, 170), prof) for x in led[:2]]
        lines.append("No people management is claimed that your profile does not hold: lead "
                     "from what you set up, the standards you brought in and who you brought along.")
    elif re.search(r"interviewing anywhere else", q, re.I):
        n = ctx.get("elsewhere", 0)
        lines.append(("Yes: %d other process(es) at an interview stage. Say so, name nobody, and "
                      "invent no offer (source: %s)" % (n, prep.TRACKER_SOURCE)) if n else
                     ("Nothing at an interview stage elsewhere: say you are in early conversations "
                      "if that is true, and invent nothing (source: %s)" % prep.TRACKER_SOURCE))
    elif re.search(r"^how do you know", q, re.I):
        ref = referrer_of(ctx)
        row_ = state.already_contacted(ctx["contacts"], name=ref, company=ctx["company"]) if ref else None
        how = _text((row_ or {}).get("route_detail")) or prep.ROUTE_WORDS.get(
            _text((row_ or {}).get("route")), _text((row_ or {}).get("route")))
        if how:
            lines.append("How you came to know them: %s (source: %s)" % (how, prep.CONTACTS_SOURCE))
    elif re.search(r"after your permit|longer term", q, re.I):
        if facts.get("work_authorization"):
            lines.append("Your status: %s (source: %s). Asked directly, so answer it: what you "
                         "intend, and nothing beyond what your profile says."
                         % (facts["work_authorization"], prof))
    elif re.search(r"willing to travel", q, re.I):
        lines.append("Say what travel works for you, honestly. Your profile records nothing on it: "
                     "add it to 01-candidate-profile.md so the next pack can say it.")
    elif re.search(r"commercial result", q, re.I):
        money_story = next((s for s in ctx["stories"] if re.search(r"[£$€]|\d+%|\bsaved|\brevenue",
                                                                  _text(s["star"].get("R")), re.I)), None)
        if money_story:
            lines.append("Story: %s, the one whose result is money or a number (source: %s)"
                         % (money_story["title"], money_story["source"]))
    elif why_us:
        told = _text((ctx["draft"] or {}).get("p2"))
        if told:
            lines.append("The letter told them: %s (source: %s)"
                         % (told, _text(ctx["draft"].get("_path"))))
        lines.append("Use a hook from The company, never a generic line.")
    if prepared:
        lines.append("Prepared: %s (source: %s)%s" % (
            prepared["answer"], prepared["source"],
            " Marked CONFIRM in the file: check it is still true first." if prepared["confirm"]
            else ""))
        etype = employer_type(ctx)
        against = argues_against(prepared["answer"], etype) if etype not in prepared.get("suits", (etype,)) \
            or etype in prepared.get("not_for", ()) else ""
        if etype and (against or etype in prepared.get("not_for", ())):
            lines.append("CAREFUL: this argues against a %s employer%s, and %s is one. Rewrite it "
                         "from your real reasons for this one before you say it."
                         % (etype, " (\"%s\")" % against if against else " (its Not for: line)",
                            ctx["company"]))
    if story:
        lines.append("Story: %s (%s; source: %s)" % (story["title"], how, story["source"]))
    elif mapped:
        lines.append("Mapped to %r, which is not a story in %s: check the title."
                     % (mapped, STORIES_FILE))
    if story:
        return {"kind": "story", "short": "story: %s" % story["title"], "lines": lines}
    if prepared:
        return {"kind": "prepared", "short": "prepared answer, below", "lines": lines}
    if why_us:
        return {"kind": "say", "short": "a hook below" + (", and what the letter told them"
                                                          if _text((ctx["draft"] or {}).get("p2"))
                                                          else ""),
                "lines": lines}
    if item.get("gap") and not item.get("framing"):
        lines.append("No framing recorded (profile skills.py BRIDGES): write one before the "
                     "interview. Say plainly what you do not hold, then the nearest true thing; "
                     "never claim it.")
        return {"kind": "none", "short": "a gap with no framing yet: write one (Gaps)",
                "lines": lines}
    if lines:
        first = re.sub(r" \(source: .*$", "", lines[0]).replace("The form said: ", "the form said ")
        if first.startswith(prep.RAW_MARK):
            first = "your summary, said your way (Your answers)"
        return {"kind": "say", "short": prep._short(first, 70), "lines": lines}
    lines.append("No story or prepared answer covers this yet: draft one from %s, facts only "
                 "(interview.md Step 3)." % prep.PROFILE_SOURCE)
    return {"kind": "none", "short": "no story yet: draft one", "lines": lines}


# ---------------------------------------------------------------- the other sections

def hooks(ctx) -> list:
    """Sourced facts to hang "why this company" on: the letter's first, then the research."""
    research, draft = ctx["research"] or {}, ctx["draft"] or {}
    out = []
    told = _text(draft.get("p2"))
    if told and _text(draft.get("_path")):
        out.append(prep.sourced(told, draft["_path"]))
    default = prep._research_source(research)
    for raw in list(research.get("facts") or []):
        fact = prep._fact(raw, default)
        if fact is not None:
            out.append(fact)
    out += prep._facts(research.get("recent_news") or research.get("news"), default)
    # A fact only a search summary gave is a lead, so it hangs "why us" last, if at all.
    out.sort(key=lambda f: prep.UNREAD in f.value)
    if len(out) < HOOKS:
        out += [prep.sourced(a, u) for a, u in prep._source_anchors(research)]
    return out


def do_not_say(ctx, never_say=None) -> list:
    """Lines: the research's prohibitions, the credentials not held, the banned phrases."""
    research = ctx["research"] or {}
    default = prep._research_source(research)
    out = ["- Do not say: %s (source: %s)" % (f.value, f.source)
           for f in prep._facts(research.get("do_not_claim"), default)]
    out += ["- Careful: %s (source: %s)" % (f.value, f.source)
            for f in prep._facts(research.get("cautions"), default)]
    for g in ctx["gaps_hard"]:
        out.append("- Never claim %s%s (source: tools/bridges.py)"
                   % (g.asked, ": " + g.note if g.note else ""))
    phrases = [p for p, _rx in (never_say if never_say is not None else learned.never_say())]
    if phrases:
        out.append("- Words you have said never to use: %s (source: %s)" % (
            ", ".join('"%s"' % p for p in phrases[:MAX_NEVER_SAY]), prep.LEARNED_SOURCE))
    out.append("- No claim in the room that is not on the paper they read.")
    return out


def paper_lines(ctx) -> list:
    """What the documents they read argued, so nothing said contradicts them."""
    row, draft = ctx["row"], ctx["draft"] or {}
    src = _text(draft.get("_path"))
    out = []
    files = [f for f in (row.get("cv_file"), row.get("cover_letter_file")) if _text(f)]
    if ctx.get("process"):
        # Nothing was submitted, so nothing a draft argued reached them.
        out.append("- Nothing went in through a portal, so there is no letter or form: what they "
                   "hold is what the messages carried (What they have been told), and any %s "
                   "sent by email or passed on by the referrer." % _noun())
        if files:
            out.append("- Drafted for this role and never sent: %s. Not what they read."
                       % ", ".join(files))
        return out
    if files:
        out.append("- Sent: %s (source: %s)" % (", ".join(files), prep.TRACKER_SOURCE))
    if ctx["outreach_sent"]:
        out.append("- The note drafted for the hiring manager or recruiter: %s/outreach.md. If it "
                   "went, whoever it went to may be on the panel." % _rel(ctx["folder"]))
    if not draft:
        out.append("- No draft.json kept for this application, so what the letter argued is "
                   "not on file: read the letter itself before the interview.")
        return out
    if _text(draft.get("angle")):
        out.append("- The argument: %s (source: %s)" % (_text(draft["angle"]), src))
    for r in draft.get("requirement_map") or []:
        if isinstance(r, dict) and _text(r.get("requirement")):
            out.append("- %s: %s (source: %s)" % (_text(r["requirement"]),
                                                   _text(r.get("evidence")) or "no evidence named", src))
    _company, fit = prep._letter_lines(draft)
    out += fit
    return out


def gap_lines(ctx) -> list:
    """The gaps and their framings, then what the score and the audit already saw.

    `fit_why` (the score's reasons) and `residual_risks` (what the grounding audit
    said an interviewer could probe) are read from the draft when it carries them;
    neither is written to it yet, and a pack built from an older draft goes without.
    """
    out = []
    draft = ctx["draft"] or {}
    src = _text(draft.get("_path"))
    for g in ctx["facts"].get("gaps") or []:
        if g["framing"]:
            out.append("- %s. Say: %s (source: %s)" % (g["gap"], g["framing"], g["source"]))
        else:
            out.append("- %s. No framing recorded: write one before the interview, never on "
                       "the day (source: %s)" % (g["gap"], g["source"]))
    for b in ctx["facts"].get("blockers") or []:
        out.append("- BLOCKER: %s. No framing fixes this. (source: %s)"
                   % (b, prep._profile_source(ctx["facts"])))
    docked = [_text(w) for w in draft.get("fit_why") or [] if _text(w).startswith("-")]
    out += ["- The score docked it: %s (source: %s)" % (w, src) for w in docked[:MAX_GAP_NOTES]]
    out += ["- The grounding audit said an interviewer could probe: %s (source: %s)"
            % (_text(r), src) for r in list(draft.get("residual_risks") or [])[:MAX_GAP_NOTES]
            if _text(r)]
    # Skills the profile does not list that they said yes to claiming on this application:
    # the resume names them, so the interview may well ask.
    out += ["- You said yes to claiming %s on this application: expect a question on it, with a "
            "real example ready (source: %s)" % (_text(k), src)
            for k in draft.get("consented_skills") or [] if _text(k)]
    return out


def _screening():
    """tools/screening_answers.py, or None for a profile with no screening.py.

    Imported here rather than at the top: it reads the profile's screening.py as
    it loads, and a pack with no money facts is still a pack.
    """
    try:
        import screening_answers
        return screening_answers
    except (ImportError, person.NoProfile):
        return None


def _band():
    """(target line, floor) from the salary table, or ("", None) when there is none."""
    sheet = _screening()
    if sheet is None:
        return "", None
    try:
        floor, low, high = sheet.salary_band()
    except sheet.MissingFact:       # no table to read: said where the band is printed
        return "", None
    cur = prep._CURRENCY_CODE
    return ("%s%s to %s" % (cur + " " if cur else "", "{:,}".format(low), "{:,}".format(high)),
            floor)


def _offer_lines() -> list:
    """Total compensation and the caveats, from the person's evaluation rubric."""
    mine = _read(EVALUATION)
    out = []
    for text, src in ((mine, _repo_rel(EVALUATION)),
                      (_read(APP_EVALUATION), _repo_rel(APP_EVALUATION))):
        m = re.search(r"Always report total compensation[^\n]*", text)
        if m:
            out.append("- %s (source: %s)" % (_text(m.group(0)), src))
            break
    m = re.search(r"Two honest caveats[^\n]*\n((?:\s*\d+\.\s[^\n]*\n?)+)", mine)
    for item in re.findall(r"^\s*\d+\.\s+(.*)$", m.group(1), re.M) if m else ():
        if "[PLACEHOLDER" not in item:
            out.append("- Caveat: %s (source: %s)" % (_text(item.replace("**", "")),
                                                      _repo_rel(EVALUATION)))
    if not out:
        out.append("- Total compensation, not base: bonus, pension or retirement match and "
                   "health benefits (source: %s)" % _repo_rel(APP_EVALUATION))
    return out


def money(ctx) -> tuple:
    """(the one-screen line, the section's lines): what the form said, the band, the offer."""
    folder = _rel(ctx["folder"])
    said = [(q, a) for q, a in ctx["form"] if not a.startswith("[")]
    lines = []
    if said:
        lines.append("- The form said (source: %s/screening_answers.md):" % folder)
        lines += ["  - %s **%s**" % (q, a) for q, a in said[:MAX_FORM_LINES]]
    if ctx["form_fields"]:
        lines.append("- Typed into the portal (source: %s/form_fields.txt):" % folder)
        lines += ["  - %s" % ln for ln in ctx["form_fields"][:MAX_FORM_LINES]]
    target, floor = _band()
    if target:
        lines.append("- Your target band: %s. Walk-away floor %s: keep it to yourself. "
                     "(source: %s)" % (target, "{:,}".format(floor),
                                       _repo_rel(EVALUATION)))
        import profile_consistency
        for f in profile_consistency.findings():
            if f["fact"] in ("pay band", "walk-away floor"):
                lines.append("  - CHECK: %s:%d says \"%s\". The band above is the one the "
                             "form answers use: settle which is right before the call."
                             % (f["file"], f["line"], f["said"]))
    else:
        lines.append("- Your band: %s, no salary table in %s. Ask their range rather than quote "
                     "a number you cannot source." % (prep.NOT_RESEARCHED,
                                                       _repo_rel(EVALUATION)))
    lines.append("- Market band:")
    lines += ["  " + ln for ln in prep.comp_band(
        ctx["role"], "", "", prep._comp_sources(ctx["research"], ctx["row"]))]
    sheet = _screening()
    try:
        sponsor = "needed" if sheet.requires_sponsorship() else "not needed"
        lines.append("- Sponsorship: %s. Say it plainly, with no caveat. (source: %s)"
                     % (sponsor, prep.PROFILE_SOURCE))
    except (AttributeError, getattr(sheet, "MissingFact", LookupError)):
        # Never guessed, and never silently left out either.
        lines.append("- Sponsorship: your profile does not say \"no sponsorship required\" or "
                     "\"sponsorship required\" in so many words, so nothing is printed here. Add "
                     "the one that is true to %s." % prep.PROFILE_SOURCE)
    if ctx["step"] == "offer":
        lines += _offer_lines()
    _q, said = _form_value(ctx, _PAY_Q)
    if ctx["step"] == "offer":
        one = "weigh total compensation, not base%s; the floor stays unsaid" % (
            ", against your target %s" % target if target else "")
    elif said:
        one = "the form said %s%s; a recruiter checks what you say against it" % (
            said, ", your target %s" % target if target and target not in said else "")
    elif target:
        one = "nothing on the form; your target is %s, and the floor stays unsaid" % target
    else:
        one = "%s: ask their range first" % prep.NOT_RESEARCHED
    return one, lines


def _guide_categories() -> dict:
    """{category: [questions]} from the app guide's questions to ask."""
    out, current = {}, None
    for heading, body in _sections(_read(APP_GUIDE)):
        if heading.startswith("About "):
            current = heading.split(" (")[0]
            out[current] = [_text(m.group(1)) for m in
                            (re.match(r"^\s*-\s*\"(.+)\"\s*$", ln) for ln in body) if m]
    return out


def ask_lines(ctx) -> list:
    # prep.py anchors its last question on the role and names the contact book,
    # where a call's role comes from; here it is the tracker's.
    out = ["- %s (source: %s)" % (q["question"], prep.TRACKER_SOURCE
                                  if q["anchor"] == ctx["role"] else q["source"])
           for q in prep.questions_for_them(ctx["research"], ctx["role"])]
    cats = _guide_categories()
    for cat in STEP_CATEGORIES.get(ctx["step"], ()):
        for q in [q for q in cats.get(cat, []) if "[" not in q][:2]:
            if len(out) >= MAX_ASK:
                break
            out.append("- %s (the guide's \"%s\" list: cut it if the research already answers it)"
                       % (q, cat))
    return out[:MAX_ASK]


# A row whose own next step says to leave them be: "Keep warm, no action", "Do not use
# him to chase ...", a HOLD or FREEZE, or waiting on their reply ("Wait for his reply":
# the ball is in their court, and a message on top of it is a chase).
_HANDS_OFF = re.compile(r"\bno action\b|\b(?:do not|don'?t) (?:contact|message|use|chase|nudge)\b|"
                        r"^\s*(?:HOLD|FREEZE)\b|"
                        r"\b(?:wait|waiting|await|awaiting)\b(?: (?:for|on))?"
                        r" (?:(?:his|her|their|a|the) )?(?:reply|response|answer)\b|"
                        r"\bleave (?:him|her|them) (?:be|alone)\b", re.I)
# A row's own words, quoted whole up to this length and cut at a word beyond it.
ROW_QUOTE = 140

def _referred(c, ctx, name) -> bool:
    """Did this contact put the candidate forward for this application? Their status or
    route says so, their outcome records a referral, their row links this application,
    or the application's own notes name them beside a referral. The status alone missed
    a referrer whose row was waiting on his reply, with "referral_converted_to_interview"
    as its outcome and his name beside "referral" in the tracker."""
    # A route of "referral" with someone named in `referred_by` says this contact was
    # reached through that person's introduction, not that they put the candidate forward;
    # with nobody named, they are the referral.
    if _text(c.get("status")) == "referral_in_progress" or (
            _text(c.get("route")).startswith("referral") and not _text(c.get("referred_by"))):
        return True
    if "referr" in _text(c.get("outcome")).lower():
        return True
    linked = _text(c.get("linked_application"))
    if linked and linked == _text(ctx["row"].get("cv_file")):
        return True
    if len(name) > 3:
        text = " ".join([_text(ctx["row"].get("notes")), _text(ctx.get("outcome"))]).lower()
        for m in re.finditer(re.escape(name.lower()), text):
            if "referr" in text[max(0, m.start() - 80):m.end() + 80]:
                return True
    return False


def warm_lines(ctx) -> list:
    """Who is already talking to them, and who of the interviewers is already known.
    A row that says to leave someone be is shown with its own words, never with a
    message to send: one said "Keep warm, no action" and the pack told the candidate to
    tell him the interview was booked."""
    k = company_key(ctx["company"])
    here = [c for c in ctx["contacts"] if company_key(c.get("company")) == k]
    names = " ".join(_text(x).lower() for x in [ctx["with"]] + [s["with"] for s in ctx["stages"]])
    out, referrer = [], None
    # "Booked" only when the stage this pack is for has a date: told to say a round was
    # booked that had no date yet, the candidate would be telling them something untrue.
    booked = bool(_text(ctx.get("date")))
    for c in here:
        cid = _text(c.get("contact_id"))
        status = state.effective_status(c, state.threads_for(ctx["threads"], cid))
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        title = ", " + _text(c.get("title")) if _text(c.get("title")) else ""
        step = _text(c.get("next_action"))
        if _referred(c, ctx, name):
            referrer = referrer or name
        if step and _HANDS_OFF.search(step):
            out.append("- %s%s [%s]: their row says to leave them be for now: \"%s\". "
                       "(source: %s)" % (name, title, status, prep.clip(step, ROW_QUOTE), prep.CONTACTS_SOURCE))
            continue
        if len(name) > 3 and name.lower() in names:
            known = ["documents/network/%s/%s" % (cid, f) for f in ("prep.md", "reading.json")
                     if cid and os.path.exists(person.state("documents", "network", cid, f))]
            out.append("- %s%s is interviewing you and is in your contact book [%s]%s. "
                       "(source: %s)" % (name, title, status, ": reuse " + " and ".join(known)
                                         if known else "", prep.CONTACTS_SOURCE))
        elif _referred(c, ctx, name):
            then = (" Their row's next step: \"%s\"." % prep.clip(step, ROW_QUOTE)) if step else ""
            tell = ("Tell them the interview is booked, and thank them after it." if booked else
                    "Tell them once the interview has a date, and thank them after it.")
            out.append("- %s%s put you forward [%s]. %s%s (source: %s)"
                       % (name, title, status, tell, then, prep.CONTACTS_SOURCE))
        elif status in throttle.RESPONDED:
            out.append("- %s%s is already talking to you [%s]: %s (source: %s)"
                       % (name, title, status, "tell them it is booked." if booked else
                          "tell them once it has a date.", prep.CONTACTS_SOURCE))
    channel = _text(ctx["row"].get("channel"))
    if referrer:
        out.append("- How did you hear about us: through %s. (source: %s)"
                   % (referrer, prep.CONTACTS_SOURCE))
    elif channel:
        out.append("- How did you hear about us: %s. (source: %s)" % (channel, prep.TRACKER_SOURCE))
    return out


def earlier_lines(ctx) -> list:
    src = "%s/outcome.md" % _rel(ctx["folder"])
    out = ["- %s %s%s (source: %s)" % ("Held:" if s["done"] else "Booked:", s["label"],
                                       " " + s["date"] if s["date"] else "", src)
           for s in ctx["stages"] if s["date"]]
    record = _record(ctx["outcome"])
    out += ["- %s%s (source: %s)" % (h + ": " if h and h.lower() != "notes" else "", n, src)
            for h, n in record[:MAX_RECORD]]
    if len(record) > MAX_RECORD:
        out.append("- And %d more in %s." % (len(record) - MAX_RECORD, src))
    out += ["- Earlier pack: %s/%s" % (_rel(ctx["folder"]), f) for f in ctx["earlier"]]
    return out


def _story_lines(ctx) -> list:
    out = []
    for s in ctx["stories"]:
        out.append("- **%s**%s (source: %s)" % (s["title"], " (%s)" % s["theme"] if s["theme"]
                                                 else "", s["source"]))
        for part in "STAR":
            if s["star"].get(part):
                out.append("  - %s: %s" % (part, s["star"][part]))
        out.append("  - Use for: %s" % ("; ".join(s["use_for"]) if s["use_for"] else
                                        "none written, so no question reaches it: add a "
                                        "`Use for:` line in %s" % STORIES_FILE))
    return out


REWORK_EMPTY = "Nothing yet. A mock interview adds the answers to work on here."


def _rework_lines(text) -> list:
    """The lines kept under "To rework" in an existing pack, carried into the next."""
    m = re.search(r"^## To rework\s*$", str(text or ""), re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)
    body = body[:nxt.start()] if nxt else body
    # Every line the person kept there, bullet or not; only the placeholder goes.
    return [ln.rstrip() for ln in body.splitlines() if ln.strip() and REWORK_EMPTY not in ln]


# ---------------------------------------------------------------- who, where, what was said

# The person.json values the pack reads, written out so a reader of the profile's names
# (tools/profile_names.py) sees each one.
_PERSON = {
    "identity.moved": lambda: person.get("identity.moved", ""),
    "identity.area": lambda: person.get("identity.area", ""),
    "identity.location": lambda: person.get("identity.location", ""),
}


def _noun() -> str:
    """The person's word for the document, as their profile says it (a resume, or a CV)."""
    try:
        return _text(person.get("documents.noun", "resume")) or "resume"
    except person.NoProfile:
        return "resume"


def _person(dotted) -> str:
    """One optional value from person.json, "" when the profile does not hold it."""
    try:
        return _text(_PERSON[dotted]())
    except person.NoProfile:
        return ""


def referrer_of(ctx) -> str:
    """The name of whoever put the candidate forward for this process, or ""."""
    k = company_key(ctx["company"])
    for c in ctx["contacts"]:
        if company_key(c.get("company")) != k:
            continue
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        if _referred(c, ctx, name):
            return name
    return ""


# Words that say a status is temporary: a permit, a visa, a working holiday. Read from the
# profile's own work-authorization wording, never guessed.
_TEMPORARY = re.compile(r"\b(?:permit|visa|working holiday|temporary|fixed[- ]term|expires?|"
                        r"until \d{4})\b", re.I)


def temporary_status(ctx) -> bool:
    """Read from the work-authorization facts, with every sentence about sponsorship taken
    out first: "No visa sponsorship required" says nothing about a permit."""
    said = re.sub(r"[^.]*\bsponsor\w*[^.]*\.?", " ",
                  _text(ctx["facts"].get("work_authorization")), flags=re.I)
    return bool(_TEMPORARY.search(said))


MOVED_MONTHS = 12


def newcomer(ctx) -> str:
    """The month the person moved, when it was within MOVED_MONTHS (person.json
    identity.moved), else ""."""
    moved = _person("identity.moved")
    when = state.as_date(moved + ("-01" if re.fullmatch(r"\d{4}-\d{2}", moved) else ""))
    today = state.as_date(ctx["today"]) or dt.date.today()
    if when is None or (today - when).days > MOVED_MONTHS * 31 or when > today:
        return ""
    return moved


def home_place() -> str:
    """Where the person lives, as their profile says it."""
    return _person("identity.area") or _person("identity.location")


# What an employer is, read from the tracker's sector, the research and the name: the
# kind of place a stock answer can argue against.
EMPLOYER_TYPES = (
    ("consulting", re.compile(r"\b(?:consult(?:ing|ancy|ancies|ants?)|advisory (?:firm|services|"
                              r"practice)|professional services)\b", re.I)),
    ("public sector", re.compile(r"\b(?:public sector|government|ministry|city council|county "
                                 r"council|(?:government|public|federal|provincial|state) "
                                 r"agency|nhs|municipal)\b", re.I)),
    ("bank", re.compile(r"\b(?:banks?|banking|insurers?|insurance|asset manage\w*|pension "
                        r"funds?|financial services)\b", re.I)),
    ("startup", re.compile(r"\b(?:start-?up|seed|series [abc]|scale-?up)\b", re.I)),
    ("product", re.compile(r"\b(?:saas|software|platform|product company|tech company|"
                           r"marketplace|app)\b", re.I)),
)


def employer_type(ctx) -> str:
    """The kind of employer, from the most direct source that names one: the tracker's
    sector, then the research's own sector words, then the name, then what the research
    says it does. A bank whose summary mentions a wealth-advisory arm is a bank."""
    research = ctx["research"] or {}
    # The person's own rule for what counts as public sector (profile/search.py BAR_PUBLIC,
    # read by tools/bar.py) outranks the generic words below; their pension funds never do.
    try:
        import bar
        name = "%s %s" % (ctx["company"], company_key(ctx["company"]))
        if bar.PUBLIC.search(name) and not bar.PENSIONS.search(name):
            return "public sector"
    except (ImportError, person.NoProfile, AttributeError):
        pass
    for text in (ctx["row"].get("sector"),
                 " ".join(_text(research.get(k)) for k in ("sector", "industry", "type")),
                 ctx["company"],
                 " ".join(_text(research.get(k)) for k in ("summary", "what_they_do"))):
        found = next((t for t, rx in EMPLOYER_TYPES if rx.search(_text(text))), "")
        if found:
            return found
    return ""


# A stock answer that argues against the kind of employer it is about to be said to:
# "depth over a rotating client portfolio" and "product companies rather than more
# consulting" were both about to be used for a consulting firm.
_AGAINST = {
    "consulting": re.compile(r"(?:rather than|instead of|away from|not|less|over|leave|leaving|"
                             r"tired of)\b[^.]{0,50}\b(?:consult\w*|client portfolio|rotating "
                             r"clients?|client work|clients)\b|depth over[^.]{0,30}\bclient", re.I),
    "product": re.compile(r"(?:rather than|instead of|away from|over)\b[^.]{0,40}\bproduct\b", re.I),
    "bank": re.compile(r"(?:rather than|instead of|away from|leave|leaving)\b[^.]{0,40}"
                       r"\b(?:bank\w*|financ\w*)\b", re.I),
    "public sector": re.compile(r"(?:rather than|instead of|away from|leave|leaving)\b[^.]{0,40}"
                                r"\b(?:public sector|government)\b", re.I),
    "startup": re.compile(r"(?:rather than|instead of|away from)\b[^.]{0,40}\bstart-?ups?\b", re.I),
}


def argues_against(answer, etype) -> str:
    """The words in `answer` that argue against an employer of `etype`, or ""."""
    rx = _AGAINST.get(etype)
    m = rx.search(_text(answer)) if rx else None
    return m.group(0) if m else ""


# What the people at this employer have been told, by topic. A recruiter screen checks
# location and start date first, and the referrer had been told by message five weeks
# before that the candidate was "moving" and "currently at a UK consultancy", while the
# profile said the move was complete.
TOLD_TOPICS = (
    ("where you are", re.compile(r"\b(?:(?:moving|move|moved) (?:to|from|over|here)|relocat\w*|"
                                 r"based in|living in|will be in|arriv\w*|from the (?:uk|us)|"
                                 r"currently in)\b", re.I)),
    ("current employer", re.compile(r"\b(?:currently (?:at|with|working)|i work (?:at|for)|"
                                    r"now at|at the moment i|i'm at|i am at|consult\w* (?:at|for))\b",
                                    re.I)),
    ("work authorization", re.compile(r"\b(?:sponsor\w*|visa|permit|right to work|work "
                                      r"authori[sz]ation|eligible to work|entitled to work)\b",
                                      re.I)),
    ("notice or start", re.compile(r"\b(?:notice|start(?:ing)? (?:on|in|from|date)|available "
                                   r"(?:from|to start)|could start)\b", re.I)),
    # An amount only beside a currency sign or a word for pay: "250k customers" is not pay.
    ("pay", re.compile(r"(?:[$£€]\s?\d|\b(?:salary|compensation|base pay|pay of|package|"
                       r"looking for around|expecting)\b)", re.I)),
)


def _said(text) -> list:
    """[(topic, sentence)] for every sentence of `text` on a topic a screen checks."""
    out = []
    text = _text(text).replace("\\n", "\n").replace("\u2019", "'").replace("\u2018", "'")
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        sent = sent.strip()
        for topic, rx in TOLD_TOPICS:
            if sent and rx.search(sent):
                out.append((topic, sent))
    return out


def _differs_from_band(sent) -> bool:
    """Does `sent` name pay outside the person's target band? Amounts are read as amounts
    (110,000, 110000, 110k): a "000" in the band is not a match for every round number."""
    import profile_consistency as pc
    sheet = _screening()
    try:
        _floor, low, high = sheet.salary_band()
    except (AttributeError, getattr(sheet, "MissingFact", LookupError)):
        return False
    for m in pc._RANGE.finditer(sent):
        if (pc._amount(m.group(1)), pc._amount(m.group(2))) != (low, high):
            return True
    rest = pc._RANGE.sub(" ", sent)
    return any(not low <= pc._amount(m.group(1)) <= high
               for m in pc._SINGLE.finditer(rest) if pc._amount(m.group(1)) >= 1000)


def told_lines(ctx) -> list:
    """Every message to anyone at this employer, and what the form said, on the topics a
    screen checks first, each with a line where it disagrees with the profile now."""
    k = company_key(ctx["company"])
    here = {_text(c.get("contact_id")): c for c in ctx["contacts"]
            if company_key(c.get("company")) == k}
    out, seen = [], set()
    moved = _person("identity.moved")
    current = [n for e in ctx["facts"].get("employers") or [] if isinstance(e, dict)
               and "present" in _text(e.get("dates")).lower()
               for n in (_text(e.get("company")),) if n]
    for r in ctx["threads"]:
        cid = _text(r.get("contact_id"))
        if cid not in here or _text(r.get("direction")).lower() not in ("out", "outbound", "sent"):
            continue
        name = state.person_name(here[cid].get("name")) or _text(here[cid].get("name"))
        for topic, sent in _said(r.get("full_text")):
            key = (topic, sent.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append("- %s, to %s, on %s: \"%s\" (source: %s)" % (
                _text(r.get("date")) or "undated", name, topic, prep.clip(sent, 180),
                prep.THREADS_SOURCE))
            if topic == "where you are" and moved and re.search(
                    r"\b(?:moving (?:to|from|over|here)|relocating|move to|will be in)\b",
                    sent, re.I):
                out.append("  - DIFFERS: they were told you were moving; your profile says you "
                           "moved (%s). Say \"I made the move\" plainly if it comes up." % moved)
            if topic == "current employer" and current and not any(
                    _text(n).split()[0].lower() in sent.lower() for n in current if _text(n)):
                out.append("  - CHECK: your profile's current employer is %s; say it the same "
                           "way they heard it, or explain the difference." % ", ".join(current))
            if topic == "pay" and _differs_from_band(sent):
                out.append("  - CHECK: your target band is %s; a number they heard that "
                           "differs is the one a recruiter remembers." % _band()[0])
    for q, a in ctx["form"]:
        for topic, _sent in _said(q + ". " + a):
            out.append("- The form, on %s: %s **%s** (source: %s/screening_answers.md)"
                       % (topic, q, a, _rel(ctx["folder"])))
            break
    if ctx["process"]:
        out.append("- No documents went through a portal: anything they hold (a %s sent by "
                   "email, or passed on by the referrer) %s. Check the city and number on it "
                   "match what you will say." % (_noun(), "is in the messages above" if out
                                                 else "came outside the message log"))
    return out


# How each kind of interviewer tends to listen, by their title. A recruiter checks the
# basics and the story hangs together; a hiring manager, fit and motivation; a
# practitioner, depth; an executive, judgement.
ANGLES = (
    (prep._SCREENER,
     "the basics and that your story hangs together: location, start date, work "
     "authorization, pay, why this move"),
    (re.compile(r"\b(?:chief|vp|vice president|director|head|partner|principal)\b", re.I),
     "judgement and why: what you would do in their first months, and why you"),
    (re.compile(r"\b(?:manager|lead)\b", re.I),
     "fit and motivation: how you work with a team like theirs, and what you would own"),
    (re.compile(r".", re.I),
     "depth: how you did the work, the trade-offs, and what you would do differently"),
)


def _reading_for(name, company):
    """(contact_id, reading) for someone at this employer, from the contact book's id or
    any reading kept under documents/network, or (\"\", None)."""
    import glob
    want = state._match_name(name)
    k = company_key(company)
    for path in glob.glob(person.state("documents", "network", "*", "reading.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, ValueError):
            continue
        if state._match_name(got.get("name")) == want and company_key(got.get("company")) == k:
            return os.path.basename(os.path.dirname(path)), got
    return "", None


# Telling a person's name from a title in "--with". A title opens on a seniority word or
# ends on a role noun ("Senior Data Scientist", "Engagement Manager", "two partners"); a name
# is two or three capitalised words, perhaps with an initial ("Priya A. Shah"), and a surname
# that is also a word ("Tom Head") is still a name.
_ROLE_FIRST = re.compile(r"^(?:head|lead|senior|principal|associate|chief|vp|svp|evp|director|"
                         r"managing|staff|junior|the|a|an|two|three|some|someone|their|our|hr|"
                         r"talent|people|recruit\w*|hiring)\b", re.I)
_ROLE_LAST = re.compile(r"\b(?:scientists?|engineers?|analysts?|managers?|partners?|"
                        r"recruiters?|directors?|consultants?|leads?|officers?|specialists?|"
                        r"architects?|developers?|team|panel|founders?|ceo|cto|cfo|coo)$", re.I)
_NAME = re.compile(r"^[A-Z][\w'\-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][\w'\-]+){1,2}$")


def _interviewers(ctx) -> list:
    """[{name, title}] from who this stage is with: each name paired with the title written
    after it ("Dana Okafor, Head of Data"), a title alone where no name is known."""
    out = []
    for part in re.split(r"\s*(?:,|;|\band\b|&)\s*", _text(ctx["with"])):
        part = part.strip()
        if not part:
            continue
        if _NAME.match(part) and not _ROLE_FIRST.match(part) and not _ROLE_LAST.search(part):
            out.append({"name": part, "title": ""})
        elif out and out[-1]["name"] and not out[-1]["title"]:
            out[-1]["title"] = part
        else:
            out.append({"name": "", "title": part})
    return out


def _reading_of(ctx, name):
    """(contact_id, reading or None, contact row or None) for one interviewer."""
    import reading as _reading
    row = state.already_contacted(ctx["contacts"], name=name, company=ctx["company"])
    cid, found = (_text(row.get("contact_id")), _reading.load(_text(row.get("contact_id")))) \
        if row else ("", None)
    if found is None:
        cid, found = _reading_for(name, ctx["company"])
    return cid, found, row


def meeting_lines(ctx) -> list:
    """Who the person will meet: what each tends to listen for and wants to hear, what the
    person shares with them, their recent public, professional work, and the stories to lead
    with. Only what tools/network/reading.py keeps: their headline, a short excerpt of their
    About, history shared with the candidate, and their own public work. Nothing personal,
    ever. Someone named only by title ("the recruiter", "Head of Data") still gets what their
    kind of interviewer listens for, and the question to ask them."""
    import reading as _reading
    formats, _assumed = interview_formats(ctx)
    out = []
    for who in _interviewers(ctx):
        name, given = who["name"], who["title"]
        if not name:
            title = given
            out.append("- **%s**. Likely listening for %s." % (
                title[:1].upper() + title[1:], dict(zip(KINDS, ANGLES))[_kind(title)][1]))
            out += tailored(ctx, "", title, " ".join([ctx["role"], ctx["posting"][:2000]]),
                            {}, "", formats)
            continue
        cid, found, row = _reading_of(ctx, name)
        title = _text((found or {}).get("headline")) or given or _text((row or {}).get("title"))
        angle = dict(zip(KINDS, ANGLES))[_kind(title)][1]
        out.append("- **%s**%s. Likely listening for %s." % (name, ", " + prep.clip(title, 90)
                                                              if title else "", angle))
        if not found and _kind(title) != "screener":
            # A recruiter's own posts are about hiring: nothing worth reading for the call.
            out.append("  - RESEARCH FIRST (Claude, not you): %s's public, professional work "
                       "(a talk, an article, code, their team's own pages), kept with `python3 "
                       "tools/network/reading.py add <id> --name \"%s\" --company \"%s\" ...`, "
                       "then this is rebuilt. Never a people-search site; their profile only "
                       "through your own browser when you have set that up."
                       % (name, name, ctx["company"]))
        if not found:
            out += tailored(ctx, name, title, " ".join([title, ctx["role"]]), {}, "", formats)
            continue
        src = "documents/network/%s/reading.json" % cid
        for _strength, kind, what, ev in _reading.hooks(found)[:3]:
            if kind == "about":
                continue
            out.append("  - %s%s (source: %s)" % (what[:1].upper() + what[1:],
                                                  ": \"%s\"" % prep.clip(ev, 120) if ev else "", src))
        topics = " ".join([_text(found.get("headline")), _text(found.get("about"))]
                          + [_text(i.get("text")) for i in found.get("items") or []])
        out += tailored(ctx, name, title, topics, found, src, formats)
    if out:
        out.append("- Use what is here to choose what to lead with, not to show you looked: "
                   "nothing personal, nothing from outside their work, and never \"I saw on "
                   "your profile\".")
    return out


# How a stage changes what one interviewer listens for: the same person probes depth in a
# technical round and judgement in a final.
STAGE_ANGLE = {"screen": "whether the basics hold and the story makes sense",
               "technical": "how you did the work and the trade-offs you made",
               "final": "whether they would hire you over the others, and why now",
               "offer": "whether you will say yes, and on what terms"}


# Who an interviewer is, by their title: one kind per entry of ANGLES, in its order.
KINDS = ("screener", "senior", "manager", "practitioner")
# What each kind wants to hear: the signal that scores, beside what they listen for.
WANT = {
    "screener": "the basics said plainly and the same as on paper, and real interest in this "
                "employer rather than any job",
    "senior": "judgement and commercial sense: what you would do, why, and what it would "
              "change for them",
    "manager": "that you would own your work, make the team better and need little managing",
    "practitioner": "that you did the work yourself and know it in depth, including what went "
                    "wrong and what you would change",
}


# What a question is really checking, and what a strong answer gives them. The person's own
# material answers it; this is what to aim the answer at. Most specific first.
INTENT = tuple((re.compile(rx, re.I), checking, hear) for rx, checking, hear in (
    (r"tell me about yourself|walk me through your (?:background|resume|cv)\b",
     "whether your story is clear and points at this role",
     "about ninety seconds: where you are now, the thread through your roles, and why this "
     "role is the next step"),
    (r"why are you leaving|why are you looking|^why now\??$",
     "whether you are running from something, and whether you would stay",
     "a pull towards this kind of work, and nothing negative about your current employer"),
    (r"walk me through your career|career moves|career so far|moves between jobs|"
     r"why (?:did you|so many) (?:move|change)",
     "whether you would leave them soon too",
     "each move as a step towards more of one thing, said in a breath"),
    (r"code you'?re proud of|\bbug\b",
     "craft", "the problem, your reasoning, the fix, and the test that proves it"),
    (r"commercial|business (?:result|impact)|measurable",
     "whether your work changed a number someone cared about",
     "the number, and who acted on it"),
    (r"project|walk me through",
     "whether you did the work yourself and understand it",
     "the problem, what you did, and the result in numbers, in about a minute"),
    (r"^why (?!(?:are|do|did|would|should|is|not|now)\b)\S|why do you want to (?:work|join)|"
     r"why (?:this|our) "
     r"(?:company|firm|team)",
     "whether you chose them, or are applying everywhere",
     "something specific and true about them (the hooks), tied to what you want to do next"),
    (r"salary|\bpay\b|compensation",
     "whether you fit the budget, and whether you will be straightforward about it",
     "a band you can stand behind, the same one they have already heard, said calmly"),
    (r"sponsor|work authori[sz]ation|right to work|eligible to work|entitled to work",
     "whether hiring you creates paperwork",
     "a plain answer in your profile's own wording, with no hedging"),
    (r"\bnotice(?: period)?\b(?!d)|when could you start|start date",
     "whether your timing fits theirs",
     "a date, and how flexible you can honestly be"),
    (r"where are you based|where do you live|relocat",
     "whether you can do the job where it is done",
     "the place, plainly, matching what they have already been told"),
    (r"interviewing (?:anywhere|elsewhere)|other (?:processes|offers)",
     "how much time they have, and how serious you are",
     "the honest shape (for example, early stages elsewhere), no names, no invented offers, "
     "and that this one is a priority if it is"),
    (r"\bled\b|leadership|lead something",
     "whether you take ownership and bring people with you",
     "something you started or owned, how you got others on board, and what changed"),
    (r"changed someone'?s mind|influence|persuad",
     "influence without authority",
     "their view first, what you did to understand it, the evidence you used, the outcome"),
    (r"without being asked|initiative|took (?:something|it) on",
     "drive", "what you noticed that nobody asked about, what you did, what it led to"),
    (r"different from you|conflict|disagree",
     "how you work with people unlike you",
     "respect for their view, what you adapted, and the result"),
    (r"went wrong|mistake|\bfail",
     "self-awareness, and whether you learn",
     "your own part owned plainly, what you did next, what you do differently now"),
    (r"weakness",
     "self-awareness", "a real one, what you do about it, and evidence it is improving"),
    (r"five years|long ?term|after your permit",
     "whether you would stay and grow here",
     "a direction this employer can offer, and your plan to stay"),
    (r"reservations|concerns",
     "whether anything will stop you saying yes",
     "something honest and small, with what would settle it"),
    (r"experience with|how much .+ have you done",
     "whether you can do this part of the job",
     "the nearest real thing you have done, plainly, and how fast you would close the gap"),
    (r"result was right|check(?:ed)? |validat",
     "rigour", "how you knew it was right: the test, the baseline, what you would have done if "
               "it failed"),
    (r"differently",
     "reflection", "one concrete change, and why"),
    (r"more time|left out",
     "judgement under constraints", "what you put first and why, and the next thing you would do"),
    (r"how do you know|introduction",
     "how strong the referral is", "how you know them, in a sentence, warmly"),
    (r"how are you finding",
     "whether you are settling, and staying",
     "something true and good about it, and a question back"),
    (r"travel",
     "whether you can do the job the way it is done", "a straight answer, any limit said plainly"),
    (r"anything (?:else|about my background)|go into more",
     "a last chance to settle a doubt",
     "the one strength you have not landed yet, in two sentences"),
))
INTENT_MARK = "> Checking:"


def intent(question, company="") -> tuple:
    """(what it is checking, what they want to hear) for a question, or ("", ""). "Why
    <the employer>?" is read by the employer's own name first, whatever the name is."""
    q = _text(question)
    if company and re.match(r"^why %s\b" % re.escape(_text(company)), q, re.I):
        q = "Why this company?"
    return next(((c, h) for rx, c, h in INTENT if rx.search(q)), ("", ""))


def _kind(title) -> str:
    return next(k for k, (rx, _a) in zip(KINDS, ANGLES) if rx.search(title or "x"))


# The question to ask, by who they are and what the round is. A recruiter is asked about
# the process, never about their own posts (a recruiter's posts are about hiring, and asking
# reads as having looked); a practitioner about how the team does the work the round tests.
ASK_KIND = {
    "screener": "What does the next stage look like, and what will the team weigh most in it?",
    "senior": "Where do you want this team to be in a year, and what would get it there?",
    "manager": "What would someone in this role have done well, six months in?",
}
ASK_FORMAT = {
    "coding": "How does the team review and test code before it ships?",
    "technical": "How does the team decide an analysis or a model is ready to be used?",
    "case": "What kind of work have you been on lately, and what made it hard?",
    "presentation": "What will the people in the room want to have decided by the end?",
    "behavioural": "What do the people who do well here have in common?",
}
_PUBLIC_WORK = ("talk", "article", "podcast", "publication", "post", "code", "featured")


def _ask_them(ctx, kind, formats, work, src) -> list:
    """The question for one interviewer: anchored on their own public work where they have
    some and it fits, else on what their kind of interviewer owns and the round tests. A
    screen leaves time for one."""
    if kind == "screener":
        return ["  - Ask them: \"%s\" Nothing about their own posts." % ASK_KIND["screener"]]
    out = []
    if work:
        w = work[0]
        out.append("  - Ask them, on their own work: their %s%s, \"%s\". How it has gone since, "
                   "or what the team learned from it; never how you came across it. (source: %s)"
                   % (w["kind"], " (%s)" % w["date"] if w.get("date") else "",
                      prep.clip(w.get("text"), 90), src))
    if not work or ctx["step"] != "screen":
        q = ASK_KIND.get(kind) or next((ASK_FORMAT[f] for f in formats if f in ASK_FORMAT),
                                       "What does a good week on this team look like?")
        out.append("  - Ask them: \"%s\"" % q)
    return out


TEAMS_KEY = "teams"            # company_research: {"<team as the pack names it>": [facts]}
NOT_FOUND_KEY = "not_found"    # company_research: topics searched for with nothing public


def _researched(research, topic) -> tuple:
    """("found", lines), ("none", []) or ("todo", []) for one research topic: a team (as the
    pack names it) or "interview_process". Claude does the research; the person never has
    to. "none" is a search that found nothing public, which is an answer too."""
    research = research or {}
    default = prep._research_source(research)
    if topic == "interview_process":
        facts = prep._facts(research.get("interview_process"), default)
    else:
        teams = research.get(TEAMS_KEY) or {}
        key = next((k for k in teams if what_works._norm(k) == what_works._norm(topic)),
                   None) if isinstance(teams, dict) else None
        facts = prep._facts(teams.get(key), default) if key else []
    if facts:
        return "found", ["%s (source: %s)" % (f.value, f.source) for f in facts]
    gone = [_text(x) for x in research.get(NOT_FOUND_KEY) or []]
    if any(what_works._norm(x) in (what_works._norm(topic), what_works._norm("team:" + topic))
           for x in gone):
        return "none", []
    return "todo", []


def tailored(ctx, name, title, topics, found, src, formats=()) -> list:
    """What to do differently for this one interviewer, so they score you higher: which of
    your own strengths to put first (the ones nearest their work), the story to lead with,
    what their team works on (researched by Claude and kept in the research cache, never
    left to the person), and the question that fits who they are and what the round tests.
    Everything comes from the person's profile and the research: nothing is claimed that
    the profile does not hold."""
    out = []
    step = ctx["step"]
    found = found or {}
    if step in STAGE_ANGLE:
        out.append("  - At this stage they are weighing %s." % STAGE_ANGLE[step])
    out.append("  - Wants to hear: %s." % WANT[_kind(title)])
    strengths = [(similar(topics, s_), s_) for s_ in ctx["facts"].get("strengths") or [] if _text(s_)]
    near = [s_ for score, s_ in sorted(strengths, key=lambda x: -x[0]) if score > 0][:2]
    if near:
        out.append("  - Put first, for them: %s (source: %s)" % (
            "; ".join(prep.clip(x, 110) for x in near), prep._profile_source(ctx["facts"])))
    story, _score = best_story(topics, ctx["stories"], ())
    if story:
        out.append("  - Lead with: %s, the closest of your stories to what they work on "
                   "(source: %s)" % (story["title"], story["source"]))
    kind = _kind(title)
    team = re.split(r"\s+(?:at|@|\|)\s+", _text(found.get("headline")) or _text(title),
                    maxsplit=1)[0].strip()
    if team and kind != "screener" and team.lower() != _text(name).lower():
        state_, lines = _researched(ctx["research"], team)
        if state_ == "found":
            out += ["  - Their team (%s): %s" % (prep.clip(team, 60), ln) for ln in lines[:2]]
        elif state_ == "none":
            out.append("  - Their team (%s): nothing public found about it; ask them what it "
                       "owns." % prep.clip(team, 60))
        else:
            out.append("  - RESEARCH FIRST (Claude, not you): what \"%s\" works on at %s, from "
                       "the employer's own pages. The employer-researcher keeps it under `%s` "
                       "in company_research (or under `%s` when nothing is public), then this "
                       "is rebuilt." % (team, ctx["company"], TEAMS_KEY, NOT_FOUND_KEY))
    work = [i for i in found.get("items") or [] if i.get("kind") in _PUBLIC_WORK]
    out += _ask_them(ctx, kind, formats, work, src)
    return out


# ---------------------------------------------------------------- the format

# The shape of the interview, beside its step. A thirty-minute recruiter call at a
# consultancy, its case round and a coding round at a product company are three different
# preparations: what is tested, the questions that come with it, the drills, and what is
# worth knowing about how this employer runs it. Read from the stage's own words first
# (outcome.md, --stage, --format), then assumed from the step, the employer and the role,
# and said to be assumed.
FORMATS = (
    ("presentation", re.compile(r"\b(?:presentation|present(?:ing)? back|take[- ]?home|"
                                r"case study|assignment)\b", re.I)),
    ("case", re.compile(r"\b(?:case|market[- ]sizing|guesstimate)\b", re.I)),
    ("coding", re.compile(r"\b(?:cod(?:e|ing)|live programming|pair(?:ing)? programming|"
                          r"algorithms?|data structures?|leetcode|whiteboard)\b", re.I)),
    ("behavioural", re.compile(r"\b(?:behaviou?ral|pei|personal experience|competenc\w*|"
                               r"values|(?:culture|team) fit|fit interview|motivational)\b", re.I)),
    ("technical", re.compile(r"\b(?:technical|sql|statistic\w*|system design|ml design|"
                             r"modell?ing|analytics|deep dive)\b", re.I)),
    ("screen", re.compile(r"\b(?:phone|recruiter|screen\w*|hr|talent|intro\w*)\b", re.I)),
)
FORMAT_NAMES = {"presentation": "A presentation", "case": "A case interview",
                "coding": "A coding interview", "behavioural": "A behavioural interview",
                "technical": "A technical interview", "screen": "A screen"}
# What each format tests, the questions it brings beyond the step's, and how to prepare.
# The person's own material answers them; nothing here is an answer.
FORMAT_PREP = {
    "screen": {
        "tests": "whether the basics hold (where you are, when you could start, pay, work "
                 "authorization) and whether your story makes sense, usually in twenty to "
                 "thirty minutes",
        "questions": (),
        "hear": "a clear story that matches what they already hold (the same place, dates and "
                "numbers) and a specific reason for this employer",
        "drills": ("Say \"tell me about yourself\" in under ninety seconds, out loud, twice.",
                   "Have the numbers ready: notice, start date, and the band you will name.",
                   "Two questions for them on the process and the team, none the website "
                   "answers.")},
    "case": {
        "tests": "how you structure a problem you have not seen, do the maths out loud, and "
                 "land a recommendation",
        "questions": (),
        "hear": "structure before maths, a hypothesis said early, the numbers out loud, and a "
                "recommendation they could act on",
        "drills": ("Practise cases out loud and timed, in the style this employer publishes: "
                   "the mock interview (Step 4) runs them, one at a time.",
                   "Restate the question and ask one or two clarifying questions before you "
                   "structure it.",
                   "Round numbers, and say the maths as you go.",
                   "End on a recommendation in under a minute, then the risks and the next "
                   "step.")},
    "behavioural": {
        "tests": "evidence of how you behave, one story at a time, with follow-up questions "
                 "that go deep on a single story",
        "questions": ("Tell me about a time you changed someone's mind.",
                      "Tell me about a time you took something on without being asked.",
                      "Tell me about a time you worked with someone very different from you.",
                      "Tell me about something you owned that went wrong."),
        "hear": "specific moments, your own actions said with \"I\", a result in numbers, and "
                "what you learned",
        "drills": ("One story per question, known two levels deeper than you will say it: who "
                   "said what, what you did yourself, what changed.",
                   "Say \"I\", not \"we\": they score what you did.",
                   "Expect ten minutes of follow-ups on one story; a thin one runs out.")},
    "coding": {
        "tests": "how you solve a problem in code while talking: the approach first, then "
                 "working code, then tests and complexity",
        "questions": ("Walk me through some code you're proud of.",
                      "Tell me about a hard bug you tracked down."),
        "hear": "the approach before the code, clean working code, edge cases tested, and the "
                "complexity named",
        "drills": ("Practise timed problems in the language you will use, talking as you go.",
                   "Say the approach and its complexity before writing anything.",
                   "Test with an edge case before you say you are done.")},
    "technical": {
        "tests": "depth on your own work: how you did it, the trade-offs, and how you knew it "
                 "was right",
        "questions": ("How did you check the result was right?",
                      "What would you do differently now?"),
        "hear": "trade-offs you chose on purpose, how you validated the result, and the limits "
                "you know about",
        "drills": ("For each project you will mention: the data, the method, the alternative "
                   "you rejected and why, and the result.",
                   "Be ready to write a query or reason about a statistic out loud.")},
    "presentation": {
        "tests": "how you think and communicate: the choices you made, what you left out, and "
                 "how you take questions",
        "questions": ("What would you do with more time?", "What did you leave out, and why?"),
        "hear": "the answer first, evidence that holds up, and calm, direct handling of "
                "questions",
        "drills": ("Lead with the answer, then the evidence.",
                   "Rehearse to time, with a minute spare.",
                   "Prepare for the three questions you least want.")},
}
_ENGINEERING = re.compile(r"\b(?:engineer\w*|developer|programmer|software|swe|sre|devops)\b",
                          re.I)


def interview_formats(ctx) -> tuple:
    """([formats], why assumed or ""): the stage's own words first, then an assumption from
    the step, the employer and the role."""
    words = " ".join(_text(x) for x in (ctx["stage"], ctx.get("format")))
    found = [f for f, rx in FORMATS if rx.search(words)]
    if found:
        return found, ""
    step = ctx["step"]
    if step == "offer":
        return [], ""
    if step == "screen":
        return ["screen"], ""
    if employer_type(ctx) == "consulting":
        return ["case", "behavioural"], "a consulting firm's rounds are usually a case and a " \
                                        "behavioural interview together"
    if step == "final":
        return ["behavioural"], "a final round usually turns on motivation and how you work"
    if _ENGINEERING.search(ctx["role"]):
        return ["coding"], "an engineering role's technical round is usually code"
    return ["technical"], "the round after a screen usually goes into how you did the work"


def route_lines(ctx) -> list:
    """How this process started, and what that changes in the room."""
    ref = referrer_of(ctx)
    channel = _text((ctx.get("row") or {}).get("channel")).lower()
    if ref:
        return ["- Through %s's referral. They know: if asked, say how you know %s in a "
                "sentence, and do not lead with it." % (ref, ref.split()[0])]
    if channel == "recruiter":
        return ["- A recruiter approached you. \"Why are you interested?\" still needs a real "
                "answer: it is asked as if you had applied."]
    if ctx.get("process"):
        return ["- Through a contact, with no application: what they hold came by email or "
                "through them (What they have been told)."]
    return ["- You applied: everything you say must match what you sent (What the paper says)."]


def format_lines(ctx) -> list:
    """The format: what it tests, how to prepare, what this employer says about how it runs
    it (researched by Claude), and how the process started."""
    formats, assumed = interview_formats(ctx)
    out = []
    if assumed:
        out.append("- Assumed %s: %s. Ask the recruiter what the round involves, then rebuild "
                   "with --format." % (" and ".join(f for f in formats), assumed))
    for f in formats:
        p = FORMAT_PREP[f]
        out.append("- **%s.** It tests %s. They want to hear %s." % (FORMAT_NAMES[f], p["tests"],
                                                                      p["hear"]))
        out += ["  - " + d for d in p["drills"]]
    if formats == ["screen"] and employer_type(ctx) == "consulting":
        out.append("- After the screen, a consulting firm's rounds are usually a case and a "
                   "behavioural interview: start the case drills now, not when the invite comes.")
    if formats and formats != ["screen"]:
        state_, lines = _researched(ctx["research"], "interview_process")
        if state_ == "found":
            out += ["- How %s says it runs this: %s" % (ctx["company"], ln) for ln in lines[:3]]
        elif state_ == "none":
            out.append("- %s publishes nothing on how it runs this; the drills above stand."
                       % ctx["company"])
        else:
            out.append("- RESEARCH FIRST (Claude, not you): how %s says it runs %s, from its "
                       "own careers pages. The employer-researcher keeps it as "
                       "`interview_process` in company_research (or under `%s` when nothing "
                       "is public), then this is rebuilt."
                       % (ctx["company"], " and ".join(FORMAT_NAMES[f].lower() for f in formats),
                          NOT_FOUND_KEY))
    return out + route_lines(ctx)


def where_lines(ctx) -> list:
    """For someone who moved recently: their area, a briefing Claude researches, and what the
    question underneath it is. Never a memory of something they have not done: a follow-up
    question on an invented anecdote is the quickest way to lose the room."""
    moved = newcomer(ctx)
    if not moved:
        return []
    place = home_place()
    return [
        "- You moved recently: you live in %s, since %s (source: profile/person.json). \"How "
        "are you finding it?\" is friendly, and underneath it they are checking you are settled "
        "and staying, so an honest line and one specific thing you like answers both. Claude "
        "researches a short briefing and writes it under %s, each line with its source: the "
        "neighbourhoods, getting around, food, the weather now, and your field's scene here, so "
        "you can follow any thread." % (place or "your area", moved, FOUND_OUT[4:]),
        "- Before the call, do two or three things near you (a walk, a market, a cafe), so every "
        "anecdote you tell is your own.",
        "- Anything you do not know yet: \"Still working that out. What would you recommend?\"",
    ]


# How each step's small talk usually opens, so the first minute is not a surprise.
OPENERS = {
    "screen": "\"How's your week going?\" and \"Where are you calling from?\"",
    "technical": "a minute on how your day is going before they start",
    "final": "how the process has been for you so far, and the journey in if it is on site",
}
_SHARED = ("shared employer", "shared school", "same city before")


def _lead(ctx) -> str:
    """The one strength of the person's to put first for this role: their own profile's,
    nearest the role and the posting."""
    words = " ".join([ctx["role"], ctx["posting"][:3000]])
    ranked = sorted(((similar(words, x), x) for x in ctx["facts"].get("strengths") or []
                     if _text(x)), key=lambda t: -t[0])
    # With no word in common, the profile's own order stands: it already puts first the
    # strength nearest the role.
    return prep.clip(ranked[0][1], 90) if ranked else ""


def small_talk_lines(ctx) -> list:
    """The first minutes, each line doing a job for the rest of the interview: the opener
    walks into the strength to put first, shared ground makes "why this employer" personal,
    their news is the bridge to "why us", and a recent move answers the question underneath
    ("will they stay?"). Everything is true for this person and this call; nothing is
    invented to fill a silence."""
    import reading as _reading
    out = []
    lead = _lead(ctx)
    if ctx["step"] in OPENERS:
        out.append("- The first minute: expect %s. Answer in a sentence, warmly, and ask one "
                   "back.%s" % (OPENERS[ctx["step"]], (
                       " If something true from your week is close to the strength to put "
                       "first for this role (\"%s\"), say that: it walks you straight into "
                       "it." % lead) if lead else ""))
    for who in _interviewers(ctx):
        if not who["name"]:
            continue
        cid, found, _row = _reading_of(ctx, who["name"])
        for _strength, kind, what, _ev in _reading.hooks(found or {}):
            if kind in _SHARED:
                out.append("- With %s: %s. If it comes up, it is an easy way in, and it makes "
                           "\"why %s\" personal rather than generic; never as something you "
                           "looked up (source: documents/network/%s/reading.json)."
                           % (who["name"], what, ctx["company"], cid))
    research = ctx["research"] or {}
    news = prep._facts(research.get("recent_news") or research.get("news"),
                       prep._research_source(research))
    if news:
        why_us = hooks(ctx)[:1]
        same = bool(why_us) and why_us[0].value == news[0].value
        out.append("- If the talk turns to them: %s (source: %s). It is %s, so say it once, "
                   "where it lands best." % (prep.clip(news[0].value, 160), news[0].source,
                                             "also your hook for \"Why %s?\"" % ctx["company"]
                                             if same else "a bridge into \"Why %s?\""
                                             % ctx["company"]))
    out += where_lines(ctx)
    if out:
        out += ["- Keep it to a minute or two: this is where they decide whether they like "
                "talking to you, so warm, short, and back to the point.",
                "- Anything you have not done or do not know, say so: an honest \"not yet\" "
                "lands better than an invented answer. Never say you have done, seen or been "
                "somewhere you have not."]
    return out


# ---------------------------------------------------------------- the living document

def conditional_questions(ctx) -> list:
    """[(question, why)] a screen asks only of some people: a referred candidate, a
    temporary status, a recent move, a consulting firm's travel."""
    out = []
    if ctx["step"] != "screen":
        return out
    ref = referrer_of(ctx)
    if ref:
        out.append(("How do you know %s?" % ref, "you were referred"))
    if temporary_status(ctx):
        out.append(("What about longer term, after your permit?", "your status is temporary"))
    if newcomer(ctx):
        out.append(("How are you finding %s?" % (home_place().split(",")[0] or "it here"),
                    "you moved recently"))
    if employer_type(ctx) == "consulting":
        out.append(("Are you willing to travel?", "a consulting firm asks every time"))
    return out


def _owned(text) -> dict:
    """{section: body lines} for the sections the person writes in, from the last version."""
    out, cur = {}, None
    for line in str(text or "").splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            cur = m.group(1) if m.group(1) in OWNED else None
            if cur:
                out[cur] = []
            continue
        if cur:
            out[cur].append(line)
    return out


def _answer_blocks(lines) -> dict:
    """{normalised question: (question, [answer lines])} from the Your answers section."""
    out, q, body = {}, None, []
    for line in list(lines or ()) + ["### "]:
        m = re.match(r"^### (.*)$", line)
        if m:
            if q:
                out[what_works._norm(q)] = (q, body)
            q, body = m.group(1).strip(), []
        elif q is not None and not line.startswith(INTENT_MARK):
            body.append(line)
    return out


def _found_out(text) -> list:
    """The lines written under Small talk's own heading, kept on every rebuild, whether or
    not the section still has anything else to say."""
    m = re.search(r"^" + re.escape(FOUND_OUT) + r"\s*$", str(text or ""), re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)     # the next section; a "#### Food" inside stays
    return [ln for ln in (body[:nxt.start()] if nxt else body).splitlines()
            if ln.strip() and ln.strip() != FOUND_EMPTY
            and ln.strip() != "- Nothing yet: each line you add here, with its source, stays."]


def _own_words(body) -> list:
    """The lines of an answer block the person (or the session, for them) wrote: never the
    marker or the "- From:" lines this file generated, which a rebuild makes afresh."""
    return [ln for ln in body or () if ln.strip() and TO_WRITE not in ln
            and not ln.lstrip().startswith(("- From:", "- careful:"))]


def answer_lines(ctx, answered) -> list:
    """Your answers: one block a question, the person's own words kept from the last
    version, and otherwise what to say it from, marked to be written."""
    kept = _answer_blocks(_owned(ctx["living"]).get("Your answers"))
    out = []
    for q, a in answered:
        out.append("### %s" % q["question"])
        checking, hear = intent(q["question"], ctx["company"])
        if checking:
            out.append("%s %s. They want to hear: %s." % (INTENT_MARK, checking, hear))
        old = kept.get(what_works._norm(q["question"]))
        body = _own_words(old[1] if old else [])
        if body:
            out += body
        else:
            out.append(TO_WRITE)
            out += ["- From: %s" % re.sub(r"^Say: ", "", ln) for ln in a["lines"][:3]]
        out.append("")
    # An answer written for a question this stage does not list (an earlier stage's, one the
    # person added, one reworded since) is never dropped: it follows, as they wrote it.
    asked = {what_works._norm(q["question"]) for q, _a in answered}
    for key, (q, body) in kept.items():
        mine = _own_words(body)
        if key not in asked and mine:
            out += ["### %s" % q] + mine + [""]
    return out


def check(path) -> list:
    """[(question, problem)] for the answers in a living document that are not yet fit to
    say: the first ONE_SCREEN_QUESTIONS must be written, and every written one must read
    as said (voice_check.spoken_findings). Raw profile wording is never an answer."""
    text = _read(path)
    blocks = _answer_blocks(_owned(text).get("Your answers"))
    # Research the document asks Claude for is part of being ready: the person never sees a
    # RESEARCH FIRST line, only what it found.
    out = [("Research", re.sub(r"^\s*-\s*", "", ln).split(". The employer-researcher")[0])
           for ln in text.splitlines() if "RESEARCH FIRST (Claude" in ln]
    for i, (q, body) in enumerate(blocks.values()):
        mine = _own_words(body)
        if not " ".join(mine).strip():
            if i < ONE_SCREEN_QUESTIONS:
                out.append((q, "not written yet"))
            continue
        out += [(q, why) for why in prep.unsayable(mine)]
    return out


def stages_mark(ctx) -> str:
    """The stages this document has been built for, kept in it (open_actions reads it)."""
    m = _STAGES_MARK.search(ctx["living"] or "")
    have = [s for s in (m.group(1).split("; ") if m else []) if s]
    if ctx["stage"] not in have:
        have.append(ctx["stage"])
    return "<!-- stages: %s -->" % "; ".join(have)


def campaign_offer(ctx) -> str:
    """The one-time offer of a chat just for this employer, once a stage is booked: "" when
    it was made before or nothing is booked yet."""
    booked = any(s["scheduled"] and not s["done"] for s in ctx["stages"])
    if not booked or os.path.exists(os.path.join(ctx["folder"], CAMPAIGN_FILE)):
        return ""
    return ("Want a separate chat just for %s? It keeps the prep in one place and leaves this "
            "chat for the rest of the search." % ctx["company"])


CAMPAIGN_FILE = "campaign.json"


def record_campaign(company, role, chat="", declined=False, today=None) -> str:
    """The person's answer to the campaign chat: {"chat", "started"} or {"declined"}, in the
    process's folder. The offer is made once; open_actions and the brief read it, and leave
    an employer with a campaign chat to that chat."""
    folder = outreach.app_folder(company, role)
    os.makedirs(folder, exist_ok=True)
    day = _text(today) or dt.date.today().isoformat()
    body = {"declined": day} if declined else {"chat": _text(chat), "started": day}
    path = os.path.join(folder, CAMPAIGN_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=1)
        fh.write("\n")
    return path


def campaign_chat(folder) -> str:
    """The campaign chat that owns this process, or "" (none, or the offer declined)."""
    try:
        with open(os.path.join(folder, CAMPAIGN_FILE), encoding="utf-8") as fh:
            return _text(json.load(fh).get("chat"))
    except (OSError, ValueError, AttributeError):
        return ""


# ---------------------------------------------------------------- the pack

def _section(title, lines, empty) -> list:
    if title not in SECTIONS:
        raise ValueError("%r is not one of the pack's SECTIONS" % title)
    return ["## " + title, ""] + (list(lines) if lines else ["- " + empty]) + [""]


def pack_markdown(ctx, never_say=None) -> str:
    """The living document for this process, one screen first. `never_say` defaults to the
    person's phrases. What the person wrote (their answers, the rework, their notes, what
    they found out about where they live) is carried from the last version."""
    banned = (lambda text: [m.group(0) for _p, rx in never_say for m in rx.finditer(text)]) \
        if never_say is not None else learned.dislikes
    questions = likely_questions(ctx)
    answered = [(q, answer_for(q, ctx)) for q in questions]
    one_money, money_lines = money(ctx)
    hook_facts = hooks(ctx)
    donts = do_not_say(ctx, never_say)
    owned = _owned(ctx["living"])

    when = ", ".join(x for x in (ctx["date"], "with " + ctx["with"] if ctx["with"] else "") if x)
    lines = ["# Interview prep: %s at %s" % (ctx["role"], ctx["company"]), "",
             "Last updated %s. Next: %s%s. One document for this whole process: change an "
             "answer here, and it is sent to you again." % (ctx["today"], ctx["stage"],
                                                            ", " + when if when else ""),
             "Every fact carries its source, and anything unsourced was left out.",
             stages_mark(ctx), ""]

    formats, _assumed = interview_formats(ctx)
    assessing = "; ".join(FORMAT_PREP[f]["tests"] for f in formats) or \
        STAGE_ANGLE.get(ctx["step"], "")
    screen = ["**What they are assessing:** %s." % assessing if assessing else "",
              "**What they want to hear:** %s." % "; ".join(FORMAT_PREP[f]["hear"] for f in formats)
              if formats else "", ""]
    screen = [ln for i, ln in enumerate(screen) if ln or (i == 2 and any(screen[:2]))]
    screen += ["**Likely questions, and what to answer with**"]
    screen += ["%d. %s -> %s" % (i, q["question"], a["short"])
               for i, (q, a) in enumerate(answered[:ONE_SCREEN_QUESTIONS], 1)]
    screen += ["", "**Hooks**"]
    letter = _text((ctx["draft"] or {}).get("_path"))
    screen += ["- %s%s (source: %s)" % ("The letter told them: " if f.source == letter else "",
                                         prep._short(f.value, 110), f.source)
               for f in hook_facts[:HOOKS]] or ["- %s: nothing researched to hang \"why us\" on."
                                                % prep.NOT_RESEARCHED]
    screen += ["", "**Money:** %s." % one_money, ""]
    # The list of what not to say quotes the very words it warns against, so it is neither
    # flagged for them here nor read by voice_check as something the person will say.
    quoted = [voice_check.QUOTED_OPEN, "**Do not say**"] + donts[:MAX_DO_NOT] + [voice_check.QUOTED_CLOSE]
    lines += _section("On one screen", prep._flag_banned(screen, banned) + quoted, "")
    lines += _section("Your answers", prep._flag_banned(answer_lines(ctx, answered), banned),
                      "No questions to answer yet.")
    lines += _section("What they have been told", told_lines(ctx),
                      "Nothing logged to anyone at %s, and no form on file." % ctx["company"])
    lines += _section("Who you are meeting", meeting_lines(ctx),
                      "Nobody named for this stage yet: when the invite names them, rebuild this "
                      "with --with \"<name, title>\".")
    lines += _section("The format", format_lines(ctx), "An offer: nothing to drill.")

    detail = []
    for q, a in answered:
        detail.append("- **Q.** %s (%s; source: %s)" % (q["question"], q["why"], q["source"]))
        checking, hear = intent(q["question"], ctx["company"])
        if checking:
            detail.append("  - Checking %s. They want to hear %s." % (checking, hear))
        detail += ["  - " + ln for ln in a["lines"]]
    lines += _section("Likely questions", prep._flag_banned(detail, banned),
                      "No questions: nothing on file to anticipate.")
    lines += _section("Stories", prep._flag_banned(_story_lines(ctx), banned),
                      "No STAR stories in profile/%s: write three or four before the interview "
                      "(/setup --section history)." % STORIES_FILE)
    lines += _section("What the paper says", paper_lines(ctx), "Nothing on file about what was sent.")
    lines += _section("Gaps and honest framing", prep._flag_banned(gap_lines(ctx), banned),
                      "No gap the posting names: lead with the matches.")
    lines += _section("Money and eligibility", money_lines, prep.NOT_RESEARCHED)
    company = prep._company_lines(ctx["research"], ctx["today"])
    stale = prep._stale_line(ctx["research"], ctx["today"]) if company else ""
    lines += _section("The company", company + ([stale] if stale else []),
                      "RESEARCH FIRST (Claude, not you): %s itself, from its own pages "
                      "(interview.md Step 2), then this is rebuilt." % ctx["company"])
    talk = small_talk_lines(ctx)
    found = _found_out(ctx["living"])
    lines += _section("Small talk", talk + ["", FOUND_OUT, ""] + (found or [FOUND_EMPTY]),
                      "")
    ask = ask_lines(ctx) + ["- Is there anything about my background you'd like me to go into "
                            "more? (the close: it gives them the last word on any doubt)"]
    lines += _section("Ask them", prep._flag_banned(ask, banned),
                      "Nothing researched to anchor a question on.")
    lines += _section("Warm route", warm_lines(ctx), "Nobody in the contact book at %s."
                      % ctx["company"])
    lines += _section("Earlier stages", earlier_lines(ctx), "No earlier stage on record.")
    lines += _section("To rework", ctx["rework"], REWORK_EMPTY)
    notes = [ln for ln in owned.get("Notes", []) if ln.strip() != NOTES_EMPTY]
    while notes and not notes[0].strip():
        notes.pop(0)
    while notes and not notes[-1].strip():
        notes.pop()
    lines += _section("Notes", notes, NOTES_EMPTY[2:])
    return "\n".join(lines).rstrip() + "\n"


def living_path(ctx) -> str:
    return os.path.join(ctx["folder"], LIVING)


def write_pack(ctx, never_say=None) -> str:
    """Write the living document beside the application and return its path. What the
    person wrote in it is kept."""
    path = living_path(ctx)
    os.makedirs(ctx["folder"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(pack_markdown(ctx, never_say))
    return path


# ---------------------------------------------------------------- what came of it

def add_asked(company, role, stage, question, story="", landed="", note="", date=None,
              source="") -> str:
    """One question an interview asked, into the bank. Returns the bank's path, or ""
    when that employer's stage already has it: /outcome run twice records it once.

    `source` is for a question the person was told about rather than asked (the recruiter
    listed it, a contact who interviewed there, a review site): it names where it came
    from, and the pack says "reported by" it. Without it, a reported question could only
    be recorded as one they had been asked."""
    landed, source = _text(landed).lower(), _text(source)
    if landed and landed not in what_works.LANDED:
        raise ValueError("landed is one of %s, or blank" % ", ".join(what_works.LANDED))
    if source and landed:
        raise ValueError("a reported question was not asked, so nothing landed: drop --landed "
                         "or --source")
    if not _text(question):
        raise ValueError("a question to record is needed")
    path = person.state(*what_works.BANK)
    same = (company_key(company), what_works._norm(stage), what_works._norm(question))
    if any((company_key(r.get("company")), what_works._norm(r.get("stage")),
            what_works._norm(r.get("question"))) == same for r in what_works.bank()):
        return ""
    # Saved in place (tools/csv_store.py): a bank written before `source` existed gains
    # the column only when a row has one, and its other rows keep their lines.
    rows = csv_store.read_rows(path, what_works.BANK_COLUMNS)
    rows.append({"date": _text(date) or dt.date.today().isoformat(), "company": _text(company),
                 "role": _text(role), "stage": _text(stage), "question": _text(question),
                 "story": _text(story), "landed": landed, "note": _text(note), "source": source})
    csv_store.write_rows(path, rows, what_works.BANK_COLUMNS)
    return path


def add_rework(company, role, stage, question, note, date=None, where="mock") -> str:
    """An answer to work on, appended under To rework in the process's living document (or
    an older stage's pack, where the process predates it)."""
    folder = outreach.app_folder(company, role)
    path = os.path.join(folder, LIVING)
    if not os.path.exists(path):
        path = os.path.join(folder, pack_name(stage))
    text = _read(path)
    if not text:
        raise LookupError("no pack for %s at %s yet: build it first (pack --write)"
                          % (stage, company))
    line = '- %s, %s: "%s": %s' % (_text(date) or dt.date.today().isoformat(), where,
                                   _text(question), _text(note))
    m = re.search(r"^## To rework\s*$", text, re.M)
    if not m:
        text = text.rstrip() + "\n\n## To rework\n\n" + line + "\n"
    else:
        body = text[m.end():]
        nxt = re.search(r"^## ", body, re.M)
        end = m.end() + (nxt.start() if nxt else len(body))
        kept = _rework_lines(text)
        text = text[:m.end()] + "\n\n" + "\n".join(kept + [line]) + "\n\n" + text[end:].lstrip()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")
    return path


# ---------------------------------------------------------------- CLI

def _day(value) -> str:
    """A date as YYYY-MM-DD, or argparse's own error: a short or reversed date is written to
    outcome.md and never read back as booked."""
    if not value:
        return ""               # argparse runs a default through the type as well
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and dt.date.fromisoformat(value):
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("%r is not a date: write it YYYY-MM-DD" % value)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="build the pack for one stage")
    p.add_argument("company")
    p.add_argument("--role", default="")
    p.add_argument("--stage", default="", help="as outcome.md names it; default the next booked")
    p.add_argument("--date", default="", type=_day)
    p.add_argument("--with", dest="with_", default="", help="who it is with, name or title")
    p.add_argument("--format", dest="format_", default="",
                   help="what the round is, when its name does not say: case, coding, "
                        "behavioural, technical, presentation or screen")
    p.add_argument("--map", default="", help="JSON {question: story title} the session mapped")
    p.add_argument("--write", action="store_true", help="save it beside the application")
    p.add_argument("--today", type=_day)
    q = sub.add_parser("asked", help="record a question an interview asked")
    r = sub.add_parser("rework", help="add an answer to work on to the stage's pack")
    for s in (q, r):
        s.add_argument("--company", required=True)
        s.add_argument("--role", default="")
        s.add_argument("--stage", required=True)
        s.add_argument("--question", required=True)
        s.add_argument("--note", default="")
        s.add_argument("--date", type=_day)
    q.add_argument("--story", default="")
    q.add_argument("--landed", default="", choices=("",) + what_works.LANDED)
    q.add_argument("--source", default="", help="for a question they were told about, not "
                   "asked: where it came from (the recruiter, a contact, a review site and its link)")
    r.add_argument("--where", default="mock", help="mock, or the real interview")
    pr = sub.add_parser("process", help="a hiring process with no application (a referral, a "
                                        "recruiter's call): register it so the pack, /outcome "
                                        "and the brief can read it")
    pr.add_argument("company")
    pr.add_argument("--contact", required=True, help="the contact_id who leads it")
    pr.add_argument("--role", required=True)
    pr.add_argument("--stage", default="")
    pr.add_argument("--date", default="", type=_day)
    pr.add_argument("--with", dest="with_", default="")
    pr.add_argument("--format", dest="format_", default="")
    pr.add_argument("--today", type=_day)
    cp = sub.add_parser("campaign", help="record the answer to the offer of a chat just for "
                                         "this employer")
    cp.add_argument("company")
    cp.add_argument("--role", default="")
    who = cp.add_mutually_exclusive_group(required=True)
    who.add_argument("--yes", metavar="CHAT", help="the campaign chat's title or session id")
    who.add_argument("--no", action="store_true")
    ck = sub.add_parser("check", help="are the answers in the living document fit to say: "
                                      "written, first person, as said rather than written")
    ck.add_argument("company")
    ck.add_argument("--role", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "process":
            row, folder, added = register_process(a.company, a.contact, a.role, a.stage, a.date,
                                                  a.with_, today=a.today)
            print("%s: %s at %s, led by %s; its folder is %s.\n"
                  % ("registered" if added else "already registered", row["role"], row["company"],
                     row["contact_person"], _rel(folder)))
            # One command from a booked call to its document: the prep is built and kept now.
            ctx = gather(row["company"], row["role"], a.stage, a.date, a.with_, a.today,
                         format_=a.format_)
            sys.stdout.write(pack_markdown(ctx))
            _keep(ctx)
            if a.stage and not a.date:
                print("no date given: the stage is on record, but the brief cannot remind you "
                      "of it until it has one (run this again with --date)")
            return 0
        if a.cmd == "campaign":
            tracker = what_works._csv(person.state("job_search_tracker.csv"))
            row = _row(a.company, a.role, tracker,
                       state.load_contacts(person.state("network_contacts.csv")))
            path = record_campaign(_text(row.get("company")), _text(row.get("role")),
                                   chat=a.yes or "", declined=a.no)
            print("recorded in %s%s" % (_rel(path), "; the rest of the search leaves %s to that "
                                        "chat" % row.get("company") if a.yes else ""))
            return 0
        if a.cmd == "check":
            tracker = what_works._csv(person.state("job_search_tracker.csv"))
            row = _row(a.company, a.role, tracker,
                       state.load_contacts(person.state("network_contacts.csv")))
            path = os.path.join(outreach.app_folder(_text(row.get("company")),
                                                    _text(row.get("role"))), LIVING)
            if not os.path.exists(path):
                print("interview_pack: no %s yet: build it with pack --write" % _rel(path))
                return 1
            found = check(path)
            for q, why in found:
                print("- %s: %s" % (q, why))
            todo = [q for q, b in _answer_blocks(_owned(_read(path)).get("Your answers")).values()
                    if not _own_words(b)]
            research = sum(1 for q, _w in found if q == "Research")
            answers = len(found) - research
            print("; ".join(x for x in (
                "%d answer(s) not fit to say yet" % answers if answers else "",
                "%d piece(s) of research still to do" % research if research else "")
                if x) + "." if found else "Every answer written is fit to say aloud.")
            if todo and not found:
                print("Still to write, beyond the first five: %d." % len(todo))
            return 1 if found else 0
        if a.cmd == "asked":
            path = add_asked(a.company, a.role, a.stage, a.question, a.story, a.landed,
                             a.note, a.date, a.source)
            print("added to %s" % _rel(path) if path else
                  "already in %s for that stage" % "/".join(what_works.BANK))
            return 0
        if a.cmd == "rework":
            # The process's own row names the role, as check and campaign find it.
            tracker = what_works._csv(person.state("job_search_tracker.csv"))
            row = _row(a.company, a.role, tracker,
                       state.load_contacts(person.state("network_contacts.csv")))
            print("added to %s" % _rel(add_rework(_text(row.get("company")) or a.company,
                                                   _text(row.get("role")) or a.role, a.stage,
                                                   a.question, a.note, a.date, a.where)))
            return 0
        if a.map:
            with open(a.map, encoding="utf-8") as fh:
                story_map = json.load(fh)
            if not isinstance(story_map, dict):
                raise ValueError("%s holds no {question: story title} object" % a.map)
        else:
            story_map = {}
        ctx = gather(a.company, a.role, a.stage, a.date, a.with_, a.today, story_map,
                     format_=a.format_)
        sys.stdout.write(pack_markdown(ctx))
        if a.write:
            _keep(ctx)
    except (LookupError, ValueError, OSError) as exc:
        print("interview_pack: %s" % exc, file=sys.stderr)
        return 1
    return 0


def _keep(ctx) -> None:
    """Write the living document and say what is left before it goes to the person."""
    path = write_pack(ctx)
    print("\nwritten: %s" % _rel(path))
    left = check(path)
    research = [w for q, w in left if q == "Research"]
    for line in research:
        print("research first: %s" % line)
    if len(left) > len(research):
        print("not yet fit to say: %d answer(s); write them in the document as you would say "
              "them, then `interview_pack.py check \"%s\"`"
              % (len(left) - len(research), ctx["company"]))
    offer = campaign_offer(ctx)
    if offer:
        print("offer once, optionally, at the end of the reply: %s On a yes, automation/"
              "prompts/campaign.md says how to start it; either way record the answer: "
              "python3 tools/interview_pack.py campaign \"%s\" --yes \"<the chat's title or "
              "id>\" | --no" % (offer, ctx["company"]))


if __name__ == "__main__":
    raise SystemExit(main())
