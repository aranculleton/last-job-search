#!/usr/bin/env python3
"""Every rule that leaves something out, holds it back, caps it or gates it, and when each ends.

Two things, both computed here (the engine computes, the page draws):

- **`RULES`, the inventory**: one row a rule, across jobs, applications, people, messages,
  interviews and the page itself, each with where it lives (`where`, for whoever changes
  the app), when it ends (`ends`) or, where it never does, why that is the person's own
  choice (`why`), what the person says or taps to lift it (`override`), what missing data
  does to it (`missing`) and where on the page it is seen (`shown`). The words are the
  person's own settings where a rule has one (their follow-up rule, their number a company).
  `tests/test_every_hold_says_when_it_ends.py` holds the table: every `where` names a real
  definition, and for every rule a test feeds it missing data and finds it does not hold for
  ever by accident.
- **`live`, what is held back today**: the holds that are on now for this person, each one
  plain line with its day or its reason and its override, "Fernhill Freight: open again
  Thu 3 Dec, or say 'more at Fernhill Freight'". The page draws them under Settings, Your
  rules, as one row ("Held back for now").

Why: an employer was shut for 45 days whenever two people there were waiting on a reply, a
number nobody chose, a note with no date held its employer for ever, and nothing on the page
said any of it (the maintainer, 2026-11-09).

    python3 tools/holds.py              # what is held back today, a line each
    python3 tools/holds.py --rules      # every rule, when it ends and how to lift it
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

AREAS = ("jobs", "applications", "people", "messages", "interviews", "page")

# One row a rule. `ends` and `why` are templates filled from the person's settings
# (`settings()`); exactly one of them says something. `where` is "file:name", checked by the
# test. Nothing here is shown with a file name: those are for whoever changes the app.
RULES = (
    # ------------------------------------------------------------------ jobs
    {"id": "job_age", "area": "jobs", "name": "Jobs posted too long ago",
     "where": ("tools/prefilter.py:MAX_AGE_DAYS", "tools/prefilter.py:_decide"),
     "ends": "", "why": "your own window for how recent a job must be",
     "override": "change How recent in Your rules",
     "missing": "a job with no date is kept and scored",
     "shown": "Settings, Your rules"},
    {"id": "gates", "area": "jobs",
     "name": "Jobs that need a language, citizenship, clearance or qualification you do not have",
     "where": ("tools/throttle.py:_STILL_CUTS_CORE", "tools/exclude.py:GATE_NAMES"),
     "ends": "", "why": "the job's own words require it; looked at again whenever your "
                        "profile changes",
     "override": "tell Claude you have it, or add the language in Your rules",
     "missing": "a job that says nothing about it is kept",
     "shown": "Jobs, What a search left out"},
    {"id": "sectors", "area": "jobs", "name": "Kinds of employer you will not work for",
     "where": ("tools/bar.py:verdict", "tools/sector.py:is_agency"),
     "ends": "", "why": "your choice, kept until you change it",
     "override": "use the trash beside it in Your rules",
     "missing": "an employer nobody has judged yet is judged first, never hidden",
     "shown": "Settings, Your rules"},
    {"id": "declined", "area": "jobs", "name": "Employers you turned down",
     "where": ("tools/run_round.py:declined_now", "tools/network/surface.py:turned_down"),
     "ends": "", "why": "your choice, kept until you change it",
     "override": "use the trash beside the employer in Your rules",
     "missing": "an employer you never named is never turned down",
     "shown": "Settings, Your rules, Employers you've turned down"},
    {"id": "dismissed", "area": "jobs", "name": "Jobs you set aside",
     "where": ("tools/exclude.py:BASES", "tools/app_actions.py:_job_dismiss"),
     "ends": "", "why": "your choice for that one job; another role at the employer still shows",
     "override": "tap Bring back under Set aside in Jobs",
     "missing": "only the job you set aside is held, never its employer",
     "shown": "Jobs, Set aside"},
    {"id": "ruled_out", "area": "jobs", "name": "Jobs a search already ruled out",
     "where": ("tools/throttle.py:is_stale_exclusion", "tools/throttle.py:RE_EVALUATED"),
     "ends": "a reason that was only a score, a pay band or a preference is read again on "
             "every search",
     "why": "", "override": "tap Bring back under What a search left out in Jobs",
     "missing": "a ruling with no reason holds only that one posting, never its employer",
     "shown": "Jobs, What a search left out"},
    {"id": "duplicates", "area": "jobs", "name": "The same job posted again",
     "where": ("tools/throttle.py:RELIST_WINDOW",),
     "ends": "after {relist} days the same title at the employer counts as a new opening",
     "why": "", "override": "add it yourself with Add a job",
     "missing": "a job with no title or employer is never taken for another",
     "shown": "Jobs"},
    {"id": "no_team", "area": "jobs", "name": "Employers with no team for you where you look",
     "where": ("tools/throttle.py:do_not_target_until", "tools/network/discovery.py:presence_blocks"),
     "ends": "on its own review day, or {dnt} days after it was found where it names none",
     "why": "", "override": "say 'look at <employer> again'",
     "missing": "a finding with no date holds nothing",
     "shown": "Settings, Your rules, Held back for now"},
    # ------------------------------------------------------------------ applications
    {"id": "application_open", "area": "applications",
     "name": "Other jobs at an employer you applied to",
     "where": ("tools/throttle.py:open_applications", "tools/throttle.py:SILENCE_DAYS",
               "tools/throttle.py:undated_application"),
     "ends": "when they answer, or {silence} days after you applied (or after the job's closing "
             "day) with no reply; a role scoring {override_points} points more still shows",
     "why": "", "override": "say 'stop waiting on <employer>'",
     "missing": "an application with no date holds nothing",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "referral", "area": "applications",
     "name": "Applying cold where someone is referring you",
     "where": ("tools/throttle.py:referral_holds",),
     "ends": "", "why": "only you know when a referral is over; the job itself is never hidden",
     "override": "say 'the referral at <employer> is over'",
     "missing": "only a referral you recorded holds anything",
     "shown": "Jobs, on the job's card"},
    {"id": "application_nudges", "area": "applications",
     "name": "Follow-ups to an application",
     "where": ("tools/followups.py:MAX_NUDGES", "tools/followups.py:FIRST_NUDGE_DAYS",
               "tools/followups.py:REOPEN_WINDOW_DAYS"),
     "ends": "at most {app_nudges} follow-ups; closed as no reply after {silence} days, and "
             "opened again if they write within {reopen} days",
     "why": "", "override": "say 'they replied' on the application",
     "missing": "an application with no recipient is asked about, never chased",
     "shown": "To do"},
    # ------------------------------------------------------------------ people
    {"id": "employer_wait", "area": "people",
     "name": "More people at an employer where people are waiting on a reply",
     "where": ("tools/network/reading.py:waiting_until", "tools/network/reading.py:at_employer",
               "tools/network/reading.py:EMPLOYER_WAIT_DAYS"),
     "ends": "{per_employer} at a time; each one waiting frees their place {wait}",
     "why": "", "override": "say 'more at <employer>'",
     "missing": "someone with no date holds nothing",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "limit", "area": "people", "name": "Someone who has not answered your limit of messages",
     "where": ("tools/network/state.py:at_limit", "tools/network/schema.py:MAX_UNANSWERED"),
     "ends": "when they write back; your limit is {max_unanswered} messages with no reply",
     "why": "", "override": "tap Close on their card, or paste their reply with They replied",
     "missing": "messages with no date still count, so nobody gets a third by accident",
     "shown": "Contacts"},
    {"id": "closed", "area": "people", "name": "Conversations you closed or set aside",
     "where": ("tools/network/state.py:CLOSED",),
     "ends": "", "why": "your choice; a reply from them opens it again",
     "override": "say 'write to <name> again'",
     "missing": "only a conversation you closed is closed",
     "shown": "Contacts"},
    {"id": "people_turned_down", "area": "people", "name": "People at employers you turned down",
     "where": ("tools/network/surface.py:turned_down", "tools/network/surface.py:employer_out"),
     "ends": "", "why": "your choice, kept until you change the employer's rule",
     "override": "use the trash beside the employer in Your rules",
     "missing": "a recruiter at an agency is never held for the agency",
     "shown": "Contacts"},
    {"id": "place", "area": "people", "name": "People living outside where you look",
     "where": ("tools/network/surface.py:outside_market",),
     "ends": "", "why": "your own places to look; a reply from them is always answered",
     "override": "change Where in Your rules",
     "missing": "someone with no place known is never held for it",
     "shown": "Contacts"},
    {"id": "person_hold", "area": "people", "name": "Someone you put on hold",
     "where": ("tools/network/state.py:action_hold", "tools/network/state.py:hold_lifts"),
     "ends": "on the day the hold names, or the day beside it",
     "why": "", "override": "say 'write to <name> again'",
     "missing": "a hold with no day at all is listed under Held back for now until you lift it",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "request", "area": "people", "name": "Follow-ups to a request nobody accepted",
     "where": ("tools/network/surface.py:held",),
     "ends": "when they accept, or when you withdraw it", "why": "",
     "override": "withdraw it from their card",
     "missing": "a request with no date is never chased",
     "shown": "Contacts"},
    {"id": "written_to", "area": "people", "name": "Someone already written to, offered as new",
     "where": ("tools/network/surface.py:check",),
     "ends": "", "why": "they are not someone new; what is owed them comes by your follow-up rule",
     "override": "open their card in Contacts",
     "missing": "a name that may be someone in your contacts is asked about first",
     "shown": "Contacts"},
    {"id": "inmail", "area": "people", "name": "InMail once this month's credits are used",
     "where": ("tools/network/state.py:platform_budget",),
     "ends": "on the first of next month", "why": "",
     "override": "tell Claude the number LinkedIn shows",
     "missing": "with no balance told, it counts what you sent",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "invitations", "area": "people", "name": "LinkedIn's weekly invitation limit",
     "where": ("tools/network/state.py:CAPPED_NOTE",),
     "ends": "when LinkedIn lets requests go again; the app sets no limit of its own",
     "why": "", "override": "follow them meanwhile, and the request goes the next week",
     "missing": "only LinkedIn saying so holds anything",
     "shown": "Contacts"},
    {"id": "reading_stop", "area": "people", "name": "Reading profiles after LinkedIn shows a check",
     "where": ("tools/network/reading.py:stopped",),
     "ends": "the next day", "why": "",
     "override": "nothing to do",
     "missing": "only a check LinkedIn showed stops it",
     "shown": "Settings, Your rules, Held back for now"},
    # ------------------------------------------------------------------ messages
    {"id": "follow_up", "area": "messages", "name": "A follow-up before its day",
     "where": ("tools/network/state.py:follow_up_on", "tools/network/schema.py:FOLLOW_UP_DAYS"),
     "ends": "{follow_up} after the last message", "why": "",
     "override": "draft it now on their card",
     "missing": "a thread with nothing dated gets no day, and is never owed by accident",
     "shown": "Contacts"},
    {"id": "put_off", "area": "messages", "name": "Something you put off",
     "where": ("tools/app_actions.py:_due_snooze",),
     "ends": "on the day you chose", "why": "", "override": "tap Show under put off in To do",
     "missing": "Tomorrow and Next week always carry a day",
     "shown": "To do"},
    {"id": "note_aside", "area": "messages", "name": "A first note you set aside",
     "where": ("tools/app_actions.py:_msg_skip",),
     "ends": "", "why": "your choice for that person",
     "override": "tap Undo, or say 'write to <name> again'",
     "missing": "only the note you set aside is held",
     "shown": "Contacts"},
    # ------------------------------------------------------------------ interviews
    {"id": "interview_quiet", "area": "interviews", "name": "Chasing during interviews",
     "where": ("tools/open_actions.py:INTERVIEW_QUIET_DAYS", "tools/throttle.py:is_silent"),
     "ends": "a live process is never chased; after {quiet} quiet days Claude asks how it went",
     "why": "", "override": "say how it went, on the interview",
     "missing": "an interview with no date is asked about, never timed out",
     "shown": "Coming up"},
    {"id": "prep", "area": "interviews", "name": "Prep and thank-you notes",
     "where": ("tools/open_actions.py:PREP_WINDOW_DAYS", "tools/open_actions.py:THANKS_DAYS"),
     "ends": "prep shows {prep} days before; a thank-you is offered for {thanks} days after",
     "why": "", "override": "tap Update my prep on the interview",
     "missing": "an interview with no day is shown with no day, never dropped",
     "shown": "Coming up"},
    # ------------------------------------------------------------------ page
    {"id": "todo_hidden", "area": "page", "name": "To do cards you hid",
     "where": ("templates/app/app.js:hideTodo",),
     "ends": "after a week, on that device", "why": "",
     "override": "tap Show under hidden this week in To do",
     "missing": "nothing is hidden unless you hid it",
     "shown": "To do"},
    {"id": "ideas_paused", "area": "page", "name": "Ideas Claude suggests, after three No thanks",
     "where": ("tools/app_alerts.py:paused", "tools/app_alerts.py:PAUSE_DAYS"),
     "ends": "{pause} days after the third", "why": "",
     "override": "say 'show me ideas again'",
     "missing": "a No thanks with no day does not count",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "idea_declined", "area": "page", "name": "One idea you said No thanks to",
     "where": ("tools/app_alerts.py:NO_KEY",),
     "ends": "", "why": "your answer to that one idea", "override": "tap Undo when it is said",
     "missing": "only that idea is held", "shown": "Brief"},
    {"id": "brief_paused", "area": "page", "name": "Your brief, paused",
     "where": ("tools/routines.py:pause", "tools/routines.py:paused"),
     "ends": "on the day you chose", "why": "", "override": "tap Resume in Settings, Your brief",
     "missing": "a break always carries its day", "shown": "Settings, Your brief"},
    {"id": "news_seen", "area": "page", "name": "News a brief already carried",
     "where": ("tools/brief.py:NEWS_MAX",),
     "ends": "", "why": "the same story twice is no news; at most {news} a brief",
     "override": "choose how many in Settings, Your brief",
     "missing": "a story with no link is judged on its words",
     "shown": "Brief"},
    {"id": "export_later", "area": "page", "name": "The LinkedIn download reminder, put off",
     "where": ("tools/network/export.py:put_off_on",),
     "ends": "it asks again on its next turn", "why": "",
     "override": "choose how often in Settings, LinkedIn",
     "missing": "never asked for, it is asked for", "shown": "To do"},
    {"id": "update_questions", "area": "page", "name": "Questions an update brought",
     "where": ("tools/profile_upgrades.py:SAFE_DEFAULTS",),
     "ends": "", "why": "they wait in Settings, never in To do, since nothing about them is late",
     "override": "answer them under From updates in Settings",
     "missing": "a setting with a safe default never asks", "shown": "Settings"},
)


def _rule_settings() -> dict:
    """The person's own numbers the inventory's words are filled from."""
    out = {"relist": 30, "dnt": 90, "silence": 45, "override_points": 10, "app_nudges": 2,
           "reopen": 120, "per_employer": "2 people", "wait": "about four weeks after the last "
           "message", "max_unanswered": 2, "follow_up": "6 business days", "quiet": 14,
           "prep": 7, "thanks": 7, "pause": 30, "news": 5}
    try:
        import throttle
        out.update(relist=throttle.RELIST_WINDOW, dnt=throttle.DO_NOT_TARGET_REVIEW_DAYS,
                   silence=throttle.SILENCE_DAYS, override_points=throttle.OVERRIDE_POINTS)
    except Exception:  # noqa: BLE001  no profile to read: the app's numbers stand
        pass
    try:
        import followups
        out.update(app_nudges=followups.MAX_NUDGES, reopen=followups.REOPEN_WINDOW_DAYS)
    except Exception:  # noqa: BLE001
        pass
    try:
        import reading
        import schema
        n = reading.PER_EMPLOYER
        out["per_employer"] = f"{n} {'person' if n == 1 else 'people'}"
        out["max_unanswered"] = schema.MAX_UNANSWERED
        out["follow_up"] = (f"{schema.FOLLOW_UP_DAYS} days" if schema.FOLLOW_UP_DAYS
                            else f"{schema.FOLLOWUP_BUSINESS_DAYS} business days")
        out["wait"] = (f"{reading.EMPLOYER_WAIT_DAYS} days after the last message, as you set"
                       if reading.EMPLOYER_WAIT_DAYS else
                       f"about {reading.WAITING_DAYS} days after a first note, by your follow-up "
                       f"rule ({schema.follow_up_rule()}), counted from the last message")
    except Exception:  # noqa: BLE001
        pass
    try:
        import open_actions
        out.update(quiet=open_actions.INTERVIEW_QUIET_DAYS, prep=open_actions.PREP_WINDOW_DAYS,
                   thanks=open_actions.THANKS_DAYS)
    except Exception:  # noqa: BLE001
        pass
    try:
        import app_alerts
        out["pause"] = app_alerts.PAUSE_DAYS
    except Exception:  # noqa: BLE001
        pass
    try:
        import brief
        out["news"] = brief.NEWS_MAX
    except Exception:  # noqa: BLE001
        pass
    return out


def rules() -> list[dict]:
    """Every rule, its words filled from the person's settings, with `line`: its name, when
    it ends or why it never does, and how to lift it, one plain line."""
    s = _rule_settings()
    out = []
    for r in RULES:
        ends = r["ends"].format(**s)
        why = r["why"].format(**s)
        said = ends or f"kept, as {why}"
        over = r["override"][:1].upper() + r["override"][1:]
        out.append(dict(r, ends=ends, why=why, line=f"{r['name']}: {said}. {over}."))
    return out


# ------------------------------------------------------------------ live holds

def day_words(d: dt.date) -> str:
    """A day ahead, as the page says one: "Thu 3 Dec"."""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def _hold(rule: str, what: str, line: str, until=None, say: str = "") -> dict:
    from company_key import key
    return {"id": f"hold~{rule}~{key(what) or what.lower()}", "rule": rule, "what": what,
            "until": until.isoformat() if isinstance(until, dt.date) else (until or None),
            "line": line, "say": say}


def _employer_waits(today, contacts, threads) -> list:
    """Each employer at the person's number of people waiting: the day it opens again."""
    import reading
    import state
    by = state.by_contact(threads)
    groups: dict = {}
    for c in contacts:
        k = state.row_company_key(c)
        if not k:
            continue
        msgs = by.get(str(c.get("contact_id") or "").strip(), [])
        if state.effective_status(c, msgs) not in reading.WAITING:
            continue
        until = reading.waiting_until(c, msgs)
        if until is None or until <= today:
            continue
        groups.setdefault(k, []).append((until, str(c.get("company") or "").strip()))
    out = []
    for k, rows in sorted(groups.items()):
        names = [n for _, n in rows if n]
        company = max(set(names), key=names.count) if names else k
        limit, _theirs = reading.employer_limit(company)
        if limit is None or len(rows) < limit:
            continue
        opens = sorted(d for d, _ in rows)[len(rows) - limit]
        out.append(_hold("employer_wait", company,
                         f"{company}: open again {day_words(opens)}, or say 'more at {company}'",
                         opens, f"more at {company}"))
    return out


