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
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bar  # noqa: E402
from company_key import key  # noqa: E402
from lookup_score import norm  # noqa: E402

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

# Tracker statuses that close an application. `declined` is not in the canonical
# vocabulary (/outcome lists `rejected`, `offer_declined`, `withdrawn`) but it
# is in the tracker, and reading it as open would suppress that employer forever.
FINAL = {"hired", "rejected", "no_response", "no response", "offer_declined",
         "offer declined", "withdrawn", "declined"}

# Statuses where documents exist but nothing was sent. CLAUDE.md throttles on
# "a company with an open application" and sets the override against "what was
# already sent", and a draft is neither: an employer suppressed by a `drafted`
# row alone has every new role there hidden behind documents nobody ever
# submitted. A draft is worth knowing about,
# which is why it produces a note on the surfaced row rather than silence.
UNSENT = {"drafted", "draft", "in_progress", "in progress", "not_sent", "not sent"}

# The documented override: a role scoring this much higher than the open
# application is surfaced anyway, named explicitly. It was in CLAUDE.md and in
# no code, so the highest-scoring role of a run could be suppressed by a
# months-old application scoring thirty points below it.
OVERRIDE_POINTS = 10
# Skips that are re-evaluated on every run rather than treated as already-seen.
RE_EVALUATED = ("company throttle", "same-employer duplicate")

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
    r"|\bprefer(?:red|s)?\s+(?:a\s+)?(?:master|phd|doctora)", re.I)

# What still cuts, whatever else the reason says. Read first, because a reason
# routinely carries both: "scored 40. Core function is dashboard maintenance"
# is a role-shape cut that happens to quote a score.
#
# This is the part every search shares: the hard cuts the rules name, in the
# words this repo's own stages write. The person's own vocabulary (the
# language, the designations and the role families they will not do) is
# search.py's STILL_CUTS, and the two are one pattern.
_STILL_CUTS_CORE = (
    r"\bcitizen\w*|\bpermanent residen\w*|\bclearance\b"
    r"|\blanguage gate\b|\bprofessional credential\b"
    r"|\bresearch (?:ml|scientist|role)\b|\bml engineering or research\b"
    r"|\bduplicate\b|\bclosed\b|\bexpired\b|\bno longer (?:posted|listed|live)\b"
    r"|\brelocation\b|\bon-?site in\b|\blocation gate\b"
    # Blocker 10 in 10-triage-blockers.md, which is narrower than "the salary is
    # low" and is a real standing exclusion: a stated range whose *maximum* is
    # below the floor is the employer saying it will not pay the minimum. A
    # midpoint below the floor is the flag CLAUDE.md describes, and that one is
    # released above.
    r"|\bblocker 10\b|\brange tops out\b|\bwhole (?:stated )?range\b"
    r"|\bmaximum (?:is |sits )?below\b|\bentire range\b"
    # Blocker 1: a graduate degree stated as required with no equivalence route.
    r"|\bmaster'?s?\s+(?:degree\s+)?(?:is\s+)?(?:a\s+)?(?:must|required)\b"
    r"|\bstates a master'?s?\b|\brequires? a master'?s?\b|\bPhD required\b"
    # A reason that names a numbered blocker or the triage stage is citing
    # 10-triage-blockers.md, which is the current rule set and not an old one.
    # Those knockouts stand; what this releases is the weighted score that came
    # after them.
    r"|\btriage knockout\b|\bknockout at triage\b|\bblocker \d+\b"
    r"|\btier 1 pre-?filter\b|\bmechanical (?:screen|pre-?filter)\b"
    r"|\bfree.?text screen\b")
_STILL_CUTS = re.compile(
    "|".join([_STILL_CUTS_CORE, *getattr(person.module("search"), "STILL_CUTS", ())]),
    re.I)


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


def is_stale_exclusion(reason: str) -> bool:
    """Was this ruled out for something the current rules rank rather than cut?

    Order matters. A reason routinely carries both a score and a real cut, and
    the real cut wins: "scored 40. Core function is dashboard maintenance" is a
    deal-breaker the profile names, with a number attached.
    """
    text = str(reason or "")
    if _STILL_CUTS.search(text):
        return False
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
# terminal state. Nothing in the system ever writes `no_response`, because that
# requires somebody to notice silence and run /outcome, and silence is exactly
# what nobody notices. So most of the named target employers become
# permanently invisible to the search.
#
# Six weeks is the number because that is well past the point where a hiring
# process that is still alive would have said something, and comfortably past
# the "we'll be in touch in 2-3 weeks" that most of these rows were told.
SILENCE_DAYS = 45


def _row_age_days(row: dict, today: "dt.date | None" = None) -> int | None:
    """Days since the tracker row's date, or None when it cannot be read."""
    raw = (row.get("date") or "").strip()[:10]
    try:
        then = dt.date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return ((today or dt.date.today()) - then).days


def is_silent(row: dict, today: "dt.date | None" = None) -> bool:
    """A sent application with no reply recorded, old enough to presume dead.

    Deliberately does NOT rewrite the tracker. Marking a row `no_response` is a
    claim about the world that a person should make, and /outcome is where that
    happens. This only stops the row SUPPRESSING, which is a claim about this
    repo's own behaviour and is ours to make.
    """
    age = _row_age_days(row, today)
    return age is not None and age >= SILENCE_DAYS


