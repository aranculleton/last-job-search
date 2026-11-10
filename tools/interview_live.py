#!/usr/bin/env python3
"""The live prep for one interview: its parts in the order the interview runs, built and
checked here, drawn by the page.

The living document (`interview_prep.md`, tools/interview_pack.py) is the record: sourced,
kept across rebuilds, read the night before. The live prep is what the person holds in the
minutes before and practises from: the interview's own shape (a recruiter screen, a hiring
manager's interview, a technical round or a take-home presented back, a consulting firm's
case with its personal experience interview, a panel, a final), and in each part what to say
first, the questions it is likely to bring with who asks them, a Simple and a Detailed answer
to each, the follow-ups behind them by who asks, the stories they come from, the words of the
role and the employer explained in the employer's own terms, the questions to ask them, the
time each part takes, and the notes that are for the person alone.

Who writes what. The engine writes everything a record holds: the shape and its timing, the
questions and which story each is answered with (`interview_pack.likely_questions`,
`plan_stories`), the stories as the profile tells them, the questions to ask, the pay, notice
and place to say, what not to say, the gaps and how to put them, and the questions they are
known to ask. Claude writes the words to be said (the openings, every answer, the follow-ups,
the terms), in a copy of the file this prints, and passes it back with `--fill`. Nothing is
written until every check passes (`problems`): the words can be said in the time, every term
is explained with a worked example, every known question is answered in an opening, and
nothing is claimed that the profile does not hold. A draft the person asked for is marked
`draft` and listed, never refused (CLAUDE.md, "A draft they ask for is not a claim").

    python3 tools/interview_pack.py live "<Company>" [--role R] [--stage S] --out <file>
    python3 tools/interview_pack.py live "<Company>" [--role R] [--stage S] --fill <file> --write
    python3 tools/interview_pack.py live-check "<Company>" [--role R]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

LIVE = "interview_live.json"
VERSION = 1
# Words a minute said aloud: 150 is an ordinary pace; a fast talker sets their own
# (person.json interview.words_per_minute, written when they say so).
WPM = 150

PERSONAS = {"recruiter": "Recruiter", "manager": "Hiring manager",
            "technical": "Technical interviewer", "peer": "Future colleague",
            "senior": "Senior leader", "partner": "Partner"}

# Each shape: what it is called, its usual length, who is in the room, and its parts with
# their share of the time. A part's minutes scale with the round's real length.
SHAPES = {
    "screen": ("A recruiter screen", 30, ("recruiter",),
               (("opening", 6), ("motivation", 6), ("experience", 8), ("basics", 5), ("close", 5))),
    "manager": ("A hiring manager interview", 45, ("manager", "peer"),
                (("opening", 5), ("experience", 15), ("behaviour", 10), ("motivation", 7),
                 ("close", 8))),
    "technical": ("A technical interview", 60, ("technical", "peer"),
                  (("opening", 5), ("experience", 15), ("technical", 28), ("close", 12))),
    "take_home": ("A take-home, presented back", 60, ("technical", "manager"),
                  (("opening", 4), ("presenting", 24), ("technical", 20), ("close", 12))),
    "case": ("A case interview with a personal experience interview", 60, ("partner", "senior"),
             (("opening", 4), ("personal", 22), ("case", 26), ("close", 8))),
    "panel": ("A panel interview", 60, ("manager", "technical", "peer", "senior"),
              (("opening", 5), ("experience", 15), ("behaviour", 15), ("technical", 10),
               ("motivation", 5), ("close", 10))),
    "final": ("A final interview", 45, ("senior", "manager"),
              (("opening", 5), ("motivation", 10), ("behaviour", 12), ("experience", 8),
               ("close", 10))),
}
PART_TITLES = {
    "opening": "Hello, and tell me about yourself",
    "motivation": "Why this role, and why them",
    "basics": "Where you are, when you could start, and pay",
    "experience": "Your work, in depth",
    "behaviour": "Times you did it",
    "technical": "How you did the work",
    "presenting": "Presenting your take-home",
    "case": "The case",
    "personal": "A time you did it",
    "close": "Your questions for them",
}
# Who usually asks in each part, first of these the room holds.
PART_WHO = {
    "opening": ("recruiter", "manager", "partner", "senior", "technical"),
    "motivation": ("recruiter", "manager", "senior", "partner"),
    "basics": ("recruiter", "manager"),
    "experience": ("manager", "technical", "partner", "senior"),
    "behaviour": ("manager", "senior", "peer"),
    "technical": ("technical", "peer", "manager"),
    "presenting": ("technical", "manager"),
    "case": ("partner", "senior"),
    "personal": ("partner", "senior"),
    "close": ("manager", "recruiter", "partner", "senior"),
}
# Where a question goes, by what it asks; a shape without that part takes the next.
_KIND_OF = (
    ("opening", re.compile(r"about yourself|walk me through your (?:career|background|cv|resume)"
                           r"|introduce yourself", re.I)),
    ("basics", re.compile(r"\bsalary\b|\bpay\b|compensation|\bnotice\b|\bstart\b|sponsor|right to "
                          r"work|\bvisa\b|where are you based|interviewing anywhere|\btravel\b|"
                          r"\bpermit\b|how do you know", re.I)),
    ("motivation", re.compile(r"\bwhy\b|leaving|looking|five years|reservations|motivat|"
                              r"interest(?:ed)? in|the moves", re.I)),
    ("case", re.compile(r"\bcase\b|market siz|estimate how many|how would you (?:size|price)",
                        re.I)),
    ("behaviour", re.compile(r"\ba time\b|describe a situation|an example of|went wrong|"
                             r"changed someone|led something", re.I)),
    ("technical", re.compile(r"validat|check the result|\bmodel\b|\bcode\b|\bsql\b|pipeline|"
                             r"differently|\bbug\b|\btest|statistic|data quality", re.I)),
)
_FALLBACK = {"basics": ("basics", "motivation", "opening"),
             "motivation": ("motivation", "opening", "basics"),
             "opening": ("opening",),
             "case": ("case", "technical", "experience", "personal"),
             "behaviour": ("behaviour", "personal", "experience"),
             "technical": ("technical", "presenting", "experience", "case"),
             "experience": ("experience", "behaviour", "personal", "technical", "presenting")}
# A part with no question of its own has nothing to prepare, except where it always speaks.
_ALWAYS = ("opening", "close")
# The basics are said plainly and short: a Detailed version of "one month" is padding.
_NO_DETAIL = ("basics",)
MAX_QUESTIONS = 12
SIMPLE_SENTENCES = (2, 4)
DETAIL_RATIO = 1.6
MAX_BEATS = 7
MAX_DEPTH = 3
# The follow-ups that come after nearly every story, by who asks them. Their answers are
# Claude's to write from the story itself.
STORY_FOLLOW = (("manager", "What was your part in it, exactly?"),
                ("technical", "How did you know it had worked?"),
                ("senior", "What would you do differently now?"))
RED_FLAGS = (
    "Speaking badly of an employer you have worked for.",
    "A number your own work does not hold, or one you cannot explain if asked how.",
    "Naming the other employers you are talking to, or an offer you do not have.",
    "\"I'll take anything\": say why this role, every time.",
    "Answering a question they did not ask: answer, then stop.",
)
CONFIRM = "I'll confirm that and come back to you."

_TERM = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_DASH = re.compile("[–—]")
_SHARED = re.compile(r"\blast time\b|\bas (?:we|you) (?:discussed|said|mentioned|agreed)\b|"
                     r"\byou (?:asked|raised|mentioned) (?:earlier|before|last)\b|"
                     r"\bwhen we (?:last )?(?:spoke|talked|met)\b|\bas I (?:said|mentioned) "
                     r"(?:before|last)\b|\blike you asked\b", re.I)
# An opening is said before anything else in its part: "you asked" there can only mean an
# earlier conversation, which nobody can check is the one in the room.
_SHARED_OPENING = re.compile(r"\byou (?:asked|raised|mentioned|said)\b|\bagain,? as\b", re.I)
_NUMBERED = re.compile(r"^\s*(?:\(?\d+[.)]|\(?[ivx]+[.)])\s")
_SENTENCE = re.compile(r"(?<=[.!?])[\"”’']?\s+(?=[A-Z0-9\"“‘'(£$€])")
_WORD = re.compile(r"[A-Za-z0-9£$€%]+(?:['’.,][A-Za-z0-9]+)*")


# ---------------------------------------------------------------- text

def _t(value) -> str:
    return " ".join(str(value or "").split())


def plain(text, terms=None) -> str:
    """A text as it is said: each [[term]] its label, or the term's own name."""
    terms = terms or {}

    def one(m):
        return m.group(2) or _t((terms.get(m.group(1)) or {}).get("name")) or m.group(1)
    return _TERM.sub(one, str(text or ""))


