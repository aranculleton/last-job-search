#!/usr/bin/env python3
"""Where a person's documents live and what they are called. One place.

A resume is cv/<Prefix>_<ABBR>_Resume.tex and its letter is
cover_letters/<Prefix>_<ABBR>_Cover_Letter.tex, where <Prefix> is
identity.file_prefix in the profile (the person's name, "First_Last") and
<ABBR> is the human-looking name tools/doc_name.py derives from the company:
the person, then the employer, then the kind of document. Until 2026-11-06 the kind
came second (<Prefix>_Resume_<ABBR>); a document made then keeps that name,
since it may have gone to an employer under it, and every reader here knows
both orders (resume_name_rx, letter_name_rx, doc_abbr).
The prefix used to be a literal in about ten tools that had to agree, and the
tracker stores these paths, so tools/doc_name.py matches against them: they
come from here or they drift.

    python3 tools/docpaths.py shell         # the batch check's profile values, as shell assignments
    python3 tools/docpaths.py merge-twins   # one application in two folders, made one
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


LETTER_WORD = "Cover_Letter"


def new_resume_stem(abbr: str) -> str:
    """The name a resume made now takes: <Prefix>_<ABBR>_<Noun> (the maintainer, 2026-11-06:
    the person, the employer, then the kind of document)."""
    return f"{prefix()}_{abbr}_{noun_word()}"


def new_letter_stem(abbr: str) -> str:
    return f"{prefix()}_{abbr}_{LETTER_WORD}"


def old_resume_stem(abbr: str) -> str:
    """The name a resume made until 2026-11-06 has: <Prefix>_<Noun>_<ABBR>."""
    return f"{prefix()}_{noun_word()}_{abbr}"


def old_letter_stem(abbr: str) -> str:
    return f"{prefix()}_{LETTER_WORD}_{abbr}"


def general_stem(word: str) -> str:
    """A resume for no employer, named by what it is ("current", "For_Sam"):
    <Prefix>_<Noun>_<word>. No employer sits between the person and the document, so the
    word that says which one comes last, as it always has, and a kept one is still found."""
    return old_resume_stem(word)


def _made_as(folder: str, stem: str) -> bool:
    """Whether a document with this name is on disk in any form (.tex, .pdf, a template's own
    source)."""
    import glob
    return bool(glob.glob(glob.escape(person.state(folder, stem)) + ".*"))


def resume_stems(abbr: str) -> list[str]:
    """Every name this application's resume may have, the new order first."""
    return list(dict.fromkeys((new_resume_stem(abbr), old_resume_stem(abbr))))


def letter_stems(abbr: str) -> list[str]:
    return list(dict.fromkeys((new_letter_stem(abbr), old_letter_stem(abbr))))


def resume_stem(abbr: str) -> str:
    """This application's resume name: the one it was made under when it is on disk in the
    old order only (it may have been sent so, and its tracker row names it), else the new
    order. A redraft of an older application writes over its own files, never beside them."""
    new, old = new_resume_stem(abbr), old_resume_stem(abbr)
    return old if new != old and not _made_as("cv", new) and _made_as("cv", old) else new


def letter_stem(abbr: str) -> str:
    new, old = new_letter_stem(abbr), old_letter_stem(abbr)
    return (old if new != old and not _made_as("cover_letters", new)
            and _made_as("cover_letters", old) else new)


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


# The documents a draft makes. A resume for no posting (general_resume.py) has no letter, and
# neither has one the person asked for alone: `resume_only` on the pick, which staging puts on
# the draft (stage_picks.py --resume-only, the page's "Draft the resume only"). There was no
# way to ask for a resume alone, and a resume-only run named letters in the tracker that were
# never made (the maintainer, 2026-11-04).
RESUME_ONLY = "resume_only"


def has_letter(draft: dict | None) -> bool:
    """Whether this draft makes a cover letter: the one answer every step reads (the drafter's
    brief, the audits, the render, the checks, the note and the tracker row)."""
    d = draft if isinstance(draft, dict) else {}
    return not (d.get("general") or d.get(RESUME_ONLY))


