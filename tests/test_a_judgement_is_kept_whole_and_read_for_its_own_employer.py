"""`bar.py judge` keeps every judgement, and a judgement speaks for its own employer only.

- A judged file it could not read (git conflict markers, after two chats each judged one
  employer) was read as empty, and the next judgement wrote back only its own row: the
  others were gone, and meanwhile every verdict read "not on your employer lists yet".
- Judgements made at the same moment crashed on one shared temporary file, or wrote over
  each other.
- A judgement was looked up by the company key, which drops "Insurance", "Software" or
  "Global" from the end, so "Brackwater Software" judged spoke for "Brackwater Insurance".
- `unjudged`, and the networking tools' latest round, picked "the newest" saved round by
  the file's time, which a fresh clone gives every file alike.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "network"))

import bar  # noqa: E402


@pytest.fixture
def judged_file(tmp_path, monkeypatch):
    f = tmp_path / "employers_judged.json"
    monkeypatch.setattr(bar, "_judged_path", lambda: str(f))
    bar._judged_cache.clear()
    yield f
    bar._judged_cache.clear()


def test_a_file_it_cannot_read_is_never_written_over(judged_file, capsys):
    for name in ("Fernbrook Labs", "Gorsefield Trading", "Hollin Data"):
        bar.judge(name, bar.SIGNAL, "invented", today="2026-10-21")
    good = judged_file.read_text(encoding="utf-8")
    broken = "<<<<<<< HEAD\n" + good + "=======\n" + good + ">>>>>>> theirs\n"
    judged_file.write_text(broken, encoding="utf-8")
    with pytest.raises(ValueError) as e:
        bar.judge("Brindle Works", bar.NONE, "a small agency", today="2026-10-21")
    assert "employers_judged.json" in str(e.value)
    assert judged_file.read_text(encoding="utf-8") == broken
    assert bar.main(["judge", "Brindle Works", "none", "a small agency"]) == 2
    assert "employers_judged.json" in capsys.readouterr().out
    # Read, it says so once, plainly, and reads no judgement from it.
    assert bar.verdict("Fernbrook Labs")[0] == bar.NONE
    assert "employers_judged.json cannot be read" in capsys.readouterr().err


def _judge_one(args):
    path, i = args
    env = {**os.environ}
    code = ("import sys; sys.path.insert(0, %r); import bar; bar._judged_path = lambda: %r; "
            "bar.judge('Invented Firm %d', 'none', 'test %d', today='2026-10-21')"
            % (TOOLS, path, i, i))
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").returncode


def test_judgements_made_at_once_are_all_kept(judged_file):
    n = 12
    with multiprocessing.Pool(n) as pool:
        codes = pool.map(_judge_one, [(str(judged_file), i) for i in range(n)])
    assert codes == [0] * n
    kept = json.loads(judged_file.read_text(encoding="utf-8"))
    assert len(kept) == n


def test_a_judgement_speaks_for_its_own_employer_only(judged_file):
    bar.judge("Brackwater Software", bar.NONE, "a two-person web studio", today="2026-10-21")
    assert bar.verdict("Brackwater Software")[1] == "judged 2026-10-21: a two-person web studio"
    assert bar.verdict("Brackwater Software Ltd")[1].startswith("judged")
    for other in ("Brackwater Insurance", "Brackwater Financial Services", "Brackwater Global"):
        assert "two-person web studio" not in bar.verdict(other)[1], other
        assert not bar.listed(other)
    # Two employers that share a key are judged apart, and neither overwrites the other.
    bar.judge("Brackwater Insurance", bar.PRESTIGE, "a large insurer", today="2026-10-21")
    assert bar.verdict("Brackwater Software")[0] == bar.NONE
    assert bar.verdict("Brackwater Insurance")[0] == bar.PRESTIGE


def test_an_older_file_keyed_by_company_key_is_still_read(judged_file):
    judged_file.write_text(json.dumps({"brackwater": {
        "name": "Brackwater Software", "verdict": "signal", "why": "an older entry",
        "date": "2026-10-01"}}), encoding="utf-8")
    assert bar.verdict("Brackwater Software")[0] == bar.SIGNAL
    bar.judge("Brackwater Software", bar.NONE, "judged again", today="2026-10-21")
    kept = json.loads(judged_file.read_text(encoding="utf-8"))
    assert [r["why"] for r in kept.values()] == ["judged again"]


def _rounds(tmp_path):
    d = tmp_path / "rounds"
    d.mkdir()
    for n in (18, 29, 21, 3):
        (d / f"r{n}.json").write_text(json.dumps([
            {"company": f"Round {n} Employer", "title": "Analyst", "fit": 70}]), encoding="utf-8")
        # A fresh clone's times, git having written r3 last.
        t = 1_800_000_000 + (1 if n == 3 else 0)
        os.utime(d / f"r{n}.json", (t, t))
    return d


def test_the_newest_round_is_the_highest_numbered_however_the_files_are_dated(judged_file,
                                                                              tmp_path,
                                                                              monkeypatch):
    d = _rounds(tmp_path)
    monkeypatch.setattr(bar.person, "state", lambda *p: str(d / p[-1]) if p[-1] == "*.json"
                        else str(d))
    assert bar.unjudged() == ["Round 29 Employer"]
    import why
    assert why.open_roles("Round 29 Employer", str(d))
    assert why.open_roles("Round 3 Employer", str(d)) == []
