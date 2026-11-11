"""Old follow-up packs are put aside, so the network folder holds only the two that are read.

Every brief writes a follow-up pack, and only the newest two are ever read again
(followup_drafts.earlier_drafts), yet nothing moved the older ones: one copy had 14 of them
beside the rest of the network folder (audit HC-4). Writing today's pack now moves every pack
but the newest two into documents/network/old/, kept, never deleted. Invented contents.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import followup_drafts  # noqa: E402
import person  # noqa: E402

DAYS = ["2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"]


def test_writing_a_pack_puts_all_but_the_newest_two_aside(tmp_path, monkeypatch):
    state = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    monkeypatch.setenv("LJS_STATE", str(state))
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    person.reset()
    folder = state / "documents" / "network"
    folder.mkdir(parents=True, exist_ok=True)
    for d in DAYS:
        (folder / (followup_drafts.PACK_NAME % d)).write_text(f"# Pack {d}\n", encoding="utf-8")
    (folder / "plan.md").write_text("their own notes\n", encoding="utf-8")
    monkeypatch.setattr(followup_drafts, "render_pack", lambda today, got, contacts: "# Pack\n")
    path = followup_drafts.write_pack("2026-11-10", [], [])
    assert path.endswith(followup_drafts.PACK_NAME % "2026-11-10")
    left = sorted(p.name for p in folder.iterdir() if p.is_file())
    assert left == ["followup_pack_2026-11-09.md", "followup_pack_2026-11-10.md", "plan.md"]
    old = sorted(p.name for p in (folder / "old").iterdir())
    assert old == [followup_drafts.PACK_NAME % d for d in DAYS[:4]]
    # What is read again is unchanged: today's and the newest before it.
    assert followup_drafts.earlier_drafts("2026-11-10") == {}
