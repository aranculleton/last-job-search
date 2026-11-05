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
no network and nothing but the three state files, the outreach notes and each
live application's outcome.md, and the same files and `--today` always print
the same text.

A resume somebody asked for is owed exactly as a reply is: "a resume owed to <name>",
from their request until a message logged to them says one went (state.resumes_owed),
with the command that logs it with its file. A resume that went shows on its employer's
line with the date and the file, so which one they hold is never a question.

An interview booked in outcome.md (`- [ ] Phone screen (scheduled 2026-03-14,
with Head of Planning)`, as /outcome writes it) is on the list twice over: due
today once it is `PREP_WINDOW_DAYS` away with no `interview_prep_*.md` for that
stage in the folder, and after it, while no thank-you note sits there.

    python3 tools/open_actions.py                 # everything owed, grouped
    python3 tools/open_actions.py --company acme  # one employer
    python3 tools/open_actions.py --due           # due today or overdue, summary first
    python3 tools/open_actions.py --markdown      # write documents/network/open_actions.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "network"))

import followups                                     # noqa: E402
import docpaths                                      # noqa: E402
import person                                        # noqa: E402
import throttle                                      # noqa: E402
import what_works                                    # noqa: E402
from company_key import key as company_key            # noqa: E402
from network import state                             # noqa: E402

ROOT = os.path.dirname(_HERE)
TRACKER = person.state("job_search_tracker.csv")
OUT_MD = person.state("documents", "network", "open_actions.md")

# Tracker statuses that mean the application is finished: the throttle's set, so the
# two never drift (a copy elsewhere lost "declined" once).
FINAL = throttle.FINAL

