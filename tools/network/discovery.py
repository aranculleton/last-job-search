#!/usr/bin/env python3
"""People search: build the queries, then throw most of the results away.

Discovery is two jobs pulling in opposite directions. The query has to be wide
enough that one call returns ten usable profiles, and the filter has to be
narrow enough that what survives is worth a connection request. The brief is
blunt about which one matters: twenty mediocre names is a failure, and every
message spends a scarce slot and a piece of the sender's reputation.

What lives here, in the order a run uses it:

  queries_for           the one search pattern that works (brief 3.1), capped
                        at two queries per company (brief 3.6)
  disqualify            the free filters that save a slot: revenue roles wearing
                        technical titles, staffing spam, and people who have
                        already left the company the search matched them to
  is_stale              the six-month recency bar
  name_collision_check  one name, two employers (the profile's NAME_COLLISIONS)
  classify_tier         1 live hiring intent, 2 hiring authority, 3 senior IC,
                        4 adjacent (brief 3.3)
  triage                all of the above over a list of people, plus the
                        explicit "no relevant presence in this city" verdict
                        the brief asks to be recorded so the company is not
                        re-targeted next month

Everything here is pure logic over data passed in. The searches themselves and
any model judgment happen in the skill layer, so both halves stay testable
without a network.

Person dicts are loose by design because they are assembled from search
snippets rather than a schema: name, title (or headline), company, location,
snippet, linkedin_url, and a date under one of DATE_FIELDS. `triage` returns
copies carrying `tier` and `signal`, which are CONTACT_COLUMNS names in
`tools/network/schema.py`, so a kept person can be written straight into
network_contacts.csv without a translation step.

Usage:
    python3 tools/network/discovery.py "<Company>" "<City>"
"""

from __future__ import annotations

import calendar
import datetime as dt
import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import person as _person  # noqa: E402
from company_key import key as company_key  # noqa: E402

# `person` is the loop variable for a search result throughout this module, so
# the profile loader goes by another name.
_NET = _person.module("networking") if _person.exists("networking.py") else None


def _NET_GET(name, default):
    return getattr(_NET, name, default)


# The city a search targets when none is named: networking.py's HOME_CITY.
HOME_CITY = _NET_GET("HOME_CITY", "")

# ---------------------------------------------------------------------------
# 3.1 / 3.6  Query construction
# ---------------------------------------------------------------------------

# Who actually replies: a running tally of replies against messages sent, per
# segment, as (replied, sent), kept in the person's networking.py as
# REPLY_EVIDENCE. It starts empty; record your own counts as the contact book
# grows. A small sample ranks targets, it does not gate them.
#
# The shape that tends to reply is a HANDS-ON title at a company where data is
# the product or the core function ("Head of Data", "Lead Data Engineer"), not
# an administrator of a data function inside a large institution: those titles
# name the work, not the org.
#
# Nothing says an executive at a large institution will not reply. Do not read
# the silence of a fresh send as evidence.
REPLY_EVIDENCE = getattr(_NET, "REPLY_EVIDENCE", None) or {
    "alumni": (0, 0),
    "founder_small": (0, 0),
    "practitioner_lead": (0, 0),
    "recruiter": (0, 0),
    "institution_exec": (0, 0),
}

# Titles that name the work. Ranked above titles that name the org. Ordering
# only, and the person's: a data team's "Lead Data Scientist" is a nursing
# team's "Clinical Nurse Lead". networking.py HANDS_ON_TITLE; unset, nobody is
# ranked up for it.
_NEVER = re.compile(r"(?!x)x")
HANDS_ON_TITLE = _NET_GET("HANDS_ON_TITLE", None) or _NEVER

# Titles that name the org rather than the work. Still worth contacting; they
# just sort below the ones above when a run has more names than slots.
ADMIN_TITLE = re.compile(
    r"\b(?:chief\b[\w&,\s]{0,30}?\bofficer|cdao|vice\s+president|vp\b|managing\s+director"
    r"|associate\s+partner|head\s+of\s+(?:enterprise|strategy|governance))", re.I)


def reply_rank(contact):
    """Sort key for a discovery run's output, best odds first.

    Ordering only. A low rank is never a reason to drop someone: the whole
    point of clearing do_not_target was that a weak prior is not evidence.
    """
    route = (contact.get("route") or "").lower()
    title = contact.get("title") or ""
    if route.startswith("alumni") or route == "referral":
        return (0, "alumni or referral, the route that replies most often")
    if HANDS_ON_TITLE.search(title):
        return (1, "hands-on title, names the work rather than the org")
    if re.search(r"\b(?:founder|co-?founder|ceo)\b", title, re.I):
        return (2, "founder at a small company")
    if re.search(r"\b(?:recruit\w*|talent)\b", title, re.I):
        return (3, "recruiter")
    if ADMIN_TITLE.search(title):
        return (5, "administers a data function, unmeasured, ranks last")
    return (4, "no signal either way")


# Rosters beat title queries.
#
# A title query returns executives. Public search indexes press releases,
# leadership pages, awards and conference programmes, and a Chief Data Officer
# is in all four while a Senior Manager in pricing analytics is in none.
# Usable mid-level names come from a speaker roster and almost none from a
# title query, which returns CDAOs, chief AI scientists and global chief data
# officers instead.
#
# Two rules that are not obvious:
#   1. Ask a roster for EVERY speaker, not for the relevant ones. The same page
#      asked to "list every speaker with title and company" returns dozens of
#      usable names; asked for "data leaders at banks" it returns a handful of
#      executives, because the filtering happens before the caller sees it.
#   2. Verify every roster name against a second source before sending. A share
#      of roster-sourced contacts will have left the named employer or will not
#      resolve to a findable profile at all.
#
# Which rosters is the market's, so the list is the profile's: networking.py,
# ROSTERS, as (key, url, note) in the order to read them.
ROSTERS = tuple(getattr(_NET, "ROSTERS", ()))

