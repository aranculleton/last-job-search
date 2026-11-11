"""A new chat starts on the newest version its copy follows, and an open chat checks once a day.

The maintainer, 2026-11-11: their copy follows the app's master, which moves many times a day,
and expects it "always up to date with master", yet a new chat started on a day already checked
was told "already checked today" and worked on the version from the morning. Now the start of
a new chat (`app.py start`) takes one look at the app (`git ls-remote`: one round trip, nothing
fetched) and, only where what the copy follows moved past its last merge, runs the full check
(`sync_app.py --if-moved`). A chat already open keeps `--if-stale`'s once a day, and no other
path looks: an hourly check was wasteful (the maintainer, the same day). The same for every
copy: on releases, the newest release is what moves.

Each test is the real path on two throwaway repositories (tests/test_sync_app.py): a bare-bones
app, with the start's own tools in it, as the app remote, and a person's copy made from it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_sync_app import ENV, commit, read, run, sh, write  # noqa: E402

# What `import app` needs, and the sync it runs.
TOOLS = ("app.py", "person.py", "python_floor.py", "local_path.py", "place.py", "sync_app.py",
         "personal_paths.py")


@pytest.fixture
def copies(tmp_path):
    app = str(tmp_path / "app")
    os.makedirs(app)
    sh(app, "git", "init", "-q", "-b", "master")
    for tool in TOOLS:
        write(app, f"tools/{tool}", read(ROOT, f"tools/{tool}"))
    write(app, ".gitignore", "__pycache__/\n")
    write(app, "README.md", "v1\n")
    write(app, "CHANGELOG.md", "# Changelog\n")
    commit(app, "app v1")
    me = str(tmp_path / "me")
    sh(str(tmp_path), "git", "clone", "-q", app, me)
    sh(me, "git", "remote", "remove", "origin")
    origin = str(tmp_path / "origin.git")
    sh(str(tmp_path), "git", "init", "-q", "--bare", "-b", "master", origin)
    sh(me, "git", "remote", "add", "origin", origin)
    write(me, "profile/person.json", json.dumps({"app_channel": "master"}) + "\n")
    commit(me, "set me up")
    sh(me, "git", "push", "-q", "origin", "master")
    rc, out = run(me, app)                               # the day's check, this morning
    assert rc == 0, out
    return app, me


def _probe(me, app, code):
    r = subprocess.run([sys.executable, "-c", "import sys, json; sys.path.insert(0, 'tools'); "
                        + code], cwd=me, env=dict(ENV, LJS_APP_URL=app), text=True,
                       encoding="utf-8", errors="replace", capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _days_check(me, app, new_chat):
    return _probe(me, app, "import app; print(json.dumps(app.days_check('m', '', 'none', "
                           f"new_chat={new_chat})))")


def _seen(me):
    return sh(me, "git", "rev-parse", "refs/remotes/app/master").strip()


def test_a_new_chat_takes_what_moved_and_an_open_chat_waits_for_tomorrow(copies):
    app, me = copies
    write(app, "README.md", "v2\n")
    commit(app, "app v2, merged this afternoon")
    seen = _seen(me)
    # A chat already open: the day's check ran, so nothing is looked at or taken.
    assert _days_check(me, app, False) == {"ran": False}
    rc, out = run(me, app, "--if-stale")
    assert rc == 0 and "already checked today" in out and read(me, "README.md") == "v1\n"
    # The look itself fetches nothing: it only says the app moved.
    assert _probe(me, app, "import sync_app; print(json.dumps(sync_app.moved()))") is True
    assert _seen(me) == seen
    # A new chat: the full check, and the new version.
    got = _days_check(me, app, True)
    assert got["ran"] and got["rc"] == 0 and got["landed"], got
    assert read(me, "README.md") == "v2\n"
    # Nothing moved since: the next new chat looks, finds nothing, and runs nothing.
    assert _days_check(me, app, True) == {"ran": False}


def test_on_releases_only_a_new_release_moves(copies):
    app, me = copies
    write(me, "profile/person.json", json.dumps({"app_channel": "stable"}) + "\n")
    commit(me, "releases only")
    sh(app, "git", "tag", "v1.0.0")
    write(app, "README.md", "v2, not released\n")
    commit(app, "after the release")
    assert _days_check(me, app, True) == {"ran": False}
    assert read(me, "README.md") == "v1\n"
    sh(app, "git", "tag", "-a", "v1.1.0", "-m", "1.1.0")      # an annotated tag, as a cut makes
    got = _days_check(me, app, True)
    assert got["ran"] and got["rc"] == 0, got
    assert read(me, "README.md") == "v2, not released\n"
    assert _days_check(me, app, True) == {"ran": False}


def test_where_updates_wait_a_version_already_seen_is_no_news(copies):
    app, me = copies
    write(me, "profile/person.json", json.dumps({"app_channel": "master",
                                                 "app_updates": "when_asked"}) + "\n")
    commit(me, "updates wait for my word")
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    got = _days_check(me, app, True)
    assert got["ran"] and "An update is waiting" in got["said"], got
    assert read(me, "README.md") == "v1\n"
    assert _days_check(me, app, True) == {"ran": False}


def test_an_app_that_cannot_be_reached_never_holds_the_start(copies, tmp_path):
    _app, me = copies
    assert _days_check(me, str(tmp_path / "no-such-app"), True) == {"ran": False}


def test_a_check_that_just_failed_is_not_tried_again_by_every_new_chat(copies):
    app, me = copies
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    write(me, ".git/ljs-last-sync-tried", "%d\n" % int(time.time()))   # failed a minute ago
    assert _days_check(me, app, True) == {"ran": False}
    write(me, ".git/ljs-last-sync-tried", "%d\n" % int(time.time() - 4 * 3600))
    assert _days_check(me, app, True)["ran"]
    assert read(me, "README.md") == "v2\n"
