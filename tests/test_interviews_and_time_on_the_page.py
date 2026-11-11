"""Interviews and time, from the 3 November audit: the page half.

Each test taps the page as the audit's steps did (tests/app_page/harness.js with
fake_claude.js), on the invented sample search (tests/fixtures/app_model_sample.json), on a
phone unless the finding was about a wide screen. A device's own clock is set where a finding
was about one: London, Toronto and Vancouver.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_page  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample, browser  # noqa: E402

T = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _go(run, tmp_path, steps, model=None, seed=None, fake=None, clock=T, vp=PHONE, zone=None):
    model = model or _sample()
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed=seed or {},
              fake=fake or {"canSend": "available"}, clock=clock,
              **({"timezoneId": zone} if zone else {}))
    assert not got["errors"], got["errors"]
    return got


def _acts(got, action):
    return [a for a in got["actions"] if a["action"] == action]


def _paste(text):
    return {"hash": "chat", "eval": "(() => { const t = document.querySelector('#talk-text'); t.value = " + json.dumps(text) +
            "; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()"}


INVITE = ("Hi Morgan, thank you for applying to the Senior Supply Chain Analyst role at Larkspur Retail. We would like to "
          "invite you to the initial round. We have interview days on 29 October, 30 October and 5 November: let me "
          "know which day you would prefer by Tuesday 27 October.")
OFFER = {"kind": "interview", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst", "stage": "initial round",
         "day": "2026-10-29", "days": ["2026-10-29", "2026-10-30", "2026-11-05"], "reply_by": "2026-10-27", "time": None,
         "with": "the recruiter", "application": "app-larkspur-supply"}


# ------------------------------------------------------------------ several days offered (interviews 1, 2; top 30, 15)


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_an_invitation_offering_several_days_asks_which_and_books_the_one_tapped(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        _paste(INVITE),
        {"click": "Send", "exact": True, "wait": 600, "read": "#main"},
        {"click": "I'll take Fri 30 Oct", "exact": True, "read": "#main"},
    ], fake={"canSend": "available", "sample": {"reply": json.dumps(OFFER)}}, vp=vp)
    card = got["after"][1]["text"]
    # The model said the first day as "day": it is never booked as if chosen.
    assert "they offer Thu 29 Oct, Fri 30 Oct or Thu 5 Nov" in card and "Which day will you take?" in card, card
    assert "Book it" not in card
    a = _acts(got, "outcome.interview")
    assert len(a) == 1 and a[0]["value"]["on"] == "2026-10-30" and a[0]["value"]["stage"] == "Initial round"
    assert "offered" not in a[0]["value"]
    assert "Booked for Fri 30 Oct" in got["after"][2]["text"]


def test_choose_later_keeps_the_days_offered_and_the_day_to_answer_by(run, tmp_path):
    got = _go(run, tmp_path, [
        _paste(INVITE),
        {"click": "Send", "exact": True, "wait": 600},
        {"click": "I'll choose later", "exact": True, "read": "#main"},
    ], fake={"canSend": "available", "sample": {"reply": json.dumps(OFFER)}})
    a = _acts(got, "outcome.interview")[0]
    assert a["value"]["on"] == "" and a["value"]["offered"] == OFFER["days"] and a["value"]["reply_by"] == "2026-10-27"
    assert "waits in Coming up until you choose your day" in got["after"][2]["text"]


def test_a_second_invitation_is_never_shown_as_booked_by_an_earlier_booking(run, tmp_path):
    # Interviews 3: an earlier booking on the same application made the new offer read
    # "Booked ... Done." before anything was tapped.
    seed = {"actions/act~early": {"item": "app-larkspur-supply", "action": "outcome.interview",
                                  "value": {"on": "2026-10-28", "stage": "Phone screen"}, "at": "2026-10-24T09:00:00Z"},
            "receipts/act~early": {"applied_at": "2026-10-24T10:00:00Z", "result": "ok"}}
    one = dict(OFFER, days=[], day="2026-11-05", stage="Final round")
    got = _go(run, tmp_path, [
        _paste(INVITE),
        {"click": "Send", "exact": True, "wait": 600, "read": ".offer-card",
         "eval": "[...document.querySelectorAll('.offer-card [data-k=\"book-it\"]')].map((b) => [b.textContent, b.getAttribute('aria-pressed')])"},
    ], seed=seed, fake={"canSend": "available", "sample": {"reply": json.dumps(one)}})
    assert got["after"][1]["eval"] == [["Book it", None]] or got["after"][1]["eval"] == [["Book it", "false"]], got["after"][1]["eval"]
    assert "Done." not in got["after"][1]["text"] and "Booked" not in got["after"][1]["text"]


def _offered_model():
    model = _sample()
    iv = next(i for i in model["interviews"] if i["id"] == "int-harbourline-risk")
    iv.update(when=None, offered=["2026-10-29", "2026-10-30"], reply_by="2026-10-27", next_stage="Second interview")
    model["due"] = [{"id": "due-interview-harbourline", "kind": "interview", "sub": "choose", "title": "Harbourline Bank: choose your interview day and tell them",
                     "context": "", "due": "2026-10-27", "company": "Harbourline Bank", "overdue_days": 0, "action": "go:interviews",
                     "item": "int-harbourline-risk", "work": None, "done": None, "snooze": None, "rev": "dc1"}] + model["due"]
    model["upcoming"] = [u for u in model["upcoming"] if "harbourline-risk" not in u["id"]] + [
        dict(next(u for u in model["upcoming"] if u["id"] == "up-dl-app-quayside-demand"), id="up-app-harbourline-risk-choose-1",
             kind="deadline", title="Choose your day: Second interview, Harbourline Bank", day="2026-10-27",
             note="Offered Thu 29 or Fri 30 Oct. Tell them the day you choose.", offered=["2026-10-29", "2026-10-30"],
             go={"to": "interviews", "item": "int-harbourline-risk"})]
    return model


def test_a_day_to_choose_is_on_to_do_the_card_and_the_strip_and_one_tap_books_it(run, tmp_path):
    # Interviews 2 and 4: the choice reached no list, and its card had no way to give the day.
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": "#main"},
        {"click": "Choose the day", "exact": True, "read": "dialog"},
        {"click": "Thu 29 Oct", "exact": True},
        {"hash": "interviews/int-harbourline-risk", "read": "#main article[data-item=\"int-harbourline-risk\"]"},
        {"hash": "brief", "eval": "!!document.querySelector('[data-k=\"week:2026-10-30\"] i.offered')"},
    ], model=_offered_model())
    assert "Harbourline Bank: choose your interview day and tell them" in got["after"][0]["text"]
    assert "Thu 29 Oct" in got["after"][1]["dialog"] and "Fri 30 Oct" in got["after"][1]["dialog"]
    a = _acts(got, "outcome.interview")
    assert a and a[0]["item"] == "int-harbourline-risk" and a[0]["value"]["on"] == "2026-10-29"
    assert got["after"][4]["eval"] is True


def test_a_refused_booking_says_why_never_that_it_changed(run, tmp_path):
    # Interviews 2: "Not done: this changed since you saw it" over a booking refused for a
    # missing day.
    seed = {"actions/act~iv-book": {"item": "int-larkspur-supply", "action": "outcome.interview",
                                    "value": {"on": "2026-11-31", "stage": "Final round"}, "at": "2026-10-25T08:00:00Z"},
            "receipts/act~iv-book": {"applied_at": "2026-10-25T08:30:00Z", "result": "conflict",
                                     "note": "2026-11-31 is not a day: give it as 2026-10-25."}}
    got = _go(run, tmp_path, [{"hash": "interviews/int-larkspur-supply", "read": "#main article[data-item=\"int-larkspur-supply\"]"}], seed=seed)
    text = got["after"][0]["text"]
    assert "Not done: 2026-11-31 is not a day" in text and "changed since you saw it" not in text, text


def test_an_interview_card_with_days_offered_says_them_and_chooses_from_the_card(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-harbourline-risk", "read": "#main article[data-item=\"int-harbourline-risk\"]"},
    ], model=_offered_model())
    text = got["after"][0]["text"]
    assert "They offer Thu 29 Oct or Fri 30 Oct" in text and "tell them by Tue 27 Oct" in text and "Choose the day" in text, text


# ------------------------------------------------------------------ one convention for a time (interviews 5, 20; top 30, 14)


@pytest.mark.parametrize("device, here", [("Europe/London", "14:00"), ("America/Vancouver", None), ("America/Toronto", None)])
def test_a_time_is_said_in_the_persons_zone_with_the_devices_beside_it(run, tmp_path, device, here):
    model = _sample()
    model["person"]["time_zone"] = "America/Toronto"
    iv = next(i for i in model["interviews"] if i["id"] == "int-larkspur-supply")
    iv["when"] = "2026-10-28T14:00:00Z"           # 10:00 in Toronto, still on summer time
    up = next(u for u in model["upcoming"] if u["id"].startswith("up-app-larkspur"))
    up.update(start="2026-10-28T14:00:00Z", end="2026-10-28T14:30:00Z")
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-larkspur-supply", "read": "#main article[data-item=\"int-larkspur-supply\"]"},
        {"hash": "jobs", "eval": "(() => { const d = document.createElement('div'); return window.LJS && 1; })()"},
    ], model=model, zone=device)
    card = got["after"][0]["text"]
    assert "10:00" in card, card
    if device == "America/Toronto":
        assert "here)" not in card
    elif device == "Europe/London":
        assert "10:00 Toronto time (" + here + " here)" in card, card
    else:
        assert "Toronto time (" in card and "here)" in card


def test_with_no_zone_named_the_page_uses_the_devices_and_asks_for_one(run, tmp_path):
    model = _sample()
    model["person"]["time_zone"] = ""
    model["settings"] = model["settings"] + [{"id": "setting-time_zone", "key": "time_zone", "label": "Your time zone", "kind": "text",
                                              "value": "", "choices": None, "rev": "tz0"}]
    model["needs_you"] = [{"id": "q-time-zone", "kind": "question", "title": "Which time zone are you in?",
                           "body": "Your interviews, calls and calendar links use it.", "options": [{"label": "Say where you are", "action": "setting.set", "input": "text"}],
                           "about": {}, "rev": "qtz"}] + model["needs_you"]
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": "#main"},
        {"click": "Say where you are", "exact": True},
        {"fill": {"Say where you are": "Toronto"}, "submit": True},
        {"hash": "interviews/int-larkspur-supply", "read": "#main article[data-item=\"int-larkspur-supply\"]"},
    ], model=model, zone="America/Vancouver")
    assert "Which time zone are you in?" in got["after"][0]["text"]
    a = _acts(got, "setting.set")
    assert a and a[0]["item"] == "q-time-zone" and a[0]["value"] == "Toronto"
    # Meanwhile the device's own zone: 13:00Z on 28 October is 06:00 in Vancouver.
    assert "6:00" in got["after"][3]["text"] and "here)" not in got["after"][3]["text"]


def test_settings_says_your_time_zone_apart_from_the_brief(run, tmp_path):
    model = _sample()
    model["settings"] = model["settings"] + [{"id": "setting-time_zone", "key": "time_zone", "label": "Your time zone", "kind": "text",
                                              "value": "Toronto", "choices": None, "rev": "tz1"}]
    got = _go(run, tmp_path, [{"hash": "settings", "read": "#main"}], model=model)
    assert "Your time zone" in got["after"][0]["text"] and "Toronto" in got["after"][0]["text"]


# ------------------------------------------------------------------ Coming up (interviews 13, 21, 24)


def test_something_added_stays_in_coming_up_once_claude_has_saved_it(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Add something", "exact": True},
        {"click": "Something else: a call, a test, a careers fair", "exact": True},
        {"fill": {"What it is": "Coffee with Ivo", "The time": "14:00"}, "submit": True, "read": "#main"},
        {"receipts": True, "read": "#main"},
    ])
    a = _acts(got, "upcoming.add")[0]
    assert a["value"]["time"] == "14:00" and a["value"]["zone"] == "Europe/London"
    assert "Coffee with Ivo" in got["after"][2]["text"]
    assert "Coffee with Ivo" in got["after"][3]["text"], "the row stays once its receipt is in"


def test_an_interview_booked_here_is_in_coming_up_at_once(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Add something", "exact": True},
        {"click": "An interview", "exact": True},
        # A few applications: a button each, the one tapped going straight on (DESIGN.md).
        {"click": "Senior Supply Chain Analyst at Larkspur Retail", "within": "dialog", "exact": True},
        {"wait": 100},
        {"fill": {"Which stage": "Final round", "The day": "2026-11-03", "The time": "2pm ET"}, "submit": True, "read": "#main"},
    ])
    a = _acts(got, "outcome.interview")[0]
    assert a["value"]["on"] == "2026-11-03" and a["value"]["time"] == "2pm ET" and a["value"]["zone"] == "Europe/London"
    assert "Final round" in got["after"][4]["text"]


def test_a_round_that_has_ended_leaves_coming_up_that_evening(run, tmp_path):
    model = _sample()
    got = _go(run, tmp_path, [{"hash": "interviews", "read": "#main"}], model=model, clock="2026-10-28T22:30:00Z")
    assert "Phone screen: Larkspur Retail" not in got["after"][0]["text"]


def test_the_briefs_coming_up_never_lists_a_late_follow_up(run, tmp_path):
    # Interviews 24: with the one thing booked leading Today, Coming up listed follow-ups days
    # late, under a line about the next two weeks the phone's strip did not show.
    model = _sample()
    model["upcoming"] = [u for u in model["upcoming"] if u["id"].startswith("up-app-larkspur")]
    model["interviews"] = [i for i in model["interviews"] if i["id"] == "int-larkspur-supply"]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[document.querySelectorAll('.bp-up-due').length, "
                                                       "(document.querySelector('[data-k=\"bp:upcoming\"] .bp-body') || {}).innerText || '']"}],
              model=model, clock="2026-10-28T09:00:00Z")
    count, text = got["after"][0]["eval"]
    assert count == 0 and "Nothing else booked." in text and "Nothing booked in the next two weeks" not in text


# ------------------------------------------------------------------ the interview card (interviews 7, 14, 17, 22, 26)


def test_the_interview_bin_offers_a_move_before_an_end_and_a_move_keeps_it(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-larkspur-supply", "click": "Not going ahead: Larkspur Retail", "exact": True, "read": "dialog"},
        {"click": "It was moved or cancelled", "exact": True},
        {"submit": True},
    ])
    assert "It was moved or cancelled" in got["after"][0]["dialog"] and "They said no" in got["after"][0]["dialog"]
    a = _acts(got, "outcome.interview")
    assert a and a[0]["value"]["moved"] is True and a[0]["value"]["on"] == ""


def test_i_heard_back_records_against_the_interviews_own_application(run, tmp_path):
    model = _sample()
    # A second role at the same employer, listed first: found by the employer's name, the answer
    # went to it.
    other = dict(next(a for a in model["applications"] if a["id"] == "app-larkspur-supply"), id="app-larkspur-other",
                 role="Buyer", rev="apX")
    model["applications"] = [other] + model["applications"]
    iv = next(i for i in model["interviews"] if i["id"] == "int-larkspur-supply")
    iv["when"] = "2026-10-24T13:00:00Z"
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-larkspur-supply", "click": "I heard back from Larkspur Retail", "exact": True},
        {"click": "Not this time", "role": "radio", "exact": True},
        {"submit": True},
    ], model=model)
    a = _acts(got, "outcome.rejected")
    assert a and a[0]["item"] == "app-larkspur-supply"


def test_a_prep_for_an_earlier_plan_of_rounds_says_so_on_its_card(run, tmp_path):
    model = _sample()
    iv = next(i for i in model["interviews"] if i["id"] == "int-larkspur-supply")
    iv["prep"] = dict(iv["prep"], stale=True)
    got = _go(run, tmp_path, [{"hash": "interviews/int-larkspur-supply", "read": "#main article[data-item=\"int-larkspur-supply\"]",
                               "eval": "[...document.querySelectorAll('#main article[data-item=\"int-larkspur-supply\"] .btn.primary')].map((b) => b.textContent)"}],
              model=model)
    assert "Prep is for an earlier plan of rounds" in got["after"][0]["text"] and "Prep ready" not in got["after"][0]["text"]
    assert got["after"][0]["eval"] == ["Update my prep"]


def test_i_have_an_interview_lists_those_interviewing_first_in_one_list(run, tmp_path):
    model = _sample()
    apps = [dict(model["applications"][0], id="app-many-%d" % n, role="Analyst role %d" % n, company="Fernhill Freight",
                 status="applied", rev="m%d" % n) for n in range(60)]
    model["applications"] = model["applications"] + apps
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Add something", "exact": True},
        {"click": "An interview", "exact": True, "read": "dialog",
         "eval": "(() => { const s = document.querySelector('dialog select'); return s ? [s.querySelectorAll('option').length, s.querySelector('optgroup').label, document.querySelectorAll('dialog input[type=radio]').length] : null; })()"},
    ], model=model)
    got_ = got["after"][1]["eval"]
    assert got_ and got_[1] == "Interviewing now" and got_[2] == 0 and got_[0] > 60


def test_the_calendar_sheet_says_a_phone_gets_a_zip_and_what_is_quicker(run, tmp_path):
    # Interviews 27: a page may save a zip, never an .ics, and a phone shows it as a zip.
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Add to your calendar: Phone screen: Larkspur Retail", "exact": True, "read": "dialog"},
    ])
    assert "On a phone it arrives as a zip, so Google Calendar or Copy the details is quicker there." in got["after"][0]["dialog"]


def test_what_was_sent_is_said_even_with_no_file_name(run, tmp_path):
    # Interviews 28: a resume logged with no file name was left out of What you sent.
    model = _sample()
    iv = next(i for i in model["interviews"] if i["id"] == "int-larkspur-supply")
    iv["sent_files"] = [{"kind": "resume", "name": None, "path": None, "asset": None, "to": "Juno", "on": "2026-10-20"}]
    got = _go(run, tmp_path, [{"hash": "interviews/int-larkspur-supply", "click": "Read your prep for your phone screen with Larkspur Retail",
                               "exact": True, "read": "body"}], model=model)
    assert "Your CV, to Juno, 20 Oct" in got["after"][0]["text"] or "Your CV, to Juno, Tue 20 Oct" in got["after"][0]["text"], got["after"][0]["text"][-800:]


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_coming_up_reads_your_prep_with_the_pill_to_do_has(run, tmp_path, vp):
    # The UX review of 2026-11-10 (U-12): the night before, the key action in Coming up was a
    # small underlined "Prep ready" while To do called it "Read your prep". It is the row's pill,
    # in the same words, and Prepare me is a pill too.
    look = ("[...document.querySelectorAll('#main .up-prep .btn')].map((b) => [b.textContent.trim(), b.classList.contains('link')])")
    got = _go(run, tmp_path, [{"hash": "interviews", "eval": look}, {"hash": "todo", "eval": (
        "[...document.querySelectorAll('#main [data-item=\"soon:int-larkspur-supply\"] .card-actions .btn')].map((b) => b.textContent.trim())")}], vp=vp)
    rows, todo = got["after"][0]["eval"], got["after"][1]["eval"]
    assert ["Read your prep", False] in rows and ["Prepare me", False] in rows, rows
    assert "Prep ready" not in [r[0] for r in rows] and not any(link for _t, link in rows), rows
    assert "Read your prep" in todo, todo
