"""The example documents compile only when a change touches what they compile with, and
the compile starts as soon as the plan says so, never after the suite.

The rule matched all of templates/, which is mostly the page's own code, and the compile
waited for the Checks job: two minutes of work that started nine minutes in (2026-11-11).
ci.yml's plan job decides it now (tools/ci_plan.py LATEX): the example documents, their
classes and fonts, the three modules that write a real resume and letter, the tools that fit
and check a PDF, and ci.yml itself. It fails open: no usable base compiles.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import ci_plan  # noqa: E402

import workflow_runs as W  # noqa: E402


@pytest.mark.parametrize("path, compiles", [
    ("cv/main_example.tex", True), ("cover_letters/cover.cls", True),
    ("cover_letters/OpenFonts/x.otf", True), ("texmf/tex/latex/x.sty", True),
    ("templates/doc_design.py", True), ("templates/doc_style.py", True),
    ("templates/resume_gen.py", True), ("tools/fit_to_page.py", True),
    ("tools/render_application.py", True), ("tools/verify_pdf.py", True),
    (".github/workflows/ci.yml", True),
    ("templates/app/app.js", False), ("templates/app/DESIGN.md", False),
    ("templates/README.md", False), ("templates/doc_design.pyc", False),
    (".github/workflows/platforms.yml", False), ("tools/app.py", False),
    ("CHANGELOG.md", False),
])
def test_only_what_the_compile_uses_compiles(path, compiles):
    assert bool(ci_plan.LATEX.match(path)) is compiles


def test_no_documents_only_change_ever_needs_latex():
    for pattern in ci_plan.DOCS_ONLY:
        probe = pattern.replace("**", "x.png").replace("*", "x")
        assert ci_plan.is_docs(probe) and not ci_plan.LATEX.match(probe), probe


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


@pytest.mark.parametrize("path, tex", [("templates/doc_style.py", "true"),
                                       ("templates/app/app.js", "false")])
def test_the_plan_says_whether_this_change_compiles(tmp_path, path, tex):
    r = tmp_path / "app"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    _git(r, "config", "user.email", "ci@example.com")
    _git(r, "config", "user.name", "CI")
    (r / "README.md").write_text("app\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD")
    f = r / path
    f.parent.mkdir(parents=True)
    f.write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "change")
    for event in ("pull_request", "push"):
        assert ci_plan.lane(event, base, root=str(r))["latex"] == tex
    assert ci_plan.lane("pull_request", "0" * 40, root=str(r))["latex"] == "true"


def test_a_run_by_hand_compiles_when_its_box_is_ticked():
    assert ci_plan.lane("workflow_dispatch", "", "true")["latex"] == "true"
    assert ci_plan.lane("workflow_dispatch", "", "false")["latex"] == "false"
    assert ci_plan.lane("workflow_dispatch", "", "")["latex"] == "false"


def test_the_compile_waits_for_the_plan_alone():
    jobs = W.load("ci.yml")["jobs"]
    assert jobs["latex-smoke"]["needs"] == "plan"
    assert "needs.plan.outputs.latex == 'true'" in jobs["latex-smoke"]["if"]
    assert "latex" not in (jobs["checks"].get("outputs") or {})
    out = {"plan": {"docs_only": "false", "latex": "true"}}
    got = W.run("ci.yml", W.pull_request(), outputs=out, fails={"checks", "suite"})
    assert got["latex-smoke"] == "success"
    step = next(s for s in jobs["plan"]["steps"] if s.get("id") == "plan")
    assert step["env"]["LATEX"] == "${{ inputs.latex }}"


def test_a_compile_the_plan_asked_for_that_did_not_run_fails_fast_checks():
    needs = {j: {"result": "success", "outputs": {}} for j in ci_plan.FAST_NEEDS}
    needs["plan"]["outputs"] = {"docs_only": "false", "latex": "true"}
    needs["docs"]["result"] = "skipped"
    assert ci_plan.verdict(needs)[0] is True
    needs["latex-smoke"]["result"] = "skipped"
    assert ci_plan.verdict(needs)[0] is False
    needs["plan"]["outputs"]["latex"] = "false"
    assert ci_plan.verdict(needs)[0] is True
