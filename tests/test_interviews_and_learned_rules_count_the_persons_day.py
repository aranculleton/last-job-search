"""Interview packs and the rules Claude learns are dated on the person's own day.

The final engine review of 2026-11-11 (item 12): tools/interview_pack.py and tools/learned.py
dated things with the computer's day (date.today()) while the page, the holds and the search
count the person's (person.today(), which also honours a run's fixed day, LJS_TODAY). On a
laptop set to another zone than the profile, or a cloud computer on UTC, the two are a day
apart for hours of every day: a learned rule dated the day after it was given, and so its
review day and "kept on" with it, a posting "retrieved" tomorrow. Here the person's day is
held three days from the computer's, as no zone makes it but every zone's difference shows.
Every name is invented.
"""
from __future__ import annotations

import ast
import datetime as dt
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402


@pytest.fixture
def theirs(monkeypatch):
    """The person's day, three days from the computer's."""
    day = dt.date.today() + dt.timedelta(days=3)
    monkeypatch.setattr(person, "today", lambda *a, **k: day)
    return day


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def test_an_interview_pack_dates_on_the_persons_day(theirs, tmp_path):
    folder = str(tmp_path / "kestrel_mutual_data_analyst")
    assert interview_pack.write_posting(folder, "Kestrel Mutual", "Data Analyst") == "written"
    with open(os.path.join(folder, "job_posting.md"), encoding="utf-8") as fh:
        assert f"**Retrieved:** {theirs.isoformat()}," in fh.read()
    said = interview_pack.rework_entry("Why this team?", "Lead with the forecasting work.")
    assert said.startswith(f"- {theirs.isoformat()}, mock:"), said


def test_a_learned_rule_is_dated_on_the_persons_day(theirs, profile):
    entry = learned.record("voice", "too stiff for me", "plain and direct; no stock pleasantries",
                           applied_to=["profile/networking.py OPENER"])
    assert entry["date"] == theirs.isoformat(), entry
    assert learned._page_today() == theirs.isoformat()


def _computer_days(path: str) -> list[str]:
    """Each `date.today()` or `datetime.now()` a module reads, by the function it is in, past
    _page_today's own fallback where no profile can be read."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "today" and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "date"):
                if fn.name == "_page_today" and any(
                        isinstance(h, ast.ExceptHandler) and node in list(ast.walk(h))
                        for h in ast.walk(fn)):
                    continue
                found.append(f"{fn.name}:{node.lineno}")
    return sorted(set(found))


def test_neither_reads_the_computers_day():
    for name in ("interview_pack.py", "learned.py"):
        assert _computer_days(os.path.join(ROOT, "tools", name)) == [], name
