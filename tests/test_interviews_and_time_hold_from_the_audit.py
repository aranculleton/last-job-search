"""Interviews and time, from the 3 November audit: the engine half.

Each test is one finding's own steps (the audit's interviews area and the top 30, items 14,
15, 16, 17 and 29), on invented people and employers. Times are worked out in London, Toronto
and Vancouver, before and after the clocks change (Europe on 25 October 2026, North America on
1 November 2026), because the bugs lived exactly there: a Toronto person whose brief runs on
UK time had every time on the page five hours out.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import brief  # noqa: E402
import docpaths  # noqa: E402
import interview_pack  # noqa: E402
import open_actions  # noqa: E402
import person  # noqa: E402
import upcoming  # noqa: E402
import what_works  # noqa: E402

CO, ROLE = "Quayside Analytics", "Data Scientist"
HEAD = "# Outcome\n\n## Interview stages reached\n\n"


# ------------------------------------------------------------------ helpers


@pytest.fixture
def where(tmp_path, monkeypatch):
    """A state folder and a profile of one's own, the profile a copy of the example person's."""
    import app_state
    state = tmp_path / "state"
    state.mkdir()
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    monkeypatch.setenv("LJS_STATE", str(state))
    monkeypatch.setenv("LJS_PROFILE", prof)
    person.reset()
    yield types.SimpleNamespace(state=str(state), profile=prof)
    person.reset()


def _toronto(prof, routines_zone="Europe/London"):
    """The audit's person: TIMEZONE in plain words, a brief scheduled on UK time."""
    net = os.path.join(prof, "networking.py")
    text = open(net, encoding="utf-8").read()
    text = text.replace('TIMEZONE = "UK time (Europe/London)"', 'TIMEZONE = "Eastern (Toronto time)"')
    text = text.replace('HOME_CITY = "Manchester"', 'HOME_CITY = "Toronto"')
    open(net, "w", encoding="utf-8").write(text)
    routines = os.path.join(prof, "routines.json")
    got = json.load(open(routines, encoding="utf-8"))
    got["timezone"] = routines_zone
    json.dump(got, open(routines, "w", encoding="utf-8"))
    person.reset()


def _row(status="interview", notes=""):
    return {"company": CO, "role": ROLE, "status": status, "notes": notes, "date": "2026-10-01",
            "applied_on": "2026-10-02", "cv_file": "", "cover_letter_file": "", "deadline": ""}


def _outcome(lines):
    folder = docpaths.app_folder(CO, ROLE)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write(HEAD + "".join(x + "\n" for x in lines))
    return folder


def _ctx(today, now=None, zone="Europe/London", tracker=None, contacts=()):
    return types.SimpleNamespace(today=dt.date.fromisoformat(today),
                                 now=app_model.parse_time(now) if now else None, zone=zone,
                                 names=(), contacts=list(contacts),
                                 tracker=tracker if tracker is not None else [_row()])


# ------------------------------------------------------------------ the person's own zone (top 30, 14; interviews 5)


def test_the_persons_zone_is_read_from_their_words_and_never_from_the_brief(where):
    _toronto(where.profile)
    assert person.home_zone_named(where.profile) == "America/Toronto"
    # The page is told Toronto, and "today" is Toronto's: 20:30 in Toronto on 3 November is
    # already the 4th in London.
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-04T01:30:00Z"))
    assert ctx.zone == "America/Toronto"
    assert app_model._person(ctx, {})["time_zone"] == "America/Toronto"
    assert app_model.local_day(ctx.now, ctx.zone).isoformat() == "2026-11-03"


@pytest.mark.parametrize("words, want", [
    ("Eastern (Toronto time)", "America/Toronto"), ("Pacific Time", "America/Los_Angeles"),
    ("UK time (Europe/London)", "Europe/London"), ("Vancouver", "America/Vancouver"),
    ("Mississauga, ON", "America/Toronto"), ("the local time zone", ""), ("", "")])
def test_a_zone_said_in_plain_words_is_read(words, want):
    assert person.zone_in(words) == want