LETTER_FIELDS = ("p1", "p2", "lead", "cl_bullets", "p4")


def writes_letter(draft: dict | None) -> bool:
    """Whether a drafted application has a letter to name: has_letter, and, for a draft (an
    object carrying a summary), a letter field with words in it. A letterless draft not
    marked resume-only still had its letter named in the tracker, and the file found on
    disk from an earlier render passed the check (the maintainer, 2026-11-05). A pick or a
    staging record carries no letter fields, and is answered by has_letter alone."""
    if not has_letter(draft):
        return False
    d = draft if isinstance(draft, dict) else {}
    if "summary" not in d:
        return True
    return any(str((x.get("text") if isinstance(x, dict) else x) or "").strip()
               for k in LETTER_FIELDS
               for x in (d.get(k) if isinstance(d.get(k), list) else [d.get(k)]))


def made(rel: str) -> bool:
    """Whether a document the tracker would name (its repo-relative path, as cv_file and
    cover_letter_file store it) is on disk: its .tex or its .pdf."""
    rel = str(rel or "").strip()
    if not rel:
        return False
    stem = os.path.splitext(rel)[0]
    return any(os.path.isfile(person.state(stem + ext)) for ext in (".tex", ".pdf"))


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
    # The one the app made (general_resume.py: <Prefix>_<Noun>_current.pdf), first: beside
    # a hand-made "..._CURRENT_2026-09.pdf", two names said current, only one was dated, and
    # nothing could be told, so the fresh one the person asked for was never offered.
    own = "/".join(GENERAL_DIR + (general_stem("current") + ".pdf",))
    if own in files:
        return own

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


_NEVER_SEND = re.compile(r"never send|do not send|don'?t send|not to be sent|must never be sent", re.I)


def never_sent(rel_path: str) -> bool:
    """Does the person's own profile/CLAUDE.md name this file in a line saying never to send
    it? "Do not send it" beside the hand-made ..._CURRENT_2026-09.pdf is the rule."""
    base = os.path.basename(str(rel_path or "")).lower()
    if not base:
        return False
    try:
        with open(person.path("CLAUDE.md"), encoding="utf-8") as f:
            text = f.read()
    except (OSError, person.NoProfile):
        return False
    return any(base in line.lower() and _NEVER_SEND.search(line) for line in text.splitlines())


def resume_to_offer() -> str:
    """The resume that may be offered or attached when someone asks for "your resume", or "".
    Only the one the app made and checked (general_resume.py's own `_current` file), which
    breaks none of the person's rules and which their profile does not say never to send. An
    older hand-made file is never it, however it is named (2026-11-04: reply guidance pointed
    at a ..._CURRENT_2026-09.pdf the person's rules forbid). "" means make one for them."""
    own = "/".join(GENERAL_DIR + (general_stem("current") + ".pdf",))
    if own not in general_resumes() or never_sent(own) or resume_problems(own):
        return ""
    return own


_problems_cache: dict = {}


