"""The chat that answers the page keeps hearing it, and never takes over a chat that is the person's.

From the stranger audit, 3 November (X-4, X-6, X-24, X-27, X-64, X-65, X-84): the person's own
chat was renewed like a helper the app started, and a helper was then free to archive it and
move the brief; a chat that took the page over never asked to watch it, so the page went deaf
again after every renewal or Wake Claude; a chat that once saw another answer the page never
looked again; a chat taking the page archived the old helper while its brief was still saving;
an update moved the page out of an idle helper into whichever chat the person opened; a second
chat during setup took the page from the chat setting them up; and the Wake link typed a
command into the person's new chat. Every page and chat id here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_one_chat_answers_the_page import Copy  # noqa: E402

NOW = dt.datetime(2026, 11, 4, 17, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def copy(tmp_path, monkeypatch):
    c = Copy(tmp_path)
    for k, v in c.env().items():
        monkeypatch.setenv(k, v)
    yield c
    sys.path.remove(c.root)


def _db(rec, version=3, **more):
    return dict({"meta": {"listener": {"data": rec, "version": version}}, "work": {}}, **more)


def test_the_persons_own_chat_is_never_renewed_into_a_helper(copy, monkeypatch):
    """X-4: the chat the person published from answers the page as theirs: a day on, it is
    never replaced by a helper the app starts unasked (which then archived it and took its
    brief). A helper the app started still renews."""
    import app_listen
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "context_tokens", lambda: 0)
    monkeypatch.setattr("app_setup.origin", lambda: ("example-owner", "my-job-search"))
    own = {"chat": "session_PERSONSOWN", "kind": "cloud", "helper": False,
           "since": "2026-11-03T08:00:00Z", "answered_at": "2026-11-04T16:00:00Z"}
    assert app_listen.renewal(own, _db(own), "session_PERSONSOWN", NOW) is None
    helper = dict(own, chat="session_EXAMPLEHELPERA", helper=True)
    assert app_listen.renewal(helper, _db(helper), "session_EXAMPLEHELPERA", NOW)
    # The record of a take keeps whether the chat it took from was a helper, so the tidy-up
    # only ever puts away a chat the app started.
    took = app_listen.decide(_db(own), "session_EXAMPLEHELPERB", str(copy.root) + "/a", NOW,
                             listen=True, helper=True)
    assert took["record"]["took_from"] == "session_PERSONSOWN"
    assert took["record"]["took_from_helper"] is False


def test_a_chat_of_the_persons_put_away_before_is_brought_back(copy, tmp_path):
    """X-4's repair for a copy it already happened to: a chat the person named, archived by an
    earlier tidy-up, is brought back once at the next tidy; one the app made stays put away."""
    import subprocess
    with open(os.path.join(copy.profile, "tidy.json"), "w", encoding="utf-8") as fh:
        json.dump({"archived": [
            {"id": "session_PERSONSOWN", "title": "Find me a data job in Manchester", "on": "2026-11-01"},
            {"id": "session_OLDHELPER", "title": "Job search helper", "on": "2026-11-01"}]}, fh)
    sessions = tmp_path / "s.json"
    sessions.write_text(json.dumps({"data": []}), encoding="utf-8")
    run = lambda: subprocess.run(  # noqa: E731
        [sys.executable, os.path.join(ROOT, "tools", "tidy.py"), "plan", "--sessions",
         str(sessions), "--dump", str(tmp_path / "nodump")], env=copy.env(),
        capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
    said = run()
    assert "unarchive_session" in said and "session_PERSONSOWN" in said, said
    assert "session_OLDHELPER" not in said
    assert "session_PERSONSOWN" not in run()                     # once


def test_a_chat_that_takes_the_page_watches_it_and_takes_the_work_waiting(copy, tmp_path):
    """X-6: the chat that takes the page asks to watch it (a chat watches only a page it
    published, or one it asks to watch), and starts the work that waited while nobody heard."""
    import app_listen
    old = {"chat": "session_OLD", "kind": "cloud", "helper": True,
           "since": "2026-11-03T08:00:00Z", "answered_at": "2026-11-04T09:00:00Z"}
    db = _db(old, work={"search~1": {"data": {"kind": "search", "status": "queued",
                                              "asked_at": "2026-11-04T16:00:00Z"}, "version": 1}})
    took = app_listen.decide(db, "session_NEW", str(tmp_path / "a"), NOW, listen=True, helper=True)
    said = "\n".join(took["lines"])
    assert took["role"] == "listener"
    assert "ArtifactComments, action watch" in said and "on: true" not in said.replace(" ", "")
    assert "app.py wake" in said
    # The chat that already answers it keeps its watch asked for at every check-in too.
    mine = app_listen.decide(_db(dict(old, chat="session_NEW")), "session_NEW",
                             str(tmp_path / "b"), NOW)
    assert "ArtifactComments, action watch" in "\n".join(mine["lines"])


def test_taking_the_page_never_archives_the_chat_it_took_from(copy, tmp_path):
    """X-27: a fresh helper told the old one to be archived while the old one was still
    writing the brief and saving the morning's work. Putting old chats away is the tidy-up's,
    which keeps a chat that is running or holds work not landed."""
    import app_listen
    old = {"chat": "session_H1", "kind": "cloud", "helper": True,
           "since": "2026-11-03T08:00:00Z", "answered_at": "2026-11-04T07:40:00Z"}
    took = app_listen.decide(_db(old), "session_H2", str(tmp_path / "a"), NOW, listen=True,
                             helper=True)
    assert not [ln for ln in took["lines"] if "archive_session" in ln]
    # And the renewal is started only once this chat's own work has landed.
    line = app_listen.renew_line({"title": "Job search helper"})
    assert "land.py" in line


def test_an_update_never_moves_the_page_out_of_an_idle_helper(copy, tmp_path):
    """X-64: an update took the page from the helper after an hour with nothing to do, into
    whichever chat the person opened, which they then closed. A helper that is only idle is
    asked to republish; it is taken from only when it stopped answering."""
    import app_listen
    helper = {"chat": "session_HELPER", "kind": "cloud", "helper": True,
              "since": "2026-11-04T08:00:00Z", "answered_at": "2026-11-04T15:05:00Z"}
    got = app_listen.decide(_db(helper), "session_PERSONSQUESTION", str(tmp_path / "a"),
                            NOW, update=True)
    assert got["role"] == "other"
    # Something waited ten minutes and more with no answer: it stopped, and is taken from.
    db = _db(helper, work={"draft~1": {"data": {"kind": "draft", "status": "queued",
                                                "asked_at": "2026-11-04T16:30:00Z"}, "version": 1}})
    assert app_listen.decide(db, "session_PERSONSQUESTION", str(tmp_path / "b"), NOW,
                             update=True)["role"] == "listener"


def test_a_cached_listener_is_looked_at_again(copy):
    """X-24: once a chat saw another answer the page it never looked again, so a closed
    computer session or an archived helper left the page with nobody for good."""
    import app_listen
    now = dt.datetime.now(dt.timezone.utc)
    app_listen._save_seen({"listener": {"chat": "local-1", "kind": "computer", "confirmed": True,
                                        "seen_at": app_listen._stamp(now - dt.timedelta(hours=3))}})
    # Another session on the computer, hours later: the one that published has ended.
    assert app_listen.role("local-3", url="https://claude.ai/code/artifact/x") == "claim"
    # Two sessions open at once on one computer: the other still answers.
    app_listen._save_seen({"listener": {"chat": "local-1", "kind": "computer", "confirmed": True,
                                        "seen_at": app_listen._stamp(now)}})
    assert app_listen.role("local-3", url="https://claude.ai/code/artifact/x") == "other"
    # A cloud listener seen lately stays the other's; seen over a day ago, it is asked again.
    app_listen._save_seen({"listener": {"chat": "session_H", "kind": "cloud", "confirmed": True,
                                        "seen_at": app_listen._stamp(dt.datetime.now(dt.timezone.utc))}})
    assert app_listen.role("session_ME", url="https://claude.ai/code/artifact/x") == "other"
    app_listen._save_seen({"listener": {"chat": "session_H", "kind": "cloud", "confirmed": True,
                                        "seen_at": "2026-10-01T00:00:00Z"}})
    assert app_listen.role("session_ME", url="https://claude.ai/code/artifact/x") == "claim"


def test_the_chat_setting_them_up_keeps_the_page(copy, tmp_path):
    """X-65: a second chat during setup took the page from the chat writing the profile, and
    then carried setup on beside it: never while that chat's setup is going."""
    import app_listen
    import app_setup
    with open(os.path.join(copy.profile, "place.json"), "w", encoding="utf-8") as fh:
        json.dump({"setup": {"started": "2026-11-04", "chat": "session_SETUP"}}, fh)
    rec = {"chat": "session_SETUP", "kind": "cloud", "helper": False,
           "since": "2026-11-04T08:00:00Z", "answered_at": "2026-11-04T08:00:00Z"}
    db = _db(rec, work={"draft~1": {"data": {"kind": "draft", "status": "queued",
                                             "asked_at": "2026-11-04T16:30:00Z"}, "version": 1}})
    got = app_listen.decide(db, "session_SECOND", str(tmp_path / "a"), NOW, update=True)
    assert got["role"] == "other", got["lines"]
    assert app_setup.carry_on() == [] or not any("carries on" in ln for ln in app_setup.carry_on())


