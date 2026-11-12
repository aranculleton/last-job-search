"""A tweak runs from the id `app.py wake` prints beside it, as well as from its file.

Issue #224: the wake printed the item's id (`tweak~...`) next to its step, `tweak.py apply
--work <item>`, and tweak.py took only a file: the id was refused as no such file, because
the read folder saves the item as `work/tweak@...json`, with @ for ~. The merge step a
redraft prints said `--work <this item>` too. Now the step names the read folder, tweak.py
finds the item there by its id, and every step it prints runs as printed. The employer, the
role and the item here are invented (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL  # noqa: E402
from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks, _posting  # noqa: E402

WID = f"tweak~{KESTREL}~20990101T0000"


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


def _saved_as_a_read_saves_it(t, changes) -> str:
    """The claimed item in the read folder, named as a read names it: @ for ~."""
    item = {"kind": "tweak", "status": "claimed",
            "args": {"target": {"id": KESTREL, "output": "resume"}, "changes": changes,
                     "text": None}}
    where = os.path.join(t.dump, "work")
    os.makedirs(where, exist_ok=True)
    path = os.path.join(where, WID.replace("~", "@") + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"id": WID, "version": 3, "data": item}, fh)
    return path


def _run(t, argv):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tweak.py"), *argv],
                       env=t.env(), capture_output=True, encoding="utf-8", errors="replace",
                       timeout=300, cwd=ROOT)
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise AssertionError(r.stdout + r.stderr) from None


def test_the_step_the_wake_prints_names_the_read_folder_and_the_id():
    row = app.work_row("tweak")
    assert 'tweak.py apply "$D" --work <its id>' in row
    assert "--work <item>" not in row


def test_the_id_the_wake_prints_finds_the_item_the_read_saved(t):
    _posting(t)
    _saved_as_a_read_saves_it(t, [{"p": "R8", "v": "plainer"}])
    got = _run(t, ["apply", t.dump, "--work", WID])
    assert got["status"] == "needs_model", got
    assert "No such file" not in json.dumps(got)
    (merge,) = [s for s in got["steps"] if "tweak.py merge" in s]
    assert "<this item>" not in merge
    # Every path quoted: under a user folder with a space (Windows CI's "Zoë Quillfeather",
    # 2026-11-11) a bare round folder split in two and the merge was refused as printed.
    assert f'"{t.dump}" --work "{WID}" --round "{got["round"]}"' in merge
    # The merge runs as printed: the item is found again, whatever the redraft then says.
    again = _run(t, shlex.split(merge.split("python3 tools/tweak.py ", 1)[1]))
    assert "No work item" not in again.get("summary", "")
    assert "No such file" not in again.get("summary", "")


def test_the_claim_batchs_own_record_reads_as_the_item(t):
    # A comment on #224: the claim's batch keeps its own record of the item, only the fields
    # the claim changed, under <D>/wake/<n>/work/files/work/, and given that file `apply` said
    # "That is not a tweak". It is made here the way a claim makes it.
    import page_db
    _posting(t)
    _saved_as_a_read_saves_it(t, [{"p": "R8", "v": "plainer"}])
    w = page_db.Writes(os.path.join(t.dump, "wake", "1", "work"))
    item = {"kind": "tweak", "error": "the last try stopped"}
    claim = page_db.taken(item, "cloud-1", "cloud", "2099-01-01T00:00:00Z",
                          "2099-01-01T00:20:00Z")
    entry = w.add("update", "work", WID, claim, if_version=3)
    batch_record = entry["file_path"]
    assert os.sep + os.path.join("wake", "1", "work", "files", "work") + os.sep in batch_record
    assert "kind" not in json.load(open(batch_record, encoding="utf-8"))
    got = _run(t, ["apply", "--work", batch_record])
    assert got["status"] == "needs_model", got
    assert "not a tweak" not in json.dumps(got)
    # A body with no record of its item anywhere is still not taken for one.
    stray = os.path.join(os.path.dirname(t.dump), "stray", "files", "work",
                         "@".join(("tweak", "nobody", "20990101T0000.json")))
    os.makedirs(os.path.dirname(stray), exist_ok=True)
    with open(stray, "w", encoding="utf-8") as fh:
        json.dump(claim, fh)
    no = _run(t, ["apply", "--work", stray])
    assert no["status"] == "refused" and no["summary"] == "That is not a tweak."


def test_the_items_own_file_still_works(t):
    _posting(t)
    path = _saved_as_a_read_saves_it(t, [{"p": "R8", "v": "plainer"}])
    got = _run(t, ["plan", "--work", path])
    assert got.get("status") != "refused", got


def test_an_id_with_nothing_saved_for_it_says_where_to_look(t):
    os.makedirs(os.path.join(t.dump, "work"), exist_ok=True)
    got = _run(t, ["apply", t.dump, "--work", "tweak~nobody~20990101T0000"])
    assert got["status"] == "refused"
    assert "No work item tweak~nobody~20990101T0000" in got["summary"]
    assert '"$D"' in got["summary"] and "Errno" not in got["summary"]
