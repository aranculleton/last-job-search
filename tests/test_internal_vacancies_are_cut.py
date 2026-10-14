"""A vacancy open only to the employer's own staff cannot be won from outside.

A test round of the scheduled shortlist put "Data Analyst Support | S2 | Data &
AI Domain | Milton Keynes | Internal Mobility" eighth. Nothing screened for it,
and an application there is wasted however good the match.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import text_screen as T  # noqa: E402

BODY = (" The analyst builds weekly forecasts and works with the operations team on "
        "stock cover, supplier lead times and the reporting the directors read. ") * 4


@pytest.mark.parametrize("title,sentence", [
    ("Data Analyst Support | S2 | Data & AI Domain | Milton Keynes | Internal Mobility", ""),
    ("Analyst (internal applicants only)", ""),
    ("Analyst", "This role is open to current Acme employees only."),
    ("Analyst", "This vacancy is only open to existing staff."),
    ("Analyst", "Internal applicants only."),
    ("Analyst", "Restricted to internal candidates."),
])
def test_an_internal_only_vacancy_is_cut(title, sentence):
    out = T.screen({"title": title, "desc": sentence + BODY})
    assert out["text_screen"] == "cut"
    assert any("own staff only" in c for c in out["cuts"]), out["cuts"]


@pytest.mark.parametrize("title,sentence", [
    ("Internal Audit Manager", ""),
    ("Analyst", "We welcome internal and external applicants."),
    ("Analyst", "Internal candidates will be prioritised."),
    ("Analyst", "This role is open to current employees and external candidates."),
    ("Analyst", "This document is for internal use only."),
])
def test_a_vacancy_open_to_everyone_is_not(title, sentence):
    out = T.screen({"title": title, "desc": sentence + BODY})
    assert not any("own staff only" in c for c in out["cuts"]), out["cuts"]


def test_the_shortlist_message_is_written_for_a_phone():
    t = open(os.path.join(ROOT, "automation", "prompts", "job_round.md"), encoding="utf-8").read()
    assert "1. <Role>, <Employer> (<score>)" in t and "<apply link>" in t
    assert "score | company | role" not in t
