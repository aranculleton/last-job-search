"""Each control sits by its words, and each line reads whole (templates/app/DESIGN.md).

A review of the page's screenshots (2026-11-18), checked against the code: on a 1970px screen a
draft's download icon stood about 1,000px from "1 page · checked" and a work line's Stop Claude
about 1,200px from its words; on a phone a past job's line ("4 poi...") was cut short, "End of
day" broke over two lines in Coming up's time column, a To do row's name was cut with room to
spare beside its arrow and bin, and "I heard back" wrapped under a pill and its gauge stood 20px
in from the card's words; at 1970 Your profile put Education beside "Still to fill in", read
before Experience; the side menu gave Contacts no count; and Settings said "Open in the Claude
app" as a value. Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import LISTEN, _w  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
HUGE = {"width": 1970, "height": 1100}
MEASURE = 720


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _eval(run, tmp_path, where, js, vp, **kw):
    step = {"hash": "jobs", "open": "jobsw:applied", "eval": js} if where == "applied" else {"hash": where, "eval": js}
    return _go(run, tmp_path, [step], vp, clock=T, **kw)["after"][0]["eval"]


# ------------------------------------------------------------------ 1: a control near its words

DOC_ROWS = r"""(() => [...document.querySelectorAll('#main [data-item="app-ellerwick-insight"] .doc-row')].filter((r) => r.getClientRects().length).map((r) => {
  const words = r.querySelector('.doc-words').getBoundingClientRect(), meta = r.querySelector('.doc-meta').getBoundingClientRect();
  const acts = [...r.querySelectorAll('.doc-acts > .btn')].filter((b) => b.getClientRects().length).map((b) => b.getBoundingClientRect());
  return {name: r.querySelector('.doc-name').textContent, from: Math.round(words.left), meta: Math.round(meta.right),
    first: Math.round(Math.min(...acts.map((b) => b.left))), last: Math.round(Math.max(...acts.map((b) => b.right)))};
}))()"""
WORK_LINE = r"""(() => { const l = document.querySelector('#main [data-item="r12-1"] [data-work-inline]'); if (!l) return null;
  const t = l.querySelector('.wi-text'), g = document.createRange(); g.selectNodeContents(t); const words = [...g.getClientRects()].filter((q) => q.width > 0.5);
  const stop = [...l.querySelectorAll('.btn')].find((b) => /Stop Claude/.test(b.textContent)); if (!stop) return null;
  return {from: Math.round(t.getBoundingClientRect().left), end: Math.round(Math.max(...words.map((q) => q.right))),
    stop: Math.round(stop.getBoundingClientRect().left), stopEnd: Math.round(stop.getBoundingClientRect().right)}; })()"""


@pytest.mark.parametrize("vp", [WIDE, HUGE], ids=["1440", "1970"])
def test_a_documents_open_and_pencil_stay_near_its_words_on_a_wide_card(run, tmp_path, vp):
    rows = _eval(run, tmp_path, "drafts", DOC_ROWS, vp)
    assert [r["name"] for r in rows] == ["CV", "Cover letter"], rows
    for r in rows:
        # Within a reading measure of where its words start, never across the card.
        assert r["first"] > r["meta"] and r["last"] - r["from"] <= MEASURE, r


@pytest.mark.parametrize("vp", [WIDE, HUGE], ids=["1440", "1970"])
def test_a_work_lines_stop_claude_stays_near_its_words_on_a_wide_card(run, tmp_path, vp):
    seed = dict(LISTEN, **{"work/draft~r12-1": _w(kind="draft", title="Draft: Harbourline Bank, Pricing Analyst", status="queued", args={"job": "r12-1"})})
    line = _eval(run, tmp_path, "jobs", WORK_LINE, vp, seed=seed)
    assert line, "the card says Claude's work on it, with Stop Claude"
    assert line["stop"] >= line["end"] and line["stopEnd"] - line["from"] <= MEASURE, line


# ------------------------------------------------------------------ 2 and 3: Your profile

JOB_SUBS = r"""[...document.querySelectorAll('#main .prof-job-sub')].filter((e) => e.getClientRects().length).map((e) => ({text: e.textContent,
  whole: e.scrollWidth <= e.clientWidth + 1, right: Math.round(e.getBoundingClientRect().right), row: Math.round(e.closest('.prof-job').getBoundingClientRect().right)}))"""


def test_a_past_jobs_line_under_its_title_is_never_cut_short_on_a_phone(run, tmp_path):
    subs = _eval(run, tmp_path, "profile", JOB_SUBS, PHONE)
    assert len(subs) >= 2 and any("Claude can use" in s["text"] or "nothing yet" in s["text"] for s in subs), subs
    assert all(s["whole"] and s["right"] <= s["row"] for s in subs), subs


PARTS = r"""[...document.querySelectorAll('#main .prof-grid > *')].filter((e) => e.getClientRects().length).map((e) => {
  const b = e.getBoundingClientRect(), h = e.querySelector('h3');
  return {name: h ? h.textContent.trim() : '', top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left)}; })"""


@pytest.mark.parametrize("vp", [WIDE, HUGE], ids=["1440", "1970"])
def test_your_profile_reads_what_to_fill_in_then_experience_then_the_rest(run, tmp_path, vp):
    parts = _eval(run, tmp_path, "profile", PARTS, vp)
    by = {p["name"]: p for p in parts}
    miss, exp = by["Still to fill in"], by["Experience"]
    # Side by side at the top: what to fill in, then Experience beside it.
    assert abs(miss["top"] - exp["top"]) <= 1 and exp["left"] > miss["left"], parts
    # Nothing else stands beside what to fill in: the rest is under it.
    for p in parts:
        if p["name"] not in ("Still to fill in", "Experience"):
            assert p["top"] >= miss["bottom"], (p, miss)
    order = [p["name"] for p in sorted(parts, key=lambda p: (p["top"], p["left"]))]
    assert order[:2] == ["Still to fill in", "Experience"], order


# ------------------------------------------------------------------ 4: the side menu's counts

COUNTS = r"""(() => { const n = (k) => { const e = document.querySelector('[data-k="side:' + k + '"] .navcount'); return e ? [e.firstChild.textContent, (e.querySelector('.sr-only') || {}).textContent] : null; };
  return {contacts: n('contacts'), jobs: n('jobs'), sum: document.querySelector('#main .sum').textContent}; })()"""


def test_contacts_in_the_side_menu_says_its_messages_to_send(run, tmp_path):
    seen = _eval(run, tmp_path, "contacts", COUNTS, WIDE)
    assert seen["jobs"] and seen["jobs"][1] == " to apply", seen
    # The number Contacts' own summary says, worded as the others are.
    assert seen["contacts"] and seen["contacts"][1] == " to send", seen
    assert seen["sum"].startswith(seen["contacts"][0] + " message"), seen


# ------------------------------------------------------------------ 5: a value, never an instruction

READING = r"""[...document.querySelectorAll('#main .set-sum')].filter((s) => /LinkedIn profiles|Reading their profiles/.test(s.querySelector('.set-name').textContent))
  .map((s) => (s.querySelector('.set-value') || {textContent: ''}).textContent.trim())"""


def test_reading_linkedin_profiles_says_where_it_works_as_a_value(run, tmp_path):
    values = _eval(run, tmp_path, "settings", READING, WIDE)
    assert values, "Settings > LinkedIn has its reading row"
    assert all("Open in the Claude app" not in v for v in values), values
    assert any("Only in the Claude app" in v for v in values), values


# ------------------------------------------------------------------ 6: a phone's short words whole

WORDS = r"""[...document.querySelectorAll('#main .up-when.is-word')].filter((e) => e.getClientRects().length && /^(End of day|All day)$/.test(e.textContent.trim())).map((e) => {
  const g = document.createRange(); g.selectNodeContents(e); const lines = new Set([...g.getClientRects()].filter((q) => q.width > 0.5).map((q) => Math.round(q.top)));
  const title = e.parentElement.querySelector('.up-main').getBoundingClientRect(), words = [...g.getClientRects()].filter((q) => q.width > 0.5);
  return {text: e.textContent.trim(), lines: lines.size, end: Math.round(Math.max(...words.map((q) => q.right))), title: Math.round(title.left)}; })"""


def test_end_of_day_is_one_line_in_coming_ups_time_column_on_a_phone(run, tmp_path):
    words = _eval(run, tmp_path, "interviews", WORDS, PHONE)
    assert any(w["text"] == "End of day" for w in words), words
    assert all(w["lines"] == 1 and w["end"] <= w["title"] for w in words), words


NAMES = r"""[...document.querySelectorAll('#main .g-row')].filter((r) => r.getClientRects().length).map((r) => {
  const n = r.querySelector('.g-name').getBoundingClientRect(), acts = [...r.querySelectorAll('.g-acts > *')].filter((e) => e.getClientRects().length).map((e) => e.getBoundingClientRect());
  const bin = r.querySelector('.g-acts > [data-bin]');
  return {name: r.querySelector('.g-name').textContent, room: Math.round(acts.length ? Math.min(...acts.map((b) => b.left)) - n.right : 0),
    bin: bin ? Math.round(bin.getBoundingClientRect().width) : null, target: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--target')) || 44}; })"""


def test_a_to_do_rows_name_has_the_room_its_arrow_and_trash_leave_on_a_phone(run, tmp_path):
    rows = _eval(run, tmp_path, "todo", NAMES, PHONE)
    noor = [r for r in rows if r["name"].startswith("Noor at")]
    assert noor, rows
    for r in rows:
        # The name runs to 8px from the row's button, and the trash is a finger's width, no wider.
        assert r["room"] <= 8, r
        assert r["bin"] is None or r["bin"] <= r["target"], r


# ------------------------------------------------------------------ 7: I heard back, wrapped

WRAPPED = r"""(() => [...document.querySelectorAll('#main .card.app-record')].map((c) => {
  const b = c.querySelector('.card-actions > [data-k^="heard:"]'); if (!b || !b.getClientRects().length) return null;
  const q = b.getBoundingClientRect(), mid = (r) => (r.top + r.bottom) / 2;
  const before = [...b.parentElement.children].slice(0, [...b.parentElement.children].indexOf(b)).filter((e) => e.getClientRects().length);
  const alone = !before.some((e) => Math.abs(mid(e.getBoundingClientRect()) - mid(q)) < 8);
  const g = document.createRange(); g.selectNodeContents(b); const words = g.getClientRects()[0];
  const t = document.createRange(); t.selectNodeContents(c.querySelector('h3')); const title = t.getClientRects()[0];
  return {title: c.querySelector('h3').textContent.trim(), alone, after: before.length ? before[before.length - 1].className : '', off: Math.round(words.left - title.left)};
}).filter(Boolean))()"""


def test_i_heard_back_wrapped_onto_its_own_line_starts_under_the_title_after_a_gauge_too(run, tmp_path):
    rows = _eval(run, tmp_path, "applied", WRAPPED, PHONE)
    wrapped = [r for r in rows if r["alone"]]
    # Wrapped under a lone pill and under a pill with its gauge: both start flush.
    assert any("cost" in r["after"] for r in wrapped), rows
    assert all(abs(r["off"]) <= 1 for r in wrapped), wrapped
