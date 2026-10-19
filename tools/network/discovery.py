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
import company_research  # noqa: E402
import dates  # noqa: E402
import person as _person  # noqa: E402
import company_key as _company_key  # noqa: E402
from company_key import fold as _ck_fold, key as company_key  # noqa: E402
import places as _places  # noqa: E402

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
    r"\b(?:chief\b[\w&,\s]{0,30}?\bofficer|cdao|vice\s+president|[asde]?vp\b|managing\s+director"
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
    import compose      # its RECRUITER_TITLE is the careful one: a manager "recruiting
    if compose.is_recruiter(title):   # data scientists" is not a recruiter
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
    # LinkedIn's own address only: "/in/" is also a language path on employers' sites
    # ("<employer>.com/in/en/leadership"), and its page was kept as a verified person.
    if "linkedin.com/in/" not in u:
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
    r"(?:activity|share|ugcPost)-(?P<activity>\d{15,25})", re.I)

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


def resolve_result(url, company=None):
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
    who = handle.replace("-", " ")
    # A company page's post carries the company's handle, not a person's, and
    # turning it into /in/<company> invented a profile that does not exist. Its
    # handle may be the employer under another of its names ("<employer>-group"), or
    # an institution's: a university's post about the employer was kept as a person.
    if (company and (_norm_place(who) in (_norm_place(company), company_key(company))
                     or same_employer(who, company))) or _INSTITUTION.search(who):
        return {"profile_url": None, "post_date": post_date(url), "kind": "company_post"}
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


# "Company" and a bare "Co" are left off a profile as often as a legal form,
# though only the search drops them: never after "&" or "and", where they are
# the name.
_COMPANY_TAIL = re.compile(r"[\s,.]+(?:company|co)\.?$", re.I)


def search_name(company):
    """The employer as people write it on their profiles.

    A shortlist carries the legal name, "Fernhill Freight Services Limited
    (UK)", and quoted whole that phrase is on almost no profile. The legal form
    and a bracketed qualifier come off (company_key.display_name, the list the
    salutation uses); the case and the rest of the name stay.
    """
    import company_key as _ck
    s = _ck.display_name(company)
    while True:
        cut = _COMPANY_TAIL.sub("", s).strip(" ,.")
        if cut == s or not cut or _ck.JOINED_END.search(cut):
            return s
        s = cut


def queries_for(company, titles=None, location=HOME_CITY, mode="cold"):
    """Build the people-search queries for one company, brief 3.1.

    In `cold` and `hiring_team`, `company` is the target employer. In the two
    alumni modes it is the shared history: the past employer or the school. The
    target company is absent from those queries on purpose (brief 3.4).

    One title per query, in plain words: "<employer> <title> <city>", run with
    allowed_domains=SEARCH_DOMAINS. Measured on 2026-10-18 over two employers in one
    city: the plain shape found 14 people named at the employer for the searches
    that found 5 in the older shape, which quoted a literal "linkedin.com/in" and
    ORed four quoted titles; the ORed titles alone brought back job listings, nine
    results in ten. The domain filter does what the literal did.

    Returns at most MAX_QUERIES strings, and never more than HARD_MAX_QUERIES
    whatever the caller passes.
    """
    if mode not in MODE_TITLE_GROUPS:
        raise ValueError("unknown mode %r; expected one of %s" % (mode, ", ".join(MODES)))
    anchor = _clean(company if mode in QUOTED_ANCHOR_MODES else search_name(company))
    if not anchor:
        raise ValueError(
            "queries_for needs a company; in the alumni modes that is the past "
            "employer or the school, not the target employer")

    groups = [g for g in _title_groups(titles, mode) if g]
    if not groups:
        raise ValueError("queries_for needs at least one title to search for")
    # The caller's titles in their order; otherwise the first of each group, so the
    # hiring authority and the senior practitioner each get a search.
    picks = ([t for g in groups for t in g] if titles else [g[0] for g in groups])

    # An alumni anchor is history and stays quoted: unquoted, "<Name> Money" matches
    # every profile with the word money in it.
    anchor_term = '"%s"' % anchor if mode in QUOTED_ANCHOR_MODES else anchor
    place = _clean(location)

    out = []
    for i, title in enumerate(picks):
        parts = [anchor_term, _clean(title), place]
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
# Search results to people: the bulk step, with nothing fetched
# ---------------------------------------------------------------------------

# A LinkedIn result title is the profile's own headline as the search engine
# indexed it: "Name - Employer", "Name - Title - Employer", "Name - Title at
# Employer", or "Name - <a place>". It is the evidence a person exists at an
# employer that needs no read: the profile's URL and its own words, captured
# from the result and never fetched.
_TITLE_SPLIT = re.compile(r"\s+[-\u2013\u2014|]\s+")
# A letters-after-the-name word: all capitals (CFA, PMP, FCA), dotted (P.Eng., M.Sc.), or
# one of the mixed-case degrees. Never any short capitalised word: that took a short
# surname off a three-word name, and would take "Smith" off "Mary Ann Smith".
_CREDENTIAL = re.compile(r"^(?:[A-Z][A-Z0-9&]{1,6}|(?=[A-Za-z.]*\.)[A-Z][A-Za-z.]{1,7}|"
                         r"Ph\.?D\.?|D\.?Phil\.?|M\.?Sc\.?|B\.?Sc\.?|M\.?Eng\.?|"
                         r"P\.?Eng\.?|M\.?B\.?A\.?|M\.?P\.?H\.?)$")
