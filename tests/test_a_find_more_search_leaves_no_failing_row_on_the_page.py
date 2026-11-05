"""A "find N more" search takes every row failing a hard rule off the Jobs page, in the same step.

The maintainer's "find 20 more" on 5 November drafted only what passed its own checks and
left every failing row on Jobs as a fresh "Draft this" find: US-based roles, employers that
failed the bar, copies of roles already drafted or applied to. 18 of 37 were removed by hand.
The Found list is now decided by the shortlist's own function (run_round.page_rules, read
by app_model._jobs), and the search writes each row it rules out as a ruling with its plain
reason (run_round.leave_out), on its left-out list where Bring back undoes it.

Here: an earlier search of 12 still on the page, 6 of them failing now, and a top-up that
ranks 25, 12 of them failing. The page's Found list holds the 19 that pass and nothing else.
Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import bar  # noqa: E402
import datetime as dt  # noqa: E402
import exclude  # noqa: E402
import filtered  # noqa: E402
import run_round  # noqa: E402
import sector  # noqa: E402
from company_key import key as company_key  # noqa: E402

TODAY = "2026-11-05"
NOW = dt.datetime(2026, 11, 5, 21, tzinfo=dt.timezone.utc)
GOOD = "You will build SQL and Python reporting for the planning team."
LEEDS = "Leeds, England, United Kingdom"


def _row(n, company, title="Data Analyst", place=LEEDS, desc=GOOD, url=None, seen="2026-11-05",
         score=True):
    r = {"title": title, "company": company, "date": seen, "first_seen": seen,
         "portal": "linkedin", "desc": desc, "location": place,
         "url": url or f"https://www.linkedin.com/jobs/view/{9000 + n}/"}
    if score:
        # Scores from 62 to 98, the failing rows among the passing ones as a ranking mixes them.
        r.update(fit=62 + (n * 13) % 37, priority=65 + (n * 13) % 37)
    return r


# The earlier search, still on the page: six pass, and six fail now (two US-based ones an
# older build kept, an employer judged since to clear none of the bar, one turned down by
# name since, the role already applied to under a new title, and a second copy of a row).
EARLIER_PASS = [_row(n, c, seen="2026-11-02") for n, c in enumerate(
    ["Alderbank Freight", "Brookvale Grocers", "Cinderford Logistics", "Dunmore Retail",
     "Eastholme Foods", "Farrowdale Supply"], 1)]
EARLIER_FAIL = [
    _row(7, "Galeworth Systems", place="Chicago, IL, United States", seen="2026-11-02"),
    _row(8, "Hollinsway Labs", place="Remote (US only)", seen="2026-11-02"),
    _row(9, "Ivybridge Studio", seen="2026-11-02"),
    _row(10, "Juniper Gaming Group", seen="2026-11-02"),
    _row(11, "Larkspur Retail", title="Supply Chain Analyst", url="https://example.com/jobs/1",
         seen="2026-11-02"),
    _row(12, "Alderbank Freight", url="https://careers.example/alderbank/2", seen="2026-11-02"),
]
# The top-up: thirteen pass, twelve fail.
NEW_PASS = [_row(20 + n, c) for n, c in enumerate(
    ["Kettlewell Foods", "Lowfold Haulage", "Marchbank Retail", "Netherby Grocers",
     "Oakhurst Freight", "Pendleford Supply", "Quarrybank Foods", "Ravensworth Retail",
     "Stonebridge Logistics", "Thornaby Foods", "Underhill Haulage", "Vellacott Supply",
     "Westerdale Grocers"], 1)]
NEW_FAIL = [
    _row(41, "Yarrowfield Analytics", place="Austin, Texas, United States"),
    _row(42, "Zennor Data", place="Remote - USA"),
    _row(43, "Ashcombe Robotics", place="Seattle, WA, United States"),
    _row(44, "Bramblecote Staffing"),
    _row(45, "Coldharbour Recruitment Staffing"),
    _row(46, "Copperleaf Casino"),
    _row(47, "Ivybridge Studio", title="Pricing Analyst"),
    _row(48, "Harrowgate Insurance", desc=GOOD + " Fluency in Welsh is essential for this role."),
    _row(49, "Fernhill Freight", title="Operations Analyst (Hybrid)"),
    _row(50, "Larkspur Retail", title="Senior Supply Chain Analyst"),
    _row(51, "Alderbank Freight", url="https://careers.example/alderbank/88"),
    _row(52, "Quillfield Retail", score=False),
]


@pytest.fixture
def state(tmp_path, monkeypatch):
    """The example person's state, copied: their tracker holds an application to Larkspur
    Retail and a draft for Fernhill Freight; an earlier search of 12 is on their page; the
    person's bar is stated, one employer judged since as clearing none of it and one turned
    down by name."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    rounds = st / "documents" / "rounds"
    rounds.mkdir(parents=True)
    (rounds / "r7.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "desc"} for r in EARLIER_PASS[:3] + EARLIER_FAIL[:3]
         + EARLIER_PASS[3:] + EARLIER_FAIL[3:]]), encoding="utf-8")
    monkeypatch.setattr(sector, "AGENCY", re.compile(r"\bstaffing\b", re.I))
    monkeypatch.setattr(bar, "FRONTIER", {"frontier example labs"})
    judged = tmp_path / "employers_judged.json"
    monkeypatch.setattr(bar, "_judged_path", lambda: str(judged))
    bar.judge("Ivybridge Studio", bar.NONE, "a two-person design studio", today="2026-11-04")
    monkeypatch.setattr(run_round, "declined_now", lambda: {
        company_key("Juniper Gaming Group"): "you said no more roles from them"})
    return st


