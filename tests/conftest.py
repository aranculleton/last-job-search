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
import sys
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
# The suite gives CI's answer wherever it runs: a cloud chat's own marker would add the cards
# a cloud copy shows (choosing Auto, the PDF tools' line) to every model the tests build. A
# test of a cloud chat sets it itself.
os.environ.pop("CLAUDE_CODE_REMOTE", None)
# And a test that does set it is a cloud chat on every computer: a cloud chat is told by its
# container's own markers as well (place.in_cloud), which CI's runners do not have and a cloud
# container does. A test of a session over Remote Control clears them itself.
os.environ["CLAUDE_CODE_CONTAINER_ID"] = "container_tests"
# Nor a chat's on a computer: Claude Code's CLAUDECODE makes a save end at its push there
# (land.on_computer). A test of a computer chat sets it itself.
os.environ.pop("CLAUDECODE", None)
# Nor which chat runs the tests: a claim is decided by this chat's own id (app_listen.this_chat),
# and a developer's session id passed a test locally that failed on GitHub (2026-11-11). A test
# of one chat says which with LJS_CHAT or --chat.
for _k in ("LJS_CHAT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
           "CLAUDE_CODE_BRIDGE_SESSION_ID"):
    os.environ.pop(_k, None)
# A landing in a test never opens or merges a pull request on GitHub (tools/land.py
# _github_here): a test that checks that step hands the landing a stand-in.
os.environ["LJS_LAND_NO_GITHUB"] = "1"
# Nor does the app's hook start a landing in a test's copy (learned._save_now): it asks for one,
# as it did before it started them itself. A test of that step unsets this.
os.environ["LJS_HOOK_NO_SAVE"] = "1"
atexit.register(shutil.rmtree, _state, ignore_errors=True)
# The checkout the suite runs in is read as the app's own, wherever it is. In a person's copy
# (ci_local.sh runs this suite there; the computer check runs it in one cloned from a folder)
# the day's update check is the copy's, and where it has not run that day, start, a wake and
# the hooks put it first (app_setup._sync_stale), so a test read the copy's day rather than
# the app's answer (2026-11-04). There the app's address is this checkout's own; in the app
# itself nothing changes.
import subprocess  # noqa: E402
_origin = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
if _origin.returncode == 0 and _origin.stdout.strip():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app as _sync_app  # noqa: E402
    if not _sync_app.is_the_app(ROOT):
        os.environ["LJS_APP_URL"] = _origin.stdout.strip()
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
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import schema as _schema  # noqa: E402,F401
from network import schema as _network_schema  # noqa: E402,F401
# The message log's module is reached by two names as well (`state`, and `network.state` from
# followup_drafts and the page's model), and each fixes its file paths when first imported.
# Imported here, under the tests' own state, so a test that points LJS_STATE at a folder of its
# own for a moment cannot leave one name reading that folder, deleted, for every test after it
# in the same worker (the review, 2026-11-10: the referral-ask tests failed after the interview
# pack's, which first imported network.state inside a fixture of its own).
import state as _state_module  # noqa: E402,F401
from network import state as _network_state  # noqa: E402,F401


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


@pytest.fixture(autouse=True)
def _each_test_starts_clean():
    """Every test starts with the suite's own profile and state, and none of the checkout's own
    records another test left. Each worker keeps one state folder for its whole run, and a
    checkout's records live there when it is not a git checkout (app_listen.checkout_file: the
    listener it last saw, when it last asked for a fresh helper, the chats marked nested):
    one test's renewal made a later one find none, and a test that set LJS_PROFILE by hand and
    popped it left the next with no profile at all. Both passed alone and failed beside others
    under load."""
    clean_start()
    yield
    os.environ["LJS_PROFILE"] = EXAMPLE
    os.environ["LJS_STATE"] = _state
    try:
        import person
        person.reset()
    except Exception:  # noqa: BLE001  not imported by this test
        pass


def clean_start() -> None:
    """What every test starts with (_each_test_starts_clean): the checkout's own records in
    the worker's state folder cleared, and the suite's profile and state set again."""
    for name in os.listdir(_state):
        if name.startswith(".ljs-"):
            try:
                os.remove(os.path.join(_state, name))
            except OSError:
                pass
    os.environ["LJS_PROFILE"] = EXAMPLE
    os.environ["LJS_STATE"] = _state


@pytest.fixture(autouse=True)
def _no_skill_answered_yet():
    """Every test starts with no skill answered. The person's one answer per skill
    (tools/skill_answers.py) lives in the suite's one state folder, so a yes one test recorded
    was the next test's answer before it asked."""
    try:
        os.remove(os.path.join(_state, "documents", "skill_answers.json"))
    except OSError:
        pass
    yield


@pytest.fixture(autouse=True)
def _limits_as_the_profile_says():
    """Every test starts with the networking limits and the follow-up rule as the profile in
    use says them (schema.limits_now reads them again when the settings change): a test that
    pointed LJS_PROFILE at a copy of its own left them read from it, and a later test's own
    rule (monkeypatched) was read over from the example mid-test."""
    for name in ("schema", "network.schema"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "limits_now"):
            try:
                mod.limits_now()
            except Exception:  # noqa: BLE001  a test of a profile with no settings: as it was
                pass
    yield


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
    for name in ("_record_check", "own_tests", "own_tests_later", "app_watch", "network_check", "model_check",
                 "place_check", "upgrades"):
        monkeypatch.setattr(sync_app, name, step(name))
    monkeypatch.setattr(sync_app, "is_the_app", lambda: False)
    # A run that does not finish stamps when it was tried in the checkout's own git folder:
    # here that is the real checkout's, never the tests' to write to.
    monkeypatch.setattr(sync_app, "_record_tried", lambda *a, **k: None)
    monkeypatch.setattr(sync_app, "own_folder", lambda: "")
    monkeypatch.setattr(sync_app, "stale", lambda: state["stale"])
    # The app's default, never the checkout's own profile: in a person's copy whose person
    # waits for their word, the day's run was a look and a test of the sync failed (audit
    # SV-4). A test of the other choice sets it itself.
    monkeypatch.setattr(sync_app, "updates", lambda: "auto")
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
