"""The link a card shows is the one to click, checked where it can be.

A posting's link reached the person as the board gave it: tracking on the end, sometimes
inside a redirect, sometimes a page that asks them to sign in, and never checked as still
open. tools/apply_link.py takes the tracking off (keeping every part that names the job,
so the posting's key does not move), unwraps a redirect from the link itself, says what
kind of page it is, and where the employer's board is on file finds the posting on it
and stamps when. LinkedIn is never fetched. Every board here is a stand-in.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import apply_link as al  # noqa: E402
from lookup_score import norm  # noqa: E402

NOW = dt.datetime(2026, 10, 25, 9, 30, tzinfo=dt.timezone.utc)


def test_tracking_comes_off_and_the_job_stays():
    for seen, shown in (
        ("https://www.linkedin.com/jobs/view/data-analyst-4012345678/?refId=a1&trackingId=b2"
         "&trk=public_jobs_topcard", "https://www.linkedin.com/jobs/view/data-analyst-4012345678/"),
        # gh_src is where the click came from, as utm_source is, not which job.
        ("https://boards.greenhouse.io/oakmere/jobs/123?gh_jid=123&gh_src=li&utm_source=x",
         "https://boards.greenhouse.io/oakmere/jobs/123?gh_jid=123"),
        ("https://jobs.lever.co/oakmere/abc-123?lever-origin=applied&lever-source=LinkedIn",
         "https://jobs.lever.co/oakmere/abc-123"),
        ("https://careers.oakmere.example/job?id=77&utm_campaign=fall&ref=board",
         "https://careers.oakmere.example/job?id=77"),
        ("https://ca.indeed.com/viewjob?jk=abc123&from=serp&vjs=3",
         "https://ca.indeed.com/viewjob?jk=abc123&vjs=3"),
        ("https://www.linkedin.com/jobs/search/?currentJobId=4012345678&geoId=1&trk=x",
         "https://www.linkedin.com/jobs/search/?currentJobId=4012345678"),
        ("https://wd1.myworkdayjobs.com/en-US/Oakmere/job/Leeds/Analyst_R-1?source=LinkedIn",
         "https://wd1.myworkdayjobs.com/en-US/Oakmere/job/Leeds/Analyst_R-1"),
    ):
        assert al.clean(seen) == shown, seen
        # The posting is the same posting to every stage that matches on its key.
        assert norm(al.clean(seen)) == norm(seen), seen


def test_one_posting_has_one_key_wherever_the_click_came_from():
    """Greenhouse's gh_src was kept as the job, so one posting was three keys to dedupe and
    to the tracker check; and any board's /jobs/view/<number> read as that LinkedIn job."""
    bare = "https://boards.greenhouse.io/oakmere/jobs/4000123"
    assert norm(bare + "?gh_src=linkedin") == norm(bare + "?gh_src=indeed") == norm(bare)
    assert norm("https://jobs.example-board.test/jobs/view/7654321") != "li:7654321"
    for u in ("https://www.linkedin.com/jobs/view/7654321", "https://ca.linkedin.com/jobs/view/"
              "data-analyst-at-oakmere-7654321/?trk=x", "linkedin.com/jobs/view/7654321", "7654321"):
        assert norm(u) == "li:7654321", u


def test_a_link_with_nothing_to_take_off_is_left_as_it_is():
    for u in ("https://jobs.ashbyhq.com/oakmere/5f0c", "https://careers.oakmere.example/#/job/9",
              "", None):
        assert al.clean(u) == (u.strip() if isinstance(u, str) else u)


def test_a_redirect_is_unwrapped_from_the_link_itself():
    target = "https://boards.greenhouse.io/oakmere/jobs/123?gh_jid=123"
    assert al.unwrap("https://www.google.com/url?q=https%3A%2F%2Fboards.greenhouse.io%2Foakmere"
                     "%2Fjobs%2F123%3Fgh_jid%3D123&sa=D") == target
    assert al.unwrap("https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fboards."
                     "greenhouse.io%2Foakmere%2Fjobs%2F123%3Fgh_jid%3D123") == target
    assert al.unwrap("https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fboards."
                     "greenhouse.io%2Foakmere%2Fjobs%2F123%3Fgh_jid%3D123&data=x") == target
    assert al.unwrap("https://l.facebook.com/l.php?u=" + target.replace(":", "%3A")
                     .replace("/", "%2F").replace("?", "%3F").replace("=", "%3D")) == target
    # Only ever to a web address, and never a page that merely looks like a redirect.
    assert al.unwrap("https://www.google.com/url?q=javascript:alert(1)").startswith(
        "https://www.google.com/")
    plain = "https://careers.oakmere.example/url?q=https://elsewhere.example"
    assert al.unwrap(plain) == plain


