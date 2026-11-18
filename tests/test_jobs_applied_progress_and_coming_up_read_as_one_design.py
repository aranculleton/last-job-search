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
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
PERSON_ZONE = _sample()["person"]["time_zone"]


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _eval(run, tmp_path, where, js, vp, zone=None):
    step = {"hash": "jobs", "open": "jobsw:applied", "eval": js} if where == "applied" else {"hash": where, "eval": js}
    return _go(run, tmp_path, [step], vp, clock=T, zone=zone)["after"][0]["eval"]


# ------------------------------------------------------------------ one ring for a fit

RINGS = r"""(() => { const root = getComputedStyle(document.documentElement);
  const word = (r) => { const w = r.parentElement.matches('.fit-with-word') ? r.parentElement.querySelector('.fit-word') : null; return w && w.getClientRects().length ? w.textContent.trim() : null; };
  const ring = (r) => ({name: r.getAttribute('aria-label'), role: r.getAttribute('role'), n: r.textContent.trim(), word: word(r),
    sc: getComputedStyle(r).getPropertyValue('--sc').trim(), w: Math.round(r.getBoundingClientRect().width)});
  return {cards: [...document.querySelectorAll('#main .card.job, #main .card.app')].filter((c) => c.getClientRects().length && c.querySelector('.job-top .fit-ring'))
      .map((c) => ring(c.querySelector('.job-top .fit-ring'))),
    pills: document.querySelectorAll('#main .score-pill, #main .bp-score').length,
    done: root.getPropertyValue('--st-done').trim(), running: root.getPropertyValue('--st-running').trim()}; })()"""
BRIEF_RINGS = r"""[...document.querySelectorAll('#main .bp-jobs .fit-ring')].filter((r) => r.getClientRects().length)
  .map((r) => ({sm: r.classList.contains('sm'), w: Math.round(r.getBoundingClientRect().width), name: r.getAttribute('aria-label'),
    word: r.parentElement.matches('.fit-with-word') ? r.parentElement.querySelector('.fit-word').textContent.trim() : null}))"""


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
        # "fit" beside every ring: on Jobs, where jobs are ranked, nothing said what "71" was (the
        # UX review of the redesign's second round, 2026-11-17).
        assert r["word"] == "fit", r
    brief = _eval(run, tmp_path, "brief", BRIEF_RINGS, vp)
    assert brief and all(r["sm"] and r["w"] == 28 and r["name"].startswith("Fit ") and r["word"] == "fit" for r in brief), brief


# ------------------------------------------------------------------ Jobs: the list in its stages

LIST = r"""(() => { const m = document.querySelector('#main');
  const fold = m.querySelector('details.confirm-fold');
  const asks = [...m.querySelectorAll('.card')].filter((c) => /Did you apply to /.test(c.textContent));
  const first = m.querySelector('.job-groups');
  return {fold: fold ? fold.querySelector(':scope > summary').textContent.trim() : null,
    inFold: asks.filter((c) => c.closest('details.confirm-fold')).length,
    outside: asks.filter((c) => !c.closest('details.confirm-fold')).map((c) => c.textContent.slice(0, 60)),
    foldAfter: !!(fold && first && (first.compareDocumentPosition(fold) & Node.DOCUMENT_POSITION_FOLLOWING)),
    apply: fold ? fold.querySelectorAll('.applylink').length : -1,
    asked: fold ? [...fold.querySelectorAll(':scope .card')].map((c) => ({one: c.matches('.card.job.confirm-card'), bin: !!c.querySelector('.job-top [data-bin]'),
      answers: [...c.querySelectorAll('.question .opts .btn')].map((b) => b.textContent.trim()), more: !!c.querySelector('details.more')})) : [],
    groups: [...m.querySelectorAll('.job-group')].map((g) => [g.querySelector('.list-head').textContent.trim(),
      [...g.querySelectorAll('.card .job-top .fit-ring')].map((r) => Number(r.textContent))]),
    text: m.innerText}; })()"""