# How close an employer is to an outcome. Higher sorts first, because the list
# is read top-down and the thing nearest a decision is the thing worth the next
# hour.
HEAT = {
    # The tracker writes `interview` and `offer`, the /outcome vocabulary. This
    # table keyed on `interviewing` alone, so an employer with an interview
    # under way sorted below a call booked with an employer that does not hire
    # for the role. The live statuses come from the one vocabulary (throttle.py).
    **dict.fromkeys(throttle.LIVE_PROCESS, 100),
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

# An interview booked in outcome.md: its pack is due once it is this close, and
# a thank-you is owed for this long after it, then the list lets it go. It sorts
# before the follow-up nudges: the date is fixed and somebody is expecting them.
PREP_WINDOW_DAYS = 7
THANKS_DAYS = 7
INTERVIEW_RANK = len(KIND_ORDER) - 1
# A stage written before 4.7 says what it is only in its words: a test or a take-home is
# something to finish by its day (the same words tools/upcoming.py reads).
_TEST_WORDS = re.compile(r"\b(?:test|assessment(?! cent(?:re|er))|case study|take[- ]home|exercise|challenge|"
                         r"hirevue|coding task|assignment|questionnaire)\b", re.I)
# An interview, then nothing. A row at `interview` stays there however long the employer
# is silent: the nudges are for sent applications, and a live process is never timed out
# (followups.live_processes: a wrong nudge mid-process costs more than a missed one). So
# once the thank-you window closed the list went quiet for good, and a final round weeks
# past with no word never reached it. After this many days with nothing recorded since,
# it asks: a short status note, or the outcome. A question on the list, never a nudge.
INTERVIEW_QUIET_DAYS = 14
# The statuses that mean an interview is running. An offer is not here: what is owed then is
# the person's decision, not a word from the employer.
INTERVIEWING = followups.LIVE_PROCESS - {"offer"}


def _tracker(path=TRACKER):
    import csv_store
    return csv_store.tracker(path)


def network_views(contacts, threads, index=None):
    """Every contact's derived status, and the two throttle views read from it.

    The heat, the replied-contact recipients and the referral holds all need
    the statuses, and the last two must judge the rows handed in rather than a
    second read of the file, so they are computed once, here. `index` is
    `state.by_contact(threads)` when the caller has it already.
    """
    live = {}
    index = state.by_contact(threads) if index is None else index
    for c in contacts:
        cid = str(c.get("contact_id") or "").strip()
        live[cid] = state.effective_status(c, list(index.get(cid, ())))
    return (live, throttle.warm_routes(rows=contacts, live=live),
            throttle.referral_holds(rows=contacts, live=live))


_network = network_views  # the module's own name for it; other modules call network_views


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
    for item in state.resumes_owed(contacts, threads, tracker):
        if item["company_key"]:
            slot(item["company_key"], item["company"]).setdefault("resumes_owed", []).append(item)
    index = state.by_contact(threads)       # one pass over the log, not one a contact
    for c in contacts:
        k = state.row_company_key(c) if hasattr(state, "row_company_key") else company_key(c.get("company"))
        if not k:
            continue
        e = slot(k, (c.get("company") or "").strip())
        e["contacts"].append(c)
        cid = str(c.get("contact_id") or "").strip()
        for got in state.resumes_sent(index.get(cid, []), cid):
            e.setdefault("resumes_sent", []).append(dict(got, name=c.get("name", "")))
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
        resumes = e.get("resumes_owed", [])
        if only_live and not e["owed"] and not live_apps and not shown and not resumes:
            continue
        lines.append("## %s" % (e["name"] or e["key"]))
        chat = campaigns(live_apps).get(e["key"])
        if chat:
            # Shown whether or not anything is due: the brief and other chats leave this
            # employer to it, and two chats preparing one call contradict each other.
            lines.append("- **handled by its campaign chat (%s)**: its prep, drafts and drills "
                         "live there" % chat)
        live_ids = {id(a) for a in live_apps}
        for a in live_apps:
            quiet = state_of.get(id(a), {}).get("state") == "quiet"
            lines.append("- %s: **%s** %s (%s)%s"
                         % ("process, no application" if throttle.is_process(a) else "application",
                            a.get("status", "?"), a.get("role", "?"), a.get("date", "?"),
                            ", gone quiet, not chased" if quiet else ""))
            folder, files, stages = _stages(a)
            for st in stages:
                if not st["done"] and st["date"] and st["date"] >= str(today):
                    lines.append("  - booked: %s %s%s%s" % (
                        st["label"] or "interview", st["date"],
                        ", with " + st["with"] if st["with"] else "",
                        "" if _has_pack(files, st, folder) else ", no pack yet"))
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
        for item in resumes:
            lines.append("- " + state.resume_owed_line(item, mark="**"))
        for got in e.get("resumes_sent", []):
            lines.append("- %s sent to %s %s%s" % (
                state.noun(), got["name"] or "?", got["date"] or "(no date)",
                ": " + ", ".join(got["files"]) if got["files"] else ", which file not recorded"))
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


def stages(row):
    """(the application's folder, its files, its outcome.md stages), each empty when absent."""
    folder = docpaths.app_folder(row.get("company"), row.get("role") or "")
    try:
        files = os.listdir(folder)
        with open(os.path.join(folder, "outcome.md"), encoding="utf-8") as fh:
            return folder, files, what_works.outcome_stages(fh.read())
    except OSError:
        return folder, [], []


_stages = stages  # the module's own name for it; other modules call stages


def _has_pack(files, stage, folder="") -> bool:
    """A pack is on file for this stage: the process's living interview_prep.md built for a
    stage of the same step (its `<!-- stages: ... -->` line), or an older per-stage
    interview_prep_<stage>.md."""
    if "interview_prep.md" in files and folder:
        try:
            with open(os.path.join(folder, "interview_prep.md"), encoding="utf-8") as fh:
                m = re.search(r"^<!-- stages: (.*?) -->$", fh.read(), re.M)
        except OSError:
            m = None
        if m and any(what_works.stage_step(x) == stage["step"] for x in m.group(1).split("; ")):
            return True
    return any(f.startswith("interview_prep_") and f.endswith(".md")
               and what_works.stage_step(f[15:-3].replace("_", " ")) == stage["step"]
               for f in files)


# What "Done" on a thank-you writes into the row's notes (app_actions due.done): the note went
# by some other way than a file in the folder. A thank-you row had no Done at all, and was
# finished only by drafting one with Claude (the audit, 2026-11-03).
THANKED_NOTE = "thank-you sent"


def _thanked(files, held_on, notes="") -> bool:
    """A thank-you or follow-up note dated on or after the interview is in the folder, or the
    row's notes say one went on or after it."""
    for f in files:
        if f.startswith(("followup_", "thank_you_")):
            d = state.as_date(f)
            if d and d >= held_on:
                return True
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2}):[^|]*\b%s\b" % re.escape(THANKED_NOTE),
                         str(notes or "")):
        d = state.as_date(m.group(1))
        if d and d >= held_on:
            return True
    return False


