"""The two follow-up caps have names of their own, each bound once.

`followups.MAX_NUDGES` (2, an application's follow-ups) and `schema.MAX_NUDGES` (a contact's,
bound twice: 1, then from MAX_UNANSWERED) shared a name and meant different things (the audit of
2026-11-10, NW-29). Each now has its own name; the old ones stay for callers written before.
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import followups  # noqa: E402
import schema  # noqa: E402


def _bound(path, name):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    return sum(1 for n in tree.body if isinstance(n, ast.Assign)
               for t in n.targets if isinstance(t, ast.Name) and t.id == name)


def test_each_cap_is_bound_once_under_its_own_name():
    assert _bound("tools/network/schema.py", "MAX_NUDGES") == 1
    assert _bound("tools/network/schema.py", "CONTACT_NUDGES") == 1
    assert _bound("tools/followups.py", "APPLICATION_NUDGES") == 1
    assert schema.CONTACT_NUDGES == schema.MAX_NUDGES == schema.MAX_UNANSWERED - 1
    assert followups.APPLICATION_NUDGES == followups.MAX_NUDGES == 2
