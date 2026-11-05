"""A tap is one action, said truly, whatever the hand, the store or the second window does.

The robustness audit of 3 November 2026 (the 4.8.0 page, on one person's real data, in
Chromium) found the page writing one tap twice, saying "Undone." over an action a chat then
applied, promising to keep taps made offline and keeping none, freezing silently on one bad
item, waiting for ever on a store that never answered, and saying "Connected." over a dead
feed. Each test here is one finding, its steps as the audit ran them, on the page's own
sample (tests/fixtures/app_model_sample.json, every person and employer invented), driven by
tests/app_page/harness.js's `script` with the fake runtime's knobs (fake_claude.js: failWrites,
failDeletes, hang, subError).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from test_the_page_works_in_a_browser import PHONE, _sample, _write, pages, run  # noqa: E402

_ = (pages, run)   # the fixtures, used by name

T0 = "2026-10-25T09:00:00Z"
# A To do card with its own Done: the Fernhill Freight follow-up is drafted now, so it sits in
# "2 messages ready to send", which opens the draft (2026-11-04).
DONE = "Done: Thank-you note after your Harbourline Bank first interview"
ITEM = "due-harbourline-thanks"


def _page(tmp_path, name="sample", model=None):
    return _write(tmp_path, name, model or _sample())


def _script(run, html, steps, **kw):
    got = run("script", html=html, clock=kw.pop("clock", T0), steps=steps, **kw)
    assert not got["errors"], got["errors"]
    return got["steps"]


# What an Undo says reaches the live region a moment after the tap (announce): a step reads it
# once it is there, with a time limit, never after a set number of frames (CI, 2026-11-04:
# read as "" in the moment between the region clearing and the words).
UNDO_SAID = ("/Undone\\.|Too late to undo|not saved/.test(['live', 'alert']"
             ".map((id) => (document.getElementById(id) || {}).textContent || '').join(' '))")


def _mine(entry, item=ITEM):
    return [a for a in entry["actions"] if a.get("item") == item]


# ------------------------------------------------------------------ 1. one tap, one action


# A checklist card whose rows each write an action and whose one button writes one for every
# row: the busy week's "Did these notes go?". The audit found it on "N people haven't answered
# two messages" and its Close, a card To do no longer has (the maintainer, 2026-11-04:
# nothing to do is not a To do).
SENT = "q-sent-fernhill_freight_halloway"


# Two taps that land before the page has drawn again: the audit's real page took 1.2 s to draw
# Contacts on a desktop and seconds on a phone, and the second tap of a double tap, or one
# 400 ms later, landed on the same button.
TWICE = ("(() => { const b = document.querySelector('[data-k=\"sgy:todo:%s\"]'); b.click(); b.click(); return true; })()")


def test_a_double_tap_writes_one_action(run, pages):
    s = _script(run, pages["busy"], [{"hash": "todo", "eval": TWICE % SENT}, {"run": 500}])
    assert len(_mine(s[-1], SENT)) == 1, _mine(s[-1], SENT)


def test_a_held_enter_writes_one_action(run, pages):
    # The card focused, as j and k leave it, and Enter held: each repeat pressed its main
    # button, "They all went" here, again (robustness audit 1: 7 + 7 actions).
    s = _script(run, pages["busy"], [{"hash": "todo", "focus": '[data-card][data-item="grp:sent"]'}, {"hold": "Enter", "repeats": 4}])
    items = [a.get("item") for a in s[-1]["actions"]]
    assert SENT in items and len(items) == 2 and len(set(items)) == 2, s[-1]["actions"]


def test_the_same_tap_in_a_second_window_is_the_same_action_and_one_undo_takes_back_every_copy(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [
        {"hash": "todo", "tab": 0},
        {"hash": "todo", "tab": 1},
        {"tab": 0, "click": DONE},
        # The second window sees the first one's tap as its own: nothing left to tap twice.
        {"tab": 1, "eval": "!![...document.querySelectorAll('#main button')].find((b) => (b.getAttribute('aria-label') || '').startsWith(%s))" % json.dumps(DONE)},
        # Two windows tapping in the same instant still land two copies: the other's, as it wrote it.
        {"tab": 0, "chat": [["actions/act~due-fernhill-nudge~due.done~race1",
                             {"item": ITEM, "action": "due.done", "value": {"on": "2026-10-25"}, "at": "2026-10-25T09:00:01Z", "rev_seen": "d1", "tab": "tother"}]]},
        {"tab": 0, "click": "Undo", "within": ".toast", "exact": True, "ready": UNDO_SAID},
    ], tabs=2)
    assert len(_mine(s[2])) == 1
    assert s[3]["eval"] is False, "the other window offers no second Done for a tap already made"
    assert len(_mine(s[4])) == 2
    assert _mine(s[-1]) == [], "Undo takes back every copy of the tap"
    assert "Undone." in s[-1]["live"]


# ------------------------------------------------------------------ 2. one write to work, pinned to the store


def _failed_work():
    return {"work/draft~harbourline": {"kind": "draft", "title": "Drafting for Harbourline Bank", "to": "cloud", "args": {},
                                       "asked_at": T0, "status": "failed", "error": "The posting page would not open",
                                       "finished_at": T0, "attempt": 1, "stage": 0, "steps": [], "stop_asked": False,
                                       "asked_from": {"tab": "t0"}, "_v": 3}}


def test_a_double_tap_on_try_again_is_one_write_and_one_ring(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"hash": "work"}, {"dblclick": "Try again: Drafting for Harbourline Bank"}], seed=_failed_work())
    writes = [c for c in s[-1]["calls"] if c["cap"] == "db" and c["path"] == "work/draft~harbourline"]
    rings = [c for c in s[-1]["calls"] if c["cap"] == "comments" and c["text"]]
    assert len(writes) == 1, writes
    assert len(rings) <= 1, rings
    (w,) = s[-1]["work"]
    assert w["attempt"] == 2 and w["status"] == "queued" and w["_v"] == 4


def test_a_double_tap_on_stop_is_one_write(run, tmp_path):
    seed = _failed_work()
    seed["work/draft~harbourline"].update(status="running", claimed_by="cloud-1", claimed_at=T0, stage_at=T0)
    html = _page(tmp_path)
    s = _script(run, html, [{"hash": "work"}, {"dblclick": "Stop: Drafting for Harbourline Bank"}], seed=seed)
    writes = [c for c in s[-1]["calls"] if c["cap"] == "db" and c["path"] == "work/draft~harbourline"]
    assert len(writes) == 1, writes
    assert s[-1]["work"][0]["stop_asked"] is True


# ------------------------------------------------------------------ 3, 4, 10. Undo says what happened


def test_undo_after_a_chat_has_taken_the_action_is_too_late_and_says_so(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [
        {"hash": "todo", "click": DONE},
        {"claim": True},
        {"click": "Undo", "within": ".toast", "exact": True, "ready": UNDO_SAID},
    ])
    assert len(_mine(s[-1])) == 1, "the action a chat is applying stays"
    assert "Too late to undo" in s[-1]["live"] and "Undone." not in s[-1]["live"]


def test_an_undo_that_does_not_save_says_so_and_never_that_claude_did_it(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [
        {"hash": "todo", "click": DONE},
        {"fake": {"failDeletes": True}, "click": "Undo", "within": ".toast", "exact": True},
    ])
    assert len(_mine(s[-1])) == 1
    said = " ".join(s[-1]["badToasts"]) + s[-1]["alert"]
    assert "Undo not saved" in said, s[-1]
    assert "already done it" not in s[-1]["live"] + said


def test_an_undo_in_another_window_takes_the_saved_line_off_this_one(run, tmp_path):
    html = _page(tmp_path)
    states = "[...LJS.state().local.values()].map((r) => r.state)"
    s = _script(run, html, [
        {"hash": "todo", "tab": 0},
        {"hash": "todo", "tab": 1},
        {"tab": 0, "click": DONE},
        # The other window takes it back from its list of recent changes.
        {"tab": 1, "tap": "details.recent > summary"},
        {"tab": 1, "click": "Undo", "within": "details.recent", "exact": True},
        {"tab": 0, "run": 1000, "eval": states},
    ], tabs=2)
    assert _mine(s[-1]) == []
    assert s[-1]["eval"] == ["undone"], s[-1]["eval"]


# ------------------------------------------------------------------ 5. offline taps are kept


def test_a_tap_made_while_the_store_refuses_is_saved_by_itself_once_back_online(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [
        {"hash": "todo", "fake": {"failWrites": True}, "event": "offline"},
        {"click": DONE},
        {"fake": {"failWrites": False}, "event": "online", "run": 500},
    ])
    assert "Offline." in s[0]["conn"] and "if this page stays open" in s[0]["conn"]
    assert _mine(s[1]) == [] and any("Not saved" in t for t in s[1]["badToasts"])
    assert len(_mine(s[-1])) == 1, "kept and saved once the page was back"


# ------------------------------------------------------------------ 6, 16. a bad screen document


def test_one_null_item_in_a_screen_leaves_every_screen_working(run, tmp_path):
    m = _sample()
    html = _page(tmp_path, model=m)
    later = "2026-10-26T08:00:00Z"
    seed = {"view/due": {"made_at": later, "data": [None] + m["due"]},
            "view/people": {"made_at": later, "data": m["people"][:3] + [None] + m["people"][3:]}}
    s = _script(run, html, [{"hash": "todo"}, {"hash": "contacts"}, {"hash": "todo", "click": DONE}], seed=seed)
    assert "Thank-you note after your Harbourline Bank first interview" in s[0]["main"]
    assert "Juno" in s[1]["main"]
    assert len(_mine(s[-1])) == 1, "taps still save and draw"


def test_a_screen_of_the_wrong_shape_keeps_the_good_data(run, tmp_path):
    m = _sample()
    html = _page(tmp_path, model=m)
    later = "2026-10-26T08:00:00Z"
    seed = {"view/people": {"made_at": later, "data": None},
            "view/jobs": {"made_at": later, "data": dict(m["jobs"], rows="x")}}
    s = _script(run, html, [{"hash": "contacts"}, {"hash": "jobs"}], seed=seed)
    assert "Juno" in s[0]["main"] and "Nobody is waiting on you" not in s[0]["main"]
    assert "No search yet" not in s[1]["main"] and m["jobs"]["rows"][0]["title"] in s[1]["main"]


# ------------------------------------------------------------------ 9. a store that never answers


def test_a_store_that_never_answers_ends_in_not_saved(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"hash": "todo"}, {"click": DONE, "run": 11000}], fake={"hang": ["db"]})
    assert any("Not saved" in t for t in s[-1]["badToasts"]), s[-1]["toasts"]


def test_a_viewer_check_that_never_answers_says_what_to_do(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"run": 11000, "read": "#opening"}], fake={"hang": ["user"]})
    assert "taking too long" in s[-1]["main"], s[-1]["main"]


# ------------------------------------------------------------------ 12. a double tap rings once


def test_a_double_tap_on_draft_rings_once(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"hash": "todo", "dblclick": "Draft the thank-you: Thank-you note after your Harbourline Bank"}])
    rings = [c for c in s[-1]["calls"] if c["cap"] == "comments" and c["text"]]
    assert len(rings) == 1, rings
    assert len(s[-1]["work"]) == 1


# ------------------------------------------------------------------ 13. a dead feed is said


def test_a_feed_that_keeps_failing_backs_off_and_is_never_shown_as_connected(run, tmp_path):
    html = _page(tmp_path)
    count = "(window.__subs || {}).work || 0"
    s = _script(run, html, [
        {"hash": "todo", "run": 200},
        {"run": 60000, "eval": count},
        {"chat": [["receipts/act~x~due.done~1", {"applied_at": "2026-10-25T09:01:00Z", "result": "ok", "note": ""}]], "run": 300},
    ], fake={"subError": ["work"]})
    assert s[1]["eval"] <= 8, "a retry a second or two apart, for ever, flapped the header: %s" % s[1]["eval"]
    assert s[-1]["conn"].startswith("reconnecting"), s[-1]["conn"]


# ------------------------------------------------------------------ 14. hiding with storage refused


def test_hiding_a_card_with_storage_refused_hides_it_and_says_on_this_device(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"hash": "todo"}, {"click": "Hide for a week: Thank-you note after your Harbourline Bank"}], noStorage=True)
    assert any("on this device" in t for t in s[-1]["toasts"]), s[-1]["toasts"]
    assert "11 things need you now" in s[0]["main"]
    assert "10 things need you now" in s[-1]["main"], s[-1]["main"][:200]


# ------------------------------------------------------------------ 15. a long name


def test_a_long_unbroken_name_never_pushes_the_page_sideways(run, tmp_path):
    m = _sample()
    long = "Q" * 330
    m["people"][0]["first_name"] = long
    for x in m["messages"]:
        if x.get("contact") == m["people"][0]["id"]:
            x["to"] = long
    html = _page(tmp_path, model=m)
    # Contacts carries each message on its person's card (one page since 2026-11-04), its old
    # address included.
    s = _script(run, html, [{"hash": "contacts"}, {"hash": "drafts-messages"}], viewport=PHONE)
    assert all(x["width"] <= PHONE["width"] for x in s), [x["width"] for x in s]


# ------------------------------------------------------------------ 17. a whole list of one revision


def test_a_half_written_list_never_shows_twice_or_mixed(run, tmp_path):
    html = _page(tmp_path)
    made = "2026-10-26T08:00:00Z"
    part = lambda n, rev, parts, items: {"list": "applications", "part": n, "parts": parts, "rev": rev, "made_at": made, "items": items}  # noqa: E731
    seed = {"view/list~applications~1": part(1, "new", 2, [{"id": "app-halfway", "company": "Partwell", "role": "Analyst", "applied_on": "2026-10-20",
                                                             "status": "applied", "last": "2026-10-20", "live": True}]),
            # part 2 of the new revision has not landed: an older one's is still there
            "view/list~applications~3": dict(part(3, "old", 3, [{"id": "app-stale", "company": "Stalebrook", "role": "Analyst", "applied_on": "2026-10-19",
                                                                  "status": "applied", "last": "2026-10-19", "live": True}]), made_at="2026-10-24T08:00:00Z")}
    s = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]'}], seed=seed)
    assert "Larkspur Retail" in s[-1]["main"], "the Applied list is open"
    assert "Stalebrook" not in s[-1]["main"] and "Partwell" not in s[-1]["main"]


# ------------------------------------------------------------------ 18 to 21. words and numbers


def test_ago_counts_calendar_days_and_whole_minutes(run, tmp_path):
    html = _page(tmp_path)
    w = "LJS.words"
    s = _script(run, html, [{"eval": "[%s.ago('2026-11-03T12:00:00Z'), %s.ago(Date.parse('2026-11-04T11:00:30Z')), %s.ago('2026-11-02T12:18:00Z')]" % (w, w, w)}],
                clock="2026-11-04T12:00:00Z")
    yesterday, hour, two = s[-1]["eval"]
    assert yesterday == "yesterday" and hour == "1 hour ago" and two == "2 days ago", s[-1]["eval"]


def test_not_today_late_on_the_night_the_clocks_go_forward_is_tomorrow(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"eval": "LJS.words.plusDays(1)"}], clock="2027-03-27T23:30:00Z")
    assert s[-1]["eval"] == "2027-03-28"


def test_the_pay_floor_reads_what_people_write_and_refuses_the_rest(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"eval": "['90k', '90,000', '£85,000', 'CAD 95000', '90,000-100,000', '90', 'about ninety'].map(LJS.words.payNumber)"}])
    assert s[-1]["eval"] == [90000, 90000, 85000, 95000, None, None, None], s[-1]["eval"]


def test_a_picture_address_is_this_pages_own_or_https(run, tmp_path):
    html = _page(tmp_path)
    s = _script(run, html, [{"eval": "['//evil.example/x.png', '/\\\\evil.example/x.png', '/_blob/abc', 'https://x.example/a.png'].map(LJS.words.assetUrl)"}])
    off, back, own, ok = s[-1]["eval"]
    assert not off.startswith("//") and not back.startswith("/\\") and own == "/_blob/abc" and ok == "https://x.example/a.png"
