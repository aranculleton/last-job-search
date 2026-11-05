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
    assert asked[0]["args"] == {"count": 5, "note": "Product teams in logistics"}, asked[0]
    assert asked[0]["title"] == "People: Product teams in logistics", asked[0]["title"]


def test_find_people_left_empty_looks_at_the_employers_wanted(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "head-find-people"},
        {"submit": True, "ready": "!document.querySelector('dialog[open]')"},
    ], PHONE, clock=T)
    asked = [w for w in got["work"] if w["kind"] == "network"]
    assert len(asked) == 1 and asked[0]["args"] == {"count": 5} and asked[0]["title"] == "People at the employers you want", asked


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
    """Find jobs is the search going ("Finding jobs") while it runs, and the header carries no
    line of its own about it: the work pill and the button say it (2026-11-05)."""
    got = _go(run, tmp_path, [{"hash": "jobs", "read": "#main .sec-head", "eval": PLAIN}], PHONE,
              seed={"work/search~1": _work("search", "Finding jobs")}, clock=T)
    head = got["after"][0]["text"]
    assert got["after"][0]["eval"] == 0 and "Finding jobs" in head, head
    assert "Searching now" not in head and "Claude is on it" not in head, head
    assert [w["kind"] for w in got["work"]] == ["search"]


# Jobs and Coming up left this list on 2026-11-05: their headers say nothing of Claude's
# work (below).
@pytest.mark.parametrize("screen,kind,title", [
    ("profile", "profile", "A change to your profile"),
])
def test_each_screen_says_when_claude_is_working_on_it(run, tmp_path, screen, kind, title):
    count = "document.querySelectorAll('#main .running-here').length"
    got = _go(run, tmp_path, [{"hash": screen, "eval": count}, {"hash": "progress", "eval": count}], PHONE,
              seed={"work/" + kind + "~1": _work(kind, title)}, clock=T)
    here, elsewhere = got["after"]
    assert here["eval"] == 1 and "Claude is on it: " + title + "." in here["text"], here["text"][:400]
    assert "See how it is going" in here["text"]
    assert elsewhere["eval"] == 0, "the line is on the screen whose work it is, nowhere else"


TOOLS = """[document.querySelectorAll('#main .running-here').length,
  [...document.querySelectorAll('#main .sec-head .head-tools .btn')].map((b) => [b.textContent.replace(/\\s+/g, ' ').trim(), b.classList.contains('link')]),
  document.querySelectorAll('#main .sec-head .sum-small .btn.link').length]"""


@pytest.mark.parametrize("tab", ["To apply", "Applied"])
def test_jobs_header_says_nothing_of_claudes_work_and_its_tools_are_pills(run, tmp_path, tab):
    """Jobs' header, on both its tabs, carried "Claude is on it: ..." under the summary and a
    small underlined line ("Add a job · Your CV"): the header's work pill and each card's own
    line say what Claude is doing, and Add a job and your CV are soft pills beside Find jobs, as
    Contacts' Paste a message beside Find people (the maintainer, 2026-11-05)."""
    got = _go(run, tmp_path, [{"hash": "jobs", "click": tab, "read": "#main .sec-head", "eval": TOOLS}], PHONE,
              seed={"work/draft~1": _work("draft", "Drafts for 2 roles")}, clock=T)
    lines, tools, links = got["after"][0]["eval"]
    head = got["after"][0]["text"]
    assert lines == 0 and "Claude is on it" not in head and "See how it is going" not in head, head
    assert [t for t, _ in tools][-2:] == ["Add a job", "Your CV"] and not any(link for _, link in tools), tools
    assert links == 0, ("no small underlined line under the summary", head)


def test_contacts_says_claude_is_working_on_a_reply_on_that_persons_card(run, tmp_path):
    """Contacts has no line of its own for Claude's work since 2026-11-04 (the maintainer: the
    header's work pill and each card's own line already say it): the reply to Juno says so on
    Juno's card, and nowhere else on the screen."""
    work = dict(_work("reply", "A reply to Juno"), args={"contact": "larkspur_retail_castellan"})
    line = "(document.querySelector('#main [data-item=\"larkspur_retail_castellan\"] .going') || {}).textContent || ''"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": "[document.querySelectorAll('#main .running-here').length, " + line + "]"}],
              PHONE, seed={"work/reply~1": work}, clock=T)
    lines, said = got["after"][0]["eval"]
    assert lines == 0 and said.strip().startswith("Claude is on it"), (lines, said)


def test_coming_up_has_no_line_of_its_own_for_claudes_work(run, tmp_path):
    """As Contacts (2026-11-04): the header's work pill and each row's own line say what Claude
    is doing, never a third line of the header (the UX review, 2026-11-05)."""
    count = "document.querySelectorAll('#main .running-here').length"
    got = _go(run, tmp_path, [{"hash": "interviews", "eval": count}], PHONE,
              seed={"work/prep~int-harbourline-risk": _work("prep", "Prep for the second interview")}, clock=T)
    assert got["after"][0]["eval"] == 0, got["after"][0]["text"][:300]
    assert "Preparing your prep" in got["after"][0]["text"], "its own row says it"