# Asked of a roster page. Deliberately unfiltered: see rule 1 above.
ROSTER_PROMPT = ("List EVERY speaker with full name, exact job title and company. "
                 "Complete roster, all of them, including manager, senior manager, "
                 "lead, staff and director level people, not only executives.")

# An org chart, for names below the executive line at one named employer.
ORG_CHART = "https://theorg.com/org/%s/org-chart"


def roster_first(company=None):
    """The order a discovery run should work in, cheapest and highest-yield first.

    `company` is optional; when given, the org chart for that employer is
    appended, since it is the one source that is per-company rather than
    per-event.
    """
    out = [(name, url, why) for name, url, why in ROSTERS]
    if company:
        slug = str(company).strip().lower().replace(" ", "-")
        out.append(("theorg:%s" % slug, ORG_CHART % slug,
                    "Org chart for %s. Names below the executive line." % company))
    return out


# The site: operator is the whole trick. Brief 3.2 lists what happens without
# it: company-name searches return job listings and recruitment spam, careers
# pages return JavaScript chrome, and an individual profile URL is login-walled.
# Brief 3.1 prescribes the bare `site:linkedin.com/in` operator. Measured
# against this toolchain, that returns job-board aggregator pages and almost
# no people. The same intent expressed as a quoted phrase, with the caller
# restricting to the LinkedIn domains, returns usable profiles.
#
# So the operator is the phrase, and the domain restriction moves to the
# caller. SEARCH_DOMAINS is what /network passes as WebSearch allowed_domains;
# without it this pattern drifts back toward job boards. A market whose profiles
# live on a country subdomain adds it in the person's networking.py.
SITE = '"linkedin.com/in"'
SEARCH_DOMAINS = list(getattr(_NET, "SEARCH_DOMAINS", None) or ["linkedin.com"])

# Aggregator paths that mean the result is a job listing, not a person. Brief
# 3.4 says harvesting company names off these pages is free discovery, so they
# are worth recognising rather than merely discarding.
JOB_BOARD_PATHS = ("/jobs/", "/jobs-", "glassdoor.", "ziprecruiter.", "indeed.",
                   "builtin.com", "jobright", "simplyhired")


def is_person_url(url):
    """True when a search result is a profile rather than a listing.

    The phrase-based query is looser than the site: operator it replaces, so
    the caller has to sort the results. A LinkedIn URL carrying /jobs/ is a
    posting no matter what the title says.
    """
    u = (url or "").lower()
    if "/in/" not in u:
        return False
    return not any(p in u for p in JOB_BOARD_PATHS)


# A LinkedIn post permalink looks like
#   linkedin.com/posts/<handle>_<slugified-title>-activity-<id>-<hash>
# and carries two things nothing else in a result set does: the author's own
# profile handle, and an exact post date. The date matters because the whole
# staleness check runs on dates that snippets usually do not give, and a
# hiring post from 2023 reads identically to one from last week.
_POST_URL = re.compile(
    r"linkedin\.com/posts/(?P<handle>[^/_?#]+)[^/?#]*?"
    r"activity-(?P<activity>\d{15,25})", re.I)

# LinkedIn activity IDs are Snowflake-style: the high bits are milliseconds
# since the Unix epoch, so the timestamp comes out of the URL with no call.
# Checked against real posts: the decoded date matched the date each post's
# page showed.
_ACTIVITY_EPOCH_SHIFT = 22


def post_date(url):
    """The date a LinkedIn post was published, read out of its activity ID."""
    m = _POST_URL.search(url or "")
    if not m:
        return None
    try:
        ms = int(m.group("activity")) >> _ACTIVITY_EPOCH_SHIFT
    except ValueError:
        return None
    if not 946_684_800_000 < ms < 4_102_444_800_000:   # 2000-01-01 .. 2100-01-01
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date()


def resolve_result(url):
    """Turn one search result into (profile_url, post_date) or None.

    A discovery search returns three kinds of URL mixed together: profiles,
    post permalinks, and job listings. Dropping everything that is not a
    profile, which is what is_person_url() alone does, throws away the post
    permalinks, and those are where the tier-1 hiring signals live. A company
    run can return as many such posts as usable profiles.

    Returns None for a listing, so the caller can filter on it directly.
    """
    if is_person_url(url):
        return {"profile_url": url, "post_date": None, "kind": "profile"}
    m = _POST_URL.search(url or "")
    if not m:
        return None
    handle = m.group("handle")
    return {"profile_url": "https://www.linkedin.com/in/%s" % handle,
            "post_date": post_date(url),
            "kind": "post"}

# Brief 3.6: one search per company is usually enough, two if the first returns
# nothing usable, never more than three. Two is what this returns; HARD_MAX is
# the ceiling the brief sets and exists so a future caller that assembles its
# own title groups still cannot blow the budget.
MAX_QUERIES = 2
HARD_MAX_QUERIES = 3

# Four ORed titles is about where a query stops helping: past that the engine
# starts truncating and the ranking dilutes across titles nobody wanted. Extra
# titles are dropped rather than spilled into a third query, because the call
# budget is the scarcer resource.
MAX_TITLES_PER_QUERY = 4

