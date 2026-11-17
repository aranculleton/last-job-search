"""The chats the app makes are named "Last Job Search · <what it is for>", short and plain.

Issue #289: the app's chats in the person's list had long, mixed names that were cut off and
did not say how they related ("Job search: morning brief", "Job search page", "Job search:
on your computer", "Job search · Reading 8 profiles on your computer · Mac"). Now each starts
with the app's name, then one plain word or two anyone understands: "Brief" and "Your
computer" are kept for good, "Page" is replaced by a fresh one, and a one-off job's chat
says its task and its day. No computer's name (the same name on a Mac, Windows or Linux), no
invented shorthand. The app's own lookups know the old names and the new, and the chats an
existing install already has under an old name are renamed by the daily tidy-up, once.
Every id, title, employer and page here is invented.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app  # noqa: E402
import app_listen  # noqa: E402
import app_setup  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402
from test_a_finished_chat_closes_at_once_and_one_page_helper_stays import (  # noqa: E402
    LIVE, PAGE, REPO, _chat, copy)

assert copy  # the fixture, imported

APP = "Last Job Search · "
NOW = dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc)
BRIEF_CHAT = "session_EXAMPLEBRIEFCHAT"
COMPUTER_CHAT = "session_EXAMPLECOMPUTERCHAT"
RUNS_CHAT = "session_EXAMPLESCHEDULEDRUNS"


def _job_call(monkeypatch, title: str, question: bool = False) -> str:
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    got = app.where_it_runs({"heavy": True, "kind": "search", "title": title,
                             "work": "work/search~example"}, LIVE, "cloud", question=question,
                            now=NOW)
    return got["create_session"]["title"]


def test_every_chat_the_app_makes_starts_with_its_name_then_what_it_is_for(monkeypatch):
    names = {
        "brief": routines.brief_chat_call("example-owner/example-copy")["title"],
        "page": app_listen.helper_call({}, "example-owner", "example-copy")["title"],
        "computer": computer.LISTENER_TITLE,
        "job": _job_call(monkeypatch, "People search"),
        "question": _job_call(monkeypatch, "Is my letter ok?", question=True),
        "computer job": computer.session_title("People at Harbourline Bank", "Studio Laptop"),
        "unsaved": app.UNSAVED_TITLE.format(day="16 Nov"),
    }
    assert names["brief"] == APP + "Brief"
    assert names["page"] == APP + "Page"
    assert names["computer"] == APP + "Your computer"
    assert names["job"] == APP + "People search, 16 Nov"
    assert names["question"] == APP + "Chat questions, 16 Nov"
    assert names["computer job"] == APP + "People at Harbourline Bank"
    assert names["unsaved"] == APP + "Changes to save, 16 Nov"
    for what, name in names.items():
        # Short enough not to be cut off, never a computer's own name or an invented shorthand.
        assert name.startswith(APP) and len(name) <= 45, (what, name)
        assert not re.search(r"\b(?:Mac|Windows|Linux|Studio Laptop|Mac link|Job)\b",
                             name[len(APP):]), (what, name)
    # Two job chats at work under one name still get (2), after the day.
    two = app.distinct_title(names["job"], {names["job"]})
    assert two == APP + "People search, 16 Nov (2)" and tidy.APP_TITLE.match(two)


def test_the_apps_lookups_know_the_old_names_and_the_new():
    page, old_page = APP + "Page", "Job search page"
    for name in (page, page + " (finishing up)", old_page, "Job search helper"):
        assert tidy.HELPER_NAME.match(name) and tidy.APP_TITLE.match(name), name
    for name in (APP + "People search, 16 Nov", APP + "Brief", APP + "Your computer",
                 "Holiday plans", "Last Job Search notes"):
        assert not tidy.HELPER_NAME.match(name), name
    for name in (APP + "Your computer", "Job search: on your computer"):
        assert tidy.LISTENER_NAME.match(name), name
    assert not tidy.LISTENER_NAME.match(APP + "People search, 16 Nov")
    for name in (APP + "Brief", "Job search: morning brief", "⚡ Job search: morning brief"):
        assert routines._BRIEF_TITLE.match(name), name
    assert not routines._BRIEF_TITLE.match(APP + "Page")
    assert not routines._BRIEF_TITLE.match(APP + "Brief notes for Larkspur, 16 Nov")
    for name in (APP + "People search, 16 Nov", APP + "Chat questions, 16 Nov (2)",
                 APP + "Changes to save, 16 Nov", "⚡ " + APP + "Scheduled run",
                 "Job search: Interview prep: Larkspur Retail, Data Analyst"):
        assert tidy.APP_TITLE.match(name), name
    assert not tidy.APP_TITLE.match("Last Job Search notes")
    # A Chat question claimed for the Chat's own chat, under either name.
    for name in (APP + "Chat questions, 16 Nov", APP + "Chat questions, 16 Nov (2)",
                 "Job search: Chat", "Job search: Chat (2)"):
        assert page_db.in_question_chat({"chat_title": name}), name
    assert not page_db.in_question_chat({"chat_title": APP + "People search, 16 Nov"})


def test_the_computer_puts_away_its_finished_job_chats_by_either_name_never_its_own_chat():
    old = NOW - dt.timedelta(hours=5)
    listing = [{"title": t, "id": f"local-{i}", "status": "idle", "updated_at": old.isoformat()}
               for i, t in enumerate((APP + "People at Harbourline Bank",
                                      "Job search · Find 10 people at Larkspur · Studio Laptop",
                                      APP + "Your computer", "Job search: on your computer",
                                      "Holiday plans"))]
    got = [r["title"] for r in computer.archivable(listing, True, now=NOW,
                                                   keep=(computer.LISTENER_TITLE,))]
    assert got == [APP + "People at Harbourline Bank",
                   "Job search · Find 10 people at Larkspur · Studio Laptop"], got


def _plan(copy, tmp_path, monkeypatch, chats, renamed_before=None):
    """The daily tidy-up's plan, run as the chat that answers the page runs it."""
    monkeypatch.setattr(tidy, "_listener", lambda dump: {
        "chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-16T08:10:00Z"})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda *_: set())
    monkeypatch.setattr(tidy, "on_github", lambda: {"master"})
    monkeypatch.setattr(tidy, "_computer_chat", lambda db: COMPUTER_CHAT)
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEBRIEF",
         "cron": "CRON_TZ=Europe/London 0 8 * * *", "prompt_file": routines.BRIEF_FILE,
         "copy": True, "chat": {"session_id": BRIEF_CHAT, "own": True}}]}
    # By its name in sys.modules: another test file may have loaded routines afresh.
    monkeypatch.setattr("routines.load", lambda p=None: reg)
    triggers = [{"id": "trig_EXAMPLEBRIEF", "name": routines.BRIEF_NAME, "enabled": True,
                 "persistent_session_id": BRIEF_CHAT, "cron_expression": reg["routines"][0]["cron"],
                 "prompt": routines.with_copy(routines.stub(reg, "morning_brief", own_chat=True),
                                              REPO)},
                {"id": "trig_EXAMPLERUNS", "name": "Job search: a check-in", "enabled": True,
                 "persistent_session_id": RUNS_CHAT, "cron_expression": "0 9 * * 1",
                 "prompt": "A weekly check-in."}]
    if renamed_before:
        with open(os.path.join(copy.profile, "tidy.json"), "w", encoding="utf-8") as fh:
            json.dump({"archived": [], "renamed": renamed_before}, fh)
    stdin = json.dumps({"sessions": {"data": chats}, "triggers": {"triggers": triggers}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert tidy.main(["plan", "--stdin", "--chat", LIVE, "--now", NOW.isoformat()]) == 0
    return buf.getvalue()


def test_an_existing_installs_chats_take_the_new_names_once(copy, tmp_path, monkeypatch):
    """The brief's chat, the computer's own chat and the scheduled runs' chat an install made
    before this version keep their old names unless the app renames them: the daily tidy-up
    does, once each, asking nobody and saying nothing. The page's helper renames itself at
    its next check-in (below). A chat of the person's own is never touched."""
    chats = [_chat(LIVE, "Job search page"),
             _chat(BRIEF_CHAT, "Job search: morning brief"),
             _chat(COMPUTER_CHAT, "Job search: on your computer"),
             _chat(RUNS_CHAT, "Job search: scheduled runs"),
             _chat("session_EXAMPLEMINE", "Holiday plans")]
    out = _plan(copy, tmp_path, monkeypatch, chats)
    renames = {ln.split(":", 1)[0].split()[1]: ln for ln in out.splitlines()
               if ln.startswith("rename ")}
    assert set(renames) == {BRIEF_CHAT, COMPUTER_CHAT, RUNS_CHAT}, out
    assert json.dumps({"session_id": BRIEF_CHAT, "title": APP + "Brief"},
                      ensure_ascii=False) in renames[BRIEF_CHAT]
    assert json.dumps({"session_id": COMPUTER_CHAT, "title": APP + "Your computer"},
                      ensure_ascii=False) in renames[COMPUTER_CHAT]
    assert json.dumps({"session_id": RUNS_CHAT, "title": APP + "Scheduled runs"},
                      ensure_ascii=False) in renames[RUNS_CHAT]
    assert all("set_session_title" in ln for ln in renames.values())
    assert any("say nothing" in ln for ln in out.splitlines() if ln.startswith("rename"))
    assert "nothing to tidy" not in out and "archive_session" not in out, out
    # Once: recorded when the plan's calls are done (made or refused), it is never asked for
    # again, and a chat under its new name is left alone.
    with contextlib.redirect_stdout(io.StringIO()):
        assert tidy.main(["done", "--today", "2026-11-16"]) == 0
    assert set(tidy.renamed()) == {BRIEF_CHAT, COMPUTER_CHAT, RUNS_CHAT}
    out = _plan(copy, tmp_path, monkeypatch, chats)
    assert not [ln for ln in out.splitlines() if ln.startswith("rename ")], out
    chats = [_chat(LIVE, APP + "Page"), _chat(BRIEF_CHAT, APP + "Brief"),
             _chat(COMPUTER_CHAT, APP + "Your computer")]
    out = _plan(copy, tmp_path, monkeypatch, chats, renamed_before={})
    assert not [ln for ln in out.splitlines() if ln.startswith("rename ")], out


def test_the_live_helper_under_an_old_name_takes_the_new_one_once(copy, monkeypatch):
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    for old in ("Job search page", "Job search helper"):
        rec = {"chat": LIVE, "title": old, "kind": "cloud", "helper": True,
               "since": "2026-11-16T08:00:00Z", "answered_at": "2026-11-16T09:30:00Z"}
        db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {}}
        got = app_listen.decide(db, LIVE, str(copy.root) + "/" + old.split()[-1], NOW)
        rename = f'set_session_title (session_id {LIVE}, title "{APP}Page")'
        assert any(rename in ln for ln in got["lines"]), got["lines"]
        assert got["record"]["title"] == APP + "Page"
