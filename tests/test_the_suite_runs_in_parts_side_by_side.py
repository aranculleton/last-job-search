"""CI runs the suite on three runners side by side, the Python 3.9 leg on three more and the
page's browser tests on two, each runner taking its own part of the test files.

On one runner the suite took a median 9 minutes on Python 3.13 and up to 15 on 3.9, one 3.9
run stopped at its limit, and the browser tests took up to 15 (2026-11-11): every merge waited
for the slowest. Split by tools/ci_plan.py `part`, every test file runs in exactly one part,
the split is the same on every runner, and the checks that take seconds (lint, guards, the
portal CLIs) run once, never once a part. A private copy run by hand takes one part, the
whole suite, so its bill does not triple.
"""
from __future__ import annotations

import os
import random
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import ci_plan  # noqa: E402

import workflow_runs as W  # noqa: E402

SPLIT = {"suite": 3, "python-floor": 3, "page": 2}


def _browser_files() -> list[str]:
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
        pattern = re.search(r"grep -lE '([^']+)' tests/\*\.py", fh.read()).group(1)
    picks = re.compile(pattern)
    out = []
    for f in ci_plan.every_test(ROOT):
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            if picks.search(fh.read()):
                out.append(f)
    return out


def test_pytest_collects_only_the_files_the_split_knows():
    """The split lists tests/test_*.py; a test file anywhere else would be in no part."""
    stray = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
        for f in files:
            top = os.path.samefile(base, os.path.join(ROOT, "tests"))
            if f.endswith("_test.py") or (f.startswith("test_") and f.endswith(".py") and not top):
                stray.append(os.path.relpath(os.path.join(base, f), ROOT))
    assert stray == [], stray


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_every_test_file_runs_in_exactly_one_part(n):
    every = ci_plan.every_test(ROOT)
    parts = [ci_plan.part(f"{k}/{n}", root=ROOT) for k in range(1, n + 1)]
    files = [f for p in parts for f in p]
    assert sorted(files) == every and len(set(files)) == len(files)
    assert all(parts), "no part is empty"


def test_the_browser_files_split_in_two_without_a_gap_or_a_repeat():
    browser = _browser_files()
    assert len(browser) > 10
    halves = [ci_plan.part(f"{k}/2", browser, ROOT) for k in (1, 2)]
    assert sorted(halves[0] + halves[1]) == sorted(browser)
    assert not set(halves[0]) & set(halves[1])


def test_every_runner_splits_the_same_way_whatever_order_it_lists_the_files():
    browser = _browser_files()
    shuffled = browser[:]
    random.Random(7).shuffle(shuffled)
    assert ci_plan.part("1/2", shuffled, ROOT) == ci_plan.part("1/2", browser, ROOT)
    assert ci_plan.part("2/3", root=ROOT) == ci_plan.part("2/3", ci_plan.every_test(ROOT), ROOT)


def test_a_part_that_does_not_exist_stops_the_job_rather_than_running_everything():
    """`files=$(... part 4/3)` must fail the step: an empty list would hand pytest no files,
    and pytest with no files runs the whole tree."""
    for shard in ("4/3", "0/3", "", "half"):
        got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "ci_plan.py"), "part",
                              shard], capture_output=True, text=True, encoding="utf-8",
                             cwd=ROOT)
        assert got.returncode == 2 and got.stdout == "", shard


def _matrix(job: dict, private: bool) -> list:
    expr = job["strategy"]["matrix"]["part"]
    return W.evaluate(expr, {"github": W.event("pull_request", private=private)})


def test_ci_runs_every_part_and_a_private_copy_one():
    jobs = W.load("ci.yml")["jobs"]
    for name, n in SPLIT.items():
        job = jobs[name]
        assert _matrix(job, private=False) == list(range(1, n + 1)), name
        assert _matrix(job, private=True) == [1], name
        assert job["strategy"]["fail-fast"] is False, name
        runs = "\n".join(str(s.get("run", "")) for s in job["steps"])
        assert "tools/ci_plan.py part ${{ matrix.part }}/${{ strategy.job-total }}" in runs, name
        assert "${{ matrix.part }}" in job["name"] and "${{ strategy.job-total }}" in job["name"]
        # A failed split fails the step: the list is taken first, never inside pytest's line.
        assert re.search(r"(?m)^\s*(files|mine)=\$\(python tools/ci_plan\.py part ", runs), name
    assert ci_plan.part("1/1", root=ROOT) == ci_plan.every_test(ROOT)


def test_a_persons_own_tests_run_in_one_part_only():
    jobs = W.load("ci.yml")["jobs"]
    for name in ("suite", "python-floor"):
        own = [s for s in jobs[name]["steps"] if "profile/tests" in str(s.get("run", ""))]
        assert own and all(str(s["if"]).startswith("matrix.part == 1 && ") for s in own), name


def test_the_quick_checks_run_once_not_in_every_part():
    jobs = W.load("ci.yml")["jobs"]
    once = ("tools/lint_skills.py", "ruff check", "tools/security_guards.py",
            "tools/leak_scan.py", "tools/name_guard.py", "bun run typecheck",
            "tools/check_framework_version.py")
    for name, job in jobs.items():
        runs = "\n".join(str(s.get("run", "")) for s in job.get("steps", []))
        for check in once:
            assert (check in runs) == (name == "checks"), (name, check)
    assert "strategy" not in jobs["checks"]


def test_fast_checks_waits_for_every_part():
    jobs = W.load("ci.yml")["jobs"]
    needs = jobs["fast"]["needs"]
    assert {"checks", "suite", "python-floor", "page", "latex-smoke"} <= set(needs)


def test_a_part_has_room_but_a_hang_is_still_stopped():
    jobs = W.load("ci.yml")["jobs"]
    for name in SPLIT:
        assert 10 <= jobs[name]["timeout-minutes"] <= 20, name