def words(text, terms=None) -> int:
    return len(_WORD.findall(plain(text, terms)))


def sentences(text, terms=None) -> int:
    t = _t(plain(text, terms))
    return len([s for s in _SENTENCE.split(t) if s.strip()]) if t else 0


def minutes(n_words, wpm) -> float:
    """Minutes to say `n_words`, to the nearest half."""
    return round(2 * n_words / max(60, int(wpm or WPM))) / 2


def wpm() -> int:
    try:
        n = int(person.get("interview.words_per_minute", WPM) or WPM)
    except (TypeError, ValueError, person.NoProfile):
        n = WPM
    return n if 60 <= n <= 300 else WPM


# ---------------------------------------------------------------- the shape

_PANEL = re.compile(r"\bpanel\b", re.I)
_TAKE_HOME = re.compile(r"take[- ]?home|assignment|present(?:ation|ing)? (?:back|your)|"
                        r"case study", re.I)
_CASE = re.compile(r"\bcase\b|market[- ]sizing|guesstimate", re.I)
_FINAL = re.compile(r"\bfinal\b|last round|\bpartner\b|on-?site|assessment cent(?:re|er)", re.I)
_SCREEN = re.compile(r"\b(?:phone|recruiter|screen\w*|hr|talent|intro\w*)\b", re.I)
_TECH = re.compile(r"\b(?:technical|coding|code|sql|deep dive|system design|pairing)\b", re.I)
_MANAGER = re.compile(r"\b(?:hiring manager|manager|second|competenc\w*|behaviou?ral)\b", re.I)