def test_with_no_zone_named_the_page_is_told_none_and_asks_for_it(where):
    net = os.path.join(where.profile, "networking.py")
    text = open(net, encoding="utf-8").read()
    text = text.replace('TIMEZONE = "UK time (Europe/London)"', 'TIMEZONE = "my time"')
    text = text.replace('HOME_CITY = "Manchester"', 'HOME_CITY = ""')
    open(net, "w", encoding="utf-8").write(text)
    data = json.load(open(os.path.join(where.profile, "person.json"), encoding="utf-8"))
    data["identity"]["location"] = ""
    json.dump(data, open(os.path.join(where.profile, "person.json"), "w", encoding="utf-8"))
    person.reset()
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T12:00:00Z"))
    targets = {}
    assert app_model._person(ctx, targets)["time_zone"] == ""
    asks = app_model._zone_question(ctx, targets)
    assert [a["id"] for a in asks] == ["q-time-zone"] and asks[0]["options"][0]["input"] == "text"
    assert targets["q-time-zone"]["key"] == "time_zone"


def test_the_zone_said_on_the_page_is_kept_and_words_naming_none_are_refused(where):
    import app_actions
    run = types.SimpleNamespace(target={"kind": "setting", "key": "time_zone"},
                                value={"value": "Vancouver"}, words=None)
    run.words = lambda k="why": " ".join(str(run.value.get(k) or "").split())
    got = app_actions._set_time_zone(run)
    assert person.get("time_zone") == "America/Vancouver" and "Vancouver" in got["note"]
    assert app_model.setting_values()["time_zone"] == "Vancouver"
    run.value = {"value": "somewhere nice"}
    with pytest.raises(app_actions.Refused, match="write your city"):
        app_actions._set_time_zone(run)
    # Its undo puts back what was there: nothing.
    run.value = got["undo"]["value"]
    app_actions._set_time_zone(run)
    assert person.get("time_zone", "") == ""


@pytest.mark.parametrize("day, clock, zone, want", [
    # Before and after the clocks go back in Canada and the US (1 November 2026); London's went back on
    # 25 October, so the week between is four hours apart, not five.
    ("2026-10-30", "10:00", "America/Toronto", "2026-10-30T14:00:00Z"),
    ("2026-11-03", "10:00", "America/Toronto", "2026-11-03T15:00:00Z"),
    # British Columbia keeps one clock all year in the newest zone data, so its moment comes
    # from the zone itself.
    ("2026-10-30", "10:00", "America/Vancouver", None),
    ("2026-11-03", "10:00", "America/Vancouver", None),
    ("2026-10-24", "18:00", "Europe/London", "2026-10-24T17:00:00Z"),
    ("2026-10-26", "18:00", "Europe/London", "2026-10-26T18:00:00Z"),
])
def test_an_interview_time_is_the_moment_in_its_zone_across_the_clock_changes(day, clock, zone, want):
    if want is None:
        import zoneinfo
        h, m = (int(x) for x in clock.split(":"))
        at = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(h, m), zoneinfo.ZoneInfo(zone))
        want = at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
    assert app_model.interview_when(day, clock, zone, "UTC") == want
    # Written in words beside the time, the same moment; "Pacific" for a person in Vancouver
    # is Vancouver's clock.
    words = {"America/Toronto": "Toronto time", "America/Vancouver": "Pacific",
             "Europe/London": "UK"}[zone]
    assert app_model.interview_when(day, clock, words, zone) == want


# ------------------------------------------------------------------ a time typed with a zone (interviews 6, 12, 23)


