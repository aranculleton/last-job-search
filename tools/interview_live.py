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
the terms), only those, keyed by part and question (`words_into`), and passes them with `--fill`. Nothing is
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

# Who may ask, as the page tags them: the people in an interview room (the maintainer,
# 2026-11-10: hiring manager, technical interviewer, HR, future peer, senior leader), with the
# recruiter of a screen and a consulting firm's partner.
PERSONAS = {"recruiter": "Recruiter", "manager": "Hiring manager",
            "technical": "Technical interviewer", "hr": "HR", "peer": "Future peer",
            "senior": "Senior leader", "partner": "Partner", "test": "The test",
            "recorded": "Recorded question"}

# The hello and the close of a day of several interviews, said fresh to each interviewer.
OPENING_EACH = "Hello, and your story, fresh for each interviewer"
CLOSE_EACH = "Your questions, a different one for each"
# Each shape: what it is called, its usual length, who is in the room, and its parts with
# their share of the time. A part's minutes scale with the round's real length.
SHAPES = {
    "screen": ("A recruiter screen", 30, ("recruiter",),
               (("opening", 6), ("motivation", 6), ("experience", 8), ("basics", 5), ("close", 5))),
    "manager": ("A hiring manager interview", 45, ("manager", "peer"),
                (("opening", 5), ("experience", 15), ("behaviour", 10), ("motivation", 7),
                 ("close", 8))),
    # A technical round (coding, SQL, statistics, machine learning, system design) runs as its
    # own stages: the warm-up and background, a problem worked aloud, the probes and trade-offs
    # behind it, and their questions (the maintainer, 2026-11-10).
    "technical": ("A technical interview", 60, ("technical", "peer"),
                  (("opening", 8, "Warm-up, and your background"), ("technical", 27),
                   ("probes", 13), ("close", 12))),
    # A technical screen: a shorter technical round, and the basics a screen checks.
    "tech_screen": ("A technical screen", 45, ("technical", "recruiter"),
                    (("opening", 6, "Warm-up, and your background"), ("technical", 20),
                     ("probes", 8), ("basics", 5, "Why them, and the basics"), ("close", 6))),
    "take_home": ("A take-home, presented back", 60, ("technical", "manager"),
                  (("opening", 4), ("presenting", 24), ("technical", 20, "How you did the work"), ("close", 12))),
    # A consulting case: the structure, the maths said aloud and the answer in a minute; most
    # firms put a personal experience interview in the same sitting.
    "case": ("A case interview with a personal experience interview", 60, ("partner", "senior"),
             (("opening", 4), ("personal", 20), ("case", 12), ("maths", 8), ("synthesis", 8),
              ("close", 8))),
    "case_only": ("A case interview", 45, ("partner", "senior"),
                  (("opening", 4), ("case", 15), ("maths", 10), ("synthesis", 8), ("close", 8))),
    # One or two stories told in depth, and the probes behind each.
    "personal": ("A personal experience interview", 30, ("partner", "senior"),
                 (("opening", 3), ("personal", 22), ("close", 5))),
    # A technical round and a case in one sitting.
    "technical_case": ("A technical interview and a case", 60, ("technical", "partner"),
                       (("opening", 5), ("technical", 20), ("probes", 7), ("case", 10),
                        ("maths", 6), ("synthesis", 4), ("close", 8))),
    # A timed test or exercise, alone: not a conversation, so the prep is how it works, how to
    # take each kind of item, the pacing, and items to practise on.
    "assessment": ("A timed test or exercise", 60, ("test",),
                   (("format", 6), ("approach", 18), ("pacing", 6), ("practice", 30))),
    # Stories, one question at a time, and the probes behind each (a behavioural, values or
    # competency interview).
    "behavioural": ("A behavioural interview", 45, ("manager", "peer"),
                    (("opening", 5), ("behaviour", 22), ("experience", 8), ("motivation", 4),
                     ("close", 6))),
    # A one-way video interview: questions on the screen, answers recorded, nobody to ask.
    "recorded": ("A recorded video interview", 30, ("recorded",),
                 (("format", 4, "How the recording works"), ("opening", 5), ("motivation", 6),
                  ("behaviour", 10), ("experience", 5))),
    # Several interviews back to back (a superday, an onsite or virtual onsite, an assessment
    # centre): each interviewer hears the story fresh, and each gets a question of their own.
    "superday": ("Several interviews back to back", 180, ("manager", "technical", "peer", "senior"),
                 (("opening", 15, OPENING_EACH), ("experience", 35), ("behaviour", 40),
                  ("technical", 40, "How you do the work"), ("motivation", 20),
                  ("close", 30, CLOSE_EACH))),
    "panel": ("A panel interview", 60, ("manager", "technical", "peer", "senior"),
              (("opening", 5), ("experience", 15), ("behaviour", 15), ("technical", 10, "How you do the work"),
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
    "technical": "A problem, worked aloud",
    "probes": "The follow-up probes and trade-offs",
    "presenting": "Presenting your take-home",
    "case": "The case: how you structure it",
    "maths": "The maths, said aloud",
    "synthesis": "Your answer, in a minute",
    "personal": "One story in depth, and the probes behind it",
    "format": "How the test works",
    "approach": "How to take each kind of item",
    "pacing": "Pacing against the time",
    "practice": "Items to practise on",
    "close": "Your questions for them",
}
# Each part's name on its chip: a word or two, found at a glance mid-interview.
PART_SHORT = {"opening": "Intro", "motivation": "Why them", "basics": "The basics",
              "experience": "Your work", "behaviour": "Examples", "technical": "The problem",
              "probes": "Probes", "presenting": "Take-home", "case": "The case",
              "maths": "Maths", "synthesis": "Your answer", "personal": "Your story",
              "format": "How it works", "approach": "Approach", "pacing": "Pacing",
              "practice": "Practice", "close": "Your questions"}
# Who usually asks in each part, first of these the room holds.
PART_WHO = {
    "opening": ("recruiter", "manager", "partner", "senior", "technical"),
    "motivation": ("recruiter", "manager", "senior", "partner"),
    "basics": ("recruiter", "hr", "manager"),
    "experience": ("manager", "technical", "partner", "senior"),
    "behaviour": ("manager", "senior", "peer"),
    "technical": ("technical", "peer", "manager"),
    "probes": ("technical", "peer", "manager"),
    "presenting": ("technical", "manager"),
    "case": ("partner", "senior"),
    "maths": ("partner", "senior"),
    "synthesis": ("partner", "senior"),
    "personal": ("partner", "senior", "manager"),
    "format": ("test", "recorded"), "approach": ("test",), "pacing": ("test",),
    "practice": ("test",),
    "close": ("manager", "recruiter", "partner", "senior"),
}
# Where a question goes, by what it asks; a shape without that part takes the next.
_KIND_OF = (
    ("opening", re.compile(r"about yourself|walk me through your (?:career|background|cv|resume)"
                           r"|introduce yourself", re.I)),
    # "How do you know <someone>?", never "How do you know it worked?".
    ("basics", re.compile(r"\bsalary\b|\bpay\b|compensation|\bnotice\b|\bstart\b|sponsor|right to "
                          r"work|\bvisa\b|where are you based|interviewing anywhere|\btravel\b|"
                          r"\bpermit\b|how do you know (?!(?:if|whether|that|it|its|the|this|these|"
                          r"what|when|how|your|you)\b)\w+\W*$", re.I)),
    ("maths", re.compile(r"estimate how many|how many .* (?:a|per) (?:year|day|week)|"
                         r"calculate|back of the envelope|market siz", re.I)),
    ("synthesis", re.compile(r"\brecommend|what would you tell (?:the|their) (?:ceo|client)|"
                             r"summari[sz]e your|sum up", re.I)),
    # What a take-home brings: what was left out, what more time would change.
    ("presenting", re.compile(r"\bleave out\b|\bleft out\b|with more time|your (?:take-home|"
                              r"presentation|slides|analysis)\b", re.I)),
    # "Why that change and not a bigger one?" asks about a choice in the work, never why them: a
    # mixed round put it in the hello (the maintainer, 2026-11-12).
    ("probes", re.compile(r"\bwhy (?:that|this|those|these|the|your) (?:change|approach|model|method|"
                          r"choice|features?|metric|threshold|solution|design|fix|step|algorithm|"
                          r"library|split|cut|number|test|query|join|tool|way)\b|\bwhy (?:did|would) "
                          r"you (?:choose|pick|use|go with)\b|\bwhy not\b|\band not (?:a|an|the) "
                          r"(?:bigger|smaller|simpler|harder|different|other)\b", re.I)),
    ("motivation", re.compile(r"\bwhy\b|leaving|looking|five years|reservations|motivat|draws you|"
                              r"interest(?:ed)? in|the moves", re.I)),
    ("case", re.compile(r"\bcase\b|how would you (?:size|price)", re.I)),
    # A skill, a tool or a certificate the posting names is asked where the work is tested,
    # never in the one story told in depth.
    ("skill", re.compile(r"experience (?:with|in|of)\b|certif|qualifi|\blicen[cs]e|proficien|"
                         r"familiar(?:ity)? with|how familiar|have you (?:used|worked with)|"
                         r"how well do you know|\bmember of\b|\bmembership\b|\bdo you hold\b|"
                         r"\bare you (?:\w+ )?(?:qualified|certified|chartered|licensed)\b", re.I)),
    ("behaviour", re.compile(r"\ba time\b|describe a situation|an example of|went wrong|"
                             r"changed someone|led something", re.I)),
    ("probes", re.compile(r"trade-?off|differently|why not|what if|how would it scale|edge case|"
                          r"complexity|\bfaster\b|speed (?:it|this|that) up|optimi[sz]|"
                          r"explain (?:this|it|that|the \w+|your \w+) to (?:the |a |your )?"
                          r"(?:client|business|stakeholders?|manager|non-?technical|team)", re.I)),
    # The work in front of them: the data, its columns and features, the model, taking it live.
    ("technical", re.compile(r"validat|check the result|\bmodel\b|\bcode\b|\bsql\b|pipeline|"
                             r"\bbug\b|\btest|statistic|data quality|python|algorithm|"
                             r"\b(?:this|the|that) (?:data|dataset|table|file|function|query|"
                             r"output|result|analysis)\b|\bin the data\b|\bfeatures?\b|"
                             r"\bcolumns?\b|\bproduction\b|\bdeploy", re.I)),
)
_FALLBACK = {"basics": ("basics", "motivation", "opening"),
             "motivation": ("motivation", "basics", "opening"),
             "opening": ("opening",),
             "case": ("case", "technical", "experience", "personal", "practice"),
             "maths": ("maths", "case", "technical", "practice", "experience"),
             "synthesis": ("synthesis", "case", "experience", "personal"),
             "behaviour": ("behaviour", "personal", "experience"),
             "skill": ("technical", "experience", "probes", "presenting", "behaviour", "basics",
                       "personal"),
             "probes": ("probes", "technical", "presenting", "experience"),
             "technical": ("technical", "presenting", "experience", "personal"),
             "presenting": ("presenting", "probes", "technical", "experience"),
             "experience": ("experience", "behaviour", "personal", "technical", "presenting")}
# A part with no question of its own has nothing to prepare, except where it always speaks.
_ALWAYS = ("opening", "close", "format", "approach", "pacing")
# The pieces a round can combine in one sitting, in the order they are named: "personal
# experience, technical coding" is the story in depth, then the problem worked aloud. Each is a
# kind of interview the round's own words say; an acronym nobody spelled out is never read as
# one (the maintainer, 2026-11-10: "never guess what a firm's acronym for a round means").
_PIECES = (
    # "PEI" is the name every consulting recruiter uses for it, not one firm's private one.
    ("personal", re.compile(r"personal[- ]experience|personal stor(?:y|ies)|\bPEIs?\b", re.I),
     "a personal experience interview", (("personal", 20),)),
    # "Practical skills" and a code review are a problem worked in front of them, as a coding
    # round is (an invented round, 2026-11-11: "Practical Skills and Personal Experience").
    ("technical", re.compile(r"\b(?:technical|coding|code|sql|python|hackerrank|leetcode|"
                             r"codesignal|codility|coderpad|statistics|machine learning|"
                             r"system design|data structures|algorithms?|pairing|"
                             r"pair[- ]programming|live coding|practical(?: skills?)?|"
                             r"code review|problem[- ]solving)\b", re.I),
     "a technical interview", (("technical", 22), ("probes", 10))),
    ("case", re.compile(r"\bcase\b(?! study)|market[- ]sizing|guesstimate", re.I),
     "a case", (("case", 12), ("maths", 8), ("synthesis", 6))),
    ("presenting", re.compile(r"take[- ]?home|present(?:ation|ing)? (?:back|your)|case study",
                              re.I),
     "a take-home presented back", (("presenting", 20),)),
    ("behaviour", re.compile(r"\bbehaviou?ral\b|competenc|\bvalues\b|\bculture (?:fit|add)\b|"
                             r"\bbar raiser\b|\bsituational\b|\b(?:cultural|team) fit\b|"
                             r"\bfit (?:interview|questions?|round|conversation)\b", re.I),
     "behavioural questions", (("behaviour", 12),)),
)
_ROOM_OF = {"personal": ("partner", "senior"), "technical": ("technical", "peer"),
            "case": ("partner", "senior"), "presenting": ("technical", "manager"),
            "behaviour": ("manager", "peer")}
# The basics are said plainly and short: a Detailed version of "one month" is padding.
_NO_DETAIL = ("basics",)
MAX_QUESTIONS = 12
SIMPLE_SENTENCES = (2, 4)
# A simple answer is read at a glance mid-interview, each sentence a line of its own on the
# page: none longer than this many words (the UX review, 2026-11-10, U-5).
SIMPLE_WORDS = 30
DETAIL_RATIO = 1.6
# A prep written the live way (2026-11-11): `simple` is a list of points, cue lines to glance at
# mid-call, and `detailed` the script read aloud in the person's own voice. A `simple` still
# written as one string is a prep from before, held to the rules above and never to these.
CUES = (3, 5)
CUES_FOLLOW = (2, 4)
CUES_BASIC = (1, 3)
CUE_WORDS = 10
SCRIPT_WORDS = (80, 200)
SCRIPT_WORDS_FOLLOW = (30, 90)
SCRIPT_AVERAGE = 18
SCRIPT_FIRST = 25
CONTRACTION_EVERY = 60
ESSAY = ("furthermore", "moreover", "additionally", "in conclusion", "whilst", "thereby",
         "in order to", "utilise", "utilize", "leverage")
HOOK_FILLER = ("happy to", "more detail", "if you'd like", "if you want", "i can go into")
# A point is the script's idea in a few words of the person's own: it may share up to three
# words in a row with the script, never four, and it may sum the script up rather than quote
# it. The maintainer, 2026-11-12, on a real prep ("all the content could be better"): points
# made to share the script's words but never five in a row came out as pieces cut from its
# sentences, stopping on "gets" or "under" (here invented: "Every new forecast gets").
CUE_SHARED_RUN = 4
# Words a phrase never stops on, at its end or before a comma inside it: each needs something
# after it. "with", "for" and "about" are left out, as a phrase ends on them naturally ("the
# teams I worked with").
DANGLING = frozenset((
    "a an the my our your their his her its every "
    "of to at by from under into onto through across between than as via per toward towards "
    "and or but nor so because if whether while which whose "
    "gets could should would must might very").split())
# Follow-ups a node: two or three under a question, then up to three, then up to two.
FOLLOW_N = (2, 3)
FOLLOW_MAX = {2: 3, 3: 2}
FOLLOW_Q_WORDS = 12
TERM_PLAIN_WORDS = 25
TERM_LIKE_WORDS = 30
# Which way of an answer leads: the points on a call (the live review, 2026-11-11: the lines
# found at a glance come first, the script to read from under them), unless the person says.
LEADS = ("cues", "script")
LEAD = LEADS[0]
# Capitals anyone reads as a word: never a term to explain.
PLAIN_CAPS = {"I", "OK", "UK", "US", "CEO"}
# Words a person outside the field may not know, said or not: each is explained in the terms
# wherever a live prep says it (`uncovered`). The employer's own words are added from the records.
JARGON = ("MAPE", "regression", "cohort", "pipeline", "ETL", "A/B test", "p-value", "SHAP",
          "XGBoost", "feature", "backtest", "merge", "groupby", "join", "null", "vectorise",
          "SKU", "KPI", "SLA", "stakeholder", "dashboard", "model drift", "IFRS 9", "Basel",
          "PD", "LGD")
# What a coding part holds, each a list (`steps`, `stuck`, `edges`, `code`, `more`).
CODING = ("steps", "stuck", "edges", "code", "more")
STEPS = (4, 7)
STUCK = (2, 4)
EDGES = (3, 6)
CODE_ROWS = (3, 8)
MORE = (2, 4)
MAX_BEATS = 7
MAX_DEPTH = 3
# The follow-ups that come after nearly every story, by who asks them: said once in each part a
# story is told in (the part's `follow`), never under each of its questions, where the same
# three stood again and again (the screen review, 2026-11-11). Their answers are Claude's to
# write from the stories told there.
STORY_FOLLOW = (("manager", "What was your part in it, exactly?"),
                ("technical", "What didn't work?"),
                ("technical", "How did you know it had worked?"),
                ("senior", "Who disagreed, and how did you handle it?"),
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


# Where a beat of what to say first keeps its words: "t" is the engine's own, and a chat has
# written them as plain words or under another name ("text"). The merge read "t" alone, so
# every line written another way was kept as "" and the page drew "Say first" over empty
# bullets, the night before an interview (2026-11-11).
_BEAT_KEYS = ("t", "text", "line", "say")


def _beat_words(beat) -> str:
    """A beat's words to say, however they were written: plain words, or an object holding
    them under "t" (or "text", "line", "say"). "" when it holds none."""
    if isinstance(beat, str):
        return _t(beat)
    if isinstance(beat, dict):
        for key in _BEAT_KEYS:
            if isinstance(beat.get(key), str) and _t(beat[key]):
                return _t(beat[key])
    return ""


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


def _cues(node) -> list:
    """An answer's points as lines: the list written the live way, or an older one-string
    answer split by its sentences, as the page splits it."""
    s = (node or {}).get("simple")
    if isinstance(s, list):
        return [_t(c) for c in s if _t(c)]
    t = _t(s)
    return [x for x in _SENTENCE.split(t) if x.strip()] if t else []


def _said(node) -> str:
    """An answer's points as one text, for the timing, the checks and the Brief."""
    s = (node or {}).get("simple")
    if isinstance(s, list):
        return " ".join(c if c.rstrip().endswith((".", "!", "?")) else c + "."
                        for c in _cues(node))
    return _t(s)


def _live_way(node) -> bool:
    """Is this answer written the live way, its points a list (2026-11-11)?"""
    return isinstance((node or {}).get("simple"), list)


def minutes(n_words, wpm) -> float:
    """Minutes to say `n_words`, to the nearest half."""
    return round(2 * n_words / max(60, int(wpm or WPM))) / 2


def lead() -> str:
    """Which the page shows first in each answer: the points ("cues", the app's default) or the
    script ("script"), as the person said (person.json interview.lead). A tap on the page puts
    the other first on that device, and that wins on it."""
    try:
        v = _t(person.get("interview.lead", LEAD)).lower()
    except (TypeError, ValueError, person.NoProfile):
        v = LEAD
    return v if v in LEADS else LEAD


def wpm() -> int:
    try:
        n = int(person.get("interview.words_per_minute", WPM) or WPM)
    except (TypeError, ValueError, person.NoProfile):
        n = WPM
    return n if 60 <= n <= 300 else WPM


# ---------------------------------------------------------------- the shape

_PANEL = re.compile(r"\bpanel\b", re.I)
# "Onsite" says where an interview is held, not what it is.
_FINAL = re.compile(r"\bfinal\b|last round|\bpartner\b", re.I)
_SCREEN = re.compile(r"\b(?:phone|recruiter|screen\w*|hr|talent|intro\w*)\b", re.I)
_TECH = re.compile(r"\b(?:technical|coding|code|sql|deep dive|system design|pairing)\b", re.I)
# "Second round" says which round, never what kind: it is not read as the hiring manager's.
_MANAGER = re.compile(r"\b(?:hiring manager|manager|competenc\w*|behaviou?ral)\b", re.I)
# A timed test or exercise taken alone, said in so many words ("OA" is the recruiters' own
# name for an online assessment); an assessment centre is a day of several.
_ASSESS = re.compile(r"\b(?:online|timed|aptitude|numerical|verbal|logical|psychometric|"
                     r"reasoning|problem[- ]solving|coding|hackerrank|codesignal|codility)\s+"
                     r"(?:test|assessment|game|exercise|challenge)s?\b|"
                     r"\baptitude\b|\bpsychometric\b|\bassessment\b(?!\s+(?:cent(?:re|er)|day))|"
                     r"(?-i:\bOAs?\b)|\bonline test|\bunproctored\b|\bself[- ]paced\b|"
                     r"\bpymetrics\b|\bSHL\b|\btestgorilla\b", re.I)
# A test named only by what it tests ("SQL test", "technical test"): usually taken alone, and
# said to be a guess.
_TEST = re.compile(r"\b(?:technical|python|sql|coding|code|data|excel|r|numerical)\s+"
                   r"(?:test|challenge)s?\b", re.I)
# Somebody is there with them: the words that make a coding round an interview, not a test.
_LIVE = re.compile(r"\blive\b|\binterview(?:er|ers|s)?\b|\bpair(?:ing| programming)?\b|"
                   r"\bwith (?:an?|the|two|three|our) (?:\w+ )?(?:interviewer|engineer|scientist|"
                   r"analyst|manager|partner|panel)s?\b", re.I)
# A coding site named and nothing else said: usually a test taken alone, and a guess.
_PLATFORM = re.compile(r"\b(hackerrank|codesignal|codility|coderbyte)\b", re.I)
_PLATFORM_NAMES = {"hackerrank": "HackerRank", "codesignal": "CodeSignal",
                   "codility": "Codility", "coderbyte": "Coderbyte"}
# A one-way video interview: questions on the screen and answers recorded.
_RECORDED = re.compile(r"\bhirevue\b|\bone[- ]way\b|\bpre[- ]recorded\b|"
                       r"\brecorded (?:video|interview|answers?)\b|\basynchronous video\b|"
                       r"\bvideo interview\b.{0,20}\brecorded\b|\brecorded\b.{0,20}\bvideo\b",
                       re.I)
# Several interviews back to back in a day; "onsite" alone may only say where one is held.
_DAY = re.compile(r"\bsuper ?day\b|\bvirtual on-?site\b|\bassessment (?:cent(?:re|er)|day)\b|"
                  r"\bback[- ]to[- ]back\b|\binterview day\b|\b(?:full|half)[- ]day\b|"
                  r"\b(?:[2-6]|two|three|four|five|six) (?:\d{2,3}[- ]min(?:ute)?s?[- ])?"
                  r"(?:interviews|rounds|sessions|conversations)\b|"
                  r"\b[2-6]\s*[x\u00d7]\s*\d{2,3}\s*(?:minutes?|mins?)\b", re.I)
_ONSITE = re.compile(r"\bon-?site\b", re.I)


_PROBLEM_SOLVING = re.compile(r"\bproblem[- ]solving\b", re.I)


def pieces(said, consulting=False) -> list:
    """The kinds of interview a round's own words name, in the order they name them. At a
    consulting firm a problem-solving interview is its case."""
    found = []
    for name, rx, _label, _parts in _PIECES:
        hits = [m for m in rx.finditer(said or "")
                if not (consulting and name == "technical" and _PROBLEM_SOLVING.fullmatch(m.group(0)))]
        if hits:
            found.append((hits[0].start(), name))
    if consulting and "case" not in [n for _a, n in found]:
        m = _PROBLEM_SOLVING.search(said or "")
        # A problem-solving test is taken alone, never a case.
        if m and not re.match(r"\s+(?:test|assessment|game|exercise|challenge)", said[m.end():], re.I):
            found.append((m.start(), "case"))
    return [n for _at, n in sorted(found)]


# A part the written prep states with its length: "Practical Skills, about 30 to 45 minutes",
# "Then Personal Experience: Connection, about 15 minutes". The kind is the last one named
# before the minutes, in the same sentence.
_STATED_KIND = re.compile(
    r"\b(?:practical(?: skills?)?|technical|live coding|coding|code review|pair[- ]programming|"
    r"problem[- ]solving|case(?! stud)|market[- ]sizing|personal experience|PEIs?|"
    r"behaviou?ral|competenc\w*|(?:culture|cultural|team) fit|fit (?=interview|questions?|round)|"
    r"take[- ]?home)\b", re.I)
_STATED_MINUTES = re.compile(r"(?:\b(?:about|around|roughly|approximately|up to)\s+|~\s*)?"
                             r"\b(\d{1,3})(?:\s*(?:to|-|\u2013|or)\s*(\d{1,3}))?\s*(?:minutes?|mins?)\b",
                             re.I)
# Stated parts further apart than this are not one round's split.
_STATED_SPAN = 700


def _stated_piece(word, consulting) -> str:
    w = word.lower()
    if re.match(r"personal|pei", w):
        return "personal"
    if re.match(r"case|market", w) or (consulting and _PROBLEM_SOLVING.match(w)):
        return "case"
    if re.match(r"behav|competenc|culture|cultural|team|fit", w):
        return "behaviour"
    if re.match(r"take", w):
        return "presenting"
    return "technical"


def stated_split(ctx, consulting=None) -> list:
    """[(kind, low, high)] as the round's own written words state its parts, each with its
    minutes, in their order: the format first, then the written prep beside it
    (`interview_prep.md`). Only a split of two kinds or more counts, close together and no
    longer in all than the round. The prep is one for the whole hiring process, so a split
    in it is this round's only after the round's name, or where it shares a kind the round's
    own name says: another round's split is never this one's. Empty where nothing states one."""
    if consulting is None:
        import interview_pack as P
        consulting = P.employer_type(ctx) == "consulting"
    label = _t(ctx.get("stage")).lower()
    own = set(pieces(" ".join(_t(x) for x in (ctx.get("stage"), ctx.get("format"))), consulting))
    for source, text in (("format", _t(ctx.get("format"))), ("prep", str(ctx.get("living") or ""))):
        found = []
        for m in _STATED_MINUTES.finditer(text):
            before = re.split(r"[.!?;]\s|\n", text[max(0, m.start() - 90):m.start()])[-1]
            kinds = list(_STATED_KIND.finditer(before))
            if not kinds:
                continue
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) and int(m.group(2)) >= lo else lo
            if not 2 <= lo <= 240:
                continue
            found.append((m.start(), _stated_piece(kinds[-1].group(0), consulting), lo, hi))
        runs, run = [], []
        for item in found:
            if run and item[0] - run[-1][0] > _STATED_SPAN:
                runs.append(run)
                run = []
            run.append(item)
        if run:
            runs.append(run)
        named = text.lower().find(label) if label else -1
        if named >= 0:
            runs.sort(key=lambda r: r[0][0] < named)
        for r in runs:
            split = {}
            for _at, kind, lo, hi in r:
                was = split.get(kind, (0, 0))
                split[kind] = (was[0] + lo, was[1] + hi)
            if len(split) < 2 or sum(lo for lo, _hi in split.values()) > 240:
                continue
            if source == "prep" and not (0 <= named < r[0][0]) and not own & set(split):
                continue
            return [(k, lo, hi) for k, (lo, hi) in split.items()]
    return []


def shape_def(shape) -> tuple:
    """(name, usual minutes, who is in the room, parts) for a shape, a combined sitting's
    ("combined:personal+technical") made from its pieces in their order, with the hello first
    and their questions last."""
    if shape in SHAPES:
        return SHAPES[shape]
    kind, _sep, rest = str(shape).partition(":")
    if kind not in ("combined", "day"):
        raise KeyError(shape)
    defs = {n: (label, parts) for n, _rx, label, parts in _PIECES}
    names = [n for n in rest.split("+") if n in defs]
    label = " and ".join(defs[n][0] for n in names)
    room = tuple(dict.fromkeys(w for n in names for w in _ROOM_OF[n]))
    if kind == "day":
        # Several interviews back to back, each named: the story said fresh to each, every
        # kind named, why them, and a question of their own for each interviewer.
        parts = ((("opening", 15, OPENING_EACH),) + tuple((k, m * 2) for n in names
                                                          for k, m in defs[n][1])
                 + (("motivation", 15), ("close", 25, CLOSE_EACH)))
        room = tuple(dict.fromkeys(room + ("manager", "senior")))
        return ("Several interviews back to back: " + label, 180, room, parts)
    parts = (("opening", 5),) + tuple(p for n in names for p in defs[n][1]) + (("close", 8),)
    return (label[:1].upper() + label[1:] + " in one sitting", 60, room, parts)


def shape_of(ctx) -> tuple:
    """(shape, why it was assumed or ""): the round's own words first (its stage, its format as
    the record, the recruiter or the person says it), then the step, the employer and the role.
    None for an offer, which is a negotiation, not an interview. Two or more kinds named for one
    sitting are one combined prep, in the order they were named; several interviews back to back
    are a day. A round's number ("Second round", "Stage 2") never says its kind: the kind is then
    a guess, and said to be one."""
    import interview_pack as P
    said = " ".join(_t(x) for x in (ctx.get("stage"), ctx.get("format")))
    step = ctx.get("step") or "technical"
    if step == "offer":
        return None, ""
    consulting = P.employer_type(ctx) == "consulting"
    names = pieces(said, consulting)
    # The parts the round's own written words state, each with its minutes, are what it is,
    # whatever one kind its name says: "Practical Skills, about 30 to 45 minutes ... Then
    # Personal Experience, about 15 minutes" is both, in that order (an invented round,
    # 2026-11-11: the hour was all personal questions and nothing for the coding).
    stated = stated_split(ctx, consulting)
    if stated and sum(lo for _k, lo, _hi in stated) <= (_booked_minutes(ctx) or 180):
        names = [k for k, _lo, _hi in stated]
    # Whether anyone is in the room is the format's to say where one is given: "Technical
    # interview" with "CodeSignal General Coding Assessment" is a test taken alone (the review
    # of the fixes, 2026-11-10).
    fmt = _t(ctx.get("format"))
    live = bool(_LIVE.search(fmt if fmt else said))
    if _RECORDED.search(said) and not re.search(r"\blive\b", said, re.I):
        return "recorded", ""
    if set(names) <= {"technical"} and not live and not _DAY.search(said):
        if _ASSESS.search(said):
            return "assessment", ""
        if _TEST.search(said):
            return "assessment", ("a test named by what it tests, with nobody named in the room, "
                                  "is usually taken alone")
    # "Onsite" alone may say only where one interview is held: a day when nothing says one
    # length, and then only a guess unless kinds are named.
    one_length = re.search(r"\b(?:[1-8]\d|90)\s*(?:minutes?|mins?)\b", said, re.I) and not \
        re.search(r"\beach\b|\binterviews\b", said, re.I)
    day = _DAY.search(said) or (_ONSITE.search(said) and not one_length)
    if day:
        if names:
            return "day:" + "+".join(names), ""
        return "superday", ("" if _DAY.search(said) else "an onsite round is usually several "
                            "interviews back to back")
    if len(names) >= 2:
        if names == ["personal", "case"] or (names == ["case", "personal"] and consulting):
            return "case", ""
        return "combined:" + "+".join(names), ""
    platform = _PLATFORM.search(said)
    if names == ["technical"] and platform and not live and not \
            _TECH.search(_PLATFORM.sub(" ", said)) and not _PIECES[1][1].search(_PLATFORM.sub(" ", said)):
        return "assessment", ("a %s round with nobody named is usually a timed test you take "
                              "alone" % _PLATFORM_NAMES[platform.group(1).lower()])
    if _PANEL.search(said):
        return "panel", ""
    if names == ["presenting"]:
        return "take_home", ""
    if names == ["case"]:
        return ("case" if consulting else "case_only"), ""
    if names == ["personal"]:
        return "personal", ""
    if names == ["behaviour"]:
        return "behavioural", ""
    # A technical round said in so many words; a technical screen is a shorter one with the
    # basics a screen checks.
    if names == ["technical"] or _TECH.search(said):
        return ("tech_screen" if _SCREEN.search(said) else "technical"), ""
    if _SCREEN.search(said):
        return "screen", ""
    if consulting and step != "screen":
        return "case", ("a consulting firm's rounds after the screen are usually a case and a "
                        "personal experience interview together")
    if _FINAL.search(said):
        return "final", ""
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


_WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6}
_HOURS = re.compile(r"\b(\d+(?:\.\d+)?|an?|one|two|three|four|five|six)\s*(?:hours?|hrs?)\b"
                    r"(?:\s+and\s+a\s+half)?", re.I)
_EACH = re.compile(r"\b([2-6]|two|three|four|five|six)\s+(?:interviews|rounds|sessions|"
                   r"conversations)\b[^.;]{0,40}?\b(\d{2,3})\s*(?:minutes?|mins?)\b|"
                   r"\b([2-6])\s*[x\u00d7]\s*(\d{2,3})\s*(?:minutes?|mins?)\b|"
                   r"\b([2-6]|two|three|four|five|six)\s+(\d{2,3})[- ]min(?:ute)?s?[- ]"
                   r"(?:interviews|rounds|sessions|conversations)\b", re.I)


def round_minutes(ctx, shape, stated=None) -> int:
    """The round's length as booked, else the shape's usual length, or the parts the written
    prep states where they take longer."""
    return _booked_minutes(ctx) or max(shape_def(shape)[1],
                                       sum(hi for _k, _lo, hi in stated or ()))


def _booked_minutes(ctx) -> int:
    """The round's length as booked or said, 0 where nothing says it."""
    label = _t(ctx.get("stage")).lower()
    for s in ctx.get("stages") or []:
        if _t(s.get("label")).lower() == label and int(s.get("minutes") or 0) > 0:
            return int(s["minutes"])
    said = "%s %s" % (_t(ctx.get("stage")), _t(ctx.get("format")))
    # Several interviews of a length each: the day is all of them.
    m = _EACH.search(said)
    if m:
        n = m.group(1) or m.group(3) or m.group(5)
        n = int(n) if n.isdigit() else _WORD_NUMBERS[n.lower()]
        return n * int(m.group(2) or m.group(4) or m.group(6))
    m = re.search(r"\b(\d{2,3})\s*(?:minutes?|mins?)\b", said, re.I)
    if m and 10 <= int(m.group(1)) <= 240:
        return int(m.group(1))
    m = _HOURS.search(said)
    if m:
        n = m.group(1).lower()
        hours = float(n) if n[0].isdigit() else _WORD_NUMBERS[n]
        hours += 0.5 if re.search(r"and a half", m.group(0), re.I) else 0
        if 0.25 <= hours <= 9:
            return int(round(hours * 60))
    return 0


def _piece_of(kind) -> str:
    """The kind of interview a part belongs to ("probes" is the technical interview's)."""
    return next((n for n, _rx, _label, pp in _PIECES if any(k == kind for k, _m in pp)), "")


def stated_for(ctx, shape) -> list:
    """The written split (`stated_split`) where it is the one this shape was built from: a
    sitting of several kinds whose parts are exactly the kinds stated."""
    stated = stated_split(ctx)
    if not stated:
        return []
    have = {_piece_of(p[0]) for p in shape_def(shape)[3]} - {""}
    return stated if have == {k for k, _lo, _hi in stated} else []


def _stated_minutes(parts, total, stated):
    """Each stated kind's minutes as the prep gives them (a range is its middle), shared among
    its own parts as they usually are; the hello and their questions take what is left, never
    under two minutes each. None where the parts are not the kinds stated."""
    want = {k: int(round((lo + hi) / 2.0)) for k, lo, hi in stated}
    groups, edges = {}, []
    for i, p in enumerate(parts):
        n = _piece_of(p[0])
        if n in want:
            groups.setdefault(n, []).append(i)
        else:
            edges.append(i)
    if set(groups) != set(want) or not edges:
        return None
    room = total - 2 * len(edges)
    if room < 2 * sum(len(ix) for ix in groups.values()):
        return None
    if sum(want.values()) > room:
        # Longer in all than the round: each kind keeps its share of what there is.
        scale = room / float(sum(want.values()))
        want = {k: max(2 * len(groups[k]), int(v * scale)) for k, v in want.items()}
    got = [0] * len(parts)
    for n, ix in groups.items():
        usual = sum(parts[i][1] for i in ix)
        share = [max(2, int(round(parts[i][1] * want[n] / float(usual)))) for i in ix]
        share[share.index(max(share))] += want[n] - sum(share)
        for i, m in zip(ix, share):
            got[i] = m
    rest = total - sum(got)
    usual = sum(parts[i][1] for i in edges)
    for i in edges:
        got[i] = max(2, int(round(parts[i][1] * rest / float(usual))))
    while sum(got) != total:
        step = 1 if sum(got) < total else -1
        pool = [i for i in edges if step > 0 or got[i] > 2] or \
            [i for i in range(len(got)) if step > 0 or got[i] > 2]
        got[max(pool, key=lambda i: got[i])] += step
    return got


def _part_minutes(shape, total, stated=None) -> list:
    parts = shape_def(shape)[3]
    got = _stated_minutes(parts, total, stated) if stated else None
    if got:
        return got
    usual = sum(p[1] for p in parts)
    got = [max(2, int(round(p[1] * total / usual))) for p in parts]
    # Rounding never takes the parts past the round itself.
    while sum(got) > total and max(got) > 2:
        got[got.index(max(got))] -= 1
    # Nor short of it: a minute rounding lost goes to the longest stop.
    while sum(got) < total:
        got[got.index(max(got))] += 1
    return got


def kind_of(question) -> str:
    q = _t(question)
    return next((k for k, rx in _KIND_OF if rx.search(q)), "experience")


def _place(kind, kinds, strict=False) -> str:
    """The part a question of this kind is asked in. `strict`: None where the round has no
    part for it (a case interview asks no "What is your experience with SAP?" as its case);
    otherwise the nearest part, for a question they are known to ask, which is always placed."""
    order = _FALLBACK.get(kind, (kind,))
    if strict:
        # The hello holds the introduction and why them, nothing else: pay or notice the records
        # bring to a round with no part for them is left for the pack (the maintainer,
        # 2026-11-12, of a mixed round whose opening held a question about the work).
        order = tuple(k for k in order if k != "opening" or kind in ("opening", "motivation"))
    hit = next((k for k in order if k in kinds), None)
    if hit or strict:
        return hit
    return "experience" if "experience" in kinds else kinds[1] if len(kinds) > 2 else kinds[0]


# What each part usually asks where the records hold nothing for it: the pack's own stock
# questions, so the answers come from the person's stories and stock answers as any other.
_POOL_FOR = ("opening", "motivation", "basics", "experience", "behaviour", "personal",
             "technical", "probes", "presenting")


def _pool(kind, ctx) -> list:
    import interview_pack as P
    fp, sq = P.FORMAT_PREP, P.STAGE_QUESTIONS
    company = ctx.get("company") or "us"
    pools = {
        "opening": sq["technical"][1:2],
        "motivation": (sq["final"][0], sq["screen"][1], sq["final"][2]),
        "basics": (sq["screen"][3], sq["screen"][5]),
        "experience": sq["technical"][:1],
        "behaviour": fp["behavioural"]["questions"],
        "personal": fp["behavioural"]["questions"][:2] + sq["technical"][:1],
        "technical": fp["coding"]["questions"] + fp["technical"]["questions"][:1],
        "probes": ("What are the trade-offs in your approach?", "How would it scale to ten times the data?"),
        "presenting": fp["presentation"]["questions"],
    }
    return [q.format(company=company) for q in pools.get(kind, ())]


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


def employer_terms(ctx) -> dict:
    """The words already explained in this employer's own work by another interview's live
    prep there (another role's folder), so a second prep starts from them and Claude writes
    only the new ones. This folder's own saved prep is merged in by `merge`."""
    import docpaths
    here = os.path.basename(os.path.normpath(ctx.get("folder") or ""))
    out = {}
    base = person.state("documents", "applications")
    for name in docpaths.employer_folders(ctx["company"]):
        if name == here:
            continue
        doc = load(os.path.join(base, name))
        for k, v in ((doc or {}).get("terms") or {}).items():
            if isinstance(v, dict) and k not in out:
                out[k] = v
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
    name, _usual, room, parts_def = shape_def(shape)
    # A partner asks at a consulting firm; anywhere else the same seat is the hiring manager's.
    if P.employer_type(ctx) != "consulting":
        room = tuple(dict.fromkeys("manager" if w == "partner" else w for w in room))
    stated = stated_for(ctx, shape)
    total = round_minutes(ctx, shape, stated)
    kinds = [d[0] for d in parts_def]
    mins = _part_minutes(shape, total, stated)
    parts = [{"id": "p%d" % (i + 1), "kind": d[0],
              "title": d[2] if len(d) > 2 else PART_TITLES[d[0]], "short": PART_SHORT[d[0]],
              "minutes": m,
              "who": _who(d[0], room), "say": [], "bridge": "", "questions": [], "follow": []}
             for i, (d, m) in enumerate(zip(parts_def, mins))]
    by_kind = {p["kind"]: p for p in parts}
    st_list = list(ctx.get("stories") or [])
    stories = [{"id": _story_id(i), "title": s["title"], "proves": _proves(s),
                "star": {k: _t(s["star"].get(k)) for k in "STAR" if _t(s["star"].get(k))},
                "questions": []} for i, s in enumerate(st_list)]
    sid = {s["title"].lower(): stories[i]["id"] for i, s in enumerate(st_list)}
    # A test taken alone asks nothing of the interview's kind: its items to practise are
    # Claude's to write, from what the test covers.
    items = [] if shape in ("assessment",) else list(P.likely_questions(ctx))
    placed = []
    # A question every story already brings as a follow-up ("What would you do differently
    # now?") is asked there, once, never also as a question of its own (2026-11-10).
    follows = {_norm(fq) for _w, fq in STORY_FOLLOW} if ctx.get("stories") else set()
    for item in items:
        if _norm(item["question"]) in follows:
            continue
        k = _place(kind_of(item["question"]), kinds, strict=True)
        if k:
            placed.append((item, k))
    # A part a person answers in with no question of the records' own takes the questions its
    # kind of interview usually brings: a manager's "Times you did it" and "Why this role" were
    # empty while six questions sat in "Your work" (2026-11-10).
    have = {_norm(i["question"]) for i, _k in placed} | follows
    for k in kinds:
        if k in _POOL_FOR and not any(pk == k for _i, pk in placed):
            for text in _pool(k, ctx):
                if _norm(text) not in have:
                    placed.append(({"question": text, "why": "what this kind of interview usually asks",
                                    "source": "the format"}, k))
                    have.add(_norm(text))
    ctx = dict(ctx)
    ctx["plan"] = P.plan_stories([i for i, _k in placed], ctx)
    questions = []
    # As many questions as the round has time for: a 20 minute screen is short, an hour long.
    # Every part with questions keeps its first; the rest in the order they are likeliest.
    cap = max(4, min(MAX_QUESTIONS, int(round(total / 5.0))))
    # A count the invite gives ("HireVue, 5 questions") is the count prepared.
    said_n = re.search(r"\b(\d{1,2}|three|four|five|six|seven|eight|nine|ten)\s+questions\b",
                       "%s %s" % (_t(ctx.get("stage")), _t(ctx.get("format"))), re.I)
    if said_n:
        n = said_n.group(1).lower()
        n = int(n) if n.isdigit() else dict(_WORD_NUMBERS, seven=7, eight=8, nine=9, ten=10)[n]
        cap = max(1, min(MAX_QUESTIONS, n))
    first = {}
    for n, (_i, k) in enumerate(placed):
        first.setdefault(k, n)
    keep = sorted(first.values())[:cap]
    keep += [n for n in range(len(placed)) if n not in keep][:max(0, cap - len(keep))]
    for n, (item, k) in enumerate(placed):
        if n not in keep:
            continue
        part = by_kind[k]
        ans = P.answer_for(item, ctx)
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
             # Its own follow-ups only: those after any story are the part's (finish).
             "follow": []}
        questions.append(q)
        part["questions"].append(q["id"])
    # The known questions, each placed as a question of its own, or on the one it already is.
    known = []
    for i, k in enumerate(known_questions(ctx)):
        kid = "k%d" % (i + 1)
        known.append(dict(k, id=kid, question=None))
    _place_known(known, questions, parts, room)
    asks = []
    # A test taken alone, or a recorded interview, has nobody to ask.
    for ln in (P.ask_lines(ctx) if "close" in kinds else []):
        text = P.plain_line(ln)[0]
        q, why = P._last_parens(text)
        q = said_ask(q)
        if q.endswith("?") and not any(_norm(a["q"]) == _norm(q) for a in asks):
            asks.append({"id": "a%d" % (len(asks) + 1), "q": q, "why": why,
                         "follow": []})
    if "close" in kinds:
        asks.append({"id": "a%d" % (len(asks) + 1), "q": P.CLOSE_QUESTION,
                     "why": "the last word on any doubt, while you are still in the room",
                     "follow": []})
    doc = {"version": VERSION, "built": ctx.get("today") or dt.date.today().isoformat(),
           "company": ctx["company"], "role": ctx.get("role") or "", "stage": ctx.get("stage") or "",
           "date": ctx.get("date") or "", "with": ctx.get("with") or "", "format": _t(ctx.get("format")),
           "shape": shape, "shape_name": name, "assumed": assumed, "minutes": total,
           "wpm": wpm(), "lead": lead(), "room": list(room), "parts": parts, "questions": questions,
           "stories": stories, "ask": asks, "terms": employer_terms(ctx), "known": known,
           "private": private_notes(ctx)}
    return finish(doc)


