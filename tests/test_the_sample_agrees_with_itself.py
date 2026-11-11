"""The page's sample says one thing in every place a stranger walks, and the engine never asks
whether an application went once it is recorded as sent.

The screen review of 2026-11-11 (row 40): the sample (tests/fixtures/app_model_sample.json)
asked "Did you apply to Fernhill Freight?" while Applied listed that application, sent Sun 20
Sept; Progress said "24 applied" over a list of 14; and the interview prep said "you are in
Leeds" while every note in Contacts said Manchester. The engine (tools/app_model.py) asks "Did
you apply?" of a draft whose notes say it went: with the same role at the same employer already
recorded as sent on or after the draft's day, that application is in Applied, and the question
is never asked. Every person and employer is invented (tests/app_state.py, the sample).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
from test_the_page_shows_the_repo_and_nothing_private import model  # noqa: E402

SAMPLE = os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json")


def _sample():
    with open(SAMPLE, encoding="utf-8") as fh:
        return json.load(fh)


def _sent(m):
    return [a for a in m["done"]["applications"] if a.get("applied_on")]


def test_no_did_you_apply_for_an_employer_applied_shows_as_sent():
    m = _sample()
    sent = {a["company"] for a in _sent(m)} | {a["company"] for a in m["applications"] if a.get("applied_on")}
    asks = [q for q in m["needs_you"] if q["title"].startswith("Did you apply to ")]
    assert asks, "the sample still asks one, so the card is seen"
    for q in asks:
        company = q["title"][len("Did you apply to "):].rstrip("?")
        assert company == q["about"]["company"] and company not in sent, (q["title"], sorted(sent))


def test_progress_counts_the_applications_it_lists():
    m = _sample()
    d = m["done"]
    sent = _sent(m)
    assert d["counts"]["applied"] == len(sent) == d["funnel"][0]["n"], (d["counts"], len(sent))
    # Each week counts the applications sent in it, by their own days.
    for w in d["weeks"]:
        y, n = map(int, w["week"].split("-W"))
        mon = dt.date.fromisocalendar(y, n, 1)
        mine = [a for a in sent if mon <= dt.date.fromisoformat(a["applied_on"]) < mon + dt.timedelta(days=7)]
        assert w["applied"] == len(mine), (w, [a["company"] for a in mine])


def test_the_prep_says_the_place_contacts_say():
    m = _sample()
    where = {j["place"].split(",")[0] for j in m["you"]["jobs"][:1]}
    notes = " ".join(t["text"] for p in m["people"] for t in p.get("thread") or [] if t.get("from", "you") == "you")
    said = re.findall(r"you are in (\w+)", json.dumps(m["interviews"]))
    assert said and set(said) == where, (said, where)
    assert all(w in notes for w in where), where


def _with_row(state, row):
    path = os.path.join(state, "job_search_tracker.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.append(dict({k: "" for k in app_state.TRACKER_COLUMNS}, **row))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=app_state.TRACKER_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def test_the_engine_never_asks_did_you_apply_of_an_application_recorded_as_sent(tmp_path):
    state = app_state.small(str(tmp_path / "state"))
    asked = lambda m: [q for q in m["needs_you"] if q["title"] == "Did you apply to Dovecote Freight?"]  # noqa: E731
    assert asked(model(state)), "a draft whose notes say it went is asked about"
    # The same role, recorded as sent after the draft was made (a second row for it).
    _with_row(state, {"date": "2026-10-21", "company": "Dovecote Freight", "role": "Inventory Analyst",
                      "status": "applied", "applied_on": "2026-10-21", "channel": "company site",
                      "notes": "2026-10-21: applied via the portal"})
    m = model(state)
    assert any(a["company"] == "Dovecote Freight" and a["role"] == "Inventory Analyst"
               for a in m["done"]["applications"]), m["done"]["applications"]
    assert not asked(m), [q["title"] for q in m["needs_you"]]


def test_an_earlier_application_to_the_same_role_still_lets_it_ask(tmp_path):
    # Sent in the spring, drafted again in October: this draft's own sending is the question.
    state = app_state.small(str(tmp_path / "state"))
    _with_row(state, {"date": "2026-04-02", "company": "Dovecote Freight", "role": "Inventory Analyst",
                      "status": "rejected", "applied_on": "2026-04-02", "channel": "company site"})
    m = model(state)
    assert [q for q in m["needs_you"] if q["title"] == "Did you apply to Dovecote Freight?"], \
        [q["title"] for q in m["needs_you"]]
