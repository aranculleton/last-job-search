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
    python3 tools/learned.py restore <n>         # a rule retired for a later one, back
    python3 tools/learned.py tidy [--dry]        # retire every rule a later one repeats or contradicts
    python3 tools/learned.py locked              # the settings no upgrade may change
    python3 tools/learned.py offers              # app improvements waiting on their choice
    python3 tools/learned.py decide <n> keep|switch
    python3 tools/learned.py built-in            # after an update: rules the app now does itself
    python3 tools/learned.py built-in --retire <n>=<id>... --done   # "Now part of the app", once
    python3 tools/learned.py record --about-app --said "..."  # a complaint about the app: never a rule
    python3 tools/learned.py app-bugs [--all] [--close <n>]   # the maintainer's own copy only

**A reaction is recorded, not remembered.** Writing "record each reaction" in CLAUDE.md
did not make it happen: one chat redrafted nine times on the person's corrections ("rude",
"identical in structure", "too long", "that's not how I found him") and recorded none of
them until asked. So it is code now. `hook` is the one hook the app ships: on each
prompt it notes a reaction in this chat's pending list (`pending`), and the turn cannot
end while one is there; `compose.py` and `reading.py draft` refuse to draft over one. A
`record` (or a `skip`, saying why it sets no rule) clears it. A record shows the rule
back in one line and retires, by itself, every earlier rule it says again or contradicts:
the newest thing they said stands, nothing is asked, what the old rule carried comes along,
and `restore` brings one back (`tidy` does the same for a pile made before). It may name
the checks the rule outranks (`--overrides`): the
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
# Other words for an area, read the same way by `record` and `brief`: "networking" (the word
# the tips and the skills use for messages to people) was refused by record while brief took
# it and listed only the "other" rules (2026-11-05).
AREA_ALIASES = {
    "networking": "messages", "network": "messages", "outreach": "messages",
    "message": "messages", "notes": "messages", "replies": "messages", "reply": "messages",
    "tone": "voice", "writing": "voice", "style": "voice",
    "document": "documents", "resume": "documents", "resumes": "documents",
    "cv": "documents", "letter": "documents", "letters": "documents",
    "question": "questions", "person": "people", "contacts": "people",
    "target": "targets", "employers": "targets", "companies": "targets",
    "job": "jobs", "roles": "jobs", "interviews": "interview",
    # The page's own groups of rules, by the name of the thing each is about (the Tweak
    # panels in templates/app/app.js, TWEAK): every one is accepted, so a rule kept from
    # the page is never refused for its group's name (`--area brief` was, 2026-11-05).
    # The brief has no area of its own; its rules are "other", which its panel reads.
    "brief": "other", "briefs": "other", "prep": "interview", "preps": "interview",
}
# The page's rule groups (its Tweak panels), read by tests/test_the_reaction_check_reads_only_the_person.py
# against the page itself, so a group the page adds is accepted here or that test fails.
PAGE_GROUPS = ("resume", "letter", "message", "jobs", "prep", "brief")


def area_of(word) -> str:
    """The area a word names, an alias read as its area (AREA_ALIASES), or SystemExit with
    the areas there are. One answer for `record` and `brief`."""
    w = re.sub(r"[\s-]+", "_", str(word or "").strip().lower())
    w = AREA_ALIASES.get(w, w)
    if w not in AREAS:
        raise SystemExit(f"learned: area {word!r}; one of {', '.join(AREAS)}")
    return w


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


def file_data() -> dict:
    path = _path()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {"entries": data}


_data = file_data  # the module's own name for it; other modules call file_data


def _writable() -> str:
    """Where a record goes, or SystemExit: never before /setup, and never into the app's
    example person, which the app's own tests read and a tool run there would change."""
    path = _path()
    if not path:
        raise SystemExit("learned: no profile; nothing can be recorded before /setup")
    if person.in_example(path):
        raise SystemExit("learned: profile.example is the app's example person; nothing is "
                         "recorded there")
    return path


def _first_write(data: dict, path: str) -> dict:
    """A rules file made for the first time starts with every behaviour the app already does
    by itself counted as checked (`built_in_done`): a person who sets up today never has a
    rule they give later put away for something the app did before they gave it."""
    if not os.path.exists(path) and "built_in" not in data:
        data["built_in"] = {"checked": [b["id"] for b in BUILT_IN],
                            "on": person.today().isoformat()}
    return data


def save_entries(rows: list[dict], offers_: list[dict] | None = None) -> None:
    path = _writable()
    data = _first_write(_data(), path)   # what else the file keeps (the skips) stays
    data.update({"entries": rows, "offers": offers_ if offers_ is not None else all_offers()})
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


_save = save_entries  # the module's own name for it; other modules call save_entries


# ------------------------------------------------------------------ a rule is its setting

# Rules whose setting the app knows, whatever words they come in: `record` writes the setting
# in the same command and names it in `applied_to`, so a rule is never kept without it. The
# person's "update only when I say" (2026-10-25) was recorded against an app file and never
# written into person.json, and ten updates came in by themselves (engine audit, 2026-11-03).
_ABOUT_UPDATES = re.compile(r"\b(?:the app|app'?s|sync\w*|updates|new versions?)\b", re.I)
_UPDATES_WAIT = re.compile(
    r"\b(?:only|never|don'?t|do not|no|stop|not)\b[^.;]{0,60}\bupdat|"
    r"\bupdat\w*\b[^.;]{0,60}\b(?:only|unless|until|when|wait)\b[^.;]{0,30}"
    r"\b(?:i|he|she|they|you|asked|told|say|says|said)\b|"
    # "App updates: I'll say when", "I decide on app updates" (the review of SV-1).
    r"\bupdat\w*\b[^.;]{0,30}\b(?:i|he|she|they)(?:'ll| will| shall)?\s+(?:say|decide|tell)\b|"
    r"\b(?:i|he|she|they)(?:'ll| will| shall)?\s+(?:say|decide|choose)\b[^.;]{0,30}\bupdat",
    re.I)
_UPDATES_AUTO = re.compile(r"\bupdat\w*\b[^.;]{0,40}\b(?:by (?:them|it)sel(?:f|ves)|"
                           r"automatically|on (?:its|their) own|without (?:asking|being asked))\b",
                           re.I)
# "never ask him again", "don't ask me", "stop asking": the person is not to be asked, so the
# updates come by themselves. Read as "never ... update" it wrote the opposite: "App updates
# come by themselves; never ask him again" became "when_asked" in a person's copy (audit SV-1,
# 2026-11-10). Only the words that stand for the person between the "not" and the "ask", so
# "don't update without asking me" still waits.
_ASK_OFF = re.compile(r"\b(?:never|don'?t|do not|no need to|no more|stop|quit)\s+"
                      r"(?:(?:ever|even|again|me|him|her|them|you|bother)\s+){0,2}"
                      r"ask(?:ing|s)?\b", re.I)
# A reply's own "no" in front of what it says ("No, updates come by themselves").
_REPLY_NO = re.compile(r"^\s*(?:no|nope|nah)\s*[,!:-]\s*", re.I)
# One sentence at a time: a full stop inside a file's name (sync_app.py) is not an end.
_SENTENCE = re.compile(r"[.;!?\n]+(?=\s|$)")


def updates_said(text: str) -> str:
    """"auto", "when_asked" or "" (they say neither, or both): what these words say about how
    the app's updates arrive. Each sentence is read on its own, and a "not" that belongs to
    asking ("never ask him again") is about asking, never about updating."""
    if not (_ABOUT_UPDATES.search(text or "") and re.search(r"\bupdat", text or "", re.I)):
        return ""
    found: set[str] = set()
    asked_off = False
    for part in _SENTENCE.split(text):
        part = _REPLY_NO.sub("", part)
        rest = _ASK_OFF.sub(" ", part)
        # Only a sentence about updates: "Don't ask me again about LinkedIn. App updates: I'll
        # say when." was read as updates by themselves (the review of SV-1, 2026-11-11).
        asked_off = asked_off or (rest != part and re.search(r"\bupdat", part, re.I) is not None)
        if _UPDATES_WAIT.search(rest):
            found.add("when_asked")
        elif _UPDATES_AUTO.search(rest):
            found.add("auto")
    if not found and asked_off:
        found.add("auto")              # "updates should just happen, don't ask me"
    return found.pop() if len(found) == 1 else ""
# "only jobs from the last 10 days", "nothing older than a week" -> JOB_AGE_DAYS.
_WINDOW = re.compile(r"\b(?:last|past|within|under|less than|no older than|not older than|"
                     r"younger than|newer than|up to|at most)\s+(?:(\d{1,3})\s+days?|a\s+(week)|"
                     r"(two|2)\s+weeks)\b", re.I)
_JOBS_WORDS = re.compile(r"\b(?:jobs?|postings?|roles?|listings?|openings?|vacanc\w+|search)\b",
                         re.I)
# "only follow up when there's something new", "no nudges without a reason" -> PLAIN_NUDGE
# False; "follow up even with nothing new" -> True. A follow-up with nothing new to say is a
# short plain one unless the person said otherwise (followup_drafts.plain_nudge_allowed).
_NUDGE_WORDS = re.compile(r"\b(?:nudg\w*|follow[- ]?ups?|follow(?:ing)? (?:them |people )?up|"
                          r"chas(?:e|es|ing))\b", re.I)
# Having something new to say, never news as a subject ("never mention news about me").
_NEWS_WORDS = re.compile(r"\b(?:nothing (?:new|to say)|something new|anything new|new reason|"
                         r"(?:a|no|any) reason|without (?:a |any )?(?:reason|news)|"
                         r"(?:no|any|unless there(?:'?s| is)|if there(?:'?s| is)|when there(?:'?s| is)|"
                         r"only with) (?:some )?news)\b", re.I)
_PLAIN_ON = re.compile(r"\b(?:even|anyway|still|regardless|always)\b", re.I)
_PLAIN_OFF = re.compile(r"\b(?:only|unless|never|don'?t|do not|stop|no|not|without)\b", re.I)
# A rule about what a follow-up says, never whether one goes: "never repeat what the earlier
# message already said; refer back to it and add something new" is about not saying the same
# thing twice, and read as "only follow up with something new" it turned every plain follow-up
# into a question for the person (2026-11-06). It sets the switch only where it also says
# when one goes (only, unless, without).
_REPEAT_WORDS = re.compile(r"\b(?:repeat\w*|restat\w*|already said|said before|same (?:thing|words|point))\b",
                           re.I)
_SEND_GATE = re.compile(r"\b(?:only|unless|without)\b", re.I)


def known_settings(area: str, said: str, rule: str) -> list[tuple[str, object]]:
    """[(setting, value)] a rule says in any words, as `applied_to` names them: "profile/
    person.json app_updates" (when_asked or auto), "profile/search.py JOB_AGE_DAYS" and
    "profile/networking.py PLAIN_NUDGE" (whether a follow-up with nothing new to say is still
    drafted as a short plain one)."""
    text = f"{said} {rule}"
    out: list[tuple[str, object]] = []
    if area in ("messages", "voice", "people", "other") and _NUDGE_WORDS.search(text) \
            and _NEWS_WORDS.search(text) \
            and not (_REPEAT_WORDS.search(text) and not _SEND_GATE.search(text)):
        # "still nudge with no news" is a yes. Read wrongly, a yes only drafts (nothing is
        # ever sent), while a wrong no leaves the follow-ups unwritten: a yes is read first.
        if _PLAIN_ON.search(text):
            out.append(("profile/networking.py PLAIN_NUDGE", True))
        elif _PLAIN_OFF.search(text):
            out.append(("profile/networking.py PLAIN_NUDGE", False))
    # The person's own words decide where they say either; the rule restated from them only
    # where they do not. Never the two read as one run: the end of one and the start of the
    # other made a sentence neither said.
    chosen = updates_said(said) or updates_said(rule)
    if chosen:
        out.append(("profile/person.json app_updates", chosen))
    if area in ("search", "jobs", "targets", "other") and _JOBS_WORDS.search(text):
        m = _WINDOW.search(text)
        if m:
            days = int(m.group(1)) if m.group(1) else 7 if m.group(2) else 14
            # The window the search takes (run_round.job_age_ok): what is written here is
            # what is searched, never a number the search reads as 14.
            import run_round
            if run_round.job_age_ok(days):
                out.append(("profile/search.py JOB_AGE_DAYS", days))
    return out


def apply_setting(setting: str, value) -> None:
    """One known setting written, the way the page's own Settings write it, then read back
    from the file: what is on disk is what the tools follow, so a value that does not read
    back as the one meant stops here, said, never recorded as done (audit SV-1)."""
    where, _, key = setting.partition(" ")
    if where.endswith("person.json"):
        was = person.put([key], value)
        try:
            with open(person.path("person.json"), encoding="utf-8") as fh:
                got = json.load(fh).get(key)
        except (OSError, ValueError, AttributeError):
            got = None
        if got != value:
            # What was there before goes back: left as read, the wrong value stood on disk
            # while the command said nothing was recorded (the review of SV-1, 2026-11-11).
            person.put([key], person.REMOVE if was is person.MISSING else was)
        person.reset()
    else:
        import profile_set
        name = os.path.basename(where)
        before = getattr(person.module(name[:-3]), key, person.MISSING)
        profile_set.set_line(name, key, value)
        person.reset()
        got = getattr(person.module(name[:-3]), key, None)
        if got != value and before is not person.MISSING:
            profile_set.set_line(name, key, before)
            person.reset()
    if got != value:
        raise SystemExit(f"learned: {setting} was to be {json.dumps(value)} but reads back as "
                         f"{json.dumps(got)}: it was put back as it was, and nothing was "
                         "recorded. Write it again with the page's Settings or this command, "
                         "and check it.")