def _held_by_now(st, now) -> bool:
    """Has a stage booked for today, with its time on record, ended by `now` (UTC)? Its
    thank-you is owed the same day, not the morning after (the audit, 2026-11-03)."""
    if now is None or not st.get("time"):
        return False
    try:
        import datetime as _dt
        import zoneinfo
        zone = st.get("zone") or ""
        name = zone if "/" in zone else _stage_zone(zone)
        h, m = (int(x) for x in st["time"].split(":"))
        start = _dt.datetime.combine(_dt.date.fromisoformat(st["date"]), _dt.time(h, m),
                                     tzinfo=zoneinfo.ZoneInfo(name))
    except Exception:  # noqa: BLE001  no zone data, or a time that is not one
        return False
    return start + dt.timedelta(minutes=int(st.get("minutes") or 60)) <= now


def _stage_zone(word) -> str:
    """The zone a stage line's word names, else the person's own."""
    import person
    got = person.ZONE_WORDS.get(str(word or "").upper()) if word else ""
    if got:
        return got
    try:
        return person.home_zone_named(person.directory()) or "UTC"
    except person.NoProfile:
        return "UTC"


def _last_word(row, files, stages, today):
    """(the last thing that happened on an interview row, its date, status notes sent since).

    The latest of: a stage held, the row's date, a dated entry in its notes, and a
    thank-you or follow-up note on file. None for the date when a stage is still booked
    ahead: a process with a date in it is not quiet.
    """
    if any(not st["done"] and st["date"] and st["date"] >= today.isoformat() for st in stages):
        return "", None, 0
    seen = []
    for st in stages:
        d = state.as_date(st["date"])
        if d and d <= today:
            seen.append((d, "the %s" % (st["label"] or "interview")))
    d = state.as_date(throttle.applied_on(row) or row.get("date"))
    if d:
        seen.append((d, "the last update"))
    for entry in str(row.get("notes") or "").split("|"):
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", entry)
        d = state.as_date(m.group(1)) if m else None
        if d and d <= today:
            seen.append((d, "the last note"))
    notes_sent = []
    for f in files:
        if f.startswith(("followup_", "thank_you_")):
            d = state.as_date(f)
            if d and d <= today:
                seen.append((d, "the last note you sent"))
                if f.startswith("followup_"):
                    notes_sent.append(d)
    notes_sent += [d for d in followups.nudges_sent(row.get("notes")) if d and d <= today]
    if not seen:
        return "", None, 0
    when, what = max(seen)
    stage = max((x for x in seen if x[1] not in ("the last update", "the last note",
                                                  "the last note you sent")),
                default=(None, ""))
    # A status note is one sent after the thank-you window: the thank-you is not one.
    after = stage[0] + dt.timedelta(days=THANKS_DAYS) if stage[0] else None
    sent_since = len({d for d in notes_sent if after and d > after})
    return what, when, sent_since


