"""Contacts, the four name cards and Your profile read as one family (the redesign's second
round, 2026-11-17).

What the reviews found, each pinned here on the sample (every person, employer and job in it is
invented):

- one person was several colours (Marisol blue on the Brief, clay in Contacts, every Contacts
  initial the same clay) and the cards drew no initial at all;
- a person's card offered four equal pills ("Call booked", "The referral is over", "They sent me
  a job", "Don't contact again") that read as status tags, and its Next said "Asked for your CV"
  without saying who;
- one task, a CV Tamsin asked for, was said four ways on four screens;
- the interview card was 960 wide round a lone "No prep yet." that its Next already said;
- on a draft, Copy was filled on the first card and outlined on the rest, 1000px from I sent it
  on a laptop, and nothing said what to do once copied;
- a past job in Your profile ran to six lines beside "Change" and a trash.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
TAMSIN = "copperleaf_pay_tamsin"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _fill(sel):
    return ("((e) => e ? [...e.classList].find((c) => /^av-[1-6]$/.test(c)) || 'none' : null)(document.querySelector(%r))" % sel)


# ------------------------------------------------------------------ one person, one colour

def test_a_person_is_one_colour_in_contacts_on_their_card_and_on_their_employers(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": "[...document.querySelectorAll('#main li.person > .avatar')].map((a) => [a.closest('[data-item]').dataset.item, [...a.classList].find((c) => /^av-/.test(c))])"},
        {"hash": "contacts/" + TAMSIN + "/open", "ready": "!!document.querySelector('dialog.detail[open] .d-person')", "eval": _fill("dialog.detail[open] .detail-head > .avatar")},
        {"hash": "jobs/emp~copperleaf-pay/open", "ready": "!!document.querySelector('dialog.detail[open] .d-employer')",
         "eval": "[...document.querySelectorAll('dialog.detail[open] .d-row[data-k^=\"emp-person:\"]')].map((r) => [r.dataset.k.split(':')[1], ((a) => a ? [...a.classList].find((c) => /^av-/.test(c)) : null)(r.querySelector('.avatar'))])"},
    ], WIDE, clock=T)
    rows = dict(got["after"][0]["eval"])
    assert len(rows) >= 5 and all(rows.values()), rows
    # Six soft fills by id: not every initial the same one.
    assert len(set(rows.values())) >= 3, rows
    assert got["after"][1]["eval"] == rows[TAMSIN], (got["after"][1]["eval"], rows[TAMSIN])
    people = dict(got["after"][2]["eval"])
    assert people and people[TAMSIN] == rows[TAMSIN] and all(people.values()), people


# ------------------------------------------------------------------ a person's card

MENU = r"""(() => {
  const d = document.querySelector('dialog.detail[open] .d-person');
  const m = d && d.querySelector('details.upd-menu');
  if (!m) return null;
  const items = [...m.querySelectorAll('.menu-panel > button')];
  const red = getComputedStyle(document.documentElement).getPropertyValue('--st-failed').trim();
  const probe = document.createElement('span'); probe.style.color = red; document.body.appendChild(probe);
  const want = getComputedStyle(probe).color; probe.remove();
  return {open: m.open, label: m.querySelector('summary').textContent.trim(), chevron: !!m.querySelector('summary svg, summary .ic'),
    items: items.map((b) => b.textContent.trim()), heights: items.map((b) => Math.round(b.getBoundingClientRect().height)),
    lastRed: items.length ? getComputedStyle(items[items.length - 1]).color === want : false,
    face: [...d.querySelectorAll(':scope > .card-actions > .btn')].map((b) => b.textContent.trim())};
})()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_persons_rarer_updates_are_one_menu_with_the_way_to_stop_last_in_red(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts/" + TAMSIN + "/open", "ready": "!!document.querySelector('dialog.detail[open] .d-person')", "eval": MENU},
        {"open": "menu:dupd:" + TAMSIN, "eval": MENU},
        # Escape closes the menu and never the card under it.
        {"eval": "(() => { const m = document.querySelector('details.upd-menu'); m.querySelector('summary').focus(); "
                 "m.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true})); "
                 "return [m.open, !!document.querySelector('dialog.detail[open]')]; })()"},
    ], vp, clock=T)
    shut, opened = got["after"][0]["eval"], got["after"][1]["eval"]
    assert shut and not shut["open"] and shut["label"].startswith("Update") and shut["chevron"], shut
    # None of the four on the card's face as pills of their own.
    assert not {"The referral is over", "They sent me a job", "Don't contact again", "Call booked"} & set(shut["face"]), shut
    assert opened["open"] and opened["items"][-1] == "Don't contact again" and opened["lastRed"], opened
    assert "The referral is over" in opened["items"] and "They sent me a job" in opened["items"], opened
    assert min(opened["heights"]) >= 44, opened
    assert got["after"][2]["eval"] == [False, True], got["after"][2]["eval"]


# ------------------------------------------------------------------ one task, one wording