# Title sets for the person's function, split the way brief 3.3 splits the
# tiers: hiring authority (tier 2) and senior IC (tier 3). `function` is
# deliberately junior-blind: in the alumni modes the hook is the shared
# employer, not the seniority, and an alumnus two rungs down still answers and
# still knows who is hiring. `recruiting` is for hiring_team, where the posting
# proves there is an open req and the recruiter is the named route.
#
# The titles are the person's (networking.py TITLE_SETS). They were a data
# team's, written here, so a discovery run for anybody else searched for data
# scientists at every employer. A profile without them cannot run a search:
# queries_for() says so rather than searching for someone else's colleagues.
TITLE_SETS = dict(_NET_GET("TITLE_SETS", None) or {})
TITLE_GROUPS = ("hiring_authority", "senior_ic", "function", "recruiting")


class NoTitles(RuntimeError):
    """The profile names no TITLE_SETS, so there is nothing to search for."""


# Mode names match the `route` vocabulary in schema.py, so the mode that found
# someone is the route recorded against them with no mapping table in between.
MODE_TITLE_GROUPS = {
    "cold": ("hiring_authority", "senior_ic"),
    # Brief 3.4: alumni of a past employer now in the target city answered at
    # roughly 60-70% against 10-25% for cold, so this mode searches the past
    # employer and the target city and never names a target company. Naming one
    # would collapse it back into a cold search with extra words.
    "alumni_employer": ("function", "hiring_authority"),
    "alumni_school": ("function", "hiring_authority"),
    "hiring_team": ("hiring_authority", "recruiting"),
}
MODES = tuple(MODE_TITLE_GROUPS)

# In the alumni modes the anchor is a history term, so it is always quoted:
# unquoted, "<Name> Money" matches every profile with the word money in it.
QUOTED_ANCHOR_MODES = ("alumni_employer", "alumni_school")


def _clean(term: str | None) -> str:
    return re.sub(r"\s+", " ", (term or "").strip())


def _quote_title(term: str) -> str:
    """Titles are always quoted. Unquoted, "head of data" matches any profile
    holding the three words anywhere, which is most of them."""
    return '"%s"' % _clean(term)


def _quote_term(term: str) -> str:
    """Company and location: quoted only when multi-word, matching brief 3.1's
    worked example, which leaves a one-word company bare."""
    t = _clean(term)
    if not t:
        return ""
    return '"%s"' % t if " " in t else t


def _title_groups(titles, mode):
    """Two groups of titles, one per query.

    Caller-supplied titles win and are chunked in the order given, so a skill
    that knows a company calls its managers something odd ("Analytics Chapter
    Lead") gets that searched first rather than buried behind the defaults.
    """
    if titles:
        seen, flat = set(), []
        for t in titles:
            t = _clean(t)
            if t and t.lower() not in seen:
                seen.add(t.lower())
                flat.append(t)
        return [flat[i:i + MAX_TITLES_PER_QUERY]
                for i in range(0, len(flat), MAX_TITLES_PER_QUERY)][:MAX_QUERIES]
    missing = [g for g in MODE_TITLE_GROUPS[mode] if not TITLE_SETS.get(g)]
    if missing:
        raise NoTitles(
            f"profile/networking.py TITLE_SETS has no {', '.join(missing)} titles: the "
            f"job titles of the people to find, in {TITLE_GROUPS}. /setup writes them.")
    return [TITLE_SETS[g][:MAX_TITLES_PER_QUERY] for g in MODE_TITLE_GROUPS[mode]]


def queries_for(company, titles=None, location=HOME_CITY, mode="cold"):
    """Build the people-search queries for one company, brief 3.1.

    In `cold` and `hiring_team`, `company` is the target employer. In the two
    alumni modes it is the shared history: the past employer or the school. The
    target company is absent from those queries on purpose (brief 3.4).

    Returns at most MAX_QUERIES strings, and never more than HARD_MAX_QUERIES
    whatever the caller passes.
    """
    if mode not in MODE_TITLE_GROUPS:
        raise ValueError("unknown mode %r; expected one of %s" % (mode, ", ".join(MODES)))
    anchor = _clean(company)
    if not anchor:
        raise ValueError(
            "queries_for needs a company; in the alumni modes that is the past "
            "employer or the school, not the target employer")

    groups = [g for g in _title_groups(titles, mode) if g]
    if not groups:
        raise ValueError("queries_for needs at least one title to search for")

    anchor_term = '"%s"' % anchor if mode in QUOTED_ANCHOR_MODES else _quote_term(anchor)
    place = _quote_term(location)

    out = []
    for i, group in enumerate(groups):
        parts = [SITE, " OR ".join(_quote_title(t) for t in group), anchor_term]
        if place:
            parts.append(place)
        # hiring_team runs against a company with a live posting, so the first
        # query leans on the word that separates a manager who is recruiting
        # right now from one who is not.
        if mode == "hiring_team" and i == 0:
            parts.append("hiring")
        q = " ".join(p for p in parts if p)
        if q not in out:
            out.append(q)
    return out[:min(MAX_QUERIES, HARD_MAX_QUERIES)]


# ---------------------------------------------------------------------------
# 3.3  Signal hierarchy
# ---------------------------------------------------------------------------

