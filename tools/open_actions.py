#!/usr/bin/env python3
"""One view of everything in flight, across applications and conversations.

The two halves of this system each had their own answer to "what now". The
tracker knew about applications and `/threads` knew about conversations, and
neither knew about the other, so the honest answer to "what is happening at
<employer>" was two commands and a mental join. This renders the join: employers first,
each carrying its applications, its contacts and what is owed, ordered by how
close each one is to an outcome.

`tools/company_key.py` is the join, the same key the throttle and the
networking store use, so a short name and a legal name are one employer here
exactly as they are everywhere else.

Nothing here is stored. It is derived on every run from the tracker, the
contacts and the message log, which is what stops it going stale the way a
hand-kept action list does. If an action is missing, the fix is the state file,
not this view.

## --due, for a morning routine

The full view answers "what is happening". `--due` answers "what do I do
today": only what is due today or overdue, both halves, and what a hold is
keeping back. It is a second rendering of the same derivation, not a second
tool, because a separate daily-brief script would be one more reader of the
three state files with its own copy of the joins and the holds, and the
follow-up engine it would sit on was itself unreachable for a month for exactly
that reason (see `followups.py`).

A scheduled routine runs it in a fresh session and pastes the top into a push
notification, so the first five lines stand alone: the counts, then one line
each for overdue people, overdue applications, due today, and held. It reads
no network and nothing but the three state files and the outreach notes, and
the same files and `--today` always print the same text.

    python3 tools/open_actions.py                 # everything owed, grouped
    python3 tools/open_actions.py --company acme  # one employer
    python3 tools/open_actions.py --due           # due today or overdue, summary first
    python3 tools/open_actions.py --markdown      # write documents/network/open_actions.md
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "network"))

import followups                                     # noqa: E402
import person                                        # noqa: E402
import throttle                                      # noqa: E402
from company_key import key as company_key            # noqa: E402
from network import state                             # noqa: E402

ROOT = os.path.dirname(_HERE)
TRACKER = person.state("job_search_tracker.csv")
OUT_MD = person.state("documents", "network", "open_actions.md")

# Tracker statuses that mean the application is finished.
FINAL = {"hired", "rejected", "no_response", "no response", "offer_declined",
         "offer declined", "withdrawn", "declined"}

# How close an employer is to an outcome. Higher sorts first, because the list
# is read top-down and the thing nearest a decision is the thing worth the next
# hour.
HEAT = {
    # The tracker writes `interview` and `offer`, the /outcome vocabulary. This
    # table keyed on `interviewing` alone, so an employer with an interview
    # under way sorted below a call booked with an employer that does not hire
    # for the role.
    "offer": 100,
    "interview": 100,
    "interviewing": 100,
    "call_booked": 90,
    "referral_in_progress": 85,
    "replied_needs_response": 80,
    "in_conversation": 60,
    "applied": 50,
    # Accepted and silent is warmer than sent and silent: a free DM channel and
    # a click of interest. It had no entry, and once the log derived it one
    # employer sank to 0, below every employer nobody has written to.
    "connected_no_reply": 45,
    "awaiting_reply": 40,
    "drafted": 20,
    "not_contacted": 10,
}

# Within one half of the due list, the order `state.owed` already argues for:
# somebody who answered and is waiting, then a date the candidate set, then a
# nudge. Application follow-ups come after all three, because a person is not
# waiting on one.
KIND_ORDER = {"reply": 0, "action_due": 1, "nudge": 2,
              # A request still pending and a first message owed after an
              # acceptance used to be listed as nudges; they keep a nudge's place.
              "first_message": 2, "request_pending": 2}


def _tracker(path=TRACKER):
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _network(contacts, threads):
    """Every contact's derived status, and the two throttle views read from it.

    The heat, the replied-contact recipients and the referral holds all need
    the statuses, and the last two must judge the rows handed in rather than a
    second read of the file, so they are computed once, here.
    """
    live = {}
    for c in contacts:
        cid = str(c.get("contact_id") or "").strip()
        live[cid] = state.effective_status(c, state.threads_for(threads, cid))
    return (live, throttle.warm_routes(rows=contacts, live=live),
            throttle.referral_holds(rows=contacts, live=live))


def build(contacts, threads, tracker, today, docs=None):
    """Employer key -> everything in flight there, sorted hottest first."""
    by_key: dict[str, dict] = {}
    live, warm, holds = _network(contacts, threads)
    # A nudge that is due is owed exactly the way a reply is owed, and it used
    # to live in a tool nothing imported. Keyed by id() of the tracker row so
    # two applications at one employer do not collide. Everything but
    # `waiting` rides along: a held nudge shows its reason, a superseded row
    # shows as closed, and a quiet one says so once.
    reviewed = {id(n["row"]): n for n in followups.review(
        tracker, state.as_date(today), warm, holds, docs or followups.DOCS)}

    def slot(k, display):
        e = by_key.setdefault(k, {"key": k, "name": display, "applications": [],
                                  "contacts": [], "owed": [], "heat": 0})
        if display and len(display) > len(e["name"]):
            e["name"] = display
        return e

    for row in tracker:
        k = company_key(row.get("company"))
        if not k:
            continue
        e = slot(k, (row.get("company") or "").strip())
        e["applications"].append(row)
        status = (row.get("status") or "").strip().lower()
        n = reviewed.get(id(row))
        if status not in FINAL and not (n and n["state"] == "closed"):
            e["heat"] = max(e["heat"], HEAT.get(status, 0))
        if n and n["state"] != "waiting":
            e.setdefault("nudges", []).append(n)

    owed_ids = {r.get("contact_id") for r in state.owed(contacts, threads, today)}
    for c in contacts:
        k = state.row_company_key(c) if hasattr(state, "row_company_key") else company_key(c.get("company"))
        if not k:
            continue
        e = slot(k, (c.get("company") or "").strip())
        e["contacts"].append(c)
        status = live.get(str(c.get("contact_id") or "").strip()) or ""
        e["heat"] = max(e["heat"], HEAT.get(status, 0))
        if c.get("contact_id") in owed_ids or (c.get("next_action") or "").strip():
            e["owed"].append((c, status))

    return sorted(by_key.values(),
                  key=lambda e: (-e["heat"], -len(e["owed"]), e["name"].lower()))


def render(entries, today, only_live=True):
    lines = []
    for e in entries:
        nudges = e.get("nudges", [])
        state_of = {id(n["row"]): n for n in nudges}
        superseded = {i for i, n in state_of.items() if n["state"] == "closed"}
        live_apps = [a for a in e["applications"]
                     if (a.get("status") or "").strip().lower() not in FINAL
                     and id(a) not in superseded]
        shown = [n for n in nudges
                 if n["state"] in ("due", "held") or (n["state"] == "quiet" and n["notice"])]
        if only_live and not e["owed"] and not live_apps and not shown:
            continue
        lines.append("## %s" % (e["name"] or e["key"]))
        live_ids = {id(a) for a in live_apps}
        for a in live_apps:
            quiet = state_of.get(id(a), {}).get("state") == "quiet"
            lines.append("- application: **%s** %s (%s)%s"
                         % (a.get("status", "?"), a.get("role", "?"), a.get("date", "?"),
                            ", gone quiet, not chased" if quiet else ""))
        for a in e["applications"]:
            if id(a) in live_ids:
                continue
            later = state_of.get(id(a), {}).get("closed_by")
            lines.append("- closed: %s %s%s" % (
                a.get("status", "?"), a.get("role", "?"),
                " (the later %s row of %s is that application now)"
                % (later.get("status") or "?", later.get("date") or "?") if later else ""))
        for n in shown:
            if n["state"] == "due":
                lines.append("- **follow-up due**: %s, applied %s (%dd, %s)"
                             % (n["role"] or "role not recorded", n["date"], n["age"],
                                followups.when(n)))
                lines.append("  - " + followups.to_line(n))
                if followups.body(n):
                    lines.append("  - " + followups.body(n))
            elif n["state"] == "held":
                lines.append("- follow-up held: %s, applied %s (%s). %s"
                             % (n["role"] or "role not recorded", n["date"],
                                followups.when(n), "; ".join(n["held"])))
            else:
                lines.append("- **gone quiet, stop**: " + followups.stop_line(n))
        for c, status in e["owed"]:
            who = "**%s**%s" % (c.get("name", "?"),
                               (", " + c["title"]) if c.get("title") else "")
            lines.append("- %s [%s] %s" % (who, status,
                                           (c.get("next_action") or "no action recorded")))
            if (c.get("next_action_due") or "") and c["next_action_due"] <= today:
                # A HOLD or FREEZE with a date on it is a date to look again,
                # not a date to send. Marking it DUE put a freeze in the
                # same list as the messages that were actually owed.
                hold = state.action_hold(c.get("next_action"), today)
                lines[-1] += ("  HELD, %s" % hold) if hold else "  **DUE %s**" % c["next_action_due"]
        # Contacts with nothing outstanding still matter: they are who is
        # already known at this employer, which is what stops a future run
        # opening a cold thread beside a warm one. Named, not detailed.
        loud = {id(c) for c, _ in e["owed"]}
        quiet = sorted(c.get("name", "?") for c in e["contacts"] if id(c) not in loud)
        if quiet:
            lines.append("- also here: %s%s" % (", ".join(quiet[:10]),
                         " and %d more" % (len(quiet) - 10) if len(quiet) > 10 else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- --due


def _stored_draft(contact) -> str:
    """The message waiting in a contact's notes. Everything after "| DRAFT:" is it."""
    notes = str(contact.get("notes") or "")
    return notes.split("| DRAFT:", 1)[1].strip() if "| DRAFT:" in notes else ""


