"""The page's own payloads are applied by the engine as the person meant them.

LEGACY_AUDIT.md (2026-10-25), section 1: the page and the engine were built against each
other's tests, not each other, so a setup answer, a settings change and a resume pasted on
the page were refused or misread while the suite passed. Each payload here is the one the
page sends (templates/app/app.js), and the shape each takes is recorded in CONTRACT.md 6.13.
One writer, reader or id each, too: person.json, LINKEDIN_PLAN, the tracker, the name a
message greets by, a draft's work id, and a document put in the page's file store.
Every person here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import tone  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, NOW, Search  # noqa: E402
from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


@pytest.fixture
def fresh(tmp_path):
    return Copy(str(tmp_path))


# ------------------------------------------------------------------ setup


def test_a_setup_answer_as_the_page_sends_it_is_saved(fresh):
    aid = fresh.act("setup.answer", "setup-work",
                    value={"step": "work", "answers": {"work": "Analyst", "place": "Leeds"}})
    got = fresh.apply()
    assert got["ok"] == [aid], fresh.receipt(aid)
    saved = fresh.answers()["work"]
    assert (saved["work"], saved["place"]) == ("Analyst", "Leeds")
    assert fresh.model()["setup"]["next"] != "work"


def test_a_resume_pasted_in_the_setup_card_is_kept_in_the_copy_and_off_the_page(fresh):
    words = "Morgan Ellis\nPlanning analyst, five years of SQL and forecasting."
    aid = fresh.act("setup.answer", "setup-resume",
                    value={"step": "resume", "answers": {"resume": words}})
    claimed = json.loads(fresh.run("apply", fresh.dump, "--chat", "cloud-1", "--now", NOW,
                                   "--claim"))
    batch = json.load(open(claimed["batches"][0], encoding="utf-8"))
    wipe = next(e for e in batch if e["doc_id"] == aid)
    assert json.load(open(wipe["file_path"], encoding="utf-8"))["value"] == {"__delete__": True}
    got = fresh.apply()
    assert got["ok"] == [aid], fresh.receipt(aid)
    saved = fresh.answers()["resume"]
    assert saved["source"] == "pasted" and saved["file"].startswith("documents/cv/")
    with open(os.path.join(fresh.state, *saved["file"].split("/")), encoding="utf-8") as fh:
        assert fh.read().strip() == words


# ------------------------------------------------------------------ settings


@pytest.mark.parametrize("item", ["setting-tips", "setting:tips"])
def test_a_setting_is_one_item_by_either_name_the_page_has_used(search, item):
    s = next(x for x in search.model()["settings"] if x["key"] == "tips")
    assert s["id"] == "setting-tips"
    aid = search.act("setting.set", item, value="off", rev=s["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert next(x for x in search.model()["settings"] if x["key"] == "tips")["value"] == "off"


def test_the_linkedin_plan_is_read_and_written_one_way(search):
    s = next(x for x in search.model()["settings"] if x["key"] == "linkedin_plan")
    aid = search.act("setting.set", s["id"], value="free", rev=s["rev"])
    assert search.apply()["ok"] == [aid]
    with open(os.path.join(search.profile, "networking.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("LINKEDIN_PLAN = ") == 1 and 'LINKEDIN_PLAN = "free"' in text
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    plan = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = ['tools', "
                           "'tools/network']\nimport schema; print(schema.plan(fresh=True))"],
                          env=env, cwd=ROOT, capture_output=True, encoding="utf-8").stdout
    assert plan.strip() == "free"
    assert next(x for x in search.model()["settings"]
                if x["key"] == "linkedin_plan")["value"] == "free"


# ------------------------------------------------------------------ jobs and messages


def test_the_page_bare_values_for_a_day_and_a_reason_are_kept(search):
    job = next(r for r in search.model()["jobs"]["rows"] if r["id"] == "r9-1")
    aid = search.act("job.applied", job["id"], value="2026-10-01", rev=job["rev"])
    assert search.apply()["ok"] == [aid]
    assert search.tracker_row("Brindle Hart Logistics")["applied_on"] == "2026-10-01"
    job = next(r for r in search.model()["jobs"]["rows"] if r["id"] == "r9-4")
    search.written_back()
    aid = search.act("job.dismiss", job["id"], value="pay", rev=job["rev"])
    assert search.apply()["ok"] == [aid]
    seen = json.load(open(os.path.join(search.state, "job_scraper", "seen_jobs.json"),
                          encoding="utf-8"))["seen"]
    assert any(e.get("exclusion_reason") == "pay" for e in seen.values() if isinstance(e, dict))


def test_i_sent_it_with_todays_date_as_its_value_logs_the_drafts_words(search):
    (msg,) = search.model()["messages"]
    aid = search.act("msg.sent", msg["id"], value="2026-10-25", rev=msg["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    import csv
    with open(os.path.join(search.state, "network_threads.csv"), encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["contact_id"] == msg["contact"]]
    assert rows[-1]["full_text"] == msg["body"] and rows[-1]["date"] == "2026-10-25"


def test_one_draft_work_id_for_the_page_and_the_engine(search):
    job = next(r for r in search.model()["jobs"]["rows"] if r["id"] == "r9-1")
    wid = job["draft_work"]["id"]
    assert wid == app_model.draft_work_id(job["apply"]["url"] or "https://jobs.example/"
                                          "brindle/demand", job["company"], job["title"])
    aid = search.act("job.draft", job["id"], rev=job["rev"])
    got = search.apply()
    assert got["ok"] == [aid]
    batch = json.load(open(got["batches"][0], encoding="utf-8"))
    assert any(e["collection"] == "work" and e["doc_id"] == wid for e in batch)


# ------------------------------------------------------------------ files on the page


def test_a_document_put_in_the_page_store_is_offered_until_it_changes(search):
    item = search.item(KESTREL)
    assert all(f["asset"] is None for f in item["files"])
    path = item["files"][0]["path"]
    aid = "e5" * 16
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "files-saved",
                        path, aid], env=dict(os.environ, LJS_PROFILE=search.profile,
                                             LJS_STATE=search.state, LJS_COPY="private"),
                       capture_output=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    item = search.item(KESTREL)
    assert item["files"][0]["asset"] == aid
    with open(os.path.join(search.state, *path.split("/")), "ab") as fh:
        fh.write(b"\n% changed\n")
    assert search.item(KESTREL)["files"][0]["asset"] is None     # a new version: upload again


# ------------------------------------------------------------------ one helper each


def test_one_name_to_greet_by_everywhere():
    import followups
    for name, want in (("Wren Halloway", "Wren"), ("Halloway, Wren", "Wren"),
                       ("Xiu Mei (Sally) Ho, PhD", "Sally"), ("pell@example.co.uk", ""),
                       ("", "")):
        assert tone.greeting_name(name) == want, name
        assert app_model.first_name(name) == want, name
        assert followups._first_name(name) == want, name


def test_one_person_json_writer(tmp_path, monkeypatch):
    import person
    prof = tmp_path / "profile"
    prof.mkdir()
    (prof / "person.json").write_text('{"identity": {"name": "Morgan"}}\n', encoding="utf-8")
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    person.reset()
    assert person.put("documents.style", "navy") is person.MISSING
    assert person.get("documents.style") == "navy"
    assert person.put("documents.style", person.REMOVE) == "navy"
    assert json.loads((prof / "person.json").read_text(encoding="utf-8")) == {
        "identity": {"name": "Morgan"}, "documents": {}}
    person.reset()


def test_one_tracker_loader(tmp_path):
    import csv_store
    assert csv_store.tracker(str(tmp_path / "none.csv")) == []
    p = tmp_path / "t.csv"
    p.write_text("date,company,role\n2026-10-01,Wren Health\n", encoding="utf-8")
    (row,) = csv_store.tracker(str(p))
    assert row == {"date": "2026-10-01", "company": "Wren Health", "role": ""}


def test_the_reason_picked_after_set_aside_updates_that_ruling(search):
    """The page sends Set aside with no value, then the reason chip under the same action
    id (CONTRACT 6.11): the one ruling takes the reason; nothing is ruled twice."""
    job = next(r for r in search.model()["jobs"]["rows"] if r["id"] == "r9-4")
    doc = {"action": "job.dismiss", "item": job["id"], "value": None,
           "at": "2026-10-25T17:01:00Z", "rev_seen": job["rev"], "tab": "t1"}
    search.put("actions", "act-aside", doc, version=1)
    assert search.apply()["ok"] == ["act-aside"]
    search.written_back()
    search.put("actions", "act-aside", dict(doc, value={"why": "pay"}), version=2)
    got = search.apply()
    assert got["amended"] == ["act-aside"], got
    seen = json.load(open(os.path.join(search.state, "job_scraper", "seen_jobs.json"),
                          encoding="utf-8"))["seen"]
    rulings = [e for e in seen.values() if isinstance(e, dict)
               and e.get("url") == "https://jobs.example/larkspur/supply"]
    assert len(rulings) == 1 and rulings[0]["exclusion_reason"] == "pay"
    search.written_back()
    assert "amended" not in search.apply()                       # once
