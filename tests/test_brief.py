"""The brief is gathered by code in one command, so a scheduled run reads it once.

A run used to read the state files, the last brief, the last pack, every owed contact's
thread and the publisher pages itself, in a chat that re-read all of it on every one of some
thirty calls (1.5M to 2.5M tokens a run, the cost audit of 2026-10-25). tools/brief.py reads
them and prints the message with the news still to fill, under 2,500 characters, and under
two seconds on a large state. Invented people only, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]
EXAMPLE = os.path.join(ROOT, "profile.example")
TODAY = "2026-10-25"

import brief  # noqa: E402


def _state(tmp_path) -> str:
    d = str(tmp_path / "state")
    shutil.copytree(os.path.join(EXAMPLE, "state"), d)
    return d


def _profile(state) -> str:
    """A copy of the example profile beside the state: --write keeps the tip line's record
    in the profile (tools/tips.py), and the example person's own folder is never written."""
    d = os.path.join(os.path.dirname(state), "profile")
    if not os.path.isdir(d):
        shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("state", "tips.json"))
    return d


def _run(state, *args, stdin=None, env_extra=None):
    env = dict(os.environ, LJS_PROFILE=_profile(state), LJS_STATE=state, PYTHONIOENCODING="utf-8",
               LJS_BRIEF_SYNC=os.path.join(state, "sync.txt"))
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "brief.py"), *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, input=stdin,
                          encoding="utf-8", timeout=120)


# ------------------------------------------------------------------ the example person