@pytest.mark.parametrize("said, home, want", [
    ("Meet 3pm Toronto time", "Europe/London", ("15:00", None, "America/Toronto")),
    ("10am ET", "America/Toronto", ("10:00", None, "America/Toronto")),
    ("1:00 PM EST", "America/Toronto", ("13:00", None, "America/Toronto")),
    ("2pm", "America/Toronto", ("14:00", None, "America/Toronto")),
    ("noon", "America/Vancouver", ("12:00", None, "America/Vancouver")),
    ("10-11am", "Europe/London", ("10:00", "11:00", "Europe/London")),
    ("2pm Pacific Time", "America/Toronto", ("14:00", None, "America/Los_Angeles")),
    ("Call at 14.30 Thursday", "America/Toronto", ("14:30", None, "America/Toronto")),
])
def test_a_time_as_people_write_it_is_read_with_its_zone(said, home, want):
    got = upcoming.call_time(said, home)
    assert (got["time"], got["end"], got["zone"]) == want


def test_two_times_offered_are_a_choice_not_a_booking():
    assert upcoming.call_time("Are you free 12pm or Friday 6 November at 9am Eastern?",
                              "America/Toronto") is None


def _apply_outcome(where, value, folder=None):
    """outcome.interview applied the way the page's tap is, on a tracker row of our own."""
    import app_actions
    import csv_store
    import throttle
    path = person.state("job_search_tracker.csv")
    cols = ["date", "company", "role", "status", "notes", "applied_on"] + list(throttle.CONFIRM_COLUMNS)
    if not os.path.exists(path):
        csv_store.write_rows(path, [_row()], cols)
    run = types.SimpleNamespace(target={"kind": "application", "company": CO, "role": ROLE,
                                        "date": "2026-10-01"},
                                value=value, day=dt.date(2026, 11, 3),
                                local=dt.datetime(2026, 11, 3, 12, 0))
    run.words = lambda k="why": " ".join(str(run.value.get(k) or "").split())
    return app_actions._outcome(run, "interview")


def test_a_time_typed_with_its_zone_is_kept_and_one_it_cannot_read_is_refused(where):
    import app_actions
    _toronto(where.profile)
    got = _apply_outcome(where, {"stage": "first round", "on": "2026-11-12", "time": "10am ET",
                                 "zone": "America/Toronto", "minutes": 120, "place": "Teams"})
    assert "10:00 Toronto time" in got["note"]
    md = open(os.path.join(docpaths.app_folder(CO, ROLE), "outcome.md"), encoding="utf-8").read()
    assert "- [ ] First round (scheduled 2026-11-12 10:00 America/Toronto, 120 min, on Teams)" in md
    st = what_works.outcome_stages(md)[0]
    assert (st["time"], st["zone"], st["minutes"], st["place"]) == ("10:00", "America/Toronto", 120, "Teams")
    # Coming up: two hours, on Teams, at 10:00 Toronto (15:00 UTC on 12 November).
    up = upcoming.build(_ctx("2026-11-03", "2026-11-03T16:00:00Z", zone="America/Toronto"))[0]
    assert (up["start"], up["end"], up["place"]) == ("2026-11-12T15:00:00Z", "2026-11-12T17:00:00Z",
                                                     "Microsoft Teams")
    with pytest.raises(app_actions.Refused, match="could not be read"):
        _apply_outcome(where, {"stage": "First round", "on": "2026-11-12", "time": "after lunch"})


# ------------------------------------------------------------------ several days offered (top 30, 15; interviews 1, 2, 4)


