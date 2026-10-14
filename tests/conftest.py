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
