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
    python3 tools/holds.py lift "hold~employer_wait~fernhill freight" --said "more at Fernhill Freight"
                                        # a pill tapped: lift that one hold now, by its id
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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
    {"id": "judged_none", "area": "jobs",
     "name": "Employers Claude judged to clear none of pay, prestige or signal",
     "where": ("tools/bar.py:judgement", "tools/bar.py:JUDGED_NONE_DAYS"),
     "ends": "{judged} days after Claude judged it, and then it is judged again",
     "why": "", "override": "ask Claude to judge the employer again",
     "missing": "a judgement with no day holds nothing, and the employer is judged again",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "declined", "area": "jobs", "name": "Employers you turned down",
     "where": ("tools/run_round.py:declined_now", "tools/network/surface.py:turned_down"),
     "ends": "", "why": "your choice, kept until you change it",
     "override": "use the trash beside the employer in Your rules",
     "missing": "an employer you never named is never turned down",
     "shown": "Settings, Your rules, Employers you've turned down"},
    {"id": "dismissed", "area": "jobs", "name": "Jobs you set aside",
     "where": ("tools/exclude.py:set_aside_days", "tools/exclude.py:set_aside_until",
               "tools/app_actions.py:_job_dismiss"),
     "ends": "{set_aside} days after you set it aside, then it is shown once more; for good "
             "only where your own words said so (never, not at all, for good)",
     "why": "", "override": "tap Bring back under Set aside in Jobs, or the bin beside it in "
                            "Your rules",
     "missing": "a job set aside with no day is counted from the day Claude first finds it "
                "so, and only that job is held, never its employer",
     "shown": "Settings, Your rules, Roles you set aside"},
    {"id": "ruled_out", "area": "jobs", "name": "Jobs a search already ruled out",
     "where": ("tools/throttle.py:is_stale_exclusion", "tools/throttle.py:RE_EVALUATED"),
     "ends": "a reason that was only a score, a pay band or a preference is read again on "
             "every search",
     "why": "", "override": "tap Bring back under What a search left out in Jobs",
     "missing": "a ruling with no reason holds only that one posting, never its employer",
     "shown": "Jobs, What a search left out"},
    {"id": "job_left_out", "area": "jobs", "name": "A job Claude stopped drafting",
     "where": ("tools/app.py:cmd_done", "tools/exclude.py:set_aside_until"),
     "ends": "{set_aside} days after Claude stopped its draft, then it is shown once more",
     "why": "", "override": "tap Look again now under Held back for now",
     "missing": "one stopped with no day is counted from the day Claude first finds it so, "
                "and only that job is held, never its employer or the same role posted "
                "elsewhere",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "duplicates", "area": "jobs", "name": "The same job posted again",
     "where": ("tools/throttle.py:RELIST_WINDOW",),
     "ends": "after {relist} days the same title at the employer counts as a new opening",
     "why": "", "override": "add it yourself with Add a job",
     "missing": "a job with no title or employer is never taken for another",
     "shown": "Jobs"},
    {"id": "no_team", "area": "jobs", "name": "Employers with no team for you where you look",
     "where": ("tools/throttle.py:do_not_target_until", "tools/network/discovery.py:presence_blocks",
               "tools/network/candidates.py:EMPTY_DAYS"),
     "ends": "on its own review day, or {dnt} days after it was found where it names none; "
             "an employer a people search found nobody who fits at is searched again after "
             "{empty} days",
     "why": "", "override": "ask Claude to look at the employer again",
     "missing": "a finding with no date holds nothing",
     "shown": "Settings, Your rules, Held back for now"},
    # ------------------------------------------------------------------ applications
    {"id": "application_open", "area": "applications",
     "name": "Other jobs at an employer you applied to",
     "where": ("tools/throttle.py:open_applications", "tools/throttle.py:SILENCE_DAYS",
               "tools/throttle.py:undated_application"),
     "ends": "when they answer, or {silence} days after you applied (or after the job's closing "
             "day) with no reply; a role scoring {override_points} points more still shows",
     "why": "", "override": "tell Claude to stop waiting on the employer",
     "missing": "an application with no date holds nothing",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "referral", "area": "applications",
     "name": "Applying cold where someone is referring you",
     "where": ("tools/throttle.py:referral_holds",),
     "ends": "", "why": "only you know when a referral is over; the job itself is never hidden",
     "override": "tell Claude the referral there is over",
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
               "tools/network/reading.py:EMPLOYER_WAIT_DAYS",
               "tools/network/state.py:REQUEST_WITHDRAW_DAYS",
               "tools/network/state.py:close_gone_cold"),
     "ends": "{per_employer} at a time; each one waiting frees their place {wait}; a "
             "connection request nobody accepted frees it after {withdraw} days at most, and "
             "a conversation with no answer in {cold} days is closed as gone cold",
     "why": "", "override": "ask Claude for more people at the employer",
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
     "override": "ask Claude to write to them again",
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
     "why": "", "override": "ask Claude to write to them again",
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
    {"id": "inmail", "area": "people", "name": "Paid LinkedIn messages, once this month's are used",
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
     "where": ("tools/app_actions.py:_msg_skip", "tools/network/state.py:dropped_until",
               "tools/network/state.py:reopen_set_aside"),
     "ends": "{set_aside} days after you set it aside, then they are offered again; for good "
             "only where your own words said so (never)",
     "why": "", "override": "tap Look again now under Held back for now, or Undo",
     "missing": "a note set aside with no day is held only until you bring it back",
     "shown": "Settings, Your rules, Held back for now"},
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
    {"id": "ideas_paused", "area": "page", "name": "Ideas Claude suggests, after you dismiss three",
     "where": ("tools/app_alerts.py:paused", "tools/app_alerts.py:PAUSE_DAYS"),
     "ends": "{pause} days after the third", "why": "",
     "override": "ask Claude to show you ideas again",
     "missing": "a Dismiss with no day does not count",
     "shown": "Settings, Your rules, Held back for now"},
    {"id": "idea_declined", "area": "page", "name": "One idea you dismissed",
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
    out = {"relist": 30, "dnt": 90, "empty": 30, "judged": 90, "set_aside": 182, "silence": 45, "override_points": 10, "app_nudges": 2,
           "reopen": 120, "per_employer": "2 people", "wait": "about two weeks after the last "
           "message, or once the follow-up then due has gone", "withdraw": 21, "cold": 90, "max_unanswered": 2, "follow_up": "6 weekdays", "quiet": 14,
           "prep": 7, "thanks": 7, "pause": 30, "news": 5}
    try:
        import throttle
        out.update(relist=throttle.RELIST_WINDOW, dnt=throttle.DO_NOT_TARGET_REVIEW_DAYS,
                   silence=throttle.SILENCE_DAYS, override_points=throttle.OVERRIDE_POINTS)
    except Exception:  # noqa: BLE001  no profile to read: the app's numbers stand
        pass
    try:
        import exclude
        out["set_aside"] = exclude.set_aside_days()
    except Exception:  # noqa: BLE001
        pass
    try:
        import bar
        out["judged"] = bar.JUDGED_NONE_DAYS
    except Exception:  # noqa: BLE001
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
                            else f"{schema.FOLLOWUP_BUSINESS_DAYS} weekdays")
        # A follow-up then due holds the place until it has gone (reading.follow_up_owed):
        # "once a follow-up is due" said the place freed on the day the follow-up was offered,
        # and new notes went beside it (issue 262).
        out["wait"] = (f"{reading.EMPLOYER_WAIT_DAYS} days after the last message, as you set, "
                       "or once the follow-up then due has gone"
                       if reading.EMPLOYER_WAIT_DAYS else
                       f"about {reading.WAITING_DAYS} days after the last message, or once the "
                       "follow-up then due by your rule has gone")
        import state
        out.update(withdraw=state.REQUEST_WITHDRAW_DAYS, cold=state.GONE_COLD_DAYS)
    except Exception:  # noqa: BLE001
        pass
    try:
        import candidates
        out["empty"] = candidates.EMPTY_DAYS
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
    it ends or why it never does, and how to lift it, one plain line. A rule with no end says
    why in plain words ("your choice, kept until you change it"), never "kept, as ..."."""
    s = _rule_settings()
    out = []
    for r in RULES:
        ends = r["ends"].format(**s)
        why = r["why"].format(**s)
        said = ends or why
        over = r["override"][:1].upper() + r["override"][1:]
        out.append(dict(r, ends=ends, why=why, line=f"{r['name']}: {said}. {over}."))
    return out


def applies(rule_id: str) -> bool:
    """Can this rule hold anything for this person? One about a bar of pay, prestige or
    signal cannot for a profile that states none (bar.applies), and listed among their rules
    it read as a bar they had set (the screen review, 2026-11-11). Every other rule can."""
    if rule_id == "judged_none":
        import bar
        return bar.applies()
    return True


# ------------------------------------------------------------------ live holds

def day_words(d: dt.date) -> str:
    """A day ahead, as the page says one: "Thu 3 Dec"."""
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def _hold(rule: str, what: str, line: str, until=None, say: str = "", lift: str = "") -> dict:
    """One hold: `line` ends at its day (or why it has none), and the reason where there is
    one; `say` is what lifts it now, asked of Claude, and `lift` the few words of the page's
    pill that asks it ("Open it now"). A line ending "or say 'more at <employer>'" left the
    person to type it (the screen review, 2026-11-09)."""
    from company_key import key
    return {"id": f"hold~{rule}~{key(what) or what.lower()}", "rule": rule, "what": what,
            "until": until.isoformat() if isinstance(until, dt.date) else (until or None),
            "line": line, "say": say, "lift": lift if say else ""}


def _employer_waits(today, contacts, threads) -> list:
    """Each employer at the person's number of people waiting: the day it opens again, or the
    follow-up that has to go first. Who holds a place is the one count every step reads
    (reading.at_employer): someone within their wait, or owed a follow-up until it goes. This
    list counted only the first, so an employer a follow-up held was missing here, and one
    whose wait was ending read "opens again" on the day the follow-up fell due and held it
    (issue 262)."""
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
        groups.setdefault(k, []).append(c)
    out = []
    for k, rows in sorted(groups.items()):
        names = [n for n in (str(c.get("company") or "").strip() for c in rows) if n]
        company = max(set(names), key=names.count) if names else k
        limit, _theirs = reading.employer_limit(company, today)
        if limit is None or len(rows) < limit:
            continue
        until: dict = {}
        owed: set = set()
        waiting, _ = reading.at_employer(company, rows, today=today, threads=threads,
                                         until=until, owed=owed)
        if len(waiting) < limit:
            continue
        # The day each one stops holding a place by themselves: the end of their wait, unless
        # a follow-up is owed to them then (or now), which holds it until it goes.
        frees, chase = [], []
        for c in waiting:
            cid = str(c.get("contact_id") or "")
            day = until.get(cid)
            if cid in owed:
                chase.append((today, c))
            elif day is not None and reading.follow_up_owed(c, by.get(cid, []), day):
                chase.append((day, c))
            elif day is not None:
                frees.append(day)
        need = len(waiting) - limit + 1
        # Why, then the day: "2 people there are waiting on a reply" (the screen review,
        # 2026-11-09: the line said when, never why).
        n = len(waiting)
        why = f"{n} people there are" if n != 1 else "1 person there is"
        frees.sort()
        if len(frees) >= need:
            opens = frees[need - 1]
            out.append(_hold("employer_wait", company,
                             f"{company}: {why} waiting on a reply, so it opens again "
                             f"{day_words(opens)}", opens, f"more at {company}", "Open it now"))
            continue
        chase.sort(key=lambda x: (x[0], str(x[1].get("name") or "")))
        # The follow-ups that have to go, soonest due first, beside every wait that ends by
        # itself; the day is when the last of them can. One follow-up frees a place: any of
        # those due by then ("Ines or Bram"); more, all of them.
        k_need = min(need - len(frees), len(chase))
        due = chase[k_need - 1][0]
        opens = max([due] + frees)
        firsts = [_first(c) for d, c in chase if d <= due]
        many = k_need > 1
        who = firsts[0] if len(firsts) == 1 else (
            ", ".join(firsts[:-1]) + (" and " if many else " or ") + firsts[-1])
        when = f", from {day_words(opens)}" if opens > today else ""
        out.append(_hold("employer_wait", company,
                         f"{company}: {why} waiting on a reply, so it opens again once your "
                         f"follow-up{'s' if many else ''} to {who} "
                         f"{'have' if many else 'has'} gone{when}", opens, f"more at {company}",
                         "Open it now"))
    return out


def _first(contact) -> str:
    """Whom a line names: their first name, or "someone"."""
    try:
        import tone
        return tone.greeting_name((contact or {}).get("name")) or "someone"
    except Exception:  # noqa: BLE001  an odd name is said as someone, never breaks the list
        return "someone"


def _applications(today) -> list:
    import throttle
    out = []
    for k, rows in sorted(throttle.open_applications(today=today).items()):
        company = str(rows[0].get("company") or k).strip()
        live = [r for r in rows if str(r.get("status") or "").strip().lower()
                in throttle.LIVE_PROCESS]
        if live:
            # The pill names what is over: "It's over" alone read as alarming and said neither
            # what nor whose (the screen review, 2026-11-11).
            out.append(_hold("application_open", company,
                             f"{company}: no new jobs there while your interviews run", None,
                             f"it's over at {company}", "My interviews there are over"))
            continue
        ends = []
        for r in rows:
            sent = throttle.as_date(throttle.applied_on(r) or r.get("date"), iso_only=True)
            closes = throttle.as_date(r.get("deadline"), iso_only=True)
            start = max(d for d in (sent, closes) if d) if (sent or closes) else None
            if start:
                ends.append(start + dt.timedelta(days=throttle.SILENCE_DAYS))
        until = max(ends) if ends else None
        when = f"until they reply or {day_words(until)}" if until else "until they reply"
        out.append(_hold("application_open", company,
                         f"{company}: no new jobs there while your application waits, {when}",
                         until, f"stop waiting on {company}", "Stop waiting"))
    return out


def _no_team(today) -> list:
    """Each employer with no team for the person where they look, one hold whatever says so:
    the search's own list (do_not_target.json) and a people search's finding kept beside the
    employer's research (discovery.presence_blocks), which held everyone there back with
    nothing here saying so. Where both say it, the hold lasts to the later day and names both
    `sources`, so Look again now lifts both: lifting one by its id brought the employer back
    with the other's day (the rules review, 2026-11-11)."""
    import throttle
    from company_key import key
    found: dict = {}
    data = throttle._read_do_not_target() or {}
    for name, e in sorted((data.get("companies") or {}).items()):
        until = throttle.do_not_target_until(e)
        if not until or until < today.isoformat():
            continue
        found.setdefault(key(name) or name.lower(), [name, []])[1].append(
            ("search", dt.date.fromisoformat(until)))
    for name, d in _no_team_found(today):
        found.setdefault(key(name) or name.lower(), [name, []])[1].append(("people", d))
    # And a check of who works there that found nobody who fits in the place (candidates.order
    # skips the employer for EMPTY_DAYS): held back with nothing here saying so, nor a way to
    # search again sooner (the rules review, 2026-11-11).
    nobody: dict = {}
    for name, d, place in _nobody_fits(today):
        found.setdefault(key(name) or name.lower(), [name, []])[1].append(("check", d))
        nobody.setdefault(key(name) or name.lower(), place)
    out = []
    for k, (name, said) in sorted(found.items()):
        d = max(day for _src, day in said)
        srcs = sorted({s for s, _ in said})
        if srcs == ["check"]:
            line = (f"{name}: a people search found nobody who fits in {nobody[k]}, searched "
                    f"again {day_words(d)}")
        else:
            by = "a search found" if srcs == ["people"] else ""
            line = (f"{name}: {by + ' ' if by else ''}no team for you where you look, "
                    f"looked at again {day_words(d)}")
        out.append(dict(_hold("no_team", name, line, d, f"look at {name} again",
                              "Look again now"), sources=srcs))
    return out


