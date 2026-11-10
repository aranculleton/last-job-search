"""The brief's news comes in one round, rests what keeps finding nothing, and keeps out what
the person ruled out.

Three things from one morning's brief (the maintainer, 2026-11-10): today's searches ran, and
only when they came back thin did a second, wider round run, a whole extra wait most mornings;
a watched subject that found nothing new day after day was searched every day all the same;
and an item about a kind of employer the person had ruled out reached their page. Now the
reader is handed every search at once, numbered, runs them in parallel and ranks them in one
round, each item naming the search that found it; a watched subject that found nothing new on
its last three runs rests a week, the dates kept in the person's state and expiring; and the
same exclusions the job round applies by name (tools/bar.py) keep such items off. Invented
people only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]
EXAMPLE = os.path.join(ROOT, "profile.example")

import pytest  # noqa: E402

import bar  # noqa: E402
import brief  # noqa: E402

TODAY = dt.date(2026, 11, 12)
WATCH = [{"what": "BC nursing union pay talks", "every": "day"},
         {"what": "Vancouver hospital hiring", "every": "day"},
         {"what": "BC nurse licensing changes", "every": "week"}]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    (tmp_path / "documents" / "briefs").mkdir(parents=True)
    return tmp_path


def test_every_search_is_numbered_in_one_list_for_one_round():
    qs = brief.queries(TODAY, ["Harbourline Health"], WATCH, searched={})
    wide = brief.wider(TODAY, ["Harbourline Health"], WATCH, qs)
    got = brief.numbered(qs, wide, WATCH, TODAY)
    assert [x["n"] for x in got] == list(range(1, len(got) + 1))
    assert len(got) <= brief.SEARCHES_MAX and any(x["wider"] for x in got)
    # Each search names the watched thing it carries, today's (with the month) and wider.
    by_q = {x["q"]: x["what"] for x in got}
    assert by_q["BC nursing union pay talks November 2026"] == "BC nursing union pay talks"
    assert "BC nurse licensing changes" in {x["what"] for x in got if x["wider"]} | {
        x["what"] for x in got if not x["wider"]}
    assert all(by_q[q] == "" for q in by_q if "Harbourline" in q)   # an employer: never rests
    reader = open(os.path.join(ROOT, ".claude", "agents", "news-reader.md"), encoding="utf-8").read()
    flat = " ".join(reader.split())
    assert "all at once: every WebSearch call in one message, so they run in parallel" in flat
    assert "Never one round and then another" in flat and "One story once" in flat
    assert "- [<number of the search that found it>]" in reader


def test_a_watched_thing_that_finds_nothing_new_three_runs_running_rests_a_week(state):
    what = "BC nurse licensing changes"
    for n in range(2):
        assert brief.note_found({what: 0, "Vancouver hospital hiring": 1},
                                TODAY + dt.timedelta(days=n)) == []
    assert brief.resting(TODAY + dt.timedelta(days=1)) == set()
    third = TODAY + dt.timedelta(days=2)
    assert brief.note_found({what: 0}, third) == [what]
    assert brief.resting(third) == {what.lower()}
    got = json.loads((state / "documents" / "briefs" / "watched.json").read_text())
    assert got["_rest"] == {what.lower(): (third + dt.timedelta(days=7)).isoformat()}
    # Left out of today's searches and the wider ones while it rests...
    due = [w["what"] for w in brief.due_watch(third, WATCH, searched={})]
    assert what not in due and "Vancouver hospital hiring" in due
    qs = brief.queries(third, [], WATCH, searched={})
    assert what not in " ".join(brief.wider(third, [], WATCH, qs))
    # ...and tried again a week later, its rest expired, its count from none.
    later = third + dt.timedelta(days=7)
    assert brief.resting(later) == set()
    assert what in [w["what"] for w in brief.due_watch(later, WATCH, searched={})]
    brief.note_found({what: 0}, later)
    got = json.loads((state / "documents" / "briefs" / "watched.json").read_text())
    assert "_rest" not in got and got["_empty"] == {what.lower(): [later.isoformat()]}
    # Finding something starts it from none.
    brief.note_found({what: 2}, later + dt.timedelta(days=1))
    assert "_empty" not in json.loads((state / "documents" / "briefs" / "watched.json").read_text())


def test_numbered_items_are_kept_once_their_numbers_noted_and_stripped(state, monkeypatch):
    monkeypatch.setattr(brief, "_note_news", lambda kept, today: [])
    searches = brief.numbered(["BC nursing union pay talks November 2026"],
                              ["BC nurse licensing changes"], WATCH, TODAY)
    brief.plan_searched(["BC nursing union pay talks"], TODAY, searches)
    item = ("Union and province reach a tentative deal (Example Times, 2026-11-11, "
            "https://example.com/deal). A point to raise in any interview this month.")
    got = brief.take_news("- [1] %s\n- [1, 2] %s\n" % (item, item), TODAY)
    assert got["kept"] == [item]                                   # one story once, no tag
    watched = json.loads((state / "documents" / "briefs" / "watched.json").read_text())
    assert watched["bc nursing union pay talks"] == TODAY.isoformat()
    assert "_empty" not in watched                                 # both searches found it
    # A reader that numbered its items, with nothing from search 2: noted as found nothing.
    brief.plan_searched(["BC nursing union pay talks"], TODAY, searches)
    brief.take_news("- [1] %s\n" % item.replace("deal)", "deal-2)"), TODAY)
    watched = json.loads((state / "documents" / "briefs" / "watched.json").read_text())
    assert watched["_empty"] == {"bc nurse licensing changes": [TODAY.isoformat()]}
    # A reader that came back with nothing may not have run: nothing is counted against it.
    brief.plan_searched(["BC nursing union pay talks"], TODAY + dt.timedelta(days=1), searches)
    brief.take_news("", TODAY + dt.timedelta(days=1))
    watched = json.loads((state / "documents" / "briefs" / "watched.json").read_text())
    assert watched["_empty"] == {"bc nurse licensing changes": [TODAY.isoformat()]}


def test_news_about_an_employer_kind_the_person_ruled_out_is_left_out(state, monkeypatch):
    """A nurse in Vancouver who will not work for private cosmetic clinics, and who turned
    down one hospital group by name: news about either never reaches their brief."""
    monkeypatch.setattr(brief, "_note_news", lambda kept, today: [])
    monkeypatch.setattr(bar, "EXCLUDED_RULES", [(
        re.compile(r"\bcosmetic (?:clinic|surgery)\w*\b", re.I),
        "a kind of employer the candidate will not work for (private cosmetic clinics)")])
    monkeypatch.setattr(bar, "DECLINED", {"brightwater health group": "declined by the candidate"})
    clinic = ("Glowline Cosmetic Clinics opens three Vancouver sites and hires 40 nurses "
              "(Example Times, 2026-11-11, https://example.com/glow). Shows nurses are in demand.")
    declined = ("Brightwater Health Group to expand its emergency wing (Example Times, "
                "2026-11-11, https://example.com/bw). A point for any interview.")
    fine = ("Province funds 300 new nursing seats (Example Times, 2026-11-11, "
            "https://example.com/seats). A point to raise in any interview this month.")
    assert "cosmetic" in brief.ruled_out(clinic)
    assert brief.ruled_out(declined) == "declined by the candidate"
    assert brief.ruled_out(fine) == ""
    # Only what happened is read: the reader's clause naming the person's own words is not.
    assert brief.ruled_out(fine.replace("A point", "Unlike cosmetic surgery, a point")) == ""
    got = brief.take_news("\n".join("- " + x for x in (clinic, declined, fine)), TODAY)
    assert got["kept"] == [fine] and len(got["ruled_out"]) == 2
    # Never carried forward from an earlier brief either.
    record = state / "documents" / "briefs" / "2026-11-10.md"
    record.write_text("# Brief, 2026-11-10\n\n## News\n\nFrom search results.\n\n- %s\n- %s\n"
                      % (clinic, fine.replace("seats)", "seats-2)")), encoding="utf-8")
    carried, _day = brief.carry_news(TODAY, paths=[str(record)])
    assert len(carried) == 1 and "nursing seats" in carried[0]


def test_on_the_real_path_the_example_persons_excluded_sector_never_reaches_the_record(tmp_path):
    """The example person rules out gambling and tobacco employers (profile.example)."""
    state = str(tmp_path / "state")
    shutil.copytree(os.path.join(EXAMPLE, "state"), state)
    prof = str(tmp_path / "profile")
    shutil.copytree(EXAMPLE, prof, ignore=shutil.ignore_patterns("state", "tips.json"))
    env = dict(os.environ, LJS_PROFILE=prof, LJS_STATE=state, PYTHONIOENCODING="utf-8",
               LJS_BRIEF_SYNC=os.path.join(state, "sync.txt"))
    env.pop("CLAUDE_CODE_REMOTE", None)

    def run(*args, stdin=None):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "brief.py"), *args],
                              cwd=ROOT, env=env, capture_output=True, text=True, input=stdin,
                              encoding="utf-8", timeout=120)
    run("--today", "2026-11-12", "--write")
    items = ("- [1] A casino group opens a Manchester analytics office (Example Times, "
             "2026-11-11, https://example.com/casino). Shows analysts are hired.\n"
             "- [1] A Leeds grocer adds a forecasting team (Example Times, 2026-11-11, "
             "https://example.com/grocer). A point for any interview.\n")
    r = run("news", "--today", "2026-11-12", stdin=items)
    assert "1 left out, about an employer or a kind of employer the person ruled out" in r.stdout
    record = open(os.path.join(state, "documents", "briefs", "2026-11-12.md"), encoding="utf-8").read()
    assert "casino" not in record.split("## News", 1)[1] and "Leeds grocer" in record
    assert "news: only " not in r.stdout             # the reader brought some: no second search