def open_applications(path: str = TRACKER,
                      today: "dt.date | None" = None) -> dict[str, list[dict]]:
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
    for r in _tracker_rows(path):
        status = (r.get("status") or "").strip().lower()
        if status in FINAL or status in UNSENT:
            continue
        if is_silent(r, today):
            continue
        k = key(r.get("company"))
        if k:
            out.setdefault(k, []).append(r)
    return out


def silent_applications(path: str = TRACKER,
                        today: "dt.date | None" = None) -> dict[str, list[dict]]:
    """Employer key -> sent rows old enough to have stopped suppressing.

    The companion to `open_applications`. The shortlist row carries a note
    built from this, so a role resurfacing at an employer already applied to
    says so rather than looking like the throttle forgot.
    """
    out: dict[str, list[dict]] = {}
    for r in _tracker_rows(path):
        status = (r.get("status") or "").strip().lower()
        if status in FINAL or status in UNSENT or not is_silent(r, today):
            continue
        k = key(r.get("company"))
        if k:
            out.setdefault(k, []).append(r)
    return out


def drafted_applications(path: str = TRACKER) -> dict[str, dict]:
    """Employer key -> the first unsent draft there, for the note on the row."""
    out: dict[str, dict] = {}
    for r in _tracker_rows(path):
        if (r.get("status") or "").strip().lower() not in UNSENT:
            continue
        k = key(r.get("company"))
        if k and k not in out:
            out[k] = r
    return out


def _tracker_rows(path: str = TRACKER) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_seen(path: str = SEEN) -> dict:
    if not os.path.exists(path):
        return {"seen": {}}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        data = {"seen": {}}
    data.setdefault("seen", {})
    return data


def ruled_out(entries: dict) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """URL key -> reason and (title, employer key) -> reason for everything already ruled out."""
    urls: dict[str, str] = {}
    pairs: dict[tuple[str, str], str] = {}
    since = rescreen_since()
    for u, e in entries.items():
        if not isinstance(e, dict):
            continue
        status = (e.get("status") or "").lower()
        if status not in ("excluded", "skipped"):
            continue
        reason = (e.get("exclusion_reason") or e.get("skip_reason") or e.get("reason") or "")
        if status == "skipped" and reason.lower().startswith(RE_EVALUATED):
            continue
        # An entry with no reason recorded is not evidence of anything, and it
        # was blocking the posting forever AND blocking every future posting
        # sharing its (title, employer) pair. Entries in this state included the
        # closest domain matches in the whole corpus. A permanent exclusion has
        # to be able to say why.
        if not reason.strip():
            continue
        # Scored out under rules that no longer say to cut on a score. The entry
        # stays as the record; it just stops blocking, and the posting is ranked
        # again against the current scoring.
        if status == "excluded" and is_stale_exclusion(reason):
            continue
        if (status == "excluded" and since and screened_before(e, since)
                and not _NOT_A_VERDICT.search(reason)):
            continue
        why = f"{status} in seen_jobs.json: {reason[:120] or 'no reason recorded'}"
        n = norm(e.get("url") or u)
        if n:
            urls[n] = why
        t = (e.get("title") or "").strip().lower()
        k = key(e.get("company"))
        if t and k:
            pairs[(t, k)] = why
    return urls, pairs


