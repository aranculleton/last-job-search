#!/usr/bin/env python3
"""What a posting is, read by code when it is staged, before any model spends a token.

One shortlisted role turned out, only after its research agent had finished, to be a
fixed-term contract in a finance department ending in four months. The posting text
said so, and the shortlist and the staging step both had that text and showed none of
it. So staging now reads every posting for the things a person decides on before
anything is drafted, and prints them beside the skills question:

    terms        permanent, or a contract, fixed term or cover, with its length and end
    pay          the stated band and its currency, and whether it is for the person's
                 place, for somewhere else, or in another currency
    years        the entry bar the posting states against the years the person holds
    degree       the level asked, whether it is required, and whether an equivalence
                 route is offered
    where        the location, the work mode, and the location gate's verdict
    seen         whether this search has seen the posting before, under another link
                 (a repost), or ruled it out
    employer     an application already in there, the same role applied to before, an
                 unsent draft, a referral in flight, a contact who has replied

A fatal or surprising property becomes a plain question (`questions`), and staging
holds the pick back from drafting until the person answers it: a fixed-term contract
(unless profile/search.py OPP_CONTRACT is None, a person who wants contracts), a pay
band for another place or in another currency, an application already in at the
employer, the same role applied to before, a referral in flight there, a posting ruled
out before, or a location the gate fails. Everything else is printed, never asked.

Nothing here cuts or scores. The readers are the ones the round already uses
(tools/text_screen.py for pay, years and sentences, tools/prefilter.py for the place,
tools/throttle.py for the tracker, the contact book and seen_jobs.json, which derives
each contact's status through tools/network/state.py); the contract reader is new,
because nothing read a posting's body for its terms. Posting text is untrusted: the
quotes here are shown to the person as evidence and never written above the fence of a
staged pick.

    python3 tools/posting_profile.py <posting.txt> --company C --role R [--location L]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from company_key import key  # noqa: E402
from dates import as_date  # noqa: E402

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18,
          "twenty-four": 24, "twenty four": 24}
_N = r"(\d{1,2}|" + "|".join(re.escape(w) for w in sorted(_WORDS, key=len, reverse=True)) + r")"
_MONTHS = ("january february march april may june july august september october november "
           "december").split()
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|" \
         r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"

# ------------------------------------------------------------------ terms

_NUMS = r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|eighteen|" \
        r"twenty[- ]four)"
FIXED = re.compile(
    r"\bfixed[- ]term\b|\bFTC\b|\btemporary (?:role|position|contract|assignment|post|job|"
    r"opportunity|vacancy)\b|\btemporary,? (?:full|part)[- ]time\b|\bon a temporary basis\b|"
    r"\btemp[- ]to[- ]perm\b|"
    # "A term position" is a fixed term; "a long-term position" is the opposite, a job
    # meant to last, so "term" counts only on its own. A short-term role is still one,
    # and a long-term contract is still a contract.
    r"(?<![-\w])(?<!long )(?<!medium )(?<!mid )term (?:position|role|post|appointment)\b|"
    r"\bterm contract\b|\bshort[- ]term (?:role|position|post|appointment|assignment|"
    r"placement|job)\b|"
    # Cover for someone's leave is a fixed term; a leave policy with "coverage" is a benefit
    # ("100% parental leave coverage for 6 months", "family coverage from day one").
    r"\b(?:maternity|paternity|parental)(?: leave)? (?:cover|replacement|contract)\b|"
    r"\bmat(?:ernity)? cover\b|\bto cover (?:a |an )?(?:maternity|paternity|parental) leave\b|"
    # A secondment the role IS, never one the employer offers its staff.
    r"\b(?:role|position|post|job|this) is (?:offered as |on )?(?:a )?secondment\b|"
    r"\b\d+[- ]month secondment\b|"
    # A duration is the job's only when it is said of the job: "Duration: 6 months" as a
    # line of its own, "assignment duration", "the duration of the contract is 6 months".
    # "Projects with a typical duration of 6 months" is the work, not the job.
    r"(?:^|[|\u2022\u00b7(]\s*|\b(?:contract|role|position|assignment|engagement|placement|"
    r"secondment|post|job|appointment)\s+)duration\s*[:\-\u2013]?\s*(?:is\s+|of\s+)?(?:about\s+|"
    r"approximately\s+)?" + _NUMS + r"\s+(?:months?|weeks?|years?)\b|"
    r"\bduration of (?:the |this |your )?(?:contract|role|position|assignment|engagement|"
    r"placement|secondment|post|job|appointment|cover)\W{0,3}\s*(?:is\s+|will be\s+|of\s+)?"
    r"(?:about\s+|approximately\s+|around\s+)?(?:\d{1,2}|" + _NUMS[3:-1] + r")\s*[- ]?"
    r"(?:months?|weeks?|years?)\b|"
    r"\b(?:on an interim basis|interim (?:role|position|basis|assignment|contract|post|appointment|"
    r"engagement))\b",
    re.I)
# A title that says how the job is held, not what it is: "Analyst (Contract)", "Analyst -
# Contract", "12 Month FTC", a maternity leave cover, an analyst contractor. A contract
# analyst, a manager of contracts or "Contract Pricing" holds a permanent job about
# contracts, so "contract" counts only standing alone at the end of a part of the title or
# in brackets.
TITLE_TERMS = re.compile(
    r"\bfixed[- ]term\b|\bFTC\b|\btemporary\b|\btemp\b|\b\d+[- ]months?\b|"
    # "Interim Finance Analyst" holds the job for a while; "Interim and Annual Reporting"
    # is the work, a company's half-year accounts.
    r"\binterim\b(?!\s*(?:and\b|&|/)|\s+(?:reporting|reports?|results|"
    r"accounts|financials?|statements?|close|audits?|dividends?|filings?|management "
    r"accounts)\b)|"
    r"\bmat(?:ernity)? cover\b|\b(?:maternity|paternity|parental)(?: leave)? cover\b|"
    r"\(\s*(?:contract|contractor|freelance)\s*\)|"
    r"[-\u2013|,]\s*(?:contract|contractor|freelance)\s*(?=$|[-\u2013|,(])|"
    r"\bcontractor\s*$|\bfreelance\b|\bcontract (?:role|position)\b", re.I)
CONTRACT = re.compile(
    r"\bcontract (?:role|position|basis|opportunity|assignment|engagement|job)\b|"
    r"\bcontract (?:length|duration|term|period)\W{0,3}\s*(?:is\s+|of\s+)?(?:about\s+|approximately\s+)?"
    + _NUMS + r"\b|"
    # "on a contract", "for a 6-month contract", never "for a contract research organisation".
    r"\b(?:on|for) a (?:\d+[- ]month )?contract(?=\s*(?:[.,;:)]|$|basis|role|position|"
    r"until|till|ending|lasting|running|of\s+\d|of\s+(?:one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve|eighteen)|for\s+\d|with\b))|"
    r"\b" + _N + r"[- ](?:month|week)s?(?:[- ]long)?\s+(?:contract|assignment|engagement)\b|"
    r"\b(?:initial|initially)\s+(?:\d+|" + _N[1:-1] + r")[- ]month (?:term|contract|period|assignment)\b|"
    # "Contract until June 2027" is the job's end; "every supplier contract until
    # signature" is the work. So the end has to be a date.
    r"\bcontract (?:until|till|through|ending(?: on| in)?|to|runs? (?:until|to|through))\s+"
    r"(?:(?:the )?end of\s+)?(?:" + _MONTH + r"(?=\s|$|[.,;])|\d{1,2}(?:st|nd|rd|th)?\s|\d{4}\b|"
    r"(?:the |this |next )?(?:financial|calendar|fiscal|academic|school) year\b|further notice\b|"
    r"(?:this|next) year\b)|"
    # IR35 as the engagement's status, never the work ("our IR35 compliance reviews",
    # "whether each contractor sits inside or outside IR35"). A day rate as pay, never a
    # product ("spot and day rate pricing").
    r"(?<!inside or )(?<!inside and )(?<!in or )\b(?:inside|outside) (?:of )?IR35\b(?!\s+(?:or|and)\b)|"
    r"\bIR35(?: status| determination| position)?\W{1,3}\s*(?:inside|outside)\b(?!\s+(?:or|and)\b)|"
    r"\bday rate\W{0,3}\s*(?:of\s+|is\s+|up to\s+|from\s+|between\s+|c\.?\s*|circa\s+|around\s+)*[£$€]?\s?\d|"
    r"\b(?:competitive|negotiable|attractive|excellent|market|daily) day rate\b|"
    r"\bday rate (?:negotiable|dependent|depending|DOE|available|on offer|paid)\b|"
    r"[£$€]\s?\d[\d,.]*\s?(?:k\s?)?(?:-|\u2013|to)?\s*(?:[£$€]\s?\d[\d,.]*\s?)?(?:per day|a day|/\s?day|p/?d)\b|"
    r"\bfreelance (?:role|engagement|basis|contract|work)\b|"
    r"\b(?:employment|job|position|contract|work) type\W{0,3}\s*(?:contract|contractor|"
    r"temporary|fixed[- ]term|freelance)\b|\bcontract[- ]to[- ](?:hire|perm\w*)\b|\bcontractor (?:role|position|basis)\b",
    re.I)
# A permanent job as a posting states it: "This is a permanent, full-time role",
# "Employment type: Permanent", the US "regular, full-time". Never "full-time" alone, which is
# hours ("Employment type: Full-time" beside "Duration: 6 months"), and never "permanent"
# in passing ("a permanent home for software teams"). Stated, it wins over a benefit, a
# secondment the employer offers, or a stray word elsewhere in the posting.
PERMANENT = re.compile(
    r"\b(?:is|as) a permanent\b|\bis permanent\b|\bpermanent,? (?:(?:full|part)[- ]time,? )?(?:role|position|post|"
    r"job|contract|opportunity|vacancy|appointment|employment|hire|basis)\b|"
    r"\b(?:employment|job|position|contract|work) type\W{0,3}\s*permanent\b|\bregular,? full[- ]time\b",
    re.I)
# "Could become permanent", "with a view to a permanent position": a contract that may be.
_MAYBE_PERMANENT = re.compile(r"\b(?:possib\w+|potential\w*|chance|opportunity|could|may|might|"
                              r"view to|lead to|leading to|becom\w+|convert\w*|extend\w*|"
                              r"temp[- ]to[- ]perm)\b", re.I)
# "This is not a contract role", "permanent, not fixed-term": a term named to be denied.
_DENIED = re.compile(r"\b(?:not|no|non)[- ](?:a |an )?(?:fixed[- ]term|contract|temporary)\b", re.I)
_DENIED_PERM = re.compile(r"\bnot (?:a )?permanent\b|\bnon[- ]permanent\b", re.I)
_DURATION = re.compile(r"\b" + _N + r"[- ](month|week|year)s?\b", re.I)
_ENDS = re.compile(
    r"\b(?:until|till|through|to|ending(?: on| in)?|ends?(?: on| in)?|end date\W{0,3}|"
    r"expected to end(?: on| in)?|finishing(?: on| in)?)\s+"
    r"((?:\d{1,2}(?:st|nd|rd|th)?\s+)?" + _MONTH + r",?\s+\d{4}|\d{4}-\d{2}-\d{2}|"
    + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})", re.I)
_IN_MONTHS = re.compile(r"\b(?:ending|ends|end|finishing|finishes|for(?: a period of)?|"
                        r"lasting|duration\W{0,3}|length\W{0,3})\s+(?:of\s+)?(?:about\s+|"
                        r"approximately\s+|around\s+)?(?:in\s+)?" + _N + r"\s+(month|week|year)s?\b",
                        re.I)
SHORT_MONTHS = 12


def _n(tok: str) -> int:
    t = tok.lower()
    return int(t) if t.isdigit() else _WORDS.get(t, 0)


def _months(n: int, unit: str) -> int:
    unit = unit.lower()
    if unit.startswith("week"):
        return max(1, round(n / 4.345))
    if unit.startswith("year"):
        return n * 12
    return n


def _date(text: str) -> dt.date | None:
    s = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", text.strip().rstrip(".,"))
    s = re.sub(r"\.", "", s).replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    d = as_date(s)
    if d:
        return d
    m = re.match(r"([A-Za-z]+) (\d{1,2}) (\d{4})$", s)      # "March 31 2027"
    if m:
        name = m.group(1).lower()
        month = next((i for i, x in enumerate(_MONTHS, 1) if x.startswith(name[:3])), 0)
        try:
            return dt.date(int(m.group(3)), month, int(m.group(2))) if month else None
        except ValueError:
            return None
    m = re.match(r"(\d{1,2}) ([A-Za-z]+) (\d{4})$", s)
    if m:
        month = next((i for i, x in enumerate(_MONTHS, 1) if x.startswith(m.group(2).lower()[:3])), 0)
        try:
            return dt.date(int(m.group(3)), month, int(m.group(1))) if month else None
        except ValueError:
            return None
    m = re.match(r"([A-Za-z]+) (\d{4})$", s)
    if m:
        month = next((i for i, x in enumerate(_MONTHS, 1) if x.startswith(m.group(1).lower()[:3])), 0)
        return dt.date(int(m.group(2)), month, 1) if month else None
    return None


def _sentences(text: str) -> list:
    import text_screen
    return text_screen.sentences(text or "")


def terms(text: str, title: str = "", today=None) -> dict:
    """{kind, months, ends, quote}: kind is "permanent", "fixed-term", "contract",
    "contract to hire" or "not stated"; months and ends only when the posting says."""
    today = today or dt.date.today()
    found = {"kind": "not stated", "months": None, "ends": None, "ends_about": None, "quote": ""}
    if TITLE_TERMS.search(title or "") and not _DENIED.search(title or ""):
        fixed = re.search(r"fixed|ftc|temp|month|cover|interim", TITLE_TERMS.search(title).group(0),
                          re.I)
        found.update(kind="fixed-term" if fixed else "contract", quote=title)
    title_said = found["kind"] != "not stated"
    stated = next((s for s in _sentences(text) if PERMANENT.search(s) and not _DENIED_PERM.search(s)
                   and not _MAYBE_PERMANENT.search(s) and not FIXED.search(s)
                   and not CONTRACT.search(s)), "")
    if stated and not title_said:
        found.update(kind="permanent", quote=stated[:220])
        return found
    for s in _sentences(text):
        if _DENIED.search(s):
            continue
        fixed, contract = FIXED.search(s), CONTRACT.search(s)
        if not (fixed or contract):
            continue
        if found["kind"] in ("not stated", "permanent") or not found["quote"] or found["quote"] == title:
            kind = "fixed-term" if fixed else "contract"
            if re.search(r"contract[- ]to[- ](?:hire|perm)", s, re.I):
                kind = "contract to hire"
            found.update(kind=kind, quote=s[:220])
        end = _ENDS.search(s)
        if end and not found["ends"]:
            d = _date(end.group(1))
            if d and d >= today - dt.timedelta(days=31):
                found["ends"] = d.isoformat()
        span = _IN_MONTHS.search(s) or _DURATION.search(s)
        if span and found["months"] is None:
            found["months"] = _months(_n(span.group(1)), span.group(2))
            # "Ending in four months" is counted from today; "a six-month contract" from
            # a start date the posting may not give, so only the first gives an end.
            if re.match(r"(?:ending|ends|end|finishing|finishes)\b", span.group(0), re.I) \
                    and not found["ends"]:
                found["ends_about"] = (today + dt.timedelta(days=round(found["months"] * 30.44))
                                       ).isoformat()
    if found["kind"] == "not stated":
        for s in _sentences(text):
            if PERMANENT.search(s) and not _DENIED_PERM.search(s):
                found.update(kind="permanent", quote=s[:220])
                break
    if found["ends"] and found["months"] is None:
        end = dt.date.fromisoformat(found["ends"])
        found["months"] = max(0, round((end - today).days / 30.44))
    return found


def wants_contracts() -> bool:
    """A person whose search accepts contracts (profile/search.py OPP_CONTRACT = None) is
    not asked about one. Everyone else wants a permanent role, as tools/opportunity.py
    assumes."""
    try:
        s = person.module("search")
    except Exception:
        return False
    return getattr(s, "OPP_CONTRACT", "unset") is None


# ------------------------------------------------------------------ pay

_US_STATES = ("alabama alaska arizona arkansas california colorado connecticut delaware florida "
              "georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine "
              "maryland massachusetts michigan minnesota mississippi missouri montana nebraska "
              "nevada ohio oklahoma oregon pennsylvania tennessee texas utah vermont virginia "
              "wisconsin wyoming").split()
_ELSEWHERE_WORDS = re.compile(
    r"\b(?:" + "|".join(_US_STATES) + r"|new york(?: city)?|nyc|new jersey|san francisco|"
    r"bay area|seattle|boston|chicago|los angeles|washington(?:,? d\.?c\.?)?|"
    r"united states|europe|european union|emea|apac|latam)\b", re.I)
_CURRENCIES = {"$": "USD or another dollar", "£": "GBP", "€": "EUR", "₹": "INR",
               "¥": "JPY"}
_CODES = re.compile(r"(?<![A-Za-z])(USD|CAD|GBP|EUR|AUD|NZD|INR|SGD|CHF|JPY)(?![A-Za-z])")
_AMOUNT = re.compile(r"\d[\d,.\s]*\d(?:\s?k)?|\d+\s?k\b", re.I)


def _names_home(s: str) -> bool:
    import places
    low = (s or "").lower()
    return bool(places.HOME_COUNTRY_RX.search(low)) or any(
        m and re.search(r"\b%s\b" % re.escape(str(m).lower()), low) for m in places.METRO)


# "£45,000 - £50,000 plus London weighting of £4,000": an allowance on top of the band,
# never the band's place. The band itself is the national one.
_ALLOWANCE = re.compile(r"\b(?:(?:inner|outer)\s+)?[\w-]+(?:\s+[\w-]+)?\s+(?:weighting|"
                        r"(?:location |cost[- ]of[- ]living |area )?allowance|supplement)\b", re.I)


def _names_metro(s: str) -> bool:
    import places
    low = (s or "").lower()
    return any(m and re.search(r"\b%s\b" % re.escape(str(m).lower()), low) for m in places.METRO)


def _elsewhere(s: str) -> str:
    """The place another than the person's own a pay sentence names, or ""."""
    s = _ALLOWANCE.sub(" ", s or "")
    if _names_home(s):
        return ""
    import places
    m = _ELSEWHERE_WORDS.search(s or "") or places.abroad_short(s or "")
    if m:
        return m.group(0)
    low = (s or "").lower()
    outside = list((places.LOCATION or {}).get("outside") or ())
    for c in list(places.OTHER_COUNTRIES) + [str(x).lower() for x in outside]:
        if c and re.search(r"\b%s\b" % re.escape(c), low):
            return c
    return ""


