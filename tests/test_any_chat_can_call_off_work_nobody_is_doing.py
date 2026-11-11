"""Any chat can call off work nobody is doing, and never work another chat is doing now.

The audit of 2026-11-10 (PE-6): a cloud chat could withdraw only work for the computer that
nobody had started. Work waiting on the person (a LinkedIn sign-in), and work a chat on the
computer had claimed and then gone quiet on, could only be ended by the person's own Stop.
Each is now called off by any chat with its reason (`app.py done --stopped --summary`), the
question it carried cleared; a claim still moving on stays that chat's. Every person,
employer and computer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)
WHY = "Called off: these profiles were read earlier today."


def _ago(minutes: int) -> str:
    return app_model.stamp(T - dt.timedelta(minutes=minutes))


def _body(got) -> dict:
    with open(got["batches"][0], encoding="utf-8") as fh:
        entries = json.load(fh)
    entry = next(e for e in entries if e["collection"] == "work")
    with open(entry["file_path"], encoding="utf-8") as fh:
        return json.load(fh)


def _off(item, tmp_path, name, **kw):
    return page_db.finish(_db(("w", item)), "w", T, str(tmp_path / name), status="stopped",
                          chat_kind="cloud", chat="session_helper", **kw)


def test_a_question_waiting_on_the_person_is_called_off_with_its_reason(tmp_path):
    asked = _w("network", "Harbourline Bank", to="computer", status="needs_you",
               note="LinkedIn is signed out in Claude's browser.", asked_you_at=_ago(30),
               needs={"question": "LinkedIn is signed out in Claude's browser.",
                      "signin": "linkedin"})
    with pytest.raises(ValueError, match="say why"):
        _off(asked, tmp_path, "a")
    body = _body(_off(asked, tmp_path, "b", summary=WHY))
    assert body["status"] == "stopped" and body["withdrawn"] is True
    assert body["result"]["summary"] == WHY
    assert body["needs"] is None and body["note"] is None and body["asked_you_at"] is None


def test_work_whose_chat_went_quiet_is_called_off_but_a_live_claim_is_not(tmp_path):
    quiet = _w("network", "Harbourline Bank", to="computer", status="running", claimed_by="mac-1",
               claimed_at=_ago(70), lease_until=_ago(40))
    body = _body(_off(quiet, tmp_path, "q", summary=WHY))
    assert body["status"] == "stopped" and body["withdrawn"] is True
    live = dict(quiet, lease_until=app_model.stamp(T + dt.timedelta(minutes=20)))
    with pytest.raises((KeyError, ValueError)):
        _off(live, tmp_path, "l", summary=WHY)
    # Unstarted work, as before.
    assert _body(_off(_w("network", to="computer"), tmp_path, "u", summary=WHY))["withdrawn"]
