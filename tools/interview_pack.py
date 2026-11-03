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
            [--date YYYY-MM-DD] [--time 14:00] [--with "<name or title>"] [--map map.json]
            [--write]
    python3 tools/interview_pack.py book "<Company>" [--role R] [--stage S]
            [--date YYYY-MM-DD] --time 2pm [--zone EST] [--with "<who>"]
    python3 tools/interview_pack.py times [--company C]
    python3 tools/interview_pack.py asked --company C --role R --stage S --question "..."
            [--story "<story title>"] [--landed yes|partly|no] [--note "..."]
    python3 tools/interview_pack.py rework --company C --role R --stage S
            --question "..." --note "..."
    python3 tools/interview_pack.py feedback --question "..." --answer-file F
            --band Strong|Solid|Gap --point "<their words>" "<what to keep or change>"
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

import person as _person  # noqa: E402
import local_path  # noqa: E402

# Run with no profile (the app itself, or before /setup), the imports below read it and the
# command crashed with a traceback, `--help` included. It says so plainly instead.
if __name__ == "__main__" and not _person.exists():
    if set(sys.argv[1:]) & {"-h", "--help"}:
        print(__doc__.strip())
        raise SystemExit(0)
    print("%s: no profile/ yet: /setup builds one." % "interview_pack")
    raise SystemExit(1)

import bridges  # noqa: E402
import csv_store  # noqa: E402
import learned  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import profile_facts  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import told as places_told  # noqa: E402
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
# The mark on an answer still to write. It was an instruction to Claude ("said aloud, first
# person, whole sentences, contractions welcome"), read by the person on their page; how an
# answer is written is in interview.md Step 3. The older mark is still read as the same one.
TO_WRITE = "[not written yet: Claude writes it with you, the way you would say it]"
OLD_TO_WRITE = "[to write: said aloud, first person, whole sentences, contractions welcome]"
TO_WRITES = (TO_WRITE, OLD_TO_WRITE)
# Research the document still needs, which Claude does before the person reads it: said in
# plain words, since the person may see the line on their page before the research is in.
# The older wording is still read wherever the line is looked for.
RESEARCH_MARK = "Not looked up yet (Claude does this before you read it):"
RESEARCH_MARKS = (RESEARCH_MARK, "RESEARCH FIRST (Claude")


def research_line(line) -> bool:
    """Is this a line asking Claude for research the document does not hold yet?"""
    return any(m in str(line or "") for m in RESEARCH_MARKS)
_STAGES_MARK = re.compile(r"^<!-- stages: (.*?) -->$", re.M)

# One screen is what is read in the minutes before: five questions, three to five things to
# say, two or three questions to ask them, three hooks, one money line and the one or two
# things not to say that matter. The detail below is for the night before. Four "do not say"
# lines, one of them the same rule on every pack, read as a list of warnings to a person
# about to go in (2026-11-03: "so many random don't says").
ONE_SCREEN_QUESTIONS = 5
HOOKS = 3
MAX_DO_NOT = 2
MAX_SAY = 5
MAX_ASK_FIRST = 3
MAX_QUESTIONS = 18
MAX_REQUIREMENTS = 3
MAX_FORM_LINES = 8
MAX_RECORD = 24   # lines of the person's own outcome record
RECORD_ITEM = 200
MAX_ASK = 6
MAX_ASK_SCREEN = 3            # a twenty-minute screen has time for about three
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
    return local_path.rel(path, person.state()).replace(os.sep, "/")


def _repo_rel(path) -> str:
    """A path in the repo (profile/..., .claude/...), as prep.PROFILE_SOURCE names one."""
    return local_path.rel(path, ROOT).replace(os.sep, "/")


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


# ---------------------------------------------------------------- plain words for the person

# The pack is read by a tired person on a phone in the minutes before a call, and it named its
# sources as files: "(source: ../../profile/07-interview-prep.md)", "job_search_tracker.csv",
# "company_research/x.json" (2026-11-03: "links to random json files and destinations the
# user shouldn't know about"). Every source is still given, as what it is to them. A link to
# an employer's own page stays a link: that is a source they can open.
_SOURCE_WORDS = (
    (r"\.claude/|job-application-assistant", "the app's guide"),
    (r"07-interview-prep", "your stories and answers"),
    (r"04-job-evaluation", "your pay targets"),
    (r"01-candidate-profile|person\.json|02-behavioral|skills\.py|BRIDGES|bridges|"
     r"networking\.py|WORK_AUTH|profile_facts|(?:^|/)profile(?:/|$)", "your profile"),
    (r"job_search_tracker", "your applications"),
    (r"network_contacts", "your contacts"),
    (r"network_threads", "your messages"),
    (r"screening_answers|form_fields", "the application form"),
    (r"job_posting", "the job posting"),
    (r"outcome\.md", "this interview's record"),
    (r"draft\.json|cover_letter|Cover_Letter|outreach\.md", "what you sent"),
    (r"(?:^|/)cv/|_CV_|_Resume_", "the resume you sent"),
    (r"interview_prep", "an earlier prep"),
    (r"learned|liked", "what you told Claude"),
    (r"asked\.json|interview_bank|question_bank", "your past interviews"),
    (r"documents/network|reading\.json|prep\.md", "your notes on them"),
    (r"company_research|research", "the research"),
)
# A file or a folder named in a source, with the name of a setting inside it that may follow
# ("profile/person.json identity.places_told", "networking.py WORK_AUTH").
_PATH_TOKEN = re.compile(
    r"(?<![\w/:.])(?:\.\./)*(?:[\w.&-]+/)*[\w.&-]+\.(?:md|json|csv|py|tex|txt|pdf|docx)\b"
    r"(?:\s+(?:[a-z_]+\.[a-z_.]+|[A-Z_]{3,})\b)?"
    r"|(?<![\w/:.])(?:\.\./)*(?:[\w.&-]+/)+[\w.&-]*[_.][\w.&-]*/?")


def _path_words(token) -> str:
    for rx, words in _SOURCE_WORDS:
        if re.search(rx, token):
            return words
    return "your files"


def source_words(src) -> str:
    """A source as the person knows it: "your profile", "the job posting", an employer's
    link as it is. Words that are already words stay, and a file named inside a sentence
    ("the recruiter's email, recorded in documents/interview/question_bank.csv") is said in
    words where it stands."""
    s = _text(src)
    if not s or re.match(r"https?://", s, re.I):
        return s
    out = _PATH_TOKEN.sub(lambda m: _path_words(m.group(0)), s)
    # The same place named twice ("your CV, your CV") is said once.
    parts = list(dict.fromkeys(p.strip() for p in out.split(", ")))
    return ", ".join(parts)


_SOURCE_IN = re.compile(r"(\bsource: )([^()]+?)(\))")


def plain_sources(line) -> str:
    """A line with every "source: <file>" in it said in words (source_words)."""
    return _SOURCE_IN.sub(lambda m: m.group(1) + source_words(m.group(2)) + m.group(3),
                          str(line))


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


# What a stock answer holds while it is still a template: "[Customize per company]",
# "<the employer>", TODO. Printed as it stands, it read as the answer (2026-10-20).
_FILL_IN = re.compile(r"\[(?:PLACEHOLDER|TODO|TBD|FILL|INSERT|ADD|CUSTOMI[SZ]E|TAILOR)[^\]]*\]"
                      r"|\bcustomi[sz]e (?:this |it )?(?:per|for (?:each|every|the)) (?:company|"
                      r"employer|role|firm)\b|<[^<>\n]{2,40}>|\b(?:TODO|TBD)\b", re.I)


def hard_answers(path=None) -> list:
    """{question, answer, confirm, source} for each question heading with a quoted answer.

    An answer still holding a `[PLACEHOLDER` is not an answer and is left out; one
    holding any other fill-in ("[Customize per company]", "<the employer>") is kept with
    `fill_in`, so the pack says what to fill instead of printing it as an answer. One
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
        tags, use_for = {}, []
        for ln in body:
            m = re.match(r"^\s*(suits|not for)\s*:\s*(.+)$", _flat(ln), re.I)
            if m:
                tags[m.group(1).lower()] = tuple(t.strip().lower() for t in m.group(2).split(",")
                                                 if t.strip())
            m = _USE_FOR.match(_flat(ln))
            if m:
                use_for = _tags(m.group(1))
        # A heading can hold several wordings of one question: '"Why are you leaving <the
        # current employer>?" / "Why are you looking?"'. Each is matched on its own.
        alternatives = [_text(q) for q in _QUOTED.findall(heading)] or [heading.strip("\"“” ")]
        fill = _FILL_IN.search(answer)
        out.append({"question": heading.strip("\"“” "), "answer": answer,
                    "confirm": confirm, "source": _repo_rel(path),
                    "fill_in": fill.group(0) if fill else "",
                    "alternatives": alternatives, "use_for": use_for,
                    "suits": tags.get("suits", ()), "not_for": tags.get("not for", ())})
    return out


# ---------------------------------------------------------------- matching

_STOP = frozenset("""a an the and or of to in on for with you your me my i about how what why when
where do does did is are was were have has had tell time this that it as at be by from walk
through give example describe us our we can could would will there their they them any some
one most now then today currently here""".split())
# "now", "then", "today", "currently" and "here" say when or where, never what a question is
# about. With "now" a topic word, "What would you do differently now?" matched "Why now?" at
# 0.5 and took the answer written for leaving a consultancy, at a bank.


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


# The words a question means beside the words it says, for matching it to a story's
# `Use for:` tags: "a project in sixty seconds" is "a project end to end", and "took
# something on without being asked" is "a time you took initiative".
_MEANS = (
    (re.compile(r"\b(?:in (?:sixty|60) seconds|in a minute|briefly|quickly)\b", re.I), " end to end"),
    (re.compile(r"without being asked|took (?:something|it) on", re.I), " initiative improve a process"),
    (re.compile(r"changed someone'?s mind|influence|persuad", re.I),
     " stakeholders getting people to adopt your work"),
    (re.compile(r"different from you", re.I), " working with commercial teams stakeholders"),
    (re.compile(r"commercial result|business result", re.I), " analysis changed a business result"),
)


def _match_text(question) -> str:
    q = _text(question)
    return q + "".join(extra for rx, extra in _MEANS if rx.search(q))


def _story_score(question, st, bank_rows=()) -> float:
    """How well one story's `Use for:` tags fit the question, moved by what the bank says
    it did for a like question before."""
    score = max((similar(question, tag) for tag in st["use_for"]), default=0.0)
    for row in bank_rows:
        if _text(row.get("story")).lower() != st["title"].lower():
            continue
        if similar(row.get("question"), question) < 0.5:
            continue
        landed = _text(row.get("landed")).lower()
        score += BANK_NUDGE if landed == "yes" else -BANK_NUDGE if landed == "no" else 0
    return score


def story_scores(question, story_list, bank_rows=()) -> list:
    """[(story, score)] for every story that fits the question at all (MATCH), best first;
    stories that fit equally keep the file's order."""
    scored = [(st, _story_score(question, st, bank_rows)) for st in story_list]
    return sorted([x for x in scored if x[1] >= MATCH], key=lambda x: -x[1])


def best_story(question, story_list, bank_rows=()) -> tuple:
    """(story, score) whose `Use for:` tags best fit the question, or (None, 0)."""
    ranked = story_scores(question, story_list, bank_rows)
    return ranked[0] if ranked else (None, 0.0)


# How close a second story has to come to the best one for the plan to take it instead: the
# best is already the answer to another question in this pack, or was told at this employer
# in an earlier round. Each question was matched on its own, so two of the five answers on one
# screen could be the same story, and a final round heard the screen's story again: a thin
# bench, to the people deciding the hire. A story that fits clearly better still wins.
STORY_NEAR = 0.15


def told_here(ctx) -> dict:
    """{story title, lower-cased: where it was told} for every story already told at this
    employer in an earlier round: the question bank's rows for this employer (what /outcome
    recorded), and the stories an earlier stage's own pack answered with. A question reported
    rather than asked told nothing, and this round's own rows are this round."""
    k = company_key(ctx["company"])
    out = {}
    for r in ctx.get("bank") or ():
        title = _text(r.get("story"))
        if (not title or _text(r.get("source")) or company_key(r.get("company")) != k
                or _same_round(r.get("stage"), ctx.get("stage"))):
            continue
        out.setdefault(title.lower(), "told here %s" % (_at(r.get("stage")) if _text(
            r.get("stage")) else "at an earlier stage"))
    for name in ctx.get("earlier") or ():
        for title in _kept_map(_read(os.path.join(ctx["folder"], name))).values():
            out.setdefault(_text(title).lower(), "the answer in %s" % name)
    # The living document's last build, when it was for another round: what it prepared is
    # what that round heard.
    built = ctx.get("built") or {}
    if built.get("stage") and not _same_round(built["stage"], ctx.get("stage")):
        for title in (built.get("stories") or {}).values():
            out.setdefault(_text(title).lower(), "prepared here %s" % _at(built["stage"]))
    return out


def _fixed_story(item, ctx) -> tuple:
    """(story or None, how) when the question's story is not the plan's to choose: the
    session mapped it (--map), the last build answered it with one (the kept map), or the
    letter's evidence names one. (None, "") when matching decides."""
    q = item["question"]
    mapped = ctx["map"].get(q)
    if mapped:
        return (next((s for s in ctx["stories"] if s["title"].lower() == _text(mapped).lower()),
                     None), "mapped")
    kept = _kept_story(q, ctx).lower()
    story = next((s for s in ctx["stories"] if s["title"].lower() == kept), None) if kept else None
    if story is not None:
        return story, "as the last build answered it"
    if item.get("evidence"):
        story = story_for_evidence(item["evidence"], ctx["stories"])
        if story is not None:
            return story, "it carries the letter's evidence"
    return None, ""


def plan_stories(questions, ctx) -> dict:
    """{question: (story, how)} for every question a story answers by its tags, chosen across
    the whole pack rather than one question at a time.

    The best fit goes to the question it fits best. Where that story already answers another
    question here (mapped, kept or chosen first), or was told at this employer in an earlier
    round, a second story that fits nearly as well (STORY_NEAR) takes its place and `how` says
    why; one that does not stays, because a weaker story is worse than a repeated one. A story
    the session mapped or the last build kept is never moved: it is claimed before anything
    is matched."""
    told = told_here(ctx)
    # A story that landed at this employer in an earlier round is one they have heard: its
    # lift from the bank there made it outscore every fresh story, so a final round was
    # prepared with what the behavioural round had just heard (2026-10-21). The bank still
    # lifts what landed elsewhere, and still marks down what fell flat here.
    k = company_key(ctx["company"])
    bank = [r for r in ctx["bank"] or () if not (
        company_key(r.get("company")) == k and not _same_round(r.get("stage"), ctx.get("stage"))
        and _text(r.get("landed")).lower() == "yes")]
    claimed: dict[str, str] = {}
    open_ = []
    for i, item in enumerate(questions):
        story, _how = _fixed_story(item, ctx)
        if story is not None:
            claimed.setdefault(story["title"].lower(), item["question"])
        elif not ctx["map"].get(item["question"]):
            ranked = story_scores(_match_text(item["question"]), ctx["stories"], bank)
            if ranked:
                open_.append((i, item["question"], ranked))
    out = {}
    for _i, q, ranked in sorted(open_, key=lambda x: (-x[2][0][1], x[0])):
        top = ranked[0][1]
        near = [(st, score) for st, score in ranked if score >= top - STORY_NEAR]
        pick = min(near, key=lambda x: (x[0]["title"].lower() in claimed,
                                        x[0]["title"].lower() in told, -x[1]))[0]
        how = "matched by its Use for tags"
        best = ranked[0][0]
        if pick is not best:
            key = best["title"].lower()
            how += "; chosen over %s, %s" % (best["title"], "which answers \"%s\" here"
                                             % claimed[key] if key in claimed else told[key])
        claimed.setdefault(pick["title"].lower(), q)
        out[q] = (pick, how)
    return out


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


def _unnamed(text, names) -> str:
    """`text` with these employer names taken out: "Why are you leaving <their current
    employer>?" is the same question as "Why are you leaving your current role?", and the
    name in the heading kept the two apart."""
    for n in sorted({_text(x) for x in names if _text(x)}, key=len, reverse=True):
        text = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(n), " ", str(text or ""), flags=re.I)
    return _text(text)


def _answer_for(question, answers, names=(), company="", fits=None) -> dict | None:
    """The stock answer for `question`: by any wording its heading holds or its `Use for:`
    tags, with employer names taken out of both, and by meaning for the questions only the
    person can answer (motive): "Why are you looking?" answers "Why are you leaving your
    current role?". Where several answer it, one that fits this employer (`fits`) is taken
    before one that would work against it."""
    kind = motive(question, company)
    hits = []
    for a in answers:
        top = 0.0
        for alt in list(a.get("alternatives") or [a["question"]]) + list(a.get("use_for") or []):
            score = similar(_unnamed(question, names), _unnamed(alt, names))
            if kind and motive(alt, company) == kind:
                score = max(score, 0.75)
            top = max(top, score)
        if top >= 0.5:
            hits.append((bool(fits(a)) if fits else True, top, a))
    return max(hits, key=lambda h: (h[0], h[1]))[2] if hits else None


# The questions only the person can answer: why they are leaving, why each move, why this
# employer, where they are heading. Dates and employers say when someone moved, never why,
# and a pack that said "draft one from the profile, facts only" had a session invent the
# reasons. (kind, the question's words, what Claude asks the person, the Use for: tags the
# answer is kept under.) `{company}` is the employer the pack is for.
MOTIVES = (
    ("leaving", r"\bwhy (?:are you |do you want to |would you )?(?:leav\w*|looking|move on)\b|"
                r"\bwhy now\b|\breasons? for leaving\b|\bwhy (?:are you )?(?:on the market|open "
                r"to (?:a )?(?:move|new))",
     "In your own words, why are you looking to leave {current} now? One or two real reasons, "
     "and what you want more of.",
     "why are you leaving; why are you looking; why now"),
    ("moves", r"\bmoves? between jobs\b|\bwalk me through your (?:career|cv|resume|background)\b|"
              r"\bwhy did you (?:leave|move)\b|\bcareer (?:story|path|moves)\b|\b(?:so many|the) "
              r"moves\b",
     "What made you take each move{moves}? A line each, in your own words.",
     "walk me through your career; the moves between jobs; why did you leave"),
    ("why_us", r"^why (?:this (?:company|firm|team)|us|join us|{company})(?!\w)|\bwhy (?:do you want|"
               r"would you like) to (?:work|join)\b|\bwhat (?:attracts|draws) you\b|"
               r"\bwhy (?:are you )?interested\b",
     "What draws you to {company} in particular, beyond what anyone could read on its website?",
     "why this company; why do you want to work here"),
    ("future", r"\bfive years\b|\b5 years\b|\bwhere do you see yourself\b|\blong[- ]term "
               r"(?:goals?|plans?)\b|\bcareer goals?\b",
     "Where do you want to be in a few years? A sentence or two, in your own words.",
     "where do you see yourself in five years; long-term goals"),
)
# What /interview asks before anything is written for one of these, and what `check` holds on
# (prep.py holds it, so the call prep's check reads the same mark).
ASK_MARK = prep.ASK_MARK


def motive(question, company="") -> str:
    """The kind of motivation question this is (MOTIVES), or ""."""
    q = _text(question)
    for kind, rx, _ask, _tags in MOTIVES:
        rx = rx.replace("{company}", re.escape(_text(company)) if _text(company) else r"\b\B")
        if re.search(rx, q, re.I):
            return kind
    return ""


def motive_ask(kind, ctx) -> str:
    """The one plain question Claude asks the person for a motivation answer."""
    ask = next(a for k, _rx, a, _t in MOTIVES if k == kind)
    employers = [_text(e.get("company")) for e in ctx["facts"].get("employers") or []
                 if isinstance(e, dict) and _text(e.get("company"))]
    current = [_text(e.get("company")) for e in ctx["facts"].get("employers") or []
               if isinstance(e, dict) and "present" in _text(e.get("dates")).lower()]
    return ask.format(company=ctx["company"], current=current[0] if current else "where you are",
                      moves=" (%s)" % ", then ".join(reversed(employers)) if len(employers) > 1
                      else "")


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


def _ahead_key(s) -> tuple:
    """When a stage still to come is: its day and time, or the first day it was offered on; a
    stage with no day at all comes after every dated one."""
    day = s.get("date") or min(s.get("offered") or [""]) or "9999-12-31"
    return (day, s.get("time") or "")


def next_stage(stages, today="") -> dict:
    """The stage this pack is for, when none is named: the earliest one booked ahead (by its
    day, never by where its line sits: a later round booked first came out as the next one,
    the audit, 2026-11-03), else the next undone. A booked stage whose date has passed and
    nobody ticked was most likely held: it is passed over, as a held one would be."""
    past = [i for i, s in enumerate(stages) if s["scheduled"] and not s["done"]
            and today and s.get("date") and s["date"] < today]
    booked = [s for i, s in enumerate(stages) if s["scheduled"] and not s["done"] and i not in past]
    if booked:
        return min(booked, key=_ahead_key)
    done = [i for i, s in enumerate(stages) if s["done"] or i in past]
    after = stages[(done[-1] + 1) if done else 0:]
    if after:
        return after[0]
    # Every stage on record held and none booked: the next is the next round, never the
    # "Phone screen" a pack assumes when nothing is on record at all.
    return {"label": "Round %d" % (len(stages) + 1), "date": "", "with": ""} if stages else {}


# "2. <question> -> story: <title>" on one screen: the story each question was answered with
# when the document was last built.
_PLAN_STORY = re.compile(r"^\d+\. (.+?) -> story: (.+?)\s*$")


def _kept_map(living) -> dict:
    """{question: story title} from the living document's last build. A session's --map is
    kept nowhere else, so a bank's rebuild without it gave "What would you do differently
    now?" no story, where the last build had answered it with one the session chose."""
    screen = str(living or "").split("## On one screen\n", 1)
    if len(screen) < 2:
        return {}
    out = {}
    for line in screen[1].split("\n## ", 1)[0].splitlines():
        m = _PLAN_STORY.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def last_build(folder) -> dict:
    """{"stage", "stories": {question: story}} of the living document's last build: the stage
    it was built for (its record, else its own "Next:" line) and the stories its one screen
    gave each question. {} when there is none."""
    living = _read(os.path.join(folder, LIVING))
    if not living:
        return {}
    record = built_record(folder) or {}
    m = _NEXT.search(living)
    stage = _text(record.get("stage")) or (m.group(1).strip() if m else "")
    return {"stage": stage, "stories": _kept_map(living)}


def kept_stories(folder, stage) -> dict:
    """{question: story} a rebuild keeps from the last build, for the same round only: a
    story was kept wherever matching had chosen it, so a final round re-told what the
    behavioural round had told (2026-10-21). With a record of the build, only the stories the
    session mapped (--map) are kept; matching chooses the rest again, across the whole plan.
    A document from before the record keeps each story for its first question only, so an
    older build's story on two questions is not carried on."""
    built = last_build(folder)
    if not built or not _same_round(built.get("stage"), stage):
        return {}
    record = built_record(folder)
    if record is not None:
        got = record.get("mapped") or {}
        return {str(q): str(t) for q, t in got.items() if _text(t)} \
            if isinstance(got, dict) else {}
    out, seen = {}, set()
    for q, title in built["stories"].items():
        if title.lower() not in seen:
            seen.add(title.lower())
            out[q] = title
    return out


def _kept_story(question, ctx) -> str:
    """The story the last build kept for this question, unless it was told at this employer
    in an earlier round: "" when matching decides."""
    kept = _text((ctx.get("kept_map") or {}).get(question))
    return "" if not kept or kept.lower() in told_here(ctx) else kept


def _at(stage) -> str:
    """"at the Phone screen", "in Round 2 (behavioural)": a stage as a sentence names it."""
    stage = _text(stage)
    return "in %s" % stage if re.match(r"(?i)(?:round|stage)\b", stage) else "at the %s" % stage


def _same_round(a, b) -> bool:
    """Do two stage names name one round? "Round 2 (technical)" and "Round 2" do; "Round 2"
    and "Round 20" do not."""
    a, b = what_works._norm(a), what_works._norm(b)
    return bool(a and b) and (a == b or a.startswith(b + " ") or b.startswith(a + " "))


def _round_words(text) -> frozenset:
    return frozenset(re.findall(r"[a-z]+|\d+", _text(text).lower()))


def _pack_for_round(filename, stage) -> bool:
    """Is `interview_prep_<x>.md` a pack for this round, under any of the names chats gave
    one: "round2_technical", "round_2" and "technical_round_2" are all "Round 2 (technical)".
    Its words and the stage's, one set inside the other; "round_20" is not "Round 2"."""
    m = re.match(r"interview_prep_(.+)\.md$", filename)
    a, b = _round_words(m.group(1) if m else ""), _round_words(stage)
    return bool(a and b) and (a <= b or b <= a)


def _built_for(folder, stages, found, today="") -> str:
    """The stage the living document was last built for, when a rebuild names none and it is
    still the one ahead: the same round as the next one on record, by its fuller name; else,
    unless the next one is booked, the last one built while no held stage has passed it. A
    bank's rebuild with no --stage turned "Round 2 (technical)" into "Round 2" and kept both in
    the stages line; a checklist's unbooked "Technical interview" did the same."""
    m = _STAGES_MARK.search(_read(os.path.join(folder, LIVING)))
    built = [x for x in (m.group(1).split("; ") if m else []) if x]
    ahead = _text(found.get("label"))
    same = [x for x in built if _same_round(x, ahead)]
    if same:
        return max(same, key=len)
    if not built or found.get("scheduled"):
        return ""
    last = built[-1]
    # Held as next_stage reads it: ticked, or booked for a day now past.
    held = any((s["done"] or s["scheduled"] and today and s.get("date") and s["date"] < today)
               and (_same_round(s["label"], last) or s["step"] == what_works.stage_step(last))
               for s in stages)
    return "" if held else last


# A process came through a person, not a portal, so its posting may not be held at all. Its
# folder still gets a job_posting.md, as every application folder has one: one without it
# turned the person's own CI red on the app's folder test, and they could not land work.
POSTING_NOT_HELD = profile_facts.POSTING_NOT_HELD