# A question to ask anchored on what was read, as the pack writes it for the person to see
# where it came from ('The research says "Opened a cross-dock in January". What has that
# changed for your team?'), is read aloud as written in the minutes before. The live prep
# says it the way a person would.
_ANCHORED = re.compile(r"^The (research says|posting describes) [\"“](.+?)[\"”]\.?\s+(.+)$")
_DID = re.compile(r"^(?:\w+ed|won|began|bought|made|set|led|grew|built|ran|took|became|"
                  r"launched|raised|opened|moved|hired|cut|sold|split|spun|chose)\b", re.I)


def _lc(text) -> str:
    """Its first letter small, unless the first word is a name or an acronym."""
    t = _t(text)
    return t[:1].lower() + t[1:] if t[:1].isupper() and t[1:2].islower() else t


# A fact said as the reason for a question is short and whole: past this many words, or cut
# short where it was read, the question is asked on its own (the maintainer, 2026-11-12: a real
# prep pasted a fact cut short, the role's title and city in brackets, in front of the question).
ASK_FACT_WORDS = 14
# A question that leans on the fact before it, as it is asked with no fact said.
_ASK_ALONE = {
    "is that still how the team is set up?": "How is the team set up today?",
    "what does that mean for headcount on this team?": "Is the team growing this year?",
    "what has that changed for your team?": "What has changed most for your team this year?",
    "how much of that reaches the work day to day?": "What does the work look like day to day?",
    "what is the part of that an outsider would get wrong?":
        "What would an outsider most often get wrong about the work here?",
    "what is the first thing it needs someone to fix?":
        "What is the first thing this role needs someone to fix?",
}