def _other_currency(s: str) -> str:
    """The currency a pay sentence states its figures in, when that is not the person's."""
    import text_screen as ts
    if ts.FOREIGN_CURRENCY.search(s):
        return ts.FOREIGN_CURRENCY.search(s).group(0)
    for code in _CODES.findall(s):
        if code != (ts.CODE or "").upper():
            return code
    for sym in _CURRENCIES:
        if sym != ts.CUR and re.search(re.escape(sym) + r"\s?\d", s):
            return sym
    return ""


_MONEY = r"[£$€]\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b"
_BAND = re.compile(r"(" + _MONEY + r")\s*(?:-|\u2013|\u2014|to)\s*([£$€]?\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b)")


def _money_value(tok: str) -> int | None:
    t = re.sub(r"[£$€,\s]", "", tok or "")
    k = t.lower().endswith("k")
    try:
        n = float(t[:-1] if k else t)
    except ValueError:
        return None
    return int(round(n * (1000 if k else 1)))


_GAP = re.compile(r"\s*(?:/|;|,?\s+(?:and|or|while|whereas|but)\b|,)\s*", re.I)


def _bands_in(sentence: str) -> list:
    """[(low, high, clause)] for each pay band a sentence states, each with the words
    around it: the clause that says where that band applies. The words between two
    bands are split where they break ("(London) / £40,000", "in London, and £40,000"),
    the first part the earlier band's and the rest the later one's, so "(London)" after
    the first band is never read as the place of the second."""
    sentence = sentence or ""
    found = list(_BAND.finditer(sentence))
    cuts = []
    for a, b in zip(found, found[1:]):
        gap = sentence[a.end():b.start()]
        brk = _GAP.search(gap)
        cuts.append(a.end() + (brk.start() if brk else 0))
    out = []
    for i, m in enumerate(found):
        start = cuts[i - 1] if i else 0
        end = cuts[i] if i < len(cuts) else len(sentence)
        lo, hi = _money_value(m.group(1)), _money_value(m.group(2))
        if lo and hi:
            out.append((lo, hi, sentence[start:end]))
    return out


