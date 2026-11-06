"""What the person sends to Claude from the page is written first, rung after, and said honestly.

The QA audit of 3 November 2026 ("chat_work", findings 1 to 29 and "Too many buttons") drove
the page in a browser on one person's real data and found a chat message saved but never rung,
a ring that went out before its work was written, a refused tap that always read "this changed
since you saw it", waiting work that said "Not picked up yet" while it waited its turn behind
the cap, batch members that said "May have stopped" while their batch ran, and more. Each test
here plays the audit's own steps on the invented sample search
(tests/fixtures/app_model_sample.json): every person and employer in it is made up.
"""
from __future__ import annotations

import json
import os
import sys
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _at(minutes_before_nine: int) -> str:
    t = dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.timezone.utc) - dt.timedelta(minutes=minutes_before_nine)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _work(kind, title, status="queued", asked=30, **more):
    doc = {"kind": kind, "title": title, "to": "cloud", "args": {}, "asked_at": _at(asked), "status": status,
           "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None, "claimed_at": None,
           "stop_asked": False, "attempt": 1}
    doc.update(more)
    return doc


def _rings(got):
    return [r for r in got["rings"]]


FAKE = {"canSend": "available"}
NEEDS_CHAT = {"toolCalls": [{"name": "needs_chat", "input": {"reason": "It needs the employer's own website"}}], "reply": "x"}


# ------------------------------------------------------------------ 1, 18 and the hand-off note


def test_a_question_handed_on_after_the_tap_is_spent_is_saved_said_once_and_sent_with_the_next_tap(run, tmp_path):
    """Finding 1: the quick helper handed a question on after the Send tap had stopped
    counting; the card said "Saved. It starts next time..." and nothing rang. Now the words
    are kept in Claude's thread with their work, the one line under the message says they are
    not sent yet, with one button, and the next tap sends them."""
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": "Is there anything new on the Harbourline Bank careers site?"},
        {"click": "Send", "exact": True, "wait": 400, "read": "#main .talk-list", "store": "talk/", "rings": True,
         "count": "#main .talk-list button"},
        {"click": "Send to Claude", "exact": True, "wait": 300, "rings": True, "read": "#main .talk-list"},
    ], PHONE, fake=dict(FAKE, sample=dict(NEEDS_CHAT, spendTap=True)), clock=T)
    first = got["after"][1]
    mine = [d for d in first["store"] if d.get("from") == "you"]
    assert len(mine) == 1 and mine[0]["path"].startswith("talk/cloud-1/messages/"), first["store"]
    assert mine[0]["text"] == "Is there anything new on the Harbourline Bank careers site?"
    talk = [w for w in first["work"] if w["kind"] == "talk"]
    assert len(talk) == 1 and talk[0]["args"]["message"] == mine[0]["path"].split("/")[-1]
    assert first["rings"] == [], "the tap was spent: nothing rang, and nothing pretends it did"
    text = first["text"]
    assert "Saved. It starts next time" not in text
    # The hand-off line is one short state since 2026-11-05, and a line saying it is not sent
    # yet never opens "Sent to Claude" (it read "Sent to Claude · Not sent to Claude yet").
    assert "Sent to Claude · Not sent" not in text, text
    assert text.index("Is there anything new") < text.index("Not sent to Claude yet"), "the note follows the message"
    assert "Not sent to Claude yet: it goes with your next tap here." in text
    assert first["count"] == 1, "one button says it, once"
    after = got["after"][2]
    assert [r["text"] for r in after["rings"]] == ["[app] [work:" + talk[0]["id"] + "]"]


def test_a_request_typed_in_chat_is_written_before_its_ring_and_nothing_rings_when_nothing_was_written(run, tmp_path):
    """Findings 18 and 22: the ring went out before the message and its work were written (1.9 s
    apart on the real page), and rang even when every write then failed."""
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
        {"click": "Send", "exact": True, "wait": 300, "rings": True, "store": "talk/"},
    ], PHONE, fake=dict(FAKE, failWrites=True), clock=T)
    assert got["after"][1]["rings"] == [] and got["after"][1]["work"] == []
    ok = _go(run, tmp_path, [
        {"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
        {"click": "Send", "exact": True, "wait": 300, "rings": True, "store": "talk/"},
    ], PHONE, fake=FAKE, clock=T)
    calls = ok["after"][1]
    assert len(calls["rings"]) == 1 and calls["rings"][0]["text"].startswith("[app] [work:talk~cloud-1~")
    assert any(d.get("from") == "you" for d in calls["store"]) and calls["work"], "written, then rung"


def test_sending_again_at_once_after_a_failed_send_goes(run, tmp_path):
    """Finding 16: after "Not sent. Try again." the same words pressed again within 8 s did nothing."""
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
        {"click": "Send", "exact": True, "wait": 300, "eval": "document.querySelector('#talk-text').value"},
        {"click": "Send", "exact": True, "wait": 300, "store": "talk/", "rings": True},
    ], PHONE, fake=dict(FAKE, failFirstWrites=1), clock=T)
    assert got["after"][1]["eval"] == "Find me five more analyst roles in Leeds", "the words went back in the box"
    second = got["after"][2]
    assert [d["text"] for d in second["store"] if d.get("from") == "you"] == ["Find me five more analyst roles in Leeds"]
    assert len([w for w in second["work"] if w["kind"] == "talk"]) == 1 and len(second["rings"]) == 1