def _applications(today) -> list:
    import throttle
    out = []
    for k, rows in sorted(throttle.open_applications(today=today).items()):
        company = str(rows[0].get("company") or k).strip()
        live = [r for r in rows if str(r.get("status") or "").strip().lower()
                in throttle.LIVE_PROCESS]
        if live:
            out.append(_hold("application_open", company,
                             f"{company}: no new jobs there while your interviews run, or say "
                             f"'it's over at {company}'", None, f"it's over at {company}"))
            continue
        ends = []
        for r in rows:
            sent = throttle.as_date(throttle.applied_on(r) or r.get("date"), iso_only=True)
            closes = throttle.as_date(r.get("deadline"), iso_only=True)
            start = max(d for d in (sent, closes) if d) if (sent or closes) else None
            if start:
                ends.append(start + dt.timedelta(days=throttle.SILENCE_DAYS))
        until = max(ends) if ends else None
        when = f"until {day_words(until)} unless they reply" if until else "until they reply"
        out.append(_hold("application_open", company,
                         f"{company}: no new jobs there while your application waits, {when}, "
                         f"or say 'stop waiting on {company}'", until,
                         f"stop waiting on {company}"))
    return out


def _no_team(today) -> list:
    import throttle
    data = throttle._read_do_not_target() or {}
    out = []
    for name, e in sorted((data.get("companies") or {}).items()):
        until = throttle.do_not_target_until(e)
        if not until or until < today.isoformat():
            continue
        d = dt.date.fromisoformat(until)
        out.append(_hold("no_team", name, f"{name}: no team for you where you look, looked at "
                         f"again {day_words(d)}, or say 'look at {name} again'", d,
                         f"look at {name} again"))
    return out


