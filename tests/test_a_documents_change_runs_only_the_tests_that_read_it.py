"""A pull request that changes only documents no tool reads runs only the tests that read them.

The release's CHANGELOG pull request (#206, 2026-11-11) ran 8,273 tests twice, the browser
and LaTeX for two changed documents. tools/ci_plan.py decides once, in ci.yml's plan job:
a change made only of files on its allowlist (CHANGELOG.md, docs/NEXT_BUILDER.md, the README
and its pictures, MAINTAINING.md and the like) skips the suite, the 3.9 leg and the page's
browser tests and runs the tests that read those files. Anything in doubt runs everything: a
file not on the list (a rename counts as both names), no usable base, a run by hand, and
every push to master. Fast checks passes a skipped job only where the plan says it was not
needed, and fails on any failure.
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

DOCS = ["CHANGELOG.md", "docs/NEXT_BUILDER.md"]


@pytest.mark.parametrize("files, docs", [
    (DOCS, True),
    (["README.md", "docs/images/page-brief-light-dark-0000.png"], True),
    (["MAINTAINING.md"], True),
    ([".github/PULL_REQUEST_TEMPLATE.md", "SECURITY.md", "CONTRIBUTING.md"], True),
    # #206, as it was: two workflows and a test besides the documents.
    ([".github/workflows/ci.yml", ".github/workflows/everywhere.yml", "CHANGELOG.md",
      "docs/NEXT_BUILDER.md", "tests/test_an_interview_has_a_live_prep.py",
      "tools/public_names.json"], False),
    (["CHANGELOG.md", "tools/release.py"], False),
    (["RUNBOOK.md"], False), (["CLAUDE.md"], False), (["SETUP.md"], False),
    ([".claude/skills/app/SKILL.md"], False), (["templates/app/app.js"], False),
    (["templates/README.md"], False), (["tests/CLAUDE.md"], False),
    (["profile.example/CLAUDE.md"], False), (["docs/rule_map.json"], False),
    (["docs/removed_names.json"], False), (["automation/README.md"], False),
    (["documents/README.md"], False), (["texmf/README.md"], False),
    (["docs/images"], False), (["docs/NEXT_BUILDER.md.bak"], False),
    ([], False),
])
def test_only_a_change_made_wholly_of_documents_is_documents_only(files, docs):
    assert ci_plan.docs_only(files) is docs


def test_nothing_a_chat_or_tool_reads_is_ever_on_the_list():
    for pattern, why in ci_plan.DOCS_ONLY.items():
        assert why.strip(), pattern
        assert not pattern.startswith(ci_plan.NEVER_DOCS) and pattern not in ci_plan.NEVER_DOCS
    for never in ci_plan.NEVER_DOCS:
        probe = never + "x.md" if never.endswith("/") else never
        assert not ci_plan.is_docs(probe), probe


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "app"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "ci@example.com")
    _git(r, "config", "user.name", "CI")
    (r / "tests").mkdir()
    (r / "tools").mkdir()
    (r / "docs").mkdir()
    (r / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (r / "docs" / "NEXT_BUILDER.md").write_text("notes\n", encoding="utf-8")
    (r / "tools" / "release.py").write_text("NOTES = 'CHANGELOG.md'\n", encoding="utf-8")
    (r / "tools" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (r / "tests" / "test_release.py").write_text("import release\n", encoding="utf-8")
    (r / "tests" / "test_handover.py").write_text("# reads docs/NEXT_BUILDER.md\n",
                                                  encoding="utf-8")
    (r / "tests" / "test_every_file.py").write_text("import os\nos.walk('.')\n",
                                                    encoding="utf-8")
    (r / "tests" / "test_unrelated.py").write_text("x = 2\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def test_a_documents_pull_request_runs_the_tests_that_read_them(repo):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n- A line\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "notes")
    got = ci_plan.lane("pull_request", base, str(repo))
    assert got["docs_only"] == "true"
    # One that reads code naming the file, one that lists files; never the unrelated one.
    assert got["tests"].split() == ["tests/test_every_file.py", "tests/test_release.py"]
    (repo / "docs" / "NEXT_BUILDER.md").write_text("more\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "handover")
    got = ci_plan.lane("pull_request", base, str(repo))
    assert "tests/test_handover.py" in got["tests"].split()


def test_masters_own_run_and_a_run_by_hand_are_always_the_whole_suite(repo):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n- A line\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "notes")
    assert ci_plan.lane("push", base, str(repo))["docs_only"] == "false"
    assert ci_plan.lane("workflow_dispatch", "", str(repo))["docs_only"] == "false"


@pytest.mark.parametrize("base", ["", "0" * 40, "f" * 40, "not-a-commit"])
def test_with_no_usable_base_everything_runs(repo, base):
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n- A line\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "notes")
    assert ci_plan.lane("pull_request", base, str(repo))["docs_only"] == "false"


def test_a_tool_moved_under_docs_is_still_a_tool_changed(repo):
    """git names a rename by its new name alone; a tool moved to docs/images/ would read as
    a picture added."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "images").mkdir()
    _git(repo, "mv", "tools/x.py", "docs/images/x.png")
    _git(repo, "commit", "-qm", "moved")
    assert ci_plan.changed(base, str(repo)) == ["docs/images/x.png", "tools/x.py"]
    assert ci_plan.lane("pull_request", base, str(repo))["docs_only"] == "false"


