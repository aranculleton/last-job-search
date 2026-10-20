"""Nothing a round leaves at the top of documents/rounds/ is anything but a round summary.

Each round wrote its paced boards' resume point to documents/rounds/.sweep.json, beside
the summaries. A person's own test reads every documents/rounds/*.json and requires each
to be named like a round (r19), and pathlib's glob matches dotfiles, so every repo's local
CI failed after its first round on 3.7.0. The resume point now lives one folder down,
documents/rounds/.sweep/cursor.json, still under documents/rounds (which is committed).
An old .sweep.json is read once, then moved, by the next round or at once by the sync.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import profile_upgrades  # noqa: E402
import run_round  # noqa: E402
import scrape_wide  # noqa: E402

ROUND_NAME = re.compile(r"^r\d+$")
OLD = {"cityboard-search": {"date": "2026-10-16", "mode": "tail", "next": 3, "sent": 9}}


def _rounds(tmp_path) -> Path:
    return tmp_path / "documents" / "rounds"


def test_a_round_leaves_only_round_summaries_at_the_top(monkeypatch, tmp_path):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    shortlist = tmp_path / "06_shortlist.json"
    shortlist.write_text(json.dumps([{"priority": 80, "fit": 78, "title": "Planner",
                                      "url": "https://jobs.example/1"}]))
    # The two things a round writes under documents/rounds/: its summary and the cursor.
    run_round.write_summary(str(shortlist), person.state(run_round.SUMMARY_DIR), "r19")
    monkeypatch.setattr(scrape_wide, "PLAN", {"cityboard-search": ("tail", 4, 10, 0)})
    scrape_wide.save_cursor({"cityboard-search": 6}, "2026-10-19")
    # The person's check, as they wrote it: pathlib's glob, which matches dotfiles.
    names = sorted(p.stem for p in _rounds(tmp_path).glob("*.json"))
    assert names == ["r19"]
    assert all(ROUND_NAME.match(n) for n in names)
    cursor = _rounds(tmp_path) / ".sweep" / "cursor.json"
    assert json.loads(cursor.read_text())["cityboard-search"]["next"] == 2


def test_an_old_cursor_is_read_once_and_moved_by_the_next_round(monkeypatch, tmp_path):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _rounds(tmp_path).mkdir(parents=True)
    (_rounds(tmp_path) / ".sweep.json").write_text(json.dumps(OLD))
    assert scrape_wide._cursor() == OLD                       # where the last round stopped
    monkeypatch.setattr(scrape_wide, "PLAN", {"otherboard-search": ("tail", 2, 5, 0)})
    scrape_wide.save_cursor({"otherboard-search": 3}, "2026-10-19")
    assert not (_rounds(tmp_path) / ".sweep.json").exists()
    moved = json.loads((_rounds(tmp_path) / ".sweep" / "cursor.json").read_text())
    assert moved["cityboard-search"] == OLD["cityboard-search"] and "otherboard-search" in moved


def test_the_sync_moves_an_old_cursor_at_once(monkeypatch, tmp_path):
    """A person's CI failed from their first round on 3.7.0 until the next one, so the
    move is an instant upgrade the sync runs, not something a round gets round to."""
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    u = profile_upgrades.by_id("sweep-cursor-moved")
    assert u.cost == "instant" and u.needs == "nobody" and not u.pending()
    _rounds(tmp_path).mkdir(parents=True)
    (_rounds(tmp_path) / ".sweep.json").write_text(json.dumps(OLD))
    assert u.pending()
    env = dict(os.environ, LJS_STATE=str(tmp_path),
               LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    p = subprocess.run([sys.executable, *u.command[1:]], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert not (_rounds(tmp_path) / ".sweep.json").exists() and not u.pending()
    assert json.loads((_rounds(tmp_path) / ".sweep" / "cursor.json").read_text()) == OLD
    for path in ("documents/rounds/.sweep.json", "documents/rounds/.sweep/cursor.json"):
        assert any(Path(path).match(g) for g in u.paths), path
    # Run again with nothing to move, it changes nothing and says so.
    p = subprocess.run([sys.executable, *u.command[1:]], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0 and "nothing to move" in p.stdout
