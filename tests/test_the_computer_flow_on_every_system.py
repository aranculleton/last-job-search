"""The computer side on a Mac, on Windows and on Linux, decided by what the computer reports.

The computer flow was built and its bugs found on one Mac, and its words said so: every step
for showing Claude's browser named Cmd+Shift+B first and Windows' key second, said nothing of
Linux, and the settings steps named a Mac's menus whatever the computer was. Each system now
gets its own keys and menus, from the registry's per-system variants
(tools/claude_surfaces.json), chosen by the computer's own report: sys.platform there, as its
heartbeat carries it, or a Windows path in the cloud's list of computers before any
heartbeat; with neither, the steps say all three in one short line. Invented computers only.
"""
from __future__ import annotations

import datetime as dt
import ntpath
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import claude_surfaces as C  # noqa: E402
import computer  # noqa: E402
import place  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)
MAC, WIN, LINUX = "darwin", "win32", "linux"
KEYS = {MAC: "Cmd+Shift+B", WIN: "Ctrl+Shift+B", LINUX: "Ctrl+Shift+B"}
OTHER = {MAC: "Ctrl+Shift+B", WIN: "Cmd+Shift+B", LINUX: "Cmd+Shift+B"}
SHOWN = ("browser-pane-show", "browser-pane-stay-signed-in")
CLOUD = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_CONTAINER_ID": "c-1"}


def _beat(system, age_s=60, name="Studio Laptop", **facts):
    f = dict(browser="shown", linkedin="in", cookies="unknown", read="ok", version="9.9.9",
             task=False, system=system)
    f.update(facts)
    data = computer.beat_fields(name, T - dt.timedelta(seconds=age_s), **f)
    return {computer.beat_id(name): {"data": data, "version": 3}}


def _waiting():
    return _db(("network~people", _w("network", "Harbourline Bank", to="computer",
                                     asked="2026-10-25T17:00:00Z",
                                     title="People at Harbourline Bank")))


# ------------------------------------------------------------------ what the computer is


def test_the_system_is_what_the_computer_reports():
    assert [C.system_of(x) for x in ("darwin", "macOS", "win32", "Windows", "cygwin", "msys",
                                     "linux", "Linux", "freebsd", "", None)] == \
        [MAC, MAC, WIN, WIN, WIN, WIN, LINUX, LINUX, "", "", ""]
    assert C.this_system("darwin") == MAC and C.this_system("win32") == WIN
    assert C.this_system("linux", "6.1.0-13-amd64") == LINUX
    # Inside WSL Python says linux, but the app on screen is the Windows one: its keys and
    # menus are Windows'.
    assert C.this_system("linux", "5.15.153.1-microsoft-standard-WSL2") == WIN
    # A cloud chat's own system is its container's, never the person's computer.
    assert C.here_system(CLOUD) == ""


def test_every_system_has_its_own_variant_and_the_entry_says_all_three():
    for eid in SHOWN + ("remote-control-settings",):
        assert C.for_system(eid, "") == eid
        for system, suffix in C.SYSTEMS.items():
            got = C.for_system(eid, system)
            assert got == f"{eid}-{suffix}", (eid, system)
            e = C.entry(got)
            assert e["system"] == system and e["variant_of"] == eid
            assert e["sources"] and e["verified_on"] and e.get("steps"), got
    # An entry with no variants is the same on every computer.
    assert C.for_system("connect-github", WIN) == "connect-github"


# ------------------------------------------------------------------ the steps shown


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_each_computer_is_told_its_own_key_for_claudes_browser(system):
    for eid in SHOWN:
        for page in (False, True):
            said = "\n".join(C.steps(eid, page=page, system=system))
            assert KEYS[system] in said and OTHER[system] not in said, (eid, system, said)
            assert "on a Mac" not in said and "on Windows" not in said, said
        assert KEYS[system] in C.say(eid, system=system)


def test_a_computer_not_known_is_told_all_three_in_one_line():
    for eid in SHOWN:
        for page in (False, True):
            lines = C.steps(eid, page=page)
            both = [ln for ln in lines if "Cmd+Shift+B" in ln and "Ctrl+Shift+B" in ln]
            assert len(both) == 1 and "Mac" in both[0] and "Windows" in both[0] \
                and "Linux" in both[0], lines


