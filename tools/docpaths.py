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

# ------------------------------------------------------------ an application's folder
#
# Here, beside the documents' names, since 2026-10-25: they lived in outreach.py, so every
# tool that only needed a folder (the brief, the due list, the follow-ups) loaded the whole
# drafting toolchain to find one. outreach.py still offers them under the same names.

def slug(company, role, abbr=""):
    """Directory name for one application. The abbreviation is part of it, so
    two roles at one employer with the same title (one employer posted "Senior
    Business Analyst" twice), or two long titles that agree for eighty
    characters (one role advertised in two cities), never overwrite each other.

    Raises ValueError when company and role together hold no letter or digit.
    The caller joins the result into a path, so returning "" wrote the
    application's files straight into documents/applications/ rather than into
    a folder of its own. documents/README.md has always stated that as the
    rule; nothing enforced it, because the test covering the rule
    reimplemented it instead of calling this function, and the two had drifted
    apart on four of six cases.

    The second strip is after the truncation, not before. An 80-character cut
    can land on an underscore, and appending the abbreviation then produced the
    doubled underscore the same rule says cannot occur.

    Non-ASCII letters are dropped rather than transliterated, so `Ørsted`
    derives `rsted`. That is ugly and it is deliberate: the folder names in
    documents/applications/ were all written under this behaviour, and changing
    it would orphan every one of them."""
    s = f"{company} {role}".lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:80].strip("_")
    if not s:
        # A company and a role with no ASCII letter between them (an employer named in
        # Japanese, Greek or Cyrillic): spelled in Latin letters where a table can
        # (doc_name.ascii_name), else named by the documents' own name, which is never
        # empty (doc_name.suffix). None of these had a folder: slug() raised.
        import doc_name
        s = re.sub(r"[^a-z0-9]+", "_", doc_name.ascii_name(f"{company} {role}").lower())
        s = s.strip("_")[:80].strip("_")
        if not s and abbr:
            return re.sub(r"[^a-z0-9]+", "", abbr.lower())
    if not s:
        raise ValueError(
            "no folder name can be derived from company=%r role=%r: between them "
            "they hold no letter or digit. Ask for a company or role that does, "
            "and do not create a file or directory." % (company, role))
    if abbr:
        s += "_" + re.sub(r"[^a-z0-9]+", "", abbr.lower())
    return s


def _abbr_on_file(company, role):
    """The abbreviation the tracker's row for this application was written under."""
    import csv_store
    csv_store.refuse_conflicts(person.state("job_search_tracker.csv"))
    try:
        rows = csv_store.dict_rows(person.state("job_search_tracker.csv"), refuse=False)
    except OSError:
        return ""
    from company_key import key as company_key
    want = (company_key(company), slug("x", role))
    rx = resume_name_rx()
    for r in reversed(rows):
        got = (company_key(r.get("company")), slug("x", r.get("role") or "x"))
        m = rx.search(r.get("cv_file") or "")
        if got == want and m:
            return m.group(1)
    return ""


def without_ref(role) -> str:
    """The role without the requisition number a tracker or a board wrote into it ("Data
    Scientist II (R_1234567)", "Planner - REQ-20931"), else unchanged. The one rule for it,
    doc_name.role_core: this kept its own, and "Data Analyst - REQ-2026-0412" came back
    "Data Analyst - REQ-2026", so the folder named without the number was never found."""
    import doc_name
    return doc_name.role_core(role) or str(role or "")


def app_folder(company, role, abbr=""):
    """The folder one application lives in (documents/README.md, Subfolder naming).

    The commands wrote `<company>_<role>/` while the tools wrote
    `<company>_<role>_<abbr>/`, so /outcome and /interview missed the folder a
    batch had written and started a second one beside it. The folder already
    there wins: the full name, then the name without the abbreviation, then the
    one folder for this company and role under any abbreviation. Otherwise the
    full name, which is the rule.

    A role carrying its requisition number, "Data Scientist II (R_1234567)", is also
    looked for without it: the folder was named before the number was written into the
    tracker, and the interview pack built itself from an empty folder.
    """
    base = person.state("documents", "applications")
    abbr = abbr or _abbr_on_file(company, role)
    try:
        stem = slug(company, role)
    except ValueError:
        # No ASCII letter in the company or the role: only the documents' own name names
        # the folder (slug, above).
        if not abbr:
            raise
        return os.path.join(base, slug(company, role, abbr))
    full = slug(company, role, abbr) if abbr else stem
    bare = without_ref(role)
    plain = slug(company, bare) if bare != role else stem
    for name in dict.fromkeys((full, stem, plain)):
        if os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    try:
        hits = [d for d in sorted(os.listdir(base)) for st in dict.fromkeys((stem, plain))
                if d.startswith(st + "_") and "_" not in d[len(st) + 1:]
                and os.path.isdir(os.path.join(base, d))]
    except OSError:
        hits = []
    return os.path.join(base, hits[0] if len(hits) == 1 else full)


def employer_folders(company) -> list[str]:
    """Every application folder at this employer, by name."""
    base = person.state("documents", "applications")
    try:
        prefix = slug(company, "") + "_"
        return sorted(d for d in os.listdir(base)
                      if d.startswith(prefix) and os.path.isdir(os.path.join(base, d)))
    except (OSError, ValueError):
        return []

if __name__ == "__main__":
    if sys.argv[1:] == ["shell"]:
        print(shell())
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