# ------------------------------------------------------------------ 2: a ring that fails


def test_a_vanished_doorbell_thread_is_rung_again_on_a_fresh_one_in_the_same_tap(run, tmp_path):
    """Finding 2: the stored doorbell named a thread that was gone; the first tap of every
    window was lost. Now the same tap rings again on a fresh thread, which is kept."""
    seed = {"meta/doorbell": {"rung_at": _at(60), "thread": "gone1", "ids": [], "rung": {}}}
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
        {"click": "Send", "exact": True, "wait": 400, "rings": True, "store": "meta/", "read": "#main .talk-list"},
    ], PHONE, seed=seed, fake=dict(FAKE, deadThreads=["gone1"]), clock=T)
    after = got["after"][1]
    assert [(r["thread"], r["anchor"]) for r in after["rings"]] == [("gone1", False), (None, True)], after["rings"]
    bell = next(d for d in after["store"] if d["path"] == "meta/doorbell")
    assert bell["thread"] not in ("gone1", None), bell
    assert "Not sent" not in after["text"] and "Saved. It starts next time" not in after["text"]


def test_a_new_chat_answering_the_page_is_rung_on_a_fresh_thread(run, tmp_path):
    """A new chat took the page at 17:01 and sat idle while seven taps from 17:19 went to the
    thread the chat before it had made and resolved (the maintainer's copy, 2026-11-05). A
    ring names the chat that answered when its thread was made; once another answers, the
    next ring starts a fresh thread, and while the same chat answers, its thread is used."""
    listen = {"chat": "session_EXAMPLENEW", "kind": "cloud", "helper": True,
              "since": _at(30), "answered_at": _at(20), "watching": True}
    steps = [{"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
             {"click": "Send", "exact": True, "wait": 400, "rings": True, "store": "meta/"}]
    for before, ring in (("session_EXAMPLEOLD", (None, True)), (None, (None, True)),
                         ("session_EXAMPLENEW", ("oldchat1", False))):
        bell = {"rung_at": _at(60), "thread": "oldchat1", "ids": [], "rung": {}}
        if before:
            bell["listener"] = before
        where = tmp_path / str(before)
        where.mkdir()
        got = _go(run, where, steps, PHONE,
                  seed={"meta/doorbell": bell, "meta/listen": listen}, fake=FAKE, clock=T)
        after = got["after"][1]
        assert [(r["thread"], r["anchor"]) for r in after["rings"]] == [ring], (before, after["rings"])
        kept = next(d for d in after["store"] if d["path"] == "meta/doorbell")
        assert kept["listener"] == "session_EXAMPLENEW" and kept["thread"], kept


def test_a_ring_that_fails_says_not_sent_with_one_way_to_send_it(run, tmp_path):
    """Finding 2: an upstream_error read exactly like a planned "later"."""
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": "Find me five more analyst roles in Leeds"},
        {"click": "Send", "exact": True, "wait": 400, "read": "#main .talk-list", "count": "#main .talk-list button"},
        {"hash": "jobs", "read": "#rail"},
    ], WIDE, fake=dict(FAKE, sendError="upstream_error"), clock=T)
    assert "Not sent to Claude yet: it goes with your next tap here." in got["after"][1]["text"]
    assert got["after"][1]["count"] == 1
    assert "Not sent yet" in got["after"][2]["text"] and "Saved. It starts next time" not in got["after"][2]["text"]


# ------------------------------------------------------------------ 3, 4, 20, 21: pasting


INVITE = ("Hi Morgan, thank you for applying to the Senior Supply Chain Analyst role at Larkspur Retail. We would like to invite you to an "
          "initial round interview. Please choose a slot that suits you from the link below and we will confirm.")


def _type_js(text):
    return "(() => { const t = document.querySelector('#talk-text'); t.value = " + json.dumps(text) + "; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()"


