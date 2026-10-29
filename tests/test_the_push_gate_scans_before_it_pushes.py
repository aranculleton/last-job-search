"""tools/push_gate.sh, the maintainer's one command before a push to the public app.

Before 4.3 each session rebuilt this gate from memory and ran the whole suite by hand three
times (an hour, the maintainer, 2026-10-29). What it must always do is pinned here: scan the
exact tree, every patch, the commit messages and any text to be posted against the
maintainer's denylist, run the name guard, push only after every step passed, and never force.
The whole suite, browser tests included, is CI's (ci.yml `page`).
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
    push = code.index("git push")
    assert code.index('if [ -n "$failed" ]') < push and "exit 1" in code[code.index('if [ -n "$failed" ]'):push]


def test_the_browser_tests_it_leaves_out_are_the_ones_ci_runs():
    """The gate skips the page's browser tests because CI's page job runs them: the two pick
    them with the same pattern, so a browser test is never left to neither."""
    yaml = pytest.importorskip("yaml")
    ci = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8"))
    run = ci["jobs"]["page"]["steps"][-1]["run"]
    pattern = run.split("grep -lE '", 1)[1].split("'", 1)[0]
    assert pattern in SRC


def test_a_follow_up_push_tests_only_what_changed_since_the_last_one():
    """The branch's last push passed this gate and its CI runs the whole suite, so a one-line
    fix re-tests that line's tests, not the release's (2026-10-29: five minutes, and a timing
    test tipped over by the load). The scans still read every patch since master."""
    assert 'merge-base --is-ancestor "origin/$BRANCH" HEAD' in SRC
    assert 'git diff --name-only "$TBASE" HEAD' in SRC
    assert '"$BASE..HEAD"' in SRC and "name_guard.py diff origin/master" in SRC
