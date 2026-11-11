#!/usr/bin/env python3
"""A resume for no posting in particular: the one a person sends when nobody named a role.

Made at the end of setup for someone who had no resume (they built their history with
Claude, setup-sections.md `history`), and on request ("build my resume") for anyone. It is
the same document every application gets, drafted from the same profile and rendered,
fitted and checked by the same tools, with two differences: the "posting" it is aimed at is
a short description of the roles the person is searching for, written here from their
search settings and the skills they hold; and there is no cover letter.

    python3 tools/stage_picks.py general <dir>                   # draft, render, check, keep
    python3 tools/stage_picks.py general <dir> --summary-file F  # the summary Claude wrote
    python3 tools/stage_picks.py general <dir> --style navy      # this resume's own colour
    python3 tools/stage_picks.py general <dir> --role "Data Analyst"

<dir> is a scratch folder for the draft and its checks. What it keeps is the PDF and a
plain-text copy in documents/cv/ (`<Prefix>_<Noun>_current.pdf` and `.txt`), the place the
app looks for the resume to send when no role is named (tools/docpaths.py current_resume).

The summary is the profile's own Canonical Summary Statement (01-candidate-profile.md)
unless Claude wrote one for this resume (`--summary-file`, with its claim map in
`--claims-file`), which the grounding audit reads as it reads any summary (`grounding`): a
question it raises keeps the resume from being made. Its colour: the draft's own `--style`, else person.json
`documents.styles` `default`, else the style mapped to the kind of employer most of their
target employers are (profile/boards.py, as templates/doc_style.py reads a kind), else black.

Every file is read and written as UTF-8 and every path is joined by os.path, so the one
command runs the same on Windows, a Mac, Linux and a cloud chat. Exit 0 when it is kept
with every check passed, 1 when a check failed or it could not be rendered.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(HERE, "network"), os.path.join(ROOT, "templates")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import docpaths  # noqa: E402
import local_path  # noqa: E402
import person  # noqa: E402

COMPANY = "General"       # the draft's employer: names its files <Prefix>_General_<Noun>
SLUG = "general"
KEEP_SUFFIX = "current"   # documents/cv/<Prefix>_<Noun>_current.pdf: current_resume() finds it
TITLES = 3                # how many of the search's titles the description names
SHORT_BULLETS = 1         # bullets per role in the short copy pasted into the reply


def _cap(words: str) -> str:
    """A search title as a heading: "supply chain analyst" -> "Supply Chain Analyst", and a
    word already written with a capital ("BI", "dbt") left as it is."""
    small = {"and", "of", "the", "for", "in", "to", "a", "an"}
    out = []
    for i, w in enumerate(str(words or "").split()):
        out.append(w if any(c.isupper() for c in w) or (i and w in small) else w.capitalize())
    return " ".join(out)


def target_roles() -> list[str]:
    """The roles they search for, in their order: search.py SCRAPE_QUERIES."""
    try:
        got = list(getattr(person.module("search"), "SCRAPE_QUERIES", []) or [])
    except person.NoProfile:
        got = []
    seen, out = set(), []
    for t in got:
        t = str(t or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(_cap(t))
    return out


def held_skills() -> list[str]:
    """Every skill skills.py ITEMS holds, in its order, without the ones it shows only when
    a posting names them (SECONDARY): a general resume answers no posting."""
    sk = person.module("skills")
    secondary = set(getattr(sk, "SECONDARY", ()) or ())
    out = []
    for item in getattr(sk, "ITEMS", []) or []:
        name = item[1]
        if name not in secondary and name not in out:
            out.append(name)
    return out


def describe(roles: list[str], skills: list[str]) -> str:
    """What the allocator reads in place of a posting: the roles and the skills held, so the
    bullets that answer the search most often are the ones on the page."""
    noun = person.get("documents.noun", "resume")
    head = ", ".join(roles[:TITLES]) or "the roles in this search"
    return (f"A general {noun} for {head}, answering no posting in particular: the "
            f"strongest work for these roles. Skills held: {', '.join(skills)}.")


def canonical_summary() -> str:
    """The profile's Canonical Summary Statement, as one paragraph, or ""."""
    import profile_facts
    path = person.file("candidate_profile", "01-candidate-profile.md")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    return profile_facts.summary(profile_facts.sections(lines))


