"""Every rule that holds anything back says when it ends, or why it never does, and how to
lift it; and missing data never makes one hold for ever by accident (T12).

An employer was shut for 45 days whenever two people there were waiting on a reply: a number
nobody chose, counted from the first note however recent the follow-up, and a note with no
date held its employer for ever. Nothing on the page said so, or when it would open (the
maintainer, 2026-11-09). Now:

- someone waiting holds their employer by the person's own follow-up rule, from the last
  contact (`reading.waiting_until`), or by their own EMPLOYER_WAIT_DAYS; with no date at all
  they hold nothing;
- `tools/holds.py` lists every rule (`RULES`) and what is held back today (`live`), each one
  plain line with its day or reason and its override, drawn under Settings, Your rules;
- a do-not-target entry with no review day, an application with no date and a hold with a
  day beside it no longer hold for ever.

Made-up people only: a nurse in Vancouver, a remote software engineer and a career changer
with no laptop, each with their own follow-up rule.
"""
from __future__ import annotations

import ast
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
import holds  # noqa: E402

TODAY = dt.date(2026, 11, 9)
JARGON = re.compile(r"\b(?:config|repository|branch|cli|environment|proxy|\w+\.(?:py|json|csv|md))\b",
                    re.I)


# ------------------------------------------------------------------ the table