def test_an_invitation_offering_several_days_is_a_choice_owed_everywhere(where):
    _apply_outcome(where, {"stage": "initial round", "on": "",
                           "offered": ["2026-11-12", "2026-11-13", "2026-11-19", "2026-11-20"],
                           "reply_by": "2026-11-04", "with": "the recruiter"})
    md = open(os.path.join(docpaths.app_folder(CO, ROLE), "outcome.md"), encoding="utf-8").read()
    assert "- [ ] Initial round (offered 2026-11-12, 2026-11-13, 2026-11-19, 2026-11-20; " \
           "reply by 2026-11-04, with the recruiter)" in md
    st = what_works.outcome_stages(md)[0]
    assert st["offered"][0] == "2026-11-12" and st["reply_by"] == "2026-11-04" and not st["date"]
    # To do and the Brief: the choice, due by the day to answer, even where the employer has a
    # chat of its own (it was held there, and reached nothing).
    folder = docpaths.app_folder(CO, ROLE)
    with open(os.path.join(folder, "campaign.json"), "w", encoding="utf-8") as fh:
        json.dump({"chat": "its own chat"}, fh)
    items = open_actions.due_items([], [], [_row()], dt.date(2026, 11, 3))
    choose = [i for i in items if i.get("sub") == "choose"]
    assert len(choose) == 1 and not choose[0]["held"] and choose[0]["due"] == "2026-11-04"
    assert "12, 13, 19 or 20 Nov" in choose[0]["what"]
    # Coming up: a day to choose, with the days offered, on the day to answer by.
    up = upcoming.build(_ctx("2026-11-03", "2026-11-03T16:30:00Z"))
    assert [(u["kind"], u["day"]) for u in up] == [("deadline", "2026-11-04")]
    assert up[0]["offered"] == ["2026-11-12", "2026-11-13", "2026-11-19", "2026-11-20"]
    assert "Thu 12, Fri 13, Thu 19 or Fri 20 Nov" in up[0]["note"]
    # The Brief's opening line says it, never the chat's own name.
    lead = brief._lead({"processes": [_row()], "applications": 1}, [], [], True, [], {}, dt.date(2026, 11, 3))
    assert lead == CO + ": choose your initial round day (12, 13, 19 or 20 Nov) and tell them, by Wed 4 Nov."
    # Choosing a day books it in place of the offer.
    _apply_outcome(where, {"stage": "Initial round", "on": "2026-11-13"})
    md = open(os.path.join(folder, "outcome.md"), encoding="utf-8").read()
    assert "offered" not in md and "- [ ] Initial round (scheduled 2026-11-13" in md


def test_the_model_carries_the_days_offered_on_the_interview(where):
    _outcome(["- [ ] Initial round (offered 2026-11-12, 2026-11-13; reply by 2026-11-04)"])
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T16:30:00Z"))
    ctx._got["tracker"] = [_row()]
    iv = app_model._interviews(ctx, {})[0]
    assert (iv["next_stage"], iv["offered"], iv["reply_by"], iv["when"]) == (
        "Initial round", ["2026-11-12", "2026-11-13"], "2026-11-04", None)


# ------------------------------------------------------------------ a round that has been (top 30, 16; interviews 7, 26)


def test_a_round_held_stays_itself_and_its_thank_you_is_owed_that_evening_with_a_done(where):
    folder = _outcome(["- [ ] Recruiter screen (scheduled 2026-11-02 18:00 Europe/London, 30 min)"])
    assert interview_pack.next_stage(what_works.outcome_stages(open(
        os.path.join(folder, "outcome.md")).read()), "2026-11-03")["label"] == "Round 2"
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T16:30:00Z"))
    ctx._got["tracker"] = [_row()]
    iv = app_model._interviews(ctx, {})[0]
    assert iv["next_stage"] == "Recruiter screen" and iv["when"] == "2026-11-02T18:00:00Z"
    # The thank-you is owed the same evening, once the screen has ended, not the day after.
    same = open_actions.interview_items([_row()], dt.date(2026, 11, 2),
                                        app_model.parse_time("2026-11-02T19:00:00Z"))
    assert [(i["sub"], i["due"]) for i in same] == [("thank_you", "2026-11-02")]
    before = open_actions.interview_items([_row()], dt.date(2026, 11, 2),
                                          app_model.parse_time("2026-11-02T17:00:00Z"))
    assert [i["sub"] for i in before] != ["thank_you"]
    # On To do it has a Done, which writes that it went.
    due = [d for d in app_model._due(ctx, {}) if d["sub"] == "thank_you"]
    assert due and due[0]["done"] == {"action": "due.done", "label": "Done"}


def test_done_on_a_thank_you_clears_it(where):
    _outcome(["- [x] Recruiter screen (2026-11-02)"])
    notes = "2026-11-03: %s, said on the page" % open_actions.THANKED_NOTE
    assert not [i for i in open_actions.interview_items([_row(notes=notes)], dt.date(2026, 11, 3))
                if i["sub"] == "thank_you"]
    assert [i for i in open_actions.interview_items([_row()], dt.date(2026, 11, 3))
            if i["sub"] == "thank_you"]


