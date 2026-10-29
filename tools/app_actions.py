#!/usr/bin/env python3
"""What the person did on the page, applied to the repo exactly once, with a receipt.

The page writes an action (`actions/<id>`: item, action, value, at, rev_seen, tab) and a
chat applies it. Each action goes through the writer the chat commands already use, never
a copy of its rules:

    job.dismiss        exclude.py add, basis person            undone by job.bring_back
    job.bring_back     exclude.py lift; a filtered posting      undone by job.dismiss
                       goes back on its round (filtered.py back)
    job.draft          queues work/draft~<key>; writes nothing  undone by work.stop
                       in the repo
    job.applied        confirm.py applied --new (they applied   undone by ready.not_applied
                       outside the app)
    job.not_applied    confirm.py not-applied on its row        undone by ready.applied
    ready.applied      confirm.py applied                       undone by ready.not_applied
    ready.not_applied  confirm.py not-applied                   undone by ready.applied
    ready.not_applying confirm.py skip                          undone by ready.reopen
    ready.reopen       confirm.py reopen                        undone by ready.not_applying
    msg.sent           state.py sent / nudge / message, with    undone by msg.unsent
                       the words as they went (an edit to the
                       draft is learned by state.py itself)
    msg.unsent         state.py unsend                          undone by msg.sent
    msg.skip           state.py drop                            undone by msg.unskip
    msg.unskip         state.py reopen                          undone by msg.skip
    person.stop        state.py set --status closed             undone by person.status
    person.status      state.py set (status, next action, due)  undone by person.status
    consent.yes / .no  the answer on its work item (db only)    undone by the other one
    setting.set        person.json, tips.py, LINKEDIN_PLAN,     undone by setting.set
                       PROFILE_READS
    needs.answer       learned.py decide; a fact written where  undone by needs.unanswer
                       its [CONFIRM] mark was                   (a fact), or by saying so
    due.done           state.py set, a contact's dated next     undone by due.undo
                       action cleared; or "followed up <day>"
                       on the application's row (followups.py)
    tweak.undo         queues the tweak's undo as work (db only)  undone by work.stop
    suggest.dismiss    profile/app.json: that suggestion is     undone by suggest.undismiss
                       never offered again (tools/app_alerts.py)
    work.stop          stop_asked on a work item (db only)      undone by work.resume
    undo               the inverse its receipt recorded

The setup and update actions (setup.*, app.update_now, upgrade.undo) are in the table below.

Exactly once, three ways. An action with a receipt is never applied again. An action is
applied only while the item it was made on is as the person saw it (`rev_seen` is the
item's rev now): one made on something that has changed since is refused, receipt `stale`,
nothing written, so two devices that answered one question differently never overwrite
each other. And a run keeps a ledger in the dump folder, so running `apply` again before
the receipts are written back re-sends the same receipts instead of applying twice. Every
row an action writes is dated by the action's own time (`at`, in the person's zone), so two
chats that both applied it would write the same row, which the row-wise merge keeps once.

Undo: every receipt that can be taken back carries `undo` (the inverse action, what it acts
on, the value) and `guard` (a hash of what the action left). An `undo` action runs that
inverse only while the guard still holds; when something else has changed it since, it is
refused, and the person says so in a chat instead.

    python3 tools/app.py apply <dump dir> [--chat ID] [--claim] [--out DIR]
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_model  # noqa: E402
import page_db  # noqa: E402
import person  # noqa: E402

LEDGER = "applied.json"
CLAIM_S = 10 * 60

# name: (the item kinds it acts on, the writer, its undo). One table: the docstring above,
# the receipts and the tests all read this.
ACTIONS = {
    "job.dismiss": (("job",), "exclude.py add, basis person", "job.bring_back"),
    "job.bring_back": (("job", "filtered", "filtered_group"),
                       "exclude.py lift; filtered.py back (one posting, or a whole group)",
                       "job.dismiss"),
    "job.draft": (("job",), "queues work/draft~<key> (no repo write)", "work.stop"),
    "job.applied": (("job", "new_job"), "confirm.py applied --new (a job on the list, or one "
                                        "applied for elsewhere: company, role, link, day)",
                    "ready.not_applied"),
    "learned.retire": (("learned",), "learned.py retire: the rule stops applying, kept as "
                                     "history", "learned.unretire"),
    "learned.unretire": (("learned",), "the rule applying again", "learned.retire"),
    "tip.seen": (("tip",), "profile/tips.json: this tip shown, by tips.py's own rules", ""),
    "requests.withdrawn": (("due",), "state.py withdraw: the requests nobody accepted, "
                                     "withdrawn on LinkedIn", "requests.unwithdrawn"),
    "requests.unwithdrawn": (("due",), "the withdrawals taken off network_threads.csv",
                             "requests.withdrawn"),
    "search.set": (("search",), "profile/search.py through profile_set (tools/tweak.py "
                                "J6 to J12, kept): roles, places, pay, window, employers, sites",
                   "search.unset"),
    "search.unset": (("search",), "the setting as it was (tools/tweak.py undo)", "search.set"),
    "rule.lift": (("rule",), "exclude.py lift on the person's own rulings of that kind; or the "
                             "employer off do_not_target.json", "rule.restore"),
    "rule.restore": (("rule",), "the rulings back as they were", "rule.lift"),
    "brief.move": (("schedule",), "routines.py move: the brief's days and time ({days, time} "
                                  "or {cron}) in profile/routines.json, and the one "
                                  "update_trigger call kept for a chat (routines.py calls)",
                   "brief.move"),
    "brief.pause": (("schedule", "search"), "routines.py pause: a break until {until} (two "
                                            "weeks when none is given): HOLD until on live "
                                            "contacts, DO NOT CHASE until on applications, "
                                            "the brief rested and one brief on the day back "
                                            "kept for a chat", "brief.resume"),
    "brief.resume": (("schedule", "search"), "routines.py resume: every hold the break wrote "
                                             "put back, the brief on again", "brief.pause"),
    "brief.off": (("schedule",), "routines.py off: the brief alone turned off, its days and "
                                 "time kept, the update_trigger call kept for a chat",
                  "brief.on"),
    "brief.on": (("schedule",), "routines.py on: the brief on again on its days and time "
                                "(after a break in force, when it ends)", "brief.off"),
    "job.not_applied": (("job", "application"),
                        "confirm.py not-applied, on the job's own tracker row", "ready.applied"),
    "job.add": (("new_job",), "queues work/evaluate~<key>: the posting scored first (/apply "
                              "Step 1), kept by tools/added_jobs.py; applied already, confirmed "
                              "with its day", "work.stop"),
    "job.keep": (("job",), "documents/rounds/kept/jobs.json: on the list past later searches",
                 "job.unkeep"),
    "job.unkeep": (("job",), "documents/rounds/kept/jobs.json: off it again", "job.keep"),
    "person.call_booked": (("person", "message"), "state.py set --status call_booked, the "
                                                  "call's day as its next action",
                           "person.status"),
    "referral.agreed": (("person", "message", "referral"),
                        "state.py set --status referral_in_progress, the role named",
                        "person.status"),
    "referral.ended": (("person", "message", "referral"),
                       "state.py set: the referral over (hired, rejected, withdrawn), the hold "
                       "lifted", "person.status"),
    "due.snooze": (("due", "message"), "state.py set --due <day>, or \"DO NOT CHASE until "
                                       "<day>\" on the application's row (followups.py)",
                   "due.undo"),
    "ready.applied": (("tracker", "application"), "confirm.py applied", "ready.not_applied"),
    "ready.not_applied": (("tracker", "application"), "confirm.py not-applied", "ready.applied"),
    "ready.not_applying": (("tracker",), "confirm.py skip", "ready.reopen"),
    "ready.reopen": (("tracker",), "confirm.py reopen", "ready.not_applying"),
    "outcome.interview": (("application", "tracker", "interview"),
                          "confirm.record_outcome interview, and the booked stage line in "
                          "outcome.md (interview_pack.record_stage)", "outcome.undo"),
    "outcome.offer": (("application", "tracker", "interview"), "confirm.record_outcome offer; \"Offer "
                                                  "received\" ticked in outcome.md",
                      "outcome.undo"),
    "outcome.rejected": (("application", "tracker", "interview"), "confirm.record_outcome rejected; "
                                                     "outcome.md Status", "outcome.undo"),
    "outcome.withdrawn": (("application", "tracker", "interview"), "confirm.record_outcome withdrawn; "
                                                      "outcome.md Status", "outcome.undo"),
    "outcome.no_response": (("application", "tracker", "interview"), "confirm.record_outcome no_response; "
                                                        "outcome.md Status", "outcome.undo"),
    "outcome.undo": (("application", "tracker", "interview"),
                     "the tracker row and outcome.md as they were", ""),
    "process.register": (("person",), "interview_pack.py process: a call with someone on the "
                                      "hiring side made a hiring process (a tracker row, its "
                                      "folder and outcome.md, the call booked as its stage)",
                         ""),
    "ready.sent_to_contact": (("tracker", "application"),
                              "state.py message <contact> --attached <the resume>: the resume a "
                              "contact asked for, logged as sent to them with its file",
                              "msg.unsent"),
    "profile.pasted": (("message", "person"),
                       "reading.py read --source paste on the words pasted (then off the "
                       "page's database); a note waiting on that read queued for its rewrite "
                       "(network work, args.rewrite)", ""),
    "interview.rework": (("interview",), "interview_pack.add_rework: an answer to work on, "
                                        "kept under To rework in the living document",
                         "interview.unrework"),
    "interview.unrework": (("interview",), "that line taken off To rework", ""),
    "msg.sent": (("message", "person", "app_message"),
                 "state.py sent / nudge / message (text, subject, on, attached), or \"followed "
                 "up <day>\" on an application's row; the same words within 7 days refused",
                 "msg.unsent"),
    "msg.unsent": (("message", "person"), "state.py unsend", "msg.sent"),
    "msg.received": (("person", "message"), "state.py received, their words as they came; "
                                            "with draft, queues work/reply~<contact>",
                     "msg.unreceived"),
    "msg.unreceived": (("person", "message"), "their message taken off network_threads.csv",
                       "msg.received"),
    "msg.skip": (("message", "person"), "state.py drop", "msg.unskip"),
    "msg.unskip": (("message", "person"), "state.py reopen", "msg.skip"),
    "person.stop": (("person", "message"), "state.py set --status closed", "person.status"),
    "person.status": (("person", "message"), "state.py set", "person.status"),
    "consent.yes": (("work",), "the work item's answers (db only)", "consent.no"),
    "consent.no": (("work",), "the work item's answers (db only)", "consent.yes"),
    "setting.set": (("setting",), "person.json, tips.py, networking.py LINKEDIN_PLAN and "
                    "PROFILE_READS",
                    "setting.set"),
    "needs.answer": (("offer", "fact", "upgrade_ask"),
                     "learned.py decide; the profile at its mark; an update's question "
                     "(profile_upgrades.py --no, or a chat to set it up)", "needs.unanswer"),
    "needs.unanswer": (("fact",), "the profile: the mark put back", "needs.answer"),
    "setup.answer": (("setup_step",), "profile/setup_answers.json, read by /setup",
                     "setup.restore"),
    "setup.resume": (("setup_step",), "the resume into documents/cv/ (pasted) or its page "
                                      "asset noted to fetch; profile/setup_answers.json",
                     "setup.restore"),
    "setup.build_resume": (("setup_step",), "profile/setup_answers.json: build it with them",
                           "setup.restore"),
    "setup.skip": (("setup_step",), "profile/setup_answers.json: skipped, a default used",
                   "setup.restore"),
    "setup.restore": (("setup_step",), "profile/setup_answers.json: a step as it was",
                      "setup.restore"),
    "setup.done": (("outside",), "checked again (the job sites), or noted as done", ""),
    "setup.make_copy": (("outside",), "gh repo create <name> --template the app --private", ""),
    "app.update_now": (("update",), "queues work/update~<sha> (db only)", "work.stop"),
    "upgrade.undo": (("upgrade",), "git revert of that improvement's own commit",
                     "upgrade.undo"),
    "due.done": (("due",), "state.py set (a contact's dated next action cleared), or "
                           "\"followed up <day>\" on the application's row", "due.undo"),
    "due.undo": (("due",), "the next action and its day put back, or the note taken off",
                 "due.done"),
    "tweak.undo": (("tracker", "message"), "queues work/tweak~<item>~undo-<key>: the chat "
                                            "puts the version before back (tools/tweak.py undo)",
                   "work.stop"),
    "tweak.offer": (("tweak_offer",), "tools/tweak.py answer_offer: a usual kept (its "
                                     "setting and a learned rule), a button added, or Not now "
                                     "kept for 30 days", "tweak.offer_undo"),
    "tweak.offer_undo": (("tweak_offer",), "tools/tweak.py undo_offer", ""),
    "hint.seen": (("hint",), "profile/tips.json page_hints: the one-time hint not shown again",
                  ""),
    "suggest.dismiss": (("suggest",), "profile/app.json suggest_no: never offered again",
                        "suggest.undismiss"),
    "suggest.undismiss": (("suggest",), "profile/app.json suggest_no: may be offered again",
                          "suggest.dismiss"),
    "export.requested": (("linkedin",), "export.py requested: the day the LinkedIn download "
                                        "was asked for", "export.unrequested"),
    "export.unrequested": (("linkedin",), "the day it was asked for put back", "export.requested"),
    "export.take": (("linkedin",), "export.py take on the files the page added (fetched by the "
                                   "chat into --assets): saved, history imported, counted",
                    ""),
    "reader.checked": (("linkedin",), "documents/network/page_reader.json: the page read a "
                                      "LinkedIn page, or could not", ""),
    "reading.done": (("page_read",), "reading.py read --source browser, as a computer chat "
                                     "logs a reading; off the page's queue", ""),
    "work.stop": (("work",), "stop_asked on the work item (db only)", "work.resume"),
    "work.resume": (("work",), "stop_asked cleared (db only)", "work.stop"),
    "undo": ((), "the inverse its receipt recorded", ""),
}




class Refused(Exception):
    """The action cannot apply: its receipt says why, in plain words."""


# ------------------------------------------------------------------ the item index



def _lock_born(lock: str) -> float:
    """When a lock was taken, as its taker wrote it: by Python's own clock, so a lock is
    judged by the clock that judges it, never the file system's (a lock read as 400 days old
    with the date moved on was broken under a live writer, 2026-10-29)."""
    try:
        with open(lock, encoding="ascii") as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return os.path.getmtime(lock)

def _sections_for(item_id: str) -> tuple:
    if item_id.startswith("due-"):
        return ("due",)
    if item_id.startswith("filtered~"):
        return ("jobs",)
    if item_id.startswith("sg-"):
        return ("jobs", "ready", "messages", "interviews", "people")
    if item_id.startswith("setup-"):
        return ("setup",)
    if item_id == "update-now" or item_id.startswith("upg-"):
        return ("updates",)
    if item_id.startswith("q-"):
        return ("needs_you",)
    if item_id.startswith("app-"):
        return ("ready", "applications", "needs_you")
    if item_id.startswith("msg-"):
        return ("messages",)
    if item_id.startswith("int-"):
        return ("interviews",)
    if item_id.startswith("ref-"):
        return ("referrals",)
    if item_id.startswith(("linkedin-", "read-")):
        return ("linkedin",)
    if item_id.startswith("learned-"):
        return ("learned",)
    if item_id.startswith("tip-"):
        return ("help",)
    if item_id.startswith(("rule-", "search-")):
        return ("search",)
    if item_id == "schedule":
        return ("schedule",)
    if item_id.startswith("resume-"):
        return ("resume",)
    if item_id.startswith("setting-"):
        return ("settings",)
    if re.search(r"-f?\d+$", item_id):
        return ("jobs", "people")
    return ("people", "jobs")


class Index:
    """The targets of the items on the page now, one section at a time, rebuilt after a write."""

    def __init__(self, today: dt.date, now: dt.datetime, shown: dict | None = None):
        self.today, self.now, self.shown = today, now, shown
        self.cache: dict = {}

    def section(self, name: str) -> dict:
        if name not in self.cache:
            _, self.cache[name] = app_model.build(self.today, self.now, only={name})
        return self.cache[name]

    def find(self, item_id: str, kinds=(), rev: str = "") -> dict | None:
        """The item's target. One id on two sections (an application is its draft's id on
        Drafts and on Applied) is the one of a kind the action takes, the one whose rev the
        person saw first."""
        hits = []
        for name in _sections_for(item_id):
            got = self.section(name).get(item_id)
            if got:
                hits.append(dict(got, id=item_id))
        fit = [h for h in hits if not kinds or h.get("kind") in kinds] or hits
        return next((h for h in fit if rev and h.get("rev") == rev), fit[0] if fit else None)


    def changed(self) -> None:
        self.cache.clear()
        person.reset()
        import docpaths
        docpaths.forget_abbreviations()


# ------------------------------------------------------------------ guards: what an action left


def _tracker_row(target: dict):
    import csv_store
    path = person.state("job_search_tracker.csv")
    rows = csv_store.read_rows(path) if os.path.exists(path) else []
    for r in rows:
        if (r.get("date") or "", r.get("company") or "", r.get("role") or "") == (
                target.get("date") or "", target.get("company") or "", target.get("role") or ""):
            return rows, r
    return rows, None


def _contact(cid: str):
    from network import state
    contacts = state.load_contacts(person.state("network_contacts.csv"))
    threads = state.load_threads(person.state("network_threads.csv"))
    row = next((c for c in contacts if str(c.get("contact_id") or "").strip() == cid), None)
    return row, [t for t in threads if str(t.get("contact_id") or "").strip() == cid]


def guard(target: dict) -> str:
    """A hash of the repo state an action on `target` acts on."""
    kind = target.get("kind")
    if kind in ("tracker", "application"):
        _, row = _tracker_row(target)
        return app_model.rev_of(sorted((row or {}).items()))
    if kind == "interview":
        import docpaths
        import interview_pack
        _, row = _tracker_row(target)
        living = os.path.join(docpaths.app_folder(target.get("company"), target.get("role")),
                              interview_pack.LIVING)
        return app_model.rev_of(sorted((row or {}).items()),
                                interview_pack.rework_lines(app_model.read_text(living)))
    if kind in ("job", "filtered") and target.get("many"):
        return app_model.rev_of([guard(dict(one, kind="job")) for one in target["many"]])
    if kind in ("job", "filtered"):
        from lookup_score import norm
        import exclude
        seen = exclude.load_seen(person.state("job_scraper", "seen_jobs.json")).get("seen") or {}
        want = norm(target.get("url") or "")
        entry = next((e for k, e in seen.items() if isinstance(e, dict)
                      and (norm(e.get("url") or k) == want)), None)
        return app_model.rev_of(entry)
    if kind in ("message", "person", "referral"):
        row, msgs = _contact(target.get("contact") or "")
        return app_model.rev_of(sorted((row or {}).items()), [sorted(m.items()) for m in msgs])
    if kind == "setting":
        return app_model.rev_of(app_model.setting_values().get(target.get("key")))
    if kind == "fact":
        return app_model.rev_of(app_model.read_text(_fact_path(target)))
    if kind == "setup_step":
        import app_setup
        return app_model.rev_of(app_setup.answers().get(target.get("step")))
    if kind == "suggest":
        import app_alerts
        return app_model.rev_of(app_alerts.dismissed().get(target.get("id")))
    if kind == "due":
        if target.get("half") == "contact":
            row, msgs = _contact(target.get("contact") or "")
            return app_model.rev_of(sorted((row or {}).items()), [sorted(m.items()) for m in msgs])
        _, row = _sent_row(target)
        return app_model.rev_of(sorted((row or {}).items()))
    return ""


def _sent_row(target: dict):
    """(every tracker row, the application a follow-up is for): the newest sent row with
    that employer and role."""
    import csv_store
    import throttle
    path = person.state("job_search_tracker.csv")
    rows = csv_store.read_rows(path) if os.path.exists(path) else []
    hits = [r for r in rows if (r.get("company") or "") == target.get("company")
            and (r.get("role") or "role not recorded") == target.get("role")
            and str(r.get("status") or "").strip().lower() not in throttle.UNSENT]
    return rows, (max(hits, key=lambda r: throttle.applied_on(r) or r.get("date") or "")
                  if hits else None)


# ------------------------------------------------------------------ one action


# The one shape of `value` is an object: {"on": "2026-10-21"}, {"why": "pay"}, {"text": ...}
# (CONTRACT 6.13). A page that sends a bare string or number means the field below, so a
# date typed for "When did you apply?" or a reason picked for Set aside is never lost
# (FUNCTIONS_SPEC 4.1). A bare ISO day is "on" wherever the action takes a day.
BARE = {
    "job.dismiss": "why", "job.bring_back": "why", "job.applied": "on", "job.keep": "why",
    "ready.applied": "on", "msg.sent": "text", "msg.received": "text", "msg.skip": "why",
    "msg.unskip": "why", "person.stop": "why", "person.status": "status",
    "person.call_booked": "on", "setting.set": "value", "needs.answer": "value",
    "tweak.offer": "value", "tweak.undo": "key", "hint.seen": "hint", "consent.yes": "skill",
    "consent.no": "skill", "setup.answer": "text", "setup.make_copy": "name",
    "outcome.interview": "stage", "outcome.rejected": "why", "outcome.offer": "on",
    "outcome.withdrawn": "why", "outcome.no_response": "why", "referral.agreed": "role",
    "referral.ended": "why", "due.snooze": "until", "reading.done": "text",
    "brief.pause": "until", "tip.seen": "area", "job.add": "text", "brief.move": "time",
    "interview.rework": "question", "profile.pasted": "text", "ready.sent_to_contact": "text",
}
DATED = {"job.applied", "ready.applied", "msg.sent", "msg.received", "outcome.interview",
         "outcome.rejected", "outcome.offer", "outcome.withdrawn", "outcome.no_response",
         "person.call_booked", "due.snooze", "referral.agreed", "brief.pause",
         "ready.sent_to_contact"}
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def value_of(act: dict) -> dict:
    """The action's value as an object, whatever shape the page sent it in. A setup answer
    is its fields: `{step, answers: {...}}`, as the page's setup card sends it, is read as
    the fields inside `answers` (CONTRACT 6.13)."""
    value = act.get("value")
    if isinstance(value, dict):
        inner = value.get("answers")
        if str(act.get("action") or "").startswith("setup.") and isinstance(inner, dict):
            return dict({k: v for k, v in value.items() if k not in ("answers", "step")},
                        **inner)
        return value
    if value in (None, "") or isinstance(value, (list, bool)):
        return {"value": value} if isinstance(value, (list, bool)) else {}
    name = str(act.get("action") or "")
    out = {"value": value}
    text = str(value).strip()
    if name in DATED and _DAY.match(text):
        out["until" if name in ("due.snooze", "brief.pause") else "on"] = text
    elif BARE.get(name):
        out[BARE[name]] = value
    return out


class Run:
    """One action being applied: its document, its target, its time, and the batch it adds to."""

    def __init__(self, aid, act, target, db, writes, chat, zone, now, version=None):
        self.aid, self.act, self.target, self.db, self.w, self.chat = (
            aid, act, target, db, writes, chat)
        self.version = version
        self.at = app_model.parse_time(act.get("at")) or now
        self.day = app_model.local_day(self.at, zone)
        try:
            import zoneinfo
            self.local = self.at.astimezone(zoneinfo.ZoneInfo(zone)).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            self.local = self.at.replace(tzinfo=None)
        self.value = value_of(act)

    def words(self, key="why") -> str:
        return " ".join(str(self.value.get(key) or "").split())

    def on(self, key="on") -> str:
        """A day the person gave ("When did you apply?", "sent on"): ISO, never after today
        in their zone, or today when none was given."""
        given = self.words(key)
        if not given:
            return self.day.isoformat()
        try:
            day = dt.date.fromisoformat(given[:10])
        except ValueError:
            raise Refused(f"{given} is not a day: give it as 2026-10-21.") from None
        if day > self.day:
            raise Refused("That day has not come yet.")
        return day.isoformat()


def _cli(module, argv) -> tuple[int, str]:
    """A tool's own command line, in this process, with what it printed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            code = module.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return int(code or 0), buf.getvalue()


