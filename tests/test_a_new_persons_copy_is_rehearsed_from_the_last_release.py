"""An update is rehearsed on a new person's copy made from the last release, as well as on a real one.

The maintainer's own copy is one person, far along: a stranger who made their copy from an
older release and starts a chat on the day the update lands meets the update another way, the
old version's start printing the update check as a step. Taking 4.15.0 that way sent the chat
round the whole start twice, and nothing had rehearsed it (2026-11-11). `rehearse_sync.py
--fresh <tag>` makes that copy from the app at the release, set up as the example person, and
plays out a cloud chat and a chat on their computer starting on update day. These tests check
what it plans and the copy it makes, offline; the whole run is made by hand before a release.
Every repository here is a throwaway one made by the test.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_setup  # noqa: E402
import rehearse_sync  # noqa: E402

# What a start before 4.15.0 printed on update day (4.14.0's own words, its steps shortened).
OLD_START = """app start: set up, page to publish
Claude, do this:
1. python3 tools/sync_app.py --pull   (the day's update check; do what it prints, then carry on)
2. python3 tools/sync_app.py --on "rehearsal" --tools "none"   (the day's update check; do what it prints, then carry on)
3. Build the person's page, in parts: python3 tools/app.py page --out-dir <your scratchpad>/page
"""


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                           "user.email=t@example.com", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def test_the_update_check_an_old_start_printed_is_run_as_printed():
    got = rehearse_sync.commands(OLD_START)
    assert got == [[sys.executable, "tools/sync_app.py", "--pull"],
                   [sys.executable, "tools/sync_app.py", "--on", "rehearsal", "--tools", "none"]]
    # A start that runs the check itself prints none: nothing to run.
    assert rehearse_sync.commands("app start: set up\nClaude, do this:\n1. Carry on.\n") == []


def test_the_page_is_built_where_the_steps_say_and_its_address_read():
    assert rehearse_sync.page_steps(OLD_START) == [("page", "")]
    again = ("1. python3 tools/app.py page --out-dir <your scratchpad>/page --url "
             "https://claude.ai/code/artifact/0000, then do the read")
    assert rehearse_sync.page_steps(again) == [("page", "https://claude.ai/code/artifact/0000")]


def test_being_sent_round_the_start_again_fails_and_its_own_steps_do_not():
    assert rehearse_sync._AGAIN.search(app_setup.START_CHANGED)
    assert rehearse_sync._AGAIN.search(app_setup.PAGE_NOT_YET)
    assert not rehearse_sync._AGAIN.search(app_setup.START_HERE_SAY)


def test_a_new_persons_copy_is_the_release_tree_set_up_as_the_example_person(tmp_path,
                                                                           monkeypatch):
    app = tmp_path / "app"
    (app / "profile.example" / "state").mkdir(parents=True)
    (app / "tools").mkdir()
    (app / "README.md").write_text("The app.\n", encoding="utf-8")
    (app / "tools" / "x.py").write_text("a = 1\n", encoding="utf-8")
    (app / "profile.example" / "person.json").write_text('{"identity": {"name": "Morgan"}}\n',
                                                         encoding="utf-8")
    (app / "profile.example" / "state" / "README.md").write_text("What this is for.\n",
                                                                 encoding="utf-8")
    (app / "profile.example" / "state" / "job_search_tracker.csv").write_text(
        "date,company\n", encoding="utf-8")
    assert subprocess.run(["git", "init", "-q", "-b", "master", str(app)]).returncode == 0
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "the app")
    _git(app, "tag", "v1.0.0")
    (app / "tools" / "x.py").write_text("a = 2\n", encoding="utf-8")
    _git(app, "commit", "-qam", "after the release")
    monkeypatch.setattr(rehearse_sync, "HERE", str(app))
    # The rehearsal's own environment, in a home with no git identity, as on CI's machines.
    env = rehearse_sync._env(False, "file:///none", str(tmp_path / "home"))
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    assert rehearse_sync._seed_fresh("v1.0.0", str(tmp_path), env) == ""
    seed = tmp_path / "seed"
    # The release's tree, one commit as the template makes it, then their setup.
    assert (seed / "tools" / "x.py").read_text(encoding="utf-8") == "a = 1\n"
    assert _git(seed, "log", "--format=%s").stdout.split("\n")[:2] == ["set me up",
                                                                       "Initial commit"]
    assert (seed / "profile" / "person.json").is_file()
    assert (seed / "job_search_tracker.csv").is_file()
    assert (seed / "README.md").read_text(encoding="utf-8") == "The app.\n"
    assert (seed / "profile" / "tests" / "test_my_search.py").is_file()
    assert _git(seed, "status", "--porcelain").stdout == ""
    # A release this app never made is said plainly, and nothing is made.
    monkeypatch.setattr(rehearse_sync, "HERE", ROOT)
    assert rehearse_sync.fresh("v0.0.0-never", "HEAD", ci=False, keep=False) == 2


def test_fresh_takes_no_repository_and_a_plain_run_needs_one(capsys):
    import pytest
    with pytest.raises(SystemExit):
        rehearse_sync.main(["somewhere", "--fresh", "v4.14.0"])
    with pytest.raises(SystemExit):
        rehearse_sync.main([])


def test_a_page_that_is_due_with_no_build_printed_fails_the_rehearsal(tmp_path):
    reh = rehearse_sync.Rehearsal()
    due = "app start: set up, page to publish\nClaude, do this:\n1. Carry on.\n"
    rehearse_sync._page_plan(reh, "cloud", str(tmp_path), {}, str(tmp_path), due)
    assert [(s[1], s[2]) for s in reh.steps] == [("the steps name the page's build", False)]
    # Nothing about the page due: nothing to build, nothing said.
    reh = rehearse_sync.Rehearsal()
    rehearse_sync._page_plan(reh, "cloud", str(tmp_path), {}, str(tmp_path),
                             "app start: set up\nClaude, do this:\n1. Carry on.\n")
    assert reh.steps == []
