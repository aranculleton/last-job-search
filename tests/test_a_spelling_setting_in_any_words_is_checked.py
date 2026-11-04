"""A spelling setting written the way the market tables write it still switches the check on.

Setup writes documents.spelling from the research, and the tables say "New Zealand English
(British forms: colour, organise)", "Irish and British English (en-IE)" or "British English".
The checks knew only four bare words, so any other value ran every resume and letter with
no spelling rule at all, while the drafting pack promised one ("Spelling: new zealand
throughout [code]"). A value is now read for the variety it names, and a value the checks
still do not know is said plainly: the pack no longer claims a check, and the profile's
documents upgrade lists it.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import draft_pack  # noqa: E402
import locale_rules  # noqa: E402
import person  # noqa: E402
import profile_upgrades  # noqa: E402

TEXT = ("I organized the color palette, analyzed customer behavior and centered the "
        "program on modeling.")


def flagged(spelling):
    L = locale_rules.for_documents({"spelling": spelling})
    return sorted({m.group(0).lower() for _, m in L.wrong_spellings(TEXT)})


@pytest.mark.parametrize("spelling", [
    "new zealand", "new_zealand", "nz", "New Zealand English (British forms: colour, organise)",
    "irish", "Irish and British English (en-IE)", "indian", "Indian English (British forms)",
    "south african", "singapore", "en-GB", "en_GB", "British English", "UK English",
])
def test_every_british_form_of_the_setting_checks_british_spelling(spelling):
    assert flagged(spelling) == flagged("british")
    assert "color" in flagged(spelling) and "organized" in flagged(spelling)


@pytest.mark.parametrize("spelling,variety", [
    ("en-US", "american"), ("American English", "american"), ("US", "american"),
    ("en-CA", "canadian"), ("Canadian English", "canadian"),
    ("en-AU", "australian"), ("Australian English", "australian"),
])
def test_the_other_varieties_in_their_codes_and_names(spelling, variety):
    assert locale_rules.spelling_variety(spelling) == variety
    assert flagged(spelling) == flagged(variety)


def test_a_document_in_another_language_has_no_english_variety():
    assert locale_rules.spelling_variety("German (neue Rechtschreibung)") == ""
    assert locale_rules.spelling_variety("") == ""


def test_the_pack_promises_a_spelling_check_only_where_there_is_one(monkeypatch):
    docs = {"noun": "CV", "banned_nouns": ["resume"]}

    def lines(spelling):
        monkeypatch.setattr(person, "get", lambda key, default=None: (
            dict(docs, spelling=spelling) if key == "documents" else default))
        return draft_pack.locale_lines()[0]

    nz = lines("New Zealand English (British forms: colour, organise)")
    assert nz.startswith("Spelling: british English throughout") and "[code]" in nz
    unknown = lines("Klingon")
    assert "[code]" not in unknown.split(".")[0] and "no spelling check" in unknown


def test_an_unknown_english_setting_is_listed_as_an_upgrade(monkeypatch):
    real = person.get

    def get(key, default=None):
        if key == "documents.spelling":
            return "Plain English"
        return real(key, default)

    monkeypatch.setattr(person, "get", get)
    assert "spelling" in profile_upgrades._letter_language()
    monkeypatch.setattr(person, "get", lambda key, default=None: (
        "New Zealand English" if key == "documents.spelling" else real(key, default)))
    assert profile_upgrades._letter_language() == ""
