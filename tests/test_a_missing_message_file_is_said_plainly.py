"""A message file that is not there is said in one plain line, never a traceback.

`state.py sent`, `text`, `nudge`, `message` and `resent` opened `--text-file` without a
guard and ended in FileNotFoundError; `received` already said it plainly. Nothing is
recorded either way.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATE = str(ROOT / "tools" / "network" / "state.py")


@pytest.mark.parametrize("args", [
    ["sent", "acme_halloway"],
    ["text", "acme_halloway", "--date", "2026-10-01"],
    ["nudge", "acme_halloway"],
    ["message", "acme_halloway"],
    ["resent", "acme_halloway"],
    ["received", "acme_halloway"],
])
def test_each_command_says_it_cannot_read_the_file(tmp_path, args):
    book, log = tmp_path / "network_contacts.csv", tmp_path / "network_threads.csv"
    book.write_text("contact_id,name,company,status\nacme_halloway,Wren Halloway,Acme,"
                    "awaiting_reply\n", encoding="utf-8")
    log.write_text("contact_id,date,direction,channel,scenario,summary,full_text\n",
                   encoding="utf-8")
    before = (book.read_bytes(), log.read_bytes())
    missing = str(tmp_path / "not_there.txt")
    places = ["--threads", str(log)] + ([] if args[0] == "text" else ["--contacts", str(book)])
    env = dict(os.environ, LJS_STATE=str(tmp_path))
    r = subprocess.run([sys.executable, STATE, *args, "--text-file", missing, *places],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Traceback" not in r.stderr and f"cannot read {missing}" in r.stdout
    assert (book.read_bytes(), log.read_bytes()) == before


def test_a_texts_file_that_is_not_there_is_said_too(tmp_path):
    log = tmp_path / "network_threads.csv"
    log.write_text("contact_id,date,direction,channel,scenario,summary,full_text\n",
                   encoding="utf-8")
    r = subprocess.run([sys.executable, STATE, "nudge", "--texts", str(tmp_path / "none.json"),
                        "--threads", str(log), "--contacts", str(tmp_path / "c.csv")],
                       capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, LJS_STATE=str(tmp_path)), timeout=60)
    assert r.returncode == 1 and "Traceback" not in r.stderr and "cannot read" in r.stdout
