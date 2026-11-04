"""A stranger's brief reaches them, says where it is, and mends itself (the stranger audit of
3 November, group B: routines and the brief).

A stranger set up in a cloud chat, or on a phone, with no connection to the maintainer: their
brief posted silently into an old chat with no phone notification and nothing saying where it
was; a break whose one welcome-back run failed never ended; a brief that stopped was noticed
by nobody; a chat with no page was told to press a bell it did not have; the maintainer's own
bar for employers was applied to everyone. The builder's decisions of the same night are
binding here: the brief stays bound to the chat that holds the copy, never moved, turned off
or made again while it works, and the run sends its headline with PushNotification, asked
from one place (tools/brief.py's own lines). Invented ids and employers only, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]
EXAMPLE = os.path.join(ROOT, "profile.example")
PAGE = "https://claude.ai/code/artifact/example-page"
CHAT = "session_EXAMPLEHERCHAT"
REPO = "example-owner/my-job-search"

import brief  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402
import repo_files  # noqa: E402


class Copy:
    """A person's copy: the example profile and state, in a folder of the test's own."""

    def __init__(self, tmp_path, page=True):
        self.tmp = tmp_path
        self.state = str(tmp_path / "state")
        shutil.copytree(os.path.join(EXAMPLE, "state"), self.state)
        self.profile = str(tmp_path / "profile")
        shutil.copytree(EXAMPLE, self.profile, ignore=shutil.ignore_patterns("state", "tests",
                                                                             "tips.json"))
        if page:
            self.write("app.json", {"url": PAGE})
        self.sync = str(tmp_path / "sync.txt")

    def write(self, name, data):
        with open(os.path.join(self.profile, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read(self, name):
        with open(os.path.join(self.profile, name), encoding="utf-8") as fh:
            return json.load(fh)

    def env(self, **more):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                   LJS_BRIEF_SYNC=self.sync, PYTHONIOENCODING="utf-8", LJS_COPY="private",
                   LJS_CHAT=CHAT)
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.update(more)
        return env

    def run(self, tool, *args, ok=(0,), stdin=None, **env):
        r = subprocess.run([*repo_files.python_on_github(os.path.join(ROOT, "tools", tool)), *args],
                           cwd=ROOT,
                           env=self.env(**env), capture_output=True, text=True, encoding="utf-8",
                           timeout=180, input=stdin)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout


def _prompt(path):
    with open(os.path.join(ROOT, "automation", "prompts", path), encoding="utf-8") as fh:
        return fh.read()


def _readme():
    with open(os.path.join(ROOT, "automation", "README.md"), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


# ------------------------------------------------------------------ the push (S3, X-1)


def test_a_brief_bound_to_a_chat_ends_with_one_push_of_its_headline(tmp_path):
    """S3, X-1: the brief posted into a chat with no notification. The run now sends its
    headline, with the page's link, under PushNotification's 200 characters, asked by
    brief.py's own lines alone (one place, never the shared prompts)."""
    c = Copy(tmp_path)
    out = c.run("brief.py", "--today", "2026-11-03")
    message, claude = out.split("FOR CLAUDE", 1)
    asks = [ln for ln in claude.splitlines() if "PushNotification" in ln]
    assert len(asks) == 1, claude
    line = json.loads(re.search(r"with (\".*?\"), then", asks[0]).group(1))
    lead = message.strip().splitlines()[1]
    assert line.startswith(lead[:40]) and line.endswith(" " + PAGE) and len(line) < 200
    assert "brief.py pushed" in asks[0]
    for shared in ("_common.md", "morning_brief.md"):
        assert "PushNotification" not in _prompt(shared), shared
    with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
        assert json.load(fh)["agentPushNotifEnabled"] is True
    import security_guards
    assert "agentPushNotifEnabled" in security_guards.ALLOWED_SETTINGS_KEYS


