#!/usr/bin/env python3
"""The eight to twelve form fields that actually gate a submission.

The system produces a resume, a cover letter and an outreach note, and then
leaves the candidate at a portal form asking whether they require
sponsorship, what their notice period is and what salary they expect. Those
answers decide whether the application is read at all, and until now nothing
wrote them down.

So they were retyped from memory, per application, which is how they drift. The
one most likely to be got wrong is the one that matters most: the sponsorship
question. Where the honest answer is a plain no, a candidate who hedges it
with an explanation nobody asked for has just told an ATS to filter them out.

The questions, answers and notes are the profile's (screening.py: they depend
on the person's country and situation). The facts in them are parsed here from
the profile's own documents: the notice period from the candidate profile, the
salary band from the table in the evaluation rubric, the sponsorship position
from the summary and the candidate profile. So a corrected fact propagates
instead of being corrected in one place and stale in the other twelve.

WHERE IT REFUSES. If a fact cannot be parsed out of the profile, this raises
rather than guessing or falling back to a default. An answer sheet that
silently carries a wrong sponsorship answer or a stale notice period is worse
than no answer sheet, because it will be trusted and pasted.

Usage:
    python3 tools/screening_answers.py --slug <application folder>
    python3 tools/screening_answers.py --print
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
import local_path  # noqa: E402


def _file(key: str, default: str) -> str:
    return person.file(key, default)


PROFILE = _file("candidate_profile", "01-candidate-profile.md")
EVALUATION = _file("evaluation", "04-job-evaluation.md")
CLAUDE_MD = _file("summary", "CLAUDE.md")
try:
    _SHEET = person.module("screening")
except person.NoProfile:
    # A profile with no screening.py still has its facts (the band, the notice, the
    # sponsorship position), which the interview pack and the consistency check read; only
    # the answer sheet itself needs the file, and says so when asked for.
    _SHEET = None


class MissingFact(RuntimeError):
    """A fact the answer sheet needs is not in the profile any more."""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise MissingFact(f"cannot read {os.path.basename(path)}: {exc}") from exc


def notice_period() -> str:
    """The notice period, from the profile's own line.

    Parsed rather than hardcoded because a copy of a fact goes stale: a
    correction made in the profile must reach the answer sheet, and a stale
    earlier reading must not be reused. The line is a table row
    `**Notice period** | **one month**` or a sentence `**Notice: one month.**`,
    as the profile template writes it.
    """
    text = _read(PROFILE)
    m = re.search(r"\*\*Notice period\*\*\s*\|\s*\*\*([^*|]+)\*\*", text)
    if not m:
        m = re.search(r"\*\*Notice:\s*([^.*]+)\.?\*\*", text)
    if not m:
        raise MissingFact(f"no notice period in {os.path.basename(PROFILE)}")
    return m.group(1).strip().rstrip(".")


def salary_band() -> tuple[int, int, int]:
    """(walk-away floor, target low, target high) in the profile's currency,
    from the rubric's salary table."""
    text = _read(EVALUATION)
    floor = re.search(r"\*\*Walk-away floor\*\*\s*\|\s*\*\*([\d,]+)\*\*", text)
    target = re.search(r"\*\*Target\*\*\s*\|\s*\*\*([\d,]+)\s*-\s*([\d,]+)\*\*", text)
    if not (floor and target):
        raise MissingFact(f"no salary band table in {os.path.basename(EVALUATION)}")
    n = (lambda s: int(s.replace(",", "")))
    return n(floor.group(1)), n(target.group(1)), n(target.group(2))


def requires_sponsorship() -> bool:
    """What the profile says, in so many words, and never a default.

    Checked rather than assumed. If the sponsorship position ever changes, this
    answer must change the same day the profile changes, not whenever somebody
    remembers this file exists. The profile says "no sponsorship required" or
    "sponsorship required"; anything else raises.
    """
    text = _read(CLAUDE_MD) + _read(PROFILE)
    if re.search(r"no sponsorship required", text, re.I):
        return False
    if re.search(r"\bsponsorship (?:is )?required\b", text, re.I):
        return True
    raise MissingFact(
        "The profile no longer states whether sponsorship is required. This "
        "answer is the one most likely to be filtered on, so it is not "
        "guessed.")


def answers() -> list[tuple[str, str, str]]:
    """(question as portals ask it, the answer, the note for the candidate)."""
    if _SHEET is None:
        raise MissingFact("the profile has no screening.py, the form's questions: /setup "
                          "writes it")
    floor, low, high = salary_band()
    facts = dict(floor=floor, low=low, high=high, notice=notice_period(),
                 sponsor_answer="Yes" if requires_sponsorship() else "No")
    return [(q, a.format(**facts), n.format(**facts)) for q, a, n in _SHEET.QUESTIONS]


NEEDS_A_PERSON = tuple(getattr(_SHEET, "NEEDS_A_PERSON", ()))


def render(company: str = "", role: str = "") -> str:
    head = f"# Screening answers: {role or '<role>'} at {company or '<company>'}\n"
    lines = [head,
             "Generated from `01-candidate-profile.md`, `CLAUDE.md` and the salary",
             "table in `04-job-evaluation.md`. Correct a fact there, not here.\n"]
    for question, answer, note in answers():
        flag = "  **(decide per application)**" if question in NEEDS_A_PERSON else ""
        lines.append(f"### {question}{flag}\n")
        lines.append(f"**{answer}**\n")
        lines.append(f"{note}\n")
    lines.append("---\n")
    lines.append("Answers given on a portal are recorded in `form_fields.txt` in this")
    lines.append("folder, so a follow-up or a second application does not contradict")
    lines.append("the first.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", help="application folder under documents/applications/")
    ap.add_argument("--company", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--print", dest="show", action="store_true")
    a = ap.parse_args()

    try:
        body = render(a.company, a.role)
    except MissingFact as exc:
        print(f"screening_answers: {exc}", file=sys.stderr)
        return 2

    if a.show or not a.slug:
        print(body)
        return 0

    folder = person.state("documents", "applications", a.slug)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "screening_answers.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"screening_answers: wrote {local_path.rel(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
