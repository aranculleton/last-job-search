"""A resume made for someone who asked for one is theirs: on their card, found by their name,
and never in place of the person's own.

A person's copy (2026-11-05): a recruiter asked for a resume with no role named, and the one
made for him only replaced "Your resume". Nothing on his card said it had been made, searching
his name found nothing, and the person's own resume was gone. Now `general_resume.py
--for-contact` keeps it in that contact's own folder, named for them, with a record the model
reads onto their card. Every person and employer is invented (the example person's own).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402

JUNO = "larkspur_retail_castellan"


@pytest.fixture
def copy(tmp_path, monkeypatch):
    state = app_state.small(str(tmp_path / "state"))
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    monkeypatch.setenv("LJS_STATE", state)
    monkeypatch.setenv("LJS_PROFILE", profile)
    return state, profile


def _run(copy, *code):
    state, profile = copy
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = [%r, %r]\n" % (
        os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")) + "\n".join(code)],
        env=dict(os.environ, LJS_STATE=state, LJS_PROFILE=profile), capture_output=True,
        encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_it_is_kept_in_their_folder_named_for_them_and_the_persons_own_is_untouched(copy):
    state, _ = copy
    got = json.loads(_run(copy, "import general_resume as g, json",
                          "print(json.dumps([g.keep_paths(%r)[0], g.keep_paths()[0]]))" % JUNO))
    theirs, own = got
    assert theirs.startswith(os.path.join(state, "documents", "network", JUNO) + os.sep), theirs
    # Named as the person's own: the contact receives the file, and "_For_Juno" told them it
    # was made for them (a person's copy, 2026-11-10). Their folder keeps it apart.
    assert os.path.basename(theirs) == "Morgan_Ellis_CV.pdf", theirs   # the example says CV
    assert own != theirs and os.path.join("documents", "cv") in own


def test_their_card_says_it_and_offers_it(copy):
    state, _ = copy
    pdf = os.path.join(state, "documents", "network", JUNO, "Morgan_Ellis_Resume_For_Juno.pdf")
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    with open(pdf, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    before = _run(copy, "import docpaths", "print(docpaths.current_resume())").strip()
    _run(copy, "import general_resume as g", "g.keep_for_contact(%r, %r, '2026-10-24')" % (JUNO, pdf))
    model = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model",
                                       "--now", "2026-10-25T18:00:00Z"], capture_output=True,
                                      encoding="utf-8", env=dict(os.environ), timeout=120).stdout)
    juno = next(p for p in model["people"] if p["id"] == JUNO)
    r = juno["resume_for_them"]
    assert r["name"] == "Morgan_Ellis_Resume_For_Juno.pdf" and r["made_on"] == "2026-10-24", r
    assert r["get"]["kind"] == "files" and r["get"]["args"]["paths"] == [
        "documents/network/%s/Morgan_Ellis_Resume_For_Juno.pdf" % JUNO], r
    # Never in place of the person's own.
    assert _run(copy, "import docpaths", "print(docpaths.current_resume())").strip() == before
    assert not any(p.get("resume_for_them") for p in model["people"] if p["id"] != JUNO)


def test_it_goes_into_the_pages_store_as_it_is_made_so_get_it_downloads_at_once(copy):
    """Made with no job named, it was never put in the page's own store: its Get it started a
    new piece of work ("The resume made for Juno, ready to download") instead of downloading
    (the maintainer, 2026-11-10). Its making's finish queues it with the applications' files
    (app_model.files_missing, page_db.queue_files), and once uploaded, Get it is the file."""
    state, _ = copy
    pdf = os.path.join(state, "documents", "network", JUNO, "Morgan_Ellis_Resume_For_Juno.pdf")
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    with open(pdf, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    _run(copy, "import general_resume as g", "g.keep_for_contact(%r, %r, '2026-10-24')" % (JUNO, pdf))
    rel = "documents/network/%s/Morgan_Ellis_Resume_For_Juno.pdf" % JUNO
    got = json.loads(_run(
        copy, "import app_model, page_db, json, datetime as dt, tempfile",
        "miss = [x for x in app_model.files_missing() if x['id'].startswith(app_model.RESUME_FOR_PREFIX)]",
        "q = page_db.queue_files({}, miss, dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc), tempfile.mkdtemp())",
        "print(json.dumps({'miss': miss, 'q': q['applications']}))"))
    (one,) = got["miss"]
    assert one["id"] == "resfor-" + JUNO and one["paths"] == [rel], one
    # In the person's own word for the document (the example person says CV).
    assert one["what"] == "the CV for Juno", one
    assert got["q"] == ["resfor-" + JUNO], got
    # Uploaded (`app.py files-saved`): their card's Get it is the file, and nothing is missing.
    after = json.loads(_run(
        copy, "import app_model, json",
        "app_model.record_assets([(%r, %r)])" % (rel, "c" * 32),
        "print(json.dumps([app_model.resume_made_for(%r)['asset'], "
        "[x['id'] for x in app_model.files_missing()]]))" % JUNO))
    assert after[0] == "c" * 32 and not any(i.startswith("resfor-") for i in after[1]), after
