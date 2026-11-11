"""What an independent reviewer found walking the page (2026-11-05), each held so it stays put.

The reviewer used the page on the example search, a busy week and a large search, on a phone
and a laptop, in light and dark: a job tapped "Draft this" said "Drafting" with no Cancel and
then "Draft ready" over nothing; counts on one screen disagreed with another; controls that
wake Claude carried no gauge and one that does not carried one; a put-off row read as done.
Each test taps the page as the reviewer did and reads what it says. Every person and employer
is invented (tests/fixtures/app_model_example.json, tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

EXAMPLE = os.path.join(ROOT, "tests", "fixtures", "app_model_example.json")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _example():
    with open(EXAMPLE, encoding="utf-8") as fh:
        return json.load(fh)


def _row(m, rid):
    return next(r for r in m["jobs"]["rows"] if r["id"] == rid)


CARD = '#main [data-item="r9-1"]'
TAB = '#main [data-k="jobsw:found"]'


# ------------------------------------------------------------------ 1: a job being drafted


def test_a_job_being_drafted_says_where_its_draft_stands_with_cancel_and_stays_counted(run, tmp_path):
    """Draft this on a find: its card says where the draft stands in Claude's work words with
    Cancel (never a "Drafting" pill over work still waiting), "Finished: putting it on your
    page" until its draft is there (never "Draft ready" with a See the draft that opened
    nothing), and the job stays one of the jobs to apply to, in the tab and the summary."""
    m = _example()
    wid = _row(m, "r9-1")["draft_work"]["id"]
    running = {"kind": "draft", "title": "Draft: Brindle Hart Logistics", "status": "running", "claimed_by": "cloud-1",
               "claimed_at": "2026-10-25T08:59:00Z", "stage": 1, "stage_at": "2026-10-25T08:59:00Z", "lease_until": "2026-10-25T12:00:00Z",
               "stages": [{"name": "Reading the posting", "est_s": 60}, {"name": "Writing the CV and letter", "est_s": 300}],
               "args": _row(m, "r9-1")["draft_work"]["args"], "_v": 3}
    done = dict(running, status="done", finished_at="2026-10-25T18:01:00Z", _v=4)
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": TAB},
        {"click": "Draft this: Brindle Hart Logistics, Demand Planning Analyst", "read": CARD},
        {"read": TAB},
        {"read": "#main .summary"},
        {"write": {"work/" + wid: running}, "tick": 8000, "read": CARD},
        {"write": {"work/" + wid: done}, "read": CARD},
        {"read": TAB},
    ], PHONE, model=m)
    before = got["after"][0]["text"]
    queued, tab, summary, going, finished, tab2 = (got["after"][i]["text"] for i in range(1, 7))
    # "Stop Claude" wherever Claude's work is called off (the maintainer, 2026-11-05).
    assert "Stop Claude" in queued and "Drafting" not in queued, queued
    assert any(w.lower() in queued.lower() for w in ("Waiting for Claude", "Waiting its turn", "Next", "Sent", "Waking Claude")), queued
    assert tab == before and tab2 == before, (before, tab, tab2)
    # One sentence whose total is the tab's since the UX review of 2026-11-10 (U-9): it said
    # "3 to send, 2 still to make".
    # Being made only while its work goes, still to make where nothing makes it (the review of
    # 2026-11-11): the job just asked for is being made; the draft never made is still to make.
    # A job still to look at that asks a question is waiting on you, counted there once (2026-11-11).
    assert "to apply to: 1 ready, 1 waiting on you, 1 being made, 1 still to make" in summary, summary
    assert ("Claude is on it" in going or "Draft" in going) and "Stop Claude" in going, going
    assert "Finished: putting it on your page" in finished, finished
    assert "Draft ready" not in finished and "See the draft" not in finished, finished


# ------------------------------------------------------------------ 6: a question about a job


def test_a_question_about_a_job_is_asked_on_that_jobs_card_and_holds_draft_this(run, tmp_path):
    """"Did you apply to Dovecote Freight?" stood as a card of its own above that job's card,
    which still offered Draft this, and the summary said "1 needs your answer" while more
    showed: the question is in the job's grey box, Draft this waits for the answer, and the
    summary counts every open question."""
    m = _example()
    got = _go(run, tmp_path, [
        {"hash": "jobs", "count": '#main [data-item^="need:"], #main .orphan', "read": '#main [data-item="r9-3"]'},
        {"read": "#main .summary"},
    ], PHONE, model=m)
    card = got["after"][0]
    assert card["count"] == 0, "the question is never a card of its own above the job"
    assert "Did you apply to Dovecote Freight?" in card["text"], card["text"]
    assert "Draft this" not in card["text"], card["text"]
    # Counted with what waits on the person, once (2026-11-11): "One needs your answer." after
    # "1 waiting on you" said one thing twice. Moved with the rule.
    assert "waiting on you" in got["after"][1]["text"], got["after"][1]["text"]
    assert "needs your answer" not in got["after"][1]["text"], got["after"][1]["text"]


# ------------------------------------------------------------------ 7: the Brief and a draft not made


def test_the_brief_counts_drafts_ready_apart_from_those_being_made_and_apply_waits_for_files(run, tmp_path):
    """The Brief said "2 drafts ready to apply" beside Jobs' "2 to send, 1 still to make", and a
    draft whose files were never made offered "Apply on their site"."""
    m = _example()
    got = _go(run, tmp_path, [
        {"hash": "brief", "read": "#main .bp-send"},
        {"hash": "jobs", "read": '#main [data-item="app-fernhill_freight_operations_analyst"]'},
    ], WIDE, model=m)
    brief, card = got["after"][0]["text"], got["after"][1]["text"]
    # In Jobs' own words, from its one tally: a draft nothing is making is "still to make"
    # there, and the Brief called it "being made" (the screen review, 2026-11-11).
    assert "1 draft ready to apply, 1 still to make" in brief, brief
    assert "Apply on" not in card, card
    assert "Not made yet" in card or "Claude" in card, card


# ------------------------------------------------------------------ 2: no gauge on a control that only runs code


def _wren_follow_up(m):
    """The example with Wren's follow-up drafted and waiting to go."""
    msg = copy.deepcopy(m["messages"][0])
    text = "Hi Wren, just following up on my note last month. Would be great to hear how the team works."
    msg.update(id="msg-fernhill_freight_halloway", contact="fernhill_freight_halloway", first_name="Wren", employer="Fernhill Freight",
               channel="linkedin_message", kind="follow_up", type="follow_up", body=text, text=text, chars=len(text), why=None,
               wave=None, wave_label=None, rev="wrenfu1", related={"people": ["fernhill_freight_halloway"]})
    msg["count"] = dict(msg["count"], chars=len(text), label=f"{len(text)} of 300 characters")
    m["messages"].append(msg)
    m["to_send"] = {"n": 2, "ids": m["to_send"]["ids"] + [msg["id"]]}
    return m