# A part that names a job rather than an employer: "Data and Analytics Leader".
# A job word the list lacked made "Senior Actuary, London" a place, and the title was lost.
_ROLE_WORD = re.compile(r"\b(?:manager|director|head|lead|leader|analyst|scientist|engineer|"
                        r"officer|consultant|founder|specialist|partner|vp|avp|svp|evp|"
                        r"president|adviser|advisor|architect|coordinator|executive|principal|"
                        r"associate|strategist|developer|designer|recruiter|researcher|"
                        r"professor|student|intern|actuary|actuaries|accountant|auditor|"
                        r"underwriter|economist|statistician|controller|treasurer|chief|"
                        r"secretary|administrator|assistant|representative|counsel|lawyer|"
                        r"solicitor|attorney|paralegal|nurse|physician|doctor|pharmacist|"
                        r"therapist|teacher|lecturer|tutor|editor|writer|journalist|producer|"
                        r"technician|operator|planner|buyer|trader|broker|banker|agent|owner|"
                        r"ceo|cfo|cto|coo|cio|cdo|cro|chair|chairman|chairwoman|chairperson|"
                        r"fellow|postdoc|graduate|apprentice|trainee|supervisor|inspector|"
                        r"investigator|examiner|programmer|modeller|modeler|quant|steward|"
                        r"contractor|freelancer|volunteer|trustee|governor|mentor|coach|"
                        r"practitioner|expert|staff)s?\b", re.I)
# "<function> @ <Employer>" is how many headlines write "at". Read whole, "Data @
# Kestrel" was an employer of that name, and its person was dropped as working elsewhere.
_AT = re.compile(r"(?:\bat\s+|(?:^|\s)@\s*)(\S.*)$")
# A place in the shape a LinkedIn location takes, whatever the city: "Greater <City>
# Area", "<City> Bay Area", "Region of <Name>", "<Name> County". The words alone are
# not enough: "Kestrel State Bank" and "Greater Kestrel Analytics" are employers.
_PLACE_SHAPE = re.compile(r"^(?:greater\s+\S|(?:region|county|province|state)\s+of\s)|"
                          r"\s(?:area|region|county|province|state)$", re.I)
# An institution: where somebody studies or works, never a place, and never the employer
# a search was for unless it is that institution.
_INSTITUTION = re.compile(r"\b(?:university|universit[éeà]|college|school|institute|"
                          r"polytechnic|academy|hochschule|école|escuela)\b", re.I)
# Words that name a team or a function, not an employer and not a place: "Data
# Science, Data & AI Strategy" and "Data Governance Team" are where in an
# organisation somebody sits. A part made only of these is never read as a place
# or as an employer.
_TEAM_WORDS = frozenset("""data analytics analysis ai ml science sciences strategy governance
office team engineering insight insights platform platforms risk operations technology digital
research product products finance marketing enterprise intelligence business machine learning
artificial decision decisions quantitative modelling modeling pricing growth transformation
innovation lab labs centre center excellence management information systems security cloud
software development global and of the for""".split())
_JOINERS = frozenset({"and", "of", "the", "for"})
# The statuses an existence check can give, strongest first. Only "verified" is ever
# shown as confirmed, and even that is as of the search: the profile was indexed,
# never read, and may have changed since.
PROFILE_STATUS = ("verified", "likely", "unconfirmed")


def _person_like(name: str) -> bool:
    words = name.split()
    return 2 <= len(words) <= 5 and all(re.match(r"^[^\W\d_][\w.'\-]*$", w) for w in words)


# Words in an organisation's name or a page's, never a person's: "Leadership Team",
# "<Employer> Group", "<Employer> Careers".
_ORG_WORDS = re.compile(r"\b(?:team|leadership|careers?|jobs|talent|recruiting|recruitment|"
                        r"hiring|official|news|foundation|association|society|department|"
                        r"group|company|limited|ltd|inc|llc|plc|corp|corporation|gmbh)\b", re.I)


def _a_person(name: str, company: str = "") -> bool:
    """Is this a person's name: a few plain words that are not an institution, a team,
    an organisation, or the employer itself? A university's post naming the employer
    was kept as a likely contact called "University of <Name>", and the employer's own
    page as one called "<Employer> Group"."""
    if not _person_like(name) or _INSTITUTION.search(name) or _ORG_WORDS.search(name) \
            or _team_only(name):
        return False
    return not (company and same_employer(name, company))


def _team_only(text: str) -> bool:
    words = re.findall(r"[a-z]+", _ck_fold(text).lower())
    return bool(words) and all(w in _TEAM_WORDS for w in words) \
        and any(w not in _JOINERS for w in words)


def _plain_words(part: str) -> bool:
    """Could this be a place's name: a few plain words, no job, team or institution in it."""
    s = str(part or "")
    if re.search(r"[\d&@]", s) or _ROLE_WORD.search(s) or _INSTITUTION.search(s):
        return False
    words = re.findall(r"[a-z]+", _ck_fold(s).lower())
    return 1 <= len(words) <= 4 and not any(w in _TEAM_WORDS - _JOINERS for w in words)


def _known_place(part: str) -> bool:
    """A place the person's profile names (their metro, regions, home country, the
    countries and cities its location gate knows), or one in a place's shape."""
    s = _norm_place(part)
    if not s:
        return False
    if s in _PLACE_NAMES or _places.HOME_COUNTRY_RX.fullmatch(s):
        return True
    return bool(_PLACE_SHAPE.search(str(part).strip())) and _plain_words(part)


def _is_place(text: str) -> bool:
    """A location as a result title writes one. Every comma part could be a place and
    at least one is a known place: a comma alone made "Data Science, Data & AI
    Strategy" a location, which no city matched, so its person ranked as out of market."""
    parts = [p.strip() for p in str(text or "").split(",") if p.strip()]
    return (bool(parts) and all(_known_place(p) or _plain_words(p) for p in parts)
            and any(_known_place(p) for p in parts))


