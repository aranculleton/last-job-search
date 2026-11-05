"""What the engine needs from the person names its kind of answer, so the page draws it.

A refusal that asked "Which day is it?" carried a text box at best, and "Say it in Chat" at
worst (the maintainer, 2026-11-05: "surely that one we could just have a date picker"). A
refused tap's receipt now names the kind of answer (`ask`: date with its time, time, number,
choice), a question Claude stops on names its kind too (`app.py done --question --answer`),
and the answer the page sends with it finishes the work. Every person and employer is
invented.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_actions  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402
from test_an_application_and_a_contact_have_a_life_on_the_page import LARKSPUR, _app  # noqa: E402
from test_every_work_move_is_a_command_pinned_to_its_read import claimed_batch, entries  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def test_a_day_that_is_not_a_day_asks_for_a_date_with_its_time_and_the_answer_books_it(search):
    a = _app(search, LARKSPUR)
    bad = search.act("outcome.interview", LARKSPUR, rev=a["rev"],
                     value={"stage": "Phone screen", "on": "next Thursday"})
    search.apply()
    r = search.receipt(bad)
    assert r["result"] == "conflict", r
    assert r["ask"] == {"key": "on", "label": "Which day is it?", "kind": "date", "type": "date",
                        "time": "time"}, r
    # The page's date picker and time, sent as the same tap again (askFix).
    search.written_back()
    good = search.act("outcome.interview", LARKSPUR, rev=a["rev"],
                      value={"stage": "Phone screen", "on": "2026-10-30", "time": "14:30"})
    got = search.apply()
    assert good in got["ok"], search.receipt(good)
    assert "phone screen booked for 2026-10-30 at 14:30" in \
        search.tracker_row("Larkspur Retail")["notes"].lower()


def test_a_time_that_cannot_be_read_asks_for_a_time(search):
    a = _app(search, LARKSPUR)
    aid = search.act("outcome.interview", LARKSPUR, rev=a["rev"],
                     value={"stage": "Phone screen", "on": "2026-10-30", "time": "after lunch"})
    search.apply()
    r = search.receipt(aid)
    assert r["result"] == "conflict" and r["ask"]["kind"] == "time" and r["ask"]["key"] == "time", r


def test_each_kind_of_answer_is_kept_whole_and_an_unknown_one_is_text():
    assert app_actions.ask("value", "Pay", "number")["kind"] == "number"
    yn = app_actions.ask("value", "Did it go?", "yesno")
    assert [c["value"] for c in yn["choices"]] == ["yes", "no"]
    sc = app_actions.clean_ask({"key": "answer", "kind": "scale"})
    assert (sc["min"], sc["max"]) == (1, 5)
    assert app_actions.clean_ask({"key": "answer", "kind": "colour"})["kind"] == "text"
    # A choice with one option is no choice: a line of text.
    assert app_actions.clean_ask({"key": "answer", "kind": "choice",
                                  "choices": [{"value": "a"}]})["kind"] == "text"
    with pytest.raises(ValueError):
        app_actions.ask("x", "x", "colour")
    # Every action an older refusal asked a question of has its answer to offer.
    for action, a in app_actions.OLD_REFUSAL_ASKS.items():
        assert action in app_actions.ACTIONS and a["kind"] == "date", action


def test_a_question_claude_stops_on_carries_its_kind_of_answer_and_the_words_it_is_about(tmp_path):
    d = claimed_batch(tmp_path)
    out = str(tmp_path / "q")
    assert app.main(["done", d, "--work", "draft~two", "--chat", "session_job",
                     "--question", "This line says you led the team. Keep it?",
                     "--about", "I led the pricing team at Harbourline",
                     "--answer", "choice", "--choice", "keep=Keep it", "--choice", "cut=Take it out",
                     "--out", out]) == 0
    body = entries(sorted(glob.glob(os.path.join(out, "*.json"))))
    item = next(e for e in body if e["doc_id"] == "draft~two")["body"]
    assert item["status"] == "needs_you" and item["note"] == "This line says you led the team. Keep it?"
    n = item["needs"]
    assert n["about"] == "I led the pricing team at Harbourline" and n["work"] == "draft~two", n
    assert n["answer"]["kind"] == "choice" and n["answer"]["choices"] == [
        {"value": "keep", "label": "Keep it"}, {"value": "cut", "label": "Take it out"}], n
    # Pages before 4.10 read the choices as their words alone.
    assert item["choices"] == ["Keep it", "Take it out"]


def test_a_question_with_no_kind_is_a_line_of_text(tmp_path):
    d = claimed_batch(tmp_path)
    got = page_db.finish(page_db.load(d), "draft~two",
                         dt.datetime(2026, 11, 3, 17, 20, tzinfo=dt.timezone.utc), str(tmp_path / "q"),
                         question="What did the recruiter call the team?", chat="session_job", dump_dir=d)
    item = next(e for e in entries(got["batches"]) if e["doc_id"] == "draft~two")["body"]
    assert item["needs"]["answer"]["kind"] == "text" and item["choices"] is None, item
