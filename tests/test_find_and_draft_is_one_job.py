""""Find N jobs and draft them all" is one job: the search drafts each job as it is found.

The maintainer's "find jobs and draft them all" on 5 November took two searches and 13 chats
run by hand. A search asked to draft what it finds (args.draft, the page's Find jobs) now
keeps searching until N rows pass every rule (the shortlist's own function), takes the
failing ones off the page in the same step, and queues a draft of each passing row as it is
found, claimed with the search, so its own chat drafts them together (page_db.search_drafts).
Its one card counts them, "x of N drafted", and each finished draft is in Drafts as it lands.

Here: a search for 5 ranks 9, 4 of them failing. Every person and employer is invented.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402
import app_model  # noqa: E402
import exclude  # noqa: E402
import filtered  # noqa: E402
import page_db  # noqa: E402
import run_round  # noqa: E402
import sector  # noqa: E402

TODAY = "2026-11-05"
NOW = "2026-11-05T21:00:00Z"
CHAT = "cloud-7"
SID = "search~20261105T2040-abcd"
GOOD = "You will build SQL and Python reporting for the planning team."
LEEDS = "Leeds, England, United Kingdom"


def _row(n, company, title="Data Analyst", place=LEEDS, desc=GOOD):
    return {"title": title, "company": company, "date": TODAY, "first_seen": TODAY,
            "portal": "linkedin", "desc": desc, "location": place, "fit": 95 - n,
            "priority": 98 - n, "url": f"https://www.linkedin.com/jobs/view/{7000 + n}/"}


PASS = [_row(1, "Kettlewell Foods"), _row(3, "Lowfold Haulage"), _row(5, "Marchbank Retail"),
        _row(7, "Netherby Grocers"), _row(9, "Oakhurst Freight")]
FAIL = [_row(2, "Yarrowfield Analytics", place="Austin, Texas, United States"),
        _row(4, "Bramblecote Staffing"),
        _row(6, "Harrowgate Insurance", desc=GOOD + " Fluency in Welsh is essential."),
        _row(8, "Larkspur Retail", title="Senior Supply Chain Analyst")]


@pytest.fixture
def page(tmp_path, monkeypatch):
    """The example person's state, copied, and the page's database as the search's own chat
    read it: the search, asked for 5 and to draft them, claimed by that chat."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(sector, "AGENCY", re.compile(r"\bstaffing\b", re.I))
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    item = {"kind": "search", "title": "Finding jobs and drafting them", "to": "cloud",
            "args": {"note": None, "size": 5, "draft": True}, "status": "running",
            "claimed_by": CHAT, "claimed_at": "2026-11-05T20:41:00Z",
            "lease_until": "2026-11-05T21:30:00Z", "asked_at": "2026-11-05T20:40:00Z",
            "stage": 1, "stage_at": "2026-11-05T20:42:00Z", "priority": 0,
            "stages": [{"name": s["name"], "est_s": s["est_s"]}
                       for s in page_db.progress("search")["stages"]]}
    (dump / "work" / (SID.replace("~", "@") + ".json")).write_text(
        json.dumps(dict(item, _v=4)), encoding="utf-8")
    return st, str(dump)


def _round(tmp_path, monkeypatch, st, rows):
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
        "run_round.py", "--out", str(tmp_path / "r4"), "--from-scraped", str(scraped),
        "--seen", str(st / "job_scraper" / "seen_jobs.json"),
        "--tracker", str(st / "job_search_tracker.csv"),
        "--summary-dir", str(st / "documents" / "rounds"), "--today", TODAY, "--jobage", "14",
        "--show", "5", "--pages", "1", "--expand"])
    run_round.main()


def _app(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = app.main(list(argv))
    assert code == 0, out.getvalue()
    return json.loads(out.getvalue())


def _work(dump):
    return {k: d["data"] for k, d in page_db.load(dump)["work"].items()}


def _lists():
    """The page's Found list (jobs to draft) and its Drafts list, by employer."""
    m, _ = app_model.build(dt.date.fromisoformat(TODAY), app_model.parse_time(NOW),
                           only=("jobs", "ready"))
    found = {r["company"] for r in m["jobs"]["rows"] if r["status"] == "new"}
    drafts = {r["company"] for r in m["ready"] if r["status"] == "drafted"}
    return found, drafts


def _drafted(st, row):
    """What the drafting path leaves for one job (record_drafts.py): its tracker row."""
    path = st / "job_search_tracker.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    head = list(rows[0])
    rows.append({**{k: "" for k in head}, "date": TODAY, "company": row["company"],
                 "role": row["title"], "status": "drafted", "fit_rating": str(row["fit"]),
                 "cv_file": f"cv/Morgan_Ellis_CV_{row['company'].split()[0]}.tex",
                 "source": row["url"]})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)


