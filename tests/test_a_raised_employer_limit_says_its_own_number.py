"""A note past the usual number at an employer, on the person's word, says the numbers right.

Saving a note at an employer where the person allowed more people than usual said "more than 2
at <employer>" with the usual number however many they had allowed there, and at exactly the
usual number (the audit of 2026-11-10, NW-27). The line now says how many with this one, the
usual number, and the person's own number there. Every employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402
from company_key import key  # noqa: E402

WORD = {"employer": "Quayside Foods", "limit": 4, "said": "go up to four at Quayside",
        "date": "2026-11-01"}


def test_the_line_says_how_many_the_usual_and_their_own_number(monkeypatch):
    monkeypatch.setattr(reading, "PER_EMPLOYER", 2)
    monkeypatch.setattr(reading, "more_at", lambda: {key("Quayside Foods"): WORD})
    line = reading.beyond_usual_line("Quayside Foods", 3)
    assert line.startswith("3 people at Quayside Foods with this one, past the usual 2"), line
    assert "up to 4 there" in line and "go up to four at Quayside" in line, line
    assert reading.beyond_usual_line("Quayside Foods", 2) == ""      # at the usual: nothing past
    monkeypatch.setattr(reading, "more_at", lambda: {key("Quayside Foods"): dict(WORD, limit=None)})
    assert "no number of the app's there" in reading.beyond_usual_line("Quayside Foods", 5)
    monkeypatch.setattr(reading, "more_at", lambda: {})
    assert reading.beyond_usual_line("Quayside Foods", 5) == ""


def test_the_save_says_it_through_the_one_line():
    with open(os.path.join(ROOT, "tools", "network", "reading.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "more than {PER_EMPLOYER} at {company}" not in text
    assert "beyond_usual_line(company," in text