def resume_problems(rel_path: str) -> list[str]:
    """What in a resume to send as it is breaks the person's own rules, in plain words, or
    [] when nothing does: check_claims.py's errors (the dashes, the spelling, the document's
    noun, a skill not held, the profile's own claim rules) read off its text. A resume the
    person keeps in documents/cv/ was offered for download and to a contact as it was, and
    the one offered said "standardising" and "modeling" with en dashes in its dates: their
    profile said never to send it (2026-11-03). A PDF nothing here can read is said so."""
    path = person.state(*str(rel_path).split("/"))
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (path, st.st_mtime, st.st_size)
    if _problems_cache.get("key") == key:
        return list(_problems_cache["out"])
    out: list[str] = []
    text = ""
    if path.lower().endswith(".pdf"):
        import pdftext
        # A file nothing here can read is not known to break anything: it is not held back.
        try:
            text = pdftext.text(path)
        except pdftext.Unreadable:
            text = ""
    elif path.lower().endswith(".docx"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            text = re.sub(r"<[^>]+>", " ", re.sub(r"</w:p>", "\n", xml))
        except (OSError, KeyError, zipfile.BadZipFile):
            text = ""
    if text:
        import check_claims
        seen = []
        for sev, name, snippet, _why in check_claims.check_text(text):
            if sev == "ERROR" and name not in seen:
                seen.append(name)
                out.append(_PLAIN_RULE.get(name, name.replace("-", " ")) + ' ("%s")'
                           % " ".join(snippet.split())[:40])
    _problems_cache.update(key=key, out=out)
    return list(out)


_PLAIN_RULE = {"em-dash": "a dash your rules ban", "british-ise-spelling": "British spelling",
               "american-spelling": "American spelling", "unheld-skill": "a skill you do not hold",
               "duplicated-word": "a word said twice", "unsupported-status": "a status you do not hold",
               "figure-drift": "a figure that differs from your profile"}


def _name_rx(word: str) -> re.Pattern:
    """A document's filename in either order, <Prefix>_<ABBR>_<word> (now) or
    <Prefix>_<word>_<ABBR> (until 2026-11-06), capturing the ABBR as group 1."""
    p, w = re.escape(prefix()), re.escape(word)
    return re.compile(p + "_(?=" + w + "_|[A-Za-z0-9_]*?_" + w + "(?![A-Za-z0-9_]))"
                      "(?:" + w + "_)?([A-Za-z0-9_]+?)(?:_" + w + ")?(?![A-Za-z0-9_])")


def resume_name_rx() -> re.Pattern:
    """Matches a resume filename, in the order made now or the order used until 2026-11-06, and
    captures its ABBR."""
    return _name_rx(noun_word())


def letter_name_rx() -> re.Pattern:
    """Matches a cover letter's filename, in either order, and captures its ABBR."""
    return _name_rx(LETTER_WORD)


# The words an app-made document's name has carried for its kind, whatever the profile's
# noun is now: a row written under "Resume" stays readable after the noun became "CV".
KIND_WORDS = ("Resume", "CV", LETTER_WORD)


def doc_abbr(name: str) -> str:
    """The ABBR in an app-made resume or letter's file name or path, in either order, or ""."""
    stem = os.path.splitext(os.path.basename(str(name or "").strip()))[0]
    words = list(dict.fromkeys((noun_word(), *KIND_WORDS)))
    for w in words:
        m = _name_rx(w).fullmatch(stem)
        if m:
            return m.group(1)
    alt = "|".join(re.escape(w) for w in words)
    m = re.search(r"_(?:%s)_([A-Za-z0-9_]+)$" % alt, stem) or \
        re.search(r"^[A-Za-z0-9]+_[A-Za-z0-9]+_([A-Za-z0-9_]+?)_(?:%s)$" % alt, stem)
    return m.group(1) if m else ""


# ------------------------------------------------------------ the name an employer sees
#
# What the PDF the person downloads and uploads is called (the maintainer, 2026-11-06: "a
# setting for what to put for file names ... don't overwhelm the user, sensible defaults ...
# use standards"). The kept file in cv/ and cover_letters/ is always <Prefix>_<ABBR>_<Noun>,
# whatever is chosen: the tracker names it, and two applications' files must never share a
# name, which "your name and the document" alone would. So the setting shapes only the copy
# that leaves: the page's download (app_model files' `send`) and the chat's copy
# (tools/shown.py). What the guidance says, read 2026-11-06:
#   - CSUN Career Center, "The (Simple) Guidelines You Should Follow When Naming Your Resume
#     and Cover Letter Files" (nazariancareers.csun.edu/blog/2021/08/26/the-simple-
#     guidelines-you-should-follow-when-naming-your-resume-and-cover-letter-files/): your
#     first and last name and what the file is; the position and organisation optional, to
#     show it was tailored; a posting's own naming instruction comes first; no slashes, no
#     version numbers.
#   - StylingCV, "How to name your resume file" (stylingcv.com/blog/how-to-name-your-resume-
#     file-2026/): FirstName-LastName-Resume, or with the company and position when tailored;
#     standard ASCII characters; no spaces or symbols (@ # $ % & *); "aim for under 40
#     characters".
#   - Resume Worded (resumeworded.com/resume-file-name-cover-letter-filename-key-advice):
#     your name, "resume" or "cover letter" and the position; A-Z, 0-9, dashes and
#     underscores only, no accents; spaces can become "%20" in some tracking systems; "it
#     doesn't matter which order"; it would leave the company out, the one source that does.
#   - CV Wizard (cvwizard.com/uk/articles/resume-cv-difference) and LiveCareer UK
#     (livecareer.co.uk/cv/resume-vs-cv): "CV" in the UK and Ireland, "resume" in the US and
#     most of Canada, either in Australia. That word is the person's documents.noun, which
#     /setup takes from their market (tools/markets/<cc>.json, documents "noun").
# None of them makes the parts or their order depend on industry, role or seniority (an
# academic CV is a different document, not a different name), and none differs by country
# beyond the word for the document. So one default everywhere, the word by market: the
# person, the employer (they apply to many, and download many), then the document.
FILE_NAMES_KEY = "documents.file_names"
FILE_NAME_PRESETS = (
    ("name_employer_document", "Name, employer, document", ("employer",)),
    ("name_document", "Name, document", ()),
    ("name_employer_role_document", "Name, employer, role, document", ("employer", "role")),
)
FILE_NAMES_DEFAULT = "name_employer_document"
# The most a name runs to before its extension: under the 40 to 50 the guidance asks for
# where it can be, with the person's name and the document word never cut.
FILE_NAME_MAX = 50


def recommended_file_names(country: str = "") -> str:
    """The preset recommended for a market: the same in every one (the sources above differ
    by country only in the document's word, which documents.noun carries)."""
    return FILE_NAMES_DEFAULT


def file_names() -> str:
    """The person's choice (person.json documents.file_names), else the recommended one."""
    try:
        got = str(person.get(FILE_NAMES_KEY, "") or "").strip()
    except Exception:  # noqa: BLE001  no profile: the default
        got = ""
    known = [p[0] for p in FILE_NAME_PRESETS]
    if got in known:
        return got
    try:
        country = str(person.get("identity.country", "") or "")
    except Exception:  # noqa: BLE001
        country = ""
    return recommended_file_names(country)


def _plain_words(text: str) -> list[str]:
    """Words safe in any file name on any portal: ASCII letters and digits, accents folded,
    "&" as "and", apostrophes and full stops dropped (Kestrel & Co. -> Kestrel_and_Co)."""
    import doc_name
    t = doc_name.ascii_name(str(text or "")).replace("&", " and ")
    t = re.sub(r"['’.]", "", t)
    return re.findall(r"[A-Za-z0-9]+", t)


# Words that only join others: a cut never ends on one ("Head_of").
_JOINERS = {"of", "for", "and", "the", "in", "at", "to", "de", "du", "la", "le", "et", "und",
            "y", "e", "da", "do", "di", "van", "von"}


def _employer_words(employer: str) -> list[str]:
    """The employer as people say it: its legal and generic tail dropped, as the kept name's
    own (doc_name.GENERIC: "Kestrel Foods & Co." is Kestrel_Foods), never to nothing."""
    import doc_name
    words = _plain_words(employer)
    while len(words) > 1 and (words[-1].lower() in doc_name.GENERIC
                              or words[-1].lower() in _JOINERS):
        words.pop()
    if len(words) > 1 and words[0].lower() == "the":
        words.pop(0)
    return words


def _trim_end(words: list[str], room: int) -> list[str]:
    """The first words that fit in `room` characters, never ending on a joining word."""
    out = []
    for w in words:
        if len("_".join(out + [w])) > room:
            break
        out.append(w)
    while out and out[-1].lower() in _JOINERS:
        out.pop()
    return out


def _role_words(words: list[str], room: int) -> list[str]:
    """A role cut to `room` characters the way a title reads: whole where it fits; "Head of
    Supply Chain Planning" keeps its head and the words after it that fit (Head_of_Supply_
    Chain); otherwise the words before its last are what go ("Senior Demand Planning Analyst"
    is Demand_Planning_Analyst, then Planning_Analyst, then Analyst), since the last word is
    the job. [] when not even that fits."""
    if len("_".join(words)) <= room:
        return list(words)
    at = next((i for i, w in enumerate(words) if i and w.lower() in ("of", "for")), None)
    if at is not None:
        got = _trim_end(words, room)
        return got if len(got) > at + 1 else []
    for i in range(1, len(words)):
        if len("_".join(words[i:])) <= room:
            return words[i:]
    return []


def file_name(kind_word: str, employer: str = "", role: str = "", preset: str | None = None,
              ext: str = ".pdf", fallback: str = "") -> str:
    """The name a document leaves under, by the preset (the person's own when None): the
    person's prefix, then the employer and the role where the preset has them, then the
    document's word (their noun, or Cover_Letter), in at most FILE_NAME_MAX characters. The
    person's name and the document's word are never cut; the role is cut first, the way a
    title reads (_role_words), then the employer from its end. `fallback` stands for an
    employer that has no letter to show."""
    import doc_name
    preset = preset or file_names()
    has = dict((p[0], p[2]) for p in FILE_NAME_PRESETS).get(preset, ("employer",))
    head = "_".join(_plain_words(prefix().replace("_", " "))) or prefix()
    room = FILE_NAME_MAX - len(head) - len(kind_word) - 2
    emp = (_employer_words(employer) or _employer_words(fallback)) if "employer" in has else []
    # With a role to follow, the employer takes at most half the room, so the role's last
    # word (the job) still fits; alone, all of it.
    emp_room = room // 2 if "role" in has and role else room
    emp = _trim_end(emp, emp_room) or emp[:1]
    parts = ["_".join(emp)] if emp else []
    if "role" in has:
        left = room - (len(parts[0]) + 1 if parts else 0)
        got = _role_words(_plain_words(doc_name.role_core(role) or role), left)
        if got:
            parts.append("_".join(got))
    return "_".join([head, *parts, kind_word]) + ext


def example_file_name(preset: str | None = None, employer: str = "", role: str = "") -> str:
    """What a resume would leave as under a preset, for the setting's own row: the person's
    own name and, where given, a real recent employer and role."""
    return file_name(noun_word(), employer or "Employer", role or "Analyst", preset)


def send_name(name: str, company: str = "", role: str = "", preset: str | None = None) -> str:
    """The name a made document is downloaded and uploaded under (file_name), whichever order
    the kept file was made in. With no employer (a resume for no posting) it is the person's
    name and the document; a name that is not an app-made document's comes back as it is."""
    base = os.path.basename(str(name or "").strip())
    stem, ext = os.path.splitext(base)
    try:
        words = list(dict.fromkeys((noun_word(), *KIND_WORDS)))
        prefix()
    except Exception:  # noqa: BLE001  no profile: the name as it is
        return base
    for w in words:
        m = _name_rx(w).fullmatch(stem)
        if m:
            return file_name(w, company, role, preset, ext)
    return base


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

def _abbr_text(abbr) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(abbr or "").lower())


