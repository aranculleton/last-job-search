"""Pay is read however a posting writes it: no currency mark, decimals, by the hour, a
heading on the line above, or one band per place.

From one person's run, each of these was read as no salary stated, so the posting
skipped both the pay cut and the pay score, and a band per place was read as its highest,
so the band for the person's own city, under their cut line, was never cut.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import places  # noqa: E402
import text_screen as T  # noqa: E402


@pytest.fixture
def market(monkeypatch):
    values, labelled = T.money_parser("$", "CAD")
    monkeypatch.setattr(T, "money_values", values)
    monkeypatch.setattr(T, "labelled_value", labelled)
    monkeypatch.setattr(T, "_BOUNDS", (30_000, 500_000))
    monkeypatch.setattr(T, "FOREIGN_CURRENCY", re.compile(r"\b(usd|us\s?\$)\b|us\$", re.I))
    monkeypatch.setattr(places, "METRO", ("larkspur", "fernhill"))


@pytest.mark.parametrize("text,band", [
    ("The salary range for this role is CA$110,000-CA$130,000.", (110_000, 130_000)),
    ("Salary: 95-125K", (95_000, 125_000)),
    ("The base pay is 95,000.00 - 125,000.00 annually.", (95_000, 125_000)),
    ("Compensation: 110k - 130k", (110_000, 130_000)),
    ("Salary Range\nCA$110,000-CA$130,000", (110_000, 130_000)),
    ("The hourly pay range is $45 - $55 per hour.", (93_600, 114_400)),
    ("Salary range: $45.00/hr - $55.00/hr", (93_600, 114_400)),
])
def test_a_band_however_it_is_written(market, text, band):
    assert T.salary_range(text)[:2] == band


def test_the_band_for_their_own_place_is_the_one_read(market):
    both = "Pay range: $58,000 - $66,000 (Larkspur), $70,000 - $80,000 (Kestrel City)"
    assert T.salary_range(both)[:2] == (58_000, 66_000)
    other = "Salary range: Kestrel City $70,000 - $80,000; Larkspur $58,000 - $66,000."
    assert T.salary_range(other)[:2] == (58_000, 66_000)
    # No band names their place: the highest, as before.
    elsewhere = "Pay range: $58,000 - $66,000 (Brannock), $70,000 - $80,000 (Kestrel City)"
    assert T.salary_range(elsewhere)[:2] == (70_000, 80_000)


@pytest.mark.parametrize("text", [
    "We have 5-7 years of history and 2020-2024 growth. Salary is competitive.",
    "Join our team of 120 - 150 analysts with an annual offsite.",
    "The salary range is USD 110,000 - 130,000.",
])
def test_what_is_not_a_band_in_their_currency_is_not_read(market, text):
    assert T.salary_range(text)[:2] == (None, None)


def test_a_single_labelled_figure_still_reads_and_a_401k_is_not_a_band(market):
    assert T.salary_range("Salary: $105,000 plus a 401k match.")[:2] == (105_000, 105_000)


# The band for their own place is chosen by the one place matcher the residence cut
# uses. The pay reader kept a copy that matched a metro town inside any word and the
# home country only in the case the profile wrote it, so with a metro holding Sale and
# Bury, a "wholesale" desk and a Canterbury office both read as home, and a band
# marked "(UK remote)" did not. The example person lives in Greater Manchester.
@pytest.mark.parametrize("text,band", [
    # Neither band is theirs: the highest, as for any posting with no home band.
    ("Salary: £30,000 - £33,000 on our wholesale desk; £50,000 - £60,000 in London.",
     (50_000, 60_000)),
    ("Salary: £30,000 - £33,000 (Canterbury); £50,000 - £60,000 (London).",
     (50_000, 60_000)),
    # Their country, however the posting cases it.
    ("Salary: £70,000 - £80,000 (US remote); £50,000 - £60,000 (UK remote).",
     (50_000, 60_000)),
    # Their own metro, written as a town on its own, still wins.
    ("Salary: £50,000 - £60,000 (London); £40,000 - £45,000 (Sale).", (40_000, 45_000)),
])
def test_their_own_place_is_read_as_a_place_not_inside_a_word(text, band):
    assert T.salary_range(text)[:2] == band


def test_the_pay_reader_and_the_residence_cut_agree_on_home():
    for part in ("(Wholesale team, London)", "(Canterbury)", "remote within the UK",
                 "(Bury)", "Manchester, NH"):
        assert T._home(part) == T._names_home(part), part
