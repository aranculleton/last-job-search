"""Big jobs run side by side in the one helper chat, and never hold it.

The maintainer, 2026-10-29: "are we still able to run networking at the same time as a job
search? and both at the same time as interview prep?" Before, the helper waited on each big
job, so a networking run asked for during a search sat "In line" for up to an hour. Now
`next` says where each job runs, a big one goes to a background agent inside the same chat
(never a new chat), and the helper goes straight back for the next tap. Three at most
(`page_db.HEAVY_CAP`), and the page says "In line" only once three are running.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import page_db  # noqa: E402
import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import NOW, Search, _w  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_the_page_knows_the_same_big_jobs_and_the_same_cap_as_the_engine():
    js = _read("templates/app/app.js")
    kinds = re.search(r"const HEAVY_KINDS = new Set\(\[([^\]]*)\]\)", js).group(1)
    assert {k.strip().strip('"') for k in kinds.split(",")} == \
        {k for k, v in page_db.WORK_KINDS.items() if v["heavy"]}
    assert f"const HEAVY_CAP = {page_db.HEAVY_CAP};" in js and page_db.HEAVY_CAP == 3


def test_next_says_a_big_job_runs_as_a_background_agent_and_light_work_here(search):
    search.put("work", "network~acme", _w("network", "Kestrel Mutual"), version=1)
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--now", NOW))
    assert got["work"] == "network~acme" and got["heavy"] is True
    assert got["run"] == "background agent"
    search.put("work", "network~acme", _w("network", "Kestrel Mutual", status="done"), version=2)
    search.put("work", "talk~1", _w("talk"), version=1)
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--now", NOW))
    assert got["work"] == "talk~1" and got["heavy"] is False and got["run"] == "here"


def test_the_helper_never_waits_on_a_big_job_and_never_makes_a_chat_for_one():
    skill = " ".join(_read(".claude/skills/app/SKILL.md").split())
    assert "A big job never holds this chat" in skill
    assert "`run_in_background: true`" in skill and "`isolation: \"worktree\"`" in skill
    assert "Never wait for either: go straight back to step 3" in skill
    assert "never a new chat" in skill
    # One writer of the page's view, so two agents never write it at once.
    assert "this chat is the one writer of the page's view" in skill
    assert "waited for, with the url" not in skill


def test_a_job_is_in_line_only_once_three_big_ones_are_running():
    js = _read("templates/app/app.js")
    body = js[js.index("  function queuePlace(id, w) {"):]
    body = body[:body.index("\n  }\n") + 4]
    assert "HEAVY_CAP" in body and "if (!heavy(w)) return {pos: 0" in body
