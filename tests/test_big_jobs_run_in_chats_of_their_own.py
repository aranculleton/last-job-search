"""Big jobs run in chats of their own, side by side, and never hold the chat that answers
the page.

The maintainer, 2026-10-29: "are we still able to run networking at the same time as a job
search? and both at the same time as interview prep?" Then, from a person's copy the same
day: run inside the chat that answers the page, even as background agents, a search and a
networking run held it for 15 and 23 minutes, and the page waited on every tap. Changed
2026-10-29: this file pinned "a background agent inside the same chat, never a new chat";
now `next` never hands a big job to that chat to run itself. In a cloud chat it prints the
create_session call for a chat of its own, which runs the one item, pins its progress and
lands it, and never publishes, watches or answers the page; a background agent is only the
fallback where no chat can be started. Three at most (`page_db.HEAVY_CAP`), and the page
says "In line" only once three are running.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import page_db  # noqa: E402
import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import NOW, Search, _w  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_the_page_knows_the_same_big_jobs_and_the_same_cap_as_the_engine():
    js = _read("templates/app/app.js")
    kinds = re.search(r"const HEAVY_KINDS = new Set\(\[([^\]]*)\]\)", js).group(1)
    assert {k.strip().strip('"') for k in kinds.split(",")} == \
        {k for k, v in page_db.WORK_KINDS.items() if v["heavy"]}
    assert f"const HEAVY_CAP = {page_db.HEAVY_CAP};" in js and page_db.HEAVY_CAP == 3


def test_next_sends_a_big_job_to_a_chat_of_its_own_and_keeps_light_work_here(search):
    search.put("work", "network~acme", _w("network", "Kestrel Mutual"), version=1)
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--now", NOW))
    assert got["work"] == "network~acme" and got["heavy"] is True
    # A copy with a GitHub address starts a chat; one without falls back to an agent. Never
    # here, whichever it is.
    assert got["run"] in ("child session", "background agent")
    call = got.get("create_session") or got.get("agent")
    assert "--work network~acme" in call["prompt"] and "app.py pin" in call["prompt"]
    alone = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                  "--no-sessions", "--now", NOW))
    assert alone["run"] == "background agent" and "create_session" not in alone
    search.put("work", "network~acme", _w("network", "Kestrel Mutual", status="done"), version=2)
    search.put("work", "talk~1", _w("talk"), version=1)
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--now", NOW))
    assert got["work"] == "talk~1" and got["heavy"] is False and got["run"] == "here"


def test_the_chat_that_answers_the_page_never_runs_or_waits_on_a_big_job():
    skill = " ".join(_read(".claude/skills/app/SKILL.md").split())
    assert "A big job runs in a chat of its own" in skill
    assert "make the `create_session` call exactly as `next` printed it" in skill
    assert "It never publishes, watches or answers the page" in skill
    # The fallback where no chat can be started.
    assert "`run_in_background: true`" in skill and "`isolation: \"worktree\"`" in skill
    assert "Never wait for either: go straight back to step 3" in skill
    # One writer of the page's view, so two chats never write it at once.
    assert "This chat is the one writer of the page's view" in skill
    assert "waited for, with the url" not in skill
    assert "never a new chat" not in skill
    head = _read(".claude/skills/app/SKILL.md").split("---", 2)[1]
    assert "mcp__claude-code-remote__create_session" in head


def test_a_job_is_in_line_only_once_three_big_ones_are_running():
    js = _read("templates/app/app.js")
    body = js[js.index("  function queuePlace(id, w) {"):]
    body = body[:body.index("\n  }\n") + 4]
    assert "HEAVY_CAP" in body and "if (!heavy(w)) return {pos: 0" in body


def _doc(kind, status, company, asked, **kw):
    import datetime as dt
    now = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.timezone.utc)
    at = lambda m: (now + dt.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {"kind": kind, "status": status, "asked_at": at(asked), "args": {"company": company},
            "title": f"Resume and letter: {company}", "attempt": 1}
    data.update({k: at(v) if k in ("claimed_at", "lease_until", "stage_at") else v for k, v in kw.items()})
    return {"data": data, "version": 3}


def test_drafts_asked_while_one_runs_start_at_once_and_one_for_the_same_employer_waits():
    """The maintainer, 2026-11-01: "if I queue multiple tasks... just as the draft is gonna
    close I decide to draft a couple more, what will it do?" Drafts for other employers start
    at once in one chat of their own; one for the same employer waits for its lock, and starts
    when the first one's chat reports it finished (the app skill: then step 3 again)."""
    import datetime as dt
    now = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.timezone.utc)
    work = {"draft~a": _doc("draft", "running", "Fetch", -20, claimed_at=-19, lease_until=10),
            "draft~b": _doc("draft", "queued", "Fetch", -1),
            "draft~c": _doc("draft", "queued", "Adobe", -1),
            "draft~d": _doc("draft", "queued", "Shopify", 0)}
    db = {"work": work, "locks": {"emp~fetch": {"data": {"work": "draft~a", "until": "2026-11-01T10:10:00Z"},
                                                "version": 1}}}
    got = page_db.next_item(db, "cloud", now)
    assert got["work"] == "draft~c" and [w["work"] for w in got["with"]] == ["draft~d"]
    assert "emp~fetch" not in got["locks"]
    work["draft~a"]["data"]["status"] = "done"
    for k in ("draft~c", "draft~d"):
        work[k]["data"].update(status="running", lease_until="2026-11-01T10:30:00Z")
    db["locks"] = {}
    assert page_db.next_item(db, "cloud", now)["work"] == "draft~b"


