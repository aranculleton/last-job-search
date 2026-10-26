"""A message is copied off the page exactly, sent by hand, and logged once with its words.

FUNCTIONS_SPEC.md (2026-10-25) section 1.5, a must-have: each message carries the text to
copy (an InMail's or an email's subject apart from its body), its character count against
the plan's limit (always shown on a first note), where it goes (a pointer to the owner-only
reach/<contact> document, never the address in the page), and any warning compose.advise
left standing, in plain words. "I sent it" logs the words that went, the person's own
edit included, on the day they went, and the same send twice (a double tap, two chats at
once, a chat on Monday and the page on Tuesday) is one thread row. "They replied" logs
their words, the row says a reply is owed, and the reply drafted next starts from them.
An application's follow-up drafted by code is a message too. Every person here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_page  # noqa: E402
import app_state  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import APP, NOW, Search  # noqa: E402

PELL = "kestrel_mutual_ansgar"
WREN = "fernhill_freight_halloway"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _threads(search, cid):
    with open(os.path.join(search.state, "network_threads.csv"), encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["contact_id"] == cid]


def _contact(search, cid):
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == cid)


def _set_contact(search, cid, **fields):
    path = os.path.join(search.state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["contact_id"] == cid:
            r.update(fields)
    app_state._save_csv(path, rows, list(rows[0].keys()))


def _draft(search, cid, text):
    path = os.path.join(search.state, "documents", "network", cid, "draft.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


# ------------------------------------------------------------------ what the page is given


def test_a_first_note_gives_the_words_to_copy_its_count_and_where_it_goes(search):
    m = search.model()
    (msg,) = m["messages"]
    assert (msg["type"], msg["subject"]) == ("first_note", None)
    assert msg["body"] == msg["text"]
    assert msg["count"] == {"chars": len(msg["body"]), "limit": 300, "show": True, "warn": False,
                            "over": False, "label": f"{len(msg['body'])} of 300 characters"}
    assert msg["open"] == {"kind": "profile", "doc": f"reach/{PELL}",
                           "label": "Open their profile"}
    assert isinstance(msg["warnings"], list)
    # The address is never in the page: only in the owner's own database document.
    page = app_page.render(m)
    assert "linkedin.com/in/example-pell-ansgar" not in json.dumps(m) + page
    assert "pell.ansgar@example.co.uk" not in json.dumps(m) + page
    budget = m["message_budget"]
    assert budget["ready"] == 1 and budget["line"].startswith("1 note ready.")


def test_the_address_is_kept_for_the_owner_alone(search):
    out = search.run("view", os.path.join(search.dump, "view_out"), "--now", NOW)
    batch = json.load(open(json.loads(out)["batches"][0], encoding="utf-8"))
    reach = [e for e in batch if e["collection"] == "reach"]
    doc = next(e for e in reach if e["doc_id"] == PELL)
    got = json.load(open(doc["file_path"], encoding="utf-8"))
    assert got == {"linkedin": "https://www.linkedin.com/in/example-pell-ansgar",
                   "email": "pell.ansgar@example.co.uk"}
    rules = app_page.capabilities()["db"]["rules"]
    for level in ("view", "interact", "admin"):
        assert not page_db.can(rules, f"reach/{PELL}", "read", level), level
        assert not page_db.can(rules, f"reach/{PELL}", "write", level), level
    assert page_db.can(rules, f"reach/{PELL}", "read", "owner")
    # Even with the root rule loosened, reach/ stays the owner's.
    loose = [{"path": "", "read": "view", "write": "interact"}] + rules[1:]
    assert not page_db.can(loose, f"reach/{PELL}", "read", "view")


def test_an_inmail_is_two_things_to_copy_and_its_subject_is_logged_apart(search):
    _set_contact(search, PELL, channel="inmail")
    _draft(search, PELL, "Subject: Claims analytics at Kestrel\n\nHi Pell, we were both at "
                         "Leeds. I build forecasts for operations teams in Manchester. How is "
                         "the claims analytics team set up?")
    (msg,) = search.model()["messages"]
    assert (msg["type"], msg["channel"]) == ("inmail", "inmail")
    assert msg["subject"] == "Claims analytics at Kestrel"
    assert not msg["body"].startswith("Subject") and "Subject:" not in msg["body"]
    aid = search.act("msg.sent", msg["id"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    (row,) = _threads(search, PELL)
    assert row["subject"] == "Claims analytics at Kestrel"
    assert row["full_text"] == msg["body"] and "Subject:" not in row["full_text"]


# ------------------------------------------------------------------ I sent it


def test_i_sent_it_logs_the_words_that_went_on_the_day_they_went(search):
    (msg,) = search.model()["messages"]
    edited = msg["body"].replace("How is the claims analytics team set up?",
                                 "How does the claims team plan its year?")
    aid = search.act("msg.sent", msg["id"], value={"text": edited, "on": "2026-10-24"})
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    (row,) = _threads(search, PELL)
    assert (row["date"], row["full_text"]) == ("2026-10-24", edited)
    note = search.receipt(aid)["note"]
    assert note.startswith("Logged as sent to Pell on 2026-10-24.")


def test_the_same_send_within_a_week_is_one_row(search):
    (msg,) = search.model()["messages"]
    first = search.act("msg.sent", msg["id"], value={"text": msg["body"], "on": "2026-10-24"})
    assert search.apply()["ok"] == [first]
    search.written_back()
    # Logged again from another tap the next day (another action id): refused, with the day.
    search.put("actions", "act-again", {"action": "msg.sent", "item": msg["id"],
                                        "value": {"text": msg["body"]},
                                        "at": "2026-10-25T17:30:00Z", "rev_seen": msg["rev"],
                                        "tab": "t1"}, version=1)
    got = search.apply()
    assert got["ok"] == [] and got["conflict"] == ["act-again"], got
    assert search.receipt("act-again")["note"] == "Already logged on Saturday 24 October."
    assert len(_threads(search, PELL)) == 1


def test_two_chats_logging_the_same_send_at_once_write_one_row(search):
    (msg,) = search.model()["messages"]
    doc = {"action": "msg.sent", "item": msg["id"], "value": {"text": msg["body"]},
           "at": "2026-10-25T17:01:00Z", "rev_seen": msg["rev"], "tab": "t1"}
    dumps = []
    for n in (1, 2):
        d = os.path.join(search.dump + f"_{n}", "actions")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "act-sent.json"), "w", encoding="utf-8") as fh:
            json.dump(dict(doc, __version__=1), fh)
        dumps.append(os.path.dirname(d))
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    runs = [subprocess.Popen([sys.executable, APP, "apply", d, "--chat", f"chat-{n}", "--now",
                              NOW], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             encoding="utf-8") for n, d in enumerate(dumps, 1)]
    outs = [json.loads(r.communicate(timeout=300)[0]) for r in runs]
    assert sorted(len(o["ok"]) for o in outs) == [0, 1], outs
    rows = [r for r in _threads(search, PELL) if r["full_text"] == msg["body"]]
    assert len(rows) == 1


# ------------------------------------------------------------------ they replied


def test_their_reply_is_logged_a_reply_is_owed_and_the_draft_starts_from_their_words(search):
    person = next(p for p in search.model()["people"] if p["id"] == WREN)
    words = "Thanks Morgan, happy to chat. The planning team sits in the new hub."
    aid = search.act("msg.received", WREN, value={"text": words, "draft": True},
                     rev=person["rev"])
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    rows = _threads(search, WREN)
    assert rows[-1]["direction"] in ("in", "inbound") and rows[-1]["full_text"] == words
    after = next(p for p in search.model()["people"] if p["id"] == WREN)
    assert after["status"] == "replied_needs_response"
    assert after["status_word"] == "Replied: your turn"
    assert after["owed"]["label"] == "Draft a reply" and after["owed"]["kind"] == "reply"
    batch = json.load(open(got["batches"][0], encoding="utf-8"))
    work = next(e for e in batch if e["collection"] == "work")
    assert work["doc_id"] == f"reply~{WREN}"
    queued = json.load(open(work["file_path"], encoding="utf-8"))
    assert queued["args"] == {"contact": WREN, "received": aid, "on": "2026-10-25"}
    # Their words leave the page's database once they are in the log.
    wipe = next(e for e in batch if e["collection"] == "actions" and e["doc_id"] == aid)
    assert json.load(open(wipe["file_path"], encoding="utf-8")) == {"value": {"__delete__": True}}
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    assert not any(r["full_text"] == words for r in _threads(search, WREN))


# ------------------------------------------------------------------ a send nobody confirmed


def test_a_note_past_its_day_with_nothing_logged_is_asked_about(search):
    _set_contact(search, PELL, next_action_due="2026-10-20")
    m = search.model()
    q = next(n for n in m["needs_you"] if n["id"] == f"q-sent-{PELL}")
    assert q["kind"] == "confirm" and q["title"] == "Did your note to Pell go?"
    assert [o["label"] for o in q["options"]] == ["Yes, it went", "Not yet"]
    assert not any(d.get("item") == PELL for d in m["due"])
    aid = search.act("msg.sent", q["id"], value=q["options"][0]["value"], rev=q["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert len(_threads(search, PELL)) == 1


def test_not_yet_moves_the_day(search):
    _set_contact(search, PELL, next_action_due="2026-10-20")
    q = next(n for n in search.model()["needs_you"] if n["id"] == f"q-sent-{PELL}")
    aid = search.act("due.snooze", q["id"], value=q["options"][1]["value"], rev=q["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert _contact(search, PELL)["next_action_due"] == "2026-10-26"


# ------------------------------------------------------------------ an application's follow-up


def test_an_applications_follow_up_is_a_message_and_i_sent_it_logs_it_on_its_row(search):
    path = os.path.join(search.state, "job_search_tracker.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["company"] == "Kestrel Mutual":
            r.update(status="applied", applied_on="2026-10-15", confirmed_by="chat",
                     confirmed_at="2026-10-15 09:00")
    app_state._save_csv(path, rows, list(rows[0].keys()))
    out = search.run("model", "--now", NOW)
    assert out
    code = ("import sys, json; sys.path[:0] = ['tools', 'tools/network']\n"
            "import open_actions, followup_drafts, person\nfrom network import state\n"
            "import csv_store, datetime\n"
            "c = state.load_contacts(person.state('network_contacts.csv'))\n"
            "t = state.load_threads(person.state('network_threads.csv'))\n"
            "rows = csv_store.dict_rows(person.state('job_search_tracker.csv'))\n"
            "items = open_actions.due_items(c, t, rows, datetime.date(2026, 10, 25))\n"
            "print(next(followup_drafts.item_id(i) for i in items if i['half'] == 'application'"
            " and i['who'].startswith('Kestrel')))")
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    did = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         encoding="utf-8", cwd=ROOT).stdout.strip()
    assert did.startswith("app:")
    pack = os.path.join(search.state, "documents", "network", "followup_pack_2026-10-25.md")
    with open(pack, "w", encoding="utf-8") as fh:
        fh.write(f"# Follow-ups\n\n<!-- draft id={did} kind=message source=followups -->\n"
                 "```\nHi, I applied for the Claims Forecasting Analyst role on 15 October and "
                 "wanted to check where it stands.\n```\n")
    msg = next(x for x in search.model()["messages"] if x["application"])
    assert (msg["type"], msg["employer"]) == ("follow_up", "Kestrel Mutual")
    aid = search.act("msg.sent", msg["id"], rev=msg["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert "followed up 2026-10-25" in search.tracker_row("Kestrel Mutual")["notes"]
    folder = os.path.join(search.state, "documents", "applications",
                          "kestrel_mutual_claims_forecasting_analyst_kestrel")
    assert os.path.isfile(os.path.join(folder, "followup_2026-10-25.md"))
    shutil.rmtree(os.path.join(search.state, "rounds"), ignore_errors=True)


def test_a_message_kind_for_each_of_the_seven(search):
    assert app_model.MESSAGE_TYPES == ("first_note", "inmail", "email", "reply", "follow_up",
                                       "referral_ask", "thank_you")
    c = {"status": "call_booked", "next_action": "Send a thank-you after the call"}
    assert app_model.message_type("reply", "linkedin_message", c) == "thank_you"
    c = {"status": "in_conversation", "next_action": "Ask for a referral for the Analyst role"}
    assert app_model.message_type("reply", "linkedin_message", c) == "referral_ask"
    assert app_model.message_type("first_note", "email", {}) == "email"
    # A referral already in flight is past its ask: a message then is a reply.
    assert app_model._message_kind("referral_in_progress") == "reply"
