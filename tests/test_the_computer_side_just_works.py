"""The computer side: work that needs a LinkedIn read is done on the person's own computer,
in the best place there is, and no cloud chat takes it and closes it unread.

On 2026-11-09 a "find 10 people" run sat queued with the person at their computer, a cloud
chat claimed a rewrite that needed a profile and closed it with "Can't read LinkedIn from
here", `app.py next` placed the computer's run as a background agent with no browser, the
computer's chat obeyed an old memory over the person's setting, a zsh loop of fifty fixes
"failed", and its own report of the run's time and steps was wrong. Each is pinned here, with
invented people and computers only (tests/app_state.py).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)


def _beat(age_s=60, **facts):
    f = dict(browser="shown", linkedin="in", cookies="on", read="ok", version="9.9.9", task=True)
    f.update(facts)
    data = computer.beat_fields("Studio Laptop", T - dt.timedelta(seconds=age_s), **f)
    return {computer.beat_id("Studio Laptop"): {"data": data, "version": 3}}


BRIDGE = {"environments": [
    {"environment_id": "env_cloud", "name": "Default", "kind": "anthropic_cloud", "state": "active"},
    {"environment_id": "env_bridge1", "name": "Studio Laptop:Documents:ab12",
     "description": "Bridge environment (Studio Laptop)", "kind": "bridge", "state": "active"}]}


# ------------------------------------------------------------------ 2.2: routing


def test_a_cloud_chat_never_claims_finishes_or_fails_work_for_the_computer(tmp_path):
    item = _w("network", "Harbourline Bank", to="computer")
    db = _db(("network~people", item))
    assert page_db.next_item(db, "cloud", T) is None
    assert page_db.next_item(db, "computer", T)["work"] == "network~people"
    chosen = {"work": "network~people", "version": 1, "locks": []}
    with pytest.raises(ValueError, match="needs the person's computer"):
        page_db.claim(db, chosen, "cloud-1", "cloud", T, str(tmp_path / "c"))
    assert page_db.claim(db, chosen, "mac-1", "computer", T, str(tmp_path / "m"))
    running = _db(("network~people", dict(item, status="running", claimed_by="mac-1")))
    for status, err in (("done", ""), ("failed", "Can't read LinkedIn from here")):
        with pytest.raises(ValueError, match="needs the person's computer"):
            page_db.finish(running, "network~people", T, str(tmp_path / status), status=status,
                           error=err, summary="Ten people found and drafted.", chat_kind="cloud",
                           chat="mac-1")
    # Their own Stop is the one way a cloud chat ends it.
    stopped = _db(("network~people", dict(item, status="running", claimed_by="mac-1",
                                          stop_asked=True)))
    assert page_db.finish(stopped, "network~people", T, str(tmp_path / "s"), status="stopped",
                          chat_kind="cloud", chat="mac-1")["status"] == "stopped"
    # Work for anywhere is untouched.
    assert page_db.next_item(_db(("d1", _w("draft", "Kestrel Mutual"))), "cloud", T)


def test_the_computer_chat_does_computer_work_itself_never_as_an_agent_with_no_browser(tmp_path):
    s = Search(str(tmp_path))
    s.put("work", "network~people", _w("network", "Harbourline Bank", to="computer",
                                       title="People at the employers you want"), version=4)
    s.put("work", "draft~kestrel", _w("draft", "Kestrel Mutual"), version=2)
    got = json.loads(s.run("next", s.dump, "--chat", "mac-1", "--kind", "computer",
                           "--computer-only", "--now", NOW))
    assert got["work"] == "network~people" and got["run"] == "here"
    assert "agent" not in got and "create_session" not in got
    steps = "\n".join(got["steps"])
    assert "--kind computer --computer-only" in steps and "--kind cloud" not in steps
    assert "send_message" not in steps
    # The cloud chat is never offered it, and takes the draft instead.
    cloud = json.loads(s.run("next", s.dump, "--chat", "cloud-1", "--kind", "cloud", "--now", NOW))
    assert cloud["work"] == "draft~kestrel"


# ------------------------------------------------------------------ 2.3: the fallback chain


def test_the_chain_picks_the_best_place_there_is_in_order():
    db = _db(("network~people", _w("network", "Harbourline Bank", to="computer",
                                   title="People at Harbourline Bank")))
    tools = ["create_session", "request_computer_folder", "mcp__remote-devices__Claude_Browser__navigate"]
    # 1. A chat working on the computer takes it.
    live = dict(db, chats={"mac-1": {"data": {"kind": "computer", "seen_at": NOW}, "version": 1}})
    assert computer.route(live, T, envs=BRIDGE, tools=tools)["route"] == "computer chat"
    # 2. A cloud chat starts a chat on the computer: in Auto, named, with a whole prompt.
    got = computer.route(db, T, envs=BRIDGE, tools=tools, url="https://claude.ai/artifact/x",
                         copy="github.com/example-owner/my-job-search")
    assert got["route"] == "computer session"
    call = got["call"]
    assert call["environment_id"] == "env_bridge1" and call["permission_mode"] == "auto"
    assert call["title"] == "Job search · People at Harbourline Bank · Studio Laptop"
    assert "network~people" in call["prompt"] and "Never message another chat" in call["prompt"]
    assert "send_message" not in call["prompt"]
    assert "confirm_repository_trust" in got["then"] and "computer.py started" in got["then"]
    # 3. With no way to start one, the computer's scheduled task takes it.
    with_task = dict(db, chats=_beat(age_s=600))
    assert computer.route(with_task, T, envs={"environments": []}, tools=[])["route"] == "computer task"
    # 4. A folder the computer offers.
    folders = {"folders": [{"environment_id": "env_f", "computer_name": "Studio Laptop",
                            "folder": "search", "online": True}]}
    assert computer.route(db, T, envs=[], folders=folders,
                          tools=["request_computer_folder"])["route"] == "computer folder"
    # 5. A cloud chat lent the computer's browser does it itself.
    assert computer.route(db, T, envs=[], tools=["enable__mcp__remote-devices__Claude_Browser"]
                          )["route"] == "linked browser"
    # 6. Nothing: one line, at most one action, and the paste.
    last = computer.route(db, T, envs=[], tools=[], works_on="computer")
    assert last["route"] == "paste" and last["paste"] and last["line"]
    assert last["action"] is None or set(last["action"]) >= {"label", "steps"}


def test_a_chat_already_started_is_not_started_twice_and_is_archived_when_over(tmp_path):
    db = _db(("network~people", _w("network", "Harbourline Bank", to="computer")))
    batches = computer.started(db, "network~people", "session_x1", "env_bridge1", "Studio Laptop",
                               T, str(tmp_path))
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    sess = json.load(open(entry["file_path"], encoding="utf-8")) if entry.get("file_path") else entry["data"]
    db["work"]["network~people"]["data"].update(computer_session=sess["computer_session"])
    assert computer.waiting(db, T)["started"] == {"network~people": "session_x1"}
    assert computer.route(db, T, envs=BRIDGE, tools=["create_session"])["route"] == "none"
    db["work"]["network~people"]["data"]["status"] = "done"
    assert computer.waiting(db, T)["finished"] == [{"work": "network~people", "session": "session_x1"}]


# ------------------------------------------------------------------ 2.4: the heartbeat


@pytest.mark.parametrize("age,facts,envs,want", [
    (60, {}, BRIDGE, "ready"),
    (60, {"linkedin": "out"}, BRIDGE, "signed_out"),
    (60, {"cookies": "off"}, BRIDGE, "forgets"),
    (60, {"read": "stopped"}, BRIDGE, "paused"),
    (5 * 3600, {}, None, "off"),
    (5 * 3600, {}, {"environments": []}, "no_bridge"),
    (8 * 86400, {}, None, "gone"),
])
def test_the_page_shows_the_computer_in_one_line(age, facts, envs, want):
    db = dict(_db(), chats=_beat(age_s=age, **facts))
    st = computer.state(db, T, envs=envs)
    assert st["state"] == want and st["line"] == computer.SAY[want]
    assert st["computer"] == "Studio Laptop"
    assert not st["card"]                       # nothing waits: no card
    if st["action"]:
        assert st["action"]["steps"] and all(s[:1].isdigit() for s in st["action"]["steps"])


def test_one_card_only_while_computer_work_waits_and_the_person_is_needed():
    work = ("network~people", _w("network", "Harbourline Bank", to="computer",
                                 asked="2026-10-25T17:00:00Z"))
    signed_out = dict(_db(work), chats=_beat(linkedin="out"))
    st = computer.state(signed_out, T, envs=BRIDGE)
    assert st["card"] and computer.card(st)["steps"]
    assert computer.card(st)["id"] == "q-setup-computer"
    ready = dict(_db(work), chats=_beat())
    assert not computer.state(ready, T, envs=BRIDGE)["card"]
    # Just asked: the chain gets its ten minutes before anyone is bothered.
    fresh = ("network~people", _w("network", "Harbourline Bank", to="computer", asked=NOW))
    assert not computer.state(dict(_db(fresh), chats=_beat(linkedin="out")), T)["card"]


def test_a_person_with_no_computer_is_shown_nothing_about_one(monkeypatch):
    """A career changer with no laptop, who said they work on their phone, is never shown a
    computer row or card; someone who said they have one, and has not set it up, is."""
    import app
    db = _db(("d1", _w("draft", "Kestrel Mutual")))
    monkeypatch.setattr(computer, "_works_on", lambda: "phone")
    assert app.computer_seen(db, T) is None
    monkeypatch.setattr(computer, "_works_on", lambda: "")
    assert app.computer_seen(db, T) is None
    monkeypatch.setattr(computer, "_works_on", lambda: "computer")
    assert app.computer_seen(db, T)["state"] == "not_set_up"
    # Work sent to the computer by someone with no computer said: told plainly, never hidden.
    sent = _db(("n1", _w("network", "Harbourline Bank", to="computer")))
    monkeypatch.setattr(computer, "_works_on", lambda: "phone")
    assert app.computer_seen(sent, T)["state"] == "no_computer"


def test_the_page_draws_the_engines_line_and_card(tmp_path, monkeypatch):
    """Settings' row and the To do card come from the engine, worked out once (DESIGN.md)."""
    import person
    s = Search(str(tmp_path))
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setenv(person.STATE_ENV, s.state)
    person._modules.clear()
    person._data.clear()
    work = ("network~people", _w("network", "Harbourline Bank", to="computer",
                                 asked="2026-10-25T17:00:00Z"))
    st = computer.state(dict(_db(work), chats=_beat(linkedin="out")), T, envs=BRIDGE)
    model, _ = app_model.build(T.date(), T, only=("needs_you", "where"), computer=st)
    row = model["where"]["computer"]
    assert row["state"] == "signed_out" and row["say"] == computer.SAY["signed_out"]
    assert row["steps"] and row["action"] == "Sign in once"
    cards = [c for c in model["needs_you"] if c["id"] == "q-setup-computer"]
    assert len(cards) == 1 and cards[0]["steps"] and cards[0]["link"]
    ready = computer.state(dict(_db(work), chats=_beat()), T, envs=BRIDGE)
    model, _ = app_model.build(T.date(), T, only=("needs_you", "where"), computer=ready)
    assert model["where"]["computer"]["state"] == "ready"
    assert not [c for c in model["needs_you"] if c["id"] == "q-setup-computer"]
    person._modules.clear()
    person._data.clear()


