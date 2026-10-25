#!/usr/bin/env python3
"""What the person has told the search about themselves, kept for good.

The app ships defaults for everything a person has not had a view on yet: the
voice of a first note, the questions an interview pack asks, who counts as worth
contacting, which roles rank high. Defaults are how anyone starts. But every time
the person reacts ("I don't like this message", "not this kind of company", "too
formal", "stop asking me that"), that reaction is worth more than any default, and
it was being lost: applied once in the chat, forgotten by the next session, and
open to the next sync or upgrade putting the default back.

So every reaction is recorded here, in profile/learned.json, which is the person's
file and which no sync touches:

    {"entries": [{"date": "2026-10-15", "area": "voice",
                  "said": "too formal, I'd never say 'I hope this finds you well'",
                  "rule": "plain and direct; no stock pleasantries",
                  "applied_to": ["profile/networking.py OPENER"],
                  "never_say": ["hope this finds you well"],
                  "status": "active"}]}

- `rule` is what is different from now on, in one sentence, read before drafting.
- `applied_to` names every setting the reaction changed. Those settings are the
  person's now: an upgrade or a redone /setup section never changes them
  (`locked()`), only an explicit new instruction from the person does.
- `never_say` phrases are enforced in code: tools/network/tone.py and
  tools/voice_check.py flag them in anything drafted, as `person_dislikes`, and every
  composer in tools/network/compose.py refuses a message carrying one.
- `length` is how long they asked a kind of message to run, as a number
  (`--length inmail=170`): compose.inmail_words() reads it ahead of networking.py.

    python3 tools/learned.py brief [area]        # the active rules, for a drafting step
    python3 tools/learned.py list [area]         # every entry, numbered
    python3 tools/learned.py record --area voice --said "..." --rule "..." \\
        [--applied-to "profile/networking.py OPENER"]... [--never-say "..."]... \\
        [--overrides <check>]... [--replaces <n>]... [--length inmail[:<reader>]=<words>]...
    python3 tools/learned.py skip --said "..." --why "..."   # a reaction that sets no rule
    python3 tools/learned.py approve --said "..." --text-file <message> --channel inmail \\
        --reader peer                            # a message they approved, kept whole
    python3 tools/learned.py brief messages --channel inmail --reader peer   # examples first
    python3 tools/learned.py pending             # reactions this chat has not recorded
    python3 tools/learned.py retire <n>          # they changed their mind
    python3 tools/learned.py locked              # the settings no upgrade may change
    python3 tools/learned.py offers              # app improvements waiting on their choice
    python3 tools/learned.py decide <n> keep|switch

**A reaction is recorded, not remembered.** Writing "record each reaction" in CLAUDE.md
did not make it happen: one chat redrafted nine times on the person's corrections ("rude",
"identical in structure", "too long", "that's not how I found him") and recorded none of
them until asked. So it is code now. `hook` is the one hook the app ships: on each
prompt it notes a reaction in this chat's pending list (`pending`), and the turn cannot
end while one is there; `compose.py` and `reading.py draft` refuse to draft over one. A
`record` (or a `skip`, saying why it sets no rule) clears it. A record shows the rule
back in one line, lists the earlier rules it contradicts, with their dates, so the person
can say which stands, and may name the checks the rule outranks (`--overrides`): the
person's own voice wins over a validator's default once they have said so. An edit the
person made to a draft before sending it is recorded by itself (`record_edit`), from the
sent text against the draft.

**When the app learns something better.** A sync brings genuine fixes, and they
apply: they change code, not the person's settings. When an update would change a
setting the person has shaped (a better default voice, a sharper question set),
nothing changes behind their back and nothing is quietly ignored either: /upgrade
records an *offer* (`offer()`): what the app now does, what they chose and why. It is
put to them with the session's other questions: keep theirs, or switch. Either answer is
recorded; a switch retires the old entry and records the new choice as theirs, and a
keep is offered again after REOFFER_DAYS, saying when they kept it, because a no is for
now, never for ever.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

FILE = "learned.json"
# Where a reaction belongs. "other" catches the rest; an area is a filter for the
# brief, never a reason to drop what was said.
AREAS = ("voice", "messages", "questions", "people", "targets", "jobs", "documents",
         "search", "interview", "other")
# "targets" is which employers to pick and pursue; a rule about them went under "messages"
# for want of it (2026-10-20).


def _path() -> str | None:
    try:
        return person.path(FILE)
    except person.NoProfile:
        return None


def load() -> list[dict]:
    path = _path()
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("entries") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict)]


def _data() -> dict:
    path = _path()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {"entries": data}


_EXAMPLE = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "profile.example"))


def _writable() -> str:
    """Where a record goes, or SystemExit: never before /setup, and never into the app's
    example person, which the app's own tests read and a tool run there would change."""
    path = _path()
    if not path:
        raise SystemExit("learned: no profile; nothing can be recorded before /setup")
    if os.path.realpath(path).startswith(_EXAMPLE + os.sep):
        raise SystemExit("learned: profile.example is the app's example person; nothing is "
                         "recorded there")
    return path


def _save(rows: list[dict], offers_: list[dict] | None = None) -> None:
    path = _writable()
    data = _data()                       # what else the file keeps (the skips) stays
    data.update({"entries": rows, "offers": offers_ if offers_ is not None else all_offers()})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def entries(area: str | None = None) -> list[dict]:
    """The active entries, oldest first, for one area or all of them."""
    return [r for r in load() if r.get("status", "active") == "active"
            and (area is None or r.get("area") == area)]


def record(area: str, said: str, rule: str, applied_to=(), never_say=(),
           today: str | None = None, overrides=(), replaces=(), answers: bool = True,
           length=()) -> dict:
    """Keep one reaction, in the person's own words (`said`, kept as said). Returns the
    entry written, with `conflicts`: the earlier active rules it contradicts, for the
    person to choose between. `replaces` retires earlier entries by number, once they
    have chosen this one; `overrides` names the checks this rule outranks. `answers` is
    False for a record nobody reacted with (a profile rule adopted by an upgrade), which
    clears no reaction waiting in the chat. `length` is how long they asked a kind of
    message to run, as "<kind>[:<reader>]=<words>" ("inmail=170", "inmail:peer=160"): the
    length checks read it (`length()`), never the words of the rule."""
    if area not in AREAS:
        raise SystemExit(f"learned: area {area!r}; one of {', '.join(AREAS)}")
    if not str(said or "").strip() or not str(rule or "").strip():
        raise SystemExit("learned: record needs what they said and the rule it gives")
    entry = {"date": today or dt.date.today().isoformat(), "area": area,
             "said": str(said).strip(), "rule": " ".join(str(rule).split()),
             "applied_to": [str(a) for a in applied_to if str(a).strip()],
             "never_say": [str(p) for p in never_say if str(p).strip()],
             "status": "active"}
    over = [str(c).strip() for c in overrides if str(c).strip()]
    if over:
        entry["overrides"] = over
    lengths = parse_lengths(length)
    if lengths:
        entry["length"] = lengths
    rows = load()
    for n in replaces:
        if not 1 <= int(n) <= len(rows):
            raise SystemExit(f"learned: no entry {n} to replace; there are {len(rows)}")
        rows[int(n) - 1]["status"] = "retired"
        rows[int(n) - 1]["retired_for"] = entry["date"]
    found = conflicts(entry, rows)
    rows.append(entry)
    _save(rows)
    if answers:
        resolve_pending(entry["said"])
    return {**entry, "conflicts": found, "own_overlaps": own_overlaps(entry["never_say"])}


