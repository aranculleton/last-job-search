"""A container that already has every package asks the package index nothing.

Audit E-12 (2026-11-10): `tools/setup_env.sh --python` took 8.2 to 8.7 seconds on a ready
container on every brief run, 4 to 5 of them an unconditional `pip3 install --upgrade cffi`
against the package index. cffi is still upgraded first where anything fails to import (pypdf
panics on a broken one), and never where everything is here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(tmp_path, ready: bool):
    """setup_env.sh --python in a cloud chat, with a pip3 that writes down what it is asked and
    a python3 whose imports all work (or all fail)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "pip.log"
    (bin_ / "pip3").write_text("#!/bin/sh\necho \"$*\" >> %s\n" % log, encoding="utf-8")
    real = sys.executable
    (bin_ / "python3").write_text(
        "#!/bin/sh\ncase \"$*\" in\n"
        "  *import*|*'-m ruff'*|'-m ruff --version') exit %d ;;\n"
        "esac\nexec %s \"$@\"\n" % (0 if ready else 1, real), encoding="utf-8")
    for f in ("pip3", "python3"):
        (bin_ / f).chmod(0o755)
    env = dict(os.environ, PATH=str(bin_) + os.pathsep + os.environ.get("PATH", ""),
               CLAUDE_CODE_REMOTE="true")
    subprocess.run(["bash", os.path.join(ROOT, "tools", "setup_env.sh"), "--python"], cwd=ROOT,
                   env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=120)
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="a cloud container's shell")
def test_a_ready_container_runs_no_pip(tmp_path):
    assert _run(tmp_path, ready=True) == []


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="a cloud container's shell")
def test_a_container_missing_something_upgrades_cffi_first(tmp_path):
    asked = _run(tmp_path, ready=False)
    assert asked and asked[0].endswith("--upgrade cffi"), asked
