"""A booked interview stage written with a time is read with its date.

`register_process` accepted "--date 2026-10-27 10:00" and wrote "(scheduled 2026-10-27
10:00, with Head of Planning)", and a chat writing outcome.md by hand does the same, but the
reader allowed nothing between the date and ", with": the stage read back with no date, so no
"no pack yet" and no thank-you reminder ever reached the due list. Every name here is invented.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import open_actions  # noqa: E402
import outreach  # noqa: E402
import what_works  # noqa: E402


@pytest.mark.parametrize("when,date,who", [
    ("scheduled 2026-10-27 10:00, with Head of Planning", "2026-10-27", "Head of Planning"),
    ("scheduled 2026-10-27, with Head of Planning", "2026-10-27", "Head of Planning"),
    ("scheduled 2026-10-27 at 2pm, with the panel", "2026-10-27", "the panel"),
    ("scheduled 2026-10-27, 2:30 pm EST", "2026-10-27", ""),
    ("scheduled 2026-10-27 10.30", "2026-10-27", ""),
])
def test_the_date_and_who_are_read_past_a_time(when, date, who):
    got = what_works.outcome_stages(f"- [ ] Phone screen ({when})")
    assert [(s["label"], s["date"], s["scheduled"], s["with"]) for s in got] == [
        ("Phone screen", date, True, who)]


def test_a_stage_booked_with_a_time_reaches_the_due_list(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    row = {"date": "2026-10-20", "company": "Acme", "role": "Analyst", "status": "interview"}
    folder = Path(outreach.app_folder(row["company"], row["role"]))
    folder.mkdir(parents=True)
    (folder / "outcome.md").write_text(
        "## Interview stages reached\n\n- [ ] Phone screen (scheduled 2026-10-27 10:00, with "
        "Head of Planning)\n", encoding="utf-8")
    items = open_actions.interview_items([row], "2026-10-25")
    assert items and "2026-10-27" in " ".join(str(v) for i in items for v in i.values())
