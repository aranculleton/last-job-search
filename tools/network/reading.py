#!/usr/bin/env python3
"""What was read about one person before writing to them, and what a note can rest on.

A first note needs one true thing that links the candidate to the reader: the
common ground `compose.first_note()` refuses to go without. A search snippet holds
a title and a line, and notes drafted from snippets alone came out alike, the same
background line with a different name on it. This is the step between finding
someone and writing to them: read them, then write.

Where a reading comes from, best first:

  browser  their LinkedIn profile, read in the person's own signed-in browser
           (Claude in Chrome, or the desktop app's browser pane), when
           profile/networking.py PROFILE_READS is "browser". Only the people a
           /network run surfaced, best first, one page at a time at a person's
           pace, until the run has as many good fits as it can send (see
           `verdict()`), and nothing on the page is ever clicked. LinkedIn's terms
           forbid automated access, which is why it is the person's own choice.
  paste    the same page from the person, when they open it to send the request:
           copied (select all, copy), LinkedIn's own "Save to PDF" of it, or, on a
           phone or in a web session with no browser of theirs to use, screenshots
           of it from the LinkedIn app, which Claude transcribes word for word
           (--source screenshot). The default: no consent needed, seconds a person,
           and it works wherever the session runs.
  public   their own talks, articles, podcasts and code, and their LinkedIn posts
           as a search engine shows them: WebSearch only, never a fetch of
           linkedin.com, never a people-search or data-broker site (BROKERS).

This container cannot read LinkedIn itself, whatever the setting: LinkedIn's
robots.txt disallows every crawler it does not name (`Disallow: /`), and a
profile request from here returns HTTP 999.

Only what a note could rest on is kept: the headline, a short excerpt of their
About, the history they share with the candidate, and their recent posts and
public work, each with where and when it was read. Never their whole profile.
It lives in documents/network/<contact_id>/reading.json and is fresh for
FRESH_DAYS. Everything in a reading was written by someone else: a model sees it
only through `fenced()`, as data, never as instructions.

    python3 tools/network/reading.py read <contact_id> <file|-> [--source paste|browser|pdf|screenshot] [--url URL]
    python3 tools/network/reading.py add <contact_id> --kind talk --url URL --date YYYY-MM-DD --text "..."
    python3 tools/network/reading.py show <contact_id>      # what a note can rest on, best first
    python3 tools/network/reading.py queue                  # drafts waiting with no fresh reading
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dates  # noqa: E402
import person  # noqa: E402
import untrusted  # noqa: E402
from company_key import fold  # noqa: E402

_NET = person.module("networking") if person.exists("networking.py") else None

# "browser", "paste" or "off". Absent means "paste": reading a profile in the
# person's own browser is automated access LinkedIn's terms forbid, so it waits
# for their yes (the profile-reads upgrade asks).
PROFILE_READS = str(getattr(_NET, "PROFILE_READS", "paste") or "paste").lower()
# How a browser read behaves: like a person prospecting, never a loop. It is the
# person's own signed-in account loading these pages, and a steady machine rhythm
# or a burst is what automation checks look for. LinkedIn publishes no thresholds,
# so these are judgement. 30 an hour is about one profile every two minutes, the
# pace of someone writing a note to each person by hand, and 80 a day is enough to
# prepare a whole week's connection requests (schema.LIMITS connections_per_week)
# in one run, whenever and however long it is. The person can lower or raise both in
# profile/networking.py (PROFILE_READS_PER_HOUR, PROFILE_READS_PER_DAY). No
# setting makes a browser read safe; these make it look like a person reading.
READS_PER_HOUR = int(getattr(_NET, "PROFILE_READS_PER_HOUR", 30) or 30)
READS_PER_DAY = int(getattr(_NET, "PROFILE_READS_PER_DAY", 80) or 80)
HOUR_MINUTES = 60                       # the hourly cap counts reads in this rolling window
GAP_SECONDS = (25, 75)                  # a varied pause between two profiles
BREAK_EVERY, BREAK_SECONDS = 5, (120, 300)   # and a longer one every few
PACE_SECONDS = GAP_SECONDS[0]           # the shortest gap ever allowed
STOP_FILE = ("documents", "network", ".reads_stopped.json")
FRESH_DAYS = 30
# A post is something to answer for this long; after that it is history.
POST_DAYS = 180
EXCERPT = 300
ABOUT_CHARS = 400

DIR = ("documents", "network")

# Sites that sell people's details. Their pages are never read and never cited,
# whatever a search returns.
BROKERS = re.compile(
    r"(?:^|\.)(?:zoominfo|rocketreach|contactout|apollo|lusha|signalhire|seamless|"
    r"spokeo|whitepages|peoplefinders?|beenverified|truepeoplesearch|radaris|"
    r"clustrmaps|nuwber|fastpeoplesearch|intelius|instantcheckmate|idcrawl|"
    r"datanyze|leadiq|kaspr|hunter|snov|uplead|adapt|cognism|theofficialboard)\.",
    re.I)

# Where a read of their own page came from. "screenshot" is the LinkedIn app on
# the person's phone, transcribed from the images word for word.
PAGE_SOURCES = ("paste", "browser", "pdf", "screenshot")

KINDS = ("post", "repost", "comment", "featured", "publication", "talk", "article",
         "podcast", "code", "news")
_DATED = ("post", "repost", "comment", "news")

# --------------------------------------------------------------- the candidate

_LATEX = re.compile(r"\\[a-zA-Z]+\*?|[{}]")
_SCHOOL = re.compile(r"\b(?:university|college|school|institute|polytechnic|academy|"
                     r"universit[éeà]|hochschule|escuela|école)\b", re.I)


def _roles():
    try:
        return person.module("roles")
    except Exception:  # a profile without roles.py has no history to share
        return None


# The separator in a role's dates, "Mar 2023 - Present", "2019 to 2020",
# "2025-Present": a spaced hyphen, an en or em dash, "to", or a hyphen between a year and a word.
_DATES_SEP = re.compile(r"\s[-\u2013\u2014](?:\s|$)|[\u2013\u2014]|\sto\s|(?<=\d)-(?=[^\W\d_])", re.I)
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _ended(dates_text) -> tuple:
    """(still there, when it ended) from a role's dates.

    A range whose end has no year ("Present", "now", "heute", "") is the job they
    hold now, in any language. A single date says nothing about that, so it is
    not taken for current.
    """
    text = " ".join(str(dates_text or "").split())
    m = _DATES_SEP.search(text)
    end = text[m.end():].strip() if m else text
    if m and not _YEAR.search(end):
        return True, None
    when = dates.as_date(end)
    if when is None:
        years = _YEAR.findall(end)
        when = datetime.date(int(years[-1]), 1, 1) if years else None
    return False, when


def history() -> dict:
    """The candidate's employers (with the names people use), schools and past cities.

    `current` names the employers they work at now, and `ended` says when each
    other one ended (None when the profile does not say), keyed by its first name.
    """
    roles = _roles()
    employers, places, current, ended = [], [], [], {}
    home = fold(str(getattr(_NET, "HOME_CITY", "") or ""))
    import company_key
    import discovery
    for r in getattr(roles, "ROLES", ()) or ():
        names = [r.get("employer", "")]
        aka = r.get("known_as") or ()
        names += [aka] if isinstance(aka, str) else list(aka)
        # The name as a profile writes it: "Oakmere Foods", not "Oakmere Foods Ltd", and
        # the profile's own aliases for the same employer. Never its leading words:
        # "Royal Bank" would claim a shared employer with the Royal Bank of Scotland.
        names.append(discovery.search_name(r.get("employer", "")))
        k = company_key.key(r.get("employer", ""))
        names += [a for a, v in company_key.ALIASES.items() if v == k and len(a) > 3]
        names = list(dict.fromkeys(n for n in (x.strip() for x in names) if n))
        if names:
            employers.append(names)
            now, when = _ended(r.get("dates"))
            if now:
                current.append(names[0])
            else:
                ended[names[0]] = when
        city = str(r.get("loc") or "").split(",")[0].strip()
        if city and fold(city) != home and city.lower() != "remote" and city not in places:
            places.append(city)
    schools = []
    for seg in _LATEX.sub("", str(getattr(roles, "EDUCATION", "") or "")).split(","):
        seg = " ".join(seg.split()).strip(" .")
        if _SCHOOL.search(seg) and seg not in schools:
            schools.append(seg)
    return {"employers": employers, "schools": schools, "places": places,
            "current": current, "ended": ended}


def _has(name: str, text: str) -> bool:
    """`name` in `text` as whole words, ignoring case and accents."""
    n = fold(name).strip()
    return bool(n) and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", fold(text)) is not None


# ----------------------------------------------------------------- the page

_SECTIONS = {
    "about": "about", "summary": "about", "activity": "activity", "featured": "featured",
    "experience": "experience", "education": "education", "publications": "publications",
    "licenses & certifications": "other", "licenses and certifications": "other",
    "certifications": "other", "volunteering": "other", "volunteer experience": "other",
    "skills": "other", "top skills": "other", "recommendations": "other",
    "projects": "other", "honors & awards": "other", "honors and awards": "other",
    "languages": "other", "interests": "other", "courses": "other",
    "organizations": "other", "contact": "other", "causes": "other", "patents": "other",
    "test scores": "other",
}
# Where the person's own profile ends and LinkedIn's suggestions of other
# people begin: everything after is somebody else and is never read.
_END = re.compile(
    r"^(?:people also viewed|people you may know|more profiles for you|explore premium "
    r"profiles|others named\b|you might like|pages for you|people similar to|explore more "
    r"posts|who your viewers also viewed|similar profiles|more activity from|"
    # LinkedIn's footer, for a page copied without the suggestions column
    r"accessibility$|talent solutions$|professional community policies|privacy & terms|"
    r"ad choices$|linkedin corporation)", re.I)
_NOISE = re.compile(
    r"^(?:…|\.\.\.)?\s*(?:see more|show more|see less|show less|more)$|^show all\b|"
    r"^(?:like|comment|repost|send|follow|following|connect|message|more|contact info|"
    r"report this (?:post|profile)|edited|visible to anyone on or off linkedin|"
    r"view (?:full )?profile|open to|add profile section|enhance profile|resources)$|"
    r"^\d[\d,.]*\+?\s*(?:followers?|connections?|reactions?|comments?|reposts?|likes?)$|"
    r"^page \d+ of \d+$|^\d[\d,.]*$|^[•·]$|^(?:he|she|they)/(?:him|her|them)$|"
    r"^[•·]?\s*(?:1st|2nd|3rd\+?)(?:\s+degree connection)?$", re.I)
_POST_HEAD = re.compile(r"\b(posted this|reposted this|shared this|commented on (?:this|a post))\b",
                        re.I)
_AGE = re.compile(r"(?<![\w-])(\d{1,3})\s*(mo|mos|yr|yrs|y|w|d|h|hr|hrs|m|minutes?|hours?|days?|"
                  r"weeks?|months?|years?)\b(?!\w)(?:\s+ago)?", re.I)
# A line that is only a post's age, or ends with one: "2w", "2w • Edited", "3 weeks ago".
_AGE_AT_END = re.compile(
    r"(?:^|[•·])\s*(\d{1,3})\s*(mo|mos|yr|yrs|w|d|h)\b[\s•·]*(?:edited)?[\s•·]*$"   # "• 2w"
    r"|\b(\d{1,3})\s+(minutes?|hours?|days?|weeks?|months?|years?)\s+ago[\s•·]*$", re.I)
_AGE_ONLY = re.compile(r"^(?:\d{1,3}\s*(?:mo|mos|yr|yrs|y|w|d|h|hr|hrs|m|minutes?|hours?|days?|"
                       r"weeks?|months?|years?)\b(?:\s+ago)?)?[\s•·]*(?:edited)?[\s•·]*$", re.I)
_PAGE_ONE = re.compile(r"^page \d+ of \d+$", re.I)


def _age_date(n: int, unit: str, today: datetime.date) -> str:
    u = unit.lower()
    u = {"minute": "m", "minutes": "m", "hour": "h", "hours": "h", "day": "d", "days": "d",
         "week": "w", "weeks": "w", "month": "mo", "months": "mo", "year": "y",
         "years": "y"}.get(u, u)
    days = {"h": 0, "hr": 0, "hrs": 0, "m": 0, "d": 1, "w": 7, "mo": 30, "mos": 30,
            "y": 365, "yr": 365, "yrs": 365}[u] * n
    return (today - datetime.timedelta(days=days)).isoformat()


def _clean_lines(text: str) -> list:
    out = []
    for raw in untrusted.strip_markers(str(text or "")).replace("\r", "").split("\n"):
        line = " ".join(raw.split())
        if line:
            out.append(line)
    return out


def _sections(lines: list) -> tuple[list, dict, list]:
    """(lines before the first section, {section: [lines]}, the lines just before the
    first About or Experience), with LinkedIn's suggestions of other people cut off."""
    pre, secs, cur, seen, before_main = [], {}, None, [], None
    for line in lines:
        if _END.match(line):
            break
        name = _SECTIONS.get(line.lower().rstrip(":"))
        if name:
            if name == cur:          # LinkedIn prints some headings twice
                continue
            if name in secs and secs[name]:
                break                # a heading again after its content: the footer
            if before_main is None and name in ("about", "experience"):
                before_main = [x for x in seen if not _NOISE.match(x)][-3:]
            cur = name
            secs.setdefault(cur, [])
            continue
        seen.append(line)
        if cur is None:
            pre.append(line)
        else:
            secs[cur].append(line)
    return pre, secs, before_main or []


