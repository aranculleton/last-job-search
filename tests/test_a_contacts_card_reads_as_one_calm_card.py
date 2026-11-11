"""A person's card in Contacts reads as one calm card.

The maintainer, 2026-11-09, "any better way to display", on a card for someone not written to:
under the note, five stacked lines of different weights and tones: "Waiting for their profile:
Claude reads it next time this page is open in the Claude app on your computer, then rewrites
this note.", "290 of 300 characters", "Where they live is not on record: check their profile
before you send.", "You asked says waiting for profilie, can u action on all the ones
waiting? ..." and "Changing it next · starting in a moment · 1m 53s" with Stop Claude. Now:

- the note's facts are one quiet line, "290/300 · Waiting for their profile · Location not on
  record", the sentences behind its one "?"; a note held back on purpose keeps its own line,
  with its one way on (tests/test_a_note_held_for_its_employer_says_so.py);
- a change asked with the pencil is one soft grey block under the draft: what was asked, then
  its state with Stop Claude beside the words;
- work sent to a chat that is up says "Starting in a moment" for half a minute at most, then
  "Waiting for Claude, asked at <time>";
- words in one note's pencil box about every note waiting for a profile, or naming the others,
  put them all on the page's reading list and leave this note as it is (tools/tweak.py
  about_others), finished as unchanged, so the card says what was done at once.

Every name here is invented.
"""
from __future__ import annotations

import copy
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
           {"id": "msg-d", "contact": "d", "first_name": "Taro", "hold": None},
           # Held back on purpose, not waiting for a read: never one of them.
           {"id": "msg-e", "contact": "e", "first_name": "Ottilie", "hold": "On hold",
            "hold_why": "employer_full"}]


@pytest.mark.parametrize("words", [ASKS, "can you do Lea's too", "read all their profiles first",
                                   "action every one of the waiting notes"])
def test_pencil_words_about_every_waiting_note_are_about_them_all(words):
    got = tweak.about_others(words, WAITING[0], WAITING)
    assert [m["contact"] for m in got] == ["a", "b", "c"], words


@pytest.mark.parametrize("words", ["make it warmer", "shorter, and mention the Leeds office",
                                   "drop the last sentence", "ask about all their planning tools",
                                   "mention Taro introduced us", "say hi to Bo's team",
                                   "mention Ottilie from the same team"])
def test_pencil_words_about_this_note_stay_a_change_to_it(words):
    # "Bo" is too short to be told from a word; Taro has no note waiting, and Ottilie's waits
    # on a hold of its own, not a read.
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
    assert msg["hold"] and not msg.get("hold_why"), msg
    before = msg["text"]
    # The example person pastes profiles: the summary says to paste, and nothing is queued.
    pasted = t.tweak("apply", "message", msg["id"], text=ASKS, rev=msg["rev"])
    assert pasted["status"] == "done" and pasted["outcome"] == "unchanged" and pasted["queued"] == [], pasted
    assert pasted["summary"].startswith("Paste their profile on their card instead"), pasted
    assert "this note is unchanged" in pasted["summary"], pasted
    t.python("import sys; sys.path[:0] = ['tools']\nimport profile_set\n"
             "profile_set.set_line('networking.py', 'PROFILE_READS', 'browser')\n")
    got = t.tweak("apply", "message", msg["id"], text=ASKS + " ", rev=msg["rev"])
    assert got["status"] == "done" and got["outcome"] == "unchanged" and got["queued"] == ["kestrel_mutual_ansgar"], got
    # Where it is read, as the note's own line says it: on their computer by itself where it
    # is ready, else by the page while it is open in the Claude app there.
    there = t.model()["messages"][0]["hold"] == app_model.READ_HOLD["computer"]
    where = "on your computer by itself" if there else "while your page is open in the Claude app on your computer"
    assert got["summary"].startswith("Pell is on your page's reading list instead: Claude reads their profile " + where), got
    # The outcome is one `app.py done --outcome` takes, so its card says it at once.
    assert got["outcome"] in page_db.OUTCOMES
    assert t.model()["messages"][0]["text"] == before
    queued = t.python("import sys; sys.path[:0] = ['tools', 'tools/network']\nimport reading, json\n"
                      "print(json.dumps([q['contact'] for q in reading.page_queue()]))")
    assert json.loads(queued) == ["kestrel_mutual_ansgar"]
    # Its own words are still a change to it.
    own = t.tweak("apply", "message", msg["id"], text="make it warmer", rev=msg["rev"])
    assert own["status"] == "needs_model" and not own.get("outcome"), own


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
               hold=app_model.READ_HOLD["browser"], hold_why=None, where_unknown=True, wave=None, wave_label=None, alerts=[],
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
        " const b = [...(g ? g.querySelectorAll('button') : [])].find((x) => /Stop Claude/.test(x.textContent));"
        " const seen = (el) => {{ const k = el.cloneNode(true); k.querySelectorAll('.sr-only').forEach((x) => x.remove()); return k.textContent; }};"
        " return {{line: f ? seen(f.querySelector('.facts-line')) : '', facts: f ? f.textContent : '',"
        " qs: c.querySelectorAll('button.q').length, block: g ? g.innerText : '', grey: g ? getComputedStyle(g).backgroundColor : '',"
        " card: getComputedStyle(c).backgroundColor, gap: t && b ? b.__drawnRect().left - t.__drawnRect().right : null,"
        " stopIn: !!b, held: c.querySelectorAll('[data-k^=\"held:\"]').length}}; }})()")