def test_each_kind_of_page_is_named():
    assert al.kind("https://www.linkedin.com/jobs/view/4012345678") == "linkedin"
    assert al.kind("https://www.glassdoor.ca/job-listing/x") == "login wall"
    assert al.kind("https://builtin.com/job/data-analyst/1") == "login wall"
    assert al.kind("https://www.builtintoronto.com/job/x") == "login wall"
    assert al.kind("https://ca.indeed.com/viewjob?jk=1") == "aggregator"
    assert al.kind("https://www.ziprecruiter.com/c/x") == "aggregator"
    assert al.kind("https://boards.greenhouse.io/oakmere/jobs/1") == "board"
    assert al.kind("https://oakmere.wd3.myworkdayjobs.com/x") == "board"
    assert al.kind("https://careers.oakmere.example/jobs/1") == "employer"
    assert al.kind("") == "" and al.kind(None) == ""


BOARD = {"Oakmere Foods": ("greenhouse", "oakmere")}
LISTING = [
    {"title": "Supply Chain Analyst", "location": "Leeds",
     "url": "https://boards.greenhouse.io/oakmere/jobs/123?gh_jid=123"},
    {"title": "Senior Data Analyst", "location": "Leeds",
     "url": "https://boards.greenhouse.io/oakmere/jobs/456?gh_jid=456"},
]


def _reader(calls, rows=LISTING, err=None):
    def read(employer, kind, token):
        calls.append((employer, kind, token))
        return list(rows), err
    return read