def _top(pre: list, before_main: list) -> tuple[str, str]:
    """(headline, location) from the top of the page."""
    anchor = next((i for i, x in enumerate(pre) if x.lower() == "contact info"), None)
    if anchor is not None:
        before = [x for x in pre[:anchor] if not _NOISE.match(x)]
        if len(before) >= 2:
            return before[-2][:160], before[-1][:120]
        return (before[-1][:160], "") if before else ("", "")
    # A "Save to PDF" export: name, headline and location sit right before Summary
    # or Experience, after the sidebar sections LinkedIn prints first.
    if len(before_main) == 3:
        return before_main[1][:160], before_main[2][:120]
    return "", ""


def _posts(lines: list, today: datetime.date, name: str = "") -> list:
    """Their posts and reposts, dated, newest first as the page lists them.

    A comment is skipped: what the page shows under it is mostly somebody else's
    post, and a note that credits them with it is wrong.
    """
    items, cur = [], None
    own = fold(name).strip()
    for i, line in enumerate(lines):
        head = _POST_HEAD.search(line)
        if head:
            if cur and cur["text"] and cur["kind"] != "comment":
                items.append(cur)
            verb = head.group(1).lower()
            kind = ("repost" if verb.startswith("repost") or verb.startswith("shared")
                    else "comment" if verb.startswith("comment") else "post")
            age = _AGE.search(line[head.end():]) or next(
                (m for m in (_AGE.search(x) for x in lines[i + 1:i + 3]) if m), None)
            cur = {"kind": kind, "date": _age_date(int(age.group(1)), age.group(2), today)
                   if age else "", "url": "", "text": ""}
            continue
        if cur is None and not _NOISE.match(line):
            # No "posted this" line above it, as a phone screenshot or a short paste
            # shows it: a line that ends with the post's age starts one ("3 weeks ago").
            end = _AGE_AT_END.search(line)
            if end:
                n, unit = (end.group(1), end.group(2)) if end.group(1) else (end.group(3), end.group(4))
                before = line[:end.start()].strip(" •·-")
                cur = {"kind": "post", "date": _age_date(int(n), unit, today),
                       "url": "", "text": before[:EXCERPT] if len(before) >= 12 else ""}
                continue
        if cur is None or _NOISE.match(line) or _AGE_ONLY.match(line):
            continue
        if own and fold(line).strip() == own:
            continue
        if len(cur["text"]) < EXCERPT:
            cur["text"] = (cur["text"] + " " + line).strip()[:EXCERPT]
    if cur and cur["text"] and cur["kind"] != "comment":
        items.append(cur)
    return items