def _target_employers() -> list[str]:
    try:
        return list(getattr(person.module("boards"), "BOARDS", {}) or {})
    except person.NoProfile:
        return []


def style_for(own: str = "") -> tuple[str, str]:
    """(style, why) for the general resume. The kind is the one most of the employers in
    boards.py are, among the kinds documents.styles maps; a tie goes to the first named."""
    import doc_style
    if str(own or "").strip():
        return doc_style.check(own.strip(), "--style"), "this resume's own choice"
    s = doc_style.setting()
    if s.get("default"):
        return (doc_style.check(s["default"], "person.json documents.styles default"),
                "documents.styles default")
    kinds = s.get("kinds") or {}
    if kinds:
        counts, first = collections.Counter(), {}
        for i, name in enumerate(_target_employers()):
            for k in doc_style.kinds_of(name):
                if k in kinds:
                    counts[k] += 1
                    first.setdefault(k, i)
                    break
        if counts:
            kind = max(counts, key=lambda k: (counts[k], -first[k]))
            return kinds[kind], f"most of their target employers are a {kind}"
    return doc_style.DEFAULT, "no style is set"


def draft(role: str = "", style: str = "", summary: str = "") -> dict:
    """The general draft: everything render_application.build() reads, with the letter's
    fields empty, as no letter is made."""
    roles = target_roles()
    if role:
        roles = [_cap(role)] + [r for r in roles if r.lower() != role.strip().lower()]
    skills = held_skills()
    text = str(summary or "").strip() or canonical_summary()
    if not text:
        # Written into the profile, not only passed in: with --summary-file alone the same
        # stop came back every time the resume was made again (the stranger audit, X-73).
        raise SystemExit("general: the profile has no Canonical Summary Statement "
                         "(01-candidate-profile.md) and no --summary-file was given. Write two "
                         "or three sentences from the profile into 01-candidate-profile.md "
                         "under the exact heading \"## Canonical Summary Statement\", as a \"> \" "
                         "quote (profile.example/01-candidate-profile.md shows it), save it, "
                         "and run this again.")
    name, why = style_for(style)
    a = {"company": COMPANY, "role": roles[0] if roles else _cap(person.get("documents.noun",
                                                                            "resume")),
         "general": True, "posting": describe(roles, skills), "summary": text,
         "tools": ", ".join(skills), "p1": "", "p2": "", "lead": "", "cl_bullets": [],
         "p4": "", "style_why": why}
    if name != "black" or why != "no style is set":
        a["style"] = name
    return a


def grounding(a: dict, claims=None) -> list[str]:
    """The grounding audit's own questions of the general resume's summary, each in one line,
    or [] when it rests on the profile: the code half of the audit every resume made for a
    posting gets (tools/draft_audit.py grounding_flags), never a second set of rules. The
    profile's own Canonical Summary Statement rests on it word for word (SUMMARY); a summary
    Claude wrote carries its claim map (`claims`: each sentence with the ids it rests on,
    from draft_pack's evidence), and any question code raises keeps it from being kept: a
    general resume has no model auditor to rule on one, so it is written again from what the
    cited text says. A general resume took a written summary with no audit at all (the
    maintainer, 2026-11-06: "the fact-checking against the profile only runs on resumes
    made for a posting")."""
    import draft_audit
    text = str(a.get("summary") or "").strip()
    if not text:
        return []
    d = {"summary": text, "claim_map": claim_map(a, claims)}
    flags = draft_audit.grounding_flags(d, {"company": COMPANY, "role": a.get("role") or ""},
                                        a.get("posting") or "", None)
    import check_claims
    out = [f"{f['flag']}: \"{f['sentence']}\": {f['detail']}" for f in flags]
    out += [f"{name}: \"{snip}\": {why}" for sev, name, snip, why in check_claims.check_text(text)
            if sev == "ERROR"]
    return out


