"""No command crashes when it is run with nothing, or asked for help.

From one person's repo: audit_letters.py, fit_to_page.py, outreach.py and
render_application.py died on an IndexError with no arguments, outreach.py --help
crashed, and bar.py read "--help" as a company. Every command that reads its arguments
by position is run here both ways; one that takes names prints its usage for --help.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _positional_commands() -> list[str]:
    out = []
    for base in ("tools", os.path.join("tools", "network")):
        for f in sorted(os.listdir(os.path.join(ROOT, base))):
            if not f.endswith(".py"):
                continue
            text = open(os.path.join(ROOT, base, f), encoding="utf-8").read()
            at = re.search(r"__name__ == ['\"]__main__['\"]", text)
            main = text[at.start():] if at else ""
            if main and re.search(r"sys\.argv\[\d\]|for \w+ in sys\.argv\[1:\]|\" \"\.join\(sys\.argv",
                                  main + text):
                out.append(os.path.join(base, f))
    return out


COMMANDS = _positional_commands()


def test_the_commands_that_read_arguments_by_position_are_found():
    for name in ("audit_letters.py", "fit_to_page.py", "outreach.py", "render_application.py",
                 "bar.py", "company_key.py", "sector.py", "robots_check.py"):
        assert any(c.endswith(name) for c in COMMANDS), name


@pytest.mark.parametrize("cmd", COMMANDS)
def test_nothing_or_help_never_crashes(cmd, tmp_path):
    env = dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example"), LJS_STATE=str(tmp_path))
    for args in ([], ["--help"]):
        r = subprocess.run([sys.executable, os.path.join(ROOT, cmd), *args], cwd=str(tmp_path),
                           capture_output=True, text=True, env=env, timeout=120,
                           stdin=subprocess.DEVNULL)
        assert "Traceback" not in r.stderr, (cmd, args, r.stderr[-400:])
        if args:
            assert "usage" in (r.stdout + r.stderr).lower(), (cmd, r.stdout[:200])
            assert r.returncode == 0, (cmd, r.returncode)
