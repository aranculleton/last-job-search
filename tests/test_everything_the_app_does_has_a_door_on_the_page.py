"""Everything the app does has a door on the page, with a writer behind it.

CAPABILITY_MAP.md (2026-10-25) section 3, the engine halves: setup's answers move setup on;
where Claude works, row by row; a resume added on the page saved from its file store; a job
added by link, and one applied for elsewhere; unaccepted requests withdrawn together, never
nudged; what it learned, each rule removable; the search's own settings changed through
the files the chat writes, and a kind of job left out brought back; the resume for no
named role; a break that holds every follow-up; one tip in the page's words and the tour;
a look at their own profile as a To do card; outside steps worded for the page. Every
writer is applied once and can be taken back. Every person and employer is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_setup  # noqa: E402
import app_state  # noqa: E402
import claude_surfaces  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402
from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy  # noqa: E402

WREN = "fernhill_freight_halloway"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _contact(search, cid):
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == cid)


def _threads(search):
    with open(os.path.join(search.state, "network_threads.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ G3: where Claude works


def test_where_claude_works_is_four_rows_each_with_its_state_and_next_step(search):
    w = search.model()["where"]
    assert w["helper"]["state"] == "not_set_up" and "computer is off" in w["helper"]["say"]
    assert w["reading"]["state"] == "open_in_app"
    assert w["computer"]["state"] == "optional"
    assert w["brief"] == {"state": "ready", "when": "Mondays and Thursdays at 7:56",
                          "say": "Your brief comes Mondays and Thursdays at 7:56."}
    # The listener as this copy last saw it (tools/app_listen.py keeps it beside the copy's
    # git folder; with none, in the folder itself): the helper took the page.
    import app_listen
    with open(os.path.join(search.state, "." + app_listen.CACHE), "w", encoding="utf-8") as fh:
        json.dump({"listener": {"chat": "session_EXAMPLEHELPER", "kind": "cloud",
                                "title": "Job search: Claude's helper", "helper": True,
                                "since": "2026-10-25T17:00:00Z",
                                "seen_at": "2026-10-25T17:55:00Z", "confirmed": True}}, fh)
    m = search.model()
    assert m["where"]["helper"]["state"] == "ready"
    lis = m["listener"]
    seen = lis["seen"]
    assert (seen["title"], seen["kind"], seen["helper"], seen["seen_recently"]) == (
        "Job search: Claude's helper", "cloud", True, True)
    assert lis["doc"] == "meta/listener" and lis["wake"]["label"] == "Wake Claude"


# ------------------------------------------------------------------ G6: the resume from the file store


def test_a_resume_added_on_the_page_is_saved_from_the_file_store(tmp_path):
    fresh = Copy(str(tmp_path))
    aid = fresh.act("setup.resume", "setup-resume", value={"asset": "d4" * 16,
                                                           "name": "My resume.pdf"})
    first = fresh.apply()
    assert first["ok"] == [aid]
    # Without the file fetched, it is noted to fetch, as before; with it, saved at once.
    assert fresh.answers()["resume"]["asset"] == "d4" * 16
    assets = os.path.join(str(tmp_path), "assets")
    os.makedirs(assets)
    with open(os.path.join(assets, "d4" * 16 + ".pdf"), "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    again = fresh.act("setup.resume", "setup-resume", value={"asset": "d4" * 16,
                                                             "name": "My resume.pdf"})
    got = fresh.apply("--assets", assets)
    assert got["ok"] == [again], fresh.receipt(again)
    assert fresh.receipt(again)["remove_assets"] == ["d4" * 16]
    saved = fresh.answers()["resume"]
    assert saved["file"].startswith("documents/cv/resume_added_") and "asset" not in saved
    assert saved["file"].endswith(".pdf")
    assert os.path.isfile(os.path.join(fresh.state, *saved["file"].split("/")))


# ------------------------------------------------------------------ G7: a job added, or applied elsewhere


def test_a_job_added_by_its_link_is_scored_before_anything_else(search):
    aid = search.act("job.add", "job-new", value={"url": "https://jobs.example/wren/planner"},
                     rev="")
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    batch = json.load(open(got["batches"][0], encoding="utf-8"))
    work = next(e for e in batch if e["collection"] == "work")
    doc = json.load(open(work["file_path"], encoding="utf-8"))
    assert doc["kind"] == "evaluate" and doc["args"]["url"] == "https://jobs.example/wren/planner"
    # The chat that scores it keeps the row; the page shows it first.
    out = search.run("model", "--now", NOW)
    assert out
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    import subprocess
    row = os.path.join(str(search.dump), "row.json")
    with open(row, "w", encoding="utf-8") as fh:
        json.dump({"title": "Planner", "company": "Wren Health", "fit": 71,
                   "url": "https://jobs.example/wren/planner",
                   "fit_why": ["+10 planning and SQL asked and held"]}, fh)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "added_jobs.py"), "add", row],
                       env=env, capture_output=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout
    first = search.model()["jobs"]["rows"][0]
    assert (first["id"], first["company"], first["added"]) == ("added-1", "Wren Health", True)
    assert "You added this one." in first["notes"]
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "added_jobs.py"), "add", row],
                       env=env, capture_output=True, encoding="utf-8")
    assert "brought up to date" in r.stdout          # the same posting twice is one row


def test_an_application_made_elsewhere_is_recorded_with_its_day(search):
    aid = search.act("job.applied", "job-new", rev="",
                     value={"company": "Wren Health", "role": "Planner", "on": "2026-10-21",
                            "url": "https://jobs.example/wren/planner"})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    row = search.tracker_row("Wren Health")
    assert (row["status"], row["applied_on"], row["role"]) == ("applied", "2026-10-21", "Planner")


# ------------------------------------------------------------------ G8: requests nobody accepted


def _pending(search):
    path = os.path.join(search.state, "network_threads.csv")
    rows = app_state._csv_rows(path)
    for r in rows:
        if r["contact_id"] == WREN:
            r.update(channel="connection", scenario="connection_note")
    app_state._save_csv(path, rows, list(rows[0].keys()))


def test_requests_nobody_accepted_are_one_row_to_withdraw_never_a_nudge(search):
    _pending(search)
    m = search.model()
    row = next(d for d in m["due"] if d["kind"] == "withdraw")
    assert row["who"] == [{"contact": WREN, "first_name": "Wren", "employer": "Fernhill Freight"}]
    assert row["done"] == {"action": "requests.withdrawn", "label": "I withdrew them"}
    assert not any(d["kind"] == "nudge" and d.get("item") == WREN for d in m["due"])
    claude_surfaces.entry(row["steps"])                       # its steps are in the registry
    before = len(_threads(search))
    aid = search.act("requests.withdrawn", row["id"], rev=row["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert len(_threads(search)) == before + 1
    assert not any(d["kind"] == "withdraw" for d in search.model()["due"])
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    assert len(_threads(search)) == before


# ------------------------------------------------------------------ G9: what it learned


def test_each_rule_it_learned_is_shown_and_can_be_removed(search):
    import subprocess
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'tools')\n"
                    "import learned\nlearned.record('voice', 'too formal', 'Plain and direct, "
                    "no stock pleasantries', today='2026-10-20', answers=False)"],
                   env=env, cwd=ROOT, check=True)
    (rule,) = search.model()["learned"]
    assert rule["rule"] == "Plain and direct, no stock pleasantries"
    assert rule["said"] == "too formal" and rule["area"] == "voice"
    aid = search.act("learned.retire", rule["id"], rev=rule["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.model()["learned"] == []
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    assert len(search.model()["learned"]) == 1


# ------------------------------------------------------------------ G10: your search


def test_the_search_settings_are_read_and_written_through_the_profiles_own_file(search):
    s = search.model()["search"]
    assert "supply chain analyst" in s["roles"] and s["pay"]["floor"] == 42000
    assert {p["name"] for p in s["portals"]} >= {"linkedin-search", "freehire-search"}
    aid = search.act("search.set", "search-settings", rev=s["rev"],
                     value={"what": "pay", "value": 45000})
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    assert search.model()["search"]["pay"]["floor"] == 45000
    batch = json.load(open(got["batches"][0], encoding="utf-8"))
    assert any(e["collection"] == "work" and e["doc_id"].startswith("search~") for e in batch)
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    assert search.model()["search"]["pay"]["floor"] == 42000
    s = search.model()["search"]
    off = search.act("search.set", "search-settings", rev=s["rev"],
                     value={"what": "sites", "name": "freehire-search", "on": False})
    search.written_back()
    assert search.apply()["ok"] == [off]
    sites = {p["name"]: p["on"] for p in search.model()["search"]["portals"]}
    assert sites["freehire-search"] is False and sites["linkedin-search"] is True


def test_a_kind_of_job_left_out_is_shown_and_brought_back(search):
    for rank in (1, 4):
        job = next(r for r in search.model()["jobs"]["rows"] if r["rank"] == rank)
        search.act("job.dismiss", job["id"], value="too junior", rev=job["rev"])
        search.apply()
        search.written_back()
    rule = next(r for r in search.model()["search"]["rules"] if r["words"] == "too junior")
    assert rule["count"] == 2
    aid = search.act("rule.lift", rule["id"], rev=rule["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    statuses = {r["rank"]: r["status"] for r in search.model()["jobs"]["rows"]}
    assert statuses[1] != "dismissed" and statuses[4] != "dismissed"
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    statuses = {r["rank"]: r["status"] for r in search.model()["jobs"]["rows"]}
    assert statuses[1] == "dismissed" and statuses[4] == "dismissed"


# ------------------------------------------------------------------ G12: your resume


def test_the_resume_for_no_named_role_is_in_the_model_with_its_download(search):
    r = search.model()["resume"]
    assert r["file"] is None and r["work"]["kind"] == "general_resume"
    cv = os.path.join(search.state, "documents", "cv")
    os.makedirs(cv, exist_ok=True)
    with open(os.path.join(cv, "Morgan_Ellis_CV_current.pdf"), "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    r = search.model()["resume"]
    assert r["file"]["name"] == "Morgan_Ellis_CV_current.pdf" and r["made_on"]
    assert r["get"]["kind"] == "files"


# ------------------------------------------------------------------ G13: taking a break


def test_a_break_holds_every_follow_up_until_its_day_and_resume_lifts_it(search):
    """One break, kept by tools/routines.py whichever door it came through (the search's
    settings or the brief's row): the same holds, the same record, the same undo."""
    before_due = search.model()["due"]
    assert any(d["item"] == WREN for d in before_due)
    s = search.model()["search"]
    aid = search.act("brief.pause", "search-settings", value="2026-11-08", rev=s["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.receipt(aid)["note"].startswith("Your search is paused until 8 Nov.")
    m = search.model()
    assert m["search"]["pause"] == {"until": "2026-11-08", "since": "2026-10-25"}
    assert m["schedule"]["paused"]["until"] == "2026-11-08"
    assert not any(d["item"] == WREN for d in m["due"])
    assert _contact(search, WREN)["next_action"].startswith(
        "HOLD until 2026-11-08 (search paused 2026-10-25): ")
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back], search.receipt(back)
    m = search.model()
    assert m["search"]["pause"] is None and m["schedule"]["paused"] is None
    assert _contact(search, WREN)["next_action"] == "One nudge if no reply"
    assert any(d["item"] == WREN for d in m["due"])
    assert "chase again (search resumed)" in search.tracker_row("Larkspur Retail")["notes"]


# ------------------------------------------------------------------ G15: a tip and the tour


def test_one_tip_in_the_page_words_and_the_tour(search):
    h = search.model()["help"]
    tip = h["tip"]
    assert tip["area"] == "search" and "in Chat" in tip["text"] and "Tell me" not in tip["text"]
    assert [t["key"] for t in h["tour"]][:2] == ["todo", "jobs"]
    aid = search.act("tip.seen", tip["id"], rev=tip["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    after = search.model()["help"]["tip"]
    assert after is None or after["id"] != tip["id"] or after["text"] != tip["text"]


# ------------------------------------------------------------------ G16, G17


def test_a_look_at_their_own_profile_is_a_to_do_card_and_no_thanks_is_kept(search):
    # The example person said no to this once; that no taken off, it was never looked over.
    asked = os.path.join(search.profile, "asked.json")
    with open(asked, encoding="utf-8") as fh:
        nos = json.load(fh)
    nos.pop("own-profile-review", None)
    with open(asked, "w", encoding="utf-8") as fh:
        json.dump(nos, fh)
    m = search.model()
    card = next(n for n in m["needs_you"] if n["id"] == "q-own-profile")
    assert card["kind"] == "suggest" and card["options"][0]["work"]["kind"] == "own_profile"
    assert card["body"].startswith("Never looked over")
    assert not any(n["id"] == "q-upgrade-own-profile-review" for n in m["needs_you"])
    aid = search.act("needs.answer", "q-own-profile", value="no", rev=card["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert not any(n["id"] == "q-own-profile" for n in search.model()["needs_you"])


def test_steps_on_a_page_card_never_say_this_chat():
    for eid in ("cloud-internet", "cloud-setup-script", "browser-pane-stay-signed-in"):
        lines = claude_surfaces.steps(eid, page=True)
        assert lines[-1].endswith("tap Done."), lines
        assert not any("this chat" in ln.lower() or "say done" in ln.lower() for ln in lines)
    item = app_setup.outside_item("job-sites")
    assert not any("this chat" in ln.lower() for ln in item["steps"])


# ------------------------------------------------------------------ G1: setup moves on


def test_each_setup_answer_the_page_sends_is_applied_and_moves_setup_on(tmp_path):
    fresh = Copy(str(tmp_path))
    values = {"resume": ("setup.resume", {"text": "Morgan Ellis, analyst, five years of SQL."}),
              "work": ("setup.answer", {"work": "Planning analyst", "place": "Leeds"}),
              "right_to_work": ("setup.answer", {"answer": "yes"}),
              "pay": ("setup.skip", None),
              "roles": ("setup.answer", {"roles": ["Planning analyst"]}),
              "avoid": ("setup.skip", None)}
    done = []
    setup = fresh.model()["setup"]
    while setup["next"]:
        nxt = setup["next"]
        action, value = values[nxt]
        aid = fresh.act(action, f"setup-{nxt}", value=value)
        got = fresh.apply()
        assert got["ok"] == [aid], fresh.receipt(aid)
        setup = fresh.model()["setup"]
        assert setup["next"] != nxt, nxt             # the answer moved setup on
        done.append(nxt)
        assert len(done) <= 6
    assert done[0] == "resume" and setup["progress"]["done"] >= 4
