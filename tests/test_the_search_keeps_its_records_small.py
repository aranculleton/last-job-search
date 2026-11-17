"""The search's saved records stay small: what a later round reads, and nothing it decides again.

After two months of rounds one copy's seen_jobs.json held 19MB, 23,786 entries, and its
left-out lists about 59MB, 5 to 6MB a round, all committed: every round wrote each posting it
only saw (surfaced, or skipped for a reason the throttle decides again every round) with every
field it had and a sentence of reason, and kept every row its own free gates left out, which
it decides again for free before any fetch (issue 310). Every new chat copied them, every save
staged them, every stage parsed them.

Now a record keeps what a later round reads: in full while the relist rule can match it, then
only when it was seen; a left-out list keeps SEARCH_KEPT rows of each of the search's own
rules and counts the rest, its counts whole; a ruling, an application or anything written by
hand is never touched; the next round shortens a file grown before, and so do two background
upgrades; and a save says when one of the search's files grows past SIZE_WARN_MB. Invented
postings only.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import filtered  # noqa: E402
import rules_view  # noqa: E402
import save_state  # noqa: E402
import throttle  # noqa: E402


def _row(n, company="Oakmere Foods", title="Demand Planner"):
    return {"url": f"https://www.linkedin.com/jobs/view/43000{n:05d}", "title": title,
            "company": company, "location": "Manchester, England, United Kingdom",
            "location_verdict": "PASS", "portal": "linkedin", "date": "2026-11-01",
            "fit": 62, "opportunity": 55, "priority": 34.1}


def _round(path, day, n=200):
    """One round's throttle: n postings skipped as a second role at an employer, one surfaced."""
    data = throttle.load_seen(str(path))
    skipped = [dict(_row(i), skip_reason="same-employer duplicate: a higher-ranked role at "
                                         "Oakmere Foods was surfaced (Senior Demand Planner, "
                                         "fit 71), and one role per employer is shown")
               for i in range(1, n)]
    throttle.write_back(str(path), data, skipped, day, [_row(0)])
    return throttle.load_seen(str(path))["seen"]


def test_a_round_keeps_a_posting_it_only_saw_as_what_a_later_round_reads(tmp_path):
    seen = _round(tmp_path / "seen_jobs.json", "2026-11-10")
    e = seen[_row(1)["url"]]
    assert set(e) <= {"title", "company", "location", "first_seen", "last_seen", "status",
                      "fit", "priority", "skip_reason", "relisted_from"}
    assert e["skip_reason"] == "same-employer duplicate" and e["status"] == "skipped"
    assert (e["first_seen"], e["last_seen"], e["title"]) == ("2026-11-10", "2026-11-10",
                                                             "Demand Planner")
    # Still never a ruling, and still dated: by its own link and as a relist under another.
    urls, pairs = throttle.ruled_out(seen, "2026-11-11")
    assert not urls and not pairs
    relist = dict(_row(999), url="https://www.linkedin.com/jobs/view/4399999999")
    relist["url"] = "https://www.linkedin.com/jobs/view/4399999999"
    assert throttle.first_seen(seen, "2026-11-12")(_row(1)) == "2026-11-10"
    assert throttle.first_seen(seen, "2026-11-12")(relist) == "2026-11-10"


def test_past_the_relist_window_only_when_it_was_seen_is_kept_and_half_a_year_on_nothing(
        tmp_path):
    path = tmp_path / "seen_jobs.json"
    _round(path, "2026-09-01", n=3)
    data = throttle.load_seen(str(path))
    assert throttle.compact(data["seen"], "2026-10-15") == 3
    assert data["seen"][_row(1)["url"]] == {"first_seen": "2026-09-01",
                                             "last_seen": "2026-09-01", "status": "skipped"}
    assert throttle.first_seen(data["seen"], "2026-10-15")(_row(1)) == "2026-09-01"
    assert throttle.compact(data["seen"], "2026-10-15") == 0          # once is enough
    assert throttle.compact(data["seen"], "2027-03-15") == 3 and data["seen"] == {}


def test_a_ruling_an_application_and_anything_written_by_hand_are_never_touched(tmp_path):
    def rec(n):            # as the throttle writes an entry: no field of the round's own row
        return {k: v for k, v in _row(n).items() if k != "date"}
    entries = {
        "a": dict(rec(1), status="excluded", exclusion_reason="eligibility: citizens only",
                  first_seen="2026-01-01"),
        "b": dict(rec(2), status="skipped", skip_reason="scored 58, below the 60 pass bar",
                  first_seen="2026-01-01"),
        "c": dict(rec(3), status="surfaced", first_seen="2026-01-01", notes="the person liked it"),
        "d": dict(rec(4), status="applied", first_seen="2026-01-01"),
    }
    assert throttle.is_record(dict(rec(5), status="surfaced", first_seen="2026-01-01"))
    before = json.loads(json.dumps(entries))
    assert throttle.compact(entries, "2026-11-17") == 0 and entries == before


