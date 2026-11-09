"""A person's card in Contacts reads as one calm card.

The maintainer, 2026-11-09, "any better way to display", on a card for someone not written to:
under the note, five stacked lines of different weights and tones: "Waiting for their profile:
Claude reads it next time this page is open in the Claude app on your computer, then rewrites
this note.", "290 of 300 characters", "Where they live is not on record: check their profile
before you send.", "You asked says waiting for profilie, can u action on all the ones
waiting? ..." and "Changing it next · starting in a moment · 1m 53s" with Stop Claude at the
card's far edge. Now:

- the note's facts are one quiet line, "290/300 · Waiting for their profile · Location not on
  record", the sentences behind its one "?";
- a change asked with the pencil is one soft grey block under the draft: what was asked, then
  its state with Stop Claude beside the words;
- work sent to a chat that is up says "Starting in a moment" for half a minute at most, then
  "Waiting for Claude, asked at <time>";
- words in one note's pencil box about every note waiting for a profile, or naming the others,
  put them all on the page's reading list and leave this note as it is, the block saying so in
  a line (tools/tweak.py about_others).

Every name here is invented.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402
from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import app_alerts  # noqa: E402
import app_model  # noqa: E402
import app_page  # noqa: E402
import page_db  # noqa: E402
import tweak  # noqa: E402

CLOCK = "2026-10-25T09:00:00Z"
WIDE = {"width": 1440, "height": 1000}
PHONE = {"width": 390, "height": 1000}
ASKS = "says waiting for profile, can u action on all the ones waiting? lea, ana, bo, cal etc"


# ------------------------------------------------------------------ the engine


def test_the_count_and_the_location_have_their_few_words_from_the_engine():
    assert app_model.count_of(290, 300, "first_note")["short"] == "290/300"
    assert app_page.tables()["facts"]["where_unknown"] == list(app_model.WHERE_UNKNOWN)
    assert set(app_model.READ_HOLD_SHORT) == set(app_model.READ_HOLD)
    assert all(len(w) <= 30 for w in app_model.READ_HOLD_SHORT.values()), app_model.READ_HOLD_SHORT


WAITING = [{"id": "msg-a", "contact": "a", "first_name": "Ines", "hold": "Waiting"},
           {"id": "msg-b", "contact": "b", "first_name": "Lea", "hold": "Waiting"},
           {"id": "msg-c", "contact": "c", "first_name": "Bo", "hold": "Waiting"},
           {"id": "msg-d", "contact": "d", "first_name": "Taro", "hold": None}]


@pytest.mark.parametrize("words", [ASKS, "can you do Lea's too", "read all their profiles first",
                                   "action every one of the waiting notes"])
def test_pencil_words_about_every_waiting_note_are_about_them_all(words):
    got = tweak.about_others(words, WAITING[0], WAITING)
    assert [m["contact"] for m in got] == ["a", "b", "c"], words


@pytest.mark.parametrize("words", ["make it warmer", "shorter, and mention the Leeds office",
                                   "drop the last sentence", "ask about all their planning tools",
                                   "mention Taro introduced us", "say hi to Bo's team"])
def test_pencil_words_about_this_note_stay_a_change_to_it(words):
    # "Bo" is too short to be told from a word; Taro has no note waiting.
    assert tweak.about_others(words, WAITING[0], WAITING) == [], words


def test_none_waiting_means_the_words_are_this_notes_own():
    assert tweak.about_others(ASKS, WAITING[3], [WAITING[3]]) == []


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


def test_words_about_every_waiting_note_put_them_on_the_reading_list_and_leave_this_one(t):
    t.python("import sys; sys.path[:0] = ['tools', 'tools/network']\n"
             "import person, os\n"
             "p = person.state('documents', 'network', 'kestrel_mutual_ansgar', 'draft.md')\n"
             "os.makedirs(os.path.dirname(p), exist_ok=True)\n"
             "open(p, 'w', encoding='utf-8').write('WAITS ON A READ: nothing was read about them.\\n\\n"
             "Hi Pell, I would love to hear how the team works.\\n')\n")
    (msg,) = t.model()["messages"]
    assert msg["hold"], msg
    before = msg["text"]
    # The example person pastes profiles: the line says to paste, and nothing is queued.
    pasted = t.tweak("apply", "message", msg["id"], text=ASKS, rev=msg["rev"])
    assert pasted["status"] == "done" and pasted["unchanged"] is True and pasted["queued"] == [], pasted
    assert "Paste each one's profile on their card" in pasted["summary"], pasted
    t.python("import sys; sys.path[:0] = ['tools']\nimport profile_set\n"
             "profile_set.set_line('networking.py', 'PROFILE_READS', 'browser')\n")
    got = t.tweak("apply", "message", msg["id"], text=ASKS + " ", rev=msg["rev"])
    assert got["status"] == "done" and got["unchanged"] is True and got["queued"] == ["kestrel_mutual_ansgar"], got
    assert "this note is unchanged" in got["summary"] and "open in the Claude app on your computer" in got["summary"], got
    assert t.model()["messages"][0]["text"] == before
    queued = t.python("import sys; sys.path[:0] = ['tools', 'tools/network']\nimport reading, json\n"
                      "print(json.dumps([q['contact'] for q in reading.page_queue()]))")
    assert json.loads(queued) == ["kestrel_mutual_ansgar"]
    # Its own words are still a change to it.
    own = t.tweak("apply", "message", msg["id"], text="make it warmer", rev=msg["rev"])
    assert own["status"] == "needs_model" and not own.get("unchanged"), own


def test_a_change_finished_with_nothing_changed_says_so_on_its_card(tmp_path):
    now = dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc)
    db = {"work": {"tweak~x": {"version": 3, "data": {"kind": "tweak", "status": "running", "claimed_by": "cloud-1",
                                                        "args": {"target": {"id": "msg-a", "output": "message"}}}}}}
    got = page_db.finish(db, "tweak~x", now, str(tmp_path), summary="That was about every note waiting for a profile.",
                         chat="cloud-1", unchanged=True)
    sets = [json.load(open(e["file_path"], encoding="utf-8")) for b in got["batches"]
            for e in json.load(open(b, encoding="utf-8")) if e["collection"] == "work" and e.get("file_path")]
    assert any((s.get("result") or {}).get("unchanged") is True for s in sets), sets


# ------------------------------------------------------------------ the page


@pytest.fixture(scope="module")
def run():
    yield from browser()


WID = "tweak~msg-kit-1~a1b2c3d4e5"


def _model():
    m = copy.deepcopy(_sample())
    kit = next(x for x in m["messages"] if x["id"] == "msg-kit-1")
    body = ("Hi Kit, hope you're well. I'm a data analyst, ex-Fernhill and Quayside, and just moved to "
            "Leeds from Bristol. I build demand forecasts and stock models in Python and SQL, which I "
            "imagine is similar to some of the planning work on your team. I'd love to hear what "
            "you're working on. Thanks!")
    kit.update(body=body, text=body, chars=len(body), limit=300, count=app_model.count_of(len(body), 300, "first_note"),
               hold=app_model.READ_HOLD["browser"], where_unknown=True, wave=None, wave_label=None, alerts=[],
               paste=app_alerts.paste_profile("msg-kit-1", "Kit"))
    m["to_send"] = app_model.to_send(m["messages"])
    m["to_read"] = app_model.to_read(m["messages"])
    m["linkedin"] = {"reading": {"id": "linkedin-reader", "page_reads": False, "ok": None, "setting": "browser",
                                 "rev": "r0", "hold": dict(app_model.READ_HOLD),
                                 "hold_short": dict(app_model.READ_HOLD_SHORT), "queue": []}}
    return m, kit


def _seed(kit, asked="2026-10-25T08:58:07Z", rung="2026-10-25T08:58:10Z", **more):
    work = {"kind": "tweak", "status": "queued", "to": "either", "title": "Change the note to Kit", "asked_at": asked,
            "asked_from": {"tab": "contacts"},
            "args": {"v": 1, "target": {"id": kit["id"], "output": "message", "contact": kit["contact"]},
                     "changes": [], "text": ASKS, "keep": None},
            "stages": [{"name": "Getting started", "est_s": 15}, {"name": "Changing it", "est_s": 45}]}
    work.update(more)
    return {"work/" + WID: work, "meta/doorbell": {"rung_at": rung, "ids": [WID], "rung": {WID: rung}},
            "beats/helper": {"seen_at": "2026-10-25T08:59:30Z", "watching": True, "kind": "cloud"}}


CARD = "#main [data-item=\"{cid}\"]"
LOOK = ("(() => {{ const c = document.querySelector('" + CARD + "'); const f = c.querySelector('.msg-facts');"
        " const g = c.querySelector('[data-tweak-going], [data-tweak-done]'); const t = g && g.querySelector('.wi-text');"
        " const s = g && g.querySelector('[data-k$=\":cancel\"], .btn-stop, button.stop');"
        " const b = [...(g ? g.querySelectorAll('button') : [])].find((x) => /Stop Claude/.test(x.textContent));"
        " const seen = (el) => {{ const k = el.cloneNode(true); k.querySelectorAll('.sr-only').forEach((x) => x.remove()); return k.textContent; }};"
        " return {{line: f ? seen(f.querySelector('.facts-line')) : '', facts: f ? f.textContent : '',"
        " qs: c.querySelectorAll('button.q').length, block: g ? g.innerText : '', grey: g ? getComputedStyle(g).backgroundColor : '',"
        " card: getComputedStyle(c).backgroundColor, gap: t && b ? b.__drawnRect().left - t.__drawnRect().right : null,"
        " stopIn: !!b, lines: [...c.querySelectorAll('.pdraft > p, .pdraft > div')].map((x) => x.className)}}; }})()")


def _look(run, tmp_path, vp, seed, scheme="light", steps=()):
    m, kit = _model()
    html = _write(tmp_path, "card", m)
    got = run("script", html=html, viewport=vp, clock=CLOCK, seed=seed, fake={"canSend": "available"},
              steps=[{"hash": "contacts", "eval": LOOK.format(cid=kit["contact"])}, *steps])
    return got, kit


def test_the_notes_facts_are_one_quiet_line_with_one_question_mark(run, tmp_path):
    got, kit = _look(run, tmp_path, WIDE, {})
    look = got["steps"][0]["eval"]
    n = len(kit["body"])
    assert look["line"] == f"{n}/300 · Waiting for their profile · Location not on record", look
    # The sentences are behind its one "?", never three lines of their own.
    assert "next time this page is open in the Claude app on your computer" in look["facts"], look
    assert "check their profile before you send" in look["facts"] and look["qs"] == 1, look
    card = got["steps"][0]["main"]
    assert "Where they live is not on record" not in card, card


@pytest.mark.parametrize("vp", [WIDE, PHONE], ids=["wide", "phone"])
def test_a_pencil_request_is_one_grey_block_its_state_honest_and_stop_beside_it(run, tmp_path, vp):
    got, kit = _look(run, tmp_path, vp, _seed(_model()[1]))
    look = got["steps"][0]["eval"]
    block = look["block"]
    assert block.startswith("You asked") and "can u action on all the ones waiting" in block, block
    # Sent about two minutes ago to a chat that is up and not taken: waiting, with when.
    assert "Waiting for Claude, asked at" in block, block
    assert "starting in a moment" not in block.lower() and "Changing it next" not in block, block
    assert look["stopIn"] and look["grey"] != look["card"], look
    if vp is WIDE:
        assert look["gap"] is not None and 0 <= look["gap"] <= 24, look


def test_starting_in_a_moment_is_said_only_for_half_a_minute(run, tmp_path):
    seed = _seed(_model()[1], asked="2026-10-25T08:59:50Z", rung="2026-10-25T08:59:52Z")
    got, kit = _look(run, tmp_path, WIDE, seed, steps=[{"run": 60000, "eval": LOOK.format(cid=_model()[1]["contact"])}])
    first, later = got["steps"][0]["eval"]["block"], got["steps"][1]["eval"]["block"]
    assert "Starting in a moment" in first, first
    assert "Waiting for Claude, asked at" in later and "Starting in a moment" not in later, later


def test_a_request_about_every_waiting_note_says_what_was_done_and_no_new_version(run, tmp_path):
    said = ("That was about every note waiting for a profile, so this one is unchanged. Kit, Lea and Ana are on your "
            "page's reading list: it reads them while it is open in the Claude app on your computer, then rewrites each note.")
    seed = _seed(_model()[1], status="done", claimed_at="2026-10-25T08:58:30Z", finished_at="2026-10-25T08:59:00Z",
                 result={"summary": said, "links": [], "unchanged": True})
    got, kit = _look(run, tmp_path, WIDE, seed)
    block = got["steps"][0]["eval"]["block"]
    assert block.startswith("You asked") and said in block, block
    assert "new version" not in block.lower() and "Stop Claude" not in block, block


# ------------------------------------------------------------------ the computer's work

# A cloud chat took a pencil change on a note waiting for a profile read, could not read
# LinkedIn, closed it as done, and the chat on the computer never saw it (the maintainer,
# 2026-11-09). Work about such a note is the computer's: decided as it is queued, checked again
# when a chat looks for work (for items an older page queued to "either"), and a cloud chat that
# holds one never closes it as done.

ROUTE = r'''
import sys, json, datetime as dt
sys.path[:0] = ["tools", "tools/network"]
import os, person, profile_set, page_db, reading
p = person.state("documents", "network", "kestrel_mutual_ansgar", "draft.md")
os.makedirs(os.path.dirname(p), exist_ok=True)
open(p, "w", encoding="utf-8").write("WAITS ON A READ: nothing was read about them.\n\nHi Pell.\n")
profile_set.set_line("networking.py", "PROFILE_READS", "browser")
now = dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc)
item = {"kind": "tweak", "status": "queued", "to": "either", "asked_at": "2026-10-25T08:58:00Z",
        "args": {"target": {"id": "msg-kestrel_mutual_ansgar", "output": "message"}, "text": "warmer"}}
db = {"work": {"tweak~msg-kestrel_mutual_ansgar~1": {"version": 2, "data": dict(item)}}, "locks": {}}
out = {"needs": page_db.needs_computer(item), "cloud": page_db.can_take(item, "cloud"),
       "computer": page_db.can_take(item, "computer"),
       "next_cloud": page_db.next_item(db, "cloud", now), "next_computer": (page_db.next_item(db, "computer", now) or {}).get("work")}
asked = page_db.ask({"work": {}}, "tweak", "Change the note to Pell", now, sys.argv[1] + "/ask",
                    args={"target": {"id": "msg-kestrel_mutual_ansgar", "output": "message"}, "text": "warmer"})
out["asked_to"] = [json.load(open(e["file_path"]))["to"] for b in asked["batches"] for e in json.load(open(b)) if e.get("file_path")]
held = {"work": {"tweak~x": {"version": 3, "data": dict(item, status="running", claimed_by="cloud-1")}}, "locks": {}}
got = page_db.finish(held, "tweak~x", now, sys.argv[1] + "/fin", summary="Your note is warmer now.", chat="cloud-1", chat_kind="cloud")
fields = [json.load(open(e["file_path"])) for b in got["batches"] for e in json.load(open(b)) if e.get("file_path")]
out["finished"] = [got["status"], [f.get("status") for f in fields], [f.get("to") for f in fields]]
got = page_db.finish(held, "tweak~x", now, sys.argv[1] + "/fin2", summary="Your note is warmer now.", chat="cloud-1", chat_kind="computer")
out["computer_finish"] = got["status"]
# Once their page is read, any chat may rewrite it.
reading.save("kestrel_mutual_ansgar", {"sources": [{"kind": "browser", "read_on": "2026-10-25"}], "items": []})
out["after_read"] = page_db.can_take(item, "cloud")
print(json.dumps(out))
'''


def test_work_about_a_note_waiting_for_a_read_is_the_computers(t, tmp_path):
    got = json.loads(t.python(ROUTE.replace("sys.argv[1]", repr(str(tmp_path)))))
    assert got["needs"] == ["kestrel_mutual_ansgar"], got
    # Checked again when a chat looks for work: a cloud chat never claims it, the computer's does.
    assert got["cloud"] is False and got["computer"] is True, got
    assert got["next_cloud"] is None and got["next_computer"] == "tweak~msg-kestrel_mutual_ansgar~1", got
    # Decided as it is queued.
    assert got["asked_to"] == ["computer"], got
    # A cloud chat holding one never closes it as done: it goes back, queued for the computer.
    assert got["finished"][0] == "queued" and got["finished"][1] == ["queued"] and got["finished"][2] == ["computer"], got
    assert got["computer_finish"] == "done", got
    assert got["after_read"] is True, got


def test_the_engine_says_where_a_waiting_notes_work_runs(t):
    t.python("import sys; sys.path[:0] = ['tools', 'tools/network']\n"
             "import person, os, profile_set\n"
             "p = person.state('documents', 'network', 'kestrel_mutual_ansgar', 'draft.md')\n"
             "os.makedirs(os.path.dirname(p), exist_ok=True)\n"
             "open(p, 'w', encoding='utf-8').write('WAITS ON A READ: nothing was read about them.\\n\\nHi Pell.\\n')\n")
    (msg,) = t.model()["messages"]
    # The example person pastes profiles: nothing for the computer to read.
    assert msg["hold"] and msg["work_to"] == "either", msg
    t.python("import sys; sys.path[:0] = ['tools']\nimport profile_set\n"
             "profile_set.set_line('networking.py', 'PROFILE_READS', 'browser')\n")
    (msg,) = t.model()["messages"]
    assert msg["work_to"] == "computer", msg


def test_the_card_says_its_pencil_waits_for_the_claude_app_on_the_computer(run, tmp_path):
    m, kit = _model()
    kit["work_to"] = "computer"
    html = _write(tmp_path, "computer", m)
    # Queued to "either" by an older page; no chat on the computer has checked in.
    got = run("script", html=html, viewport=WIDE, clock=CLOCK, seed=_seed(kit), fake={"canSend": "available"},
              steps=[{"hash": "contacts", "eval": LOOK.format(cid=kit["contact"])}])
    block = got["steps"][0]["eval"]["block"]
    assert "Waiting for the Claude app on your computer" in block and "Waiting for Claude," not in block, block