def _said_fact(fact) -> str:
    """A fact read about them as it can be said aloud: what is in brackets taken out, its end
    tidied. "" when it was cut short where it was read, or is too long to say in a breath."""
    t = _t(fact)
    clipped = t.endswith(("...", "\u2026"))
    while True:
        u = re.sub(r"\s*[(\[][^()\[\]]*[)\]]", "", t)
        if u == t:
            break
        t = u
    t = _t(t).rstrip(".!\u2026 ")
    if clipped or not t or re.search(r"[()\[\]\"\u201c\u201d;:]", t) or len(_WORD.findall(t)) > ASK_FACT_WORDS:
        return ""
    return t


def said_ask(question) -> str:
    """A question to ask them as it would be said, a short reason and then the question: 'I saw
    you opened a cross-dock in January. What has that changed for your team?'. A fact too long
    to say, or cut short where it was read, is never pasted in: the question is asked on its own
    ('What has changed most for your team this year?'). Anything else is left as it is."""
    m = _ANCHORED.match(_t(question))
    if not m:
        return _t(question)
    kind, tail = m.group(1), _t(m.group(3))
    tail = tail[:1].upper() + tail[1:]
    fact = _said_fact(m.group(2))
    if not fact:
        return _ASK_ALONE.get(tail.lower(), tail)
    # A name keeps its capital ("Fernhill Freight runs ..."); an ordinary first word does not.
    common = _lc(fact) if _DID.match(fact) or re.match(
        r"(?i)(?:the|a|an|its|their|it|this|they|there|more|most|over|about)\b", fact) else fact
    if kind == "posting describes":
        lead = "I saw the role covers %s" % common
    elif _DID.match(fact):
        lead = "I saw you %s" % common
    else:
        lead = "I read that %s" % common
    return "%s. %s" % (lead, tail)