def due_items(contacts, threads, tracker, today, docs=None):
    """Everything due today or overdue in both halves, plus what a hold is keeping back.

    Contacts: everything `state.owed` lists, which is only ever what is owed
    now (a reply the moment they answer, a nudge once its clock has run, a
    date the person set on themselves), so the rule lives there once. Each is
    dated by the person's own `next_action_due` where there is one, else by
    when it fell owed, else today. Applications: every follow-up
    `followups.review` finds due or held, and a gone-quiet notice on its one
    day. Unsorted; `render_due` orders it.
    """
    today = state.as_date(today)
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    items = []
    for o in state.owed(contacts, threads, today):
        # A reply nobody put a date on is owed all the same. Reading only
        # next_action_due dropped it, and the brief's first line said
        # "0 replies owed" while someone sat waiting for an answer.
        c = by_id.get(o["contact_id"], {})
        due = state.as_date(o["next_action_due"] or o.get("due")) or today
        name = o["name"] or o["contact_id"]
        who = name + "".join(", " + x for x in (c.get("title"), o["company"]) if x)
        items.append({
            "half": "contact", "key": o["company_key"], "rank": KIND_ORDER.get(o["kind"], 9),
            "name": name + (" (%s)" % o["company"] if o["company"] else ""),
            "who": "%s [%s]" % (who, o["status"]), "due": due.isoformat(),
            "late": (today - due).days, "what": o["next_action"], "to": "",
            "text": _stored_draft(c),
            "held": [h for h in (state.action_hold(o["next_action"], today),) if h],
            "quiet": False, "kind": o["kind"], "status": o["status"]})
    _, warm, holds = _network(contacts, threads)
    for n in followups.review(tracker, today, warm, holds, docs or followups.DOCS):
        quiet = n["state"] == "quiet" and n["notice"]
        if n["state"] not in ("due", "held") and not quiet:
            continue
        role = n["role"] or "role not recorded"
        items.append({
            "half": "application", "key": n["key"], "rank": len(KIND_ORDER),
            "name": "%s (%s)" % (n["company"], role if len(role) <= 40 else role[:37] + "..."),
            "who": "%s - %s" % (n["company"], role),
            "due": n["due_on"] or n["quiet_on"], "late": n["late"],
            "what": ("nudge %d of %d, applied %s" % (n["nudge"], followups.MAX_NUDGES, n["date"])
                     if not quiet else followups.stop_line(n)),
            "to": followups.to_line(n) if n["state"] == "due" else "",
            "text": followups.body(n) if n["state"] == "due" else "",
            "held": list(n["held"]), "quiet": quiet, "ready": bool(n["message"])})
    return items