def _defined(path: str, name: str) -> bool:
    full = os.path.join(ROOT, path)
    src = open(full, encoding="utf-8").read()
    if path.endswith(".js"):
        return re.search(r"\bfunction\s+" + re.escape(name) + r"\b", src) is not None
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            return True
        targets = (node.targets if isinstance(node, ast.Assign) else
                   [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return True
    return False


@pytest.mark.parametrize("rule", holds.RULES, ids=[r["id"] for r in holds.RULES])
def test_every_rule_names_where_it_lives_and_it_is_there(rule):
    assert rule["where"], rule["id"]
    for w in rule["where"]:
        path, name = w.split(":")
        assert _defined(path, name), f"{rule['id']}: {w} is not defined"


@pytest.mark.parametrize("rule", holds.rules(), ids=[r["id"] for r in holds.RULES])
def test_every_rule_says_when_it_ends_or_why_it_stays_and_how_to_lift_it(rule):
    assert rule["area"] in holds.AREAS
    assert bool(rule["ends"]) != bool(rule["why"]), \
        f"{rule['id']}: one of when it ends, or why it never does"
    for k in ("override", "missing", "shown", "line"):
        assert rule[k].strip(), (rule["id"], k)
    assert rule["override"][:1].upper() + rule["override"][1:] in rule["line"]
    assert not JARGON.search(rule["line"]), rule["line"]
    assert "{" not in rule["line"], rule["line"]


ENGINE_WORDS = re.compile(r"<\w+>|No thanks|InMail|business days|kept, as\b")


@pytest.mark.parametrize("rule", holds.rules(), ids=[r["id"] for r in holds.RULES])
def test_every_rule_is_said_in_the_persons_words(rule):
    """The screen review (2026-11-09): "How every rule ends" read "say 'more at <employer>'",
    "after three No thanks", "InMail", "6 business days" and "kept, as your own window"."""
    for k in ("line", "name", "override"):
        assert not ENGINE_WORDS.search(rule[k]), (rule["id"], k, rule[k])


def test_the_ids_are_one_each():
    ids = [r["id"] for r in holds.RULES]
    assert len(ids) == len(set(ids))


# ------------------------------------------------------------------ missing data, rule by rule

@pytest.fixture
def example(tmp_path, monkeypatch):
    """The example person's profile and an empty state of the test's own."""
    state = tmp_path / "state"
    (state / "job_scraper").mkdir(parents=True)
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    monkeypatch.setenv("LJS_STATE", str(state))
    return state


def _job_age(_s):
    import prefilter
    kept, why = prefilter.decide({"title": "Supply Chain Analyst", "company": "Fernhill Freight",
                                  "location": "Manchester, England, United Kingdom"}, TODAY)
    assert not why.startswith("age"), why


def _gates(_s):
    import text_screen
    assert text_screen.eligibility_cut("") is None
    assert text_screen.residence_cut("") is None


def _sectors(_s):
    import surface
    assert surface.turned_down("") == ""


def _judged_none(_s):
    import bar
    assert bar.judged_none_until({"verdict": "none", "why": "small"}) is None
    assert bar.judged_none_until({"verdict": "none", "date": "2026-11-01"}) > TODAY


def _declined(_s):
    import run_round
    assert run_round.declined_now() == {}     # the example person turned nobody down


def _dismissed(_s):
    import exclude
    # A role set aside with no day holds nothing; one with a day ends, unless their words
    # said for good.
    assert exclude.set_aside_until({"exclusion_reason": "the pay"}) == dt.date.min
    assert exclude.set_aside_until({"exclusion_reason": "the pay",
                                    "excluded_date": "2026-11-01"}) > TODAY
    assert exclude.set_aside_until({"exclusion_reason": "never again",
                                    "excluded_date": "2026-11-01"}) is None


def _job_left_out(_s):
    import exclude
    import throttle
    # A draft a chat stopped with no day holds nothing; with one it ends, even where its words
    # say never (they are the chat's); and it holds that posting alone, never the role.
    stop = {"exclusion_reason": "never one they can take", "basis": "person", "by": exclude.CHAT,
            "title": "Pricing Analyst", "company": "Fernway Insurance"}
    assert exclude.set_aside_until(stop) == dt.date.min
    assert exclude.set_aside_until(dict(stop, excluded_date="2026-11-01")) > TODAY
    assert throttle.entry_pair(stop) is None


def _ruled_out(_s):
    import throttle
    # A score is never a verdict; with no reason at all, only that one posting is held.
    assert throttle.is_stale_exclusion("scored 41, below the 60 pass bar")


def _duplicates(_s):
    import throttle
    assert throttle._posting_key("", "", "")[0] == ""


def _no_team(state):
    import throttle
    import discovery
    assert throttle.do_not_target_until({"reason": "only a sales office"}) == ""
    assert throttle.do_not_target_until({"recorded": "2026-08-01"}) == "2026-10-30"
    path = state / "job_scraper" / "do_not_target.json"
    path.write_text(json.dumps({"companies": {"Quenby Freight": {"reason": "only sales"},
                                              "Tarnwick Mills": {"recorded": "2026-10-01"}}}))
    got = throttle.load_do_not_target(str(path), TODAY.isoformat())
    assert list(got) == ["tarnwick mills"], got
    assert throttle.expired_do_not_target(str(path), TODAY.isoformat()) == ["Quenby Freight"]
    assert not discovery.presence_blocks({"verdict": "no_relevant_presence"}, TODAY)


def _application_open(_s):
    import throttle
    rows = [{"company": "Hollowmere Foods", "status": "applied"},
            {"company": "Brindle Hart", "status": "interview"}]
    got = throttle.open_applications(rows=rows, today=TODAY)
    assert list(got) == ["brindle hart"], got   # an interview holds while it runs


def _referral(_s):
    import throttle
    assert throttle.referral_holds(rows=[]) == {}


def _application_nudges(_s):
    import followups
    assert followups.MAX_NUDGES >= 1


def _employer_wait(_s):
    import reading
    assert reading.waiting_until({}, []) is None
    row = {"contact_id": "k1", "name": "Ada Example", "company": "Kestrel Mutual",
           "status": "awaiting_reply"}
    waiting, _ = reading.at_employer("Kestrel Mutual", [row, dict(row, contact_id="k2")],
                                     today=TODAY, threads=[])
    assert waiting == []
    # The row's own follow-up day, where nothing else is dated: one wait after it.
    assert reading.waiting_until({"next_action_due": "2026-11-02"}, []) > dt.date(2026, 11, 2)


def _limit(_s):
    import state
    msgs = [{"contact_id": "a", "direction": "outbound", "channel": "linkedin", "summary": "note",
             "full_text": "Hello there"},
            {"contact_id": "a", "direction": "outbound", "channel": "linkedin", "summary": "nudge",
             "full_text": "Following up"}]
    assert state.at_limit({"contact_id": "a", "status": "awaiting_reply"}, msgs, "awaiting_reply")


def _closed(_s):
    import state
    assert "" not in state.CLOSED and "awaiting_reply" not in state.CLOSED


def _people_turned_down(_s):
    import surface
    assert surface.turned_down("Some Agency Ltd", agency=True) == ""


def _place(_s):
    import surface
    assert surface.outside_market("") == ""


def _person_hold(_s):
    import state
    assert state.action_hold("Hold: waiting for them to be back", TODAY) == "on hold, no end date"
    # The row's day ends only a bare hold: one that names a condition stays held, however old
    # the row's follow-up day (a stale day lifted "Hold until she replies" at once).
    assert state.action_hold("HOLD", TODAY, "2026-11-01") == ""
    assert state.action_hold("Frozen.", TODAY, "2026-12-01").startswith("on hold until")
    assert state.action_hold("Hold until she replies", TODAY, "2026-11-01") == \
        "on hold, no end date"
    assert state.action_hold("Hold: waiting for them to be back", TODAY, "2026-11-01")
    got = holds._person_holds(TODAY, [{"name": "Ada Example", "next_action":
                                       "Hold until she replies", "next_action_due": "2026-11-01"}])
    assert got and "no end day" in got[0]["line"]
    assert state.action_hold("Hold until 2026-12-01", TODAY).startswith("on hold until")
    got = holds._person_holds(TODAY, [{"name": "Ada Example", "next_action": "Hold"}])
    assert got and "no end day" in got[0]["line"] and got[0]["say"] == "write to Ada again"


def _request(_s):
    import state
    assert state.request_pending([]) is None


def _written_to(_s):
    import surface
    got = surface.check({}, {"contacts": [], "threads": {}, "today": TODAY})
    assert got["show"] is False and got["reason"]


def _inmail(_s):
    import state
    b = state.platform_budget([], [], TODAY)
    assert b["inmails_left"] == b["inmails_limit"]


def _invitations(_s):
    import schema
    assert "connections_per_week" not in schema.LIMITS


def _reading_stop(_s):
    import reading
    assert reading.stopped(TODAY) == ""


def _follow_up(_s):
    import state
    assert state.follow_up_due({}, [])[1] is None


def _put_off(_s):
    import inspect
    import app_actions
    # No day given is tomorrow, never "until further notice".
    assert 'r.words("until") or (r.day + dt.timedelta(days=1))' in \
        inspect.getsource(app_actions._due_snooze)


def _note_aside(_s):
    import app_actions
    import state
    assert app_actions.ACTIONS["msg.skip"][2] == "msg.unskip"
    # One set aside with no day (in a chat, or "never") has no end of its own, and is not held
    # back for now: it is set aside until brought back. One with a day ends on it.
    assert state.dropped_until({"outcome": "dropped 2026-11-01: moved on"}) is None
    assert state.dropped_until({"outcome": "dropped 2026-11-01 until 2027-05-02: not now"}) == \
        dt.date(2027, 5, 2)


def _interview_quiet(_s):
    import throttle
    assert not throttle.is_silent({"status": "interview"}, TODAY)


def _prep(_s):
    import open_actions
    assert open_actions.PREP_WINDOW_DAYS > 0 and open_actions.THANKS_DAYS > 0


def _todo_hidden(_s):
    src = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    body = src[src.index("function hideTodo("):][:600]
    assert re.search(r"now\(\) \+ 7 \* DAY", body), body


def _ideas_paused(_s):
    import app_alerts
    no = {f"s{i}": {"kind": "warm"} for i in range(5)}
    assert app_alerts.paused(TODAY, no) == {}


def _idea_declined(_s):
    import app_actions
    assert "suggest.undismiss" in app_actions.ACTIONS


def _brief_paused(state):
    import routines
    with pytest.raises(ValueError):
        routines.pause("", TODAY.isoformat(), path=str(state / "routines.json"))


def _news_seen(_s):
    import brief
    assert brief.NEWS_MAX > 0


def _export_later(_s):
    import export
    assert export.due(TODAY, threads=[]) == ""     # never taken: the first is asked for elsewhere


def _update_questions(_s):
    import profile_upgrades
    assert "networking.EMPLOYER_WAIT_DAYS" in profile_upgrades.SAFE_DEFAULTS


MISSING = {"job_age": _job_age, "gates": _gates, "sectors": _sectors, "judged_none": _judged_none, "declined": _declined,
           "dismissed": _dismissed, "job_left_out": _job_left_out, "ruled_out": _ruled_out, "duplicates": _duplicates,
           "no_team": _no_team, "application_open": _application_open, "referral": _referral,
           "application_nudges": _application_nudges, "employer_wait": _employer_wait,
           "limit": _limit, "closed": _closed, "people_turned_down": _people_turned_down,
           "place": _place, "person_hold": _person_hold, "request": _request,
           "written_to": _written_to, "inmail": _inmail, "invitations": _invitations,
           "reading_stop": _reading_stop, "follow_up": _follow_up, "put_off": _put_off,
           "note_aside": _note_aside, "interview_quiet": _interview_quiet, "prep": _prep,
           "todo_hidden": _todo_hidden, "ideas_paused": _ideas_paused,
           "idea_declined": _idea_declined, "brief_paused": _brief_paused,
           "news_seen": _news_seen, "export_later": _export_later,
           "update_questions": _update_questions}


def test_every_rule_has_a_missing_data_test():
    assert set(MISSING) == {r["id"] for r in holds.RULES}


@pytest.mark.parametrize("rid", sorted(MISSING))
def test_missing_data_never_holds_for_ever_by_accident(rid, example):
    MISSING[rid](example)


# ------------------------------------------------------------------ the clock and the window

def test_the_window_follows_the_follow_up_rule_from_the_last_contact(monkeypatch):
    import reading
    import schema
    monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", 14)
    monkeypatch.setattr(schema, "MAX_UNANSWERED", 2)
    monkeypatch.setattr(schema, "MAX_NUDGES", 1)
    first = {"contact_id": "a", "first_contacted": "2026-10-01", "status": "awaiting_reply"}
    # One note: once its follow-up is due (14 days), the employer is free. Waiting for every
    # message the limit allows held big employers about four weeks (2026-11-10).
    assert reading.waiting_until(first, [], wait_days=None) == dt.date(2026, 10, 15)
    note = {"contact_id": "a", "date": "2026-10-01", "direction": "outbound",
            "channel": "linkedin", "summary": "note", "full_text": "Hello"}
    nudge = dict(note, date="2026-10-20", summary="nudge", full_text="Following up")
    # The follow-up went late, on the 20th: the clock runs from it, one wait more.
    assert reading.waiting_until(first, [note, nudge], wait_days=None) == dt.date(2026, 11, 3)
    # Their own number of days, from the last contact.
    assert reading.waiting_until(first, [note, nudge], wait_days=10) == dt.date(2026, 10, 30)


def test_a_request_nobody_accepted_stops_holding_once_it_is_one_to_withdraw(monkeypatch):
    import reading
    import schema
    import state
    monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", 14)
    row = {"contact_id": "r", "status": "awaiting_reply", "company": "Wrenfield Labs"}
    request = {"contact_id": "r", "date": "2026-10-01", "direction": "outbound",
               "channel": "linkedin", "summary": "connection request", "full_text": "Hi there",
               "scenario": "connection_request"}
    assert state.request_pending([request]) == dt.date(2026, 10, 1)
    # A person's own long wait still lets a request go once it is worth withdrawing.
    assert reading.waiting_until(row, [request], wait_days=45) == dt.date(2026, 10, 22)
    assert reading.waiting_until(row, [request], wait_days=None) == dt.date(2026, 10, 15)
    # Three weeks on, nobody at the employer is counted as waiting.
    waiting, _ = reading.at_employer("Wrenfield Labs", [row], today=dt.date(2026, 10, 23),
                                     threads=[request])
    assert waiting == []


def test_a_thread_silent_for_months_is_closed_as_gone_cold_and_a_reply_opens_it():
    import state
    today = dt.date(2026, 11, 10)
    old = {"contact_id": "g1", "name": "Ottilie Brack", "company": "Harrowgate Software",
           "status": "awaiting_reply", "first_contacted": "2023-05-02"}
    recent = dict(old, contact_id="g2", name="Joss Penhale", first_contacted="2026-10-30")
    theirs = dict(old, contact_id="g3", name="Rafe Mallory",
                  next_action="Ask again after her product launch", next_action_due="2027-01-10")
    rows = [{"contact_id": c, "date": d, "direction": "outbound", "channel": "linkedin",
             "summary": "message", "full_text": "Hello"}
            for c, d in (("g1", "2023-05-02"), ("g2", "2026-10-30"), ("g3", "2026-03-01"))]
    contacts = [old, recent, theirs]
    said = state.write_follow_ups(contacts, rows, today)
    assert old["status"] == "gone_cold" and not old.get("next_action_due")
    assert "gone cold 2026-11-10" in old["outcome"] and "closed by itself" in old["outcome"]
    assert any("Ottilie Brack" in x and "gone cold" in x for x in said)
    assert recent["status"] == "awaiting_reply"
    assert theirs["status"] == "awaiting_reply"          # a date of their own, still ahead
    # Recorded once: a second run changes nothing.
    assert not any("gone cold" in x for x in state.write_follow_ups(contacts, rows, today))
    # Reversible: a reply from them opens it again by itself.
    rows.append({"contact_id": "g1", "date": "2026-11-12", "direction": "inbound",
                 "channel": "linkedin", "summary": "reply", "full_text": "Sorry, only saw this"})
    mine = [r for r in rows if r["contact_id"] == "g1"]
    assert state.effective_status(old, mine) == "replied_needs_response"
    # Their own number of days.
    again = dict(recent, contact_id="g4", status="awaiting_reply", outcome="")
    assert state.close_gone_cold([again], [dict(rows[1], contact_id="g4")], today, days=5)
    assert again["status"] == "gone_cold"


# ------------------------------------------------------------------ T12, with made-up people

PEOPLE = {
    "nurse": {"name": "Priya Okafor", "city": "Vancouver",
              "networking": "FOLLOW_UP_DAYS = 14\nMAX_UNANSWERED = 2\n",
              "employer": "Larchmont Health", "opens": "2026-11-13",
              "why": "2 people there are"},
    "engineer": {"name": "Tomas Ferreira", "city": "Remote",
                 "networking": "EMPLOYER_WAIT_DAYS = 10\nPEOPLE_PER_EMPLOYER = 1\n",
                 "employer": "Quillfeather Software", "opens": "2026-11-12",
                 "why": "1 person there is"},
    "changer": {"name": "Dana Whitlock", "city": "Leeds", "networking": "",
                "employer": "Brackenridge Trust", "opens": None},
}


def _write_csv(path, rows, columns):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def _made_up(tmp_path, who: str) -> dict:
    import schema
    p = PEOPLE[who]
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(prof, "networking.py"), "a", encoding="utf-8") as fh:
        fh.write(f"\n# {p['name']}, a made-up person in {p['city']}\n" + p["networking"])
    st = tmp_path / "state"
    (st / "job_scraper").mkdir(parents=True)
    emp = p["employer"]
    contacts = [
        {"contact_id": "w1", "name": "Ines Harrow", "company": emp, "status": "awaiting_reply",
         "first_contacted": "2026-10-30"},
        {"contact_id": "w2", "name": "Bram Ostler", "company": emp, "status": "awaiting_reply",
         "first_contacted": "2026-11-02"},
        {"contact_id": "h1", "name": "Celia Marsh", "company": "Ashgrove Partners",
         "status": "in_conversation", "next_action": "Hold: back after her leave"},
    ]
    threads = [{"contact_id": "w1", "date": "2026-10-30", "direction": "outbound",
                "channel": "linkedin", "summary": "first note", "full_text": "Hello"},
               {"contact_id": "w2", "date": "2026-11-02", "direction": "outbound",
                "channel": "linkedin", "summary": "first note", "full_text": "Hello"},
               {"contact_id": "h1", "date": "2026-10-20", "direction": "inbound",
                "channel": "linkedin", "summary": "reply", "full_text": "Back in a while"},
               {"contact_id": "h1", "date": "2026-10-21", "direction": "outbound",
                "channel": "linkedin", "summary": "answer", "full_text": "Thanks"}]
    _write_csv(st / "network_contacts.csv", contacts, schema.CONTACT_COLUMNS)
    _write_csv(st / "network_threads.csv", threads, schema.THREAD_COLUMNS)
    _write_csv(st / "job_search_tracker.csv",
               [{"date": "2026-10-20", "company": "Fallowmere Clinic", "role": "Role",
                 "status": "applied", "applied_on": "2026-10-20"}],
               ["date", "company", "sector", "role", "role_type", "channel", "status",
                "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
                "source", "deadline", "applied_on"])
    (st / "job_scraper" / "do_not_target.json").write_text(json.dumps(
        {"companies": {"Ridley Assurance": {"reason": "only a sales office here",
                                            "recorded": "2026-10-01"}}}))
    (st / "job_scraper" / "seen_jobs.json").write_text(json.dumps({"seen": {}}))
    env = dict(os.environ, LJS_PROFILE=prof, LJS_STATE=str(st), LJS_COPY="private")
    env.pop("CLAUDE_CODE_REMOTE", None)
    return env


def _holds(env, *more):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "--json",
                        "--today", TODAY.isoformat(), *more], env=env, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout)