def test_only_a_brief_with_no_notification_of_its_own_is_asked_to_push(monkeypatch):
    base = {"timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE}]}
    for setup, chat, asks in (("chat_per_briefing", True, True), ("routines_screen", False, False),
                              ("ops_relay", False, False), ("ops_relay", True, True)):
        reg = json.loads(json.dumps(base))
        reg["setup"] = setup
        if chat:
            reg["routines"][0]["chat"] = {"session_id": CHAT}
        monkeypatch.setattr(routines, "load", lambda path=None, reg=reg: reg)
        assert brief.push_due({"lead": "x"}) is asks, setup
        assert bool(brief.push_step({"lead": "x"})) is asks, setup
    assert brief.push_due({"lead": "x", "paused": "2026-11-10"}) is False
    long = brief.push_line({"lead": "word " * 80, "page": PAGE})
    assert len(long) < 200 and long.endswith(" " + PAGE)


def test_a_push_that_was_not_sent_is_said_once_in_her_next_message_in_that_chat(tmp_path):
    """The builder's decision: where the push could not be sent, the person's next message
    in that chat says so, once, and promises nothing."""
    c = Copy(tmp_path, page=False)
    c.run("brief.py", "--write")
    assert "not sent" in c.run("brief.py", "pushed", "Notification not sent.")
    event = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "morning"})
    said = c.run("learned.py", "hook", stdin=event)
    assert "could not be sent to your phone" in said and "earlier in this chat" in said
    assert "could not be sent" not in c.run("learned.py", "hook", stdin=event)   # once
    # Never in another chat, never on the next run's own turn.
    c.run("brief.py", "pushed", "Notification not sent.")
    os.remove(os.path.join(os.path.dirname(c.sync), brief.PUSH_SAID))
    assert "could not be sent" not in c.run("learned.py", "hook", stdin=event,
                                            LJS_CHAT="session_EXAMPLEOTHER")
    run = json.dumps({"hook_event_name": "UserPromptSubmit",
                      "prompt": "Scheduled run: morning brief. Run `git fetch origin master`"})
    assert "could not be sent" not in c.run("learned.py", "hook", stdin=run)
    # Sent: nothing to say.
    assert "push was sent" in c.run("brief.py", "pushed", "Mobile push requested.")
    assert "could not be sent" not in c.run("learned.py", "hook", stdin=event)


def test_where_it_comes_is_said_and_nothing_promises_a_push(tmp_path):
    """X-1, X-11: 'Your brief is on ... the bell on your Brief' was said with no page and no
    bell, never which chat it came to, and the docs said silence meant failure."""
    assert routines.default("America/New_York", page=False)["say"] == (
        "Your morning brief comes to this chat every day at 7:38, New York time. Say \"move my "
        "brief\" or \"stop my brief\" in any chat to change it.")
    assert "bell" in routines.default("America/New_York", page=True)["say"]
    for said in (routines.default("Europe/Paris", page=False)["say"],
                 routines.default("Europe/Paris", page=True)["say"]):
        assert "phone" not in said and "push" not in said
    readme = _readme()
    assert "silence" not in readme.lower() and "/setup` never makes it" not in readme
    assert "may not arrive; the brief itself is the record" in readme
    # A brief made before says where it comes on its first run after the update, once.
    c = Copy(tmp_path, page=False)
    out = c.run("brief.py", "--write")
    assert "Your brief comes to this chat every day at 7:38, London time." in out
    assert "Your brief comes to" not in c.run("brief.py", "--write")
    assert c.read("routines.json")["told_where"]


def test_setup_names_the_brief_in_its_last_message_with_or_without_a_page():
    """X-42: a chat-only setup was sent to a README section saying '/setup never makes it'."""
    with open(os.path.join(ROOT, ".claude", "commands", "setup.md"), encoding="utf-8") as fh:
        setup = fh.read()
    step5 = setup.split("## Step 5", 1)[1]
    assert "with or without a page" in step5 and "Where there is no page: automation/README.md" \
        not in step5
    assert "where and when your morning brief comes" in step5


# ------------------------------------------------------------------ binding and pressing


