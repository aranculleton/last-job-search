#!/usr/bin/env python3
"""What has worked for this person, read from what already happened.

The search already records every result that matters: the tracker knows which
applications reached an interview, and the message log knows which messages drew
a reply. Nothing read it back. So a person had to say "write it like the one Sam
answered" or "use the CV that got me the interview" every time, and the search
learned nothing from its own record.

This reads it back. It is counting, not a model: no call to anything, no state
of its own, nothing to fall out of step. Every number is derived from
`job_search_tracker.csv`, `network_threads.csv`, `network_contacts.csv` and the
draft each application was rendered from (`documents/applications/<slug>/draft.json`),
so recording a result is all it takes for the next draft to use it.

    python3 tools/what_works.py brief messages [--route R] [--channel C] [--tier T]
    python3 tools/what_works.py brief documents
    python3 tools/what_works.py brief search
    python3 tools/what_works.py event --contact <contact_id>
    python3 tools/what_works.py event --company "<employer>"

- `brief messages` is read before a networking message is drafted: the reply rate,
  any difference clear enough not to be chance, and the messages that drew a
  reply, closest to the one being drafted first. The drafting step matches their
  shape (length, opening move, the question asked), never their words.
- `brief documents` is read before /apply drafts: the applications that reached an
  interview, with the summary and the bullets their resume used. Those bullets
  also get a small lift in `tools/allocate.py` (`WIN_BONUS`), so a resume that
  worked shapes the next one without anybody asking.
- `brief search` is the interview rate by fit band, route and channel: whether the
  scores are predicting anything.
- `event` is the one-line audit run when a result arrives (/outcome, a reply logged
  by /reply): what this result had, and what the rates are now.

Small numbers lie, so a difference is reported only when both groups have at
least `MIN_GROUP` decided cases and the gap is unlikely to be chance (a
two-proportion test at 95%). Until then it says so, and shows the examples alone.
Every brief is a few lines: it is read before drafting, so it is kept cheap.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import functools
import glob
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "network"))

import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

# A message is decided once it has a reply, or once this many days have passed
# without one. Before that it is waiting, and counting it as a failure would make
# every new batch look like a bad one.
REPLY_WAIT_DAYS = 14
# An application still `applied` after this many days is counted as unanswered,
# the same 45 days `tools/followups.py` stops chasing at.
SILENT_DAYS = 45
# The smallest group a rate is compared on.
MIN_GROUP = 8
# |z| for a difference unlikely to be chance (two-sided, 95%).
CLEAR_Z = 1.96
EXEMPLARS = 3
EXEMPLAR_CHARS = 500

WIN = frozenset({"interview", "offer", "hired", "offer_declined", "offer declined"})
LOSS = frozenset({"rejected", "no_response", "no response"})

_ROUTE_GROUP = (("alumni", "alumni"), ("referral", "warm intro"), ("mutual", "warm intro"),
                ("intro", "warm intro"), ("inbound", "inbound"), ("job_posting", "named on a posting"),
                ("hiring_team", "named on a posting"), ("community", "community"), ("cold", "cold"))


def _today(value=None) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _date(value):
    try:
        return dt.date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _csv(path: str) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def route_group(route: str) -> str:
    r = str(route or "").strip().lower()
    for stem, group in _ROUTE_GROUP:
        if stem in r:
            return group
    return r or "not recorded"


def _length_group(text: str) -> str:
    n = len(text)
    if not n:
        return ""
    return "under 200 characters" if n < 200 else "200-300 characters" if n <= 300 \
        else "over 300 characters"


def _rate(hit: int, n: int) -> str:
    return "%d of %d (%d%%)" % (hit, n, round(100 * hit / n)) if n else "none yet"


def clear(a_hit: int, a_n: int, b_hit: int, b_n: int) -> bool:
    """Is the gap between two rates unlikely to be chance? Both groups at MIN_GROUP."""
    if a_n < MIN_GROUP or b_n < MIN_GROUP:
        return False
    p = (a_hit + b_hit) / (a_n + b_n)
    if p in (0.0, 1.0):
        return False
    z = (a_hit / a_n - b_hit / b_n) / math.sqrt(p * (1 - p) * (1 / a_n + 1 / b_n))
    return abs(z) >= CLEAR_Z


def differences(cases: list[dict], features: tuple[str, ...], what: str) -> list[str]:
    """One line per feature whose best and worst groups differ clearly."""
    out = []
    for f in features:
        groups: dict[str, list[int]] = {}
        for c in cases:
            v = c.get(f)
            if v:
                g = groups.setdefault(v, [0, 0])
                g[0] += 1 if c["won"] else 0
                g[1] += 1
        big = [(v, h, n) for v, (h, n) in groups.items() if n >= MIN_GROUP]
        if len(big) < 2:
            continue
        best = max(big, key=lambda x: (x[1] / x[2], x[2]))
        worst = min(big, key=lambda x: (x[1] / x[2], -x[2]))
        if best is not worst and clear(best[1], best[2], worst[1], worst[2]):
            out.append("By %s: %s %s %s; %s %s %s." % (
                f.replace("_", " "), best[0], what, _rate(best[1], best[2]),
                worst[0], what, _rate(worst[1], worst[2])))
    return out


# ------------------------------------------------------------------ messages

def message_cases(contacts: list[dict], threads: list[dict], today=None) -> list[dict]:
    """Every message sent before a reply came, each marked won, lost or waiting.

    Per contact, oldest first: until the first inbound row that says something,
    every outbound row is an attempt, the first an opener and the rest nudges.
    The reply is credited to the last attempt before it. After the first reply
    the conversation is live and its messages are not counted: they answer
    somebody, they do not open anything.
    """
    import state
    today = _today(today)
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    rows: dict[str, list[dict]] = {}
    for r in threads:
        rows.setdefault(str(r.get("contact_id") or "").strip(), []).append(r)
    cases = []
    for cid, mine in rows.items():
        if not cid:
            continue
        contact = by_id.get(cid, {})
        attempts: list[dict] = []
        replied_on = None
        for r in state._ordered(mine):
            if state.said_something(r):
                replied_on = state.as_date(r.get("date"))
                break
            # A bare connection request says nothing, so it neither wins nor
            # loses: on a free account the message follows the acceptance, and
            # that message is the opener.
            if state._direction(r) == "out" and not state.is_call(r) \
                    and state._scenario(r) not in state.MID_CONVERSATION and not (
                    state.channel_of(r) == "connection"
                    and not str(r.get("full_text") or "").strip()
                    and not str(r.get("summary") or "").strip()):
                attempts.append(r)
        for i, r in enumerate(attempts):
            sent = state.as_date(r.get("date"))
            last = i == len(attempts) - 1
            won = bool(last and replied_on)
            waiting = (not won and last and not replied_on
                       and (sent is None or (today - sent).days < REPLY_WAIT_DAYS))
            if waiting:
                continue
            text = " ".join(str(r.get("full_text") or "").split())
            cases.append({
                "contact_id": cid, "name": contact.get("name") or cid,
                "company": contact.get("company", ""), "date": sent.isoformat() if sent else "",
                "attempt": "opener" if i == 0 else "follow-up",
                "route": route_group(contact.get("route")),
                "found_via": str(contact.get("found_via") or "").strip() or "not recorded",
                "channel": state.channel_of(r) or "not recorded",
                "tier": ("tier %s" % str(contact.get("tier")).strip())
                if str(contact.get("tier") or "").strip() else "",
                "length": _length_group(text),
                "question": ("asks a question" if "?" in text else "no question") if text else "",
                "text": text, "summary": " ".join(str(r.get("summary") or "").split()),
                "won": won,
                "days_to_reply": (replied_on - sent).days if won and sent and replied_on else None,
            })
    return cases


def _closeness(c: dict, route=None, channel=None, tier=None) -> tuple:
    score = ((2 if channel and c["channel"] == channel else 0)
             + (2 if route and c["route"] == route_group(route) else 0)
             + (1 if tier and c["tier"] == "tier %s" % tier else 0))
    return (score, bool(c["text"]), c["date"])


_CHANNEL_NAMES = {"connection": "connection note", "inmail": "InMail", "email": "email",
                  "message": "message", "intro": "introduction"}


def _channel_name(channel: str) -> str:
    return _CHANNEL_NAMES.get(channel, channel)


def _after(days) -> str:
    if days is None:
        return ""
    return " the same day" if days == 0 else " after %d day%s" % (days, "" if days == 1 else "s")


def _clip(text: str) -> str:
    return text if len(text) <= EXEMPLAR_CHARS else text[:EXEMPLAR_CHARS - 3].rstrip() + "..."


def brief_messages(contacts, threads, today=None, route=None, channel=None, tier=None) -> str:
    cases = message_cases(contacts, threads, today)
    openers = [c for c in cases if c["attempt"] == "opener"]
    follow = [c for c in cases if c["attempt"] == "follow-up"]
    if not openers:
        return ""
    won = [c for c in cases if c["won"]]
    lines = ["What has worked, from your own messages (counted from network_threads.csv):",
             "- First messages answered: %s%s." % (
                 _rate(sum(c["won"] for c in openers), len(openers)),
                 "; follow-ups answered: " + _rate(sum(c["won"] for c in follow), len(follow))
                 if follow else "")]
    found = differences(openers, ("route", "found_via", "channel", "tier", "length", "question"),
                        "answered")
    lines += ["- " + d for d in found] or [
        "- No difference is clear yet (each group needs %d decided messages and a gap "
        "unlikely to be chance)." % MIN_GROUP]
    shown = [c for c in won if c["text"]]
    if shown:
        lines.append("Messages that drew a reply, closest to this one first. Match their shape "
                     "(length, opening move, the question), never their words or their facts:")
        for c in sorted(shown, key=lambda c: _closeness(c, route, channel, tier),
                        reverse=True)[:EXEMPLARS]:
            lines.append("  %s, %s, %s route, %d characters, answered%s: \"%s\"" % (
                c["date"], _channel_name(c["channel"]), c["route"], len(c["text"]),
                _after(c["days_to_reply"]), _clip(c["text"])))
    elif won:
        lines.append("- The messages that drew replies were logged without their text, so there "
                     "is no example to show. Logging the full text of each message sent fixes it.")
    return "\n".join(lines)


def event_contact(contacts, threads, contact_id: str, today=None) -> str:
    every = message_cases(contacts, threads, today)
    hit = next((c for c in every if c["contact_id"] == contact_id and c["won"]), None)
    if not hit:
        return ""
    openers = [c for c in every if c["attempt"] == "opener"]
    same = [c for c in openers if c["route"] == hit["route"]]
    shape = ", ".join(x for x in (_channel_name(hit["channel"]), hit["route"] + " route",
                                  hit["length"], hit["question"]) if x)
    keep = ("It is now an example the next message like it is drafted against."
            if hit["text"] else "Its text was not logged, so it cannot be an example; log the "
            "full text of what was sent.")
    return "%s answered your %s of %s%s (%s). %s First messages on the %s route: %s answered." % (
        hit["name"], "first message" if hit["attempt"] == "opener" else "follow-up",
        hit["date"] or "an unrecorded date", _after(hit["days_to_reply"]), shape, keep,
        hit["route"], _rate(sum(c["won"] for c in same), len(same)))


# ------------------------------------------------------------------ applications

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def drafts(root: str | None = None) -> list[dict]:
    """Every kept draft object, from documents/applications/*/draft.json."""
    root = root or person.state()
    out = []
    for path in sorted(glob.glob(os.path.join(root, "documents", "applications", "*", "draft.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict):
                out.append(dict(d, _path=os.path.relpath(path, root)))
    return out


def draft_for(row: dict, kept: list[dict]) -> dict | None:
    """The draft a tracker row was sent with: its file's abbreviation, else the same role.

    Never another role's draft. With one draft at an employer it used to be
    taken whatever its role, so a later, never-sent draft for a different role
    was credited with the interview the earlier application won, and the
    allocator lifted bullets that employer never saw.
    """
    k = company_key(row.get("company"))
    at = [d for d in kept if company_key(d.get("company")) == k]
    m = re.search(r"_([A-Za-z0-9_]+)\.(?:tex|pdf)$", str(row.get("cv_file") or ""))
    if m:
        by_abbr = [d for d in at if str(d.get("abbr") or "").lower() == m.group(1).lower()]
        if by_abbr:
            return by_abbr[-1]
    same = [d for d in at if _norm(d.get("role")) == _norm(row.get("role"))]
    return same[-1] if same else None


def _fit_band(value) -> str:
    try:
        n = float(str(value).strip())
    except ValueError:
        return ""
    return "fit 75+" if n >= 75 else "fit 60-74" if n >= 60 else "fit under 60"


# An interview is a fact about the past: a row that reached one and was later
# rejected reached it all the same. /outcome updates the status in place, so a
# rejection after the interview read as "did not reach an interview" and every
# interview that ended in a no vanished from what this learns from. The notes
# (/outcome appends a dated note) or the application's outcome.md say it happened.
# An interview as an event, never the bare word: "do not claim it in interview"
# and "two days onsite" are advice and a work pattern, and both read as one.
_REACHED = re.compile(
    r"(?<!no )(?<!not )\b(?:interviewed|invited to (?:an? )?interview|interview "
    r"(?:invite|invitation|scheduled|booked|held|done|completed|stage|round|with|on \d)"
    r"|(?:phone|recruiter|hiring manager|technical|first|second|final) (?:screen|interview)"
    r"|screening call|(?:first|second|third|final) round)\b", re.I)


def reached_interview(row: dict, root: str | None = None) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in WIN:
        return True
    if _REACHED.search(str(row.get("notes") or "")):
        return True
    try:
        import outreach
        folder = outreach.app_folder(row.get("company"), row.get("role") or "")
        with open(os.path.join(folder, "outcome.md"), encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return False
    return "- [x]" in text.lower() or "interview_only" in text


def application_cases(tracker: list[dict], today=None) -> list[dict]:
    """Every sent application with a result: reached an interview or did not."""
    today = _today(today)
    cases = []
    for r in tracker:
        status = str(r.get("status") or "").strip().lower()
        applied = _date(r.get("date"))
        if status in WIN or (status in LOSS and reached_interview(r)):
            won = True
        elif status in LOSS or (status == "applied" and applied
                                and (today - applied).days >= SILENT_DAYS):
            won = False
        else:
            continue
        cases.append({"row": r, "won": won, "status": status,
                      "company": r.get("company", ""), "role": r.get("role", ""),
                      "date": applied.isoformat() if applied else "",
                      "fit_band": _fit_band(r.get("fit_rating")),
                      "channel": " ".join(str(r.get("channel") or "").lower().split()),
                      "role_type": " ".join(str(r.get("role_type") or "").lower().split()),
                      "sector": " ".join(str(r.get("sector") or "").lower().split())})
    return cases


def _waiting(tracker, today) -> int:
    today = _today(today)
    return sum(1 for r in tracker if str(r.get("status") or "").strip().lower() == "applied"
               and _date(r.get("date")) and (today - _date(r.get("date"))).days < SILENT_DAYS)


def brief_documents(tracker, kept, today=None) -> str:
    cases = application_cases(tracker, today)
    if not cases:
        return ""
    wins = [c for c in cases if c["won"]]
    lines = ["What has worked, from your own applications (counted from job_search_tracker.csv):",
             "- Reached an interview: %s; %d sent in the last %d days not counted yet." % (
                 _rate(len(wins), len(cases)), _waiting(tracker, today), SILENT_DAYS)]
    if not wins:
        lines.append("- No interview on record yet, so there is nothing to copy: draft on the "
                     "defaults.")
        return "\n".join(lines)
    lines.append("Applications that reached an interview. Read the resume and letter before "
                 "drafting a similar role, and match what they did, never their facts:")
    for c in sorted(wins, key=lambda c: c["date"], reverse=True)[:EXEMPLARS]:
        r, d = c["row"], draft_for(c["row"], kept)
        files = ", ".join(f for f in (r.get("cv_file"), r.get("cover_letter_file")) if f)
        lines.append("  %s, %s at %s (%s%s%s)%s" % (
            c["date"], c["role"], c["company"], c["status"],
            ", " + c["fit_band"] if c["fit_band"] else "",
            ", " + c["channel"] if c["channel"] else "",
            ": " + files if files else ": no resume or letter on record"))
        if d:
            if d.get("summary"):
                lines.append("    summary: \"%s\"" % _clip(" ".join(str(d["summary"]).split())))
            used = [b for j in d.get("jobs") or [] for b in j.get("bullets") or []]
            if used:
                lines.append("    bullets: %s" % ", ".join(used))
    return "\n".join(lines)


def brief_search(tracker, today=None) -> str:
    cases = application_cases(tracker, today)
    if not cases:
        return ""
    found = differences(cases, ("fit_band", "channel", "role_type", "sector"), "reached interview")
    head = "Interviews from your applications: %s." % _rate(sum(c["won"] for c in cases), len(cases))
    if not found:
        return head + (" Too few results yet to say which kinds of role or route do better "
                       "(each group needs %d decided applications)." % MIN_GROUP)
    return "\n".join([head] + ["- " + d for d in found])


def event_company(tracker, kept, company: str, today=None, role: str = "") -> str:
    """The audit line for the result /outcome just recorded at this employer.

    The row is the one named by `role`, else the employer's latest row that
    reached an interview, else its latest row. Taking the last row alone said
    nothing at an employer with two applications when the earlier one won.
    """
    k = company_key(company)
    rows = [r for r in tracker if company_key(r.get("company")) == k]
    if not rows:
        return ""
    cases = application_cases(tracker, today)
    named = [r for r in rows if role and _norm(r.get("role")) == _norm(role)]
    won = [r for r in rows if reached_interview(r)]
    row = (named or won or rows)[-1]
    status = str(row.get("status") or "").strip().lower()
    rate = "Interviews so far: %s." % _rate(sum(c["won"] for c in cases), len(cases))
    if not reached_interview(row):
        return rate
    if status not in WIN:
        status = "interview"
    d = draft_for(row, kept)
    how = ", ".join(x for x in (_fit_band(row.get("fit_rating")),
                                " ".join(str(row.get("channel") or "").split())) if x)
    files = [f for f in (row.get("cv_file"), row.get("cover_letter_file")) if f]
    if d:
        keeps = ("Its resume and letter are now examples /apply reads before drafting, and the "
                 "%d bullets it used get a small lift in the allocator."
                 % len({b for j in d.get("jobs") or [] for b in j.get("bullets") or []}))
    elif files:
        keeps = ("Its resume and letter are now examples /apply reads before drafting (%s)."
                 % ", ".join(files))
    else:
        keeps = ("Neither its resume nor its letter is on record, so there is nothing to learn "
                 "from it beyond the count.")
    return "%s at %s (%s)%s. %s %s" % (status.replace("_", " ").capitalize(), row.get("company"),
                                       row.get("role") or "role not recorded",
                                       ", from a " + how + " application" if how else "", keeps, rate)


# ------------------------------------------------------------------ the allocator's lift

@functools.lru_cache(maxsize=8)
def _bullet_wins(root: str) -> dict:
    tracker = _csv(os.path.join(root, "job_search_tracker.csv"))
    kept = drafts(root)
    wins: dict[str, int] = {}
    for c in application_cases(tracker):
        if not c["won"]:
            continue
        d = draft_for(c["row"], kept)
        for b in {b for j in (d or {}).get("jobs") or [] for b in j.get("bullets") or []}:
            wins[b] = wins.get(b, 0) + 1
    return wins


def bullet_wins() -> dict:
    """{bullet id: applications that reached an interview with it on the resume}."""
    return dict(_bullet_wins(person.state()))


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief", help="what has worked, read before drafting")
    b.add_argument("area", choices=("messages", "documents", "search"))
    b.add_argument("--route")
    b.add_argument("--channel")
    b.add_argument("--tier")
    e = sub.add_parser("event", help="the one-line audit when a result arrives")
    g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("--contact", help="contact_id whose reply was just logged")
    g.add_argument("--company", help="employer whose application result was just recorded")
    e.add_argument("--role", default="", help="with --company: the role whose result it was")
    for p in (b, e):
        p.add_argument("--today")
    a = ap.parse_args(argv)
    import state
    tracker = _csv(person.state("job_search_tracker.csv"))
    if a.cmd == "brief" and a.area == "messages":
        out = brief_messages(state.load_contacts(), state.load_threads(), a.today,
                             a.route, a.channel, a.tier)
    elif a.cmd == "brief" and a.area == "documents":
        out = brief_documents(tracker, drafts(), a.today)
    elif a.cmd == "brief":
        out = brief_search(tracker, a.today)
    elif a.contact:
        out = event_contact(state.load_contacts(), state.load_threads(), a.contact, a.today)
    else:
        out = event_company(tracker, drafts(), a.company, a.today, a.role)
    print(out or "(nothing on record yet: the defaults apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
