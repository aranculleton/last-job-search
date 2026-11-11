#!/usr/bin/env python3
"""Every follow-up drafted by code first, then put through the gate a hand-written one gets.

What is owed comes from `open_actions.due_items` (both halves: contacts and applications), so
this never keeps a clock of its own. For each item it makes the draft the state files can
support and nothing more:

  an application nudge   followups.py's own text, to the recipient it found
  a networking nudge     the draft waiting for them (documents/network/<id>/draft.md, what
                         the page's Messages shows), one on the contact's row or in an earlier
                         pack; else a nudge (compose.nudge) whose new reason is a posting at
                         their employer from the newest saved round, said only to a reader
                         allowed to hear the role, or a follow-up on their own offer; else,
                         with nothing new to say, a short plain follow-up (plain_nudge): it
                         follows up on the person's own unanswered note and asks one question
                         about the reader's work, in the person's own words where they have
                         some, unless their own rule says otherwise (plain_nudge_allowed)
  anything else          the draft waiting for them, one on the contact's row or in an
                         earlier pack

Every draft then goes through `compose.validate` (the gate: a finding means code could not
make it cleanly, and it is listed as needs writing, with the finding as the reason) and
`compose.advise` (warnings, kept beside the draft for the rewrite). Nothing is claimed that
the thread or the profile does not hold: the only new fact code ever writes is a posting
the search found, named as it was posted.

A draft code cannot make is listed with why, and who can write it: "here" when the thread
holds what a writer needs (a reply: their message is in the log), "you" when it needs the
person (a recipient nobody has found, a nudge their own rule keeps for something new).

A draft that passes the gate is put where the page's Messages shows it, in the same step
(`keep`): a contact's in documents/network/<id>/draft.md, the one draft waiting for them, and
an application's in today's pack, which Messages reads for it. Follow-ups written by hand and
passed by `check --pack` went only into the pack, and Messages never showed one (2026-11-04).

    python3 tools/followup_drafts.py                     # everything due, each with its draft or why not
    python3 tools/followup_drafts.py --contact <id>      # one contact
    python3 tools/followup_drafts.py --company <name>    # one employer, both halves
    python3 tools/followup_drafts.py --json
    python3 tools/followup_drafts.py --pack              # also write documents/network/followup_pack_<today>.md,
                                                         # and put each clean draft in Messages
    python3 tools/followup_drafts.py context --due       # what a writer needs, for what code could not draft
    python3 tools/followup_drafts.py context <id>...
    python3 tools/followup_drafts.py check <drafts.json> [--pack]   # the gate, for drafts written by hand
    python3 tools/followup_drafts.py role-holds [--dry]  # set aside drafts written before the role they wait for
    python3 tools/followup_drafts.py unfitted [--dry]    # set aside code's follow-ups never fitted to your rules

`check` reads a JSON list of {"id": <contact id or app:...>, "text": "<the draft>"} (and
"kind" where it is not the usual one), runs validate, the restatement check against their
last message, and advise, and puts each draft the gate passes where Messages shows it; with
--pack today's pack is written with them too.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
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


# How many words, besides the name and the employer, two drafts may differ by and still be
# one message with those swapped: "a" for "an", "are" for "'re", a day. A share of the words
# was the test, nine in ten, and a person's own recipe keeps three of a first note's four
# lines the same for everyone, so two notes whose one tailored line differed were refused
# (the review, 2026-11-10).
SWAP_WORDS = 3
_GREET = re.compile(r"^\s*(?:hi|hello|hey|dear)\b[^,.!?\n]{0,40}[,.!]\s*", re.I)


# A link, and a run of capitalised words that is not a sentence's first (a name, an employer, a
# role's title: "Senior Pricing Analyst", "Data Scientist, Forecasting").
_LINK = re.compile(r"https?://\S+|www\.\S+", re.I)
_PROPER = re.compile(r"(?<=[\w,;:)] )(?:[A-Z][\w&'.-]*(?:,? (?:of |and |& )?[A-Z][\w&'.-]*)*)")


def _bare(text: str, name: str = "", company: str = "") -> str:
    """A draft with its greeting, the reader's name, their employer, every other name or title
    (a capitalised run) and every link taken out, in small letters: what is left is what was
    written, whoever it is to. Two referral asks from one template, the same but for the role
    and its link, passed as two messages (the review, 2026-11-11)."""
    t = _GREET.sub("", " ".join(str(text or "").split()))
    t = _LINK.sub("*", t)
    words = [w for w in re.split(r"\s+", str(name or "").strip()) if len(w) > 1]
    for w in sorted(set(words + ([company.strip()] if company.strip() else [])),
                    key=len, reverse=True):
        t = re.sub(r"(?<!\w)" + re.escape(w) + r"(?:'s)?(?!\w)", "*", t, flags=re.I)
    t = _PROPER.sub("*", t)
    t = re.sub(r"[^a-z0-9* ]+", " ", t.lower())
    return re.sub(r"\*(?:\s*\*)+", "*", " ".join(t.split())).strip()


def same_but_for_name(text: str, contact: str, name: str = "", company: str = "",
                      others: dict | None = None) -> str:
    """Why this draft is not written for its reader, or "": it is the draft waiting for
    someone else, with the name and the employer swapped (once both are taken out, the two
    differ by SWAP_WORDS words at most; a line written for this reader differs by more). `others` is {contact id: (their draft, name, employer)}; None
    reads every draft waiting on a card (documents/network/<id>/draft.md) with the contact
    book. Two cards carried one referral follow-up, word for word but for those (the
    maintainer, 2026-11-10): every message is built for its reader."""
    import difflib
    mine = _bare(text, name, company)
    if len(mine.split()) < 8:
        return ""                      # a line or two of thanks is the same to anyone
    if others is None:
        others = _waiting_drafts(skip=contact)
    for cid, (theirs, their_name, their_company) in sorted(others.items()):
        if cid == contact:
            continue
        other = _bare(theirs, their_name, their_company)
        if not other:
            continue
        a, b = mine.split(), other.split()
        apart = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2
                    in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
                    if op != "equal")
        if apart <= SWAP_WORDS:
            first = (str(their_name or "").split() or ["someone else"])[0]
            return ("the same words as your draft to %s, with the name and the employer "
                    "swapped: write it from what this person said and does" % first)
    return ""


# Code's old follow-up on their offer, as it stood on a card: one message for everyone, with
# the name and the employer swapped.
_OFFER_TEMPLATE = re.compile(
    r"you (?:kindly )?offered to (?:refer me if a role came up|put me in touch with someone) at "
    r".{1,80}?, and I'd still be glad of that\. If (?:one does|a role there appeals), would it "
    r"be all right to send you the link\?", re.I | re.S)


def drafts_before_a_role(contacts=None) -> list[tuple[str, str]]:
    """[(contact id, why)] for each draft waiting on a card that should carry no words yet:
    one to someone on hold until a role is posted (it was written before the role), and
    code's old follow-up on their offer, which was the same message on every card."""
    from network import state
    contacts = state.load_contacts() if contacts is None else contacts
    book = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    out = []
    today = person.today()
    for cid, (body, _name, _company) in sorted(_waiting_drafts().items()):
        c = book.get(cid) or {}
        # Only while the hold is on: a draft saved for them ends it (reply.save_draft).
        if state.role_hold(c.get("next_action")) and state.action_hold(
                c.get("next_action"), today, c.get("next_action_due")):
            out.append((cid, "on hold until a role is posted"))
        elif _OFFER_TEMPLATE.search(body):
            out.append((cid, "the follow-up on their offer that code wrote for everyone"))
    return out


