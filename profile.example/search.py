"""Morgan Ellis's search: what they want, what they hold, where they will work. Fictional.

The shape every profile's search.py takes. /setup writes a real one from the
person's answers and from Claude's research on their market; the tools read it:
text_screen.py (salary, language, eligibility, credentials), prefilter.py
(location and title gates), opportunity.py and fit.py (scoring), bar.py (the
person's bar), throttle.py (exclusion vocabulary) and scrape_wide.py (what to
search). Anything left out falls back to a neutral default in the tool.
"""

import re

# ---------------------------------------------------------------------------
# Pay and experience
# ---------------------------------------------------------------------------
CURRENCY_SYMBOL = "£"
CURRENCY_CODE = "GBP"          # how a pay band is written when it names no currency
SALARY_FLOOR = 42_000          # walk-away: a stated range whose top is below this is cut
SALARY_TARGET = 48_000
SALARY_HIGH = 65_000
SALARY_PLAUSIBLE = (18_000, 250_000)
SALARY_CUT_BELOW = 32_000
SALARY_RANGE_BOUNDS = (15_000, 300_000)
YEARS_HELD = 7
# A range quoted in another currency is not comparable with the floor.
FOREIGN_CURRENCY = re.compile(r"\b(usd|us\s?\$|eur|euros?)\b|€", re.I)

# ---------------------------------------------------------------------------
# The bar: sectors this person will not work in
# ---------------------------------------------------------------------------
BAR_TARGET_MIDPOINT = 48_000
BAR_EXCLUDED = [
    (re.compile(r"\b(betting|bookmaker|casino|gambling|tobacco)\b", re.I),
     "a sector the candidate will not work in (gambling and tobacco)"),
]

# ---------------------------------------------------------------------------
# Language and eligibility
# ---------------------------------------------------------------------------
# English is the only language held. Welsh is the one the market raises: a
# role in Wales that makes it essential is a different job.
WELSH = re.compile(
    r"\bwelsh\b[^.\n]{0,40}\b(essential|required|mandatory)\b"
    r"|\b(fluent|fluency)\s+(in\s+)?welsh\b", re.I)
WELSH_SOFT = re.compile(r"\bwelsh\b[^.\n]{0,30}\b(desirable|an advantage|a plus|welcome)\b",
                        re.I)
LANGUAGE_GATE = [("Welsh", WELSH, WELSH_SOFT)]
LANGUAGES_HELD = ("english",)

# Settled status (EU Settlement Scheme): the right to work in the UK, no
# sponsorship, but not British citizenship. So "right to work in the UK" is met,
# while a role open only to British nationals, or one needing a security
# clearance the candidate does not hold, is a bar.
ELIGIBILITY = re.compile(
    r"\b(sc|dv|security)[- ]?(cleared|clearance)\b|\bdeveloped vetting\b"
    r"|\bbritish (citizen\w*|nationals?|nationality)\b|\bsole uk national\w*\b", re.I)
ENTITLED = re.compile(r"\bright to work in the (uk|united kingdom)\b", re.I)
ELIGIBILITY_STATUS_TERMS = re.compile(r"\b(british citizen\w*|british nationals?)\b", re.I)
ELIGIBILITY_ALWAYS = re.compile(r"\b(active|current|existing)\s+(sc|dv)\b|\bsole uk national",
                                re.I)
ELIGIBILITY_CUT_REASON = ("eligibility gate: British nationality or a security clearance "
                          "stated as a condition")

# Professional credentials the market gates on, none of them held.
DESIGNATION = re.compile(
    r"\b(ifoa|actuar\w*|aca|acca|cima|chartered accountant|ceng|chartered engineer)\b", re.I)
DESIGNATED_TITLE = re.compile(r"\b(actuar\w*|chartered accountant)\b", re.I)
# A discipline whose core is research, not the analytics the candidate does.
RESEARCH_ML = re.compile(
    r"\b(reinforcement learning|causal inference|contextual bandits?|"
    r"bayesian optimi[sz]ation|large language model pre-?training)\b", re.I)