def _titled(lines: list, kind: str, limit: int = 3) -> list:
    out = []
    for line in lines:
        if _NOISE.match(line) or len(line) < 12:
            continue
        out.append({"kind": kind, "date": "", "url": "", "text": line[:EXCERPT]})
        if len(out) >= limit:
            break
    return out


def _shared(secs: dict) -> dict:
    """What they share with the candidate, each with the line that shows it."""
    hist = history()
    exp = secs.get("experience") or []
    edu = secs.get("education") or []

    def evidence(names, lines):
        for line in lines:
            if any(_has(n, line) for n in names):
                return line[:160]
        return ""

    employers = []
    for names in hist["employers"]:
        line = evidence(names, exp)
        if line:
            employers.append({"name": names[0], "aka": names[1:], "evidence": line})
    schools = [{"name": s, "evidence": evidence([s], edu)}
               for s in hist["schools"] if evidence([s], edu)]
    places = [{"name": p, "evidence": evidence([p], exp)}
              for p in hist["places"] if evidence([p], exp)]
    return {"employers": employers, "schools": schools, "places": places}


_EMPLOYMENT = re.compile(r"^(.+?)\s+·\s+(?:full-time|part-time|contract|internship|"
                         r"self-employed|freelance|seasonal|apprenticeship|permanent|"
                         r"temporary)\b", re.I)
