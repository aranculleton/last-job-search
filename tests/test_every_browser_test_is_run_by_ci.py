"""Every file with a test in a browser is one the page job runs.

Only the page job installs Playwright; everywhere else a browser test skips. The page job
picks its files by a pattern, and five files that took the browser from
test_the_page_works_in_a_browser by name (`from ... import run`) matched none of it, so
their browser tests skipped on every CI run, 4.12 included: about four minutes of checks
that a tap is never dropped silently, run by nobody. tools/everywhere.sh picks its files by
the same pattern.
"""
from __future__ import annotations

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
EVERYWHERE = os.path.join(ROOT, "tools", "everywhere.sh")
# What gives a test a browser: the harness, or the fixtures of the two modules that start it.
USES_A_BROWSER = re.compile(r"app_page/harness\.js|journeys\.browser\(\)"
                            r"|^from test_the_page_(?:works_in_a_browser|journeys) import"
                            r"|^import test_the_page_(?:works_in_a_browser|journeys)", re.M)


def _pattern(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    got = re.findall(r"grep -lE '([^']+)' tests/\*\.py", text)
    assert len(got) == 1, (path, got)
    return got[0]


def test_the_page_job_and_everywhere_pick_files_alike():
    assert _pattern(CI) == _pattern(EVERYWHERE)


def test_every_file_that_starts_a_browser_is_picked():
    picks = re.compile(_pattern(CI))
    missed = []
    for path in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if USES_A_BROWSER.search(text) and not picks.search(text):
            missed.append(os.path.basename(path))
    assert not missed, missed
