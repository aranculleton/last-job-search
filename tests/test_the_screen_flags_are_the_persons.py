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


def test_the_revenue_reason_is_the_persons(monkeypatch):
    assert "dressed as technical" in _rule("revenue_role").reason      # the example's own
    # A profile that sets none gets the app's default, which names no field: read off
    # the rule the tool builds without the setting, not off its source.
    monkeypatch.delattr(person.module("networking"), "NOT_HIRING_REASON")
    try:
        fresh = importlib.reload(discovery)
        default = next(r for r in fresh.DISQUALIFIERS if r.name == "revenue_role").reason
    finally:
        monkeypatch.undo()
        importlib.reload(discovery)
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


def test_the_extracted_screen_cuts_pay_where_the_free_screen_does():
    # The extracted-fields screen cut at the walk-away floor, while the free screen and
    # CLAUDE.md cut only below the cut line and rank the rest: a role the free screen
    # kept was dropped on the model path. The example's cut line is 32,000 and its
    # floor 42,000.
    under_floor = score_posting.screen(dict(RECORD, salary_max=38_000))
    assert under_floor["score_it"] and not under_floor["cuts"], under_floor
    assert any("38,000" in f and "never a cut" in f for f in under_floor["flags"])
    below_line = score_posting.screen(dict(RECORD, salary_max=30_000))
    assert not below_line["score_it"] and "30,000" in below_line["cuts"][0]
    assert score_posting.screen(dict(RECORD, salary_max=50_000))["score_it"]