def test_the_settings_steps_name_each_systems_own_menus():
    mac = "\n".join(C.steps("remote-control-settings", system=MAC))
    win = "\n".join(C.steps("remote-control-settings", system=WIN))
    lin = "\n".join(C.steps("remote-control-settings", system=LINUX))
    assert "Claude, then Check for Updates" in mac and "Help, then" not in mac
    assert "Help, then Check for Updates" in win and "menu bar" not in win
    assert "share a folder" in win
    assert "software updates" in lin and "claude remote-control" in lin
    assert "claude remote-control" not in mac and "claude remote-control" not in win
    for said in (mac, win, lin):
        assert "Settings, then Claude Code, then Remote Control" in said
    # Not known: one line says each system's way to update.
    anyone = C.steps("remote-control-settings")
    upd = [ln for ln in anyone if "Check for Updates" in ln]
    assert len(upd) == 1 and "on a Mac" in upd[0] and "on Windows" in upd[0] \
        and "on Linux" in upd[0], anyone
    # The page's card ends on its own button, every system.
    for system in (MAC, WIN, LINUX, ""):
        assert C.steps("remote-control-settings", page=True, system=system)[-1].endswith("tap Done.")


def test_the_command_gives_this_computers_steps_and_all_three_in_the_cloud(capsys, monkeypatch):
    assert C.main(["steps", "browser-pane-show", "--system", "win32"]) == 0
    out, err = capsys.readouterr()
    assert "Ctrl+Shift+B" in out and "Cmd+Shift+B" not in out
    assert "'browser-pane-show-windows' checked" in err          # its own page and day
    assert C.main(["steps", "browser-pane-show", "--system", "all"]) == 0
    out, _ = capsys.readouterr()
    assert "Ctrl+Shift+B" in out and "Cmd+Shift+B" in out
    # Run on the person's computer, the command reads that computer itself.
    monkeypatch.setattr(C, "here_system", lambda env=None: MAC)
    assert C.main(["steps", "browser-pane-stay-signed-in"]) == 0
    out, _ = capsys.readouterr()
    assert "Cmd+Shift+B" in out and "Ctrl+Shift+B" not in out
    monkeypatch.setattr(C, "here_system", lambda env=None: "")
    assert C.main(["say", "browser-pane-stay-signed-in"]) == 0
    out, _ = capsys.readouterr()
    assert "Cmd+Shift+B" in out and "Ctrl+Shift+B" in out


# ------------------------------------------------------------------ the heartbeat and the card


def test_the_heartbeat_says_which_system_the_computer_is(monkeypatch):
    f = computer.beat_fields("Studio Laptop", T, system=WIN)
    assert f["system"] == WIN
    with pytest.raises(ValueError):
        computer.beat_fields("Studio Laptop", T, system="amiga")
    # Measured, never guessed: the computer's own.
    monkeypatch.setattr(C, "this_system", lambda platform=None, release=None: LINUX)
    assert computer.beat_fields("Studio Laptop", T)["system"] == LINUX


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_the_card_for_a_signed_out_computer_names_its_own_keys(system):
    st = computer.state(dict(_waiting(), chats=_beat(system, linkedin="out")), T)
    assert st["state"] == "signed_out" and st["system"] == system
    said = "\n".join(st["action"]["steps"])
    assert KEYS[system] in said and OTHER[system] not in said, said
    assert st["action"]["id"] == C.for_system("browser-pane-stay-signed-in", system)
    item = computer.card(dict(st, card=True))
    assert item["link"] == C.official(C.entry(st["action"]["id"]))
    assert item["checked"] == C.entry(st["action"]["id"])["verified_on"]


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_the_keep_the_sign_in_question_names_its_own_keys(system):
    """The browser that forgets LinkedIn each time the app quits is asked to keep it (Keep
    cookies), in the words for that computer."""
    st = computer.state(dict(_waiting(), chats=_beat(system, cookies="off")), T)
    assert st["state"] == "forgets"
    said = "\n".join(st["action"]["steps"])
    assert "Keep cookies" in said and KEYS[system] in said and OTHER[system] not in said


