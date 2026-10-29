"""On each card of the page: what is wrong or urgent, and at most one suggestion.

UX_DECISIONS (2026-10-25), "Crucial suggestions without pressing Tweak". Three levels, none
a pop-up:

1. `alerts`, level 1, wrong or urgent: a check that failed, an apply link that has closed or
   is not the employer's own, a closing date today or tomorrow, a referral in flight at that
   employer, an interview within a day with no prep, a note over its limit or written before
   the profile was read (with "Paste their profile"), a reply owed more than three days, a
   networking call today or tomorrow with no prep. Each says what and why, with one action
   and its cost. They count in To do and stay whatever the Suggestions setting says.
2. `suggest`, level 2, one at most, with its evidence: someone there who replied, a tool the
   person holds beside one the posting asks for that their resume leaves out, a clear
   difference in which of their own messages drew replies (what_works, only with enough
   data), a referrer owed word of where the process they started has got to. Use / No
   thanks; No thanks is for good for that suggestion (`suggest.dismiss`, kept in
   profile/app.json and in the page's database), three of one kind within 30 days pause
   that kind for 30 days, and at most three new ones reach the page a day.
3. Nice to have: inside Tweak as (Recommended), on the page, never here.

Nothing here calls a model, fetches anything or writes anything while building: every
source is code that already runs (the throttle's warm routes and referral holds, the link
check staging recorded, the page-count checks, bridges, what_works).

    alert   {level: 1, id, kind, text, why, action, cost, contact?}
    suggest {level: 2, id, kind, text, why, action, cost, since, rev}
    action  {type: "work", label, kind, id, title, args}   queue a work item (page_db kinds)
          | {type: "act", label, action, item, value}       an ACTIONS entry, applied once
          | {type: "go", label, to, item}                   open that section at that item
          | null                                            nothing to press: it says what
    cost    {state: 0..3, label}                            TWEAKS.md 1.1, in plain words
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re

import person

# TWEAKS.md 1.1: what the person reads beside a button, never "tokens".
COSTS = {0: "Free, instant", 1: "A little Claude, about 30 seconds",
         2: "Some Claude, about a minute or two", 3: "A lot of Claude, several minutes"}
# How much of Claude each kind of work takes, by the same four states.
WORK_COST = {"search": 2, "draft": 3, "resume_for_contact": 3, "prep": 3, "network": 3,
             "reply": 2, "follow_up": 2, "brief": 2, "research": 2, "update": 1, "talk": 1,
             "files": 1, "tweak": 2,
             # One posting scored; the resume for no named role (no drafting call); a look
             # over their own profile.
             "evaluate": 1, "general_resume": 1, "own_profile": 2,
             # The page's new code built and published by the listener: no drafting.
             "republish": 1,
             # A change to their own profile, and a fresh resume made from it.
             "profile": 2}

SUGGEST_PER_DAY = 3
PAUSE_AFTER = 3
PAUSE_DAYS = 30
# Most valuable first, when more are waiting than may be shown today.
ORDER = ("warm", "tell_referrer", "near", "works")
SETTING = "suggestions"           # person.json; its choices are app_model.SETTINGS
APP_JSON = "app.json"
NO_KEY = "suggest_no"


def cost(state) -> dict | None:
    return None if state is None else {"state": int(state), "label": COSTS[int(state)]}


def work(kind: str, label: str, title: str, args: dict, wid: str = "") -> dict:
    return {"type": "work", "label": label, "kind": kind, "id": wid or "", "title": title,
            "args": args}


def act(label: str, action: str, item: str, value=None) -> dict:
    return {"type": "act", "label": label, "action": action, "item": item, "value": value}


def go(label: str, to: str, item: str = "") -> dict:
    return {"type": "go", "label": label, "to": to, "item": item}


def _cost_of(action) -> dict | None:
    if not action:
        return None
    if action["type"] == "work":
        return cost(WORK_COST.get(action["kind"], 2))
    return cost(0)


def alert(kind: str, item_id: str, text: str, why: str, action=None) -> dict:
    return {"level": 1, "id": f"al-{kind}-{item_id}", "kind": kind, "text": text, "why": why,
            "action": action, "cost": _cost_of(action)}


def suggestion(kind: str, item_id: str, evidence, text: str, why: str, action) -> dict:
    import app_model
    h = hashlib.sha256(repr(evidence).encode("utf-8")).hexdigest()[:8]
    sid = f"sg-{kind}-{item_id}-{h}"
    return {"level": 2, "id": sid, "kind": kind, "text": text, "why": why, "action": action,
            "cost": _cost_of(action), "since": None, "rev": app_model.rev_of(sid, text)}


def _first(name) -> str:
    import app_model
    return app_model.first_name(name)


def _day(value) -> dt.date | None:
    from dates import as_date
    return as_date(value, iso_only=True) or as_date(value)


def _soon(value, today: dt.date) -> str:
    """"today" or "tomorrow" when `value` is one of them, else ""."""
    d = _day(value) if value else None
    if d is None:
        return ""
    return {0: "today", 1: "tomorrow"}.get((d - today).days, "")


# ------------------------------------------------------------------ who is warm there


def _hold(ctx, company):
    """(contact row, first name) of whoever has put the person's name forward there."""
    from company_key import key
    _, _, holds = ctx.network
    k = key(company)
    if k not in holds:
        return None
    who = next((c for c in ctx.contacts if c.get("contact_id") and
                ctx.live.get(c["contact_id"]) == "referral_in_progress"
                and key(c.get("company")) == k), {})
    return who, _first(who.get("name")) or "someone there"