def _standing(clause: str) -> int:
    """How surely a band is the person's own: 3 names their metro, 2 their region or
    country, 1 no place at all ("(national)"), 0 somewhere else."""
    if _elsewhere(clause):
        return 0
    bare = _ALLOWANCE.sub(" ", clause)
    if _names_metro(bare):
        return 3
    return 2 if _names_home(bare) else 1


def pay(text: str) -> dict:
    """{low, high, currency, quote, where}: where is "home", "elsewhere: <place>",
    "another currency: <code>" or "" when no pay is stated."""
    import text_screen as ts
    lo, hi, quote = ts.salary_range(text or "")
    cur = ts.CODE or ts.CUR
    if lo or hi:
        place = _elsewhere(quote)
        bands = [b + (_standing(b[2]),) for b in _bands_in(quote)]
        if place or len({b[3] for b in bands}) > 1:
            # "£40,000 to £48,000, or £52,000 to £60,000 for London-based colleagues": the
            # band with no other place beside it is the person's own, and the posting
            # does state pay for where they are. One that names their own city beats one
            # for the country ("(London) / (national)" for someone in London).
            best = max(bands, key=lambda b: b[3], default=None)
            if best and best[3]:
                return {"low": best[0], "high": best[1], "currency": cur, "quote": quote,
                        "where": "home"}
        return {"low": lo, "high": hi, "currency": cur, "quote": quote,
                "where": ("elsewhere: " + place) if place else "home"}
    for s in _sentences(text):
        if not ts.RANGE_CUE.search(s) or not _AMOUNT.search(s):
            continue
        other = _other_currency(s)
        if other:
            return {"low": None, "high": None, "currency": other, "quote": s[:220],
                    "where": "another currency: " + other}
    return {"low": None, "high": None, "currency": cur, "quote": "", "where": ""}


