"""The row-by-row merge runs wherever the sync ran, and is set before master is merged in.

Two faults found on 2026-10-25:
- the driver said `python3`, which is a Microsoft Store stand-in on a Windows computer
  with python.org's Python, so every merge there fell back to git's line merge and two
  chats' appended rows conflicted;
- the driver was set only by a full sync, so a fresh clone or a resumed cloud computer
  pulled master with none, and the same two rows conflicted there too.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import merge_state  # noqa: E402
import profile_upgrades  # noqa: E402
import sync_app  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           PYTHONDONTWRITEBYTECODE="1")
HEADER = "date,contact_id,direction,channel,scenario,full_text\n"


def g(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def test_the_driver_runs_the_python_that_wrote_it_by_its_full_path():
    d = merge_state.driver(r"C:\Users\Ana O'Neil\AppData\Local\Programs\Python\python.exe")
    assert "'C:/Users/Ana O'\\''Neil/AppData/Local/Programs/Python/python.exe' " \
           "tools/merge_state.py %O %A %B %P" in d
    assert "python3 tools/merge_state.py" not in merge_state.driver()
    assert merge_state.driver().startswith(
        "if [ -f tools/merge_state.py ]; then " + merge_state._sh_quote(sys.executable))


def _files(tmp_path):
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    base.write_text("id,status\na,sent\n")
    ours.write_text("id,status\na,replied\n")
    theirs.write_text("id,status\na,closed\n")
    return base, ours, theirs


def _cmd(driver, base, ours, theirs):
    return (driver.replace("%O", str(base)).replace("%A", str(ours))
            .replace("%B", str(theirs)).replace("%P", "network_contacts.csv"))


def test_a_python_since_removed_is_replaced_by_the_one_py_sh_finds(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "merge_state.py").write_text(
        "import sys\nopen(sys.argv[2], 'w').write('merged\\n')\n")
    shutil.copy(os.path.join(ROOT, "tools", "py.sh"), tools / "py.sh")
    base, ours, theirs = _files(tmp_path)
    gone = str(tmp_path / "removed-python" / "python.exe")
    r = subprocess.run(["sh", "-c", _cmd(merge_state.driver(gone), base, ours, theirs)],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert ours.read_text() == "merged\n"


def test_the_line_merge_it_falls_back_to_labels_each_side(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "merge_state.py").write_text("import sys\nsys.exit(3)\n")
    base, ours, theirs = _files(tmp_path)
    r = subprocess.run(["sh", "-c", _cmd(merge_state.driver(), base, ours, theirs)],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0
    merged = ours.read_text()
    assert "<<<<<<< ours" in merged and ">>>>>>> theirs" in merged
    assert ".merge_file_" not in merged and str(tmp_path) not in merged


def _origin_with_threads(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "master")
    (origin / "tools").mkdir()
    for f in ("merge_state.py", "py.sh"):
        shutil.copy(os.path.join(ROOT, "tools", f), origin / "tools" / f)
    shutil.copy(os.path.join(ROOT, ".gitattributes"), origin / ".gitattributes")
    (origin / "network_threads.csv").write_text(
        HEADER + "2026-10-01,ana_kowal,out,linkedin,first_note,Hello\n", encoding="utf-8")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "start")
    return origin


def test_a_fresh_clone_pulls_master_with_the_driver_set(tmp_path, monkeypatch, capsys):
    origin = _origin_with_threads(tmp_path)
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    g(me, "switch", "-q", "-c", "claude/work")
    with open(me / "network_threads.csv", "a", encoding="utf-8") as fh:
        fh.write("2026-10-02,bo_lind,out,linkedin,first_note,Hi Bo\n")
    g(me, "commit", "-qam", "this chat's message")
    with open(origin / "network_threads.csv", "a", encoding="utf-8") as fh:
        fh.write("2026-10-02,cy_ward,in,linkedin,reply,Thanks\n")
    g(origin, "commit", "-qam", "another chat's message")
    assert g(me, "config", "--get", "merge.ljs-state.driver", check=False).returncode
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 0, capsys.readouterr().out
    rows = (me / "network_threads.csv").read_text(encoding="utf-8")
    assert "Hi Bo" in rows and "Thanks" in rows and "<<<<<<<" not in rows
    assert sys.executable.replace("\\", "/") in g(
        me, "config", "--get", "merge.ljs-state.driver").stdout


def _instant(command):
    return profile_upgrades.Upgrade(id="example", added="2026-10-25", gives="x",
                                    pending=lambda: "", run="", cost="instant",
                                    command=command, paths=("profile/x.json",))


def test_an_instant_upgrade_runs_on_the_python_running_the_sync(monkeypatch):
    seen = []

    class Done:
        returncode = 0

    def fake_run(argv, **kw):
        seen.append(argv)
        return Done()
    monkeypatch.setattr(profile_upgrades.subprocess, "run", fake_run)
    monkeypatch.setattr(profile_upgrades, "_changed", lambda: set())
    up = _instant(("python3", "tools/x.py", "--write"))
    notes = profile_upgrades.run_instant([(up, "why")])
    assert seen == [[sys.executable, "tools/x.py", "--write"]]
    assert notes == [] or all("not applied" not in n for n in notes)


def test_an_instant_upgrade_that_cannot_start_is_undone_and_said(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        raise FileNotFoundError(argv[0])
    monkeypatch.setattr(profile_upgrades.subprocess, "run", fake_run)
    monkeypatch.setattr(profile_upgrades, "_changed", lambda: set())
    monkeypatch.setattr(profile_upgrades, "_git", lambda *a, **k: calls.append(a))
    up = _instant(("node", "x.js"))
    assert profile_upgrades.run_instant([(up, "why")]) == [
        "example: not applied (it could not run: FileNotFoundError)"]
    assert ("checkout", "--", ".") in calls


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_the_row_merge_still_merges_two_chats_rows_with_the_new_driver(tmp_path):
    origin = _origin_with_threads(tmp_path)
    a = tmp_path / "a"
    g(tmp_path, "clone", "-q", str(origin), str(a))
    merge_state.install(str(a))
    g(a, "switch", "-q", "-c", "one")
    with open(a / "network_threads.csv", "a", encoding="utf-8") as fh:
        fh.write("2026-10-03,di_moss,out,linkedin,first_note,Hello Di\n")
    g(a, "commit", "-qam", "one")
    g(a, "switch", "-q", "master")
    with open(a / "network_threads.csv", "a", encoding="utf-8") as fh:
        fh.write("2026-10-03,ed_fenn,out,email,first_note,Hello Ed\n")
    g(a, "commit", "-qam", "two")
    r = g(a, "merge", "-q", "--no-edit", "one", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (a / "network_threads.csv").read_text(encoding="utf-8")
    assert "Hello Di" in text and "Hello Ed" in text
