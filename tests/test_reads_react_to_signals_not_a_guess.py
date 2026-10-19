"""Browser reads react to what LinkedIn shows, load fewer pages, and keep one count a machine.

From a long networking session on 3.7.0 (2026-10-19): a round that should take minutes
took over two hours, nearly all of it waiting on fixed pacing; the limits were constants a
person could not change; a short list made before the release filled the day with people
already read or closed; each worktree kept its own count, so two chats on one account each
read a full day; and the session spent its tool calls polling "wait: Ns". Invented people
and employers only.
"""
from __future__ import annotations

import datetime
import os
import random
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pace  # noqa: E402
import reading  # noqa: E402

NOW = datetime.datetime(2026, 10, 19, 15, 0)


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


# ------------------------------------------------------------------ one dial, every limit

def test_careful_is_the_old_pace_value_for_value():
    for name, old in (("reads_per_hour", 8), ("reads_per_day", 15), ("gap_seconds", (45, 240)),
                      ("gap_median", 90), ("break_after", (3, 7)), ("break_minutes", (5, 12)),
                      ("dwell_seconds", (20, 60)), ("reads_per_run", 5), ("unplaced", 2),
                      ("paste_top", 3), ("fresh_days", 30), ("loads_per_hour", 8),
                      ("loads_per_day", 15)):
        assert pace.value(name, "careful") == old, name


def test_the_dial_sets_every_limit_and_a_setting_beats_it(monkeypatch):
    monkeypatch.setattr(pace, "_NET", types.SimpleNamespace(PROFILE_READ_RISK="fast"))
    assert pace.preset() == "fast" and pace.value("reads_per_hour") == 20
    assert pace.value("gap_seconds") == (25, 150)
    monkeypatch.setattr(pace, "_NET", types.SimpleNamespace(
        PROFILE_READ_RISK="fast", PROFILE_READS_PER_HOUR=6, PROFILE_READ_GAP_SECONDS=(60, 300)))
    assert pace.value("reads_per_hour") == 6 and pace.value("gap_seconds") == (60, 300)
    assert "your setting" in pace.source("reads_per_hour")
    # Unreadable: the preset, said so; an unknown dial: careful.
    monkeypatch.setattr(pace, "_NET", types.SimpleNamespace(PROFILE_READS_PER_HOUR="lots",
                                                           PROFILE_READ_RISK="reckless"))
    assert pace.preset() == "careful" and pace.value("reads_per_hour") == 8
    assert "could not be read" in pace.source("reads_per_hour")


def test_every_limit_is_named_with_its_reason_in_one_report():
    lines = "\n".join(pace.report())
    for name in pace.LIMITS:
        assert pace.SETTING[name] in lines
    assert "No pace is safe" in lines and "terms forbid automated access" in lines
    # Why reads per run is 5: said in the code and the report.
    assert "five of seven profile reads" in pace.LIMITS["reads_per_run"][1]


def test_limits_prints_the_value_the_source_and_what_binds_now(here, capsys):
    assert reading.main(["limits"]) == 0
    out = capsys.readouterr().out
    assert "PROFILE_READ_RISK" in out and "PROFILE_READS_PER_RUN = 5 (the careful preset)" in out
    assert "the limit that binds" in out


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


def test_a_soft_signal_doubles_the_pause_and_a_second_stops(here):
    reading.page_read("people", "https://example.org/p", NOW - datetime.timedelta(seconds=70))
    last = reading._loads()[-1]
    reading.signal("not_rendering", "a page of 40 characters", NOW - datetime.timedelta(seconds=60))
    g = reading.gate_state(NOW + datetime.timedelta(seconds=last["gap"] - 69), profile=False)
    assert g["kind"] == "wait"                       # the gap it asked for, doubled
    assert not reading.stopped(NOW.date())
    reading.signal("slow", "the page took 40s", NOW)
    assert reading.stopped(NOW.date())


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


def test_the_ramp_starts_low_rises_on_clean_days_and_falls_back_after_a_signal(monkeypatch):
    monkeypatch.setattr(pace, "_NET", types.SimpleNamespace(PROFILE_READ_RISK="fast"))
    today = NOW.date()
    days = [NOW - datetime.timedelta(days=d) for d in (3, 2, 1)]
    assert pace.hourly_ceiling(today, [], {})[0] == 5
    assert pace.hourly_ceiling(today, days[-1:], {})[0] == 10
    assert pace.hourly_ceiling(today, days, {})[0] == 20
    signalled = {"friction": [{"at": (NOW - datetime.timedelta(days=1)).isoformat(), "kind": "slow"}]}
    assert pace.hourly_ceiling(today, days, signalled)[0] == 5


# ------------------------------------------------------------------ pages by kind

def test_list_pages_have_their_own_caps_and_all_loads_one_more(here):
    for i in range(reading.PAGES_PER_HOUR):
        reading.page_read("search", f"https://example.org/s{i}", NOW - datetime.timedelta(minutes=55 - i * 5))
    g = reading.gate_state(NOW, profile=False)
    assert g["kind"] == "later" and "PROFILE_PAGES_PER_HOUR" in g["why"]
    # A profile is still within its own cap, but every load counts toward the ramp.
    assert reading.gate_state(NOW, sends_left=10)["kind"] in ("go", "wait", "later")


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
    got = reading.shortlist(["p6"], NOW.date(), contacts=contacts, sends_left=10)
    assert set(got["pruned"]) == {"p1", "p2"}
    assert got["ids"] == ["p0", "p3", "p4", "p5", "p6"] and got["cap"] == 5
    got = reading.shortlist(["p7"], NOW.date(), contacts=contacts, remove=["p0"], sends_left=10)
    assert got["removed"] == ["p0"] and "p7" in got["ids"] and "p0" not in got["ids"]


def test_the_list_is_sized_to_the_requests_left_today(here):
    contacts = [{"contact_id": f"q{i}", "location": "Leeds"} for i in range(6)]
    got = reading.shortlist([c["contact_id"] for c in contacts], NOW.date(), contacts=contacts,
                            sends_left=1)
    assert got["cap"] == 1 + reading.SKIP_SPARE and len(got["ids"]) == 4
    assert "1 request(s) that can still go today" in got["why"]


# ------------------------------------------------------------------ reads off the critical path

def test_next_names_who_to_read_and_says_done_at_the_end(here, monkeypatch, capsys):
    import state
    people = [{"contact_id": "r1", "name": "Wren Allard", "company": "Fernhill Freight",
               "location": "Leeds", "linkedin_url": "https://www.linkedin.com/in/wren-allard-example"}]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: people)
    reading.shortlist(["r1"], datetime.date.today(), contacts=people, sends_left=10)
    assert reading.main(["next", "--mode", "card"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "Wren Allard" in out and "wren-allard-example" in out and "nothing scrolled" in out
    _profile_load("r1", datetime.datetime.now())
    assert reading.main(["next"]) == reading.EXIT["done"]
    assert "done: nothing left to read" in capsys.readouterr().out


def test_a_card_read_dwells_in_its_own_range():
    lo, hi = reading.CARD_DWELL_SECONDS
    assert all(lo <= reading.dwell(random.Random(s), mode="card") <= hi for s in range(20))


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
