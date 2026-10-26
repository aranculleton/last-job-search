"""An employer's name with accents keeps its letters in a file name, and Acme and ACME
are one name, as they are one file on a Mac or Windows.

doc_name dropped every letter outside ASCII, so an employer called Brévanne had its
documents named `<Name>_Resume_Brvanne`, and Nørdvik's `Nrdvik` (2026-10-25). The
batch check compared names case by case, and two roles named Acme and ACME wrote one
file. An application made under an old name keeps it: its files and tracker row carry
it. The people and employers here are invented or the plain examples above.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import doc_name  # noqa: E402


@pytest.mark.parametrize("company, want", [
    ("Société de Brévanne", "Societe"),          # over the length cap: the first word
    ("Brévanne", "Brevanne"),
    ("Nørdvik", "Nordvik"),
    ("Weißfeld", "Weissfeld"),
    ("Łąkowo", "Lakowo"),
    ("Acme Ltd", "Acme"),
])
def test_accented_letters_keep_their_base_letter(company, want):
    assert doc_name.suffix(company) == want


def test_an_application_already_made_under_the_old_name_keeps_it(tmp_path, monkeypatch):
    import render_application as R
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [
        {"company": "Brévanne", "role": "Analyst", "status": "applied",
         "cv_file": f"cv/{doc_name.docpaths.resume_stem('Brvanne')}.tex"}])
    assert R.final_abbr({"company": "Brévanne", "role": "Analyst"}) == "Brvanne"
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [])
    monkeypatch.setattr(R.os.path, "exists", lambda p: False)
    assert R.final_abbr({"company": "Brévanne", "role": "Analyst"}) == "Brevanne"


def test_two_names_that_differ_only_in_case_are_one_file(monkeypatch):
    import render_application as R
    monkeypatch.setattr(doc_name, "tracker_rows", lambda: [])
    monkeypatch.setattr(R, "final_abbr", lambda a: a["abbr"])
    apps = [{"company": "Acme", "role": "Analyst", "abbr": "Acme"},
            {"company": "ACME", "role": "Engineer", "abbr": "ACME"}]
    with pytest.raises(FileExistsError, match="claimed twice"):
        R.check_batch(apps, rows=[])


# --- a name with no Latin letter, and a role's accents (the drafting audit, 2026-10-25) ----

NON_LATIN = ["架空商事", "Δοκιμή Ανάλυση", "Пример Данные", "架空物流"]


def test_a_name_with_no_latin_letter_is_never_the_empty_name():
    names = [doc_name.suffix(c) for c in NON_LATIN]
    assert names[1:3] == ["DokimiAnalysi", "PrimerDannye"]       # spelled in Latin letters
    assert all(re.fullmatch(r"[A-Za-z0-9]+", n) for n in names), names
    assert len(set(names)) == len(names)                          # two employers, two files
    assert doc_name.suffix(NON_LATIN[0]) == doc_name.suffix(NON_LATIN[0])   # and stable
    assert doc_name.suffix(NON_LATIN[0], "データ").startswith(names[0])


def test_the_profile_names_an_employer_no_table_can_spell(monkeypatch):
    monkeypatch.setitem(doc_name.KNOWN, "架空商事", "Kakushoji")
    assert doc_name.suffix("架空商事") == "Kakushoji"


def test_a_second_such_employer_never_overwrites_the_first(tmp_path):
    import stage_picks
    first = doc_name.suffix(NON_LATIN[0])
    rows = [{"company": NON_LATIN[0], "role": "データアナリスト", "status": "drafted",
             "cv_file": f"cv/{doc_name.docpaths.resume_stem(first)}.tex"}]
    second = stage_picks.choose_abbr(NON_LATIN[3], "データアナリスト", rows, str(tmp_path))
    assert second and second != first
    # One name for two employers is refused even for the same role, still unsent.
    with pytest.raises(FileExistsError):
        doc_name.check_free(first, NON_LATIN[3], "データアナリスト", rows)
    doc_name.check_free(first, NON_LATIN[0], "データアナリスト", rows)   # its own redraft


def test_such_an_application_has_a_folder(tmp_path, monkeypatch):
    import outreach
    abbr = doc_name.suffix(NON_LATIN[0])
    assert outreach.slug(NON_LATIN[0], "データアナリスト", abbr) == abbr.lower()
    assert outreach.slug(NON_LATIN[2], "Аналитик", "PrimerDannye") == \
        "primer_dannye_analitik_primerdannye"
    assert outreach.app_folder(NON_LATIN[0], "データアナリスト", abbr).endswith(abbr.lower())
    with pytest.raises(ValueError):
        outreach.slug(NON_LATIN[0], "データアナリスト")       # no name at all: still refused


def test_a_roles_accents_are_folded_and_an_old_token_is_kept():
    import stage_picks
    toks = stage_picks.role_tokens("Économiste principal - Prévision")
    assert toks[:3] == ["Prevision", "Economiste", "EconomistePrevision"]
    assert doc_name.suffix("Acme", "Économie") == "Acme_Economie"
    # A redraft finds the name its unsent draft was given under the old rule.
    old = "Acme_PrVision"
    assert "PrVision" in toks
    rows = [{"company": "Acme", "role": "Data Analyst", "status": "applied",
             "cv_file": f"cv/{doc_name.docpaths.resume_stem('Acme')}.tex"},
            {"company": "Acme", "role": "Économiste principal - Prévision", "status": "drafted",
             "cv_file": f"cv/{doc_name.docpaths.resume_stem(old)}.tex"}]
    assert stage_picks.choose_abbr("Acme", "Économiste principal - Prévision", rows,
                                   "/nonexistent") == old
