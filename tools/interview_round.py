#!/usr/bin/env python3
"""One upcoming interview round, as the page practises it (issue 367).

The pack (`tools/interview_pack.py`) is the document; this is the same round as parts the
page can drill: who is in the room and what each is likely to dig into, a cheat sheet that
fits one screen, the person's stories and every number they can say, flashcards built from
the likely questions with follow-ups three deep on every technical one, the day itself when
the round is in person, cases to practise, and how ready they are.

Everything here is read from what the search already holds: the profile
(`01-candidate-profile.md`, the source of truth, and the stories file), the round's record
(`outcome.md`), the pack, the logistics the person gave (`interview_logistics.json`, kept by
`interview_pack.py logistics`), and the marks the person left on the page (the page
database's `practice` collection). Nothing is invented: what is not held is null, and the
pack lists it as "FILL IN: <the question to answer>".

Spaced repetition (the page mirrors this rule; `schedule` is the one place it is written):
the intervals are 1, 3, 7 and 14 days. A card never marked is due now. "got" moves it to
the next interval (the first "got" to 1 day, then 3, 7, 14, and 14 after that), "shaky"
keeps the interval it is on (a first "shaky" is 1 day), "missed" puts it back to 1 day. It
is next due that many days after the mark.

    python3 tools/interview_round.py schedule '<marks as JSON>'
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ------------------------------------------------------------------ spaced repetition

INTERVALS = (1, 3, 7, 14)
MARKS = ("got", "shaky", "missed")
PRACTICE = "practice"          # the page database's collection
MOCK, CASE = "mock", "case"    # the `kind` of a practice doc that is not a card's marks


def _when(value):
    """A mark's time as an aware datetime, or None."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            t = dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time())
        except ValueError:
            return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _iso(t) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_step(step, mark):
    """The interval a card is on after one mark, as an index into INTERVALS. `step` is None
    for a card never marked."""
    last = len(INTERVALS) - 1
    if mark == "got":
        return 0 if step is None else min(step + 1, last)
    if mark == "shaky":
        return 0 if step is None else step
    return 0                                   # missed, or anything unknown: back to 1 day


def schedule(marks) -> dict:
    """{"step": index or None, "interval": days or None, "due": iso or None, "last": the
    latest mark or None, "count": marks read} from a card's marks, read oldest first. A card
    never marked is due now (`due` None)."""
    rows = []
    for m in marks or ():
        if not isinstance(m, dict) or str(m.get("mark") or "") not in MARKS:
            continue
        t = _when(m.get("at"))
        if t is not None:
            rows.append((t, m["mark"]))
    rows.sort(key=lambda r: r[0])
    step, last_t, last = None, None, None
    for t, mark in rows:
        step, last_t, last = next_step(step, mark), t, mark
    if step is None:
        return {"step": None, "interval": None, "due": None, "last": None, "count": 0}
    days = INTERVALS[step]
    return {"step": step, "interval": days, "due": _iso(last_t + dt.timedelta(days=days)),
            "last": last, "count": len(rows)}


def is_due(sched: dict, now) -> bool:
    if not sched.get("due"):
        return True
    t = _when(sched["due"])
    return t is None or t <= (now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc))


# ------------------------------------------------------------------ the page's marks

def _data(doc):
    return doc.get("data") if isinstance(doc, dict) and isinstance(doc.get("data"), dict) else doc


def docs_from(db) -> list:
    """The practice docs from a page dump (page_db.load) or a list of docs, as plain dicts."""
    if isinstance(db, dict):
        coll = db.get(PRACTICE) if PRACTICE in db else db
        values = coll.values() if isinstance(coll, dict) else []
    else:
        values = db or []
    return [d for d in (_data(v) for v in values) if isinstance(d, dict)]


def mirror_docs() -> list:
    """The practice docs this copy kept from the page's last read (page_reads' mirror), for
    a command run outside a page update (the pack, the brief). [] when there are none."""
    try:
        import page_reads
        folder = os.path.join(page_reads.mirror_dir(), PRACTICE)
    except Exception:  # noqa: BLE001  no copy to read: nothing practised that it knows of
        return []
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, ValueError):
            continue
        got = _data(got)
        if isinstance(got, dict):
            out.append(got)
    return out


def for_interview(docs, interview: str) -> dict:
    """{"cards": {card id: [marks]}, "mocks": n, "cases": n} for one interview's docs."""
    cards, mocks, cases = {}, 0, 0
    for d in docs or ():
        if str(d.get("interview") or "") != interview:
            continue
        kind = str(d.get("kind") or "")
        if kind == MOCK:
            mocks += 1
        elif kind == CASE:
            cases += 1
        elif d.get("card"):
            cards.setdefault(str(d["card"]), []).extend(
                m for m in (d.get("marks") or []) if isinstance(m, dict))
    return {"cards": cards, "mocks": mocks, "cases": cases}


