#!/usr/bin/env python3
"""Company throttle, one-role-per-company and cross-run dedupe. Runs after fit.

## Why this exists

`.claude/skills/job-scraper/SKILL.md` Step 2.9 and Step 4.4 describe three
bookkeeping rules, and until this file existed none of them was code:

  company throttle     an employer with an open application is not surfaced
                       again; a second application in the same fortnight reads
                       as spray-and-pray to the recruiter reviewing both
  one role per company where a run turns up several roles at one employer,
                       only the highest scorer is surfaced
  already ruled out    a posting recorded as excluded (or gate-skipped) in
                       seen_jobs.json is never re-presented

Every skip is written back to seen_jobs.json with `status: "skipped"`, a
`skip_reason` and a `skipped_date`, so the next run can see why. Two kinds of
skip are re-evaluated every run rather than treated as permanent: a company
throttle lifts when the application closes, and a same-employer duplicate is
only a duplicate of what was surfaced that day. Everything else that is
excluded or skipped stays out.

Employer names are compared through `company_key.key` (so a legal name and
its short form are one employer) and URLs through `lookup_score.norm` (so
the two LinkedIn URL forms are one posting).

Usage:
    python3 tools/throttle.py ranked.json --out shortlist.json --skipped skipped.json
    python3 tools/throttle.py ranked.json --out shortlist.json --tracker t.csv --seen s.json --no-write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bar  # noqa: E402
from dates import as_date, days_since  # noqa: E402
from company_key import key, row_key  # noqa: E402
from lookup_score import norm  # noqa: E402
from text_screen import GATE_CUT_WORDS, pay_cut_top, ruling_refused  # noqa: E402

import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = person.state("job_search_tracker.csv")
SEEN = person.state("job_scraper", "seen_jobs.json")
DO_NOT_TARGET = person.state("job_scraper", "do_not_target.json")
CONTACTS = person.state("network_contacts.csv")
THREADS = person.state("network_threads.csv")

# Contact statuses that mean there is a live human route into this employer.
# not_contacted is deliberately absent: an identified name nobody has written to
# is a lead, not a route, and treating it as one would put "you have a referral"
# against a company where nothing has been said.
#
# A REPLY is what makes a route warm. `awaiting_reply` means a message went out
# and nothing came back, which is not a route, it is a message. A large share
# of any contact book sits there, and counting them warm printed "DO NOT APPLY
# COLD" over employers where nobody had said a word back, added the referral
# bonus to the fit score, and exempted the role from the fit floor on the
# strength of an InMail into the void.
RESPONDED = {"in_conversation", "replied_needs_response", "call_booked",
             "referral_in_progress"}

# Sent, nothing back. It changes nothing about whether to apply, and everything
# about whether to send a second message, so it rides along as its own note.
SENT_NO_REPLY = {"awaiting_reply", "connected_no_reply"}
# connected_no_reply belongs here, not in RESPONDED: accepting a request is
# not a reply, so applying to that employer is still cold and still fine.
# What it changes is the channel, not the warmth.

WARM = RESPONDED | SENT_NO_REPLY

# The one contact status that stops an application rather than annotating it.
# Somebody inside the employer has put the candidate's name forward, so a cold
# application lands as a second, worse record of the same person and spends the
# referral. The case it guards: a contact has passed the details to HR, and
# roles at that employer keep reaching the top of the shortlist anyway.
REFERRAL_IN_PROGRESS = "referral_in_progress"

# The tracker status vocabulary, the one copy in code: /outcome's "Tracker status
# vocabulary" block, and the spellings older trackers carry. what_works, followups,
# open_actions and network/state read these sets from here rather than restating them:
# a copy kept elsewhere is how open_actions once keyed on `interviewing` while the
# tracker wrote `interview`, and an employer mid-interview sorted below a booked call.
STATUSES = ("drafted", "applied", "interview", "offer", "hired", "rejected", "no_response",
            "offer_declined", "withdrawn")
# Older spellings of those, read as the same status everywhere and never written.
LEGACY_SPELLINGS = {"no response": "no_response", "offer declined": "offer_declined",
                    "interviewing": "interview"}


def _spellings(*canonical) -> frozenset:
    """The canonical statuses and every older spelling of them."""
    return frozenset(canonical) | {old for old, new in LEGACY_SPELLINGS.items()
                                   if new in canonical}


# Tracker statuses that close an application. `declined` is not in the canonical
# vocabulary (/outcome lists `rejected`, `offer_declined`, `withdrawn`) but it
# is in the tracker, and reading it as open would suppress that employer forever.
FINAL = set(_spellings("hired", "rejected", "no_response", "offer_declined", "withdrawn")
            | {"declined"})
# An interview or an offer running: a process, never silence.
LIVE_PROCESS = _spellings("interview", "offer")
# Reached an interview, whatever came after it; and closed without one.
REACHED_INTERVIEW = LIVE_PROCESS | _spellings("hired", "offer_declined")
LOST = _spellings("rejected", "no_response")

# Statuses where documents exist but nothing was sent. CLAUDE.md throttles on
# "a company with an open application" and sets the override against "what was
# already sent", and a draft is neither: an employer suppressed by a `drafted`
# row alone has every new role there hidden behind documents nobody ever
# submitted. A draft is worth knowing about,
# which is why it produces a note on the surfaced row rather than silence.
UNSENT = {"drafted", "draft", "in_progress", "in progress", "not_sent", "not sent"}

# A hiring process with no application in it (tools/interview_pack.py process): a referral
# that led to a recruiter's call, where applying through the portal as well would put a
# second, worse record of the same person in front of them. Its tracker row carries this
# in its notes. It is live at the employer like an application, but nothing was sent, so
# nothing counts it as one.
PROCESS_NOTE = "process, no portal application"


def is_process(row) -> bool:
    """Is this tracker row a hiring process with no application?"""
    return PROCESS_NOTE in str((row or {}).get("notes") or "")

# The documented override: a role scoring this much higher than the open
# application is surfaced anyway, named explicitly. It was in CLAUDE.md and in
# no code, so the highest-scoring role of a run could be suppressed by a
# months-old application scoring thirty points below it.
OVERRIDE_POINTS = 10
# Skips that are re-evaluated on every run rather than treated as already-seen.
# Every one is a reason throttle() derives afresh from live state each run (the
# tracker, the contact book, do_not_target.json, the profile's bar), so the copy
# written to seen_jobs.json is a record, never a verdict on the posting. Read as
# permanent, a referral hold kept blocking every posting it had touched after the
# referral had converted or lapsed: in one repo, 59 postings at one employer for a
# month. A do-not-target entry stopped suppressing at its review date and its
# skips went on suppressing for ever. Honoured for `excluded` entries too: a
# hand-written exclusion citing the company throttle is the same claim.
RE_EVALUATED = ("company throttle", "same-employer duplicate", "referral in progress",
                "do not target", "candidate's bar")

# A queue decision, not a verdict: the posting passed every gate and was never
# read, because the round ran out of slots or ranked it below a cut. Older rounds
# wrote these as skips, and each one blocked a posting nobody had judged.
QUEUE_DECISION = re.compile(
    r"\bnever (?:read|scored|evaluated)\b|\bnot (?:scored|read|ranked|evaluated)\b"
    r"|\bsurvived the (?:screen|prefilter)\b|\bpassed the prefilter\b"
    r"|\bqueue priority\b|\branked (?:below the [\w -]{0,20}cut|too low to (?:score|read))\b"
    r"|\b(?:affinity|scoring|reading) cut\b", re.I)

# Exclusion reasons that were true under an older set of rules and are not
# reasons any more. CLAUDE.md now says rank down, do not cut, and names the only
# four hard cuts: eligibility, language, a professional credential, and a role
# whose core is research ML. A score, a salary band and a preferred degree are
# scoring inputs, so an exclusion that cites one is a ranking decision that was
# written down as permanent.
#
# Many permanent exclusions in a long-lived seen_jobs.json say "scored 58,
# below the 60 pass bar" or the like, recorded before the gap penalty was
# rewritten: the same posting scores differently now, which is the entire
# reason a score cannot be a permanent verdict. Others cited a stated salary
# range or a preferred degree, both of which the current rules report and rank
# rather than cut.
#
# The entry is left exactly as it is. This only stops it blocking, so the record
# of what was decided and when survives, and the posting gets scored again.
_STALE_EXCLUSION = re.compile(
    r"\bfit\s*\d{1,3}\s*/\s*100"
    r"|\bscored?\s+\d{1,3}\b"
    r"|\bbelow the \d{1,3} pass bar\b"
    r"|\b(?:weak|moderate|poor) fit\b"
    r"|\bstated salary\b|\bsalary (?:range|band) below\b|\bbelow (?:the )?(?:walk-away )?floor\b"
    r"|\bprefer(?:red|s)?\s+(?:a\s+)?(?:master|phd|doctora)"
    r"|\b\d{1,2}\+?\s*(?:or more\s+)?years\b|\byears? bar\b", re.I)

# What still cuts, whatever else the reason says. Read first, because a reason
# routinely carries both: "scored 40. Core function is dashboard maintenance"
# is a role-shape cut that happens to quote a score.
#
# This is the part every search shares: the hard cuts the rules name, in the
# words this repo's own stages write. The person's own vocabulary (the
# language, the designations and the role families they will not do) is
# search.py's STILL_CUTS, and the two are one pattern.
_STILL_CUTS_CORE = (
    # Eligibility, a requirement to live elsewhere among it (text_screen's own
    # "eligibility gate: ..."), and a vacancy open to the employer's own staff.
    r"\bcitizen\w*|\bpermanent residen\w*|\bclearance\b|\beligibility gate\b"
    r"|\binternal workday site\b|\bemployer's own staff only\b"
    r"|\binternal (?:applicants?|candidates?|mobility)(?: only)?\b"
    # A language required, or a title in another language.
    r"|\blanguage gate\b|\b(?!degree\b|master|ph\.?d|years?\b)\w+ stated as a requirement\b"
    r"|\bjob title is in\b"
    r"|\bfluen\w* in\b|\bbilingual\b"
    # A professional credential.
    r"|\bprofessional (?:credential|designation|licen[cs]e)\b"
    r"|\b(?:accounting|engineering|actuarial) (?:licen[cs]e|designation|qualification|exams?)\b"
    # A different discipline: research ML, or the profile's own (search.py STILL_CUTS).
    r"|\bresearch (?:ml|scientist|role)\b|\bml engineering or research\b|\bresearch-grade ml\b"
    # Facts about the posting, not verdicts.
    r"|\bduplicate\b|\bclosed\b|\bexpired\b|\bno longer (?:posted|listed|live)\b")
# What is NOT here, deliberately: the name of the stage that wrote the reason
# ("knockout at triage", "blocker 2", "free text screen") and a years bar. A
# stage name is not a fact about the posting, and a years bar is a flag under
# the current rules: 83 years-bar exclusions in one real file, written when the
# card cut at 5+ years, kept blocking roles the current card and screen only
# rank lower. Released, such a posting goes through the current screen again,
# which cuts it again if it still cuts.
#
# Nor, any more, a degree, a pay range or a place by their wording alone. Today's
# screen ranks a stated degree, cuts a range only below the cut line and fails a
# place only by the location gate, and this list cut on all three by their words:
# "range tops out" matched the screen's own FLAG text for a range above the cut
# line, and every relocation or on-site reason blocked the same title at that
# employer whatever the gate now says. Each is judged as today's rules judge it,
# below.
#
# The screen's own gate cuts are read in the words it writes them in (text_screen
# GATE_CUT_WORDS, the profile's own eligibility wording among them), so a ruling the
# screen wrote is recognised as one whatever the profile calls its eligibility gate.
_STILL_CUTS = re.compile(
    "|".join([_STILL_CUTS_CORE, GATE_CUT_WORDS.pattern,
              *getattr(person.module("search"), "STILL_CUTS", ())]),
    re.I)
# A range below this is a different job level, the one pay cut today's screen makes
# (text_screen.py, search.py SALARY_CUT_BELOW).
SALARY_CUT_BELOW = getattr(person.module("search"), "SALARY_CUT_BELOW", 0) or 0
_RANGE_REASON = re.compile(r"\brange\b|\bsalary\b|\bpay\b|\bcompensation\b|\btops? out\b"
                           r"|\bfloor\b|\bcut line\b", re.I)
_MONEY = r"(\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?)\s?(k\b)?"
# A currency in front of a figure: a code ("GBP "), a symbol ("£", "€"), letters and a
# symbol ("C$", "CA$", "A$", "R$") or "kr". Read as only a code or one symbol, "C$32,000"
# and "kr 32 000" quoted no figure, and a ruling on one read as stale.
_MARK = r"(?:[A-Z]{3}\s?)?(?:[A-Za-z]{1,2}(?=[^\w\s])|kr\.?\s?)?[^\w\s]?\s?"
_TOP_CUE = re.compile(r"(?:tops? out at|range max(?:imum)?|max(?:imum)?(?: is| of| at)?|up to)"
                      r"\s*:?\s*" + _MARK + _MONEY, re.I)
_SPAN = re.compile(_MONEY + r"\s*(?:-|\u2013|to)\s*" + _MARK + _MONEY, re.I)
_LOCATION_REASON = re.compile(r"\brelocat\w*|\bon-?site\b|\blocation\b|\bcommut\w*"
                              r"|\bbased in\b|\boutside the\b", re.I)
_DEGREE_REASON = re.compile(r"\bmaster'?s?\b|\bph\.?\s?d\b|\bdoctora\w*|\bdegree\b", re.I)


def _amount(num: str, k: str | None) -> int:
    n = float(re.sub(r"[,\s]|\.(?=\d{3}\b)", "", num))
    return int(n * 1000) if k else int(n)


def range_top(reason: str) -> int | None:
    """The top of the pay range a reason quotes, or None when it cannot be told.

    The screen's own cut is read in the words it writes it in (text_screen.pay_cut_top),
    whatever the currency; any other wording by the cues below."""
    top = pay_cut_top(reason)
    if top is not None:
        return top
    m = _TOP_CUE.search(reason or "")
    if m:
        return _amount(m.group(1), m.group(2))
    m = _SPAN.search(reason or "")
    if m:
        return _amount(m.group(3), m.group(4) or m.group(2))
    return None


def _place_still_fails(entry: dict | None) -> bool:
    """Does the location gate still fail the place this entry recorded?"""
    loc = (entry or {}).get("location")
    if not loc:
        return False
    from prefilter import location_verdict
    return location_verdict(str(loc), str((entry or {}).get("title") or ""))[0] == "FAIL"


# Facts about a posting, not verdicts of a method: a better screen does not reopen them.
_NOT_A_VERDICT = re.compile(
    r"\bduplicate\b|\bclosed\b|\bexpired\b|\bno longer (?:posted|listed|live)\b"
    r"|\balready applied\b", re.I)


def rescreen_since() -> str:
    """The day screening last got better in a way that asks for a second look, or "".

    tools/build_versions.py versions the screening method. An exclusion written before
    a re-run version was decided by the older screen, so it stops blocking and the
    posting is screened again by the current one, in every repo, with nobody asking.
    """
    # Tests that pin how a ruling holds set LJS_RESCREEN=off: whether a better screen
    # re-judges it is tests/test_build_versions.py's question, and every real re-run
    # version would otherwise release the undated rulings their fixtures write.
    if os.environ.get("LJS_RESCREEN") == "off":
        return ""
    import build_versions
    return build_versions.last_rerun("screening")


def screened_before(entry: dict, since: str) -> bool:
    """Was this exclusion decided before `since`? Undated ones are older than any rule."""
    day = ""
    for k in ("excluded_date", "excluded_on", "date", "first_seen"):
        day = str(entry.get(k) or "")[:10]
        if day:
            break
    return not day or day < since


def is_stale_exclusion(reason: str, entry: dict | None = None) -> bool:
    """Was this ruled out for something the current rules rank rather than cut?

    An exclusion stands only while today's rules would still cut it. Order
    matters. A reason routinely carries both a score and a real cut, and the
    real cut wins: "scored 40. Core function is dashboard maintenance" is a
    deal-breaker the profile names, with a number attached. Then a pay reason
    stands only on a range topping out below the cut line, a place only where
    the location gate still fails the place the entry recorded (`entry`), and a
    degree never. First of all, a cut the screen wrote that today's screen refuses on
    the sentence it quotes is stale whatever words it shares with a real cut.
    """
    text = str(reason or "")
    if ruling_refused(text):
        return True
    if _STILL_CUTS.search(text):
        return False
    if _RANGE_REASON.search(text):
        top = range_top(text)
        return not (top is not None and top < SALARY_CUT_BELOW)
    if _LOCATION_REASON.search(text):
        return not _place_still_fails(entry)
    if _DEGREE_REASON.search(text):
        return True
    return bool(_STALE_EXCLUSION.search(text))


# How long a sent application goes without a recorded reply before it stops
# suppressing its employer.
#
# The repo already knows this shape. `is_stale_exclusion()` exists because a
# permanent exclusion is a DATED claim about a rule, and releases when the rule
# changes. An application is a dated claim too, and nobody applied that reading
# to it: a sent row with no terminal status suppressed its employer forever.
#
# It is not hypothetical: a tracker can hold dozens of sent rows and none in a
# terminal state. Nothing in the system wrote `no_response`, because that
# required somebody to notice silence and run /outcome, and silence is exactly
# what nobody notices. (The brief now closes them, `followups.close_quiet`, at
# the same number; this rule still covers any row it has not reached.) So most of the named target employers become
# permanently invisible to the search.
#
# Six weeks is the number because that is well past the point where a hiring
# process that is still alive would have said something, and comfortably past
# the "we'll be in touch in 2-3 weeks" that most of these rows were told.
SILENCE_DAYS = 45


def _row_age_days(row: dict, today: "dt.date | None" = None) -> int | None:
    """Days since the tracker row's date, or None when it cannot be read."""
    return days_since(row.get("date"), today, iso_only=True)


