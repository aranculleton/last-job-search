"""The journeys a person takes across the page, end to end (FUNCTIONS_SPEC 5.2).

Each journey taps the page as a person would, checks the action document the page wrote (its
item, its action, its value fields, and `rev_seen` equal to the item's own rev), then plays the
chat: a receipt that says it is done, and a new `view/<section>` document holding the model's
next state, as `app.py view` writes it. Then it reads what the page shows next and where its
links go. Every journey runs on a phone (375 x 812) and on a wide screen (1440 x 900). The
sample (tests/fixtures/app_model_sample.json) is an invented search: every person and employer
in it is made up.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_page  # noqa: E402
from test_the_page_works_in_a_browser import FIXTURE, HARNESS, Runner, _node_env  # noqa: E402

PHONE = {"width": 375, "height": 812}
WIDE = {"width": 1440, "height": 900}


def browser():
    """The harness in a browser, for this module and the ones that share its journeys."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    env = _node_env()
    if subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True).returncode:
        pytest.skip("Playwright for Node is not installed here")
    proc = subprocess.Popen([node, HARNESS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)
    r = Runner(proc)
    hello = r.first()
    if not hello.get("ready"):
        proc.kill()
        pytest.skip("Chromium would not start: " + str(hello.get("error", ""))[:200])
    yield r
    proc.stdin.close()
    proc.wait(timeout=60)


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _sample():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _go(run, tmp_path, steps, vp, model=None, seed=None, fake=None, clock=None):
    model = model or _sample()
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed=seed or {}, fake=fake or {"canSend": "available"}, clock=clock)
    assert not got["errors"], got["errors"]
    return got


def _one(got, action):
    found = [a for a in got["actions"] if a["action"] == action]
    assert found, (action, [a["action"] for a in got["actions"]])
    return found[-1]


def _item(model, item_id):
    for key in ("ready", "messages", "people", "interviews", "due", "needs_you", "applications"):
        for it in model.get(key) or []:
            if it.get("id") == item_id:
                return it
    for it in model["jobs"]["rows"]:
        if it["id"] == item_id:
            return it
    for g in model["jobs"]["filtered"]["groups"]:
        for it in g.get("items") or []:
            if it["id"] == item_id:
                return it
    raise KeyError(item_id)


def _rev_is_the_items(model, action):
    assert action["rev_seen"] == _item(model, action["item"])["rev"], action


# ------------------------------------------------------------------ 1 to 6: applications and interviews


def test_a_job_goes_from_draft_this_to_applied_on_the_day_given(run, tmp_path, vp):
    m = _sample()
    nxt = copy.deepcopy(m)
    row = _item(nxt, "r12-1")
    row.update(status="applied", rev="j1b")
    nxt["applications"].insert(0, {"id": "app-harbourline-pricing", "company": "Harbourline Bank", "role": "Pricing Analyst", "applied_on": "2026-10-20",
                                   "status": "applied", "last": "2026-10-20", "rev": "apx", "stages": [{"name": "Applied", "on": "2026-10-20", "done": True}]})
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Draft this: Harbourline Bank, Pricing Analyst"},
        {"click": "Yes, I have applied", "role": "radio"},
        {"fill": {"When did you apply?": "2026-10-20"}},
        {"click": "Mark as applied", "receipts": True, "view": {"jobs": nxt["jobs"], "applications": nxt["applications"]}},
        {"hash": "jobs", "open": "jobsw:applied", "read": '[data-item="app-harbourline-pricing"]'},
    ], vp)
    a = _one(got, "job.applied")
    assert a["item"] == "r12-1" and a["value"] == {"on": "2026-10-20"}
    _rev_is_the_items(m, a)
    card = got["after"][-1]["text"]
    assert "Pricing Analyst" in card and "Applied" in card and "20" in card, card


