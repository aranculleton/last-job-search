"""A connection request nobody accepted, past its withdraw day, says to withdraw it.

Issue 261: after state.REQUEST_WITHDRAW_DAYS an unaccepted request stops holding its
employer (reading.waiting_until), which is right, but nothing told the person to withdraw it.
The person's card in Contacts still said "Your connection request has not been accepted yet"
(surface.held, whatever its age), the one card To do had for withdrawing was never drawn
(templates/app/app.js, since 2026-10-29), and the date beside the request was the follow-up
day the app had written for after they accept, so two requests sent the same day showed two
days. Now, from its withdraw day, the request is one plain line wherever it is shown:
"Withdraw your request to <first name>: it has waited <n> weeks", dated by that day.

Built on the real path: the example person's state with these people added, and the page
model `app.py model` makes from it. Every person and employer here is invented.
"""
from __future__ import annotations

import datetime
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

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW              # 2026-10-25T18:00:00Z
TODAY = datetime.date(2026, 10, 25)

# (id, name, employer, the day the request went, the follow-up day written on the row)
PEOPLE = [
    # Four weeks: one to withdraw. Its row carries the app's follow-up day for after they
    # accept, under the rule as it stood when it went (six working days).
    ("larchway_pym", "Cato Pym", "Larchway Credit", "2026-09-27", "2026-10-05"),
    # Sent the same day, its row written under a later rule (fourteen days): the same
    # withdraw day all the same.
    ("larchway_lowe", "Odile Lowe", "Larchway Credit", "2026-09-27", "2026-10-11"),
    # Three and a half weeks: one to withdraw.
    ("quillmere_soto", "Bram Soto", "Quillmere Bank", "2026-10-01", "2026-10-15"),
    # Ten days: still only waiting to be accepted.
    ("fennick_ardent", "Ilsa Ardent", "Fennick Lending", "2026-10-15", "2026-10-29"),
]
NOTE = "Hi {n}, hope you're well. I build demand forecasts in Manchester."
ACTION = ("Once they accept: follow up after 14 days if no reply (one left), then stop. "
          "Withdraw the request if nobody accepts in 21 days")


def _people_rows():
    contacts, threads = [], []
    for cid, name, company, sent, due in PEOPLE:
        contacts.append({
            "contact_id": cid, "name": name, "title": "Data Lead", "company": company,
            "company_key": company.lower(), "location": "Manchester, England, United Kingdom",
            "linkedin_url": "https://www.linkedin.com/in/" + cid.replace("_", "-") + "-example",
            "tier": "2", "route": "cold", "channel": "connection", "status": "awaiting_reply",
            "first_contacted": sent, "next_action": ACTION, "next_action_due": due})
        threads.append({"contact_id": cid, "date": sent, "direction": "out",
                        "channel": "connection", "scenario": "connection_note",
                        "summary": "First note sent", "full_text": NOTE.format(n=name.split()[0])})
    return contacts, threads


def _save(path, add):
    rows = app_state._csv_rows(path)
    cols = list(rows[0].keys()) if rows else sorted({k for r in add for k in r})
    for r in add:
        for k in r:
            if k not in cols:
                cols.append(k)
    app_state._save_csv(path, rows + add, cols)


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("withdraw"))
    state = app_state.small(os.path.join(root, "state"))
    profile = app_state.profile_copy(os.path.join(root, "profile"))
    contacts, threads = _people_rows()
    _save(os.path.join(state, "network_contacts.csv"), contacts)
    _save(os.path.join(state, "network_threads.csv"), threads)
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, APP, "model", "--now", NOW], env=env,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def person(m, cid):
    return next(p for p in m["people"] if p["id"] == cid)


WITHDRAW = {
    "larchway_pym": "Withdraw your request to Cato: it has waited 4 weeks",
    "larchway_lowe": "Withdraw your request to Odile: it has waited 4 weeks",
    "quillmere_soto": "Withdraw your request to Bram: it has waited 3 weeks",
}


@pytest.mark.parametrize("cid", sorted(WITHDRAW))
def test_past_its_day_the_card_says_to_withdraw_it(model, cid):
    p = person(model, cid)
    assert p["status_word"] == "Request pending", p
    assert p["owed"] is None, p
    assert p["next"] == WITHDRAW[cid] and p["hold"] == WITHDRAW[cid], p


def test_before_its_day_it_only_waits_to_be_accepted(model):
    p = person(model, "fennick_ardent")
    assert p["status_word"] == "Request pending", p
    assert p["hold"] == "Your connection request has not been accepted yet", p
    assert "Withdraw" not in str(p["next"]), p


def test_to_do_has_one_line_each_dated_by_the_withdraw_day(model):
    rows = [d for d in model["due"] if d.get("kind") == "withdraw"]
    assert len(rows) == 1, rows
    row = rows[0]
    who = {w["contact"]: w for w in row["who"]}
    assert set(who) == set(WITHDRAW), who
    for cid, line in WITHDRAW.items():
        assert who[cid]["said"] == line, who[cid]
    # Each is due on its own withdraw day, three weeks after it went, whatever follow-up day
    # its row carried: the two sent on 27 September say one day.
    assert who["larchway_pym"]["on"] == who["larchway_lowe"]["on"] == "2026-10-18", who
    assert who["quillmere_soto"]["on"] == "2026-10-22", who
    assert row["due"] == "2026-10-18" and row["overdue_days"] == 7, row
    # Said as what to do, by name, never as a count alone.
    assert row["title"].startswith("Withdraw your requests to "), row["title"]
    assert "Cato" in row["title"], row["title"]
    assert row["done"] == {"action": "requests.withdrawn", "label": "I withdrew them"}, row


def test_one_request_is_its_own_line_on_to_do(tmp_path, monkeypatch):
    """The engine's one row, with a single request: its title is that request's line."""
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import state
    import surface
    contacts, threads = _people_rows()
    c = contacts[2]
    msgs = [t for t in threads if t["contact_id"] == c["contact_id"]]
    held = surface.held(c, msgs, "awaiting_reply", today=TODAY)
    assert held["why"] == "request" and held["said"] == WITHDRAW["quillmere_soto"], held
    assert held["withdraw_on"] == "2026-10-22", held
    # The day before its withdraw day it is only waiting.
    held = surface.held(c, msgs, "awaiting_reply", today=datetime.date(2026, 10, 21))
    assert held["said"] == "Your connection request has not been accepted yet", held
    # The due list dates it by its withdraw day, never the row's follow-up day.
    got = [i for i in state.owed(contacts, threads, TODAY) if i["kind"] == "request_pending"]
    assert {i["contact_id"]: (i["due"], i["next_action_due"]) for i in got} == {
        "larchway_pym": ("2026-10-18", ""), "larchway_lowe": ("2026-10-18", ""),
        "quillmere_soto": ("2026-10-22", "")}, got


def test_the_page_draws_to_dos_withdraw_card():
    """The card was never drawn: To do's builder skipped it (2026-10-29). It is drawn again,
    from the engine's own title and lines."""
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    start = js.index("function todoItems(")
    body = js[start:js.index("\n  }\n", start)]
    assert "withdrawTodo()" in body, "To do's builder never adds the withdraw card"
    card = js[js.index("function withdrawTodo("):]
    card = card[:card.index("\n  }\n")]
    assert "one.title" in card and ".said" in card, "the card says the engine's own lines"