def _comma_part(last: str, company: str = "") -> tuple:
    """(headline, employer, location) from a final title part that holds a comma and
    is not a location as a whole."""
    parts = [p.strip() for p in last.split(",") if p.strip()]
    n = 0
    while n < len(parts) - 1 and _known_place(parts[-1 - n]):
        n += 1
    body, place = parts[:len(parts) - n], ", ".join(parts[len(parts) - n:])
    # The employer searched, in any part: "Northgate Bank, Data Governance Team" is
    # that bank's governance team.
    for p in body if company else ():
        if same_employer(p, company):
            return ", ".join(x for x in body if x is not p), p, place
    for i in range(len(body) - 1):
        # "Quillfeather, AI by Brannock": one employer, after a job or not ("Partner,
        # Quillfeather, AI by Brannock" read "AI by Brannock" as somewhere else).
        if _BRAND_LINE.match(", ".join(body[i:])):
            return ", ".join(body[:i]), ", ".join(body[i:]), place
    # "University of Larkspur, Faculty of Science": the institution is where they are.
    inst = next((p for p in body if _INSTITUTION.search(p)), "")
    if inst:
        return ", ".join(x for x in body if x is not inst), inst, place
    head = ", ".join(body)
    if place and _ROLE_WORD.search(head):
        return head, "", place                 # "Head of Data, Greater Manchester"
    if len(body) >= 2 and _ROLE_WORD.search(", ".join(body[:-1])) and not _team_only(body[-1]):
        # "Former President and CEO, Kestrel Mutual": a job and its employer. The comma
        # alone once made it a place, so a former CEO kept the employer he had left.
        return ", ".join(body[:-1]), body[-1], place
    return head, "", place                     # a job or a team, never a place