def test_a_draft_is_downloaded_marked_applied_and_its_follow_up_is_done_from_to_do(run, tmp_path, vp):
    m = _sample()
    nxt = copy.deepcopy(m)
    _item(nxt, "app-ellerwick-insight").update(status="applied", applied_on="2026-10-25", rev="a1b")
    nxt["due"].append({"id": "due-ellerwick-follow", "kind": "follow_up", "title": "Follow up with Ellerwick Trust", "due": "2026-10-25", "overdue_days": 0,
                       "action": "work:follow_up", "application": "app-ellerwick-insight", "done": {"action": "due.done", "label": "Done"}, "rev": "d9"})
    got = _go(run, tmp_path, [
        {"hash": "drafts", "click": "Get both files: Morgan_Ellis_CV_Ellerwick.pdf and Morgan_Ellis_Cover_Letter_Ellerwick.pdf", "calls": "downloads"},
        {"click": "I have applied: Ellerwick Trust, Research Analyst", "receipts": True, "view": {"ready": nxt["ready"], "due": nxt["due"]}},
        {"hash": "todo", "read": '[data-item="due-ellerwick-follow"]'},
        {"click": "Done: Follow up with Ellerwick Trust"},
    ], vp)
    assert [c["filename"] for c in got["after"][0]["calls"]] == ["Morgan_Ellis_CV_Ellerwick.pdf", "Morgan_Ellis_Cover_Letter_Ellerwick.pdf"]
    a = _one(got, "ready.applied")
    assert a["value"]["on"] and a["rev_seen"] == "a1"
    row = got["after"][2]["text"]
    assert "Draft the follow-up" in row and "Done" in row, row
    d = _one(got, "due.done")
    assert d["item"] == "due-ellerwick-follow" and d["rev_seen"] == "d9"


def test_hearing_back_books_an_interview_and_one_prep_card_follows(run, tmp_path, vp):
    m = _sample()
    nxt = copy.deepcopy(m)
    nxt["interviews"].insert(0, {"id": "int-quayside-ops", "company": "Quayside Foods", "role": "Operations Analyst", "next_stage": "Phone screen",
                                 "when": "2026-10-26T13:00:00Z", "time": "13:00", "with": "the recruiter", "prep": None, "questions": 0,
                                 "alerts": [], "suggest": None, "status": "interview", "application": "app-quayside-ops", "rev": "iq1"})
    nxt["due"].append({"id": "due-quayside-prep", "kind": "prep", "title": "Prepare for the Quayside Foods phone screen", "due": "2026-10-26",
                       "overdue_days": 0, "action": "work:prep", "interview": "int-quayside-ops", "rev": "d10"})
    got = _go(run, tmp_path, [
        {"hash": "jobs", "open": "jobsw:applied", "click": "I heard back: Quayside Foods, Operations Analyst"},
        {"click": "An interview is booked", "role": "radio"},
        {"fill": {"Which stage": "Phone screen", "The day": "2026-10-26", "The time": "13:00", "With whom": "the recruiter"}},
        {"click": "Save", "exact": True, "receipts": True, "view": {"interviews": nxt["interviews"], "due": nxt["due"]}},
        {"hash": "todo", "eval": "[document.querySelectorAll('#main [data-item=\"soon:int-quayside-ops\"]').length, document.querySelectorAll('#main [data-item=\"due-quayside-prep\"]').length, document.querySelector('#main [data-card]').dataset.item]"},
        {"hash": "interviews"},
    ], vp, clock="2026-10-25T09:00:00Z")
    a = _one(got, "outcome.interview")
    assert a["item"] == "app-quayside-ops"
    assert a["value"] == {"on": "2026-10-26", "stage": "Phone screen", "time": "13:00", "with": "the recruiter"}
    _rev_is_the_items(m, a)
    cards, prep_rows, first = got["after"][4]["eval"]
    assert cards == 1 and prep_rows == 0, "one card for the interview and its prep, never two"
    assert first == "soon:int-quayside-ops", "the soonest interview is the first card"
    assert "Phone screen with Quayside Foods" in got["after"][5]["text"]


def test_a_rejection_stops_the_chase(run, tmp_path, vp):
    m = _sample()
    nxt = copy.deepcopy(m)
    _item(nxt, "app-quayside-ops").update(status="rejected", last="2026-10-25", rev="apr")
    nxt["due"] = [d for d in nxt["due"] if d["id"] != "due-quayside-ops-follow"]
    got = _go(run, tmp_path, [
        {"hash": "jobs", "open": "jobsw:applied", "click": "I heard back: Quayside Foods, Operations Analyst"},
        {"click": "Not this time", "role": "radio"},
        {"click": "Save", "exact": True, "receipts": True, "view": {"applications": nxt["applications"], "due": nxt["due"]}},
        {"hash": "todo"},
        {"hash": "jobs", "open": "jobsw:applied", "read": '[data-item="app-quayside-ops"]'},
    ], vp)
    a = _one(got, "outcome.rejected")
    assert a["item"] == "app-quayside-ops" and a["rev_seen"] == _item(m, "app-quayside-ops")["rev"]
    assert "Follow up on the Quayside Foods Operations Analyst application" not in got["after"][3]["text"]
    assert "Not this time" in got["after"][4]["text"]