def claim_map(a: dict, claims=None) -> list[dict]:
    """The summary's claim map: the one given, or, for the profile's own Canonical Summary
    Statement, each sentence resting on it (SUMMARY). Kept on the draft, so a summary reworded
    from the pencil is audited against what it rested on, as an application's is."""
    import draft_audit
    text = str(a.get("summary") or "").strip()
    if claims is None and text and text == canonical_summary().strip():
        claims = [{"field": "summary", "sentence": s, "cites": ["SUMMARY"]}
                  for s in draft_audit._sentences(text)]
    return [dict(c, field=c.get("field") or "summary") for c in claims or []
            if isinstance(c, dict)]


def plain_text(a: dict, short: bool = False) -> str:
    """The resume as plain text, in page order, from the same lines the PDF is checked
    against (verify_pdf.roundtrip_fields). `short` keeps the name, the summary, each role's
    heading and its first bullet, and the skills: what fits in a reply."""
    import verify_pdf
    groups = verify_pdf.roundtrip_fields(copy.deepcopy(a))
    out, bullets, skipping = [], collections.Counter(), False
    for label, fields in groups:
        texts = dict(fields)
        if label == "Contact details":
            out.append(texts.get("your name", ""))
            rest = [t for w, t in fields if w != "your name"]
            if rest and not short:
                out.append(" | ".join(rest))
        elif label.startswith("the heading "):
            heading = texts.get("heading", "")
            skipping = short and heading in _short_skip()
            if not skipping:
                out += ["", heading.upper()]
        elif skipping:
            continue
        elif label.endswith(", its heading line"):
            out.append(f"{texts.get('title', '')}, {texts.get('employer', '')} "
                       f"({texts.get('dates', '')})")
        elif ", bullet " in label:
            employer = label.split(", bullet ")[0]
            bullets[employer] += 1
            if not short or bullets[employer] <= SHORT_BULLETS:
                out.append("- " + fields[0][1])
        else:
            out += [t for _w, t in fields]
    return "\n".join(out).strip() + "\n"


def _short_skip() -> set:
    heads = person.get("documents.headings") or {}
    return {heads.get("education", "Education"), heads.get("certifications", "Certifications")}


def keep_paths(for_contact: str = "") -> tuple[str, str]:
    """Where it is kept: documents/cv/ for the person's own, or, made for a contact who asked
    for one, their own folder (documents/network/<id>/), named for them, so it never takes
    the place of the person's own (a person's copy, 2026-11-05: one made for a recruiter
    replaced "Your resume", and nothing on his card said it had been made for him)."""
    if for_contact:
        # Named as the person's own resume (<Prefix>_<Noun>): the contact receives the file,
        # and "..._Resume_For_<them>.pdf" told them it was made for them (a person's copy,
        # 2026-11-10). Their own folder keeps it apart from the person's own.
        stem = f"{docpaths.prefix()}_{docpaths.noun_word()}"
        folder = person.state("documents", "network", for_contact)
        return os.path.join(folder, stem + ".pdf"), os.path.join(folder, stem + ".txt")
    stem = docpaths.general_stem(KEEP_SUFFIX)
    folder = person.state(*docpaths.GENERAL_DIR)
    return os.path.join(folder, stem + ".pdf"), os.path.join(folder, stem + ".txt")


