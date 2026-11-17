"""Jobs, Applied, Progress and Coming up read as one design (templates/app/DESIGN.md).

Three reviews of the first redesign (2026-11-17) said these screens still read as a reskin: two
"Did you apply" questions led Jobs and its cards ran 71, 66, 79 and 84 with nothing to say why; a
fit was drawn three ways; a phone's line of facts ran to four lines and broke "Posted 5 / days
ago"; the documents were grey capsules; Applied put a later interview above the nearest; Progress
led with "This week: 0 applied." over fourteen applications; and Coming up was seven cards with
icons floating mid-card. Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _eval(run, tmp_path, where, js, vp):
    step = {"hash": "jobs", "open": "jobsw:applied", "eval": js} if where == "applied" else {"hash": where, "eval": js}
    return _go(run, tmp_path, [step], vp, clock=T)["after"][0]["eval"]


# ------------------------------------------------------------------ one ring for a fit

RINGS = r"""(() => { const root = getComputedStyle(document.documentElement);
  const ring = (r) => ({name: r.getAttribute('aria-label'), role: r.getAttribute('role'), n: r.textContent.trim(),
    sc: getComputedStyle(r).getPropertyValue('--sc').trim(), w: Math.round(r.getBoundingClientRect().width)});
  return {cards: [...document.querySelectorAll('#main .card.job, #main .card.app')].filter((c) => c.getClientRects().length && c.querySelector('.job-top .fit-ring'))
      .map((c) => ring(c.querySelector('.job-top .fit-ring'))),
    pills: document.querySelectorAll('#main .score-pill, #main .bp-score').length,
    done: root.getPropertyValue('--st-done').trim(), running: root.getPropertyValue('--st-running').trim()}; })()"""
BRIEF_RINGS = r"""[...document.querySelectorAll('#main .bp-jobs .fit-ring')].filter((r) => r.getClientRects().length)
  .map((r) => ({sm: r.classList.contains('sm'), w: Math.round(r.getBoundingClientRect().width), name: r.getAttribute('aria-label')}))"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_fit_is_one_ring_green_when_strong_and_never_blue(run, tmp_path, vp):
    seen = _eval(run, tmp_path, "jobs", RINGS, vp)
    rings = seen["cards"]
    assert len(rings) >= 4 and seen["pills"] == 0, seen
    for r in rings:
        assert r["role"] == "img" and r["name"].startswith("Fit " + r["n"] + " out of 100"), r
        assert r["w"] == 36, r
        # Blue is for work in progress and focus only; green says strong.
        assert r["sc"] != seen["running"], r
        assert (r["sc"] == seen["done"]) == r["name"].endswith(", strong"), r
    brief = _eval(run, tmp_path, "brief", BRIEF_RINGS, vp)
    assert brief and all(r["sm"] and r["w"] == 28 and r["name"].startswith("Fit ") for r in brief), brief


# ------------------------------------------------------------------ Jobs: the list in its stages

LIST = r"""(() => { const m = document.querySelector('#main');
  const fold = m.querySelector('details.confirm-fold');
  const asks = [...m.querySelectorAll('.card')].filter((c) => /Did you apply to /.test(c.textContent));
  const first = m.querySelector('.job-groups');
  return {fold: fold ? fold.querySelector(':scope > summary').textContent.trim() : null,
    inFold: asks.filter((c) => c.closest('details.confirm-fold')).length,
    outside: asks.filter((c) => !c.closest('details.confirm-fold')).map((c) => c.textContent.slice(0, 60)),
    foldFirst: !!(fold && first && (fold.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING)),
    apply: fold ? fold.querySelectorAll('.applylink').length : -1,
    groups: [...m.querySelectorAll('.job-group')].map((g) => [g.querySelector('.list-head').textContent.trim(),
      [...g.querySelectorAll('.card .job-top .fit-ring')].map((r) => Number(r.textContent))]),
    text: m.innerText}; })()"""


def test_jobs_leads_with_what_to_apply_to_in_its_stages_best_fit_first(run, tmp_path):
    seen = _eval(run, tmp_path, "jobs", LIST, WIDE)
    # Every "Did you apply" question waits in one fold at the head of the list, and a draft
    # asking it offers no "Apply on their site" while it is open.
    assert seen["fold"] == "2 jobs to confirm: did you apply?", seen["fold"]
    assert seen["inFold"] == 2 and seen["outside"] == [] and seen["foldFirst"], seen
    assert seen["apply"] == 0, seen
    # The stages each under a small heading, best fit first within each.
    heads = [g[0] for g in seen["groups"]]
    assert heads == ["Ready to send", "Being written", "New"], heads
    for head, fits in seen["groups"]:
        assert fits == sorted(fits, reverse=True), (head, fits)
    # The folds under the list in the person's words.
    for said in ("1 closed: Show", "1 you hid: Show", "41 that did not fit: Show"):
        assert said in seen["text"], said
    assert "set aside: Show" not in seen["text"] and "left out by the search" not in seen["text"]