# Words that change nothing about what a phrase says: "recently moved" and "just moved"
# make the same claim, and the person who banned one and later wrote the other in their
# own template needs to be asked which stands.
_HEDGES = {"recently", "just", "currently", "now", "really", "very", "so", "the", "a",
           "an", "my", "i", "i'm", "i've", "i'd", "to", "of", "and", "in", "on", "for",
           "with", "that", "this", "is", "am", "be", "been", "have", "has", "it", "your"}


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z']+", str(text or "").lower())
            if w not in _HEDGES and len(w) > 2}


# A phrase a rule names only to forbid it ("never describe the move as relocating") is not
# a use of it: such a rule agrees with every other ban of the phrase.
_FORBIDS = re.compile(r"\b(?:never|stop|don'?t|do not|no more|avoid|without|not|instead of"
                      r"|rather than|cut|drop|lose|remove|ban)\b", re.I)


def _uses(text: str, phrase: str) -> bool:
    """Does `text` use `phrase`, rather than name it only to forbid it?"""
    if not _says(text, phrase):
        return False
    low, p = str(text or "").lower(), str(phrase).lower()
    if p in low:
        at = [m.start() for m in re.finditer(re.escape(p), low)]
    else:                                        # said in other words: where they start
        words = sorted(_content(p))
        at = [m.start() for w in words[:1]
              for m in re.finditer(r"\b%s\b" % re.escape(w), low)]
    for i in at:
        clause = re.split(r"[.;:!?\n]", low[:i])[-1]
        if not _FORBIDS.search(" ".join(clause.split()[-8:])):
            return True
    return False


def _says(text: str, phrase: str) -> bool:
    """Does `text` say what `phrase` says: the phrase itself, or every word of it that
    carries meaning?"""
    low = str(text or "").lower()
    if str(phrase).lower() in low:
        return True
    words = _content(phrase)
    return bool(words) and words <= _content(low)


# A setting, as `--applied-to` names one: an upper-case name ("OPENER", "TITLE_SETS").
_SETTING = re.compile(r"\b[A-Z][A-Z0-9]*_?[A-Z0-9_]{2,}\b")
_FILE_NAME = re.compile(r"\S+\.(?:md|py|json|csv|txt|tex)\b")


def conflicts(entry: dict, rows: list[dict] | None = None) -> list[tuple[int, dict, str]]:
    """[(number, earlier entry, why)] for each active entry, or never-write rule in
    profile/CLAUDE.md, that `entry` contradicts: one bans what the other prescribes, or
    both set one setting differently."""
    rows = load() if rows is None else rows
    mine = " ".join([entry.get("rule") or "", entry.get("said") or ""])
    bans = [str(p) for p in entry.get("never_say") or () if str(p).strip()]
    out = []
    for n, r in enumerate(rows, 1):
        if r.get("status", "active") != "active" or r is entry:
            continue
        theirs = " ".join([r.get("rule") or "", r.get("said") or ""])
        why = ""
        for p in r.get("never_say") or ():
            if _uses(mine, str(p)) and not any(_says(str(p), b) for b in bans):
                why = f"it says never \"{p}\", and this one uses it"
                break
        if not why:
            for p in bans:
                if _uses(theirs, p) and str(p).lower() not in {
                        str(x).lower() for x in r.get("never_say") or ()}:
                    why = f"it uses \"{p}\", which this one says never to"
                    break
        if not why:
            # Two rules that set one setting ("networking.py OPENER") differently ask which
            # stands. Two that only apply to the same file or section ("07-interview-prep.md")
            # are two rules, and were flagged as a contradiction (2026-10-20).
            same = {a for a in set(r.get("applied_to") or ()) & set(entry.get("applied_to") or ())
                    if _SETTING.search(_FILE_NAME.sub(" ", str(a)))}
            if same and (r.get("rule") or "") != (entry.get("rule") or ""):
                why = f"both set {', '.join(sorted(same))}"
        if why:
            out.append((n, r, why))
    adopted = {str(p).lower() for r in rows for p in r.get("never_say") or ()}
    for phrase, rule in profile_never_phrases():
        if phrase.lower() in adopted:
            continue                                # listed above, as the entry it became
        if _uses(mine, phrase) and not any(_says(phrase, b) for b in bans):
            out.append((0, {"date": "profile/CLAUDE.md", "rule": rule, "said": rule},
                        f"profile/CLAUDE.md says never \"{phrase}\", and this one uses it"))
    return out


def overrides() -> set[str]:
    """The checks a rule of the person's outranks, by name: a validator that fights their
    voice warns instead of refusing, once they have said which wins."""
    return {str(c) for r in entries() for c in r.get("overrides") or ()}


# ------------------------------------------------------------------ how long they want it

# "Slightly longer, more substance" was recorded as a rule, and the InMail length warning
# went on firing at 134 to 150 words, because nothing reads the words of a rule (2026-10-20).
# A length is recorded as a number, for a kind of message and, if they said, a reader.
LENGTH_READERS = ("any", "peer", "decision_maker", "recruiter")
_LENGTH = re.compile(r"^\s*([a-z_]+)(?::([a-z_]+))?\s*=\s*(\d{2,4})\s*$")


def parse_lengths(specs) -> dict:
    """{kind: {reader: words}} from "<kind>[:<reader>]=<words>" specs; SystemExit on one
    that is not that shape, so a typo is said rather than dropped."""
    if isinstance(specs, str):
        specs = [specs]
    out: dict = {}
    for spec in specs or ():
        m = _LENGTH.match(str(spec).lower())
        if not m or (m.group(2) or "any") not in LENGTH_READERS:
            raise SystemExit(f"learned: --length {spec!r}; write <kind>[:<reader>]=<words>, "
                             f"for example inmail=170 or inmail:peer=160 (readers: "
                             f"{', '.join(LENGTH_READERS)})")
        out.setdefault(m.group(1), {})[m.group(2) or "any"] = int(m.group(3))
    return out


def length(kind: str, reader: str = "any") -> int | None:
    """The words the person asked a `kind` of message to run to for this reader: the latest
    active entry that says, for this reader or for any. None when they never said."""
    got = None
    for r in entries():
        per = r.get("length")
        per = per.get(kind) if isinstance(per, dict) else None
        if not isinstance(per, dict):
            continue
        n = per.get(reader, per.get("any"))
        try:
            got = int(n) if n else got
        except (TypeError, ValueError):
            continue
    return got


# ------------------------------------------------------------------ edits before sending


def _changes(draft: str, sent: str, most: int = 3) -> list[tuple[str, str]]:
    import difflib
    a, b = str(draft or "").split(), str(sent or "").split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "equal":
            out.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return out[:most]


def record_edit(draft: str, sent: str, where: str = "", today: str | None = None) -> dict | None:
    """The person changed a draft before sending it: that edit is a reaction, recorded by
    itself, with both texts. None when nothing changed beyond spacing."""
    if " ".join(str(draft or "").split()) == " ".join(str(sent or "").split()):
        return None
    parts = []
    for old, new in _changes(draft, sent):
        if old and new:
            parts.append(f'"{old}" became "{new}"')
        elif old:
            parts.append(f'cut "{old}"')
        else:
            parts.append(f'added "{new}"')
    entry = {"date": today or dt.date.today().isoformat(), "area": "messages", "kind": "edit",
             "said": "edited the draft before sending" + (f" ({where})" if where else ""),
             "rule": "write it the way they edited it: " + "; ".join(parts),
             "applied_to": [], "never_say": [], "status": "active",
             "draft": str(draft).strip(), "sent": str(sent).strip()}
    rows = load()
    rows.append(entry)
    _save(rows)
    return entry