@pytest.mark.parametrize("who", sorted(PEOPLE))
def test_t12_every_hold_shows_its_end_or_reason_and_its_override_for_a_made_up_person(
        who, tmp_path):
    p = PEOPLE[who]
    env = _made_up(tmp_path, who)
    every = _holds(env, "--rules")
    assert [r["id"] for r in every] == [r["id"] for r in holds.RULES]
    for r in every:
        assert (r["ends"] or r["why"]) and r["override"][1:] in r["line"], r
    live = {h["rule"] + ":" + h["what"]: h for h in _holds(env)}
    emp = p["employer"]
    if p["opens"]:
        h = live[f"employer_wait:{emp}"]
        d = dt.date.fromisoformat(p["opens"])
        assert h["until"] == p["opens"], h
        # Why it is held, then the day, and nothing after it: the page's pill lifts it.
        assert h["line"] == (f"{emp}: {p['why']} waiting on a reply, so it opens again "
                             f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"), h["line"]
        assert h["say"] == f"more at {emp}" and h["lift"] == "Open it now", h
    else:
        # The app's own rule: six business days. The note of 30 October had its follow-up
        # due on the 9th, so only one person still waits, under the app's two: nothing held.
        assert f"employer_wait:{emp}" not in live
    app = live["application_open:Fallowmere Clinic"]
    assert app["until"] == "2026-12-04" and app["say"] == "stop waiting on Fallowmere Clinic"
    team = live["no_team:Ridley Assurance"]
    assert team["until"] == "2026-12-30" and team["say"] == "look at Ridley Assurance again"
    hold = live["person_hold:Celia Marsh"]
    assert hold["until"] is None and hold["say"] == "write to Celia again"
    for h in live.values():
        assert not JARGON.search(h["line"]), h["line"]
        assert "Morgan" not in h["line"]
        assert "or say" not in h["line"] and (h["lift"] or not h["say"] or h["rule"] == "inmail"), h


def test_t12_the_page_model_carries_every_rule_and_what_is_held(tmp_path):
    env = _made_up(tmp_path, "nurse")
    out = tmp_path / "model.json"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now",
                        "2026-11-09T09:30:00Z", "--out", str(out)], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-1500:]
    rules = json.loads(out.read_text(encoding="utf-8"))["rules"]
    # Every rule that can hold anything for this person: one about a bar of pay, prestige or
    # signal is not listed for someone whose profile has none (the screen review, 2026-11-11).
    assert [x["id"] for x in rules["every_hold"]] == [r["id"] for r in holds.RULES if r["id"] != "judged_none"]
    lines = [h["line"] for h in rules["held"]]
    assert any(x.startswith("Larchmont Health: 2 people there are waiting on a reply, so it opens again ") for x in lines), lines
    assert any(h["say"] == "more at Larchmont Health" and h["lift"] for h in rules["held"])


def test_a_thread_the_follow_up_rule_closed_never_holds_its_employer(monkeypatch):
    """Two unanswered messages from us close a thread (state.at_limit), yet it still counted
    towards its employer's limit, holding the next person there until somebody replied (the
    maintainer, 2026-11-10)."""
    import reading
    import schema
    monkeypatch.setattr(schema, "FOLLOW_UP_DAYS", 14)
    monkeypatch.setattr(schema, "MAX_UNANSWERED", 2)
    today = dt.date(2026, 10, 20)
    row = {"contact_id": "a", "name": "Ada Example", "company": "Harbourline Insurance",
           "status": "awaiting_reply", "first_contacted": "2026-10-10"}
    note = {"contact_id": "a", "date": "2026-10-10", "direction": "outbound",
            "channel": "linkedin", "summary": "note", "full_text": "Hello"}
    nudge = dict(note, date="2026-10-19", summary="nudge", full_text="Following up")
    # One note, unanswered: it holds the employer until its follow-up is due.
    waiting, _ = reading.at_employer("Harbourline Insurance", [row], today=today, threads=[note])
    assert [c["contact_id"] for c in waiting] == ["a"]
    # Two unanswered: closed by the rule, so it holds nothing.
    waiting, _ = reading.at_employer("Harbourline Insurance", [row], today=today, threads=[note, nudge])
    assert waiting == []


