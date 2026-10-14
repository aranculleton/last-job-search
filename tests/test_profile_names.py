"""tools/profile_names.py lists every profile name the tools read, and the
example person sets every one a tool cannot do without.

/setup copies the example's shape. A name a tool reads with no default that the
example leaves out is a crash waiting in every new person's profile.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import profile_names  # noqa: E402


def test_it_finds_the_names_the_tools_read():
    names = profile_names.collect()
    assert "SALARY_FLOOR" in names["search"]
    assert "FIT_MISSING" in names["search"]
    assert "LIB" in names["bullets"]
    assert sum(len(v) for v in names.values()) > 80


def test_the_example_sets_every_name_a_tool_needs():
    names = profile_names.collect()
    unset = sorted(f"{mod}.{name}" for mod, entries in names.items()
                   for name, e in entries.items()
                   if e["required"] and name not in profile_names.example_sets(mod))
    assert unset == [], f"read with no default but missing from profile.example/: {unset}"
