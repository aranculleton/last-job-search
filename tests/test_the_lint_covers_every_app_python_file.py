"""The lint covers every Python file of the app's, in CI and in the local check alike.

Audit SV-10 (2026-11-10): `ruff check salary_lookup.py` found two errors the lint never saw,
because CI and tools/ci_local.sh named tools/, templates/ and tests/ only. A file of the app's
outside them is linted too, and the two commands name the same files. A person's own files
(profile/, the example person) are theirs and are not the app's lint.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import repo_files  # noqa: E402


def _targets(path: str) -> list[str]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"-m ruff check --no-cache ([^\n]+)", text)
    assert m, path
    return m.group(1).split()


def test_ci_and_the_local_check_lint_the_same_files_and_miss_none():
    ci = _targets(".github/workflows/ci.yml")
    local = _targets("tools/ci_local.sh")
    gate = _targets("tools/push_gate.sh")           # the maintainer's gate before a push
    assert ci == local == gate, (ci, local, gate)
    missed = [p for p in repo_files.tracked(root=ROOT, app_only=True)
              if p.endswith(".py") and not p.startswith(("profile.example/", "profile/"))
              and not any(p == t or p.startswith(t.rstrip("/") + "/") for t in ci)]
    assert missed == [], missed
