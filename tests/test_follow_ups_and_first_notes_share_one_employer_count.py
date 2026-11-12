"""Follow-ups and first notes share one count of people waiting at an employer.

Issue 262: the limit of people waiting on a reply at one employer (reading.at_employer, the
one count every step reads) let someone go the day their follow-up fell due
(reading.waiting_until), so the employer read as open at the very moment the follow-up list
offered that follow-up. On one day the page offered follow-ups to two people at an employer
and a networking run drafted two new notes there, and four or five people there had an
unanswered message at once: the pile-up the limit exists to stop.

Now someone owed a follow-up, one the lists would offer, holds their place at the employer
until it goes, and a first note there waits behind it, saying which goes first. What does not
change: once the follow-up has gone and the person's limit of unanswered messages is reached,
their place is free (the maintainer, 2026-11-10); a follow-up set aside as too old to chase,
one to someone outside where the person looks, and a request nobody accepted hold nothing.

Every person and employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_state  # noqa: E402

EMP = "Harbourline Insurance"
TODAY = dt.date(2026, 10, 20)


def _row(cid, name, first, **more):
    return dict({"contact_id": cid, "name": name, "company": EMP, "status": "awaiting_reply",
                 "first_contacted": first, "location": "Manchester, England, United Kingdom"},
                **more)


def _note(cid, day, text="Hello"):
    return {"contact_id": cid, "date": day, "direction": "out", "channel": "linkedin",
            "scenario": "first_note", "summary": "message", "full_text": text}


@pytest.fixture
def rule(monkeypatch, tmp_path):
    """The person's rule: a follow-up after 14 days, at most two messages with no reply."""
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import reading
    import schema
    monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", 14)
    monkeypatch.setattr(schema, "MAX_UNANSWERED", 2)
    monkeypatch.setattr(schema, "MAX_NUDGES", 1)
    monkeypatch.setattr(reading, "PER_EMPLOYER", 2)
    monkeypatch.setattr(reading, "EMPLOYER_WAIT_DAYS", None)
    return reading


def test_a_follow_up_owed_holds_its_place_at_the_employer(rule):
    reading = rule
    people = [_row("a", "Ines Harrow", "2026-10-01"), _row("b", "Bram Ostler", "2026-10-02")]
    log = [_note("a", "2026-10-01"), _note("b", "2026-10-02")]
    owed: set = set()
    waiting, _ = reading.at_employer(EMP, people, today=TODAY, threads=log, owed=owed)
    # Both are past their wait with a follow-up due: before, nobody counted, and the
    # employer read as open for two more notes the day both follow-ups were offered.
    assert [c["contact_id"] for c in waiting] == ["a", "b"]
    assert owed == {"a", "b"}
    line = reading.employer_full_line(EMP, people, today=TODAY, threads=log)
    assert line == (f"{EMP} has 2 owed a follow-up (Ines Harrow, Bram Ostler), against 2 a "
                    "company: send those follow-ups first"), line


def test_the_place_frees_once_the_follow_up_has_gone_and_the_limit_is_reached(rule):
    reading = rule
    people = [_row("a", "Ines Harrow", "2026-10-01"), _row("b", "Bram Ostler", "2026-10-02")]
    log = [_note("a", "2026-10-01"), _note("b", "2026-10-02"),
           _note("a", "2026-10-20", "Following up")]
    owed: set = set()
    waiting, _ = reading.at_employer(EMP, people, today=dt.date(2026, 10, 21), threads=log,
                                     owed=owed)
    # Ines has had her two messages: her thread is at its limit and holds nothing (the
    # maintainer, 2026-11-10). Bram's follow-up is still owed.
    assert [c["contact_id"] for c in waiting] == ["b"] and owed == {"b"}
    assert reading.employer_full_line(EMP, people, today=dt.date(2026, 10, 21),
                                      threads=log) == ""


def test_a_draft_counts_beside_the_follow_ups_and_is_told_to_wait(rule):
    reading = rule
    people = [_row("a", "Ines Harrow", "2026-10-01"),
              _row("c", "Tove Reyes", "", status="not_contacted")]
    log = [_note("a", "2026-10-01")]
    # One follow-up owed and one note already drafted there: the employer's two.
    line = reading.employer_full_line(EMP, people, also=[people[1]], today=TODAY, threads=log)
    assert line == (f"{EMP} has 1 owed a follow-up (Ines Harrow) and 1 with a note waiting to "
                    "send, against 2 a company: send that follow-up first"), line


@pytest.mark.parametrize("why, row, log", [
    # Set aside: owed for months with nothing done, so no list offers it.
    ("too old to chase", _row("o", "Celia Marsh", "2026-06-01"), [_note("o", "2026-06-01")]),
    # Somewhere outside where the person looks: no follow-up is ever offered to them.
    ("outside where they look",
     _row("p", "Celia Marsh", "2026-10-01", location="Toronto, Ontario, Canada"),
     [_note("p", "2026-10-01")]),
    # A connection request nobody accepted: nothing can be sent until they do.
    ("a request nobody accepted", _row("q", "Celia Marsh", "2026-10-01", channel="connection"),
     [dict(_note("q", "2026-10-01"), channel="connection", scenario="connection_note")]),
], ids=["old", "place", "request"])
def test_what_no_list_offers_holds_nothing(rule, why, row, log):
    reading = rule
    waiting, _ = reading.at_employer(EMP, [row], today=TODAY, threads=log)
    assert waiting == [], why


