"""The message log is read once for the whole contact book, never once a contact.

`resume_findings` and `open_actions.build` called `threads_for` (a pass over the whole log
and a sort) for every contact, and `state.py` runs the first twice: 4.7 seconds at 2,000
contacts and 8,000 messages, 15.4 at twice that. Every name here is invented.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import open_actions  # noqa: E402
from network import state  # noqa: E402  the module open_actions reads through


def _book(n):
    contacts = [{"contact_id": f"c{i}", "name": f"Wren Halloway{i}", "company": f"Acme {i % 7}",
                 "status": "awaiting_reply"} for i in range(n)]
    threads = [{"contact_id": f"c{i}", "date": "2026-10-01", "direction": "out",
                "channel": "message", "scenario": "", "summary": "First note sent",
                "full_text": "Hi Wren"} for i in range(n)]
    return contacts, threads


def _passes(monkeypatch, run):
    seen = {"n": 0}
    real = state.threads_for

    def counted(threads, cid):
        if len(threads) > 1:              # a pass over the whole log, not one person's rows
            seen["n"] += 1
        return real(threads, cid)

    monkeypatch.setattr(state, "threads_for", counted)
    run()
    return seen["n"]


def test_the_resume_checks_read_the_log_once(monkeypatch):
    contacts, threads = _book(120)
    assert _passes(monkeypatch, lambda: state.resume_findings(contacts, threads)) == 0


def test_the_view_of_everything_reads_the_log_once(monkeypatch):
    contacts, threads = _book(120)
    assert _passes(monkeypatch, lambda: open_actions.build(contacts, threads, [],
                                                           "2026-10-20")) == 0
