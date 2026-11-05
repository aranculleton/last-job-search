"""Two chats changing two of the person's rules keep both, and the later change of one rule
wins (documents/rules/set.json and review.json, merged by tools/merge_state.py). Before
they were wired, a merge of the two files would have stopped on a clash or kept one side."""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGE = os.path.join(ROOT, "tools", "merge_state.py")


def _merge(tmp_path, path, base, ours, theirs):
    files = []
    for name, data in (("base", base), ("ours", ours), ("theirs", theirs)):
        f = tmp_path / name
        f.write_text(json.dumps(data), encoding="utf-8")
        files.append(str(f))
    r = subprocess.run([sys.executable, MERGE, *files, path], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((tmp_path / "ours").read_text(encoding="utf-8"))


def test_two_chats_setting_two_rules_keep_both_and_the_later_wins(tmp_path):
    base = {"place": {"set_on": "2026-10-01", "words": "Toronto"}}
    ours = dict(base, pay={"set_on": "2026-11-05", "words": "80k"})
    theirs = {"place": {"set_on": "2026-11-04", "words": "Toronto and remote"}}
    got = _merge(tmp_path, "documents/rules/set.json", base, ours, theirs)
    assert got == {"place": theirs["place"], "pay": ours["pay"]}


def test_a_rule_kept_in_either_chat_stays_kept_on_its_later_day(tmp_path):
    got = _merge(tmp_path, "documents/rules/review.json", {"kept": {"a": "2026-10-01"}},
                 {"kept": {"a": "2026-10-01", "b": "2026-11-05"}},
                 {"kept": {"a": "2026-11-02"}, "brief_dismissed": "2026-11"})
    assert got == {"kept": {"a": "2026-11-02", "b": "2026-11-05"}, "brief_dismissed": "2026-11"}
