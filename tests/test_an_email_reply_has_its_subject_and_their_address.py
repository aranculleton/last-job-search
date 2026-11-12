"""An email reply is drafted with its subject, and the address they gave is on their card (#239).

A contact wrote on LinkedIn "Send me an email if you'd like to connect", their address under
it. The reply was drafted as a body alone, until the person asked for a subject in a change,
and the address stayed in the thread: neither their card nor the draft showed it, so the person
opened the thread and copied it by hand. Now `reply.py prepare` says an email starts with its
subject, `finish` refuses one without (or keeps theirs, "Re: ...", in a reply to their email),
`state.received` keeps the address a message gives on the contact (`email`), never one made
up, and the page shows it on their page and beside the draft, with Copy. Every person and
employer is invented: tests/app_state.py's search and the page's sample
(tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_a_reply_takes_two_commands import (  # noqa: E402,F401
    JUNO, ROOT, WREN, batch, put, run, search, write)
from test_a_tick_on_the_page_is_applied_once import NOW  # noqa: E402

CONNECT = ("Thanks for reaching out. Send me an email if you'd like to connect next week.\n"
           "wren.h@example.com")
BODY = "Hi Wren, thanks for this. Would Tuesday at 10am or Wednesday at 2pm suit you for a call?\n"


def _contact(s, cid):
    with open(os.path.join(s.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == cid)


def _prepare(s, cid, text, *more):
    code, out = run(s, "tools/network/reply.py", "prepare", cid, "--text-file",
                    write(s, f"{cid}.txt", text), "--date", "2026-10-25", "--today",
                    "2026-10-25", *more)
    assert code == 0, out
    return out


def _finish(s, cid, draft):
    return run(s, "tools/network/reply.py", "finish", cid, "--draft-file", "-", "--today",
               "2026-10-25", "--now", NOW, given=draft)


def test_an_email_asked_for_on_linkedin_is_drafted_with_its_subject(search):  # noqa: F811
    out = _prepare(search, WREN, CONNECT)
    assert "format: an email, so it starts with its subject" in out, out
    # The address they gave, kept on their record and said, never one made up.
    assert _contact(search, WREN)["email"] == "wren.h@example.com"
    assert "their email: wren.h@example.com" in out, out
    code, out = _finish(search, WREN, BODY)
    assert code == 1 and "REFUSED, nothing saved" in out and "Subject:" in out, out
    code, out = _finish(search, WREN, "Subject: A call next week\n\n" + BODY)
    assert code == 0, out
    with open(os.path.join(search.state, "documents", "network", WREN, "draft.md"),
              encoding="utf-8") as fh:
        assert fh.read().startswith("Subject: A call next week\n\nHi Wren")


def test_a_reply_to_their_email_keeps_their_subject(search):  # noqa: F811
    _prepare(search, JUNO, "Hi Morgan, could we talk on Thursday? Best, Juno",
             "--channel", "email", "--subject", "Our chat")
    code, out = _finish(search, JUNO, "Hi Juno, Thursday at 2pm suits me well.\n")
    assert code == 0 and "subject: Re: Our chat" in out, out
    with open(os.path.join(search.state, "documents", "network", JUNO, "draft.md"),
              encoding="utf-8") as fh:
        assert fh.read().startswith("Subject: Re: Our chat\n\n")


def test_no_address_is_kept_that_no_message_gave(search):  # noqa: F811
    _prepare(search, WREN, "Thanks Morgan, happy to have a call. Thursday afternoon works.")
    assert _contact(search, WREN)["email"] == ""


def test_the_address_reaches_the_page_owner_only(search):  # noqa: F811
    """The page's owner-only reach documents carry it, from the record or from their message
    however it was logged; the page's own data never does."""
    _prepare(search, WREN, CONNECT)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    code, out = run(search, os.path.join(ROOT, "tools", "app.py"), "view",
                    os.path.join(str(search.tmp), "v"), "--dump", search.dump, "--now", NOW)
    assert code == 0, out
    got = json.loads(out)
    addr, model = [], []
    for b in got["batches"]:
        for e in batch(b):
            (addr if e["collection"] == "addr" else model).append(e)
    assert any((e["body"] or {}).get("contacts", {}).get(WREN, {}).get("email")
               == "wren.h@example.com" for e in addr), addr
    assert not any("wren.h@example.com" in json.dumps(e["body"]) for e in model)


# ------------------------------------------------------------------ on the page

import pytest  # noqa: E402

from test_the_page_journeys import PHONE, WIDE, _go, browser  # noqa: E402


@pytest.fixture(scope="module")
def page():
    yield from browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_their_address_is_beside_the_draft_and_on_their_page_with_copy(page, tmp_path, vp):
    card = '[data-item="ellerwick_trust_priya"]'
    seed = {"reach/ellerwick_trust_priya": {"email": "marisol.e@example.com"}}
    got = _go(page, tmp_path, [
        {"hash": "contacts", "read": card},
        {"click": "Copy email address", "within": card, "clip": True},
        {"hash": "contacts", "click": "Marisol", "role": "link", "within": card,
         "read": "dialog.detail"},
        {"click": "Copy email address", "within": "dialog.detail", "clip": True},
    ], vp, seed=seed)
    assert "Email: marisol.e@example.com" in got["after"][0]["text"], got["after"][0]["text"]
    assert got["after"][1]["clip"] == "marisol.e@example.com"
    assert "Email: marisol.e@example.com" in got["after"][2]["text"], got["after"][2]["text"]
    assert got["after"][3]["clip"] == "marisol.e@example.com"
    # No address kept: no line and no button, never a guess.
    got = _go(page, tmp_path, [{"hash": "contacts", "count": '[data-k^="copy:memail:"]'}], vp)
    assert got["after"][0]["count"] == 0
