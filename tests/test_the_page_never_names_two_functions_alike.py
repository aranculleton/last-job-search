"""The page's code is one script whose functions share one scope, where a second function of
the same name silently replaces the first wherever either is called. It happened twice: a
second clock() turned the Brief's time into "498109000H 0M", and a second weekStart() made
every bar of the Brief's chart say "Week of : 2 applications" (2026-10-31)."""
from __future__ import annotations

import collections
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "templates", "app", "app.js")


def test_no_two_functions_in_the_pages_own_scope_share_a_name():
    with open(APP_JS, encoding="utf-8") as fh:
        text = fh.read()
    # The script is one function body indented two spaces: its own functions start there.
    names = re.findall(r"^  (?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", text, re.M)
    assert len(names) > 100, "the page's functions were not found: the pattern needs updating"
    twice = sorted(n for n, k in collections.Counter(names).items() if k > 1)
    assert twice == [], "two functions share a name, and the later one replaces the earlier: " + ", ".join(twice)
