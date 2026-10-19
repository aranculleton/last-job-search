#!/usr/bin/env python3
"""The facts a screen checks first, said the same way everywhere in the profile.

The pay band, the walk-away floor, the notice period and the sponsorship position each
have one source, and tools/screening_answers.py reads them from it: the salary table in
04-job-evaluation.md, the notice line in 01-candidate-profile.md, the sponsorship sentence
in CLAUDE.md and 01-candidate-profile.md. A person had one target band in the candidate
profile's logistics and another in the rubric, and an interview pack could have quoted
either to a recruiter who already had the other from the form.

This reads every other place in profile/ that restates one of them, and names each that
says something different. It never decides which is right: the source wins by default,
and the person says when the source is the one that is stale.

    python3 tools/profile_consistency.py          # exit 1 when anything disagrees
    python3 tools/profile_consistency.py --json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402

# A money amount: 110,000 or 110000 or 110k, with or without a currency in front.
_CUR = r"(?:[A-Z]{2,3}\s?\$?|[$£€]|[A-Z]{1,2}\$)?\s?"
_AMOUNT = r"(\d{2,3}(?:,\d{3})|\d{5,6}|\d{2,3}\s?[kK])\b"
_RANGE = re.compile(_CUR + _AMOUNT + r"\s*(?:to|-|–|and)\s*" + _CUR + _AMOUNT
                    # "110 to 130k": the k on the second amount is the first's too
                    + r"|" + _CUR + r"(\d{2,3})\s*(?:to|-|–)\s*" + _CUR + r"(\d{2,3})\s?[kK]\b")
_SINGLE = re.compile(_CUR + _AMOUNT)
# A line about what the person wants, as against what they earn now or what a market pays.
_TARGET = re.compile(r"\b(?:target\w*|expect\w*|asking|band|looking for|salary|compensation|"
                     r"aim\w*)\b", re.I)
_NOT_TARGET = re.compile(r"\b(?:current(?:ly)?|base of|earn\w*|market|benchmark|levels\.fyi|"
                         r"glassdoor|posted|posting|range for|median|percentile|offer(?:ed)?|"
                         r"previous|was paid|norms?|guide|survey|typical|average|reported|"
                         r"their band|our band|band is)\b", re.I)
_FLOOR = re.compile(r"\b(?:floor|walk[- ]away|minimum|bottom line)\b", re.I)
_NOTICE = re.compile(r"\bnotice(?: period)?\b(?:\s*(?:is|of|:|\|))?", re.I)
_DURATION = re.compile(r"\b(\d+|one|two|three|four|six|eight|twelve)\s+(week|month)s?\b", re.I)
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "eight": 8, "twelve": 12}
_NEEDS = re.compile(r"\b(?:need|needs|require|requires|requiring|will need)\s+(?:visa\s+|work\s+)?"
                    r"sponsorship\b|\bsponsorship (?:is |will be )?(?:required|needed)\b", re.I)
_NO_SPONSOR = re.compile(r"\bno (?:visa )?sponsorship\b|\b(?:not|never|don'?t|doesn'?t|won'?t)\s+"
                         r"(?:\w+\s+){0,2}(?:need|require)\w*\s+(?:visa\s+)?sponsorship\b"
                         r"|\bneed no sponsorship\b|\bwithout sponsorship\b", re.I)


def _range_of(m) -> tuple:
    """(low, high) from a _RANGE match, whichever of its two shapes matched."""
    if m.group(1):
        return _amount(m.group(1)), _amount(m.group(2))
    return int(m.group(3)) * 1000, int(m.group(4)) * 1000


def _amount(text: str) -> int:
    t = text.replace(",", "").replace(" ", "")
    return int(t[:-1]) * 1000 if t[-1:] in "kK" else int(t)


def _months(text: str) -> float | None:
    m = _DURATION.search(text)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1).lower()]
    return n if m.group(2).lower() == "month" else round(n / 4.345, 2)


def _files() -> list[str]:
    """Every markdown file in the profile, and the data file that carries the person's
    networking wording."""
    found = sorted(glob.glob(person.path("*.md")))
    nets = person.path("networking.py")
    return found + ([nets] if os.path.exists(nets) else [])


def _rel(path: str) -> str:
    return "profile/" + os.path.relpath(path, person.path()).replace(os.sep, "/")


_QUOTED = re.compile(r"\"[^\"]{0,300}\"|\u201c[^\u201d]{0,300}\u201d")


def _sentence_spans(text: str) -> list[tuple[int, str]]:
    """(offset, sentence) for every sentence, a sentence never running past a blank line, a
    list item or a table row: the unit a fact is stated in."""
    out = []
    for block in re.finditer(r"[^\n]+(?:\n(?![ \t]*(?:[-*+|#>]|\d+[.)]|\n))[^\n]+)*", text):
        for m in re.finditer(r"[^.!?;]+(?:[.!?;]+|$)", block.group(0)):
            if m.group(0).strip():
                out.append((block.start() + m.start(), m.group(0)))
    return out


# The person's rule for a temporary status: "name the permit only when asked directly". A
# stock answer that says to volunteer the expiry contradicts it, and the app's own template
# once seeded exactly that sentence.
_ASKED_ONLY = re.compile(r"\b(?:permit|visa|expiry|status)\b[^.\n]{0,160}\b(?:only (?:when|if) "
                         r"(?:asked|prompted)|when asked directly|unless asked)\b", re.I)
_VOLUNTEER = re.compile(r"\b(?:state|mention|give|volunteer|say)\s+(?:the\s+)?(?:expiry|"
                        r"date|end date)(?:\s+date)?\s+plainly\b|\bvolunteer (?:the )?(?:expiry|"
                        r"permit|visa)\b", re.I)


def findings(unread: list | None = None) -> list[dict]:
    """[{file, line, fact, said, source}] for every restatement that disagrees with its
    source. A fact whose source cannot be read is not checked, and is named in `unread`
    (when given) rather than passed silently."""
    import screening_answers as sheet     # reads the profile as it loads
    out: list[dict] = []
    try:
        floor, low, high = sheet.salary_band()
    except sheet.MissingFact as exc:
        if unread is not None:
            unread.append("pay band: %s" % exc)
        floor = low = high = None
    try:
        notice = sheet.notice_period()
    except sheet.MissingFact as exc:
        if unread is not None:
            unread.append("notice period: %s" % exc)
        notice = ""
    try:
        sponsor = sheet.requires_sponsorship()
    except sheet.MissingFact as exc:
        if unread is not None:
            unread.append("sponsorship: %s" % exc)
        sponsor = None
    notice_m = _months(notice) if notice else None
    # The file that says it, of the two requires_sponsorship() reads.
    sponsor_src = next((_rel(f) for f in (sheet.CLAUDE_MD, sheet.PROFILE)
                        if os.path.exists(f) and re.search(
                            r"no sponsorship required" if sponsor is False
                            else r"\bsponsorship (?:is )?required\b",
                            open(f, encoding="utf-8").read(), re.I)), _rel(sheet.CLAUDE_MD))
    texts = {}
    for path in _files():
        try:
            with open(path, encoding="utf-8") as fh:
                texts[path] = fh.read()
        except OSError:
            continue
    rule = next(((p_, m.group(0)) for p_, t in texts.items() for m in [_ASKED_ONLY.search(t)]
                 if m), None)
    if rule:
        for p_, t in texts.items():
            for m in _VOLUNTEER.finditer(t):
                before = t[max(0, t.rfind("\n", 0, m.start()) + 1):m.start()]
                if re.search(r"\b(?:never|don'?t|do not|not|avoid)\b[^.]*$", before, re.I):
                    continue        # "Never volunteer the expiry" is the rule itself
                out.append({"file": _rel(p_), "line": t.count("\n", 0, m.start()) + 1,
                            "fact": "permit disclosure", "said": m.group(0),
                            "source": "\"%s\" in %s" % (" ".join(rule[1].split())[:90],
                                                         _rel(rule[0]))})
    evaluation = os.path.normpath(sheet.EVALUATION)
    for path, text in texts.items():
        # Quoted text is a question a form asks or words someone else said ("will you
        # require sponsorship?"), never the person's position: blanked, offsets kept.
        masked = _QUOTED.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
        source_rows = os.path.normpath(path) == evaluation
        for start, sent in _sentence_spans(masked):
            i = text.count("\n", 0, start) + 1
            line = text.splitlines()[i - 1].strip() if text.splitlines() else ""
            if source_rows and re.match(r"^\|\s*\*\*(?:Target|Walk-away floor)\*\*", line):
                continue
            if sent.rstrip(" *_\"'\u201d").endswith("?"):
                continue        # a question as a form asks it, not a statement of fact
            if low is not None and _TARGET.search(sent) and not _NOT_TARGET.search(sent):
                for m in _RANGE.finditer(sent):
                    a, b = _range_of(m)
                    if a >= 1000 and (a, b) != (low, high):
                        out.append({"file": _rel(path), "line": i, "fact": "pay band",
                                    "said": m.group(0).strip(),
                                    "source": "%s to %s in %s" % (
                                        "{:,}".format(low), "{:,}".format(high),
                                        _rel(sheet.EVALUATION))})
            if floor is not None and _FLOOR.search(sent) and not _RANGE.search(sent) \
                    and not _NOT_TARGET.search(sent):
                for m in _SINGLE.finditer(sent):
                    v = _amount(m.group(1))
                    if v >= 1000 and v != floor:
                        out.append({"file": _rel(path), "line": i, "fact": "walk-away floor",
                                    "said": m.group(0).strip(),
                                    "source": "%s in %s" % ("{:,}".format(floor),
                                                            _rel(sheet.EVALUATION))})
            if notice_m is not None and _NOTICE.search(sent):
                after = sent[_NOTICE.search(sent).start():]
                said = _months(after)
                if said is not None and abs(said - notice_m) > 0.01:
                    out.append({"file": _rel(path), "line": i, "fact": "notice period",
                                "said": _DURATION.search(after).group(0),
                                "source": "%s in %s" % (notice, _rel(sheet.PROFILE))})
            if sponsor is not None:
                own = masked[start:start + len(sent)]
                if own.rstrip(" *_\"'").endswith("?"):
                    continue
                need = _NEEDS.search(_NO_SPONSOR.sub("", own))
                if sponsor is False and need:
                    out.append({"file": _rel(path), "line": i, "fact": "sponsorship",
                                "said": need.group(0),
                                "source": "no sponsorship required, in %s" % sponsor_src})
                elif sponsor is True and _NO_SPONSOR.search(own):
                    out.append({"file": _rel(path), "line": i, "fact": "sponsorship",
                                "said": _NO_SPONSOR.search(own).group(0),
                                "source": "sponsorship required, in %s" % sponsor_src})
    return out


def report(found: list[dict], unread: list | None = None) -> str:
    skipped = ["Not checked, %s" % u for u in unread or ()]
    if not found:
        return "\n".join(["The pay band, floor, notice period, sponsorship and permit disclosure "
                          "are said the same way everywhere%s." % (
                              " that could be read" if skipped else "")] + skipped)
    lines = ["%d place(s) in the profile say a fact differently from its source:" % len(found)]
    for f in found:
        where = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
        lines.append("- %s, %s: %s" % (where, f["fact"], "says \"%s\"; the source says %s"
                                       % (f["said"], f["source"]) if f["said"] else f["source"]))
    lines.append("Change each to the source, or, if the source is the stale one, correct the "
                 "source: the form answers, the interview packs and the letters all read it.")
    return "\n".join(lines + skipped)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    unread: list = []
    try:
        found = findings(unread)
    except person.NoProfile:
        print("profile_consistency: no profile/ yet: /setup builds one.")
        return 0
    print(json.dumps(found, indent=1) if a.json else report(found, unread))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
