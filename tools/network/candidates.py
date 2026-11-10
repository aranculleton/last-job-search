#!/usr/bin/env python3
"""Who to write to, from a people search, in one call: every list check, a headline filter
and a ranking by who is likeliest to help, before anyone reaches the list.

A "find 10 people" run on 2026-11-09 put names from search results on the list and only
then read their profiles, so it found too late that a recruiter there hired for sales,
another for corporate finance and two more for engineers; that five employers already had
two people waiting on a reply; and that one person had been written to a fortnight before.
It swapped people out and searched again, and stopped at eight of the ten asked for. The
checks were spread over five tools, and each was met one at a time. Here they are one
command, in this order, for every person a search found:

1. **The headline**, from the person's own settings (profile/networking.py): a role outside
   their function (`discovery.disqualify`, `reading.title_fit`), a recruiter whose
   headline names a function that is not theirs ("Sales Recruiter", "Talent Acquisition,
   Corporate Finance"), and any headline they said never to show (`SKIP_HEADLINES`).
2. **Every list check**, through the one check (`surface.check`): already in the contact
   book or written to on any channel, closed, held, an employer the bar turns down, the
   per-employer limit (the people there already waiting on a reply), and where they live
   when the result says (`surface.outside_market`). Twice on one list is once.
3. **The ranking**, best first: the kind of reader first, by the person's reply rates
   (founder, hiring leader, recruiter, senior peer, peer: their own `REPLY_RATES`, else
   their message log, else the app's order), then a hiring signal in the headline
   ("Hiring", "we're hiring"), then `why.why_them` (a warm route, a hiring post, a role open
   there, their function), a recruiter covering the person's function above one covering a
   near one (`RECRUITER_NEAR`), and background they share (an employer they left, their
   school).
4. **The list**: the hiring side first (recruiters, hiring leaders, founders), walked in
   that order, each employer up to its limit counting the people already waiting there (and
   `PER_EMPLOYER_PER_RUN` where the person set one), until `--want` are chosen. Peers fill
   only what is left once the hiring side at every employer has been tried: while another
   employer could still be searched (`employers`), they are held back and the run says
   where to search next; `--peers` takes them now. Someone chosen before (on today's short
   list, or added by today's run) stays chosen and is never swapped for someone new.
   Fewer than wanted is said honestly, with the employers to widen to next, never padded.

A run on 2026-11-10 asked for five people at big employers filled its list with engineers
and peers, whom the person's own log shows answer least, while employers with no recruiter
in the city were never left for the next one; a re-check swapped a chosen person for one
whose headline reads as sales; and every employer was searched kind by kind, many of them
empty. `order` (and `search`, which uses it) puts the employers with people known in the
place first, from what is already known (the contact book and earlier checks), and skips
one an earlier check found empty there, for EMPTY_DAYS.

    python3 tools/network/candidates.py check <people.json|page.txt|-> ... [--company C]
        [--want N] [--place P] [--peers] [--add] [--shortlist] [--json]
    python3 tools/network/candidates.py employers [--used "<employer>" ...] [--most N]
    python3 tools/network/candidates.py order "<employer>" ... [--place P]
    python3 tools/network/candidates.py search "<employer>" ... [--place P] [--all]

`check` reads a JSON list of people ({name, title, company, location, linkedin_url}), the
list extractor's output (`reading.py extractor --list`), or a people page's text. `--add`
writes the chosen people into the contact book at not_contacted in one save (never a second
row for someone already there), and `--shortlist` puts them on today's short list for their
profile reads, best first. `search` prints the LinkedIn people-search addresses for each
employer and kind of reader, from the employer's company number and the place's location
number kept once (`reading.py company-ids`, `reading.py place-ids`): no web search.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

KINDS = ("founder", "hiring_leader", "recruiter", "senior_peer", "peer")
# Who can open a door (refer, hire, put them forward), and who works beside the role.
HIRING_SIDE = ("founder", "hiring_leader", "recruiter")
PEER_SIDE = ("senior_peer", "peer")
# An employer an earlier check found nobody for in a place is skipped this long.
EMPTY_DAYS = 30
KIND_WORDS = {"founder": "founders", "hiring_leader": "hiring leaders",
              "recruiter": "recruiters", "senior_peer": "senior people in the function",
              "peer": "peers"}
# Until the person has replies of their own to count, the app's order: those who can hire or
# open a door first. Points beside why_them's 0-100.
DEFAULT_KIND_POINTS = {"founder": 8, "hiring_leader": 6, "recruiter": 6, "senior_peer": 2,
                       "peer": 0}
# Their own rates move a kind by at most this many points either way, from enough messages.
RATE_POINTS = 15
RATE_MIN = 5
# A recruiter for their function, or for a near one.
OWN_RECRUITER, NEAR_RECRUITER = 8, 3
OWN_FUNCTION, OUT_OF_FUNCTION = 6, -4
SHARED = 15

# Specialisms a recruiter's headline or a role names, by family. The person's own families
# are the ones their function's words name (networking.py FUNCTION_TITLE and the "function"
# titles); a recruiter for another family is out, one for a near family ranks a little lower.
FAMILIES = {
    "technology": ("technology", "tech", "technical", "it", "software", "engineering",
                   "engineer", "engineers", "developer", "developers", "digital", "data",
                   "analytics", "ai", "machine learning", "cloud", "security"),
    "health": ("clinical", "nursing", "nurse", "nurses", "healthcare", "health", "medical",
               "allied health", "pharmacy", "physician", "physicians"),
    "sales": ("sales", "account executive", "business development", "go-to-market", "gtm",
              "revenue", "commercial"),
    "finance": ("finance", "financial", "corporate finance", "accounting", "audit", "tax",
                "treasury", "trading", "investment banking"),
    "marketing": ("marketing", "brand", "communications", "content", "creative", "media"),
    "design": ("design", "designer", "designers", "ux", "ui", "user experience",
               "user research"),
    "legal": ("legal", "counsel", "compliance"),
    "people": ("hr", "human resources", "people operations"),
    "operations": ("operations", "supply chain", "logistics", "warehouse", "manufacturing",
                   "procurement"),
    "education": ("teaching", "teacher", "teachers", "education", "academic"),
}
_RECRUIT_WORDS = re.compile(
    r"\b(?:senior|sr\.?|lead|principal|global|head of|director of|director|vp of|vp|"
    r"vice president of|manager|technical|"
    r"recruit\w*|talent\s+(?:acquisition|partner|sourcer|scout|lead|manager|advisor)|"
    r"partner|specialist|sourcer|consultant|coordinator|team|at|for|of|and|&)\b", re.I)


def settings() -> dict:
    """The person's settings for who to find, each with the app's safe default."""
    try:
        net = person.module("networking") if person.exists("networking.py") else None
    except Exception:  # noqa: BLE001  no profile: the app's defaults
        net = None
    skip = getattr(net, "SKIP_HEADLINES", None)
    if isinstance(skip, (list, tuple)):
        skip = re.compile(r"\b(?:" + "|".join(re.escape(str(w)) for w in skip if str(w).strip())
                          + r")\b", re.I) if any(str(w).strip() for w in skip) else None
    elif isinstance(skip, str):
        skip = re.compile(skip, re.I) if skip.strip() else None
    per_run = getattr(net, "PER_EMPLOYER_PER_RUN", None)
    return {"reply_rates": dict(getattr(net, "REPLY_RATES", None) or {}),
            "recruiter_near": tuple(str(w).lower() for w in
                                    (getattr(net, "RECRUITER_NEAR", None) or ())),
            "skip_headlines": skip,
            "per_run": int(per_run) if isinstance(per_run, int) and per_run > 0 else None}


# ---------------------------------------------------------------- what kind of reader

_FOUNDER = re.compile(r"\b(?:founder|co-?founder|ceo|owner|managing partner)\b", re.I)
# A recruiting leader whose title compose.is_recruiter leaves out ("Head of Talent").
_TALENT_LEAD = re.compile(r"\b(?:head|director|vp|vice president)\s+(?:of\s+)?(?:talent|"
                          r"recruit\w*)\b", re.I)


def is_recruiter(title: str) -> bool:
    import compose
    return compose.is_recruiter(title) or bool(_TALENT_LEAD.search(str(title or "")))


def kind_of(title: str) -> str:
    """founder, hiring_leader, recruiter, senior_peer or peer, from a headline."""
    import discovery
    t = " ".join(str(title or "").split())
    if is_recruiter(t):
        return "recruiter"
    if _FOUNDER.search(t):
        return "founder"
    if discovery.AUTHORITY_TITLE.search(t):
        return "hiring_leader"
    if discovery.SENIOR_IC_TITLE.search(t):
        return "senior_peer"
    return "peer"


def kind_rates(contacts=None, threads=None) -> dict:
    """{kind: (replied, decided)}: the person's own REPLY_RATES where they set them, else
    counted from their message log (first notes that were answered or went quiet)."""
    own = settings()["reply_rates"]
    if own:
        out = {}
        for k, v in own.items():
            try:
                out[str(k)] = (int(v[0]), int(v[1]))
            except (TypeError, ValueError, IndexError):
                continue
        return out
    try:
        import state
        import what_works
        contacts = state.load_contacts() if contacts is None else contacts
        threads = state.load_threads() if threads is None else threads
        titles = {str(c.get("contact_id") or ""): c.get("title", "") for c in contacts}
        out: dict = {}
        for c in what_works.message_cases(contacts, threads):
            if c["attempt"] != "opener":
                continue
            k = kind_of(titles.get(c["contact_id"], ""))
            won, n = out.get(k, (0, 0))
            out[k] = (won + int(bool(c["won"])), n + 1)
        return out
    except Exception:  # noqa: BLE001  no log: the app's order
        return {}


def kind_points(rates: dict) -> dict:
    """Points for each kind of reader: the app's order, moved by the person's own reply
    rates where a kind has RATE_MIN decided first notes, against their rate overall."""
    out = dict(DEFAULT_KIND_POINTS)
    won = sum(w for w, _n in rates.values())
    total = sum(n for _w, n in rates.values())
    if total < RATE_MIN:
        return out
    base = (won + 1) / (total + 2)
    for k, (w, n) in rates.items():
        if k in out and n >= RATE_MIN:
            rate = (w + 1) / (n + 2)
            out[k] = max(-RATE_POINTS, min(RATE_POINTS, round(3 * RATE_POINTS * (rate - base))))
    return out


# ---------------------------------------------------------------- the headline

# A headline that reads as selling (sales, business development, an account or partnership
# role), whatever field it names: "Cloud & Platform in Nordic Insurance" reads as an
# industry lead at a vendor; one such replaced a chosen fit on a re-check (2026-11-10). Never
# applied where the person's own function is sales, and the person's SKIP_HEADLINES adds
# their own words. "Sales analytics" and the like are data roles on sales, not selling.
SALES_HEADLINE = re.compile(
    r"\b(?:account (?:executive|manager|director|lead)|client (?:partner|executive|director|"
    r"lead|manager|solutions)|business development|bdr|sdr|"
    r"sales(?!\s+(?:analytics|analyst|data|insights?|science|engineering|intelligence|"
    r"forecasting|planning|operations? analy\w*))|pre-?sales|"
    r"solutions? (?:consultant|executive|specialist|sales)|go-to-market|gtm|"
    r"partnerships?|alliances?|channel (?:manager|partner|sales)|customer success|"
    r"relationship manager|territory (?:manager|lead)|field cto|"
    r"industry (?:lead|leader|director|principal|executive|advisor|specialist)|"
    r"(?:enterprise|key|strategic) accounts?)\b", re.I)
# The words that say what someone is: a headline with none of them, that names an industry
# or its clients ("... in Financial Services", "helping banks ..."), is a vendor's pitch.
_ROLE_NOUN = re.compile(
    r"\b(?:scientists?|engineers?|engineering|analysts?|developers?|managers?|directors?|head|"
    r"leads?|leaders?|vp|svp|evp|vice president|president|chief|officers?|founder|"
    r"co-?founder|owner|recruit\w*|researchers?|architects?|designers?|nurses?|teachers?|"
    r"consultants?|specialists?|associates?|interns?|student|professor|principal|advis[eo]r|"
    r"coordinator|administrator|technician|accountant|editor|writer|[a-z]{1,2}o|partner|"
    r"fellow|statistician|economist|actuary|modell?er|programmer|practitioner|"
    r"talent|hiring)\b", re.I)
_COVERAGE = re.compile(
    r"\b(?:in|for|across|serving|covering)\s+(?:the\s+)?(?:[\w&'’.-]+\s+){0,3}?"
    r"(?:financial services|banking|banks|insurance|insurers|capital markets|public sector|"
    r"government|healthcare|life sciences|retail|telecom\w*|industr(?:y|ies)|sectors?|"
    r"verticals?|enterprises?|clients|customers|accounts|markets)\b", re.I)
_PITCH = re.compile(r"\b(?:i help|helping|we help|enabling|empowering)\b[^|]{0,80}?\b(?:"
                    r"companies|organi[sz]ations|businesses|enterprises|teams|leaders|banks|"
                    r"insurers|clients|brands|firms|lenders)\b", re.I)
# A hiring signal in a headline: "Hiring!", "#hiring", "We're hiring data people". Not "hiring
# manager", which names a part in a process, not an opening.
_HIRING_HEADLINE = re.compile(r"(?<![\w-])#?(?:(?:we[’']?re|we are|now|actively)\s+)?"
                              r"hiring\b(?!\s+(?:managers?|process)\b)", re.I)


def hiring_signal(title: str) -> bool:
    """Does the headline say they are hiring?"""
    t = " ".join(str(title or "").split())
    if not t:
        return False
    if _HIRING_HEADLINE.search(t):
        return True
    try:
        import discovery
        return bool(discovery.HIRING_SIGNAL.search(t))
    except Exception:  # noqa: BLE001  no profile: the headline words alone
        return False


def sales_reading(title: str, own: set | None = None) -> str:
    """Why a headline reads as selling rather than doing the person's work, or "": a sales,
    account or partnership role (SALES_HEADLINE), or no role at all beside an industry it
    covers or the clients it helps. Never where the person's own function is sales."""
    own = own_families() if own is None else own
    if "sales" in own:
        return ""
    t = " ".join(str(title or "").split())
    m = SALES_HEADLINE.search(t)
    if m:
        return f"reads as a sales or business-development role ({m.group(0)})"
    if _ROLE_NOUN.search(t):
        return ""
    m = _COVERAGE.search(t) or _PITCH.search(t)
    if m:
        return (f"reads as selling to an industry, not a role in your function "
                f"(\"{m.group(0).strip()}\")")
    return ""


