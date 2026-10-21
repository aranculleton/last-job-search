"""Every test in tests/ runs against the example person, never a real one.

The app's suite has to give the same answer in the public app (which ships no
profile and no state) and in a person's own repo (which has both). So before any
tool is imported, the profile is pinned to `profile.example/` and the state to a
fresh temporary copy of `profile.example/state/`: a test can read and write the
tracker, the contact book and documents/ without touching anybody's real ones.

A person's own tests, the ones that pin their data, live in `profile/tests/`
and run in a separate process against their profile (tools/ci_local.sh runs both).
The tools read the profile once, at import, so the two suites cannot share one
interpreter.
"""
import atexit
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "profile.example")

os.environ["LJS_PROFILE"] = EXAMPLE
_state = tempfile.mkdtemp(prefix="ljs_state_")
shutil.copytree(os.path.join(EXAMPLE, "state"), _state, dirs_exist_ok=True)
os.environ["LJS_STATE"] = _state
# A ledger the person exported for their own reads is never the tests' to write to: with it
# unset, the ledger lives under the tests' own state.
os.environ.pop("LJS_LEDGER", None)
atexit.register(shutil.rmtree, _state, ignore_errors=True)


import pytest  # noqa: E402


@pytest.fixture
def boards_web():
    """openroles' network replaced with canned answers, for the employer-board readers,
    through tools/offline_boards.py: the seam a person's own tests use too. `routes`,
    `robots` and `calls` as that file says."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from offline_boards import offline
    with offline() as web:
        yield web


@pytest.fixture
def drive_round(tmp_path, monkeypatch):
    """Run tools/run_round.py's main with every stage stood in, and say what it ran.

    Returns `drive(*argv) -> (calls, spawned)`: each stage as (argv, deadline), and the
    argv of any wider round it started. Each stand-in writes empty outputs, so the round
    goes on to its end. For checking what the round hands each stage, by running it,
    rather than by searching its source for how a call is spelled."""
    import json
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import run_round
    import sync_app
    calls, spawned = [], []

    def fake_run(cmd, log, deadline=None, ok=(0,)):
        calls.append((list(cmd), deadline))
        for flag in ("--out", "--dropped", "--out-all", "--skipped"):
            if flag in cmd:
                dest = cmd[cmd.index(flag) + 1]
                if cmd[1].endswith("scrape_wide.py"):
                    os.makedirs(dest, exist_ok=True)
                    dest = os.path.join(dest, "kept.json")
                with open(dest, "w", encoding="utf-8") as fh:
                    json.dump([], fh)
        return 0

    monkeypatch.setattr(run_round, "run", fake_run)
    monkeypatch.setattr(run_round.subprocess, "call",
                        lambda cmd, *a, **k: spawned.append(list(cmd)) or 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    monkeypatch.setattr(sync_app, "nudge", lambda *a, **k: None)

    def drive(*argv):
        calls.clear()
        spawned.clear()
        monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                          "--summary-dir", str(tmp_path / "summary"),
                                          "--today", "2026-10-20", *argv])
        run_round.main()
        return list(calls), list(spawned)
    return drive


@pytest.fixture
def sync_steps(monkeypatch):
    """tools/sync_app.py's main with git and the network stood in: returns `run(*argv)`
    -> (exit code, the steps it took, in order). `stale` and `sync_rc` set the day's
    state. For checking what a sync does after it succeeds by running it."""
    import sys
    import types
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    steps = []
    state = {"stale": True, "sync_rc": 0}

    def step(name, value=None):
        return lambda *a, **k: steps.append(name) or value
    for name in ("_record_check", "own_tests", "app_watch", "model_check", "place_check",
                 "upgrades"):
        monkeypatch.setattr(sync_app, name, step(name))
    monkeypatch.setattr(sync_app, "is_the_app", lambda: False)
    monkeypatch.setattr(sync_app, "own_folder", lambda: "")
    monkeypatch.setattr(sync_app, "stale", lambda: state["stale"])
    monkeypatch.setattr(sync_app, "_dirty", lambda: False)
    monkeypatch.setattr(sync_app, "pull_master", step("pull_master", 0))
    monkeypatch.setattr(sync_app, "fetch", step("fetch", None))
    monkeypatch.setattr(sync_app, "follow", lambda: "following the app")
    monkeypatch.setattr(sync_app, "app_portals", lambda: [])
    monkeypatch.setattr(sync_app, "sync", lambda: steps.append("sync") or state["sync_rc"])
    monkeypatch.setattr(sync_app, "git",
                        lambda *a, **k: types.SimpleNamespace(stdout="", returncode=0))

    def run(*argv, **set_state):
        state.update(set_state)
        steps.clear()
        return sync_app.main(list(argv)), list(steps)
    return run