def _urgency(i):
    return (i["half"] != "contact", i["rank"], -i["late"], i["name"].lower())


def _digest(label, items, late=True, note=""):
    """One standalone line naming a group and its first three members."""
    if not items:
        return "%s: none" % label
    shown = "; ".join("%s%s" % (i["name"], " %dd" % i["late"] if late and i["late"] > 0 else "")
                      for i in items[:3])
    more = " +%d more" % (len(items) - 3) if len(items) > 3 else ""
    return "%s (%d%s): %s%s" % (label, len(items), note, shown, more)


def render_due(items, today):
    """The due list, summary first. The first five lines are written to stand alone."""
    live = [i for i in items if not i["held"] and not i["quiet"]]
    over = sorted((i for i in live if i["late"] > 0), key=_urgency)
    now = sorted((i for i in live if i["late"] <= 0), key=_urgency)
    held = sorted((i for i in items if i["held"] and not i["quiet"]), key=_urgency)
    quiet = sorted((i for i in items if i["quiet"]), key=_urgency)

    people = [i for i in over if i["half"] == "contact"]
    apps = [i for i in over if i["half"] == "application"]
    ready = sum(1 for i in apps if i.get("ready"))
    # "N overdue" as the whole first line is the line a phone shows. It lumps
    # people waiting on a reply with a queue of first messages nobody is
    # waiting for (they wait on the weekly connection cap) and application
    # follow-ups with no one to send them to. The count stays, and says what it
    # is made of.
    replies = sum(1 for i in over + now if i.get("kind") == "reply")
    queued = sum(1 for i in over + now if i.get("status") == "not_contacted")
    no_one = sum(1 for i in apps if not i.get("ready"))
    head = [
        "%s: %d overdue, %d due today, %d blocked by holds%s (%d replies owed, "
        "%d first messages queued, %d application follow-ups with no recipient)"
        % (today, len(over), len(now), len(held),
           ", %d gone quiet" % len(quiet) if quiet else "", replies, queued, no_one),
        _digest("Overdue, people", people),
        _digest("Overdue, applications", apps, note=", %d ready to send" % ready),
        _digest("Due today", now, late=False),
        _digest("Blocked by holds", held, late=False)
        + (" | " + _digest("Gone quiet, stop chasing", quiet, late=False) if quiet else ""),
    ]

    body = []
    for title, group in (("OVERDUE (%d), most urgent first" % len(over), over),
                         ("DUE TODAY (%d)" % len(now), now),
                         ("BLOCKED BY HOLDS (%d): due, and a hold says not yet" % len(held), held),
                         ("GONE QUIET TODAY (%d), said once" % len(quiet), quiet)):
        if not group:
            continue
        body += ["", title]
        for i in group:
            if i["quiet"]:
                body.append("- " + i["what"])
                continue
            when = "" if i["held"] else ("%dd late: " % i["late"] if i["late"] > 0 else "today: ")
            what = "" if i["half"] == "contact" else ", " + i["what"]
            body.append("- %s%s%s" % (when, i["who"], what))
            body += ["    held: " + why for why in i["held"]]
            if i["half"] == "contact":
                body.append("    do: " + i["what"])
            elif i["to"]:
                body.append("    " + i["to"])
            if i["text"]:
                body.append("    text: " + i["text"])
    return "\n".join(head + body) + "\n"


