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