_TENURE = re.compile(r"^(?:(?:full-time|part-time|contract)\s+·\s+)?\d+\s+yrs?(?:\s+\d+\s+mos?)?$|"
                     r"^\d+\s+mos?$", re.I)


_DATES = re.compile(r"\b(?:19|20)\d{2}\b.*?(?:-|–|to)\s*(?:present|\w+\s+(?:19|20)\d{2}|(?:19|20)\d{2})|"
                    r"(?:-|–)\s*present\b", re.I)
# Save to PDF writes a role's dates as "January 2024 - Present (1 year 10 months)".
_PDF_LIKE = re.compile(r"\(\s*\d+\s+(?:years?|months?)", re.I)


_DEGREE = re.compile(r"(?:^|[·•\s])(1st|2nd|3rd\+?)(?:\s+degree connection)?\s*$", re.I)
_ACTIONS = ("connect", "message", "follow", "following", "pending")


def _reach(pre: list) -> tuple[str, str]:
    """(their degree, how they can be reached) from the top of their page, read only.

    The buttons LinkedIn shows the person on someone's profile say what is
    possible: Connect (a request with a note), Message (already connected, or an
    open profile), Follow only (Connect sits under More), Pending (a request has
    already gone). Nothing is clicked: the words on the page are enough.
    """
    degree = ""
    seen = set()
    for line in pre[:60]:
        m = _DEGREE.search(line)
        if m and not degree:
            degree = m.group(1).lower().rstrip("+")
        low = line.strip().lower()
        if low in _ACTIONS:
            seen.add(low)
    if "pending" in seen:
        reach = "pending"
    elif degree == "1st":
        reach = "message"
    elif "connect" in seen:
        reach = "request"
    elif seen & {"follow", "following"}:
        reach = "request under More"
    elif "message" in seen:
        reach = "message"
    else:
        reach = ""
    return degree, reach


def _current(exp: list) -> str:
    """The employer of their first, most recent Experience entry, or "" if unclear."""
    lines = [x for x in exp[:10] if not _NOISE.match(x)]
    for line in lines[:6]:
        m = _EMPLOYMENT.match(line)
        if m:
            return m.group(1).strip()[:120]
    if len(lines) >= 2 and _TENURE.match(lines[1]):
        return lines[0][:120]                      # several roles grouped under one employer
    if len(lines) >= 3 and any("present" in x.lower() for x in lines[1:4]) \
            and not _DATES.search(lines[1]):
        if _DATES.search(lines[2]) and not _DATES.search(lines[0]) and _PDF_LIKE.search(lines[2]):
            return lines[0][:120]                  # a Save to PDF export: employer first
    for i, line in enumerate(lines[:8]):
        if _DATES.search(line) and "present" in line.lower() and i >= 1:
            return lines[i - 1][:120]              # Title / Company / dates, no employment type
    return ""


def parse(text: str, *, name: str = "", company: str = "", source: str = "paste",
          url: str = "", today: datetime.date | None = None) -> dict:
    """A reading from a profile page's text: copied, read in a browser, or a Save-to-PDF.

    `name` is the contact's name from the contact book. A page that does not carry
    it is refused: a wrong tab pasted is the mistake this catches, and a note
    built on someone else's profile is worse than a generic one.
    """
    today = today or datetime.date.today()
    lines = [x for x in _clean_lines(text) if not _PAGE_ONE.match(x)]
    if name and not _names_them(name, lines):
        raise ValueError(f"this page does not look like {name}'s profile: their name is not on it")
    pre, secs, before_main = _sections(lines)
    headline, location = _top(pre, before_main)
    degree, reach = _reach(pre)
    about = " ".join(x for x in secs.get("about", []) if not _NOISE.match(x))[:ABOUT_CHARS]
    items = (_posts(secs.get("activity", []), today, name)
             + _titled(secs.get("featured", []), "featured", 2)
             + _titled(secs.get("publications", []), "publication", 2))
    return {
        "name": name, "company": company, "read_on": today.isoformat(),
        "sources": [{"kind": source, "url": url, "date": today.isoformat()}],
        "headline": headline, "location": location, "about": about,
        "current": _current(secs.get("experience", [])),
        "degree": degree, "reach": reach,
        "shared": _shared(secs), "items": items,
    }


def _names_them(name: str, lines: list) -> bool:
    """Their surname is on the page. Only the surname: the contact book may say
    Robert where the profile says Bob."""
    words = [w for w in fold(name).split() if len(w) > 1]
    if not words:
        return True
    text = fold(" ".join(lines[:400]))
    return re.search(r"(?<!\w)" + re.escape(words[-1]) + r"(?!\w)", text) is not None


def pdf_text(path: str) -> str:
    from pypdf import PdfReader  # the app's own dependency, already used by verify_pdf.py
    return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)


# ------------------------------------------------------------ public findings