def test_a_long_paste_is_kept_and_sent_and_an_invitation_with_no_day_asks_for_the_day(run, tmp_path):
    """Findings 3, 4 and 28: a pasted invitation was kept nowhere and reached nobody; one with
    no day was booked with an empty day; its stage showed as typed, "initial round"."""
    fields = {"kind": "interview", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst", "stage": "initial round", "day": "",
              "application": "app-larkspur-supply"}
    got = _go(run, tmp_path, [
        {"hash": "chat", "eval": _type_js(INVITE)},
        {"click": "Send", "exact": True, "wait": 600, "read": "#main", "store": "talk/", "rings": True},
        {"click": "Book it, no day yet", "exact": True},
    ], PHONE, fake=dict(FAKE, sample={"reply": json.dumps(fields)}), clock=T)
    after = got["after"][1]
    assert [d["text"] for d in after["store"] if d.get("from") == "you"] == [INVITE]
    assert len([w for w in after["work"] if w["kind"] == "talk"]) == 1 and len(after["rings"]) == 1
    assert "It gives no day yet." in after["text"] and "Add the day" in after["text"]
    booked = [a for a in got["actions"] if a["action"] == "outcome.interview"]
    assert booked and booked[-1]["value"]["on"] == "" and booked[-1]["value"]["stage"] == "Initial round", booked


def test_stop_while_a_paste_is_read_stops_it_and_no_offer_follows(run, tmp_path):
    """Finding 20: Stop showed while a paste was read, and did nothing."""
    got = _go(run, tmp_path, [
        {"hash": "chat", "eval": _type_js(INVITE)},
        {"click": "Send", "exact": True, "wait": 300, "attr": ["[data-k=talk-stop]", "hidden"]},
        {"click": "Stop Claude's work on this answer", "exact": True, "wait": 300, "read": "#main", "attr": ["[data-k=talk-stop]", "hidden"], "store": "talk/"},
    ], PHONE, fake=dict(FAKE, sample={"hang": True}), clock=T)
    assert got["after"][1]["attr"] is None, "Stop shows while it reads"
    assert got["after"][2]["attr"] is not None and "Book this interview" not in got["after"][2]["text"]
    assert [d["text"] for d in got["after"][2]["store"] if d.get("from") == "you"] == [INVITE], "the paste itself is kept"


def test_a_paste_longer_than_the_box_says_so_and_the_box_holds_a_whole_posting(run, tmp_path):
    """Finding 21: 6,720 characters were cut to 3,500 with only "3500 of 3500 characters"."""
    paste = ("(() => { const t = document.querySelector('#talk-text'); t.value = 'x'.repeat(19000); t.focus(); t.setSelectionRange(19000, 19000);"
             " const d = new DataTransfer(); d.setData('text/plain', 'y'.repeat(6720));"
             " t.dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true, cancelable: true}));"
             " t.value = 'x'.repeat(20000); t.dispatchEvent(new Event('input', {bubbles: true})); return t.maxLength; })()")
    got = _go(run, tmp_path, [
        {"hash": "chat", "eval": paste},
        {"wait": 100, "read": "#talk-count"},
    ], PHONE, fake=FAKE, clock=T)
    assert got["after"][0]["eval"] == 20000
    assert got["after"][1]["text"].startswith("Only the first 20,000 characters fit."), got["after"][1]["text"]


# ------------------------------------------------------------------ 5 and the class: a refused tap


def _refused(item, action, value, result, note, ask=None, rev="ap3", minutes=30):
    aid = "act~%s~%s~r%d" % (item, action, minutes)
    rec = {"applied_at": _at(minutes - 5), "by": "cloud-1", "result": result, "note": note, "action": action, "item": item}
    if ask:
        rec["ask"] = ask
    return aid, {"actions/" + aid: {"item": item, "action": action, "value": value, "at": _at(minutes), "rev_seen": rev, "tab": "another"},
                 "receipts/" + aid: rec}


