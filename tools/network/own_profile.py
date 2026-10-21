#!/usr/bin/env python3
"""The person's own LinkedIn profile, looked over now and then for what would stop
people replying: red flags only, never polish.

A stranger asked to connect reads the profile before accepting, and a recruiter reads it
beside the resume. What loses them is rarely the headline's length; it is a profile that
contradicts the resume, names the wrong city, shows a job that ended, lists a
certificate never earned, or says "open to work" to a current employer. So this checks
those things, mechanically, against the profile (profile/01-candidate-profile.md,
roles.py, person.json), and leaves judgement to the session's own model only when there
is some left, in a brief well under two thousand tokens.

It is not run every time. `due` is plain Python with no model call and prints nothing
when a look is not worth it, so every networking run can call it for free. It is due:

- once, when the profile has never been looked over;
- again when what it compares has changed since the last look (the current role, the
  earlier roles, where the person lives, their certifications, whether the search is
  confidential, or a newer copy of their LinkedIn profile);
- again when outreach is plainly not working: N first notes in a row unanswered past
  their nudge window, where N is the run that would happen by chance less than one time
  in twenty at the person's own reply rate (`tools/what_works.py`), or at a stated
  default until they have enough decided notes;
- and never more than once in CAP_DAYS, nor while their "no" stands
  (`tools/profile_upgrades.py --no own-profile-review`).

Where the profile comes from, in order: their LinkedIn export's Profile.csv,
Positions.csv, Education.csv, Skills.csv and Certifications.csv (`export.py`); else what
they paste, written by the session into the shape `shape` prints; or their own page
read in their own browser by the session, only where profile/networking.py PROFILE_READS
is "browser". Nothing here fetches linkedin.com, ever. Each look is kept in
documents/network/own_profile_review.json: the date, the source, what it compared, the
findings, their answers and what they decided. A finding they say they do not care
about is never raised again (`dismiss`, kept in profile/learned.json).

    python3 tools/network/own_profile.py due            # one line when worth a look, else nothing
    python3 tools/network/own_profile.py check [--from <zip|folder>] \\
        [--paste <file.json> --source paste|browser] [--dry-run]
    python3 tools/network/own_profile.py brief [--from ...] [--paste ...]
    python3 tools/network/own_profile.py answer photo|open-to-work yes|no
    python3 tools/network/own_profile.py dismiss <finding id> --said "<their words>"
    python3 tools/network/own_profile.py decide --said "<what they decided>" [--finding "..."]...
    python3 tools/network/own_profile.py shape          # the JSON a pasted profile is written into
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402
try:
    import export  # noqa: E402  (reads the profile through state.py when imported)
except person.NoProfile:   # the app itself: `due` is silent, every other command says so
    export = None

UID = "own-profile-review"
REVIEW = ("documents", "network", "own_profile_review.json")
# Never more often than this, whatever changed.
CAP_DAYS = 30
# A run of unanswered first notes is a signal when it would happen by chance less often
# than this at the person's own reply rate.
CHANCE = 0.05
# The reply rate assumed until the person has enough decided first notes of their own
# (what_works.MIN_GROUP). About one stranger in four accepted a request from a profile
# they read, in an experiment of 400 profiles and about 20,000 requests (an economics
# journal paper, 2025; uni-mannheim.de and zew.de). That is acceptance, and a reply is
# rarer, so with a lower true rate the trigger comes early: the cost is one look, at most
# once in CAP_DAYS. At 25% the run is 11, about a 4% chance on a sound profile.
DEFAULT_REPLY_RATE = 0.25
# A summary under this, with no description on a recent role, is a bare profile: in a
# study of 24,570 applications a bare one drew fewer callbacks than none at all (7.2%
# against 7.9%; 13.5% for a full one; resumego.net, a resume company's study, not peer
# reviewed).
THIN_SUMMARY_CHARS = 500
RECENT_YEARS = 3
# Dates more than this many months apart are a different story, not a typo.
DATE_SLACK_MONTHS = 1
BRIEF_MAX_CHARS = 6000
ASK = ("Want me to look over your own LinkedIn profile once, for anything that would stop "
       "people replying?")
ASK_AGAIN = ("Want me to look over your own LinkedIn profile again, for anything that would "
             "stop people replying?")
SOURCES = ("export", "paste", "browser")
# What `due` names when one of these changed since the last look.
PART_WORDS = {"role": "your current role", "roles": "your earlier roles",
              "location": "where you live", "certifications": "your certifications",
              "confidential": "whether your search is confidential",
              "export": "a newer copy of your LinkedIn profile"}
# The questions the export cannot answer, asked once each (yes or no).
QUESTIONS = {
    "photo": "Does your LinkedIn profile have a photo of you on it?",
    "open-to-work": "Is Open to Work on your LinkedIn profile switched on so that everyone "
                    "can see it (the green frame on your photo)?",
}


def _today(value=None) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)) if value else datetime.date.today()


def _h(value) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode("utf-8")) \
        .hexdigest()[:12]


def _plain(text) -> str:
    return " ".join(re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`",
                           lambda m: next(g for g in m.groups() if g is not None),
                           str(text or "")).split())


# ---------------------------------------------------------------- the record

def review_path() -> str:
    return person.state(*REVIEW)


def load_review() -> dict:
    try:
        with open(review_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    data.setdefault("reviews", [])
    data.setdefault("answers", {})
    data.setdefault("dismissed", [])
    return data


def save_review(data: dict) -> str:
    path = review_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    return path


def last_review(data: dict | None = None) -> dict | None:
    rows = [r for r in (data or load_review())["reviews"] if isinstance(r, dict) and r.get("date")]
    return max(rows, key=lambda r: r["date"]) if rows else None


# ---------------------------------------------------------------- what the profile says

def _md_text() -> str:
    try:
        path = person.file("candidate_profile", "01-candidate-profile.md")
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, person.NoProfile, KeyError):
        return ""


def _section(text: str, name: str) -> str:
    """The body of the first `##` or `###` heading that starts with `name`, any case."""
    out, inside = [], False
    for line in text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*?)\s*$", line)
        if m:
            if inside:
                break
            inside = m.group(2).strip().lower().startswith(name.lower())
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def roles() -> list:
    try:
        return list(getattr(person.module("roles"), "ROLES", None) or [])
    except Exception:  # noqa: BLE001  no profile, or a roles.py that will not load
        return []


def span(dates_text) -> tuple:
    """(start, end, current) of a role's dates, "Mar 2023 - Present": each (year, month)."""
    parts = re.split(r"\s+[-\u2013\u2014]\s+|\s+to\s+", str(dates_text or ""), maxsplit=1)
    start = export.month(parts[0]) if parts and parts[0].strip() else None
    tail = parts[1] if len(parts) > 1 else ""
    current = bool(re.search(r"\b(present|current|now|today|ongoing)\b", tail, re.I))
    return start, (None if current else export.month(tail)), current