def test_with_a_page_the_brief_binds_to_the_chat_that_answers_it_and_asked_by_nobody_says_so(
        tmp_path, monkeypatch):
    """X-11, X-69: the brief-daily upgrade bound the brief to whichever chat ran it, and every
    task the app made by itself was reported as a person's request."""
    monkeypatch.setattr(routines, "has_page", lambda: True)
    monkeypatch.setattr(routines, "_page_chat", lambda: "session_EXAMPLEHELPER")
    monkeypatch.setenv("LJS_CHAT", "session_EXAMPLECOVERLETTER")
    got = routines.plan("example-owner", "my-job-search", "Europe/London",
                        initiation="own_initiative")
    assert got["create_trigger"]["persistent_session_id"] == "session_EXAMPLEHELPER"
    assert got["create_trigger"]["initiation"] == "own_initiative"
    monkeypatch.setattr(routines, "has_page", lambda: False)
    got = routines.plan("example-owner", "my-job-search", "Europe/London")
    assert got["create_trigger"]["persistent_session_id"] == "session_EXAMPLECOVERLETTER"
    import profile_upgrades
    assert "--own-initiative" in profile_upgrades.by_id("brief-daily").run


def test_a_computer_chat_with_no_page_makes_the_page_before_any_bell(tmp_path):
    """X-37: 'press the bell on your Brief once' with no page, so no bell and no brief ever."""
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile"), CLAUDECODE="1",
               CLAUDE_CODE_SESSION_ID="abc")
    for key in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID"):
        env.pop(key, None)
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief",
                          "--triggers", str(empty)], capture_output=True, text=True,
                         encoding="utf-8", env=env).stdout
    assert "make their page first: python3 tools/app.py start" in out
    assert out.index("app.py start") < out.index("press the bell")


def test_the_default_time_is_outside_the_schedulers_slow_hours(monkeypatch):
    """X-69: 7:38 on the US west coast and in Mountain time is inside 6 to 9 AM Pacific, when
    the scheduler says runs can be delayed."""
    for zone in ("America/Los_Angeles", "America/Denver", "America/Phoenix", "America/Vancouver"):
        assert routines.default(zone, page=True)["cron"] == f"CRON_TZ={zone} 38 5 * * *", zone
    for zone in ("America/Chicago", "America/New_York", "Europe/London", "Australia/Sydney"):
        assert routines.default(zone, page=True)["cron"] == f"CRON_TZ={zone} 38 7 * * *", zone


