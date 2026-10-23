"""`open_actions.py --due` reads the message log once, not once a contact.

It took 5 to 5.5 seconds on about 1,300 contacts and 8,500 messages (2026-10-23):
`state.owed`, `state.resumes_owed` and the status pass each called `threads_for` per
contact, and every call read the whole log, about 3,900 passes in all; `resumes_owed`
also matched every tracker row against the book once a contact. Each now builds one
index (`state.by_contact`) and matches the tracker once (`state.made_for_index`). The
answers are the same; only the number of passes changed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import open_actions  # noqa: E402

state = open_actions.state           # the module the due list itself calls

TODAY = "2026-03-11"


def _book(n):
    contacts, threads = [], []
    for i in range(n):
        cid = f"kestrel_example{i}"
        contacts.append({"contact_id": cid, "name": f"Shirin Example{i}", "company": "Kestrel Mutual",
                         "status": "", "next_action": "", "next_action_due": "", "title": "",
                         "notes": ""})
        threads.append({"contact_id": cid, "date": "2026-02-02", "direction": "out",
                        "channel": "message", "summary": "first note", "full_text": "Hi"})
        if i % 3 == 0:
            threads.append({"contact_id": cid, "date": "2026-03-06", "direction": "in",
                            "channel": "message", "summary": "happy to talk",
                            "full_text": "Happy to talk."})
        if i % 7 == 0:
            threads.append({"contact_id": cid, "date": "2026-03-09", "direction": "in",
                            "channel": "message", "summary": "send your resume",
                            "full_text": "Could you send me your resume?"})
    return contacts, threads


def test_the_index_holds_what_threads_for_returns_for_every_contact():
    contacts, threads = _book(40)
    threads = list(reversed(threads))           # file order is not date order
    index = state.by_contact(threads)
    for c in contacts:
        assert index.get(c["contact_id"], []) == state.threads_for(threads, c["contact_id"])


def test_the_due_list_does_not_read_the_log_once_a_contact(monkeypatch):
    contacts, threads = _book(120)
    before = open_actions.due_items(contacts, threads, [], TODAY)
    calls = []
    real = state.threads_for
    monkeypatch.setattr(state, "threads_for", lambda t, cid: calls.append(cid) or real(t, cid))
    after = open_actions.due_items(contacts, threads, [], TODAY)
    assert after == before and before
    # Only what is owed is looked at again one by one, never the whole book.
    assert len(calls) < len(contacts) // 2, len(calls)


def test_a_resume_made_for_a_contact_is_found_from_the_index():
    contacts, threads = _book(3)
    tracker = [{"company": "Kestrel Mutual", "role": "Data Analyst", "status": "drafted",
                "date": "2026-03-10", "cv_file": "cv/Shirin_Resume_KM.tex",
                "notes": "made for Shirin Example1 (kestrel_example1)"}]
    owed = state.resumes_owed(contacts, threads, tracker)
    assert [(o["contact_id"], o["made"]) for o in owed if o["made"]] == \
        [("kestrel_example1", "2026-03-10")]
    assert state.made_for_rows(tracker, contacts, "kestrel_example1") == tracker
    assert state.made_for_rows(tracker, contacts, "kestrel_example2") == []


def test_a_queued_note_at_an_employer_the_bar_rules_out_is_held_with_the_reason():
    contacts = [{"contact_id": "saltmarsh_example", "name": "Shirin Example",
                 "company": "Saltmarsh Casino", "status": "not_contacted",
                 "next_action": "Send: the note in their draft", "next_action_due": "2026-03-01",
                 "title": "", "notes": ""}]
    items = open_actions.due_items(contacts, [], [], TODAY)
    assert [i["contact_id"] for i in items] == ["saltmarsh_example"]
    assert items[0]["held"] and items[0]["held"][0].startswith("Saltmarsh Casino: a sector")
    assert "Blocked by holds" in open_actions.render_due(items, TODAY)
