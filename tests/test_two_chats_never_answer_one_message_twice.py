"""Two chats answering one message each logged a reply, in their own words.

`state.py message` refused only the same words to the same person on the same day, so the
second chat's reply went in without a word and was relabelled a chase: twice on
2026-10-24. A second message on a day one already went since they last wrote is refused
now, with the one already there shown, unless the second really went too (`--also`).
Invented people and employers throughout.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

CID = "ana_rook"


def _t(date, direction, scenario="", text="", channel="message"):
    return {"contact_id": CID, "date": date, "direction": direction, "channel": channel,
            "scenario": scenario, "summary": scenario or "logged", "full_text": text,
            "subject": ""}


def _book():
    contacts = [{"contact_id": CID, "name": "Ana Rook", "company": "Kestrel Mutual",
                 "status": "replied", "channel": "connection",
                 "first_contacted": "2026-10-20"}]
    threads = [_t("2026-10-20", "out", "connection_note", "Hi Ana, a first note.", "connection"),
               _t("2026-10-24", "in", "", "Happy to chat next week. What would you like to know?")]
    return contacts, threads


def test_a_second_reply_to_the_same_message_the_same_day_is_refused_and_shows_the_first():
    contacts, threads = _book()
    first = "Thanks Ana! Would Tuesday at 2 suit you?"
    got = state.followed_up(contacts, threads, CID, "2026-10-24", text=first)
    assert got["row"]["scenario"] == "reply"
    with pytest.raises(ValueError) as e:
        state.followed_up(contacts, threads, CID, "2026-10-24",
                          text="Hi Ana, thank you. Could we speak on Wednesday?")
    said = str(e.value)
    assert "already logged for 2026-10-24 since they last wrote" in said
    assert first in said and "--also" in said
    assert len([r for r in threads if r["direction"] == "out"]) == 2     # nothing added


def test_a_second_message_that_really_went_is_logged_with_also():
    contacts, threads = _book()
    state.followed_up(contacts, threads, CID, "2026-10-24", text="Thanks Ana! Tuesday at 2?")
    got = state.followed_up(contacts, threads, CID, "2026-10-24", also=True,
                            text="Sorry Ana, I meant Wednesday at 2.")
    assert got["row"]["full_text"] == "Sorry Ana, I meant Wednesday at 2."


def test_a_reply_after_they_wrote_again_and_the_next_day_are_both_fine():
    contacts, threads = _book()
    state.followed_up(contacts, threads, CID, "2026-10-24", text="Thanks Ana! Tuesday at 2?")
    threads.append(_t("2026-10-24", "in", "", "Tuesday works. Speak then."))
    state.followed_up(contacts, threads, CID, "2026-10-24", text="Great, talk then.")
    contacts2, threads2 = _book()
    state.followed_up(contacts2, threads2, CID, "2026-10-24", text="Thanks Ana! Tuesday at 2?")
    got = state.followed_up(contacts2, threads2, CID, "2026-10-31", kind="nudge",
                            text="Hi Ana, just checking Tuesday still suits.")
    assert got["row"]["scenario"] == "nudge"


def test_the_resume_that_goes_after_the_reply_is_its_own_step(tmp_path, monkeypatch):
    contacts, threads = _book()
    state.followed_up(contacts, threads, CID, "2026-10-24", text="Thanks Ana! Here it is.")
    monkeypatch.setattr(state, "resolve_attachment", lambda p, root=None: "cv/Ana_Resume.pdf")
    got = state.followed_up(contacts, threads, CID, "2026-10-24", text="My resume, attached.",
                            attached="cv/Ana_Resume.pdf")
    assert "attached" in got["row"]["summary"]


def test_the_command_says_why_and_logs_nothing(tmp_path, capsys):
    import csv_store  # noqa: F401  the module the state files are written with
    contacts, threads = _book()
    cpath, tpath = str(tmp_path / "c.csv"), str(tmp_path / "t.csv")
    state.save_contacts(contacts, cpath)
    state.save_threads(threads, tpath)
    words = tmp_path / "w.txt"
    for text in ("Thanks Ana! Tuesday at 2?", "Hi Ana, could we try Wednesday?"):
        words.write_text(text)
        state.main(["message", CID, "--text-file", str(words), "--contacts", cpath,
                    "--threads", tpath, "--today", "2026-10-24"])
    out = capsys.readouterr().out
    assert "message: 1 recorded" in out and "not recorded: ana_rook: a message to Ana Rook" in out
    assert len([r for r in state.load_threads(tpath) if r["direction"] == "out"]) == 2


def test_a_call_held_today_is_not_a_message_already_sent():
    contacts, threads = _book()
    threads.append(_t("2026-10-24", "out", "call_held", "Call held", "call"))
    got = state.followed_up(contacts, threads, CID, "2026-10-24",
                            text="Thanks for the time today, Ana. It helped a lot.")
    assert got["row"]["full_text"].startswith("Thanks for the time today")


def test_the_first_message_after_a_request_accepted_the_same_day_goes_in():
    for scenario, text in (("connection_note", "Hi Ana, a short note with the request."),
                           ("request_outside", "")):
        contacts = [{"contact_id": CID, "name": "Ana Rook", "company": "Kestrel Mutual",
                     "status": "connected_no_reply", "channel": "connection",
                     "first_contacted": "2026-10-24"}]
        threads = [_t("2026-10-24", "out", scenario, text, "connection"),
                   _t("2026-10-24", "in", "connection_accepted", "", "connection")]
        got = state.followed_up(contacts, threads, CID, "2026-10-24",
                                text="Thanks for connecting, Ana. How did you find the move?")
        assert got["row"]["direction"] == "out", scenario