def _app_file(applied: str) -> str:
    """The app's own file an `applied_to` names, or "": the next update puts an app file back,
    so a rule kept there is a rule nobody follows."""
    token = str(applied or "").strip().split(" ", 1)[0].strip("`'\"")
    if not re.search(r"\.(?:py|json|md|csv|txt|tex|sh|js|ya?ml)$", token):
        return ""
    import personal_paths
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "/" in token:
        rel = token.lstrip("./")
        return rel if not personal_paths.is_personal(rel) and \
            os.path.exists(os.path.join(root, rel)) else ""
    try:
        if os.path.exists(person.path(token)):
            return ""                                    # one of their profile's files
    except person.NoProfile:
        pass
    for rel in (os.path.join("tools", token), token):
        if os.path.exists(os.path.join(root, rel)) and not personal_paths.is_personal(rel):
            return rel.replace(os.sep, "/")
    return ""


def entries(area: str | None = None) -> list[dict]:
    """The active entries, oldest first, for one area or all of them."""
    return [r for r in load() if r.get("status", "active") == "active"
            and (area is None or r.get("area") == area)]


def record(area: str, said: str, rule: str, applied_to=(), never_say=(),
           today: str | None = None, overrides=(), replaces=(), answers: bool = True,
           length=(), via: str = "", output: str = "") -> dict:
    """Keep one reaction, in the person's own words (`said`, kept as said). Returns the
    entry written, with `conflicts`: the earlier active rules it contradicts, for the
    person to choose between. `replaces` retires earlier entries by number, once they
    have chosen this one; `overrides` names the checks this rule outranks. `answers` is
    False for a record nobody reacted with (a profile rule adopted by an upgrade), which
    clears no reaction waiting in the chat. `length` is how long they asked a kind of
    message to run, as "<kind>[:<reader>]=<words>" ("inmail=170", "inmail:peer=160"): the
    length checks read it (`length()`), never the words of the rule."""
    area = area_of(area)
    if not str(said or "").strip() or not str(rule or "").strip():
        raise SystemExit("learned: record needs what they said and the rule it gives")
    applied_to = [str(a) for a in applied_to if str(a).strip()]
    for a in applied_to:
        app = _app_file(a)
        if app:
            raise SystemExit(f"learned: {app} is the app's own file, and the next update puts it "
                             "back, so a rule kept there is never followed. Make it stick in "
                             "their profile (the setting it governs there), and name that.")
    # A rule the app knows the setting of is that setting, written now (never only noted).
    written = known_settings(area, said, rule)
    for setting, value in written:
        apply_setting(setting, value)
        if setting not in applied_to:
            applied_to.append(setting)
    entry = {"date": today or person.today().isoformat(), "area": area,
             "said": str(said).strip(), "rule": " ".join(str(rule).split()),
             "applied_to": applied_to,
             "never_say": [str(p) for p in never_say if str(p).strip()],
             "status": "active"}
    over = [str(c).strip() for c in overrides if str(c).strip()]
    if over:
        entry["overrides"] = over
    lengths = parse_lengths(length)
    if lengths:
        entry["length"] = lengths
    # Where it was said ("page tweak": typed into the page's Tweak box) and about which
    # kind of output: tools/tweak.py promote reads them to offer a button.
    if str(via or "").strip():
        entry["via"] = str(via).strip()
    if str(output or "").strip():
        entry["output"] = str(output).strip()
    rows = load()
    for n in replaces:
        if not 1 <= int(n) <= len(rows):
            raise SystemExit(f"learned: no entry {n} to replace; there are {len(rows)}")
        rows[int(n) - 1]["status"] = "retired"
        rows[int(n) - 1]["retired_for"] = entry["date"]
    found = conflicts(entry, rows)
    # An earlier rule it says again is retired here, and what that rule carried (its bans,
    # the settings it shaped) comes along. One it may contradict is for the chat recording it
    # to judge, never the person to be asked: words alone mistook "Adobe is out" for undoing
    # "KPMG is out" (a dry run on a real list of 195 rules, 2026-10-31). Asking "which
    # stands?" every time piled up repeats and opposites (the maintainer, 2026-10-31: "if it
    # can be done in the background and it's not expensive, it's autonomous").
    replaced = _absorb(entry, rows, [(n, "it says the same") for n in repeats(entry, rows)])
    rows.append(entry)
    _save(rows)
    if answers:
        resolve_pending(entry["said"])
    return {**entry, "conflicts": found, "replaced": replaced,
            "own_overlaps": own_overlaps(entry["never_say"]), "set": written}


def repeats(entry: dict, rows: list[dict]) -> list[int]:
    """Numbers of the active entries in the same area that `entry` says again: the same
    words that carry meaning, or every one of theirs (three or more) inside its own. One the
    new rule only narrows (it says less) is a different rule and stays."""
    mine = _content(entry.get("rule") or "")
    neg = bool(_NEGATES.search(entry.get("rule") or ""))
    out = []
    for n, r in enumerate(rows, 1):
        if r is entry or r.get("status", "active") != "active" or r.get("area") != entry.get("area"):
            continue
        theirs = _content(r.get("rule") or "")
        if not theirs or not mine:
            continue
        # Careful (the maintainer, 2026-10-31: "be careful with the rules"): one that says
        # never where the other does not may be its opposite, so it is left for a chat to
        # judge; a newer rule that adds more than a few words is a different rule.
        if bool(_NEGATES.search(r.get("rule") or "")) != neg:
            continue
        if theirs == mine or (len(theirs) >= 4 and theirs <= mine and len(mine - theirs) <= 3) or \
                len(theirs & mine) / len(theirs | mine) >= 0.8:
            out.append(n)
    return out


_NEGATES = re.compile(r"\b(?:never|no|not|don'?t|do not|stop|avoid|without|cut|drop)\b", re.I)


def _absorb(entry: dict, rows: list[dict], gone: list[tuple[int, str]]) -> list[tuple[int, dict, str]]:
    """Retire each entry numbered in `gone` for `entry`, carrying over what it held that the
    new one does not contradict: its bans (unless the new one uses them), the settings it
    shaped, the checks it outranked, its lengths (the new one's win)."""
    out, seen = [], set()
    text = " ".join([entry.get("rule") or "", entry.get("said") or ""])
    for n, why in gone:
        if n in seen or not 1 <= n <= len(rows):
            continue
        seen.add(n)
        old = rows[n - 1]
        if old.get("status", "active") != "active":
            continue
        for key in ("never_say", "applied_to", "overrides"):
            have = list(entry.get(key) or [])
            for x in old.get(key) or ():
                if x not in have and not (key == "never_say" and _uses(text, str(x))):
                    have.append(x)
            if have:
                entry[key] = have
        for kind, per in (old.get("length") or {}).items():
            entry.setdefault("length", {}).setdefault(kind, {})
            for who, words in per.items():
                entry["length"][kind].setdefault(who, words)
        old["status"] = "retired"
        old["retired_for"] = entry.get("date")
        old["retired_why"] = why
        out.append((n, old, why))
    return out


def tidy(dry: bool = False) -> list[dict]:
    """Every active entry a later one says again, retired for it, oldest first, as `record`
    does for a new one: a pile made before that is kept to one rule each. [{n, rule, for,
    why}]; nothing is written with `dry`."""
    rows = load()
    done = []
    for i, later in enumerate(rows):
        if later.get("status", "active") != "active":
            continue
        earlier = [(n, "it says the same") for n in repeats(later, rows) if n <= i]
        for n, old, why in _absorb(later, rows, earlier):
            done.append({"n": n, "rule": old.get("rule"), "for": i + 1, "why": why})
    if done and not dry:
        _save(rows)
    return done


def clashes() -> list[dict]:
    """Each active entry that a later active one may contradict, for a chat to judge once:
    [{n, rule, date, later, later_rule, why}]. Words only find candidates."""
    rows = load()
    out = []
    for i, later in enumerate(rows):
        if later.get("status", "active") != "active":
            continue
        for n, old, why in conflicts(later, rows):
            if 0 < n <= i:
                out.append({"n": n, "rule": old.get("rule"), "date": old.get("date"),
                            "later": i + 1, "later_rule": later.get("rule"), "why": why})
    return out


# One question at most, and seldom: everything else about the rules is decided by itself (the
# maintainer, 2026-10-31: one question at most, and sparsely; the vast majority automated).
# A pair is asked about only where a chat cannot tell which stands and it
# matters to what is drafted; never a second while one is open, nor within ASK_GAP_DAYS of
# the last.
ASK_GAP_DAYS = 14


def ask(older: int, later: int, today: str | None = None) -> str:
    """Put the one question on the page: entries `older` and `later` may disagree, which
    stands? "" when it is asked, else why not (one is open, one was asked lately, or the
    pair is not two active rules)."""
    data = file_data()
    rows = data.get("entries") or []
    day = today or person.today().isoformat()
    cur = data.get("ask") or {}
    if cur and not cur.get("answer"):
        return "one question about the rules is already waiting"
    last = str(cur.get("asked") or "")
    if last and (dt.date.fromisoformat(day) - dt.date.fromisoformat(last)).days < ASK_GAP_DAYS:
        return f"one was asked on {last}; decide this one, keeping both where unsure"
    if not (1 <= older < later <= len(rows)) or any(
            rows[n - 1].get("status", "active") != "active" for n in (older, later)):
        return "those are not two rules in force, older first"
    data["ask"] = {"older": older, "later": later, "asked": day, "answer": None}
    _write_data(data)
    return ""


def asked() -> dict | None:
    """The one question waiting, with both rules, or None."""
    data = file_data()
    cur = data.get("ask") or {}
    rows = data.get("entries") or []
    if not cur or cur.get("answer"):
        return None
    o, l = int(cur.get("older") or 0), int(cur.get("later") or 0)
    if not (1 <= o < l <= len(rows)):
        return None
    return dict(cur, older_rule=rows[o - 1], later_rule=rows[l - 1])


def settle(answer: str, today: str | None = None) -> str:
    """Their answer to the one question: "later" puts the older rule away, "older" the later,
    "both" keeps both. Returns what was done, in a line."""
    if answer not in ("later", "older", "both"):
        raise SystemExit("learned: the answer is later, older or both")
    cur = asked()
    if not cur:
        return "No question about your rules is waiting."
    rows = load()
    gone = {"later": cur["older"], "older": cur["later"]}.get(answer)
    if gone:
        rows[gone - 1]["status"] = "retired"
        rows[gone - 1]["retired_for"] = today or person.today().isoformat()
        rows[gone - 1]["retired_why"] = "you chose the other"
        _save(rows)
    data = file_data()
    data["ask"] = dict(data.get("ask") or {}, answer=answer)
    _write_data(data)
    return {"later": "The newer rule stands.", "older": "The older rule stands.",
            "both": "Both rules stand."}[answer]


def _write_data(data: dict) -> None:
    path = _writable()
    _first_write(data, path)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def reviewed(mark: bool = False, today: str | None = None) -> str:
    """The day the person's rules were last judged for contradictions; `mark` sets today."""
    data = file_data()
    if mark:
        data["reviewed_on"] = today or person.today().isoformat()
        _write_data(data)
    return str(data.get("reviewed_on") or "")


def restore(n: int) -> dict:
    """An entry retired for a later one, back in force: the later one is left as it is."""
    rows = load()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no entry {n}; there are {len(rows)}")
    r = rows[n - 1]
    r["status"] = "active"
    for k in ("retired_for", "retired_why"):
        r.pop(k, None)
    _save(rows)
    return r


# Words that change nothing about what a phrase says: "recently moved" and "just moved"
# make the same claim, and the person who banned one and later wrote the other in their
# own template needs to be asked which stands.
_HEDGES = {"recently", "just", "currently", "now", "really", "very", "so", "the", "a",
           "an", "my", "i", "i'm", "i've", "i'd", "to", "of", "and", "in", "on", "for",
           "with", "that", "this", "is", "am", "be", "been", "have", "has", "it", "your"}


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z']+", str(text or "").lower())
            if w not in _HEDGES and len(w) > 2}


_content = content_words  # the module's own name for it; other modules call content_words


# A phrase a rule names only to forbid it ("never describe the move as relocating") is not
# a use of it: such a rule agrees with every other ban of the phrase.
_FORBIDS = re.compile(r"\b(?:never|stop|don'?t|do not|no more|no|avoid|without|not|instead of"
                      r"|rather than|cut|drop|lose|remove|ban)\b", re.I)


def _uses(text: str, phrase: str) -> bool:
    """Does `text` use `phrase`, rather than name it only to forbid it?"""
    if not _says(text, phrase):
        return False
    low, p = str(text or "").lower(), str(phrase).lower()
    at = [m.start() for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(p), low)]
    if not at:                                   # said in other words: where they start
        words = sorted(_content(p))
        at = [m.start() for w in words[:1]
              for m in re.finditer(r"\b%s\b" % re.escape(w), low)]
    for i in at:
        clause = re.split(r"[.;:!?\n]", low[:i])[-1]
        if not _FORBIDS.search(" ".join(clause.split()[-8:])):
            return True
    return False