@pytest.mark.parametrize("shift", [-1, 0, 1], ids=["person-behind", "same-day", "person-ahead"])
def test_a_reading_stop_holds_on_the_day_it_was_written_whatever_the_persons_day(tmp_path, monkeypatch, shift):
    """A stop is written on the computer's day; Held back asked for it on the person's day, so
    a person a day ahead of their computer (or behind it) saw no stop while reads were stopped."""
    import reading
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath("repo", *p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    machine = dt.date.today()
    reading._write_stop("LinkedIn showed a security check")
    got = holds._reading(machine + dt.timedelta(days=shift))
    assert [h["rule"] for h in got] == ["reading_stop"], got
    # The day it ends is the computer's next midnight in the person's zone, not the day after
    # the later of the two days, which said a day late on a computer ahead of the person
    # (R1-8): the test below sets both zones.


@pytest.mark.parametrize("machine, home, until, words", [
    # The computer a day ahead of the person: its midnight is 11:00 the next morning in London.
    ("Pacific/Auckland", "Europe/London", "2026-11-11", "starts again Wed 11 Nov by itself"),
    # The computer behind: its midnight is 08:00 the next morning in London.
    ("America/Los_Angeles", "Europe/London", "2026-11-11", "starts again Wed 11 Nov by itself"),
    # The computer behind a person far ahead: its midnight is 21:00 the person's same day.
    ("America/Los_Angeles", "Pacific/Auckland", "2026-11-11", "starts again later today by itself"),
], ids=["computer-ahead", "computer-behind", "later-the-same-day"])
def test_a_reading_stop_says_the_persons_day_for_the_computers_next_midnight(
        tmp_path, monkeypatch, machine, home, until, words):
    """R1-8 (independent review, 2026-11-10): a stop is kept on the computer's day and ends at
    the computer's next midnight, yet Held back said the day after the later of the computer's
    day and the person's: on a computer in Auckland, a person in London on Tuesday night was
    told reads start again Thursday, when they start at 11:00 on Wednesday."""
    import time
    import zoneinfo
    import reading
    if not hasattr(time, "tzset"):
        pytest.skip("the computer's own zone is set with time.tzset, which Windows has not; "
                    "the rule is the same there and is tested on Linux and the Mac")
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath("repo", *p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(holds.person, "home_zone", lambda: zoneinfo.ZoneInfo(home))
    monkeypatch.setenv("TZ", machine)
    time.tzset()
    try:
        now = dt.datetime(2026, 11, 10, 23, 22, tzinfo=dt.timezone.utc)
        reading._write_stop("LinkedIn showed a security check",
                            now=now.astimezone().replace(tzinfo=None))
        got = holds._reading(now.astimezone(zoneinfo.ZoneInfo(home)).date(), now=now)
    finally:
        monkeypatch.undo()
        time.tzset()
    assert [h["until"] for h in got] == [until], got
    assert got[0]["line"].endswith(words), got[0]["line"]


# ------------------------------------------------------------------ a judgement of "none"

def test_a_judgement_that_an_employer_clears_none_is_looked_at_again(tmp_path, monkeypatch):
    """A chat's judgement that an employer clears none of pay, prestige or signal (`bar.py
    judge ... none`) cut every job there and hid everyone there, new people and follow-ups
    alike, for good: it had no day of its own, nothing on the page said so, and a company that
    raised money or opened a team since stayed out. It is the chat's reading of that day, so
    it is read for bar.JUDGED_NONE_DAYS and then judged again; one with no day is judged again
    now; and Held back for now says it, with the day and a way to lift it. A judgement that
    an employer clears the bar never shuts anything, so it keeps."""
    time_machine = pytest.importorskip("time_machine")   # the CI installs it
    import bar
    import opportunity
    import run_round
    from network import surface
    f = tmp_path / "employers_judged.json"
    monkeypatch.setattr(bar, "_judged_path", lambda: str(f))
    monkeypatch.setattr(opportunity, "TIER_1", {"brindlecombe holdings"})   # a bar is stated
    bar._judged_cache.clear()
    utc = dt.timezone.utc
    try:
        bar.judge("Wrenfield Labs", bar.NONE, "a two-person studio", today="2026-08-01")
        bar.judge("Ashcombe Analytics", bar.SIGNAL, "backed by a top fund", today="2026-08-01")
        with time_machine.travel(dt.datetime(2026, 9, 1, 12, tzinfo=utc), tick=False):
            assert bar.verdict("Wrenfield Labs")[1].startswith("judged 2026-08-01")
            assert run_round.judged_none("Wrenfield Labs")
            assert "clears none" in surface.employer_out("Wrenfield Labs")
            got = [h for h in holds.live(dt.date(2026, 9, 1), [], [])
                   if h["rule"] == "judged_none"]
            until = (dt.date(2026, 8, 1) + dt.timedelta(days=bar.JUDGED_NONE_DAYS)).isoformat()
            assert [(h["what"], h["until"]) for h in got] == [("Wrenfield Labs", until)], got
            assert got[0]["say"] == "judge Wrenfield Labs again" and got[0]["lift"], got
            assert not JARGON.search(got[0]["line"]), got[0]["line"]
        with time_machine.travel(dt.datetime(2026, 11, 10, 12, tzinfo=utc), tick=False):
            # Past its day: judged again before anything is cut or hidden for it.
            assert bar.judgement("Wrenfield Labs") is None
            assert run_round.judged_none("Wrenfield Labs") == ""
            assert "not judged against your bar yet" in surface.employer_out("Wrenfield Labs")
            assert not [h for h in holds.live(dt.date(2026, 11, 10), [], [])
                        if h["rule"] == "judged_none"]
            # One that clears the bar holds nothing back, and keeps.
            assert bar.verdict("Ashcombe Analytics")[0] == bar.SIGNAL
        # A "none" with no day was never dated: it is judged again now, never kept for good.
        f.write_text(json.dumps({"quenby works": {"name": "Quenby Works", "verdict": "none",
                                                  "why": "small"}}), encoding="utf-8")
        bar._judged_cache.clear()
        assert bar.judgement("Quenby Works") is None
        assert run_round.judged_none("Quenby Works") == ""
    finally:
        bar._judged_cache.clear()


def test_a_finding_of_no_team_from_a_people_search_is_held_back_with_its_day(example):
    """A people search that finds no team for the person at an employer keeps that finding
    beside the employer's research, dated, and nobody there is shown until its review day
    (discovery.presence_blocks). The rule says it is under Held back for now, yet only the
    search's own list was read there, so it held people back with nothing on the page saying
    so, or when, or how to look again."""
    import discovery
    rec = discovery.presence_record("no_relevant_presence", dt.date(2026, 10, 1))
    research = example / "company_research"
    research.mkdir()
    (research / "harrowgate-software.json").write_text(json.dumps(
        {"company": "Harrowgate Software", "network_presence": rec}), encoding="utf-8")
    (research / "tarnwick-mills.json").write_text(json.dumps(       # past its day: nothing
        {"company": "Tarnwick Mills", "network_presence": discovery.presence_record(
            "no_relevant_presence", dt.date(2026, 6, 1))}), encoding="utf-8")
    (research / "_hosts.json").write_text(json.dumps({"hosts": {}}), encoding="utf-8")
    got = [h for h in holds.live(TODAY, [], []) if h["rule"] == "no_team"]
    assert [(h["what"], h["until"]) for h in got] == [("Harrowgate Software",
                                                       rec["review_after"])], got
    assert got[0]["say"] == "look at Harrowgate Software again" and got[0]["lift"], got
    assert not JARGON.search(got[0]["line"]), got[0]["line"]


def test_no_team_said_twice_is_one_hold_and_look_again_lifts_both(tmp_path):
    """An employer on the search's own list of no team (do_not_target.json) that a people search
    also found no team at was two holds with one id: the page showed one, Look again now lifted
    that one, and the employer came straight back with the other's later day. A country's own
    research file (<key>--<cc>.json), which the people search never reads, was listed too."""
    import discovery
    env = _made_up(tmp_path, "nurse")
    research = tmp_path / "state" / "company_research"
    research.mkdir()
    rec = discovery.presence_record("no_relevant_presence", dt.date(2026, 11, 1))
    (research / "ridley-assurance.json").write_text(json.dumps(
        {"company": "Ridley Assurance", "network_presence": rec}), encoding="utf-8")
    (research / "tarnwick-mills--ca.json").write_text(json.dumps(
        {"company": "Tarnwick Mills", "network_presence": rec}), encoding="utf-8")
    teams = [h for h in _holds(env) if h["rule"] == "no_team"]
    assert [(h["what"], h["until"], h["sources"]) for h in teams] == [
        ("Ridley Assurance", rec["review_after"], ["people", "search"])], teams
    assert rec["review_after"] > "2026-12-30"                 # the later of the two days
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        teams[0]["id"], "--said", "look at Ridley Assurance again", "--today",
                        TODAY.isoformat()], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    assert not [h for h in _holds(env) if h["rule"] == "no_team"]
    kept = json.loads((research / "ridley-assurance.json").read_text(encoding="utf-8"))
    assert kept["network_presence"]["looked_again_because"] == "look at Ridley Assurance again"


def test_a_check_that_found_nobody_who_fits_is_held_back_and_searched_again_on_a_tap(tmp_path):
    """A check of who works at an employer that found nobody who fits in the place is kept
    (documents/network/.people_seen.json) and the employer skipped for EMPTY_DAYS
    (candidates.order): a finding of no team that ended by itself, but was not under Held back
    for now and had no way to search again sooner."""
    import candidates
    env = _made_up(tmp_path, "nurse")
    seen = tmp_path / "state" / "documents" / "network" / ".people_seen.json"
    r = subprocess.run([sys.executable, "-c", (
        "import sys, datetime as d; sys.path[:0] = ['tools', 'tools/network']; import candidates;"
        "candidates.record_seen({'Harrowgate Software': (6, 0), 'Tarnwick Mills': (4, 2)},"
        " 'Vancouver', d.date(2026, 11, 1));"
        "candidates.record_seen({'Quenby Works': (3, 0)}, 'Vancouver', d.date(2026, 9, 1))")],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and seen.exists(), r.stderr[-800:]
    teams = {h["what"]: h for h in _holds(env) if h["rule"] == "no_team"}
    again = dt.date(2026, 11, 1) + dt.timedelta(days=candidates.EMPTY_DAYS)
    h = teams["Harrowgate Software"]
    assert (h["until"], h["sources"], h["lift"]) == (again.isoformat(), ["check"],
                                                     "Look again now"), h
    assert "nobody who fits in Vancouver" in h["line"] and not JARGON.search(h["line"]), h
    assert "Tarnwick Mills" not in teams and "Quenby Works" not in teams     # fit, or past
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift", h["id"],
                        "--said", h["say"], "--today", TODAY.isoformat()], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    assert "Harrowgate Software" not in {x["what"] for x in _holds(env) if x["rule"] == "no_team"}
    kept = json.loads(seen.read_text(encoding="utf-8"))
    assert [r["employer"] for p in kept.values() for r in p.values()] == [
        "Quenby Works", "Tarnwick Mills"], kept                  # what fit, and what is past


def test_only_research_holding_a_finding_is_parsed_for_held_back(example, monkeypatch):
    """Every page build read every employer's research file in full to find the few holding a
    people search's finding of no team. Only a file whose text holds one is parsed now."""
    import discovery
    research = example / "company_research"
    research.mkdir()
    rec = discovery.presence_record("no_relevant_presence", dt.date(2026, 11, 1))
    (research / "harrowgate-software.json").write_text(json.dumps(
        {"company": "Harrowgate Software", "network_presence": rec}), encoding="utf-8")
    for n in range(5):
        (research / f"employer-{n}.json").write_text(json.dumps(
            {"company": f"Employer {n}", "facts": ["a long page of research"] * 50}),
            encoding="utf-8")
    parsed = []
    real_load, real_loads = json.load, json.loads
    monkeypatch.setattr(holds.json, "load", lambda fh, **k: parsed.append(1) or real_load(fh, **k))
    monkeypatch.setattr(holds.json, "loads", lambda t, **k: parsed.append(1) or real_loads(t, **k))
    got = holds._no_team_found(TODAY)
    monkeypatch.undo()
    assert got == [("Harrowgate Software", dt.date.fromisoformat(rec["review_after"]))]
    assert len(parsed) == 1, parsed


# ------------------------------------------------------------------ a pill lifts its hold

def test_every_pill_under_held_back_lifts_its_hold_and_keeps_what_was_said(tmp_path):
    """Each line under Held back for now carries a pill that sends its words to Claude ("more at
    Larchmont Health", "show me ideas again"), but nothing said what Claude does with them, and
    for some there was nothing to run at all: the ideas' pause could only be waited out, and a
    judgement or a finding of no team could only be edited by hand. `holds.py lift "<words>"`
    lifts the one hold the words name, the way its rule is lifted, and keeps the words."""
    env = _made_up(tmp_path, "nurse")
    prof, st = env["LJS_PROFILE"], tmp_path / "state"
    with open(os.path.join(prof, "employers.py"), "a", encoding="utf-8") as fh:
        fh.write('\nTIER_1 = {"brindlecombe holdings"}\n')          # a bar is stated
    (tmp_path / "profile" / "employers_judged.json").write_text(json.dumps(
        {"wrenfield labs": {"name": "Wrenfield Labs", "verdict": "none", "why": "a small studio",
                            "date": "2026-10-20"}}), encoding="utf-8")
    app = os.path.join(prof, "app.json")
    data = json.load(open(app, encoding="utf-8")) if os.path.exists(app) else {}
    data["suggest_no"] = {f"sg-warm-x{i}-0": {"on": f"2026-11-0{i + 2}", "kind": "warm"}
                          for i in range(3)}
    with open(app, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    research = st / "company_research"
    research.mkdir()
    (research / "harrowgate-software.json").write_text(json.dumps(
        {"company": "Harrowgate Software", "network_presence": {
            "verdict": "no_relevant_presence", "date": "2026-10-01",
            "review_after": "2026-12-30"}}), encoding="utf-8")
    before = {h["say"]: h for h in _holds(env) if h.get("say")}
    for say in ("more at Larchmont Health", "stop waiting on Fallowmere Clinic",
                "look at Ridley Assurance again", "look at Harrowgate Software again",
                "judge Wrenfield Labs again", "write to Celia again", "show me ideas again"):
        assert say in before, sorted(before)

    def lift(words):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                               words, "--today", TODAY.isoformat()], env=env,
                              capture_output=True, text=True, encoding="utf-8")

    for say in before:
        r = lift(say.upper() + ".")                     # read loosely, as typed or tapped
        assert r.returncode == 0, (say, r.stdout, r.stderr[-800:])
        assert not JARGON.search(r.stdout.split("(python3")[0]), r.stdout
    after = {h["say"] for h in _holds(env) if h.get("say")}
    assert not (after & set(before)), after
    # What each one wrote, and the words it kept.
    import reading
    with open(os.path.join(prof, reading.MORE_AT_FILE), encoding="utf-8") as fh:
        more = json.load(fh)
    assert more[0]["employer"] == "Larchmont Health" and more[0]["limit"] == 3, more
    assert "more at larchmont health" in more[0]["said"].lower()
    tracker = (st / "job_search_tracker.csv").read_text(encoding="utf-8")
    assert "no_response" in tracker and "person-said" in tracker and "stopped waiting" in tracker
    dnt = json.loads((st / "job_scraper" / "do_not_target.json").read_text(encoding="utf-8"))
    assert dnt["companies"]["Ridley Assurance"]["looked_again"] == TODAY.isoformat()
    assert "Wrenfield Labs" not in (tmp_path / "profile" / "employers_judged.json").read_text()
    contacts = (st / "network_contacts.csv").read_text(encoding="utf-8")
    assert "back after her leave" not in contacts
    # Nothing matches: it says which words would, and changes nothing.
    r = lift("more at Nowhere Ltd")
    assert r.returncode == 1 and "not lifted" in r.stdout
    # A live hiring process ends only with how it ended, said by the person.
    with open(st / "job_search_tracker.csv", "a", encoding="utf-8") as fh:
        fh.write("2026-11-01,Brackenridge Trust,,Role,,,interview,,,,,,,,2026-11-01\n")
    r = lift("it's over at Brackenridge Trust")
    assert r.returncode == 1 and "/outcome" in r.stdout, r.stdout