# Tier 1 is the only tier that needs evidence rather than a title, so the
# evidence is a quote. Anything outside this list is somebody's inference and
# must not be sold to the sender as a live hiring signal. The curly-quote
# and plural variants are here because LinkedIn snippets smart-quote
# apostrophes and post authors write "open roles" as often as "open role".
# "recruiting <role>" and "hiring for <role>" were missing at first, so an
# in-house recruiter whose line read "recruiting talented data scientists and
# data science managers" scored tier 4. That is the plainest hiring statement
# a result set can hold.
# The role nouns a hiring post names, as a regex fragment: networking.py
# HIRING_ROLE_NOUNS ("recruiting ... <noun>") and HIRING_HEADLINE_NOUNS
# ("Hiring <noun> at ..."), the second defaulting to the first. Unset, they are
# the person's own function titles, plural optional: a nurse's "hiring staff
# nurses" is a signal and a data team's "hiring data scientists" is not.
def _nouns_from_titles():
    titles = TITLE_SETS.get("function") or []
    return "|".join(re.escape(t.lower()) + "s?" for t in titles) or r"(?!x)x"


_ROLE_NOUNS = _NET_GET("HIRING_ROLE_NOUNS", None) or _nouns_from_titles()
_HEADLINE_NOUNS = _NET_GET("HIRING_HEADLINE_NOUNS", None) or _ROLE_NOUNS

HIRING_SIGNAL = re.compile(
    r"(we[’']?re hiring|we are hiring|i[’']?m looking for|i am looking for|"
    r"dm me|join my team|open roles?|we are seeking|we[’']?re seeking|"
    r"reach out if|"
    # "recruiting <anything> <role>". The gap is bounded and the role noun is
    # required, so "recruiting is hard for our teams right now" stays out while
    # "recruiting talented and passionate <role>s" comes in.
    r"recruiting\b[^.\n]{0,40}?\b(?:" + _ROLE_NOUNS + r")\b|"
    r"hiring (?:for|several|a|an|multiple)\b|now hiring|"
    # "<Company>'s team is hiring in <City>, <City> or remote" and
    # "Hiring Senior <role>s at <Company>" are two tier-1 shapes that
    # once read as no signal: the first says "is hiring in", the second opens
    # on a bare "Hiring" and a role.
    r"(?:is|are|team)\s+hiring\s+(?:in|for|across|now)\b|"
    r"^\s*hiring\s+(?:(?:senior|staff|lead|principal|junior)\s+)?(?:"
    + _HEADLINE_NOUNS + r")\b|"
    r"my team is growing|growing my team|we have an opening)", re.I | re.M)

# The quote is pasted into a message as evidence, so it has to be quotable.
SIGNAL_MAX_CHARS = 240

_SENT_END = re.compile(r"[.!?\n]")
_QUOTE_CHARS = '"“”'
# "Jane Smith posted:", "Wren Halloway shared:" - the attribution is not part of
# what the person said, and quoting it back at them reads as surveillance.
_ATTRIBUTION = re.compile(
    r"^(?:[A-Z][\w.'-]+\s+){0,4}(?:posted|shared|reposted|wrote|says?|commented)"
    r"[^:]{0,24}:\s*", re.I)


def _quoted_span(text, m):
    """The quoted post the match sits inside, if it sits inside one."""
    left = max(text.rfind(c, 0, m.start()) for c in _QUOTE_CHARS)
    if left < 0:
        return None
    rights = [i for i in (text.find(c, m.end()) for c in _QUOTE_CHARS) if i != -1]
    if not rights:
        return None
    return text[left + 1:min(rights)]