TASK_CARD = r"""(() => {
  const d = document.querySelector('dialog.detail[open] .d-next-block');
  return d ? {what: d.querySelector('.d-next-what').textContent.trim(), buttons: [...d.querySelectorAll('.card-actions > .btn')].map((b) => b.textContent.trim())} : null;
})()"""
TASK_ROW = r"""(() => {
  const c = document.querySelector('#main [data-item="copperleaf_pay_tamsin"]');
  return c ? {line: (c.querySelector('.meta') || {textContent: ''}).textContent.trim(), buttons: [...c.querySelectorAll('.card-actions > .btn')].map((b) => b.textContent.trim())} : null;
})()"""
TASK_JOB = r"""(() => {
  const c = document.querySelector('#main [data-item="app-copperleaf-payments"]');
  return c ? {line: [...c.querySelectorAll('p.meta')].map((p) => p.textContent.trim()).find((t) => /Tamsin/.test(t)) || '',
    buttons: [...c.querySelectorAll('.card-actions > .btn, .card-actions > a')].map((b) => b.textContent.trim())} : null;
})()"""
TASK_TODO = r"""(() => {
  const c = document.querySelector('#main [data-item="due-tamsin-resume"]');
  return c ? {title: c.querySelector('.card-title').textContent.trim(), buttons: [...c.querySelectorAll('.card-actions > .btn')].map((b) => b.textContent.trim())} : null;
})()"""


def test_what_tamsin_asked_for_is_one_task_in_one_wording_on_every_screen(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": TASK_TODO},
        {"hash": "contacts", "eval": TASK_ROW},
        {"hash": "jobs", "eval": TASK_JOB},
        {"hash": "contacts/" + TAMSIN + "/open", "ready": "!!document.querySelector('dialog.detail[open] .d-person')", "eval": TASK_CARD},
        {"click": "I sent it: send Tamsin your CV", "within": "dialog[open]", "read": "dialog.sheet[open]"},
        {"submit": True},
    ], WIDE, clock=T)
    todo, row, job, card = (a["eval"] for a in got["after"][:4])
    assert job and job["line"] == "Send Tamsin your CV." and job["buttons"][:2] == ["Get the CV for Tamsin", "I sent it"], job
    assert todo and todo["title"] == "Send Tamsin your CV" and todo["buttons"][:2] == ["Get the CV for Tamsin", "I sent it"], todo
    assert row and row["line"].startswith("Send Tamsin your CV") and row["buttons"][:2] == ["Get the CV for Tamsin", "I sent it"], row
    assert card and card["what"].startswith("Send Tamsin your CV.") and card["buttons"] == ["Get the CV for Tamsin", "I sent it"], card
    # I sent it finishes the task, the same wherever it is pressed: the CV logged as sent to her
    # with its file (as Jobs always logged it), and her row about it done.
    assert "Sent to Tamsin" in got["after"][4]["text"], got["after"][4]["text"][:200]
    sent = [a for a in got["actions"] if a["action"] == "ready.sent_to_contact"]
    assert sent and sent[-1]["item"] == "app-copperleaf-payments" and sent[-1]["value"]["contact"] == TAMSIN, got["actions"]
    assert sent[-1]["value"]["attached"] == "Morgan_Ellis_CV_Copperleaf.pdf", sent[-1]
    done = [a for a in got["actions"] if a["action"] == "due.done"]
    assert done and done[-1]["item"] == "due-tamsin-resume", got["actions"]


# ------------------------------------------------------------------ the interview card

WIDTH = r"""(() => { const d = document.querySelector('dialog.detail[open]'); return d ? [Math.round(d.getBoundingClientRect().width), d.innerText] : null; })()"""


def test_an_interview_card_is_680_wide_without_a_prep_and_never_says_no_prep_twice(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-copperleaf-payments/open", "ready": "!!document.querySelector('dialog.detail[open]')", "eval": WIDTH},
        {"hash": "interviews/int-larkspur-supply/open", "ready": "!!document.querySelector('dialog.detail[open] .prep-main')", "eval": WIDTH},
    ], WIDE, clock=T)
    (w0, text0), (w1, _text1) = got["after"][0]["eval"], got["after"][1]["eval"]
    assert w0 == 680 and "No prep yet" not in text0 and "Get your prep" in text0, (w0, text0[:300])
    # With a prep to read beside its stages, it is wide.
    assert w1 > 680, w1


# ------------------------------------------------------------------ names in a card's facts

NAMES = r"""(() => [...document.querySelectorAll('dialog.detail[open] :is(.d-facts-line, .d-stack > .meta) :is(a.name-link, a.navlink)')].map((a) => {
  const s = getComputedStyle(a); return [a.textContent.trim(), s.textDecorationLine, s.fontWeight]; }))()"""


