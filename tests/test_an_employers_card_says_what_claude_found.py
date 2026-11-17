"""An employer's card says what Claude's research found about it and whether it clears the
person's bar (issue #263, part 2).

The card brought together an employer's roles, people and interviews, and nothing of what the
app already holds about the employer itself: the facts Claude's research saved
(`company_research/<key>.json`, with the page each came from) and the person's bar
(`tools/bar.py`: pay, prestige or signal). Now the engine hands the page, for each employer the
page names, a few facts (the ones whose quote was checked first, the newest first, three at
most, each short with its source) and the bar's verdict in plain words; an employer with no
research has no facts and the card no block. Every employer, fact and address here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import app_state  # noqa: E402
import company_research  # noqa: E402

FACTS = [
    {"claim": "Opened a second distribution centre in Wakefield this year.",
     "quote": "Our second distribution centre, in Wakefield, opened in March.",
     "url": "https://larkspur.example/news/wakefield", "date_seen": "2026-09-02",
     "quote_checked": "2026-09-02"},
    {"claim": "Its planning team moved forecasting from spreadsheets to Python in 2025.",
     "quote": "We moved our forecasting from spreadsheets to Python last year.",
     "url": "https://www.larkspur.example/careers/planning", "date_seen": "2026-10-20"},
    {"claim": "Runs 140 stores across the north of England. " * 6,
     "quote": "140 stores across the north of England.",
     "url": "https://larkspur.example/about", "date_seen": "2026-10-11",
     "quote_checked": "2026-10-11"},
    {"claim": "Named a new head of supply chain in October.",
     "quote": "We welcome our new head of supply chain.",
     "url": "https://larkspur.example/news/people", "date_seen": "2026-10-14",
     "quote_checked": "2026-10-14"},
    {"claim": "A fact with no page behind it is never said.", "date_seen": "2026-10-24"},
]


def _research(root, company, facts):
    folder = os.path.join(root, company_research.DIR)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, company_research.file_key(company) + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"company": company, "fetched_date": "2026-10-20", "sources": [f.get("url") for f in facts if f.get("url")],
                   "facts": facts}, fh)


# ------------------------------------------------------------------ the engine


def test_the_checked_facts_come_first_newest_first_three_at_most_each_short(tmp_path):
    _research(str(tmp_path), "Larkspur Retail", FACTS)
    got = app_model.employer_facts("Larkspur Retail", root=str(tmp_path))
    # Checked first, newest first among them; the unchecked one after; three at most.
    assert [f["text"][:20] for f in got["facts"]] == ["Named a new head of ", "Runs 140 stores acro", "Opened a second dist"], got
    assert got["more"] == 1, got
    first = got["facts"][0]
    assert first == {"text": "Named a new head of supply chain in October.", "source": "larkspur.example",
                     "url": "https://larkspur.example/news/people", "on": "2026-10-14", "checked": True}, first
    # Short: a long claim is cut at a word with an ellipsis, never mid-word.
    long = got["facts"][1]["text"]
    assert len(long) <= app_model.EMPLOYER_FACT_CHARS + 1 and long.endswith("…") and " " in long, long
    # The same employer however its name is written.
    assert app_model.employer_facts("Larkspur Retail Ltd", root=str(tmp_path))["facts"] == got["facts"]


def test_an_employer_with_no_research_has_no_facts(tmp_path):
    assert app_model.employer_facts("Nobody Researched Co", root=str(tmp_path)) == {"facts": [], "more": 0}
    _research(str(tmp_path), "Thin Facts Ltd", [{"claim": "Said with no page.", "date_seen": "2026-10-01"}])
    assert app_model.employer_facts("Thin Facts Ltd", root=str(tmp_path)) == {"facts": [], "more": 0}


def test_the_bar_is_said_in_plain_words_and_only_where_it_says_something(monkeypatch):
    import bar
    verdicts = {"Larkspur Retail": ("prestige", "tier 2 employer (larkspur): major brand, strong pay band"),
                "Quayside Foods": ("excluded", "food manufacturers are out"),
                "Unheard Of Ltd": ("none", "no stated range, and on none of your employer lists, and nobody has judged it yet")}
    monkeypatch.setattr(bar, "applies", lambda: True)
    monkeypatch.setattr(bar, "verdict", lambda c, posting="", today=None: verdicts[c])
    monkeypatch.setattr(bar, "listed", lambda c, today=None: c != "Unheard Of Ltd")
    assert app_model.employer_bar("Larkspur Retail") == {"bar": "prestige", "said": "A major brand with a strong pay band."}
    assert app_model.employer_bar("Quayside Foods") == {"bar": "excluded", "said": "Food manufacturers are out."}
    # Nobody has judged it: the verdict says nothing about the employer, so nothing is said.
    assert app_model.employer_bar("Unheard Of Ltd") is None
    # A profile with no bar: nothing about any employer.
    monkeypatch.setattr(bar, "applies", lambda: False)
    assert app_model.employer_bar("Larkspur Retail") is None


def _model(state):
    env = dict(os.environ, LJS_PROFILE=app_state.EXAMPLE, LJS_STATE=state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    env.pop("CLAUDE_CODE_REMOTE", None)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now", app_state.NOW],
                       env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_the_model_carries_each_named_employers_facts_and_no_one_elses(tmp_path):
    """Through the page's own build (`app.py model`): the example person applied to Kestrel
    Mutual and has someone there, and Claude researched it; an employer the page names
    nowhere is never carried, however much was found about it."""
    state = app_state.small(str(tmp_path / "state"))
    _research(state, "Kestrel Mutual", [dict(FACTS[0], claim="Kestrel Mutual moved its claims team to Manchester in 2025.",
                                             url="https://kestrel.example/news/manchester")])
    _research(state, "Never Named Anywhere", FACTS[:2])
    m = _model(state)
    assert "employers" in app_model.SECTIONS and isinstance(m.get("employers"), list), sorted(m)
    by = {e["name"]: e for e in m["employers"]}
    assert "Kestrel Mutual" in by, by
    k = by["Kestrel Mutual"]
    assert [f["text"] for f in k["facts"]] == ["Kestrel Mutual moved its claims team to Manchester in 2025."], k
    assert k["facts"][0]["source"] == "kestrel.example" and "bar" not in k, k   # the example sets no bar
    assert not any(company_research.file_key(n) == "never-named-anywhere" for n in by), by
    # Nothing said is nothing carried: an employer with no facts and no bar is not listed.
    assert all(e.get("facts") or e.get("bar") for e in m["employers"]), m["employers"]
    assert app_model.check(m) == []
