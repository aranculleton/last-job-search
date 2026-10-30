"""tools/push_gate.sh, the maintainer's one command before a push to the public app.

Before 4.3 each session rebuilt this gate from memory and ran the whole suite by hand three
times (an hour, the maintainer, 2026-10-29). What it must always do is pinned here: scan the
exact tree, every patch, the commit messages and any text to be posted against the
maintainer's denylist, run the name guard and the version note, stop at the first failure, push
only after every step passed, and never force. Every other test, browser tests included, is CI's.
"""
from __future__ import annotations

import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "tools", "push_gate.sh")
SRC = open(GATE, encoding="utf-8").read()


# The maintainer's tools run on Linux or a Mac (and CI's Linux); on Windows `bash` is the
# Linux subsystem's stub, which has no Linux installed on a runner (2026-10-29).
@pytest.mark.skipif(os.name == "nt", reason="a maintainer's tool, run on Linux or a Mac")
def test_it_is_valid_bash_and_says_how_to_run_it_without_a_repo():
    assert subprocess.run(["bash", "-n", GATE]).returncode == 0
    got = subprocess.run(["bash", GATE], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", cwd=ROOT)
    assert got.returncode == 2 and "usage: tools/push_gate.sh" in got.stdout


def test_it_scans_everything_that_goes_public_against_the_denylist():
    for what in ('"$WORK/tree" --tokens', '"$WORK/patches.txt" --tokens',
                 '"$WORK/messages.txt" --tokens', '--text "$t" --tokens',
                 "name_guard.py diff origin/master", 'name_guard.py text "$WORK/messages.txt"',
                 "build_app.py"):
        assert what in SRC, what


def test_it_pushes_only_after_every_step_and_never_with_force():
    code = "\n".join(ln for ln in SRC.splitlines() if not ln.lstrip().startswith("#"))
    pushes = [ln for ln in code.splitlines() if "git push" in ln]
    assert len(pushes) == 1 and not any(f in pushes[0] for f in ("--force", " -f ", "+HEAD", "+refs"))
    # Every step comes before the push, and a step that fails stops the gate there.
    push = code.index("git push")
    last_step = max(i for i, ln in enumerate(code.splitlines()) if ln.startswith("step "))
    assert sum(len(ln) + 1 for ln in code.splitlines()[:last_step]) < push
    body = code[code.index("step() {"):code.index("\n}", code.index("step() {"))]
    assert "exit 1" in body and "Nothing pushed" in body


def test_it_checks_privacy_then_names_then_the_version_note_and_runs_no_other_tests():
    """The maintainer, 2026-10-29: the gate stops at the first failure, checks the private data,
    the names and the version note first, and leaves every other test to CI, which runs the
    whole suite on the pull request anyway."""
    order = ['"$WORK/patches.txt" --tokens', "name_guard.py diff origin/master",
             "tests/test_build_versions.py", "tools/lint_skills.py"]
    at = [SRC.index(o) for o in order]
    assert at == sorted(at), order
    code = "\n".join(ln for ln in SRC.splitlines() if not ln.lstrip().startswith("#"))
    runs = [ln for ln in code.splitlines() if "pytest" in ln]
    assert len(runs) == 1 and "tests/test_build_versions.py" in runs[0], runs
    assert '"$BASE..HEAD"' in SRC, "the scans still read every patch since master"
