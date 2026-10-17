"""A ruling rests on something, and stops blocking when that something changes."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import exclude  # noqa: E402
import throttle  # noqa: E402

URL = "https://boards.example.com/oakmere/jobs/123"


def _seen(tmp_path):
    return str(tmp_path / "seen_jobs.json")


def test_a_ruling_under_the_current_rules_blocks(tmp_path):
    path = _seen(tmp_path)
    exclude.add(URL, "triage knockout: requires a chartered accountancy licence",
                "Finance Analyst", "Oakmere Foods", path=path)
    entries = json.load(open(path))["seen"]
    urls, _ = throttle.ruled_out(entries)
    assert any("chartered" in why for why in urls.values())


def test_a_ruling_lapses_when_its_rules_change(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "language gate: Welsh essential", "Data Analyst", "Oakmere Foods", path=path)
    monkeypatch.setattr(exclude, "rules_fingerprint", lambda: "changed00000")
    urls, pairs = throttle.ruled_out(json.load(open(path))["seen"])
    assert urls == {} and pairs == {}


def test_the_persons_own_ruling_holds_until_they_lift_it(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "Morgan: no more food manufacturers", "Data Analyst", "Oakmere Foods",
                basis="person", path=path)
    monkeypatch.setattr(exclude, "rules_fingerprint", lambda: "changed00000")
    assert throttle.ruled_out(json.load(open(path))["seen"])[0]       # rules changed, still holds
    assert len(exclude.lift("food manufacturers", "Morgan would consider them now", path=path)) == 1
    assert throttle.ruled_out(json.load(open(path))["seen"])[0] == {}


def test_the_fingerprint_moves_only_with_a_gate():
    before = exclude.rules_fingerprint()
    s = exclude.person.module("search")
    old = list(s.SCRAPE_QUERIES)
    try:
        s.SCRAPE_QUERIES.append("an extra query")              # not a gate
        assert exclude.rules_fingerprint() == before
    finally:
        s.SCRAPE_QUERIES[:] = old
    langs = s.LANGUAGES_HELD
    try:
        s.LANGUAGES_HELD = langs + ("welsh",)                   # a gate
        assert exclude.rules_fingerprint() != before
    finally:
        s.LANGUAGES_HELD = langs


def test_a_ruling_needs_a_reason(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        exclude.add(URL, "  ", path=_seen(tmp_path))


def test_older_rulings_are_reviewed_once_then_stamped_or_lifted(tmp_path):
    path = _seen(tmp_path)
    json.dump({"seen": {
        "a": {"status": "excluded", "exclusion_reason": "language gate: Welsh essential",
              "title": "Data Analyst", "company": "Oakmere Foods", "url": "a"},
        "b": {"status": "excluded", "exclusion_reason": "stated salary below the floor",
              "title": "Analyst", "company": "Saltmarsh Analytics", "url": "b"},
        "c": {"status": "skipped", "skip_reason": "same-employer duplicate", "url": "c"},
        "d": {"status": "excluded", "exclusion_reason": "posting closed", "url": "d"},
    }}, open(path, "w"))
    groups = exclude.review(path)
    assert [g for g, _, _ in groups] == ["language gate"]      # salary already lapses; the rest are not rulings
    assert exclude.stamp("language gate", "rules", path=path) == 1
    assert exclude.review(path) == []
    entry = json.load(open(path))["seen"]["a"]
    assert entry["basis"] == "rules" and entry["rules"] == exclude.rules_fingerprint()


def test_a_better_screen_never_lifts_the_persons_own_call(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "Morgan: not a fit at 40/100, no more food manufacturers",
                "Data Analyst", "Oakmere Foods", basis="person", today="2026-01-01", path=path)
    monkeypatch.setattr(throttle, "rescreen_since", lambda: "2026-06-01")   # a re-run screen since
    assert throttle.ruled_out(json.load(open(path))["seen"])[0]           # still holds