def _replied(ctx, company):
    """(contact row, first name, the day they last replied) of whoever there replied most
    lately: the throttle's warm set (throttle.RESPONDED), from the contact book itself."""
    import throttle
    from company_key import key
    from network import state
    k = key(company)
    best = None
    for c in ctx.contacts:
        cid = str(c.get("contact_id") or "").strip()
        if not cid or key(c.get("company")) != k or ctx.live.get(cid) not in throttle.RESPONDED:
            continue
        on = max((str(t.get("date") or "")[:10] for t in ctx.by_contact.get(cid) or []
                  if state.said_something(t)), default="")
        if best is None or on > best[2]:
            best = (c, _first(c.get("name")) or "someone there", on)
    return (best[0], best[1], best[2] or None) if best else None


def _hold_alert(ctx, item_id, company):
    """Level 1 on every job and draft at an employer where a referral is in flight: the
    hold's own reason (throttle.referral_holds), the person named by first name only, and
    the contact linked."""
    import app_model
    from company_key import key
    got = _hold(ctx, company)
    if not got:
        return None
    who, name = got
    cid = str(who.get("contact_id") or "")
    _, _, holds = ctx.network
    reason = app_model.scrub(holds.get(key(company)) or "", ctx.names)
    reason = re.sub(r"^referral in progress:\s*", "", reason).replace("the candidate's", "your")
    a = alert("referral_hold", item_id, f"{name} has put your name forward at {company}: "
              "do not apply cold.", (reason.strip() + " " if reason.strip() else "")
              + "A cold application lands as a second, worse record of you, and the referral "
              "is the one that loses.", go(f"Ask {name} first", "people", cid))
    a["contact"] = cid
    return a


def _warm_suggest(ctx, item_id, company):
    got = _replied(ctx, company)
    if not got:
        return None
    c, name, on = got
    cid = str(c.get("contact_id") or "").strip()
    when = f" on {on}" if on else ""
    # Their reply is not the last word when a message of the person's own went after it and
    # has no answer: what goes next follows that message up (compose.thread_findings). Told
    # only "replied on <a year ago>", a draft re-announced what an August note had said
    # (2026-10-26).
    from network import compose
    waiting = compose.unanswered_ours(ctx.by_contact.get(cid) or [])
    if waiting is not None:
        title = (f"{name} at {company} replied to you{when}, and your message of "
                 f"{waiting.get('date')} has no answer yet: follow it up about this role "
                 "before applying.")
    else:
        title = f"{name} at {company} replied to you{when}: ask {name} about this role before applying."
    return suggestion("warm", item_id, cid, title,
                      "A reply is what makes a route warm, and a cold application first "
                      "spends it.", work("reply", f"Write to {name}", f"Write to {name} at "
                                         f"{company}", {"contact": cid}, f"reply~{cid}"))


# ------------------------------------------------------------------ the cards