def _top_up(tmp_path, monkeypatch, st, rows, show):
    """run_round.main() as the page's "find N more" runs it, every stage stood in and the
    ranked shortlist `rows`."""
    def stage(cmd, log, deadline=None, ok=(0,)):
        if os.path.basename(cmd[1]) == "throttle.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(rows, fh)

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd: 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(tmp_path / "r8"), "--from-scraped", str(scraped),
        "--seen", str(st / "job_scraper" / "seen_jobs.json"),
        "--tracker", str(st / "job_search_tracker.csv"),
        "--summary-dir", str(st / "documents" / "rounds"),
        "--today", TODAY, "--jobage", "14", "--show", str(show), "--pages", "1"])
    run_round.main()


def _found(rows):
    """The page's Found list: what it offers to draft, and what is drafted already."""
    return {r["draft_work"]["args"]["url"] for r in rows if r["status"] in ("new", "ready")}


def _urls(rows):
    return {r["url"] for r in rows}


def test_a_top_up_leaves_only_the_rows_that_pass_on_the_page(tmp_path, monkeypatch, capsys,
                                                             state):
    ranked = sorted(NEW_PASS + NEW_FAIL, key=lambda r: -(r.get("priority") or 0))
    assert len(EARLIER_PASS + EARLIER_FAIL + NEW_PASS + NEW_FAIL) == 37
    _top_up(tmp_path, monkeypatch, state, ranked, 20)
    out = capsys.readouterr().out
    jobs = app_model._jobs(app_model.Ctx(dt.date.fromisoformat(TODAY), NOW), {})
    passing = _urls(EARLIER_PASS + NEW_PASS)
    assert len(passing) == 19
    assert _found(jobs["rows"]) == passing
    # Nothing failing is anywhere on Jobs as a find, and the count says only the 19.
    failing = _urls(EARLIER_FAIL + NEW_FAIL)
    assert not failing & {r["draft_work"]["args"]["url"] for r in jobs["rows"]}
    assert jobs["summary"].startswith("13 roles from the last search to look at")
    assert "6 more from earlier searches" in jobs["summary"]
    assert "found 13 of the 20 asked for" in out
    assert "left out: 16 that fail a rule, taken off your Jobs list" in out

    # Each one left out is on the search's left-out list with its reason: all but the one
    # with no score, and the application itself under its own link, which stays the
    # application. Each failing a rule is a ruling, with that reason; a copy of a job the
    # person has is left out by the page's own read of the same rules, never ruled on.
    seen = exclude.load_seen(str(state / "job_scraper" / "seen_jobs.json"))["seen"]
    ruled = {e["url"]: e["exclusion_reason"] for e in seen.values()
             if e.get("status") == "excluded" and e.get("basis") == "rules"}
    own = {"https://example.com/jobs/1", NEW_FAIL[-1]["url"]}
    copies = {NEW_FAIL[-2]["url"], NEW_FAIL[-3]["url"], NEW_FAIL[-4]["url"],
              EARLIER_FAIL[-1]["url"]}
    assert set(ruled) & (failing | passing) == failing - own - copies
    by = {(r["company"], r["title"], r["url"]): r["url"] for r in EARLIER_FAIL + NEW_FAIL}
    listed = filtered.load("r8", str(state / "documents" / "rounds"))["filtered"]
    said = {e["url"]: e["reason"] for e in listed}
    assert set(said) == failing - own
    assert all(said.values())
    assert all(ruled[u] == said[u] for u in set(ruled) & set(said))
    why = {k[:2]: said[u] for k, u in by.items() if u in said}
    assert why[("Galeworth Systems", "Data Analyst")].startswith("place: outside United Kingdom")
    assert why[("Zennor Data", "Data Analyst")].startswith("place: remote but anchored outside")
    assert why[("Ivybridge Studio", "Pricing Analyst")] == (
        "candidate's bar: clears none of pay, prestige or signal (a two-person design studio)")
    assert why[("Juniper Gaming Group", "Data Analyst")] == (
        "candidate's bar: you said no more roles from them")
    assert why[("Copperleaf Casino", "Data Analyst")].startswith("candidate's bar: a sector")
    assert why[("Bramblecote Staffing", "Data Analyst")].endswith("employer is not named")
    assert "Welsh stated as a requirement" in why[("Harrowgate Insurance", "Data Analyst")]
    assert why[("Larkspur Retail", "Senior Supply Chain Analyst")].startswith(
        "already in your applications: Senior Supply Chain Analyst (applied, 2026-09-08)")
    assert why[("Fernhill Freight", "Operations Analyst (Hybrid)")].startswith("already drafted")
    assert said[NEW_FAIL[-2]["url"]] == "already on your list, from search r7"
    assert said[EARLIER_FAIL[-1]["url"]] == "already on your list, from search r7"

    # Brought back from the left-out list, one is on Jobs again with its score.
    filtered.back("r8", ["Yarrowfield Analytics::Data Analyst"], why="I can move for this one",
                  summary_dir=str(state / "documents" / "rounds"), today=TODAY,
                  seen_path=str(state / "job_scraper" / "seen_jobs.json"))
    again = app_model._jobs(app_model.Ctx(dt.date.fromisoformat(TODAY), NOW), {})
    back = [r for r in again["rows"] if r["company"] == "Yarrowfield Analytics"]
    assert [(r["status"], r["score"]) for r in back] == [("new", NEW_FAIL[0]["fit"])]
    assert _found(again["rows"]) == passing | {NEW_FAIL[0]["url"]}


