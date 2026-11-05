#!/usr/bin/env python3
"""The answers to an application form's own questions, kept with the application.

A form asks more than the resume and the letter answer: "Why us?", "Why this role?", "An
example of when you used X". The person pastes those questions on the page (a Drafts or
Applied card's "Questions on the form"), and the chat that takes the work (`form_answers`,
the app skill's run table) drafts each answer from the profile and the posting and writes it
here, into the application's `screening_answers.md`: the file its card's "To copy" and the
interview pack already read, so one record holds every answer that went on the form. The
resume and the letter are never touched here; a change asked for them goes to the tweak path.

An answer is one paragraph (the card shows it with its Copy button), its note the line under
it. An example the person asked for that the profile does not hold is a draft: `--draft`
marks it for them to confirm or change before it goes, and nothing about it reaches the
profile until they do (CLAUDE.md, "A draft they ask for is not a claim").

Usage:
    python3 tools/form_answers.py add --slug <folder> --question "<q>" --answer "<a>" [--note "<why>"] [--draft]
    python3 tools/form_answers.py folder --company "<employer>" --role "<role>"
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402

FILE = "screening_answers.md"
DRAFT_NOTE = "A draft for you to confirm or change before you send it."
_FOOTER = re.compile(r"^---\s*$", re.M)


def _one_line(text: str) -> str:
    """One paragraph, as the card's parser reads an answer (`**...**` on one line)."""
    return " ".join(str(text or "").replace("**", "").split())


def block(question: str, answer: str, note: str = "", draft: bool = False) -> str:
    q, a = _one_line(question), _one_line(answer)
    if not q or not a:
        raise ValueError("a question and its answer, both")
    why = " ".join(x for x in (DRAFT_NOTE if draft else "", _one_line(note)) if x)
    return f"### {q}\n\n**{a}**\n\n" + (f"{why}\n\n" if why else "")


def add(folder: str, question: str, answer: str, note: str = "", draft: bool = False,
        company: str = "", role: str = "") -> str:
    """Write one answer into the folder's screening_answers.md: the same question answered
    again replaces its earlier answer, a new one goes before the file's closing note. Returns
    the file's path."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = f"# Screening answers: {role or '<role>'} at {company or '<company>'}\n\n"
    new = block(question, answer, note, draft)
    q = _one_line(question)
    same = re.compile(r"^###\s+" + re.escape(q) + r"[^\n]*\n(?:(?!^###\s|^---\s*$).*\n?)*", re.M)
    if same.search(text):
        text = same.sub(lambda _m: new, text, count=1)
    else:
        foot = _FOOTER.search(text)
        text = (text[:foot.start()] + new + text[foot.start():]) if foot else text.rstrip("\n") + "\n\n" + new
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return path


def folder_for(company: str, role: str = "", slug: str = "") -> str:
    """The application's own folder: by its slug where the page gave one, else by employer
    and role as the drafting named it (outreach.app_folder)."""
    if slug:
        return person.state("documents", "applications", os.path.basename(slug))
    import outreach
    return outreach.app_folder(company, role)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="write one answer into the application's screening_answers.md")
    a.add_argument("--slug", default="")
    a.add_argument("--company", default="")
    a.add_argument("--role", default="")
    a.add_argument("--question", required=True)
    a.add_argument("--answer", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--draft", action="store_true", help="an example for the person to confirm")
    f = sub.add_parser("folder", help="print the application's folder")
    f.add_argument("--slug", default="")
    f.add_argument("--company", default="")
    f.add_argument("--role", default="")
    o = ap.parse_args(argv)
    folder = folder_for(o.company, o.role, o.slug)
    if o.cmd == "folder":
        print(folder)
        return 0
    if not o.slug and not (o.company and os.path.isdir(folder)):
        print("form_answers: no application folder for that employer and role; give --slug",
              file=sys.stderr)
        return 2
    try:
        path = add(folder, o.question, o.answer, o.note, o.draft, o.company, o.role)
    except ValueError as exc:
        print(f"form_answers: {exc}", file=sys.stderr)
        return 2
    print(f"form_answers: wrote the answer to {os.path.basename(path)} in {os.path.basename(folder)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