def test_a_refused_tap_says_the_engines_reason_on_to_do_with_the_field_to_answer_it(run, tmp_path):
    """Finding 5: every refusal read "this changed since you saw it", with nowhere to give what
    the engine asked for, and only in the tab that made it. Now a refusal from any window is a
    To do card with the engine's own words and the field; a stale one says it changed, once."""
    aid, seed = _refused("app-fernhill-ops", "outcome.rejected", {"on": "2026-11-30"}, "conflict", "That day has not come yet.",
                         ask={"key": "on", "label": "Which day did they say no?", "type": "date"})
    sid, stale = _refused("app-brackmoor-stock-2026-09", "outcome.no_response", None, "stale", "It changed since you saw it: look again.",
                          rev="ap5", minutes=40)
    seed.update(stale)
    card = '[data-item="refused:%s"]' % aid
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": card, "count": card + " input[type=date]"},
        {"read": '[data-item="refused:%s"]' % sid},
        {"eval": "(() => { document.querySelector('%s input').value = '2026-10-24'; return 1; })()" % card},
        {"click": "Send", "within": card, "exact": True},
    ], PHONE, seed=seed, fake=FAKE, clock=T)
    text = got["after"][0]["text"]
    assert "Fernhill Freight" in text and "Not done: That day has not come yet." in text and "Which day did they say no?" in text
    assert "changed since" not in text and got["after"][0]["count"] == 1
    st = got["after"][1]["text"]
    assert st.count("changed since you saw it") == 1 and "Not done: this changed since you saw it. Look again and choose once more." in st
    again = [a for a in got["actions"] if a["action"] == "outcome.rejected" and a.get("tab") != "another"]
    assert again and again[-1]["item"] == "app-fernhill-ops" and again[-1]["value"]["on"] == "2026-10-24", got["actions"]


def test_the_engine_puts_what_it_needs_on_a_refused_receipt(tmp_path):
    """The receipt itself says which value is missing (`ask`), and an example day is today,
    never one already past ("Give it as 2026-10-28" on 3 November)."""
    from test_a_tick_on_the_page_is_applied_once import Search
    search = Search(str(tmp_path))
    larkspur = "app-larkspur_retail_senior_supply_chain_analyst"
    rev = next(a for a in search.model()["applications"] if a["id"] == larkspur)["rev"]
    later = search.act("outcome.rejected", larkspur, rev=rev, value={"on": "2099-01-01"})
    word = search.act("outcome.rejected", larkspur, rev=rev, value={"on": "next week"})
    search.apply()
    r = search.receipt(later)
    assert r["result"] == "conflict" and r["note"] == "That day has not come yet."
    # The kind of answer it needs, as every ask names it (app_actions.clean_ask), and its
    # older `type` for a page from before the kinds.
    assert r["ask"] == {"key": "on", "label": "Which day?", "type": "date", "kind": "date"}
    w = search.receipt(word)
    assert w["ask"]["key"] == "on" and "2026-10-21" not in w["note"] and "2026-10-25" in w["note"], w


def test_done_today_names_what_each_tap_was_about_and_a_refusal_is_its_own_card(run, tmp_path):
    """Finding 23: "Interview booked · Not done", "Stopped · Saved" with no employer, person or
    reason. "Recent changes" gave way to "Done today (N)" (the UX review, 2026-11-05): a tap not
    done is never listed as done, its reason on its own To do card."""
    aid, seed = _refused("app-larkspur-supply", "outcome.interview", {"on": "2026-10-20", "stage": "Initial round"}, "conflict",
                         "That application is no longer in your tracker.", rev="ap1")
    seed["actions/act~larkspur_retail_castellan~person.stop~x1"] = {"item": "larkspur_retail_castellan", "action": "person.stop", "value": None,
                                                                    "at": _at(20), "rev_seen": "p-castellan", "tab": "another"}
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Show Done today (1)", "exact": True, "read": ".todo-done-list"},
        {"read": '[data-item="refused:' + aid + '"]'},
    ], PHONE, seed=seed, fake=FAKE, clock=T)
    done, refused = got["after"][0]["text"], got["after"][1]["text"]
    assert "Stopped: Juno, Larkspur Retail" in done, done
    assert "Larkspur Retail" not in done.replace("Juno, Larkspur Retail", ""), ("a refused tap is never listed as done", done)
    assert "Larkspur Retail" in refused and "That application is no longer in your tracker." in refused, refused


# ------------------------------------------------------------------ 6 to 13: work waiting, batches, answers