def write_posting(folder, company, role, posting="", source="", today="") -> str:
    """job_posting.md for a process: the posting's text, fenced, when `posting` is a file
    holding it; its link when `posting` (or the row's source) is one; and a line saying the
    text is not held. Kept once it holds text. Returns "written", "kept" or "replaced"."""
    path = os.path.join(folder, "job_posting.md")
    had = _read(path)
    if had and (POSTING_NOT_HELD not in had or not _text(posting)):
        return "kept"
    text, url = "", ""
    posting = _text(posting)
    if re.match(r"https?://", posting):
        url = posting
    elif posting:
        if not os.path.isfile(posting):
            raise ValueError("--posting %r is neither a link nor a file holding the posting's "
                             "text" % posting)
        text = _read(posting)
    if not url and re.match(r"https?://", _text(source)):
        url = _text(source)
    lines = ["# %s - %s" % (role, company), ""]
    if url:
        lines.append("- **Source:** %s" % url)
    lines += ["- **Retrieved:** %s, for a hiring process with no application"
              % (_text(today) or dt.date.today().isoformat()), ""]
    if text.strip():
        lines.append(untrusted.fence(text, label="job posting"))
    else:
        lines.append("%s This process came through a person, not a portal. When the posting is "
                     "found, keep its text: python3 tools/interview_pack.py process \"%s\" "
                     "--contact <who leads it> --role \"%s\" --posting <a file holding it>"
                     % (POSTING_NOT_HELD, company, role))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return "replaced" if had else "written"


def missing_postings(tracker=None) -> list:
    """[(company, role, folder)] for every process whose folder has no job_posting.md: the
    ones registered before process wrote it."""
    tracker = what_works._csv(person.state("job_search_tracker.csv")) if tracker is None \
        else tracker
    out = []
    for r in tracker:
        if not is_process(r):
            continue
        folder = docpaths.app_folder(_text(r.get("company")), _text(r.get("role")))
        if os.path.isdir(folder) and not os.path.exists(os.path.join(folder, "job_posting.md")):
            out.append((_text(r.get("company")), _text(r.get("role")), folder))
    return out


def process_channel(contact) -> str:
    """The tracker's `channel` for a process, or an application, that goes through this
    contact: `referral` when they are putting the candidate forward, `recruiter` for a
    recruiter, `contact` otherwise. One answer for a process (register_process) and for a
    resume drafted for them (record_drafts.py, stage_picks.py --for-contact)."""
    c = contact or {}
    # "declined: no referral" is the opposite of one: read as `_referred` reads it.
    referral = (_text(c.get("status")) == "referral_in_progress"
                or _text(c.get("route")).startswith("referral")
                or _said_referral(_text(c.get("outcome"))))
    return "referral" if referral else ("recruiter" if prep.is_recruiter(c) else "contact")


def register_process(company, contact_id, role, stage="", date="", with_="", today=None,
                     contacts=None, posting="", time="", zone="", minutes=0, due=False) -> tuple:
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
    process = dict(status="interview", channel=process_channel(c),
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
        # so nothing reads it as an application waiting to go, or nudges it. Its source
        # stays: it is the posting's link, and the contact is named beside it.
        have.update({k_: v for k_, v in process.items()
                     if k_ != "source" or not _text(have.get("source"))})
        have["notes"] = "; ".join(x for x in (_text(have.get("notes")), note + "; the drafted "
                                              "documents were never sent") if x)
        csv_store.write_rows(tracker_path, rows, record_drafts.HEADER)
    folder = docpaths.app_folder(company, role)
    os.makedirs(folder, exist_ok=True)
    write_posting(folder, company, _text(role), posting, have.get("source"), today)
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
        text = _with_stage(text, stage, date, with_, time, zone, minutes, due)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return have, folder, added


def zone_name(zone) -> str:
    """A zone as a stage line keeps it: the time zone's own name where one is given and the
    standard library knows it ("America/Toronto"), else the invite's word in capitals (EST),
    else "". Writing the name is the way: a word is read later, and some words name two
    zones."""
    z = _text(zone)
    if "/" in z:
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(z)
            return z
        except Exception:  # noqa: BLE001  not a zone this machine knows
            return ""
    if re.fullmatch(r"[A-Za-z]{2,5}", z):
        return z.upper()
    # Words a person writes ("Toronto time", "Eastern", "Pacific Time"), kept as the zone's
    # own name: they gave no time at all before (the audit, 2026-11-03).
    return person.zone_in(z)


_ORDINALS = ((r"first|initial|1st|one", "1"), (r"second|2nd|two", "2"), (r"third|3rd|three", "3"),
             (r"fourth|4th|four", "4"))


def _round_key(label) -> str:
    """Which round a stage name says, whatever words it uses: "Initial round", "First round"
    and "Round 1 (technical)" are all "round 1"; "Final round" is "final"; "" when it names no
    round. A move written under another name booked the round twice (the audit, 2026-11-03)."""
    t = _text(label).lower()
    for words, n in _ORDINALS:
        t = re.sub(r"\b(?:%s)\b" % words, n, t)
    m = re.search(r"\b(?:round|stage)\s*(\d+)\b|\b(\d+)\s*(?:round|stage)\b", t)
    if m:
        return "round " + (m.group(1) or m.group(2))
    return "final" if re.search(r"\bfinal\b", t) else ""


def _with_stage(text, stage, date="", with_="", time="", zone="", minutes=0, due=False,
                offered=(), reply_by="", place="") -> str:
    """outcome.md's text with this stage booked on its checklist: `- [ ] <stage> (scheduled
    <date> [<HH:MM> [<zone>]], with <who>)`, the line the brief, /outcome, every pack and the
    page read. `zone` is one an invite gives beside the time (EST), when not the person's.
    With no day and `offered` days, the invitation's choice: `(offered <day>, <day>; reply by
    <day>, with <who>)`, until the day chosen is booked over it."""
    # [ \t], never \s: in a multi-line match \s ate the newline and the blank line after a
    # rebooked stage, so booking it twice ran the next heading into it.
    same = re.compile(r"^- \[ \] %s(?:[ \t]*\(.*\))?[ \t]*$" % re.escape(stage), re.M | re.I)
    hits = list(same.finditer(text))
    if not hits and _round_key(stage):
        # The same round under another name ("Initial round" moved as "First round"): the
        # one line, moved, never two rounds booked.
        hits = [m for m in re.finditer(r"^- \[ \] ([^(\n]+?)(?:[ \t]*\(.*\))?[ \t]*$", text, re.M)
                if _round_key(m.group(1)) == _round_key(stage)][:1]
    if not _text(with_) and hits:
        # Rebooked with a new date only: the interviewer already on the line stays.
        had = re.search(r",\s*with\s+([^)]*)\)", hits[0].group(0))
        with_ = had.group(1).strip() if had else ""
    if not what_works.clock(time) and hits:
        # Said again for the same day with no time: the time on the line stays.
        was = what_works.outcome_stages("## Interview stages reached\n" + hits[0].group(0))
        if was and was[0]["date"] == _text(date):
            time, zone = was[0].get("time") or "", was[0].get("zone") or ""
    if hits and not (minutes or due):
        # Rebooked: what it is and how long it lasts stay, except that a time given now makes
        # it a meeting at that time, never a test that drops it (the release review).
        was = what_works.outcome_stages("## Interview stages reached\n" + hits[0].group(0))
        if was:
            minutes = was[0].get("minutes") or 0
            due = was[0].get("kind") == "test" and not what_works.clock(time)
            place = place or was[0].get("place") or ""
    place = " ".join(re.sub(r"[,()]", " ", _text(place)).split())[:60]
    given = _text(zone)
    zone = zone_name(zone)
    if given and not zone:
        # A zone this cannot place ("Pacific Time", a misspelt name): no time rather than one
        # read later in the person's own zone, hours out.
        time = ""
    when = ("%s %s%s" % (date, what_works.clock(time), " " + zone if zone else "")
            if what_works.clock(time) and not due else date)
    length = ", %d min" % int(minutes) if minutes and not due else ""
    days = sorted({d for d in (offered or ()) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _text(d))})
    if _text(date):
        line = "- [ ] %s (%s %s%s%s%s)" % (stage, "due" if due else "scheduled", when, length,
                                           ", on %s" % place if place and not due else "",
                                           ", with %s" % with_ if _text(with_) else "")
    elif days:
        line = "- [ ] %s (offered %s%s%s)" % (
            stage, ", ".join(days),
            "; reply by %s" % reply_by if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _text(reply_by)) else "",
            ", with %s" % with_ if _text(with_) else "")
    else:
        line = "- [ ] %s" % stage
    if not hits:
        # A bare template line for the same step ("Phone screen" when a recruiter screen
        # is booked) is this stage under another name: it is replaced, never doubled.
        step = what_works.stage_step(stage)
        hits = [m for m in re.finditer(r"^- \[ \] ([^(\n]+?)[ \t]*$", text, re.M)
                if what_works.stage_step(m.group(1)) == step][:1]
    if hits:
        # The first keeps its place with the new date; any later copies go, line and all.
        for m in reversed(hits[1:]):
            end = m.end() + 1 if text[m.end():m.end() + 1] == "\n" else m.end()
            text = text[:m.start()] + text[end:]
        return text[:hits[0].start()] + line + text[hits[0].end():]
    # A new stage goes in the order the rounds run: after the last one held or booked for a
    # day before it, so a later round booked first never reads as the next one.
    when_of = lambda m: (what_works.outcome_stages(  # noqa: E731
        "## Interview stages reached\n" + m.group(0)) or [{}])[0].get("date") or ""
    before = [m for m in re.finditer(r"^- \[[ xX]\] .*$", text, re.M)
              if m.group(0)[3] in "xX" or (_text(date) and when_of(m) and when_of(m) <= date)]
    if before:
        return text[:before[-1].end()] + "\n" + line + text[before[-1].end():]
    if "## Interview stages reached\n" in text:
        return text.replace("## Interview stages reached\n",
                            "## Interview stages reached\n%s\n" % line, 1)
    return text.rstrip("\n") + "\n\n## Interview stages reached\n%s\n" % line


def tick_stage(path, stage) -> bool:
    """Tick one stage held (or a test sat) on outcome.md's checklist: `- [ ] <stage> (...)`
    becomes `- [x] ...`. False when no such line is there to tick."""
    text = _read(path)
    m = re.search(r"^- \[ \] %s(?=[ \t]*(?:\(|$))" % re.escape(_text(stage)), text, re.M | re.I) \
        if _text(stage) else None
    if not m:
        return False
    text = text[:m.start()] + "- [x]" + text[m.start() + 5:]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return True


