"""A posting that only names the person's skills does not score 100.

The posting's positives alone run past 100: the base 50, a band's +8 and core's cap of 48
make 106. So a posting that named enough of the person's capabilities, each once and in
any sentence, was clamped to 100 beside the best match in the round: a fraud analyst title
scored 100, and one round had ten rows at 100 (2026-11-03). Above 90 a point now counts
half and the posting alone stops at 98, so the top of the ranking still tells rows apart;
100 is for a role a person vouches for too, a live contact or an earlier interview. The
capabilities are a profile's with more of them than the example person has. Invented
employers only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit  # noqa: E402

CORE = [
    (re.compile(r"\bsql\b", re.I), 9, "SQL"),
    (re.compile(r"\bpython\b", re.I), 9, "Python"),
    (re.compile(r"\b(a/b test|experiment)\w*", re.I), 8, "experimentation"),
    (re.compile(r"\b(forecast|regression)\w*", re.I), 8, "forecasting"),
    (re.compile(r"\b(risk scor|fraud)\w*", re.I), 8, "risk scoring"),
    (re.compile(r"\b(pipeline|etl)\b", re.I), 6, "pipelines"),
    (re.compile(r"\b(tableau|dashboard)\b", re.I), 4, "reporting"),
    (re.compile(r"\b(stakeholder)\w*", re.I), 4, "stakeholder-facing"),
]

# Each capability named once, in passing, nothing asked hard.
STACKED = {"title": "Senior Fraud Analyst", "company": "Wexmoor Lending",
           "location": "Manchester, England, United Kingdom",
           "desc": ("Our team uses SQL, Python, Tableau dashboards and an ETL pipeline. You "
                    "will partner with stakeholders on experiments and forecasts.")}
FEWER = dict(STACKED, desc="Our team uses SQL, Python and Tableau dashboards.")


def _fit(job):
    with mock.patch.object(fit, "CORE", CORE):
        return fit.fit(job)


def test_naming_every_skill_once_no_longer_reaches_100():
    got = _fit(STACKED)
    assert got["fit"] == 97, got["fit_why"]          # 50 + 8 + 46 = 104: 90 + 7
    assert got["fit_why"][-1] == ("top of the scale: 104 counted as 97 (above 90 a match "
                                  "counts half, and the posting alone stops at 98)")


def test_the_top_of_the_ranking_still_tells_rows_apart():
    """Two rows that both clamped to 100 keep their order, a point apart or more."""
    more = dict(STACKED, desc=STACKED["desc"] + " Regression and risk scoring too.")
    assert _fit(STACKED)["fit"] > _fit(dict(STACKED, title="Fraud Analyst"))["fit"]
    assert _fit(more)["fit"] == _fit(STACKED)["fit"]   # the same skills named again add nothing


def test_under_the_knee_nothing_changes():
    got = _fit(FEWER)
    assert got["fit"] == 50 + 8 + 9 + 9 + 4 + 8        # 88, as before
    assert not any(w.startswith("top of the scale") for w in got["fit_why"])


def test_a_title_alone_is_not_a_match():
    assert _fit(dict(STACKED, desc=""))["fit"] == 50 + 8 + 8


def test_a_live_contact_still_reaches_100(tmp_path, monkeypatch):
    """Through the stage a round runs: the referral is added after the posting's own score."""
    import throttle
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps([STACKED, dict(STACKED, company="Fernhill Freight")]))
    route = [{"name": "an invented contact", "status": "replied", "next_action": ""}]
    monkeypatch.setattr(throttle, "warm_routes",
                        lambda *a, **k: {"wexmoor lending": route} if not a and not k else {})
    monkeypatch.setattr(sys, "argv", ["fit.py", str(src), "--out", str(out)])
    with mock.patch.object(fit, "CORE", CORE):
        assert fit.main() == 0
    got = {r["company"]: r["fit"] for r in json.loads(out.read_text())}
    assert got == {"Wexmoor Lending": 100, "Fernhill Freight": 97}