def test_an_interview_binned_leaves_interviews_at_once_and_undo_brings_it_back(run, tmp_path, vp):
    # The bin on an interview said "no reply" and the card stayed until a chat applied it (the
    # maintainer, 2026-10-29): it leaves Interviews, To do and the counts as it is chosen.
    card = "document.querySelector('#main article[data-item=\"int-harbourline-risk\"]')"
    line = "document.querySelector('#main .ended[data-item=\"int-harbourline-risk\"]')"
    soon = "document.querySelectorAll('#main [data-item=\"soon:int-harbourline-risk\"]').length"
    binned = [
        {"hash": "interviews", "open": "ivbin:int-harbourline-risk"},
        {"click": "No reply, and I have stopped waiting", "role": "radio"},
        {"submit": True, "ready": "!" + card + " && !!" + line},
    ]
    got = _go(run, tmp_path, [{"hash": "todo", "eval": soon}] + binned + [{"hash": "todo", "eval": soon}], vp)
    a = _one(got, "outcome.no_response")
    assert a["item"] == "int-harbourline-risk" and a["rev_seen"] == _item(_sample(), a["item"]).get("rev")
    before, ended, todo = got["after"][0], got["after"][3], got["after"][4]
    assert before["eval"] == 1 and todo["eval"] == 0, (before["eval"], todo["eval"])
    assert "Second interview with Harbourline Bank: marked as no reply." in ended["text"], ended["text"]
    assert "Saved. Claude will pick this up." in ended["text"] and "2 interviews coming up" in ended["text"], ended["text"]
    # Undo, before a chat has seen it: the card is back and nothing is left to apply.
    got = _go(run, tmp_path, binned + [{"open": "undo:ivend:int-harbourline-risk", "ready": "!!" + card + " && !" + line}], vp)
    assert "3 interviews coming up" in got["after"][3]["text"] and "marked as no reply" not in got["after"][3]["text"]
    assert not [x for x in got["actions"] if x["action"] == "outcome.no_response"]


def test_the_prep_is_read_on_the_page_and_practice_uses_its_questions(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Read your prep", "read": "dialog.detail"},
        {"click": "Practise with Claude", "within": "dialog.detail", "read": "#main", "wait": 300, "calls": "sample"},
        {"eval": "(() => { const t = document.querySelector('#talk-text'); t.value = 'I have three years of store and supplier data behind me, turned into weekly plans.'; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()"},
        {"click": "Send", "exact": True, "wait": 300, "read": "#main .talk-list"},
    ], vp, fake={"canSend": "available", "sample": {"replies": [
        "Tell me about yourself.",
        "Band: Solid\n- You said \"three years of store and supplier data\": lead with it.\n- Say more about the regional team.\nWhy Larkspur Retail?"]}})
    read = got["after"][0]["text"]
    for q in ("Tell me about yourself.", "Why Larkspur Retail?", "Tell me about a forecast that was wrong."):
        assert q in read, q
    first = got["after"][1]["calls"][0]
    asked = json.dumps(first)
    assert "Tell me about yourself." in asked and "Why Larkspur Retail?" in asked, "the practice is given the pack's own questions"
    feedback = got["after"][3]["text"]
    assert "Band: Solid" in feedback and "three years of store and supplier data" in feedback
    assert "Say more about the regional team" not in feedback, "a point that does not quote the answer is never shown"


def test_a_thank_you_due_row_drafts_a_thank_you_not_a_prep(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": '[data-item="due-harbourline-thanks"]'},
        {"click": "Draft the thank-you"},
    ], vp)
    row = got["after"][0]["text"]
    assert "Draft the thank-you" in row and "Prepare me" not in row
    (w,) = [x for x in got["after"][1]["work"] if x["kind"] == "follow_up"]
    assert w["args"]["interview"] == "int-harbourline-risk" and w["args"]["kind"] == "thank_you"


