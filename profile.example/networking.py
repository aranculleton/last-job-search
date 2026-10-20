"""Morgan Ellis's networking: their voice, their right to work, their places. Fictional.

The shape every profile's networking.py takes. Read by tools/network/compose.py
(the first note, sign-off, work authorization), tone.py (statuses not held),
reply.py (time zone, "no presence here", the eligibility bar) and discovery.py
(home city, metro, event rosters).
"""

import re

# Their LinkedIn account: "free" or "premium". It sets how long a connection
# note can be (200 or 300 characters), how many personalised notes a month a
# free account gets, and whether InMail is there at all (tools/network/schema.py).
LINKEDIN_PLAN = "premium"

# How a person's LinkedIn profile is read before a note is written to them
# (tools/network/reading.py): "browser" in Morgan's own signed-in browser, which
# LinkedIn's terms forbid as automated access and so needs their yes, or "paste",
# where they copy the page when they open it to send the request.
PROFILE_READS = "paste"
# How many profiles a browser read opens: at most this many in an hour and in a
# day, with varied pauses between them, and never more in a day than the requests
# Morgan can still send that day. It is Morgan's own LinkedIn account reading, and
# LinkedIn's terms forbid automated access at any pace: these lower the risk of a
# restriction and do not remove it, and raising them raises it.
PROFILE_READS_PER_HOUR = 8
PROFILE_READS_PER_DAY = 15

# Research papers as a discovery source (tools/network/openalex.py): for a field
# where the people worth meeting publish. Morgan's does not.
OPENALEX = False

# Where the people Morgan should meet are named, best first (tools/network/sources.py
# KINDS), researched by /setup for a mid-level data scientist in logistics and food
# in Manchester. Every run works down it, and the order moves by what draws replies.
PEOPLE_SOURCES = (
    ("connections", ""),
    ("alumni_employer", "Oakmere Foods and Saltmarsh Analytics, the employers Morgan has left"),
    ("alumni_school", "University of Leeds"),
    ("posting", "a named hiring manager on a shortlisted posting"),
    ("roster", "the regional supply-chain summit's speakers (ROSTERS above)"),
    ("community", "the city's data and analytics meetups: organisers work across employers"),
    ("posts", ""),
    ("team_page", "logistics and food employers' 'meet the team' and leadership pages"),
    ("title_search", ""),
    ("press", "supply-chain trade press quotes data leads by name"),
    ("people_tab", ""),
)

# LinkedIn's own export of Morgan's connections, as documents/linkedin/Connections.csv,
# so every run starts from people Morgan knows. "declined" when they would rather not.
CONNECTIONS_EXPORT = "declined"

