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

# The message kinds that reach someone for the first time. An easy no is allowed in a later
# message that asks a favour, never here. An email is not one: it goes to someone who asked
# for it (compose.email), and an email after a call was warned for its exit (2026-10-20).
FIRST_CONTACT = frozenset({"connection", "inmail"})

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
     # {open_ask} is the open ask in words this person's voice check passes (open_ask()):
     # the fix offered must be one the check that follows passes.
     "a stranger is not a career adviser: ask openly, \"{open_ask}\""),
    ("a test question", re.compile(
        r"\bhow do you (?:decide|know|judge|tell)\b[^?]{0,90}\b(?:good enough|ready|worth (?:it|"
        r"shipping)|right)\b", re.I),
     "an honest ask beats a test of them: a short call, or a pointer to the right person"),
    ("the old default ask", re.compile(
        r"\bI(?:'d| would) love to hear (?:more )?(?:about )?how (?:your|the) team works\b", re.I),
     "ask what you would really ask them, or for a short call, in your own words"),
    # Recorded as a reaction in one round (2026-10-20) and never checked: it says nothing
    # about why them, and every sweep opens on it.
    ("came across your profile", re.compile(
        r"\b(?:came|come|coming) across (?:your|his|her|their) (?:profile|page|linkedin)\b", re.I),
     "say how and why: \"I found you while looking at <employer>'s <team> team\", or lead on "
     "what you share"),
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
    r"|\bno (?:obligation|expectation)s?\b"
    # The exit lines a round still sent (2026-10-20): "No worries at all." on its own, "no
    # worries if you're not around", "totally fine if not", "if now isn't a good time".
    r"|^\W*no (?:worries|problem|stress)(?: at all)?\W*$"
    r"|\bno (?:worries|problem)(?: at all)?,? if (?:you|it|now|this)\b"
    r"|\b(?:totally|completely|absolutely|perfectly|entirely) (?:fine|ok(?:ay)?|understandable) "
    r"if (?:not|you)\b"
    r"|\bif (?:now|it|this)(?:'s| is)?(?:n'?t| not) (?:a good|the right) time\b"
    r"|\bif you(?:'re| are)(?:n'?t| not) (?:able|around|free|interested)\b"
    r"|\bif you(?:'d| would) rather not\b|\bno hard feelings\b", re.I)
OPEN_ASK = ("Would love to hear if you have anything coming up, or know the right person to "
            "speak to.")
# The same ask for a person whose own voice check refuses "would love to" (OWN_VOICE): the
# fix offered must be one the check that follows passes.
OPEN_ASK_PLAIN = ("If you have anything coming up, or know the right person to speak to, "
                  "it'd be great to hear.")


def open_ask() -> str:
    """The open ask in words this person's voice check passes."""
    try:
        import voice_check
    except ImportError:                       # pragma: no cover - path issue only
        return OPEN_ASK
    own = getattr(_NET, "OWN_VOICE", None)
    return OPEN_ASK_PLAIN if voice_check.hard(OPEN_ASK, allow=own) else OPEN_ASK


def exit_fix() -> str:
    return (f"an exit invites them not to reply: end on the open ask (\"{open_ask()}\"); an "
            "easy no belongs in a later message that asks a favour, never a first message")


def with_open_ask(fix: str) -> str:
    """A fix text with its {open_ask} filled in by open_ask(), read when it is shown."""
    return fix.replace("{open_ask}", open_ask()) if "{open_ask}" in fix else fix


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
# An offer on their terms, to the comma: "If you think it might help, I can send the
# write-up" hedges no claim, and was warned as two hedges (2026-10-20).
_IF_YOU_THINK = re.compile(r"\bif you (?:think|feel)\b[^,;.!?]*", re.I)
DISCLAIMERS = re.compile(
    r"\bI can(?:'t|not) (?:really )?know\b|\bfrom the outside\b"
    r"|\bI (?:could|may|might) (?:well )?be wrong\b|\bcorrect me if I(?:'m| am) wrong\b"
    r"|\bfor what it'?s worth\b|\bI(?:'m| am) (?:only|just) guessing\b"
    r"|\bI don'?t (?:really )?know (?:if|whether|much|enough)\b|\bthis (?:may|might) be (?:way )?off\b",
    re.I)