# ------------------------------------------------------------------ first in To do and the Brief (top 30, 29; interviews 8)


def test_an_interviews_own_items_come_first_however_much_else_is_owed(where):
    _outcome(["- [x] Recruiter screen (2026-11-02)"])
    contacts = [{"contact_id": "c%03d" % n, "name": "Wren Example%d" % n, "company": "Fernhill",
                 "status": "connected_no_reply", "next_action": "follow up",
                 "next_action_due": "2026-10-01", "title": "", "notes": ""} for n in range(550)]
    items = open_actions.due_items(contacts, [], [_row()], dt.date(2026, 11, 3))
    ordered = sorted(items, key=open_actions.urgency)
    assert ordered[0]["kind"] == "interview" and ordered[0]["sub"] == "thank_you"
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T09:00:00Z"))
    ctx._got["tracker"] = [_row()]
    ctx._got["contacts"] = contacts
    ctx._got["due_items"] = items
    due = app_model._due(ctx, {})
    assert due[0]["sub"] == "thank_you"


def test_the_brief_on_an_interview_day_leads_with_it_by_its_day_not_tracker_order(where):
    # Interviews 8: the 2 Nov brief never mentioned the screen that evening; its lead was the
    # first process in the tracker, and named that employer's chat.
    _outcome(["- [ ] Recruiter screen (scheduled 2026-11-02 18:00 Europe/London, 30 min)"])
    first = dict(_row(), company="Brackmoor Retail", role="Buyer")
    lead = brief._lead({"processes": [first, _row()], "applications": 2}, [], [], True, [],
                       {"brackmoor retail": "its own chat"}, dt.date(2026, 11, 2))
    assert lead == "Recruiter screen with %s is today at 18:00 (and 1 more). Your prep is on your page." % CO


def test_next_three_puts_the_thank_you_before_replies():
    got = [{"kind": "interview", "sub": "thank_you", "key": "q", "name": CO + " (" + ROLE + ")",
            "what": "thank-you not logged after the screen", "half": "application",
            "draft": {"status": "none"}}]
    replies = [{"kind": "reply", "key": "r%d" % n, "name": "Juno%d" % n, "what": "reply",
                "half": "contact", "draft": {"status": "write"}} for n in range(3)]
    three = brief._next_three(got + replies, {"applications": 1}, replies, [], {}, "", "",
                              True, [], dt.date(2026, 11, 3))
    assert three[0].startswith("Send the thank-you after your interview at " + CO)


# ------------------------------------------------------------------ the next round, by its day (interviews 10)


def test_a_round_moved_under_another_name_is_moved_and_the_next_is_the_earliest(where):
    folder = docpaths.app_folder(CO, ROLE)
    interview_pack.record_stage(folder, CO, ROLE, "Initial round", "2026-11-12", time="10:00")
    interview_pack.record_stage(folder, CO, ROLE, "First round", "2026-11-13", time="10:00")
    stages = what_works.outcome_stages(open(os.path.join(folder, "outcome.md")).read())
    assert [(s["label"], s["date"]) for s in stages] == [("First round", "2026-11-13")]
    interview_pack.record_stage(folder, CO, ROLE, "Final round", "2026-11-20")
    stages = what_works.outcome_stages(open(os.path.join(folder, "outcome.md")).read())
    assert interview_pack.next_stage(stages, "2026-11-03")["label"] == "First round"
    assert [s["label"] for s in stages] == ["First round", "Final round"]


# ------------------------------------------------------------------ Coming up's own times (interviews 11, 13, 15, 25)