def _crowd():
    """Three big jobs running in a chat on the computer (cap 3), one of them a batch of three
    drafts, and two drafts waiting their turn since half an hour ago."""
    lease = "2026-10-25T09:20:00Z"
    return {
        "meta/listener": {"chat": "local-1", "kind": "computer", "answered_at": _at(70), "watching": True},
        "work/draft~a": _work("draft", "Draft: Harbourline Bank", "running", 50, claimed_by="child-1", claimed_at=_at(45), stage=1, stage_at=_at(20),
                              lease_until=lease, steps=[{"at": _at(19), "text": "Writing the CV"}]),
        "work/draft~b": _work("draft", "Draft: Copperleaf Pay", "claimed", 50, claimed_by="child-1", claimed_at=_at(45), lease_until=_at(15), **{"with": "draft~a"}),
        "work/draft~c": _work("draft", "Draft: Kestrel Mutual", "claimed", 50, claimed_by="child-1", claimed_at=_at(45), lease_until=_at(15), **{"with": "draft~a"}),
        "work/search~x": _work("search", "Finding jobs", "running", 40, claimed_by="child-2", claimed_at=_at(39), stage_at=_at(10), lease_until=lease),
        "work/prep~y": _work("prep", "Interview prep: Larkspur Retail", "running", 40, claimed_by="child-3", claimed_at=_at(39), stage_at=_at(10), lease_until=lease),
        "work/draft~d": _work("draft", "Draft: Fernhill Freight", "queued", 30, steps=[{"at": _at(25), "text": "Waiting its turn: three jobs are running now."}]),
        "work/draft~e": _work("draft", "Draft: Quayside Foods", "queued", 29),
    }


def test_work_waiting_its_turn_stays_in_line_and_a_batch_speaks_with_its_first_item(run, tmp_path):
    """Findings 6, 9, 10, 11, 12, 13: capped drafts read "Not picked up yet", then "Starting";
    batch members read "May have stopped" with Try again and a Stop that stopped nothing;
    Claude's own line on waiting work was folded away; "Claude isn't listening" showed over all
    of it."""
    w = lambda i: '[data-work="%s"]' % i  # noqa: E731
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": w("draft~d")},
        {"read": w("draft~e")},
        {"read": w("draft~b"), "count": w("draft~b") + " button"},
        {"read": w("draft~a"), "attr": [w("draft~a") + " [data-k='stop:draft~a']", "aria-label"]},
        {"hash": "todo", "count": '[data-item="listen"]', "attr": ["#conn", "data-state"]},
        # Claude checks in after they were asked: they still cannot start, so they are not "Starting".
        {"write": {"meta/listener": {"chat": "local-1", "kind": "computer", "answered_at": _at(1), "watching": True}}, "hash": "jobs", "read": w("draft~e")},
    ], WIDE, seed=_crowd(), fake=FAKE, clock=T)
    d, e, b, a, todo, e2 = got["after"]
    assert "Next" in d["text"] and "Waiting its turn: three jobs are running now." in d["text"]
    assert "Waiting its turn" in e["text"] and "1 job before it" in e["text"]
    for t in (d["text"], e["text"]):
        assert "No answer" not in t and "not picked this up" not in t
    assert "May have stopped" not in b["text"] and "Drafted in one go with Harbourline Bank" in b["text"] and "Writing the CV" in b["text"]
    assert b["count"] == 1, "only its title's own toggle: no Stop and no Try again of its own"
    # "Stop Claude" everywhere (the maintainer, 2026-11-05).
    assert a["attr"] == "Stop Claude's work on Draft: Harbourline Bank and the 2 drafts written with it"
    assert todo["count"] == 0 and todo["attr"] == "live", "jobs running are Claude being there"
    assert "Waiting its turn" in e2["text"] and "Starting" not in e2["text"]


def test_a_batch_member_with_a_question_speaks_for_itself(run, tmp_path):
    """The re-audit of 4 November: a member of a batch that stopped on a question to the person
    was read as following its lead, so its card showed the lead's progress and no Answer, and
    the lead's Try again queued it again over its question."""
    w = lambda i: '[data-work="%s"]' % i  # noqa: E731
    ask = "Is the Looker work the same as the Tableau work?"
    seed = {"work/draft~a": _work("draft", "Draft: Harbourline Bank", "running", 50, claimed_by="child-1", claimed_at=_at(45), stage=1,
                                  stage_at=_at(5), lease_until="2026-10-25T09:20:00Z", steps=[{"at": _at(4), "text": "Writing the CV"}]),
            "work/draft~b": _work("draft", "Draft: Copperleaf Pay", "needs_you", 50, claimed_by=None, note=ask, **{"with": "draft~a"})}
    got = _go(run, tmp_path, [{"hash": "jobs", "read": w("draft~b")}], WIDE, seed=seed, fake=FAKE, clock=T)
    b = got["after"][0]["text"]
    assert "Answer" in b and "Drafted in one go with" not in b and "Writing the CV" not in b, b
    # The lead fails; its Try again takes the batch back whole, but never the question.
    seed["work/draft~a"] = _work("draft", "Draft: Harbourline Bank", "failed", 50, error="The resume would not compile.", finished_at=_at(2))
    seed["work/draft~c"] = _work("draft", "Draft: Kestrel Mutual", "claimed", 50, claimed_by="child-1", claimed_at=_at(45), **{"with": "draft~a"})
    got = _go(run, tmp_path, [
        {"hash": "work", "click": "Try again: Draft: Harbourline Bank", "exact": True, "wait": 300, "rings": True},
    ], WIDE, seed=seed, fake=FAKE, clock=T)
    work = {x["id"]: x for x in got["after"][0]["work"]}
    assert work["draft~a"]["status"] == "queued" and work["draft~c"]["status"] == "queued"
    assert work["draft~b"]["status"] == "needs_you", work["draft~b"]