def test_a_name_in_a_cards_facts_is_a_name_never_an_underlined_link(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts/" + TAMSIN + "/open", "ready": "!!document.querySelector('dialog.detail[open] .d-person')", "eval": NAMES},
        {"hash": "interviews/int-copperleaf-payments/open", "ready": "!!document.querySelector('dialog.detail[open] .meta')", "eval": NAMES},
    ], WIDE, clock=T)
    names = got["after"][0]["eval"] + got["after"][1]["eval"]
    assert {n[0] for n in names} >= {"Copperleaf Pay", "Tamsin"}, names
    assert all(n[1] == "none" and n[2] == "600" for n in names), names


# ------------------------------------------------------------------ Contacts: send in two steps

ROW = r"""(() => {
  const c = document.querySelector('#main li.person.has-draft');
  const row = c.querySelector(':scope .card-actions');
  const b = [...row.querySelectorAll(':scope > .btn')];
  const top = (e) => Math.round(e.getBoundingClientRect().top);
  const copy = b.find((x) => /^Copy/.test(x.textContent.trim())), sent = b.find((x) => x.textContent.trim() === 'I sent it');
  return {who: c.dataset.item, face: b.map((x) => x.textContent.trim()), together: !!(copy && sent) && top(copy) === top(sent),
    apart: copy && sent ? Math.round(sent.getBoundingClientRect().left - copy.getBoundingClientRect().right) : null,
    sentFilled: !!(sent && sent.classList.contains('primary')),
    line: (c.querySelector('.copied-line') || {textContent: ''}).textContent.trim(),
    inBubble: !!c.querySelector('.sendbox .bubble-copy'),
    head: document.querySelector('#main .sec-head') ? document.querySelector('#main .sec-head').innerText : ''};
})()"""
CLAMPS = r"""(() => [...document.querySelectorAll('#main li.person.has-draft')].map((c) => {
  const t = c.querySelector('.sendtext-in'), more = c.querySelector('.read-all');
  if (!t) return null;
  const lh = parseFloat(getComputedStyle(t).lineHeight);
  return [c.dataset.item, Math.round(t.getBoundingClientRect().height / lh), more ? more.textContent.trim() : null];
}).filter(Boolean))()"""
COUNTS = "[...document.querySelectorAll('#main li.person .msg-facts .count')].map((c) => c.textContent.trim())"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_copy_and_i_sent_it_sit_together_and_once_copied_it_says_where_to_paste(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": ROW},
        {"hash": "contacts", "eval": CLAMPS},
        {"hash": "contacts", "eval": COUNTS},
        {"click": "Copy message to Juno", "eval": ROW},
    ], vp, clock=T)
    before, clamps, counts, after = (a["eval"] for a in got["after"])
    assert before["face"][:2] == ["Copy", "I sent it"] and before["together"] and before["apart"] <= 16, before
    assert not before["inBubble"] and not before["sentFilled"] and before["line"] == "", before
    assert after["who"] == before["who"] and after["sentFilled"] and after["line"] == "Copied. Paste it in LinkedIn.", after
    # One count in the header: the messages written to send.
    assert "7 messages to send" in before["head"] and "need you" not in before["head"], before["head"]
    # The first draft whole; every long one after it two lines, with Show all.
    assert clamps[0][2] is None or clamps[0][1] > 2, clamps
    folded = [c for c in clamps[1:] if c[2]]
    assert folded and all(c[1] <= 2 and c[2] == "Show all" for c in folded), clamps
    # A note far inside its limit shows no count.
    assert all("to spare" in c or "over" in c for c in counts), counts


# ------------------------------------------------------------------ Your profile

JOBS = r"""(() => [...document.querySelectorAll('#main [data-k^="you-job:"]')].map((r) => {
  const t = r.querySelector('.prof-job-t'), lh = parseFloat(getComputedStyle(t).lineHeight);
  return {lines: Math.round(t.getBoundingClientRect().height / lh), go: !!r.querySelector('.set-go'), bin: !!r.closest('li').querySelector('[data-bin]'),
    height: Math.round(r.getBoundingClientRect().height)};
}))()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_your_profile_is_grouped_rows_a_job_one_line_that_opens_its_sheet(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "profile", "eval": JOBS},
        {"hash": "profile", "eval": "[...document.querySelectorAll('#main .prof-sec > .prof-top > h3.group')].map((h) => h.textContent.trim())"},
        {"hash": "profile", "open": "you-job:you-job-Brindle---Hart-Logistics-Senior-Operations-Analyst", "read": "dialog"},
    ], vp, clock=T)
    jobs, parts = got["after"][0]["eval"], got["after"][1]["eval"]
    # A row opens its own sheet, where taking it off is the last thing.
    sheet = got["after"][2]["dialog"]
    assert "Change this job" in sheet and "Take this job off" in sheet, sheet[:400]
    assert len(jobs) >= 2 and all(j["lines"] == 1 and j["go"] and not j["bin"] and j["height"] <= 72 for j in jobs), jobs
    assert parts[:1] == ["Still to fill in"] or parts[0] == "Experience", parts
    assert {"Experience", "Skills", "Education", "Certificates"} <= set(parts), parts
