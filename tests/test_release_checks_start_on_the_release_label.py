"""The Everywhere workflow and the Windows jobs of Platforms start on the `release` label and by
hand, never on a pull request's title; Platforms also weekly, Everywhere never on a schedule.

A "Release " title started them on every push: the release's CHANGELOG pull request ran
Everywhere four times for one documents change (#206, 2026-11-11), and retitling a pull
request started nothing at all. Now the label going on starts them, and each push while it
is on starts them again; another label going on starts nothing and cancels nothing. Each
job stays gated on the repo being public or the run being by hand, so a private copy pays
nothing. Everywhere's suite runs its seven variants side by side, one a job: one after
another they took 53 to 58 minutes and one run stopped at its 60-minute limit.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import workflow_runs as W  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import ci_plan  # noqa: E402

TITLE = "Release 4.15.1: a release"
EVERYWHERE = ("page", "suite")
WINDOWS = ("windows-shell", "windows-chat")


def _plan(github: dict) -> dict:
    """Platforms' plan job's answer for this event; with no base to compare, as here, a pull
    request counts as touching what a person's set-up runs."""
    ev = github.get("event") or {}
    labels = [lb["name"] for lb in (ev.get("pull_request") or {}).get("labels", [])]
    got = ci_plan.platforms(github["event_name"], ev.get("action", ""),
                            (ev.get("label") or {}).get("name", ""), labels, "")
    return {"plan": got}


def _starts(workflow: str, github: dict) -> bool:
    """Whether GitHub starts the workflow for this event at all: a pull request's action has
    to be one of its `types`."""
    if github["event_name"] != "pull_request":
        return True
    return github["event"]["action"] in W.load(workflow)["on"]["pull_request"]["types"]


def _ran(workflow: str, github: dict, inputs=None) -> set:
    out = _plan(github) if workflow == "platforms.yml" else {}
    results = W.run(workflow, github, inputs=inputs, outputs=out)
    return {j for j, r in results.items() if r == "success"}


@pytest.mark.parametrize("github, runs", [
    (W.pull_request("labeled", labels=["release"], label="release"), True),
    (W.pull_request("synchronize", labels=["release", "bug"]), True),
    # Opened or reopened with the label on (the process review, 2026-11-11: reopened, it ran
    # Windows in Platforms and nothing in Everywhere until its next push).
    (W.pull_request("opened", labels=["release"]), True),
    (W.pull_request("reopened", labels=["bug", "release"]), True),
    (W.pull_request("opened", labels=["bug"], title=TITLE), False),
    (W.pull_request("reopened", labels=[]), False),
    (W.pull_request("reopened", labels=["release"], private=True), False),
    (W.pull_request("labeled", labels=["release", "bug"], label="bug"), False),
    (W.pull_request("synchronize", title=TITLE), False),
    (W.pull_request("labeled", labels=["documentation"], label="documentation", title=TITLE), False),
    (W.pull_request("labeled", labels=["release"], label="release", private=True), False),
    (W.pull_request("synchronize", labels=["release"], private=True), False),
    (W.event("workflow_dispatch"), True),
    (W.event("workflow_dispatch", private=True), True),
])
def test_everywhere_and_windows_run_on_the_label_and_never_the_title(github, runs):
    inputs = {"suite": True, "variants": "", "tests": ""}
    assert _starts("everywhere.yml", github) or not runs
    assert (_ran("everywhere.yml", github, inputs) == set(EVERYWHERE)) is runs
    assert not runs or _ran("everywhere.yml", github, inputs) == set(EVERYWHERE)
    platforms = _ran("platforms.yml", github)
    assert all((j in platforms) is runs for j in WINDOWS), platforms


ACTIONS = ("opened", "reopened", "synchronize", "labeled", "unlabeled", "edited", "closed",
           "ready_for_review", "converted_to_draft")


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("labels, label", [(["release"], "release"), (["release", "bug"], "bug"),
                                           (["bug"], "bug"), ([], "")])
def test_everywhere_and_platforms_agree_on_every_pull_request_event(action, labels, label):
    """Whatever happens to a pull request, Everywhere checks it exactly when Platforms runs
    Windows on it: both when tools/ci_plan.py release_run says it is a release run, and the
    event is one each workflow starts on."""
    label = label if action in ("labeled", "unlabeled") else ""
    github = W.pull_request(action, labels=labels, label=label)
    want = ci_plan.release_run("pull_request", action, label, labels)
    inputs = {"suite": True, "variants": "", "tests": ""}
    everywhere = _starts("everywhere.yml", github) and \
        _ran("everywhere.yml", github, inputs) == set(EVERYWHERE)
    windows = _starts("platforms.yml", github) and set(WINDOWS) <= _ran("platforms.yml", github)
    assert everywhere is want and windows is want, (everywhere, windows, want)