def record_stage(folder, company, role, stage, date, with_="", today=None, time="",
                 zone="", minutes=0, due=False, offered=(), reply_by="", place="") -> str:
    """Book a stage given to `pack --write` in the process's outcome.md, the record the
    brief reminds from and every later pack reads: given there with a date, it was used
    for that one pack and recorded nowhere (interview audit, 2026-10-25). An outcome.md not
    there yet is started in the form documents/README.md gives. Returns the line booked."""
    out = os.path.join(folder, "outcome.md")
    text = _read(out)
    if not text:
        text = ("# Outcome: %s - %s\n\n**Status:** in_progress\n\n## Interview stages "
                "reached\n\n## Notes\n- %s: %s booked %s.\n"
                % (company, role, _text(today) or dt.date.today().isoformat(), stage,
                   "for " + date if _text(date) else "with the day still to choose"))
    text = _with_stage(text, stage, date, with_, time, zone, minutes, due, offered, reply_by,
                       place)
    os.makedirs(folder, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    m = re.search(r"^- \[ \] %s.*$" % re.escape(stage), text, re.M | re.I)
    return m.group(0) if m else ""


# ------------------------------------------------------------------ a time said elsewhere

# An interview's day and time as a note, an invite or a message says them: "Wednesday 28
# October at 2pm", "Oct 28th, 14:00 EST", "2026-10-28 at 9.30am", "2pm on the 28th of
# October". The time sat in a contact's note while the interview's record had its day alone,
# so the page said "time not set" and the chat told the person to add it themselves
# (2026-10-29): wherever it is said, the interview's own record takes it.
_MONTH_RX = (r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
             r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_SAID_DAYS = (
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?%s(?:,?\s+(?P<y>\d{4})\b)?"
               % _MONTH_RX, re.I),
    re.compile(r"\b%s\s+(?:the\s+)?(?P<d>\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(?P<y>\d{4})\b)?"
               % _MONTH_RX, re.I),
)
_SAID_CLOCK = (r"(?<![\d:.])(?P<time>\d{1,2}[:.]\d{2}(?:\s*[ap]\.?m\b\.?)?|\d{1,2}\s*[ap]\.?m\b\.?)"
               r"(?:[ \t]*\(?(?-i:(?P<zone>[A-Z]{2,5}\b|[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)?"
               r"[ \t]+(?i:time)\b|(?:Eastern|Pacific|Central|Mountain|Atlantic)\b)))?")
# Right after the day, or a few plain words on ("28 October is now at 11:15"): never across
# a number, so another day's time is not taken.
_CLOCK_AFTER = re.compile(r"[ \t,]*(?:(?:[a-z]+[ \t]+){0,3}?(?:at|from|@)[ \t]*)?" + _SAID_CLOCK,
                          re.I)
_NOTE_DAY = re.compile(r"(?=\b\d{4}-\d{2}-\d{2}:)")
_CLOCK_BEFORE = re.compile(_SAID_CLOCK + r"[ \t,]*(?:on[ \t]+)?(?:(?:mon|tue|wed|thu|fri|sat|"
                           r"sun)[a-z]*\.?,?[ \t]+)?(?:the[ \t]+)?$", re.I)
_MONTHS3 = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _zone_word(word) -> str:
    """A zone written beside a time (EST, CET, BST, "Toronto time", "Eastern"), or "" for
    capitals that are not one. Words are kept as the zone's own name."""
    import app_model
    w = _text(word)
    if re.fullmatch(r"[A-Z]{2,5}", w):
        return w if w in app_model._ZONE_WORDS or re.fullmatch(r"[A-Z]{1,4}T", w) else ""
    return person.zone_in(w) if w else ""


def time_said(text, day) -> tuple:
    """(HH:MM, zone or "") for `day` (YYYY-MM-DD) where `text` gives that day with a time
    beside it, else ("", ""). A day given with no year is taken as `day`'s own."""
    text, day = str(text or ""), _text(day)
    try:
        want = dt.date.fromisoformat(day)
    except ValueError:
        return "", ""
    for rx in _SAID_DAYS:
        for m in rx.finditer(text):
            g = m.groupdict()
            month = int(g["m"]) if g.get("m") else _MONTHS3.index(g["mon"][:3].lower()) + 1
            if (month, int(g["d"])) != (want.month, want.day) or (
                    g.get("y") and int(g["y"]) != want.year):
                continue
            hit = (_CLOCK_AFTER.match(text, m.end())
                   or _CLOCK_BEFORE.search(text[max(0, m.start() - 40):m.start()]))
            clock = what_works.clock(hit.group("time")) if hit else ""
            if clock:
                return clock, _zone_word(hit.group("zone"))
    return "", ""


def take_times(today=None, company="", tracker=None, contacts=None, threads=None) -> list:
    """Every booked interview with no time on its record whose day is said, with a time, in
    the application's notes, a note on someone at that employer, or a message recorded with
    them: the time goes on the stage's line in outcome.md, the record the page and every pack
    read. Where they disagree, the newest message says it; where that is still not one time,
    nothing is written. `company` limits it to one employer. Returns what was written, as
    [{company, role, stage, date, time, zone}]."""
    import open_actions
    today = _text(today) or dt.date.today().isoformat()
    if tracker is None:
        tracker = what_works._csv(person.state("job_search_tracker.csv"))
    if contacts is None:
        path = person.state("network_contacts.csv")
        contacts = state.load_contacts(path) if os.path.exists(path) else []
    if threads is None:
        path = person.state("network_threads.csv")
        threads = state.load_threads(path) if os.path.exists(path) else []
    only = company_key(company) if _text(company) else ""
    out = []
    for row in tracker:
        k = company_key(row.get("company"))
        if not k or (only and k != only):
            continue
        folder, _files, stages = open_actions.stages(row)
        open_ = [s for s in stages if s["date"] and not s["done"] and s["date"] >= today
                 and not s.get("time")]
        if not open_:
            continue
        here = [c for c in contacts if company_key(c.get("company")) == k]
        ids = {_text(c.get("contact_id")) for c in here} - {""}
        # A note's entries are dated by their "YYYY-MM-DD:" start, as the tools write them.
        said = [(piece[:10] if re.match(r"\d{4}-\d{2}-\d{2}:", piece) else "", piece)
                for words in [row.get("notes")] + [c.get(f) for c in here
                                                   for f in ("notes", "next_action")]
                for piece in _NOTE_DAY.split(_text(words))]
        said += [(_text(t.get("date")), t.get(f)) for t in threads
                 if _text(t.get("contact_id")) in ids for f in ("full_text", "summary", "subject")]
        for s in open_:
            found = [(when, time_said(words, s["date"])) for when, words in said if _text(words)]
            found = [(when, got) for when, got in found if got[0]]
            if not found:
                continue
            newest = max(when for when, _ in found)
            times = {got for when, got in found if when == newest}
            if len(times) != 1:
                continue
            clock, zone = times.pop()
            record_stage(folder, _text(row.get("company")), _text(row.get("role")), s["label"],
                         s["date"], "", today=today, time=clock, zone=zone)
            out.append({"company": _text(row.get("company")), "role": _text(row.get("role")),
                        "stage": s["label"], "date": s["date"], "time": clock, "zone": zone})
    return out


def saved_line(got: dict) -> str:
    """What a chat may pass on as it is, once a time is on the interview's record."""
    return "Saved on the interview: %s with %s on %s at %s%s." % (
        got["stage"], got["company"], got["date"], got["time"],
        " " + got["zone"] if got.get("zone") else "")


# The archive's own Status word for each tracker outcome (documents/README.md), and the
# checklist line an offer ticks.
ARCHIVE_STATUS = {"hired": "hired", "rejected": "rejected", "no_response": "no_response",
                  "offer_declined": "offer_declined", "withdrawn": "interview_only"}


def record_result(folder, company, role, status, date, today=None) -> str:
    """What happened, written into outcome.md as /outcome Step 3 writes it: an offer ticks
    "Offer received" with its day; a resolution sets **Status:** and **Date resolved:**;
    every line already there is kept. An outcome.md not there yet is started in the form
    documents/README.md gives. Returns the text written."""
    out = os.path.join(folder, "outcome.md")
    text = _read(out) or ("# Outcome: %s - %s\n\n**Status:** in_progress\n\n## Interview "
                          "stages reached\n\n## Notes\n" % (company, role))
    day = _text(date) or _text(today) or dt.date.today().isoformat()
    if status == "offer":
        line = "- [x] Offer received (%s)" % day
        hit = re.search(r"^- \[[ xX]\] Offer received.*$", text, re.M)
        if hit:
            text = text[:hit.start()] + line + text[hit.end():]
        else:
            text = _with_stage(text, "Offer received", "", "").replace(
                "- [ ] Offer received", line, 1)
    word = ARCHIVE_STATUS.get(status)
    if word:
        # One status a file: a "Status: in_progress" written by hand under the bold one kept
        # saying the process was live after it was resolved (2026-11-03).
        any_status = r"^(?:\*\*)?Status:(?:\*\*)?[ \t]*\S.*$"
        if re.search(any_status, text, re.M):
            text = re.sub(any_status, "**Status:** %s" % word, text, count=1, flags=re.M)
            first = re.search(r"^\*\*Status:\*\* .*$", text, re.M)
            head, rest = text[:first.end()], text[first.end():]
            text = head + re.sub(any_status + r"\n?", "", rest, flags=re.M)
        else:
            text = re.sub(r"^(# .*\n)", r"\1\n**Status:** %s\n" % word, text, count=1)
        if re.search(r"^\*\*Date resolved:\*\*.*$", text, re.M):
            text = re.sub(r"^\*\*Date resolved:\*\*.*$", "**Date resolved:** %s" % day, text,
                          count=1, flags=re.M)
        else:
            text = re.sub(r"^(\*\*Status:\*\*.*)$", r"\1\n**Date resolved:** %s" % day, text,
                          count=1, flags=re.M)
    os.makedirs(folder, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


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
    folder = docpaths.app_folder(company, role)
    if not os.path.isdir(folder):
        # Built from a folder that is not there, a pack has no posting, no form and no
        # stages, and says nothing about it. A folder at this employer under another
        # name is the likely one: name them rather than guess.
        mine = {os.path.basename(docpaths.app_folder(_text(r.get("company")), _text(r.get("role"))))
                for r in tracker if company_key(r.get("company")) == company_key(company)
                and r is not row}
        others = [f for f in docpaths.employer_folders(company) if f not in mine]
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
        found = next_stage(stages, today)
        stage = _built_for(folder, stages, found, today) or found.get("label") or "Phone screen"
        date, with_ = date or found.get("date", ""), with_ or found.get("with", "")
    else:
        same = [s for s in stages if s["label"].lower() == stage.lower()]
        if same:
            date, with_ = date or same[0]["date"], with_ or same[0]["with"]
    assumed = ""
    if not _text(with_):
        with_ = assumed = _lead_interviewer({"company": company, "row": row}, contacts, stage)
    # One reader of the posting for the pack and the call prep: a process's placeholder is
    # not a posting, and nothing in it may be read as a requirement.
    posting = profile_facts.posting_in(folder)
    threads = state.load_threads(os.path.join(root, "network_threads.csv")) \
        if threads is None else threads
    draft = what_works.draft_for(row, what_works.drafts(root))
    facts = profile_facts.build(role=role, posting=posting)
    gaps_hard = bridges.gaps(" ".join(x for x in (role, posting) if x))
    # A skill they said yes to claiming on this application is on the resume: it is a
    # question to expect (gap_lines), never a gap. Left in, the pack told them to claim it
    # and never to claim it, one section apart.
    yes = profile_facts.consented(draft)
    gaps_hard = [g for g in gaps_hard if _text(g.asked).casefold() not in yes]
    facts = profile_facts.without(facts, yes)
    return {
        "company": company, "role": role, "row": row, "folder": folder, "today": today,
        "stage": stage, "step": what_works.stage_step(stage), "date": date, "with": with_,
        "with_assumed": assumed,
        "outcome": outcome, "stages": stages, "posting": posting,
        # A process had no form: answers record_drafts wrote for a draft never sent were
        # never seen by anyone.
        "form": [] if is_process(row) else
        _form_answers(_read(os.path.join(folder, "screening_answers.md"))),
        "form_fields": [] if is_process(row) else
        [ln.rstrip() for ln in _read(os.path.join(folder, "form_fields.txt")).splitlines()
         if ln.strip()],
        "outreach_sent": os.path.exists(os.path.join(folder, "outreach.md")),
        "draft": draft,
        "research": prep.load_research(company, root),
        "facts": facts,
        "gaps_hard": gaps_hard,
        "stories": stories(), "answers": hard_answers(),
        "bank": what_works.bank(root), "contacts": contacts, "threads": threads,
        "map": dict(story_map or {}),
        "kept_map": kept_stories(folder, stage),
        "built": last_build(folder),
        # A pack for this same round under another name is an older draft of it, not an
        # earlier round: its stories were never told (handkept_notes has it folded in).
        "earlier": sorted(f for f in _listdir(folder)
                          if f.startswith("interview_prep_") and f != pack_name(stage)
                          and not _pack_for_round(f, stage)),
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
                                  {"evidence": evidence, "req": True,
                                   "evidence_source": _text(draft.get("_path"))}))
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
    # A screen opens the same way everywhere, so its standard questions come first; the
    # questions added to the map follow them. Put first, they took the one screen from
    # "Tell me about yourself" (2026-10-20). A later stage leads on what came back from
    # the one before.
    order = {
        "screen": [stage[:3], "map", "here", group["gaps"][:1], stage[3:6], "cond", "format",
                   stage[6:], "reqs", group["gaps"][1:], "again"],
        "technical": ["map", "here", "reqs", "gaps", "format", "stage", "again"],
        "final": ["map", "here", stage[:1], group["gaps"][:1], stage[1:], "format", "reqs",
                  group["gaps"][1:], "again"],
        "offer": ["map", "here"],
    }[step if step in STAGE_QUESTIONS else "technical"]
    for part in order:
        for question, why, source, extra in (group[part] if isinstance(part, str) else part):
            add(question, why, source, **extra)
    # "Everything" (Tweak I2) shows a third more questions; the rest of the pack is the same.
    return out[:MAX_QUESTIONS + (6 if person.get("prep.detail", "") == "everything" else 0)]


# A question about pay, by whole word: "payments data" and "Payward" are not pay.
_PAY_Q = r"\bsalary\b|\bcompensation\b|\bpay\b|\bremuneration\b|\bexpected (?:base|package)\b"


def _form_value(ctx, pattern) -> tuple:
    """(question, answer) from the portal's form whose question matches, or ("", "")."""
    rx = re.compile(pattern, re.I)
    # "[decide: ...]" is a field still to fill, never something the form told them.
    return next(((q, a) for q, a in ctx["form"] if rx.search(q)
                 and not _text(a).startswith("[")), ("", ""))


def call_ctx(contact, role="", facts=None, research=None, application=None, today=None) -> dict:
    """What `answer_for` reads, for a networking call rather than an interview stage. The call
    prep (tools/network/prep.py) answers its questions through this file's functions, so a
    stock answer, a reason only the person can give and an answer that argues against the
    employer are read one way in both documents; it had a builder of its own, and the two
    disagreed."""
    contact, application = contact or {}, application or {}
    return {"company": _text(application.get("company")) or _text(contact.get("company")),
            "role": _text(role), "row": application, "folder": person.state(),
            "today": _text(today) or dt.date.today().isoformat(), "facts": facts or {},
            "map": {}, "stories": stories(), "answers": hard_answers(), "bank": [], "form": [],
            "draft": None, "research": research or {}, "posting": "", "outcome": "",
            "contacts": [contact] if contact else [], "elsewhere": 0}


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
    if not mapped and _kept_story(q, ctx):
        # The story the last build gave it, while that story is still in the file: a rebuild
        # never drops a choice the session made. A story since renamed or removed is passed
        # over quietly, and matching takes it from there.
        kept = _kept_story(q, ctx).lower()
        story = next((s for s in ctx["stories"] if s["title"].lower() == kept), None)
        how = "as the last build answered it"
    # What the letter evidenced comes first: the interviewer read it, and a story that
    # matches a tag better but tells something else contradicts the paper.
    if story is None and not mapped and item.get("evidence"):
        story = story_for_evidence(item["evidence"], ctx["stories"])
        how = "it carries the letter's evidence"
    if story is None and not mapped:
        if q in (ctx.get("plan") or {}):
            # Chosen across the whole pack (plan_stories): the same story twice, or one
            # already told at this employer, gives way to one that fits nearly as well.
            story, how = ctx["plan"][q]
        else:
            story, _score = best_story(_match_text(q), ctx["stories"], ctx["bank"])
            how = "matched by its Use for tags"
    names = [ctx["company"]] + [_text(e.get("company")) for e in facts.get("employers") or []
                                if isinstance(e, dict)]
    prepared = _answer_for(q, ctx["answers"], names, ctx["company"],
                           fits=lambda a: not against_employer(a, ctx))
    kind = motive(q, ctx["company"])
    why_us = kind == "why_us"
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
        heard = places_told.place(ctx["company"])
        if heard:
            lines.append("You told %s you are in %s (source: profile/person.json "
                         "identity.places_told): say the same." % (ctx["company"], heard))
        elif home_place():
            lines.append("You live in %s (source: profile/person.json)" % home_place())
        since = newcomer(ctx)
        if since == JUST_ARRIVED:
            lines.append("You have just arrived (source: profile/person.json): say that, with "
                         "no date or month, and see Small talk.")
        elif since:
            lines.append("You have lived there %s (source: profile/person.json): see Small "
                         "talk, and tell nothing you have not done." % since)
    elif kind == "moves":
        moves = ["%s (%s)" % (_text(e.get("company")), _text(e.get("dates")))
                 for e in facts.get("employers") or [] if isinstance(e, dict) and _text(e.get("company"))]
        if moves:
            lines.append("The moves, newest first: %s (source: %s). Say the one thread that "
                         "joins them, a line a move, ending on why this one." % ("; ".join(moves), prof))
    elif re.search(r"led something|leadership", q, re.I):
        led = [x for x in facts.get("strengths") or [] if re.search(
            r"\b(?:mentor|first|introduc|standard|train|onboard|set up|owned|led)\w*", _text(x), re.I)]
        lines += ["From your profile: %s (source: %s)" % (prep.clip(x, 170), prof) for x in led[:2]]
        lines.append("Claim no people management your profile does not hold: lead from what "
                     "you set up, the standards you brought in and who you brought along. Ask "
                     "Claude for an example and it drafts one for you to check.")
    elif re.search(r"interviewing anywhere else", q, re.I):
        n = ctx.get("elsewhere", 0)
        lines.append(("Yes: %s at an interview stage. Say so, name nobody, and invent no "
                      "offer (source: %s)" % ("one other process" if n == 1 else
                                               "%d other processes" % n, prep.TRACKER_SOURCE)) if n else
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
        lines.append("Say what travel works for you, honestly. Your profile says nothing on it "
                     "yet: tell Claude, and the next prep says it.")
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
    # A stock answer that is not for this employer, or still a template, is never printed
    # as an answer: printed with a warning under it, it read as the thing to say.
    careful = against_employer(prepared, ctx) if prepared else ""
    if prepared and careful:
        lines.append("Your stock answer to this is left out for %s: %s (source: %s). Say your "
                     "real reasons for %s." % (ctx["company"], careful, prepared["source"],
                                               ctx["company"]))
        prepared = None
    elif prepared and prepared.get("fill_in"):
        lines.append("Your stock answer to this still has a gap to fill (\"%s\"): fill it in "
                     "with Claude, and the next prep uses it." % prepared["fill_in"])
        prepared = None
    where = places_told.clash(prepared["answer"], ctx["company"]) if prepared else ""
    if where:
        # Printed under a warning, it was still the answer offered as "Prepared", and it told
        # an employer that heard one city that he was settled in another (2026-11-03).
        lines.append("Your stock answer to this is left out for %s: %s." % (ctx["company"],
                                                                           plain_clash(where)))
        prepared = None
    # A stock pay answer with figures of its own beside the band the pack gives: one pack said
    # "around 70 to 80 thousand" on its first page and 70,000 to 85,000 under it
    # (2026-11-03). The band the form gave, else the profile's, is the one said.
    off = pay_differs(prepared["answer"], ctx) if prepared and re.search(_PAY_Q, q, re.I) else ""
    if off:
        lines.append("Your stock answer to this is left out: %s." % off)
        prepared = None
    if prepared:
        lines.append("Prepared: %s (source: %s)%s" % (
            prepared["answer"], prepared["source"],
            " Marked CONFIRM in the file: check it is still true first." if prepared["confirm"]
            else ""))
    ask = ""
    if kind and not story and not prepared:
        # Their reasons are theirs: asked first, never drafted from dates and employers unasked.
        # If they ask for a draft of them instead, it is written under the question, marked
        # (interview.md rule 2).
        # The command that keeps their answer is Claude's (interview.md Step 3), printed by
        # `pack` for the session, never written where the person reads.
        ask = "%s \"%s\" Or ask Claude to draft one for you to check." % (
            ASK_MARK, motive_ask(kind, ctx))
        lines.insert(0, ask)
    if story:
        lines.append("Story: %s (%s; source: %s)" % (story["title"], how, story["source"]))
    elif mapped:
        lines.append("Matched to \"%s\", which is not one of your stories: check its title."
                     % mapped)

    def done(kind_, short):
        # `prepared` (the stock answer used, or None) and `ask` (the line asking for their
        # reasons, or "") as they are, for a reader that places one answer: the call prep.
        return {"kind": kind_, "short": short, "lines": lines, "prepared": prepared, "ask": ask}

    if story:
        return done("story", "story: %s" % story["title"])
    if prepared:
        return done("prepared", "your prepared answer")
    if kind:
        return done("ask", "your own reasons: Claude asks you first")
    if why_us:
        return done("say", "something true about them" + (", and what your letter told them"
                                             if _text((ctx["draft"] or {}).get("p2")) else ""))
    if item.get("req") and not item.get("evidence") and not story:
        # The paper claimed nothing here: a story drafted unasked would claim more than it did.
        lines.append("The letter named no evidence for this. If your profile holds none, it is "
                     "a gap: say the nearest true thing plainly (Gaps and honest framing). Ask "
                     "Claude for an example and it drafts one for you to check.")
        return done("none", "no evidence on paper: the nearest true thing")
    if item.get("gap") and not item.get("framing"):
        lines.append("No honest framing written for this yet: settle one with Claude before "
                     "the interview. Say plainly what you do not hold, then the nearest true "
                     "thing. Ask Claude for an example of using it and it drafts one for you "
                     "to check.")
        return done("none", "a gap: settle how you will put it")
    if lines:
        first = re.sub(r" \(source: .*$", "", lines[0]).replace("The form said: ", "the form said ")
        if first.startswith(prep.RAW_MARK):
            first = "your summary, in your own words"
        return done("say", prep._short(first, 70))
    lines.append("No story or prepared answer covers this yet: Claude writes one from your "
                 "profile, and asked for an example you cannot recall, drafts one for you to "
                 "check.")
    return done("none", "no story yet: Claude writes one")


# ---------------------------------------------------------------- the other sections

HOOK_CHARS = 200


def _hook_text(value) -> str:
    """One hook as it reads on one screen: the research note's first whole sentence, its
    bullet marker off, cut where a clause ends only when it runs long. Cut at a fixed
    width, a research bullet ended mid-sentence (2026-10-20)."""
    return prep._short(re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s+", "", _text(value)), HOOK_CHARS)


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
    # A stock answer that works against this employer, whether or not this stage asks its
    # question: a five-year answer of "product companies rather than more consulting" was
    # one follow-up away at a consultancy, and nothing flagged it.
    out = ["- Not as it stands: your answer to \"%s\": %s. Rewrite it for %s before it comes "
           "up (source: %s)" % (a["question"], why, ctx["company"], a["source"])
           for a in ctx["answers"] for why in [against_employer(a, ctx)] if why]
    # A prohibition the research wrote as one ("Do not call it a discounter") is said once,
    # never as "Do not say: Do not ...".
    out += ["- %s%s (source: %s)" % ("" if re.match(r"(?i)(?:do not|don'?t|never|avoid)\b",
                                                    f.value) else "Do not say: ", f.value, f.source)
            for f in prep._facts(research.get("do_not_claim"), default)]
    out += ["- Careful: %s (source: %s)" % (f.value, f.source)
            for f in prep._facts(research.get("cautions"), default)]
    # The default advice, worded so it never forbids what the person asks for: a draft of
    # an example is written when asked, marked for them to confirm (interview.md rule 2).
    for g in ctx["gaps_hard"]:
        head = "Never claim %s" % g.asked + (": " + _text(g.note).rstrip(" .") if _text(g.note)
                                             else "")
        out.append("- %s. Ask Claude for an example and it drafts one for you to check "
                   "(source: your profile)" % head)
    phrases = [p for p, _rx in (never_say if never_say is not None else learned.never_say())]
    if phrases:
        out.append("- Words you have said never to use: %s (source: %s)" % (
            ", ".join('"%s"' % p for p in phrases[:MAX_NEVER_SAY]), prep.LEARNED_SOURCE))
    return out


# The one rule every interview keeps, said once where it belongs (What the paper says), never
# as a warning on the one screen of every pack, where it read as another "don't".
PAPER_RULE = ("- Say nothing in the room the paper does not say, except a draft you asked for "
              "and have made true.")


def paper_lines(ctx) -> list:
    """What the documents they read argued, so nothing said contradicts them, then where the
    resume they hold invites a push (landmine_lines)."""
    return [PAPER_RULE] + _sent_lines(ctx) + landmine_lines(ctx)


def _held_by_contacts(ctx) -> list:
    """The resumes the message log says went to someone at this employer, by name and date.

    A referrer who asked for the resume holds whichever file was sent to them, and that may
    not be the one the tracker row names: the networking chat logs it, the drafting chat
    made it (state.py message --attached)."""
    k, out = company_key(ctx["company"]), []
    for c in ctx["contacts"]:
        if company_key(c.get("company")) != k:
            continue
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        for sent in state.resumes_sent(ctx["threads"], c.get("contact_id")):
            # Which file it was is Claude's to read in the message log; the person reads it as
            # their resume, never as a file name or a command to name it.
            stem = lambda f: os.path.splitext(os.path.basename(_text(f)))[0].lower()  # noqa: E731
            applied = stem((ctx.get("row") or {}).get("cv_file"))
            what = ("your %s" % _noun() + (", a different version from the one you applied with"
                                          if applied and all(stem(f) != applied
                                                             for f in sent["files"]) else "")
                    if sent["files"] else "a %s (which version is not recorded)" % _noun())
            line = "- Sent to %s on %s: %s" % (name, sent["date"] or "an undated day", what)
            # One person kept on two rows, or a send logged twice, is one send: the same line
            # went in a pack twice (2026-11-03).
            if line not in out:
                out.append(line)
    return out


def _files_words(row) -> str:
    """The documents an application went with, as the person names them ("your resume and
    cover letter"), never their file names."""
    got = [w for col, w in (("cv_file", _noun()), ("cover_letter_file", "cover letter"))
           if _text(row.get(col))]
    return "your " + " and ".join(got) if got else ""


def _sent_lines(ctx) -> list:
    row, draft = ctx["row"], ctx["draft"] or {}
    src = _text(draft.get("_path"))
    out = _held_by_contacts(ctx)
    files = [f for f in (row.get("cv_file"), row.get("cover_letter_file")) if _text(f)]
    if ctx.get("process"):
        # Nothing was submitted, so nothing a draft argued reached them.
        out.append("- Nothing went in through a portal, so there is no letter or form: what they "
                   "hold is what the messages carried (What they have been told), and any %s "
                   "sent by email%s." % (_noun(), " or passed on by %s" % referrer_of(ctx)
                                         if referrer_of(ctx) else ""))
        if files:
            out.append("- Drafted for this role and never sent: %s. Not what they read."
                       % _files_words(row))
        return out
    if files:
        out.append("- Sent: %s (source: %s)" % (_files_words(row), prep.TRACKER_SOURCE))
    if ctx["outreach_sent"]:
        out.append("- A note was drafted for the hiring manager or recruiter. If it went, "
                   "whoever it went to may be on the panel.")
    if not draft:
        out.append("- What the letter argued is not on file: read the letter itself before the "
                   "interview.")
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


# ---------------------------------------------------------------- where the resume invites a push

# The interviewer holds the resume, and three things on it draw a question and then a second
# one behind it: a short stay, a gap between jobs, and a title the role may doubt. The pack
# said every claim on the paper must be defensible in depth and never showed which ones would
# be tested. Under a year is short; more than three months between jobs is a gap.
SHORT_TENURE_MONTHS = 12
GAP_MONTHS = 3
_MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                "dec")
_MONTH_YEAR = re.compile(r"\b(%s)[a-z]*\.?\s+((?:19|20)\d{2})\b" % "|".join(_MONTH_NAMES), re.I)
_YEAR_MONTH = re.compile(r"\b((?:19|20)\d{2})-(\d{1,2})\b|\b(\d{1,2})/((?:19|20)\d{2})\b")
_RANGE_SEP = re.compile(r"\s+(?:-|–|—|to)\s+|[–—]", re.I)
# A title's level, lowest first, by the words a title uses for it. Nothing said is the middle.
_LEVELS = ((0, re.compile(r"\b(?:intern|internship|graduate|trainee|apprentice|junior|jr|"
                          r"entry[- ]level|placement)\b", re.I)),
           (3, re.compile(r"\b(?:lead|principal|head|director|vp|chief)\b|"
                          r"(?<!product )(?<!project )(?<!account )(?<!programme )(?<!program )"
                          r"\bmanager\b", re.I)),
           (2, re.compile(r"\b(?:senior|sr)\b", re.I)))
_FIXED_TERM = re.compile(r"\b(?:intern|internship|graduate|trainee|apprentice|placement|"
                         r"contract|contractor|fixed[- ]term|temporary|temp|interim|"
                         r"freelance)\b", re.I)
# What a title says the person does, when the role says another thing.
_FUNCTION = re.compile(r"\b(scientist|engineer|analyst|developer|consultant|architect|"
                       r"designer|researcher|economist|actuary|accountant|planner|"
                       r"product manager|project manager)s?\b", re.I)


def _month(text):
    """(year, month) from "Mar 2023", "2023-03" or "03/2023"; a year alone, or nothing, None."""
    m = _MONTH_YEAR.search(text or "")
    if m:
        return int(m.group(2)), _MONTH_NAMES.index(m.group(1)[:3].lower()) + 1
    m = _YEAR_MONTH.search(text or "")
    if m:
        y, mo = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        return (int(y), int(mo)) if 1 <= int(mo) <= 12 else None
    return None


def _span(dates, today):
    """(start, end, current) as (year, month) from a role's dates, the end today's month for
    a role held now; None where either end is not given to the month."""
    parts = _RANGE_SEP.split(_text(dates), maxsplit=1)
    if len(parts) != 2:
        return None
    start, end_text = _month(parts[0]), parts[1]
    current = not re.search(r"(?:19|20)\d{2}", end_text)
    end = _month(today) if current else _month(end_text)
    return (start, end, current) if start and end else None


def plain_clash(where) -> str:
    """told.clash's reason as the person reads it: the command that records a place is
    Claude's, never printed in their document."""
    return re.split(r",\s*(?:or|then)\s+record\b", _text(where), maxsplit=1)[0]


def _a_or_an(word) -> str:
    """"an" before a vowel sound, else "a": "what a analyst here does" went in a pack."""
    return "an" if re.match(r"[aeiou]", _text(word), re.I) else "a"


def _between(a, b) -> int:
    """Whole months from (year, month) a to b."""
    return (b[0] - a[0]) * 12 + b[1] - a[1]


def _level(title) -> int:
    return next((n for n, rx in _LEVELS if rx.search(_text(title))), 1)


def _why_answer(question, ctx):
    """The person's own stock answer to a why-did-you-move question, or None."""
    names = [ctx["company"]] + [_text(e.get("company")) for e in ctx["facts"].get("employers") or []
                                if isinstance(e, dict)]
    found = _answer_for(question, ctx.get("answers") or [], names, ctx["company"],
                        fits=lambda a: not against_employer(a, ctx))
    return None if found is None or against_employer(found, ctx) or found.get("fill_in") else found


def landmines(ctx) -> list:
    """[{what, ask, then, framing}] for each place on the resume an interviewer is likely to
    push: a stay under SHORT_TENURE_MONTHS, a gap over GAP_MONTHS, a title the role may doubt.
    `ask` is the likely question, `then` the follow-up behind it, `framing` the honest lines to
    answer from: the person's own stock answer, what the profile holds, or a line saying their
    reasons are asked, never drafted."""
    facts, prof = ctx["facts"], prep._profile_source(ctx["facts"])
    jobs = [e for e in facts.get("employers") or [] if isinstance(e, dict) and _text(e.get("company"))]
    out = []

    def why(question):
        found = _why_answer(question, ctx)
        if found:
            # The same check as the answer under Your answers: printed here unmarked, a stock
            # answer naming the place this employer did not hear was the thing to say, and
            # printed under a warning it still was (2026-11-03): it is left out.
            where = places_told.clash(found["answer"], ctx["company"])
            if where:
                return ["Your stock answer to this is left out for %s: %s." % (ctx["company"],
                                                                              plain_clash(where))]
            return ["Prepared: %s (source: %s)" % (found["answer"], found["source"])]
        # The command that keeps their answer is Claude's (interview.md Step 3), never printed
        # where the person reads (2026-11-03).
        return ["Nothing on file says why, and only you can: Claude asks you once, in your words, "
                "and keeps the answer for every later employer. Never drafted from the dates."]

    spans = [(e, _span(e.get("dates"), ctx["today"])) for e in jobs]
    for e, span in spans:
        if not span:
            continue
        start, end, current = span
        # Whether it was short counts both end months (Sep to Aug is a year there); what is
        # said counts the months between, as a person says it: "Mar 2024 - Sep 2024" is six
        # months, which the profile says, and it was asked as "after 7 months" (2026-11-03).
        if _between(start, end) + (0 if current else 1) >= SHORT_TENURE_MONTHS:
            continue
        months = max(1, _between(start, end))
        name, title = _text(e["company"]), _text(e.get("title"))
        if current:
            ask = "Why are you looking to leave %s after %d months?" % (name, months)
            then = "How do we know you would stay longer with us?"
        else:
            ask = "Why did you leave %s after %d months?" % (name, months)
            then = "Would you leave us as quickly?"
        framing = why(ask)
        if _FIXED_TERM.search(title):
            framing.insert(0, "Your title there was %s: if the post had a set length (a graduate "
                              "scheme, a contract), say that first, in a sentence (source: %s)"
                           % (title, prof))
        out.append({"what": "A short stay: %s, %s (%s)" % (title or "a role", name,
                                                          _text(e.get("dates"))),
                    "ask": ask, "then": then, "framing": framing})
    # Newest first in the profile: each gap sits between a role and the one before it.
    for (newer, a), (older, b) in zip(spans, spans[1:]):
        if not (a and b):
            continue
        gap = _between(b[1], a[0]) - 1
        if gap > GAP_MONTHS:
            ask = "What were you doing between %s and %s?" % (_text(older["company"]),
                                                              _text(newer["company"]))
            out.append({"what": "%d months between jobs: %s ended %s, %s started %s" % (
                            gap, _text(older["company"]), "%s %d" % (
                                _MONTH_NAMES[b[1][1] - 1].capitalize(), b[1][0]),
                            _text(newer["company"]), "%s %d" % (
                                _MONTH_NAMES[a[0][1] - 1].capitalize(), a[0][0])),
                        "ask": ask, "then": "What did you keep up or learn in that time?",
                        "framing": ["Say what you did, plainly and briefly, then move to what it "
                                    "brought you to; the reasons are yours to give, never "
                                    "drafted (source: %s)" % prof]})
    if spans and spans[0][1] and not spans[0][1][2]:
        last_end = spans[0][1][1]
        idle = _between(last_end, _month(ctx["today"]) or last_end)
        if idle > GAP_MONTHS:
            out.append({"what": "%d months since %s ended" % (idle, _text(spans[0][0]["company"])),
                        "ask": "What have you been doing since %s?" % _text(spans[0][0]["company"]),
                        "then": "Why now?",
                        "framing": ["Say what you did, plainly and briefly; the reasons are yours "
                                    "to give, never drafted (source: %s)" % prof]})
    # The title the interviewer reads first is the latest one.
    latest = _text(jobs[0].get("title")) if jobs else ""
    role = _text(ctx["role"])
    if latest and role:
        mine, theirs = _level(latest), _level(role)
        led = [x for x in facts.get("strengths") or [] if re.search(
            r"\b(?:mentor|first|introduc|standard|train|onboard|set up|owned|led|lead)\w*",
            _text(x), re.I)]
        if theirs >= 2 and mine < theirs:
            out.append({"what": "The role is %s; your latest title is %s" % (role, latest),
                        "ask": "This is a more senior role than your current one. What have you "
                               "done at that level?",
                        "then": "What did you decide yourself, and who did you bring with you?",
                        "framing": ["From your profile: %s (source: %s)" % (prep.clip(x, 170), prof)
                                    for x in led[:2]]
                        + ["Say what you did at that level, by what you owned and decided; never "
                           "a title you did not hold."]})
        elif theirs == 0 and mine >= 2:
            ask = "Your title is %s and this role is %s. Why step back?" % (latest, role)
            out.append({"what": "The role is %s; your latest title is %s" % (role, latest),
                        "ask": ask, "then": "Would you leave for the next senior role?",
                        "framing": why(ask)})
        f_mine, f_theirs = _FUNCTION.search(latest), _FUNCTION.search(role)
        if f_mine and f_theirs and f_mine.group(1).lower() != f_theirs.group(1).lower():
            near = sorted(((similar(" ".join([role, ctx.get("posting", "")[:2000]]), x), x)
                           for x in facts.get("strengths") or [] if _text(x)), key=lambda t: -t[0])
            framing = ["From your profile: %s (source: %s)" % (prep.clip(x, 170), prof)
                       for score, x in near[:2] if score > 0]
            framing += ["Say: %s (source: profile skills.py BRIDGES)" % b.line
                        for b in bridges.assess(role) if b.verdict == bridges.BRIDGE and b.line][:1]
            framing.append("Name the work that is the same job, in their words; never the title "
                           "you did not hold.")
            out.append({"what": "Your title says %s; this role is %s" % (
                            f_mine.group(1).lower(), f_theirs.group(1).lower()),
                        "ask": "Your title is %s. What in your work is what %s %s here does?"
                               % (latest, _a_or_an(f_theirs.group(1)), f_theirs.group(1).lower()),
                        "then": "What would you need to learn first?",
                        "framing": framing})
    return out


def landmine_lines(ctx) -> list:
    """The landmines as the pack prints them, under What the paper says."""
    found = landmines(ctx)
    if not found:
        return []
    out = ["- Where they will push, from the %s they hold (each with the follow-up behind it):"
           % _noun()]
    for m in found:
        out.append("  - %s. They ask: \"%s\" Then: \"%s\"" % (m["what"], m["ask"], m["then"]))
        out += ["    - %s" % ln for ln in m["framing"]]
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
    out += ["- The fit score marked it down: %s (source: %s)" % (w, src)
            for w in docked[:MAX_GAP_NOTES]]
    out += ["- The check on your application said an interviewer could probe: %s (source: %s)"
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


_MONEY = re.compile(r"(\d{2,3}(?:,\d{3})+|\d{2,3})\s*(k\b|thousand\b)?", re.I)


def _figures(text) -> list:
    """Every pay figure in `text`, in whole units: "70 to 80 thousand" is 70,000 and
    80,000 (a bare number takes the unit of the next one that has one)."""
    found = [(m.group(1), (m.group(2) or "").lower()) for m in _MONEY.finditer(str(text or ""))]
    out, unit = [], ""
    for raw, u in reversed(found):
        unit = u or unit
        n = int(raw.replace(",", ""))
        out.append(n * 1000 if n < 1000 and unit else n)
    return sorted(x for x in out if x >= 1000)


def pay_differs(answer, ctx) -> str:
    """Why a stock answer's pay figures differ from the band this pack gives, or ""."""
    said = _figures(answer)
    if not said:
        return ""
    _q, form = _form_value(ctx, _PAY_Q) if "form" in ctx else ("", "")
    target, _floor = _band()
    band = form or target
    want = _figures(band)
    if not want or set(said) <= set(want):
        return ""
    return "it says %s, and the band to say is %s" % (
        " to ".join("{:,}".format(x) for x in (said[0], said[-1]) if x) if len(said) > 1
        else "{:,}".format(said[0]), band)


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
                lines.append("  - Check: your profile also says \"%s\". The band above is the "
                             "one the form answers use: settle which is right with Claude "
                             "before the call." % f["said"])
    else:
        lines.append("- Your band: %s, as your profile has no pay targets yet. Ask their range "
                     "rather than quote a number you cannot stand behind." % prep.NOT_RESEARCHED)
    market = prep._comp_sources(ctx["research"], ctx["row"])
    if market:
        lines.append("- Market band:")
        lines += ["  " + ln for ln in prep.comp_band(ctx["role"], "", "", market)]
    else:
        # Nothing looked up: said in a line, never as an empty band with how it was not made.
        lines.append("- Market pay for the role: %s. Ask their range rather than quote a number "
                     "you cannot stand behind." % prep.NOT_RESEARCHED)
    sheet = _screening()
    try:
        sponsor = "needed" if sheet.requires_sponsorship() else "not needed"
        lines.append("- Sponsorship: %s. Say it plainly, with no caveat. (source: %s)"
                     % (sponsor, prep.PROFILE_SOURCE))
    except (AttributeError, getattr(sheet, "MissingFact", LookupError)):
        # Never guessed, and never silently left out either.
        lines.append("- Sponsorship: your profile does not say whether you need it, so nothing "
                     "is printed here. Tell Claude which is true.")
    if ctx["step"] == "offer":
        lines += _offer_lines()
    _q, said = _form_value(ctx, _PAY_Q)
    # What to say, first: the line is read in the minutes before the call, and "nothing on
    # the form; your target is ..." made the person work out what that meant (2026-11-03).
    if ctx["step"] == "offer":
        one = "weigh the whole package, not the base pay%s, and keep your lowest figure to " \
              "yourself" % (", against your target %s" % target if target else "")
    elif said:
        one = "say what the form said, %s%s: a recruiter checks what you say against it" % (
            said, " (your target is %s)" % target if target and target not in said else "")
    elif target:
        one = "say %s, as a range, and keep your lowest figure to yourself" % target
    else:
        one = "ask their range first: your own band is %s" % prep.NOT_RESEARCHED
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


# What a recruiter screen is for, from the candidate's side: the process. Its interviewer
# owns the timeline and the format, and seldom the work.
PROCESS_QUESTIONS = (
    "What are the stages from here, and roughly how long does it take?",
    "What does the next round involve: a case, a technical interview, a take-home?",
)
TRAVEL_QUESTION = "How much travel does the role involve, and where?"
# The last question at every stage, worded the same here, in interview.md and in the app
# guide's tips: it gives them the last word on any doubt while the person is still there.
CLOSE_QUESTION = "Is there anything about my background you'd like me to go into more?"
# Notes that say one employer has more than one posting for the role.
_SIBLING_WORDS = re.compile(r"\b(?:two|both|2|several|multiple|another|second) (?:live )?"
                            r"(?:postings?|roles|openings?|reqs?|requisitions?|positions?|"
                            r"listings?|ads?)\b|\bwhich (?:team|posting|req|requisition)\b", re.I)


def _same_employer(a, b) -> bool:
    """Is employer key `b` this employer or an arm of it ("<employer> Labs")? By the first
    two words that are not filler, or the one word of a one-word name."""
    wa = [w for w in a.split() if w not in ("the", "of", "and")]
    wb = [w for w in b.split() if w not in ("the", "of", "and")]
    n = min(2, len(wa), len(wb))
    return bool(n) and wa[:n] == wb[:n]


def _seen_postings(ctx) -> list:
    """[(what, source)]: the postings in the jobs the search has seen that are for this
    role at this employer or an arm of it, one for each posting and not this call's own.

    One posting is one employer name in one place: the same role listed on two boards is
    one posting, not two, and a posting whose deadline has passed (/rank marks it expired)
    is no longer one. The call's own posting is the one the tracker row links to; where the
    row holds no link (a process with a recruiter and no application), it is the only
    posting under the employer's own name. Where the employer has several of those in
    different places and nothing says which this is, they are all listed, as the call is
    for one of them. A remote listing and a listing in a named place count as two: a
    listing does not say if it is a copy."""
    k = company_key(ctx["company"])
    try:
        seen = throttle.load_seen(person.state("job_scraper", "seen_jobs.json")).get("seen") or {}
    except (OSError, ValueError):
        seen = {}
    link = _text((ctx["row"] or {}).get("source"))
    mine = throttle.norm(link) if link.lower().startswith(("http://", "https://")) else ""
    postings, own = {}, None
    for url, e in seen.items():
        if not isinstance(e, dict) or _text(e.get("status")).lower() == "expired":
            continue
        employer = company_key(e.get("company"))
        if not _same_employer(k, employer) or not throttle._same_title(ctx["role"], e.get("title")):
            continue
        which = (employer, throttle.place(e.get("location")))
        place = _text(e.get("location"))
        postings.setdefault(which, "%s, %s%s" % (_text(e.get("title")), _text(e.get("company")),
                                                 " (%s)" % place if place else ""))
        if mine and throttle.norm(e.get("url") or url) == mine:
            own = which
    if own is None:
        theirs = [w for w in postings if w[0] == k]
        own = theirs[0] if len(theirs) == 1 else None
    return [(what, "job_scraper/seen_jobs.json") for w, what in postings.items() if w != own]


def sibling_postings(ctx) -> list:
    """[(what, source)]: the other postings for this role at this employer or an arm of it,
    from the jobs the search has seen, and what the contact notes and the tracker say. A
    pack for an employer with two live postings for one title (its main team and its Labs
    arm) never asked which the call was for.

    "Other" is the point: one posting for the role is no question, however many boards list
    it, and a single other posting is enough to ask, because the role the call is for is
    itself one, seen in the search or not."""
    found = _seen_postings(ctx)
    notes = [(_text(c.get(f)), prep.CONTACTS_SOURCE) for c in _here(ctx).values()
             for f in ("next_action", "notes", "outcome")]
    notes += [(_text(ctx["row"].get("notes")), prep.TRACKER_SOURCE),
              (_text(ctx.get("outcome")), "%s/outcome.md" % _rel(ctx["folder"]))]
    for text, src in notes:
        m = _SIBLING_WORDS.search(text)
        if m:
            start = max(0, text.rfind(".", 0, m.start()) + 1)
            found.append(("\"%s\"" % prep.clip(text[start:].strip(), 140), src))
            break
    return found


def ask_lines(ctx) -> list:
    """The questions to ask them. Which team the call is for comes first when there is more
    than one posting for the role; a screen asks about the process (its stages, the next
    round's format, travel where the work travels); then what the research anchors."""
    cap = MAX_ASK_SCREEN if ctx["step"] == "screen" else MAX_ASK
    first, out = [], []
    siblings = sibling_postings(ctx)
    if siblings:
        # The other postings, never this call's own, so the line is only asked where there is
        # one; past the third, how many more there are.
        more = len(siblings) - 3
        first.append("- Which team is this %s for? There is more than one posting for it; "
                     "besides this one: %s%s."
                     % (ctx["stage"].lower() if ctx["stage"] else "call",
                        "; ".join("%s (source: %s)" % (w, s) for w, s in siblings[:3]),
                        " (and %d more)" % more if more > 0 else ""))
    if ctx["step"] == "screen":
        out += ["- %s (a screen is where the process is asked about)" % q
                for q in PROCESS_QUESTIONS]
        if employer_type(ctx) == "consulting":
            out.append("- %s (a consulting firm's work usually travels)" % TRAVEL_QUESTION)
    # prep.py anchors its last question on the role and names the contact book,
    # where a call's role comes from; here it is the tracker's.
    out += ["- %s (source: %s)" % (q["question"], prep.TRACKER_SOURCE
                                   if q["anchor"] == ctx["role"] else q["source"])
            for q in prep.questions_for_them(ctx["research"], ctx["role"])]
    cats = _guide_categories()
    for cat in STEP_CATEGORIES.get(ctx["step"], ()):
        for q in [q for q in cats.get(cat, []) if "[" not in q][:2]:
            if len(out) >= cap:
                break
            out.append("- %s (a common one about %s: skip it if their own pages answer it)"
                       % (q, re.sub(r"^About ", "", cat).replace("&", "and").lower()))
    return first + out[:cap]


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
    if _said_referral(_text(c.get("outcome"))):
        return True
    # Named in another contact's `referred_by` at this employer: the recruiter's row said who
    # routed the resume, and the referrer, whose own row was waiting on a reply, was left out.
    cid = _text(c.get("contact_id"))
    for other in (ctx.get("contacts") or ()):
        by = _text(other.get("referred_by"))
        if other is not c and by and company_key(other.get("company")) == company_key(
                ctx["company"]) and (by == cid or (len(name) > 3 and by.lower() == name.lower())):
            return True
    linked = _text(c.get("linked_application"))
    if linked and linked == _text(ctx["row"].get("cv_file")):
        return True
    if len(name) > 3:
        text = " ".join([_text(ctx["row"].get("notes")), _text(ctx.get("outcome"))]).lower()
        for m in re.finditer(re.escape(name.lower()), text):
            if _said_referral(text[max(0, m.start() - 80):m.end() + 80]):
                return True
    return False


# "declined: no referral, hiring freeze" is the opposite of a referral, and a pack that read
# it as one told the candidate to thank someone who had said no.
_NO_REFERRAL = re.compile(r"\b(?:no|not|never|declin\w*|refus\w*|couldn'?t|can'?t|won'?t|unable|"
                          r"without)\b[^.;]{0,30}\breferr|\breferr\w*[^.;]{0,25}\b(?:declin\w*|"
                          r"refus\w*|fell through|not possible|withdrawn)\b", re.I)


def _said_referral(text) -> bool:
    """Does `text` say a referral happened (and not that it was declined)?"""
    return "referr" in text.lower() and not _NO_REFERRAL.search(text)


def warm_lines(ctx) -> list:
    """Who is already talking to them, and who of the interviewers is already known.
    A row that says to leave someone be is shown with its own words, never with a
    message to send: one said "Keep warm, no action" and the pack told the candidate to
    tell him the interview was booked."""
    here = list(_here(ctx).values())
    names = " ".join(_text(x).lower() for x in [ctx["with"]] + [s["with"] for s in ctx["stages"]])
    out, referrer = [], None
    # "Booked" only when the stage this pack is for has a date: told to say a round was
    # booked that had no date yet, the candidate would be telling them something untrue.
    booked = bool(_text(ctx.get("date")))
    lead = _lead_id(ctx)
    for c in here:
        cid = _text(c.get("contact_id"))
        status = _status_for(c, ctx)
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        title = ", " + _text(c.get("title")) if _text(c.get("title")) else ""
        step = _text(c.get("next_action"))
        if _referred(c, ctx, name):
            referrer = referrer or name
        stale_wait = status in ("replied_needs_response", "in_conversation") and re.search(
            r"\b(?:wait|waiting|await|awaiting)\b", step, re.I) and not re.search(
            r"\b(?:HOLD|FREEZE|no action|do not|don'?t)\b", step, re.I)
        if step and _HANDS_OFF.search(step) and not stale_wait:
            out.append("- %s%s (%s): your notes say to leave them be for now: \"%s\". "
                       "(source: %s)" % (name, title, status_words(status), prep.clip(step, ROW_QUOTE),
                                         prep.CONTACTS_SOURCE))
            continue
        if len(name) > 3 and name.lower() in names:
            known = [f for f in ("prep.md", "reading.json")
                     if cid and os.path.exists(person.state("documents", "network", cid, f))]
            out.append("- %s%s is interviewing you and is in your contacts (%s)%s. "
                       "(source: %s)" % (name, title, status_words(status),
                                         ": what you noted about them is under Who you are meeting"
                                         if known else "", prep.CONTACTS_SOURCE))
        elif _referred(c, ctx, name):
            then = (" Their row's next step: \"%s\"." % prep.clip(step, ROW_QUOTE)) if step else ""
            # The networking skill's rule for a referrer: thanks once, nothing asked of them,
            # and then no update until there is an outcome, unless they ask.
            stage = _text(ctx.get("stage")) or "interview"
            word = stage[:1].lower() + stage[1:]
            led = "%s %s%s" % ("an" if word[:1] in "aeiou" else "a", word,
                               " on %s" % ctx["date"] if booked else "")
            out.append("- %s%s put you forward. If you have not thanked them yet, once: "
                       "thanks, that it led to %s, and that nothing is needed from them. Then "
                       "no update until there is an outcome, unless they ask.%s (source: %s)"
                       % (name, title, led, then, prep.CONTACTS_SOURCE))
        elif status == "call_booked" or (cid and cid == lead and prep.is_recruiter(c)
                                         and status in throttle.RESPONDED):
            # Whoever booked the stage already knows it is booked.
            out.append("- %s%s booked this: nothing is owed to them before the call. "
                       "(source: %s)" % (name, title, prep.CONTACTS_SOURCE))
        elif status in throttle.RESPONDED:
            out.append("- %s%s is already talking to you (%s): %s (source: %s)"
                       % (name, title, status_words(status), "tell them it is booked." if booked
                          else "tell them once it has a date.", prep.CONTACTS_SOURCE))
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
    """One optional value from person.json, "" when the profile does not hold it. A value
    still marked `[CONFIRM: ...]` is not held: it is a question waiting for the person, and a
    pack read the neighbourhood's marker out as "You live in [CONFIRM: Which neighbourhood..."."""
    try:
        value = _text(_PERSON[dotted]())
    except person.NoProfile:
        return ""
    return "" if "[CONFIRM" in value else value


def _lead_id(ctx) -> str:
    """The contact_id of whoever leads this process (the tracker row's `contact:<id>`), or
    "" for an application."""
    src = _text((ctx.get("row") or {}).get("source"))
    return src.split(":", 1)[1].strip() if src.startswith("contact:") else ""


def _lead_interviewer(ctx, contacts, stage) -> str:
    """Who a recruiter screen is with when nobody was named: the recruiter who leads the
    process or booked the call, as "<name>, <title>", or "". A process registered with its
    recruiter as the lead still said "Nobody named for this stage yet"."""
    if what_works.stage_step(stage) != "screen" or not is_process(ctx["row"]):
        return ""
    k, lead = company_key(ctx["company"]), _lead_id(ctx)
    here = [c for c in contacts if company_key(c.get("company")) == k]
    pick = [c for c in here if _text(c.get("contact_id")) == lead] + \
        [c for c in here if _text(c.get("status")) == "call_booked"]
    c = next((c for c in pick if prep.is_recruiter(c)), None)
    if c is None:
        return ""
    name = state.person_name(c.get("name")) or _text(c.get("name"))
    return ", ".join(x for x in (name, _text(c.get("title"))) if x)


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
    clauses = re.split(r"[.;,]", _text(ctx["facts"].get("work_authorization")))
    return any(_TEMPORARY.search(c) for c in clauses if not re.search(r"\bsponsor", c, re.I))


MOVED_MONTHS = 12


# identity.moved: when they moved (YYYY-MM or YYYY-MM-DD), or "by YYYY-MM-DD" where the
# profile only confirms they were there by a date ("in <city>, confirmed 2026-09-16"). The
# upgrade that writes it had only the exact forms, wrote a CONFIRM marker for a profile that
# held a confirmed-by date, and the small talk for a call the next day was left out.
_MOVED = re.compile(r"(by\s+)?(\d{4}-\d{2}(?:-\d{2})?)", re.I)
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
FEW_WEEKS = 56          # days: "for a few weeks" up to here, "since <month>" beyond


# Someone whose own answer to "how long have you been here?" is "I've just arrived", with no
# date or month, ever (their rule, kept in learned.json, or identity.moved itself).
JUST_ARRIVED = "just arrived"
_JUST_RULE = re.compile(r"\bjust arrived\b", re.I)


def _just_arrived_rule() -> bool:
    """Has the person said to say only that they have just arrived?"""
    if _person("identity.moved").lower() == JUST_ARRIVED:
        return True
    try:
        return any(_JUST_RULE.search(" ".join(_text(r.get(k)) for k in ("rule", "said")))
                   for r in learned.entries())
    except (OSError, ValueError, person.NoProfile):
        return False


def _moved_on() -> str:
    """identity.moved when it says when, or that they have just arrived, else "": the
    move-and-area upgrade writes "none" for everyone who has not moved recently. Where the
    person's own rule is to say only that they have just arrived, that is what this says."""
    moved = _person("identity.moved")
    if moved.lower() == JUST_ARRIVED:
        return JUST_ARRIVED
    if not _MOVED.fullmatch(moved):
        return ""
    return JUST_ARRIVED if _just_arrived_rule() else moved


def _since(moved, today) -> str:
    """How long they have lived there, said as a person would: "for a few weeks" or "since
    May 2026", from identity.moved; "" when it says no date."""
    m = _MOVED.fullmatch(_text(moved))
    if not m:
        return ""
    when = state.as_date(m.group(2) + ("-01" if len(m.group(2)) == 7 else ""))
    if when is None:
        return ""
    if (today - when).days <= FEW_WEEKS:
        return "for a few weeks"
    return "since %s %d" % (_MONTHS[when.month - 1], when.year)


def newcomer(ctx) -> str:
    """How long the person has lived where they live ("for a few weeks", "since May 2026"),
    when they moved within MOVED_MONTHS (person.json identity.moved), else "". A
    confirmed-by date counts: they had moved by then. JUST_ARRIVED where that is all they
    say: no date and no month is printed for them, anywhere. An employer told another place
    (tools/told.py) hears nothing about a move it was never told of."""
    if places_told.differs(ctx.get("company", "")):
        return ""
    if _person("identity.moved").lower() == JUST_ARRIVED:
        return JUST_ARRIVED
    moved = _person("identity.moved")
    m = _MOVED.fullmatch(moved)
    when = state.as_date(m.group(2) + ("-01" if len(m.group(2)) == 7 else "")) if m else None
    today = state.as_date(ctx["today"]) or dt.date.today()
    if when is None or (today - when).days > MOVED_MONTHS * 31 or when > today:
        return ""
    return JUST_ARRIVED if _just_arrived_rule() else _since(moved, today)


def home_place(company="") -> str:
    """Where this employer heard the person is (tools/told.py), else where they live, as
    their profile says it. Kept per employer, "per employer" is no place for anyone."""
    heard = places_told.place(company) if company else ""
    if heard:
        return heard
    return next((v for v in (_person("identity.area"), _person("identity.location"))
                 if v and v.lower() != places_told.PER_EMPLOYER), "")


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
    ("product", re.compile(r"\b(?:saas|software|platform|product company|tech company|technology|"
                           r"marketplace|app)\b", re.I)),
)


def employer_type(ctx) -> str:
    """The kind of employer, from the most direct source that names one: the tracker's
    sector, then the research's own sector words, then what the person's own catalogue
    calls it (employers.py, read by tools/sector.py), then the name, then what the research
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
    # The catalogue: a consulting firm with no sector on its row and no research (its name
    # says "consulting" nowhere) was no kind at all, and its pack offered the answer the
    # person marked "Not for: consulting".
    try:
        import sector
        listed = sector.kind(ctx["company"])
    except (ImportError, person.NoProfile, AttributeError):
        listed = ""
    sources = (ctx["row"].get("sector"),
               " ".join(_text(research.get(k)) for k in ("sector", "industry", "type")),
               listed,
               ctx["company"],
               " ".join(_text(research.get(k)) for k in ("summary", "what_they_do")))
    for i, text in enumerate(sources):
        # In a summary, what the employer makes comes first: "software used by banks and
        # consulting firms" is a software company, whoever its customers are.
        types = EMPLOYER_TYPES if i < len(sources) - 1 else sorted(
            EMPLOYER_TYPES, key=lambda t: t[0] != "product")
        found = next((t for t, rx in types if rx.search(_text(text))), "")
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


def against_employer(prepared, ctx) -> str:
    """Why a stock answer would work against this employer, or "": its `Not for:` line names
    this kind of employer, its `Suits:` line names only others, or (untagged) its own words
    argue against it."""
    etype = employer_type(ctx)
    if not etype:
        return ""
    suits, not_for = prepared.get("suits") or (), prepared.get("not_for") or ()
    if etype in not_for:
        return "its Not for: line names %s employers, and %s is one" % (etype, ctx["company"])
    if suits:
        # Tagged for this kind of employer, the person has said it fits: their word stands.
        return "" if etype in suits else (
            "it was written for %s employers (its Suits: line), and %s is a %s employer"
            % (", ".join(suits), ctx["company"], etype))
    against = argues_against(prepared["answer"], etype)
    return ("it argues against a %s employer (\"%s\"), and %s is one" % (etype, against,
                                                                         ctx["company"])
            if against else "")


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
    ("pay", re.compile(r"(?:\b(?:salary|compensation|base pay|pay of|package|"
                       r"looking for around|expecting)\b|[$£€]\s?\d+(?:[.,]\d+)?\s?k\b|"
                       r"[$£€]\s?\d{2,3},\d{3}\b(?![^.]{0,40}\b(?:saved|released|revenue|sales|"
                       r"stock|costs?|budget|worth|turnover|profit|spend|savings)\b))", re.I)),
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
        lo, hi = pc._range_of(m)
        # A narrower band inside the target is the same answer; only one reaching outside it
        # is a number a recruiter would hold against the one on the form.
        if lo < low or hi > high:
            return True
    rest = pc._RANGE.sub(" ", sent)
    return any(not low <= pc._amount(m.group(1)) <= high
               for m in pc._SINGLE.finditer(rest) if pc._amount(m.group(1)) >= 1000)


def _here(ctx) -> dict:
    """{contact_id: row} for everyone in the contact book at this employer, by company_key,
    the one join every section uses."""
    k = company_key(ctx["company"])
    return {_text(c.get("contact_id")): c for c in ctx["contacts"]
            if k and company_key(c.get("company")) == k and _text(c.get("contact_id"))}


# What only the person can know, written on the row, and which the message log cannot
# derive: a call booked, a referral in flight. On the row it wins (CLAUDE.md, Networking):
# a recruiter whose last message booked the screen read as owed a reply, and the pack told
# the candidate to "tell them it is booked", to the one person who booked it.
STORED_WINS = frozenset({"call_booked", "referral_in_progress"})


# A contact's state as the person says it: "[replied_needs_response]" was printed as it is.
_STATUS_WORDS = {
    "not_contacted": "not written to yet", "awaiting_reply": "waiting for their reply",
    "connected_no_reply": "connected, no reply yet", "replied_needs_response": "replied, your turn",
    "in_conversation": "talking", "call_booked": "call booked",
    "referral_in_progress": "putting you forward", "referral_agreed": "agreed to put you forward",
    "converted_to_application": "now an application", "gone_cold": "gone quiet",
    "cold": "gone quiet", "closed": "closed", "dropped": "set aside", "stopped": "stopped",
}


def status_words(status) -> str:
    s = _text(status)
    return _STATUS_WORDS.get(s, s.replace("_", " "))


def _status_for(c, ctx) -> str:
    stored = _text(c.get("status"))
    if stored in STORED_WINS:
        return stored
    return state.effective_status(c, state.threads_for(ctx["threads"],
                                                       _text(c.get("contact_id"))))


def told_lines(ctx) -> list:
    """Every message to anyone at this employer, and what the form said, on the topics a
    screen checks first, each with a line where it disagrees with the profile now.

    What was read is said first, contact by contact, so an empty section is never silent:
    a message logged with a summary and no text (one said "moving to <city>" weeks after
    the move) is flagged, never passed over, and a contact with nothing logged is named."""
    here = _here(ctx)
    out, seen = [], set()
    heard = places_told.place(ctx["company"])
    # What this employer was told on purpose is the line to keep, not the profile's own.
    moved = "" if heard else _moved_on()
    if heard:
        out.append("- You told %s you are in %s (source: your profile): every answer and "
                   "message to them says the same." % (ctx["company"], heard))
    current = [n for e in ctx["facts"].get("employers") or [] if isinstance(e, dict)
               and "present" in _text(e.get("dates")).lower()
               for n in (_text(e.get("company")),) if n]
    sent_to = {cid: [] for cid in here}
    for r in ctx["threads"]:
        cid = _text(r.get("contact_id"))
        if cid in here and state._direction(r) == "out":
            sent_to[cid].append(r)
    for cid, c in here.items():
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        title = ", " + _text(c.get("title")) if _text(c.get("title")) else ""
        dates = sorted(_text(r.get("date")) or "undated" for r in sent_to[cid])
        out.append("- %s%s (%s): %s (source: %s)" % (
            name, title, status_words(_status_for(c, ctx)),
            "%s from you, %s" % ("one message" if len(dates) == 1 else "%d messages" % len(dates),
                                 ", ".join(dates)) if dates
            else "nothing from you on record", prep.THREADS_SOURCE))
    rows = sorted((r for rs in sent_to.values() for r in rs), key=lambda r: _text(r.get("date")))
    for r in rows:
        cid = _text(r.get("contact_id"))
        name = state.person_name(here[cid].get("name")) or _text(here[cid].get("name"))
        if not _text(r.get("full_text")):
            if state.is_bare_request(r):
                continue        # a connection request with no note said nothing
            # The command that keeps its words is Claude's (interview.md Step 3); the person
            # is asked only what it said.
            out.append("- %s, to %s: its words are not on record%s. Tell Claude what it said "
                       "about where you are, notice and pay. (source: %s)" % (
                           _text(r.get("date")) or "undated", name,
                           " (noted as \"%s\")" % prep.clip(r.get("summary"), 80)
                           if _text(r.get("summary")) else "", prep.THREADS_SOURCE))
            continue
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
                # What to say is theirs: a sentence written here was on one person's list of
                # words never to use.
                out.append("  - DIFFERS: they were told you were moving; your profile says you "
                           "live there now (%s). If it comes up, say plainly where you live now, "
                           "in your own words." % moved)
            if topic == "current employer" and current and not any(
                    _text(n).split()[0].lower() in sent.lower() for n in current if _text(n)):
                out.append("  - CHECK: your profile's current employer is %s; say it the same "
                           "way they heard it, or explain the difference." % ", ".join(current))
            if topic == "pay" and _differs_from_band(sent):
                out.append("  - CHECK: your target band is %s; a number they heard that "
                           "differs is the one a recruiter remembers." % _band()[0])
    for q, a in ctx["form"]:
        for topic, _sent in _said(q + ". " + a):
            out.append("- The form, on %s: %s %s (source: %s/screening_answers.md)"
                       % (topic, q, a, _rel(ctx["folder"])))
            break
    if ctx["process"]:
        out.append("- No documents went through a portal: anything they hold (a %s sent by "
                   "email%s) %s. Check the city and number on it match what you will say."
                   % (_noun(), ", or passed on by %s" % referrer_of(ctx) if referrer_of(ctx)
                      else "", "is in the messages above" if any(_text(r.get("full_text"))
                                                                  for r in rows)
                      else "came outside the message log"))
    return out


# How each kind of interviewer tends to listen, by their title. A recruiter checks the
# basics and the story hangs together; a hiring manager, fit and motivation; a
# practitioner, depth; an executive, judgement.
ANGLES = (
    (prep._SCREENER,
     "the basics and that your story hangs together: location, start date, work "
     "authorization, pay, why this move"),
    (re.compile(r"\b(?:chief|vp|vice presidents?|directors?|heads?|partners?|principals?)\b",
                re.I),
     "judgement and why: what you would do in their first months, and why you"),
    (re.compile(r"\b(?:managers?|leads?)\b", re.I),
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
    for path in glob.glob(os.path.join(glob.escape(person.state("documents", "network")), "*",
                                         "reading.json")):
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
_NAME = re.compile(r"^[A-Z][\w'\-]+(?:\s+[A-Z]\.)?(?:\s+(?:(?:de|la|le|du|da|di|del|der|den|van|von|"
                   r"bin|al|el)\s+)*[A-Z][\w'\-]+){0,3}$")
# Words that make a capitalised pair a team or a field, never a person: "Data Science",
# "Supply Chain Analytics".
_DOMAIN = re.compile(r"\b(?:data|science|analytics|engineering|product|marketing|finance|"
                     r"operations|supply|chain|research|platform|design|sales|strategy|risk|"
                     r"pricing|technology|security|growth|insights|ml|ai|people|talent|hr|"
                     r"recruiting|recruitment|legal|commercial|digital|infrastructure|"
                     r"consulting|practice|team|panel|office|revenue|forecasting|planning|"
                     r"logistics|customer|payments|fraud|credit|treasury|actuarial|reporting|"
                     r"economics|quant\w*|bi)\b", re.I)
_HONORIFIC = re.compile(r"^(?:dr|mr|mrs|ms|mx|prof|professor|sir|dame)\.?\s+", re.I)


def _is_name(part) -> bool:
    bare = _HONORIFIC.sub("", part).strip()
    return bool(_NAME.match(bare)) and not _ROLE_FIRST.match(bare) and \
        not _ROLE_LAST.search(bare) and not _DOMAIN.search(bare)


def _interviewers(ctx) -> list:
    """[{name, title}] from who this stage is with: each name paired with the title written
    after it ("Dana Okafor, Head of Data", "Dana Okafor (Head of Data)", "Dana Okafor - Head
    of Data"), a title alone where no name is known. An "&" or "and" inside a title ("Data &
    Analytics Manager") stays in it; between two names it separates them."""
    out = []
    for part in re.split(r"\s*[,;]\s*", _text(ctx["with"])):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.+?)\s*(?:\((.+)\)|\s[-\u2013]\s(.+))$", part)
        if m and _is_name(m.group(1).strip()):
            out.append({"name": m.group(1).strip(), "title": (m.group(2) or m.group(3)).strip()})
            continue
        halves = [h.strip() for h in re.split(r"\s+(?:and|&)\s+", part)]
        if len(halves) > 1 and any(_is_name(h) for h in halves):
            out += [{"name": h, "title": ""} if _is_name(h) else {"name": "", "title": h}
                    for h in halves]
        elif _is_name(part):
            out.append({"name": part, "title": ""})
        elif out and out[-1]["name"] and not out[-1]["title"]:
            out[-1]["title"] = part
        else:
            out.append({"name": "", "title": part})
    return out


def _reading_of(ctx, name):
    """(contact_id, reading or None, contact row or None) for one interviewer."""
    import reading as _reading
    name = _HONORIFIC.sub("", name).strip()
    row = state.already_contacted(ctx["contacts"], name=name, company=ctx["company"])
    cid, found = (_text(row.get("contact_id")), _reading.load(_text(row.get("contact_id")))) \
        if row else ("", None)
    if found is None:
        cid, found = _reading_for(name, ctx["company"])
    return cid, found, row


def _said_of(ctx, name) -> list:
    """What an earlier stage's notes say about this interviewer: "Tom pushed hard on how I
    validated the forecast" is the question they will come back to."""
    first = _HONORIFIC.sub("", name).split()[0] if name.split() else ""
    if len(first) < 3:
        return []
    rx = re.compile(r"\b%s\b" % re.escape(first), re.I)
    return ["  - Last time: %s. Expect them to come back to it; have that answer ready first "
            "(source: %s/outcome.md)." % (prep.clip(ln, 160).rstrip("."), _rel(ctx["folder"]))
            for _h, ln in _record(ctx["outcome"]) if rx.search(ln)][:2]


def meeting_lines(ctx) -> list:
    """Who the person will meet: what each tends to listen for and wants to hear, what the
    person shares with them, their recent public, professional work, and the stories to lead
    with. Only what tools/network/reading.py keeps: their headline, a short excerpt of their
    About, history shared with the candidate, and their own public work. Nothing personal,
    ever. Someone named only by title ("the recruiter", "Head of Data") still gets what their
    kind of interviewer listens for, and the question to ask them."""
    formats, _assumed = interview_formats(ctx)
    out = []
    if ctx.get("with_assumed"):
        out.append("- Assumed: %s leads this process, and a recruiter screen is with the "
                   "recruiter. If the invite names someone else, tell Claude who. (source: %s)"
                   % (ctx["with_assumed"], prep.CONTACTS_SOURCE))
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
            # How Claude keeps what it finds (reading.py add) is in interview.md Step 2, and
            # `pack` prints it: never in the person's document.
            out.append("  - %s %s's public, professional work (a talk, an article, code, "
                       "their team's own pages)." % (RESEARCH_MARK, name))
        if not found:
            out += tailored(ctx, name, title, " ".join([title, ctx["role"]]), {}, "", formats)
            out += _said_of(ctx, name)
            continue
        src = "documents/network/%s/reading.json" % cid
        out += _said_of(ctx, name)
        for _strength, kind, what, ev in _decent_hooks(found)[:3]:
            if kind == "about":
                continue
            out.append("  - %s%s (source: %s)" % (what[:1].upper() + what[1:],
                                                  ": \"%s\"" % prep.clip(ev, 120) if ev else "", src))
        topics = " ".join([_text(found.get("headline")), _text(found.get("about"))
                           if not prep.sensitive_topic(found.get("about")) else ""]
                          + [_text(i.get("text")) for i in _decent_items(found)])
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
    (r"why are you leaving|why are you looking|^why now\??$|why (?:did|would) you (?:leave|go)\b",
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
    (r"went wrong|mistake|\bfail",
     "self-awareness, and whether you learn",
     "your own part owned plainly, what you did next, what you do differently now"),
    (r"project|walk me through",
     "whether you did the work yourself and understand it",
     "the problem, what you did, and the result in numbers, in about a minute"),
    (r"why do you want to (?:work|join)|why (?:this|our) (?:company|firm|team)",
     "whether you chose them, or are applying everywhere",
     "something specific and true about them (the hooks), tied to what you want to do next"),
    # "Why data science?", "Why consulting?": the field, not the employer.
    (r"^why (?:this (?:role|field|work|area|career)|data|analytics|consulting|engineering|"
     r"product|finance|research|[a-z]+ (?:science|engineering|analytics))\b",
     "whether you chose this work on purpose",
     "what draws you to it, shown by something you have actually done"),
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
    (r"weakness",
     "self-awareness", "a real one, what you do about it, and evidence it is improving"),
    (r"five years|long ?term|after your permit",
     "whether you would stay and grow here",
     "a direction this employer can offer, and your plan to stay"),
    (r"reservations|concerns",
     "whether anything will stop you saying yes",
     "something honest and small, with what would settle it"),
    (r"^tell me about your experience with",
     "whether you can do this part of the job, as your papers say you can",
     "one specific time you did it, what you did yourself and the result"),
    (r"^what is your experience with|how much .+ have you done",
     "whether a gap is a problem",
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
    # (?!\w), not \b: a name ending in "." or ")" ("Northwind Co.") has no word boundary
    # after it, and "Why Northwind Co.?" was read as no question at all.
    if company and re.match(r"^why %s(?!\w)" % re.escape(_text(company)), q, re.I):
        q = "Why this company?"
    return next(((c, h) for rx, c, h in INTENT if rx.search(q)), ("", ""))


def _kind(title) -> str:
    return next(k for k, (rx, _a) in zip(KINDS, ANGLES) if rx.search(title or "x"))


# The question to ask, by who they are and what the round is. A recruiter is asked about
# the process, never about their own posts (a recruiter's posts are about hiring, and asking
# reads as having looked); a practitioner about how the team does the work the round tests.
# A recruiter's questions are the process ones (PROCESS_QUESTIONS, under Ask them): asked
# here as well, the next stage came up twice.
ASK_KIND = {
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
        return ["  - Ask them about the process: the questions under Ask them. Nothing about "
                "their own posts."]
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


_RANK_FIRST = re.compile(r"^(?:(?:head|director|vp|svp|evp|vice president|chief|lead|manager|"
                         r"senior|principal|staff|associate|junior)\s+(?:of\s+)?)+", re.I)
_ROLE_NOUN = re.compile(r"\s+(?:scientists?|engineers?|analysts?|managers?|leads?|directors?|"
                        r"partners?|consultants?|specialists?|architects?|developers?|officers?|"
                        r"heads?)$", re.I)


def _team_of(title) -> str:
    """The team in a title: "Head of Data" is Data, "Data Science Manager" is Data Science,
    "Associate Partner, Operations Practice" is Operations Practice. "" when it is all rank."""
    parts = [p.strip() for p in _text(title).split(",") if p.strip()]
    part = next((p for p in parts[1:] if _DOMAIN.search(p)), parts[0] if parts else "")
    team = _ROLE_NOUN.sub("", _RANK_FIRST.sub("", part)).strip(" &-")
    # Only a team that names a field: "Engagement" or "Partner" is rank, not a team.
    return team if _DOMAIN.search(team) and not re.fullmatch(r"(?:team|panel|office)", team, re.I) \
        else ""


def tailored(ctx, name, title, topics, found, src, formats=()) -> list:
    """What to do differently for this one interviewer, so they score you higher: which of
    your own strengths to put first (the ones nearest their work), the story to lead with,
    what their team works on (researched by Claude and kept in the research cache, never
    left to the person), and the question that fits who they are and what the round tests.
    Everything comes from the person's profile and the research: unasked, nothing is claimed
    that the profile does not hold, and a draft they ask for is marked for them to confirm
    (interview.md rule 2)."""
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
    team = _team_of(re.split(r"\s+(?:at|@|\|)\s+", _text(found.get("headline")) or _text(title),
                             maxsplit=1)[0])
    # Someone known only by a title ("two partners", "the hiring manager") has no team to
    # look up; a named interviewer's team is their title with the rank taken off.
    if team and name and kind != "screener" and team.lower() != _text(name).lower():
        state_, lines = _researched(ctx["research"], team)
        lines = [ln for ln in lines if not prep.sensitive_topic(ln)]
        if state_ == "found" and lines:
            out += ["  - Their team (%s): %s" % (prep.clip(team, 60), ln) for ln in lines[:2]]
        elif state_ == "none":
            out.append("  - Their team (%s): nothing public found about it; ask them what it "
                       "owns." % prep.clip(team, 60))
        else:
            # Where the employer-researcher keeps it (TEAMS_KEY, NOT_FOUND_KEY) is in its own
            # instructions: the person reads only what is still to look up.
            out.append("  - %s what \"%s\" works on at %s, from the employer's own pages."
                       % (RESEARCH_MARK, team, ctx["company"]))
    work = [i for i in _decent_items(found) if i.get("kind") in _PUBLIC_WORK]
    out += _ask_them(ctx, kind, formats, work, src)
    return out


def _decent_items(found) -> list:
    """A reading's items with nothing personal in them (prep.SENSITIVE): a post about their
    family, their health, their faith, their politics, their age or who they love is never
    something to lead with, ask about or bring up."""
    return [i for i in (found or {}).get("items") or []
            if not prep.sensitive_topic(i.get("text"), i.get("title"))]


def _decent_hooks(found) -> list:
    """reading.hooks, less every hook that touches a SENSITIVE topic."""
    import reading as _reading
    return [h for h in _reading.hooks(found or {}) if not prep.sensitive_topic(h[2], h[3])]


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
                   "Two or three questions for them on the process and the team (Ask them), "
                   "none the website answers.")},
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


# How long a round is and how it is held: what a recruiter says when booking one.
_SHAPE = re.compile(r"\b\d+\s*(?:minutes?|mins?|hours?)\b|\b(?:virtual|video call|in person|"
                    r"on[- ]?site|teams|zoom|google meet|by phone|phone call)\b", re.I)
# A technical round by its own words; what_works.stage_step calls anything unnamed technical.
_TECH_STAGE = re.compile(r"\b(?:technical|case|coding|take[- ]?home|pairing|second round|"
                         r"round (?:2|two))\b", re.I)


# A line of outcome.md that is advice or a guess rather than something said: "Recommendation:
# round 2 virtual", "Likely shape of the two rounds, from reported processes". A rebuilt pack
# listed both under "What you were told about this round". A line that says who said it
# ("the recruiter said it is sixty minutes") stays what they were told, whatever else it holds.
_ADVICE = re.compile(r"\b(?:recommend\w*|likely|probably|reportedly|reported|usually|typically|"
                     r"tends? to|should|suggest\w*|consider|assum\w*|my guess|i think)\b", re.I)
_SAID = re.compile(r"\b(?:said|says|told|mentioned|explained|confirmed|according to|wrote|"
                   r"emailed|invit\w*|booked)\b", re.I)


def _was_told(line) -> bool:
    """Is this line of the record something they were told, rather than advice or a guess?"""
    return bool(_SAID.search(line)) or not _ADVICE.search(line)


def _stage_named(text) -> str:
    """The step a line or heading names, or "" when it names none."""
    for step, rx in what_works._STEP_RX:
        if rx.search(text or ""):
            return step
    return "technical" if _TECH_STAGE.search(text or "") else ""


# Who said it, before what they said: "The recruiter said round 2 is 45 minutes" is about
# round 2, and read whole, "recruiter" filed it under the screen. Only a speaker of a few
# words is taken off: "The technical round is a case, the recruiter said" keeps its subject.
_SPEAKER = re.compile(r"^\W*(?:[\w'&.-]+[\s,]+){0,4}?(?:said|says|told (?:me|us|him|her|them)|"
                      r"mentioned|explained|confirmed|wrote|emailed)\b[:,]?\s*", re.I)


def _for_this_stage(ctx, heading, line) -> bool:
    """Is this line of outcome.md about the stage being prepared? The line's own words
    first (what was said, not who said it), then its heading's: by the stage's name, else by
    the step either names. A line under no stage at all is not this one's."""
    label = what_works._norm(ctx["stage"])
    for text in (_SPEAKER.sub("", line, count=1), heading):
        if label and label in what_works._norm(text):
            return True
        named = _stage_named(text)
        if named:
            return named == ctx["step"]
    return False


def format_lines(ctx) -> list:
    """The format: what it tests, how to prepare, what this employer says about how it runs
    it (researched by Claude), and how the process started."""
    formats, assumed = interview_formats(ctx)
    out = []
    if assumed:
        out.append("- Assumed %s: %s. Ask the recruiter what the round involves, and tell "
                   "Claude: the prep follows." % (" and ".join(f for f in formats), assumed))
    for f in formats:
        p = FORMAT_PREP[f]
        out.append("- **%s.** It tests %s. They want to hear %s." % (FORMAT_NAMES[f], p["tests"],
                                                                      p["hear"]))
        out += ["  - " + d for d in p["drills"]]
    state_, lines = _researched(ctx["research"], "interview_process")
    # What the recruiter or an earlier stage already said about this round (outcome.md) is
    # the best source there is, and needs no research. Only what was said about this round:
    # the technical round's pack quoted the screen's "virtual, 30 minutes" as its own.
    fmt = [rx for f, rx in FORMATS if f in formats and f != "screen"]
    told = [(h, ln) for h, ln in _record(ctx["outcome"])
            if _for_this_stage(ctx, h, ln) and _was_told(ln)
            and (any(rx.search(ln) for rx in fmt) or _SHAPE.search(ln))]
    out += ["- What you were told about this round: %s (source: %s/outcome.md)"
            % (prep.clip(ln, 200), _rel(ctx["folder"])) for _h, ln in told[:2]]
    if formats == ["screen"]:
        if state_ == "found":
            out += ["- What comes after the screen, as %s describes it: %s"
                    % (ctx["company"], ln) for ln in lines[:2]]
        elif employer_type(ctx) == "consulting":
            out.append("- After the screen, a consulting firm's rounds are usually a case and a "
                       "behavioural interview: start the case drills now, not when the invite "
                       "comes.")
    if formats and formats != ["screen"] and not told:
        if state_ == "found":
            out += ["- How %s says it runs this: %s" % (ctx["company"], ln) for ln in lines[:3]]
        elif state_ == "none":
            out.append("- %s publishes nothing on how it runs this; the drills above stand."
                       % ctx["company"])
        else:
            out.append("- %s how %s says it runs %s, from its own careers pages."
                       % (RESEARCH_MARK, ctx["company"],
                          " and ".join(FORMAT_NAMES[f].lower() for f in formats)))
    return out + route_lines(ctx)


def where_lines(ctx) -> list:
    """For someone who moved recently: their area, a briefing Claude researches, and what the
    question underneath it is. Unasked, never a memory of something they have not done: a
    follow-up question on an invented anecdote is the quickest way to lose the room. Asked
    for an anecdote, Claude drafts one, a place to go and a line to say, marked for them to
    make true before the call (interview.md rule 2)."""
    moved = newcomer(ctx)
    if not moved:
        return []
    place = home_place(ctx["company"])
    return [
        "- You moved recently: you live in %s, %s (source: profile/person.json). \"How "
        "are you finding it?\" is friendly, and underneath it they are checking you are settled "
        "and staying, so an honest line and one specific thing you like answers both. Claude "
        "researches a short briefing and writes it under %s, each line with its source: the "
        "neighbourhoods, getting around, food, the weather now, and your field's scene here, so "
        "you can follow any thread." % (place or "your area", "and have just arrived"
                                        if moved == JUST_ARRIVED else moved, FOUND_OUT[4:]),
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
        for _strength, kind, what, _ev in _decent_hooks(found or {}):
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
                "somewhere you have not; ask for an anecdote and Claude drafts one (a place to "
                "go, a line to say about it), marked for you to make true before the call."]
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
        out.append(("How are you finding %s?" % (home_place(ctx["company"]).split(",")[0]
                                                 or "it here"),
                    "you moved recently"))
    if employer_type(ctx) == "consulting":
        out.append(("Are you willing to travel?", "a consulting firm asks every time"))
    return out


def owned_sections(text) -> dict:
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


_owned = owned_sections  # the module's own name for it; other modules call owned_sections


def answer_blocks(lines) -> dict:
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


_answer_blocks = answer_blocks  # the module's own name for it; other modules call answer_blocks


def _found_out(text) -> list:
    """The lines written under Small talk's own heading, kept on every rebuild, whether or
    not the section still has anything else to say."""
    m = re.search(r"^" + re.escape(FOUND_OUT) + r"\s*$", str(text or ""), re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)     # the next section; a "#### Food" inside stays
    lines = [ln.rstrip() for ln in (body[:nxt.start()] if nxt else body).splitlines()
             if ln.strip() not in (FOUND_EMPTY, "- Nothing yet: each line you add here, with its "
                                   "source, stays.")]
    # Blank lines between their groups stay; only the edges are trimmed.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _own_words(body) -> list:
    """The lines of an answer block the person (or the session, for them) wrote, as they
    laid them out (a blank line between paragraphs stays): never the marker or the
    "- From:" lines this file generated, which a rebuild makes afresh."""
    out = [ln.rstrip() for ln in body or () if not any(m in ln for m in TO_WRITES)
           and not ln.lstrip().startswith(("- From:", "- careful:"))]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


# What in an answer block is a note to the person, never words they will say, and the mark
# of a draft they asked for: one definition, in prep.py beside `unsayable`, which the call
# prep's check reads too. A requested draft is listed under its own category (DRAFT) by
# both checks: shown, listed as one to confirm, never a rejection.
_NOTE_LINE = prep._NOTE_LINE
_ITALIC_LINE = prep._ITALIC_LINE
DRAFT_MARK = prep.DRAFT_MARK
DRAFT_TODO = prep.DRAFT_TODO
DRAFT = prep.DRAFT
drafted = prep.drafted


# One short line: the longer one said "Draft" on every pack, whether or not any answer was a
# draft (2026-11-03: "sometimes randomly says draft"). How a draft is marked is Claude's to
# know (interview.md rule 2), and a draft says so itself, once, above its own answer.
ANSWERS_INTRO = ("What you will say, under each question. A note to yourself goes under a line "
                 "\"Notes:\", and is kept.")
# What the line said before, still read as the tool's own in a document with no record of
# its last build, so a rebuild never keeps it as a line of the person's.
OLD_ANSWERS_INTRO = ("What you will say goes under each question, as sentences. Anything else (a "
                     "reminder, a list) goes under a line \"Notes:\", after \"Note:\", or in "
                     "italics: it is kept on every rebuild and never checked as something to say. "
                     "An answer drafted for you to confirm starts \"Draft:\"; delete that line "
                     "once it is true.")


def spoken(body) -> list:
    """The lines of an answer the person will say: their own words with every note out."""
    return prep.spoken_lines(_own_words(body))


def _restates(body, checking, hear) -> bool:
    """Does a note of theirs already say what a question is checking: the line this file
    writes under it, rewritten in their own formatting? Rebuilt, it was added again above."""
    made = "%s %s" % (checking, hear)
    for ln in body or ():
        if not (_NOTE_LINE.match(ln) or _ITALIC_LINE.match(ln)):
            continue
        plain = re.sub(r"[*_>]", " ", ln)
        if re.search(r"\bcheck\w*\b", plain, re.I) and re.search(r"\bhear\b", plain, re.I):
            return True
        if similar(plain, made) >= 0.5:
            return True
    return False


# How many of a question's notes an unwritten answer lists under Your answers; Likely
# questions carries the rest, never the same ones again.
ANSWER_NOTES = 3


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
        if checking and _restates(body, checking, hear):
            out.pop()                  # their own line already says it: never added twice
        if spoken(body):
            out += body
        else:
            # Notes kept, and still to write: the marker and what to say it from.
            out.append(TO_WRITE)
            out += ["- From: %s" % plain_sources(re.sub(r"^Say: ", "", ln))
                    for ln in a["lines"][:ANSWER_NOTES]]
            out += ([""] + body) if body else []
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
    as said (voice_check.spoken_findings), fit the time this stage gives an answer, and say
    "I" where the question asks what the person did (voice_check.answer_findings). Raw
    profile wording is never an answer.

    Three categories ride along in the first place: ("Research", what) and ("Ask",
    question), which hold the document until Claude has done them, and (DRAFT, question),
    a draft the person asked for, which is listed for them to confirm and never holds
    anything: it is what they asked for (`failures` leaves it out)."""
    text = _read(path)
    blocks = _answer_blocks(_owned(text).get("Your answers"))
    # A question answered under another heading (Notes, a section of their own) is checked
    # the same way and its draft listed: only Your answers was read, and nothing elsewhere
    # was checked or listed (2026-10-21). Empty ones there are headings, never "not written".
    elsewhere = {k: v for k, v in _question_blocks(text, skip=("Your answers",)).items()
                 if k not in blocks and " ".join(spoken(v[1])).strip()}
    # Research the document asks Claude for is part of being ready: the person never sees a
    # RESEARCH FIRST line, only what it found.
    out = [("Research", re.sub(r"^\s*-\s*", "", ln).split(". The employer-researcher")[0])
           for ln in text.splitlines() if research_line(ln)]
    company = _company_of(path)
    seconds = answer_seconds(text)
    for i, (q, body) in enumerate(blocks.values()):
        mine = spoken(body)
        where = places_told.clash(" ".join(mine), company) if company else ""
        if where:
            out.append((q, where))
        if not " ".join(mine).strip():
            # A motivation question waits on the person's own reasons, wherever it falls.
            if any(prep.asks_first(ln) for ln in body):
                out.append(("Ask", q))
            elif i < ONE_SCREEN_QUESTIONS:
                out.append((q, "not written yet"))
            continue
        out += [(q, why) for why in prep.unsayable(mine, q, seconds)]
        if drafted(body):
            out.append((DRAFT, q))
    for q, body in elsewhere.values():
        mine = spoken(body)
        # Read the same way as Your answers, the place they told this employer included.
        where = places_told.clash(" ".join(mine), company) if company else ""
        if where:
            out.append((q, where))
        out += [(q, why) for why in prep.unsayable(mine, q, seconds)]
        if drafted(body):
            out.append((DRAFT, q))
    # Every number said as the person's own is the profile's: "about four and a half years'
    # experience" went in a tell-me-about-yourself answer, against four in the profile and
    # in what the employer had already heard (2026-11-03). A draft they asked for is theirs
    # to confirm, and listed as one.
    said = [(q, body) for q, body in list(blocks.values()) + list(elsewhere.values())
            if not drafted(body) and " ".join(spoken(body)).strip()]
    out += _ungrounded_numbers(text, said)
    # A gap to fill anywhere in the document, under any heading: "[FILL IN: the hardest
    # moment]" sat in an answer under a story's heading, which no question block reads.
    reported = {why for _q, why in out}
    for where, gap in prep.placeholders(text):
        why = "a placeholder still to fill: %s" % gap
        if why not in reported:
            out.append((where, why))
    # What it says an employer heard, against what the profile says now: a pack built when
    # one employer heard one city kept saying so after the person told it another (2026-11-03).
    for m in _TOLD_LINE.finditer(text):
        now = places_told.place(m.group(1))
        if now and not places_told.same_place(now, m.group(2)):
            out.append(("the document", "it says you told %s you are in %s, and your profile "
                        "now says %s: build it again" % (m.group(1), m.group(2), now)))
    return out


_TOLD_LINE = re.compile(r"You told (.+?) you are in (.+?) \(source: profile/person\.json")


def _ungrounded_numbers(text, said) -> list:
    """[(question, why)] for each number in an answer to say that the profile does not hold.
    A figure the document's own notes and research carry (the employer's, the posting's) is
    allowed: an answer may repeat what it read about them."""
    import check_numbers
    answered = set()
    for _q, body in said:
        answered.update(ln for ln in body if ln.strip())
    rest = "\n".join(ln for ln in str(text or "").splitlines() if ln not in answered)
    base = check_numbers.grounded()
    allowed = check_numbers.Grounded(base, base.nouns, base.said, base.small)
    allowed.add_text(rest, nouns=False)
    out = []
    for q, body in said:
        # Pay and notice are what the person asks for and owes, never a claim about their work:
        # "between 48 and 58, base" is theirs to say (the band is read against the form's).
        if re.search(_PAY_Q + r"|\bnotice\b|\bstart\b", q, re.I):
            continue
        for f in check_numbers.check(" ".join(spoken(body)), allowed=allowed):
            # What they would do there ("in my first 90 days I'd ...") is a plan, never a
            # claim about their work.
            if _PLAN.search(f.get("context") or ""):
                continue
            out.append((q, "a number your profile does not hold: \"%s\". Say what "
                           "01-candidate-profile.md says, or write the true one there first"
                        % f.get("value", "")))
    return out


_PLAN = re.compile(r"\b(?:I(?:['’]d|['’]ll| would| will| could| plan| hope)|"
                   r"(?:first|next|within)\s+(?:\w+\s+)?\d+\s+(?:days|weeks|months))\b", re.I)


def _company_of(path) -> str:
    """The employer a living document is for, from its title ("# Interview prep: <role> at
    <employer>"), or ""."""
    m = re.search(r"^# Interview prep: .+ at (.+?)\s*$", _read(path), re.M)
    return m.group(1).strip() if m else ""


_NEXT = re.compile(r"^Last updated \S+\. Next: (.+?)(?:, \d{4}-\d{2}-\d{2}|, with |\. One document|\.$)",
                   re.M)


def answer_seconds(text) -> int:
    """About how long an answer in this document has, from the stage it is built for: a
    screen's 60 to 90 seconds, or a later round's two minutes for a story."""
    m = _NEXT.search(str(text or ""))
    # A document that does not say its stage gets the longer time: never cut for a guess.
    step = what_works.stage_step(m.group(1)) if m else ""
    return voice_check.SCREEN_SECONDS if step == "screen" else voice_check.ANSWER_SECONDS


# A heading that is a question someone could be asked: "### Why this team?", "### Tell me
# about a time you led something." Never one of this file's own ("### What you found out").
_ASKED = re.compile(r"\?\s*$|^(?:tell me|walk me|talk me|describe|give me)\b", re.I)


def _question_blocks(text, skip=()) -> dict:
    """{normalised question: (question, [lines])} for every question heading in the document
    outside the sections named in `skip`, its block running to the next heading."""
    out, section, q, body = {}, "", None, []
    for line in str(text or "").splitlines() + ["## "]:
        sec = re.match(r"^## (.*)$", line)
        head = re.match(r"^#{3,6} (.*)$", line)
        if sec or head:
            if q and section not in skip:
                out.setdefault(what_works._norm(q), (q, body))
            q, body = None, []
            if sec:
                section = sec.group(1).strip()
            elif _ASKED.search(head.group(1).strip()) and head.group(1).strip() != FOUND_OUT[4:]:
                q = head.group(1).strip()
            continue
        if q is not None and not line.startswith(INTENT_MARK):
            body.append(line)
    return out


failures = prep.failures


ANSWERS_HEADING = "## Your reasons, in your own words"


def write_motive(question, answer, use_for=(), suits=(), not_for=(), path=None) -> str:
    """Keep the person's own answer to a motivation question in profile/07-interview-
    prep.md, where every later pack at every employer reads it (hard_answers): the
    question as its heading, their words as said, `Use for:` with the other wordings it
    answers, and `Suits:`/`Not for:` with the kinds of employer it fits, which the pack
    checks against each employer. An answer already kept for the same question is
    replaced in place. Returns the file's path."""
    question, answer = _text(question), _text(answer)
    if not question or not answer:
        raise ValueError("a question and the person's own answer are both needed")
    kinds = {k for k, _rx in EMPLOYER_TYPES}
    for label, given in (("--suits", suits), ("--not-for", not_for)):
        bad = [x for x in given if x not in kinds]
        if bad:
            raise ValueError("%s takes kinds of employer the pack can tell apart (%s), not %s"
                             % (label, ", ".join(sorted(kinds)), ", ".join(bad)))
    kind = motive(question)
    tags = list(use_for) or [t.strip() for t in next(
        (t for k, _rx, _a, t in MOTIVES if k == kind), "").split(";") if t.strip()]
    body = ["", "> " + answer, ""]
    if tags:
        body.append("Use for: %s" % "; ".join('"%s"' % t for t in tags))
    if suits:
        body.append("Suits: %s" % ", ".join(suits))
    if not_for:
        body.append("Not for: %s" % ", ".join(not_for))
    path = path or person.path(STORIES_FILE)
    text = _read(path)
    lines = text.splitlines()
    want = what_works._norm(question)
    at = next((i for i, ln in enumerate(lines) if _HEADING.match(ln)
               and what_works._norm(_HEADING.match(ln).group(2).strip("\"“” ")) == want), None)
    if at is not None:
        level = len(_HEADING.match(lines[at]).group(1))
        end = next((j for j in range(at + 1, len(lines)) if _HEADING.match(lines[j])
                    and len(_HEADING.match(lines[j]).group(1)) <= level), len(lines))
        lines[at + 1:end] = body + [""]
    else:
        if ANSWERS_HEADING not in lines:
            lines += ["", ANSWERS_HEADING]
        lines += ["", '### "%s"' % question] + body
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return path


def stages_mark(ctx) -> str:
    """The stages this document has been built for, kept in it (open_actions reads it)."""
    m = _STAGES_MARK.search(ctx["living"] or "")
    have = [s for s in (m.group(1).split("; ") if m else []) if s]
    if ctx["stage"] not in have:
        have.append(ctx["stage"])
    # One round is one entry, by its fuller name: a line already holding "Round 2
    # (technical); Round 2" from an earlier rebuild is put right.
    have = [s for s in have if not any(o != s and _same_round(o, s) and len(o) > len(s)
                                       for o in have)]
    return "<!-- stages: %s -->" % "; ".join(dict.fromkeys(have))


CAMPAIGN_FILE = "campaign.json"


def record_campaign(company, role, chat="", declined=False, today=None) -> str:
    """The person's answer to the campaign chat: {"chat", "started"} or {"declined"}, in the
    process's folder. The offer is made once; open_actions and the brief read it, and leave
    an employer with a campaign chat to that chat."""
    folder = docpaths.app_folder(company, role)
    os.makedirs(folder, exist_ok=True)
    day = _text(today) or dt.date.today().isoformat()
    body = {"declined": day} if declined else {"chat": _text(chat), "started": day}
    path = os.path.join(folder, CAMPAIGN_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(body, fh, indent=1)
        fh.write("\n")
    return path


# ---------------------------------------------------------------- the pack

# What the person may hide from their pack (Tweak I2 and I3; person.json `prep`): hiding
# changes what they see, never what is checked. These are never hidden: what they wrote,
# the one screen with its do-not-say lines, the gaps and the money.
NEVER_HIDDEN = ("On one screen", "Your answers", "To rework", "Notes",
                "Gaps and honest framing", "Money and eligibility")
DETAILS = ("one_screen", "standard", "everything")


def hidden() -> set:
    """The sections the person's settings leave out of the pack they read."""
    detail = person.get("prep.detail", "standard")
    if detail == "one_screen":
        return {s for s in SECTIONS if s not in NEVER_HIDDEN}
    return {s for s in (person.get("prep.hide", None) or []) if s in SECTIONS
            and s not in NEVER_HIDDEN}


def _section(title, lines, empty) -> list:
    if title not in SECTIONS:
        raise ValueError("%r is not one of the pack's SECTIONS" % title)
    if title in hidden():
        return []
    # Every source in what this tool writes is said in words (plain_sources). What the person
    # wrote is theirs as it stands: Your answers carries it with the tool's own lines, which
    # answer_lines makes plain itself, and Small talk keeps what they found out.
    if title not in OWNED and title != "Small talk":
        lines = [plain_sources(ln) for ln in lines]
    return ["## " + title, ""] + (list(lines) if lines else ["- " + empty]) + [""]


# The lines of an answer's sources that quote text someone could say as it stands: a stock
# answer, the profile's own wording, or what to say.
_QUOTES_TEXT = re.compile(r"^(?:Prepared:|Say:|From your profile:|%s)" % re.escape(prep.RAW_MARK))


def _sentence(text, n=170) -> str:
    """The first sentence of `text`, cut where a clause ends when it runs long."""
    first = re.split(r"(?<=[.!?])\s+", _text(text), maxsplit=1)[0]
    return prep._short(first, n).rstrip(".") + "."


def say_these(ctx, answered, written=None) -> list:
    """Three to five things to get across, for the minutes before the call: the result to
    lead with, why this employer, the basics a screen checks, and the honest line on a gap.
    Each from the person's stories, what they wrote, the research or their profile, never
    invented; a draft they have not confirmed is never one of them."""
    written = written or {}
    if ctx["step"] == "offer":
        target, _floor = _band()
        return [x for x in (
            "Counter inside your target, %s, said as total pay." % target if target else "",
            "Ask what the package holds (bonus, pension, benefits) before you answer.",
            "Nothing is decided on the call: ask to see it in writing.") if x]
    out = []

    def mine(question_rx):
        for _key, (q, body) in written.items():
            if re.search(question_rx, q, re.I) and not drafted(body):
                said = " ".join(x.strip() for x in spoken(body) if x.strip())
                if said:
                    return said
        return ""
    # The result to lead with: the story the plan gives the first question a story answers.
    titles = [a["short"][len("story: "):] for _q, a in answered if a["kind"] == "story"]
    told = []
    for title in titles + [s["title"] for s in ctx["stories"]]:
        st = next((s for s in ctx["stories"] if s["title"].lower() == title.lower()), None)
        if st and _text(st["star"].get("R")) and st["title"] not in told:
            told.append(st["title"])
        if len(told) == (2 if ctx["step"] in ("technical", "final") else 1):
            break
    for i, title in enumerate(told):
        st = next(s for s in ctx["stories"] if s["title"] == title)
        result = _sentence(st["star"]["R"])
        out.append("Lead with your strongest result: %s" % result if i == 0 else
                   "Have a second story ready: %s (%s)." % (title, result.rstrip(".")))
    # Why them: their own words when written, else the first fact researched about them.
    why = mine(r"^why (?!are|did|do|have|would|should|leav)")
    if why:
        out.append("Why them, in your words: %s" % _sentence(why))
    else:
        # Something that happened there says "why them" better than what it is: the news first.
        research = ctx["research"] or {}
        facts = prep._facts(research.get("recent_news") or research.get("news"),
                            prep._research_source(research)) + hooks(ctx)
        facts = [f for f in facts if prep.UNREAD not in f.value]
        if facts:
            out.append("Why them: %s (source: %s)" % (_sentence(facts[0].value), facts[0].source))
    # The basics a screen checks, in one line.
    if ctx["step"] == "screen":
        basics = []
        place = places_told.place(ctx["company"]) or home_place()
        if place:
            basics.append("you are in %s" % place)
        _q, notice = _form_value(ctx, r"notice")
        if not notice:
            prepared = _answer_for("What is your notice period?", ctx["answers"],
                                   [ctx["company"]], ctx["company"])
            notice = _text((prepared or {}).get("answer"))
        if notice:
            basics.append("notice: %s" % _sentence(notice, 60).rstrip(".").lower())
        try:
            sheet = _screening()
            if sheet is not None and not sheet.requires_sponsorship():
                basics.append("no sponsorship needed")
        except (AttributeError, getattr(_screening(), "MissingFact", LookupError)):
            pass
        if basics:
            out.append("The basics: %s." % "; ".join(basics))
    # The gap most likely to come up, with its honest line.
    for g in ctx["facts"].get("gaps") or []:
        if g.get("framing"):
            out.append("If %s comes up: %s" % (_text(g["gap"]).rstrip("."),
                                               _sentence(g["framing"])))
            break
    return out[:MAX_SAY]


def ask_first(ctx) -> list:
    """Two or three questions to ask them, for the one screen: the first the research and
    the stage give, and the close."""
    if ctx["step"] == "offer":
        # An offer is not an interview: what to ask is what the package holds and when an
        # answer is wanted, never the close of an interview.
        return list(OFFER_QUESTIONS)
    out = []
    for ln in ask_lines(ctx):
        head, _why = _last_parens(re.sub(r"^\s*-\s*", "", ln))
        if head.endswith("?") and len(out) < MAX_ASK_FIRST - 1:
            out.append(head)
    return out + [CLOSE_QUESTION]


OFFER_QUESTIONS = ("What does the whole package hold: bonus, pension, benefits?",
                   "When would you like an answer by?")


# What this document and the chat around it are for, said once at the top of every pack: an
# app that listens in on a live interview, feeds answers during it or records the other side
# without asking is the opposite of preparation, and the app said nothing about it.
LIVE_LINE = ("This is for before and after the interview. Claude never helps during a live "
             "interview, and never records or transcribes one.")


def pack_markdown(ctx, never_say=None) -> str:
    """The living document for this process, one screen first. `never_say` defaults to the
    person's phrases. What the person wrote (their answers, the rework, their notes, what
    they found out about where they live) is carried from the last version."""
    banned = (lambda text: [m.group(0) for _p, rx in never_say for m in rx.finditer(text)]) \
        if never_say is not None else learned.dislikes
    questions = likely_questions(ctx)
    # The stories are chosen across the pack, not one question at a time.
    planned = dict(ctx, plan=plan_stories(questions, ctx))
    answered = [(q, answer_for(q, planned)) for q in questions]
    one_money, money_lines = money(ctx)
    hook_facts = hooks(ctx)
    donts = do_not_say(ctx, never_say)
    owned = _owned(ctx["living"])

    when = ", ".join(x for x in (ctx["date"], "with " + ctx["with"] + (
        " (assumed: the recruiter who leads it)" if ctx.get("with_assumed") else "")
        if ctx["with"] else "") if x)
    # Who, when and what for, then the one line on what this is for: the two lines about
    # keeping one document and sourcing every fact were the app's promises to itself, read by
    # a person minutes before a call (2026-11-03).
    lines = ["# Interview prep: %s at %s" % (ctx["role"], ctx["company"]), "",
             "Last updated %s. Next: %s%s." % (ctx["today"], ctx["stage"],
                                              ", " + when if when else ""),
             LIVE_LINE, stages_mark(ctx), ""]

    formats, _assumed = interview_formats(ctx)
    assessing = "; ".join(FORMAT_PREP[f]["tests"] for f in formats) or \
        STAGE_ANGLE.get(ctx["step"], "")
    screen = ["**What they are assessing:** %s." % assessing if assessing else "",
              "**What they want to hear:** %s." % "; ".join(FORMAT_PREP[f]["hear"] for f in formats)
              if formats else "", ""]
    screen = [ln for i, ln in enumerate(screen) if ln or (i == 2 and any(screen[:2]))]
    # Once they have written their reasons under the question, the one screen says so: it
    # went on saying "ask you first" over an answer they had given (2026-10-25).
    written = _answer_blocks(_owned(ctx["living"]).get("Your answers"))
    say = say_these(ctx, answered, written)
    if say:
        screen += ["**Say these**"] + ["- " + plain_sources(x) for x in say] + [""]
    screen += ["**Likely questions, and what to answer with**"]

    def _short(q, a):
        mine = written.get(what_works._norm(q["question"]))
        if a["kind"] == "ask" and mine and spoken(_own_words(mine[1])):
            return "your answer"
        return a["short"]
    screen += ["%d. %s -> %s" % (i, q["question"], _short(q, a))
               for i, (q, a) in enumerate(answered[:ONE_SCREEN_QUESTIONS], 1)]
    ask = ask_first(ctx)
    if ask:
        screen += ["", "**Ask them**"] + ["- " + x for x in ask]
    screen += ["", "**Hooks**"]
    letter = _text((ctx["draft"] or {}).get("_path"))
    screen += ["- %s%s (source: %s)" % ("The letter told them: " if f.source == letter else "",
                                         _hook_text(f.value), f.source)
               for f in hook_facts[:HOOKS]] or ["- %s: nothing researched to hang \"why us\" on."
                                                % prep.NOT_RESEARCHED]
    screen += ["", "**Money:** %s." % one_money, ""]
    # The list of what not to say quotes the very words it warns against, so it is neither
    # flagged for them here nor read by voice_check as something the person will say. Only
    # the one or two that matter, and none at all when nothing specific is on file.
    quoted = ([voice_check.QUOTED_OPEN, "**Do not say**"] + donts[:MAX_DO_NOT]
              + [voice_check.QUOTED_CLOSE]) if donts else []
    lines += _section("On one screen", prep._flag_banned(screen, banned) + quoted, "")
    yours = answer_lines(ctx, answered)
    lines += _section("Your answers", ([ANSWERS_INTRO, ""] if yours else [])
                      + prep._flag_banned(yours, banned), "No questions to answer yet.")
    # What was said to them is quoted as it was sent; only what this file tells the person
    # to do about it is checked against the words they never use.
    told = told_lines(ctx)
    lines += _section("What they have been told", [ln for t in told for ln in (
        prep._flag_banned([t], banned) if t.startswith("  - ") else [t])],
                      "Nobody at %s is in your contacts and no form is on file: nothing they "
                      "were told is on record." % ctx["company"])
    lines += _section("Who you are meeting", prep._flag_banned(meeting_lines(ctx), banned),
                      "Nobody named for this stage yet: when the invite names them, tell Claude, "
                      "and this says what they listen for.")
    lines += _section("The format", prep._flag_banned(format_lines(ctx), banned),
                      "An offer: nothing to drill.")

    # Notes on each question, never words to say: where an answer can come from. Under Your
    # answers, an unwritten answer already lists the first notes it is said from and every
    # question says what it checks: here, only what is not there, so the pack never says the
    # same thing twice (2026-11-03: "walls of text"). The text a stock answer or the profile
    # holds is quoted only while the person's own answer is unwritten, and marked as notes;
    # repeated beside an answer already written, the raw profile wording and an older stock
    # answer read as things to say (2026-10-20).
    kept = _answer_blocks(owned.get("Your answers"))
    detail = []
    for q, a in answered:
        detail.append("- **Q.** %s (%s; source: %s)" % (q["question"], q["why"], q["source"]))
        written = spoken((kept.get(what_works._norm(q["question"])) or ("", []))[1])
        for ln in a["lines"][0 if written else ANSWER_NOTES:]:
            if _QUOTES_TEXT.match(ln):
                if written:
                    continue
                ln = "Notes only: " + ln
            detail.append("  - " + ln)
    lines += _section("Likely questions", prep._flag_banned(detail, banned),
                      "No questions: nothing on file to anticipate.")
    lines += _section("Stories", prep._flag_banned(_story_lines(ctx), banned),
                      "No stories written yet: tell Claude three or four things you did and how "
                      "they turned out, and it writes them up with you.")
    lines += _section("What the paper says", paper_lines(ctx), "Nothing on file about what was sent.")
    # The one screen carries the one or two that matter; the rest are kept here, quoted as
    # the one screen quotes them (never read as words to say), so nothing is lost.
    more = donts[MAX_DO_NOT:]
    careful = ([voice_check.QUOTED_OPEN, "- Careful, too:"] + ["  " + d for d in more]
               + [voice_check.QUOTED_CLOSE]) if more else []
    gaps = prep._flag_banned(gap_lines(ctx), banned)
    lines += _section("Gaps and honest framing", (gaps or (["- No gap the posting names: lead "
                                                            "with the matches."] if careful else []))
                      + careful, "No gap the posting names: lead with the matches.")
    lines += _section("Money and eligibility", prep._flag_banned(money_lines, banned),
                      prep.NOT_RESEARCHED)
    # A prohibition the research wrote as one is said once ("Do not call it a discounter"),
    # never under a "Do not say:" label that repeats it.
    company = [re.sub(r"^- \*\*Do not say:\*\* (?=(?:Do not|Don'?t|Never|Avoid)\b)", "- ", ln)
               for ln in prep._company_lines(ctx["research"], ctx["today"])]
    stale = prep._stale_line(ctx["research"], ctx["today"]) if company else ""
    lines += _section("The company", company + ([stale] if stale else []),
                      "%s %s itself, from its own pages." % (RESEARCH_MARK, ctx["company"]))
    talk = [plain_sources(ln) for ln in small_talk_lines(ctx)]
    found = _found_out(ctx["living"])
    lines += _section("Small talk", prep._flag_banned(talk, banned) + ["", FOUND_OUT, ""]
                      + (found or [FOUND_EMPTY]), "")
    ask = ask_lines(ctx) + (["- %s (before you answer an offer)" % q for q in OFFER_QUESTIONS]
                            if ctx["step"] == "offer" else
                            ["- %s (the close: it gives them the last word on any doubt)"
                             % CLOSE_QUESTION])
    lines += _section("Ask them", prep._flag_banned(ask, banned),
                      "Nothing researched to anchor a question on.")
    lines += _section("Warm route", prep._flag_banned(warm_lines(ctx), banned),
                      "Nobody in the contact book at %s." % ctx["company"])
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


# Notes kept by hand for an employer before its living document existed: a campaign file in
# documents/network, a call prep written by hand. /interview read neither, so what was
# decided in them (where to say they are based for this employer, the reasons for each move)
# was lost to the next chat. A file is folded in once, and says so in the document's Notes.
FOLDED = "Folded in from"
_NOTE_WORDS = re.compile(r"\b(?:campaign|prep|call|screen|interview|notes?|process|plan)\b", re.I)
# What the tools themselves write; never hand-kept.
_WRITTEN = frozenset({"outcome.md", "job_posting.md", "outreach.md", "screening_answers.md",
                      LIVING, "prep.md", "draft.md"})


# First words too common to stand for one employer on their own in a file name.
_GENERIC = frozenset("""bank banks data group global capital consulting royal national first new
city united digital tech labs health the insurance financial services partners""".split())


def _names_employer(filename, key) -> bool:
    """Does a file name name this employer? By its first word when that word is its own
    ("fernhill_call_prep.md" for Fernhill Freight), by its first two when the first is
    common ("royal" alone is not Royal Bank)."""
    words = re.sub(r"[^a-z0-9]+", " ", os.path.splitext(filename)[0].lower()).split()
    want = [w for w in key.split() if w not in ("the", "of", "and")]
    if not want:
        return False
    if want[0] in _GENERIC or len(want[0]) < 4:
        return len(want) > 1 and want[0] in words and want[1] in words
    return want[0] in words


def handkept_notes(tracker=None, contacts=None) -> list:
    """[{company, role, path, living}] for every hand-kept note about an employer with a live
    hiring process that its living document has not folded in yet: a file in documents/network
    that names the employer, one in a contact's folder there for someone at it, or one beside
    the process that no tool wrote. Beside an application's living document, the same: what
    no tool wrote, and an older pack for a round the document covers."""
    import glob
    tracker = what_works._csv(person.state("job_search_tracker.csv")) if tracker is None \
        else tracker
    contacts = state.load_contacts(person.state("network_contacts.csv")) \
        if contacts is None and os.path.exists(person.state("network_contacts.csv")) \
        else (contacts or [])
    top = glob.glob(os.path.join(glob.escape(person.state("documents", "network")), "*.md"))
    out = []
    for r in tracker:
        if _text(r.get("status")).lower() in throttle.FINAL:
            continue
        company, role = _text(r.get("company")), _text(r.get("role"))
        k = company_key(company)
        folder = docpaths.app_folder(company, role)
        living = _read(os.path.join(folder, LIVING))
        # An application with interviews has a living document too: what sits beside it is
        # read (an older pack for the round it covers, 2026-10-22); notes elsewhere that name
        # the employer are a process's alone, since an application's contacts are many.
        if not is_process(r):
            if not living:
                continue
            named = glob.glob(os.path.join(glob.escape(folder), "*.md"))
        else:
            named = [p for p in top
                     if _NOTE_WORDS.search(os.path.basename(p).replace("_", " "))
                     and _names_employer(os.path.basename(p), k)]
            mine = [c for c in contacts if company_key(c.get("company")) == k]
            for c in mine:
                named += glob.glob(os.path.join(glob.escape(person.state(
                    "documents", "network", _text(c.get("contact_id")) or "-")), "*.md"))
            named += glob.glob(os.path.join(glob.escape(folder), "*.md"))
        # The rounds the living document is for: a pack kept for one of them beside it is
        # an older draft of the same round, and what it holds is folded in like a note.
        m = _STAGES_MARK.search(living)
        rounds = [x for x in (m.group(1).split("; ") if m else []) if x]
        for p in sorted(set(named)):
            base = os.path.basename(p)
            if base in _WRITTEN or (base.startswith("interview_prep_") and not (
                    living and any(_pack_for_round(base, r) for r in rounds))):
                continue
            if "%s %s" % (FOLDED, _rel(p)) in living:
                continue
            out.append({"company": company, "role": role, "path": _rel(p),
                        "living": _rel(os.path.join(folder, LIVING))})
    return out


# ---------------------------------------------------------------- a rebuild keeps their lines

# A living document is finished by hand: questions added under Ask them, answers under a
# heading of their own, sections for the next round, the close. A rebuild kept only the
# sections it knew (Your answers, To rework, Notes, what they found out) and dropped the rest
# without a word: on a copy of a real repo, a hand-finished document for a process with
# rounds still to come lost 94 lines (2026-10-21). So a rebuild now changes only what this
# tool wrote. What it wrote last time is kept beside the document (BUILT), and every line of
# the document that is not in it is the person's: a section of their own stays whole, after
# the section it followed; a line inside one of the tool's sections stays where it was, the
# tool's own lines around it refreshed; a line of the tool's they changed or removed stays
# as they left it while the tool's version of it has not changed. Before anything is
# written, every line of theirs is looked for in the new document, and if one is missing the
# document is left as it was and the rebuild says so.
BUILT = ".interview_prep.built.json"
# A document built before BUILT existed has no record of what the tool wrote: a line in one
# of its sections that the new build does not write may be the person's or an older build's.
# None is dropped: they are kept together at the end of Notes, under this heading, for the
# session to sort (moving the person's where they belong, deleting the rest), and said.
LEFTOVER_HEAD = "### Kept from the version before this one"
LEFTOVER_NOTE = ("These lines were in the document before this rebuild, in sections this tool "
                 "writes, and it no longer writes them. Any you wrote: move them where you want "
                 "them. The rest: delete them.")
_TITLE = re.compile(r"^# Interview prep: .+ at .+$")
_SECTION_HEAD = re.compile(r"^## (.+?)\s*$")
# What only this tool writes, never a person: read as the tool's in a document with no record.
_TOOL_LINE = re.compile(r"^(?:Last updated \S+\. Next: |<!-- stages: .* -->$|%s|%s$|%s$|%s$|%s$|%s$|"
                        r"Every fact carries its source, and anything unsourced was left out\.$|"
                        r"- From: |%s|- Nothing yet: each line you add here, with its source, "
                        r"stays\.$|- %s$|- %s$|- Your own answer is under Your answers\.$)"
                        % (re.escape(INTENT_MARK), re.escape(TO_WRITE), re.escape(OLD_TO_WRITE),
                           re.escape(ANSWERS_INTRO),
                           re.escape(OLD_ANSWERS_INTRO), re.escape(LIVE_LINE),
                           re.escape(FOUND_EMPTY), re.escape(REWORK_EMPTY),
                           re.escape(NOTES_EMPTY[2:])))


class WouldLose(ValueError):
    """A rebuild that would drop what the person wrote, or replace a document they wrote by
    hand: nothing is written, and the message says why in plain words."""


def built_path(folder) -> str:
    return os.path.join(folder, BUILT)


def built_record(folder) -> dict | None:
    """What the last build wrote into this process's living document ({"generated": text,
    "stage", "mapped": {question: story}}), or None when no build recorded it (a document
    from before the record, or a record a merge left unreadable)."""
    try:
        with open(built_path(folder), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("generated"), str) else None


def _doc_sections(lines) -> list:
    """[(title, [lines])]: what comes before the first "## " heading under "", then each
    "## " section, heading line first. A heading inside a fenced block is not a section."""
    out, fenced = [("", [])], False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            fenced = not fenced
        m = None if fenced else _SECTION_HEAD.match(ln)
        if m:
            out.append((m.group(1), [ln]))
        else:
            out[-1][1].append(ln)
    return out


def _known(sections) -> dict:
    """{title: index} for the sections this tool writes (the preamble included), each by its
    first appearance: a second "## Notes" is a section of the person's own."""
    out = {}
    for i, (title, _lines) in enumerate(sections):
        if (title == "" or title in SECTIONS) and title not in out:
            out[title] = i
    return out


def _matched(a, b) -> dict:
    """{index in a: index in b} for the lines the two share, in order. A blank line never
    starts a match: matched on its own, the blank after a section's last line was paired with
    one higher up, and the line between was written twice."""
    import difflib
    out = {}
    for i, j, size in difflib.SequenceMatcher(lambda ln: not ln.strip(), a, b,
                                              autojunk=False).get_matching_blocks():
        for k in range(size):
            out[i + k] = j + k
    return out


def _not_in(lines, base) -> list:
    """The lines of `lines` that `base` does not hold, as often as each appears there."""
    from collections import Counter
    gen = Counter(base)
    out = []
    for ln in lines:
        if gen[ln]:
            gen[ln] -= 1
        else:
            out.append(ln)
    return out


def _tools_own(line) -> bool:
    """A line only this tool writes and only it may change: the date and stage line, the
    stages it was built for, a marker, a placeholder, a research request."""
    return bool(_TOOL_LINE.match(line)) or research_line(line)


def _as_built(bc, oc) -> list:
    """`oc` with the tool's own lines as it wrote them: one changed by hand (an older
    rebuild's doubled stages line) is the tool's again, and one removed is put back where it
    was. Everything else in `oc` stays as it is."""
    keep = [ln for ln in oc if not (_tools_own(ln) and ln not in bc)]
    for i, ln in enumerate(bc):
        if _tools_own(ln) and keep.count(ln) < bc[:i + 1].count(ln):
            keep.insert(min(i, len(keep)), ln)
    return keep


def _merge3(base, ours, new) -> tuple:
    """One section, three ways: `base` what the tool wrote last time, `ours` the document now,
    `new` what the tool writes now. A stretch only the tool changed takes the tool's; one only
    the person changed takes theirs; where both changed it, the tool's new lines and then
    every line of theirs. A line of theirs the tool now carries itself (an answer it keeps
    under its question, wherever in the section they wrote it) is written once, where the
    tool puts it. Returns (the section, the lines in it that are the person's, which the
    result must hold)."""
    from collections import Counter
    mo, mn = _matched(base, ours), _matched(base, new)
    from_base = set(mn.values())
    carried = Counter(ln.rstrip() for j, ln in enumerate(new) if j not in from_base and ln.strip())
    # A line all three hold, never a blank one: the stretches between are compared.
    sync = [i for i in range(len(base)) if base[i].strip() and i in mo and i in mn]
    out, mine, pb, po, pn = [], [], -1, -1, -1

    def placed(lines, bc):
        """`lines` (a stretch of theirs) less the lines of theirs the tool carries, and the
        blank line that followed one."""
        gen, got, skip_blank = Counter(bc), [], False
        for ln in lines:
            if gen[ln]:
                gen[ln] -= 1
                got.append(ln)
                skip_blank = False
            elif ln.strip() and carried[ln.rstrip()]:
                carried[ln.rstrip()] -= 1
                skip_blank = True
            elif not ln.strip() and skip_blank:
                skip_blank = False
            else:
                got.append(ln)
                skip_blank = False
        return got

    for i in sync + [len(base)]:
        oi = mo[i] if i < len(base) else len(ours)
        ni = mn[i] if i < len(base) else len(new)
        bc, nc = base[pb + 1:i], new[pn + 1:ni]
        oc = _as_built(bc, ours[po + 1:oi])
        theirs = _not_in(oc, bc)
        mine += theirs
        if oc == bc or oc == nc:
            out += nc
        elif nc == bc:
            out += placed(oc, bc)
        else:
            extra = placed(theirs, [])
            while extra and not extra[-1].strip():
                extra.pop()
            while extra and not extra[0].strip():
                extra.pop(0)
            out += nc + extra
        if i < len(base):
            out.append(new[ni])
        pb, po, pn = i, oi, ni
    return out, mine


def _before_bracket(line) -> str:
    """A line up to its first bracket: what the tool writes before "(source: ...)", "(as the
    last build answered it; ...)" and the like, which change from one build to the next."""
    lead = line.split(" (", 1)[0].rstrip()
    return lead if " (" in line and len(lead.strip(" -*")) >= 15 else ""


def _legacy(ours, new_doc, title, new=()) -> list:
    """The lines of one section of a document with no record of what the tool wrote that the
    new document does not hold. A line only this tool ever writes (_TOOL_LINE), a question
    heading in Your answers with nothing of theirs under it, and a line the new build writes
    again in this section with only its bracket changed (its source, how a story was chosen)
    are the tool's own and go; anything else is kept, never guessed at. `new_doc` is a
    Counter of the new document's lines, used up as they are found; `new` the section as the
    tool writes it now."""
    leads = {_before_bracket(ln) for ln in new} - {""}
    left = []
    for i, ln in enumerate(ours):
        k = ln.rstrip()
        if new_doc[k]:
            new_doc[k] -= 1
            continue
        if not ln.strip() or _TOOL_LINE.match(ln) or (i == 0 and title):
            continue
        if _before_bracket(ln) in leads:
            continue
        if title == "" and _TITLE.match(ln):
            continue
        if title == "Your answers" and ln.startswith("### "):
            j = i + 1
            while j < len(ours) and not re.match(r"^#{2,3} ", ours[j]):
                j += 1
            if all(not x.strip() or _TOOL_LINE.match(x) for x in ours[i + 1:j]):
                continue
        left.append(ln)
    return left


def merge_living(old, new, base=None) -> tuple:
    """(the document to write, the lines kept from an older build at the end of Notes) for
    a rebuild of `old` as `new`, given `base`, what the tool wrote last time (None: no record).
    It raises WouldLose when `old` is a document this tool did not build, or when a line the
    person wrote would be missing from the result."""
    from collections import Counter
    if not str(old or "").strip():
        return new, []
    o_lines, n_lines = old.splitlines(), new.splitlines()
    first = next((ln for ln in o_lines if ln.strip()), "")
    if base is None and not _TITLE.match(first):
        raise WouldLose("the interview prep there was written by hand, not built by this tool, "
                        "so a rebuild would replace it: it is kept as it is and nothing was "
                        "written. Only if the person wants the tool's document as well: rename "
                        "that file (to prep_notes.md, say) and build again, and the new "
                        "document lists it as notes of theirs to fold in")
    O, N = _doc_sections(o_lines), _doc_sections(n_lines)
    B = _doc_sections(base.splitlines()) if base is not None else None
    ko, kb = _known(O), (_known(B) if B is not None else {})
    # The person's own sections, each after the section of the tool's it followed.
    after: dict = {}
    anchor = ""
    for i, (title, lines) in enumerate(O):
        if ko.get(title) == i:
            anchor = title
        else:
            after.setdefault(anchor, []).append(lines)
    new_doc = Counter(ln.rstrip() for ln in n_lines)
    mine, leftovers, out = [], [], []
    for title, lines in N:
        merged = list(lines)
        if title in ko:
            ours = O[ko[title]][1]
            if B is not None and title in kb:
                merged, theirs = _merge3(B[kb[title]][1], ours, lines)
                mine += theirs
            else:
                left = _legacy(ours, new_doc, title, lines)
                leftovers += left
                mine += left
        if title == "Notes" and leftovers:
            # Notes now holds something: its placeholder goes, as the next build drops it.
            merged = [ln for ln in merged if ln.strip() != NOTES_EMPTY]
            while merged and not merged[-1].strip():
                merged.pop()
            merged += ["", LEFTOVER_HEAD, "", LEFTOVER_NOTE, ""] + leftovers + [""]
        out += merged
        for own in after.get(title, []):
            mine += own
            if out and out[-1].strip():
                out.append("")
            out += own
    text = "\n".join(out).rstrip() + "\n"
    lost = _missing(mine, text)
    if lost:
        raise WouldLose("%d line(s) you wrote would have been lost (the first: \"%s\"), so "
                        "the document is kept as it was and nothing was written"
                        % (len(lost), clip_line(lost[0])))
    return text, leftovers


def clip_line(line, n=70) -> str:
    line = " ".join(str(line).split())
    return line if len(line) <= n else line[:n - 3].rstrip() + "..."


def _missing(lines, text) -> list:
    """The lines of `lines` (blank ones aside) that `text` does not hold, as often as each
    appears: what a rebuild would lose."""
    from collections import Counter
    have = Counter(ln.rstrip() for ln in str(text).splitlines())
    out = []
    for ln in lines:
        k = ln.rstrip()
        if not k.strip():
            continue
        if have[k]:
            have[k] -= 1
        else:
            out.append(ln)
    return out


def _rebuild(ctx, never_say=None) -> tuple:
    """(the document a rebuild writes, the lines kept at the end of Notes from an older build,
    what the tool itself wrote)."""
    new = pack_markdown(ctx, never_say)
    path = living_path(ctx)
    record = built_record(ctx["folder"])
    try:
        text, leftovers = merge_living(_read(path), new, record["generated"] if record else None)
    except WouldLose as exc:
        raise WouldLose("%s: %s" % (_rel(path), exc)) from None
    return text, leftovers, new


def rebuilt(ctx, never_say=None) -> tuple:
    """(the living document as a rebuild would write it now, the lines kept at the end of
    Notes from an older build), from what is on disk; it raises WouldLose (see merge_living)."""
    text, leftovers, _new = _rebuild(ctx, never_say)
    return text, leftovers


def write_pack(ctx, never_say=None) -> str:
    """Write the living document beside the application and return its path. Every line the
    person wrote in it is kept (merge_living); what was kept from an older build at the end
    of Notes is in ctx["kept_from_before"]; it raises WouldLose, writing nothing, when a line of
    theirs would be lost."""
    path = living_path(ctx)
    os.makedirs(ctx["folder"], exist_ok=True)
    text, leftovers, new = _rebuild(ctx, never_say)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    # The stories the session chose (--map), kept for this round alone: a later round
    # chooses afresh, preferring one not yet told at this employer.
    mapped = {q: t for q, t in dict(ctx.get("kept_map") or {}, **(ctx.get("map") or {})).items()
              if _text(t)}
    with open(built_path(ctx["folder"]), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated": new, "stage": ctx["stage"], "mapped": mapped}, fh, indent=1,
                  ensure_ascii=False)
        fh.write("\n")
    ctx["kept_from_before"] = leftovers
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


def rework_entry(question, note, date=None, where="mock") -> str:
    """The line To rework keeps for one answer to work on."""
    return '- %s, %s: "%s": %s' % (_text(date) or dt.date.today().isoformat(), where,
                                   _text(question), _text(note))


def add_rework(company, role, stage, question, note, date=None, where="mock") -> str:
    """An answer to work on, appended under To rework in the process's living document (or
    an older stage's pack, where the process predates it)."""
    folder = docpaths.app_folder(company, role)
    path = os.path.join(folder, LIVING)
    if not os.path.exists(path):
        path = os.path.join(folder, pack_name(stage))
    text = _read(path)
    if not text:
        raise LookupError("no pack for %s at %s yet: build it first (pack --write)"
                          % (stage, company))
    line = rework_entry(question, note, date, where)
    if line in _rework_lines(text):
        return path                     # kept already: the same answer, the same day
    m = re.search(r"^## To rework\s*$", text, re.M)
    if not m:
        text = text.rstrip() + "\n\n## To rework\n\n" + line + "\n"
    else:
        body = text[m.end():]
        nxt = re.search(r"^## ", body, re.M)
        end = m.end() + (nxt.start() if nxt else len(body))
        kept = _rework_lines(text)
        text = text[:m.end()] + "\n\n" + "\n".join(kept + [line]) + "\n\n" + text[end:].lstrip()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.rstrip() + "\n")
    return path


# ---------------------------------------------------------------- mock feedback

# Feedback on a practice answer is free text in the chat, and "you were vague" cannot be
# checked by anyone. So every point quotes the person's own words, and the quote is checked
# against what they said before the feedback is shown: a quote that is not theirs is the
# model putting words in their mouth. The verdict is a coarse band, because a fine score
# (7/10, 82 out of 100) reads as a measurement nobody made, and never a verdict on the hire,
# which only the employer can give.
BANDS = ("Strong", "Solid", "Gap")
# Fewer words than this match by accident ("I did" is in most answers) and point at nothing.
MIN_QUOTE_WORDS = 3
_FOLD_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                              "–": "-", "—": "-", " ": " "})
# A score is a number given as one: "7/10", "4 out of 5", "scored 82", "a rating of 3", "80%
# ready". A note that only mentions a rating model and a count three words on ("the credit
# rating model you built across 3 teams") was refused as a score (2026-10-21).
_SCORE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:/|out of)\s*\d+\b|"
                    r"\b(?:scored?|scoring|rated|rating|marked|graded?)\s+(?:of\s+|at\s+|as\s+|"
                    r"an?\s+|a\s+solid\s+|a\s+strong\s+)?\d+(?:\.\d+)?\b(?!\s*(?:%|[a-z]+s\b))|"
                    r"\b(?:score|rating|mark|grade)\s*(?::|=|of)\s*\d|"
                    r"\b\d+(?:\.\d+)?\s+(?:points?|marks?)\s+(?:out of|from)\b|"
                    r"\b\d+\s*%\s*(?:ready|there|of the way|match|fit|likely|chance)\b", re.I)