def is_silent(row: dict, today: "dt.date | None" = None) -> bool:
    """A sent application with no reply recorded, old enough to presume dead.

    Does NOT rewrite the tracker: this only stops the row SUPPRESSING, which is a
    claim about this repo's own behaviour. Closing the row as `no_response` is
    `followups.close_quiet`, which the brief runs and which notes the close on
    the row so the person sees it and can reverse it with /outcome.
    """
    # A live process is not silence, however long it has run: an interview loop
    # at a bank routinely passes six weeks, and a row at `interview` older than
    # SILENCE_DAYS stopped holding its employer back and was described as "never
    # heard back", inviting a cold application where the person was mid-interview.
    if str(row.get("status") or "").strip().lower() in LIVE_PROCESS:
        return False
    age = _row_age_days(row, today)
    return age is not None and age >= SILENCE_DAYS


def open_applications(path: str = TRACKER, today: "dt.date | None" = None,
                      rows: list[dict] | None = None) -> dict[str, list[dict]]:
    """Employer key -> every *sent*, still-live tracker row at that employer.

    Sent is the point. The throttle exists so the employer does not receive two
    applications in a week, and a draft sitting in `documents/` has not reached
    them.

    It used to keep only the first row per employer, which is the oldest and so
    routinely the weakest. With several applications at one employer the oldest
    represented them all, and every later role there cleared the 10-point
    override against a score nobody would have compared it to. The sharper
    failure was the row just sent: it could come back as the top result of the
    next run, hours after the application went, because the only row at that
    employer the throttle could see was a different application entirely.
    """
    out: dict[str, list[dict]] = {}
    for r in _tracker_rows(path) if rows is None else rows:
        status = (r.get("status") or "").strip().lower()
        if status in FINAL or status in UNSENT:
            continue
        if is_silent(r, today):
            continue
        k = key(r.get("company"))
        if k:
            out.setdefault(k, []).append(r)
    return out


