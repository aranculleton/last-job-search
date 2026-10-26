"""Every rule the long CLAUDE.md held has a home, and the core stays short.

Before 4.0 the app's CLAUDE.md was 54,234 characters and 737 lines, and every model call
in a person's repo carried it: every chat, every turn, and every subagent that did not set
`omitClaudeMd`. Claude Code's own guidance is to "target under 200 lines per CLAUDE.md
file. Longer files consume more context and reduce adherence", to move "a multi-step
procedure" or what "only matters for one part of the codebase" into a skill or a
path-scoped rule, and it says an `@` import does not help, "because imported files load
together with the CLAUDE.md that imports them" (code.claude.com/docs/en/memory, read
2026-10-25). Files in a subfolder "load on demand": a folder's own CLAUDE.md is loaded
"once Claude reads, writes, or edits another file in that subdirectory".

So 4.0 keeps a short core and moves every other rule to the file the work that needs it
already reads. `docs/rule_map.json` is the record: each rule of the old file (each bolded
rule, each never or always sentence, and the rows of its memory table) with the file it
now lives in and a phrase that file holds, and, under `readers`, which files each kind of
work reads, in the order it reaches them. These tests fail when:

- an anchor is missing from its file (a rule was edited away, or never written there);
- a rule's home is a file the work that needs it does not read;
- a reader claims a file nothing sends it to: each file after the first must be named in
  an earlier file of the same reader, be a skill whose description triggers on the
  reader's command, or be a folder's CLAUDE.md for a folder the work touches. The core
  counts as loaded for every main chat, but it never vouches for a command's reading: a
  pointer in the core is not a pointer in `/apply`;
- CLAUDE.md grows past 12,000 characters;
- a bolded rule appears in CLAUDE.md with no map entry.
"""
from __future__ import annotations

import json
import os
import re

from tests import repo_files

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "docs", "rule_map.json")
CORE = "CLAUDE.md"
CAP = 12_000
NEW = "new in 4.0"


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _norm(text: str) -> str:
    return " ".join(text.split())


def _map() -> dict:
    with open(MAP_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _rules() -> list[dict]:
    return _map()["rules"]


def _readers() -> dict:
    return _map()["readers"]


def _description(skill_md: str) -> str:
    text = _read(skill_md)
    if not text.startswith("---"):
        return ""
    return text.split("\n---", 1)[0]


def _unique_basenames() -> set[str]:
    seen: dict[str, int] = {}
    for p in repo_files.files("*.md", "**/*.md"):
        seen[p.name] = seen.get(p.name, 0) + 1
    return {name for name, n in seen.items() if n == 1}


def _named(earlier: str, path: str, unique: set[str]) -> bool:
    """`path` is named in `earlier`: whole, by a tail with a folder in it
    (`networking/SKILL.md`), or by a basename no other doc shares (`RUNBOOK.md`)."""
    parts = path.split("/")
    tails = ["/".join(parts[i:]) for i in range(len(parts) - 1)]
    if any(t in earlier for t in tails):
        return True
    return parts[-1] in unique and parts[-1] in earlier


# ------------------------------------------------------------------ the core

def test_the_core_stays_under_its_cap():
    text = _read(CORE)
    assert _map()["cap"] == CAP
    assert len(text) <= CAP, (
        f"CLAUDE.md is {len(text)} characters, over {CAP}. It loads on every call of every "
        "chat: move the new rule to the file the work that needs it reads, and map it in "
        "docs/rule_map.json.")


def test_every_bolded_rule_in_the_core_is_in_the_map():
    spans = {_norm(s) for s in re.findall(r"\*\*(.+?)\*\*", _read(CORE), re.S)}
    mapped = {_norm(r["core_bold"]) for r in _rules() if r["home"] == CORE and r.get("core_bold")}
    assert spans - mapped == set(), (
        "bolded in CLAUDE.md with no entry in docs/rule_map.json (home CLAUDE.md, "
        "core_bold the bolded words): " + "; ".join(sorted(spans - mapped)))
    assert mapped - spans == set(), "mapped as bold in CLAUDE.md but no longer bold there"


def test_the_core_imports_the_person_and_names_the_one_start():
    text = _read(CORE)
    assert "\n@profile/CLAUDE.md\n" in text
    assert "python3 tools/app.py start" in text
    assert "python3 tools/save_state.py" in text


def test_the_core_recommends_no_move_to_a_computer_chat():
    # 4.0: the page and the cloud chats do everything; a computer chat is optional.
    text = _norm(_read(CORE)).lower()
    assert "two chats" not in text and "for everything they do" not in text


# ------------------------------------------------------------------ the map

def test_the_map_covers_every_section_of_the_old_core():
    m = _map()
    sections = m["before"]["sections"]
    rules = m["rules"]
    assert len(rules) >= 120, len(rules)
    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids)), "an id is used twice"
    for r in rules:
        assert r["was"] in sections or r["was"] == NEW, r["id"]
        for field in ("rule", "home", "anchor"):
            assert r[field].strip(), (r["id"], field)
        assert r["needed_by"], r["id"]
    left_out = [s for s in sections if not any(r["was"] == s for r in rules)]
    assert left_out == [], f"no rule from these sections has a home: {left_out}"


