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
  tools/voice_check.py flag them in anything drafted, as `person_dislikes`.

    python3 tools/learned.py brief [area]        # the active rules, for a drafting step
    python3 tools/learned.py list [area]         # every entry, numbered
    python3 tools/learned.py record --area voice --said "..." --rule "..." \\
        [--applied-to "profile/networking.py OPENER"]... [--never-say "..."]... \\
        [--overrides <check>]... [--replaces <n>]...
    python3 tools/learned.py skip --said "..." --why "..."   # a reaction that sets no rule
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
AREAS = ("voice", "messages", "questions", "people", "jobs", "documents", "search",
         "interview", "other")


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
    data = {"entries": rows, "offers": offers_ if offers_ is not None else all_offers()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def entries(area: str | None = None) -> list[dict]:
    """The active entries, oldest first, for one area or all of them."""
    return [r for r in load() if r.get("status", "active") == "active"
            and (area is None or r.get("area") == area)]


def record(area: str, said: str, rule: str, applied_to=(), never_say=(),
           today: str | None = None, overrides=(), replaces=()) -> dict:
    """Keep one reaction, in the person's own words (`said`, kept as said). Returns the
    entry written, with `conflicts`: the earlier active rules it contradicts, for the
    person to choose between. `replaces` retires earlier entries by number, once they
    have chosen this one; `overrides` names the checks this rule outranks."""
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
    rows = load()
    for n in replaces:
        if not 1 <= int(n) <= len(rows):
            raise SystemExit(f"learned: no entry {n} to replace; there are {len(rows)}")
        rows[int(n) - 1]["status"] = "retired"
        rows[int(n) - 1]["retired_for"] = entry["date"]
    found = conflicts(entry, rows)
    rows.append(entry)
    _save(rows)
    resolve_pending(entry["said"])
    return {**entry, "conflicts": found}


# Words that change nothing about what a phrase says: "recently moved" and "just moved"
# make the same claim, and the person who banned one and later wrote the other in their
# own template needs to be asked which stands.
_HEDGES = {"recently", "just", "currently", "now", "really", "very", "so", "the", "a",
           "an", "my", "i", "i'm", "i've", "i'd", "to", "of", "and", "in", "on", "for",
           "with", "that", "this", "is", "am", "be", "been", "have", "has", "it", "your"}


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z']+", str(text or "").lower())
            if w not in _HEDGES and len(w) > 2}


def _says(text: str, phrase: str) -> bool:
    """Does `text` say what `phrase` says: the phrase itself, or every word of it that
    carries meaning?"""
    low = str(text or "").lower()
    if str(phrase).lower() in low:
        return True
    words = _content(phrase)
    return bool(words) and words <= _content(low)


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
            if _says(mine, str(p)) and not any(_says(str(p), b) for b in bans):
                why = f"it says never \"{p}\", and this one uses it"
                break
        if not why:
            for p in bans:
                if _says(theirs, p) and str(p).lower() not in {
                        str(x).lower() for x in r.get("never_say") or ()}:
                    why = f"it uses \"{p}\", which this one says never to"
                    break
        if not why:
            same = set(r.get("applied_to") or ()) & set(entry.get("applied_to") or ())
            if same and (r.get("rule") or "") != (entry.get("rule") or ""):
                why = f"both set {', '.join(sorted(same))}"
        if why:
            out.append((n, r, why))
    adopted = {str(p).lower() for r in rows for p in r.get("never_say") or ()}
    for phrase, rule in profile_never_phrases():
        if phrase.lower() in adopted:
            continue                                # listed above, as the entry it became
        if _says(mine, phrase) and not any(_says(phrase, b) for b in bans):
            out.append((0, {"date": "profile/CLAUDE.md", "rule": rule, "said": rule},
                        f"profile/CLAUDE.md says never \"{phrase}\", and this one uses it"))
    return out


def overrides() -> set[str]:
    """The checks a rule of the person's outranks, by name: a validator that fights their
    voice warns instead of refusing, once they have said which wins."""
    return {str(c) for r in entries() for c in r.get("overrides") or ()}


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