def only_the_employer(company, abbr) -> bool:
    """Whether the abbreviation is only the employer's own name, or the start of it
    ("Kestrel" or "KestrelMutual" for Kestrel Mutual). The folder name already starts with
    the employer, so such a suffix said it twice: kestrel_mutual_analyst_kestrel. Only one
    application at an employer is ever filed under its plain name (stage_picks.choose_abbr
    gives every other one a role token), so leaving it off never joins two applications."""
    a = _abbr_text(abbr)
    words = re.findall(r"[a-z0-9]+", str(company or "").lower())
    return bool(a) and any("".join(words[:k]) == a for k in range(1, len(words) + 1))


def slug(company, role, abbr="", _always=False):
    """Directory name for one application. The abbreviation is part of it, so
    two roles at one employer with the same title (one employer posted "Senior
    Business Analyst" twice), or two long titles that agree for eighty
    characters (one role advertised in two cities), never overwrite each other.
    An abbreviation that is only the employer's own name is left off
    (only_the_employer): the name already starts with the employer. `_always` gives
    the name every folder had before 2026-10-26, the abbreviation always appended.

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
    if abbr and (_always or not only_the_employer(company, abbr)):
        s += "_" + _abbr_text(abbr)
    return s


# (path, mtime_ns, size) -> {(employer key, role slug): abbr}. Every caller asks for one
# application, and the due list asks for every live one: each call read the whole tracker
# again and keyed every row, so 500 rows took 14 seconds (2026-10-25). The tracker is read
# once for each state of the file.
_ABBR_INDEX: dict = {}


def _abbr_index(path):
    import csv_store
    from company_key import key as company_key
    st = os.stat(path)
    stamp = (path, st.st_mtime_ns, st.st_size)
    got = _ABBR_INDEX.get(stamp)
    if got is not None:
        return got
    csv_store.refuse_conflicts(path)
    rows = csv_store.dict_rows(path, refuse=False)
    rx = resume_name_rx()
    got = {}
    for r in rows:                     # the last row written under a name wins, as before
        m = rx.search(r.get("cv_file") or "")
        if m:
            got[(company_key(r.get("company")), slug("x", r.get("role") or "x"))] = m.group(1)
    _ABBR_INDEX.clear()
    _ABBR_INDEX[stamp] = got
    return got


def forget_abbreviations() -> None:
    """Read the tracker again on the next ask: a writer in this process changed it within
    the file system's clock step (two seconds on some), so its time and size can match."""
    _ABBR_INDEX.clear()


