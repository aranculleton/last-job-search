#!/usr/bin/env python3
"""Where a person's documents live and what they are called. One place.

A resume is cv/<Prefix>_Resume_<ABBR>.tex and its letter is
cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex, where <Prefix> is
identity.file_prefix in the profile (the person's name, "First_Last") and
<ABBR> is the human-looking suffix tools/doc_name.py derives from the company.
The prefix used to be a literal in about ten tools that had to agree, and the
tracker stores these paths, so tools/doc_name.py matches against them: they
come from here or they drift.

    python3 tools/docpaths.py shell   # shell assignments for verify_batch.sh
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


def resume_name_rx() -> re.Pattern:
    """Matches a resume filename and captures its ABBR."""
    return re.compile(re.escape(prefix()) + "_" + re.escape(noun_word()) + r"_([A-Za-z0-9_]+)")


def _ere(s: str) -> str:
    """Escape for grep -E. Not re.escape: it writes "\\ " for a space, which
    GNU grep 3.8+ warns about on every line it reads."""
    return re.sub(r"([.\[\](){}*+?|^$\\])", r"\\\1", s)


def shell() -> str:
    """What verify_batch.sh needs from the profile, as shell assignments."""
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
        EMAIL=person.get("identity.email"),
        PHONE=person.get("identity.phone"),
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
    return "\n".join(f"{k}={shlex.quote(str(x))}" for k, x in v.items())


if __name__ == "__main__":
    if sys.argv[1:] == ["shell"]:
        print(shell())
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
