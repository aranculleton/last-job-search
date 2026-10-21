#!/usr/bin/env python3
"""Why this person, in plain words, and how good a contact they are, 0 to 100.

A run finds more people than it can write to, and a title on its own says little
about who will reply or who sits next to a role worth having. This reads what is
already known about each person (the search result, the route to them, the
reading of their profile, the roles open at their employer in the latest round)
and says why they are worth a note, the way a fit score says why a posting is.

It is counting, never a model call, so it costs nothing to run over every person
a search returns. The batch is read and written in this order, best first, and
the line goes beside each draft so the person sees why it was chosen.

Usage:
    python3 tools/network/why.py <contact_id> [...]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dates  # noqa: E402
import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

STRONG, GOOD = 75, 60
# A posting this good at their employer makes someone in its function worth more.
ROLE_FIT_FLOOR = 60
ACTIVE_DAYS = 90

# The candidate's own core work, as the job scoring already weighs it (search.py
# FIT_CORE): someone whose headline, About or posts name the same work is the person
# a note can talk shop with, and the strongest reason a match reads as perfect.
# Only the heavier entries: SQL on two profiles says nothing.
_SEARCH = person.module("search") if person.exists("search.py") else None
CORE_WEIGHT = 7
CORE = [(rx, label) for rx, pts, label in (getattr(_SEARCH, "FIT_CORE", None) or ())
        if pts >= CORE_WEIGHT and label]

# Who gets the short note: someone who runs a function or a company. Deliberately
# narrower than tone.is_senior, which decides the formal register and counts every
# manager and lead: a hands-on lead is the reader most likely to reply to a note
# with a real question in it, so they keep the question.
# AVP, SVP and EVP are as senior as VP: "AVP, Data Platforms" read as a peer.
_EXEC = re.compile(r"\b(?:chief|c[a-z]o\b|[asde]?vp\b|vice\s+president|president|partner|managing\s+director"
                   r"|head\s+of|director|founder|co-?founder|owner)\b", re.I)


def open_roles(company: str, rounds_dir: str | None = None) -> list:
    """The roles open at an employer in the latest kept round, best fit first.

    Each row carries `_path`, the round file it came from, so a reader that
    prints a score can say where the score is recorded.
    """
    files = sorted(glob.glob(os.path.join(rounds_dir or person.state("documents", "rounds"),
                                          "*.json")), key=os.path.getmtime)
    for path in reversed(files):
        if os.path.basename(path).startswith("."):
            continue
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rows, list) and rows:
            key = company_key(company)
            mine = [dict(r, _path=path) for r in rows
                    if isinstance(r, dict) and company_key(r.get("company", "")) == key]
            return sorted(mine, key=lambda r: -(r.get("fit") or 0))
    return []


def _age(date: str, today: dt.date) -> int | None:
    return dates.days_since(date, today, iso_only=True)


def route_odds(contacts, threads, today=None) -> dict:
    """{route group: (points, why)} for the routes whose reply rate clearly differs.

    The person's own results, counted by tools/what_works.py: a route moves a
    score only once both it and the rest have MIN_GROUP decided first notes and
    the gap is unlikely to be chance, held to every route compared (what_works.clear).
    Until then this is empty and nothing moves.
    """
    import what_works
    openers = [c for c in what_works.message_cases(contacts, threads, today)
               if c["attempt"] == "opener"]
    out = {}
    routes = {c["route"] for c in openers}
    for route in routes:
        mine = [c for c in openers if c["route"] == route]
        rest = [c for c in openers if c["route"] != route]
        a, b = sum(c["won"] for c in mine), sum(c["won"] for c in rest)
        if what_works.clear(a, len(mine), b, len(rest), comparisons=len(routes)):
            better = a / len(mine) > b / len(rest)
            out[route] = (6 if better else -6,
                          f"your {route} notes are answered {a} of {len(mine)}")
    return out


def why_them(contact: dict, reading: dict | None = None, roles=None,
             today: dt.date | None = None, applied=(), odds=None) -> dict:
    """{"score", "band", "skip", "reasons": [(points, why)], "line"} for one person."""
    import discovery
    today = today or dt.date.today()
    reading = reading or {}
    # What was read on their own page outranks the contact book's title, which can
    # be months old: a stale "Head of Data Platforms" ranked a person as hands-on.
    page = any(s.get("kind") in ("paste", "browser", "pdf", "screenshot")
               for s in reading.get("sources") or [])
    title = ((reading.get("headline") if page else "") or contact.get("title")
             or reading.get("headline") or "")
    contact = {**contact, "title": title}
    company = contact.get("company") or reading.get("company") or ""
    route = str(contact.get("route") or "").lower()
    reasons: list[tuple[int, str]] = []

    if reading.get("reach") == "pending":
        return {"score": 0, "band": "skip", "skip": True,
                "reasons": [(0, "a connection request to them is already pending")],
                "line": "a connection request to them is already pending"}

    if route == "connection" or contact.get("first_degree"):
        reasons.append((30, "already in your connections: a message, not a request"))
    elif route in ("referral", "mutual") or contact.get("referred_by"):
        reasons.append((30, f"a warm route: {contact.get('route_detail') or 'someone you know'}"))
    shared = reading.get("shared") or {}
    employers = [e.get("name") for e in shared.get("employers", []) if e.get("name")]
    schools = [e.get("name") for e in shared.get("schools", []) if e.get("name")]
    if employers:
        reasons.append((22, f"worked at {employers[0]}, like you"))
    elif route.startswith("alumni_employer"):
        reasons.append((20, contact.get("route_detail") or "a former colleague's employer"))
    if schools:
        reasons.append((15, f"studied at {schools[0]}, like you"))
    elif route.startswith("alumni_school"):
        reasons.append((15, contact.get("route_detail") or "went to your school"))
    places = [e.get("name") for e in shared.get("places", []) if e.get("name")]
    if places and not (employers or schools):
        reasons.append((5, f"has lived or worked in {places[0]}, like you"))
    if route == "hiring_team":
        reasons.append((20, "named on a posting there"))

    tier = str(contact.get("tier") or "").strip()
    if tier == "1":
        when = contact.get("signal_date") or ""
        reasons.append((20, "posted about hiring" + (f" on {when}" if when else "")))
    elif tier == "2":
        reasons.append((12, f"can hire: {title}" if title else "can hire"))
    elif tier == "3":
        reasons.append((8, "senior in your function"))

    theirs = " ".join([title, contact.get("signal") or "", reading.get("headline", ""),
                       reading.get("about", ""), reading.get("current", "")]
                      + [i.get("text", "") for i in reading.get("items") or []])
    same = [label for rx, label in CORE if rx.search(theirs)]
    same = list(dict.fromkeys(same))
    if same:
        reasons.append((12 + 6 * (len(same) > 1),
                        f"works on {' and '.join(same[:2])}, like you"))

    if not title:
        # Nothing says what they do. A known Chief Data Officer ranked below eight people
        # whose results named only the employer, because the unknowns lost nothing for it.
        reasons.append((-8, "their title is not in the search result: see what they do first"))
    if contact.get("found_for") and not title:
        # Not their title: the result named only the employer. A search for the job
        # surfaced them, which is a reason to look, never a claim about their role.
        reasons.append((4, f"came up in a search for {contact['found_for']} there, "
                           "which is not their title"))
    in_function = bool(title) and bool(discovery.FUNCTION_TITLE.search(title))
    roles = open_roles(company) if roles is None else roles
    good = [r for r in roles if (r.get("fit") or 0) >= ROLE_FIT_FLOOR]
    if good and (in_function or tier in ("1", "2")):
        r = good[0]
        reasons.append((15, f"{company} has a role open you scored {r.get('fit')}: {r.get('title')}"))

    # An application already in at their employer: the person a referral or a
    # word with the hiring manager would come through (state.link_to_applications).
    if applied:
        import state
    import throttle
    # A draft nobody sent is not an application there.
    live = [a for a in applied if str(a.get("status") or "").strip().lower()
            not in state.TRACKER_FINAL | throttle.UNSENT] if applied else []
    if live:
        a = live[0]
        done = "a hiring process is live there" if throttle.is_process(a) else "you applied there"
        reasons.append((4, f"{done}: {a.get('role') or 'a role'} ({a.get('status')})"))

    items = reading.get("items") or []
    ages = {id(i): _age(i.get("date", ""), today) for i in items}
    # An age of 0 is a post from today, the most active there is: never read it as missing.
    recent = [i for i in items if i.get("kind") in ("post", "repost")
              and ages[id(i)] is not None and ages[id(i)] <= ACTIVE_DAYS]
    if recent:
        reasons.append((8, "active: posted in the last three months"))
    work = [i for i in items if i.get("kind") in ("talk", "article", "podcast", "code",
                                                  "publication", "featured")]
    if work:
        reasons.append((6, f"public work to start from: {work[0].get('text', '')[:60]}".rstrip(": ")))

    reach = reading.get("reach") or ""
    if reach == "message" and not (route == "connection" or contact.get("first_degree")):
        reasons.append((10, "already connected: a message, not a request"))
    elif reach == "request under More":
        reasons.append((-3, "Connect is behind More on their profile"))

    if odds:
        import what_works
        hit = odds.get(what_works.route_group(contact.get("route")))
        if hit:
            reasons.append(hit)

    rank, why = discovery.reply_rank(contact)
    if rank == 1:
        reasons.append((5, "a hands-on title, the kind that replies most"))
    elif rank == 5:
        reasons.append((-10, "runs a function rather than doing the work; replies least"))
    if contact.get("location_unverified"):
        reasons.append((-5, "location not confirmed"))
    if contact.get("name_only") or not ((contact.get("linkedin_url") or "").strip()
                                        or (contact.get("email") or "").strip()):
        reasons.append((-8, "found by name only: find them on LinkedIn before any request"))
    elif contact.get("profile_status") == "likely":
        reasons.append((-4, "profile found, but its title does not name the employer: check it"))
    if contact.get("reverify"):
        reasons.append((-6, "named on an old page: check they still hold the role"))

    score = max(0, min(100, 30 + sum(p for p, _ in reasons)))
    band = "strong" if score >= STRONG else "good" if score >= GOOD else "worth a try"
    best = [w for p, w in sorted(reasons, key=lambda x: -x[0]) if p > 0][:3]
    return {"score": score, "band": band, "skip": False, "reasons": reasons,
            "line": "; ".join(best) or "matched the search, nothing more known yet"}


def seniority(title: str) -> str:
    """"senior" for a title that runs a function, else "peer": decides the note's length."""
    return "senior" if _EXEC.search(title or "") else "peer"


