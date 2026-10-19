"""An employer written "Long Name (SHORT)" is one employer with SHORT.

A pension plan's bracket kept the small word in its initials ("of" counted), and the
join only knew initials with the small words left out, so the long name and the short
one keyed apart: a thread and an application at one employer never linked.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import company_key  # noqa: E402


def test_a_bracketed_initialism_counts_small_words_either_way():
    company_key.learn(["Northgate of Lakeshore Pension Plan (NOLPP)"])
    assert company_key.key("NOLPP") == company_key.key("Northgate of Lakeshore Pension Plan")
    company_key.learn(["Fernhill and Larkspur Trust (FLT)"])
    assert company_key.key("FLT") == company_key.key("Fernhill and Larkspur Trust")


def test_a_bracketed_short_name_that_starts_the_name_joins_it():
    company_key.learn(["Brindle Hart Capital Partners (Brindle Hart)"])
    assert company_key.key("Brindle Hart") == company_key.key("Brindle Hart Capital Partners")


def test_a_listing_detail_in_brackets_is_never_a_name():
    for name in ("Acme Bank (UK)", "Acme Bank (Remote)", "Acme Bank (Contract)",
                 "Acme Bank (AB Group)", "Acme of Bank (XYZ)"):
        assert company_key._own_initialism(name) == "", name
    assert company_key.key("Acme Bank (UK)") == company_key.key("Acme Bank")