def set_aside_before_a_role(write: bool = True) -> list[str]:
    """Set each of `drafts_before_a_role` aside, kept (state.park_draft), and put its person
    on hold until a role is posted where they are not on hold already. A line each."""
    from network import state
    contacts = state.load_contacts()
    found = drafts_before_a_role(contacts)
    said, changed = [], False
    for cid, why in found:
        said.append("%s: %s" % (cid, why))
        if not write:
            continue
        if state.hold_for_role(contacts, cid, "they offered to refer you", today=person.today()):
            changed = True                 # on hold now, its draft set aside with it
        else:
            state.park_draft(cid)
    if changed:
        state.save_contacts(contacts)
    return said


# Code's plain follow-up kept on a card before it was fitted to the person's own rules for
# messages, set aside beside the card's draft, kept, never deleted.
UNFITTED = "draft.unfitted.md"


def unfitted_on_cards(contacts=None, threads=None, today: str = "") -> list[tuple[str, str]]:
    """[(contact id, why)] for each card holding code's plain follow-up word for word, kept
    there before it was fitted to the person's own rules for messages: runs before 2026-11-11
    (app.py follow-ups and the brief) put a draft flagged RULES_TO_FIT on the card, where the
    page said ready to send. Only while the person has such rules, as the flag needs today;
    a draft the person, a chat or /network wrote or edited is never the same words, a first
    note waiting on a read is /network's, and one already logged as sent is left alone."""
    if not _message_rules():
        return []
    import reading
    from network import state
    contacts = state.load_contacts() if contacts is None else contacts
    threads = state.load_threads() if threads is None else threads
    book = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    index = state.by_contact(threads) if threads else {}
    today = today or person.today().isoformat()
    out = []
    for cid, (body, _name, _company) in sorted(_waiting_drafts().items()):
        c = book.get(cid)
        msgs = list(index.get(cid, ()))
        if c is None or not msgs or reading.marked(cid):
            continue
        said = " ".join(body.split())
        if any(state._direction(r) == "out"
               and " ".join(str(r.get("full_text") or "").split()) == said for r in msgs):
            continue                        # sent already: the card only lags the log
        try:
            code = plain_nudge(c, msgs, today=today)
        except ValueError:
            continue
        if " ".join(str(code or "").split()) == said:
            out.append((cid, "code's plain follow-up, never fitted to your own rules for messages"))
    return out


