#!/usr/bin/env python3
"""Every follow-up drafted by code first, then put through the gate a hand-written one gets.

What is owed comes from `open_actions.due_items` (both halves: contacts and applications), so
this never keeps a clock of its own. For each item it makes the draft the state files can
support and nothing more:

  an application nudge   followups.py's own text, to the recipient it found
  a networking nudge     a draft on the contact's row or in an earlier pack, else a nudge
                         (compose.nudge) whose new reason is a posting at their employer from
                         the newest saved round, said only to a reader allowed to hear the role
  anything else          a draft on the contact's row or in an earlier pack

Every draft then goes through `compose.validate` (the gate: a finding means code could not
make it cleanly, and it is listed as needs writing, with the finding as the reason) and
`compose.advise` (warnings, kept beside the draft for the rewrite). Nothing is claimed that
the thread or the profile does not hold: the only new fact code ever writes is a posting
the search found, named as it was posted.

A draft code cannot make is listed with why, and who can write it: "here" when the thread
holds what a writer needs (a reply: their message is in the log), "you" when it needs the
person (a nudge with nothing new to say, a recipient nobody has found).

    python3 tools/followup_drafts.py                     # everything due, each with its draft or why not
    python3 tools/followup_drafts.py --contact <id>      # one contact
    python3 tools/followup_drafts.py --company <name>    # one employer, both halves
    python3 tools/followup_drafts.py --json
    python3 tools/followup_drafts.py --pack              # also write documents/network/followup_pack_<today>.md
    python3 tools/followup_drafts.py context --due       # what a writer needs, for what code could not draft
    python3 tools/followup_drafts.py context <id>...
    python3 tools/followup_drafts.py check <drafts.json> [--pack]   # the gate, for drafts written by hand

`check` reads a JSON list of {"id": <contact id or app:...>, "text": "<the draft>"} (and
"kind" where it is not the usual one), runs validate, the restatement check against their
last message, and advise, and with --pack adds each draft the gate passes to today's pack.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person                                         # noqa: E402
import local_path  # noqa: E402
from company_key import key as company_key            # noqa: E402

PACK_DIR = ("documents", "network")
PACK_NAME = "followup_pack_%s.md"
ROUNDS = ("documents", "rounds")
# A posting worth naming in a nudge: one the search scored as worth a look.
POSTING_FIT = 60
# A run writes at most this many by hand; the rest wait in the pack for a chat with the person.
WRITE_HERE_MAX = 4
# Nudges are a few lines long; the pack keeps each in a fenced block under this marker so
# the next run can reuse a draft still right for an item still due.
# An application's id holds its employer's key, which can have a space in it ("app:kestrel
# mutual::..."): read up to " kind=", or its draft was never found again.
_MARK = re.compile(r"^<!-- draft id=(?P<id>.+?) kind=(?P<kind>\S+) source=(?P<source>\S+) -->$")
_FENCE = "```"


# ---------------------------------------------------------------- the gate

def _compose():
    import compose
    return compose


def gate(text: str, kind: str, name: str = "", title: str = "", company: str = "",
         contact: str = "", their_message: str = "",
         card_only: bool = False, today: str = "") -> tuple[list[str], list[str]]:
    """(findings, warnings) for a draft: compose.validate's findings, which stop it, and
    compose.advise's warnings, which go beside it for the rewrite. Given `contact`, their
    whole thread is read as of `today` (compose.thread_findings)."""
    compose = _compose()
    found = compose.validate(text, kind, name=name or None, title=title, contact=contact,
                             their_message=their_message or None, card_only=card_only,
                             today=today or None)
    warned = compose.advise(text, kind, name=name or None, title=title,
                            their=(company,) if company else (), company=company)
    return ([f"{v.rule}: {v.text}" for v in found],
            [f"{a.rule}: {a.text}" + (f" ({a.fix})" if getattr(a, "fix", "") else "")
             for a in warned])


def limit_of(kind: str) -> int:
    """The character limit the platform holds this kind of message to, or 0."""
    try:
        compose = _compose()
        k = compose._KIND_ALIASES.get(kind, kind)
        return int((compose.KIND_LIMITS.get(k) or {}).get("chars") or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------- what each item is

def message_kind(item: dict, contact: dict | None = None) -> str:
    """The compose kind a draft for this due item is checked as."""
    if item.get("half") == "application":
        return "message"
    k = item.get("kind") or ""
    if k in ("reply", "resume"):
        return "reply"
    import state
    channel = state.channel_of(contact or {}) if contact else ""
    if k == "nudge":
        return "message" if channel == "email" else "nudge"
    if k == "first_message":
        return "dm"
    if item.get("status") == "not_contacted":
        return {"inmail": "inmail", "email": "email"}.get(channel, "connection")
    return {"email": "email", "inmail": "inmail"}.get(channel, "dm")


def item_id(item: dict) -> str:
    if item.get("half") == "contact":
        return str(item.get("contact_id") or "")
    return "app:%s::%s" % (item.get("key") or "", _slug(item.get("who") or item.get("name") or ""))


def _slug(text) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:60]


def log_line(item: dict, kind: str) -> str:
    """The command that records it once it has gone, so the next follow-up is timed from it."""
    if item.get("half") == "application":
        company = (item.get("who") or "").split(" - ")[0]
        return ("When it goes: add \"followed up <the day>\" to that row's notes "
                "(/outcome followup %s does it)" % company)
    cid = item.get("contact_id") or "<contact_id>"
    if kind == "nudge":
        return "When it goes: python3 tools/network/state.py nudge %s --text-file <the words as sent>" % cid
    if item.get("status") == "not_contacted":
        return "When it goes: python3 tools/network/state.py sent %s --text-file <the words as sent>" % cid
    return "When it goes: python3 tools/network/state.py message %s --text-file <the words as sent>" % cid


# ---------------------------------------------------------------- earlier drafts

def pack_path(day: str) -> str:
    return person.state(*PACK_DIR, PACK_NAME % day)


def read_pack(path: str) -> dict:
    """{draft id: {"kind", "source", "text"}} from a pack this module wrote."""
    out: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out
    i = 0
    while i < len(lines):
        m = _MARK.match(lines[i].strip())
        if m and i + 1 < len(lines) and lines[i + 1].startswith(_FENCE):
            body = []
            j = i + 2
            while j < len(lines) and not lines[j].startswith(_FENCE):
                body.append(lines[j])
                j += 1
            day = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
            out[m.group("id")] = {"kind": m.group("kind"), "source": m.group("source"),
                                  "text": "\n".join(body).strip(),
                                  "day": day.group(1) if day else ""}
            i = j
        i += 1
    return out


def earlier_drafts(today: str) -> dict:
    """The drafts in today's pack, then the newest earlier pack's, today's winning."""
    folder = person.state(*PACK_DIR)
    packs = sorted(p for p in glob.glob(os.path.join(folder, PACK_NAME % "*"))
                   if os.path.basename(p)[len("followup_pack_"):-3] <= today)
    out: dict = {}
    for p in packs[-2:]:
        out.update(read_pack(p))
    return out


