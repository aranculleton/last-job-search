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
import csv
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
import learned  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import profile_facts  # noqa: E402
import screening_answers  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import untrusted  # noqa: E402
import what_works  # noqa: E402
from company_key import key as company_key  # noqa: E402

ROOT = os.path.dirname(_HERE)
GUIDES = os.path.join(ROOT, ".claude", "skills", "job-application-assistant")
APP_GUIDE = os.path.join(GUIDES, "07-interview-prep.md")
APP_EVALUATION = os.path.join(GUIDES, "04-job-evaluation.md")
STORIES_FILE = "07-interview-prep.md"

SECTIONS = ("On one screen", "Likely questions", "Stories", "What the paper says",
            "Gaps and honest framing", "Money and eligibility", "The company", "Ask them",
            "Warm route", "Earlier stages", "To rework")

# One screen is what is read in the minutes before: five questions, three hooks,
# one money line, four things not to say. The detail below is for the night before.
ONE_SCREEN_QUESTIONS = 5
HOOKS = 3
MAX_DO_NOT = 4
MAX_QUESTIONS = 10
MAX_REQUIREMENTS = 3
MAX_FORM_LINES = 8
MAX_NOTES = 8
MAX_ASK = 6
MAX_NEVER_SAY = 5
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
               "What is your notice period?"),
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
        out.append({"question": heading.strip("\"“” "), "answer": answer,
                    "confirm": confirm, "source": _repo_rel(path)})
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

def _row(company, role, tracker) -> dict:
    """The tracker row this pack is for: the employer's, the role's, live first."""
    k = company_key(company)
    rows = [r for r in tracker if k and company_key(r.get("company")) == k]
    if role:
        rows = [r for r in rows if throttle._same_title(role, r.get("role"))]
    live = [r for r in rows if _text(r.get("status")).lower() not in throttle.FINAL]
    pick = live or rows
    if not pick:
        raise LookupError("no application at %r%s in the tracker: /outcome %s registers one"
                          % (company, " for %r" % role if role else "", company))
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


def _notes(text) -> list:
    """The lines under outcome.md's Notes heading: the person's own record."""
    m = re.search(r"^##\s*Notes\s*$", str(text or ""), re.M | re.I)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^##\s", body, re.M)
    body = body[:nxt.start()] if nxt else body
    return [_text(re.sub(r"^\s*[-*]\s+", "", ln)) for ln in body.splitlines()
            if _text(ln) and not ln.strip().startswith("<")]


def _next_stage(stages) -> dict:
    """The stage this pack is for, when none is named: the next one booked, else the next undone."""
    booked = [s for s in stages if s["scheduled"] and not s["done"]]
    if booked:
        return booked[0]
    done = [i for i, s in enumerate(stages) if s["done"]]
    after = stages[(done[-1] + 1) if done else 0:]
    return after[0] if after else {}


