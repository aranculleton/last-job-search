"""A widened round searches deeper, never older, and reuses what it already fetched.

`run_round.py --expand` stretched the freshness rule with every widening: 14
days, then 21, then 42. A posting six weeks old is the most expensive false
positive the pipeline has, and "never relax a gate to hit the number" covers
the freshness rule like any other. And each widened round fetched every body
again, though most of what a deeper search finds the round before had fetched.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hydrate  # noqa: E402
import run_round  # noqa: E402


def _round(tmp_path, monkeypatch, *extra):
    """Run main() with every stage stubbed; returns (stage commands, the widened call)."""
    stages, widened = [], []

    def stage(cmd, log, deadline=None, ok=(0,)):
        stages.append(cmd)
        if os.path.basename(cmd[1]) == "hydrate.py":
            out = cmd[cmd.index("--out") + 1]
            with open(out, "w") as fh:
                json.dump([{"url": "https://careers.example.com/jobs/1", "desc": "body"}], fh)

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call",
                        lambda cmd: widened.append(list(cmd)) or 2)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    out = tmp_path / "r1"
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(out), "--from-scraped",
                                      str(scraped), "--summary-dir", str(tmp_path / "summ"),
                                      "--jobage", "14", "--pages", "5", *extra])
    run_round.main()
    return stages, widened, out


def test_a_widened_round_keeps_the_freshness_rule(tmp_path, monkeypatch):
    _, widened, out = _round(tmp_path, monkeypatch, "--expand")
    (cmd,) = widened
    assert cmd[cmd.index("--jobage") + 1] == "14"
    assert cmd[cmd.index("--pages") + 1] == "10"
    # The bodies were handed on, then cleared once the wider round had run.
    cache = cmd[cmd.index("--hydrate-cache") + 1]
    assert cache == str(out / "02_hydrated.json") and not os.path.exists(cache)


def test_a_widened_round_reuses_the_bodies_it_was_handed(tmp_path, monkeypatch):
    stages, _, _ = _round(tmp_path, monkeypatch, "--round", "2",
                          "--hydrate-cache", str(tmp_path / "earlier.json"))
    (hyd,) = [c for c in stages if os.path.basename(c[1]) == "hydrate.py"]
    assert hyd[hyd.index("--cache") + 1] == str(tmp_path / "earlier.json")


def test_hydrate_fills_from_the_cache_and_never_from_a_stand_in(tmp_path):
    earlier = tmp_path / "earlier.json"
    earlier.write_text(json.dumps([
        {"url": "https://www.linkedin.com/jobs/view/analyst-4100000001?trk=x", "desc": "full body"},
        {"url": "https://careers.example.com/jobs/2", "desc": "a snippet",
         "hydrate_error": "detail exit 1"}]))
    bodies = hydrate.cached_bodies(str(earlier))
    assert bodies == {"li:4100000001": "full body"}
