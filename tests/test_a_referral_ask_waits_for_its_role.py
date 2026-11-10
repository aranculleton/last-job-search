"""A referral ask is written for its role and its reader, never before there is a role.

The maintainer, 2026-11-10: "the two held referral asks are identical apart from the name and
employer ('following up on my note from October. In your last message you offered to refer
me... I'd still be glad of that'). That breaks the person's rules that every message is built
for its reader and that the wording stays plain. A held draft should either be drafted properly
for each person, or carry no draft text until the hold lifts and it's written for the actual
role." Code wrote that follow-up, one sentence for everyone who had offered to refer the
person. Now someone who offered waits on hold until a role is posted at their employer, with
no words on their card; once one is, the chat writes the ask for that role from what they
offered; a draft that is another's with the name and the employer swapped is refused; and the
drafts already on cards from before are set aside, kept, by a profile upgrade.

Ana and her thread are tests/test_a_follow_up_follows_the_last_message.py's: she offered to
refer Morgan, and Morgan's note of August has no answer. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import followup_drafts  # noqa: E402
import person  # noqa: E402
import profile_upgrades  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402
from test_a_follow_up_follows_the_last_message import CID, thread  # noqa: E402,F401

DAY = "2026-09-04"
WREN = "fernhill_freight_halloway"
TEMPLATE = ("Hi %s, following up on my note from August. In your last message you offered to "
            "refer me if a role came up at %s, and I'd still be glad of that. If one does, would "
            "it be all right to send you the link?")
OWN = ("Hi Wren, following up on my note from September. You mentioned the Manchester team was "
       "still finding its feet: has the planning work settled into a weekly rhythm yet?")


def _item(rows=()):
    items, contacts, threads, tracker = followup_drafts.load(DAY)
    got = followup_drafts.drafts(items, contacts, threads, tracker, DAY)
    return next(i for i in got if i.get("contact_id") == CID), got


def _row(cid):
    return next(c for c in state.load_contacts() if c["contact_id"] == cid)


@pytest.fixture
def aside():
    """Whatever a test leaves waiting on Wren's card is taken off again."""
    folder = os.path.dirname(reading.draft_path(WREN))
    had = os.path.isdir(folder)
    yield
    for name in ("draft.md", state.PARKED, state.PARKED_WAS, ".draft_answers.json"):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            os.remove(path)
    if not had and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)


def test_their_offer_with_no_role_posted_is_held_and_nothing_is_written(thread):  # noqa: F811
    item, got = _item()
    draft = item["draft"]
    assert draft["status"] == "none" and draft["text"] == "" and draft["hold_role"] is True, draft
    assert "none is posted at Kestrel Mutual yet" in draft["why"]
    # Kept: nothing goes on her card, and she is on hold on her record, with the day it was
    # made and the one message of hers it was made on, so the follow-up stops falling due and
    # the page lists her under On hold, while a message she sends later is still owed a reply.
    assert followup_drafts.keep_drafted(got) == []
    assert not os.path.isfile(reading.draft_path(CID))
    assert _row(CID)["next_action"] == ("Hold until a role is posted at Kestrel Mutual: they "
                                        "offered to refer you (since %s, after 1 from them)"
                                        % person.today().isoformat())
    assert state.role_hold(_row(CID)["next_action"])
    # On hold, nothing is due for her any more.
    items, *_ = followup_drafts.load(DAY)
    assert not [i for i in items if i.get("contact_id") == CID and not i.get("held")]


def test_once_a_role_is_posted_the_chat_writes_the_ask_for_that_role(thread, monkeypatch):  # noqa: F811
    posted = [{"company": "Kestrel Mutual", "title": "Pricing Analyst (Manchester)", "fit": 74,
               "first_seen": "2026-08-30", "url": "https://jobs.example/kestrel/pricing"}]
    monkeypatch.setattr(followup_drafts, "newest_round_rows", lambda: posted)
    draft = _item()[0]["draft"]
    assert draft["status"] == "write" and draft["who"] == "here" and draft["text"] == "", draft
    assert "Kestrel Mutual has posted Pricing Analyst" in draft["why"]
    assert "compose.referral_ask" in draft["why"] and "hold_role" not in draft


