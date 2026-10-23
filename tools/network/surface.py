#!/usr/bin/env python3
"""The one check before anyone is shown as someone to write to.

Every list of people the person is asked to write to goes through `check()`: the
connections at an employer, a search's results, a pasted people search, a list page read
in their browser, the queue of first notes, and any list a chat puts together itself. It
answers "show" or "do not show", with the reason, from everything the repo knows:

- **the contact book**, by contact id, by profile address (`state.profile_handle`, which
  reads every form of one address as one), and by name at the same employer, under the
  employer the book has or the one their connections file has, which can be years old;
- **their whole thread, on every channel**: a connection request, a note, a message, an
  InMail, an email, an introduction, under every row of the book that is them. Anyone
  written to is not shown as someone new: what is owed to them is in `open_actions.py
  --due`;
- **the employer**: `tools/bar.py` (an employer the profile excludes, one judged to clear
  none of pay, prestige or signal, and one nobody has judged yet, which is judged once
  first), `job_scraper/do_not_target.json` and an earlier run's finding of no relevant
  team there;
- **a hold** on their row.

Each step used to make its own check, and a chat that skipped one surfaced people
already written to on another channel and people at employers the profile rules out
(2026-10-23). A name that may be someone already in the book under another employer or
spelling is shown with a warning to ask first, never merged and never shown as a
stranger. Someone known only from their connections file, connected long ago, is shown
with a warning that their employer and title may be out of date and that the file has no
location: their profile is read before anything is written to them.

    python3 tools/network/surface.py "<name>" [--company "<employer>"] [--url <profile address>]
    python3 tools/network/surface.py --id <contact_id> [...]
    python3 tools/network/surface.py --file <people.json>     # a list: [{name, company, linkedin_url}]
    python3 tools/network/surface.py --queue                  # everyone waiting on a first note
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import state  # noqa: E402

# A connection made longer ago than this is someone whose employer and title in the
# connections file may well have changed: LinkedIn's file carries no date for them and no
# location at all, so their profile is read before a note.
EXPORT_STALE_DAYS = 180


def _book_index(contacts) -> dict:
    """The book by contact id, by profile address, by name and by employer, each row's
    address and name worked out once: a check per person that scanned the whole book
    and the whole connections file took 42 seconds over 1,300 contacts (2026-10-23)."""
    by_id, by_handle, by_name, by_key = {}, {}, {}, {}
    handle, named = {}, {}
    for r in contacts or ():
        h = state.profile_handle(r.get("linkedin_url"))
        k = state._match_name(r.get("name"))
        handle[id(r)], named[id(r)] = h, k
        by_id.setdefault(str(r.get("contact_id") or "").strip(), []).append(r)
        if h:
            by_handle.setdefault(h, []).append(r)
        if k:
            by_name.setdefault(k, []).append(r)
        ck = state.row_company_key(r)
        if ck:
            by_key.setdefault(ck, []).append(r)
    return {"by_id": by_id, "by_handle": by_handle, "by_name": by_name, "by_key": by_key,
            "handle": handle, "name": named}


def context(contacts=None, threads=None, connections=None, today=None) -> dict:
    """What `check` reads, loaded and indexed once for a whole list."""
    if contacts is None:
        contacts = state.load_contacts() if os.path.exists(state.CONTACTS_CSV) else []
    if threads is None:
        threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    if connections is None:
        connections = state.first_degree()
    today = state.as_date(today) or datetime.date.today()
    by_handle: dict = {}
    by_name: dict = {}
    for c in connections or ():
        h = state.profile_handle(c.get("linkedin_url"))
        if h:
            by_handle.setdefault(h, c)
        k = state._match_name(c.get("name"))
        if k:
            by_name.setdefault(k, []).append(c)
    return {"contacts": contacts, "book": _book_index(contacts),
            "threads": state.by_contact(threads), "today": today,
            "connections": connections or [], "conn_by_handle": by_handle,
            "conn_by_name": by_name, "employers": {}}


def _same_employer(a, b) -> bool:
    import discovery
    return bool(state.company_key(a or "")) and bool(state.company_key(b or "")) \
        and discovery.same_employer(a or "", b or "")


def in_book(contacts, name="", company="", url="", contact_id="", also=(), index=None) -> tuple:
    """(every row of the book that is this person, how they were first found).

    By contact id, by profile address, and by the same name at the same employer, under
    `company` or any employer in `also` (their connections file's, which can be years
    old), where the row has no address of its own or none was given; every row any of
    those finds, and every other row under an address one of them has. A different
    address is a different person. `index` (_book_index) for a whole list at once."""
    ix = index or _book_index(contacts)
    found, how = [], ""

    def add(rows, why):
        nonlocal how
        for r in rows:
            if not any(r is f for f in found):
                found.append(r)
                how = how or why
    cid = str(contact_id or "").strip()
    if cid:
        add(ix["by_id"].get(cid, ()), "contact id")
    h = state.profile_handle(url)
    if h:
        add(ix["by_handle"].get(h, ()), "profile address")
    key = state._match_name(name) if name else ""
    emps = [e for e in (company, *also) if str(e or "").strip()]
    if key and emps:
        add([r for r in ix["by_name"].get(key, ())
             if not (h and ix["handle"].get(id(r)))
             and any(_same_employer(r.get("company"), e) for e in emps)], "name and employer")
    for h2 in {ix["handle"].get(id(r)) for r in found} - {"", None}:
        add(ix["by_handle"].get(h2, ()), how or "profile address")
    # And their other rows under their name at their employer, with no other address: a
    # message logged under a row a search made, before their address was known.
    for r in list(found):
        mine_h = ix["handle"].get(id(r))
        add([o for o in ix["by_name"].get(ix["name"].get(id(r)) or "", ())
             if (not ix["handle"].get(id(o)) or ix["handle"].get(id(o)) == mine_h)
             and _same_employer(o.get("company"), r.get("company"))], how)
    return found, how


def maybe_in_book(contacts, name="", company="", url="", index=None) -> str:
    """The warning for someone who may already be in the book, or "": a nickname, an
    initial, a middle name or a typo at the same employer (state._why_same, as
    `state.possible_match` reads them), or the same name at another employer where either
    side has no profile address (a move since the connections file was written)."""
    ix = index or _book_index(contacts)
    key = state._match_name(name) if name else ""
    h = state.profile_handle(url)
    if not (key or str(name or "").strip()):
        return ""
    ck = state.company_key(company) if company else ""
    for r in ix["by_key"].get(ck, ()) if ck else ():
        theirs = ix["handle"].get(id(r))
        if h and theirs and h != theirs:
            continue
        sure, why = state._why_same(name, r.get("name"))
        if sure:
            return state.duplicate_line({"row": r, "sure": sure, "reason": why})
    for r in ix["by_name"].get(key, ()) if key else ():
        theirs = ix["handle"].get(id(r))
        if h and theirs and h != theirs:
            continue
        return state.duplicate_line({"row": r, "reason": (
            "the same name, at %s in your contact book%s" % (
                r.get("company") or "no employer",
                f" and at {company} here" if company else ""))})
    return ""


def _thread_line(msgs) -> str:
    sent = [m for m in msgs if state._direction(m) == "out"]
    back = [m for m in msgs if state._direction(m) == "in" and state.said_something(m)
            and not state.is_auto_reply(m)]
    chans = sorted({state.channel_of(m) or "message" for m in msgs})
    last = msgs[-1].get("date") if msgs else ""
    return (f"{len(sent)} sent, {len(back)} back, on {', '.join(chans)}"
            + (f", last {last}" if last else ""))


def _connection(ctx, name, company, url):
    """Their row in the connections file: by profile address, or by the same name at the
    same employer. A name alone, with no employer to go with it, is nobody in particular."""
    h = state.profile_handle(url)
    if h and h in ctx["conn_by_handle"]:
        return ctx["conn_by_handle"][h]
    key = state._match_name(name) if name else ""
    if not key or not str(company or "").strip():
        return None
    return next((c for c in ctx.get("conn_by_name", {}).get(key, ())
                 if c.get("company") and _same_employer(c.get("company"), company)
                 and not (h and state.profile_handle(c.get("linkedin_url")))), None)


def employer_out(company: str, today=None) -> str:
    """Why nobody at this employer is shown, or "": the profile's bar (tools/bar.py), the
    employers it rules out for search (do_not_target.json) and an earlier run's finding
    of no relevant team there."""
    import bar
    import discovery
    import sources
    company = str(company or "").strip()
    if not company:
        return ""
    why = sources.ruled_out(company)
    if why:
        return why
    verdict, why = bar.verdict(company)
    if verdict == bar.NONE:
        if bar.listed(company):
            return f"clears none of pay, prestige or signal: {why}"
        return (f"not judged against your bar yet: judge it once (python3 tools/bar.py judge "
                f"\"{company}\" <pay|prestige|signal|none> \"<why>\"), then check again")
    try:
        if discovery.presence_ruled_out(company, today or datetime.date.today()):
            return "an earlier run found no relevant team there (company_research/)"
    except (OSError, ValueError):            # a research file that cannot be read
        pass
    return ""


def check(person: dict, ctx: dict | None = None, queued: bool = False) -> dict:
    """Show this person, or not, and why: {"show", "reason", "warn": [...], "contact_id",
    "how", "needs_read"}.

    `person` holds what the list had: name, company, linkedin_url (or url), contact_id,
    connected_on. `queued` is for the queue of first notes: a row of the book nobody has
    written to yet may be shown there, and nowhere else, since anywhere else it is not
    someone new. Every row of the book that is them is read, whichever comes first."""
    import export
    ctx = ctx or context()
    p = person or {}
    name = str(p.get("name") or "").strip()
    company = str(p.get("company") or "").strip()
    url = str(p.get("linkedin_url") or p.get("url") or "").strip()
    pid = str(p.get("contact_id") or "").strip()
    out = {"show": True, "reason": "", "warn": [], "contact_id": "", "how": "",
           "needs_read": False}

    def no(reason):
        out.update(show=False, reason=reason)
        return out

    if not (name or url or pid):
        return no("nothing to check: no name, profile address or contact id")
    mine = export.me()
    if (mine[0] and state.profile_handle(url) == mine[0]) or \
            (not url and mine[1] and export.name_key(name) == mine[1]):
        return no("that is you")
    ix = ctx.get("book") or _book_index(ctx["contacts"])
    conn = _connection(ctx, name, company, url)
    also = tuple(e for e in (p.get("also_company"), (conn or {}).get("company")) if e)
    rows, how = in_book(ctx["contacts"], name, company, url, pid, also, index=ix)
    if pid and not rows and not (name or url):
        return no(f"{pid} is not in your contact book")
    if rows:
        cid = str(rows[0].get("contact_id") or "").strip()
        out.update(contact_id=cid, how=how)
        msgs = state._ordered([m for r in rows
                               for m in ctx["threads"].get(str(r.get("contact_id") or "").strip(), ())
                               if state._direction(m)])
        statuses = [(r, state.effective_status(r, msgs)) for r in rows]
        for r, status in statuses:
            if status in state.schema.TERMINAL:
                why = str(r.get("outcome") or r.get("next_action") or "").strip()
                return no(f"{status} in your contact book as {r.get('contact_id')}"
                          + (f": {why}" if why else ""))
        status = statuses[0][1]
        if msgs:
            line = _thread_line(msgs)
            if any(s in state.schema.OWED_BY_US for _r, s in statuses):
                return no(f"they replied: a reply is owed to {cid}, not a new note ({line}); "
                          "it is in open_actions.py --due")
            return no(f"already written to as {cid}: {line}; status {status}")
        for r, status in statuses:
            if status != "not_contacted":
                # Their row says a thread is running that the log has not caught up with.
                return no(f"{status} in your contact book as {r.get('contact_id')}, though "
                          "nothing is logged yet")
        for r in rows:
            hold = state.action_hold(r.get("next_action"), ctx["today"])
            if hold:
                return no(f"{hold} ({r.get('contact_id')})")
        if not queued:
            return no(f"already in your contact book as {cid}, not written to yet: it is in "
                      "the queue, not someone new")
        company = str(rows[0].get("company") or "").strip() or company
    else:
        warn = maybe_in_book(ctx["contacts"], name, company, url, index=ix)
        if warn:
            out["warn"].append(f"ask first: {warn}")
    memo = ctx.setdefault("employers", {})
    if company not in memo:
        memo[company] = employer_out(company, ctx["today"])
    why = memo[company]
    if why:
        return no(f"{company}: {why}")
    if not company:
        out["warn"].append("no employer known, so the bar was not checked: place them first")
    connected = old_connection(p, ctx, out["contact_id"], conn)
    if connected:
        out["needs_read"] = True
        out["warn"].append(OLD_CONNECTION.format(day=connected))
    return out


OLD_CONNECTION = ("their employer and title come from your connections file (connected {day}), "
                  "which LinkedIn does not keep current, and it has no location: read their "
                  "profile before writing")


def old_connection(person: dict, ctx: dict, contact_id: str = "", conn=None) -> str:
    """The day they connected, when that was more than EXPORT_STALE_DAYS ago and nothing
    has been read about them since; "" otherwise. Their employer and title are then the
    connections file's, which may be out of date."""
    import export
    p = person or {}
    if conn is None:
        conn = _connection(ctx, p.get("name"), p.get("company"),
                           p.get("linkedin_url") or p.get("url"))
    when = export.day(p.get("connected_on") or (conn or {}).get("connected_on") or "")
    if when is None or (ctx["today"] - when).days <= EXPORT_STALE_DAYS:
        return ""
    return "" if _read(contact_id or p.get("contact_id") or "") else when.isoformat()