def _ask_like(q, olds):
    """The question to ask among `olds` (keyed by their words) that is `q` said another way,
    taken out of `olds`; None when there is none. A prep saved before 2026-11-12 says them
    "I read that <fact>, so <question>", and its follow-ups stay with the question."""
    mine = _content(q)
    best, score = None, 0.0
    for key, a in olds.items():
        theirs = _content(a.get("q"))
        if len(mine) < 2 or len(theirs) < 2:
            continue
        n = len(mine & theirs) / float(min(len(mine), len(theirs)))
        if n > score:
            best, score = key, n
    return olds.pop(best) if best is not None and score >= 0.8 else None


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
    # A gap is said once, as a note of its own with how to put it (below): never also as a
    # line of what not to say (the review, 2026-11-10).
    gap_names = [_t(g.get("gap")) for g in (ctx.get("facts") or {}).get("gaps") or [] if _t(g.get("gap"))]
    not_say = [P.plain_line(ln)[0] for ln in P.do_not_say(ctx)
               if not any(re.match(r"- Never claim %s\b" % re.escape(n), ln) for n in gap_names)]
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
        gap = _t(g.get("gap"))
        said, clause, note = P._gap_words(gap, ctx.get("posting") or "")
        what = gap if not said or said.lower() in gap.lower() else "%s (%s)" % (gap, said)
        # A qualification in the posting's own words ("CIPS membership"), never the label the
        # profile's map files it under ("Chartered procurement").
        own = re.sub(r"(?i)\s+(?:is|are|was|will be|would be)\b.*$", "", _t(clause)).strip(" .,;:")
        if said and P._CREDENTIAL.search(" ".join((gap, clause, note))) and said in own and len(own) <= 40:
            what = own[:1].upper() + own[1:] if own[:1].islower() else own
        if _t(g.get("framing")):
            # The line to say, said to be one: a first-person line alone read as a note.
            frame = "Say: \u201c%s\u201d" % _t(g.get("framing")).rstrip()
        elif P._CREDENTIAL.search(" ".join((gap, clause, note))):
            frame = ("You do not hold it, so never claim it. Say so plainly, then the nearest "
                     "true thing.")
        else:
            frame = ("Never claim it. Say plainly you have not done it as such, then the nearest "
                     "true thing.")
        weak.append({"what": what, "frame": frame})
    for m in P.landmines(ctx):
        what = _t(m.get("what"))
        frame = _frame(m.get("framing"))
        if what:
            weak.append({"what": what, "frame": frame or "Say it plainly and briefly, then what "
                                                         "you did next."})
    return {"pay": P.plain_line(pay)[0] if pay else "",
            "notice": notice, "based": based,
            "not_to_say": [x for x in not_say if x], "figures": figures,
            "weaknesses": weak, "red_flags": list(RED_FLAGS), "confirm": []}