def employed() -> bool:
    got = roles()
    return bool(got) and span(got[0].get("dates"))[2]


_CONFIDENTIAL = re.compile(r"\bconfidential(?:ly)?\b[^.\n]{0,60}\bsearch|\bsearch\w*[^.\n]{0,60}"
                           r"\bconfidential(?:ly)?\b", re.I)


def confidential() -> bool:
    """Does the profile say the search is confidential ("Searching confidentially")?"""
    if _CONFIDENTIAL.search(_md_text()):
        return True
    try:
        with open(person.path("CLAUDE.md"), encoding="utf-8") as fh:
            return bool(_CONFIDENTIAL.search(fh.read()))
    except (OSError, person.NoProfile):
        return False


_IN_PROGRESS = re.compile(r"\b(?:in progress|scheduled|rescheduled|studying|not yet|pending|"
                          r"expected|booked|working towards)\b", re.I)
_NOT_HELD = re.compile(r"\bnot\s+held\b|\bnever\s+(?:held|earned|passed|claimed|be listed|"
                       r"listed)\b|\bnot\s+(?:hold|earned|passed)\b|\bdo(?:es)? not hold\b", re.I)
_CERT_GENERIC = {"certified", "certification", "certificate", "cert", "exam", "the", "of", "in",
                 "and", "a", "an", "for", "credential", "badge", "programme", "program",
                 "course", "complete", "completed", "held"}


def _cert_name(bullet: str) -> str:
    text = _plain(bullet)
    # "Microsoft Certified: Power BI Data Analyst Associate (2024)": the colon is part of
    # the name, the dash or bracket after it is not.
    return re.split(r"\s+[-\u2013\u2014]\s+|\s*\(", text, maxsplit=1)[0].strip(" .")


def certifications() -> dict:
    """{"held", "in_progress", "not_held"} names, and "blocks": the profile's paragraphs
    that say something is not held, from 01-candidate-profile.md's Certifications section
    (roles.py CERTIFICATIONS where it has none)."""
    body = _section(_md_text(), "Certifications")
    held, progress, not_held = [], [], []
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if not m:
            continue
        name = _cert_name(m.group(1))
        if not name:
            continue
        (not_held if _NOT_HELD.search(m.group(1)) else
         progress if _IN_PROGRESS.search(m.group(1)) else held).append(name)
    if not body.strip():
        try:
            raw = str(getattr(person.module("roles"), "CERTIFICATIONS", "") or "")
        except Exception:  # noqa: BLE001
            raw = ""
        raw = raw.replace("\\textbullet{}", "|").replace("\\textbullet", "|")
        raw = re.sub(r"\\[A-Za-z]+(?:\{\})?|[{}]", "", raw)
        for item in re.split(r"[|;\u2022]", raw):
            item = item.strip()
            if item:
                name = re.split(r"\s*\(", item, maxsplit=1)[0].strip()
                (progress if _IN_PROGRESS.search(item) else held).append(name)
    blocks = [b for b in re.split(r"\n\s*\n", body) if _NOT_HELD.search(b)]
    return {"held": held, "in_progress": progress, "not_held": not_held, "blocks": blocks}


def _tokens(text) -> list:
    import state
    return re.findall(r"[a-z0-9]+", state._fold(str(text or "")).lower())


def _core(name) -> list:
    return [t for t in _tokens(name) if t not in _CERT_GENERIC and not re.fullmatch(r"(19|20)\d\d", t)]


def same_cert(a, b) -> bool:
    """One certificate under two spellings ("Microsoft Certified: Power BI Data Analyst
    Associate" and "Power BI Data Analyst Associate (PL-300)")."""
    x, y = set(_core(a)), set(_core(b))
    if not x or not y:
        return False
    both = x & y
    return (len(both) >= 2 or x == y) and len(both) / min(len(x), len(y)) >= 0.8


def _said_in(name, blocks) -> bool:
    """Is a certificate named, word for word near enough, in one of these paragraphs?"""
    want = list(dict.fromkeys(_core(name)))
    if len(want) < 2:
        return False
    for block in blocks:
        words = _tokens(block)
        width = len(want) + 3
        for i in range(max(1, len(words) - width + 1)):
            if set(want) <= set(words[i:i + width]):
                return True
    return False