def test_jobs_leads_with_what_to_apply_to_in_its_stages_best_fit_first(run, tmp_path):
    seen = _eval(run, tmp_path, "jobs", LIST, WIDE)
    # Every "Did you apply" question waits in one fold straight under the list, never ahead of
    # it, and a draft asking it offers no "Apply on their site" while it is open.
    assert seen["fold"] == "2 jobs to confirm: did you apply?", seen["fold"]
    assert seen["inFold"] == 2 and seen["outside"] == [] and seen["foldAfter"], seen
    assert seen["apply"] == 0, seen
    # Each one the same card, whatever asks it, with the same answers and the trash, and nothing
    # about the phone and the laptop (the UX review of the redesign's second round, 2026-11-17).
    assert all(c["one"] and c["bin"] and not c["more"] and c["answers"] == ["Yes, I applied", "Not yet"] for c in seen["asked"]), seen["asked"]
    assert "said different things" not in seen["text"], seen["text"]
    assert len(seen["asked"]) == 2, seen["asked"]
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
      open: (r.querySelector('.doc-acts [data-k^="doc-dl:"].icon-only') || {getAttribute: () => ''}).getAttribute('aria-label'), pen: (r.querySelector('.doc-acts .btn.icon-only') || {textContent: ''}).textContent.trim(),
      h: Math.round(r.getBoundingClientRect().height)}))}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_drafts_documents_are_rows_in_a_soft_well(run, tmp_path, vp):
    seen = _eval(run, tmp_path, "jobs", DOCS, vp)
    assert seen["chips"] == 0 and seen["well"] == seen["sunk"], seen
    assert [r["name"] for r in seen["rows"]] == ["CV", "Cover letter"], seen
    for r in seen["rows"]:
        assert r["meta"] == "1 page · checked" and r["h"] >= 44, r
        # Each saved from its own download icon, named for the document and its file (2026-11-18).
        assert r["open"].startswith("Download " + ("CV" if r["name"] == "CV" else "cover letter") + ": "), r
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


HEARD = r"""(() => [...document.querySelectorAll('#main .card.app-record')].map((c) => {
  const b = c.querySelector('.card-actions > [data-k^="heard:"]'); if (!b || !b.getClientRects().length) return null;
  const row = b.parentElement.getBoundingClientRect(), q = b.getBoundingClientRect();
  const g = document.createRange(); g.selectNodeContents(b); const words = g.getClientRects()[0];
  const t = document.createRange(); t.selectNodeContents(c.querySelector('h3')); const title = t.getClientRects()[0];
  const prev = b.previousElementSibling;
  const after = prev && prev.matches('.cost') && Math.abs((prev.getBoundingClientRect().top + prev.getBoundingClientRect().bottom) / 2 - (q.top + q.bottom) / 2) < 8 ? Math.round(q.left - prev.getBoundingClientRect().right) : null;
  return {title: c.querySelector('h3').textContent.trim(), leads: Math.abs(q.left - row.left) < 20 && words.left - title.left < 20, off: Math.round(words.left - title.left), after};
}).filter(Boolean))()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_i_heard_back_leading_a_line_starts_under_the_title_and_keeps_apart_from_a_gauge(run, tmp_path, vp):
    # "I heard back" leading a row stood 17px in from the card's words, and after a gauge read as
    # its words ("6 min of Claude  I heard back") (the redesign's second round, 2026-11-17).
    rows = _eval(run, tmp_path, "applied", HEARD, vp)
    assert rows, "Applied has I heard back"
    assert [r for r in rows if r["leads"]], rows
    assert all(abs(r["off"]) <= 1 for r in rows if r["leads"]), rows
    assert all(r["after"] >= 16 for r in rows if r["after"] is not None), rows


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


CELLS = r"""(() => { const left = (e) => { const g = document.createRange(); g.selectNodeContents(e); const r = g.getClientRects()[0]; return r ? Math.round(r.left) : null; };
  const s = document.querySelector('#main .weeks-svg'), c = document.querySelector('#main details.chart');
  const heads = [...document.querySelectorAll('#main .apps thead th')], rows = [...document.querySelectorAll('#main .apps tbody tr')].filter((r) => r.getClientRects().length);
  return {chart: [s.getBoundingClientRect().width, s.getBoundingClientRect().height, c.clientWidth - parseFloat(getComputedStyle(c).paddingLeft) - parseFloat(getComputedStyle(c).paddingRight)],
    cols: heads.map((h, i) => [left(h)].concat(rows.slice(0, 4).map((r) => r.children[i] && left(r.children[i])))),
    line: rows.length ? Math.round(rows[0].children[0].getBoundingClientRect().left) : null}; })()"""


def test_progress_on_a_computer_lines_up_its_columns_and_its_chart_fills_its_card(run, tmp_path):
    # Header words at 279, the rows' at 283 and the hairlines at 267; the weekly chart 550px wide
    # in a 1165px card (the redesign's second round, 2026-11-17).
    seen = _eval(run, tmp_path, "progress", CELLS, WIDE)
    w, h, room = seen["chart"]
    assert w >= room - 2 and h <= 220.5, seen["chart"]
    assert seen["cols"] and all(len({x for x in col if x is not None}) == 1 for col in seen["cols"]), seen["cols"]
    assert seen["cols"][0][0] == seen["line"], (seen["cols"][0], seen["line"])


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
      const v = parseFloat(getComputedStyle(p).fontSize); p.remove(); return v; })(),
    rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
    here: document.querySelectorAll('#main .up-row .up-here').length}; })()"""