def retire(n: int) -> dict:
    """The person changed their mind: entry n stops applying, and stays as history."""
    rows = load()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no entry {n}; there are {len(rows)}")
    rows[n - 1]["status"] = "retired"
    _save(rows)
    return rows[n - 1]


def locked() -> list[str]:
    """Every setting a reaction changed: the person's, which no upgrade may change."""
    seen, out = set(), []
    for r in entries():
        for a in r.get("applied_to") or ():
            if a not in seen:
                seen.add(a)
                out.append(a)
    return out


# Where a sentence or a clause opens: the start of a line, after a full stop, question or
# exclamation mark (a closing quote between them), or after a comma or a colon.
_OPENS = (r"(?:^|(?<=[.!?,;:]\s)|(?<=[.!?,;:]\s\s)|(?<=[.!?][\"'\u201d\u2019)]\s)"
          r"|(?<=[\u2013-]\s))")
_ALWAYS_CAPITAL = {"i", "i'm", "i'd", "i've", "i'll"}


def opens_a_sentence(phrase: str) -> bool:
    """Is this never-say phrase written the way a sentence opens ("Love to hear"): two words
    or more, the first capitalised and the rest in lower case? Then it is matched only where
    a sentence or clause opens, so "Love to hear" bans the clipped sentence and leaves "I'd
    love to hear" alone, which matching it anywhere refused (2026-10-22). A name ("Larkspur
    Foods") and a phrase written in lower case are matched anywhere, as before."""
    words = str(phrase or "").split()
    return (len(words) >= 2 and bool(re.fullmatch(r"[A-Z][a-z'\u2019]+", words[0]))
            and words[0].lower().replace("\u2019", "'") not in _ALWAYS_CAPITAL
            and all(not w[:1].isupper() for w in words[1:]))


def never_say() -> list[tuple[str, re.Pattern]]:
    """(phrase, pattern) for every phrase the person has said never to use."""
    out = []
    for r in entries():
        for phrase in r.get("never_say") or ():
            # An apostrophe either way: a phrase typed on a phone arrives as "I’m", and the
            # message checks straighten every draft to "I'm" first, so the curly one never
            # matched anything (2026-10-20).
            words = [re.escape(w).replace("’", "'").replace("'", "['’]")
                     for w in str(phrase).split()]
            if words:
                # Edges that work for a phrase that opens or closes on punctuation: \b
                # needs a word character there, so "(remote)" or "[sic]" never matched.
                # A phrase quoted in profile/CLAUDE.md's prose takes its capital from the
                # sentence it was quoted in, so it is matched anywhere.
                quoted = str(r.get("rule") or "").endswith(FROM_PROFILE_RULES)
                start = _OPENS if opens_a_sentence(phrase) and not quoted else r"(?<!\w)"
                out.append((phrase, re.compile(start + r"\s+".join(words) + r"(?!\w)",
                                               re.I | re.M)))
    return out


def own_overlaps(phrases) -> list[tuple[str, str, str]]:
    """[(phrase, setting, the line)] where a never-say phrase would refuse the person's own
    words: their OWN_VOICE, OPENER, ASK, ABOUT_ME or TEMPLATES in profile/networking.py.
    Every draft using that line would then be refused, so record() says so at once."""
    try:
        net = person.module("networking") if person.exists("networking.py") else None
    except person.NoProfile:
        net = None
    if net is None:
        return []
    own = []
    for name in ("OPENER", "ASK", "ABOUT_ME"):
        if str(getattr(net, name, "") or "").strip():
            own.append((name, str(getattr(net, name))))
    for key, got in (getattr(net, "TEMPLATES", None) or {}).items():
        for v in (got.values() if isinstance(got, dict) else [got]):
            for line in (v if isinstance(v, (list, tuple)) else [v]):
                if str(line or "").strip():
                    own.append((f"TEMPLATES {key}", str(line)))
    voice = getattr(net, "OWN_VOICE", None)
    if voice is not None and getattr(voice, "pattern", ""):
        # The pattern's own words, without its escapes: "I\'d love to hear" reads as said.
        own.append(("OWN_VOICE", re.sub(r"\\(.)", r"\1", voice.pattern)))
    out = []
    for phrase in phrases:
        words = [re.escape(w).replace("'", "['’]") for w in str(phrase).replace("’", "'").split()]
        if not words:
            continue
        start = _OPENS if opens_a_sentence(phrase) else r"(?<!\w)"
        rx = re.compile(start + r"\s+".join(words) + r"(?!\w)", re.I | re.M)
        out += [(phrase, setting, line) for setting, line in own if rx.search(line)]
    return out


# A phrase the profile's own rules (profile/CLAUDE.md) say never to write: quoted, in
# the clause a "never" opens ("Never write \"moving to <City>\", \"relocating\" or ...").
# Written there as prose, such a rule was followed only when the drafting model read
# it, and compose.validate passed a note that broke it. Adopted as a never-say phrase,
# every check reads it.
_NEVER_CUE = re.compile(r"\b(?:never|do not (?:write|say|use)|don't (?:write|say|use))\b", re.I)
_QUOTED = re.compile(r'(?<![*\w])"([^"\n]{1,60})"(?![*\w])'
                     r"|(?<![*\w])\u201c([^\u201d\n]{1,60})\u201d(?![*\w])")
_CLAUSE_END = re.compile(r"[;:(]|\.(?:\s|$)|\n\s*\n|\bbut\b|\bthe line is\b|\binstead\b", re.I)
PROFILE_RULES = "CLAUDE.md"
FROM_PROFILE_RULES = " (a rule in profile/CLAUDE.md)"
MAX_PHRASE_WORDS = 6


def profile_never_phrases(text: str | None = None) -> list[tuple[str, str]]:
    """[(phrase, the words that rule it out)] from profile/CLAUDE.md, in order, once each.
    A quote in italics is the person's own words reported, never a phrase to ban, and
    the document nouns the profile bans (documents.banned_nouns) are checked already."""
    if text is None:
        try:
            with open(person.path(PROFILE_RULES), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, person.NoProfile):
            return []
    nouns = {str(n).lower() for n in person.get("documents.banned_nouns", []) or []}
    out, seen = [], set()
    for m in _NEVER_CUE.finditer(text):
        rest = text[m.end():m.end() + 240]
        end = _CLAUSE_END.search(rest)
        clause = rest[:end.start()] if end else rest
        for q in _QUOTED.finditer(clause):
            phrase = (q.group(1) or q.group(2)).strip()
            low = phrase.lower()
            if (not re.search(r"[A-Za-z]", phrase) or len(phrase.split()) > MAX_PHRASE_WORDS
                    or low in seen or low in nouns):
                continue
            seen.add(low)
            out.append((phrase, " ".join((m.group(0) + clause).split())))
    return out


def unadopted() -> list[tuple[str, str]]:
    """The profile's never-write phrases not yet a never-say phrase. One the person
    retired counts as handled: their retiring it is the newer word."""
    have = {str(p).lower() for r in load() for p in r.get("never_say") or ()}
    return [(p, why) for p, why in profile_never_phrases() if p.lower() not in have]