def test_an_older_heartbeat_with_no_system_gets_all_three():
    beat = _beat(MAC, linkedin="out")
    for doc in beat.values():
        doc["data"].pop("system")
    st = computer.state(dict(_waiting(), chats=beat), T)
    said = "\n".join(st["action"]["steps"])
    assert "Cmd+Shift+B" in said and "Ctrl+Shift+B" in said and st["system"] == ""


def test_the_settings_card_before_any_heartbeat_reads_the_cloud_list():
    """No heartbeat yet: a computer whose shared folder is a Windows path is Windows."""
    envs = {"environments": [
        {"environment_id": "env_w", "name": "DESKTOP-4F2K9QZ:C:\\Users\\Zoë Example\\job-search:ab12",
         "description": "Bridge environment (DESKTOP-4F2K9QZ)", "kind": "bridge",
         "state": "inactive"}]}
    assert computer.system_seen({}, envs=envs) == WIN
    st = computer.state(_waiting(), T, envs={"environments": []}, works_on="computer")
    assert st["state"] == "not_set_up"
    st = computer.state(_waiting(), T, envs={"environments": []}, works_on="computer",
                        folders={"folders": [], "cannot_be_used": [
                            {"computer_name": "Studio Laptop", "folder": "/Users/someone/job",
                             "system": "macOS", "reason": "not_available"}]})
    assert st["system"] == MAC
    assert "Claude, then Check for Updates" in "\n".join(st["action"]["steps"])


def test_the_way_back_for_a_computer_gone_quiet_names_its_system():
    lines = computer.check(dict(_waiting(), chats=_beat(WIN, age_s=8 * 24 * 3600)), T,
                           envs={"environments": []})
    gone = [ln for ln in lines if "remote-control-settings" in ln]
    assert gone and "--system win32" in gone[0], lines


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_the_sign_in_card_names_the_computers_own_keys(system):
    import app_setup
    item = app_setup.outside_item("linkedin", system=system)
    said = "\n".join(item["steps"])
    assert KEYS[system] in said and OTHER[system] not in said, said
    assert item["checked"] == C.entry(C.for_system("browser-pane-stay-signed-in", system))["verified_on"]
    anyone = "\n".join(app_setup.outside_item("linkedin")["steps"])
    assert "Cmd+Shift+B" in anyone and "Ctrl+Shift+B" in anyone


# ------------------------------------------------------------------ names and folders


def test_a_windows_bridge_keeps_its_folder_whole_and_says_windows():
    envs = {"environments": [
        {"environment_id": "env_w", "name": "DESKTOP-4F2K9QZ:C:\\Users\\Zoë Example\\job-search:ab12",
         "description": "Bridge environment (DESKTOP-4F2K9QZ)", "kind": "bridge", "state": "active"},
        {"environment_id": "env_m", "name": "Studio Laptop:Documents:cd34",
         "description": "Bridge environment (Studio Laptop)", "kind": "bridge", "state": "active"},
        {"environment_id": "env_l", "name": "kestrel-box:job-search:ef56", "platform": "linux",
         "description": "Bridge environment (kestrel-box)", "kind": "bridge", "state": "active"}]}
    got = {b["id"]: b for b in computer.bridges(envs)}
    assert got["env_w"] == {"id": "env_w", "computer": "DESKTOP-4F2K9QZ",
                            "folder": "C:\\Users\\Zoë Example\\job-search", "system": WIN}
    # A plain folder name says nothing of the system, and nothing is guessed from a name.
    assert got["env_m"] == {"id": "env_m", "computer": "Studio Laptop", "folder": "Documents"}
    assert got["env_l"]["system"] == LINUX and got["env_l"]["folder"] == "job-search"


@pytest.mark.parametrize("system,node", [(WIN, "DESKTOP-4F2K9QZ"), (LINUX, "kestrel-box.lan")])
def test_a_computer_names_itself_without_a_macs_own_command(system, node, monkeypatch):
    import platform
    import subprocess
    monkeypatch.setattr(computer.sys, "platform", system)
    monkeypatch.setattr(platform, "node", lambda: node)

    def no_scutil(*a, **k):
        raise AssertionError("scutil is a Mac's own")
    monkeypatch.setattr(subprocess, "run", no_scutil)
    assert computer.this_computer() == node.split(".")[0]


