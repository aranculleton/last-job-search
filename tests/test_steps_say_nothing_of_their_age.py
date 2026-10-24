"""Steps a person is given say nothing of how old they are; Claude is told apart.

`claude_surfaces.steps()` put its line for Claude ("[claude_surfaces: ... re-check ...
then update tools/claude_surfaces.json]") among the person's numbered steps once an entry
was older than `stale_after_days`. Two messages pass those steps on word for word, the fix
for job sites a cloud chat cannot reach and the steps after a yes to an upgrade's question,
so each would have handed a beginner a file path, and both outgrew their length checks the
day the entries aged (found 2026-10-23, about 60 days before it would have happened). The
line now comes apart: stderr from the command, a "Claude, not for them" line in a sync or
a round, `check` in the upgrade plan.
"""
import copy
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools")]

import pytest  # noqa: E402

import claude_surfaces as C  # noqa: E402
import env_check  # noqa: E402
import profile_upgrades as U  # noqa: E402
import scrape_wide  # noqa: E402


@pytest.fixture
def aged(monkeypatch):
    """The registry as it will read once every entry is long past re-checking."""
    fresh = C.load()
    old = copy.deepcopy(fresh)
    for e in old["entries"]:
        e["verified_on"] = "2000-01-01"

    def use(which):
        monkeypatch.setattr(C, "load", lambda path=None: which)
    use(fresh)
    return lambda: use(old)


def _undated(text):
    """The words with the day the steps were checked masked: that day is meant to change."""
    return re.sub(r"checked \d{4}-\d{2}-\d{2}", "checked <day>", text)


def _ids_with_steps():
    return [e["id"] for e in C.load()["entries"] if e.get("steps")]


def test_steps_are_the_persons_lines_alone_and_the_note_is_claudes(aged):
    eids = _ids_with_steps()
    assert eids
    before = {eid: C.steps(eid)[1:] for eid in eids}
    assert all(C.notes(eid) == [] or C.age(C.entry(eid)) > 60 for eid in eids)
    aged()
    for eid in eids:
        lines = C.steps(eid)
        assert lines[1:] == before[eid], eid                     # the same numbered steps
        assert not any("claude_surfaces" in ln for ln in lines), eid
        (note,) = C.notes(eid)
        assert note.startswith(f"[claude_surfaces: {eid!r} was checked 2000-01-01")


def test_the_steps_command_gives_the_note_on_stderr_only(aged, capsys):
    eid = _ids_with_steps()[0]
    aged()
    assert C.main(["steps", eid]) == 0
    out, err = capsys.readouterr()
    assert "claude_surfaces" not in out and err.startswith("[claude_surfaces:")


def test_the_blocked_sites_message_is_the_same_however_old_its_steps(aged):
    fresh = env_check.blocked_say(["LinkedIn", "freehire"])
    assert env_check.blocked_notes() == [] or C.age(C.entry("cloud-internet")) > 60
    aged()
    assert _undated(env_check.blocked_say(["LinkedIn", "freehire"])) == _undated(fresh)
    assert env_check.blocked_notes()[0].startswith("[claude_surfaces: 'cloud-internet'")
    assert scrape_wide.blocked_notes() == env_check.blocked_notes()


def test_an_upgrades_steps_keep_their_shape_and_the_plan_carries_the_note(aged):
    u = U.by_id("connections-export")
    fresh, _ = U._steps_and_notes(u)
    aged()
    text, check = U._steps_and_notes(u)
    assert _undated(text) == _undated(fresh)
    assert len(text.splitlines()) <= 5 and text.splitlines()[-1] == \
        "I only read it. Nothing is sent to anyone."
    assert check and all(c.startswith("[claude_surfaces:") for c in check)