def silent_applications(path: str = TRACKER, today: "dt.date | None" = None,
                        rows: list[dict] | None = None) -> dict[str, list[dict]]:
    """Employer key -> sent rows old enough to have stopped suppressing.

    The companion to `open_applications`. The shortlist row carries a note
    built from this, so a role resurfacing at an employer already applied to
    says so rather than looking like the throttle forgot.
    """
    out: dict[str, list[dict]] = {}
    for r in _tracker_rows(path) if rows is None else rows:
        status = (r.get("status") or "").strip().lower()
        if status in FINAL or status in UNSENT or not is_silent(r, today):
            continue
        k = key(r.get("company"))
        if k:
            out.setdefault(k, []).append(r)
    return out


def closed_applications(path: str = TRACKER,
                        rows: list[dict] | None = None) -> dict[str, list[dict]]:
    """Employer key -> every sent application there that has closed.

    A closed application does not hold its employer (other roles there are fair
    game), but the same role is the same job: a role applied to and closed as
    `no_response` came back as the top pick of the next two rounds.
    """
    out: dict[str, list[dict]] = {}
    for r in _tracker_rows(path) if rows is None else rows:
        status = (r.get("status") or "").strip().lower()
        if status in FINAL and status not in UNSENT:
            k = key(r.get("company"))
            if k:
                out.setdefault(k, []).append(r)
    return out


def drafted_applications(path: str = TRACKER,
                         rows: list[dict] | None = None) -> dict[str, dict]:
    """Employer key -> the first unsent draft there, for the note on the row."""
    out: dict[str, dict] = {}
    for r in _tracker_rows(path) if rows is None else rows:
        if (r.get("status") or "").strip().lower() not in UNSENT:
            continue
        k = key(r.get("company"))
        if k and k not in out:
            out[k] = r
    return out


def _tracker_rows(path: str = TRACKER) -> list[dict]:
    """The tracker's rows, [] when there is none, refused when a merge left conflict
    markers in it (csv_store.read_rows, the one state-file reader)."""
    import csv_store
    return csv_store.read_rows(path)


