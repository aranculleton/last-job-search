"""A search limited to the employers the person names holds only them, every one that has a
posting passing the rules, and says which had none.

The maintainer asked for a search of 20 named employers (2026-11-06). run_round.py had no way
to limit a search: its saved shortlist was the overall top 10, so the page showed other
companies, and the 20 were filtered by hand from 06_shortlist.json. Now `--employers` aims the
scrape at them (their own boards and searches by their names), filters before anything is
fetched or ranked, keeps a place for each, and names those with no open roles.

Every employer name here is the round fixture's invented one (tests/round_fixture.py).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import round_fixture as F  # noqa: E402

sys.path.insert(0, F.TOOLS)
import run_round  # noqa: E402
from company_key import key  # noqa: E402

# Twelve employers the fixture's ordinary round shortlists, written the way a person might
# ("Wrenfield Freight" for "Wrenfield Freight Ltd", lower case), one whose only posting
# fails a rule (already drafted), and two with no posting at all.
ON_LIST = ["Greyloch", "kestrel mutual", "Wrenfield Freight", "Northvale Bank",
           "Larkspur Retail", "Brindle Hart Logistics", "Fenwick Lane Insurance",
           "Quayside Foods", "Northgate", "Oakmere Foods", "Bankside Freight",
           "Saltmarsh Analytics"]
CUT = ["Fernhill Freight"]
NONE = ["Ashcombe Works", "Mossgate Freight Ltd"]
NAMED = ON_LIST + CUT + NONE

node = pytest.mark.skipif(not shutil.which("node"), reason="the stand-in detail CLI needs node")


@pytest.fixture(autouse=True)
def _rulings_hold(monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")


def _summary(work, name="r1"):
    with open(os.path.join(work, "summary", f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@node
def test_only_the_named_employers_are_on_the_list_every_one_past_ten_and_the_rest_are_named(tmp_path):
    out, work = str(tmp_path / "r1"), str(tmp_path)
    r = F.free_stages(F.KEPT, out, work, extra=("--show", "10", "--employers", ", ".join(NAMED)))
    said = r.stdout + r.stderr
    assert r.returncode == 0, said[-3000:]
    rows = _summary(work)
    named = {key(n) for n in NAMED}
    # Only theirs: nothing else is fetched, ranked or kept.
    assert {key(x["company"]) for x in rows} <= named, [x["company"] for x in rows]
    for stage in ("01_prefiltered.json", "05_ranked.json", "06_shortlist.json"):
        assert {key(x["company"]) for x in _load(os.path.join(out, stage))} <= named, stage
    # Every one with a posting that passes is there, though ten were asked for.
    assert sorted(key(x["company"]) for x in rows) == sorted(key(n) for n in ON_LIST)
    assert len(rows) == 12 > 10
    # Ranked as usual, highest first.
    pri = [x["priority"] for x in rows]
    assert pri == sorted(pri, reverse=True)
    # The ones with nothing on the list are named plainly.
    assert "No open roles found at Ashcombe Works, Mossgate Freight Ltd in the last 14 days." in said
    assert "Open roles found at Fernhill Freight, but none that passes your rules." in said
    assert "found 12 of the" not in said
    # The round keeps the names, so a recut keeps to them.
    kept = _load(os.path.join(out, run_round.NAMED_FILE))
    assert kept["named"] == NAMED and "Ashcombe Works" not in kept["found"]
    again = subprocess.run(
        [sys.executable, os.path.join(F.TOOLS, "run_round.py"), "--recut", "--out", out,
         "--show", "10", "--today", F.TODAY, "--no-seen-write",
         "--seen", os.path.join(work, "state", "job_scraper", "seen_jobs.json"),
         "--tracker", os.path.join(work, "state", "job_search_tracker.csv"),
         "--summary-dir", os.path.join(work, "summary")],
        cwd=F.ROOT, env=dict(os.environ, LJS_PROFILE=os.path.join(F.ROOT, "profile.example"),
                             LJS_STATE=os.path.join(work, "state"), LJS_RESCREEN="off"),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert again.returncode == 0, again.stdout[-2000:] + again.stderr[-2000:]
    assert sorted(key(x["company"]) for x in _summary(work)) == sorted(key(n) for n in ON_LIST)
    assert "No open roles found at Ashcombe Works, Mossgate Freight Ltd" in again.stdout


@node
def test_an_ordinary_round_is_unchanged_and_names_no_employers(tmp_path):
    out, work = str(tmp_path / "r1"), str(tmp_path)
    r = F.free_stages(F.KEPT, out, work, extra=("--show", "10"))
    assert r.returncode == 0, r.stdout[-3000:]
    rows = _summary(work)
    # The overall top 10, other employers and all, as before.
    assert len(rows) == 10
    assert "Dovecote Systems" not in {x["company"] for x in rows}
    assert "employers:" not in r.stdout and "No open roles" not in r.stdout
    assert not os.path.exists(os.path.join(out, run_round.NAMED_FILE))
    assert F.summary(out)["shortlist"] == _load(F.GOLDEN)["shortlist"]


def test_a_recut_with_employers_limits_a_round_already_run(tmp_path):
    """The maintainer's case: an ordinary round's list cut to the named employers afterwards."""
    short = tmp_path / "06_shortlist.json"
    rows = [{"title": f"Analyst {i}", "company": c, "url": f"https://jobs.example/{i}",
             "fit": 80 - i, "priority": 80 - i}
            for i, c in enumerate(["Other One", "Kestrel Mutual", "Other Two", "Other Three",
                                   "Wrenfield Freight Ltd", "Other Four"])]
    short.write_text(json.dumps(rows))
    path = run_round.write_summary(str(short), str(tmp_path / "s"), "r1", show=1,
                                   named=["Wrenfield Freight", "KESTREL MUTUAL"])
    got = _load(path)
    assert [x["company"] for x in got] == ["Kestrel Mutual", "Wrenfield Freight Ltd"]
    # Without names, the number asked for from the top, as ever.
    path = run_round.write_summary(str(short), str(tmp_path / "s"), "r2", show=1)
    assert [x["company"] for x in _load(path)] == ["Other One"]


def test_a_named_employer_keeps_its_place_when_the_room_is_full_of_second_roles(tmp_path):
    """The throttle keeps one role an employer, but where it lets a second through (a warm
    route), no named employer loses its only row to it."""
    short = tmp_path / "06_shortlist.json"
    rows = [{"title": "A", "company": "Greyloch", "url": "https://j.example/1", "priority": 90, "fit": 90},
            {"title": "B", "company": "Greyloch", "url": "https://j.example/2", "priority": 85, "fit": 85},
            {"title": "C", "company": "Northgate", "url": "https://j.example/3", "priority": 50, "fit": 70}]
    short.write_text(json.dumps(rows))
    path = run_round.write_summary(str(short), str(tmp_path / "s"), "r1", show=1,
                                   named=["Greyloch", "Northgate"])
    assert [x["url"] for x in _load(path)] == ["https://j.example/1", "https://j.example/2",
                                              "https://j.example/3"]


def test_the_names_are_read_the_way_the_app_matches_employers(tmp_path):
    assert run_round.named_employers("Acme Ltd, Acme; Brindle Hart\n Quayside Foods ,,") == [
        "Acme Ltd", "Brindle Hart", "Quayside Foods"]
    lines = tmp_path / "employers.txt"
    lines.write_text("Greyloch\n\nNorthgate\n- Oakmere Foods\n")
    assert run_round.named_employers(str(lines)) == ["Greyloch", "Northgate", "Oakmere Foods"]
    listed = tmp_path / "employers.json"
    listed.write_text(json.dumps({"named": ["Greyloch", "Greyloch Ltd"], "found": []}))
    assert run_round.named_employers(str(listed)) == ["Greyloch"]
    assert run_round.named_employers(" , ;") == []
    assert run_round.named_room(10, ["a"] * 20) == 20
    assert run_round.named_room(10, ["a"] * 3) == 10


def test_a_search_of_named_employers_is_aimed_at_them_and_spends_far_fewer_requests(drive_round):
    import scrape_wide
    on = {"linkedin-search": True, "freehire-search": True}
    aimed = scrape_wide.named_tasks(on, 5, ["Kestrel Mutual", "Greyloch"])
    whole = scrape_wide.build_tasks(on, 5)
    assert aimed and len(aimed) < len(whole) / 4
    assert all(t[1].startswith(("Kestrel Mutual ", "Greyloch ")) for t in aimed), aimed
    # Their own boards only, matched as the app matches employer names.
    mine, none = scrape_wide.named_boards(["Wrenfield Freight", "Greyloch"], F.GREENHOUSE)
    assert mine == F.GREENHOUSE and none == ["Greyloch"]
    # The round hands the scrape its names, and a wider round keeps to them.
    calls, spawned = drive_round("--employers", "Kestrel Mutual, Greyloch", "--expand")
    scrape = next(c for c, _ in calls if c[1].endswith("scrape_wide.py"))
    names = scrape[scrape.index("--employers-file") + 1]
    assert run_round.named_employers(names) == ["Kestrel Mutual", "Greyloch"]
    pre = next(c for c, _ in calls if c[1].endswith("prefilter.py"))
    assert pre[2].endswith(os.path.join("00_scrape", "named.json"))
    assert spawned and run_round.named_employers(
        spawned[0][spawned[0].index("--employers") + 1]) == ["Kestrel Mutual", "Greyloch"]


def test_the_scrape_reads_only_the_named_employers_boards_and_searches_by_their_names(tmp_path):
    names = tmp_path / "employers.json"
    names.write_text(json.dumps({"named": ["Wrenfield Freight", "Kestrel Mutual"]}))
    asked = []

    def run(cmd, timeout=90):
        asked.append(cmd[4:])
        return F.fake_run(cmd, timeout)
    out = str(tmp_path / "scrape")
    code, said = F.scrape(out, extra=("--employers-file", str(names)), run=run)
    assert code in (0, 2), said[-2000:]
    probe = ("data", "analyst")      # the health probe's broad word
    searches = [a[a.index("-q") + 1] for a in asked if "-q" in a]
    by_name = [q for q in searches if q not in probe]
    assert by_name and all(q.startswith(("Wrenfield Freight", "Kestrel Mutual"))
                           for q in by_name), searches
    kept = _load(os.path.join(out, "kept.json"))
    assert "https://boards.greenhouse.io/wrenfield/jobs/7001" in {r["url"] for r in kept}
    assert "no board of their own on file for Kestrel Mutual" in said