def fact_parts() -> dict:
    """A hash of each part of the profile a look compares, so `due` can say which moved."""
    got = roles()
    cur = got[0] if got else {}
    try:
        certs_raw = str(getattr(person.module("roles"), "CERTIFICATIONS", "") or "")
    except Exception:  # noqa: BLE001
        certs_raw = ""
    md = _md_text()
    ident = {k: (person.get(f"identity.{k}", "") if person.exists("person.json") else "")
             for k in ("location", "area", "moved")}
    return {
        "role": _h([cur.get(k) for k in ("employer", "title", "dates")]),
        "roles": _h([[r.get(k) for k in ("employer", "title", "dates")] for r in got[1:]]),
        "location": _h([ident, re.findall(r"(?im)^\|\s*\**location\**\s*\|.*$", md)]),
        "certifications": _h([_section(md, "Certifications").strip(), certs_raw]),
        "confidential": _h(confidential()),
    }


def export_part(src=None) -> str:
    """A hash of the export's profile files, or "" when there are none to compare."""
    rows = {}
    for kind in export.GROUPS["profile"]:
        try:
            t = export.read(kind, src)
        except (OSError, ValueError):
            continue
        if t["usable"]:
            rows[kind] = t["rows"]
    return _h(rows) if rows else ""


# ---------------------------------------------------------------- is outreach working

def reply_rate(contacts, threads, today=None) -> tuple:
    """(p, decided first notes, "yours" or "default"): the person's own rate of first notes
    answered, as what_works.py counts it, once they have what_works.MIN_GROUP decided;
    DEFAULT_REPLY_RATE before that, or while none has been answered (a rate of nothing
    makes every run look like chance)."""
    import what_works
    openers = [c for c in what_works.message_cases(contacts, threads, today)
               if c["attempt"] == "opener"]
    won = sum(1 for c in openers if c["won"])
    if len(openers) >= what_works.MIN_GROUP and won:
        return won / len(openers), len(openers), "yours"
    return DEFAULT_REPLY_RATE, len(openers), "default"


def run_needed(p: float) -> int:
    """N = ceil(ln CHANCE / ln(1 - p)): the shortest run of unanswered notes that would
    happen by chance less than CHANCE of the time at reply rate p."""
    p = min(max(float(p), 1e-6), 0.999)
    return int(math.ceil(math.log(CHANCE) / math.log(1 - p)))


def unanswered_run(contacts, threads, today=None, since: str = "") -> int:
    """How many of the newest first notes, in a row, went unanswered past their nudge window.

    A first note counts once REPLY_WAIT_DAYS have passed since the last message to that
    person (the note, or its one nudge) with no reply: past the 5 to 7 business days a
    nudge waits for. Still inside that, it is neither answered nor not, and is skipped.
    Only notes sent after `since` (the last look) count, so one run is never put to the
    person twice."""
    import state
    import what_works
    today = _today(today)
    cases = what_works.message_cases(contacts, threads, today)
    won = {c["contact_id"] for c in cases if c["won"]}
    items = []
    for c in cases:
        if c["attempt"] != "opener" or (since and c["date"] and c["date"] <= since):
            continue
        replied = c["contact_id"] in won
        if not replied:
            outs = [state.as_date(r.get("date")) for r in state.threads_for(threads, c["contact_id"])
                    if state._direction(r) == "out" and not state.is_withdrawal(r)]
            outs = [d for d in outs if d]
            if outs and (today - max(outs)).days < what_works.REPLY_WAIT_DAYS:
                continue
        items.append((c["date"], replied))
    run = 0
    for _date, replied in sorted(items, reverse=True):
        if replied:
            break
        run += 1
    return run


# ---------------------------------------------------------------- due

def _standing_no(last: dict | None, today: datetime.date) -> bool:
    try:
        import profile_upgrades as U
        rec = U.asked().get(UID)
        if not rec:
            return False
        if last and str(rec.get("no", "")) < last["date"]:
            return False                       # a look after the no: it was a yes since
        u = U.by_id(UID)
        return U.again(UID, u.ask_version, u.changed, today) == ""
    except Exception:  # noqa: BLE001  no profile, or no such upgrade yet
        return False


def _load_state():
    """The contact book and log, read only: `due` never writes, and loading a file that is
    not there would create it."""
    import state
    if not (os.path.exists(state.CONTACTS_CSV) and os.path.exists(state.THREADS_CSV)):
        return [], []
    try:
        return state.load_contacts(), state.load_threads()
    except Exception:  # noqa: BLE001  a book that will not read is no reason to look
        return [], []


def due_reasons(today=None, contacts=None, threads=None, src=None) -> tuple:
    """("never" | "again" | "", [the reasons]). Nothing is printed or written."""
    if not person.exists():
        return "", []                          # the app itself: nobody's profile to look at
    today = _today(today)
    data = load_review()
    last = last_review(data)
    if _standing_no(last, today):
        return "", []
    if last is None:
        return "never", ["never looked over"]
    try:
        since = (today - datetime.date.fromisoformat(last["date"][:10])).days
    except ValueError:
        since = CAP_DAYS
    if since < CAP_DAYS:
        return "", []
    reasons = []
    old = last.get("hashes") or {}
    now = fact_parts()
    changed = [PART_WORDS[k] for k, v in now.items() if old.get(k) and v != old.get(k)]
    exp = export_part(src)
    if exp and exp != old.get("export"):
        changed.append(PART_WORDS["export"])
    if changed:
        reasons.append("changed since the last look: " + export._and(changed))
    if contacts is None or threads is None:
        contacts, threads = _load_state()
    p, decided, whose = reply_rate(contacts, threads, today)
    n = run_needed(p)
    run = unanswered_run(contacts, threads, today, since=last["date"][:10])
    if run >= n:
        rate = (f"your reply rate of {round(100 * p)}% from {decided} first notes" if whose == "yours"
                else f"the {round(100 * p)}% assumed until you have more answered first notes")
        reasons.append(f"your last {run} first notes went unanswered past their nudge window, "
                       f"which at {rate} happens by chance less than 1 time in "
                       f"{round(1 / CHANCE)}")
    return ("again" if reasons else ""), reasons


