"""Every theme cue is a literal phrase that can match a posting.

`allocate.CUE_RE` escapes each cue, so "optimi[sz]ation of pricing", written as a pattern,
matched nothing at all: a posting about the optimisation of pricing gained nothing on
experimentation from it (the drafting audit, 2026-10-25).
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import allocate  # noqa: E402


def test_no_cue_is_written_as_a_pattern():
    bad = [(t, c) for t, cues in allocate.THEME_CUES.items() for c in cues
           if re.search(r"[\[\](){}*+?|\\^$]", c)]
    assert bad == []


def test_each_cue_matches_itself():
    for theme, cues in allocate.THEME_CUES.items():
        for cue, rx in zip(cues, allocate.CUE_RE[theme]):
            assert rx.search(cue.lower()), (theme, cue)


def test_the_optimisation_of_pricing_is_experiment_work_in_either_spelling():
    for text in ("Responsible for the optimisation of pricing across plans.",
                 "Responsible for the optimization of pricing across plans."):
        assert allocate.theme_scores(text).get("experimentation"), text
