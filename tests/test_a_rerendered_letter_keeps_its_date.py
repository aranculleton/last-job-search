"""A letter rendered again from its kept draft keeps the date it was written.

`resume_gen.letter` prints `letter_date` when a draft carries one, but `build()`
never passed it on and the kept draft never stored it, so every re-render (a
renderer fix reaching an unsent application, the drafts upgrade) printed the
day of the re-render on a letter written weeks before. The first render now
sets `letter_date` in the draft that is kept, and every later one prints it.
Rendering a kept draft with render_application.py also wrote its posting back
into draft.json outside the fence; it is saved as fit_to_page saves now.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import outreach  # noqa: E402
import render_application as R  # noqa: E402


def _draft(**kw):
    return dict({
        "company": "Kestrel Mutual", "role": "Operations Analyst", "abbr": "KestrelMutual",
        "summary": "Operations analyst who builds weekly demand forecasts that move stock.",
        "tools": "SQL, Python", "posting": "Forecast weekly claims demand with SQL and Python.",
        "p1": "Claims come in waves. At Brindle & Hart I forecast demand by depot every week.",
        "p2": "Kestrel Mutual insures homes across the North West.", "lead": "Where I would start:",
        "cl_bullets": [{"label": "Forecasting", "text": "Weekly forecasts across 2,400 SKUs."}],
        "p4": "I am based in Manchester and need no sponsorship.",
    }, **kw)


def test_the_first_render_dates_the_draft_and_later_ones_keep_it():
    a = _draft()
    d = R.build(a)
    assert a["letter_date"] == d["letter_date"] == R.gen._long_date()
    again = R.build(dict(a, letter_date="4 March 2026"))
    assert again["letter_date"] == "4 March 2026"


def test_the_letter_prints_the_kept_date(tmp_path, monkeypatch):
    monkeypatch.setattr(R.gen.docpaths, "letter_tex", lambda abbr: str(tmp_path / "l.tex"))
    R.letter(R.build(_draft(letter_date="4 March 2026")))
    assert "\\currentdate{4 March 2026}" in (tmp_path / "l.tex").read_text()


def test_rendering_a_kept_draft_keeps_its_date_and_never_copies_its_posting(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    folder = outreach.write(_draft(letter_date="4 March 2026"), {}, "2026-03-04")
    for sub in ("cv", "cover_letters"):
        (tmp_path / sub).mkdir()
    kept = os.path.join(folder, "draft.json")
    env = dict(os.environ, LJS_STATE=str(tmp_path),
               LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "render_application.py"), kept],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    [after] = json.load(open(kept, encoding="utf-8"))
    assert "posting" not in after and after["posting_from"] == "job_posting.md"
    assert after["letter_date"] == "4 March 2026"
    [letter] = (tmp_path / "cover_letters").glob("*.tex")
    assert "\\currentdate{4 March 2026}" in letter.read_text(encoding="utf-8")


def test_the_kept_draft_keeps_what_its_score_rested_on(tmp_path, monkeypatch):
    # The round's shortlist is pruned away; the interview pack reads the score's reasons
    # from the kept draft, weeks later.
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    meta = {"fit": 81, "fit_why": ["+ demand forecasting", "- no SAP"], "bar": "pay"}
    folder = outreach.write(_draft(), meta, "2026-03-04")
    with open(os.path.join(folder, "draft.json"), encoding="utf-8") as fh:
        kept = json.load(fh)[0]
    assert kept["fit"] == 81 and kept["fit_why"] == ["+ demand forecasting", "- no SAP"]
    assert kept["bar"] == "pay" and "bar_reason" not in kept
