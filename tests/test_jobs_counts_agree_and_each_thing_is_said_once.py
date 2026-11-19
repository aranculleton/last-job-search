"""Jobs counts the same things everywhere, says each thing once, and every way to Applied opens it.

The screen review of 2026-11-18: an address to Applied opened whichever Jobs tab was used
last; "5 to apply for: 2 ready to send, 1 being written, 1 new. 2 to confirm." added up to 4,
and the Brief said "1 to confirm" beside Jobs' 2; a job being written with "1 question for
you" on its card sat under "Being written"; "Your CV" was a link in the header and a card
under the list on one screen; a CV made for a person was the one card on Ready to send with
no trash; and the tour still named "Found / Drafts / Applied" and said "resume" to a page that
says CV. Every person and employer is the sample's, invented
(tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
TAB = "(() => { const b = document.querySelector('#main [data-k=\"jobsw:applied\"]'); return b ? b.getAttribute('aria-pressed') : null; })()"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("addr", ["applied", "applications"])
def test_every_address_to_applied_opens_the_applied_tab(run, tmp_path, addr):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": TAB},
        {"hash": addr, "eval": TAB, "read": "#main .summary"},
        # Back on To apply, then the address again, and a fresh load of it.
        {"open": "jobsw:found", "eval": TAB},
        {"hash": addr, "eval": TAB},
        {"open": "jobsw:found", "eval": "location.hash = '" + addr + "'; 1"},
        {"reload": True, "eval": TAB},
    ], WIDE, clock=T)
    seen = [a["eval"] for a in got["after"]]
    assert seen[0] == "false" and seen[1] == "true" and seen[2] == "false" and seen[3] == "true", seen
    assert seen[5] == "true", seen
    assert "to apply for" not in got["after"][1]["text"], got["after"][1]["text"]


COUNTS = """(() => {
  const n = (el) => el ? Number((el.textContent.match(/(\\d+)/) || [0, 0])[1]) : 0;
  return {line: ((document.querySelector('#main .summary') || {}).textContent || '').trim(),
    tab: n(document.querySelector('#main [data-k="jobsw:found"] .seg-n')),
    side: n(document.querySelector('#side a[href="#jobs"] .navcount')),
    fold: document.querySelectorAll('#main details.confirm-fold .card').length,
    heads: [...document.querySelectorAll('#main .job-group > .list-head')].map((x) => x.textContent.trim()),
    asking: [...document.querySelectorAll('#main .job-group')].filter((g) => /^Needs your answer/.test(g.textContent)).map((g) => [...g.querySelectorAll('.card[data-item]')].map((c) => c.getAttribute('data-item')))[0] || []};
})()"""
BRIEF = "(document.querySelector('#main [data-k=\"bp-drafts\"]') || {}).textContent || ''"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_counts_agree(run, tmp_path, vp):
    """The total is its parts added up, on the tab, the side menu and the line; the questions
    about whether one was applied to are one count, the fold's, said the same on the Brief in
    plain words."""
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": COUNTS}, {"hash": "brief", "eval": BRIEF}], vp, clock=T)
    seen, brief = got["after"][0]["eval"], got["after"][1]["eval"]
    m = re.match(r"(\d+) to apply for: (.*?)\. (\d+) to confirm\.", seen["line"])
    assert m, seen
    total, confirm = int(m.group(1)), int(m.group(3))
    parts = [int(x) for x in re.findall(r"(\d+) (?:needs? your answer|ready to send|being written|new)", m.group(2))]
    assert sum(parts) == total, seen
    assert seen["tab"] == total, seen
    if vp is WIDE:
        assert seen["side"] == total, seen
    assert confirm == seen["fold"] == 2, seen
    # The Brief says the same number, in words a person reads without the screen beside them.
    assert "%d to say if you applied" % confirm in brief and "to confirm" not in brief, brief
    # The job being written that has a question for you waits on you, under that heading.
    assert seen["heads"][0] == "Needs your answer" and "r12-2" in seen["asking"], seen


CV = """(() => ({links: [...document.querySelectorAll('#main [data-k="jobs-resume"], #main [data-k="jobs-resume-line"]')].filter((e) => e.getClientRects().length).length,
  cards: document.querySelectorAll('#main [data-item="resume-current"], #main [data-item="resume-general"]').length}))()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_your_cv_is_said_once_on_each_jobs_tab_and_opens_its_card(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": CV},
        {"open": "jobsw:applied", "eval": CV},
        {"open": "jobsw:found", "eval": "(() => { const l = [...document.querySelectorAll('#main [data-k=\"jobs-resume\"], #main [data-k=\"jobs-resume-line\"]')].find((e) => e.getClientRects().length); l.click(); return 1; })()"},
        {"read": '#main [data-item="resume-current"], #main [data-item="resume-general"]', "eval": "location.hash"},
    ], vp, clock=T)
    found, applied = got["after"][0]["eval"], got["after"][1]["eval"]
    assert found == {"links": 1, "cards": 0}, found
    assert applied == {"links": 1, "cards": 0}, applied
    # The one link opens the card, on Your profile.
    assert got["after"][3]["eval"].startswith("#profile"), got["after"][3]["eval"]
    assert "Your CV" in got["after"][3]["text"], got["after"][3]["text"]


def test_a_cv_made_for_someone_has_its_trash_in_its_own_words(run, tmp_path):
    card = '#main [data-item="app-copperleaf-payments"]'
    got = _go(run, tmp_path, [
        {"hash": "jobs", "count": card + ' [data-k="dbin:app-copperleaf-payments"]', "attr": [card + ' [data-k="dbin:app-copperleaf-payments"]', "aria-label"]},
        {"open": "dbin:app-copperleaf-payments", "read": "dialog[open]"},
        {"click": "Tamsin no longer needs it", "within": "dialog[open]"},
    ], WIDE, clock=T)
    assert got["after"][0]["count"] == 1 and got["after"][0]["attr"] == "Not sending: your CV for Tamsin", got["after"][0]
    sheet = got["after"][1]["dialog"]
    assert "Not sending this to Tamsin?" in sheet and "Your CV for Tamsin" in sheet and "kept either way" in sheet, sheet
    # Nothing about pay, place or the employer, which teach the job search and mean nothing here.
    for gone in ("Pay", "Place", "Not my field", "Employer"):
        assert gone not in sheet, (gone, sheet)
    acts = [a for a in got["actions"] if a["action"] == "ready.not_applying"]
    assert len(acts) == 1 and acts[0]["item"] == "app-copperleaf-payments" and acts[0]["value"] == {"why": "not this role"}, acts


def test_the_tours_jobs_step_names_the_tabs_there_are_in_the_persons_word(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "jobs", "open": "help:jobs", "read": "dialog[open]"}], WIDE, clock=T)
    words = got["after"][0]["dialog"]
    assert "To apply" in words and "Applied" in words and "your CV" in words, words
    for gone in ("Found", "Drafts", "resume"):
        assert gone not in words, (gone, words)


def test_the_engines_tour_names_the_tabs_there_are():
    import tips
    jobs = next(t for t in tips.PAGE_TOUR if t["tab"] == "jobs")["text"]
    assert "To apply" in jobs and "Applied" in jobs, jobs
    for gone in ("Found:", "Drafts:", "resume"):
        assert gone not in jobs, (gone, jobs)
