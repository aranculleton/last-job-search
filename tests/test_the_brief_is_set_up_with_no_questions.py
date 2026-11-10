"""The brief is made when the person turns it on, asking nothing, and never twice.

4.3 (the maintainer, 2026-10-29): it is opt-in from a bell on the Brief, every day by
default, and it runs in the chat that answers the page, so turning it on makes no chat.

From the setup audits (2026-10-25): a cloud chat could make the brief itself, its own chat
and a task bound to it, but the person was sent to a second chat to answer two questions;
`routines.py brief` crashed on the listing the account really returns ({"data": [...]})
and read a brief stored under another name as none, so a second one would have been made;
an empty listing read a stale registry entry as set up; and a registry with no task yet
failed every local check. Invented ids only.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import routines  # noqa: E402
import tips  # noqa: E402

STUB = routines.DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                    prompt_file=routines.BRIEF_FILE, relay_id="")
RAW = {"data": [{"id": "trig_EXAMPLEA", "name": "Mon/Thu summary",
                 "cron_expression": "CRON_TZ=Europe/London 56 7 * * 1,4", "enabled": True,
                 "persistent_session_id": "session_EXAMPLEA",
                 "derived_state": {"prompt": STUB}},
                {"id": "trig_EXAMPLEB", "name": "Something else", "enabled": True,
                 "derived_state": {"prompt": "Water the plants."}}],
       "has_more": True}
REG = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": "Job search: morning brief",
     "chat": {"title": "Job search: morning brief", "session_id": "session_EXAMPLEA", "own": True},
     "trigger_id": "trig_EXAMPLEA", "cron": "CRON_TZ=Europe/London 38 7 * * 1,4",
     "prompt_file": routines.BRIEF_FILE}]}


def test_the_raw_listing_is_read_and_a_brief_under_another_name_is_found():
    tasks, more = routines.listing(RAW)
    assert more is True and [t["id"] for t in tasks] == ["trig_EXAMPLEA", "trig_EXAMPLEB"]
    assert tasks[0]["prompt"] == STUB                       # from derived_state.prompt
    got = routines.existing_brief({}, tasks)
    assert got["state"] == "found" and got["id"] == "trig_EXAMPLEA"
    assert "never create a second" in got["say"]
    # The older shapes still read.
    assert routines.listing({"triggers": [{"id": "trig_X", "prompt": STUB}]})[0][0]["prompt"] == STUB
    assert routines.listing([{"id": "trig_X"}])[0][0]["id"] == "trig_X"


def test_an_empty_listing_is_a_listing_and_no_listing_is_the_registrys_word():
    assert routines.existing_brief(REG, [])["state"] == "ask"
    assert routines.existing_brief(REG, None)["state"] == "registered"
    assert routines.existing_brief({}, [])["state"] == "none"
    assert routines.existing_brief({}, None)["state"] == "none"


def test_a_brief_turned_off_or_failing_is_said_and_never_made_again():
    tasks, _ = routines.listing(RAW)
    off = [dict(tasks[0], enabled=False)]
    got = routines.existing_brief(REG, off)
    assert got["state"] == "registered" and "turned off" in got["say"]
    failed = [dict(tasks[0], last_run={"status": "FAILED", "fired_at": "2026-10-22T06:38:00Z"})]
    assert "failed" in routines.existing_brief(REG, failed)["say"]
    # Listed under a new id (made again by hand): the registry is told the id it has now.
    moved = [dict(tasks[0], id="trig_EXAMPLEC")]
    assert "lists it as trig_EXAMPLEC" in routines.existing_brief(REG, moved)["say"]


def test_a_brief_whose_chat_lost_the_files_is_said_and_given_a_chat_of_its_own():
    """The 07:56 brief fired in the chat it is bound to, which had been made again without
    the person's files, so it wrote nothing and sent nothing, and routines.py brief still
    said it was set up (the maintainer, 2026-11-04; the helper moved it into itself by hand).
    A task that fired after its time with no record of that day's brief, or that now wakes
    another chat, is said plainly, with the calls that give it a chat of its own, made with
    the copy attached, and one run there of the brief that did not come: never this chat,
    which may approve computer access and then run no scheduled task (2026-11-10)."""
    reg = dict(REG, routines=[dict(REG["routines"][0], made="2026-10-20",
                                   cron="CRON_TZ=Europe/London 56 7 * * *")])
    task = routines.listing(RAW)[0][0]
    ran = {"status": "SUCCEEDED", "fired_at": "2026-11-04T07:56:10Z",
           "session_id": "session_EXAMPLEA"}
    now = datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.timezone.utc)
    here = "session_EXAMPLEHELPER"

    def look(last_run, days, **more):
        return routines.existing_brief(reg, [dict(task, last_run=last_run, **more)], now=now,
                                       days_on_file=days, here=here,
                                       repo="example-owner/example-copy")
    got = look(ran, {"2026-11-03"})
    assert got["state"] == "lost" and "cannot open" in got["say"], got
    chat, make, once, record, old = got["calls"]
    assert chat["tool"] == "create_session"
    assert chat["args"]["source_url"] == "https://github.com/example-owner/example-copy"
    assert make["tool"] == "create_trigger" and \
        make["args"]["persistent_session_id"] == routines.NEW_CHAT
    assert make["args"]["cron_expression"] == "CRON_TZ=Europe/London 56 7 * * *"
    assert "example-owner/example-copy" in make["args"]["prompt"]   # it gets its files
    assert once["args"]["run_once_at"] == "2026-11-04T12:05:00Z"
    assert once["args"]["persistent_session_id"] == routines.NEW_CHAT
    assert f"record --session {routines.NEW_CHAT} --trigger" in record["run"]
    assert "--own-chat" in record["run"] and here not in json.dumps(got["calls"])
    assert old["tool"] == "update_trigger" and old["args"] == {"trigger_id": "trig_EXAMPLEA",
                                                              "enabled": False}
    assert "did not come" in got["then"] and got["tell"]
    # Today's record on file: it worked, and stays where it is.
    assert look(ran, {"2026-11-04"})["state"] == "registered"
    # Not fired yet today (the scheduler runs late) and still bound to its own chat: not lost.
    assert look(dict(ran, fired_at="2026-11-03T07:56:10Z"), {"2026-11-03"})["state"] == \
        "registered"
    # The task now wakes another chat than the one it was bound to: lost, fired or not.
    assert look(dict(ran, fired_at="2026-11-03T07:56:10Z"), {"2026-11-03"},
                session="session_EXAMPLEEMPTY")["state"] == "lost"


def test_the_brief_command_prints_the_move_for_a_brief_whose_chat_lost_the_files(tmp_path):
    """The same, on the real path: `routines.py brief --triggers <page> --chat <this chat>`
    in a cloud chat, with a task that fired just now and no brief on record since."""
    profile, state = tmp_path / "profile", tmp_path / "state"
    profile.mkdir()
    (state / "documents" / "briefs").mkdir(parents=True)
    reg = dict(REG, routines=[dict(
        REG["routines"][0], made="2026-01-01", cron="CRON_TZ=Europe/London 1 0 * * *")])
    (profile / "routines.json").write_text(json.dumps(reg), encoding="utf-8")
    fired = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    page = tmp_path / "page.json"
    page.write_text(json.dumps({"data": [dict(RAW["data"][0], last_run={
        "status": "SUCCEEDED", "fired_at": fired, "session_id": "session_EXAMPLEA"})],
        "has_more": False}), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=str(profile), LJS_STATE=str(state),
               CLAUDE_CODE_REMOTE="true")
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief",
                          "--triggers", str(page), "--chat", "session_EXAMPLEHELPER"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env=env)
    assert got.returncode == 0 and got.stdout.startswith("lost: "), got.stdout + got.stderr
    assert "move 1: create_session" in got.stdout and "move 2: create_trigger" in got.stdout
    assert "session_EXAMPLEHELPER" not in got.stdout
    assert '"enabled": false' in got.stdout and "morning_brief.md" in got.stdout
    assert "the brief is set up" not in got.stdout


def test_a_brief_in_a_chat_not_made_for_it_gets_one_of_its_own_never_set_up(tmp_path):
    """`routines.py brief` said the brief was set up while its task fired in the chat that
    had handed the page on (the maintainer's copy, 2026-11-05), and a brief bound to the chat
    that answers the page failed every morning once that chat approved computer access
    (2026-11-10). A brief in a chat not made for it, whichever chat that is, moves into a
    chat of its own, made with the copy attached."""
    tasks, _ = routines.listing(RAW)
    helper_bound = dict(REG, routines=[dict(REG["routines"][0],
                                            chat={"session_id": "session_EXAMPLEA"})])
    got = routines.existing_brief(helper_bound, tasks[:1], page="session_EXAMPLEHELPER",
                                  repo="example-owner/example-copy")
    assert got["state"] == "elsewhere" and "needs a chat of its own" in got["say"], got
    chat, make, record, old = got["calls"]
    assert chat["tool"] == "create_session" and chat["args"]["title"] == routines.BRIEF_NAME
    assert make["tool"] == "create_trigger" and \
        make["args"]["persistent_session_id"] == routines.NEW_CHAT
    assert f"record --session {routines.NEW_CHAT}" in record["run"] and "--own-chat" in record["run"]
    assert old["args"] == {"trigger_id": "trig_EXAMPLEA", "enabled": False}
    assert "list_triggers" in got["then"]
    # Already in a chat of its own: set up, nothing to move, whichever chat answers the page.
    assert routines.existing_brief(REG, tasks[:1], page="session_EXAMPLEHELPER")["state"] == \
        "registered"
    # Its own chat approved computer access: no scheduled run can open it, so a new one.
    trusted = routines.needs_own_chat(REG, REG["routines"][0], tasks[0], "session_EXAMPLEA")
    assert "computer access" in trusted
    # The older ops chat relays to the phone and keeps its brief.
    ops = dict(REG, setup="ops_relay", ops_session={"id": "session_EXAMPLEA"},
               routines=[{k: v for k, v in REG["routines"][0].items() if k != "chat"}])
    assert routines.existing_brief(ops, tasks[:1])["state"] == "registered"
    # A task the app moved to a fresh chat each run (no copy, no notifications) moves; a
    # routine the person made on the Routines screen, notifications on, stays.
    fresh = dict(REG, setup="routines_screen", routines=[
        {k: v for k, v in REG["routines"][0].items() if k != "chat"}])
    assert routines.existing_brief(fresh, [dict(tasks[0], session="")])["state"] == "elsewhere"
    theirs = json.loads(json.dumps(fresh))
    theirs["routines"][0]["notifications"] = {"push": True}
    assert routines.existing_brief(theirs, [dict(tasks[0], session="")])["state"] == "registered"
    # On the real path.
    profile, state = tmp_path / "profile", tmp_path / "state"
    profile.mkdir()
    state.mkdir()
    (profile / "routines.json").write_text(json.dumps(helper_bound), encoding="utf-8")
    listing = tmp_path / "page.json"
    listing.write_text(json.dumps({"data": RAW["data"][:1], "has_more": False}),
                       encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=str(profile), LJS_STATE=str(state),
               CLAUDE_CODE_REMOTE="true")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief",
                          "--triggers", str(listing)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env=env)
    assert out.returncode == 0 and out.stdout.startswith("elsewhere: "), out.stdout + out.stderr
    assert "move 1: create_session" in out.stdout and "move 2: create_trigger" in out.stdout
    assert "the brief is set up" not in out.stdout and "never create a second" not in out.stdout
    # Recorded, it is the brief's own chat, and the check is clean.
    path = profile / "routines.json"
    routines.record("session_EXAMPLENEWCHAT", "trig_EXAMPLENEW",
                    "CRON_TZ=Europe/London 38 7 * * 1,4", path=str(path), own_chat=True)
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg["routines"][0]["chat"] == {"session_id": "session_EXAMPLENEWCHAT",
                                          "title": routines.BRIEF_NAME, "own": True}
    assert routines.check(reg) == [] and routines.owns_chat(reg["routines"][0])
    # Out of a fresh chat each run, the registry becomes a chat set-up.
    path.write_text(json.dumps(fresh), encoding="utf-8")
    routines.record("session_EXAMPLENEWCHAT", "trig_EXAMPLENEW",
                    "CRON_TZ=Europe/London 38 7 * * 1,4", path=str(path), own_chat=True)
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg["setup"] == "chat_per_briefing" and routines.check(reg) == []


def test_a_registry_with_nothing_scheduled_yet_is_clean():
    assert routines.check({"setup": "chat_per_briefing", "timezone": "Europe/London",
                           "routines": []}) == []
    assert routines.check({"routines": []}) == []


def test_the_old_relay_needs_push_and_never_email():
    reg = {"timezone": "Europe/London",
           "ops_session": {"id": "session_EXAMPLE", "title": "Scheduled tasks"},
           "routines": [{"key": "relay", "name": "relay", "trigger_id": "trig_EXAMPLERELAY",
                         "mode": "fresh_session", "cron": None, "notifications": {"push": True},
                         "prompt_file": "automation/prompts/relay.md"},
                        {"key": "morning_brief", "name": "brief", "trigger_id": "trig_EXAMPLEB",
                         "mode": "ops_session", "cron": "CRON_TZ=Europe/London 56 7 * * *",
                         "prompt_file": routines.BRIEF_FILE}]}
    assert routines.check(reg) == []
    reg["routines"][0]["notifications"] = {"email": True}
    assert any("by push" in p for p in routines.check(reg))


def test_the_defaults_are_every_day_at_738_their_time():
    assert routines.brief_minute() == (7, 38)
    got = routines.default("America/Chicago")
    assert got["cron"] == "CRON_TZ=America/Chicago 38 7 * * *"
    assert got["when"] == "Every day at 7:38"
    # Where it comes, and in whose time: the page's Brief, or with no page, this chat (X-11).
    assert routines.default("America/Chicago", page=True)["say"] == (
        "Your brief is on: every day at 7:38, Chicago time, on your page's Brief. It comes a "
        "few minutes before the hour, when the service is less busy. Change it or turn it off "
        "from the bell there.")
    assert routines.default("America/Chicago", page=False)["say"] == (
        "Your morning brief comes to this chat every day at 7:38, Chicago time. It comes a few "
        "minutes before the hour, when the service is less busy. Say \"move my brief\" or "
        "\"stop my brief\" in any chat to change it.")
    # The app moved it off 8:00, and says so; what it stood for is kept beside the cron.
    assert routines.default("America/Chicago")["asked"] == "08:00"
    assert routines.default("")["cron"] == "" or routines.default("")["zone"]
    # Other day sets are said the way a person says them.
    assert routines.day_words([1, 2, 3, 4, 5]) == "Weekdays"
    assert routines.day_words([0, 6]) == "Weekends"
    assert routines.day_words([1, 3, 4]) == "Mondays, Wednesdays and Thursdays"
    assert routines._days("weekdays") == [1, 2, 3, 4, 5]
    assert routines._days("every day") == list(range(7))
    assert routines.read_cron("CRON_TZ=Europe/London 38 7 * * 1,4")["when"] == \
        "Mondays and Thursdays at 7:38"


def test_the_plan_gives_the_brief_a_chat_of_its_own_with_the_copy_attached(monkeypatch):
    """Bound to the chat that answers the page, the brief failed every morning once that chat
    approved computer access, and a fresh chat each run has no copy (the maintainer,
    2026-11-10): the plan makes the brief's own chat with create_session and the copy as its
    source, and binds the task and the first run to it, whichever chat asks."""
    monkeypatch.setenv("LJS_CHAT", "session_EXAMPLEHELPER")
    now = datetime.datetime(2026, 10, 25, 14, 0, tzinfo=datetime.timezone.utc)
    got = routines.plan("example-owner", "my-job-search", "Europe/London", now=now,
                        chat="session_EXAMPLEHELPER")
    assert got["create_session"] == {
        "title": "Job search: morning brief",
        "source_url": "https://github.com/example-owner/my-job-search",
        "prompt": routines.BRIEF_CHAT_PROMPT, "permission_mode": "auto"}
    assert "session_EXAMPLEHELPER" not in json.dumps(got)
    task = got["create_trigger"]
    assert task["persistent_session_id"] == routines.NEW_CHAT
    assert task["cron_expression"] == "CRON_TZ=Europe/London 38 7 * * *"
    # The brief runs in any chat it lands in: where its chat is gone and the task wakes a new,
    # empty one, the prompt says how to get this copy first (2026-10-31).
    assert task["prompt"] == routines.with_copy(STUB, "example-owner/my-job-search") and "connectors" not in task
    assert "add_repo (owner example-owner, repo my-job-search, access push)" in task["prompt"]
    assert routines._is_brief_prompt(task["prompt"])
    assert task["initiation"] == "human_request"
    first = got["first_brief"]
    assert first["run_once_at"] == "2026-10-25T14:05:00Z" and "connectors" not in first
    assert first["persistent_session_id"] == routines.NEW_CHAT
    assert f"--session {routines.NEW_CHAT}" in got["record"] and "--own-chat" in got["record"]
    assert "in the chat called" not in got["say"]
    assert "fire_trigger" not in json.dumps(got)


def test_a_chat_on_the_computer_points_at_the_bell_and_makes_nothing(tmp_path):
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile"), CLAUDECODE="1")
    env.pop("CLAUDE_CODE_REMOTE", None)
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert got.returncode == 0 and "tell them: " + routines.BRIEF_BELL in got.stdout
    for made in ("create_trigger", "create_session", "RemoteTrigger", "New task"):
        assert made not in got.stdout, made


def test_what_was_made_is_recorded_and_passes_the_check(tmp_path):
    path = tmp_path / "routines.json"
    path.write_text(json.dumps({"setup": "chat_per_briefing", "timezone": "Europe/London",
                                "routines": [
                                    {"key": "job_round", "name": "Job search: shortlist",
                                     "chat": {"title": "Job search: shortlist",
                                              "session_id": "session_EXAMPLEROUND"},
                                     "trigger_id": "trig_EXAMPLEROUND",
                                     "cron": "CRON_TZ=Europe/London 52 6 * * 1,4",
                                     "prompt_file": "automation/prompts/job_round.md"}]}),
                    encoding="utf-8")
    routines.record("session_EXAMPLENEW", "trig_EXAMPLENEW",
                    "CRON_TZ=Europe/London 38 7 * * 1,4", path=str(path),
                    title="Job search: morning brief")
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert routines.check(reg) == []
    assert [r["key"] for r in reg["routines"]] == ["morning_brief", "job_round"]
    brief = reg["routines"][0]
    assert brief["trigger_id"] == "trig_EXAMPLENEW"
    assert brief["chat"] == {"title": "Job search: morning brief", "session_id": "session_EXAMPLENEW"}
    # Bound to the chat that answers the page, it is that chat's id alone.
    routines.record("session_EXAMPLEHELPER", "trig_EXAMPLENEW",
                    "CRON_TZ=Europe/London 38 7 * * *", path=str(path))
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg["routines"][0]["chat"] == {"session_id": "session_EXAMPLEHELPER"}
    # Recording it again replaces it, never a second brief.
    routines.record("session_EXAMPLENEW", "trig_EXAMPLEOTHER",
                    "CRON_TZ=Europe/London 38 7 * * 1,4", path=str(path))
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert [r["trigger_id"] for r in reg["routines"] if r["key"] == "morning_brief"] == \
        ["trig_EXAMPLEOTHER"]


def _brief_cli(tmp_path, *args, remote=True):
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile"))
    env.pop("CLAUDE_CODE_REMOTE", None)
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief",
                           *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def test_in_a_cloud_chat_it_lists_first_and_never_plans_blind(tmp_path):
    got = _brief_cli(tmp_path)
    assert got.returncode == 0 and "list the account's scheduled tasks first" in got.stdout
    assert "create_session" not in got.stdout


def test_in_a_cloud_chat_with_none_it_prints_the_calls_once_the_zone_is_known(tmp_path):
    empty = tmp_path / "page.json"
    empty.write_text(json.dumps({"data": [], "has_more": False}), encoding="utf-8")
    got = _brief_cli(tmp_path, "--triggers", str(empty))
    # No profile, so no zone: it says so rather than make a task that fires in UTC.
    assert got.returncode == 1 and "names no time zone" in got.stdout
    assert "create_trigger" not in got.stdout
    found = tmp_path / "found.json"
    found.write_text(json.dumps(RAW), encoding="utf-8")
    got = _brief_cli(tmp_path, "--triggers", str(found))
    assert got.stdout.startswith("found:") and "another page" in got.stdout


def test_the_first_brief_tip_promises_no_day_it_does_not_run():
    assert "tomorrow" not in tips.FIRST["brief"]


def test_employer_boards_are_looked_for_before_the_profile_exists(tmp_path):
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile"))
    got = subprocess.run([sys.executable, "-c",
                          "import sys; sys.path.insert(0, 'tools'); import ats_boards as a; "
                          "print(a.NO_PROFILE); print('\\n'.join(a._find_lines('Larkspur', "
                          "[{'kind': 'greenhouse', 'token': 'larkspur', 'in_range': 3, "
                          "'why': None, 'how': 'guessed', 'open': 3, 'titles': []}])))"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert got.returncode == 0, got.stderr
    assert got.stdout.startswith("True\ngreenhouse/larkspur: 3 open (no profile yet")


_FIND_NO_PROFILE = r'''
import sys
sys.path.insert(0, "tools")
import ats_boards as a
from offline_boards import offline
with offline() as web:
    wd = "acme.wd3.myworkdayjobs.com/wday/cxs/acme/External/jobs"
    web.routes[wd] = {"total": 2, "facets": [], "jobPostings": [
        {"title": "Supply Chain Analyst", "externalPath": "/job/Leeds/Supply-Chain-Analyst_R1",
         "locationsText": "Leeds", "postedOn": "Posted Today"},
        {"title": "Demand Planner", "externalPath": "/job/York/Demand-Planner_R2",
         "locationsText": "2 Locations", "postedOn": "Posted Today"}]}
    host = "careers.acme.example"
    web.robots[host] = (200, "User-agent: *\nAllow: /\n")
    web.routes[host + "/sitemap.xml"] = ("<urlset><url><loc>https://" + host + "/job/1/analyst"
                                         "</loc></url></urlset>", None)
    web.routes["/job/1/"] = ('<script type="application/ld+json">{"@type": "JobPosting", '
                             '"title": "Analyst", "jobLocation": {"address": '
                             '{"addressLocality": "Leeds"}}}</script>', None)
    for target in ("https://acme.wd3.myworkdayjobs.com/External", "careersite:" + host):
        print("\n".join(a._find_lines("Acme", a.find(target))))
    print("bodies asked:", sum("/job/Leeds" in u or "/job/York" in u for u, _ in web.calls))
'''


def test_a_workday_board_or_a_careers_site_is_found_before_the_profile_exists(tmp_path):
    """--find on a Workday board or a careers site read the round's title variants, which
    read the profile, and crashed with no profile: the case the fallback above is for."""
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile"))
    got = subprocess.run([sys.executable, "-c", _FIND_NO_PROFILE], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env=env)
    assert got.returncode == 0, got.stderr
    lines = got.stdout.splitlines()
    assert "workday/acme.wd3/External: 2 open (no profile yet, so none judged in range)" in lines
    assert any(x.startswith("careersite/") and ": 1 open (no profile yet" in x for x in lines)
    assert "bodies asked: 0" in lines            # nothing can be judged, so no body is fetched


def test_no_scheduled_task_the_app_prints_carries_a_connectors_field():
    """Some organisations refuse create_trigger's `connectors` field outright ("not available
    for this organization"), so a printed call that carried `"connectors": []` failed as
    written (the maintainer's copy, 2026-11-05). The app connects nothing, so it never needs
    the field: no tool spells it into a call."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import repo_files
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found = []
    for path in map(str, repo_files.files("tools/**/*.py")):
        if os.sep + "openroles" + os.sep in path:
            continue
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if '"connectors"' in line or "'connectors'" in line:
                    found.append(f"{os.path.relpath(path, root)}:{n}")
    assert found == []