def adopt_profile_rules(today: str | None = None) -> list[str]:
    """Record each unadopted phrase, one entry per rule it came from. Returns them."""
    by_rule: dict[str, list[str]] = {}
    for phrase, why in unadopted():
        by_rule.setdefault(why, []).append(phrase)
    for why, phrases in by_rule.items():
        record("documents", why, "never write " + ", ".join('"%s"' % p for p in phrases)
               + FROM_PROFILE_RULES, applied_to=["profile/CLAUDE.md"],
               never_say=phrases, today=today, answers=False)
    return [p for ps in by_rule.values() for p in ps]


def dislikes(text: str) -> list[str]:
    """The phrases in `text` the person has said never to use."""
    return [m.group(0) for _, rx in never_say() for m in rx.finditer(str(text or ""))]


def _key(r: dict) -> tuple:
    return (r.get("date"), r.get("area"), r.get("rule"))


def superseded(rows: list[dict] | None = None) -> dict:
    """{key of an active entry: the later active entry that overrules it}.

    A later entry overrules an earlier one when the earlier rule prescribes a phrase the
    later one says never to use: "every first note names the move (said as: I made the
    move)" and, two days on, never_say "I made the move". Both stayed active, and the
    brief told a drafting step to do both. The earlier stays on record as history; the
    brief leaves it out. An earlier entry that itself says never to use the phrase agrees
    with the later one and stands.
    """
    rows = load() if rows is None else rows
    active = [r for r in rows if r.get("status", "active") == "active"]
    out = {}
    for n, r in enumerate(active):
        text = str(r.get("rule") or "").lower()
        own = {str(p).lower() for p in r.get("never_say") or ()}
        for later in active[n + 1:]:
            if any(p.strip() and p.lower() in text and p.lower() not in own
                   for p in map(str, later.get("never_say") or ())):
                out[_key(r)] = later
                break
    return out


def brief(area: str | None = None, channel: str | None = None, reader: str | None = None) -> str:
    """The active rules as lines to follow before drafting, or "" when there are none.
    A rule a later one overrules (superseded) is left out. For messages, the messages the
    person approved come first (`approved_examples`), for this channel and reader where
    there are some: rules drawn from them were followed, and the messages themselves were
    never put in front of the drafter (2026-10-21)."""
    over = superseded()
    rows = [r for r in entries(area) if _key(r) not in over]
    if area is not None:
        rows = rows + [r for r in entries("other") if r not in rows and _key(r) not in over]
    lines = []
    if area in (None, "messages", "voice"):
        shown = approved_examples(channel, reader)
        if shown:
            lines.append("Messages you approved, best match first. Follow their shape only: "
                         "never reuse a name, an employer or any fact from them, which belong "
                         "to the person each was written for:")
            for x in shown:
                lines.append(f"  [{x.get('channel') or 'any channel'}, "
                             f"{(x.get('reader') or 'any reader').replace('_', '-')}, "
                             f"{x.get('date')}; you said: \"{x.get('said')}\"]")
                lines += ["    " + ln for ln in shape_of(x)[:EXAMPLE_CHARS].splitlines()
                          if ln.strip()]
            if rows:
                lines.append("Rules:")
    lines += [f"- {r['rule']} ({r['date']}, they said: \"{r['said']}\")" for r in rows]
    return "\n".join(lines)


# ------------------------------------------------------------ messages the person approved

# "Great, both sent", "almost perfect", "more of this": a message the person approved is the
# best example there is of what they want, better than any rule drawn from it. A set of
# InMails approved on 2026-10-20 sat in the message log and some forty rules were written
# from them, and the drafter never saw one of them. They are kept here, whole.
EXAMPLES_SHOWN = 5
EXAMPLE_CHARS = 1200
CHANNELS = ("connection", "inmail", "dm", "message", "email", "nudge", "reply", "intro")
READERS = ("peer", "decision_maker", "recruiter")


def approved(include_retired: bool = False) -> list[dict]:
    rows = [r for r in (_data().get("approved") or []) if isinstance(r, dict)]
    return rows if include_retired else [r for r in rows if r.get("status", "active") == "active"]


def approve(said: str, text: str, channel: str = "", reader: str = "", contact_id: str = "",
            today: str | None = None) -> dict:
    """Keep a message the person approved as an example: their words about it (`said`), the
    message whole (`text`), its channel and who it was for. It answers the reaction waiting
    in the chat, the way a record does."""
    if not str(said or "").strip() or not str(text or "").strip():
        raise SystemExit("learned: approve needs what they said and the message itself")
    channel = str(channel or "").strip().lower()
    reader = str(reader or "").strip().lower().replace("-", "_")
    if channel and channel not in CHANNELS:
        raise SystemExit(f"learned: channel {channel!r}; one of {', '.join(CHANNELS)}")
    if reader and reader not in READERS:
        raise SystemExit(f"learned: reader {reader!r}; one of {', '.join(READERS)}")
    path = _writable()
    data = _data()
    row = {"date": today or dt.date.today().isoformat(), "said": str(said).strip(),
           "text": str(text).strip(), "channel": channel, "reader": reader,
           "status": "active"}
    if contact_id:
        row["contact_id"] = str(contact_id).strip()
    rows = [r for r in (data.get("approved") or []) if isinstance(r, dict)]
    if any(" ".join(str(r.get("text") or "").split()) == " ".join(row["text"].split())
           and r.get("status", "active") == "active" for r in rows):
        resolve_pending(row["said"])
        return {**row, "already": True}
    rows.append(row)
    data["approved"] = rows
    data.setdefault("entries", load())
    data.setdefault("offers", all_offers())
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    resolve_pending(row["said"])
    return row


def approved_examples(channel: str | None = None, reader: str | None = None,
                      most: int = EXAMPLES_SHOWN) -> list[dict]:
    """The approved messages a draft for this channel and reader should follow, best match
    first: the same channel and reader, then the same channel, then the same reader, then
    the rest; the newest first within each."""
    channel = str(channel or "").strip().lower()
    reader = str(reader or "").strip().lower().replace("-", "_")

    def rank(r):
        same_c = bool(channel) and r.get("channel") == channel
        same_r = bool(reader) and r.get("reader") == reader
        return -(2 * same_c + same_r)

    rows = sorted(approved(), key=lambda r: str(r.get("date") or ""), reverse=True)
    return sorted(rows, key=rank)[:most]        # stable: the newest first within each


def contact_book() -> list:
    """The contact book's rows, or [] when it cannot be read."""
    try:
        import csv_store
        return csv_store.read_rows(person.state("network_contacts.csv"))
    except Exception:  # noqa: BLE001  a brief must never break on the book
        return []


def example_reader(x: dict, book: list | None = None) -> tuple:
    """(name, employer) of the person an approved example was written for, from the contact
    book (`book`, else read), else from what was read about them; ("", "") for one kept
    with no contact."""
    cid = str((x or {}).get("contact_id") or "").strip()
    if not re.match(r"^[\w.-]+$", cid):
        return "", ""
    rows = contact_book() if book is None else book
    for r in rows:
        if str(r.get("contact_id") or "").strip() == cid:
            return str(r.get("name") or "").strip(), str(r.get("company") or "").strip()
    try:
        with open(person.state("documents", "network", cid, "reading.json"),
                  encoding="utf-8") as fh:
            got = json.load(fh)
        return str(got.get("name") or "").strip(), str(got.get("company") or "").strip()
    except (OSError, ValueError, AttributeError):
        return "", ""