def never_say() -> list[tuple[str, re.Pattern]]:
    """(phrase, pattern) for every phrase the person has said never to use."""
    out = []
    for r in entries():
        for phrase in r.get("never_say") or ():
            words = [re.escape(w) for w in str(phrase).split()]
            if words:
                # Edges that work for a phrase that opens or closes on punctuation: \b
                # needs a word character there, so "(remote)" or "[sic]" never matched.
                out.append((phrase, re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)",
                                               re.I)))
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
               + " (a rule in profile/CLAUDE.md)", applied_to=["profile/CLAUDE.md"],
               never_say=phrases, today=today)
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


def brief(area: str | None = None) -> str:
    """The active rules as lines to follow before drafting, or "" when there are none.
    A rule a later one overrules (superseded) is left out."""
    over = superseded()
    rows = [r for r in entries(area) if _key(r) not in over]
    if area is not None:
        rows = rows + [r for r in entries("other") if r not in rows and _key(r) not in over]
    return "\n".join(f"- {r['rule']} ({r['date']}, they said: \"{r['said']}\")" for r in rows)


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
# saying it again, which is the failure this exists for.
REACTION = re.compile("|".join([
    r"\b(?:i\s+)?(?:don'?t|do not|didn'?t)\s+(?:like|love|want)\b", r"\bhate\b",
    r"\bnot (?:a )?fan\b",
    r"\b(?:too|so|very|really|way too)\s+(?:formal|long|short|wordy|stiff|robotic|generic|salesy"
    r"|pushy|cringe\w*|rude|polite|indirect|vague|much|many|samey|stilted|corporate)\b",
    r"\b(?:rude|cringe\w*|awkward|robotic|stilted|clunky|desperate|creepy|patroni[sz]ing"
    r"|useless|pointless|awful|terrible|weird)\b",
    r"\breads? like\b", r"\bsounds? like (?:a|an|someone|ai|a bot|chatgpt)\b",
    r"\b(?:ai|chatgpt|gpt)[- ]?(?:sounding|generated|written|ish|tells?)\b",
    r"\bthat'?s not (?:how|what|right|true|me)\b", r"\bnot how i\b",
    r"\bwhy (?:did|would|do) you\b",
    r"\bstop (?:suggesting|using|saying|adding|putting|sending|doing|asking)\b",
    r"\bnever (?:say|use|write|suggest|send|put|call)\b",
    r"\b(?:don'?t|do not) (?:say|use|write|suggest|send|put|add|mention|call|start|end|open)\b",
    r"\b(?:identical|all the same|same (?:structure|shape|opener|opening|closing|line|ending))\b",
    r"\b(?:i|i've|i have) (?:changed|edited|rewrote|reworded|tweaked)\b",
    r"\bhere'?s what i (?:sent|wrote)\b", r"\bwhat i actually sent\b",
    r"\bi (?:sent|wrote) (?:this|it) instead\b",
    r"\bi'?d (?:rather|prefer)\b", r"\bi prefer\b",
    r"\b(?:more|less) (?:casual|direct|formal|warm|friendly|personal|specific|forthright"
    r"|concise|human|natural|honest)\b",
]), re.I)


def reaction(text: str) -> str:
    """The words in `text` that make it a reaction, or "" when it is none."""
    t = str(text or "")
    if not t.strip() or t.lstrip().startswith(("<task-notification", "<system-reminder",
                                                 "<command-", "<local-command")):
        return ""
    m = REACTION.search(t)
    return m.group(0) if m else ""