def test_the_text_is_the_message_then_the_lines_for_claude(tmp_path):
    r = _run(_state(tmp_path), "--today", TODAY)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert len(out) <= brief.TEXT_MAX
    head = out.splitlines()[0]
    assert head == "Sunday brief: 2 owed · 1 application live · 0 interviews"
    # The lead says where the search is: someone is waiting on a reply.
    assert "waiting on you: Juno (Larkspur Retail)" in out
    assert "\nOwed\n- Juno Castellan (Larkspur Retail): CV owed" in out
    three = out.split("Next three\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert [ln[:3] for ln in three] == ["1. ", "2. ", "3. "]
    assert "<NEWS>" in out
    claude = out.split("FOR CLAUDE, never in the message:\n", 1)[1]
    searches = claude.split("given these searches: ", 1)[1].split("\n", 1)[0].split(" | ")
    assert 1 <= len(searches) <= 6
    assert "Larkspur Retail news" in searches[0]      # an employer in play comes first
    assert "—" not in out


def test_the_same_state_prints_the_same_text(tmp_path):
    state = _state(tmp_path)
    assert _run(state, "--today", TODAY).stdout == _run(state, "--today", TODAY).stdout


def test_without_write_nothing_is_written(tmp_path):
    state = _state(tmp_path)
    before = open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read()
    _run(state, "--today", TODAY)
    assert not os.path.exists(os.path.join(state, "documents"))
    assert open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read() == before


def test_write_does_the_upkeep_and_keeps_the_record_and_the_pack(tmp_path):
    state = _state(tmp_path)
    r = _run(state, "--today", TODAY, "--write")
    assert r.returncode == 0, r.stderr
    record = open(os.path.join(state, "documents", "briefs", TODAY + ".md"), encoding="utf-8").read()
    for heading in ("## Where the search is", "## Owed", "## Since the last brief", "## Next three",
                    "## News"):
        assert heading in record
    assert brief.NEWS_HOLDER in record
    # The application gone quiet is closed as no reply, as the brief always did.
    assert "Closing as no reply: Larkspur Retail" in record
    tracker = open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read()
    assert "closed as no_response" in tracker
    pack = open(os.path.join(state, "documents", "network", "followup_pack_%s.md" % TODAY),
                encoding="utf-8").read()
    assert "## Needs writing" in pack and "Juno Castellan" in pack


def test_the_json_is_the_pages_brief_due_and_messages_with_no_private_detail(tmp_path):
    r = _run(_state(tmp_path), "--today", TODAY, "--json")
    got = json.loads(r.stdout)
    assert set(got) == {"brief", "due", "messages"}
    assert got["brief"]["date"] == TODAY and got["brief"]["lines"][0].startswith("Sunday brief")
    for d in got["due"]:
        assert set(d) == {"id", "kind", "title", "due", "overdue_days", "action"}
        assert d["kind"] in ("follow_up", "reply", "interview", "nudge")
    text = r.stdout
    # A contact's own words, address and profile link never reach the page.
    assert "happy to help" not in text and "linkedin.com/in" not in text and "@" not in text
    assert "Reply to Juno (Larkspur Retail)" in [d["title"] for d in got["due"]]


# ------------------------------------------------------------------ the news

def test_news_goes_into_the_record_once_and_a_freeze_is_noted_on_a_live_application(tmp_path):
    state = _state(tmp_path)
    _run(state, "--today", "2026-09-20", "--write")
    items = ("- Larkspur Retail pauses hiring at its Leeds head office, with a hiring freeze "
             "until spring (Example Times, 2026-09-18, https://example.com/news/1). An employer "
             "you applied to.\n"
             "- Bank of England holds rates (Example Times, 2026-09-18, https://example.com/news/2). "
             "Your market.\n")
    r = _run(state, "news", "--today", "2026-09-20", stdin=items)
    assert "news: 2 kept" in r.stdout and "noted on the tracker for Larkspur Retail" in r.stdout
    tracker = open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read()
    assert "2026-09-20: news: Larkspur Retail pauses hiring" in tracker
    # The next brief leaves out a link an earlier one sent.
    _run(state, "--today", "2026-09-24", "--write")
    r = _run(state, "news", "--today", "2026-09-24", stdin=items)
    assert "news: 0 kept; 2 left out, already sent" in r.stdout
    record = open(os.path.join(state, "documents", "briefs", "2026-09-24.md"), encoding="utf-8").read()
    assert record.rstrip().endswith("Quiet week.")
    # The since date is the last brief's.
    assert "Since 2026-09-20." in record


def test_the_searches_come_from_the_profile_and_stay_at_six():
    md = ("### Target Sectors\n- Banking and fintech: Harbourline Bank, Kestrel Mutual, Copperleaf "
          "Pay (a lender), Ellerwick Trust\n- Pensions: Brackenhollow Mutual\n\n### Deal-breakers\n- x\n")
    names, sectors = brief.target_names(md)
    assert names == ["Harbourline Bank", "Kestrel Mutual", "Copperleaf Pay", "Ellerwick Trust",
                     "Brackenhollow Mutual"]
    assert sectors == ["Banking and fintech", "Pensions"]
    q = brief.queries(dt.date(2026, 10, 25), ["Larkspur Retail", "Fernhill Freight", "Quayside"], md)
    assert len(q) <= 6 and q[0].startswith("Larkspur Retail") and q[1].startswith("Fernhill")
    assert any("Bank of England" in x for x in q)          # the example person is in the UK
    # A different pair of targets on another day, so every one is looked at over a few weeks.
    later = brief.queries(dt.date(2026, 10, 29), [], md)
    assert later != brief.queries(dt.date(2026, 10, 25), [], md)


def test_what_counts_is_the_persons_own_line_where_they_wrote_one():
    md = ("## This search's automation\n\n- **Morning brief, what counts for this search**: "
          "employers in process; the permit, which outranks everything.\n")
    assert brief.what_counts(md).startswith("Morning brief, what counts")
    assert brief.what_counts("# nothing here\n") == brief.WHAT_COUNTS


# ------------------------------------------------------------------ the sync's output

def _log(path, today, body, exit_=0, earlier=""):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("date: %s\nexit: %d\nearlier: %s\nsetup: \n---\n%s" % (today, exit_, earlier, body))


def test_what_the_sync_printed_is_decided_into_lines(tmp_path):
    p = str(tmp_path / "sync.txt")
    _log(p, TODAY, "sync_app: following the app's releases.\n"
                   "Update waiting. Claude: tell the person this once, at the end of your reply, "
                   "in these words; the app updates only when they say so:\n"
                   '  An update is waiting: the brief costs less. Say "update" when you want it.\n'
                   "Improvements waiting for your search (2):\n"
                   "  Claude applies these itself, in the background. Nothing for you to do:\n"
                   "    - Your job boards rebuilt.  [boards-v4]\n"
                   "  These need you: one short question each, at the end of a session:\n"
                   "    - Shall I set your brief up the new way?  [routines]\n"
                   "  Claude: start a background agent now.\n"
                   "Claude, not for the person: their own tests, 2 now fail after this update.\n"
                   "  2 use parts of the app this update removed: brief.old (2).\n"
                   "Claude: CLAUDE.md changed. A chat that was already open is still following "
                   "the copy it read when it started.\n",
         earlier="origin/claude/ops-2026-10-22-morning_brief")
    got = brief.read_sync(dt.date(2026, 10, 25), p)
    assert got["update"].startswith("An update is waiting: the brief costs less.")
    assert got["upgrades"] == ["Your job boards rebuilt.  [boards-v4]"]
    assert got["questions"] == ["Shall I set your brief up the new way?  [routines]"]
    assert got["earlier"] == ["origin/claude/ops-2026-10-22-morning_brief"]
    assert got["for_claude"][0].startswith("their own tests, 2 now fail after this update. 2 use")
    assert got["for_claude"][1].startswith("CLAUDE.md changed: read it again")
    # Yesterday's log is not today's.
    assert brief.read_sync(dt.date(2026, 10, 26), p) == {}


def test_an_update_waiting_is_said_once_and_blocked_sites_open_the_message(tmp_path):
    state = _state(tmp_path)
    log = os.path.join(state, "sync.txt")
    body = ("Job sites blocked. Claude: before anything else, tell the person this, in these "
            "words, and run no search until they say it is done:\n"
            "  This chat can't reach job sites yet (LinkedIn).\n"
            "Update waiting. Claude: tell the person this once:\n"
            '  An update is waiting: small fixes. Say "update" when you want it.\n')
    _log(log, "2026-10-22", body)
    first = _run(state, "--today", "2026-10-22", "--write").stdout
    assert "This chat can't reach job sites yet (LinkedIn)." in first
    assert 'An update is waiting: small fixes.' in first
    _log(log, "2026-10-25", body)
    again = _run(state, "--today", "2026-10-25", "--write").stdout
    assert "This chat can't reach job sites yet" in again     # every run until it is fixed
    assert "An update is waiting" not in again                  # the last brief said it


def test_a_stopped_sync_and_upgrades_reach_claude_not_the_person(tmp_path):
    state = _state(tmp_path)
    _log(os.path.join(state, "sync.txt"), TODAY,
         "sync_app: stopped: uncommitted work.\n", exit_=1)
    out = _run(state, "--today", TODAY, "--write").stdout
    msg, claude = out.split("FOR CLAUDE, never in the message:\n", 1)
    assert "Today's check for app updates did not finish" in msg
    assert "sync_app" not in msg
    assert "the update check stopped (exit 1)" in claude


# ------------------------------------------------------------------ a large state

def _big_state(root, contacts=400, rows=200, seed=7, today=dt.date(2026, 10, 25)):
    import csv
    rnd = random.Random(seed)
    first = ["Ash", "Bea", "Cal", "Dee", "Eli", "Fen", "Gus", "Hal", "Ivo", "Jem", "Kit", "Lux"]
    last = ["Brook", "Carrow", "Dunmore", "Ewell", "Farrant", "Gale", "Holm", "Ibsley"]
    firms = ["Fernhill Freight", "Larkspur Retail", "Quayside Foods", "Kestrel Mutual",
             "Oakmere Foods", "Saltmarsh Analytics", "Brackmoor Retail", "Ellerwick Trust"]
    cols = ["contact_id", "name", "title", "company", "company_key", "location", "linkedin_url",
            "email", "tier", "route", "route_detail", "referred_by", "signal", "signal_date",
            "first_contacted", "channel", "status", "next_action", "next_action_due", "outcome",
            "linked_application", "notes"]
    tcols = ["contact_id", "date", "direction", "channel", "scenario", "summary", "full_text"]
    rcols = ["date", "company", "sector", "role", "role_type", "channel", "status",
             "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file", "source",
             "deadline"]
    crow, trow, rrow = [], [], []
    for i in range(contacts):
        name = "%s %s%d" % (rnd.choice(first), rnd.choice(last), i)
        firm = rnd.choice(firms)
        st = rnd.choice(["not_contacted", "awaiting_reply", "replied_needs_response",
                         "in_conversation", "awaiting_reply"])
        sent = today - dt.timedelta(days=rnd.randint(3, 80))
        crow.append({"contact_id": "c%04d" % i, "name": name, "company": firm,
                     "title": rnd.choice(["Data Analyst", "Head of Planning", "Talent Partner"]),
                     "location": "Manchester, England, United Kingdom", "channel": "linkedin",
                     "status": st, "first_contacted": "" if st == "not_contacted" else sent.isoformat()})
        if st == "not_contacted":
            continue
        trow.append({"contact_id": "c%04d" % i, "date": sent.isoformat(), "direction": "outbound",
                     "channel": "linkedin", "scenario": "first_note", "summary": "first note",
                     "full_text": "Hi %s, how is the team at %s set up?" % (name.split()[0], firm)})
        if st in ("replied_needs_response", "in_conversation"):
            trow.append({"contact_id": "c%04d" % i, "date": (sent + dt.timedelta(days=2)).isoformat(),
                         "direction": "inbound", "channel": "linkedin", "scenario": "detailed_generous",
                         "summary": "replied", "full_text": "Happy to chat next week."})
    for i in range(rows):
        rrow.append({"date": (today - dt.timedelta(days=rnd.randint(1, 120))).isoformat(),
                     "company": rnd.choice(firms) + (" %d" % i if i % 3 else ""),
                     "role": rnd.choice(["Data Analyst", "Demand Planner"]), "channel": "company site",
                     "status": rnd.choice(["applied", "applied", "drafted", "rejected", "interview"]),
                     "fit_rating": "70", "notes": "invented row"})
    os.makedirs(root, exist_ok=True)
    for name, c, data in (("network_contacts.csv", cols, crow), ("network_threads.csv", tcols, trow),
                          ("job_search_tracker.csv", rcols, rrow)):
        with open(os.path.join(root, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=c)
            w.writeheader()
            for r in data:
                w.writerow({k: r.get(k, "") for k in c})


@pytest.mark.parametrize("write", [False, True])
def test_a_large_state_is_gathered_in_under_two_seconds_and_stays_short(tmp_path, write):
    state = str(tmp_path / "big")
    _big_state(state)
    start = time.monotonic()
    r = _run(state, "--today", TODAY, *(["--write"] if write else []))
    took = time.monotonic() - start
    assert r.returncode == 0, r.stderr
    assert took < 2.0, took
    assert len(r.stdout) <= brief.TEXT_MAX
    assert r.stdout.count("\n- ") >= 4


def test_the_start_keeps_the_syncs_output_and_gathers_in_a_fresh_process(tmp_path, monkeypatch):
    calls = []

    class Done:
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def fake(argv, **kw):
        calls.append(list(argv))
        if "sync_app.py" in " ".join(argv):
            return Done(0, '  An update is waiting: small fixes. Say "update" when you want it.\n')
        if argv[:2] == ["git", "branch"]:
            return Done(0, "  origin/claude/ops-2026-10-22-morning_brief\n")
        return Done(0)

    log = str(tmp_path / "sync.txt")
    monkeypatch.setenv("LJS_BRIEF_SYNC", log)
    monkeypatch.setattr(brief.subprocess, "run", fake)
    assert brief.start(["--on", "a model", "--write"], "a model") == 0
    sync = next(c for c in calls if "sync_app.py" in " ".join(c))
    assert sync[-3:] == ["--if-stale", "--on", "a model"]
    # The gather is a new process, so an update the sync just took is the code that runs.
    assert calls[-1][1].endswith("brief.py") and calls[-1][2:] == ["--on", "a model", "--write"]
    got = brief.read_sync(dt.date.today(), log)
    assert got["update"].startswith("An update is waiting") and got["earlier"]


def test_a_search_with_nothing_in_it_still_gets_a_brief_with_three_things(tmp_path):
    state = str(tmp_path / "empty")
    os.makedirs(state)
    r = _run(state, "--today", TODAY)
    assert r.returncode == 0, r.stderr
    assert "Nothing owed" in r.stdout and "Nothing has gone out in 14 days" in r.stdout
    three = r.stdout.split("Next three\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert len(three) == 3