def test_a_draft_that_is_anothers_with_the_name_swapped_is_refused(thread, aside):  # noqa: F811
    ana = TEMPLATE % ("Ana", "Kestrel Mutual")
    wren = TEMPLATE % ("Wren", "Fernhill Freight")
    others = {WREN: (wren, "Wren Halloway", "Fernhill Freight")}
    said = followup_drafts.same_but_for_name(ana, CID, name="Ana Rook", company="Kestrel Mutual",
                                             others=others)
    assert said.startswith("the same words as your draft to Wren, with the name and the "
                           "employer swapped"), said
    # Words written for this reader are theirs, whoever else is waiting.
    assert followup_drafts.same_but_for_name(OWN, WREN, name="Wren Halloway",
                                             company="Fernhill Freight",
                                             others={CID: (ana, "Ana Rook", "Kestrel Mutual")}) == ""
    # On the door every hand-written draft goes through (`check`, which `reply.py finish` and
    # the follow-up work run): the second of two in one batch, and one against a card's draft.
    contacts, threads = state.load_contacts(), state.load_threads()
    got = followup_drafts.check([{"id": WREN, "text": wren, "kind": "nudge"},
                                 {"id": CID, "text": ana, "kind": "nudge"}], contacts, threads, DAY)
    told = {r["id"]: [f for f in r["findings"] if f.startswith("not_written_for_its_reader")]
            for r in got}
    assert not told[WREN] and len(told[CID]) == 1 and not got[1]["ok"], got
    os.makedirs(os.path.dirname(reading.draft_path(WREN)), exist_ok=True)
    with open(reading.draft_path(WREN), "w", encoding="utf-8") as fh:
        fh.write(wren + "\n")
    got = followup_drafts.check([{"id": CID, "text": ana, "kind": "nudge"}], contacts, threads, DAY)
    assert [f for f in got[0]["findings"] if f.startswith("not_written_for_its_reader")], got


def test_drafts_written_before_their_role_are_set_aside_by_an_upgrade(thread, aside):  # noqa: F811
    for cid, text in ((CID, TEMPLATE % ("Ana", "Kestrel Mutual")),
                      (WREN, TEMPLATE % ("Wren", "Fernhill Freight"))):
        os.makedirs(os.path.dirname(reading.draft_path(cid)), exist_ok=True)
        with open(reading.draft_path(cid), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    assert sorted(c for c, _why in followup_drafts.drafts_before_a_role()) == sorted([CID, WREN])
    assert profile_upgrades._drafts_before_a_role() == \
        "2 draft(s) were written before the role they wait for"
    said = followup_drafts.set_aside_before_a_role()
    assert len(said) == 2
    for cid in (CID, WREN):
        folder = os.path.dirname(reading.draft_path(cid))
        # Kept, never deleted, and off the card; its person waits for a role, on hold.
        assert not os.path.exists(reading.draft_path(cid))
        with open(os.path.join(folder, state.PARKED), encoding="utf-8") as fh:
            assert "you offered to refer me" in fh.read()
        assert state.role_hold(_row(cid)["next_action"]), _row(cid)
    assert followup_drafts.drafts_before_a_role() == []
    assert profile_upgrades._drafts_before_a_role() == ""
    upgrade = next(u for u in profile_upgrades.REGISTRY if u.id == "drafts-before-a-role")
    assert upgrade.needs == "nobody" and upgrade.cost == "instant"


def test_a_message_written_for_them_ends_the_wait_and_is_never_set_aside(thread):  # noqa: F811
    import reply
    _item_, got = _item()
    followup_drafts.keep_drafted(got)
    assert state.role_hold(_row(CID)["next_action"])
    # The role is posted and the ask is written for it: saved on her card, the wait is over
    # on her row, and the upgrade that sets aside drafts written before their role leaves it.
    reply.save_draft(CID, "Hi Ana, Kestrel has posted a Pricing Analyst role in Manchester. "
                          "You kindly said to send one over: would you be comfortable referring "
                          "me for it?\n\nhttps://jobs.example/kestrel/pricing")
    assert _row(CID)["next_action"] == "" and os.path.isfile(reading.draft_path(CID))
    assert followup_drafts.drafts_before_a_role() == []
    # Words of the person's own about an offer are theirs: only code's old follow-up, word
    # for word, is taken for a template.
    assert not followup_drafts._OFFER_TEMPLATE.search(
        "Hi Ana, you offered to refer me last year and I'd still be glad of that.")