def _days_said(days) -> str:
    """"12, 13, 19 or 20 Nov": offered days said together."""
    got = [d for d in (state.as_date(x) for x in days) if d]
    words = []
    for n, d in enumerate(got):
        last = n == len(got) - 1 or got[n + 1].month != d.month
        words.append("%d%s" % (d.day, " " + d.strftime("%b") if last else ""))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def interview_items(tracker, today, now=None, read_stages=None):
    """The interview half of the due list, from each live application's outcome.md.

    A booked stage with no pack, from PREP_WINDOW_DAYS before it (due today,
    because the pack is wanted before the day), and a stage that has been and
    gone with no thank-you on file, for THANKS_DAYS after it: from the day after, or the
    same day once its time has passed (`now`). A test or a take-home is something to do by
    its day, never a meeting to prepare a pack for or thank anyone after. An invitation
    whose day is the person's to choose is a choice owed, by the day they are to answer.
    These are `urgent`: they sort before everything else owed (urgency). And an interview
    row with no word for INTERVIEW_QUIET_DAYS and nothing booked: a status note or
    the outcome, the person's call (after two notes, the outcome only). `read_stages` is
    `stages`, or a caller's own reading of it once per application (the page's model).
    """
    today = state.as_date(today)
    read_stages = read_stages or _stages
    items = []
    for row in tracker:
        status = (row.get("status") or "").strip().lower()
        if status in FINAL or status in throttle.UNSENT or not status:
            continue
        folder, files, stages = read_stages(row)
        company = (row.get("company") or "").strip()
        role = (row.get("role") or "").strip() or "role not recorded"
        for st in stages:
            held_on = state.as_date(st["date"])
            offered = [d for d in (st.get("offered") or []) if state.as_date(d)
                       and state.as_date(d) >= today]
            if not held_on and offered and not st["done"]:
                by = state.as_date(st.get("reply_by")) or state.as_date(offered[0])
                due = min(by, state.as_date(offered[0]))
                label = (st["label"][:1].lower() + st["label"][1:]) if st["label"] else "interview"
                what = "choose your %s day (%s) and tell %s" % (
                    label, _days_said(offered), st["with"] or "them")
                items.append({
                    "half": "application", "key": company_key(company), "rank": INTERVIEW_RANK,
                    "name": "%s (%s)" % (company, role if len(role) <= 40 else role[:37] + "..."),
                    "who": "%s - %s" % (company, role), "due": due.isoformat(),
                    "late": max((today - due).days, 0), "what": what, "to": "", "text": "",
                    "held": [], "quiet": False, "kind": "interview", "sub": "choose",
                    "offered": offered, "urgent": True})
                continue
            if not held_on:
                continue
            days = (held_on - today).days
            test = st.get("kind") == "test" or (not st.get("kind") and what_works.stage_step(
                st["label"]) != "offer" and bool(_TEST_WORDS.search(st["label"] or "")))
            what = "%s, %s%s" % (st["label"] or "interview", st["date"],
                                 ", with " + st["with"] if st["with"] else "")
            if test:
                # Something to finish by its day: said as that, and nothing after it.
                if st["done"] or not 0 <= days <= PREP_WINDOW_DAYS:
                    continue
                when = ("today" if days == 0 else "tomorrow" if days == 1
                        else "by %s %d %s" % (held_on.strftime("%a"), held_on.day, held_on.strftime("%b")))
                what = "do the %s %s (%s)" % (st["label"] or "test", when, st["date"])
                due, late, sub = today, 0, "test"
            elif not st["done"] and 0 <= days <= PREP_WINDOW_DAYS and \
                    not _has_pack(files, st, folder) and not (days == 0 and _held_by_now(st, now)):
                when = ("today" if days == 0 else "tomorrow" if days == 1
                        else "in %d days" % days)
                what = "interview %s (%s), no pack yet: /interview %s" % (when, what, company)
                due, late, sub = today, 0, "prep"
            elif (days < 0 or (days == 0 and _held_by_now(st, now))) and -days <= THANKS_DAYS \
                    and not _thanked(files, held_on, row.get("notes")) and st["step"] != "offer":
                # An offer received is not a meeting to thank anyone for: it asked for a
                # thank-you note after the offer, beside the one for the final round
                # (2026-11-03).
                what = ("thank-you not logged after the %s: /outcome %s records the stage "
                        "and drafts one" % (what, company))
                due = held_on if days == 0 else held_on + dt.timedelta(days=1)
                late = (today - due).days
                sub = "thank_you"
            else:
                continue
            items.append({
                "half": "application", "key": company_key(company), "rank": INTERVIEW_RANK,
                "name": "%s (%s)" % (company, role if len(role) <= 40 else role[:37] + "..."),
                "who": "%s - %s" % (company, role), "due": due.isoformat(), "late": late,
                "what": what, "to": "", "text": "", "held": [], "quiet": False,
                "kind": "interview", "sub": sub, "urgent": True, "stage": st["label"]})
        if status not in INTERVIEWING or any(i["who"] == "%s - %s" % (company, role)
                                             for i in items):
            continue
        last, when, sent_since = _last_word(row, files, stages, today)
        if when is None or (today - when).days < INTERVIEW_QUIET_DAYS:
            continue
        due = when + dt.timedelta(days=INTERVIEW_QUIET_DAYS)
        since = "%s, %s" % (last, when.isoformat())
        if sent_since >= followups.MAX_NUDGES:
            what = ("no word since %s, and %d status notes have gone: record what happened "
                    "(/outcome %s), and send no more" % (since, sent_since, company))
        else:
            what = ("no word for %d days since %s: send a short status note (/outcome followup "
                    "%s drafts one) or record what happened (/outcome %s)"
                    % ((today - when).days, since, company, company))
        hold = followups.not_chased(row.get("notes"), today)
        items.append({
            "half": "application", "key": company_key(company), "rank": INTERVIEW_RANK,
            "name": "%s (%s)" % (company, role if len(role) <= 40 else role[:37] + "..."),
            "who": "%s - %s" % (company, role), "due": due.isoformat(),
            "late": (today - due).days, "what": what, "to": "", "text": "",
            "held": ["tracker note: " + followups._clip(hold)] if hold else [], "quiet": False,
            "kind": "interview", "sub": "status_note"})
    return items