_VERDICT = re.compile(r"\b(?:no[- ]hire|strong hire|hireable|offer[- ]ready|would be hired|"
                      r"(?:they|we|i)(?:'d| would| will| should) (?:hire|reject|pass|fail|"
                      r"advance) you|you(?:'d|'ll| would| will)? (?:get|land|win) (?:the|this|"
                      r"that|an) (?:job|offer|role)|you(?:'d|'ll| would| will)? (?:pass|fail) "
                      r"(?:the|this|that) (?:interview|round|screen|stage))\b", re.I)


def _said_words(text) -> str:
    """Words as said, for comparing a quote with an answer: case, curly quotes and spacing
    set aside, the quote's own quote marks and closing punctuation off."""
    text = str(text or "").translate(_FOLD_QUOTES).casefold()
    return " ".join(text.split()).strip(" \"'.,;:!?\u2026")


def quote_in(quote, answer) -> bool:
    """Is `quote` a run of the person's own answer, whole words, never stitched together?"""
    q = _said_words(quote)
    return bool(q) and re.search(r"(?<!\w)%s(?!\w)" % re.escape(q), _said_words(answer)) is not None


def feedback_problems(answer, band, points) -> list:
    """Why this feedback cannot be shown, or []: a band other than Strong, Solid or Gap, no
    point at all, a quote that is not a run of what they said (or too short to point at
    anything, or two pieces joined by "..."), and a score or a hiring verdict in a note.
    `points` is [(their words, what worked or what to sharpen)]."""
    out = []
    if _text(band).capitalize() not in BANDS:
        out.append("the band is %r: it is one of %s, never a score" % (_text(band), ", ".join(BANDS)))
    if not points:
        out.append("no point of feedback: each one quotes their words, then says what to keep "
                   "or change")
    for quote, note in points:
        if re.search(r"\.\.\.|…", _text(quote).strip(" .…")):
            out.append("\"%s\" joins two pieces of what they said: quote one run of it"
                       % _text(quote))
        elif len(_said_words(quote).split()) < MIN_QUOTE_WORDS:
            out.append("\"%s\" is too short to point at anything: quote at least %d of their "
                       "words" % (_text(quote), MIN_QUOTE_WORDS))
        elif not quote_in(quote, answer):
            out.append("\"%s\" is not what they said: quote their answer word for word"
                       % _text(quote))
        for rx, what in ((_SCORE, "a score"), (_VERDICT, "a verdict on the hire")):
            m = rx.search(_text(note))
            if m:
                out.append("the note on \"%s\" gives %s (\"%s\"): say what to keep or change, "
                           "never a score or whether they would be hired" % (
                               prep.clip(quote, 40), what, m.group(0)))
    return out


