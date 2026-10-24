"""The person's own files are staged by tools/save_state.py, in any shell.

CLAUDE.md's persistence rule was a shell loop, and under zsh, the Mac's own shell, a
pattern that matched nothing (`cv/*_CV_*.tex` in a repo with only resumes) stopped it
with "no matches found" before anything was staged (2026-10-24). The tool expands every
pattern itself, keeps profile/ out of a forced add, and never stages build noise.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import save_state  # noqa: E402


def _repo(tmp_path):
    r = str(tmp_path)
    subprocess.run(["git", "init", "-q", r], check=True)
    with open(os.path.join(ROOT, ".gitignore")) as src, open(tmp_path / ".gitignore", "w") as dst:
        dst.write(src.read())
    files = {
        "profile/person.json": "{}", "profile/tests/__pycache__/x.pyc": "x",
        "job_search_tracker.csv": "company\n", "network_threads.csv": "contact_id\n",
        "documents/applications/quayside/draft.json": "{}",
        "documents/applications/quayside/resume.aux": "noise",
        "cv/Morgan_Ellis_Resume_QF.tex": "x", "cv/Morgan_Ellis_Resume_QF.pdf": "x",
        "cv/Morgan_Ellis_Resume_QF.log": "noise", "cv/Morgan_Ellis_Resume_QF.txt": "noise",
        "company_research/quayside.json": "{}", "salary_data.json": "{}",
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return r


def _staged(r):
    return set(subprocess.run(["git", "-C", r, "diff", "--cached", "--name-only"],
                              capture_output=True, text=True).stdout.split())


def test_what_exists_is_staged_and_nothing_else(tmp_path, capsys):
    r = _repo(tmp_path)
    assert save_state.main([], root=r) == 0
    staged = _staged(r)
    assert {"profile/person.json", "job_search_tracker.csv", "network_threads.csv",
            "documents/applications/quayside/draft.json", "cv/Morgan_Ellis_Resume_QF.tex",
            "cv/Morgan_Ellis_Resume_QF.pdf", "company_research/quayside.json"} <= staged
    for noise in ("documents/applications/quayside/resume.aux", "cv/Morgan_Ellis_Resume_QF.log",
                  "cv/Morgan_Ellis_Resume_QF.txt", "salary_data.json",
                  "profile/tests/__pycache__/x.pyc"):
        assert noise not in staged, noise


def test_list_stages_nothing(tmp_path, capsys):
    r = _repo(tmp_path)
    assert save_state.main(["--list"], root=r) == 0
    assert _staged(r) == set()
    out = capsys.readouterr().out
    assert "add -f  cv/Morgan_Ellis_Resume_QF.tex" in out and "nothing staged" in out


def test_it_runs_the_same_from_zsh_where_the_loop_stopped(tmp_path):
    import shutil
    import pytest
    if not shutil.which("zsh"):
        pytest.skip("no zsh here to run the old loop under")
    r = _repo(tmp_path)
    loop = ('for p in cv/*_CV_*.tex job_search_tracker.csv; do [ -e "$p" ] && '
            'git add -f -- "$p"; done')
    old = subprocess.run(["zsh", "-c", loop], cwd=r, capture_output=True, text=True)
    assert "no matches found" in old.stderr and _staged(r) == set()
    run = (f"{sys.executable} -c \"import sys; sys.path.insert(0, '{ROOT}/tools'); "
           f"import save_state; sys.exit(save_state.main([], root='{r}'))\"")
    new = subprocess.run(["zsh", "-c", run], cwd=r, capture_output=True, text=True)
    assert new.returncode == 0, new.stdout + new.stderr
    assert {"job_search_tracker.csv", "profile/person.json"} <= _staged(r)


def test_a_file_taken_away_is_staged_as_removed(tmp_path):
    # A sent draft is deleted (documents/network/<id>/draft.md); the loop's
    # `git add -f -- documents/network` staged that, and walking only what exists did not.
    r = _repo(tmp_path)
    draft = tmp_path / "documents/network/ana_rook/draft.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("Hi Ana")
    assert save_state.main([], root=r) == 0
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    subprocess.run(["git", "-C", r, "commit", "-qm", "saved"], check=True, env=env)
    draft.unlink()
    (tmp_path / "cv/Morgan_Ellis_Resume_QF.pdf").unlink()
    assert save_state.main([], root=r) == 0
    gone = subprocess.run(["git", "-C", r, "diff", "--cached", "--name-only",
                           "--diff-filter=D"], capture_output=True, text=True).stdout.split()
    assert set(gone) == {"documents/network/ana_rook/draft.md", "cv/Morgan_Ellis_Resume_QF.pdf"}