def _trim(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.strip(' \'"“”:;,-')
    s = _ATTRIBUTION.sub("", s).strip()
    if len(s) > SIGNAL_MAX_CHARS:
        cut = s.rfind(" ", 0, SIGNAL_MAX_CHARS)
        s = s[:cut if cut > 0 else SIGNAL_MAX_CHARS].rstrip()
    return s


def quote_signal(snippet):
    """The live hiring signal in a snippet, quoted, or None.

    Returns the quoted post where there is one and the containing sentence
    otherwise. A bare "we are hiring" with nothing around it is not evidence a
    person can be shown, so the surrounding words come with it.
    """
    text = _clean(snippet)
    if not text:
        return None
    m = HIRING_SIGNAL.search(text)
    if not m:
        return None
    # Inside a quoted post, quote the post rather than the snippet around it,
    # then narrow to the sentence that carries the signal: a three-sentence
    # post pasted into a connection note is the generic hook the brief warns
    # against, and the one sentence naming the roles is the whole hook.
    span = _quoted_span(text, m)
    if span:
        inner = HIRING_SIGNAL.search(span)
        if inner:
            text, m = span, inner
    start = 0
    for b in _SENT_END.finditer(text, 0, m.start()):
        start = b.end()
    end_m = _SENT_END.search(text, m.end())
    end = end_m.start() if end_m else len(text)
    return _trim(text[start:end]) or None


# Tier 2, brief 3.3. "Lead" is listed under both tier 2 and tier 3 in the
# brief; it is read as tier 3 here because in this function "Lead Data
# Scientist" is an IC far more often than it is a people manager, and the cost
# of reading a manager as an IC is a slightly under-pitched message, while the
# reverse writes to somebody about headcount they do not own.
AUTHORITY_TITLE = re.compile(
    r"\b(head of|director|dir\.|vp|vice president|svp|evp|chief|"
    r"manager|managing director)\b", re.I)

SENIOR_IC_TITLE = re.compile(r"\b(principal|staff|lead|senior|sr\.?)\b", re.I)

# Tier 2 is authority "on a team matching the user's function", so authority
# alone is not enough: a Director of Marketing is tier 4 to a data analyst and
# tier 2 to a marketer. networking.py FUNCTION_TITLE. Unset, every title is in
# function: a run ranks by authority and seniority alone, which over-includes.
# A data team's list as the default would write every employer off for a nurse
# as having "no relevant presence".
FUNCTION_TITLE = _NET_GET("FUNCTION_TITLE", None) or re.compile(r".", re.S)

# The home city's metro, as a person's location may name it: a search for the
# home city accepts anyone in one of these. networking.py's METRO.
METRO = tuple(getattr(_NET, "METRO", ()))
# A profile that names no city (the country, the region, "Remote") is not
# evidence of being somewhere else, so it passes rather than failing the market
# check. networking.py's BROAD_PLACES.
BROAD_PLACES = tuple(getattr(_NET, "BROAD_PLACES", ("remote",)))
# The home city's own token and the region words a broad place counts for.
_HOME = _NET_GET("HOME_CITY", "").lower()
_REGIONS = tuple(getattr(_NET, "REGION_WORDS", ()))
_GENERIC_PLACE_WORDS = {"greater", "area", "region", "metro", "city", "the"}


def _norm_place(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def _city_tokens(s):
    city = _norm_place((s or "").split(",")[0])
    return [t for t in city.split(" ") if t and t not in _GENERIC_PLACE_WORDS]


def _same_market(location, target_location):
    """Is this person in the market being hired into?

    Brief 3.5's finding is the defect this prevents: a company with no data
    science presence in the target country can return, for "<Company> <City>",
    leaders based elsewhere who would otherwise read as tier 2 and eat a slot.

    All city tokens must appear, not any of them, because "york" alone makes
    North York answer a search for New York.
    """
    loc = _norm_place(location)
    tokens = _city_tokens(target_location)
    if not tokens:
        return True
    if not loc:
        return False
    if all(t in loc for t in tokens):
        return True
    if _HOME and _HOME in tokens and any(g in loc for g in METRO):
        return True
    if loc in BROAD_PLACES:
        target = _norm_place(target_location)
        return (any(w in target for w in _REGIONS)
                or (bool(_HOME) and _HOME in tokens) or any(g in target for g in METRO))
    return False


def _signal_reaches_market(signal, target_location):
    """A hiring post counts as tier 1 only if the hiring is here.

    The brief's own example is why this reads the post and not just the
    poster: the lead is hiring for "<City>, <Other City> or remote" and may
    sit in any of them.
    """
    text = _norm_place(signal)
    if not text:
        return False
    if "remote" in text:
        return True
    tokens = _city_tokens(target_location)
    if tokens and all(t in text for t in tokens):
        return True
    return bool(_HOME) and _HOME in tokens and any(g in text for g in METRO)


# A place named inside the post. The preposition is required because a bare
# capitalized word in a post is a team or a product far more often than a city.
_SIGNAL_PLACE = re.compile(
    r"\b(?:based in|located in|hiring in|roles? in|opening in|in|out of|across)"
    r"\s+([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){0,2})")

# Captures that follow a preposition and are not markets. "Start in January"
# and "hiring in Data Science" would otherwise read as somewhere else and cost
# a real tier 1 its rank. A capture is ignored when any token is in here, which
# fails towards keeping tier 1 rather than taking it away on a guess.
_NON_PLACE_TOKENS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "data", "analytics", "analysis", "science", "engineering", "product",
    "marketing", "sales", "finance", "research", "platform", "team", "growth",
    "operations", "risk", "fraud", "payments", "infrastructure",
}


def _place_is_target(place, target_location):
    loc = _norm_place(place)
    # "Hiring across <country>" includes the home city, so a broad place is not
    # evidence the hiring is somewhere else.
    if loc in BROAD_PLACES:
        return True
    tokens = _city_tokens(target_location)
    if not tokens:
        return True
    if all(t in loc for t in tokens):
        return True
    return bool(_HOME) and _HOME in tokens and any(g in loc for g in METRO)


def _names_other_market(signal, target_location):
    """Does the post say the hiring is somewhere other than the target market?

    A post that names its market decides tier 1 on its own words. Without this,
    a manager based in the home city posting "we are hiring 3 data scientists in Austin"
    scored tier 1 on the poster's city, and the quote pasted into the message as
    evidence was about Austin. Demoting costs a rank; the signal is still
    returned, so nothing is hidden from the caller.
    """
    places = []
    for m in _SIGNAL_PLACE.finditer(signal or ""):
        tokens = _norm_place(m.group(1)).split(" ")
        if any(t in _NON_PLACE_TOKENS for t in tokens):
            continue
        places.append(m.group(1))
    if not places:
        return False
    return not any(_place_is_target(p, target_location) for p in places)


def classify_tier(snippet, title, location, target_location=HOME_CITY):
    """Score one person 1 to 4 (brief 3.3) and return the evidence with it.

    Returns (tier, quoted_signal_or_None). The signal is returned even when it
    did not earn tier 1, because a manager hiring in the wrong city is still
    something the caller may want to see before deciding.
    """
    title = _clean(title)
    signal = quote_signal(snippet)
    in_market = _same_market(location, target_location)

    # Two ways to earn tier 1: the post names this market, or the poster is in
    # it and the post does not name a different one.
    if signal and (_signal_reaches_market(signal, target_location)
                   or (in_market and not _names_other_market(signal, target_location))):
        return 1, signal

    if in_market and FUNCTION_TITLE.search(title):
        if AUTHORITY_TITLE.search(title):
            return 2, signal
        if SENIOR_IC_TITLE.search(title):
            return 3, signal
    return 4, signal


# ---------------------------------------------------------------------------
# 3.5  Disqualifiers
# ---------------------------------------------------------------------------

Rule = namedtuple("Rule", "name scope pattern reason")

DISQUALIFIERS = (
    # Brief 3.5: an entire search at a large software vendor can return nothing but these.
    # They are customer-facing revenue roles and they do not hire for technical
    # teams. Matched against the title only: a data manager whose snippet
    # mentions working with the solutions architects is not one of them.
    # The rule is deliberately blunt about "Solutions Architect, Data & AI",
    # which reads technical and is not.
    # The person's (networking.py NOT_HIRING_TITLES; None turns it off): for
    # somebody in sales these are exactly the people to reach.
    Rule("revenue_role", "title", _NET_GET("NOT_HIRING_TITLES", re.compile(
        r"\b(solutions? architect|field engineer(?:ing)?|"
        r"cloud (?:&|and) ai specialist|technical account manager|"
        r"client partner|head of industry|customer success|sales engineer|"
        r"partner manager|account executive|solutions? consultant|"
        r"pre-?sales|business development)\b", re.I)) or _NEVER,
        "revenue role dressed as technical, does not hire for technical teams"),

    Rule("spam_urgency", "text", re.compile(
        r"\b(immediate hiring|urgent(?:ly)? hiring|hiring urgently|"
        r"immediate joiners?|urgent requirement|hot requirement|"
        r"immediate interview)\b", re.I),
        "staffing spam, urgency language"),

    # Three emoji inside a short window is the shape of these posts. Counting
    # them in a regex keeps the whole table one thing: patterns with reasons.
    Rule("spam_emoji", "text", re.compile(
        r"(?:[\U0001F300-\U0001FAFF☀-➿⬀-⯿️][\s\S]{0,60}){3,}"),
        "staffing spam, emoji-heavy urgency post"),

    # A personal mailbox collecting resumes. The send-resume context is part of
    # the pattern because plenty of legitimate people list a Gmail address.
    Rule("spam_mailbox", "text", re.compile(
        r"(?:resumes?|cv|profiles?|apply|share|send|forward|dm)[\s\S]{0,60}"
        r"@(?:gmail|yahoo|hotmail|rediffmail|outlook)\.com"
        r"|@(?:gmail|yahoo|hotmail|rediffmail)\.com[\s\S]{0,60}"
        r"(?:resumes?|apply|immediate)", re.I),
        "staffing spam, personal mailbox collecting resumes"),

    # Bulk lists spanning unrelated disciplines. Three of these in one run of
    # text is a harvest, not a vacancy.
    Rule("spam_bulk_roles", "text", re.compile(
        r"(?:\b(?:java|\.net|dotnet|sap|qa tester|qa analyst|devops|salesforce|"
        r"nurse|rn|truck driver|mechanical engineer|civil engineer|"
        r"scrum master|network engineer|ios|android|php|sql developer|"
        r"help ?desk|technician|peoplesoft|workday)\b[^\n]{0,40}){3,}", re.I),
        "staffing spam, bulk role list spanning unrelated disciplines"),

    Rule("spam_contract_vehicle", "text", re.compile(
        r"\b(c2c|corp to corp|w2 only|w-2 only|no c2c|third party resumes?)\b", re.I),
        "staffing spam, contract-vehicle language"),

    # Reads the title, but the caller's company field decides: an in-house
    # recruiter at a named company is a legitimate route and hiring_team mode
    # goes looking for exactly them. A recruiter with no employer named is the
    # brief's resume harvester.
    Rule("recruiter_no_company", "person", re.compile(
        r"\b(recruiter|recruitment|staffing|talent acquisition|head ?hunter|"
        r"resourcing|talent sourcer)\b", re.I),
        "staffing spam, recruiter with no company named"),

    # Brief 3.5, people who have moved on. Leaving is unconditional: whatever
    # the search matched them to, it is already out of date.
    Rule("moved_on_leaving", "text", re.compile(
        r"\b(my last day|last day at|final day at|signing off from)\b", re.I),
        "has moved on, is leaving"),

    # A departure that names no destination is still a departure. A search can
    # return "Spent six years at <the employer>, left as a Senior Data
    # Scientist. Excited to share I have joined a new team", and moved_on_joined
    # does not fire because that rule requires a capitalised company after
    # "joined" so it can compare against the target. Nothing is named, and the
    # person would be kept as a live tier 3 at a company they no longer work
    # for. Past-tense exit language needs no destination to be disqualifying.
    Rule("moved_on_past_tense", "text", re.compile(
        r"\b(left (?:as|after|in)\b"
        r"|(?:i(?:['\u2019]|\s+ha)?ve\s+)?joined\s+a\s+new\s+(?:team|company|role|chapter)"
        r"|after\s+\d+\+?\s+(?:great\s+)?years?\s+at\b"
        r"|wrapped up my time at)\b", re.I),
        "has moved on, past-tense departure with no destination named"),

    # Joining is conditional. "Excited to share I've joined" is only a
    # disqualifier when the company joined is not the one being searched; when
    # it is, this is the freshest contact at that employer in the results.
    # The prefix is case-insensitive because it opens a post ("Excited to
    # share..."); the captured company name is not, because a capitalized token
    # is the only thing separating a company from the rest of the sentence.
    Rule("moved_on_joined", "text", re.compile(
        r"(?i:(?:excited|thrilled|happy|pleased) to share (?:that )?)"
        r"(?i:i(?:['’]|\s+ha)?ve joined)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})"
        r"|(?i:i(?:['’]ve| have) joined)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})"
        r"|(?i:starting a new (?:role|position|chapter) (?:at|with))\s+"
        r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})"),
        "has moved on, joined another company"),

    # "ex-" and "formerly at" only disqualify when the company named is the one
    # the search matched them to. Otherwise it is career history, and dropping
    # on it loses good people: half of a city's data leaders keep an ex-big-tech
    # name in the headline.
    Rule("moved_on_former", "text", re.compile(
        r"(?i:\b(?:formerly at|previously at|ex-))\s*"
        r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})"),
        "has moved on, left the company this search matched"),
)