def interview_id(company, role, rid="") -> str:
    """The page's id for an application's interviews: "int-" and the tracker row's id."""
    if rid:
        return "int-" + str(rid)[4:] if str(rid).startswith("app-") else "int-" + str(rid)
    import app_model
    return "int-" + (app_model.row_slug(company, role) or "row")


def card_id(interview: str, question: str) -> str:
    """A card's id, stable while the question's words are the same: the interview's id and
    a short hash of the question as the bank normalizes it."""
    import what_works
    h = hashlib.sha1(what_works._norm(question).encode("utf-8")).hexdigest()[:10]
    return "%s~q%s" % (interview, h)


def practice_rank(sched: dict, now) -> int:
    """Where a card falls in practice, as the page orders it (practiseDue in the page's own
    code, which mirrors this): missed first, then any card due again, then shaky ones not due
    yet, then the ones never practised, then the ones got and not due."""
    if sched["last"] == "missed":
        return 0
    if sched["last"] is not None and is_due(sched, now):
        return 1
    if sched["last"] == "shaky":
        return 2
    if sched["last"] is None:
        return 3
    return 4


def order_cards(cards, marks_by_card: dict, now) -> list:
    """The cards in the order to practise them (practice_rank), each carrying its schedule;
    cards that rank alike keep the pack's order."""
    out = []
    for i, c in enumerate(cards):
        sched = schedule(marks_by_card.get(c["id"]) or [])
        c = dict(c, last=sched["last"], due=sched["due"])
        rank = practice_rank(sched, now)
        out.append((rank, i, c))
    return [c for _r, _i, c in sorted(out, key=lambda x: (x[0], x[1]))]


def struggled(marks_by_card: dict) -> dict:
    """{card id: "shaky" | "missed"} for the cards whose latest mark was not "got"."""
    out = {}
    for cid, marks in (marks_by_card or {}).items():
        last = schedule(marks)["last"]
        if last in ("shaky", "missed"):
            out[cid] = last
    return out


# ------------------------------------------------------------------ the profile

_NUM = re.compile(r"(?:[£$€]|(?:CA|US|GBP|CAD|USD)\$?\s?)?~?\d[\d,.]*\+?\s?(?:%|k\b|K\b|M\b|B\b|bn\b|x\b|"
                  r"(?:million|billion|thousand)\b)?(?:\s+(?:to|-)\s+~?\d[\d,.]*\s?%?)?")
# A number that is a date or a year range, not a metric.
_YEARS = re.compile(r"^(?:19|20)\d{2}$")
_UNIT = re.compile(r"^\s*([A-Za-z][\w-]*(?:\s+(?!(?:and|or|by|over|of|to|in|on|at|for|with|from|"
                   r"against|the|a|an|per|into|across)\b)[a-z][\w-]*)?)")


def _roles(profile_text=None) -> list:
    """[{company, title, bullets}] for every role under Professional Experience, every
    default bullet (not only the first three the call prep takes)."""
    import profile_facts
    lines = profile_text.splitlines() if profile_text is not None else profile_facts._read()
    secs = profile_facts.sections(lines)
    out = []
    for heading in secs:
        m = profile_facts._ROLE_HEADING.match(heading)
        if not m or heading not in profile_facts._experience_headings(secs, lines):
            continue
        bullets = profile_facts._bullets(secs[heading])
        if bullets:
            out.append({"company": profile_facts._plain(m.group("company")),
                        "title": profile_facts._plain(m.group("title")), "bullets": bullets})
    return out


def _where(role) -> str:
    return "%s at %s" % (role["title"], role["company"])


def numbers(profile_text=None) -> list:
    """Every metric the profile's experience holds, once each: [{value, what, source}]."""
    out, seen = [], set()
    for role in _roles(profile_text):
        for b in role["bullets"]:
            for m in _NUM.finditer(b):
                value = m.group(0).strip().rstrip(".,")
                bare = re.sub(r"[^\d]", "", value)
                if not bare or _YEARS.match(value) or (len(bare) == 1 and not re.search(
                        r"[%kKMBx+£$€]|million|billion", value)):
                    # A lone digit ("3 clients", "6 distribution centres") is still a number
                    # to say: kept with the word after it.
                    unit = _UNIT.match(b[m.end():])
                    if not bare or _YEARS.match(value) or not unit:
                        continue
                if not re.search(r"[%a-zA-Z£$€]", value):
                    unit = _UNIT.match(b[m.end():])
                    if unit:
                        value = "%s %s" % (value, unit.group(1))
                key = value.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"value": value, "what": _clip(b, 140), "source": _where(role)})
    return out


def _clip(text, n) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


STORY_MIN, STORY_MAX = 6, 8


def _figures(text) -> set:
    return {re.sub(r"[^\d.]", "", m.group(0)) for m in _NUM.finditer(str(text or ""))
            if len(re.sub(r"[^\d]", "", m.group(0))) > 1}