# ---------------------------------------------------------------- a new reason, from a round

def newest_round_rows() -> list[dict]:
    """The rows of the newest saved round (documents/rounds/<round>.json), or []."""
    files = glob.glob(person.state(*ROUNDS, "*.json"))
    if not files:
        return []

    def order(p):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            written = os.path.getmtime(p)
        except OSError:
            written = 0.0
        return tuple(int(n) for n in re.findall(r"\d+", name)), written

    try:
        with open(max(files, key=order), encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def posting_reason(contact: dict, since: str, rows: list[dict], tracker=()) -> dict:
    """A posting at their employer the search found after our last message, scored as worth a
    look and not already applied to, or {}."""
    k = company_key(contact.get("company"))
    if not k:
        return {}
    applied, by_key = _indexed(tracker or (), rows)
    best = {}
    for r in by_key.get(k, ()):
        if not str(r.get("title") or "").strip():
            continue
        fit = r.get("fit") if r.get("fit") is not None else r.get("priority")
        try:
            if float(fit or 0) < POSTING_FIT:
                continue
        except (TypeError, ValueError):
            continue
        seen = str(r.get("first_seen") or r.get("date") or "")[:10]
        if not seen or (since and seen <= since):
            continue
        if (k, _slug(_clean_title(r.get("title")))) in applied:
            continue
        if not best or float(fit) > float(best.get("fit") or best.get("priority") or 0):
            best = r
    return best


# What every contact's look at the postings shares: the roles applied to and the postings by
# employer, made once a run, not once a contact (on a large invented state, most of a
# Windows brief's two seconds, 2026-10-25). Kept while the same two lists are passed.
_INDEX: list = [None, None, None]


def _indexed(tracker, rows) -> tuple:
    if _INDEX[0] is not tracker or _INDEX[1] is not rows:
        applied = {(company_key(r.get("company")), _slug(_clean_title(r.get("role"))))
                   for r in tracker}
        by_key: dict = {}
        for r in rows:
            by_key.setdefault(company_key(r.get("company")), []).append(r)
        _INDEX[:] = [tracker, rows, (applied, by_key)]
    return _INDEX[2]


def _clean_title(title: str) -> str:
    t = re.split(r"\s+[-|(]\s*", str(title or "").strip(), maxsplit=1)[0]
    return re.sub(r"\s+", " ", t).strip(" ,.")


def nudge_from_posting(contact: dict, posting: dict) -> str:
    """A nudge whose new reason is the posting. Raises what compose.nudge raises."""
    compose = _compose()
    company = str(contact.get("company") or posting.get("company") or "").strip()
    title = _clean_title(posting.get("title"))
    reader = compose.reader_type(contact.get("title") or "")
    reason = "%s has since posted a %s role, which is close to the work I do" % (company, title)
    close = compose.phrase("ask", reader, key=str(contact.get("contact_id") or ""))
    return compose.nudge(contact.get("name") or "", reason, close=close or None,
                         their=(company,), thread=str(contact.get("contact_id") or "") or None)


# ---------------------------------------------------------------- drafting

def _new(status, kind="", text="", why="", who="", source="", warnings=(), findings=()):
    return {"status": status, "kind": kind, "text": text, "why": why, "who": who,
            "source": source, "warnings": list(warnings), "findings": list(findings),
            "chars": len(text or ""), "limit": limit_of(kind) if kind else 0}


def draft(item: dict, contacts_by_id: dict, threads_index: dict, tracker, earlier: dict,
          rows: list[dict], today: str = "") -> dict:
    """The draft for one due item: {"status": ready | check | write | none, ...}.

    ready  made by code and clean; check  made by code, with advise's warnings to rewrite on;
    write  code could not make it cleanly (`why`, and `who` writes it: here or you);
    none   nothing to write (an action: send a file, prep a call, withdraw a request)."""
    if item.get("held") or item.get("quiet") or item.get("old"):
        return _new("none", why="held: " + "; ".join(item.get("held") or ["not due"]))
    if item.get("half") == "application":
        if item.get("kind") == "interview":
            return _new("none", why=item.get("what") or "")
        if not item.get("ready"):
            return _new("write", kind="message", who="you",
                        why=item.get("text") or item.get("to") or "no recipient on file")
        name = ""
        m = re.match(r"Hi ([^,]+),", item.get("text") or "")
        if m and m.group(1) != "[name]":
            name = m.group(1)
        company = (item.get("who") or "").split(" - ")[0]
        return _checked(item["text"], "message", name=name, company=company, source="code", today=today)
    contact = contacts_by_id.get(item.get("contact_id") or "", {})
    kind = message_kind(item, contact)
    name = contact.get("name") or item.get("name") or ""
    title = contact.get("title") or ""
    company = contact.get("company") or ""
    cid = item.get("contact_id") or ""
    if item.get("kind") == "request_pending":
        return _new("none", why="nobody accepted: withdraw it on LinkedIn")
    if item.get("kind") == "resume":
        return _new("none", why=item.get("what") or "")
    if item.get("what", "").startswith("UNCONFIRMED"):
        return _new("none", why="did this go? Ask before anything else is sent")
    msgs = threads_index.get(cid, ())
    their = _their_last(msgs)
    stored = (item.get("text") or "").strip()
    card_only = False
    if not stored and kind in ("connection", "inmail", "dm", "email"):
        # A first note queued by /network (documents/network/<id>/draft.md): checked as it
        # stands, and one still waiting on a read of their profile is the person's to unlock.
        queued, card_only, waits = _queued_note(cid)
        if waits:
            return _new("write", kind=kind, who="you", source="stored",
                        why="the note waits on a read of their profile (/network)")
        stored = queued
    old = earlier.get(cid)
    # An earlier pack's draft answers the thread as it stood that day: once anything has
    # been logged since, it answers a conversation that has moved on.
    if old and any(str(r.get("date") or "")[:10] > (old.get("day") or "") for r in msgs):
        old = None
    refused = None
    for text, source in ((stored, "stored"), ((old or {}).get("text") if old and
                                              old.get("kind") == kind else "", "pack")):
        if text:
            got = _checked(text, kind, name=name, title=title, company=company, contact=cid,
                           their_message=their, source=source,
                           card_only=card_only and source == "stored", today=today)
            if got["status"] != "write":
                return got
            refused = refused or got        # kept: a draft to rewrite on its findings
    if item.get("kind") == "reply":
        return refused or _new("write", kind=kind, who="here",
                               why="a reply answers what they said, which is in the log")
    if item.get("kind") == "first_message":
        return refused or _new("write", kind=kind, who="you",
                    why="they accepted and nothing has been said: a first message is written "
                        "from what was read about them (/network)")
    if item.get("kind") != "nudge":
        return refused or _new("none", why=item.get("what") or "")
    # A nudge needs something new to answer: a posting the search found at their employer,
    # said only to a reader allowed to hear the role (compose.SAY_THE_ROLE).
    compose = _compose()
    reader = compose.reader_type(title)
    since = item.get("since") or ""
    posting = posting_reason(contact, since, rows, tracker) if compose.SAY_THE_ROLE.get(reader) else {}
    if posting:
        try:
            text = nudge_from_posting(contact, posting)
        except ValueError as e:
            return _new("write", kind=kind, who="you",
                        why="the nudge about %s's %s posting did not pass: %s"
                            % (company, _clean_title(posting.get("title")), _one_line(e)))
        got = _checked(text, kind, name=name, title=title, company=company, contact=cid,
                       their_message=their, source="code", today=today)
        if got["status"] != "write":
            got["why"] = "new reason: %s posted %s" % (company, _clean_title(posting.get("title")))
        return got
    offer = their_offer(msgs)
    last = compose.unanswered_ours(msgs)
    if offer is not None and last is not None:
        # Their offer to refer is the reason to answer, and the person's own note since is
        # what this follows up: never written as though the offer were the last word.
        try:
            # Dated the day it is drafted for (`--today`), never the computer's: run for another
            # day it said "from August last year" (the date check, 2026-10-29).
            text = compose.follow_up(name, msgs, OFFER_REASON % (company or "your company"),
                                     close=OFFER_CLOSE, today=today or None)
        except ValueError as e:
            return refused or _new("write", kind=kind, who="you",
                                   why="the follow-up on their offer did not pass: " + _one_line(e))
        got = _checked(text, kind, name=name, title=title, company=company, contact=cid,
                       their_message=their, source="code", today=today)
        if got["status"] != "write":
            got["why"] = "follows up on your note of %s, on their offer of %s" % (
                last.get("date"), offer.get("date"))
        return got
    return refused or _new("write", kind=kind, who="you",
                why="nothing new to say on file: a nudge needs a new reason (a role they "
                    "posted, news at %s, something you have done since)" % (company or "their employer"))


# Their own offer to refer, as the one thing a follow-up gives them to answer.
OFFER_REASON = ("in your last message you offered to refer me if a role came up at %s, and I'd "
                "still be glad of that")
OFFER_CLOSE = "If one does, would it be all right to send you the link?"


def their_offer(rows) -> dict | None:
    """Their latest message that offered to refer the person (reply.classify reads it as
    `referral_offered`, or it was logged so), or None."""
    import reply as reply_mod
    import state
    for r in reversed(list(rows or ())):
        if not state.said_something(r):
            continue
        if str(r.get("scenario") or "").strip() == "referral_offered":
            return r
        text = str(r.get("full_text") or "").strip()
        if text:
            try:
                if reply_mod.classify(text, [])["scenario"] == "referral_offered":
                    return r
            except Exception:  # noqa: BLE001  a message the classifier cannot read offers nothing
                continue
    return None


def _one_line(e) -> str:
    return " ".join(str(e).split())[:200]


def _queued_note(cid: str) -> tuple[str, bool, bool]:
    """(the note in documents/network/<id>/draft.md, whether it is card-only, whether it
    still waits on a read), or ("", False, False) when none is queued."""
    try:
        import reading
        with open(reading.draft_path(cid), encoding="utf-8") as fh:
            raw = fh.read()
        return (reading.note_body(raw).strip(), reading.card_only_draft(cid),
                reading.waits_on_read(cid))
    except (ImportError, OSError, ValueError):
        return "", False, False


def _checked(text, kind, name="", title="", company="", contact="", their_message="",
             source="code", card_only=False, today="") -> dict:
    try:
        findings, warnings = gate(text, kind, name=name, title=title, company=company,
                                  contact=contact, their_message=their_message,
                                  card_only=card_only, today=today)
    except ValueError as e:                 # a reaction waiting, an unknown kind
        return _new("write", kind=kind, who="you", why=_one_line(e), source=source)
    if findings:
        return _new("write", kind=kind, who="here", source=source, findings=findings,
                    text=text, why="the gate refused it: " + "; ".join(findings)[:300])
    return _new("check" if warnings else "ready", kind=kind, text=text, source=source,
                warnings=warnings)


def _their_last(rows) -> str:
    import state
    for r in reversed(list(rows or ())):
        if state._direction(r) == "in" and state.said_something(r):
            return str(r.get("full_text") or r.get("summary") or "")
    return ""


class FoldersOnce:
    """Each application's folder, found once a run instead of once a call.

    `docpaths.app_folder` reads the whole tracker to find a row's abbreviation every time it
    is asked, and the due list, the campaign chats and the counts ask it for every row: on
    a large tracker that was most of the brief's time. Within one run the abbreviations do
    not change (the upkeep writes a status, never a file name), so the lookup is made once
    from one read of the tracker, by the same rule, and put back afterwards."""

    def __enter__(self):
        import csv_store
        import docpaths
        self.mod, self.saved = docpaths, docpaths._abbr_on_file
        try:
            rows = csv_store.dict_rows(person.state("job_search_tracker.csv"), refuse=False)
        except OSError:
            rows = []
        rx, table = docpaths.resume_name_rx(), {}
        for r in rows:                       # later rows win, as the reversed scan finds them
            m = rx.search(r.get("cv_file") or "")
            if m:
                table[(company_key(r.get("company")),
                       docpaths.slug("x", r.get("role") or "x"))] = m.group(1)

        def lookup(company, role):
            return table.get((company_key(company), docpaths.slug("x", role or "x")), "")

        docpaths._abbr_on_file = lookup
        return self

    def __exit__(self, *exc):
        self.mod._abbr_on_file = self.saved
        return False


def load(today: str):
    """(due items, contacts, threads, tracker), as open_actions reads them."""
    import open_actions
    from network import state
    contacts, threads = state.load_contacts(), state.load_threads()
    tracker = open_actions._tracker()
    items = open_actions.due_items(contacts, threads, tracker, state.as_date(today))
    return items, contacts, threads, tracker


def drafts(items, contacts, threads, tracker, today: str) -> list[dict]:
    """Each due item with its "draft", most urgent first (open_actions' order)."""
    import open_actions
    from network import state
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    index = state.by_contact(threads) if threads else {}
    earlier = earlier_drafts(today)
    rows = newest_round_rows()
    out = []
    for i in sorted(items, key=open_actions._urgency):
        i = dict(i)
        i["id"] = item_id(i)
        i["draft"] = draft(i, by_id, index, tracker, earlier, rows, today=today)
        out.append(i)
    return out


# ---------------------------------------------------------------- the pack

def _title(item: dict, contacts_by_id: dict) -> str:
    if item.get("half") == "contact":
        c = contacts_by_id.get(item.get("contact_id") or "", {})
        return ", ".join(x for x in (c.get("name") or item.get("name"), c.get("company")) if x)
    return item.get("who") or item.get("name") or ""


def _what(item: dict) -> str:
    late = item.get("late") or 0
    when = "%d days late" % late if late > 0 else "due today"
    if item.get("half") == "application":
        return "%s, %s" % (item.get("what") or "follow-up", when)
    return "%s, %s" % ({"reply": "reply owed", "nudge": "nudge", "first_message": "first message",
                        "action_due": "your date"}.get(item.get("kind"), item.get("kind") or ""),
                       when)


def render_pack(today: str, got: list[dict], contacts) -> str:
    """The pack: each draft ready to paste with its check and the command that logs it,
    then what needs writing and why. "" when there is nothing to put in one."""
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    made = [i for i in got if i["draft"]["status"] in ("ready", "check")]
    todo = [i for i in got if i["draft"]["status"] == "write"]
    if not made and not todo:
        return ""
    out = ["# Follow-ups, %s" % today, "",
           "Drafted by code from the state files (tools/followup_drafts.py) and checked with "
           "the same gate as a draft written by hand: compose.validate, then compose.advise. "
           "Nothing here has been sent.", ""]
    for i in made:
        d = i["draft"]
        out.append("## " + _title(i, by_id))
        size = ("%d of %d characters" % (d["chars"], d["limit"]) if d["limit"]
                else "%d characters" % d["chars"])
        line = "%s. %s." % (_what(i)[:1].upper() + _what(i)[1:], size[:1].upper() + size[1:])
        if i.get("half") == "contact":
            zone = _time_for(i.get("contact_id"), contacts)
            if zone:
                line += " " + zone[0].upper() + zone[1:] + "."
        elif i.get("to"):
            line += " " + i["to"][0].upper() + i["to"][1:] + "."
        out.append(line)
        if d["warnings"]:
            out.append("Check before it goes: " + "; ".join(d["warnings"]))
        out += ["<!-- draft id=%s kind=%s source=%s -->" % (i["id"], d["kind"], d["source"]),
                _FENCE + "text", d["text"], _FENCE, log_line(i, d["kind"]), ""]
    if todo:
        out += ["## Needs writing", ""]
        for i in todo:
            d = i["draft"]
            who = "this chat can write it from the thread" if d["who"] == "here" else "needs you"
            out.append("- %s (%s): %s; %s." % (_title(i, by_id), _what(i), d["why"].rstrip("."), who))
        out.append("")
    return "\n".join(out)


def _time_for(cid, contacts) -> str:
    try:
        import reading
        return reading.time_for(cid, contacts) or ""
    except Exception:
        return ""


def write_pack(today: str, got: list[dict], contacts) -> str:
    """Write today's pack; the path, or "" when there was nothing to write."""
    text = render_pack(today, got, contacts)
    if not text:
        return ""
    path = pack_path(today)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------- for a writer

def context(ids, contacts, threads, today: str, got=None) -> str:
    """What a writer needs for each contact named: who reads it, their last words and ours,
    the scenario and the guidance for it, the limit, and any draft code made with what it
    flagged. Plain text, short."""
    import reply as reply_mod
    from network import state
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    index = state.by_contact(threads) if threads else {}
    compose = _compose()
    drafted = {i["id"]: i for i in (got or ())}
    out = []
    try:
        import learned
        rules = learned.brief("messages")
    except Exception:
        rules = ""
    if rules:
        rule_lines = [ln for ln in rules.splitlines() if ln.startswith("- ")][:6]
        if rule_lines:
            out += ["Your rules for messages (they outrank the defaults):"] + rule_lines + [""]
    for cid in ids:
        c = by_id.get(cid)
        if c is None:
            out.append("== %s: no such contact" % cid)
            continue
        rows = [r for r in index.get(cid, ()) if state._direction(r)]
        reader = compose.reader_type(c.get("title") or "")
        it = drafted.get(cid) or {}
        kind = (it.get("draft") or {}).get("kind") or ("reply" if rows and state.they_spoke_last(rows)
                                                       else "nudge")
        out.append("== %s (%s) [%s], %s, %s" % (c.get("name"), c.get("company"), cid,
                                                c.get("title") or "title not recorded",
                                                reader.replace("_", "-")))
        their = next((r for r in reversed(rows) if state._direction(r) == "in"
                      and state.said_something(r)), None)
        ours = next((r for r in reversed(rows) if state._direction(r) == "out"), None)
        if their is not None:
            out.append("their last (%s): %s" % (their.get("date"), _clip(their.get("full_text")
                                                                          or their.get("summary"))))
        if ours is not None:
            out.append("ours (%s): %s" % (ours.get("date"), _clip(ours.get("full_text")
                                                                  or ours.get("summary"))))
        waiting = compose.unanswered_ours(rows)
        if waiting is not None:
            on = state.as_date(waiting.get("date"))
            out.append("the last word is yours: your message of %s has no answer. Write a "
                       "follow-up to it (\"Following up on my note from %s\"): never tell them "
                       "again what it said, and never write as if you last spoke before %s"
                       % (waiting.get("date"), on.strftime("%B") if on else "then",
                          waiting.get("date")))
        try:
            read = reply_mod.classify("", rows, today)
            g = reply_mod.guidance(read, contact_id=cid)
            out.append("scenario: %s; move: %s" % (read["scenario"], g["move"]))
            out.append("length: about %d sentence(s); do not: %s"
                       % (g["target_sentences"], "; ".join(g["do_not"][:3])))
            if g.get("next_action"):
                out.append("owed outside the thread: " + g["next_action"])
        except Exception as e:  # a thread the classifier cannot read is still shown
            out.append("scenario: not read (%s)" % _one_line(e))
        lim = limit_of(kind)
        out.append("check as: %s%s" % (kind, ", at most %d characters" % lim if lim else ""))
        d = it.get("draft") or {}
        if d.get("text"):
            out.append("code's draft (%s): %s" % (d["status"], d["text"]))
        for f in (d.get("findings") or []) + (d.get("warnings") or []):
            out.append("  flagged: " + f)
        if d.get("why") and d.get("status") == "write":
            out.append("why code did not: " + d["why"])
        out.append("")
    if ids:
        out.append("Write each in the person's voice, claiming nothing the thread or the "
                   "profile does not hold, then: python3 tools/followup_drafts.py check "
                   "<file.json> --pack, with [{\"id\": \"<contact id>\", \"text\": \"...\"}]")
    return "\n".join(out).rstrip() + "\n"


def _clip(text, n: int = 400) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 3].rstrip() + "..."


