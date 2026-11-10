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


def _declined(_s):
    import run_round
    assert run_round.declined_now() == {}     # the example person turned nobody down


def _dismissed(_s):
    import exclude
    assert "person" in exclude.BASES          # a ruling of theirs is on one posting, kept by basis


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
    assert app_actions.ACTIONS["msg.skip"][2] == "msg.unskip"


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


MISSING = {"job_age": _job_age, "gates": _gates, "sectors": _sectors, "declined": _declined,
           "dismissed": _dismissed, "ruled_out": _ruled_out, "duplicates": _duplicates,
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
    assert [x["id"] for x in rules["every_hold"]] == [r["id"] for r in holds.RULES]
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
