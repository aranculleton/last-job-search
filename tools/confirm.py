#!/usr/bin/env python3
"""Record what the person says happened to an application, on the rows they mean.

    python3 tools/confirm.py applied <rows...> [--on YYYY-MM-DD] [--source chat|page]
    python3 tools/confirm.py not-applied <rows...> [--source chat|page]
    python3 tools/confirm.py skip <rows...>          # they decided not to send it
    python3 tools/confirm.py closed <rows...>        # the posting closed before it went
    python3 tools/confirm.py reopen <rows...>        # a draft they set aside, back among the drafts
    python3 tools/confirm.py check [--ticks <file>]

A row is named by its file name (the ABBR in <Prefix>_Resume_<ABBR>), its round slug (the
employer as staging writes it), the employer, `Employer::title words`, or a whole round:
`all from round r3 except Acme Kestrel::pricing`. Every name is resolved before anything is
written: one that matches no row, or more than one where one was meant, changes nothing
and prints the rows it could mean. What changed is printed row by row, so the person sees
exactly which applications the sentence covered.

Hand edits of the tracker were how "applied" reached it: Claude rewrote a row from a chat
sentence, overwrote its `date` with the day it went, and nothing said who confirmed it or
which rows "applied to all of them" covered. Here `date` never changes (it is part of the
key the tracker merges on, tools/merge_state.py), the day it went is `applied_on`, and
`confirmed_by` says who said so: `page` (ticked on the page), `chat` (answered when asked
in the chat), `person-said` (told unprompted, the default), or `the search` for a close the
app made on silence (followups.py --close-quiet), which `applied` undoes.

`check` lists what does not add up: an application at `applied` that nobody confirmed, a
draft whose notes say it was sent, and a row ticked as applied on the page that the
tracker still has as drafted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import csv_store  # noqa: E402
import person  # noqa: E402
import throttle  # noqa: E402
from company_key import key as company_key  # noqa: E402

TRACKER = person.state("job_search_tracker.csv")
SOURCES = {"chat": "chat", "page": "page", None: "person-said", "": "person-said"}

# What each word does: the statuses a row may be at for it to apply, the status it
# leaves the row at, and the note it writes.
ACTIONS = {
    "applied": "applied",
    "not-applied": "drafted",
    "skip": "withdrawn",
    "closed": "withdrawn",
    # They changed their mind about one they said they would not send: it is a draft again.
    # The undo of skip and closed, so every answer on the page can be taken back.
    "reopen": "drafted",
}


def _status(row) -> str:
    return str(row.get("status") or "").strip().lower()


def _search_closed(row) -> bool:
    return _status(row) in throttle.FINAL and str(row.get("confirmed_by") or "") == "the search"


def takes(action: str, row) -> bool:
    """Can `action` apply to this row? A draft takes all four; an application takes
    `not-applied` (it was never sent after all) and, closed by the search, `applied`."""
    st = _status(row)
    if action == "applied":
        return st in throttle.UNSENT or _search_closed(row)
    if action == "not-applied":
        return st in throttle.UNSENT or st == "applied"
    if action == "reopen":
        # Set aside by the person (skip, closed), never a close the search or an employer made.
        return st == "withdrawn" and not _search_closed(row) and not throttle.applied_on(row)
    return st in throttle.UNSENT


def abbr(row) -> str:
    """The ABBR in the row's resume file name, <Prefix>_Resume_<ABBR>."""
    import docpaths
    stem = os.path.splitext(os.path.basename(str(row.get("cv_file") or "")))[0]
    m = re.search(r"_(?:Resume|CV|%s)_(.+)$" % re.escape(docpaths.noun_word()), stem)
    return m.group(1) if m else ""


_abbr = abbr  # the module's own name for it; other modules call abbr


def _slug(company) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(company or "").lower()).strip("_")


def _words(s) -> set:
    return set(re.findall(r"[a-z0-9]+", throttle.title_key(s)))


def label(row) -> str:
    return f"{row.get('company') or '?'} | {row.get('role') or 'role not recorded'}"


_label = label  # the module's own name for it; other modules call label


def _employer(ref: str, company) -> bool:
    """Is `ref` this employer: the same key (tools/company_key.py), or the employer's own
    name shortened ("Kestrel" for Kestrel Mutual), word for whole word."""
    if company_key(ref) and company_key(ref) == company_key(company):
        return True
    mine = re.findall(r"[a-z0-9]+", str(ref).lower())
    theirs = re.findall(r"[a-z0-9]+", str(company or "").lower())
    return bool(mine) and len("".join(mine)) >= 3 and theirs[:len(mine)] == mine


