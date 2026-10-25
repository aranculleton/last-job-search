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
unless Claude wrote one for this resume (`--summary-file`), which the grounding auditor reads
first like any summary. Its colour: the draft's own `--style`, else person.json
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

COMPANY = "General"       # the draft's employer: names its files <Prefix>_<Noun>_General
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
        raise SystemExit("general: the profile has no Canonical Summary Statement "
                         "(01-candidate-profile.md) and no --summary-file was given. Write the "
                         "summary from the profile and run this again with --summary-file.")
    name, why = style_for(style)
    a = {"company": COMPANY, "role": roles[0] if roles else _cap(person.get("documents.noun",
                                                                            "resume")),
         "general": True, "posting": describe(roles, skills), "summary": text,
         "tools": ", ".join(skills), "p1": "", "p2": "", "lead": "", "cl_bullets": [],
         "p4": "", "style_why": why}
    if name != "black" or why != "no style is set":
        a["style"] = name
    return a


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


def keep_paths() -> tuple[str, str]:
    stem = docpaths.resume_stem(KEEP_SUFFIX)
    folder = person.state(*docpaths.GENERAL_DIR)
    return os.path.join(folder, stem + ".pdf"), os.path.join(folder, stem + ".txt")


def _verify(drafts_path: str) -> tuple[int, str]:
    """verify_batch on the one draft: the Python port where it exists, which runs on any
    computer, else the shell script."""
    py = os.path.join(HERE, "verify_batch.py")
    if os.path.exists(py):
        cmd = [sys.executable, py, drafts_path]
    elif shutil.which("bash"):
        cmd = ["bash", os.path.join(HERE, "verify_batch.sh"), drafts_path]
    else:
        return 3, "verify_batch: not run, as this computer has neither its Python port nor bash"
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def make(out_dir: str, role: str = "", style: str = "", summary: str = "",
         keep: bool = True, check: bool = True) -> dict:
    """Draft, render and fit it, check it, and keep it. Returns what happened:
    {"draft", "drafts", "pages", "lines", "verify", "verify_out", "pdf", "txt", "kept"}."""
    import fit_to_page as F
    import render_application as R
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(person.state("cv"), exist_ok=True)
    a = draft(role, style, summary)
    # Never over an application's files: an employer whose name shortens to "General".
    R.check_batch([a])
    (pages, lines), _letter = F.fit(a)
    drafts = os.path.join(out_dir, "drafts.json")
    with open(drafts, "w", encoding="utf-8") as fh:
        json.dump([a], fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    got = {"draft": a, "drafts": drafts, "pages": pages, "lines": lines, "verify": None,
           "verify_out": "", "pdf": docpaths.resume_pdf(a["abbr"]), "txt": "", "kept": False}
    if check:
        got["verify"], got["verify_out"] = _verify(drafts)
    if keep and (not check or got["verify"] == 0) and 1 <= pages <= F.PAGES:
        pdf, txt = keep_paths()
        os.makedirs(os.path.dirname(pdf), exist_ok=True)
        shutil.copyfile(got["pdf"], pdf)
        with open(txt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(plain_text(a))
        got.update(pdf=pdf, txt=txt, kept=True)
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
    ap.add_argument("--no-keep", action="store_true",
                    help="render and check it, but keep nothing in documents/cv/")
    a = ap.parse_args(argv)
    summary = ""
    if a.summary_file:
        with open(a.summary_file, encoding="utf-8") as fh:
            summary = fh.read().strip()
    try:
        got = make(a.out_dir, a.role, a.style, summary, keep=not a.no_keep)
    except Exception as exc:  # the compile, a missing profile file: said in one line
        print(f"general: not made: {exc}", file=sys.stderr)
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