def hedges(sentence: str) -> list[str]:
    """The hedges in one sentence, asking modals and an "if you think ..." offer left out."""
    s = _IF_YOU_THINK.sub(" ", _ASKING.sub(" ", str(sentence or "")))
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
# The sender's ask or wish, with them in it: "I'd love to join your team at Larkspur, or
# just hear more" claims nothing about them, and was warned as an inference (2026-10-20).
ASK_SHAPED = re.compile(
    r"^(?:I(?:'d| would) (?:really |also |just |still )?(?:love|like|be (?:glad|happy|keen|"
    r"grateful|interested))|(?:I'?m|I am) (?:keen|hoping|happy|open|always happy)|"
    r"It'?d be (?:great|good|lovely)|(?:Happy|Keen|Glad) to|Let me know|Feel free|Would love)\b",
    re.I)


# A sentence whose subject is the reader: "You moved into pricing from economics", "Your
# team builds the forecasts". Only such a sentence is an inference about them, to hedge
# once. "Your talk on forecasting stuck with me" and "I'm a big fan of your team's work"
# say what the sender felt: both were warned as inferences (2026-10-20), and a hedge in
# front of either garbles it. compose.hedge() reads the same test.
_READER_SUBJECT = re.compile(
    r"^(?:you(?:'ve|'re|'d)?|your (?:team|group|org\w*|company|function|department|unit))\b",
    re.I)


def reader_is_subject(sentence: str) -> bool:
    """Is the reader the subject of this sentence ("You moved ...", "Your team builds ...")?"""
    return bool(_READER_SUBJECT.match(tone._plain(" ".join(str(sentence or "").split()))))


_ASKING_CLOSE = re.compile(
    r"\b(?:I(?:'d| would) (?:really )?(?:love|like)|would love|keen to|happy to|glad to|"
    r"or (?:just )?(?:hear|learn|chat|talk))\b", re.I)


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]{4,}", tone._plain(str(text or "")).lower())
            if w not in tone.STOPWORDS}


# Short names and acronyms ("QMX", "ONS", "Vela"): too short for `_words`, and exactly what
# a career fact names. A fact read off their page names their employers.
_COMMON_CAPS = frozenset("""i i'm i'd i've you your you're you've hi hey hello dear the a an it
it's we our my at in on of and or but so if as by to for from with this that what how why who
when where would could can do did are is was were hope""".split())