def _contact_rows(path: str = CONTACTS) -> list[dict]:
    """The contact book's rows, [] when there is none or it cannot be read.

    Read through csv_store like the tracker, so a contact book a merge left conflict
    markers in is refused rather than read: as rows, the three marker lines were three
    contacts and both sides of the conflicted row two more, and a warm route or a
    referral hold could rest on the side that lost."""
    import csv_store
    try:
        return csv_store.read_rows(path)
    except csv_store.Conflicted:
        raise
    except OSError:
        return []


def load_seen(path: str = SEEN) -> dict:
    if not os.path.exists(path):
        return {"seen": {}}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        data = {"seen": {}}
    data.setdefault("seen", {})
    return data


# The place of a ruling that recorded none: it holds for the title at that employer
# wherever it is posted, as every ruling did before the place was kept.
ANYWHERE = "*"


def ruled_out(entries: dict, today: str = "") -> tuple[dict[str, str],
                                                       dict[tuple[str, str, str], str]]:
    """URL key -> reason and (title, employer key, city) -> reason for everything already ruled out.

    The city is part of the key: a ruling on a place or a language in one city
    blocked the same title at that employer everywhere. Read it with `ruled_pair`.

    `today` is the round's day. Given it, a ruling holds for the same title at that
    employer and city only while the ruled posting was seen within RELIST_WINDOW days,
    the window in which the same title is that posting relisted (`_seen_index`); past
    it, the same title is more likely a new opening, and a new requisition months later
    was dropped on its predecessor's ruling before anything read its own body. A ruling
    on the posting's own address holds for good, and so does a pair ruled in the
    person's own words. Without `today`, every pair holds, as it always did.
    """
    urls: dict[str, str] = {}
    pairs: dict[tuple[str, str, str], str] = {}
    since = rescreen_since()
    now = as_date(today, iso_only=True) if today else None
    relist_since = (now - dt.timedelta(days=RELIST_WINDOW)).isoformat() if now else ""
    import exclude
    rules_now, parts_now = exclude.rules_fingerprint(), exclude.rules_parts()
    for u, e in entries.items():
        if not isinstance(e, dict):
            continue
        status = (e.get("status") or "").lower()
        if status not in ("excluded", "skipped"):
            continue
        reason = (e.get("exclusion_reason") or e.get("skip_reason") or e.get("reason") or "")
        if reason.lower().startswith(RE_EVALUATED) or QUEUE_DECISION.search(reason):
            continue
        # An entry with no reason recorded is not evidence of anything, and it
        # was blocking the posting forever AND blocking every future posting
        # sharing its (title, employer) pair. Entries in this state included the
        # closest domain matches in the whole corpus. A permanent exclusion has
        # to be able to say why.
        if not reason.strip():
            continue
        # The person's own call (tools/exclude.py --basis person) holds until they
        # lift it: no better screen and no rule change speaks for them.
        own_call = e.get("basis") == "person"
        # Resting on named parts of the person's own rules (a blocker row on their
        # triage card, one gate setting), it stands while those parts do: their card
        # is today's rule for it, and `exclude.holds` below lapses it the day the part
        # changes. Anything else is judged by its reason against today's rules.
        named = isinstance(e.get("rests_on"), dict) and bool(e.get("rests_on"))
        # A ruling the screen wrote that today's screen would not make, read on the
        # sentence it quotes (text_screen.ruling_refused): a second language named only
        # as a nice-to-have, or a nationality word, cut as a language requirement; home or
        # a time zone cut as somewhere else to live; a place ending one sentence joined to
        # the next and cut as a status. It rests on settings the person never changed, so
        # nothing else would ever lift it.
        if status == "excluded" and not own_call and ruling_refused(reason):
            continue
        # Scored out under rules that no longer say to cut on a score. The entry
        # stays as the record; it just stops blocking, and the posting is ranked
        # again against the current scoring. A skip whose reason is a score is the
        # same claim: "skipped" with "scored 58, below the 60 pass bar" blocked for good.
        if not own_call and not named and is_stale_exclusion(reason, e):
            continue
        if (status == "excluded" and not own_call and since and screened_before(e, since)
                and not _NOT_A_VERDICT.search(reason)):
            continue
        # Ruled out under the person's own screening rules, and what it rests on has
        # changed since: the one blocker or gate it names, or the whole rules when it
        # names none (tools/exclude.py). The ruling stays as the record and stops
        # blocking; the posting is screened again by the current rules when next found.
        if status == "excluded" and not own_call and not exclude.holds(e, rules_now, parts_now):
            continue
        why = f"{status} in seen_jobs.json: {reason[:120] or 'no reason recorded'}"
        n = norm(e.get("url") or u)
        if n:
            urls[n] = why
        t = title_key(e.get("title"))
        k = key(e.get("company"))
        days = _days_seen(e)
        if t and k and (own_call or not relist_since or not days or max(days) >= relist_since):
            pairs[(t, k, city(e["location"]) if e.get("location") else ANYWHERE)] = why
    return urls, pairs


def ruled_pair(pairs: dict, job: dict) -> str:
    """The reason a posting's title, employer and city were ruled out, or ""."""
    t, k, c = _posting_key(job.get("title"), job.get("company"), job.get("location"))
    if not (t and k):
        return ""
    return pairs.get((t, k, c)) or pairs.get((t, k, ANYWHERE)) or ""


# A posting's own date is the portal's, and a portal relisting a posting gives it a
# new one: LinkedIn's card shows the relist date, so a role first seen a month ago
# read as posted yesterday and earned the freshness bonus. So seen_jobs.json keeps
# the day this search first saw each posting, and a posting is as old as the
# earlier of the two. A relist often comes under a new URL too, so a posting with
# the same title, employer and city as one seen within this many days is that
# posting again; past it, the same title is more likely a new opening.
RELIST_WINDOW = 30

_CITY_NOISE = re.compile(r"\([^)]*\)|\b(?:hybrid|on[- ]?site|in[- ]office|remote|flexible)\b")
_SEEN_DAYS = ("first_seen", "excluded_date", "skipped_date", "rank_date", "last_seen")


def city(location) -> str:
    """The first place a location names, lower-cased: "Toronto, ON, Canada" is "toronto"."""
    low = _CITY_NOISE.sub(" ", str(location or "").lower())
    for part in re.split(r"[,|/;]|\s[-\u2013]\s", low):
        part = " ".join(part.split()).strip(" -")
        if part:
            return part
    return ""


def _posting_key(title, company, location) -> tuple[str, str, str]:
    return (title_key(title), key(company), city(location))


def _days_seen(e: dict) -> list[str]:
    """Every day an entry records the posting as seen, as ISO dates."""
    out = []
    for k in _SEEN_DAYS:
        d = as_date(e.get(k), iso_only=True)
        if d:
            out.append(d.isoformat())
    return out


def _seen_index(entries: dict, today: str = "") -> tuple[dict, dict]:
    """(normalised URL -> entry key, (title, employer, city) -> entry key).

    The second holds only postings seen within RELIST_WINDOW days of `today`, the
    one first seen earliest for each.
    """
    now = as_date(today, iso_only=True) or dt.date.today()
    since = (now - dt.timedelta(days=RELIST_WINDOW)).isoformat()
    urls: dict[str, str] = {}
    pairs: dict[tuple, str] = {}
    first: dict[str, str] = {}
    for u, e in entries.items():
        if not isinstance(e, dict):
            continue
        days = _days_seen(e)
        first[u] = min(days) if days else ""
        n = norm(e.get("url") or u)
        if n and n not in urls:
            urls[n] = u
        t, k, c = _posting_key(e.get("title"), e.get("company"), e.get("location"))
        if t and k and days and max(days) >= since:
            have = pairs.get((t, k, c))
            if have is None or (first[u] and (not first[have] or first[u] < first[have])):
                pairs[(t, k, c)] = u
    return urls, pairs


