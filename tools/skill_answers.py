#!/usr/bin/env python3
"""One answer per skill, shared by every chat: can the person claim a skill their profile does
not list?

A posting names a skill the profile does not hold, and only the person can say whether they can
claim it and back it up (tools/stage_picks.py asks). Before this, each drafting chat kept its own
answer with the pick it drafted, so two chats running at once asked separately and answered
separately: one resume recorded "no" to a skill and another "yes" two hours later (the
maintainer, 2026-11-04), and a chat with nobody there to answer recorded "no" so that it could
carry on. So:

- **One record per skill**, `documents/skill_answers.json`, read by every chat and every
  application. A pick staged after a yes takes the yes; after a no, the no.
- **Only the person answers.** A question nobody has answered stays open. It is put to them
  once, on their page (app_model `_skill_questions`), however many postings and chats ask it,
  and a draft made meanwhile leaves the skill off and is marked as waiting on it
  (`skills_waiting` on the pick, `waiting_skills` on the draft). It is never recorded as a no.
- **The later explicit answer wins**, between two chats as within one: each answer is dated
  (`answer.at`), and tools/merge_state.py keeps the later of two. A no the person gave stays a
  no until they say otherwise.
- **Three answers: yes, just for this role, no.** A yes is theirs for every application and is
  written into their profile; "just for this role" (`ROLE`) is a yes for the roles it names
  only (`roles` on the record), used on those roles' resumes and bullets and never added to
  the profile or to any other role, so a posting from another role asks again (the
  maintainer, 2026-11-05: a skill claimed for one role should not be added to the profile
  by itself). Between the two kinds, as between two answers, the later one wins.
- **A yes redoes every unsent resume waiting on it**, whatever its day, and every one drafted
  that day for a posting naming the skill (`redo_due`):
  a yes on the page queues each as a tweak (app_actions), and a chat that takes a yes, or that
  finds one another chat took, runs `redo` (stage_picks.py consent and app.py view print it).

    python3 tools/skill_answers.py show
    python3 tools/skill_answers.py redo [--skill S]   the resumes waiting on a yes, redone with it
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

FILE = "skill_answers.json"
ANSWERS = ("yes", "no")
# "Just for this role": a yes for the roles the record names, never the profile's.
ROLE = "role"


def path() -> str:
    return person.state("documents", FILE)


def key(skill) -> str:
    """One skill however a posting spells it: "Big Query", "BigQuery" and "bigquery" are one."""
    return re.sub(r"[\s._-]+", "", str(skill or "").casefold())


def named(value) -> str:
    """The skill a tweak's change names: {"skill": ...}, the page's {"asked": ...}, or a word."""
    if isinstance(value, dict):
        value = value.get("skill") or value.get("asked") or ""
    return " ".join(str(value or "").split())


def day_of(today=None) -> str:
    """The day drafts are counted on: the one given, else the person's own day
    (person.today()), at the app's fixed clock (LJS_TODAY, as app_model.clock reads it) where
    one is set."""
    if today:
        return str(today)[:10]
    fixed = os.environ.get("LJS_TODAY")
    if fixed:
        import app_model
        t = app_model.parse_time(fixed)
        if t is not None:
            return person.today(t).isoformat()
    return person.today().isoformat()


def _now(at=None) -> str:
    t = at or dt.datetime.now(dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    try:
        with open(path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {"skills": {}}
    if not isinstance(got, dict) or not isinstance(got.get("skills"), dict):
        return {"skills": {}}
    return got


def _save(data: dict) -> None:
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _profile_yes(skill: str) -> bool:
    """A yes written into the candidate profile (stage_picks.profile_yes) before this record
    kept answers, or by a chat whose record has not reached this copy yet."""
    try:
        import stage_picks
        with open(person.file("candidate_profile", "01-candidate-profile.md"),
                  encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, person.NoProfile):
        return False
    if stage_picks.YES_HEADING not in text:
        return False
    k = key(skill)
    return any((m := stage_picks._YES_LINE.match(ln)) and key(m.group("skill")) == k
               for ln in text.split(stage_picks.YES_HEADING, 1)[1].splitlines())


def _scoped(rec: dict, company, role) -> dict | None:
    """The "just for this role" yes the record holds for this role, if any."""
    want = (key(company), key(role))
    return next((x for x in rec.get("roles") or [] if isinstance(x, dict)
                 and (key(x.get("company")), key(x.get("role"))) == want), None)


def answer(skill, data: dict | None = None, company: str = "", role: str = "") -> str:
    """"yes", "no", or "" while nobody has answered. With a role (`company`, `role`), a "just
    for this role" yes counts for that role alone, unless a yes or no for every application
    was given after it."""
    rec = ((data or load())["skills"]).get(key(skill)) or {}
    given = rec.get("answer") if isinstance(rec.get("answer"), dict) else {}
    said = str(given.get("said") or "")
    if str(company or "").strip():
        mine = _scoped(rec, company, role)
        if mine and not (said in ANSWERS and str(given.get("at") or "") > str(mine.get("at") or "")):
            return "yes"
    if said in ANSWERS:
        return said
    return "yes" if _profile_yes(skill) else ""


def ask(skill, company: str = "", role: str = "", day=None, at=None) -> str:
    """A posting asks about this skill: the answer already given, or "" with the question kept
    open (once, however many postings ask it) and this application named as waiting on it."""
    skill = named(skill)
    if not key(skill):
        return ""
    data = load()
    rec = data["skills"].setdefault(key(skill), {})
    rec.setdefault("skill", skill)
    rec.setdefault("asked", _now(at))
    said = answer(skill, data, company, role)
    entry = {"company": str(company or "").strip(), "role": str(role or "").strip(),
             "day": day_of(day)}
    have = rec.setdefault("for", [])
    same = next((x for x in have if isinstance(x, dict) and key(x.get("company")) == key(
        entry["company"]) and key(x.get("role")) == key(entry["role"])), None)
    if same is not None:
        # Staged again (a redraft): drafted on this day now.
        same["day"] = max(str(same.get("day") or ""), entry["day"])
    elif entry["company"]:
        have.append(entry)
    _save(data)
    return said


def record(skill, said: str, by: str = "chat", at=None, company: str = "", role: str = "",
           profile: bool = True) -> bool:
    """The person's own answer, for every application at once. Refused for anything but yes or
    no: nothing ever answers for them. An answer dated before the one on record leaves it as it
    is (the later explicit answer wins); True when this one stands. With `profile`, a yes is
    written into the candidate profile and a no takes a yes line out (stage_picks.profile_yes),
    where every claim check grounds a skill."""
    if said not in ANSWERS:
        raise ValueError(f"only the person answers, yes or no; not {said!r}")
    skill = named(skill)
    if not key(skill):
        raise ValueError("which skill: none was named")
    data = load()
    rec = data["skills"].setdefault(key(skill), {})
    rec.setdefault("skill", skill)
    rec.setdefault("asked", _now(at))
    was = rec.get("answer") if isinstance(rec.get("answer"), dict) else {}
    when = _now(at)
    if was.get("at") and str(was["at"]) > when:
        return False
    if was.get("said") != said:
        rec["answer"] = {"said": said, "at": when, "by": by}
        _save(data)
    if profile:
        import stage_picks
        stage_picks.profile_yes(*(([skill], []) if said == "yes" else ([], [skill])),
                                company=company, role=role, today=day_of())
    return True


def record_role(skill, roles, by: str = "chat", at=None) -> bool:
    """"Just for this role": the person can claim the skill for these roles ({company, role}
    each) and no other. Kept on the skill's one record (`roles`), never written into the
    profile; True when it stands (a yes or no for every application given after it leaves it
    as it is)."""
    skill = named(skill)
    if not key(skill):
        raise ValueError("which skill: none was named")
    roles = [{"company": str(x.get("company") or "").strip(), "role": str(x.get("role") or "").strip()}
             for x in roles or () if isinstance(x, dict) and str(x.get("company") or "").strip()]
    if not roles:
        raise ValueError("which role: none was named")
    data = load()
    rec = data["skills"].setdefault(key(skill), {})
    rec.setdefault("skill", skill)
    rec.setdefault("asked", _now(at))
    when = _now(at)
    given = rec.get("answer") if isinstance(rec.get("answer"), dict) else {}
    if given.get("at") and str(given["at"]) > when:
        return False
    have = rec.setdefault("roles", [])
    for x in roles:
        same = _scoped(rec, x["company"], x["role"])
        if same is None:
            have.append(dict(x, at=when, by=by))
        elif str(same.get("at") or "") < when:
            same.update(at=when, by=by)
    _save(data)
    return True


def open_questions(data: dict | None = None) -> list[dict]:
    """The skills nobody has answered yet, oldest first: {key, skill, asked, for}, `for` the
    roles still waiting on an answer (one answered "just for this role" is not)."""
    data = data or load()
    out = []
    for k, rec in sorted(data["skills"].items(), key=lambda kv: str(kv[1].get("asked") or "")):
        if not isinstance(rec, dict) or answer(rec.get("skill") or k, data):
            continue
        fors = [x for x in rec.get("for") or [] if isinstance(x, dict)]
        waiting = [x for x in fors if not _scoped(rec, x.get("company"), x.get("role"))]
        if rec.get("roles") and not waiting:
            continue
        out.append({"key": k, "skill": str(rec.get("skill") or k), "asked": rec.get("asked"),
                    "for": waiting})
    return out


def work_id(item_id: str, skill: str) -> str:
    """The tweak that redoes one draft with one yes: the same id whoever queues it."""
    return f"tweak~{str(item_id)[:60]}~yes-{key(skill)[:30]}"


def _draft(slug: str) -> dict:
    try:
        with open(person.state("documents", "applications", slug, "draft.json"),
                  encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    got = got[0] if isinstance(got, list) and got else got
    return got if isinstance(got, dict) else {}


def _redone(slug: str, k: str) -> bool:
    """This draft has had this yes put on it once already (its tweaks.json): one the person
    then took back with Undo is left as they left it."""
    try:
        with open(person.state("documents", "applications", slug, "tweaks.json"),
                  encoding="utf-8") as fh:
            log = json.load(fh)
    except (OSError, ValueError):
        return False
    return any(isinstance(e, dict) and any(
        isinstance(c, dict) and c.get("p") in ("yes", "near") and key(named(c.get("v"))) == k
        for c in e.get("changes") or []) for e in (log.values() if isinstance(log, dict) else ()))


def redo_due(skill=None, today=None, ready: list | None = None, queued=()) -> list[dict]:
    """The unsent resumes still without a skill the person has said yes to: each whose draft
    is waiting on it (`waiting_skills`), whatever day it was drafted, and each drafted `today`
    (person.today()) for a posting that asked about it. {id, slug, company, role, skill}, the
    skill as that draft's posting spelled it. `ready` is the page's own list of drafts when
    the caller has built it; `queued` the work ids already on their way. Only that day's
    drafts were redone once, so one staged the night before, waiting on the answer, never
    got the yes (the engine review, 2026-11-05)."""
    data = load()
    day = day_of(today)
    # A yes for every application, or one "just for" some roles: those roles' drafts only.
    yes = {k: rec for k, rec in data["skills"].items() if isinstance(rec, dict)
           and (skill is None or k == key(skill))
           and (answer(rec.get("skill") or k, data) == "yes" or rec.get("roles"))}
    if not yes:
        return []
    asked = {k: [x for x in rec.get("for") or [] if isinstance(x, dict) and x.get("day") == day]
             for k, rec in yes.items()}
    if ready is None:
        import app_model
        ready = app_model.build(only={"ready"})[0].get("ready") or []
    out = []
    for item in ready:
        if item.get("status") != "drafted" or not item.get("slug"):
            continue
        d = None
        for k, entries in asked.items():
            said = yes[k].get("skill") or k
            if answer(said, data, item.get("company"), item.get("role")) != "yes":
                continue
            today_asked = any(key(x.get("company")) == key(item.get("company"))
                              and key(x.get("role")) == key(item.get("role")) for x in entries)
            if d is None:
                d = _draft(item["slug"])
            waiting = any(key(s) == k for s in (d or {}).get("waiting_skills") or [])
            if not (today_asked or waiting):
                continue
            if not d or any(key(s) == k for s in d.get("consented_skills") or []) \
                    or _redone(item["slug"], k):
                continue
            wid = work_id(item["id"], k)
            if wid in queued:
                continue
            spelled = next((s for s in list(d.get("waiting_skills") or [])
                            + list(d.get("declined_skills") or []) if key(s) == k),
                           yes[k].get("skill") or k)
            out.append({"id": item["id"], "slug": item["slug"], "company": item.get("company"),
                        "role": item.get("role"), "skill": spelled, "work": wid,
                        **({"scope": ROLE} if answer(said, data) != "yes" else {})})
    return out


def tweak_work(due: dict) -> dict:
    """The tweak work item that redoes one draft with its yes (tools/tweak.py, change "yes"); a
    yes "just for this role" says so, so the tweak never records it for every application."""
    v = {"skill": due["skill"], **({"scope": ROLE} if due.get("scope") == ROLE else {})}
    return {"args": {"v": 1, "target": {"id": due["id"], "output": "resume"},
                     "changes": [{"p": "yes", "v": v}], "text": None, "keep": None}}


def redo_line(due: list[dict]) -> str:
    """What a chat is told to do at once when a yes leaves resumes without it."""
    if not due:
        return ""
    names = sorted({f"{d['company']} ({d['skill']})" for d in due})
    return ("The person said yes to a skill that unsent resumes still leave off: "
            + ", ".join(names) + ". Redo them with it now, unasked: python3 tools/skill_answers.py "
            "redo, then bring the page up to date.")


def redo(skill=None, today=None) -> list[dict]:
    """Each resume `redo_due` names, redone with its yes through the tweak that puts a yes on a
    draft (tools/tweak.py): the skills line rendered again and the documents checked again."""
    import tweak
    out = []
    for due in redo_due(skill, today):
        got = tweak.apply(tweak_work(due), today=dt.date.fromisoformat(day_of(today)))
        out.append(dict(due, status=got.get("status"), summary=got.get("summary")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="skill_answers.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="every skill asked about, and the answer")
    r = sub.add_parser("redo", help="the resumes still without a skill the person said yes to")
    r.add_argument("--skill", default=None)
    r.add_argument("--today", default=None, help="YYYY-MM-DD (else the person's own day)")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        data = load()
        for k, rec in sorted(data["skills"].items()):
            said = answer(rec.get("skill") or k, data) or "not answered yet"
            only = ", ".join(sorted({f"{x.get('company')} ({x.get('role')})" for x in rec.get("roles") or []
                                     if isinstance(x, dict)}))
            if only and said != "yes":
                said = f"yes just for {only}" + ("" if said == "not answered yet" else f"; {said} for the rest")
            who = ", ".join(sorted({str(x.get("company")) for x in rec.get("for") or []
                                    if isinstance(x, dict) and x.get("company")}))
            print(f"{rec.get('skill') or k}: {said}" + (f" (asked by {who})" if who else ""))
        return 0
    done = redo(a.skill, a.today)
    if not done:
        print("Nothing to redo: every unsent resume has each skill you said yes to.")
        return 0
    bad = 0
    for d in done:
        ok = d["status"] in ("done", "cached")
        bad += not ok
        print(f"{d['company']}, {d['role']}: " + (f"redone with {d['skill']}." if ok
                                                    else f"not redone: {d['summary']}"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
