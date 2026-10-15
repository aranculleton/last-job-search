#!/usr/bin/env python3
"""Deterministic grounding pre-check for generated resumes and cover letters.

The expensive grounding reviewer keeps catching the *same* errors. Across a
handful of applications it finds defects, and nearly every one belongs to a
class that has already appeared in an earlier application:

  - a metric attached to the wrong piece of work (a forecast's percentage
    error applied to a segmentation model, which has none)
  - a sector qualifier dropped from a dataset's description, which on an
    application to a different sector nudges the reader toward believing the
    work was done in that sector
  - a hedge removed ("contributed to" -> "grew"), claiming sole causation for
    a growth curve
  - a scope qualifier removed ("during peak-season weeks")
  - a tool attributed to the wrong employer
  - a certification presented as complete when it is scheduled

Paying a reviewer agent to rediscover a fixed list of string patterns is waste.
This script checks them at zero token cost, so the reviewer's attention goes to
the judgment calls only it can make.

**This does not replace the grounding reviewer.** It catches known repeats. New
error classes still need a reader. When the reviewer finds one this script
missed, add it to the profile's claims.py (a fact about the candidate) or to
app_rules() below (a rule about writing).

Usage:
    python3 tools/check_claims.py cv/<Prefix>_Resume_ACME.tex ...
    python3 tools/check_claims.py cv/*.tex cover_letters/*.tex

Exit status 1 if any ERROR-level finding fires.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

# English words that end in -ise in EVERY variety, so they are never a spelling
# error. Without this list the -ise check fires on "enterprise-scale" and the
# whole report gets discounted.
LEGITIMATE_ISE = [
    "enterprise", "enterprises", "expertise", "fundraise", "fundraising", "precise", "concise", "comprise",
    "comprised", "comprises", "supervise", "supervised", "supervising", "advise",
    "advised", "advising", "otherwise", "likewise", "wise", "rise", "rises",
    "arise", "arises", "arising", "promise", "promised", "promises", "franchise",
    "merchandise", "surprise", "surprised", "exercise", "exercised", "exercises",
    "raise", "raised", "raises", "praise", "noise", "cruise", "devise", "devised",
    "revise", "revised", "revising", "disguise", "paradise", "compromise",
    "premise", "premises", "demise", "excise", "improvise", "televise", "chastise",
    "despise",
    # Words that merely CONTAIN "ising"/"ise" and are spelled the same in every
    # dialect. Each of these produced a false positive on a real document.
    "advertising", "advertise", "advertised", "merchandising", "franchising",
    "supervision", "revision", "provision", "division", "precision", "decision",
    # More words that end in -ise in every variety.
    "wise", "clockwise", "streetwise", "noise", "poise", "guise", "expertise",
    # -ising forms of the verbs above, and -ising words with no -izing form.
    # "comprising", "promising", "surprising" and "exercising" each fired on a
    # real document.
    "comprising", "promising", "surprising", "exercising", "compromising",
    "raising", "praising", "arising", "supervising", "revising", "devising",
    "improvising", "cruising", "disguising", "televising", "chastising",
    "despising", "advertising", "franchising", "merchandising", "uprising",
    "enterprising", "unsurprising", "unpromising", "poised", "advertised",
]
# Every -ise word above in its -ises form too, now that -ises is read: "supervises"
# and "advises" are spelled that way in every variety.
LEGITIMATE_ISE += sorted({w + "s" for w in LEGITIMATE_ISE if w.endswith("ise")}
                         - set(LEGITIMATE_ISE))

# The app's own rules, which apply to everyone. The locale rules follow the
# profile's documents settings: the document noun the market does NOT use, and
# the spelling variant. The rest are writing slips.
_DOC = person.get("documents", {})
# A person's documents can carry proper nouns of their own that end in -ise (a
# product an employer names, say); their claims.py lists them as LEGITIMATE_ISE.
if person.exists("claims.py"):
    LEGITIMATE_ISE = LEGITIMATE_ISE + list(getattr(person.module("claims"), "LEGITIMATE_ISE", []))
_VARIANT_WORDS = {
    # spelling -> (forms that are wrong in it, why)
    "canadian": (r"\b(behaviors?|behavioral|modeling|modelers?|centers?)\b",
                 "Canadian English keeps modelling, behaviour and centre. Use American "
                 "spelling only for a US posting, and then consistently throughout."),
    "american": (r"\b(behaviours?|behavioural|modelling|modellers?|centres?|colours?|favours?|analyses?)\b",
                 "American English: behavior, modeling, center, color, favor, analyze."),
    "british": (r"\b(behaviors?|behavioral|modeling|modelers?|centers?|colors?|favors?|analyzes?)\b",
                "British English: behaviour, modelling, centre, colour, favour, analyse."),
    "australian": (r"\b(behavior|behavioral|modeling|modeler|center|color|favor|analyze)\b",
                   "Australian English: behaviour, modelling, centre, colour, favour, analyse."),
}


def app_rules() -> dict:
    """name -> (severity, name, pattern, why), in the app's order."""
    r = {}
    if "\u2014" in _DOC.get("banned_characters", ["\u2014", "\u2013"]):
        r["em-dash"] = ("ERROR", "em-dash", r"\u2014",
                        "No em dashes anywhere, per CLAUDE.md and rule 7.")
    noun = _DOC.get("noun", "resume")
    for banned in _DOC.get("banned_nouns", []):
        name = "the-word-" + re.sub(r"[^a-z0-9]+", "-", banned.lower())
        r[name] = ("ERROR", name, r"\b%s\b" % re.escape(banned),
                   f"The document is a {noun}, never a {banned}, in anything the employer sees.")
    spelling = _DOC.get("spelling", "")
    if spelling in ("canadian", "american"):
        # Only flags -ise forms that have a real -ize counterpart. Words that are
        # spelled -ise in every variety of English (enterprise, expertise,
        # precise, comprise, supervise, advise, otherwise, ...) are excluded, or
        # the check fires on "enterprise-scale" in every resume and gets ignored.
        why = ("Canadian English uses -ize/-ization. (modelling, behaviour and centre "
               "keep their British forms and are not matched here.)"
               if spelling == "canadian" else "American English uses -ize/-ization.")
        r["british-ise-spelling"] = (
            "ERROR", "british-ise-spelling",
            r"\b(?!(?:" + "|".join(LEGITIMATE_ISE) + r")\b)\w{4,}(?:ise|ises|ised|ising|isation|isations)\b",
            why)
    if spelling in _VARIANT_WORDS:
        pat, why = _VARIANT_WORDS[spelling]
        r["american-spelling" if spelling == "canadian" else f"{spelling}-spelling"] = (
            "ERROR", "american-spelling" if spelling == "canadian" else f"{spelling}-spelling",
            pat, why)
    r["duplicated-word"] = ("ERROR", "duplicated-word", r"\b([^\W\d_]{3,})\s+\1\b",
                            "A word is repeated. Usually an editing slip.")
    r["unsupported-connective"] = (
        "WARN", "unsupported-connective",
        r"\bin parallel\b|\bsimultaneously\b|\bwhile also\b",
        "Asserts two things happened together. The profile rarely supports that; "
        "check it does before keeping the phrase.")
    return r