def _short_names(text: str) -> set:
    return {t.lower() for t in re.findall(r"(?<![\w'])[A-Z][\w&'-]*", tone._plain(str(text or "")))
            if len(t) < 5 and t.lower() not in _COMMON_CAPS}


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
    them. STATED is said plainly, INFERRED hedged once, GUESS lightly or not at all.

    A "you" or a "your" alone is no claim: INFERRED needs the reader as the sentence's
    subject (reader_is_subject), and GUESS its own words (what would be useful to them)."""
    s = " ".join(str(sentence or "").split())
    if not s or s.endswith("?") or not _ABOUT_THEM.search(s) or _NOT_A_CLAIM.match(s) \
            or _SENDER_ACT.match(s) or ASK_SHAPED.match(tone._plain(s)):
        return ""
    if _GUESS.search(s):
        return GUESS
    if reading:
        read = _read_text(reading)
        # Their employers by a short name or initials count as much as a long word: "you
        # started out as an economist before QMX and KMB" is read off their page.
        if len(_words(s) & _words(read)) + len(_short_names(s) & _short_names(read)) >= 2:
            return STATED
    return INFERRED if reader_is_subject(s) else ""


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
    pinned = getattr(_SKILLS, "PINNED", None)        # (category, item), or None
    if isinstance(pinned, (list, tuple)) and len(pinned) == 2 and str(pinned[1]).strip():
        name = str(pinned[1]).strip()
        out.append((name, re.compile(r"\b" + re.escape(name) + r"\b", re.I)))
    for item in getattr(_SKILLS, "ITEMS", ()) or ():
        if len(item) > 2 and item[1] and item[0] in TOOL_CATEGORIES:
            try:
                out.append((str(item[1]), re.compile(item[2], re.I)))
            except (re.error, TypeError):
                continue
    for name in certification_names():
        # A note names a certificate by its maker and the word, rarely by its full title.
        maker = name.split(" Certified")[0].strip() if " Certified" in name else ""
        rx = (r"\b%s\b[^.!?]{0,60}\bcertif\w*|\bcertif\w*[^.!?]{0,30}\b%s\b"
              % (re.escape(maker), re.escape(maker)) if maker else re.escape(name))
        out.append((name, re.compile(rx, re.I)))
    return out


def certification_names() -> list[str]:
    """The certificates in roles.py CERTIFICATIONS, as plain names: the LaTeX it is written
    in (\\textbullet{} between them, \\kern0pt inside a name, \\textbf) taken out."""
    certs = str(getattr(_ROLES, "CERTIFICATIONS", "") or "")
    certs = re.sub(r"\\textbf\{([^}]*)\}", r"\1", certs)
    out = []
    for name in re.split(r"\\textbullet\{\}|\\\\|;|\n|\u2022", certs):
        # \kern0pt and its dimension go with the space TeX reads as part of it: "A\kern0pt WS"
        # prints as one word.
        name = re.sub(r"\\kern\s*-?[\d.]+\s*(?:pt|em|ex|mu)?\s?", "", name)
        name = re.sub(r"\\[a-zA-Z]+(?:\{\})?|[{}]", "", name)
        name = re.sub(r"\((?:\d{4}|in progress|expected[^)]*)\)", "", name, flags=re.I)
        name = " ".join(name.split()).strip(" .,")
        if len(name) > 6:
            out.append(name)
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
                    f"say in the same sentence why {m.group(0)} matters to them, as a plain "
                    "link (\"the same <work> your team does\", \"like you, I came to it from "
                    "<field>\"), or cut it"))
                break
    return out


# ------------------------------------------------------------------ what a round taught (2026-10-20)

# Praise from a stranger. "Your ads economics work really interested me" and "it's exactly
# the kind of work I'd like to do more of" were both called stupid praise: what replaces it
# is a plain link between their path and the sender's. compose.validate() refuses these.
FLATTERY = re.compile(
    r"\b(?:(?:really|genuinely|truly|so|particularly|especially|very) )?interest(?:ed|s) me\b"
    r"|\b(?:really |so |very )?interesting (?:work|career|path|background|journey|move)\b"
    r"|\bfascinat\w*|\bimpress(?:ive|ed|ively)\b|\binspir(?:ing|ed me|ational)\b"
    r"|\b(?:exactly |just )?the (?:kind|sort|type) of work I(?:'d| would)? (?:like|love|want|"
    r"enjoy|hope) to (?:do|be doing)\b"
    r"|\b(?:amazing|incredible|awesome|brilliant|fantastic|excellent|outstanding|stellar) "
    r"(?:work|career|path|journey|background|team|achievements?|story)\b"
    r"|\bI (?:really )?(?:love|loved) (?:what|how) you\b|\b(?:huge|big) (?:fan|admirer)\b", re.I)
FLATTERY_FIX = ("praise reads as flattery from a stranger: say the plain link between their "
                "path and yours instead (\"you moved from economics into pricing, which is the "
                "move I've been making\")")


# Praise is only to them where the sentence reaches them. "I've been fascinated by markdown
# pricing" and "a meetup talk inspired me to move into pricing" are about the sender, and
# were refused as flattery (2026-10-20). A sentence with no "you" in it still reaches them
# when it points back at something of theirs ("It's exactly the kind of work I'd like to do
# more of", after their work was named) or names a team or employer as its subject
# ("Larkspur's work is impressive").
_GREETED = re.compile(r"^(?:hi|hey|hello|dear)\b[^,\n]{0,40},\s*", re.I)
_POINTS_BACK = re.compile(r"^(?i:it|that|this|these|those)\b"
                          r"|^(?:[A-Z][\w&.-]*\s){0,3}[A-Z][\w&.-]*'s\b")


def _to_them(sentence: str) -> bool:
    s = _GREETED.sub("", tone._plain(str(sentence or "")).strip())
    return bool(_ABOUT_THEM.search(s) or _POINTS_BACK.match(s))


def flattery(text: str) -> list[tuple[str, str]]:
    """[(the praise, its sentence)] in sentences that reach the reader (`_to_them`) and are
    not the person's own settings."""
    own = _own()
    return [(m.group(0), s) for s in tone.sentences(text)
            if _to_them(s) and not _theirs(s, own) for m in FLATTERY.finditer(s)]


