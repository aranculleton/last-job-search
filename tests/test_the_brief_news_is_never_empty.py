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
    state = _state(tmp_path)
    # A month's first week: no search carries the month, which found almost nothing on the 2nd.
    early = _claude(_run(state, "--today", "2026-11-02").stdout)
    assert "November 2026" not in next(x for x in early if "given these searches: " in x)
    out = _run(state, "--today", "2026-11-12").stdout
    assert len(out) <= brief.TEXT_MAX
    lines = _claude(out)
    first = next(x for x in lines if "given these searches: " in x)
    fresh = first.split("given these searches: ", 1)[1].split("; at most", 1)[0].split(" | ")
    wide = next(x for x in lines if x.startswith("- news, never none: "))
    # Three to five items, back a week and then a month from the day, never none.
    assert "3 to 5 items" in wide and "back to 2026-11-05, then 2026-10-15" in wide
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
    today = dt.date(2026, 11, 12)
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
             "- Rates held (Example Times, 2026-10-27, https://example.com/n/2). A point for any "
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


def test_a_stage_the_record_marks_done_reaches_the_tracker_row_once(tmp_path):
    """A test taken on 29 October was marked done in the application's record, while its
    tracker row's last note was still the invite and its deadline; a chat reading the row read
    the test as due (2026-11-02). The brief's upkeep writes the stage onto the row, once."""
    import csv
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    state = _state(tmp_path)
    path = os.path.join(state, "job_search_tracker.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    cols = list(rows[0].keys())
    rows.append({c: "" for c in cols})
    rows[-1].update(date="2026-10-01", company="Kestrel Mutual", role="Claims Analyst", status="interview",
                    notes="2026-10-21: screen done 2026-10-20 | 2026-10-23: invited to an online test, "
                          "deadline 2026-11-02")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    env = dict(os.environ, LJS_PROFILE=os.path.join(os.path.dirname(state), "profile"), LJS_STATE=state)
    folder = subprocess.run([sys.executable, "-c", "import docpaths; print(docpaths.app_folder("
                             "'Kestrel Mutual', 'Claims Analyst'))"], cwd=os.path.join(ROOT, "tools"),
                            env=env, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome: Kestrel Mutual - Claims Analyst\n\n**Status:** in_progress\n\n"
                 "## Interview stages reached\n- [x] Recruiter screen (2026-10-20)\n"
                 "- [x] Online test (2026-10-29): taken\n- [ ] Final interview (date to be confirmed)\n")
    for _ in range(2):
        _run(state, "--today", "2026-11-02", "--write")
    notes = next(r for r in csv.DictReader(open(path, encoding="utf-8"))
                 if r["company"] == "Kestrel Mutual")["notes"]
    assert notes.count("2026-10-29: Online test done (from the application's record)") == 1, notes
    # The screen, older than the row's own notes, is not written again.
    assert "Recruiter screen done" not in notes



# ------------------------------------------------------------------ the release review, 2026-11-02

def _tracker_row(state, **row):
    import csv
    path = os.path.join(state, "job_search_tracker.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    cols = list(rows[0].keys())
    rows.append(dict({c: "" for c in cols}, **row))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


def _outcome(state, company, role, text):
    env = dict(os.environ, LJS_PROFILE=os.path.join(os.path.dirname(state), "profile"), LJS_STATE=state)
    folder = subprocess.run([sys.executable, "-c", "import docpaths; print(docpaths.app_folder(%r, %r))" % (company, role)],
                            cwd=os.path.join(ROOT, "tools"), env=env, capture_output=True, text=True,
                            encoding="utf-8").stdout.strip()
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


def _notes(path, company):
    import csv
    return next(r for r in csv.DictReader(open(path, encoding="utf-8")) if r["company"] == company)["notes"]


def test_a_news_note_never_hides_a_stage_and_a_written_heading_is_not_done(tmp_path):
    state = _state(tmp_path)
    path = _tracker_row(state, date="2026-10-01", company="Kestrel Mutual", role="Claims Analyst", status="interview",
                        notes="2026-10-23: invited to an online test | 2026-10-30: news: Kestrel Mutual pauses hiring "
                              "(the brief, from a search result)")
    _outcome(state, "Kestrel Mutual", "Claims Analyst", "# Outcome\n\n## Interview stages reached\n"
             "- [x] Online test (2026-10-29)\n")
    _tracker_row(state, date="2026-10-01", company="Fernhill Freight", role="Planner", status="interview",
                 notes="2026-10-20: screen booked")
    _outcome(state, "Fernhill Freight", "Planner", "# Outcome\n\n## Final interview - 2026-10-30 (cancelled by them, "
             "to be rebooked)\n")
    _run(state, "--today", "2026-11-01", "--write")
    assert "2026-10-29: Online test done" in _notes(path, "Kestrel Mutual")
    assert "done" not in _notes(path, "Fernhill Freight")


def test_a_link_sent_weeks_ago_is_not_sent_again(tmp_path):
    state = _state(tmp_path)
    for day, line in (("2026-11-03", "A hub opens (Example Times, 2026-11-02, https://example.com/a). Use it."),
                      ("2026-11-04", "Rates held (Example Times, 2026-11-03, https://example.com/b). Use it."),
                      ("2026-11-05", "Grocers grow (Example Times, 2026-11-04, https://example.com/c). Use it.")):
        _run(state, "--today", day, "--write")
        _run(state, "news", "--today", day, stdin="- " + line + "\n")
    _run(state, "--today", "2026-11-06", "--write")
    r = _run(state, "news", "--today", "2026-11-06",
             stdin="- A hub opens (Example Times, 2026-11-02, https://example.com/a). Use it.\n")
    assert "0 kept; 1 left out" in r.stdout, r.stdout


def test_a_second_run_the_same_day_keeps_its_own_news(tmp_path):
    state = _state(tmp_path)
    _run(state, "--today", "2026-11-04", "--write")
    line = "- A hub opens (Example Times, 2026-11-03, https://example.com/z). Use it.\n"
    _run(state, "news", "--today", "2026-11-04", stdin=line)
    r = _run(state, "news", "--today", "2026-11-04", stdin=line)
    assert "news: 1 kept" in r.stdout and "carried" not in r.stdout, r.stdout


def test_carried_news_keeps_the_day_it_was_gathered_and_ends_after_four_weeks(tmp_path):
    state = _state(tmp_path)
    _run(state, "--today", "2026-10-01", "--write")
    _run(state, "news", "--today", "2026-10-01", stdin="- Old (Example Times, 2026-09-30, https://example.com/o). Use it.\n")
    for day in ("2026-10-10", "2026-10-20"):
        _run(state, "--today", day, "--write")
        _run(state, "news", "--today", day, stdin="")
    rec = open(os.path.join(state, "documents", "briefs", "2026-10-20.md"), encoding="utf-8").read()
    assert "Carried from the brief of 2026-10-01." in rec
    secs = app_model.brief_sections(rec)
    assert app_model._news_fallback(types.SimpleNamespace(today=dt.date(2026, 10, 20)), secs, []) == "2026-10-01"
    _run(state, "--today", "2026-11-02", "--write")
    _run(state, "news", "--today", "2026-11-02", stdin="")
    late = open(os.path.join(state, "documents", "briefs", "2026-11-02.md"), encoding="utf-8").read()
    assert "Old" not in late.split("## News", 1)[-1] if "## News" in late else True


def test_the_furthest_stage_says_how_the_person_is_in_touch_whatever_the_rows_order():
    rows = [{"company": "Kestrel Mutual", "status": "applied"}, {"company": "Kestrel Mutual", "status": "interview"}]
    for order in (rows, rows[::-1]):
        assert brief.in_play(order, [], [], ["Kestrel Mutual"]) == ["Kestrel Mutual (interviewing)"]


def test_news_is_three_points_when_the_last_four_weeks_have_them_each_in_its_parts(tmp_path):
    """One carried point stood alone for days, as one paragraph (the maintainer, 2026-11-03:
    "the news only has 1 bullet ... quite wall of text-y"). A thin day is filled to three from
    as many earlier briefs as it takes, each item carried only from the brief that found it,
    and a line written before 4.8 without its day is split into its parts too."""
    d = tmp_path / "briefs"
    d.mkdir()
    (d / "2026-10-27.md").write_text(
        "# Brief, 2026-10-27\n\n## News\n\n- Rates held (Example Times, https://example.com/r). "
        "A line for lender interviews.\n- A hub opens (Example Post, 2026-10-26, https://example.com/h). "
        "Worth a note to the team there.\n", encoding="utf-8")
    (d / "2026-10-29.md").write_text(
        "# Brief, 2026-10-29\n\n## News\n\nCarried from the brief of 2026-10-27. From search results.\n\n"
        "- Rates held (Example Times, https://example.com/r). A line for lender interviews.\n", encoding="utf-8")
    (d / "2026-10-30.md").write_text(
        "# Brief, 2026-10-30\n\n## News\n\nFrom search results.\n\n- A launch (Example Times, 2026-10-30, "
        "https://example.com/a). A question for your interview there.\n", encoding="utf-8")
    files = sorted(str(p) for p in d.iterdir())
    got, day = brief.carry_news(dt.date(2026, 11, 3), brief.NEWS_MAX, paths=files)
    assert [x[:8] for x in got] == ["A launch", "Rates he", "A hub op"]
    assert day == "2026-10-30"
    # A new point found today with links already carried is not counted twice.
    more, _ = brief.carry_news(dt.date(2026, 11, 3), 2, skip=["Fresh (X, https://example.com/a). Use it."], paths=files)
    assert [x[:10] for x in more] == ["Rates held", "A hub open"]
    secs = [{"title": "News", "kind": "news", "text": "Nothing new.", "items": []}]
    assert app_model._news_fallback(types.SimpleNamespace(today=dt.date(2026, 11, 3)), secs, files) == "2026-10-30"
    items = secs[0]["items"]
    assert len(items) == 3
    old = next(i for i in items if i["text"].startswith("Rates held"))
    # Its day is the brief that found it, never today's.
    assert (old["what"], old["use"], old["src"], old["date"]) == ("Rates held.", "A line for lender interviews.", "Example Times", "2026-10-27")


def test_widening_always_reaches_the_local_job_market(monkeypatch):
    """Widening only by the same employers and watched things found nothing new three mornings
    running (2026-11-03): the local job market, which has news every week, is always in it."""
    monkeypatch.setattr(brief, "home_place", lambda: "Leeds")
    monkeypatch.setattr(brief, "setting", lambda k: [])
    got = brief.wider(dt.date(2026, 11, 3), ["Kestrel Mutual"], watch=[{"what": "rail fares"}],
                      qs=["rail fares November 2026"])
    assert "Leeds job market news" in got and "Leeds hiring layoffs this week" in got
    assert len(got) <= brief.SEARCHES_MAX - 1
