"""Every function of the app's is used by the app itself, not kept alive by a list or a test.

Audits CS-3 and CS-4 (2026-11-10): ten functions were named only where they were defined (some
kept alive by the snapshot of public names a release wrote then), and four were called only by
tests, which therefore tested nothing the app runs. A name leaves the way MAINTAINING.md says:
out of the code, and into docs/removed_names.json with the CHANGELOG section whose entry
announces it, since a person's own tests may use it.

A top-level function in tools/ or templates/ counts as used when its name appears anywhere in
the app's own files (code, instructions, skills, workflows) besides its definition; a test's
use does not count.
"""
from __future__ import annotations

import ast
import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import repo_files  # noqa: E402

# In another area's files, each called only by a test today, and each that area's to settle
# (use it, or retire it the way MAINTAINING.md says). Nothing is added here.
LEFT_FOR_ITS_AREA = {
    "tools/network/reading.py:asked_to_sign_in",     # LinkedIn sign-in (the computer chat)
    "tools/network/reading.py:browser_gate",         # the reading gate (audit NW-33)
    "tools/followup_drafts.py:offer_words",          # referral offers in follow-ups
}
_TEXT = (".py", ".md", ".js", ".sh", ".json", ".yml", ".yaml", ".html", ".toml")
_NOT_A_USE = ("docs/removed_names.json", "CHANGELOG.md")


def _unused() -> list[str]:
    files = repo_files.tracked(root=ROOT, app_only=True)
    used: collections.Counter = collections.Counter()
    for rel in files:
        if not rel.endswith(_TEXT) or rel.startswith(("tests/", "profile.example/")) \
                or rel in _NOT_A_USE:
            continue
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                used.update(re.findall(r"\w+", fh.read()))
        except (OSError, UnicodeDecodeError):
            continue
    out = []
    for rel in files:
        if not rel.endswith(".py") or not rel.startswith(("tools/", "templates/")) \
                or rel.startswith("tools/openroles/"):
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and not node.name.startswith("__") and used[node.name] <= 1:
                out.append(f"{rel}:{node.name}")
    return out


def test_no_function_is_kept_only_by_a_list_or_a_test():
    unused = [n for n in _unused() if n not in LEFT_FOR_ITS_AREA]
    assert unused == [], ("used nowhere in the app but its own definition (a test's use does "
                          "not count): use it, or retire it as MAINTAINING.md says", unused)