def _name_words(name: str) -> list:
    """The full name, then each word of it long enough to be a name, longest first."""
    words = [w for w in re.findall(r"[^\W\d_][\w'-]*", str(name or "")) if len(w) >= 2]
    full = " ".join(words)
    return ([full] if len(words) > 1 else []) + sorted(set(words), key=len, reverse=True)


def employer_pattern(company: str):
    """A pattern for an employer as a message names it: its name, or its key (the name
    without Ltd, Group and the like), word for word. None for no employer."""
    try:
        from company_key import key
        short = key(company)
    except Exception:  # noqa: BLE001  no employers.py in an odd profile
        short = ""
    forms = []
    for f in (company, short):
        words = re.findall(r"[a-z0-9&]+", str(f or "").lower())
        if words and words not in forms:
            forms.append(words)
    if not forms:
        return None
    return re.compile("|".join(r"(?<![a-z0-9])" + r"\W+".join(map(re.escape, w))
                               + r"(?![a-z0-9])" for w in forms), re.I)


def shape_of(x: dict) -> str:
    """An approved example as the brief shows it: the name and employer of the person it was
    written for replaced by <their name> and <their employer>. Shown whole, the next note
    to someone at another employer was copied from it, that person's employer and the talk
    they gave included (2026-10-21)."""
    text = str((x or {}).get("text") or "")
    name, company = example_reader(x)
    pat = employer_pattern(company)
    if pat is not None:
        text = pat.sub("<their employer>", text)
    for w in _name_words(name):
        text = re.sub(r"(?<![\w'-])" + re.escape(w) + r"(?![\w'-])", "<their name>", text)
    return text


def all_offers() -> list[dict]:
    rows = _data().get("offers") or []
    return [r for r in rows if isinstance(r, dict)]


# Keeping their own way is an answer for now, never for ever: a kept choice is offered
# again once this many days have passed (tools/profile_upgrades.py REASK_DAYS, the same
# rule every question follows), saying when they kept it. A switch is final: it is theirs.
REOFFER_DAYS = 30


def offers(today: dt.date | None = None) -> list[tuple[int, dict]]:
    """(number, offer) for every app improvement waiting on the person's choice: never
    answered, or kept long enough ago to be worth asking again."""
    today = today or dt.date.today()
    out = []
    for i, o in enumerate(all_offers(), 1):
        if not o.get("decision"):
            out.append((i, o))
        elif o.get("decision") == "keep":
            try:
                kept = dt.date.fromisoformat(str(o.get("decided") or ""))
            except ValueError:
                continue
            if (today - kept).days >= REOFFER_DAYS:
                out.append((i, {**o, "again": f"you kept your own way on {kept.isoformat()}"}))
    return out


def offer(setting: str, new: str, why: str, version: str, today: str | None = None) -> dict:
    """An update would change a setting the person shaped: ask, never overwrite.

    One offer per setting and app version; a version already offered, kept or
    switched is not offered again.
    """
    rows = all_offers()
    for o in rows:
        if o.get("setting") == setting and o.get("version") == version:
            return o
    mine = [r for r in entries() if setting in (r.get("applied_to") or ())]
    o = {"date": today or dt.date.today().isoformat(), "setting": setting,
         "version": version, "new": " ".join(str(new).split()),
         "why": " ".join(str(why).split()),
         "theirs": mine[-1]["rule"] if mine else "", "said": mine[-1]["said"] if mine else "",
         "decision": ""}
    rows.append(o)
    _save(load(), rows)
    return o


def question(o: dict) -> str:
    """The offer as the one plain question the person is asked."""
    theirs = (f" You told me \"{o['said']}\", so it is: {o['theirs']}." if o.get("said") else "")
    again = f" Asked again: {o['again']}." if o.get("again") else ""
    return (f"The app now does this differently ({o['setting']}): {o['new']}. {o['why']}.{theirs}"
            f"{again} Keep yours, or try the new way?")


def decide(n: int, choice: str, today: str | None = None) -> dict:
    """Record the person's answer to offer n: `keep` theirs or `switch` to the app's."""
    if choice not in ("keep", "switch"):
        raise SystemExit("learned: decide keep|switch")
    rows = all_offers()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no offer {n}; there are {len(rows)}")
    o = rows[n - 1]
    o["decision"], o["decided"] = choice, today or dt.date.today().isoformat()
    entries_ = load()
    if choice == "switch":
        for r in entries_:
            if o["setting"] in (r.get("applied_to") or ()) and r.get("status", "active") == "active":
                r["status"] = "retired"
        entries_.append({"date": o["decided"], "area": "other",
                         "said": f"switched to the app's new way ({o['version']})",
                         "rule": o["new"], "applied_to": [o["setting"]], "never_say": [],
                         "status": "active"})
    _save(entries_, rows)
    return o


# ------------------------------------------------------------------ reactions not yet recorded

# What a person says when they react to something drafted or surfaced. Loose on purpose:
# a false alarm costs one `skip` with its reason, and a missed reaction costs the person
# saying it again, which is the failure this exists for. But not so loose that a reply
# the person pastes in for /reply ("sounds like a great fit", "I'd prefer Tuesday") reads
# as their reaction: a word that is ordinary in a contact's message counts only where it
# is said about something ("that's awkward", "too much").
_ABOUT = r"(?:that'?s|it'?s|this is|that is|these are|sounds?|reads?|feels?|looks?|seems?|bit|so|too|very|really)\s+"
REACTION = re.compile("|".join([
    r"\b(?:i\s+)?(?:don'?t|do not|didn'?t)\s+like\b",
    r"\bi\s+(?:don'?t|do not|didn'?t)\s+(?:love|want)\s+(?:it|this|that|the|them|those|these|him|her)\b",
    r"\bi\s+hate\s+(?:it|this|that|the|them|those|these|how|when)\b",
    r"\bnot (?:a )?fan\b",
    r"\b(?:too|way too)\s+(?:much|many)\b",
    r"\b(?:too|so|very|really|way too)\s+(?:formal|long|short|wordy|stiff|robotic|generic|salesy"
    r"|pushy|cringe\w*|rude|polite|indirect|vague|samey|stilted|corporate)\b",
    r"\b(?:rude|cringe\w*|robotic|stilted|clunky|creepy|patroni[sz]ing)\b",
    r"\b" + _ABOUT + r"(?:a bit |quite |pretty )?(?:awkward|weird|desperate|useless|pointless"
    r"|awful|terrible)\b",
    r"\breads? like\b",
    r"\bsounds? like (?:ai|a bot|a robot|chatgpt|a template|a sales pitch|a cover letter)\b",
    r"\b(?:ai|chatgpt|gpt)[- ]?(?:sounding|generated|written|ish|tells?)\b",
    r"\bthat'?s not (?:how|what|right|true|me)\b", r"\bnot how i\b",
    r"\bwhy (?:did|would|do) you (?:say|write|use|put|add|include|open|start|end|word|phrase)\b",
    r"\bstop (?:suggesting|using|saying|adding|putting|sending|doing|asking)\b",
    r"\bnever (?:say|use|write|suggest|send|put|call)\b",
    r"\b(?:don'?t|do not) (?:say|use|write|suggest|send|put|add|mention|call|start|end|open)\b",
    # "identical" alone is anyone's word (a research report used it): a reaction says what is.
    r"\b(?:(?:all|they'?re|they are|these are|those are|it'?s|looks?|reads?|sounds?)\s+"
    r"(?:\w+\s+)?identical|identical (?:in|structure|to each other)|all the same"
    r"|same (?:structure|shape|opener|opening|closing|line|ending))\b",
    r"\b(?:i|i've|i have) (?:changed|edited|rewrote|reworded|tweaked)\b",
    r"\bhere'?s what i (?:sent|wrote)\b", r"\bwhat i actually sent\b",
    r"\bi (?:sent|wrote) (?:this|it) instead\b",
    r"\bi'?d (?:rather|prefer)\b", r"\bi prefer\b",
    r"\b(?:more|less) (?:casual|direct|formal|warm|friendly|personal|specific|forthright"
    r"|concise|human|natural|honest)\b",
]), re.I)