def gather(company, role="", stage="", date="", with_="", today=None, story_map=None,
           tracker=None, contacts=None, threads=None) -> dict:
    """Everything the pack is built from, read once."""
    root = person.state()
    today = _text(today) or dt.date.today().isoformat()
    tracker = what_works._csv(os.path.join(root, "job_search_tracker.csv")) if tracker is None \
        else tracker
    row = _row(company, role, tracker)
    company, role = _text(row.get("company")) or company, _text(row.get("role")) or role
    folder = outreach.app_folder(company, role)
    outcome = _read(os.path.join(folder, "outcome.md"))
    stages = what_works.outcome_stages(outcome)
    if not stage:
        # Nothing on record yet means the first conversation, which is a screen
        # at nearly every employer; /interview asks, and passes --stage when not.
        found = _next_stage(stages)
        stage = found.get("label") or "Phone screen"
        date, with_ = date or found.get("date", ""), with_ or found.get("with", "")
    else:
        same = [s for s in stages if s["label"].lower() == stage.lower()]
        if same:
            date, with_ = date or same[0]["date"], with_ or same[0]["with"]
    posting = untrusted.unfence(_read(os.path.join(folder, "job_posting.md")))
    contacts = state.load_contacts(os.path.join(root, "network_contacts.csv")) \
        if contacts is None else contacts
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
        "rework": _rework_lines(_read(os.path.join(folder, pack_name(stage)))),
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
        "here": [(r["question"], "asked here before (%s, %s)" % (_text(r.get("stage")) or "a stage",
                                                              _text(r.get("date")) or "undated"),
                  bank_src, {}) for r in ctx["bank"]
                 if company_key(r.get("company")) == k and _text(r.get("question"))],
        "again": [],
        "stage": [(q.format(company=company), "what %s usually asks"
                   % what_works.STEP_WORDS.get(step, "an interview"), "the stage", {})
                  for q in STAGE_QUESTIONS.get(step, ())],
        "gaps": [], "reqs": [],
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
            group["reqs"].append(("Tell me about your experience with %s." % req,
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
        if company_key(r.get("company")) != k and what_works.stage_step(r.get("stage")) == step:
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
        "screen": ["map", "here", stage[:3], group["gaps"][:1], stage[3:], "reqs", group["gaps"][1:],
                   "again"],
        "technical": ["map", "here", "reqs", "gaps", "stage", "again"],
        "final": ["map", "here", stage[:1], group["gaps"][:1], stage[1:], "reqs",
                  group["gaps"][1:], "again"],
        "offer": ["map", "here"],
    }[step if step in STAGE_QUESTIONS else "technical"]
    for part in order:
        for question, why, source, extra in (group[part] if isinstance(part, str) else part):
            add(question, why, source, **extra)
    return out[:MAX_QUESTIONS]


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
    why_us = bool(re.search(r"^why %s" % re.escape(ctx["company"]), q, re.I))
    if item.get("framing"):
        lines.append("Say: %s (source: %s)" % (item["framing"], item["source"]))
    if item.get("evidence"):
        lines.append("What the letter answered it with: %s (source: %s)"
                     % (item["evidence"], item.get("evidence_source") or item["source"]))
    if re.search(r"salary|pay|compensation", q, re.I):
        fq, fa = _form_value(ctx, r"salary|pay|compensation")
        if fa:
            lines.append("The form said: %s (source: %s/screening_answers.md). Say the same band."
                         % (fa, folder))
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
        lines.append("%s (source: %s)" % (facts["summary"], prof))
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
        return {"kind": "say", "short": "a hook below, and what the letter told them",
                "lines": lines}
    if item.get("gap") and not item.get("framing"):
        lines.append("No framing recorded (profile skills.py BRIDGES): write one before the "
                     "interview. Say plainly what you do not hold, then the nearest true thing; "
                     "never claim it.")
        return {"kind": "none", "short": "a gap with no framing yet: write one (Gaps)",
                "lines": lines}
    if lines:
        first = re.sub(r" \(source: .*$", "", lines[0]).replace("The form said: ", "the form said ")
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
    out = []
    for g in ctx["facts"].get("gaps") or []:
        if g["framing"]:
            out.append("- %s. Say: %s (source: %s)" % (g["gap"], g["framing"], g["source"]))
        else:
            out.append("- %s. No framing recorded: write one before the interview, never on "
                       "the day (source: %s)" % (g["gap"], g["source"]))
    for b in ctx["facts"].get("blockers") or []:
        out.append("- BLOCKER: %s. No framing fixes this. (source: %s)"
                   % (b, prep._profile_source(ctx["facts"])))
    return out


def _band():
    """(target line, floor) from the salary table, or ("", None) when there is none."""
    try:
        floor, low, high = screening_answers.salary_band()
    except screening_answers.MissingFact:
        return "", None
    cur = prep._CURRENCY_CODE
    return ("%s%s to %s" % (cur + " " if cur else "", "{:,}".format(low), "{:,}".format(high)),
            floor)


def _offer_lines() -> list:
    """Total compensation and the caveats, from the person's evaluation rubric."""
    mine = _read(screening_answers.EVALUATION)
    out = []
    for text, src in ((mine, _repo_rel(screening_answers.EVALUATION)),
                      (_read(APP_EVALUATION), _repo_rel(APP_EVALUATION))):
        m = re.search(r"Always report total compensation[^\n]*", text)
        if m:
            out.append("- %s (source: %s)" % (_text(m.group(0)), src))
            break
    m = re.search(r"Two honest caveats[^\n]*\n((?:\s*\d+\.\s[^\n]*\n?)+)", mine)
    for item in re.findall(r"^\s*\d+\.\s+(.*)$", m.group(1), re.M) if m else ():
        if "[PLACEHOLDER" not in item:
            out.append("- Caveat: %s (source: %s)" % (_text(item.replace("**", "")),
                                                      _repo_rel(screening_answers.EVALUATION)))
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
                                       _repo_rel(screening_answers.EVALUATION)))
    else:
        lines.append("- Your band: %s, no salary table in %s. Ask their range rather than quote "
                     "a number you cannot source." % (prep.NOT_RESEARCHED,
                                                       _repo_rel(screening_answers.EVALUATION)))
    lines.append("- Market band:")
    lines += ["  " + ln for ln in prep.comp_band(
        ctx["role"], "", "", prep._comp_sources(ctx["research"], ctx["row"]))]
    try:
        sponsor = "needed" if screening_answers.requires_sponsorship() else "not needed"
        lines.append("- Sponsorship: %s. Say it plainly, with no caveat. (source: %s)"
                     % (sponsor, prep.PROFILE_SOURCE))
    except screening_answers.MissingFact:
        pass
    if ctx["step"] == "offer":
        lines += _offer_lines()
    _q, said = _form_value(ctx, r"salary|pay|compensation")
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