def _find(job: dict, urls: dict, pairs: dict) -> tuple[str | None, bool]:
    """(the entry key a posting matches, whether by URL)."""
    n = norm(job.get("url") or "")
    if n and n in urls:
        return urls[n], True
    hit = pairs.get(_posting_key(job.get("title"), job.get("company"), job.get("location")))
    return hit, False


def oldest_copies(rows: list, today: str = "") -> dict:
    """(title, employer, city) -> the oldest date any copy of that posting in `rows` carries.

    One round finds the same posting more than once: on an aggregator and on the
    employer's own board, or on two boards. The copies' dates differ, and the newest is
    often wrong: Ashby publishes no first-posted date, only when a posting was last
    published, so a role reposted yesterday after a month open reads as new there while
    its aggregator copy says a month. Every copy is as old as the oldest. Dates within
    RELIST_WINDOW days only, as for a relist: past it, the same title is more likely a
    new opening. The date of a copy is its own (`date` or `posted_date`), the day this
    search first saw it, or the day an alert sent it.
    """
    now = as_date(today, iso_only=True) or dt.date.today()
    since = (now - dt.timedelta(days=RELIST_WINDOW)).isoformat()
    out: dict = {}
    for job in rows:
        if not isinstance(job, dict):
            continue
        k = _posting_key(job.get("title"), job.get("company"), job.get("location"))
        if not (k[0] and k[1]):
            continue
        for field in ("date", "posted_date", "first_seen", "alert_date"):
            d = as_date(job.get(field), iso_only=True)
            if d is None:
                continue
            d = d.isoformat()
            if since <= d <= now.isoformat() and (k not in out or d < out[k]):
                out[k] = d
    return out


def copy_date(index: dict, job: dict) -> str:
    """The oldest date a copy of this posting carries in the round, from `oldest_copies`."""
    return index.get(_posting_key(job.get("title"), job.get("company"), job.get("location")), "")


def first_seen(entries: dict, today: str = "", index: tuple | None = None):
    """A function from a posting to the day this search first saw it, or "".

    By its URL, or as a relist of a posting with the same title, employer and city
    seen in the last RELIST_WINDOW days. The companion of `ruled_out`: both read
    seen_jobs.json and only what the scrape already has, so prefilter can age a
    posting before hydrate fetches it. `index` is `_seen_index(entries, today)`, for a
    caller that builds it once.
    """
    urls, pairs = _seen_index(entries, today) if index is None else index

    def of(job: dict) -> str:
        k, _ = _find(job, urls, pairs)
        days = _days_seen(entries[k]) if k is not None else []
        return min(days) if days else ""
    return of


def _read_do_not_target(path: str = DO_NOT_TARGET) -> dict | None:
    """do_not_target.json as read, or None when there is none or it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_do_not_target(path: str = DO_NOT_TARGET, today: str = "",
                       data: dict | None = None) -> dict[str, str]:
    """Employer key -> why no posting from them can be relevant.

    Different in kind from an excluded posting, and the distinction is the one
    CLAUDE.md draws: a posting that was scored and rejected excludes that
    posting, never the employer, because a different role there stays in scope.
    An entry in this file says something else, that the employer has no relevant
    presence for that function in that city at all. An office that is only
    sales has no role there to stay in scope.

    Entries expire. A company opening a team in that city is exactly the fact
    that goes stale, and the usual note on such an entry is "keep the
    relationship, revisit in a few months". An entry past its review_after is
    ignored and reported, rather than quietly suppressing an employer forever.
    `data` is the file as a caller already read it (`_read_do_not_target`).
    """
    data = _read_do_not_target(path) if data is None else data
    if not data:
        return {}
    today = today or dt.date.today().isoformat()
    out = {}
    for name, e in (data.get("companies") or {}).items():
        if not isinstance(e, dict):
            continue
        if (e.get("review_after") or "") and e["review_after"] < today:
            continue
        k = key(name)
        if k:
            out[k] = "do not target: %s (%s, recorded %s, review after %s)" % (
                e.get("reason", "no reason recorded")[:160],
                e.get("scope", "all"), e.get("recorded", "?"),
                e.get("review_after", "never"))
    return out


def expired_do_not_target(path: str = DO_NOT_TARGET, today: str = "",
                          data: dict | None = None) -> list[str]:
    """Entries whose review_after has passed, so the caller can say so."""
    data = _read_do_not_target(path) if data is None else data
    if not data:
        return []
    today = today or dt.date.today().isoformat()
    return sorted(n for n, e in (data.get("companies") or {}).items()
                  if isinstance(e, dict) and (e.get("review_after") or "")
                  and e["review_after"] < today)


def _status_of(row: dict, derived: dict[str, str]) -> str:
    """This contact's status, derived from the message log where the log knows.

    The documented premise of the networking layer is that "status is derived
    from the messages, never stored independently, so it cannot drift from the
    evidence". That was true of `state.py` and false here: this function read
    the stored column straight off network_contacts.csv, so the two disagreed
    precisely where the consequences are largest.

    One case it settles: a contact stored `connected_no_reply` with one inbound
    row in the log, an accepted connection request with no message in it. The
    derivation used to read that row as a reply and made the employer a warm
    route; it now reads it as what it is, so the stored row and the log agree
    that nobody there has written a word.
    The rule still stands for the case it guards: a reply the row has not
    caught up with is the unused-referral failure in `_contacts_by_employer`'s
    docstring, a live route invisible to the thing deciding whether an
    application is cold.

    Same move `prefilter.py` already makes when it imports `throttle.ruled_out`
    rather than reimplementing it, and on the same stated grounds: a second
    implementation of one rule drifts toward the wrong answer.
    """
    return derived.get(_contact_id(row)) or (row.get("status") or "").strip()


def _contact_id(row: dict) -> str:
    for col in ("contact_id", "id"):
        if row.get(col):
            return str(row[col]).strip()
    return ""


def threads_beside(contacts: str) -> str:
    """The message log that goes with a contact book: the repo's beside the repo's, and the
    `network_threads.csv` in the same folder beside any other. A contact book given on its
    own (--contacts) was read against the repo's own log, so its statuses were derived
    from somebody else's messages."""
    if not contacts or os.path.abspath(contacts) == os.path.abspath(CONTACTS):
        return THREADS
    return os.path.join(os.path.dirname(os.path.abspath(contacts)), "network_threads.csv")


def _derived_statuses(rows: list[dict],
                      threads_path: str | None = None) -> dict[str, str]:
    """{contact_id: effective_status}, or {} when the log cannot be read.

    Fails open to the stored column. The throttle runs inside every scrape, and
    a missing or malformed message log is a reason to fall back to what the row
    says, never a reason to stop a round.

    Imported lazily because `state` imports from this module at the top level,
    so a module-level import here would be circular.
    """
    path = threads_path or THREADS
    try:
        import collections

        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        from state import effective_status

        import csv_store
        if not os.path.exists(path):
            return {}
        try:
            threads = csv_store.read_rows(path)
        except csv_store.Conflicted as e:
            # The log is a reason to fall back to what the row says, never to stop a
            # round, and never something to read as messages with the markers in it.
            print(f"{e} Until then each contact's status is read from the contact "
                  "book's own column.", file=sys.stderr)
            return {}
        by_contact = collections.defaultdict(list)
        for row in threads:
            by_contact[str(row.get("contact_id") or "").strip()].append(row)
        out = {}
        for row in rows:
            cid = _contact_id(row)
            if not cid:
                continue
            try:
                out[cid] = effective_status(row, by_contact.get(cid, []))
            except Exception:          # one bad row must not blind the rest
                continue
        return out
    except Exception:
        return {}


