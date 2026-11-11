"""Every rule the person taught Claude went on the page twice (the second audit of 2026-11-10,
D7): once in "What you have taught it" (`learned`) and again as a row of Your rules (`rules`),
though Your rules never draws a learned rule (it links to the list instead). 232 rules were
155 KB and 140 KB, every read of the page read both, and each new rule rewrote both. A learned
rule is now on the page once. Every rule here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import person  # noqa: E402


def test_a_learned_rule_is_in_the_model_once(tmp_path, monkeypatch):
    import app_model
    import learned
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    rules = [{"area": "messages", "rule": f"Never open a note with a question, case {i}",
              "said": f"no questions first please ({i})", "date": "2026-09-01",
              "status": "active"} for i in range(232)]
    (prof / learned.FILE).write_text(json.dumps({"entries": rules}), encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(prof))
    ctx = app_model.Ctx(dt.date(2026, 11, 10), dt.datetime(2026, 11, 10, 8, tzinfo=dt.timezone.utc))
    targets: dict = {}
    taught = app_model._learned(ctx, targets)
    yours = app_model._rules(ctx, targets)
    assert len(taught) == 232
    assert not [r for r in yours["rows"] if r["kind"] == "learned"]
    text = json.dumps(yours, ensure_ascii=False)
    assert "case 17" not in text and len(text) < 30_000, len(text)