def test_the_file_a_round_writes_is_a_fraction_of_what_it_was(tmp_path):
    path = tmp_path / "seen_jobs.json"
    # As the throttle writes them (throttle._sighting): the posting's own date is posted_date.
    data = {"seen": {r["url"]: dict({k: v for k, v in r.items() if k != "date"},
                                    first_seen="2026-11-10", last_seen="2026-11-10",
                                    posted_date="2026-11-01", deadline=None, source="cli",
                                    status="skipped", skipped_date="2026-11-10",
                                    skip_reason="company throttle: an application to Oakmere "
                                                "Foods is open (sent 2026-11-02), so a second "
                                                "one in the same fortnight is held back")
                     for r in (_row(i) for i in range(400))}}
    path.write_text(json.dumps(data, indent=2))
    grown = os.path.getsize(path)
    assert throttle.compact_file(str(path), "2026-11-11") == 400
    assert os.path.getsize(path) < grown * 0.55
    assert throttle.compact_file(str(path), "2026-12-30") == 400      # past the window
    assert os.path.getsize(path) < grown * 0.3


# ------------------------------------------------------------------ the left-out lists

def _stage(round_dir, rel, rows):
    p = round_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows))


def test_a_left_out_list_keeps_a_few_of_the_searchs_own_gates_and_every_count(tmp_path):
    r = tmp_path / "rounds" / "r7"
    gone = [dict(_row(i), prefilter="location: Calgary, AB is outside your places")
            for i in range(300)]
    gone += [dict(_row(1000 + i), prefilter="age: posted 40 days ago") for i in range(40)]
    _stage(r, os.path.join("00_scrape", "dropped.json"), gone)
    _stage(r, "06_skipped.json", [dict(_row(2000 + i), skip_reason="company throttle: open "
                                       "application") for i in range(30)])
    summary = tmp_path / "documents" / "rounds"
    path = filtered.write(str(r), str(summary), "r7")
    data = json.load(open(path))
    rows = data["filtered"]
    assert sum(1 for e in rows if e["stage"] == "search") == 2 * filtered.SEARCH_KEPT
    assert sum(1 for e in rows if e["stage"] == "throttle") == 30          # every one kept
    assert data["counts"] == {"location": 300, "age": 40, "company throttle": 30}
    assert sum(data["kinds"].values()) == 370
    # The page counts every row a rule left out, listed or not.
    view = rules_view.left_view(rows, "r7", None, {}, more=data["not_listed"]["kinds"])
    assert view["count"] == 370
    assert sorted(g["count"] for g in view["groups"]) == [30, 40, 300]
    # A cut made again keeps the counts whole.
    filtered.add(str(summary), "r7", [dict(_row(3000), stage="shortlist", rule="place",
                                           reason="remote abroad")])
    data = json.load(open(path))
    assert data["counts"]["location"] == 300 and data["counts"]["place"] == 1


def test_a_list_written_before_is_slimmed_once_and_keeps_its_counts(tmp_path):
    folder = tmp_path / "documents" / "rounds" / filtered.FOLDER
    rows = [{"title": f"Planner {i}", "company": "Oakmere Foods", "url": f"https://x/{i}",
             "stage": "search", "rule": "title", "reason": "title: not a role you search for"}
            for i in range(120)]
    folder.mkdir(parents=True)
    old = folder / "r3.json"
    old.write_text(json.dumps({"round": "r3", "counts": {"title": 120}, "filtered": rows}))
    assert filtered.unslimmed(str(old))
    assert filtered.slim_all(str(tmp_path / "documents" / "rounds")) == ["r3"]
    data = json.load(open(old))
    assert len(data["filtered"]) == filtered.SEARCH_KEPT and data["counts"] == {"title": 120}
    assert not filtered.unslimmed(str(old))
    assert filtered.slim_all(str(tmp_path / "documents" / "rounds")) == []


# ------------------------------------------------------------------ a save says so

def test_a_save_says_when_a_file_of_the_search_has_grown_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(save_state, "SIZE_WARN_MB", 1)
    (tmp_path / "job_scraper").mkdir()
    (tmp_path / "job_scraper" / "seen_jobs.json").write_bytes(b" " * (2 * 1024 * 1024))
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "big.md").write_bytes(b" " * (2 * 1024 * 1024))
    lines = save_state.too_big(str(tmp_path), ["job_scraper/seen_jobs.json", "profile/big.md"])
    assert len(lines) == 1 and "job_scraper/seen_jobs.json holds 2 MB" in lines[0]
    assert "nothing to tell the person" in lines[0]
