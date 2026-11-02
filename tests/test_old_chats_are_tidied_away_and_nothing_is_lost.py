"""The app's own old chats are archived by themselves; nothing the person made is touched.

The maintainer, 2026-10-29: installs that updated through several versions carry a chat for
the brief, a job round chat, helpers that were replaced and child chats for long work, and
the person should not have to do anything about them, nor lose anything in them. tools/tidy.py
decides; the chat that answers the page makes the calls. Every id, title and name here is
invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import routines  # noqa: E402
import tidy  # noqa: E402

TODAY = dt.date(2026, 10, 29)
REPO = "example-owner/my-job-search"
OLD = "2026-10-20T08:00:00Z"
HELPER = "session_EXAMPLEHELPER"


def chat(sid, title, updated=OLD, status="SESSION_STATUS_IDLE", bucket="SESSION_STATUS_BUCKET_REVIEW_READY"):
    return {"id": sid, "title": title, "session_status": status, "status_bucket": bucket,
            "created_at": "2026-10-01T08:00:00Z", "updated_at": updated}


def detail(sid, repo=REPO, branch=""):
    return {"id": sid, "session_context": {
        "sources": [{"git_repository": {"url": f"https://github.com/{repo}"}}],
        "outcomes": [{"git_repository": {"git_info": {"repo": repo, "branches": [branch] if branch else []}}}]}}


REG = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": "trig_EXAMPLEBRIEF",
     "cron": "CRON_TZ=Europe/London 38 7 * * 1,4", "prompt_file": routines.BRIEF_FILE,
     "chat": {"title": "Job search: morning brief", "session_id": "session_EXAMPLEBRIEFCHAT"}},
    {"key": "job_round", "name": "Job search: shortlist", "trigger_id": "trig_EXAMPLEROUND",
     "cron": "CRON_TZ=Europe/London 52 6 * * 1,4", "prompt_file": "automation/prompts/job_round.md",
     "chat": {"title": "Job search: shortlist", "session_id": "session_EXAMPLEROUNDCHAT"}}]}
TRIGGERS = [{"id": "trig_EXAMPLEBRIEF", "session": "session_EXAMPLEBRIEFCHAT", "enabled": True},
            {"id": "trig_EXAMPLEROUND", "session": "session_EXAMPLEROUNDCHAT", "enabled": True}]
CHATS = [
    chat(HELPER, "Job search helper"),                                  # answers the page
    chat("session_EXAMPLEOLDHELPER", "Job search helper setup"),        # the one before it
    chat("session_EXAMPLEBRIEFCHAT", "Job search: morning brief"),      # brief in its own chat
    chat("session_EXAMPLEROUNDCHAT", "Job search: shortlist"),          # job round, still on
    chat("session_EXAMPLEDRAFTS", "Job search: drafts"),                # a child chat, finished
    chat("session_EXAMPLEUNSAVED", "Job search: searches"),             # its branch not on master
    chat("session_EXAMPLEFRESH", "Job search: research", updated="2026-10-28T20:00:00Z"),
    chat("session_EXAMPLEOTHERCOPY", "Job search: drafts"),             # another copy's chat
    chat("session_EXAMPLEOWN", "Last job search with Robin"),           # the person's own chat
    chat("session_EXAMPLECAMPAIGN", "Job search: Quillon campaign"),    # a live process
    chat("session_EXAMPLEBLOCKED", "Job search: drafts", updated="2026-10-25T08:00:00Z",
         status="SESSION_STATUS_REQUIRES_ACTION", bucket="SESSION_STATUS_BUCKET_BLOCKED"),
]
INFO = {c["id"]: detail(c["id"]) for c in CHATS}
INFO["session_EXAMPLEUNSAVED"] = detail("session_EXAMPLEUNSAVED", branch="claude/searches-x1")
INFO["session_EXAMPLEOTHERCOPY"] = detail("session_EXAMPLEOTHERCOPY", repo="example-owner/another-copy")
LISTENER = {"chat": HELPER, "took_from": "session_EXAMPLEOLDHELPER"}


def _plan(**kw):
    args = dict(chats=CHATS, triggers=TRIGGERS, info=INFO, reg=REG, listener=LISTENER,
                this_chat=HELPER, repo=REPO, today=TODAY, campaigns={"session_EXAMPLECAMPAIGN"},
                branches={"claude/searches-x1"}, done_before=set())
    args.update(kw)
    return tidy.plan(**args)


def test_only_the_apps_finished_chats_are_archived():
    got = _plan()
    assert got["ask"] == []
    assert {c["id"] for c in got["archive"]} == {
        "session_EXAMPLEOLDHELPER", "session_EXAMPLEBRIEFCHAT", "session_EXAMPLEDRAFTS"}
    why = {c["id"]: c["why"] for c in got["keep"]}
    assert why[HELPER] == "it answers the page"
    assert why["session_EXAMPLEROUNDCHAT"] == "a scheduled task that is on runs in it"
    assert why["session_EXAMPLEUNSAVED"].startswith("its work is not on master yet")
    assert why["session_EXAMPLEFRESH"].startswith("used ")
    assert why["session_EXAMPLEOTHERCOPY"] == "it works on another copy"
    assert why["session_EXAMPLECAMPAIGN"] == "a live process has its own chat here"
    assert why["session_EXAMPLEBLOCKED"].startswith("used ")      # waiting on them: a week
    # The person's own chat is never even listed.
    assert "session_EXAMPLEOWN" not in why and all(c["id"] != "session_EXAMPLEOWN" for c in got["archive"])


def test_the_brief_moves_into_the_helper_before_its_chat_is_archived():
    got = _plan()
    calls = got["brief"]
    assert [c.get("tool") or "run" for c in calls] == ["create_trigger", "run", "update_trigger"]
    new = calls[0]["args"]
    assert new["persistent_session_id"] == HELPER
    assert new["cron_expression"] == "CRON_TZ=Europe/London 38 7 * * 1,4"   # their own days kept
    # With the line that gets the files where the chat has none (routines.with_copy).
    assert new["prompt"] == routines.with_copy(routines.stub(REG, "morning_brief"), REPO)
    assert new["connectors"] == []
    assert "--session " + HELPER in calls[1]["run"]
    assert calls[2]["args"] == {"trigger_id": "trig_EXAMPLEBRIEF", "enabled": False}  # off, kept
    assert "delete_trigger" not in json.dumps(got)


def test_the_brief_stays_put_when_off_resting_unknown_or_in_a_chat_they_named():
    off = json.loads(json.dumps(REG))
    off["routines"][0]["off"] = True
    assert _plan(reg=off)["brief"] == []
    rest = dict(REG, pause={"until": "2026-11-08", "since": "2026-10-25"})
    assert _plan(reg=rest)["brief"] == []
    # Bound to the person's own chat ("set up my brief in this chat"): never moved.
    own = json.loads(json.dumps(REG))
    own["routines"][0]["chat"]["session_id"] = "session_EXAMPLEOWN"
    trig = [dict(TRIGGERS[0], session="session_EXAMPLEOWN"), TRIGGERS[1]]
    got = _plan(reg=own, triggers=trig)
    assert got["brief"] == [] and all(c["id"] != "session_EXAMPLEOWN" for c in got["archive"])
    # Its chat cannot be shown to be on this copy: kept, and the brief with it.
    info = dict(INFO)
    info.pop("session_EXAMPLEBRIEFCHAT")
    assert _plan(info=info)["brief"] == []


def test_an_older_ops_chat_and_a_routine_are_never_rebuilt():
    ops = {"timezone": "Europe/London", "setup": "ops_relay",
           "ops_session": {"id": "session_EXAMPLEOPS", "title": "Scheduled tasks"},
           "routines": [{"key": "morning_brief", "name": "brief", "trigger_id": "trig_EXAMPLEB",
                         "mode": "ops_session", "cron": "CRON_TZ=Europe/London 56 7 * * *",
                         "prompt_file": routines.BRIEF_FILE}]}
    chats = CHATS + [chat("session_EXAMPLEOPS", "Job search: scheduled tasks")]
    info = dict(INFO, session_EXAMPLEOPS=detail("session_EXAMPLEOPS"))
    got = _plan(reg=ops, chats=chats, info=info)
    assert got["brief"] == []
    assert any(k["id"] == "session_EXAMPLEOPS" and "never rebuilt" in k["why"] for k in got["keep"])


def test_chats_it_cannot_judge_yet_are_read_first_and_git_trouble_keeps_them():
    got = _plan(info={})
    assert "session_EXAMPLEDRAFTS" in got["ask"] and got["archive"] == []
    got = _plan(branches=None)
    assert any(k["id"] == "session_EXAMPLEUNSAVED" and "git could not say" in k["why"]
               for k in got["keep"])
    # Once tidied, never listed again (brought back on purpose stays back).
    got = _plan(done_before={"session_EXAMPLEDRAFTS"})
    assert all(c["id"] != "session_EXAMPLEDRAFTS" for c in got["archive"] + got["keep"])


def test_the_listing_shapes_the_tools_return_are_read():
    page = {"ccr": {"data": CHATS[:2], "has_more": True}}
    assert [s["id"] for s in tidy.sessions([page])] == [HELPER, "session_EXAMPLEOLDHELPER"]
    assert tidy.details([{"ccr": INFO[HELPER]}]) == {HELPER: INFO[HELPER]}
    assert tidy._repo_of(INFO[HELPER]) == REPO.lower()
    assert tidy._branches_of(INFO["session_EXAMPLEUNSAVED"]) == ["claude/searches-x1"]


def test_done_records_what_went_and_undo_brings_it_all_back(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    prof.mkdir()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    env = dict(os.environ, LJS_STATE=str(tmp_path), LJS_PROFILE=str(prof))
    run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tidy.py"), *a],  # noqa: E731
                                    capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(tmp_path))
    assert run("due", "--today", "2026-10-29").returncode == 0
    out = run("done", "session_EXAMPLEDRAFTS", "--titles", '{"session_EXAMPLEDRAFTS": "Job search: drafts"}',
              "--today", "2026-10-29")
    assert "tidied away 1 old chat it no longer used. Nothing in them was lost" in out.stdout, out.stderr
    assert run("due", "--today", "2026-10-29").returncode == 1        # once a day
    assert run("due", "--today", "2026-10-30").returncode == 0
    rec = json.loads((prof / "tidy.json").read_text(encoding="utf-8"))
    assert rec["archived"] == [{"id": "session_EXAMPLEDRAFTS", "title": "Job search: drafts", "on": "2026-10-29"}]
    back = run("undo").stdout
    assert 'unarchive_session {"session_id": "session_EXAMPLEDRAFTS"}' in back


def test_a_brief_whose_chat_was_deleted_moves_to_the_helper():
    gone = [c for c in CHATS if c["id"] != "session_EXAMPLEBRIEFCHAT"]
    got = _plan(chats=gone)
    assert [c.get("tool") or "run" for c in got["brief"]] == ["create_trigger", "run", "update_trigger"]
    assert got["brief"][0]["args"]["persistent_session_id"] == HELPER
    assert all(c["id"] != "session_EXAMPLEBRIEFCHAT" for c in got["archive"])


# The older ops set-up: every task fires into one ops chat. Once that chat is gone, the task
# wakes a new empty chat with no copy of the files each morning (2026-10-31: "Morning brief
# could not start: no git repo in this session"), so the daily tidy-up moves the brief.
OPS = {"timezone": "Europe/London",
       "ops_session": {"id": "session_EXAMPLEOPS", "title": "Scheduled tasks"},
       "stub": "Scheduled run: {label}. You are in the ops session. Read `"
               + routines.COMMON + "` and `{prompt_file}`; else relay {relay_id}.",
       "routines": [
           {"key": "relay", "name": "Job search: deliver to phone", "trigger_id": "trig_EXAMPLERELAY",
            "mode": "fresh_session", "cron": None, "notifications": {"push": True},
            "prompt_file": "automation/prompts/relay.md"},
           {"key": "morning_brief", "name": "Job search: brief (daily)", "trigger_id": "trig_EXAMPLEB",
            "mode": "ops_session", "cron": "CRON_TZ=Europe/London 56 7 * * *",
            "prompt_file": routines.BRIEF_FILE},
           {"key": "job_round", "name": "Job search: job round", "trigger_id": "trig_EXAMPLER",
            "mode": "ops_session", "cron": "CRON_TZ=Europe/London 52 6 * * 1,4",
            "prompt_file": "automation/prompts/job_round.md"}]}


def test_an_ops_brief_whose_chat_is_gone_moves_to_the_helper():
    woke = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEEMPTY", "enabled": True}]
    got = _plan(reg=OPS, triggers=woke)
    assert [c.get("tool") or "run" for c in got["brief"]] == ["create_trigger", "run", "update_trigger"]
    new = got["brief"][0]["args"]
    assert new["persistent_session_id"] == HELPER
    assert new["cron_expression"] == "CRON_TZ=Europe/London 56 7 * * *"
    # The plain stub: the moved brief is not told it is in the ops chat, nor to relay; it
    # says how to get the files where the chat has none.
    assert new["prompt"] == routines.with_copy(routines.DEFAULT_STUB.format(
        label="morning brief", Label="Morning brief", prompt_file=routines.BRIEF_FILE, relay_id=""), REPO)
    assert "ops session" not in new["prompt"] and "add_repo (owner example-owner, repo my-job-search" in new["prompt"]
    assert got["brief"][2]["args"] == {"trigger_id": "trig_EXAMPLEB", "enabled": False}
    assert any(k["id"] == "session_EXAMPLEOPS" and "gone" in k["why"] for k in got["keep"])
    assert all(c["id"] != "session_EXAMPLEEMPTY" for c in got["archive"])


def test_an_ops_brief_stays_while_its_chat_may_still_be_there():
    # Listed: it relays to the phone, so it stays (and is never archived).
    live = chat("session_EXAMPLEOPS", "Job search: scheduled tasks")
    on_ops = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEOPS", "enabled": True}]
    got = _plan(reg=OPS, triggers=on_ops, chats=CHATS + [live],
                info=dict(INFO, session_EXAMPLEOPS=detail("session_EXAMPLEOPS")))
    assert got["brief"] == []
    assert all(c["id"] != "session_EXAMPLEOPS" for c in got["archive"])
    # Missing from the listing (a page not read) but the task still names it: not moved.
    assert _plan(reg=OPS, triggers=on_ops)["brief"] == []
    # The task does not say where it runs: not moved.
    assert _plan(reg=OPS, triggers=[{"id": "trig_EXAMPLEB", "session": "", "enabled": True}])["brief"] == []
    # Turned off, or resting on a break: not moved.
    off = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEEMPTY", "enabled": False}]
    assert _plan(reg=OPS, triggers=off)["brief"] == []
    rest = dict(OPS, pause={"until": "2026-11-08"})
    woke = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEEMPTY", "enabled": True}]
    assert _plan(reg=rest, triggers=woke)["brief"] == []


def test_the_moved_ops_brief_is_recorded_and_the_registry_stays_an_ops_one(tmp_path):
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(OPS), encoding="utf-8")
    # A chat recording a re-listed id with its own id: the brief still fires in the ops chat,
    # so it names no chat of its own and keeps the relay to the phone.
    routines.record(HELPER, "trig_EXAMPLEB", "CRON_TZ=Europe/London 56 7 * * *", path=str(path))
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert "chat" not in next(r for r in reg["routines"] if r["key"] == "morning_brief")
    assert routines.setup_of(reg) == "ops_relay" and reg["setup"] == "ops_relay"
    # The move out of a lost ops chat (tidy's run line carries --own-chat).
    move = _plan(reg=OPS, triggers=[{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEEMPTY",
                                     "enabled": True}])["brief"][1]["run"]
    assert move.endswith(" --own-chat")
    routines.record(HELPER, "trig_EXAMPLENEW", "CRON_TZ=Europe/London 56 7 * * *", path=str(path),
                    own_chat=True)
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert routines.setup_of(reg) == "ops_relay" and routines.check(reg) == []
    brief = next(r for r in reg["routines"] if r["key"] == "morning_brief")
    assert brief["trigger_id"] == "trig_EXAMPLENEW" and brief["chat"] == {"session_id": HELPER}
    assert "mode" not in brief
    # Its stub from now on is the plain one; the job round, still in the ops chat, keeps the
    # registry's own.
    assert "ops session" not in routines.stub(reg, "morning_brief")
    assert "ops session" in routines.stub(reg, "job_round")
    # Brought back into the ops chat itself, it names no chat of its own.
    routines.record("session_EXAMPLEOPS", "trig_EXAMPLEB", "CRON_TZ=Europe/London 56 7 * * *",
                    path=str(path))
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert "chat" not in next(r for r in reg["routines"] if r["key"] == "morning_brief")


def test_an_ops_brief_back_from_a_break_runs_in_the_ops_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))   # read only
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(OPS), encoding="utf-8")
    routines.pause("2026-11-08", today="2026-10-31", path=str(path))
    back = next(c for c in routines.calls(str(path)) if c.get("for") == "back")["args"]
    # Never a new chat on firing: it would have no copy of the files.
    assert back["persistent_session_id"] == "session_EXAMPLEOPS"
    assert "create_new_session_on_fire" not in back


def test_an_ops_brief_bound_to_a_chat_with_a_copy_is_never_moved():
    # The ops chat is gone, but the task names a chat on this copy (the person's own, made
    # when they rebuilt it themselves): it runs there, so it stays.
    own = chat("session_EXAMPLEOWN", "Last job search with Robin")
    bound = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEOWN", "enabled": True}]
    got = _plan(reg=OPS, triggers=bound)
    assert got["brief"] == [] and own in CHATS
    # Bound to the chat that answers the page already: nothing to make.
    assert _plan(reg=OPS, triggers=[dict(bound[0], session=HELPER)])["brief"] == []
    # A listed chat that works on no copy is the empty one it woke: moved.
    empty = chat("session_EXAMPLEEMPTY", "Job search: brief (daily)", updated="2026-10-29T08:00:00Z")
    woke = [dict(bound[0], session="session_EXAMPLEEMPTY")]
    info = dict(INFO, session_EXAMPLEEMPTY={"id": "session_EXAMPLEEMPTY", "session_context": {}})
    got = _plan(reg=OPS, triggers=woke, chats=CHATS + [empty], info=info)
    assert got["brief"][0]["args"]["persistent_session_id"] == HELPER
    # Not read yet: read first, nothing moved meanwhile.
    got = _plan(reg=OPS, triggers=woke, chats=CHATS + [empty])
    assert got["ask"] == ["session_EXAMPLEEMPTY"] and got["brief"] == []


def test_a_moved_ops_brief_follows_a_new_helper():
    moved = json.loads(json.dumps(OPS))
    brief = next(r for r in moved["routines"] if r["key"] == "morning_brief")
    brief.pop("mode")
    brief["chat"] = {"session_id": "session_EXAMPLEOLDHELPER"}
    on_old = [{"id": "trig_EXAMPLEB", "session": "session_EXAMPLEOLDHELPER", "enabled": True}]
    got = _plan(reg=moved, triggers=on_old)
    assert got["brief"][0]["args"]["persistent_session_id"] == HELPER
    assert any(c["id"] == "session_EXAMPLEOLDHELPER" and "brief moved" in c["why"]
               for c in got["archive"])


def test_moving_to_another_zone_owes_an_update_for_every_task(tmp_path):
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(dict(OPS, setup="ops_relay")), encoding="utf-8")
    got = routines.move(zone="America/Toronto", path=str(path))
    ids = sorted(c["args"]["trigger_id"] for c in got["calls"] if c["tool"] == "update_trigger")
    assert ids == ["trig_EXAMPLEB", "trig_EXAMPLER"]


def test_a_brief_that_stays_put_is_given_the_line_that_gets_its_files():
    """A brief whose chat was deleted woke a new, empty chat each morning and could only say
    it could not start: no brief for two days (the maintainer, 2026-10-31). Its stored prompt
    now says how to get the files, so it runs in any chat it lands in; one stored before that
    is given the line by the day's tidy-up, once."""
    old = routines.DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                       prompt_file=routines.BRIEF_FILE, relay_id="")
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": "trig_EXAMPLEBRIEF",
         "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE}]}
    live = [{"id": "trig_EXAMPLEBRIEF", "session": HELPER, "enabled": True, "prompt": old}]
    got = _plan(reg=reg, triggers=live)
    assert got["brief"] == [{"tool": "update_trigger", "why": got["brief"][0]["why"],
                             "args": {"trigger_id": "trig_EXAMPLEBRIEF",
                                      "prompt": routines.with_copy(old, REPO)}}]
    fixed = got["brief"][0]["args"]["prompt"]
    assert fixed.startswith("Scheduled run: morning brief. If this chat has no copy of example-owner/my-job-search ")
    assert routines._is_brief_prompt(fixed), "still found as the brief"
    # Once: a prompt with the line, a brief turned off or resting, is left alone.
    assert _plan(reg=reg, triggers=[dict(live[0], prompt=fixed)])["brief"] == []
    assert _plan(reg=reg, triggers=[dict(live[0], enabled=False)])["brief"] == []
    assert _plan(reg=dict(reg, pause={"until": "2026-11-09"}), triggers=live)["brief"] == []
    # Never a copy it cannot name.
    assert routines.with_copy(old, "") == old and routines.with_copy(old, "not a repo") == old