def _uses_itself(text: str, phrase: str) -> bool:
    """`_uses`, with the phrase said as itself: never only its words scattered."""
    low = str(text or "").lower()
    return bool(re.search(r"(?<!\w)%s(?!\w)" % re.escape(str(phrase).lower()), low)) and \
        _uses(text, phrase)


def _where(text: str, phrase: str, around: int = 30) -> str:
    """The words of `text` the check matched `phrase` against, a few either side: what a
    clash compares, said with it."""
    low = str(text or "").lower()
    m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(str(phrase).lower()), low)
    if m is None:
        words = sorted(_content(phrase))
        m = next((x for w in words for x in [re.search(r"\b%s\b" % re.escape(w), low)] if x),
                 None)
    if m is None:
        return " ".join(str(text or "").split())[:2 * around]
    a, b = max(0, m.start() - around), min(len(text), m.end() + around)
    return ("..." if a else "") + " ".join(str(text)[a:b].split()) + ("..." if b < len(text) else "")


def _says(text: str, phrase: str) -> bool:
    """Does `text` say what `phrase` says: the phrase itself, or every word of it that
    carries meaning?"""
    low = str(text or "").lower()
    if re.search(r"(?<!\w)%s(?!\w)" % re.escape(str(phrase).lower()), low):
        return True
    words = _content(phrase)
    return bool(words) and words <= _content(low)


# The areas whose rules are about the words written (a message, a document, the voice of
# both, an answer to a question): a ban in one is about what every other writes too.
WRITTEN = {"voice", "messages", "documents", "questions", "interview"}
# Settings that are lists a rule adds to, never one value two rules can set differently.
_LISTS = re.compile(r"(?:DECLINED|EXCLUDED|EXCLUDE|BLOCKED|NEVER|AVOID|SKIP|TARGETS|WATCH|"
                    r"FOLLOW|NAMES|PHRASES|LIST)\b")
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
        # Rules about different things (a rule about how quickly taps are done, and one about
        # a follow-up's words) share a word by chance: "update" in the one was read as using
        # the other's "never ask for an update" (2026-11-05). A phrase is matched in other
        # words only between two rules about what is written (WRITTEN); else only as itself.
        same = {str(r.get("area") or ""), str(entry.get("area") or "")}
        uses = _uses if len(same) == 1 or same <= WRITTEN else _uses_itself
        why = ""
        for p in r.get("never_say") or ():
            if uses(mine, str(p)) and not any(_says(str(p), b) for b in bans):
                why = (f"it says never \"{p}\", and this one uses it "
                       f"(\"{_where(mine, str(p))}\")")
                break
        if not why:
            for p in bans:
                if uses(theirs, p) and str(p).lower() not in {
                        str(x).lower() for x in r.get("never_say") or ()}:
                    why = (f"it uses \"{p}\" (\"{_where(theirs, p)}\"), which this one says "
                           "never to")
                    break
        if not why:
            # Two rules that set one setting ("networking.py OPENER") differently ask which
            # stands. Two that only apply to the same file or section ("07-interview-prep.md")
            # are two rules, and were flagged as a contradiction (2026-10-20).
            # A list ("BAR_DECLINED": employers that are out) grows: "Adobe is out" never
            # undoes "KPMG is out" (2026-10-31).
            same = {a for a in set(r.get("applied_to") or ()) & set(entry.get("applied_to") or ())
                    if _SETTING.search(_FILE_NAME.sub(" ", str(a))) and not _LISTS.search(str(a))}
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


# How alike the words sent and the draft must be (difflib's ratio over their words, 0 to 1)
# for the difference to be the person's edit. Below it, what went is another message, not
# the draft changed: a message written apart from an out-of-date draft was read as an edit
# of it, and a rule was recorded from the difference (2026-11-05). A sentence rewritten in a
# two-sentence note keeps about 0.6; a different message to the same person, under 0.2.
EDIT_ALIKE = 0.5


def alike(draft: str, sent: str) -> float:
    """How much of the draft's words, in order, the sent words keep: difflib's ratio."""
    import difflib
    a = [w.lower() for w in str(draft or "").split()]
    b = [w.lower() for w in str(sent or "").split()]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def record_edit(draft: str, sent: str, where: str = "", today: str | None = None) -> dict | None:
    """The person changed a draft before sending it: that edit is a reaction, recorded by
    itself, with both texts. None when nothing changed beyond spacing, and None when what
    went is plainly not the draft (`alike` under EDIT_ALIKE): another message, not an edit."""
    if " ".join(str(draft or "").split()) == " ".join(str(sent or "").split()):
        return None
    if alike(draft, sent) < EDIT_ALIKE:
        return None
    parts = []
    for old, new in _changes(draft, sent):
        if old and new:
            parts.append(f'"{old}" became "{new}"')
        elif old:
            parts.append(f'cut "{old}"')
        else:
            parts.append(f'added "{new}"')
    entry = {"date": today or person.today().isoformat(), "area": "messages", "kind": "edit",
             "said": "edited the draft before sending" + (f" ({where})" if where else ""),
             "rule": "write it the way they edited it: " + "; ".join(parts),
             "applied_to": [], "never_say": [], "status": "active",
             "draft": str(draft).strip(), "sent": str(sent).strip()}
    rows = load()
    rows.append(entry)
    _save(rows)
    return entry


def retire(n: int, why: str = "") -> dict:
    """The person changed their mind: entry n stops applying, and stays as history. `why`
    is kept with it (NOW_PART for a rule the app now does by itself)."""
    rows = load()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no entry {n}; there are {len(rows)}")
    rows[n - 1]["status"] = "retired"
    if str(why or "").strip():
        rows[n - 1]["retired_why"] = " ".join(str(why).split())
    _save(rows)
    return rows[n - 1]


# ------------------------------------------------------------------ what the app now does itself
#
# A person teaches the app something ("name my resume file after me and the employer"), and
# a later version does it for everyone. Their rule then only repeats the app, adds to a list
# they have to read, and nothing ever retired it (the maintainer, 2026-11-06: rules the app
# has since built in are retired after each update, "Now part of the app", once). So the app
# keeps a registry of the behaviours it now does by itself; after an update the copy's
# Claude lists the active rules that may only say one of them again (`built_in_candidates`),
# judges each, retires the ones truly covered with NOW_PART (`retire_built_in`), and records
# the registry as checked (`built_in_done`), so nothing is proposed twice. The profile
# upgrade `built-in-rules` (tools/profile_upgrades.py) is pending while there is one to judge.
#
# Each behaviour: `id`, the `version` it arrived in and its day (`since`), `does` (one plain
# sentence of what the app does now), `areas` (the rule areas it can cover) and `match`
# (patterns, every one of which must be found in the rule or in what they said). A match is
# only a candidate: Claude retires a rule only where the behaviour covers all of it. Add a
# behaviour here when a release builds in something people used to have to ask for.

NOW_PART = "Now part of the app"

BUILT_IN = (
    {"id": "document-file-names", "version": "3.0.0", "since": "2026-10-14",
     "does": "Your resume and cover letter files are named for you: your name, the employer "
             "as it writes its own name, then Resume (or CV) or Cover_Letter; Settings, File "
             "names, chooses another way.",
     "areas": ("documents", "other"),
     "match": (r"\b(?:file ?names?|named|name (?:the|my|each|every) (?:file|pdf|resume|cv|"
               r"letter|document)s?|call (?:the|my) (?:file|pdf)s?)\b|\.pdf\b|_(?:resume|cv|"
               r"cover)",)},
    {"id": "follow-ups-at-once", "version": "4.10.0", "since": "2026-11-05",
     "does": "Follow-ups you ask for on your page are written straight away, all together in "
             "one go, and show in Messages ready to copy.",
     "areas": ("messages", "other"),
     "match": (r"\bfollow[- ]?ups?\b",
               r"\b(?:at once|straight away|immediately|right away|as soon as|the moment|"
               r"together|in one go|all of them|without (?:waiting|asking)|when i (?:tap|ask|"
               r"press))\b")},
    {"id": "messages-fixed-by-themselves", "version": "4.10.0", "since": "2026-11-05",
     "does": "A message that breaks your rules (too long for LinkedIn, a phrase that reads "
             "machine-written, asking for a job) is rewritten by itself before you see it.",
     "areas": ("messages", "voice", "other"),
     "match": (r"\b(?:fix|rewrite|redraft|correct|shorten|check)\w*\b",
               r"\b(?:before (?:i see|showing|you show)|by (?:it|your)sel(?:f|ves)|without "
               r"(?:me|asking|being asked)|automatically)\b")},
    {"id": "files-on-the-page", "version": "4.10.0", "since": "2026-11-05",
     "does": "Once a draft is made, its files are put on your page by themselves, ready to "
             "save, with no button to press first.",
     "areas": ("documents", "other"),
     "match": (r"\b(?:files?|pdfs?|downloads?|documents?|resumes?|cvs?|letters?)\b",
               r"\b(?:on|to|onto|in) (?:the|my) (?:page|app)\b")},
    {"id": "closed-postings-set-aside", "version": "4.10.0", "since": "2026-11-05",
     "does": "A job whose posting has closed is set aside by itself, with Bring back if you "
             "want it again.",
     "areas": ("jobs", "search", "other"),
     "match": (r"\b(?:closed|expired|no longer (?:open|accepting|available|live)|taken down)\b",
               r"\b(?:jobs?|postings?|roles?|listings?|adverts?|openings?)\b")},
    {"id": "one-role-per-employer", "version": "4.10.1", "since": "2026-11-05",
     "does": "Jobs shows one role per employer, the best fit, with the others set aside and "
             "any role you added, drafted or applied for kept.",
     "areas": ("jobs", "search", "targets", "other"),
     "match": (r"\b(?:one|1|a single|single|only one)\s+(?:role|job|posting|position|"
               r"application)s?\s+(?:per|at each|for each|from each|at any|at a|at one)\s+"
               r"(?:employer|company|firm|organi[sz]ation)\b"
               r"|\b(?:several|multiple|many|lots of|two|2|more than one)\s+(?:roles?|jobs?|"
               r"postings?)\s+(?:at|from)\s+(?:the same|one|a single)\s+(?:employer|company|"
               r"firm)\b",)},
)
_BUILT_IN = {b["id"]: b for b in BUILT_IN}


def built_in_checked(data: dict | None = None) -> set[str]:
    """The behaviours whose rules have been judged already (`built_in_done`)."""
    got = (data if data is not None else file_data()).get("built_in") or {}
    return {str(x) for x in (got.get("checked") or []) if isinstance(x, str)}


def built_in_new(data: dict | None = None) -> list[dict]:
    """The behaviours this copy's rules have not been judged against yet."""
    seen = built_in_checked(data)
    return [b for b in BUILT_IN if b["id"] not in seen]


def covers(b: dict, entry: dict) -> bool:
    """Might behaviour `b` cover this rule? Every one of its patterns found in the rule or in
    what they said, in one of its areas. A candidate, never a verdict."""
    if entry.get("area") not in b.get("areas", AREAS):
        return False
    text = " ".join(str(entry.get(k) or "") for k in ("rule", "said"))
    return all(re.search(p, text, re.I) for p in b["match"])


def built_in_candidates(data: dict | None = None) -> list[tuple[int, dict, dict]]:
    """[(n, entry, behaviour)]: each active rule a behaviour not judged yet may cover, with
    the first such behaviour, oldest rule first."""
    data = file_data() if data is None else data
    new = built_in_new(data)
    if not new:
        return []
    rows = [r for r in (data.get("entries") or []) if isinstance(r, dict)]
    out = []
    for n, r in enumerate(rows, 1):
        if r.get("status", "active") != "active":
            continue
        b = next((b for b in new if covers(b, r)), None)
        if b:
            out.append((n, r, b))
    return out


def retire_built_in(n: int, bid: str, today: str | None = None) -> dict:
    """Entry n retired because behaviour `bid` now does what it asked: kept as history with
    NOW_PART, shown so on the page, and never proposed again (it is no longer active)."""
    if bid not in _BUILT_IN:
        raise SystemExit(f"learned: no behaviour {bid!r}; one of {', '.join(_BUILT_IN)}")
    rows = load()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no entry {n}; there are {len(rows)}")
    r = rows[n - 1]
    if r.get("status", "active") != "active":
        raise SystemExit(f"learned: entry {n} is not in use already")
    r["status"] = "retired"
    r["retired_why"] = NOW_PART
    r["built_in"] = bid
    r["retired_on"] = today or person.today().isoformat()
    _save(rows)
    return r


def built_in_done(today: str | None = None) -> tuple[int, str]:
    """Every behaviour in the registry recorded as judged, so this happens once for each.
    Returns (how many rules this pass put away as part of the app, the one line for the
    person, "" when there is nothing to say). Writes nothing where there is no rules file."""
    path = _path()
    if not path or not os.path.exists(path) or person.in_example(path):
        return 0, ""
    data = file_data()
    new = {b["id"] for b in built_in_new(data)}
    n = sum(1 for r in (data.get("entries") or []) if isinstance(r, dict)
            and r.get("built_in") in new and r.get("status") == "retired")
    data["built_in"] = {"checked": [b["id"] for b in BUILT_IN],
                        "on": today or person.today().isoformat()}
    _write_data(data)
    return n, built_in_line(n)


