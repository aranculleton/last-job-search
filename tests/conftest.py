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
def boards_web(monkeypatch):
    """openroles' network replaced with canned answers, for the employer-board readers.

    `routes` maps a URL substring to an answer (JSON, text, or (None, "HTTP 404"), or a
    function of (url, payload)); `robots` maps a host to (status, body); `calls` records
    every (url, payload) sent. Nothing reaches the network.
    """
    import json
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from openroles import _http
    routes: dict = {}
    robots: dict = {}
    calls: list = []

    def request(url, payload=None, accept="application/json"):
        calls.append((url, payload))
        for key, answer in routes.items():
            if key in url:
                if callable(answer):
                    answer = answer(url, payload)
                return answer if isinstance(answer, tuple) else (answer, None)
        return None, "HTTP 404"

    def request_raw(url, payload=None, accept="*/*", limit=0):
        data, err = request(url, payload)
        return (data if isinstance(data, str) else json.dumps(data)), err

    monkeypatch.setattr(_http, "RETRY_PAUSE", 0)
    monkeypatch.setattr(_http, "request", request)
    monkeypatch.setattr(_http, "request_raw", request_raw)
    monkeypatch.setattr(_http, "robots_txt", lambda host: robots.get(host, (404, "")))
    return type("BoardsWeb", (), {"routes": routes, "robots": robots, "calls": calls})