# ---------------------------------------------------------------------------
# Location: Greater Manchester first, the North West by flag, remote in the UK
# ---------------------------------------------------------------------------
GREATER_MANCHESTER = [
    "manchester", "salford", "stockport", "trafford", "altrincham", "bolton",
    "bury", "oldham", "rochdale", "wigan", "tameside", "ashton-under-lyne",
    "sale", "stretford", "media city", "mediacity",
]
REGIONS = {
    "england": "England", "scotland": "Scotland", "wales": "Wales",
    "northern ireland": "Northern Ireland",
}
OTHER_COUNTRIES = ["ireland", "france", "germany", "netherlands", "spain", "poland",
                   "india", "united states", "usa", "canada", "australia"]
OUTSIDE = ["london", "birmingham", "bristol", "edinburgh", "glasgow", "cardiff",
           "newcastle", "belfast", "cambridge", "oxford", "reading"]
LOCATION = dict(
    home_country="United Kingdom",
    home_country_rx=re.compile(r"\b(united kingdom|uk|great britain|gb)\b"),
    home_country_alone=["united kingdom", "uk"],
    region_word="nation",
    regions=REGIONS,
    home_region="England",
    home_region_name="England",
    home_region_alone=[["england"], ["england", "uk"], ["england", "united kingdom"]],
    home_region_reason="England-wide, includes remote",
    metro_name="Greater Manchester",
    metro=GREATER_MANCHESTER,
    outside=OUTSIDE,
    other_countries=OTHER_COUNTRIES,
    # Places flagged rather than failed: commutable from Manchester, decided later.
    flag_places=[(re.compile(r"\b(leeds|liverpool|warrington|preston|sheffield)\b"),
                  "a commutable northern city; considered, never auto-dropped")],
)
LOCATION_FLAG_COSTS = [("commutable", None, 8, "a commutable northern city")]
LOCATION_FLAG_DEFAULT = (10, "outside Greater Manchester, decided later")

# ---------------------------------------------------------------------------
# Titles: what the job is called
# ---------------------------------------------------------------------------
POSITIVE = [r"analy", r"data", r"insight", r"forecast", r"planning", r"supply chain",
            r"operations", r"logistics", r"demand", r"inventory", r"reporting",
            r"business intelligence", r"\bbi\b", r"optimi"]
NEGATIVE = [
    (r"warehouse operative|forklift|hgv driver|picker|packer",
     "a warehouse or driving role, not analytics"),
]

# ---------------------------------------------------------------------------
# tools/fit.py: seniority, the core of the job, and what is not held
# ---------------------------------------------------------------------------
FIT_BANDS = [
    (re.compile(r"\b(chief|vp|vice[- ]president|head of|director)\b", re.I),
     -40, "director level, several bands above seven years"),
    (re.compile(r"\bprincipal\b", re.I), -25, "principal, typically 10+ years"),
    (re.compile(r"\b(lead|manager)\b", re.I), -4, "lead or manager, often with reports"),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), +8, "senior, the band the profile holds"),
    (re.compile(r"\b(analyst|specialist|planner|scientist)\b", re.I),
     +6, "individual-contributor band"),
]
# Titles below and above this person's level. A posting is ranked down for
# them, never cut: tools/fit.py docks a below-level title 25, tools/opportunity.py
# docks below 25 and above 12. Someone early in their career sets no
# FIT_BELOW_LEVEL, or a narrower one ("intern|student"), because "junior" and
# "graduate" are the roles they want.
FIT_BELOW_LEVEL = re.compile(
    r"\b(intern|internship|co[- ]?op|student|graduate|junior|entry[- ]level|"
    r"new grad\w*|campus|early career|apprentice|trainee|"
    r"post[- ]?doc\w*|postdoctoral|research fellow|phd candidate)\b", re.I)