def set_aside_unfitted(write: bool = True) -> list[str]:
    """Set each of `unfitted_on_cards` aside, kept (UNFITTED, never over another file), so
    the card offers nothing to send and the follow-up is owed again: the next run drafts it,
    flagged, for Claude to fit to the person's rules (`check`), and only a rewrite that
    passes reaches the card. A line each."""
    from network import state
    said = []
    for cid, why in unfitted_on_cards():
        said.append("%s: %s" % (cid, why))
        if write:
            folder = state._draft_folder(cid)
            if folder:
                state.park_draft(cid, as_name=state._free_name(folder, UNFITTED))
    return said


def _waiting_drafts(skip: str = "") -> dict:
    """{contact id: (the draft waiting on their card, their name, their employer)}."""
    try:
        import reading
        from network import state
        book = {str(c.get("contact_id") or "").strip(): c for c in state.load_contacts()}
    except Exception:  # noqa: BLE001  no book: nothing to compare with
        return {}
    out = {}
    for path in glob.glob(person.state("documents", "network", "*", "draft.md")):
        cid = os.path.basename(os.path.dirname(path))
        if cid == skip or cid not in book:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                body = reading.note_body(fh.read()).strip()
        except OSError:
            continue
        if body:
            out[cid] = (body, book[cid].get("name") or "", book[cid].get("company") or "")
    return out


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

def newest_round_rows(today=None) -> list[dict]:
    """The postings Jobs holds now: the newest saved round's (documents/rounds/<round>.json),
    then those it carries from earlier searches (app_model.carried: found in the last
    CARRY_DAYS days, or kept for later), or []. Read from the newest round alone, a hold that
    lifted for a role went back on as soon as a newer search was saved without it (the review,
    2026-11-10), though the role was still on the person's list. `today` is the page's day
    (default the person's own)."""
    try:
        import app_model
        newest = app_model.newest_round()
    except Exception:  # noqa: BLE001  no page model here: the newest round's own rows
        return _newest_file_rows()
    if not newest:
        return []
    rows = app_model.read_json(newest, [])
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    try:
        day = today if isinstance(today, dt.date) else (
            dt.date.fromisoformat(str(today)[:10]) if today else person.today())
        rows += [r for _name, _rank, r in app_model.carried(day, newest)]
    except Exception:  # noqa: BLE001  an earlier round that cannot be read carries nothing
        pass
    return rows


def _newest_file_rows() -> list[dict]:
    """The rows of the newest saved round file, by its number and then its time."""
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


def live_application(contact: dict, tracker=(), since: str = "", held_on: str = "") -> dict:
    """The person's own application or hiring process at their employer that is still open
    (applied, an interview, an offer; a draft only when made after `since`, the last message,
    as a posting counts only once found since), the newest, as a posting: {"title", "company",
    "url", "status", "from": "tracker"}, or {}. A role they are already in for is a role
    posted: a hold that waited for one said none was posted at an employer where an interview
    was booked (the review, 2026-11-10)."""
    import throttle
    k = company_key(contact.get("company"))
    if not k:
        return {}

    def open_(r):
        status = str(r.get("status") or "").strip().lower()
        if status in throttle.FINAL:
            return False
        began = str(r.get("date") or "")[:10]
        # There when the hold was made (`held_on`): the hold was made knowing it, so it lifts
        # nothing; a draft from before held a person on hold as soon as it was made (the
        # review, 2026-11-11). One begun since lifts it.
        if held_on and began <= held_on:
            return False
        return status != "drafted" or not since or began > since
    live = [r for r in tracker or () if company_key(r.get("company")) == k
            and str(r.get("role") or "").strip() and open_(r)]
    if not live:
        return {}
    r = max(live, key=lambda x: str(x.get("date") or ""))
    return {"title": _clean_title(r.get("role")), "company": str(r.get("company") or "").strip(),
            "url": str(r.get("source") or r.get("apply_url") or "").strip(),
            "status": str(r.get("status") or "").strip().lower(), "from": "tracker"}


