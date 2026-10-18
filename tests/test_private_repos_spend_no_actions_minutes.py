"""A private copy of this repo spends no GitHub Actions minutes unless asked.

GitHub bills private repos per job, rounded up to the minute, and gives public
repos their minutes free. A monthly allowance runs out faster than it looks: a
routine that opens one PR a day for files no check reads still bills every job
of every run. So every CI job runs on a public repo (the app) or on a manual
dispatch, and `./tools/ci_local.sh` is CI everywhere else.

These pin the three things that keep that true: every job is gated, every job
has a timeout (the default is 360 minutes), and superseded runs are cancelled.
"""
import pathlib

import pytest

# The 3.10 leg installs pytest and nothing else.
yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"


def _load(name):
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def test_every_ci_job_is_skipped_on_a_private_repo_unless_dispatched():
    jobs = _load("ci.yml")["jobs"]
    for name, job in jobs.items():
        cond = str(job.get("if", ""))
        if "needs" in job:
            # Skipped with the job it needs; a skipped dependency skips it.
            needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
            for n in needs:
                assert "github.event.repository.private" in str(jobs[n].get("if", "")), (name, n)
            continue
        assert "!github.event.repository.private" in cond, name


def test_a_manual_dispatch_can_still_run_the_checks_on_a_private_repo():
    jobs = _load("ci.yml")["jobs"]
    for name in ("checks", "python-floor"):
        assert "workflow_dispatch" in str(jobs[name]["if"]), name


def test_every_job_in_every_workflow_has_a_timeout():
    for wf in WF.glob("*.yml"):
        for name, job in _load(wf.name)["jobs"].items():
            assert isinstance(job.get("timeout-minutes"), int), (wf.name, name)


def test_superseded_ci_runs_are_cancelled():
    conc = _load("ci.yml")["concurrency"]
    assert conc["cancel-in-progress"] is True


def test_ci_local_finds_the_floor_python_without_a_system_one():
    # The cloud containers stopped shipping the floor Python; uv installs one in
    # seconds, which is what lets ci_local.sh stand in for CI's floor leg. Both
    # legs run the floor tools/python_floor.py names, so the three never drift.
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import python_floor
    floor = "%d.%d" % python_floor.FLOOR
    text = (ROOT / "tools" / "ci_local.sh").read_text(encoding="utf-8")
    assert f"FLOOR_VERSION={floor}" in text
    assert "uv python find $FLOOR_VERSION" in text and "uv python install $FLOOR_VERSION" in text
    job = _load("ci.yml")["jobs"]["python-floor"]
    assert any(str((s.get("with") or {}).get("python-version")) == floor for s in job["steps"])