def test_waiting_work_counts_a_batch_once_against_the_cap():
    """Finding 9 in the engine: one chat drafting a batch of three filled a cap of three."""
    import page_db
    now = dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.timezone.utc)
    seed = _crowd()
    db = {"work": {k.split("/")[1]: {"data": v, "version": 3} for k, v in seed.items() if k.startswith("work/")}}
    for k in ("draft~b", "draft~c"):
        db["work"][k]["data"]["lease_until"] = "2026-10-25T09:20:00Z"
    del db["work"]["prep~y"]
    got = page_db.next_item(db, "computer", now, cap=3)
    assert got and got["work"] == "draft~d", "the batch is one of the three, so one more starts"


def test_a_batch_leases_move_with_its_first_item_and_a_new_claim_is_in_no_batch(tmp_path):
    """Findings 8 and 11: members' leases were never renewed, so after half an hour another
    chat drafted them again; a claim kept a `with` naming a batch long finished."""
    import page_db
    now = dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.timezone.utc)
    seed = _crowd()
    db = {"work": {k.split("/")[1]: {"data": v, "version": 3} for k, v in seed.items() if k.startswith("work/")}}
    got = page_db.pin(db, "draft~a", now, str(tmp_path / "pin"), stage=1, line="Writing the letter", chat="child-1")
    renewed = {e["doc_id"]: e for e in _entries(got["batches"]) if e["collection"] == page_db.stored("work")[0]}
    ids = {k: page_db.safe_id(k) for k in ("draft~a", "draft~b", "draft~c")}
    assert set(renewed) == set(ids.values()), renewed
    b, a = renewed[ids["draft~b"]], renewed[ids["draft~a"]]
    assert b["body"]["lease_until"] == a["body"]["lease_until"] > "2026-10-25T09:20:00Z"
    assert b["if_version"] == 3
    db["work"]["draft~q"] = {"data": _work("draft", "Draft: Quayside Foods", "queued", 5, **{"with": "draft~old"}), "version": 2}
    files = page_db.claim(db, {"work": "draft~q", "version": 2, "locks": []}, "cloud-1", "cloud", now, str(tmp_path / "claim"))
    claimed = [e for e in _entries(files) if e["doc_id"] == page_db.safe_id("draft~q")]
    assert claimed
    # Cleared, as the store holds it once the claim lands: the claim takes the field away
    # (`{"__delete__": true}`, the form engine 5 pins in
    # tests/test_every_work_move_is_a_command_pinned_to_its_read.py), never keeps the old batch.
    landed = page_db._merged(db["work"]["draft~q"]["data"], claimed[0]["body"])
    assert landed.get("with") in (None, ""), landed


def _entries(paths):
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for e in json.load(fh):
                if e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as b:
                        e["body"] = json.load(b)
                out.append(e)
    return out


def test_a_finished_job_brings_the_page_up_to_date_even_when_its_check_failed():
    """Finding 7: a job whose local check failed left its work unlanded and, told to say
    nothing, never brought the page up to date or told the chat that answers it."""
    import app
    chosen = {"work": "draft~a", "kind": "draft", "title": "Draft: Harbourline Bank", "stages": []}
    own = "\n".join(app.job_steps(chosen, "listener-1", "https://claude.ai/artifact/x", session=True))
    assert "landed or not" in own and own.index("landed or not") < own.index("tools/app.py view")
    agent = "\n".join(app.job_steps(chosen, "listener-1", "https://claude.ai/artifact/x", session=False))
    assert "\"Finished draft~a, not landed: bring the page up to date.\"" in agent and "landed or not" in agent
    with open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        assert "`Finished <id>, not landed`" in fh.read(), "the chat that answers the page knows the second line"