def due(today=None, contacts=None, threads=None, src=None) -> str:
    """One line when a look at their own profile is worth it, else "". Plain Python."""
    kind, reasons = due_reasons(today, contacts, threads, src)
    if not kind:
        return ""
    ask = ASK if kind == "never" else ASK_AGAIN
    return (f"Own LinkedIn profile: worth a look ({'; '.join(reasons)}). Ask once, at the end: "
            f"\"{ask}\" Yes: python3 tools/network/own_profile.py check. No: python3 "
            f"tools/profile_upgrades.py --no {UID}")


# ---------------------------------------------------------------- their profile, read

SHAPE = {
    "headline": "", "location": "", "summary": "",
    "positions": [{"company": "", "title": "", "started": "Mar 2023", "finished": "",
                   "description": "", "location": ""}],
    "education": [{"school": "", "degree": "", "start": "", "end": ""}],
    "certifications": [{"name": "", "authority": "", "started": ""}],
    "skills": [""],
}


def from_export(src=None) -> dict | None:
    """Their own profile from the export's files, or None when none is there."""
    t = {k: export.read(k, src) for k in export.GROUPS["profile"]}
    if not any(x["usable"] for x in t.values()):
        return None
    prof = t["profile"]["rows"][0] if t["profile"]["usable"] and t["profile"]["rows"] else {}
    return {
        "source": "export",
        "headline": str(prof.get("Headline") or "").strip(),
        "summary": str(prof.get("Summary") or "").strip(),
        "location": str(prof.get("Geo Location") or "").strip(),
        "positions": [{"company": r.get("Company Name", ""), "title": r.get("Title", ""),
                       "description": r.get("Description", ""), "location": r.get("Location", ""),
                       "started": r.get("Started On", ""), "finished": r.get("Finished On", "")}
                      for r in t["positions"]["rows"]],
        "education": [{"school": r.get("School Name", ""), "degree": r.get("Degree Name", ""),
                       "start": r.get("Start Date", ""), "end": r.get("End Date", "")}
                      for r in t["education"]["rows"]],
        "certifications": [{"name": r.get("Name", ""), "authority": r.get("Authority", ""),
                            "started": r.get("Started On", "")}
                           for r in t["certifications"]["rows"]],
        "skills": [r.get("Name", "") for r in t["skills"]["rows"] if r.get("Name")],
        "known": {"profile": t["profile"]["usable"], "location": t["profile"]["usable"]
                  and "Geo Location" not in t["profile"]["missing"],
                  "summary": t["profile"]["usable"] and "Summary" not in t["profile"]["missing"],
                  "positions": t["positions"]["usable"],
                  "descriptions": t["positions"]["usable"]
                  and "Description" not in t["positions"]["missing"],
                  "certifications": t["certifications"]["usable"],
                  "skills": t["skills"]["usable"]},
        "files": [x["file"] for x in t.values() if x["usable"]],
        "not_read": export.describe([x for x in t.values() if not x["usable"] or x["missing"]]),
    }


def from_paste(path: str, source: str = "paste") -> dict:
    """Their own profile as the session wrote a paste (or a read in their own browser)
    into SHAPE. A key left out is a part not seen, and is never checked."""
    if source not in ("paste", "browser"):
        raise ValueError("a pasted profile's source is paste or browser")
    if source == "browser":
        net = person.module("networking") if person.exists("networking.py") else None
        if str(getattr(net, "PROFILE_READS", "") or "") != "browser":
            raise ValueError("their own page is read in their browser only where "
                             "profile/networking.py PROFILE_READS is \"browser\"; otherwise "
                             "they paste it")
    with open(path, encoding="utf-8") as fh:
        got = json.load(fh)
    if not isinstance(got, dict):
        raise ValueError("the pasted profile is a JSON object in the shape `shape` prints")

    def rows(key, fields):
        return [{f: str((r or {}).get(f) or "") for f in fields}
                for r in got.get(key) or () if isinstance(r, dict)]
    return {
        "source": source,
        "headline": str(got.get("headline") or "").strip(),
        "summary": str(got.get("summary") or got.get("about") or "").strip(),
        "location": str(got.get("location") or "").strip(),
        "positions": rows("positions", ("company", "title", "description", "location",
                                        "started", "finished")),
        "education": rows("education", ("school", "degree", "start", "end")),
        "certifications": rows("certifications", ("name", "authority", "started")),
        "skills": [str(s) for s in got.get("skills") or () if str(s).strip()],
        "known": {"profile": True, "location": "location" in got,
                  "summary": "summary" in got or "about" in got,
                  "positions": "positions" in got,
                  "descriptions": any("description" in (r or {}) for r in got.get("positions") or ()),
                  "certifications": "certifications" in got, "skills": "skills" in got},
        "files": [os.path.basename(path)],
        "not_read": [f"no {k} in the paste" for k in ("location", "positions", "certifications")
                     if k not in got],
    }


# ---------------------------------------------------------------- the mechanical pass

_TITLE_SHORT = {"sr": "senior", "snr": "senior", "jr": "junior", "mgr": "manager",
                "eng": "engineer", "assoc": "associate", "dir": "director", "asst": "assistant",
                "&": "and"}
_SENIORITY = {"senior", "lead", "principal", "head", "chief", "director", "manager", "junior",
              "associate", "staff", "vp", "graduate", "intern", "assistant"}