# What is never the person's own reaction inside their message: a reminder the harness
# adds, text they pasted (a contact's reply, a posting), a quoted line, a code block.
_NOT_THEIRS = re.compile(r"<system-reminder>.*?</system-reminder>"
                         r"|<pasted_content\b[^>]*>.*?</pasted_content>"
                         r"|<task-notification>.*?</task-notification>"
                         r"|<agent-message\b[^>]*>.*?</agent-message>"
                         r"|```.*?```|^\s*>.*?$"
                         # A document's own headings ("**Do not say**", "## Notes") are its
                         # labels, never the person saying anything.
                         r"|^\s*#{1,6}\s.*?$|^\s*(?:\*\*|__)[^*_\n]{1,80}(?:\*\*|__)\s*:?\s*$",
                         re.S | re.M)
# Text another agent or a notification wrote, wherever it sits in the prompt.
_RELAYED = re.compile(r"\[Subagent hand-back\]|Another Claude session sent a message|"
                      r"\[SYSTEM NOTIFICATION", re.I)
_LONG_QUOTE = re.compile(r'"[^"\n]{80,}"|\u201c[^\u201d\n]{80,}\u201d')
# "She replied: ..." introduces their words, not the person's.
_THEIR_WORDS = re.compile(r"\b(?:replied|wrote back|responded|answered|said|wrote|messaged"
                          r"|their (?:reply|message|answer)|(?:his|her) (?:reply|message|answer)"
                          r"|the reply)\s*:", re.I)


# The person approving a message: kept as an example (`approve`), the way a reaction against
# one is kept as a rule. Said about a message, never a contact's own words (the same cuts
# `reaction` makes apply).
APPROVAL = re.compile("|".join([
    r"\b(?:almost|nearly|just about|pretty much)?\s*perfect\b",
    r"\bmore (?:of|like) (?:this|these|that|those)\b",
    r"\b(?:great|good|nice|lovely)[,!.]?\s+(?:both|all|they'?re|it'?s|that'?s)?\s*(?:been\s+)?sent\b",
    r"\b(?:sent|sending) (?:it |them |both |all )?as (?:is|written|drafted)\b",
    r"\b(?:spot on|nailed it|exactly (?:right|it)|that'?s the one|these are (?:great|good|perfect))\b",
    r"\b(?:love|loved) (?:this|these|it|them|that one)\b",
]), re.I)


def approval(text: str) -> str:
    """The words in `text` that approve a message, or "" when it approves none."""
    t = str(text or "").replace("\u2019", "'").replace("\u2018", "'")
    if not t.strip() or t.lstrip().startswith(("<task-notification", "<system-reminder",
                                                 "<command-", "<local-command", "/reply")):
        return ""
    if _RELAYED.search(t):
        return ""
    t = _LONG_QUOTE.sub(" ", _NOT_THEIRS.sub(" ", t))
    cut = _THEIR_WORDS.search(t)
    if cut:
        t = t[:cut.start()]
    if reaction(t):
        return ""                  # a reaction against it is the one to record
    m = APPROVAL.search(t)
    return m.group(0).strip() if m else ""


def reaction(text: str) -> str:
    """The words in `text` that make it a reaction, or "" when it is none."""
    t = str(text or "").replace("\u2019", "'").replace("\u2018", "'")
    if not t.strip() or t.lstrip().startswith(("<task-notification", "<system-reminder",
                                                 "<command-", "<local-command")):
        return ""
    if t.lstrip().startswith("/reply"):          # the rest is the contact's message
        t = t.lstrip().split("\n", 1)[0]
    if _RELAYED.search(t):                       # another agent's report, relayed
        return ""
    t = _LONG_QUOTE.sub(" ", _NOT_THEIRS.sub(" ", t))
    cut = _THEIR_WORDS.search(t)
    if cut:
        t = t[:cut.start()]
    m = REACTION.search(t)
    return m.group(0) if m else ""


