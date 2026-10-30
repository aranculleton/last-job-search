"""Windows runs the suite on three runners side by side, each taking its own part (the
previous builder's first open item, 2026-10-30): the parts never overlap, together they are
the whole suite, every runner splits it the same way, and an empty or malformed part is the
whole suite, as on Linux and the Mac."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import platform_check  # noqa: E402


def test_three_parts_are_the_whole_suite_once():
    tests = os.path.join(ROOT, "tests")
    every = sorted(os.path.join("tests", f) for f in os.listdir(tests) if f.startswith("test_") and f.endswith(".py"))
    parts = [platform_check.suite_part(f"{k}/3") for k in (1, 2, 3)]
    assert [p[0] for p in parts] == [" (part 1 of 3)", " (part 2 of 3)", " (part 3 of 3)"]
    files = [f for _, fs in parts for f in fs]
    assert sorted(files) == every and len(set(files)) == len(files)
    sizes = [sum(os.path.getsize(os.path.join(ROOT, f)) for f in fs) for _, fs in parts]
    assert max(sizes) < 1.2 * min(sizes), sizes
    assert parts == [platform_check.suite_part(f" {k} / 3 ") for k in (1, 2, 3)], "the same split every time"


def test_no_part_is_the_whole_suite():
    for shard in ("", "0/3", "4/3", "two of three", None):
        assert platform_check.suite_part(shard) == ("", ["tests"])


def test_the_workflow_gives_each_windows_runner_its_part():
    with open(os.path.join(ROOT, ".github", "workflows", "platforms.yml"), encoding="utf-8") as fh:
        flow = fh.read()
    for k in (1, 2, 3):
        assert '{"os":"windows-latest", "shard":"%d/3"}' % k in flow
    assert "LJS_SUITE_SHARD: ${{ matrix.target.shard }}" in flow
