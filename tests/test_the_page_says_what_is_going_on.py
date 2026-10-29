"""The page says what Claude is doing, and what it does is not asked for twice (the maintainer,
2026-10-29).

Each screen whose work is running says so at its head; Find jobs and Find people turn into what
is going while a run is, so a second tap never starts a second run; Find people takes a note in
the person's own words, as Find jobs does; the bin on a To do row takes the row away as it is
chosen; and Contacts counts as needing the person only those who do, with the follow-ups they
could send counted apart. Every person and employer here is invented.
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _one, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _work(kind, title, status="running", **extra):
    doc = {"kind": kind, "title": title, "to": "cloud", "args": {}, "asked_at": T, "status": status,
           "claimed_by": "cloud-1" if status == "running" else None, "claimed_at": T if status == "running" else None,
           "stages": [{"name": "Getting started", "est_s": 60}, {"name": "Working", "est_s": 600}],
           "stage": 1, "stage_at": T, "steps": [], "stop_asked": False, "attempt": 1}
    doc.update(extra)
    return doc


def test_find_people_takes_a_note_in_the_person_s_words_as_find_jobs_does(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "head-find-people"},
        {"fill": {"Anything different this time?": "Product teams in logistics"}, "submit": True,
         "ready": "!document.querySelector('dialog[open]')"},
    ], vp, clock=T)
    asked = [w for w in got["work"] if w["kind"] == "network"]
    assert len(asked) == 1, asked
    assert asked[0]["args"] == {"note": "Product teams in logistics"}, asked[0]
    assert asked[0]["title"] == "People: Product teams in logistics", asked[0]["title"]


def test_find_people_left_empty_looks_at_the_employers_wanted(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "head-find-people"},
        {"submit": True, "ready": "!document.querySelector('dialog[open]')"},
    ], PHONE, clock=T)
    asked = [w for w in got["work"] if w["kind"] == "network"]
    assert len(asked) == 1 and asked[0]["args"] == {} and asked[0]["title"] == "People at the employers you want", asked


PLAIN = "[...document.querySelectorAll('#main button')].filter((b) => /^(Find people|Find jobs)$/.test(b.textContent.trim())).length"


def test_a_people_run_going_turns_find_people_into_what_is_going_and_never_starts_a_second(run, tmp_path, vp):
    going = "[...document.querySelectorAll('#main button')].filter((b) => b.textContent.trim().startsWith('Finding people')).length"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": "[" + PLAIN + ", " + going + "]"}, {"open": "head-find-people:going"}],
              vp, seed={"work/network~1": _work("network", "People at the employers you want")}, clock=T)
    plain, shown = got["after"][0]["eval"]
    assert plain == 0 and shown >= 1, got["after"][0]["text"][:400]
    # Tapping it shows the work; nothing new is asked for.
    assert [w["kind"] for w in got["work"]] == ["network"], got["work"]


def test_a_search_going_takes_find_jobs_off_jobs_and_says_it_is_searching(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "jobs", "read": "#main .sec-head", "eval": PLAIN}], PHONE,
              seed={"work/search~1": _work("search", "Finding jobs")}, clock=T)
    assert got["after"][0]["eval"] == 0 and "Searching now" in got["after"][0]["text"], got["after"][0]["text"]
    assert [w["kind"] for w in got["work"]] == ["search"]


@pytest.mark.parametrize("screen,kind,title", [
    ("interviews", "prep", "Prep for the second interview"),
    ("contacts", "reply", "A reply to Juno"),
    ("jobs", "draft", "Drafts for 2 roles"),
])
def test_each_screen_says_when_claude_is_working_on_it(run, tmp_path, screen, kind, title):
    count = "document.querySelectorAll('#main .running-here').length"
    got = _go(run, tmp_path, [{"hash": screen, "eval": count}, {"hash": "progress", "eval": count}], PHONE,
              seed={"work/" + kind + "~1": _work(kind, title)}, clock=T)
    here, elsewhere = got["after"]
    assert here["eval"] == 1 and "Claude is on it: " + title + "." in here["text"], here["text"][:400]
    assert "See how it is going" in here["text"]
    assert elsewhere["eval"] == 0, "the line is on the screen whose work it is, nowhere else"


def test_two_things_running_on_one_screen_are_counted_and_finished_work_is_not(run, tmp_path):
    seed = {"work/prep~1": _work("prep", "Prep one"), "work/thank_you~1": _work("thank_you", "A thank-you", status="queued"),
            "work/prep~2": _work("prep", "Prep two", status="done", finished_at=T)}
    got = _go(run, tmp_path, [{"hash": "interviews", "eval": "document.querySelector('#main .running-here').getAttribute('data-running')"}],
              PHONE, seed=seed, clock=T)
    assert got["after"][0]["eval"] == "2" and "Claude is on 2 things here." in got["after"][0]["text"]


def test_the_bin_on_a_to_do_row_takes_the_row_away_as_it_is_chosen(run, tmp_path, vp):
    # The bin on "Did your note to ... go?" said the employer was not wanted and the row stayed
    # until a chat applied it (the maintainer, 2026-10-29): it goes, with the person's other rows.
    row = "document.querySelector('#main [data-item=\"q-sent-fernhill_freight_halloway\"]')"
    due = "document.querySelector('#main [data-item=\"due-fernhill-nudge\"]')"
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "[!!" + row + ", !!" + due + "]"},
        {"click": "Not Wren?", "within": "#main [data-item=\"q-sent-fernhill_freight_halloway\"]"},
        {"click": "Not interested in Fernhill Freight any more", "role": "radio"},
        {"submit": True, "ready": "!" + row + " && !" + due, "eval": "[!!" + row + ", !!" + due + "]"},
    ], vp, clock=T)
    assert got["after"][0]["eval"] == [True, True], "the row and its follow-up were there to bin"
    assert got["after"][3]["eval"] == [False, False]
    a = _one(got, "person.stop")
    assert a["item"] == "fernhill_freight_halloway"
    assert a["value"]["scope"] == "employer" and a["value"]["employer"] == "Fernhill Freight", a["value"]


def test_the_bin_for_one_person_leaves_the_rest_of_their_employer(run, tmp_path):
    row = "document.querySelector('#main [data-item=\"q-sent-fernhill_freight_halloway\"]')"
    got = _go(run, tmp_path, [
        {"hash": "todo"},
        {"click": "Not Wren?", "within": "#main [data-item=\"q-sent-fernhill_freight_halloway\"]"},
        {"click": "Don't contact Wren", "role": "radio"},
        {"submit": True, "ready": "!" + row},
    ], PHONE, clock=T)
    a = _one(got, "person.stop")
    assert a["value"]["scope"] == "person", a["value"]
    # The application question about the same employer is not the person's, so it stays.
    assert "Did you apply to Fernhill Freight?" in got["after"][3]["text"]


def test_contacts_counts_only_who_needs_the_person_and_the_follow_ups_apart(run, tmp_path):
    # 418 people "needed" the person when every follow-up due this week counted (the
    # maintainer, 2026-10-29: "do 418 people really need me?"). A follow-up they could send is
    # counted as one, never as someone waiting on them.
    model = _sample()
    model["needs_you"] = []
    model["due"] = []
    model["people"] = [
        {"id": "p-" + str(i), "first_name": n, "employer": "Tidewell Logistics", "status": "awaiting_reply",
         "last": "2026-10-10", "next_action": "One nudge if no reply", "due": "2026-10-25", "rev": "r" + str(i)}
        for i, n in enumerate(["Ilse", "Bram", "Corin", "Dace"])
    ] + [{"id": "p-wait", "first_name": "Esk", "employer": "Tidewell Logistics", "status": "awaiting_reply",
          "last": "2026-10-20", "due": "2026-11-20", "rev": "rw"}]
    got = _go(run, tmp_path, [{"hash": "contacts", "read": "#main .sec-head"}], PHONE, model=copy.deepcopy(model), clock=T)
    head = got["after"][0]["text"]
    assert "Nobody is waiting on you." in head, head
    assert "4 follow-ups you could send." in head, head
    assert "need you" not in head, head
