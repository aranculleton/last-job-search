#!/usr/bin/env python3
"""Where a person's documents live and what they are called. One place.

A resume is cv/<Prefix>_Resume_<ABBR>.tex and its letter is
cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex, where <Prefix> is
identity.file_prefix in the profile (the person's name, "First_Last") and
<ABBR> is the human-looking suffix tools/doc_name.py derives from the company.
The prefix used to be a literal in about ten tools that had to agree, and the
tracker stores these paths, so tools/doc_name.py matches against them: they
come from here or they drift.

    python3 tools/docpaths.py shell   # the batch check's profile values, as shell assignments
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

ROOT = person.ROOT


def prefix() -> str:
    return person.get("identity.file_prefix")


def noun_word() -> str:
    """The document's noun as it sits in a filename: "Resume" or "CV".

    The person's own word (person.json documents.noun), because the filename is
    the first thing an employer reads and a profile that bans "resume" must not
    upload <Name>_Resume_ACME.pdf.
    """
    noun = person.get("documents.noun", "resume")
    return noun[:1].upper() + noun[1:] if noun.islower() else noun


def resume_stem(abbr: str) -> str:
    return f"{prefix()}_{noun_word()}_{abbr}"


def letter_stem(abbr: str) -> str:
    return f"{prefix()}_Cover_Letter_{abbr}"


def resume_rel(abbr: str, ext: str = ".tex") -> str:
    """Repo-relative, as the tracker's cv_file column stores it."""
    return f"cv/{resume_stem(abbr)}{ext}"


def letter_rel(abbr: str, ext: str = ".tex") -> str:
    """Repo-relative, as the tracker's cover_letter_file column stores it."""
    return f"cover_letters/{letter_stem(abbr)}{ext}"


def resume_tex(abbr: str) -> str:
    return person.state(resume_rel(abbr, ".tex"))


def resume_pdf(abbr: str) -> str:
    return person.state(resume_rel(abbr, ".pdf"))


def letter_tex(abbr: str) -> str:
    return person.state(letter_rel(abbr, ".tex"))


def letter_pdf(abbr: str) -> str:
    return person.state(letter_rel(abbr, ".pdf"))


# The person's own resume, the one they send when someone asks for it and names no role:
# documents/cv/, which they fill (documents/README.md). A tailored resume for a role nobody
# named is a guess, and the guess is what the reader sees.
GENERAL_DIR = ("documents", "cv")
SENDABLE = (".pdf", ".docx", ".doc")
_DATED = re.compile(r"(\d{4})[-_.]?(\d{2})(?:[-_.]?(\d{2}))?")


def general_resumes() -> list[str]:
    """Every file in documents/cv/ that could go to someone as it is, repo-relative."""
    folder = person.state(*GENERAL_DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return ["/".join(GENERAL_DIR + (n,)) for n in names
            if os.path.splitext(n)[1].lower() in SENDABLE
            and os.path.isfile(os.path.join(folder, n))]


def current_resume() -> str:
    """The resume to send when no role was named, repo-relative, or "" when it cannot be told.

    The one whose name says it is current ("Morgan_Ellis_CV_current.pdf"), else the only one,
    else the one whose name carries the latest date; a PDF before a Word copy of the same.
    Two undated files and nothing saying which is "": the person is asked, never guessed for.
    """
    files = general_resumes()
    if not files:
        return ""

    def best(group):
        pdfs = [f for f in group if f.lower().endswith(".pdf")]
        group = pdfs or group
        if len(group) == 1:
            return group[0]
        dated = [((m.group(1), m.group(2), m.group(3) or "00"), f) for f in group
                 for m in [_DATED.search(os.path.basename(f))] if m]
        if len(dated) == len(group):
            top = max(d for d, _ in dated)
            hits = [f for d, f in dated if d == top]
            return hits[0] if len(hits) == 1 else ""
        return ""

    current = [f for f in files if "current" in os.path.basename(f).lower()]
    return best(current) if current else best(files)


def resume_name_rx() -> re.Pattern:
    """Matches a resume filename and captures its ABBR."""
    return re.compile(re.escape(prefix()) + "_" + re.escape(noun_word()) + r"_([A-Za-z0-9_]+)")


def _ere(s: str) -> str:
    """Escape for grep -E. Not re.escape: it writes "\\ " for a space, which
    GNU grep 3.8+ warns about on every line it reads."""
    return re.sub(r"([.\[\](){}*+?|^$\\])", r"\\\1", s)


def shell() -> str:
    """What the batch check needs from the profile, as shell assignments (values())."""
    return "\n".join(f"{k}={shlex.quote(str(x))}" for k, x in values().items())


def contact_lines() -> list:
    """Every contact detail the resume prints, as the page prints it: the place, the phone,
    the email, the LinkedIn label and each documents.resume_extra line. verify_batch
    checks the page for each, so a line LaTeX dropped is never lost in silence."""
    ident = person.get("identity", {}) or {}
    out = [ident.get(k) for k in ("location", "phone", "email")]
    if ident.get("linkedin"):
        out.append(ident.get("linkedin_label") or "LinkedIn")
    out += list(person.get("documents.resume_extra", []) or [])
    return [" ".join(str(x).split()) for x in out if str(x or "").strip()]


def values() -> dict:
    """What tools/verify_batch.py needs from the profile, by name."""
    roles = person.module("roles").ROLES
    heads = person.get("documents.headings")
    noun_ban = person.get("documents.banned_nouns", [])
    pinned = getattr(person.module("skills"), "PINNED", None) if person.exists("skills.py") else None
    order = ">".join(r["employer"] for r in roles) + ">"
    alt = "|".join(_ere(r["employer"]) for r in roles)
    mins = " ".join(f"{i}:{r['verify_min']}:{r['short']}" for i, r in enumerate(roles)
                    if r.get("verify_min"))
    v = dict(
        PREFIX=prefix(),
        NOUN_WORD=noun_word(),
        ROLE_ALT=alt,
        ROLE_ORDER=order,
        ROLE_HEADER="/".join(r["short"] for r in roles),
        ROLE_NAMES=json.dumps([r["employer"] for r in roles]),
        ROLE_MINS=mins,
        # Optional, as the renderer treats them: a profile with no phone was "cannot read
        # the profile" here, so it could never be verified.
        EMAIL=person.get("identity.email", "") or "",
        PHONE=person.get("identity.phone", "") or "",
        CONTACT_LINES=json.dumps(contact_lines(), ensure_ascii=False),
        PINNED=pinned[1] if pinned else "",
        # A profile with no certifications renders no Certifications section.
        SECTIONS=json.dumps([heads[k] for k in
                             (person.get("documents.section_order", None)
                              or ("summary", "experience", "skills", "education",
                                  "certifications"))
                             if k != "certifications"
                             or getattr(person.module("roles"), "CERTIFICATIONS", "")]),
        RESUME_PAGES=str(person.get("documents.resume_pages", 1) or 1),
        H_EXPERIENCE=heads["experience"],
        H_SKILLS=heads["skills"],
        H_EDUCATION=heads["education"],
        BANNED_NOUNS="|".join(_ere(n) for n in noun_ban),
        BANNED_FLAG=("SAYS_" + re.sub(r"[^A-Z0-9]+", "_", noun_ban[0].upper())) if noun_ban else "",
    )
    return v


if __name__ == "__main__":
    if sys.argv[1:] == ["shell"]:
        print(shell())
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
