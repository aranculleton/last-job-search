"""A greeting by the name before the brackets, or the one inside them, is the right name.

From a person's copy, 2026-11-11: three follow-ups that greeted their reader correctly were
marked on the page as greeting them by the wrong name, and a rewrite was queued for each. The
card's check, and the gate a rewrite passes on the page, were handed the one name a greeting
would pick (the bracketed one, where the brackets hold a name) instead of the reader's whole
name, so "Hi Ottilie" to "Ottilie (Lark) Fennimore" was read against "Lark" alone. A bracket
holds a nickname, a maiden name or a romanised name, never the only name to greet them by.

Now both checks read the whole name, as the drafting gate always did: a greeting by either
name passes, and a greeting to somebody else is still caught. Every person, employer and
chat id is invented.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
import repo_files  # noqa: E402
from test_a_ring_is_answered_in_one_command import NOW, Ring  # noqa: E402

# (whole name, a greeting by the name before the brackets, one by the name inside them).
# The last two have no brackets: an ordinary name, and one written all in small letters.
NAMES = [("Ottilie (Lark) Fennimore", "Ottilie", "Lark"),
         ("Jia (WenLi) Quarrendon", "Jia", "WenLi"),
         ("ngozi (zee)", "Ngozi", "Zee"),
         ("Wren Halloway", "Wren", "Wren"),
         ("rhian pellow", "Rhian", "Rhian")]
WRONG = "Tamsin"
BODY = ("following up on my note from September. What is the team working on this quarter?")


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    r.ids = app_state.nudges_due(r.state, len(NAMES))
    path = os.path.join(r.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    whole = dict(zip(r.ids, (n for n, _a, _b in NAMES)))
    for row in rows:
        if row["contact_id"] in whole:
            row["name"] = whole[row["contact_id"]]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    yield r
    sys.path.remove(r.root)


def _drafts(ring, greetings):
    for cid, first in zip(ring.ids, greetings):
        path = os.path.join(ring.state, "documents", "network", cid, "draft.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"Hi {first}, {BODY}\n")


def _cards(ring) -> dict:
    model = json.loads(ring.run("model", "--now", NOW))
    return {m["contact"]: m for m in model["messages"] if m.get("contact") in ring.ids}


def _wrong_name(card) -> bool:
    return any(b["rule"] == "greeting_wrong_name" for b in card.get("blocked") or []) or \
        "wrong name" in json.dumps(card.get("fix") or {})


def _gate(ring, greetings) -> dict:
    """The gate a rewrite on the page passes (tweak.message_gate), run as the page's chat runs
    it, in a process of its own on this copy."""
    pairs = [[cid, f"Hi {first}, {BODY}"] for cid, first in zip(ring.ids, greetings)]
    code = ("import json, sys\n"
            f"sys.path[:0] = [{os.path.join(ROOT, 'tools')!r}, "
            f"{os.path.join(ROOT, 'tools', 'network')!r}]\n"
            "import tweak\n"
            "out = {cid: tweak.message_gate(text, 'follow_up', cid)[0]\n"
            "       for cid, text in json.loads(sys.stdin.read())}\n"
            "print(json.dumps(out))\n")
    driver = os.path.join(ring.root, "message_gate.py")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write(code)
    r = subprocess.run([*repo_files.python_on_github(driver)], env=ring.env(),
                       input=json.dumps(pairs), capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("which", [1, 2], ids=["before the brackets", "inside the brackets"])
def test_a_greeting_by_either_name_is_not_the_wrong_name(ring, which):
    greetings = [n[which] for n in NAMES]
    _drafts(ring, greetings)
    cards = _cards(ring)
    assert sorted(cards) == sorted(ring.ids), cards
    for cid, (name, *_g) in zip(ring.ids, NAMES):
        assert not _wrong_name(cards[cid]), (name, cards[cid]["blocked"], cards[cid]["fix"])
        assert not cards[cid]["blocked"], (name, cards[cid]["blocked"])
    for cid, found in _gate(ring, greetings).items():
        assert not any(f.startswith("greeting_wrong_name") for f in found), (cid, found)


def test_a_greeting_to_somebody_else_is_still_the_wrong_name(ring):
    _drafts(ring, [WRONG] * len(NAMES))
    cards = _cards(ring)
    for cid, (name, *_g) in zip(ring.ids, NAMES):
        assert _wrong_name(cards[cid]), (name, cards[cid]["blocked"])
    for cid, found in _gate(ring, [WRONG] * len(NAMES)).items():
        assert any(f.startswith("greeting_wrong_name") for f in found), (cid, found)
