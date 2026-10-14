#!/usr/bin/env python3
"""The candidate side of a prep document, read out of the profile rather than typed.

`prep.py` takes a `profile_facts` dict and, quite deliberately, invents nothing
when it is absent: an empty dict produces "No profile facts were passed in, so
no answers are drafted". Nothing in the repo ever built that dict, so every prep
document shipped with two of its nine sections empty, including the two a call
actually turns on. "They will likely ask" and "Fit, honestly" were blank on
every document alike.

Everything here is read from files that already exist:

  `01-candidate-profile.md`   the summary, the employers and their evidence,
                              the narrative, the work authorization and the
                              deal-breakers
  `tools/bridges.py`          the gaps, and the honest sentence to answer each
                              one with

Nothing is authored here except the section names it looks for, which is the
point: a fact edited in the profile changes the prep document on the next run,
and there is no second copy to drift. `prep.PROFILE_SOURCE` already attributes
these facts to the profile by contract, and now that attribution is true.

Gaps are per role rather than fixed. `bridges.assess` reads the role title and
whatever posting text is passed, so a pricing role and a streaming role are
asked about different things, and a gap with no honest framing is left to
`fit_assessment` to say so plainly rather than answered with something invented.

Usage:
    python3 tools/network/profile_facts.py [--role "Operations Analyst"]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridges  # noqa: E402
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))
PROFILE_MD = person.file("candidate_profile", "01-candidate-profile.md")
_NET = person.module("networking") if person.exists("networking.py") else None

# How many employers reach the document. The two most recent answer "what have
# you built that is closest to this", and a third is already more history than a
# thirty-minute call has room for.
MAX_EMPLOYERS = 3
MAX_EVIDENCE = 3
MAX_STRENGTHS = 3

_HEADING = re.compile(r"^(#{2,3})\s+(.*?)\s*$")
_BULLET = re.compile(r"^[-*]\s+(.+?)\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
# "### Senior Operations Analyst - Brindle & Hart Logistics (Mar 2023 - Present)"
_ROLE_HEADING = re.compile(r"^(?P<title>.+?)\s+-\s+(?P<company>.+?)\s*\((?P<dates>[^)]*)\)\s*$")
_WS = re.compile(r"\s+")
# Markdown that is markup rather than words. A prep document is read off a
# phone, where `**bold**` renders as asterisks.
_EMPHASIS = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`")


def _plain(text) -> str:
    return _WS.sub(" ", _EMPHASIS.sub(lambda m: next(g for g in m.groups() if g is not None),
                                      str(text or ""))).strip()


def _read(path=PROFILE_MD) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def sections(lines) -> dict:
    """`{heading: [lines]}` for every `##` and `###` in the profile.

    Flat rather than nested, because every section this reads is addressed by
    its own name and a tree would only be walked back down again.
    """
    out, current = {}, None
    for line in lines:
        m = _HEADING.match(line)
        if m:
            current = m.group(2).strip()
            out.setdefault(current, [])
            continue
        if current is not None:
            out[current].append(line)
    return out


def _blockquote(body) -> str:
    """The first blockquote in a section, as one paragraph."""
    out = []
    for line in body:
        m = _QUOTE.match(line.strip())
        if m:
            out.append(m.group(1).strip())
        elif out:
            break
    return _plain(" ".join(x for x in out if x))


def _blockquote_paragraphs(body) -> list:
    """A blockquote as its paragraphs, joined back across the source wrapping.

    The profile is hard-wrapped at about ninety columns, so reading one `>` line
    as one paragraph cut the narrative mid-sentence. Paragraphs are separated by
    a bare `>`.
    """
    out, current = [], []
    for line in body:
        m = _QUOTE.match(line.strip())
        if not m:
            if current:
                break
            continue
        text = m.group(1).strip()
        if text:
            current.append(text)
        elif current:
            out.append(_plain(" ".join(current)))
            current = []
    if current:
        out.append(_plain(" ".join(current)))
    return out


def _bullets(body, stop_at_bold_lead=True) -> list:
    """The bullets directly under a heading, stopping at the first sub-block.

    The profile puts "Additional detail available for tailoring" bullets under
    the same heading as the default ones. Those exist to be swapped in against a
    posting, which is a resume decision, not a briefing one, so the run stops at
    the bold lead-in that introduces them.
    """
    out = []
    for line in body:
        stripped = line.strip()
        m = _BULLET.match(stripped)
        if m:
            out.append(_plain(m.group(1)))
            continue
        if not stripped or stripped.startswith("<!--"):
            continue
        if out and stop_at_bold_lead:
            break
    return out


def employers(secs, lines=None) -> list:
    """Each role as `{company, title, dates, evidence}`, most recent first.

    Reserve Experience is deliberately not read. It is opt-in per role by the
    profile's own instruction, and a call is not the place to volunteer it.

    `lines` is the same file `secs` was built from. Passing it matters: without
    it this re-read the live profile to work out which headings sit under
    Professional Experience, so a call against any other file silently
    classified its roles against the wrong one.
    """
    out = []
    order = [h for h in secs if _ROLE_HEADING.match(h)]
    experience = _experience_headings(secs, lines)
    for heading in order:
        if heading not in experience:
            continue
        m = _ROLE_HEADING.match(heading)
        evidence = _bullets(secs[heading])[:MAX_EVIDENCE]
        if not evidence:
            continue
        out.append({"company": _plain(m.group("company")),
                    "title": _plain(m.group("title")),
                    "dates": _plain(m.group("dates")),
                    "evidence": evidence})
    return out[:MAX_EMPLOYERS]


def _experience_headings(secs, lines=None) -> set:
    """Role headings that sit under Professional Experience, not under Reserve.

    `sections()` is flat, so the two blocks are told apart by where their
    headings fall in the file rather than by nesting.
    """
    lines = _read() if lines is None else lines
    out, inside = set(), False
    for line in lines:
        m = _HEADING.match(line)
        if not m:
            continue
        name = m.group(2).strip()
        if m.group(1) == "##":
            inside = name.lower().startswith("professional experience")
            continue
        if inside and name in secs:
            out.add(name)
    return out


def _first_sentence(text) -> str:
    body = _plain(text)
    m = re.search(r"(?<=[.!?])\s", body)
    return body[:m.start() + 1] if m else body


def narrative(secs) -> str:
    """The unusual-route answer, in the profile's framing, condensed to what a call needs.

    The profile says the person's own words are for picking what to say and how
    to frame it, never to be pasted, so the first and last movements of it are
    taken and the rest left on the page: the route and what it taught, without
    the detail the profile says not to lead on.
    """
    body = _blockquote_paragraphs(
        secs.get("Personal Narrative (candidate's own words)", []))
    if not body:
        return ""
    opener = _first_sentence(body[0])
    learned = next((p for p in body if "learning quickly" in p or "under pressure" in p), "")
    return " ".join(x.strip() for x in (opener, _first_sentence(learned)) if x.strip())


def summary(secs) -> str:
    return _blockquote(secs.get("Canonical Summary Statement", []))


def work_authorization(secs) -> str:
    """One sentence, from whichever section states the work authorization.

    Read rather than hard-coded, because work authorization is the fact most
    likely to change and the one it is least affordable to get wrong on a call.
    """
    for name in ("Logistics and availability", "Identity"):
        for line in secs.get(name, []):
            flat = _plain(line)
            if not _WORK_AUTH_LINE.search(flat):
                continue
            # The profile states it in a two-column table, so the answer is the
            # last cell. Read as a line it came out as "| Work eligibility |
            # <the authorization>."
            if flat.startswith("|"):
                cells = [c.strip() for c in flat.strip("|").split("|")]
                flat = cells[-1] if cells else flat
            body = flat.lstrip("-* ").split(":", 1)[-1].strip()
            # Two sentences here, not one: the authorization and what it does
            # not cover are both answers to "do you need sponsorship".
            return " ".join(_sentences_upto(body, 2))
    return ""


def _sentences_upto(text, count) -> list:
    body = _plain(text)
    parts = re.split(r"(?<=[.!?])\s+", body)
    return [p for p in parts if p][:count]


# Where the deal-breakers are actually written: the profile's summary document
# (person.json files.summary), read from the file that holds them rather than
# restated here, which would be a second copy to drift. Which of them are
# categorical, and what in a role raises each, is the profile's
# (networking.py PREP_CATEGORICAL and PREP_TRIGGERS); the defaults are the
# eligibility bars every search shares.
CLAUDE_MD = person.file("summary", "CLAUDE.md")
_CATEGORICAL = getattr(_NET, "PREP_CATEGORICAL", None) or re.compile(
    r"\b(citizenship|permanent residen|clearance)\b", re.I)


# What the role has to actually say for the matching deal-breaker to be worth
# printing: (what in the role raises it, which deal-breaker line it raises).
# Without this every prep document opened its Fit section with a BLOCKER line
# for every categorical deal-breaker, on calls where none of them had come up,
# which is how a section stops being read. networking.py's PREP_TRIGGERS.
_TRIGGERS = tuple(getattr(_NET, "PREP_TRIGGERS", None) or (
    (re.compile(r"\bcitizen\w*|\bpermanent residen\w*|\bPR status\b|\bsecurity clearance\b"
                r"|\bclearance\b", re.I),
     re.compile(r"^Roles requiring .*(?:citizenship|permanent residen|clearance)", re.I)),
))

# The line in the candidate profile that states the work authorization.
_WORK_AUTH_LINE = getattr(_NET, "WORK_AUTH_LINE", None) or re.compile(
    r"\b(work permit|visa|authori[sz]ed to work|work authori[sz]ation|right to work)\b", re.I)


def blockers(text="", path=CLAUDE_MD) -> list:
    """The categorical ones the role actually raises. Never softened into a gap.

    A blocker is a hard no that no framing fixes, so it prints in its own voice
    and prints first. That is only worth doing when the role raises it: a
    relocation deal-breaker is answered by saying where they live, and a
    citizenship bar on a job that never mentions citizenship is not a fact about
    this call.
    """
    items = [_first_sentence(x).rstrip(". ")
             for x in _bullets(sections(_read(path)).get("Deal-breakers", []),
                               stop_at_bold_lead=False)
             if _CATEGORICAL.search(x)]
    asked = str(text or "")
    out = []
    for trigger, matches in _TRIGGERS:
        if not trigger.search(asked):
            continue
        out += [x for x in items if matches.search(x) and x not in out]
    return out


def strengths(secs, lines=None) -> list:
    """What to lead with, taken from the most recent role's own evidence.

    Not a separate list. A strength that is not already a line on the resume is
    one they would be asked to evidence and could not, and the point of the
    section is the opposite.
    """
    roles = employers(secs, lines)
    return [e for role in roles[:2] for e in role["evidence"]][:MAX_STRENGTHS]


def gaps_for(text) -> list:
    """What this role will ask about that the person does not straightforwardly hold.

    `bridges` is the source: it already holds the honest sentence for each one,
    written to be usable unchanged. A bridge with no line is passed through with
    no framing so `fit_assessment` says one still has to be written, which is
    the truthful output and the one that gets it written.
    """
    out = []
    for a in bridges.assess(text or ""):
        if a.verdict == bridges.HELD:
            continue
        out.append({"gap": a.asked, "framing": a.line,
                    "source": "tools/bridges.py"})
    return out


def build(role="", posting="", path=PROFILE_MD) -> dict:
    """The `profile_facts` dict `prep.prep_markdown` takes.

    `role` and `posting` only steer the gaps. Everything else is the same
    whoever the call is with, which is why it is read once from the profile
    rather than assembled per contact.
    """
    lines = _read(path)
    secs = sections(lines)
    facts = {
        "summary": summary(secs),
        "narrative": narrative(secs),
        "employers": employers(secs, lines),
        "strengths": strengths(secs, lines),
        "work_authorization": work_authorization(secs),
        "blockers": blockers(" ".join(x for x in (role, posting) if x)),
        "gaps": gaps_for(" ".join(x for x in (role, posting) if x)),
    }
    return {k: v for k, v in facts.items() if v}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--role", default="", help="role title, which steers the gaps")
    ap.add_argument("--posting", default="", help="posting text, same")
    ap.add_argument("--profile", default=PROFILE_MD)
    a = ap.parse_args()
    print(json.dumps(build(a.role, a.posting, a.profile), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