def _haystack(person):
    return " ".join(str(person.get(f) or "") for f in
                    ("title", "headline", "snippet", "summary", "about", "activity"))


def _matched(m):
    """The first non-empty capture, or the whole match when nothing captured."""
    for g in m.groups():
        if g:
            return _clean(g)
    return _clean(m.group(0))


def disqualify(person, target_company=None):
    """Why this person should not be contacted, or None.

    `target_company` is the employer the search was run against. It defaults to
    whatever the person record carries, so a caller that never tracked it still
    gets the unconditional rules.
    """
    title = " ".join(str(person.get(f) or "") for f in ("title", "headline"))
    text = _haystack(person)
    target = target_company or person.get("target_company") or person.get("company") or ""
    target_k = company_key(target)

    for rule in DISQUALIFIERS:
        # Only the "text" scope reads the snippet. "person" scope patterns run
        # against the title as well, because scope "person" fell through to the
        # haystack and dropped a Head of Data Science whose post mentioned
        # working with the talent acquisition team, labelled as staffing spam.
        hay = text if rule.scope == "text" else title
        m = rule.pattern.search(hay)
        if not m:
            continue

        if rule.name == "recruiter_no_company":
            if not _clean(person.get("company")):
                return "%s: %s" % (rule.reason, _matched(m))
            continue

        if rule.name == "moved_on_joined":
            joined = company_key(_matched(m))
            if joined and target_k and joined == target_k:
                continue    # they joined the company being searched, which is the point
            return "%s: %s" % (rule.reason, _matched(m))

        if rule.name == "moved_on_former":
            left = company_key(_matched(m))
            if not left or not target_k or left != target_k:
                continue    # career history at some other employer, not a move away
            return "%s: %s" % (rule.reason, _matched(m))

        return "%s: %s" % (rule.reason, _matched(m))
    return None