def stories(profile_text=None, stories_list=None) -> list:
    """The person's stories, six to eight of them: the STAR stories they wrote first, each
    tied to the profile line it is about, then the profile's own lines that carry a result,
    each marked with what is still theirs to fill in. [{id, title, trigger, bullets, source,
    use_for, methods}]."""
    import interview_pack
    roles = _roles(profile_text)
    lines = [(r, b) for r in roles for b in r["bullets"]]
    written = interview_pack.stories() if stories_list is None else stories_list
    out, used = [], set()
    for st in written[:STORY_MAX]:
        star = st.get("star") or {}
        text = " ".join(star.get(k, "") for k in "STAR")
        figs = _figures(text)
        best = None
        for i, (_r, b) in enumerate(lines):
            score = len(figs & _figures(b)) * 2 + interview_pack.similar(text, b)
            if score > 0.25 and (best is None or score > best[0]):
                best = (score, i)
        if best is not None:
            used.add(best[1])
            r, b = lines[best[1]]
            source = "%s: %s" % (_where(r), _clip(b, 90))
        else:
            source = "your stories file: %s (FILL IN: which role was this?)" % st["title"]
        bullets = [("%s: %s" % (w, star[k])) for k, w in (("S", "Situation"), ("T", "Task"),
                                                          ("A", "What you did"), ("R", "Result"))
                   if star.get(k)]
        out.append({"id": _story_id(st["title"]), "title": st["title"],
                    "trigger": _trigger(star.get("R") or text),
                    "bullets": bullets, "source": source, "use_for": list(st.get("use_for") or []),
                    "methods": interview_pack.recorded_methods(text, "\n".join(
                        b for _r, b in lines))})
    # The profile's lines with a result, the most recent role first, until there are enough.
    for i, (r, b) in enumerate(lines):
        if len(out) >= STORY_MAX or (len(out) >= STORY_MIN and not _figures(b)):
            continue
        if i in used or not _figures(b):
            continue
        title = _clip(re.split(r"[,;:]", b)[0], 70)
        out.append({"id": _story_id(b), "title": title, "trigger": _trigger(b),
                    "bullets": ["Result: %s" % b,
                                "FILL IN: what was the situation before, and who needed it?",
                                "FILL IN: what did you do yourself, step by step?"],
                    "source": "%s: %s" % (_where(r), _clip(b, 90)), "use_for": [],
                    "methods": interview_pack.methods_in(b)})
    return out[:STORY_MAX]


def _story_id(title) -> str:
    return "story-" + hashlib.sha1(str(title).lower().encode("utf-8")).hexdigest()[:8]


def _trigger(text) -> str:
    """The few words that bring a story back: its first figure and what it is of, else its
    first words."""
    t = " ".join(str(text or "").split())
    m = _NUM.search(t)
    if m and len(re.sub(r"[^\d]", "", m.group(0))) > 0:
        after = _UNIT.match(t[m.end():])
        return _clip((m.group(0).strip() + (" " + after.group(1) if after else "")), 40)
    return _clip(" ".join(t.split()[:6]), 40).rstrip(".,;")


# ------------------------------------------------------------------ cards and follow-ups

FILL_IN = "FILL IN: %s"
NO_METHOD_ASK = ("which model or method did you use for this, and what did you compare it "
                 "against?")


def follow_chain(question, methods=()) -> list:
    """The follow-ups to prepare under a technical question, three deep on every chain:
    [{question, answer, follow}]. The third level is asked about the method the profile
    records for the work; where it records none, its answer is a FILL IN."""
    import interview_pack
    out = []
    for first, second, third in interview_pack.tech_follow_chains(question, methods):
        gap = not methods
        out.append({"question": first, "answer": None, "follow": [
            {"question": second, "answer": None, "follow": [
                {"question": third, "answer": (FILL_IN % NO_METHOD_ASK) if gap else None,
                 "follow": []}]}]})
    return out


def _depth(nodes) -> int:
    return max((1 + _depth(n.get("follow") or []) for n in nodes or ()), default=0)


def _sentences(text) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "")) if s.strip()]