def _reactions_path() -> str | None:
    """This chat's list: its own worktree's git directory, never shared with another
    chat's folder. Tests point LJS_STATE at a temporary folder; a test that does not
    (the person's own, run by the sync) never reads the chat's list, so a reaction
    waiting in the chat cannot fail it."""
    st = os.environ.get("LJS_STATE")
    if st:
        return os.path.join(st, ".reactions.json")
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    import subprocess
    try:
        r = subprocess.run(["git", "-C", os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True,
            timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    gd = r.stdout.strip()
    return os.path.join(gd, "ljs-reactions.json") if r.returncode == 0 and gd else None


def _load_pending() -> list[dict]:
    p = _reactions_path()
    try:
        with open(p, encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, TypeError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _save_pending(rows: list[dict]) -> None:
    p = _reactions_path()
    if not p:
        return
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False)
    except OSError:
        pass


# An answered reaction is remembered for a day, so the end of the turn, which reads the
# transcript again, does not put back one that was recorded some way it cannot see.
ANSWERED_KEEP = dt.timedelta(days=1)


def _fresh(rows: list[dict]) -> list[dict]:
    cut = (dt.datetime.now() - ANSWERED_KEEP).isoformat(timespec="seconds")
    return [r for r in rows if not r.get("answered") or str(r.get("answered")) >= cut]


def pending() -> list[dict]:
    """Reactions this chat has noted and not yet recorded or skipped."""
    return [r for r in _load_pending() if not r.get("answered")]


def note_reaction(text: str, cue: str = "", again: bool = False) -> dict | None:
    """Put a reaction on this chat's list, once. `again` is a new message from the person,
    which counts even in words they used before; read back from the transcript, a
    reaction already answered stays answered."""
    said = " ".join(str(text or "").split())[:400]
    if not said:
        return None
    rows = _fresh(_load_pending())
    if any(r.get("said") == said and (not again or not r.get("answered")) for r in rows):
        return None
    row = {"said": said, "cue": cue or reaction(text),
           "at": dt.datetime.now().isoformat(timespec="seconds")}
    rows.append(row)
    _save_pending(rows)
    return row


def resolve_pending(said: str = "") -> None:
    """A record or a skip clears the reaction it answers: the one it quotes, else the
    oldest."""
    rows = _fresh(_load_pending())
    waiting = [i for i, r in enumerate(rows) if not r.get("answered")]
    if not waiting:
        return
    words = _content(said)
    best = max(waiting, key=lambda i: len(words & _content(rows[i].get("said"))))
    if not words or not (words & _content(rows[best].get("said"))):
        best = waiting[0]
    rows[best]["answered"] = dt.datetime.now().isoformat(timespec="seconds")
    _save_pending(rows)


def skip(said: str, why: str, today: str | None = None) -> dict:
    """A reaction that sets no rule (a one-off, or not a reaction at all), with the reason:
    the explicit alternative to recording it."""
    if not str(why or "").strip():
        raise SystemExit("learned: skip needs why it sets no rule")
    data = _data()
    row = {"date": today or dt.date.today().isoformat(), "said": str(said or "").strip(),
           "why": " ".join(str(why).split())}
    path = _writable()
    if path:
        data.setdefault("skipped", []).append(row)
        data.setdefault("entries", load())
        data.setdefault("offers", all_offers())
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    resolve_pending(said)
    return row


def refuse_over_pending(what: str) -> str:
    """The line a drafting command prints, and refuses on, while a reaction waits."""
    rows = pending()
    if not rows:
        return ""
    first = rows[0]["said"]
    return (f"{what}: {len(rows)} reaction(s) from the person not recorded yet, the first: "
            f"\"{first[:160]}\". Record it before drafting again (python3 tools/learned.py "
            "record --area <area> --said \"<their words>\" --rule \"<what changes>\"), or say "
            "why it sets no rule (python3 tools/learned.py skip --said \"...\" --why \"...\").")


# How many times the end of one turn is held for one reaction before letting it end with
# a warning: the chat can always record or skip, so this is only a guard against a loop.
HOLD_LIMIT = 3


# A long chat's transcript runs to hundreds of megabytes, and the end of every turn read
# it whole. Only the current turn matters: it is read from the end, a block at a time,
# back to the last turn the chat finished, and never more than TAIL_MAX.
TAIL_BLOCK = 1 << 20
TAIL_MAX = 32 << 20
_TURN_END = (b'"stop_reason":"end_turn"', b'"stop_reason": "end_turn"')


def _tail_lines(path: str) -> list[str]:
    """The transcript's lines from the last finished turn on (or its last TAIL_MAX)."""
    try:
        fh = open(path, "rb")
    except (OSError, TypeError):
        return []
    with fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        at, data = size, b""
        while at > 0 and size - at < TAIL_MAX:
            step = min(TAIL_BLOCK, at)
            at -= step
            fh.seek(at)
            data = fh.read(step) + data
            lines = data.split(b"\n")
            body = lines[1:] if at > 0 else lines      # the first may be a part line
            # The last finished turn before the person's latest message: the current
            # turn's own final message may already be written when the hook runs.
            users = [i for i, ln in enumerate(body) if b'"type":"user"' in ln
                     or b'"type": "user"' in ln]
            ends = [i for i, ln in enumerate(body) if any(t in ln for t in _TURN_END)
                    and users and i < users[-1]]
            if ends:
                return [ln.decode("utf-8", "replace") for ln in body[ends[-1]:]]
        lines = data.split(b"\n")
        return [ln.decode("utf-8", "replace") for ln in (lines[1:] if at > 0 else lines)]


def _transcript_texts(path: str) -> list[tuple[int, str, str]]:
    """[(line number, kind, text)] from the end of a Claude Code transcript: kind "user"
    for what the person typed, "tool" for each command the chat ran, "end" where the chat
    finished a turn."""
    out = []
    for n, line in enumerate(_tail_lines(path)):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("isMeta") or d.get("isSidechain") \
                or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
            continue                    # a summary of earlier turns, or not in the chat
        origin = d.get("origin") if isinstance(d.get("origin"), dict) else {}
        if d.get("type") == "user" and origin.get("kind") not in (None, "human"):
            continue                    # a notification or another agent, not the person
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = msg.get("content")
        if d.get("type") == "user":
            if isinstance(content, str):
                out.append((n, "user", content))
            elif isinstance(content, list):
                texts = [c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text"]
                if texts and not any(isinstance(c, dict) and c.get("type") == "tool_result"
                                     for c in content):
                    out.append((n, "user", "\n".join(texts)))
        elif d.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                    out.append((n, "tool", " ".join(str(v) for v in inp.values())))
            if msg.get("stop_reason") == "end_turn":
                out.append((n, "end", ""))
    return out


def _this_turn(items: list) -> list:
    """What came after the last turn the chat finished before the person's latest message:
    the prompt that opened this turn, the messages sent while it worked, and what it ran
    (and this turn's own final message, which may already be written). A reaction days old
    in a chat that has carried on since is not this turn's to hold."""
    users = [i for i, it in enumerate(items) if it[1] == "user"]
    if not users:
        return []
    for i in range(users[-1] - 1, -1, -1):
        if items[i][1] == "end":
            return items[i + 1:]
    return items


_ANSWERED = re.compile(r"learned\.py[\"']?\s+(?:record|skip|approve)\b"
                       r"|\blearned\.(?:record|skip|approve)\(")


def hook(event: dict) -> dict:
    """The Claude Code hook (the one the app ships, allowlisted in security_guards.py).

    UserPromptSubmit: a prompt that reads as a reaction goes on this chat's list, and the
    chat is told, in the turn, to record it. Stop: the turn is held while a reaction from
    the person has no `learned.py record` or `skip` after it, read from the transcript
    (which also holds messages sent while the chat was working) and from the list. Returns
    what the hook prints: {} to let things be."""
    path = _path()
    if path is None or os.path.realpath(path).startswith(_EXAMPLE + os.sep):
        return {}                     # the app itself, before /setup, or its example person
    name = event.get("hook_event_name") or ""
    if name == "UserPromptSubmit":
        text = str(event.get("prompt") or "")
        cue = reaction(text)
        liked = "" if cue else approval(text)
        if liked:
            note_reaction(text, liked, again=True)
            return {"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"The person approved a message (\"{liked}\"). In this turn, keep each "
                    "message they approved as an example, whole: python3 tools/learned.py "
                    "approve --said \"<their words>\" --text-file <the message as approved> "
                    "--channel <connection|inmail|dm|...> --reader <peer|decision_maker|"
                    "recruiter>. learned.py brief messages shows it to every later draft. If "
                    "it approves nothing, python3 tools/learned.py skip --said \"...\" --why "
                    "\"...\".")}}
        if not cue:
            return {}
        note_reaction(text, cue, again=True)
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"The person reacted (\"{cue}\"). In this turn, before drafting again: apply "
                "it, make it stick in the setting it governs, record it in their own words "
                "with python3 tools/learned.py record (it shows the rule back and any earlier "
                "rule it contradicts), and say in one line what changes from now on. If it "
                "sets no rule, python3 tools/learned.py skip --said \"...\" --why \"...\".")}}
    if name != "Stop":
        return {}
    items = _this_turn(_transcript_texts(event.get("transcript_path") or ""))
    waiting = []
    for i, (_n, kind, text) in enumerate(items):
        if kind != "user" or not (reaction(text) or approval(text)):
            continue
        if not any(k == "tool" and _ANSWERED.search(t) for _m, k, t in items[i + 1:]):
            waiting.append(text)
    for text in waiting[-3:]:
        note_reaction(text)
    rows = _load_pending()
    waiting = [r for r in rows if not r.get("answered")]
    if not waiting:
        return {}
    first = waiting[0]
    held = int(first.get("held") or 0)
    if held >= HOLD_LIMIT:
        first["answered"] = dt.datetime.now().isoformat(timespec="seconds")
        first["let_go"] = True
        _save_pending(rows)
        return {"systemMessage": f"learned.py: a reaction was let go unrecorded after {held} "
                                 f"tries: \"{first['said'][:120]}\""}
    first["held"] = held + 1
    _save_pending(rows)
    return {"decision": "block", "reason": refuse_over_pending("Not finished")}