def _said(out: str) -> str:
    """The reason a tool printed for not doing it, without its command names."""
    for line in out.splitlines():
        line = line.strip()
        m = re.search(r"not (?:recorded|changed|dropped|reopened|reopen\w*): (.*)", line)
        if m:
            return m.group(1)
        if line.startswith(("set: ", "unsend: ")) and "not changed" not in line:
            return line.split(": ", 1)[1]
    return out.strip().splitlines()[-1] if out.strip() else "it did not apply"


def _text_file(text: str) -> str:
    fd, path = tempfile.mkstemp(prefix="ljs_page_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


# ---- jobs


def _job_dismiss(r: Run) -> dict:
    import exclude
    t = r.target
    if t.get("many"):
        # The undo of a group brought back: each posting set aside again, by the person.
        for one in t["many"]:
            if one.get("url"):
                exclude.add(one["url"], "taken back after bringing the group back",
                            title=one.get("title", ""), company=one.get("company", ""),
                            basis="person", today=r.day.isoformat(),
                            path=person.state("job_scraper", "seen_jobs.json"))
        return {"note": f"Set aside again: {len(t['many'])} postings.",
                "undo": {"action": "job.bring_back", "target": dict(t)}}
    if not t.get("url"):
        raise Refused("This posting has no link to rule it out by.")
    why = r.words()
    declined = ""
    if r.value.get("scope") == "employer" and t.get("company"):
        # "No more roles from them": the employer joins the ones turned down by name
        # (profile/search.py BAR_DECLINED, which bar.py and every round read), and Bring
        # back takes it off again (the maintainer, 2026-10-26).
        declined = _decline_employer(str(t["company"]), why or "no more roles from them",
                                     r.day.isoformat())
    exclude.add(t["url"], why or "not for me (said on the page)", title=t.get("title", ""),
                company=t.get("company", ""), basis="person", today=r.day.isoformat(),
                location=t.get("place", ""), path=person.state("job_scraper", "seen_jobs.json"))
    # A reason about the posting itself (it closed) or none in particular is no preference
    # to learn; pay, place, field and employer are.
    rule = _dismiss_rule(why, t)
    if rule:
        try:
            import learned
            learned.record("jobs", why, rule, applied_to=["job_scraper/seen_jobs.json"],
                           today=r.day.isoformat(), answers=False)
        except SystemExit:
            pass                        # no profile to learn in: the ruling still stands
    note = (f"No more roles from {declined}." if declined
            else f"{t.get('title')} at {t.get('company')} will not be shown again.")
    return {"note": note,
            "undo": {"action": "job.bring_back", "target": dict(t, kind="job", declined=declined)},
            "why": why}


def _dismiss_rule(why: str, t: dict) -> str:
    """What a reason in the job bin teaches the next ranking (/rank reads `learned.py brief
    jobs` before it scores): a rule about roles like this one, never only this posting. A
    closed posting or "not this role" teaches nothing."""
    w = (why or "").strip().lower()
    what = f"{t.get('title')} at {t.get('company')} ({t.get('url')})"
    place = str(t.get("place") or "").strip()
    pay = str(t.get("pay") or "").strip()
    if w == "pay":
        return (f"Rank lower roles paying like {what}" + (f", {pay}" if pay else "")
                + ": the pay was not enough for them.")
    if w == "place":
        return (f"Rank lower roles in the place of {what}" + (f" ({place})" if place else "")
                + ": the place did not suit them.")
    if w == "field":
        return (f"Not their field: rank lower roles like {what}, the same kind of work in "
                "another title too.")
    if w in ("", "closed", "not this role", "role", "employer"):
        return ""
    return f"Not this posting: {what}. Their words: {why}"


def _job_bring_back(r: Run) -> dict:
    import exclude
    t = r.target
    if t.get("declined"):
        import profile_set
        try:
            have = dict(profile_set.get("search.py", "BAR_DECLINED") or {})
        except Exception:  # noqa: BLE001
            have = {}
        if have.pop(str(t["declined"]), None) is not None:
            profile_set.set_line("search.py", "BAR_DECLINED", have)
    why = r.words() or "brought back on the page"
    if t["kind"] == "filtered_group" or t.get("many"):
        import filtered
        picks = [str(n) for n in t.get("ns") or []] or [one["url"] for one in t["many"]]
        try:
            got = filtered.back(t["round"], picks, why=r.words(), today=r.day.isoformat(),
                                seen_path=person.state("job_scraper", "seen_jobs.json"))
        except SystemExit as e:
            raise Refused(str(e).replace("filtered: ", "")) from None
        many = [{"url": e.get("url") or "", "title": e.get("title") or "",
                 "company": e.get("company") or "", "rank": rank} for e, rank in got]
        new = {"kind": "job", "round": t["round"], "many": many, "ns": t.get("ns") or [],
               "reason": t.get("reason") or ""}
        return {"note": f"Back on the shortlist: {len(many)} postings left out for "
                        f"{t.get('reason') or 'that reason'}.",
                "undo": {"action": "job.dismiss", "target": new}, "target_after": new}
    if t["kind"] == "filtered":
        import filtered
        pick = t.get("url") or str(t.get("n"))
        try:
            got = filtered.back(t["round"], [pick], why=r.words(), today=r.day.isoformat(),
                                seen_path=person.state("job_scraper", "seen_jobs.json"))
        except SystemExit as e:
            raise Refused(str(e).replace("filtered: ", "")) from None
        rank = got[0][1] if got else None
        new = dict(t, kind="job", rank=rank, id=f"{t['round']}-{rank}")
        return {"note": f"{t.get('title')} at {t.get('company')} is back on the shortlist.",
                "undo": {"action": "job.dismiss", "target": new}, "target_after": new}
    lifted = exclude.lift(urls=[t["url"]], why=why, today=r.day.isoformat(),
                          path=person.state("job_scraper", "seen_jobs.json"))
    if not lifted:
        raise Refused("It was not ruled out, so there is nothing to bring back.")
    try:
        import learned
        for n, e in enumerate(learned.load(), 1):
            if e.get("status", "active") == "active" and t["url"] in str(e.get("rule") or ""):
                learned.retire(n)
    except SystemExit:
        pass
    return {"note": f"{t.get('title')} at {t.get('company')} is back.",
            "undo": {"action": "job.dismiss", "target": dict(t)}}


def _job_draft(r: Run) -> dict:
    t = r.target
    wid = app_model.draft_work_id(t.get("url") or "", t.get("company"), t.get("title"))
    have = (r.db.get("work") or {}).get(wid)
    if have and str(have["data"].get("status") or "") not in page_db.FINISHED:
        return {"note": "Already on its way.", "undo": None}
    noun = str(person.get("documents.noun", "resume"))
    answers = r.value.get("answers") if isinstance(r.value.get("answers"), dict) else {}
    doc = {"kind": "draft", "title": f"{noun[:1].upper() + noun[1:]} and letter: "
                                     f"{t.get('company')}, {t.get('title')}",
           "to": str(r.value.get("to") or "cloud"),
           "args": {"round": t.get("round"), "rank": t.get("rank"), "url": t.get("url"),
                    "company": t.get("company"), "title": t.get("title")},
           "answers": answers, "asked_at": app_model.stamp(r.at),
           "asked_from": {"tab": r.act.get("tab") or ""}, "priority": 0, "status": "queued",
           "stages": [{"name": s["name"], "est_s": s["est_s"]}
                      for s in page_db.progress("draft")["stages"]], "stage": 0}
    r.w.add("set", "work", wid, doc, if_version=have["version"] if have else None)
    return {"note": "Queued: Claude drafts it next.",
            "undo": {"action": "work.stop", "target": {"kind": "work", "id": wid}}}


def _job_applied(r: Run) -> dict:
    import confirm
    t = r.target
    if t.get("kind") == "new_job":
        # Applied for elsewhere, outside the app: the row /apply Step 1c writes.
        t = {"company": " ".join(str(r.value.get("company") or "").split())[:120],
             "title": " ".join(str(r.value.get("role") or r.value.get("title") or "")
                               .split())[:160],
             "url": str(r.value.get("url") or "").strip()[:500]}
        if not t["company"] or not t["title"]:
            raise Refused("Say the employer and the role.")
    on = r.on()
    try:
        row = confirm.add_applied(t.get("company"), t.get("title"), t.get("url", ""), on=on,
                                  source="page", path=person.state("job_search_tracker.csv"),
                                  today=r.day, now=r.local)
    except confirm.Refused as e:
        raise Refused(str(e)) from None
    new = {"kind": "tracker", "date": row["date"], "company": row["company"], "role": row["role"]}
    return {"note": f"Recorded: you applied to {t.get('company')} on {on}.",
            "undo": {"action": "ready.not_applied", "target": new}, "target_after": new}


def _job_not_applied(r: Run) -> dict:
    """"Not applied after all" on a job marked applied: its own tracker row back among the
    drafts (confirm.py not-applied), the same writer as on a draft."""
    t = r.target
    ctx = app_model.Ctx(r.day, r.at)
    row = app_model.tracker_match(ctx, t.get("company"), t.get("title"))
    if row is None:
        raise Refused("It is not marked as applied.")
    r.target = {"kind": "tracker", "date": row.get("date") or "", "company": row.get("company") or "",
                "role": row.get("role") or ""}
    before = _confirm(r, "not-applied")
    return {"note": "Marked as not applied.",
            "undo": {"action": "ready.applied", "target": dict(r.target),
                     "value": {"on": before.get("applied_on") or ""}},
            "target_after": dict(r.target)}


def _job_add(r: Run) -> dict:
    """"Add a job": one link or the posting's text, scored by a chat before anything else
    (the evaluate work), and, if they applied already, recorded as applied on their day."""
    url = str(r.value.get("url") or "").strip()
    text = str(r.value.get("text") or "").strip()
    if not url and re.match(r"^https?://\S+$", text):
        url, text = text, ""
    if not url and len(text) < 80:
        raise Refused("Paste the job's link, or the whole posting.")
    applied = r.words("applied_on") or r.words("on")
    if applied:
        try:
            if dt.date.fromisoformat(applied[:10]) > r.day:
                raise Refused("That day has not come yet.")
        except ValueError:
            raise Refused(f"{applied} is not a day.") from None
    key = app_model.rev_of(url or text[:2000])[:10]
    wid = f"evaluate~{key}"
    have = (r.db.get("work") or {}).get(wid)
    if have and str(have["data"].get("status") or "") not in page_db.FINISHED:
        return {"note": "Already on its way.", "undo": None}
    r.w.add("set", "work", wid, {
        "kind": "evaluate", "title": "Scoring the job you added", "to": "either",
        "args": {"url": url, "text": text[:60000], "applied_on": applied[:10] if applied else "",
                 # Who sent it (their referral route) and whether to draft once it is scored.
                 "contact": str(r.value.get("contact") or "").strip(),
                 # Someone not in the contact book, by name: kept in the role's notes.
                 "from_name": str(r.value.get("from_name") or "").strip()[:80],
                 "draft": bool(r.value.get("draft")) and not applied},
        "asked_at": app_model.stamp(r.at), "asked_from": {"tab": r.act.get("tab") or ""},
        "priority": 0, "status": "queued", "stage": 0,
        "stages": [{"name": x["name"], "est_s": x["est_s"]}
                   for x in page_db.progress("evaluate")["stages"]]},
        if_version=have["version"] if have else None)
    return {"note": "Claude scores it next" + (" and records it as applied." if applied
                                              else ", then drafts your resume and cover letter."
                                              if r.value.get("draft")
                                              else ", and it goes at the top of your jobs."),
            "undo": {"action": "work.stop", "target": {"kind": "work", "id": wid}}}


def _kept_path() -> str:
    return person.state(*app_model.KEPT_FILE)


def _job_keep(r: Run, keep: bool = True) -> dict:
    t = r.target
    if not t.get("url"):
        raise Refused("This posting has no link to keep it by.")
    got = app_model.kept_jobs()
    if keep:
        got[t["url"]] = {"round": t.get("round"), "rank": t.get("rank"),
                         "title": t.get("title", ""), "company": t.get("company", ""),
                         "kept_on": r.day.isoformat(), "why": r.words()}
    elif not got.pop(t["url"], None):
        raise Refused("It was not kept.")
    path = _kept_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    return {"note": (f"Kept: {t.get('title')} stays on your list after the next search."
                     if keep else f"{t.get('title')} is no longer kept."),
            "undo": {"action": "job.unkeep" if keep else "job.keep", "target": dict(t)}}


# ---- the tracker


def _confirm(r: Run, word: str, on: str = "") -> dict:
    import confirm
    import csv_store
    import throttle
    path = person.state("job_search_tracker.csv")
    rows, row = _tracker_row(r.target)
    if row is None:
        raise Refused("That application is no longer in your tracker.")
    if not confirm.takes(word, row):
        raise Refused(f"It is marked {row.get('status') or 'blank'} now, so that does not apply.")
    before = {"applied_on": row.get("applied_on") or throttle.applied_on(row)}
    confirm.apply(word, [row], r.day, on=on, source="page", now=r.local)
    csv_store.write_rows(path, rows, list(dict.fromkeys(
        csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
    return before


def _ready_applied(r: Run) -> dict:
    on = r.on()
    _confirm(r, "applied", on=on)
    note = f"Marked as applied on {on}."
    # "I applied, naming X": X's referral is now in flight there, so nothing else at that
    # employer goes in cold and the follow-up is a thank-you, not a nudge.
    cid = str(r.value.get("referrer") or "").strip()
    if cid and _contact(cid)[0] is not None:
        role = str(r.target.get("role") or "")
        _cli(_state(), ["set", cid, "--status", "referral_in_progress", "--next-action",
                        f"Referral for {role}: wait to hear, then thank them" if role else
                        "Referral in progress: wait to hear, then thank them", "--due", "",
                        "--note", f"applied naming them as referrer{' for ' + role if role else ''}"
                        ", said on the page", "--today", r.day.isoformat()])
        note += f" {_first(cid)} is named as your referrer."
    return {"note": note, "undo": {"action": "ready.not_applied", "target": r.target}}


def _ready_not_applied(r: Run) -> dict:
    before = _confirm(r, "not-applied")
    return {"note": "Marked as not sent yet.",
            "undo": {"action": "ready.applied", "target": r.target,
                     "value": {"on": before["applied_on"]} if before["applied_on"] else {}}}


def _ready_not_applying(r: Run) -> dict:
    _confirm(r, "skip")
    return {"note": "Set aside: you are not sending this one.",
            "undo": {"action": "ready.reopen", "target": r.target}}


def _ready_reopen(r: Run) -> dict:
    _confirm(r, "reopen")
    return {"note": "Back among your drafts.",
            "undo": {"action": "ready.not_applying", "target": r.target}}


# ---- what happened after an application went (the writers /outcome uses)


def _stage_day(r: Run) -> str:
    """The day an interview stage is booked for: any day, since it is usually to come."""
    given = r.words("on") or r.words("date")
    if not given:
        raise Refused("Which day is it? Give it as 2026-10-28.")
    try:
        return dt.date.fromisoformat(given[:10]).isoformat()
    except ValueError:
        raise Refused(f"{given} is not a day: give it as 2026-10-28.") from None


def _outcome(r: Run, status: str) -> dict:
    import confirm
    import csv_store
    import interview_pack
    import outreach
    import throttle
    import what_works
    rows, row = _tracker_row(r.target)
    if row is None:
        raise Refused("That application is no longer in your tracker.")
    company, role = row.get("company") or "", row.get("role") or ""
    folder = outreach.app_folder(company, role)
    md = os.path.join(folder, "outcome.md")
    before = {"row": {k: row.get(k) or "" for k in ("status", "notes", "confirmed_by",
                                                    "confirmed_at")},
              "md": app_model.read_text(md) if os.path.isfile(md) else None}
    try:
        if status == "interview":
            day = _stage_day(r)
            stage = " ".join(str(r.value.get("stage") or r.target.get("stage") or
                                 "Interview").split())[:60]
            clock = what_works.clock(r.words("time"))
            when = f" at {clock}" if clock else ""
            changed = confirm.record_outcome(row, "interview", r.day,
                                             note=f"{stage} booked for {day}{when}",
                                             source="page", now=r.local)
            interview_pack.record_stage(folder, company, role, stage, day, r.words("with"),
                                        today=r.day.isoformat(), time=clock)
            said = f"Booked: {stage} with {company} on {day}{when}."
        else:
            day = r.on()
            changed = confirm.record_outcome(row, status, r.day, note=r.words("why"),
                                             source="page", now=r.local)
            if changed:
                interview_pack.record_result(folder, company, role, status, day,
                                             today=r.day.isoformat())
            said = {"offer": f"An offer from {company}: recorded.",
                    "rejected": f"Recorded: {company} said no. The follow-ups there stop.",
                    "withdrawn": f"Recorded: you withdrew from {company}.",
                    "no_response": f"Recorded: no word from {company}. The follow-ups stop."
                    }[status]
    except confirm.Refused as e:
        raise Refused(str(e)) from None
    md_now = app_model.read_text(md) if os.path.isfile(md) else None
    if not changed and md_now == before["md"]:
        return {"note": "Already recorded.", "undo": None}
    if status == "interview" and not changed:
        # The row was at interview already: a later stage, dated on the row as the first was.
        confirm.add_note(row, f"{r.day.isoformat()}: {stage} booked for {day}{when} (page)")
    path = person.state("job_search_tracker.csv")
    csv_store.write_rows(path, rows, list(dict.fromkeys(
        csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
    return {"note": said, "undo": {"action": "outcome.undo", "target": dict(r.target),
                                   "value": before}}


def _rework(r: Run) -> dict:
    """"Keep this to work on" after a practice answer: the question and what to sharpen,
    under To rework in the process's living document (interview_pack.py rework), once."""
    import interview_pack
    t = r.target
    question = r.words("question")[:300]
    note = r.words("note")[:500]
    if not question:
        raise Refused("Which question: none was given.")
    if not note:
        raise Refused("What to work on: say it in a few words.")
    where = r.words("where") if r.words("where") in ("mock", "the real interview") else "mock"
    stage = r.words("stage") or t.get("stage") or "the next stage"
    line = interview_pack.rework_entry(question, note, r.day.isoformat(), where)
    living = os.path.join(_app_folder(t), interview_pack.LIVING)
    if line in interview_pack.rework_lines(app_model.read_text(living)):
        return {"note": "Already kept to work on.", "undo": None}
    try:
        interview_pack.add_rework(t.get("company"), t.get("role"), stage, question, note,
                                  r.day.isoformat(), where)
    except LookupError:
        raise Refused("There is no prep for this interview yet: Prepare me makes it, then "
                      "answers can be kept to work on.") from None
    return {"note": "Kept to work on: it is under To rework in your prep.",
            "undo": {"action": "interview.unrework", "target": dict(t),
                     "value": {"line": line, "stage": stage}}}


def _unrework(r: Run) -> dict:
    import interview_pack
    t = r.target
    line = str(r.value.get("line") or "")
    gone = interview_pack.remove_rework(t.get("company"), t.get("role"),
                                        r.words("stage") or t.get("stage") or "", line)
    return {"note": "Taken off To rework." if gone else "It was not on To rework.",
            "undo": None}


def _app_folder(t: dict) -> str:
    import docpaths
    return docpaths.app_folder(t.get("company"), t.get("role"))


def _outcome_undo(r: Run) -> dict:
    import csv_store
    import outreach
    import throttle
    rows, row = _tracker_row(r.target)
    if row is None:
        raise Refused("That application is no longer in your tracker.")
    for k, v in (r.value.get("row") or {}).items():
        row[k] = v
    path = person.state("job_search_tracker.csv")
    csv_store.write_rows(path, rows, list(dict.fromkeys(
        csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
    md = os.path.join(outreach.app_folder(row.get("company") or "", row.get("role") or ""),
                      "outcome.md")
    was = r.value.get("md")
    if was is None:
        if os.path.isfile(md):
            os.remove(md)
    else:
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(was)
    return {"note": "Taken back: it is as it was.", "undo": None}


# ---- messages and people


_STATE_CHANNEL = {"linkedin_note": "connection", "inmail": "inmail", "email": "email",
                  "linkedin_message": "message"}


def _state():
    from network import state
    return state


def _first(cid: str) -> str:
    row, _ = _contact(cid)
    return app_model.first_name((row or {}).get("name")) or "them"


SAME_SEND_DAYS = 7


@contextlib.contextmanager
def _thread_lock(wait: float = 30.0):
    """One writer of the message log at a time on this computer: two chats, or one chat
    applying a double tap from two dumps, check for the same send and write it in turn, so
    the second finds the first's row (FUNCTIONS_SPEC 1.5 item 3)."""
    import hashlib
    import time
    folder = os.path.join(tempfile.gettempdir(), "ljs-thread-locks")
    os.makedirs(folder, exist_ok=True)
    name = hashlib.sha1(os.path.abspath(person.state("network_threads.csv")).encode()
                        ).hexdigest()
    lock = os.path.join(folder, name + ".lock")
    start = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, repr(time.time()).encode("ascii"))
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - _lock_born(lock) > 120:      # a writer that died
                    os.remove(lock)
                    continue
            except OSError:
                continue
            if time.time() - start > wait:
                raise Refused("Another chat is writing your messages right now: try again "
                              "in a minute.") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _already_sent(cid: str, text: str, day: dt.date) -> str:
    """The day the same words to this person are already logged, within SAME_SEND_DAYS of
    `day`, or "": logged in a chat on Monday and tapped on the page on Tuesday is one send."""
    state = _state()
    _, msgs = _contact(cid)
    want = " ".join(str(text or "").lower().split())
    for m in msgs:
        if state.direction(m) != "out":
            continue
        got = " ".join(str(m.get("full_text") or "").lower().split())
        when = app_model.as_day(m.get("date"))
        if got and got == want and when and abs((day - when).days) <= SAME_SEND_DAYS:
            return when.isoformat()
    return ""


def _weekday(day: str) -> str:
    d = app_model.as_day(day)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}" if d else day


_SENT_CHANNEL = {"linkedin_note": "connection", "inmail": "inmail", "email": "email",
                 "linkedin_message": "message"}


def _msg_sent(r: Run) -> dict:
    """"I sent it": the words that went (the draft, or the person's own edit pasted back),
    its subject, the day it went and any file with it, through state.py, which learns an
    edit from the words and dates the next follow-up. One send is one row: the same words
    to the same person already logged within a week are refused with the day they went."""
    state = _state()
    t = r.target
    if t.get("half") == "application":
        return _app_followup_sent(r)
    cid = t.get("contact") or ""
    kind = str(r.value.get("kind") or t.get("msg_kind") or "first_note")
    channel = str(r.value.get("channel") or t.get("channel") or "linkedin_note")
    text = str(r.value.get("text") or t.get("text") or "").strip()
    sub_in, text = state.split_subject(text)
    text = text.strip()
    subject = " ".join(str(r.value.get("subject") or sub_in or t.get("subject") or "").split())
    outside = bool(r.value.get("outside"))
    if not text and outside:
        # "Yes, it went" for a note sent outside the app with no draft on file: the send is
        # kept so nobody is written to twice; its words are not known.
        text = "[sent outside the app; the words were not kept]"
    if not text:
        raise Refused("The words that went are needed, so they can be kept with the thread.")
    day = r.on()
    attached = r.words("attached")
    path = _text_file(text)
    try:
        with _thread_lock():
            went = _already_sent(cid, text, app_model.as_day(day))
            if went:
                raise Refused(f"Already logged on {_weekday(went)}.")
            _, msgs = _contact(cid)
            logged = [m for m in msgs if state.direction(m)]
            if not logged:
                argv = ["sent", cid, "--text-file", path, "--date", day, "--today",
                        r.day.isoformat(), "--channel", _SENT_CHANNEL.get(channel, "connection")]
                if outside:
                    argv.append("--outside")
            else:
                argv = ["nudge" if kind == "follow_up" else "message", cid, "--text-file", path,
                        "--date", day, "--today", r.day.isoformat()]
                if channel in ("email", "inmail"):
                    argv += ["--channel", channel]
            if subject:
                argv += ["--subject", subject]
            if attached:
                argv += ["--attached", attached]
            code, out = _cli(state, argv)
    finally:
        os.remove(path)
    if code:
        raise Refused(_said(out))
    who = _first(cid)
    row, _ = _contact(cid)
    nxt = app_model.as_day((row or {}).get("next_action_due"))
    then = (f" Next: {str((row or {}).get('next_action') or '').strip()[:80]}, "
            f"{_weekday(nxt.isoformat())}." if nxt and nxt > r.day else "")
    return {"note": f"Logged as sent to {who} on {day}.{then}",
            "undo": {"action": "msg.unsent", "target": {"kind": "message", "contact": cid},
                     "value": {"kind": kind, "channel": channel, "text": text,
                               "subject": subject}}}


def _ready_sent_to_contact(r: Run) -> dict:
    """"I sent it to Tamsin" on a resume a contact asked for: the message logged to them with
    the resume's file (state.py message --attached), as "I sent it" logs any message, so
    RECONCILE and the interview pack know what they hold."""
    cid = r.words("contact")
    if not cid or _contact(cid)[0] is None:
        raise Refused("Who was it sent to? They are not in your contact book.")
    _, row = _tracker_row(r.target)
    attached = r.words("attached")
    for col in ("cv_file", "cover_letter_file"):
        pdf = os.path.splitext(str((row or {}).get(col) or ""))[0] + ".pdf"
        if attached and os.path.basename(pdf) == attached:
            attached = pdf                          # the file as the repo names it
    saved = (r.target, r.value)
    r.target = {"kind": "person", "contact": cid}
    r.value = dict(r.value, attached=attached, kind="message",
                   channel=r.value.get("channel") or "linkedin_message")
    try:
        got = _msg_sent(r)
    finally:
        r.target, r.value = saved
    noun = str(person.get("documents.noun", "resume"))
    got["note"] = got["note"].replace("Logged as sent", f"Your {noun} logged as sent", 1)
    return got


def _process_register(r: Run) -> dict:
    """"Make it an interview": a call booked with a recruiter or a hiring manager on a live
    role is an interview stage (FUNCTIONS_SPEC 1.9), registered as /prep says
    (interview_pack.py process): a tracker row, its folder and outcome.md with the call
    booked as its stage. Run twice, it changes nothing."""
    import interview_pack
    from network import compose
    cid = r.target.get("contact") or r.words("contact")
    row, _ = _contact(cid)
    if row is None:
        raise Refused("They are not in your contact book any more.")
    role = r.words("role") or " ".join(str(row.get("role") or "").split()) or \
        app_model.role_in(row.get("next_action")) or "role not recorded"
    stage = r.words("stage") or ("Recruiter screen" if compose.is_recruiter(row.get("title"))
                                 else "Interview")
    day = r.words("on") or str(row.get("next_action_due") or "")
    day = day[:10] if app_model.as_day(day[:10]) else ""
    try:
        _row, _folder, added = interview_pack.register_process(
            row.get("company"), cid, role, stage, day, r.words("with"),
            today=r.day.isoformat(), time=r.words("time"))
    except (LookupError, ValueError) as e:
        raise Refused(str(e)[:1].upper() + str(e)[1:].rstrip(".") + ".") from None
    company = str(row.get("company") or "")
    return {"note": (f"Now an interview: {stage} at {company}" + (f" on {day}" if day else "")
                     + ". Prepare me makes its prep.") if added else
            f"Already an interview at {company}.", "undo": None}


def _app_followup_sent(r: Run) -> dict:
    """An application's follow-up that went: "followed up <day>" on its tracker row, the
    words kept as followup_<day>.md in its folder, as /outcome Step 2b logs one."""
    import confirm
    import csv_store
    import followups
    import outreach
    import throttle
    t = r.target
    day = r.on()
    text = str(r.value.get("text") or t.get("text") or "").strip()
    rows, row = _sent_row(t)
    if row is None:
        raise Refused("That application is no longer in your tracker.")
    mark = followups.LOG_AS % day
    if mark in str(row.get("notes") or ""):
        raise Refused(f"Already logged on {_weekday(day)}.")
    before = row.get("notes") or ""
    confirm.add_note(row, f"{mark}, said on the page")
    path = person.state("job_search_tracker.csv")
    csv_store.write_rows(path, rows, list(dict.fromkeys(
        csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
    folder = outreach.app_folder(t.get("company") or "", t.get("role") or "")
    kept = ""
    if text:
        os.makedirs(folder, exist_ok=True)
        kept = os.path.join(folder, f"followup_{day}.md")
        if not os.path.exists(kept):
            with open(kept, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
        else:
            kept = ""
    return {"note": f"Logged: you followed up with {t.get('company')} on {day}.",
            "undo": {"action": "due.undo", "target": {"kind": "due", "half": "application",
                                                       "company": t.get("company"),
                                                       "role": t.get("role")},
                     "value": {"notes": before, "remove": app_model.rel(kept) if kept else ""}}}


def _msg_received(r: Run) -> dict:
    """"They replied": their words as they came, through state.py received, so a reply is
    owed and the reply drafted next starts from what they said. The words leave the page's
    database with the claim (claim()), as a pasted resume does."""
    state = _state()
    cid = r.target.get("contact") or ""
    text = str(r.value.get("text") or "").strip()
    if not text:
        raise Refused("Paste what they said, so the reply can answer it.")
    day = r.on()
    path = _text_file(text)
    try:
        with _thread_lock():
            argv = ["received", cid, "--text-file", path, "--date", day, "--today",
                    r.day.isoformat()]
            channel = str(r.value.get("channel") or "")
            if channel in state.RECEIVED_CHANNELS:
                argv += ["--channel", channel]
            if r.value.get("subject"):
                argv += ["--subject", r.words("subject")]
            code, out = _cli(state, argv)
    finally:
        os.remove(path)
    if code:
        raise Refused(_said(out))
    # Their words are in the log now: the page's database keeps none of them.
    if r.version is not None and not str(r.act.get("claimed_by") or ""):
        r.w.add("update", "actions", r.aid, {"value": {"__delete__": True}},
                if_version=r.version)
    who = _first(cid)
    got = {"note": f"Logged: {who} wrote on {day}. A reply is owed.",
           "undo": {"action": "msg.unreceived", "target": {"kind": "person", "contact": cid},
                    "value": {"on": day}}}
    if r.value.get("draft"):
        wid = page_db.safe_id(f"reply~{cid}")
        have = (r.db.get("work") or {}).get(wid)
        if not have or str(have["data"].get("status") or "") in page_db.FINISHED:
            r.w.add("set", "work", wid, {
                "kind": "reply", "title": f"Reply to {who}", "to": "either",
                "args": dict({"contact": cid, "received": r.aid, "on": day},
                             **({"want": str(r.value.get("want"))[:600]} if r.value.get("want")
                                else {})),
                "asked_at": app_model.stamp(r.at), "asked_from": {"tab": r.act.get("tab") or ""},
                "priority": 0, "status": "queued", "stage": 0,
                "stages": [{"name": x["name"], "est_s": x["est_s"]}
                           for x in page_db.progress("reply")["stages"]]},
                if_version=have["version"] if have else None)
            got["note"] += " Claude drafts the reply next."
    return got


def _msg_unreceived(r: Run) -> dict:
    """Their message taken off the log again: the newest one in from them on that day."""
    from network import state as st
    cid = r.target.get("contact") or ""
    day = r.words("on")
    path = person.state("network_threads.csv")
    with _thread_lock():
        rows = st.load_threads(path)
        hit = None
        for i in range(len(rows) - 1, -1, -1):
            m = rows[i]
            if str(m.get("contact_id") or "").strip() == cid and st.direction(m) == "in" \
                    and str(m.get("date") or "")[:10] == day:
                hit = i
                break
        if hit is None:
            raise Refused("Their message is not on the log any more.")
        del rows[hit]
        st.save_threads(rows, path)
        contacts = st.load_contacts(person.state("network_contacts.csv"))
        c = st.already_contacted(contacts, contact_id=cid)
        if c is not None and str(c.get("status") or "") in st.DERIVABLE | {""}:
            c["status"] = st.derive_status(st.threads_for(rows, cid))
            st.save_contacts(contacts, person.state("network_contacts.csv"))
    return {"note": f"Taken off the log: {_first(cid)}'s message.", "undo": None}


def _kind_of_row(row: dict) -> str:
    scen = str(row.get("scenario") or "").lower()
    if scen in ("connection_note", "connection_request", "first_message", "first_note"):
        return "first_note"
    if "nudge" in scen or "follow" in scen:
        return "follow_up"
    return "reply"


def _msg_unsent(r: Run) -> dict:
    state = _state()
    cid = r.target.get("contact") or ""
    _, msgs = _contact(cid)
    out_rows = [m for m in msgs if state.direction(m) == "out"]
    last = max(out_rows, key=lambda m: str(m.get("date") or "")) if out_rows else {}
    code, out = _cli(state, ["unsend", cid, "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    value = {"kind": _kind_of_row(last), "text": last.get("full_text") or "",
             "channel": {"connection": "linkedin_note", "inmail": "inmail",
                         "email": "email"}.get(str(last.get("channel") or ""), "linkedin_message")}
    return {"note": f"Taken off the log: the message to {_first(cid)} is a draft again.",
            "undo": {"action": "msg.sent", "target": {"kind": "message", "contact": cid},
                     "value": value}}


def _msg_skip(r: Run) -> dict:
    cid = r.target.get("contact") or ""
    code, out = _cli(_state(), ["drop", cid, "--reason", r.words() or "not now, said on the page",
                                "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return {"note": f"Set aside: no note to {_first(cid)} for now.",
            "undo": {"action": "msg.unskip", "target": {"kind": "message", "contact": cid}}}


def _msg_unskip(r: Run) -> dict:
    cid = r.target.get("contact") or ""
    code, out = _cli(_state(), ["reopen", cid, "--reason", r.words() or "brought back on the page",
                                "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return {"note": f"{_first(cid)} is back among the people to write to.",
            "undo": {"action": "msg.skip", "target": {"kind": "message", "contact": cid}}}


def _set_contact(r: Run, status: str, action: str, due: str, note: str) -> dict:
    cid = r.target.get("contact") or ""
    row, _ = _contact(cid)
    if row is None:
        raise Refused("They are no longer in your contact book.")
    before = {"status": row.get("status") or "", "next_action": row.get("next_action") or "",
              "due": row.get("next_action_due") or ""}
    code, out = _cli(_state(), ["set", cid, "--status", status, "--next-action", action,
                                "--due", due, "--note", note, "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return before


def _decline_employer(company: str, why: str, day: str) -> str:
    """The employer joins the ones turned down by name (profile/search.py BAR_DECLINED, read
    by bar.py, every round and discovery), keyed the way bar.py looks it up; "" when it was
    already there, so an undo never takes away a ruling the person made before."""
    import profile_set
    from company_key import key as _ckey
    try:
        have = dict(profile_set.get("search.py", "BAR_DECLINED") or {})
    except Exception:  # noqa: BLE001  no setting yet: start one
        have = {}
    k = _ckey(company) or company
    if not k or k in have:
        return ""
    have[k] = f"turned down on the page, {day}: {why}"
    profile_set.set_line("search.py", "BAR_DECLINED", have)
    return k


def _undecline(k: str) -> None:
    import profile_set
    try:
        have = dict(profile_set.get("search.py", "BAR_DECLINED") or {})
    except Exception:  # noqa: BLE001
        return
    if have.pop(k, None) is not None:
        profile_set.set_line("search.py", "BAR_DECLINED", have)


PARKED = "draft.not-needed.md"     # a note nobody will send, kept beside its folder's draft


def _park_draft(cid: str) -> bool:
    """A drafted note nobody will send (they are in touch another way), kept, never deleted:
    the page lists only draft.md, and the undo puts it back."""
    folder = person.state("documents", "network", cid)
    src, dst = os.path.join(folder, "draft.md"), os.path.join(folder, PARKED)
    if not os.path.exists(src):
        return False
    os.replace(src, dst)
    return True


def _unpark_draft(cid: str) -> None:
    folder = person.state("documents", "network", cid)
    src, dst = os.path.join(folder, PARKED), os.path.join(folder, "draft.md")
    if os.path.exists(src) and not os.path.exists(dst):
        os.replace(src, dst)


def _person_stop(r: Run) -> dict:
    """The bin beside a person, each choice doing what it says: not this person (closed);
    not the employer any more (them closed, everyone there not yet written to closed too,
    and no more roles or people from it); or in touch another way (no note drafted, the
    route kept as a conversation)."""
    why = r.words() or "no more messages, said on the page"
    scope = str(r.value.get("scope") or "")
    cid = r.target.get("contact") or ""
    target = {"kind": "person", "contact": cid}
    if scope == "other":
        before = _set_contact(r, "in_conversation", "", "", why)
        parked = _park_draft(cid)
        return {"note": f"No note to {_first(cid)}: you are in touch another way.",
                "undo": {"action": "person.status", "target": dict(target, parked=parked),
                         "value": before}}
    before = _set_contact(r, "closed", "", "", why)
    if scope != "employer":
        return {"note": f"No more messages to {_first(cid)}.",
                "undo": {"action": "person.status", "target": target, "value": before}}
    from company_key import key as _ckey
    st = _state()
    row, _ = _contact(cid)
    company = str((row or {}).get("company") or r.value.get("employer") or "")
    k = _ckey(company)
    others = []
    if k:
        threads = st.load_threads(person.state("network_threads.csv"))
        wrote = {str(t.get("contact_id") or "").strip() for t in threads}
        for c in st.load_contacts(person.state("network_contacts.csv")):
            oid = str(c.get("contact_id") or "").strip()
            if oid == cid or oid in wrote or _ckey(c.get("company") or "") != k:
                continue
            if str(c.get("status") or "") in ("", "not_contacted"):
                code, out = _cli(st, ["set", oid, "--status", "closed", "--note", why,
                                      "--today", r.day.isoformat()])
                if not code:
                    others.append({"contact": oid, "value": {
                        "status": c.get("status") or "", "next_action": c.get("next_action") or "",
                        "due": c.get("next_action_due") or ""}})
    declined = _decline_employer(company, why, r.day.isoformat()) if company else ""
    more = f", and {len(others)} more there" if others else ""
    return {"note": f"No more messages to {_first(cid)}{more}; no more roles or people from "
                    f"{company or 'them'}.",
            "undo": {"action": "person.status",
                     "target": dict(target, others=others, declined=declined), "value": before}}


def _person_status(r: Run) -> dict:
    status = r.words("status")
    if not status:
        raise Refused("Which status: none was given.")
    before = _set_contact(r, status, str(r.value.get("next_action") or ""),
                          str(r.value.get("due") or ""), r.words() or "changed on the page")
    cid = r.target.get("contact") or ""
    # The undo of "not the employer any more": everyone else it closed, and the employer.
    st = _state()
    for o in r.target.get("others") or []:
        v = o.get("value") or {}
        _cli(st, ["set", o["contact"], "--status", v.get("status") or "not_contacted",
                  "--next-action", v.get("next_action") or "", "--due", v.get("due") or "",
                  "--note", "brought back on the page", "--today", r.day.isoformat()])
    if r.target.get("declined"):
        _undecline(str(r.target["declined"]))
    if r.target.get("parked"):
        _unpark_draft(cid)
    return {"note": f"{_first(cid)}: {status.replace('_', ' ')}.",
            "undo": {"action": "person.status", "target": {"kind": "person", "contact": cid},
                     "value": before}}


def _call_booked(r: Run) -> dict:
    day = _stage_day(r)
    time_ = r.words("time")
    at = f" at {time_}" if re.match(r"^\d{1,2}:\d{2}$", time_) else ""
    cid = r.target.get("contact") or ""
    before = _set_contact(r, "call_booked", f"Call on {day}{at}: prepare for it", day,
                          f"call booked for {day}{at}, said on the page")
    return {"note": f"Call with {_first(cid)} on {day}{at}. Prepare for it from their row.",
            "undo": {"action": "person.status", "target": {"kind": "person", "contact": cid},
                     "value": before}}


def _referral_agreed(r: Run) -> dict:
    cid = r.target.get("contact") or ""
    role = " ".join(str(r.value.get("role") or "").split())[:100]
    before = _set_contact(r, "referral_in_progress",
                          f"Referral for {role}: wait to hear, then thank them" if role else
                          "Referral in progress: wait to hear, then thank them", "",
                          f"they put the person forward{' for ' + role if role else ''}, said "
                          "on the page")
    return {"note": f"{_first(cid)} is putting you forward"
                    + (f" for {role}" if role else "") + ". Nothing goes cold there meanwhile.",
            "undo": {"action": "person.status", "target": {"kind": "person", "contact": cid},
                     "value": before}}


REFERRAL_ENDS = {"hired": "hired", "rejected": "not taken forward", "withdrawn": "withdrawn",
                 "over": "over"}


def _referral_ended(r: Run) -> dict:
    cid = r.target.get("contact") or ""
    why = r.words() or "over"
    said = REFERRAL_ENDS.get(why.lower(), why)
    before = _set_contact(r, "in_conversation", "Thank them for the referral", "",
                          f"the referral ended: {said}, said on the page")
    return {"note": f"The referral through {_first(cid)} is over ({said}). The hold there is "
                    "lifted.",
            "undo": {"action": "person.status", "target": {"kind": "person", "contact": cid},
                     "value": before}}


def _due_snooze(r: Run) -> dict:
    """Not today: the due day moved, written back where the due list reads it."""
    t = r.target
    until = r.words("until") or (r.day + dt.timedelta(days=1)).isoformat()
    try:
        day = dt.date.fromisoformat(until[:10])
    except ValueError:
        raise Refused(f"{until} is not a day.") from None
    if day <= r.day:
        raise Refused("Pick a day after today.")
    if t.get("half") == "application":
        import confirm
        import csv_store
        import throttle
        rows, row = _sent_row(t)
        if row is None:
            raise Refused("That application is no longer in your tracker.")
        before = row.get("notes") or ""
        confirm.add_note(row, f"{r.day.isoformat()}: DO NOT CHASE until {day.isoformat()}, said on "
                           "the page")
        path = person.state("job_search_tracker.csv")
        csv_store.write_rows(path, rows, list(dict.fromkeys(
            csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
        return {"note": f"Not today: {t.get('company')} again on {day.isoformat()}.",
                "undo": {"action": "due.undo", "target": dict(t), "value": {"notes": before}}}
    if t.get("half") == "requests":
        # "Keep waiting" on the connection requests nobody accepted: each one's day moved.
        moved = 0
        for cid in t.get("contacts") or []:
            if _contact(cid)[0] is None:
                continue
            code, _out = _cli(_state(), ["set", cid, "--due", day.isoformat(), "--note",
                                         f"kept waiting for the request, again {day.isoformat()}, "
                                         "said on the page", "--today", r.day.isoformat()])
            moved += 0 if code else 1
        if not moved:
            raise Refused("None of them is in your contact book now.")
        return {"note": f"Kept waiting: asked again on {day.isoformat()}.", "undo": None}
    cid = t.get("contact") or ""
    row, _ = _contact(cid)
    if row is None:
        raise Refused("They are no longer in your contact book.")
    before = {"next_action": row.get("next_action") or "", "due": row.get("next_action_due") or ""}
    code, out = _cli(_state(), ["set", cid, "--due", day.isoformat(), "--note",
                                f"not today, again {day.isoformat()}, said on the page",
                                "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return {"note": f"Not today: {_first(cid)} again on {day.isoformat()}.",
            "undo": {"action": "due.undo", "target": {"kind": "due", "half": "contact",
                                                       "contact": cid}, "value": before}}


# ---- what it learned, tips


def _learned_retire(r: Run, retire: bool = True) -> dict:
    import learned
    n = int(r.target.get("n") or 0)
    rows = learned.load()
    if not 1 <= n <= len(rows):
        raise Refused("That rule is no longer there.")
    if retire:
        learned.retire(n)
    else:
        rows[n - 1]["status"] = "active"
        learned.save_entries(rows)
    rule = " ".join(str(rows[n - 1].get("rule") or "").split())[:80]
    return {"note": (f"Removed: {rule}" if retire else f"Back: {rule}"),
            "undo": {"action": "learned.unretire" if retire else "learned.retire",
                     "target": dict(r.target)}}


def _tip_seen(r: Run) -> dict:
    import tips
    area = str(r.target.get("area") or r.words("area") or "general")
    state = tips.load()
    tips.line(area, r.day, state)
    tips.save(state)
    return {"note": "Got it.", "undo": None}


# ---- requests nobody accepted


def _withdrawn(r: Run) -> dict:
    t = r.target
    want = [str(c) for c in (r.value.get("contacts") or t.get("contacts") or [])
            if str(c) in set(t.get("contacts") or [])]
    if not want:
        raise Refused("Which requests: none of these is waiting any more.")
    with _thread_lock():
        code, out = _cli(_state(), ["withdraw", *want, "--reason", "withdrawn on LinkedIn, "
                                    "said on the page", "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return {"note": f"Logged: {len(want)} request{'s' if len(want) != 1 else ''} withdrawn.",
            "undo": {"action": "requests.unwithdrawn", "target": dict(t),
                     "value": {"contacts": want, "on": r.day.isoformat()}}}


def _unwithdrawn(r: Run) -> dict:
    from network import state as st
    want = set(str(c) for c in r.value.get("contacts") or [])
    day = r.words("on")
    path = person.state("network_threads.csv")
    with _thread_lock():
        rows = st.load_threads(path)
        keep = [m for m in rows if not (str(m.get("contact_id") or "").strip() in want
                                        and st.is_withdrawal(m)
                                        and str(m.get("date") or "")[:10] == day)]
        if len(keep) == len(rows):
            raise Refused("Those withdrawals are not on the log any more.")
        st.save_threads(keep, path)
        cpath = person.state("network_contacts.csv")
        contacts = st.load_contacts(cpath)
        for c in contacts:
            if str(c.get("contact_id") or "").strip() in want:
                c["status"] = st.derive_status(st.threads_for(keep, c["contact_id"]))
        st.save_contacts(contacts, cpath)
    return {"note": "Taken back: the requests are waiting again.", "undo": None}


# ---- your search


_SEARCH_ROWS = {"window": "J6", "places": "J7", "roles": "J8", "employers": "J9",
                "sites": "J10", "wide": "J11", "pay": "J12"}


def _search_set(r: Run) -> dict:
    """A search setting changed on the page, through the writers the Tweak panel's search
    rows use (tools/tweak.py, kept): the person's own profile/search.py, with what depends
    on it queued (a search, an employer's board found)."""
    import tweak
    what = r.words("what")
    p = _SEARCH_ROWS.get(what)
    if not p:
        raise Refused("That is not a search setting the page can change.")
    v = r.value.get("value") if "value" in r.value else r.value.get("to")
    steps = None
    if what in ("places", "roles"):
        add, rem = r.value.get("add"), r.value.get("remove")
        if isinstance(add, str) or isinstance(rem, str):
            v = {"add": add} if add else {"remove": rem}
        elif isinstance(add, list) or isinstance(rem, list):
            # Several at once, from the page's one sheet: each written in turn, so every one
            # reads the list as the one before left it.
            steps = ([{"add": str(x).strip()} for x in add or [] if str(x).strip()]
                     + [{"remove": str(x).strip()} for x in rem or [] if str(x).strip()])
        elif isinstance(v, list):
            raise Refused("Say what to add or take off, one at a time.")
    if what == "sites" and r.value.get("name"):
        v = {str(r.value["name"]): bool(r.value.get("on"))}
    if what == "pay" and isinstance(v, str):
        # The first number written, never every digit run together ("90,000, hoping for
        # 110,000" was once read as 90000110000).
        m = re.search(r"\d[\d,]*(?:\.\d+)?", v)
        v = float(m.group(0).replace(",", "")) if m else None
    if what == "pay" and not isinstance(v, (int, float)):
        raise Refused("Give the lowest pay you would take, as one number.")

    def one(change) -> dict:
        work = {"kind": "tweak", "args": {"target": {"id": "jobs", "output": "jobs"},
                                          "changes": [{"p": p, "v": change}],
                                          "keep": {"scope": "all"}}}
        got = tweak.apply(work, r.day)
        if got.get("status") not in ("done", "cached"):
            raise Refused(got.get("summary") or "It could not be changed.")
        for n, item in enumerate(got.get("then") or []):
            wid = page_db.safe_id(f"{item['kind']}~setting~{got.get('key')}~{n}")
            r.w.add("set", "work", wid, {"kind": item["kind"], "title": item.get("title") or "",
                                         "to": page_db.WORK_KINDS[item["kind"]]["to"],
                                         "args": item.get("args") or {},
                                         "asked_at": app_model.stamp(r.at), "priority": 0,
                                         "status": "queued", "stage": 0,
                                         "stages": page_db.progress(item["kind"])["stages"]})
        return got

    if steps is not None:
        if not steps:
            raise Refused("Nothing to change.")
        notes = [one(c).get("summary") for c in steps]
        return {"note": "; ".join(n for n in notes if n) or "Changed.", "undo": None}
    got = one(v)
    return {"note": got.get("summary") or "Changed.",
            "undo": {"action": "search.unset", "target": dict(r.target),
                     "value": {"key": got.get("key")}} if got.get("status") == "done" else None}


def _search_unset(r: Run) -> dict:
    import tweak
    key = re.sub(r"[^0-9a-f]", "", str(r.value.get("key") or ""))[:10]
    got = tweak.apply({"kind": "tweak", "args": {"target": {"id": "jobs", "output": "jobs"},
                                                 "undo": key, "changes": []}}, r.day)
    if got.get("status") != "done":
        raise Refused(got.get("summary") or "It has changed since.")
    return {"note": "Back as it was.", "undo": None}


def _rule_lift(r: Run) -> dict:
    import exclude
    t = r.target
    path = person.state("job_scraper", "seen_jobs.json")
    if t.get("company"):
        dnt = person.state("job_scraper", "do_not_target.json")
        data = app_model.read_json(dnt, {})
        rows = data.get("entries") if isinstance(data, dict) and "entries" in data else data
        rows = rows if isinstance(rows, list) else []
        gone = [e for e in rows if isinstance(e, dict) and e.get("company") == t["company"]]
        if not gone:
            raise Refused("That employer is not left out any more.")
        keep = [e for e in rows if e not in gone]
        out = dict(data, entries=keep) if isinstance(data, dict) and "entries" in data else keep
        with open(dnt, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return {"note": f"{t['company']} is searched again.",
                "undo": {"action": "rule.restore", "target": dict(t), "value": {"dnt": gone}}}
    data = exclude.load_seen(path)
    keys = [k for k, e in (data.get("seen") or {}).items() if isinstance(e, dict)
            and str(e.get("status") or "").lower() == "excluded" and e.get("basis") == "person"
            and exclude.reason_group(str(e.get("exclusion_reason") or "")) == t.get("words")]
    if not keys:
        raise Refused("Nothing is left out for that reason any more.")
    exclude.lift(urls=[data["seen"][k].get("url") or k for k in keys],
                 why="brought back on the page", today=r.day.isoformat(), path=path)
    return {"note": f"Brought back: {len(keys)} left out for \"{t.get('words')}\".",
            "undo": {"action": "rule.restore", "target": dict(t), "value": {"keys": keys}}}


def _rule_restore(r: Run) -> dict:
    import exclude
    if r.value.get("dnt"):
        dnt = person.state("job_scraper", "do_not_target.json")
        data = app_model.read_json(dnt, {})
        rows = data.get("entries") if isinstance(data, dict) and "entries" in data else data
        rows = (rows if isinstance(rows, list) else []) + list(r.value["dnt"])
        out = dict(data, entries=rows) if isinstance(data, dict) and "entries" in data else rows
        with open(dnt, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return {"note": "Left out again.", "undo": None}
    path = person.state("job_scraper", "seen_jobs.json")
    data = exclude.load_seen(path)
    for k in r.value.get("keys") or []:
        e = (data.get("seen") or {}).get(k)
        if isinstance(e, dict):
            e["status"] = "excluded"
            e.pop("lifted_date", None)
            e.pop("lifted_because", None)
    exclude.save_seen(data, path)
    return {"note": "Left out again.", "undo": None}


# ---- the brief's schedule and a break (tools/routines.py: move, pause, resume)


def _routines_said(e: Exception) -> str:
    said = str(e).strip().rstrip(".")
    said = {"there is no brief yet to move": "There is no brief yet: turn it on from the bell "
                                             "on your Brief",
            "there is no brief to turn off": "Your brief is not on",
            "there is no brief yet to turn on": "There is no brief yet: turn it on from the bell "
                                                "on your Brief, and Claude sets it up",
            "a break ends after today": "Pick a day after today",
            "name at least one day": "Pick at least one day"}.get(said, said)
    return said[:1].upper() + said[1:] + "."


def _waiting(got: dict) -> str:
    """What is left for a chat: the scheduled-task change code cannot make."""
    return (" A chat makes the change to the brief itself next; nothing else is needed from "
            "you.") if got.get("calls") else ""


def _brief_move(r: Run) -> dict:
    """New days and a new time for the brief (or a whole schedule, an undo): written to
    profile/routines.json by routines.py move, the task's own change kept for a chat."""
    import routines
    cron = r.words("cron")
    days = r.value.get("days")
    try:
        got = routines.move(cron=cron) if cron else routines.move(
            days=days if days not in (None, "", []) else None, time=r.words("time") or None)
    except ValueError as e:
        raise Refused(_routines_said(e)) from None
    if got["cron"] == got.get("old"):
        return {"note": f"Your brief already comes {got['when']}.", "undo": None}
    return {"note": got["say"] + _waiting(got),
            "undo": {"action": "brief.move", "target": dict(r.target),
                     "value": {"cron": got["old"]}} if got.get("old") else None}


def _brief_pause(r: Run) -> dict:
    """Taking a break until a day (two weeks when none is given): routines.py pause holds
    every follow-up and rests the brief, one brief kept for the day they come back."""
    import routines
    until = r.words("until")
    try:
        day = dt.date.fromisoformat(until[:10]) if until else r.day + dt.timedelta(days=14)
    except ValueError:
        raise Refused(f"{until} is not a day: give it as 2026-11-08.") from None
    had = routines.paused(r.day.isoformat())
    if had and had.get("until") == day.isoformat():
        return {"note": f"Your search is paused until {day.isoformat()} already.", "undo": None}
    try:
        with _thread_lock():
            got = routines.pause(day.isoformat(), today=r.day.isoformat())
    except ValueError as e:
        raise Refused(_routines_said(e)) from None
    return {"note": got["say"] + _waiting(got),
            "undo": {"action": "brief.resume", "target": dict(r.target), "value": {}}}


def _brief_resume(r: Run) -> dict:
    import routines
    was = routines.paused(r.day.isoformat())
    if not was:
        return {"note": "Your search is not paused.", "undo": None}
    with _thread_lock():
        got = routines.resume(today=r.day.isoformat())
    undo = got.get("undo")
    return {"note": (got.get("say") or "Your search is running again.") + _waiting(got),
            "undo": {"action": "brief.pause", "target": dict(r.target),
                     "value": undo["value"]} if undo else None}


def _brief_switch(r: Run, which: str) -> dict:
    """The brief alone, off or on again (routines.py off, on): nothing else in the search
    stops or starts, and the task's own change is kept for a chat."""
    import routines
    try:
        got = (routines.off if which == "off" else routines.on)()
    except ValueError as e:
        raise Refused(_routines_said(e)) from None
    if not got.get("changed"):
        return {"note": got["say"], "undo": None}
    return {"note": got["say"] + _waiting(got),
            "undo": {"action": got["undo"]["action"], "target": dict(r.target), "value": {}}}


# ---- LinkedIn: the data download and the page's own reading


class NeedsAssets(Exception):
    """The action names page assets this chat has not fetched yet: no receipt, and the
    chat is told which to fetch (Artifact read with each id as the path) and to apply
    again with --assets."""

    def __init__(self, ids):
        super().__init__("fetch: " + ", ".join(ids))
        self.ids = list(ids)


ASSETS_DIR: list = [None]


def _export_requested(r: Run) -> dict:
    import export
    before = export.load_record().get("requested_on") or ""
    export.requested(r.day.isoformat())
    return {"note": "Noted: the LinkedIn download is asked for. LinkedIn emails the link, "
                    "which works for 72 hours.",
            "undo": {"action": "export.unrequested", "target": dict(r.target),
                     "value": {"before": before}}}


def _export_unrequested(r: Run) -> dict:
    import export
    export.save_record({"requested_on": str(r.value.get("before") or "")})
    return {"note": "Taken back.", "undo": {"action": "export.requested",
                                           "target": dict(r.target)}}


def _assets_given(r: Run) -> list:
    """[(asset id, the file name it stands for, its part)], only names the app reads. A file
    over the page store's 20 MiB comes as parts (`part`, from 1), each a whole number of
    records under the file's own header line, joined again in `_export_take`."""
    import export
    names = set(export.FILES.values())
    out = []
    for a in r.value.get("assets") or ():
        if not isinstance(a, dict):
            continue
        aid, name = re.sub(r"[^0-9a-f]", "", str(a.get("id") or ""))[:32], str(a.get("name") or "")
        base = os.path.basename(name)
        match = next((n for n in names if n.lower() == base.lower()), None)
        try:
            part = max(1, int(a.get("part") or 1))
        except (TypeError, ValueError):
            part = 1
        if aid and match:
            out.append((aid, match, part))
    return out


def _export_take(r: Run) -> dict:
    """The files of a LinkedIn download the person added on the page, taken the way a chat
    takes one (export.py take): saved, the history imported, follow-up dates written, the
    day recorded. The same download taken twice changes nothing. The receipt names the
    assets, which may be removed from the page's store now."""
    import hashlib
    import shutil
    import export
    given = _assets_given(r)
    if not given:
        raise Refused("Add the files from your LinkedIn download: messages.csv, "
                      "Invitations.csv and Connections.csv.")
    folder = ASSETS_DIR[0]
    found, missing = [], []
    for aid, name, part in given:
        hits = [f for f in (os.listdir(folder) if folder and os.path.isdir(folder) else [])
                if f.split(".")[0] == aid]
        (found.append((os.path.join(folder, hits[0]), name, part)) if hits else missing.append(aid))
    if missing:
        raise NeedsAssets(missing)
    found.sort(key=lambda x: (x[1], x[2]))
    h = hashlib.sha256()
    for path, name, _part in found:
        h.update(name.encode())
        with open(path, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()[:20]
    remove = [g[0] for g in given]
    with _thread_lock():
        rec = export.load_record()
        # The same download again changes nothing, unless its files are no longer on file
        # (taken in a chat whose folder went with it): then it is taken again.
        if digest in (rec.get("taken_hashes") or []) and export._holds_any(export.default_folder()):
            return {"note": "Already taken: that download changed nothing new.", "undo": None,
                    "remove_assets": remove}
        work = tempfile.mkdtemp(prefix="ljs_export_")
        try:
            for path, name, part in found:
                # Parts after the first carry the header line again: it is dropped, so the
                # joined file is the one LinkedIn gave.
                with open(path, "rb") as src, open(os.path.join(work, name), "ab") as out:
                    data = src.read()
                    out.write(data.split(b"\n", 1)[1] if part > 1 and b"\n" in data else data)
            lines = export.take([work])
        finally:
            shutil.rmtree(work, ignore_errors=True)
        rec = export.load_record()
        export.save_record({"taken_hashes": ((rec.get("taken_hashes") or []) + [digest])[-10:]})
    counts = dict(export.load_record().get("counts") or {})
    said = {k: int(counts.get(k) or 0) for k in ("messages", "connections", "invitations",
                                                 "replied", "imported")}
    note = (f"Taken: {said['messages']} messages, {said['connections']} connections and "
            f"{said['invitations']} invitations read; {said['replied']} people replied since "
            "the last one.")
    return {"note": note, "undo": None, "counts": said, "remove_assets": remove,
            "lines": [app_model.scrub(x, ()) for x in lines[:3]]}


def _page_reads_save(updates: dict) -> dict:
    import place
    got = dict(place.page_reads_record(), **updates)
    path = person.state(*place.PAGE_READS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return got


def _reader_checked(r: Run) -> dict:
    """"Check it works" on the page: it read a LinkedIn page as the person, or could not.
    From then on, for PAGE_READS_DAYS, the page counts as a browser that can read."""
    ok = r.value.get("ok")
    ok = str(r.value.get("value") or "").lower() in ("ok", "yes", "true") if ok is None else \
        bool(ok)
    _page_reads_save({"ok": ok, "checked_at": app_model.stamp(r.at),
                      "said": r.words("said")[:200]})
    if not ok and r.words("kind") == "check":
        # One of LinkedIn's own checks, met on the page: the day's reads stop here as they do
        # for a chat that meets one (reading.stop), and the page waits for tomorrow.
        import reading
        reading.stop("LinkedIn showed a check on the page: " + (r.words("said") or "a check")[:120])
        return {"note": "LinkedIn asked to check it was you, so reading stops for today. Finish "
                        "its check in Claude's browser; reading starts again tomorrow.",
                "undo": None}
    return {"note": ("Your page reads LinkedIn: profiles are read there from now on."
                     if ok else "Not signed in to LinkedIn in Claude's browser yet: sign in "
                                "there, and the page checks again by itself."),
            "undo": None}


REWRITE = "network~rewrite~"


def _rewrite_ids(args) -> list:
    args = args if isinstance(args, dict) else {}
    got = [str(c) for c in (args.get("contacts") or []) if str(c).strip()]
    one = str(args.get("contact") or "").strip()
    return got + [one] if one and one not in got else got


def _queue_rewrite(r: Run, cid: str) -> str:
    """Their waiting note, rewritten on the profile just read, as one `network` work item for
    every profile read before Claude next runs: a batch of reads is one piece of work and one
    chat turn, never one each (the maintainer, 2026-10-29: keep it cheap). Returns the line
    for the receipt."""
    import reading
    if not (reading.waits_on_read(cid) or reading.card_only_draft(cid)):
        return ""
    work = r.db.get("work") or {}
    for doc in work.values():
        d = doc["data"]
        if d.get("kind") == "network" and (d.get("args") or {}).get("rewrite") and \
                str(d.get("status") or "") not in page_db.FINISHED and cid in _rewrite_ids(d.get("args")):
            return " Your note to them is already being rewritten."
    # The batch still open: written earlier in this same run, or queued and not yet taken.
    wid, data, version = "", None, None
    for e in r.w.entries:
        if e["collection"] == "work" and e["doc_id"].startswith(page_db.safe_id(REWRITE)) and \
                e["op"] == "set" and e.get("file_path"):
            with open(e["file_path"], encoding="utf-8") as fh:
                data = json.load(fh)
            data.pop(page_db.VERSION_FIELD, None)
            wid, version = e["doc_id"], e.get("if_version")
    if data is None:
        for k, doc in sorted(work.items()):
            d = doc["data"]
            if k.startswith(page_db.safe_id(REWRITE)) and str(d.get("status") or "") == "queued" \
                    and not d.get("claimed_by"):
                wid, data, version = k, dict(d), doc["version"]
                data.pop(page_db.VERSION_FIELD, None)
                break
    if data is None:
        wid = page_db.safe_id(REWRITE + app_model.stamp(r.at).replace(":", "").replace("-", ""))
        data = {"kind": "network", "to": page_db.WORK_KINDS["network"]["to"],
                "args": {"contacts": [], "rewrite": True, "read": []},
                "asked_at": app_model.stamp(r.at), "asked_from": {"tab": r.act.get("tab") or ""},
                "priority": 0, "status": "queued", "stage": 0,
                "stages": page_db.progress("network")["stages"]}
    args = dict(data.get("args") or {})
    ids = _rewrite_ids(args)
    if cid not in ids:
        ids.append(cid)
    args.update({"contacts": ids, "rewrite": True,
                 "read": [x for x in (args.get("read") if isinstance(args.get("read"), list)
                                      else [args.get("read")] if args.get("read") else [])]
                 + [r.aid]})
    args.pop("contact", None)
    data["args"] = args
    data["title"] = (f"Your note to {_first(ids[0])}, on their profile" if len(ids) == 1 else
                     f"Your notes to {len(ids)} people, on their profiles")
    r.w.add("set", "work", wid, data, if_version=version)
    return " Claude rewrites your note to them on it next."


def _reading_done(r: Run) -> dict:
    """A profile the page read: logged by `reading.py read --source browser` exactly as a
    computer chat logs one, then off the page's queue, and its waiting note queued for its
    rewrite with every other profile read since Claude last ran. Their page's words leave the
    page's database with the receipt.

    The page reads three of LinkedIn's pages for each person: the profile (its top card), its
    Experience and its Education (`value.pages` names those that loaded). The profile alone
    shows no Experience until it is scrolled (seen live, 2026-10-29), and a refused read stayed
    on the queue to be read again at every opening: so a read with its Experience page loaded
    is never told to scroll, and a refusal no read can fix takes them off the queue."""
    import reading
    cid = r.target.get("contact") or ""
    text = str(r.value.get("text") or "")
    if not text.strip():
        _page_reads_save({"last_failed_at": app_model.stamp(r.at),
                          "said": r.words("said")[:200]})
        raise Refused("Nothing was read from their page: " + (r.words("said") or "it was "
                      "empty") + ".")
    mode = str(r.value.get("mode") or r.target.get("mode") or "deep")
    pages = [str(p) for p in (r.value.get("pages") or []) if isinstance(p, str)]
    pages += [str(p) for p in (r.value.get("tried") or []) if isinstance(p, str)]
    # The page's queue is its list for the day: on today's short list, as a computer chat
    # puts each person it reads (`reading.py shortlist`), then read the same way.
    _cli(reading, ["shortlist", cid])
    path = _text_file(text)
    try:
        argv = ["read", cid, path, "--source", "browser", "--mode",
                mode if mode in reading.READ_MODES else "deep", "--browser", "pane"]
        if "experience" in pages:
            # Their Experience page itself was opened: scrolling the profile would show
            # nothing more, so what it showed is read as it is.
            argv.append("--no-experience")
        if r.words("url"):
            argv += ["--url", r.words("url")]
        code, out = _cli(reading, argv)
    finally:
        os.remove(path)
    if r.version is not None and not str(r.act.get("claimed_by") or ""):
        r.w.add("update", "actions", r.aid, {"value": {"text": {"__delete__": True}}},
                if_version=r.version)
    kept = code in (reading.EXIT["ok"], reading.EXIT["skip"]) or \
        any(ln.startswith("reading: saved ") for ln in out.splitlines())
    if not kept:
        # LinkedIn signed out, asked for a check, or the page had not loaded: worth reading
        # again, so they stay on the queue. Anything else no second read would change (reads
        # set to paste, a page that is not theirs): off the queue, so it is never read again.
        again = {reading.EXIT["signin"]: "LinkedIn showed its sign-in page, not their profile. "
                                          "Sign in in Claude's browser and they are read again.",
                 reading.EXIT["check"]: "LinkedIn asked to check it's you, so reading stops for "
                                         "today. They are read again tomorrow.",
                 reading.EXIT["unknown"]: "Their page did not load. They are read again next time.",
                 reading.EXIT["scroll"]: "Their Experience did not load. They are read again "
                                          "next time."}
        if code in again:
            raise Refused(again[code])
        reading.page_read_done(cid)
        raise Refused("Their profile could not be kept, so it is not read again: paste it on "
                      "their card instead." if reading.reads_now() == "browser" else
                      "Reading profiles is set to paste: paste theirs on their card.")
    reading.page_read_done(cid)
    rec = _page_reads_save({"ok": True, "last_read_at": app_model.stamp(r.at)})
    _page_reads_save({"reads": int(rec.get("reads") or 0) + 1})
    verdict = next((ln for ln in out.splitlines() if ln.startswith("verdict:")), "")
    who = _first(cid)
    said = f"Read {who}'s page."
    if "SKIP" in verdict:
        return {"note": said + " Not one to write to now.", "undo": None}
    return {"note": said + (" Worth writing to." if "KEEP" in verdict else "")
            + _queue_rewrite(r, cid), "undo": None}


def _profile_pasted(r: Run) -> dict:
    """Their LinkedIn page, pasted on a phone or the web (CAPABILITY_MAP G14): kept by
    `reading.py read --source paste` exactly as a chat keeps a paste, the words then gone from
    the page's database. A note to them written before anything was read (WAITS ON A READ,
    or card-only) is queued for its rewrite on what was read (`_queue_rewrite`: one piece
    of work for every profile kept before Claude next runs, each contact on it once)."""
    import reading
    cid = r.target.get("contact") or ""
    text = str(r.value.get("text") or "")
    if len(text.split()) < 12:
        raise Refused("That is too short to be their profile: open their LinkedIn page, "
                      "select everything, copy it and paste it again.")
    path = _text_file(text)
    try:
        argv = ["read", cid, path, "--source", "paste"]
        if r.words("url"):
            argv += ["--url", r.words("url")]
        code, out = _cli(reading, argv)
    finally:
        os.remove(path)
    if r.version is not None and not str(r.act.get("claimed_by") or ""):
        raw = r.act.get("value")
        gone = {"text": {"__delete__": True}} if isinstance(raw, dict) else {"__delete__": True}
        r.w.add("update", "actions", r.aid, {"value": gone}, if_version=r.version)
    if code not in (reading.EXIT["ok"], reading.EXIT["skip"]):
        raise Refused(_said(out) if out.strip() else "their profile was not kept")
    who = _first(cid)
    verdict = next((ln for ln in out.splitlines() if ln.startswith("verdict:")), "")
    said = "Kept what their profile says." if who == "them" else \
        f"Kept what {who}'s profile says."
    if "SKIP" in verdict:
        return {"note": said + " Not one to write to now.", "undo": None}
    return {"note": said + _queue_rewrite(r, cid), "undo": None}


# ---- work items (the page's own list; nothing in the repo)


def _work(r: Run) -> tuple[str, dict]:
    wid = page_db.safe_id(r.target.get("id") or "")
    doc = (r.db.get("work") or {}).get(wid)
    if doc is None:
        raise Refused("That piece of work was not read: read the work list, then apply again.")
    return wid, doc


def _consent(r: Run, answer: str) -> dict:
    wid, doc = _work(r)
    skills = r.value.get("skills") or ([r.value.get("skill")] if r.value.get("skill") else [])
    skills = [str(s).strip() for s in skills if str(s).strip()]
    if not skills:
        raise Refused("Which skill: none was named.")
    answers = dict(doc["data"].get("answers") or {})
    held = dict(answers.get("skills") or {})
    held.update({s: answer for s in skills})
    answers["skills"] = held
    r.w.add("update", "work", wid, {"answers": answers}, if_version=doc["version"])
    other = "consent.no" if answer == "yes" else "consent.yes"
    return {"note": ("Noted: you can back up " if answer == "yes" else "Noted: leave off ")
            + ", ".join(skills) + ".",
            "undo": {"action": other, "target": {"kind": "work", "id": wid},
                     "value": {"skills": skills}}}


def _work_stop(r: Run, stop: bool = True) -> dict:
    wid = page_db.safe_id(r.target.get("id") or "")
    if stop and r.w.drop("work", wid):
        return {"note": "Not started: taken off the list.", "undo": None}
    wid, doc = _work(r)
    if str(doc["data"].get("status") or "") in page_db.FINISHED:
        raise Refused("It has already finished.")
    r.w.add("update", "work", wid, {"stop_asked": stop}, if_version=doc["version"])
    return {"note": "Stopping at its next step." if stop else "Carrying on.",
            "undo": {"action": "work.resume" if stop else "work.stop",
                     "target": {"kind": "work", "id": wid}}}


# ---- settings


def _save_person_json(key: str, value) -> None:
    person.put([key], value)


def _set_plan(value: str) -> None:
    """LINKEDIN_PLAN written the way every setting is (profile_set: the line replaced, read
    back to check it parses), never by a pattern over the file."""
    import profile_set
    profile_set.set_line("networking.py", "LINKEDIN_PLAN", value)


def _setting_set(r: Run) -> dict:
    key = r.target.get("key")
    choices = {k: [c[0] for c in ch] for k, _, ch in app_model.SETTINGS}
    value = str(r.value.get("value") or "").strip()
    if value not in choices.get(key, ()):
        raise Refused(f"{value or 'nothing'} is not one of the choices.")
    old = app_model.setting_values().get(key)
    if key in ("app_updates", "suggestions"):
        _save_person_json(key, value)
    elif key == "tips":
        import tips
        got = tips.load()
        got["off"] = value == "off"
        got["off_set"] = r.local.isoformat(timespec="seconds")
        tips.save(got)
    elif key == "linkedin_plan":
        _set_plan(value)
    elif key == "profile_reads":
        import profile_set
        profile_set.set_line("networking.py", "PROFILE_READS", value)
    label = dict(next(ch for k, _, ch in app_model.SETTINGS if k == key))[value]
    return {"note": f"Changed: {label}.",
            "undo": {"action": "setting.set", "target": dict(r.target), "value": {"value": old}}}


# ---- tweaks


def _tweak_undo(r: Run) -> dict:
    """Undo a tweak: the chat that claims it puts the version before back and makes the
    documents again (tools/tweak.py undo), so it is work, with its time, never instant."""
    key = re.sub(r"[^0-9a-f]", "", str(r.value.get("key") or ""))[:10]
    if not key:
        raise Refused("Which change to take back: none was named.")
    t = r.target
    output = "message" if t.get("kind") == "message" else str(r.value.get("output") or "resume")
    item = str(r.act.get("item") or "")
    wid = page_db.safe_id(f"tweak~{item}~undo-{key}")
    have = (r.db.get("work") or {}).get(wid)
    if have and str(have["data"].get("status") or "") not in page_db.FINISHED:
        return {"note": "Already on its way.", "undo": None}
    target = {"id": item, "output": output}
    if t.get("company"):
        target["company"] = t["company"]
    if t.get("contact"):
        target["contact"] = t["contact"]
    doc = {"kind": "tweak", "title": "Put back the version before", "to": "either",
           "args": {"target": target, "undo": key, "changes": []},
           "asked_at": app_model.stamp(r.at), "asked_from": {"tab": r.act.get("tab") or ""},
           "priority": 0, "status": "queued",
           "stages": [{"name": x["name"], "est_s": x["est_s"]}
                      for x in page_db.progress("tweak")["stages"]], "stage": 0}
    r.w.add("set", "work", wid, doc, if_version=have["version"] if have else None)
    return {"note": "Queued: Claude puts it back next.",
            "undo": {"action": "work.stop", "target": {"kind": "work", "id": wid}}}


def _tweak_offer(r: Run) -> dict:
    import tweak
    # The index names the target by the page's own id (q-tweak-<offer id>).
    oid = str(r.target.get("id") or "")
    o = tweak.offer(oid[len("q-tweak-"):] if oid.startswith("q-tweak-") else oid, r.day)
    if o is None:
        raise Refused("That is no longer offered.")
    yes = str(r.words() or r.value.get("value") or "").lower() in ("yes", "y", "true")
    got = tweak.answer_offer(o, yes, r.day)
    note = ("Kept as your usual." if yes and o["kind"] == "usual" else
            "Added: it is on the Tweak panel now." if yes else
            "No problem, I'll ask again in a month.")
    return {"note": note, "undo": {"action": "tweak.offer_undo", "target": dict(r.target),
                                   "value": got}}


def _tweak_offer_undo(r: Run) -> dict:
    import tweak
    tweak.undo_offer(r.value)
    return {"note": "Taken back.", "undo": None}


def _hint_seen(r: Run) -> dict:
    import tweak
    name = re.sub(r"[^a-z_]", "", str(r.value.get("hint") or r.words() or "tweak"))[:20] or "tweak"
    tweak.hint_seen(name, r.day)
    return {"note": "Got it.", "undo": None}


# ---- what is due


def _due_done(r: Run) -> dict:
    t, day = r.target, r.day.isoformat()
    if t.get("half") == "application":
        import confirm
        import csv_store
        import followups
        import throttle
        rows, row = _sent_row(t)
        if row is None:
            raise Refused("That application is no longer in your tracker.")
        before = row.get("notes") or ""
        confirm.add_note(row, f"{followups.LOG_AS % day}, said on the page")
        path = person.state("job_search_tracker.csv")
        csv_store.write_rows(path, rows, list(dict.fromkeys(
            csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
        return {"note": f"Marked as followed up today: {t.get('company')}.",
                "undo": {"action": "due.undo", "target": dict(t), "value": {"notes": before}}}
    cid = t.get("contact") or ""
    row, _ = _contact(cid)
    if row is None:
        raise Refused("They are no longer in your contact book.")
    before = {"next_action": row.get("next_action") or "", "due": row.get("next_action_due") or ""}
    code, out = _cli(_state(), ["set", cid, "--next-action", "", "--due", "", "--note",
                                "done, said on the page", "--today", day])
    if code:
        raise Refused(_said(out))
    return {"note": f"Done: {_first(cid)}.",
            "undo": {"action": "due.undo", "target": dict(t), "value": before}}


def _due_undo(r: Run) -> dict:
    t = r.target
    if t.get("half") == "application":
        import csv_store
        import throttle
        rows, row = _sent_row(t)
        if row is None:
            raise Refused("That application is no longer in your tracker.")
        row["notes"] = str(r.value.get("notes") or "")
        path = person.state("job_search_tracker.csv")
        csv_store.write_rows(path, rows, list(dict.fromkeys(
            csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
        kept = str(r.value.get("remove") or "")
        if kept and re.match(r"^documents/applications/[^/]+/followup_\d{4}-\d{2}-\d{2}\.md$",
                             kept.replace("\\", "/")):
            try:
                os.remove(person.state(*kept.replace("\\", "/").split("/")))
            except OSError:
                pass
        return {"note": f"The follow-up is due again: {t.get('company')}.",
                "undo": {"action": "due.done", "target": dict(t)}}
    cid = t.get("contact") or ""
    code, out = _cli(_state(), ["set", cid, "--next-action", str(r.value.get("next_action") or ""),
                                "--due", str(r.value.get("due") or ""), "--note",
                                "brought back on the page", "--today", r.day.isoformat()])
    if code:
        raise Refused(_said(out))
    return {"note": f"Due again: {_first(cid)}.", "undo": {"action": "due.done", "target": dict(t)}}


# ---- suggestions


def _suggest_dismiss(r: Run) -> dict:
    import app_alerts
    sid = str(r.target.get("id") or "")
    before = app_alerts.dismiss(sid, str(r.target.get("sug_kind") or ""), r.day)
    return {"note": "No thanks: it will not be suggested again.",
            "undo": {"action": "suggest.undismiss", "target": dict(r.target),
                     "value": {"before": before}}}


def _suggest_undismiss(r: Run) -> dict:
    import app_alerts
    sid = str(r.target.get("id") or "")
    app_alerts.undismiss(sid, r.value.get("before"))
    return {"note": "It may be suggested again.",
            "undo": {"action": "suggest.dismiss", "target": dict(r.target)}}


# ---- questions


def _fact_path(target: dict) -> str:
    return os.path.join(os.path.dirname(person.directory()), *str(target.get("file") or "").split("/"))


def _needs_answer(r: Run) -> dict:
    t = r.target
    if t["kind"] == "upgrade_ask":
        choice = r.words("value")
        if choice == "no":
            import profile_upgrades
            profile_upgrades.record_no(t["upgrade"], today=r.day)
            return {"note": profile_upgrades.NO_REPLY, "undo": None}
        if choice != "yes":
            raise Refused("Yes or not now: which?")
        wid = "talk~upgrade~" + page_db.safe_id(t["upgrade"])
        r.w.add("set", "work", wid, {
            "kind": "talk", "title": t.get("ask") or "Set this up with me", "to": "either",
            "args": {"upgrade": t["upgrade"]}, "asked_at": app_model.stamp(r.at),
            "priority": 0, "status": "queued", "stages": page_db.progress("talk")["stages"],
            "stage": 0})
        return {"note": "Claude takes you through it next.",
                "undo": {"action": "work.stop", "target": {"kind": "work", "id": wid}}}
    if t["kind"] == "offer":
        import learned
        choice = r.words("value")
        if choice not in ("keep", "switch"):
            raise Refused("Keep yours, or try the new way: which?")
        learned.decide(int(t["n"]), choice, today=r.day.isoformat())
        return {"note": "Kept your way." if choice == "keep" else "Trying the new way.",
                "undo": None}
    answer = " ".join(str(r.value.get("text") or r.value.get("value") or "").split())
    if not answer:
        raise Refused("No answer was given.")
    path = _fact_path(t)
    if not path.endswith(".md") and _answer_in_place(path, t, answer):
        # Written where its mark was, in the code or data file itself, and the file still
        # loads: instant, with no chat (each answer had been ten minutes of a chat's work,
        # the maintainer, 2026-10-29).
        return {"note": "Written into your profile.", "undo": None}
    if not path.endswith(".md"):
        wid = "talk~fact~" + app_model.rev_of(t.get("file"), t.get("what"))[:8]
        r.w.add("set", "work", wid, {
            "kind": "talk", "title": f"Write your answer into your profile: {t.get('what')}",
            "to": "either", "args": {"file": t.get("file"), "what": t.get("what"),
                                     "answer": answer},
            "asked_at": app_model.stamp(r.at), "priority": 0, "status": "queued",
            "stages": page_db.progress("talk")["stages"], "stage": 0})
        return {"note": "Your chat writes it in.", "undo": None}
    import profile_upgrades
    text = app_model.read_text(path)
    hit = next((m for m in profile_upgrades.CONFIRM.finditer(text)
                if ((m.group(1) or "").strip() or "a fact marked unconfirmed") == t.get("what")),
               None)
    if hit is None:
        raise Refused("That mark is no longer in your profile.")
    new = text[:hit.start()] + answer + text[hit.end():]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    return {"note": "Written into your profile.",
            "undo": {"action": "needs.unanswer", "target": dict(t),
                     "value": {"at": hit.start(), "answer": answer, "mark": hit.group(0)}}}


def _answer_in_place(path: str, t: dict, answer: str) -> bool:
    """The answer put where its [CONFIRM: ...] mark is in a .py or .json profile file, only
    when the file still loads after it; False leaves the file as it was."""
    import profile_upgrades
    if not (path.endswith(".py") or path.endswith(".json")) or not os.path.isfile(path):
        return False
    text = app_model.read_text(path)
    hit = next((m for m in profile_upgrades.CONFIRM.finditer(text)
                if ((m.group(1) or "").strip() or "a fact marked unconfirmed") == t.get("what")),
               None)
    if hit is None:
        return False
    # Inside a quoted string or a comment, the words alone, with nothing that could end it.
    safe = re.sub(r"[\\\"'\n\r]", " ", answer).strip()
    if not safe:
        return False
    new = text[:hit.start()] + safe + text[hit.end():]
    try:
        if path.endswith(".py"):
            compile(new, path, "exec")
        else:
            json.loads(new)
    except (SyntaxError, ValueError):
        return False
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    return True


def _needs_unanswer(r: Run) -> dict:
    path = _fact_path(r.target)
    text = app_model.read_text(path)
    at, answer, mark = int(r.value.get("at") or 0), str(r.value.get("answer") or ""), \
        str(r.value.get("mark") or "")
    if not answer or text[at:at + len(answer)] != answer:
        raise Refused("Your profile has changed there since: say so in a chat.")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text[:at] + mark + text[at + len(answer):])
    return {"note": "The question is back.",
            "undo": {"action": "needs.answer", "target": dict(r.target),
                     "value": {"text": answer}}}


# ---- setup, from the page


def _setup_fields(step: str) -> set:
    import app_setup
    if step == "history":
        return {"text", "done"}
    spec = next((s for s in app_setup.STEPS if s["id"] == step), None)
    return {f["key"] for f in (spec or {}).get("fields", ())}


def _clean(value, depth: int = 0):
    """An answer as the page sent it, kept to plain values of a sane size."""
    if isinstance(value, str):
        return value.strip()[:2000]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, list) and depth < 2:
        return [_clean(v, depth + 1) for v in value[:30]]
    if isinstance(value, dict) and depth < 2:
        return {str(k)[:40]: _clean(v, depth + 1) for k, v in list(value.items())[:12]}
    return str(value)[:2000]


def _restore_undo(r: Run, before) -> dict:
    return {"action": "setup.restore", "target": dict(r.target), "value": {"before": before}}


def _setup_answer(r: Run) -> dict:
    import app_setup
    step = r.target["step"]
    a = app_setup.answers()
    before = a.get(step)
    if step == "history":
        h = dict(before or {})
        jobs = list(h.get("jobs") or [])
        text = str(r.value.get("text") or "").strip()
        if not text and not r.value.get("done"):
            raise Refused("Nothing was written.")
        if text:
            jobs.append(_clean(text))
        h.update(jobs=jobs, at=app_model.stamp(r.at))
        if r.value.get("done"):
            h["done"] = True
        a["history"] = h
    elif step == "resume":
        # The resume step answered as a field: the words go into the copy and leave the
        # page's database, as setup.resume does (LEGACY_AUDIT W7).
        text = r.value.get("text") or r.value.get("resume")
        if isinstance(text, str) and text.strip() and not r.value.get("asset"):
            r.value = dict(r.value, text=text)
        return _setup_resume(r)
    else:
        keys = _setup_fields(step)
        got = {k: _clean(v) for k, v in r.value.items() if k in keys}
        if not got or all(v in ("", [], None, {}) for v in got.values()):
            raise Refused("No answer was given.")
        a[step] = dict(got, at=app_model.stamp(r.at))
    app_setup.save_answers(a)
    return {"note": "Saved.", "undo": _restore_undo(r, before)}


def _setup_restore(r: Run) -> dict:
    import app_setup
    step = r.target["step"]
    a = app_setup.answers()
    now = a.get(step)
    before = r.value.get("before")
    if before is None:
        a.pop(step, None)
    else:
        a[step] = before
    app_setup.save_answers(a)
    return {"note": "Back as it was.", "undo": _restore_undo(r, now)}


def _setup_resume(r: Run) -> dict:
    import app_setup
    a = app_setup.answers()
    before = a.get("resume")
    asset = r.words("asset")
    text = str(r.value.get("text") or "")
    at = app_model.stamp(r.at)
    if asset:
        aid = page_db.safe_id(asset)
        name = os.path.basename(r.words("name")[:120]) or "resume"
        folder = ASSETS_DIR[0]
        hits = [f for f in (os.listdir(folder) if folder and os.path.isdir(folder) else [])
                if f.split(".")[0] == aid]
        if hits:
            # Fetched into --assets by this chat (Artifact read, path = the id), as a
            # LinkedIn download's files are: saved in the copy now, and off the page.
            import shutil
            ext = os.path.splitext(name)[1].lower() or os.path.splitext(hits[0])[1].lower()
            if ext not in (".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt"):
                raise Refused("A resume is a PDF or a Word file.")
            stamp_ = r.at.strftime("%Y%m%d-%H%M%S")
            dest = person.state("documents", "cv", f"resume_added_{stamp_}{ext}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(folder, hits[0]), dest)
            a["resume"] = {"source": "asset", "file": app_model.rel(dest), "name": name, "at": at}
            app_setup.save_answers(a)
            return {"note": "Got it. I'll read it now.", "undo": _restore_undo(r, before),
                    "remove_assets": [aid]}
        a["resume"] = {"source": "asset", "asset": aid, "name": name, "at": at}
        note = "Got it. I'll read it now."
    elif text.strip():
        stamp_ = r.at.strftime("%Y%m%d-%H%M%S")
        path = person.state("documents", "cv", f"resume_pasted_{stamp_}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.strip() + "\n")
        a["resume"] = {"source": "pasted", "file": app_model.rel(path), "at": at}
        note = "Got it. I'll read it now."
        # The words are in their own copy now: the page's database keeps none of them.
        if r.version is not None and not str(r.act.get("claimed_by") or ""):
            raw = r.act.get("value")
            gone = ({"text": {"__delete__": True}} if isinstance(raw, dict) and "text" in raw
                    and "answers" not in raw else {"__delete__": True})
            r.w.add("update", "actions", r.aid, {"value": gone}, if_version=r.version)
    else:
        raise Refused("Add the file, or paste it.")
    app_setup.save_answers(a)
    return {"note": note, "undo": _restore_undo(r, before)}


def _setup_build(r: Run) -> dict:
    import app_setup
    a = app_setup.answers()
    before = a.get("resume")
    a["resume"] = {"source": "build", "at": app_model.stamp(r.at)}
    app_setup.save_answers(a)
    return {"note": "We'll build it together, one job at a time, newest first.",
            "undo": _restore_undo(r, before)}


def _setup_skip(r: Run) -> dict:
    import app_setup
    step = r.target["step"]
    a = app_setup.answers()
    before = a.get(step)
    a[step] = {"skipped": True, "at": app_model.stamp(r.at)}
    app_setup.save_answers(a)
    return {"note": "Skipped: I'll use a sensible default and you can change it later.",
            "undo": _restore_undo(r, before)}


def _setup_done(r: Run) -> dict:
    import app_setup
    key = r.target.get("key")
    if key == "job-sites":
        got = app_setup.check_job_sites(r.day.isoformat())
        if got.get("blocked"):
            raise Refused("This chat still can't reach " + ", ".join(got["blocked"][:3])
                          + ". It can take a minute after the change: try Done again shortly.")
        return {"note": "This chat reaches the job sites now.", "undo": None}
    if key == "copy":
        return {"note": "Open a chat on your new copy and say \"set me up\". This page "
                        "carries on there.", "undo": None}
    if key == "private":
        kind = app_setup.repo_kind()
        if kind["kind"] != "private":
            raise Refused("GitHub still shows your copy as public.")
        return {"note": "Your copy is private now.", "undo": None}
    if app_setup.set_up():
        a = app_setup.answers()
        a.setdefault("outside", {})[key] = app_model.stamp(r.at)
        app_setup.save_answers(a)
    return {"note": "Noted, thank you.", "undo": None}


def _setup_make_copy(r: Run) -> dict:
    import app_setup
    got = app_setup.make_copy(r.words("name") or app_setup.COPY_NAME)
    if not got["ok"]:
        raise Refused(got["say"] + " Make it on GitHub instead: the steps are on this card.")
    return {"note": got["say"], "undo": None}


def _app_update_now(r: Run) -> dict:
    sha = str(r.target.get("sha") or "")
    wid = "update~" + sha[:12]
    have = (r.db.get("work") or {}).get(wid)
    if have and str(have["data"].get("status") or "") not in page_db.FINISHED:
        return {"note": "Already on its way.", "undo": None}
    r.w.add("set", "work", wid, {
        "kind": "update", "title": "Updating the app", "to": "either",
        "args": {"sha": sha, "migration": bool(r.target.get("migration"))},
        "asked_at": app_model.stamp(r.at), "priority": 1, "status": "queued",
        "stages": page_db.progress("update")["stages"], "stage": 0},
        if_version=have["version"] if have else None)
    return {"note": "Queued: Claude updates it next.",
            "undo": {"action": "work.stop", "target": {"kind": "work", "id": wid}}}


def _git(*args) -> tuple[int, str]:
    import subprocess
    # The search's own history: the state root, which is the repo itself except in a test.
    r = subprocess.run(["git", "-C", person.state(), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _upgrade_undo(r: Run) -> dict:
    sha = str(r.target.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Refused("That change cannot be found.")
    code, out = _git("status", "--porcelain", "--untracked-files=no")
    if code or out.strip():
        raise Refused("Your copy has changes not saved yet: try again once they are.")
    code, out = _git("revert", "--no-edit", sha)
    if code:
        _git("revert", "--abort")
        raise Refused("It could not be taken back by itself: say so in a chat.")
    code, new = _git("rev-parse", "HEAD")
    return {"note": "Taken back.",
            "undo": {"action": "upgrade.undo", "target": {"kind": "upgrade",
                                                          "sha": new.strip()}}}


HANDLERS = {
    "setup.answer": _setup_answer, "setup.resume": _setup_resume,
    "setup.build_resume": _setup_build, "setup.skip": _setup_skip,
    "setup.restore": _setup_restore, "setup.done": _setup_done,
    "setup.make_copy": _setup_make_copy, "app.update_now": _app_update_now,
    "upgrade.undo": _upgrade_undo,
    "job.dismiss": _job_dismiss, "job.bring_back": _job_bring_back, "job.draft": _job_draft,
    "job.applied": _job_applied, "job.not_applied": _job_not_applied,
    "ready.applied": _ready_applied,
    "ready.not_applied": _ready_not_applied, "ready.not_applying": _ready_not_applying,
    "ready.reopen": _ready_reopen, "msg.sent": _msg_sent, "msg.unsent": _msg_unsent,
    "msg.received": _msg_received, "msg.unreceived": _msg_unreceived,
    "outcome.interview": lambda r: _outcome(r, "interview"),
    "outcome.offer": lambda r: _outcome(r, "offer"),
    "outcome.rejected": lambda r: _outcome(r, "rejected"),
    "outcome.withdrawn": lambda r: _outcome(r, "withdrawn"),
    "outcome.no_response": lambda r: _outcome(r, "no_response"),
    "outcome.undo": _outcome_undo,
    "interview.rework": _rework, "interview.unrework": _unrework,
    "profile.pasted": _profile_pasted, "process.register": _process_register,
    "ready.sent_to_contact": _ready_sent_to_contact,
    "job.add": _job_add, "job.keep": _job_keep, "job.unkeep": lambda r: _job_keep(r, keep=False),
    "person.call_booked": _call_booked, "referral.agreed": _referral_agreed,
    "referral.ended": _referral_ended, "due.snooze": _due_snooze,
    "msg.skip": _msg_skip, "msg.unskip": _msg_unskip, "person.stop": _person_stop,
    "person.status": _person_status,
    "consent.yes": lambda r: _consent(r, "yes"), "consent.no": lambda r: _consent(r, "no"),
    "setting.set": _setting_set, "needs.answer": _needs_answer,
    "needs.unanswer": _needs_unanswer,
    "suggest.dismiss": _suggest_dismiss, "suggest.undismiss": _suggest_undismiss,
    "due.done": _due_done, "due.undo": _due_undo, "tweak.undo": _tweak_undo,
    "tweak.offer": _tweak_offer, "tweak.offer_undo": _tweak_offer_undo, "hint.seen": _hint_seen,
    "work.stop": _work_stop, "work.resume": lambda r: _work_stop(r, stop=False),
    "export.requested": _export_requested, "export.unrequested": _export_unrequested,
    "export.take": _export_take, "reader.checked": _reader_checked,
    "reading.done": _reading_done,
    "learned.retire": _learned_retire, "learned.unretire": lambda r: _learned_retire(r, False),
    "tip.seen": _tip_seen, "requests.withdrawn": _withdrawn,
    "requests.unwithdrawn": _unwithdrawn, "search.set": _search_set,
    "search.unset": _search_unset, "rule.lift": _rule_lift, "rule.restore": _rule_restore,
    "brief.move": _brief_move, "brief.pause": _brief_pause, "brief.resume": _brief_resume,
    "brief.off": lambda r: _brief_switch(r, "off"), "brief.on": lambda r: _brief_switch(r, "on"),
}
assert set(HANDLERS) | {"undo"} == set(ACTIONS)
# The two answers nothing on the page takes back, and why: said in a chat instead.
NO_UNDO = {
    "outcome.undo": "it is itself the taking back of an outcome",
    "interview.unrework": "it is itself the taking back of an answer kept to work on",
    "process.register": "a hiring process registered is a tracker row and its folder that "
                        "every reader goes by; a chat takes it back, with the person",
    "profile.pasted": "a profile read is what their note rests on, and its words are gone from "
                      "the page; a chat takes a reading back, with the person",
    "export.take": "a download taken is history imported into the log; taking it back is a "
                   "chat's, with the person",
    "reader.checked": "a check is a check: the next one says what is true then",
    "reading.done": "a reading is kept as read; a later one replaces it",
    "tip.seen": "a tip seen is seen: nothing about the search changed",
    "setup.done": "it only checks again what the person did outside the page",
    "hint.seen": "a hint seen is seen: nothing about the search changed",
    "tweak.offer_undo": "it is itself the taking back of an answer",
    "setup.make_copy": "a repository is never deleted by the app; the person deletes it on GitHub",
}
# Actions that change only the page's own list, so the repo is not read again after them.
DB_ONLY = {"job.add", "job.draft", "consent.yes", "consent.no", "work.stop", "work.resume",
           "app.update_now", "setup.make_copy", "tweak.undo"}
# What may be applied on the app itself or a public copy: nothing that writes about the
# person. The rest waits, unreceipted, for their private copy.
PUBLIC_SAFE = {"setup.make_copy", "work.stop", "work.resume"}

# ------------------------------------------------------------------ the run


def _receipt(result: str, note: str, by: str, now: dt.datetime, aid: str, act: dict,
             undo=None, guard_after: str = "") -> dict:
    out = {"applied_at": app_model.stamp(now), "by": by, "result": result, "note": note,
           "action": str(act.get("action") or ""), "item": str(act.get("item") or "")}
    if result == "ok":
        out["undo"] = undo
        out["guard"] = guard_after
    return out


def _item_id(item: str) -> str:
    """The model's own id for an item: a setting is setting-<key> (CONTRACT 6.13); the page
    named it setting:<key> during the build, read as the same item."""
    return "setting-" + item[len("setting:"):] if item.startswith("setting:") else item


def _target_of(act: dict, index: Index) -> dict | None:
    name = str(act.get("action") or "")
    kinds = ACTIONS.get(name, ((),))[0]
    item = _item_id(str(act.get("item") or ""))
    if "work" in kinds:
        return {"kind": "work", "id": item}
    if "hint" in kinds:
        return {"kind": "hint", "id": item}
    if "new_job" in kinds and item in ("job-new", "jobs-add"):
        return {"kind": "new_job", "id": item}
    return index.find(item, kinds, str(act.get("rev_seen") or ""))


def _logged_already(act: dict, zone: str, now: dt.datetime) -> str:
    """For "I sent it" on a message no longer on the page because it went (logged in a
    chat, or from another device): the day those words were logged, so the receipt says
    so instead of "look again"."""
    if str(act.get("action") or "") != "msg.sent":
        return ""
    item = str(act.get("item") or "")
    cid = item[4:] if item.startswith("msg-") else item[7:] if item.startswith("q-sent-") else ""
    text = str(value_of(act).get("text") or "").strip()
    if not cid or not text:
        return ""
    at = app_model.parse_time(act.get("at")) or now
    try:
        return _already_sent(cid, _state().split_subject(text)[1].strip(),
                             app_model.local_day(at, zone))
    except Exception:  # noqa: BLE001
        return ""


def _seen_current(act: dict, target: dict, index: "Index") -> bool:
    """Was the item as the person saw it? Its own rev, which every item and every button on
    a card's alert or suggestion carries (CONTRACT 6.13), and nothing else: the page's
    top-level rev is never compared with an item's."""
    seen = str(act.get("rev_seen") or "")
    return bool(seen) and seen == target.get("rev")


def _one(aid: str, act: dict, index: Index, db: dict, w, chat: str, zone: str,
         now: dt.datetime, done: dict, names, version=None) -> dict:
    name = str(act.get("action") or "")
    if name not in ACTIONS:
        return _receipt("conflict", "The app does not know that action yet.", chat, now, aid, act)
    if name == "undo":
        value = act.get("value") if isinstance(act.get("value"), dict) else {}
        first = str(act.get("undoes") or value.get("undoes") or "")
        prior = done.get(first) or ((db.get("receipts") or {}).get(first) or {}).get("data")
        undo = (prior or {}).get("undo")
        if not prior or prior.get("result") != "ok" or not undo:
            return _receipt("conflict", "There is nothing to undo there: say so in a chat.",
                            chat, now, aid, act)
        target = dict(undo.get("target") or {})
        if prior.get("guard") and guard(target) != prior["guard"]:
            return _receipt("stale", "It has changed since: say what you want in a chat.",
                            chat, now, aid, act)
        shown = act
        act = dict(act, action=undo["action"], value=undo.get("value") or {})
        name = undo["action"]
    else:
        shown = act
        target = _target_of(act, index)
        if target is None:
            went = _logged_already(act, zone, now)
            if went:
                return _receipt("conflict", f"Already logged on {_weekday(went)}.", chat, now,
                                aid, act)
            return _receipt("stale", "That is no longer on the page: look again.", chat, now,
                            aid, act)
        kinds = ACTIONS[name][0]
        if target.get("kind") not in kinds:
            return _receipt("conflict", "That cannot be done to that.", chat, now, aid, act)
        if target.get("kind") not in ("work", "hint", "linkedin", "new_job") and \
                not _seen_current(act, target, index):
            return _receipt("stale", "It changed since you saw it: look again.", chat, now,
                            aid, act)
    run = Run(aid, act, target, db, w, chat, zone, now, version)
    try:
        got = HANDLERS[name](run)
    except NeedsAssets:
        raise
    except Refused as e:
        return _receipt("conflict", app_model.scrub(str(e), names), chat, now, aid, shown)
    except (ValueError, OSError) as e:
        return _receipt("conflict", "It could not be done: " + app_model.scrub(str(e), names),
                        chat, now, aid, shown)
    if name not in DB_ONLY:
        index.changed()
    undo = got.get("undo")
    after = got.get("target_after") or (undo or {}).get("target") or target
    out = _receipt("ok", got["note"], chat, now, aid, shown, undo=undo,
                   guard_after=guard(after) if after.get("kind") != "work" else "")
    for k in ("counts", "remove_assets", "lines", "why"):
        if k in got:
            out[k] = got[k]
    if not undo:
        # No inverse here, said plainly rather than left blank (UX audit, 2026-10-25). An
        # inverse that exists has no time limit: it runs while the guard still holds.
        out["undo_note"] = "Only a chat can take this back: say so in a chat."
    if shown is not act:
        out["ran"] = name
    return out


def _claimed_by_other(act: dict, chat: str, now: dt.datetime) -> bool:
    by = str(act.get("claimed_by") or "")
    until = app_model.parse_time(act.get("claimed_until"))
    return bool(by) and by != chat and until is not None and until > now


def pending(db: dict, chat: str, now: dt.datetime) -> list[tuple[str, dict, int | None]]:
    """(id, action, version) of every action with no receipt, oldest first, leaving out
    those another chat has claimed and is still within its claim."""
    receipts = db.get("receipts") or {}
    out = []
    for aid, doc in (db.get("actions") or {}).items():
        if aid in receipts or _claimed_by_other(doc["data"], chat, now):
            continue
        at = app_model.parse_time(doc["data"].get("at"))
        out.append((at.timestamp() if at else 0.0, aid, doc))
    return [(aid, doc["data"], doc["version"]) for _, aid, doc in sorted(out)]


def claim(dump_dir: str, chat: str, now: dt.datetime, out_dir: str) -> dict:
    """The claim on every pending action, pinned to the version read, as one batch."""
    db = page_db.load(dump_dir)
    w = page_db.Writes(out_dir)
    todo = pending(db, chat, now)
    unpinned = []
    until = app_model.stamp(now + dt.timedelta(seconds=CLAIM_S))
    for aid, act, version in todo:
        if version is None:
            unpinned.append(aid)
            continue
        data = {"claimed_by": chat, "claimed_until": until}
        resume_answer = act.get("action") == "setup.answer" and str(
            act.get("item") or "").endswith("setup-resume")
        words = value_of(act)
        if (act.get("action") in ("setup.resume", "msg.received", "reading.done",
                                  "profile.pasted")
                or resume_answer) and (words.get("text") or words.get("resume")
                                       or isinstance(act.get("value"), str)):
            # A pasted resume, or a contact's own words, leave the page's database with the
            # claim: the dump this chat applies from has kept them, and the repo is where
            # they belong (their words are never kept on the page).
            raw = act.get("value")
            data["value"] = ({"text": {"__delete__": True}}
                             if isinstance(raw, dict) and "text" in raw and "answers" not in raw
                             else {"__delete__": True})
        w.add("update", "actions", aid, data, if_version=version)
    return {"claimed": [a for a, _, v in todo if v is not None], "unpinned": unpinned,
            "batches": w.save("claim")}


def apply_dir(dump_dir: str, chat: str = "chat", now: dt.datetime | None = None,
              out_dir: str | None = None, assets_dir: str | None = None) -> dict:
    """Apply every pending action in a dump; the receipts (and any work items) to write back.
    An action naming page assets not fetched into `assets_dir` gets no receipt: `fetch`
    lists them, to fetch and apply again."""
    now = now or dt.datetime.now(dt.timezone.utc)
    ASSETS_DIR[0] = assets_dir
    out_dir = out_dir or os.path.join(dump_dir, "out")
    db = page_db.load(dump_dir)
    ledger_path = os.path.join(dump_dir, LEDGER)
    ledger = app_model.read_json(ledger_path, {}) or {}
    w = page_db.Writes(out_dir)
    try:
        zone = person.home_zone_named(person.directory()) or "UTC"
    except person.NoProfile:
        zone = "UTC"
    safe_only = None
    today = app_model.local_day(now, zone)
    import app_alerts
    index = Index(today, now, shown=app_alerts.shown_in(db.get("view") or {}))
    names = None
    summary: dict = {"ok": [], "stale": [], "conflict": [], "again": []}
    done: dict = {}
    for aid, act, version in pending(db, chat, now):
        if str(act.get("action") or "") not in PUBLIC_SAFE:
            if safe_only is None:
                import app_setup
                k = app_setup.repo_kind()["kind"]
                safe_only = k in ("app", "public", "none")
            if safe_only:
                summary.setdefault("waiting", []).append(aid)
                continue           # nothing about the person is written here: it waits
        if aid in ledger:
            receipt = ledger[aid]
            summary["again"].append(aid)
        else:
            if names is None:
                try:
                    names = app_model.Ctx(today, now).names
                except person.NoProfile:
                    names = app_model.Names([])
            try:
                receipt = _one(aid, act, index, db, w, chat, zone, now, done, names, version)
            except NeedsAssets as e:
                summary.setdefault("fetch", []).append({"action": aid, "assets": e.ids})
                continue
            ledger[aid] = receipt
            with open(ledger_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(ledger, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
            summary[receipt["result"]].append(aid)
        done[aid] = receipt
        w.add("set", "receipts", aid, receipt)
    _amend_reasons(db, done, ledger, ledger_path, w, chat, zone, now, summary)
    summary["batches"] = w.save("batch")
    summary["writes"] = len(w.entries)
    return summary


# An answer the page adds to an action already applied, under the same action id: the
# reason for Set aside, picked from the chips that show after the first tap (CONTRACT 6.11).
AMENDS = {"job.dismiss": "why"}


def _amend_reasons(db, done, ledger, ledger_path, w, chat, zone, now, summary) -> None:
    """A reason given after the ruling was made updates that ruling, never adds one."""
    for aid, doc in (db.get("actions") or {}).items():
        act = doc["data"]
        field = AMENDS.get(str(act.get("action") or ""))
        if not field:
            continue
        rec_doc = (db.get("receipts") or {}).get(aid)
        rec = done.get(aid) or (rec_doc or {}).get("data")
        if not rec or rec.get("result") != "ok":
            continue
        said = " ".join(str(value_of(act).get(field) or "").split())
        target = (rec.get("undo") or {}).get("target")
        if not said or said == rec.get(field) or not target:
            continue
        run = Run(aid, act, dict(target, kind="job"), db, w, chat, zone, now)
        try:
            got = _job_dismiss(run)
        except (Refused, ValueError, OSError):
            continue
        new = dict(rec, note=got["note"], **{field: said})
        ledger[aid] = new
        with open(ledger_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(ledger, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        w.add("set", "receipts", aid, new,
              if_version=rec_doc["version"] if rec_doc and aid not in done else None)
        summary.setdefault("amended", []).append(aid)