def shape_of(ctx) -> tuple:
    """(shape, why it was assumed or ""): the round's own words first, then the step, the
    employer and the role. None for an offer, which is a negotiation, not an interview."""
    import interview_pack as P
    said = " ".join(_t(x) for x in (ctx.get("stage"), ctx.get("format")))
    step = ctx.get("step") or "technical"
    if step == "offer":
        return None, ""
    consulting = P.employer_type(ctx) == "consulting"
    for shape, rx in (("panel", _PANEL), ("take_home", _TAKE_HOME), ("case", _CASE)):
        if rx.search(said):
            return shape, ""
    if _SCREEN.search(said):
        return "screen", ""
    if consulting and step != "screen":
        return "case", ("a consulting firm's rounds after the screen are usually a case and a "
                        "personal experience interview together")
    if _FINAL.search(said):
        return "final", ""
    if _TECH.search(said):
        return "technical", ""
    if _MANAGER.search(said):
        return "manager", ""
    if step == "screen":
        return "screen", ""
    if step == "final":
        return "final", "a final round usually turns on why this employer and how you work"
    formats = P.interview_formats(ctx)[0]
    if "coding" in formats or "technical" in formats and P._ENGINEERING.search(ctx.get("role") or ""):
        return "technical", "an engineering role's second round usually goes into the work itself"
    return "manager", "the round after a screen is usually with the hiring manager"


def round_minutes(ctx, shape) -> int:
    """The round's length as booked, else the shape's usual length."""
    label = _t(ctx.get("stage")).lower()
    for s in ctx.get("stages") or []:
        if _t(s.get("label")).lower() == label and int(s.get("minutes") or 0) > 0:
            return int(s["minutes"])
    m = re.search(r"\b(\d{2,3})\s*(?:minutes?|mins?)\b", _t(ctx.get("stage")), re.I)
    if m and 10 <= int(m.group(1)) <= 240:
        return int(m.group(1))
    return SHAPES[shape][1]


def _part_minutes(shape, total) -> list:
    parts = SHAPES[shape][3]
    usual = sum(n for _k, n in parts)
    got = [max(2, int(round(n * total / usual))) for _k, n in parts]
    # Rounding never takes the parts past the round itself.
    while sum(got) > total and max(got) > 2:
        got[got.index(max(got))] -= 1
    return got


def kind_of(question) -> str:
    q = _t(question)
    return next((k for k, rx in _KIND_OF if rx.search(q)), "experience")


def _place(kind, kinds) -> str:
    return next((k for k in _FALLBACK.get(kind, (kind,)) if k in kinds), None) or (
        "experience" if "experience" in kinds else kinds[1] if len(kinds) > 2 else kinds[0])


def _who(kind, room) -> str:
    return next((w for w in PART_WHO.get(kind, ()) if w in room), room[0])


# ---------------------------------------------------------------- built from the records

def _norm(text) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", _t(text).lower()).strip()


def _story_id(i) -> str:
    return "s%d" % (i + 1)


def _proves(st) -> list:
    """What a story proves, in a few words a tag: its own `Use for:` lines, as topics."""
    out = []
    for tag in st.get("use_for") or []:
        t = re.sub(r"^(?:tell me about|walk me through|how do you|a time you|a time|describe)\s+",
                   "", _t(tag), flags=re.I)
        t = re.sub(r"^(?:a|an|the|your)\s+", "", t, flags=re.I).rstrip("?.")
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t[:1].upper() + t[1:])
    return out[:5]


def _from_lines(ans) -> list:
    """What an answer is said from, as plain lines for Claude: the story, the stock answer,
    the framing, never a source file."""
    import interview_pack as P
    out = []
    for ln in ans.get("lines") or []:
        s = P.plain_line(ln)[0]
        if s:
            out.append(s)
    return out


def known_questions(ctx) -> list:
    """The questions they are known to ask: what a recruiter or the person reported (the
    question bank's rows with a source), and those the session adds with --fill."""
    import company_key as ck
    k = ck.key(ctx["company"])
    out = []
    for r in ctx.get("bank") or []:
        if ck.key(r.get("company")) == k and _t(r.get("source")) and _t(r.get("question")):
            out.append({"text": _t(r["question"]), "from": _t(r["source"])})
    return out


