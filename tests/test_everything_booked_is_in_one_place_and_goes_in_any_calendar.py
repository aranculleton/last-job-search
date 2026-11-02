"""Everything booked or due ahead is in one list, and each goes into any calendar in a tap.

The maintainer, 2026-11-02: "I keep losing track of things... there's no consistent way to
view upcoming things I've booked like interviews, calls etc." What was booked lived in
three places that never met: an application's interview stages, a contact marked "call
booked" (its time only in the words of its next action) and the closing day of an
application drafted and not sent. `tools/upcoming.py` puts them in one list by day, with
what the person adds themselves, and nothing that is a follow-up. Each item carries a Google
Calendar link, two Outlook links and an iCalendar event, so no account is ever connected.
Every person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import csv
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_state  # noqa: E402
import upcoming  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

THORNBURY = os.path.join("documents", "applications", "thornbury_bank_risk_analyst_thornbury")
JUNO, WREN = "larkspur_retail_castellan", "fernhill_freight_halloway"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _outcome(search, lines):
    path = os.path.join(search.state, THORNBURY, "outcome.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n" + "".join(x + "\n" for x in lines))


def _contact(search, cid, **change):
    path = os.path.join(search.state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["contact_id"] == cid:
            r.update(change)
    app_state._save_csv(path, rows, list(rows[0].keys()))


def _tracker(search, company, **change):
    path = os.path.join(search.state, "job_search_tracker.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["company"] == company:
            r.update(change)
    app_state._save_csv(path, rows, list(rows[0].keys()))


def _up(search):
    m = search.model()
    assert not [b for b in app_model.check(m) if "upcoming" in b]
    return m["upcoming"]


# ------------------------------------------------------------------ a time said in words


@pytest.mark.parametrize("said, home, want", [
    ("Call booked Thursday 2pm ET on Teams", "Europe/London", ("14:00", None, "America/New_York")),
    ("Intro call 18:00-18:30 UK", "America/Toronto", ("18:00", "18:30", "Europe/London")),
    ("Coffee at 9:30 am", "Europe/London", ("09:30", None, "Europe/London")),
    ("Chat at 14:00", "America/Toronto", ("14:00", None, "America/Toronto")),
    ("call 2:30pm to 3pm EST", "UTC", ("14:30", "15:00", "America/New_York")),
    ("lunch at 12pm", "UTC", ("12:00", None, "UTC")),
])
def test_a_time_written_in_a_next_action_is_read_with_its_zone(said, home, want):
    got = upcoming.call_time(said, home)
    assert (got["time"], got["end"], got["zone"]) == want


# The release review (2026-11-02) found each of these read wrong: "at" taken for Atlantic
# time, a range losing its pm, European clocks missed, and an unknown zone read as the
# person's own (a time in the wrong zone is worse than none).
@pytest.mark.parametrize("said, want", [
    ("Call 2pm at their office", ("14:00", None, "Europe/London")),
    ("Coffee 10:00 at Union Station", ("10:00", None, "Europe/London")),
    ("Call 2:30-3pm ET", ("14:30", "15:00", "America/New_York")),
    ("2-3pm", ("14:00", "15:00", "Europe/London")),
    ("2:30 - 3:00 pm", ("14:30", "15:00", "Europe/London")),
    ("11-1pm", ("11:00", "13:00", "Europe/London")),
    ("Call at 14.30", ("14:30", None, "Europe/London")),
    ("Entretien 14h30", ("14:30", None, "Europe/London")),
    ("9.30am coffee", ("09:30", None, "Europe/London")),
])
def test_ranges_words_and_european_clocks_read_right(said, want):
    got = upcoming.call_time(said, "Europe/London")
    assert (got["time"], got["end"], got["zone"]) == want


@pytest.mark.parametrize("said", ["Call 2pm IST", "Screen 10:00 BRT"])
def test_a_zone_the_app_does_not_know_gives_no_time_rather_than_a_wrong_one(said):
    assert upcoming.call_time(said, "Europe/London") is None


@pytest.mark.parametrize("said", ["send the CV by 2026-10-20", "One nudge if no reply",
                                  "Call booked Thursday", "", None, "Look at the 6 new roles",
                                  "10-12 people"])
def test_no_time_is_read_where_none_is_written(said):
    assert upcoming.call_time(said, "UTC") is None


def test_where_a_call_happens_is_read_from_its_words():
    assert upcoming.place("call on Teams, link in the invite") == "Microsoft Teams"
    assert upcoming.place("Zoom") == "Zoom"
    assert upcoming.place("coffee in person near the office") == "In person"
    assert upcoming.place("Call booked Thursday 2pm") is None


# ------------------------------------------------------------------ the calendars


def _timed(**kw):
    return dict(upcoming._item("call", "up-call-x-2026-10-28", "Call with Juno (Larkspur Retail)",
                               "2026-10-28", "14:00", "America/New_York", minutes=30,
                               where="Microsoft Teams", note="Ask about the team"), **kw)


def _whole_day():
    return upcoming._item("test", "up-t-2026-11-04", "Online test due: Thornbury Bank",
                          "2026-11-04")


def test_a_timed_item_opens_google_and_outlook_filled_in_at_the_right_moment():
    item = _timed()
    assert (item["start"], item["end"]) == ("2026-10-28T18:00:00Z", "2026-10-28T18:30:00Z")
    cal = upcoming.links(item, "https://claude.ai/artifact/example")
    g = urllib.parse.urlparse(cal["google"])
    q = urllib.parse.parse_qs(g.query)
    assert (g.netloc, g.path) == ("calendar.google.com", "/calendar/render")
    assert q["action"] == ["TEMPLATE"] and q["text"] == [item["title"]]
    assert q["dates"] == ["20261028T180000Z/20261028T183000Z"]
    assert q["location"] == ["Microsoft Teams"]
    assert "https://claude.ai/artifact/example" in q["details"][0]
    assert sorted(cal) == ["google", "ics", "outlook"]       # one Outlook, the person's own
    u = urllib.parse.urlparse(cal["outlook"])
    o = urllib.parse.parse_qs(u.query)
    assert u.netloc == "outlook.live.com" and o["rru"] == ["addevent"]
    assert o["startdt"] == ["2026-10-28T18:00:00Z"] and o["enddt"] == ["2026-10-28T18:30:00Z"]
    assert o["allday"] == ["false"] and o["subject"] == [item["title"]]
    assert o["location"] == ["Microsoft Teams"]


def test_a_whole_day_ends_the_next_day_as_every_calendar_reads_it():
    item = _whole_day()
    assert item["all_day"] and item["start"] is None and item["time"] is None
    cal = upcoming.links(item)
    assert urllib.parse.parse_qs(urllib.parse.urlparse(cal["google"]).query)["dates"] == ["20261104/20261105"]
    o = urllib.parse.parse_qs(urllib.parse.urlparse(cal["outlook"]).query)
    assert (o["startdt"], o["enddt"], o["allday"]) == (["2026-11-04"], ["2026-11-05"], ["true"])
    ics = cal["ics"]
    assert "DTSTART;VALUE=DATE:20261104\r\n" in ics and "DTEND;VALUE=DATE:20261105\r\n" in ics


def test_the_calendar_file_is_rfc_5545_folded_escaped_and_reminds_an_hour_before():
    long_note = "Bring the portfolio; ask about the team, the stack\\tools and the move. " * 3
    item = _timed(note=long_note, title="Café chat, Thornbury; with the head of risk")
    whole = upcoming.calendar([upcoming.vevent(item, "https://claude.ai/artifact/example")])
    assert whole.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:") and whole.endswith("END:VCALENDAR\r\n")
    assert "\n" not in whole.replace("\r\n", "")              # every line ends CRLF, none bare
    lines = whole.split("\r\n")
    assert all(len(ln.encode("utf-8")) <= 75 for ln in lines)
    unfolded = whole.replace("\r\n ", "")
    assert "SUMMARY:Café chat\\, Thornbury\\; with the head of risk\r\n" in unfolded
    assert "stack\\\\tools" in unfolded and "\\nYour job search page: https://claude.ai/artifact/example" in unfolded
    assert "UID:up-call-x-2026-10-28.last-job-search\r\n" in unfolded
    assert "DTSTART:20261028T180000Z\r\nDTEND:20261028T183000Z\r\n" in unfolded
    assert "LOCATION:Microsoft Teams\r\n" in unfolded and "TRIGGER:-PT1H\r\n" in unfolded
    assert unfolded.count("BEGIN:VEVENT") == 1 and unfolded.count("END:VALARM") == 1


def test_folding_never_splits_a_character():
    line = "SUMMARY:" + "é" * 60
    folded = upcoming._fold(line)
    parts = folded.split("\r\n ")
    assert "".join(parts) == line
    assert all(len(p.encode("utf-8")) <= 75 for p in parts)


# ------------------------------------------------------------------ one list, by day


def test_the_list_holds_interviews_tests_calls_and_closing_days_and_never_a_follow_up(search):
    _outcome(search, [
        "- [x] Phone screen (2026-10-15, with the recruiter)",
        "- [ ] Online assessment (scheduled 2026-10-27)",
        "- [ ] Panel interview (scheduled 2026-10-28 10:00 UK, with the head of risk)",
        "- [ ] Final interview (scheduled 2027-03-01)",           # beyond the window
    ])
    _contact(search, JUNO, status="call_booked", next_action_due="2026-10-30",
             next_action="Call booked Friday 2pm ET on Teams")
    _tracker(search, "Kestrel Mutual", deadline="2026-11-06")
    ups = _up(search)
    kinds = [(u["day"], u["kind"], u["title"]) for u in ups]
    assert kinds == [
        ("2026-10-27", "test", "Online assessment due: Thornbury Bank"),
        ("2026-10-28", "interview", "Panel interview: Thornbury Bank"),
        ("2026-10-30", "call", "Call with Juno (Larkspur Retail)"),
        ("2026-11-06", "deadline", "Apply by: Claims Forecasting Analyst, Kestrel Mutual"),
    ], kinds
    panel = ups[1]
    assert (panel["start"], panel["end"]) == ("2026-10-28T10:00:00Z", "2026-10-28T11:00:00Z")  # GMT from 25 Oct
    assert panel["go"] == {"to": "interviews", "item": "int-thornbury_bank_risk_analyst"}
    assert panel["note"] == "Risk Analyst, with the head of risk"
    call = ups[2]
    assert (call["start"], call["end"], call["place"]) == ("2026-10-30T18:00:00Z", "2026-10-30T18:30:00Z", "Microsoft Teams")
    assert call["go"] == {"to": "contacts", "item": JUNO}
    assert ups[0]["all_day"] and ups[3]["all_day"]
    # A contact owed a nudge is a To do, never the calendar's.
    assert not any(WREN in str(u["go"]) for u in ups)


def test_a_closing_day_shows_only_when_drafted_unsent_and_within_three_weeks(search):
    _tracker(search, "Kestrel Mutual", deadline="2026-11-30")            # 36 days off
    assert not [u for u in _up(search) if u["kind"] == "deadline"]
    _tracker(search, "Kestrel Mutual", deadline="2026-11-06", cv_file="", cover_letter_file="")
    assert not [u for u in _up(search) if u["kind"] == "deadline"]       # nothing drafted yet
    _tracker(search, "Kestrel Mutual", deadline="2026-10-20",
             cv_file="cv/Morgan_Ellis_CV_Kestrel.tex")
    assert not [u for u in _up(search) if u["kind"] == "deadline"]       # already passed


def test_a_finished_process_and_a_held_stage_leave_the_list(search):
    _outcome(search, ["- [x] Panel interview (2026-10-28, with the head of risk)"])
    assert not [u for u in _up(search) if u["kind"] == "interview"]
    _outcome(search, ["- [ ] Panel interview (scheduled 2026-10-28)"])
    _tracker(search, "Thornbury Bank", status="rejected")
    assert not [u for u in _up(search) if u["kind"] == "interview"]


def test_a_call_the_same_day_as_an_interview_there_is_said_once_and_lends_its_zone(search):
    # The stage line has a clock time and no zone; the call note on the same day, at the same
    # time, says ET. Read as the person's own zone it would be five hours out.
    _outcome(search, ["- [ ] Recruiter screen (scheduled 2026-10-29 14:00, with the recruiter)"])
    path = os.path.join(search.state, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    rows.append(dict(rows[0], contact_id="thornbury_bank_ash", name="Ash Pellow",
                     company="Thornbury Bank", company_key="thornbury bank",
                     status="call_booked", next_action_due="2026-10-29",
                     next_action="Screen at 14:00 ET on Zoom"))
    app_state._save_csv(path, rows, list(rows[0].keys()))
    ups = _up(search)
    assert [u["kind"] for u in ups if u["day"] == "2026-10-29"] == ["interview"]
    screen = next(u for u in ups if u["day"] == "2026-10-29")
    assert (screen["zone"], screen["start"], screen["end"]) == (
        "America/New_York", "2026-10-29T18:00:00Z", "2026-10-29T18:30:00Z")


def test_a_time_elsewhere_sits_on_the_day_it_falls_where_the_person_is(search):
    # 18:00 in California on 29 October is 01:00 on the 30th in London: the list and the
    # interview's card must agree on the day.
    _outcome(search, ["- [ ] Final interview (scheduled 2026-10-29 18:00 PT, with the team)",
                      "- [ ] Final interview (scheduled 2026-10-31 10:00, with the panel)",
                      "- [ ] Final interview (scheduled 2026-10-31 14:00, with the director)"])
    ups = [u for u in _up(search) if u["kind"] == "interview"]
    assert ups[0]["day"] == "2026-10-30" and ups[0]["start"] == "2026-10-30T01:00:00Z"
    # Two stages with one name on one day are two items, each its own calendar entry.
    same = [u for u in ups if u["day"] == "2026-10-31"]
    assert len(same) == 2 and len({u["id"] for u in same}) == 2


def test_a_booked_call_carries_its_time_on_the_person_too(search):
    _contact(search, JUNO, status="call_booked", next_action_due="2026-10-30",
             next_action="Call booked Friday 2pm ET")
    person_ = next(p for p in search.model()["people"] if p["id"] == JUNO)
    assert person_["call"]["day"] == "2026-10-30"
    assert person_["call"]["time"] == "18:00"                 # 2pm ET, said in London time


# ------------------------------------------------------------------ what the person adds


def test_something_added_on_the_page_shows_and_comes_off_and_back(search):
    aid = search.act("upcoming.add", "upcoming-add", value={"title": "Careers fair", "on": "2026-11-12", "time": "11:00"}, rev="add")
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    own = [u for u in _up(search) if u["kind"] == "event"]
    assert [(u["title"], u["day"], u["time"]) for u in own] == [("Careers fair", "2026-11-12", "11:00")]
    fair = own[0]
    assert fair["own"] and fair["start"] == "2026-11-12T11:00:00Z"      # London is on GMT then
    assert os.path.isfile(os.path.join(search.state, "documents", "upcoming.json"))
    search.written_back()
    gone = search.act("upcoming.remove", fair["id"], rev=fair["rev"])
    assert search.apply()["ok"] == [gone], search.receipt(gone)
    assert not [u for u in _up(search) if u["kind"] == "event"]
    search.written_back()
    back = search.act("undo", None, value={"undoes": gone})
    assert search.apply()["ok"] == [back], search.receipt(back)
    again = [u for u in _up(search) if u["kind"] == "event"]
    assert [(u["id"], u["title"]) for u in again] == [(fair["id"], "Careers fair")]


@pytest.mark.parametrize("value", [{"title": "", "on": "2026-11-12"},
                                   {"title": "Fair", "on": "next week"},
                                   {"title": "Fair", "on": "2026-11-12", "time": "25:00"}])
def test_something_added_wrong_is_refused_and_nothing_is_written(search, value):
    before = search.files_hash()
    aid = search.act("upcoming.add", "upcoming-add", value=value, rev="add")
    out = search.apply()
    assert aid not in out["ok"]
    assert search.files_hash() == before


@pytest.mark.parametrize("day", ["20261104", "2026-W45-3", "2026-11-04 10:00", "2026-02-30"])
def test_only_a_real_day_written_out_is_kept(tmp_path, monkeypatch, day):
    s = Search(str(tmp_path))
    monkeypatch.setenv("LJS_STATE", s.state)
    monkeypatch.setenv("LJS_PROFILE", s.profile)
    with pytest.raises(ValueError):
        upcoming.add("Fair", day)
    assert upcoming.added() == []


def test_the_command_line_keeps_and_takes_away(tmp_path, monkeypatch, capsys):
    s = Search(str(tmp_path))
    monkeypatch.setenv("LJS_STATE", s.state)
    monkeypatch.setenv("LJS_PROFILE", s.profile)
    assert upcoming.main(["add", "Coffee with a former colleague", "2026-11-03", "9:05", "--note", "near the station"]) == 0
    row = upcoming.added()[-1]
    assert (row["title"], row["day"], row["time"], row["note"]) == (
        "Coffee with a former colleague", "2026-11-03", "09:05", "near the station")
    assert upcoming.main(["add", "Fair", "2026-11-03", "9am"]) == 1
    assert "a time like 14:30" in capsys.readouterr().out
    assert upcoming.main(["remove", row["id"]]) == 0
    assert upcoming.added() == []
    assert upcoming.main(["remove", row["id"]]) == 1


def test_a_page_never_breaks_on_a_list_it_cannot_build(search, monkeypatch):
    import app_model as am

    def boom(*_a, **_k):
        raise RuntimeError("bad line")
    monkeypatch.setattr(upcoming, "build", boom)
    ctx_targets: dict = {}
    assert am._upcoming(type("C", (), {})(), ctx_targets) == []
    assert ctx_targets == {"upcoming-add": {"kind": "upcoming", "rev": "add"}}


def test_every_item_on_the_sample_page_matches_what_the_engine_makes():
    import json
    with open(os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json"), encoding="utf-8") as fh:
        sample = json.load(fh)
    assert not [b for b in app_model.check(sample) if "upcoming" in b]
    kinds = {u["kind"] for u in sample["upcoming"]}
    assert kinds == set(upcoming.KINDS)
    for u in sample["upcoming"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", u["day"])
        assert u["cal"]["ics"].startswith("BEGIN:VEVENT\r\n")