# ---------------------------------------------------------------------------
# 3.5  Stale data
# ---------------------------------------------------------------------------

STALE_MONTHS = 6


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = _clean(value)
    if not s:
        return None
    s = s.split("T")[0]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%d %B %Y", "%B %Y", "%b %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _months_before(date, months):
    month = date.month - months
    year = date.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    # Clamp so 31 August minus six months is a real date in February.
    return dt.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


def is_stale(date_str, today, months=STALE_MONTHS):
    """Is this activity older than about six months (brief 3.5)?

    An unparseable or missing activity date is not stale. The brief wants
    recency weighted heavily, but a missing timestamp is a gap in the snippet
    rather than evidence the person has gone quiet, and dropping on it would
    throw away most search results, which carry no date at all.

    `today` is held to a stricter standard than the snippet date because it
    comes from the caller, not from a search result. It used to return False
    when it could not be read, which turned the whole recency filter off in
    silence: a profile last active in 2019 came back as a live tier 2.
    """
    t = _as_date(today)
    if t is None:
        raise ValueError(
            "is_stale needs a readable date for `today`, got %r; the recency "
            "filter is off rather than lenient without one" % (today,))
    d = _as_date(date_str)
    if d is None:
        return False
    return d < _months_before(t, months)


# Keyed by `company_key.key`, so an alias or a legal suffix on the way in still
# finds the note. Each note names what to verify: entity, industry, HQ,
# headcount. Getting this wrong is expensive in both directions, either a
# message about the wrong company or a good employer skipped as a duplicate.
# The names are the market's, so the table is the profile's: employers.py,
# NAME_COLLISIONS.
_EMP = _person.module("employers") if _person.exists("employers.py") else None
COLLISIONS = dict(getattr(_EMP, "NAME_COLLISIONS", {}))


def name_collision_check(company, known_collisions=None):
    """A note the caller must verify before including this company, or None."""
    table = COLLISIONS if known_collisions is None else known_collisions
    k = company_key(company)
    if not k:
        return None
    if k in table:
        return table[k]
    # A caller passing a hand-written table may key it by display name.
    for name, note in table.items():
        if company_key(name) == k:
            return note
    return None


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

# Where a person's activity date might be. Checked in order; the first present
# field wins.
# Two different questions wear the same shape here, and conflating them has a
# cost. SIGNAL_DATE_FIELDS date the hiring post; PRESENCE_DATE_FIELDS date the
# person's own last activity. An old hiring post means the opening is cold, not
# that the manager left: a manager can come back in the same run as a current
# Data Science Manager profile and as a hiring post from a year earlier, and
# treating the post date as their last activity deletes a live tier 2. So a
# stale signal strips the signal, and only a stale presence date drops the
# person.
SIGNAL_DATE_FIELDS = ("signal_date", "posted")
PRESENCE_DATE_FIELDS = ("activity_date", "last_activity", "date")
DATE_FIELDS = SIGNAL_DATE_FIELDS + PRESENCE_DATE_FIELDS

RELEVANT_TIERS = (1, 2, 3)


