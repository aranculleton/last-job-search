"""Platforms runs on a pull request only when it touches what a person's set-up runs on Linux
or a Mac, and there without the suite on Linux, which Checks runs already.

The paths were far wider (the page's own code, tools/app.py, tools/sync_app.py and more):
Platforms had run 124 times on pull requests, 80 of the runs cancelled, and the Linux job spent
19 of its 21 minutes on the suite Checks had just run (audit, 2026-11-11). The list now lives
in tools/ci_plan.py PLATFORM_PATHS, each path with what of the set-up it is, and the plan job
reads it, because a `paths:` filter applies to every event and would stop a release labelled
`release` that touched none of them.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import ci_plan  # noqa: E402
import repo_files  # noqa: E402

yaml = pytest.importorskip("yaml")              # the 3.9 leg installs pytest and no more
import workflow_runs as W  # noqa: E402


def test_every_path_says_why_and_names_a_file_that_is_there():
    tracked = repo_files.tracked(root=ROOT)
    for pattern, why in ci_plan.PLATFORM_PATHS.items():
        assert why.strip(), pattern
        assert any(ci_plan._glob(pattern).match(f) for f in tracked), f"{pattern} names no file"


@pytest.mark.parametrize("path, runs", [
    ("tools/installs.py", True), ("tools/env_check.py", True), ("tools/local_path.py", True),
    ("tools/python_floor.py", True), ("requirements.txt", True), ("tools/pdftext.py", True),
    ("tools/verify_batch.sh", True), ("tools/fit_to_page.py", True),
    ("templates/doc_design.py", True), ("templates/doc_style.py", True),
    ("templates/resume_gen.py", True), ("cv/main_example.tex", False),
    ("cover_letters/cover.cls", True), ("texmf/tex/latex/x.sty", True),
    ("tools/network/export.py", True), ("tools/stage_picks.py", True),
    ("tools/platform_check.py", True), (".github/workflows/platforms.yml", True),
    # The page's own code, and what only a computer chat or Windows runs.
    ("templates/app/app.js", False), ("templates/app/DESIGN.md", False),
    ("tools/app.py", False), ("tools/sync_app.py", False), ("tools/app_listen.py", False),
    ("tools/merge_state.py", False), ("tools/computer_setup.ps1", False),
    (".claude/settings.json", False), ("COMPUTER.md", False), (".gitattributes", False),
    ("tools/setup_env.sh", False), ("tools/network/state.py", False), ("CHANGELOG.md", False),
])
def test_only_what_a_persons_set_up_runs_starts_it(path, runs):
    assert ci_plan.touches_platforms([path]) is runs


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def _change(tmp_path, path):
    r = tmp_path / "app"
    (r / "tools").mkdir(parents=True)
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "ci@example.com")
    _git(r, "config", "user.name", "CI")
    (r / "README.md").write_text("app\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD")
    f = r / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "change")
    return str(r), base


@pytest.mark.parametrize("path, person", [("tools/installs.py", "true"),
                                          ("templates/app/app.js", "false")])
def test_an_ordinary_pull_request_runs_linux_and_the_mac_only_for_the_set_up(tmp_path, path,
                                                                            person):
    root, base = _change(tmp_path, path)
    got = ci_plan.platforms("pull_request", "synchronize", "", [], base, root)
    assert (got["person"], got["windows"]) == (person, "false")


@pytest.mark.parametrize("event, action, label, labels, person, windows", [
    ("schedule", "", "", [], "true", "true"),
    ("workflow_dispatch", "", "", [], "true", "true"),
    ("pull_request", "labeled", "release", ["release"], "true", "true"),
    ("pull_request", "synchronize", "", ["release"], "true", "true"),
    ("pull_request", "reopened", "", ["bug", "release"], "true", "true"),
    ("pull_request", "labeled", "bug", ["release", "bug"], "false", "false"),
    ("pull_request", "labeled", "bug", ["bug"], "false", "false"),
    ("push", "", "", [], "false", "false"),
])
def test_a_release_runs_every_system_whatever_it_touches(event, action, label, labels, person,
                                                         windows):
    got = ci_plan.platforms(event, action, label, labels, "")
    assert (got["person"], got["windows"]) == (person, windows)


def test_with_no_base_to_compare_linux_and_the_mac_run():
    got = ci_plan.platforms("pull_request", "opened", "", [], "")
    assert (got["person"], got["windows"]) == ("true", "false")


def test_the_workflow_reads_the_plan_and_has_no_paths_filter():
    wf = W.load("platforms.yml")
    assert "paths" not in wf["on"]["pull_request"]
    assert "labeled" in wf["on"]["pull_request"]["types"]
    jobs = wf["jobs"]
    assert jobs["person"]["needs"] == "plan"
    for name in ("windows-shell", "windows-chat"):
        assert jobs[name]["needs"] == "plan"
    step = next(s for s in jobs["plan"]["steps"] if s.get("id") == "plan")
    assert 'tools/ci_plan.py platforms --out "$GITHUB_OUTPUT"' in step["run"]
    assert set(step["env"]) == {"EVENT", "ACTION", "LABEL", "LABELS", "BASE"}
    assert jobs["plan"]["steps"][0]["with"]["fetch-depth"] == 0


@pytest.mark.parametrize("person, windows, private, runs", [
    ("true", "false", False, {"plan", "person"}),
    ("false", "false", False, {"plan"}),
    ("true", "true", False, {"plan", "person", "windows-shell", "windows-chat"}),
    ("true", "true", True, set()),
])
def test_each_job_runs_as_the_plan_says_and_a_private_copy_pays_nothing(person, windows,
                                                                        private, runs):
    out = {"plan": {"person": person, "windows": windows}}
    got = W.run("platforms.yml", W.pull_request(private=private), outputs=out)
    assert {j for j, r in got.items() if r == "success"} == runs


@pytest.mark.parametrize("event, os_name, runs", [
    ("pull_request", "Linux", False), ("pull_request", "macOS", True),
    ("pull_request", "Windows", True), ("schedule", "Linux", True),
    ("workflow_dispatch", "Linux", True),
])
def test_the_suite_is_left_out_on_linux_for_a_pull_request_only(event, os_name, runs):
    step = next(s for s in W.load("platforms.yml")["jobs"]["person"]["steps"]
                if s.get("name") == "The test suite")
    ctx = {"github": {"event_name": event}, "runner": {"os": os_name}}
    assert W.truthy(W.evaluate(step["if"], ctx)) is runs


def test_platforms_and_everywhere_agree_on_what_a_release_run_is():
    expr = W.load("everywhere.yml")["jobs"]["page"]["if"]
    cases = [("labeled", "release", ["release"]), ("labeled", "bug", ["release", "bug"]),
             ("synchronize", "", ["release"]), ("synchronize", "", []),
             ("labeled", "release", ["release", "bug"])]
    for action, label, labels in cases:
        gh = W.pull_request(action, labels=labels, label=label)
        assert W.truthy(W.evaluate(expr, {"github": gh})) is ci_plan.release_run(
            "pull_request", action, label, labels), (action, label, labels)