def _employer_and_place(text: str) -> tuple:
    """"Kestrel Mutual, Greater Manchester" after "at": the employer, and where they are."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    n = 0
    while n < len(parts) - 1 and _known_place(parts[-1 - n]):
        n += 1
    return ", ".join(parts[:len(parts) - n]), ", ".join(parts[len(parts) - n:])


def parse_result_title(title: str, company: str = "") -> dict:
    """{"name", "headline", "employer", "location"} from one result title; "" for a
    part the title does not carry, and no name when it is not a person's.

    `company` is the employer the search was for: a part that names it is read as
    where they work, wherever it sits in the title."""
    t = re.sub(r"\s*\|\s*LinkedIn\s*$", "", str(title or ""), flags=re.I)
    t = re.sub(r"\s*(?:\.\.\.|\u2026)\s*$", "", t).strip()
    parts = [p.strip() for p in _TITLE_SPLIT.split(t) if p.strip()]
    out = {"name": "", "headline": "", "employer": "", "location": ""}
    if not parts:
        return out
    name = re.sub(r"\([^)]*\)", " ", parts[0]).split(",")[0]
    words = name.split()
    while len(words) > 2 and _CREDENTIAL.match(words[-1]):
        words.pop()
    name = " ".join(words)
    if not _a_person(name, company):
        return out
    rest = parts[1:]
    # "<Brand> - AI by <Parent>": a brand line written with a dash instead of a comma is
    # one employer, and its second half alone ("AI by <Parent>") read as another employer.
    for i in range(len(rest) - 1, 0, -1):
        if _BY_PARENT.match(rest[i]):
            rest[i - 1:i + 1] = ["%s, %s" % (rest[i - 1], rest[i])]
    # "Name - Title - Employer - <a place>": the place last, and the employer before it.
    # Only the title was read, so somebody at another firm was kept as likely at the
    # employer searched.
    if len(rest) >= 3 and _is_place(rest[-1]) and not _names_company(rest[-1], company):
        inner = parse_result_title(" - ".join([name] + rest[:-1]), company)
        inner["location"] = inner["location"] or rest[-1]
        return inner
    out["name"] = name
    if not rest:
        return out
    last = rest[-1]
    at = _AT.search(last)
    if len(rest) >= 2:
        out["headline"] = rest[0]
    if at:
        out["headline"] = out["headline"] or last
        out["employer"], out["location"] = _employer_and_place(at.group(1).strip())
    elif _is_place(last) and not _names_company(last, company):
        out["location"] = last
    elif "," in last:
        headline, out["employer"], out["location"] = _comma_part(last, company)
        out["headline"] = out["headline"] or headline
    elif (len(rest) == 1 and _ROLE_WORD.search(last)) or _team_only(last):
        out["headline"] = out["headline"] or last
    else:
        out["employer"] = last
    return out


# The second half of a brand line: "AI by <Parent>", "a <Parent> company" is not one.
_BY_PARENT = re.compile(r"^(?:\S+\s+){0,3}by\s+\S", re.I)


def _names_company(text: str, company: str) -> bool:
    """Does one comma part of `text` name the employer searched? Then it is no place:
    "<Employer>, Manchester" was read as a location, and the employer was lost."""
    return bool(company) and any(same_employer(p.strip(), company)
                                 for p in str(text or "").split(",") if p.strip())


def profile_status(parsed: dict, url: str, company: str = "", name: str = "") -> str:
    """How sure a search result makes it that this person has a profile at this employer.

    verified:    a profile URL whose own title names the person and the employer
    likely:      a profile URL whose title names the person, and the employer only
                 as part of its headline, or not at all
    unconfirmed: anything else. A search cannot prove someone has no profile.

    A match rests on the employer named as where they work, never on a word of the
    title that happens to spell it: an institution whose name contains it, or the
    person's own name. A search for a one-word employer finds everyone with that
    first name, and each came back "likely" at the employer.
    """
    if not is_person_url(url) or not parsed.get("name"):
        return "unconfirmed"
    if name:
        import state
        if state._match_name(name) != state._match_name(parsed["name"]):
            return "unconfirmed"
    if not company:
        return "likely"
    if parsed.get("employer"):
        return "verified" if same_employer(parsed["employer"], company) else "unconfirmed"
    if _names_employer(parsed.get("headline", ""), company):
        return "likely"
    return "unconfirmed" if name_explains(parsed["name"], company) else "likely"


def name_explains(name: str, company: str) -> bool:
    """Is the employer's name one of the person's own names? Then a result that names
    no employer was found by their name, and says nothing about where they work."""
    want = re.findall(r"[a-z0-9]+", _ck_fold(search_name(company)).lower())
    have = set(re.findall(r"[a-z0-9]+", _ck_fold(name).lower()))
    return bool(want) and all(w in have for w in want)


def people_from_results(results, company: str = "", kind: str = "title_search",
                        query: str = "", today=None) -> list:
    """The people a set of search results names, each with its evidence. Nothing fetched.

    `results` is what the search tool returned: [{"title", "url"}, ...]. A listing,
    a company page and a result that is not a person's are dropped; a post becomes
    its author with the post's date. Only a result that is the person's own profile
    or post counts: a name that appears in a search summary, a "people also viewed"
    list or another person's page is somebody else's page and never a candidate.
    """
    today = today or dt.date.today()
    out, seen = [], set()
    for r in results or ():
        url, title = str(r.get("url") or ""), str(r.get("title") or "")
        got = resolve_result(url, company)
        if not got or not got.get("profile_url"):
            continue
        handle = _profile_handle(got["profile_url"])
        if handle in seen:
            continue
        parsed = parse_result_title(title, company)
        if got["kind"] == "post":
            m = re.match(r"^(.+?)\s+(?:on LinkedIn|posted on LinkedIn)\b:?", title)
            parsed = {"name": m.group(1).strip() if m else "", "headline": "", "employer": "",
                      "location": ""}
            if not _a_person(parsed["name"], company):
                continue
            # A post the search matched on its body, about another company, says nothing
            # about where its author works: a post about another company was kept as a
            # candidate at the employer searched. Only a post titled with the employer,
            # after its author's name: an author whose first name is the employer's
            # was kept on the strength of the name.
            if company and not _names_employer(title[m.end():], company):
                continue
        if not parsed["name"]:
            continue
        seen.add(handle)
        status = profile_status(parsed, got["profile_url"], company) if got["kind"] == "profile" \
            else "likely"
        # A name check whose employer is one of the person's own names proves nothing
        # either: the check searches "<name> <employer>", which their name alone answers,
        # so a consultant called Ada was kept at an employer called Ada.
        by_name = status == "unconfirmed" and not parsed["employer"] and bool(company)
        employer = parsed["employer"]
        if employer and status == "verified" and company_key(employer) != company_key(company):
            # The employer under another of its names ("<Name> Ratings", a brand line):
            # filed under the name searched, so the contact joins its applications.
            employer = company
        found = {
            "name": parsed["name"], "title": parsed["headline"],
            "company": employer or (company if status != "unconfirmed" else ""),
            "location": parsed["location"], "linkedin_url": got["profile_url"],
            "found_via": kind, "profile_status": status,
            "post_date": got["post_date"].isoformat() if got.get("post_date") else "",
            # A post's date is its author's own last activity on LinkedIn, and a hiring
            # post's signal date: kept only as post_date, which no check reads, a 2023
            # post passed for someone there now.
            "activity_date": got["post_date"].isoformat() if got.get("post_date") else "",
            "signal_date": got["post_date"].isoformat() if got.get("post_date") else "",
            "evidence": f"search result {today.isoformat()}: \"{title.strip()}\" ({url})"
                        + (f", for {query!r}" if query else ""),
        }
        if by_name:
            # Nothing but their own name ties them to the employer: triage drops them.
            found["name_match_only"] = (f"the search matched their name, not {company}: "
                                        "the result names no employer")
        out.append(found)
    return out


# Words a group gives one of its businesses: "<Name> Ratings", "<Name> Analytics",
# "<Name> Data & Services". company_key strips some (services, solutions,
# technologies) and keeps the rest, so somebody at the ratings arm read as working
# somewhere else and was dropped from a search for the group. A firm the person knows
# to be separate goes in their employers.py SEPARATE, and is never joined here.
BUSINESS_LINE = frozenset({"ratings", "analytics", "data", "services", "solutions", "digital",
                           "labs", "ai", "research", "insights", "intelligence", "technology",
                           "technologies", "consulting", "advisory"})
# "<Brand>, <what it does> by <Parent>": one employer, written as its brand and its parent,
# which a person may file as "<Parent> <Brand>".
_BRAND_LINE = re.compile(r"^\s*([^,]+?)\s*,\s*(?:[^,]*?\s)?by\s+([^,]+?)\s*$", re.I)


def _names_of(name: str) -> list:
    """The names one employer string stands for: itself, a brand line's brand and its
    parent (alone and together), or each part of "Northgate Bank, Data Team"."""
    s = str(name or "").strip()
    m = _BRAND_LINE.match(s)
    if m:
        brand, parent = m.group(1), m.group(2)
        return [s, brand, parent, f"{brand} {parent}", f"{parent} {brand}"]
    return [s] + ([p.strip() for p in s.split(",") if p.strip()] if "," in s else [])


def _same_key(a: str, b: str) -> bool:
    ka, kb = company_key(a), company_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    if _company_key.SEPARATE.match(ka) or _company_key.SEPARATE.match(kb):
        return False
    short, long_ = sorted((ka.split(), kb.split()), key=len)
    return long_[:len(short)] == short and all(w in BUSINESS_LINE for w in long_[len(short):])


def same_employer(a: str, b: str) -> bool:
    """Do these two names mean one employer? company_key's join, plus what a profile
    headline writes that it does not: a business line after the name ("<Name> Ratings",
    "<Name> Data & Services") and a brand line ("<Brand>, AI by <Parent>" against
    "<Parent> <Brand>"). Each of those was dropped as "works at <it>, not <the employer>".
    """
    if not company_key(a) or not company_key(b):
        return False
    return any(_same_key(x, y) for x in _names_of(a) for y in _names_of(b))


# A brand line inside running text: "Quillfeather, AI by Brannock is hiring".
_BRAND_IN_TEXT = re.compile(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3}),\s*(?:\S+\s+){0,3}?"
                            r"by\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3})")


def _names_employer(text: str, company: str) -> bool:
    """Does `text` name `company`, as people write it (search_name) or by its key (the
    name without "Group" and the like), word for word, or as a brand line? Word for word
    alone, a post by somebody at "<Name> Ratings" was skipped in a search for "<Name>
    Group", and so was a post naming the employer by its brand line."""
    text = str(text or "")
    low = text.lower()
    for want in dict.fromkeys((search_name(company).lower(), company_key(company))):
        words = re.findall(r"[a-z0-9&]+", want or "")
        if words and re.search(r"(?<![a-z0-9])" + r"\W+".join(map(re.escape, words))
                               + r"(?![a-z0-9])", low):
            return True
    return any(same_employer("%s, by %s" % (m.group(1), m.group(2)), company)
               for m in _BRAND_IN_TEXT.finditer(text))