def build(ctx) -> dict:
    """The live prep as the records make it, before Claude writes the words: the shape and its
    parts, each question placed with who asks it and the story it comes from, the stories, the
    questions to ask, the private notes and the known questions. Every answer still to write is
    empty, and `problems` says so."""
    import interview_pack as P
    shape, assumed = shape_of(ctx)
    if shape is None:
        raise ValueError("an offer is weighed, not interviewed for: the pack's money section "
                         "prepares it")
    name, _usual, room, parts_def = SHAPES[shape]
    total = round_minutes(ctx, shape)
    kinds = [k for k, _n in parts_def]
    mins = _part_minutes(shape, total)
    parts = [{"id": "p%d" % (i + 1), "kind": k, "title": PART_TITLES[k], "minutes": m,
              "who": _who(k, room), "say": [], "questions": []}
             for i, (k, m) in enumerate(zip(kinds, mins))]
    by_kind = {p["kind"]: p for p in parts}
    st_list = list(ctx.get("stories") or [])
    stories = [{"id": _story_id(i), "title": s["title"], "proves": _proves(s),
                "star": {k: _t(s["star"].get(k)) for k in "STAR" if _t(s["star"].get(k))},
                "questions": []} for i, s in enumerate(st_list)]
    sid = {s["title"].lower(): stories[i]["id"] for i, s in enumerate(st_list)}
    items = P.likely_questions(ctx)
    ctx = dict(ctx)
    ctx["plan"] = P.plan_stories(items, ctx)
    questions = []
    for item in items[:MAX_QUESTIONS]:
        ans = P.answer_for(item, ctx)
        part = by_kind[_place(kind_of(item["question"]), kinds)]
        story = None
        for ln in ans.get("lines") or []:
            m = re.match(r"^Story: (.+?) \(", ln)
            if m:
                story = sid.get(m.group(1).lower())
        prepared = ans.get("prepared") or {}
        q = {"id": "q%d" % (len(questions) + 1), "part": part["id"],
             "who": _who(part["kind"], room), "q": item["question"], "also": [],
             "simple": _t(prepared.get("answer")) if prepared else "", "detailed": "",
             "story": story, "known": None, "draft": False,
             "from": _from_lines(ans),
             "follow": ([{"who": w, "q": fq, "also": [], "simple": "", "detailed": "", "follow": []}
                         for w, fq in STORY_FOLLOW] if story else [])}
        questions.append(q)
        part["questions"].append(q["id"])
    # The known questions, each placed as a question of its own, or on the one it already is.
    known = []
    for i, k in enumerate(known_questions(ctx)):
        kid = "k%d" % (i + 1)
        known.append(dict(k, id=kid, question=None))
    _place_known(known, questions, parts, room)
    asks = []
    for ln in P.ask_lines(ctx):
        text = P.plain_line(ln)[0]
        q, _sep, why = text.partition(" (")
        if q.endswith("?"):
            asks.append({"id": "a%d" % (len(asks) + 1), "q": q, "why": why.rstrip(")"),
                         "follow": []})
    asks.append({"id": "a%d" % (len(asks) + 1), "q": P.CLOSE_QUESTION,
                 "why": "the last word on any doubt, while you are still in the room", "follow": []})
    doc = {"version": VERSION, "built": ctx.get("today") or dt.date.today().isoformat(),
           "company": ctx["company"], "role": ctx.get("role") or "", "stage": ctx.get("stage") or "",
           "date": ctx.get("date") or "", "with": ctx.get("with") or "",
           "shape": shape, "shape_name": name, "assumed": assumed, "minutes": total,
           "wpm": wpm(), "room": list(room), "parts": parts, "questions": questions,
           "stories": stories, "ask": asks, "terms": {}, "known": known,
           "private": private_notes(ctx)}
    return finish(doc)


def _place_known(known, questions, parts, room) -> None:
    """Each known question onto the question that already asks it, else a new one in the
    part it belongs to."""
    kinds = [p["kind"] for p in parts]
    import interview_pack as P
    for k in known:
        if k.get("question") and any(q["id"] == k["question"] for q in questions):
            continue
        hit = next((q for q in questions if P.similar(q["q"], k["text"]) >= 0.5
                    or _norm(q["q"]) == _norm(k["text"])), None)
        if hit is None:
            part = next(p for p in parts if p["kind"] == _place(kind_of(k["text"]), kinds))
            hit = {"id": "q%d" % (len(questions) + 1), "part": part["id"],
                   "who": _who(part["kind"], room), "q": k["text"], "also": [], "simple": "",
                   "detailed": "", "story": None, "known": None, "draft": False,
                   "from": ["They are known to ask this (%s)." % k["from"]], "follow": []}
            questions.append(hit)
            part["questions"].append(hit["id"])
        hit["known"] = k["id"]
        k["question"] = hit["id"]


def private_notes(ctx) -> dict:
    """What is for the person alone: the pay to say, notice, where they are based as their
    profile says to say it, what not to say, figures not to quote, the gaps and how to put
    them, the red flags, and what to confirm later rather than guess."""
    import interview_pack as P
    import told
    pay, _lines = P.money(ctx)
    notice = ""
    for a in ctx.get("answers") or []:
        if re.search(r"\bnotice\b", a.get("question") or "", re.I) and not a.get("fill_in"):
            notice = _t(a["answer"])
    if not notice:
        _q, said = P._form_value(ctx, r"notice")
        notice = _t(said)
    based = told.place(ctx["company"]) or P.home_place(ctx["company"])
    not_say = [P.plain_line(ln)[0] for ln in P.do_not_say(ctx)]
    figures = []
    research = ctx.get("research") or {}
    for f in research.get("do_not_claim") or []:
        claim = _t(f.get("claim") if isinstance(f, dict) else f)
        if re.search(r"\d", claim):
            figures.append(claim)
    target, floor = P._band()
    if floor:
        figures.append("Your lowest figure, %s: it stays with you." % "{:,}".format(floor))
    weak = []
    for g in (ctx.get("facts") or {}).get("gaps") or []:
        weak.append({"what": _t(g.get("gap")),
                     "frame": _t(g.get("framing")) or "Say plainly you have not done it as such, "
                                                      "then the nearest true thing."})
    for m in P.landmines(ctx):
        what = _t(m.get("what"))
        frame = " ".join(x for x in (P.plain_line(ln)[0] for ln in m.get("framing") or []) if x)
        if what:
            weak.append({"what": what, "frame": frame or "Say it plainly and briefly, then what "
                                                         "you did next."})
    return {"pay": P.plain_line(pay)[0] if pay else "",
            "notice": notice, "based": based,
            "not_to_say": [x for x in not_say if x], "figures": figures,
            "weaknesses": weak, "red_flags": list(RED_FLAGS), "confirm": []}


