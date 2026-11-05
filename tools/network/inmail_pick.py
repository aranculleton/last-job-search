#!/usr/bin/env python3
"""Who in a people search is worth one of the person's few InMails, instead of a note.

A discovery run drafted a connection note for everyone it found, whatever the person's
LinkedIn plan, and an InMail only when the person asked for one in words (the maintainer,
2026-11-05). On a plan with InMail credits the run now decides by itself, here, in code:
someone is worth a credit when they are worth a lot (a recruiter or a hiring leader at an
employer the person wants) and a connection request is a weak way to reach them (their
page offers no Connect, nothing connects them to the person, or a request to them has
sat unaccepted). Never on a free plan, never past the credits left less a small reserve,
and at most `PER_RUN` in one run.

The decision is kept beside the draft (`documents/network/<contact_id>/inmail.json`):
why, the day, which of the two messages is the one to send, and the other one, so the
page can switch a person between the InMail and the connection note without a chat
(`switch`), freeing the credit or spending one.

    python3 tools/network/inmail_pick.py pick <contact_id> ... [--today YYYY-MM-DD]
    python3 tools/network/inmail_pick.py use <contact_id> <file|-> [--card-only]
    python3 tools/network/inmail_pick.py switch <contact_id> connection|inmail
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

# One credit kept back for the person's own use (someone they meet, a reply that needs
# one): the run never spends the last.
RESERVE = 1
# At most this many InMails a run: the rest of a run is connection notes, as before.
PER_RUN = 2
# A request nobody has answered in three weeks is a weak way in: an InMail reaches the
# inbox instead of the invitations list.
UNACCEPTED_DAYS = 21
# An employer the person's own lists rate this high (tools/opportunity.py: TIER_1 30,
# TIER_2 20) is one they want.
TARGET_TIER = 20
FILE = "inmail.json"

_LEADER = re.compile(r"\b(?:hiring\s+manager|head\s+of|director|chief|[asde]?vp\b|vice\s+president|"
                     r"founder|co-?founder|partner|manager|lead)\b", re.I)


def plan_has_credits(plan: str | None = None) -> bool:
    """A plan with InMail credits: Premium, or the person's own LINKEDIN_LIMITS. Never free."""
    import schema
    p = schema.plan(fresh=True) if plan is None else str(plan or "free").lower()
    if p == "free":
        return False
    return int(schema.PLANS.get(p, {}).get("inmail_credits_per_month") or 0) > 0 or \
        int(schema.LIMITS.get("inmail_credits_per_month") or 0) > 0


def is_target(company: str) -> bool:
    """An employer the person wants: high on their own employer lists, judged by their bar
    to clear it on pay or prestige, or one with a role open there they scored well."""
    if not str(company or "").strip():
        return False
    try:
        import opportunity
        if opportunity.tier(company)[0] >= TARGET_TIER:
            return True
    except Exception:  # noqa: BLE001  no employer lists: not by tier
        pass
    try:
        import bar
        if bar.applies() and bar.verdict(company)[0] in (bar.PAY, bar.PRESTIGE):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        import why
        return any((r.get("fit") or 0) >= why.ROLE_FIT_FLOOR for r in why.open_roles(company))
    except Exception:  # noqa: BLE001
        return False


def _value(p: dict) -> str:
    """Why they are worth a credit, in a few words, or "" for anyone else."""
    import compose
    title = str(p.get("title") or p.get("headline") or "")
    target = p["target"] if "target" in p else is_target(str(p.get("company") or ""))
    if not target:
        return ""
    if compose.is_recruiter(title):
        return "a recruiter at a target employer"
    if str(p.get("tier") or "").strip() == "1":
        return "posted about hiring at a target employer"
    if str(p.get("tier") or "").strip() == "2" or _LEADER.search(title):
        return "a hiring leader at a target employer"
    return ""


def _weak(p: dict, reading: dict | None) -> str:
    """Why a connection request would reach them badly, or "" when it would do."""
    r = reading or {}
    if r.get("connect") == "missing" or (r.get("reach") == "message" and r.get("degree") in ("2nd", "3rd")):
        return "their page offers no Connect"
    try:
        waited = int(p.get("request_waiting_days") or 0)
    except (TypeError, ValueError):
        waited = 0
    if waited >= UNACCEPTED_DAYS:
        return f"your request has waited {waited} days"
    route = str(p.get("route") or "").lower()
    warm = route in ("connection", "referral", "mutual") or route.startswith(("alumni", "hiring_team")) \
        or p.get("referred_by") or (r.get("shared") or {}).get("employers") or (r.get("shared") or {}).get("schools")
    if warm or r.get("mutuals"):
        return ""
    if r.get("degree") == "3rd":
        return "you share no connections, so a request would wait"
    return "a request would wait"


