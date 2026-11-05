"""A finished chat closes at once, a finished chat never comes back, and one page helper stays.

The maintainer, 2026-11-04. A job's chat (an interview prep, a search, drafts) sat in the
sidebar for up to a day after its work was done, and nobody could tell whether it was still
working: it now tells the chat that started it (send_message), which puts the results on the
page and archives it at once. On 3 November the tidy-up archived "Job search: Interview prep:
<Employer>, <Role>" but recorded it with an empty title, and the next tidy-up took it for a
chat of the person's own and brought it back. And a heavy user's renewals stacked up several
identical "Job search helper" chats: there is only ever the live page helper ("Job search
page") beside the person's own chat. Every id, title, employer and page here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import app_listen  # noqa: E402
import app_setup  # noqa: E402
import page_db  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402
from test_one_chat_answers_the_page import Copy  # noqa: E402

PAGE = "https://claude.ai/code/artifact/example-page"
REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 5)
NOW = dt.datetime(2026, 11, 5, 9, 0, tzinfo=dt.timezone.utc)
LIVE = "session_EXAMPLEPAGEHELPER"
PREP = "session_EXAMPLEPREPCHAT"
PREP_TITLE = "Job search: Interview prep: Larkspur Retail, Data Analyst"


@pytest.fixture
def copy(tmp_path, monkeypatch):
    c = Copy(tmp_path)
    for k, v in c.env().items():
        monkeypatch.setenv(k, v)
    git = tmp_path / "git"
    git.mkdir()
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(git))
    yield c
    sys.path.remove(c.root)


def _chat(sid, title, updated="2026-11-05T08:50:00Z", status="SESSION_STATUS_IDLE"):
    return {"id": sid, "title": title, "session_status": status,
            "status_bucket": "SESSION_STATUS_BUCKET_REVIEW_READY",
            "created_at": "2026-11-01T08:00:00Z", "updated_at": updated}


def _detail(sid, title="", repo=REPO, branch=""):
    return {"id": sid, "title": title, "session_context": {
        "sources": [{"git_repository": {"url": f"https://github.com/{repo}"}}],
        "outcomes": [{"git_repository": {"git_info": {"repo": repo,
                                                      "branches": [branch] if branch else []}}}]}}


def _record(copy):
    with open(os.path.join(copy.profile, "tidy.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _write_record(copy, rows):
    with open(os.path.join(copy.profile, "tidy.json"), "w", encoding="utf-8") as fh:
        json.dump({"archived": rows}, fh)


def _json(tmp_path, name, value):
    p = tmp_path / name
    p.write_text(json.dumps(value), encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ note 7: a job's chat reports back


def test_a_jobs_chat_reports_back_to_the_chat_that_started_it(monkeypatch):
    """The job's chat, once its work is landed, sends one message to the chat that started it,
    whose id is in its prompt: it never sits waiting for tomorrow's tidy-up."""
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    chosen = {"work": "prep~1", "kind": "prep", "title": "Interview prep: Larkspur Retail, Data Analyst",
              "heavy": True, "stages": page_db.progress("prep")["stages"]}
    got = app.where_it_runs(chosen, LIVE, "cloud")
    said = " ".join(got["create_session"]["prompt"].split())
    assert f"send_message, session_id {LIVE}" in said
    assert "[app] Finished prep~1, on master, in chat <your own id>:" in said
    assert "your own id is get_session with no session_id" in said
    # Landed first, then the message, and the page brought up to date here only where the
    # message cannot go (the chat that started it was replaced and archived).
    assert said.index("land your work on master") < said.index("send_message, session_id")
    assert said.index("send_message, session_id") < said.index("Only where send_message is not there")
    assert said.index("Only where send_message is not there") < said.index("tools/app.py view")
    assert "first" not in got
    # The chat that started it reads the message back by the app's own pattern.
    m = app.REPORTED.search("[app] Finished prep~1, on master, in chat session_EXAMPLEJOB: a pack")
    assert m and m.groups() == ("prep~1", "on master", "session_EXAMPLEJOB")
    # Its own id unknown here: the call says to put it in first, from get_session.
    blind = app.where_it_runs(chosen, "", "cloud")
    assert app.PARENT in blind["create_session"]["prompt"]
    assert "get_session with no session_id" in blind["first"]
    # A background agent has no chat to message: it ends with its line, as before.
    agent = app.where_it_runs(chosen, LIVE, "computer")["agent"]["prompt"]
    assert "send_message" not in agent and "Finished prep~1, on master: bring the page" in agent