# ---------------------------------------------------------------- Claude's words onto it

# What Claude writes and a rebuild keeps; everything else is the records' and is made again.
_Q_WRITTEN = ("who", "also", "simple", "detailed", "follow", "draft")


def merge(fresh, filled) -> dict:
    """The records' prep (`fresh`) with Claude's words (`filled`) kept: each question's answers,
    follow-ups, who asks and its other wordings, matched by the question; each part's opening,
    matched by its kind; the terms; the follow-ups to the questions to ask; the known questions
    and questions Claude added; what to confirm later. A question the records no longer ask is
    kept where Claude wrote it, so nothing written is lost."""
    doc = json.loads(json.dumps(fresh))
    if not filled:
        return doc
    byq = {_norm(q.get("q")): q for q in filled.get("questions") or []}
    for q in doc["questions"]:
        old = byq.pop(_norm(q["q"]), None)
        if old:
            for k in _Q_WRITTEN:
                if k in old and old[k] not in (None, "", []):
                    q[k] = old[k]
            if old.get("story") and any(s["id"] == old["story"] for s in doc["stories"]):
                q["story"] = old["story"]
    parts = {p["kind"]: p for p in doc["parts"]}
    old_parts = {p.get("kind"): p for p in filled.get("parts") or []}
    old_ids = {p.get("id"): p.get("kind") for p in filled.get("parts") or []}
    # Questions Claude added, or the records no longer ask: kept, in the part of their kind.
    for old in byq.values():
        if not _t(old.get("q")):
            continue
        kind = old_ids.get(old.get("part")) or kind_of(old["q"])
        part = parts.get(kind) or parts.get(_place(kind_of(old["q"]), list(parts)))
        q = {"id": "q%d" % (len(doc["questions"]) + 1), "part": part["id"],
             "who": old.get("who") or part["who"], "q": _t(old["q"]),
             "also": old.get("also") or [], "simple": old.get("simple") or "",
             "detailed": old.get("detailed") or "", "story": old.get("story"),
             "known": None, "draft": bool(old.get("draft")), "from": old.get("from") or [],
             "follow": old.get("follow") or []}
        if q["story"] and not any(s["id"] == q["story"] for s in doc["stories"]):
            q["story"] = None
        doc["questions"].append(q)
        part["questions"].append(q["id"])
    # The openings, their links rewritten to this build's question ids.
    old_qid = {q.get("id"): _norm(q.get("q")) for q in filled.get("questions") or []}
    new_qid = {_norm(q["q"]): q["id"] for q in doc["questions"]}
    known_text = {k.get("id"): _norm(k.get("text")) for k in filled.get("known") or []}
    for kind, part in parts.items():
        old = old_parts.get(kind)
        if not old:
            continue
        say = []
        for b in old.get("say") or []:
            beat = {"t": _t(b.get("t"))}
            prompts = [new_qid.get(old_qid.get(x)) for x in b.get("prompts") or []]
            beat["prompts"] = [x for x in prompts if x]
            if b.get("known"):
                beat["known_text"] = known_text.get(b["known"]) or ""
            say.append(beat)
        part["say"] = say
        if _t(old.get("title")):
            part["title"] = _t(old["title"])
    # The known questions: the records' and Claude's, once each.
    have = {_norm(k["text"]) for k in doc["known"]}
    for k in filled.get("known") or []:
        if _t(k.get("text")) and _norm(k["text"]) not in have:
            doc["known"].append({"id": "k%d" % (len(doc["known"]) + 1), "text": _t(k["text"]),
                                 "from": _t(k.get("from")) or "you", "question": None})
            have.add(_norm(k["text"]))
    for k in doc["known"]:
        k["question"] = None
        for q in doc["questions"]:
            if q.get("known") == k["id"]:
                q["known"] = None
    # Claude's placing of a known question on a question is kept, by the words of both.
    placed = {}
    for k in filled.get("known") or []:
        if k.get("question") and old_qid.get(k["question"]):
            placed[_norm(k.get("text"))] = new_qid.get(old_qid[k["question"]])
    room = doc["room"]
    for k in doc["known"]:
        qid = placed.get(_norm(k["text"]))
        if qid:
            k["question"] = qid
            next(q for q in doc["questions"] if q["id"] == qid)["known"] = k["id"]
    _place_known(doc["known"], doc["questions"], doc["parts"], room)
    by_text = {_norm(k["text"]): k["id"] for k in doc["known"]}
    for part in doc["parts"]:
        for b in part["say"]:
            t = b.pop("known_text", None)
            if t:
                b["known"] = by_text.get(t)
    # Terms are Claude's alone.
    doc["terms"] = {k: v for k, v in (filled.get("terms") or {}).items() if isinstance(v, dict)}
    # The questions to ask: the records' with Claude's follow-ups, then Claude's own.
    old_ask = {_norm(a.get("q")): a for a in filled.get("ask") or []}
    for a in doc["ask"]:
        old = old_ask.pop(_norm(a["q"]), None)
        if old and old.get("follow"):
            a["follow"] = old["follow"]
    for old in old_ask.values():
        if _t(old.get("q")):
            doc["ask"].insert(len(doc["ask"]) - 1, {"id": "a%d" % (len(doc["ask"]) + 1),
                                                    "q": _t(old["q"]), "why": _t(old.get("why")),
                                                    "follow": old.get("follow") or []})
    priv = doc["private"]
    old_priv = filled.get("private") or {}
    for key in ("not_to_say", "figures", "red_flags", "confirm"):
        for x in old_priv.get(key) or []:
            if _t(x) and _t(x) not in priv[key]:
                priv[key].append(_t(x))
    have_w = {_norm(w["what"]) for w in priv["weaknesses"]}
    for w in old_priv.get("weaknesses") or []:
        if isinstance(w, dict) and _t(w.get("what")) and _norm(w["what"]) not in have_w:
            priv["weaknesses"].append({"what": _t(w["what"]), "frame": _t(w.get("frame"))})
    return finish(doc)