def test_i_sent_it_carries_no_gauge(run, tmp_path):
    """"I sent it" on a drafted follow-up carried a follow-up's two minutes: what only the page
    does wakes nothing and shows no gauge."""
    m = _wren_follow_up(_example())
    card = '#main [data-item="fernhill_freight_halloway"]'
    got = _go(run, tmp_path, [
        {"hash": "contacts", "read": card, "count": card + " .card-actions .cost, " + card + " .card-actions [data-wakes]"},
    ], PHONE, model=m)
    assert "I sent it" in got["after"][0]["text"] or "Copy" in got["after"][0]["text"], got["after"][0]["text"]
    assert got["after"][0]["count"] == 0, "no gauge beside a control that only marks the message sent"


# ------------------------------------------------------------------ 3: a checklist row's Draft


def _two_follow_ups(m):
    """The example with a second follow-up owed, to an invented Ash at Copperleaf Pay, so the
    two are one checklist card."""
    wren = next(p for p in m["people"] if p["id"] == "fernhill_freight_halloway")
    nudge = next(d for d in m["due"] if d["kind"] == "nudge")
    ash = copy.deepcopy(wren)
    ash.update(id="copperleaf_pay_ash", first_name="Ash", employer="Copperleaf Pay", rev="ash1",
               owed=dict(wren["owed"], id="follow_up~copperleaf_pay_ash", args={"contact": "copperleaf_pay_ash"}, due="due-nudge-copperleaf_pay_ash"),
               related={"due": ["due-nudge-copperleaf_pay_ash"]})
    m["people"].append(ash)
    m["due"].append(dict(nudge, id="due-nudge-copperleaf_pay_ash", title="Follow up with Ash at Copperleaf Pay", company="Copperleaf Pay",
                         item="copperleaf_pay_ash", contact="copperleaf_pay_ash", rev="ashd1", related={"people": ["copperleaf_pay_ash"]},
                         work={"kind": "follow_up", "id": "follow_up~copperleaf_pay_ash", "args": {"contact": "copperleaf_pay_ash"}, "title": "Follow up with Ash at Copperleaf Pay"}))
    return m