def test_a_zone_written_abbreviation_first_is_read_and_a_bad_one_never_recorded(tmp_path):
    """X-66: 'EST/EDT (America/New_York)' became CRON_TZ=EST/EDT, a zone every check took.
    Reading it right came with fbeb80b (person.zone_in takes the first zone this computer
    knows); a bad zone is now refused, and one already in a registry is rewritten."""
    import person
    for words, zone in (("EST/EDT (America/New_York)", "America/New_York"),
                        ("AEST/AEDT (Australia/Sydney)", "Australia/Sydney"),
                        ("CET/CEST (Europe/Berlin)", "Europe/Berlin")):
        assert person.zone_in(words) == zone
    assert not routines.zone_ok("EST/EDT") and routines.zone_ok("America/New_York")
    assert routines.default("EST/EDT")["cron"] == ""
    path = tmp_path / "routines.json"
    try:
        routines.record(CHAT, "trig_EXAMPLEB", "CRON_TZ=EST/EDT 38 7 * * *", path=str(path))
        raise AssertionError("recorded")
    except ValueError as e:
        assert "EST/EDT" in str(e)
    # One recorded before: rewritten to the person's own zone, its update owed.
    old = {"setup": "chat_per_briefing", "timezone": "EST/EDT", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": "CRON_TZ=EST/EDT 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": CHAT}}]}
    path.write_text(json.dumps(old), encoding="utf-8")
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(routines, "home_zone", lambda: "America/New_York")
    try:
        owed = routines.calls(str(path), today="2026-11-03")
    finally:
        mp.undo()
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg["timezone"] == "America/New_York"
    assert reg["routines"][0]["cron"] == "CRON_TZ=America/New_York 38 7 * * *"
    assert any(c["args"].get("cron_expression") == "CRON_TZ=America/New_York 38 7 * * *"
               for c in owed)


# ------------------------------------------------------------------ mending itself


def test_a_break_whose_welcome_back_failed_ends_by_itself(tmp_path):
    """X-9: the one welcome-back run was the only thing that ended a break; if it failed, the
    brief stayed off for good while the page showed it on. It now gets its files in any chat,
    runs in a chat with the copy (never a new empty one), and any start, wake or brief after
    the day lifts the break."""
    c = Copy(tmp_path)
    c.run("routines.py", "pause", "--until", "2026-11-10", "--today", "2026-11-03")
    owed = json.loads(c.run("routines.py", "calls", "--today", "2026-11-03"))
    back = next(x for x in owed if x["for"] == "back")["args"]
    assert routines.COPY_MARK in back["prompt"]
    assert back["persistent_session_id"].startswith("session_") and \
        "create_new_session_on_fire" not in back
    # The welcome-back never ran. The first chat after the day ends the break all the same.
    owed = json.loads(c.run("routines.py", "calls", "--today", "2026-11-12"))
    assert "pause" not in c.read("routines.json")
    assert ("update_trigger", True) in [(x["tool"], x["args"].get("enabled")) for x in owed]
    assert routines.page_part(os.path.join(c.profile, "routines.json"))["paused"] is None
    # A routine's break comes back in the chat that asked for it, never a new empty chat.
    screen = {"setup": "routines_screen", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLES",
         "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
         "notifications": {"push": True}}]}
    c.write("routines.json", screen)
    c.run("routines.py", "pause", "--until", "2026-11-10", "--today", "2026-11-03")
    back = next(x for x in json.loads(c.run("routines.py", "calls", "--today", "2026-11-03"))
                if x["for"] == "back")["args"]
    assert back["persistent_session_id"] == CHAT and "create_new_session_on_fire" not in back


def test_a_brief_that_did_not_come_is_noticed_once_and_shown_late(tmp_path):
    """X-10: a brief that stopped (its chat gone, its task off, a run failed) was noticed by
    nobody; the page kept saying 'Every day at 7:38'."""
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": CHAT}, "made": "2026-10-30"}]}
    noon = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
    assert routines.overdue(reg, noon, {"2026-11-01"}) == "2026-11-03"
    assert routines.overdue(reg, noon, {"2026-11-03"}) == ""
    early = dt.datetime(2026, 11, 3, 8, 0, tzinfo=dt.timezone.utc)      # inside the grace
    assert routines.overdue(reg, early, {"2026-11-02"}) == ""
    assert routines.overdue(reg, early, {"2026-11-01"}) == "2026-11-02"
    made_today = json.loads(json.dumps(reg))
    made_today["routines"][0]["made"] = "2026-11-03"
    assert routines.overdue(made_today, noon, set()) == ""
    off = json.loads(json.dumps(reg))
    off["routines"][0]["off"] = True
    assert routines.overdue(off, noon, set()) == ""
    assert routines.overdue(dict(reg, pause={"until": "2026-11-09"}), noon, set()) == ""
    # Any chat that asks what is owed is given one look at the scheduled tasks, once a day.
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    owed = routines.calls(str(path), today="2026-11-03")
    assert [c["tool"] for c in owed if c["for"] == "late"] == ["list_triggers"]
    assert "routines.py brief --triggers" in owed[-1]["why"]
    routines.called(owed[-1]["n"], path=str(path))
    assert not [c for c in routines.calls(str(path), today="2026-11-03") if c["for"] == "late"]
    assert routines.late_line("2026-11-02").startswith("Your brief didn't come on 2 Nov")


