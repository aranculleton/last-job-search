"""A connection request logged as a first note is pending, never a follow-up.

Issue 242: a note sent with a connection request was logged as `out, linkedin, first_note`,
"Connection request with note sent", on a contact whose channel was `connection`. Nobody
accepted it, and fourteen days on the card said "Follow-up ready", "Next: follow up" and
"Draft the follow-up", and To do listed "Follow up with ..." under Due or late: a message
nobody could send. It reads as the request it went as: "Request pending" with nothing to send,
and one to withdraw after state.REQUEST_WITHDRAW_DAYS.

A note on the record saying no more messages ("Follow-up limit reached: no more messages
unless they write") stopped only the follow-up drafter (issue 223's leave_alone), never the due
list, the limit or the card: the same record was offered a follow-up everywhere else. It is
read once (state.told_no_more), by all of them.

Built on the real path: the example person's state with these people added, and the page
model `app.py model` makes from it. Every person and employer here is invented.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_state  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW              # 2026-10-25T18:00:00Z
CONTACTS = ["contact_id", "name", "title", "company", "company_key", "location",
            "linkedin_url", "email", "tier", "route", "route_detail", "referred_by", "signal",
            "signal_date", "first_contacted", "channel", "status", "next_action",
            "next_action_due", "outcome", "linked_application", "notes"]
THREADS = ["contact_id", "date", "direction", "channel", "scenario", "summary", "full_text"]
HOME = "Manchester, England, United Kingdom"
NOTE = "Hi {n}, hope you're well. I build demand forecasts in Manchester. I'd love to hear what you're working on."
# The app's own follow-up line, as it sat on the record in the issue.
WAITING = "Sent 8 Oct, no reply yet: follow up after 14 days (one left), then stop"
LIMIT = "Follow-up limit reached: no more messages unless they write"

# (id, name, employer, contact channel, the note's summary, sent on, notes on the record)
PEOPLE = [
    # The issue's shape: a request by the contact's channel, logged as a first note.
    ("brackenhill_ardent", "Ilsa Ardent", "Brackenhill Insurance", "connection",
     "Connection request with note sent", "2026-10-08", "invented"),
    # Its summary alone says it went as a request.
    ("quillmere_soto", "Bram Soto", "Quillmere Bank", "linkedin",
     "Connection request with note sent", "2026-10-08", "invented"),
    # By the contact's channel alone.
    ("fennick_lowe", "Odile Lowe", "Fennick Lending", "connection", "message", "2026-10-08",
     "invented"),
    # Three weeks on: one to withdraw, never a follow-up.
    ("larchway_pym", "Cato Pym", "Larchway Credit", "connection",
     "Connection request with note sent", "2026-10-01", "invented"),
    # A first message on LinkedIn to someone already connected: a follow-up, as before.
    ("ormsby_reyes", "Tove Reyes", "Ormsby Mutual", "linkedin", "message", "2026-10-08",
     "invented"),
    # A message to someone connected, whose record says no more messages.
    ("tamsworth_quell", "Nell Quell", "Tamsworth Bank", "linkedin", "message", "2026-10-08",
     LIMIT),
    # The issue's own record: a request logged as a note, and the note saying no more.
    ("hollins_vane", "Ada Vane", "Hollins Mutual", "connection",
     "Connection request with note sent", "2026-10-08", LIMIT),
]


def _save(path, rows, columns, add):
    with open(path, encoding="utf-8", newline="") as fh:
        have = list(csv.DictReader(fh))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in have + add:
            w.writerow({k: r.get(k, "") for k in columns})


def write_people(state, people):
    contacts, threads = [], []
    for cid, name, company, channel, summary, sent, notes in people:
        first = name.split()[0]
        contacts.append(dict(
            dict.fromkeys(CONTACTS, ""), contact_id=cid, name=name, title="Data Lead",
            company=company, company_key=company.lower(), location=HOME,
            linkedin_url="https://www.linkedin.com/in/" + cid.replace("_", "-") + "-example",
            tier="2", route="cold", route_detail="Leaders search, " + sent,
            channel=channel, status="awaiting_reply",
            first_contacted=sent, next_action=WAITING.replace("8 Oct", _day(sent)),
            next_action_due=(datetime.date.fromisoformat(sent)
                             + datetime.timedelta(days=14)).isoformat(), notes=notes))
        threads.append({"contact_id": cid, "date": sent, "direction": "out",
                        "channel": "linkedin", "scenario": "first_note", "summary": summary,
                        "full_text": NOTE.format(n=first)})
    _save(os.path.join(state, "network_contacts.csv"), None, CONTACTS, contacts)
    _save(os.path.join(state, "network_threads.csv"), None, THREADS, threads)


def _day(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def page_model(root, people):
    state = app_state.small(os.path.join(root, "state"))
    profile = app_state.profile_copy(os.path.join(root, "profile"))
    write_people(state, people)
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, APP, "model", "--now", NOW], env=env,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    return page_model(str(tmp_path_factory.mktemp("request")), PEOPLE)


def person(m, cid):
    return next(p for p in m["people"] if p["id"] == cid)


def due_of(m, cid):
    return [d for d in m["due"] if cid in str(d.get("id")) or d.get("item") == cid
            or cid in json.dumps(d.get("work") or {})]


def follow_ups(m, name):
    """To do's rows offering a follow-up to `name`: "Follow up with ..." or its button."""
    return [d for d in m["due"] if name in str(d.get("title") or "")
            and ("Follow up" in str(d.get("title")) or d.get("kind") in ("nudge", "follow_up"))]