def built_in_line(n: int) -> str:
    """The one plain line the person is told, or "" for none."""
    if n <= 0:
        return ""
    if n == 1:
        return "1 of your rules is now part of the app, so it's off your list."
    return f"{n} of your rules are now part of the app, so they're off your list."


# ------------------------------------------------------------------ about the app, never a rule
#
# "Why is it so slow" is about the app, not about how the person wants their work done. Kept
# as a rule it was read before every draft and changed nothing (the maintainer, 2026-11-06:
# a complaint about how the app behaves is never saved as a personal rule; in the
# maintainer's own copy it is reported to them as an app bug, and for anyone else it is
# worked around). Two checks: a cheap pattern (`about_app`) that refuses a record until the
# chat says which it is, and the chat's own flag (`record --about-app`), which routes it
# (`route_about_app`) instead of keeping it and clears it from the turn's list.

# Slow, frozen, crashed or buggy only with the app as what is (a recruiter slow to reply, a
# crash course, the bug they fixed at their last job and interviews that froze are theirs:
# an independent review, 2026-11-06). Where unsure, the person's rule is kept.
_APP_SUBJECT = (r"(?:the app|this app|the page|this page|my page|the site|it|claude|the search|"
                r"searching|the chat|(?:a|the|this|that) button|buttons|loading|everything|"
                r"the sync|the update|updates|the screen)")
_APP_VERB_TO = r"(?:load|open|start|save|update|search|respond|answer|come up|show)"
ABOUT_APP = re.compile("|".join([
    r"\b" + _APP_SUBJECT + r"\s+(?:\w+\s+){0,2}slow(?:er)?\b(?!\s+to\s+(?!" + _APP_VERB_TO
    + r"\b)\w)",
    r"\bhow slow " + _APP_SUBJECT + r"\b",
    r"\b" + _APP_SUBJECT + r"\s+(?:\w+\s+){0,2}tak(?:es?|ing|en)\s+(?:forever|ages|so long|"
    r"too long|far too long|an age)\b",
    r"\b" + _APP_SUBJECT + r"\s+(?:\w+\s+){0,2}(?:crash(?:ed|es|ing)|fro(?:ze|zen)|"
    r"freez(?:es|ing)|buggy|glitch(?:ed|es|ing|y)?)\b",
    r"\b(?:it|app|page|screen|chat)\s+(?:hangs|hung|is hanging)\b",
    r"\b(?:a|the|this|another)\s+(?:bug|glitch)\s+(?:in|on|with)\s+(?:the|this|my)\s+(?:app|"
    r"page|site|search|chat|button|screen)\b",
    r"\b(?:it|app|page|screen|button|link|tab|chat|claude|sync|update|search)\s+(?:\w+\s+){0,2}"
    r"(?:doesn'?t|does not|isn'?t|is not|won'?t|will not|didn'?t|did not|never|stopped)\s+"
    r"(?:work(?:ing|s)?|load(?:ing|s)?|open(?:ing|s)?|respond(?:ing|s)?|sav(?:e|ing|es)"
    r"|updat(?:e|ing|es)|show(?:ing|s)? up|do(?:es)? anything)\b",
    r"\b(?:the|this|that|a)\s+(?:button|link|page|screen|app|tab)\s+(?:does nothing|is dead|"
    r"is blank|went blank|is empty|is stuck|is broken|broke)\b",
    r"\b(?:app|page|it|claude|everything|the site)\s+(?:is\s+)?broken\b",
    r"\bstuck (?:on|loading|at)\b", r"\bspinn(?:er|ing)\b", r"\bloading\s+(?:forever|for ages)\b",
    r"\b(?:an?|the)\s+error\s+(?:message|came up|popped up|appeared|keeps)\b",
    r"\b(?:gave|gives|throws?|threw|shows?|showed)\s+(?:me\s+)?an?\s+error\b",
    r"\bwhy\s+(?:does|did|is|do|won'?t|can'?t|isn'?t|doesn'?t)\s+(?:the app|the page|this app|"
    r"this page|my page|claude)\b(?!\s+(?:keep\s+)?(?:say|write|use|put|add|include|open|start|"
    r"end|word|phrase|suggest|pick|choose|show me)\w*)",
    r"\bkeeps?\s+(?:crashing|failing|freezing|logging me out|asking me to (?:allow|approve|"
    r"sign in|press))\b",
]), re.I)


def about_app(text: str) -> str:
    """The words that make `text` read as about how the app behaves, or "". A cue for the
    chat to decide, never the decision: the chat says which with `--about-app` or
    `--not-about-app`."""
    m = ABOUT_APP.search(own_words(str(text or "").replace("’", "'")))
    return m.group(0) if m else ""


ABOUT_APP_WHY = "about the app, worked around"
ABOUT_APP_BUG = "about the app, kept as an app bug for its maker"


def _maintainers() -> bool:
    """This is the app maintainer's own copy (tools/sync_app.py maintainers())."""
    try:
        import sync_app
        return bool(sync_app.maintainers())
    except Exception:  # noqa: BLE001  no git, no copy: anyone's
        return False


def route_about_app(said: str, today: str | None = None,
                    maintainer: bool | None = None) -> dict:
    """A complaint about how the app behaves, never kept as a rule. In the maintainer's own
    copy it is kept as an app bug (`app_bugs`, with a link to open it on the app's page,
    tools/report.py link); for anyone else it is set aside with ABOUT_APP_WHY and worked
    around. Either way it leaves the turn's list, so the end of the turn is not held for it."""
    said = str(said or "").strip()
    if not said:
        raise SystemExit("learned: --about-app needs what they said")
    mine = _maintainers() if maintainer is None else bool(maintainer)
    day = today or person.today().isoformat()
    row = skip(said, ABOUT_APP_BUG if mine else ABOUT_APP_WHY, today=day)
    row["route"] = "maintainer" if mine else "worked_around"
    if mine:
        try:
            import report
            link = report.link()
        except Exception:  # noqa: BLE001  no link to build: kept all the same
            link = ""
        data = file_data()
        bug = {"date": day, "said": said, "status": "open"}
        if link:
            bug["link"] = link
        data.setdefault("app_bugs", []).append(bug)
        _write_data(data)
        row["link"] = link
    return row


def app_bugs(include_closed: bool = False) -> list[dict]:
    """The complaints about the app kept as app bugs in the maintainer's own copy."""
    rows = [r for r in (file_data().get("app_bugs") or []) if isinstance(r, dict)]
    return rows if include_closed else [r for r in rows if r.get("status", "open") == "open"]


def close_app_bug(n: int, today: str | None = None) -> dict:
    """App bug n (numbered as `app-bugs --all` lists them), fixed or let go."""
    data = file_data()
    rows = [r for r in (data.get("app_bugs") or []) if isinstance(r, dict)]
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no app bug {n}; there are {len(rows)}")
    rows[n - 1]["status"] = "closed"
    rows[n - 1]["closed_on"] = today or person.today().isoformat()
    data["app_bugs"] = rows
    _write_data(data)
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
            body = phrase_pattern(phrase)
            if body:
                # Edges that work for a phrase that opens or closes on punctuation: \b
                # needs a word character there, so "(remote)" or "[sic]" never matched.
                # A phrase quoted in profile/CLAUDE.md's prose takes its capital from the
                # sentence it was quoted in, so it is matched anywhere.
                quoted = str(r.get("rule") or "").endswith(FROM_PROFILE_RULES)
                start = _OPENS if opens_a_sentence(phrase) and not quoted else r"(?<!\w)"
                # An initialism the person said to write in full (two or more capitals) is
                # a word in capitals: read in any case, it matched inside names.
                flags = re.M if _INITIALISM.fullmatch(str(phrase).strip()) else re.I | re.M
                out.append((phrase, re.compile(start + body + r"(?!\w)", flags)))
    return out


# A phrase that opens with the person saying what they did: "I made the move" is the same
# words as "I've made the move" and "I have made the move", and only the first was refused,
# so a follow-up saying "I've made the move" passed every check and was sent (2026-10-21).
_SUBJECTS = frozenset({"i", "we"})
_HELPER = r"(?:['’](?:ve|d)|\s+(?:have|had|has))?"
_INITIALISM = re.compile(r"[A-Z]{2,5}")


def phrase_pattern(phrase: str) -> str:
    """The pattern for a never-say phrase, without its edges: each word as written (an
    apostrophe either way), whitespace between, and, where it opens on "I" or "we" with a
    verb after it, the same words with "'ve", "'d", "have" or "had" between them."""
    # An apostrophe either way: a phrase typed on a phone arrives as "I’m", and the
    # message checks straighten every draft to "I'm" first, so the curly one never
    # matched anything (2026-10-20).
    words = [re.escape(w).replace("’", "'").replace("'", "['’]")
             for w in str(phrase or "").split()]
    if not words:
        return ""
    if len(words) >= 2 and str(phrase).split()[0].lower() in _SUBJECTS:
        return words[0] + _HELPER + r"\s+" + r"\s+".join(words[1:])
    return r"\s+".join(words)


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
        body = phrase_pattern(str(phrase).replace("’", "'"))
        if not body:
            continue
        start = _OPENS if opens_a_sentence(phrase) else r"(?<!\w)"
        flags = re.M if _INITIALISM.fullmatch(str(phrase).strip()) else re.I | re.M
        rx = re.compile(start + body + r"(?!\w)", flags)
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
    # A name the profile says to write in full is a ban on its initials: "Always write
    # "<Employer Name>" in full" held no "never", so "ex-<initials>" passed every check and went in
    # two sent messages (2026-10-21).
    for m in _IN_FULL.finditer(text):
        name = (m.group(1) or m.group(2)).strip()
        caps = [w for w in name.split() if w[:1].isupper()]
        short = "".join(w[0] for w in caps)
        if len(caps) < 2 or len(caps) != len(name.split()) or short.lower() in seen:
            continue
        seen.add(short.lower())
        rest = text[m.end():m.end() + 160]
        end = _CLAUSE_END.search(rest)
        out.append((short, " ".join((m.group(0) + (rest[:end.start()] if end else ""))
                                    .split())))
    return out


_IN_FULL = re.compile(r"\b(?:write|say|spell|name)\s+(?:out\s+)?(?:\"([^\"\n]{3,60})\"|"
                      r"“([^”\n]{3,60})”)\s+(?:in full|out in full|out)\b", re.I)


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
    """The phrases in `text` the person has said never to use: each never-say phrase, and,
    where one of them says the person moved (`bans_the_move`), every other way of saying
    that (`moved_claims`)."""
    text = str(text or "")
    rules = never_say()
    hits = [(m.start(), m.end(), m.group(0)) for _, rx in rules for m in rx.finditer(text)]
    if bans_the_move([p for p, _rx in rules]):
        own = _own_lines()
        for a, b, said in moved_claims(text, spans=True):
            # The person's own words are never caught by the wider family: a first note built
            # from their own ABOUT_ME was refused for the move it states (the maintainer's
            # copy, 2026-10-29). Their never-say phrases still are, word for word, above.
            if any(_flat(said) in o for o in own):
                continue
            if not any(x < b and a < y for x, y, _s in hits):
                hits.append((a, b, said))
    return [said for _a, _b, said in sorted(hits, key=lambda h: h[0])]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _own_lines() -> list[str]:
    """The lines the person set as their own in profile/networking.py, flattened."""
    try:
        if not person.exists("networking.py"):
            return []
        net = person.module("networking")
    except Exception:  # noqa: BLE001  no profile, or a broken one: nothing of theirs
        return []
    out = []
    for name in ("OPENER", "ABOUT_ME", "ASK", "WHO_LINE", "GREETING", "REFERRAL_LINE",
                 "REFERRAL_CLOSE"):
        v = getattr(net, name, "")
        out += [_flat(x) for x in (v if isinstance(v, (list, tuple)) else [v]) if str(x).strip()]
    return out


# A ban on saying the person moved ("recently moved", "relocating", "moving to <City>") is a
# ban on the claim, never on those few spellings of it: a note saying "just moved from London
# to Toronto" passed every check of a person whose profile said never to write "moving to
# Toronto", "relocating" or "recently moved", and reached their page as a ready draft
# (2026-10-26). A never-say phrase that is one of these turns the whole family on. "Made the
# move" is a person's own line in one profile, so it is caught only where it is banned itself,
# and "just arrived" is another's (their answer to "how long have you been here?"), so arriving
# is never in the family.
_MOVE_BAN = re.compile(
    r"\b(?:just|recently|newly|currently|finally)\s+(?:moved|moving|relocated|relocating|"
    r"emigrated)\b|\brelocat(?:e|ed|es|ing|ion)\b|\bemigrat(?:e|ed|ing)\b"
    r"|\b(?:moved|moving)\s+(?:over\s+|here\s+|back\s+|across\s+)?(?:to|from)\b"
    r"|\bmade\s+the\s+move\b", re.I)
# The family, as a draft says it. Each needs the person as the one moving: a verb with
# nothing moved after it ("I moved our reporting to dbt" moved reporting), or a place the
# profile knows after it ("moved to Snowflake", "moved to Brindle & Hart" are a tool and a job).
_OBJ = (r"(?!\s+(?:it|them|this|that|these|those|our|the|a|an|his|her|their|its|my|"
        r"everything|all|some|most|every|each)\b)")
_MOVED_NEAR = re.compile(
    r"\b(?:just|recently|newly|only\s+just|finally)\s+(?:moved|relocated|emigrated)"
    r"%s(?=\s+(?:to|from|over|here|back|across|in|to\s+the)\b|\s*[.,;:!?)]|\s*$)" % _OBJ,
    re.I)