# ------------------------------------------------------------------ years, degree, place

def years(text: str) -> dict:
    import text_screen as ts
    low, high, quote = ts.entry_years(text or "")
    return {"asks": low, "highest": high, "held": ts.YEARS_HELD, "quote": quote}


_BACHELOR = re.compile(r"\b(?:bachelor['\u2019]?s?|b\.?sc|b\.?a\b|undergraduate degree|university degree|"
                       r"(?:a |an )?(?:relevant |related )?degree in)\b|\bb\.\s?[sa]\.", re.I)
_PHD = re.compile(r"\bph\.?\s?d\b|\bdoctora\w*", re.I)
_MASTER_WORD = r"(?:master|msc|m\.\s?sc|m\.\s?s\.|mba)"
_MASTER_OR = re.compile(r"\b" + _MASTER_WORD + r"[^;:]{0,140}?(?:\bor|/)\s*(?:an?\s+)?$", re.I)
_OR_MASTER = re.compile(r"^[^;:]{0,140}?(?:\bor\b|/)\s*(?:an?\s+)?" + _MASTER_WORD, re.I)


def degree(text: str) -> dict:
    """{level, required, equivalence, quote} for the highest degree a requirement asks."""
    import text_screen as ts
    best = {"level": "", "required": False, "equivalence": False, "quote": ""}
    rank = {"": 0, "a degree": 1, "a bachelor's degree": 1, "a master's degree": 2, "a PhD": 3}
    said = _sentences(text)
    for i, s in enumerate(said):
        level = ""
        # A graduate degree offered beside a bachelor's is no graduate bar: "Bachelor’s or
        # master’s degree" was read as a master's, required (2026-10-23).
        grads = [m for m in ts.DEGREE.finditer(s)
                 if not ts.NOT_A_DEGREE.match(s, m.start()) and not ts.beside_a_bachelor(s, m)]
        # A PhD offered beside a master's ("a Master's or PhD", "PhD or Master's") is a
        # master's bar.
        if any(_PHD.match(m.group(0)) and not _MASTER_OR.search(s[:m.start()])
               and not _OR_MASTER.search(s[m.end():]) for m in grads):
            level = "a PhD"
        elif grads:
            level = "a master's degree"
        elif _BACHELOR.search(s):
            level = ("a bachelor's degree"
                     if re.search(r"bachelor|b\.?sc|b\.?a\b|\bb\.\s?[sa]\.|undergraduate", s, re.I)
                     else "a degree")
        if not level or rank[level] < rank[best["level"]]:
            continue
        required = not ts.PREFERRED.search(s)
        if rank[level] == rank[best["level"]] and best["required"] and not required:
            continue
        # "In lieu" is read past the sentence: the splitter cuts at a semicolon, and "A
        # university degree; strong experience in lieu of one" is a route. Nothing else is:
        # "or related experience" in the next sentence is about the years asked there.
        after = said[i + 1][:150] if i + 1 < len(said) else ""
        best = {"level": level, "required": required,
                "equivalence": bool(ts.ESCAPE.search(s) or ts.DEGREE_ROUTE.search(s)
                                    or re.search(r"\bin lieu\b", after, re.I)),
                "quote": s[:220]}
    return best


