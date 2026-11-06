#!/usr/bin/env python3
"""Deterministic grounding pre-check for generated resumes and cover letters.

The expensive grounding reviewer keeps catching the *same* errors. Across a
handful of applications it finds defects, and nearly every one belongs to a
class that has already appeared in an earlier application:

  - a metric attached to the wrong piece of work (a forecast's percentage
    error applied to a segmentation model, which has none)
  - a sector qualifier dropped from a dataset's description, which on an
    application to a different sector nudges the reader toward believing the
    work was done in that sector
  - a hedge removed ("contributed to" -> "grew"), claiming sole causation for
    a growth curve
  - a scope qualifier removed ("during peak-season weeks")
  - a tool attributed to the wrong employer
  - a certification presented as complete when it is scheduled

Paying a reviewer agent to rediscover a fixed list of string patterns is waste.
This script checks them at zero token cost, so the reviewer's attention goes to
the judgment calls only it can make.

**This does not replace the grounding reviewer.** It catches known repeats. New
error classes still need a reader. When the reviewer finds one this script
missed, add it to the profile's claims.py (a fact about the candidate) or to
app_rules() below (a rule about writing).

Usage:
    python3 tools/check_claims.py cv/<Prefix>_ACME_Resume.tex ...
    python3 tools/check_claims.py cv/*.tex cover_letters/*.tex

Exit status 1 if any ERROR-level finding fires.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locale_rules  # noqa: E402
import person  # noqa: E402

# The app's own rules apply to everyone. The locale rules among them (the
# dashes, the document noun the market does NOT use, the spelling variant)
# follow the profile's documents settings, and tools/locale_rules.py is the one
# copy every reader takes them from. These names are kept so a caller that read
# them here still can. The rest are writing slips.
_LOCALE = locale_rules.LOCALE
LEGITIMATE_ISE = _LOCALE.legitimate_ise
_VARIANT_WORDS = {k: (pat, why) for k, (_, pat, why) in locale_rules.VARIANT_WORDS.items()}


def app_rules() -> dict:
    """name -> (severity, name, pattern, why), in the app's order."""
    r = {}
    L = _LOCALE
    if L.dash_pattern:
        # Every character the profile bans, and the dash typed as "--" or "---",
        # which is how LaTeX writes both. The name is the one profiles place.
        r["em-dash"] = ("ERROR", "em-dash", L.dash_pattern,
                        "No em dashes anywhere, per the writing guide's rule 1, nor any other "
                        "character documents.banned_characters names, typed as -- or --- "
                        "included.")
    for n in L.nouns:
        name = "the-word-" + re.sub(r"[^a-z0-9]+", "-", n.word.lower())
        r[name] = ("ERROR", name, n.document.pattern,
                   f"The document is a {L.noun}, never a {n.word}, in anything the employer sees.")
    if L.ise is not None:
        r["british-ise-spelling"] = ("ERROR", "british-ise-spelling", L.ise.pattern, L.ise_why)
    if L.variant is not None:
        name = "american-spelling" if L.spelling == "canadian" else f"{L.spelling}-spelling"
        r[name] = ("ERROR", name, L.variant.pattern, L.variant_why)
    # A status the person does not hold (networking.py UNSUPPORTED_STATUS), which every
    # message was already checked for: a resume or letter is held to the same.
    net = person.module("networking") if person.exists("networking.py") else None
    status = getattr(net, "UNSUPPORTED_STATUS", None)
    if status is not None and status.pattern != r"(?!x)x":
        r["unsupported-status"] = ("ERROR", "unsupported-status", status.pattern,
                                   "A status the profile does not hold: "
                                   + str(getattr(net, "UNSUPPORTED_WHY", "") or "check it"))
    # A skill the profile records as not held (skills.py NOT_HELD). The skills
    # block can never print one, but a summary, a letter or a hand edit can, and
    # nothing read for it. On a letter it is a warning: naming the posting's
    # requirement to bridge it is allowed, if rarely wise (rule 8).
    unheld = unheld_pattern()
    if unheld:
        r["unheld-skill"] = ("ERROR", "unheld-skill", unheld,
                             "A skill profile/skills.py NOT_HELD says the candidate does not "
                             "hold, and they were not asked about it for this application. "
                             "Only their yes puts one on a document (stage_picks.py consent).")
    r["duplicated-word"] = ("ERROR", "duplicated-word", r"\b([^\W\d_]{3,})\s+\1\b",
                            "A word is repeated. Usually an editing slip.")
    # A line no reader needs, which a hand-made resume carried and was sent with (2026-09).
    r["references-on-request"] = ("ERROR", "references-on-request",
                                  r"\breferences?\b[^.\n¦]{0,30}?\b(?:available\s+)?"
                                  r"(?:up)?on\s+request\b",
                                  "\"References available upon request\" says nothing a reader "
                                  "needs: take it out.")
    r["unsupported-connective"] = (
        "WARN", "unsupported-connective",
        r"\bin parallel\b|\bsimultaneously\b|\bwhile also\b",
        "Asserts two things happened together. The profile rarely supports that; "
        "check it does before keeping the phrase.")
    return r