DAILY = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": "trig_EXAMPLEDAILY",
     "cron": "CRON_TZ=Europe/London 56 7 * * *", "prompt_file": routines.BRIEF_FILE,
     "chat": {"session_id": HELPER}}]}
LIVE_DAILY = [{"id": "trig_EXAMPLEDAILY", "session": HELPER, "enabled": True,
               "prompt": routines.with_copy(routines.stub(DAILY, "morning_brief"), REPO)}]


def test_a_copy_with_no_daily_brief_gets_a_silent_daily_upkeep_bound_to_the_helper():
    """Only a chat takes the app's updates and writes the page's data, and a page wakes a chat
    only from a tap: a person who opens only their page had nothing kept current (the
    maintainer, 2026-11-02). Where the brief does not run every day, a silent task does it."""
    got = _plan()                                  # a brief on Mondays and Thursdays only
    up = got["upkeep"]
    assert [c.get("tool") or "run" for c in up] == ["create_trigger", "run"]
    new = up[0]["args"]
    assert new["name"] == routines.UPKEEP_NAME and new["persistent_session_id"] == HELPER
    assert new["cron_expression"].startswith("CRON_TZ=Europe/London ") and new["cron_expression"].endswith(" * * *")
    assert routines.at_most_daily(new["cron_expression"]) and new["connectors"] == []
    assert "automation/prompts/upkeep.md" in new["prompt"] and "add_repo (owner example-owner" in new["prompt"]
    assert "upkeep-record --session " + HELPER in up[1]["run"]
    # None at all yet (no brief ever set up): the upkeep is made too.
    assert [c.get("tool") or "run" for c in _plan(reg={})["upkeep"]] == ["create_trigger", "run"]