OPP_BELOW_LEVEL = re.compile(r"\b(intern|internship|co[- ]?op|student|graduate|junior|"
                             r"entry[- ]level|apprentice)\b", re.I)
OPP_ABOVE_LEVEL = re.compile(r"\b(director|vp|vice president|head of|chief|principal)\b", re.I)
# tools/opportunity.py also adds employer tiers (employers.py), OPP_CORE and
# OPP_LEVERAGE. This profile sets none of them, so tools/fit.py rescales
# opportunity to the most it can score (58) rather than 130; OPP_SCALE pins it.

# tools/score_posting.py: job families that are not this person's, and the
# homonym fields that separate two jobs sharing a vocabulary. Flags, never cuts.
# The extractor is asked for each field named here.
SCREEN_WRONG_FAMILY = {
    "reporting_bi": "reporting and dashboard building is the whole job "
                    "(a deal-breaker the profile names)",
    "ml_engineering": "production ML engineering, a named weak-match area",
    "research_science": "research science rather than decision-facing analytics",
    "consulting_general": "strategy consulting with no technical stack named",
    "ops_planning": "demand or supply planning, a different job family",
    "software_engineering": "software engineering, a different job family",
}
SCREEN_HOMONYMS = {
    ("modelling_kind", "financial_valuation"):
        "'modelling' here is financial or valuation modelling (DCF, fund and "
        "portfolio work), not statistical or ML modelling",
    ("risk_kind", "market_investment"):
        "'risk' here is market, investment or portfolio risk, not account, "
        "credit or fraud risk scoring",
    ("risk_kind", "quant_library_engineering"):
        "'risk' here means building and packaging quant pricing or risk "
        "libraries, which is software engineering",
    ("analytics_serves", "sales_gtm"):
        "the analytics function serves sales or go-to-market, not product, "
        "pricing, risk or experimentation",
}

FIT_CORE = [
    (re.compile(r"\bsql\b", re.I), 9, "SQL"),
    (re.compile(r"\bpython\b", re.I), 8, "Python"),
    (re.compile(r"\b(forecast|demand planning|time[- ]series)\w*", re.I), 8, "forecasting"),
    (re.compile(r"\b(supply chain|logistics|inventory|warehouse)\b", re.I), 8, "supply chain"),
    (re.compile(r"\b(power bi|tableau|dashboard)\b", re.I), 5, "reporting"),
    (re.compile(r"\b(stakeholder|cross[- ]functional)\w*", re.I), 4, "stakeholder-facing"),
]
FIT_MISSING = [
    # (pattern, points at full demand, why): weighed by how hard the posting asks
    (re.compile(r"\b(spark|pyspark|scala)\b", re.I), -8, "big-data engineering is not held"),
]

# ---------------------------------------------------------------------------
# What the scrape searches (tools/scrape_wide.py)
# ---------------------------------------------------------------------------
SCRAPE_LOCATIONS = ["Manchester, England, United Kingdom", "Salford, England, United Kingdom",
                    "Stockport, England, United Kingdom", "United Kingdom"]
SCRAPE_REMOTE_LOCATIONS = ["United Kingdom"]
SCRAPE_EMPLOYERS = []
SCRAPE_EMPLOYER_QUERIES = ["data analyst", "supply chain analyst"]
SCRAPE_QUERIES = ["supply chain analyst", "operations analyst", "demand planning analyst",
                  "data analyst", "logistics analyst", "inventory analyst",
                  "business intelligence analyst", "forecasting analyst"]