def _abbr_on_file(company, role):
    """The abbreviation the tracker's row for this application was written under."""
    from company_key import key as company_key
    try:
        index = _abbr_index(person.state("job_search_tracker.csv"))
    except OSError:
        return ""
    return index.get((company_key(company), slug("x", role)), "")


def without_ref(role) -> str:
    """The role without the requisition number a tracker or a board wrote into it ("Data
    Scientist II (R_1234567)", "Planner - REQ-20931"), else unchanged. The one rule for it,
    doc_name.role_core: this kept its own, and "Data Analyst - REQ-2026-0412" came back
    "Data Analyst - REQ-2026", so the folder named without the number was never found."""
    import doc_name
    return doc_name.role_core(role) or str(role or "")


def folder_names(company, role, abbr) -> list[str]:
    """The names an application filed under `abbr` may have on disk, the one to look for
    first first: the name every folder had before 2026-10-26 (the abbreviation always
    appended, so kestrel_mutual_analyst_kestrel), then the name the rule gives now. Most
    applications on disk are older than the change, and a folder written under the old
    name stays that application's folder. Raises ValueError as slug() does."""
    if not abbr:
        return [slug(company, role)]
    return list(dict.fromkeys((slug(company, role, abbr, _always=True),
                               slug(company, role, abbr))))


