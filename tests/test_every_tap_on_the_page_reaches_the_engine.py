"""Every tap on the page is applied by the engine, from the page's own payload.

The other page tests build each action themselves, or fill in the item's rev, so a page that
sent the wrong shape could pass them all. Here nothing is built by hand: the page is made by
`tools/app.py page` from an invented search, a browser taps it as a person would, and the
action documents the page's own act() wrote are handed, exactly as written, to
`tools/app.py apply` over that same search. Each must come back applied, and the search must
show it: the tracker row, the ruling kept with its reason, the setting, the contact book.
Every person and employer is invented (tests/app_state.py).
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_actions  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402
from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy  # noqa: E402
from test_the_page_shows_the_engines_own_data import PHONE, _page, _seed  # noqa: E402
from test_the_page_works_in_a_browser import HARNESS, Runner, _node_env  # noqa: E402

APP_JS = os.path.join(ROOT, "templates", "app", "app.js")

# Actions the page sends that the engine does not apply yet. Each is the engine builder's to
# add (FUNCTIONS_SPEC 4); the test below fails once one of them exists, so the list is kept
# honest and the action then joins the round trip.
ENGINE_TODO: dict = {}


@pytest.fixture(scope="module")
def run():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    env = _node_env()
    probe = subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True)
    if probe.returncode:
        pytest.skip("Playwright for Node is not installed here")
    proc = subprocess.Popen([node, HARNESS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)
    r = Runner(proc)
    hello = r.first()
    if not hello.get("ready"):
        proc.kill()
        pytest.skip("Chromium would not start: " + str(hello.get("error", ""))[:200])
    yield r
    proc.stdin.close()
    proc.wait(timeout=60)


def _env(where):
    env = dict(os.environ, LJS_PROFILE=where.profile, LJS_STATE=where.state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    return env


def _tap(run, tmp, where, name, steps, viewport=PHONE):
    """The page for this search, tapped; the action documents its act() wrote."""
    env = _env(where)
    html = _page(str(tmp), name, env)
    seed = _seed(str(tmp), name, env)
    got = run("engine", html=html, seed=seed, viewport=viewport, steps=steps, fake={"canSend": "available"})
    assert not got["errors"], got["errors"]
    return got


def _hand_over(where, got):
    """The page's actions, exactly as it wrote them, put in the dump a chat applies."""
    ids = []
    for doc in got["actions"]:
        doc = dict(doc)
        aid = "act~" + re.sub(r"[^A-Za-z0-9_.~-]", "_", doc["item"])[:90] + "~" + doc["action"]
        os.makedirs(os.path.join(where.dump, "actions"), exist_ok=True)
        with open(os.path.join(where.dump, "actions", aid + ".json"), "w", encoding="utf-8") as fh:
            json.dump(dict(doc, __version__=1), fh)
        ids.append((aid, doc))
    return ids


def _receipts(where, ids):
    out = {}
    for aid, doc in ids:
        p = os.path.join(where.dump, "out", "files", "receipts", aid + ".json")
        with open(p, encoding="utf-8") as fh:
            out[doc["action"] + " " + doc["item"]] = json.load(fh)
    return out


def _round_trip(run, tmp, where, name, steps, viewport=PHONE):
    got = _tap(run, tmp, where, name, steps, viewport)
    ids = _hand_over(where, got)
    assert ids, "the taps wrote no action"
    where.apply()
    rec = _receipts(where, ids)
    bad = {k: (v.get("result"), v.get("note")) for k, v in rec.items() if v.get("result") != "ok"}
    assert not bad, bad
    return got, rec


def _tracker(state, company):
    with open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["company"] == company]


