"""The LinkedIn download is asked for as often as it is used, and as often as the person wants.

The maintainer, 2026-11-06: "LinkedIn download: a reminder weekly while I have sent notes or
messages in the last two weeks, every two weeks otherwise; its trash offers 'Every 2 weeks',
'Every month' and 'Stop asking', saved and changeable in Settings." The cadence is worked out
once, in export.every_days, on a set day here (never the machine's), and the brief, every
chat and the page read it from there. The trash's choice is a setting.set beside an
export.later in one tap, and both are taken back by Undo. Every person and message here is
invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
import export as E  # noqa: E402
import person  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

DAY = dt.date(2026, 11, 6)


def _ago(n: int) -> str:
    return (DAY - dt.timedelta(days=n)).isoformat()


def _row(days_ago: int, direction: str = "out", channel: str = "message") -> dict:
    return {"contact_id": "kestrel_example", "date": _ago(days_ago), "direction": direction,
            "channel": channel, "scenario": "", "summary": "a note", "full_text": "Hello.",
            "subject": ""}


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """A profile and state of their own, the download taken nine days before DAY and kept."""
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    st = tmp_path / "state"
    (st / "documents" / "linkedin").mkdir(parents=True)
    (st / "documents" / "linkedin" / "Connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n", encoding="utf-8")
    monkeypatch.setenv(person.ENV, prof)
    monkeypatch.setenv(person.STATE_ENV, str(st))
    # The app's own fortnight, whatever profile this run was started with.
    monkeypatch.setattr(E, "EXPORT_EVERY_DAYS", 14)
    monkeypatch.setattr(E, "_OWN_EVERY", False)
    person.reset()

    def choose(value):
        with open(os.path.join(prof, "networking.py"), "a", encoding="utf-8") as fh:
            fh.write(f'\nEXPORT_REMIND = "{value}"\n')
        person.reset()

    E.save_record({"taken_on": _ago(9)})
    yield choose
    person.reset()


def test_weekly_while_notes_or_messages_went_out_in_the_last_two_weeks(copy):
    sent = [_row(3, channel="connection"), _row(40)]
    assert E.messaging(DAY, sent)
    assert E.every_days(DAY, sent) == 7
    st = E.status(DAY.isoformat(), found=[], threads=sent)
    assert st["state"] == "request" and st["due_on"] == _ago(2), st
    assert E.due(DAY, sent).startswith("Your LinkedIn download is 9 days old")


def test_every_two_weeks_when_nothing_went_out_in_the_last_two_weeks(copy):
    # Fourteen days ago is outside the two weeks; a message from them is not one they sent.
    quiet = [_row(14), _row(2, direction="in")]
    assert not E.messaging(DAY, quiet)
    assert E.every_days(DAY, quiet) == 14
    st = E.status(DAY.isoformat(), found=[], threads=quiet)
    assert st["state"] == "fresh" and st["due_on"] == (DAY + dt.timedelta(days=5)).isoformat()
    assert E.due(DAY, quiet) == ""
    assert E.due(DAY + dt.timedelta(days=5), quiet).startswith("Your LinkedIn download is 14 days old")
    # The day just before the two weeks are up still counts as messaging.
    assert E.every_days(DAY, [_row(13)]) == 7


@pytest.mark.parametrize("choice,days", [("fortnightly", 14), ("monthly", 30)])
def test_a_chosen_cadence_holds_however_busy_the_person_is(copy, choice, days):
    copy(choice)
    busy = [_row(1)]
    assert E.remind_choice() == choice and E.every_days(DAY, busy) == days
    st = E.status(DAY.isoformat(), found=[], threads=busy)
    assert st["state"] == "fresh" and st["every_days"] == days, st
    assert st["due_on"] == (DAY - dt.timedelta(days=9) + dt.timedelta(days=days)).isoformat()


def test_stop_asking_never_asks_again_not_even_for_a_first_download(copy, tmp_path):
    copy("off")
    assert E.every_days(DAY, [_row(1)]) == 0
    assert E.status(DAY.isoformat(), found=[], threads=[])["state"] == "fresh"
    assert E.due(DAY + dt.timedelta(days=200), []) == ""
    # Nothing ever taken, and nothing on file: still not asked.
    os.remove(E.record_path())
    os.remove(os.path.join(str(tmp_path), "state", "documents", "linkedin", "Connections.csv"))
    assert E.status(DAY.isoformat(), found=[], threads=[])["state"] == "fresh"


def test_an_unknown_choice_is_the_rule(copy):
    copy("sometimes")
    assert E.remind_choice() == "auto" and E.every_days(DAY, [_row(1)]) == 7


def test_put_away_from_its_trash_the_next_ask_counts_from_that_day(copy):
    copy("fortnightly")
    E.save_record({"taken_on": _ago(20), "put_off_on": _ago(2)})
    st = E.status(DAY.isoformat(), found=[], threads=[])
    assert st["state"] == "fresh" and st["due_on"] == (DAY + dt.timedelta(days=12)).isoformat(), st
    assert E.due(DAY, []) == ""
    assert E.due(DAY + dt.timedelta(days=12), []).startswith("Your LinkedIn download is 32 days old")


# ------------------------------------------------------------------ through the page's actions


TRASH = [("fortnightly", "every two weeks"), ("monthly", "every month"), ("off", "not asked for any more")]


@pytest.mark.parametrize("choice,said", TRASH, ids=[t[0] for t in TRASH])
def test_each_trash_choice_is_applied_and_taken_back_by_undo(tmp_path, choice, said):
    page = Search(str(tmp_path))
    ex = page.model()["linkedin"]["export"]
    rem = ex["reminder"]
    assert (rem["id"], rem["value"]) == ("setting-export_remind", "auto")
    assert [c[1] for c in rem["choices"]] == ["Weekly while messaging", "Every 2 weeks",
                                               "Every month", "Off"]
    assert ex["due"] is True, ex
    # The one tap the trash sends: how often, and this reminder put away.
    a = page.act("setting.set", rem["id"], value=choice, rev=rem["rev"])
    b = page.act("export.later", "linkedin-export", value={"day": "2026-10-25"}, rev=ex["rev"])
    got = page.apply()
    assert got["ok"] == [a, b], (page.receipt(a), page.receipt(b))
    assert said in page.receipt(a)["note"]
    with open(os.path.join(page.profile, "networking.py"), encoding="utf-8") as fh:
        assert f'EXPORT_REMIND = "{choice}"' in fh.read()
    with open(os.path.join(page.state, "documents", "network", "linkedin_export.json"),
              encoding="utf-8") as fh:
        assert json.load(fh)["put_off_on"] == "2026-10-25"
    ex = page.model()["linkedin"]["export"]
    assert ex["reminder"]["value"] == choice and ex["due"] is False, ex
    assert ex["every_days"] == {"fortnightly": 14, "monthly": 30, "off": 0}[choice]
    # Undo in its toast takes back both.
    page.written_back()
    back_a = page.act("undo", None, value={"undoes": a})
    back_b = page.act("undo", None, value={"undoes": b})
    assert page.apply()["ok"] == [back_a, back_b]
    ex = page.model()["linkedin"]["export"]
    assert ex["reminder"]["value"] == "auto" and ex["due"] is True, ex


def test_settings_offers_the_rule_back_and_refuses_a_choice_it_does_not_have(tmp_path):
    page = Search(str(tmp_path))
    rem = page.model()["linkedin"]["export"]["reminder"]
    a = page.act("setting.set", rem["id"], value="off", rev=rem["rev"])
    assert page.apply()["ok"] == [a]
    rem = page.model()["linkedin"]["export"]["reminder"]
    b = page.act("setting.set", rem["id"], value="auto", rev=rem["rev"])
    c = page.act("setting.set", rem["id"], value="daily", rev=rem["rev"])
    got = page.apply()
    assert got["ok"] == [b] and "not one of the choices" in page.receipt(c)["note"], got
    assert "weekly while you are messaging people" in page.receipt(b)["note"]
    assert page.model()["linkedin"]["export"]["reminder"]["value"] == "auto"
