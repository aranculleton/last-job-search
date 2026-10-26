"""The checks that fail a batch must not fail a document written the right way.

Each case here is a correct document that `verify_batch.sh` used to reject, or
a file name the pipeline used to lose:

- `check_numbers.py` read "2024 Weekend" as "2024 week", which is no longer a
  year, so a date running into a capitalised word was an ungrounded claim.
  "12 monthly", "3 hourly" and "2023 Daytime" broke the same way.
- `audit_letters.py` required the opening to name the role, which is the
  "I am applying for the <role> role" opener 03-writing-style.md bans, and to
  carry the candidate's employer as the exact string in roles.py, when a
  letter says "at Brindle & Hart", not "at Brindle & Hart Logistics".
- Ireland's DAC, CLG, UC and Teoranta, and compound forms like "Pty Ltd" and
  "Co., Ltd.", stayed on the salutation, the file name and the company key.
- `fit_to_page.fit()` read the draft's abbr before build() replaced it, so a
  hand-written abbr ended in a compile looking for a file never written, and a
  draft with none was a bare KeyError.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from unittest import mock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit_letters as AU  # noqa: E402
import check_numbers as CN  # noqa: E402
import company_key  # noqa: E402
import doc_name  # noqa: E402
import fit_to_page as F  # noqa: E402
import outreach  # noqa: E402
import render_application as R  # noqa: E402


# ---- numbers ---------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Promoted in 2024 Weekend rota lead",
    "In 2023 Daytime cover",
    "cut 3 hourly",
])
def test_a_unit_word_must_end_where_the_word_ends(text):
    assert CN.claims(text) == set()


def test_a_monthly_count_is_a_count_not_a_duration():
    assert CN.claims("ran 12 monthly reviews") == {(12.0, "")}


@pytest.mark.parametrize("text,claim", [
    ("12 months", (12.0, "month")), ("14 days", (14.0, "day")), ("6 hrs", (6.0, "hour")),
    ("10 weeks.", (10.0, "week")), ("40%", (40.0, "%")), ("5k users", (5000.0, "")),
    ("3x faster", (3.0, "x")), ("2.5 million", (2.5e6, "")),
])
def test_real_units_still_read(text, claim):
    assert CN.claims(text) == {claim}


# ---- the letter audit --------------------------------------------------------

def _letter(company="Wrenfield Freight Ltd", role="Senior Supply Chain Analyst", p1=None):
    return {
        "company": company, "role": role,
        "p1": p1 or ("Chilled and ambient volumes behave differently, and a forecast that "
                     "treats them as one stream fills the wrong trailers. At Brindle & Hart "
                     "I forecast both, by depot, every week."),
        "p2": "Wrenfield moves goods across the North West for retailers.",
        "lead": "Where I would start:",
        "cl_bullets": [{"label": "Forecasting", "text": "Depot-level demand forecasts."}],
        "p4": "Thank you for reading.",
    }


def _audit(a, batch=()):
    with mock.patch.object(AU, "pdf_text", lambda abbr: "Dear Wrenfield Freight hiring team,\n"):
        return AU.audit(a, batch)[0]


def test_an_opening_written_to_the_guide_passes():
    assert _audit(_letter()) == []


def test_the_opener_the_guide_bans_is_what_fails():
    a = _letter(p1="I am applying for the Senior Supply Chain Analyst role at Wrenfield. "
                   "At Oakmere Foods I forecast fresh categories weekly.")
    flags = _audit(a)
    assert any("announces the application" in f for f in flags), flags


@pytest.mark.parametrize("opening", [
    "I am writing to express my interest in this position.",
    "I'm excited to apply for this role.",
    "Please accept my application for the analyst role.",
    "With great interest I read your posting.",
])
def test_every_shape_of_the_announcement_is_caught(opening):
    assert AU.ANNOUNCES.search(opening)


@pytest.mark.parametrize("opening", [
    "Forecasting on live stock data, where a wrong number means an empty shelf, is where "
    "I have done my most useful work.",
    "The posting puts demand forecasting and route planning in the same job, which is the "
    "pair I work on now.",
    "Three of the five things this role lists are what I did at Oakmere Foods.",
])
def test_the_guides_own_openings_are_not_announcements(opening):
    assert not AU.ANNOUNCES.search(opening)


@pytest.mark.parametrize("text", [
    "At Brindle & Hart I forecast depot volumes.",        # leading words of a long name
    "At Oakmere I forecast fresh categories.",            # the role's known_as
    "Oakmere Foods taught me promotions.",                # the name in roles.py
    "At Brindle-Hart Logistics I built the model.",       # any punctuation between words
])
def test_the_employer_is_recognised_as_people_write_it(text):
    assert R.EMPLOYER_NAMED.search(text)


@pytest.mark.parametrize("text", [
    "I forecast for a large grocer.",
    "a bank of models",
    "The salt marsh analytics are new.",                  # words split differently
])
def test_a_sentence_naming_no_employer_is_still_caught(text):
    assert not R.EMPLOYER_NAMED.search(text)


def test_a_one_word_name_must_be_written_as_a_name():
    assert R.EMPLOYER_NAMED.search("At Oakmere I forecast fresh categories.")
    assert not R.EMPLOYER_NAMED.search("the oakmere approach")
    with mock.patch.object(R, "ROLES", [{"employer": "Target Corporation"}]):
        named = re.compile(
            r"\b(?:%s)\b" % "|".join(R._form_pattern(f) for f in R._employer_forms(R.ROLES)),
            re.I)
    assert named.search("Six years at Target taught me replenishment.")
    assert not named.search("I target the slow movers first.")


def test_an_opening_with_no_credential_still_fails():
    a = _letter(p1="Chilled and ambient volumes behave differently. I forecast both weekly.")
    assert any("names none of the candidate's employers" in f for f in _audit(a))


def test_two_roles_at_one_employer_must_each_name_their_role():
    a = _letter(role="Senior Supply Chain Analyst")
    b = _letter(company="Wrenfield Freight", role="Transport Planner")
    flags = _audit(a, [a, b])
    assert any("never names its own" in f for f in flags), flags
    a["p2"] = "The supply chain analyst seat at Wrenfield covers the whole network."
    assert not any("never names its own" in f for f in _audit(a, [a, b]))


def test_one_role_at_an_employer_need_not_name_it():
    a = _letter()
    assert not any("never names its own" in f for f in _audit(a, [a]))


def test_a_legal_form_left_on_the_salutation_is_caught():
    a = _letter()
    with mock.patch.object(AU, "pdf_text", lambda abbr: "Dear Wrenfield Freight DAC hiring team,\n"):
        assert "legal suffix in salutation" in AU.audit(a)[0]


# ---- legal forms ------------------------------------------------------------

@pytest.mark.parametrize("company,short", [
    ("Rowan Distribution DAC", "Rowan Distribution"),
    ("Acme CLG", "Acme"), ("Acme UC", "Acme"), ("Acme Teoranta", "Acme"),
    ("Acme ULC", "Acme"), ("Acme Pty Ltd", "Acme"), ("Acme Co., Ltd.", "Acme"),
    ("Acme Pvt Ltd", "Acme"), ("Acme Private Limited", "Acme"), ("Acme Pte. Ltd.", "Acme"),
    ("The Northwind Group Limited", "Northwind"), ("Harbour Group", "Harbour Group"),
    ("Tamworth & Co.", "Tamworth & Co"), ("UC Davis", "UC Davis"),
])
def test_the_legal_form_comes_off_the_name_a_person_uses(company, short):
    assert R.short_name(company) == short


@pytest.mark.parametrize("a,b", [
    ("Acme DAC", "Acme"), ("Acme Teoranta", "Acme"), ("Acme Co., Ltd.", "Acme"),
    ("Acme Pvt Ltd", "Acme"), ("Tamworth & Co.", "Tamworth"), ("Acme S.p.A.", "Acme"),
])
def test_the_throttle_sees_one_employer(a, b):
    assert company_key.key(a) == company_key.key(b)


def test_a_leading_form_word_is_part_of_the_name():
    assert company_key.key("UC Davis") == "uc davis"


@pytest.mark.parametrize("company,name", [
    ("Rowan DAC", "Rowan"), ("Acme Teoranta", "Acme"), ("Acme Pvt Ltd", "Acme"),
    ("Acme CLG", "Acme"), ("Acme UC", "Acme"),
])
def test_the_file_name_drops_the_legal_form(company, name):
    assert doc_name.suffix(company) == name


# ---- the name a draft's files are written under ------------------------------

def test_a_draft_with_no_company_says_so():
    with pytest.raises(ValueError, match="no company"):
        R.final_abbr({"role": "Analyst"})


def test_the_final_compile_opens_the_file_build_wrote():
    """A hand-written abbr is replaced by build(); the fit must follow it."""
    compiled = []
    a = {"company": "Wrenfield Freight Ltd", "role": "Analyst", "abbr": "FF", "jobs": [],
         "posting": ""}
    with mock.patch.object(F, "_render_resume", lambda a: 1), \
            mock.patch.object(F, "grow_resume", lambda *x, **k: False), \
            mock.patch.object(F, "_render_letter", lambda a: 1), \
            mock.patch.object(F, "body_words", lambda a: 100), \
            mock.patch.object(F, "_lines", lambda pdf: 40), \
            mock.patch.object(F.R, "jobs_for", lambda a: []), \
            mock.patch.object(F, "compile_resume", lambda abbr, passes=1: compiled.append(abbr) or 1):
        F.fit(a)
    assert compiled == ["Wrenfield"] and a["abbr"] == "Wrenfield"


def test_a_draft_with_no_abbr_is_named_rather_than_a_keyerror():
    a = {"company": "Wrenfield Freight Ltd", "role": "Analyst", "jobs": [], "posting": ""}
    with mock.patch.object(F, "_render_resume", lambda a: 1), \
            mock.patch.object(F, "grow_resume", lambda *x, **k: False), \
            mock.patch.object(F, "_render_letter", lambda a: 1), \
            mock.patch.object(F, "body_words", lambda a: 100), \
            mock.patch.object(F, "_lines", lambda pdf: 40), \
            mock.patch.object(F.R, "jobs_for", lambda a: []), \
            mock.patch.object(F, "compile_resume", lambda abbr, passes=1: 1):
        F.fit(a)
    assert a["abbr"] == "Wrenfield"


def test_a_shortlist_row_with_no_abbr_is_named(tmp_path):
    drafts = tmp_path / "drafts.json"
    apps_in = tmp_path / "apps_in.json"
    drafts.write_text(json.dumps([_letter() | {"abbr": "Wrenfield", "summary": "", "tools": ""}]))
    apps_in.write_text(json.dumps([{"company": "Wrenfield Freight Ltd", "title": "Analyst"}]))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "outreach.py"),
                        str(drafts), str(apps_in)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode != 0
    assert "has no abbr" in p.stderr and "Traceback" not in p.stderr


def test_outreach_and_the_audit_agree_on_the_credential():
    assert outreach.CREDENTIAL is R.EMPLOYER_NAMED is AU._EMPLOYERS