def to_write_here(got) -> list[str]:
    """The contacts whose draft this chat can write or rewrite from the thread: a reply, a
    draft the gate refused, or one advise warned about."""
    return [i["contact_id"] for i in got if i.get("half") == "contact"
            and (i["draft"]["status"] == "check"
                 or (i["draft"]["status"] == "write" and i["draft"]["who"] == "here"))]


def check(entries, contacts, threads, today: str, got=None) -> list[dict]:
    """The gate for drafts written by hand: [{"id", "ok", "findings", "warnings", ...}]."""
    from network import state
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    index = state.by_contact(threads) if threads else {}
    drafted = {i["id"]: i for i in (got or ())}
    out = []
    for e in entries:
        iid = str(e.get("id") or e.get("contact_id") or "").strip()
        text = str(e.get("text") or "").strip()
        c = by_id.get(iid, {})
        it = drafted.get(iid) or {}
        kind = e.get("kind") or (it.get("draft") or {}).get("kind") or (
            "message" if iid.startswith("app:") else "reply")
        if not text:
            out.append({"id": iid, "ok": False, "kind": kind, "text": "",
                        "findings": ["no text"], "warnings": []})
            continue
        try:
            findings, warnings = gate(text, kind, name=c.get("name") or "", title=c.get("title") or "",
                                      company=c.get("company") or "", contact=iid if c else "",
                                      their_message=_their_last(index.get(iid, ())), today=today)
        except ValueError as err:
            findings, warnings = [_one_line(err)], []
        out.append({"id": iid, "ok": not findings, "kind": kind, "text": text,
                    "findings": findings, "warnings": warnings, "item": it})
    return out