def test_a_search_for_five_drafts_the_five_that_pass_and_counts_them(tmp_path, monkeypatch,
                                                                     page):
    st, dump = page
    _round(tmp_path, monkeypatch, st, sorted(PASS + FAIL, key=lambda r: -r["priority"]))
    # The four that fail are off the page in the same step, each with its reason.
    seen = exclude.load_seen(str(st / "job_scraper" / "seen_jobs.json"))["seen"]
    ruled = {e["company"]: e["exclusion_reason"] for e in seen.values()
             if e.get("status") == "excluded" and e.get("basis") == "rules"}
    assert ruled["Yarrowfield Analytics"].startswith("place: ")
    assert ruled["Bramblecote Staffing"].endswith("employer is not named")
    assert "Welsh stated as a requirement" in ruled["Harrowgate Insurance"]
    left = {e["company"]: e["reason"] for e in filtered.load(
        "r4", str(st / "documents" / "rounds"))["filtered"]}
    assert set(left) == {r["company"] for r in FAIL}
    assert left["Larkspur Retail"].startswith("already in your applications")
    found, drafts = _lists()
    assert found == {r["company"] for r in PASS}
    assert drafts == {"Fernhill Freight"}                    # the example person's own draft

    got = _app("search-drafts", dump, "--work", SID, "--chat", CHAT, "--last",
               "--today", TODAY, "--now", NOW)
    assert [q["company"] for q in got["queued"]] == [r["company"] for r in PASS]
    work = _work(dump)
    mine = [w for w in work.values() if w.get("for_search") == SID]
    assert len(mine) == 5
    assert all(w["kind"] == "draft" and w["status"] == "claimed" and w["with"] == SID
               and w["claimed_by"] == CHAT for w in mine)
    s = work[SID]
    assert s["count"] == {"done": 0, "total": 5, "word": "drafted"}
    assert s["stages"][s["stage"]]["name"] == "Drafting each one"
    # The queue offers none of them to another chat: they are this search's own.
    assert page_db.next_item(page_db.load(dump), "cloud", app_model.parse_time(NOW),
                             cap=10) is None
    # The search's pin renews its drafts and leaves them their own stages and count.
    _app("pin", dump, "--work", SID, "--chat", CHAT, "--stage", "draft", "--line",
         "Drafting the 5 jobs it found", "--now", "2026-11-05T21:05:00Z")
    work = _work(dump)
    assert all(w["lease_until"] > "2026-11-05T21:30" and w["stage"] == 0 and "count" not in w
               for w in work.values() if w.get("for_search") == SID)
    assert work[SID]["count"] == {"done": 0, "total": 5, "word": "drafted"}

    ids = {w["args"]["url"]: k for k, w in work.items() if w.get("for_search") == SID}
    for n, row in enumerate(PASS, 1):
        _drafted(st, row)
        done = _app("done", dump, "--work", ids[row["url"]], "--chat", CHAT, "--summary",
                    f"Your CV and letter for {row['company']} are ready.", "--now", NOW)
        assert done["search"] == SID
        s = _work(dump)[SID]
        assert s["count"] == {"done": n, "total": 5, "word": "drafted"}
        found, drafts = _lists()
        assert drafts == {"Fernhill Freight"} | {r["company"] for r in PASS[:n]}
        assert found == {r["company"] for r in PASS[n:]}
        assert s["status"] == ("done" if n == 5 else "running")
    assert s["result"]["summary"] == "Found 5 jobs that pass every rule, and drafted all 5."


def test_a_draft_not_begun_whose_job_fails_a_rule_now_is_stopped_and_the_next_taken(
        tmp_path, monkeypatch, page):
    """The search found its first shortlist and queued its drafts; meanwhile an employer was
    turned down by name. Its draft, not begun, is stopped with why, and the next job is taken."""
    st, dump = page
    _round(tmp_path, monkeypatch, st, sorted(PASS + FAIL, key=lambda r: -r["priority"])[:7])
    first = _app("search-drafts", dump, "--work", SID, "--chat", CHAT, "--today", TODAY,
                 "--now", NOW)
    assert len(first["queued"]) == 4
    assert _work(dump)[SID]["count"]["total"] == 5        # still searching: 5 asked for
    from company_key import key as company_key
    monkeypatch.setattr(run_round, "declined_now", lambda: {
        company_key("Lowfold Haulage"): "you said no more roles from them"})
    _round(tmp_path, monkeypatch, st, sorted(PASS + FAIL, key=lambda r: -r["priority"]))
    again = _app("search-drafts", dump, "--work", SID, "--chat", CHAT, "--last",
                 "--today", TODAY, "--now", NOW)
    work = _work(dump)
    gone = work[again["stopped"][0]]
    assert gone["args"]["company"] == "Lowfold Haulage" and gone["status"] == "stopped"
    assert "no more roles from them" in gone["result"]["summary"]
    assert [q["company"] for q in again["queued"]] == ["Oakhurst Freight"]
    assert work[SID]["count"] == {"done": 0, "total": 4, "word": "drafted"}