_EVIDENCE = re.compile(r"^(?:From your profile|Say|Prepared):", re.I)


def _frame(lines) -> str:
    """How to put a place they may push, as sentences for the person: what to do first, then
    what the profile holds to say it with, each ending where it ends. The lines were joined as
    they came, so "...ending a daily two-hour reconciliation Name the work..." ran on (the
    review, 2026-11-10), and a line clipped for the pack ended on "an estimated..."."""
    import interview_pack as P
    said = [x for x in (P.plain_line(ln)[0] for ln in lines or []) if _t(x)]
    out = []
    for x in [x for x in said if not _EVIDENCE.match(x)] + [x for x in said if _EVIDENCE.match(x)]:
        x = _t(x)
        if x.endswith("..."):
            # Clipped: back to the last whole clause, never a sentence cut mid-way.
            x = re.sub(r",[^,]*\.\.\.$", "", x) if "," in x else x[:-3].rstrip()
        out.append(x if re.search(r"[.!?\u201d\"]$", x) else x.rstrip(",;: ") + ".")
    return " ".join(out)


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
        part = (parts.get(kind) or parts.get(_place(kind_of(old["q"]), list(parts)))
                or doc["parts"][-1])
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
            # A beat with no words under any name is left out, never kept as an empty line.
            text = _beat_words(b)
            if not text:
                continue
            b = b if isinstance(b, dict) else {}
            beat = {"t": text}
            prompts = [new_qid.get(old_qid.get(x)) for x in b.get("prompts") or []]
            beat["prompts"] = [x for x in prompts if x]
            if b.get("known"):
                beat["known_text"] = known_text.get(b["known"]) or _norm(b["known"])
            say.append(beat)
        part["say"] = say
        if _t(old.get("bridge")):
            part["bridge"] = _t(old["bridge"])
        if _t(old.get("title")):
            part["title"] = _t(old["title"])
        if old.get("follow"):
            part["follow"] = old["follow"]
        for f in CODING:
            if isinstance(old.get(f), list) and old[f]:
                part[f] = old[f]
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
    # Terms are Claude's alone: this prep's own, over those another prep at the employer has.
    doc["terms"] = dict(doc.get("terms") or {})
    doc["terms"].update({k: v for k, v in (filled.get("terms") or {}).items() if isinstance(v, dict)})
    # The questions to ask: the records' with Claude's follow-ups, then Claude's own.
    old_ask = {_norm(said_ask(a.get("q"))): a for a in filled.get("ask") or []}
    for a in doc["ask"]:
        old = old_ask.pop(_norm(a["q"]), None) or _ask_like(a["q"], old_ask)
        if old and old.get("follow"):
            a["follow"] = old["follow"]
    for old in old_ask.values():
        if _t(old.get("q")):
            doc["ask"].insert(len(doc["ask"]) - 1, {"id": "a%d" % (len(doc["ask"]) + 1),
                                                    "q": said_ask(old["q"]), "why": _t(old.get("why")),
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


def is_copy(filled) -> bool:
    """Is a --fill file a whole copy of the prep, as older chats wrote it?"""
    return isinstance(filled, dict) and isinstance(filled.get("parts"), list) \
        and isinstance(filled.get("questions"), list)


# The shape each key of a words file takes (`words_into`).
_WORDS_SHAPE = {"parts": dict, "questions": dict, "new": list, "known": list, "terms": dict,
                "ask": dict, "ask_new": list, "confirm": list}


def words_shape(words) -> str:
    """What is wrong with a words file's shape, in plain words, or "" when it is fit."""
    if not isinstance(words, dict):
        return ("the words file is not one: write an object with parts, questions and the rest "
                "(interview.md Step 3b), never a list")
    for k, want in _WORDS_SHAPE.items():
        if k in words and not isinstance(words[k], want):
            return ("the words file's \"%s\" is %s: write it as %s (interview.md Step 3b)"
                    % (k, "a list" if isinstance(words[k], list) else "the wrong shape",
                       "an object keyed by id" if want is dict else "a list"))
    for k in ("parts", "questions"):
        for key, w in (words.get(k) or {}).items():
            if not isinstance(w, dict):
                return ("the words file's \"%s\" entry %r is not an object of words: write it "
                        "as {\"say\": [...]} or {\"simple\": \"...\"} (interview.md Step 3b)" % (k, key))
    for key, w in (words.get("parts") or {}).items():
        for f in CODING:
            if f in w and not isinstance(w[f], list):
                return ("the words file's part %r writes \"%s\" as one value: write it as a list "
                        "(interview.md Step 3b)" % (key, f))
        if "say" in w and not isinstance(w["say"], list):
            return ("the words file's part %r writes \"say\" as one value: write it as a list of "
                    "lines, [{\"t\": \"<the words to say>\", \"prompts\": [...]}] (interview.md "
                    "Step 3b)" % key)
        for i, b in enumerate(w.get("say") or []):
            if not _beat_words(b):
                return ("the words file's part %r has a line to say first with no words in it "
                        "(line %d): write each as {\"t\": \"<the words to say>\", \"prompts\": "
                        "[...]} (interview.md Step 3b)" % (key, i + 1))
    return ""


def words_into(base, words) -> dict:
    """The prep `base` (as built, with what was written before) with only the words Claude
    wrote put in, in the form `merge` keeps. Claude writes the words alone, keyed by part and
    question, and code puts them in their place: re-writing the whole built file to fill it
    was 37k characters, about 20k of them the engine's own (the efficiency audit, 2026-11-10).

    {"parts": {"<part id or kind>": {"say": [{"t", "prompts", "known"}], "bridge", "title",
               "follow": [{"who", "q", "simple", ...}]}},
     "questions": {"<question id or its words>": {"simple", "detailed", "also", "follow",
                   "who", "story", "draft"}},
     "new": [{"part": "<part id or kind>", "who", "q", "simple", ...}],
     "known": [{"text", "from"}], "terms": {...},
     "ask": {"<ask id or its words>": [{"if", "then"}]}, "ask_new": [{"q", "why", "follow"}],
     "confirm": ["..."]}

    A part, question or question to ask the words name that is not in the prep is an error,
    said in plain words: nothing written is dropped without a word."""
    wrong = words_shape(words or {})
    if wrong:
        raise ValueError(wrong)
    doc = json.loads(json.dumps(base))
    words = words or {}
    parts = doc["parts"]

    def part_of(key):
        hit = next((p for p in parts if p["id"] == key), None) or \
            next((p for p in parts if p["kind"] == key), None)
        if hit is None:
            raise ValueError("the words name a part %r that this prep does not have: its parts "
                             "are %s" % (key, ", ".join("%s (%s)" % (p["id"], p["kind"]) for p in parts)))
        return hit

    for key, w in (words.get("parts") or {}).items():
        part = part_of(key)
        for f in ("say", "bridge", "title", "follow") + CODING:
            if f in (w or {}):
                part[f] = w[f]
    byid = {q["id"]: q for q in doc["questions"]}
    bytext = {_norm(q["q"]): q for q in doc["questions"]}
    for key, w in (words.get("questions") or {}).items():
        q = byid.get(key) or bytext.get(_norm(key))
        if q is None:
            raise ValueError("the words answer a question %r that is not in this prep: add it "
                             "under \"new\" with its part" % key)
        for f in _Q_WRITTEN + ("story",):
            if f in (w or {}):
                q[f] = w[f]
    taken = {q["id"] for q in doc["questions"]}
    for i, w in enumerate(words.get("new") or []):
        if not isinstance(w, dict) or not _t(w.get("q")):
            continue
        qid = _t(w.get("id")) or "new%d" % (i + 1)
        if qid in taken:
            # Another question's id would repoint every "Likely to prompt" link to it.
            raise ValueError("the new question %r is given the id %s, which is already a "
                             "question's: give it an id of its own, like new%d"
                             % (_t(w["q"]), qid, i + 1))
        taken.add(qid)
        q = {"id": qid, "part": part_of(w.get("part"))["id"],
             "who": w.get("who") or "", "q": _t(w["q"]), "also": w.get("also") or [],
             "simple": w.get("simple") or "", "detailed": w.get("detailed") or "",
             "story": w.get("story"), "known": None, "draft": bool(w.get("draft")),
             "from": [], "follow": w.get("follow") or []}
        doc["questions"].append(q)
    if words.get("known"):
        have = {_norm(k.get("text")) for k in doc.get("known") or []}
        doc["known"] = list(doc.get("known") or []) + [
            k for k in words["known"] if _t(k.get("text")) and _norm(k["text"]) not in have]
    if isinstance(words.get("terms"), dict):
        doc["terms"] = dict(doc.get("terms") or {}, **words["terms"])
    asks = doc.get("ask") or []
    for key, follow in (words.get("ask") or {}).items():
        a = next((a for a in asks if a["id"] == key or _norm(a["q"]) == _norm(key)), None)
        if a is None:
            raise ValueError("the words follow up a question to ask %r that is not in this "
                             "prep: add it under \"ask_new\"" % key)
        a["follow"] = follow
    for w in words.get("ask_new") or []:
        if _t((w or {}).get("q")):
            asks.insert(max(0, len(asks) - 1), {"id": "x", "q": _t(w["q"]), "why": _t(w.get("why")),
                                                "follow": w.get("follow") or []})
    doc["ask"] = asks
    for x in words.get("confirm") or []:
        if _t(x) and _t(x) not in doc["private"]["confirm"]:
            doc["private"]["confirm"].append(_t(x))
    return doc


# A problem as it is set: a task, never a question about past work.
_TASK = re.compile(r"^(?:given\b|write\b|build\b|design\b|implement\b|find\b|calculate\b|"
                   r"estimate\b|code\b|create\b|you have\b|here(?:['\u2019]s| is)\b|"
                   r"how would you (?:build|design|implement|write|code|model|find|approach)\b)", re.I)


def _follow_once(part, mine) -> None:
    """The follow-ups said once in a part: those after any story, where a story is told there,
    and any written under two or more of its questions. Each is lifted off its questions onto
    the part (`follow`), keeping the first words written for it and the story they tell, so a
    question keeps only follow-ups of its own (the screen review, 2026-11-11: the same three
    stood under every question of a part)."""
    own = [f for f in part.get("follow") or [] if isinstance(f, dict) and _t(f.get("q"))]
    have = {_norm(f["q"]): f for f in own}
    told = any(q.get("story") for q in mine)
    under: dict = {}
    for q in mine:
        for f in q.get("follow") or []:
            under.setdefault(_norm(f.get("q")), set()).add(q["id"])
    story = {_norm(fq) for _w, fq in STORY_FOLLOW} if told else set()
    lift = {k for k, qs in under.items() if len(qs) > 1 or k in have or k in story}
    for q in mine:
        kept = []
        for f in q.get("follow") or []:
            k = _norm(f.get("q"))
            if k not in lift:
                kept.append(f)
                continue
            got = have.get(k)
            if got is None:
                got = have[k] = {"who": f.get("who") or "", "q": _t(f.get("q")), "also": [],
                                 "simple": "", "detailed": "", "follow": []}
                own.append(got)
            if not _said(got) and _said(f):
                for key in ("who", "also", "simple", "detailed", "follow", "draft"):
                    if f.get(key) not in (None, "", []):
                        got[key] = f[key]
                if q.get("story"):
                    got["story"] = q["story"]
        q["follow"] = kept
    if told:
        for w, fq in STORY_FOLLOW:
            if _norm(fq) not in have:
                have[_norm(fq)] = {"who": w, "q": fq, "also": [], "simple": "", "detailed": "",
                                   "follow": []}
                own.append(have[_norm(fq)])
    part["follow"] = own


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
        # The problem as set leads "A problem, worked aloud", ahead of questions about past
        # code (the night-before run, 2026-11-10).
        mine = [q for q in doc["questions"] if q["part"] == p["id"]]
        if p["kind"] in ("technical", "practice"):
            mine.sort(key=lambda q: not _TASK.search(_t(q.get("q"))))
        p["questions"] = [q["id"] for q in mine]
        _follow_once(p, mine)
        n = sum(words(b.get("t"), terms) for b in p["say"]) + words(p.get("bridge"), terms)
        n += sum(words(_said(q), terms) for q in doc["questions"] if q["part"] == p["id"])
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


# Where an answer's points are said, as `spoken` names them: cue lines to glance at, never
# held to the rules for sentences (choppy, two to four of them).
POINTS = "the points"
# Where a coding part's lines are said: short on purpose, never held to flowing sentences.
CODING_LINE = "while coding"


def _answer_texts(node, where, draft, question):
    if _live_way(node):
        if _cues(node):
            yield ("%s, %s" % (where, POINTS), _said(node), draft, question)
    elif _t(node.get("simple")):
        yield ("%s, simple answer" % where, node["simple"], draft, question)
    if _t(node.get("detailed")):
        yield ("%s, detailed answer" % where, node["detailed"], draft, question)


def _coding_lines(p):
    """(where, text) for what a coding part has the person say: each step, what to say when
    stuck, the cases to name, what each piece of code means and what they would do next."""
    title = p.get("title")
    for i, st in enumerate(p.get("steps") or []):
        if isinstance(st, dict):
            for key in ("t", "say"):
                if _t(st.get(key)):
                    yield ("\"%s\", step %d, %s" % (title, i + 1, CODING_LINE), st[key])
    for key, name in (("stuck", "if you are stuck"), ("edges", "a case to name"),
                      ("more", "with more time")):
        for i, x in enumerate(p.get(key) or []):
            if isinstance(x, str) and _t(x):
                yield ("\"%s\", %s (%d), %s" % (title, name, i + 1, CODING_LINE), x)
    for i, c in enumerate(p.get("code") or []):
        if isinstance(c, dict) and _t(c.get("means")):
            yield ("\"%s\", what code line %d means, %s" % (title, i + 1, CODING_LINE), c["means"])


def spoken(doc):
    """(where, text, draft, question) for everything the person will say aloud."""
    qs = {q["id"]: q for q in doc.get("questions") or []}
    for p in doc.get("parts") or []:
        for i, b in enumerate(p.get("say") or []):
            yield ("\"%s\", what to say first (%d)" % (p.get("title"), i + 1), b.get("t"), False, "")
        if _t(p.get("bridge")):
            yield ("\"%s\", what to say first (the line to end on)" % p.get("title"),
                   p["bridge"], False, "")
        for where, text in _coding_lines(p):
            yield (where, text, False, "")
        for f, _d, here in _nodes(p, where="\"%s\", after any story" % p.get("title")):
            yield from _answer_texts(f, here, bool(f.get("draft")), f.get("q") or "")
    for q in qs.values():
        where = "\"%s\"" % _t(q.get("q"))
        yield from _answer_texts(q, where, bool(q.get("draft")), q["q"])
        for f, _d, here in _nodes(q, where=where):
            yield from _answer_texts(f, here, bool(q.get("draft") or f.get("draft")), q["q"])
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


# Clipped fragments are hard to say aloud: "Their care history. Their frailty." Two short
# sentences in a row, or an answer whose sentences average under about eight words, is one.
CHOPPY_SHORT = 4
CHOPPY_AVERAGE = 8
CHOPPY = "it reads as clipped fragments: write this as flowing sentences, joined with commas and \"and\""


def choppy(text, terms=None) -> bool:
    """Is this written as clipped fragments rather than sentences a person would say?"""
    t = _t(plain(text, terms))
    counts = [len(_WORD.findall(s)) for s in _SENTENCE.split(t) if s.strip()]
    if len(counts) < 2:
        return False
    if any(a <= CHOPPY_SHORT and b <= CHOPPY_SHORT for a, b in zip(counts, counts[1:])):
        return True
    return sum(counts) / float(len(counts)) < CHOPPY_AVERAGE


_STOP = frozenset((
    "a an and the of to in on for at by with from as is was "
    "were be been are it its this that these those i i'm i've i'd we you "
    "your my our they their them he she his her or but so if then than "
    "not no do did does done have has had will would could should can just about "
    "into over out up what which who how when where why there here very really also "
    "more most some any all each one two three me us what's that's it's don't didn't").split())
_CONTRACTION = re.compile(r"\b\w+['\u2019](?:s|re|ve|d|ll|t|m)\b", re.I)
_NUM = re.compile(r"(?:^|(?<=[\s(~]))([£$€]?\d[\d,.]*\s?(?:%|k|K|M|B|bn|x|pp)?\+?)(?=[\s.,;:)!?]|$)")


def _content(text, terms=None) -> set:
    """The words that carry a text's meaning, each by its first five letters, so "trusted"
    meets "trust" and the small words never count."""
    out = set()
    for w in _WORD.findall(plain(text, terms).lower()):
        w = w.replace("\u2019", "'").strip("'.,")
        if len(w) > 2 and w not in _STOP and not w[0].isdigit():
            out.add(_stem(w))
    return out


def _stem(w) -> str:
    """A word by its first five letters once an ending is off: "tests", "tested" and "test"
    are one word, as are "trusted" and "trust"."""
    for end in ("ing", "ed", "s"):
        if len(w) > len(end) + 2 and w.endswith(end) and not w.endswith("ss"):
            w = w[:-len(end)]
            break
    return w[:5]


def _numbers(text, terms=None) -> set:
    return {m.group(1).rstrip(".,").replace(" ", "") for m in _NUM.finditer(plain(text, terms))}


def _runs(text, terms=None, n=5) -> set:
    w = [x.lower().strip("'.,") for x in _WORD.findall(plain(text, terms))]
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def dangles(text, terms=None) -> str:
    """The word a point stops on that needs something after it ("gets", "under", "the"), at its
    end or before a comma, colon or semicolon inside it; "" when it reads as a whole phrase."""
    toks = _t(plain(text, terms)).split()
    for i, tok in enumerate(toks):
        last = i == len(toks) - 1
        if not last and (i == 0 or not tok.endswith((",", ";", ":"))):
            continue
        w = tok.strip(",;:.!?\"'()\u2018\u2019\u201c\u201d").lower()
        if w in DANGLING:
            return w
    return ""


def _lines_of(text, terms=None) -> list:
    t = _t(plain(text, terms))
    return [x for x in _SENTENCE.split(t) if x.strip()] if t else []


def _live_checks(node, where, terms, level, basic) -> list:
    """The checks for an answer written the live way: its points (`simple`, a list) are the
    script in a few words, each a whole phrase and never a piece cut from it, and the script
    (`detailed`) is said as the person talks, the point first. Neither has to set up a follow-up:
    the page offers the follow-ups as choices, and an answer that ends on a hook to one reads
    like a machine (the maintainer, 2026-11-12)."""
    out = []
    cues = _cues(node)
    d = _t(node.get("detailed"))
    lo, hi = CUES_BASIC if basic else CUES_FOLLOW if level else CUES
    if level and words(node.get("q")) > FOLLOW_Q_WORDS:
        out.append((where, "the follow-up runs to %d words: put it as they would ask it, %d "
                           "words at most" % (words(node.get("q")), FOLLOW_Q_WORDS)))
    if not cues:
        out.append((where, "the points are not written yet: %d to %d short lines, the point "
                           "first" % (lo, hi)))
        return out
    if not lo <= len(cues) <= hi:
        out.append((where, "it has %d point%s: make it %d to %d short lines to glance at"
                    % (len(cues), "" if len(cues) == 1 else "s", lo, hi)))
    for c in cues:
        n = words(c, terms)
        if n > CUE_WORDS:
            out.append((where, "the point \"%s\" runs to %d words: keep each to %d at most, the "
                               "key words only" % (_t(plain(c, terms)), n, CUE_WORDS)))
        if c.rstrip().endswith("."):
            out.append((where, "the point \"%s\" ends with a full stop: it is a line to glance "
                               "at, not a sentence" % _t(plain(c, terms))))
        stop = dangles(c, terms)
        if stop:
            out.append((where, "the point \"%s\" stops on \"%s\": make it a whole phrase, the "
                               "idea in your own words" % (_t(plain(c, terms)), stop)))
    if not d:
        if not basic:
            out.append((where, "the script is not written yet: the answer as you would say it "
                               "aloud, in your own voice"))
        return out
    wd = words(d, terms)
    lo, hi = SCRIPT_WORDS_FOLLOW if level else SCRIPT_WORDS
    if wd < lo or wd > hi:
        out.append((where, "the script is %d words: make it %d to %d, about %s to say"
                    % (wd, lo, hi, "half a minute" if level else "a minute or so")))
    lines = _lines_of(d, terms)
    counts = [len(_WORD.findall(x)) for x in lines]
    if counts and (sum(counts) / float(len(counts)) > SCRIPT_AVERAGE or max(counts) > SIMPLE_WORDS):
        out.append((where, "the script's sentences are too long to say in one breath: keep them "
                           "to about %d words, none over %d" % (SCRIPT_AVERAGE, SIMPLE_WORDS)))
    need = max(1, wd // CONTRACTION_EVERY)
    if len(_CONTRACTION.findall(plain(d, terms))) < need:
        out.append((where, "the script reads as written, not said: use the short forms you say "
                           "(I'd, it's, we didn't), about one every %d words" % CONTRACTION_EVERY))
    low = " " + _t(plain(d, terms)).lower() + " "
    for w in ESSAY:
        if re.search(r"\b%s\b" % re.escape(w), low):
            out.append((where, "\"%s\" is a written word, not a said one: say it the way you "
                               "would out loud" % w))
    q = _t(node.get("q"))
    if lines:
        head = lines[0]
        if len(_WORD.findall(head)) > SCRIPT_FIRST or not (
                (_content(head) & _content(q)) or _numbers(head) or not q):
            out.append((where, "the script does not open on the point: say the answer to \"%s\" "
                               "first, in one short sentence" % (q or "the question")))
    # It ends where the answer ends: never on an offer to say more, and never made to set up
    # the first follow-up, which the page offers as a choice (the maintainer, 2026-11-12).
    if lines and any(f in lines[-1].lower() for f in HOOK_FILLER):
        out.append((where, "the script ends on an offer to say more: end on your answer, and let "
                           "them ask"))
    # The points are the script in a few words: the same numbers, and never four of the
    # script's words in a row; a point may sum it up in words of its own.
    said = " ".join(cues)
    if _numbers(said, terms) != _numbers(d, terms):
        out.append((where, "the points and the script hold different numbers: a point says what "
                           "the script does not, or the script holds a number the points miss"))
    script_runs = _runs(d, terms, CUE_SHARED_RUN)
    for c in cues:
        hit = sorted(_runs(c, terms, CUE_SHARED_RUN) & script_runs)
        if hit:
            out.append((where, "the point \"%s\" copies the script (\"%s\"): say the idea in a "
                               "few words of your own, three in a row from the script at most"
                        % (_t(plain(c, terms)), " ".join(hit[0]))))
    if lines and not _content(cues[0], terms) & _content(lines[0]):
        out.append((where, "the first point is not the point the script opens on: lead with it"))
    return out


def _answer_checks(node, where, terms, need_detail) -> list:
    out = []
    s, d = _t(node.get("simple")), _t(node.get("detailed"))
    if not s:
        out.append((where, "the simple answer is not written yet: write it as you would say "
                           "it, two to four sentences"))
        return out
    n = sentences(s, terms)
    longest = max((len(_WORD.findall(x)) for x in _SENTENCE.split(_t(plain(s, terms))) if x.strip()),
                  default=0)
    if longest > SIMPLE_WORDS:
        out.append((where, "a sentence of the simple answer runs to %d words: say it in shorter "
                           "sentences, %d words at most, each a line to glance at" % (longest, SIMPLE_WORDS)))
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


# The words of the work a prep's questions and answers use that a listener may need explained:
# a prep that uses any of them with no terms at all is not finished (an invented round,
# 2026-11-11: a live coding hour was shown with an empty glossary).
_TECH_WORDS = re.compile(
    r"\b(?:python|sql|pandas|numpy|scikit-learn|sklearn|pyspark|spark|dbt|airflow|snowflake|"
    r"databricks|tableau|power bi|sap|apis?|etl|elt|pipelines?|data warehouse|schemas?|"
    r"quer(?:y|ies)|joins?|window functions?|regressions?|classifi(?:er|ers|cation)|clustering|"
    r"forecast(?:s|ing)?|time series|machine learning|deep learning|neural networks?|"
    r"models?|modell?ing|statistic(?:s|al)?|p-values?|hypothesis tests?|a/b tests?|"
    r"confidence intervals?|algorithms?|complexity|big o|data structures?|hash ?maps?|"
    r"recursion|unit tests?|edge cases?|dataframes?|hackerrank|pair[- ]programming|"
    r"live coding|starter code)\b", re.I)


def technical_words(doc) -> list:
    """The technical words a prep's questions and answers use, first seen first, lower case."""
    texts = [_t(q.get("q")) for q in doc.get("questions") or []]
    texts += [_t(t) for w, t, _d, _q in spoken(doc) if not w.startswith("your question")]
    seen = []
    for t in texts:
        for m in _TECH_WORDS.finditer(t):
            w = m.group(0).lower()
            if w not in seen:
                seen.append(w)
    return seen


# What the first words of a part that works a problem are for, said with what to write there.
_SAY_FIRST = {
    "technical": (" (how you open a problem: say it back in your own words, say what you will "
                  "check first in any starter code and data, and that you will think aloud as "
                  "you go)"),
    "probes": (" (the trade-offs you chose on purpose, and what you would change with more time "
               "or more data)"),
}


def intro_question(doc, part):
    """The opening part's "Tell me about yourself" (or "Walk me through your background"), the
    question its answer is the opening of, or None: a part that is no opening, or holds no such
    question, opens on its own lines to say first."""
    if (part or {}).get("kind") != "opening":
        return None
    return next((q for q in (doc or {}).get("questions") or []
                 if q.get("part") == part.get("id") and kind_of(q.get("q")) == "opening"), None)


def _tree_checks(q, where) -> list:
    """A question written the live way has two or three follow-ups, then up to three under
    each, then up to two, and at least one line of them three deep, so whatever they ask next
    has its answer ready."""
    out = []
    lo, hi = FOLLOW_N
    own = [f for f in q.get("follow") or [] if isinstance(f, dict)]
    if not lo <= len(own) <= hi:
        out.append((where, "it has %d follow-up%s: give it %d or %d, the likeliest first"
                    % (len(own), "" if len(own) == 1 else "s", lo, hi)))
    deepest = 0
    for f, depth, here in _nodes(q, where=where):
        deepest = max(deepest, depth)
        n = len([x for x in f.get("follow") or [] if isinstance(x, dict)])
        most = FOLLOW_MAX.get(depth + 1, 0)
        if depth < MAX_DEPTH and n > most:
            out.append((here, "it has %d follow-ups: keep it to %d" % (n, most)))
    if own and deepest < MAX_DEPTH:
        out.append((where, "no line of its follow-ups goes %d deep: take the likeliest one "
                           "further, a question and its answer at each step" % MAX_DEPTH))
    return out


def _coding_checks(p) -> list:
    """What a coding part holds, when it is written: the steps to take, what to say when
    stuck, the cases to name, a few lines of code and what each means, what you'd do next."""
    out = []
    title = "\"%s\"" % p.get("title")
    if not any(k in p for k in CODING):
        return out
    for key in CODING:
        if key in p and not isinstance(p[key], list):
            out.append((title, "its %s is one value: write it as a list" % key))
    if out:
        return out

    def count(key, rng, what):
        n = len(p.get(key) or [])
        if not rng[0] <= n <= rng[1]:
            out.append((title, "it has %d %s: write %d to %d" % (n, what, rng[0], rng[1])))
    count("steps", STEPS, "steps to take")
    count("stuck", STUCK, "lines for when you are stuck")
    count("edges", EDGES, "cases to name")
    count("code", CODE_ROWS, "lines of handy code")
    count("more", MORE, "things you'd do with more time")
    for i, st in enumerate(p.get("steps") or []):
        st = st if isinstance(st, dict) else {}
        if not _t(st.get("t")) or len(_WORD.findall(_t(st.get("t")))) > 6:
            out.append((title, "step %d needs a name of six words at most" % (i + 1)))
        if not _t(st.get("say")) or len(_WORD.findall(_t(st.get("say")))) > 20:
            out.append((title, "step %d needs what to say as you do it, twenty words at most"
                        % (i + 1)))
    first = p.get("steps") or []
    if first and isinstance(first[0], dict) and not re.search(
            r"\bback\b|\bdata\b|\bcheck\b|\bconfirm\b|\bask\b", _t(first[0].get("say")), re.I):
        out.append((title, "the first step is saying the task back and asking about the data"))
    for x in p.get("edges") or []:
        if not isinstance(x, str) or len(_WORD.findall(_t(x))) > 8:
            out.append((title, "a case to name runs long: eight words at most, from this task's "
                               "own data"))
    for i, c in enumerate(p.get("code") or []):
        c = c if isinstance(c, dict) else {}
        if not c.get("c") or "\n" in str(c["c"]) or len(str(c["c"])) > 80:
            out.append((title, "code line %d should be one line of 80 characters at most" % (i + 1)))
        if not _t(c.get("means")) or len(_WORD.findall(_t(c.get("means")))) > 12:
            out.append((title, "code line %d needs what it means in twelve plain words at most"
                        % (i + 1)))
    for x in p.get("more") or []:
        if not _t(x).startswith("With more time I'd"):
            out.append((title, "what you'd do next starts \"With more time I'd\""))
    return out


_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9&/]+\b")


def _matches(terms) -> list:
    """Every phrase that opens a term, lower case: its match phrases, its name and its key."""
    out = []
    for k, v in terms.items():
        for ph in list(v.get("match") or []) + [v.get("name"), k]:
            if isinstance(ph, str) and _t(ph):
                out.append(_t(ph).lower())
    return out


def _covered(word, text, terms, phrases) -> bool:
    low = word.lower()
    if any(low == ph or re.search(r"\b%s" % re.escape(low), ph) for ph in phrases):
        return True
    for m in _TERM.finditer(str(text or "")):
        label = _t(m.group(2) or (terms.get(m.group(1)) or {}).get("name") or m.group(1)).lower()
        if low in label:
            return True
    return False


def uncovered(doc, ctx=None) -> list:
    """[(where, word)] for each word a person outside the field may not know, said in a live
    prep written the live way and explained by none of its terms: an acronym, a word of the
    employer's own, or one on JARGON."""
    terms = doc.get("terms") or {}
    phrases = _matches(terms)
    try:
        theirs = [_t((v or {}).get("name")) for v in employer_terms(ctx).values()] if ctx else []
    except (KeyError, OSError, person.NoProfile):
        theirs = []
    words_ = [w for w in list(JARGON) + theirs if w]
    out, seen = [], set()
    for where, text, _d, _q in spoken(doc):
        if where.startswith("your question"):
            continue
        t = plain(text, terms)
        found = [m.group(0) for m in _ACRONYM.finditer(t) if m.group(0) not in PLAIN_CAPS]
        low = t.lower()
        for w in words_:
            if re.search(r"(?<![a-z])%s(?:s|es|ed|ing)?(?![a-z])" % re.escape(w.lower()), low):
                found.append(w)
        for w in found:
            if w.lower() in seen or _covered(w, text, terms, phrases):
                continue
            seen.add(w.lower())
            out.append((where, w))
    return out


def _term_live_checks(doc) -> list:
    """Each term of a prep written the live way: plain words short, an everyday likeness of
    its own, and neither leaning on another term or a set of capitals."""
    out = []
    terms = doc.get("terms") or {}
    for k, v in terms.items():
        name = _t(v.get("name")) or k
        where = "the term \"%s\"" % name
        pl, like = _t(v.get("plain")), _t(v.get("like"))
        if pl and len(_WORD.findall(pl)) > TERM_PLAIN_WORDS:
            out.append((where, "say what it means in %d words at most" % TERM_PLAIN_WORDS))
        if not like:
            out.append((where, "add what it is like, an everyday likeness anyone would know"))
        elif len(_WORD.findall(like)) > TERM_LIKE_WORDS:
            out.append((where, "keep what it is like to %d words" % TERM_LIKE_WORDS))
        elif _runs(like) & _runs(pl):
            out.append((where, "what it is like repeats what it means: give a likeness of its own"))
        others = [ph for kk, vv in terms.items() if kk != k for ph in _matches({kk: vv})]
        for text in (pl, like):
            low = " " + text.lower() + " "
            hit = next((ph for ph in others if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(ph), low)), None)
            caps = [m.group(0) for m in _ACRONYM.finditer(text) if m.group(0) not in PLAIN_CAPS]
            if hit or caps:
                out.append((where, "explain it without another hard word (\"%s\"): it has to make "
                                   "sense on its own" % (hit or caps[0])))
                break
    return out


def live_way(doc) -> bool:
    """Is any answer in this prep written the live way (points as a list)?"""
    for q in doc.get("questions") or []:
        if _live_way(q) or any(_live_way(f) for f, _d, _w in _nodes(q)):
            return True
    return any(_live_way(f) for p in doc.get("parts") or [] for f, _d, _w in _nodes(p))


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
                                                                    "technical", "like")), False, "")
            for k, v in terms.items()]:
        for m in _TERM.finditer(str(text or "")):
            if m.group(1) not in terms:
                out.append((where, "it explains \"%s\", and there is no such term: add it to the "
                                   "terms, or take the brackets off" % (m.group(2) or m.group(1))))
    new_way = live_way(doc)
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
        if not _t(v.get("example")) and not new_way:
            out.append(("the term \"%s\"" % name, "it needs a small worked example"))
        if not _t(v.get("plain")):
            out.append(("the term \"%s\"" % name, "say what it means in plain words too"))
    # One word for one thing: a phrase a term goes by opens that term and no other, so the
    # same words never explain two things (SPEC section 2, rule 12).
    owner = {}
    for k, v in terms.items():
        for ph in v.get("match") or []:
            if not isinstance(ph, str) or not _t(ph):
                out.append(("the term \"%s\"" % (_t(v.get("name")) or k),
                            "a phrase it goes by is empty: take it out"))
                continue
            low = _t(ph).lower()
            if low in owner and owner[low] != k:
                out.append(("the term \"%s\"" % (_t(v.get("name")) or k),
                            "\"%s\" already opens \"%s\": one phrase for one term"
                            % (_t(ph), _t(terms[owner[low]].get("name")) or owner[low])))
            owner.setdefault(low, k)
    # Words of the work used and none explained: the glossary is still to write, and a prep
    # with an empty one is never shown as finished.
    if not terms:
        used = technical_words(doc)
        if used:
            out.append(("the terms", "none are explained yet, and the questions and answers use "
                        "%s: add each word a listener may not know to the terms, with what it "
                        "means at %s, a small worked example and plain words"
                        % (", ".join("\"%s\"" % w for w in used[:4]), company or "the employer")))
    # No dashes of the kind the app never writes, anywhere.
    for s in _all_strings(doc):
        if _DASH.search(s):
            out.append(("\"%s\"" % (_t(s)[:60]), "it has a long dash: use a comma, a colon or "
                                                 "a full stop"))
    # The parts: something to say first, a few beats, never numbered, in the time it has.
    timing = (doc.get("timing") or {}).get("parts") or {}
    for p in doc.get("parts") or []:
        say = p.get("say") or []
        intro = intro_question(doc, p)
        if intro is not None:
            # The answer to "Tell me about yourself" is how the opening is said: one script, never
            # also as lines to say first (the maintainer, 2026-11-12: the same intro stood as the
            # part's lines, as that answer, and again at a glance). A line answering a question
            # they are known to ask is still said first.
            if [b for b in say if not b.get("known")]:
                out.append(("\"%s\"" % p.get("title"), "the answer to \"%s\" is how you open: "
                            "write the opening once, as that answer, and leave this part's lines "
                            "to say first empty" % _t(intro.get("q"))))
        elif not say:
            out.append(("\"%s\"" % p.get("title"), "nothing to say first yet: write two or three "
                                                   "sentences to say aloud as it starts"
                        + _SAY_FIRST.get(p.get("kind"), "")))
        if p.get("kind") == "technical" and not any(_TASK.search(_t(q.get("q"))) for q in
                                                       doc.get("questions") or [] if q.get("part") == p.get("id")):
            out.append(("\"%s\"" % p.get("title"), "add the problem they are likely to set, as they "
                        "would set it (\"Given ..., write a function that ...\"), with how you would "
                        "say it back, structure it, test it and talk it through"))
        if p.get("kind") == "practice" and not p.get("questions"):
            out.append(("\"%s\"" % p.get("title"), "no items to practise yet: add three to five of "
                        "the kind the test sets, each with how to take it (simple) and the worked "
                        "answer (detailed)"))
        out += _coding_checks(p)
        if p.get("steps"):
            for q in doc.get("questions") or []:
                if q.get("part") == p.get("id") and kind_of(_t(q.get("q"))) in (
                        "behaviour", "personal", "motivation"):
                    out.append(("\"%s\"" % _t(q.get("q")), "a question about your past or your "
                                "reasons belongs in the part where you tell your story, not "
                                "while you code"))
        if len(say) > MAX_BEATS:
            out.append(("\"%s\"" % p.get("title"), "%d things to say first: keep it to %d"
                        % (len(say), MAX_BEATS)))
        for i, b in enumerate(say):
            if not _t(b.get("t")):
                out.append(("\"%s\", what to say first (%d)" % (p.get("title"), i + 1),
                            "it has no words: write them, or take the line out"))
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
        if _live_way(q):
            out += _live_checks(q, where, terms, 0, kind in _NO_DETAIL)
            if kind not in _NO_DETAIL:
                out += _tree_checks(q, where)
        else:
            out += _answer_checks(q, where, terms, kind not in _NO_DETAIL)
        if q.get("story") and not any(s["id"] == q["story"] for s in doc.get("stories") or []):
            out.append((where, "it is answered with a story that is not among yours"))
        for f, depth, here in _nodes(q, where=where):
            if depth > MAX_DEPTH:
                out.append((here, "follow-ups go three deep at most: fold this one into the one "
                                  "above"))
            if f.get("who") not in PERSONAS:
                out.append((here, "say who is likely to ask it"))
            out += (_live_checks(f, here, terms, depth, False) if _live_way(f)
                    else _answer_checks(f, here, terms, False))
    # The follow-ups said once in a part, after any story told there: written as any other.
    for p in doc.get("parts") or []:
        for f, depth, here in _nodes(p, where="\"%s\", after any story" % p.get("title")):
            if depth > MAX_DEPTH:
                out.append((here, "follow-ups go three deep at most: fold this one into the one "
                                  "above"))
            if f.get("who") not in PERSONAS:
                out.append((here, "say who is likely to ask it"))
            out += (_live_checks(f, here, terms, depth, False) if _live_way(f)
                    else _answer_checks(f, here, terms, False))
            if f.get("story") and not any(s["id"] == f["story"] for s in doc.get("stories") or []):
                out.append((here, "it is answered with a story that is not among yours"))
    # The questions to ask: each with what to say back to their likely answer.
    for a in doc.get("ask") or []:
        if not a.get("follow"):
            out.append(("your question \"%s\"" % _t(a.get("q")),
                        "add what you would ask next to their likely answer"))
        for f in a.get("follow") or []:
            if not _t(f.get("if")) or not _t(f.get("then")):
                out.append(("your question \"%s\"" % _t(a.get("q")),
                            "a follow-up needs their likely answer and what you say next"))
    # Every known question: on a question, and answered before they ask it, in an opening. One
    # asked as "Tell me about yourself" is answered by the opening itself, which is its answer.
    said_known = {b.get("known") for p in doc.get("parts") or [] for b in p.get("say") or []}
    said_known |= {q.get("known") for p in doc.get("parts") or []
                   for q in [intro_question(doc, p)] if q is not None and _said(q)}
    for k in doc.get("known") or []:
        if not k.get("question") or k["question"] not in qids:
            out.append(("\"%s\"" % k.get("text"), "a question they are known to ask is not "
                                                  "placed on any part"))
        if k.get("id") not in said_known:
            out.append(("\"%s\"" % k.get("text"), "a question they are known to ask: answer it "
                                                  "in what you say first in its part, and mark it"))
    # Words that assume a history nobody can check, and phrases the person never wants.
    import learned
    # The basics are said short on purpose ("One month."), and a question to ask is a question.
    short_ok = {q["q"] for q in doc.get("questions") or []
                if (parts.get(q.get("part")) or {}).get("kind") in _NO_DETAIL}
    for where, text, _d, _q in spoken(doc):
        t = plain(text, terms)
        if not where.startswith("your question") and _q not in short_ok and \
                not where.endswith((POINTS, CODING_LINE)) and choppy(text, terms):
            out.append((where, CHOPPY))
        m = _SHARED.search(t) or (_SHARED_OPENING.search(t) if "what to say first" in where else None)
        if m:
            out.append((where, "\"%s\" assumes you have spoken before: say it fresh" % m.group(0)))
        for hit in learned.dislikes(t):
            out.append((where, "\"%s\" is a phrase you asked never to use" % hit))
    if new_way:
        out += _term_live_checks(doc)
        for where, w in uncovered(doc, ctx):
            out.append((where, "\"%s\" is not explained: add it to the terms with plain, here "
                               "and like" % w))
    out += grounding(doc, ctx)
    return out


