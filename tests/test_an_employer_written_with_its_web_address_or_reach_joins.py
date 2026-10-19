"""An employer written with its web address, or with its reach before a business line,
is the same employer.

From one person's repo: "<Name>.com Services LLC", the name an employer's own postings
use, keyed as "<name> com" and joined nothing at <Name>; and "<Initials> Global Ratings"
never joined "<Initials> Global", whose key had dropped the "global". Invented names.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import company_key  # noqa: E402
import discovery  # noqa: E402


@pytest.mark.parametrize("name", ["Larkspur.com Services LLC", "Larkspur.com, Inc.", "larkspur.ca",
                                  "Larkspur.co.uk Ltd"])
def test_a_web_address_in_the_name_is_the_employer(name):
    assert company_key.key(name) == company_key.key("Larkspur") == "larkspur"


def test_initials_key_alike_however_they_are_written():
    assert company_key.key("J.P. Fernhill & Co.") == company_key.key("JP Fernhill") == "jp fernhill"
    assert company_key.key("K&M Global") == company_key.key("K & M Global") == "km"
    assert company_key.key("Kestrel.Commerce") == "kestrel commerce"     # not a web address


def test_reach_before_a_business_line_joins_the_parent():
    assert discovery.same_employer("K&M Global Ratings", "K&M Global")
    assert discovery.same_employer("Fernhill International Analytics", "Fernhill")
    assert not discovery.same_employer("Kestrel Global Partners", "Kestrel")   # not a line