# ------------------------------------------------------------------ a phone's facts: two lines

LINES = r"""(() => { const lines = (el) => { const g = document.createRange(); g.selectNodeContents(el);
    const rows = []; for (const q of [...g.getClientRects()].filter((x) => x.width > 1 && x.height > 4)) {
      if (!rows.some((y) => Math.min(y.b, q.bottom) - Math.max(y.t, q.top) > 0.5 * Math.min(y.b - y.t, q.height))) rows.push({t: q.top, b: q.bottom}); }
    return rows.length; };
  return [...document.querySelectorAll('#main .card.job .facts, #main .card.app .facts')].filter((f) => f.getClientRects().length)
    .map((f) => ({id: f.closest('[data-item]').dataset.item, lines: lines(f), words: f.innerText})); })()"""


def test_a_phones_line_of_facts_is_two_lines_at_most_each_fact_whole(run, tmp_path):
    facts = _eval(run, tmp_path, "jobs", LINES, PHONE)
    assert len(facts) >= 4, facts
    assert [f for f in facts if f["lines"] > 2] == [], facts
    pricing = next(f for f in facts if f["id"] == "r12-1")
    # Where it is, then the pay and the closing day (its weekday left to a wider screen); when
    # it was posted is in its details.
    assert pricing["words"].split("\n")[0].startswith("Harbourline Bank"), pricing
    assert "£46,000 to £52,000" in pricing["words"] and "Closes 31 Oct" in pricing["words"] and "Posted" not in pricing["words"], pricing
    wide = _eval(run, tmp_path, "jobs", LINES, WIDE)
    assert all(f["lines"] == 1 for f in wide), wide


# ------------------------------------------------------------------ a draft's documents

