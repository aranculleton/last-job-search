#!/usr/bin/env python3
"""Which applications are due a follow-up, who it goes to, and what to send.

A sent application gets a first nudge seven days after it went, and a second
and last one seven days after the first was actually sent. Nothing is sent from
here: the output is a list to act on, and the message is a draft a person
edits.

## Why this is imported rather than only run

It worked, and nothing knew it existed. It was named in one line of
`RUNBOOK.md` and nowhere else, so whether a follow-up went out depended on
somebody remembering to type a command, which is exactly the class of state
this repo exists to stop relying on. `tools/open_actions.py` is the one view of
everything owed, so a follow-up that is due belongs in it beside the
conversations that are owed a reply, employer by employer.

A nudge is also the cheapest thing in the whole system. A resume costs a
drafting pass and two reviewers; a follow-up costs one sentence, and a reply to
it is worth the same as a reply to anything else.

## What keeps a nudge back

An earlier version listed nudges that were mostly wrong in one of six ways.
Each is now a rule, next to the code it governs:

  numbering    the second nudge follows a first that was actually sent
  holds        an interview, an offer or a referral running at the employer
  not chased   a DO NOT CHASE entry in the row's notes
  superseded   a later row for the same role is the application now
  recipient    who it goes to, or plainly nobody
  stop         two nudges met with silence, or SILENCE_DAYS since it went

    python3 tools/followups.py [--today YYYY-MM-DD]
    python3 tools/followups.py --close-quiet [--dry-run]   # the brief runs this
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dates                                          # noqa: E402
import outreach                                       # noqa: E402
import docpaths                                       # noqa: E402
import person                                         # noqa: E402
import throttle                                       # noqa: E402
from company_key import key as company_key            # noqa: E402
from network import state                             # noqa: E402
from network import tone                              # noqa: E402

ROOT = os.path.dirname(_HERE)
TRACKER = person.state("job_search_tracker.csv")
DOCS = person.state("documents", "applications")

FIRST_NUDGE_DAYS = 7      # after the application went
NUDGE_GAP_DAYS = 7        # after the first nudge actually went
MAX_NUDGES = 2

# Where the chase ends, and the same number at which the throttle stops counting
# an application at all. Imported rather than restated: two copies of one
# threshold are two thresholds by the next time either is edited.
SILENCE_DAYS = throttle.SILENCE_DAYS

NUDGE_1 = ("Hi {name}, I applied for the {role} role on {date} and wanted to make sure it "
           "reached the right person. Happy to share anything that would help the review. "
           "Is there a good time for a short call?")
NUDGE_2 = ("Hi {name}, following up once more on the {role} application from {date}. "
           "If the role has moved on, no problem at all; if it is still open, I would "
           "value ten minutes to talk through the fit.")

# What a person writes in the row's notes once a nudge has gone. Numbering reads
# this and nothing else.
#
# The old rule numbered by age: fourteen days after applying it offered "nudge 2
# of 2", "following up once more", whether or not a first had ever gone, and
# most rows listed that way recorded no follow-up. A recruiter reading "once
# more" about a first message is reading a draft nobody checked.
#
# Two spellings, because there are two writers: this file said to append
# `follow-up sent YYYY-MM-DD`, and `/outcome` Step 2b logs `followed up
# YYYY-MM-DD`. Reading only the first made a nudge logged through /outcome
# invisible here, and it would have been offered again. The date is the one
# written beside the marker, or the one the note opens on ("<date>:
# follow-up sent to the recruiter"), which is how every other tracker note is
# written. "followed up" counts only with its date, because recruiters follow up
# too and the notes say so in prose.
_SENT = re.compile(
    r"(?<!no )(?<!not )\bfollow[- ]?up sent\b(?:\W{0,4}(?:on\s+)?(\d{4}-\d{2}-\d{2}))?"
    r"|\bfollowed up\W{0,4}(?:on\s+)?(\d{4}-\d{2}-\d{2})", re.I)
_LEADING_DATE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})")
LOG_AS = "followed up %s"      # the /outcome Step 2b form, so there is one to write

# A row somebody has said to leave alone. A profile can say of an application
# that it is not chased, and nothing reads that sentence, so the row is offered
# a nudge like any other. A row can also carry "DO NOT CHASE" in its own notes
# and be offered one too.
#
# Data, not a name in this file. The marker is a dated entry in the row's notes
# like every other; `until <date>` in the same entry ends it, and a later entry
# saying "chase again" ends it too, so lifting it never means rewriting history.
_NOT_CHASED = re.compile(r"\bdo(?:[\s-]+not|n['’]?t)[\s-]+chase\b", re.I)
_CHASE_AGAIN = re.compile(r"\b(?:chase again|resume chasing)\b", re.I)

# The /outcome vocabulary's live-process statuses, plus the `interviewing` that
# open_actions.HEAT keyed on while the tracker wrote `interview`.
LIVE_PROCESS = frozenset({"interview", "interviewing", "offer"})

# A tracker `role` that is a note rather than a job title ("Questionnaire
# completed", "Several applications (titles unknown)"), and the template used
# to paste it straight into the sentence: "I applied for the Questionnaire
# completed role on <date>". That reaches a recruiter as a draft nobody read,
# which is worse than sending nothing, so the draft is withheld and the row is
# flagged for a title instead.
_PLACEHOLDER_ROLE = re.compile(
    r"not recorded|several applications|questionnaire|unknown|^n/?a$|"
    r"^\s*$|multiple roles|two roles", re.I)

# Who a nudge goes to. Every draft opened "Hi [name]" and nothing said who that
# was, so most drafts were addressed to nobody. A template to nobody is a
# research task dressed as a message, so it now says which it is.
_ABBR = re.compile(re.escape(docpaths.prefix()) + "_" + re.escape(docpaths.noun_word())
                   + r"_([A-Za-z0-9]+)")
_SEND_ON = re.compile(r"^Send on (?P<channel>[^,\n]+?) to (?P<who>[^,.\n]+)", re.M)
NO_RECIPIENT = ("no recipient on file: find the recruiter or hiring manager first, "
                "then put the name in the tracker row's contact_person column")


def _rows(path: str = TRACKER) -> list[dict]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _status(row: dict) -> str:
    return str(row.get("status") or "").strip().lower()


def _iso(raw) -> datetime.date | None:
    return dates.as_date(raw, iso_only=True)


def _clip(text, n: int = 140) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def nudges_sent(notes) -> list[datetime.date | None]:
    """Every follow-up the notes record, in the order written; None where undated."""
    out: list[datetime.date | None] = []
    for entry in str(notes or "").split("|"):
        opens_on = _LEADING_DATE.match(entry)
        for m in _SENT.finditer(entry):
            out.append(_iso(m.group(1) or m.group(2) or (opens_on.group(1) if opens_on else "")))
    return out


def not_chased(notes, today: datetime.date) -> str:
    """The note that says to leave this row alone, or "" when none stands today."""
    standing = ""
    for entry in str(notes or "").split("|"):
        if _CHASE_AGAIN.search(entry):
            standing = ""
        m = _NOT_CHASED.search(entry)
        if m:
            lifts = state.hold_lifts(entry[m.end():])
            standing = "" if lifts is not None and lifts <= today else entry.strip()
    return standing


def superseded(rows: list[dict]) -> dict[int, dict]:
    """id(row) -> the later row that is now the record of the same application.

    The tracker appends a row when a role is redrawn, re-sent or closed out,
    rather than editing the old one, so one role can sit in it twice and only
    the later row is the application. Nothing here read past the row in hand: an
    `applied` row followed by a `withdrawn`, `rejected` or `interview` row for
    the same role was nudged as though still open. The shape, the right way
    round: a draft was withdrawn and the role applied to again later, so the
    withdrawn row is the earlier one and the sent application stays chased.

    Later means by date, then by position in the file. A draft supersedes
    nothing, because nothing was sent. Roles are compared by
    `throttle._same_title`, the same test the throttle uses to recognise a role
    already applied to.
    """
    order = sorted(range(len(rows)),
                   key=lambda i: (_iso(rows[i].get("date")) or datetime.date.min, i))
    keys = {i: company_key(rows[i].get("company")) for i in order}
    out: dict[int, dict] = {}
    for n, i in enumerate(order):
        if not keys[i]:
            continue
        for j in order[n + 1:]:
            if (keys[j] == keys[i] and _status(rows[j]) not in throttle.UNSENT
                    and throttle._same_title(rows[i].get("role"), rows[j].get("role"))):
                out[id(rows[i])] = rows[j]
                break
    return out


def live_processes(rows: list[dict], closed: dict[int, dict]) -> dict[str, dict]:
    """Employer key -> the interview or offer running there, if one is.

    An employer can have an interview running while the same list offers a
    nudge on another application there to the same talent-acquisition team. A
    second approach mid-process reads as scattered to exactly the people
    assessing them. An interview row does not time out here the way a silent
    application does in the throttle: a three-round process can outlast
    SILENCE_DAYS, and a wrong nudge during one costs more than a missed one on
    a side application.
    """
    out: dict[str, dict] = {}
    for r in rows:
        if _status(r) in LIVE_PROCESS and id(r) not in closed:
            k = company_key(r.get("company"))
            if k:
                out.setdefault(k, r)
    return out


def outreach_note(row: dict, docs: str = DOCS) -> str:
    """documents/applications/<slug>/outreach.md for this row, or "".

    The folder name comes from `outreach.slug`, the function that wrote it, with
    the abbreviation read off the row's resume. Folders from before the
    abbreviation joined the name are tried without it.
    """
    m = _ABBR.search(str(row.get("cv_file") or ""))
    for abbr in ((m.group(1), "") if m else ("",)):
        try:
            folder = outreach.slug(row.get("company") or "", row.get("role") or "", abbr)
        except ValueError:
            return ""
        path = os.path.join(docs, folder, "outreach.md")
        if os.path.isfile(path):
            return path
    return ""


def _first_name(name) -> str:
    """The name to greet by, from the same rule every other message uses.

    This read the first word of `state.person_name`, a second copy of the
    greeting rule, and it drifted twice: it dropped a preferred name in
    brackets ("Xiu Mei (Sally) Ho" came out "Xiu") and read "Halloway, Wren"
    as "Halloway". An address on its own is still nobody to greet.
    """
    parts = state.person_name(name).split()
    if not parts or "@" in parts[0]:
        return ""
    first = tone.first_name(name)
    return first if first[:1].isalpha() else ""


def recipient(row: dict, people=(), docs: str = DOCS,
              today: datetime.date | None = None) -> dict:
    """Who a nudge on this application goes to, how, and where that came from.

    First match wins: a person named on the tracker row, then the outreach note
    written with the application, then somebody at the employer who has replied.
    {} when there is nobody, which the caller says plainly.

    `people` is the employer's entry from `throttle.warm_routes`, and only a
    status in `throttle.RESPONDED` is read from it, whatever the caller passed.
    Somebody sitting on an unanswered message is not a route, and a nudge about
    an application sent through them is a second unanswered message with a
    worse subject.
    """
    named = str(row.get("contact_person") or "").strip()
    if named:
        return {"who": named, "name": _first_name(named),
                "how": "by email" if "@" in named else "",
                "source": "tracker contact_person"}
    note = outreach_note(row, docs)
    if note:
        with open(note, encoding="utf-8") as fh:
            m = _SEND_ON.search(fh.read())
        return {"who": m.group("who").strip() if m else "the hiring manager or the recruiter",
                "name": "", "how": "on " + m.group("channel").strip() if m else "",
                "source": os.path.relpath(note, ROOT) if note.startswith(ROOT) else note}
    for p in people or ():
        if p.get("status") not in throttle.RESPONDED:
            continue
        if today is not None and state.action_hold(p.get("next_action"), today):
            continue
        who = p.get("name") or "?"
        if p.get("title"):
            who += ", " + p["title"]
        return {"who": "%s, who has replied at this employer [%s]" % (who, p.get("status")),
                "name": _first_name(p.get("name")), "how": "in that thread",
                "source": "network_contacts.csv"}
    return {}


def _notice_day(day: datetime.date) -> datetime.date:
    """The day a one-off notice is shown: the day itself, or the first working day after a weekend.

    Said once means said on a day somebody reads it. The routine pasting this
    into a push notification may run on weekdays only, and a stop falling on a
    Saturday would then never be said at all.
    """
    # state.WEEKEND: the profile's working week, and a weekend when there is no profile.
    while day.weekday() in state.WEEKEND:
        day += datetime.timedelta(days=1)
    return day


def review(rows: list[dict], today: datetime.date, warm: dict | None = None,
           holds: dict | None = None, docs: str = DOCS) -> list[dict]:
    """Where every sent application's follow-up stands, oldest first.

    One entry per `applied` row with a readable date, in one of five states:

      due       a nudge is owed today or earlier; `to` says who it goes to
      held      a nudge would be owed and something says wait; `held` says what
      waiting   nothing is owed yet
      quiet     gone quiet: stop chasing; `notice` is true on the one day to say so
      closed    a later row for the same role is the application now

    `warm` and `holds` are `throttle.warm_routes()` and
    `throttle.referral_holds()`, or those functions run over rows the caller
    already holds. Each entry carries the row it came from, so a caller that
    groups by employer can place it without re-reading the tracker.
    """
    warm, holds = warm or {}, holds or {}
    closed = superseded(rows)
    running = live_processes(rows, closed)
    out: list[dict] = []
    for r in rows:
        if _status(r) != "applied":
            continue
        applied = _iso(r.get("date"))
        if applied is None:
            continue
        k = company_key(r.get("company"))
        role = str(r.get("role") or "").strip()
        it = {"row": r, "key": k, "company": str(r.get("company") or "").strip(),
              "role": role, "date": applied.isoformat(), "age": (today - applied).days,
              "state": "waiting", "nudge": 0, "sent": 0, "due_on": "", "late": 0,
              "quiet_on": "", "notice": False, "held": [], "closed_by": None,
              "to": {}, "needs_role": bool(_PLACEHOLDER_ROLE.search(role)), "message": ""}
        out.append(it)
        if id(r) in closed:
            it.update(state="closed", closed_by=closed[id(r)])
            continue

        sent = nudges_sent(r.get("notes"))
        dated = [d for d in sent if d is not None]
        last = max(dated) if dated else None
        it["sent"] = len(sent)

        # Nothing ever stopped being due. A row two nudges and six weeks past
        # its application was listed exactly like one from last week, every
        # day, while the throttle holds that an application silent for
        # SILENCE_DAYS has stopped counting. The same number ends the chase
        # here, or a week of silence after the second nudge if that comes
        # first, and the row is said to have gone quiet once, not listed as due.
        quiet_on = applied + datetime.timedelta(days=SILENCE_DAYS)
        if len(sent) >= MAX_NUDGES and last is not None:
            quiet_on = min(quiet_on, last + datetime.timedelta(days=NUDGE_GAP_DAYS))
        it["quiet_on"] = quiet_on.isoformat()
        if today >= quiet_on:
            it.update(state="quiet", notice=_notice_day(quiet_on) == today)
            continue
        if len(sent) >= MAX_NUDGES:
            continue                         # both have gone; nothing left to send

        n = len(sent) + 1
        if n == 1:
            due_on = applied + datetime.timedelta(days=FIRST_NUDGE_DAYS)
        else:
            base = last or applied + datetime.timedelta(days=FIRST_NUDGE_DAYS)
            due_on = base + datetime.timedelta(days=NUDGE_GAP_DAYS)
        it.update(nudge=n, due_on=due_on.isoformat())
        if today < due_on:
            continue
        it["late"] = (today - due_on).days

        reasons = []
        if n == 2 and last is None:
            # Timing the second from a guess is how it lands the day after a
            # late first: say what is missing instead of guessing.
            reasons.append("the first follow-up is logged without a date, so the second "
                           "cannot be timed: add the date to that note")
        note = not_chased(r.get("notes"), today)
        if note:
            reasons.append("tracker note: " + _clip(note))
        live = running.get(k)
        if live is not None:
            reasons.append("live process here: %s for %s, since %s" % (
                _status(live), live.get("role") or "?", live.get("date") or "?"))
        if k in holds:
            reasons.append(_clip(holds[k]))
        if reasons:
            it.update(state="held", held=reasons)
            continue

        it["state"] = "due"
        it["to"] = recipient(r, warm.get(k, ()), docs, today)
        if it["to"] and not it["needs_role"]:
            tpl = NUDGE_1 if n == 1 else NUDGE_2
            it["message"] = tpl.format(name=it["to"].get("name") or "[name]",
                                       role=role, date=it["date"])
    out.sort(key=lambda x: -x["age"])
    return out


def due(rows: list[dict], today: datetime.date, warm: dict | None = None,
        holds: dict | None = None, docs: str = DOCS) -> list[dict]:
    """Every application owed a nudge today or earlier, oldest first."""
    return [x for x in review(rows, today, warm, holds, docs) if x["state"] == "due"]


def to_line(it: dict) -> str:
    """Who this nudge goes to, as one line, or the plain statement that nobody is on file."""
    to = it.get("to") or {}
    if not to:
        return NO_RECIPIENT
    line = "to: " + to["who"]
    if to.get("how"):
        line += ", " + to["how"]
    if to.get("source"):
        line += " (%s)" % to["source"]
    return line


def body(it: dict) -> str:
    """The draft to send, or why there is none. "" when the recipient line says it all."""
    if it.get("needs_role"):
        return ("no draft: the tracker records %r where a job title goes. Put the real "
                "title in that row and run this again." % (it.get("role") or "",))
    return it.get("message") or ""


def stop_line(it: dict) -> str:
    """The one-off notice for an application that has gone quiet."""
    why = ("two follow-ups and no reply" if it.get("sent", 0) >= MAX_NUDGES
           else "%d days since it went and no reply" % it["age"])
    return ("%s - %s, applied %s: %s. Stop chasing it; the brief closes it as no_response."
            % (it["company"], it["role"] or "role not recorded", it["date"], why))


# The note a closed row carries, so the close is dated, says why and says how to undo it.
CLOSED_NOTE = ("%s: closed as no_response, %s (followups.py --close-quiet). "
               "If they reply after all, /outcome records it.")


def close_quiet(path: str = TRACKER, today: datetime.date | None = None,
                write: bool = True, holds: dict | None = None) -> list[dict]:
    """Close every application that has gone quiet as `no_response`, with a dated note.

    A row sat at `applied` for months after the chase ended: nothing wrote the close,
    because that waited on somebody running /outcome about silence, which is the one
    thing nobody notices. The throttle already stops counting such a row; this records
    what the throttle assumed. A row is left open while anything says it may still be
    alive: an interview or offer at that employer, a referral in flight there, or a
    DO NOT CHASE note in force. Returns the review entries it closed (or would close).
    """
    import csv_store  # the tracker's shared reader and writer: columns and line endings kept
    today = today or datetime.date.today()
    rows = csv_store.read_rows(path)
    if not rows:
        return []
    holds = throttle.referral_holds() if holds is None else holds
    running = live_processes(rows, superseded(rows))
    gone = [it for it in review(rows, today, holds=holds)
            if it["state"] == "quiet" and it["key"] not in holds and it["key"] not in running
            and not not_chased(it["row"].get("notes"), today)]
    if not gone or not write:
        return gone
    for it in gone:
        r = it["row"]
        why = ("two follow-ups and no reply" if it["sent"] >= MAX_NUDGES
               else "no reply in %d days" % it["age"])
        r["status"] = "no_response"
        note = CLOSED_NOTE % (today.isoformat(), why)
        r["notes"] = ((r.get("notes") or "").rstrip() + " | " + note).strip(" |")
    csv_store.write_rows(path, rows, csv_store.header(path))
    return gone


def when(it: dict) -> str:
    """The timing, as `nudge 1 of 2, due <date>, 1d late` or `... due today`."""
    late = "due today" if it["late"] <= 0 else "%dd late" % it["late"]
    return "nudge %d of %d, due %s, %s" % (it["nudge"], MAX_NUDGES, it["due_on"], late)


def render(items: list[dict], today: datetime.date) -> list[str]:
    lines: list[str] = []
    due_now = [x for x in items if x["state"] == "due"]
    held = [x for x in items if x["state"] == "held"]
    quiet = [x for x in items if x["state"] == "quiet"]
    for it in due_now:
        lines.append("")
        lines.append("[%dd] %s - %s   (%s)" % (it["age"], it["company"], it["role"], when(it)))
        lines.append("   " + to_line(it))
        if body(it):
            lines.append("   " + body(it))
    if held:
        lines.append("")
        lines.append("HELD, not to send (%d): the nudge would be due, and this is why not" % len(held))
        for it in held:
            lines.append("[%dd] %s - %s   (%s)" % (it["age"], it["company"], it["role"], when(it)))
            for why in it["held"]:
                lines.append("   held: " + why)
    notices = [x for x in quiet if x["notice"]]
    if notices:
        lines.append("")
        lines.append("GONE QUIET TODAY (%d), said once" % len(notices))
        for it in notices:
            lines.append("   " + stop_line(it))
    lines.append("")
    if not due_now:
        lines.append("nothing due")
    else:
        lines.append("%d due. After sending, append '%s' to that row's tracker notes; the "
                     "second nudge is timed from that date." % (len(due_now), LOG_AS % today))
        nobody = sum(1 for x in due_now if not x["to"])
        if nobody:
            lines.append("%d of them have no recipient on file and got no draft." % nobody)
        vague = sum(1 for x in due_now if x["needs_role"])
        if vague:
            lines.append("%d of them have no usable job title in the tracker and got no draft."
                         % vague)
    if held:
        lines.append("%d held." % len(held))
    if quiet:
        lines.append("%d gone quiet in all and no longer chased; `followups.py --close-quiet` "
                     "closes them as no_response, and the brief runs it." % len(quiet))
    return lines


def main() -> int:
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--close-quiet", action="store_true",
                    help="close every application gone quiet as no_response, with a dated note")
    ap.add_argument("--dry-run", action="store_true", help="with --close-quiet: list, write nothing")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today)
    if a.close_quiet:
        gone = close_quiet(today=today, write=not a.dry_run)
        verb = "would close" if a.dry_run else "closed"
        print("%s %d gone quiet as no_response%s" % (
            verb, len(gone), ": " + "; ".join("%s (%s, applied %s)" % (
                it["company"], it["role"] or "role not recorded", it["date"]) for it in gone)
            if gone else ""))
        return 0
    items = review(_rows(), today, warm=throttle.warm_routes(), holds=throttle.referral_holds())
    print("\n".join(render(items, today)).lstrip("\n"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
