#!/usr/bin/env python3
"""What a draft is warned about before it is shown, each with what to write instead.

`compose.validate()` refuses what must never go: a note over the platform's limit, a job
ask to a stranger, a status the profile does not hold. This is the other half, from one
long session's corrections (2026-10-19 and 20): what reads as generated ("reads like
someone who just learned English as a second language"), a close that invites no reply
("that's almost inviting him not to respond"), a claim about the reader written as fact,
or hedged three times over, and a credential with no reason to be there ("it just sounds
like you randomly mentioned it, is there a point?"). Each is a warning with its fix: the
chat rewrites before showing anything, and the person decides.

The person's own words are never warned about: a sentence that is their own setting in
profile/networking.py, or a check one of their rules outranks (`learned.py record
--overrides <rule>`).

    import advice
    for a in advice.check(note, "connection", reader="peer", reading=r):
        print(a.rule, a.text, a.fix)
"""
from __future__ import annotations

import os
import re
import sys
from collections import namedtuple

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402
import tone  # noqa: E402

Advice = namedtuple("Advice", "rule text fix")

_NET = person.module("networking") if person.exists("networking.py") else None
_SKILLS = person.module("skills") if person.exists("skills.py") else None
_ROLES = person.module("roles") if person.exists("roles.py") else None

# The message kinds that reach someone for the first time. A soft exit is allowed in a
# follow-up, never here.
FIRST_CONTACT = frozenset({"connection", "inmail", "email"})

# ------------------------------------------------------------------ what reads as generated

# (name, pattern, what to write instead). Each was in a draft the person rejected.
AI_TELLS = (
    ("sits close to", re.compile(r"\bsits? (?:close|near|right next) to\b", re.I),
     "say the link plainly, or cut it"),
    ("is the kind of path", re.compile(
        r"\b(?:is|was) (?:exactly |just )?the (?:kind|sort) of (?:path|route|move|career)\b", re.I),
     "say it directly: \"your move from <X> into <Y> is the one I'm hoping to make\""),
    ("I would value", re.compile(r"\bI(?:'d| would) (?:really |truly )?value\b", re.I),
     "\"I'd really appreciate\", or just ask"),
    ("praise of the company", re.compile(
        r"\b(?:high|top|first) on my (?:list|shortlist)\b|\bdream (?:company|employer|job|team)\b"
        r"|\bI(?:'ve| have) (?:long |always )?admired\b|\bbig fan of\b", re.I),
     "praise fits any company: give the reason that is about this person or their team"),
    ("the route I would most like", re.compile(
        r"\b(?:route|path|direction|move) I(?:'d| would) (?:most )?(?:like|love) to (?:follow|take|make)\b"
        r"|\bwhere I(?:'d| would) most like to (?:work|be|end up)\b", re.I),
     "say it plainly: \"I'm hoping to move into <the work>\""),
    ("which teams to look at", re.compile(
        r"\bwhich teams? to (?:look at|target|approach)\b|\bhow to approach (?:them|the team|teams)\b",
        re.I),
     "ask one thing: \"would you know the right person to speak to?\""),
    ("a title as an opener", re.compile(
        r"(?:^|[,.!?]\s+)(?:[A-Za-z-]+\s){0,3}(?:scientist|analyst|engineer|consultant|developer|"
        r"designer|manager|researcher|marketer|recruiter|student|graduate)\s+here\b", re.I),
     "say who you are as a sentence: \"I'm a <title> in <city>\""),
    ("asks how to get hired", re.compile(
        r"\bhow (?:would|should|could|do|did|can) (?:I|someone|one|a candidate|people|you)\b"
        r"[^?.!]{0,50}\b(?:get (?:hired|in(?:to)?|a foot in)|break in(?:to)?|land (?:a|the) role|"
        r"join (?:your|the) team|stand out)\b|\bwhat (?:would|does) it take to (?:join|get (?:in|hired))\b"
        r"|\bwhat do you look for (?:in (?:a )?candidates?|when (?:you )?hir\w*)\b", re.I),
     "a stranger is not a career adviser: ask openly, \"would love to hear if you have anything "
     "coming up, or know the right person to speak to\""),
    ("a test question", re.compile(
        r"\bhow do you (?:decide|know|judge|tell)\b[^?]{0,90}\b(?:good enough|ready|worth (?:it|"
        r"shipping)|right)\b", re.I),
     "an honest ask beats a test of them: a short call, or a pointer to the right person"),
    ("the old default ask", re.compile(
        r"\bI(?:'d| would) love to hear (?:more )?(?:about )?how (?:your|the) team works\b", re.I),
     "ask what you would really ask them, or for a short call, in your own words"),
)