def add_to_pack(today: str, checked: list[dict], got: list[dict], contacts) -> str:
    """Today's pack with every draft the gate passed in place of what code had there."""
    by = {c["id"]: c for c in checked if c["ok"]}
    merged = []
    for i in got:
        if i["id"] in by:
            c = by[i["id"]]
            i = dict(i)
            i["draft"] = _new("check" if c["warnings"] else "ready", kind=c["kind"], text=c["text"],
                              source="written", warnings=c["warnings"])
        merged.append(i)
    return write_pack(today, merged, contacts)


# ---------------------------------------------------------------- output

def render(got: list[dict]) -> str:
    lines = []
    for i in got:
        d = i["draft"]
        if d["status"] == "none" and (i.get("held") or i.get("quiet") or i.get("old")):
            continue
        head = "- %s [%s]: %s" % (i.get("name") or i.get("who"), i["id"], _what(i))
        if d["status"] in ("ready", "check"):
            lines.append(head + " [draft %s, %s, %d chars%s]"
                         % ("ready" if d["status"] == "ready" else "to check", d["kind"], d["chars"],
                            " of %d" % d["limit"] if d["limit"] else ""))
            lines.append("    " + d["text"].replace("\n", "\n    "))
            lines += ["    check: " + w for w in d["warnings"]]
        elif d["status"] == "write":
            lines.append(head + " [needs writing, %s: %s]"
                         % ("here" if d["who"] == "here" else "needs you", d["why"]))
        else:
            lines.append(head + " [nothing to write: %s]" % (d["why"] or i.get("what") or ""))
    return "\n".join(lines) + ("\n" if lines else "nothing due\n")


