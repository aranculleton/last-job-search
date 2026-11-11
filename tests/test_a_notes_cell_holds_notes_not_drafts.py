"""A contact's notes hold notes, never past drafts: the check of the contacts names one that does.

Drafts live in documents/network/<id>/ (draft.md, draft.older.md, draft.not-needed.md), and no
command writes a draft into a contact's notes. Chats did it by hand: 30 rows in one book held
"superseded draft", the longest cell 4,681 characters (the audit of 2026-11-10, NW-31). Every
person is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402


def _row(cid, notes):
    return {"contact_id": cid, "name": cid.title(), "company": "Quayside Foods",
            "status": "awaiting_reply", "notes": notes}


def test_a_draft_or_a_long_notes_cell_is_named():
    book = [_row("drafty", "2026-10-01: superseded draft: Hi Ivo, hope you're well..."),
            _row("long", "met at the depot open day. " * 80),
            _row("fine", "met at the depot open day; prefers email")]
    found = {p["contact_id"]: p["detail"] for p in state.reconcile(book, [])
             if p["reason"] == "notes_hold_drafts"}
    assert sorted(found) == ["drafty", "long"], found
    assert "documents/network/drafty/" in found["drafty"], found
