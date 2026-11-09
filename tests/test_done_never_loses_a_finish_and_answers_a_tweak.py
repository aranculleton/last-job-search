"""`app.py done` keeps each finish, and answers a change asked with a card's pencil.

The maintainer's copy, 2026-11-09. Every `done` wrote its batch to the same out/finish.json:
finishing two items one after another before sending the first lost the first item's update,
while the dump already said it had finished, so `done` refused it again ("already finished")
and `wake` went on to claim items the page had finished, with old versions. And a plain
written answer to a tweak (a change asked with a message's pencil) was refused with "Name its
thread", because a tweak has none: the chat had to turn its answer into a question. Every
person and employer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import page_db  # noqa: E402
from test_every_work_move_is_a_command_pinned_to_its_read import (  # noqa: E402
    T, claimed_batch, db_of, dump_dir, entries)


def test_two_finishes_one_after_another_keep_both_batches(tmp_path):
    d = claimed_batch(tmp_path)
    out = str(tmp_path / "out")
    first = page_db.finish(page_db.load(d), "draft~two", T("17:20"), out,
                           summary="Drafted the resume and letter for Quillon Data.",
                           chat="session_job", dump_dir=d)
    second = page_db.finish(page_db.load(d), "draft~three", T("17:21"), out,
                            summary="Drafted the resume and letter for Fernhill Freight.",
                            chat="session_job", dump_dir=d)
    assert set(first["batches"]).isdisjoint(second["batches"]), (first, second)
    # Both are still there to send, each with its own item's update.
    a = {e["doc_id"] for e in entries(first["batches"])}
    b = {e["doc_id"] for e in entries(second["batches"])}
    assert "draft~two" in a and "draft~three" in b, (a, b)
    for p in first["batches"] + second["batches"]:
        name = os.path.basename(p)
        assert all(c.isalnum() or c in "-_." for c in name), name   # a name Windows takes


def _tweak_db(talk=None):
    item = {"kind": "tweak", "status": "running", "to": "either", "claimed_by": "session_job",
            "title": "Change the note to Juno", "created_at": "2026-11-03T16:59:00Z",
            "args": {"v": 1, "text": "Make it shorter and drop the second sentence.",
                     "target": {"id": "msg-larkspur_retail_castellan", "output": "message",
                                "contact": "larkspur_retail_castellan"}},
            "stages": page_db.progress("tweak")["stages"]}
    db = db_of({"tweak~msg-larkspur_retail_castellan~1": (item, 4)})
    if talk is not None:
        db["talk"] = {page_db.card_thread("message", "msg-larkspur_retail_castellan"): {"data": talk, "version": 2}}
    return db


def test_a_written_answer_to_a_tweak_goes_under_its_card(tmp_path):
    db = _tweak_db()
    d = dump_dir(str(tmp_path / "d"), db)
    wid = "tweak~msg-larkspur_retail_castellan~1"
    got = page_db.finish(page_db.load(d), wid, T("17:10"), str(tmp_path / "o"),
                         summary="Answered your question about the note to Juno.",
                         reply="The second sentence is the only line that says why you are writing, "
                               "so I kept it and cut the opening instead.",
                         chat="session_job", dump_dir=d)
    th = page_db.card_thread("message", "msg-larkspur_retail_castellan")
    # The page's own name for the card's thread (app.js cardThread: "card-" + seg(kind-id)).
    assert th == "card-message-msg-larkspur_retail_castellan"
    assert got["thread"] == th
    body = entries(got["batches"])
    head = next(e for e in body if e["collection"] == "talk" and e["doc_id"] == th)
    assert head["body"]["card"] == {"kind": "message", "id": "msg-larkspur_retail_castellan",
                                    "label": "the note to Juno"}, head
    said = [e["body"] for e in body if e["collection"] == f"talk/{th}/messages"]
    assert [m["from"] for m in sorted(said, key=lambda m: m["at"])] == ["you", "cloud"], said
    assert said and any(m["text"].startswith("Make it shorter") for m in said)
    item = next(e for e in body if e["collection"] == "work")["body"]
    assert item["status"] == "done"


def test_a_tweak_on_a_card_that_already_has_a_thread_keeps_it(tmp_path):
    db = _tweak_db(talk={"to": "either", "card": {"kind": "message", "id": "msg-larkspur_retail_castellan",
                                                   "label": "the message to Juno"},
                         "title": "About the message to Juno", "created_at": "2026-11-01T09:00:00Z"})
    d = dump_dir(str(tmp_path / "d"), db)
    got = page_db.finish(page_db.load(d), "tweak~msg-larkspur_retail_castellan~1", T("17:10"),
                         str(tmp_path / "o"), summary="Answered your question about the note to Juno.",
                         reply="Done as asked.", chat="session_job", dump_dir=d)
    th = page_db.card_thread("message", "msg-larkspur_retail_castellan")
    head = next(e for e in entries(got["batches"]) if e["collection"] == "talk" and e["doc_id"] == th)
    assert head["op"] == "update" and head.get("if_version") == 2, head


def test_a_tweak_with_no_card_still_asks_for_its_thread(tmp_path):
    db = _tweak_db()
    db["work"]["tweak~msg-larkspur_retail_castellan~1"]["data"]["args"]["target"] = {"id": "jobs", "output": "jobs"}
    d = dump_dir(str(tmp_path / "d"), db)
    try:
        page_db.finish(page_db.load(d), "tweak~msg-larkspur_retail_castellan~1", T("17:10"),
                       str(tmp_path / "o"), summary="Searched again.", reply="Searched again.",
                       chat="session_job", dump_dir=d)
    except ValueError as e:
        assert "thread" in str(e)
    else:
        raise AssertionError("a tweak with no card has no thread to answer in")