def role_for_offer(contact: dict, since: str, rows: list[dict], tracker=()) -> dict:
    """The role a referral offer waits for: a posting at their employer the search found since
    the last message (posting_reason), else the person's own open application or process there
    (live_application), or {}."""
    from network import state
    return (posting_reason(contact, since, rows, tracker)
            or live_application(contact, tracker, since,
                                held_on=state.hold_made(contact.get("next_action"))))


def role_said(role: dict, company: str) -> str:
    """The role a referral ask is for, in the words the page and the draft step say it."""
    import throttle
    title = " ".join(str(role.get("title") or "a role").split())
    status = str(role.get("status") or "")
    if role.get("from") == "tracker" and "offer" in status:
        return f"You have an offer for {title} at {company}"
    if role.get("from") == "tracker" and status in throttle.LIVE_PROCESS:
        return f"You have an interview for {title} at {company}"
    if role.get("from") == "tracker" and status not in ("", "drafted"):
        return f"You have applied for {title} at {company}"
    return f"{company} has posted {title}"


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

def _new(status, kind="", text="", why="", who="", source="", warnings=(), findings=(),
         look=False):
    out = {"status": status, "kind": kind, "text": text, "why": why, "who": who,
           "source": source, "warnings": list(warnings), "findings": list(findings),
           "chars": len(text or ""), "limit": limit_of(kind) if kind else 0}
    if look:
        out["look"] = True
    return out