def test_someone_new_there_is_held_with_the_follow_ups_named(rule):
    import surface
    import state
    people = [_row("a", "Ines Harrow", "2026-10-01"), _row("b", "Bram Ostler", "2026-10-02")]
    log = [_note("a", "2026-10-01"), _note("b", "2026-10-02")]
    ctx = {"contacts": people, "today": TODAY, "thread_rows": log,
           "threads": state.by_contact(log)}
    said = surface.employer_full(EMP, ctx, "name:someone")
    assert said.startswith(f"{EMP} has 2 owed a follow-up (Ines Harrow, Bram Ostler)"), said
    assert said.endswith("send those follow-ups first"), said


def test_held_back_for_now_says_the_follow_up_goes_first_or_the_day_it_opens(rule):
    """Your rules, Held back for now (tools/holds.py) reads the one count: an employer a
    follow-up holds is listed, with the follow-up that opens it; one whose places free by
    themselves (requests nobody accepted, on their withdraw day) keeps its day."""
    import holds
    people = [_row("a", "Ines Harrow", "2026-10-01"), _row("b", "Bram Ostler", "2026-10-12")]
    log = [_note("a", "2026-10-01"), _note("b", "2026-10-12")]
    got = holds._employer_waits(TODAY, people, log)
    assert [h["line"] for h in got] == [
        f"{EMP}: 2 people there are waiting on a reply, so it opens again once your "
        "follow-up to Ines has gone"], got
    assert got[0]["until"] == TODAY.isoformat(), got
    # Requests nobody accepted yet: each holds a place for one follow-up wait (14 days), and
    # nothing is owed to them after it, so the first frees its place by itself.
    requests = [_row("q", "Ines Harrow", "2026-10-09", channel="connection"),
                _row("r", "Bram Ostler", "2026-10-12", channel="connection")]
    sent = [dict(_note("q", "2026-10-09"), channel="connection", scenario="connection_note"),
            dict(_note("r", "2026-10-12"), channel="connection", scenario="connection_note")]
    got = holds._employer_waits(TODAY, requests, sent)
    assert [h["line"] for h in got] == [
        f"{EMP}: 2 people there are waiting on a reply, so it opens again Fri 23 Oct"], got


# ------------------------------------------------------------------ the page, on the real path

NOTE = "Hi Tove, hope you're well. I build demand forecasts in Manchester. How is the team set up?\n"


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    """The example person (the app's own follow-up rule: six working days, two people an
    employer) with two people at one employer written to on 5 and 6 October, both owed a
    follow-up on 25 October, and a first note drafted to a third person there."""
    root = str(tmp_path_factory.mktemp("share"))
    st = app_state.small(os.path.join(root, "state"))
    profile = app_state.profile_copy(os.path.join(root, "profile"))
    path = os.path.join(st, "network_contacts.csv")
    rows = app_state._csv_rows(path)
    cols = list(rows[0].keys())
    for cid, name, first, status in (("harbourline_harrow", "Ines Harrow", "2026-10-05", "awaiting_reply"),
                                     ("harbourline_ostler", "Bram Ostler", "2026-10-06", "awaiting_reply"),
                                     ("harbourline_reyes", "Tove Reyes", "", "not_contacted")):
        rows.append(dict.fromkeys(cols, "") | {
            "contact_id": cid, "name": name, "title": "Data Lead", "company": EMP,
            "company_key": EMP.lower(), "location": "Manchester, England, United Kingdom",
            "linkedin_url": "https://www.linkedin.com/in/" + cid.replace("_", "-") + "-example",
            "tier": "2", "route": "cold", "channel": "linkedin", "status": status,
            "first_contacted": first})
    app_state._save_csv(path, rows, cols)
    tpath = os.path.join(st, "network_threads.csv")
    trows = app_state._csv_rows(tpath)
    tcols = list(trows[0].keys())
    for cid, day in (("harbourline_harrow", "2026-10-05"), ("harbourline_ostler", "2026-10-06")):
        trows.append(dict.fromkeys(tcols, "") | _note(cid, day, "Hi, hope you're well."))
    app_state._save_csv(tpath, trows, tcols)
    app_state._write(os.path.join(st, "documents", "network", "harbourline_reyes", "draft.md"), NOTE)
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=st, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now",
                        app_state.NOW], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_the_page_offers_the_follow_ups_and_holds_the_new_note_behind_them(model):
    titles = [d["title"] for d in model["due"]]
    assert f"Follow up with Ines at {EMP}" in titles and f"Follow up with Bram at {EMP}" in titles, titles
    note = next(m for m in model["messages"] if m.get("contact") == "harbourline_reyes")
    # Which goes first, said on the note, and the note is not offered as ready to send.
    assert note["hold"] == f"On hold: follow up with Ines and Bram at {EMP} first", note["hold"]
    assert note["hold_why"] == "employer_full", note
    assert "harbourline_reyes" not in json.dumps(model.get("to_send") or {}), model.get("to_send")