def test_a_row_on_the_page_that_fails_now_leaves_it_before_any_search(tmp_path, monkeypatch,
                                                                      state):
    """No search has run since the rules caught up: the page's own read leaves the failing
    rows out at once, and Bring back on one still works."""
    rounds = state / "documents" / "rounds"
    (rounds / "r8.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "desc"} for r in NEW_PASS[:4] + NEW_FAIL[:3]]),
        encoding="utf-8")
    ctx = app_model.Ctx(dt.date.fromisoformat(TODAY), NOW)
    jobs = app_model._jobs(ctx, {})
    assert _found(jobs["rows"]) == _urls(EARLIER_PASS + NEW_PASS[:4])
    aside = {r["company"]: r for r in jobs["rows"] if r["status"] == "dismissed"}
    assert set(aside) == {"Yarrowfield Analytics", "Zennor Data", "Ashcombe Robotics"}
    assert aside["Yarrowfield Analytics"]["notes"][-1].startswith(
        "Left out: Not where you can work: outside United Kingdom")
    import app_actions

    class _W:
        def add(self, *a, **k):
            pass

    t = {"kind": "job", "url": NEW_FAIL[0]["url"], "company": "Yarrowfield Analytics",
         "title": "Data Analyst", "round": "r8", "rank": 5}
    run = app_actions.Run("a1", {"action": "job.bring_back", "at": "2026-11-05T21:00:00Z",
                                 "value": {}}, t, {"work": {}}, _W(), "cloud-1", "UTC", NOW)
    assert "is back" in app_actions._job_bring_back(run)["note"]
    again = app_model._jobs(app_model.Ctx(dt.date.fromisoformat(TODAY), NOW), {})
    assert NEW_FAIL[0]["url"] in _found(again["rows"])


def test_a_remote_role_in_the_neighbouring_country_passes_only_if_it_hires_from_home(
        monkeypatch):
    """The location gate flags a remote role anchored in the one neighbouring country: it
    passes only when the employer explicitly hires from home, which its place cannot show
    (prefilter.py). The cut reads the posting: one that never says so is left out."""
    import prefilter
    said = "remote, anchored in the neighbouring country"
    monkeypatch.setattr(prefilter, "_NB", {"remote_reason": said})
    monkeypatch.setattr(prefilter, "location_verdict", lambda place, title="": (
        ("FLAG", said) if "Neighbourland" in place else ("PASS", "home")))
    row = _row(60, "Marlpit Software", place="Remote, Neighbourland")
    assert run_round.place_rule(row) == (f"place: {said}, and the posting never says it hires "
                                         f"from {prefilter._HOME}")
    hires = dict(row, desc=GOOD + " This role is open to candidates based anywhere in the UK.")
    assert run_round.place_rule(hires) == ""
    # A saved shortlist keeps no posting: its row is left as the gate left it, ranked down.
    assert run_round.place_rule({k: v for k, v in row.items() if k != "desc"}) == ""
    assert run_round.place_rule(_row(61, "Marlpit Software")) == ""