def test_two_things_running_on_one_screen_are_counted_and_finished_work_is_not(run, tmp_path):
    seed = {"work/profile~1": _work("profile", "A change"), "work/profile~2": _work("profile", "Another change", status="queued"),
            "work/profile~3": _work("profile", "A third", status="done", finished_at=T)}
    got = _go(run, tmp_path, [{"hash": "profile", "eval": "document.querySelector('#main .running-here').getAttribute('data-running')"}],
              PHONE, seed=seed, clock=T)
    # "Claude is on it" only for work Claude has begun (2026-11-03): the thank-you not yet picked
    # up waits, and says so, still counted.
    assert got["after"][0]["eval"] == "2" and "Claude is on 1 thing here, 1 more waiting." in got["after"][0]["text"], got["after"][0]["text"][:300]


def test_the_bin_on_a_to_do_row_takes_the_row_away_as_it_is_chosen(run, tmp_path, vp):
    # The bin on "Did your note to ... go?" said the employer was not wanted and the row stayed
    # until a chat applied it (the maintainer, 2026-10-29): it goes, with the person's other rows.
    # Asked first of the quick answers here, so its card's bin is hers (2026-11-05).
    row = "document.querySelector('#main [data-q=\"q-sent-fernhill_freight_halloway\"]')"
    due = "document.querySelector('#main [data-item=\"due-fernhill-nudge\"]')"
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "[!!" + row + ", !!" + due + "]"},
        {"click": "Not Wren?", "within": "#main [data-q=\"q-sent-fernhill_freight_halloway\"]"},
        # The choice is the tap that does it (2026-11-03); the next step only reads.
        {"click": "Not interested in Fernhill Freight any more", "within": "dialog"},
        {"ready": "!" + row + " && !" + due, "eval": "[!!" + row + ", !!" + due + "]"},
    ], vp, model=_sent_first(_sample()), clock=T)
    assert got["after"][0]["eval"] == [True, True], "the row and its follow-up were there to bin"
    assert got["after"][3]["eval"] == [False, False]
    a = _one(got, "person.stop")
    assert a["item"] == "fernhill_freight_halloway"
    assert a["value"]["scope"] == "employer" and a["value"]["employer"] == "Fernhill Freight", a["value"]


def _sent_first(model):
    # "Did your note to Wren go?" first of the quick answers, so it is the one showing.
    model["needs_you"].sort(key=lambda n: not n["id"].startswith("q-sent-"))
    return model


def test_the_bin_for_one_person_leaves_the_rest_of_their_employer(run, tmp_path):
    row = "document.querySelector('#main [data-q=\"q-sent-fernhill_freight_halloway\"]')"
    title = "(document.querySelector('#main [data-item=\"quick\"] .card-title') || {}).textContent || ''"
    got = _go(run, tmp_path, [
        {"hash": "todo"},
        {"click": "Not Wren?", "within": "#main [data-q=\"q-sent-fernhill_freight_halloway\"]"},
        # The choice is the tap that does it (2026-11-03); the next step only reads.
        {"click": "Don't contact Wren", "within": "dialog"},
        {"ready": "!" + row, "eval": title},
    ], PHONE, model=_sent_first(_sample()), clock=T)
    a = _one(got, "person.stop")
    assert a["value"]["scope"] == "person", a["value"]
    # The application question about the same employer is not the person's, so it stays: three
    # quick answers left of four ("Did you apply to Fernhill Freight?" among them).
    assert got["after"][3]["eval"] == "3 quick answers", got["after"][3]["eval"]


def test_contacts_counts_only_who_needs_the_person_and_the_follow_ups_apart(run, tmp_path):
    # 418 people "needed" the person when every follow-up due this week counted (the
    # maintainer, 2026-10-29: "do 418 people really need me?"). A follow-up they could send is
    # counted as one, never as someone waiting on them.
    model = _sample()
    model["needs_you"] = []
    model["due"] = []
    # Where each stands is the engine's answer (app_model.standing, 2026-11-03): four with a
    # follow-up due, one waiting. The page counts what the engine says, never dates of its own.
    model["people"] = [
        {"id": "p-" + str(i), "first_name": n, "employer": "Tidewell Logistics", "status": "awaiting_reply",
         "group": "follow", "last": "2026-10-10", "next_action": "One nudge if no reply", "due": "2026-10-25", "rev": "r" + str(i)}
        for i, n in enumerate(["Ilse", "Bram", "Corin", "Dace"])
    ] + [{"id": "p-wait", "first_name": "Esk", "employer": "Tidewell Logistics", "status": "awaiting_reply",
          "group": "waiting", "last": "2026-10-20", "due": "2026-11-20", "rev": "rw"}]
    # Nothing drafted, so the header is about people alone (the sample's drafts are to others).
    model["messages"] = []
    shown = "[...document.querySelectorAll('#main ul.people > li[data-item]')].map((l) => l.dataset.item)"
    got = _go(run, tmp_path, [{"hash": "contacts", "read": "#main .sec-head"}, {"eval": shown}], PHONE, model=copy.deepcopy(model), clock=T)
    head = got["after"][0]["text"]
    assert "Nobody is waiting on you." in head, head
    assert "need you" not in head, head
    # The header is one short line since 2026-11-04 (the maintainer: "quite cluttered"): the
    # four follow-ups are their own cards up front, never counted as people who need you; the
    # one waiting is below the fold.
    assert got["after"][1]["eval"] == ["p-0", "p-1", "p-2", "p-3"], got["after"][1]["eval"]