# ------------------------------------------------------------------ 7 to 13: messages and contacts


def test_a_first_note_is_copied_exactly_opened_and_logged_with_the_words_that_went(run, tmp_path, vp):
    m = _sample()
    edited = "Hello Ash, I saw you moved to Copperleaf Pay from Quayside Foods. " + "I work on supply chain analytics in Manchester. " * 6
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "contsw:messages", "click": "Copy note to Ash", "clip": True, "read": '[data-item="msg-ash-1"]'},
        {"click": "I sent the note to Ash", "read": '[data-item="msg-ash-1"]'},
    ], vp)
    note = _item(m, "msg-ash-1")
    assert got["after"][0]["clip"] == note["text"], "exactly the words, no label, no count"
    assert "Copied" in got["after"][0]["text"] and "of 300 characters" in got["after"][0]["text"]
    a = _one(got, "msg.sent")
    assert a["item"] == "msg-ash-1" and a["value"]["text"] == note["text"] and a["value"]["on"]
    _rev_is_the_items(m, a)
    # Changed before sending: the words that went are logged, and the count turns red over the limit.
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "contsw:messages"},
        {"open": "changed-sum:msg-ash-1"},
        {"eval": "(() => { const t = document.querySelector('#chg-msg-ash-1'); t.value = " + json.dumps(edited) + "; t.dispatchEvent(new Event('input', {bubbles: true})); return document.querySelector('#chg-msg-ash-1-n').className; })()"},
        {"click": "I sent these words"},
    ], vp)
    assert "tone-bad" in got["after"][2]["eval"], "the count turns red over the limit, and nothing is cut"
    a = _one(got, "msg.sent")
    assert a["item"] == "msg-ash-1" and a["value"]["text"] == edited.strip()


def test_an_inmail_copies_subject_and_message_apart(run, tmp_path, vp):
    m = _sample()
    noor = _item(m, "msg-noor-1")
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "contsw:messages", "click": "Copy subject", "within": '[data-item="msg-noor-1"]', "clip": True},
        {"click": "Copy message", "within": '[data-item="msg-noor-1"]', "clip": True},
    ], vp)
    assert got["after"][0]["clip"] == noor["subject"]
    assert got["after"][1]["clip"] == noor["body"] and "Subject:" not in got["after"][1]["clip"]


def test_an_email_opens_in_the_mail_app_with_subject_and_body_filled(run, tmp_path, vp):
    seed = {"reach/ellerwick_trust_priya": {"email": "priya@example.com"}}
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "contsw:messages", "attr": ['[data-k="open:msg-priya-thanks"]', "href"]},
    ], vp, seed=seed)
    href = got["after"][0]["attr"]
    assert href.startswith("mailto:priya%40example.com?subject=Thank%20you%20for%20Thursday&body=")
    assert "%0D%0A" in href and "\n" not in href
    got = _go(run, tmp_path, [{"hash": "contacts", "open": "contsw:messages", "count": '[data-k="open:msg-priya-thanks"]'}], vp)
    assert got["after"][0]["count"] == 0, "no address on file: no button, never a guess"


def test_a_wave_of_first_notes_is_grouped_by_employer_with_the_week_s_budget(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "contsw:messages", "read": "#main .wave"},
        {"hash": "todo", "count": '#main [data-item^="wave:"]'},
    ], vp)
    wave = got["after"][0]["text"]
    for employer in ("Copperleaf Pay", "Larkspur Retail Ltd", "Quayside Foods"):
        assert employer in wave, employer
    assert "3 notes ready. 3 sent this week of about 20." in wave
    assert got["after"][1]["count"] == 1, "one card for the wave in To do, never one a note"