_SEEKING = re.compile(
    r"#?open ?to ?work\b|\bopen to (?:new )?(?:roles?|opportunit\w+|offers|work)\b"
    r"|\bseeking (?:new |a new |my next |the next )?(?:roles?|opportunit\w+|position|work|"
    r"employment|challenge)\b|\blooking for (?:my next|a new|new|the next) (?:role|opportunit\w+|"
    r"position|challenge)\b|\bactively (?:looking|seeking)\b|\bavailable for (?:hire|work)\b"
    r"|\bjob ?seeker\b", re.I)


def _title_words(title) -> set:
    words = [_TITLE_SHORT.get(w, w) for w in _tokens(str(title or "").replace("&", " and "))]
    return {w for w in words if w not in ("the", "of", "a", "an")}


def same_title(a, b) -> bool:
    """One job title, near enough: most words shared and the same seniority words."""
    x, y = _title_words(a), _title_words(b)
    if not x or not y:
        return True                    # a blank is not a contradiction
    if (x & _SENIORITY) != (y & _SENIORITY):
        return False
    return len(x & y) / len(x | y) >= 0.5


def _months_apart(a, b) -> int | None:
    if a is None or b is None:
        return None
    if a[1] is None or b[1] is None:
        return 0 if a[0] == b[0] else abs(a[0] - b[0]) * 12
    return abs((a[0] * 12 + a[1]) - (b[0] * 12 + b[1]))


def _when(m) -> str:
    if m is None:
        return "no date"
    if m[1] is None:
        return str(m[0])
    return datetime.date(m[0], m[1], 1).strftime("%b %Y")


def _employer_names(role: dict) -> list:
    known = role.get("known_as") or ()
    known = [known] if isinstance(known, str) else list(known)
    return [role.get("employer", "")] + known


def _same_employer(company, role) -> bool:
    import discovery
    return any(discovery.same_employer(company, n) for n in _employer_names(role) if n)


def _finding(fid, what, evidence, fix) -> dict:
    return {"id": fid, "what": what, "evidence": evidence, "fix": fix}


def _verdict(place: str) -> tuple:
    try:
        import prefilter
        return prefilter.location_verdict(place)
    except Exception:  # noqa: BLE001  no search.py, or a gate that cannot load
        return "", ""


def _location(p) -> list:
    if not p["known"].get("location"):
        return []
    geo = p["location"]
    city = str(person.get("identity.location", "") or "")
    area = str(person.get("identity.area", "") or "")
    if not city:
        return []
    if not geo:
        return [_finding("location", "Your LinkedIn profile names no location.",
                         "location: empty",
                         f"Set it to {city}: recruiters search by place, and a profile with no "
                         "place is in none of those searches.")]
    verdict, why = _verdict(geo)
    named = any(w and w.lower() in geo.lower()
                for w in (city.split(",")[0].strip(), area.split(",")[0].strip()))
    if verdict == "FAIL" or (verdict != "PASS" and not named):
        return [_finding("location", f"Your LinkedIn profile says you are in {geo}; your profile "
                         f"says you live in {city}" + (f" ({why})." if why else "."),
                         f"location: \"{geo}\"",
                         f"Set it to {city}, so a search for people there finds you and a "
                         "reader is not left wondering where you are.")]
    return []


def _never_said(p) -> list:
    import learned
    text = "\n".join((p["headline"], p["summary"], p["location"]))
    found = list(dict.fromkeys(learned.dislikes(text)))
    if not found:
        return []
    quoted = ", ".join(f"\"{w}\"" for w in found[:4])
    return [_finding("never-say", f"Your LinkedIn profile says {quoted}, wording you have said "
                     "never to use.", f"headline, about or location: {quoted}",
                     "Take it out there too: a reader who sees it on your profile hears it in "
                     "every note you send.")]