@pytest.mark.parametrize("cid", ["brackenhill_ardent", "quillmere_soto", "fennick_lowe"])
def test_a_request_nobody_accepted_reads_request_pending_with_nothing_to_send(model, cid):
    p = person(model, cid)
    assert p["status_word"] == "Request pending", p
    assert p["owed"] is None and p["group"] == "held", p
    assert p["hold"] == "Your connection request has not been accepted yet", p
    assert not follow_ups(model, p["first_name"]), follow_ups(model, p["first_name"])
    assert not due_of(model, cid), due_of(model, cid)
    assert cid not in {x.get("contact") for x in model["messages"]}


def test_three_weeks_on_it_is_one_to_withdraw_never_a_follow_up(model):
    p = person(model, "larchway_pym")
    assert p["status_word"] == "Request pending" and p["owed"] is None, p
    assert not follow_ups(model, "Cato"), follow_ups(model, "Cato")
    withdraw = [d for d in model["due"] if d.get("kind") == "withdraw"]
    assert withdraw and "larchway_pym" in json.dumps(withdraw), withdraw


def test_a_first_message_to_someone_connected_is_followed_up_as_before(model):
    p = person(model, "ormsby_reyes")
    assert p["status_word"] == "Waiting for a reply", p
    assert (p["owed"] or {}).get("kind") == "follow_up", p
    assert follow_ups(model, "Tove"), [d.get("title") for d in model["due"]]
    # How she was found says its day in words, as "you wrote 8 Oct" beside it does.
    row = follow_ups(model, "Tove")[0]
    assert "Leaders search, 8 Oct" in row["context"] and "2026-" not in row["context"], row


def test_the_engine_reads_the_request_from_the_record_on_every_path(tmp_path, monkeypatch):
    """state.owed, the follow-up drafter and surface.held, from the contact's row."""
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import followup_drafts
    import open_actions
    import state
    import surface
    rows = [{"contact_id": "brackenhill_ardent", "date": "2026-10-08", "direction": "out",
             "channel": "linkedin", "scenario": "first_note", "summary": "message",
             "full_text": NOTE.format(n="Ilsa")}]
    her = {"contact_id": "brackenhill_ardent", "name": "Ilsa Ardent",
           "company": "Brackenhill Insurance", "channel": "connection",
           "status": "awaiting_reply", "next_action": WAITING, "next_action_due": "2026-10-22"}
    assert state.request_pending(rows) is None          # the rows alone: a message
    assert state.request_pending(rows, her) == datetime.date(2026, 10, 8)
    today = datetime.date(2026, 10, 25)
    assert state.owed([her], rows, today) == []
    assert [i["kind"] for i in state.owed([her], rows, datetime.date(2026, 10, 30))] == [
        "request_pending"]
    items = open_actions.due_items([her], rows, [], today)
    assert not [i for i in followup_drafts.drafts(items, [her], rows, [], today.isoformat())
                if i.get("contact_id") == "brackenhill_ardent"]
    assert surface.held(her, rows, "awaiting_reply")["why"] == "request"
    # Once she is connected (a message logged after it, an acceptance), it is a message again.
    accepted = rows + [{"contact_id": "brackenhill_ardent", "date": "2026-10-10",
                        "direction": "in", "channel": "linkedin",
                        "scenario": "connection_accepted", "summary": "", "full_text": ""}]
    assert state.request_pending(accepted, her) is None


def test_a_record_saying_no_more_messages_is_never_offered_one(model):
    p = person(model, "tamsworth_quell")
    assert p["group"] == "leave" and (p["owed"] or {}).get("kind") == "close", p
    assert p["next"] == "Their record says no more messages: leave it unless they write back"
    assert not follow_ups(model, "Nell"), follow_ups(model, "Nell")
    assert not due_of(model, "tamsworth_quell"), due_of(model, "tamsworth_quell")
    assert "tamsworth_quell" not in {x.get("contact") for x in model["messages"]}


def test_the_issues_record_reads_request_pending(model):
    p = person(model, "hollins_vane")
    assert p["status_word"] == "Request pending" and p["owed"] is None, p
    assert not follow_ups(model, "Ada") and not due_of(model, "hollins_vane")


def test_the_due_list_the_limit_and_the_drafter_read_the_record_alike(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import followup_drafts
    import open_actions
    import state
    rows = [{"contact_id": "tamsworth_quell", "date": "2026-10-08", "direction": "out",
             "channel": "linkedin", "scenario": "first_note", "summary": "message",
             "full_text": NOTE.format(n="Nell")}]
    her = {"contact_id": "tamsworth_quell", "name": "Nell Quell", "company": "Tamsworth Bank",
           "channel": "linkedin", "status": "awaiting_reply", "next_action": WAITING,
           "next_action_due": "2026-10-22", "notes": LIMIT}
    today = datetime.date(2026, 10, 25)
    assert state.owed([dict(her, notes="invented")], rows, today)[0]["kind"] == "nudge"
    assert state.owed([her], rows, today) == []
    assert state.at_limit(her, rows) and state.why_undated(her, rows) == "limit"
    assert followup_drafts.leave_alone(her, {}) == 'their record says "Follow-up limit reached"'
    items = open_actions.due_items([her], rows, [], today)
    assert not [i for i in followup_drafts.drafts(items, [her], rows, [], today.isoformat())
                if i.get("contact_id") == "tamsworth_quell"]
    # A word from them is answered: a reply owed is never stopped by it.
    wrote = rows + [{"contact_id": "tamsworth_quell", "date": "2026-10-20", "direction": "in",
                     "channel": "linkedin", "scenario": "detailed_generous",
                     "summary": "replied", "full_text": "Happy to talk next week."}]
    assert [i["kind"] for i in state.owed([dict(her, status="replied_needs_response")], wrote,
                                          today)] == ["reply"]