def test_every_task_of_the_apps_gets_the_line_for_its_files_from_any_chat(tmp_path):
    """X-43: only the helper's tidy-up gave a stored prompt the line that gets the copy, so a
    chat-only person's brief, a shortlist and a welcome-back never got it."""
    old = routines.DEFAULT_STUB.format(label="job round", Label="Job round",
                                       prompt_file="automation/prompts/job_round.md", relay_id="")
    listing = [{"id": "trig_EXAMPLEROUND", "name": "Job search: shortlist", "enabled": True,
                "prompt": old},
               {"id": "trig_EXAMPLEPLANTS", "name": "Water the plants", "enabled": True,
                "prompt": "Water the plants."},
               {"id": "trig_EXAMPLEDONE", "name": "Job search: shortlist", "enabled": True,
                "prompt": routines.with_copy(old, REPO)}]
    got = routines.mend(listing, REPO)
    assert [c["args"]["trigger_id"] for c in got] == ["trig_EXAMPLEROUND"]
    assert routines.COPY_MARK in got[0]["args"]["prompt"]
    # The brief-copy-line upgrade is pending until every task is marked mended.
    import profile_upgrades
    assert profile_upgrades.by_id("brief-copy-line").needs == "nobody"
    # A cloned copy loads none of its agents: the brief says how the news is found then.
    assert ".claude/agents/news-reader.md" in _prompt("morning_brief.md")


# ------------------------------------------------------------------ the tidy-up


def test_run_chats_are_the_apps_and_are_remembered_until_old_enough():
    """CHAT_ONLY_REVIEWS: run chats a task started are titled with a lightning mark and are
    never in list_sessions, so the tidy-up never saw them, though the README said it did."""
    assert tidy.APP_TITLE.match("⚡ Job search: deliver to phone")
    assert tidy.APP_TITLE.match("⚡️ Job search: morning brief")
    assert not tidy.APP_TITLE.match("⚡ my own routine")
    stub = routines.DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                        prompt_file=routines.BRIEF_FILE, relay_id="")
    tasks = [{"id": "trig_EXAMPLESCREEN", "prompt": stub, "session": "", "enabled": True,
              "last_run": {"session_id": "session_EXAMPLERUN9", "fired_at": "2026-11-03T06:38:00Z"}},
             {"id": "trig_EXAMPLEBOUND", "prompt": stub, "session": CHAT, "enabled": True,
              "last_run": {"session_id": CHAT, "fired_at": "2026-11-03T06:38:00Z"}}]
    runs, chats = tidy.run_chats(tasks, {"session_EXAMPLERUN1": "2026-10-28T06:38:00Z"},
                                 set(), set())
    assert runs == {"session_EXAMPLERUN1": "2026-10-28T06:38:00Z",
                    "session_EXAMPLERUN9": "2026-11-03T06:38:00Z"}
    reg = {"setup": "routines_screen", "timezone": "Europe/London", "routines": []}
    info = {c["id"]: {"id": c["id"], "session_context": {
        "sources": [{"git_repository": {"url": "https://github.com/" + REPO}}]}} for c in chats}
    got = tidy.plan(chats, [], info, reg, {"chat": "session_EXAMPLEHELPER"},
                    "session_EXAMPLEHELPER", REPO, dt.date(2026, 11, 3), set(), set(), set())
    assert [a["id"] for a in got["archive"]] == ["session_EXAMPLERUN1"]      # two days old
    assert any(k["id"] == "session_EXAMPLERUN9" for k in got["keep"])        # today's