def finish(doc) -> dict:
    """The parts in order with their questions, each story with the questions it answers, and
    the timing: minutes a part and the person's own talk in it, from the words."""
    for i, a in enumerate(doc["ask"]):
        a["id"] = "a%d" % (i + 1)
    for s in doc["stories"]:
        s["questions"] = [q["id"] for q in doc["questions"] if q.get("story") == s["id"]]
    speed = int(doc.get("wpm") or WPM)
    terms = doc.get("terms") or {}
    parts_t, talk_all = {}, 0
    for p in doc["parts"]:
        p["questions"] = [q["id"] for q in doc["questions"] if q["part"] == p["id"]]
        n = sum(words(b.get("t"), terms) for b in p["say"])
        n += sum(words(q.get("simple"), terms) for q in doc["questions"] if q["part"] == p["id"])
        talk = minutes(n, speed)
        talk_all += n
        parts_t[p["id"]] = {"minutes": p["minutes"], "talk": talk, "words": n}
    doc["timing"] = {"minutes": doc["minutes"], "parts_minutes": sum(p["minutes"] for p in doc["parts"]),
                     "talk": minutes(talk_all, speed), "wpm": speed, "parts": parts_t}
    return doc


# ---------------------------------------------------------------- the checks

def _nodes(q, depth=1, where=""):
    """Every follow-up under a question, with its depth and where it is, for the checks."""
    for f in q.get("follow") or []:
        here = "%s, then \"%s\"" % (where, _t(f.get("q")))
        yield f, depth, here
        yield from _nodes(f, depth + 1, here)


def spoken(doc):
    """(where, text, draft, question) for everything the person will say aloud."""
    qs = {q["id"]: q for q in doc.get("questions") or []}
    for p in doc.get("parts") or []:
        for i, b in enumerate(p.get("say") or []):
            yield ("\"%s\", what to say first (%d)" % (p.get("title"), i + 1), b.get("t"), False, "")
    for q in qs.values():
        where = "\"%s\"" % _t(q.get("q"))
        for key in ("simple", "detailed"):
            if _t(q.get(key)):
                yield ("%s, %s answer" % (where, key), q[key], bool(q.get("draft")), q["q"])
        for f, _d, here in _nodes(q, where=where):
            for key in ("simple", "detailed"):
                if _t(f.get(key)):
                    yield ("%s, %s answer" % (here, key), f[key],
                           bool(q.get("draft") or f.get("draft")), q["q"])
    for a in doc.get("ask") or []:
        yield ("your question \"%s\"" % _t(a.get("q")), a.get("q"), False, "")
        for f in a.get("follow") or []:
            yield ("your question \"%s\", if they say %s" % (_t(a.get("q")), _t(f.get("if"))),
                   f.get("then"), False, "")


def _all_strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v)
    elif isinstance(value, str):
        yield value


def _answer_checks(node, where, terms, need_detail) -> list:
    out = []
    s, d = _t(node.get("simple")), _t(node.get("detailed"))
    if not s:
        out.append((where, "the simple answer is not written yet: write it as you would say "
                           "it, two to four sentences"))
        return out
    n = sentences(s, terms)
    lo, hi = SIMPLE_SENTENCES
    if not lo <= n <= hi:
        out.append((where, "the simple answer is %d sentence%s: make it %d to %d, a real "
                           "spoken answer" % (n, "" if n == 1 else "s", lo, hi)))
    if need_detail and not d:
        out.append((where, "the detailed answer is not written yet: the two-minute version, "
                           "with your own numbers and what you learned"))
    if d:
        ws, wd = words(s, terms), words(d, terms)
        if wd <= ws:
            out.append((where, "the detailed answer (%d words) is no longer than the simple one "
                               "(%d): add how you did it, the result and what you learned"
                        % (wd, ws)))
        elif wd > DETAIL_RATIO * ws:
            out.append((where, "the detailed answer is %d words against %d in the simple one: "
                               "keep it under %d, so it stays the same answer, a little fuller"
                        % (wd, ws, int(DETAIL_RATIO * ws))))
    return out