# Guessing what someone sees from their level or title: "You've probably seen a fair few of
# the Toronto teams from a Staff role" was "weird and presumptuous". A question about it
# asks; a sentence that assumes it guesses.
_LEVEL = (r"(?:staff|senior|principal|lead|head|director|manager|management|leadership|vp|"
          r"chief|executive|exec|partner|founder)")
_VANTAGE = re.compile(
    r"\b(?:from|in|at|with|given) (?:a|an|your|that|such an?) (?:[\w-]+ ){0,2}" + _LEVEL
    + r"(?: [\w-]+){0,2} (?:role|position|seat|level|title|chair|job)\b"
    r"|\b(?:from|in|at) (?:a|an|your) (?:[\w-]+ )?(?:role|position|seat|level|vantage point) "
    r"(?:like|as senior as) (?:that|yours)\b"
    r"|\bfrom where you (?:sit|stand)\b|\bat your level\b|\bin your (?:position|seat|shoes)\b"
    r"|\bgiven your (?:seniority|level|title|role|position|vantage point)\b"
    r"|\bas (?:a|an) " + _LEVEL + r"\b[^.!?]{0,40}\byou\b", re.I)
_PERCEIVE = re.compile(
    r"\b(?:seen|see|saw|know|knew|notice[ds]?|heard|hear|come across|came across|met|meet|"
    r"deal(?:t)? with|run into|ran into|get to see|have a view|have visibility|have a sense|"
    r"be aware|familiar|exposed to|across)\b", re.I)


def vantage(sentence: str) -> str:
    """The words that guess what they see from their level or title, or ""."""
    s = tone._plain(str(sentence or "")).strip()
    if not s or s.endswith("?") or not _ABOUT_THEM.search(s):
        return ""
    m = _VANTAGE.search(s)
    return m.group(0) if m and _PERCEIVE.search(s) else ""


# A comparison that never says how: "goes a lot further than", "a step on from", "take my
# work next" were all called unclear. Bigger, more complex, at more scale: say which.
VAGUE_COMPARISON = re.compile(
    r"\bgo(?:es|ing|ne)? (?:(?:a lot|a bit|a little|a step|much|way|even|well|far) )?further "
    r"than\b"
    r"|\b(?:a |the )?(?:big |real |natural |clear |logical )?step (?:on|up|beyond|further|"
    r"forward) (?:from|on from)\b"
    r"|\btak(?:e|es|ing) (?:my|the|this|that|our|their) (?:work|career|skills|experience) "
    r"(?:next|further|forward)\b"
    r"|\b(?:the|a) next level\b|\blevel up\b|\bbeyond what I(?:'ve| have)? (?:done|do|did)\b",
    re.I)
_SAYS_HOW = re.compile(
    r"\b(?:bigger|larger|smaller|fewer|harder|faster|wider|broader|deeper|complex\w*|scale\w*|"
    r"volumes?|more (?!of\b|than\b|about\b|to\b)\w+|senior|technical|\d[\d,.]*\w*)\b", re.I)
VAGUE_FIX = ("say how it compares: bigger, more complex, more data, more users, more senior "
             "(\"the same pricing models at ten times the volume\")")


# Their career read back to them: "you did X, then Y, then Z". Name the one step that links
# to the sender's.
_SEQUENCE = re.compile(
    r"\bthen\b|\bbefore that\b|\bbefore\b|\bafter (?:that|which)\b|\blater\b|\band now\b"
    r"|,\s*now\b|\bfollowed by\b|\bwent on to\b|\bthese days\b", re.I)
_FROM_TO_TO = re.compile(r"\bfrom\b[^.!?]{1,50}\bto\b[^.!?]{1,50}\b(?:and then|then|to)\b", re.I)