def test_a_draft_that_stops_on_a_hard_rule_takes_its_job_off_jobs(tmp_path, monkeypatch, page):
    st, dump = page
    _round(tmp_path, monkeypatch, st, sorted(PASS, key=lambda r: -r["priority"]))
    _app("search-drafts", dump, "--work", SID, "--chat", CHAT, "--last", "--today", TODAY,
         "--now", NOW)
    wid = next(k for k, w in _work(dump).items() if w.get("args", {}).get("company")
               == "Netherby Grocers")
    _app("done", dump, "--work", wid, "--chat", CHAT, "--left-out",
         "the posting says the role is only open in Dublin", "--now", NOW)
    w = _work(dump)
    assert w[wid]["status"] == "stopped"
    assert w[wid]["result"]["summary"] == ("Not drafted: the posting says the role is only "
                                           "open in Dublin.")
    # Its reason is kept as a left-out, so the page says it and offers no Try again (the
    # maintainer, 2026-11-06: Try again drafted a job already ruled out).
    assert w[wid]["result"]["left_out"] == "the posting says the role is only open in Dublin", w[wid]
    found, _drafts = _lists()
    assert "Netherby Grocers" not in found
    seen = exclude.load_seen(str(st / "job_scraper" / "seen_jobs.json"))["seen"]
    assert any(e.get("company") == "Netherby Grocers" and e.get("basis") == "rules"
               and e.get("status") == "excluded" for e in seen.values())
    assert w[SID]["count"] == {"done": 0, "total": 5, "word": "drafted"}


def test_a_job_left_out_is_dated_by_the_persons_own_day(tmp_path, monkeypatch, page):
    """--left-out dated its ruling with the computer's UTC date: for a person ahead of UTC it
    was ruled out "yesterday" late in their evening. The person's own day dates it."""
    import person
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("state"))
    pj = prof / "person.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["time_zone"] = "Pacific/Auckland"                 # 21:00 UTC is the next morning
    pj.write_text(json.dumps(data, indent=2), encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(prof))
    person._modules.clear()
    person._data.clear()
    st, dump = page
    _round(tmp_path, monkeypatch, st, sorted(PASS, key=lambda r: -r["priority"]))
    _app("search-drafts", dump, "--work", SID, "--chat", CHAT, "--last", "--today", TODAY,
         "--now", NOW)
    wid = next(k for k, w in _work(dump).items() if w.get("args", {}).get("company")
               == "Netherby Grocers")
    _app("done", dump, "--work", wid, "--chat", CHAT, "--left-out",
         "the posting says the role is only open in Dublin", "--now", NOW)
    seen = exclude.load_seen(str(st / "job_scraper" / "seen_jobs.json"))["seen"]
    [entry] = [e for e in seen.values() if e.get("company") == "Netherby Grocers"]
    assert entry["excluded_date"] == "2026-11-06", entry
    person._modules.clear()
    person._data.clear()


def test_the_search_s_own_chat_is_told_to_draft_what_it_finds(page):
    """The steps a search's chat is given (app.py job_steps, for its child chat and for
    next --job-chat) say to queue the drafts as each shortlist lands and draft them together."""
    _st, dump = page
    item = page_db.load(dump)["work"][SID]["data"]
    queued = dict(item, status="queued", claimed_by=None, claimed_at=None, lease_until=None,
                  stage=0, stage_at=None)
    with open(os.path.join(dump, "work", SID.replace("~", "@") + ".json"), "w",
              encoding="utf-8") as fh:
        json.dump(dict(queued, _v=5), fh)
    chosen = page_db.next_item(page_db.load(dump), "cloud", app_model.parse_time(NOW), cap=10)
    assert chosen["draft_all"] == 5
    assert [s["key"] for s in chosen["stages"]][-1] == "draft"
    steps = "\n".join(app.job_steps(chosen, CHAT, "https://claude.ai/artifact/x"))
    assert f"app.py search-drafts \"$D\" --work {SID} --chat {CHAT}" in steps
    assert app.work_row("draft").rstrip(".") in steps
    assert "never app.py done it yourself" in steps
