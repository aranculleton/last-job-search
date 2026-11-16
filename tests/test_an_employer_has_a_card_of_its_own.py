"""An employer's name opens its own card, as a person's does (issue #263).

A person's name opened their card with what the page knows of them; an employer's name opened
nothing. Now it opens one card with the employer's roles (applications with where they stand,
then jobs found there), its people and its interviews, each opening its own card, and the
employer however its name is written (the sample's "Larkspur Retail Ltd" is Larkspur Retail). Every
employer, person and role is the sample's own, invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _model():
    return journeys._sample()


CARD = r"""(() => {
  const d = document.querySelector('dialog.detail[open]');
  if (!d) return null;
  const parts = {};
  for (const s of d.querySelectorAll('.d-employer section.d-block')) {
    parts[s.querySelector('h3').textContent.trim()] = [...s.querySelectorAll('li')].map((li) => li.textContent.replace(/\s+/g, ' ').trim());
  }
  const r = d.getBoundingClientRect();
  return {title: d.querySelector('.detail-title').textContent.trim(), parts,
    said: (d.querySelector('.d-employer > p') || {textContent: ''}).textContent.trim(),
    fits: r.width <= window.innerWidth + 1, address: location.hash};
})()"""
TAP = "(() => { const b = document.querySelector('[data-k=\"%s\"]'); if (b) b.click(); return !!b; })()"


def _names(rows):
    return [x.split(" · ")[0] for x in rows]


def test_an_employer_on_a_job_card_opens_its_card_with_its_roles_and_people(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "ready": "!!document.querySelector('[data-k=\"emp:job:r12-2\"]')",
         "eval": TAP % "emp:job:r12-2"},
        {"ready": "!!document.querySelector('dialog.detail[open] .d-employer')", "eval": CARD},
    ], vp, model=_model())
    assert got["after"][0]["eval"] is True, "the employer on the job card is a link"
    card = got["after"][1]["eval"]
    assert card and card["title"] == "Larkspur Retail", card
    # Its applications first, each with where it stands and when, then the job found there.
    assert _names(card["parts"]["Roles"]) == ["Senior Supply Chain Analyst", "Stock Analyst",
                                              "Supply Chain Data Analyst"], card
    assert "applied Fri 2 Oct" in card["parts"]["Roles"][0], card
    # The same employer however it is written: Kit is at "Larkspur Retail Ltd".
    assert _names(card["parts"]["People"]) == ["Juno", "Kit"], card
    assert len(card["parts"]["Interviews"]) == 1, card
    assert card["said"] == "3 roles · 2 people · 1 interview", card
    assert card["fits"] and card["address"].endswith("/emp~larkspur-retail/open"), card


def test_an_employers_card_opens_from_its_address_and_each_row_opens_its_own_card(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/emp~copperleaf-pay/open",
         "ready": "!!document.querySelector('dialog.detail[open] .d-employer')", "eval": CARD},
        {"eval": TAP % "emp-iv:int-copperleaf-payments"},
        {"ready": "!document.querySelector('dialog.detail[open] .d-employer')",
         "eval": "(document.querySelector('dialog.detail[open] .detail-title') || {textContent: ''}).textContent.trim()"},
    ], WIDE, model=_model())
    card = got["after"][0]["eval"]
    assert card and card["title"] == "Copperleaf Pay", card
    assert list(card["parts"]) == ["Roles", "People", "Interviews"], card
    assert _names(card["parts"]["People"]) == ["Tamsin", "Ash"], card
    # A row opens its own card: the interview's.
    assert "Copperleaf Pay" in got["after"][2]["eval"], got["after"][2]