def _words_in(text: str, words) -> list:
    low = " " + re.sub(r"[^a-z0-9&+\-]+", " ", str(text or "").lower()) + " "
    return [w for w in words if f" {w} " in low]


def own_families() -> set:
    """The families the person's own function names (networking.py FUNCTION_TITLE and the
    "function" titles). All of them where it names nothing: nothing is then out for its
    family."""
    import discovery
    rx = discovery.FUNCTION_TITLE
    pat = getattr(rx, "pattern", ".")
    titles = " ".join(str(t) for t in discovery.TITLE_SETS.get("function") or [])
    if pat == "." and not titles.strip():
        return set(FAMILIES)
    out = {fam for fam, words in FAMILIES.items()
           if (pat != "." and any(rx.search(f" {w} ") for w in words))
           or _words_in(titles, words)}
    return out or set(FAMILIES)


def _specialism(title: str) -> str:
    """What a recruiter's headline says they recruit for: the headline without the words
    that only say they recruit."""
    rest = _RECRUIT_WORDS.sub(" ", str(title or ""))
    return " ".join(re.sub(r"[^\w&+\- ]|(?<!\w)-|-(?!\w)", " ", rest).split())


def headline_fit(title: str, company: str = "", sets: dict | None = None,
                 own: set | None = None) -> tuple:
    """(keep, points, why) for a search result's headline, before anything else: the
    person's own SKIP_HEADLINES, a role their search rules out (discovery.disqualify, an
    unrelated function), a recruiter for a function that is not theirs, a role in another
    family altogether. Kept ones carry points for how close the role is."""
    import discovery
    import reading
    sets = settings() if sets is None else sets
    own = own_families() if own is None else own
    t = " ".join(str(title or "").split())
    if not t:
        return True, -2, "no headline in the result: see what they do first"
    skip = sets["skip_headlines"]
    if skip is not None and skip.search(t):
        return False, 0, f"a headline you said never to show ({skip.search(t).group(0)})"
    why = discovery.disqualify({"title": t, "company": company}, company or None)
    if why:
        return False, 0, why
    fn = discovery.FUNCTION_TITLE
    in_fn = getattr(fn, "pattern", ".") != "." and bool(fn.search(t))
    if is_recruiter(t):
        spec = _specialism(t)
        near = sets["recruiter_near"]
        if spec and getattr(fn, "pattern", ".") != "." and fn.search(spec):
            return True, OWN_RECRUITER, f"a recruiter for your function ({spec})"
        if spec and near and _words_in(spec, near):
            return True, NEAR_RECRUITER, f"a recruiter for {_words_in(spec, near)[0]}, near your function"
        fams = {f for f, ws in FAMILIES.items() if _words_in(spec, ws)}
        if fams and not fams & own:
            return False, 0, f"recruits for {spec}, not your function"
        if fams & own:
            return True, NEAR_RECRUITER, f"a recruiter for {spec}, near your function"
        return True, 0, "a recruiter; their headline does not say for which teams"
    if not _FOUNDER.search(t):
        sold = sales_reading(t, own)
        if sold:
            return False, 0, sold
    rank, fit = reading.title_fit(t)
    if rank == 0:
        return False, 0, fit
    if in_fn or rank >= 3:
        return True, OWN_FUNCTION, fit or "a role in your function"
    if _FOUNDER.search(t):
        return True, 0, "runs the company"
    fams = {f for f, ws in FAMILIES.items() if _words_in(t, ws)}
    if fams and not fams & own:
        return False, 0, f"a {sorted(fams)[0]} role, not your function"
    if rank >= 2:
        return True, OWN_FUNCTION, fit or "a role in your function"
    return True, OUT_OF_FUNCTION if not fams else 0, fit or "the headline names nothing of your function"


