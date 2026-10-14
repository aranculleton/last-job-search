"""Morgan Ellis's networking: their voice, their right to work, their places. Fictional.

The shape every profile's networking.py takes. Read by tools/network/compose.py
(the first note, sign-off, work authorization), tone.py (statuses not held),
reply.py (time zone, "no presence here", the eligibility bar) and discovery.py
(home city, metro, event rosters).
"""

import re

# Who is writing.
SIGN_OFF = {"senior": "Kind regards,\nMorgan Ellis", "peer": "Thanks,\nMorgan"}
OPENER = "hope you're well"
ABOUT_ME = "I work in supply-chain analytics in Manchester and I'm looking for my next role"
ASK = "Would you have 15 minutes for a few questions sometime"
# Their own phrases, allowed back into a first note.
OWN_VOICE = re.compile(r"^(?:hope you'?re well|(?:would|I'?d) love (?:to|a)\b)", re.I)

# Work authorization, in the two registers.
WORK_AUTH = {
    "senior": "I have settled status and full right to work in the UK, no sponsorship needed",
    "peer": "I can already work in the UK, no sponsorship needed",
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