# Who is writing.
SIGN_OFF = {"senior": "Kind regards,\nMorgan Ellis", "peer": "Thanks,\nMorgan"}
OPENER = "hope you're well"
ABOUT_ME = "I work in supply-chain analytics in Manchester and I'm looking for my next role"
ASK = "Would you have 15 minutes for a few questions sometime"
# Their own phrases, allowed back into a first note.
# How the person sounds, and what each kind of reader is told (tools/network/compose.py).
# Each is shown here at the app's default; a person's /setup writes theirs.
# Opening a sentence on "I'm" or "I'd": "allow", "warn" or "refuse".
CONTRACTIONS = "allow"
# How the person sounds in a message (tools/network/advice.py voice()), read by the
# composers and by compose.advise(). "contractions": True writes "I'm", "I'd", "it's" where
# speech has them, and advise() flags the stiff full form ("I am", "I would"). "shorthand"
# is the person's own short names, {full form: what they say}: an employer people know by a
# short name, "macro" for macroeconomics. The composers write the shorthand and advise()
# flags the full form. Never a deliberate typo. Empty, as here, nothing changes; Morgan's
# could be:
#   VOICE = {"contractions": True,
#            "shorthand": {"Saltmarsh Analytics": "Saltmarsh", "macroeconomics": "macro"}}
VOICE = {"contractions": False, "shorthand": {}}
# Work authorization in a first message, by who reads it; a message can still override it.
ELIGIBILITY = {"recruiter": True, "decision_maker": True, "peer": False}
# Saying the role wanted in a first message. Asking for the job stays a recruiter's alone.
SAY_THE_ROLE = {"recruiter": True, "decision_maker": True, "peer": False}
# The brief note's length for a senior reader.
SENIOR_NOTE_CHARS = 220
# An employer named late: "warn" (with the reordering) or "refuse".
EMPLOYERS_FIRST = "warn"
# An InMail longer than this reader needs is warned (the 200-word ceiling still holds).
INMAIL_WORDS = {"recruiter": 170, "decision_maker": 170, "peer": 130}
# The InMail subject; empty builds it from roles.py: "<title>, ex-<employers left>".
SUBJECT = ""
# The person's own ways of saying what carries no fact, per reader type or "any", each a
# list the composer chooses between per contact. Empty: their OPENER and ASK, then the
# app's phrase bank (python3 tools/network/compose.py phrases).
TEMPLATES = {}
OWN_VOICE = re.compile(r"^(?:hope you'?re well|(?:would|I'?d) love (?:to|a)\b)", re.I)

# Work authorization, in the two registers.
WORK_AUTH = {
    "senior": "I have settled status and full right to work in the UK, no sponsorship needed",
    "peer": "I can already work in the UK, no sponsorship needed",
    # What a recruiter or an employer hears, on a call or a form.
    "employer": "I have settled status and full right to work in the UK, no sponsorship needed",
}
WORK_AUTH_CLAUSE = re.compile(
    r"(?:my\s+)?visa(?:'s| is)?(?:\s+all)?\s+sorted"
    r"|I have settled status and full right to work in the UK"
    r"(?:,?\s*(?:and\s+)?no sponsorship (?:is\s+)?(?:needed|required))?"
    r"|I can already work in the UK"
    r"(?:,?\s*(?:and\s+)?no sponsorship (?:is\s+)?(?:needed|required))?", re.I)
WORK_AUTH_ANY = re.compile(
    r"\bno sponsorship\b|\bright to work\b|\bsettled status\b|\bwork in the UK\b|\bvisa\b", re.I)
# Statuses not held: settled status is not citizenship.
UNSUPPORTED_STATUS = re.compile(r"\b(british citizen(?:ship)?|uk citizen(?:ship)?|dual citizen)\b",
                                re.I)
UNSUPPORTED_WHY = "the candidate holds settled status, not British citizenship"
STATUS_NAME = "settled status"

# Places.
HOME_CITY = "Manchester"
HOME_COUNTRY = "uk"
HOME_ADJECTIVE = "british"
REGION_WORDS = ("uk", "united kingdom", "england")
TIMEZONE = "UK time (Europe/London)"
TIMEZONE_ABBR = "UK"
PLACE_WORDS = ("manchester", "salford", "leeds", "england", "uk", "british")
METRO = ("greater manchester", "salford", "stockport", "trafford", "bolton", "oldham",
         "rochdale", "wigan", "bury", "altrincham")
BROAD_PLACES = ("uk", "united kingdom", "england", "remote", "remote uk", "uk remote",
                "north west", "north west england")

# Where the people are listed: event speaker rosters, as (key, url, note).
ROSTERS = (
    ("example_supply_chain_summit", "https://example.com/speakers/",
     "A fictional roster: replace with the person's real events."),
)

# Call prep: which deal-breakers in profile/CLAUDE.md are categorical, and what
# in a role raises each.
PREP_CATEGORICAL = re.compile(r"\b(citizenship|nationality|clearance|Welsh)\b", re.I)
PREP_TRIGGERS = (
    (re.compile(r"\bbritish (citizen\w*|nationals?)\b|\bclearance\b|\bdeveloped vetting\b", re.I),
     re.compile(r"^Roles requiring .*(?:nationality|citizenship|clearance)", re.I)),
    (re.compile(r"\bwelsh\b", re.I), re.compile(r"Welsh", re.I)),
)
WORK_AUTH_LINE = re.compile(r"\b(settled status|right to work|work authori[sz]ation)\b", re.I)