def test_a_reply_owed_says_so_and_drafts_from_their_words_already_kept(run, tmp_path, vp):
    """Juno's reply is in the conversation already: drafting the answer asks only what to say
    back, never for their words a second time (2026-10-29)."""
    got = _go(run, tmp_path, [
        {"hash": "contacts", "read": '[data-item="larkspur_retail_castellan"]'},
        {"click": "Draft a reply to Juno", "read": "dialog"},
        {"fill": {"Anything you want to say back": "Yes, Thursday at 12 works."}, "submit": True},
    ], vp)
    assert "Replied: your turn" in got["after"][0]["text"]
    assert "Paste what Juno said" not in got["after"][1]["dialog"]
    w = [x for x in got["work"] if x and x.get("kind") == "reply"]
    assert len(w) == 1 and w[0]["args"] == {"contact": "larkspur_retail_castellan", "want": "Yes, Thursday at 12 works."}


def test_a_call_is_booked_prepared_for_and_followed_by_a_thank_you(run, tmp_path, vp):
    m = _sample()
    got = _go(run, tmp_path, [
        {"hash": "contacts", "more": "ellerwick_trust_priya", "click": "A call booked with Marisol"},
        {"fill": {"The day": "2026-10-28"}, "submit": True},
        {"hash": "contacts", "click": "Prepare for the call with Bea"},
        {"submit": True},
    ], vp)
    a = _one(got, "person.call_booked")
    assert a["item"] == "ellerwick_trust_priya" and a["value"]["on"] == "2026-10-28"
    _rev_is_the_items(m, a)
    (w,) = [x for x in got["after"][-1]["work"] if x["kind"] == "prep"]
    assert w["args"] == {"contact": "harbourline_bank_bea"} or w["args"].get("contact") == "harbourline_bank_bea"
    assert "interview" not in w["args"]
    # After the day: How did it go? offers the thank-you.
    later = copy.deepcopy(m)
    _item(later, "harbourline_bank_bea").update(call={"day": "2026-10-24", "time": "15:00"}, due="2026-10-24")
    got = _go(run, tmp_path, [{"hash": "contacts", "read": '[data-item="harbourline_bank_bea"]'}], vp, model=later)
    assert "How did it go?" in got["after"][0]["text"] and "Draft the thank-you" in got["after"][0]["text"]


def test_a_hiring_call_becomes_an_interview_not_a_call_prep(run, tmp_path, vp):
    m = _sample()
    _item(m, "harbourline_bank_bea")["is_process_stage"] = True
    got = _go(run, tmp_path, [
        {"hash": "contacts", "read": '[data-item="harbourline_bank_bea"]'},
        {"click": "Make the call with Bea an interview"},
    ], vp, model=m)
    assert "This call is an interview stage" in got["after"][0]["text"]
    assert "Prepare for the call" not in got["after"][0]["text"]
    a = _one(got, "process.register")
    assert a["item"] == "harbourline_bank_bea"


# ------------------------------------------------------------------ 14 to 18: referrals and links


def test_a_referral_is_asked_for_one_role_and_holds_cold_applications(run, tmp_path, vp):
    m = _sample()
    nxt = copy.deepcopy(m)
    _item(nxt, "larkspur_retail_castellan").update(status="referral_in_progress", rev="p-juno2")
    row = _item(nxt, "r12-2")
    row["alerts"] = [{"level": 1, "id": "al-referral_hold-r12-2", "kind": "referral_hold",
                      "text": "Juno has put your name forward at Larkspur Retail for the Supply Chain Data Analyst role: do not apply cold.",
                      "why": "A cold application lands as a second, worse record of you, and the referral is the one that loses.",
                      "action": {"type": "go", "label": "See Juno", "to": "people", "item": "larkspur_retail_castellan"}, "cost": {"state": 0, "label": "Free, instant"}}]
    got = _go(run, tmp_path, [
        {"hash": "jobs", "more": "r12-2", "click": "Ask Juno for a referral for this role"},
        {"submit": True, "receipts": True, "view": {"people": nxt["people"], "jobs": nxt["jobs"]}},
        {"hash": "jobs", "eval": "document.querySelector('#main [data-item=\"r12-2\"]').textContent"},
        {"hash": "contacts", "more": "larkspur_retail_castellan", "click": "The referral is over: Juno"},
        {"click": "Not this time", "role": "radio", "submit": True},
    ], vp)
    (w,) = [x for x in got["after"][1]["work"] if x["kind"] == "reply"]
    assert w["args"]["contact"] == "larkspur_retail_castellan" and w["args"]["job"] == "r12-2" and w["args"]["kind"] == "referral_ask"
    assert "Supply Chain Data Analyst role" in got["after"][2]["eval"], "the hold names the role"
    ended = _one(got, "referral.ended")
    assert ended["item"] == "larkspur_retail_castellan" and ended["value"] == {"why": "rejected"}