def _profile_handle(url: str) -> str:
    import state
    return state.profile_handle(url) or url


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
    # "I'm looking for", "dm me" and "reach out if" are how a job seeker writes
    # too: "I'm looking for my next opportunity in data" made another candidate
    # tier 1 with that line as the hook. They count only with a role after them.
    r"(we[’']?re hiring|we are hiring|"
    r"(?:i[’']?m|i am|we[’']?re|we are) looking for (?:a |an |two |three |several |\d+ )?"
    r"(?:(?:senior|staff|lead|principal|junior)\s+)?(?:" + _ROLE_NOUNS + r")\b|"
    r"join my team|open roles?|we are seeking|we[’']?re seeking|"
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
# English, and the person's to replace (networking.py AUTHORITY_TITLE and
# SENIOR_IC_TITLE): "Leiter Datenanalyse" or "Directora de Anal\u00edtica" matched
# neither, so in another language everybody read as tier 4, and "Staff Nurse"
# read as a senior IC.
AUTHORITY_TITLE = _NET_GET("AUTHORITY_TITLE", None) or re.compile(
    r"\b(head of|director|dir\.|vp|vice president|svp|evp|avp|chief|"
    r"manager|managing director)\b", re.I)

SENIOR_IC_TITLE = _NET_GET("SENIOR_IC_TITLE", None) or re.compile(
    r"\b(principal|staff|lead|senior|sr\.?)\b", re.I)

# Tier 2 is authority "on a team matching the user's function", so authority
# alone is not enough: a Director of Marketing is tier 4 to a data analyst and
# tier 2 to a marketer. networking.py FUNCTION_TITLE. Unset, every title is in
# function: a run ranks by authority and seniority alone, which over-includes.
# A data team's list as the default would write every employer off for a nurse
# as having "no relevant presence".
FUNCTION_TITLE = _NET_GET("FUNCTION_TITLE", None) or re.compile(r".", re.S)

# The home city's metro, as a person's location may name it: a search for the
# home city accepts anyone in one of these. networking.py's METRO and the job
# search's metro (search.py LOCATION, through tools/places.py) together: the two
# were written separately and drifted, and a contact in a town only one of them
# named read as out of market. networking.py's list stays the person's own and is
# only added to; unset, the search's metro is the whole list.
METRO = _places.metro_with(getattr(_NET, "METRO", ()))
# A whole post is read against networking.py's METRO alone. The search's list was
# written for location strings, and in free text a town named like a word matches
# the word: "Sale" is in "point of sale".
_TEXT_METRO = tuple(getattr(_NET, "METRO", ()))
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


_COUNTRY = tuple(w for w in (_NET_GET("HOME_COUNTRY", "") or "",) if w)
_HOME_TOKENS = [t for t in _norm_place(_HOME).split(" ") if t]
# REGION_WORDS is read two ways: as the region part of a location ("Bury,
# England") and as a word in a post ("remote across the UK"). A postal
# abbreviation belongs to the first only: "on" or "in" as a word in free text
# matches nearly every post. Free text skips the short words English uses for
# something else.
_COMMON_WORDS = {"on", "in", "at", "or", "an", "as", "is", "it", "to", "of", "by", "me",
                 "we", "us", "be", "do", "go", "no", "so", "up", "hi", "ok", "la", "de"}
def _free_text(words):
    return tuple(w for w in words if _norm_place(w) and _norm_place(w) not in _COMMON_WORDS)


_FREE_TEXT_PLACES = _free_text(_REGIONS + _COUNTRY)
# The countries a location may name that are not home: the profile's location
# gate list (search.py LOCATION other_countries), which the prefilter reads too.
_OTHER_COUNTRIES = tuple(_norm_place(c) for c in _places.OTHER_COUNTRIES)


# Every place the profile names, normalised: what a result title's location may be.
# The person's metro and home city, their regions and country, the broad places, the
# countries and cities the job search's location gate knows, and networking.py
# PLACE_WORDS. With no world gazetteer, a part the profile never names is a place only
# in a place's shape (_PLACE_SHAPE) or beside a known one ("<City>, <Region>, France").
_LOC = _places.LOCATION
_PLACE_NAMES = frozenset(n for n in (_norm_place(x) for x in (
    *METRO, _HOME, *_REGIONS, *_COUNTRY, *BROAD_PLACES, *_OTHER_COUNTRIES, *_places.REGIONS,
    *(_LOC.get("outside") or ()), *(_LOC.get("home_country_alone") or ()),
    *(str(_LOC.get(k) or "") for k in ("home_country", "home_region", "metro_name")),
    *getattr(_NET, "PLACE_WORDS", ()))) if n)


def _has_words(text, phrase):
    """`phrase` as whole words in `text`: "bury" is not in "aylesbury"."""
    p = _norm_place(phrase)
    return bool(p) and re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", text) is not None


def _in_metro(text, metro=None):
    return any(_has_words(text, g) for g in (METRO if metro is None else metro))


def _is_home(tokens):
    """Is the target the home city? Every word of it, so "New York" works."""
    return bool(_HOME_TOKENS) and all(t in tokens for t in _HOME_TOKENS)


def _abroad(location):
    """A location that names another country after the city.

    "Manchester, <region>, United States" carries the city and is not it. Only
    a country the profile names as not home counts: reading every region part
    the profile did not list as abroad put "<City>, ON", the ordinary Canadian
    form, in another country and ranked the person last.
    """
    parts = [_norm_place(p) for p in str(location or "").split(",")[1:]]
    return any(p in _OTHER_COUNTRIES for p in parts if p)


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
    if _abroad(location):
        return False
    words = set(loc.split())
    if all(t in words for t in tokens):
        return True
    if _is_home(tokens) and _in_metro(loc):
        return True
    if loc in BROAD_PLACES:
        target = _norm_place(target_location)
        return (any(_has_words(target, w) for w in _FREE_TEXT_PLACES)
                or _is_home(tokens) or _in_metro(target))
    return False