def test_a_shortlist_in_a_helper_the_page_no_longer_uses_moves_with_the_brief():
    """X-50: the helper the brief moved out of was archived while the shortlist still ran in
    it. A task that works where it is stays; one in a chat that no longer works moves."""
    old = "session_EXAMPLEOLDHELPER"
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": old}},
        {"key": "job_round", "name": "Job search: shortlist", "trigger_id": "trig_EXAMPLER",
         "cron": "CRON_TZ=Europe/London 52 6 * * 1,4",
         "prompt_file": "automation/prompts/job_round.md", "chat": {"session_id": old}}]}
    trig = [{"id": "trig_EXAMPLEB", "session": old, "enabled": True},
            {"id": "trig_EXAMPLER", "session": old, "enabled": True}]
    chats = [{"id": old, "title": "Job search helper", "updated_at": "2026-10-20T08:00:00Z"},
             {"id": "session_EXAMPLEHELPER", "title": "Job search helper",
              "updated_at": "2026-11-03T08:00:00Z"}]
    info = {old: {"id": old, "session_context": {
        "sources": [{"git_repository": {"url": "https://github.com/" + REPO}}]}}}
    got = tidy.plan(chats, trig, info, reg, {"chat": "session_EXAMPLEHELPER", "took_from": old},
                    "session_EXAMPLEHELPER", REPO, dt.date(2026, 11, 3), set(), set(), set())
    assert got["brief"][0]["args"]["persistent_session_id"] == "session_EXAMPLEHELPER"
    assert got["moves"][0]["args"]["persistent_session_id"] == "session_EXAMPLEHELPER"
    assert "rebind job_round" in got["moves"][1]["run"]
    assert [a["id"] for a in got["archive"]] == [old]
    # The shortlist page goes up before its message.
    assert "app.py view" in _prompt("job_round.md")


# ------------------------------------------------------------------ the bar is the person's (X-18)


def test_no_bar_the_person_never_set_hides_anyone_or_anything(tmp_path, monkeypatch):
    """X-18: 'pay, prestige or signal' was one person's bar, applied to every stranger:
    unjudged employers refused, judged 'none' ones turned down and their follow-ups hidden,
    and the brief had a chat judge every employer each morning."""
    import bar
    import opportunity
    from network import surface
    monkeypatch.setattr(bar, "_judged_path", lambda: str(tmp_path / "employers_judged.json"))
    bar._judged_cache.clear()
    assert not bar.applies()                         # the example person states no bar
    assert surface.employer_out("Harborview Home Goods") == ""
    bar.judge("Riverside Community Food Bank", bar.NONE, "a local charity", today="2026-11-03")
    assert not bar.applies()                         # a judgement is not a bar
    assert surface.turned_down("Riverside Community Food Bank") == ""
    assert surface.employer_out("Riverside Community Food Bank") == ""
    assert bar.unjudged_contacts() == [] and "judge its pay" not in bar.verdict("Harborview")[1]
    # A hard rule the person did state still holds.
    assert bar.verdict("Saltmarsh Casino")[0] == bar.EXCLUDED
    # A person whose profile states a bar keeps it, judgements and all.
    monkeypatch.setattr(opportunity, "TIER_1", {"brindlecombe holdings"})
    assert bar.applies()
    assert "clears none" in surface.employer_out("Riverside Community Food Bank")
    assert "not judged against your bar yet" in surface.employer_out("Harborview Home Goods")
    bar._judged_cache.clear()
    assert "states no bar" in _prompt("job_round.md")
    import profile_upgrades
    u = profile_upgrades.by_id("bar-unstated")
    assert u.cost == "instant" and "lift" in u.command


# ------------------------------------------------------------------ setup and reset


def test_a_stranger_who_stops_after_the_page_goes_up_is_reminded_once(tmp_path, monkeypatch):
    """X-23: nothing was scheduled before setup's last step, so a stranger who answered nothing
    in the first sitting was never contacted again."""
    import app_listen
    import app_setup
    monkeypatch.setattr(routines, "has_page", lambda: True)
    monkeypatch.setattr(app_setup, "_finished", lambda: False)
    path = tmp_path / "routines.json"
    assert routines.remind_due(str(path))
    got = routines.remind_plan("example-owner", "my-job-search", chat=CHAT,
                               now=dt.datetime(2026, 11, 3, 14, 0, tzinfo=dt.timezone.utc))
    call = got["create_trigger"]
    assert call["run_once_at"] == "2026-11-04T14:00:00Z" and call["persistent_session_id"] == CHAT
    assert call["initiation"] == "own_initiative" and "create_new_session_on_fire" not in call
    assert not routines._is_brief_prompt(call["prompt"])        # never read as a second brief
    routines.reminded("trig_EXAMPLEREMIND", path=str(path))
    assert not routines.remind_due(str(path)) and routines.check(routines.load(str(path))) == []
    # The first publish prints it, while setup is unfinished.
    monkeypatch.setattr(routines, "remind_due", lambda path=None: True)
    monkeypatch.setattr(app_listen, "first_claim", lambda *a, **k: {"batches": []})
    monkeypatch.setattr(app_listen, "pin_asked", lambda: True)
    lines = app_listen.published_lines(PAGE, CHAT, True, str(tmp_path))
    assert any("routines.py remind" in ln for ln in lines)