_RELOCATED = re.compile(r"\b(?:relocat(?:e|ed|ing)|emigrat(?:e|ed|ing))\b%s" % _OBJ, re.I)
_SINCE_MOVING = re.compile(r"\b(?:since|after|before)\s+(?:moving|relocating|emigrating|"
                           r"coming\s+over)\b", re.I)
_CAME_OVER = re.compile(r"\b(?:came|come|coming)\s+over\s+(?:from|to|here)\b", re.I)
_MOVED_TO = re.compile(r"\b(?:moved|moving|relocated|relocating)\s+(?:over\s+|here\s+|back\s+|"
                       r"across\s+)?(?:to|from)\s+(?:the\s+)?", re.I)


def bans_the_move(phrases=None) -> bool:
    """Has the person said never to say they moved: a never-say phrase that is a way of
    saying it ("recently moved", "relocating", "moving to Toronto")? `phrases` defaults to
    every never-say phrase recorded."""
    if phrases is None:
        phrases = [p for p, _rx in never_say()]
    return any(_MOVE_BAN.search(str(p)) for p in phrases)


def _places() -> list[str]:
    """Every place the profile names, longest first: where the person lives (and each of its
    names), where each employer was told they are, and where each past role was."""
    out = set()
    try:
        import told
        out.update(n for n, _qual in told._known())
    except Exception:  # noqa: BLE001  no profile, or none of it: no places
        pass
    try:
        roles = person.module("roles") if person.exists("roles.py") else None
    except Exception:  # noqa: BLE001
        roles = None
    for r in getattr(roles, "ROLES", None) or ():
        loc = str((r or {}).get("loc") or "") if isinstance(r, dict) else ""
        out.update(p.strip() for p in loc.split(",") if len(p.strip()) > 1)
    return sorted(out, key=len, reverse=True)


def moved_claims(text: str, spans: bool = False) -> list:
    """Every way `text` says the person moved, is moving or relocated: "just moved",
    "recently relocated", "relocating", "since moving", "came over from", and "moved from" or
    "moving to" a place the profile knows. Never "just arrived" or "made the move", which
    are people's own lines. With `spans`, (start, end, words) each."""
    text = str(text or "")
    if not _MOVE_BAN.search(text) and not _SINCE_MOVING.search(text) \
            and not _CAME_OVER.search(text) and not _MOVED_NEAR.search(text):
        return []
    found = []
    for rx in (_MOVED_NEAR, _RELOCATED, _SINCE_MOVING, _CAME_OVER):
        found += [(m.start(), m.end()) for m in rx.finditer(text)]
    places = _places()
    for m in _MOVED_TO.finditer(text):
        # The rest of the clause: "moved from London to Toronto" names the known one second.
        rest = re.split(r"[.;:!?\n]", text[m.end():m.end() + 80], maxsplit=1)[0]
        for p in places:
            hit = re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(p), rest, re.I)
            if hit:
                found.append((m.start(), m.end() + hit.end()))
                break
    # One claim a stretch: "just moved from London to Toronto" is one, said whole.
    merged = []
    for a, b in sorted(found):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    out = []
    for a, b in merged:
        # Said whole, to the places it names: "just moved from London to Toronto".
        tail = _PLACE_TAIL.match(text, b)
        b = tail.end() if tail else b
        out.append((a, b, text[a:b]) if spans else text[a:b])
    return out


_PLACE_TAIL = re.compile(r"(?:\s+(?:(?:from|to|over|in)\s+)*(?:the\s+)?[A-Z][\w'’-]*"
                         r"(?:\s+[A-Z][\w'’-]*)*){1,2}")


def entry_key(r: dict) -> tuple:
    return (r.get("date"), r.get("area"), r.get("rule"))


_key = entry_key  # the module's own name for it; other modules call entry_key


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
        # One setting set twice: the later word is the one followed. "Ask me which place for
        # each employer" stayed in every brief beside the rule that replaced it, "this
        # employer hears one city, everyone else the other" (2026-11-03). Lists only grow.
        mine = _one_settings(r)
        later_same = next((x for x in active[n + 1:] if mine & _one_settings(x)
                           and (x.get("rule") or "") != (r.get("rule") or "")), None)
        if later_same is not None:
            out[_key(r)] = later_same
            continue
        for later in active[n + 1:]:
            # As a phrase, never as letters inside a word: a ban on two initials overruled every
            # earlier rule with "back" or "bank" in it.
            if any(p.strip() and p.lower() not in own
                   and re.search(r"(?<!\w)%s(?!\w)" % re.escape(p.lower()), text)
                   for p in map(str, later.get("never_say") or ())):
                out[_key(r)] = later
                break
    return out


def _one_settings(r: dict) -> set:
    """The settings an entry sets that hold one value (never a list a rule adds to)."""
    return {str(a) for a in r.get("applied_to") or ()
            if _SETTING.search(_FILE_NAME.sub(" ", str(a))) and not _LISTS.search(str(a))}


