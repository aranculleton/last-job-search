#!/usr/bin/env python3
"""Every number in a generated document must trace back to the profile.

`check_claims.py` is the companion to this and says honestly what it is: a list
of string patterns harvested from errors the grounding reviewer already caught.
It stops the same mistake twice. It cannot stop a new one, because a metric
nobody has invented yet is not in the list, and a fabricated figure that has
never appeared before passes it silently.

SECURITY.md ranks a fabricated claim reaching an employer as the worst thing
this system can do, worse than any leak. This closes the general case for the
one kind of claim that can be checked mechanically: the numeric kind.

The rule is conservation. A number in the output must exist in the source of
truth, which is the profile: the files its person.json names under
`grounding.sources` (by default its candidate profile, its CLAUDE.md and its
bullets.py). There is no judgement in it, and that is the point: "60M+
records" is checkable, "a strong track record" is not. App documentation is
never a source: a number in an app doc would then count as grounded for
everyone and silently whitelist a fabricated figure.

Magnitude and unit are normalised so "5k", "5,000" and "5000" are one claim,
and "$300M+" and "300 million" are another. A resume that rounds 2.5M to "2.5
million" therefore still matches, and one that quietly promotes 60M to 75M
does not.

WHAT IS DELIBERATELY NOT A FINDING:

  - dates and years, which are structure rather than claims
  - LaTeX residue: lengths in em, pt, ex, in, cm, and \\baselineskip factors
  - small ordinals under `SMALL`, because "3 clients" style numbers are as
    likely to be prose as a claim and the noise would drown the signal
  - a company fact in a cover letter, which is verified separately against an
    independently located source and is not the candidate's own claim

THE LETTER, with `--drafts`. Only the resume was ever checked, and the letter's
opening, bullets and close are free model text that an interviewer reads as
closely. So the drafts mode checks a draft's `summary`, `p1`, `lead`, `p4` and
`cl_bullets` against the profile, and also allows what the letter may honestly
repeat about the employer: the figures in `p2` (the one verified company fact,
which is not itself checked here) and the figures in the posting.

Measured when written: across 53 committed resumes, prose only, exactly one
novel number, and it was LaTeX residue. The documents are already grounded, so
this is a regression guard rather than a repair, the same shape as voice_check.

Usage:
    python3 tools/check_numbers.py cv/<Prefix>_Resume_ACME.tex
    python3 tools/check_numbers.py cv/*.tex
    python3 tools/check_numbers.py --drafts rounds/r1/drafts.json [cv/*.tex]
Exit 0 clean, 1 an ungrounded number, 2 a bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from voice_check import plain  # noqa: E402
import person  # noqa: E402

# Paths in person.json are relative to the profile directory.
SOURCES = tuple(
    os.path.normpath(person.path(p)) for p in
    person.get("grounding.sources", ["01-candidate-profile.md", "CLAUDE.md", "bullets.py"]))

# Below this, a bare number is more likely to be prose than a claim.
SMALL = 10

# LaTeX lengths that survive the strip. A number followed by one of these is
# typography, not a statement about the candidate.
_UNIT_NOISE = r"(?:em|ex|pt|pc|bp|dd|cc|sp|in|cm|mm|baselineskip|textwidth|linewidth)"
_RESIDUE = re.compile(r"\d[\d.]*\s*" + _UNIT_NOISE + r"\b", re.I)

# Every unit word ends on a word boundary. Without it "2024 Weekend" read as
# "2024 week", which is no longer a year, so a resume whose dates run into a
# capitalised word failed verify_batch.sh; "12 monthly reviews", "3 hourly
# checks" and "2023 Daytime cover" broke the same way.
_NUM = re.compile(
    r"(?<![\w.])"
    r"(\d[\d,]*(?:\.\d+)?)"
    # "8+ years" and "9 per cent" carried no unit: the "+" sat between the number
    # and its unit, and "per cent" was not a unit, so a bare number under 10 was
    # thrown away and an invented "8+ years of experience" passed.
    r"\s*\+?\s*"
    r"(%|(?:per\s?cent|percent|k|m|bn|b|million|billion|thousand|hours?|hrs?|days?|weeks?|"
    r"months?|years?|x)\b)?",
    re.I)

_MAGNITUDE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6,
              "b": 1e9, "bn": 1e9, "billion": 1e9}
_UNIT_ALIAS = {"hrs": "hour", "hr": "hour", "percent": "%", "per cent": "%"}
# A four-digit number in this range is a year, and a year is structure.
_YEAR = re.compile(r"^(19|20)\d{2}$")


def claim_key(value: str, unit: str) -> tuple[float, str] | None:
    """(magnitude, unit) for one number, or None when it is not a claim."""
    unit = re.sub(r"\s+", " ", (unit or "").lower()).rstrip("s")
    unit = _UNIT_ALIAS.get(unit, unit)
    raw = value.replace(",", "")
    if _YEAR.match(raw) and not unit:
        return None
    try:
        n = float(raw)
    except ValueError:
        return None
    if unit in _MAGNITUDE:
        return (n * _MAGNITUDE[unit], "")
    if not unit and n < SMALL:
        return None
    return (n, unit)


def claims(text: str) -> set[tuple[float, str]]:
    """Every numeric claim in `text`, normalised."""
    body = _RESIDUE.sub(" ", plain(text or ""))
    out = set()
    for m in _NUM.finditer(body):
        key = claim_key(m.group(1), m.group(2))
        if key is not None:
            out.add(key)
    return out


def grounded(paths=SOURCES) -> set[tuple[float, str]]:
    """Every numeric claim the source of truth supports."""
    out: set[tuple[float, str]] = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                out |= claims(fh.read())
        except OSError:
            continue
    return out


def quote(text: str, value: str) -> str:
    body = plain(text or "")
    m = re.search(r"[^.\n]{0,70}" + re.escape(value) + r"[^.\n]{0,50}", body)
    return (m.group(0).strip() if m else "")[:140]


def check(text: str, source: str = "", allowed=None) -> list[dict]:
    """Numbers in `text` that the source of truth does not support."""
    allowed = allowed if allowed is not None else grounded()
    body = _RESIDUE.sub(" ", plain(text or ""))
    out = []
    for m in _NUM.finditer(body):
        key = claim_key(m.group(1), m.group(2))
        if key is None or key in allowed:
            continue
        out.append({
            "source": source,
            "value": m.group(0).strip(),
            "normalised": f"{key[0]:g}{(' ' + key[1]) if key[1] else ''}",
            "context": quote(text, m.group(1)),
        })
    return out


# The draft fields that are the candidate's own words, rendered. `p2` is the
# researched paragraph and is allowed rather than checked; `concession` and the
# notes are never rendered.
DRAFT_FIELDS = ("summary", "p1", "lead", "p4")


def _bullet_text(b) -> str:
    if isinstance(b, dict):
        return f"{b.get('label', '')}: {b.get('text', '')}"
    return " ".join(str(x) for x in b)


def check_draft(a: dict, allowed=None) -> list[dict]:
    """Numbers in one draft's letter and summary that nothing supports."""
    allowed = allowed if allowed is not None else grounded()
    ok = set(allowed) | claims(a.get("p2") or "") | claims(a.get("posting") or "")
    name = a.get("abbr") or a.get("company") or "draft"
    out = []
    for k in DRAFT_FIELDS:
        out += check(a.get(k) or "", f"{name}.{k}", ok)
    for i, b in enumerate(a.get("cl_bullets") or []):
        out += check(_bullet_text(b), f"{name}.cl_bullets[{i}]", ok)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--drafts", help="a drafts.json: check each letter and summary as well")
    a = ap.parse_args()
    if not (a.paths or a.drafts):
        ap.error("give a document, or --drafts drafts.json")

    allowed = grounded()
    if not allowed:
        print("check_numbers: the source of truth is unreadable; refusing to "
              "pass everything by default", file=sys.stderr)
        return 2

    findings = []
    for path in a.paths:
        try:
            with open(path, encoding="utf-8") as fh:
                findings += check(fh.read(), os.path.basename(path), allowed)
        except OSError as exc:
            print(f"check_numbers: cannot read {path}: {exc}", file=sys.stderr)
            return 2
    drafts = []
    if a.drafts:
        # Through fit_to_page's loader: a kept draft.json names its posting,
        # and the posting's own figures are allowed in the letter.
        import fit_to_page
        try:
            drafts, _ = fit_to_page.load(a.drafts)
        except (OSError, ValueError) as exc:
            print(f"check_numbers: cannot read {a.drafts}: {exc}", file=sys.stderr)
            return 2
        for d in drafts:
            findings += check_draft(d, allowed)

    if not findings:
        print(f"check_numbers: {len(a.paths)} file(s) and {len(drafts)} letter(s) clean, "
              f"{len(allowed)} grounded values")
        return 0
    print(f"check_numbers: {len(findings)} number(s) not in the profile")
    for f in findings:
        print(f"  {f['source']}: {f['value']!r} (as {f['normalised']})")
        if f["context"]:
            print(f"      ...{f['context']}...")
    print("  Either the profile is missing a fact the document states, or the "
          "document states a fact the candidate cannot support. Both need a "
          "person; neither is safe to ship.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
