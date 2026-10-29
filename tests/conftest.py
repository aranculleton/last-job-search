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
# Pages tools/company_research.py fetched, kept for the quote check: the tests' own, never
# the machine's shared folder a real research run uses.
_pages = tempfile.mkdtemp(prefix="ljs_pages_")
os.environ["LJS_RESEARCH_PAGES"] = _pages
atexit.register(shutil.rmtree, _pages, ignore_errors=True)

# The networking limits are read from the profile when their module is first imported, and
# the app reaches that module by two names (`schema`, and `network.schema` from the page's
# model). Both are imported here, under the example, so a test that points LJS_PROFILE at a
# free plan for a moment cannot fix the limits for every test after it in the same worker
# (2026-10-29: a 209-character follow-up was checked against 180 on one parallel run and
# 280 on another). A test that changes the plan reloads both (reload_limits below).
import sys  # noqa: E402
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import schema as _schema  # noqa: E402,F401
from network import schema as _network_schema  # noqa: E402,F401


def _reload_limits():
    """Re-read the networking limits under both of the module's names, from whatever profile
    LJS_PROFILE now names: after a test switches the plan, and again when it switches back."""
    import importlib
    for name in ("schema", "network.schema"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    return sys.modules["schema"]


import pytest  # noqa: E402


# Speed limits are measured on a quiet machine. In parallel workers (pytest-xdist) every
# worker shares the runner's cores, and a build that takes 1.5s alone read 2.6s of its own
# processor time on Python 3.9 (2026-10-29): no clock is immune to cores shared by four
# workers. So a test marked `timing` is skipped in the workers and run once, alone, when the
# parallel run ends, and its result decides the run as any other test's does. Run without
# workers, it runs in place as before.
def pytest_configure(config):
    config.addinivalue_line("markers", "timing: a speed limit, measured alone after a parallel run")


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        return
    later = pytest.mark.skip(reason="a speed limit: timed alone once the parallel run ends")
    for item in items:
        if item.get_closest_marker("timing"):
            item.add_marker(later)


def pytest_sessionfinish(session, exitstatus):
    import subprocess
    config = session.config
    if os.environ.get("PYTEST_XDIST_WORKER") or hasattr(config, "workerinput"):
        return
    if not getattr(config.option, "numprocesses", None) or getattr(config.option, "markexpr", ""):
        return
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider", "-m", "timing",
           "-rf", "--tb=short", *config.args]
    got = subprocess.run(cmd, cwd=str(config.invocation_params.dir), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    report = config.pluginmanager.get_plugin("terminalreporter")
    lines = [ln for ln in (got.stdout + got.stderr).splitlines() if ln.strip()]
    if report is not None:
        report.write_sep("-", "speed limits, timed alone")
        for ln in (lines if got.returncode not in (0, 5) else lines[-1:]):
            report.write_line(ln)
    if got.returncode not in (0, 5) and session.exitstatus == 0:
        session.exitstatus = 1


@pytest.fixture
def reload_limits():
    """_reload_limits, for a test that switches the plan: call it after, and again after
    switching back."""
    return _reload_limits


@pytest.fixture
def judged(tmp_path, monkeypatch):
    """`judged("Kestrel Mutual", ...)`: employers the example person has judged against
    their bar (`bar.py judge`), kept in a file of the test's own. Nobody at an employer
    nobody has judged is shown as someone to write to (tools/network/surface.py), so a test
    of who is shown at an invented employer judges it first, as a run does."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import bar
    monkeypatch.setattr(bar, "_judged_path", lambda: str(tmp_path / "employers_judged.json"))
    bar._judged_cache.clear()

    def judge(*companies, verdict="prestige"):
        for company in companies:
            bar.judge(company, verdict, "an invented employer the example person judged",
                      today="2026-10-23")
    yield judge
    bar._judged_cache.clear()


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
    state; `sync_rc` is what the look or the update returns. For checking what a run does
    after it succeeds by running it."""
    import sys
    import types
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    steps = []
    state = {"stale": True, "sync_rc": 0}

    def step(name, value=None):
        return lambda *a, **k: steps.append(name) or value
    for name in ("_record_check", "own_tests", "app_watch", "network_check", "model_check",
                 "place_check", "upgrades"):
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
    monkeypatch.setattr(sync_app, "look", lambda: steps.append("look") or state["sync_rc"])
    monkeypatch.setattr(sync_app, "git",
                        lambda *a, **k: types.SimpleNamespace(stdout="", returncode=0))

    def run(*argv, **set_state):
        state.update(set_state)
        steps.clear()
        return sync_app.main(list(argv)), list(steps)
    return run