def test_the_heartbeat_is_measured_never_guessed():
    with pytest.raises(ValueError):
        computer.beat_fields("Studio Laptop", T, browser="probably")
    f = computer.beat_fields("Studio Laptop:Documents:ab12", T, browser="hidden",
                             linkedin="in", cookies="unknown", read="none", task=False, version="1")
    assert f["computer"] == "Studio Laptop" and f["watching"] is False
    assert f["last_read"] is None and f["keep_cookies"] == "unknown"


def test_a_bridge_names_its_computer():
    assert computer.bridges(BRIDGE) == [{"id": "env_bridge1", "computer": "Studio Laptop",
                                         "folder": "Documents"}]
    asleep = {"environments": [dict(BRIDGE["environments"][1], state="inactive")]}
    assert computer.bridges(asleep) == []


# ------------------------------------------------------------------ 2.6: the daily check


def test_the_daily_check_names_what_is_broken_and_the_way_back():
    work = ("network~people", _w("network", "Harbourline Bank", to="computer",
                                 asked="2026-10-25T17:00:00Z"))
    lines = computer.check(dict(_db(work), chats=_beat(linkedin="out")), T, envs=BRIDGE)
    assert lines and "signed out" in lines[0]
    gone = computer.check(dict(_db(), chats=_beat(age_s=9 * 86400)), T, envs=None)
    assert any("remote-control-settings" in ln for ln in gone)
    no_task = computer.check(dict(_db(), chats=_beat(task=False)), T, envs=BRIDGE)
    assert any(computer.TASK_NAME in ln for ln in no_task)
    behind = computer.check(dict(_db(), chats=_beat(version="1.0.0")), T, envs=BRIDGE,
                            version="9.9.9")
    assert any("older version" in ln for ln in behind)
    assert computer.check(dict(_db(), chats=_beat()), T, envs=BRIDGE, version="9.9.9") == []