def _assemble():
    """The profile's rules in its order, with "@name" placing an app rule; any
    app rule the profile does not place runs after them."""
    mine = person.module("claims") if person.exists("claims.py") else None
    rules = app_rules()
    out = []
    for entry in getattr(mine, "CHECKS", []):
        if isinstance(entry, str) and entry.startswith("@"):
            if entry[1:] in rules:
                out.append(rules.pop(entry[1:]))
        else:
            out.append(tuple(entry))
    out.extend(rules.values())
    return out, list(getattr(mine, "FIGURE_DRIFT", []))


# (severity, name, pattern, why) - pattern is searched case-insensitively.
# ERROR means "this is wrong"; WARN means "look at this, it is often wrong".
# FIGURE_DRIFT: (pattern, why) for figures whose exact form the profile fixes;
# a drift is an escalation.
CHECKS, FIGURE_DRIFT = _assemble()


def strip_latex(text: str) -> str:
    """Remove commands and comments so patterns match prose, not markup."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        out.append(line)
    t = "\n".join(out)
    t = re.sub(r"\\textbackslash|\\textasciitilde\{\}", "~", t)
    # Drop \begin{env} / \end{env} with the environment name, or a document full
    # of itemize blocks reports a phantom "itemize itemize" duplicated word.
    t = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}", " ", t)
    # Drop fontspec/geometry style option blocks, which are not prose.
    t = re.sub(r"\\fontspec\s*\[[^\]]*\]", " ", t)
    t = re.sub(r"\\(?:textbf|textit|emph|href|url|item|section|item)\b", " ", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
    # Separate LaTeX fields with a sentinel rather than a space: "University of
    # Leeds}{Leeds, UK" is two distinct cventry fields, and collapsing the brace
    # to a space makes it read as the duplicated word "Leeds Leeds".
    t = t.replace("{", " \u00a6 ").replace("}", " \u00a6 ")
    return t


def check(path: str) -> list[tuple[str, str, str, str]]:
    raw = open(path, encoding="utf-8").read()
    text = strip_latex(raw)
    findings = []
    for sev, name, pat, why in CHECKS:
        for m in re.finditer(pat, text, re.I | re.S):
            snippet = re.sub(r"\s+", " ", m.group(0))[:110]
            findings.append((sev, name, snippet, why))
    for pat, why in FIGURE_DRIFT:
        for m in re.finditer(pat, text, re.I):
            findings.append(("ERROR", "figure-drift",
                             re.sub(r"\s+", " ", m.group(0))[:80], why))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--quiet", action="store_true",
                    help="print only files with findings")
    a = ap.parse_args()

    errors = 0
    for path in a.files:
        found = check(path)
        if not found and a.quiet:
            continue
        if not found:
            print(f"OK    {path}")
            continue
        print(f"\n{path}")
        for sev, name, snippet, why in found:
            if sev == "ERROR":
                errors += 1
            print(f"  {sev:5} [{name}]  ...{snippet}...")
            print(f"        {why}")
    print(f"\n{errors} error-level finding(s) across {len(a.files)} file(s).",
          file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
