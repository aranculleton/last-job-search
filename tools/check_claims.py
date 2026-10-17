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
import locale_rules  # noqa: E402
import person  # noqa: E402

# The app's own rules apply to everyone. The locale rules among them (the
# dashes, the document noun the market does NOT use, the spelling variant)
# follow the profile's documents settings, and tools/locale_rules.py is the one
# copy every reader takes them from. These names are kept so a caller that read
# them here still can. The rest are writing slips.
_LOCALE = locale_rules.LOCALE
LEGITIMATE_ISE = _LOCALE.legitimate_ise
_VARIANT_WORDS = {k: (pat, why) for k, (_, pat, why) in locale_rules.VARIANT_WORDS.items()}


def app_rules() -> dict:
    """name -> (severity, name, pattern, why), in the app's order."""
    r = {}
    L = _LOCALE
    if L.dash_pattern:
        # Every character the profile bans, and the dash typed as "--" or "---",
        # which is how LaTeX writes both. The name is the one profiles place.
        r["em-dash"] = ("ERROR", "em-dash", L.dash_pattern,
                        "No em dashes anywhere, per CLAUDE.md and rule 7, nor any other "
                        "character documents.banned_characters names, typed as -- or --- "
                        "included.")
    for n in L.nouns:
        name = "the-word-" + re.sub(r"[^a-z0-9]+", "-", n.word.lower())
        r[name] = ("ERROR", name, n.document.pattern,
                   f"The document is a {L.noun}, never a {n.word}, in anything the employer sees.")
    if L.ise is not None:
        r["british-ise-spelling"] = ("ERROR", "british-ise-spelling", L.ise.pattern, L.ise_why)
    if L.variant is not None:
        name = "american-spelling" if L.spelling == "canadian" else f"{L.spelling}-spelling"
        r[name] = ("ERROR", name, L.variant.pattern, L.variant_why)
    # A status the person does not hold (networking.py UNSUPPORTED_STATUS), which every
    # message was already checked for: a resume or letter is held to the same.
    net = person.module("networking") if person.exists("networking.py") else None
    status = getattr(net, "UNSUPPORTED_STATUS", None)
    if status is not None and status.pattern != r"(?!x)x":
        r["unsupported-status"] = ("ERROR", "unsupported-status", status.pattern,
                                   "A status the profile does not hold: "
                                   + str(getattr(net, "UNSUPPORTED_WHY", "") or "check it"))
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
        # A comment after the markup on a line is not prose either. "\%" is a
        # percent sign, so only an unescaped one starts a comment.
        out.append(re.sub(r"(?<!\\)%.*", "", line))
    t = "\n".join(out)
    # LaTeX's named dashes, as the characters, before commands are dropped.
    t = locale_rules.latex_dashes(t)
    # A link's address is not prose: \href{address}{text} keeps the text.
    t = re.sub(r"\\(?:href|url)\s*\{[^}]*\}", " ", t)
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