def problems(doc, ctx=None) -> list:
    """[(where, what to fix)] for a live prep not yet fit to show, in plain words. Empty when
    it is ready. Drafts the person asked for are not problems: `drafts` lists them."""
    out = []
    terms = doc.get("terms") or {}
    company = _t(doc.get("company"))
    qids = {q["id"] for q in doc.get("questions") or []}
    # Every term used exists, and every term is explained in the employer's own terms with a
    # worked example.
    for where, text, _d, _q in list(spoken(doc)) + [
            ("the term \"%s\"" % k, " ".join(_t(v.get(f)) for f in ("here", "example", "plain",
                                                                    "technical")), False, "")
            for k, v in terms.items()]:
        for m in _TERM.finditer(str(text or "")):
            if m.group(1) not in terms:
                out.append((where, "it explains \"%s\", and there is no such term: add it to the "
                                   "terms, or take the brackets off" % (m.group(2) or m.group(1))))
    # The employer named by the first word of its name that is not a small one ("The", "&").
    first = next((w for w in re.findall(r"[A-Za-z0-9]+", company.lower())
                  if w not in ("the", "and", "of", "a", "an")), "") if company else ""
    for k, v in terms.items():
        name = _t(v.get("name")) or k
        if not _t(v.get("name")):
            out.append(("the term \"%s\"" % k, "it has no name to show"))
        if not _t(v.get("here")):
            out.append(("the term \"%s\"" % name, "say what it means at %s, in their own work"
                        % (company or "the employer")))
        elif first and first not in _t(v.get("here")).lower() + " " + _t(v.get("example")).lower():
            out.append(("the term \"%s\"" % name, "explain it in %s's own work: name them, or one "
                        "of their products, in what it means there" % company))
        if not _t(v.get("example")):
            out.append(("the term \"%s\"" % name, "it needs a small worked example"))
        if not _t(v.get("plain")):
            out.append(("the term \"%s\"" % name, "say what it means in plain words too"))
    # No dashes of the kind the app never writes, anywhere.
    for s in _all_strings(doc):
        if _DASH.search(s):
            out.append(("\"%s\"" % (_t(s)[:60]), "it has a long dash: use a comma, a colon or "
                                                 "a full stop"))
    # The parts: something to say first, a few beats, never numbered, in the time it has.
    timing = (doc.get("timing") or {}).get("parts") or {}
    for p in doc.get("parts") or []:
        say = p.get("say") or []
        if not say and (p.get("questions") or p.get("kind") in _ALWAYS):
            out.append(("\"%s\"" % p.get("title"), "nothing to say first yet: write two or three "
                                                   "sentences to say aloud as it starts"))
        if len(say) > MAX_BEATS:
            out.append(("\"%s\"" % p.get("title"), "%d things to say first: keep it to %d"
                        % (len(say), MAX_BEATS)))
        for i, b in enumerate(say):
            if _NUMBERED.match(_t(b.get("t"))):
                out.append(("\"%s\", what to say first (%d)" % (p.get("title"), i + 1),
                            "take the number off the front: the words say the order already"))
            for x in b.get("prompts") or []:
                if x not in qids:
                    out.append(("\"%s\", what to say first (%d)" % (p.get("title"), i + 1),
                                "it points at a question that is not in the prep"))
        t = timing.get(p.get("id")) or {}
        if t and t.get("talk", 0) > p.get("minutes", 0):
            out.append(("\"%s\"" % p.get("title"),
                        "your words take about %s minutes to say at %d words a minute, in a "
                        "%d minute part: cut the openings or the simple answers"
                        % (_num(t["talk"]), int(doc.get("wpm") or WPM), p.get("minutes", 0))))
    total = sum(p.get("minutes", 0) for p in doc.get("parts") or [])
    if total > int(doc.get("minutes") or 0):
        out.append(("the timing", "the parts take %d minutes in a %d minute interview: shorten "
                                  "one" % (total, int(doc.get("minutes") or 0))))
    # Every answer: a simple one of two to four sentences, a detailed one that is the same
    # answer a little fuller, follow-ups no more than three deep, each with who asks it.
    parts = {p["id"]: p for p in doc.get("parts") or []}
    for q in doc.get("questions") or []:
        where = "\"%s\"" % _t(q.get("q"))
        kind = (parts.get(q.get("part")) or {}).get("kind")
        if q.get("part") not in parts:
            out.append((where, "it is in no part of the interview"))
        if q.get("who") not in PERSONAS:
            out.append((where, "say who is likely to ask it"))
        out += _answer_checks(q, where, terms, kind not in _NO_DETAIL)
        if q.get("story") and not any(s["id"] == q["story"] for s in doc.get("stories") or []):
            out.append((where, "it is answered with a story that is not among yours"))
        for f, depth, here in _nodes(q, where=where):
            if depth > MAX_DEPTH:
                out.append((here, "follow-ups go three deep at most: fold this one into the one "
                                  "above"))
            if f.get("who") not in PERSONAS:
                out.append((here, "say who is likely to ask it"))
            out += _answer_checks(f, here, terms, False)
    # The questions to ask: each with what to say back to their likely answer.
    for a in doc.get("ask") or []:
        if not a.get("follow"):
            out.append(("your question \"%s\"" % _t(a.get("q")),
                        "add what you would ask next to their likely answer"))
        for f in a.get("follow") or []:
            if not _t(f.get("if")) or not _t(f.get("then")):
                out.append(("your question \"%s\"" % _t(a.get("q")),
                            "a follow-up needs their likely answer and what you say next"))
    # Every known question: on a question, and answered before they ask it, in an opening.
    said_known = {b.get("known") for p in doc.get("parts") or [] for b in p.get("say") or []}
    for k in doc.get("known") or []:
        if not k.get("question") or k["question"] not in qids:
            out.append(("\"%s\"" % k.get("text"), "a question they are known to ask is not "
                                                  "placed on any part"))
        if k.get("id") not in said_known:
            out.append(("\"%s\"" % k.get("text"), "a question they are known to ask: answer it "
                                                  "in what you say first in its part, and mark it"))
    # Words that assume a history nobody can check, and phrases the person never wants.
    import learned
    for where, text, _d, _q in spoken(doc):
        t = plain(text, terms)
        m = _SHARED.search(t) or (_SHARED_OPENING.search(t) if "what to say first" in where else None)
        if m:
            out.append((where, "\"%s\" assumes you have spoken before: say it fresh" % m.group(0)))
        for hit in learned.dislikes(t):
            out.append((where, "\"%s\" is a phrase you asked never to use" % hit))
    out += grounding(doc, ctx)
    return out