def _contacts_by_employer(path: str, statuses: set, rows: list[dict] | None = None,
                          live: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """Employer key -> the live conversations already running there.

    The half of the join that was missing. A standing referral offer can sit
    unused: a scrape that surfaces a posting at that employer has no idea, and
    the cold application it produces spends the referral for nothing.

    This never suppresses. A warm route makes a posting MORE worth having, not
    less, and hiding it would lose the role to protect the referral. It rides
    along on the surfaced row so the draft step can use it.

    A caller already holding the contact book passes it as `rows`, with `live`
    its derived statuses ({contact_id: status}), instead of a path.
    `open_actions.build` does, so a referral hold that has to stop an
    application nudge is judged on the rows being rendered and not on a second
    read of the file, which a test's fixture never reaches.
    """
    if rows is None:
        rows = _contact_rows(path)
        if not rows:
            return {}
        live = _derived_statuses(rows, threads_beside(path))
    live = live or {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        if _status_of(r, live) not in statuses:
            continue
        k = row_key(r)
        if not k:
            continue
        out.setdefault(k, []).append({
            "name": (r.get("name") or "").strip(),
            "title": (r.get("title") or "").strip(),
            "status": _status_of(r, live),
            "next_action": (r.get("next_action") or "").strip(),
        })
    # Referral offers first: that is the one a drafter must not miss.
    order = {"referral_in_progress": 0, "call_booked": 1,
             "replied_needs_response": 2, "in_conversation": 3, "awaiting_reply": 4}
    for people in out.values():
        people.sort(key=lambda p: order.get(p["status"], 9))
    return out


def warm_routes(path: str = CONTACTS, rows: list[dict] | None = None,
                live: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """Employer key -> the people there who have actually replied."""
    return _contacts_by_employer(path, RESPONDED, rows, live)


def pending_outreach(path: str = CONTACTS, rows: list[dict] | None = None,
                     live: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """Employer key -> the people there who were messaged and have not replied.

    Not a route, so it adds no points and suppresses nothing. It is the note
    that stops a second message going to somebody already sitting on a first.
    """
    return _contacts_by_employer(path, SENT_NO_REPLY, rows, live)


def referral_holds(path: str = CONTACTS, rows: list[dict] | None = None,
                   live: dict[str, str] | None = None) -> dict[str, str]:
    """Employer key -> why no application may be sent there right now.

    An internal referral already in flight is the one case where applying makes
    things worse: the employer ends up with two records of the same candidate
    and the referral is the one that loses.
    """
    out: dict[str, str] = {}
    for k, people in _contacts_by_employer(path, {REFERRAL_IN_PROGRESS}, rows, live).items():
        p = people[0]
        who = p["name"] + (", %s" % p["title"] if p.get("title") else "")
        out[k] = ("referral in progress: %s has put the candidate's name forward here. "
                  "Do not apply cold; it would collide with the referral. %s"
                  % (who, p.get("next_action") or "")).strip()
    return out


# Everything in a title but its letters and digits, in any script.
_TITLE_NOISE = re.compile(r"[\W_]+")
# A bracket that says how or where a role is posted, not which role it is.
_TITLE_TAG = re.compile(
    r"\((?:future opportunities|evergreen|talent pool|remote|hybrid|on[- ]?site|"
    r"full[- ]time|permanent|[mfwd]/[mfwd]/[mfwd]|all genders)\)", re.I)


def title_key(title) -> str:
    """A title as the role it names: "Sr. Analyst, Supply Chain (Hybrid)" is
    "senior analyst supply chain".

    Letters and digits only, so a comma or a posting tag does not make two jobs, and
    seniority spellings folded. The one key for a title: the role already applied to
    (`_same_title`), a relist of a posting seen before (`first_seen`, the age gate),
    copies of one posting in a round, and a posting already ruled out (`ruled_pair`).
    Those three read the exact lower-cased title while the first folded, so "Senior
    Data Analyst (Hybrid)" and "Sr. Data Analyst" were new postings to the age gate and
    to a ruling on "Senior Data Analyst" at the same employer and city.
    """
    x = _TITLE_NOISE.sub(" ", _TITLE_TAG.sub(" ", str(title or "")).casefold())
    x = re.sub(r"\b(sr|snr)\b", "senior", x)
    x = re.sub(r"\b(jr)\b", "junior", x)
    return " ".join(x.split())


def _same_title(a, b) -> bool:
    """Is this the role already applied to, under a spelling that drifted?

    Compared by `title_key`. The whole title, never a prefix of it: "Data Analyst"
    closed matched "Data Analyst, Fraud Strategy", and a skip on a closed application
    is never looked at again, so the second role was blocked for good.
    """
    x = title_key(a)
    return bool(x) and x == title_key(b)


def same_title(a, b) -> bool:
    """`_same_title` under a public name: tools/posting_profile.py asks it at staging
    whether a pick is the role already applied to."""
    return _same_title(a, b)


def _as_score(value) -> float | None:
    """A tracker `fit_rating` as a number, or None. It is hand-typed as "63/100"."""
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else None


def throttle(rows: list[dict], open_apps: dict[str, dict], urls: dict[str, str],
             pairs: dict[tuple, str], today: str,
             blocked: dict[str, str] | None = None,
             warm: dict[str, list[dict]] | None = None,
             drafted: dict[str, dict] | None = None,
             pending: dict[str, list[dict]] | None = None,
             holds: dict[str, str] | None = None,
             silent: dict[str, list[dict]] | None = None,
             closed: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[dict]]:
    """Split ranked rows into surfaced and skipped. Order by priority, highest first."""
    rows = sorted(rows, key=lambda r: -(r.get("priority") or 0))
    kept, skipped = [], []
    surfaced: dict[str, dict] = {}
    for r in rows:
        k = key(r.get("company"))
        n = norm(r.get("url"))
        reason = None
        # The candidate's bar (tools/bar.py). Only its hard rules cut here: the
        # sectors and employers the profile excludes (search.py, BAR_*). Every
        # surviving row carries its verdict below, "none"
        # included, because failing pay, prestige and signal is a flag for the
        # person choosing, not a reason the pipeline may hide a role.
        verdict, verdict_why = bar.verdict(r.get("company"), r.get("desc") or "")
        if verdict == bar.EXCLUDED:
            reason = f"candidate's bar: {verdict_why}"
        elif blocked and k and k in blocked:
            reason = blocked[k]
        elif holds and k and k in holds:
            # The only contact state that stops an application instead of
            # annotating it. Everything else about a conversation is a note.
            reason = holds[k]
        elif n and n in urls:
            reason = f"already ruled out, {urls[n]}"
        elif (pair_why := ruled_pair(pairs, r)):
            reason = f"already ruled out, {pair_why}"
        elif k and closed and any(_same_title(r.get("title"), c.get("role"))
                                  for c in closed.get(k, [])):
            c = next(c for c in closed[k] if _same_title(r.get("title"), c.get("role")))
            done = ("already in a hiring process for this role, with no application, from"
                    if is_process(c) else "already applied to this role on")
            reason = (f"{done} {c.get('date') or 'an unrecorded date'} "
                      f"({c.get('status')}); a relisted posting is the same job")
        elif k and k in open_apps:
            opens = open_apps[k]
            if isinstance(opens, dict):      # one row, the shape this took before
                opens = [opens]
            # CLAUDE.md's override, which lived only in CLAUDE.md: a role
            # scoring OVERRIDE_POINTS higher than what was already sent is
            # surfaced anyway, named explicitly. Without it the best role of a
            # run could be suppressed by a months-old application scoring
            # thirty points below it. An open application with no score
            # recorded cannot be compared, so it throttles as before.
            #
            # Every open row at the employer is checked, not just one. The role
            # already applied to has to be recognised whichever of them it is,
            # and the override has to clear the BEST thing already sent: read
            # against the weakest, "materially better" means nothing.
            # Like for like: the tracker's `fit_rating` is the 0-100 fit, so the
            # new role is read by its fit too. It used to read `priority` (fit
            # times opportunity, uncapped), so a role at fit 86 cleared a sent 75
            # "by 22 points" when the honest margin was 11. Priority is only the
            # fallback for a row that never went through fit.py.
            here = _as_score(r.get("fit") if r.get("fit") is not None else r.get("priority"))
            # The override is for a MATERIALLY BETTER role, not a better score on
            # the role already sent. Re-scoring is routine: change the scorer and
            # yesterday's 79 is today's 94 with nothing about the job different.
            # A "Senior Analyst, Supply Chain (Future Opportunities)" role can
            # surface exactly that way, against an application already sent for
            # the same title, and the note would invite a duplicate application.
            same_role = next(
                (o for o in opens if _same_title(r.get("title"), o.get("role"))), None)
            best = max(opens, key=lambda o: (_as_score(o.get("fit_rating")) or -1))
            sent = _as_score(best.get("fit_rating"))
            # An unscored open row, or a live process, holds the employer as the
            # comment above says it does: the override is measured against what
            # was sent, and nothing can clear an application with no score or
            # an interview in progress.
            unscored = any(_as_score(o.get("fit_rating")) is None
                           or str(o.get("status") or "").lower() in LIVE_PROCESS for o in opens)
            if (same_role is None and sent is not None and here is not None and not unscored
                    and here - sent >= OVERRIDE_POINTS):
                r = {**r, "throttle_override_note": (
                    "OVERRIDE: fit %d against %d for %s, already %s at this employer. "
                    "Surfaced because it clears the open application by %d points."
                    % (here, sent, best.get("role") or "?", best.get("status") or "?",
                       here - sent))}
            else:
                o = same_role or best
                why = ("this role is already in a hiring process here, with no application"
                       if same_role is not None and is_process(same_role)
                       else "the same role has already been applied to"
                       if same_role is not None
                       else "a hiring process is already live at this employer"
                       if is_process(best)
                       else "an application is already open at this employer")
                reason = (f"company throttle: {why} "
                          f"({o.get('role') or '?'}, {o.get('status') or '?'}, "
                          f"{o.get('date') or '?'})")
        # Not part of the chain above. A row surfaced past the company throttle
        # still has to be deduplicated against the rest of the run, and while
        # this was an `elif` it never could be: any employer with an open
        # application took the branch before it. A role could come back twice
        # in one shortlist that way, both copies of a role already applied to.
        if reason is None and k and k in surfaced:
            s = surfaced[k]
            reason = (f"same-employer duplicate: {s.get('title')} scored higher this run "
                      f"({s.get('priority')} vs {r.get('priority')})")
        if reason:
            skipped.append({**r, "skip_reason": reason, "skipped_date": today})
        else:
            r = {**r, "bar": verdict, "bar_reason": verdict_why}
            if k:
                surfaced[k] = r
            quiet = (silent or {}).get(k) or []
            if quiet:
                # The employer was suppressed and is not any more. Say so, or
                # this reads as the throttle having forgotten an application.
                oldest = min(quiet, key=lambda x: x.get("date") or "9999")
                r = {**r, "silent_application_note": (
                    "APPLIED HERE ALREADY and never heard back: %s, %s. That one "
                    "stopped suppressing this employer after %d days of silence, "
                    "so this role is worth considering. Check before sending, and "
                    "run /outcome to close the old row out."
                    % (oldest.get("role") or "?", oldest.get("date") or "?",
                       SILENCE_DAYS))}
            draft = (drafted or {}).get(k)
            if draft:
                # A draft is not a reason to hide the employer, and it is a
                # reason to check before drafting again.
                r = {**r, "drafted_note": (
                    "DOCUMENTS ALREADY DRAFTED here and never sent: %s, %s. Send that one or "
                    "close it out before drafting another."
                    % (draft.get("role") or "?", draft.get("date") or "?"))}
            people = (warm or {}).get(k) or []
            if people:
                r = {**r, "warm_route": people,
                     "warm_route_note": "DO NOT APPLY COLD. %s" % "; ".join(
                         "%s (%s)%s" % (p["name"], p["status"],
                                        ": " + p["next_action"] if p["next_action"] else "")
                         for p in people[:3])}
            waiting = [q for q in ((pending or {}).get(k) or [])
                       if q["name"] not in {p["name"] for p in people}]
            if waiting:
                # Applying here is fine and always was. What is not fine is a
                # second message to somebody sitting on a first one.
                r = {**r, "outreach_pending": waiting,
                     "outreach_pending_note": (
                         "Applying is fine, this is not a warm route. A message is "
                         "already out and unanswered: %s. Do not send another."
                         % "; ".join("%s%s" % (q["name"],
                                               " (%s)" % q["title"] if q.get("title") else "")
                                     for q in waiting[:3]))}
            kept.append(r)
    return kept, skipped


# Statuses a round may move to "surfaced" or "skipped": what an earlier round or a
# hand-added backlog wrote. Never an application, a ranking or an exclusion.
_ROUND_STATUSES = ("new", "estimated", "skipped", "surfaced")


def _sighting(entries: dict, urls: dict, pairs: dict, r: dict, today: str) -> str | None:
    """The entry for this posting, made or found, with its first and last sighting.

    Found by URL, the entry's `first_seen` is kept and `last_seen` moves to today.
    Found as a relist under a new URL, a new entry starts from the first sighting
    of the old one. Not found, a new entry starts today. None for a row with no URL.
    """
    u = r.get("url")
    if not u:
        return None
    k, by_url = _find(r, urls, pairs)
    if k is not None and by_url:
        e = entries[k]
        days = _days_seen(e)
        e.setdefault("first_seen", min(days) if days else today)
        e["last_seen"] = today
        return k
    entry = {
        "title": r.get("title"), "company": r.get("company"), "url": u,
        "first_seen": today, "last_seen": today, "posted_date": r.get("date") or None,
        "deadline": None, "portal": r.get("portal"), "source": "cli",
        "location": r.get("location"), "location_verdict": r.get("location_verdict"),
        "fit": r.get("fit"), "opportunity": r.get("opportunity"),
        "priority": r.get("priority"), "status": "surfaced",
    }
    if k is not None:
        days = _days_seen(entries[k])
        entry["first_seen"] = min(days) if days else today
        entry["relisted_from"] = entries[k].get("url") or k
    entries[u] = entry
    n = norm(u)
    if n:
        urls[n] = u
    return u


def write_back(path: str, data: dict, skipped: list[dict], today: str,
               kept: list[dict] | tuple = (), index: tuple | None = None) -> int:
    """Record every skip, and when each posting was first and last seen. Returns skips written.

    Surfaced rows are recorded too, at status "surfaced", so the day a posting was
    first seen survives it being relisted. They are not "new": /rank reads "new" as
    a backlog added by hand. `index` is `_seen_index` of these entries on this day, for
    a caller that built it already; it is added to as postings are recorded.
    """
    entries = data.setdefault("seen", {})
    urls, pairs = _seen_index(entries, today) if index is None else index
    n = 0
    for r in skipped:
        reason = r["skip_reason"]
        k = _sighting(entries, urls, pairs, r, today)
        if k is None or reason.startswith("already ruled out"):
            continue  # it is already recorded; do not rewrite the original reason
        e = entries[k]
        # Never downgrade an application or a permanent exclusion to a skip.
        if (e.get("status") or "new") in _ROUND_STATUSES:
            e["status"] = "skipped"
        e["skip_reason"] = reason
        e["skipped_date"] = today
        n += 1
    for r in kept:
        k = _sighting(entries, urls, pairs, r, today)
        if k is None:
            continue
        e = entries[k]
        if (e.get("status") or "new") in _ROUND_STATUSES:
            e["status"] = "surfaced"
        r["first_seen"] = e.get("first_seen") or today
    tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path) or ".",
                                      delete=False, encoding="utf-8", suffix=".tmp")
    with tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
    os.replace(tmp.name, path)
    return n


# The kinds of skip, as their reasons open, for the count a round prints. The count was
# keyed on the reason up to its first colon or comma, so a reason with neither (an
# application already made to the same role) counted as a whole sentence of its own.
_SKIP_KINDS = re.compile(
    r"^(candidate's bar|do not target|referral in progress|already ruled out|"
    r"already applied to this role|already in a hiring process for this role|"
    r"company throttle|same-employer duplicate)\b", re.I)


def skip_kind(reason: str) -> str:
    """The kind of skip a reason records, in a few words."""
    text = str(reason or "").strip()
    m = _SKIP_KINDS.match(text)
    if m:
        return m.group(1)
    return re.split(r"[:;,(]", text, maxsplit=1)[0].strip()[:40] or "no reason"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="fit.py output, every ranked row")
    ap.add_argument("--out", required=True, help="the shortlist: surfaced rows only")
    ap.add_argument("--skipped", help="the rows this stage removed, with reasons")
    ap.add_argument("--tracker", default=TRACKER)
    ap.add_argument("--seen", default=SEEN)
    ap.add_argument("--do-not-target", default=DO_NOT_TARGET)
    ap.add_argument("--contacts", default=CONTACTS)
    ap.add_argument("--threads", default=None,
                    help="the message log contact statuses are derived from (default: the "
                         "network_threads.csv beside --contacts)")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--no-write", action="store_true",
                    help="do not record skips in seen_jobs.json")
    ap.add_argument("--keep-ruled-out", dest="keep_ruled_out", action="store_true",
                    help="skip nothing for a past ruling in seen_jobs.json, so everything "
                         "previously excluded is scored again (run_round.py --no-seen-read)")
    a = ap.parse_args()

    with open(a.infile, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = list(data.values()) if isinstance(data, dict) else list(data)
    # A posting that gives its employer's short name in brackets teaches the
    # join before any row is keyed, so "Long Name (LN)" and "LN" are one employer
    # for the one-role-per-employer rule, whichever comes first.
    import company_key
    company_key.learn(r.get("company") for r in rows)
    # Each state file read once, so every rule below judges the same snapshot of it:
    # the tracker was read eight times, the contact book and the message log three each.
    today = as_date(a.today, iso_only=True)
    tracker = _tracker_rows(a.tracker)
    contacts = _contact_rows(a.contacts)
    live = _derived_statuses(contacts, a.threads or threads_beside(a.contacts)) if contacts else {}
    dnt = _read_do_not_target(a.do_not_target) or {}
    open_apps = open_applications(a.tracker, today, rows=tracker)
    seen = load_seen(a.seen)
    # Re-judging everything was the point of --no-seen-read, and the prefilter
    # honoured it while this applied every past ruling at the end anyway, so a
    # round with the flag re-scored nothing.
    urls, pairs = ({}, {}) if a.keep_ruled_out else ruled_out(seen["seen"], a.today)
    blocked = load_do_not_target(a.do_not_target, a.today, data=dnt)
    warm = warm_routes(a.contacts, rows=contacts, live=live)
    kept, skipped = throttle(rows, open_apps, urls, pairs, a.today, blocked, warm,
                             drafted_applications(a.tracker, rows=tracker),
                             pending_outreach(a.contacts, rows=contacts, live=live),
                             referral_holds(a.contacts, rows=contacts, live=live),
                             silent_applications(a.tracker, today, rows=tracker),
                             closed_applications(a.tracker, rows=tracker))

    stale = expired_do_not_target(a.do_not_target, a.today, data=dnt)
    if stale:
        print("do_not_target entries past review_after, no longer suppressing: %s"
              % ", ".join(stale), file=sys.stderr)

    # The day each surfaced posting was first seen rides on the shortlist, so a
    # relisted posting reads as old there too.
    index = _seen_index(seen["seen"], a.today)
    seen_on = first_seen(seen["seen"], a.today, index=index)
    for r in kept:
        r["first_seen"] = seen_on(r) or a.today
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, indent=1)
    if a.skipped:
        with open(a.skipped, "w", encoding="utf-8") as fh:
            json.dump(skipped, fh, indent=1)
    written = 0 if a.no_write else write_back(a.seen, seen, skipped, a.today, kept,
                                              index=index)

    from collections import Counter
    kinds = Counter(skip_kind(r["skip_reason"]) for r in skipped)
    print(f"{len(rows)} ranked -> {len(kept)} surfaced, {len(skipped)} skipped "
          f"({dict(kinds)}); {len(open_apps)} employers with an open application; "
          f"{len(blocked)} employers on do_not_target; "
          f"{written} skips recorded in seen_jobs.json"
          + ("" if a.no_write else f", and when each of the {len(kept)} surfaced was first seen"),
          file=sys.stderr)
    n_warm = sum(1 for r in kept if r.get("warm_route"))
    if n_warm:
        print(f"{n_warm} surfaced roles have a live contact at that employer",
              file=sys.stderr)
    n_over = sum(1 for r in kept if r.get("throttle_override_note"))
    if n_over:
        print(f"{n_over} surfaced past the company throttle on the "
              f"{OVERRIDE_POINTS}-point override", file=sys.stderr)
    n_draft = sum(1 for r in kept if r.get("drafted_note"))
    if n_draft:
        print(f"{n_draft} are at employers with documents drafted and never sent",
              file=sys.stderr)
    for r in kept[:40]:
        print(f"  pri{r.get('priority', 0):>4} fit{r.get('fit', 0):>4} "
              f"{(r.get('company') or '')[:28]:28} {(r.get('title') or '')[:46]}")
        for note in ("warm_route_note", "throttle_override_note", "drafted_note",
                     "silent_application_note"):
            if r.get(note):
                print(f"        {r[note][:110]}")
    return 0


if __name__ == "__main__":
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:  # a merge left markers: say which file, read nothing
        print(f"throttle: {e}", file=sys.stderr)
        raise SystemExit(1) from None