def cards(reading, interview: str, story_list=()) -> list:
    """Practice flashcards from the pack's likely questions: [{id, q, trigger, bullets,
    follow}], the id stable for the question's words. What to say is the person's written
    answer, else the notes it is said from, else a FILL IN; every technical card is three
    follow-ups deep."""
    import interview_pack
    out = []
    for q in (reading or {}).get("questions") or []:
        question = q.get("question") or ""
        if not question:
            continue
        st = _story_for(question, story_list)
        if q.get("answer"):
            bullets = _sentences(q["answer"])[:5]
        else:
            bullets = [n for n in (q.get("notes") or []) if n][:3]
        if not bullets and st:
            bullets = list(st.get("bullets") or [])[:4]
        if not bullets:
            bullets = [FILL_IN % ("what would you say to \"%s\", in a sentence or two?" % question)]
        follow = list(q.get("follow") or [])
        if interview_pack.technical(question) and _depth(follow) < 3:
            follow = follow + [n for n in follow_chain(question, (st or {}).get("methods") or ())
                               if interview_pack.what_works._norm(n["question"]) not in
                               {interview_pack.what_works._norm(f.get("question")) for f in follow}]
        trigger = q.get("cue") or (st or {}).get("title") or _clip(question, 40)
        out.append({"id": card_id(interview, question), "q": question, "trigger": trigger,
                    "bullets": bullets, "follow": _nested(follow),
                    "section": "Your answers" if q.get("added") else "Likely questions",
                    "why": q.get("why") or None,
                    **({"story": st["id"]} if st else {})})
    return out


def _story_for(question, story_list):
    """The story a question is best answered with: by its `Use for:` tags, else the one whose
    own words share the most with the question, or None."""
    import interview_pack
    tagged = [s for s in story_list or () if s.get("use_for")]
    st, _score = interview_pack.best_story(question, tagged) if tagged else (None, 0)
    if st is not None:
        return st
    asked = interview_pack._words(question) - _ASKING
    if not asked:
        return None
    scored = [(len(asked & interview_pack._words(" ".join(
                  [s["title"]] + list(s.get("use_for") or []) + list(s.get("bullets") or []))))
               / len(asked), i, s) for i, s in enumerate(story_list or ())]
    best = max(scored, key=lambda x: (x[0], -x[1]), default=None)
    return best[2] if best and best[0] >= STORY_WORDS else None


STORY_WORDS = 0.5
# Words that ask, not what is asked about.
_ASKING = frozenset("tell describe walk talk give time example check".split())


def _nested(nodes) -> list:
    return [{"question": n.get("question"), "answer": n.get("answer"),
             "follow": _nested(n.get("follow") or [])} for n in nodes or ()]


# ------------------------------------------------------------------ who, format, in person

_IN_PERSON = re.compile(r"\b(?:in[- ]person|on[- ]?site|onsite|at (?:the|their|our) office|"
                        r"in the office|office visit|face[- ]to[- ]face|super ?day|assessment "
                        r"centre|assessment center)\b", re.I)
_REMOTE = re.compile(r"\b(?:video|zoom|teams|google meet|meet|phone|call|virtual|remote|online)\b",
                     re.I)


def in_person(stage: dict, format_text="", logistics=None) -> bool:
    """Is this round in the room? Said so by its record, its format or its label, or a place
    to go to recorded for it."""
    if logistics and logistics.get("address"):
        return True
    words = " ".join(str(x or "") for x in (format_text, stage.get("label"), stage.get("place"),
                                            stage.get("details")))
    return bool(_IN_PERSON.search(words))


def who(with_text, step="", outcome="") -> list:
    """[{name, role, probes}] for who the round is with: each named person or title, and what
    they are likely to dig into, from their kind of role and this round (interview_pack's
    ANGLES and WANT), and what an earlier round's record says they pushed on."""
    import interview_pack
    out = []
    for w in interview_pack._interviewers({"with": with_text or ""}):
        title = w.get("title") or ""
        kind = interview_pack._kind(title or w.get("name") or "")
        listens = dict(zip(interview_pack.KINDS, interview_pack.ANGLES))[kind][1]
        probes = [listens[:1].upper() + listens[1:]]
        if interview_pack.WANT.get(kind):
            probes.append("Wants to hear " + interview_pack.WANT[kind])
        if interview_pack.STAGE_ANGLE.get(step):
            probes.append("In this round: " + interview_pack.STAGE_ANGLE[step])
        first = (w.get("name") or "").split()
        if first and len(first[0]) >= 3:
            rx = re.compile(r"\b%s\b" % re.escape(first[0]), re.I)
            probes += ["Last time: " + _clip(ln, 160) for _h, ln in interview_pack._record(outcome)
                       if rx.search(ln)][:2]
        said = [p[len("Last time: "):] for p in probes if p.startswith("Last time: ")]
        out.append({"name": w.get("name") or title, "role": title or None, "probes": probes,
                    "kind": kind, "about": "; ".join(said) or None})
    return out


def likely_asker(question, who_list) -> str | None:
    """Who in the room is likely to ask a question: the one person there is, a practitioner
    or manager for a technical one, a senior leader or the recruiter for the rest, else
    "Either". None when nobody is named."""
    import interview_pack
    if not who_list:
        return None
    if len(who_list) == 1:
        return who_list[0]["name"]
    want = ("practitioner", "manager") if interview_pack.technical(question) else \
        ("senior", "screener", "manager")
    for kind in want:
        hit = [w for w in who_list if w.get("kind") == kind]
        if len(hit) == 1:
            return hit[0]["name"]
    return "Either"