def test_a_checklist_rows_draft_carries_the_gauge_and_then_its_work_line(run, tmp_path):
    """A row's Draft on "Follow up with 2 people" woke Claude with no gauge beside it, and then
    showed only "See it": the row's Draft carries the gauge, and once tapped the row says where
    its follow-up stands, with Cancel."""
    m = _two_follow_ups(_example())
    row = '#main [data-item="due-nudge-copperleaf_pay_ash"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": row, "count": row + " [data-wakes] + .cost"},
        {"click": "Draft: Follow up with Ash at Copperleaf Pay", "read": row},
    ], PHONE, model=m)
    assert "Draft" in got["after"][0]["text"], got["after"][0]["text"]
    assert got["after"][0]["count"] == 1, "the row's Draft carries the gauge"
    after = got["after"][1]["text"]
    assert "Stop Claude" in after and "See it" not in after, after   # Stop Claude (2026-11-05)


# ------------------------------------------------------------------ 4: many of one kind, one card


EMPLOYERS = ("Moss Freight", "Wren Mutual", "Teal Retail", "Sable Pay")


def _application_rows(m):
    """The example with four applications owed a follow-up and four interviews with no word
    since the last update, as a large search has them (invented employers)."""
    for i, co in enumerate(EMPLOYERS):
        slug = co.lower().replace(" ", "_")
        m["due"].append({"id": f"due-follow_up-{slug}", "kind": "follow_up", "title": f"Follow up on Analyst {i} at {co}", "context": "",
                         "due": "2026-10-01", "company": co, "overdue_days": 24, "action": "work:follow_up", "sub": "follow_up",
                         "item": f"app-{slug}", "work": {"kind": "follow_up", "id": f"follow_up~app-{slug}", "args": {"application": f"app-{slug}", "company": co}},
                         "done": {"action": "due.done", "label": "Done"}, "snooze": {"action": "due.snooze", "label": "Not today"}, "rev": f"af{i}"})
        m["due"].append({"id": f"due-interview-{slug}", "kind": "interview", "title": f"No word from {co} since your last update", "context": "",
                         "due": "2026-09-20", "company": co, "overdue_days": 35, "action": "work:follow_up", "sub": "status_note",
                         "item": f"int-{slug}", "work": {"kind": "follow_up", "id": f"follow_up~int-{slug}~status_note", "args": {"interview": f"int-{slug}", "kind": "status_note", "company": co}},
                         "done": {"action": "due.done", "label": "Done"}, "snooze": {"action": "due.snooze", "label": "Not today"}, "rev": f"sn{i}"})
    return m


def test_follow_ups_on_applications_and_no_word_since_an_update_are_one_card_each(run, tmp_path):
    """A large search showed about fifty "No word from <employer> since your last update" cards
    and sixteen "Follow up on <role>" cards, "67 things today": each kind is one checklist card,
    a row an employer with its Draft and its Done, counted once."""
    m = _application_rows(_example())
    got = _go(run, tmp_path, [
        {"hash": "todo", "count": '#main .card.todo[data-item^="due-follow_up-"], #main .card.todo[data-item^="due-interview-"]',
         "eval": "[...document.querySelectorAll('#main .group-card .card-title')].map((e) => e.textContent.trim())"},
        {"read": "#main .summary"},
    ], PHONE, model=m)
    titles = got["after"][0]["eval"]
    assert "Follow up on 4 applications" in titles, titles
    assert "No word since your last update: 4 employers" in titles, titles
    rows = got["after"][0]["count"]
    assert rows == 0, "no card of its own for any of them"
    # Juno's reply, Wren's follow-up and the quick answers, one card each, the two
    # checklists, one each, and the week's InMail balance question (a Premium example, since
    # 2026-11-05): never a thing a row.
    assert got["after"][1]["text"].startswith("6 things today"), got["after"][1]["text"]