def test_a_name_with_an_accent_is_read_whole(repo):
    """git quotes such a name unless asked not to; quoted, a picture read as an unknown file
    and a tool's name came out wrong."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "images").mkdir()
    (repo / "docs" / "images" / "caf\u00e9.png").write_bytes(b"png")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "a picture")
    assert ci_plan.changed(base, str(repo)) == ["docs/images/caf\u00e9.png"]
    assert ci_plan.docs_only(ci_plan.changed(base, str(repo)))


def test_a_pull_requests_merge_is_also_measured_against_the_base_as_it_is_now(repo):
    """GitHub tests a pull request's merge with the base as it is when the merge is made,
    and the base the event names can be older: there a change that puts a tool back as it
    was at the older base reads as no change. Both differences count."""
    old = _git(repo, "rev-parse", "HEAD")
    (repo / "tools" / "x.py").write_text("x = 3\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "master moved")
    _git(repo, "checkout", "-qb", "work")
    (repo / "tools" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n- A line\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "notes, and x as it was")
    _git(repo, "checkout", "-q", "master")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "work")
    assert ci_plan.changed(old, str(repo)) == ["CHANGELOG.md"]
    assert ci_plan.changed(old, str(repo), merge=True) == ["CHANGELOG.md", "tools/x.py"]
    assert ci_plan.lane("pull_request", old, str(repo))["docs_only"] == "false"


def test_the_real_documents_reach_the_tests_that_read_them():
    tracked = repo_files.tracked(root=ROOT)
    picked = set(ci_plan.tests_for(DOCS, ROOT, tracked))
    # Named outright, and through code that names the file (build_versions names every doc).
    assert {"tests/test_release.py", "tests/test_build_versions.py"} <= picked
    # Through data: docs/rule_map.json names MAINTAINING.md.
    assert "tests/test_core_rules_have_a_home.py" in ci_plan.tests_for(["MAINTAINING.md"],
                                                                         ROOT, tracked)
    # Through code: claude_surfaces.py keeps blocks in README.md; its test never names it.
    assert "tests/test_claude_surfaces.py" in ci_plan.tests_for(["README.md"], ROOT, tracked)
    # Every test that lists the tree, and the scans of every file.
    for t in ("tests/test_every_file_keeps_plain_line_endings.py",
              "tests/test_the_leak_scan_catches_a_person.py"):
        assert t in picked, t
    every = [f for f in tracked if f.startswith("tests/test_") and f.count("/") == 1]
    assert len(picked) < len(every) / 2, "the lane is not the whole suite again"


# ------------------------------------------------------------------ the workflow

def _needs_ok(docs: str, tex: str = "false", fails=(), private=False, event=None):
    gh = event or W.pull_request(private=private)
    out = {"plan": {"docs_only": docs, "tests": "tests/test_release.py"},
           "checks": {"latex": tex}}
    results = W.run("ci.yml", gh, outputs=out, fails=fails)
    if results["fast"] == "skipped":
        return results, None
    ok, _ = ci_plan.verdict(W.needs_json("ci.yml", "fast", results, out))
    return results, ok


def test_a_documents_change_skips_the_suite_and_runs_its_tests_and_fast_checks_passes():
    results, ok = _needs_ok("true")
    assert results["docs"] == "success" and results["checks"] == "success"
    assert {results[j] for j in ("suite", "python-floor", "page", "latex-smoke")} == {"skipped"}
    assert ok is True


def test_any_other_change_runs_everything_and_not_the_documents_job():
    results, ok = _needs_ok("false")
    assert {results[j] for j in ("plan", "checks", "suite", "python-floor", "page")} == {"success"}
    assert results["docs"] == "skipped" and ok is True
    results, ok = _needs_ok("false", tex="true")
    assert results["latex-smoke"] == "success" and ok is True


@pytest.mark.parametrize("docs, failing", [
    ("true", "docs"), ("true", "checks"), ("false", "suite"), ("false", "python-floor"),
    ("false", "page"), ("false", "checks"), ("true", "plan"), ("false", "plan"),
])
def test_any_failure_fails_fast_checks(docs, failing):
    _, ok = _needs_ok(docs, fails={failing})
    assert ok is False


def test_a_job_skipped_that_the_change_needed_fails_fast_checks():
    needs = {j: {"result": "success", "outputs": {}} for j in ci_plan.FAST_NEEDS}
    needs["plan"]["outputs"] = {"docs_only": "false"}
    needs["checks"]["outputs"] = {"latex": "true"}
    for job in ("suite", "python-floor", "page", "latex-smoke"):
        broken = {k: dict(v) for k, v in needs.items()}
        broken[job] = {"result": "skipped", "outputs": {}}
        assert ci_plan.verdict(broken)[0] is False, job
    needs["plan"]["outputs"] = {}                   # a plan with no answer
    assert ci_plan.verdict(needs)[0] is False
    needs["plan"]["outputs"] = {"docs_only": "true"}
    needs["docs"] = {"result": "skipped", "outputs": {}}
    assert ci_plan.verdict(needs)[0] is False


def test_a_private_copy_pays_nothing_and_a_run_by_hand_runs_everything():
    results, ok = _needs_ok("false", private=True)
    assert set(results.values()) == {"skipped"} and ok is None
    by_hand = W.event("workflow_dispatch", private=True)
    results, ok = _needs_ok("false", event=by_hand)
    assert results["suite"] == "success" and ok is True


def test_fast_checks_waits_for_every_job_the_verdict_reads():
    jobs = W.load("ci.yml")["jobs"]
    assert tuple(jobs["fast"]["needs"]) == ci_plan.FAST_NEEDS
    steps = "\n".join(str(s.get("run", "")) for s in jobs["fast"]["steps"])
    assert "tools/ci_plan.py verdict" in steps
    assert any((s.get("env") or {}).get("NEEDS") == "${{ toJSON(needs) }}"
               for s in jobs["fast"]["steps"])


def test_the_plan_compares_with_the_base_and_hands_its_answer_on():
    plan = W.load("ci.yml")["jobs"]["plan"]
    step = next(s for s in plan["steps"] if s.get("id") == "plan")
    assert step["env"]["BASE"] == "${{ github.event.pull_request.base.sha || github.event.before }}"
    assert 'tools/ci_plan.py lane --out "$GITHUB_OUTPUT"' in step["run"]
    assert plan["steps"][0]["with"]["fetch-depth"] == 0
    for key in ("docs_only", "tests"):
        assert plan["outputs"][key] == "${{ steps.plan.outputs.%s }}" % key