def _reactions_path() -> str | None:
    """This chat's list: its own worktree's git directory, never shared with another
    chat's folder. Tests point LJS_STATE at a temporary folder."""
    st = os.environ.get("LJS_STATE")
    if st:
        return os.path.join(st, ".reactions.json")
    import subprocess
    try:
        r = subprocess.run(["git", "-C", os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True,
            timeout=10)
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


def pending() -> list[dict]:
    """Reactions this chat has noted and not yet recorded or skipped."""
    return _load_pending()


def note_reaction(text: str, cue: str = "") -> dict | None:
    """Put a reaction on this chat's list, once."""
    said = " ".join(str(text or "").split())[:400]
    if not said:
        return None
    rows = _load_pending()
    if any(r.get("said") == said for r in rows):
        return None
    row = {"said": said, "cue": cue or reaction(text),
           "at": dt.datetime.now().isoformat(timespec="seconds")}
    rows.append(row)
    _save_pending(rows)
    return row


def resolve_pending(said: str = "") -> None:
    """A record or a skip clears the reaction it answers: the one it quotes, else the
    oldest."""
    rows = _load_pending()
    if not rows:
        return
    words = _content(said)
    best = max(range(len(rows)), key=lambda i: len(words & _content(rows[i].get("said"))))
    if not words or not (words & _content(rows[best].get("said"))):
        best = 0
    del rows[best]
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


def _transcript_texts(path: str) -> list[tuple[int, str, str]]:
    """[(line number, kind, text)] from a Claude Code transcript: kind "user" for what the
    person typed, "tool" for each command the chat ran."""
    out = []
    try:
        fh = open(path, encoding="utf-8")
    except (OSError, TypeError):
        return out
    with fh:
        for n, line in enumerate(fh):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isMeta") or d.get("isSidechain"):
                continue
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
    """What came after the last turn the chat finished: the prompt that opened this one,
    the messages sent while it worked, and what it ran. A reaction days old in a chat that
    has carried on since is not this turn's to hold."""
    for i in range(len(items) - 1, -1, -1):
        if items[i][1] == "end":
            return items[i + 1:]
    return items


_ANSWERED = re.compile(r"learned\.py\s+(?:record|skip)\b")


def hook(event: dict) -> dict:
    """The Claude Code hook (the one the app ships, allowlisted in security_guards.py).

    UserPromptSubmit: a prompt that reads as a reaction goes on this chat's list, and the
    chat is told, in the turn, to record it. Stop: the turn is held while a reaction from
    the person has no `learned.py record` or `skip` after it, read from the transcript
    (which also holds messages sent while the chat was working) and from the list. Returns
    what the hook prints: {} to let things be."""
    if _path() is None:
        return {}                                   # the app itself, or before /setup
    name = event.get("hook_event_name") or ""
    if name == "UserPromptSubmit":
        text = str(event.get("prompt") or "")
        cue = reaction(text)
        if not cue:
            return {}
        note_reaction(text, cue)
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
        if kind != "user" or not reaction(text):
            continue
        if not any(k == "tool" and _ANSWERED.search(t) for _m, k, t in items[i + 1:]):
            waiting.append(text)
    for text in waiting[-3:]:
        note_reaction(text)
    rows = pending()
    if not rows:
        return {}
    first = rows[0]
    held = int(first.get("held") or 0)
    if held >= HOLD_LIMIT:
        rows.pop(0)
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
    li = sub.add_parser("list")
    li.add_argument("area", nargs="?")
    r = sub.add_parser("record")
    r.add_argument("--area", required=True)
    r.add_argument("--said", required=True)
    r.add_argument("--rule", required=True)
    r.add_argument("--applied-to", action="append", default=[])
    r.add_argument("--never-say", action="append", default=[])
    r.add_argument("--overrides", action="append", default=[],
                   help="a check this rule outranks, by its name (compose.py prints it)")
    r.add_argument("--replaces", action="append", default=[], type=int,
                   help="an earlier entry this one replaces, by number, once they chose")
    k = sub.add_parser("skip")
    k.add_argument("--said", required=True)
    k.add_argument("--why", required=True)
    sub.add_parser("pending")
    t = sub.add_parser("retire")
    t.add_argument("n", type=int)
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
    if a.cmd == "brief":
        print(brief(a.area) or "(nothing learned yet: the defaults apply)")
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
                   replaces=a.replaces)
        print(f"learned: {e['area']}: {e['rule']}")
        print(f"Say to the person, in one line: From now on, {e['rule']} (you said: "
              f"\"{e['said'][:160]}\").")
        if e.get("overrides"):
            print(f"  outranks the check(s): {', '.join(e['overrides'])}")
        for n, old, why in e["conflicts"]:
            where = f"entry {n}" if n else "a rule in profile/CLAUDE.md"
            print(f"  CONTRADICTS {where} ({old.get('date')}: {old.get('rule')}): {why}.")
        if e["conflicts"]:
            nums = [str(n) for n, _o, _w in e["conflicts"] if n]
            print("Ask the person once which stands, with both dates. Theirs is this one: "
                  + (f"python3 tools/learned.py retire {' '.join(nums)}" if nums else
                     "change the line in profile/CLAUDE.md")
                  + f"; the earlier one: python3 tools/learned.py retire {len(load())}.")
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
        e = retire(a.n)
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
