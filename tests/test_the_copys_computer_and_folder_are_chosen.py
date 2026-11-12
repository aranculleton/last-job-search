"""The chat started on the person's computer is started in the folder that holds their copy, on
the computer that wrote the heartbeat, and finds the copy wherever it is in that folder.

From the local review of 2026-11-11 (local review 8): `pick_bridge` ignored the folder, so with
two connections on one Mac ("Documents" and the copy's own folder) either could be taken; the
heartbeat's name comes from the computer ("Morgan's MacBook Air") while the connection says
"Mac", so the fresh check-in and the tested computer never matched (the tests used one name on
both sides); the chat's search for the copy stopped at three folders down, missing a copy at
Documents/GitHub/<copy>, and with the app's own copy beside the person's it took either; and
nothing told the person when the copy was in no folder Claude could start in. Every computer,
folder and person here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402

WORK = ("network~read~1", _w("network", to="computer", title="Reading one profile"))
COPY = "github.com/morgan-example/my-job-search"
TWO = {"environments": [
    {"environment_id": "env_docs", "name": "Mac:Documents:4ba6", "kind": "bridge",
     "description": "Bridge environment (Mac)", "state": "active"},
    {"environment_id": "env_copy", "name": "Mac:my-job-search:77c1", "kind": "bridge",
     "description": "Bridge environment (Mac)", "state": "active"}]}
LAPTOP = "Morgan's MacBook Air"


def _beat(copy_path: str = "", minutes: float = 30, name: str = LAPTOP) -> dict:
    data = computer.beat_fields(name, T - dt.timedelta(minutes=minutes), linkedin="in",
                                chat="session_mac0", copy=copy_path)
    return {computer.beat_id(name): {"data": data, "version": 2}}


def test_a_computer_is_known_by_more_than_its_exact_name():
    beats = ["Morgan's MacBook Air"]
    assert computer.same_computer("Mac", "Morgan's MacBook Air", beats)
    assert computer.same_computer("morgans macbook air", "Morgan’s MacBook Air", beats)
    # "Mac" in two names is no match: which one is not known.
    assert not computer.same_computer("Mac", "Morgan's MacBook Air",
                                      beats + ["Morgan's Mac mini"])
    assert not computer.same_computer("Studio Laptop", "Morgan's MacBook Air", beats)


def test_the_folder_that_holds_the_copy_is_chosen(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    # Known from the heartbeat: the copy's own folder first, whatever the list's order.
    db = dict(_db(WORK), chats=_beat("Documents/GitHub/my-job-search"))
    assert [b["id"] for b in computer.pick_bridge(computer.bridges(TWO), db, T, COPY)][0] == \
        "env_copy"
    # With nothing known but the copy's name, the same.
    bare = _db(WORK)
    assert computer.pick_bridge(computer.bridges(TWO), bare, T, COPY)[0]["id"] == "env_copy"
    # Only Documents served: it holds the copy, so it is taken.
    docs = {"environments": TWO["environments"][:1]}
    assert computer.pick_bridge(computer.bridges(docs), db, T, COPY)[0]["id"] == "env_docs"


def test_the_fresh_signed_in_computer_is_matched_to_its_connection(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    envs = {"environments": [
        {"environment_id": "env_desk", "name": "Studio Desktop:my-job-search:1a1a",
         "kind": "bridge", "description": "Bridge environment (Studio Desktop)",
         "state": "active"},
        {"environment_id": "env_mac", "name": "Mac:my-job-search:2b2b", "kind": "bridge",
         "description": "Bridge environment (Mac)", "state": "active"}]}
    db = dict(_db(WORK), chats=_beat("Documents/GitHub/my-job-search"))
    assert computer.pick_bridge(computer.bridges(envs), db, T, COPY)[0]["id"] == "env_mac"


def test_no_folder_that_holds_the_copy_puts_a_card_on_the_page(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    only = {"environments": [
        {"environment_id": "env_desk", "name": "Mac:Desktop:5e5e", "kind": "bridge",
         "description": "Bridge environment (Mac)", "state": "active"}]}
    db = dict(_db(WORK), chats=_beat("Documents/GitHub/my-job-search"))
    got = computer.route(db, T, chat="session_starter", envs=only, tools=["create_session"],
                         url="u", copy=COPY)
    assert got["route"] == "no folder" and "call" not in got, got
    st = computer.state(db, T + dt.timedelta(minutes=15), envs=only)
    assert st["state"] == "no_folder" and st["card"], st
    card = computer.card(st)
    assert "my-job-search" in card["body"] and card["steps"], card


def test_a_chat_that_cannot_find_the_copy_tells_the_page(tmp_path, monkeypatch):
    """The copy in no folder known: the chat started there says so on the page, and the page
    names the folder to add; no chat is started there again until the list changes."""
    _as(monkeypatch, "cloud", tmp_path)
    prompt = " ".join(computer.session_prompt("network~read~1", "People", "u", COPY).split())
    step1 = prompt[prompt.index("1. "):prompt.index("2. ")]
    assert "computer_lost~" in step1 and "stop" in step1
    lost = {"computer_lost~session_mac1": {"data": {
        "folder": "/Users/morgan/Desktop", "chat": "session_mac1",
        "at": app_model.stamp(T - dt.timedelta(minutes=20))}, "version": 1}}
    only = {"environments": [
        {"environment_id": "env_desk", "name": "Mac:Desktop:5e5e", "kind": "bridge",
         "description": "Bridge environment (Mac)", "state": "active"}]}
    starter = {"computer_starter": {"data": {"chat": "session_starter", "bell": "b"},
                                    "version": 1}}
    db = dict(_db(WORK), meta=dict(lost, **starter))
    got = computer.route(db, T, chat="session_starter", envs=only, tools=["create_session"],
                         url="u", copy=COPY)
    assert got["route"] == "no folder", got
    st = computer.state(db, T, envs=only)
    assert st["state"] == "no_folder"
    # The folder it was given changes: started there.
    more = {"environments": only["environments"] + TWO["environments"][1:]}
    got = computer.route(db, T, chat="session_starter", envs=more, tools=["create_session"],
                         url="u", copy=COPY)
    assert got["route"] == "computer session" and got["call"]["environment_id"] == "env_copy"


def _repo(path: str, origin: str) -> None:
    os.makedirs(os.path.join(path, "tools"), exist_ok=True)
    with open(os.path.join(path, "tools", "app.py"), "w", encoding="utf-8") as fh:
        fh.write("")
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "remote", "add", "origin", origin], check=True)


def shell_of(name: str) -> str:
    """The shell a chat on this computer runs the command in: on Windows, Git Bash, which
    Claude Code there uses, never the bash.exe on PATH that starts Windows Subsystem for Linux
    ("has no installed distributions", the Windows check, 2026-11-11); elsewhere, by name."""
    if name != "bash" or sys.platform != "win32":
        return shutil.which(name) or ""
    import pathlib
    found = []
    try:
        ex = subprocess.run(["git", "--exec-path"], capture_output=True, text=True,
                            encoding="utf-8").stdout.strip()
    except OSError:
        ex = ""
    if ex:                                   # <Git>\mingw64\libexec\git-core
        for up in list(pathlib.Path(ex).parents)[:4]:
            found += [up / "bin" / "bash.exe", up / "usr" / "bin" / "bash.exe"]
    for env in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            found += [pathlib.Path(base) / "Git" / "bin" / "bash.exe",
                      pathlib.Path(base) / "Programs" / "Git" / "bin" / "bash.exe"]
    on_path = shutil.which("bash") or ""
    if on_path and not any(w in on_path.lower() for w in ("system32", "windowsapps")):
        found.append(pathlib.Path(on_path))
    return next((str(f) for f in found if f.is_file()), "")


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_the_copy_is_found_four_folders_down_and_by_its_own_address(tmp_path, shell):
    sh = shell_of(shell)
    if not sh:
        pytest.skip(f"no {shell} here" + (": no Git Bash on this Windows computer"
                                          if sys.platform == "win32" and shell == "bash" else ""))
    docs = tmp_path / "Documents"
    _repo(str(docs / "GitHub" / "my-job-search"), "@".join(("git", "github.com:morgan-example/my-job-search.git")))
    _repo(str(docs / "GitHub" / "last-job-search"), "https://github.com/aranculleton/last-job-search")
    _repo(str(docs / "Old" / "my-job-search-2"),
          "https://github.com/morgan-example/my-job-search-2.git")
    cmd = computer.find_copy_command(COPY)
    assert computer.shell_problems(cmd) == []
    got = subprocess.run([sh, "-c", cmd], cwd=str(docs), capture_output=True, text=True, encoding="utf-8")
    assert got.stdout.split() == ["./GitHub/my-job-search"], got.stdout + got.stderr
    # Started in the copy itself, it is found where it is.
    here = subprocess.run([sh, "-c", cmd], cwd=str(docs / "GitHub" / "my-job-search"),
                          capture_output=True, text=True, encoding="utf-8")
    assert here.stdout.split() == ["."], here.stdout + here.stderr


def test_the_heartbeat_and_the_setup_say_where_the_copy_is(tmp_path, monkeypatch):
    home = tmp_path / "home"
    copy = home / "Documents" / "GitHub" / "my-job-search"
    os.makedirs(copy)
    # Home as the computer's own: HOME on a Mac or Linux, USERPROFILE on Windows, which is
    # what Python reads there (and Claude Code's own home on Windows).
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert computer.copy_place(str(copy)) == "Documents/GitHub/my-job-search"
    # A chat's own working folder inside the copy names the copy, not itself.
    assert computer.copy_place(str(copy / ".claude" / "worktrees" / "job-1")) == \
        "Documents/GitHub/my-job-search"
    data = json.loads(json.dumps(computer.beat_fields(LAPTOP, T, copy="Documents/GitHub/x")))
    assert data["copy"] == "Documents/GitHub/x"


def test_home_is_the_computers_own_not_a_shells(tmp_path, monkeypatch):
    """On Windows, Git Bash sets HOME (/c/Users/...) while Python and Claude Code take home from
    USERPROFILE: the copy's place is read under the home Python gives, whatever HOME says."""
    home = tmp_path / "Zoë Quillfeather"
    copy = home / "Documents" / "GitHub" / "my-job-search"
    os.makedirs(copy)
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("USERPROFILE", str(home))
    # Windows' own rule (ntpath.expanduser: USERPROFILE first), played on any computer.
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: os.environ["USERPROFILE"] + p[1:] if p.startswith("~") else p)
    assert computer.copy_place(str(copy)) == "Documents/GitHub/my-job-search"
