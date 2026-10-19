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

Only what a note could rest on is kept: the headline, their About (the summary of
their work they wrote for anyone to read, kept whole up to LinkedIn's own limit so a
note can rest on any of it, and shown as a short excerpt), the history they share
with the candidate, and their recent posts and public work, each with where and when
it was read. Never their whole profile.
It lives in documents/network/<contact_id>/reading.json and is fresh for
FRESH_DAYS. Everything in a reading was written by someone else: a model sees it
only through `fenced()`, as data, never as instructions.

    python3 tools/network/reading.py read <contact_id> <file|-> [--source paste|browser|pdf|screenshot] [--url URL]
    python3 tools/network/reading.py add <contact_id> --kind talk --url URL --date YYYY-MM-DD --text "..."
    python3 tools/network/reading.py show <contact_id>      # what a note can rest on, best first
    python3 tools/network/reading.py queue                  # drafts waiting with no fresh reading
    python3 tools/network/reading.py paste <file|->         # several profiles in one paste, split by ---
    python3 tools/network/reading.py draft <contact_id> <file|->   # a note to draft.md, marked if unread
    python3 tools/network/reading.py gate [--wait [--timeout S]]  # may a browser page load go now
    python3 tools/network/reading.py invitations <file|->          # the sent-invitations list, once
    python3 tools/network/reading.py people <file|-> --company C   # an employer's People tab, once
    python3 tools/network/reading.py skip <contact_id> --reason R  # a read ruled them out: close it
    python3 tools/network/reading.py batch [<contact_id>...]       # are the queued notes too alike?
    python3 tools/network/reading.py extractor                     # the read-only page snippet
    python3 tools/network/reading.py next [--wait] [--mode card|deep]   # who to read next, once a page may load
    python3 tools/network/reading.py shortlist [<id>...] [--remove <id>...]  # today's short list
    python3 tools/network/reading.py search-url --company C [--place P] [--keywords K] [--learn ADDRESS]
    python3 tools/network/reading.py queue --urls                  # the fast path: addresses to open and paste
    python3 tools/network/reading.py limits                        # every limit, its value and why
    python3 tools/network/reading.py friction [--kind K --words W] # the signals seen, and the ramp

Exit codes, one meaning each, so `read; verdict` can be chained (EXIT):
    0  done: go, KEEP, saved          1  an error, or nothing to act on
    2  the command line was wrong (argparse)
    3  SKIP: a read or a public finding rules them out
    4  LinkedIn's sign-in page: wait for the person, nothing counted
    5  LinkedIn showed a check: browser reads stopped for today
    6  the page is neither a profile, a sign-in nor a check
    7  wait: the pause after the last page, seconds (the time is printed)
    8  later: the hourly cap, a time later today (printed)
    9  tomorrow: the day's cap, the send-day cap, or stopped for today
    10 not read yet: no page of theirs read, so KEEP cannot be said
    11 the batch of notes is too alike to send
    12 done: nobody left to read on today's short list (`next`)
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

EXIT = {"ok": 0, "error": 1, "skip": 3, "signin": 4, "check": 5, "unknown": 6, "wait": 7,
        "later": 8, "tomorrow": 9, "not_read": 10, "alike": 11, "done": 12}

# "browser", "paste" or "off". Absent means "paste": reading a profile in the
# person's own browser is automated access LinkedIn's terms forbid, so it waits
# for their yes (the profile-reads upgrade asks).
PROFILE_READS = str(getattr(_NET, "PROFILE_READS", "paste") or "paste").lower()
# How a browser read behaves: like a person writing to a few people, never a loop.
# It is the person's own signed-in account loading these pages, and a steady
# machine rhythm or a burst is what automation checks look for. LinkedIn
# publishes no thresholds and its terms forbid automated access at any pace, so
# nothing here makes a browser read safe: these lower the risk and do not remove
# it. A read is for someone the person will send to today, so the day's reads stop
# at the requests left today (state.platform_budget) and SKIP_SPARE more, for the
# people a read rules out; 15 a day and 8 an hour are the ceilings, the pace of
# someone writing each note by hand.
#
# The pace now, and why. Between two pages: a gap drawn from a log-normal curve
# with its middle at GAP_MEDIAN (90 seconds), never under 45 seconds or over 240,
# so most gaps sit near a minute and a half and no two runs repeat. After a
# varying 3 to 7 pages (BREAK_AFTER, drawn again each time), a longer break of 5
# to 12 minutes (BREAK_SECONDS). On each page, 20 to 60 seconds scrolled through
# at reading pace (DWELL_SECONDS), which is also what makes LinkedIn load the
# sections it fills in late. The evidence is thin and stated as such: LinkedIn
# publishes no rate, so these are a judgement of how long a person spends reading
# a profile and writing a note, not a measured safe limit. What is measured is the
# failure they replaced: an even 25 to 75 second gap with a break on exactly every
# fifth read, and caps of 30 an hour and 80 a day, which is a rhythm a machine has
# and a person does not.
#
# The person owns the trade-off: every limit below is a setting in profile/networking.py,
# and one dial, PROFILE_READ_RISK, sets them all from a named preset ("careful" by default,
# which is this pace exactly; "normal"; "fast"). tools/network/pace.py holds them in one
# place, each with its default and why, and `reading.py limits` prints them. No preset but
# careful applies unless they write it, and no setting here shortens anything they have not
# set themselves.
import pace  # noqa: E402

READS_PER_HOUR = pace.value("reads_per_hour")
READS_PER_DAY = pace.value("reads_per_day")
PAGES_PER_HOUR = pace.value("pages_per_hour")
PAGES_PER_DAY = pace.value("pages_per_day")
LOADS_PER_HOUR = max(pace.value("loads_per_hour"), READS_PER_HOUR)
LOADS_PER_DAY = max(pace.value("loads_per_day"), READS_PER_DAY)
SKIP_SPARE = pace.value("skip_spare")
HOUR_MINUTES = 60                       # the hourly caps count loads in this rolling window
GAP_SECONDS = pace.value("gap_seconds")  # between two pages: most near GAP_MEDIAN
GAP_MEDIAN = pace.value("gap_median")
BREAK_AFTER = pace.value("break_after")  # a longer break after somewhere in this many reads
BREAK_MINUTES_DEFAULT = pace.LIMITS["break_minutes"][2]


def _break_minutes(value) -> tuple:
    """The person's PROFILE_READ_BREAK_MINUTES as (shortest, longest), or the default.
    A single number is a fixed length; anything unreadable is the default."""
    try:
        lo, hi = (value, value) if isinstance(value, (int, float)) else tuple(value)[:2]
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return BREAK_MINUTES_DEFAULT
    if lo < 0 or hi < 0:
        return BREAK_MINUTES_DEFAULT
    return (min(lo, hi), max(lo, hi))


BREAK_MINUTES = _break_minutes(pace.value("break_minutes"))
BREAK_SECONDS = (int(BREAK_MINUTES[0] * 60), int(BREAK_MINUTES[1] * 60))
DWELL_SECONDS = pace.value("dwell_seconds")            # a deep read: scrolled to the end
CARD_DWELL_SECONDS = pace.value("card_dwell_seconds")  # a card read: top card and About only
READ_MODES = ("card", "deep")
PACE_SECONDS = GAP_SECONDS[0]           # the shortest gap ever allowed
STOP_FILE = ("documents", "network", ".reads_stopped.json")
# Reading enriches a short list; it never makes the list. A run ranks everyone it
# found (tools/network/sources.py, the ladder), puts its best on the day's short list,
# and a browser read refuses anyone not on it. Without a browser, a paste is offered for
# the best HAND_TOP at most, never for everyone.
#
# The funnel, cheapest first. Free sources (search results with their summaries,
# the connections export) make the list. Then one-page reads, each page holding many
# people: the sent-invitations list (who already has a request pending, for everyone
# at once) and a people search narrowed to the employer (headline, place and degree for
# a dozen people a load). Only then a profile read, of their own page, for the few the
# person will write to that day, as its card when that decides it. The day's list is
# sized to the requests that can still go today (and SKIP_SPARE for those a read rules
# out), never above READS_PER_RUN, and at most UNVERIFIED_ON_SHORTLIST of it may be people
# nothing has placed in the person's city yet. READS_PER_RUN was 10 and is 5 since 3.7.0:
# in one session (2026-10-19) five of seven profile reads went on facts a cheaper check had
# already shown (a request already pending, a city elsewhere, a role outside their
# function).
READS_PER_RUN = pace.value("reads_per_run")
UNVERIFIED_ON_SHORTLIST = pace.value("unplaced")
HAND_TOP = pace.value("paste_top")
SHORTLIST_FILE = ("documents", "network", ".shortlist.json")
# The one-page reads (a list of many people, read once) and when each was read: they
# pace like a profile and count against their own caps (PAGES_PER_*) and all loads
# together (LOADS_PER_*), never the send-day cap, which is about the people written to.
PAGES_FILE = ("documents", "network", ".page_reads.json")
PAGE_KINDS = ("invitations", "people", "search")
# Signed in to LinkedIn in the browser today, as the session last saw it. A sign-in
# page before this is a wait for the person; after it, LinkedIn signed them out
# mid-run, which is a stop. Never a password: only that a signed-in page was seen.
SIGNIN_FILE = ("documents", "network", ".signed_in.json")
SIGNIN_URL = "https://www.linkedin.com/login"
SIGNIN_POLL_SECONDS = 20                # how often the session looks at the pane's address
SIGNIN_WAIT_MINUTES = 5                 # then it asks again, never gives up silently
FRESH_DAYS = pace.value("fresh_days")
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
        # "Royal Fernhill" would claim a shared employer with Royal Fernhill Insurance.
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


_CONTACT = re.compile(r"^[·•]?\s*contact info$", re.I)
# "Toronto, Ontario, Canada · Contact info" on one line, as a browser's page text
# gives it when the place and the link sit in one row.
_CONTACT_TAIL = re.compile(r"\s*[·•]?\s*contact info$", re.I)
# The signed-in top card puts "Current employer · School" between the headline and
# the location. Taking the line before the location as the headline saved that
# line instead of the headline.
_ORG_LINE = re.compile(r"\s[·•]\s")
# Lines of the top card that are neither the headline, the place nor where they work:
# the mutual-connection line, a request already sent, the buttons, the counts. The
# mutual-connection line was saved as the headline on two profiles in one session.
_CARD_SKIP = re.compile(
    r"\bmutual connections?\b|\bis a mutual connection\b|^pending$|^follow$|^following$|"
    r"^connect$|^message$|^more$|^open to\b|^verified$|^\d[\d,.]*\+?\s*(?:followers?|connections?)$|"
    r"^(?:he|she|they)/(?:him|her|them)$|^[·•]?\s*(?:1st|2nd|3rd\+?)(?:\s+degree connection)?$|"
    r"^view (?:my|full) profile$|^talks about\b|^provides services\b|^save to pdf$|^report",
    re.I)
_DEGREE_TAIL = re.compile(r"\s*[·•]\s*(?:1st|2nd|3rd\+?)(?:\s+degree connection)?\s*$", re.I)


def _looks_place(line: str) -> bool:
    """Is this top-card line where they are, rather than a school or an employer?"""
    import discovery
    x = " ".join(str(line or "").split())
    if not x or _SCHOOL.search(x) or _ORG_LINE.search(x) or len(x) > 80:
        return False
    return ("," in x or discovery._is_place(x) or discovery._PLACE_SHAPE.search(x) is not None
            or bool(re.search(r"\b(?:area|metropolitan|remote)\b", x, re.I)))


def _name_at(lines: list, name: str):
    """Index of the line that is their name, or None."""
    surname = (fold(name).split() or [""])[-1]
    if not surname:
        return None
    for i, x in enumerate(lines):
        if len(x) <= len(name) + 30 and re.search(
                r"(?<!\w)" + re.escape(surname) + r"(?!\w)", fold(x)):
            return i
    return None


def _top(pre: list, before_main: list, name: str = "") -> tuple[str, str, str]:
    """(headline, location, the card's "Employer · School" line) from the top of the page.

    The card reads, in a browser today: name, degree, headline, place, Contact info,
    employer, school, connections, a mutual connection, then the buttons. Older pages
    and copies put "Employer · School" on one line between the headline and the place,
    and some copies run the place and "Contact info" into one line. Read by what each
    line is rather than where it sits: the school line had been taken for the place
    ("based in <the school>") and the mutual-connection line for the headline.
    """
    lines = []
    anchor = None
    for x in pre:
        if _CONTACT.match(x):
            anchor = len(lines) if anchor is None else anchor
            continue
        if _CONTACT_TAIL.search(x) and len(x) > len("contact info") + 2:
            head = _CONTACT_TAIL.sub("", x).strip(" ·•")
            if head:
                lines.append(head)
                anchor = len(lines) if anchor is None else anchor
            continue
        lines.append(_DEGREE_TAIL.sub("", x).strip())
    at = _name_at(lines, name) if name else None
    if at is None and anchor is None:
        # A "Save to PDF" export: name, headline and location sit right before Summary
        # or Experience, after the sidebar sections LinkedIn prints first.
        if len(before_main) == 3:
            if name and fold(before_main[1]) == fold(name):
                # No location line: the line before the name, the name, then the headline.
                # Read as name, headline and location, it made the name the headline and
                # their job where they live ("based in Head of Data at ...").
                return before_main[2][:160], "", ""
            return before_main[1][:160], before_main[2][:120], ""
        return "", "", ""
    first = (at + 1) if at is not None else 0
    card = [(i, x) for i, x in enumerate(lines[first:], first)
            if x and not _NOISE.match(x) and not _CARD_SKIP.search(x)]
    if at is None and anchor is not None:
        # No name found: the headline and the place are the lines just before Contact
        # info, with "Employer · School" between them on an older card.
        pre_anchor = [(i, x) for i, x in card if i < anchor]
        take = 3 if len(pre_anchor) >= 3 and _ORG_LINE.search(pre_anchor[-2][1]) else 2
        card = pre_anchor[-take:] + [(i, x) for i, x in card if i >= anchor]
    if not card:
        return "", "", ""
    headline = card[0][1]
    rest = card[1:]
    location, org = "", ""
    if anchor is not None:
        before = [x for i, x in rest if i < anchor]
        after = [x for i, x in rest if i >= anchor]
        if before:
            # The line just before Contact info is where they are, whatever the city:
            # a place no list knows ("Slough") is still the place. Never a school or an
            # "Employer · School" line.
            last = before[-1]
            location = last if not _SCHOOL.search(last) and not _ORG_LINE.search(last) else ""
            org = next((x for x in before if _ORG_LINE.search(x)), "")
        if not location:
            location = next((x for x in after[:1] if _looks_place(x)), "")
        if not org:
            org = next((x for x in after if not _looks_place(x) and not _SCHOOL.search(x)), "")
    else:
        for x in [x for _, x in rest][:3]:
            if not location and _looks_place(x):
                location = x
            elif not org and _ORG_LINE.search(x):
                org = x
        if not org:
            org = next((x for _, x in rest if x != location and not _looks_place(x)
                        and not _SCHOOL.search(x)), "")
    return headline[:160], location[:120], org[:200]


