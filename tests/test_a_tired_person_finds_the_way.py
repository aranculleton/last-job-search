"""A tired person finds the way on the page (2026-11-02).

Nine places a walk through the page stopped someone who is tired and not technical: Draft
this held up by a question nothing had answered, a To do card hidden by mistake with only a
toast to undo it, an interview's calendar hidden behind a small icon, the job bin saying
nothing of what its reason changes, a phone toast whose Close fell onto a line of its own,
a draft that "needs a fix" with the fix folded out of sight, a break that only Settings
could take, the Chat footer half under the tab bar, and To do opening on small questions
while a thank-you was two days late. Each test taps the page as a person would. Every
person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _one  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


T = "2026-10-25T09:00:00Z"


# ------------------------------------------------------------------ 1. Draft this goes ahead


def test_draft_this_drafts_in_one_tap_with_no_chosen_and_the_postings_question_left_open(run, tmp_path, vp):
    # One tap drafts, with no sheet first (2026-11-03, the session's "one tap drafts"), and its
    # toast carries an Undo that calls the draft off before Claude starts, as "Don't do it" does.
    toast = "(() => [...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | '))()"
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Draft this: Harbourline Bank, Pricing Analyst", "read": "dialog",
         "ready": "[...document.querySelectorAll('[data-toast]')].some((t) => t.textContent.includes('Drafting Harbourline Bank'))", "eval": toast},
        {"click": "Undo", "exact": True, "within": "#toasts", "eval": toast},
    ], vp, clock=T)
    assert got["after"][0]["dialog"] == "", "no sheet: the person pressed Draft this"
    assert "Undo" in got["after"][0]["eval"], got["after"][0]["eval"]
    w = [x for x in got["work"] if x and x.get("kind") == "draft"]
    assert w, "the draft is asked for, the posting's own question left unanswered"
    assert w[-1]["args"]["already_applied"] == "no" and w[-1]["args"]["job"] == "r12-1"
    assert w[-1]["args"]["answers"] == [], "a question left open is not sent as an answer"
    assert w[-1]["status"] == "stopped" and w[-1]["stop_asked"], ("Undo calls the draft off", w[-1])
    assert "Not drafting Harbourline Bank" in got["after"][1]["eval"], got["after"][1]["eval"]
    assert not got["actions"], "nothing is marked as applied"


def test_a_field_to_answer_is_listed_from_its_bullet_with_no_bar_down_its_side(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        # "Add something" asks what first, an interview or anything else (2026-11-03).
        {"hash": "interviews", "open": "up-add"},
        {"open": "sheet-choice:other"},
        {"submit": True, "eval": "(() => { const a = document.querySelector('dialog .errors ul a'); const f = document.querySelector('dialog .field.has-error');"
         " const s = getComputedStyle(a), fs = getComputedStyle(f); return {align: s.textAlign, side: fs.borderLeftWidth, pad: fs.paddingLeft, words: a.textContent}; })()"},
    ], vp, clock=T)
    r = got["after"][2]["eval"]
    assert r["words"] == "What it is"
    assert r["align"] in ("left", "start"), ("each line reads from its bullet, never centred away from it", r)
    assert r["side"] == "0px" and r["pad"] == "0px", ("nothing has a line down its side", r)


# ------------------------------------------------------------------ 2. a card hidden by mistake comes back


def test_a_card_hidden_by_mistake_comes_back_from_the_end_of_to_do(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        # Its card is one tap into Help Claude do more (DESIGN.md, Places).
        {"hash": "todo", "open": "help-start"},
        {"open": "hide:you-finish", "count": '[data-k="hide:you-finish"]'},
        {"click": "Show 1 hidden this week", "read": ".todo-hidden-list"},
        {"click": "Bring back: Finish your profile", "count": '[data-k="hide:you-finish"]'},
    ], vp, clock=T)
    _, first, shown, back = got["after"]
    assert first["count"] == 0, "hidden"
    assert "1 hidden this week: Show" in first["text"], "said at the end of To do, as Jobs says what was set aside"
    assert "Finish your profile" in shown["text"] and "Bring back" in shown["text"]
    assert back["count"] == 1, "back on To do"
    assert "hidden this week" not in back["text"]


# ------------------------------------------------------------------ 3. an interview into the calendar, in words


def test_an_interview_goes_into_the_calendar_from_its_to_do_card_and_its_prep(run, tmp_path, vp):
    card = '[data-item="soon:int-larkspur-supply"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": card},
        {"click": "Add to calendar", "within": card, "read": "dialog.cal-sheet"},
        {"eval": "document.querySelector('[data-k=cal-close]').click(); 'closed'"},
        {"click": "Read your prep", "within": card, "read": "dialog.detail"},
        {"click": "Add to calendar", "within": "dialog.detail", "read": "dialog.cal-sheet"},
    ], vp, clock=T)
    assert "Add to calendar" in got["after"][0]["text"], "a button with words on the To do card"
    for i in (1, 4):
        sheet = got["after"][i]["text"]
        assert "Add to your calendar" in sheet and "Phone screen: Larkspur Retail" in sheet and "Google Calendar" in sheet, sheet
    assert "Add to calendar" in got["after"][3]["text"], "and on the interview's prep"


# ------------------------------------------------------------------ 4. the bin says what its reason changes; Avoid has a Change


@pytest.mark.parametrize("reason,said", [("Not my field", "Set aside. Fewer jobs outside your field from now on."),
                                         ("The pay", "Set aside. Fewer jobs paying like this from now on."),
                                         ("The place", "Set aside. Fewer jobs in places like this from now on.")])
def test_the_job_bin_says_what_its_reason_changes(run, tmp_path, reason, said):
    # Each reason is its own button and acts at once (2026-11-03: a reason, then "Take it off my
    # list", was two taps for one thing).
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Not for me: Harbourline Bank, Pricing Analyst"},
        {"click": reason, "exact": True, "within": "dialog", "read": ".toasts"},
    ], PHONE, clock=T)
    assert said in got["after"][1]["text"], got["after"][1]["text"]
    assert _one(got, "job.dismiss")["value"]["why"] in ("field", "pay", "place")


def test_what_to_avoid_is_changed_in_the_search_panel_which_has_one_name(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:search-avoid", "read": '[data-k="info-sum:search-avoid"]'},
        {"open": "search-change:avoid", "read": ".tweak-panel"},
    ], vp, clock=T)
    panel = got["after"][1]["text"]
    assert panel.startswith("Change the search"), "the panel has the name of the button that opens it from Jobs"
    assert "Edit the search" not in panel and "What should change?" in panel


# ------------------------------------------------------------------ 5. a phone toast keeps Close on its row


def test_a_phone_toast_keeps_close_on_its_words_row(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Not for me: Harbourline Bank, Pricing Analyst"},
        {"click": "Not this one", "within": "dialog", "eval": "(() => { const t = document.querySelector('.toast'); const x = t.querySelector('[data-k^=\"toast-x\"]').getBoundingClientRect();"
         " const w = t.querySelector('.toast-text').getBoundingClientRect(); return {h: Math.round(t.getBoundingClientRect().height), row: x.top < w.bottom && x.bottom > w.top}; })()"},
    ], PHONE, clock=T)
    r = got["after"][1]["eval"]
    assert r["row"], ("Close sits on the words' row, never a line of its own", r)
    assert r["h"] <= 60, r


# ------------------------------------------------------------------ 6. a draft that needs a fix shows it


def test_a_draft_that_needs_a_fix_says_so_on_its_card_with_its_state_by_the_title(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "drafts", "read": '#main [data-item="app-quayside-demand"]',
         "eval": "(() => { const c = document.querySelector('#main [data-item=\"app-quayside-demand\"]'); const al = c.querySelector('[data-alert=\"al-checks-app-quayside-demand\"]');"
                 " const h3 = c.querySelector('.job-top h3').getBoundingClientRect(); const pill = c.querySelector('.job-top .state-word').getBoundingClientRect();"
                 " return {folded: !al || !!al.closest('details'), onRow: pill.top < h3.bottom, atStart: Math.abs(pill.left - h3.left) <= 2,"
                 " gap: Math.round(pill.top - h3.bottom)}; })()"},
    ], vp, clock=T)
    card = got["after"][0]["text"]
    r = got["after"][0]["eval"]
    assert not r["folded"], "the failed check is on the card, not folded into More"
    # What Claude can do by itself is never a button (2026-11-05): the failed check is said on
    # the card, and Claude makes it again once its question is answered.
    assert "the CV runs to a second page by two lines" in card and "Make it again" not in card, card
    assert "Two answers about Quayside Foods" in card, "its question stays first"
    assert r["onRow"] or (r["atStart"] and r["gap"] <= 8), ("the state stays by the title, never pushed off to the right below it", r)


# ------------------------------------------------------------------ 7. a break from the Brief's bell


def test_the_bells_sheet_takes_a_break_through_the_same_sheet_settings_opens(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "brief", "open": "brief-bell", "read": "dialog[open]"},
        {"click": "Take a break until…", "within": "dialog[open]", "read": "dialog[open]"},
        {"click": "One week", "role": "radio", "exact": True},
        {"submit": True},
    ], vp, clock=T)
    assert "Take a break until…" in got["after"][0]["text"]
    sheet = got["after"][1]["text"]
    assert sheet.startswith("Take a break") and "One week" in sheet and "Two weeks" in sheet, sheet
    pause = _one(got, "brief.pause")
    assert pause["item"] == "schedule" and pause["value"] == {"until": "2026-11-01"} and pause["rev_seen"] == "sc1"
    same = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:brief-pause"},
        {"click": "Take a break until…", "within": "#main", "read": "dialog[open]"},
    ], vp, clock=T)
    assert same["after"][1]["text"] == sheet, "one sheet, from Settings and from the bell alike"


# ------------------------------------------------------------------ 8. the Chat footer on a phone


FOOT = ("(() => { const f = document.querySelector('#foot .foot-line').getBoundingClientRect(); const t = document.querySelector('.tabs').getBoundingClientRect();"
        " return {top: Math.round(f.top), bottom: Math.round(f.bottom), tabs: Math.round(t.top)}; })()")


def test_the_chat_footer_never_sits_half_under_the_tab_bar(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "chat", "eval": "scrollTo(0, 0); " + FOOT},
        {"eval": "scrollTo(0, document.documentElement.scrollHeight); " + FOOT},
    ], PHONE, clock=T)
    top, end = got["after"][0]["eval"], got["after"][1]["eval"]
    assert top["top"] >= top["tabs"], ("on the first screen the footer is below the tab bar, never peeking out of it", top)
    assert end["bottom"] <= end["tabs"], ("scrolled down, it is read above the tab bar", end)


# ------------------------------------------------------------------ 9. what is late comes first


FIRST = ("(() => { document.querySelectorAll('details.band-more').forEach((d) => { d.open = false; });"
         " const open = (c) => !c.closest('details:not([open])');"
         " const cards = [...document.querySelectorAll('#main .band [data-card]')].filter(open).map((c) => ({title: (c.querySelector('.card-title') || {}).textContent,"
         " band: (c.closest('.band').querySelector('h3') || {}).textContent || ''}));"
         " const you = document.querySelector('#main [data-item=\"you\"]');"
         " return {cards, youFolded: !you || !open(you), fold: (document.querySelector('#main .band-more-sum') || {}).textContent}; })()")


def test_to_do_opens_on_what_is_late_or_due_today_and_folds_the_setup(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": FIRST}], vp, clock=T)
    r = got["after"][0]["eval"]
    titles = [c["title"] for c in r["cards"]]
    # The Fernhill Freight follow-up and the reply to Juno are drafted, so they are rows of the
    # one card of messages to send, which opens Contacts at them (the UX review, 2026-11-05).
    for owed in ("Thank-you note after your Harbourline Bank first interview", "Messages to send (7)", "Send your CV to Tamsin"):
        assert owed in titles, (owed, titles)
    bands = [c["band"] for c in r["cards"]]
    assert bands[0] == "Due or late", bands
    if "Needs your answer" in bands:
        last_owed = max(titles.index(t) for t in titles if t.startswith(("Thank-you", "Follow up with", "Reply to", "Send your", "Messages to send")))
        assert bands.index("Needs your answer") > last_owed, ("questions come after what is owed", r["cards"])
    assert r["youFolded"], "Finish your profile waits behind the fold while today's things show"
    # Four cards today all show (one card an act and a person, 2026-11-05): the first fold is
    # Help Claude do more's "and N more", its card right after today's things (2026-11-10), or what is not due yet;
    # more than five, and it is "Show N more".
    assert r["fold"].startswith(("Show ", "and ", "Not due yet")), r


# Found along the way, 2026-11-02. "Did your note to Wren go?" is answered once the note is
# marked sent (on her card in Contacts, its old Messages address kept), never asked again: one
# question fewer on the quick answers card (2026-11-05).
UNFOLD = "(() => { [...document.querySelectorAll('#main button')].filter((b) => /^Show \\d+ more/.test(b.textContent.trim())).forEach((b) => b.click()); return 1; })()"
ASKED = "(document.querySelector('#main [data-item=\"quick\"] .card-title') || {}).textContent || ''"


def test_a_note_marked_sent_is_no_longer_asked_about(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": UNFOLD}, {"eval": ASKED},
                              {"hash": "messages", "eval": "(() => { document.querySelector('[data-k=\"sent:msg-wren-2\"]').click(); return 1; })()"},
                              {"hash": "todo", "eval": UNFOLD}, {"eval": ASKED}], vp, clock=T)
    assert got["after"][1]["eval"] == "4 quick answers" and got["after"][4]["eval"] == "3 quick answers", [a["eval"] for a in got["after"]]


def test_a_message_ranks_first_in_its_group_and_a_text_box_asks_to_be_filled_in():
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    # A message ranks 0: with || it became 9 and fell behind a hold at the same employer.
    assert "KIND_RANK[a.kind] || 9" not in js and "KIND_RANK[a.kind] ?? 9" in js
    # An empty box to type in says to fill it in, not "Choose one.".
    assert '"Choose one." : "Fill this in."' in js
