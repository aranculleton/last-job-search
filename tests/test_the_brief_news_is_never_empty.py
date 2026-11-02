"""The brief's news is never empty, and each item says how to use it.

On 2 November the news reader returned "Quiet week.", the record said "Nothing new." and the
page hid its News panel. The maintainer: "what is the point of showing a quiet week? anytime
someone logs in they want to have something that helps ... it should never say nothing new or
some random useless placeholder." Now a thin day widens inside the one reader call (the
searches with no month, back a week and then a month, never a link sent before); each item
ends in how the person can use it (a talking point, an interview question, a reason to write);
a reader that brought nothing carries the last items forward with their day; and the page
shows the newest earlier brief's news while today's is missing. Invented people only.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]
EXAMPLE = os.path.join(ROOT, "profile.example")

import app_model  # noqa: E402
import brief  # noqa: E402

READER = os.path.join(ROOT, ".claude", "agents", "news-reader.md")
PROMPT = os.path.join(ROOT, "automation", "prompts", "morning_brief.md")


def _state(tmp_path) -> str:
    d = str(tmp_path / "state")
    shutil.copytree(os.path.join(EXAMPLE, "state"), d)
    prof = str(tmp_path / "profile")
    shutil.copytree(EXAMPLE, prof, ignore=shutil.ignore_patterns("state", "tips.json"))
    return d


def _run(state, *args, stdin=None):
    env = dict(os.environ, LJS_PROFILE=os.path.join(os.path.dirname(state), "profile"),
               LJS_STATE=state, PYTHONIOENCODING="utf-8",
               LJS_BRIEF_SYNC=os.path.join(state, "sync.txt"))
    env.pop("CLAUDE_CODE_REMOTE", None)
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "brief.py"), *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, input=stdin,
                          encoding="utf-8", timeout=120)


def _claude(out: str) -> list[str]:
    return out.split("FOR CLAUDE, never in the message:\n", 1)[1].splitlines()


def test_a_thin_day_widens_inside_the_one_reader_call(tmp_path):
    out = _run(_state(tmp_path), "--today", "2026-11-02").stdout
    assert len(out) <= brief.TEXT_MAX
    lines = _claude(out)
    first = next(x for x in lines if "given these searches: " in x)
    fresh = first.split("given these searches: ", 1)[1].split("; at most", 1)[0].split(" | ")
    wide = next(x for x in lines if x.startswith("- news, never none: "))
    # Three to five items, back a week and then a month from the day, never none.
    assert "3 to 5 items" in wide and "back to 2026-10-26, then 2026-10-05" in wide
    more = wide.split("with these searches too: ", 1)[1].split(" | ")
    # The wider ones carry no month (a "November 2026" search on the 2nd finds almost
    # nothing), repeat none of today's, and keep the reader within eight searches in all.
    assert more and not any("November 2026" in q for q in more)
    assert not set(more) & set(fresh)
    assert len(fresh) + len(more) <= brief.SEARCHES_MAX


def test_each_employer_in_play_says_how_the_person_is_in_touch_and_is_never_searched(tmp_path):
    out = _run(_state(tmp_path), "--today", "2026-10-25").stdout
    lines = _claude(out)
    play = next(x for x in lines if x.startswith("- news, in play"))
    # The example person is waiting on a reply from someone at Larkspur Retail: the item about
    # that employer can say "worth a line to Juno at Larkspur Retail".
    assert "Larkspur Retail (" in play and "Juno" in play
    searches = " ".join(x for x in lines if "searches" in x)
    assert "Juno" not in searches


def test_wider_never_exceeds_the_reader_cap_and_needs_searches_to_widen():
    watch = [{"what": "Thing %d" % n, "every": "week"} for n in range(8)]
    today = dt.date(2026, 11, 2)
    qs = ["Thing %d November 2026" % n for n in range(6)]
    got = brief.wider(today, [], watch, qs)
    # A subject today's searches leave out comes first: a new subject brings new items.
    assert got == ["Thing 6", "Thing 7"] and len(got) == brief.SEARCHES_MAX - 6
    assert brief.wider(today, [], watch, qs[:2])[:2] == ["Thing 2", "Thing 3"]
    assert brief.wider(today, [], watch, []) == []


def test_a_reader_that_brought_nothing_carries_the_last_items_with_their_day(tmp_path):
    state = _state(tmp_path)
    _run(state, "--today", "2026-10-28", "--write")
    items = ("- Larkspur Retail opens a Leeds data hub (Example Times, 2026-10-27, "
             "https://example.com/n/1). Worth a line to Juno at Larkspur Retail.\n"
             "- Rates held (Example Wire, 2026-10-27, https://example.com/n/2). A point for any "
             "interview this month.\n")
    _run(state, "news", "--today", "2026-10-28", stdin=items)
    _run(state, "--today", "2026-11-02", "--write")
    r = _run(state, "news", "--today", "2026-11-02", stdin="")
    record = open(os.path.join(state, "documents", "briefs", "2026-11-02.md"), encoding="utf-8").read()
    news = record.split("## News", 1)[1]
    assert not re.search(r"nothing new|quiet week|searching:", news, re.I)
    assert "Carried from the brief of 2026-10-28." in news and "Leeds data hub" in news
    assert "carried 2 from the brief of 2026-10-28" in r.stdout
    # Older than four weeks is not news: nothing is carried, and nothing stands in for it.
    _run(state, "--today", "2026-12-30", "--write")
    _run(state, "news", "--today", "2026-12-30", stdin="Quiet week.\n")
    late = open(os.path.join(state, "documents", "briefs", "2026-12-30.md"), encoding="utf-8").read()
    assert "## News" not in late and "Quiet week" not in late


def test_the_page_shows_the_newest_earlier_news_while_todays_is_missing(tmp_path):
    d = tmp_path / "briefs"
    d.mkdir()
    (d / "2026-10-29.md").write_text(
        "# Brief, 2026-10-29\n\n## News\n\nFrom search results.\n\n- A launch (Example Times, "
        "2026-10-28, https://example.com/a). A question for your interview there.\n",
        encoding="utf-8")
    (d / "2026-11-01.md").write_text("# Brief, 2026-11-01\n\n## News\n\nQuiet week.\n", encoding="utf-8")
    for today_news in ("Nothing new.", brief.NEWS_HOLDER):
        (d / "2026-11-02.md").write_text("# Brief, 2026-11-02\n\n## Owed\n\n- One\n\n## News\n\n%s\n"
                                         % today_news, encoding="utf-8")
        files = sorted(str(p) for p in d.iterdir())
        secs = app_model.brief_sections(open(files[-1], encoding="utf-8").read())
        ctx = types.SimpleNamespace(today=dt.date(2026, 11, 2))
        day = app_model._news_fallback(ctx, secs, files[:-1])
        assert day == "2026-10-29"
        news = [s for s in secs if s["kind"] == "news"][0]
        assert len(news["items"]) == 1 and "A launch" in news["items"][0]["text"]
    # Today's own news wins, and no older day is named.
    (d / "2026-11-02.md").write_text("# Brief, 2026-11-02\n\n## News\n\n- Fresh (X, 2026-11-02, "
                                     "https://example.com/f). Use it.\n", encoding="utf-8")
    secs = app_model.brief_sections((d / "2026-11-02.md").read_text(encoding="utf-8"))
    assert app_model._news_fallback(types.SimpleNamespace(today=dt.date(2026, 11, 2)), secs,
                                    sorted(str(p) for p in d.iterdir())[:-1]) == ""
    # The page names the day the items it shows were gathered.
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert "newsAsOf(b.news_date || b.date)" in js


def test_the_reader_and_the_prompt_never_settle_for_nothing():
    reader = open(READER, encoding="utf-8").read()
    prompt = open(PROMPT, encoding="utf-8").read()
    # No return that says nothing was found, and no message line standing in for news.
    assert "`Nothing new.`" not in reader and "Quiet week.\"" not in prompt
    assert "Three to six lines" in reader and "how the person can use it" in reader
    assert "Never put a person's name in a search." in reader
    assert "Never\n\"Nothing new\"" in prompt or "Never \"Nothing new\"" in prompt.replace("\n", " ")


def test_the_lines_for_claude_are_never_cut(tmp_path, monkeypatch):
    """A long brief was cut at TEXT_MAX whole, and the cut fell on the republish and the page's
    update (the maintainer's own state, 2026-11-02): now only the message gives way."""
    monkeypatch.setattr(brief, "claude_lines", lambda b: ["step %d %s" % (n, "x" * 600)
                                                          for n in range(6)] + ["the page, last"])
    monkeypatch.setattr(brief, "message_lines", lambda b, owed_max: ["Brief"] + ["owed"] * owed_max)
    monkeypatch.setattr(brief, "setting", lambda name: "standard")
    out = brief.render_text({})
    assert out.rstrip().endswith("- the page, last") and "cut at" not in out
    assert out.count("owed") == 2