def _signal_reaches_market(signal, target_location, in_market=False):
    """A hiring post counts as tier 1 only if the hiring is here.

    The brief's own example is why this reads the post and not just the
    poster: the lead is hiring for "<City>, <Other City> or remote" and may
    sit in any of them. "Remote" reaches here only from somebody here or with
    the country or region named: "hiring remote data scientists, US time zones
    only" from Austin was tier 1 for Manchester.
    """
    text = _norm_place(signal)
    if not text:
        return False
    words = set(text.split())
    # The places the post names come first: "<City>, <Other City> or remote"
    # names this city, and reading "remote" first returned before it looked.
    tokens = _city_tokens(target_location)
    if tokens and all(t in words for t in tokens):
        return True
    if _is_home(tokens) and _in_metro(text, _TEXT_METRO):
        return True
    if "remote" in words:
        return in_market or any(_has_words(text, w) for w in _FREE_TEXT_PLACES)
    return False


# A place named inside the post. The preposition is required because a bare
# capitalized word in a post is a team or a product far more often than a city.
_SIGNAL_PLACE = re.compile(
    r"\b(?:based in|located in|hiring in|roles? in|opening in|in|out of|across)"
    r"\s+([A-Z\u00c0-\u00de][a-z\u00df-\u00ff]+(?:[\s-][A-Z\u00c0-\u00de][a-z\u00df-\u00ff]+){0,2})")

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
    if all(t in set(loc.split()) for t in tokens):
        return True
    return _is_home(tokens) and _in_metro(loc)


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


# Other functions a hiring line can name. Tier 1 is a live hiring post about the
# person's own work, and a Director of Data Science posting "our marketing team
# is hiring a content writer" passed on the poster's title alone, quoted as the
# evidence. A word the person's own titles use is never "other": an operations
# analyst's "operations team" is their own.
_OTHER_FUNCTION_WORDS = (
    "marketing", "sales", "content", "brand", "social media", "copywriter", "writer",
    "editor", "designer", "design", "ux", "ui", "legal", "lawyer", "counsel", "hr",
    "human resources", "people partner", "recruiter", "finance", "financial",
    "accounting", "accountant", "payroll", "customer success", "customer support",
    "support", "account executive", "account manager", "business development", "bdr",
    "sdr", "communications", "pr", "crm", "procurement", "facilities", "office manager",
    "administrator", "administrative", "assistant", "receptionist", "nurse", "teacher",
    "chef", "driver", "warehouse", "store", "retail associate", "business", "operations",
    "product", "engineering", "engineer", "developer", "data", "analytics")


def _own_words() -> set:
    text = " ".join([_ROLE_NOUNS, " ".join(TITLE_SETS.get("function") or []),
                     getattr(FUNCTION_TITLE, "pattern", "")]).lower()
    return set(re.findall(r"[a-z]+", text))


def _other_function_rx():
    own = _own_words()
    words = [w for w in _OTHER_FUNCTION_WORDS if not set(w.split()) & own]
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I) \
        if words else None


_OTHER_FUNCTION = _other_function_rx()


def about_their_function(signal) -> bool | None:
    """Is this hiring line about the person's own work? None when it names no role.

    A role of theirs that no other function qualifies ("a data analyst") says yes;
    one that does ("a sales analyst") does not count, and a line naming only
    another function says no. A bare "we're hiring" says nothing either way, and
    the poster's title decides.
    """
    text = str(signal or "")
    if not text:
        return None
    for m in re.finditer(r"\b(?:" + _ROLE_NOUNS + r")\b", text, re.I):
        before = text[max(0, m.start() - 25):m.start()]
        if not (_OTHER_FUNCTION and _OTHER_FUNCTION.search(before)):
            return True
    if _OTHER_FUNCTION and _OTHER_FUNCTION.search(text):
        return False
    return None