def shared_background(p: dict, hist: dict | None = None) -> str:
    """An employer the person has left, or their school, named in the result, or ""."""
    import reading
    hist = reading.history() if hist is None else hist
    text = " ".join(str(p.get(k) or "") for k in ("title", "headline", "summary", "snippet"))
    current = {company_key(c) for c in hist.get("current") or ()}
    for names in hist.get("employers") or ():
        if company_key(names[0]) in current:
            continue
        if any(reading._has(n, text) for n in names if len(n) > 2):
            return f"worked at {names[0]}, like you"
    for s in hist.get("schools") or ():
        if reading._has(s, text):
            return f"studied at {s}, like you"
    return ""


# ---------------------------------------------------------------- the one call

def _person(p: dict, company: str = "") -> dict:
    title = p.get("title") or p.get("headline") or ""
    emp = p.get("company") or p.get("employer") or company or ""
    return {**p, "name": " ".join(str(p.get("name") or "").split()), "title": title,
            "company": " ".join(str(emp).split()),
            "linkedin_url": p.get("linkedin_url") or p.get("url") or ""}


def _chosen_before(rows, msgs, listed: set, today: datetime.date) -> str:
    """The contact id of someone a run already chose, or "": in the book, nobody has written
    to them, and they are on today's short list or a people search added them today. A
    second check had them out as "already in your contact book" and filled their place
    with someone new (2026-11-10)."""
    import state
    if msgs:
        return ""
    for r in rows:
        cid = str(r.get("contact_id") or "").strip()
        if state.effective_status(r, ()) != "not_contacted":
            continue
        notes = str(r.get("notes") or "")
        if cid in listed or (f"added {today.isoformat()}" in notes
                             and "found by a people search" in notes):
            return cid
    return ""