def feedback_lines(question, band, points) -> list:
    """The feedback as it is shown: the band, then each point under its own words."""
    out = ["**%s.** %s" % (_text(band).capitalize(), _text(question))]
    out += ["- You said \"%s\": %s" % (_text(q).strip(" \"'"), _text(n)) for q, n in points]
    return out


# ---------------------------------------------------------------- what the page reads

# The page shows a process's living document as a reading view (FUNCTIONS_SPEC 1.8): the one
# screen, the questions to practise with the person's own answers, what is kept to rework.
# Read here, from the document this file wrote, so the page and the pack never disagree on
# what it says; code only, no model call.


def section_lines(text, title) -> list:
    """The lines under `## <title>` in a living document, up to the next `## `."""
    m = re.search(r"^## %s\s*$" % re.escape(title), str(text or ""), re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)
    return (body[:nxt.start()] if nxt else body).splitlines()


_BOLD_LEAD = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
_SOURCE_TAIL = re.compile(r"\s*\(source: ([^()]*)\)\s*$")
_SCREEN_PART = {"likely questions, and what to answer with": "questions", "hooks": "hooks",
                "do not say": "do_not_say", "say these": "say", "ask them": "ask"}


def _plain(text) -> str:
    return " ".join(re.sub(r"\*\*|__", "", str(text or "")).split())


