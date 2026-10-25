"""Every follow-up is drafted by code first, through the gate a hand-written one gets.

The model wrote every nudge by hand, after reading the thread and the networking skill, and
most of them said what code already knew: an application's follow-up is followups.py's own
text, a nudge's one new fact is a posting the search found at their employer. Code drafts
those, compose.validate() decides whether code made it cleanly, compose.advise() puts its
warnings beside it, and only what code could not make is left for a writer, with the reason.
Invented people only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import followup_drafts as F  # noqa: E402
import followups  # noqa: E402

TODAY = dt.date(2026, 10, 25)


def _contact(cid, title="Head of Planning", company="Fernhill Freight", name="Juno Halloway", **kw):
    row = {"contact_id": cid, "name": name, "title": title, "company": company,
           "location": "Manchester, England, United Kingdom", "channel": "linkedin",
           "status": "awaiting_reply", "next_action": "", "next_action_due": "", "notes": ""}
    row.update(kw)
    return row


def _nudge_item(cid, since="2026-10-01", text=""):
    return {"half": "contact", "kind": "nudge", "contact_id": cid, "name": "Juno Halloway (Fernhill Freight)",
            "status": "awaiting_reply", "since": since, "late": 10, "held": [], "quiet": False,
            "old": False, "text": text, "what": "One nudge if no reply", "key": "fernhill freight"}


THREAD = [{"contact_id": "fernhill_halloway", "date": "2026-10-01", "direction": "outbound",
           "channel": "linkedin", "scenario": "first_note", "summary": "first note",
           "full_text": "Hi Juno, I build demand forecasts in Manchester. How is the planning "
                        "team at Fernhill set up?"}]
POSTING = [{"company": "Fernhill Freight", "title": "Demand Planning Analyst - Manchester (Hybrid)",
            "fit": 74, "first_seen": "2026-10-20", "url": "https://example.com/jobs/77"}]


def _draft(item, contact, rows=POSTING, earlier=None, threads=THREAD, tracker=()):
    return F.draft(item, {contact["contact_id"]: contact}, {contact["contact_id"]: threads},
                   tracker, earlier or {}, rows)


# ------------------------------------------------------------------ networking nudges

def test_a_posting_at_their_employer_is_the_new_reason_for_a_reader_allowed_the_role():
    d = _draft(_nudge_item("fernhill_halloway"), _contact("fernhill_halloway"))
    assert d["status"] in ("ready", "check"), d
    assert d["source"] == "code" and d["kind"] == "nudge"
    assert d["text"].startswith("Hi Juno, Fernhill Freight has since posted a Demand Planning "
                                "Analyst role")
    assert "Manchester (Hybrid)" not in d["text"]          # the title as a person says it
    assert d["chars"] <= d["limit"] and d["findings"] == []


def test_a_peer_is_not_told_the_role_so_the_nudge_waits_for_a_reason():
    d = _draft(_nudge_item("fernhill_halloway"), _contact("fernhill_halloway", title="Data Analyst"))
    assert d["status"] == "write" and d["who"] == "you"
    assert "nothing new to say" in d["why"]


def test_a_posting_older_than_the_message_is_no_news():
    old = [dict(POSTING[0], first_seen="2026-09-20")]
    d = _draft(_nudge_item("fernhill_halloway"), _contact("fernhill_halloway"), rows=old)
    assert d["status"] == "write" and "nothing new" in d["why"]


def test_a_posting_already_applied_to_is_the_application_clock_not_a_nudge():
    tracker = [{"company": "Fernhill Freight", "role": "Demand Planning Analyst", "status": "applied"}]
    d = _draft(_nudge_item("fernhill_halloway"), _contact("fernhill_halloway"), tracker=tracker)
    assert d["status"] == "write"


def test_a_stored_draft_the_gate_refuses_is_kept_to_rewrite_with_its_findings():
    item = _nudge_item("fernhill_halloway", text="Hi Juno, just checking in on my last message.")
    d = _draft(item, _contact("fernhill_halloway"), rows=[])
    assert d["status"] == "write" and d["who"] == "here" and d["source"] == "stored"
    assert any("check_in" in f or "banned_phrase" in f for f in d["findings"]), d["findings"]
    assert d["text"].startswith("Hi Juno, just checking in")


def test_a_reply_is_left_to_a_writer_with_the_thread():
    item = dict(_nudge_item("fernhill_halloway"), kind="reply")
    d = _draft(item, _contact("fernhill_halloway"))
    assert d["status"] == "write" and d["who"] == "here" and d["kind"] == "reply"


def test_held_quiet_and_old_items_get_no_draft():
    for extra in ({"held": ["live process here"]}, {"quiet": True}, {"old": True}):
        d = _draft(dict(_nudge_item("fernhill_halloway"), **extra), _contact("fernhill_halloway"))
        assert d["status"] == "none"


# ------------------------------------------------------------------ the pack

def test_the_pack_carries_each_draft_and_the_next_run_reuses_one_still_right(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    contact = _contact("fernhill_halloway")
    item = dict(_nudge_item("fernhill_halloway"), id="fernhill_halloway")
    item["draft"] = _draft(item, contact)
    path = F.write_pack("2026-10-22", [item], [contact])
    assert path.endswith(os.path.join("documents", "network", "followup_pack_2026-10-22.md"))
    text = open(path, encoding="utf-8").read()
    assert "<!-- draft id=fernhill_halloway kind=nudge source=code -->" in text
    assert "state.py nudge fernhill_halloway --text-file" in text
    earlier = F.earlier_drafts("2026-10-25")
    assert earlier["quiet" if False else "fernhill_halloway"]["text"] == item["draft"]["text"]
    again = _draft(_nudge_item("fernhill_halloway"), contact, rows=[], earlier=earlier)
    assert again["source"] == "pack" and again["text"] == item["draft"]["text"]
    # Anything logged since that pack and its draft answers a thread that has moved on.
    moved = THREAD + [dict(THREAD[0], date="2026-10-23", full_text="Hi Juno, one more thing.")]
    later = _draft(_nudge_item("fernhill_halloway"), contact, rows=[], earlier=earlier, threads=moved)
    assert later["source"] != "pack"


def test_nothing_due_writes_no_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    assert F.write_pack("2026-10-25", [], []) == ""
    assert not os.path.exists(tmp_path / "documents")


# ------------------------------------------------------------------ the gate for drafts by hand

def test_check_refuses_a_check_in_and_passes_a_reply_that_answers():
    contact = _contact("fernhill_halloway")
    threads = THREAD + [{"contact_id": "fernhill_halloway", "date": "2026-10-03", "direction": "inbound",
                         "channel": "linkedin", "scenario": "detailed_generous", "summary": "replied",
                         "full_text": "Hi, the team is six people. Happy to talk next week."}]
    got = F.check([{"id": "fernhill_halloway", "text": "Hi Juno, just checking in on this."},
                   {"id": "fernhill_halloway", "text": "Thanks Juno, that helps a lot. Would Tuesday "
                                                 "afternoon suit for 15 minutes?"}],
                  [contact], threads, TODAY.isoformat())
    assert got[0]["ok"] is False and got[0]["findings"]
    assert got[1]["ok"] is True, got[1]


def test_context_gives_a_writer_their_words_ours_and_the_move(monkeypatch):
    contact = _contact("fernhill_halloway")
    threads = THREAD + [{"contact_id": "fernhill_halloway", "date": "2026-10-03", "direction": "inbound",
                         "channel": "linkedin", "scenario": "detailed_generous", "summary": "replied",
                         "full_text": "Hi, the team is six people. Happy to talk next week."}]
    out = F.context(["fernhill_halloway"], [contact], threads, TODAY.isoformat())
    assert "their last (2026-10-03): Hi, the team is six people." in out
    assert "ours (2026-10-01): Hi Juno" in out
    assert "scenario: " in out and "check as: reply" in out
    assert "followup_drafts.py check" in out


# ------------------------------------------------------------------ applications

def test_an_application_follow_up_is_followups_text_through_the_gate():
    rows = [{"date": "2026-10-10", "company": "Quayside Foods", "role": "Demand Planner",
             "status": "applied", "contact_person": "Wren Castellan", "notes": ""}]
    due = [x for x in followups.review(rows, TODAY) if x["state"] == "due"]
    assert due, "the invented application is due its first follow-up"
    it = due[0]
    item = {"half": "application", "kind": "", "key": it["key"], "who": "Quayside Foods - Demand Planner",
            "name": "Quayside Foods (Demand Planner)", "ready": bool(it["message"]),
            "text": followups.body(it), "to": followups.to_line(it), "held": [], "quiet": False}
    d = F.draft(item, {}, {}, rows, {}, [])
    assert d["status"] == "ready" and d["kind"] == "message"
    assert d["text"].startswith("Hi Wren, I applied for the Demand Planner role on 2026-10-10")
    # No recipient on file: nobody to write to, so nothing is drafted.
    none = F.draft(dict(item, ready=False, text="", to=followups.NO_RECIPIENT), {}, {}, rows, {}, [])
    assert none["status"] == "write" and none["who"] == "you" and "recipient" in none["why"]


def test_every_template_followups_writes_passes_the_apps_own_gate():
    for tpl in (followups.NUDGE_1, followups.NUDGE_2, followups.NUDGE_AFTER_WORD):
        text = tpl.format(name="Wren", role="Demand Planner", date="2026-10-10", heard="2026-10-14")
        found, warned = F.gate(text, "message", name="Wren", company="Quayside Foods")
        assert found == [] and warned == [], (tpl, found, warned)
    it = {"message": followups.NUDGE_2.format(name="Wren", role="Demand Planner", date="2026-10-10"),
          "to": {"name": "Wren"}, "company": "Quayside Foods"}
    assert followups.checked(it) == []


# ------------------------------------------------------------------ first notes queued by /network

def _queued(tmp_path, cid, text):
    d = tmp_path / "documents" / "network" / cid
    d.mkdir(parents=True)
    (d / "draft.md").write_text(text, encoding="utf-8")


def _first_note_item(cid):
    return {"half": "contact", "kind": "action_due", "contact_id": cid, "status": "not_contacted",
            "name": "Juno Halloway (Fernhill Freight)", "late": 1, "held": [], "quiet": False,
            "old": False, "text": "", "what": "Send the first note", "key": "fernhill freight"}


def test_a_first_note_waiting_on_a_read_is_the_persons_to_unlock(tmp_path, monkeypatch):
    import reading
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _queued(tmp_path, "fernhill_halloway", reading.WAITS_ON_A_READ + ": nothing was read.\n\n"
            "Hi Juno, I build demand forecasts in Manchester.\n")
    d = _draft(_first_note_item("fernhill_halloway"), _contact("fernhill_halloway", status="not_contacted"),
               rows=[], threads=[])
    assert d["status"] == "write" and d["who"] == "you" and "read of their profile" in d["why"]


def test_a_queued_note_with_nothing_read_is_refused_by_the_gate_and_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _queued(tmp_path, "fernhill_halloway", "Hi Juno, I build demand forecasts in Manchester. How "
                                           "is the planning team at Fernhill set up?\n")
    d = _draft(_first_note_item("fernhill_halloway"), _contact("fernhill_halloway", status="not_contacted"),
               rows=[], threads=[])
    assert d["kind"] == "connection" and d["source"] == "stored"
    assert d["status"] == "write" and any(f.startswith("no_reading") for f in d["findings"])
