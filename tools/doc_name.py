"""The filename suffix on a resume or cover letter, derived from the company.

The employer sees the filename on the attachment, so it has to read like a
person named it. The rule used to ask for a 2-to-4 character UPPERCASE
abbreviation, which is right for a company that genuinely writes itself that
way (IBM, SAP) and wrong for every company that does not. Applied to the rest
it produced <Name>_Resume_ACMEWIDGETS.pdf: not an abbreviation at all, just the
company name shouted, and a name like that reads as machine-generated.

So: a company writes its own name, and this returns it. A name styled with an
inner capital keeps it, a lower-case letter in an initialism keeps it, a word
stays a word. Only the names in KNOWN override that, and every one of them is
either an abbreviation people actually say out loud or a company that styles
itself in capitals. KNOWN is the profile's (employers.py ABBREVIATIONS),
because which companies need one depends on who the person applies to.

The derivation is here rather than in the drafter's head because the drafter
got it wrong across a batch of documents while the rule sat in markdown two
files away.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docpaths  # noqa: E402
import person  # noqa: E402

TRACKER = person.state("job_search_tracker.csv")
_EMP = person.module("employers") if person.exists("employers.py") else None

# An established abbreviation people say out loud, or a name whose own styling
# is not what title-casing would produce. Keyed on the lowercased company name.
KNOWN = dict(getattr(_EMP, "ABBREVIATIONS", {}))

# Dropped from the END of a name before shortening. They identify the legal
# entity, not the company anybody names in conversation. Only ever from the
# end: "Co" leads "Co-Ventures", and stripping it from the front left the
# file named <Name>_Resume_Ventures. The profile adds its market's words
# (employers.py NAME_FILLER: a country name, so "Acme Ireland" is Acme).
GENERIC = {"inc", "incorporated", "ltd", "limited", "pty", "llc", "llp", "lp", "corp",
           "corporation", "company", "co", "group", "holdings", "plc", "gmbh",
           # Ireland's DAC, CLG, UC and Teoranta, Canada's ULC, and the "Pvt
           # Ltd" and "Pte Ltd" of South and South-East Asia.
           "dac", "clg", "uc", "ulc", "teoranta", "teo", "pvt", "pte", "private",
           "technologies", "technology", "software", "solutions",
           "international", "worldwide", "financial"} | set(getattr(_EMP, "NAME_FILLER", ()))

MAX_CHARS = 14   # long enough for a two-word brand, short enough to stay a name


def _words(company: str) -> list[str]:
    """Words, with a hyphenated name kept whole: Co-Ventures is one word."""
    parts = re.split(r"[^A-Za-z0-9-]+", str(company or "").strip())
    return [p.strip("-") for p in parts if p.strip("-")]


def suffix(company: str, role_token: str = "") -> str:
    """The `<Name>` in <Prefix>_Resume_<Name>.tex.

    `role_token` is appended only when applying to two different roles at one
    employer, which is the one case where the company name alone collides.
    """
    words = _words(company)
    if not words:
        return ""
    known = KNOWN.get(" ".join(words).lower())
    if known is None:
        # Drop the trailing generic words, but never all of them: "The Co Group"
        # is nothing at all once "the" and "co" are gone.
        kept = list(words)
        if len(kept) > 1 and kept[0].lower() == "the":
            kept.pop(0)
        while len(kept) > 1 and kept[-1].lower() in GENERIC:
            kept.pop()
        # Truncate on a word boundary. Cutting mid-word gave a brand plus three
        # letters of the next word, which reads as a typo rather than as a
        # shortening.
        taken = []
        for w in kept:
            w = w.replace("-", "")
            if taken and len("".join(taken)) + len(w) > MAX_CHARS:
                break
            taken.append(w)
        # A cut that ends on "of" or "and" ("NationalBankof") is the
        # machine-made name this module exists to prevent.
        while len(taken) > 1 and taken[-1].lower() in ("of", "and", "the", "for", "de", "du",
                                                      "la", "le", "et", "&"):
            taken.pop()
        known = "".join(taken) or kept[0].replace("-", "")[:MAX_CHARS]
    token = re.sub(r"[^A-Za-z0-9]", "", role_token)
    return known + ("_" + token if token else "")


def is_shouty(name: str) -> bool:
    """A suffix that is a word in capitals rather than an abbreviation.

    Everything in KNOWN is allowed however it is cased. Anything else longer
    than four characters and entirely upper-case is the failure mode this
    module exists to stop.
    """
    n = str(name or "").split("_")[0]
    if n in set(KNOWN.values()):
        return False
    return len(n) > 4 and n.isupper()


# A gender marker a posting adds to its title ("(m/w/d)", "f/m/x", "(H/F)", "(all
# genders)"): it says who may apply, never which role it is.
_GENDER = re.compile(
    r"\(\s*(?:all genders|any gender|gn|m/w/d|w/m/d)\s*\)|"
    r"\(?(?<![\w/])(?:m|f|w|d|h|x|div|divers|diverse)(?:\s*/\s*(?:m|f|w|d|h|x|div|divers|"
    r"diverse)){1,3}(?![\w/])\)?", re.I)
# A requisition code or posting number: "REQ-2026-0412", "Req #1234", "Job ID: 88231",
# "JR0099", "R-12345", "Ref AB1234", a bare "40912".
_REQ = re.compile(
    r"(?<![\w-])(?:req(?:uisition)?|job|ref(?:erence)?|vacancy|posting|position)\.?\s*"
    r"(?:id|no|number|code|ref)?\.?\s*[:#-]?\s*#?\s*[A-Za-z]{0,4}[-_]?\d[\w/-]*|"
    r"(?<![\w-])#\s*\d[\w-]*|"
    r"(?<![\w-])(?:[A-Za-z]{1,4}[-_]?)?\d{3,}(?:[-_/][A-Za-z0-9]+)*(?![\w-])", re.I)


def role_core(title: str) -> str:
    """A posting title without its requisition code or gender marker: "Senior Data
    Analyst - REQ-2026-0412" and "Data Analyst (m/w/d)" are "Senior Data Analyst" and
    "Data Analyst". Neither belongs in a file name, and neither says which role it is."""
    s = _GENDER.sub(" ", str(title or ""))
    s = _REQ.sub(" ", s)
    s = re.sub(r"\(\s*[,;:/|-]*\s*\)|\[\s*[,;:/|-]*\s*\]", " ", s)
    s = re.sub(r"(?:\s*[-\u2013\u2014|:,;/]+)+\s*$", "", s.strip())
    s = re.sub(r"^\s*[-\u2013\u2014|:,;/]+\s*", "", s)
    s = re.sub(r"(\s[-\u2013\u2014|]\s)(?:\s*[-\u2013\u2014|]\s)+", r"\1", s)
    return " ".join(s.split())


def tracker_rows(path: str = TRACKER) -> list[dict]:
    """The rows, through csv_store.read_rows, the one state-file reader: a conflicted file
    is refused, and a short row's missing cells read as blanks, never None."""
    import csv_store
    try:
        return csv_store.read_rows(path)
    except OSError:
        return []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def owners(name: str, rows: list[dict]) -> list[dict]:
    """Tracker rows whose recorded resume or letter already carries this name."""
    # Case-folded: `_Acme.tex` and `_ACME.tex` are one file on macOS and
    # Windows, so a second Acme role would replace the documents already sent.
    stems = {docpaths.resume_rel(name, "").casefold(),
             docpaths.letter_rel(name, "").casefold()}
    return [r for r in rows
            if any(os.path.splitext((r.get(col) or "").strip())[0].casefold() in stems
                   for col in ("cv_file", "cover_letter_file"))]