# ------------------------------------------------------------------ 5: who needs you, one meaning


def test_who_needs_you_is_one_meaning_and_to_dos_count_is_read_as_things_for_today(run, tmp_path):
    """Contacts said "1 needs you" while To do, showing Juno's reply and Wren's follow-up, was
    read aloud as "3 need you": who needs you is one meaning on every screen
    (app_model.NEEDS_YOU: a reply, a thank-you or a call yours to do; a follow-up you could send
    is apart, the maintainer, 2026-11-04), and To do's count is read as what it counts, the
    things for today."""
    m = _example()
    got = _go(run, tmp_path, [
        {"hash": "contacts", "read": "#main .summary"},
        {"hash": "todo", "eval": "[...document.querySelectorAll('.badge')].map((b) => b.textContent.trim())"},
    ], PHONE, model=m)
    assert "1 needs you" in got["after"][0]["text"] and m["people_count"]["need"] == 1, got["after"][0]["text"]
    badges = got["after"][1]["eval"]
    assert badges and all("need you" not in b and b.endswith("for today") for b in badges), badges


# ------------------------------------------------------------------ 8: a question and a fix Claude makes


KESTREL = "app-kestrel_mutual_claims_forecasting_analyst"


def test_a_draft_with_a_question_and_a_check_claude_fixes_is_still_made_again(run, tmp_path):
    """A draft with a question and a check Claude can fix itself said "One check needs you"
    with no control and offered Apply: Claude makes it again whatever the question, the card
    says so, the question still asks, and Apply is not the filled next step."""
    m = _example()
    a = next(x for x in m["ready"] if x["id"] == KESTREL)
    a["alerts"] = [{"level": 1, "id": "al-checks-" + KESTREL, "kind": "checks", "text": "The CV runs to a second page.",
                    "why": "Both documents are read back at the right length before anything is sent.",
                    "action": {"type": "work", "label": "Make it again", "kind": "draft", "id": "draft~" + KESTREL,
                               "title": "Make it again: Kestrel Mutual", "args": {"application": KESTREL, "redo": True}},
                    "cost": {"state": 3, "label": "A lot of Claude, several minutes"}}]
    m["needs_you"].append({"id": "q-kestrel-looker", "kind": "question", "title": "Have you used Looker?", "body": "",
                           "options": [{"label": "Yes", "action": "need.answer", "value": "yes"}, {"label": "No", "action": "need.answer", "value": "no"}],
                           "about": {"company": "Kestrel Mutual", "role": "Claims Forecasting Analyst"}, "rev": "kq1"})
    card = '#main [data-item="' + KESTREL + '"]'
    got = _go(run, tmp_path, [{"hash": "jobs", "read": card, "count": card + ' [data-primary="1"]'}], PHONE, model=m)
    text = got["after"][0]["text"]
    assert "Have you used Looker?" in text, text
    assert "Claude makes it again next" in text or "Claude is making it again" in text, text
    assert "needs you" not in text, text
    assert got["after"][0]["count"] == 0, "Apply is not the filled next step over a draft about to change"


# ------------------------------------------------------------------ 9: put off is not done


def test_a_row_put_off_is_not_done_and_contacts_says_it_is_put_off(run, tmp_path):
    """Next week from a To do card's trash gave "1 of 3 done" and filed it under Done today,
    with no line to bring it back, and Contacts still said Overdue with Draft the follow-up:
    put off is not done. It leaves To do with "1 put off: Show", and Contacts says until when,
    with nothing owed on its face."""
    m = _example()
    wren = '#main [data-item="fernhill_freight_halloway"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": "#main .summary"},
        {"click": "Not Wren", "then": "Next week"},
        {"tick": 12000, "read": "#main"},
        {"hash": "contacts", "read": wren},
    ], PHONE, model=m)
    after, card = got["after"][2]["text"], got["after"][3]["text"]
    assert "done" not in after.split("\n")[0], after.split("\n")[0]
    assert "Done today" not in after, after[-400:]
    assert "1 put off" in after, after[-400:]
    assert "Put off until" in card and "Overdue" not in card and "Draft the follow-up" not in card, card