def item(kind: str, url: str, text: str, date: str = "") -> dict:
    """One thing found about them in public, checked before it is kept."""
    kind = kind.lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    host = re.sub(r"^https?://", "", str(url or "")).split("/")[0].lower()
    if host and BROKERS.search("." + host + "."):
        raise ValueError(f"{host} sells people's details; it is never read or cited")
    if re.search(r"(?:^|\.)linkedin\.com$", host) and "/in/" in str(url):
        raise ValueError("a profile URL is not a finding: read the profile (read), "
                         "or add a post by its own /posts/ or /feed/update/ link")
    if kind in _DATED and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date or "")):
        raise ValueError(f"a {kind} needs its date (YYYY-MM-DD): an undated post may be years old")
    body = " ".join(untrusted.strip_markers(str(text or "")).split())[:EXCERPT]
    if not body:
        raise ValueError("a finding needs the words it rests on: the title or the line itself")
    return {"kind": kind, "date": str(date or ""), "url": str(url or ""), "text": body}


def merge(old: dict | None, new: dict) -> dict:
    """`new` read over `old`: a fresh page replaces the page fields; findings are kept."""
    if not old:
        return new
    out = dict(old)
    for k in ("headline", "location", "about", "current", "degree", "reach"):
        out[k] = new.get(k) or old.get(k, "")
    if any(s.get("kind") in PAGE_SOURCES for s in new.get("sources", [])):
        out["shared"] = new.get("shared") or old.get("shared", {})
    out["sources"] = old.get("sources", []) + new.get("sources", [])
    seen = {(i.get("kind"), i.get("text")) for i in old.get("items", [])}
    out["items"] = old.get("items", []) + [i for i in new.get("items", [])
                                           if (i.get("kind"), i.get("text")) not in seen]
    out["read_on"] = max(old.get("read_on", ""), new.get("read_on", ""))
    out["name"] = new.get("name") or old.get("name", "")
    out["company"] = new.get("company") or old.get("company", "")
    return out


# ------------------------------------------------------------------- verdict

def verdict(reading: dict, company: str = "") -> tuple[bool, str]:
    """After the read: still worth writing to? (keep, why not).

    A snippet can be months old. The page says whether they have moved on from
    the employer they were found at, whether the role is one the search filters
    out, and whether they are somewhere else entirely. A person dropped here is
    the next one's turn, the way a posting that fails a gate makes room for the
    next in a round. Keeps them when unsure: a wrong skip costs a good contact.
    """
    import discovery
    from company_key import key as company_key
    company = company or reading.get("company", "")
    headline = reading.get("headline", "")
    posts = " ".join(i.get("text", "") for i in reading.get("items", [])
                     if i.get("kind") in ("post", "repost") and (_days(i.get("date", ""), datetime.date.today()) or 0) <= 90)
    person_ = {"title": headline, "headline": headline, "about": reading.get("about", ""),
               "activity": posts, "company": company, "location": reading.get("location", "")}
    why = discovery.disqualify(person_, target_company=company)
    if why:
        return False, why
    if reading.get("reach") == "pending":
        return False, "a connection request to them is already pending"
    current = reading.get("current", "")
    if company and current and company_key(current) != company_key(company) \
            and not _has(company, headline) and not _has(company, current):
        return False, f"has moved on: their current employer is {current}, not {company}"
    if discovery._abroad(reading.get("location", "")) and "remote" not in fold(headline):
        return False, f"based elsewhere: {reading.get('location')}"
    return True, ""


# --------------------------------------------------------------------- hooks

def _days(date: str, today: datetime.date) -> int | None:
    # A timestamp is read as its day: a post dated 2026-10-17T10:00:00 is not undated.
    return dates.days_since(date, today, iso_only=True)


def hooks(reading: dict, today: datetime.date | None = None) -> list:
    """What a note to them can rest on, best first: (strength, kind, what, evidence)."""
    today = today or datetime.date.today()
    out = []
    shared = reading.get("shared") or {}
    for e in shared.get("employers", []):
        out.append((10, "shared employer", f"you both worked at {e['name']}", e.get("evidence", "")))
    for s in shared.get("schools", []):
        out.append((9, "shared school", f"you both studied at {s['name']}", s.get("evidence", "")))
    for i in reading.get("items", []):
        age = _days(i.get("date", ""), today)
        kind = i.get("kind", "")
        if kind in _DATED and (age is None or age > POST_DAYS):
            continue
        base = {"post": 8, "repost": 6, "comment": 5, "news": 4, "featured": 5}.get(kind, 7)
        if kind in _DATED and age is not None and age > 90:
            base -= 3
        when = f" ({i['date']})" if i.get("date") else ""
        out.append((base, kind, f"their {kind}{when}", i.get("text", "")))
    for p in shared.get("places", []):
        out.append((6, "same city before", f"you both worked in {p['name']}", p.get("evidence", "")))
    if reading.get("about"):
        out.append((3, "about", "something specific in their About", _clip(reading["about"], 200)))
    return sorted(out, key=lambda h: -h[0])


_STOP = set("""a an and are as at be been both but by for from had has have how i i'm in
into is it its just me my of on or our so that the their them they this to us was we were
what when where which who why will with you your you're yours""".split())
# Words any note uses, which prove nothing about having read someone.
_GENERIC = set("""about across after again also always another around back being best better
between big build building built career change changed company could data day days did doing
done each enjoyed even every few find first focus found from fun get getting given going good
great happy help hope interesting into journey just keen know learn learned like liked looking
lot love loved made make making many might more most move moved much need new next nice now
often one only other over part people piece pieces point post posted posts really recent
recently right role roles said saw see seeing seen share shared since some something still
such sure take talk talked team teams than thanks thing things think thought through time
today topic took two use used using very want way well work worked working would year years
""".split())


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9'&+.-]*[a-z0-9]|[a-z0-9]", fold(text))
            if len(w) >= 3 and w not in _STOP and w not in _GENERIC}