# A list of three credentials in a row ("Oakmere Foods, Saltmarsh Analytics and Brindle &
# Hart"): the shape a
# generated note takes. Name the one that matters to this reader.
_ITEM = r"(?:ex-)?[A-Z][\w&.'-]*(?:\s(?:of\s|and\s)?[A-Z][\w&.'-]*){0,3}"
_LIST3 = re.compile(rf"\b({_ITEM}),\s+({_ITEM}),?\s+and\s+({_ITEM})\b")

# A close that hands them a reason not to reply. Allowed in a follow-up, never a first
# message: the close that drew a reply was an open ask.
EXITS = re.compile(
    r"\bif not,? no (?:worries|problem|pressure|stress)\b"
    r"|\bno (?:worries|problem|pressure)(?: at all)?,? (?:if not|if you(?:'re| are) (?:busy|not able)|"
    r"if you can'?t|either way)\b"
    r"|\bno pressure\b|\btotally (?:understand|get it) if\b|\bcompletely understand if\b"
    r"|\bfeel free to ignore\b|\bno need to (?:reply|respond)\b|\bif you(?:'re| are) too busy\b"
    r"|\bno (?:obligation|expectation)s?\b", re.I)
OPEN_ASK = ("Would love to hear if you have anything coming up, or know the right person to "
            "speak to.")
EXIT_FIX = (f"an exit invites them not to reply: end on the open ask (\"{OPEN_ASK}\"); a soft "
            "exit belongs in a follow-up, never a first message")

# ------------------------------------------------------------------ hedges

# One light hedge per inference, from these; never two in a sentence, never a disclaimer.
HEDGES = ("I imagine", "I can imagine", "I'm guessing", "probably", "it seems like",
          "it looks like")
_HEDGE = re.compile(
    r"\b(?:I (?:can )?imagine|I'?m guessing|guess|guessing|probably|presumably|seems?|"
    r"looks? like|I think|think|thought|maybe|perhaps|possibly|might|could|not sure|suppose)\b",
    re.I)
# "could you", "might I ask" ask; they do not hedge.
_ASKING = re.compile(r"\b(?:could|would|can|might) (?:you|we|I ask)\b", re.I)
DISCLAIMERS = re.compile(
    r"\bI can(?:'t|not) (?:really )?know\b|\bfrom the outside\b"
    r"|\bI (?:could|may|might) (?:well )?be wrong\b|\bcorrect me if I(?:'m| am) wrong\b"
    r"|\bfor what it'?s worth\b|\bI(?:'m| am) (?:only|just) guessing\b"
    r"|\bI don'?t (?:really )?know (?:if|whether|much|enough)\b|\bthis (?:may|might) be (?:way )?off\b",
    re.I)


def hedges(sentence: str) -> list[str]:
    """The hedges in one sentence, asking modals left out."""
    s = _ASKING.sub(" ", str(sentence or ""))
    return [m.group(0) for m in _HEDGE.finditer(s)]


# ------------------------------------------------------------------ where a claim comes from

STATED, INFERRED, GUESS = "STATED", "INFERRED", "GUESS"
_ABOUT_THEM = re.compile(r"\b(?:you|your|you've|you're|yours)\b", re.I)
_NOT_A_CLAIM = re.compile(
    r"^(?:hi|hey|hello|dear|hope|would|could|can|do|did|are|is|if|thanks|thank|happy|let me)\b",
    re.I)
# The sender's own act, with them as its object: how they were found, or what both share.
# Not a claim about them.
_SENDER_ACT = re.compile(
    r"^(?:I(?:'ve| have)? (?:came across|come across|found|met|was (?:looking|reading)|"
    r"saw your name|noticed (?:that )?we)|We(?:'re| are) both|We both|(?:\w+ )?suggested I)\b",
    re.I)