def load_do_not_target(path: str = DO_NOT_TARGET, today: str = "") -> dict[str, str]:
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
    """
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
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


def expired_do_not_target(path: str = DO_NOT_TARGET, today: str = "") -> list[str]:
    """Entries whose review_after has passed, so the caller can say so."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
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

        with open(path, newline="", encoding="utf-8") as fh:
            threads = list(csv.DictReader(fh))
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
        try:
            with open(path, newline="") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            return {}
        live = _derived_statuses(rows)
    live = live or {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        if _status_of(r, live) not in statuses:
            continue
        k = key(r.get("company"))
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


def pending_outreach(path: str = CONTACTS) -> dict[str, list[dict]]:
    """Employer key -> the people there who were messaged and have not replied.

    Not a route, so it adds no points and suppresses nothing. It is the note
    that stops a second message going to somebody already sitting on a first.
    """
    return _contacts_by_employer(path, SENT_NO_REPLY)


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


_TITLE_NOISE = re.compile(r"[^a-z0-9]+")


def _same_title(a, b) -> bool:
    """Is this the role already applied to, under a spelling that drifted?

    Compared on letters and digits only, so "Sr. Analyst, Supply Chain" and
    "Senior Analyst, Supply Chain (Future Opportunities)" are not treated as two
    jobs by a comma. Seniority words are folded for the same reason.
    """
    def norm(x):
        x = _TITLE_NOISE.sub(" ", str(x or "").lower())
        x = re.sub(r"\b(sr|snr)\b", "senior", x)
        x = re.sub(r"\b(jr)\b", "junior", x)
        return " ".join(x.split())
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    return x == y or x.startswith(y) or y.startswith(x)


def _as_score(value) -> float | None:
    """A tracker `fit_rating` as a number, or None. It is hand-typed as "63/100"."""
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else None


def throttle(rows: list[dict], open_apps: dict[str, dict], urls: dict[str, str],
             pairs: dict[tuple[str, str], str], today: str,
             blocked: dict[str, str] | None = None,
             warm: dict[str, list[dict]] | None = None,
             drafted: dict[str, dict] | None = None,
             pending: dict[str, list[dict]] | None = None,
             holds: dict[str, str] | None = None,
             silent: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[dict]]:
    """Split ranked rows into surfaced and skipped. Order by priority, highest first."""
    rows = sorted(rows, key=lambda r: -(r.get("priority") or 0))
    kept, skipped = [], []
    surfaced: dict[str, dict] = {}
    for r in rows:
        k = key(r.get("company"))
        n = norm(r.get("url"))
        pair = ((r.get("title") or "").strip().lower(), k)
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
        elif pair in pairs:
            reason = f"already ruled out, {pairs[pair]}"
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
            if (same_role is None and sent is not None and here is not None
                    and here - sent >= OVERRIDE_POINTS):
                r = {**r, "throttle_override_note": (
                    "OVERRIDE: fit %d against %d for %s, already %s at this employer. "
                    "Surfaced because it clears the open application by %d points."
                    % (here, sent, best.get("role") or "?", best.get("status") or "?",
                       here - sent))}
            else:
                o = same_role or best
                why = ("the same role has already been applied to"
                       if same_role is not None
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


def write_back(path: str, data: dict, skipped: list[dict], today: str) -> int:
    """Record every throttle/duplicate skip in seen_jobs.json. Returns rows written."""
    entries = data.setdefault("seen", {})
    index = {norm(u): u for u in entries if norm(u)}
    n = 0
    for r in skipped:
        reason = r["skip_reason"]
        if reason.startswith("already ruled out"):
            continue  # it is already recorded; do not rewrite the original reason
        u = r.get("url")
        if not u:
            continue
        existing = index.get(norm(u))
        if existing is None:
            entries[u] = {
                "title": r.get("title"), "company": r.get("company"), "url": u,
                "first_seen": today, "posted_date": r.get("date") or None,
                "deadline": None, "portal": r.get("portal"), "source": "cli",
                "location": r.get("location"),
                "location_verdict": r.get("location_verdict"),
                "fit": r.get("fit"), "opportunity": r.get("opportunity"),
                "priority": r.get("priority"),
                "status": "skipped", "skip_reason": reason, "skipped_date": today,
            }
            index[norm(u)] = u
        else:
            e = entries[existing]
            # Never downgrade an application or a permanent exclusion to a skip.
            if (e.get("status") or "new") in ("new", "estimated", "skipped"):
                e["status"] = "skipped"
            e["skip_reason"] = reason
            e["skipped_date"] = today
        n += 1
    tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path) or ".",
                                      delete=False, encoding="utf-8", suffix=".tmp")
    with tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
    os.replace(tmp.name, path)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="fit.py output, every ranked row")
    ap.add_argument("--out", required=True, help="the shortlist: surfaced rows only")
    ap.add_argument("--skipped", help="the rows this stage removed, with reasons")
    ap.add_argument("--tracker", default=TRACKER)
    ap.add_argument("--seen", default=SEEN)
    ap.add_argument("--do-not-target", default=DO_NOT_TARGET)
    ap.add_argument("--contacts", default=CONTACTS)
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--no-write", action="store_true",
                    help="do not record skips in seen_jobs.json")
    a = ap.parse_args()

    data = json.load(open(a.infile))
    rows = list(data.values()) if isinstance(data, dict) else list(data)
    open_apps = open_applications(a.tracker)
    seen = load_seen(a.seen)
    urls, pairs = ruled_out(seen["seen"])
    blocked = load_do_not_target(a.do_not_target, a.today)
    warm = warm_routes(a.contacts)
    kept, skipped = throttle(rows, open_apps, urls, pairs, a.today, blocked, warm,
                             drafted_applications(a.tracker),
                             pending_outreach(a.contacts), referral_holds(a.contacts),
                             silent_applications(a.tracker))

    stale = expired_do_not_target(a.do_not_target, a.today)
    if stale:
        print("do_not_target entries past review_after, no longer suppressing: %s"
              % ", ".join(stale), file=sys.stderr)

    json.dump(kept, open(a.out, "w"), indent=1)
    if a.skipped:
        json.dump(skipped, open(a.skipped, "w"), indent=1)
    written = 0 if a.no_write else write_back(a.seen, seen, skipped, a.today)

    from collections import Counter
    kinds = Counter(r["skip_reason"].split(":")[0].split(",")[0] for r in skipped)
    print(f"{len(rows)} ranked -> {len(kept)} surfaced, {len(skipped)} skipped "
          f"({dict(kinds)}); {len(open_apps)} employers with an open application; "
          f"{len(blocked)} employers on do_not_target; "
          f"{written} skips recorded in seen_jobs.json", file=sys.stderr)
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
    raise SystemExit(main())
