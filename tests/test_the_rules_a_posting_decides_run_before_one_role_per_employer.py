"""The rules a posting decides run before one role per employer is chosen and before the
round keeps its top rows, so a cut made again has real rows to refill from.

From one person's round (2026-11-16, issue #303): the throttle kept one role per employer
before the place rule ran, and at three employers the role it kept was a remote role abroad
that the cut then removed, while the same employers' roles in the person's own city had
already been skipped as duplicates. The round then kept its top 60 rows, 25 of which failed
the place rule; a cut made again after the evening's judgements could draw only on those 60
and said "the round had no more" with about 1,400 ranked rows never read. Every employer is
invented.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-16"
SAID = "remote, anchored in the neighbouring country"
GOOD = "You will build SQL and Python reporting for the planning team."
LEEDS = "Leeds, England, United Kingdom"
ABROAD = "Remote, Neighbourland"


def _row(n, company, fit, place=LEEDS, title="Data Analyst"):
    return {"title": title, "company": company, "date": "2026-11-14",
            "first_seen": "2026-11-14", "portal": "linkedin", "desc": GOOD, "location": place,
            "url": f"https://www.linkedin.com/jobs/view/{7000 + n}/", "fit": fit,
            "priority": fit + 10, "opportunity": 70}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The example person's state, copied, and a location gate with one neighbouring
    country whose remote roles pass only when the posting says it hires from home."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(prefilter, "_NB", {"remote_reason": SAID})
    monkeypatch.setattr(prefilter, "location_verdict", lambda place, title="": (
        ("FLAG", SAID) if "Neighbourland" in place else ("PASS", "home")))
    monkeypatch.setattr(run_round, "declined_now", lambda: {})
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    return tmp_path, st, seen


def _round(tmp_path, st, seen, monkeypatch, ranked, show, name="r5"):
    """run_round.main() with the ranking stood in by `ranked` and the real throttle run as
    its own process on whatever the round hands it."""
    def stage(cmd, log, deadline=None, ok=(0,)):
        tool = os.path.basename(cmd[1])
        if tool == "fit.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        elif tool == "throttle.py":
            got = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            assert got.returncode == 0, got.stderr

    monkeypatch.setattr(run_round, "run", stage)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]", encoding="utf-8")
    out = tmp_path / "rounds" / name
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(out), "--from-scraped", str(scraped), "--seen", str(seen),
        "--tracker", str(st / "job_search_tracker.csv"),
        "--summary-dir", str(st / "documents" / "rounds"), "--today", TODAY, "--jobage", "14",
        "--show", str(show), "--pages", "1"])
    run_round.main()
    summary = st / "documents" / "rounds" / f"{name}.json"
    return out, json.loads(summary.read_text(encoding="utf-8"))


def test_one_role_per_employer_keeps_the_role_that_can_be_shown(world, monkeypatch, capsys):
    tmp_path, st, seen = world
    ranked = []
    for n, company in enumerate(("Ashgrove Analytics", "Birchmoor Lending",
                                 "Cobbledale Insurance"), 1):
        ranked.append(_row(n, company, 88, place=ABROAD, title="Senior Data Analyst"))
        ranked.append(_row(10 + n, company, 74))
    ranked += [_row(20 + n, c, 70 - n) for n, c in enumerate(
        ("Dunholme Foods", "Eskdale Freight", "Fellbeck Retail"), 1)]
    out, summary = _round(tmp_path, st, seen, monkeypatch, ranked, 6)
    said = capsys.readouterr().out
    got = {(r["company"], r["location"]) for r in summary}
    assert got == {("Ashgrove Analytics", LEEDS), ("Birchmoor Lending", LEEDS),
                   ("Cobbledale Insurance", LEEDS), ("Dunholme Foods", LEEDS),
                   ("Eskdale Freight", LEEDS), ("Fellbeck Retail", LEEDS)}, said
    assert "of the 6 asked for" not in said
    # Every role kept with its posting can be shown, and the remote ones are on the round's
    # left-out list with the reason, where Bring back undoes it.
    kept = json.loads((out / run_round.SHORTLIST).read_text(encoding="utf-8"))
    assert all(r["location"] == LEEDS for r in kept)
    left = json.loads((st / "documents" / "rounds" / "filtered" / "r5.json")
                      .read_text(encoding="utf-8"))["filtered"]
    abroad = [e for e in left if e.get("location") == ABROAD]
    assert len(abroad) == 3 and {e["rule"] for e in abroad} == {"location"}
    assert all("never says it hires from" in e["reason"] for e in abroad)


def test_a_cut_made_again_refills_from_a_reserve_and_says_when_the_kept_rows_ran_out(
        world, monkeypatch, capsys):
    tmp_path, st, seen = world
    monkeypatch.setattr(run_round, "KEEP_TOP", 4)
    ranked = [_row(n, f"Gorsefield Employer {n:02d}", 90 - n) for n in range(1, 15)]
    out, summary = _round(tmp_path, st, seen, monkeypatch, ranked, 2)
    assert [r["company"] for r in summary] == ["Gorsefield Employer 01",
                                               "Gorsefield Employer 02"]
    # The round keeps its top rows and a reserve of three times the number asked for.
    kept = json.loads((out / run_round.SHORTLIST).read_text(encoding="utf-8"))
    assert len(kept) == 4 + 3 * 2
    capsys.readouterr()
    # Rulings made after the round take the first five off: a cut made again refills
    # from the reserve.
    for r in ranked[:5]:
        exclude.add(r["url"], "not this kind of company", r["title"], r["company"],
                    basis="person", today=TODAY, path=str(seen))
    argv = ["run_round.py", "--out", str(out), "--recut", "--show", "2", "--seen", str(seen),
            "--summary-dir", str(st / "documents" / "rounds"), "--today", TODAY,
            "--jobage", "14", "--tracker", str(st / "job_search_tracker.csv")]
    monkeypatch.setattr(sys, "argv", argv)
    assert run_round.main() == 0
    again = json.loads((st / "documents" / "rounds" / "r5.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in again] == ["Gorsefield Employer 06",
                                             "Gorsefield Employer 07"]
    capsys.readouterr()
    # Every kept row ruled out: the cut says the kept rows ran out, never that the round
    # had no more, and how many it ranked and did not keep.
    for r in ranked[5:10]:
        exclude.add(r["url"], "not this kind of company", r["title"], r["company"],
                    basis="person", today=TODAY, path=str(seen))
    assert run_round.main() == 0
    said = capsys.readouterr().out
    assert "found 0 of the 2 asked for" in said
    assert "the round had no more" not in said
    assert "4 more it ranked were not kept" in said
