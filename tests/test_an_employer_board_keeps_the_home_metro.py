"""An employer board keeps a posting in any town of the home metro, not only the ones it lists.

`ats_boards._wanted` kept a posting only when its location matched
profile/boards.py PLACES. For the example person "Bolton", "Altrincham", "Wigan"
and "Sale" pass the prefilter as the home metro and were dropped here first, so
a posting on a target employer's own board in one of them never reached a
round. The home metro and the home country are read too; a remote posting that
names somewhere else, which this filter rejects on purpose, still is.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402


def test_every_home_metro_town_and_the_home_country_are_wanted():
    for loc in ("Bolton", "Altrincham", "Wigan", "Sale", "Ashton-under-Lyne",
                "Remote - United Kingdom", "Remote, GB"):
        assert ats_boards._wanted(loc), loc
        assert ats_boards._choose([loc])[0] == loc, loc


def test_what_was_rejected_on_purpose_still_is():
    # "Remote - SF Bay Area" passes the prefilter as remote; this filter wants
    # positive evidence of a place the person can work.
    for loc in ("Remote - SF Bay Area", "Hybrid", "Distributed", "Remote Poland", ""):
        assert not ats_boards._wanted(loc), loc
