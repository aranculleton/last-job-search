"""A repo in a folder whose name has brackets in it is saved and read whole.

`glob` reads "[2026]" in "Job search [2026]" as one character out of "2", "0" and "6", so
every pattern under such a folder matched nothing: the end-of-session save staged none of
the tracker, the contact book, the message log or the documents and said it had, and every
reader that lists the drafts, the readings or the rounds found none. Every name here is
invented.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import draft_pack  # noqa: E402
import save_state  # noqa: E402
import what_works  # noqa: E402


def _repo(tmp_path):
    root = tmp_path / "Job search [2026]" / "repo"
    (root / "documents" / "applications" / "acme_analyst").mkdir(parents=True)
    (root / "documents" / "network" / "acme_halloway").mkdir(parents=True)
    for name in ("job_search_tracker.csv", "network_contacts.csv", "network_threads.csv"):
        (root / name).write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "documents" / "applications" / "acme_analyst" / "draft.json").write_text(
        json.dumps({"company": "Acme", "role": "Analyst"}), encoding="utf-8")
    (root / "documents" / "applications" / "acme_analyst" / "outreach.md").write_text(
        "Hi Wren", encoding="utf-8")
    (root / "documents" / "network" / "acme_halloway" / "reading.json").write_text(
        json.dumps({"sources": [], "company_ids": {"acme": {"id": "4242"}}}), encoding="utf-8")
    return root


def test_the_save_stages_every_state_file(tmp_path):
    root = _repo(tmp_path)
    _plain, forced = save_state.paths(str(root))
    assert {"job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
            "documents/applications/acme_analyst/draft.json"} <= set(forced)


def test_the_readers_find_what_is_there(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setenv("LJS_STATE", str(root))
    assert [d["company"] for d in what_works.drafts(str(root))] == ["Acme"]
    assert [Path(p).parent.name for p in draft_pack.note_paths()] == ["acme_analyst"]
    from network import reading
    assert reading.known_company_id("Acme") == ("4242", "acme_halloway")