def test_a_pill_lifts_its_own_hold_by_its_id_where_words_name_two(tmp_path):
    """The pill sent only its words, and two holds can share them: two people on hold called
    Sam ("write to Sam again"), or an employer judged to clear none of the bar that a search
    also found no team at (both said "look at <employer> again"). Either tap was refused as
    "more than one hold has those words". The page now sends the hold's id with the words
    (args.about.ref), `holds.py lift <id> --said <words>` lifts that one and keeps the words,
    and a judgement has words of its own."""
    import schema
    env = _made_up(tmp_path, "nurse")
    prof, st = env["LJS_PROFILE"], tmp_path / "state"
    with open(os.path.join(prof, "employers.py"), "a", encoding="utf-8") as fh:
        fh.write('\nTIER_1 = {"brindlecombe holdings"}\n')          # a bar is stated
    (tmp_path / "profile" / "employers_judged.json").write_text(json.dumps(
        {"ridley assurance": {"name": "Ridley Assurance", "verdict": "none",
                              "why": "a small office", "date": "2026-10-20"}}), encoding="utf-8")
    contacts = [{"contact_id": f"s{i}", "name": f"Sam {last}", "company": emp,
                 "status": "in_conversation", "next_action": "Hold: back after the move"}
                for i, (last, emp) in enumerate((("Corrin", "Dellow Freight"),
                                                  ("Pettifer", "Ormsby Retail")), 1)]
    _write_csv(st / "network_contacts.csv", contacts, schema.CONTACT_COLUMNS)
    _write_csv(st / "network_threads.csv", [], schema.THREAD_COLUMNS)
    held = _holds(env)
    sams = [h for h in held if h["rule"] == "person_hold"]
    assert [h["say"] for h in sams] == ["write to Sam again"] * 2, sams
    ridley = {h["rule"]: h for h in held if h["what"] == "Ridley Assurance"}
    assert ridley["judged_none"]["say"] == "judge Ridley Assurance again", ridley
    assert ridley["no_team"]["say"] == "look at Ridley Assurance again", ridley

    def lift(*args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                               *args, "--today", TODAY.isoformat()], env=env,
                              capture_output=True, text=True, encoding="utf-8")

    r = lift("write to Sam again")                      # words alone: refused, nothing changed
    assert r.returncode == 1 and "more than one" in r.stdout, r.stdout
    r = lift(sams[1]["id"], "--said", "write to Sam again")
    assert r.returncode == 0 and "Sam Pettifer: off hold" in r.stdout, (r.stdout, r.stderr)
    book = (st / "network_contacts.csv").read_text(encoding="utf-8")
    assert book.count("back after the move") == 1, book
    for h in ridley.values():
        r = lift(h["id"], "--said", h["say"])
        assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    left = {(h["rule"], h["what"]) for h in _holds(env)}
    assert not {("judged_none", "Ridley Assurance"), ("no_team", "Ridley Assurance"),
                ("person_hold", "Sam Pettifer")} & left, left
    assert ("person_hold", "Sam Corrin") in left
    dnt = json.loads((st / "job_scraper" / "do_not_target.json").read_text(encoding="utf-8"))
    assert dnt["companies"]["Ridley Assurance"]["looked_again_because"] == \
        "look at Ridley Assurance again"