def test_a_yes_or_no_question_is_answered_in_one_tap_and_goes_back_as_its_own_job(run, tmp_path):
    """Findings 8 and 24: a yes-or-no question had only a free-text box, and the answered item
    kept a `with` naming a batch that had finished."""
    seed = {"work/draft~q": _work("draft", "Draft: Fernhill Freight", "needs_you", 30, claimed_by=None, **{"with": "draft~gone"},
                                  note="Is the Looker work the same as the Tableau work? A yes puts it on this CV; a no keeps it off.")}
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Answer: Draft: Fernhill Freight", "exact": True, "read": "dialog"},
        {"click": "Yes", "within": "dialog", "exact": True, "wait": 300, "rings": True},
        {"hash": "jobs", "read": '[data-work="draft~q"]'},
    ], WIDE, seed=seed, fake=FAKE, clock=T)
    sheet = got["after"][0]["text"]
    assert "Yes" in sheet and "No" in sheet and "Something else" in sheet
    item = next(x for x in got["after"][1]["work"] if x["id"] == "draft~q")
    assert item["status"] == "queued" and item["with"] is None and list(item["args"]["answers"].values()) == ["Yes"]
    assert [r["text"] for r in got["after"][1]["rings"]] == ["[app] [work:draft~q]"]
    # One short state (the maintainer, 2026-11-05): "Waking Claude", or about to start.
    assert "Waking Claude" in got["after"][2]["text"] or "Starting in a moment" in got["after"][2]["text"], got["after"][2]["text"]


# ------------------------------------------------------------------ 14, 15, 17: the chat's own lines


def _thread(msgs, work=None):
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "A question", "created_at": _at(200)}}
    for mid, m in msgs:
        seed["talk/cloud-1/messages/" + mid] = m
    if work:
        seed.update(work)
    return seed


def test_the_chat_line_under_a_message_says_what_its_card_says(run, tmp_path):
    """Finding 14: the chat said "Claude is starting on this…" while the card said "Not picked
    up yet", for work nobody had."""
    seed = _thread([("m1", {"from": "you", "text": "Can you check the Quayside Foods careers page?", "at": _at(30), "work": "talk~cloud-1~m1"})],
                   {"work/talk~cloud-1~m1": _work("talk", "Answer: “Can you check the Quayside Foods careers page?”", "queued", 30,
                                                   args={"thread": "cloud-1", "message": "m1"}),
                    "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": _at(60), "watching": True}})
    got = _go(run, tmp_path, [
        {"hash": "chat", "read": "#main .talk-list"},
        {"hash": "jobs", "read": '[data-work="talk~cloud-1~m1"] .wc-now'},
        {"read": '[data-work="talk~cloud-1~m1"] .wc-actions'},
    ], WIDE, seed=seed, fake=FAKE, clock=T)
    chat, card = got["after"][0]["text"], got["after"][1]["text"]
    assert "starting on this" not in chat
    assert card and card in chat, (card, chat)
    # Too many buttons, 1: starting a chat by hand has one name, the To do card's.
    assert "Open Claude" in got["after"][2]["text"] and "Start it now" not in got["after"][2]["text"]


@pytest.mark.parametrize("how", ["failed", "stopped"])
def test_a_chat_message_that_failed_or_was_called_off_says_so_in_the_chat(run, tmp_path, how):
    """Finding 15: the message just sat there with no answer and no reason."""
    w = _work("talk", "Answer: “Draft a reply to Juno”", how, 30, args={"thread": "cloud-1", "message": "m1"}, finished_at=_at(10),
              error="It could not find Juno in your contacts." if how == "failed" else None, stop_asked=how == "stopped")
    seed = _thread([("m1", {"from": "you", "text": "Draft a reply to Juno", "at": _at(30), "work": "talk~cloud-1~m1"})], {"work/talk~cloud-1~m1": w})
    got = _go(run, tmp_path, [{"hash": "chat", "read": "#main .talk-list"}], PHONE, seed=seed, fake=FAKE, clock=T)
    text = got["after"][0]["text"]
    if how == "failed":
        assert "Claude could not finish this: It could not find Juno in your contacts." in text and "Try again" in text
    else:
        assert "You called this off." in text and "Try again" not in text


