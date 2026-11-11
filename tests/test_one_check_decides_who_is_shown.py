"""One check, in code, decides who may be shown for a message: tools/network/surface.py.

The 2026-11-10 audit (NW-16): a person's own rules said to run a script of their own before
anyone was shown (written to in the last ten days, two unanswered, closed, a declined
employer, already replied), while the networking skill said surface.py was the only check.
The script matched by name alone and skipped holds, the do-not-target list, profile addresses
and the per-employer limit. Now the person's ten days is a setting surface.py reads
(networking.py QUIET_AFTER_SEND_DAYS), and a profile rule that names a script of its own which
never calls surface.py is an upgrade that points the rule back at it. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import schema  # noqa: E402
from network import surface  # noqa: E402

TODAY = datetime.date(2026, 11, 10)
ROW = {"contact_id": "ashgrove_lindqvist", "name": "Petra Lindqvist", "company": "",
       "status": "awaiting_reply", "location": ""}


def _sent(days_ago):
    return [{"contact_id": ROW["contact_id"], "direction": "outbound", "channel": "linkedin",
             "scenario": "first_message", "summary": "Note",
             "date": (TODAY - datetime.timedelta(days=days_ago)).isoformat()}]


def test_someone_written_to_five_days_ago_is_never_shown_as_someone_new():
    ctx = surface.context(contacts=[dict(ROW)], threads=_sent(5), connections=[], today=TODAY)
    got = surface.check(dict(ROW), ctx)
    assert not got["show"] and "already written to" in got["reason"]


def test_the_persons_quiet_days_hold_a_message_to_someone_written_to_lately(monkeypatch):
    monkeypatch.setattr(schema, "QUIET_AFTER_SEND_DAYS", 10)
    got = surface.held(dict(ROW), _sent(5), "awaiting_reply", today=TODAY)
    assert got and got["why"] == "recent"
    assert "2026-11-15" in got["said"]
    assert surface.held(dict(ROW), _sent(11), "awaiting_reply", today=TODAY) is None
    # They wrote back: an answer is never held by the quiet days.
    assert surface.held(dict(ROW), _sent(5), "awaiting_reply", replying=True,
                        today=TODAY) is None
    # Unset, nothing changes for anyone else.
    monkeypatch.setattr(schema, "QUIET_AFTER_SEND_DAYS", 0)
    assert surface.held(dict(ROW), _sent(5), "awaiting_reply", today=TODAY) is None


@pytest.fixture
def profile(tmp_path, monkeypatch):
    p = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), p,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    monkeypatch.setenv("LJS_PROFILE", str(p))
    person.reset()
    yield p
    monkeypatch.undo()
    person.reset()


RULE = ("\n**Before any person is shown for a message, run `python3 profile/who_check.py "
        "\"Name\" ...`**: it prints DO NOT SHOW for anyone written to in the last 10 days.\n")


def test_a_profile_rule_naming_its_own_check_is_an_upgrade_until_it_calls_surface(profile):
    up = next(u for u in U.REGISTRY if u.id == "one-surface-check")
    assert up.pending() == ""
    with open(profile / "CLAUDE.md", "a", encoding="utf-8") as fh:
        fh.write(RULE)
    (profile / "who_check.py").write_text(
        "\"\"\"The surface check, by name.\"\"\"\nimport csv\n\ndef main():\n"
        "    print('OK: not in the book')\n", encoding="utf-8")
    assert "profile/who_check.py" in up.pending()
    (profile / "who_check.py").write_text(
        "from network import surface\n\ndef main():\n    surface.check({})\n", encoding="utf-8")
    assert up.pending() == ""


# The independent review of NW-16 (2026-11-11): any profile .py named on a line with "show"
# or "surface" was flagged (the app's own data files, profile/networking.py among them), and
# the upgrade then told a chat to rewrite them; a script calling the check through
# `from network.surface import check` was flagged too; and the page had no words for the
# new hold.
def test_only_a_script_the_rule_runs_is_flagged_never_a_data_file_it_names(profile):
    up = next(u for u in U.REGISTRY if u.id == "one-surface-check")
    with open(profile / "CLAUDE.md", "a", encoding="utf-8") as fh:
        fh.write("\nWho is shown follows profile/networking.py (QUIET_AFTER_SEND_DAYS) and "
                 "the skills in profile/skills.py.\n")
    assert up.pending() == ""
    with open(profile / "CLAUDE.md", "a", encoding="utf-8") as fh:
        fh.write(RULE)
    (profile / "who_check.py").write_text(
        "from network.surface import check\n\ndef main(people):\n"
        "    return [check(p) for p in people]\n", encoding="utf-8")
    assert up.pending() == ""


def test_the_page_says_why_someone_written_to_lately_is_not_shown():
    import app_model
    row = app_model._hidden_row({"recent": 2}, 0)
    assert "2 people written to in the last few days not shown" in row["title"]