def test_stop_waiting_stamps_the_persons_own_time(tmp_path):
    """Stop waiting marked the application confirmed at the computer's clock time beside the
    person's day: on a computer set to Auckland, a person in London read a time eleven hours
    out. It is the person's own time now."""
    import zoneinfo
    env = dict(_made_up(tmp_path, "nurse"), TZ="Pacific/Auckland")
    london = zoneinfo.ZoneInfo("Europe/London")
    before = dt.datetime.now(london).replace(second=0, microsecond=0)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        "hold~application_open~fallowmere clinic", "--said", "stop waiting",
                        "--today", TODAY.isoformat()], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    after = dt.datetime.now(london)
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    with open(tmp_path / "state" / "job_search_tracker.csv", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    day, hhmm = row["confirmed_at"].split()
    assert day == TODAY.isoformat()
    stamped = dt.datetime.combine(before.date(), dt.time.fromisoformat(hhmm), london)
    if stamped < before:                                   # the run crossed midnight
        stamped += dt.timedelta(days=1)
    assert before <= stamped <= after, (row["confirmed_at"], before, after)


# ------------------------------------------------------------------ one clock for what is held

def test_what_the_search_holds_back_is_counted_on_the_persons_day(tmp_path, monkeypatch):
    """The search read its holds on the computer's day: a computer set to Auckland, at what is
    still Tuesday evening for a person in London, had already lifted a do-not-target entry
    whose review day is that Tuesday, counted an application a day older than it is, and dated
    a judgement Wednesday, while Held back for now (on the person's day) said otherwise. Every
    day the search holds things back by is the person's own (person.today())."""
    import zoneinfo
    time_machine = pytest.importorskip("time_machine")   # the CI installs it
    import bar
    import prefilter
    import throttle
    monkeypatch.setattr(bar, "_judged_path", lambda: str(tmp_path / "employers_judged.json"))
    bar._judged_cache.clear()
    dnt = tmp_path / "do_not_target.json"
    dnt.write_text(json.dumps({"companies": {"Ridley Assurance": {
        "reason": "only a sales office here", "review_after": "2026-11-10"}}}), encoding="utf-8")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text(json.dumps({"seen": {}}), encoding="utf-8")
    applied = {"company": "Fallowmere Clinic", "status": "applied", "applied_on": "2026-09-27"}
    try:
        # The computer in Auckland, where it is Wednesday (time-machine sets its zone).
        with time_machine.travel(dt.datetime(2026, 11, 11, 12, 22,
                                             tzinfo=zoneinfo.ZoneInfo("Pacific/Auckland")),
                                 tick=False):
            assert dt.date.today() == dt.date(2026, 11, 11)
            assert holds.person.today() == dt.date(2026, 11, 10)   # Tuesday in London
            assert "ridley assurance" in throttle.load_do_not_target(str(dnt))
            assert throttle.expired_do_not_target(str(dnt)) == []
            check = prefilter.already_ruled_out(str(seen), do_not_target=str(dnt))
            assert check({"title": "Analyst", "company": "Ridley Assurance"}).startswith(
                "do not target")
            assert not throttle.is_silent(applied)                 # 45 days on Wednesday only
            assert list(throttle.open_applications(rows=[applied])) == ["fallowmere clinic"]
            bar.judge("Wrenfield Labs", bar.NONE, "a small studio")
            assert json.loads((tmp_path / "employers_judged.json").read_text())[
                "wrenfield labs"]["date"] == "2026-11-10"
    finally:
        bar._judged_cache.clear()


def test_the_page_decides_on_the_persons_day_too(monkeypatch):
    """The page's own day (app_model.clock, read by `app.py view` for Held back for now, the
    ends of what was set aside and Jobs) fell back to the computer's date while the search
    counted the person's: on a computer in Auckland on Wednesday, the page lifted on Wednesday
    what the search, on Tuesday in London, still held (NW-17, BT-6: one day-source)."""
    import zoneinfo
    time_machine = pytest.importorskip("time_machine")   # the CI installs it
    import app_model
    monkeypatch.delenv("LJS_TODAY", raising=False)
    with time_machine.travel(dt.datetime(2026, 11, 11, 12, 22,
                                         tzinfo=zoneinfo.ZoneInfo("Pacific/Auckland")),
                             tick=False):
        assert dt.date.today() == dt.date(2026, 11, 11)
        assert app_model.person.today() == dt.date(2026, 11, 10)
        day, now = app_model.clock()
        assert day == dt.date(2026, 11, 10), day
        assert now == dt.datetime(2026, 11, 10, 23, 22, tzinfo=dt.timezone.utc)
        assert app_model.clock("2026-11-12")[0] == dt.date(2026, 11, 12)   # a day given wins


def test_a_judgement_changed_in_the_same_clock_tick_is_read_again(tmp_path, monkeypatch):
    """The judged file was cached on its time alone: another chat taking a "none" back (Look
    again now) within the same tick of the file's clock, as on a coarse clock, left this one
    reading the old judgement, still cutting the employer's jobs. A cache is keyed on the
    file's time and size (MAINTAINING.md)."""
    import bar
    import opportunity
    f = tmp_path / "employers_judged.json"
    monkeypatch.setattr(bar, "_judged_path", lambda: str(f))
    monkeypatch.setattr(opportunity, "TIER_1", {"brindlecombe holdings"})
    bar._judged_cache.clear()
    try:
        day = holds.person.today().isoformat()
        f.write_text(json.dumps({"wrenfield labs": {"name": "Wrenfield Labs", "verdict": "none",
                                                   "why": "small", "date": day}}), encoding="utf-8")
        st = os.stat(f)
        assert bar.judgement("Wrenfield Labs")["verdict"] == "none"
        f.write_text(json.dumps({}), encoding="utf-8")          # taken back by another chat
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))        # in the same tick
        assert bar.judgement("Wrenfield Labs") is None
    finally:
        bar._judged_cache.clear()


