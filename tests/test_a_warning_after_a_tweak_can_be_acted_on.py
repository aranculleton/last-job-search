"""A warning a tweak's merge gives can be acted on: a second pass on its round, or its undo.

Issue #225: once `tweak.py merge` came back done with a warning, everything the chat could do
about it was refused. A second merge on the same round said "It changed since you saw it",
the undo it had just printed said "There is nothing to undo there", and the chat edited the
draft by hand, past every message check. Now a second pass on the round starts from that
round's own result, the undo it prints runs as printed (and `undo --work` alone finds the
change that left the note as it stands), and a change made by anyone else in between is still
refused. The person, the employer and the note here are invented (tests/app_state.py).
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

from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks  # noqa: E402

FIRST = ("Hi Pell, hope you're well. I build forecasts for operations teams in Manchester. "
         "We were both at Leeds. How is the claims analytics team set up?")
SECOND = ("Hi Pell, hope you're well. I build forecasts for operations teams in Manchester, "
          "and we were both at Leeds. How is the claims analytics team set up?")


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


def _run(t, argv) -> dict:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tweak.py"), *argv],
                       env=t.env(), capture_output=True, encoding="utf-8", errors="replace",
                       timeout=300, cwd=ROOT)
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise AssertionError(r.stdout + r.stderr) from None


def _text(t) -> str:
    (msg,) = t.model()["messages"]
    return msg["text"]


def _claimed(t):
    """One tweak item, saved once as a read saves it, and its round staged by `apply`. The
    note is a card-only one written with no parts, so changing it is a rewrite."""
    t.python("import sys; sys.path[:0] = ['tools', 'tools/network']\nimport reading\n"
             "reading.write_draft('kestrel_mutual_ansgar', \"Hi Pell, hope you're well. We were "
             "both at Leeds. I build forecasts for operations teams in Manchester. How is the "
             "claims analytics team set up?\", 'Pell Ansgar', card_only=True)\n"
             # Something read about them, so a rewritten first note may be shown.
             "reading.save('kestrel_mutual_ansgar', dict(reading.load('kestrel_mutual_ansgar') "
             "or {}, items=[{'text': 'Runs the claims analytics team.', "
             "'url': 'https://example.com/kestrel-team'}]))\n")
    (msg,) = t.model()["messages"]
    wid = f"tweak~{msg['id']}~20990101T0000"
    where = os.path.join(t.dump, "work")
    os.makedirs(where, exist_ok=True)
    item = {"kind": "tweak", "status": "claimed",
            "args": {"target": {"id": msg["id"], "output": "message", "rev": msg["rev"]},
                     "changes": [{"p": "M5", "v": "me_first"}], "text": None}}
    with open(os.path.join(where, wid.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"id": wid, "version": 2, "data": item}, fh)
    got = _run(t, ["apply", t.dump, "--work", wid])
    assert got["status"] == "needs_model", got
    return msg, wid, got["round"]


def _write(round_dir, text):
    with open(os.path.join(round_dir, "message.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


def _printed(step) -> list:
    return shlex.split(step.split("python3 tools/tweak.py ", 1)[1])


def test_a_second_pass_on_the_same_round_and_both_undos_run(t):
    msg, wid, rd = _claimed(t)
    _write(rd, FIRST)
    one = _run(t, ["merge", t.dump, "--work", wid, "--round", rd])
    assert one["status"] == "done", one
    assert _text(t) == FIRST
    assert one["undo_step"].endswith(f'--work "{wid}" --key {one["key"]}')
    # Acting on its warning: the note written again into the same round, merged again.
    _write(rd, SECOND)
    two = _run(t, ["merge", t.dump, "--work", wid, "--round", rd])
    assert two["status"] == "done", two
    assert _text(t) == SECOND
    # The undo the second pass printed runs as printed: back to the first pass.
    back = _run(t, _printed(two["undo_step"]))
    assert back["status"] == "done", back
    assert _text(t) == FIRST
    # And undo by the item alone takes back the change that left it as it stands.
    orig = _run(t, ["undo", t.dump, "--work", wid])
    assert orig["status"] == "done", orig
    assert _text(t) == msg["text"]


def test_a_change_made_by_someone_else_between_the_two_is_still_refused(t):
    msg, wid, rd = _claimed(t)
    _write(rd, FIRST)
    assert _run(t, ["merge", t.dump, "--work", wid, "--round", rd])["status"] == "done"
    draft = os.path.join(t.state, "documents", "network", msg["contact"], "draft.md")
    with open(draft, encoding="utf-8") as fh:
        raw = fh.read()
    by_hand = raw.replace("both at Leeds", "both at Leeds years ago")
    assert by_hand != raw
    with open(draft, "w", encoding="utf-8") as fh:
        fh.write(by_hand)
    _write(rd, SECOND)
    got = _run(t, ["merge", t.dump, "--work", wid, "--round", rd])
    assert got["status"] == "refused" and "changed since" in got["summary"], got
    with open(draft, encoding="utf-8") as fh:
        assert fh.read() == by_hand