def test_a_linkedin_posting_is_matched_on_the_employers_own_board():
    calls = []
    row = {"company": "Oakmere Foods", "title": "Sr. Data Analyst", "location": "Leeds",
           "url": "https://www.linkedin.com/jobs/view/4012345678/?trk=x", "portal": "linkedin"}
    got = al.shown(row, now=NOW, read=_reader(calls), boards=BOARD)
    assert got["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert got["url_seen"] == row["url"]
    assert got["apply_url"] == "https://boards.greenhouse.io/oakmere/jobs/456?gh_jid=456"
    assert got["link_status"] == "open"
    assert got["link_check"] == ("open on Oakmere Foods's own board (matched by title), "
                                 "checked 2026-10-25 09:30 UTC")
    assert calls == [("Oakmere Foods", "greenhouse", "oakmere")]


def test_a_boards_own_posting_no_longer_listed_is_closed():
    row = {"company": "Oakmere Foods", "title": "Planner", "portal": "greenhouse",
           "url": "https://boards.greenhouse.io/oakmere/jobs/999?gh_jid=999"}
    got = al.shown(row, now=NOW, read=_reader([]), boards=BOARD)
    assert got["link_status"] == "closed"
    assert got["link_check"] == ("closed: no longer on Oakmere Foods's own board, "
                                 "checked 2026-10-25 09:30 UTC")
    listed = dict(row, url=LISTING[0]["url"], title="Supply Chain Analyst")
    got = al.shown(listed, now=NOW, read=_reader([]), boards=BOARD)
    assert (got["link_status"], got["apply_url"]) == ("open", LISTING[0]["url"])


def test_a_posting_on_a_sibling_board_is_never_called_closed():
    """The board's token was looked for anywhere in the link, so a posting on "oakmereuk"
    read as one "oakmere" no longer lists: a false closed, the expensive mistake."""
    for portal in ("linkedin", "greenhouse"):
        row = {"company": "Oakmere Foods", "title": "Planner", "portal": portal,
               "url": "https://boards.greenhouse.io/oakmereuk/jobs/999"}
        got = al.shown(row, now=NOW, read=_reader([]), boards=BOARD)
        assert got["link_status"] == "unknown", portal
    row = {"company": "Oakmere Foods", "title": "Planner", "portal": "linkedin",
           "url": "https://job-boards.greenhouse.io/Oakmere/jobs/999"}
    assert al.shown(row, now=NOW, read=_reader([]), boards=BOARD)["link_status"] == "closed"


def test_a_listing_that_left_postings_out_never_says_closed():
    row = {"company": "Oakmere Foods", "title": "Planner", "portal": "greenhouse",
           "url": "https://boards.greenhouse.io/oakmere/jobs/999?gh_jid=999"}
    got = al.shown(row, now=NOW, read=_reader([], rows=[], err="2 of 9 posting bodies failed"),
                   boards=BOARD)
    assert got["link_status"] == "unknown" and "did not answer" in got["link_check"]
    got = al.shown(row, now=NOW, read=_reader([], err="1 of 3 posting bodies failed"),
                   boards=BOARD)
    assert got["link_status"] == "unknown"
    assert got["link_check"].startswith("not on Oakmere Foods's own board by that title")


def test_a_board_that_does_not_answer_says_so():
    def broken(employer, kind, token):
        raise OSError("connection reset")
    row = {"company": "Oakmere Foods", "title": "Planner",
           "url": "https://www.linkedin.com/jobs/view/4012345678/"}
    got = al.shown(row, now=NOW, read=broken, boards=BOARD)
    assert got["link_status"] == "unknown"
    assert "did not answer (OSError: connection reset)" in got["link_check"]
    assert "LinkedIn is never fetched" in got["link_check"]


def test_with_no_board_on_file_nothing_is_fetched_and_it_says_why():
    def never(*a):
        raise AssertionError("fetched with no board on file")
    for url, says in (
        ("https://www.linkedin.com/jobs/view/4012345678/", "not checked: LinkedIn is never fetched"),
        ("https://www.glassdoor.ca/job-listing/x", "asks you to sign in"),
        ("https://ca.indeed.com/viewjob?jk=1", "lists other sites' jobs"),
        ("https://careers.elsewhere.example/1", "not checked"),
    ):
        got = al.shown({"company": "Elsewhere Ltd", "title": "Analyst", "url": url},
                       now=NOW, read=never, boards=BOARD)
        assert says in got["link_check"] and got["link_status"] == "unknown", url
        assert "apply_url" not in got


def test_each_board_is_read_once_however_many_cards_ask():
    calls = []
    rows = [{"company": "Oakmere Foods", "title": t, "url": f"https://www.linkedin.com/jobs/view/{n}/"}
            for n, t in ((4012345671, "Supply Chain Analyst"), (4012345672, "Senior Data Analyst"),
                         (4012345673, "Planner"))]
    got = al.shown_all(rows, now=NOW, read=_reader(calls), boards=BOARD)
    assert len(calls) == 1
    assert [g["link_status"] for g in got] == ["open", "open", "unknown"]


def test_shown_twice_is_shown_once():
    row = {"company": "Oakmere Foods", "title": "Senior Data Analyst",
           "url": "https://www.linkedin.com/jobs/view/4012345678/?refId=1"}
    once = al.shown(row, now=NOW, read=_reader([]), boards=BOARD)
    assert al.shown(once, now=NOW, read=_reader([]), boards=BOARD) == once


def test_the_command_reads_a_list_and_writes_it_back(tmp_path, capsys):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"company": "Elsewhere Ltd", "title": "Analyst",
                                 "url": "https://www.linkedin.com/jobs/view/4012345678/?trk=a"}]),
                    encoding="utf-8")
    assert al.main(["--file", str(path), "--write"]) == 0
    out = json.loads(path.read_text(encoding="utf-8"))
    assert out[0]["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert out[0]["link_check"] == "not checked: LinkedIn is never fetched"
    assert "Elsewhere Ltd | Analyst" in capsys.readouterr().out
    assert al.main([]) == 2


def test_a_staged_pick_carries_the_link_to_click(tmp_path):
    import stage_picks
    posting = ("Oakmere Foods is hiring a Supply Chain Analyst in Leeds to plan stock across "
               "its depots. You will build forecasts in Python and SQL. Permanent, full time.")
    row = {"company": "Oakmere Foods", "title": "Supply Chain Analyst", "location": "Leeds, UK",
           "url": "https://www.linkedin.com/jobs/view/4012345678/?refId=a1&trk=public_jobs",
           "portal": "linkedin", "desc": posting, "fit": 80}
    rd = tmp_path / "r1"
    [p] = stage_picks.stage(str(rd), ["1"], rows=[], shortlist=[row], fetch=lambda r: {},
                            root=str(tmp_path))
    [app] = json.loads((rd / "apps_in.json").read_text(encoding="utf-8"))
    assert app["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert app["url_seen"] == row["url"]
    assert app["link_check"] == "not checked: LinkedIn is never fetched"
    head = open(p["file"], encoding="utf-8").read()
    # In the shortlist row, fenced after the posting: nothing the board wrote sits above a
    # fence (updated 2026-10-25, the drafting audit).
    row_block = head[head.index("shortlist row"):]
    assert ("apply link: https://www.linkedin.com/jobs/view/4012345678/ (not checked: "
            "LinkedIn is never fetched)") in row_block


def test_the_tracker_row_says_where_to_apply_and_whether_it_closed():
    import record_drafts
    draft = {"company": "Oakmere Foods", "role": "Senior Data Analyst", "abbr": "Oakmere"}
    seen = "https://www.linkedin.com/jobs/view/4012345678/"
    own = "https://boards.greenhouse.io/oakmere/jobs/456?gh_jid=456"
    row = record_drafts._row_for(draft, {"url": seen, "apply_url": own, "link_status": "open",
                                         "link_check": "open on Oakmere Foods's own board, "
                                                       "checked 2026-10-25 09:30"},
                                 "2026-10-25", "")
    assert row["source"] == seen
    assert (f"Apply at {own} (open on Oakmere Foods's own board, checked 2026-10-25 09:30)."
            in row["notes"])
    shut = record_drafts._row_for(draft, {"url": own, "link_status": "closed",
                                          "link_check": "closed: no longer on Oakmere Foods's "
                                                        "own board, checked 2026-10-25 09:30"},
                                  "2026-10-25", "")
    assert "Link closed: no longer on Oakmere Foods's own board" in shut["notes"]
    plain = record_drafts._row_for(draft, {"url": seen}, "2026-10-25", "")
    assert "Apply at" not in plain["notes"] and "Link " not in plain["notes"]