def classify_tier(snippet, title, location, target_location=HOME_CITY):
    """Score one person 1 to 4 (brief 3.3) and return the evidence with it.

    Returns (tier, quoted_signal_or_None). The signal is returned even when it
    did not earn tier 1, because a manager hiring in the wrong city is still
    something the caller may want to see before deciding.
    """
    title = _clean(title)
    signal = quote_signal(snippet)
    # No location in the result is not evidence of elsewhere: a roster row or a
    # snippet carries none, and the search itself named the city. Read as
    # unverified, it tiers like somebody here; triage marks it so.
    in_market = _same_market(location, target_location) if _clean(location) else True

    # Two ways to earn tier 1: the post names this market, or the poster is in
    # it and the post does not name a different one. Either way it has to be
    # hiring for the person's own work: a Director of Marketing posting "we're
    # hiring" is not a live signal for an analyst.
    about = about_their_function(signal)
    for_them = about if about is not None else bool(FUNCTION_TITLE.search(title))
    if signal and for_them and (
            _signal_reaches_market(signal, target_location, in_market)
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
    # The reason is the person's too (networking.py NOT_HIRING_REASON): "dressed
    # as technical" only says something to somebody in a technical function.
    Rule("revenue_role", "title", _NET_GET("NOT_HIRING_TITLES", re.compile(
        r"\b(solutions? architect|field engineer(?:ing)?|"
        r"cloud (?:&|and) ai specialist|technical account manager|"
        r"client partner|head of industry|customer success|sales engineer|"
        r"partner manager|account executive|solutions? consultant|"
        r"pre-?sales|business development)\b", re.I)) or _NEVER,
        _NET_GET("NOT_HIRING_REASON",
                 "a customer-facing revenue role, which does not hire for your function")),

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
    # The role words are the person's to change (networking.py SPAM_BULK_ROLES):
    # three of these in a run is a harvest for an IT or office search, and a
    # hospital's real nursing post for somebody who is a nurse. The default list
    # is kept; a person whose own job is on it removes that word.
    Rule("spam_bulk_roles", "text", re.compile(
        r"(?:\b(?:" + "|".join(_NET_GET("SPAM_BULK_ROLES", (
            r"java", r"\.net", r"dotnet", r"sap", r"qa tester", r"qa analyst", r"devops",
            r"salesforce", r"nurse", r"rn", r"truck driver", r"mechanical engineer",
            r"civil engineer", r"scrum master", r"network engineer", r"ios", r"android",
            r"php", r"sql developer", r"help ?desk", r"technician", r"peoplesoft",
            r"workday"))) + r")\b[^\n]{0,40}){3,}", re.I),
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
        # "joined a new team" is an internal move, and "after 8 years at Acme I
        # lead data" is tenure: only a leaving verb makes the years a departure.
        r"|(?:i(?:['\u2019]|\s+ha)?ve\s+)?joined\s+a\s+new\s+(?:company|chapter)"
        r"|after\s+\d+\+?\s+(?:great\s+|wonderful\s+|amazing\s+)?years?\s+at\b[^.!?\n]{0,40}"
        r"\b(?:left|leaving|moved on|moving on|on to (?:the )?next|onto (?:the )?next|"
        r"next chapter|new chapter|new adventure|said goodbye|saying goodbye|farewell|"
        r"it'?s time|stepped away|stepping away|departed|departing|last day|signing off)"
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
    # Their own headline says they have left: "Former President and CEO". It is the
    # title the search result carries, so it describes them now.
    Rule("moved_on_former_title", "person", re.compile(
        r"^\s*(former|ex|retired)\b(?!-\w)(?!.*\b(?:turned|now|current(?:ly)?)\b)", re.I),
        "has moved on, their own title says so"),
    Rule("moved_on_former", "text", re.compile(
        r"(?i:\b(?:formerly at|previously at|ex-))\s*"
        r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})"),
        "has moved on, left the company this search matched"),
)

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
# Distinct emoji in one post before it reads as a harvest rather than a hiring post.
SPAM_EMOJI_MIN = 5


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
            # Search results rarely carry the employer, so the company the
            # search ran against is theirs: an in-house Talent Acquisition
            # Partner found by the recruiting query was dropped as spam.
            if not _clean(person.get("company")) and not _clean(target):
                return "%s: %s" % (rule.reason, _matched(m))
            continue

        if rule.name == "spam_emoji":
            # Counted on distinct emoji, without the variation selector and
            # joiners that made "\u27a1\ufe0f" two: a real hiring post with three
            # arrows and a tick is not a staffing harvest.
            bare = re.sub("[\ufe0f\u200d\U0001F3FB-\U0001F3FF]", "", text)
            if len(set(_EMOJI.findall(bare))) < SPAM_EMOJI_MIN:
                continue

        if rule.name == "moved_on_joined":
            if target_k and same_employer(_matched(m), target):
                continue    # they joined the company being searched, which is the point
            return "%s: %s" % (rule.reason, _matched(m))

        if rule.name == "moved_on_former":
            if not target_k or not same_employer(_matched(m), target):
                continue    # career history at some other employer, not a move away
            return "%s: %s" % (rule.reason, _matched(m))

        return "%s: %s" % (rule.reason, _matched(m))
    return None


# ---------------------------------------------------------------------------
# 3.5  Stale data
# ---------------------------------------------------------------------------

STALE_MONTHS = 6


def _as_date(value):
    # A snippet's date comes as a month, a written date or a timestamp: every
    # format `dates.as_date` reads.
    return dates.as_date(value)


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
    # A result with no location says nothing about where they are, so it is never
    # reported as "not in" the city.
    if _clean(person.get("location")) and not _same_market(person.get("location"), target_location):
        return "not in %s: %s" % (target_location, person.get("location"))
    return "tier 4 adjacent: better targets exist at this company"


def printed_date(person) -> bool:
    """Is this person's date the date of a page that names them, not their own activity?

    True for every source kind that is not LinkedIn itself (sources.KINDS: press,
    team pages, rosters, awards...), where the date is the article's or the event's.
    """
    import sources
    kind = sources.KINDS.get(str(person.get("found_via") or ""))
    return bool(kind) and not kind.linkedin


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
    keep, adjacent, dropped, unknown, unrelated = [], [], [], [], []

    for person in people or []:
        # Found by their own name, not the employer's (people_from_results): nothing
        # says they work there, so they are not counted as a person who came back.
        if person.get("name_match_only"):
            unrelated.append((person, person["name_match_only"]))
            continue
        reason = disqualify(person, target_company)
        if reason:
            dropped.append((person, reason))
            continue

        # A company-targeted search returns near-misses: a result can be
        # another employer's Head of Data Science, whose title and city are a
        # perfect tier 2 and who is no use for a referral at the target. The
        # run asked "who at <Company>", so a result naming a different
        # current employer is out, and a blank employer field is not, because
        # most search results never return one. The employer under another of
        # its names (a business line, a brand line) is the same employer.
        stated = person.get("company") or ""
        if company_key(stated) and company_key(target_company or "") \
                and not same_employer(stated, target_company):
            dropped.append((person, "works at %s, not %s" % (stated, target_company)))
            continue

        presence = _person_date(person, PRESENCE_DATE_FIELDS)
        reverify = ""
        if is_stale(presence, today):
            # A press piece, a team page or an event's speaker list is dated by the
            # page, not by the person: a 2018 appointment says who was appointed,
            # not that they left. Kept, and marked to be checked before a note rests
            # on it. A date from LinkedIn itself is their own last activity.
            if not printed_date(person):
                dropped.append((person, "stale: last activity %s is over %d months old"
                                % (presence.isoformat(), STALE_MONTHS)))
                continue
            reverify = ("named on a %s page dated %s: check they still hold this role "
                        "before a note rests on it" % (person.get("found_via"), presence.isoformat()))

        tier, signal = classify_tier(
            person.get("snippet"),
            person.get("title") or person.get("headline"),
            person.get("location"),
            target_location)

        # A hiring post from last year is not live hiring intent. Drop the
        # signal and re-tier on the title alone, rather than dropping someone
        # who is demonstrably still in the seat. Tier 1 needs a live signal, so
        # an undated one does not earn it either: the signal date used to be
        # back-filled from the person's last activity, which dated a 2021
        # headline "We're hiring planners" to last week. A post permalink dates
        # itself (resolve_result), and that is the date that counts.
        signal_date = _person_date(person, SIGNAL_DATE_FIELDS)
        undated = bool(signal) and tier == 1 and signal_date is None
        if signal and (is_stale(signal_date, today) or undated):
            kept_line = signal if undated else None
            signal = None
            tier, _ = classify_tier(None,
                                    person.get("title") or person.get("headline"),
                                    person.get("location"),
                                    target_location)
        else:
            kept_line = None

        d = _person_date(person)
        enriched = dict(person)
        enriched["tier"] = tier
        enriched["signal"] = signal
        if kept_line:
            enriched["undated_signal"] = kept_line
        if not _clean(person.get("location")):
            enriched["location_unverified"] = True
        if reverify:
            enriched["reverify"] = reverify
        if not (person.get("linkedin_url") or "").strip():
            # Found by name only (a press piece, a speaker list): no request can go to
            # someone who has not been found on LinkedIn yet.
            enriched["name_only"] = True
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
        if not _clean(person.get("title") or person.get("headline") or person.get("snippet")):
            # A result titled only "Name - Employer" says nothing about the job: unknown,
            # not adjacent. Kept below the people whose title is known and never dropped
            # as tier 4, because the search that surfaced them asked for the job.
            enriched["title_unknown"] = True
            unknown.append((enriched, d, relevant))
            continue
        (keep if tier in RELEVANT_TIERS else adjacent).append(
            (enriched, d, relevant))

    # Three answers, not two. Nothing back from the search is no evidence about
    # the employer at all, and recording it as "no relevant presence" wrote a
    # company off on an empty result.
    if keep or unknown:
        verdict = "has_presence"
    elif adjacent or dropped:
        verdict = "no_relevant_presence"
    else:
        verdict = "no_results"
    if not keep:
        keep = adjacent + unknown
    else:
        dropped.extend((row[0], _adjacent_reason(row[0], target_location))
                       for row in adjacent)
        keep = keep + unknown
    dropped.extend(unrelated)

    # Sort is stable, so people with no date keep the order the search returned
    # them in rather than being shuffled to an arbitrary position.
    keep.sort(key=lambda row: (row[0]["tier"], row[2],
                               -(row[1].toordinal() if row[1] else 0)))
    return {"keep": [row[0] for row in keep], "dropped": dropped,
            "verdict": verdict}