FOR_CONTACT_RECORD = "resume.json"     # in documents/network/<id>/: the resume made for them
# The person's own general resume as a draft, beside its PDF: what the Tweak panel changes (its
# bullets, its look, its summary through both audits, tools/tweak.py), as an application's
# documents/applications/<slug>/draft.json is. The person could not choose its bullets (the
# maintainer, 2026-11-06).
DRAFT_DIR = ("documents", "cv", "general")


def draft_file() -> str:
    """documents/cv/general/draft.json: the kept draft of the person's own general resume."""
    return person.state(*DRAFT_DIR, "draft.json")


def keep_draft(a: dict) -> str:
    """Keep the general draft as rendered (its bullets chosen), for the Tweak panel."""
    path = draft_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump([a], fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return path


def keep_again(path: str = "") -> bool:
    """After a change made to the kept draft (tools/tweak.py renders and checks it), the
    resume sent when nobody named a role is that one: its PDF and plain-text copy in
    documents/cv/ made again from it. False when there is no rendered PDF to keep."""
    import fit_to_page as F
    path = path or draft_file()
    try:
        apps, _read_in = F.load(path)
    except (OSError, ValueError):
        return False
    if not apps:
        return False
    a = apps[0]
    src = docpaths.resume_pdf(a.get("abbr") or "")
    if not a.get("abbr") or not os.path.isfile(src):
        return False
    pdf, txt = keep_paths()
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    shutil.copyfile(src, pdf)
    with open(txt, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(plain_text(a))
    return True


def bullets_on(a: dict) -> list[dict]:
    """The bullets on the kept general resume, in page order: {id, employer, text}, the text
    plain, for the Tweak panel's Bullets row."""
    import bullet_rewording
    out = []
    for j in a.get("jobs") or []:
        for b in j.get("bullets") or []:
            text = bullet_rewording.plain(bullet_rewording.original(b) or "") or b
            out.append({"id": b, "employer": str(j.get("employer") or ""), "text": text})
    return out


def keep_for_contact(contact_id: str, pdf: str, today: str = "") -> str:
    """Record on the contact who asked that this resume was made for them: their card shows
    it, and it is found by their name. Returns the record's path."""
    import datetime as dt
    path = person.state("documents", "network", contact_id, FOR_CONTACT_RECORD)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"for": contact_id, "file": local_path.rel(pdf, person.state()).replace(os.sep, "/"),
                   "made_on": today or dt.date.today().isoformat(), "job": None}, fh, indent=1)
        fh.write("\n")
    return path