def test_the_chat_that_started_it_closes_it_only_when_it_is_done_and_on_master(copy, tmp_path,
                                                                              monkeypatch):
    """`tidy.py close` names the archive only for one of the app's own job chats on this copy
    whose job has ended and whose work is on master, with the title it has now; `closed`
    records it without counting as the day's tidy-up."""
    db = {"work": {"prep~1": {"data": {"kind": "prep", "status": "done"}, "version": 3}}}
    listener = {"chat": LIVE, "kind": "cloud", "helper": True}
    det = {PREP: _detail(PREP, PREP_TITLE)}
    ok = tidy.close(PREP, "prep~1", db, det, listener, LIVE, REPO, set())
    assert ok == ("archive", PREP_TITLE)
    going = {"work": {"prep~1": {"data": {"kind": "prep", "status": "running"}, "version": 3}}}
    assert tidy.close(PREP, "prep~1", going, det, listener, LIVE, REPO, set())[0] == "keep"
    branch = {PREP: _detail(PREP, PREP_TITLE, branch="claude/prep-x1")}
    assert "not on master" in tidy.close(PREP, "prep~1", db, branch, listener, LIVE, REPO,
                                         {"claude/prep-x1"})[1]
    theirs = {PREP: _detail(PREP, "My notes for Larkspur")}
    assert tidy.close(PREP, "prep~1", db, theirs, listener, LIVE, REPO, set())[0] == "keep"
    other = {PREP: _detail(PREP, PREP_TITLE, repo="example-owner/another-copy")}
    assert tidy.close(PREP, "prep~1", db, other, listener, LIVE, REPO, set())[0] == "keep"
    assert tidy.close(LIVE, "prep~1", db, {LIVE: _detail(LIVE, "Job search page")}, listener,
                      LIVE, REPO, set())[0] == "keep"
    assert tidy.close(PREP, "prep~1", db, {}, listener, LIVE, REPO, set())[0] == "keep"

    # The commands, as the chat that answers the page runs them.
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    # ArtifactData spells the id's "~" as "@" in the file's name (page_db.load).
    name = "prep~1".replace("~", "@") + ".json"
    (dump / "work" / name).write_text(json.dumps(db["work"]["prep~1"]), encoding="utf-8")
    monkeypatch.setattr(tidy, "_listener", lambda d: listener)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    tidy._mark_checked("2026-11-05", "2026-11-05T08:00:00Z")
    args = ["close", PREP, "--work", "prep~1", "--dump", str(dump), "--chat", LIVE,
            "--details", _json(tmp_path, "d.json", det[PREP])]
    out = _tidy(args)
    assert f'archive_session {{"session_id": "{PREP}"}}' in out
    assert f"python3 tools/tidy.py closed {PREP}" in out
    assert _tidy(["closed", PREP, "--today", "2026-11-05"])
    assert _record(copy)["archived"] == [{"id": PREP, "title": PREP_TITLE, "on": "2026-11-05"}]
    assert tidy._planned() == {}