# ------------------------------------------------------------------ 2.8: memory, shells, pace


def test_an_old_chat_memory_never_outranks_the_persons_setting(tmp_path):
    home = tmp_path / "home"
    copy = tmp_path / "Documents" / "search"
    copy.mkdir(parents=True)
    # The chat on the computer was started in the shared folder, above the copy.
    proj = re.sub(r"[^A-Za-z0-9]", "-", str(tmp_path / "Documents"))
    mem = home / ".claude" / "projects" / proj / "memory"
    mem.mkdir(parents=True)
    (mem / "feedback_updates.md").write_text(
        "---\ntype: feedback\n---\nOnly update the app when I say so; never take updates "
        "by themselves.\n", encoding="utf-8")
    (mem / "user_role.md").write_text("A nurse in Vancouver looking for clinic roles.\n",
                                      encoding="utf-8")
    os.environ.pop("CLAUDE_CONFIG_DIR", None)
    got = computer.memory_conflicts(str(copy), home=str(home),
                                    settings={"profile/person.json app_updates": "auto"})
    assert [(os.path.basename(c["file"]), c["memory_says"], c["setting_says"]) for c in got] == [
        ("feedback_updates.md", "when_asked", "auto")]
    line = computer.memory_line(got)
    assert "settings win" in line and "Leave the note" in line
    agree = computer.memory_conflicts(str(copy), home=str(home),
                                      settings={"profile/person.json app_updates": "when_asked"})
    assert agree == [] and computer.memory_line(agree) == ""