def one_screen(text) -> dict | None:
    """The "On one screen" section as parts: {assessing, hear, questions [{question,
    answer}], hooks [{text, source}], money, do_not_say [{text, source}], say [{text,
    source}], ask [{text, source}]}; each item that uses a phrase the person banned carries
    `careful`. None when there is no such section. `say` and `ask` are empty in a document
    built before the one screen carried them."""
    lines = section_lines(text, "On one screen")
    if not any(ln.strip() for ln in lines):
        return None
    out = {"assessing": None, "hear": None, "questions": [], "hooks": [], "money": None,
           "do_not_say": [], "say": [], "ask": []}
    part, last = None, None
    for ln in lines:
        s = ln.strip()
        if not s or s in (voice_check.QUOTED_OPEN, voice_check.QUOTED_CLOSE):
            continue
        if s.startswith("- careful:") and last is not None:
            last["careful"] = _plain(s[len("- careful:"):]).strip()
            continue
        head = re.fullmatch(r"\*\*(.+?)\*\*", s)
        if head and head.group(1).lower() in _SCREEN_PART:
            part, last = _SCREEN_PART[head.group(1).lower()], None
            continue
        lead = _BOLD_LEAD.match(s)
        if lead:
            name = lead.group(1).lower()
            value = _plain(lead.group(2)).rstrip(".") or None
            if name == "what they are assessing":
                out["assessing"] = value
            elif name == "what they want to hear":
                out["hear"] = value
            elif name == "money":
                out["money"] = value
            part, last = None, None
            continue
        if part == "questions":
            m = re.match(r"^\d+\.\s+(.*)$", s)
            if m:
                q, _sep, a = m.group(1).partition(" -> ")
                last = {"question": _plain(q), "answer": _plain(a) or None}
                out["questions"].append(last)
        elif part in ("hooks", "do_not_say", "say", "ask") and s.startswith("- "):
            body = s[2:]
            src = _SOURCE_TAIL.search(body)
            last = {"text": _plain(body[:src.start()] if src else body),
                    "source": src.group(1).strip() if src else None}
            out[part].append(last)
    return out