def app_folder(company, role, abbr=""):
    """The folder one application lives in (documents/README.md, Subfolder naming). Every
    tool that writes into an application's folder or reads one asks here, so one
    application has one folder.

    With `abbr`, the name its documents were written under, it is that application's own
    folder: one already on disk under either name (folder_names), else the name the rule
    gives. verify_batch.py named it without the abbreviation while outreach.py named it
    with, so one application's checks and its note sat in two folders (2026-10-26).

    Without one, the abbreviation is read off the tracker's row, and an older folder is
    looked for as well. The commands wrote `<company>_<role>/` while the tools wrote
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
    given = bool(abbr)
    abbr = abbr or _abbr_on_file(company, role)
    try:
        stem = slug(company, role)
    except ValueError:
        # No ASCII letter in the company or the role: only the documents' own name names
        # the folder (slug, above).
        if not abbr:
            raise
        return os.path.join(base, slug(company, role, abbr))
    names = folder_names(company, role, abbr)
    full = names[-1]
    if given:
        # Never another application's folder: the name without the abbreviation can be one.
        for name in names:
            if os.path.isdir(os.path.join(base, name)):
                return os.path.join(base, name)
        return os.path.join(base, full)
    bare = without_ref(role)
    plain = slug(company, bare) if bare != role else stem
    for name in dict.fromkeys((*names, stem, plain)):
        if os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    try:
        hits = [d for d in sorted(os.listdir(base)) for st in dict.fromkeys((stem, plain))
                if d.startswith(st + "_") and "_" not in d[len(st) + 1:]
                and os.path.isdir(os.path.join(base, d))]
    except OSError:
        hits = []
    return os.path.join(base, hits[0] if len(hits) == 1 else full)


# ------------------------------------------------------------ one application in two folders

# The files that make a folder an application of its own: a folder holding neither is what
# a tool that missed the abbreviation left beside the real one (verify_batch.py's verify.json).
_OWN = ("draft.json", "job_posting.md")


def _source(folder) -> str:
    try:
        with open(os.path.join(folder, "job_posting.md"), encoding="utf-8") as fh:
            m = re.search(r"\*\*Source:\*\*\s*(\S+)", fh.read(4000))
        return m.group(1) if m else ""
    except OSError:
        return ""


def twin_folders(base=None) -> list[tuple[str, str]]:
    """[(stray, home)]: a folder that is another folder's name without its abbreviation and
    holds the same application, so its files belong in the other. It is the same
    application when it holds no application of its own (no draft.json or job_posting.md)
    or the same posting (the same Source line). Where several folders carry the name and
    an abbreviation, the stray's verify.json names which one; otherwise it is left alone."""
    base = base or person.state("documents", "applications")
    try:
        names = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    except OSError:
        return []
    out = []
    for a in names:
        sibs = [b for b in names if b.startswith(a + "_") and "_" not in b[len(a) + 1:]]
        if not sibs:
            continue
        stray = os.path.join(base, a)
        home = sibs[0] if len(sibs) == 1 else None
        try:
            with open(os.path.join(stray, "verify.json"), encoding="utf-8") as fh:
                named = a + "_" + _abbr_text(json.load(fh).get("abbr"))
            home = named if named in sibs else home
        except (OSError, ValueError, AttributeError):
            pass
        if home is None:
            continue
        own = any(os.path.exists(os.path.join(stray, f)) for f in _OWN)
        if own and not (_source(stray) and _source(stray) == _source(os.path.join(base, home))):
            continue
        out.append((stray, os.path.join(base, home)))
    return out