def _unsent(row: dict) -> bool:
    """Drafted and never sent: its documents may be rendered again."""
    return (row.get("status") or "").strip().lower() == "drafted"


def reusable(name: str, role: str, rows: list[dict]) -> bool:
    """Whether every application holding this name is this role, still unsent.

    A regenerated draft for the SAME role keeps its name while nothing has gone
    out. Once it has (applied, interview, rejected), the files under that name
    are what the employer received: `/interview` and `/outcome` read them, and
    a redraft rendered over them replaced the record with a document nobody sent.
    """
    return all(_norm(r.get("role")) == _norm(role) and _unsent(r) for r in owners(name, rows))


def check_free(name: str, company: str, role: str, rows: list[dict]) -> None:
    """Raise when writing this name would replace another application's documents.

    `suffix()` gives one name per employer, so a second role there derives the
    name the first one was sent under. A round can pick second roles at
    employers whose resumes are already on file under their plain names;
    rendering would overwrite the record `/interview` reads with a document
    nobody sent. Only an unsent draft of the same role may be rendered over.
    """
    for r in owners(name, rows):
        same = _norm(r.get("role")) == _norm(role)
        if same and _unsent(r):
            continue
        what = ("the documents already sent for" if same else "the documents for")
        raise FileExistsError(
            f"{name} already holds {what} {r.get('company')}, "
            f"{r.get('role')!r} ({r.get('status')}, {r.get('date')}). Rendering "
            f"{company}, {role!r} under it would overwrite them. Give the draft an "
            f"abbr with a role token, e.g. {suffix(company, 'RoleName')}, or stage "
            "it with tools/stage_picks.py, which picks one.")


if __name__ == "__main__":   # pragma: no cover
    import sys
    if not sys.argv[1:] or sys.argv[1] in ("-h", "--help"):
        print('usage: python3 tools/doc_name.py "<employer name>" [...]: the name its documents take')
        sys.exit(0 if sys.argv[1:] else 2)
    for c in sys.argv[1:]:
        print("%-34s -> %s" % (c, suffix(c)))