SCRAPE_DEEP = "Manchester"
SCRAPE_EMPLOYER_LOCATIONS = ["United Kingdom"]
SCRAPE_EMPLOYER_REMOTE = ["United Kingdom"]
PORTAL_COUNTRY = "GB"
# The person's say over which portals run, by portal name, overriding each
# portal's SKILL.md default. Empty takes the app's defaults: linkedin-search and
# freehire-search on, and any portal built for this person on (tools/portals.py).
PORTALS: dict[str, bool] = {}
# The places a portal built for this person searches, as that board writes them,
# when that differs from SCRAPE_LOCATIONS: {"<portal>-search": ["<place>"]}.
# A portal not named searches the first of SCRAPE_LOCATIONS.
PORTAL_LOCATIONS: dict[str, list[str]] = {}
# The job boards researched for this person by /setup (or later, when a round
# comes back thin): each one built as a portal or why not, with the source.
# `python3 tools/portals.py` lists the ones with no portal, and a round that
# misses its yield target names them. One entry per board:
#   {"board": "<name>", "url": "<https://...>", "covers": "<market, field>",
#    "portal": "<name>-search", "status": "built" | "<why not, e.g. robots.txt
#    disallows /jobs>", "source": "<where the coverage claim came from>",
#    "checked": "YYYY-MM-DD"}
PORTAL_RESEARCH: list[dict] = [
    # Researched 14 Oct 2026 for this example's market (Manchester, supply chain and data
    # analyst roles). Real boards and real robots.txt rules; nothing is built, because an
    # example person has no repo of their own to build a portal in.
    {"board": "Reed", "url": "https://www.reed.co.uk",
     "covers": "UK general board, strong on Manchester analyst, planning and operations roles",
     "status": "not built: robots.txt (*) disallows only /api/, /handlers/ and tracking query "
               "strings, so search and postings are allowed, no Crawl-delay; public without "
               "login; the official Jobseeker API (free key) is the cleaner route; worth building",
     "source": "https://www.reed.co.uk/robots.txt", "checked": "2026-10-14"},
    {"board": "GOV.UK Find a job", "url": "https://www.jobs.service.gov.uk/jobs",
     "covers": "the UK public employment service, all fields, direct employers",
     "status": "not built: robots.txt allows /jobs and disallows the rest, no Crawl-delay; "
               "its terms allow reasonable automated copying for personal use; small for "
               "Manchester analyst roles, but cheap and sanctioned, so worth a light portal",
     "source": "https://www.jobs.service.gov.uk/robots.txt", "checked": "2026-10-14"},
    {"board": "Totaljobs", "url": "https://www.totaljobs.com",
     "covers": "UK general board, strong on office, analyst and logistics roles",
     "status": "not built: robots.txt allows search and postings but caps paging at 5, no "
               "Crawl-delay; automated fetches from a cloud container got no reply; build "
               "after Reed, and test from the runtime first",
     "source": "https://www.totaljobs.com/robots.txt", "checked": "2026-10-14"},
    {"board": "CV-Library", "url": "https://www.cv-library.co.uk",
     "covers": "UK general board, agency-heavy",
     "status": "not built: robots.txt disallows every query string except jobId= and "
               "page_number=, so only slug search pages work; a cloud container was "
               "blocked (403); lower priority",
     "source": "https://www.cv-library.co.uk/robots.txt", "checked": "2026-10-14"},
    {"board": "Adzuna UK", "url": "https://www.adzuna.co.uk",
     "covers": "UK aggregator across many boards, with salary estimates",
     "status": "not built: mostly reposts other boards; robots.txt could not be read (403); "
               "the official API needs a key, allows personal research and is rate limited",
     "source": "https://developer.adzuna.com/docs/terms_of_service", "checked": "2026-10-14"},
    {"board": "Indeed UK", "url": "https://uk.indeed.com",
     "covers": "UK's largest general board",
     "status": "not built: robots.txt disallows /viewjob and /job/ for every crawler, so "
               "postings cannot be fetched; no public job-search API",
     "source": "https://uk.indeed.com/robots.txt", "checked": "2026-10-14"},
]
# Read the person's LinkedIn job alerts into each round (tools/job_alerts.py), as
# a Gmail search for the alert emails, without a date: the round adds one. Empty
# is off, and stays off unless the person asks, because it reads their inbox.
# /setup writes it as "from:<the sender on one of their own alerts>".
JOB_ALERT_QUERY = ""
CANARY_LOCATION = "United Kingdom"
