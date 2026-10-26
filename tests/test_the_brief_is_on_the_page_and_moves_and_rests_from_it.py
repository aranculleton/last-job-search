"""The brief is the page's too: it takes in the page's ticks first, links the page, asks its
questions there, and its days, time and a break are changed from the page.

What the person ticked on their page changed nothing the brief counted until some chat woke,
it linked a file on GitHub, and its questions waited in a chat nobody had open. Code cannot
change a scheduled task, so moving the brief or pausing the search writes the registry and
the state files (tools/routines.py) and keeps the one call a chat must make. Invented people
only, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]
EXAMPLE = os.path.join(ROOT, "profile.example")
TODAY = "2026-10-25"
PAGE = "https://claude.ai/code/artifact/example-page"

import brief  # noqa: E402


class Search:
    def __init__(self, tmp_path, page=True):
        self.state = str(tmp_path / "state")
        shutil.copytree(os.path.join(EXAMPLE, "state"), self.state)
        self.profile = str(tmp_path / "profile")
        shutil.copytree(EXAMPLE, self.profile, ignore=shutil.ignore_patterns("state", "tests",
                                                                             "tips.json"))
        if page:
            with open(os.path.join(self.profile, "app.json"), "w", encoding="utf-8") as fh:
                json.dump({"url": PAGE}, fh)
        self.sync = str(tmp_path / "sync.txt")

    def env(self):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                   LJS_BRIEF_SYNC=self.sync, PYTHONIOENCODING="utf-8", LJS_COPY="private")
        env.pop("CLAUDE_CODE_REMOTE", None)
        return env

    def run(self, tool, *args, ok=(0,)):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", tool), *args], cwd=ROOT,
                           env=self.env(), capture_output=True, text=True, encoding="utf-8",
                           timeout=120)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout

    def registry(self):
        with open(os.path.join(self.profile, "routines.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def contacts(self):
        import csv
        with open(os.path.join(self.state, "network_contacts.csv"), encoding="utf-8") as fh:
            return {r["contact_id"]: r for r in csv.DictReader(fh)}

    def tracker(self):
        import csv
        with open(os.path.join(self.state, "job_search_tracker.csv"), encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


def _questions(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("date: %s\nexit: 0\nearlier: \nsetup: \n---\n"
                 "  These need you: one short question each, at the end of a session:\n"
                 "    - Is your notice period still a month?  [fact]\n" % TODAY)


# ------------------------------------------------------------------ the page


def test_the_message_links_the_page_and_its_questions_wait_there(tmp_path):
    s = Search(tmp_path)
    _questions(s.sync)
    out = s.run("brief.py", "--today", TODAY)
    message, claude = out.split("FOR CLAUDE, never in the message:\n", 1)
    assert "Your page: %s#todo" % PAGE in message and "github.com" not in message
    assert "1 question waits for you on your page." in message
    assert "notice period" not in message
    assert "the questions are on the page as To do cards" in claude
    assert "app.py view <D>/view --dump <D> --chat brief" in claude
    assert "Never publish or watch the page" in claude
    # With no page, the record on GitHub and the questions at the end, as before.
    bare = Search(tmp_path / "bare", page=False)
    _questions(bare.sync)
    out = bare.run("brief.py", "--today", TODAY)
    assert "Your page:" not in out and "at most three questions" in out


def test_the_ticks_on_the_page_are_applied_before_anything_is_counted(monkeypatch, tmp_path):
    s = Search(tmp_path)
    monkeypatch.setenv("LJS_PROFILE", s.profile)
    first = brief.page_first(PAGE, ["--on", "Opus 5.5", "--write", "--today", TODAY])
    lines = first.splitlines()
    assert lines[0].startswith("PAGE FIRST, FOR CLAUDE")
    assert "collection actions, then collection receipts" in lines[1]
    assert "app.py apply <D> --chat brief --claim" in lines[2]
    assert "app.py apply <D> --chat brief," in lines[3]
    assert "python3 tools/brief.py --write --today %s --page-applied" % TODAY in lines[4]
    assert brief.page_url() == PAGE
    # The start stops before the gather where there is a page.
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(brief.subprocess, "run", lambda argv, **kw: calls.append(argv) or Done())
    monkeypatch.setenv("LJS_BRIEF_SYNC", s.sync)
    assert brief.start(["--on", "m", "--write"], "m") == 0
    assert not any(str(c[1]).endswith("brief.py") for c in calls if len(c) > 1)
    calls.clear()
    assert brief.start(["--on", "m", "--write", "--page-applied"], "m") == 0
    assert str(calls[-1][1]).endswith("brief.py")


def test_the_prompt_says_the_page_comes_first_and_is_never_published():
    with open(os.path.join(ROOT, "automation", "prompts", "morning_brief.md"),
              encoding="utf-8") as fh:
        text = fh.read()
    assert "PAGE\nFIRST" in text or "PAGE FIRST" in text
    assert "Never publish the page or watch it" in text


# ------------------------------------------------------------------ moving the brief


def test_the_brief_moves_to_new_days_and_a_time_and_a_chat_moves_the_task(tmp_path):
    s = Search(tmp_path)
    out = s.run("routines.py", "move", "--days", "tue,fri", "--time", "9:00")
    assert "tell them: Your brief comes Tuesdays and Fridays at 8:38 from now on." in out
    r = next(x for x in s.registry()["routines"] if x["key"] == "morning_brief")
    assert r["cron"] == "CRON_TZ=Europe/London 38 8 * * 2,5"
    assert s.run("routines.py", "check").strip() == "routines.json: clean"
    owed = json.loads(s.run("routines.py", "calls"))
    assert owed == [{"tool": "update_trigger", "for": "move", "n": 1,
                     "args": {"trigger_id": "trig_EXAMPLEBRIEF",
                              "cron_expression": "CRON_TZ=Europe/London 38 8 * * 2,5"},
                     "why": "the brief now comes Tuesdays and Fridays at 8:38"}]
    # Moved twice before a chat made the call: one call, the newest.
    s.run("routines.py", "move", "--time", "18:15")
    owed = json.loads(s.run("routines.py", "calls"))
    assert len(owed) == 1 and owed[0]["args"]["cron_expression"].endswith("15 18 * * 2,5")
    assert "made; 0 still owed" in s.run("routines.py", "called", "1")
    import routines
    part = routines.page_part(os.path.join(s.profile, "routines.json"))
    assert part["when"] == "Tuesdays and Fridays at 18:15" and part["paused"] is None
    assert part["actions"] == {"move": "brief.move", "pause": "brief.pause",
                               "resume": "brief.resume"}
    model = json.loads(s.run("app.py", "model", "--now", "2026-10-25T18:00:00Z"))
    assert model["schedule"]["when"] == "Tuesdays and Fridays at 18:15"


def test_a_time_off_the_hour_is_kept_and_a_bad_one_changes_nothing(tmp_path):
    import routines
    assert routines.cron_for("1,4", "07:38", "Europe/London")["cron"] == \
        "CRON_TZ=Europe/London 38 7 * * 1,4"
    assert routines.cron_for("Mondays and Thursdays", "8am", "Europe/London")["time"] == "07:38"
    assert routines.read_cron("CRON_TZ=Europe/London 56 7 * * 1-5")["days"] == [1, 2, 3, 4, 5]
    s = Search(tmp_path)
    before = s.registry()
    assert "nothing changed" in s.run("routines.py", "move", "--time", "25:99", ok=(1,))
    assert s.registry() == before


# ------------------------------------------------------------------ a break


def test_a_break_holds_the_brief_and_every_follow_up_and_coming_back_early_undoes_it(tmp_path):
    s = Search(tmp_path)
    before = s.contacts()
    out = s.run("routines.py", "pause", "--until", "2026-11-08", "--today", TODAY)
    assert "tell them: Your search is paused until 8 Nov. Nothing is chased meanwhile." in out
    held = {cid: c for cid, c in s.contacts().items()
            if c["next_action"].startswith("HOLD until 2026-11-08 (search paused 2026-10-25): ")}
    assert held, "no contact was held"
    import open_actions
    import state as st
    contacts = st.load_contacts(os.path.join(s.state, "network_contacts.csv"))
    for cid in held:
        assert st.action_hold(next(c for c in contacts if c["contact_id"] == cid)["next_action"],
                              "2026-10-30") == "on hold until 2026-11-08"
    import followups
    live = [r for r in s.tracker() if r["status"] in ("applied", "interview")]
    assert live and all(followups.not_chased(r["notes"], dt.date(2026, 10, 30)) for r in live)
    owed = json.loads(s.run("routines.py", "calls"))
    assert [c["tool"] for c in owed] == ["update_trigger", "create_trigger"]
    assert owed[0]["args"] == {"trigger_id": "trig_EXAMPLEBRIEF", "enabled": False}
    back = owed[1]["args"]
    assert back["persistent_session_id"] == "session_EXAMPLEBRIEF"
    assert back["run_once_at"] == "2026-11-08T07:56:00Z"        # 7:56 in London, in winter
    assert "automation/prompts/morning_brief.md" in back["prompt"]
    s.run("routines.py", "called", "2", "--id", "trig_EXAMPLEBACK")
    s.run("routines.py", "called", "1")
    # A brief that runs anyway during the break says so in one line, and nothing else.
    out = s.run("brief.py", "--today", "2026-10-28", "--write")
    message = out.split("FOR CLAUDE", 1)[0].strip().splitlines()
    assert message == ["Your search is paused until 8 Nov. Nothing is chased meanwhile.",
                       "Your page: %s#todo" % PAGE]
    assert "no news search" in out
    # Back early: every hold the break wrote comes off, the applications are chased again,
    # and the brief is turned back on, its welcome-back run taken away.
    out = s.run("routines.py", "resume", "--today", "2026-10-30")
    assert "Welcome back" in out
    after = s.contacts()
    for cid in held:
        assert after[cid]["next_action"] == before[cid]["next_action"]
    assert all("chase again (search resumed)" in r["notes"] for r in s.tracker()
               if r["status"] in ("applied", "interview"))
    owed = json.loads(s.run("routines.py", "calls"))
    assert [(c["tool"], c["args"]) for c in owed] == [
        ("update_trigger", {"trigger_id": "trig_EXAMPLEBRIEF", "enabled": True}),
        ("delete_trigger", {"trigger_id": "trig_EXAMPLEBACK"})]
    assert "pause" not in s.registry() and s.run("routines.py", "check").strip().endswith("clean")
    assert open_actions  # the due list read the holds above


def test_the_brief_on_the_day_the_break_ends_lifts_it(tmp_path):
    s = Search(tmp_path)
    s.run("routines.py", "pause", "--until", "2026-11-08", "--today", TODAY)
    out = s.run("brief.py", "--today", "2026-11-08", "--write")
    assert "Welcome back: your break is over" in out
    assert "pause" not in s.registry()
    assert "routines.py calls" in out.split("FOR CLAUDE", 1)[1]
