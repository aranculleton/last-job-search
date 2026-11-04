"""Contacts on the page, built by the engine from a search worked by the app's commands.

Walked through on 2026-11-03 (tests/test_someone_new_and_an_acceptance_are_recorded_by_command.py
holds the commands). What the page got wrong:

- It never showed a conversation: the engine wrote no `thread`, so "Your conversation" said
  only "Last in touch", and "Draft a reply" asked for their words again, which logged them a
  second time on another day.
- A thread at the limit of unanswered messages offered "Draft the follow-up" on its row (a
  third message the rule forbids) while To do offered "Close"; "Close" only cleared the line,
  and the summary counted it as a follow-up to send, while the fold said "nothing owed".
- A person with no employer read "Sam at"; a row named its person again ("Next: reply to Sam");
  first notes from a networking run reached To do nowhere, the engine never marking them a wave.

Every person and employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_someone_new_and_an_acceptance_are_recorded_by_command import (  # noqa: E402
    APP, NOW, SAM, TODAY, Book, book, lived_in)

PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1440, "height": 900}
_ = book   # the fixture, used by name


# ------------------------------------------------------------------ the page's model

def test_a_person_carries_their_conversation_with_no_contact_detail(book):
    lived_in(book)
    m = book.model()
    sam = next(p for p in m["people"] if p["id"] == "tate")
    assert sam["employer"] == "" and sam["wrote"] is False
    said = sam["thread"][-1]
    assert said["from"] == "them" and said["on"] == "2026-10-24"
    assert "\r" not in said["text"] and "open to a chat" in said["text"]
    assert "sam.tate@example.com" not in json.dumps(m) and "(an email address)" in said["text"]
    priya = next(p for p in m["people"] if p["id"] == "northwind_analytics_okafor")
    assert [t.get("event") for t in priya["thread"]] == [None, True]
    assert priya["thread"][1]["text"].startswith("Accepted")


def test_a_thread_at_its_limit_offers_only_to_close_and_close_closes_it(book):
    from test_a_tick_on_the_page_is_applied_once import Search
    lived_in(book)
    m = book.model()
    dev = next(p for p in m["people"] if p["id"] == "copperleaf_pay_raman")
    # The engine's one button for them is Close (tools/app_model.py standing), never a message.
    assert dev["stopped"] is True and dev["owed"]["kind"] == "close", dev["owed"]
    due = next(d for d in m["due"] if d.get("item") == "copperleaf_pay_raman"
               or "copperleaf_pay_raman" in d["id"])
    assert due["leave"] is True and due["step"].startswith("No reply to 2 messages")
    priya = next(d for d in m["due"] if "northwind_analytics_okafor" in d["id"])
    assert priya["step"] == "Follow up" and "leave" not in priya
    # "Close" on it: gone quiet, and its undo puts the status back.
    s = Search.__new__(Search)
    s.state, s.profile, s.dump, s.n = book.state, book.profile, os.path.join(book.root, "dump"), 0
    a = s.act("due.done", due["id"], value={"on": TODAY}, rev=due["rev"])
    assert s.apply()["ok"] == [a]
    assert book.contact("copperleaf_pay_raman")["status"] == "gone_cold"
    s.written_back()
    u = s.act("undo", undoes=a)
    assert u in s.apply()["ok"]
    row = book.contact("copperleaf_pay_raman")
    assert row["status"] == "connected_no_reply" and row["next_action"].startswith("Nudged")


def test_their_words_pasted_again_with_draft_a_reply_still_drafts_once(book):
    from test_a_tick_on_the_page_is_applied_once import Search
    lived_in(book)
    s = Search.__new__(Search)
    s.state, s.profile, s.dump, s.n = book.state, book.profile, os.path.join(book.root, "dump"), 0
    before = len(book.rows("tate"))
    a = s.act("msg.received", "tate", value={"text": SAM, "on": TODAY, "draft": True})
    assert s.apply()["ok"] == [a]
    assert len(book.rows("tate")) == before, "their message is in the log once"
    assert "already kept" in s.receipt(a)["note"]
    work = os.path.join(s.dump, "out", "files", "work")
    assert any(f.startswith("reply") for f in os.listdir(work)), "the reply is still drafted"


def test_first_notes_from_a_run_are_one_wave_and_a_route_is_not_said_twice(book):
    lived_in(book)
    m = book.model()
    firsts = [x for x in m["messages"] if x["type"] == "first_note" and x["hold"] is None]
    assert len(firsts) >= 3 and {x.get("wave") for x in firsts} == {"w2026-43"}
    sam = next(d for d in m["due"] if "tate" in d["id"])
    assert sam["context"] == "Recruiter", sam["context"]


# ------------------------------------------------------------------ the page itself

@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    import app_page
    root = str(tmp_path_factory.mktemp("contacts"))
    b = Book(root)
    lived_in(b)
    out = os.path.join(root, "page.artifact.html")
    b.run(APP, "page", "--now", NOW, "--out", out)
    path = os.path.join(root, "page.html")
    with open(out, encoding="utf-8") as fh, open(path, "w", encoding="utf-8") as w:
        w.write(app_page.standalone(fh.read()))
    return path


@pytest.mark.parametrize("vp,scheme", [(PHONE, "light"), (WIDE, "dark")], ids=["phone", "wide-dark"])
def test_contacts_says_what_to_do_once_and_agrees_with_to_do(run, page, vp, scheme):
    got = run("engine", html=page, viewport=vp, scheme=scheme, clock="2026-10-25T18:30:00Z",
              steps=[
                  {"hash": "todo", "read": "#main"},
                  {"hash": "contacts", "open": "fold:contacts"},
                  {"hash": "contacts", "open": "pname:row:tate"},
                  {"hash": "contacts", "open": "pname:row:copperleaf_pay_raman"}])
    assert not got["errors"], got["errors"]
    todo, contacts = got["after"][0]["text"], got["after"][1]["text"]
    sam, dev = got["after"][2]["dialog"], got["after"][3]["dialog"]
    # No dangling "at" for someone with no employer, anywhere.
    assert "Sam at" not in contacts and not sam.split("\n")[2].endswith(" at")
    assert "Find more people at\n" not in sam + "\n"
    # Their words are on their page, and someone who wrote first was not "written to". Read as
    # words: Chrome's engine breaks the line before the hidden "(not yet)" and Safari's does not
    # (2026-11-04), while both show and read out the same.
    assert "open to a chat" in sam and "Written to (not yet)" in " ".join(sam.split()), sam
    assert "Accepted your connection request." in dev
    # Dev's limit is reached: Close, never a third message, on the row and in To do.
    row = contacts.split("Dev at Copperleaf Pay")[1].split("More")[0]
    assert "Close" in row and "Draft the follow-up" not in row, row
    assert "No reply to 2 messages: leave it unless they write back." in row
    # The row does not name them again ("Next: reply to Sam, 2 days late").
    # The step without their name, and its one date in the form every card uses (2026-11-03).
    assert "Next: reply · " in contacts and "reply to Sam" not in contacts
    # The summary counts what To do lists, and the fold never says nothing is owed when it is.
    group = todo.split("Follow up with 2 people", 1)[1].split("Draft all", 1)[0]
    assert "Wren at Fernhill Freight" in group and "Rhian at Northwind Analytics" in group, todo
    assert "2 follow-ups you could send" in contacts, contacts.split("\n")[2]
    assert "nothing owed to them now" not in contacts
    # The run's first notes are one card in To do.
    assert "first notes ready to send" in todo
    card = todo.split("first notes ready to send", 1)[1].split("Open them", 1)[0]
    assert card.count("ready.") == 1, card     # "3 notes ready. 3 notes ready." said it twice
