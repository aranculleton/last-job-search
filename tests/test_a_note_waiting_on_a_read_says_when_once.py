"""A note waiting for its person's profile says, once, when the reading happens, and its count is
quiet while it is within the limit.

The maintainer, 2026-11-07, on three cards for people not yet written to: "when exactly is this
waiting for claude thing going to happen? is there a simple way to do it in to do or even here
in the contacts page?" and "also why is the characters thing in yellow?". Each card said "Not
ready to send: waiting for their profile: ..." and then the same words again as an alert, with
"Paste <name>'s profile" carrying a networking run's gauge ("a lot of your allowance"), and
"291 of 300 characters" in amber on a note that was fine.

What is true (tools/network/reading.py; templates/app/app.js, flow B): the reading is the page's
own, never a chat's. It runs by itself only while the page is open in the Claude app on a
computer, in Claude's browser, signed in to LinkedIn there, in the tab the page keeps for it
(opened once by Read them, never by itself). Anywhere else it waits.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import app_alerts  # noqa: E402
import app_model  # noqa: E402
import page_db  # noqa: E402

CLOCK = "2026-10-25T09:00:00Z"
PHONE = {"width": 390, "height": 844}


# ------------------------------------------------------------------ the engine


def test_a_count_within_the_limit_is_quiet_and_near_only_in_the_last_twentieth():
    at_rest = app_model.count_of(291, 300, "first_note")
    assert at_rest["tone"] == "muted" and at_rest["near"] is True and at_rest["near_at"] == 285, at_rest
    assert app_model.count_of(284, 300, "first_note")["near"] is False
    over = app_model.count_of(301, 300, "first_note")
    assert over["tone"] == "bad" and over["over"] is True and over["near"] is False, over
    # A reply's long limit: said only near or over it, by the same rule.
    assert app_model.count_of(7000, 8000, "reply")["show"] is False
    assert app_model.count_of(7700, 8000, "reply")["show"] is True


def test_a_held_note_is_not_to_send_and_is_on_the_one_reading_list():
    msgs = [{"id": "msg-a", "contact": "a", "hold": "Waiting for their profile: ..."},
            {"id": "msg-b", "contact": "b", "hold": None},
            {"id": "msg-c", "contact": "c", "hold": "Waiting for their profile: ..."}]
    assert app_model.to_send(msgs) == {"n": 1, "ids": ["msg-b"]}
    assert app_model.to_read(msgs) == {"n": 2, "ids": ["msg-a", "msg-c"], "contacts": ["a", "c"]}
    # Said once: no alert repeating the hold, whatever else the note has.
    alerts, suggest = app_alerts.for_message(None, {"id": "msg-a", "hold": "Waiting", "kind": "first_note",
                                                    "limit": 300, "chars": 320})
    assert alerts == [] and suggest is None


def test_pasting_a_profile_costs_one_notes_rewrite_not_a_networking_run():
    a = app_alerts.paste_profile("msg-a", "Ash")
    assert a["cost"]["state"] == 2 and a["cost"]["seconds"] == sum(s for _, _, s in page_db.REWRITE_STAGES), a
    assert a["cost"]["seconds"] < sum(s for _, _, s in page_db.STAGES["network"])
    # This copy's own rewrites, once it has three, say their own time, and set the gauge by it.
    assert app_alerts.paste_profile("msg-a", "Ash", {"rewrite": 50})["cost"] == {"state": 1, "label": app_alerts.COSTS[1], "seconds": 50}
    assert app_alerts.paste_profile("msg-a", "Ash", {"rewrite": 900})["cost"]["state"] == 3


def test_a_rewrite_is_timed_apart_from_a_networking_run():
    import datetime as dt
    now = dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc)

    def done(i, minutes, rewrite):
        start = now - dt.timedelta(hours=1 + i)
        return {"data": {"kind": "network", "status": "done", "args": {"rewrite": True} if rewrite else {},
                         "claimed_at": start.isoformat(), "finished_at": (start + dt.timedelta(minutes=minutes)).isoformat()}}
    db = {"work": {f"w{i}": done(i, m, r) for i, (m, r) in enumerate([(2, True), (3, True), (2, True), (25, False), (30, False), (28, False)])}}
    assert page_db.work_times(db, now) == {"network": 28 * 60, "rewrite": 2 * 60}


class _Ctx:
    def __init__(self):
        self._got = {}

    def _once(self, key, make):
        if key not in self._got:
            self._got[key] = make()
        return self._got[key]


@pytest.mark.parametrize("setting,ready,want", [("browser", True, "computer"), ("browser", False, "browser"),
                                                ("paste", True, "paste")])
def test_the_notes_line_says_where_it_is_read(monkeypatch, setting, ready, want):
    import reading
    monkeypatch.setattr(reading, "reads_now", lambda: setting)
    monkeypatch.setattr(app_model, "computer_reads", lambda ctx: ready)
    assert app_model.read_hold(_Ctx()) == app_model.READ_HOLD[want]
    assert "press" not in app_model.READ_HOLD["computer"].lower()


def _reads_model(computer=True, setting="browser"):
    return {"person": {"computer": computer},
            "linkedin": {"reading": {"setting": setting, "paused": False,
                                     "queue": [{"id": "read-kit_a", "contact": "kit_a", "first_name": "Kit"}]}},
            "to_read": {"n": 2, "ids": ["msg-kit_a", "msg-ash_b"], "contacts": ["kit_a", "ash_b"]}}


def test_with_their_computer_ready_the_read_is_sent_there_by_itself():
    """No one presses anything: the view's own fixes queue one `network` item `to: computer`,
    reading each waiting person there and rewriting their notes, which no cloud chat may
    take (page_db.computer_only). Once a day for the same people, never twice while going."""
    import datetime as dt
    import app
    now = dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc)
    wid, fields = app.computer_reads(_reads_model(), {}, now)
    assert wid.startswith(page_db.safe_id(app.COMPUTER_READS + "20261025")), wid
    assert fields["kind"] == "network" and fields["to"] == "computer" and fields["status"] == "queued", fields
    assert fields["args"]["contacts"] == ["kit_a", "ash_b"] and fields["args"]["read_first"] is True, fields
    assert fields["title"] == "Reading 2 profiles on your computer", fields
    assert page_db.computer_only(fields, "cloud") and not page_db.computer_only(fields, "computer")
    # The same view again: the same id, which the store refuses to make twice.
    assert app.computer_reads(_reads_model(), {}, now)[0] == wid
    # Already on its way, by this or a rewrite: nothing more.
    going = {wid: {"data": dict(fields, status="running")}}
    assert app.computer_reads(_reads_model(), going, now) is None
    # No computer known ready, or profiles pasted: never sent there.
    assert app.computer_reads(_reads_model(computer=False), {}, now) is None
    assert app.computer_reads(_reads_model(setting="paste"), {}, now) is None
    # The computer's chat is told how to do it.
    with open(os.path.join(os.path.dirname(HERE), ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        assert "`args.read_first`" in fh.read()


# ------------------------------------------------------------------ the page


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _model(computer=False):
    m = copy.deepcopy(_sample())
    # The page's own reading, with no computer known ready (the example person has one: the
    # last test here is theirs).
    m["person"]["computer"] = computer
    ash = next(x for x in m["messages"] if x["id"] == "msg-ash-1")
    body = (ash.get("body") or ash["text"]).strip()
    body = (body + " " + "x" * 300)[:291]
    ash.update(body=body, text=body, chars=291, limit=300, count=app_model.count_of(291, 300, "first_note"))
    kit = next(x for x in m["messages"] if x["id"] == "msg-kit-1")
    kit.update(hold=app_model.READ_HOLD["browser"], wave=None, wave_label=None, alerts=[],
               paste=app_alerts.paste_profile("msg-kit-1", "Kit"))
    m["to_send"] = app_model.to_send(m["messages"])
    m["to_read"] = app_model.to_read(m["messages"])
    m["linkedin"] = {"reading": {"id": "linkedin-reader", "page_reads": False, "ok": None, "setting": "browser",
                                 "rev": "r0", "hold": dict(app_model.READ_HOLD),
                                 "queue": [{"id": "read-" + kit["contact"], "contact": kit["contact"], "first_name": "Kit",
                                            "employer": kit["employer"], "mode": "deep", "asked_on": "2026-10-25",
                                            "reach": "reach/" + kit["contact"], "rev": "q1"}]}}
    return m, kit


KIT = "(document.querySelector('#main [data-item=\"{cid}\"]') || {{}}).innerText || ''"
LINE = "(document.querySelector('[data-k=\"held:msg-kit-1\"]') || {}).textContent || ''"
QUEUE = ("[(document.querySelector('[data-item=\"reading-queue\"]') || {}).textContent || '',"
         " !!document.querySelector('[data-item=\"reading-queue\"] [data-k=\"read-them\"]')]")
# The count as drawn, or as the field's own typing redraws it (the span itself).
COUNT = "((el) => el ? (el.querySelector('.count') || el).className : '')(document.getElementById('cnt-msg-ash-1'))"
# As the page stands once it knows it is open in the Claude app, signed in, with its tab kept.
IN_APP = ("(() => { const r = LJS.state().reading; r.here = true; r.ok = true; r.needTab = false; {more} LJS.render();"
          " return 1; })()")


def test_away_from_the_computer_the_card_says_when_once_and_paste_is_one_notes_minutes(run, tmp_path):
    m, kit = _model()
    html = _write(tmp_path, "held", m)
    got = run("script", html=html, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "eval": KIT.format(cid=kit["contact"])},
        {"hash": "todo", "eval": QUEUE}])
    card = got["steps"][0]["eval"]
    assert card.count("Waiting for their profile") == 1, card
    assert "next time this page is open in the Claude app on your computer" in card, card
    assert "Not ready to send" not in card and "Copy" not in card, card
    # Paste is the alternative, beside it, with one note's rewrite as its gauge.
    assert "Paste Kit's profile" in card and "2 min" in card and "a lot of your allowance" not in card, card
    todo, read_them = got["steps"][1]["eval"]
    assert "Open your page in the Claude app on your computer to read 1 profile" in todo and not read_them, todo
    # And none of it twice on To do: the note is not a row of Messages to send.
    assert "Kit" not in (got["steps"][1]["main"].split("Messages to send", 1) + [""])[1].split("Open Contacts", 1)[0]


def test_in_the_claude_app_it_reads_by_itself_and_the_card_says_reading(run, tmp_path):
    m, kit = _model()
    html = _write(tmp_path, "held-app", m)
    cid = kit["contact"]
    got = run("script", html=html, viewport={"width": 1280, "height": 900}, clock=CLOCK, steps=[
        {"hash": "contacts", "eval": IN_APP.replace("{more}", "r.busy = false; r.cur = null;")},
        {"eval": LINE},
        {"hash": "todo", "eval": QUEUE},
        {"hash": "contacts", "eval": IN_APP.replace("{more}", "r.busy = true; r.cur = '" + cid + "'; r.at = \"Kit's profile\"; r.total = 1; r.done = 0;")},
        {"eval": "[" + LINE + ", !!document.querySelector('[data-k=\"held:msg-kit-1\"] .spin')]"},
        {"hash": "todo", "eval": QUEUE}])
    waiting = got["steps"][1]["eval"]
    assert waiting.startswith("Waiting its turn: Claude reads their profile here by itself"), waiting
    todo, read_them = got["steps"][2]["eval"]
    # What Claude does by itself is never a button (DESIGN.md, Buttons).
    assert "Claude reads 1 profile by itself" in todo and "Nothing to press" in todo and not read_them, todo
    line, spin = got["steps"][4]["eval"]
    assert line.strip() == "Reading their profile…" and spin, line
    todo, read_them = got["steps"][5]["eval"]
    assert "Claude is reading 1 profile" in todo and "Reading Kit's profile, 1 of 1" in todo and not read_them, todo


def test_a_count_is_grey_at_rest_amber_only_while_editing_near_the_limit_and_red_over(run, tmp_path):
    m, _kit = _model()
    html = _write(tmp_path, "count", m)
    got = run("script", html=html, viewport={"width": 1280, "height": 900}, clock=CLOCK, steps=[
        {"hash": "contacts", "eval": COUNT},
        {"tap": "[data-k=\"pen:msg-ash-1\"]"},
        {"tap": "[data-k=\"penedit:msg-ash-1\"]", "eval": COUNT},
        {"type": ["[data-k=\"pentext:msg-ash-1\"]", "y" * 305], "eval": "[" + COUNT + ", (document.querySelector('#cnt-msg-ash-1') || {}).textContent]"},
        {"type": ["[data-k=\"pentext:msg-ash-1\"]", "y" * 200], "eval": COUNT}])
    assert "tone-muted" in got["steps"][0]["eval"], got["steps"][0]["eval"]
    assert "tone-warn" in got["steps"][2]["eval"], got["steps"][2]["eval"]
    cls, words = got["steps"][3]["eval"]
    assert "tone-bad" in cls and "5 over the limit" in words, (cls, words)
    assert "tone-muted" in got["steps"][4]["eval"], got["steps"][4]["eval"]


# ------------------------------------------------------------------ the line names what is there

HOLD = "(document.querySelector('[data-k=\"held:msg-kit-1\"]') || {getAttribute: () => ''}).getAttribute('data-hold')"
READ_THEM = "!!document.querySelector('[data-item=\"reading-queue\"] [data-k=\"read-them\"]')"
TAB = IN_APP.replace("{more}", "r.busy = false; r.cur = null; r.needTab = true;")


def test_a_line_saying_press_read_them_has_that_button_on_to_do(run, tmp_path):
    """The maintainer, 2026-11-10: "Waiting for their profile: press Read them in To do once"
    with no Read them card on To do. The line says to press it only while To do shows it:
    with another card in its place (profiles read, waiting for their notes), it waits its turn."""
    m, kit = _model()
    html = _write(tmp_path, "tab", m)
    other = {"actions/act~read-someone~reading.done~1": {
        "item": "read-someone_else", "action": "reading.done", "value": {"text": "A profile."},
        "at": "2026-10-25T08:00:00Z", "rev_seen": "q0", "tab": "t0"}}
    seen = []
    for seed in ({}, other):
        got = run("engine", html=html, viewport={"width": 1280, "height": 900}, clock=CLOCK, seed=seed, steps=[
            {"hash": "contacts", "eval": TAB},
            {"eval": HOLD},
            {"hash": "todo", "eval": READ_THEM}])
        assert not got["errors"], got["errors"]
        seen.append((got["after"][1]["eval"], got["after"][2]["eval"]))
    for hold, button in seen:
        assert hold != "tab" or button, seen
    # Alone, it is the button's line; behind the read profiles' card, never.
    assert seen[0] == ("tab", True), seen
    assert seen[1][0] != "tab", seen


def test_with_their_computer_ready_it_is_read_there_by_itself(run, tmp_path):
    """Their computer is set up and ready (`computer_ready`, computer.reads_there): the note says
    Claude reads it on their computer by itself, on a phone as in the Claude app, and To do's
    card says the same with nothing to press. The engine sends the read there (app.py
    computer_reads)."""
    m, kit = _model(computer=True)
    kit["hold"] = app_model.READ_HOLD["computer"]
    html = _write(tmp_path, "computer", m)
    for vp, first in ((PHONE, []), ({"width": 1280, "height": 900}, [{"hash": "contacts", "eval": TAB}])):
        got = run("engine", html=html, viewport=vp, clock=CLOCK, seed={}, steps=first + [
            {"hash": "contacts", "eval": "[" + HOLD + ", " + LINE + "]"},
            {"hash": "todo", "eval": QUEUE}])
        assert not got["errors"], got["errors"]
        hold, line = got["after"][len(first)]["eval"]
        assert hold == "computer" and line.startswith("Waiting for their profile: Claude reads it on your computer by itself"), (hold, line)
        todo, read_them = got["after"][len(first) + 1]["eval"]
        assert "Claude reads 1 profile on your computer by itself" in todo and "Nothing to press" in todo, todo
        assert not read_them and "I'll paste them instead" not in todo, todo