def worth(p: dict, reading: dict | None = None) -> str:
    """Why this person is worth an InMail rather than a connection note, in the words the
    draft card shows ("a recruiter at a target employer, and a request would wait"), or ""
    when a connection note is right: a peer, someone already connected, a request already
    pending (it may still be accepted), someone found by name only, someone written to."""
    r = reading or {}
    status = str(p.get("status") or "not_contacted").strip() or "not_contacted"
    if status not in ("not_contacted", "awaiting_reply"):
        return ""
    if status == "awaiting_reply" and not p.get("request_waiting_days"):
        return ""
    if p.get("first_degree") or str(p.get("route") or "").lower() == "connection" \
            or r.get("degree") == "1st":
        return ""
    if r.get("reach") == "pending" and not p.get("request_waiting_days"):
        return ""
    if p.get("name_only") or not str(p.get("linkedin_url") or "").strip():
        return ""
    if str(p.get("channel") or "").lower() in ("open_profile", "email", "message"):
        return ""
    value = _value({**p, "title": (r.get("headline") or p.get("title") or "")})
    if not value:
        return ""
    weak = _weak(p, r)
    return f"{value}, and {weak}" if weak else ""


def spare(left: int, queued: int = 0, reserve: int = RESERVE) -> int:
    """Credits a run may spend: what is left, less the InMails already drafted and waiting,
    less the reserve. Never below 0."""
    return max(int(left or 0) - int(queued or 0) - int(reserve), 0)


def _rank(why_: str) -> int:
    return (0 if "no Connect" in why_ else 1 if "waited" in why_ else 2) * 3 + \
        (0 if why_.startswith("posted") else 1 if why_.startswith("a recruiter") else 2)


def choose(people, readings=None, left: int = 0, queued: int = 0, plan: str | None = None,
           per_run: int = PER_RUN, reserve: int = RESERVE) -> list[dict]:
    """[{"contact_id", "why"}] for the people of this run worth an InMail, best first: none
    on a plan without credits, and no more than `per_run` or the spare credits allow.
    `people` are contact rows or search results (title, company, tier, route, linkedin_url,
    and "target" where the caller already knows); `readings` {contact_id: reading}."""
    if not plan_has_credits(plan):
        return []
    room = min(int(per_run), spare(left, queued, reserve))
    if room <= 0:
        return []
    readings = readings or {}
    found = []
    for i, p in enumerate(people or ()):
        cid = str(p.get("contact_id") or "").strip()
        w = worth(p, readings.get(cid))
        if w:
            found.append((_rank(w), -int(p.get("score") or 0), i, cid, w))
    found.sort()
    return [{"contact_id": cid, "why": w} for *_k, cid, w in found[:room]]


# ---------------------------------------------------------------- what the card says


def card_line(why_: str) -> str:
    """"InMail (suggested): a recruiter at a target employer, and a request would wait"."""
    return f"InMail (suggested): {why_}" if why_ else "InMail"


def credit_line(left: int) -> str:
    """"uses 1 of your 4 InMails", from the credits left now."""
    n = max(int(left or 0), 0)
    return f"uses 1 of your {n} InMail{'s' if n != 1 else ''}" if n else "you have no InMails left"


# ---------------------------------------------------------------- the record beside the draft


def _path(cid: str) -> str:
    import reading
    return os.path.join(os.path.dirname(reading.draft_path(cid)), FILE)