_HYBRID = re.compile(r"\bhybrid\b|\b(?:\d|one|two|three|four) days? (?:a|per|each) week "
                     r"(?:in|at|from) (?:the |our )?office\b", re.I)
_REMOTE = re.compile(r"\b(?:fully |100% )?remote\b|\bwork from home\b|\bhome[- ]based\b", re.I)
_ONSITE = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b|\boffice[- ]based\b|\bin[- ]person\b", re.I)
_DAYS = re.compile(r"\b(\d|one|two|three|four|five) days? (?:a|per|each) week (?:in|at) "
                   r"(?:the |our )?(?:office|site)", re.I)


def where(row: dict, text: str) -> dict:
    """{location, mode, days, verdict, why}: the location gate's own verdict."""
    loc = str(row.get("location") or "").strip()
    mode = "not stated"
    body = text or ""
    for src in (loc, body):
        if _HYBRID.search(src):
            mode = "hybrid"
        elif _REMOTE.search(src) and not re.search(r"\bnot (?:a )?remote\b|\bno remote\b",
                                                    src, re.I):
            mode = "remote"
        elif _ONSITE.search(src):
            mode = "on-site"
        if mode != "not stated":
            break
    days = _DAYS.search(text or "")
    verdict, why = "", ""
    try:
        import prefilter
        verdict, why = prefilter.location_verdict(loc, str(row.get("title") or ""))
    except Exception:
        pass
    return {"location": loc, "mode": mode, "days": _n(days.group(1)) if days else None,
            "verdict": verdict, "why": why}


