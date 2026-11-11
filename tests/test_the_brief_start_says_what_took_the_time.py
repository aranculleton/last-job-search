"""The brief's start says how long each part took, and its output is never cut.

One run's start took 5.5 of its 12 minutes and nothing said which part (the update, the Python
side or the earlier work), and the run piped the brief's output through `tail -40`, which can
cut the lines meant for Claude (audit BT-8). The start now keeps each part's seconds in its
log, and the prompt says the output is never piped. No network: the steps are stubbed.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import brief  # noqa: E402

from test_the_brief_reads_its_prompt_again_after_an_update import _start  # noqa: E402


def test_the_start_keeps_how_long_each_part_took(tmp_path, monkeypatch, capsys):
    same = {"automation/prompts/morning_brief.md": "a"}
    _start(tmp_path, monkeypatch, [same, same], capsys)
    log = (tmp_path / "sync.txt").read_text(encoding="utf-8")
    head = log.split("\n---\n", 1)[0]
    took = next(ln for ln in head.splitlines() if ln.startswith("took: "))
    for part in ("update", "python", "earlier"):
        assert part + " " in took
    assert brief.read_sync(dt.date(2026, 11, 10), str(tmp_path / "sync.txt"))["took"] == \
        took[len("took: "):]


def test_the_prompt_never_pipes_the_briefs_output():
    prompt = " ".join(open(os.path.join(ROOT, "automation", "prompts", "morning_brief.md"),
                           encoding="utf-8").read().split())
    assert "never chained or piped" in prompt


class _Done:
    returncode, stdout, stderr = 0, "", ""


def _calls(tmp_path, monkeypatch, ready: bool):
    import datetime as dt
    import person
    calls = []

    def run(argv, **kw):
        joined = " ".join(map(str, argv))
        calls.append(("run", joined))
        if "import pytest, pypdf" in joined:
            return type("R", (), {"returncode": 0 if ready else 1, "stdout": "", "stderr": ""})()
        return _Done()

    class Popen:
        def __init__(self, argv, **kw):
            calls.append(("popen", " ".join(map(str, argv))))
            self.returncode = 0

        def communicate(self, timeout=None):
            calls.append(("wait", ""))
            return "", ""

    monkeypatch.setenv("LJS_BRIEF_SYNC", str(tmp_path / "sync.txt"))
    monkeypatch.setattr(brief.subprocess, "run", run)
    monkeypatch.setattr(brief.subprocess, "Popen", Popen)
    monkeypatch.setattr(brief, "page_url", lambda: "")
    monkeypatch.setattr(brief, "_prompts_seen", lambda: {})
    monkeypatch.setattr(person, "today", lambda now=None: dt.date(2026, 11, 10))
    import land
    monkeypatch.setattr(land, "stranded", lambda root=None, fetch=False: {}, raising=False)
    assert brief.start(["--on", "m", "--write"], "m") == 0
    return calls


def test_the_setup_script_runs_after_the_update_and_keeps_the_one_list(tmp_path, monkeypatch):
    """The brief kept its own list of packages and checked it before the update, so a package
    an update adds was never installed by the brief (review of fix/helpers, item 13). The
    setup script runs after the update check, and skips a ready Python side itself, from its one
    list (setup_env.sh, efficiency audit E-12)."""
    calls = _calls(tmp_path, monkeypatch, ready=True)
    assert not hasattr(brief, "PY_NEEDS")
    if os.name != "posix":
        return                    # the setup script is bash, run only where bash is the shell
    runs = [c for k, c in calls if k == "run"]
    sync = next(i for i, c in enumerate(runs) if "sync_app.py" in c)
    setup = next(i for i, c in enumerate(runs) if "setup_env.sh" in c)
    assert sync < setup
    script = open(os.path.join(ROOT, "tools", "setup_env.sh"), encoding="utf-8").read()
    assert 'python3 -c "import pytest, pypdf, yaml, openpyxl"' in script