def _nobody_fits(today) -> list:
    """(employer, the day it is searched again, the place) for each check of who works there
    that found nobody who fits, while candidates.order still skips it."""
    import candidates
    out = []
    for _k, places in sorted(candidates._where().items()):
        for place, rec in sorted((places or {}).items()) if isinstance(places, dict) else ():
            # Only nobody who fits: people held back there (written to, the employer's limit of
            # people waiting) are full for now, which a reply or a close lifts (#258).
            if not candidates.nobody_fits(rec):
                continue
            try:
                when = dt.date.fromisoformat(str(rec.get("date") or "")[:10])
            except ValueError:
                continue                     # a check with no day holds nothing
            again = when + dt.timedelta(days=candidates.EMPTY_DAYS)
            if when <= today < again and str(rec.get("employer") or "").strip():
                out.append((str(rec["employer"]).strip(), again,
                            "the search" if place == "anywhere" else place.title()))
    return out


def _no_team_found(today) -> list:
    """(employer, review day) for each people search's finding of no team that holds today."""
    import glob
    import company_research
    import discovery
    out = []
    for path in sorted(glob.glob(os.path.join(glob.escape(company_research._root()), "*.json"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        # A country's own file (<key>--<cc>.json) is never read for the finding
        # (discovery.presence_ruled_out reads the plain one), nor a file of the app's own.
        if stem.startswith("_") or "--" in stem:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            # Read only where a finding is written: every page build passed here, and most
            # research files hold none.
            if '"network_presence"' not in text:
                continue
            data = json.loads(text)
        except (OSError, ValueError):
            continue
        rec = data.get("network_presence") if isinstance(data, dict) else None
        if not discovery.presence_blocks(rec, today):
            continue
        name = str(data.get("company") or "").strip() or stem.replace("-", " ").title()
        out.append((name, dt.date.fromisoformat(str(rec["review_after"])[:10])))
    return out


def _judged_none(today) -> list:
    """Each employer a chat judged to clear none of the person's bar, while that judgement
    still speaks for it (bar.judged_none): its jobs are cut and nobody there is shown."""
    import bar
    out = []
    for name, j, until in bar.judged_none(today):
        why = " ".join(str(j.get("why") or "").split())[:80].rstrip(" .")
        out.append(_hold("judged_none", name, f"{name}: judged to clear none of pay, prestige "
                         f"or signal" + (f" ({why})" if why else "") + ", so its jobs and "
                         f"people are left out until {day_words(until)}", until,
                         f"judge {name} again", "Look again now"))
    return out


def _jobs_left_out(today) -> list:
    """Each job a chat stopped drafting because it is not one the person can take (app.py done
    --left-out), until the day it is shown once more: held as one they set aside, for that
    posting alone. Judged again against today's rules on every page build, a stop on a
    degree, a place or pay was back on Jobs at the next one (the engine review, 2026-11-11)."""
    import hashlib
    import exclude
    out = []
    for k, e in (exclude.load_seen(person.state("job_scraper", "seen_jobs.json"))
                 .get("seen") or {}).items():
        if not (isinstance(e, dict) and e.get("by") == exclude.CHAT
                and e.get("basis") == "person"
                and str(e.get("status") or "").lower() == "excluded"
                and exclude.set_aside_holds(e, today)):
            continue
        url = str(e.get("url") or k)
        until = exclude.set_aside_until(e)
        title = " ".join(str(e.get("title") or "A job").split())
        company = " ".join(str(e.get("company") or "").split())
        what = f"{title} at {company}" if company else title
        why = " ".join(str(e.get("exclusion_reason") or "").split())[:80].rstrip(" .")
        h = _hold("job_left_out", what, f"{what}: not drafted" + (f" ({why})" if why else "")
                  + f", shown again {day_words(until)}", until, f"look at {what} again",
                  "Look again now")
        out.append(dict(h, id="hold~job_left_out~" + hashlib.sha1(url.encode()).hexdigest()[:12],
                        url=url))
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
        h = _hold("person_hold", name, f"{name}: {when}", lifts, f"write to {first} again",
                  "Write again")
        out.append(dict(h, contact_id=str(c.get("contact_id") or "").strip()))
    return out


def _notes_aside(today, contacts) -> list:
    """Each first note the person set aside for now, until the day it is offered again
    (state.dropped_until): "for now" held them for good, with nothing here saying so."""
    import state
    out = []
    for c in state.set_aside_for_now(contacts):
        until = state.dropped_until(c)
        if until <= today:
            continue                    # offered again on the page's next wake (reopen_set_aside)
        name = str(c.get("name") or c.get("contact_id") or "").strip()
        h = _hold("note_aside", name, f"{name}: no note for now, offered again "
                  f"{day_words(until)}", until, f"look at {name} again", "Look again now")
        out.append(dict(h, contact_id=str(c.get("contact_id") or "").strip()))
    return out


def _inmail(today, contacts, threads) -> list:
    import state
    b = state.platform_budget(contacts, threads, today)
    if not b.get("inmails_limit") or b.get("inmails_left") != 0:
        return []
    month_end = dt.date.fromisoformat(b["month_end"])
    nxt = month_end + dt.timedelta(days=1)
    # No pill: only the person knows the number LinkedIn shows (the rule says to tell Claude).
    return [_hold("inmail", "Paid LinkedIn messages", "Paid LinkedIn messages: none left this "
                  f"month, more from {day_words(nxt)}", nxt)]


def _reading(today, now=None) -> list:
    import reading
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone()
    # A stop is kept on the computer's own day, as reads write it, so it is asked for on that
    # day: asked on the person's day it vanished, or held on, whenever the two days differ.
    why = reading.stopped(local.date())
    if not why:
        return []
    # It ends at the computer's next midnight, said as the day that moment is in the person's
    # own zone: the day after the later of the two days told a person in London on a computer
    # in Auckland that reads start again a day after they do (review, 2026-11-10, R1-8).
    ends = dt.datetime.combine(local.date() + dt.timedelta(days=1), dt.time(0)).astimezone()
    z = person.home_zone()
    nxt = (ends.astimezone(z) if z else ends.astimezone()).date()
    when = "later today" if nxt <= today else day_words(nxt)
    return [_hold("reading_stop", "Reading profiles", "Reading profiles: stopped for now "
                  f"after LinkedIn showed a check, starts again {when} by itself", nxt)]


def _ideas(today) -> list:
    import app_alerts
    out = []
    for kind, until in sorted(app_alerts.paused(today).items()):
        d = dt.date.fromisoformat(until)
        out.append(_hold("ideas_paused", "Ideas" + (f" ({kind})" if kind else ""),
                         "Ideas Claude suggests: paused after you dismissed three, until "
                         f"{day_words(d)}", d, "show me ideas again", "Show ideas now"))
    return out


SOURCES = (("employer_wait", lambda t, c, th: _employer_waits(t, c, th)),
           ("application_open", lambda t, c, th: _applications(t)),
           ("no_team", lambda t, c, th: _no_team(t)),
           ("judged_none", lambda t, c, th: _judged_none(t)),
           ("job_left_out", lambda t, c, th: _jobs_left_out(t)),
           ("person_hold", lambda t, c, th: _person_holds(t, c)),
           ("note_aside", lambda t, c, th: _notes_aside(t, c)),
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


# ------------------------------------------------------------------ lifting one now

def _plain(words) -> str:
    return " ".join(str(words or "").lower().replace("\u2019", "'").split()).strip(" .!?'\"")


def find(words: str, held: list) -> list:
    """The holds `words` ask to lift: the one with that id, else every one whose pill says
    those words (`say`), read loosely. An id names one hold; words can name two (an employer
    both judged and with no team found, two people on hold called Sam), so the page sends the
    id (the rules review, 2026-11-11)."""
    w = _plain(words)
    by_id = [h for h in held if w and w == h["id"].lower()]
    return by_id or [h for h in held if w and w == _plain(h.get("say"))]


def lift(words: str, today: dt.date | None = None, said: str = "") -> str:
    """Lift the one hold `words` name (its id, as the page's pill sends it, or its pill's
    words, `say`) now, the way its rule is lifted, and say in one line what changed: what
    Claude runs when the person taps a pill under Held back for now. Raises ValueError, in
    plain words, when no hold or more than one matches, or the hold has no pill (only time,
    or a number the person must tell, ends it). `said`, the person's words (the pill's own
    where none are given), is kept with every change that keeps them."""
    today = today or person.today()
    held = live(today)
    got = find(words, held)
    if not got:
        said = "; ".join(f"'{h['say']}'" for h in held if h.get("say")) or "nothing"
        raise ValueError(f"nothing held back today is lifted by '{words}': the ones that can "
                         f"be are {said}")
    if len(got) > 1:
        raise ValueError("more than one hold has those words: name one by its id: "
                         + "; ".join(f"{h['id']} ({h['line']})" for h in got))
    h = got[0]
    if not h.get("say"):
        raise ValueError(f"{h['line']}: nothing lifts this one but its day")
    kept = said or (h["say"] if _plain(words) == h["id"].lower() else words)
    return LIFTS[h["rule"]](h, today, " ".join(str(kept).split()))


def _lift_employer_wait(h, today, words) -> str:
    import reading
    import state
    contacts = state.load_contacts()
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    owed: set = set()
    waiting, _ = reading.at_employer(h["what"], contacts, today=today, threads=threads,
                                     owed=owed)
    # The limit counts the notes already drafted for people there as well as the people
    # waiting (reading.employer_full_line): room for the waiting alone left the next note
    # refused after the tap wherever one was drafted.
    k = state.row_company_key({"company": h["what"]})
    drafted = [c for c in contacts if state.row_company_key(c) == k
               and str(c.get("status") or "not_contacted").strip() == "not_contacted"
               and re.match(r"^[\w.-]+$", str(c.get("contact_id") or ""))
               and os.path.isfile(reading.draft_path(str(c["contact_id"])))]
    up_to = len(waiting) + len(drafted) + 1
    # The room ends by itself once the waiting it was made beside has cleared: the last day
    # anyone waiting there now holds the employer (reading.waiting_until). Kept with no end,
    # it capped the employer for good, even below a number the person raised since.
    # Someone owed a follow-up holds their place until it goes, a day nobody knows: the room
    # beside them lasts one follow-up wait from today (issue 262). Their own wait ended
    # already, and a room ending then ended before it was made.
    by = state.by_contact(threads)
    ends = [state.follow_up_on(today) if str(c.get("contact_id") or "") in owed else
            reading.waiting_until(c, by.get(str(c.get("contact_id") or "").strip(), []))
            for c in waiting]
    ends = [d for d in ends if d]
    until = max(ends) if ends else (dt.date.fromisoformat(h["until"]) if h.get("until")
                                    else today)
    reading.set_more_at(h["what"], f"{words} (Held back for now)", up_to=up_to, today=today,
                        until=until)
    notes = f", beside {len(drafted)} note{'s' if len(drafted) != 1 else ''} already drafted" \
        if drafted else ""
    return (f"{h['what']}: one more person there may be written to now{notes}, {up_to} in all "
            f"while nobody there has answered, until {day_words(until)}")


def _lift_application(h, today, words) -> str:
    import csv_store
    import throttle
    from company_key import key
    k = key(h["what"])
    rows = csv_store.read_rows(throttle.TRACKER)
    mine = [r for r in rows if key(r.get("company")) == k
            and str(r.get("status") or "").strip().lower() not in throttle.FINAL
            and str(r.get("status") or "").strip().lower() not in throttle.UNSENT]
    if any(str(r.get("status") or "").strip().lower() in throttle.LIVE_PROCESS for r in mine):
        # How a hiring process ended is theirs to say: never written as a guess.
        raise ValueError(f"ask how it ended at {h['what']} (no offer, an offer turned down, "
                         "they stepped back), then record it as /outcome does: that ends the hold")
    # The person's own time beside their own day: the computer's clock put an hour of another
    # zone beside it (the rules review, 2026-11-11).
    now, z = dt.datetime.now(dt.timezone.utc), person.home_zone()
    at = (now.astimezone(z) if z else now.astimezone()).strftime("%H:%M")
    for r in mine:
        r["applied_on"] = throttle.applied_on(r) or str(r.get("date") or "")[:10]
        r["status"] = "no_response"
        r["confirmed_by"], r["confirmed_at"] = "person-said", f"{today.isoformat()} {at}"
        note = f"{today.isoformat()}: stopped waiting, as you said ({words})"
        r["notes"] = ((r.get("notes") or "").rstrip() + " | " + note).strip(" |")
    csv_store.write_rows(throttle.TRACKER, rows, list(dict.fromkeys(
        csv_store.header(throttle.TRACKER) + list(throttle.CONFIRM_COLUMNS))))
    return (f"{h['what']}: no longer waited on, so its other jobs show again; the application "
            "is marked as no reply, and a reply from them opens it again")


def _lift_no_team(h, today, words) -> str:
    """Both of what says the employer has no team for the person (`sources`), lifted together:
    lifting one left the other holding it."""
    import tempfile
    import throttle
    from company_key import key
    yesterday = (today - dt.timedelta(days=1)).isoformat()
    sources = h.get("sources") or [h.get("source") or "search"]
    if "search" in sources:
        data = throttle._read_do_not_target() or {}
        companies = data.get("companies") or {}
        name = next((n for n in companies if key(n) == key(h["what"])), None)
        if name is None:
            raise ValueError(f"{h['what']} is not on the search's own list any more")
        companies[name] = dict(companies[name], review_after=yesterday,
                               looked_again=today.isoformat(), looked_again_because=words)
        path = throttle.DO_NOT_TARGET
        tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path) or ".", delete=False,
                                          encoding="utf-8", newline="\n", suffix=".tmp")
        with tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.write("\n")
        os.replace(tmp.name, path)
    if "check" in sources:
        import candidates
        candidates.look_again(h["what"])
    if "people" in sources:
        import company_research
        data, _age, _fresh = company_research.load(h["what"])
        rec = dict(data.get("network_presence") or {}, review_after=today.isoformat(),
                   looked_again=today.isoformat(), looked_again_because=words)
        company_research.save(h["what"], {"network_presence": rec})
    return (f"{h['what']}: looked at again from today; its jobs and people are judged afresh "
            "by the next search")


def _lift_judged_none(h, today, words) -> str:
    import bar
    bar.unjudge(h["what"])
    return (f"{h['what']}: Claude's judgement taken back; judge it again now with what you "
            f"know today (python3 tools/bar.py judge \"{h['what']}\" <pay|prestige|signal|none> "
            "\"<why>\"), and nothing is cut for it until then")


def _lift_job_left_out(h, today, words) -> str:
    import exclude
    exclude.lift(urls=[h["url"]], why=f"{words} (Held back for now)", today=today.isoformat(),
                 path=person.state("job_scraper", "seen_jobs.json"))
    return f"{h['what']}: back on Jobs from today"


def _lift_person(h, today, words) -> str:
    import state
    cid = h.get("contact_id") or ""
    contacts = state.load_contacts()
    row = next((c for c in contacts if str(c.get("contact_id") or "").strip() == cid), None)
    if row is None:
        raise ValueError(f"{h['what']} is not in your contacts any more")
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    state.put_next(row, state.by_contact(threads).get(cid, []), "", "")
    state.save_contacts(contacts)
    return f"{h['what']}: off hold; what is owed them follows your follow-up rule from now"


def _lift_note_aside(h, today, words) -> str:
    import state
    cid = h.get("contact_id") or ""
    contacts = state.load_contacts()
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    state.reopen(contacts, threads, cid, today, f"{words} (Held back for now)")
    state.save_contacts(contacts)
    return f"{h['what']}: offered again from today, with the note as it was"


def _lift_ideas(h, today, words) -> str:
    import app_alerts
    app_alerts.unpause(today)
    return "Ideas Claude suggests: offered again from today"


LIFTS = {"employer_wait": _lift_employer_wait, "application_open": _lift_application,
         "no_team": _lift_no_team, "judged_none": _lift_judged_none,
         "job_left_out": _lift_job_left_out, "person_hold": _lift_person, "note_aside": _lift_note_aside,
         "ideas_paused": _lift_ideas}


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["lift"]:
        lp = argparse.ArgumentParser(prog="holds.py lift",
                                     description="lift one hold now, by its pill's words or id")
        lp.add_argument("words", help="the hold's id, as the pill sent it, or its words")
        lp.add_argument("--said", default="", help="the person's own words, kept with the change")
        lp.add_argument("--today", default="", help="the day to judge on (YYYY-MM-DD)")
        la = lp.parse_args(argv[1:])
        try:
            print(lift(la.words, dt.date.fromisoformat(la.today) if la.today else None,
                       la.said))
        except ValueError as e:
            print(f"holds: not lifted: {e}")
            return 1
        return 0
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
        # Claude reads this: what lifts each one now, said after its line.
        print(h["line"] if a.rules else
              h["line"] + (f". To lift it now, say '{h['say']}'." if h.get("say") else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