_NEGATED = re.compile(r"\b(?:not|never|no|without|neither|nor)\b|n['\u2019]t\b", re.I)


def _asked_of_them(value, text) -> bool:
    """Is a figure said only inside a question for them (a sentence ending "?")?"""
    sents = [x for x in _SENTENCE.split(_t(text)) if value and value.lower() in x.lower()]
    return bool(sents) and all(x.rstrip().endswith("?") for x in sents)


def _negated(snippet, text) -> bool:
    """Is every place `snippet` is said in `text` governed by a negation a few words before it
    ("I'm not a member of CIPS", "I don't hold CIPS membership")? A "no" anywhere else in the
    sentence ("I hold CIPS membership, and I have no doubt...") is not one (the review of the
    fixes, 2026-11-10)."""
    low, s = _t(text).lower(), snippet.lower()
    at = [m.start() for m in re.finditer(re.escape(s), low)]
    if not at:
        return False
    for i in at:
        before = re.split(r"[.!?;,]", low[:i])[-1]
        if not _NEGATED.search(" ".join(before.split()[-5:])):
            return False
    return True


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
        # A question to ask them is about their work, never a claim about the person's.
        about_them = where.startswith("your question")
        if not about_them and not re.search(P._PAY_Q + r"|\bnotice\b|\bstart\b", question or "", re.I):
            for f in check_numbers.check(t, allowed=allowed):
                # A time ahead, or a figure inside a question asked of them, is not a claim
                # about the person's work (the night-before run, 2026-11-10).
                ctx_ = f.get("context") or ""
                if P._PLAN.search(ctx_) or _asked_of_them(_t(f.get("value")), t):
                    continue
                out.append((where, "\"%s\" is a number your profile does not hold: say the one "
                                   "it holds, or mark the answer a draft for you to confirm"
                            % f.get("value", "")))
        for sev, name, snippet, why in check_claims.check_text(t):
            if sev != "ERROR":
                continue
            # Saying plainly that you do not hold it is the honest answer, never a claim: "No,
            # I'm not a member of CIPS" was refused as naming a skill not held.
            if name == "unheld-skill" and _negated(snippet, t):
                continue
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
    for p in doc.get("parts") or []:
        for f, _d, here in _nodes(p, where="\"%s\", after any story" % p.get("title")):
            if f.get("draft"):
                out.append(here)
    return out