def _card_employer(org: str) -> str:
    """The current employer the top card names, never the school beside it."""
    first = _ORG_LINE.split(org or "")[0].strip()
    return "" if not first or _SCHOOL.search(first) else first[:120]


# A headline's past, never where they work: "ex-<Employer>", "formerly <Employer>".
_PAST_PART = re.compile(r"(?:\bex[-\s]|\bformer(?:ly)?\s+(?:at\s+)?|\bpreviously\s+(?:at\s+)?|"
                        r"\bpast:\s*)[^|\u00b7\u2022,;]*", re.I)
_HEAD_SPLIT = re.compile(r"\s+[|\u00b7\u2022]\s+|\s+-\s+|\s*\|\s*")
# "<role> at <Employer>" or "<role> @ <Employer>": the employer is the run of
# capitalised words after it, joined by "of", "&" and the like ("Bank of Northgate",
# "Brindle & Hart Logistics"), so "at Kestrel Mutual and part-time lecturer" names
# Kestrel Mutual; a lower-case word after "at" is no employer ("at scale").
_AT_EMPLOYER = re.compile(
    r"(?:\bat\s+|(?:^|\s)@\s*)([A-Z0-9][\w&'.-]*(?:\s+(?:(?:of|de|du|des|la|le|the|and|for|"
    r"y|e|&)\s+)?[A-Z0-9&][\w&'.-]*)*)")


def _headline_employer(text: str) -> str:
    """The employer a headline or a "Current:" line names as where they work, or ""."""
    for seg in _HEAD_SPLIT.split(_PAST_PART.sub(" ", str(text or ""))):
        m = _AT_EMPLOYER.search(seg)
        if m and m.group(1).strip(" .-"):
            return m.group(1).strip(" .-")[:120]
    return ""


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
    headline, location, org = _top(pre, before_main, name)
    degree, reach = _reach(pre)
    about = _clip(" ".join(x for x in secs.get("about", []) if not _NOISE.match(x)), ABOUT_KEEP)
    items = (_posts(secs.get("activity", []), today, name)
             + _titled(secs.get("featured", []), "featured", 2)
             + _titled(secs.get("publications", []), "publication", 2))
    return {
        "name": name, "company": company, "read_on": today.isoformat(),
        "sources": [{"kind": source, "url": url, "date": today.isoformat()}],
        "headline": headline, "location": location, "about": about,
        "current": _current_employer(headline, secs.get("experience", []), org),
        "degree": degree, "reach": reach,
        "shared": _shared(secs), "items": items,
    }


# The About is kept whole for grounding (grounded(), and the fenced reading a draft is
# written from), up to LinkedIn's own limit for it. Cut to its first ABOUT_CHARS, the
# part that mattered (a remit spanning pricing and revenue intelligence) was lost and a
# note had to ground on weaker words (2026-10-19). It is the summary they wrote of their
# work for anyone to read; shown, it is cut to a line (hooks), and the verdict reads its
# first ABOUT_CHARS, as it always did.
ABOUT_KEEP = 2600


def _current_employer(headline: str, experience: list, org: str) -> str:
    """Where they work now: the first Experience entry, else the employer the headline
    names, else the top card's organisation line.

    The card's first organisation badge was taken as the employer for someone whose
    headline named a large employer: the badge was an industry body (2026-10-19). A
    badge is never preferred to the headline, and an Experience entry listed first
    (a side role at that body) gives way to the employer the headline names when that
    employer is in their Experience too.
    """
    import discovery
    head = _headline_employer(headline)
    exp = _current(experience)
    if head and exp and not discovery.same_employer(head, exp) \
            and any(_has(head, x) for x in experience):
        return head
    return exp or head or _card_employer(org)


def _names_them(name: str, lines: list) -> bool:
    """Their surname is on the page. Only the surname: the contact book may say
    Robert where the profile says Bob."""
    words = [w for w in fold(name).split() if len(w) > 1]
    if not words:
        return True
    text = fold(" ".join(lines[:400]))
    return re.search(r"(?<!\w)" + re.escape(words[-1]) + r"(?!\w)", text) is not None


# ------------------------------------------------------- what LinkedIn showed

# A check LinkedIn puts in front of the account: the one kind of page that ends the
# day's reads. Looked for first, because a check page can carry sign-in words too.
_CHECK = re.compile(
    r"security (?:verification|check)|let's do a quick security check|verify (?:your )?identity|"
    r"confirm (?:it's|that it's) you|captcha|are you a (?:human|robot)|press and hold|"
    r"unusual activity|suspicious activity|automated (?:activity|behaviou?r|software)|"
    r"account (?:has been |is )?(?:temporarily )?restricted|temporarily (?:limited|restricted)|"
    r"we've (?:detected|noticed)|too many (?:requests|profile views)|"
    # Chrome's own page for LinkedIn's refusal, which a browser shows as "HTTP ERROR 999"
    r"http error 999|\berror 999\b", re.I)
# Signed out: LinkedIn's sign-in or join page, or a public profile view behind its
# authwall. Before the person has signed in today this is a wait, never a stop.
_SIGNIN = re.compile(
    r"\bauthwall\b|^join linkedin$|^sign in$|join now|sign in to view|join to view|"
    r"new to linkedin\?|forgot password\?|agree & join|^welcome back$|"
    r"sign in with (?:email|apple|google)|email or phone|keep me logged in|"
    r"to see (?:more|their full profile), sign in", re.I | re.M)
# What only the signed-in view of a profile prints.
_SIGNED_IN = re.compile(r"^[\u00b7\u2022]?\s*contact info$|^(?:1st|2nd|3rd\+?)$|"
                        r"^[\u00b7\u2022]\s*(?:1st|2nd|3rd\+?)$|^message$|^connect$|^pending$|"
                        r"^more$", re.I | re.M)


def page_kind(text: str) -> tuple[str, str]:
    """("check" | "signin" | "profile" | "unknown", the words that decided it).

    Reads the page text the browser returned, nothing more: a check LinkedIn
    showed, its sign-in or join page, or a signed-in profile.
    """
    body = "\n".join(_clean_lines(text)[:120])
    m = _CHECK.search(body)
    if m:
        return "check", m.group(0)
    signed = len(_SIGNED_IN.findall(body))
    m = _SIGNIN.search(body)
    if m and signed < 3:
        return "signin", m.group(0)
    if signed >= 2 or _SECTION_LINE.search(body):
        return "profile", ""
    return "unknown", ""


_SECTION_LINE = re.compile(r"^(?:about|experience|education|activity)$", re.I | re.M)

# Where the pane is, by its address alone: the session looks at the tab's URL and
# title while the person signs in, never at the page.
_SIGNED_OUT_URL = re.compile(r"linkedin\.com/(?:login|uas/login|authwall|signup|"
                             r"checkpoint/lg|m/login)", re.I)
_CHECK_URL = re.compile(r"linkedin\.com/checkpoint/challenge", re.I)
_SIGNED_IN_URL = re.compile(r"linkedin\.com/(?:feed|in/|mynetwork|messaging|notifications|"
                            r"search/results|company/|jobs/|m/feed)", re.I)


def url_kind(url: str) -> str:
    """"signed-in", "verifying" (LinkedIn asking the person to confirm it is them while
    they sign in), or "waiting" (still on the sign-in page, or somewhere unclear)."""
    if _CHECK_URL.search(url or ""):
        return "verifying"
    if _SIGNED_OUT_URL.search(url or ""):
        return "waiting"
    return "signed-in" if _SIGNED_IN_URL.search(url or "") else "waiting"


def signed_in_today(today: datetime.date | None = None) -> bool:
    day = (today or datetime.date.today()).isoformat()
    return any(isinstance(got, dict) and got.get("date") == day
               for got in (_json(person.state(*SIGNIN_FILE)), pace.load().get("signed_in")))