def test_no_upgrade_starts_while_setup_is_still_writing_the_profile(copy):
    """X-65: a second chat during setup, or a chat coming back to a stopped one, was told to
    start a background upgrade writing the same profile files setup was still writing. While
    setup is unfinished the upgrades wait, said in one line, and the plan is empty."""
    import subprocess
    import build_versions
    rec_path = os.path.join(copy.profile, "build_versions.json")
    with open(rec_path, encoding="utf-8") as fh:
        rec = json.load(fh)
    name = next(n for n, m in build_versions.METHODS.items()
                if m.get("by") == "upgrade" and not m.get("every_version") and n in rec)
    rec[name] = {"version": 1, "date": "2026-10-01"}
    with open(rec_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)

    def run(*args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_upgrades.py"),
                               *args], env=copy.env(), capture_output=True, text=True,
                              encoding="utf-8", timeout=120).stdout
    assert "upgrade.md" in run() or "pending" in run()            # it is pending
    with open(os.path.join(copy.profile, "place.json"), "w", encoding="utf-8") as fh:
        json.dump({"setup": {"started": "2026-11-04", "chat": "session_SETUP"}}, fh)
    said = run()
    assert "upgrade.md" not in said and "wait until setup is finished" in said, said
    assert json.loads(run("--plan").split("\n\n")[0] or "[]") == []