def test_every_command_the_app_prints_runs_the_same_in_zsh_and_bash():
    assert computer.shell_problems('for kv in "a 1" "b 2"; do set -- $kv; echo "$1"; done')
    assert computer.shell_problems("for w in $list; do echo $w; done")
    assert computer.shell_problems("bash -c 'set -- $kv'") == []
    assert computer.shell_problems('for kv in "a 1"; do k="${kv%% *}"; done') == []
    found = []
    for base in ("tools", ".claude", "automation"):
        for dp, _dns, fns in os.walk(os.path.join(ROOT, base)):
            if "openroles" in dp:
                continue
            for f in fns:
                # Shell scripts name bash themselves (their first line); only what a chat is
                # told to run, in a tool's words or the instructions, is held to both shells.
                if not f.endswith((".py", ".md")) or f == "computer.py":
                    continue
                with open(os.path.join(dp, f), encoding="utf-8", errors="replace") as fh:
                    for n, line in enumerate(fh, 1):
                        if computer.shell_problems(line):
                            found.append(f"{os.path.relpath(os.path.join(dp, f), ROOT)}:{n}")
    assert found == [], found
    prompt = computer.session_prompt("network~people", "People", "https://claude.ai/artifact/x",
                                     "github.com/example-owner/my-job-search")
    assert computer.shell_problems(prompt) == []


def test_the_pace_rule_is_one_sentence_and_a_chat_says_only_what_it_does():
    import pace
    assert "no wait" in pace.PACE_RULE and "at a time" in pace.PACE_RULE
    said = pace.say(10)
    assert "10 LinkedIn pages" in said and not re.search(r"\d+\s*(?:to|-)\s*\d+\s*s", said)
    assert "PACE_RULE" in computer.session_prompt("w", "t", "u", "c")


# ------------------------------------------------------------------ 2.9: measured


def _line(t, content=None, usage=None, **kw):
    msg = {"content": content or []}
    if usage:
        msg["usage"] = usage
    return json.dumps(dict(timestamp=t, message=msg, **kw))


