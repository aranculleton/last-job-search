"""What an employer received stays as it was received.

Three ways a redraft wrote over the record of an application already sent:

  - `doc_name.check_free` and `stage_picks.choose_abbr` let the same role keep
    its name at any status, so redrafting a role already applied to (or
    rejected, or at interview) rendered new documents over the ones sent, and
    `/interview` then prepared from a resume the employer never saw.
  - `outreach.write` rewrote `job_posting.md` on every run, though /apply Step
    6b says an archived posting is left alone.
  - Run over a kept `draft.json`, which names its posting rather than carrying
    it, `outreach.py` loaded it with a bare json.load and wrote an empty fence
    over the only copy of the posting.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import doc_name  # noqa: E402
import outreach  # noqa: E402
import stage_picks  # noqa: E402


def _row(status, role="Data Analyst", abbr="Acme"):
    return {"company": "Acme", "role": role, "status": status, "date": "2026-10-01",
            "cv_file": f"cv/Morgan_Ellis_CV_{abbr}.tex",
            "cover_letter_file": f"cover_letters/Morgan_Ellis_Cover_Letter_{abbr}.tex"}


@pytest.mark.parametrize("status", ["applied", "interview", "rejected", "no_response"])
def test_a_role_already_sent_is_never_rendered_over(status):
    with pytest.raises(FileExistsError, match="already sent"):
        doc_name.check_free("Acme", "Acme", "Data Analyst", [_row(status)])


def test_an_unsent_draft_of_the_same_role_may_be_rendered_again():
    doc_name.check_free("Acme", "Acme", "Data Analyst", [_row("drafted")])
    with pytest.raises(FileExistsError):
        doc_name.check_free("Acme", "Acme", "Pricing Analyst", [_row("drafted")])


def test_a_redraft_of_a_sent_role_is_staged_under_its_own_name(tmp_path):
    assert stage_picks.choose_abbr("Acme", "Data Analyst", [_row("drafted")], str(tmp_path)) == "Acme"
    sent = stage_picks.choose_abbr("Acme", "Data Analyst", [_row("applied")], str(tmp_path))
    assert sent != "Acme" and sent.startswith("Acme_")
    # The redraft's own unsent draft keeps that name when it is redrafted again.
    rows = [_row("applied"), _row("drafted", abbr=sent)]
    assert stage_picks.choose_abbr("Acme", "Data Analyst", rows, str(tmp_path)) == sent


def _draft(**kw):
    return dict({"company": "Wrenfield Freight Ltd", "role": "Analyst", "abbr": "Wrenfield",
                 "posting": "The posting that was applied to.", "p1": "x.", "p2": "y.",
                 "lead": "", "cl_bullets": [], "p4": "", "summary": "", "tools": ""}, **kw)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    return tmp_path


def test_an_archived_posting_is_left_alone(state):
    d = outreach.write(_draft(), {}, "2026-10-14")
    first = open(os.path.join(d, "job_posting.md"), encoding="utf-8").read()
    outreach.write(_draft(posting="A later fetch of the posting, edited since."), {}, "2026-10-20")
    assert open(os.path.join(d, "job_posting.md"), encoding="utf-8").read() == first
    assert "The posting that was applied to." in first


def test_no_posting_text_writes_no_archive_and_names_none(state):
    d = outreach.write(_draft(posting=""), {}, "2026-10-14")
    assert not os.path.exists(os.path.join(d, "job_posting.md"))
    kept = json.load(open(os.path.join(d, "draft.json"), encoding="utf-8"))[0]
    assert "posting_from" not in kept and "posting" not in kept


def test_a_kept_draft_run_again_keeps_its_posting(tmp_path):
    env = dict(os.environ, LJS_STATE=str(tmp_path), LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    sys_path = [sys.executable, os.path.join(ROOT, "tools", "outreach.py")]
    first = tmp_path / "drafts.json"
    first.write_text(json.dumps([_draft()]), encoding="utf-8")
    r = subprocess.run(sys_path + [str(first)], capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    [folder] = (tmp_path / "documents" / "applications").iterdir()
    archived = (folder / "job_posting.md").read_text(encoding="utf-8")
    kept = folder / "draft.json"
    assert "posting" not in json.loads(kept.read_text(encoding="utf-8"))[0]
    r = subprocess.run(sys_path + [str(kept)], capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (folder / "job_posting.md").read_text(encoding="utf-8") == archived
    assert "kept the archived job_posting.md" in r.stdout
    assert json.loads(kept.read_text(encoding="utf-8"))[0]["posting_from"] == "job_posting.md"


def test_a_name_in_capitals_is_said_when_it_is_picked(tmp_path, capsys):
    # doc_name.is_shouty was documented as "the check" for a shouted file name and was
    # never called: a board that writes the employer in capitals gave a resume named
    # in capitals, and nothing said so.
    shortlist = [{"company": "HARBOUR FREIGHT LTD", "title": "Data Analyst",
                  "desc": "Own demand forecasting in SQL and Python.", "url": "https://x.example/1"},
                 {"company": "Quayside Foods", "title": "Data Analyst",
                  "desc": "Own demand forecasting in SQL and Python.", "url": "https://x.example/2"}]
    staged = stage_picks.stage(str(tmp_path / "r1"), ["1", "2"], rows=[], root=str(tmp_path),
                               shortlist=shortlist)
    assert [p["abbr"] for p in staged] == ["HARBOURFREIGHT", "QuaysideFoods"]
    err = capsys.readouterr().err
    assert "HARBOURFREIGHT is the employer's name in capitals" in err
    assert "'harbour freight ltd': 'HarbourFreight'" in err
    assert "QuaysideFoods" not in err