def ranked(contacts: list, today: dt.date | None = None, tracker=None, threads=None) -> list:
    """Contacts best first, each with its `why` attached (a copy; nothing is written)."""
    import reading as _reading
    import state
    if tracker is None:
        tracker = state.load_tracker() if os.path.exists(state.TRACKER_CSV) else []
    apps = {l["contact_id"]: l["applications"] for l in state.link_to_applications(contacts, tracker)}
    if threads is None:
        threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    odds = route_odds(contacts, threads, today) if threads else {}
    out = []
    for c in contacts:
        w = why_them(c, _reading.load(c.get("contact_id", "")) or {}, today=today,
                     applied=apps.get(c.get("contact_id", ""), ()), odds=odds)
        out.append({**c, "why": w})
    return sorted(out, key=lambda c: (c["why"]["skip"], -c["why"]["score"]))


def not_writable(contact: dict, threads=(), today: dt.date | None = None) -> str:
    """Why this contact must not be written to now, or "" when a first note may go.

    The default ranking listed people whose rows said closed, on hold, in conversation
    or awaiting a reply, among them a closed contact at an employer the person had
    ruled out (scoring 57) and people at an employer with a live interview, marked
    HOLD. Only someone nothing has gone to, with no hold and at an employer still in
    the search, is worth ranking for a first note."""
    import sources
    import state
    today = today or dt.date.today()
    cid = str(contact.get("contact_id") or "").strip()
    status = state.effective_status(contact, state.threads_for(list(threads), cid))
    if status != "not_contacted":
        return status
    hold = state.action_hold(contact.get("next_action"), today)
    if hold:
        return f"on hold: {hold}"
    out = sources.ruled_out(contact.get("company") or "")
    return f"employer ruled out: {out}" if out else ""


def main(argv: list | None = None) -> int:
    import state
    args = argv if argv is not None else sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print("usage: python3 tools/network/why.py [--all] [contact_id ...]\n\n"
              "Only contacts a first note may go to, unless --all or ids are named.\n\n"
              + __doc__.strip())
        return 0
    everyone = "--all" in args
    ids = {a for a in args if a != "--all"}
    contacts = [c for c in state.load_contacts() if not ids or c.get("contact_id") in ids]
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    left_out = 0
    if not (everyone or ids):
        keep = [c for c in contacts if not not_writable(c, threads)]
        left_out, contacts = len(contacts) - len(keep), keep
    for c in ranked(contacts, threads=threads):
        w = c["why"]
        tag = ""
        if everyone or ids:
            why_not = not_writable(c, threads)
            tag = f"  [not now: {why_not}]" if why_not else ""
        print(f"{w['score']:>3}  {c.get('name')} ({c.get('company')}): {w['line']}{tag}")
    if left_out:
        print(f"({left_out} others left out: written to, closed, on hold or at an employer "
              "ruled out; --all lists them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
