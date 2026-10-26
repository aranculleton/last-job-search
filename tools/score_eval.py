#!/usr/bin/env python3
"""Measure what a scoring change actually did, instead of arguing about it.

`tests/fixtures/screened_postings/` is a regression corpus for the SCREEN: a
`cut__` file must keep being cut, a `pass__` file must keep passing. It works,
and it is the reason the screen has not silently started deleting good roles.

`fit.py` had no equivalent. Every weight, every demand multiplier, every bridge
factor and every floor in it was set by argument, and once set there was no way
to distinguish an improvement from a lucky change. The only feedback was a
person reading a shortlist and feeling that it looked better or worse.

The honest design here is a BASELINE, not a label set. Nobody knows the true
fit score of a posting, so inventing one would be dressing an opinion up as
data. What can be known is what the scorer said last time, and that a change of
eleven points on a posting nobody meant to touch is worth looking at before it
ships.

So: score every fixture, compare against the recorded baseline, and report the
drift. `--update` re-records, which is a deliberate act that shows up in a diff
next to the change that caused it.

On top of the baseline sit the expectations, which are the assertions that can be
defended without knowing an exact number, and each fixture's name says its own: a
`cut__` posting must be gated, a `pass__` one must not. Those hold across any
retuning, and a change that breaks one is wrong rather than merely different.

Usage:
    python3 tools/score_eval.py                 compare against the baseline
    python3 tools/score_eval.py --update        re-record it
    python3 tools/score_eval.py --tolerance 5   allow more drift per posting
Exit 0 clean, 1 drift beyond tolerance or a broken expectation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit as fit_mod           # noqa: E402
import person                   # noqa: E402
import text_screen              # noqa: E402

# A corpus posting with no location line is read as being in the home city.
_HOME = (list(getattr(person.module("search"), "SCRAPE_LOCATIONS", ())) or [""])[0]

# The corpus and its baseline are the person's: real postings screened for one
# search, and the scores one profile gave them. They live with the person's
# own tests (profile/tests/fixtures/).
CORPUS = person.path("tests", "fixtures", "screened_postings")
BASELINE = person.path("tests", "fixtures", "score_baseline.json")

# Drift larger than this on one posting is reported. Small enough to catch a
# real change, large enough that rounding does not cry wolf.
DEFAULT_TOLERANCE = 3

# What must hold whatever the weights are retuned to, read from each fixture's name.
#
# An expectation is only worth writing where the answer is defensible without knowing
# the exact number, and a fixture's name is that answer: the corpus names every file
# `cut__*` or `pass__*` for what must happen to it (MAINTAINING.md, "Adding a test").
# These were four stems of one person's corpus written out here, so every other
# person's corpus failed on four files it never had, the run straight after --update
# included.
EXPECTED_BY_NAME = {
    "cut__": {"screened": True, "why": "named cut__: it must keep being cut"},
    "pass__": {"screened": False, "why": "named pass__: it must keep passing"},
}


def expectations(stems) -> dict[str, dict]:
    """{stem: what must hold} for the fixtures there are, from their names."""
    return {stem: want for stem in stems for prefix, want in EXPECTED_BY_NAME.items()
            if stem.startswith(prefix)}


class _HardCuts(Mapping):
    """The hard cuts of the corpus there is: {stem: what must hold} for its `cut__` postings,
    read each time it is looked at, so a corpus changed since import is the one read."""

    def _now(self) -> dict[str, dict]:
        stems = sorted(n[:-4] for n in os.listdir(CORPUS) if n.endswith(".txt")) \
            if os.path.isdir(CORPUS) else []
        return {s: w for s, w in expectations(stems).items() if s.startswith("cut__")}

    def __getitem__(self, stem):
        return self._now()[stem]

    def __iter__(self):
        return iter(self._now())

    def __len__(self):
        return len(self._now())


# Kept for the people whose own tests use it (profile/tests): the name this module's
# expectations had until 2026-10-25, when it was four stems of one person's corpus written
# out, all four hard cuts. It now reads the cuts of whatever corpus there is; expectations()
# and EXPECTED_BY_NAME are what the check reads, `pass__` postings included. A public name
# stays while a test may.
EXPECTATIONS: Mapping[str, dict] = _HardCuts()


def _title_and_location(text: str) -> tuple[str, str]:
    """The corpus keeps 'Company | Title' on line 1 and the location on line 2."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    head = lines[0] if lines else ""
    title = head.split("|")[-1].strip() if "|" in head else head
    location = lines[1] if len(lines) > 1 else _HOME
    return title, location