DOCS = r"""(() => { const c = document.querySelector('[data-item="app-ellerwick-insight"]'); const w = c.querySelector('.doc-rows');
  return {well: w ? getComputedStyle(w).backgroundColor : null, sunk: (() => { const p = document.createElement('div'); p.style.background = 'var(--sunk)'; document.body.append(p);
    const v = getComputedStyle(p).backgroundColor; p.remove(); return v; })(), chips: c.querySelectorAll('.doc-part').length,
    rows: [...c.querySelectorAll('.doc-row')].map((r) => ({name: r.querySelector('.doc-name').textContent, meta: r.querySelector('.doc-meta').textContent,
      open: !!r.querySelector('.doc-acts [data-k^="doc-open:"]'), pen: (r.querySelector('.doc-acts .btn.icon-only') || {textContent: ''}).textContent.trim(),
      h: Math.round(r.getBoundingClientRect().height)}))}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_drafts_documents_are_rows_in_a_soft_well(run, tmp_path, vp):
    seen = _eval(run, tmp_path, "jobs", DOCS, vp)
    assert seen["chips"] == 0 and seen["well"] == seen["sunk"], seen
    assert [r["name"] for r in seen["rows"]] == ["CV", "Cover letter"], seen
    for r in seen["rows"]:
        assert r["meta"] == "1 page · checked" and r["open"] and r["h"] >= 44, r
    assert seen["rows"][0]["pen"].startswith("Edit the CV") and seen["rows"][1]["pen"].startswith("Edit the letter"), seen


# ------------------------------------------------------------------ Applied

APPLIED = r"""(() => [...document.querySelectorAll('#main .card.app-record')].map((c) => ({title: c.querySelector('h3').textContent,
  heard: (() => { const b = c.querySelector('[data-k^="heard:"]'); return b ? [b.classList.contains('quiet'), getComputedStyle(b).backgroundColor] : null; })()})))()"""


def test_applied_is_ordered_by_what_comes_next_and_i_heard_back_is_quiet(run, tmp_path):
    cards = _eval(run, tmp_path, "applied", APPLIED, WIDE)
    # The phone screen on Wed 28 Oct before the second interview on Wed 4 Nov, then the
    # follow-up due.
    assert [c["title"] for c in cards[:3]] == ["Senior Supply Chain Analyst", "Credit Risk Analyst", "Operations Analyst"], cards
    heard = [c["heard"] for c in cards if c["heard"]]
    assert len(heard) >= 4 and all(q and bg in ("rgba(0, 0, 0, 0)", "transparent") for q, bg in heard), heard


# ------------------------------------------------------------------ Progress

PROGRESS = r"""(() => { const t = document.querySelector('#main .apps .listv > .scroll-x, #main .apps .app-rows');
  const s = t ? getComputedStyle(t) : null;
  return {sum: document.querySelector('#main .sum').textContent, card: s ? [s.backgroundColor, parseFloat(s.borderTopLeftRadius)] : null}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_progress_leads_with_its_totals_and_its_applications_sit_in_a_card(run, tmp_path, vp):
    seen = _eval(run, tmp_path, "progress", PROGRESS, vp)
    # The sample's week has no applications: its totals lead, never "This week: 0 applied."
    assert seen["sum"] == "14 applied, 3 interviews so far.", seen
    assert seen["card"] and seen["card"][0] not in ("rgba(0, 0, 0, 0)", "transparent") and seen["card"][1] >= 12, seen


# ------------------------------------------------------------------ Coming up

COMING = r"""(() => { const days = [...document.querySelectorAll('#main [data-k="up-days"] > .up-day')];
  return {days: days.map((d) => ({head: d.querySelector('h3').textContent, lists: d.querySelectorAll(':scope > .up-list').length,
      rows: d.querySelectorAll('.up-row').length})),
    rows: [...document.querySelectorAll('#main .up-row')].map((r) => { const w = r.querySelector(':scope > .up-when'), t = r.querySelector('.up-title'), link = r.querySelector('.up-link');
      const wr = w.getBoundingClientRect();
      return {id: r.dataset.item, when: w.querySelector('.btn') ? null : [Math.round(wr.left), Math.round(wr.width)], size: parseFloat(getComputedStyle(t).fontSize), weight: getComputedStyle(t).fontWeight,
        menus: r.querySelectorAll('.up-menu').length, loose: [...r.querySelectorAll('.btn.icon-only')].filter((b) => !b.closest('.up-menu')).length,
        items: [...r.querySelectorAll('.up-menu .menu-item')].map((b) => b.textContent), chip: [...r.querySelectorAll('.up-sub .state-word')].map((s) => s.textContent),
        opens: link ? r.classList.contains('opens') && getComputedStyle(r).cursor === 'pointer' : null}; }),
    prep: [...document.querySelectorAll('#main [data-k^="up-prep:"], #main [data-k^="up-read:"]')].map((b) => b.dataset.k + '=' + b.textContent),
    lg: (() => { const p = document.createElement('span'); p.style.fontSize = 'var(--t-lg)'; document.querySelector('#main').append(p);
      const v = parseFloat(getComputedStyle(p).fontSize); p.remove(); return v; })()}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_coming_up_is_a_card_a_day_each_row_its_time_what_it_is_and_one_more(run, tmp_path, vp):
    seen = _eval(run, tmp_path, "interviews", COMING, vp)
    assert [d["head"] for d in seen["days"]][:2] == ["Wed 28 Oct", "Thu 29 Oct"], seen["days"]
    assert all(d["lists"] == 1 and d["rows"] >= 1 for d in seen["days"]), seen["days"]
    rows = {r["id"]: r for r in seen["rows"]}
    # The time a steady column, as wide on every row with a time.
    times = {tuple(r["when"]) for r in seen["rows"] if r["when"]}
    assert len(times) == 1 and next(iter(times))[1] == (64 if vp is WIDE else 56), times
    # A title in a card title's size (To do's), semibold; one More, no bare icons beside it.
    for r in seen["rows"]:
        assert r["size"] == seen["lg"] and r["weight"] == "600", (r, seen["lg"])
        assert r["menus"] <= 1 and r["loose"] == 0, r
    screen = rows["up-app-larkspur-supply-phone-screen-2026-10-28"]
    assert screen["opens"] and screen["chip"] == ["Prep ready"], screen
    assert screen["items"][:2] == ["Add to your calendar", "Change the day"], screen
    assert rows["up-ev20261020120000"]["items"] == ["Add to your calendar", "Take it off"], rows["up-ev20261020120000"]
    assert rows["up-app-copperleaf-payments-recruiter-call-2026-10-30"]["chip"] == ["No prep yet"]
    # Only the next interview with no prep carries "Prepare me"; reading a prep is the row's own tap.
    assert seen["prep"] == ["up-prep:up-app-copperleaf-payments-recruiter-call-2026-10-30=Prepare me"], seen["prep"]


def test_a_coming_up_row_opens_what_it_is_from_anywhere_on_it(run, tmp_path):
    # A tap on the row's second line, not its title, opens the interview's prep; one on its
    # More opens the menu and nothing else.
    row = '#main [data-item="up-app-larkspur-supply-phone-screen-2026-10-28"]'
    got = _go(run, tmp_path, [
        {"hash": "interviews", "eval": "(() => { document.querySelector('" + row + " .up-note').click(); return true; })()"},
        {"ready": "!!document.querySelector('dialog.detail[open]')"},
    ], PHONE, clock=T)
    assert "Larkspur Retail" in got["after"][1]["dialog"], got["after"][1]["dialog"][:300]
    got = _go(run, tmp_path, [{"hash": "interviews", "open": "up-more:up-app-larkspur-supply-phone-screen-2026-10-28",
                               "eval": "!!document.querySelector('dialog.detail[open]')"}], PHONE, clock=T)
    assert got["after"][0]["eval"] is False