def cv_recital(sentence: str) -> bool:
    s = tone._plain(str(sentence or ""))
    if not _ABOUT_THEM.search(s) or s.rstrip().endswith("?"):
        return False
    return len(_SEQUENCE.findall(s)) >= 2 or bool(_FROM_TO_TO.search(s))


# Congratulations, then the jobs ask, in one note: their news used as the way in.
_CONGRATS = re.compile(r"\bcongrat\w*|\bwell done on\b", re.I)
_JOBS = re.compile(
    r"\banything (?:coming up|open)\b|\b(?:openings?|vacanc\w+|open (?:roles?|positions?|reqs?))\b"
    r"|\bhiring\b|\bopportunit\w+|\bjoin(?:ing)? (?:your|the) team\b|\bmy next role\b"
    r"|\b(?:roles?|positions?) (?:on|in|at) (?:your|the) team\b", re.I)


# A number is a figure; a year, the minutes asked for and "from 22% to 14%" (one change,
# said with two numbers) are not several.
_FIGURE = re.compile(r"(?<![\w.])(?:~|c\.\s?)?\$?\d[\d,.]*(?:\s?(?:%|k\b|m\b|bn\b|x\b)|\+)?")
_DURATION = re.compile(r"^\s*(?:-\s*\d+\s*)?(?:minutes?|mins?|hours?|days?|weeks?|months?)\b",
                       re.I)
METRIC_DUMP = {"connection": 3, "inmail": 4, "email": 5}


def figures(text: str) -> list[str]:
    """The figures in a message, a change ("from 22% to 14%") counted once."""
    t = tone._plain(str(text or ""))
    found = []
    for m in _FIGURE.finditer(t):
        raw = m.group(0).strip()
        if re.fullmatch(r"(?:19|20)\d\d", raw) or _DURATION.match(t[m.end():]):
            continue
        if found and re.fullmatch(r"\s*(?:to|-|\u2013|and|vs\.?)\s*", t[found[-1][1]:m.start()]):
            found[-1] = (found[-1][0] + " to " + raw, m.end())
            continue
        found.append((raw, m.end()))
    return [f for f, _ in found]


# A close with nothing to answer about them. "I'd love to join your team, or just learn more
# about it" was "a bit bare": the close that works asks about their current work or team.
_WORK_QUESTION = re.compile(
    r"\b(?:what|how|which|where|whether)\b[^.!?]{0,80}\b(?:working on|work(?:s)? on|focus\w* on|"
    r"building|set up|structured|organi[sz]ed|look(?:ing)? for|priorit\w+|at the moment|"
    r"right now|these days|this year|next|(?:the|your|their) (?:team|group|work|plans?))\b",
    re.I)
# The message with room for it. A connection note may close on a plain ask (the skill says
# so), and an email goes to someone who asked for it, often for the resume alone.
BARE_CLOSE_KINDS = frozenset({"inmail"})


def _signoff(sentence: str) -> bool:
    return len(sentence.split()) <= 3 and not sentence.rstrip().endswith("?")


def close(text: str, n: int = 2) -> list[str]:
    """The last `n` sentences before the sign-off: what the reader is left to answer."""
    sents = [s for s in tone.sentences(text) if not re.match(r"^subject\s*:", s, re.I)]
    while sents and _signoff(sents[-1]):
        sents.pop()
    return sents[-n:]


# ------------------------------------------------------------------ words said twice

# The words that carry no content of their own. "now" is not one: "now" twice in two
# sentences was the person's own example (2026-10-20).
_LIGHT = frozenset("""a an the and or but nor so yet for of to in on at by from with into onto
over under about as than then that this these those there here it its i me my mine we our ours
us you your yours he him his she her hers they them their theirs be am is are was were been
being have has had having do does did will would shall should can could may might must not no
if when while where which who whom whose what why how also just very too quite some any all
each both either own same other such only even back up out off one get got go going like hi
hey hello dear thanks thank much many more most well""".split())


def _stem(word: str) -> str:
    """Plural and possessive off (tone._stem), from five letters up."""
    return tone._stem(word, longer_than=4)