def test_a_resume_asked_for_is_made_for_that_person_and_logged_with_its_file(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        # The choices read from the options themselves: Firefox and Safari leave a select's
        # options out of the dialog's text (the Everywhere check, 2026-10-29).
        {"hash": "todo", "click": "Choose the role", "read": "dialog",
         "eval": "[...document.querySelectorAll('dialog option')].map((o) => o.textContent).join('\\n')"},
        {"click": "Cancel", "exact": True},
        {"hash": "drafts", "click": "I sent it to Tamsin"},
        {"submit": True},
    ], vp)
    sheet = got["after"][0]["dialog"]
    assert "Which role is it for?" in sheet and "Free, instant" in got["after"][0]["eval"], sheet
    a = _one(got, "ready.sent_to_contact")
    assert a["item"] == "app-copperleaf-payments" and a["rev_seen"] == "a3"
    assert a["value"]["attached"] == "Morgan_Ellis_CV_Copperleaf.pdf" and a["value"]["contact"] == "copperleaf_pay_tamsin"


def test_a_referral_led_screen_with_no_application_names_the_referrer(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "read": '[data-item="int-copperleaf-payments"]'},
        {"hash": "jobs", "more": "r12-3", "read": '[data-item="r12-3"]'},
    ], vp)
    card = got["after"][0]["text"]
    assert "Referred by Tamsin" in card
    assert "I have applied" not in got["after"][1]["text"], "a process led by a referral has no cold application"


def test_the_warm_route_on_a_job_opens_the_person_and_back_returns(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Juno", "role": "link", "within": "[data-item=\"r12-2\"] .warm"},
        {"eval": "history.back(), 0", "until": "location.hash !== '#contacts/larkspur_retail_castellan'"},
    ], vp)
    assert got["after"][0]["hash"] == "#contacts/larkspur_retail_castellan"
    assert got["after"][1]["hash"] == "#jobs"


def test_links_are_the_model_s_own_so_spelling_differences_still_join(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "jobs", "more": "r12-2", "read": '[data-item="r12-2"]'}], vp)
    assert "Kit" in got["after"][0]["text"], "Kit at Larkspur Retail Ltd is linked from the Larkspur Retail role"


# ------------------------------------------------------------------ 19 to 23: changing your mind, To do, setup


def test_changing_your_mind_keeps_the_reason_and_brings_things_back(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Not for me: Harbourline Bank, Pricing Analyst"},
        # Why is asked once, in the bin's own sheet (2026-10-29: never a second "Why?").
        {"click": "The pay", "role": "radio", "exact": True},
        {"click": "Take it off my list"},
        {"click": "41 left out by the search", "exact": False},
        {"click": "Bring back Transport Planning Analyst at Fernhill Freight"},
        {"click": "Set it aside", "exact": True},
    ], vp)
    d = [a for a in got["actions"] if a["action"] == "job.dismiss"]
    assert any(a["item"] == "r12-1" and a["value"] == {"why": "pay"} for a in d)
    b = _one(got, "job.bring_back")
    assert b["item"] == "r12-f1" and b["rev_seen"] == "f1"
    closed = [a for a in d if a["item"] == "r12-5"]
    assert closed and closed[-1]["rev_seen"] == "j5" and closed[-1]["value"] == {"why": "closed"}


def test_an_unconfirmed_send_is_asked_as_a_question(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": '[data-item="q-sent-fernhill_freight_halloway"]', "eval": "[...document.querySelectorAll('[data-item=\"q-sent-fernhill_freight_halloway\"] .opts button')].map((b) => b.className)"},
        {"click": "Yes, it went"},
    ], vp)
    assert "Did your note to Wren go?" in got["after"][0]["text"]
    classes = got["after"][0]["eval"]
    assert len(classes) == 2 and len(set(classes)) == 1, "two answers of equal weight"
    a = _one(got, "msg.sent")
    assert a["item"] == "msg-wren-2" and a["value"]["outside"] is True and a["rev_seen"] == "m2"