def _look(run, tmp_path, vp, seed, steps=()):
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
    # The sentences are behind its one "?", never three lines of their own: the example
    # person's computer reads LinkedIn by itself, so the engine's line for that.
    assert app_model.READ_HOLD["computer"] in look["facts"], look
    assert "check their profile before you send" in look["facts"] and look["qs"] == 1, look
    # Why it waits is said once, in the line.
    assert look["held"] == 1, look
    card = got["steps"][0]["main"]
    assert "Where they live is not on record" not in card, card


@pytest.mark.parametrize("vp", [WIDE, PHONE], ids=["wide", "phone"])
def test_a_pencil_request_is_one_grey_block_its_state_honest_and_stop_beside_it(run, tmp_path, vp):
    got, kit = _look(run, tmp_path, vp, _seed(_model()[1]))
    look = got["steps"][0]["eval"]
    block = look["block"]
    assert block.startswith("You asked") and "can u action on all the ones waiting" in block, block
    # Sent about two minutes ago to a chat that is up and not taken: waiting, never "starting in
    # a moment" with a clock, and never "Changing it next" over work nothing has started. Beside
    # Claude's work on a wide screen it says its one state (the panel says when).
    assert "Waiting for Claude" in block, block
    if vp is PHONE:
        assert "Waiting for Claude, asked at" in block, block
    assert "starting in a moment" not in block.lower() and "Changing it next" not in block, block
    assert look["stopIn"] and look["grey"] != look["card"], look
    if vp is WIDE:
        assert look["gap"] is not None and 0 <= look["gap"] <= 24, look


def test_starting_in_a_moment_is_said_only_for_half_a_minute(run, tmp_path):
    seed = _seed(_model()[1], asked="2026-10-25T08:59:50Z", rung="2026-10-25T08:59:52Z")
    got, kit = _look(run, tmp_path, PHONE, seed, steps=[{"run": 60000, "eval": LOOK.format(cid=_model()[1]["contact"])}])
    first, later = got["steps"][0]["eval"]["block"], got["steps"][1]["eval"]["block"]
    assert "Starting in a moment" in first, first
    assert "Waiting for Claude, asked at" in later and "Starting in a moment" not in later, later


def test_a_request_about_every_waiting_note_says_what_was_done_and_no_new_version(run, tmp_path):
    said = ("Kit, Lea and Ana are on your page's reading list instead: Claude reads their profiles while your "
            "page is open in the Claude app on your computer, then rewrites each note. That was about every "
            "note waiting for a profile, so this one is unchanged.")
    seed = _seed(_model()[1], status="done", claimed_at="2026-10-25T08:58:30Z", finished_at="2026-10-25T08:59:00Z",
                 result={"summary": said, "links": [], "outcome": "unchanged"})
    got, kit = _look(run, tmp_path, WIDE, seed)
    block = got["steps"][0]["eval"]["block"]
    assert "Kit, Lea and Ana are on your page's reading list instead" in block, block
    assert "new version" not in block.lower() and "putting" not in block.lower() and "Stop Claude" not in block, block
