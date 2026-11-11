"""Every networking decision counts the person's own day, never the computer's.

The person's day is `person.today()` (their home zone). The audit of 2026-11-10 (NW-17) found the
message log's commands, the follow-up and per-employer waits, the throttle and `dates.days_since`
counting the computer's date: a chat on a laptop in another zone, or a cloud chat at the turn of
the day, wrote a different date from another chat's and worked out a different due day. One day
source now: what is checked here is that no networking decision path asks the computer for its
date, and that a default follows the person's day. The reading module's own sweep is
tests/test_every_hold_says_when_it_ends.py; its sign-in records keep the computer's day on
purpose (the browser on that computer is what was signed in).
"""
from __future__ import annotations

import ast
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import person  # noqa: E402

FILES = ("tools/network/state.py", "tools/throttle.py", "tools/dates.py",
         "tools/network/export.py", "tools/network/reply.py", "tools/network/compose.py",
         "tools/open_actions.py", "tools/followup_drafts.py")


def _machine_days(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "today" and not node.args
                and ast.unparse(node.func.value) in ("datetime.date", "dt.date", "date")):
            found.append(f"{path}:{node.lineno}")
    return found


def test_no_networking_decision_asks_the_computer_for_its_date():
    found = [x for p in FILES for x in _machine_days(p)]
    assert found == [], found


def test_a_default_day_is_the_persons(monkeypatch):
    import dates
    import state
    theirs = datetime.date(2031, 3, 9)              # a day the computer's clock is not on
    monkeypatch.setattr(person, "today", lambda now=None: theirs)
    assert dates.days_since("2031-03-02") == 7
    book = []
    row, how = state.add_contact(book, "Ivo Marsh", "Quayside Foods")
    assert how == "added" and row["notes"] == "added 2031-03-09", row


def test_the_message_logs_commands_date_by_the_persons_day(monkeypatch, tmp_path, capsys):
    """The key paths with the person's day one off the computer's: a note added by hand, a
    follow-up's due day from the command's own default, and the per-employer wait."""
    import state
    machine = datetime.date.today()
    theirs = machine - datetime.timedelta(days=1)
    monkeypatch.setattr(person, "today", lambda now=None: theirs)
    book = [{"contact_id": "quayside_foods_ivo", "name": "Ivo Marsh", "company": "Quayside Foods",
             "status": "awaiting_reply", "next_action": "", "next_action_due": ""}]
    state.set_contact(book, [], "quayside_foods_ivo", note="met at the depot open day")
    assert book[0]["notes"].startswith(theirs.isoformat() + ":"), book[0]["notes"]
    # The command's default day is theirs: an empty book, and the day it says it counted from.
    cp, tp = tmp_path / "c.csv", tmp_path / "t.csv"
    import schema
    for path, cols in ((cp, schema.CONTACT_COLUMNS), (tp, schema.THREAD_COLUMNS)):
        path.write_text(",".join(cols) + "\n", encoding="utf-8")
    ap_days = []
    real = state._need_date

    def seen(value, what):
        ap_days.append(str(value))
        return real(value, what)
    monkeypatch.setattr(state, "_need_date", seen)
    state.main(["--contacts", str(cp), "--threads", str(tp)])
    capsys.readouterr()
    assert theirs.isoformat() in ap_days and machine.isoformat() not in ap_days, ap_days