# ------------------------------------------------------------------ seen before, and the employer

def seen(row: dict, today=None, seen_path=None) -> dict:
    """{first_seen, days, repost, ruled_out}: what seen_jobs.json knows of this posting."""
    import throttle
    from lookup_score import norm
    # A caller may give the day as text ("2026-10-21"), as staging's own callers do.
    today = (today if isinstance(today, dt.date) else as_date(today, iso_only=True)) \
        or dt.date.today()
    try:
        entries = throttle.load_seen(seen_path or person.state("job_scraper", "seen_jobs.json"))["seen"]
    except (OSError, ValueError):
        entries = {}
    url = norm(row.get("url") or "")
    # The round's own reading of a relist (throttle.sightings), so staging says what the
    # round dated the posting as.
    own, other = [[d] if d else [] for d in (
        as_date(x, iso_only=True) for x in throttle.sightings(entries, today.isoformat())(row))]
    ruled = ""
    try:
        try:
            urls, pairs = throttle.ruled_out(entries, today.isoformat())
        except TypeError:                  # a stand-in written before it took the day
            urls, pairs = throttle.ruled_out(entries)
        ruled = urls.get(url, "") if url else ""
        ruled = ruled or throttle.ruled_pair(pairs, row)
    except Exception:
        ruled = ""
    first = min(own + other) if (own or other) else None
    repost = bool(other) and (not own or min(other) < min(own))
    return {"first_seen": first.isoformat() if first else "",
            "days": (today - first).days if first else None,
            "repost": repost, "ruled_out": ruled}