def _person_date(person, fields=DATE_FIELDS):
    for f in fields:
        d = _as_date(person.get(f))
        if d is not None:
            return d
    return None


def _adjacent_reason(person, target_location):
    """Why an adjacent person was dropped, in the terms that actually applied.

    Reporting "tier 4 adjacent" for a Senior Data Scientist sitting in another
    city reads as a seniority judgement and hides the real reason, which is the
    one the next run needs: the person is not in the target market. A run can
    drop somebody that way.
    """
    if not _same_market(person.get("location") or "", target_location):
        return "not in %s: %s" % (
            target_location, person.get("location") or "location unknown")
    return "tier 4 adjacent: better targets exist at this company"


def triage(people, target_location=HOME_CITY, today=None, target_company=None):
    """Run the whole discovery filter over one company's search results.

    Returns {'keep': [...], 'dropped': [(person, reason)], 'verdict': ...}.

    `target_company` is the employer the search ran against, and the moved-on
    rules need it: a search for one company's people returns profiles whose
    current employer is somewhere else, and "Senior Data Scientist at <Other>,
    ex-<Company>" is exactly the stale row the brief says to drop. Without it those rules fell
    back to the person's own company field, compared it against itself and kept
    everybody, so the only entry point a run uses never applied them.

    Kept people are copies carrying `tier` and `signal`, sorted by tier and
    then by recency inside a tier, so the first name in the list is the one to
    message first.

    Tier 4 is handled the way brief 3.3 asks: dropped when anything in tiers
    1 to 3 survived, kept when nothing did, because adjacent names are only
    worth reading when there is nothing better. The verdict tracks the relevant
    tiers alone, so a company that returned nothing but Location Scouts is
    recorded as no_relevant_presence even though those names came back.
    """
    today = today or dt.date.today()
    keep, adjacent, dropped = [], [], []

    for person in people or []:
        reason = disqualify(person, target_company)
        if reason:
            dropped.append((person, reason))
            continue

        # A company-targeted search returns near-misses: a result can be
        # another employer's Head of Data Science, whose title and city are a
        # perfect tier 2 and who is no use for a referral at the target. The
        # run asked "who at <Company>", so a result naming a different
        # current employer is out, and a blank employer field is not, because
        # most search results never return one.
        stated = person.get("company") or ""
        stated_k, target_k = company_key(stated), company_key(target_company or "")
        if stated_k and target_k and stated_k != target_k:
            dropped.append((person, "works at %s, not %s" % (stated, target_company)))
            continue

        presence = _person_date(person, PRESENCE_DATE_FIELDS)
        if is_stale(presence, today):
            dropped.append((person, "stale: last activity %s is over %d months old"
                            % (presence.isoformat(), STALE_MONTHS)))
            continue

        tier, signal = classify_tier(
            person.get("snippet"),
            person.get("title") or person.get("headline"),
            person.get("location"),
            target_location)

        # A hiring post from last year is not live hiring intent. Drop the
        # signal and re-tier on the title alone, rather than dropping someone
        # who is demonstrably still in the seat.
        signal_date = _person_date(person, SIGNAL_DATE_FIELDS)
        if signal and is_stale(signal_date, today):
            signal = None
            tier, _ = classify_tier(None,
                                    person.get("title") or person.get("headline"),
                                    person.get("location"),
                                    target_location)

        d = _person_date(person)
        enriched = dict(person)
        enriched["tier"] = tier
        enriched["signal"] = signal
        if signal and not enriched.get("signal_date") and d is not None:
            enriched["signal_date"] = d.isoformat()
        # Tier 4 is a flat bucket, but it is not a uniform one: a Data Engineer
        # at the target company and an Events Coordinator are both tier 4, and
        # when tier 4 becomes the fallback list the first name in it is the one
        # that gets messaged. Rank in-function, in-market people ahead of the
        # rest without inventing a tier the brief does not have.
        relevant = 0 if (_same_market(person.get("location") or "",
                                      target_location)
                         and FUNCTION_TITLE.search(
                             _clean(person.get("title")
                                    or person.get("headline")))) else 1
        (keep if tier in RELEVANT_TIERS else adjacent).append(
            (enriched, d, relevant))

    verdict = "has_presence" if keep else "no_relevant_presence"
    if not keep:
        keep = adjacent
    else:
        dropped.extend((row[0], _adjacent_reason(row[0], target_location))
                       for row in adjacent)

    # Sort is stable, so people with no date keep the order the search returned
    # them in rather than being shuffled to an arbitrary position.
    keep.sort(key=lambda row: (row[0]["tier"], row[2],
                               -(row[1].toordinal() if row[1] else 0)))
    return {"keep": [row[0] for row in keep], "dropped": dropped,
            "verdict": verdict}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: discovery.py "<Company>" ["<City>"] [mode]')
    company = sys.argv[1]
    place = sys.argv[2] if len(sys.argv) > 2 else HOME_CITY
    mode = sys.argv[3] if len(sys.argv) > 3 else "cold"
    note = name_collision_check(company)
    if note:
        print("collision: %s\n" % note)
    for q in queries_for(company, location=place, mode=mode):
        print(q)
    # The query alone is half the call. Without the domain constraint the same
    # search returns job boards, which is the whole reason the site: operator
    # was dropped, so the CLI prints both rather than the half that looks
    # complete on its own.
    print("\nallowed_domains=%r" % (SEARCH_DOMAINS,))
    print("Filter every result through resolve_result(); it drops listings and "
          "turns a post permalink into a profile url plus an exact date.")
