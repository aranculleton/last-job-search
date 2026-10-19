"""fit_to_page's report flags an application by the profile's page count.

The flag read `resume_pages == 1`, so a profile whose `documents.resume_pages`
is 2 had every application marked CHECK however well it fitted, and a flag that
is always on is read by nobody. `MAX_LINES` beside it was used by nothing.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit_to_page  # noqa: E402


def test_the_flag_follows_the_profiles_page_count(monkeypatch):
    monkeypatch.setattr(fit_to_page, "PAGES", 2)
    assert not fit_to_page.needs_check(2, 1, 220)
    assert not fit_to_page.needs_check(1, 1, 220)
    assert fit_to_page.needs_check(3, 1, 220)
    monkeypatch.setattr(fit_to_page, "PAGES", 1)
    assert fit_to_page.needs_check(2, 1, 220)
    assert not fit_to_page.needs_check(1, 1, 220)


def test_the_letter_and_its_words_still_flag():
    assert fit_to_page.needs_check(1, 2, 200)
    assert fit_to_page.needs_check(1, 1, fit_to_page.MAX_BODY_WORDS + 1)


def test_no_unused_line_budget_is_left_to_mislead():
    assert not hasattr(fit_to_page, "MAX_LINES")