def unheld_pattern(except_for=()) -> str:
    """One pattern for every skill the profile's skills.py NOT_HELD lists, or "", leaving
    out any the person said yes to for this document (`except_for`)."""
    if not person.exists("skills.py"):
        return ""
    pats = [pat for pat, _ in getattr(person.module("skills"), "NOT_HELD", {}).values()
            if pat and not any(re.search(pat, y, re.I) for y in except_for)]
    return "|".join(f"(?:{p})" for p in pats)


# The person's answers about skills their profile does not hold, asked before the
# draft (tools/stage_picks.py consent), travel in the document's own header, so a
# check of the file needs nothing else: a yes is theirs to claim, a no is flagged.
_YES = "Claimed with the candidate's yes"
_NO = "The candidate said no to"


def consent_header(yes=(), no=()) -> str:
    """The header lines that record the person's answers, or "" when there are none."""
    out = ""
    for label, names in ((_YES, yes), (_NO, no)):
        names = [re.sub(r"\s+", " ", str(n)).strip() for n in names or () if str(n).strip()]
        if names:
            out += f"% {label}: {', '.join(names)}\n"
    return out


def read_consent(raw: str) -> tuple[list[str], list[str]]:
    """(yes, no) from a document's header."""
    got = {}
    for label in (_YES, _NO):
        m = re.search(r"^%+\s*" + re.escape(label) + r":\s*(.+)$", raw, re.M)
        got[label] = [n.strip() for n in m.group(1).split(",") if n.strip()] if m else []
    return got[_YES], got[_NO]


DEFAULT_SOURCES = ("01-candidate-profile.md", "CLAUDE.md", "bullets.py")
_sources_cache: dict = {}


def grounding_text() -> str:
    """Every file person.json `grounding.sources` names (the candidate profile, the summary
    and bullets.py by default), as one text, read again when one of them changes."""
    try:
        paths = [os.path.normpath(person.path(p)) for p in
                 person.get("grounding.sources", list(DEFAULT_SOURCES))]
    except person.NoProfile:
        return ""
    # Its time and its size: on Windows a yes and then a no written in one tick of the clock
    # kept the time, and a skill said no to was still held (the release run, 2026-11-04).
    stamp = []
    for p in paths:
        try:
            st = os.stat(p)
            stamp.append((p, (st.st_mtime_ns, st.st_size)))
        except OSError:
            stamp.append((p, None))
    if _sources_cache.get("stamp") != stamp:
        parts = []
        for p, m in stamp:
            if m is None:
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
        _sources_cache.update(stamp=stamp, text="\n".join(parts))
    return _sources_cache["text"]


def skill_pattern(name: str) -> re.Pattern:
    """A skill's name as a profile writes it: any case, a space or a hyphen between words."""
    words = [re.escape(w) for w in re.split(r"[\s\-]+", str(name or "").strip()) if w]
    return re.compile(r"(?<![\w])" + r"[\s\-]+".join(words) + r"(?![\w])", re.I)


def grounded_skill(name: str) -> bool:
    """Does a file the profile grounds claims in name this skill?"""
    return bool(str(name or "").strip()) and bool(skill_pattern(name).search(grounding_text()))


# Rules that warn rather than fail on a cover letter. Read by check().
LETTER_SEVERITY = {"unheld-skill": "WARN"}