def _read(contact_id: str) -> bool:
    if not contact_id:
        return False
    try:
        import reading
        return reading.has_read(reading.load(contact_id))
    except (ImportError, OSError, ValueError):
        return False


def screen(people, ctx: dict | None = None, queued: bool = False) -> tuple:
    """(shown, held) for a list: shown is each person with `surface` (the check) attached,
    held is (person, reason) for everyone not shown."""
    ctx = ctx or context()
    shown, held = [], []
    for p in people or ():
        got = check(p, ctx, queued=queued)
        if got["show"]:
            shown.append({**p, "surface": got})
        else:
            held.append((p, got["reason"]))
    return shown, held


def _line(p, got) -> str:
    who = (str(p.get("name") or p.get("contact_id") or p.get("linkedin_url") or "?")
           + (f" ({p['company']})" if p.get("company") else ""))
    if not got["show"]:
        return f"NOT   {who}: {got['reason']}"
    return "SHOW  " + who + "".join(f"\n      {w}" for w in got["warn"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Show this person as someone to write to, or not, "
                                             "and why.")
    ap.add_argument("name", nargs="?", default="")
    ap.add_argument("--company", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--id", nargs="*", default=[], dest="ids")
    ap.add_argument("--file", default="", help="a JSON list of people: [{name, company, linkedin_url}]")
    ap.add_argument("--queue", action="store_true", help="everyone in the book waiting on a first note")
    a = ap.parse_args(argv)
    ctx = context()
    if a.file:
        with open(a.file, encoding="utf-8") as fh:
            people = json.load(fh)
        people = people.get("people", people) if isinstance(people, dict) else people
        queued = False
    elif a.queue:
        people = [c for c in ctx["contacts"] if str(c.get("status") or "not_contacted").strip()
                  in ("", "not_contacted")]
        queued = True
    elif a.ids:
        people = [{"contact_id": i} for i in a.ids]
        queued = True
    elif a.name or a.url:
        people = [{"name": a.name, "company": a.company, "linkedin_url": a.url}]
        queued = False
    else:
        ap.print_help()
        return 2
    shown = 0
    for p in people:
        if not isinstance(p, dict):
            continue
        got = check(p, ctx, queued=queued)
        if p.get("contact_id") and not p.get("name"):
            row = next((c for c in ctx["contacts"] if c.get("contact_id") == p["contact_id"]), {})
            p = {**row, **p}
        shown += got["show"]
        print(_line(p, got))
    if not people:
        print("nobody to check" + (": nobody is waiting on a first note" if a.queue else ""))
    elif len(people) > 1:
        print(f"{shown} of {len(people)} to show")
    return 0


if __name__ == "__main__":
    sys.exit(main())