def _stored_draft(contact) -> str:
    """The message waiting in a contact's notes. Everything after "| DRAFT:" is it."""
    notes = str(contact.get("notes") or "")
    return notes.split("| DRAFT:", 1)[1].strip() if "| DRAFT:" in notes else ""


def due_items(contacts, threads, tracker, today, docs=None, network=None, now=None,
              index=None, read_stages=None):
    """Everything due today or overdue in both halves, plus what a hold is keeping back.

    `network` is `_network(contacts, threads)` when the caller has it already (the page's
    model does): on a big contact book it is the slowest part, and was worked out twice.
    `index` is `state.by_contact(threads)`, likewise: the log grouped once, not five times,
    and `read_stages` its reading of each application's stages (interview_items).

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
    index = (state.by_contact(threads) if threads else {}) if index is None else index
    items = []
    for o in state.owed(contacts, threads, today, index=index,
                        live=network[0] if network else None):
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
            "late": (today - due).days,
            # A send past its day with nothing logged may have gone from the LinkedIn app,
            # where the log never hears: two people listed "send now" already showed
            # Pending. Asked, never told to send again.
            "what": (("UNCONFIRMED: did this go? If it did: python3 tools/network/state.py sent "
                      f"{o['contact_id']} --draft (--text-file <the words> if it went with "
                      "other words, --outside if sent from LinkedIn itself). If not: "
                      + o["next_action"]) if o.get("unconfirmed") else o["next_action"]),
            "to": "",
            "text": _stored_draft(c),
            "held": [h for h in (state.action_hold(o["next_action"], today),) if h],
            "quiet": False, "kind": o["kind"], "status": o["status"],
            "contact_id": o["contact_id"], "old": bool(o.get("old")),
            "since": o.get("since", "")})
    # A first note queued for someone not written to yet goes through the one check every
    # list of people does (tools/network/surface.py): written to on another channel, or at
    # an employer the bar rules out, it is held with the reason, never "send now".
    queued = [i for i in items if i["status"] == "not_contacted"]
    if queued:
        import surface
        ctx = surface.context(contacts=contacts, threads=threads, today=today, index=index)
        for i in queued:
            got = surface.check(by_id.get(i["contact_id"]) or {"contact_id": i["contact_id"]},
                                ctx, queued=True)
            if not got["show"]:
                i["held"].append(got["reason"])
    # A resume somebody asked for: on their row when they have one here, else a row of its
    # own, owed since the day they asked (or the date the person set on it).
    # One asked for more than state.OLD_OWED_DAYS ago, with no date of the person's own on
    # it and none made for them since, is history like any other thread that has ended: set
    # aside, never "send it now" to someone who asked in 2021.
    for r in state.resumes_owed(contacts, threads, tracker, index=index):
        line = state.resume_owed_line(r)
        c = by_id.get(r["contact_id"], {})
        days = [d for d in (r["asked"], r["made"], r.get("made_on", "")) if d]
        old = (bool(days) and state.owed_too_long(max(days), today)
               and not state.dated_by_person(c, index.get(r["contact_id"], ())))
        # Asked long ago with nothing from them since: closed by itself, a date the chat
        # wrote to record the ask notwithstanding (state.RESUME_ASK_LAPSE_DAYS). It leaves
        # the owed list, the brief says so once, and their card and thread still hold it.
        lapsed = state.resume_ask_lapsed(r["asked"], index.get(r["contact_id"], ()), today,
                                         c.get("next_action_due")) if not (r["made"] or r.get("made_on")) else None
        got = next((i for i in items if i.get("contact_id") == r["contact_id"]), None)
        if got is not None:
            if lapsed:
                got.update(old=True, lapsed_on=lapsed.isoformat(), what=line)
            elif not old:
                got["what"], got["old"] = line, False
            continue
        if lapsed:
            old = True
        name = r["name"] or r["contact_id"]
        due = (state.as_date(c.get("next_action_due")) or state.as_date(r["asked"] or r["made"])
               or today)
        if due > today:                  # the person put a later day on it: not due yet
            continue
        who = name + "".join(", " + x for x in (c.get("title"), r["company"]) if x)
        items.append({
            "half": "contact", "key": r["company_key"], "rank": KIND_ORDER["reply"],
            "name": name + (" (%s)" % r["company"] if r["company"] else ""),
            "who": "%s [%s owed]" % (who, state.noun()), "due": due.isoformat(),
            "late": (today - due).days, "what": line, "to": "", "text": "",
            "held": [h for h in (state.action_hold(c.get("next_action"), today),) if h],
            "quiet": False, "kind": "resume", "status": c.get("status", ""),
            "contact_id": r["contact_id"], "old": old,
            **({"lapsed_on": lapsed.isoformat(), "asked": r["asked"]} if lapsed else {})})
    _hold_by_rule(items, by_id, threads, index)
    _, warm, holds = network or _network(contacts, threads)
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
    items += interview_items(tracker, today, now, read_stages)
    # An employer with a chat of its own (a campaign chat, interview_pack.py campaign): that
    # chat drafts what is owed there, and nothing else writes it. It is still owed, and still
    # shown: held, a reply about which interview day to choose reached no list, no Brief and
    # no To do (the audit, 2026-11-03).
    owned = campaigns(tracker)
    for i in items:
        chat = owned.get(i.get("key") or "")
        if chat:
            i["campaign"] = chat
    return items


def _hold_by_rule(items, by_id, threads, index=None) -> None:
    """Every contact item the person's own surface rules stop (surface.held: their limit of
    unanswered messages, an employer their bar turns down, somewhere outside where they
    look, a request nobody accepted, a thread closed) is held with the reason, and carries
    `rule` ({"why", "said"}) so a screen can say it: one check, so To do, Contacts, Messages
    and the brief never disagree about who may be written to (2026-11-03: the brief's due
    list and the page offered a third and a fourth message, and follow-ups at employers the
    person had turned down)."""
    import surface
    if index is None:
        index = state.by_contact(threads) if threads else {}
    memo: dict = {}
    for i in items:
        if i.get("half") != "contact" or i.get("kind") == "request_pending":
            continue
        c = by_id.get(i.get("contact_id") or "") or {"contact_id": i.get("contact_id")}
        got = surface.held(c, index.get(i.get("contact_id") or "", ()), i.get("status") or "",
                           replying=i.get("kind") in ("reply", "resume"), memo=memo)
        if got:
            i["rule"] = got
            i["held"] = list(i.get("held") or []) + [got["said"] or "closed"]


def campaigns(tracker) -> dict:
    """{company key: campaign chat} for every live process with a chat of its own."""
    import json as _json
    out = {}
    for row in tracker or ():
        if (row.get("status") or "").strip().lower() in FINAL:
            continue
        folder = docpaths.app_folder(row.get("company"), row.get("role") or "")
        try:
            with open(os.path.join(folder, "campaign.json"), encoding="utf-8") as fh:
                chat = str(_json.load(fh).get("chat") or "").strip()
        except (OSError, ValueError, AttributeError):
            continue
        if chat:
            out[company_key(row.get("company"))] = chat
    return out


def urgency(i):
    """The order owed things are done in. An interview's own (its prep before the day, the
    thank-you after it, a day to choose) first: its day is fixed and somebody is expecting
    them, and behind 550 follow-ups it sat 100th of 150 and past the page's cut (the audit,
    2026-11-03). Then people before applications, as before, except that any other interview
    row sorts among the people waiting, before the follow-up nudges (INTERVIEW_RANK's note),
    never after every contact item: with some 550 contact items it came at index 574 and the
    page's due list, cut at 100, never showed it (journeys audit 5)."""
    interview = i.get("kind") == "interview" and i["half"] == "application"
    return (not i.get("urgent"), i["half"] != "contact" and not interview,
            KIND_ORDER["nudge"] - 0.5 if interview else i["rank"], -i["late"],
            i["name"].lower())


_urgency = urgency  # the module's own name for it; other modules call urgency


def _digest(label, items, late=True, note=""):
    """One standalone line naming a group and its first three members."""
    if not items:
        return "%s: none" % label
    shown = "; ".join("%s%s" % (i["name"], " %dd" % i["late"] if late and i["late"] > 0 else "")
                      for i in items[:3])
    more = " +%d more" % (len(items) - 3) if len(items) > 3 else ""
    return "%s (%d%s): %s%s" % (label, len(items), note, shown, more)


def render_due(items, today):
    """The due list, summary first. The first five lines are written to stand alone.

    Two kinds are counted rather than listed among what to write. A request nobody
    accepted has nobody to write to: the job is withdrawing them, together, so they are one
    section. Something owed more than `state.OLD_OWED_DAYS` with nothing done is a thread
    that has ended (most often years of LinkedIn history brought in at once): counted on
    the first line, and `state.py` still lists each one."""
    old = [i for i in items if i.get("old")]
    items = [i for i in items if not i.get("old")]
    asks = sorted((i for i in items if i.get("kind") == "request_pending" and not i["held"]),
                  key=lambda i: (-i["late"], i["name"].lower()))
    items = [i for i in items if not (i.get("kind") == "request_pending" and not i["held"])]
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
    # waiting for (they wait on the person to send them) and application
    # follow-ups with no one to send them to. The count stays, and says what it
    # is made of.
    replies = sum(1 for i in over + now if i.get("kind") == "reply")
    queued = sum(1 for i in over + now if i.get("status") == "not_contacted")
    no_one = sum(1 for i in apps if not i.get("ready") and i.get("kind") != "interview")
    head = [
        "%s: %d overdue, %d due today, %d blocked by holds%s%s%s (%d replies owed, "
        "%d first messages queued, %d application follow-ups with no recipient)"
        % (today, len(over), len(now), len(held),
           ", %d gone quiet" % len(quiet) if quiet else "",
           ", %d requests to withdraw" % len(asks) if asks else "",
           ", %d owed over %d days set aside" % (len(old), state.OLD_OWED_DAYS) if old else "",
           replies, queued, no_one),
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
    if asks:
        body += ["", "REQUESTS TO WITHDRAW (%d): nobody accepted in %d days, so there is nobody "
                     "to write to. Withdraw on LinkedIn the ones you choose, then record those: "
                     "python3 tools/network/state.py withdraw <contact_id>... (--all-due "
                     "records every one listed here, and none held)"
                     % (len(asks), state.REQUEST_WITHDRAW_DAYS)]
        body += ["- %s, sent %s" % (i["who"], i.get("since") or "on a day not recorded")
                 for i in asks]
    if old:
        body += ["", "SET ASIDE (%d): owed more than %d days with nothing done, so not listed "
                     "here; python3 tools/network/state.py lists every one, and a date you put "
                     "on one (state.py set <contact_id> --due <date>) brings it back"
                     % (len(old), state.OLD_OWED_DAYS)]
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
        with open(OUT_MD, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(header + body)
        print("wrote %s (%d employers)" % (OUT_MD, body.count("\n## ") + body.startswith("## ")))
    else:
        print(header + body)
    return 0


if __name__ == "__main__":
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:  # a merge left markers: say which file, read nothing
        print(f"open_actions: {e}", file=sys.stderr)
        raise SystemExit(1) from None