def load(cid: str) -> dict:
    try:
        with open(_path(cid), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(cid: str, rec: dict) -> None:
    p = _path(cid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
        fh.write("\n")


def _read(p: str) -> str:
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _write(p: str, text: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def mark_picked(cid: str, why_: str, today: str) -> dict:
    """Keep the run's decision before the InMail is written: `use` reads it."""
    rec = dict(load(cid), why=why_, on=today, picked=True)
    _save(cid, rec)
    return rec


def use(cid: str, inmail_text: str, card_only: bool = False) -> tuple[int, str]:
    """Save the InMail as their draft, checked as one (reading.save_drafts), with the
    connection note it replaces kept to switch back to. (exit code, what was said)."""
    import io
    from contextlib import redirect_stdout

    import reading
    import state
    contacts = state.load_contacts()
    row = next((c for c in contacts if str(c.get("contact_id") or "") == cid), None)
    if row is None:
        return 1, f"inmail: {cid} is not in the contact book"
    if not state.split_subject(inmail_text)[0]:
        return 1, "inmail: an InMail starts with its subject: a first line \"Subject: ...\""
    before_channel = str(row.get("channel") or "")
    before = _read(reading.draft_path(cid))
    # Their message window says which it is (reading.message_check): free to an Open Profile,
    # which spends nothing, or a credit. Unchecked, save_drafts refuses it and says how to
    # check: 14 InMails were drafted on a guess and 2 went (2026-10-24).
    free = reading.message_window(reading.load(cid)) == "free"
    row["channel"] = "open_profile" if free else "inmail"
    state.save_contacts(contacts)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = reading.save_drafts({cid: (inmail_text, bool(card_only))})
    said = buf.getvalue().strip()
    if code:
        contacts = state.load_contacts()
        for c in contacts:
            if str(c.get("contact_id") or "") == cid:
                c["channel"] = before_channel
        state.save_contacts(contacts)
        if before:
            _write(reading.draft_path(cid), before)
        return code, said
    rec = load(cid)
    # The message-window check sets the row's channel itself: the note goes back as a note.
    note_channel = before_channel if before_channel.lower() not in ("inmail", "open_profile") \
        else ""
    rec.update({"active": "inmail", "other": before, "other_channel": note_channel or "connection"})
    rec.pop("picked", None)
    rec.setdefault("why", "")
    _save(cid, rec)
    return 0, said or f"inmail: saved as an InMail for {cid}"


def can_switch(cid: str, channel: str) -> str:
    """The channel this person's draft can switch to ("connection" or "inmail"), or ""."""
    rec = load(cid)
    if not rec.get("other", "").strip():
        return ""
    active = "inmail" if channel == "inmail" else "connection"
    if rec.get("active", "inmail") != active:
        return ""
    return "connection" if active == "inmail" else "inmail"


def switch(cid: str, to: str, left: int | None = None) -> str:
    """Swap their draft between the InMail and the connection note, and their channel with
    it: the credit is freed (to "connection") or spent (to "inmail", only while one is
    left). Returns what changed, in plain words. ValueError when it cannot."""
    import reading
    import state
    if to not in ("connection", "inmail"):
        raise ValueError("it switches to a connection note or an InMail")
    contacts = state.load_contacts()
    row = next((c for c in contacts if str(c.get("contact_id") or "") == cid), None)
    if row is None:
        raise ValueError("They are no longer in your contact book.")
    now = "inmail" if str(row.get("channel") or "").lower() == "inmail" else "connection"
    if now == to:
        raise ValueError("It is already " + ("an InMail." if to == "inmail" else "a connection note."))
    rec = load(cid)
    other = str(rec.get("other") or "")
    if not other.strip() or rec.get("active", "inmail") != now:
        raise ValueError("There is no " + ("InMail" if to == "inmail" else "connection note")
                         + " written for them to switch to.")
    if to == "inmail" and left is not None and left < 1:
        raise ValueError("You have no InMails left this month.")
    if str(row.get("status") or "not_contacted") not in ("not_contacted", "dropped"):
        raise ValueError("A message has gone to them since.")
    current = _read(reading.draft_path(cid))
    _write(reading.draft_path(cid), other)
    row["channel"] = "inmail" if to == "inmail" else str(rec.get("other_channel") or "connection")
    if to == "inmail":
        rec["other_channel"] = now if now != "inmail" else "connection"
    else:
        rec["other_channel"] = "inmail"
    rec.update({"active": to, "other": current})
    state.save_contacts(contacts)
    _save(cid, rec)
    return ("A connection note now, and the InMail credit is free." if to == "connection"
            else "An InMail now: it uses one of your credits.")


# ---------------------------------------------------------------- the weekly ask

# The balance LinkedIn shows is asked for once a week on a plan with credits: the count from
# the log is only a floor (credits carry over, up to 15 on Premium Career, and an Open
# Profile message spends none), and the pick above spends what is left (the maintainer,
# 2026-11-05).
ASK_EVERY_DAYS = 7
ASK_ID = "q-inmail-credits"
ASK_TITLE = "How many InMails does LinkedIn show you have left?"
ASK_STEPS = "linkedin-inmail-credits"


def _balance_file() -> dict:
    import state
    try:
        with open(state._inmail_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def last_asked(today: datetime.date) -> datetime.date | None:
    """The last day the person answered: a balance kept, or "not this week"."""
    got = _balance_file()
    days = []
    for k in ("date", "skipped"):
        try:
            d = datetime.date.fromisoformat(str(got.get(k) or "")[:10])
        except ValueError:
            continue
        if d <= today:
            days.append(d)
    return max(days) if days else None


def ask_due(today: datetime.date, plan: str | None = None) -> bool:
    """Is the weekly question due: a plan with credits, and no answer in the last week?"""
    if not plan_has_credits(plan):
        return False
    last = last_asked(today)
    return last is None or (today - last).days >= ASK_EVERY_DAYS


def skip_week(today: datetime.date) -> None:
    """"Not this week": asked again in a week, the balance kept as it was."""
    import state
    got = _balance_file()
    got["skipped"] = today.isoformat()
    p = state._inmail_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1)
        fh.write("\n")


# ---------------------------------------------------------------- the run's command


def _waiting_days(cid: str, threads, today: datetime.date) -> int:
    import state
    rows = [r for r in threads if str(r.get("contact_id") or "") == cid]
    reqs = [state.as_date(r.get("date")) for r in rows if state.is_request(r)]
    later = [r for r in rows if state._direction(r) == "in" or state.is_withdrawal(r)]
    if not reqs or later or not reqs[-1]:
        return 0
    return (today - reqs[-1]).days


def pick(ids, today: datetime.date) -> list[dict]:
    """The run's decision over these contacts, kept beside each picked one's draft."""
    import reading
    import state
    contacts = state.load_contacts()
    threads = state.load_threads()
    book = {str(c.get("contact_id") or ""): c for c in contacts}
    b = state.platform_budget(contacts, threads, today.isoformat())
    people, readings = [], {}
    for cid in ids:
        c = book.get(cid)
        if c is None:
            continue
        people.append(dict(c, request_waiting_days=_waiting_days(cid, threads, today)))
        readings[cid] = reading.load(cid) or {}
    got = choose(people, readings, left=b["inmails_left"], queued=b["queued_unsent"]["inmail"])
    for g in got:
        mark_picked(g["contact_id"], g["why"], today.isoformat())
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inmail_pick.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick", help="which of these people get an InMail instead of a note")
    p.add_argument("ids", nargs="+")
    p.add_argument("--today", default=None)
    u = sub.add_parser("use", help="save an InMail as their draft, keeping the note to switch back")
    u.add_argument("contact_id")
    u.add_argument("file", help="the InMail (a first line Subject: ...), or - for stdin")
    u.add_argument("--card-only", action="store_true")
    s = sub.add_parser("switch", help="switch their draft to a connection note or an InMail")
    s.add_argument("contact_id")
    s.add_argument("to", choices=("connection", "inmail"))
    a = ap.parse_args(argv)
    if a.cmd == "pick":
        today = datetime.date.fromisoformat(a.today) if a.today else person.today()
        if not plan_has_credits():
            print("inmail: your LinkedIn plan has no InMail credits: everyone gets a connection note")
            return 0
        got = pick(a.ids, today)
        if not got:
            print("inmail: nobody here is worth an InMail now: everyone gets a connection note")
            return 0
        for g in got:
            print(f"  {g['contact_id']}: {card_line(g['why'])}. Their message window is checked "
                  "first (reading.py extractor --message-check on their page, or their word: "
                  f"reading.py message-check {g['contact_id']} free|credits --by-hand); then "
                  "write the InMail and save it: python3 tools/network/inmail_pick.py use "
                  f"{g['contact_id']} -")
        return 0
    if a.cmd == "use":
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        code, said = use(a.contact_id, text, a.card_only)
        print(said)
        return code
    try:
        print(switch(a.contact_id, a.to))
    except ValueError as e:
        print(f"inmail: not switched: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