def _content_tokens(sentence: str, lower_seen: set) -> list[str]:
    out = []
    for i, tok in enumerate(re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)):
        low = tok.lower()
        if "'" in low and not low.endswith("'s"):
            continue                           # a contraction is a function word
        if tok[:1].isupper():
            # A name, wherever it sits; at the start of a sentence, a capital is only
            # position when the word is written in lower case elsewhere in the message.
            if i > 0 or tok.isupper() or low not in lower_seen:
                continue
        w = _stem(low)
        if len(w) >= 3 and w not in _LIGHT:
            out.append(w)
    return out


def content_words(text: str) -> set:
    """The content words of `text`, as `repeated()` counts them."""
    t = tone._plain(str(text or ""))
    seen = set(re.findall(r"\b[a-z][a-z'-]*", t))
    return {w for s in tone.sentences(t) for w in _content_tokens(s, seen)}


# What counts as a word said twice, plainly:
#   - a content word twice within one sentence is always warned ("consulting" twice in the
#     line about the sender);
#   - "now" in two sentences side by side is always warned: the person's own example
#     (2026-10-20);
#   - any other word in two sentences side by side is warned, unless the message's own
#     subject names it: a word of a sentence that speaks to them (the reason for writing,
#     their team) or asks them something (the question), or a team's own name ("the
#     pricing team"). A message about pricing says "pricing" more than once, as tone.py
#     argues for a reply, and was warned for it (2026-10-20).
_SAID_TWICE_ALWAYS = frozenset({"now"})
_TEAM_NAME = re.compile(r"\b([A-Za-z][\w'-]*)\s+(teams?)\b", re.I)


def _subject_words(sents: list[str], toks: list[list[str]]) -> set:
    """The words the message's own subject names (see above)."""
    out = set()
    for s, words in zip(sents, toks):
        if words and (_ABOUT_THEM.search(s) or s.rstrip().endswith("?")):
            out |= set(words)
        for m in _TEAM_NAME.finditer(tone._plain(s)):
            out |= {_stem(m.group(1)), _stem(m.group(2))}
    return out


def repeated(text: str) -> list[tuple[str, str]]:
    """[(word, where)] for each content word said twice in one sentence or in two sentences
    side by side, by the rule above. Names, numbers and the words that carry no content are
    left out, and so are the person's own fixed lines."""
    own = _own()
    sents = [s for s in tone.sentences(text) if not re.match(r"^subject\s*:", s, re.I)]
    # The greeting and the courtesy line are furniture, and the sign-off is a name.
    body = []
    for i, s in enumerate(sents):
        if i < 2:
            s = re.sub(r"^(?:hi|hey|hello|dear)\b[^,\n]{0,40},\s*", "", s, flags=re.I).strip()
            if not s or re.match(r"^(?:hope|trust)\b[^.!?]{0,40}\bwell\b", s, re.I):
                continue
        body.append(s)
    while body and _signoff(body[-1]):
        body.pop()
    lower_seen = {w for w in re.findall(r"\b[a-z][a-z'-]*", tone._plain(text))}
    # The person's fixed lines, their work authorization among them, are theirs as set: a
    # word in one is not a repeat of a word drafted beside it.
    wa = getattr(_NET, "WORK_AUTH", None)
    own |= {_norm(v) for v in (wa.values() if isinstance(wa, dict) else ()) if str(v).strip()}
    toks = [[] if _theirs(s, own) else _content_tokens(s, lower_seen) for s in body]
    subject = _subject_words(body, toks) - _SAID_TWICE_ALWAYS
    out, said = [], set()
    for i, words in enumerate(toks):
        dup = {w for w in words if words.count(w) > 1}
        if i + 1 < len(toks):
            dup |= (set(words) & set(toks[i + 1])) - subject
        for w in sorted(dup - said):
            said.add(w)
            out.append((w, body[i][:80]))
    return out


# ------------------------------------------------------------------ the person's voice

_YES = {"true", "yes", "y", "1", "on"}