def mark_signed_in(now: datetime.datetime | None = None) -> None:
    now = now or datetime.datetime.now()
    rec = {"date": now.date().isoformat(), "at": now.isoformat(timespec="seconds")}
    p = person.state(*SIGNIN_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
        fh.write("\n")
    pace.put("signed_in", rec)


SIGNIN_SAY = ("LinkedIn's sign-in is open in the browser pane. Sign in there yourself, then "
              "say 'done' or just wait; I'll carry on. You stay signed in after that, even with "
              "the browser hidden or closed.")


def signin_steps() -> list:
    """What the session does when LinkedIn is not signed in yet: open its sign-in page
    in the pane, say one sentence, and wait, looking only at the pane's address."""
    return [
        f"open {SIGNIN_URL} in the browser pane (the sign-in page, not a profile)",
        "look at whether the pane is showing: the browser tool's tabs_context says displayed, "
        "hidden or not open. Hidden or not open, the person cannot see the sign-in page: give "
        "them `python3 tools/claude_surfaces.py steps browser-pane-show` first (the pane keeps "
        "its sign-ins when hidden; it only goes out of view)",
        f"tell the person, once: {SIGNIN_SAY}",
        "never type in it, read it, look at it or keep anything from it while they sign in",
        f"every {SIGNIN_POLL_SECONDS}s, look only at the pane's address and title and run "
        "`reading.py signin --url <address>`: signed-in means carry on with the first "
        "profile; verifying means LinkedIn is asking them to confirm it is them, part of "
        "signing in, so keep waiting",
        f"after {SIGNIN_WAIT_MINUTES} minutes with no sign-in, ask once more whether they "
        "want to sign in now or send a paste of each profile instead; never give up silently",
    ]


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
    date = str(date or "").strip()
    if date.lower() == UNKNOWN_DATE:
        date = UNKNOWN_DATE
    exact = re.match(r"^\d{4}-\d{2}-\d{2}$", date) and dates.as_date(date, iso_only=True)
    if kind in _DATED and not (exact or _MONTH.match(date) and _approx(date)):
        raise ValueError(f"a {kind} needs its date, the day (YYYY-MM-DD) or at least the month "
                         "(YYYY-MM): an undated post may be years old")
    if date and date != UNKNOWN_DATE and not (exact or _approx(date)):
        raise ValueError(f"a date is YYYY-MM-DD, YYYY-MM, YYYY or 'unknown', not {date!r}")
    body = " ".join(untrusted.strip_markers(str(text or "")).split())[:EXCERPT]
    if not body:
        raise ValueError("a finding needs the words it rests on: the title or the line itself")
    return {"kind": kind, "date": date, "url": str(url or ""), "text": body}


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
    company = company or reading.get("company", "")
    headline = reading.get("headline", "")
    posts = " ".join(i.get("text", "") for i in reading.get("items", [])
                     if i.get("kind") in ("post", "repost") and (_item_days(i.get("date", ""), datetime.date.today()) or 0) <= 90)
    person_ = {"title": headline, "headline": headline,
               "about": _clip(reading.get("about", ""), ABOUT_CHARS),
               "activity": posts, "company": company, "location": reading.get("location", "")}
    why = discovery.disqualify(person_, target_company=company)
    if why:
        return False, why
    if reading.get("reach") == "pending":
        return False, "a connection request to them is already pending"
    current = reading.get("current", "")
    # The employer under another of its names ("<Name> Ratings", "<Brand>, AI by
    # <Parent>") is where they were found, not somewhere they moved to.
    if company and current and not discovery.same_employer(current, company) \
            and not _has(company, headline) and not _has(company, current):
        return False, f"has moved on: their current employer is {current}, not {company}"
    loc = reading.get("location", "")
    if loc and "remote" not in fold(headline):
        if discovery._abroad(loc):
            return False, f"based elsewhere: {loc}"
        # The person's own location gate, the one that screens postings, knows their
        # market and the places they consider. A place it fails is elsewhere. A bare
        # city it does not recognise ("Amsterdam", "Slough") cannot be placed without
        # a gazetteer: kept, with a caution, because a wrong skip loses a good contact.
        import prefilter
        v, why_loc = prefilter.location_verdict(loc, headline)
        if v == "FAIL":
            return False, f"based elsewhere: {loc} ({why_loc})"
        if "not recognized" in why_loc and not discovery._same_market(loc, discovery.HOME_CITY):
            return True, (f"caution: based in {loc}, a place your search does not name; check "
                          f"they work in {discovery.HOME_CITY} before writing")
    return True, ""


# --------------------------------------------------------------------- hooks

# A finding's date as it is known: a day, a month ("2026-03", a paper dated by its
# issue), a year, or "unknown" (an undated podcast). Making up a day for one, to get
# past a check that wanted YYYY-MM-DD, put a false precision into the record.
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_ONLY = re.compile(r"^(\d{4})$")
UNKNOWN_DATE = "unknown"


def _approx(date: str) -> datetime.date | None:
    """The earliest day a month or a year can mean, so its age is never understated."""
    text = str(date or "").strip()
    m = _MONTH.match(text)
    if m and 1 <= int(m.group(2)) <= 12:
        return datetime.date(int(m.group(1)), int(m.group(2)), 1)
    m = _YEAR_ONLY.match(text)
    if m:
        return datetime.date(int(m.group(1)), 1, 1)
    return None


def _days(date: str, today: datetime.date) -> int | None:
    # A timestamp is read as its day: a post dated 2026-10-17T10:00:00 is not undated.
    return dates.days_since(date, today, iso_only=True)


def _item_days(date: str, today: datetime.date) -> int | None:
    """A finding's age: its day, or for a month or a year known alone, from the earliest
    day it can mean. Only findings take the coarser dates; everything else stays exact."""
    got = _days(date, today)
    if got is None and _approx(date):
        return (today - _approx(date)).days
    return got


def shown_date(date: str) -> str:
    """A finding's date as it should read: the day, "March 2026", "2026", or "date unknown"."""
    text = str(date or "").strip()
    if not text or text.lower() == UNKNOWN_DATE:
        return "date unknown" if text else ""
    m = _MONTH.match(text)
    if m and _approx(text):
        return _approx(text).strftime("%B %Y")
    return text


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
        age = _item_days(i.get("date", ""), today)
        kind = i.get("kind", "")
        if kind in _DATED and (age is None or age > POST_DAYS):
            continue
        base = {"post": 8, "repost": 6, "comment": 5, "news": 4, "featured": 5}.get(kind, 7)
        if kind in _DATED and age is not None and age > 90:
            base -= 3
        when = f" ({shown_date(i['date'])})" if i.get("date") else ""
        out.append((base, kind, f"their {kind}{when}", i.get("text", "")))
    for p in shared.get("places", []):
        out.append((6, "same city before", f"you both worked in {p['name']}", p.get("evidence", "")))
    if reading.get("about"):
        out.append((3, "about", "something specific in their About", _clip(reading["about"], 200)))
    if reading.get("headline") and _page_read(reading):
        out.append((2, "headline", "what they call their work", reading["headline"]))
    return sorted(out, key=lambda h: -h[0])


def _page_read(reading: dict) -> bool:
    """Was their own page read (pasted, in the browser, a PDF, screenshots), not only searched?"""
    return any(s.get("kind") in PAGE_SOURCES for s in (reading or {}).get("sources", []))


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
    # Lowercased first: without it the pattern dropped every capital, so "Model
    # Governance" read as "odel overnance" and never met "model governance".
    return {w for w in re.findall(r"[a-z0-9][a-z0-9'&+.-]*[a-z0-9]|[a-z0-9]", fold(text).lower())
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
    today = datetime.date.today()
    # A dated item older than POST_DAYS is history, as hooks() treats it: a 2018
    # appointment is evidence of who was appointed, not of what they do now.
    sources = [(i.get("kind", "item"), i.get("text", "")) for i in reading.get("items", [])
               if not (i.get("kind") in _DATED and (_item_days(i.get("date", ""), today) or 0) > POST_DAYS)]
    sources += [("about", reading.get("about", ""))]
    # Their headline and current role count when they were read on their own page:
    # what they call their work is a fair thing to write about, and the page, not a
    # months-old search snippet, is where it was read.
    if _page_read(reading):
        sources += [("headline", reading.get("headline", "")),
                    ("current role", reading.get("current", ""))]
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
    """"phone", "web", "desktop-cloud", "local" or "unknown": where this session runs
    (tools/place.py, which the right-place check and this share)."""
    import place
    return place.surface(env)


def route(tools=(), consent: str | None = None, env=None, signed_in: bool | None = None) -> dict:
    """How this session reads a profile, chosen for the person, never asked of them.

    `tools` is what the session itself has: "browser" (the desktop app's built-in
    browser pane, as mcp__Claude_Browser__* or mcp__remote-devices__Claude_Browser__*),
    "chrome" (Claude in Chrome with a Chrome window connected), "chrome-off" (Claude
    in Chrome installed, but list_connected_browsers returned none), "enable"
    (enable__mcp__remote-devices__Claude_Browser, which turns the pane on for the
    conversation). Returns the route, which browser, whether it can be used now,
    what Claude does, and the one sentence the person is told ("" when nothing needs
    saying). A person is never told to press a key or find a setting.
    """
    have = {str(t).lower() for t in tools}
    consent = (consent or PROFILE_READS).lower()
    where = surface(env)
    signed_in = signed_in_today() if signed_in is None else signed_in
    hand = ("screenshots of their profile from the LinkedIn app" if where == "phone"
            else "their profile pasted (select all, copy), its Save to PDF, or screenshots")
    pane = ("the browser pane in the Claude desktop app" if where == "local"
            else "the browser pane in the Claude desktop app on your computer, while the app is open")
    first = ("" if signed_in else
             " The first time, LinkedIn's sign-in opens there: sign in yourself, once; the "
             "pane remembers it after that, until LinkedIn signs you out.")
    if consent == "off":
        return {"route": "public", "browser": "", "usable": False, "do": "public work only",
                "say": "", "signin": False}
    if consent == "browser":
        if "browser" in have or "chrome" in have:
            label = pane if "browser" in have else "your own Chrome, through Claude in Chrome"
            return {"route": "browser", "browser": label, "usable": True,
                    "do": ("`reading.py signin` first when it says so, then read each profile "
                           "in " + label + ", nothing clicked"),
                    "say": (f"I'll read the LinkedIn profiles of the best {READS_PER_RUN} I find, "
                            f"in {label}, one at a time, clicking nothing.{first}"),
                    "signin": not signed_in}
        if "enable" in have:
            return {"route": "enable", "browser": pane, "usable": True,
                    "do": "call enable__mcp__remote-devices__Claude_Browser, then `reading.py "
                          "signin` when it says so, and read each profile, nothing clicked",
                    "say": (f"I'll read the LinkedIn profiles of the best {READS_PER_RUN} I find, "
                            f"in {pane}, one at a time, clicking nothing.{first}"),
                    "signin": not signed_in}
        import place
        if "chrome-off" in have:
            say = ("Your setting reads profiles in your own browser, but Claude in Chrome is "
                   "installed and no Chrome window is connected to it. For now, for the one or "
                   f"two who matter most, send {hand} and I'll do the rest.")
        else:
            # The same words the place check says once, then weekly (tools/place.py): the
            # choice is offered, never made for them, and the setting is not changed.
            owner, name = place.repo()
            # A read was asked for here, so this is the person asking how: the full steps.
            told = place.check(where, "browser", [], True, (), owner, name, detail=True)
            say = told[0] if told else (f"For the one or two who matter most, send {hand} and "
                                        "I'll do the rest.")
        return {"route": "hand", "browser": "", "usable": False,
                "do": f"make the whole list from search results and their connections "
                      f"(sources.ladder); offer {hand} for the best {HAND_TOP} only, never "
                      "everyone, or carry on in the chat they move to",
                "say": say, "signin": False}
    return {"route": "hand", "browser": "", "usable": False,
            "do": f"make the whole list from search results and their connections "
                  f"(sources.ladder); offer {hand} for the best {HAND_TOP} only, never everyone",
            "say": (f"For the one or two who matter most, send {hand} and I'll make the note "
                    "about them; the rest are written from what the search found."),
            "signin": False}


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


def _loads(pages: bool = True) -> list:
    """Every browser page load on file, oldest first: [{kind, when, gap, brk, load_seconds}].

    Read from both places a load is written: beside the readings in documents/network,
    which a cloud session commits, and the ledger this computer keeps for the repository
    (tools/network/pace.py), which every worktree of it shares. One chat per worktree had
    its own record, so two chats on one account each read a full day's pages. The same
    load in both is counted once."""
    out, seen = [], set()

    def keep(kind, src):
        got = _load(src)
        if not got:
            return
        key = ("profile" if kind == "profile" else "page", got[0].isoformat(timespec="seconds"))
        if key in seen:
            return
        seen.add(key)
        out.append({"kind": kind, "when": got[0], "gap": got[1], "brk": got[2],
                    "load_seconds": src.get("load_seconds")})

    for f in glob.glob(person.state(*DIR, "*", "reading.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                srcs = json.load(fh).get("sources", [])
        except (OSError, ValueError):
            continue
        for src in srcs:
            if src.get("kind") == "browser" and src.get("at"):
                keep("profile", src)
    if pages:
        for p in _pages():
            keep(str(p.get("kind") or "people"), p)
    for rec in pace.load().get("loads") or []:
        if isinstance(rec, dict) and rec.get("at") and (pages or rec.get("kind") == "profile"):
            keep(str(rec.get("kind") or "profile"), rec)
    return sorted(out, key=lambda x: x["when"])


def _browser_reads(pages: bool = True) -> list:
    """Every browser page load on file, oldest first: [(when, the gap it asked for, a
    break?)]. A profile read and a one-page read (`page_read`) both count: the pace is
    about page loads, whatever the page held. `pages=False` is profiles alone."""
    return [(x["when"], x["gap"], x["brk"]) for x in _loads(pages)]


def _load(src: dict):
    """(when, gap, a break?) from one recorded read, or None when it carries no time."""
    try:
        gap = float(src.get("next_gap") or PACE_SECONDS)
        when = datetime.datetime.fromisoformat(str(src.get("at")))
    except (TypeError, ValueError):
        return None
    # A break was once told apart only by its length; one the person set shorter than
    # the longest gap would have restarted the count. It is recorded now.
    brk = bool(src["break"]) if "break" in src else gap > GAP_SECONDS[1]
    return (when, gap, brk)


def _pages() -> list:
    try:
        with open(person.state(*PAGES_FILE), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return []
    return [p for p in (got.get("reads") or []) if isinstance(p, dict)]


def _load_seconds_seen() -> list:
    return [x["load_seconds"] for x in _loads() if x.get("load_seconds") is not None]


def note_load(kind: str, at: str, gap: float, brk: bool, ident: str = "",
              load_seconds: float | None = None, now: datetime.datetime | None = None) -> str:
    """Record a browser load in the ledger, and how long it took to load where the session
    timed it: a load far slower than the person's own recent ones is a soft signal (pace.py),
    and a second within the hour stops the day. Returns the signal's kind, or ""."""
    history = _load_seconds_seen()
    pace.add_load(kind, at, gap, brk, ident, load_seconds)
    if load_seconds is not None and pace.slow(float(load_seconds), history):
        return signal("slow", "the page took %.0fs to load, against %.0fs usually"
                      % (float(load_seconds), sorted(history[-pace.SLOW_SAMPLE:])[
                          len(history[-pace.SLOW_SAMPLE:]) // 2]), now)
    return ""


def signal(kind: str, words: str = "", now: datetime.datetime | None = None) -> str:
    """Keep one friction signal, and stop the day's reads on a hard one, or on the second
    soft one within the hour. Returns the kind."""
    now = now or datetime.datetime.now()
    pace.record_friction(kind, words, now)
    if kind in pace.HARD or pace.soft_recent(now) >= pace.SOFT_STOPS:
        _write_stop("%s: %s" % (kind.replace("_", " "), words) if words else kind, now.date())
    return kind


def page_read(kind: str, url: str = "", now: datetime.datetime | None = None,
              people: int = 0, rng=None, load_seconds: float | None = None) -> dict:
    """Record one read of a page that lists many people (PAGE_KINDS): when, which, how
    many it named and the pause after it. Counts against the list-page and all-load caps,
    never the send-day cap. Returns the record."""
    if kind not in PAGE_KINDS:
        raise ValueError(f"a one-page read is one of {', '.join(PAGE_KINDS)}, not {kind!r}")
    now = now or datetime.datetime.now()
    gap, brk = pause(rng)
    rec = {"kind": kind, "url": str(url or ""), "at": now.isoformat(timespec="seconds"),
           "people": int(people), "next_gap": gap, "break": brk}
    if load_seconds is not None:
        rec["load_seconds"] = float(load_seconds)
    keep = [p for p in _pages() if str(p.get("at", ""))[:10] >= (now.date() - datetime.timedelta(days=7)).isoformat()]
    p = person.state(*PAGES_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"reads": keep + [rec]}, fh, indent=1)
        fh.write("\n")
    note_load(kind, rec["at"], gap, brk, rec["url"], load_seconds, now)
    return rec


def last_browser_read() -> datetime.datetime | None:
    reads = _browser_reads()
    return reads[-1][0] if reads else None


def stopped(today: datetime.date | None = None) -> str:
    """Why browser reads are stopped for today, or "". A warning ends the day's reads, in
    every chat on this computer: the ledger holds the stop as well as the file here."""
    day = (today or datetime.date.today()).isoformat()
    for got in (_json(person.state(*STOP_FILE)), pace.load().get("stop") or {}):
        if isinstance(got, dict) and got.get("date") == day:
            return str(got.get("reason") or "stopped")
    return ""


def _json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _write_stop(reason: str, today: datetime.date | None = None) -> str:
    rec = {"date": (today or datetime.date.today()).isoformat(),
           "reason": " ".join(str(reason or "").split())[:200]}
    p = person.state(*STOP_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
        fh.write("\n")
    pace.put("stop", rec)
    return p


def _signal_kind(reason: str) -> str:
    """The friction log's kind for what a stop said LinkedIn showed."""
    r = str(reason or "").lower()
    if "999" in r:
        return "http_999"
    if "unusual" in r or "suspicious" in r:
        return "unusual_activity"
    if "signed out" in r or "sign-in page after" in r:
        return "signed_out"
    return "check"


def stop(reason: str, today: datetime.date | None = None) -> str:
    """Record that LinkedIn showed a warning, a security check, a CAPTCHA or a sign-in wall:
    the day's reads stop, and the signal goes in the friction log, which holds the ramp back."""
    pace.record_friction(_signal_kind(reason), reason)
    return _write_stop(reason, today)


def sends_left_today(today: datetime.date | None = None) -> int | None:
    """Connection requests the person can still send today, or None when unknown."""
    try:
        import state
        b = state.platform_budget(state.load_contacts(), state.load_threads(),
                                  today or datetime.date.today())
        return int(b.get("connections_left_today"))
    except Exception:  # noqa: BLE001  the cap is a ceiling; without the book it stands alone
        return None


def gate_state(now: datetime.datetime | None = None, sends_left: int | None = -1,
               profile: bool = True) -> dict:
    """May a browser read go now? {"kind", "why", "at"}.

    kind is "go"; "wait" (the pause after the last page: a short wait, `at` says when);
    "later" (an hourly cap or the ramp: later today, at `at`); or "tomorrow" (stopped for
    the day, a daily cap, or enough read for the requests that can still go today).
    `profile` is False for a one-page read (PAGE_KINDS), which has caps of its own and
    which the send-day cap does not hold: that cap is about the people written to, and a
    list page writes to nobody. All loads together have caps as well, and the hourly one
    rises with clean days of reading (pace.hourly_ceiling). `sends_left` is the requests
    left today; -1 reads it from the contact book.
    """
    now = now or datetime.datetime.now()
    why = stopped(now.date())
    if why:
        return {"kind": "tomorrow", "at": None,
                "why": f"browser reads are stopped for today: {why}. Tomorrow, or a paste"}
    loads = _loads()
    ledger = pace.load()
    today = [x for x in loads if x["when"].date() == now.date()]
    mine = [x for x in today if (x["kind"] == "profile") == profile]
    kind_day, kind_name = ((READS_PER_DAY, "PROFILE_READS_PER_DAY") if profile
                           else (PAGES_PER_DAY, "PROFILE_PAGES_PER_DAY"))
    if len(mine) >= kind_day:
        return {"kind": "tomorrow", "at": None,
                "why": f"{kind_day} {'profiles' if profile else 'list pages'} read today "
                       f"({kind_name}); the rest wait for tomorrow or a paste"}
    if len(today) >= LOADS_PER_DAY:
        return {"kind": "tomorrow", "at": None,
                "why": f"{LOADS_PER_DAY} pages loaded today (PROFILE_LOADS_PER_DAY); the rest "
                       "wait for tomorrow or a paste"}
    if profile:
        left = sends_left_today(now.date()) if sends_left == -1 else sends_left
        people = [x for x in today if x["kind"] == "profile"]
        if left is not None and len(people) >= left + SKIP_SPARE:
            return {"kind": "tomorrow", "at": None,
                    "why": f"{len(people)} profiles read today, enough for the {left} "
                           "request(s) that can still go today: a profile is read only for "
                           "someone sent to that day. The rest wait for tomorrow"}
    window = now - datetime.timedelta(minutes=HOUR_MINUTES)
    hour = [x for x in loads if x["when"] > window]
    hour_mine = [x for x in hour if (x["kind"] == "profile") == profile]
    kind_hour, kind_hname = ((READS_PER_HOUR, "PROFILE_READS_PER_HOUR") if profile
                             else (PAGES_PER_HOUR, "PROFILE_PAGES_PER_HOUR"))
    ceiling, why_ceiling = pace.hourly_ceiling(now.date(), [x["when"] for x in loads], ledger)
    ceiling = min(ceiling, LOADS_PER_HOUR)
    for got, cap, name in ((hour_mine, kind_hour, kind_hname), (hour, ceiling, why_ceiling)):
        if len(got) >= cap:
            resume = min(x["when"] for x in got) + datetime.timedelta(minutes=HOUR_MINUTES)
            label = name if name.startswith("PROFILE_") else (
                "PROFILE_LOADS_PER_HOUR" if name == "loads_per_hour" else name)
            return {"kind": "later", "at": resume,
                    "why": f"{cap} pages in the last hour ({label}); the next after "
                           f"{resume:%H:%M}"}
    if loads:
        last = loads[-1]
        gap = last["gap"]
        # A soft signal within the hour (a page that did not render, a slow load) doubles
        # the pause before the next: a step back at the first sign, before any stop.
        if pace.soft_recent(now, ledger):
            gap *= 2
        waited = (now - last["when"]).total_seconds()
        if waited < gap:
            at = last["when"] + datetime.timedelta(seconds=gap)
            return {"kind": "wait", "at": at,
                    "why": f"{waited:.0f}s since the last page; wait {gap - waited:.0f}s more"}
    return {"kind": "go", "at": None, "why": ""}


def browser_gate(now: datetime.datetime | None = None, sends_left: int | None = -1,
                 profile: bool = True) -> str:
    """"" when a browser read may go now, otherwise why not and when it may."""
    return gate_state(now, sends_left, profile)["why"]


def reads_left(now: datetime.datetime | None = None, sends_left: int | None = -1) -> tuple:
    """(profiles that may still be read today, the limit that binds, said plainly).

    The queue printed the daily cap alone ("80 left today") while the hourly cap of 8
    was what held: the binding one is the smallest of the day, the hour, all loads, the
    ramp and the requests that can still go today."""
    now = now or datetime.datetime.now()
    loads = _loads()
    hour_ago = now - datetime.timedelta(minutes=HOUR_MINUTES)
    today = [x for x in loads if x["when"].date() == now.date()]
    profiles = [x for x in today if x["kind"] == "profile"]
    hour = [x for x in loads if x["when"] > hour_ago]
    ceiling, why_ceiling = pace.hourly_ceiling(now.date(), [x["when"] for x in loads])
    ceiling = min(ceiling, LOADS_PER_HOUR)
    limits = [(max(0, READS_PER_DAY - len(profiles)), f"{READS_PER_DAY} a day (PROFILE_READS_PER_DAY)"),
              (max(0, READS_PER_HOUR - sum(1 for x in hour if x["kind"] == "profile")),
               f"{READS_PER_HOUR} an hour (PROFILE_READS_PER_HOUR)"),
              (max(0, LOADS_PER_DAY - len(today)), f"{LOADS_PER_DAY} pages a day in all "
                                                    "(PROFILE_LOADS_PER_DAY)"),
              (max(0, ceiling - len(hour)), f"{ceiling} pages an hour in all ("
               + ("PROFILE_LOADS_PER_HOUR" if why_ceiling == "loads_per_hour" else why_ceiling)
               + ")")]
    left = sends_left_today(now.date()) if sends_left == -1 else sends_left
    if left is not None:
        limits.append((max(0, left + SKIP_SPARE - len(profiles)),
                       f"the {left} request(s) that can still go today, and {SKIP_SPARE} spare"))
    n, what = min(limits, key=lambda x: x[0])
    return n, what


def _is_break(reads) -> int:
    """How many reads since the last long break, this one included."""
    since_break = 0
    for r in reversed(reads):
        brk = r[2] if len(r) > 2 else r[1] > GAP_SECONDS[1]
        if brk:                            # a break, never a long ordinary gap
            break
        since_break += 1
    return since_break + 1


def pause(rng=None, reads=None) -> tuple:
    """(seconds to leave after this read, whether that is the long break)."""
    import math
    import random
    rng = rng or random
    reads = _browser_reads() if reads is None else reads
    if _is_break(reads) >= rng.randint(*BREAK_AFTER):
        return int(rng.uniform(*BREAK_SECONDS)), True
    gap = rng.lognormvariate(math.log(GAP_MEDIAN), 0.45)
    return int(min(max(gap, GAP_SECONDS[0]), GAP_SECONDS[1])), False


def next_gap(rng=None, reads=None) -> int:
    """The pause to leave after this read: varied, with a longer break that comes after
    anywhere from 3 to 7 reads, never on a fixed count."""
    return pause(rng, reads)[0]


def dwell(rng=None, mode: str = "deep") -> int:
    """Seconds to spend on a profile before its text is read. Deep: scrolled through to
    the end at reading pace, which is also what loads the About, Experience and Education
    sections LinkedIn only fills in as the page is scrolled. Card: the top card and About,
    nothing scrolled, which decides most keep or skip."""
    import random
    return int((rng or random).uniform(*(CARD_DWELL_SECONDS if mode == "card" else DWELL_SECONDS)))


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


def _shortlist_file(today: datetime.date) -> list:
    """Today's short list, from the file here and from this computer's ledger, which every
    worktree shares: one chat's list is every chat's."""
    day = today.isoformat()
    out = []
    for got in (_json(person.state(*SHORTLIST_FILE)), pace.load().get("shortlist") or {}):
        if isinstance(got, dict) and got.get("date") == day:
            out += [i for i in got.get("ids") or [] if i not in out]
    return out


def _save_shortlist(ids: list, today: datetime.date) -> None:
    rec = {"date": today.isoformat(), "ids": list(ids)}
    p = person.state(*SHORTLIST_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
        fh.write("\n")
    pace.put("shortlist", rec)


def _read_on(contact_id: str, day: str) -> bool:
    """Was their own page read on this day?"""
    got = load(contact_id) or {}
    return any(s.get("kind") in PAGE_SOURCES and str(s.get("date") or s.get("at") or "")[:10] == day
               for s in got.get("sources", []))


def _gone(contact_id: str, contacts, today: datetime.date) -> str:
    """Why someone no longer belongs on today's list, or "": their page was read on an
    earlier day and still stands, or the contact book has moved past a first note (written
    to, closed). A list made before a release, holding people since read or closed, filled
    the day and refused everyone better."""
    row = next((c for c in contacts or () if c.get("contact_id") == contact_id), None)
    if row is not None and (row.get("status") or "not_contacted") not in ("not_contacted",):
        return "now %s in the contact book" % row.get("status")
    got = load(contact_id)
    if got and _page_read(got) and fresh(got, today) and not _read_on(contact_id, today.isoformat()):
        return "read on %s, and that reading stands" % got.get("read_on")
    return ""


def shortlist_cap(sends_left: int | None = -1, today: datetime.date | None = None) -> tuple:
    """(how many may be on today's list, why): the requests that can still go today and
    SKIP_SPARE for those a read rules out, never above READS_PER_RUN."""
    left = sends_left_today(today) if sends_left == -1 else sends_left
    if left is None:
        return READS_PER_RUN, f"PROFILE_READS_PER_RUN {READS_PER_RUN}"
    need = left + SKIP_SPARE
    if need >= READS_PER_RUN:
        return READS_PER_RUN, (f"PROFILE_READS_PER_RUN {READS_PER_RUN}; {left} request(s) can "
                               "still go today")
    return need, f"the {left} request(s) that can still go today, and {SKIP_SPARE} spare"


def placed(contact_id: str, contacts=None) -> bool:
    """Has anything placed them in a city: the contact book's location, or a page
    (a profile or a one-page read) that showed one? A search result with no place in
    it leaves them unverified, and five of seven reads in one session went on people
    a place would have ruled out."""
    got = load(contact_id) or {}
    if str(got.get("location") or "").strip():
        return True
    if contacts is None:
        try:
            import state
            contacts = state.load_contacts()
        except Exception:  # noqa: BLE001  no contact book: nothing placed them
            contacts = []
    row = next((c for c in contacts if c.get("contact_id") == contact_id), {})
    return bool(str(row.get("location") or "").strip())


def shortlist(ids, today: datetime.date | None = None, contacts=None, remove=(),
              sends_left: int | None = -1) -> dict:
    """Add to today's short list for deep reads, best first. {"ids", "added", "full",
    "unplaced", "pruned", "removed", "cap", "why"}.

    It adds, never replaces wholesale: running it again with the ones still unread dropped
    the ones already read, and a list that can be replaced at will is no cap at all. But
    the people a list no longer needs leave it by themselves (`_gone`: read on an earlier
    day, or past a first note in the contact book), and `remove` takes one off by hand.
    Only the people still to read today, and those read today, count toward the cap
    (`shortlist_cap`, sized to the requests that can still go today), and at most
    UNVERIFIED_ON_SHORTLIST of them may be people nothing has placed in a city yet
    (`placed`): the rest of those wait for a one-page read or a public finding.
    """
    today = today or datetime.date.today()
    if contacts is None:
        try:
            import state
            contacts = state.load_contacts()
        except Exception:  # noqa: BLE001  no contact book: nothing is past a first note
            contacts = []
    had = _shortlist_file(today)
    removed = [i for i in had if i in set(remove)]
    pruned = {i: why for i in had if i not in removed for why in [_gone(i, contacts, today)] if why}
    have = [i for i in had if i not in removed and i not in pruned]
    cap, why = shortlist_cap(sends_left, today)
    unplaced_on = sum(1 for i in have if not placed(i, contacts))
    added, full, unplaced = [], [], []
    for i in dict.fromkeys(x for x in ids if x):
        if i in have or i in removed:
            continue
        if _gone(i, contacts, today):
            continue
        if len(have) >= cap:
            full.append(i)
            continue
        if not placed(i, contacts):
            if unplaced_on >= UNVERIFIED_ON_SHORTLIST:
                unplaced.append(i)
                continue
            unplaced_on += 1
        have.append(i)
        added.append(i)
    _save_shortlist(have, today)
    return {"ids": have, "added": added, "full": full, "unplaced": unplaced,
            "pruned": pruned, "removed": removed, "cap": cap, "why": why}


def on_shortlist(contact_id: str, today: datetime.date | None = None) -> bool:
    return contact_id in _shortlist_file(today or datetime.date.today())


def next_up(today: datetime.date | None = None, contacts=None) -> dict | None:
    """The next person on today's list whose page is still to read, as their contact row
    (or {"contact_id"} when they are not in the book yet), or None when none is left."""
    today = today or datetime.date.today()
    if contacts is None:
        try:
            import state
            contacts = state.load_contacts()
        except Exception:  # noqa: BLE001
            contacts = []
    for i in _shortlist_file(today):
        if _gone(i, contacts, today) or _read_on(i, today.isoformat()):
            continue
        return next((c for c in contacts if c.get("contact_id") == i), {"contact_id": i})
    return None


def read_recently(reading: dict | None, today: datetime.date | None = None) -> bool:
    """Was something read about them (their page, or public work kept) within FRESH_DAYS?
    The same test draft_text uses to decide a note rests on a reading, plus its age: the
    queue used fresh(), which counts their page alone, so a note rightly written from a
    talk or a post was listed as waiting on a read for good."""
    if not has_read(reading):
        return False
    age = _days((reading or {}).get("read_on", ""), today or datetime.date.today())
    return age is None or age <= FRESH_DAYS


def queue(contacts: list, today: datetime.date | None = None) -> list:
    """Contacts with a first note waiting and nothing read about them lately, or whose
    note still says it waits on a read: read since, and not rewritten yet."""
    import why
    out = []
    for c in contacts:
        cid = c.get("contact_id", "")
        if (c.get("status") or "not_contacted") != "not_contacted" or not cid:
            continue
        if not os.path.isfile(draft_path(cid)):
            continue
        # On hold, or at an employer the search has ruled out: never offered for a read.
        if why.not_writable(c, (), today):
            continue
        if waits_on_read(cid) or not read_recently(load(cid), today):
            out.append(c)
    return out


def written_the_older_way(contact_id: str) -> bool:
    """Is their waiting note one written before notes rested on a reading: nothing read
    about them, and no WAITS ON A READ line? Only those are what the network-notes
    method redoes. A note the current code wrote is either from a reading or opens on
    that line, and counting those too told every /network run to rewrite the notes the
    networking upgrade had just written, a rewrite that needs the very reads it waits on."""
    return (os.path.isfile(draft_path(contact_id)) and not waits_on_read(contact_id)
            and not has_read(load(contact_id)))


# ------------------------------------------------------------------- drafts

# The first line of a note written for someone nobody has read. A first note rests on
# what was read about them (compose.first_note(reading=) refuses one that does not),
# and the networking upgrade and a /network run with no browser both write notes from
# search results alone, which then sat in the queue looking ready to send. The line
# says so where anyone opening the draft sees it, and `queue` lists the draft until a
# note written from a reading replaces it.
WAITS_ON_A_READ = "WAITS ON A READ"


def draft_path(contact_id: str) -> str:
    return os.path.join(os.path.dirname(path(contact_id)), "draft.md")


def has_read(reading: dict | None) -> bool:
    """Was anything read about them: their own page, or a public finding kept?"""
    return _page_read(reading) or bool((reading or {}).get("items"))


def waits_on_read(contact_id: str) -> bool:
    """Does their waiting draft still open on the WAITS ON A READ line?"""
    try:
        with open(draft_path(contact_id), encoding="utf-8") as fh:
            return fh.readline().startswith(WAITS_ON_A_READ)
    except OSError:
        return False


def draft_text(contact_id: str, note: str, name: str = "") -> str:
    """The draft file for a first note: the note, under the WAITS ON A READ line when
    nothing has been read about them."""
    note = str(note or "").strip()
    if has_read(load(contact_id)):
        return note + "\n"
    who = name or "them"
    return (f"{WAITS_ON_A_READ}: nothing was read about {who}, so this note rests on the "
            "search result only and is not sent as it stands. Read their profile (a paste, "
            f"or the browser: python3 tools/network/reading.py read {contact_id} <file>), then "
            "rewrite it from what was read with compose.first_note(..., reading=) and "
            f"python3 tools/network/reading.py draft {contact_id} <file>.\n\n{note}\n")


def write_draft(contact_id: str, note: str, name: str = "") -> str:
    """Write documents/network/<contact_id>/draft.md (draft_text) and return its path."""
    p = draft_path(contact_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(draft_text(contact_id, note, name))
    return p


# ------------------------------------------------------------ one page, many people

# The sent-invitations list (claude_surfaces.py show linkedin-sent-invitations): one card a person,
# their name, their headline, then "Sent 3 days ago" and a Withdraw button. One read
# of it says who already has a request pending, for everyone at once, where reading
# each profile to find "Pending" spent a deep read on a fact this page holds.
_SENT_AGE = re.compile(r"^sent\s+(?:(today|yesterday)|(\d{1,3})\s+(minute|hour|day|week|month|year)s?\s+ago)\b",
                       re.I)
_INVITE_NOISE = re.compile(
    r"^(?:withdraw|manage invitations?|received|sent|people(?:\s*\(\d[\d,]*\))?|pages|events|"
    r"newsletters|all|grow|catch up|my network|invitations?|load more|show more|"
    r"view (?:.+'s )?profile|.+'s profile (?:picture|photo)|previous|next|page \d+ of \d+|"
    r"\d+ (?:people|invitations?)|you have no sent invitations?.*)$", re.I)


# The fold under a note's preview: everything above it, back to the Withdraw before
# it, is the note that went with the card above.
_MORE_LINE = re.compile(r"^(?:\u2026|\.\.\.)?\s*(?:see|show)\s+more$", re.I)
# The list's own count, "People (425)": how many requests are pending in all.
_INVITE_TOTAL = (re.compile(r"^(?:people|sent)\s*\((\d[\d,]*)\)$", re.I),
                 re.compile(r"^(\d[\d,]*)\s+(?:people|invitations?)$", re.I))


def invitations(text: str, today: datetime.date | None = None) -> list:
    """[{name, headline, sent}] from the sent-invitations page's text, in page order.
    `sent` is the day the request went, as near as "Sent 2 weeks ago" says: the latest
    day it can mean, so a card is never taken for newer than it is.

    A request sent with a note lists the note's preview after Withdraw, then "...show
    more", then the next card. Taking the first line after Withdraw as the next name
    named every later card after the note above it. So a card is the two lines before
    its "Sent" line, its name and its headline, and whatever sits between the last
    Withdraw and those two (to the fold, when there is one) is the note of the card
    above it, never a name: kept on that card as `note` (`note_cut` where the page folds
    it), so a send recorded from this page logs the words the person wrote.
    """
    today = today or datetime.date.today()
    out, block = [], []
    for line in _clean_lines(text):
        m = _SENT_AGE.match(line)
        if m:
            people = [x for x in block if not _INVITE_NOISE.match(x) and not _NOISE.match(x)
                      and not _CARD_SKIP.search(x)]
            if len(people) > 2 and out and "note" not in out[-1]:
                # A note with no fold: its lines run on into the next card's two.
                out[-1]["note"], out[-1]["note_cut"] = " ".join(people[:-2])[:1000], False
            if people:
                if m.group(1):
                    when = today - datetime.timedelta(days=0 if m.group(1).lower() == "today" else 1)
                else:
                    unit = {"minute": "m", "hour": "h", "day": "d", "week": "w", "month": "mo",
                            "year": "y"}[m.group(3).lower()]
                    when = datetime.date.fromisoformat(_age_date(int(m.group(2)), unit, today))
                name, headline = (people[-2], people[-1]) if len(people) > 1 else (people[0], "")
                out.append({"name": name[:120], "headline": headline[:160], "sent": when.isoformat()})
            block = []
            continue
        if _MORE_LINE.match(line):
            # A note's preview ends here, cut by the page: the card above it wrote it, and
            # the next card starts.
            words = [x for x in block if not _INVITE_NOISE.match(x) and not _NOISE.match(x)]
            if words and out and "note" not in out[-1]:
                out[-1]["note"], out[-1]["note_cut"] = " ".join(words)[:1000], True
            block = []
            continue
        if _INVITE_NOISE.match(line):
            if line.lower() == "withdraw":
                block = []
            continue
        block.append(line)
    return out


def invitations_total(text: str) -> int | None:
    """How many requests the list says are pending in all ("People (425)"), or None.
    The tab's own count first; "425 people" only where the page has no tab count."""
    lines = _clean_lines(text)[:40]
    for rx in _INVITE_TOTAL:
        m = next((m for m in map(rx.match, lines) if m), None)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


# Letters after a name, however a card writes them ("Ph. D.", "PhD", "M.B.A.", "CFA").
# Two letters or fewer only in capitals or with dots: a two-letter surname such as
# "Ma" stays a surname.
_POSTNOMINALS = frozenset("""phd dphil md mba msc mres mphil meng bsc bcomm ba bs ma ms mpa mph
llb llm jd cfa cpa cma cfp pmp frm cissp peng ceng pe esq acca aca fca fcca cima acma caia
csm psm fia fsa asa cipd mcipd frsa rn jr sr ii iii iv""".split())
_HONORIFIC_WORDS = frozenset({"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir"})
_PRONOUN_WORDS = frozenset({"he", "him", "his", "she", "her", "hers", "they", "them", "their",
                            "theirs", "ze", "zir", "xe", "xem", "any", "pronouns"})


def _bare_word(token: str) -> str:
    return re.sub(r"[\W_]+", "", fold(token).lower())


def _postnominal(tokens: list) -> bool:
    joined = "".join(tokens)
    bare = re.sub(r"[\W_]+", "", fold(joined))
    low = bare.lower()
    if low not in _POSTNOMINALS:
        return False
    return len(low) > 2 or bare.isupper() or "." in joined


def _name_parts(name: str):
    """({the given names they may go by}, surname) from a name as a card or the contact
    book writes it, or None when it is not a first and last name.

    A card wrote a name with a middle name, a nickname in brackets and "Ph. D." after it
    ("Tamsin Rhian (Wren) Oyelaran, Ph. D.") where the contact book had the nickname and
    the surname ("Wren Oyelaran"), and the exact match the list used never saw them as
    one person. So: a nickname in brackets is a given name they go by (a pronoun in
    brackets is not), letters after the name go however they are dotted or spaced, an
    honorific goes, and a middle name is neither a given name to match on nor the
    surname. A part after a comma is letters after the name ("Oyelaran, PhD, PMP") or
    not a name at all, so it is left out.
    """
    raw = fold(str(name or ""))
    nicks = []
    for inner in re.findall(r"\(([^)]*)\)", raw):
        words = [_bare_word(w) for w in inner.split() if _bare_word(w)]
        if (not words or "/" in inner or set(words) <= _PRONOUN_WORDS
                or words[0] in ("nee", "born", "formerly")):
            continue
        nicks.append(words[0])
    s = re.sub(r"\([^)]*\)", " ", raw)
    s = re.split(r"\s+[|\u2013\u2014\u00b7\u2022-]\s+", s)[0]
    tokens = [t for t in s.split(",")[0].split() if _bare_word(t)]
    while tokens and _bare_word(tokens[0]) in _HONORIFIC_WORDS:
        tokens.pop(0)
    while len(tokens) > 2:
        for k in (3, 2, 1):
            if len(tokens) - k >= 2 and _postnominal(tokens[-k:]):
                del tokens[-k:]
                break
        else:
            break
    if len(tokens) < 2:
        return None
    return {_bare_word(tokens[0]), *nicks}, _bare_word(tokens[-1])


def same_person(a: str, b: str) -> bool:
    """Do two written names name one person: the same surname, and a given name one of
    them goes by in common (the first name, or a nickname in brackets)?"""
    pa, pb = _name_parts(a), _name_parts(b)
    return bool(pa and pb and pa[1] == pb[1] and pa[0] & pb[0])


def match_invitations(cards: list, contacts: list, threads: list | None = None,
                      total: int | None = None) -> dict:
    """{"pending": [(card, contact)], "unknown": [card], "gone": [contact],
    "unchecked": [contact], "oldest": the oldest loaded card's day, "complete": bool}.

    pending: a card whose name is a contact the log has not heard went (a request sent
    from LinkedIn itself). gone: a request the log has as waiting that the page no
    longer lists (accepted, or withdrawn there): told, never written.

    The page loads about ten of the list (one session: ten of 425), newest first. A
    request missing from the loaded part is gone only when it went after the oldest
    card loaded, which is where the loaded part ends; one that went on or before that
    day is `unchecked`, never gone: the page says nothing about it. Every one of the
    415 not loaded had been reported as no longer pending. `total` is the list's own
    count (invitations_total); when every card is loaded, every request is checked.
    """
    import state
    parts = [(c, _name_parts(c.get("name"))) for c in contacts]
    pending, unknown, listed = [], [], set()
    for card in cards:
        want = _name_parts(card["name"])
        rows = [c for c, p in parts if want and p and p[1] == want[1] and p[0] & want[0]]
        if len(rows) > 1:
            rows = [c for c in rows if _has(c.get("company") or "", card["headline"])] or rows[:0]
        if len(rows) != 1:
            unknown.append(card)
            continue
        c = rows[0]
        listed.add(c.get("contact_id"))
        if (c.get("status") or "not_contacted") in ("not_contacted", "dropped"):
            pending.append((card, c))
    if threads is None:
        threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    oldest = min((c["sent"] for c in cards if c.get("sent")), default="")
    complete = total is not None and total <= len(cards)
    edge = datetime.date.fromisoformat(oldest) if oldest else None
    gone, unchecked = [], []
    for c in contacts:
        cid = c.get("contact_id")
        if cid in listed:
            continue
        rows = [r for r in state.threads_for(threads, cid) if state._direction(r)]
        when = state.request_pending(rows)
        if when is None:
            continue
        if complete or (edge is not None and when > edge):
            gone.append(c)
        else:
            unchecked.append(c)
    return {"pending": pending, "unknown": unknown, "gone": gone, "unchecked": unchecked,
            "oldest": oldest, "complete": complete}


# What a people-search card says about where someone works now: LinkedIn's
# "Current: <role> at <employer>" line under the headline.
_CURRENT_LINE = re.compile(r"^current:\s*(.+)$", re.I)


def _employer_names(company: str) -> list:
    """The employer as people write it: its name, the name without a legal suffix, and
    the profile's aliases for it (employers.py COMPANY_ALIASES)."""
    import company_key
    import discovery
    k = company_key.key(company)
    names = [company, discovery.search_name(company)]
    names += [a for a, v in company_key.ALIASES.items() if v == k and len(a) > 1]
    return list(dict.fromkeys(n for n in (x.strip() for x in names) if n))


def _said(name: str, text: str) -> bool:
    """`name` in `text` as whole words, in any case: a profile's alias is stored in
    lower case ("kmu") and a headline writes it in capitals ("KMU")."""
    n = fold(name).strip().lower()
    return bool(n) and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)",
                                 fold(text).lower()) is not None


def card_where(person_: dict, company: str) -> tuple[str, str]:
    """("at" | "elsewhere" | "unknown", the employer the card names) for one card.

    A people search for an employer returns people at other employers too, and the
    one-page read screened nobody by employer: every card passed, and the command
    counted them all as at the employer. The card's "Current:" line decides first,
    then the headline: the employer it names as where they work ("<role> at <X>",
    "<role> @ <X>"), or the employer itself named anywhere in it, never in the past
    ("ex-<X>"). A card that says neither, or names another employer beside it, is
    "unknown", which a deep read settles: a wrong "elsewhere" loses a good contact.
    """
    import discovery
    names = _employer_names(company)
    for text in (person_.get("current_line", ""), person_.get("title", "")):
        if not text:
            continue
        now = _PAST_PART.sub(" ", text)
        emp = _headline_employer(text)
        if emp and (discovery.same_employer(emp, company) or discovery._target_in(emp, company)):
            return "at", emp
        named = any(_said(n, now) for n in names) or discovery._names_employer(now, company)
        if emp:
            return ("unknown", "") if named else ("elsewhere", emp)
        if named:
            return "at", company
    return "unknown", ""


def people_page(text: str, company: str) -> list:
    """[{name, title, location, degree, reach, linkedin_url, where, employer}] from an
    employer's People tab or a people search, read once: a dozen people's headline,
    place and degree for one page load. `reach` is "pending" where the card shows a
    request already sent; `where` is card_where()'s answer."""
    import sources
    people = sources.people_paste(text, company)
    lines = _clean_lines(text)
    promo = sources._promo_lines(lines)
    starts, at = [], 0
    for p in people:
        i = next((n for n in range(at, len(lines))
                  if n not in promo and lines[n].startswith(p["name"])), None)
        starts.append(i)
        at = i + 1 if i is not None else at
    for n, p in enumerate(people):
        p["reach"], p["current_line"] = "", ""
        i = starts[n]
        if i is not None:
            stop = next((s for s in starts[n + 1:] if s is not None), len(lines))
            for x in lines[i + 1:min(i + 9, stop)]:
                low = x.strip().lower()
                if low == "pending":
                    p["reach"] = "pending"
                    break
                if low in ("connect", "message", "follow"):
                    p["reach"] = {"connect": "request", "message": "message",
                                  "follow": "request under More"}[low]
                    break
            p["current_line"] = next((m.group(1) for m in (_CURRENT_LINE.match(x)
                                                           for x in lines[i + 1:stop]) if m), "")
        p["where"], p["employer"] = card_where(p, company)
    return people


def screen(person_: dict, company: str) -> tuple[bool, str]:
    """The cheap check on what a one-page read showed: (still worth a deep read, why not).
    A card that names another employer as where they work is out; one that names none
    is kept, with that said, because a wrong skip costs a good contact."""
    where, employer = person_.get("where"), person_.get("employer", "")
    if where is None:
        where, employer = card_where(person_, company)
    # A request already pending is said first: it is recorded as sent, never closed.
    if where == "elsewhere" and person_.get("reach") != "pending":
        return False, f"works elsewhere: the card names {employer}, not {company}"
    provisional = {"headline": person_.get("title", ""), "location": person_.get("location", ""),
                   "reach": person_.get("reach", ""), "current": "", "items": [], "about": ""}
    keep, why = verdict(provisional, company)
    if keep and where == "unknown":
        why = "; ".join(x for x in (why, f"the card does not say where they work: the deep "
                                         f"read checks it is {company}") if x)
    return keep, why


def from_list(contact_id: str, person_: dict, company: str, url: str = "",
              today: datetime.date | None = None) -> dict:
    """Keep what a one-page read showed about one person, beside anything read before.
    A "list" source: it places them and screens them, and it is never a read of their
    own page, so a note still cannot rest on it."""
    today = today or datetime.date.today()
    old = load(contact_id) or {}
    new = {"name": person_.get("name", ""), "company": company, "read_on": old.get("read_on", ""),
           "sources": [{"kind": "list", "url": url, "date": today.isoformat()}],
           "headline": person_.get("title", ""), "location": person_.get("location", ""),
           "degree": person_.get("degree", ""), "reach": person_.get("reach", ""), "items": []}
    if old:
        got = dict(old)
        for k in ("headline", "location", "degree"):
            got[k] = old.get(k) or new[k]
        if new["reach"]:
            got["reach"] = new["reach"]
        got["sources"] = old.get("sources", []) + new["sources"]
    else:
        got = {**new, "about": "", "shared": {}, "current": ""}
    save(contact_id, got)
    return got


# ------------------------------------------------------------ notes too alike

# How many notes in a batch may share one sentence before the batch reads as a
# template: two, or a third of the batch, whichever is more.
ALIKE_MIN = 2
ALIKE_SHARE = 1 / 3
# A line the person's profile says varies by person (VARY_ABOUT_ME), so it is held to
# the same rule as anything else a drafter repeats.
VARY_ABOUT_ME = bool(getattr(_NET, "VARY_ABOUT_ME", False))
_GREETING = re.compile(r"^\s*(?:hi|hello|hey|dear)\b[^,.!?]{0,40}[,.!]\s*", re.I)


def _sentences(note: str) -> list:
    body = _GREETING.sub("", " ".join(str(note or "").split()))
    return [x.strip() for x in re.split(r"(?<=[.?!])\s+", body) if len(x.strip()) >= 12]


def _same(a: str, b: str) -> bool:
    wa = set(re.findall(r"[a-z0-9']+", fold(a).lower()))
    wb = set(re.findall(r"[a-z0-9']+", fold(b).lower()))
    return bool(wa) and bool(wb) and len(wa & wb) / len(wa | wb) >= 0.8


def alike(notes: dict, ask: str | None = None, about_me: str | None = None,
          opener: str | None = None, vary_about_me: bool | None = None) -> list:
    """What makes a batch of first notes a template: [(what, sentence, [ids])].

    `same_ground` compares only the common ground, so ten notes ending on one sentence
    passed. Here every sentence counts: one shared by more than ALIKE_MIN notes (or
    ALIKE_SHARE of the batch) is a finding, and so is an ask that is not the person's
    own (ASK in networking.py, the one place it lives). The person's opener, their
    ASK and their ABOUT_ME are theirs to repeat, unless VARY_ABOUT_ME says the
    background line differs by person."""
    import compose
    ask = compose.ASK if ask is None else ask
    about_me = compose.ABOUT_ME if about_me is None else about_me
    opener = compose.OPENER if opener is None else opener
    vary = VARY_ABOUT_ME if vary_about_me is None else vary_about_me
    own = [x for x in (ask, opener) + (() if vary else (about_me,)) if x]
    per = {cid: _sentences(t) for cid, t in notes.items()}
    limit = max(ALIKE_MIN, int(len(notes) * ALIKE_SHARE))
    out, seen = [], []
    for sents in per.values():
        for sent in sents:
            if any(_same(sent, x) for x in own) or any(_same(sent, x) for x in seen):
                continue
            ids = [k for k, v in per.items() if any(_same(sent, y) for y in v)]
            if len(ids) > limit:
                out.append(("shared", sent, ids))
                seen.append(sent)
    if ask:
        asks = {}
        for cid, sents in per.items():
            last = sents[-1] if sents else ""
            if last.endswith("?") and not _same(last, ask) and re.search(
                    r"\b(?:open to|quick (?:chat|call)|minutes|few questions|grab a coffee|"
                    r"catch up|connect)\b", last, re.I):
                asks.setdefault(last, []).append(cid)
        for sent, ids in asks.items():
            out.append(("not your ask", sent, ids))
    return out


def queued_notes(contacts: list) -> dict:
    """{contact_id: note} for every first note waiting to be sent, without its marker line."""
    out = {}
    for c in contacts:
        cid = c.get("contact_id", "")
        if (c.get("status") or "not_contacted") != "not_contacted" or not cid:
            continue
        try:
            with open(draft_path(cid), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, ValueError):
            continue
        if text.startswith(WAITS_ON_A_READ):
            text = text.split("\n\n", 1)[-1]
        out[cid] = text.strip()
    return out


# ------------------------------------------------------------ read-only extractor

# A snippet the browser tool runs on a profile page it already has open, returning
# the parts a reading keeps as compact JSON: no click, no scroll, no request. Copying
# the whole page text out by hand cost thousands of tokens a profile and changed what
# was captured; this returns the same text get_page_text would, cut to the sections
# parse() reads. `read --json` takes its output.
EXTRACTOR = r"""(() => {
  const clip = (t, n) => (t || "").replace(/\n{3,}/g, "\n\n").trim().slice(0, n);
  const main = document.querySelector("main") || document.body;
  const out = {url: location.href, title: document.title, top: "", sections: []};
  const secs = Array.from(main.querySelectorAll("section"));
  if (secs.length) out.top = clip(secs[0].innerText, 1500);
  const want = /^(about|activity|experience|education|featured|publications)$/i;
  for (const s of secs.slice(1)) {
    const h = s.querySelector("h2");
    const head = h ? h.innerText.split("\n")[0].trim() : "";
    if (want.test(head)) out.sections.push({heading: head, text: clip(s.innerText, 2500)});
  }
  return JSON.stringify(out);
})()"""


def from_extract(raw: str) -> str:
    """The extractor's JSON as the page text parse() reads: the top card, then each
    section under its heading."""
    got = json.loads(raw)
    if isinstance(got, str):
        got = json.loads(got)
    parts = [str(got.get("top") or "")]
    for sec in got.get("sections") or []:
        head = str(sec.get("heading") or "").strip()
        body = str(sec.get("text") or "")
        if head and not body.lstrip().lower().startswith(head.lower()):
            body = head + "\n" + body
        parts.append(body)
    return "\n".join(p for p in parts if p.strip())


# ------------------------------------------------------------ several in one paste

# One paste holding several profiles: the person opens each to send the request and
# copies them into one message. Between two profiles, a line of three or more dashes
# (or underscores, or equals signs). Each piece is parsed on its own, so a wrong tab
# is refused for that profile alone (parse()'s name check), never saved under somebody.
PASTE_SEPARATOR = re.compile(r"^[ \t]*(?:-{3,}|_{3,}|={3,})[ \t]*$", re.M)


def split_paste(text: str) -> list:
    """The profiles in one paste, in order; a paste with no separator is one profile."""
    return [p.strip() for p in PASTE_SEPARATOR.split(str(text or "")) if p.strip()]


def _word_in(word: str, text: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text) is not None


def match_paste(pieces: list, contacts: list) -> list:
    """[(piece, contact or None, why)]: each pasted profile matched to one contact.

    A profile matches when the top of its page (before its first section, never
    LinkedIn's column of other people) carries the contact's whole name, or their
    surname with their employer named on the page. Two contacts it could equally be,
    or none, leave it unmatched with the reason; a contact is matched at most once.
    """
    import discovery
    import state
    out, used = [], set()
    for piece in pieces:
        lines = _clean_lines(piece)
        pre, secs, _ = _sections(lines)
        top = fold(" ".join(pre[:60] or lines[:60])).lower()
        page = fold(" ".join(pre + [x for v in secs.values() for x in v])).lower()
        scored = []
        for c in contacts:
            cid = c.get("contact_id", "")
            words = [w for w in fold(state.person_name(c.get("name"))).lower().split() if len(w) > 1]
            if not cid or cid in used or not words or not _word_in(words[-1], top):
                continue
            company = discovery.search_name(c.get("company") or "").lower()
            at = bool(company) and _has(company, page)
            full = all(_word_in(w, top) for w in words)
            if full or at:
                scored.append((int(full) + int(at), c))
        best = max((n for n, _ in scored), default=0)
        tops = [c for n, c in scored if n == best]
        if len(tops) == 1:
            used.add(tops[0]["contact_id"])
            out.append((piece, tops[0], ""))
        elif tops:
            out.append((piece, None, "could be " + " or ".join(
                f"{c.get('name')} ({c['contact_id']})" for c in tops)))
        else:
            out.append((piece, None, "names nobody whose note waits on a read"))
    return out


# ----------------------------------------------------------------------- CLI

def _paste(text: str, source: str = "paste", today: datetime.date | None = None) -> int:
    """Read several pasted profiles at once: each matched to a queued contact, parsed
    on its own, saved; then which matched, which did not, and what to do next."""
    import state
    pieces = split_paste(text)
    waiting = queue(state.load_contacts(), today)
    print(f"reading: {len(pieces)} profile(s) in the paste, {len(waiting)} note(s) waiting on a read")
    read, skipped = [], []
    for i, (piece, c, why) in enumerate(match_paste(pieces, waiting), 1):
        head = _clip(next(iter(_clean_lines(piece)), ""), 60)
        if c is None:
            print(f"  {i}. not matched (\"{head}\"): {why}")
            continue
        try:
            new = parse(piece, name=c.get("name", ""), company=c.get("company", ""),
                        source=source, url=c.get("linkedin_url", ""), today=today)
        except ValueError as e:
            print(f"  {i}. not read (\"{head}\"): {e}")
            continue
        save(c["contact_id"], merge(load(c["contact_id"]), new))
        keep, why_ = verdict(load(c["contact_id"]), c.get("company", ""))
        print(f"  {i}. {c.get('name')} ({c['contact_id']}): read; "
              + ("KEEP" + (f" ({why_})" if why_ else "") if keep else f"SKIP: {why_}"))
        (read if keep else skipped).append(c)
    rest = [c for c in waiting if c not in read and c not in skipped]
    if rest:
        print("  still waiting on a read: " + ", ".join(
            f"{c.get('name')} ({c['contact_id']})" for c in rest))
    if read:
        print("next: rewrite each note read above from its reading, `reading.py show <id>` for "
              "what it can rest on, then compose.first_note(..., reading=reading.load(<id>)), "
              "reading.same_ground() across them, and `reading.py draft <id> <file>`; show "
              "each new note in the reply")
    for c in skipped:
        _, why_ = verdict(load(c["contact_id"]), c.get("company", ""))
        print(_skip_hint(c["contact_id"], why_))
    if not read and not skipped:
        print("next: nothing matched; paste each profile under a line of --- and check the "
              "names against `reading.py queue`")
    return 0 if read or skipped else 1


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


def _skip_hint(contact_id: str, why: str) -> str:
    """What to run after a SKIP: a request already pending is recorded as sent, never
    closed; anything else closes the contact with its reason and removes the draft.

    The command is printed whole, the reason quoted for the shell so it runs as printed
    whatever the reason holds, and it says it is run once the person has confirmed
    nothing else is needed from them: a skip is final, and a contact closed is never
    surfaced again."""
    if "already pending" in why:
        return (f"next: a request already went, from LinkedIn itself: python3 "
                f"tools/network/state.py sent {contact_id} --outside")
    import shlex
    return ("next, once the person has confirmed nothing else is needed from them: python3 "
            f"tools/network/reading.py skip {contact_id} --reason {shlex.quote(why)} "
            "(closes them with the reason and removes their draft)")


def _gate_line(g: dict, now: datetime.datetime) -> str:
    if g["kind"] == "go":
        return ""
    when = ""
    if g.get("at"):
        secs = max(0, int((g["at"] - now).total_seconds()))
        when = f"; next page at {g['at']:%H:%M:%S} (in {secs}s)"
    return f"{g['kind']}: {g['why']}{when}"


def _wait_gate(timeout: float, profile: bool = True, sleep=None, clock=None) -> dict:
    """Hold until a browser page may load, up to `timeout` seconds. A Claude session
    cannot sleep in the foreground (the harness refuses it), so `gate --wait` is run
    in the background and exits when the gate opens, or with the reason at the
    timeout. Never waits for "tomorrow"."""
    import time
    sleep = sleep or time.sleep
    clock = clock or datetime.datetime.now
    end = clock() + datetime.timedelta(seconds=max(0.0, timeout))
    while True:
        now = clock()
        g = gate_state(now, profile=profile)
        if g["kind"] in ("go", "tomorrow") or not g.get("at") or g["at"] > end:
            return g
        sleep(max(1.0, min(30.0, (g["at"] - now).total_seconds() + 1)))


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
    r.add_argument("--json", action="store_true",
                   help="the file is the `extractor` snippet's JSON, not page text")
    r.add_argument("--mode", choices=READ_MODES, default="deep",
                   help="card: read from the top card and About; deep: scrolled to the end")
    r.add_argument("--load-seconds", type=float, default=None,
                   help="how long the page took to load, where the session timed it")
    v = sub.add_parser("verdict", help="after the read: KEEP, SKIP (exit 3), or not read yet (10)")
    v.add_argument("contact_id")
    v.add_argument("--company", default="")
    a_ = sub.add_parser("add", help="one public finding: a talk, an article, a post")
    a_.add_argument("contact_id")
    a_.add_argument("--kind", required=True, choices=KINDS)
    a_.add_argument("--url", required=True)
    a_.add_argument("--date", default="",
                    help="YYYY-MM-DD, or YYYY-MM or YYYY when that is all that is known, or unknown")
    a_.add_argument("--text", required=True)
    a_.add_argument("--name", default="", help="for a candidate not in the contact book yet")
    a_.add_argument("--company", default="")
    s = sub.add_parser("show")
    s.add_argument("contact_id")
    pa = sub.add_parser("paste", help="one paste holding several profiles, each matched to "
                                      "a contact whose note waits on a read")
    pa.add_argument("file", help="the paste, or - for stdin; profiles split by a line of ---")
    pa.add_argument("--source", choices=("paste", "screenshot"), default="paste")
    dr = sub.add_parser("draft", help="write a first note to the contact's draft.md, marked "
                                      "WAITS ON A READ when nothing was read about them")
    dr.add_argument("contact_id")
    dr.add_argument("file", help="the note, or - for stdin")
    qu = sub.add_parser("queue", help="drafts waiting with no fresh reading")
    qu.add_argument("--top", type=int, default=HAND_TOP,
                    help="how many to offer a paste for: the best few, never everyone")
    qu.add_argument("--urls", action="store_true",
                    help="the fast path: only their profile addresses, to open by hand and "
                         "paste back in one go (no automation at all)")
    sl = sub.add_parser("shortlist", help="add to today's short list for deep reads, best first")
    sl.add_argument("ids", nargs="*")
    sl.add_argument("--remove", nargs="+", default=[], metavar="ID",
                    help="take people off today's list")
    nx = sub.add_parser("next", help="the next person on today's list to read, once a page may "
                                     "load (run with --wait in the background)")
    nx.add_argument("--wait", action="store_true")
    nx.add_argument("--timeout", type=float, default=900.0)
    nx.add_argument("--mode", choices=READ_MODES, default="card",
                    help="card: the top card and About, nothing scrolled; deep: scrolled to "
                         "the end, for Experience and Activity")
    sub.add_parser("limits", help="every reading limit, its value, where it came from, and why")
    fr = sub.add_parser("friction", help="the signals LinkedIn showed, and the ramp; or keep one")
    fr.add_argument("--kind", choices=pace.HARD + pace.SOFT, default=None)
    fr.add_argument("--words", default="", help="what it showed, word for word")
    su = sub.add_parser("search-url", help="a people search narrowed to one employer (and a "
                                           "place), from the filters the person set once")
    su.add_argument("--company", required=True)
    su.add_argument("--place", default="")
    su.add_argument("--keywords", default="")
    su.add_argument("--learn", default="", metavar="ADDRESS",
                    help="the address of a search the person filtered by hand: its filters are "
                         "kept for this employer (and place)")
    st = sub.add_parser("stop", help="LinkedIn showed a check or a warning: no browser reads today")
    st.add_argument("reason", nargs="?", default="")
    st.add_argument("--reason", dest="reason_flag", default="")
    ga = sub.add_parser("gate", help="may a browser page load go now, and if not, when")
    ga.add_argument("--wait", action="store_true",
                    help="hold until it may (run it in the background), up to --timeout")
    ga.add_argument("--timeout", type=float, default=900.0)
    ga.add_argument("--page", action="store_true",
                    help="for a one-page read (invitations, people), which the send-day cap does not hold")
    ga.add_argument("--mode", choices=READ_MODES, default="deep")
    pg = sub.add_parser("page", help="what LinkedIn showed: a profile, its sign-in page, or a check")
    pg.add_argument("file", help="the page text, or - for stdin")
    si = sub.add_parser("signin", help="LinkedIn is not signed in yet: what to do, and the wait")
    si.add_argument("--url", default="", help="the pane's address, looked at while they sign in")
    si.add_argument("--done", action="store_true", help="a signed-in page was seen")
    ro = sub.add_parser("route", help="how this session reads profiles, and what to tell the person")
    ro.add_argument("--tools", default="",
                    help="what the session has, comma-separated: browser, chrome, enable")
    iv = sub.add_parser("invitations", help="the sent-invitations page, read once: who already "
                                            "has a request pending")
    iv.add_argument("file", help="the page text, or - for stdin")
    iv.add_argument("--record", action="store_true",
                    help="record each pending one as sent (state.py sent --outside)")
    iv.add_argument("--url", default="")
    iv.add_argument("--load-seconds", type=float, default=None)
    pp = sub.add_parser("people", help="an employer's People tab or a people search, read once")
    pp.add_argument("file", help="the page text, or - for stdin")
    pp.add_argument("--company", required=True)
    pp.add_argument("--url", default="")
    pp.add_argument("--load-seconds", type=float, default=None)
    sk = sub.add_parser("skip", help="a read ruled them out: close them with the reason, "
                                     "and remove their draft")
    sk.add_argument("contact_id")
    sk.add_argument("--reason", required=True)
    ba = sub.add_parser("batch", help="are the queued first notes too alike to send (exit 11)")
    ba.add_argument("ids", nargs="*", help="the notes to check; every queued note by default")
    sub.add_parser("extractor", help="the read-only snippet that returns a profile page as JSON")
    a = ap.parse_args(argv)

    if a.cmd == "extractor":
        print(EXTRACTOR)
        return EXIT["ok"]
    if a.cmd == "limits":
        for line in pace.report():
            print(line)
        n, what = reads_left()
        print(f"Now: {n} profile read(s) can still go today (the limit that binds: {what}). "
              f"The ledger: {pace.ledger_dir()}")
        return EXIT["ok"]
    if a.cmd == "friction":
        if a.kind:
            signal(a.kind, a.words)
            why = stopped()
            print(f"reading: kept ({a.kind})" + (f"; browser reads are stopped for today: {why}"
                                                if why else "; the next pause is doubled"))
            return EXIT["ok"]
        log = pace.friction()
        loads = [x["when"] for x in _loads()]
        n, why_ = pace.hourly_ceiling(datetime.date.today(), loads)
        print(f"friction: {len(log)} signal(s) on file; pages an hour allowed now: {n} ({why_})")
        for x in log[-12:]:
            print(f"  {x.get('at')}  {x.get('kind')}: {x.get('words') or ''}")
        return EXIT["ok"]
    if a.cmd == "next":
        return _cli_next(a)
    if a.cmd == "search-url":
        try:
            if a.learn:
                got = learn_search(a.learn, a.company, a.place)
                print(f"reading: kept the filters for {a.company}"
                      + (f" in {a.place}" if a.place else "") + f": {got}")
                return EXIT["ok"]
            print(search_url(a.company, a.place, a.keywords))
        except (LookupError, ValueError) as e:
            print(f"reading: {e}")
            return EXIT["error"]
        return EXIT["ok"]
    if a.cmd == "stop":
        reason = a.reason or a.reason_flag
        if not reason:
            raise SystemExit("reading: stop needs what LinkedIn showed, as `stop \"<words>\"` "
                             "or `stop --reason \"<words>\"`")
        print(f"reading: browser reads stopped for today ({os.path.relpath(stop(reason), person.state())})")
        return EXIT["ok"]
    if a.cmd == "gate":
        now = datetime.datetime.now()
        g = _wait_gate(a.timeout, profile=not a.page) if a.wait else gate_state(now, profile=not a.page)
        if g["kind"] != "go":
            print(_gate_line(g, datetime.datetime.now()))
            if g["kind"] in ("wait", "later") and not a.wait:
                print("  to wait it out, run in the background: python3 tools/network/reading.py "
                      "gate --wait (it exits when the next page may load)")
            return EXIT[g["kind"]]
        if not signed_in_today():
            print("go, after sign-in: open the page; if LinkedIn shows its sign-in page "
                  "instead, run `reading.py signin` (a wait, not a stop)")
        print(_go_line(a.mode))
        return EXIT["ok"]
    if a.cmd == "page":
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        kind, words = page_kind(text)
        print(kind + (f": {words}" if words else ""))
        return {"profile": EXIT["ok"], "signin": EXIT["signin"],
                "check": EXIT["check"]}.get(kind, EXIT["unknown"])
    if a.cmd == "signin":
        if a.done:
            mark_signed_in()
            print("reading: signed in; carry on with the first profile")
            return EXIT["ok"]
        if a.url:
            state_ = url_kind(a.url)
            if state_ == "signed-in":
                mark_signed_in()
            print(state_)
            return EXIT["ok"] if state_ == "signed-in" else EXIT["signin"]
        if signed_in_today():
            print("reading: already signed in today; a sign-in page now means LinkedIn signed "
                  "them out, which is a stop: `reading.py stop \"signed out mid-run\"`")
            return EXIT["ok"]
        print("LinkedIn is not signed in yet. This is a wait for the person, never a stop, and "
              "nothing is counted:")
        for i, step in enumerate(signin_steps(), 1):
            print(f"  {i}. {step}")
        return EXIT["signin"]
    if a.cmd == "route":
        r_ = route([t for t in a.tools.split(",") if t.strip()])
        print(f"route: {r_['route']} ({surface()})"
              + (f"\nbrowser: {r_['browser']}" if r_["browser"] else "")
              + f"\nusable now: {'yes' if r_['usable'] else 'no'}\ndo: {r_['do']}")
        if r_["signin"]:
            print("first: `reading.py signin` when the first profile shows LinkedIn's sign-in page")
        if r_["say"]:
            print(f"tell them, once: {r_['say']}")
        return EXIT["ok"]
    if a.cmd == "shortlist":
        if not a.ids and not a.remove:
            got = shortlist([])
        else:
            got = shortlist(a.ids, remove=a.remove)
        print(f"reading: today's short list, {len(got['ids'])} of at most {got['cap']} "
              f"({got['why']}): " + (", ".join(got["ids"]) or "nobody yet"))
        for i, why_ in got["pruned"].items():
            print(f"  taken off: {i}, {why_}")
        if got["removed"]:
            print(f"  removed: {', '.join(got['removed'])}")
        if got["full"]:
            print(f"  not added, the day's list is full: {', '.join(got['full'])}. They wait for "
                  "tomorrow's, or take someone off with --remove <id>")
        if got["unplaced"]:
            print(f"  not added, nothing places them in a city yet: {', '.join(got['unplaced'])}. "
                  f"At most {UNVERIFIED_ON_SHORTLIST} such a day; a one-page read (`reading.py "
                  "people`) or a public finding places them first")
        return EXIT["ok"]
    if a.cmd == "queue":
        import state
        import why
        waiting = [c for c in why.ranked(queue(state.load_contacts()))]
        top = waiting[:max(0, a.top)]
        if a.urls:
            # The fast path, with no automation at all: the person opens each address, selects
            # all and copies, and sends them back in one paste with a line of --- between.
            for c in top:
                print(c.get("linkedin_url") or f"(no address on file) {c.get('name')} "
                      f"({c.get('company')}) [{c['contact_id']}]")
            print(f"then: paste the {len(top)} page(s) back in one message, a line of --- "
                  "between them, into `python3 tools/network/reading.py paste -`")
            return EXIT["ok"]
        left = ""
        if PROFILE_READS == "browser":
            n, what = reads_left()
            left = f", {n} profile read(s) can still go today (the limit that binds: {what})"
        print(f"{len(waiting)} draft(s) waiting with no fresh reading; profile reads: {PROFILE_READS}"
              + left)
        if waiting:
            print(f"offer a paste for these {len(top)} only, the best by why-them, several in "
                  "one message with a line of --- between them (`reading.py paste`); the rest "
                  "keep the line at the top of their draft saying each waits on a read:")
        for i, c in enumerate(top, 1):         # numbered, so a reply can say "1 and 3"
            print(f"  {i}. {c.get('name')} ({c.get('company')}) {c.get('linkedin_url') or ''}"
                  f"  [{c['contact_id']}]")
        return EXIT["ok"]
    if a.cmd == "paste":
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        return _paste(text, a.source)
    if a.cmd == "draft":
        note = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
        if not note.strip():
            raise SystemExit("reading: draft needs the note's text")
        import state
        row = next((c for c in state.load_contacts() if c.get("contact_id") == a.contact_id), {})
        p = write_draft(a.contact_id, note, row.get("name", ""))
        print(f"reading: saved {os.path.relpath(p, person.state())}"
              + ("" if has_read(load(a.contact_id)) else
                 f"; nothing read about {row.get('name') or a.contact_id} yet, so it opens "
                 f"on {WAITS_ON_A_READ} and reading.py queue lists it"))
        return EXIT["ok"]
    if a.cmd == "batch":
        import state
        notes = queued_notes(state.load_contacts())
        if a.ids:
            notes = {k: v for k, v in notes.items() if k in a.ids}
        found = alike(notes)
        print(f"batch: {len(notes)} queued note(s) checked")
        for what, sent_, ids in found:
            print(f"  {what}: \"{_clip(sent_, 110)}\" in {len(ids)}: {', '.join(ids[:8])}"
                  + (" ..." if len(ids) > 8 else ""))
        if found:
            print("  too alike to send as a batch: rewrite each from its own reading (the "
                  "background line chosen per person where the profile says so), and the ask "
                  "from ASK in profile/networking.py")
            return EXIT["alike"]
        print("  no sentence repeats past the limit, and every ask is the person's own")
        return EXIT["ok"]
    if a.cmd == "verdict":
        found = load(a.contact_id)
        if not found:
            print(f"reading: nothing read about {a.contact_id} yet")
            return EXIT["not_read"]
        keep, why = verdict(found, a.company or found.get("company", ""))
        if not keep:
            print(f"SKIP: {why}")
            print(_skip_hint(a.contact_id, why))
            return EXIT["skip"]
        if not _page_read(found):
            # Public findings, or a one-page read, rule nothing out; that is not a KEEP.
            # A read refused for its pace then printed KEEP for someone a request had
            # already gone to.
            print(f"NOT READ YET: nothing on file rules {a.contact_id} out, and their own "
                  "profile has not been read (a browser read, a paste or a PDF)")
            return EXIT["not_read"]
        print("KEEP" + (f" ({why})" if why else ""))
        return EXIT["ok"]
    if a.cmd == "invitations":
        return _cli_invitations(a)
    if a.cmd == "people":
        return _cli_people(a)
    if a.cmd == "skip":
        import state
        contacts = state.load_contacts()
        got = load(a.contact_id) or {}
        if "pending" in a.reason.lower():
            print(f"reading: a request to {a.contact_id} is already pending, so it went: "
                  f"python3 tools/network/state.py sent {a.contact_id} --outside")
            return EXIT["error"]
        row = ({"name": got.get("name", ""), "company": got.get("company", ""),
                "location": got.get("location", ""), "title": got.get("headline", "")}
               if got.get("name") else None)
        try:
            c = state.close(contacts, a.contact_id, datetime.date.today(), a.reason, row=row)
        except ValueError as e:
            raise SystemExit(f"reading: {e}") from None
        state.save_contacts(contacts)
        print(f"reading: {c.get('name') or a.contact_id} closed ({a.reason}); never surfaced "
              "again, and their draft removed")
        return EXIT["ok"]
    old = load(a.contact_id)
    if a.cmd == "show":                 # a reading stands on its own: no contact row needed
        if not old:
            print(f"reading: nothing read about {a.contact_id} yet")
            return EXIT["error"]
        _show(old)
        return EXIT["ok"]
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
            now = datetime.datetime.now()
            g = gate_state(now)
            if g["kind"] != "go":
                print(f"reading: not read. {_gate_line(g, now)}")
                return EXIT[g["kind"]]
        if source == "pdf":
            text = pdf_text(a.file)
        elif a.file == "-":
            text = sys.stdin.read()
        else:
            with open(a.file, encoding="utf-8") as fh:
                text = fh.read()
        if a.json:
            try:
                text = from_extract(text)
            except (ValueError, AttributeError, TypeError) as e:
                raise SystemExit(f"reading: --json needs the extractor's output ({e})") from None
        if source == "browser":
            kind, words = page_kind(text)
            if kind == "check":
                stop(f"LinkedIn showed a check: {words}")
                print(f"reading: LinkedIn showed a check ({words}). Browser reads are stopped "
                      "for today; tell the person what it showed, and never try to get past it")
                return EXIT["check"]
            if kind == "signin" and signed_in_today():
                stop("LinkedIn's sign-in page after they had signed in today")
                print("reading: LinkedIn signed them out mid-run. Browser reads are stopped for "
                      "today; tell the person, and carry on tomorrow")
                return EXIT["check"]
            if kind == "signin":
                print("reading: LinkedIn's sign-in page, not a profile. Not a read, not counted, "
                      "nothing stopped: run `reading.py signin` and wait for the person")
                return EXIT["signin"]
            if kind == "unknown" and len(" ".join(_clean_lines(text))) < NOT_RENDERED_CHARS:
                # A page that stopped rendering is a soft signal: the next pause doubles, and
                # a second within the hour ends the day's reads.
                signal("not_rendering", "a page of %d characters, not a profile"
                       % len(" ".join(_clean_lines(text))))
                why_ = stopped()
                print("reading: the page did not render (nearly empty). Not a read; "
                      + (f"browser reads are stopped for today: {why_}" if why_ else
                         "the next pause is doubled. If it happens again, the day stops"))
                return EXIT["check"] if why_ else EXIT["unknown"]
        if source == "browser" and not on_shortlist(a.contact_id):
            raise SystemExit(f"reading: {a.contact_id} is not on today's short list. A browser "
                             f"read is for the day's best {READS_PER_RUN} only: rank everyone "
                             "found, then `reading.py shortlist <ids, best first>`")
        try:
            new = parse(text, name=contact.get("name", ""), company=contact.get("company", ""),
                        source=source,
                        url=a.url or contact.get("linkedin_url", ""))
        except ValueError as e:
            raise SystemExit(f"reading: {e}") from None
        slow_ = ""
        if source == "browser":
            gap, brk = pause()
            at = datetime.datetime.now().isoformat(timespec="seconds")
            new["sources"][0]["at"] = at
            new["sources"][0]["next_gap"] = gap
            new["sources"][0]["break"] = brk
            new["sources"][0]["mode"] = a.mode
            if a.load_seconds is not None:
                new["sources"][0]["load_seconds"] = a.load_seconds
            mark_signed_in()            # a profile in the pane means they are signed in
            slow_ = note_load("profile", at, gap, brk, a.contact_id, a.load_seconds)
        reading = merge(old, new)
    print(f"reading: saved {os.path.relpath(save(a.contact_id, reading), person.state())}")
    _show(reading)
    if a.cmd == "read":
        keep, why = verdict(reading, contact.get("company", ""))
        print(("verdict: KEEP" + (f" ({why})" if why else "")) if keep
              else f"verdict: SKIP: {why} (read the next person instead)")
        if not keep:
            print(_skip_hint(a.contact_id, why))
        if source == "browser":
            at = datetime.datetime.now() + datetime.timedelta(seconds=new["sources"][0]["next_gap"])
            print(f"pace: the next page at {at:%H:%M:%S} at the earliest "
                  f"({new['sources'][0]['next_gap']}s"
                  + (", the longer break" if new["sources"][0]["break"] else "")
                  + "); never two at once")
            if slow_:
                why_ = stopped()
                print("pace: that page loaded far slower than your recent ones, a soft signal: "
                      + (f"browser reads are stopped for today: {why_}" if why_ else
                         "the next pause is doubled"))
    return EXIT["ok"]


# A browser page with less text than this is one that did not render, not a profile.
NOT_RENDERED_CHARS = 300


def _go_line(mode: str = "deep") -> str:
    if mode == "card":
        return (f"go: open the page and spend {dwell(mode='card')}s on its top card and About, "
                "nothing scrolled and nothing clicked, then read its text once (`read ... "
                "--mode card`). A card decides most keep or skip; read deep only for those it "
                "cannot")
    return (f"go: spend {dwell()}s on the page, scrolling it to the end at reading pace "
            "(nothing clicked), then read its text once")


def _cli_next(a) -> int:
    """The next person on today's list, once a page may load. Run with --wait in the
    background: the session carries on with the drafts already read meanwhile, and shows
    each as its read completes, instead of polling a clock."""
    import state
    contacts = state.load_contacts()
    nxt = next_up(contacts=contacts)
    if nxt is None:
        today = datetime.date.today().isoformat()
        done = [i for i in _shortlist_file(datetime.date.today()) if _read_on(i, today)]
        print(f"done: nothing left to read on today's list ({len(done)} read today"
              + (f": {', '.join(done)}" if done else "") + "). Show each draft that is not "
              "shown yet, then tell the person the run is done (a notification where the "
              "session has one)")
        return EXIT["done"]
    g = _wait_gate(a.timeout) if a.wait else gate_state()
    if g["kind"] != "go":
        print(_gate_line(g, datetime.datetime.now()))
        return EXIT[g["kind"]]
    url = nxt.get("linkedin_url") or ""
    print(f"next: {nxt.get('name') or nxt['contact_id']} ({nxt.get('company') or '?'}) "
          f"[{nxt['contact_id']}] {url or '(no address on file: find their page first)'}")
    print(_go_line(a.mode))
    print(f"then: python3 tools/network/reading.py read {nxt['contact_id']} - --source browser "
          f"--mode {a.mode}, show the person the draft it allows, and run `reading.py next "
          "--wait` in the background again")
    return EXIT["ok"]


# A people search narrowed to one employer (and a place). LinkedIn documents its Current
# company and Connections filters (help pages a528043 and a566261, read through a web
# search) but not the address they make, so the shape is never guessed: it is learned from
# a search the person filtered by hand in their own browser, kept per employer and place,
# and reused with the keywords changed. A plain keyword search with the employer's name in
# it is not that filter: for two large employers it returned almost nobody who works there,
# and for two others it worked only because their people name the employer in their
# headline. An employer's People tab dropped a keywords parameter on load (the address
# reset to the plain tab, with no place on its cards), so it is not used to filter.
SEARCH_FILE = ("documents", "network", ".search_filters.json")
SEARCH_BASE = "https://www.linkedin.com/search/results/people/"
_FILTERS = ("currentCompany", "geoUrn")


def _filters() -> dict:
    return _json(person.state(*SEARCH_FILE))


def learn_search(address: str, company: str, place: str = "") -> dict:
    """Keep the filters of a people search the person narrowed by hand: the employer's
    (and the place's) values as the address carries them, and the rest of its shape."""
    from urllib.parse import parse_qs, urlsplit
    from company_key import key as company_key
    u = urlsplit(str(address or ""))
    if "linkedin.com" not in u.netloc or not u.path.startswith("/search/results/people"):
        raise ValueError("that is not a LinkedIn people-search address: narrow a people search "
                         "to the employer in your own browser (python3 tools/claude_surfaces.py "
                         "steps linkedin-people-at-employer), then copy its address")
    q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
    if "currentCompany" not in q:
        raise ValueError("that search is not narrowed to an employer yet: narrow it (python3 "
                         "tools/claude_surfaces.py steps linkedin-people-at-employer), then copy "
                         "the address again")
    data = _filters()
    emp = data.setdefault("employers", {}).setdefault(company_key(company), {})
    emp.update(name=company, currentCompany=q["currentCompany"])
    shape = {k: v for k, v in q.items() if k not in _FILTERS + ("keywords", "page")}
    data["shape"] = shape
    if place and q.get("geoUrn"):
        data.setdefault("places", {})[" ".join(place.lower().split())] = q["geoUrn"]
    p = person.state(*SEARCH_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    return {"currentCompany": q["currentCompany"], "geoUrn": q.get("geoUrn", ""), **shape}


def search_url(company: str, place: str = "", keywords: str = "") -> str:
    """The address of a people search narrowed to this employer (and place), with these
    keywords, in the shape learned from the person's own filtered search."""
    from urllib.parse import urlencode
    from company_key import key as company_key
    data = _filters()
    emp = (data.get("employers") or {}).get(company_key(company))
    if not emp:
        raise LookupError(f"no filter on file for {company}: in your own browser, search for "
                          f"people narrowed to {company} (python3 tools/claude_surfaces.py steps "
                          "linkedin-people-at-employer)"
                          + (f" and the location to {place}" if place else "")
                          + ", copy the address, and keep it: python3 tools/network/reading.py "
                          f"search-url --company \"{company}\""
                          + (f" --place \"{place}\"" if place else "") + " --learn \"<address>\"")
    q = {"currentCompany": emp["currentCompany"]}
    if place:
        geo = (data.get("places") or {}).get(" ".join(place.lower().split()))
        if not geo:
            raise LookupError(f"no location filter on file for {place}: filter one search by it "
                              "by hand and keep its address with --learn")
        q["geoUrn"] = geo
    if keywords:
        q["keywords"] = keywords
    q.update(data.get("shape") or {})
    return SEARCH_BASE + "?" + urlencode(q)


def _cli_invitations(a) -> int:
    import state
    now = datetime.datetime.now()
    if PROFILE_READS == "browser":
        g = gate_state(now, profile=False)
        if g["kind"] != "go":
            print(f"reading: not read. {_gate_line(g, now)}")
            return EXIT[g["kind"]]
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    kind, words = page_kind(text)
    if kind == "check":
        stop(f"LinkedIn showed a check: {words}")
        print(f"reading: LinkedIn showed a check ({words}). Browser reads are stopped for today")
        return EXIT["check"]
    cards = invitations(text)
    total = invitations_total(text)
    rec = page_read("invitations", a.url, now, people=len(cards), load_seconds=a.load_seconds)
    contacts = state.load_contacts()
    threads = state.load_threads()
    got = match_invitations(cards, contacts, threads=threads, total=total)
    print(f"invitations: {len(cards)} request(s) pending on the page"
          + (f", {len(cards)} of {total} loaded" if total is not None and total > len(cards) else "")
          + f"; the next page at "
          f"{now + datetime.timedelta(seconds=rec['next_gap']):%H:%M:%S} at the earliest")
    done = 0
    for card, c in got["pending"]:
        line = (f"  sent outside the app: {c.get('name')} ({c.get('company')}), pending since "
                f"about {card['sent']} [{c['contact_id']}]")
        if a.record:
            try:
                state.sent(contacts, threads, c["contact_id"], datetime.date.today(),
                           date=card["sent"], outside=True, text=card.get("note", ""),
                           preview=bool(card.get("note_cut")))
                done += 1
                line += ": recorded as sent, draft removed"
            except ValueError as e:
                line += f": not recorded ({e})"
        print(line)
    if done:
        state.save_threads(threads)
        state.save_contacts(contacts)
    if got["pending"] and not a.record:
        print("next: record them, so the queue stops saying send: python3 "
              "tools/network/reading.py invitations <the same file> --record")
    for c in got["gone"]:
        print(f"  no longer pending: {c.get('name')} ({c.get('company')}) [{c['contact_id']}]: "
              "accepted, or withdrawn on LinkedIn; their profile or the person says which")
    if got["unchecked"]:
        # Ten loaded of 425 had every other request reported as gone (2026-10-19).
        shown = got["unchecked"][:5]
        loaded = f"{len(cards)} of {total}" if total is not None else f"the {len(cards)} loaded"
        print(f"  not checked: {len(got['unchecked'])} request(s) the log has as waiting went "
              f"on or before the oldest one loaded ({got['oldest'] or 'none loaded'}); only "
              f"{loaded} are on the page, newest first, so whether theirs is still pending is "
              "not known: "
              + ", ".join(f"{c.get('name')} [{c['contact_id']}]" for c in shown)
              + (" ..." if len(got["unchecked"]) > len(shown) else ""))
    if got["unknown"]:
        print(f"  {len(got['unknown'])} other pending request(s) to people not in the contact book")
    return EXIT["ok"]


def _cli_people(a) -> int:
    import state
    now = datetime.datetime.now()
    if PROFILE_READS == "browser":
        g = gate_state(now, profile=False)
        if g["kind"] != "go":
            print(f"reading: not read. {_gate_line(g, now)}")
            return EXIT[g["kind"]]
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    kind, words = page_kind(text)
    if kind == "check":
        stop(f"LinkedIn showed a check: {words}")
        print(f"reading: LinkedIn showed a check ({words}). Browser reads are stopped for today")
        return EXIT["check"]
    people = people_page(text, a.company)
    rec = page_read("people", a.url, now, people=len(people), load_seconds=a.load_seconds)
    contacts = state.load_contacts()
    # Counted apart: every card was counted as at the employer, people elsewhere too.
    count = {w: sum(1 for p in people if p.get("where") == w) for w in ("at", "elsewhere", "unknown")}
    print(f"people: {len(people)} on the page: {count['at']} at {a.company}, "
          f"{count['elsewhere']} elsewhere, {count['unknown']} where the card does not say; "
          f"the next page at "
          f"{now + datetime.timedelta(seconds=rec['next_gap']):%H:%M:%S} at the earliest")
    for p in people:
        keep, why = screen(p, a.company)
        row = state.already_contacted(contacts, name=p["name"], company=a.company,
                                      linkedin_url=p.get("linkedin_url"))
        tag = f"[{row['contact_id']}]" if row else "[not in the book]"
        waiting = bool(row) and (row.get("status") or "not_contacted") in ("not_contacted", "dropped")
        if waiting:
            from_list(row["contact_id"], p, a.company, a.url)
        print(f"  {'deep read' if keep else 'out'}: {p['name']}, {p.get('title') or '?'}"
              f"{', ' + p['location'] if p.get('location') else ''}"
              f"{' (' + p['degree'] + ')' if p.get('degree') else ''} {tag}"
              + (f": {why}" if why else ""))
        if waiting and not keep:
            print("    " + _skip_hint(row["contact_id"], why))
    print("next: shortlist only the few you will write to today, best first (`reading.py "
          "shortlist`); the rest are drafted from what the page showed and marked as waiting "
          "on a read")
    return EXIT["ok"]


if __name__ == "__main__":
    sys.exit(main())