def test_a_pasted_interview_invitation_is_booked_only_after_the_person_confirms(run, tmp_path, vp):
    invite = ("Hi Morgan, thank you for applying to the Operations Analyst role at Quayside Foods. We would like to invite you to a phone screen "
              "on Thursday 29 October at 11:00 with Sam from our talent team. Please confirm.")
    fields = {"kind": "interview", "company": "Quayside Foods", "role": "Operations Analyst", "stage": "Phone screen", "day": "2026-10-29", "time": "11:00", "with": "Sam from the talent team",
              "application": "app-quayside-ops"}
    got = _go(run, tmp_path, [
        {"hash": "chat", "eval": "(() => { const t = document.querySelector('#talk-text'); t.value = " + json.dumps(invite) + "; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()"},
        {"click": "Send", "exact": True, "wait": 600, "read": "#main"},
        {"click": "Book it"},
    ], vp, fake={"canSend": "available", "sample": {"reply": json.dumps(fields)}})
    before = [a for a in got["actions"] if a["action"] == "outcome.interview"]
    assert "Book this interview" in got["after"][1]["text"] and "11:00" in got["after"][1]["text"]
    a = before[-1]
    assert a["item"] == "app-quayside-ops" and a["value"]["on"] == "2026-10-29" and a["value"]["time"] == "11:00"


def test_setup_runs_to_a_first_shortlist(run, tmp_path, vp):
    m = {"model": 1, "made_at": "2026-10-25T08:00:00Z", "rev": "0", "person": {"first_name": "Morgan", "doc_noun": "CV", "time_zone": "Europe/London", "repo": "morgan-example/job-search"},
         "setup": {"state": "running", "next": "work", "progress": {"done": 1, "total": 6, "label": "2 of 6"},
                   "research": [{"topic": "boards", "label": "Job sites for your work and city", "status": "running"}],
                   "steps": [{"id": "setup-resume", "step": "resume", "n": 1, "kind": "upload-or-paste", "question": "Your CV: add the file, or paste it.", "status": "done", "rev": "s1",
                              "options": [{"label": "Build one with me", "action": "setup.build_resume"}]},
                             {"id": "setup-work", "step": "work", "n": 2, "kind": "text", "question": "What work do you want next, and where?", "status": "next", "rev": "s2",
                              "fields": [{"key": "work", "kind": "text", "label": "The work you want next"}, {"key": "place", "kind": "place", "label": "Where you'd like to work"}]}]}}
    nxt = dict(copy.deepcopy(m)["setup"], state="searching", next=None, progress={"done": 6, "total": 6, "label": "6 of 6"},
               research=[{"topic": "boards", "label": "Job sites for your work and city", "status": "done"}])
    jobs = _sample()["jobs"]
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Continue"},
        {"fill": {"The work you want next": "Demand planning", "Where you'd like to work": "Leeds"}},
        {"click": "Continue", "exact": True, "within": "dialog.question-screen", "receipts": True, "view": {"setup": nxt}},
        {"hash": "todo", "read": "#main"},
        {"view": {"setup": dict(nxt, state="done"), "jobs": jobs}, "hash2": "jobs"},
    ], vp, model=m)
    a = _one(got, "setup.answer")
    assert a["value"] == {"work": "Demand planning", "place": "Leeds"} and a["rev_seen"] == "s2"
    assert "Your first shortlist" in got["after"][3]["text"] and "Searching" in got["after"][3]["text"]
    assert "Supply Chain Data Analyst" in got["after"][4]["text"]


def test_the_brief_opens_its_items(run, tmp_path, vp):
    # The Brief is a page of its own (4.3): each line opens the thing it is about.
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": "(() => !!document.querySelector('#main .brief-page .bp-next'))()"},
        {"click": "Reply to Juno at Larkspur Retail.", "role": "link"},
        {"hash": "brief", "click": "Read the prep for the Larkspur Retail phone screen.", "role": "link"},
    ], vp, clock="2026-10-25T07:30:00Z")
    assert got["after"][0]["eval"], "the Brief has its own page, with the next three"
    assert got["after"][1]["hash"] == "#contacts/larkspur_retail_castellan"
    assert got["after"][2]["hash"] == "#interviews/int-larkspur-supply"