def test_open_it_now_counts_the_notes_already_drafted_there_so_one_tap_is_enough(tmp_path):
    """The limit at an employer counts the people waiting on a reply and the notes already
    drafted for people there (reading.employer_full_line). Open it now made room for the
    waiting only, so with a note drafted the next one was still refused after the tap."""
    import reading
    env = _made_up(tmp_path, "nurse")
    prof, st = env["LJS_PROFILE"], tmp_path / "state"
    import schema
    contacts = (st / "network_contacts.csv")
    rows = list(csv.DictReader(open(contacts, encoding="utf-8")))
    rows.append({"contact_id": "d1", "name": "Wynn Calder", "company": "Larchmont Health",
                 "status": "not_contacted"})
    _write_csv(contacts, rows, schema.CONTACT_COLUMNS)
    draft = st.joinpath(*reading.DIR, "d1", "draft.md")
    draft.parent.mkdir(parents=True)
    draft.write_text("Hi Wynn, hope you're well.", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        "more at Larchmont Health", "--today", TODAY.isoformat()], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    with open(os.path.join(prof, reading.MORE_AT_FILE), encoding="utf-8") as fh:
        more = json.load(fh)
    # Two waiting, one drafted, and room for one more.
    assert more[0]["limit"] == 4, more
    assert "1 note already drafted" in r.stdout, r.stdout


def test_open_it_now_makes_room_that_ends_and_never_lowers_the_persons_number(
        tmp_path, monkeypatch):
    """Open it now wrote a number for the employer (profile/more_at.json) that never ended and
    was shown nowhere, and employer_limit read it over the person's own: with their number
    raised to 5 since, the employer stayed capped at the 3 the tap made room for. The room is
    now the larger of the two, ends once the waiting it was made beside has cleared (the last
    day anyone waiting there then holds it), and is a line in Your rules with a bin."""
    import app_actions
    import reading
    import rules_view
    env = _made_up(tmp_path, "nurse")
    prof = env["LJS_PROFILE"]
    held = [h for h in _holds(env) if h["rule"] == "employer_wait"]
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        held[0]["id"], "--said", "more at Larchmont Health", "--today",
                        TODAY.isoformat()], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    path = os.path.join(prof, reading.MORE_AT_FILE)
    with open(path, encoding="utf-8") as fh:
        more = json.load(fh)
    # Two waiting, the later one written to on 2 November: a 14-day wait ends on the 16th.
    assert (more[0]["limit"], more[0]["until"]) == (3, "2026-11-16"), more
    assert "until Mon 16 Nov" in r.stdout, r.stdout
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(reading, "_more_at_path", lambda: path)
    monkeypatch.setattr(reading, "PER_EMPLOYER", 2)
    assert reading.employer_limit("Larchmont Health", TODAY)[0] == 3
    monkeypatch.setattr(reading, "PER_EMPLOYER", 5)          # their own number, raised since
    assert reading.employer_limit("Larchmont Health", TODAY)[0] == 5
    monkeypatch.setattr(reading, "PER_EMPLOYER", 2)
    assert reading.employer_limit("Larchmont Health", dt.date(2026, 11, 17)) == (2, {})
    rows = rules_view.more_at_rows(TODAY, {})
    assert [(x["name"], x["until"], x["words"]) for x in rows] == [
        ("More at Larchmont Health", "2026-11-16", "more at Larchmont Health")], rows
    assert rows[0]["sentence"].startswith("At Larchmont Health, up to 3 people may be written "
                                          "to while nobody there has answered, past your usual 2")
    assert not JARGON.search(rows[0]["sentence"]), rows[0]["sentence"]
    assert rules_view.more_at_rows(dt.date(2026, 11, 17), {}) == []
    # The bin takes it back, and its undo puts it back as it was.

    class _W:
        def add(self, *a, **k):
            pass

    now = dt.datetime(2026, 11, 9, 12, tzinfo=dt.timezone.utc)
    t = {"kind": "your_rule", "id": rows[0]["id"], "drop": rows[0]["drop"]}
    run = app_actions.Run("a1", {"action": "rule.drop", "at": "2026-11-09T12:00:00Z",
                                 "value": {}}, t, {"work": {}}, _W(), "cloud-1", "UTC", now)
    got = app_actions._rule_drop(run)
    assert reading.employer_limit("Larchmont Health", TODAY) == (2, {})
    undo = app_actions.Run("a2", {"action": "rule.undrop", "at": "2026-11-09T12:01:00Z",
                                  "value": got["undo"]["value"]}, t, {"work": {}}, _W(),
                           "cloud-1", "UTC", now)
    app_actions._rule_undrop(undo)
    assert reading.employer_limit("Larchmont Health", TODAY)[1]["until"] == "2026-11-16"


def test_a_lower_number_the_person_gave_for_one_employer_is_obeyed(tmp_path, monkeypatch):
    """The engine review of 2026-11-11: `reading.py more-at "<employer>" --up-to 1` said "kept"
    and recorded the rule, and employer_limit then read it as max(1, PER_EMPLOYER): a second
    note at that employer was drafted and shown. A number of the person's own is obeyed; only
    Open it now's room (a row with an end day) is never below their usual number."""
    import reading
    import rules_view
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    st = app_state.small(str(tmp_path / "state"))
    env = dict(os.environ, LJS_PROFILE=prof, LJS_STATE=st)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                        "more-at", "Harbourline Bank", "--up-to", "1", "--said",
                        "just one person at Harbourline for now"], env=env, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0 and "up to 1 person, fewer than the usual" in r.stdout, \
        r.stdout + r.stderr
    path = os.path.join(prof, reading.MORE_AT_FILE)
    monkeypatch.setattr(reading, "_more_at_path", lambda: path)
    monkeypatch.setattr(reading, "PER_EMPLOYER", 2)
    assert reading.employer_limit("Harbourline Bank", TODAY)[0] == 1
    row = rules_view.more_at_rows(TODAY, {})[0]
    assert row["sentence"].startswith("At Harbourline Bank, up to 1 person may be written to "
                                      "while nobody there has answered, fewer than your usual 2")
    # Open it now's room for one is still never below their usual number.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([{"employer": "Harbourline Bank", "limit": 1, "said": "Open it now",
                    "date": TODAY.isoformat(), "until": "2026-11-20"}], fh)
    assert reading.employer_limit("Harbourline Bank", TODAY)[0] == 2


# ------------------------------------------------------------------ "already applied", by the tracker

def test_an_already_applied_skip_is_read_from_the_trackers_current_row(tmp_path):
    """A posting skipped as "already applied to this role" was kept out by that record for good,
    by its own link before anything was read, though the throttle works it out afresh from the
    tracker on every round: a row put right in the tracker (the wrong employer, a role never
    sent) left the posting out for ever. The tracker's current row decides, every round."""
    import prefilter
    import throttle
    url = "https://jobs.example.com/hollowmere/77"
    job = {"url": url, "title": "Supply Analyst", "company": "Hollowmere Foods",
           "location": "Leeds, England, United Kingdom", "fit": 80, "priority": 80}
    seen = tmp_path / "seen_jobs.json"
    seen.write_text(json.dumps({"seen": {url: dict(job, status="skipped", first_seen="2026-11-01",
                                                   skip_reason="already applied to this role on "
                                                   "2026-09-01 (rejected); a relisted posting is "
                                                   "the same job", skipped_date="2026-11-01")}}),
                    encoding="utf-8")
    check = prefilter.already_ruled_out(str(seen), today=TODAY)
    assert check(job) == ""                       # never kept out by the old record alone
    urls, pairs = throttle.ruled_out(json.loads(seen.read_text())["seen"], TODAY.isoformat())
    # The tracker still has the row: the throttle keeps it out, as before.
    row = {"date": "2026-09-01", "company": "Hollowmere Foods", "role": "Supply Analyst",
           "status": "rejected"}
    kept, skipped = throttle.throttle([job], {}, urls, pairs, TODAY.isoformat(),
                                      closed=throttle.closed_applications(rows=[row]))
    assert not kept and skipped[0]["skip_reason"].startswith("already applied to this role")
    # Put right in the tracker: it comes back.
    kept, skipped = throttle.throttle([job], {}, urls, pairs, TODAY.isoformat(),
                                      closed=throttle.closed_applications(rows=[]))
    assert [r["url"] for r in kept] == [url], skipped


