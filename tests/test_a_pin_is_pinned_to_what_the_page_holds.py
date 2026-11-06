"""`app.py pin` pins every write to the version the page holds, never one ahead.

The maintainer's copy, 6 November 2026: a job's pin wrote `if_version: 3` while the page held
the item at 2, so the send was refused; running the pin again after `app.py version` got
through. Two ways led there, both on a batch of postings drafted together:

- each posting named with `--work`, as the command's help says: the leader's pin renews the
  others, and each was then written again on its own from the same read, in a second batch
  pinned to the same version. Whichever went second was refused, and a refused leader's batch
  left the folder one ahead of the page for the next pin;
- the page wrote one posting while the job ran: the pin was refused for it, `app.py version`
  set that posting right, and the leader, moved on in the folder outside the record of what
  was sent, stayed one ahead, so the pin run again was refused for it.

The store here is a dictionary that keeps the real one's rules (a batch is all or nothing, an
existing record needs its version, and each write counts it up by one); the chat's read saves
each record's fields with its `_v`, as ArtifactData's `out_dir` does. Every employer and chat
id is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
from test_every_work_move_is_a_command_pinned_to_its_read import T, db_of, draft, dump_dir  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
JOB = "session_job"


class Page:
    """The page's work records: {id: version}, and the chat's folder read from them."""

    def __init__(self, tmp_path, monkeypatch):
        self.tmp = str(tmp_path)
        # Neither the store's corrections nor the mirror ever reach the checkout this runs in.
        monkeypatch.setenv("LJS_VERSIONS", os.path.join(self.tmp, "known.json"))
        monkeypatch.setenv("LJS_PAGE_MIRROR", os.path.join(self.tmp, "mirror"))
        db = db_of({"draft~lead": (draft("Larkspur Retail", asked="2026-11-03T16:00:00Z"), 1),
                    "draft~two": (draft("Quillon Data", asked="2026-11-03T16:01:00Z"), 1),
                    "draft~three": (draft("Fernhill Freight", asked="2026-11-03T16:02:00Z"), 1)})
        self.versions = {wid: doc["version"] for wid, doc in db["work"].items()}
        self.data = {wid: doc["data"] for wid, doc in db["work"].items()}
        chosen = page_db.next_item(db, "cloud", T("17:05"), cap=page_db.HEAVY_CAP_CHATS)
        assert self.send(page_db.claim(db, chosen, JOB, "cloud", T("17:05"),
                                       os.path.join(self.tmp, "claim"))) is None
        # The job's own chat reads the page afresh into its folder.
        self.d = dump_dir(os.path.join(self.tmp, "D"), {"work": {
            wid: {"data": self.data[wid], "version": v} for wid, v in self.versions.items()}})

    def send(self, batches):
        """Each batch in turn, as the chat sends them: None, or the first refused (id, the
        version the store holds)."""
        for path in batches:
            with open(path, encoding="utf-8") as fh:
                entries = [e for e in json.load(fh) if e["collection"] == "work"]
            for e in entries:
                if e.get("if_version") != self.versions[e["doc_id"]]:
                    return e["doc_id"], self.versions[e["doc_id"]]
            for e in entries:
                with open(e["file_path"], encoding="utf-8") as fh:
                    self.data[e["doc_id"]] = dict(self.data[e["doc_id"]], **json.load(fh))
                self.versions[e["doc_id"]] += 1
        return None

    def run(self, *args):
        r = subprocess.run([sys.executable, APP, *args], capture_output=True, text=True,
                           encoding="utf-8", timeout=120, env=dict(os.environ))
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout

    def pin(self, works, n):
        named = [x for w in works for x in ("--work", w)]
        got = json.loads(self.run("pin", self.d, *named, "--chat", JOB, "--stage", "research",
                                  "--line", f"Step {n}", "--now", f"2026-11-03T17:{10 + n}:00Z"))
        return got["batches"]


@pytest.fixture
def page(tmp_path, monkeypatch):
    return Page(tmp_path, monkeypatch)


@pytest.mark.parametrize("works", [["draft~lead", "draft~two", "draft~three"],
                                   ["draft~two", "draft~lead", "draft~three"]])
def test_every_posting_named_is_written_once_and_every_pin_lands(page, works):
    for n in range(3):
        before = dict(page.versions)
        batches = page.pin(works, n)
        assert page.send(batches) is None, f"pin {n} refused"
        # Each posting written once a pin, so each moved on by exactly one.
        assert page.versions == {k: v + 1 for k, v in before.items()}
    got = json.loads(page.run("pin", page.d, *[x for w in works for x in ("--work", w)],
                              "--chat", JOB, "--stage", "research", "--now",
                              "2026-11-03T17:20:00Z"))
    assert sorted(w["work"] for w in got["works"]) == sorted(works)


def test_a_pin_refused_for_one_posting_is_made_again_pinned_to_the_page(page):
    assert page.send(page.pin(["draft~lead"], 0)) is None
    page.versions["draft~two"] += 1          # the page writes the second posting meanwhile
    refused = page.send(page.pin(["draft~lead"], 1))
    assert refused == ("draft~two", page.versions["draft~two"])
    page.run("version", page.d, "work/" + refused[0], str(refused[1]))
    batches = page.pin(["draft~lead"], 2)
    pinned = {}
    for path in batches:
        with open(path, encoding="utf-8") as fh:
            pinned.update({e["doc_id"]: e["if_version"] for e in json.load(fh)})
    # Every posting pinned to what the page holds: the leader is not one ahead.
    assert pinned == page.versions
    assert page.send(batches) is None
