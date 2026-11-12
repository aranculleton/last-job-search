"""A follow-up is written for its reader, or held: never stock lines offered as ready to send.

Issue 223, from one follow-up pack: most of its nudges were one of three stock sentences with
only the first name and the opener changed ("a quick follow-up to my note from October.
What's your team focused on these days, and what do you look for in people who join?"), and
the gate passed them as ready. One went to a thread that had run its course: the contact
pointed to the careers site, the person answered that he had applied, and 14 days later the
pack drafted "I'm still looking for roles", which gave them nothing to answer. Another went to
someone at an employer where a referral and interviews were under way, whose own record said
"no check-in, the conversation has moved to the colleague".

Now code's stock lines are flagged for the chat to write from the thread (never kept on the
card, refused when handed back unchanged, and set aside where an older run left them on a
card); a thread closed that way is held with the reason; and nobody at an employer with a live
process, or whose record says not to check in, is followed up. On the drafter's own path:
`followup_drafts.draft` with the rows the contact book, the log and the tracker carry. Every
person and employer is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import followup_drafts as F  # noqa: E402

TODAY = dt.date(2026, 10, 25).isoformat()
CID = "fernhill_halloway"


def _contact(cid=CID, title="Data Analyst", company="Fernhill Freight", name="Juno Halloway", **kw):
    row = {"contact_id": cid, "name": name, "title": title, "company": company,
           "location": "Manchester, England, United Kingdom", "channel": "linkedin",
           "status": "awaiting_reply", "next_action": "", "next_action_due": "", "notes": ""}
    row.update(kw)
    return row


def _nudge(cid=CID, since="2026-10-01"):
    return {"half": "contact", "kind": "nudge", "contact_id": cid,
            "name": "Juno Halloway (Fernhill Freight)", "status": "awaiting_reply", "since": since,
            "late": 10, "held": [], "quiet": False, "old": False, "text": "",
            "what": "One nudge if no reply", "key": "fernhill freight"}


OURS = {"contact_id": CID, "date": "2026-10-01", "direction": "outbound", "channel": "linkedin",
        "scenario": "first_note", "summary": "first note",
        "full_text": "Hi Juno, I build demand forecasts in Manchester. How is the planning team "
                     "at Fernhill set up?"}
THEIRS = {"contact_id": CID, "date": "2026-10-05", "direction": "inbound", "channel": "linkedin",
          "summary": "reply", "full_text": "Hi! I don't know that team well, to be honest. Have "
                                           "you looked at the careers site?"}
THANKS = {"contact_id": CID, "date": "2026-10-06", "direction": "outbound", "channel": "linkedin",
          "scenario": "reply", "summary": "reply",
          "full_text": "Thanks Juno, I have, and I've applied to the demand planning analyst role "
                       "there."}


def _draft(contact=None, thread=(OURS,), tracker=(), book=None, item=None, text=""):
    contact = contact or _contact()
    book = dict(book or {})
    book[contact["contact_id"]] = contact
    item = dict(item or _nudge(contact["contact_id"]))
    item["text"] = text
    return F.draft(item, book, {contact["contact_id"]: list(thread)}, list(tracker), {}, [],
                   today=TODAY)


# ------------------------------------------------------------------ stock lines

STOCK = ("Hi Juno, a quick follow-up to my note from October. What's your team focused on "
         "these days, and what do you look for in people who join?")
WRITTEN = ("Hi Juno, following up on my note from October. How did the autumn peak go for your "
           "planners at Fernhill this year?")


def test_code_s_stock_follow_up_is_flagged_to_write_and_never_kept_as_ready():
    d = _draft()
    assert d["source"] == "code" and d["status"] == "check", d
    assert any(w.startswith(F.STOCK + ":") for w in d["warnings"]), d["warnings"]
    assert F.stock_follow_up(d["text"], "Juno Halloway", "Fernhill Freight"), d["text"]
    got = [{"half": "contact", "contact_id": CID, "draft": d}]
    assert F.to_write_here(got) == [CID]          # listed for the chat to write
    assert F.keep_drafted(got) == []              # never put on the card as ready to send


def test_stock_lines_waiting_on_a_card_are_not_ready_and_a_written_one_is():
    assert _draft(text=STOCK)["status"] == "check"
    d = _draft(text=WRITTEN)
    assert d["source"] == "stored" and not any(w.startswith(F.STOCK) for w in d["warnings"]), d
    assert F.stock_follow_up(WRITTEN, "Juno Halloway", "Fernhill Freight") == ""


def test_stock_lines_handed_back_as_written_are_refused():
    contact = _contact()
    out = F.check([{"id": CID, "text": STOCK, "kind": "nudge"}], [contact],
                  [OURS], TODAY)
    assert out[0]["ok"] is False, out
    assert any(f.startswith("not_written_for_its_reader:") for f in out[0]["findings"]), out
    ok = F.check([{"id": CID, "text": WRITTEN, "kind": "nudge"}], [contact], [OURS], TODAY)
    assert not any("stock" in f for f in ok[0]["findings"]), ok


def test_stock_lines_an_older_run_left_on_a_card_are_set_aside():
    """The example's own contact, owed a follow-up, with code's stock lines on the card and no
    rules of the person's own for messages: listed, so the next sync sets it aside (kept)."""
    import reading
    wren = "fernhill_freight_halloway"
    path = reading.draft_path(wren)
    had = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    made = not os.path.isdir(os.path.dirname(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("Hi Wren, coming back to my note from September. How is your team set up at "
                     "the moment, and what's it working on this year?\n")
        assert wren in dict(F.unfitted_on_cards(today=TODAY)), F.unfitted_on_cards(today=TODAY)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(WRITTEN.replace("Juno", "Wren").replace("October", "September") + "\n")
        assert wren not in dict(F.unfitted_on_cards(today=TODAY))
    finally:
        if had is None:
            os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(had)
        # The folder it made goes too: left empty, a later test in this worker took it for
        # one of the example's own and kept the draft it wrote there (CI, 2026-11-11).
        if made:
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)


# ------------------------------------------------------------------ a closed thread

def test_a_thread_they_pointed_elsewhere_and_we_answered_is_held_with_the_reason():
    d = _draft(thread=(OURS, THEIRS, THANKS), item=_nudge(since="2026-10-06"))
    assert d["status"] == "none" and not d["text"], d
    assert d["why"].startswith("held: the conversation ended there"), d["why"]
    assert "careers site" in d["why"], d["why"]
    # Stock lines waiting on the card change nothing: still held.
    assert _draft(thread=(OURS, THEIRS, THANKS), text=STOCK)["status"] == "none"


def test_a_thread_where_we_asked_something_back_is_still_followed_up():
    asked = dict(THANKS, full_text="Thanks Juno, I've applied to the analyst role there. Would "
                                   "you know who leads that team?")
    d = _draft(thread=(OURS, THEIRS, asked), item=_nudge(since="2026-10-06"))
    assert d["status"] != "none", d
    # And a draft written for them with a real ask, waiting on the card, is not held.
    ask = ("Hi Juno, following up on my note from October. I applied to the demand planning "
           "analyst role at Fernhill: would you be comfortable passing my name to its hiring "
           "manager?")
    d = _draft(thread=(OURS, THEIRS, THANKS), item=_nudge(since="2026-10-06"), text=ask)
    assert d["status"] != "none" and d["source"] == "stored", d


# ------------------------------------------------------------------ a live process, or "no check-in"

def test_nobody_at_an_employer_with_an_interview_running_is_followed_up():
    tracker = [{"date": "2026-10-10", "company": "Fernhill Freight", "role": "Demand Planner",
                "status": "interview", "notes": ""}]
    d = _draft(tracker=tracker)
    assert d["status"] == "none" and "hiring process at Fernhill Freight" in d["why"], d
    # A process that ended is no reason to hold.
    over = [dict(tracker[0], status="rejected")]
    assert _draft(tracker=over)["status"] != "none"


def test_nobody_at_an_employer_with_a_referral_in_progress_is_followed_up():
    colleague = _contact("fernhill_marsh", name="Robin Marsh", title="Head of Planning",
                         status="referral_in_progress")
    d = _draft(book={colleague["contact_id"]: colleague})
    assert d["status"] == "none" and "referral is in progress at Fernhill Freight" in d["why"], d


def test_a_record_that_says_no_check_in_is_honoured():
    contact = _contact(notes="2026-10-20: no check-in, the conversation has moved to the colleague")
    d = _draft(contact=contact)
    assert d["status"] == "none" and "no check-in" in d["why"], d
    assert _draft(contact=_contact(next_action="Don't follow up: she is on leave"))["status"] == "none"