def draft(item: dict, contacts_by_id: dict, threads_index: dict, tracker, earlier: dict,
          rows: list[dict], today: str = "") -> dict:
    """The draft for one due item: {"status": ready | check | write | none, ...}.

    ready  made by code and clean; check  made by code, with advise's warnings to rewrite on;
    write  code could not make it cleanly (`why`, and `who` writes it: here or you);
    none   nothing to write (an action: send a file, prep a call, withdraw a request)."""
    if item.get("held") or item.get("quiet") or item.get("old"):
        return _new("none", why="held: " + "; ".join(item.get("held") or ["not due"]))
    if item.get("campaign"):
        # Owed, and drafted in the employer's own chat: two chats writing to one person
        # contradict each other (open_actions.due_items).
        return _new("none", why="drafted in the chat that runs this employer's process")
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
    if not stored and item.get("kind") != "reply":
        # The draft waiting for them (documents/network/<id>/draft.md), which the page's
        # Messages shows: a first note queued by /network, or a follow-up kept there before
        # (`keep`), checked as it stands, so a run never writes a second over the one the
        # person sees or edited. One still waiting on a read of their profile is the person's
        # to unlock. A reply's is not read: it may answer a message of theirs since overtaken.
        queued, card_only, waits = _queued_note(cid)
        if waits:
            # Nobody is asked to write it: it is rewritten once their profile is read.
            return _new("write", kind=kind, who="read", source="stored",
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
        return refused or _new("write", kind=kind, who="here",
                    why="they accepted and nothing has been said: a first message is written "
                        "from what was read about them (/network)")
    if item.get("kind") != "nudge":
        return refused or _new("none", why=item.get("what") or "")
    compose = _compose()
    reader = compose.reader_type(title)
    since = item.get("since") or ""
    offer = their_offer(msgs)
    if offer is not None:
        # They offered to refer the person, or to put them in touch, once there is a role.
        # With one posted, the referral ask is written for that role and this person, from
        # what they offered, by the chat (compose.referral_ask). With none, nothing is
        # written: code's follow-up on the offer was one message with the name and the
        # employer swapped, on two cards at once (the maintainer, 2026-11-10). They wait on
        # hold until a role is posted (`hold_for_role`, state.ROLE_HOLD), and come back by
        # themselves.
        role = role_for_offer(contact, since, rows, tracker)
        if role:
            return refused or _new(
                "write", kind=kind, who="here",
                why="%s, since their offer of %s: write the referral ask for that one role, in "
                    "what they offered, with the posting's link (compose.referral_ask)"
                    % (role_said(role, company or "their employer"),
                       offer.get("date") or "an earlier day"))
        got = _new("none", kind=kind, why=ROLE_WAIT_WHY % (company or "their employer"))
        got["hold_role"] = True
        return got
    # A nudge needs something new to answer: a posting the search found at their employer,
    # said only to a reader allowed to hear the role (compose.SAY_THE_ROLE).
    posting = posting_reason(contact, since, rows, tracker) if compose.SAY_THE_ROLE.get(reader) else {}
    if posting:
        try:
            text = nudge_from_posting(contact, posting)
        except ValueError as e:
            return _new("write", kind=kind, who="here",
                        why="the nudge about %s's %s posting did not pass: %s"
                            % (company, _clean_title(posting.get("title")), _one_line(e)))
        got = _checked(text, kind, name=name, title=title, company=company, contact=cid,
                       their_message=their, source="code", today=today)
        if got["status"] != "write":
            got["why"] = "new reason: %s posted %s" % (company, _clean_title(posting.get("title")))
        return got
    if refused:
        return refused                      # their own words, to rewrite on its findings
    # Nothing new to say: a short plain follow-up all the same, never a refusal that leaves
    # the page's Follow up doing nothing. Code wrote one for 1 of 19 due (2026-11-04).
    if not plain_nudge_allowed():
        # Claude looks for something new before anyone is asked anything (LOOK_FIRST); the
        # person is never asked to write it (2026-11-06).
        return _new("write", kind=kind, who="here", look=True,
                    why="nothing new to say on file, and your own rule is to follow up only "
                        "with something new (a role they posted, news at %s, something you "
                        "have done since)" % (company or "their employer"))
    try:
        text = plain_nudge(contact or {"contact_id": cid, "name": name}, msgs, today=today)
    except ValueError as e:
        return _new("write", kind=kind, who="here", look=True,
                    why="the plain follow-up did not pass: " + _one_line(e))
    got = _checked(text, kind, name=name, title=title, company=company, contact=cid,
                   their_message=their, source="code", today=today)
    if got["status"] != "write":
        got["why"] = "nothing new to say, so a short plain follow-up"
        if _message_rules():
            # Code cannot read the person's own rules for messages (where they are, the roles
            # they want, a thanks): its plain draft goes to Claude to fit them, never as it is
            # (2026-11-06: the plain follow-up left out what a newer rule asked for).
            got["status"] = "check"
            got["warnings"] = list(got.get("warnings") or []) + [RULES_TO_FIT]
    return got


RULES_TO_FIT = ("code's plain follow-up has not been fitted to your own rules for messages "
                "(listed at the top): rewrite it to them")


def _message_rules() -> list[str]:
    """The person's active rules for messages, as `learned.brief` lists them, or []."""
    try:
        import learned
        return [ln for ln in learned.brief("messages").splitlines() if ln.startswith("- ")]
    except Exception:  # noqa: BLE001  an unreadable learned file sets no rule
        return []


def plain_nudge_allowed() -> bool:
    """Is a follow-up with nothing new to say still drafted, short and plain? Yes, unless the
    person said otherwise: profile/networking.py PLAIN_NUDGE, or the newest rule of theirs
    that says either way (learned.known_settings reads one in any words, and `record` writes
    the setting), so a rule kept before the setting existed is followed too."""
    try:
        net = person.module("networking")
    except Exception:  # noqa: BLE001  no profile: the app's default
        net = None
    own = getattr(net, "PLAIN_NUDGE", None)
    if own is not None:
        return bool(own)
    try:
        import learned
        over = learned.superseded()
        for r in reversed(learned.entries()):
            if learned.entry_key(r) in over:
                continue
            for setting, value in learned.known_settings(
                    str(r.get("area") or ""), str(r.get("said") or ""), str(r.get("rule") or "")):
                if setting.endswith(" PLAIN_NUDGE"):
                    return bool(value)
    except Exception:  # noqa: BLE001  an unreadable learned file sets no rule
        pass
    return True


def plain_nudge(contact: dict, msgs, today: str = "") -> str:
    """A short plain follow-up for a thread where nothing new has happened: it follows up on
    the person's own unanswered message by its month ("following up on my note from
    October") and asks one thing, a question about the reader's work (to a recruiter, the
    plain ask), in the person's own words where their profile has them (compose.options:
    their TEMPLATES and ASK first, then the app's lines their voice check passes). One that
    shares two or more words with that message is passed over, so it is never asked again.
    Held to a nudge's length and gate. Raises what compose.nudge raises."""
    compose = _compose()
    import learned
    import state
    cid = str(contact.get("contact_id") or "")
    reader = compose.reader_type(contact.get("title") or "")
    last = compose.unanswered_ours(msgs)
    said = learned.content_words(str((last or {}).get("full_text") or (last or {}).get("summary")
                                     or ""))
    if reader == "recruiter":
        lines = [(o, o) for o in compose.options("ask", reader)]
    else:
        lines = [(compose._question(o.replace("{team}", "your team")), o.replace("{team}", ""))
                 for o in compose.options("work_question", reader)]
    lines = [(line, words) for line, words in lines if str(line or "").strip()]
    if not lines:
        raise ValueError("no plain question in the person's own words or the app's")
    # Chosen by contact, as compose.phrase chooses: a batch varies and a redraft does not.
    start = int(hashlib.sha1(cid.encode()).hexdigest(), 16) % len(lines) if cid else 0
    ordered = lines[start:] + lines[:start]
    reason = next((line for line, words in ordered
                   if len(learned.content_words(words) & said) < 2), ordered[0][0])
    name = str(contact.get("name") or "")
    if last is not None:
        return compose.follow_up(name, msgs, reason, today=today or None, vary=cid)
    # Owed, with no words of ours in the log (their history predates it): said as a follow-up
    # all the same, never as a first message.
    word = "email" if state.channel_of(contact) == "email" else "note"
    company = str(contact.get("company") or "").strip()
    return compose.nudge(name, reason, opener="following up on my " + word,
                         their=(company,) if company else ())


# Why nothing is drafted for someone who offered to refer the person while no role is posted.
ROLE_WAIT_WHY = ("they offered to refer you once there is a role, and none is posted at %s yet: "
                 "on hold until one is, and written then for that role")

# Their own offer to refer, as the one thing a follow-up gives them to answer. Kept for a
# message a chat writes about one posted role; code no longer drafts a follow-up from them
# (ROLE_WAIT_WHY).
OFFER_REASON = ("in your last message you offered to refer me if a role came up at %s, and I'd "
                "still be glad of that")
OFFER_CLOSE = "If one does, would it be all right to send you the link?"
# An offer to introduce is not an offer to refer. "Happy to connect you with a recruiter if
# something appeals" was followed up as "you offered to refer me", which they never said
# (2026-11-03): the follow-up says what they offered.
INTRO_REASON = ("in your last message you kindly offered to put me in touch with someone at %s, "
                "and I'd still be glad of that")
INTRO_CLOSE = "If a role there appeals, would it be all right to send you the link?"


def offer_words(offer: dict) -> tuple[str, str]:
    """(reason, close) for a follow-up on their offer, in what they offered: to refer the
    person only where their own words say refer or referral, else to put them in touch."""
    import compose
    said = str((offer or {}).get("full_text") or (offer or {}).get("summary") or "")
    if compose._REFER_WORDS.search(said):
        return OFFER_REASON, OFFER_CLOSE
    return INTRO_REASON, INTRO_CLOSE


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
    except ValueError as e:                 # a reaction waiting, an unknown kind: Claude's
        return _new("write", kind=kind, who="here", why=_one_line(e), source=source)
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
    shelve_packs(today)
    return path


PACKS_KEPT = 2          # earlier_drafts reads the newest two; the rest go to old/


def shelve_packs(today: str) -> list[str]:
    """Move every pack up to `today` but the newest PACKS_KEPT into documents/network/old/,
    kept, never deleted: only those two are read again, and 14 piled up (audit HC-4). The
    paths moved to."""
    folder = person.state(*PACK_DIR)
    packs = sorted(p for p in glob.glob(os.path.join(folder, PACK_NAME % "*"))
                   if os.path.basename(p)[len("followup_pack_"):-3] <= today)
    out = []
    for p in packs[:-PACKS_KEPT]:
        dest = os.path.join(folder, "old", os.path.basename(p))
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(p, dest)
        except OSError:
            continue
        out.append(dest)
    return out


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
        if d.get("look"):
            out.append(LOOK_FIRST % {"company": c.get("company") or "their employer"})
            seen = _what_was_read(cid)
            if seen:
                out.append("their profile as read: " + seen)
        out.append("")
    if ids:
        out.append("Write each in the person's voice, claiming nothing the thread or the "
                   "profile does not hold, then: python3 tools/followup_drafts.py check "
                   "<file.json> --pack, with [{\"id\": \"<contact id>\", \"text\": \"...\"}]")
    return "\n".join(out).rstrip() + "\n"


# Nothing new on file: what Claude looks at before writing, and what it does when nothing
# turns up. The person is never asked to write a follow-up (2026-11-06).
LOOK_FIRST = ("look first: their profile as read (below), news at %(company)s this month, roles "
              "%(company)s has posted since your note, and anything new in your own profile "
              "(01-candidate-profile.md). Use the one true thing you find; if nothing turns up, "
              "write a short plain follow-up, or where your rule is to follow up only with "
              "something new, pass {\"id\": \"<contact id>\", \"none\": \"nothing new yet\"} "
              "and nobody is asked anything")


def _what_was_read(cid: str) -> str:
    """Their stored profile read, in a line: headline, where they are, the start of About."""
    try:
        import reading
        got = reading.load(cid) or {}
    except (ImportError, OSError, ValueError):
        return ""
    if not isinstance(got, dict):
        return ""
    parts = [str(got.get(k) or "").strip() for k in ("headline", "location")]
    about = str(got.get("about") or "").strip()
    line = "; ".join(x for x in parts if x)
    if about:
        line = (line + "; about: " if line else "about: ") + about
    return _clip(line, 300) if line else ""


def _clip(text, n: int = 400) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 3].rstrip() + "..."


