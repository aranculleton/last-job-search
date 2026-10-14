"""The screen's job-family flags and the networking reasons belong to the profile.

They were an analyst's, written into the app: "reporting and dashboard building
is the whole job", "'modelling' here is valuation, not statistics", and a
networking skip reason saying "revenue role dressed as technical" to a teacher.
The example person is an analyst, so it sets them and scores exactly as before;
a profile that sets nothing gets no analyst wording at all.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import discovery  # noqa: E402
import person  # noqa: E402
import score_posting  # noqa: E402

RECORD = {"id": "1", "company": "Acme", "title": "Analyst", "core_function": "reporting_bi",
          "modelling_kind": "financial_valuation", "evidence": ""}


def _flags(mod):
    return mod.screen(dict(RECORD))["flags"]


def test_the_example_analyst_keeps_its_flags():
    flags = _flags(score_posting)
    assert any("reporting and dashboard building" in f for f in flags), flags
    assert any("valuation modelling" in f for f in flags), flags


def test_a_profile_that_sets_none_gets_no_analyst_wording():
    search = person.module("search")
    with mock.patch.object(search, "SCREEN_WRONG_FAMILY", {}, create=True), \
            mock.patch.object(search, "SCREEN_HOMONYMS", {}, create=True):
        fresh = importlib.reload(score_posting)
        try:
            flags = _flags(fresh)
        finally:
            importlib.reload(score_posting)
    assert not any("dashboard" in f or "modelling" in f for f in flags), flags


def _rule(name):
    return next(r for r in discovery.DISQUALIFIERS if r.name == name)


def test_the_revenue_reason_is_the_persons():
    assert "dressed as technical" in _rule("revenue_role").reason      # the example's own
    src = open(os.path.join(ROOT, "tools", "network", "discovery.py"), encoding="utf-8").read()
    default = re.search(r'"NOT_HIRING_REASON",\s*"([^"]+)"', src).group(1)
    assert "technical" not in default and "your function" in default


def test_a_nurse_can_take_their_own_job_off_the_spam_list():
    text = "Now hiring: nurse, RN and a technician for the ward team"
    assert _rule("spam_bulk_roles").pattern.search(text)
    net = person.module("networking")
    with mock.patch.object(net, "SPAM_BULK_ROLES", ("java", "php", "devops"), create=True):
        fresh = importlib.reload(discovery)
        try:
            rule = next(r for r in fresh.DISQUALIFIERS if r.name == "spam_bulk_roles")
            assert not rule.pattern.search(text)
        finally:
            importlib.reload(discovery)