# ------------------------------------------------------------------ logistics

LOGISTICS = "interview_logistics.json"
LOGISTICS_FIELDS = ("address", "entrance", "floor", "travel", "arrive_by", "bring", "wear",
                    "timeline", "time_zone", "confirmed")


def logistics_path(folder) -> str:
    return os.path.join(folder, LOGISTICS)


def _load_all(folder) -> dict:
    try:
        with open(logistics_path(folder), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def load_logistics(folder, stage_label) -> dict:
    """What the person told about getting to this round, {} when nothing."""
    import interview_pack
    rounds = _load_all(folder).get("rounds") or {}
    for label, got in rounds.items():
        if isinstance(got, dict) and (label.lower() == str(stage_label or "").lower()
                                      or interview_pack._same_round(label, stage_label)):
            return got
    return {}


def save_logistics(folder, stage_label, today="", **fields) -> dict:
    """Records what is given for this round (a value None leaves the one held), and returns
    the round's whole record. `bring` adds to what is held; `timeline` is [{at, what}]."""
    whole = _load_all(folder)
    rounds = whole.setdefault("rounds", {})
    key = next((k for k in rounds if k.lower() == str(stage_label).lower()), str(stage_label))
    cur = dict(rounds.get(key) or {})
    for k, v in fields.items():
        if k not in LOGISTICS_FIELDS or v is None:
            continue
        if k == "bring":
            cur["bring"] = list(dict.fromkeys(list(cur.get("bring") or []) + list(v)))
        elif k == "timeline":
            cur["timeline"] = list(cur.get("timeline") or []) + [t for t in v if isinstance(t, dict)]
        elif k == "confirmed":
            cur["confirmed"] = bool(v)
        else:
            cur[k] = str(v).strip() or None
    if today:
        cur["updated"] = str(today)
    rounds[key] = cur
    os.makedirs(folder, exist_ok=True)
    with open(logistics_path(folder), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(whole, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return cur


# What to wear, by the kind of employer (interview_pack.EMPLOYER_TYPES): advice, said as a
# suggestion, never as something the employer said.
WEAR = {"bank": "a suit or a smart jacket and trousers or skirt: banks still read it as respect",
        "consulting": "business wear, jacket on: consultancies dress for clients",
        "public sector": "smart: a jacket, a tie optional",
        "startup": "smart casual, a notch above what the team wears day to day",
        "product": "smart casual, a notch above what the team wears day to day"}
WEAR_ANY = "smart casual, a notch above what the team wears day to day"
BRING = ("Photo ID for the front desk", "Two printed copies of the resume you sent",
         "A pen and a notebook, for a paper case or the questions you ask",
         "The names of who you are meeting", "Water, and something to eat before")
WHITEBOARD = ("Say the question back in your own words, and write it at the top",
              "Ask two or three questions about the goal and the data before you draw anything",
              "Lay out your approach as three or four boxes first, then go into one",
              "Write the numbers big and round; say each sum out loud as you do it",
              "Stop at the end and say what you'd check next, and what could make you wrong")
FINAL_FIVE = ("Phone on silent and away; bag down, water within reach",
              "Read your cheat sheet once: the three stories and the numbers",
              "Say your ninety-second answer to \"tell me about yourself\" once, quietly",
              "Slow breath out, longer than in, three times",
              "Your first line ready: thank them for the time, and say you've been looking "
              "forward to it")
DEBRIEF = ("Within the hour, two minutes: each question you were asked, whether it landed, and "
           "what you'd change. Tell Claude, and it is recorded for the next round.")


def _minus(clock, minutes) -> str | None:
    m = re.match(r"^(\d{1,2})[:.](\d{2})$", str(clock or "").strip())
    if not m:
        return None
    t = dt.datetime(2000, 1, 1, int(m.group(1)), int(m.group(2))) - dt.timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def logistics(stage: dict, held: dict, etype="", home_zone="") -> dict:
    """The day as the page draws it: what the person told, advice where advice fits (what to
    bring and wear, the whiteboard, the last five minutes), and None where only they or the
    employer know (the address, the entrance, the floor, the travel)."""
    held = dict(held or {})
    clock = str(stage.get("time") or "")
    arrive = held.get("arrive_by") or _minus(clock, 15)
    zone = held.get("time_zone") or str(stage.get("zone") or "") or None
    timeline = [t for t in held.get("timeline") or [] if isinstance(t, dict)]
    if not timeline:
        timeline = [{"at": "The day before", "what": "Plan the route and the time it takes, lay "
                     "out what to wear, read your cheat sheet once, and sleep"},
                    {"at": _minus(arrive, 60) if arrive else "Two hours before",
                     "what": "Eat, then leave with time to spare for a late train"},
                    {"at": arrive or "Fifteen minutes before",
                     "what": "Arrive, find the entrance, sign in"},
                    {"at": clock or "The start", "what": "The interview"},
                    {"at": "Within the hour after", "what": DEBRIEF}]
        if zone and home_zone and zone != home_zone:
            timeline.insert(0, {"at": "Three days before", "what": "Another time zone (%s): "
                                "move your sleep an hour a day toward it, and keep the "
                                "interview's time in that zone in your calendar" % zone})
    return {"address": held.get("address") or None, "entrance": held.get("entrance") or None,
            "floor": held.get("floor") or None, "travel": held.get("travel") or None,
            "arrive_by": arrive, "bring": list(held.get("bring") or BRING),
            "wear": held.get("wear") or "Suggested: " + WEAR.get(etype, WEAR_ANY),
            "timeline": timeline, "time_zone": zone, "final_five": list(FINAL_FIVE),
            "whiteboard": list(WHITEBOARD), "confirmed": bool(held.get("confirmed"))}


UNKNOWN_ASK = {"address": "what is the address of the building?",
               "entrance": "which entrance, and who do you ask for at the desk?",
               "floor": "which floor or room?",
               "travel": "how will you get there, and how long does it take?",
               "arrive_by": "what time should you arrive by?"}


def unknowns(day: dict) -> list:
    """The logistics only the person can give, as FILL IN lines with the question to answer."""
    return [FILL_IN % q for k, q in UNKNOWN_ASK.items() if not day.get(k)]


def on_the_day_lines(day: dict) -> list:
    """The pack's "On the day" section, from `logistics`."""
    out = []
    place = ", ".join(x for x in (day.get("address"), day.get("entrance"), day.get("floor")) if x)
    out.append("- **Where:** %s" % (place or "not given yet"))
    out.append("- **Getting there:** %s" % (day.get("travel") or "not given yet"))
    out.append("- **Arrive by:** %s%s" % (day.get("arrive_by") or "not given yet",
                                          " (%s)" % day["time_zone"] if day.get("time_zone") else ""))
    out += ["  - " + u for u in unknowns(day)]
    if not day.get("confirmed"):
        out.append("  - Not confirmed yet: once you have checked these with the invite, tell "
                   "Claude and it marks them confirmed.")
    out.append("- **Bring:** " + "; ".join(day.get("bring") or []))
    out.append("- **Wear:** " + str(day.get("wear") or ""))
    out.append("- **The day, in order:**")
    out += ["  - %s: %s" % (t.get("at"), t.get("what")) for t in day.get("timeline") or []]
    out.append("- **A whiteboard or a paper case:**")
    out += ["  - " + x for x in day.get("whiteboard") or []]
    out.append("- **The last five minutes:**")
    out += ["  - " + x for x in day.get("final_five") or []]
    out.append("- **After:** " + DEBRIEF)
    return out


# ------------------------------------------------------------------ cases

CASE_KINDS = {"bank": "finance", "consulting": "consulting", "product": "analytics",
              "startup": "analytics", "public sector": "general"}


def cases_for(kind, text="") -> list:
    """The cases to practise for this kind of employer, from tools/interview_cases.py when it
    is there, else []. Its own reading of the employer and role (`kind_of`) first, then the
    kind of employer this file knows."""
    try:
        import interview_cases
        kind_of = getattr(interview_cases, "kind_of", None)
        named = kind_of(text) if kind_of and text else ""
        got = interview_cases.cases_for(str(named or CASE_KINDS.get(kind, "general")))
        return [c for c in got or [] if isinstance(c, dict)]
    except Exception:  # noqa: BLE001  no cases module, or none for this kind
        return []


# ------------------------------------------------------------------ readiness

READY_WEIGHTS = {"cards": 55, "mocks": 20, "cases": 10, "logistics": 15}


def readiness(card_list, marks_by_card, mocks=0, cases_done=0, cases_total=0, on_site=False,
              confirmed=False, now=None) -> dict:
    """{score 0-100, practised [got, total], cases_done, mocks_done, logistics_confirmed,
    next}: how ready the person is, from what they practised on the page. Cards count most;
    a mock and a case when there are cases; the logistics only for a round in the room."""
    now = now or dt.datetime.now(dt.timezone.utc)
    total = len(card_list)
    scheds = {c["id"]: schedule(marks_by_card.get(c["id"]) or []) for c in card_list}
    got = sum(1 for s in scheds.values() if s["last"] == "got")
    shaky = [c for c in card_list if scheds[c["id"]]["last"] in ("shaky", "missed")]
    untried = [c for c in card_list if scheds[c["id"]]["last"] is None]
    due = [c for c in card_list if scheds[c["id"]]["last"] == "got" and is_due(scheds[c["id"]], now)]
    parts = {"cards": got / total if total else 0.0, "mocks": min(mocks, 1)}
    if cases_total:
        parts["cases"] = min(cases_done, 2) / 2
    if on_site:
        parts["logistics"] = 1.0 if confirmed else 0.0
    weight = sum(READY_WEIGHTS[k] for k in parts)
    score = int(round(100 * sum(READY_WEIGHTS[k] * v for k, v in parts.items()) / weight)) \
        if weight else 0
    if total and len(untried) == total:
        nxt = "Go through your %d answer cards once" % total
    elif shaky:
        nxt = "Go over the %d card%s you were shaky on" % (len(shaky), "" if len(shaky) == 1 else "s")
    elif on_site and not confirmed:
        nxt = "Check the address and the time with the invite, and tell Claude"
    elif untried:
        nxt = "Practise the %d card%s you haven't tried yet" % (len(untried),
                                                                "" if len(untried) == 1 else "s")
    elif not mocks:
        nxt = "Do one mock interview with Claude"
    elif cases_total and not cases_done:
        nxt = "Work through one practice case"
    elif due:
        nxt = "Run the %d card%s due again today" % (len(due), "" if len(due) == 1 else "s")
    elif not total:
        nxt = "Ask Claude to build the prep for this round"
    else:
        nxt = "You're ready: read your cheat sheet the morning of"
    return {"score": max(0, min(100, score)), "practised": [got, total], "cases_done": cases_done,
            "mocks_done": mocks, "logistics_confirmed": bool(confirmed), "next": nxt}


# ------------------------------------------------------------------ the round

MAX_CHEAT = 8


def cheat_sheet(reading, story_list, nums, who_list, day, shaky_qs) -> list:
    """At most eight lines: what the whole round comes down to."""
    glance = (reading or {}).get("glance") or {}
    out = []
    if glance.get("assessing"):
        out.append("They are checking: %s" % glance["assessing"])
    if glance.get("hear"):
        out.append("They want to hear: %s" % glance["hear"])
    if who_list:
        out.append("You meet: %s" % ", ".join(w["name"] for w in who_list if w.get("name")))
    if story_list:
        out.append("Lead with: %s" % "; ".join(s["title"] for s in story_list[:3]))
    if nums:
        out.append("Numbers to land: %s" % ", ".join(n["value"] for n in nums[:5]))
    if shaky_qs:
        out.append("Shaky last time: %s" % "; ".join(shaky_qs[:2]))
    if glance.get("money"):
        out.append("Money: %s" % glance["money"])
    if day:
        out.append("Arrive by %s%s" % (day.get("arrive_by") or "the time on the invite",
                                       ", at " + day["address"] if day.get("address") else ""))
    if glance.get("ask"):
        out.append("Ask them: %s" % glance["ask"][0])
    return out[:MAX_CHEAT]


def employer_kind(row: dict) -> str:
    """The kind of employer, from the tracker row's sector, then its name."""
    import interview_pack
    for text in (row.get("sector"), row.get("company")):
        found = next((t for t, rx in interview_pack.EMPLOYER_TYPES if rx.search(str(text or ""))), "")
        if found:
            return found
    return ""


def build(folder, text, stage: dict, row: dict, interview: str, docs=(), now=None,
          home_zone="", profile_text=None, reading=None) -> dict:
    """The round object the page draws (the contract in this module's docstring and the
    page's): who, format, in_person, cheat_sheet, stories, numbers, cards, logistics, cases,
    readiness."""
    import interview_pack
    now = now or dt.datetime.now(dt.timezone.utc)
    outcome = interview_pack._read(os.path.join(folder, "outcome.md"))
    label = str(stage.get("label") or "")
    fmt = interview_pack.stage_format(outcome, label) if label else ""
    held = load_logistics(folder, label) if label else {}
    on_site = in_person(stage, fmt, held)
    etype = employer_kind(row)
    reading = reading if reading is not None else (interview_pack.reading(text, row.get("company") or "")
                                                   if text else None)
    story_list = stories(profile_text)
    nums = numbers(profile_text)
    mine = for_interview(docs, interview)
    card_list = order_cards(cards(reading, interview, story_list), mine["cards"], now)
    hard = struggled(mine["cards"])
    for s in story_list:
        s["questions"] = [c["id"] for c in card_list if c.get("story") == s["id"]
                          or any(interview_pack.similar(c["q"], t) >= interview_pack.MATCH
                                 for t in s.get("use_for") or [])]
        mains = [c["id"] for c in card_list if c.get("story") == s["id"]]
        s["home"] = (mains or s["questions"] or [None])[0]
    who_list = who(stage.get("with"), interview_pack.what_works.stage_step(label), outcome)
    for c in card_list:
        c["who"] = likely_asker(c["q"], who_list)
    day = logistics(stage, held, etype, home_zone) if on_site else None
    case_list = cases_for(etype, " ".join(str(x or "") for x in (
        row.get("sector"), row.get("company"), row.get("role"))))
    ready = readiness(card_list, mine["cards"], mine["mocks"], mine["cases"], len(case_list),
                      on_site, bool(held.get("confirmed")), now)
    fmt_names = ((reading or {}).get("glance") or {}).get("assessing")
    return {
        "who": who_list,
        "format": fmt or fmt_names or None,
        "in_person": on_site,
        "cheat_sheet": cheat_sheet(reading, story_list, nums, who_list, day,
                                   [c["q"] for c in card_list if c["id"] in hard]),
        "stories": [{k: s[k] for k in ("id", "title", "trigger", "bullets", "source", "questions",
                                       "home")} for s in story_list],
        "numbers": nums,
        "cards": card_list,
        "logistics": day,
        "cases": case_list,
        "readiness": ready,
        "plan": plan(stage, card_list, story_list, nums, case_list, on_site, ready, now),
        # Where the person sits on the project the round is about: nothing records it yet.
        "project": None,
    }


MAX_PLAN_DAYS = 14


def plan(stage: dict, card_list, story_list, nums, case_list, on_site, ready: dict, now) -> list:
    """[{day, focus}] from today to the interview's day: one thing a day, the hardest first,
    a mock near the end, the day before light. [] when the round has no day yet or it is gone."""
    try:
        when = dt.date.fromisoformat(str(stage.get("date") or "")[:10])
    except ValueError:
        return []
    today = now.date()
    if when < today:
        return []
    weak = [c for c in card_list if c.get("last") in ("missed", "shaky")]
    fresh = [c for c in card_list if c.get("last") is None]
    todo = []
    if fresh:
        todo.append("Go through all %d answer cards once, out loud" % len(card_list))
    if weak:
        todo.append("The %d card%s you were shaky on or missed" % (len(weak), "" if len(weak) == 1 else "s"))
    if story_list:
        todo.append("Tell your stories out loud: %s" % "; ".join(s["title"] for s in story_list[:3]))
    if nums:
        todo.append("Drill your numbers until you can say them without looking")
    if any(c.get("follow") for c in card_list):
        todo.append("The follow-ups on your technical answers, three deep")
    if case_list:
        todo.append("Work through one practice case: %s" % (case_list[0].get("title") or "the first"))
    if on_site and not ready.get("logistics_confirmed"):
        todo.append("Check the address, entrance and time against the invite")
    if not ready.get("mocks_done"):
        todo.append("One mock interview with Claude")
    days = [today + dt.timedelta(days=n) for n in range(min((when - today).days, MAX_PLAN_DAYS) + 1)]
    out = []
    for i, d in enumerate(days):
        if d == when:
            focus = "The interview: read your cheat sheet once, then go"
        elif d == when - dt.timedelta(days=1) and len(days) > 2:
            focus = "Light: the cheat sheet and the cards due, then rest"
        elif todo:
            focus = todo[i % len(todo)]
        else:
            focus = "The cards due today"
        out.append({"day": d.isoformat(), "focus": focus})
    return out


def brief_line(company, stage_label, day, ready: dict) -> str:
    """One plain line for the brief: a round, its day, how ready, and the one thing to do."""
    when = ""
    if day:
        try:
            d = dt.date.fromisoformat(str(day)[:10])
            when = " on %s %d %s" % (d.strftime("%a"), d.day, d.strftime("%b"))
        except ValueError:
            when = ""
    return "%s, %s%s: %d%% ready. Next: %s." % (company, stage_label or "next round", when,
                                                int(ready.get("score") or 0),
                                                str(ready.get("next") or "").rstrip("."))


def brief_lines(tracker, today: dt.date, docs=None) -> list:
    """The brief's readiness lines: one for each round booked from today on, in day order."""
    import app_model
    import interview_pack
    import open_actions
    import throttle
    docs = mirror_docs() if docs is None else docs
    now = dt.datetime.combine(today, dt.time(8), tzinfo=dt.timezone.utc)
    out = []
    for row, rid in zip(tracker, app_model.tracker_ids(tracker)):
        st = str(row.get("status") or "").strip().lower()
        if st not in throttle.LIVE_PROCESS or st == "offer":
            continue
        try:
            folder, _files, stages = open_actions.stages(row)
        except Exception:  # noqa: BLE001  a row with no folder: no round to be ready for
            continue
        nxt = interview_pack.next_stage(stages, today.isoformat()) if stages else {}
        if not nxt or not nxt.get("date") or nxt["date"] < today.isoformat():
            continue
        text = interview_pack._read(os.path.join(folder, interview_pack.LIVING))
        try:
            got = build(folder, text, nxt, row, interview_id("", "", rid), docs, now)
        except Exception:  # noqa: BLE001  a round that cannot be read is left out of the line
            continue
        out.append((nxt["date"], brief_line(row.get("company") or "", nxt.get("label"),
                                            nxt["date"], got["readiness"])))
    return [line for _d, line in sorted(out)]


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "schedule":
        print(json.dumps(schedule(json.loads(args[1])), indent=1))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
