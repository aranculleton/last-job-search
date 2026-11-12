"""A reply to someone who asked for the resume queues one made for them, in the same step (#232).

A contact wrote "send me an email with your resume and we can talk next week". `reply.py
prepare` read it as `send_resume`, `finish` drafted the email saying the resume was attached,
and the only resume on their card was the person's general one: nothing was made for that
reader until the person noticed and asked. Now `finish` queues the page's own
resume_for_contact (the resume only, no role named, a note naming their team and employer) in
the reply's own finishing batch, and its line says the resume is being made, so the email and
the resume arrive together. Once, never twice; and a reply with no ask queues none. Every
person and employer is invented: tests/app_state.py's search, with the second Juno Castellan
at Thornbury Bank that test_a_reply_takes_two_commands adds. The example person's word for
the document is "CV" (person.json documents.noun), so every line here says it, and each
reply goes by email, so it starts with its subject (#239).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_a_reply_takes_two_commands import (  # noqa: E402,F401
    JUNO, ROOT, WREN, batch, put, run, search, write)
from test_a_tick_on_the_page_is_applied_once import NOW  # noqa: E402

ASK = ("Thanks Morgan, good to hear from you. Send me an email with your resume and we can "
       "talk next week.")
DRAFT = ("Subject: Next week\n\nHi Juno, thanks for getting back to me. I've attached my CV, "
         "and next week works "
         "well for a call.\n")
RESUME_ID = f"contact_resume~{JUNO}~general"


def _prepare(s, cid, text):
    code, out = run(s, "tools/network/reply.py", "prepare", cid, "--text-file",
                    write(s, f"{cid}.txt", text), "--date", "2026-10-25", "--channel", "email",
                    "--today", "2026-10-25")
    assert code == 0, out
    return out


def _item(s, wid, cid, version=3, thread=""):
    put(s, "work", wid, {"kind": "reply", "title": "Reply", "to": "cloud",
                         "args": dict({"contact": cid}, **({"thread": thread} if thread else {})),
                         "status": "running", "stage": 1}, version)


def _finish(s, cid, wid, draft, *more):
    code, out = run(s, "tools/network/reply.py", "finish", cid, "--draft-file", "-",
                    "--work", wid, "--dump", s.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25", *more, given=draft)
    assert code == 0, out
    return out, json.loads(out[out.index("{"):])


def _resume_work(got):
    return [e for b in got["batches"] for e in batch(b)
            if e["collection"] == "work" and (e.get("body") or {}).get("kind")
            == "resume_for_contact"]


def test_a_resume_ask_queues_one_resume_with_the_reply_and_says_so(search):  # noqa: F811
    read = _prepare(search, JUNO, ASK)
    assert "scenario: send_resume" in read, read
    _item(search, "reply~juno", JUNO, thread="cloud-c7")
    out, got = _finish(search, JUNO, "reply~juno", DRAFT)

    (made,) = _resume_work(got)
    body = made["body"]
    assert made["doc_id"] == RESUME_ID and body["status"] == "queued", made
    assert body["args"]["contact"] == JUNO and body["args"]["job"] is None
    assert body["args"]["resume_only"] is True
    # Their team and employer, from their record, by first name only.
    assert body["args"]["note"] == ("Juno asked for your CV in their reply. Aim it at their "
                                    "team and the work it does: Talent Partner, Thornbury Bank.")
    assert body["title"] == "CV for Juno"
    # The finishing line, on the page and to Claude, says it is being made.
    (work,) = [e for e in batch(got["batches"][0]) if e["doc_id"] == "reply~juno"]
    assert work["body"]["result"]["summary"] == \
        "Your reply to Juno is ready, and a CV for them is being made.", work
    (said,) = [e for e in batch(got["batches"][0]) if e["collection"].startswith("talk/")]
    assert said["body"]["text"] == ("Your reply to Juno is drafted, ready to copy on their card. "
                                    "A CV for Juno is being made to go with it."), said
    assert "one made for them is queued (" + RESUME_ID + ")" in out, out

    # Finished again (the draft rewritten): the same batch, one resume, never two.
    out2, again = _finish(search, JUNO, "reply~juno", DRAFT)
    assert len(_resume_work(again)) == 1 and again["batches"] == got["batches"], out2

    # Another reply to them later, read after the first landed: the resume is being made
    # already, so nothing more is queued.
    _item(search, "reply~juno2", JUNO)
    out3, third = _finish(search, JUNO, "reply~juno2",
                          "Subject: Tuesday\n\nHi Juno, thanks again. Tuesday at 10am suits "
                          "me well.\n")
    assert _resume_work(third) == [], out3
    assert "being made already (" + RESUME_ID + ")" in out3, out3


def test_a_reply_with_no_resume_ask_queues_none(search):  # noqa: F811
    _prepare(search, WREN, "Thanks Morgan, happy to have a call. Thursday afternoon works.")
    _item(search, "reply~wren", WREN)
    out, got = _finish(search, WREN, "reply~wren",
                       "Subject: Thursday\n\nHi Wren, thanks for this. Thursday "
                       "afternoon suits me well.\n")
    assert _resume_work(got) == [], out
    assert "being made" not in out, out


def test_a_draft_saying_the_resume_is_attached_queues_one_too(search):  # noqa: F811
    """Their message named no resume, but the reply says one is attached: the one attached is
    made for them, never the general one by default."""
    _prepare(search, WREN, "Thanks Morgan, happy to help where I can. Drop me an email.")
    _item(search, "reply~wren", WREN)
    out, got = _finish(search, WREN, "reply~wren",
                       "Subject: My CV\n\nHi Wren, thanks for this. I've attached my "
                       "CV for context.\n")
    (made,) = _resume_work(got)
    assert made["body"]["args"]["contact"] == WREN, out


def test_in_a_chat_with_no_page_the_one_command_to_queue_it_is_given(search):  # noqa: F811
    _prepare(search, JUNO, ASK)
    code, out = run(search, "tools/network/reply.py", "finish", JUNO, "--draft-file", "-",
                    "--today", "2026-10-25", "--now", NOW, given=DRAFT)
    assert code == 0, out
    assert ("python3 tools/app.py ask \"$D\" --kind resume_for_contact --id " + RESUME_ID) in out
    assert "Show the draft in full" in out
