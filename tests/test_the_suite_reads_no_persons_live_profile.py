"""The app's suite gives the app's answer whatever the checkout's own profile says.

`tools/ci_local.sh` runs this suite inside a person's copy, which has a `profile/` of its own.
In a copy whose person waits for their word on updates (`"app_updates": "when_asked"`), a test
of the sync read that live setting and failed: the `sync_steps` fixture never stood in for
`sync_app.updates`, which reads `profile/person.json` beside the tools (audit SV-4,
2026-11-10). Here the tests that drive the sync are run in a copy of this checkout whose own
person waits for their word, and they must pass as they do in the app. Invented data only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")


def _sync_step_tests() -> list[str]:
    """Every test that drives the sync through the `sync_steps` fixture, by its pytest id."""
    out = []
    for name in sorted(os.listdir(TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")) or name == os.path.basename(__file__):
            continue
        with open(os.path.join(TESTS, name), encoding="utf-8") as fh:
            text = fh.read()
        out += [f"tests/{name}::{m.group(1)}"
                for m in re.finditer(r"^def (test_\w+)\([^)]*\bsync_steps\b", text, re.M)]
    return out


def _copy_that_waits(tmp_path) -> str:
    """This checkout as a person's copy would hold it, every file the app's own (linked, not
    copied), and a profile of an invented person who chose to say when updates come."""
    copy = tmp_path / "copy"
    copy.mkdir()
    try:
        for name in os.listdir(ROOT):
            if name in ("profile", ".git", ".pytest_cache", "__pycache__"):
                continue
            os.symlink(os.path.join(ROOT, name), copy / name)
    except (OSError, NotImplementedError):
        pytest.skip("this computer does not let a test make links")
    shutil.copytree(os.path.join(ROOT, "profile.example"), copy / "profile",
                    ignore=shutil.ignore_patterns("state", "tests", "__pycache__"))
    p = copy / "profile" / "person.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["app_updates"] = "when_asked"
    p.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return str(copy)


def test_the_tests_that_drive_the_sync_pass_in_a_copy_that_waits_for_its_person(tmp_path):
    ids = _sync_step_tests()
    assert ids, "no test drives the sync through sync_steps any more: point this at the ones that do"
    copy = _copy_that_waits(tmp_path)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTEST_", "LJS_")) and k != "COV_CORE_SOURCE"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-p", "no:randomly", *ids], cwd=copy, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    assert f"{len(ids)} passed" in r.stdout, r.stdout[-1500:]