def test_only_platforms_runs_weekly():
    """Platforms' weekly run catches what changes outside the app (TinyTeX, Bun, GitHub's
    runners) before a new person's set-up meets it. Everywhere's engines are pinned, so a
    weekly run only checked a master nothing had changed (the maintainer, 2026-11-11: "cheap
    and efficient"): every release runs it on the label."""
    import yaml
    def on(name):
        with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        return doc.get("on", doc.get(True))
    assert "schedule" not in on("everywhere.yml")
    assert "schedule" in on("platforms.yml")
    inputs = {"suite": True, "variants": "", "tests": ""}
    assert _ran("everywhere.yml", W.event("schedule"), inputs) == set()
    assert set(WINDOWS) <= _ran("platforms.yml", W.event("schedule"))
    assert not set(WINDOWS) & _ran("platforms.yml", W.event("schedule", private=True))


def test_a_run_by_hand_can_leave_the_suite_out():
    got = _ran("everywhere.yml", W.event("workflow_dispatch"), {"suite": False})
    assert got == {"page"}


def test_the_label_or_the_title_decides_nothing_else_in_either_file():
    for name in ("everywhere.yml", "platforms.yml"):
        text = (W.WORKFLOWS / name).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        assert "pull_request.title" not in code, name
    on = W.load("everywhere.yml")["on"]
    assert on["pull_request"]["types"] == ["opened", "reopened", "labeled", "synchronize"]
    assert "labeled" in W.load("platforms.yml")["on"]["pull_request"]["types"]


def _group(name: str, github: dict) -> str:
    raw = W.load(name)["concurrency"]["group"]
    return re.sub(r"\$\{\{(.*?)\}\}", lambda m: W._str(W.evaluate(m.group(1), {"github": github})),
                  raw)


def test_another_label_never_cancels_the_run_checking_the_release():
    for name in ("everywhere.yml", "platforms.yml"):
        release = _group(name, dict(W.pull_request("labeled", ["release"], "release"),
                                    ref="refs/pull/7/merge"))
        push = _group(name, dict(W.pull_request("synchronize", ["release"]),
                                 ref="refs/pull/7/merge"))
        other = _group(name, dict(W.pull_request("labeled", ["release", "bug"], "bug"),
                                  ref="refs/pull/7/merge"))
        # Opened or reopened with the label, GitHub sends that and `labeled` together: one
        # group, so the second cancels the first and one run checks the release.
        opened = [_group(name, dict(W.pull_request(action, ["release"]), ref="refs/pull/7/merge"))
                  for action in ("opened", "reopened")]
        assert release == push == opened[0] == opened[1] != other, (name, release, other)
        assert W.load(name)["concurrency"]["cancel-in-progress"] is True


def test_the_suite_runs_every_variant_side_by_side_one_a_job():
    with open(os.path.join(ROOT, "tools", "everywhere.sh"), encoding="utf-8") as fh:
        variants = re.search(r'^SUITE_VARIANTS="([^"]+)"', fh.read(), re.M).group(1).split()
    job = W.load("everywhere.yml")["jobs"]["suite"]
    assert job["strategy"]["matrix"]["variant"] == variants
    assert job["strategy"]["fail-fast"] is False
    step = next(s for s in job["steps"] if "tools/everywhere.sh" in str(s.get("run", "")))
    assert step["run"].strip() == 'tools/everywhere.sh suite "$VARIANT"'
    assert step["env"]["VARIANT"] == "${{ matrix.variant }}"
    assert step["env"]["EVERYWHERE_STRICT"] == "1"
    assert job["timeout-minutes"] <= 30


def test_a_release_takes_windows_in_three_parts_and_an_ordinary_change_linux_and_the_mac():
    expr = W.load("platforms.yml")["jobs"]["person"]["strategy"]["matrix"]["target"]

    def systems(github):
        plan = {"result": "success", "outputs": _plan(github)["plan"]}
        return W.evaluate(expr, {"github": github, "needs": {"plan": plan}})

    release = systems(W.pull_request("labeled", ["release"], "release"))
    plain = systems(W.pull_request("synchronize", title=TITLE))
    assert [t["os"] for t in release].count("windows-latest") == 3
    assert [t["os"] for t in plain] == ["ubuntu-24.04", "macos-latest"]


def _expressions(node, key=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _expressions(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _expressions(v, key)
    elif isinstance(node, str):
        found = re.findall(r"\$\{\{(.*?)\}\}", node, re.S)
        if key == "if" and not found:
            found = [node]
        yield from found


def test_every_expression_in_every_workflow_reads():
    """A bracket too many in an `if:` still parses as YAML, and GitHub refuses the whole file
    only once it is pushed (this file's own first draft had one)."""
    for wf in sorted(W.WORKFLOWS.glob("*.yml")):
        for expr in _expressions(W.load(wf.name)):
            W.evaluate(expr, {})          # raises on anything it cannot read