def test_every_anchor_is_in_its_home():
    missing = []
    for r in _rules():
        path = os.path.join(ROOT, r["home"])
        if not os.path.isfile(path):
            missing.append(f"{r['id']}: {r['home']} does not exist")
        elif _norm(r["anchor"]) not in _norm(_read(r["home"])):
            missing.append(f"{r['id']}: {r['home']} no longer says {r['anchor']!r}")
    assert missing == [], "\n".join(missing)


def test_every_rule_lives_where_the_work_that_needs_it_reads():
    readers = _readers()
    wrong = []
    for r in _rules():
        for who in r["needed_by"]:
            assert who in readers, f"{r['id']}: no reader called {who!r}"
            rd = readers[who]
            if r["home"] in rd["files"] or (r["home"] == CORE and rd["main"]):
                continue
            wrong.append(f"{r['id']}: {who} needs it, and reads {rd['files']}, not {r['home']}")
    assert wrong == [], "\n".join(wrong)


def test_each_reader_is_sent_to_every_file_it_reads():
    unique = _unique_basenames()
    loose = []
    for who, rd in _readers().items():
        files = rd["files"]
        assert files, who
        for f in files:
            assert os.path.isfile(os.path.join(ROOT, f)), f"{who}: {f} does not exist"
        if not rd["main"]:
            assert CORE not in files, f"{who} starts without the project's CLAUDE.md"
        for i, f in enumerate(files[1:], start=1):
            earlier = [g for g in files[:i] if g != CORE or files[0] == CORE]
            if any(_named(_read(g), f, unique) for g in earlier):
                continue
            if f.endswith("SKILL.md") and who.startswith("/") and \
                    re.search(re.escape(who) + r"\b", _description(f)):
                continue
            folder = f[: -len("CLAUDE.md")]
            if f.endswith("/CLAUDE.md") and any(t.startswith(folder) for t in rd.get("touches", ())):
                continue
            loose.append(f"{who}: nothing before {f} in {files} sends it there")
    assert loose == [], "\n".join(loose)


def test_a_folders_claude_md_is_a_home_only_for_work_in_that_folder():
    readers = _readers()
    for r in _rules():
        if r["home"].endswith("/CLAUDE.md"):
            folder = r["home"][: -len("CLAUDE.md")]
            for who in r["needed_by"]:
                assert any(t.startswith(folder) for t in readers[who].get("touches", ())), (
                    f"{r['id']}: {r['home']} loads only when a file in {folder} is read")


def test_every_command_and_the_scraper_skill_are_readers():
    readers = _readers()
    entries = {rd["files"][0] for rd in readers.values()}
    commands = sorted(f for f in os.listdir(os.path.join(ROOT, ".claude", "commands"))
                      if f.endswith(".md"))
    for name in commands:
        rel = f".claude/commands/{name}"
        assert f"/{name[:-3]}" in readers and readers[f"/{name[:-3]}"]["files"][0] == rel, rel
    assert ".claude/skills/job-scraper/SKILL.md" in entries
    assert ".claude/skills/app/SKILL.md" in entries


def test_the_rules_that_moved_point_back_from_the_core():
    # The core's pointer table names every file a moved rule lives in, so a chat that
    # needs one finds it from the one file it always has.
    core = _read(CORE)
    homes = {r["home"] for r in _rules() if r["home"] != CORE}
    by_name = {
        ".claude/skills/networking/SKILL.md": "networking skill",
        ".claude/skills/job-scraper/SKILL.md": "job-scraper skill",
        ".claude/skills/job-application-assistant/SKILL.md": "`/apply`",
        ".claude/skills/job-application-assistant/verification-checklist.md": "`/apply`",
        ".claude/commands/apply.md": "`/apply`",
        ".claude/commands/setup.md": "`/setup`",
        ".claude/commands/add-portal.md": "`/setup`",
        ".claude/commands/upgrade.md": "RUNBOOK.md, \"Start of a session\"",
        ".claude/agents/grounding-auditor.md": "`/apply`",
        "tools/CLAUDE.md": "MAINTAINING.md",
        "tests/CLAUDE.md": "MAINTAINING.md",
    }
    for home in sorted(homes):
        assert by_name.get(home, home) in core, home
