"""A letter is dated in the language it is written in, in the person's own order.

The letter's date line was always made with English month names in one of two orders, so
a Berlin stranger's letter opened "Sehr geehrte" under "3 November 2026", and a profile
whose setup wrote the market table's own date format ("DD/MM/YYYY", "DD.MM.YYYY") was
dated in the North American order. The date now follows the documents' language, taken
from documents.language, or from the one language the country's table lists when the
headings are not English; where it still cannot be told, the documents upgrade lists it.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "templates"))

import locale_rules  # noqa: E402
import person  # noqa: E402
import profile_upgrades  # noqa: E402
import resume_gen  # noqa: E402

DAY = datetime.date(2026, 11, 3)
GERMAN = {"salutation_prefix": "Sehr geehrte", "closing": "Mit freundlichen Grüßen",
          "page_label": "Seite", "date_format": "DD.MM.YYYY",
          "headings": {"summary": "Profil", "experience": "Berufserfahrung",
                       "skills": "Kenntnisse", "education": "Ausbildung"}}


_DRAFT = {
    "company": "Kestrel Mutual", "role": "Operations Analyst", "abbr": "KestrelMutual",
    "summary": "Operations analyst who builds weekly demand forecasts that move stock.",
    "tools": "SQL, Python", "posting": "Forecast weekly claims demand with SQL and Python.",
    "p1": "Claims come in waves. At Brindle & Hart I forecast demand by depot every week.",
    "p2": "Kestrel Mutual insures homes across the North West.", "lead": "Where I would start:",
    "cl_bullets": [{"label": "Forecasting", "text": "Weekly forecasts across 2,400 SKUs."}],
    "p4": "I am based in Manchester.",
}


def test_the_letter_renderer_dates_a_german_letter_in_german(monkeypatch):
    monkeypatch.setattr(resume_gen, "_DOC", dict(GERMAN, language="de"))
    assert resume_gen._long_date(DAY) == "3. November 2026"
    monkeypatch.setattr(resume_gen, "_DOC", dict(GERMAN, language="fr"))
    assert resume_gen._long_date(DAY) == "3 novembre 2026"
    monkeypatch.setattr(resume_gen, "_DOC", dict(GERMAN, language="es"))
    assert resume_gen._long_date(datetime.date(2026, 11, 1)) == "1 de noviembre de 2026"


def test_the_language_comes_from_the_country_when_the_headings_are_not_english(monkeypatch):
    monkeypatch.setattr(person, "country", lambda: "DE")
    assert locale_rules.long_date(DAY, GERMAN) == "3. November 2026"
    monkeypatch.setattr(person, "country", lambda: "BR")
    assert locale_rules.long_date(DAY, dict(GERMAN, headings={"experience": "Experiência"})) \
        == "3 de novembro de 2026"


@pytest.mark.parametrize("fmt,expected", [
    ("day_month_year", "3 November 2026"), ("DD/MM/YYYY; month and year on a CV", "3 November 2026"),
    ("month_day_year", "November 3, 2026"), ("MM/DD/YYYY", "November 3, 2026"),
    ("", "November 3, 2026"),
])
def test_an_english_letter_takes_the_order_its_setting_opens_with(fmt, expected, monkeypatch):
    monkeypatch.setattr(resume_gen, "_DOC", {"date_format": fmt, "headings": {"skills": "Skills"}})
    assert resume_gen._long_date(DAY) == expected


def test_a_letter_whose_language_cannot_be_told_is_an_upgrade(monkeypatch):
    real = person.get
    docs = dict(GERMAN)

    def get(key, default=None):
        if key == "documents":
            return docs
        if key.startswith("documents."):
            return docs.get(key.split(".", 1)[1], default)
        return real(key, default)

    monkeypatch.setattr(person, "get", get)
    monkeypatch.setattr(person, "country", lambda: "CH")        # no table: cannot be told
    assert "date" in profile_upgrades._letter_language()
    docs["language"] = "de"
    assert profile_upgrades._letter_language() == ""


def test_an_unsent_letter_kept_with_an_english_date_is_redated_in_its_language(monkeypatch):
    import render_application as R
    monkeypatch.setattr(R.gen, "_DOC", dict(GERMAN, language="de"))
    a = dict(_DRAFT, letter_date="3 November 2026")
    assert R.build(a)["letter_date"] == "3. November 2026" == a["letter_date"]
    # The same day, never the day of the re-render; a date already in its language stays.
    assert R.build(dict(_DRAFT, letter_date="3. November 2026"))["letter_date"] == "3. November 2026"