# ---------------------------------------------------------------------------
# What a run leaves for the next one
# ---------------------------------------------------------------------------

# "No relevant presence" is a dated claim, like every other ruling-out here: a
# company stands up a team in a city, and the finding goes stale. It was written
# to company_research/ with no date and no reader, so it neither held nor
# expired. Kept there, beside the employer's research, through
# tools/company_research.py (which holds the review period beside the research's
# own freshness rule), and read by /network step 1 until the review date. Never
# written to do_not_target.json: two people searches are not the evidence that
# file needs, and the throttle reads it to skip the employer's job postings too.
PRESENCE_REVIEW_DAYS = company_research.PRESENCE_REVIEW_DAYS


def presence_record(verdict, today):
    """The record /network writes for an employer with no relevant presence, or None."""
    if verdict != "no_relevant_presence":
        return None
    day = _as_date(today)
    return {"verdict": verdict, "date": day.isoformat(),
            "review_after": (day + dt.timedelta(days=PRESENCE_REVIEW_DAYS)).isoformat()}


def presence_blocks(record, today):
    """Whether an earlier run's finding still rules this employer out today."""
    if not isinstance(record, dict) or record.get("verdict") != "no_relevant_presence":
        return False
    until = _as_date(record.get("review_after"))
    return until is not None and _as_date(today) < until


def record_presence(company, verdict, today, root=None):
    """Merge this run's finding into the employer's research file; its path, or None.

    Only `no_relevant_presence` is recorded (`presence_record`). The merge keeps
    every other field and leaves `fetched_date` alone, so the research beside it
    does not start to look freshly fetched.
    """
    record = presence_record(verdict, today)
    if record is None:
        return None
    return company_research.save(company, {"network_presence": record}, root=root)


def presence_ruled_out(company, today, root=None):
    """Whether the employer's cached finding still rules it out of a /network run today.

    Read whatever the research's own age: the finding carries its own date and
    review period, and stale facts beside it do not make it stale.
    """
    data, _age, _fresh = company_research.load(company, root=root)
    return presence_blocks(data.get("network_presence"), today)


def alumni_at(people, targets):
    """The alumni from one city-wide pass who now work at one of the targets.

    An alumni search names the shared history, never the target, so it is run
    once per /network rather than once per company, and each hit is sorted to
    the target it works at. Run through triage with no target_company first.
    """
    want = [t for t in targets or () if company_key(t)]
    out = {}
    for p in people or ():
        hit = next((t for t in want if same_employer(p.get("company") or "", t)), None)
        if hit is not None:
            out.setdefault(hit, []).append(p)
    return out


def _same_or_blank(a, b) -> bool:
    """One employer, or both unnamed: how two records of one person are matched."""
    return same_employer(a, b) if company_key(a or "") and company_key(b or "") \
        else not company_key(a or "") and not company_key(b or "")


def mark_first_degree(people, connections):
    """Flag the people the person is already connected with, from their own export.

    A 1st-degree connection takes a message, not a connection request: no note
    limit, no budget, and it was being drafted as a 300-character request
    LinkedIn would not let them send.
    """
    import state
    by_url = {state.profile_handle(c.get("linkedin_url")): c for c in connections or ()
              if state.profile_handle(c.get("linkedin_url"))}
    by_name = {}
    for c in connections or ():
        by_name.setdefault(state._match_name(c.get("name")), []).append(c)
    out = []
    for p in people or ():
        q = dict(p)
        hit = (by_url.get(state.profile_handle(p.get("linkedin_url") or p.get("url")))
               or next((c for c in by_name.get(state._match_name(p.get("name")), ())
                        if _same_or_blank(c.get("company"), p.get("company"))), None))
        if hit:
            q["first_degree"] = True
            q["channel"] = "message"
        out.append(q)
    return out


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