def test_a_daily_brief_needs_no_upkeep_and_one_made_before_is_taken_away():
    assert _plan(reg=DAILY, triggers=LIVE_DAILY)["upkeep"] == []
    with_up = json.loads(json.dumps(DAILY))
    with_up["routines"].append({"key": "upkeep", "name": routines.UPKEEP_NAME, "trigger_id": "trig_EXAMPLEUP",
                                "cron": "CRON_TZ=Europe/London 39 5 * * *", "prompt_file": routines.UPKEEP_FILE,
                                "chat": {"session_id": HELPER}})
    got = _plan(reg=with_up, triggers=LIVE_DAILY + [{"id": "trig_EXAMPLEUP", "session": HELPER, "enabled": True}])
    assert [c.get("tool") or "run" for c in got["upkeep"]] == ["delete_trigger", "run"]
    assert got["upkeep"][0]["args"] == {"trigger_id": "trig_EXAMPLEUP"} and "upkeep-forget" in got["upkeep"][1]["run"]


def test_the_upkeep_follows_a_renewed_helper_and_its_old_copy_is_deleted_not_piled_up():
    reg = json.loads(json.dumps(REG))
    reg["routines"].append({"key": "upkeep", "name": routines.UPKEEP_NAME, "trigger_id": "trig_EXAMPLEUP",
                            "cron": "CRON_TZ=Europe/London 39 5 * * *", "prompt_file": routines.UPKEEP_FILE,
                            "chat": {"session_id": "session_EXAMPLEOLDHELPER"}})
    trig = TRIGGERS + [{"id": "trig_EXAMPLEUP", "session": "session_EXAMPLEOLDHELPER", "enabled": True}]
    got = _plan(reg=reg, triggers=trig)["upkeep"]
    assert [c.get("tool") or "run" for c in got] == ["create_trigger", "run", "delete_trigger"]
    assert got[0]["args"]["persistent_session_id"] == HELPER and got[0]["args"]["cron_expression"] == "CRON_TZ=Europe/London 39 5 * * *"
    assert got[2]["args"] == {"trigger_id": "trig_EXAMPLEUP"}
    # Bound to the helper already, and on: nothing to do.
    reg["routines"][-1]["chat"] = {"session_id": HELPER}
    trig[-1] = dict(trig[-1], session=HELPER)
    assert _plan(reg=reg, triggers=trig)["upkeep"] == []


