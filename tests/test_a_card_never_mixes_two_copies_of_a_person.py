"""A person's card never shows one copy's record beside another copy's answer.

Issue 242: a chat changed a person's record, and `app.py view` rewrote the page's short list
of people (`list~people~*`) and the messages from it, but kept the people section, which
another chat holding work not landed yet had drawn last (`holds_unlanded`, for up to
UNLANDED_KEEP_S). The card read the old record beside the new answer, and the chat had said
"Updated in Contacts". The people section, its whole list and the messages draw the same
people, so they are kept or written together: written when this chat's own change touched the
people since the kept one was drawn (the change shows on the card at once), kept otherwise.

The real path: `state.py set` changes the record and notes it (tools/touched.py), `app.py
view` draws the page from each chat's copy, and the store keeps the real one's rules. Every
person, employer and chat id is invented (tests/app_state.py's small search).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_a_reply_drafted_shows_on_its_card_before_it_lands as D  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

OWN = "session_EXAMPLEOTHERCHAT"         # another chat, its save not landed yet
WREN = "fernhill_freight_halloway"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def _set(ring, chat, *args):
    env = dict(ring.env(), LJS_CHAT=chat)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "state.py"),
                        "set", WREN, *args, "--today", "2026-10-25"], env=env,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def _doc(ring, doc_id):
    with open(os.path.join(ring.db, "screen", doc_id + ".json"), encoding="utf-8") as fh:
        return json.load(fh)["data"]


def _wren(ring):
    """Wren as the people section draws her card, and as the short list does."""
    card = next(p for p in _doc(ring, "people")["data"] if p["id"] == WREN)
    listed = [x for n in range(1, 9) if os.path.exists(os.path.join(ring.db, "screen",
                                                                    f"list~people~{n}.json"))
              for x in _doc(ring, f"list~people~{n}")["items"] if x["id"] == WREN]
    return card, listed[0]


def _drawn_by_another_chat_with_work_not_landed(ring):
    """The helper draws the page from master; then another chat, holding a save not landed
    yet, changes Wren's next step (her card only, never the short list) and draws it."""
    master = D._commit(ring.state, "master")
    got, ok = D._view(ring, R.CHAT, "2026-10-25T18:00:00Z", master, master)
    assert ok, got
    _set(ring, OWN, "--next-action", "Send the planning case study on Friday")
    theirs = D._commit(ring.state, "their next step, not landed")
    D._git(ring.state, "reset", "-q", "--hard", master)
    got, ok = D._view(ring, OWN, "2026-10-25T18:05:00Z", master, theirs)
    assert ok, got
    card, listed = _wren(ring)
    assert card["status"] == listed["status"] == "awaiting_reply", (card, listed)
    return master


def test_a_change_this_chat_made_shows_on_the_card_at_once(ring):
    master = _drawn_by_another_chat_with_work_not_landed(ring)
    # This chat closes Wren, as a chat answering "this one has gone quiet" does, and draws.
    _set(ring, R.CHAT, "--status", "gone_cold")
    got, ok = D._view(ring, R.CHAT, "2026-10-25T18:10:00Z", master, master)
    assert ok, got
    card, listed = _wren(ring)
    assert card["status"] == listed["status"] == "gone_cold", (card, listed)
    kept = got.get("kept_newer") or []
    assert not {"people", "messages", "due"} & set(kept), kept
    assert not any(k.startswith("list~people~") for k in kept), kept


def test_with_no_change_of_its_own_the_card_and_its_list_are_kept_together(ring):
    master = _drawn_by_another_chat_with_work_not_landed(ring)
    # The record moved with no note of this chat's (another chat's change, logged by hand).
    import csv
    path = os.path.join(ring.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["contact_id"] == WREN:
            r["status"] = "gone_cold"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    got, ok = D._view(ring, R.CHAT, "2026-10-25T18:10:00Z", master, master)
    assert ok, got
    card, listed = _wren(ring)
    assert card["status"] == listed["status"] == "awaiting_reply", (card, listed)
    kept = got.get("kept_newer") or []
    assert "people" in kept and any(k.startswith("list~people~") for k in kept), kept