def employer(row: dict, rows=None, today=None, contacts_path=None) -> dict:
    """What is already running at this employer: applications by state, and the people.

    `rows` is the tracker as staging read it; the contact book is read through
    tools/throttle.py, which derives each contact's status from the message log."""
    import throttle
    today = today or dt.date.today()
    k = key(row.get("company"))
    if rows is None:
        import doc_name
        rows = doc_name.tracker_rows(person.state("job_search_tracker.csv"))
    out = {"open": [], "same_role": [], "drafts": [], "quiet": [], "closed": [],
           "referral": "", "replied": [], "waiting": []}
    for r in rows or []:
        if not k or key(r.get("company")) != k:
            continue
        status = str(r.get("status") or "").strip().lower()
        brief = {"role": str(r.get("role") or "").strip(), "date": str(r.get("date") or "").strip(),
                 "status": status}
        if throttle.same_title(r.get("role"), row.get("title")) and status not in throttle.UNSENT:
            out["same_role"].append(brief)
        elif status in throttle.UNSENT:
            out["drafts"].append(brief)
        elif status in throttle.FINAL:
            out["closed"].append(brief)
        elif throttle.is_silent(r, today):
            out["quiet"].append(brief)
        else:
            out["open"].append(brief)
    path = contacts_path or person.state("network_contacts.csv")
    try:
        out["referral"] = throttle.referral_holds(path).get(k, "")
        out["replied"] = [p["name"] for p in throttle.warm_routes(path).get(k, [])]
        out["waiting"] = [p["name"] for p in throttle.pending_outreach(path).get(k, [])]
    except Exception:          # an unreadable contact book never stops staging
        pass
    return out


# ------------------------------------------------------------------ the profile, its lines, its questions

def read(row: dict, text: str, rows=None, today=None, seen_path=None, contacts_path=None) -> dict:
    """The posting's profile: everything above, as data."""
    today = today or dt.date.today()
    return {"terms": terms(text, row.get("title") or "", today), "pay": pay(text),
            "years": years(text), "degree": degree(text), "where": where(row, text),
            "seen": seen(row, today, seen_path),
            "employer": employer(row, rows, today, contacts_path)}


def _money(n) -> str:
    return "{:,}".format(int(n)) if n else "?"


def _band(p: dict) -> str:
    if p.get("low") and p.get("high") and p["low"] != p["high"]:
        return "%s %s to %s" % (p["currency"], _money(p["low"]), _money(p["high"]))
    return "%s %s" % (p["currency"], _money(p.get("high") or p.get("low")))


_KIND = {"fixed-term": "fixed-term contract", "contract": "contract",
         "contract to hire": "contract to hire"}


def _length(t: dict) -> str:
    bits = []
    if t.get("months") is not None:
        bits.append("about %d month%s" % (t["months"], "" if t["months"] == 1 else "s"))
    if t.get("ends"):
        bits.append("ending %s" % t["ends"])
    elif t.get("ends_about"):
        bits.append("ending about %s" % t["ends_about"])
    return ", ".join(bits)


def _terms_text(t: dict) -> str:
    if t["kind"] in ("not stated", "permanent"):
        return t["kind"]
    return ", ".join(x for x in (_KIND.get(t["kind"], t["kind"]), _length(t)) if x)


# A quoted passage, and one cut short before its closing quote (a ruling keeps only its
# first 120 characters), with what introduces it: ': "Fluent Spanish required, ..."'.
_QUOTED = re.compile(r'\s*:?\s*["\u201c][^"\u201d]*(?:["\u201d]|$)')


def lines(prof: dict, quotes: bool = True) -> list:
    """The profile as a person reads it, one short line a property. With quotes=False,
    only what was derived (for above a staged pick's fence): no quote, no place and no
    reason that repeats the board's own words, which a location written as an instruction
    carried above the fence."""
    out = []
    t = prof["terms"]
    out.append("terms: " + _terms_text(t))
    p = prof["pay"]
    if not p["where"]:
        out.append("pay: not stated")
    elif p["where"] == "home":
        out.append("pay: %s" % _band(p))
    elif p["where"].startswith("elsewhere"):
        out.append("pay: %s, stated for %s, not for your area"
                   % (_band(p), p["where"][11:] if quotes else "another place"))
    else:
        out.append("pay: stated only in another currency (%s)" % p["currency"]
                   + (': "%s"' % p["quote"][:120] if quotes else ""))
    y = prof["years"]
    out.append("years: %s, you have %s" % ("asks %d+" % y["asks"] if y["asks"] else "none stated",
                                          y["held"]))
    d = prof["degree"]
    if d["level"]:
        out.append("degree: %s, %s%s" % (d["level"], "required" if d["required"] else "preferred",
                                         ", or equivalent experience" if d["equivalence"]
                                         else (", no equivalence route offered" if d["required"] else "")))
    else:
        out.append("degree: none stated")
    w = prof["where"]
    gate = ""
    if not quotes:
        gate = " [the location check: %s]" % w["verdict"] if w["verdict"] else ""
    elif w["verdict"] == "FLAG":
        gate = " [check: %s]" % _plain_why(w["why"])
    elif w["verdict"]:
        gate = " [%s: %s]" % (w["verdict"], _plain_why(w["why"]))
    place = (w["location"] or "no location given") if quotes else "as the row says"
    out.append("where: %s, %s%s%s" % (place, w["mode"],
                                      " (%d days a week in the office)" % w["days"] if w["days"] else "",
                                      gate))
    s = prof["seen"]
    if s["ruled_out"]:
        # A ruling quotes the sentence it rests on, and that is posting text: above a
        # staged pick's fence it is said without its quote.
        ruled = s["ruled_out"] if quotes else _QUOTED.sub("", s["ruled_out"]).strip(" :;")
        out.append("seen: ruled out before (%s)" % ruled)
    elif s["repost"]:
        out.append("seen: first seen %s (%d days ago) under another link: looks like a repost"
                   % (s["first_seen"], s["days"]))
    elif s["first_seen"]:
        out.append("seen: first seen %s (%d days ago)" % (s["first_seen"], s["days"]))
    else:
        out.append("seen: new to this search")
    e = prof["employer"]
    bits = []
    bits += ["you applied for this role on %s (status: %s)" % (a["date"] or "an unknown date",
                                                               a["status"])
             for a in e["same_role"]]
    bits += ["application in for %s (%s, %s)" % (a["role"], a["date"] or "undated", a["status"])
             for a in e["open"]]
    bits += ["applied for %s on %s, no reply since" % (a["role"], a["date"] or "an unknown date")
             for a in e["quiet"]]
    bits += ["an unsent draft for %s" % a["role"] for a in e["drafts"]]
    bits += ["closed: %s (%s)" % (a["role"], a["status"]) for a in e["closed"]]
    if e["referral"]:
        bits.append("a referral is in flight")
    if e["replied"]:
        bits.append("%s has replied to you: send it through them, not cold" % ", ".join(e["replied"]))
    if e["waiting"]:
        bits.append("messaged %s, no reply yet: applying is fine, a second message is not"
                    % ", ".join(e["waiting"]))
    out.append("employer: " + ("; ".join(bits) if bits else "no application or conversation on record"))
    return out


