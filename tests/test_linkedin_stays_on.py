"""LinkedIn's job search stays on, and only the person ever switches it off.

The person who runs this app said it plainly: stop disabling LinkedIn. It carries more
postings than every other source in most markets, it reads LinkedIn's public listings with
no LinkedIn account (so it cannot get anyone's account restricted), and turning it off is
the person's call alone, in profile/search.py PORTALS. These pin that no default, no tool,
no upgrade and no instruction turns it off or suggests it.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import portals  # noqa: E402
import profile_upgrades as U  # noqa: E402


def test_it_ships_on_and_the_example_keeps_it_on():
    skill = (ROOT / ".agents/skills/linkedin-search/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"^enabled: true\b", skill, re.M)
    assert portals.enabled().get("linkedin-search") is True
    example = (ROOT / "profile.example/search.py").read_text(encoding="utf-8")
    assert not re.search(r"['\"]linkedin-search['\"]\s*:\s*False", example)


def test_nothing_in_the_app_writes_it_off():
    # The one place that names the switch is the explanation of the person's own line.
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True).stdout.split()
    off = re.compile(r"['\"]linkedin-search['\"]\s*:\s*False")
    found = [n for n in names if not n.startswith(("tests/", "CHANGELOG"))
             and (ROOT / n).suffix in (".py", ".md", ".js", ".json", ".sh")
             and off.search((ROOT / n).read_text(encoding="utf-8", errors="replace"))]
    assert found == ["tools/portals.py"], found


def test_no_upgrade_or_instruction_suggests_switching_it_off():
    turn_off = re.compile(r"(?:turn|switch)\w*\s+(?:it\s+|LinkedIn\s+|linkedin-search\s+)?off",
                          re.I)
    for u in U.REGISTRY:
        text = " ".join((u.run or "", u.ask or "", u.gives or ""))
        assert not ("linkedin" in text.lower() and turn_off.search(text)), u.id
    setup = (ROOT / ".claude/commands/setup.md").read_text(encoding="utf-8")
    assert "Claude never switches it off and never suggests it" in setup
    assert "uses no LinkedIn\n  account" in setup or "uses no LinkedIn account" in setup
