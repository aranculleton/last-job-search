"""Browser reads react to what LinkedIn shows, load fewer pages, and keep one count a machine.

From a long networking session on 3.7.0 (2026-10-19): a round that should take minutes
took over two hours, nearly all of it waiting on fixed pacing; the limits were constants a
person could not change; a short list made before the release filled the day with people
already read or closed; each worktree kept its own count, so two chats on one account each
read a full day; and the session spent its tool calls polling "wait: Ns". Since 2026-10-22
the app sets no reading limit of its own (no caps, pauses, breaks or ramp, and no dial):
only LinkedIn's own signals stop a read. Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pace  # noqa: E402
import reading  # noqa: E402

NOW = datetime.datetime(2026, 10, 19, 15, 0)


@pytest.fixture(autouse=True)
def _ledger_keeps_these_dates(monkeypatch):
    # The pace ledger drops what is older than KEEP_DAYS by the calendar, and the loads here
    # are dated in October 2026: kept from then, so these tests pass whatever today is.
    keep = (datetime.date.today() - datetime.date(2026, 10, 1)).days + pace.KEEP_DAYS
    monkeypatch.setattr(pace, "KEEP_DAYS", max(pace.KEEP_DAYS, keep))


@pytest.fixture
def here(tmp_path, monkeypatch):
    state_dir = tmp_path / "chat_a"
    monkeypatch.setattr(reading.person, "state", lambda *p: str(state_dir.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    return tmp_path


def _profile_load(cid, when, gap=60):
    reading.save(cid, {"sources": [{"kind": "browser", "at": when.isoformat(), "next_gap": gap,
                                    "date": when.date().isoformat()}]})


# ------------------------------------------------------------------ no limit of the app's own

def test_no_page_waits_on_a_limit_of_the_apps_own(here, monkeypatch):
    # The maintainer's word, 2026-10-22: at one page every two minutes the waiting was most
    # of a networking run, and only LinkedIn's real limits should stop a read.
    for i in range(120):
        reading.page_read("people", f"https://example.org/p{i}", NOW - datetime.timedelta(seconds=i))
    for i in range(120):
        _profile_load(f"x{i}", NOW - datetime.timedelta(seconds=i))
    assert reading.gate_state(NOW)["kind"] == "go"                     # a page right after one
    assert reading.gate_state(NOW, profile=False)["kind"] == "go"
    assert reading.gate_state(NOW, sends_left=0)["kind"] == "go"       # no requests-left sizing
    assert reading.reads_left(NOW) == (None, reading.NO_LIMITS)
    # A setting of a limit the app removed holds nothing.
    monkeypatch.setattr(pace, "_NET", types.SimpleNamespace(
        PROFILE_READ_RISK="careful", PROFILE_READS_PER_HOUR=1, PROFILE_READ_GAP_SECONDS=(600, 900)))
    assert reading.gate_state(NOW)["kind"] == "go"
    assert "PROFILE_READS_PER_HOUR" in pace.RETIRED and "PROFILE_READ_RISK" in pace.RETIRED
    for gone in ("LIMITS", "PRESET_NAMES", "value", "hourly_ceiling", "record_breach"):
        assert not hasattr(pace, gone), gone


def test_limits_says_there_is_none_of_the_apps_own(here, capsys):
    assert reading.main(["limits"]) == 0
    out = capsys.readouterr().out
    assert "no limit of the app's own" in out
    assert "security check" in out
    # What stops a read, said as a fact; no warning about the person's own account in it.
    assert "terms forbid" not in out and "safe" not in out
    assert "PROFILE_READ_RISK" not in out and "What binds" not in out


def test_a_signal_yesterday_holds_nothing_back_today(here):
    yesterday = NOW - datetime.timedelta(days=1)
    reading.stop("LinkedIn showed a check: security verification", yesterday.date())
    assert reading.stopped(yesterday.date())
    assert not reading.stopped(NOW.date()) and reading.gate_state(NOW)["kind"] == "go"


def test_the_time_a_round_takes_is_the_browsers_own(here):
    got = reading.estimate(3, NOW)
    assert got["seconds"] == 3 * reading.SECONDS_A_READ and got["today"] == 3
    assert "no waiting of the app's own" in got["line"]
    reading.stop("LinkedIn showed a check: security verification", NOW.date())
    assert "cannot start today" in reading.estimate(3, NOW)["line"]


# ------------------------------------------------------------------ one count a machine

def test_two_worktrees_share_one_count_one_stop_and_one_list(here, monkeypatch):
    for i in range(3):
        reading.page_read("people", f"https://example.org/p{i}", NOW - datetime.timedelta(minutes=50 - i))
    reading.stop("LinkedIn showed a check: security verification", NOW.date())
    reading.shortlist(["a1"], NOW.date(), contacts=[{"contact_id": "a1", "location": "Leeds"}],
                      sends_left=10)
    # The second chat's worktree has none of the first's files, only the shared ledger.
    other = here / "chat_b"
    monkeypatch.setattr(reading.person, "state", lambda *p: str(other.joinpath(*p)))
    assert len(reading._loads()) == 3
    assert "security verification" in reading.stopped(NOW.date())
    assert reading.on_shortlist("a1", NOW.date())


def test_a_test_never_writes_a_real_ledger(monkeypatch, tmp_path):
    monkeypatch.delenv("LJS_LEDGER", raising=False)
    monkeypatch.setenv(pace.person.STATE_ENV, str(tmp_path))
    assert pace.ledger_dir().startswith(str(tmp_path))


# ------------------------------------------------------------------ signals

def test_a_hard_signal_stops_the_day_and_is_kept(here):
    reading.signal("http_999", "HTTP ERROR 999", NOW)
    assert "http 999" in reading.stopped(NOW.date())
    assert [x["kind"] for x in pace.friction()] == ["http_999"]
    assert reading.page_kind("This page isn't working\nHTTP ERROR 999")[0] == "check"


def test_a_page_that_came_back_empty_is_said_and_a_second_within_the_hour_stops(here):
    reading.page_read("people", "https://example.org/p", NOW - datetime.timedelta(seconds=70))
    reading.signal("not_rendering", "a page of 40 characters", NOW - datetime.timedelta(seconds=60))
    assert not reading.stopped(NOW.date())
    assert reading.gate_state(NOW, profile=False)["kind"] == "go"      # no pause doubled
    reading.signal("not_rendering", "a page of 38 characters", NOW)
    assert reading.stopped(NOW.date())
    assert reading.gate_state(NOW)["kind"] == "tomorrow"


def test_a_slow_load_stops_nothing(here):
    # A slow page is far more often the person's own connection than LinkedIn (2026-10-22).
    reading.page_read("people", "https://example.org/p", NOW - datetime.timedelta(seconds=70))
    for secs in (60, 30, 0):
        reading.signal("slow", "the page took 40s", NOW - datetime.timedelta(seconds=secs))
    assert not reading.stopped(NOW.date())
    assert reading.gate_state(NOW, profile=False)["kind"] == "go"
    assert [x["kind"] for x in pace.friction()] == ["slow", "slow", "slow"]


def test_a_load_far_slower_than_usual_is_a_soft_signal(here):
    for i, secs in enumerate((3, 4, 3, 5)):
        reading.page_read("people", f"https://example.org/q{i}",
                          NOW - datetime.timedelta(hours=3, minutes=i * 10), load_seconds=secs)
    assert not pace.friction()
    reading.page_read("people", "https://example.org/q9", NOW, load_seconds=40)
    assert [x["kind"] for x in pace.friction()] == ["slow"]


def test_a_page_that_did_not_render_is_not_a_read(here, monkeypatch, capsys):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    reading.shortlist(["c9"], datetime.date.today(), contacts=[{"contact_id": "c9", "location": "Leeds"}],
                      sends_left=10)
    page = here / "blank.txt"
    page.write_text("LinkedIn\n", encoding="utf-8")
    code = reading.main(["read", "c9", str(page), "--source", "browser", "--name", "Wren Allard",
                         "--company", "Fernhill Freight"])
    assert code == reading.EXIT["unknown"]
    assert "did not render" in capsys.readouterr().out
    assert [x["kind"] for x in pace.friction()] == ["not_rendering"]


# ------------------------------------------------------------------ the short list

def test_the_list_drops_people_read_before_or_closed_and_counts_only_who_is_left(here):
    contacts = [{"contact_id": f"p{i}", "location": "Leeds", "status": "not_contacted"}
                for i in range(8)]
    contacts[1]["status"] = "closed"
    yesterday = NOW - datetime.timedelta(days=1)
    reading.save("p2", {"read_on": yesterday.date().isoformat(), "sources": [
        {"kind": "browser", "at": yesterday.isoformat(), "date": yesterday.date().isoformat()}]})
    # A list from earlier today, before the release: six, two of them done with.
    reading._save_shortlist(["p0", "p1", "p2", "p3", "p4", "p5"], NOW.date())
    got = reading.shortlist(["p6"], NOW.date(), contacts=contacts, sends_left=2)
    assert set(got["pruned"]) == {"p1", "p2"}
    assert got["ids"] == ["p0", "p3", "p4", "p5", "p6"] and got["cap"] is None
    got = reading.shortlist(["p7"], NOW.date(), contacts=contacts, remove=["p0"], sends_left=2)
    assert got["removed"] == ["p0"] and "p7" in got["ids"] and "p0" not in got["ids"]


def test_the_list_has_no_cap_of_the_apps_own(here):
    # It was sized to the requests left this week and held under 80 (2026-10-20); with no
    # limit of the app's own, everyone worth writing to goes on it.
    contacts = [{"contact_id": f"q{i}", "location": "Leeds", "company": f"Firm {i}"}
                for i in range(100)]
    got = reading.shortlist([c["contact_id"] for c in contacts], NOW.date(), contacts=contacts,
                            sends_left=1)
    assert got["cap"] is None and len(got["ids"]) == 100 and not got["full"]
    assert reading.shortlist_cap(today=NOW.date())[0] is None


# ------------------------------------------------------------------ reads off the critical path

def test_next_names_who_to_read_and_says_done_at_the_end(here, monkeypatch, capsys):
    import state
    people = [{"contact_id": "r1", "name": "Wren Allard", "company": "Fernhill Freight",
               "location": "Leeds", "linkedin_url": "https://www.linkedin.com/in/wren-allard-example"}]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: people)
    reading.shortlist(["r1"], datetime.date.today(), contacts=people, sends_left=10)
    assert reading.main(["next", "--mode", "card"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    # Since 2026-10-21 every read scrolls to the very end first: Experience and Education
    # are on the page only then.
    assert "Wren Allard" in out and "wren-allard-example" in out and "very end" in out
    _profile_load("r1", datetime.datetime.now())
    assert reading.main(["next"]) == reading.EXIT["done"]
    assert "done: nothing left to read" in capsys.readouterr().out


# ------------------------------------------------------------------ fewer pages

def test_a_people_search_narrowed_to_an_employer_is_learned_then_built(here):
    hand = ("https://www.linkedin.com/search/results/people/?currentCompany=%5B%2212345%22%5D"
            "&geoUrn=%5B%22678%22%5D&keywords=planning&origin=FACETED_SEARCH")
    reading.learn_search(hand, "Fernhill Freight", "Leeds")
    url = reading.search_url("Fernhill Freight", "Leeds", "demand forecasting")
    assert url.startswith(reading.SEARCH_BASE)
    assert "currentCompany=%5B%2212345%22%5D" in url and "geoUrn=%5B%22678%22%5D" in url
    assert "keywords=demand+forecasting" in url and "origin=FACETED_SEARCH" in url
    with pytest.raises(LookupError, match="narrowed to Oakmere Foods"):
        reading.search_url("Oakmere Foods")
    with pytest.raises(ValueError):
        reading.learn_search("https://www.linkedin.com/company/fernhill/people/?keywords=data",
                             "Fernhill Freight")


def test_the_fast_path_prints_only_the_addresses_to_open(here, monkeypatch, capsys):
    import state
    import why
    people = [{"contact_id": "f1", "name": "Wren Allard", "company": "Fernhill Freight",
               "linkedin_url": "https://www.linkedin.com/in/wren-allard-example"}]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: people)
    monkeypatch.setattr(reading, "queue", lambda contacts, today=None: contacts)
    monkeypatch.setattr(why, "ranked", lambda rows, *a, **k: rows)
    assert reading.main(["queue", "--urls"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "https://www.linkedin.com/in/wren-allard-example"
    assert "reading.py paste -" in out[-1]


# ------------------------------------------------------------------ the line before a round

def test_reads_already_sent_to_hold_nothing_back(here, monkeypatch):
    # From a real run (2026-10-20): 18 read today, 10 of them already sent to, and the gate
    # said "18 profiles read today, enough for the 13 request(s) that can still go". There
    # is no such count now, whoever was sent to.
    import state
    start = NOW.replace(hour=8, minute=0)
    for i in range(18):
        _profile_load(f"p{i}", start + datetime.timedelta(minutes=20 * i))
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    later = start + datetime.timedelta(hours=8)
    assert reading.gate_state(later, sends_left=13)["kind"] == "go"
    assert reading.reads_left(later, sends_left=13)[0] is None


def test_the_budget_line_says_there_is_no_limit_or_that_linkedin_stopped_the_day(here):
    line = reading.budget_line(NOW, sends_left=None)
    assert line == f"Reads today: {reading.NO_LIMITS}."
    assert "request(s) left" not in reading.budget_line(NOW, sends_left=2)
    reading.stop("LinkedIn showed a check: Let's do a quick security check", NOW.date())
    assert "stopped for today" in reading.budget_line(NOW, sends_left=None)