# ---------------------------------------------------------------- on disk

def kind_changed(folder, stage="") -> str:
    """The kind of round the record now says, where the live prep saved for that round was made
    for another ("" when it was not, or nothing is saved): `book --format` changed what the
    round is and the saved prep gave no sign of it (the night-before run, 2026-11-10)."""
    import interview_pack as P
    doc = load(folder)
    if not doc:
        return ""
    label = _t(stage) or _t(doc.get("stage"))
    if _t(doc.get("stage")) and label and not P._same_round(doc["stage"], label):
        return ""
    try:
        with open(os.path.join(folder, "outcome.md"), encoding="utf-8") as fh:
            now = P.stage_format(fh.read(), label)
    except OSError:
        return ""
    return now if now and _norm(now) != _norm(doc.get("format")) else ""


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
    # A prep saved before the follow-ups after any story were the part's says them once too,
    # as it is read: nothing needs making again (the screen review, 2026-11-11).
    for p in out.get("parts") or []:
        # A line to say first with no words, as a prep saved before 2026-11-11 can hold, is
        # left out rather than drawn as an empty bullet.
        p["say"] = [b for b in p.get("say") or [] if isinstance(b, dict) and _t(b.get("t"))]
        _follow_once(p, [q for qid in p.get("questions") or [] for q in out["questions"] if q["id"] == qid])
    for q in out["questions"]:
        q.pop("from", None)
    out["drafts"] = (out.pop("checked", None) or {}).get("drafts", 0)
    out["personas"] = dict(PERSONAS)
    # The person's own setting as it is now, so a change reaches the page without making the
    # prep again; with none, the points lead, as the page leads with them.
    out["lead"] = lead()
    # What the Brief's "Likely to come up" draws, in the engine's one order.
    out["likely"] = [q["id"] for q in _likely_order(out)]
    return out


def likely(doc, n=5) -> list:
    """The questions most likely to come up, in the order the interview runs: the known ones
    first in each part, then the rest. What the Brief's "Likely to come up" reads."""
    return [{"question": q["q"], "answer": _t(plain(_said(q), doc.get("terms"))),
             "draft": bool(q.get("draft"))} for q in _likely_order(doc)[:n]]


def _likely_order(doc) -> list:
    order = {p["id"]: i for i, p in enumerate(doc.get("parts") or [])}
    return sorted(doc.get("questions") or [], key=lambda q: (order.get(q["part"], 99),
                                                             not q.get("known")))
