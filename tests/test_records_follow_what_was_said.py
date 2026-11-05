"""Records follow what was said: an answer is no follow-up, a mark made in the same minute
takes, and an old ask unanswered for long leaves the owed list by itself.

The maintainer's notes, 2026-11-05: (14) the person's message moving a call to another day,
sent to someone who had offered the day, was counted as an unanswered follow-up and marked
them "no more follow-ups"; (17) "no answer owed" did not take the first time when their
message was logged in the same minute; (18) an old request from someone last heard from long
ago stayed on the owed list until closed by hand. Every person and employer is invented.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import reply  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def rule(monkeypatch):
    monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", 14)
    monkeypatch.setattr(schema, "MAX_UNANSWERED", 2)
    monkeypatch.setattr(schema, "MAX_NUDGES", 1)
    monkeypatch.setattr(state, "_drop_draft", lambda cid: False)


CID = "fernhill_quillan"


def _c(**kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update({"contact_id": CID, "name": "Odo Quillan", "company": "Fernhill Freight",
                "status": "in_conversation", **kw})
    return row


def _row(day, direction, text, scenario=""):
    return {"contact_id": CID, "date": day, "direction": direction, "channel": "message",
            "scenario": scenario, "summary": text[:40], "full_text": text}


def test_a_new_day_for_the_call_they_offered_is_an_answer_not_a_follow_up(rule):
    contacts = [_c()]
    log = [_row("2026-10-20", "out", "Hi Odo, hope you're well. I'm a data analyst.", "first_message"),
           _row("2026-10-22", "in", "Happy to chat. Does Thursday at 2pm work?"),
           _row("2026-10-22", "out", "Thursday at 2pm works well, thank you.", "reply")]
    # Sent from the page as the reply drafted to their message (msg.sent, kind reply).
    got = state.followed_up(contacts, log, CID, "2026-10-24", kind="message", answers=True,
                            text="So sorry, something has come up on Thursday. Could we do Friday at 2pm instead?")
    assert got["row"]["scenario"] == "reply", got
    msgs = [r for r in log if r["contact_id"] == CID]
    # Two messages, one answer: not their limit, and their one follow-up is still to come.
    assert state._chases(msgs) == 1
    assert not state.at_limit(contacts[0], msgs)
    assert not state.STOP_LINE.match(contacts[0]["next_action"]), contacts[0]["next_action"]
    assert reply.nudge_due(msgs, "2026-12-20").get("due"), reply.nudge_due(msgs, "2026-12-20")
    # One chase after the answer is their limit, as before.
    state.followed_up(contacts, log, CID, "2026-11-08", kind="nudge", text="Hi Odo, does Friday still suit?")
    msgs = [r for r in log if r["contact_id"] == CID]
    assert state.at_limit(contacts[0], msgs)
    assert not reply.nudge_due(msgs, "2026-12-20").get("due")


def test_the_page_logs_a_reply_drafted_to_them_as_an_answer(where, monkeypatch):
    import app_actions
    import types
    import datetime
    seen = []
    monkeypatch.setattr(app_actions, "_cli", lambda st, argv: (seen.append(argv), (0, ""))[1])
    monkeypatch.setattr(app_actions, "_already_sent", lambda *a: None)
    monkeypatch.setattr(app_actions, "_contact", lambda cid: ({"contact_id": cid, "next_action_due": ""},
                                                            [{"direction": "in", "date": "2026-10-22"}]))
    monkeypatch.setattr(app_actions, "_first", lambda cid: "Odo")
    for kind in ("reply", "follow_up"):
        run = types.SimpleNamespace(target={"kind": "message", "contact": CID, "msg_kind": kind},
                                    value={"text": "Could we do Friday instead?", "kind": kind, "on": "2026-10-24"},
                                    day=datetime.date(2026, 10, 24), at=None)
        run.words = lambda k="why", run=run: " ".join(str(run.value.get(k) or "").split())
        run.on = lambda: "2026-10-24"
        try:
            app_actions._msg_sent(run)
        except Exception:  # noqa: BLE001  only the command it ran is read here
            pass
    assert seen and seen[0][0] == "message" and "--answers" in seen[0], seen
    assert seen[-1][0] == "nudge" and "--answers" not in seen[-1], seen


def test_no_answer_owed_takes_the_first_time_for_a_message_logged_on_their_day(rule):
    """Their message was logged on the person's own day, ahead of the computer's clock (an
    evening in Toronto is the next morning in UTC): the mark dated by the computer read the
    message as written after it, and they stayed owed until it was run again."""
    contacts = [_c(status="replied_needs_response")]
    log = [_row("2026-10-20", "out", "Hi Odo, hope you're well. I'm a data analyst.", "first_message"),
           _row("2026-10-25", "in", "Thanks, I'll come back to you next week.")]
    row, _ = state.no_reply(contacts, log, CID, "they will come back next week", "2026-10-24")
    assert row["next_action"].startswith("Nothing owed (2026-10-25)"), row["next_action"]
    assert [i for i in state.owed(contacts, log, "2026-10-25") if i["contact_id"] == CID] == []
    # Their next message is owed as any other.
    log.append(_row("2026-10-27", "in", "Could you send me your resume?"))
    assert [i["kind"] for i in state.owed(contacts, log, "2026-10-27") if i["contact_id"] == CID] == ["reply"]


@pytest.fixture
def where(tmp_path, monkeypatch):
    import app_state
    import person
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("LJS_STATE", str(state_dir))
    monkeypatch.setenv("LJS_PROFILE", app_state.profile_copy(str(tmp_path / "profile")))
    person.reset()
    yield
    person.reset()


def _asked_book():
    # The chat that logged the ask wrote a date on the row to send it by: a date of the
    # person's own, so the 45-day rule never set it aside.
    contacts = [_c(status="replied_needs_response", next_action="Send your resume, as asked",
                   next_action_due="2026-08-20")]
    log = [_row("2026-08-10", "out", "Hi Odo, hope you're well. I'm a data analyst.", "first_message"),
           _row("2026-08-15", "in", "Thanks! Could you send me your resume?")]
    return contacts, log


def test_a_resume_asked_for_long_ago_with_nothing_since_closes_by_itself_and_is_said_once(where):
    import datetime
    import brief
    import open_actions
    contacts, log = _asked_book()
    mine = lambda day: [i for i in open_actions.due_items(contacts, log, [], day)  # noqa: E731
                        if i.get("contact_id") == CID]
    # Within two months of the ask it is owed as it was.
    assert [i["old"] for i in mine("2026-10-10")] == [False]
    # Past them, with nothing from them since: off the owed list, the day it closed kept.
    (it,) = mine("2026-10-20")
    assert it["old"] is True and it["lapsed_on"] == "2026-10-15", it
    said = brief._lapsed_asks([it], datetime.date(2026, 10, 14), datetime.date(2026, 10, 20))
    assert said == ["Closed by itself: %s's request for your %s (asked 15 Aug), with nothing " % (contacts[0]["name"], brief._noun()) +
                    "from them since. It stays on their card in Contacts, and a word from them opens it again."], said
    # Said once: the next brief does not say it again.
    assert brief._lapsed_asks([it], datetime.date(2026, 10, 20), datetime.date(2026, 10, 21)) == []
    # A date the person put on it still ahead keeps it; a word from them since opens it.
    assert state.resume_ask_lapsed("2026-08-15", log, "2026-10-20", due="2026-10-30") is None
    log.append(_row("2026-10-01", "in", "Still keen to see it when you can."))
    assert state.resume_ask_lapsed("2026-08-15", log, "2026-10-20") is None


def test_in_a_thread_they_never_answered_a_second_message_is_still_a_chase(rule):
    contacts = [_c(status="awaiting_reply")]
    log = [_row("2026-10-01", "out", "Hi Odo, hope you're well. I'm a data analyst.", "first_message")]
    got = state.followed_up(contacts, log, CID, "2026-10-15", kind="message", text="Hi Odo, any thoughts?")
    assert got["row"]["scenario"] == "nudge"
    assert state.at_limit(contacts[0], log)
