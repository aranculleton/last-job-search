"""One list of legal forms and one display name for an employer.

The people search (`discovery.search_name`) and the letter's salutation and the
outreach note (`render_application.short_name`) each kept their own list, and
each had a fix the other lacked: the search turned "Tamworth & Co." into
"Tamworth &", the salutation printed "(UK)" and "AS", and "ULC" and "Pvt Ltd"
came off only in the salutation. `company_key.display_name` is the one list;
each caller keeps its own rule about Group, Company and Holdings.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import company_key  # noqa: E402
import discovery as D  # noqa: E402
import render_application as R  # noqa: E402


@pytest.mark.parametrize("company,name", [
    ("Tamworth & Co.", "Tamworth & Co."),
    ("Tamworth & Co., Ltd.", "Tamworth & Co."),
    ("Acme ULC", "Acme"), ("Acme Pvt Ltd", "Acme"), ("Acme Pte. Ltd.", "Acme"),
    ("Fjordline AS", "Fjordline"), ("Fjordline A/S", "Fjordline"),
    ("Fernhill Freight Services Limited (UK)", "Fernhill Freight Services"),
    ("Acme Company", "Acme"), ("Brindle and Co", "Brindle and Co"),
])
def test_the_people_search_name(company, name):
    assert D.search_name(company) == name


@pytest.mark.parametrize("company,short", [
    ("Acme Analytics Inc. (UK)", "Acme Analytics"), ("Fjordline AS", "Fjordline"),
    ("Harbour Group (UK)", "Harbour Group"), ("Tamworth & Co., Ltd.", "Tamworth & Co"),
    ("Acme Company", "Acme Company"), ("The Northwind Group Limited", "Northwind"),
    ("Kestrel Mutual Insurance Ltd", "Kestrel Mutual Insurance"),
])
def test_the_name_a_letter_and_a_note_use(company, short):
    assert R.short_name(company) == short


def test_there_is_one_list():
    assert R.LEGAL_SUFFIX is company_key.LEGAL_FORM
    assert R.strip_legal("Acme Pty Ltd") == company_key.display_name("Acme Pty Ltd") == "Acme"
    assert not hasattr(D, "_LEGAL_TAIL")


def test_the_join_key_is_untouched():
    assert company_key.key("Acme Analytics Inc. (UK)") == company_key.key("Acme Analytics")
    assert company_key.key("Tamworth & Co.") == company_key.key("Tamworth")
