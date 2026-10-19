"""The brief's due list counts every reply someone is waiting for.

`open_actions.py --due` is the list the brief opens with. It read only a date the
person had set themselves (`next_action_due`), so a contact who had answered, with no
date written beside them, was dropped, and the first line said "0 replies owed" while
a reply was owed. Everything `state.owed` lists is owed now, dated or not.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import open_actions  # noqa: E402

TODAY = "2026-03-11"


def _contact(cid, **kw):
    row = {"contact_id": cid, "name": kw.pop("name", "Shirin Example"), "company": "Kestrel Mutual",
           "status": "", "next_action": "", "next_action_due": "", "title": "", "notes": ""}
    row.update(kw)
    return row


def test_a_reply_owed_with_no_date_is_due_and_counted():
    contacts = [_contact("kestrel_example")]
    threads = [{"contact_id": "kestrel_example", "date": "2026-03-02", "direction": "out",
                "channel": "message", "summary": "first note", "full_text": "Hi"},
               {"contact_id": "kestrel_example", "date": "2026-03-06", "direction": "in",
                "channel": "message", "summary": "happy to talk", "full_text": "Happy to talk."}]
    items = open_actions.due_items(contacts, threads, [], TODAY)
    assert [(i["kind"], i["due"], i["late"]) for i in items] == [("reply", "2026-03-06", 5)]
    head = open_actions.render_due(items, TODAY).splitlines()[0]
    assert "1 replies owed" in head and "1 overdue" in head


def test_a_date_the_person_set_still_wins():
    contacts = [_contact("kestrel_example", next_action="answer about Thursday",
                         next_action_due="2026-03-11")]
    threads = [{"contact_id": "kestrel_example", "date": "2026-03-06", "direction": "in",
                "channel": "message", "summary": "free Thursday?", "full_text": "Free Thursday?"}]
    items = open_actions.due_items(contacts, threads, [], TODAY)
    assert [(i["kind"], i["due"], i["late"]) for i in items] == [("reply", "2026-03-11", 0)]


def test_nothing_owed_is_nothing_listed():
    contacts = [_contact("kestrel_example")]
    threads = [{"contact_id": "kestrel_example", "date": "2026-03-10", "direction": "out",
                "channel": "message", "summary": "first note", "full_text": "Hi"}]
    assert open_actions.due_items(contacts, threads, [], TODAY) == []
