"""Someone new, an acceptance and a reply pasted twice, each recorded by command, once.

Walked through as a person and a chat would on 2026-11-03, on the example person's search
(tests/app_state.py). There was no command to add someone who wrote first (a recruiter, a
name passed on), so a chat wrote the contact book by hand, which the rules forbid, and
`received` refused their message until it had. Nor one to record that someone accepted a
request: the networking skill said to log it by hand, and the row kept "Once they accept ...
withdraw the request" with the old date. Their words pasted again on another day were logged
twice, and one person in two conversations of a LinkedIn download was two people.

`Book` and `lived_in` are shared with tests/test_contacts_are_recorded_and_shown_as_they_happened.py.
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

APP = os.path.join(ROOT, "tools", "app.py")
STATE = os.path.join(ROOT, "tools", "network", "state.py")
EXPORT = os.path.join(ROOT, "tools", "network", "export.py")
NOW = app_state.NOW
TODAY = app_state.TODAY
PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1440, "height": 900}


class Book:
    """The example search in a folder of its own, worked on by the app's own commands."""

    def __init__(self, root):
        self.state = app_state.small(os.path.join(root, "state"))
        self.profile = app_state.profile_copy(os.path.join(root, "profile"))
        self.root = root
        self.n = 0
        self.env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                        LJS_COPY="private")
        self.env.pop("LJS_TODAY", None)

    def run(self, tool, *args, ok=(0,)):
        r = subprocess.run([sys.executable, tool, *args], env=self.env, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout + r.stderr

    def state_py(self, *args, ok=(0,)):
        return self.run(STATE, *args, ok=ok)

    def words(self, text):
        self.n += 1
        path = os.path.join(self.root, f"words{self.n}.txt")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def contact(self, cid):
        return next((r for r in app_state._csv_rows(os.path.join(self.state, "network_contacts.csv"))
                     if r["contact_id"] == cid), None)

    def rows(self, cid):
        return [r for r in app_state._csv_rows(os.path.join(self.state, "network_threads.csv"))
                if r["contact_id"] == cid]

    def model(self):
        return json.loads(self.run(APP, "model", "--now", NOW))


SAM = ("Hi Morgan, I'm recruiting for a supply-chain analyst role with a client in Manchester.\r\n"
       "\r\nAre you open to a chat? You can reach me on sam.tate@example.com.")


def lived_in(book):
    """Sam, a recruiter with no employer, wrote first; Dev accepted, was nudged and stayed
    silent; Rhian accepted a note and has not answered; three first notes from a run wait."""
    s = book.state_py
    s("add", "Sam Tate", "--title", "Recruiter", "--route", "recruiter", "--today", TODAY)
    s("received", "tate", "--text-file", book.words(SAM), "--date", "2026-10-24", "--today", TODAY)
    for name, co in (("Dev Raman", "Copperleaf Pay"), ("Rhian Okafor", "Northwind Analytics")):
        s("add", name, "--company", co, "--title", "Data Lead", "--today", TODAY)
    s("sent", "copperleaf_pay_raman", "--text-file", book.words(
        "Hi Dev, hope you're well. How is the data team at Copperleaf set up?"),
      "--date", "2026-09-25", "--today", "2026-09-25")
    s("accepted", "copperleaf_pay_raman", "--date", "2026-09-26", "--today", "2026-09-26")
    s("nudge", "copperleaf_pay_raman", "--text-file", book.words(
        "Hi Dev, I saw Copperleaf posted a data role in Manchester. Is it in your team?"),
      "--date", "2026-10-06", "--today", "2026-10-06")
    s("sent", "northwind_analytics_okafor", "--text-file", book.words(
        "Hi Rhian, hope you're well. What does the analytics team at Northwind work on?"),
      "--date", "2026-10-01", "--today", "2026-10-01")
    s("accepted", "Rhian Okafor", "--date", "2026-10-02", "--today", "2026-10-02")
    for name, co, note in (
            ("Rosa Lindqvist", "Kestrel Mutual", "Hi Rosa, how is the analytics team at Kestrel set up? I build demand forecasts for food logistics."),
            ("Ivo Haddad", "Quayside Foods", "Hi Ivo, I saw Quayside is growing its planning team. My work is supply-chain analytics in Manchester."),
            ("Bea Novak", "Ellerwick Trust", "Hi Bea, would you have a few minutes in the next couple of weeks? I'm curious how Ellerwick plans its stock.")):
        got = s("add", name, "--company", co, "--today", TODAY)
        cid = got.split(" added as ")[1].split(".")[0]
        book.run(os.path.join(ROOT, "tools", "network", "reading.py"), "draft", cid,
                 book.words(note), "--card-only")


@pytest.fixture
def book(tmp_path):
    return Book(str(tmp_path))


# ------------------------------------------------------------------ the commands

def test_someone_who_wrote_first_is_added_once_and_their_message_logged(book):
    out = book.state_py("add", "Sam Tate", "--title", "Recruiter", "--today", TODAY)
    assert "added as tate" in out
    row = book.contact("tate")
    assert row["status"] == "not_contacted" and row["company"] == "" and row["title"] == "Recruiter"
    # The same name again, with no employer, is asked about, never a second row.
    out = book.state_py("add", "Sam Tate", "--today", TODAY, ok=(1,))
    assert "already in your contact book called Sam Tate: tate" in out
    # Someone already in the book at their employer is that row.
    out = book.state_py("add", "Juno Castellan", "--company", "Larkspur Retail", "--today", TODAY)
    assert "already in your contact book as larkspur_retail_castellan" in out
    # An initial, at the employer written short, may be her: asked, never added.
    out = book.state_py("add", "J. Castellan", "--company", "Larkspur", "--today", TODAY, ok=(1,))
    assert "may be Juno Castellan" in out and "larkspur_retail_castellan" in out
    assert "added as" in book.state_py("add", "J. Castellan", "--company", "Larkspur", "--new",
                                       "--today", TODAY)
    book.state_py("received", "tate", "--text-file", book.words(SAM), "--date", "2026-10-24",
                  "--today", TODAY)
    assert book.contact("tate")["status"] == "replied_needs_response"


def test_an_acceptance_is_recorded_and_the_clock_runs_from_it(book):
    import state
    book.state_py("add", "Rhian Okafor", "--company", "Northwind Analytics", "--today", TODAY)
    book.state_py("sent", "northwind_analytics_okafor", "--text-file", book.words(
        "Hi Rhian, hope you're well. What does the analytics team at Northwind work on?"),
        "--date", "2026-10-01", "--today", "2026-10-01")
    assert book.contact("northwind_analytics_okafor")["next_action"].startswith("Once they accept")
    out = book.state_py("accepted", "Rhian Okafor", "--date", "2026-10-02", "--today", "2026-10-02")
    assert "accepted on 2026-10-02" in out
    row = book.contact("northwind_analytics_okafor")
    assert row["status"] == "connected_no_reply"
    assert "Once they accept" not in row["next_action"] and "Withdraw" not in row["next_action"]
    assert row["next_action_due"] == state.follow_up_on(dt.date(2026, 10, 2)).isoformat()
    took = [r for r in book.rows("northwind_analytics_okafor") if r["direction"] == "in"]
    assert [(r["scenario"], r["full_text"]) for r in took] == [("accepted_no_reply", "")]
    # Once is all: a second acceptance, and one with no request behind it, are refused.
    assert "already logged" in book.state_py("accepted", "northwind_analytics_okafor",
                                             "--today", TODAY, ok=(1,))
    assert "nothing to accept" in book.state_py("accepted", "larkspur_retail_castellan",
                                                "--today", TODAY, ok=(1,))


def test_a_request_with_no_note_accepted_owes_a_first_message_now(book):
    book.state_py("add", "Ivo Haddad", "--company", "Quayside Foods", "--today", TODAY)
    book.state_py("sent", "quayside_foods_haddad", "--no-note", "--date", "2026-10-10",
                  "--today", "2026-10-10")
    book.state_py("accepted", "quayside_foods_haddad", "--date", "2026-10-20", "--today", TODAY)
    row = book.contact("quayside_foods_haddad")
    assert row["next_action"].startswith("Write to them") and row["next_action_due"] == "2026-10-20"


def test_their_reply_pasted_again_on_another_day_is_not_logged_twice(book):
    long = "Hi Morgan, happy to help. Send me your CV and I'll pass it on to the team."
    path = book.words(long)
    before = len(book.rows("larkspur_retail_castellan"))
    book.state_py("received", "larkspur_retail_castellan", "--text-file", path, "--date",
                  "2026-10-20", "--today", TODAY)
    out = book.state_py("received", "larkspur_retail_castellan", "--text-file", path,
                        "--today", TODAY, ok=(1,))
    assert "already logged" in out and "2026-10-20" in out
    assert len(book.rows("larkspur_retail_castellan")) == before + 1
    # A short one may really come twice.
    thanks = book.words("Thanks!")
    book.state_py("received", "larkspur_retail_castellan", "--text-file", thanks, "--date",
                  "2026-10-21", "--today", TODAY)
    book.state_py("received", "larkspur_retail_castellan", "--text-file", thanks, "--date",
                  "2026-10-23", "--today", TODAY)


def test_one_person_in_two_conversations_of_an_export_is_one_line(tmp_path, monkeypatch):
    import datetime
    import export as E
    monkeypatch.setattr(E, "HERE", datetime.timezone.utc)   # the person's day, read in UTC
    me = "https://www.linkedin.com/in/morgan-ellis-example"
    them = "https://www.linkedin.com/in/example-tobias-brightwell"
    (tmp_path / "messages.csv").write_text(
        "CONVERSATION ID,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,DATE,CONTENT\r\n"
        f"c1,Morgan Ellis,{me},Tobias Brightwell,{them},2026-10-21 10:00:00 UTC,Thanks for connecting.\r\n"
        f"c2,Tobias Brightwell,{them},Morgan Ellis,{me},2026-10-22 11:00:00 UTC,Good to meet you.\r\n",
        encoding="utf-8")
    plan = E.plan_history([], [], str(tmp_path), mine=("morgan-ellis-example", E.name_key("Morgan Ellis")))
    assert len(plan["unmatched"]) == 1, plan["unmatched"]
    u = plan["unmatched"][0]
    assert (u["sent"], u["received"], u["last"], u["last_from"]) == (1, 1, "2026-10-22", "them")