def _num(x) -> str:
    return ("%g" % x)


def grounding(doc, ctx=None) -> list:
    """What the grounding checks refuse in anything said as the person's own: a number the
    profile does not hold (`check_numbers`), what `check_claims` calls an error (a
    certification not held, a word the person's market does not use, a date gone by), and a
    place this employer was not told (`told.clash`). A draft the person asked for is theirs to
    confirm, never refused here; pay and notice are what they ask for and owe."""
    import check_claims
    import check_numbers
    import told
    import interview_pack as P
    terms = doc.get("terms") or {}
    company = _t(doc.get("company"))
    base = check_numbers.grounded()
    allowed = check_numbers.Grounded(base, base.nouns, base.said, base.small)
    # What they read about the employer, the posting and the person's own records may be
    # repeated: an answer can say what the employer does.
    extra = []
    if ctx:
        extra.append(_t(ctx.get("posting")))
        extra.append(json.dumps(ctx.get("research") or {}))
    extra.append(json.dumps(doc.get("private") or {}))
    for s in doc.get("stories") or []:
        extra.append(" ".join((s.get("star") or {}).values()))
    allowed.add_text("\n".join(extra), nouns=False)
    out = []
    for where, text, draft, question in spoken(doc):
        if draft:
            continue
        t = plain(text, terms)
        if not re.search(P._PAY_Q + r"|\bnotice\b|\bstart\b", question or "", re.I):
            for f in check_numbers.check(t, allowed=allowed):
                if P._PLAN.search(f.get("context") or ""):
                    continue
                out.append((where, "\"%s\" is a number your profile does not hold: say the one "
                                   "it holds, or mark the answer a draft for you to confirm"
                            % f.get("value", "")))
        for sev, _name, snippet, why in check_claims.check_text(t):
            if sev == "ERROR":
                out.append((where, "\"%s\": %s" % (snippet, why)))
        if company:
            clash = told.clash(t, company)
            if clash:
                out.append((where, P.plain_clash(clash)))
    return out


def drafts(doc) -> list:
    """The answers still marked as drafts the person asked for: theirs to confirm."""
    out = []
    for q in doc.get("questions") or []:
        if q.get("draft"):
            out.append(_t(q.get("q")))
        for f, _d, here in _nodes(q, where="\"%s\"" % _t(q.get("q"))):
            if f.get("draft") and not q.get("draft"):
                out.append(here)
    return out


# ---------------------------------------------------------------- on disk

def path_for(folder) -> str:
    return os.path.join(folder, LIVE)


def load(folder) -> dict | None:
    try:
        with open(path_for(folder), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    return doc if ready(doc) else None


def ready(doc) -> bool:
    """A live prep the page can draw: this version's shape, written after its checks passed."""
    return (isinstance(doc, dict) and doc.get("version") == VERSION
            and isinstance(doc.get("parts"), list) and bool(doc["parts"])
            and isinstance(doc.get("questions"), list)
            and (doc.get("checked") or {}).get("problems") == 0)


def write(ctx, filled) -> tuple:
    """(path or "", problems): the records' prep with Claude's words, written beside the
    living document only once every check passes."""
    doc = merge(build(ctx), filled)
    found = problems(doc, ctx)
    if found:
        return "", found
    doc["checked"] = {"on": ctx.get("today") or dt.date.today().isoformat(), "problems": 0,
                      "drafts": len(drafts(doc))}
    path = path_for(ctx["folder"])
    os.makedirs(ctx["folder"], exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path, []


def for_page(doc) -> dict | None:
    """The live prep as the page holds it: what Claude wrote it from (`from`) is Claude's, and
    stays out."""
    if not ready(doc):
        return None
    out = json.loads(json.dumps(doc))
    for q in out["questions"]:
        q.pop("from", None)
    out["drafts"] = (out.pop("checked", None) or {}).get("drafts", 0)
    out["personas"] = dict(PERSONAS)
    # What the Brief's "Likely to come up" draws, in the engine's one order.
    out["likely"] = [q["id"] for q in _likely_order(out)]
    return out


def likely(doc, n=5) -> list:
    """The questions most likely to come up, in the order the interview runs: the known ones
    first in each part, then the rest. What the Brief's "Likely to come up" reads."""
    return [{"question": q["q"], "answer": _t(plain(q.get("simple"), doc.get("terms"))),
             "draft": bool(q.get("draft"))} for q in _likely_order(doc)[:n]]


def _likely_order(doc) -> list:
    order = {p["id"]: i for i, p in enumerate(doc.get("parts") or [])}
    return sorted(doc.get("questions") or [], key=lambda q: (order.get(q["part"], 99),
                                                             not q.get("known")))
