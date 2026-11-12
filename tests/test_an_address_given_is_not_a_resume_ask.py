"""An email address given to set up a call is an email to write, never a resume ask (#241).

`reply.py` read any address in a reply as `send_resume` ("action beats substance"), so "Send
me an email if you'd like to connect next week" with an address under it was drafted as "Email
the resume now, attached", a resume was made for that reader, and the send was logged as a
resume sent as asked, though nobody asked. Now an address, or "email me", is `send_email`:
the email sets up the conversation and carries nothing. `send_resume` needs their words to ask
for the resume, a CV or their background, or a role being discussed. Every person and employer
is invented: tests/app_state.py's search, through the real `reply.py prepare` and `finish`.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_a_reply_takes_two_commands import (  # noqa: E402,F401
    ROOT, WREN, batch, put, run, search, write)
from test_a_tick_on_the_page_is_applied_once import NOW  # noqa: E402

import reply  # noqa: E402

CONNECT = ("Thanks for reaching out. Send me an email if you'd like to connect next week.\n"
           "wren.h@example.com")


def test_an_address_to_connect_is_an_email_to_write_with_nothing_attached():
    for text in (CONNECT, "Happy to help. Drop me a line at wren.h@example.com and we can find a "
                          "time.", "Email me and we can set something up."):
        got = reply.classify(text)
        assert got["scenario"] == "send_email", (text, got)
        advice = reply.guidance(got)
        assert "which_resume" not in advice, advice
        assert f"no {reply._NOUN} attached" in advice["next_action"], advice
    # Their words ask for the document, or a role is being discussed: the resume goes.
    for text in ("Send me your CV at wren.h@example.com and I'll pass it on.",
                 "Happy to share your background with the team, email me at wren.h@example.com.",
                 "Email me at wren.h@example.com about the analyst role and I'll take a look."):
        assert reply.classify(text)["scenario"] == "send_resume", text
    # A no with a signature is still a no.
    assert reply.classify("Thanks, but we are not hiring right now.\nWren | wren.h@example.com"
                          )["scenario"] == "rejection"


def test_on_the_real_path_the_email_queues_no_resume(search):  # noqa: F811
    code, out = run(search, "tools/network/reply.py", "prepare", WREN, "--text-file",
                    write(search, "wren.txt", CONNECT), "--date", "2026-10-25", "--today",
                    "2026-10-25")
    assert code == 0, out
    assert "scenario: send_email" in out and "scenario: send_resume" not in out, out
    assert "which CV" not in out, out
    put(search, "work", "reply~wren", {"kind": "reply", "title": "Reply", "to": "cloud",
                                       "args": {"contact": WREN}, "status": "running",
                                       "stage": 1}, 3)
    code, out = run(search, "tools/network/reply.py", "finish", WREN, "--draft-file", "-",
                    "--work", "reply~wren", "--dump", search.dump, "--kind", "cloud", "--now",
                    NOW, "--today", "2026-10-25",
                    given=("Subject: A call next week\n\nHi Wren, thanks for this. Would Tuesday "
                           "at 10am or Wednesday at 2pm suit you for a call?\n"))
    assert code == 0, out
    got = json.loads(out[out.index("{"):])
    made = [e for b in got["batches"] for e in batch(b)
            if e["collection"] == "work" and (e.get("body") or {}).get("kind")
            == "resume_for_contact"]
    assert made == [] and "being made" not in out, out
