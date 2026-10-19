"""A round that misses keeps every file its message tells you to read, and names the right one.

The MISSED message sent the reader to 01_dropped.json for "the location and age
gates". Those drops are the scrape's own: scrape_wide applies the age, place and
title gates before it writes kept.json, so they land in 00_scrape/dropped.json,
and 01_dropped.json holds only what the search had already ruled out. The prune
deleted 00_scrape/ whole, so the file that answered the question was gone.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_round  # noqa: E402

DROPPED = [{"title": "Supply Chain Analyst", "company": "Northgate", "location": "London",
            "prefilter": "location: on-site outside the Greater Manchester (london)",
            "desc": "x" * 5000}]


def test_a_missed_round_keeps_the_scrapes_drops_and_names_them(tmp_path, monkeypatch, capsys):
    def stage(cmd, log, deadline=None, ok=(0,)):
        if os.path.basename(cmd[1]) == "scrape_wide.py":
            out = cmd[cmd.index("--out") + 1]
            os.makedirs(out, exist_ok=True)
            for name, rows in (("kept.json", []), ("dropped.json", DROPPED),
                               ("scraped.json", DROPPED)):
                with open(os.path.join(out, name), "w") as fh:
                    json.dump(rows, fh)

    monkeypatch.setattr(run_round, "run", stage)
    out = tmp_path / "r1"
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(out),
                                      "--summary-dir", str(tmp_path / "summ")])
    assert run_round.main() == run_round.EXIT_YIELD_MISSED
    kept = out / "00_scrape" / "dropped.json"
    rows = json.loads(kept.read_text())
    assert rows[0]["prefilter"].startswith("location:") and "desc" not in rows[0]
    assert not (out / "00_scrape" / "scraped.json").exists()
    said = capsys.readouterr().out
    assert os.path.join("00_scrape", "dropped.json") + " for the age, location and title gates" in said
    assert "01_dropped.json for the location" not in said