def _seen(state):
    with open(os.path.join(state, "job_scraper", "seen_jobs.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ what the page can send


def test_every_action_the_page_sends_is_one_the_engine_applies_or_is_named_as_still_to_come():
    with open(APP_JS, encoding="utf-8") as fh:
        js = fh.read()
    sent = set(re.findall(r'action: "([a-z_]+\.[a-z_]+)"', js))
    sent |= {"outcome." + k for k in re.findall(r'heard\("([a-z_]+)"', js)}
    known = set(app_actions.ACTIONS)
    assert not (sent - known - set(ENGINE_TODO)), sent - known - set(ENGINE_TODO)
    assert not (set(ENGINE_TODO) & known), ("the engine has these now: take them off ENGINE_TODO",
                                            set(ENGINE_TODO) & known)
    assert not (sent & set(getattr(app_actions, "ALIASES", {}))), "the page sends the engine's own names, never an alias"


def test_the_page_never_sends_an_action_without_its_items_rev():
    with open(APP_JS, encoding="utf-8") as fh:
        js = fh.read()
    body = js[js.index("async function act(list, label)"):]
    body = body[:body.index("\n  }\n")]
    assert "M().rev" not in body, "a missing rev is never filled in with the model's own"


# ------------------------------------------------------------------ the round trips


def test_marking_a_job_applied_records_the_day_given(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "applied", [
        {"hash": "jobs", "click": "Draft this: Brindle Hart Logistics, Demand Planning Analyst"},
        {"click": "Yes, I have applied", "role": "radio"},
        {"fill": {"When did you apply?": "2026-10-20"}},
        {"click": "Mark as applied"},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "job.applied"]
    assert a["value"] == {"on": "2026-10-20"} and a["rev_seen"]
    (row,) = [r for r in _tracker(where.state, "Brindle Hart Logistics") if r["status"] == "applied"]
    assert row["applied_on"] == "2026-10-20", row


def test_setting_a_job_aside_keeps_the_reason_given(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "aside", [
        {"hash": "jobs", "click": "Not for me: Dovecote Freight, Inventory Analyst"},
        {"click": "The pay", "role": "radio", "exact": True}, {"click": "Take it off my list"},
    ])
    acts = [x for x in got["actions"] if x["action"] == "job.dismiss"]
    assert acts and acts[-1]["value"] == {"why": "pay"}
    seen = json.dumps(_seen(where.state))
    assert "pay" in seen.lower(), "the reason is kept with the ruling"


def test_bringing_back_a_posting_the_search_left_out(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "back", [
        {"hash": "jobs", "click": "left out by the search"},
        {"click": "Bring back", "exact": False},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "job.bring_back"]
    assert a["item"].startswith("r9-f") and a["rev_seen"], a


def test_a_draft_marked_applied_and_a_note_marked_sent(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "sent", [
        {"hash": "drafts", "click": "I have applied: Kestrel Mutual, Claims Forecasting Analyst"},
        {"hash": "drafts-messages", "click": "I sent the note to"},
    ])
    by = {x["action"]: x for x in got["actions"]}
    assert len(by["ready.applied"]["value"]["on"]) == 10, "the day it went"
    assert by["msg.sent"]["value"]["text"] and by["msg.sent"]["value"]["channel"]
    assert any(r["status"] == "applied" for r in _tracker(where.state, "Kestrel Mutual"))


def test_a_setting_changed_on_the_page_is_changed(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "setting", [
        {"hash": "settings", "open": "set-sum:tips", "click": "Off", "role": "radio", "exact": True, "wait": 900},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "setting.set"]
    assert a["item"] == "setting-tips" and a["rev_seen"], a
    m = where.model()
    assert next(s for s in m["settings"] if s["key"] == "tips")["value"] == "off"


def test_a_person_put_in_the_bin_is_never_messaged_again(run, tmp_path):
    # The bin on a person's row (the maintainer, 2026-10-29: "i dont wanna message ade"): one
    # choice in its own sheet, applied by the engine, and the person shows as stopped.
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "bin", [
        # Wren owes nothing today, so is one tap below the people who do.
        {"hash": "contacts", "click": "more people, nothing owed to them now", "exact": False},
        {"click": "Not Wren?", "exact": True},
        {"click": "Don't contact Wren", "role": "radio", "exact": True},
        {"submit": True},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "person.stop"]
    assert a["item"] == "fernhill_freight_halloway" and a["rev_seen"] and a["value"]["why"], a
    wren = next(p for p in where.model()["people"] if p["id"] == "fernhill_freight_halloway")
    assert wren["status"] in ("stopped", "closed"), wren["status"]


def test_the_bin_on_a_to_do_row_turns_the_employer_down_in_the_engine(run, tmp_path):
    # The bin on a To do row (the maintainer, 2026-10-29: "it didnt go away"): the employer
    # choice is applied by the engine as well as taken off the page.
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "todobin", [
        {"hash": "todo", "click": "Not Wren?", "exact": False},
        {"click": "Not interested in Fernhill Freight any more", "role": "radio", "exact": True},
        {"submit": True},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "person.stop"]
    assert a["value"]["scope"] == "employer" and a["value"]["employer"] == "Fernhill Freight", a
    wren = next(p for p in where.model()["people"] if p["id"] == "fernhill_freight_halloway")
    assert wren["status"] in ("stopped", "closed"), wren["status"]


def test_a_suggestion_declined_is_not_offered_again(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "nothanks", [
        {"hash": "jobs", "click": "No thanks", "exact": False},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "suggest.dismiss"]
    assert a["rev_seen"] and isinstance(a["value"], dict), a


def test_a_question_answered_on_to_do(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    got, rec = _round_trip(run, tmp_path, where, "answer", [
        {"hash": "todo", "click": "Not yet", "exact": False},
    ])
    assert got["actions"] and all(x["rev_seen"] for x in got["actions"])


def test_a_pasted_resume_reaches_the_setup_as_the_resume_never_as_an_answer(run, tmp_path):
    where = Copy(str(tmp_path / "c"))
    got, rec = _round_trip(run, tmp_path, where, "resume", [
        {"hash": "todo", "click": "Start"},
        {"click": "Paste it", "fill": {"Paste your resume here": "Analyst at Brindle Hart Logistics, 2021 to now."}},
        {"click": "Save it"},
    ])
    (a,) = got["actions"]
    assert a["action"] == "setup.resume" and a["value"] == {"text": "Analyst at Brindle Hart Logistics, 2021 to now."}
    steps = {s["step"]: s for s in where.model()["setup"]["steps"]}
    assert steps["resume"]["status"] == "done"


def test_a_setup_answer_is_the_steps_own_fields_flat(run, tmp_path):
    where = Copy(str(tmp_path / "c"))
    # The second question, answered on its own: the step's fields, flat, as the engine reads them.
    got = _tap(run, tmp_path, where, "answer", [
        {"hash": "todo", "click": "Start"},
        {"click": "Paste it", "fill": {"Paste your resume here": "Analyst."}},
        {"click": "Save it"},
        {"fill": {"The work you want next": "Demand planning", "Where you'd like to work": "Leeds"}},
        {"click": "Continue"},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "setup.answer"]
    assert a["value"] == {"work": "Demand planning", "place": "Leeds"}, "the step's own fields, flat"
    only = dict(got, actions=[a])
    ids = _hand_over(where, only)
    where.apply()
    rec = _receipts(where, ids)
    assert rec["setup.answer setup-work"]["result"] == "ok", rec
    steps = {s["step"]: s for s in where.model()["setup"]["steps"]}
    assert steps["work"]["status"] == "done"


def test_two_setup_answers_in_a_row_are_both_applied(run, tmp_path):
    where = Copy(str(tmp_path / "c"))
    _round_trip(run, tmp_path, where, "setup", [
        {"hash": "todo", "click": "Start"},
        {"click": "Paste it", "fill": {"Paste your resume here": "Analyst at Brindle Hart Logistics, 2021 to now."}},
        {"click": "Save it"},
        {"fill": {"The work you want next": "Demand planning", "Where you'd like to work": "Leeds"}},
        {"click": "Continue"},
    ])