# ------------------------------------------------------------------ 12: the CV's pencil


def test_a_change_to_the_cv_says_when_it_starts_has_cancel_and_holds_apply(run, tmp_path):
    """The CV's pencil said "starts now" while the header said "1 waiting"; the card then said
    "Claude changes this next ... See it" with no Cancel; and "Apply on their site" stayed the
    filled next step over a CV about to change."""
    m = _example()
    seed = {"work/reply~juno": {"kind": "reply", "title": "Reply to Juno", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:50:00Z",
                                "status": "queued", "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None,
                                "claimed_at": None, "stop_asked": False, "attempt": 1}}
    card = '#main [data-item="' + KESTREL + '"]'
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Edit the CV", "within": card},
        {"click": "Compact", "exact": True, "within": "dialog[open]", "read": "#tweak-line"},
        {"click": "Apply", "exact": True, "within": "dialog[open]", "read": card, "count": card + ' [data-primary="1"]'},
    ], PHONE, model=m, seed=seed)
    sheet = got["after"][1]["text"]
    assert "starts now" not in sheet and "after “Reply to Juno”" in sheet, sheet
    after = got["after"][2]
    # Its task in a few words, then Stop Claude (the maintainer, 2026-11-05).
    assert "Changing it next" in after["text"] and "Stop Claude" in after["text"], after["text"]
    assert after["count"] == 0, "Apply is not the filled next step over a CV about to change"


# ------------------------------------------------------------------ 14: every control that wakes Claude has its gauge


NO_GAUGE = ("[...document.querySelectorAll('#main [data-wakes]')].filter((b) => b.getClientRects().length"
            " && !(b.nextElementSibling && b.nextElementSibling.classList.contains('cost')))"
            ".map((b) => (b.getAttribute('aria-label') || b.textContent).trim())")


def test_shorter_warmer_more_formal_pin_it_and_make_one_carry_the_gauge(run, tmp_path):
    """Shorter, Warmer and More formal marked themselves as waking Claude with no kind, so no
    gauge was drawn, and Pin it on the Brief and Make one for your resume queued work with
    none: each names its kind, and its gauge stands beside it."""
    m = _example()
    got = _go(run, tmp_path, [
        {"hash": "contacts", "click": "Change the note to Pell", "eval": NO_GAUGE, "count": "#main .pen-tell [data-wakes] + .cost"},
        {"hash": "brief", "eval": NO_GAUGE, "read": "#main .pin-offer"},
        {"hash": "jobs", "eval": NO_GAUGE, "read": '#main [data-item="resume-current"]'},
    ], WIDE, model=m)
    pen, brief, jobs = got["after"]
    # Since 2026-11-05 the chips fill the box and its one Ask Claude carries the one gauge (the
    # maintainer: a gauge on every chip was clutter).
    assert pen["eval"] == [] and pen["count"] == 1, pen["eval"]
    assert "Pin it" in brief["text"] and brief["eval"] == [], brief["eval"]
    assert "Make one" in jobs["text"] and jobs["eval"] == [], jobs["eval"]


# ------------------------------------------------------------------ 15: no empty band


def test_contacts_with_a_few_people_draws_no_empty_row_under_its_header(run, tmp_path):
    """With three people there is nothing to search or filter, and the row for them drew an
    empty 44px band under the header: a row that holds nothing is not drawn."""
    got = _go(run, tmp_path, [{"hash": "contacts", "count": "#main .controls"}], PHONE, model=_example())
    assert got["after"][0]["count"] == 0


# ------------------------------------------------------------------ 16: one set of state words