def _tidy(argv):
    """tidy.main in this process, its output returned (the monkeypatches hold)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert tidy.main(argv) == 0
    return buf.getvalue()


def test_two_job_chats_at_work_never_share_a_name(monkeypatch, tmp_path):
    """A job chat started beside another still at work under the same name gets (2): no two
    of the person's chats are called the same. The name is kept on the work item's claim."""
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    now = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)
    title = "Interview prep: Larkspur Retail, Data Analyst"   # a second round asked for
    db = {"work": {
        "prep~a": {"data": {"kind": "prep", "status": "running", "title": title,
                              "chat_title": f"Job search: {title}", "claimed_by": LIVE,
                              "claimed_at": "2026-11-05T11:55:00Z",
                              "lease_until": "2026-11-05T12:25:00Z"}, "version": 2},
        "prep~b": {"data": {"kind": "prep", "status": "queued", "to": "cloud", "title": title,
                              "asked_at": "2026-11-05T11:58:00Z", "args": {}}, "version": 1}}}
    got = app.choose(db, LIVE, "cloud", now, claim_out=str(tmp_path / "claim"))
    assert got["work"] == "prep~b"
    named = got["create_session"]["title"]
    assert named == f"Job search: {title} (2)" and tidy.APP_TITLE.match(named)
    files = [os.path.join(d, f) for d, _, fs in os.walk(tmp_path / "claim") for f in fs]
    written = [json.load(open(f, encoding="utf-8")) for f in files if "prep@b" in f]
    assert written and written[0]["chat_title"] == f"Job search: {title} (2)", written
    assert app.distinct_title("Job search: x", {"Job search: x", "Job search: x (2)"}) == \
        "Job search: x (3)"
    long = "Job search: " + "An analyst role at Kestrel Mutual " * 3
    assert tidy.APP_TITLE.match(app.distinct_title(long[:72], {long[:72]}))


# ------------------------------------------------------------------ note 8: never brought back


def test_a_finished_chat_recorded_with_no_title_is_never_brought_back(copy, tmp_path):
    """The real path of 3 November: an interview prep's chat archived with an empty stored
    title. Its live title is the app's, so it is never taken for the person's own; an empty
    title alone is never evidence. A chat of the person's own put away before still comes
    back once (X-4)."""
    _write_record(copy, [
        {"id": PREP, "title": "", "on": "2026-11-03"},
        {"id": "session_EXAMPLEGONE", "title": "", "on": "2026-11-03"},
        {"id": "session_PERSONSOWN", "title": "Find me a data job in Leeds", "on": "2026-11-01"}])
    listed = _json(tmp_path, "s.json", {"data": [_chat(PREP, PREP_TITLE, status="SESSION_STATUS_ARCHIVED")]})
    run = lambda: subprocess.run(  # noqa: E731
        [sys.executable, os.path.join(ROOT, "tools", "tidy.py"), "plan", "--sessions", listed,
         "--dump", str(tmp_path / "nodump")], env=copy.env(), capture_output=True, text=True,
        encoding="utf-8", timeout=60).stdout
    said = run()
    assert f'unarchive_session {{"session_id": "{PREP}"}}' not in said, said
    assert "session_EXAMPLEGONE" not in said
    assert 'unarchive_session {"session_id": "session_PERSONSOWN"}' in said
    assert "unarchive_session" not in run()                      # once


def _plan_here(copy, tmp_path, monkeypatch, chats, details, listener=None):
    monkeypatch.setattr(tidy, "_listener", lambda d: listener or {"chat": LIVE, "kind": "cloud",
                                                                  "helper": True})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(routines, "load", lambda *a, **k: {})
    args = ["plan", "--chat", LIVE, "--today", TODAY.isoformat(),
            "--sessions", _json(tmp_path, "s.json", {"data": chats})]
    for i, d in enumerate(details):
        args += ["--details", _json(tmp_path, f"d{i}.json", d)]
    return _tidy(args)


def test_the_tidy_up_keeps_each_real_title_itself(copy, tmp_path, monkeypatch):
    """`plan` keeps the titles of what it names, so `done` records each from the ids alone:
    a title copied back through the shell was lost (an apostrophe in an employer's name ends
    the quoting, and a JSON it cannot read was dropped without a word)."""
    title = "Job search: Interview prep: O'Hara & Byrne, Data Analyst"
    sid = "session_EXAMPLEOLDPREP"
    out = _plan_here(copy, tmp_path, monkeypatch, [_chat(sid, title, updated="2026-10-30T08:00:00Z")],
                     [_detail(sid, title)])
    assert f"archive {sid}: {title}" in out
    assert "--titles" not in out and f"tidy.py done <each one archived> (all of them: {sid})" in out
    _tidy(["done", sid, "--today", TODAY.isoformat()])
    assert _record(copy)["archived"] == [{"id": sid, "title": title, "on": TODAY.isoformat()}]


def test_an_app_chat_brought_back_by_mistake_is_put_away_again(copy, tmp_path, monkeypatch):
    """A copy the 3 November tidy-up already did it to: the chat it brought back (restored,
    no stored title) is judged afresh like any other of the app's chats, put away again once
    finished, and its entry gets its title."""
    _write_record(copy, [{"id": PREP, "title": "", "on": "2026-11-03", "restored": True}])
    out = _plan_here(copy, tmp_path, monkeypatch, [_chat(PREP, PREP_TITLE, updated="2026-11-03T10:00:00Z")],
                     [_detail(PREP, PREP_TITLE)])
    assert f"archive {PREP}: {PREP_TITLE}" in out, out
    _tidy(["done", PREP, "--today", TODAY.isoformat()])
    assert _record(copy)["archived"] == [{"id": PREP, "title": PREP_TITLE, "on": TODAY.isoformat()}]
    # Recorded again, it is never brought back, and never judged again.
    again = _plan_here(copy, tmp_path, monkeypatch, [_chat(PREP, PREP_TITLE)], [_detail(PREP, PREP_TITLE)])
    assert "unarchive_session" not in again and f"archive {PREP}" not in again


# ------------------------------------------------------------------ note 9: one page helper


REG = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": "trig_EXAMPLEBRIEF",
     "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
     "chat": {"session_id": "session_EXAMPLEOLDA"}}]}


def _helpers_plan(**kw):
    chats = [
        _chat(LIVE, "Job search page"),                                # the live page helper
        _chat("session_EXAMPLEOLDA", "Job search helper"),             # holds the brief
        _chat("session_EXAMPLEOLDB", "Job search helper"),             # used minutes ago
        _chat("session_EXAMPLEOLDC", "Job search helper"),             # work not on master
        _chat("session_EXAMPLEOLDD", "Job search page (finishing up)"),
        _chat("session_PERSONSOWN", "Look after my job search"),       # the person's own
        _chat("session_PERSONSTOOK", "Job search helper"),             # theirs, it says so
    ]
    info = {c["id"]: _detail(c["id"], c["title"]) for c in chats}
    info["session_EXAMPLEOLDC"] = _detail("session_EXAMPLEOLDC", "Job search helper",
                                          branch="claude/helper-unsaved")
    args = dict(chats=chats, triggers=[{"id": "trig_EXAMPLEBRIEF", "session": "session_EXAMPLEOLDA",
                                        "enabled": True}],
                info=info, reg=REG, listener={"chat": LIVE, "took_from": "session_PERSONSTOOK",
                                              "took_from_helper": False},
                this_chat=LIVE, repo=REPO, today=TODAY, campaigns=set(),
                branches={"claude/helper-unsaved"}, done_before=set())
    args.update(kw)
    return tidy.plan(**args)


def test_the_helpers_left_over_are_put_away_the_brief_moved_first():
    """Several old helpers from before: each is put away once its work is on master, never
    kept for being used lately; the one holding the brief only after the brief is made in the
    live helper, recorded and the old one turned off. The person's own chats and the live
    helper are never touched."""
    got = _helpers_plan()
    assert got["ask"] == []
    gone = {c["id"]: c["why"] for c in got["archive"]}
    assert set(gone) == {"session_EXAMPLEOLDA", "session_EXAMPLEOLDB", "session_EXAMPLEOLDD"}
    assert gone["session_EXAMPLEOLDA"] == "the brief moved into the chat that answers the page"
    kept = {c["id"]: c["why"] for c in got["keep"]}
    assert "not on master" in kept["session_EXAMPLEOLDC"]
    assert kept[LIVE] == "it answers the page"
    assert "session_PERSONSOWN" not in gone and "session_PERSONSTOOK" not in gone
    calls = got["brief"]
    assert calls[0]["tool"] == "create_trigger" and calls[0]["args"]["persistent_session_id"] == LIVE
    assert "routines.py record" in calls[1]["run"]
    assert calls[2] == {"tool": "update_trigger", "args": {"trigger_id": "trig_EXAMPLEBRIEF",
                                                           "enabled": False},
                        "why": "the old task is turned off, never deleted"}
    # Once landed, the one with unsaved work goes too.
    later = _helpers_plan(branches=set())
    assert "session_EXAMPLEOLDC" in {c["id"] for c in later["archive"]}
    # A helper its renewal started since the live one took the page may yet take it: kept.
    fresh = dict(_chat("session_EXAMPLEFRESH", "Job search page"), created_at="2026-11-05T08:58:00Z")
    chats = [_chat(LIVE, "Job search page"), fresh,
             dict(_chat("session_EXAMPLEOLDB", "Job search helper"), created_at="2026-11-05T07:00:00Z")]
    rec = {"chat": LIVE, "since": "2026-11-05T08:30:00Z", "took_from": "session_PERSONSTOOK",
           "took_from_helper": False}
    got = tidy.plan(chats, [], {c["id"]: _detail(c["id"], c["title"]) for c in chats}, {}, rec,
                    LIVE, REPO, TODAY, set(), set(), set())
    assert [c["id"] for c in got["archive"]] == ["session_EXAMPLEOLDB"]
    assert "may yet take it" in {c["id"]: c["why"] for c in got["keep"]}["session_EXAMPLEFRESH"]
    # A brief turned off on an old helper is not moved, so its chat is kept for it.
    off = _helpers_plan(triggers=[{"id": "trig_EXAMPLEBRIEF", "session": "session_EXAMPLEOLDA",
                                   "enabled": False}])
    assert "session_EXAMPLEOLDA" not in {c["id"] for c in off["archive"]} and off["brief"] == []


def test_a_hand_over_puts_the_helper_it_replaced_away_now(copy, tmp_path, monkeypatch):
    """The helper a new one took over from is put away at the new one's first check-in, not
    two quiet days on; while it still runs, the tidy-up is asked for again half an hour later,
    for a day."""
    old = "session_EXAMPLEOLDHELPER"
    rec = {"chat": LIVE, "since": "2026-11-05T08:55:00Z", "took_from": old, "took_from_helper": True}
    assert tidy.retiring(rec, NOW) == old
    assert tidy.retiring(dict(rec, took_from_helper=False), NOW) == ""
    assert tidy.retiring(rec, NOW + dt.timedelta(days=2)) == ""
    tidy._mark_checked("2026-11-05", "2026-11-05T09:00:00Z")
    assert tidy.due("2026-11-05", db={"work": {}}, listener=rec, now=NOW) is False
    assert tidy.due("2026-11-05", db={"work": {}}, listener=rec,
                    now=NOW + dt.timedelta(minutes=31)) is True
    chats = [_chat(LIVE, "Job search page"), _chat(old, "Job search page (finishing up)")]
    det = {c["id"]: _detail(c["id"], c["title"]) for c in chats}
    got = tidy.plan(chats, [], det, {}, rec, LIVE, REPO, TODAY, set(), set(), set())
    assert [c["id"] for c in got["archive"]] == [old]
    chats[1]["session_status"] = "SESSION_STATUS_RUNNING"
    got = tidy.plan(chats, [], det, {}, rec, LIVE, REPO, TODAY, set(), set(), set())
    assert got["archive"] == [] and {"id": old, "title": chats[1]["title"],
                                     "why": "it is running"} in got["keep"]
    _write_record(copy, [{"id": old, "title": "Job search page (finishing up)", "on": "2026-11-05"}])
    assert tidy.retiring(rec, NOW) == ""


def test_the_first_tidy_up_after_the_update_runs_even_if_one_ran_today(copy):
    """The helpers left over from before are swept by the first tidy-up after the update,
    even where the day's had already run under the older version."""
    path = tidy._checked_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"checked": "2026-11-05", "at": "2026-11-05T07:00:00Z"}, fh)
    assert tidy.due("2026-11-05") is True
    tidy._mark_checked("2026-11-05", "2026-11-05T09:00:00Z")
    assert tidy.due("2026-11-05") is False