def _person_holds(today, contacts) -> list:
    import state
    out = []
    for c in contacts:
        why = state.action_hold(c.get("next_action"), today, c.get("next_action_due"))
        if not why:
            continue
        name = str(c.get("name") or c.get("contact_id") or "").strip()
        first = name.split()[0] if name else name
        lifts = state.hold_end(c.get("next_action"), c.get("next_action_due"))
        when = f"on hold until {day_words(lifts)}" if lifts else "on hold with no end day"
        out.append(_hold("person_hold", name, f"{name}: {when}, or say 'write to {first} again'",
                         lifts, f"write to {first} again"))
    return out


def _inmail(today, contacts, threads) -> list:
    import state
    b = state.platform_budget(contacts, threads, today)
    if not b.get("inmails_limit") or b.get("inmails_left") != 0:
        return []
    month_end = dt.date.fromisoformat(b["month_end"])
    nxt = month_end + dt.timedelta(days=1)
    return [_hold("inmail", "InMail", f"InMail: none left this month, more from "
                  f"{day_words(nxt)}, or tell Claude the number LinkedIn shows", nxt,
                  "I have <n> InMail credits")]


def _reading(today) -> list:
    import reading
    why = reading.stopped(today)
    if not why:
        return []
    nxt = today + dt.timedelta(days=1)
    return [_hold("reading_stop", "Reading profiles", "Reading profiles: stopped for today "
                  f"after LinkedIn showed a check, starts again {day_words(nxt)} by itself", nxt)]