def test_a_reply_late_is_overdue_in_contacts_and_while_drafted_says_so(run, tmp_path):
    """Juno's reply, five days late, was Overdue in To do and not in Contacts; and while Claude
    drafted it her card still said "Replied: your turn": one late, the engine's, on both
    screens, and her state says the reply is asked for, then that Claude is drafting it."""
    m = _example()
    juno = '#main [data-item="larkspur_retail_castellan"] .top-end'
    wren = '#main [data-item="fernhill_freight_halloway"]'
    running = {"kind": "reply", "title": "Reply to Wren", "to": "cloud", "args": {"contact": "fernhill_freight_halloway"},
               "asked_at": "2026-10-25T09:00:30Z", "status": "running", "claimed_by": "cloud-1", "claimed_at": "2026-10-25T09:00:40Z",
               "stage": 1, "stage_at": "2026-10-25T09:00:40Z", "lease_until": "2026-10-25T12:00:00Z", "stages": [], "steps": [], "attempt": 1, "_v": 2}
    got = _go(run, tmp_path, [
        {"hash": "contacts", "read": juno},
        {"click": "They replied", "within": wren, "fillMain": {"Paste what Wren sent": "Thanks for the note. Happy to talk next week."}},
        {"click": "Draft my reply", "within": wren, "read": wren + " .top-end"},
        {"write": {"work/reply~fernhill_freight_halloway": running}, "tick": 4000, "read": wren + " .top-end"},
    ], PHONE, model=m)
    # A day the person set is no deadline since the UX review of 2026-11-10 (U-6): her drafted
    # reply past its day is ready to send, never "Overdue".
    assert ("Ready to send" in got["after"][0]["text"] or "Follow-up ready" in got["after"][0]["text"]) and "Overdue" not in got["after"][0]["text"], got["after"][0]["text"]
    asked, going = got["after"][2]["text"], got["after"][3]["text"]
    assert "Replied: your turn" not in asked and "Reply asked for" in asked, asked
    assert "Claude is drafting it" in going, going


# ------------------------------------------------------------------ 17: the card budget


# Each card's pills on its face, More, its pencils and its trash apart, and a checklist's rows
# apart (each row has its own): one filled and two soft at most (DESIGN.md, the budget).
FACE = r"""(() => {
  const seen = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length) && !e.closest('details:not([open]) > :not(summary)') && !e.closest('[hidden]');
  const out = {};
  for (const c of [...document.querySelectorAll('#main [data-card]')].filter(seen)) {
    const rows = '.card-actions, .wc-actions, .suggest-acts, .more-acts, .g-acts, .fix, .bp-foot, .opts';
    const pills = [...c.querySelectorAll('.btn, a.applylink')].filter((b) => seen(b) && b.closest('[data-card]') === c && !b.closest('.g-row, .more-panel, .info-panel')
      && !b.matches('.icon-only, .link, .more-btn') && (!b.matches('.quiet') || b.parentElement.matches(rows)));
    out[c.getAttribute('data-item')] = pills.map((b) => (b.getAttribute('aria-label') || b.textContent).trim().slice(0, 40));
  }
  return out;
})()"""


def test_every_card_keeps_to_one_filled_and_two_soft_pills_and_each_pencil_has_its_word(run, tmp_path):
    """A draft card had five pills and More, a suggestion's two among them; a find four soft
    pills and More; "All checks passed ✎ ✎" said nothing of which pencil was the CV's; and an
    interview's card in To do put "New day" on its face: every card keeps to one filled pill and
    two soft ones, each pencil stands beside its own document's word, and a new day is under
    More."""
    m = _sample()
    # A find with a warm route suggested in its grey box: Write to and No thanks (invented).
    _row(m, "r12-1")["suggest"] = {"level": 2, "id": "sg-warm-r12-1", "kind": "warm",
                                   "text": "Tam at Harbourline Bank replied to you on 23 Oct: ask Tam about this role before applying.",
                                   "why": "A reply is what makes a route warm.", "since": "2026-10-25", "rev": "sgw1",
                                   "action": {"type": "work", "label": "Write to Tam", "kind": "reply", "id": "reply~tam",
                                              "title": "Write to Tam at Harbourline Bank", "args": {"contact": "tam"}},
                                   "cost": {"state": 2, "label": "Some Claude, about a minute or two"}}
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": FACE, "read": '#main [data-item="app-ellerwick-insight"] .checks'},
        {"hash": "todo", "eval": FACE},
        {"hash": "jobs", "read": '#main [data-item="r12-1"]'},
    ], PHONE, model=m)
    jobs, todo = got["after"][0]["eval"], got["after"][1]["eval"]
    over = {k: v for k, v in {**jobs, **todo}.items() if len(v) > 3}
    assert not over, over
    assert "Write to Tam" in got["after"][2]["text"] and len(jobs["r12-1"]) == 3, jobs["r12-1"]
    checks = got["after"][0]["text"]
    assert "CV" in checks and "letter" in checks, checks
    ivs = {k: v for k, v in todo.items() if k.startswith("soon:")}
    assert ivs and not any("new day" in " ".join(v).lower() for v in ivs.values()), ivs