def warm_lines(ctx) -> list:
    """Who is already talking to them, and who of the interviewers is already known."""
    k = company_key(ctx["company"])
    here = [c for c in ctx["contacts"] if company_key(c.get("company")) == k]
    names = " ".join(_text(x).lower() for x in [ctx["with"]] + [s["with"] for s in ctx["stages"]])
    out, referrer = [], None
    for c in here:
        cid = _text(c.get("contact_id"))
        status = state.effective_status(c, state.threads_for(ctx["threads"], cid))
        name = state.person_name(c.get("name")) or _text(c.get("name"))
        title = ", " + _text(c.get("title")) if _text(c.get("title")) else ""
        if len(name) > 3 and name.lower() in names:
            known = ["documents/network/%s/%s" % (cid, f) for f in ("prep.md", "reading.json")
                     if cid and os.path.exists(person.state("documents", "network", cid, f))]
            out.append("- %s%s is interviewing you and is in your contact book [%s]%s. "
                       "(source: %s)" % (name, title, status, ": reuse " + " and ".join(known)
                                         if known else "", prep.CONTACTS_SOURCE))
        elif status == "referral_in_progress" or _text(c.get("route")).startswith("referral"):
            referrer = referrer or name
            out.append("- %s%s put you forward [%s]. Tell them the interview is booked, and "
                       "thank them after it. (source: %s)" % (name, title, status,
                                                              prep.CONTACTS_SOURCE))
        elif status in throttle.RESPONDED:
            out.append("- %s%s is already talking to you [%s]: tell them it is booked. "
                       "(source: %s)" % (name, title, status, prep.CONTACTS_SOURCE))
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
    out += ["- %s (source: %s)" % (n, src) for n in _notes(ctx["outcome"])[:MAX_NOTES]]
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
    return [ln.rstrip() for ln in body.splitlines()
            if ln.strip().startswith("-") and REWORK_EMPTY not in ln]


# ---------------------------------------------------------------- the pack

def _section(title, lines, empty) -> list:
    return ["## " + title, ""] + (list(lines) if lines else ["- " + empty]) + [""]


def pack_markdown(ctx, never_say=None) -> str:
    """The whole pack, one screen first. `never_say` defaults to the person's phrases."""
    banned = (lambda text: [m.group(0) for _p, rx in never_say for m in rx.finditer(text)]) \
        if never_say is not None else learned.dislikes
    questions = likely_questions(ctx)
    answered = [(q, answer_for(q, ctx)) for q in questions]
    one_money, money_lines = money(ctx)
    hook_facts = hooks(ctx)
    donts = do_not_say(ctx, never_say)

    when = ", ".join(x for x in (ctx["date"], "with " + ctx["with"] if ctx["with"] else "") if x)
    lines = ["# Interview pack: %s at %s, %s" % (ctx["role"], ctx["company"], ctx["stage"]), "",
             "%sWritten %s. One screen first, the detail after; every fact carries its source, "
             "and anything unsourced was left out." % (when + ". " if when else "", ctx["today"]), ""]

    screen = ["**Likely questions, and what to answer with**"]
    screen += ["%d. %s -> %s" % (i, q["question"], a["short"])
               for i, (q, a) in enumerate(answered[:ONE_SCREEN_QUESTIONS], 1)]
    screen += ["", "**Hooks**"]
    letter = _text((ctx["draft"] or {}).get("_path"))
    screen += ["- %s%s (source: %s)" % ("The letter told them: " if f.source == letter else "",
                                         prep._short(f.value, 110), f.source)
               for f in hook_facts[:HOOKS]] or ["- %s: nothing researched to hang \"why us\" on."
                                                % prep.NOT_RESEARCHED]
    screen += ["", "**Money:** %s." % one_money, "", "**Do not say**"]
    screen += donts[:MAX_DO_NOT]
    lines += _section(SECTIONS[0], prep._flag_banned(screen, banned), "")

    detail = []
    for q, a in answered:
        detail.append("- **Q.** %s (%s; source: %s)" % (q["question"], q["why"], q["source"]))
        detail += ["  - " + ln for ln in a["lines"]]
    lines += _section(SECTIONS[1], prep._flag_banned(detail, banned),
                      "No questions: nothing on file to anticipate.")
    lines += _section(SECTIONS[2], prep._flag_banned(_story_lines(ctx), banned),
                      "No STAR stories in profile/%s: write three or four before the interview "
                      "(/setup --section history)." % STORIES_FILE)
    lines += _section(SECTIONS[3], paper_lines(ctx), "Nothing on file about what was sent.")
    lines += _section(SECTIONS[4], prep._flag_banned(gap_lines(ctx), banned),
                      "No gap the posting names: lead with the matches.")
    lines += _section(SECTIONS[5], money_lines, prep.NOT_RESEARCHED)
    company = prep._company_lines(ctx["research"], ctx["today"])
    stale = prep._stale_line(ctx["research"], ctx["today"]) if company else ""
    lines += _section(SECTIONS[6], company + ([stale] if stale else []),
                      "%s. Research it before the interview (interview.md Step 2)."
                      % prep.NOT_RESEARCHED)
    lines += _section(SECTIONS[7], prep._flag_banned(ask_lines(ctx), banned),
                      "Nothing researched to anchor a question on.")
    lines += _section(SECTIONS[8], warm_lines(ctx), "Nobody in the contact book at %s."
                      % ctx["company"])
    lines += _section(SECTIONS[9], earlier_lines(ctx), "No earlier stage on record.")
    lines += _section(SECTIONS[10], ctx["rework"], REWORK_EMPTY)
    return "\n".join(lines).rstrip() + "\n"