def _verify(drafts_path: str) -> tuple[int, str]:
    """verify_batch on the one draft: the Python port where it exists, which runs on any
    computer, else the shell script."""
    py = os.path.join(HERE, "verify_batch.py")
    if os.path.exists(py):
        cmd = [sys.executable, py, drafts_path]
    elif local_path.bash():
        # A full path: a bare "bash" on Windows reaches WSL's launcher (local_path.bash).
        cmd = [local_path.bash(), os.path.join(HERE, "verify_batch.sh"), drafts_path]
    else:
        return 3, "verify_batch: not run, as this computer has neither its Python port nor bash"
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def make(out_dir: str, role: str = "", style: str = "", summary: str = "",
         keep: bool = True, check: bool = True, for_contact: str = "", claims=None) -> dict:
    """Draft, render and fit it, check it, and keep it. Returns what happened:
    {"draft", "drafts", "pages", "lines", "verify", "verify_out", "pdf", "txt", "kept",
    "grounding"}. A summary the grounding audit questions (`grounding`) is never rendered."""
    import fit_to_page as F
    import render_application as R
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(person.state("cv"), exist_ok=True)
    a = draft(role, style, summary)
    asked = grounding(a, claims)
    a["claim_map"] = claim_map(a, claims)
    if asked:
        return {"draft": a, "drafts": "", "pages": 0, "lines": 0, "verify": 1,
                "verify_out": "", "pdf": "", "txt": "", "kept": False, "grounding": asked}
    # Never over an application's files: an employer whose name shortens to "General".
    R.check_batch([a])
    (pages, lines), _letter = F.fit(a)
    drafts = os.path.join(out_dir, "drafts.json")
    with open(drafts, "w", encoding="utf-8", newline="\n") as fh:
        json.dump([a], fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    got = {"draft": a, "drafts": drafts, "pages": pages, "lines": lines, "verify": None,
           "verify_out": "", "pdf": docpaths.resume_pdf(a["abbr"]), "txt": "", "kept": False,
           "grounding": []}
    if check:
        got["verify"], got["verify_out"] = _verify(drafts)
    if keep and (not check or got["verify"] == 0) and 1 <= pages <= F.PAGES:
        pdf, txt = keep_paths(for_contact)
        os.makedirs(os.path.dirname(pdf), exist_ok=True)
        shutil.copyfile(got["pdf"], pdf)
        with open(txt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(plain_text(a))
        got.update(pdf=pdf, txt=txt, kept=True)
        if for_contact:
            keep_for_contact(for_contact, pdf)
        else:
            keep_draft(a)
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="stage_picks.py general",
                                 description="A resume for no posting in particular.")
    ap.add_argument("out_dir", help="a scratch folder for the draft and its checks")
    ap.add_argument("--role", default="", help="the title to aim at, first of the search's "
                                               "titles by default")
    ap.add_argument("--style", default="", help="this resume's own colour (templates/"
                                                "doc_style.py --list)")
    ap.add_argument("--summary-file", default="",
                    help="the summary Claude wrote for it, else the profile's own")
    ap.add_argument("--claims-file", default="",
                    help="with --summary-file: its claim map, a JSON list of {\"sentence\", "
                         "\"cites\": [ids from the drafting pack]}, read by the grounding "
                         "audit as a posting's draft is")
    ap.add_argument("--for-contact", default="", metavar="CONTACT_ID",
                    help="made for this contact, who asked for one: kept in their folder, named "
                         "for them, never in place of your own")
    ap.add_argument("--no-keep", action="store_true",
                    help="render and check it, but keep nothing in documents/cv/")
    a = ap.parse_args(argv)
    summary = ""
    if a.summary_file:
        with open(a.summary_file, encoding="utf-8") as fh:
            summary = fh.read().strip()
    claims = None
    try:
        if a.claims_file:
            with open(a.claims_file, encoding="utf-8") as fh:
                claims = json.load(fh)
        if a.for_contact and not re.match(r"^[\w.-]+$", a.for_contact):
            raise ValueError(f"not a contact id: {a.for_contact!r}")
        got = make(a.out_dir, a.role, a.style, summary, keep=not a.no_keep,
                   for_contact=a.for_contact, claims=claims)
    except Exception as exc:  # the compile, a missing profile file: said in one line
        print(f"general: not made: {exc}", file=sys.stderr)
        return 1
    if got.get("grounding"):
        print("general: not made: the summary claims what the profile does not show, so "
              "nothing was kept. Write it again saying only what the cited text says (python3 "
              "tools/draft_pack.py show lists the ids), with its claim map (--claims-file), or leave "
              "out --summary-file to use the profile's own summary:\n"
              + "\n".join("- " + x for x in got["grounding"]))
        return 1
    d = got["draft"]
    print(f"general: {d['role']} | {got['pages']} page(s), {got['lines']} lines | style "
          f"{d.get('style', 'black')} ({d['style_why']})")
    if got["verify_out"]:
        print(got["verify_out"].splitlines()[-1])
    if got["verify"] not in (0, None):
        print("general: a check failed, so nothing was kept; the checks:\n" + got["verify_out"])
        return 1
    if got["kept"]:
        print(f"kept: {local_path.rel(got['pdf'], person.state())}")
        print(f"text: {local_path.rel(got['txt'], person.state())}")
        print("send: the PDF with SendUserFile, and paste this short copy beside it:")
        print(plain_text(d, short=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
