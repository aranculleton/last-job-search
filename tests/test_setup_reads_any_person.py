"""Smaller assumptions that only held for one kind of person.

- allocate.py's mentoring theme counted the bare word "junior", so every
  posting FOR a junior role scored mentoring bullets up.
- 04-job-evaluation.md was written around a permit holder; a citizen had permit
  placeholders to fill and nothing on free-movement areas.
- person.json's keys were documented nowhere; profile_names.py lists them now.
- /setup's environment check read any HTTP status as success, so a host the
  network policy refused still "answered", and it never looked at Ashby,
  Workday, pypdf or bun.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import allocate  # noqa: E402
import env_check  # noqa: E402
import profile_names  # noqa: E402


def _matches(theme, text):
    return any(rx.search(text.lower()) for rx in allocate.CUE_RE[theme])


def test_a_junior_role_is_not_a_mentoring_role():
    assert not _matches("mentoring", "junior supply chain analyst, entry level, graduate scheme")


@pytest.mark.parametrize("text", [
    "you will mentor two analysts", "coach the team on SQL",
    "develop junior analysts through code review", "upskill the planners",
])
def test_developing_people_is_still_mentoring(text):
    assert _matches("mentoring", text)


def test_the_evaluation_template_is_written_for_any_status():
    t = open(os.path.join(ROOT, ".claude", "skills", "job-application-assistant",
                          "04-job-evaluation.md"), encoding="utf-8").read()
    gate = t[t.index("## Eligibility Gate"):t.index("## Language Gate")]
    assert "Run this first, for every candidate" in gate
    assert '"citizen, <City>"' in gate and "Citizen of <Country>; no sponsorship needed" in gate
    assert "free-movement area" in gate and "Common Travel Area" in gate


def test_person_json_keys_are_listed_with_where_they_are_read():
    keys = profile_names.collect_person()
    for k in ("documents.noun", "identity.file_prefix", "documents.paper", "identity.country"):
        assert k in keys and keys[k]["where"], k
    assert keys["identity.file_prefix"]["required"]
    # Read with a default, or guarded by a .get(): optional, not needed.
    assert not keys["documents.paper"]["required"]
    assert not keys["identity.linkedin"]["required"]


def test_the_example_sets_every_person_key_a_tool_needs():
    have = profile_names.example_person_keys()
    needed = sorted(k for k, e in profile_names.collect_person().items()
                    if e["required"] and k not in have)
    assert needed == [], f"read with no default but missing from profile.example/person.json: {needed}"


@pytest.mark.parametrize("exit_code,connect,code,verdict", [
    (0, "200", "200", "reachable"),
    (0, "200", "401", "reachable"),          # the host answered: it is reachable
    (0, "000", "404", "reachable"),          # no proxy in the way
    (56, "403", "000", "blocked"),           # the network policy refused the tunnel
    (56, "407", "000", "blocked"),
    (56, "502", "000", "unreachable"),       # DNS or the host, not the policy
    (6, "000", "000", "unreachable"),
    (28, "", "", "unreachable"),
])
def test_a_refused_host_is_not_read_as_reachable(exit_code, connect, code, verdict):
    assert env_check.classify(exit_code, connect, code) == verdict


def test_the_check_covers_every_board_the_app_calls():
    hosts = " ".join(u for _, u in env_check.HOSTS)
    for h in ("linkedin.com", "freehire.me", "greenhouse.io", "lever.co", "ashbyhq.com"):
        assert h in hosts, h
    setup = open(os.path.join(ROOT, ".claude", "commands", "setup.md"), encoding="utf-8").read()
    assert "python3 tools/env_check.py" in setup
    assert '-w "%{http_code}' not in setup