def _last_parens(text) -> tuple:
    """(what comes before, what is inside) for a line ending in one balanced parenthetical,
    nested ones within it kept: "Q? (asked here before (Phone screen); source: x)"."""
    t = str(text or "").rstrip()
    if not t.endswith(")"):
        return t, ""
    depth = 0
    for i in range(len(t) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(t[i], 0)
        if depth == 0:
            return t[:i].rstrip(), t[i + 1:-1]
    return t, ""


def practice(text) -> dict:
    """What the page practises from (FUNCTIONS_SPEC 1.8): {questions [{question, why, answer,
    draft}], reworked [lines], bands, min_quote_words}. `answer` is what the person wrote to
    say under Your answers (their words only, notes out), `draft` whether it still carries a
    draft's mark; `reworked` the lines kept under To rework. The band and the quote rule are
    the ones `feedback` holds every point to, so the page can check its own feedback before
    showing it."""
    written = _answer_blocks(_owned(text).get("Your answers"))
    qs = []
    # An older pack, written before its sections, lists its questions at the top level.
    for ln in section_lines(text, "Likely questions") or str(text or "").splitlines():
        if not ln.startswith("- **Q.** "):
            continue
        head, inside = _last_parens(ln[len("- **Q.** "):])
        why = inside.rsplit("; source: ", 1)[0] if "; source: " in inside else ""
        q = _plain(head if why or "; source: " in inside else ln[len("- **Q.** "):])
        mine = (written.get(what_works._norm(q)) or ("", []))[1]
        said = [x.strip() for x in spoken(mine) if x.strip()]
        qs.append({"question": q, "why": _plain(why) or None,
                   "answer": " ".join(said) or None, "draft": prep.drafted(mine)})
    return {"questions": qs, "reworked": rework_lines(text),
            "bands": list(BANDS), "min_quote_words": MIN_QUOTE_WORDS}


def format_of(text) -> dict | None:
    """The format section as the page shows it: {names, assumed, told}. `names` are the
    kinds of round it prepares for ("Screen", "Case"), `assumed` whether the document had
    to assume them, `told` what the person was told about how the round runs. None when the
    document has no such section."""
    lines = section_lines(text, "The format")
    if not any(ln.strip() for ln in lines):
        return None
    names = [m.group(1) for ln in lines for m in [re.match(r"^- \*\*(.+?)\.\*\*", ln)] if m]
    told = [_plain(_SOURCE_TAIL.sub("", ln.split(": ", 1)[1]))
            for ln in lines if ln.startswith("- What you were told about this round: ")]
    return {"names": names, "assumed": any(ln.startswith("- Assumed ") for ln in lines),
            "told": told}


def rework_lines(text) -> list:
    """The lines kept under "To rework" in a living document."""
    return _rework_lines(text)


# ---------------------------------------------------------------- the prep as the page reads it

# The page showed the whole document as it is written, after its one screen: twenty thousand
# characters of headings, sources, file paths, commands and status codes, the same notes
# twice (2026-11-03: "hits you with walls of text, links to random json files and
# destinations the user shouldn't know about, is weirdly formatted and sometimes randomly
# says draft"). `reading` gives the page the document as parts in plain words: the few things
# for the minutes before, each likely question with its answer, and the rest as short
# sections to fold. It reads any version of the document, so a prep written before this one
# reads as cleanly until it is remade.

# How the page names a section, where its own name is a word the person would not use.
READ_TITLES = {"Warm route": "People you know there", "Earlier stages": "Earlier rounds",
               "To rework": "To work on", "Notes": "Your notes",
               "Gaps and honest framing": "Gaps, and how to put them",
               "Money and eligibility": "Pay and right to work"}
# The order the page folds them in: what is most read the night before first.
READ_ORDER = ("Stories", "The company", "Who you are meeting", "The format", "Ask them",
              "What they have been told", "What the paper says", "Gaps and honest framing",
              "Money and eligibility", "Small talk", "Warm route", "Earlier stages",
              "To rework", "Notes")
# Read into other parts: the one screen, the answers and the notes on each question.
_READ_ELSEWHERE = ("On one screen", "Your answers", "Likely questions")
# Every line, whole: nothing in the prep is cut on its way to the page. It was cut at 20,000
# characters mid-word, then at 24 lines a section and 600 characters a line, kept to the
# first sentence, with no sign (the audit, 2026-11-03). A section folds; a big one reaches the
# page in parts (tools/page_db.py split).
_STAR_WORDS = {"S": "The situation", "T": "The task", "A": "What you did", "R": "The result",
               "Situation": "The situation", "Task": "The task", "Action": "What you did",
               "Result": "The result"}
_PLACEHOLDERS = (FOUND_EMPTY, NOTES_EMPTY, "- " + REWORK_EMPTY,
                 "- Nothing yet: each line you add here, with its source, stays.")
# What only Claude needs in a line written by an older version of this file: a command, a
# rule of its own instructions, an instruction to rebuild, a file to edit.
_CLAUDE_ONLY = re.compile(
    r"(?:Their answer is kept for every later employer|Nothing on file can supply the reasons|"
    r"If they ask for a draft instead|The employer-researcher keeps|, kept with `|, then this "
    r"is rebuilt|then this is rebuilt|rebuild (?:this )?with --|Add it: python3|"
    r"python3 tools/|`[^`]*\.py\b)[^\n]*$")
_RULE_REF = re.compile(r"\s*\((?:interview\.md [^)]*|rule \d+|/setup[^)]*|[\w./-]+\.(?:py|md|json|csv)"
                       r"(?: [A-Z_]+)?)\)")
_STATUS_CODE = re.compile(r"\s*\[([a-z]+(?:_[a-z]+)+)\]")
_FILE_WORD = re.compile(r"(?<![\w/:.])(?:[\w.-]+/)*[\w.-]+\.(?:md|json|csv|py|tex|txt)\b")
_PLURAL_S = re.compile(r"\b(\w+)\((e?s)\)")
_COUNTED = re.compile(r"\b(\d+) (\w+)\((e?s)\)")


def _file_words(name) -> str:
    """A file an older document named in its text, as the person knows it."""
    if re.search(r"(?:^|/)cv/|_CV_|_Resume_", name):
        return "your %s" % _noun()
    if re.search(r"cover_letter|Cover_Letter", name):
        return "your cover letter"
    if "outreach" in name:
        return "the note drafted to them"
    return source_words(name)


def plain_line(line) -> tuple:
    """(the words of one line of the document, as the page shows them, the employer's own
    link it cites or "") or ("", "") for a line that is Claude's alone (research still to do,
    a placeholder). No markdown, no source files, no commands, no status codes."""
    raw = str(line or "")
    if research_line(raw) or raw.strip() in _PLACEHOLDERS or raw.strip().startswith("<!--"):
        return "", ""
    s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", raw).strip()
    s = re.sub(r"^>\s*", "", s)
    link = ""
    for m in _SOURCE_IN.finditer(s):
        if re.match(r"https?://", m.group(2).strip(), re.I) and not link:
            link = m.group(2).strip()
    # The source goes from the page's line: "(source: x)" whole, "; source: x" inside a bracket.
    s = re.sub(r"\s*\(source: [^()]*\)", "", s)
    s = re.sub(r";\s*source: [^();]*(?=\))", "", s)
    s = re.sub(r"\(\s*\)", "", s)
    for old in prep.ASK_MARKS:
        s = s.replace(old, prep.ASK_MARK)
    s = s.replace(prep.RAW_MARK, "From your profile:")
    s = re.sub(r"^(?:Notes, not words to say|Notes only):\s*", "", s)
    s = re.sub(r"^Prepared:\s*", "Your prepared answer: ", s)
    s = re.sub(r"^From:\s*", "", s)
    s = re.sub(r"^Prepared:\s*", "Your prepared answer: ", s)
    s = re.sub(r"^Story:\s*", "Your story: ", s)
    s = _CLAUDE_ONLY.sub("", s)
    s = _RULE_REF.sub("", s)
    s = _STATUS_CODE.sub(lambda m: " (%s)" % status_words(m.group(1)), s)
    # Lines an older version wrote around a file name, said as what they meant.
    s = re.sub(r"^No draft\.json kept for this application, so what", "What", s)
    s = re.sub(r"^Read: ", "", s)
    s = re.sub(r"^Do not say: (?=(?:Do not|Don'?t|Never|Avoid)\b)", "", s)
    s = _FILE_WORD.sub(lambda m: _file_words(m.group(0)), s)
    s = re.sub(r"\b(your [a-z ]+), \1\b", r"\1", s)
    s = _COUNTED.sub(lambda m: ("one %s" % m.group(2)) if m.group(1) == "1"
                     else "%s %s%s" % (m.group(1), m.group(2), m.group(3)), s)
    s = _PLURAL_S.sub(lambda m: m.group(1) + m.group(2), s)
    s = re.sub(r"(?<!\.)\.\.(?!\.)", ".", s)
    s = re.sub(r"\*\*|__|`", "", s)
    s = re.sub(r"(?<!\w)\*(?!\s)([^*]+?)(?<!\s)\*(?!\w)", r"\1", s)
    s = " ".join(s.split()).strip()
    if s and s[-1] in ",;:":
        s = s[:-1].rstrip() + "."
    if s in (".", ":"):
        s = ""
    return s, link


def _read_section(title, lines) -> dict | None:
    """One section of the document as the page folds it: {key, title, items [{text, link,
    sub [text]}]}, or None when nothing in it is for the person."""
    items, cur, group = [], None, None
    for ln in lines:
        if not ln.strip():
            continue
        head = re.match(r"^#{3,6}\s+(.*)$", ln)
        if head:
            # A heading inside a section ("What you found out") holds the lines under it.
            label = plain_line(head.group(1))[0]
            group = {"text": label, "link": "", "sub": [], "head": True} if label else None
            if group:
                items.append(group)
            continue
        text, link = plain_line(ln)
        if not text:
            continue
        if title == "Ask them":
            text = re.sub(r"\s*\([^()]*\)$", "", text)
        if title == "To rework":
            # rework_entry's line, "<day>, <where>: "<question>": <note>", said the other way
            # round: the question, then what to change, then where it came from.
            m = re.match(r'^(\d{4}-\d{2}-\d{2}), ([^:]+): "(.+?)": (.*)$', text)
            if m:
                text = "%s %s (from %s, %s)" % (m.group(3), m.group(4), "your practice"
                                                if m.group(2) == "mock" else m.group(2),
                                                m.group(1))
        if title == "Stories":
            star = re.match(r"^(S|T|A|R|Situation|Task|Action|Result):\s*(.*)$", text)
            if star and cur is not None:
                cur["sub"].append("%s: %s" % (_STAR_WORDS[star.group(1)], star.group(2)))
                continue
            if re.match(r"^Use for:", text):
                continue        # the tags a question reaches a story by: Claude's, not the page's
            text = re.sub(r"\s*\((?:[a-z][^()]*)\)$", "", text)   # its theme, a tag
        indented = re.match(r"^\s{2,}[-*+]\s", ln)
        if group is not None:
            group["sub"].append(text)
            continue
        if indented and cur is not None:
            cur["sub"].append(text + (" (%s)" % _host(link) if link and title != "The company"
                                      else ""))
            continue
        cur = {"text": text, "link": link, "sub": []}
        items.append(cur)
    items = [i for i in items if not i.get("head") or i["sub"]]
    if not items:
        return None
    return {"key": re.sub(r"[^a-z]+", "_", title.lower()).strip("_"),
            "title": READ_TITLES.get(title, title), "items": items}


# What an older one screen said to answer with, in words that pointed at the document ("below",
# "(Your answers)"), as the page says it: None where the person's own answer is shown instead.
_OLD_CUES = ((r"^your summary, said your way.*$", "your summary, in your own words"),
             (r"^prepared answer, below$", "your prepared answer"),
             (r"^your answer, below$", ""), (r"^your answer$", ""),
             (r"^ask you first.*$", "your own reasons: Claude asks you first"),
             (r"^a hook below", "something true about them"),
             (r"^a gap with no framing yet.*$", "a gap: settle how you will put it"),
             (r"^no story yet: draft one$", "no story yet: Claude writes one"))


def _why_story(note) -> str:
    """A story note without how the story was chosen ("matched by its Use for tags", "mapped"):
    that is Claude's, not the person's."""
    return re.sub(r"\s*\((?:matched|mapped|as the last build|it carries the letter|chosen over)"
                  r"[^()]*(?:\([^()]*\)[^()]*)*\)", "", note)


def _cue(text) -> str | None:
    t = _text(text)
    for rx, words in _OLD_CUES:
        t = re.sub(rx, words, t, flags=re.I)
    t = re.sub(r"^story: ", "your story: ", t)
    return t or None


def _host(url) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", _text(url), re.I)
    return m.group(1) if m else ""


def _doc_parts(text) -> list:
    """[(title, lines)] of a document's "## " sections, in order."""
    return [(t, ls[1:]) for t, ls in _doc_sections(str(text or "").splitlines()) if t]


def reading(text, company="") -> dict | None:
    """The prep as the page reads it, in plain words, from any version of the document:
    {glance {assessing, hear, say [text], ask [text], money, careful [text], hooks [{text,
    link}]}, questions [{question, why, answer, draft, cue, checking, notes [text]}],
    sections [{key, title, items}], live}. `answer` is what the person wrote to say, `draft`
    true only where that answer still carries a draft's mark, `cue` what to answer with
    while it is unwritten. None for an empty document."""
    text = str(text or "")
    if not text.strip():
        return None
    shot = one_screen(text) or {}
    plain = lambda x: plain_line(x)[0]   # noqa: E731
    cues = {what_works._norm(q["question"]): q.get("answer") for q in shot.get("questions") or []}
    glance = {"assessing": plain(shot.get("assessing")) or None,
              "hear": plain(shot.get("hear")) or None,
              "say": [t for t in (plain(x["text"]) for x in shot.get("say") or []) if t],
              "ask": [t for t in (plain(x["text"]) for x in shot.get("ask") or []) if t],
              "money": plain(shot.get("money")) or None,
              "careful": [t for t in (plain(x["text"]) for x in (shot.get("do_not_say") or [])
                                      [:MAX_DO_NOT]) if t and not t.startswith("No claim in the room")],
              "hooks": [{"text": plain(x["text"]), "link": x.get("source") or ""}
                        for x in (shot.get("hooks") or [])[:HOOKS] if plain(x["text"])
                        and not plain(x["text"]).startswith(prep.NOT_RESEARCHED)]}
    for h in glance["hooks"]:
        if not re.match(r"https?://", h["link"], re.I):
            h["link"] = ""
    parts = _doc_parts(text)
    found = dict(parts)
    # A document from before the one screen said what to say and what to ask: the first
    # questions of its own Ask them, and nothing invented.
    if not glance["ask"] and found.get("Ask them"):
        asks = [plain_line(ln)[0] for ln in found["Ask them"] if ln.startswith("- ")]
        asks = [re.sub(r"\s*\([^()]*\)$", "", a) for a in asks if a]
        glance["ask"] = [a for a in asks if a.endswith("?")][:MAX_ASK_FIRST]
    blocks = _answer_blocks(found.get("Your answers") or [])
    notes_of = {}
    for ln in found.get("Likely questions") or []:
        if ln.startswith("- **Q.** "):
            head, _inside = _last_parens(ln[len("- **Q.** "):])
            cur = notes_of.setdefault(what_works._norm(_plain(head)), [])
        elif re.match(r"^\s{2,}-\s", ln) and notes_of:
            t = plain(ln)
            if t and not re.match(r"^(?:Checking |Your own answer is under)", t):
                cur.append(t)
    # What each question checks: the line Your answers writes under its heading.
    checks, at = {}, None
    for ln in found.get("Your answers") or []:
        m = re.match(r"^### (.*)$", ln)
        if m:
            at = what_works._norm(m.group(1).strip())
        elif at and ln.startswith(INTENT_MARK):
            checks[at] = plain(re.sub(r"^%s\s*" % re.escape(INTENT_MARK), "", ln))
    questions = []
    for q in practice(text)["questions"]:
        key = what_works._norm(q["question"])
        body = (blocks.get(key) or ("", []))[1]
        froms = [plain(ln) for ln in body if ln.lstrip().startswith("- From:")]
        notes_of[key] = [_why_story(n) for n in notes_of.get(key, [])]
        froms = [_why_story(n) for n in froms]
        notes = [n for n in froms + notes_of.get(key, []) if n]
        notes = list(dict.fromkeys(notes))
        cue = _cue(plain(cues.get(key) or ""))
        if q["answer"]:
            # Written: what it was said from is history, and a reason to ask is answered.
            notes = [n for n in notes if not n.startswith((prep.ASK_MARK, "Your prepared answer",
                                                           "From your profile"))]
        questions.append({"question": q["question"], "why": plain(q["why"] or "") or None,
                          "answer": q["answer"], "draft": bool(q["answer"]) and q["draft"],
                          "cue": cue, "checking": checks.get(key) or None,
                          "notes": notes})
    sections = []
    order = [t for t in READ_ORDER if t in found] + [t for t, _ls in parts if t not in READ_ORDER
                                                     and t not in _READ_ELSEWHERE]
    for title in order:
        got = _read_section(title, found[title])
        if got:
            if title == "The company" and company:
                got["title"] = "About %s" % company
            sections.append(got)
    if not glance["say"]:
        glance["say"] = _say_from(shot, sections, glance["hooks"])
    return {"glance": glance, "questions": questions, "sections": sections,
            "live": LIVE_LINE in text}


def _say_from(shot, sections, hook_list) -> list:
    """What to say, for a document built before its one screen said it: the result of the
    story its first question is answered with, and the first fact about the employer."""
    out = []
    stories = next((s["items"] for s in sections if s["key"] == "stories"), [])
    titles = [re.sub(r"^story: ", "", _text(q.get("answer")), flags=re.I)
              for q in shot.get("questions") or [] if re.match(r"(?i)story: ", _text(q.get("answer")))]
    for title in titles + [i["text"] for i in stories]:
        st = next((i for i in stories if i["text"].lower() == title.lower()), None)
        result = next((x.split(": ", 1)[1] for x in (st or {}).get("sub") or []
                       if x.startswith("The result: ")), "")
        if result:
            out.append("Lead with your strongest result: %s" % _sentence(result))
            break
    if hook_list:
        out.append("Why them: %s" % _sentence(hook_list[0]["text"]))
    return out


def remove_rework(company, role, stage, line) -> bool:
    """Take one line back off To rework (the undo of `add_rework`). True when it was there."""
    folder = docpaths.app_folder(company, role)
    path = os.path.join(folder, LIVING)
    if not os.path.exists(path):
        path = os.path.join(folder, pack_name(stage))
    text = _read(path)
    kept = _rework_lines(text)
    if line not in kept:
        return False
    m = re.search(r"^## To rework\s*$", text, re.M)
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)
    end = m.end() + (nxt.start() if nxt else len(body))
    rest = [k for k in kept if k != line]
    text = text[:m.end()] + "\n\n" + ("\n".join(rest) if rest else "- " + REWORK_EMPTY) + "\n\n" \
        + text[end:].lstrip()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.rstrip() + "\n")
    return True


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


