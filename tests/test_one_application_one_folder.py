"""One application, one folder, named for its employer once.

verify_batch.py named an application's folder without the abbreviation its documents were
written under (the tracker had no row yet), while outreach.py named it with, so one
application's checks sat in `<employer>_<role>/` and its note, posting and draft in
`<employer>_<role>_<employer>/`, and the page never showed the checks that ran. Every tool
now asks docpaths.app_folder, an abbreviation that is only the employer's own name is left
off the folder's name, a folder written under the old name keeps it, and
`docpaths.py merge-twins` (profile upgrade one-folder-each) makes the pairs already on disk
one. Every employer here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import docpaths  # noqa: E402

CO, ROLE, ABBR = "Larkspur Retail", "Senior Data Scientist", "LarkspurRetail"
NEW = "larkspur_retail_senior_data_scientist"
OLD = NEW + "_larkspurretail"


def _env(state):
    env = dict(os.environ, LJS_STATE=str(state), LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    env.pop("LJS_TODAY", None)
    return env


def _py(state, code):
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r)\n" % TOOLS + code],
                       env=_env(state), cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _checks(state):
    """verify_batch.py keeping this application's checks, as its run does."""
    _py(state, "import verify_batch\nverify_batch._record(%r, ['LETTER_2p'], 1, 2, True)"
        % {"company": CO, "role": ROLE, "abbr": ABBR})


def _note(state, abbr=ABBR, url="https://jobs.example/larkspur/sds"):
    """outreach.py writing the posting, the note and the kept draft, as RUNBOOK step 3 does."""
    drafts = state / "drafts.json"
    drafts.write_text(json.dumps([{
        "company": CO, "role": ROLE, "abbr": abbr, "posting": "Build forecasts in Python.",
        "p1": "x.", "p2": "y.", "lead": "", "cl_bullets": [], "p4": "", "summary": "",
        "tools": ""}]), encoding="utf-8")
    apps_in = state / "apps_in.json"
    apps_in.write_text(json.dumps([{"abbr": abbr, "url": url, "company": CO, "title": ROLE}]),
                       encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "outreach.py"), str(drafts),
                        str(apps_in)], env=_env(state), cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr


def _folders(state):
    base = state / "documents" / "applications"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def test_the_checks_and_the_note_share_one_folder_named_for_the_employer_once(tmp_path):
    _checks(tmp_path)               # before the tracker has a row, as a batch runs
    _note(tmp_path)
    assert _folders(tmp_path) == [NEW]
    held = set(os.listdir(tmp_path / "documents" / "applications" / NEW))
    assert {"verify.json", "outreach.md", "draft.json", "job_posting.md"} <= held


def test_a_folder_written_under_the_old_name_keeps_it(tmp_path):
    (tmp_path / "documents" / "applications" / OLD).mkdir(parents=True)
    _checks(tmp_path)
    _note(tmp_path)
    assert _folders(tmp_path) == [OLD]
    assert (tmp_path / "documents" / "applications" / OLD / "verify.json").is_file()


def test_a_second_role_at_the_employer_keeps_its_own_name_and_folder(tmp_path):
    assert docpaths.slug(CO, ROLE, "LarkspurRetail_DataScience") == NEW + "_larkspurretaildatascience"
    assert docpaths.slug(CO, ROLE, "LR") == NEW + "_lr", "an abbreviation that is not the name"
    _note(tmp_path)
    _note(tmp_path, abbr="LarkspurRetail_SeniorDataScientist", url="https://jobs.example/larkspur/sds-2")
    assert _folders(tmp_path) == [NEW, NEW + "_larkspurretailseniordatascientist"]
    # Two applications, each holding its own posting: not one in two folders.
    assert docpaths.twin_folders(str(tmp_path / "documents" / "applications")) == []


def _pair(state, stray_at="2026-10-20T09:00:00Z", home_at=None):
    base = state / "documents" / "applications"
    (base / NEW).mkdir(parents=True)
    (base / OLD).mkdir()
    (base / NEW / "verify.json").write_text(json.dumps({"at": stray_at, "abbr": ABBR, "flags": []}),
                                            encoding="utf-8")
    (base / OLD / "draft.json").write_text("[]", encoding="utf-8")
    (base / OLD / "job_posting.md").write_text("- **Source:** https://jobs.example/larkspur/sds\n",
                                               encoding="utf-8")
    if home_at:
        (base / OLD / "verify.json").write_text(
            json.dumps({"at": home_at, "abbr": ABBR, "flags": ["LETTER_2p"]}), encoding="utf-8")
    return base


def test_one_application_already_in_two_folders_is_made_one(tmp_path):
    base = _pair(tmp_path)
    assert docpaths.twin_folders(str(base)) == [(str(base / NEW), str(base / OLD))]
    out = _py(tmp_path, "import runpy, sys\nsys.argv = ['docpaths.py', 'merge-twins']\n"
              "runpy.run_path(%r, run_name='__main__')" % os.path.join(TOOLS, "docpaths.py"))
    assert NEW in out and OLD in out
    assert _folders(tmp_path) == [OLD]
    assert json.loads((base / OLD / "verify.json").read_text(encoding="utf-8"))["at"] \
        == "2026-10-20T09:00:00Z"
    # Every reader finds it there, with or without the abbreviation.
    assert _py(tmp_path, "import docpaths\nprint(docpaths.app_folder(%r, %r))" % (CO, ROLE)) \
        .strip().endswith(OLD)


def test_two_different_copies_keep_the_newer_and_the_older_beside_it(tmp_path):
    base = _pair(tmp_path, stray_at="2026-10-24T09:00:00Z", home_at="2026-10-22T09:00:00Z")
    assert docpaths.merge_twins(str(base))
    held = sorted(os.listdir(base / OLD))
    assert held == ["draft.json", "job_posting.md", "verify.earlier.json", "verify.json"]
    assert json.loads((base / OLD / "verify.json").read_text(encoding="utf-8"))["at"] \
        == "2026-10-24T09:00:00Z"
    assert json.loads((base / OLD / "verify.earlier.json").read_text(encoding="utf-8"))["at"] \
        == "2026-10-22T09:00:00Z"