def test_the_live_helper_is_called_job_search_page_and_takes_the_name_once(copy, monkeypatch):
    """The live helper is "Job search page", a name no other chat has; one from before, still
    "Job search helper", takes it at its next check-in, once. The tidy-up knows both names."""
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    assert app_listen.HELPER_CHAT_TITLE == "Job search page"
    rec = {"chat": LIVE, "title": "Job search helper", "kind": "cloud", "helper": True,
           "since": "2026-11-05T08:00:00Z", "answered_at": "2026-11-05T08:30:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {}}
    got = app_listen.decide(db, LIVE, str(copy.root) + "/a", NOW)
    rename = f'set_session_title (session_id {LIVE}, title "Job search page")'
    assert any(rename in ln for ln in got["lines"]), got["lines"]
    assert got["record"]["title"] == "Job search page"
    db2 = {"meta": {"listener": {"data": got["record"], "version": 4}}, "work": {}}
    assert not any("set_session_title" in ln for ln in app_listen.decide(db2, LIVE, str(copy.root) + "/b", NOW)["lines"])
    # The person's own chat answering the page keeps its own name.
    own = dict(rec, helper=False, title="Job search")
    db3 = {"meta": {"listener": {"data": own, "version": 3}}, "work": {}}
    assert not any("set_session_title" in ln for ln in app_listen.decide(db3, LIVE, str(copy.root) + "/c", NOW)["lines"])
    for name in ("Job search page", "Job search page (finishing up)", "Job search helper",
                 "Job search helper (finishing up)"):
        assert tidy.APP_TITLE.match(name) and tidy.HELPER_NAME.match(name), name
    assert not tidy.HELPER_NAME.match("Job search: Interview prep: Larkspur Retail, Data Analyst")


# ------------------------------------------- the maintainer's live run, 5 November (4.10.1)

OWN = "session_EXAMPLEPERSONSCHAT"
OLD = "session_EXAMPLEOLDHELPER"
OPS_REG = {"setup": "ops_relay", "timezone": "Europe/London",
           "ops_session": {"id": "session_EXAMPLEOPSCHAT"},
           "routines": [{"key": "morning_brief", "name": "Job search: morning brief",
                         "trigger_id": "trig_EXAMPLELEFTBRIEF",
                         "cron": "CRON_TZ=Europe/London 56 7 * * *",
                         "prompt_file": routines.BRIEF_FILE}]}


def _live_run(this_chat, now=dt.datetime(2026, 11, 5, 9, 30, tzinfo=dt.timezone.utc)):
    """The sidebar that morning: the person's own chat called "Job search helper" like the
    helpers, the helper a hand-over replaced still running the brief (remade there after the
    hand-over, the registry naming no chat for it), and the live helper."""
    seed = {"origin": "claude_code_mcp_seed"}
    chats = [dict(_chat(OWN, "Job search helper", updated="2026-11-05T08:20:00Z"),
                  origin="desktop_app"),
             dict(_chat(OLD, "Job search helper (finishing up)", updated="2026-11-05T08:44:00Z"),
                  **seed),
             dict(_chat(LIVE, "Job search helper", updated="2026-11-05T00:24:00Z"), **seed)]
    triggers = [{"id": "trig_EXAMPLELEFTBRIEF", "persistent_session_id": OLD, "enabled": True,
                 "prompt": "Scheduled run: morning brief."},
                {"id": "trig_EXAMPLEOWNBRIEF", "persistent_session_id": OWN, "enabled": False}]
    listener = {"chat": LIVE, "helper": True, "since": "2026-11-05T00:09:00Z",
                "took_from": OLD, "took_from_helper": True}
    info = {c["id"]: _detail(c["id"], c["title"]) for c in chats}
    return tidy.plan(chats, triggers, info, OPS_REG, listener, this_chat, REPO, TODAY, set(),
                     set(), set(), now=now)


def test_a_chat_they_started_goes_only_once_it_is_an_old_helper_they_have_left():
    """The chat they set up in answered the page first and carries the helper's name; once it
    has handed the page on it is an old helper ("we have 3 when we should have 1"), put away
    once they have not used it for an hour, never while they are in it. A chat of theirs that
    never had the helper's name is never listed, from any chat."""
    for here in (LIVE, OLD):
        got = _live_run(here)
        assert {c["id"]: c["why"] for c in got["archive"]}.get(OWN) == \
            "a helper the page no longer uses", here
    soon = _live_run(LIVE, now=dt.datetime(2026, 11, 5, 9, 0, tzinfo=dt.timezone.utc))
    assert {c["id"]: c["why"] for c in soon["keep"]}[OWN] == "they used it in the last hour"
    assert OWN not in {c["id"] for c in _live_run(OWN)["archive"]}     # never from itself
    mine = dict(_chat("session_EXAMPLEMYNOTES", "Job search: my own notes",
                      updated="2026-10-01T08:00:00Z"), origin="desktop_app")
    got = tidy.plan([mine], [], {mine["id"]: _detail(mine["id"])}, {}, {"chat": LIVE}, LIVE,
                    REPO, TODAY, set(), set(), set())
    assert got["archive"] == [] and got["keep"] == []
    assert tidy.person_started({"origin": "desktop_app"})
    assert not tidy.person_started({"origin": "claude_code_mcp_seed"})
    assert not tidy.person_started({})               # a listing that does not say: as before


def test_a_brief_left_in_the_helper_a_hand_over_replaced_moves_and_that_helper_goes():
    """The brief's task fired into the helper a hand-over replaced while the registry named no
    chat for it, so that helper was kept for good ("a scheduled task that is on runs in it").
    The task says where the brief runs: it moves into the live helper, the copy made for the
    old one is deleted, and the old helper is put away."""
    for here in (LIVE, OWN):
        got = _live_run(here)
        assert got["ask"] == []
        gone = {c["id"]: c["why"] for c in got["archive"]}
        assert gone[OLD] == "the brief moved into the chat that answers the page", here
        calls = got["brief"]
        assert calls[0]["tool"] == "create_trigger"
        assert calls[0]["args"]["persistent_session_id"] == LIVE
        assert "routines.py record --session " + LIVE in calls[1]["run"]
        assert calls[2]["tool"] == "delete_trigger"
        assert calls[2]["args"] == {"trigger_id": "trig_EXAMPLELEFTBRIEF"}
    # Run from the old helper itself (the brief's own run): the brief moves now, and the chat
    # is kept only until a tidy-up from another chat puts it away.
    got = _live_run(OLD)
    assert [c["tool"] for c in got["brief"] if "tool" in c] == ["create_trigger", "delete_trigger"]
    assert {c["id"]: c["why"] for c in got["keep"]}[OLD] == "it is this chat"
    # Used moments ago, it is kept, and so is the brief in it, until a later tidy-up.
    soon = _live_run(LIVE, now=dt.datetime(2026, 11, 5, 8, 50, tzinfo=dt.timezone.utc))
    assert OLD not in {c["id"] for c in soon["archive"]} and soon["brief"] == []


def test_the_live_helper_asks_for_its_own_check_in_while_the_old_one_finishes(copy):
    """After two hand-overs in an hour, both "(finishing up)" chats stayed until the next
    morning: the new helper's first tidy-up kept each while it was still finishing, and nothing
    rang the new helper again (the maintainer's live run, 2026-11-05). Run by the live helper
    within a day of its hand-over, with an old helper kept only for now, the tidy-up asks for a
    check-in half an hour on, one at a time; from any other chat, a day on, or with nothing
    kept for now, it asks for none."""
    soon = dt.datetime(2026, 11, 5, 8, 50, tzinfo=dt.timezone.utc)
    assert _live_run(LIVE, now=soon)["recheck"] is True          # the old one used moments ago
    assert _live_run(OWN, now=soon)["recheck"] is False          # not the live helper
    assert _live_run(LIVE)["recheck"] is False                   # the old one put away instead
    later = dt.datetime(2026, 11, 6, 8, 50, tzinfo=dt.timezone.utc)
    assert _live_run(LIVE, now=later)["recheck"] is False        # a day on: the daily tidy-up
    assert tidy.recheck_due(soon)
    tidy.mark_recheck(soon)
    assert not tidy.recheck_due(soon + dt.timedelta(minutes=10))
    assert tidy.recheck_due(soon + dt.timedelta(minutes=31))
    tidy._mark_checked("2026-11-05")                             # the day's mark keeps it
    assert not tidy.recheck_due(soon + dt.timedelta(minutes=10))
    assert tidy.RECHECK_MIN * 60 >= tidy.RETIRE_AGAIN_S          # due again by the check-in