def write_pack(ctx, never_say=None) -> str:
    """Write the pack beside the application and return its path. Rework notes carry over."""
    path = os.path.join(ctx["folder"], pack_name(ctx["stage"]))
    os.makedirs(ctx["folder"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(pack_markdown(ctx, never_say))
    return path


# ---------------------------------------------------------------- what came of it

def add_asked(company, role, stage, question, story="", landed="", note="", date=None) -> str:
    """One question an interview asked, into the bank. Returns the bank's path."""
    landed = _text(landed).lower()
    if landed and landed not in what_works.LANDED:
        raise ValueError("landed is one of %s, or blank" % ", ".join(what_works.LANDED))
    if not _text(question):
        raise ValueError("a question to record is needed")
    path = person.state(*what_works.BANK)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=what_works.BANK_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"date": _text(date) or dt.date.today().isoformat(), "company": _text(company),
                    "role": _text(role), "stage": _text(stage), "question": _text(question),
                    "story": _text(story), "landed": landed, "note": _text(note)})
    return path


def add_rework(company, role, stage, question, note, date=None, where="mock") -> str:
    """An answer to work on, appended to the stage's pack under To rework."""
    folder = outreach.app_folder(company, role)
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

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="build the pack for one stage")
    p.add_argument("company")
    p.add_argument("--role", default="")
    p.add_argument("--stage", default="", help="as outcome.md names it; default the next booked")
    p.add_argument("--date", default="")
    p.add_argument("--with", dest="with_", default="", help="who it is with, name or title")
    p.add_argument("--map", default="", help="JSON {question: story title} the session mapped")
    p.add_argument("--write", action="store_true", help="save it beside the application")
    p.add_argument("--today")
    q = sub.add_parser("asked", help="record a question an interview asked")
    r = sub.add_parser("rework", help="add an answer to work on to the stage's pack")
    for s in (q, r):
        s.add_argument("--company", required=True)
        s.add_argument("--role", default="")
        s.add_argument("--stage", required=True)
        s.add_argument("--question", required=True)
        s.add_argument("--note", default="")
        s.add_argument("--date")
    q.add_argument("--story", default="")
    q.add_argument("--landed", default="", choices=("",) + what_works.LANDED)
    r.add_argument("--where", default="mock", help="mock, or the real interview")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "asked":
            print("added to %s" % _rel(add_asked(a.company, a.role, a.stage, a.question,
                                                  a.story, a.landed, a.note, a.date)))
            return 0
        if a.cmd == "rework":
            print("added to %s" % _rel(add_rework(a.company, a.role, a.stage, a.question,
                                                   a.note, a.date, a.where)))
            return 0
        story_map = json.load(open(a.map, encoding="utf-8")) if a.map else {}
        ctx = gather(a.company, a.role, a.stage, a.date, a.with_, a.today, story_map)
    except (LookupError, ValueError) as exc:
        print("interview_pack: %s" % exc, file=sys.stderr)
        return 1
    sys.stdout.write(pack_markdown(ctx))
    if a.write:
        print("\nwritten: %s" % _rel(write_pack(ctx)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