def _q(item):
    # A question is on the quick answers card by its id (data-q); a row by its own.
    at = "data-q" if item.startswith("q-") else "data-item"
    return "!!document.querySelector('#main [" + at + "=\"" + item + "\"]')"


def _fernhill():
    # Two more rows at the employer: one for a person nobody has written to yet, one for a
    # person already in a conversation; and a reply owed to the person whose row is binned.
    model = _sent_first(_sample())
    base = next(d for d in model["due"] if d["id"] == "due-fernhill-nudge")
    model["people"].append({"id": "fernhill_freight_tamsin", "first_name": "Tamsin", "employer": "Fernhill Freight",
                            "status": "not_contacted", "rev": "p-tamsin"})
    for did, cid, kind in [("due-fernhill-tamsin", "fernhill_freight_tamsin", "nudge"),
                           ("due-fernhill-odile", "fernhill_freight_odile", "nudge"),
                           ("due-fernhill-reply", "fernhill_freight_halloway", "reply")]:
        model["due"].append(dict(copy.deepcopy(base), id=did, contact=cid, kind=kind, item="msg-" + did))
    return model


def _bin(choice):
    rows = "[" + ", ".join(_q(i) for i in ["q-sent-fernhill_freight_halloway", "due-fernhill-nudge", "due-fernhill-tamsin",
                                           "due-fernhill-odile", "due-fernhill-reply"]) + "]"
    return [{"hash": "todo", "eval": rows},
            {"click": "Not Wren?", "within": "#main [data-q=\"q-sent-fernhill_freight_halloway\"]"},
            # The choice is the tap that does it (2026-11-03); the next step only reads.
            {"click": choice, "within": "dialog"},
            {"ready": _q("q-sent-fernhill_freight_halloway")[1:], "eval": rows}]


def test_the_bin_for_an_employer_takes_away_every_row_there(run, tmp_path):
    # "No more from" an employer takes everyone there out of To do, a colleague already written
    # to as well; their thread stays in Contacts (the maintainer, 2026-11-05: "i trashed aviva
    # and said no more from that one" while a reply owed there was still in Next). Before, the
    # page hid only the people nobody had written to yet.
    got = _go(run, tmp_path, _bin("Not interested in Fernhill Freight any more"), PHONE, model=_fernhill(), clock=T)
    # The reply owed to Wren is the same draft as her follow-up: one row for her on the messages
    # card (one row a person, 2026-11-05), under the follow-up's id.
    assert got["after"][0]["eval"] == [True, True, True, True, False], got["after"][0]["eval"]
    assert got["after"][3]["eval"] == [False, False, False, False, False], got["after"][3]["eval"]


def test_in_touch_another_way_drops_the_note_and_keeps_a_reply_they_are_owed(run, tmp_path):
    got = _go(run, tmp_path, _bin("Already in touch another way"), PHONE, model=_fernhill(), clock=T)
    assert _one(got, "person.stop")["value"]["scope"] == "other"
    assert got["after"][3]["eval"] == [False, False, True, True, True], got["after"][3]["eval"]


def _ended(status):
    model = _sample()
    next(i for i in model["interviews"] if i["id"] == "int-harbourline-risk")["status"] = status
    seed = {"actions/act~iv-end": {"item": "int-harbourline-risk", "action": "outcome.no_response", "value": {"on": "2026-10-20"},
                                   "at": "2026-10-20T09:00:00Z"},
            "receipts/act~iv-end": {"applied_at": "2026-10-20T10:00:00Z", "result": "ok"}}
    card = "!!document.querySelector('#main article[data-item=\"int-harbourline-risk\"]')"
    return model, seed, card


def test_an_interview_ended_on_the_page_comes_back_when_a_chat_books_a_new_stage(run, tmp_path):
    # The end hid the interview for good, so a stage a chat booked afterwards on the same
    # application never showed. Once the chat has saved the end, the record decides.
    for status, shown in [("no_response", False), ("interview", True)]:
        model, seed, card = _ended(status)
        got = _go(run, tmp_path, [{"hash": "interviews/int-harbourline-risk", "eval": card}], PHONE, model=model, seed=seed, clock=T)
        assert got["after"][0]["eval"] is shown, (status, got["after"][0]["text"][:300])
