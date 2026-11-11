"""Someone on hold is in a group of their own, owes nothing, and comes back by themselves.

The maintainer, 2026-11-10: "Held notes stay in the main list, and look like work to do ...
notes on hold (two people, both waiting for a fitting role to be posted) still show among the
people to act on. They have the full draft open, a 'Send it anyway' link and a 'Talking'
badge ... held notes move to their own collapsed group at the bottom ('On hold: 2, waiting for
a role to be posted'), with the draft folded away. They come back up to the list by themselves
once the hold lifts. They also don't count towards 'to send' or 'need you'." And the two held
drafts were one message with the name and the employer swapped: a hold that waits for a role
carries no draft at all, and the referral ask is written for the role once it is posted.

The engine's half: where each person stands, the counts, To do's rows, and the lift, on the
real path (`app.py model` over a search's own files). The page's half is
tests/test_the_on_hold_group_is_last_and_folded.py. Every person and employer is invented
(tests/app_state.py's small search).
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402

WREN = "fernhill_freight_halloway"        # written to on 21 September, no answer, a follow-up due
DRAFT = "Hi Wren, following up on my note from September. How is the Manchester team settling in?"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _set(search, cid, **fields):
    path = os.path.join(search.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["contact_id"] == cid:
            r.update(fields)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _draft(search, cid, text):
    folder = os.path.join(search.state, "documents", "network", cid)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "draft.md"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


def _model(search, now=NOW):
    return json.loads(search.run("model", "--now", now))


def _person(m, cid):
    return next(p for p in m["people"] if p["id"] == cid)


def test_someone_on_hold_owes_nothing_and_is_counted_nowhere(search):
    _draft(search, WREN, DRAFT)
    before = _model(search)
    assert _person(before, WREN)["group"] == "follow" and before["to_send"]["n"] == 2
    assert any(d.get("item") == WREN or WREN in d["id"] for d in before["due"])
    _set(search, WREN, next_action="Hold until 2026-11-23: Wren is away until then",
         next_action_due="2026-11-23")
    m = _model(search)
    p = _person(m, WREN)
    assert p["group"] == "held" and p["owed"] is None, p
    assert p["on_hold"] == {"said": "On hold: Wren is away until then. Claude checks again on "
                                    "Mon 23 Nov.", "role": False, "until": "2026-11-23"}
    # Last on the list, and counted in nothing: not to send, not needing you, not drafted.
    assert m["people"][-1]["id"] == WREN
    assert m["people_count"]["on_hold"] == {"n": 1, "why": None}
    assert m["people_count"]["need"] == before["people_count"]["need"]
    assert m["people_count"]["drafted"] == before["people_count"]["drafted"] - 1
    assert m["to_send"]["n"] == 1 and "msg-" + WREN not in m["to_send"]["ids"]
    # The draft is kept, on hold, with the one way to send it anyway on the page.
    msg = next(x for x in m["messages"] if x["contact"] == WREN)
    assert msg["hold_why"] == "person_hold" and msg["hold"] == p["on_hold"]["said"]
    # Never a To do row, so never in the Brief's lists either.
    assert not [d for d in m["due"] if WREN in json.dumps(d)], m["due"]
    # The day it lifts, they are back where their conversation puts them, by themselves.
    back = _model(search, "2026-11-23T18:00:00Z")
    assert _person(back, WREN)["group"] == "follow" and _person(back, WREN)["on_hold"] is None
    assert "msg-" + WREN in back["to_send"]["ids"]


def _post_a_role(search, company, title="Supply Chain Analyst"):
    path = os.path.join(search.state, "documents", "rounds", "r9.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    rows.append({"company": company, "title": title, "fit": 78, "first_seen": "2026-10-24",
                 "date": "2026-10-24", "url": "https://jobs.example/fernhill/supply-chain",
                 "location": "Manchester"})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)


def test_a_hold_for_a_role_carries_no_draft_and_lifts_when_one_is_posted(search):
    import state
    _draft(search, WREN, DRAFT)
    _set(search, WREN, next_action=state.ROLE_HOLD % "Fernhill Freight"
         + ": they offered to refer you", next_action_due="")
    m = _model(search)
    p = _person(m, WREN)
    assert p["group"] == "held" and p["owed"] is None
    assert p["on_hold"]["role"] is True
    assert p["on_hold"]["said"] == ("On hold until a role is posted at Fernhill Freight: they "
                                    "offered to refer you. Claude writes this when a role is "
                                    "posted.")
    # No words on their card until there is a role to write them for.
    assert not [x for x in m["messages"] if x["contact"] == WREN]
    assert m["people_count"]["on_hold"] == {"n": 1, "why": "waiting for a role to be posted"}
    assert m["to_send"]["n"] == 1
    # The draft written before the role is set aside, kept, by the app's own upgrade (as it is
    # the moment a hold for a role is recorded).
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state, LJS_COPY="private")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "followup_drafts.py"),
                        "role-holds"], env=env, capture_output=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0 and "1 draft(s)" in r.stdout, r.stdout + r.stderr
    folder = os.path.join(search.state, "documents", "network", WREN)
    assert not os.path.exists(os.path.join(folder, "draft.md"))
    assert os.path.exists(os.path.join(folder, "draft.not-needed.md"))
    # A role is posted at their employer: back on the list, the referral ask their one step.
    _post_a_role(search, "Fernhill Freight")
    m = _model(search)
    p = _person(m, WREN)
    assert p["group"] == "now" and p["on_hold"] is None, p
    assert p["owed"]["kind"] == "referral" and p["owed"]["label"] == "Draft the referral ask"
    assert p["owed"]["args"] == {"contact": WREN, "kind": "referral_ask",
                                 "role": "Supply Chain Analyst",
                                 "url": "https://jobs.example/fernhill/supply-chain"}
    assert p["next"] == "Fernhill Freight has posted Supply Chain Analyst: ask them to refer you"
    assert m["people_count"]["on_hold"]["n"] == 0
    assert m["people_count"]["need"] == 2


def _they_wrote(search, cid, day, text):
    path = os.path.join(search.state, "network_threads.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        head = next(csv.reader(fh))
    with open(path, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=head).writerow(dict.fromkeys(head, "") | {
            "contact_id": cid, "date": day, "direction": "inbound", "channel": "linkedin",
            "scenario": "reply", "summary": "replied", "full_text": text})


def test_a_hold_holds_a_reply_only_until_they_write_again(search):
    import state
    _they_wrote(search, WREN, "2026-10-20", "Hi Morgan, nothing open on my team just now. "
                "If a role comes up, send it over and I will refer you.")
    # A hold with no day of its own never holds a reply they are owed.
    _set(search, WREN, next_action=state.ROLE_HOLD % "Fernhill Freight", next_action_due="")
    m = _model(search)
    assert _person(m, WREN)["group"] == "now" and _person(m, WREN)["on_hold"] is None
    assert [d for d in m["due"] if d["kind"] == "reply" and WREN in d["id"]]
    # One made after reading their message holds the reply to it: on hold, off To do.
    _set(search, WREN, next_action=state.hold_since(state.ROLE_HOLD % "Fernhill Freight",
                                                    "2026-10-21"))
    m = _model(search)
    p = _person(m, WREN)
    assert p["group"] == "held" and p["on_hold"]["role"] is True, p
    assert "since" not in p["on_hold"]["said"], p["on_hold"]
    assert not [d for d in m["due"] if WREN in d["id"]], m["due"]
    assert m["people_count"]["need"] == 1
    # They write again: that is news the hold never saw, and a reply is owed.
    _they_wrote(search, WREN, "2026-10-24", "Hi Morgan, a quick question: are you still looking?")
    m = _model(search)
    assert _person(m, WREN)["group"] == "now" and _person(m, WREN)["on_hold"] is None
    assert [d for d in m["due"] if d["kind"] == "reply" and WREN in d["id"]]


def test_a_reply_the_same_day_as_the_hold_is_still_owed(search):
    """A hold dated by its day alone could not see a message of theirs sent later that day, so
    the reply stayed held until they wrote again (the held-notes review, 2026-11-10)."""
    import state
    _they_wrote(search, WREN, "2026-10-21", "Hi Morgan, nothing open on my team just now. "
                "If a role comes up, send it over and I will refer you.")
    msgs = [r for r in state.load_threads(os.path.join(search.state, "network_threads.csv"))
            if r["contact_id"] == WREN]
    held = state.hold_since(state.ROLE_HOLD % "Fernhill Freight", "2026-10-21", msgs)
    assert held.endswith("(since 2026-10-21, after 1 from them)"), held
    assert state.hold_stands(held, msgs)
    _set(search, WREN, next_action=held)
    assert _person(_model(search), WREN)["group"] == "held"
    # They write again the same day: owed a reply, though the day is the hold's own.
    _they_wrote(search, WREN, "2026-10-21", "Sorry, one more thing: are you open to contract work?")
    m = _model(search)
    assert _person(m, WREN)["group"] == "now" and _person(m, WREN)["on_hold"] is None
    assert [d for d in m["due"] if d["kind"] == "reply" and WREN in d["id"]]