def test_a_long_conversation_shows_its_newest_messages(run, tmp_path):
    """Finding 17: only the first 200 messages ever showed, so new ones never appeared."""
    msgs = [("m%03d" % i, {"from": "you" if i % 2 else "cloud", "text": "Message number %d" % i,
                           "at": (dt.datetime(2026, 10, 20, 8, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            for i in range(205)]
    got = _go(run, tmp_path, [{"hash": "chat", "read": "#main .talk-list"}], PHONE, seed=_thread(msgs), fake=FAKE, clock=T)
    text = got["after"][0]["text"]
    assert "Message number 204" in text and "Message number 4\n" not in text + "\n"
    assert text.index("Message number 200") < text.index("Message number 204"), "oldest first on screen"


# ------------------------------------------------------------------ 19, 25, 26, 27, 28


def test_a_tap_waiting_with_no_receipt_wakes_claude_and_says_so(run, tmp_path):
    """Finding 19 and 26: a tap that is not a setup answer waited with no time limit, never
    counted as waiting, beside a green dot."""
    seed = {"actions/act~app-fernhill-ops~outcome.no_response~w1": {"item": "app-fernhill-ops", "action": "outcome.no_response", "value": None,
                                                                    "at": _at(30), "rev_seen": "ap3", "tab": "another"},
            "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": _at(60), "watching": True}}
    # Finding 25 too: with thirty follow-ups due, the one card that unblocks the rest leads.
    model = journeys._sample()
    nudge = next(d for d in model["due"] if d["kind"] == "nudge")
    model["due"] = model["due"] + [dict(nudge, id="due-many-%d" % i, title="Follow up with Ines %d" % i, rev="dm%d" % i) for i in range(30)]
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "document.querySelector('#main [data-card]').dataset.item", "attr": ["#conn", "data-state"]},
        {"click": "Wake Claude", "within": '[data-item="listen"]', "wait": 300, "rings": True},
    ], PHONE, model=model, seed=seed, fake=FAKE, clock=T)
    assert got["after"][0]["eval"] == "listen" and got["after"][0]["attr"] == "unheard"
    assert [r["text"] for r in got["after"][1]["rings"]] == ["[app] [act:act~app-fernhill-ops~outcome.no_response~w1]"]


def test_the_phone_pill_counts_what_waits(run, tmp_path):
    """Finding 27: on a phone the pill read "3 running" and left out what waited."""
    seed = {"work/search~x": _work("search", "Finding jobs", "running", 20, claimed_by="c", claimed_at=_at(19), stage_at=_at(5), lease_until="2026-10-25T09:20:00Z"),
            "work/draft~d": _work("draft", "Draft: Fernhill Freight", "queued", 2), "work/draft~e": _work("draft", "Draft: Quayside Foods", "queued", 1)}
    got = _go(run, tmp_path, [{"hash": "todo", "read": "#pill"}], PHONE, seed=seed, fake=FAKE, clock=T)
    assert "1 running · 2 waiting" in got["after"][0]["text"], got["after"][0]["text"]


def test_a_chat_answer_is_said_once_and_its_title_is_cut_at_a_word(run, tmp_path):
    """Finding 28: "Answer: “…find 10 m…”" cut mid-word; "Answer: “…”: ready." said twice;
    "Nothing is sent." under a chat answer."""
    long = "also scratch the job drafts we have and find 10 more recent ones please"
    got = _go(run, tmp_path, [
        {"hash": "chat", "type": long},
        {"click": "Send", "exact": True, "wait": 300},
        {"hash": "jobs", "read": "#rail"},
    ], WIDE, fake=FAKE, clock=T)
    talk = [w for w in got["work"] if w["kind"] == "talk"]
    assert talk[0]["title"] == "Answer: “also scratch the job drafts we have and find 10…”", talk[0]["title"]
    assert "Nothing is sent." not in got["after"][2]["text"]
    seed = _thread([("m1", {"from": "you", "text": "Is Larkspur hiring?", "at": _at(5), "work": "talk~cloud-1~m1"})],
                   {"work/talk~cloud-1~m1": _work("talk", "Answer: “Is Larkspur hiring?”", "running", 5, claimed_by="cloud-1", claimed_at=_at(4), stage_at=_at(4), lease_until="2026-10-25T09:20:00Z")})
    done = _work("talk", "Answer: “Is Larkspur hiring?”", "done", 5, finished_at=_at(0), result={"summary": "Answered.", "links": []})
    seed["work/draft~z"] = _work("draft", "Draft: Fernhill Freight", "running", 5, claimed_by="c", claimed_at=_at(4), stage_at=_at(4), lease_until="2026-10-25T09:20:00Z")
    asks = dict(seed["work/draft~z"], status="needs_you", note="Is the Looker work the same as the Tableau work?")
    got = _go(run, tmp_path, [
        {"hash": "jobs"},
        {"write": {"work/talk~cloud-1~m1": done}, "read": "#toasts"},
        {"write": {"work/draft~z": asks}, "read": "#toasts"},
    ], WIDE, seed=seed, fake=FAKE, clock=T)
    assert "Claude answered in Chat." in got["after"][1]["text"] and "”: ready." not in got["after"][1]["text"]
    # Too many buttons, 3: a question is answered from its card, never from a third place.
    assert "Claude has a question" in got["after"][2]["text"] and "Answer it" not in got["after"][2]["text"]