def _todays_list(today: datetime.date) -> set:
    try:
        import reading
        return set(reading._shortlist_file(today))
    except Exception:  # noqa: BLE001  no short list yet
        return set()


def kind_order(points: dict) -> dict:
    """{kind: its place}, best-answering first by the person's points; kinds with the same
    points share a place, and the score decides between them."""
    ranks = sorted({points.get(k, 0) for k in KINDS}, reverse=True)
    return {k: ranks.index(points.get(k, 0)) for k in KINDS}


def peers_last(points: dict) -> bool:
    """Do peers wait for the hiring side? Unless the person's own replies say peers answer
    them better than every kind on the hiring side."""
    return max(points.get(k, 0) for k in PEER_SIDE) <= max(points.get(k, 0) for k in HIRING_SIDE)


def check(people, company: str = "", want: int | None = None, contacts=None, threads=None,
          today: datetime.date | None = None, peers: bool | None = None,
          place: str = "") -> dict:
    """{"chosen", "ranked", "out", "want", "short", "employers", "peers_held",
    "peers_filled", "next_employers", "kept", "seen"}: everyone found, through every check
    once, ranked, and the list chosen from the best. `out` is [(person, why)].

    `peers`: None holds peers back while another employer could still be searched for the
    hiring side (`employers`), True lets them fill what is left now, False never."""
    import surface
    import why as why_mod
    import state
    today = today or person.today()
    contacts = state.load_contacts() if contacts is None else contacts
    threads = state.load_threads() if threads is None else threads
    sets = settings()
    own = own_families()
    points = kind_points(kind_rates(contacts, threads))
    order = kind_order(points)
    try:
        import reading
        hist = reading.history()
    except Exception:  # noqa: BLE001  no roles.py: nothing shared to find
        hist = {}
    ctx = surface.context(contacts=contacts, threads=threads, today=today)
    by = state.by_contact(threads)
    ctx["book"] = ix = ctx.get("book") or surface._book_index(contacts)
    listed = _todays_list(today)
    seen, ranked, out = set(), [], []
    for raw in people or ():
        if not isinstance(raw, dict):
            continue
        p = _person(raw, company)
        if not (p["name"] or p["linkedin_url"]):
            continue
        key = state.profile_handle(p["linkedin_url"]) or \
            f"{state._match_name(p['name'])}@{company_key(p['company'])}"
        if key in seen:
            continue                     # twice on one list is once
        seen.add(key)
        rows, _how = surface.in_book(contacts, p["name"], p["company"], p["linkedin_url"],
                                     str(p.get("contact_id") or ""), index=ix)
        msgs = [m for r in rows for m in by.get(str(r.get("contact_id") or "").strip(), ())
                if state._direction(m)]
        kept = _chosen_before(rows, msgs, listed, today) if rows else ""
        keep, pts, fit = headline_fit(p["title"], p["company"], sets, own)
        warn = []
        if kept:
            if not keep:
                warn.append(f"chosen already, though {fit}: take them off only if you say so "
                            f"(reading.py shortlist --remove {kept})")
                keep, pts, fit = True, 0, ""
            got = {"show": True, "warn": warn, "contact_id": kept, "reopen": ""}
        if not keep:
            out.append((p, fit))
            continue
        if not kept:
            place_ = surface.outside_market(p.get("location") or "") or (
                surface.outside_market(rows[0].get("location") or "") if rows else "")
            if place_:
                out.append((p, f"lives in {place_}, outside where you are looking"))
                continue
            got = surface.check(p, ctx, again_after_run=True)
            if not got["show"]:
                out.append((p, got["reason"]))
                continue
        kind = kind_of(p["title"])
        w = why_mod.why_them({**p, "tier": p.get("tier", "")}, {}, today=today)
        if w["skip"] and not kept:
            out.append((p, w["line"]))
            continue
        reasons = [(pts, fit)] if fit and pts else []
        kp = points.get(kind, 0)
        if kp:
            reasons.append((kp, f"{KIND_WORDS[kind]} answer you more often" if kp > 0
                            else f"{KIND_WORDS[kind]} answer you less often"))
        hiring = hiring_signal(p["title"])
        if hiring:
            reasons.append((10, "says they are hiring"))
        shared = shared_background(p, hist) if hist else ""
        if shared:
            reasons.append((SHARED, shared))
        score = max(0, min(100, w["score"] + sum(x for x, _y in reasons)))
        line = "; ".join([y for x, y in sorted(reasons, key=lambda r: -r[0]) if x > 0]
                         + [w["line"]])
        ranked.append({**p, "kind": kind, "score": score, "why": line, "hiring": hiring,
                       "kept": bool(kept), "warn": got["warn"],
                       "contact_id": got["contact_id"], "reopen": got.get("reopen", "")})
    # Kept first, then the kind of reader by the person's replies, then a hiring signal,
    # then the score.
    ranked.sort(key=lambda r: (not r["kept"], order.get(r["kind"], 9), not r["hiring"],
                               -r["score"]))
    # The list: each employer to its limit, counting the people already waiting.
    ctx2 = surface.context(contacts=contacts, threads=threads, today=today)
    ctx2["count_list"] = True
    chosen, per_run = [], {}
    wait_peers = peers_last(points)

    def take(r) -> bool:
        k = company_key(r["company"])
        if not r["kept"] and sets["per_run"] and k and per_run.get(k, 0) >= sets["per_run"]:
            r["held"] = f"{sets['per_run']} at {r['company']} this run already, as you set"
            return False
        full = "" if r["kept"] else surface.employer_full(r["company"], ctx2, f"list:{len(chosen)}")
        if full:
            r["held"] = full
            return False
        ctx2["shown"][f"list:{len(chosen)}"] = {"name": r["name"], "company": r["company"]}
        per_run[k] = per_run.get(k, 0) + 1
        chosen.append(r)
        return True

    def room() -> bool:
        return want is None or len(chosen) < want

    later = []
    for r in ranked:
        if r["kept"]:
            take(r)                         # never swapped for someone new
        elif wait_peers and r["kind"] in PEER_SIDE:
            later.append(r)
        elif room():
            take(r)
    held, filled, nxt = [], 0, []
    if later and room():
        allow = peers if peers is not None else None
        if want is None:
            allow = True if allow is None else allow
        if allow is None:
            used = sorted({r["company"] for r in ranked if r["company"]}
                          | {p_["company"] for p_, _w in out if p_.get("company")}
                          | ({company} if company else set()))
            nxt = employers(used, most=5, contacts=contacts, today=today)
            allow = not nxt
        if allow:
            for r in later:
                if not room():
                    break
                if take(r):
                    filled += 1
        else:
            held = later
            for r in later:
                r["held"] = ("a peer: the hiring side at the next employers comes first "
                             "(--peers takes them now)")
    short = max(0, (want or 0) - len(chosen)) if want else 0
    hiring_less = sorted({r["company"] for r in later if r["company"]}
                         - {r["company"] for r in chosen if r["kind"] in HIRING_SIDE})
    return {"chosen": chosen, "ranked": ranked, "out": out, "want": want, "short": short,
            "employers": sorted({r["company"] for r in chosen if r["company"]}),
            "peers_held": [r["name"] for r in held], "peers_filled": filled,
            "next_employers": [e for e, _w in nxt], "no_hiring_side": hiring_less,
            "kept": [r["name"] for r in chosen if r["kept"]],
            "seen": _seen(people, ranked, out, company)}


