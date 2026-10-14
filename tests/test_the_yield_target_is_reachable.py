"""A profile without employer tiers can still meet the yield target.

`tools/fit.py` multiplies fit by opportunity rescaled to 0-100, and the rescale
divided by a fixed 130. That number was calibrated on a profile with employer
tiers (up to +30), brand leverage (up to +30) and core capabilities, whose raw
opportunity runs well past 130. The example person, and anybody /setup wrote
without those lists, tops out at 58: base 40, a high stated band (+12) and a
posting from the last two days (+6). So no posting's priority could pass about
45, the 60+ and 75+ target was unreachable by construction, and every round
expanded three times and then blamed a thin market.

The scale is now 130, or the most the profile can score if that is lower, and
`OPP_SCALE` in search.py pins it. A profile that reaches 130 ranks exactly as
it did.
"""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit  # noqa: E402
import opportunity  # noqa: E402

STRONG = {
    "title": "Senior Supply Chain Analyst", "company": "Wrenfield Freight Ltd",
    "location": "Manchester, England, United Kingdom", "date": "2026-10-12",
    "desc": ("Wrenfield Freight is a third-party logistics business moving chilled and "
             "ambient goods across the North West. You will own demand forecasting and "
             "inventory analytics for our network, working with operations and commercial "
             "teams. Strong SQL and Python are required, with Power BI for reporting. "
             "Experience with route planning or warehouse slotting is an advantage. "
             "Salary: £50,000 - £58,000 per year plus bonus. Hybrid, three days in our "
             "Trafford office. 5+ years of experience in an analytics role."),
}


def test_the_example_is_scaled_to_what_it_can_score():
    assert opportunity.ceiling() == 58
    assert opportunity.SCALE == 58


def test_a_profile_that_reaches_130_keeps_130():
    with mock.patch.object(opportunity, "TIER_1", {"acme"}), \
            mock.patch.object(opportunity, "CORE", [(None, 8)] * 5), \
            mock.patch.object(opportunity, "LEVERAGE", [(None, 20, "x")] * 2):
        assert opportunity.ceiling() == 40 + 30 + 40 + 30 + 12 + 6
        assert min(opportunity.CALIBRATED_SCALE, opportunity.ceiling()) == 130


def test_only_positive_terms_raise_the_ceiling():
    with mock.patch.object(opportunity, "CORE", [(None, 5), (None, -9)]), \
            mock.patch.object(opportunity, "WRONG_FAMILY", [(None, -20)]):
        assert opportunity.ceiling() == 58 + 5


def test_a_strong_posting_meets_the_target_for_the_example(tmp_path, monkeypatch):
    """Through the real path: opportunity.score, then fit.py's blend."""
    import datetime as dt
    row = opportunity.score(dict(STRONG), dt.date(2026, 10, 14))
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps([row]))
    monkeypatch.setattr(sys, "argv", ["fit.py", str(src), "--out", str(out)])
    assert fit.main() == 0
    ranked = json.loads(out.read_text())
    assert ranked[0]["priority"] >= 75, ranked[0]