def for_job(ctx, item: dict) -> tuple[list, dict | None]:
    jid, company, status = item["id"], item["company"], item["status"]
    out = []
    if status in ("applied", "dismissed"):
        return out, None
    held = _hold_alert(ctx, jid, company)
    if held:
        out.append(held)
    if item["apply"]["status"] == "closed":
        out.append(alert("closed", jid, "This posting has closed.",
                         "The employer's own board no longer lists it"
                         + (f" (checked {item['apply']['checked_on']})."
                            if item["apply"].get("checked_on") else "."),
                         act("Set it aside", "job.dismiss", jid)))
    when = _soon(item.get("deadline"), ctx.today)
    if when:
        out.append(alert("deadline", jid, f"Applications close {when}.",
                         f"The posting gives {item['deadline']} as its closing date.",
                         go("Open its draft", "ready") if status == "ready"
                         else go("Draft it", "jobs", jid)))
    return out, (None if held else _warm_suggest(ctx, jid, company))


_NOT_OWN = {"aggregator": "lists other sites' jobs", "board": "asks you to sign in"}


def _host(url: str) -> str:
    m = re.match(r"^https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else "that site"


def for_ready(ctx, item: dict, row: dict, folder: str) -> tuple[list, dict | None]:
    rid, company = item["id"], item["company"]
    if item["status"] != "drafted":
        return [], None
    out = []
    held = _hold_alert(ctx, rid, company)
    if held:
        out.append(held)
    checks = item["checks"]
    if not checks["passed"]:
        again = "Make it" if checks["line"].startswith("Not made yet") else "Make it again"
        out.append(alert("checks", rid, checks["line"] + ".",
                         "Both documents are made and read back at the right length before "
                         "anything is sent.",
                         work("draft", again, f"{again}: {company}",
                              {"company": company, "role": item["role"], "application": rid,
                               "redo": True}, f"draft~{rid}")))
    link = item["apply"]
    if link["status"] == "closed":
        out.append(alert("closed", rid, "This posting has closed.",
                         "The employer's own board no longer lists it"
                         + (f" (checked {link['checked_on']})." if link.get("checked_on")
                            else "."), act("Not applying", "ready.not_applying", rid)))
    elif link["kind"] in _NOT_OWN:
        out.append(alert("not_own_link", rid, "This apply link is not the employer's own.",
                         f"{_host(link['url'])} {_NOT_OWN[link['kind']]}: apply on "
                         f"{company}'s own site."))
    elif not link["url"]:
        out.append(alert("no_link", rid, "There is no apply link on file.",
                         "Without it the application cannot go where the employer reads it."))
    sug = None if held else _warm_suggest(ctx, rid, company)
    return out, sug or _near_suggest(rid, item, row, folder)


def _near_suggest(rid: str, item: dict, row: dict, folder: str):
    """A tool the person holds beside one the posting asks for, when the resume leaves the
    held one out (bridges.unheld_asked: only what the profile holds is ever offered)."""
    import app_model
    text = app_model.read_text(os.path.join(folder, "job_posting.md"))
    tex = str(row.get("cv_file") or "").strip()
    resume = app_model.read_text(person.state(*tex.split("/"))) if tex else ""
    if not text or not resume:
        return None
    try:
        import bridges
        asked = bridges.unheld_asked(text)
    except Exception:  # noqa: BLE001  a profile without the skill map has nothing to offer
        return None
    low = resume.casefold()
    for a in asked:
        have = [h for h in a.get("have") or [] if h.casefold() not in low]
        if not a.get("have") or not have or len(have) < len(a["have"]):
            continue                    # nothing held beside it, or the resume shows it
        h = have[0]
        return suggestion("near", rid, (a["skill"], h), f"The posting asks for {a['skill']}; "
                          f"you have {h}, and your resume does not show it. Add {h}?",
                          f"{h} is on your profile and is the same kind of tool.",
                          work("tweak", f"Add {h}", f"Add {h}: {item['company']}",
                               {"target": {"id": rid, "output": "resume",
                                           "company": item["company"], "rev": item["rev"]},
                                "text": f"Show {h} where the posting asks for {a['skill']}."},
                               f"tweak~{rid}~near"))
    return None


_CHANNEL = {"linkedin_note": "LinkedIn connection note", "linkedin_message": "LinkedIn message",
            "inmail": "InMail", "email": "email"}


# What the page asks for a pasted profile (CAPABILITY_MAP G14): the words for phone and web,
# where the page cannot read LinkedIn itself.
PASTE_ASK = ("Open their LinkedIn page, select everything on it, copy, and paste it here. "
             "Only what a note can rest on is kept; the paste itself is not.")


def paste_profile(item_id: str, first: str) -> dict:
    """The "Paste their profile" action: profile.pasted with the words the page asks for.
    It logs the read in code, then queues the note's rewrite on it (`network` work)."""
    a = act(f"Paste {first}'s profile" if first else "Paste their profile",
            "profile.pasted", item_id)
    a.update({"input": "text", "ask": PASTE_ASK})
    return a


def for_message(ctx, item: dict) -> tuple[list, dict | None]:
    mid = item["id"]
    out = []
    if item.get("hold"):
        a = alert("read_first", mid, item["hold"] + ".",
                  "A note written before their profile was read can get them wrong.",
                  paste_profile(mid, item.get("first_name") or ""))
        # Logging the paste is free; the rewrite it queues is a chat's.
        a["cost"] = cost(WORK_COST["network"])
        out.append(a)
    if item.get("limit") and item["chars"] > item["limit"]:
        out.append(alert("too_long", mid, f"{item['chars']} characters: over the "
                         f"{item['limit']} a {_CHANNEL.get(item['channel'], 'message')} "
                         "allows.", "LinkedIn refuses a note over its limit; it cuts nothing.",
                         work("tweak", "Shorten it", f"Shorten the note to {item['first_name']}",
                              {"target": {"id": mid, "output": "message",
                                          "contact": item["contact"], "rev": item["rev"]},
                               "text": f"Under {item['limit']} characters."},
                              f"tweak~{mid}~limit")))
    return out, (_works_suggest(ctx, item) if item["kind"] == "first_note" else None)


# The features of a first note a rewrite can change; route, channel and tier it cannot.
_CHANGEABLE = {"length": "Shorter: {best}.", "question": "End with one short question."}
_SAID = {"under 200 characters": "under 200 characters", "200-300 characters":
         "of 200 to 300 characters", "over 300 characters": "over 300 characters",
         "asks a question": "that ask a question", "no question": "with no question"}


def _clear_gaps(ctx) -> dict:
    """{feature: (best group, its rate, worst group, its rate)} for each feature of the
    person's own first notes whose best and worst groups differ clearly, counted the way
    what_works.brief_messages counts them (the same comparisons, the same test)."""
    def make():
        import what_works as ww
        cases = [c for c in ww.message_cases(ctx.contacts, ctx.threads, ctx.today)
                 if c["attempt"] == "opener"]
        tested = []
        for f in ("route", "found_via", "channel", "tier", "length", "question"):
            groups: dict = {}
            for c in cases:
                if c.get(f):
                    g = groups.setdefault(c[f], [0, 0])
                    g[0] += 1 if c["won"] else 0
                    g[1] += 1
            big = [(v, h, n) for v, (h, n) in groups.items() if n >= ww.MIN_GROUP]
            if len(big) >= 2:
                tested.append((f, big))
        comparisons = sum(len(b) * (len(b) - 1) // 2 for _f, b in tested)
        out = {}
        for f, big in tested:
            best = max(big, key=lambda x: (x[1] / x[2], x[2]))
            worst = min(big, key=lambda x: (x[1] / x[2], -x[2]))
            if best is not worst and ww.clear(best[1], best[2], worst[1], worst[2], comparisons):
                out[f] = (best[0], _rate(best[1], best[2]), worst[0],
                          _rate(worst[1], worst[2]))
        return out
    return ctx._once("alerts_gaps", make)


def _rate(hit: int, n: int) -> str:
    return f"{hit} of {n}, {round(100 * hit / n)}%"


def _works_suggest(ctx, item: dict):
    import what_works as ww
    gaps = _clear_gaps(ctx)
    text = item["text"]
    mine = {"length": ww.length_group(text),
            "question": "asks a question" if "?" in text else "no question"}
    for f, how in _CHANGEABLE.items():
        if f not in gaps or gaps[f][2] != mine[f]:
            continue
        best, b_rate, worst, w_rate = gaps[f]
        return suggestion("works", item["id"], (f, best, worst),
                          f"Your first notes {_SAID.get(best, best)} drew more replies "
                          f"({b_rate}) than ones {_SAID.get(worst, worst)} ({w_rate}), and "
                          "this one is like the second. Change it?",
                          "Counted from your own messages; the gap is unlikely to be chance.",
                          work("tweak", "Change it", f"Rework the note to {item['first_name']}",
                               {"target": {"id": item["id"], "output": "message",
                                           "contact": item["contact"], "rev": item["rev"]},
                                "text": how.format(best=_SAID.get(best, best))},
                               f"tweak~{item['id']}~works"))
    return None


# A reply waiting longer than this is a level-1 alert on the contact (FUNCTIONS_SPEC 1.4).
REPLY_OWED_DAYS = 3


def _their_last_word(ctx, cid: str) -> dt.date | None:
    from network import state
    days = [_day(str(t.get("date") or "")[:10]) for t in ctx.by_contact.get(cid) or []
            if state.said_something(t)]
    days = [d for d in days if d]
    return max(days) if days else None


def for_person(ctx, item: dict) -> tuple[list, dict | None]:
    """On a contact: a reply owed for more than REPLY_OWED_DAYS days, a call today or
    tomorrow with no prep, and, as the one suggestion, telling a referrer where the process
    they started has got to."""
    cid, status = item["id"], item["status"]
    name = item.get("first_name") or "They"
    out = []
    if status == "replied_needs_response":
        said = _their_last_word(ctx, cid)
        days = (ctx.today - said).days if said else None
        if days is not None and days > REPLY_OWED_DAYS:
            out.append(alert("reply_owed", cid, f"{name} replied {days} days ago and is "
                             "waiting for your answer.",
                             "A reply left for a week reads as lost interest, and this "
                             "conversation is the way to a referral.",
                             work("reply", "Draft a reply", f"Reply to {name}",
                                  {"contact": cid}, f"reply~{cid}")))
    call = item.get("call") or {}
    when = _soon(call.get("day"), ctx.today) if call.get("day") else ""
    if when and not call.get("prep"):
        out.append(alert("call_no_prep", cid, f"Your call with {name} is {when} and there is "
                         "no prep yet.", f"Booked for {call['day']}.",
                         work("prep", "Prepare for the call", f"Call prep: {name}",
                              {"contact": cid, "call": True}, f"prep~call~{cid}")))
    return out, (None if out else _referrer_update(ctx, item))


def _referrer_update(ctx, item: dict):
    """The one person owed news unasked: whoever put the person forward, once something
    has happened in that process since the person last wrote to them."""
    import app_model
    from network import state
    cid = item["id"]
    if (ctx.live.get(cid) or item["status"]) != "referral_in_progress":
        return None
    msgs = ctx.by_contact.get(cid) or []
    last_out = max((str(m.get("date") or "")[:10] for m in msgs
                    if state.direction(m) == "out"), default="")
    news = app_model.process_news(ctx, cid)
    if not news or news["on"] <= last_out:
        return None
    name = item.get("first_name") or "them"
    return suggestion("tell_referrer", cid, (news["on"], news["what"]),
                      f"Tell {name} where it stands: {news['what']}.",
                      f"{name} put your name forward, and has heard nothing from you since "
                      f"{last_out or 'then'}.",
                      work("reply", f"Write to {name}", f"An update for {name}",
                           {"contact": cid, "update": news["what"]}, f"reply~{cid}"))


def for_interview(ctx, item: dict) -> tuple[list, dict | None]:
    if item.get("past"):
        return [], None
    when = _soon(item.get("when"), ctx.today)
    if not when or item.get("prep"):
        return [], None
    iid = item["id"]
    stage = item.get("next_stage") or "the next stage"
    return [alert("no_prep", iid, f"Your {item['company']} interview is {when} and there is "
                  "no prep yet.", f"{stage[:1].upper() + stage[1:]} on {item['when']}.",
                  work("prep", "Prepare me", f"Interview prep: {item['company']}, "
                       f"{item['role']}", {"interview": iid}, f"prep~{iid}"))], None


# ------------------------------------------------------------------ what may be offered


def _app_json() -> str:
    import app_setup
    return os.path.join(app_setup.profile_dir(), APP_JSON)


def dismissed() -> dict:
    """{suggestion id: {on, kind}}: every No thanks, from profile/app.json."""
    import app_setup
    got = app_setup.read_json(_app_json(), {}).get(NO_KEY)
    return got if isinstance(got, dict) else {}


def dismiss(sid: str, kind: str, on: dt.date) -> dict | None:
    """Record a No thanks. Returns what was there before (None for nothing)."""
    import app_setup
    data = app_setup.read_json(_app_json(), {})
    no = data.get(NO_KEY) if isinstance(data.get(NO_KEY), dict) else {}
    before = no.get(sid)
    no[sid] = {"on": on.isoformat(), "kind": kind}
    data[NO_KEY] = no
    app_setup.write_json(_app_json(), data)
    return before


def undismiss(sid: str, before=None) -> None:
    import app_setup
    data = app_setup.read_json(_app_json(), {})
    no = data.get(NO_KEY) if isinstance(data.get(NO_KEY), dict) else {}
    if before:
        no[sid] = before
    else:
        no.pop(sid, None)
    data[NO_KEY] = no
    app_setup.write_json(_app_json(), data)


def paused(today: dt.date, no: dict | None = None) -> dict:
    """{kind: the day it is offered again}: three No thanks of one kind within 30 days pause
    it for 30 days from the third."""
    no = dismissed() if no is None else no
    by: dict = {}
    for e in no.values():
        d = _day((e or {}).get("on"))
        if d and (today - d).days < PAUSE_DAYS * 2:
            by.setdefault(str(e.get("kind") or ""), []).append(d)
    out = {}
    for kind, days in by.items():
        days.sort()
        for i in range(PAUSE_AFTER - 1, len(days)):
            if (days[i] - days[i - PAUSE_AFTER + 1]).days < PAUSE_DAYS:
                until = days[i] + dt.timedelta(days=PAUSE_DAYS)
                if until > today:
                    out[kind] = until.isoformat()
    return out


def setting() -> str:
    try:
        got = str(person.get(SETTING, "") or "").strip().lower()
    except person.NoProfile:
        return "on"
    return got if got in ("on", "urgent", "off") else "on"


CARDS = (("jobs", lambda m: (m.get("jobs") or {}).get("rows") or []),
         ("ready", lambda m: m.get("ready") or []),
         ("messages", lambda m: m.get("messages") or []),
         ("interviews", lambda m: m.get("interviews") or []),
         ("people", lambda m: m.get("people") or []))


def offer(model: dict, today: dt.date, shown: dict | None = None) -> None:
    """Decide, in place, which suggestions reach the page: none when the setting says only
    urgent or off; never one the person said No thanks to, nor one of a paused kind; every
    one already on the page (`shown`, {id: the day it first showed}, from the page's
    database) keeps its day; and at most SUGGEST_PER_DAY new ones a day, most valuable
    first. A suggestion that waits is offered on a later day."""
    shown = shown or {}
    on = setting() == "on"
    no = dismissed()
    stop = paused(today, no)
    waiting = []
    for _name, rows in CARDS:
        for item in rows(model):
            s = item.get("suggest")
            if not s:
                continue
            if not on or s["id"] in no or s["kind"] in stop:
                item["suggest"] = None
            elif s["id"] in shown:
                s["since"] = shown[s["id"]]
            else:
                waiting.append(item)
    today_s = today.isoformat()
    room = SUGGEST_PER_DAY - sum(1 for d in shown.values() if d == today_s)
    waiting.sort(key=lambda i: ORDER.index(i["suggest"]["kind"])
                 if i["suggest"]["kind"] in ORDER else len(ORDER))
    for item in waiting:
        if room > 0:
            item["suggest"]["since"] = today_s
            room -= 1
        else:
            item["suggest"] = None


def shown_in(view: dict) -> dict:
    """{suggestion id: since} of every suggestion in the page's current view documents
    (`view/<section>` from the database), so tomorrow's cap counts what is already there."""
    import page_db
    out = {}
    for name, _rows in CARDS:
        # page_db.load: {doc id: {data: the document, version}}; the document holds the
        # section under its own `data`, or in parts when it was too big for one.
        data = page_db.joined(view or {}, name)
        items = data.get("rows") if isinstance(data, dict) else data
        for item in items if isinstance(items, list) else []:
            s = item.get("suggest") if isinstance(item, dict) else None
            if isinstance(s, dict) and s.get("id") and s.get("since"):
                out[str(s["id"])] = str(s["since"])
    return out