def _clock(value) -> str:
    """A time as HH:MM (14:00, 2pm, 9.30am all read), or argparse's own error."""
    if not value:
        return ""
    got = what_works.clock(value)
    if got:
        return got
    raise argparse.ArgumentTypeError("%r is not a time: write it like 14:00 or 2pm" % value)


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
    pr.add_argument("--posting", default="", help="the posting: a file holding its text, or its "
                                                  "link; without it the folder says it is not "
                                                  "held yet")
    pr.add_argument("--today", type=_day)
    for s in (p, pr):
        s.add_argument("--time", default="", type=_clock, help="its time: 14:00, 2pm or 9.30am")
        s.add_argument("--zone", default="", help="a zone the invite gives beside the time "
                                                  "(EST), when it is not the person's own")
    bk = sub.add_parser("book", help="save an interview's day and time on its own record "
                                     "(outcome.md), however it was given: said in a chat, an "
                                     "invite, a message or a note")
    bk.add_argument("company")
    bk.add_argument("--role", default="")
    bk.add_argument("--stage", default="", help="as outcome.md names it; default the next booked")
    bk.add_argument("--date", default="", type=_day, help="default: the day it is booked for")
    bk.add_argument("--time", default="", type=_clock, help="14:00, 2pm or 9.30am")
    bk.add_argument("--zone", default="", help="the time zone, as its name where you know it "
                                               "(America/Toronto), else the invite's word (EST), "
                                               "when it is not the person's own")
    bk.add_argument("--with", dest="with_", default="")
    bk.add_argument("--today", type=_day)
    for s_ in (p, pr, bk):
        s_.add_argument("--minutes", type=int, default=0,
                        help="how long it lasts, as the invite says (45); never guessed")
        s_.add_argument("--due", action="store_true",
                        help="something to finish by the day (an online test, a case study), "
                             "not a meeting at a time")
    tm = sub.add_parser("times", help="every booked interview whose time is said in a note or "
                                      "a message and not yet on its record: saved there")
    tm.add_argument("--company", default="")
    tm.add_argument("--today", type=_day)
    po = sub.add_parser("postings", help="give every process folder that has none a "
                                         "job_posting.md (registered before process wrote one)")
    po.add_argument("--today", type=_day)
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
    mo = sub.add_parser("motive", help="keep the person's own answer to a motivation question "
                                       "(why leaving, the moves, why this employer, where next) "
                                       "in profile/07-interview-prep.md, for every employer")
    mo.add_argument("question")
    mo.add_argument("--answer", required=True, help="their words, as they said them")
    mo.add_argument("--use-for", default="", help="other wordings it answers, ;-separated")
    mo.add_argument("--suits", default="", help="kinds of employer it fits, comma-separated")
    mo.add_argument("--not-for", dest="not_for", default="",
                    help="kinds of employer it must not be said to, comma-separated")
    fb = sub.add_parser("feedback", help="check mock-interview feedback before it is shown: "
                                         "every point quotes their own words, and the band "
                                         "is Strong, Solid or Gap")
    fb.add_argument("--question", required=True)
    said = fb.add_mutually_exclusive_group(required=True)
    said.add_argument("--answer", help="their answer, word for word as they said or typed it")
    said.add_argument("--answer-file", help="a file holding their answer, word for word")
    fb.add_argument("--band", required=True, help=", ".join(BANDS))
    fb.add_argument("--point", nargs=2, action="append", default=[],
                    metavar=("THEIR_WORDS", "NOTE"),
                    help="their own words, then what worked or what to sharpen; repeatable")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "feedback":
            answer = a.answer if a.answer is not None else _read(a.answer_file)
            if not _text(answer):
                raise ValueError("no answer to check the quotes against: give their words "
                                 "with --answer or --answer-file")
            problems = feedback_problems(answer, a.band, a.point)
            if problems:
                print("feedback not shown, because:", file=sys.stderr)
                for why in problems:
                    print("- " + why, file=sys.stderr)
                return 1
            print("\n".join(feedback_lines(a.question, a.band, a.point)))
            return 0
        if a.cmd == "motive":
            split = lambda v, sep: [x.strip().lower() for x in v.split(sep) if x.strip()]  # noqa: E731
            path = write_motive(a.question, a.answer, [x.strip() for x in a.use_for.split(";")
                                                       if x.strip()],
                                split(a.suits, ","), split(a.not_for, ","))
            print("kept in %s: every later pack, at every employer, uses it and checks it "
                  "against the employer" % _repo_rel(path))
            return 0
        if a.cmd == "times":
            got = take_times(today=a.today, company=a.company)
            for g in got:
                print(saved_line(g))
            if not got:
                print("times: nothing to save: every booked interview has its time on its "
                      "record, or no note or message gives one")
            return 0
        if a.cmd == "book":
            import open_actions
            tracker = what_works._csv(person.state("job_search_tracker.csv"))
            row = _row(a.company, a.role, tracker,
                       state.load_contacts(person.state("network_contacts.csv")))
            company, role = _text(row.get("company")) or a.company, _text(row.get("role"))
            today = a.today or dt.date.today().isoformat()
            _folder, _files, stages = open_actions.stages(row)
            named = [s for s in stages if s["label"].lower() == _text(a.stage).lower()]
            stage = named[0] if named else ({} if _text(a.stage) else next_stage(stages, today))
            label, date = _text(a.stage) or _text(stage.get("label")), a.date or _text(
                stage.get("date"))
            if not (label and date):
                raise ValueError("no interview is booked at %s yet: give it with --stage and "
                                 "--date" % company)
            if _text(a.zone) and not zone_name(a.zone):
                raise ValueError("%r is not a time zone this can place: give its name, like "
                                 "America/Toronto or Europe/London" % a.zone)
            folder = docpaths.app_folder(company, role)
            line = record_stage(folder, company, role, label, date, a.with_, today=today,
                                time=a.time, zone=a.zone, minutes=a.minutes, due=a.due)
            print("saved in %s/outcome.md: %s" % (_rel(folder), line))
            print("The page shows it once it is brought up to date (python3 tools/app.py view).")
            return 0
        if a.cmd == "postings":
            done = missing_postings()
            for company, role, folder in done:
                write_posting(folder, company, role, today=a.today)
                print("written: %s/job_posting.md" % _rel(folder))
            print("postings: %d process folder(s) given a job_posting.md" % len(done))
            return 0
        if a.cmd == "process":
            row, folder, added = register_process(a.company, a.contact, a.role, a.stage, a.date,
                                                  a.with_, today=a.today, posting=a.posting,
                                                  time=a.time, zone=a.zone, minutes=a.minutes,
                                                  due=a.due)
            print("%s: %s at %s, led by %s; its folder is %s.\n"
                  % ("registered" if added else "already registered", row["role"], row["company"],
                     row["contact_person"], _rel(folder)))
            # One command from a booked call to its document: the prep is built and kept now.
            ctx = gather(row["company"], row["role"], a.stage, a.date, a.with_, a.today,
                         format_=a.format_)
            if not _show(ctx, write=True):
                return 1
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
            path = os.path.join(docpaths.app_folder(_text(row.get("company")),
                                                    _text(row.get("role"))), LIVING)
            if not os.path.exists(path):
                print("interview_pack: no %s yet: build it with pack --write" % _rel(path))
                return 1
            found = check(path)
            for q, why in found:
                print("- %s: %s" % (q, why))
            todo = [q for q, b in _answer_blocks(_owned(_read(path)).get("Your answers")).values()
                    if not spoken(b)]
            held = failures(found)
            research = sum(1 for q, _w in held if q == "Research")
            asks = sum(1 for q, _w in held if q == "Ask")
            drafts = len(found) - len(held)
            answers = len(held) - research - asks
            print("; ".join(x for x in (
                "%d question(s) to ask you first: your own reasons" % asks if asks else "",
                "%d answer(s) not fit to say yet" % answers if answers else "",
                "%d piece(s) of research still to do" % research if research else "",
                "%d draft(s) for you to confirm, shown as drafts (%s)" % (drafts, DRAFT_TODO)
                if drafts else "")
                if x) + "." if found else "Every answer written is fit to say aloud.")
            if todo and not held:
                print("Still to write, beyond the first five: %d." % len(todo))
            if not held:
                # Checked after a hand edit, the copy to send is made again from it: it
                # was the version before the edit, and nothing said so (2026-10-25).
                _send_line(path)
            return 1 if held else 0
        if a.cmd == "asked":
            company, role = a.company, a.role
            if not _text(role):
                # The process's own row names the role, as check and rework find it; a
                # question kept with no role was never matched to its stage's pack again.
                try:
                    row = _row(a.company, "", what_works._csv(
                        person.state("job_search_tracker.csv")),
                        state.load_contacts(person.state("network_contacts.csv")))
                    company = _text(row.get("company")) or company
                    role = _text(row.get("role"))
                except LookupError as exc:
                    if "name the role" in str(exc):
                        raise
                    print("no application at %s, so no role is recorded with it: --role "
                          "names one" % a.company)
            path = add_asked(company, role, a.stage, a.question, a.story, a.landed,
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
        if a.write and _text(a.stage) and _text(a.date):
            # The stage and its day go on the record first, so the pack is built from it.
            tracker = what_works._csv(person.state("job_search_tracker.csv"))
            row = _row(a.company, a.role, tracker,
                       state.load_contacts(person.state("network_contacts.csv")))
            company, role = _text(row.get("company")) or a.company, _text(row.get("role"))
            folder = docpaths.app_folder(company, role)
            if os.path.isdir(folder):
                booked = record_stage(folder, company, role, a.stage, a.date, a.with_,
                                      today=a.today, time=a.time, zone=a.zone,
                                      minutes=a.minutes, due=a.due)
                if booked:
                    print("booked in %s/outcome.md: %s" % (_rel(folder), booked))
        ctx = gather(a.company, a.role, a.stage, a.date, a.with_, a.today, story_map,
                     format_=a.format_)
        if not _show(ctx, write=a.write):
            return 1
    except (LookupError, ValueError, OSError) as exc:
        print("interview_pack: %s" % exc, file=sys.stderr)
        return 1
    return 0


def _show(ctx, write=False) -> bool:
    """Print the living document as a rebuild writes it (every line the person wrote kept),
    and with `write`, write it (`_keep`). False when it was not written: a line of theirs
    would have been lost, or the document there is one they wrote by hand, said in a line.
    Without `write` that is only a note: the pack is shown as the tool builds it."""
    try:
        if write:
            path = write_pack(ctx)
            text = _read(path)
        else:
            text, _left = rebuilt(ctx)
    except WouldLose as exc:
        sys.stdout.write(pack_markdown(ctx))
        print("interview_pack: %s%s" % ("" if write else "if written: ", exc), file=sys.stderr)
        return not write
    sys.stdout.write(text)
    if write:
        _report(ctx, path)
    return True


def _keep(ctx) -> None:
    """Write the living document and say what is left before it goes to the person."""
    _report(ctx, write_pack(ctx))


def _send_line(path) -> None:
    """The copy to send, named for whose it is (tools/shown.py): the kept file's own name is
    the same for every employer."""
    try:
        import shown
        print("send: %s (this copy, never the file above: its name says whose it is)"
              % shown.copy(path))
    except Exception as exc:  # noqa: BLE001  the document is written; only its copy failed
        print("send: no named copy (%s); send %s" % (exc, _rel(path)))


def _report(ctx, path) -> None:
    """What is left before the document just written goes to the person."""
    print("\nwritten: %s" % _rel(path))
    _send_line(path)
    left = ctx.get("kept_from_before") or []
    if left:
        print("kept from the version before this one: %d line(s) this tool no longer writes "
              "are at the end of Notes, under \"%s\". Read them: move any the person wrote "
              "where it belongs, delete the rest, then build again." % (len(left),
                                                                     LEFTOVER_HEAD[4:]))
    left = check(path)
    research = [w for q, w in left if q == "Research"]
    for line in research:
        print("research first: %s" % line)
    if research:
        # How what is found is kept, said to Claude here and never in the person's document
        # (2026-11-03: the document carried these commands to a person minutes before a call).
        print("  keep it: the employer, its teams (company_research `%s`) and how it runs a "
              "round (`interview_process`, or `%s` when nothing is public) with the "
              "employer-researcher; an interviewer's public work with python3 "
              "tools/network/reading.py add <id> --name \"<name>\" --company \"%s\" (never a "
              "people-search site); then build again" % (TEAMS_KEY, NOT_FOUND_KEY,
                                                         ctx["company"]))
    asks = [w for q, w in left if q == "Ask"]
    for line in asks:
        print("ask the person first, once, in the plain words the document gives: %s" % line)
    if asks:
        print("  keep each answer for every later employer: python3 tools/interview_pack.py "
              "motive \"<the question>\" --answer \"<their words>\" [--suits <kinds> --not-for "
              "<kinds>], then build again; asked for a draft instead, write it under the "
              "question marked as one (interview.md rule 2)")
    drafts = [w for q, w in left if q == DRAFT]
    if drafts:
        print("drafts they asked for, to show them as drafts: %d (%s): %s"
              % (len(drafts), DRAFT_TODO, "; ".join(drafts)))
    unfit = len(left) - len(research) - len(asks) - len(drafts)
    if unfit:
        print("not yet fit to say: %d answer(s); write them in the document as you would say "
              "them, then `interview_pack.py check \"%s\"`" % (unfit, ctx["company"]))


if __name__ == "__main__":
    raise SystemExit(main())
