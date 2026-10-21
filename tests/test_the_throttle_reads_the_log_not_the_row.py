"""Warm or cold is decided by the messages, in both places that decide it.

The networking layer's documented premise, in CLAUDE.md: "Status is derived
from the messages, never stored independently, so it cannot drift from the
evidence." That was true of `state.py` and false of `throttle.py`, which read
the stored column straight off `network_contacts.csv`. Two implementations of
one rule, which is the failure this repo names more than any other.

The case this was written for was misread, and the correction matters as much
as the rule. A contact stored `connected_no_reply` had one inbound row in the
log: "Accepted the connection request. No message." (scenario
`accepted_no_reply`). The derivation read that row's direction and called it a
reply, so a test pinned that employer as a warm route. It never was: nobody
there had written a word, and the stored row was right.
`test_accepting_a_request_is_not_a_reply` in a person's own suite has the
whole account.

The rule stands. Reading the stored column instead of the log is still two
implementations of one rule, and a reply the row has not caught up with is
still the unused-referral failure described in `_contacts_by_employer`'s own
docstring: a live route invisible to the thing deciding whether the
application is cold.

The throttle now derives, the same way `prefilter.py` imports
`throttle.ruled_out()` rather than reimplementing it. It fails open to the
stored column, because a missing message log is a reason to fall back to the
row, never a reason to stop a scrape.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import throttle  # noqa: E402


def _csv(rows, fields):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    fh.close()
    return fh.name


class AReplyMakesTheRouteWarmEvenIfNobodyEditedTheRow(unittest.TestCase):
    FIELDS = ["contact_id", "name", "company", "status", "title", "next_action"]
    TFIELDS = ["contact_id", "direction", "date", "channel", "body"]

    def setUp(self):
        self.contacts = _csv([{
            "contact_id": "c1", "name": "Robin Vale", "company": "Acme",
            "status": "connected_no_reply", "title": "Director", "next_action": "",
        }], self.FIELDS)
        self.addCleanup(lambda: Path(self.contacts).unlink(missing_ok=True))

    def _threads(self, rows):
        path = _csv(rows, self.TFIELDS)
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return path

    def test_the_stored_row_alone_reads_as_not_yet_warm(self):
        """Establishes the starting state the bug depended on."""
        self.assertIn("connected_no_reply", throttle.SENT_NO_REPLY)
        self.assertNotIn("connected_no_reply", throttle.RESPONDED)

    def test_an_inbound_message_moves_it_to_warm(self):
        threads = self._threads([
            {"contact_id": "c1", "direction": "out", "date": "2026-08-01",
             "channel": "linkedin", "body": "hello"},
            {"contact_id": "c1", "direction": "in", "date": "2026-08-05",
             "channel": "linkedin", "body": "happy to chat"},
        ])
        rows = list(csv.DictReader(open(self.contacts, newline="", encoding="utf-8")))
        derived = throttle._derived_statuses(rows, threads)
        self.assertEqual("replied_needs_response", derived.get("c1"))
        self.assertIn(throttle._status_of(rows[0], derived), throttle.RESPONDED)

    def test_with_no_reply_it_stays_where_it_was(self):
        threads = self._threads([
            {"contact_id": "c1", "direction": "out", "date": "2026-08-01",
             "channel": "linkedin", "body": "hello"},
        ])
        rows = list(csv.DictReader(open(self.contacts, newline="", encoding="utf-8")))
        derived = throttle._derived_statuses(rows, threads)
        self.assertNotIn(throttle._status_of(rows[0], derived), throttle.RESPONDED)


class ItFailsOpenToTheStoredColumn(unittest.TestCase):
    """A scrape must never stop because the message log is unreadable."""

    def test_a_missing_log_falls_back(self):
        rows = [{"contact_id": "c1", "status": "awaiting_reply"}]
        self.assertEqual({}, throttle._derived_statuses(rows, "/nonexistent/x.csv"))
        self.assertEqual("awaiting_reply", throttle._status_of(rows[0], {}))

    def test_a_row_with_no_id_falls_back(self):
        self.assertEqual("in_conversation",
                         throttle._status_of({"status": "in_conversation"}, {}))

    def test_a_corrupt_log_falls_back_rather_than_raising(self):
        path = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                           encoding="utf-8")
        path.write("\x00not,a,csv\n\x00")
        path.close()
        self.addCleanup(lambda: Path(path.name).unlink(missing_ok=True))
        try:
            throttle._derived_statuses([{"contact_id": "c1"}], path.name)
        except Exception as e:                     # noqa: BLE001 - the point
            self.fail(f"a corrupt log must not raise: {e!r}")


class TheRuleHasOneImplementation(unittest.TestCase):
    def test_the_throttle_does_not_reimplement_the_derivation(self):
        # Two implementations of one rule is the failure this repo names more than any
        # other. Whatever state.effective_status says a contact's status is, the
        # throttle says too: stand in a derivation of its own and read it back.
        sys.path.insert(0, str(ROOT / "tools" / "network"))
        import state
        from unittest import mock
        log = _csv([{"contact_id": "c1", "direction": "out", "date": "2026-08-01",
                     "channel": "linkedin", "body": "hello"}],
                   ["contact_id", "direction", "date", "channel", "body"])
        self.addCleanup(lambda: Path(log).unlink(missing_ok=True))
        rows = [{"contact_id": "c1", "status": "awaiting_reply"}]
        with mock.patch.object(state, "effective_status", lambda row, msgs: "call_booked"):
            self.assertEqual({"c1": "call_booked"}, throttle._derived_statuses(rows, log))


if __name__ == "__main__":
    unittest.main()


def _run_main(tmp, argv, monkeypatch):
    import json
    src, out = tmp / "ranked.json", tmp / "short.json"
    src.write_text(json.dumps([{"title": "Data Analyst", "company": "Kestrel Mutual",
                                "url": "https://boards.example.com/k/1", "priority": 80,
                                "fit": 80, "location": "Manchester"}]))
    monkeypatch.setattr(sys, "argv", ["throttle.py", str(src), "--out", str(out),
                                      "--seen", str(tmp / "seen.json"), "--no-write", *argv])
    throttle.main()
    return json.loads(out.read_text())


def test_a_round_reads_each_state_file_once(tmp_path, monkeypatch):
    # The tracker was read eight times in one run, the contact book and the message log
    # three times each, so the rules of one round could judge different copies of a file
    # another chat was saving.
    calls = {"tracker": 0, "log": 0}
    real_t, real_d = throttle._tracker_rows, throttle._derived_statuses
    monkeypatch.setattr(throttle, "_tracker_rows",
                        lambda *a, **k: calls.__setitem__("tracker", calls["tracker"] + 1)
                        or real_t(*a, **k))
    monkeypatch.setattr(throttle, "_derived_statuses",
                        lambda *a, **k: calls.__setitem__("log", calls["log"] + 1)
                        or real_d(*a, **k))
    _run_main(tmp_path, [], monkeypatch)
    assert calls == {"tracker": 1, "log": 1}


def test_a_replayed_round_judges_silence_on_its_own_day(tmp_path, monkeypatch):
    # The application's silence was measured from the computer's date, not the round's
    # --today, so a replay of an older round released employers it had held.
    tracker = tmp_path / "tracker.csv"
    tracker.write_text("date,company,role,status,fit_rating\n"
                       "2026-09-01,Kestrel Mutual,Supply Chain Analyst,applied,90\n",
                       encoding="utf-8")
    kept = _run_main(tmp_path, ["--tracker", str(tracker), "--today", "2026-09-20"], monkeypatch)
    assert kept == []
    kept = _run_main(tmp_path, ["--tracker", str(tracker), "--today", "2026-10-30"], monkeypatch)
    assert [r["company"] for r in kept] == ["Kestrel Mutual"]


# ---- the round's own state files reach every stage that reads them ---------------
# A round pointed at a copy of the state (--tracker, --contacts) still had fit read the
# repo's tracker and contact book, the prefilter's referral holds read the repo's
# contact book, and the throttle derive the copy's statuses from the repo's message log.

_BOOK = ("contact_id,name,title,company,status,next_action\n"
         "kestrel_vale,Robin Vale,Analytics Lead,Kestrel Mutual,{status},\n")
_LOG = ("contact_id,date,direction,channel,scenario,summary,full_text\n"
        "kestrel_vale,2026-09-01,outbound,linkedin,first_note,first note,Hello Robin.\n"
        "kestrel_vale,2026-09-03,inbound,linkedin,replied,replied,Happy to talk.\n")


def test_the_throttle_reads_the_log_beside_the_contact_book_it_was_given(tmp_path, monkeypatch):
    state = tmp_path / "copy"
    state.mkdir()
    (state / "network_contacts.csv").write_text(_BOOK.format(status="awaiting_reply"))
    (state / "network_threads.csv").write_text(_LOG)
    kept = _run_main(tmp_path, ["--contacts", str(state / "network_contacts.csv")], monkeypatch)
    assert "DO NOT APPLY COLD" in kept[0].get("warm_route_note", ""), kept


def test_fit_reads_the_tracker_and_contact_book_it_was_given(tmp_path, monkeypatch):
    import json
    import fit
    tracker = tmp_path / "tracker.csv"
    tracker.write_text("date,company,role,status,fit_rating\n"
                       "2026-08-01,Kestrel Mutual,Supply Chain Analyst,interview,80\n")
    (tmp_path / "network_contacts.csv").write_text(_BOOK.format(status="awaiting_reply"))
    (tmp_path / "network_threads.csv").write_text(_LOG)
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps([{"title": "Data Analyst", "company": "Kestrel Mutual",
                                "desc": "SQL and Python."}]))
    monkeypatch.setattr(sys, "argv", ["fit.py", str(src), "--out", str(out),
                                      "--tracker", str(tracker),
                                      "--contacts", str(tmp_path / "network_contacts.csv")])
    fit.main()
    (row,) = json.loads(out.read_text())
    assert any("interviewed you before" in w for w in row["fit_why"]), row["fit_why"]
    assert row.get("warm_route") and row["warm_route"][0]["name"] == "Robin Vale"


def test_the_prefilter_holds_on_the_contact_book_it_was_given(tmp_path, monkeypatch):
    import json
    import prefilter
    book = tmp_path / "network_contacts.csv"
    book.write_text(_BOOK.format(status="referral_in_progress"))
    src, kept, dropped = tmp_path / "in.json", tmp_path / "kept.json", tmp_path / "dropped.json"
    src.write_text(json.dumps([{"title": "Data Analyst", "company": "Kestrel Mutual",
                                "location": "Manchester, England, United Kingdom",
                                "url": "https://boards.example.com/k/2", "date": "2026-10-19"}]))
    monkeypatch.setattr(sys, "argv", ["prefilter.py", str(src), "--out", str(kept),
                                      "--dropped", str(dropped), "--today", "2026-10-20",
                                      "--seen", str(tmp_path / "seen.json"),
                                      "--contacts", str(book)])
    prefilter.main()
    assert json.loads(kept.read_text()) == []
    assert "referral in progress" in json.loads(dropped.read_text())[0]["prefilter_reason"]