def is_letter(path: str) -> bool:
    """A cover letter, by its folder or its name (<Prefix>_<ABBR>_Cover_Letter)."""
    return (os.path.basename(os.path.dirname(os.path.abspath(path))) == "cover_letters"
            or "cover_letter" in os.path.basename(path).lower())


def _assemble():
    """The profile's rules in its order, with "@name" placing an app rule; any
    app rule the profile does not place runs after them."""
    mine = person.module("claims") if person.exists("claims.py") else None
    rules = app_rules()
    out = []
    for entry in getattr(mine, "CHECKS", []):
        if isinstance(entry, str) and entry.startswith("@"):
            if entry[1:] in rules:
                out.append(rules.pop(entry[1:]))
        else:
            out.append(tuple(entry))
    out.extend(rules.values())
    return out, list(getattr(mine, "FIGURE_DRIFT", []))


# (severity, name, pattern, why) - pattern is searched case-insensitively.
# ERROR means "this is wrong"; WARN means "look at this, it is often wrong".
# FIGURE_DRIFT: (pattern, why) for figures whose exact form the profile fixes;
# a drift is an escalation.
CHECKS, FIGURE_DRIFT = _assemble()


def strip_latex(text: str) -> str:
    """Remove commands and comments so patterns match prose, not markup."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        # A comment after the markup on a line is not prose either. "\%" is a
        # percent sign, so only an unescaped one starts a comment.
        out.append(re.sub(r"(?<!\\)%.*", "", line))
    t = "\n".join(out)
    # LaTeX's named dashes, as the characters, before commands are dropped.
    t = locale_rules.latex_dashes(t)
    # A link's address is not prose: \href{address}{text} keeps the text.
    t = re.sub(r"\\(?:href|url)\s*\{[^}]*\}", " ", t)
    t = re.sub(r"\\textbackslash|\\textasciitilde\{\}", "~", t)
    # Drop \begin{env} / \end{env} with the environment name, or a document full
    # of itemize blocks reports a phantom "itemize itemize" duplicated word.
    t = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}", " ", t)
    # Drop fontspec/geometry style option blocks, which are not prose. A letter in a
    # colour asks for its font again with fontspec's own key, "Color", which is not the
    # person's spelling of anything (templates/doc_style.py).
    t = re.sub(r"\\fontspec\s*\[[^\]]*\]", " ", t)
    t = re.sub(r"\\addfontfeatures?\s*\{[^}]*\}", " ", t)
    t = re.sub(r"\\(?:textbf|textit|emph|href|url|item|section|item)\b", " ", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
    # Separate LaTeX fields with a sentinel rather than a space: "University of
    # Leeds}{Leeds, UK" is two distinct cventry fields, and collapsing the brace
    # to a space makes it read as the duplicated word "Leeds Leeds".
    t = t.replace("{", " \u00a6 ").replace("}", " \u00a6 ")
    return t


def check(path: str) -> list[tuple[str, str, str, str]]:
    raw = open(path, encoding="utf-8").read()
    return check_text(raw, letter=is_letter(path))


def check_text(raw: str, letter: bool = False) -> list[tuple[str, str, str, str]]:
    """The findings for a document's text, read as `check` reads a file: `letter` says
    whether the letter's severities apply, and the person's answers are read from the
    consent header in `raw` (consent_header). The drafting audit reads a draft object
    this way before anything is rendered (tools/draft_audit.py)."""
    text = strip_latex(raw)
    findings = []
    yes, no = read_consent(raw)
    for sev, name, pat, why in CHECKS:
        if letter:
            sev = LETTER_SEVERITY.get(name, sev)
        if name == "unheld-skill" and yes:
            pat = unheld_pattern(except_for=yes)
            if not pat:
                continue
        for m in re.finditer(pat, text, re.I | re.S):
            snippet = re.sub(r"\s+", " ", m.group(0))[:110]
            findings.append((sev, name, snippet, why))
    for pat, why in FIGURE_DRIFT:
        for m in re.finditer(pat, text, re.I):
            findings.append(("ERROR", "figure-drift",
                             re.sub(r"\s+", " ", m.group(0))[:80], why))
    # A yes puts a skill on the page, and the yes must be in the profile: a chat is never a
    # source until the fact is written there (CLAUDE.md, "grounded"). NLP, BigQuery and
    # LLM-as-judge went on a sent resume on a yes given in a chat, and no profile file held
    # any of them (2026-10-26). `stage_picks.py consent` writes each yes into the candidate
    # profile as it records it; one it did not write is an error until it is there.
    for n in yes:
        if not grounded_skill(n):
            findings.append(("ERROR", "ungrounded-yes", n,
                             f"{n} is claimed on the candidate's yes, and no profile file "
                             "holds it: record the yes with `python3 tools/stage_picks.py "
                             "consent <round> <pick> --yes \"" + n + "\"`, which writes it into "
                             "01-candidate-profile.md, or take it off."))
    now = available_now_clash(text)
    if now:
        findings.append(("ERROR", "available-now", now.split("\", ")[0].lstrip("\""),
                         "Starting at once is not what your profile says: " + now + "."))
    # Something still to happen, dated in a month that has gone: "certification in progress,
    # scheduled September 2026" went on resumes sent in October and stayed there.
    for m in _STALE.finditer(text):
        when = _month_of(m.group("month"), m.group("year"))
        if when and when < _this_month():
            findings.append(("ERROR", "stale-date", " ".join(m.group(0).split()),
                             "A date that has passed, said as still to come: give the new "
                             "date the profile holds, or leave the date out."))
    # A warning, not an error: the word can also sit inside work the profile does hold.
    for n in no:
        for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text, re.I):
            findings.append(("WARN", "declined-skill", m.group(0),
                             "The candidate said no to claiming this for this application. "
                             "Take it out unless it describes work the profile does hold."))
    return findings


# "Available straight away" to a recruiter, from someone with a month's notice (2026-10-21).
_AVAILABLE_NOW = re.compile(
    r"\b(?:available|free|able)\s+(?:to\s+start\s+)?(?:straight\s+away|right\s+away|"
    r"immediately|at\s+once|from\s+(?:now|today|tomorrow))\b"
    r"|\b(?:can|could)\s+start\s+(?:straight\s+away|right\s+away|immediately|tomorrow|now)\b",
    re.I)
_NO_NOTICE = re.compile(r"\b(?:immediate(?:ly)?|none|no notice|nil|zero|straight away|right "
                        r"away|now)\b", re.I)


def available_now_clash(text: str) -> str:
    """What `text` says about starting at once that the profile's notice period does not
    allow, or "": "available straight away" from someone whose notice is one month."""
    m = _AVAILABLE_NOW.search(str(text or ""))
    if not m:
        return ""
    try:
        import screening_answers
        notice = screening_answers.notice_period()
    except Exception:  # noqa: BLE001  no notice on file: nothing to hold it against
        return ""
    if _NO_NOTICE.search(notice):
        return ""
    return f"\"{m.group(0)}\", and your notice period is {notice}"


_MONTH_NAMES = ("january", "february", "march", "april", "may", "june", "july", "august",
                "september", "october", "november", "december")
_STALE = re.compile(r"\b(?:scheduled|booked|expected|due|planned|sitting)\s+(?:for\s+|in\s+)?"
                    r"(?P<month>(?i:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
                    r"[a-z]*\.?)\s+(?P<year>20\d\d)\b", re.I)


def _month_of(month: str, year: str):
    m = str(month or "").lower().rstrip(".")
    n = next((i for i, name in enumerate(_MONTH_NAMES, 1) if name.startswith(m[:3])), None)
    return (int(year), n) if n else None


def _this_month():
    import datetime as _dt
    today = _dt.date.today()
    return (today.year, today.month)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--quiet", action="store_true",
                    help="print only files with findings")
    a = ap.parse_args()

    errors = 0
    for path in a.files:
        found = check(path)
        if not found and a.quiet:
            continue
        if not found:
            print(f"OK    {path}")
            continue
        print(f"\n{path}")
        for sev, name, snippet, why in found:
            if sev == "ERROR":
                errors += 1
            print(f"  {sev:5} [{name}]  ...{snippet}...")
            print(f"        {why}")
    print(f"\n{errors} error-level finding(s) across {len(a.files)} file(s).",
          file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
