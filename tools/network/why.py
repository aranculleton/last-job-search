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

_EXEC = re.compile(r"\b(?:chief|c[a-z]o\b|vp\b|vice\s+president|president|partner|managing\s+director"
                   r"|head\s+of|director)\b", re.I)


def open_roles(company: str, rounds_dir: str | None = None) -> list:
    """The roles open at an employer in the latest kept round, best fit first."""
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
            mine = [r for r in rows if isinstance(r, dict) and company_key(r.get("company", "")) == key]
            return sorted(mine, key=lambda r: -(r.get("fit") or 0))
    return []


def _age(date: str, today: dt.date) -> int | None:
    try:
        return (today - dt.date.fromisoformat(str(date)[:10])).days
    except ValueError:
        return None


def why_them(contact: dict, reading: dict | None = None, roles=None,
             today: dt.date | None = None) -> dict:
    """{"score", "band", "skip", "reasons": [(points, why)], "line"} for one person."""
    import discovery
    today = today or dt.date.today()
    reading = reading or {}
    title = contact.get("title") or reading.get("headline") or ""
    company = contact.get("company") or reading.get("company") or ""
    route = str(contact.get("route") or "").lower()
    reasons: list[tuple[int, str]] = []

    if reading.get("reach") == "pending":
        return {"score": 0, "band": "skip", "skip": True,
                "reasons": [(0, "a connection request to them is already pending")],
                "line": "a connection request to them is already pending"}

    if route in ("referral", "mutual") or contact.get("referred_by"):
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

    in_function = bool(title) and bool(discovery.FUNCTION_TITLE.search(title))
    roles = open_roles(company) if roles is None else roles
    good = [r for r in roles if (r.get("fit") or 0) >= ROLE_FIT_FLOOR]
    if good and (in_function or tier in ("1", "2")):
        r = good[0]
        reasons.append((15, f"{company} has a role open you scored {r.get('fit')}: {r.get('title')}"))

    items = reading.get("items") or []
    recent = [i for i in items if i.get("kind") in ("post", "repost")
              and (_age(i.get("date", ""), today) or 10 ** 6) <= ACTIVE_DAYS]
    if recent:
        reasons.append((8, "active: posted in the last three months"))
    work = [i for i in items if i.get("kind") in ("talk", "article", "podcast", "code",
                                                  "publication", "featured")]
    if work:
        reasons.append((6, f"public work to start from: {work[0].get('text', '')[:60]}".rstrip(": ")))

    reach = reading.get("reach") or ""
    if reach == "message":
        reasons.append((10, "already connected: a message, not a request"))
    elif reach == "request under More":
        reasons.append((-3, "Connect is behind More on their profile"))

    rank, why = discovery.reply_rank(contact)
    if rank == 1:
        reasons.append((5, "a hands-on title, the kind that replies most"))
    elif rank == 5:
        reasons.append((-10, "runs a function rather than doing the work; replies least"))
    if contact.get("location_unverified"):
        reasons.append((-5, "location not confirmed"))

    score = max(0, min(100, 30 + sum(p for p, _ in reasons)))
    band = "strong" if score >= STRONG else "good" if score >= GOOD else "worth a try"
    best = [w for p, w in sorted(reasons, key=lambda x: -x[0]) if p > 0][:3]
    return {"score": score, "band": band, "skip": False, "reasons": reasons,
            "line": "; ".join(best) or "matched the search, nothing more known yet"}


def seniority(title: str) -> str:
    """"senior" for a title that runs a function, else "peer": decides the note's length."""
    return "senior" if _EXEC.search(title or "") else "peer"


def ranked(contacts: list, today: dt.date | None = None) -> list:
    """Contacts best first, each with its `why` attached (a copy; nothing is written)."""
    import reading as _reading
    out = []
    for c in contacts:
        w = why_them(c, _reading.load(c.get("contact_id", "")) or {}, today=today)
        out.append({**c, "why": w})
    return sorted(out, key=lambda c: (c["why"]["skip"], -c["why"]["score"]))


def main(argv: list | None = None) -> int:
    import state
    ids = set(argv if argv is not None else sys.argv[1:])
    contacts = [c for c in state.load_contacts() if not ids or c.get("contact_id") in ids]
    for c in ranked(contacts):
        w = c["why"]
        print(f"{w['score']:>3}  {c.get('name')} ({c.get('company')}): {w['line']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