def test_a_run_is_measured_from_its_own_transcript(tmp_path, monkeypatch):
    f = tmp_path / "s.jsonl"
    use = lambda name, **inp: {"type": "tool_use", "name": name, "input": inp}  # noqa: E731
    lines = [
        _line("2026-10-25T17:00:00Z", [use("Bash", command="python3 tools/app.py pin \"$D\" --work w --stage find")]),
        _line("2026-10-25T17:02:00Z", [use("WebSearch", query="x")]),
        _line("2026-10-25T17:05:00Z", [use("Bash", command="python3 tools/app.py pin \"$D\" --work w --stage read")]),
        _line("2026-10-25T17:06:00Z", [use("mcp__Claude_Browser__navigate", url="https://www.linkedin.com/in/example-person/")]),
        _line("2026-10-25T17:07:00Z", [use("mcp__Claude_Browser__navigate", url="https://www.linkedin.com/in/example-person/details/experience/")]),
        _line("2026-10-25T17:08:00Z", [use("mcp__Claude_Browser__navigate", url="https://www.linkedin.com/search/results/people/?keywords=x")]),
        _line("2026-10-25T17:12:00Z", usage={"input_tokens": 1000, "output_tokens": 2000,
                                             "cache_read_input_tokens": 100000,
                                             "cache_creation_input_tokens": 0}),
    ]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    u = computer.measure(str(f))
    assert u["wall_s"] == 12 * 60 and u["calls"] == 6
    assert u["tools"]["Bash"] == 2 and u["web_searches"] == 1
    assert u["pages"] == {"profile": 1, "experience": 1, "people search": 1}
    assert u["linkedin_pages"] == 3
    assert u["stages"] == {"find": 300, "read": 420}
    assert u["tokens"]["output"] == 2000 and u["est_usd"] > 0
    assert computer.usage_line(u).startswith("Took 12 min: 6 steps, 3 LinkedIn pages")
    # Kept, and the brief's trend reads it.
    state = tmp_path / "state"
    (state / "documents").mkdir(parents=True)
    monkeypatch.setenv("LJS_STATE", str(state))
    computer.record_run("w", "network", u, T)
    line = computer.trend(T.date())
    assert line.startswith("Your computer did 1 LinkedIn run this week: about 12 min")


# ------------------------------------------------------------------ 2.7, B21: the chats it makes


def test_the_chats_it_starts_are_known_as_the_apps_by_their_name():
    import tidy
    title = computer.session_title("People at Harbourline Bank", "Studio Laptop:Documents:ab12")
    assert title == "Job search · People at Harbourline Bank · Studio Laptop"
    assert tidy.APP_TITLE.match(title)
    assert not tidy.APP_TITLE.match("Holiday plans · Studio Laptop")


# ------------------------------------------------------------------ B20, B22: scheduled tasks


TRIGGERS = {"triggers": [
    {"id": "trig_brief", "name": "Job search: morning brief", "persistent_session_id": "session_helper",
     "cron_expression": "CRON_TZ=America/Vancouver 38 7 * * *", "enabled": True, "prompt": "brief"},
    {"id": "trig_other", "name": "Job search: first brief", "persistent_session_id": "session_other",
     "run_once_at": "2026-10-26T09:00:00Z", "enabled": True},
    {"id": "trig_off", "name": "Old task", "persistent_session_id": "session_helper", "enabled": False}]}


def test_computer_access_is_never_approved_where_a_scheduled_task_fires():
    """Approving computer access ties the chat to the person's devices for good, and a brief
    bound to it then failed with access denied (2026-11-09): each task is moved first to a
    fresh chat a run, with no connectors field (the brief needs none, and some organisations refuse the field), the old one turned off."""
    moves = computer.trust_check("session_helper", TRIGGERS)
    assert len(moves) == 1 and moves[0].startswith("move trig_brief: create_trigger ")
    call = json.loads(moves[0].split("create_trigger ", 1)[1].split(", then update_trigger")[0])
    assert call["create_new_session_on_fire"] is True and "connectors" not in call
    assert call["cron_expression"].startswith("CRON_TZ=") and "persistent_session_id" not in call
    assert '"enabled": false' in moves[0] and "--setup routines_screen" in moves[0]
    assert computer.trust_check("session_fresh", TRIGGERS) == [
        "trust: ok, no scheduled task fires into this chat"]
    # The daily check spots a task bound to the chat that approved it.
    lines = computer.check(_db(), T, triggers=TRIGGERS, locked="session_helper")
    assert any("morning brief" in ln and "trust-check" in ln for ln in lines)
    assert computer.check(_db(), T, triggers=TRIGGERS, locked="") == []
    got = computer.route(_db(("n1", _w("network", to="computer"))), T, envs=BRIDGE,
                         tools=["create_session"])
    assert "trust-check" in got["then"] and got["then"].index("trust-check") < \
        got["then"].index("confirm_repository_trust")
