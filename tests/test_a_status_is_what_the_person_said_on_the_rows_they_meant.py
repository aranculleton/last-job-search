"""A status is what the person said, written on the rows they meant, by somebody named.

"Applied" reached the tracker only as a hand edit from a chat sentence: /outcome overwrote
the row's `date` with the day it went, nothing said who confirmed it, and nothing said
which rows "applied to all of them" covered. Two chats editing that row then stopped every
merge of the tracker, because `date` is part of the key its rows merge on. Now `date` never
changes, tools/confirm.py writes `applied_on`, `confirmed_by` and `confirmed_at` on exactly
the rows a sentence names, refuses a name that could mean more than one, and `check` finds
what does not add up. Every employer here is invented.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import confirm  # noqa: E402
import followups  # noqa: E402
import merge_state  # noqa: E402
import throttle  # noqa: E402
import what_works  # noqa: E402

HEAD = ["date", "company", "role", "status", "notes", "cv_file", "source"]
TODAY = dt.date(2026, 10, 25)
NOW = dt.datetime(2026, 10, 25, 9, 30)


def _resume(abbr):
    return f"cv/Alex_Example_Resume_{abbr}.tex"


ROWS = [
    {"date": "2026-10-20", "company": "Acme Analytics", "role": "Senior Data Analyst",
     "status": "drafted", "notes": "r3. Scores: fit 78.", "cv_file": _resume("AcmeAnalytics")},
    {"date": "2026-10-20", "company": "Kestrel Mutual", "role": "Pricing Analyst",
     "status": "drafted", "notes": "r3. Scores: fit 74.", "cv_file": _resume("Kestrel")},
    {"date": "2026-10-20", "company": "Kestrel Mutual", "role": "Claims Forecasting Analyst",
     "status": "drafted", "notes": "r3. Scores: fit 71.", "cv_file": _resume("Kestrel_Claims")},
    {"date": "2026-10-21", "company": "Oakmere Foods", "role": "Supply Chain Analyst",
     "status": "drafted", "notes": "r4. Scores: fit 80.", "cv_file": _resume("Oakmere")},
    {"date": "2026-09-01", "company": "Brindle Hart", "role": "Logistics Analyst",
     "status": "applied", "notes": "r1.", "cv_file": _resume("BrindleHart")},
]


def _tracker(tmp_path, rows=ROWS):
    path = str(tmp_path / "job_search_tracker.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEAD})
    return path


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _by(path, company, role):
    return next(r for r in _read(path) if r["company"] == company and r["role"] == role)


def test_applied_writes_who_and_when_and_never_moves_the_date(tmp_path):
    path = _tracker(tmp_path)
    done = confirm.run("applied", ["AcmeAnalytics"], on="2026-10-22", path=path,
                       today=TODAY, now=NOW)
    assert [(r["company"], what) for r, what in done] == [
        ("Acme Analytics", "drafted -> applied, applied on 2026-10-22")]
    row = _by(path, "Acme Analytics", "Senior Data Analyst")
    assert (row["date"], row["status"], row["applied_on"]) == ("2026-10-20", "applied", "2026-10-22")
    assert (row["confirmed_by"], row["confirmed_at"]) == ("person-said", "2026-10-25 09:30")
    assert row["notes"].endswith("2026-10-25: applied on 2026-10-22, confirmed (person-said)")
    # Every other row is as it was, every column where it was.
    assert list(row)[:len(HEAD)] == HEAD
    assert _by(path, "Oakmere Foods", "Supply Chain Analyst")["status"] == "drafted"


def test_each_way_of_naming_a_row(tmp_path):
    path = _tracker(tmp_path)
    confirm.run("applied", ["Kestrel::claims"], path=path, today=TODAY, source="chat")
    assert _by(path, "Kestrel Mutual", "Claims Forecasting Analyst")["confirmed_by"] == "chat"
    confirm.run("applied", ["oakmere_foods"], path=path, today=TODAY, source="page")
    assert _by(path, "Oakmere Foods", "Supply Chain Analyst")["confirmed_by"] == "page"
    assert _by(path, "Oakmere Foods", "Supply Chain Analyst")["applied_on"] == "2026-10-25"
    # The employer alone, now that one draft is left there.
    confirm.run("skip", ["Kestrel Mutual"], path=path, today=TODAY)
    row = _by(path, "Kestrel Mutual", "Pricing Analyst")
    assert (row["status"], row["applied_on"]) == ("withdrawn", "")
    assert throttle.applied_on(row) == ""


def test_a_name_that_could_be_two_rows_changes_nothing_and_lists_them(tmp_path):
    path = _tracker(tmp_path)
    before = open(path, encoding="utf-8").read()
    with pytest.raises(confirm.Refused, match=r"could be any of 2 applications; name one: "
                       r"Kestrel Mutual \| Pricing Analyst \(Kestrel\); Kestrel Mutual \| "
                       r"Claims Forecasting Analyst \(Kestrel_Claims\)"):
        confirm.run("applied", ["Acme Analytics", "Kestrel"], path=path, today=TODAY)
    # All or nothing: Acme, which was clear, was not written either.
    assert open(path, encoding="utf-8").read() == before
    with pytest.raises(confirm.Refused, match="matches no application"):
        confirm.run("applied", ["Fernhill"], path=path, today=TODAY)
    with pytest.raises(confirm.Refused, match="Brindle Hart \\| Logistics Analyst is applied"):
        confirm.run("skip", ["Brindle Hart"], path=path, today=TODAY)


def test_all_from_a_round_except_some_covers_exactly_those(tmp_path, capsys):
    path = _tracker(tmp_path)
    assert confirm.main(["applied", "all", "from", "round", "r3", "except", "Kestrel::claims",
                         "--tracker", path, "--today", "2026-10-25"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "confirm: 2 applications changed:",
        "  Acme Analytics | Senior Data Analyst: drafted -> applied, applied on 2026-10-25",
        "  Kestrel Mutual | Pricing Analyst: drafted -> applied, applied on 2026-10-25"]
    assert _by(path, "Kestrel Mutual", "Claims Forecasting Analyst")["status"] == "drafted"
    assert _by(path, "Oakmere Foods", "Supply Chain Analyst")["status"] == "drafted"
    # An exception that is not in the round is a mistake, said before anything is written.
    assert confirm.main(["applied", "all", "from", "round", "4", "except", "Acme",
                         "--tracker", path]) == 1
    assert "is none of round 4's: Oakmere Foods | Supply Chain Analyst" in capsys.readouterr().out


def test_not_applied_and_closed(tmp_path):
    path = _tracker(tmp_path)
    confirm.run("applied", ["Oakmere"], path=path, today=TODAY)
    confirm.run("not-applied", ["Oakmere"], path=path, today=TODAY, source="chat")
    row = _by(path, "Oakmere Foods", "Supply Chain Analyst")
    assert (row["status"], row["applied_on"], row["confirmed_by"]) == ("drafted", "", "chat")
    confirm.run("closed", ["Oakmere"], path=path, today=TODAY)
    row = _by(path, "Oakmere Foods", "Supply Chain Analyst")
    assert row["status"] == "withdrawn" and "the posting closed first" in row["notes"]


def test_a_close_on_silence_is_the_searchs_and_applied_undoes_it(tmp_path, capsys):
    path = _tracker(tmp_path, [{"date": "2026-07-01", "company": "Fernhill Freight",
                                "role": "Pricing Analyst", "status": "applied"}])
    gone = followups.close_quiet(path, TODAY, holds={})
    assert [it["company"] for it in gone] == ["Fernhill Freight"]
    row = _read(path)[0]
    assert (row["status"], row["confirmed_by"], row["applied_on"], row["date"]) == (
        "no_response", "the search", "2026-07-01", "2026-07-01")
    done = confirm.run("applied", ["Fernhill::pricing"], path=path, today=TODAY)
    assert done[0][1] == "no_response -> applied, kept open (applied on 2026-07-01)"
    row = _read(path)[0]
    assert (row["status"], row["applied_on"], row["confirmed_by"]) == (
        "applied", "2026-07-01", "person-said")


def test_close_quiet_says_it_is_closing_and_how_to_keep_one_open(tmp_path, monkeypatch, capsys):
    path = _tracker(tmp_path, [{"date": "2026-07-01", "company": "Fernhill Freight",
                                "role": "Pricing Analyst", "status": "applied"}])
    monkeypatch.setattr(followups, "TRACKER", path)
    real = followups.close_quiet
    monkeypatch.setattr(followups, "close_quiet",
                        lambda **k: real(path, k.get("today"), k.get("write", True), holds={}))
    monkeypatch.setattr(sys, "argv", ["followups.py", "--close-quiet", "--today", "2026-10-25"])
    assert followups.main() == 0
    out = capsys.readouterr().out
    assert "closing 1 as no reply: Fernhill Freight (Pricing Analyst, applied 2026-07-01)" in out
    assert 'keep open: python3 tools/confirm.py applied "Fernhill Freight::Pricing Analyst"' in out


def test_readers_take_the_day_it_went_and_old_rows_still_read(tmp_path):
    new = {"date": "2026-08-01", "company": "Acme Analytics", "role": "Data Analyst",
           "status": "applied", "applied_on": "2026-10-20", "confirmed_by": "chat"}
    old = {"date": "2026-10-20", "company": "Acme Analytics", "role": "Data Analyst",
           "status": "applied"}
    assert throttle.applied_on(new) == throttle.applied_on(old) == "2026-10-20"
    assert throttle.applied_on({"date": "2026-08-01", "status": "drafted"}) == ""
    # The nudge clock and the results read the day it went, not the day it was drafted.
    for row in (new, old):
        [it] = followups.review([dict(row)], TODAY, warm={}, holds={})
        assert it["date"] == "2026-10-20" and it["age"] == 5
    assert what_works._waiting([dict(new)], TODAY) == 1
    assert throttle._row_age_days(new, TODAY) == 5


def test_two_chats_on_one_row_merge_now_that_the_date_holds(tmp_path):
    text = open(_tracker(tmp_path), encoding="utf-8").read()
    (tmp_path / "ours").mkdir()
    ours_path = _tracker(tmp_path / "ours")
    confirm.run("applied", ["AcmeAnalytics"], on="2026-10-22", path=ours_path, today=TODAY,
                now=NOW)
    ours = open(ours_path, encoding="utf-8").read()
    # The other chat added a note to the same row, the way /outcome appends one.
    theirs = text.replace("r3. Scores: fit 78.", "r3. Scores: fit 78. | 2026-10-24: recruiter named")
    merged, problems = merge_state.merge(text, ours, theirs, "job_search_tracker.csv")
    assert problems == []
    rows = list(csv.DictReader(merged.splitlines()))
    acme = next(r for r in rows if r["company"] == "Acme Analytics")
    assert (acme["status"], acme["applied_on"], acme["date"]) == ("applied", "2026-10-22",
                                                                 "2026-10-20")
    assert "recruiter named" in acme["notes"] and "confirmed (person-said)" in acme["notes"]
    assert len(rows) == len(ROWS)


def test_check_finds_what_does_not_add_up(tmp_path, capsys):
    rows = [dict(r) for r in ROWS]
    rows[0]["notes"] += " | 2026-10-23: told me they applied via the portal"
    rows.append({"date": "2026-10-15", "company": "Larkspur Retail", "role": "Analyst",
                 "status": "applied", "notes": ""})
    path = _tracker(tmp_path, rows)
    ticks = tmp_path / "ticks.json"
    ticks.write_text('{"ticks": [{"row": "Oakmere", "status": "applied", "at": "2026-10-24 18:02"}]}',
                     encoding="utf-8")
    assert confirm.main(["check", "--tracker", path, "--ticks", str(ticks),
                         "--today", "2026-10-25"]) == 1
    out = capsys.readouterr().out
    assert "applied, nobody confirmed:\n  Larkspur Retail | Analyst (applied 2026-10-15)" in out
    assert "and 1 older than 30 days" in out                        # Brindle Hart, 2026-09-01
    assert ("notes say sent, tracker says drafted:\n  Acme Analytics | Senior Data Analyst: "
            "2026-10-23: told me they applied via the portal") in out
    assert ("ticked applied, tracker says drafted:\n  Oakmere Foods | Supply Chain Analyst "
            "(ticked 2026-10-24 18:02)") in out
    # Once said, there is nothing left to ask about.
    confirm.run("applied", ["AcmeAnalytics", "Oakmere"], path=path, today=TODAY)
    assert confirm.main(["check", "--tracker", path, "--today", "2026-10-25"]) == 1
    assert "Acme Analytics" not in capsys.readouterr().out
    assert confirm.main([]) == 2


def test_an_application_made_outside_the_app_is_added_as_said(tmp_path, capsys):
    path = _tracker(tmp_path)
    assert confirm.main(["applied", "--new", "--company", "Fernhill Freight", "--role",
                         "Pricing Analyst", "--url", "https://jobs.example/9", "--on",
                         "2026-10-18", "--source", "chat", "--tracker", path,
                         "--today", "2026-10-25"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "confirm: 1 application added:", "  Fernhill Freight | Pricing Analyst: applied on 2026-10-18"]
    row = _by(path, "Fernhill Freight", "Pricing Analyst")
    assert (row["date"], row["status"], row["applied_on"], row["confirmed_by"], row["source"]) == (
        "2026-10-25", "applied", "2026-10-18", "chat", "https://jobs.example/9")
    # A role the tracker already holds open is confirmed, never added twice.
    assert confirm.main(["applied", "--new", "--company", "Oakmere Foods", "--role",
                         "Supply Chain Analyst", "--tracker", path]) == 1
    assert 'confirm that row: confirm.py applied "Oakmere Foods::Supply Chain Analyst"' in (
        capsys.readouterr().out)