def test_the_reminders_run_says_only_that_setup_waits_and_pushes_it(tmp_path):
    c = Copy(tmp_path)
    place = c.read("place.json")
    place["setup"] = {"started": "2026-11-03", "chat": CHAT}
    c.write("place.json", place)
    out = c.run("brief.py")
    message, claude = out.split("FOR CLAUDE", 1)
    assert message.strip() == ("Your job search setup is waiting for you on your page: %s. "
                               "Answer there, one question at a time; Claude does the rest." % PAGE)
    assert "PushNotification" in claude and "nothing to save" in claude


def test_after_a_reset_the_brief_turns_itself_off_and_says_so_once(tmp_path):
    """X-81: after /reset, every scheduled task kept running, replying 'No profile yet' into
    the old chat every morning."""
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "gone"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "brief.py")], cwd=ROOT,
                       env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.stdout.startswith("Your job search was reset, so its morning brief is off now.")
    assert "update_trigger, enabled false" in r.stdout and "this one included" in r.stdout
    with open(os.path.join(ROOT, ".claude", "commands", "reset.md"), encoding="utf-8") as fh:
        reset = fh.read()
    assert "list_triggers" in reset.split("### Profile reset", 1)[1].split("```", 1)[0]


# ------------------------------------------------------------------ what the brief says


def test_a_chat_only_brief_says_the_words_to_use_never_page_buttons():
    """X-68: 'Jobs, Find jobs' and 'Contacts, Find people' were said to people with no page."""
    three = brief._next_three([], {"applications": 0}, [], [], {}, "", "", False, [],
                              dt.date(2026, 11, 3), page=False)
    text = " ".join(three)
    assert "Jobs, Find jobs" not in text and "Contacts, Find people" not in text
    assert "say \"find me jobs\"" in text
    with_page = " ".join(brief._next_three([], {"applications": 0}, [], [], {}, "", "", False,
                                           [], dt.date(2026, 11, 3), page=True))
    assert "Jobs, Find jobs" in with_page


def test_the_first_brief_counts_from_setup_and_leads_with_it(tmp_path):
    """X-72: minutes after setup the brief opened 'Nothing has gone out in 14 days', counted
    from before the person began, and led with a question about a LinkedIn profile they may
    not have."""
    counts = {"processes": [], "applications": 0}
    day = dt.date(2026, 11, 3)
    assert brief._lead(counts, [], [], False, [], {}, day, day).startswith("Your search is set up.")
    assert brief._lead(counts, [], [], False, [], {}, day, dt.date(2026, 11, 1)).startswith(
        "Nothing has gone out in 2 days.")
    assert brief._lead(counts, [], [], False, [], {}, day, None).startswith(
        "Nothing has gone out in 14 days.")
    # No page: the chat's message then carries the Since line (with a page it is the
    # headline, the lead and the link, and the page shows the rest).
    c = Copy(tmp_path, page=False)
    place = c.read("place.json")
    place["setup"] = {"started": "2026-11-01", "finished": "2026-11-01"}
    c.write("place.json", place)
    out = c.run("brief.py", "--today", "2026-11-03")
    assert "Since 1 Nov:" in out
    # The own-profile question, with no LinkedIn address on file, asks whether there is one.
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(brief, "_linkedin_on_file", lambda: False)
    try:
        three = brief._next_three([], {"applications": 0}, [], [], {}, "",
                                  "own profile: \"Want me to look over your own LinkedIn profile "
                                  "once, for anything that would stop people replying?\"", False,
                                  [], day, page=True, new=True)
    finally:
        mp.undo()
    assert three[0].startswith("Find new jobs")
    assert three[1].startswith("If you have a LinkedIn profile")


