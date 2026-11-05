"""Follow-ups queued together are one job: one claim, one command that drafts them all.

Tapping "Draft all" for nine follow-ups queued nine `follow_up` items, and the chat that
answers the page took each as a piece of work of its own: nine claims, each its own batch
(every claim writes the chat's heartbeat, so none could go together), then for each one the
networking skill's way of drafting a reply (the guidance, the gate, the draft saved, the item
finished, the page brought up to date), which the maintainer saw as "burning tokens"
(2026-11-05). Code already drafts a follow-up (tools/followup_drafts.py) and gates it; what was
missing was taking them together. Now the first follow-up waiting is claimed `with` every
other one, as drafts queued together are, and `app.py follow-ups` drafts every one this chat
holds in one run, keeps each clean draft where Messages shows it and finishes those items in
one batch; only what code could not write is left, all in one context block, and comes back
through the same command with `--written`. Every person, employer and chat id is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
from test_a_ring_is_answered_in_one_command import (CHAT, NOW, Ring, land, next_item,  # noqa: E402
                                                     parts, sends)

WORK = "the work below, claimed"


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    r.ids = app_state.nudges_due(r.state, 9)
    for n, cid in enumerate(r.ids):
        r.put("work", "follow_up~" + cid, {
            "kind": "follow_up", "status": "queued", "to": "either",
            "asked_at": f"2026-10-25T17:{n:02d}:00Z", "title": "Follow up with someone",
            "args": {"contact": cid}})
    yield r
    sys.path.remove(r.root)


def follow_ups(ring, d, *args, stdin=None):
    import subprocess
    import repo_files
    r = subprocess.run([*repo_files.python_on_github(os.path.join(ROOT, "tools", "app.py")),
                        "follow-ups", d, "--chat", CHAT, "--now", NOW, "--today", "2026-10-25",
                        *args], env=ring.env(), input=stdin, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def batches(said):
    return [ln for ln in said.splitlines() if ln.endswith(".json") and os.path.isfile(ln)]


def test_nine_follow_ups_are_one_claim_and_one_command(ring):
    d = ring.read("wake1")
    said = ring.wake(d)
    # One claim for all nine, gone with the check-in: nine claims were nine batches.
    assert len(sends(said)) == 1 and WORK in parts(said)[0], said
    assert all(land(ring, said)), said
    item = next_item(said)
    assert item["kind"] == "follow_up" and len(item["with"]) == 8, item
    assert "\nalso: " not in said
    for cid in ring.ids:
        doc = ring.stored("work", "follow_up~" + cid)["data"]
        assert doc["status"] == "running" and doc["claimed_by"] == CHAT, (cid, doc)
    # The wake names the one command, with this folder, and no skill to load.
    run = f"python3 tools/app.py follow-ups \"{d}\" --chat {CHAT}"
    assert run in said and "load no skill for them" in said, said
    assert "step 4's row says for a follow_up" not in said, said
    # One run drafts every one in code and finishes them in one batch.
    got = follow_ups(ring, d)
    assert got.startswith("follow-ups: 9 finished"), got
    sent = batches(got)
    assert len(sent) == 1, got
    import fake_db
    assert all(fake_db.apply(ring.db, b) for b in sent), got
    for cid in ring.ids:
        doc = ring.stored("work", "follow_up~" + cid)["data"]
        assert doc["status"] == "done", (cid, doc)
        assert doc["result"]["summary"].startswith("Your follow-up to "), doc
        # Each draft is where the page's Messages shows it.
        draft = os.path.join(ring.state, "documents", "network", cid, "draft.md")
        assert os.path.isfile(draft), cid
    assert f"app.py view \"{d}/view\"" in got and got.count("app.py view") == 1
    # Nothing is left for this chat: run again, it finds nothing.
    assert follow_ups(ring, d).startswith("follow-ups: 0 finished"), got


def test_a_follow_up_code_cannot_write_is_written_here_and_passed_back(ring, monkeypatch):
    """One the gate refuses comes back as one context block; what the chat writes for it goes
    through the same command, gated, kept on the card and finished."""
    d = ring.read("wake1")
    assert all(land(ring, ring.wake(d)))
    # Code's draft for one is refused: a draft waiting for them that breaks the gate.
    bad = ring.ids[0]
    path = os.path.join(ring.state, "documents", "network", bad, "draft.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x" * 900 + "\n")
    got = follow_ups(ring, d)
    assert "8 finished" in got and "1 to write here" in got, got
    assert f"to write: {bad}" in got and "--written -" in got, got
    import fake_db
    assert all(fake_db.apply(ring.db, b) for b in batches(got)), got
    assert ring.stored("work", "follow_up~" + bad)["data"]["status"] == "running"
    first = bad.split("_")[-1]
    text = ("Hi there, following up on my note from September. How is the analytics team "
            "set up these days?")
    again = follow_ups(ring, d, "--written", "-",
                       stdin=json.dumps([{"id": bad, "text": text}]))
    assert again.startswith("follow-ups: 1 finished"), again
    assert all(fake_db.apply(ring.db, b) for b in batches(again)), again
    assert ring.stored("work", "follow_up~" + bad)["data"]["status"] == "done"
    with open(path, encoding="utf-8") as fh:
        assert "following up on my note" in fh.read(), first


def _lives(ring, cid, row="", read=""):
    """Where `cid` lives: on their row, or only in what their profile showed when read."""
    import csv
    path = os.path.join(ring.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["contact_id"] == cid:
            r["location"] = row
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    if read:
        p = os.path.join(ring.state, "documents", "network", cid, "reading.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"name": cid, "location": read, "headline": "Head of Analytics"}, fh)


def test_no_follow_up_is_drafted_for_someone_living_where_the_persons_rules_exclude(ring):
    """A person's copy (2026-11-05): a follow-up was drafted to someone living in London,
    though the person's own rule skips people there. Most rows carry no location: it is in
    what their profile showed when it was read, and only first notes looked there. Now every
    follow-up reads it too: code drafts none, one written by hand is not kept, and the item is
    finished saying why, once. Someone with no location anywhere still gets their draft, with
    the card's "Where they live is not on record" line. (The example person is in Manchester;
    Canada is outside where they look.)"""
    away, read_away, unknown = ring.ids[0], ring.ids[1], ring.ids[2]
    _lives(ring, away, row="Toronto, Ontario, Canada")
    _lives(ring, read_away, read="Toronto, Ontario, Canada")
    _lives(ring, unknown)
    d = ring.read("wake1")
    assert all(land(ring, ring.wake(d)))
    text = ("Hi there, following up on my note from September. How is the analytics team "
            "set up these days?")
    got = follow_ups(ring, d, "--written", "-",
                     stdin=json.dumps([{"id": read_away, "text": text}]))
    import fake_db
    assert all(fake_db.apply(ring.db, b) for b in batches(got)), got
    assert "refused" not in got, got
    for cid in (away, read_away):
        doc = ring.stored("work", "follow_up~" + cid)["data"]
        assert doc["status"] == "done", (cid, doc)
        assert doc["result"]["summary"].startswith("No follow-up for "), doc
        assert "they are in Canada, outside where you are looking" in doc["result"]["summary"], doc
        assert not os.path.isfile(os.path.join(ring.state, "documents", "network", cid, "draft.md")), cid
    # Nowhere on record: drafted as before, and the card says to check where they live.
    assert os.path.isfile(os.path.join(ring.state, "documents", "network", unknown, "draft.md"))
    model = json.loads(ring.run("model", "--now", NOW))
    card = next(m for m in model["messages"] if m["contact"] == unknown)
    assert card["where_unknown"] is True, card
    assert not any(m["contact"] in (away, read_away) for m in model["messages"]), model["messages"]