# ------------------------------------------------------------------ 18: no underlined text as a control


UNDERLINED = r"""(() => {
  const seen = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const els = [...document.querySelectorAll('#main .pin-acts > *, #main .todo-top a, #main .todo-top button:not(.icon-only), #main .export-foot button, #main .export-foot a')];
  return els.filter(seen).filter((e) => getComputedStyle(e).textDecorationLine !== 'none').map((e) => e.textContent.trim());
})()"""


def test_not_now_open_in_coming_up_and_the_linkedin_download_are_never_underlined_text(run, tmp_path):
    """"Not now" beside Pin it, "Open in Coming up" in an interview card's top line and "Add
    your LinkedIn download" alone at the foot of Contacts were underlined text in a row of
    actions: each is a soft pill, or the card's own title."""
    m = _example()
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": UNDERLINED, "read": "#main .pin-offer"},
        {"hash": "todo", "eval": UNDERLINED, "read": '#main [data-item="soon:int-thornbury_bank_risk_analyst"]'},
        {"hash": "contacts", "eval": UNDERLINED, "read": "#main .export-foot"},
    ], PHONE, model=m)
    brief, todo, contacts = got["after"]
    assert "Not now" in brief["text"] and brief["eval"] == [], brief["eval"]
    assert "Open in Coming up" not in todo["text"] and todo["eval"] == [], (todo["text"], todo["eval"])
    assert "Add your LinkedIn download" in contacts["text"] and contacts["eval"] == [], contacts["eval"]


# ------------------------------------------------------------------ 11: Your rules, as the example's engine made them


def test_the_examples_rules_have_a_row_for_every_cut_jobs_counts_and_say_the_country_as_remote():
    """The example's Your rules summed fewer left out than Jobs said (its qualification cut had
    no row) and listed the country-wide remote search as a town: the engine's own model (the
    example fixture, made by tests/app_state.py) has a row for every kind Jobs counts, adding
    up to Jobs' count, and says the country as remote work anywhere in it."""
    m = _example()
    groups = m["jobs"]["filtered"]["groups"]
    rows = m["rules"]["rows"]
    assert {g["kind"] for g in groups} <= {r["kind"] for r in rows}, ([g["kind"] for g in groups], [r["kind"] for r in rows])
    assert sum(r["left_out"] or 0 for r in rows) == m["jobs"]["filtered"]["count"]
    where = next(r for r in rows if r["id"] == "rule~places")["sentence"]
    assert "remote work anywhere in the United Kingdom" in where and "Stockport and United Kingdom" not in where, where


# ------------------------------------------------------------------ 19: the foot under the column


EDGES = ("(() => { const s = document.querySelector('#main > .sec'), f = document.querySelector('.foot-line') || document.querySelector('.foot');"
         " return [Math.round(s.getBoundingClientRect().left), Math.round(f.getBoundingClientRect().left)]; })()")


@pytest.mark.parametrize("model", ["example", "sample"])
def test_the_laptop_foot_starts_where_the_screens_column_does(run, tmp_path, model):
    """On a laptop "Private to you. Details" started left of the cards on Contacts and Jobs:
    the foot keeps to the screen's column, on every screen."""
    m = _example() if model == "example" else _sample()
    got = _go(run, tmp_path, [{"hash": s, "eval": EDGES} for s in ("contacts", "jobs", "todo", "brief")], WIDE, model=m)
    edges = {s: a["eval"] for s, a in zip(("contacts", "jobs", "todo", "brief"), got["after"])}
    off = {s: e for s, e in edges.items() if abs(e[0] - e[1]) > 2}
    assert not off, off
