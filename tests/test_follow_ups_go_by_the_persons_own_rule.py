"""Follow-ups go by the person's own rule, and the date is written on each contact.

From a person's repo on 2026-10-23: first messages and nudges were timed by the app's six
business days alone, though the person follows up after fourteen days connected with no
message, and the brief reads a follow-up only from a date on the contact row, which an
imported thread never had. profile/networking.py now takes FOLLOW_UP_DAYS and
MAX_UNANSWERED, and `state.write_follow_ups` puts the date on every contact waiting on a
reply, never over a date or note of the person's own.
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pytest  # noqa: E402

import reply  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def rule(monkeypatch):
    def set_(days=0, unanswered=2):
        monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", days)
        monkeypatch.setattr(schema, "MAX_UNANSWERED", unanswered)
        monkeypatch.setattr(schema, "MAX_NUDGES", unanswered - 1)
    return set_


def _c(cid="kestrel_haldane", **kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update({"contact_id": cid, "name": "Corwin Haldane", "company": "Kestrel Mutual",
                "status": "awaiting_reply", **kw})
    return row


def _out(day, cid="kestrel_haldane", scenario=""):
    return {"contact_id": cid, "date": day, "direction": "out", "channel": "message",
            "scenario": scenario, "summary": "note", "full_text": "Hi Corwin, hope you're well."}


def _kinds(contacts, threads, today):
    return [(i["contact_id"], i["kind"], i["due"]) for i in state.owed(contacts, threads, today)]


def test_unset_the_apps_six_business_days_and_one_nudge_stand(rule):
    rule()
    assert state.follow_up_on("2026-10-01") == state.add_business_days(
        datetime.date(2026, 10, 1), schema.FOLLOWUP_BUSINESS_DAYS)
    assert schema.follow_up_rule() == "6 business days, at most 2 with no reply"


def test_fourteen_days_connected_and_silent_is_when_a_follow_up_is_due(rule):
    rule(days=14)
    contacts, log = [_c()], [_out("2026-10-01")]
    assert _kinds(contacts, log, "2026-10-14") == []
    assert _kinds(contacts, log, "2026-10-15") == [("kestrel_haldane", "nudge", "2026-10-15")]
    got = reply.nudge_due(log, "2026-10-14")
    assert not got["due"] and got["due_date"] == "2026-10-15" and "14 days" in got["reason"]
    assert reply.nudge_due(log, "2026-10-15")["due"]
    # From the day they accepted, when that is the last thing that happened.
    accepted = [dict(_out("2026-09-01"), channel="connection", scenario="connection_request"),
                {"contact_id": "kestrel_haldane", "date": "2026-09-20", "direction": "in",
                 "channel": "connection", "scenario": "connection_accepted", "summary": "",
                 "full_text": ""}]
    assert state.follow_up_due(contacts[0], accepted)[1] == datetime.date(2026, 10, 4)


def test_the_cap_on_unanswered_messages_is_the_persons(rule):
    contacts = [_c()]
    log = [_out("2026-09-01"), _out("2026-09-20", scenario="nudge")]
    rule(days=14, unanswered=2)
    assert _kinds(contacts, log, "2026-11-30") == []
    assert "2 messages have gone with no reply" in reply.nudge_due(log, "2026-11-30")["reason"]
    rule(days=14, unanswered=3)
    assert _kinds(contacts, log, "2026-10-04") == [("kestrel_haldane", "nudge", "2026-10-04")]


def test_the_date_is_written_on_each_contact_and_never_over_the_persons_own(rule):
    rule(days=14)
    contacts = [_c(), _c("fernhill_oyelaran", name="Tamsin Oyelaran", company="Fernhill Freight",
                         next_action="HOLD until 2026-12-01: interview running"),
                _c("larkspur_pellow", name="Rhian Pellow", company="Larkspur Retail",
                   next_action="Ask about the Leeds team when we speak"),
                _c("brannock_quarrie", name="Fenella Quarrie", company="Brannock",
                   next_action="Follow up if no reply, and mention the Leeds depot")]
    log = [_out("2026-10-01"), _out("2026-10-01", "fernhill_oyelaran"),
           _out("2026-10-01", "larkspur_pellow"), _out("2026-10-01", "brannock_quarrie")]
    said = state.write_follow_ups(contacts, log, "2026-10-05")
    assert said == ["Corwin Haldane (kestrel_haldane): follow up on 2026-10-15"]
    assert contacts[0]["next_action"] == ("Follow up if no reply (1 of 2 sent; your rule: 14 "
                                          "days, at most 2 with no reply)")
    assert contacts[0]["next_action_due"] == "2026-10-15"
    for c in contacts[1:]:                       # their own words, untouched, and undated
        assert "your rule" not in c["next_action"] and not c["next_action_due"]
    # Written again with nothing changed, nothing is said.
    assert state.write_follow_ups(contacts, log, "2026-10-05") == []
    # A date the person moved is theirs, and so is one they cleared.
    contacts[0]["next_action_due"] = "2026-11-20"
    assert state.write_follow_ups(contacts, log, "2026-10-05") == []
    assert contacts[0]["next_action_due"] == "2026-11-20"
    # A rule they change re-dates what the app wrote.
    contacts[0]["next_action_due"] = "2026-10-15"
    rule(days=21)
    assert state.write_follow_ups(contacts, log, "2026-10-05") == \
        ["Corwin Haldane (kestrel_haldane): follow up on 2026-10-22"]


def test_at_the_limit_the_row_says_so_and_keeps_the_day_to_close_it(rule):
    rule(days=14)
    contacts = [_c()]
    log = [_out("2026-10-01"), _out("2026-10-15", scenario="nudge")]
    assert state.write_follow_ups(contacts, log, "2026-10-16") == \
        ["Corwin Haldane (kestrel_haldane): no more follow-ups; close it on 2026-10-29 if still silent"]
    assert contacts[0]["next_action"].startswith("No more follow-ups: 2 messages with no reply")
    assert "state.py set kestrel_haldane --status gone_cold" in contacts[0]["next_action"]
    assert _kinds(contacts, log, "2026-10-29") == [("kestrel_haldane", "action_due", "2026-10-29")]
    rule()                                       # the app's own words, as they always were
    contacts = [_c()]
    state.write_follow_ups(contacts, log, "2026-10-16")
    assert contacts[0]["next_action"].startswith("Nudged: nothing more unless they reply")
    rule(days=14, unanswered=1)                  # one message, and no follow-up at all
    contacts, log = [_c()], [_out("2026-10-01")]
    state.write_follow_ups(contacts, log, "2026-10-02")
    assert contacts[0]["next_action"].startswith("No more follow-ups: 1 messages with no reply")
    assert not reply.nudge_due(log, "2026-10-20")["due"]
    assert _kinds(contacts, log, "2026-10-14") == []
    assert _kinds(contacts, log, "2026-10-15") == [("kestrel_haldane", "action_due", "2026-10-15")]


def test_a_note_logged_as_sent_carries_the_persons_date(rule, monkeypatch):
    rule(days=14)
    monkeypatch.setattr(state, "_drop_draft", lambda cid: False)
    contacts, log = [_c(status="not_contacted")], []
    state.sent(contacts, log, "kestrel_haldane", "2026-10-01", channel="message",
               text="Hi Corwin, hope you're well. How is the planning team set up?")
    assert contacts[0]["next_action_due"] == "2026-10-15"


def test_a_nudge_says_what_follows_by_the_persons_rule(rule, monkeypatch):
    monkeypatch.setattr(state, "_drop_draft", lambda cid: False)
    rule(days=14, unanswered=3)
    contacts, log = [_c()], [_out("2026-09-01")]
    state.followed_up(contacts, log, "kestrel_haldane", "2026-09-15", kind="nudge",
                      text="Hi Corwin, is a call next week still good for you?")
    assert contacts[0]["next_action"].startswith("Follow up if no reply (2 of 3 sent")
    assert contacts[0]["next_action_due"] == "2026-09-29"
    state.followed_up(contacts, log, "kestrel_haldane", "2026-09-29", kind="nudge",
                      text="Hi Corwin, one last thought on the planning team.")
    assert contacts[0]["next_action"].startswith("No more follow-ups: 3 messages with no reply")
    assert contacts[0]["next_action_due"] == "2026-10-13"      # the day to close it
    rule()                                     # the app's own rule: one nudge, said so
    assert state.waiting_action(1) == "One nudge if no reply"


def test_only_undated_rows_count_for_the_upgrade(rule):
    rule()
    contacts = [_c(), _c("fernhill_oyelaran", name="Tamsin Oyelaran", company="Fernhill Freight",
                         next_action="One nudge if no reply", next_action_due="2026-10-09")]
    log = [_out("2026-10-01"), _out("2026-10-01", "fernhill_oyelaran")]
    assert [s.split(" (")[1].split(")")[0]
            for s in state.write_follow_ups([dict(c) for c in contacts], log, "2026-10-02",
                                            only_undated=True)] == ["kestrel_haldane"]


def test_a_promise_with_no_date_to_count_from_keeps_the_clock_theirs(rule):
    rule()
    log = [{"contact_id": "kestrel_haldane", "date": "not a date", "direction": "in",
            "channel": "message", "scenario": "", "summary": "",
            "full_text": "Send me your resume and I will see about openings."},
           dict(_out("2026-10-10"), full_text="Thanks, here it is.")]
    honest, why = reply.following_up_is_honest(log, "2026-10-20")
    assert not honest and "the clock is theirs" in why


def test_a_setting_that_is_not_a_number_never_stops_the_tools(monkeypatch):
    class Net:
        FOLLOW_UP_DAYS = "fourteen"
        MAX_UNANSWERED = None
    monkeypatch.setattr(schema, "_NETWORKING", Net)
    assert schema._days_setting("FOLLOW_UP_DAYS") == 0
    assert schema._days_setting("MAX_UNANSWERED") == 0


def test_the_apps_line_on_someone_who_has_written_since_comes_off(rule):
    """A background upgrade wrote "no more follow-ups" from a copy of the log made before
    the contact's reply asking for the resume (2026-10-24). Run again on the merged log,
    the app's own line comes off, and their reply is owed like any other. A line the person
    or a chat wrote is never touched."""
    rule(days=14)
    contacts = [_c()]
    log = [_out("2026-10-01"), _out("2026-10-15", scenario="nudge")]
    state.write_follow_ups(contacts, log, "2026-10-16")
    assert contacts[0]["next_action"].startswith("No more follow-ups")
    log.append({"contact_id": "kestrel_haldane", "date": "2026-10-16", "direction": "in",
                "channel": "message", "scenario": "", "summary": "asked for the resume",
                "full_text": "Thanks Corwin here, could you send your resume?"})
    said = state.write_follow_ups(contacts, log, "2026-10-17")
    assert said == ["Corwin Haldane (kestrel_haldane): the follow-up line is off: they have "
                    "written since, so a reply is owed"]
    assert (contacts[0]["next_action"], contacts[0]["next_action_due"]) == ("", "")
    assert [k for _, k, _ in _kinds(contacts, log, "2026-10-17")] == ["reply"]
    assert state.write_follow_ups(contacts, log, "2026-10-17") == []      # once only
    own = [_c(next_action="Send the resume she asked for", next_action_due="2026-10-18")]
    assert state.write_follow_ups(own, log, "2026-10-17") == []
    assert own[0]["next_action"] == "Send the resume she asked for"