def test_an_end_time_is_on_the_day_it_was_written_for():
    item = upcoming._item("call", "x", "Call", "2026-11-10", "18:00", "America/Los_Angeles",
                          "18:30", home="Europe/London")
    assert (item["day"], item["start"], item["end"]) == (
        "2026-11-11", "2026-11-11T02:00:00Z", "2026-11-11T02:30:00Z")
    tokyo = upcoming._item("call", "y", "Call", "2026-11-10", "10:00", "Asia/Tokyo", "10:45",
                           home="America/Toronto")
    assert (tokyo["start"], tokyo["end"]) == ("2026-11-10T01:00:00Z", "2026-11-10T01:45:00Z")


def test_a_round_that_has_ended_leaves_coming_up_that_evening(where):
    _outcome(["- [ ] Recruiter screen (scheduled 2026-11-02 18:00 Europe/London, 30 min)"])
    assert upcoming.build(_ctx("2026-11-02", "2026-11-02T17:00:00Z"))
    assert upcoming.build(_ctx("2026-11-02", "2026-11-02T22:30:00Z")) == []


def test_a_moved_interview_keeps_its_calendar_id_and_its_name_starts_as_a_title(where):
    folder = _outcome(["- [ ] initial round (scheduled 2026-11-12 10:00 Europe/London)"])
    one = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z"))[0]
    assert one["title"].startswith("Initial round: ")
    interview_pack.record_stage(folder, CO, ROLE, "initial round", "2026-11-12", time="11:00",
                                zone="Europe/London")
    two = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z"))[0]
    uid = lambda i: next(x for x in i["cal"]["ics"].split("\r\n") if x.startswith("UID:"))  # noqa: E731
    assert one["start"] != two["start"] and uid(one) == uid(two)
    assert "SEQUENCE:" in two["cal"]["ics"]


# ------------------------------------------------------------------ tests are not meetings (interviews 16)


def test_a_test_is_something_to_do_by_its_day_never_a_meeting_to_thank_anyone_for(where):
    _outcome(["- [x] Online test (due 2026-11-01)", "- [ ] Case study (due 2026-11-05)"])
    items = open_actions.interview_items([_row()], dt.date(2026, 11, 3))
    assert [(i["sub"], i["what"].split(" (")[0]) for i in items] == [("test", "do the Case study by Thu 5 Nov")]
    # An assessment centre is a day of interviews, never a test.
    _outcome(["- [ ] Assessment centre (scheduled 2026-11-06)"])
    items = open_actions.interview_items([_row()], dt.date(2026, 11, 3))
    assert [i["sub"] for i in items] == ["prep"]


# ------------------------------------------------------------------ an older prep (interviews 17)


def test_a_prep_for_an_older_plan_of_rounds_says_so(where):
    folder = _outcome(["- [ ] Code review interview", "- [ ] Personal interview"])
    with open(os.path.join(folder, "interview_prep.md"), "w", encoding="utf-8") as fh:
        fh.write("# Prep\n\n<!-- stages: Code review interview; Personal interview -->\n")
    old = os.path.getmtime(os.path.join(folder, "interview_prep.md")) - 3600
    os.utime(os.path.join(folder, "interview_prep.md"), (old, old))
    interview_pack.record_stage(folder, CO, ROLE, "Initial round", "2026-11-12")
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T09:00:00Z"))
    ctx._got["tracker"] = [_row()]
    iv = app_model._interviews(ctx, {})[0]
    assert iv["next_stage"] == "Initial round" and iv["prep"]["stale"] is True
    # The offer is not one of the rounds.
    assert "Offer received" not in [s["label"] for s in iv["stages"]]


# ------------------------------------------------------------------ the Brief's lines (interviews 18, 19)


def test_the_briefs_sentences_stay_apart_and_link_to_the_employer_they_name(where):
    sections = app_model.brief_sections("# Brief\n\n## Where the search is\n\nTuesday brief: 3 owed · "
                                        "2 interviews\n\nLarkspur Retail is live.\n")
    assert sections[0]["text"] == "Tuesday brief: 3 owed · 2 interviews. Larkspur Retail is live."
    # A short name inside a longer word is not that employer: "Lark" in "Larkspur", "Ash" in
    # "Ashford" (the audit's were a two-letter firm inside another's name, and in "they").
    ctx = types.SimpleNamespace(tracker=[dict(_row(), company="Lark"), dict(_row(), company="Larkspur Retail")],
                                contacts=[{"company": "Ash", "contact_id": "ash_x"}])
    assert app_model.brief_link(ctx, "Larkspur Retail is live, and they wrote")["item"] == \
        app_model.tracker_ids(ctx.tracker)[1]
    assert app_model.brief_link(ctx, "Ashford holds its rates")["item"] is None
    assert app_model.brief_link(ctx, "Lark wrote back")["item"] == app_model.tracker_ids(ctx.tracker)[0]


