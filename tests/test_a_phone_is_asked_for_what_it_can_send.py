"""A phone is asked for what a phone can send, in a few words.

In a chat with no browser of the person's, the route offered a phone a hundred words of
computer steps and "paste the profile", while its own "do" line asked for screenshots,
and the ladder told a phone to send LinkedIn's Save to PDF, which the phone app does not
have (networking audit, 2026-10-25). One line now says what to send for where the chat
runs, and the route, the ladder and /network all say it. And the sign-in line no longer
tells someone reading in their own Chrome that a pane will keep a sign-in.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import place  # noqa: E402
import reading  # noqa: E402
import sources  # noqa: E402

PHONE = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_ENTRYPOINT": "remote_mobile"}


def test_what_to_send_fits_the_place():
    assert "LinkedIn app" in reading.what_to_send("phone")
    assert "Save to PDF" not in reading.what_to_send("phone")
    for where in ("web", "unknown", "desktop-cloud"):
        assert "Save to PDF" not in reading.what_to_send(where)
        assert "screenshots" in reading.what_to_send(where)
    assert "Save to PDF" in reading.what_to_send("local")


def test_the_ladder_tells_a_phone_what_a_phone_can_send(monkeypatch):
    for k, v in PHONE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    said = sources.ladder([], "browser", has_export=False)["say"]
    assert "screenshots of their profile from the LinkedIn app" in said
    assert "Save to PDF" not in said


def test_the_phone_line_is_short_and_says_one_thing_to_send():
    r = reading.route([], "browser", PHONE)
    assert len(r["say"].split()) <= place.SHORT_WORDS
    assert r["say"].count("screenshots") == 1
    assert "paste the" not in r["say"].lower()


def test_reading_in_their_own_chrome_never_promises_a_pane_keeps_the_sign_in():
    local = {"CLAUDECODE": "1"}
    chrome = reading.route(["chrome"], "browser", local, signed_in=False)["say"]
    assert "your own Chrome" in chrome and "pane" not in chrome
    pane = reading.route(["browser"], "browser", local, signed_in=False)["say"]
    assert "sign in yourself, once" in pane and "keeps it for later chats" in pane
