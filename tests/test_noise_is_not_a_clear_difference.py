"""Noise is not reported as a clear difference.

`what_works.differences()` takes the best and the worst group of each feature and asked a
two-proportion z-test at 8 a group whether they differ, as if that pair had been chosen
beforehand, over four features for `brief search` and six for `brief messages`. Simulated
with every group sharing one true rate, it called a difference clear in about a third of
briefs (three groups of ten, four features) and over half (four groups of twelve). The
brief says "unlikely to be chance", and the person reads it as which route or which kind
of role works. Fisher's exact test, twenty a group, and the 5% shared across every pair
the brief looked at keep that promise; the output keeps its shape.
"""
from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import what_works as W  # noqa: E402


def _cases(rates, n, features, rng):
    out = []
    for f in range(features):
        for g, p in enumerate(rates):
            out += [{"f%d" % f: "group %d" % g, "won": rng.random() < p} for _ in range(n)]
    return out


def _clear_share(rates, n, features, trials, seed):
    rng = random.Random(seed)
    names = tuple("f%d" % f for f in range(features))
    return sum(bool(W.differences(_cases(rates, n, features, rng), names, "won"))
               for _ in range(trials)) / trials


def test_fishers_exact_test_is_the_one_in_the_books():
    # The lady tasting tea: 3 of 4 against 1 of 4, two-sided p = 34/70.
    assert abs(W.fisher_p(3, 4, 1, 4) - 34 / 70) < 1e-12
    assert W.fisher_p(0, 20, 0, 20) == 1.0 and W.fisher_p(5, 20, 5, 20) == 1.0


def test_groups_that_all_share_one_rate_are_rarely_called_different():
    # Three groups a feature, four features, every group answering 30% of the time.
    # The z-test at eight a group called this clear in about four briefs in ten.
    assert _clear_share([0.3] * 3, 20, 4, trials=400, seed=7) <= 0.05
    assert _clear_share([0.3] * 4, 12, 4, trials=100, seed=7) == 0.0      # under the floor


def test_a_real_gap_is_still_found():
    assert _clear_share([0.7, 0.1], 20, 1, trials=200, seed=7) >= 0.9


def test_the_more_pairs_a_brief_looks_at_the_wider_a_gap_must_be():
    # 11 of 20 against 3 of 20 clears one comparison and not twelve.
    assert W.clear(11, 20, 3, 20) and not W.clear(11, 20, 3, 20, comparisons=12)


def test_the_line_says_the_same_thing_it_always_did():
    cases = [{"route": "alumni", "won": i < 15} for i in range(20)] + \
            [{"route": "cold", "won": i < 2} for i in range(20)]
    assert W.differences(cases, ("route",), "answered") == [
        "By route: alumni answered 15 of 20 (75%); cold answered 2 of 20 (10%)."]