def test_since_the_last_brief_counts_an_interview_after_it_happened_in_good_english(where):
    _outcome(["- [ ] Recruiter screen (scheduled 2026-11-02 18:00)"])
    on_the_day = brief.counts_since([_row()], [], dt.date(2026, 11, 1), dt.date(2026, 11, 2))
    after = brief.counts_since([_row()], [], dt.date(2026, 11, 2), dt.date(2026, 11, 3))
    assert (on_the_day["interviews"], after["interviews"]) == (0, 1)
    line = brief.since_line({"since": "2026-11-02", "since_counts": dict(after, sent=0, replies=1)})
    assert "1 reply, 1 interview" in line


# ------------------------------------------------------------------ what was sent (interviews 28)


def test_one_resume_logged_twice_is_listed_once():
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T09:00:00Z"))
    ctx._got["contacts"] = [{"contact_id": "fern_x", "name": "Juno Example", "company": CO}]
    ctx._got["by_contact"] = {"fern_x": []}
    sent = [{"files": [], "date": "2026-10-30"}, {"files": [], "date": "2026-10-30"}]
    from network import state as net_state
    orig = net_state.resumes_sent
    net_state.resumes_sent = lambda msgs, cid: sent
    try:
        got = app_model._sent_files(ctx, dict(_row(), channel="referral", applied_on=""))
    finally:
        net_state.resumes_sent = orig
    resumes = [f for f in got if f["to"] == "Juno"]
    assert len(resumes) == 1 and resumes[0]["kind"] == "resume"


# ------------------------------------------------------------------ the whole prep (top 30, 17; interviews 9)


def test_the_whole_prep_reaches_the_page_however_long_it_is():
    long_line = "- " + " ".join("Word%d." % n for n in range(400))
    company = "\n".join("- Fact %d about the company, with its source." % n for n in range(60))
    text = ("# Prep\n\n## The company\n\n%s\n%s\n\n## Notes\n\n- The very last line.\n"
            % (company, long_line))
    got = interview_pack.reading(text, CO)
    sec = next(s for s in got["sections"] if s["title"] == "About " + CO)
    assert len(sec["items"]) == 61 and sec["items"][-1]["text"].endswith("Word399.")
    assert any(i["text"] == "The very last line." for s in got["sections"] for i in s["items"])


def test_a_brief_line_about_a_person_at_an_employer_opens_them_not_the_application(where):
    """A person's copy (2026-11-05): "Follow up with Wren at Larkspur Retail" opened the
    application in Jobs, since the line names the employer and not her full name. A first name
    of someone there, said in the line, is who it is about: it opens her in Contacts."""
    ctx = types.SimpleNamespace(tracker=[dict(_row(), company="Larkspur Retail")],
                                contacts=[{"company": "Larkspur Retail", "contact_id": "larkspur_halloway",
                                           "name": "Wren Halloway"},
                                          {"company": "Fernhill Freight", "contact_id": "fernhill_vale",
                                           "name": "Robin Vale"}])
    assert app_model.brief_link(ctx, "Follow up with Wren at Larkspur Retail: drafted for you.") == \
        {"item": "larkspur_halloway", "section": "people"}
    # Someone else's first name, or nobody's, still opens the employer's application.
    assert app_model.brief_link(ctx, "Robin wrote about Larkspur Retail")["item"] == \
        app_model.tracker_ids(ctx.tracker)[0]
    assert app_model.brief_link(ctx, "Larkspur Retail is live")["section"] == "applications"