def main():
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", help="one employer, by any spelling of its name")
    ap.add_argument("--all", action="store_true",
                    help="include employers with nothing outstanding")
    ap.add_argument("--due", action="store_true",
                    help="only what is due today or overdue, both halves, summary first")
    ap.add_argument("--markdown", action="store_true",
                    help="write documents/network/open_actions.md")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    today = dt.date.fromisoformat(a.today)
    contacts, threads = state.load_contacts(), state.load_threads()

    if a.due:
        items = due_items(contacts, threads, _tracker(), today)
        if a.company:
            want = company_key(a.company)
            items = [i for i in items if i["key"] == want]
        sys.stdout.write(render_due(items, a.today))
        return 0

    entries = build(contacts, threads, _tracker(), today)

    if a.company:
        want = company_key(a.company)
        entries = [e for e in entries if e["key"] == want]
        if not entries:
            print("nothing in flight at %r (key %r)" % (a.company, want))
            return 0

    body = render(entries, a.today, only_live=not a.all)
    header = ("# Open actions, %s\n\n"
              "Generated by `python3 tools/open_actions.py --markdown`. Do not hand-edit:\n"
              "it is rebuilt from `job_search_tracker.csv`, `network_contacts.csv` and\n"
              "`network_threads.csv`, and an edit here is overwritten on the next run.\n"
              "To change an action, change the state file it comes from.\n\n"
              "Employers are ordered by how close they are to an outcome.\n\n" % a.today)

    if a.markdown:
        os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
        with open(OUT_MD, "w") as fh:
            fh.write(header + body)
        print("wrote %s (%d employers)" % (OUT_MD, body.count("\n## ") + body.startswith("## ")))
    else:
        print(header + body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
