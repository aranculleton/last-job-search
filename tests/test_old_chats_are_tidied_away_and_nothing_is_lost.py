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
    assert new["prompt"] == routines.stub(REG, "morning_brief") and new["connectors"] == []
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
    # The plain stub: the moved brief is not told it is in the ops chat, nor to relay.
    assert new["prompt"] == routines.DEFAULT_STUB.format(
        label="morning brief", Label="Morning brief", prompt_file=routines.BRIEF_FILE, relay_id="")
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
    routines.record(HELPER, "trig_EXAMPLENEW", "CRON_TZ=Europe/London 56 7 * * *", path=str(path))
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
