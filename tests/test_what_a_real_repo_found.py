"""What running the app against a real person's repo, and reading every document
against the code, turned up. Each of these was a working-looking path that failed:

- fleet.py counted only squash-merge subjects as pull requests, so a repo that
  merges the ordinary way raised "nothing reached master through a pull request"
  on every run;
- every round's prune deleted `06_shortlist.json`, the file drafting is staged
  from, so "draft 1 and 3" from the shortlist just sent failed on a missing file,
  and in a later session there was no way back to the posting at all;
- a single /apply had no way into the pipeline a batch uses, so it skipped the
  allocator, the renderer's layout rules, verify_batch.sh and the kept draft;
- the commands named an application's folder `<company>_<role>/` while the tools
  wrote `<company>_<role>_<abbr>/`, so /outcome and /interview started a second one;
- the drafting workflow sent every agent to a fixed container path;
- /reset left personal data behind (per-contact folders, the person's own boards);
- the skill docs still carried em dashes, including in the report /upskill writes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fleet  # noqa: E402
import outreach  # noqa: E402
import personal_paths  # noqa: E402
import record_drafts  # noqa: E402
import run_round  # noqa: E402
import stage_picks  # noqa: E402
from tests import repo_files  # noqa: E402

POSTING = "Larkspur Retail is hiring a Senior Supply Chain Analyst in Manchester. " * 3
ROW = {"company": "Larkspur Retail", "title": "Senior Supply Chain Analyst",
       "url": "https://example.com/jobs/1", "location": "Manchester", "priority": 90, "fit": 81}


def test_a_merge_commit_is_a_pull_request():
    assert fleet.via_pull_request("Merge pull request #28 from someone/branch")
    assert fleet.via_pull_request("Add the thing (#28)")
    assert not fleet.via_pull_request("Merge branch 'master' into feature")
    assert not fleet.via_pull_request("Fix a typo")


# ------------------------------------------------------------------ the round keeps its shortlist

def test_the_prune_keeps_the_shortlist_with_its_bodies(tmp_path):
    rows = [dict(ROW, title="Role %d" % i, desc="body %d" % i) for i in range(run_round.KEEP_TOP + 5)]
    (tmp_path / run_round.SHORTLIST).write_text(json.dumps(rows), encoding="utf-8")
    (tmp_path / "05_ranked.json").write_text("[]", encoding="utf-8")
    (tmp_path / "round.log").write_text("log", encoding="utf-8")
    run_round.prune(str(tmp_path))
    kept = json.loads((tmp_path / run_round.SHORTLIST).read_text(encoding="utf-8"))
    assert len(kept) == run_round.KEEP_TOP and kept[0]["desc"] == "body 0"
    assert not (tmp_path / "05_ranked.json").exists() and (tmp_path / "round.log").exists()


def test_a_later_session_stages_from_the_committed_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    rounds = tmp_path / "documents" / "rounds"
    rounds.mkdir(parents=True)
    (rounds / "r9.json").write_text(json.dumps([{k: v for k, v in ROW.items()}]), encoding="utf-8")
    round_dir = tmp_path / "rounds" / "r9"                      # gone with the old container
    fetched = []

    def fetch(row):
        fetched.append(row["url"])
        return dict(row, desc=POSTING)

    staged = stage_picks.stage(str(round_dir), ["1"], rows=[], root=str(tmp_path), fetch=fetch)
    assert fetched == [ROW["url"]]
    text = open(staged[0]["file"], encoding="utf-8").read()
    assert POSTING.strip() in text


def test_a_posting_the_board_will_not_give_is_read_from_a_saved_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    round_dir = tmp_path / "rounds" / "r9"
    s = stage_picks.slug(ROW["company"])
    saved = round_dir / "postings" / ("%s.txt" % s)
    no_body = [dict(ROW)]

    def refuse(row):
        return dict(row, hydrate_error="detail exit 1")

    try:
        stage_picks.stage(str(round_dir), ["1"], rows=[], root=str(tmp_path),
                          shortlist=no_body, fetch=refuse)
    except SystemExit as e:
        assert str(saved) in str(e) and "detail exit 1" in str(e)
    else:
        raise AssertionError("staged a posting with no text")
    saved.parent.mkdir(parents=True)
    saved.write_text(POSTING, encoding="utf-8")
    staged = stage_picks.stage(str(round_dir), ["1"], rows=[], root=str(tmp_path),
                               shortlist=no_body, fetch=refuse)
    assert POSTING.strip() in open(staged[0]["file"], encoding="utf-8").read()


def test_a_single_apply_is_staged_like_a_round_pick(tmp_path):
    posting = tmp_path / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    out = tmp_path / "apply"
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "single",
                        str(out), "--company", "Larkspur Retail", "--role",
                        "Senior Supply Chain Analyst", "--posting-file", str(posting),
                        "--url", ROW["url"], "--fit", "81"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    assert p.returncode == 0, p.stderr
    # The example tracker already holds an application for this very role, so staging
    # now holds it and asks first (tools/posting_profile.py); the answer releases it.
    # Until 2026-10-21 it was staged straight into picks.json, unasked.
    assert "You applied for Senior Supply Chain Analyst at Larkspur Retail" in p.stdout
    assert json.loads((out / "picks.json").read_text(encoding="utf-8")) == []
    held = json.loads((out / "held.json").read_text(encoding="utf-8"))
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "consent",
                    str(out), held[0]["slug"], "--draft"], check=True, capture_output=True,
                   cwd=ROOT)
    picks = json.loads((out / "picks.json").read_text(encoding="utf-8"))
    apps = json.loads((out / "apps_in.json").read_text(encoding="utf-8"))
    assert picks[0]["company"] == "Larkspur Retail" and picks[0]["abbr"]
    assert apps[0]["fit"] == 81 and apps[0]["portal"] == "pasted" and "desc" not in apps[0]


def test_a_single_application_gets_a_clean_tracker_row():
    meta = {"company": "Larkspur Retail", "fit": 81, "portal": "pasted", "url": ROW["url"],
            "deadline": "2026-11-01"}
    draft = {"company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
             "abbr": "Larkspur", "notes_for_tracker": "Angle: forecasting."}
    row = record_drafts._row_for(draft, meta, "2026-10-15", "")
    assert "None" not in row["notes"] and "Scores: fit 81." in row["notes"]
    assert row["channel"] == "" and row["deadline"] == "2026-11-01"
    round_row = record_drafts._row_for(draft, dict(meta, portal="linkedin", opportunity=70,
                                                   priority=88), "2026-10-15", "r1")
    assert round_row["channel"] == "portal"
    assert "Scores: fit 81, opportunity 70, priority 88." in round_row["notes"]


# ------------------------------------------------------------------ one folder per application

def test_the_folder_already_on_disk_is_the_one_used(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    apps = tmp_path / "documents" / "applications"
    (apps / "larkspur_retail_senior_supply_chain_analyst").mkdir(parents=True)
    got = outreach.app_folder("Larkspur Retail", "Senior Supply Chain Analyst")
    assert got.endswith("larkspur_retail_senior_supply_chain_analyst")
    (apps / "larkspur_retail_senior_supply_chain_analyst").rmdir()
    (apps / "larkspur_retail_senior_supply_chain_analyst_larkspur").mkdir()
    got = outreach.app_folder("Larkspur Retail", "Senior Supply Chain Analyst")
    assert got.endswith("_larkspur")
    new = outreach.app_folder("Fernhill Freight", "Operations Analyst", "Fernhill")
    assert new.endswith("fernhill_freight_operations_analyst_fernhill")


# ------------------------------------------------------------------ the docs match what runs

def test_the_drafting_workflow_names_no_container_path():
    with open(os.path.join(ROOT, ".claude", "workflows", "draft-applications.js"),
              encoding="utf-8") as fh:
        assert "/home/" not in fh.read()


def test_reset_names_every_personal_path():
    with open(os.path.join(ROOT, ".claude", "commands", "reset.md"), encoding="utf-8") as fh:
        text = fh.read()
    for pattern in personal_paths.PERSONAL:
        root = pattern.split("/*")[0].rstrip("/")
        assert root in text, "/reset leaves %s behind" % pattern


def test_no_em_dash_in_any_document_the_app_ships():
    # The app's own documents only: this suite runs in a person's repo too, where
    # a saved posting is theirs and says whatever its employer wrote.
    dash = chr(0x2014)
    files = repo_files.tracked("*.md", root=ROOT)
    found = [f for f in files if f != "CHANGELOG-upstream.md" and not personal_paths.is_personal(f)
             and dash in open(os.path.join(ROOT, f), encoding="utf-8").read()]
    assert not found, found


def test_a_shortlist_that_will_not_parse_is_not_kept(tmp_path):
    (tmp_path / run_round.SHORTLIST).write_text("not json", encoding="utf-8")
    run_round.prune(str(tmp_path))
    assert not (tmp_path / run_round.SHORTLIST).exists()


def test_a_shortlist_that_will_not_parse_is_closed_before_it_is_removed(tmp_path):
    """The file was opened inside json.load and left open while the failure was handled,
    so on Windows, which deletes no file that is open, the removal failed and the broken
    shortlist was kept (the suite on Windows, 2026-10-25). Each file read is closed first:
    on any computer, an unclosed file says so with a ResourceWarning when it is let go."""
    import gc
    import warnings
    for name in (run_round.SHORTLIST, "01_dropped.json"):
        (tmp_path / name).write_text("not json", encoding="utf-8")
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        run_round.trim(str(tmp_path / run_round.SHORTLIST))
        run_round.slim(str(tmp_path / "01_dropped.json"))
        run_round.write_summary(str(tmp_path / "01_dropped.json"), str(tmp_path / "o"), "r1")
        run_round.count(str(tmp_path / "01_dropped.json"))
        gc.collect()
    assert [w for w in seen if issubclass(w.category, ResourceWarning)] == []
    assert not (tmp_path / run_round.SHORTLIST).exists()
