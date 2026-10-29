"""A speed limit is measured alone, never beside the suite's other workers.

With the suite in parallel workers, a build that takes 1.5s alone read 2.6s on Python 3.9
and 3.3s on Windows (2026-10-29): the workers share the runner's cores. tests/conftest.py
holds every test marked `timing` back from the workers and runs them alone at the end. A
new speed limit without the mark would flake the same way, so every one carries it.
"""
from __future__ import annotations

import ast
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOUND = re.compile(r"assert .*(took|began|elapsed|time\.(monotonic|perf_counter|process_time)\(\)).* < [0-9.]+")


def test_every_speed_limit_is_marked_timing():
    unmarked = []
    for path in glob.glob(os.path.join(ROOT, "tests", "test_*.py")):
        src = open(path, encoding="utf-8").read()
        if not BOUND.search(src):
            continue
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
                continue
            body = ast.get_source_segment(src, node) or ""
            marks = [ast.unparse(d) for d in node.decorator_list]
            if BOUND.search(body) and "pytest.mark.timing" not in marks:
                unmarked.append(f"{os.path.basename(path)}::{node.name}")
    assert not unmarked, unmarked


def test_the_suite_times_them_alone_after_a_parallel_run():
    src = open(os.path.join(ROOT, "tests", "conftest.py"), encoding="utf-8").read()
    assert "PYTEST_XDIST_WORKER" in src and '"-m", "timing"' in src and '"no:xdist"' in src
    assert "session.exitstatus = 1" in src