def test_a_role_set_aside_with_no_address_of_its_own_is_listed_and_its_bin_lifts_it(tmp_path):
    """A ruling of the person's written with no `url` field, kept under the posting's address
    as its key, is held by that key (throttle.ruled_out) but Your rules skipped it: held, and
    listed nowhere with a way to lift it."""
    import exclude
    import rules_view
    key = "https://jobs.example.com/hollowmere/77"
    seen = tmp_path / "seen_jobs.json"
    seen.write_text(json.dumps({"seen": {key: {
        "basis": "person", "status": "excluded", "title": "Supply Analyst",
        "company": "Hollowmere Foods", "exclusion_reason": "not for me",
        "excluded_date": "2026-11-01"}}}), encoding="utf-8")
    entries = exclude.load_seen(str(seen))["seen"]
    import throttle
    from lookup_score import norm
    assert norm(key) in throttle.ruled_out(entries, TODAY.isoformat())[0]     # held by its key
    rows = rules_view.set_aside_rows(entries, TODAY, {})
    assert [(r["name"], r["drop"]) for r in rows] == [
        ("Supply Analyst at Hollowmere Foods", {"kind": "set_aside", "url": key})], rows
    gone = exclude.lift(why="taken off in Your rules", today=TODAY.isoformat(), path=str(seen),
                        urls=[rows[0]["drop"]["url"]])
    assert len(gone) == 1
    assert rules_view.set_aside_rows(exclude.load_seen(str(seen))["seen"], TODAY, {}) == []


def test_a_note_set_aside_for_now_ends_is_held_back_and_never_stays_for_good(tmp_path):
    """"Set aside: no note to <name> for now" set the contact `dropped` for good: nothing ever
    reopened them and the rule said it never ends. A note set aside on the page now holds as
    long as a role set aside, is under Held back for now with Look again now, and is offered
    again on its day; one the person said never to stays set aside."""
    from test_a_tick_on_the_page_is_applied_once import Search
    import exclude
    import state
    search = Search(str(tmp_path))
    msgs = search.model()["messages"]
    assert len(msgs) >= 1
    a = search.act("msg.skip", msgs[0]["id"])
    assert search.apply()["ok"] == [a], search.receipt(a)
    end = dt.date(2026, 10, 25) + dt.timedelta(days=exclude.set_aside_days())
    assert search.receipt(a)["note"].endswith(
        f"until {end.day} {end.strftime('%b %Y')}, then offered again."), search.receipt(a)
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    got = [h for h in _holds(env) if h["rule"] == "note_aside"]
    assert [(h["until"], h["lift"]) for h in got] == [(end.isoformat(), "Look again now")], got
    assert not JARGON.search(got[0]["line"]), got[0]["line"]
    # Look again now, by its id, offers them again with their note as it was.
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        got[0]["id"], "--said", got[0]["say"], "--today", TODAY.isoformat()],
                       env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr[-800:])
    book = os.path.join(search.state, "network_contacts.csv")
    row = next(c for c in state.load_contacts(book) if c["contact_id"] == got[0]["contact_id"])
    assert row["status"] == "not_contacted", row
    assert not [h for h in _holds(env) if h["rule"] == "note_aside"]
    # Its day come, the page's wake offers it again by itself; "never" stays set aside.
    who = row["contact_id"]
    threads = os.path.join(search.state, "network_threads.csv")
    contacts = state.load_contacts(book)
    state.drop(contacts, state.load_threads(threads), who, "2026-05-01", "not now",
               until="2026-11-01")
    state.save_contacts(contacts, book)
    assert state.reopen_set_aside(TODAY, book, threads) == [f"{row['name']} ({who})"]
    contacts = state.load_contacts(book)
    state.drop(contacts, state.load_threads(threads), who, "2026-05-01", "never")
    state.save_contacts(contacts, book)
    assert state.reopen_set_aside(dt.date(2030, 1, 1), book, threads) == []
    assert next(c for c in state.load_contacts(book) if c["contact_id"] == who)["status"] == \
        "dropped"


# ------------------------------------------------------------------ Your rules' own buttons reach them

def test_a_bin_or_keep_it_in_your_rules_reaches_its_rule_on_the_page(tmp_path):
    """Your rules' rows are kept under "rule~..." ids in the page's rules section, but a tap on
    one looked for it in Contacts and Jobs: every bin (an employer turned down, a kind of
    employer, a learned rule) and every Keep it came back "That is no longer on the page: look
    again", so a rule the person wanted lifted on the page never was."""
    from test_a_tick_on_the_page_is_applied_once import Search
    search = Search(str(tmp_path))
    a = search.act("job.dismiss", "r9-1", value={"why": "employer", "scope": "employer"})
    assert search.apply()["ok"] == [a]
    search.written_back()
    rows = {r["kind"]: r for r in search.model()["rules"]["rows"]}
    took = search.act("rule.drop", rows["declined"]["id"], rev=rows["declined"]["rev"])
    kept = search.act("rule.keep", rows["sector"]["id"], rev=rows["sector"]["rev"])
    got = search.apply()
    assert got["ok"] == [took, kept], (got, search.receipt(took).get("note"))
    assert "declined" not in {r["kind"] for r in search.model()["rules"]["rows"]}


# ------------------------------------------------------------------ a role set aside, on the page

def test_a_role_set_aside_on_the_page_says_its_true_end_and_is_listed_with_a_bin(tmp_path):
    """"will not be shown again" was the page's word for a role set aside, and it was true for
    ever. It now says the day it ends (about six months on) or "for good" where the person's
    words said so; Your rules lists each with its end and a bin that brings it back."""
    from test_a_tick_on_the_page_is_applied_once import Search
    search = Search(str(tmp_path))
    plain = search.act("job.dismiss", "r9-1", value={"why": "too far to travel"})
    good = search.act("job.dismiss", "r9-2", value={"why": "never this kind of work"})
    assert search.apply()["ok"] == [plain, good]
    import exclude
    end = dt.date(2026, 10, 25) + dt.timedelta(days=exclude.set_aside_days())
    assert search.receipt(plain)["note"].endswith(
        f"is set aside until {end.day} {end.strftime('%b %Y')}."), search.receipt(plain)
    assert search.receipt(good)["note"].endswith("is set aside for good."), search.receipt(good)
    rows = [r for r in search.model()["rules"]["rows"] if r["kind"] == "set_aside"]
    assert sorted(r["until"] or "" for r in rows) == ["", end.isoformat()], rows
    assert all(r["drop"] and r["drop"]["kind"] == "set_aside" for r in rows)
    one = next(r for r in rows if r["until"])
    assert "too far to travel" in (one["words"] or "") and not JARGON.search(one["sentence"])
    # The bin brings it back, and its undo sets it aside again.
    took = search.act("rule.drop", one["id"], rev=one["rev"])
    assert search.apply()["ok"] == [took]
    left = [r for r in search.model()["rules"]["rows"] if r["kind"] == "set_aside"]
    assert [r["until"] for r in left] == [None], left
    search.written_back()
    back = search.act("undo", undoes=took)
    assert search.apply()["ok"] == [back]
    assert len([r for r in search.model()["rules"]["rows"] if r["kind"] == "set_aside"]) == 2


def test_a_live_interviews_hold_names_what_is_over(monkeypatch):
    """The pill under "no new jobs there while your interviews run" read "It's over" alone,
    which said neither what was over nor that it was the person's to say (the screen review,
    2026-11-11). It names the interviews, in the person's voice as "Stop waiting" is."""
    import throttle
    monkeypatch.setattr(throttle, "open_applications", lambda today=None: {"brindle hart": [{"company": "Brindle Hart", "status": "interview"}]})
    got = holds._applications(TODAY)
    assert [(h["lift"], h["say"]) for h in got] == [("My interviews there are over", "it's over at Brindle Hart")], got