def to_write_here(got) -> list[str]:
    """The contacts whose draft this chat can write or rewrite from the thread: a reply, a
    draft the gate refused, or one advise warned about."""
    return [i["contact_id"] for i in got if i.get("half") == "contact"
            and (i["draft"]["status"] == "check"
                 or (i["draft"]["status"] == "write" and i["draft"]["who"] == "here"))]


def held_by_rule(contact: dict, msgs, kind: str = "") -> str:
    """Why the person's own surface rules stop a message to this contact, in plain words, or
    "": surface.held, the one check every screen and the due list read. A reply to someone
    who wrote last is held only by what stops a reply (a closed thread, an employer turned
    down), as there."""
    from network import state
    import surface
    msgs = list(msgs or ())
    status = state.effective_status(contact, msgs)
    got = surface.held(contact, msgs, status,
                       replying=kind == "reply" or status in state.schema.OWED_BY_US)
    if not got:
        return ""
    return got.get("said") or "their conversation is closed"


def check(entries, contacts, threads, today: str, got=None) -> list[dict]:
    """The gate for drafts written by hand: [{"id", "ok", "findings", "warnings", ...}]."""
    from network import state
    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    index = state.by_contact(threads) if threads else {}
    drafted = {i["id"]: i for i in (got or ())}
    waiting = _waiting_drafts()
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
        # Held as the due list holds it: by what is owed (a reply to someone who wrote, or a
        # follow-up), never by the kind a draft was checked as, which a held item has none of.
        owed = "reply" if (it.get("kind") in ("reply", "resume") if it else kind == "reply") \
            else "nudge"
        stop = held_by_rule(c, index.get(iid, ()), owed) if c else None
        if stop:
            # The person's own rules stop anything going to them (where they live, their limit,
            # an employer turned down): a draft written by hand is held as one written by code
            # is, never kept on their card to send (a person's copy, 2026-11-05).
            out.append({"id": iid, "ok": False, "kind": kind, "text": text, "held": stop,
                        "findings": ["held: " + stop], "warnings": [], "item": it})
            continue
        try:
            findings, warnings = gate(text, kind, name=c.get("name") or "", title=c.get("title") or "",
                                      company=c.get("company") or "", contact=iid if c else "",
                                      their_message=_their_last(index.get(iid, ())), today=today)
        except ValueError as err:
            findings, warnings = [_one_line(err)], []
        # Written for its reader: never the draft waiting for someone else, or one earlier
        # in this batch, with the name and the employer swapped.
        if c and not iid.startswith("app:"):
            others = dict(waiting)
            others.update({o["id"]: (o["text"], (by_id.get(o["id"]) or {}).get("name") or "",
                                     (by_id.get(o["id"]) or {}).get("company") or "")
                           for o in out if o.get("text") and o["id"] in by_id})
            same = same_but_for_name(text, iid, name=c.get("name") or "",
                                     company=c.get("company") or "", others=others)
            if same:
                findings = list(findings) + ["not_written_for_its_reader: " + same]
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


