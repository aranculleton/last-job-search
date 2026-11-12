"""Before a reply to an offer to refer, or a follow-up to someone at an employer, is drafted,
that employer's open roles are checked against the person's search (issue 233).

A contact wrote "if you see any positions that interest you, let me know and I'd be happy to
refer you", and the reply only thanked them. Their employer's board was on file, with a role
that fitted, and nothing looked at it: the person had to ask "did you scan the roles to see if
there's anything he can refer?". Now the board profile/boards.py names is read the way a round
reads it (here a fake Greenhouse board, through tools/offline_boards.py, so nothing reaches the
network), each role scored the way the search scores it, and:

- a role that fits makes the message a referral ask naming it, with the job on the card;
- none fitting leaves the plain message, says "No open role there fits yet" so the person knows
  it was checked, and puts the contact on the wait for a role (state.ROLE_HOLD) that a later
  search lifts, when the ask is written for the role it found;
- an employer with no board on file is said so in one line, never guessed at.

Ana, Kestrel Mutual and her thread are tests/test_a_follow_up_follows_the_last_message.py's:
she offered to refer Morgan a year ago and Morgan's note of August has no answer. Every person,
employer and role is invented.
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import ats_boards  # noqa: E402
import employer_roles  # noqa: E402
import followup_drafts  # noqa: E402
import state  # noqa: E402
from offline_boards import offline  # noqa: E402
from test_a_follow_up_follows_the_last_message import CID, thread  # noqa: E402,F401

DAY = "2026-09-04"
BOARD = {"Kestrel Mutual": ("greenhouse", "kestrelmutual")}
ROUTE = "boards-api.greenhouse.io/v1/boards/kestrelmutual/jobs"
PRICING = {"id": 9101, "title": "Pricing Data Analyst",
           "absolute_url": "https://boards.greenhouse.io/kestrelmutual/jobs/9101",
           "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-08-30",
           "content": "&lt;p&gt;Kestrel Mutual is hiring a Pricing Data Analyst.&lt;/p&gt;"
                      "&lt;ul&gt;&lt;li&gt;Strong SQL and Python&lt;/li&gt;&lt;li&gt;Demand "
                      "forecasting and pricing models&lt;/li&gt;&lt;li&gt;Power BI reporting "
                      "for stakeholders&lt;/li&gt;&lt;/ul&gt;"}
UNFIT = [{"id": 9102, "title": "HGV Driver",
          "absolute_url": "https://boards.greenhouse.io/kestrelmutual/jobs/9102",
          "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-08-30",
          "content": "&lt;p&gt;Night runs between our depots.&lt;/p&gt;"},
         {"id": 9103, "title": "Receptionist",
          "absolute_url": "https://boards.greenhouse.io/kestrelmutual/jobs/9103",
          "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-08-30",
          "content": "&lt;p&gt;Front desk and visitors.&lt;/p&gt;"}]


@pytest.fixture
def board(monkeypatch):
    """Kestrel Mutual's careers board on file, answered from canned jobs; read afresh."""
    monkeypatch.setattr(ats_boards, "BOARDS", dict(BOARD))
    # No search has found anything there: only the board can.
    monkeypatch.setattr(followup_drafts, "newest_round_rows", lambda today=None: [])
    employer_roles.forget()

    def serve(jobs):
        web = offline({ROUTE: {"jobs": jobs}})
        return web
    yield serve
    employer_roles.forget()


def _ana():
    items, contacts, threads, tracker = followup_drafts.load(DAY)
    got = followup_drafts.drafts(items, contacts, threads, tracker, DAY)
    return next(i for i in got if i.get("contact_id") == CID), got


def _row():
    return next(c for c in state.load_contacts() if c["contact_id"] == CID)


def test_a_fitting_role_on_their_board_makes_the_follow_up_a_referral_ask(thread, board):  # noqa: F811
    with board([PRICING] + UNFIT) as web:
        item, got = _ana()
    assert any(ROUTE in url for url, _ in web.calls)
    draft = item["draft"]
    # The ask is written for that one role, from what she offered, and the job is on the card.
    assert draft["status"] == "write" and draft["who"] == "here", draft
    assert "Kestrel Mutual has posted Pricing Data Analyst" in draft["why"]
    assert "compose.referral_ask" in draft["why"] and "hold_role" not in draft
    assert draft["role"]["title"] == "Pricing Data Analyst"
    assert draft["role"]["url"] == PRICING["absolute_url"]
    assert draft["role"]["fit"] >= followup_drafts.POSTING_FIT
    shown = followup_drafts.render(got)
    assert "job: Pricing Data Analyst at Kestrel Mutual" in shown and PRICING["absolute_url"] in shown
    # Nobody is put on hold: there is a role to ask about now.
    assert followup_drafts.hold_for_role(got) == []