def voice() -> dict:
    """The person's voice (profile/networking.py VOICE): {"contractions": bool, "shorthand":
    {full form: what they say}}. Absent or malformed, nothing changes: no contractions are
    suggested and no shorthand is used."""
    got = getattr(_NET, "VOICE", None)
    got = got if isinstance(got, dict) else {}
    short = got.get("shorthand")
    pairs = {}
    for k, v in (short.items() if isinstance(short, dict) else ()):
        k, v = " ".join(str(k or "").split()), " ".join(str(v or "").split())
        if k and v and k.lower() != v.lower():
            pairs[k] = v
    c = got.get("contractions", False)
    c = c.strip().lower() in _YES if isinstance(c, str) else bool(c)
    return {"contractions": c, "shorthand": pairs}


# The full forms a person who speaks in contractions would not write, and what they say.
CONTRACTIBLE = {
    "i would not": "I wouldn't", "i will not": "I won't", "i do not": "I don't",
    "i have been": "I've been", "you have been": "you've been", "we have been": "we've been",
    "i am": "I'm", "i would": "I'd", "i will": "I'll", "it is": "it's", "that is": "that's",
    "there is": "there's", "what is": "what's", "you are": "you're", "we are": "we're",
    "they are": "they're", "do not": "don't", "does not": "doesn't", "did not": "didn't",
    "cannot": "can't", "is not": "isn't", "are not": "aren't", "was not": "wasn't",
    "would not": "wouldn't", "will not": "won't",
}
_CONTRACTIBLE = re.compile(
    r"\b(?:" + "|".join(re.escape(k).replace(r"\ ", r"\s+")
                         for k in sorted(CONTRACTIBLE, key=len, reverse=True))
    + r")\b(?=\s+[A-Za-z])", re.I)


def _with_case(found: str, short: str) -> str:
    """What the person says, with the capital the full form had where it opened a sentence."""
    if found[:1].isupper() and short[:1].islower():
        return short[:1].upper() + short[1:]
    return short