# ---------------------------------------------------------------- where Messages shows it

def keep(pairs) -> list[str]:
    """Each (contact id, draft) the gate passed, put where the page's Messages shows it
    (documents/network/<id>/draft.md, the one draft waiting for them), by the code that
    passed it: the ids written. Never over the same words, and never over a first note still
    marked as resting on a read or on their card alone, which is /network's to rewrite. A
    marked draft to someone the person has already talked to is no first note but one left
    from before the conversation: the follow-up takes its place (reading.talked_with)."""
    import reading
    import reply
    out = []
    for cid, text in pairs:
        cid, text = str(cid or "").strip(), str(text or "").strip()
        if not cid or not text or cid.startswith("app:"):
            continue
        try:
            with open(reading.draft_path(cid), encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = None
        except ValueError:                   # not an id a folder can have
            continue
        if raw is not None and ((reading.marked(cid) and not reading.talked_with(cid))
                                or reading.note_body(raw).strip() == text):
            continue
        reply.save_draft(cid, text)
        out.append(cid)
    return out


def keep_drafted(got) -> list[str]:
    """`keep` for what code drafted: each contact's draft that came out clean. Everyone whose
    follow-up waits for a role goes on hold on their record in the same step (`hold_for_role`).
    One flagged for a rewrite (`check`) is not clean: on the card, the page offered it as
    ready to send while the same run listed it to rewrite, and the next run read it back from
    the card, unflagged, and finished it as ready (a person's copy, 2026-11-11). It reaches
    the card only once rewritten and passed (`keep_checked`)."""
    hold_for_role(got)
    return keep((i.get("contact_id"), i["draft"]["text"]) for i in got
                if i.get("half") == "contact" and i["draft"]["status"] == "ready")


def hold_for_role(got) -> list[str]:
    """Each contact whose follow-up waits for a role to be posted (`draft`'s `hold_role`),
    put on hold on their record (state.hold_for_role): the due list stops asking for a
    follow-up there is nothing to say in, and the page lists them under On hold until a role
    is posted. The ids put on hold."""
    ids = [str(i.get("contact_id") or "") for i in got
           if i.get("half") == "contact" and (i.get("draft") or {}).get("hold_role")]
    if not ids:
        return []
    from network import state
    contacts = state.load_contacts()
    held = [cid for cid in ids if state.hold_for_role(contacts, cid, "they offered to refer you",
                                                      today=person.today())]
    if held:
        state.save_contacts(contacts)
    return held


def keep_checked(checked, contacts) -> list[str]:
    """`keep` for drafts written by hand: each one `check` passed, for someone in the book."""
    known = {str(c.get("contact_id") or "").strip() for c in contacts}
    return keep((c["id"], c["text"]) for c in checked if c["ok"] and c["id"] in known)


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
    today = person.today().isoformat()
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
    if argv[:1] == ["role-holds"]:
        ap = argparse.ArgumentParser(
            prog="followup_drafts.py role-holds",
            description="Set aside (kept) each draft written before the role it waits for.")
        ap.add_argument("--dry", action="store_true", help="count them, change nothing")
        a = ap.parse_args(argv[1:])
        said = set_aside_before_a_role(write=not a.dry)
        if a.dry:
            print(len(said))
            return 0
        print("set aside, kept: %d draft(s) written before the role they wait for; each is "
              "written for that role once it is posted" % len(said))
        for line in said[:40]:
            print("  " + line)
        return 0
    if argv[:1] == ["unfitted"]:
        ap = argparse.ArgumentParser(
            prog="followup_drafts.py unfitted",
            description="Set aside (kept) code's plain follow-ups left on a card before they "
                        "were fitted to the person's own rules for messages.")
        ap.add_argument("--dry", action="store_true", help="count them, change nothing")
        a = ap.parse_args(argv[1:])
        said = set_aside_unfitted(write=not a.dry)
        if a.dry:
            print(len(said))
            return 0
        print("set aside, kept: %d follow-up(s) never fitted to your own rules for messages; "
              "each is written again to fit them before it is offered to send" % len(said))
        for line in said[:40]:
            print("  " + line)
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
        # Each one that passed goes where the page's Messages shows it, now: a contact's as
        # the draft waiting for them, an application's in today's pack, which Messages reads.
        shown = keep_checked(res, contacts)
        if shown:
            print("on their cards in Contacts: " + ", ".join(shown))
        if a.pack or any(r["ok"] and r["id"].startswith("app:") for r in res):
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
        shown = keep_drafted(got)
        if shown:
            print("on their cards in Contacts: " + ", ".join(shown), file=sys.stderr)
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