def _json_safe(got: list[dict]) -> list[dict]:
    keep = ("id", "half", "kind", "name", "due", "late", "contact_id", "draft")
    return [{k: i.get(k) for k in keep} for i in got]


def main(argv=None) -> int:
    with FoldersOnce():
        return _main(argv)


def _main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    today = dt.date.today().isoformat()
    if argv[:1] == ["context"]:
        ap = argparse.ArgumentParser(prog="followup_drafts.py context")
        ap.add_argument("ids", nargs="*")
        ap.add_argument("--due", action="store_true",
                        help="the most urgent contacts whose draft this chat can write or rewrite")
        ap.add_argument("--limit", type=int, default=WRITE_HERE_MAX,
                        help="with --due: at most this many (default %(default)s)")
        ap.add_argument("--today", default=today)
        a = ap.parse_args(argv[1:])
        items, contacts, threads, tracker = load(a.today)
        got = drafts(items, contacts, threads, tracker, a.today)
        here = to_write_here(got) if a.due else []
        ids = list(a.ids) + here[:max(a.limit, 0)]
        if len(here) > len(ids) - len(a.ids):
            print("(%d more to write: each is listed in the pack for a chat with the person)"
                  % (len(here) - (len(ids) - len(a.ids))))
        if not ids:
            print("nothing for this chat to write: every draft code made is clean, and the "
                  "rest need the person")
            return 0
        sys.stdout.write(context(ids, contacts, threads, a.today, got))
        return 0
    if argv[:1] == ["check"]:
        ap = argparse.ArgumentParser(prog="followup_drafts.py check")
        ap.add_argument("file", help="a JSON list of {id, text[, kind]}; - reads it from stdin")
        ap.add_argument("--pack", action="store_true", help="add each draft that passes to today's pack")
        ap.add_argument("--today", default=today)
        a = ap.parse_args(argv[1:])
        raw = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        entries = json.loads(raw)
        entries = entries if isinstance(entries, list) else [entries]
        items, contacts, threads, tracker = load(a.today)
        got = drafts(items, contacts, threads, tracker, a.today)
        res = check(entries, contacts, threads, a.today, got)
        for r in res:
            print("%s %s (%s, %d chars)" % ("PASS" if r["ok"] else "REFUSED", r["id"], r["kind"],
                                           len(r["text"])))
            for f in r["findings"]:
                print("  refused: " + f)
            for w in r["warnings"]:
                print("  warning: " + w)
        if a.pack:
            path = add_to_pack(a.today, res, got, contacts)
            print("pack: %s" % (local_path.rel(path, person.state()) if path else "nothing to write"))
        return 0 if all(r["ok"] for r in res) else 1
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--contact", help="one contact, by id")
    ap.add_argument("--company", help="one employer, both halves")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pack", action="store_true", help="write today's pack")
    ap.add_argument("--today", default=today)
    a = ap.parse_args(argv)
    items, contacts, threads, tracker = load(a.today)
    got = drafts(items, contacts, threads, tracker, a.today)
    if a.contact:
        got = [i for i in got if i.get("contact_id") == a.contact]
    if a.company:
        want = company_key(a.company)
        got = [i for i in got if i.get("key") == want]
    if a.pack:
        path = write_pack(a.today, got, contacts)
        print("pack: %s" % (local_path.rel(path, person.state()) if path else "nothing to write"),
              file=sys.stderr)
    if a.json:
        print(json.dumps(_json_safe(got), indent=1, ensure_ascii=False))
    else:
        sys.stdout.write(render(got))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