def grounded(common_ground: str, reading: dict | None) -> tuple[bool, str]:
    """Does the note's common ground rest on something actually read about them.

    True when it names history they share (an employer, school or city found on
    their page), or carries the distinctive words of something they wrote, said
    or published. A common ground the reading does not support is a guess, and
    a guess dressed as research is what this stops. (ok, what it rests on).
    """
    if not reading:
        return False, "nothing was read about them"
    cg = str(common_ground or "")
    shared = reading.get("shared") or {}
    for group in ("employers", "schools", "places"):
        for s in shared.get(group, []):
            if any(_has(n, cg) for n in [s.get("name", "")] + list(s.get("aka") or [])):
                return True, f"shared {group[:-1]}: {s['name']}"
    # Their name and their employer are known before anything is read, so they
    # prove nothing: "your work at <Employer>" is the note a snippet already made.
    known = _words(reading.get("name", "")) | _words(reading.get("company", ""))
    mine = _words(cg) - known
    sources = [(i.get("kind", "item"), i.get("text", "")) for i in reading.get("items", [])]
    sources += [("about", reading.get("about", ""))]
    for kind, text in sources:
        theirs = _words(text)
        need = 1 if len(theirs) <= 6 else 2
        common = mine & theirs
        if len(common) >= need:
            return True, f"their {kind}: {', '.join(sorted(common)[:4])}"
    return False, "the common ground matches nothing read about them"


def same_ground(grounds: dict) -> list:
    """Pairs of notes that say the same thing to different people: [(a, b, overlap)].

    The failure a person caught: one background line and a swapped hook, so every
    note read alike. Compare only what is about the reader.
    """
    keys = list(grounds)
    words = {k: _words(grounds[k]) for k in keys}
    out = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            wa, wb = words[a], words[b]
            if fold(grounds[a]).strip() == fold(grounds[b]).strip() and grounds[a].strip():
                out.append((a, b, 1.0))
                continue
            if len(wa) >= 3 and len(wb) >= 3:
                overlap = len(wa & wb) / len(wa | wb)
                if overlap >= 0.5:
                    out.append((a, b, round(overlap, 2)))
    return out


def fenced(reading: dict) -> str:
    """The reading for a prompt: data inside a fence, never instructions."""
    keep = {k: reading.get(k) for k in ("headline", "location", "about", "shared", "items")}
    return untrusted.fence(json.dumps(keep, ensure_ascii=False, indent=1),
                           label=f"LinkedIn and public material about {reading.get('name') or 'them'}")


# --------------------------------------------------------------------- route

# What a session can tell about itself: a cloud session sets CLAUDE_CODE_REMOTE,
# and CLAUDE_CODE_ENTRYPOINT names where it was started (a value seen:
# "remote_desktop", a cloud session opened from the desktop app).
def surface(env=None) -> str:
    """"phone", "web", "desktop-cloud", "local" or "unknown": where this session runs."""
    env = os.environ if env is None else env
    entry = str(env.get("CLAUDE_CODE_ENTRYPOINT", "")).lower()
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() != "true":
        return "local" if env.get("CLAUDECODE") else "unknown"
    if any(w in entry for w in ("mobile", "ios", "android", "phone")):
        return "phone"
    if "desktop" in entry:
        return "desktop-cloud"
    if "web" in entry:
        return "web"
    return "unknown"


def route(tools=(), consent: str | None = None, env=None) -> dict:
    """How this session reads a profile, chosen for the person, never asked of them.

    `tools` is what the session itself has: "browser" (the desktop app's built-in
    browser, as mcp__Claude_Browser__* or mcp__remote-devices__Claude_Browser__*),
    "chrome" (Claude in Chrome), "enable" (enable__mcp__remote-devices__Claude_Browser,
    which turns the built-in browser on for the conversation). Returns the route,
    what Claude does, and the one line the person is told, or "" when nothing needs
    saying. A person is never told to press a key or find a setting: the browser is
    used when it is there, switched on when it can be, and otherwise the route that
    works where they are is asked for, once.
    """
    have = {str(t).lower() for t in tools}
    consent = (consent or PROFILE_READS).lower()
    where = surface(env)
    hand = ("screenshots of their profile from the LinkedIn app" if where == "phone"
            else "their profile pasted (select all, copy), its Save to PDF, or screenshots")
    if consent == "off":
        return {"route": "public", "do": "public work only", "say": ""}
    if consent == "browser":
        if have & {"browser", "chrome"}:
            return {"route": "browser", "do": "read each profile in the browser, nothing clicked",
                    "say": ""}
        if "enable" in have:
            return {"route": "enable", "do": "call enable__mcp__remote-devices__Claude_Browser, "
                    "then read each profile in the browser, nothing clicked", "say": ""}
        why = {"phone": "this session runs in the cloud and a phone has no browser it can use",
               "web": "this session runs in the cloud and the web page has no browser it can use",
               "desktop-cloud": "this session runs in the cloud and the desktop app has not "
                                "given it a browser",
               }.get(where, "this session has no browser it can use")
        return {"route": "hand", "do": f"ask once for {hand}; everything after is automatic",
                "say": f"Profiles are read automatically only in a session with a browser: "
                       f"{why}. Until then, send {hand} for each person and I'll do the rest. "
                       f"A session run on your computer from the Claude desktop app reads "
                       f"them by itself."}
    return {"route": "hand", "do": f"ask once for {hand}; everything after is automatic",
            "say": f"Send {hand} for each person and I'll make each note about them."}


# ------------------------------------------------------------------- storage

def path(contact_id: str) -> str:
    if not re.match(r"^[\w.-]+$", contact_id or ""):
        raise ValueError(f"not a contact id: {contact_id!r}")
    return person.state(*DIR, contact_id, "reading.json")