_GUESS = re.compile(
    r"\b(?:useful|valuable|helpful|a (?:good |great |strong |natural )?fit|of use|add value|"
    r"could help|would help|bring)\b[^.!?]{0,40}\b(?:you|your team|a team like yours|yours)\b"
    r"|\ba team like yours\b|\byour team (?:needs|is probably|must|would)\b", re.I)


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]{4,}", tone._plain(str(text or "")).lower())
            if w not in tone.STOPWORDS}


def _read_text(reading: dict | None) -> str:
    r = reading or {}
    parts = [r.get("headline", ""), r.get("about", ""), r.get("current", "")]
    parts += [i.get("text", "") for i in r.get("items") or []]
    parts += [" ".join(str(e.get(k) or "") for k in ("employer", "title", "place"))
              for e in r.get("experience") or []]
    return " ".join(parts)


def provenance(sentence: str, reading: dict | None = None) -> str:
    """Where a claim about the reader comes from: STATED (they wrote it: their page says
    it), INFERRED (from a title, an employer or a career path), GUESS (about their current
    team, or what would be useful to them), or "" when the sentence claims nothing about
    them. STATED is said plainly, INFERRED hedged once, GUESS lightly or not at all."""
    s = " ".join(str(sentence or "").split())
    if not s or s.endswith("?") or not _ABOUT_THEM.search(s) or _NOT_A_CLAIM.match(s) \
            or _SENDER_ACT.match(s):
        return ""
    if _GUESS.search(s):
        return GUESS
    if reading and len(_words(s) & _words(_read_text(reading))) >= 2:
        return STATED
    return INFERRED


def claims(text: str, reading: dict | None = None) -> list[tuple[str, str, bool]]:
    """[(sentence, provenance, hedged)] for each sentence that claims something about them."""
    out = []
    for s in tone.sentences(text):
        p = provenance(s, reading)
        if p:
            out.append((s, p, bool(hedges(s))))
    return out


# ------------------------------------------------------------------ a reason for each credential

# A clause that ties what the sender holds to the reader: why it matters to them.
_LINKS = re.compile(
    r"\b(?:which is why|that'?s why|is why|so|because|since|why|like you|like yours|same as|"
    r"similar to|relevant|for your|on your|to your|interest(?:s|ed)? me|drew me|draws me|"
    r"got me|led me|made me|which is what|the same)\b|\byou(?:r|'re|'ve)?\b", re.I)


# The skills categories that are tools (profile/skills.py ITEMS): a tool named in a note
# needs its reason. A domain ("demand forecasting") is the work itself.
TOOL_CATEGORIES = ("lang", "eng", "bi")


def credentials() -> list[tuple[str, re.Pattern]]:
    """(name, pattern) for what the sender holds that a note might mention as a credential:
    the profile's tools (TOOL_CATEGORIES), the ones it pins, and their certifications."""
    out = []
    for name in getattr(_SKILLS, "PINNED", None) or ():
        out.append((str(name), re.compile(r"\b" + re.escape(str(name)) + r"\b", re.I)))
    for item in getattr(_SKILLS, "ITEMS", ()) or ():
        if len(item) > 2 and item[1] and item[0] in TOOL_CATEGORIES:
            try:
                out.append((str(item[1]), re.compile(item[2], re.I)))
            except (re.error, TypeError):
                continue
    certs = str(getattr(_ROLES, "CERTIFICATIONS", "") or "")
    for name in re.split(r"\\\\|;|\n", re.sub(r"\\textbf\{([^}]*)\}", r"\1", certs)):
        name = re.sub(r"\(\d{4}\)|\\[a-z]+", "", name).strip(" .,")
        if len(name) > 6:
            out.append((name, re.compile(re.escape(name), re.I)))
    return out