def _cli_hook() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        out = hook(event if isinstance(event, dict) else {})
    except Exception as e:  # noqa: BLE001  a hook must never break the chat it runs in
        print(f"learned.py hook: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if out:
        print(json.dumps(out))
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:
        return _cli_hook()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("area", nargs="?")
    b.add_argument("--channel", default=None, help="messages: the channel being drafted for")
    b.add_argument("--reader", default=None, help="messages: peer, decision_maker or recruiter")
    ap_ = sub.add_parser("approve", help="keep a message the person approved as an example")
    ap_.add_argument("--said", required=True, help="their words about it")
    ap_.add_argument("--text-file", required=True, help="the message as they approved it")
    ap_.add_argument("--channel", default="")
    ap_.add_argument("--reader", default="")
    ap_.add_argument("--contact", default="", help="who it went to, by contact id")
    sub.add_parser("approved", help="the messages kept as examples")
    li = sub.add_parser("list")
    li.add_argument("area", nargs="?")
    r = sub.add_parser("record")
    r.add_argument("--area", required=True)
    r.add_argument("--said", required=True)
    r.add_argument("--rule", required=True)
    r.add_argument("--applied-to", action="append", default=[])
    r.add_argument("--never-say", action="append", default=[],
                   help="a phrase never to use: in lower case, matched anywhere; capitalised "
                        "as a sentence opens (\"Love to hear\"), only where a sentence or "
                        "clause opens, so \"I'd love to hear\" stays allowed")
    r.add_argument("--overrides", action="append", default=[],
                   help="a check this rule outranks, by its name (compose.py prints it)")
    r.add_argument("--replaces", action="append", default=[], type=int,
                   help="an earlier entry this one replaces, by number, once they chose")
    r.add_argument("--length", action="append", default=[],
                   help="how long they asked a kind of message to run, in words: "
                        "<kind>[:<reader>]=<words>, e.g. inmail=170")
    k = sub.add_parser("skip")
    k.add_argument("--said", required=True)
    k.add_argument("--why", required=True)
    sub.add_parser("pending")
    t = sub.add_parser("retire")
    t.add_argument("n", type=int, nargs="+")
    sub.add_parser("locked")
    sub.add_parser("offers")
    d = sub.add_parser("decide")
    d.add_argument("n", type=int)
    d.add_argument("choice", choices=("keep", "switch"))
    sub.add_parser("adopt-profile-rules")
    o = sub.add_parser("offer")
    o.add_argument("--setting", required=True)
    o.add_argument("--new", required=True)
    o.add_argument("--why", required=True)
    o.add_argument("--version", required=True)
    a = ap.parse_args(argv)
    try:                        # a record is saved before it is shown: showing never fails
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if a.cmd == "brief":
        print(brief(a.area, a.channel, a.reader) or "(nothing learned yet: the defaults apply)")
    elif a.cmd == "approve":
        with open(a.text_file, encoding="utf-8") as fh:
            text = fh.read()
        e = approve(a.said, text, a.channel, a.reader, a.contact)
        print("learned: " + ("already kept as an example" if e.get("already") else
                             f"kept as an example of what you want ({e['channel'] or 'any channel'}, "
                             f"{(e['reader'] or 'any reader').replace('_', '-')})")
              + "; every later draft of its kind is shown it first (learned.py brief messages)")
    elif a.cmd == "approved":
        for i, x in enumerate(approved(), 1):
            print(f"{i:3}. {x.get('date')} {x.get('channel') or '-'} {x.get('reader') or '-'}: "
                  f"\"{' '.join(str(x.get('text') or '').split())[:100]}\" (said: \"{x.get('said')}\")")
    elif a.cmd == "list":
        over = superseded()
        for i, row in enumerate(load(), 1):
            if a.area and row.get("area") != a.area:
                continue
            later = over.get(_key(row))
            status = (f"overruled by {later.get('date')}" if later
                      else row.get("status", "active"))
            print(f"{i:3}. [{status}] {row.get('date')} {row.get('area')}: "
                  f"{row.get('rule')}  (said: \"{row.get('said')}\")")
    elif a.cmd == "record":
        e = record(a.area, a.said, a.rule, a.applied_to, a.never_say, overrides=a.overrides,
                   replaces=a.replaces, length=a.length)
        print(f"learned: {e['area']}: {e['rule']}")
        for kind, per in (e.get("length") or {}).items():
            print("  length: " + ", ".join(f"{kind} to {'any reader' if who == 'any' else who}"
                                           f" runs to about {n} words" for who, n in per.items()))
        print(f"Say to the person, in one line: From now on, {e['rule']} (you said: "
              f"\"{e['said'][:160]}\").")
        if e.get("overrides"):
            print(f"  outranks the check(s): {', '.join(e['overrides'])}")
        for phrase, setting, line in e.get("own_overlaps") or ():
            print(f"  WARNING: never saying \"{phrase}\" refuses your own {setting} "
                  f"(\"{' '.join(line.split())[:90]}\"), so every draft using it is refused. "
                  "Capitalised as a sentence opens (\"Love to hear\"), it bans only the "
                  "clipped sentence; or change that line.")
        for n, old, why in e["conflicts"]:
            where = f"entry {n}" if n else "a rule in profile/CLAUDE.md"
            print(f"  CONTRADICTS {where} ({old.get('date')}: {old.get('rule')}): {why}.")
        if e["conflicts"]:
            # Each command names the entry it retires and when that rule was made: "Theirs is
            # this one: retire 50" was read as "this one is 50", the earlier rule (2026-10-20).
            new = len(load())
            olds = [(n, o) for n, o, _w in e["conflicts"] if n]
            earlier = ", ".join(f"{n} ({o.get('date')})" for n, o in olds)
            print(f"Ask the person once which stands, with both dates. The new rule is entry "
                  f"{new} ({e.get('date')}).")
            print("  If the new rule stands: "
                  + (f"python3 tools/learned.py retire {' '.join(str(n) for n, _o in olds)} "
                     f"(retires the earlier entry {earlier})" if olds else
                     "change the line in profile/CLAUDE.md"))
            print(f"  If the earlier rule stands: python3 tools/learned.py retire {new} "
                  f"(retires the new entry {new})")
    elif a.cmd == "skip":
        skip(a.said, a.why)
        print(f"learned: not a rule ({a.why}); {len(pending())} reaction(s) still unrecorded")
    elif a.cmd == "pending":
        rows = pending()
        for r in rows:
            print(f"- {r.get('at')}: \"{r.get('said')}\"")
        print(f"{len(rows)} reaction(s) not recorded yet")
        return 1 if rows else 0
    elif a.cmd == "retire":
        for n in a.n:
            e = retire(n)
            print(f"retired: {e.get('rule')}")
    elif a.cmd == "locked":
        for item in locked():
            print(item)
    elif a.cmd == "offers":
        for n, o in offers():
            print(f"{n}. {question(o)}")
    elif a.cmd == "adopt-profile-rules":
        got = adopt_profile_rules()
        print("learned: checked from now on: " + ", ".join('"%s"' % p for p in got) if got
              else "learned: every never-write phrase in profile/CLAUDE.md is checked already")
    elif a.cmd == "offer":
        o = offer(a.setting, a.new, a.why, a.version)
        print(f"offered: {question(o)}")
    elif a.cmd == "decide":
        o = decide(a.n, a.choice)
        print(f"{o['setting']}: {o['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