def _roles(p, today) -> list:
    """The current role, and each role in the resume's span against LinkedIn's."""
    if not p["known"].get("positions"):
        return []
    mine = roles()
    if not mine:
        return []
    out = []
    linked = [dict(x, _start=export.month(x.get("started")), _end=export.month(x.get("finished")),
                   _current=not str(x.get("finished") or "").strip()) for x in p["positions"]
              if str(x.get("company") or x.get("title") or "").strip()]
    first, *_rest = mine
    start0, _end0, current0 = span(first.get("dates"))
    if current0:
        now = [x for x in linked if x["_current"]]
        if not now:
            out.append(_finding("current-role", "Your LinkedIn profile shows no current job; "
                                f"you work at {first.get('employer')} as {first.get('title')}.",
                                "every position has an end date",
                                f"Add {first.get('title')} at {first.get('employer')}, from "
                                f"{_when(start0)}: a profile with no current job reads as out "
                                "of work, and a recruiter compares it with the resume."))
        elif not any(_same_employer(x["company"], first) for x in now):
            shown = "; ".join(f"{x['title']} at {x['company']}" for x in now[:2])
            out.append(_finding("current-role", f"Your LinkedIn profile shows {shown} as your "
                                f"current job; your profile says {first.get('title')} at "
                                f"{first.get('employer')}.",
                                f"current position: {shown}",
                                f"Add {first.get('title')} at {first.get('employer')}, from "
                                f"{_when(start0)}, and end the one that finished."))
    earliest = min((s for s in (span(r.get("dates"))[0] for r in mine) if s), default=None)
    flagged_current = any(f["id"] == "current-role" for f in out)
    for i, role in enumerate(mine):
        start, end, current = span(role.get("dates"))
        theirs = [x for x in linked if x["company"] and _same_employer(x["company"], role)]
        key = re.sub(r"[^a-z0-9]+", "-", str(role.get("employer", "")).lower()).strip("-")
        fid = f"role:{key}"
        if not theirs:
            if i == 0 and flagged_current:
                continue
            out.append(_finding(fid, f"{role.get('title')} at {role.get('employer')} "
                                f"({role.get('dates')}) is on your resume and not on LinkedIn.",
                                "no position at that employer",
                                "Add it with the same title and dates: a recruiter who finds a "
                                "job on one and not the other asks which is true."))
            continue
        problems = []
        if not any(same_title(x["title"], role.get("title")) for x in theirs):
            problems.append(f"the title is \"{theirs[0]['title']}\" there and "
                            f"\"{role.get('title')}\" on your resume")
        first_start = min((x["_start"] for x in theirs if x["_start"]), default=None)
        gap = _months_apart(first_start, start)
        if gap is not None and gap > DATE_SLACK_MONTHS:
            problems.append(f"it starts {_when(first_start)} there and {_when(start)} on your "
                            "resume")
        still = any(x["_current"] for x in theirs)
        if current and not still and not (i == 0 and flagged_current):
            problems.append("LinkedIn shows it ended; your resume says you are still there")
        elif not current and still:
            problems.append(f"LinkedIn still shows it as your current job; your resume says it "
                            f"ended {_when(end)}")
        elif not current and end:
            last_end = max((x["_end"] for x in theirs if x["_end"]), default=None)
            gap = _months_apart(last_end, end)
            if gap is not None and gap > DATE_SLACK_MONTHS:
                problems.append(f"it ends {_when(last_end)} there and {_when(end)} on your resume")
        if problems:
            out.append(_finding(fid, f"{role.get('employer')}: " + "; ".join(problems) + ".",
                                "; ".join(f"{x['title']} at {x['company']}, "
                                          f"{x.get('started') or '?'} to "
                                          f"{x.get('finished') or 'present'}" for x in theirs),
                                "Make the two say the same: titles and dates are what a reader "
                                "checks first, and a mismatch reads as one of them being untrue."))
    # A role on LinkedIn, inside the resume's years, that the profile does not know at all.
    if earliest:
        known = " ".join(_md_text().splitlines())
        for x in linked:
            if any(_same_employer(x["company"], r) for r in mine) or not x["company"]:
                continue
            end = x["_end"] or (today.year, today.month)
            if (end[0], end[1] or 12) < (earliest[0], earliest[1] or 1):
                continue                       # over before the resume's years begin
            if x["company"].lower() in known.lower():
                continue                       # Reserve Experience and the like: known, kept off
            ck = re.sub(r"[^a-z0-9]+", "-", x["company"].lower()).strip("-")
            out.append(_finding(f"role-extra:{ck}", f"LinkedIn lists {x['title']} at "
                                f"{x['company']} ({x.get('started') or '?'} to "
                                f"{x.get('finished') or 'present'}), which your profile does "
                                "not have.", f"position: {x['title']} at {x['company']}",
                                "Either it belongs in your profile (tell me, and I add it), or "
                                "it comes off LinkedIn: one story on both."))
    return out


def _certs(p) -> list:
    if not p["known"].get("certifications"):
        return []
    mine = certifications()
    try:
        not_held_rx = [re.compile(pat, re.I) for pat, _why in
                       getattr(person.module("skills"), "NOT_HELD", {}).values()]
    except Exception:  # noqa: BLE001
        not_held_rx = []
    out = []
    listed = [c["name"] for c in p["certifications"] if str(c.get("name") or "").strip()]
    for name in listed:
        if any(same_cert(name, h) for h in mine["held"]):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if any(same_cert(name, h) for h in mine["in_progress"]):
            out.append(_finding(f"cert-in-progress:{slug}", f"LinkedIn lists {name} as earned; "
                                "your profile says it is still in progress.",
                                f"certification: \"{name}\"",
                                "Take it off until it is passed (or name it as in progress in "
                                "your About): a certificate a recruiter cannot verify is the "
                                "claim they doubt the rest by."))
        elif (any(same_cert(name, n) for n in mine["not_held"]) or _said_in(name, mine["blocks"])
              or any(rx.search(name) for rx in not_held_rx)):
            out.append(_finding(f"cert-not-held:{slug}", f"LinkedIn lists {name}; your profile "
                                "says you do not hold it.", f"certification: \"{name}\"",
                                "Take it off LinkedIn: a certificate that is not held is the one "
                                "claim a recruiter can check, and it costs every other one."))
    for held in mine["held"]:
        if not any(same_cert(held, n) for n in listed):
            slug = re.sub(r"[^a-z0-9]+", "-", held.lower()).strip("-")
            out.append(_finding(f"cert-missing:{slug}", f"Your resume lists {held}; LinkedIn "
                                "does not.", "no certification of that name",
                                "Add it: a reader comparing the two sees it on one and wonders "
                                "about the other."))
    return out


def _thin(p, today) -> list:
    if not (p["known"].get("summary") and p["known"].get("descriptions")):
        return []
    if len(p["summary"]) >= THIN_SUMMARY_CHARS:
        return []
    recent = []
    for x in p["positions"]:
        end = export.month(x.get("finished"))
        if not str(x.get("finished") or "").strip() or (end and end[0] >= today.year - RECENT_YEARS):
            recent.append(x)
    if not recent or any(str(x.get("description") or "").strip() for x in recent):
        return []
    return [_finding("thin", f"Your About is {len(p['summary'])} characters and none of your "
                     "recent jobs has a description.",
                     f"about: {len(p['summary'])} characters; {len(recent)} recent "
                     "position(s), none described",
                     "Add three or four lines to the current job and an About of a short "
                     "paragraph, from your resume's own bullets: in a study of 24,570 "
                     "applications a bare profile drew fewer callbacks than none at all.")]