def _shorthand_rx(full: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])" + r"\s+".join(map(re.escape, full.split())) + r"(?![\w'])",
                      re.I)


def _stiff(text: str, keep=()) -> list[tuple[int, int, str, str]]:
    """[(start, end, full form, what the person says)], in order, none overlapping."""
    v = voice()
    t = tone._plain(str(text or ""))
    kept = [str(k).lower() for k in keep or () if str(k).strip()]
    spans = []
    for full, short in v["shorthand"].items():
        if any(full.lower() in k or k in full.lower() for k in kept):
            continue
        spans += [(m.start(), m.end(), m.group(0), _with_case(m.group(0), short))
                  for m in _shorthand_rx(full).finditer(t)]
    if v["contractions"]:
        for m in _CONTRACTIBLE.finditer(t):
            opens = not t[:m.start()].strip() or re.search(r"[.!?\n]\s*$", t[:m.start()])
            if opens and tone.CONTRACTIONS == "refuse":
                continue
            spans.append((m.start(), m.end(), m.group(0), _with_case(
                m.group(0), CONTRACTIBLE[" ".join(m.group(0).lower().split())])))
    out, end = [], -1
    for sp in sorted(spans):
        if sp[0] >= end:
            out.append(sp)
            end = sp[1]
    return out


def stiff_forms(text: str, keep=()) -> list[tuple[str, str]]:
    """[(the full form, what the person says)]: their shorthand where they listed one, and a
    contraction where their VOICE says they speak in them (never opening a sentence when
    their CONTRACTIONS refuse that). `keep` holds names that stay as written: theirs."""
    return [(full, short) for _s, _e, full, short in _stiff(text, keep)]


def spoken(text: str, keep=()) -> str:
    """`text` in the person's own voice: each stiff form (stiff_forms) replaced by what they
    say. Nothing changes without a VOICE setting."""
    # The visible text: _stiff reads offsets in tone._plain(), which match it, not a text
    # still holding a zero-width space.
    out = tone._visible(text)
    for start, end, _full, short in reversed(_stiff(out, keep)):
        out = out[:start] + short + out[end:]
    return out


# ------------------------------------------------------------------ the person's own words

def _own() -> set:
    """The sentences the person set as their own (OPENER, ABOUT_ME, ASK, TEMPLATES)."""
    found = []
    for name in ("OPENER", "ABOUT_ME", "ASK", "WHO_LINE"):
        found.append(str(getattr(_NET, name, "") or ""))
    templates = getattr(_NET, "TEMPLATES", None)
    for intents in (templates.values() if isinstance(templates, dict) else ()):
        for variants in (intents.values() if isinstance(intents, dict) else ()):
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
          reading: dict | None = None, creds=None, keep=()) -> list[Advice]:
    """Every warning for this draft, each with its fix. `first_contact` defaults to the
    kind (a note, an InMail, an email); an exit is only warned about there. `keep` holds
    the names on the reader's side (their employer), which the person's shorthand leaves
    as written."""
    text = str(text or "")
    first_contact = (kind in FIRST_CONTACT) if first_contact is None else first_contact
    own = _own()
    out = []
    # The close, where it asks, is the sender's ask and never a claim about them: "I'd love
    # to join your team at Larkspur, or just hear more" was warned as one (2026-10-20).
    last = close(text, 1)
    for s in tone.sentences(text):
        if _theirs(s, own):
            continue
        for name, rx, fix in AI_TELLS:
            m = rx.search(s)
            if m:
                out.append(Advice("ai_tell", f"{name}: {m.group(0)}", with_open_ask(fix)))
        m = _LIST3.search(s)
        if m:
            out.append(Advice("three_credentials", m.group(0),
                              "a list of three reads as generated: name the one that matters "
                              "to this reader"))
        found = hedges(s)
        # A question hedges nothing it claims: "Would you know anyone I could speak to who
        # might know the team?" was warned as two hedges (2026-10-20).
        if len(found) >= 2 and not s.rstrip().endswith("?"):
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
                out.append(Advice("soft_exit", m.group(0), exit_fix()))
        seen = vantage(s)
        if seen:
            out.append(Advice("guesses_from_their_level", seen,
                              "what they see is a guess from their title: ask it (\"how do "
                              "the teams there tend to ...?\"), or cut it"))
        m = VAGUE_COMPARISON.search(s)
        if m and not _SAYS_HOW.search(s):
            out.append(Advice("vague_comparison", m.group(0), VAGUE_FIX))
        if cv_recital(s):
            out.append(Advice("cv_recital", s[:100],
                              "their career read back to them is a CV recital: name the one "
                              "step that links to yours (\"you moved from logistics into "
                              "forecasting, which is the move I'm making\")"))
        p = "" if (last and s == last[-1] and _ASKING_CLOSE.search(s)) \
            else provenance(s, reading)
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
    out += _whole(text, kind, first_contact)
    out += [Advice("repeated_word", f"\"{w}\" twice in: {where}",
                   "say it once: cut the second, or use another word for it")
            for w, where in repeated(text)]
    out += [Advice("stiff_full_form", full,
                   f"you say \"{short}\" (profile/networking.py VOICE): write that")
            for full, short in stiff_forms(text, keep)]
    try:
        import learned
        over = learned.overrides()
    except (ImportError, SystemExit):
        over = set()
    return [a for a in out if a.rule not in over]


def _whole(text: str, kind: str, first_contact: bool) -> list[Advice]:
    """What only the message as a whole shows: their news used as the way into a jobs ask, a
    run of numbers, and a close that asks nothing about them."""
    out = []
    if first_contact:
        c, j = _CONGRATS.search(text), _JOBS.search(text)
        if c and j:
            out.append(Advice("congratulations_then_a_jobs_ask", f"{c.group(0)} ... {j.group(0)}",
                              "their news is not the way into asking about roles: congratulate "
                              "them and ask about the work, or leave the news out"))
        most = METRIC_DUMP.get(kind)
        figs = figures(text)
        if most and len(figs) >= most:
            out.append(Advice("metric_dump", ", ".join(figs),
                              "one piece of work with its numbers is evidence; several is a "
                              "dump: keep the one that matters to this reader"))
        if kind in BARE_CLOSE_KINDS:
            ending = close(text)
            if ending and not any(_WORK_QUESTION.search(s) for s in ending):
                out.append(Advice("bare_close", ending[-1][:100],
                                  "the close asks nothing about them: add a real question "
                                  "about their current work or team (\"what is <team> working "
                                  "on at the moment, and what do you look for in people "
                                  "joining?\"; compose.inmail(team=) writes one)"))
    return out


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