def brief(area: str | None = None, channel: str | None = None, reader: str | None = None) -> str:
    """The active rules as lines to follow before drafting, or "" when there are none.
    A rule a later one overrules (superseded) is left out. For messages, the messages the
    person approved come first (`approved_examples`), for this channel and reader where
    there are some: rules drawn from them were followed, and the messages themselves were
    never put in front of the drafter (2026-10-21)."""
    area = area_of(area) if area else None
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
    row = {"date": today or person.today().isoformat(), "said": str(said).strip(),
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
    _first_write(data, path)
    data.setdefault("entries", load())
    data.setdefault("offers", all_offers())
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
    today = today or person.today()
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
    o = {"date": today or person.today().isoformat(), "setting": setting,
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
    o["decision"], o["decided"] = choice, today or person.today().isoformat()
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
# The page's own words. A tap on the page reaches the chat as the doorbell "[app] [work:<id>]",
# and Claude Code wraps a page's comment as "Artifact comment sent to Claude" with the page's
# text (notice, card, receipt) quoted in it: all the app's words, never the person's (the
# skill says a ring is "never the person's words"). A message that is such a ring is the app's
# wholly; the doorbell line is dropped from any other. Only what the person typed is read.
# Claude Code heads such a turn "[Artifact comment sent to Claude]", in brackets, with the
# comment's thread and the page's own text it was left on: "reads like" in that text was held
# as the person's reaction (2026-11-05). The header and everything under it to the doorbell,
# a blank line or the end is the page's, wherever it sits in the prompt (`_WRAPPER`).
_PAGE_RING = re.compile(r"^\s*\[?\s*(?:\[app\]|artifact comment sent to claude)", re.I)
_DOORBELL = re.compile(r"^[ \t]*\[app\][^\n]*$", re.I | re.M)
_WRAPPER = re.compile(r"^[ \t]*\[?[ \t]*artifact comment sent to claude\b.*?"
                      r"(?:^[ \t]*\[app\][^\n]*$|\n[ \t]*\n|\Z)", re.I | re.S | re.M)


def own_words(text: str) -> str:
    """Only what the person typed: the page's wrapper around a comment (`_WRAPPER`), its
    doorbell lines, the harness's reminders, quoted and pasted text all taken out, in the
    order the reaction and approval checks read it."""
    t = _WRAPPER.sub(" ", str(text or ""))
    return without_pasted(_LONG_QUOTE.sub(" ", _NOT_THEIRS.sub(" ", _DOORBELL.sub(" ", t))))
_LONG_QUOTE = re.compile(r'"[^"\n]{80,}"|\u201c[^\u201d\n]{80,}\u201d')
# "She replied: ..." introduces their words, not the person's.
_THEIR_WORDS = re.compile(r"\b(?:replied|wrote back|responded|answered|said|says|wrote|messaged"
                          r"|their (?:reply|message|answer)|(?:his|her) (?:reply|message|answer)"
                          r"|the reply)\s*:", re.I)

# Someone else's message pasted in whole, with no "replied:" to say so. A contact's "please
# don't use my work email" was held as the person's own reaction, and the chat had to skip it
# before it could draft the reply (2026-11-03). Such a message opens on a greeting to the
# person by their own first name ("Hi Morgan,"), on a thanks for getting in touch, on a
# LinkedIn or email header (a name and a time, "From:", "sent the following message"), or
# on the line after a short one that introduces it ("Juno replied on LinkedIn"); it runs to
# its sign-off ("Best,\nJuno"), or to the end. What the person wrote around it is theirs.
_GREETING = (r"(?:hi|hey|hello|hiya|dear|morning|good (?:morning|afternoon|evening))"
             r"[ \t]+(?:there\b|{name}\b)")
_OPENS_THEIRS = re.compile(
    r"(?:thanks?|thank you)(?: so much| very much| a lot)? for (?:reaching out|getting in "
    r"touch|connecting|the (?:connection|connect|invite|invitation)|your (?:message|note|"
    r"interest|patience)|thinking of me)\b|(?:great|nice|good|lovely) to (?:hear from|connect "
    r"with|meet) you\b", re.I)
_HEADER = re.compile(r"(?:from|sent|subject|date|cc)[ \t]*:[ \t]*\S|-{2,}[ \t]*(?:original|"
                     r"forwarded) message|.{0,60}\bsent the following messages?\b|"
                     r"(?:(?-i:[A-Z])[\w'’.-]*[ \t]+){0,3}\d{1,2}:\d{2}[ \t]*[ap]\.?m\.?[ \t]*$|"
                     r"\d{1,2}:\d{2}[ \t]*(?:[ap]\.?m\.?)?[ \t]*$|"
                     r"view [\w'’ .-]{1,60}['’]s? profile[ \t]*$", re.I)
_INTRODUCES = re.compile(r"(?<!\bi )(?<!\byou )(?<!\bwe )\b(?:replied|wrote back|responded|"
                         r"got back to me|messaged me|wrote to me|sent me (?:this|a message|a "
                         r"note|a dm))\b|\b(?:reply|message|note|answer|response|email|dm|"
                         r"inmail) (?:back )?from\b|\b(?:his|her|their|[a-z]+['’]s) (?:reply|"
                         r"message|answer|response)\b|\b(?:got this from|came in from)\b", re.I)
_SIGNS_OFF = re.compile(r"(?:best|best wishes|all the best|cheers|thanks|thank you|many thanks|"
                        r"thanks again|regards|kind regards|warm regards|warmly|speak soon|talk "
                        r"soon|take care|sincerely)[ \t]*[,!.]?[ \t]*$", re.I)
INTRO_MAX_WORDS = 12


def _own_first_name() -> str:
    """The person's own first name (person.json), or "" where there is no profile."""
    try:
        name = person.get("identity.first", "") or str(person.get("identity.name", "")).split(" ")[0]
    except Exception:  # noqa: BLE001  the app itself, or a profile not set up
        return ""
    return re.sub(r"[^\w'’-]", "", str(name or ""))


# A line the person says to Claude, never a label over someone's message: "Draft a reply to
# Juno's message." read as introducing what followed, and the instruction under it was
# dropped as Juno's (the release review, 2026-11-03).
_ASKS = re.compile(r"(?:please[ \t]+)?(?:(?:can|could|would|will)[ \t]+you\b|(?:draft|write|"
                   r"reply|respond|answer|help|make|do|send|look|read|check|tell|show|turn|"
                   r"redo|rewrite)\b)", re.I)


def _name_line(s: str) -> bool:
    """A name under a sign-off ("Juno", "Juno C."): a few words, capitalised."""
    return bool(s) and len(s.split()) <= 4 and s[:1].isupper()


def _signed_after(lines: list[str], i: int) -> bool:
    """Do the lines after `i` close on a sign-off with a name under it ("Best,\\nJuno"), or
    one ending in a comma: what runs to it reads as a message someone wrote."""
    for j in range(i + 1, len(lines)):
        s = lines[j].strip()
        if _SIGNS_OFF.match(s):
            if s.endswith(","):
                return True
            if _name_line(next((x.strip() for x in lines[j + 1:] if x.strip()), "")):
                return True
    return False


def _introduces(prev: str, lines: list[str], i: int) -> bool:
    """Is `prev`, the line before lines[i], a short one introducing a message under it? Only
    as a label ("Juno's reply", "Juno got back to me on LinkedIn") or ending in ":", or
    where what follows reads as a message (it closes on a sign-off). A sentence of the
    person's own ("Draft a reply to Juno's message.") introduces nothing."""
    p = prev.strip()
    if not (0 < len(p.split()) <= INTRO_MAX_WORDS and _INTRODUCES.search(p)):
        return False
    if p.endswith(":"):
        return True
    if p[-1:] not in ".?!" and not _ASKS.match(p):
        return True
    return _signed_after(lines, i - 1)


def without_pasted(text: str) -> str:
    """`text` with every message pasted into it that someone else wrote taken out, so only
    the person's own words are left to read for a reaction or an approval."""
    name = _own_first_name()
    greeting = re.compile(_GREETING.format(name=re.escape(name) if name else r"(?!x)x"), re.I)
    keep, theirs, prev = [], False, ""
    lines = str(text or "").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if theirs == "signed":
            # A sign-off with a name under it ("Best,\nJuno") closes their message, and the
            # person's own words may follow it. A "Thanks!" with no name is still theirs.
            theirs = not _name_line(s)
            continue
        if theirs:
            if _SIGNS_OFF.match(s):
                theirs = "signed"
            continue
        if s and (greeting.match(s) or _HEADER.match(s) or _introduces(prev, lines, i)):
            theirs = True                  # this line is theirs too: a greeting, a header
            continue
        if s and _OPENS_THEIRS.match(s):
            # "Thanks for reaching out" opens their message, or is the person thanking
            # Claude: the line is theirs, and what follows only when it closes on a sign-off.
            # Everything after it was dropped (the release review, 2026-11-03).
            theirs = _signed_after(lines, i)
            continue
        keep.append(line)
        prev = s or prev
    return "\n".join(keep)


# The person approving a message: kept as an example (`approve`), the way a reaction against
# one is kept as a rule. Said about a message, never a contact's own words (the same cuts
# `reaction` makes apply).
APPROVAL = re.compile("|".join([
    # "Perfect" about what was shown, never what something must be: "it needs to be perfect
    # and completely comprehensive" was kept as an approval, and the chat had to clear it with
    # a commit and a pull request of its own (audit D12, 2026-11-10).
    r"\b(?:(?:almost|nearly|just about|pretty much)\s+)?(?<!\bbe )(?<!\bbeing )(?<!\bnot )"
    r"(?<!\bmake it )perfect\b",
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
    if _RELAYED.search(t) or _PAGE_RING.search(t):
        return ""
    t = own_words(t)
    cut = _THEIR_WORDS.search(t)
    if cut:
        t = t[:cut.start()]
    if reaction(t):
        return ""                  # a reaction against it is the one to record
    m = APPROVAL.search(t)
    return m.group(0).strip() if m else ""


# Too long said of the chat, the page or the app, never of something written for the person:
# "hand over to a fresh helper ..., this chat is too long" and "the page is too long to load"
# held turns as reactions to a draft (audit D12, 2026-11-10).
# A list, a screen or the page being too long is a reaction to what was shown ("the list is
# too long, just give me the top 5"): only the page too slow to load is about the app (the
# review of D12, 2026-11-11).
_NOT_A_DRAFT = re.compile(
    r"\b(?:this|the|my|that)\s+(?:chat|app|conversation|session|context|thread|history|"
    r"helper)\s+(?:is|was|gets|got|has got|'s)\s+(?:\w+\s+){0,2}?too\s+(?:long|big|slow)\b|"
    r"\b(?:this|the|my|that)\s+page\s+(?:is|was|gets|got|'s)\s+(?:\w+\s+){0,2}?too\s+"
    r"(?:long\s+to\s+(?:load|open)|slow)\b", re.I)


def reaction(text: str) -> str:
    """The words in `text` that make it a reaction, or "" when it is none."""
    t = str(text or "").replace("\u2019", "'").replace("\u2018", "'")
    if not t.strip() or t.lstrip().startswith(("<task-notification", "<system-reminder",
                                                 "<command-", "<local-command")):
        return ""
    if t.lstrip().startswith("/reply"):          # the rest is the contact's message
        t = t.lstrip().split("\n", 1)[0]
    if _RELAYED.search(t) or _PAGE_RING.search(t):   # another agent's report, or the page's ring
        return ""
    t = own_words(t)
    cut = _THEIR_WORDS.search(t)
    if cut:
        t = t[:cut.start()]
    t = _NOT_A_DRAFT.sub(" ", t)
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
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
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


def note(text: str, output: str = "") -> dict | None:
    """Words the person typed into the page's Tweak box, put on this chat's list like any
    reaction said in the chat (the hook never sees them: they arrive through the page's
    database). From then on every composer refuses and the turn cannot end until they are
    recorded or skipped, `--via "page tweak"` with the output's kind."""
    row = note_reaction(text, cue="page tweak", again=True)
    if row is not None and output:
        rows = _load_pending()
        for r in rows:
            if r.get("said") == row["said"] and not r.get("answered"):
                r["output"] = output
        _save_pending(rows)
        row["output"] = output
    return row


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


def skip(said: str, why: str, today: str | None = None, via: str = "",
         output: str = "") -> dict:
    """A reaction that sets no rule (a one-off, or not a reaction at all), with the reason:
    the explicit alternative to recording it."""
    if not str(why or "").strip():
        raise SystemExit("learned: skip needs why it sets no rule")
    data = _data()
    row = {"date": today or person.today().isoformat(), "said": str(said or "").strip(),
           "why": " ".join(str(why).split())}
    if str(via or "").strip():
        row["via"] = str(via).strip()
    if str(output or "").strip():
        row["output"] = str(output).strip()
    path = _writable()
    if path:
        _first_write(data, path)
        data.setdefault("skipped", []).append(row)
        data.setdefault("entries", load())
        data.setdefault("offers", all_offers())
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
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


GITHUB_EVENT = re.compile(r"<event\b[^>]*\bsource=\"github\"", re.I)
GITHUB_EVENT_SAID = ("A GitHub event about a save's pull request: nothing waits on it here. "
                     "Read nothing and run nothing else; where this chat has "
                     "unsubscribe_pr_activity, make that one call for this pull request, then "
                     "end the turn with no text.")


# A turn the app or the platform makes, never the person typing: a ring from the page, a task's
# notification, a scheduled run, a GitHub event, a peer chat's message.
_MACHINE_TURN = re.compile(r"^\s*(?:\[app\]|<\\?task-notification>|Scheduled run:|<wake\b|<event\b"
                           r"|<webhook-payload>|<child-session-event>|\[SYSTEM)"
                           r"|Artifact comment sent to Claude", re.I)
RETIRED_PERSON = ("This chat handed the person's page to a fresh helper, which answers the page "
                  "now. The person is writing here themself: answer the person as in any chat, "
                  "and put anything for their page on the page as ever.")


def _retired() -> str:
    """The one line for a chat that has handed the page on (app_listen.retired_here), or "".
    Never raises."""
    try:
        import app_listen
        if app_listen.retired_here():
            return app_listen.RETIRED_LINE.format(chat=app_listen.this_chat())
    except Exception:  # noqa: BLE001  the hook never breaks a chat
        pass
    return ""


def hook(event: dict) -> dict:
    """The Claude Code hook (the one the app ships, allowlisted in security_guards.py).

    UserPromptSubmit: a prompt that reads as a reaction goes on this chat's list, and the
    chat is told, in the turn, to record it. Stop: the turn is held while a reaction from
    the person has no `learned.py record` or `skip` after it, read from the transcript
    (which also holds messages sent while the chat was working) and from the list. Returns
    what the hook prints: {} to let things be."""
    path = _path()
    if path is None or person.in_example(path):
        return {}                     # the app itself, before /setup, or its example person
    name = event.get("hook_event_name") or ""
    retired = _retired()
    if retired and name == "UserPromptSubmit":
        # A helper that handed the page on: one line a turn, nothing read (app_listen
        # RETIRED_LINE). A turn on a nearly full chat can compact it (2026-11-06). Never to the
        # person typing: they were answered "archive yourself" mid-conversation (second audit
        # A8); they are answered as in any chat.
        if not _MACHINE_TURN.search(str(event.get("prompt") or "")):
            retired = RETIRED_PERSON
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": retired}}
    if retired and name == "Stop":
        return {}                     # never held for work: it does none (app.py retired)
    if name == "UserPromptSubmit" and GITHUB_EVENT.search(str(event.get("prompt") or "")):
        # A save's pull request, which the cloud chat was subscribed to by itself: nothing in
        # a person's copy waits on one (CLAUDE.md, "Saving"), and each woke the chat twice a
        # save (the maintainer's copy, 2026-11-06).
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": GITHUB_EVENT_SAID}}
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
        app_cue = about_app(text)
        if app_cue:
            # A complaint about the app itself is never a rule of theirs: it is routed, and
            # the routing clears it from the list, so the turn is not held for it (2026-11-06).
            return {"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"The person reacted (\"{cue}\"), and it reads as about how the app itself "
                    f"behaves (\"{app_cue}\"). Judge it. Only if it is plainly about the app and "
                    "says nothing about how they want their own work done: python3 "
                    "tools/learned.py record --about-app --said \"<their words>\" (it routes it "
                    "and clears it) and work round it now, saying only what it prints to say. "
                    "If it says how they want their work done, or you are not sure, it is "
                    "theirs: record it as usual, adding --not-about-app.")}}
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
    undone = _undone(event, items)
    # One hold a turn, in the form this chat's Claude Code honours (_page_hold_form): the
    # reaction with whatever else is undone, else what is undone, else the page owed.
    transcript = event.get("transcript_path") or ""
    if not waiting:
        if undone:
            return _page_hold_form("Not finished: " + " ".join(undone), transcript)
        return _page_hold(event)
    first = waiting[0]
    held = int(first.get("held") or 0)
    if held >= HOLD_LIMIT:
        first["answered"] = dt.datetime.now().isoformat(timespec="seconds")
        first["let_go"] = True
        _save_pending(rows)
        # Shown to the person: their own words and what to do, never a file's name (X-75).
        let_go = {"systemMessage": LET_GO.format(said=" ".join(first["said"].split())[:100])}
        return dict(let_go, **_page_hold_form("Not finished: " + " ".join(undone), transcript)) \
            if undone else let_go
    first["held"] = held + 1
    _save_pending(rows)
    return _page_hold_form(" ".join([refuse_over_pending("Not finished")] + undone), transcript)


LET_GO = ("I couldn't keep what you said (\"{said}\") as a rule this time. Say it again "
          "whenever you want it kept.")


# ------------------------------------------------------------------ what a turn leaves undone
#
# Two things a chat was only told to do, and a chat-only person lost when it did not: saving
# the turn's work (the stranger audit, 2026-11-03, X-62: quick edits and taps gone with the
# computer) and starting the improvements the day's update check listed (the chat-only review,
# S4: listed every morning for days, never started). The end of the turn is held for them the
# way it is for a reaction: once a turn (never while Claude Code already continues for a hold,
# stop_hook_active), a few times a day for each chat at most, with a way out recorded for a
# chat that cannot start the improvements (profile_upgrades.py --not-now), never in a chat
# started for one big job, and never breaking a chat. Days by one clock, the person's
# (person.today).

SAVE_STEPS = ("this turn's work is not saved anywhere that outlives this chat ({what}). Run "
              "python3 tools/land.py --detach --message \"<what changed>\" (an ordinary call: "
              "it returns at once and saves in a process of its own), then end the turn; "
              "nothing to say about it.")
UPGRADE_STEPS = ("{n} improvement{s} to the person's search that the update check listed "
                 "{have} not been started today. Start them now, never asking first: one "
                 "background agent (model sonnet) that follows .claude/commands/upgrade.md, then "
                 "end the turn; never show an id, a version or the word upgrade. Only if this "
                 "chat cannot start one: python3 tools/profile_upgrades.py --not-now \"<why>\".")
# Started: an agent given /upgrade, the skill itself, or its first step (reading the plan).
_UPGRADE_STARTED = re.compile(r"\.claude/commands/upgrade\.md|(?:^|\s)/upgrade\b|"
                              r"^upgrade(?:\s+\d+)?$|profile_upgrades\.py[\"']?\s+--plan\b")


def _turn_tools(items: list) -> list[str]:
    """What this turn ran: the commands after the last turn the chat finished, however the
    turn opened (the person, a scheduled run, a notification)."""
    i = len(items)
    while i and items[i - 1][1] == "end":
        i -= 1                          # this turn's own final message, already written
    j = i
    while j and items[j - 1][1] != "end":
        j -= 1
    return [t for _n, k, t in items[j:i] if k == "tool"]


def _undone(event: dict, items: list) -> list[str]:
    """The reasons this turn is not finished yet, beyond a reaction: [] to let it end."""
    if event.get("stop_hook_active"):
        return []
    out = []
    try:
        import app_listen
        import land
        import profile_upgrades
        chat = app_listen.this_chat() or str(event.get("session_id") or "")
        today = person.today()
        tools = _turn_tools(items)
        if any(_UPGRADE_STARTED.search(t) for t in tools):
            profile_upgrades.mark_started(today)
        if any(_WORK_CHAT.search(t) for _n, _k, t in items) or _job_chat(event):
            return out                  # a chat started for one big job: it lands its own work
        late = _late_work(chat)
        if late:
            out.append(LATE_STEPS.format(ids=", ".join(late[:6]) + (" ..." if len(late) > 6
                                                                    else "")))
        ids = profile_upgrades.unstarted(today, chat)
        if ids and profile_upgrades.hold_once(chat, today):
            out.append(UPGRADE_STEPS.format(n=len(ids), s="s" if len(ids) != 1 else "",
                                            have="have" if len(ids) != 1 else "has"))
        # A save this turn started, or one still running or asked for (land.wanted), is a
        # save in progress: the hold fired while a save ran, and added a turn every time
        # (the maintainer, 2026-11-05).
        saving = any(_LANDING.search(t) for t in tools)
        what = [] if saving else land.save_due(person.state(), chat, today.isoformat())
        if what and not _save_now(what):
            out.append(SAVE_STEPS.format(what=", ".join(what)))
    except Exception:  # noqa: BLE001  a hook must never break the chat it runs in
        return out
    return out


def _save_now(what: list[str]) -> bool:
    """The save the turn would be held for, started here, in a process of its own (land.py
    --detach), so the turn ends: the hold spent a whole turn of the chat, its history read
    again, only to run that one command (audit D11, 2026-11-10). True when it started; where it
    could not, the turn is held with the steps, as before."""
    import contextlib
    import io
    import land
    if os.environ.get("LJS_HOOK_NO_SAVE"):
        return False                   # the app's own tests: no landing started in their copies
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = land.detach(person.state(), "Saved: " + ", ".join(what)[:60])
    except Exception:  # noqa: BLE001  the chat is asked to, as before
        return False
    return code == 0


LATE_STEPS = ("work the person asked for on their page while the last pass ran is still waiting "
              "({ids}): it was named at that pass's end and never taken. Take it now, as a ring "
              "is taken (the app skill, step 0: the same Agent call, its notification \"work "
              "waiting after the last pass: {ids}\"), then end the turn; nothing to say about it.")


def _late_work(chat: str) -> list[str]:
    """The work the last pass of the page's helper named at its end and never took, for this
    chat (page_reads.late_waiting), the hold kept as made so it is made once."""
    import page_reads
    late = page_reads.late_waiting(chat)
    if late:
        page_reads.late_held()
    return late


_WORK_CHAT = re.compile(r"tools/app\.py start\b[^\n]*--work \S")
# A landing this turn started: land.py itself, or the page update that ends a wake and starts
# one (`app.py view ... --end`).
_LANDING = re.compile(r"tools/land\.py(?![^\n]*--(?:after-merge|waiting))|tools/app\.py[\"']?\s+view\b[^\n]*--end\b")


def _job_chat(event: dict) -> bool:
    """Was this chat started for one big job (`app.py start --work`, app_setup.job_chat)?
    Its later messages no longer name the job, and the person may type in it."""
    try:
        import app_setup
        return bool(app_setup.job_chat(str(event.get("session_id") or "")))
    except Exception:  # noqa: BLE001  a hook must never break the chat it runs in
        return False

# ------------------------------------------------------------------ the page owed
#
# A person whose page was never published never learns they have one: start printed "page to
# publish", the chat went on with what they asked, and nothing held it (the chat-only review,
# S1; the stranger audit, X-25). While this chat owes the page (app_setup.page_owed: a copy of
# their own with a profile, no page address, a clean record, no other chat setting them up,
# and this chat never having said it cannot publish), a turn the person opened is held until
# it is published, at most PAGE_HOLDS times a chat a day, and only where the hold can be
# counted: a count that cannot be saved holds nothing, never every turn. The way out is this
# chat's own (`app.py published none --why`), never the copy's.
PAGE_HOLDS = 3
PAGE_HELD = "ljs-page-held.json"
_SCHEDULED = re.compile(r"^\s*(?:Scheduled run:|<\\?task-notification>)")
PAGE_OWED = ("Not finished: this person's job search page has never been published, so nothing "
             "tells them it exists. Before this turn ends, never asking first: python3 "
             "tools/app.py start --on \"<this chat's model>\" --tools \"<browser tools>\" and its "
             "page steps (build, publish, published), then the one line `published` gives you "
             "to tell them. If this chat cannot publish (no Artifact tool, or a publish refused "
             "twice): python3 tools/app.py published none --why \"<why>\", for this chat only.")
PAGE_DUE = ("The person's job search page has never been published. In this turn, before the "
            "rest and never asking first: python3 tools/app.py start and its page steps, then "
            "tell them the one line `app.py published` gives you. If this chat cannot publish: "
            "python3 tools/app.py published none --why \"<why>\" (this chat only).")


def _page_today() -> str:
    """The person's own day (person.today(): their zone, or the day a run was told), never
    the computer's: a cloud computer's clock is UTC."""
    try:
        return person.today().isoformat()
    except Exception:  # noqa: BLE001  no profile to read: the computer's day
        return dt.date.today().isoformat()


def _last_said(path: str) -> tuple[str, str]:
    """(who, text) of the newest message in the chat that is not a tool's answer: "human"
    when the person wrote it (or sent it while the chat worked), else what Claude Code says
    sent it ("task-notification" for a scheduled run, a ring or a job finishing)."""
    for line in reversed(_tail_lines(path)):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("type") != "user" or d.get("isMeta") \
                or d.get("isCompactSummary") or d.get("isSidechain"):
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, list):
            if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                continue
            content = "\n".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
        origin = d.get("origin") if isinstance(d.get("origin"), dict) else {}
        return str(origin.get("kind") or "human"), str(content or "")
    return "", ""


# Stop's own feedback (hookSpecificOutput.additionalContext) keeps the turn going from Claude
# Code 2.1.163 on, with no hook error shown to the person (its changelog: "Stop and SubagentStop
# hooks can now return hookSpecificOutput.additionalContext to give Claude feedback and keep the
# turn going without being labeled a hook error"); an older one ignores it and lets the turn
# end. Each transcript entry carries the version that wrote it: from that version the page's
# hold is the non-error form, below it or where none is known a block, which every version
# honours (the chat-only branch's third round).
PAGE_HOLD_CONTEXT_FROM = (2, 1, 163)


def _page_hold_form(reason: str, path: str) -> dict:
    version = ()
    for line in reversed(_tail_lines(path)):
        m = re.search(r'"version"\s*:\s*"(\d+)\.(\d+)\.(\d+)', line)
        if m and ('"type":"user"' in line or '"type": "user"' in line
                  or '"type":"assistant"' in line or '"type": "assistant"' in line):
            version = tuple(int(x) for x in m.groups())
            break
    if version >= PAGE_HOLD_CONTEXT_FROM:
        return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": reason}}
    return {"decision": "block", "reason": reason}


# `app.py published <url>` keeps the page's address in profile/app.json, on this chat's
# computer until the chat saves it. One that never did lost it with a computer replaced
# overnight, and the next day was held to publish a second page, with a second first-page line
# and pin question. The chat's transcript comes back with it (code.claude.com/docs/en/
# claude-code-on-the-web, "Environment expired": "Restored: your conversation history"), and
# the address is in it: kept again from there, once a day, never a second page.
_PUBLISHED_URL = re.compile(r"app\.py[\"']?\s+published\s+[\"']?(https://claude\.ai/[^\s\"'`]+)")
PAGE_HEALED = ("The person's page address came back from this chat's own history (it was kept "
               "on a computer since replaced, never saved): save it with the rest now (CLAUDE.md, "
               "\"Saving\"). Nothing to tell the person about it.")


def _published_here(path: str) -> str:
    """The newest page address this chat kept, read back from its transcript, or ""."""
    try:
        fh = open(path, "rb")
    except (OSError, TypeError):
        return ""
    with fh:
        fh.seek(0, os.SEEK_END)
        size = at = fh.tell()
        rest = b""
        while at > 0 and size - at < TAIL_MAX:
            step = min(TAIL_BLOCK, at)
            at -= step
            fh.seek(at)
            lines = (fh.read(step) + rest).split(b"\n")
            rest = lines[0] if at > 0 else b""
            for line in reversed(lines[1:] if at > 0 else lines):
                if b"published" not in line or b'"tool_use"' not in line:
                    continue
                found = _PUBLISHED_URL.findall(line.decode("utf-8", "replace").replace('\\"', '"'))
                if found:
                    return found[-1]
    return ""


def _heal_page(chat: str, transcript: str) -> bool:
    """Keep again the address this chat's own transcript shows it published, where the copy's
    record says no page was ever made. True when it did."""
    import app_listen
    import app_setup
    if not transcript or app_setup.page_owed(chat) != "new":
        return False
    path = app_setup._local_file(PAGE_HELD)
    got = app_setup.read_json(path, {})
    key, day = (chat or "this-folder") + ":heal", _page_today()
    if got.get(key) == day:
        return False
    got[key] = day
    try:
        app_setup.write_json(path, got)
    except OSError:
        return False
    url = _published_here(transcript)
    if not url:
        return False
    app_setup.record_page(url, chat=chat, current=False)
    app_listen.mark_introduced()
    if not app_listen.pin_asked():
        app_listen.record_pin_offered()          # offered when it was published
    return True


def _page_owed_here(transcript: str = "") -> tuple[str, str]:
    """(this chat's id, "new") while this chat owes the person's first page, else ("", "")."""
    try:
        import app_listen
        import app_setup
        chat = app_listen.this_chat("")
        _heal_page(chat, transcript)
        owed = app_setup.page_owed(chat)
        return (chat, owed) if owed else ("", "")
    except Exception:  # noqa: BLE001  a hook never breaks the chat it runs in
        return "", ""


def _page_hold(event: dict) -> dict:
    """The Stop hold while the page is owed: {} or a hold in the form this Claude Code takes.
    Once a turn: never while Claude Code already continues for a hold (stop_hook_active)."""
    if event.get("stop_hook_active"):
        return {}
    chat, owed = _page_owed_here(event.get("transcript_path") or "")
    if not owed:
        return {}
    who, text = _last_said(event.get("transcript_path") or "")
    if who != "human" or _SCHEDULED.match(text) or _WORK_CHAT.search(text) or _job_chat(event):
        return {}                     # nobody here to tell: a scheduled run, a ring, a job chat
    try:
        import app_setup
        path = app_setup._local_file(PAGE_HELD)
        got = app_setup.read_json(path, {})
        key, day = chat or "this-folder", _page_today()
        me = got.get(key) if isinstance(got.get(key), dict) else {}
        held = int(me.get("held") or 0) if me.get("day") == day else 0
        if held >= PAGE_HOLDS:
            return {}
        got[key] = {"day": day, "held": held + 1}
        app_setup.write_json(path, got)
        if (app_setup.read_json(path, {}).get(key) or {}).get("held") != held + 1:
            return {}                 # the count did not keep: never hold a turn for ever
    except Exception:  # noqa: BLE001
        return {}
    return _page_hold_form(PAGE_OWED, event.get("transcript_path") or "")


def _scheduled_start(event: dict) -> str:
    """A scheduled run of the brief starts with app.py start --scheduled morning_brief, never
    the plain start CLAUDE.md names first (it is read before the prompt file, and CLAUDE.md is
    at its size limit): said beside the run's own first words (review of fix/helpers, item 11)."""
    if (event.get("hook_event_name") or "") != "UserPromptSubmit":
        return ""
    prompt = str(event.get("prompt") or "")
    if not re.match(r"\s*Scheduled run:\s*morning brief\b", prompt, re.I):
        return ""
    return ("This is the morning brief's scheduled run. Start with python3 tools/app.py start "
            "--scheduled morning_brief --on \"<this chat's model>\" instead of the plain start, "
            "and follow its prompt file.")


def _wake_due(event: dict) -> str:
    """The page's Wake link types plain words into a new chat (app_listen.WAKE_PROMPT, never a
    command a person would see: the stranger audit, X-84); this says what they mean."""
    if (event.get("hook_event_name") or "") != "UserPromptSubmit":
        return ""
    try:
        import app_listen
        words = app_listen.WAKE_PROMPT.rstrip(".").lower()
        if words not in " ".join(str(event.get("prompt") or "").lower().split()):
            return ""
        return ("The person opened this chat from their page to look after it. Start with "
                f"{app_listen.WAKE_COMMAND} --on \"<this chat's model>\" --tools \"<browser "
                "tools>\" instead of the plain start, and do what it prints.")
    except Exception:  # noqa: BLE001
        return ""


def _page_due(event: dict) -> str:
    """Said beside the person's own message while this chat owes the page, so the turn
    publishes it before the hold has to."""
    if (event.get("hook_event_name") or "") != "UserPromptSubmit":
        return ""
    prompt = str(event.get("prompt") or "")
    if _SCHEDULED.match(prompt) or _WORK_CHAT.search(prompt) or _job_chat(event):
        return ""
    path = _path()
    if path is None or person.in_example(path):
        return ""
    try:
        import app_setup
        had = bool(app_setup.page_record().get("url"))
    except Exception:  # noqa: BLE001
        had = True
    owed = _page_owed_here(event.get("transcript_path") or "")[1]
    if not had and not owed:
        try:
            if app_setup.page_record().get("url"):
                return PAGE_HEALED
        except Exception:  # noqa: BLE001
            pass
    return PAGE_DUE if owed else ""


def _update_due(event: dict) -> str:
    """The day's update check, said beside the day's first message in any chat, a chat left
    open for weeks included: the line in CLAUDE.md asking for it was missed, and a copy
    stayed on an old version (the maintainer, 2026-11-02: "with ZERO PROMPTING even if its
    the same chat thats been used this entire time"). Files only: the check itself runs in
    the turn, never here, where a prompt hook is cut off after 30 seconds, mid-merge. This is
    the app's one hook, so it says this too, rather than a second hook."""
    if (event.get("hook_event_name") or "") != "UserPromptSubmit":
        return ""
    if _WORK_CHAT.search(str(event.get("prompt") or "")) or _job_chat(event):
        # A chat started for one big job (tools/app.py child_prompt): the chat that answers
        # the page took the day's check, and a job must not take an update part way through.
        return ""
    path = _path()
    if path is None or person.in_example(path):
        return ""                     # the app, before /setup (its start syncs), the example person
    try:
        import sync_app
        # A check tried in the last few hours that could not finish is not asked for again
        # on every message (the stranger audit, X-71).
        return sync_app.HOOK_LINE if sync_app.stale() and sync_app.retry_due() else ""
    except Exception:  # noqa: BLE001  a hook must never break the chat it runs in
        return ""


def _brief_unsent(event: dict) -> str:
    """The person's next message in the chat a brief ran in, where that run's push was not
    sent: said once, where the brief is (tools/brief.py unsent_line). Never on a scheduled
    run's own turn, in the app or for its example person."""
    prompt = str(event.get("prompt") or "")
    if (event.get("hook_event_name") or "") != "UserPromptSubmit" or \
            prompt.lstrip().startswith("Scheduled run:") or "task-notification" in prompt:
        return ""
    path = _path()
    if path is None or person.in_example(path):
        return ""
    try:
        import app_listen
        import brief
        return brief.unsent_line(app_listen.this_chat())
    except Exception:  # noqa: BLE001  a hook must never break the chat it runs in
        return ""


def _with_update(out: dict, due: str) -> dict:
    if not due:
        return out
    if not out:
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": due}}
    spec = out.get("hookSpecificOutput") or {}
    spec["additionalContext"] = (due + "\n\n" + str(spec.get("additionalContext") or "")).strip()
    out["hookSpecificOutput"] = dict(spec, hookEventName="UserPromptSubmit")
    return out


def _cli_hook() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        event = event if isinstance(event, dict) else {}
        if (event.get("hook_event_name") or "") == "PostToolUse":
            # After a read of the page's database, where a copy's settings run this hook on
            # PostToolUse (where a copy's settings do not, chats run app.py versions after each read:
            # page_db.hook_keeps_versions): each record's version, as the read listed it, kept
            # in the file it saved (page_db.keep_listed). Says nothing, holds nothing.
            import page_db
            page_db.keep_listed_event(event)
            return 0
        due = "\n\n".join(x for x in (_update_due(event), _scheduled_start(event) or
                                       _wake_due(event) or _page_due(event)) if x)
        out = _with_update(_with_update(hook(event), _brief_unsent(event)), due)
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
    # --area and --rule are needed for a rule, and not with --about-app (`record` says so).
    r.add_argument("--area", default="")
    r.add_argument("--said", required=True)
    r.add_argument("--rule", default="")
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
    r.add_argument("--via", default="", help="where it was said: \"page tweak\" for the page's box")
    r.add_argument("--output", default="", help="the kind of output it was about: resume, letter, message")
    r.add_argument("--about-app", action="store_true",
                   help="it is about how the app behaves (slow, broken, a button that does "
                        "nothing), not how they want their work done: never kept as a rule, "
                        "routed (an app bug in the maintainer's own copy, else worked around)")
    r.add_argument("--not-about-app", action="store_true",
                   help="it reads as about the app, but it is truly how they want their own "
                        "work done: keep it as a rule")
    bi = sub.add_parser("built-in", help="rules the app now does by itself, judged after an update")
    bi.add_argument("--retire", action="append", default=[], metavar="N=ID",
                    help="entry N is now part of the app, by behaviour ID")
    bi.add_argument("--done", action="store_true",
                    help="every behaviour judged: record it, so this happens once")
    bi.add_argument("--all", action="store_true", help="every behaviour the app does by itself")
    ab = sub.add_parser("app-bugs", help="complaints about the app kept for its maker")
    ab.add_argument("--all", action="store_true")
    ab.add_argument("--close", type=int, action="append", default=[])
    k = sub.add_parser("skip")
    k.add_argument("--said", required=True)
    k.add_argument("--why", required=True)
    k.add_argument("--via", default="")
    k.add_argument("--output", default="")
    nt = sub.add_parser("note", help="words typed into the page's Tweak box, held like any reaction")
    nt.add_argument("--said", required=True)
    nt.add_argument("--output", default="")
    sub.add_parser("pending")
    t = sub.add_parser("retire")
    t.add_argument("n", type=int, nargs="+")
    t.add_argument("--why", default="", help="kept with it, and shown on their page")
    t = sub.add_parser("ask")
    t.add_argument("older", type=int)
    t.add_argument("later", type=int)
    t = sub.add_parser("restore")
    t.add_argument("n", type=int, nargs="+")
    t = sub.add_parser("tidy")
    t.add_argument("--dry", action="store_true")
    t.add_argument("--clashes", action="store_true")
    t.add_argument("--reviewed", action="store_true")
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
        want = area_of(a.area) if a.area else ""
        for i, row in enumerate(load(), 1):
            if want and row.get("area") != want:
                continue
            later = over.get(_key(row))
            status = (f"overruled by {later.get('date')}" if later
                      else row.get("status", "active"))
            print(f"{i:3}. [{status}] {row.get('date')} {row.get('area')}: "
                  f"{row.get('rule')}  (said: \"{row.get('said')}\")")
    elif a.cmd == "record" and a.about_app:
        got = route_about_app(a.said)
        if got["route"] == "maintainer":
            print("learned: not kept as a rule: it is about how the app behaves, and this is the "
                  "app maker's own copy, so it is kept as an app bug (python3 tools/learned.py "
                  "app-bugs lists them).")
            print("Say to them, in one line: That one's the app's, not a rule of yours: I've "
                  "kept it as an app bug to fix" + (f" (open it on the app's page: {got['link']})"
                                                   if got.get("link") else "")
                  + ", and worked round it for now.")
        else:
            print("learned: not kept as a rule: it is about how the app behaves, not how they "
                  "want their work done. Work round it for them now, the best honest way the "
                  "app allows, and never trouble them with the app's problems (CLAUDE.md, "
                  "\"App-owned files and personal files\").")
        print("Then work round it in this turn; nothing is waiting on it.")
    elif a.cmd == "record" and not a.not_about_app and about_app(a.said + " \n " + a.rule):
        cue = about_app(a.said + " \n " + a.rule)
        raise SystemExit(
            f"learned: not recorded: \"{cue}\" reads as about how the app behaves, not how "
            "they want their work done, and a complaint about the app is never a rule of "
            "theirs. If it is about the app: python3 tools/learned.py record --about-app "
            "--said \"<their words>\" (it routes it and clears it from this turn), then work "
            "round it. If it says how they want their own work done, or you are not sure, "
            "it is theirs: run the same record again with --not-about-app.")
    elif a.cmd == "record":
        e = record(a.area, a.said, a.rule, a.applied_to, a.never_say, overrides=a.overrides,
                   replaces=a.replaces, length=a.length, via=a.via, output=a.output)
        print(f"learned: {e['area']}: {e['rule']}")
        for setting, value in e.get("set") or ():
            print(f"  set: {setting} = {json.dumps(value)} (the setting this rule is, written now)")
        for kind, per in (e.get("length") or {}).items():
            print("  length: " + ", ".join(f"{kind} to {'any reader' if who == 'any' else who}"
                                           f" runs to about {n} words" for who, n in per.items()))
        print(f"Say to the person, in one line: From now on, {e['rule']} (you said: "
              f"\"{e['said'][:160]}\").")
        # A record left unsaved held the end of a cloud chat's turn ("uncommitted changes"),
        # 2026-10-30: it goes with this turn's work, saved the one way.
        print("Save it with this turn's work: python3 tools/save_state.py, then commit "
              "(RUNBOOK.md, \"4. Record and persist, then land on master\").")
        if e.get("overrides"):
            print(f"  outranks the check(s): {', '.join(e['overrides'])}")
        for phrase, setting, line in e.get("own_overlaps") or ():
            print(f"  WARNING: never saying \"{phrase}\" refuses your own {setting} "
                  f"(\"{' '.join(line.split())[:90]}\"), so every draft using it is refused. "
                  "Capitalised as a sentence opens (\"Love to hear\"), it bans only the "
                  "clipped sentence; or change that line.")
        # The newest thing they said stands, with nothing asked: each earlier rule it repeats
        # or contradicts is retired, named with its date, and can be brought back.
        for n, old, why in e.get("replaced") or ():
            print(f"  Replaced entry {n} ({old.get('date')}: {old.get('rule')}): {why}. "
                  f"Back if it should not have gone: python3 tools/learned.py restore {n}")
        for n, old, why in e["conflicts"]:
            where = f"entry {n}" if n else "a rule in profile/CLAUDE.md"
            print(f"  MAY CONTRADICT {where} ({old.get('date')}: {old.get('rule')}): {why}.")
        if e["conflicts"]:
            # The newest thing they said stands; whether this one truly undoes the older is
            # judged here, by the chat, never asked (2026-10-31).
            print("Judge each yourself: where the new rule plainly reverses the older, the newest "
                  "stands, so retire it (python3 tools/learned.py retire <n>, or change that line "
                  "in profile/CLAUDE.md) and say so in one line; where they only share words, "
                  "leave it. Only where you truly cannot tell and it changes what is drafted: "
                  "python3 tools/learned.py ask <older> <newer> puts one question on their page "
                  "(it refuses while one waits or one was asked lately; then keep both).")
    elif a.cmd == "skip":
        skip(a.said, a.why, via=a.via, output=a.output)
        print(f"learned: not a rule ({a.why}); {len(pending())} reaction(s) still unrecorded")
    elif a.cmd == "note":
        got = note(a.said, a.output)
        print("learned: held like any reaction: record it (learned.py record ... --via \"page "
              "tweak\") or skip it (learned.py skip ... --via \"page tweak\") before the turn "
              "ends" if got else "learned: already on the list")
    elif a.cmd == "pending":
        rows = pending()
        for r in rows:
            print(f"- {r.get('at')}: \"{r.get('said')}\"")
        print(f"{len(rows)} reaction(s) not recorded yet")
        return 1 if rows else 0
    elif a.cmd == "retire":
        for n in a.n:
            e = retire(n, a.why)
            print(f"retired: {e.get('rule')}")
    elif a.cmd == "ask":
        why = ask(a.older, a.later)
        print("learned: asked on their page; nothing else to say about it" if not why else
              f"learned: not asked: {why}")
    elif a.cmd == "restore":
        for n in a.n:
            e = restore(n)
            print(f"back in force: {e.get('rule')}")
    elif a.cmd == "tidy" and a.reviewed:
        print(f"learned: rules judged on {reviewed(mark=True)}")
    elif a.cmd == "tidy" and a.clashes:
        got = clashes()
        for d in got:
            print(f"  entry {d['n']} ({d['date']}: {d['rule']}) and the later entry {d['later']} "
                  f"({d['later_rule']}): {d['why']}")
        print(f"learned: {len(got)} pair(s) to judge. For each, retire the older only where the "
              "later plainly reverses it (python3 tools/learned.py retire <n>); where they only "
              "share words, or you are not sure, leave both: a rule wrongly put away is worse "
              "than two kept. At most one pair, the one that most changes what is drafted and "
              "you truly cannot call, may go to the person: python3 tools/learned.py ask <older> "
              "<newer>. Then python3 tools/learned.py tidy --reviewed"
              if got else "learned: nothing to judge")
    elif a.cmd == "tidy":
        got = tidy(dry=a.dry)
        for d in got:
            print(f"  entry {d['n']} ({d['rule']}) {'would be' if a.dry else ''} retired for entry "
                  f"{d['for']}: {d['why']}")
        print(f"learned: {len(got)} rule(s) {'to tidy' if a.dry else 'tidied'}" if got else
              "learned: nothing to tidy")
    elif a.cmd == "built-in" and a.all:
        for b in BUILT_IN:
            print(f"{b['id']} (since {b['version']}): {b['does']}")
    elif a.cmd == "built-in" and (a.retire or a.done):
        for spec in a.retire:
            n, _, bid = str(spec).partition("=")
            if not n.strip().isdigit() or not bid.strip():
                raise SystemExit(f"learned: --retire {spec!r}; give it as <n>=<behaviour id>")
            e = retire_built_in(int(n), bid.strip())
            print(f"{NOW_PART}: {e.get('rule')}")
        if a.done:
            _n, line = built_in_done()
            print("learned: every behaviour the app now does by itself is checked against "
                  "their rules; this is not asked again until the app does something new.")
            print(f"Say to the person, in one line: {line}" if line else
                  "Nothing to say to the person: none of their rules was put away.")
    elif a.cmd == "built-in":
        got = built_in_candidates()
        if not got:
            built_in_done()
            print("learned: none of their rules repeats what the app now does by itself")
        for n, e, b in got:
            extra = []
            if e.get("never_say"):
                extra.append("bans " + ", ".join('"%s"' % p for p in e["never_say"]))
            if e.get("applied_to"):
                extra.append("shaped " + ", ".join(e["applied_to"]))
            print(f"  entry {n} ({e.get('date')}, {e.get('area')}): {e.get('rule')} (said: "
                  f"\"{' '.join(str(e.get('said') or '').split())[:120]}\")"
                  + (f" [{'; '.join(extra)}]" if extra else ""))
            print(f"    may be {b['id']} (since {b['version']}): {b['does']}")
        if got:
            print(f"learned: {len(got)} rule(s) to judge. Put one away only where what the app "
                  "now does covers all of it; a rule that asks for more, or for something "
                  "different (its own wording, a ban, a setting it shaped), stays. For each "
                  "covered: python3 tools/learned.py built-in --retire <n>=<id>. Then, judged or "
                  "not, python3 tools/learned.py built-in --done, and say the one line it prints.")
    elif a.cmd == "app-bugs" and a.close:
        for n in a.close:
            got = close_app_bug(n)
            print(f"closed: {got.get('said')}")
    elif a.cmd == "app-bugs":
        shown = 0
        for i, r in enumerate(app_bugs(include_closed=True), 1):   # numbered as --close reads
            if a.all or r.get("status", "open") == "open":
                shown += 1
                print(f"{i:3}. [{r.get('status', 'open')}] {r.get('date')}: \"{r.get('said')}\"")
        print(f"{shown} app bug(s)" + ("" if a.all else " open"))
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