def _ideas(today) -> list:
    import app_alerts
    out = []
    for kind, until in sorted(app_alerts.paused(today).items()):
        d = dt.date.fromisoformat(until)
        out.append(_hold("ideas_paused", "Ideas" + (f" ({kind})" if kind else ""),
                         f"Ideas Claude suggests: paused until {day_words(d)} after three No "
                         "thanks, or say 'show me ideas again'", d, "show me ideas again"))
    return out


SOURCES = (("employer_wait", lambda t, c, th: _employer_waits(t, c, th)),
           ("application_open", lambda t, c, th: _applications(t)),
           ("no_team", lambda t, c, th: _no_team(t)),
           ("person_hold", lambda t, c, th: _person_holds(t, c)),
           ("inmail", lambda t, c, th: _inmail(t, c, th)),
           ("reading_stop", lambda t, c, th: _reading(t)),
           ("ideas_paused", lambda t, c, th: _ideas(t)))


def live(today: dt.date | None = None, contacts=None, threads=None) -> list[dict]:
    """What is held back today, each {"id", "rule", "what", "until", "line", "say"}: the
    soonest to end first, those with no end day last. A source that cannot be read adds
    nothing and never breaks the rest."""
    today = today or person.today()
    if contacts is None or threads is None:
        try:
            import state
            contacts = state.load_contacts() if contacts is None else contacts
            threads = (state.load_threads() if os.path.exists(state.THREADS_CSV) else []) \
                if threads is None else threads
        except Exception:  # noqa: BLE001  no contact book: nothing about people is held
            contacts, threads = contacts or [], threads or []
    out = []
    for _rule, fn in SOURCES:
        try:
            out.extend(fn(today, contacts, threads))
        except Exception:  # noqa: BLE001  one unreadable source never hides the rest
            continue
    return sorted(out, key=lambda h: (h["until"] is None, h["until"] or "", h["what"].lower()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rules", action="store_true", help="every rule and how it ends")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", default="", help="the day to judge on (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    got = rules() if a.rules else live(dt.date.fromisoformat(a.today) if a.today else None)
    if a.json:
        print(json.dumps(got, indent=2, ensure_ascii=False))
        return 0
    if not got:
        print("Nothing is held back today.")
    for h in got:
        print(h["line"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