def matches(ref: str, row) -> bool:
    """Does `ref` name this row: its ABBR, its slug, its employer, or Employer::title words."""
    ref = str(ref or "").strip()
    if not ref:
        return False
    if "::" in ref:
        company, title = ref.split("::", 1)
        return _employer(company, row.get("company")) and _words(title) <= _words(row.get("role"))
    if _abbr(row) and ref.lower() == _abbr(row).lower():
        return True
    if ref.lower() == _slug(row.get("company")) and "_" in ref:
        return True
    return _employer(ref, row.get("company"))


def _round_rows(rows, name: str) -> list:
    name = str(name or "").strip()
    names = {name, name if name.lower().startswith("r") else "r" + name}
    return [r for r in rows
            if any(str(r.get("notes") or "").strip().startswith(n + ".") for n in names)]


class Refused(Exception):
    """A name that matched no row, or several where one was meant: nothing written."""


def resolve(action: str, refs, rows) -> list:
    """The rows `refs` name for `action`, in tracker order, or Refused with the candidates."""
    refs = [str(r) for r in refs if str(r).strip()]
    if not refs:
        raise Refused("name the applications: a file name, an employer, Employer::title "
                      "words, or all from round <name>")
    chosen: list = []
    if refs[0].lower() == "all":
        words = refs[1:]
        low = [w.lower() for w in words]
        if "round" in low:
            i = low.index("round")
            name = words[i + 1] if i + 1 < len(words) else ""
        else:
            name = next((w for w in words if w.lower() not in ("from", "except")), "")
        if not name:
            raise Refused("all from round <name>: which round?")
        rest = words[low.index("except") + 1:] if "except" in low else []
        pool = [r for r in _round_rows(rows, name) if takes(action, r)]
        if not pool:
            raise Refused(f"no application from round {name} can be marked {action}: "
                          + ("; ".join(f"{_label(r)} ({_status(r)})"
                                       for r in _round_rows(rows, name)) or "the round has none"))
        out = []
        for ref in rest:
            hit = [r for r in pool if matches(ref, r)]
            if not hit:
                raise Refused(f"{ref!r} is none of round {name}'s: "
                              + "; ".join(_label(r) for r in pool))
            out += hit
        chosen = [r for r in pool if not any(r is x for x in out)]
    else:
        for ref in refs:
            hit = [r for r in rows if matches(ref, r)]
            live = [r for r in hit if takes(action, r)]
            if not hit:
                raise Refused(f"{ref!r} matches no application in the tracker")
            if not live:
                raise Refused(f"{ref!r} cannot be marked {action}: "
                              + "; ".join(f"{_label(r)} is {_status(r) or 'blank'}" for r in hit))
            if len(live) > 1:
                raise Refused(f"{ref!r} could be any of {len(live)} applications; name one: "
                              + "; ".join(f"{_label(r)} ({_abbr(r) or _status(r)})" for r in live))
            chosen += live
    seen, out = set(), []
    for r in chosen:
        if id(r) not in seen:
            seen.add(id(r))
            out.append(r)
    return out


def add_note(row, text: str) -> None:
    row["notes"] = ((row.get("notes") or "").rstrip() + " | " + text).strip(" |")


_note = add_note  # the module's own name for it; other modules call add_note


def apply(action: str, rows: list, today: dt.date, on: str = "", source=None,
          now: dt.datetime | None = None) -> list:
    """Write `action` onto each row. Returns [(row, what changed)]."""
    by = SOURCES.get(source, source)
    at = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    done = []
    for r in rows:
        before = _status(r) or "blank"
        r["status"] = ACTIONS[action]
        r["confirmed_by"], r["confirmed_at"] = by, at
        if action == "applied" and before in throttle.FINAL:
            # Closed by the search on silence; the person says it is still open. The day
            # it went stays what it was.
            r["applied_on"] = on or r.get("applied_on") or throttle.applied_on(r)
            what = f"{before} -> applied, kept open (applied on {r['applied_on']})"
            _note(r, f"{today.isoformat()}: kept open, not closed after all ({by})")
        elif action == "applied":
            r["applied_on"] = on or today.isoformat()
            what = f"{before} -> applied, applied on {r['applied_on']}"
            _note(r, f"{today.isoformat()}: applied on {r['applied_on']}, confirmed ({by})")
        elif action == "not-applied":
            r["applied_on"] = ""
            what = f"{before} -> drafted, not sent"
            _note(r, f"{today.isoformat()}: not applied, confirmed ({by})")
        elif action == "reopen":
            r["applied_on"] = ""
            what = f"{before} -> drafted, back among the drafts"
            _note(r, f"{today.isoformat()}: back among the drafts, not sent yet ({by})")
        else:
            r["applied_on"] = ""
            why = "they chose not to send it" if action == "skip" else "the posting closed first"
            what = f"{before} -> withdrawn, not sent: {why}"
            _note(r, f"{today.isoformat()}: not sent, {why} ({by})")
        done.append((r, what))
    return done