def test_a_brief_moved_off_the_helper_this_one_replaced_is_deleted_there_not_left_off():
    """Each daily renewal of the helper moved the brief and left the old copy turned off: one
    a day piled up in the person's list of scheduled tasks (2026-11-02)."""
    moved = json.loads(json.dumps(REG))
    brief = next(r for r in moved["routines"] if r["key"] == "morning_brief")
    brief["chat"] = {"session_id": "session_EXAMPLEOLDHELPER"}
    on_old = [{"id": "trig_EXAMPLEBRIEF", "session": "session_EXAMPLEOLDHELPER", "enabled": True}]
    calls = _plan(reg=moved, triggers=on_old)["brief"]
    assert [c.get("tool") or "run" for c in calls] == ["create_trigger", "run", "delete_trigger"]
    assert calls[2]["args"] == {"trigger_id": "trig_EXAMPLEBRIEF"}
    # A brief moved out of a chat of the person's own is still only turned off, never deleted.
    assert _plan()["brief"][2]["tool"] == "update_trigger"


def test_a_registry_with_the_upkeep_in_it_is_clean(tmp_path, monkeypatch):
    path = tmp_path / "routines.json"
    routines.record_upkeep(HELPER, "trig_EXAMPLEUP", "CRON_TZ=Europe/London 39 5 * * *", path=str(path))
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert routines.check(reg) == [], routines.check(reg)
    assert routines.upkeep_entry(reg)["chat"] == {"session_id": HELPER}
    routines.forget_upkeep(path=str(path))
    assert routines.upkeep_entry(json.loads(path.read_text(encoding="utf-8"))) is None