def test_no_fitting_role_leaves_the_plain_wait_says_it_was_checked_and_watches(thread, board):  # noqa: F811
    with board(UNFIT):
        item, got = _ana()
    draft = item["draft"]
    assert draft["status"] == "none" and draft["text"] == "" and draft["hold_role"] is True
    assert "none is posted at Kestrel Mutual yet" in draft["why"]
    assert draft["roles_checked"].startswith(employer_roles.NONE_FITS), draft
    assert "2 open role(s) read on Kestrel Mutual's careers board" in draft["roles_checked"]
    assert "No open role there fits yet" in followup_drafts.render(got)
    # The watch: she waits on hold for a role at Kestrel Mutual, which a later search lifts.
    assert followup_drafts.hold_for_role(got) == [CID]
    assert state.role_hold(_row()["next_action"])
    assert "Hold until a role is posted at Kestrel Mutual" in _row()["next_action"]


def test_a_role_a_later_search_finds_lifts_the_watch_into_the_ask(thread, board, monkeypatch):  # noqa: F811
    with board(UNFIT):
        _item, got = _ana()
    followup_drafts.hold_for_role(got)
    posted = [{"company": "Kestrel Mutual", "title": "Pricing Data Analyst", "fit": 72,
               "first_seen": "2026-09-10", "url": PRICING["absolute_url"]}]
    monkeypatch.setattr(followup_drafts, "newest_round_rows", lambda today=None: posted)
    contact = _row()
    role = followup_drafts.role_for_offer(contact, "2026-08-24", posted)
    assert role["title"] == "Pricing Data Analyst"


def test_an_employer_with_no_board_is_said_so(thread, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ats_boards, "BOARDS", {})
    monkeypatch.setattr(followup_drafts, "newest_round_rows", lambda today=None: [])
    employer_roles.forget()
    with offline() as web:
        item, _got = _ana()
    assert web.calls == []
    draft = item["draft"]
    assert draft["hold_role"] is True
    assert draft["roles_checked"] == ("Kestrel Mutual has no careers board on file, so its "
                                      "open roles were not checked")


def test_an_ordinary_follow_up_checks_the_board_too(thread, board, monkeypatch):  # noqa: F811
    # The same thread with no offer in it: Ana answered once and the person's August note is
    # unanswered, so an ordinary follow-up is due.
    monkeypatch.setattr(followup_drafts, "their_offer", lambda msgs: None)
    with board([PRICING] + UNFIT):
        item, _got = _ana()
    draft = item["draft"]
    assert draft["status"] == "write" and "referral ask" in draft["why"], draft
    assert draft["role"]["title"] == "Pricing Data Analyst"
    employer_roles.forget()
    with board(UNFIT):
        item, got = _ana()
    draft = item["draft"]
    assert "role" not in draft
    assert draft["roles_checked"].startswith("No open role there fits yet"), draft
    assert "No open role there fits yet" in followup_drafts.render(got)


def test_the_reply_to_an_offer_names_the_role_or_says_none_fits(thread, board, tmp_path):  # noqa: F811
    import reply
    c = _row()
    with board([PRICING] + UNFIT):
        lines = reply.roles_to_refer(c, tracker=[])
    assert lines[0].startswith("open roles: Pricing Data Analyst is open on Kestrel Mutual's "
                               "careers board and fits your search"), lines
    assert "ask for the referral for Pricing Data Analyst" in lines[1]
    employer_roles.forget()
    with board(UNFIT):
        lines = reply.roles_to_refer(c, tracker=[])
    assert lines[0].startswith("open roles: No open role there fits yet"), lines
    assert "when a search finds one that fits, the referral ask is written for it" in lines[1]
    # Run as the chat runs it: prepare on her new message, an offer, prints the check.
    said = tmp_path / "ana.txt"
    said.write_text("Good to hear from you! If you see any positions that interest you, let me "
                    "know and I'd be happy to refer you.", encoding="utf-8")
    employer_roles.forget()
    out = io.StringIO()
    with board([PRICING]), redirect_stdout(out):
        assert reply.prepare([CID, "--text-file", str(said), "--date", DAY, "--today", DAY]) == 0
    assert "scenario: referral_offered" in out.getvalue(), out.getvalue()
    assert "open roles: Pricing Data Analyst is open on Kestrel Mutual's careers board" \
        in out.getvalue(), out.getvalue()