def _confidential(p, answers) -> list:
    if not confidential():
        return []
    out = []
    m = _SEEKING.search(p["headline"]) or _SEEKING.search(p["summary"])
    if m:
        where = "headline" if _SEEKING.search(p["headline"]) else "About"
        out.append(_finding("confidential-visible", f"Your search is confidential, and your "
                            f"LinkedIn {where} says \"{m.group(0)}\".", f"{where}: \"{m.group(0)}\"",
                            "Take it out: your current employer can read your profile like "
                            "anyone else."))
    if (answers.get("open-to-work") or {}).get("answer") == "yes":
        out.append(_finding("confidential-open-to-work", "Your search is confidential, and Open "
                            "to Work shows to everyone.", "your answer: everyone can see it",
                            "Switch it to recruiters only, or off: even recruiters only cannot "
                            "promise your own employer's recruiters will not see it."))
    return out


def dismissed() -> set:
    """Finding ids the person said they do not care about: profile/learned.json is the
    record, so retiring that entry brings the finding back."""
    try:
        import learned
        rows = learned.entries("other")
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    for r in rows:
        if any("own_profile_review" in a for a in r.get("applied_to") or ()):
            out |= set(re.findall(r'never raise "([^"]+)" again', r.get("rule", "")))
    return out


def check(p: dict, today=None, answers: dict | None = None) -> dict:
    """{"findings": [...], "questions": [(id, question)], "not_read": [...], "dismissed": n}.

    Mechanical red flags only, each with its evidence and one fix. Nothing a person could
    call a nitpick: no headline length, connection count, banner, recommendations or
    skills order, for none of which there is evidence that it matters."""
    today = _today(today)
    answers = load_review()["answers"] if answers is None else answers
    found = (_location(p) + _never_said(p) + _roles(p, today) + _certs(p) + _thin(p, today)
             + _confidential(p, answers))
    if (answers.get("photo") or {}).get("answer") == "no":
        found.append(_finding("photo", "Your LinkedIn profile has no photo.", "your answer: no photo",
                              "Add one of you, face visible: a request from a profile with no "
                              "photo is the one most often ignored, and reads as a fake account."))
    gone = dismissed()
    kept = [f for f in found if f["id"] not in gone]
    asks = [(q, QUESTIONS[q]) for q in ("photo", "open-to-work")
            if q not in answers and (q != "open-to-work" or confidential())]
    return {"findings": kept, "questions": asks, "not_read": p.get("not_read", []),
            "dismissed": len(found) - len(kept)}


def record(p: dict, result: dict, today=None, src=None) -> dict:
    """Keep one look: the date, the source, what it compared, and the findings. `src` is
    the export the look read, so its hash is of those files and not the default folder's."""
    data = load_review()
    row = {"date": _today(today).isoformat(), "source": p["source"], "files": p.get("files", []),
           "hashes": dict(fact_parts(),
                          export=export_part(src) if p["source"] == "export" else ""),
           "findings": [{k: f[k] for k in ("id", "what", "fix")} for f in result["findings"]],
           "answers": dict(data["answers"]), "decided": "", "judged": []}
    data["reviews"].append(row)
    save_review(data)
    return row


# ---------------------------------------------------------------- the brief