def test_an_update_that_changed_how_a_chat_starts_says_so_once(copy, monkeypatch):
    """X-78: copies at 4.0 to 4.2 took the update in their start's second step and went on
    with the old start's later steps, making a helper chat this release then put away. After
    a sync that changed how a chat starts, the chat is told its earlier steps are out of date."""
    import app_setup
    head = app_setup._head()
    assert head
    # A copy whose start never recorded which version it spoke for (4.0 to 4.2): said once.
    assert "changed how a chat starts" in app_setup.start_changed_line()
    assert app_setup.start_changed_line() == ""
    # Start spoke for a version whose start differs from this one's: said once.
    code, older = app_setup._git("rev-list", "-n", "1", head, "--", "tools/app_setup.py")
    code, older = app_setup._git("rev-parse", older.strip() + "~1")
    with open(app_setup._local_file(app_setup.START_HEAD), "w", encoding="utf-8") as fh:
        fh.write(older.strip() + "\n")
    assert "out of date" in app_setup.start_changed_line()
    # A start in this version records it: nothing more to say.
    copy.run("start", "--on", "m", "--tools", "none")
    assert app_setup.start_changed_line() == ""


def test_a_job_whose_chat_waits_on_the_person_says_so_on_the_page(copy, tmp_path):
    """X-7 and X-8, left to the page's side by group D: a job running in a chat of its own can
    stop on a question to the person (an approval it needs) with nobody there, and its card
    said only "may have stopped", then it was ended. The chat that answers the page reads each
    such chat (get_session); one that waits on the person is said to on its card, its lease
    kept, until its own next step clears it."""
    import app
    import page_db
    copy.page()
    os.makedirs(os.path.join(copy.db, "work"), exist_ok=True)
    with open(os.path.join(copy.db, "work", "draft~1.json"), "w", encoding="utf-8") as fh:
        json.dump({"data": {"kind": "draft", "status": "running", "claimed_by": "session_EXAMPLECHILDA",
                            "asked_at": "2026-11-04T16:00:00Z", "stage": 0,
                            "stage_at": "2026-11-04T16:01:00Z",
                            "lease_until": "2026-11-04T16:31:00Z"}, "version": 3}, fh)
    dump = copy.dump()
    db = page_db.load(dump)
    assert app.running_elsewhere(db, "session_LISTENER") == [("draft~1", "session_EXAMPLECHILDA")]
    said = json.loads(copy.run("pin", dump, "--work", "draft~1", "--blocked", "--now",
                               "2026-11-04T17:00:00Z"))
    assert said["batches"] and copy.send("\n".join(said["batches"]))
    item = json.load(open(os.path.join(copy.db, "work", "draft~1.json")))["data"]
    assert item["blocked_at"] == "2026-11-04T17:00:00Z" and item["lease_until"] > "2026-11-04T17:00"
    assert item["steps"][-1]["text"] == page_db.BLOCKED_LINE
    assert app.running_elsewhere(page_db.load(copy.dump("d2")), "session_LISTENER") == []
    # The job's own next step clears it.
    said = json.loads(copy.run("pin", copy.dump("d3"), "--work", "draft~1", "--chat",
                               "session_EXAMPLECHILDA", "--line", "Drafting the letter", "--now",
                               "2026-11-04T17:05:00Z"))
    assert said["batches"] and copy.send("\n".join(said["batches"]))
    assert not json.load(open(os.path.join(copy.db, "work", "draft~1.json")))["data"]["blocked_at"]


def test_the_wake_link_types_plain_words_and_the_chat_knows_them(copy, monkeypatch):
    """X-84: the page's Wake Claude link typed a python command into the person's new chat.
    It types plain words now, and the app's hook tells that chat what to run."""
    import app_listen
    import learned
    assert "python3" not in app_listen.WAKE_PROMPT and "--" not in app_listen.WAKE_PROMPT
    assert "python3" not in app_listen.wake_url("example-owner/my-job-search")
    got = learned._wake_due({"hook_event_name": "UserPromptSubmit",
                             "prompt": app_listen.WAKE_PROMPT})
    assert "app.py start --listen --helper" in got
    assert learned._wake_due({"hook_event_name": "UserPromptSubmit", "prompt": "hi"}) == ""