def load(contact_id: str) -> dict | None:
    try:
        with open(path(contact_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save(contact_id: str, reading: dict) -> str:
    p = path(contact_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(reading, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return p


def fresh(reading: dict | None, today: datetime.date | None = None) -> bool:
    today = today or datetime.date.today()
    age = _days((reading or {}).get("read_on", ""), today)
    return age is not None and age <= FRESH_DAYS and any(
        s.get("kind") in PAGE_SOURCES for s in (reading or {}).get("sources", []))


def _browser_reads() -> list:
    """Every browser read on file, oldest first: [(when, the gap it asked for)]."""
    out = []
    for f in glob.glob(person.state(*DIR, "*", "reading.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                srcs = json.load(fh).get("sources", [])
        except (OSError, ValueError):
            continue
        for src in srcs:
            if src.get("kind") == "browser" and src.get("at"):
                try:
                    out.append((datetime.datetime.fromisoformat(src["at"]),
                                float(src.get("next_gap") or PACE_SECONDS)))
                except ValueError:
                    continue
    return sorted(out)


def last_browser_read() -> datetime.datetime | None:
    reads = _browser_reads()
    return reads[-1][0] if reads else None


def stopped(today: datetime.date | None = None) -> str:
    """Why browser reads are stopped for today, or "". A warning ends the day's reads."""
    try:
        with open(person.state(*STOP_FILE), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return ""
    day = (today or datetime.date.today()).isoformat()
    return str(got.get("reason") or "stopped") if got.get("date") == day else ""


def stop(reason: str, today: datetime.date | None = None) -> str:
    """Record that LinkedIn showed a warning, a security check, a CAPTCHA or a sign-in wall."""
    p = person.state(*STOP_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"date": (today or datetime.date.today()).isoformat(),
                   "reason": " ".join(str(reason or "").split())[:200]}, fh)
        fh.write("\n")
    return p


def browser_gate(now: datetime.datetime | None = None) -> str:
    """"" when a browser read may go now, otherwise why not and when it may."""
    now = now or datetime.datetime.now()
    why = stopped(now.date())
    if why:
        return f"browser reads are stopped for today: {why}. Tomorrow, or a paste"
    reads = _browser_reads()
    today = [t for t, _ in reads if t.date() == now.date()]
    if len(today) >= READS_PER_DAY:
        return (f"{READS_PER_DAY} profiles read today (PROFILE_READS_PER_DAY); "
                "the rest wait for tomorrow or a paste")
    window = now - datetime.timedelta(minutes=HOUR_MINUTES)
    last_hour = [t for t, _ in reads if t > window]
    if len(last_hour) >= READS_PER_HOUR:
        resume = min(last_hour) + datetime.timedelta(minutes=HOUR_MINUTES)
        return (f"{READS_PER_HOUR} profiles in the last hour (PROFILE_READS_PER_HOUR); "
                f"the next after {resume:%H:%M}")
    if reads:
        last, gap = reads[-1]
        waited = (now - last).total_seconds()
        if waited < gap:
            return f"{waited:.0f}s since the last profile; wait {gap - waited:.0f}s more"
    return ""


def next_gap(rng=None) -> int:
    """The pause to leave after this read: varied, and longer every few reads."""
    import random
    rng = rng or random
    window = datetime.datetime.now() - datetime.timedelta(minutes=HOUR_MINUTES)
    n = sum(1 for t, _ in _browser_reads() if t > window) + 1
    lo, hi = BREAK_SECONDS if n % BREAK_EVERY == 0 else GAP_SECONDS
    return int(rng.uniform(lo, hi))


def reads_today(today: datetime.date | None = None) -> int:
    day = (today or datetime.date.today()).isoformat()
    n = 0
    for f in glob.glob(person.state(*DIR, "*", "reading.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                srcs = json.load(fh).get("sources", [])
        except (OSError, ValueError):
            continue
        n += sum(1 for s in srcs if s.get("kind") == "browser" and s.get("date") == day)
    return n


def queue(contacts: list, today: datetime.date | None = None) -> list:
    """Contacts with a first note waiting and no fresh reading of their profile."""
    out = []
    for c in contacts:
        cid = c.get("contact_id", "")
        if (c.get("status") or "not_contacted") != "not_contacted" or not cid:
            continue
        if not os.path.isfile(person.state(*DIR, cid, "draft.md")):
            continue
        if not fresh(load(cid), today):
            out.append(c)
    return out


# ----------------------------------------------------------------------- CLI

def _contact(contact_id: str, name: str = "", company: str = "") -> dict:
    """The contact row, or the candidate a /network run is reading before it writes state."""
    import state
    for c in state.load_contacts():
        if c.get("contact_id") == contact_id:
            return c
    if name and company:
        return {"contact_id": contact_id, "name": name, "company": company}
    raise SystemExit(f"reading: no contact {contact_id!r} in network_contacts.csv "
                     "(a candidate not written yet takes --name and --company)")


def _show(reading: dict) -> None:
    print(f"{reading.get('name') or '?'}: {reading.get('headline') or '(no headline)'}"
          f"{' | ' + reading['location'] if reading.get('location') else ''}")
    hs = hooks(reading)
    if not hs:
        print("  nothing personal to rest a note on yet: paste their profile, or add a finding")
    for strength, kind, what, ev in hs[:6]:
        print(f"  [{strength}] {kind}: {what}" + (f'\n        "{_clip(ev, 150)}"' if ev else ""))


def _clip(text: str, n: int) -> str:
    """At most n characters, cut at a word, with an ellipsis when cut."""
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (cut or text[:n]) + "…"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="a profile page: copied text, a browser read, or a PDF")
    r.add_argument("contact_id")
    r.add_argument("file", help="a text file, a .pdf from LinkedIn's Save to PDF, or - for stdin")
    r.add_argument("--source", choices=PAGE_SOURCES, default=None)
    r.add_argument("--url", default="")
    r.add_argument("--name", default="", help="for a candidate not in the contact book yet")
    r.add_argument("--company", default="")
    v = sub.add_parser("verdict", help="after the read: KEEP, or SKIP and why (exit 3)")
    v.add_argument("contact_id")
    v.add_argument("--company", default="")
    a_ = sub.add_parser("add", help="one public finding: a talk, an article, a post")
    a_.add_argument("contact_id")
    a_.add_argument("--kind", required=True, choices=KINDS)
    a_.add_argument("--url", required=True)
    a_.add_argument("--date", default="")
    a_.add_argument("--text", required=True)
    a_.add_argument("--name", default="", help="for a candidate not in the contact book yet")
    a_.add_argument("--company", default="")
    s = sub.add_parser("show")
    s.add_argument("contact_id")
    sub.add_parser("queue", help="drafts waiting with no fresh reading")
    st = sub.add_parser("stop", help="LinkedIn showed a warning or a wall: no browser reads today")
    st.add_argument("reason")
    sub.add_parser("gate", help="may a browser read go now, and if not, when")
    ro = sub.add_parser("route", help="how this session reads profiles, and what to tell the person")
    ro.add_argument("--tools", default="",
                    help="what the session has, comma-separated: browser, chrome, enable")
    a = ap.parse_args(argv)

    if a.cmd == "stop":
        print(f"reading: browser reads stopped for today ({os.path.relpath(stop(a.reason), person.state())})")
        return 0
    if a.cmd == "gate":
        why = browser_gate()
        print("go" if not why else f"wait: {why}")
        return 0 if not why else 3
    if a.cmd == "route":
        r_ = route([t for t in a.tools.split(",") if t.strip()])
        print(f"route: {r_['route']} ({surface()})\ndo: {r_['do']}")
        if r_["say"]:
            print(f"tell them, once: {r_['say']}")
        return 0
    if a.cmd == "queue":
        import state
        waiting = queue(state.load_contacts())
        print(f"{len(waiting)} draft(s) waiting with no fresh reading; profile reads: {PROFILE_READS}"
              + (f", {max(0, READS_PER_DAY - reads_today())} browser read(s) left today"
                 if PROFILE_READS == "browser" else ""))
        for i, c in enumerate(waiting, 1):     # numbered, so a reply can say "3 and 5"
            print(f"  {i}. {c.get('name')} ({c.get('company')}) {c.get('linkedin_url') or ''}"
                  f"  [{c['contact_id']}]")
        return 0
    if a.cmd == "verdict":
        found = load(a.contact_id)
        if not found:
            print(f"reading: nothing read about {a.contact_id} yet")
            return 1
        keep, why = verdict(found, a.company or found.get("company", ""))
        print("KEEP" if keep else f"SKIP: {why}")
        return 0 if keep else 3
    old = load(a.contact_id)
    if a.cmd == "show":                 # a reading stands on its own: no contact row needed
        if not old:
            print(f"reading: nothing read about {a.contact_id} yet")
            return 1
        _show(old)
        return 0
    known = old or {}
    contact = _contact(a.contact_id, getattr(a, "name", "") or known.get("name", ""),
                       getattr(a, "company", "") or known.get("company", ""))
    if a.cmd == "add":
        new = {"name": contact.get("name", ""), "company": contact.get("company", ""),
               "read_on": (old or {}).get("read_on", "") or datetime.date.today().isoformat(),
               "sources": [{"kind": "public", "url": a.url,
                            "date": datetime.date.today().isoformat()}],
               "items": [item(a.kind, a.url, a.text, a.date)]}
        reading = merge(old, new) if old else {**new, "headline": "", "location": "",
                                               "about": "", "shared": {}}
    else:
        source = a.source or ("pdf" if a.file.lower().endswith(".pdf") else "paste")
        if source == "browser":
            if PROFILE_READS != "browser":
                raise SystemExit("reading: profile reads in the browser are off "
                                 "(profile/networking.py PROFILE_READS); ask the person to paste "
                                 "the page instead")
            if fresh(old):
                raise SystemExit(f"reading: {a.contact_id} was read on {old.get('read_on')}; "
                                 "a profile is opened once, and that reading stands")
            why = browser_gate()
            if why:
                raise SystemExit(f"reading: {why}")
        if source == "pdf":
            text = pdf_text(a.file)
        elif a.file == "-":
            text = sys.stdin.read()
        else:
            with open(a.file, encoding="utf-8") as fh:
                text = fh.read()
        try:
            new = parse(text, name=contact.get("name", ""), company=contact.get("company", ""),
                        source=source,
                        url=a.url or contact.get("linkedin_url", ""))
        except ValueError as e:
            raise SystemExit(f"reading: {e}") from None
        if source == "browser":
            new["sources"][0]["at"] = datetime.datetime.now().isoformat(timespec="seconds")
            new["sources"][0]["next_gap"] = next_gap()
        reading = merge(old, new)
    print(f"reading: saved {os.path.relpath(save(a.contact_id, reading), person.state())}")
    _show(reading)
    if a.cmd == "read":
        keep, why = verdict(reading, contact.get("company", ""))
        print("verdict: KEEP" if keep else f"verdict: SKIP: {why} (read the next person instead)")
        if source == "browser":
            print(f"pace: the next profile in {new['sources'][0]['next_gap']}s at the earliest; "
                  "vary it, never open two at once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