def test_an_update_of_a_hundred_changes_is_counted_whole(tmp_path):
    """X-70: '... and 19 more' for an update that brought 103."""
    log = tmp_path / "sync.txt"
    log.write_text("date: 2026-11-03\nexit: 0\nearlier: \nsetup: \n---\nWhat changed:\n"
                   + "".join("  - Change %d\n" % i for i in range(20))
                   + "  ... and 83 more (CHANGELOG.md)\n", encoding="utf-8")
    got = brief.read_sync(dt.date(2026, 11, 3), str(log))
    assert len(got["changed"]) == 20 and got["more"] == 83


def test_a_profile_missing_a_setting_stops_the_brief_with_one_line_never_a_traceback(tmp_path):
    """X-39: a profile file missing a setting (a hand edit, a merge that dropped a line) broke
    every brief with a raw traceback, and nothing said which file."""
    c = Copy(tmp_path)
    with open(os.path.join(c.profile, "search.py"), "w", encoding="utf-8") as fh:
        fh.write('"""Emptied by a merge."""\n')
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "brief.py"), "--write"],
                       cwd=ROOT, env=c.env(), capture_output=True, text=True, encoding="utf-8",
                       timeout=180)
    assert r.returncode == 1 and "Traceback" not in r.stdout + r.stderr, r.stdout + r.stderr
    line = r.stdout.strip().splitlines()[-1]
    assert line.startswith("app: stopped: ") and "profile/search.py has no " in line
    assert "compare it with profile.example/" in line


def test_only_work_that_waited_a_day_is_named_as_not_saved(tmp_path, monkeypatch):
    """X-30: every branch a landing left waiting was named as not saved, every morning, though
    the next landing brings it in; the line never came true. Only work off master a day or
    more (land.stranded) is named, with the one line the start says too."""
    import land

    class Done:
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    monkeypatch.setattr(brief.subprocess, "run", lambda argv, **kw: Done(0))
    monkeypatch.setattr(land, "waiting", lambda root=None: ["origin/claude/an-hour-ago",
                                                            "origin/claude/three-days-ago"])
    monkeypatch.setattr(land, "stranded", lambda root=None, fetch=False: {
        "origin/claude/three-days-ago": 3}, raising=False)
    log = str(tmp_path / "sync.txt")
    monkeypatch.setenv("LJS_BRIEF_SYNC", log)
    brief.start(["--on", "a model"], "a model")
    got = brief.read_sync(dt.date.today(), log)
    assert got["earlier"] == ["origin/claude/three-days-ago"]
    lines = brief.claude_lines({"sync": got, "paused": "", "written": False, "write_here": [],
                                "profile_line": "", "queries": [], "since": "2026-11-01",
                                "skip_links": [], "what_counts": "x", "pack": "", "page": ""})
    said = next(ln for ln in lines if "three-days-ago" in ln)
    assert brief.UNSAVED_SAY in said and "_common.md step 3" not in said


def test_the_upkeep_says_what_it_did_and_runs_only_where_the_brief_does_not():
    """X-38: a silent run every day at 5am in her one chat, ending with an unexplained 'Done.'"""
    up = " ".join(_prompt("upkeep.md").split())
    assert '"Done." and nothing else' not in up and "Kept your search up to date" in up
    reg = {"timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": "CRON_TZ=Europe/London 38 7 * * 1-5", "prompt_file": routines.BRIEF_FILE}]}
    assert routines.upkeep_cron(reg).endswith(" * * 0,6")
