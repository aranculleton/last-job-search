"""A round says what each source read and what failed: each site's searches, failures and
postings, the employer boards that returned nothing and why, and what cut the scrape short.

From one person's evening (2026-11-16, issue #300): a round said "a quarter of portal requests
failed" when one in 5,760 had, and nothing of the 17 employer boards it never read. Every board
and employer here is invented, and every request is answered offline
(tests/round_fixture.py).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import round_fixture as F  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-16"


def test_the_round_says_what_each_source_read_and_what_failed(tmp_path, monkeypatch):
    # One more employer board, whose site answers nothing: it is named, with why.
    monkeypatch.setattr(F, "GREENHOUSE", {**F.GREENHOUSE,
                                          "Quarrelwood Bank": ("greenhouse", "quarrelwood")})
    out = tmp_path / "r1" / "00_scrape"
    code, said = F.scrape(str(out))
    report = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    sites = {s["source"]: s for s in report["sites"]}
    assert "linkedin" in sites and sites["linkedin"]["requests"] > 0
    assert sites["linkedin"]["found"] >= sites["linkedin"]["kept"] > 0
    assert "Quarrelwood Bank" in report["boards"]["quiet"]
    assert report["boards"]["found"].get("greenhouse", 0) > 0
    lines = run_round.say_sources(str(tmp_path / "r1"))
    text = "\n".join(lines)
    assert lines[0] == "sources: what each read and what failed"
    assert "  linkedin: " in text and "Quarrelwood Bank" in text
    # The board that refused the probe is said, as it was never searched.
    assert "refused the probe" in text or "refused" in said
    assert "Quarrelwood Bank" in run_round.failed_sources(str(tmp_path / "r1"))