# On a device in the person's own zone each time is said once, in a steady 64px column (56 on a
# phone). On a device in another zone each time says both ("13:00 London time (Thu 3:00 here)")
# and the column is wider on every row alike, 10rem (8rem on a phone, as wide as the time here
# with its day, issue 334), so the rows still line up (DESIGN.md, "A time from another zone").
# The device's zone is set both ways: taken from the machine, the far zones of Everywhere drew
# the design's own wider column, 90 and 150px, against the home zone's 56 and 64, and the test
# failed there with nothing wrong (2026-11-17).
@pytest.mark.parametrize("zone", [PERSON_ZONE, "Pacific/Kiritimati"], ids=["home", "far"])
@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_coming_up_is_a_card_a_day_each_row_its_time_what_it_is_and_one_more(run, tmp_path, vp, zone):
    seen = _eval(run, tmp_path, "interviews", COMING, vp, zone=zone)
    assert [d["head"] for d in seen["days"]][:2] == ["Wed 28 Oct", "Thu 29 Oct"], seen["days"]
    assert all(d["lists"] == 1 and d["rows"] >= 1 for d in seen["days"]), seen["days"]
    rows = {r["id"]: r for r in seen["rows"]}
    # The time a steady column, as wide on every row with a time.
    times = {tuple(r["when"]) for r in seen["rows"] if r["when"]}
    home = zone == PERSON_ZONE
    assert (seen["here"] == 0) == home, (zone, seen["here"])
    want = (64 if vp is WIDE else 56) if home else round((10 if vp is WIDE else 8) * seen["rem"])
    assert len(times) == 1 and next(iter(times))[1] == want, (times, want)
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


BRIEF_PREP = r"""[...document.querySelectorAll('#main .bp-up-row .up-prep')].filter((p) => p.getClientRects().length)
  .map((p) => { const b = p.querySelector('.btn'); return b ? [b.textContent.trim(), b.classList.contains('link'), getComputedStyle(b).textDecorationLine] : [p.textContent.trim()]; })"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_briefs_coming_up_says_its_prep_in_soft_pills_as_coming_up_does(run, tmp_path, vp):
    rows = _eval(run, tmp_path, "brief", BRIEF_PREP, vp)
    assert rows and all(len(r) == 1 or (not r[1] and r[2] == "none") for r in rows), rows
    said = [r[0] for r in rows]
    # One pill, on the next interview's row; the others' prep in the quiet words.
    assert said[0] == "Read your prep" and sum(1 for r in rows if len(r) > 1) == 1, rows
    assert "Prepare me" not in said[1:] and all(r[0] in ("Prep ready", "No prep yet", "Prep is for an earlier plan") for r in rows[1:]), rows