def _seen(people, ranked, out, company: str) -> dict:
    """{employer: (people found there, people who fit)} for what a check saw: the record
    `order` reads next time."""
    found: dict = {}
    for raw in people or ():
        if isinstance(raw, dict):
            emp = str(raw.get("company") or raw.get("employer") or company or "").strip()
            if emp:
                found.setdefault(emp, [0, 0])[0] += 1
    for r in ranked:
        if r.get("company"):
            found.setdefault(r["company"], [0, 0])[1] += 1
    if company and company not in found:
        found[company] = [0, 0]
    return {k: tuple(v) for k, v in found.items()}


# ---------------------------------------------------------------- the first pass

def _where_file() -> str:
    return person.state("documents", "network", ".people_seen.json")


def _where() -> dict:
    try:
        with open(_where_file(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _place_key(place: str) -> str:
    return " ".join(str(place or "").lower().split()) or "anywhere"


def record_seen(seen: dict, place: str = "", today: datetime.date | None = None) -> None:
    """Keep what a check saw at each employer in a place, dated: who was found and who fit.
    An employer with nobody who fits is skipped by `order` for EMPTY_DAYS."""
    if not seen:
        return
    today = today or person.today()
    data = _where()
    pk = _place_key(place)
    for emp, (found, fit) in seen.items():
        k = company_key(emp)
        if not k:
            continue
        data.setdefault(k, {})[pk] = {"employer": emp, "date": today.isoformat(),
                                      "found": int(found), "fit": int(fit)}
    path = _where_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
            fh.write("\n")
    except OSError:
        pass                                # a record missed costs a search, nothing more


def _in_place(location: str, place: str) -> bool:
    loc = " ".join(str(location or "").lower().split())
    pl = _place_key(place)
    return pl == "anywhere" or (bool(loc) and pl.split(",")[0].strip() in loc)


def order(names, place: str = "", contacts=None, today: datetime.date | None = None) -> list:
    """[(employer, why, skip)] best first: the employers where people who fit are known in
    the place (the contact book: someone there in the function or on the hiring side, never
    closed by the person; an earlier check that found some), then those with a company
    number kept (one search away), then the rest, each in the order given. `skip` is the
    reason an employer is left out today: an earlier check found nobody who fits in the
    place within EMPTY_DAYS. From what is already known only: no web search."""
    import state
    today = today or person.today()
    contacts = state.load_contacts() if contacts is None else contacts
    seen = _where()
    pk = _place_key(place)
    sets = settings()
    own = own_families()
    known: dict = {}
    for c in contacts or ():
        k = state.row_company_key(c)
        if not k or not _in_place(c.get("location") or "", place):
            continue
        if str(c.get("status") or "") in ("dropped",) or (
                str(c.get("status") or "") == "closed" and not state.closed_by_a_run(c)):
            continue
        keep, _pts, _fit = headline_fit(c.get("title") or "", c.get("company") or "", sets, own)
        if keep and (c.get("title") or "").strip():
            known[k] = known.get(k, 0) + 1
    try:
        import reading
        ids = (reading._filters().get("employers") or {})
    except Exception:  # noqa: BLE001
        ids = {}
    rows = []
    for i, name in enumerate(dict.fromkeys(str(n).strip() for n in names if str(n).strip())):
        k = company_key(name)
        rec = (seen.get(k) or {}).get(pk) or {}
        when = state.as_date(rec.get("date"))
        age = (today - when).days if when else None
        if rec and not rec.get("fit") and age is not None and age < EMPTY_DAYS:
            again = when + datetime.timedelta(days=EMPTY_DAYS)
            rows.append((3, i, name, "", f"searched {when.isoformat()}: nobody who fits in "
                         f"{place or 'the search'}; looked at again from {again.isoformat()}"))
            continue
        n = known.get(k, 0)
        fit = int(rec.get("fit") or 0) if age is not None and age < 2 * EMPTY_DAYS else 0
        if n or fit:
            why = "; ".join(x for x in (
                f"{n} in your contact book there" if n else "",
                f"{fit} who fit found on {rec['date']}" if fit else "") if x)
            rows.append((0, i, name, why, ""))
        elif ids.get(k) and not ids[k].get("wrong"):
            rows.append((1, i, name, "its company number is kept: one search away", ""))
        else:
            rows.append((2, i, name, "nothing known there yet", ""))
    rows.sort(key=lambda r: (r[0], -_n_known(r[3]), r[1]))
    return [(name, why, skip) for _g, _i, name, why, skip in rows]


def _n_known(why: str) -> int:
    m = re.match(r"(\d+)", why or "")
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- widening

def employers(used=(), most: int = 10, contacts=None, today=None, place: str = "") -> list:
    """[(employer, why)]: where to search next when a run is short, best first: employers
    with a role the person scored well in the latest round, then their own employer lists
    (employers.py TIER_1, TIER_2), then employers judged to clear their bar. Never one this
    run used, one the one check rules out, or one already at its limit of people waiting."""
    import surface
    import state
    contacts = state.load_contacts() if contacts is None else contacts
    today = today or person.today()
    ctx = surface.context(contacts=contacts, today=today)
    done = {company_key(u) for u in used if str(u).strip()}
    pool: list = []
    try:
        import glob
        import why as why_mod
        from run_round import round_order
        files = sorted(glob.glob(os.path.join(glob.escape(person.state("documents", "rounds")),
                                              "*.json")), key=round_order)
        for path in reversed(files):
            if os.path.basename(path).startswith("."):
                continue
            with open(path, encoding="utf-8") as fh:
                rows = json.load(fh)
            if isinstance(rows, list) and rows:
                good = sorted((r for r in rows if isinstance(r, dict)
                               and (r.get("fit") or 0) >= why_mod.ROLE_FIT_FLOOR),
                              key=lambda r: -(r.get("fit") or 0))
                pool += [(r.get("company", ""), f"a role you scored {r.get('fit')} there")
                         for r in good]
                break
    except Exception:  # noqa: BLE001  no rounds: the lists alone
        pass
    try:
        import opportunity
        for t, label in ((getattr(opportunity, "TIER_1", ()), "on your first list"),
                         (getattr(opportunity, "TIER_2", ()), "on your second list")):
            pool += [(str(n), label) for n in sorted(t or ())]
    except Exception:  # noqa: BLE001
        pass
    try:
        import bar
        for _k, r in sorted(bar.judged().items()):
            if isinstance(r, dict) and r.get("verdict") in (bar.PAY, bar.PRESTIGE, bar.SIGNAL):
                pool.append((r.get("name") or _k, f"judged to clear your bar ({r['verdict']})"))
    except Exception:  # noqa: BLE001
        pass
    out, seen = [], set(done)
    for name, why_ in pool:
        k = company_key(name)
        if not k or k in seen:
            continue
        seen.add(k)
        if surface.employer_out(name, today) or surface.employer_full(name, ctx):
            continue
        out.append((name, why_))
        if len(out) >= most * 3:
            break
    # The first pass: known people in the place first, known-empty ones left out.
    whys = dict(out)
    ranked = [(n, whys[n]) for n, _w, skip in order([n for n, _ in out], place,
                                                     contacts=contacts, today=today) if not skip]
    return ranked[:most]


def search_urls(company: str, place: str = "") -> list:
    """[(kind, address)] of the LinkedIn people searches for this employer, one a kind of
    reader that helps, the person's best-answering kinds first; [] with the reason raised as
    LookupError when no company number is kept for it."""
    import discovery
    import reading
    pts = kind_points(kind_rates())
    groups = [("recruiter", "recruiting"), ("hiring_leader", "hiring_authority"),
              ("senior_peer", "senior_ic"), ("peer", "function")]
    groups.sort(key=lambda g: -pts.get(g[0], 0))
    out = []
    for kind, group in groups:
        titles = [t for t in discovery.TITLE_SETS.get(group) or [] if str(t).strip()]
        if not titles:
            continue
        words = " OR ".join('"%s"' % t for t in titles[:reading.FUNCTION_KEYWORDS])
        out.append((kind, reading.search_url(company, place, words)))
    return out


# ---------------------------------------------------------------- the command

def load_people(text: str, company: str = "") -> list:
    """People from a JSON list, the list extractor's output, or a people page's text."""
    import reading
    t = str(text or "").strip()
    if t.startswith("["):
        got = json.loads(t)
        return [p for p in got if isinstance(p, dict)]
    if t.startswith("{"):
        got = json.loads(t)
        if isinstance(got, dict) and isinstance(got.get("people"), list):
            return got["people"]
        if isinstance(got, dict) and isinstance(got.get("ranked"), list):
            return got["ranked"]             # an earlier check's --json: checked again, at once
        if reading._list_json(t):
            return reading.people_page(reading.from_list_extract(t), company)
    return reading.people_page(t, company)


def _add(chosen, contacts, today) -> list:
    """Each chosen person into the contact book at not_contacted, one save for all."""
    import state
    lines = []
    for r in chosen:
        if r.get("reopen"):
            # Closed by an earlier run, not by the person, and chosen again today.
            row = state.already_contacted(contacts, contact_id=r["reopen"])
            if row is not None and str(row.get("status") or "") == "closed":
                state.reopen(contacts, [], r["reopen"], today,
                             "found again by a people search; the earlier close was a run's, "
                             "not yours")
                lines.append(f"  opened again: {r['name']} ({r['reopen']}), closed by an earlier "
                             "run, not by you")
            continue
        if r.get("contact_id"):
            continue
        try:
            row, how = state.add_contact(contacts, r["name"], r["company"], today,
                                         title=r.get("title", ""),
                                         linkedin_url=r.get("linkedin_url", ""),
                                         location=r.get("location", ""),
                                         route=r.get("route", ""),
                                         note=f"found by a people search: {r['why'][:120]}")
        except ValueError as e:
            lines.append(f"  not added: {r['name']}: {e}")
            continue
        r["contact_id"] = row["contact_id"]
        if how == "added":
            row["found_via"] = row.get("found_via") or r.get("found_via", "") or "people_tab"
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="candidates.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="every check, the headline filter and the ranking, at once")
    c.add_argument("files", nargs="+", help="people as JSON, the list extractor's output, a "
                   "page's text or an earlier check's --json, one or several; - for stdin")
    c.add_argument("--company", default="", help="the employer the search was narrowed to")
    c.add_argument("--want", type=int, default=None, help="how many the run is to find")
    c.add_argument("--place", default="", help="the place the search was narrowed to")
    c.add_argument("--peers", action="store_true",
                   help="let peers fill what is left now, before other employers are tried")
    c.add_argument("--add", action="store_true", help="add the chosen to the contact book")
    c.add_argument("--shortlist", action="store_true", help="put the chosen on today's short list")
    c.add_argument("--json", action="store_true")
    e = sub.add_parser("employers", help="where to search next when a run is short")
    e.add_argument("--used", nargs="*", default=[])
    e.add_argument("--most", type=int, default=10)
    e.add_argument("--place", default="", help="the place, so employers known empty there wait")
    o = sub.add_parser("order", help="the employers to search first, from what is known")
    o.add_argument("employers", nargs="+")
    o.add_argument("--place", default="")
    s = sub.add_parser("search", help="LinkedIn people-search addresses, by kind of reader")
    s.add_argument("employers", nargs="+")
    s.add_argument("--place", default="")
    s.add_argument("--all", action="store_true",
                   help="also the employers an earlier check found nobody for in the place")
    a = ap.parse_args(argv)
    if a.cmd == "employers":
        got = employers(a.used, a.most, place=a.place)
        if not got:
            print("employers: none left that clear your bar and have room: ask the person for "
                  "more employers they would like, or names they know of")
            return 1
        for name, why_ in got:
            print(f"  {name}: {why_}")
        return 0
    if a.cmd == "order":
        for name, why_, skip in order(a.employers, a.place):
            print(f"  {'skip' if skip else 'next'}  {name}: {skip or why_}")
        return 0
    if a.cmd == "search":
        bad = 0
        ranked = order(a.employers, a.place)
        skipped = [(n, sk) for n, _w, sk in ranked if sk and not a.all]
        for n, sk in skipped:
            print(f"  {n}: skipped, {sk} (--all searches it anyway)")
        todo = [n for n, _w, sk in ranked if a.all or not sk]
        if not todo:
            return 1
        for emp in todo:
            try:
                for kind, url in search_urls(emp, a.place):
                    print(f"  {emp} [{KIND_WORDS[kind]}]: {url}")
            except LookupError as err:
                print(f"  {emp}: {err}")
                bad += 1
        return 1 if bad == len(todo) else 0
    import state
    people = []
    for f in a.files:
        text = sys.stdin.read() if f == "-" else open(f, encoding="utf-8").read()
        try:
            people += load_people(text, a.company)
        except ValueError as err:
            print(f"candidates: {f} is not a list of people ({err})")
            return 1
    contacts = state.load_contacts()
    today = person.today()
    got = check(people, a.company, a.want, contacts=contacts, today=today,
                peers=True if a.peers else None, place=a.place)
    record_seen(got["seen"], a.place, today)
    added = []
    if a.add and got["chosen"]:
        added = _add(got["chosen"], contacts, today)
        state.save_contacts(contacts)
    if a.shortlist and got["chosen"]:
        import reading
        sl = reading.shortlist([r["contact_id"] for r in got["chosen"] if r.get("contact_id")],
                               today=today, contacts=contacts)
        added.append(f"  on today's short list: {len(sl['ids'])}"
                     + (f"; drafted from the card, no read needed: {', '.join(sl['card_enough'])}"
                        if sl.get("card_enough") else ""))
    if a.json:
        print(json.dumps({k: v for k, v in got.items() if k != "out"}
                         | {"out": [{"name": p["name"], "company": p["company"], "why": w}
                                    for p, w in got["out"]]}, ensure_ascii=False, indent=1))
        return 0
    n = len(got["chosen"])
    print(f"candidates: {len(people)} found, {len(got['out'])} out, {len(got['ranked'])} fit, "
          f"{n} chosen" + (f" of the {a.want} wanted" if a.want else ""))
    for r in got["chosen"]:
        cid = f" [{r['contact_id']}]" if r.get("contact_id") else ""
        print(f"  {r['score']:>3}  {r['name']}, {r['title'] or '?'}, {r['company']}{cid}: "
              f"{r['why']}" + "".join(f"\n       {w}" for w in r.get("warn") or ()))
    held = [r for r in got["ranked"] if r.get("held")]
    for r in held[:5]:
        print(f"  held: {r['name']} ({r['company']}): {r['held']}")
    reasons: dict = {}
    for p, w in got["out"]:
        reasons.setdefault(w.split(":")[0][:80], []).append(p["name"])
    for w, names in sorted(reasons.items(), key=lambda x: -len(x[1]))[:8]:
        print(f"  out, {len(names)}: {w} ({', '.join(names[:3])}"
              + (" ..." if len(names) > 3 else "") + ")")
    for line in added:
        print(line)
    if got["kept"]:
        print(f"  kept, chosen before: {', '.join(got['kept'])} (never swapped for someone new)")
    if got["peers_filled"]:
        print(f"  peers: {got['peers_filled']} of the list, after the recruiters, hiring leaders "
              "and founders at every employer tried")
    if got["peers_held"]:
        print(f"  peers held back: {len(got['peers_held'])} ({', '.join(got['peers_held'][:4])}"
              + (" ..." if len(got["peers_held"]) > 4 else "") + "). Recruiters, hiring leaders "
              "and founders come first"
              + (f": none found at {', '.join(got['no_hiring_side'])}" if got["no_hiring_side"]
                 else "")
              + ", so search the next employers first ("
              + "; ".join(got["next_employers"]) + "), then check again; --peers takes them "
              "now")
    if got["short"]:
        more = employers(got["employers"] + [a.company] if a.company else got["employers"],
                         most=5, contacts=contacts, today=today, place=a.place)
        print(f"short: {got['short']} more to find. Never padded: widen to the next employers "
              + ("(" + "; ".join(f"{e} ({w})" for e, w in more) + ")" if more else
                 "(none left that clear your bar: say so honestly, and ask for more employers "
                 "or names they know)")
              + ": candidates.py search \"<employer>\", then check again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