_SHORT_PLACES = {"nyc", "emea", "apac", "latam", "uk", "us", "usa", "eu", "uae", "dc"}


def _place(name: str) -> str:
    """A place as a person writes it: "London", "New York", "EMEA"."""
    return " ".join(w.upper() if w.lower().strip(".,") in _SHORT_PLACES else w[:1].upper() + w[1:]
                    for w in str(name or "").split())


def _plain_why(why: str) -> str:
    """The location gate's reason without the pipeline's own words ("Tier 2 decides")."""
    return re.sub(r";?\s*Tier \d+ decides\.?", "", str(why or "")).strip(" ;")


def questions(prof: dict, row: dict) -> list:
    """[{id, question}]: what the person is asked before this posting is drafted."""
    company, role = str(row.get("company") or "this employer"), str(row.get("title") or "this role")
    out = []
    t = prof["terms"]
    if t["kind"] in ("fixed-term", "contract") and not wants_contracts():
        length = _length(t)
        short = (t.get("months") is not None and t["months"] <= SHORT_MONTHS)
        out.append({"id": "contract", "question":
                    "%s at %s is a %s%s%s, the posting says. Do you still want it drafted?"
                    % (role, company, "short " if short else "", _KIND[t["kind"]],
                       " (%s)" % length if length else "")})
    p = prof["pay"]
    if p["where"].startswith("elsewhere"):
        out.append({"id": "pay_elsewhere", "question":
                    "The only pay %s states for %s is for %s (%s), not for where you are. "
                    "Do you still want it drafted?" % (company, role, _place(p["where"][11:]),
                                                        _band(p))})
    elif p["where"].startswith("another currency"):
        out.append({"id": "pay_elsewhere", "question":
                    "The only pay %s states for %s is in another currency (%s), so it may be "
                    "for another country. Do you still want it drafted?"
                    % (company, role, p["currency"])})
    e = prof["employer"]
    if e["same_role"]:
        a = e["same_role"][0]
        out.append({"id": "applied_before", "question":
                    "You applied for %s at %s on %s (status: %s). Do you want to apply again?"
                    % (role, company, a["date"] or "an unknown date", a["status"])})
    if e["open"]:
        a = e["open"][0]
        out.append({"id": "application_in", "question":
                    "You already have an application in at %s (%s, sent %s, status: %s). Do "
                    "you want a second one there?"
                    % (company, a["role"], a["date"] or "on an unknown date", a["status"])})
    if e["referral"]:
        who = e["referral"].split(". Do not apply cold")[0].replace("referral in progress: ", "")
        who = who.replace("the candidate's name", "your name").rstrip(".")
        out.append({"id": "referral", "question":
                    "%s. A cold application now would collide with it. Do you still want it "
                    "drafted?" % who})
    s = prof["seen"]
    if s["ruled_out"]:
        out.append({"id": "ruled_out", "question":
                    "%s at %s was ruled out before (%s). Do you still want it drafted?"
                    % (role, company, s["ruled_out"])})
    w = prof["where"]
    if w["verdict"] == "FAIL":
        out.append({"id": "location", "question":
                    "%s at %s is %s. Do you still want it drafted?" % (role, company,
                                                                         _plain_why(w["why"]))})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("posting_file")
    ap.add_argument("--company", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--location", default="")
    ap.add_argument("--url", default="")
    a = ap.parse_args(argv)
    with open(a.posting_file, encoding="utf-8") as fh:
        text = fh.read()
    row = {"company": a.company, "title": a.role, "location": a.location, "url": a.url}
    prof = read(row, text)
    print("\n".join(lines(prof)))
    for q in questions(prof, row):
        print("ASK: " + q["question"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