def _clip(text, n) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def _asked_about(limit=5) -> list:
    import csv
    try:
        with open(person.state("job_search_tracker.csv"), newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return []
    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    return list(dict.fromkeys(str(r.get("role") or "").strip() for r in rows
                              if str(r.get("role") or "").strip()))[:limit]


def brief(p: dict, result: dict, today=None, force: bool = False) -> str:
    """For the session's own model: what is left to judge, compact. "" when nothing is.

    Printed when a look is due or one was recorded today, and only when there is a
    headline or an About to judge."""
    today = _today(today)
    last = last_review()
    fresh = bool(last and last["date"][:10] == today.isoformat())
    if not (force or fresh or due_reasons(today)[0]):
        return ""
    if not (p["headline"] or p["summary"]):
        return ""
    md = _md_text()
    said = " ".join(m.group(1) for m in re.finditer(r"^>\s?(.*)$", _section(md, "Canonical Summary"),
                                                    re.M))
    try:
        net = person.module("networking") if person.exists("networking.py") else None
    except Exception:  # noqa: BLE001
        net = None
    about_me = str(getattr(net, "ABOUT_ME", "") or "")
    current = next((x for x in p["positions"] if not str(x.get("finished") or "").strip()), None)
    lines = [
        "Judge this person's own LinkedIn profile for one thing: would anything here stop a "
        "stranger they write to from replying, or a recruiter from believing them? At most "
        "three findings, each quoting the profile's own words, each with one fix. \"Nothing "
        "that would stop people replying\" is an expected answer, and often the right one. "
        "Never comment on the photo, banner, connection count, recommendations, headline "
        "length or the order of skills, nor on anything already flagged below.",
        "Already flagged: " + ("; ".join(f["what"] for f in result["findings"]) or "nothing"),
        "What they do (their profile, the source of truth): "
        + (_clip(_plain(said), 500) or "not in the profile"),
        "What they tell people they want: " + (_clip(about_me, 200) or "not set"),
        "Roles they are asking about: " + (", ".join(_asked_about()) or "none tracked yet"),
        f"Headline: \"{_clip(p['headline'], 300)}\"",
        f"About: \"{_clip(p['summary'], 1600)}\"",
    ]
    if current:
        lines.append(f"Current job there: {current.get('title')} at {current.get('company')}: "
                     f"\"{_clip(current.get('description'), 500)}\"")
    lines += [
        "Two questions only:",
        "1. Do the headline and About say what they do in the words the people they write to "
        "use for it?",
        "2. From this page alone, would a reader believe they fit the roles they ask about?",
        "Then ask the person what they want to change, and record it: python3 "
        "tools/network/own_profile.py decide --said \"<their words>\" --finding \"<each "
        "finding>\"",
    ]
    return _clip_lines(lines, BRIEF_MAX_CHARS)


def _clip_lines(lines, most) -> str:
    out, used = [], 0
    for line in lines:
        if used + len(line) > most:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


# ---------------------------------------------------------------- answers and decisions

def answer(question: str, value: str, today=None) -> dict:
    if question not in QUESTIONS:
        raise ValueError(f"no question {question!r}; one of {', '.join(QUESTIONS)}")
    value = str(value or "").strip().lower()
    if value not in ("yes", "no"):
        raise ValueError("the answer is yes or no")
    data = load_review()
    data["answers"][question] = {"answer": value, "date": _today(today).isoformat()}
    last = last_review(data)
    if last is not None:                       # the look it answers keeps it too
        last.setdefault("answers", {})[question] = data["answers"][question]
    save_review(data)
    return data["answers"][question]


def dismiss(fid: str, said: str, today=None) -> dict:
    """A finding the person does not care about: kept in profile/learned.json, so it is
    never raised again, and noted in the review record."""
    import learned
    if not str(said or "").strip():
        raise ValueError("a dismissal keeps the person's own words: --said \"...\"")
    got = learned.record("other", said, f"Own LinkedIn profile: never raise \"{fid}\" again",
                         applied_to=["documents/network/own_profile_review.json"], today=(
                             _today(today).isoformat()))
    data = load_review()
    data["dismissed"].append({"id": fid, "date": _today(today).isoformat(), "said": said})
    save_review(data)
    return got


def decide(said: str, findings=(), today=None) -> dict:
    data = load_review()
    last = last_review(data)
    if last is None:
        raise ValueError("no look on record to add a decision to: run check first")
    last["decided"] = " ".join(str(said or "").split())
    last["judged"] = [str(f).strip() for f in findings if str(f).strip()]
    last["decided_on"] = _today(today).isoformat()
    save_review(data)
    return last


# ---------------------------------------------------------------- the command line

def _source_of(a) -> dict | None:
    if a.paste:
        return from_paste(a.paste, a.source or "paste")
    return from_export(a.src)


def _no_source() -> str:
    return ("own_profile: no copy of your own LinkedIn profile to look at. Either attach your "
            "export's profile files (the steps: python3 tools/claude_surfaces.py steps "
            "linkedin-export-files), or paste your profile's text and the session writes it "
            "into the shape python3 tools/network/own_profile.py shape prints")


def _print_check(p, result, recorded) -> None:
    src = {"export": "your LinkedIn export", "paste": "what you pasted",
           "browser": "your page, read in your own browser"}[p["source"]]
    print(f"Own LinkedIn profile, from {src} ({', '.join(p.get('files') or [])}):")
    if result["findings"]:
        print(f"RED FLAGS ({len(result['findings'])})")
        for n, f in enumerate(result["findings"], 1):
            print(f"  {n}. {f['what']} Fix: {f['fix']}")
            print(f"     evidence: {f['evidence']}  [{f['id']}]")
    else:
        print("No red flags: nothing mechanical that would stop people replying.")
    if result["dismissed"]:
        print(f"  ({result['dismissed']} you said you do not care about, not raised)")
    for q, words in result["questions"]:
        print(f"ASK ONCE, yes or no: {words} Then: python3 tools/network/own_profile.py "
              f"answer {q} yes|no")
    for line in result["not_read"]:
        print(f"Not checked: {line}")
    if recorded:
        print("Kept in documents/network/own_profile_review.json. Next, for the judgement: "
              "python3 tools/network/own_profile.py brief")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="own_profile.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("due")
    d.add_argument("--today", default=None)
    for name in ("check", "brief"):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="src", default=None)
        p.add_argument("--paste", default=None)
        p.add_argument("--source", choices=("paste", "browser"), default=None)
        p.add_argument("--today", default=None)
        if name == "check":
            p.add_argument("--dry-run", action="store_true")
    an = sub.add_parser("answer")
    an.add_argument("question", choices=sorted(QUESTIONS))
    an.add_argument("value", choices=("yes", "no"))
    di = sub.add_parser("dismiss")
    di.add_argument("finding")
    di.add_argument("--said", required=True)
    de = sub.add_parser("decide")
    de.add_argument("--said", required=True)
    de.add_argument("--finding", action="append", default=[])
    sub.add_parser("shape")
    a = ap.parse_args(argv)
    if not person.exists() or export is None:
        if a.cmd != "due":
            print("own_profile: no profile yet: run /setup")
        return 0 if a.cmd == "due" else 2
    if a.cmd == "due":
        line = due(a.today)
        if line:
            print(line)
        return 0
    if a.cmd == "shape":
        print(json.dumps(SHAPE, indent=2))
        return 0
    if a.cmd == "answer":
        got = answer(a.question, a.value)
        print(f"own_profile: kept, {a.question}: {got['answer']}; never asked again")
        return 0
    if a.cmd == "dismiss":
        dismiss(a.finding, a.said)
        print(f"own_profile: \"{a.finding}\" is never raised again (profile/learned.json)")
        return 0
    if a.cmd == "decide":
        try:
            decide(a.said, a.finding)
        except ValueError as e:
            print(f"own_profile: {e}")
            return 1
        print("own_profile: what they decided is kept with the last look")
        return 0
    try:
        p = _source_of(a)
    except (OSError, ValueError) as e:
        print(f"own_profile: {e}")
        return 1
    if p is None:
        print(_no_source())
        return 2
    result = check(p, a.today)
    if a.cmd == "check":
        if not a.dry_run:
            record(p, result, a.today, src=a.src)
        _print_check(p, result, recorded=not a.dry_run)
        return 0
    text = brief(p, result, a.today)
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