def without_purpose(text: str, creds=None) -> list[Advice]:
    """Each credential named in a sentence that never says why it matters to this reader."""
    creds = credentials() if creds is None else creds
    out = []
    for s in tone.sentences(text):
        # A sentence with a number in it is evidence (a piece of work and its outcome),
        # which carries its own point.
        if _LINKS.search(s) or re.search(r"\d", s):
            continue
        for _name, rx in creds:
            m = rx.search(s)
            if m:
                out.append(Advice(
                    "credential_without_purpose", m.group(0),
                    f"say in the same sentence why {m.group(0)} matters to them (\"which is "
                    "why <their work> interests me\"), or cut it"))
                break
    return out


# ------------------------------------------------------------------ the person's own words

def _own() -> set:
    """The sentences the person set as their own (OPENER, ABOUT_ME, ASK, TEMPLATES)."""
    found = []
    for name in ("OPENER", "ABOUT_ME", "ASK", "WHO_LINE"):
        found.append(str(getattr(_NET, name, "") or ""))
    for intents in (getattr(_NET, "TEMPLATES", None) or {}).values():
        for variants in (intents or {}).values():
            found += [str(v) for v in (variants if isinstance(variants, (list, tuple))
                                       else [variants])]
    return {_norm(s) for s in found if s.strip()}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", tone._plain(str(s or "")).lower()).strip()


def _theirs(sentence: str, own: set) -> bool:
    n = _norm(sentence)
    return bool(n) and any(o and (o in n) for o in own if len(o) > 12)


# ------------------------------------------------------------------ the whole check

def check(text: str, kind: str = "connection", reader: str = "peer", first_contact=None,
          reading: dict | None = None, creds=None) -> list[Advice]:
    """Every warning for this draft, each with its fix. `first_contact` defaults to the
    kind (a note, an InMail, an email); an exit is only warned about there."""
    text = str(text or "")
    first_contact = (kind in FIRST_CONTACT) if first_contact is None else first_contact
    own = _own()
    out = []
    for s in tone.sentences(text):
        if _theirs(s, own):
            continue
        for name, rx, fix in AI_TELLS:
            m = rx.search(s)
            if m:
                out.append(Advice("ai_tell", f"{name}: {m.group(0)}", fix))
        m = _LIST3.search(s)
        if m:
            out.append(Advice("three_credentials", m.group(0),
                              "a list of three reads as generated: name the one that matters "
                              "to this reader"))
        found = hedges(s)
        if len(found) >= 2:
            out.append(Advice("stacked_hedge", f"{', '.join(found)} in: {s[:80]}",
                              "hedge an inference once and lightly (\"I imagine\", \"I'm "
                              "guessing\", \"probably\", \"it seems like\"), never twice"))
        m = DISCLAIMERS.search(s)
        if m:
            out.append(Advice("disclaimer", m.group(0),
                              "cut it: one light hedge on the claim says enough"))
        if first_contact:
            m = EXITS.search(s)
            if m:
                out.append(Advice("soft_exit", m.group(0), EXIT_FIX))
        p = provenance(s, reading)
        if p == GUESS and re.search(r"\ba team like yours\b|\buseful\b", s, re.I):
            out.append(Advice("generic_fit", s[:100],
                              "a fit claimed for any team is presumptuous: give a parallel in "
                              "their own path instead (reading.py show lists them)"))
        elif p in (INFERRED, GUESS) and not found:
            out.append(Advice("unhedged_inference", s[:100],
                              "an inference written as fact: hedge it once (\"I imagine\", "
                              "\"I'm guessing\", \"it looks like\"), or say what they wrote"))
    out += [a for a in without_purpose(text, creds)
            if not any(_theirs(s, own) and a.text in s for s in tone.sentences(text))]
    try:
        import learned
        over = learned.overrides()
    except (ImportError, SystemExit):
        over = set()
    return [a for a in out if a.rule not in over]


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Warnings for a draft, each with its fix.")
    ap.add_argument("file", help="the draft, or - for stdin")
    ap.add_argument("--kind", default="connection")
    ap.add_argument("--reader", default="peer", choices=("peer", "decision_maker", "recruiter"))
    a = ap.parse_args(argv)
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    found = check(text, a.kind, a.reader)
    for x in found:
        print(f"warn: {x.rule}: {x.text} -> {x.fix}")
    print(f"{len(found)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
