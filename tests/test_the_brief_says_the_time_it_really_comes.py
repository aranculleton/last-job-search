"""The brief's time on the page is the time it really comes, and a time the person picks sticks.

The maintainer, 2026-11-06: "The brief time moves without telling the person. The app turns
8:00 into 7:38 without saying so, and the scheduler itself turns 8:00 into 8:07. The page
should show the real time, or let the person pick one that sticks." The app moved every time
picked on the hour 1 to 29 minutes earlier (Claude's own scheduling guidance), and a run set on
the hour can start several minutes late (code.claude.com/docs/en/routines, "Runs on the
hour"). Now a picked time is kept to the minute, only the app's own default is moved and says
so, and a late start the scheduler reports is the time shown, with one line why. Every person
here is invented; no network.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import routines  # noqa: E402

LONDON = "Europe/London"
MOVED = "Comes at 7:38: a few minutes before the hour, when the service is less busy."


def _registry(tmp_path, cron, **brief):
    path = str(tmp_path / "routines.json")
    reg = {"setup": "chat_per_briefing", "timezone": LONDON,
           "routines": [{"key": "morning_brief", "name": routines.BRIEF_NAME,
                         "chat": {"session_id": "session_EXAMPLEHELPER"},
                         "trigger_id": "trig_EXAMPLEBRIEF", "cron": cron,
                         "prompt_file": routines.BRIEF_FILE, **brief}]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    return path


def _brief(path):
    with open(path, encoding="utf-8") as fh:
        return next(r for r in json.load(fh)["routines"] if r["key"] == "morning_brief")


# ------------------------------------------------------------------ a time picked sticks


def test_a_chosen_8_is_stored_as_8_and_shown_as_8_with_nothing_to_explain(tmp_path):
    path = _registry(tmp_path, f"CRON_TZ={LONDON} 38 7 * * *")
    got = routines.move(time="08:00", path=path)
    assert got["cron"] == f"CRON_TZ={LONDON} 0 8 * * *"
    assert got["say"] == "Your brief comes every day at 8:00 from now on."
    r = _brief(path)
    assert r["cron"] == f"CRON_TZ={LONDON} 0 8 * * *"
    assert r["asked"] == {"time": "08:00", "by": "person"}
    part = routines.page_part(path)
    assert (part["when"], part["time"], part["why"]) == ("Every day at 8:00", "08:00", "")
    # New days later, the same time sent back: still 8:00, still theirs.
    routines.move(days="weekdays", time="08:00", path=path)
    assert _brief(path)["cron"] == f"CRON_TZ={LONDON} 0 8 * * 1,2,3,4,5"
    assert routines.page_part(path)["when"] == "Weekdays at 8:00"
    # Half past is kept too.
    routines.move(time="6:30", path=path)
    assert routines.page_part(path)["when"] == "Weekdays at 6:30"


def test_a_chosen_8_from_the_page_is_kept_and_undo_brings_back_the_moved_default(tmp_path):
    from test_a_tick_on_the_page_is_applied_once import Search
    search = Search(str(tmp_path))
    s = search.model()["schedule"]
    assert s["when"] == "Every day at 7:38" and s["why"] == MOVED
    aid = search.act("brief.move", "schedule", value={"days": [1, 2, 3, 4, 5, 6, 7],
                                                      "time": "08:00"}, rev=s["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.receipt(aid)["note"].startswith("Your brief comes every day at 8:00 from now on.")
    s2 = search.model()["schedule"]
    assert (s2["when"], s2["time"], s2["why"]) == ("Every day at 8:00", "08:00", "")
    reg = json.load(open(os.path.join(search.profile, "routines.json"), encoding="utf-8"))
    assert reg["owed"][-1]["args"]["cron_expression"].endswith(" 0 8 * * *")
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back], search.receipt(back)
    s3 = search.model()["schedule"]
    assert s3["when"] == "Every day at 7:38" and s3["why"] == MOVED


# ------------------------------------------------------------------ the app's own default


def test_the_apps_default_is_shown_as_the_moved_time_with_its_line(tmp_path):
    d = routines.default(LONDON, page=True)
    assert d["cron"] == f"CRON_TZ={LONDON} 38 7 * * *" and d["asked"] == "08:00"
    assert "It comes a few minutes before the hour, when the service is less busy." in d["say"]
    # Recorded as the setup chat records it: what was asked beside what was set.
    path = str(tmp_path / "routines.json")
    routines.record("session_EXAMPLEHELPER", "trig_EXAMPLEBRIEF", d["cron"], path=path,
                    asked=d["asked"])
    assert _brief(path)["asked"] == {"time": "08:00", "by": "app"}
    part = routines.page_part(path)
    assert (part["when"], part["time"], part["why"]) == ("Every day at 7:38", "07:38", MOVED)
    # The setup command carries what was asked.
    assert "--asked 08:00" in routines.plan("example", "copy", LONDON,
                                            chat="session_EXAMPLEHELPER")["record"]


def test_an_older_copy_with_a_moved_minute_and_no_record_is_shown_its_real_time_and_why(tmp_path):
    # Made before what was asked was recorded: only the app's rule ever set :38.
    path = _registry(tmp_path, f"CRON_TZ={LONDON} 38 7 * * 1,4")
    part = routines.page_part(path)
    assert (part["when"], part["why"]) == ("Mondays and Thursdays at 7:38", MOVED)
    assert "It comes a few minutes before the hour" in routines.where_line(routines.load(path))
    # Out of the scheduler's slow hours on the US west coast: earlier than asked, and said.
    west = routines.real_time({"cron": "CRON_TZ=America/Los_Angeles 38 5 * * *",
                               "asked": {"time": "08:00", "by": "app"}})
    assert west["why"] == ("Comes at 5:38: earlier than 8:00, outside the hours when the service "
                           "often starts late.")
    # A time nobody moved has nothing to explain.
    assert routines.page_part(_registry(tmp_path, f"CRON_TZ={LONDON} 15 9 * * *"))["why"] == ""


# ------------------------------------------------------------------ the scheduler's late start


def _listing(cron_seen_at, next_run_at="", fired_at=""):
    return routines.listing({"data": [{
        "id": "trig_EXAMPLEBRIEF", "name": routines.BRIEF_NAME, "cron_expression": cron_seen_at,
        "persistent_session_id": "session_EXAMPLEHELPER", "enabled": True,
        "derived_state": {"prompt": "Scheduled run: morning brief. " + routines.BRIEF_FILE},
        **({"next_run_at": next_run_at} if next_run_at else {}),
        "last_run": ({"status": "SUCCEEDED", "fired_at": fired_at} if fired_at else {})}],
        "has_more": False})[0]


def test_a_later_time_the_scheduler_reports_is_the_time_shown(tmp_path):
    cron = f"CRON_TZ={LONDON} 0 8 * * *"
    path = _registry(tmp_path, cron, asked={"time": "08:00", "by": "person"})
    assert routines.page_part(path)["when"] == "Every day at 8:00"
    # The last run fired at 8:07 London time (GMT in November).
    assert routines.saw(_listing(cron, fired_at="2026-11-05T08:07:31Z"), path=path)
    part = routines.page_part(path)
    assert (part["when"], part["time"], part["real_time"]) == ("Every day at 8:07", "08:00", "08:07")
    assert part["why"] == ("Comes at about 8:07: the service starts it a few minutes after 8:00, "
                           "the time it is set for. A time a few minutes past the hour starts on "
                           "time.")
    assert "every day at 8:07" in routines.where_line(routines.load(path))
    assert not routines.saw(_listing(cron, fired_at="2026-11-05T08:07:31Z"), path=path)
    # Its next run, as the scheduler reports it, counts the same way (summer time: BST).
    path2 = _registry(tmp_path, cron)
    routines.saw(_listing(cron, next_run_at="2026-07-02T07:06:00Z"), path=path2)
    assert routines.page_part(path2)["when"] == "Every day at 8:06"
    # Moved since: what was seen of the old time says nothing about the new one.
    routines.move(time="09:15", path=path)
    part = routines.page_part(path)
    assert (part["when"], part["why"]) == ("Every day at 9:15", "")


def test_routines_brief_keeps_what_the_scheduler_reports(tmp_path):
    import subprocess
    profile = tmp_path / "profile"
    profile.mkdir()
    cron = f"CRON_TZ={LONDON} 0 8 * * *"
    _registry(profile, cron)
    listing = tmp_path / "listing.json"
    listing.write_text(json.dumps({"data": [{
        "id": "trig_EXAMPLEBRIEF", "name": routines.BRIEF_NAME, "cron_expression": cron,
        "persistent_session_id": "session_EXAMPLEHELPER", "enabled": True,
        "derived_state": {"prompt": "Scheduled run: morning brief. " + routines.BRIEF_FILE},
        "last_run": {"status": "SUCCEEDED", "fired_at": "2026-11-05T08:07:00Z",
                     "session_id": "session_EXAMPLEHELPER"}}], "has_more": False}))
    env = dict(os.environ, LJS_PROFILE=str(profile), LJS_STATE=str(tmp_path / "state"),
               LJS_COPY="private", LJS_CHAT="session_EXAMPLEHELPER")
    env.pop("CLAUDE_CODE_REMOTE", None)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), "brief",
                        "--triggers", str(listing), "--chat", "session_EXAMPLEHELPER"],
                       cwd=ROOT, env=env, capture_output=True, encoding="utf-8", timeout=120)
    assert r.stdout.startswith("registered:"), r.stdout + r.stderr
    assert routines.page_part(str(profile / "routines.json"))["when"] == "Every day at 8:07"


# ------------------------------------------------------------------ on the page


@pytest.fixture(scope="module")
def run():
    import test_the_page_journeys as journeys
    yield from journeys.browser()


def test_settings_shows_the_real_time_its_line_and_the_time_set_in_the_sheet(run, tmp_path):
    from test_the_page_journeys import PHONE, _go, _sample
    m = _sample()
    m["schedule"] = dict(copy.deepcopy(m["schedule"]), when="Mondays and Thursdays at 8:07",
                         time="08:00", real_time="08:07",
                         why="Comes at about 8:07: the service starts it a few minutes after "
                             "8:00, the time it is set for.")
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:brief-when", "read": "#main"},
        {"click": "Change it", "within": "#main"},
        {"eval": "document.querySelector('dialog[open] input[type=time]').value"},
    ], PHONE, model=m, clock="2026-10-25T09:00:00Z")
    row = got["after"][0]["text"]
    assert "Mondays and Thursdays at 8:07" in row and "Comes at about 8:07" in row
    assert "at 8:00" not in row
    assert got["after"][2]["eval"] == "08:00", "the sheet edits the time it is set for"