# ---------------------------------------------------------------------------
# Who to look for, read by tools/network/discovery.py and reply.py. These are a
# data and analytics function's; a person in another field writes their own.
# ---------------------------------------------------------------------------
# The job titles a discovery run searches for, by group: hiring authority
# (tier 2), senior individual contributors (tier 3), the function itself (the
# alumni modes) and recruiters (the hiring-team mode).
TITLE_SETS = {
    "hiring_authority": [
        "Head of Data",
        "Director of Data Science",
        "Director of Analytics",
        "Data Science Manager",
        "Analytics Manager",
        "VP Data",
        "Head of Data Science",
        "Senior Manager, Analytics",
    ],
    "senior_ic": [
        "Staff Data Scientist",
        "Principal Data Scientist",
        "Lead Data Scientist",
        "Senior Data Scientist",
        "Staff Data Engineer",
        "Senior Analytics Engineer",
        "Lead Data Analyst",
    ],
    "function": [
        "Data Scientist",
        "Data Analyst",
        "Analytics Engineer",
        "Data Engineer",
    ],
    "recruiting": [
        "Technical Recruiter",
        "Talent Acquisition Partner",
        "Recruiting Manager",
        "Talent Partner",
    ],
}
# A title on a team in this function: what makes an in-market authority tier 2.
FUNCTION_TITLE = re.compile(
    r"\b(data|analytics|analytic|analysis|machine learning|ml|ai|"
    r"artificial intelligence|insight|insights|quantitative|quant|"
    r"decision scien\w+|business intelligence|bi|research scien\w+|"
    r"statistic\w*|econometric\w*|forecast\w*|experimentation|risk model\w*)\b",
    re.I)
# Titles that name the work rather than the org; ranked first when a run has
# more names than slots.
HANDS_ON_TITLE = re.compile(
    r"\b(?:tech(?:nical)?\s+lead|lead\s+(?:data|ml|machine|analytics|engineer)"
    r"|data\s+scien(?:ce|tist)\s*(?:&|and)?\s*ai\s+lead(?:er)?"
    r"|head\s+of\s+data(?:\s*(?:&|and)\s*ai)?"
    r"|staff\s+(?:data|applied|machine)"
    r"|principal\s+(?:data|applied|machine)"
    r"|applied\s+(?:ai|ml|scientist))", re.I)
# The role nouns a hiring post names ("recruiting ... <noun>", "Hiring <noun>").
# Why a revenue title (NOT_HIRING_TITLES, the default list here) is skipped,
# in this person's terms.
NOT_HIRING_REASON = "revenue role dressed as technical, does not hire for technical teams"
HIRING_ROLE_NOUNS = (r"data scientists?|data engineers?|data analysts?|analytics engineers?|"
                     r"machine learning engineers?|data science|analytics")
HIRING_HEADLINE_NOUNS = (r"data scientists?|data engineers?|data analysts?|"
                         r"analytics engineers?|machine learning engineers?|ml engineers?|"
                         r"applied scientists?")
# In a reply: functions that are not this person's ("I'm in sales"), where a
# contact can have moved to ("I've moved to product"), and the words for their
# own ("I don't work in data").
OTHER_FUNCTIONS = (r"sales|marketing|recruit\w*|hr|people|finance|legal|"
                   r"support|customer success|the commercial")
OTHER_FUNCTIONS_MOVED = (r"sales|marketing|recruit\w*|hr|people|finance|legal|"
                         r"support|customer success|product|design|ops|operations")
OWN_FUNCTION_WORDS = r"data|analytics|engineering|that"