def _stamp(path) -> str:
    """When a file was made: a JSON record's own `at`, else its time on disk."""
    try:
        with open(path, encoding="utf-8") as fh:
            at = json.load(fh).get("at")
        if isinstance(at, str) and at:
            return at
    except (OSError, ValueError, AttributeError):
        pass
    import datetime as dt
    return dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_twins(base=None) -> list[str]:
    """Each stray's files moved into its home, and the stray removed: a file the home
    lacks is moved; the same file in both is kept once; two different copies keep the
    newer under its own name and the older beside it as <name>.earlier<ext>, so nothing is
    lost. Returns a line for each folder merged."""
    import filecmp
    import shutil
    lines = []
    for stray, home in twin_folders(base):
        moved = 0
        for root, _dirs, files in os.walk(stray):
            # Below the stray itself, so on its drive: the same place below the home.
            rel = root[len(stray):].lstrip("/\\")
            for f in files:
                src = os.path.join(root, f)
                dst = os.path.normpath(os.path.join(home, rel, f))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                elif filecmp.cmp(src, dst, shallow=False):
                    os.remove(src)
                else:
                    stem, ext = os.path.splitext(dst)
                    older, n = stem + ".earlier" + ext, 2
                    while os.path.exists(older):
                        older, n = f"{stem}.earlier{n}{ext}", n + 1
                    if _stamp(src) > _stamp(dst):
                        shutil.move(dst, older)
                        shutil.move(src, dst)
                    else:
                        shutil.move(src, older)
                moved += 1
        shutil.rmtree(stray, ignore_errors=True)
        lines.append(f"{os.path.basename(stray)}: {moved} file(s) moved into "
                     f"{os.path.basename(home)}")
    return lines


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
    elif sys.argv[1:] == ["merge-twins"]:
        # One application in two folders, made one (profile upgrade one-folder-each).
        for line in merge_twins():
            print(line)
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
