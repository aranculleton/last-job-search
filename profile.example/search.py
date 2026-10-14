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
CANARY_LOCATION = "United Kingdom"
