"""An employer's name with accents keeps its letters in a file name, and Acme and ACME
are one name, as they are one file on a Mac or Windows.

doc_name dropped every letter outside ASCII, so Société Générale's documents were
`<Name>_Resume_SocitGnrale`, Nestlé's `Nestl` and Ørsted's `rsted` (2026-10-25). The
batch check compared names case by case, and two roles named Acme and ACME wrote one
file. An application made under an old name keeps it: its files and tracker row carry
it. The people and employers here are invented or the plain examples above.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import doc_name  # noqa: E402


@pytest.mark.parametrize("company, want", [
    ("Société Générale", "Societe"),            # two words over the length cap: the first
    ("Nestlé", "Nestle"),
    ("Ørsted", "Orsted"),
    ("Brandt Straße Logistik", "BrandtStrasse"),
    ("Łódź Freight", "LodzFreight"),
    ("Acme Ltd", "Acme"),
])
def test_accented_letters_keep_their_base_letter(company, want):
    assert doc_name.suffix(company) == want


def test_an_application_already_made_under_the_old_name_keeps_it(tmp_path, monkeypatch):
    import render_application as R
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [
        {"company": "Nestlé", "role": "Analyst", "status": "applied",
         "cv_file": f"cv/{doc_name.docpaths.resume_stem('Nestl')}.tex"}])
    assert R.final_abbr({"company": "Nestlé", "role": "Analyst"}) == "Nestl"
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [])
    monkeypatch.setattr(R.os.path, "exists", lambda p: False)
    assert R.final_abbr({"company": "Nestlé", "role": "Analyst"}) == "Nestle"


def test_two_names_that_differ_only_in_case_are_one_file(monkeypatch):
    import render_application as R
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [])
    monkeypatch.setattr(R, "final_abbr", lambda a: a["abbr"])
    apps = [{"company": "Acme", "role": "Analyst", "abbr": "Acme"},
            {"company": "ACME", "role": "Engineer", "abbr": "ACME"}]
    with pytest.raises(FileExistsError, match="claimed twice"):
        R.check_batch(apps, rows=[])