def run(action: str, refs, on: str = "", source=None, path: str = TRACKER,
        today: dt.date | None = None, now: dt.datetime | None = None) -> list:
    """Resolve, then write, the whole set or none of it. Returns [(row, what changed)]."""
    today = today or dt.date.today()
    rows = csv_store.read_rows(path)
    chosen = resolve(action, refs, rows)
    done = apply(action, chosen, today, on=on, source=source, now=now)
    csv_store.write_rows(path, rows, list(dict.fromkeys(
        csv_store.header(path) + list(throttle.CONFIRM_COLUMNS))))
    return done


def add_applied(company: str, role: str, url: str = "", on: str = "", source=None,
                path: str = TRACKER, today: dt.date | None = None,
                now: dt.datetime | None = None) -> dict:
    """A row for an application the tracker never had (they applied outside the app), at
    `applied`, said by them. Refused when the tracker already has that role open: confirm
    that row instead."""
    import record_drafts
    today = today or dt.date.today()
    company, role = str(company or "").strip(), str(role or "").strip()
    if not company or not role:
        raise Refused("a new application needs --company and --role")
    rows = csv_store.read_rows(path, record_drafts.HEADER)
    have = [r for r in rows if _employer(company, r.get("company"))
            and throttle.same_title(r.get("role"), role) and _status(r) not in throttle.FINAL]
    if have:
        raise Refused(f"the tracker already has {_label(have[0])} ({_status(have[0])}); "
                      f"confirm that row: confirm.py applied \"{have[0].get('company')}::{role}\"")
    row = {c: "" for c in record_drafts.HEADER}
    row.update(date=today.isoformat(), company=company, role=role, status="applied",
               source=str(url or "").strip(), applied_on=on or today.isoformat(),
               confirmed_by=SOURCES.get(source, source),
               confirmed_at=(now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M"),
               notes=f"{today.isoformat()}: applied outside the app, on {on or today.isoformat()}")
    rows.append(row)
    csv_store.write_rows(path, rows, record_drafts.HEADER)
    return row


# What happened after an application went, as /outcome Step 4 writes it: the row's status
# in the canonical spelling and a short dated note, every other field kept (FUNCTIONS_SPEC
# 1.2). The page's "I heard back" and /outcome write the same way through this.
OUTCOMES = ("interview", "offer", "hired", "rejected", "withdrawn", "no_response",
            "offer_declined")
OUTCOME_SAID = {"interview": "interview", "offer": "offer received", "hired": "offer accepted",
                "rejected": "rejected", "withdrawn": "withdrew", "no_response": "no response",
                "offer_declined": "offer declined"}


def record_outcome(row: dict, status: str, today: dt.date, note: str = "", source=None,
                   now: dt.datetime | None = None) -> bool:
    """Write `status` onto an application that went, with a dated note. False, and nothing
    written, when the row is at that status already (said twice, or by two chats); a row
    that never went is refused: it is confirmed applied first, with its day."""
    if status not in OUTCOMES:
        raise Refused(f"{status} is not an outcome ({', '.join(OUTCOMES)})")
    st = _status(row)
    if st in throttle.UNSENT or not st:
        raise Refused(f"{_label(row)} is not marked as sent: mark it applied first, with the "
                      "day it went")
    if st == status:
        return False
    by = SOURCES.get(source, source)
    row["status"] = status
    row["confirmed_by"] = by
    row["confirmed_at"] = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    words = " ".join(str(note or "").split())
    _note(row, f"{today.isoformat()}: {OUTCOME_SAID[status]}" + (f", {words}" if words else "")
          + f" ({by})")
    return True


# A draft whose notes say it went: what a chat wrote down without changing the status.
_SAID_SENT = re.compile(r"\b(?:said|says|told|confirmed)\b[^|]{0,40}\b(?:applied|sent|submitted)\b|"
                        r"\b(?:applied|submitted) (?:on|via|through) \w", re.I)
RECENT_DAYS = 30


def check(rows: list, today: dt.date, ticks=()) -> dict:
    """{kind: [line]} of what does not add up between the tracker and what was said."""
    out: dict = {"applied, nobody confirmed": [], "notes say sent, tracker says drafted": [],
                 "ticked applied, tracker says drafted": []}
    older = 0
    for r in rows:
        st = _status(r)
        if st == "applied" and not str(r.get("confirmed_by") or "").strip():
            on = throttle.applied_on(r)
            try:
                age = (today - dt.date.fromisoformat(on[:10])).days
            except ValueError:
                age = None
            if age is None or age <= RECENT_DAYS:
                out["applied, nobody confirmed"].append(f"{_label(r)} (applied {on or 'undated'})")
            else:
                older += 1
        if st in throttle.UNSENT and not str(r.get("confirmed_by") or "").strip():
            said = [p.strip() for p in str(r.get("notes") or "").split("|") if _SAID_SENT.search(p)]
            if said:
                out["notes say sent, tracker says drafted"].append(f"{_label(r)}: {said[-1]}")
    for t in ticks or ():
        if not isinstance(t, dict) or str(t.get("status") or "").lower() != "applied":
            continue
        ref = t.get("row") or t.get("slug") or "::".join(
            x for x in (str(t.get("company") or ""), str(t.get("role") or "")) if x)
        hit = [r for r in rows if matches(ref, r) and _status(r) in throttle.UNSENT]
        for r in hit:
            out["ticked applied, tracker says drafted"].append(
                f"{_label(r)} (ticked {t.get('at') or 'on the page'})")
    if older:
        out["applied, nobody confirmed"].append(
            f"and {older} older than {RECENT_DAYS} days, from before confirming was recorded")
    return {k: v for k, v in out.items() if v}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Record what the person says happened to an "
                                             "application, on the rows they mean.")
    ap.add_argument("action", nargs="?", choices=sorted(ACTIONS) + ["check"])
    ap.add_argument("rows", nargs="*", help="file names, employers, Employer::title words, or "
                                            "all from round <name> except ...")
    ap.add_argument("--on", default="", help="the day it went (applied), YYYY-MM-DD")
    ap.add_argument("--source", choices=("chat", "page"), default=None,
                    help="where they said it: chat (asked), page (ticked); unprompted if left out")
    ap.add_argument("--new", action="store_true",
                    help="applied: an application the tracker never had (with --company, --role)")
    ap.add_argument("--company", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--url", default="", help="--new: the posting's link")
    ap.add_argument("--ticks", help="check: a JSON list of the page's ticks")
    ap.add_argument("--tracker", default=TRACKER)
    ap.add_argument("--today", default="")
    a = ap.parse_args(argv)
    if not a.action:
        ap.print_usage()
        return 2
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    if a.on:
        try:
            dt.date.fromisoformat(a.on)
        except ValueError:
            print(f"confirm: --on {a.on!r} is not a date (YYYY-MM-DD)")
            return 2
    if a.action == "check":
        ticks = []
        if a.ticks:
            try:
                with open(a.ticks, encoding="utf-8") as fh:
                    ticks = json.load(fh)
            except (OSError, ValueError) as e:
                print(f"confirm: cannot read {a.ticks}: {e}")
                return 2
            ticks = ticks.get("ticks", []) if isinstance(ticks, dict) else ticks
        found = check(csv_store.read_rows(a.tracker), today, ticks)
        if not found:
            print("confirm: nothing to ask: every status the tracker holds was said by somebody")
            return 0
        for kind, lines in found.items():
            print(f"{kind}:")
            for line in lines:
                print(f"  {line}")
        return 1
    if a.new:
        if a.action != "applied":
            print("confirm: --new is for an application they made outside the app (applied)")
            return 2
        try:
            row = add_applied(a.company, a.role, a.url, on=a.on, source=a.source,
                              path=a.tracker, today=today)
        except Refused as e:
            print(f"confirm: nothing changed. {e}")
            return 1
        print(f"confirm: 1 application added:\n  {_label(row)}: applied on {row['applied_on']}")
        return 0
    try:
        done = run(a.action, a.rows, on=a.on, source=a.source, path=a.tracker, today=today)
    except Refused as e:
        print(f"confirm: nothing changed. {e}")
        return 1
    print(f"confirm: {len(done)} application{'s' if len(done) != 1 else ''} changed:")
    for row, what in done:
        print(f"  {_label(row)}: {what}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except csv_store.Conflicted as e:
        print(f"confirm: {e}")
        sys.exit(1)