def test_a_job_whose_chat_stopped_starts_again_once_by_itself():
    """A job's chat that stopped left its card "running" for good (2026-11-01). Once its claim
    has not moved on for LEASE_S, the next chat to look starts it again from the top, saying
    so on its card; a second stop waits for the person's "Ask Claude again"."""
    import datetime as dt
    now = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.timezone.utc)
    dead = _doc("draft", "running", "Fetch", -60, claimed_at=-59, lease_until=-5, stage=3)
    got = page_db.next_item({"work": {"draft~f": dead}}, "cloud", now)
    assert got["work"] == "draft~f" and got["again"] == 2
    alive = _doc("draft", "running", "Fetch", -60, claimed_at=-59, lease_until=5)
    assert page_db.next_item({"work": {"draft~f": alive}}, "cloud", now) is None
    twice = _doc("draft", "running", "Fetch", -60, claimed_at=-59, lease_until=-5, attempt=2)
    assert page_db.next_item({"work": {"draft~f": twice}}, "cloud", now) is None
    stopped = _doc("draft", "running", "Fetch", -60, claimed_at=-59, lease_until=-5, stop_asked=True)
    assert page_db.next_item({"work": {"draft~f": stopped}}, "cloud", now) is None


def test_a_job_started_again_is_claimed_from_the_top_and_says_so(tmp_path):
    import datetime as dt
    now = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.timezone.utc)
    dead = _doc("draft", "running", "Fetch", -60, claimed_at=-59, lease_until=-5, stage=3)
    db = {"work": {"draft~f": dead}}
    got = page_db.next_item(db, "cloud", now)
    files = page_db.claim(db, got, "cloud-2", "cloud", now, str(tmp_path))
    with open(files[0], encoding="utf-8") as fh:
        batch = json.load(fh)
    w = next(x for x in batch if x["collection"] == "work")
    with open(w["file_path"], encoding="utf-8") as fh:
        fields = json.load(fh)
    assert w["if_version"] == 3, "pinned: a chat that was only slow, not stopped, keeps it"
    assert fields["claimed_by"] == "cloud-2" and fields["attempt"] == 2 and fields["stage"] == 0
    assert "Started again" in fields["steps"][0]["text"]


def test_the_brief_takes_work_still_waiting_on_the_page():
    """Nothing but a tap or a finished job wakes the chat that answers the page; the daily
    brief, which runs there, sweeps up what is still waiting (2026-11-01)."""
    assert "Then the app skill's steps 1 to 3, for work still waiting" in _read("tools/brief.py")