def _company(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    head = lines[0] if lines else ""
    return head.split("|")[0].strip() if "|" in head else ""


def cases() -> list[dict]:
    out = []
    for name in sorted(os.listdir(CORPUS)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(CORPUS, name)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        title, location = _title_and_location(body)
        out.append({"stem": name[:-4], "title": title, "location": location,
                    "company": _company(body), "desc": body})
    return out


def evaluate(case: dict) -> dict:
    """What the pipeline says about one posting, at the points worth pinning."""
    job = {"title": case["title"], "desc": case["desc"],
           "company": case["company"], "location": case["location"]}
    screened = False
    screen_reason = ""
    try:
        verdict = text_screen.screen(job)
        cuts = verdict.get("cuts") or []
        screened = verdict.get("text_screen") == "cut" or bool(cuts)
        screen_reason = "; ".join(cuts) or str(verdict.get("text_screen") or "")
    except Exception as exc:                      # a screen that raises is a finding
        screen_reason = f"{type(exc).__name__}: {exc}"

    scored = fit_mod.fit(job)
    low, high, _ = text_screen.entry_years(case["desc"])
    return {
        "stem": case["stem"],
        "fit": scored["fit"],
        "entry_years": low,
        "top_years": high,
        "screened": screened,
        "screen_reason": screen_reason[:120],
        "above_floor": scored["fit"] >= fit_mod.FIT_FLOOR,
    }


def load_baseline() -> dict:
    try:
        with open(BASELINE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def compare(now: list[dict], before: dict, tolerance: int) -> list[str]:
    findings = []
    for row in now:
        old = before.get(row["stem"])
        if old is None:
            findings.append(f"NEW    {row['stem']}: fit {row['fit']} (no baseline)")
            continue
        delta = row["fit"] - old.get("fit", row["fit"])
        if abs(delta) > tolerance:
            findings.append(
                f"DRIFT  {row['stem']}: fit {old.get('fit')} -> {row['fit']} ({delta:+d})")
        if row["screened"] != old.get("screened", row["screened"]):
            findings.append(
                f"GATE   {row['stem']}: screened {old.get('screened')} -> {row['screened']}")
    gone = sorted(set(before) - {r["stem"] for r in now})
    findings.extend(f"GONE   {stem}: in the baseline, not in the corpus" for stem in gone)
    return findings


def check_expectations(now: list[dict]) -> list[str]:
    broken = []
    by_stem = {r["stem"]: r for r in now}
    for stem, want in expectations(by_stem).items():
        row = by_stem[stem]
        for field, value in want.items():
            if field == "why":
                continue
            if row.get(field) != value:
                broken.append(f"BROKE  {stem}: {field} is {row.get(field)!r}, "
                              f"expected {value!r} ({want['why']})")
    return broken


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="re-record the baseline")
    ap.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()
    if not os.path.isdir(CORPUS):
        print("score_eval: no screened-postings corpus here (profile/tests/fixtures/"
              "screened_postings, a person's own), so there is nothing to score")
        return 0

    now = [evaluate(c) for c in cases()]
    if a.update:
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({r["stem"]: r for r in now}, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"score_eval: baseline re-recorded over {len(now)} postings")
        return 0

    if a.json:
        print(json.dumps(now, indent=1))
        return 0

    findings = compare(now, load_baseline(), a.tolerance)
    broken = check_expectations(now)
    scores = sorted(r["fit"] for r in now)
    print(f"score_eval: {len(now)} postings, fit {scores[0]} to {scores[-1]}, "
          f"median {scores[len(scores) // 2]}")
    for line in broken + findings:
        print("  " + line)
    if broken:
        print("  An expectation is an assertion that holds across any retuning. "
              "A change that breaks one is wrong, not merely different.")
    if findings and not broken:
        print("  Drift is not automatically bad. If the change was intended, "
              "re-record with --update in the same commit.")
    return 1 if (broken or findings) else 0


if __name__ == "__main__":
    sys.exit(main())
