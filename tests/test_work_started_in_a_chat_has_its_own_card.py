"""Work a person asks for in a chat shows on their page as its own card, one for each job.

Issue 276: asked in a chat to "run a job search and a people search", the chat ran both in
background helpers and set its one "busy" line, so the page showed one card for two jobs, and
where the line was not set, nothing: the person looked, saw no search running and thought
neither had started. The command that puts chat-started work on the page's work list was
there (`app.py ask ... --here`, since 4 November), but only the page's own instructions named
it: the job search and the people search a chat runs when asked never said to use it.

Here two jobs asked of one chat are two running cards, that chat's, which no other chat ever
takes or starts again, and the instructions a chat reads to run either job say to register it
first. Every chat id and employer is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import app_model  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db  # noqa: E402

T = app_model.parse_time(NOW)
CHAT = "session_EXAMPLECHAT276"


def _asked(db, tmp_path, kind, title, args, n):
    got = page_db.ask(db, kind, title, T, str(tmp_path / f"b{n}"), args=args, chat_id=CHAT,
                      here=True, chat_kind="computer")
    with open(json.load(open(got["batches"][0], encoding="utf-8"))[0]["file_path"],
              encoding="utf-8") as fh:
        fields = json.load(fh)
    db["work"][got["work"]] = {"data": fields, "version": 1}
    return got["work"], fields


def test_a_job_search_and_a_people_search_asked_in_one_chat_are_two_cards_of_its_own(tmp_path):
    db = _db()
    search, s = _asked(db, tmp_path, "search", "Finding jobs", {}, 1)
    people, p = _asked(db, tmp_path, "network", "People at Harbourline Bank",
                       {"company": "Harbourline Bank"}, 2)
    assert search != people
    for f in (s, p):
        assert (f["status"], f["claimed_by"], f["in_chat"]) == ("running", CHAT, True)
        assert f["stages"] and f["stage"] == 0
    # No other chat takes either, now or long after this chat's last word: work a chat began
    # for the person there is never started again elsewhere, only ended once that chat is quiet.
    for later in (T, T + dt.timedelta(seconds=page_db.LEASE_S * 3)):
        assert page_db.next_item(db, "cloud", later) is None
        assert page_db.next_item(db, "computer", later) is None
    assert sorted(page_db.stranded(db, T + dt.timedelta(seconds=page_db.LEASE_S * 3))) == \
        sorted([search, people])
    assert page_db.stranded(db, T) == []


def _said(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_the_job_search_and_the_people_search_a_chat_runs_put_themselves_on_the_page():
    # Pinned as phrases (MAINTAINING.md, "Adding a test"): the instructions a chat reads to run
    # each job name the command, so the job is on the person's work list from its first step.
    scrape = _said(".claude/skills/job-scraper/SKILL.md")
    assert 'python3 tools/app.py ask "$D" --kind search' in scrape
    assert "--here --chat <your chat id>" in scrape
    network = _said(".claude/commands/network.md")
    assert 'python3 tools/app.py ask "$D" --kind network' in network
    assert "Every run asked in a chat is on the page's work list first" in network
    for text in (scrape, network):
        assert "its own card" in text and "app.py pin" in text and "app.py done" in text
