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
from tests import repo_files  # noqa: E402


def test_it_ships_on_and_the_example_keeps_it_on():
    skill = (ROOT / ".agents/skills/linkedin-search/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"^enabled: true\b", skill, re.M)
    assert portals.enabled().get("linkedin-search") is True
    example = (ROOT / "profile.example/search.py").read_text(encoding="utf-8")
    assert not re.search(r"['\"]linkedin-search['\"]\s*:\s*False", example)


def writes_it_off(root=ROOT) -> list[str]:
    """The app's own files that set LinkedIn's switch off. A person's own files are theirs
    to write in: their notes may quote the switch, and their profile is where it lives."""
    off = re.compile(r"['\"]linkedin-search['\"]\s*:\s*False")
    return [n for n in repo_files.tracked(root=root) if not n.startswith(("tests/", "CHANGELOG"))
            and (Path(root) / n).suffix in (".py", ".md", ".js", ".json", ".sh")
            and off.search((Path(root) / n).read_text(encoding="utf-8", errors="replace"))]


def test_nothing_in_the_app_writes_it_off():
    # The one place that names the switch is the explanation of the person's own line.
    assert writes_it_off() == ["tools/portals.py"]


def test_a_person_may_write_it_off_in_their_own_files(tmp_path):
    # Their profile is where the switch lives, and their notes may quote it. Only the
    # app's files are held to this, and a name with a space in it is read whole.
    files = {"tools/portals.py": "PORTALS = {'linkedin-search': False}\n",
             "profile/search.py": "PORTALS = {'linkedin-search': False}\n",
             "handoff/notes.md": "Tried 'linkedin-search': False for a week.\n",
             "tools/odd name.md": "'linkedin-search': False\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    assert writes_it_off(tmp_path) == ["tools/odd name.md", "tools/portals.py"]


def test_no_upgrade_or_instruction_suggests_switching_it_off():
    turn_off = re.compile(r"(?:turn|switch)\w*\s+(?:it\s+|LinkedIn\s+|linkedin-search\s+)?off",
                          re.I)
    for u in U.REGISTRY:
        text = " ".join((u.run or "", u.ask or "", u.gives or ""))
        assert not ("linkedin" in text.lower() and turn_off.search(text)), u.id
    setup = (ROOT / ".claude/commands/setup.md").read_text(encoding="utf-8")
    assert "Claude never switches it off and never suggests it" in setup
    assert "uses no LinkedIn\n  account" in setup or "uses no LinkedIn account" in setup