def test_chat_memory_is_found_under_a_windows_folder(tmp_path):
    """A chat's memory sits under ~/.claude/projects/<the folder, every other character a
    dash>, as Claude Code names it on Windows too: C:\\Users\\Zoë Example\\job-search is
    C--Users-Zo--Example-job-search."""
    home = tmp_path / "home"
    mem = home / ".claude" / "projects" / "C--Users-Zo--Example-job-search" / "memory"
    mem.mkdir(parents=True)
    (mem / "note.md").write_text("Only update when I say.\n", encoding="utf-8")
    up = home / ".claude" / "projects" / "C--Users-Zo--Example" / "memory"
    up.mkdir(parents=True)
    (up / "above.md").write_text("A note one folder up.\n", encoding="utf-8")
    got = computer.memory_files("C:\\Users\\Zoë Example\\job-search", home=str(home),
                                pathmod=ntpath, env={})
    assert sorted(os.path.basename(f) for f in got) == ["above.md", "note.md"]


# ------------------------------------------------------------------ the browser this chat has


def test_one_helper_says_which_browser_a_chat_has():
    b = place.browser_of
    assert b(["mcp__Claude_Browser__navigate", "Bash"], cloud=False) == "pane"
    assert b(["mcp__remote-devices__Claude_Browser__navigate"], cloud=True) == "linked"
    assert b(["enable__mcp__remote-devices__Claude_Browser"], cloud=True) == "linked"
    assert b(["mcp__claude-in-chrome__navigate"], cloud=False) == "chrome"
    assert b(["enable__mcp__claude-in-chrome"], cloud=False) == "chrome"
    assert b(["Bash", "create_session"], cloud=True) == "none" and b((), cloud=False) == "none"
    # The words the start command takes: "browser" is the pane on the computer and the
    # linked computer's pane in a cloud chat; "enable" is the linked one before it is on.
    assert b(["browser"], cloud=False) == "pane" and b(["browser"], cloud=True) == "linked"
    assert b(["enable"], cloud=True) == "linked" and b(["chrome"], cloud=False) == "chrome"
    assert b(["none"], cloud=False) == "none" and b("browser,chrome", cloud=False) == "pane"
    # Claude's own browser comes first where a chat has both.
    assert b(["mcp__claude-in-chrome__navigate", "mcp__Claude_Browser__navigate"],
             cloud=False) == "pane"


def test_a_chat_with_the_pane_by_its_tool_names_reads_profiles_itself(monkeypatch):
    import reading
    monkeypatch.setattr(place, "in_cloud", lambda env=None: False)
    got = reading.route(["mcp__Claude_Browser__navigate", "mcp__Claude_Browser__get_page_text"],
                        consent="browser")
    assert got["route"] == "here", got
    got = reading.route(["mcp__claude-in-chrome__navigate"], consent="browser")
    assert got["route"] != "here", got


def test_a_cloud_chat_lent_the_computers_browser_by_its_word_reads_it_there(monkeypatch):
    import app_listen
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(place, "in_cloud", lambda env=None: True)
    got = computer.route(_waiting(), T, envs={"environments": []}, tools=["browser"])
    assert got["route"] == "linked browser", got


def test_the_linkedin_download_counts_chrome_by_its_tool_names():
    import export
    assert export.has_browser(["mcp__claude-in-chrome__navigate"])
    assert export.has_browser(["chrome"]) and not export.has_browser(["Bash"])


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_the_sign_in_line_in_a_chat_on_the_computer_names_its_keys(system):
    import reading
    said = reading.signed_out_say("pane", system=system)
    assert KEYS[system] in said and OTHER[system] not in said
    anyone = reading.signed_out_say("pane")
    assert "Cmd+Shift+B" in anyone and "Ctrl+Shift+B" in anyone


@pytest.mark.parametrize("system", [MAC, WIN, LINUX])
def test_a_chat_on_the_computer_is_given_its_own_sign_in_line(system, monkeypatch):
    import reading
    monkeypatch.setattr(C, "here_system", lambda env=None: system)
    monkeypatch.setattr(reading, "app_job_here", lambda: "")
    steps = "\n".join(reading.signin_steps())
    assert KEYS[system] in steps and OTHER[system] not in steps, steps
