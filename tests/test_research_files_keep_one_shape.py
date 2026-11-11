"""Every research file keeps one shape, and says so when one does not.

The 2026-11-10 audit (NW-32): research files drifted: three of 149 had no `company`, and
seven were named differently from their employer's key, found only through the old-name
lookup. `python3 tools/company_research.py check` names each file missing its employer, or,
where it holds facts, the day it was fetched or its sources, and each named apart from its
key; it changes nothing. Every employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import company_research as CR  # noqa: E402

FACT = {"text": "Opened a Leeds office.", "url": "https://example.org/a", "quote": "q"}


def _put(root, name, data):
    folder = os.path.join(root, "company_research")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_a_file_missing_its_date_or_named_apart_from_its_key_is_named(tmp_path, capsys):
    root = str(tmp_path)
    _put(root, CR.file_key("Ottergate Foods") + ".json",
         {"company": "Ottergate Foods", "fetched_date": "2026-11-01",
          "sources": ["https://example.org/a"], "facts": [FACT]})
    _put(root, CR.file_key("Quillfeather Bank") + ".json",
         {"company": "Quillfeather Bank", "sources": ["https://example.org/b"], "facts": [FACT]})
    _put(root, "ashgrove-ledger-inc.json",
         {"company": "Ashgrove Ledger", "fetched_date": "2026-11-01",
          "sources": ["https://example.org/c"], "facts": [FACT]})
    # A finding of nobody to contact there holds no facts: no date or sources owed.
    _put(root, CR.file_key("Marlowe Cartage") + ".json",
         {"company": "Marlowe Cartage", "network_presence": {"verdict": "none"}})
    got = CR.shape_problems(root)
    assert [(p["file"], p["why"]) for p in got] == [
        ("ashgrove-ledger-inc.json", "named apart from its employer's key ("
         + CR.file_key("Ashgrove Ledger") + ".json)"),
        (CR.file_key("Quillfeather Bank") + ".json", "no fetched_date")]
    assert CR.main(["check", "--root", root]) == 1
    assert "no fetched_date" in capsys.readouterr().out
    assert os.path.isfile(os.path.join(root, "company_research", "ashgrove-ledger-inc.json"))
