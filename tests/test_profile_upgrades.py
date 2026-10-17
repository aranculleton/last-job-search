"""Profile upgrades: a feature that needs something done on the person's side reaches
the people who set up before it existed.

/setup runs once. When the app added job-board research (profile/search.py
PORTAL_RESEARCH), every profile written before it never got any: rounds kept
searching LinkedIn and freehire only, however often the repo synced, and nothing
said so. The registry checks each person's repo for the trace each action
leaves, the sync lists what is missing, and these tests keep it honest:

- the example is always fully upgraded, and each upgrade is pending on a copy of
  it with that upgrade's trace taken out;
- a profile name added since the first release is covered by an upgrade or
  has a stated safe default;
- a CHANGELOG entry that tells existing users to do something names its upgrade;
- the sync lists the pending upgrades whether it merged anything or not, and an
  instant upgrade commits only the personal files it owns.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import portals  # noqa: E402
import profile_names  # noqa: E402
import profile_upgrades as U  # noqa: E402

EXAMPLE = os.path.join(ROOT, "profile.example")


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A copy of the example profile, in use for the test."""
    d = tmp_path / "profile"
    shutil.copytree(EXAMPLE, d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _drop(profile_dir, module, *names):
    """Take assignments of `names` out of profile/<module>.py, as an older profile lacks them."""
    path = profile_dir / f"{module}.py"
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    cut = set()
    for node in ast.parse(src).body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", None) in names for t in targets):
            cut.update(range(node.lineno - 1, node.end_lineno))
    assert cut, f"{names} not assigned in {module}.py"
    path.write_text("".join(ln for i, ln in enumerate(lines) if i not in cut), encoding="utf-8")
    person._modules.clear()


def _drop_key(profile_dir, dotted):
    path = profile_dir / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    node = data
    *parents, last = dotted.split(".")
    for part in parents:
        node = node[part]
    del node[last]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()


def _set_country(profile_dir, code):
    path = profile_dir / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["identity"]["country"] = code
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()


# ------------------------------------------------------------------ the registry

def test_every_upgrade_is_well_formed():
    ids = [u.id for u in U.REGISTRY]
    assert len(ids) == len(set(ids))
    for u in U.REGISTRY:
        assert re.fullmatch(r"[a-z][a-z0-9-]+", u.id), u.id
        dt.date.fromisoformat(u.added)
        assert u.cost in U.COSTS and u.gives and u.run, u.id
        if u.cost == "instant":
            assert u.command and u.paths, f"{u.id}: an instant upgrade names its command and paths"


def test_the_example_is_fully_upgraded(profile):
    assert [(u.id, why) for u, why in U.pending()] == []


@pytest.mark.parametrize("uid", [u.id for u in U.REGISTRY if u.names and not u.conditional])
def test_each_named_upgrade_is_pending_without_its_names(profile, uid):
    u = U.by_id(uid)
    by_module: dict = {}
    for full in u.names:
        if full.startswith("person.json:"):
            _drop_key(profile, full.split(":", 1)[1])
            continue
        module, name = full.split(".", 1)
        by_module.setdefault(module, []).append(name)
    for module, names in by_module.items():
        _drop(profile, module, *names)
    assert u.pending(), f"{uid} is not pending on a profile without {u.names}"


def test_every_conditional_upgrade_has_its_own_test():
    here = open(__file__, encoding="utf-8").read()
    for u in U.REGISTRY:
        if u.conditional:
            assert f'by_id("{u.id}")' in here, f"{u.id} is conditional and has no test of its own"


def test_a_bullet_theme_no_posting_word_matches(profile):
    path = profile / "bullets.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '{"forecasting", "modelling", "python", "sql", "commercial"}',
        '{"forecasting", "modelling", "python", "sql", "commercial", "ward_rounds"}', 1),
        encoding="utf-8")
    assert "ward_rounds" in U.by_id("bullet-themes").pending()


def test_the_working_week_is_asked_only_where_it_differs(profile):
    _drop(profile, "search", "WEEKEND") if "WEEKEND" in (profile / "search.py").read_text() else None
    assert U.by_id("market-week").pending() == ""            # GB: Saturday and Sunday is right
    _set_country(profile, "SA")
    assert "weekend" in U.by_id("market-week").pending()


def test_the_market_language_is_asked_only_outside_english_markets(profile):
    assert U.by_id("market-language").pending() == ""        # GB, English postings
    _set_country(profile, "DE")
    text = (profile / "search.py").read_text(encoding="utf-8")
    present = [n for n in ("INTERNAL_ONLY", "INTERNAL_ONLY_TITLE", "CANARY_QUERY")
               if re.search(rf"^{n}\b", text, re.M)]
    if present:
        _drop(profile, "search", *present)
    assert "INTERNAL_ONLY" in U.by_id("market-language").pending()


def test_a_letter_in_another_language_gets_its_own_greeting(profile):
    assert U.by_id("letter-language").pending() == ""
    path = profile / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["documents"]["headings"] = {"summary": "Profil", "experience": "Berufserfahrung",
                                     "skills": "Kenntnisse", "education": "Ausbildung",
                                     "certifications": "Zertifikate"}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()
    assert U.by_id("letter-language").pending() == ""        # it set its own words
    _drop_key(profile, "documents.salutation_prefix")
    assert "Dear" in U.by_id("letter-language").pending()


def test_an_undated_look_at_the_boards_is_not_done(profile):
    path = profile / "search.py"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'"checked":\s*"[^"]*"', '"checked": ""', text), encoding="utf-8")
    person._modules.clear()
    assert "dated" in U.by_id("boards").pending()


def test_a_portal_built_before_the_contract_is_an_upgrade(profile, tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    for name, front in (("linkedin-search", ""), ("freehire-search", ""),
                        ("oldboard-search", ""), ("newboard-search", "contract: 1\n")):
        (skills / name / "cli" / "src").mkdir(parents=True)
        (skills / name / "cli" / "src" / "cli.ts").write_text("// cli\n")
        (skills / name / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n{front}---\n")
    monkeypatch.setattr(portals, "SKILLS", str(skills))
    why = U.by_id("portal-contract").pending()
    assert "oldboard-search" in why and "newboard-search" not in why


def test_a_portal_switched_on_that_no_longer_exists_is_an_upgrade(profile):
    path = profile / "search.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "PORTALS: dict[str, bool] = {}", 'PORTALS: dict[str, bool] = {"jobnet-search": True}'),
        encoding="utf-8")
    person._modules.clear()
    assert "jobnet-search" in U.by_id("missing-portal").pending()


def test_a_needed_setting_missing_from_an_older_profile_is_an_upgrade(profile):
    needed = sorted((m, n) for m, d in profile_names.collect().items()
                    for n, e in d.items() if e["required"] and (profile / f"{m}.py").exists())
    module, name = needed[0]
    _drop(profile, module, name)
    assert f"{module}.{name}" in U.by_id("required").pending()


def test_no_profile_means_nothing_to_upgrade(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(person.ENV, str(tmp_path / "nowhere"))
    person._modules.clear()
    assert U.main([]) == 0 and capsys.readouterr().out == ""


def test_statement_templates_scoring_and_role_headings_read_the_profile(profile):
    md = profile / "CLAUDE.md"
    md.write_text(md.read_text(encoding="utf-8").replace("## Profile statement templates",
                                                          "## Notes"), encoding="utf-8")
    assert U.by_id("statement-templates").pending()
    cp = profile / "01-candidate-profile.md"
    text = cp.read_text(encoding="utf-8")
    cp.write_text(re.sub(r"^(### [^\n]+?) - ", r"\1, ", text, count=1, flags=re.M), encoding="utf-8")
    assert U.by_id("role-headings").pending()


def test_a_field_the_scoring_vocabulary_was_not_written_for(profile):
    path = profile / "search.py"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^SCRAPE_QUERIES = \[", text, re.M)
    path.write_text(text[:m.end()] + '"registered nurse", ' + text[m.end():], encoding="utf-8")
    person._modules.clear()
    assert "registered nurse" in U.by_id("scoring-vocabulary").pending()


def test_the_round_line_says_what_claude_applies_and_what_needs_you(profile):
    _drop(profile, "search", "PORTAL_RESEARCH", "JOB_ALERT_QUERY")
    assert U.line() == ("Profile upgrades: 1 Claude applies itself (boards); "
                        "1 needs you (job-alerts).")


# ------------------------------------------------------------------ nobody has to ask

def test_every_upgrade_says_how_urgent_it_is_and_who_it_needs():
    for u in U.REGISTRY:
        assert u.priority in (1, 2, 3, 4), u.id
        assert u.needs in ("nobody", "you"), u.id


def test_only_what_truly_needs_the_person_waits_for_them():
    """A list a person has to read and act on is a list nobody acts on. Adding to
    this set is a decision: the upgrade cannot be done from the profile and research."""
    assert {u.id for u in U.REGISTRY if u.needs == "you"} == {"job-alerts", "unconfirmed-facts",
                                                                 "method-routines", "linkedin-plan",
                                                                 "learned-choices", "profile-reads"}
    assert "inbox" in U.by_id("job-alerts").ask
    # Consent to a risk to their own account names the risk.
    assert "terms forbid" in U.by_id("profile-reads").ask


def test_the_plan_is_most_urgent_first(profile):
    _drop(profile, "search", "PORTAL_RESEARCH")
    _drop(profile, "skills", "LABELS")
    ids = [p["id"] for p in U.plan()]
    assert ids == ["skills-headings", "boards"]
    assert U.plan()[0]["needs"] == "nobody" and U.plan()[0]["why"]


def test_check_answers_for_one_upgrade(profile, capsys):
    assert U.main(["--check", "boards"]) == 0 and capsys.readouterr().out.strip() == "done"
    _drop(profile, "search", "PORTAL_RESEARCH")
    assert U.main(["--check", "boards"]) == 1 and "PORTAL_RESEARCH" in capsys.readouterr().out


def test_an_unconfirmed_fact_is_asked_until_it_is_answered(profile):
    assert U.by_id("unconfirmed-facts").pending() == ""
    cp = profile / "01-candidate-profile.md"
    cp.write_text(cp.read_text(encoding="utf-8")
                  + "\n- Settled status expires: [CONFIRM: the expiry date on the share code]\n",
                  encoding="utf-8")
    (profile / "tests").mkdir(exist_ok=True)
    (profile / "tests" / "test_x.py").write_text('MARK = "[CONFIRM: not a fact]"\n')
    why = U.by_id("unconfirmed-facts").pending()
    assert why.startswith("1 fact in your profile only you can confirm: the expiry date")
    block = U.block(U.pending())
    assert "These need you" in block and "the expiry date on the share code" in block


def test_the_sync_block_splits_what_claude_does_from_what_needs_you(profile):
    _drop(profile, "search", "PORTAL_RESEARCH", "JOB_ALERT_QUERY")
    block = U.block(U.pending())
    alone, yours = block.split("These need you")
    assert "boards" in alone and "Claude applies these itself" in alone
    assert "job-alerts" in yours and "inbox" in yours


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_a_session_applies_them_without_being_asked():
    claude = _read("CLAUDE.md")
    step = claude[claude.index("5. **Profile upgrades"):claude.index("In the app itself")]
    for must in ("run_in_background: true", 'isolation: "worktree"', "/upgrade",
                 "never offer them a list or wait for a yes", "at most three",
                 "git revert <sha>"):
        assert must in step, must
    cmd = _read(".claude", "commands", "upgrade.md")
    for must in ("Never ask the person", "[CONFIRM:", "--check <id>", "Profile upgrade: <id>",
                 "git revert <sha>", "Never switch off a portal"):
        assert must in cmd, must


def test_every_scheduled_run_takes_the_apps_updates_first():
    """A person may not open a chat for days; the brief is what keeps their copy current."""
    common = _read("automation", "prompts", "_common.md")
    assert "python3 tools/sync_app.py --if-stale" in common and "/upgrade 20" in common
    assert common.index("sync_app.py --if-stale") < common.index("setup_env.sh")
    rnd = _read("automation", "prompts", "job_round.md")
    assert "_common.md` step 2" in rnd and "/upgrade 20" in rnd


def test_the_brief_never_searches():
    brief = _read("automation", "prompts", "morning_brief.md")
    assert "run_round" not in brief and "Never run a search here" in brief


# ------------------------------------------------------------------ the lints

def _names_now() -> set:
    out = {f"{m}.{n}" for m, d in profile_names.collect().items() for n in d}
    out |= {f"person.json:{k}" for k in profile_names.collect_person()}
    return out


def test_a_new_profile_name_is_an_upgrade_or_a_stated_safe_default():
    """Every name a tool reads that the first release did not: covered by an
    upgrade, or listed in SAFE_DEFAULTS with the reason. An older profile lacks
    every one of them, so each needs that decision."""
    with open(os.path.join(ROOT, "tools", "profile_names_baseline.txt"), encoding="utf-8") as fh:
        baseline = {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}
    covered = {n for u in U.REGISTRY for n in u.names} | set(U.SAFE_DEFAULTS)
    undecided = sorted(_names_now() - baseline - covered)
    assert undecided == [], ("profile names with no upgrade and no stated safe default "
                             f"(tools/profile_upgrades.py): {undecided}")


def test_safe_defaults_and_upgrade_names_are_real_names():
    now = _names_now()
    for n in list(U.SAFE_DEFAULTS) + [n for u in U.REGISTRY for n in u.names]:
        assert n in now, f"{n} is not read by any tool"
    assert all(len(r) > 20 for r in U.SAFE_DEFAULTS.values())


# A bullet that tells someone already set up to do something. Descriptions of
# what /setup does for a new person are not instructions.
INSTRUCTION = re.compile(r"\*\*If you|\bIf your\b|\bre-?run\b|\brun `|/setup --section|"
                         r"\bcopy\b[^.]*\binto your profile|\bput it back\b|\bbuild it again\b",
                         re.I)
MARK = re.compile(r"Profile upgrade: `([a-z0-9-]+)`")


def _unreleased_and_later():
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    head = text[text.index("## [Unreleased]"):text.index("## [3.0.0]")]
    return [b for b in re.split(r"\n(?=- \*\*)", head) if b.startswith("- **")]


def test_a_changelog_instruction_names_its_upgrade():
    ids = {u.id for u in U.REGISTRY}
    loose = []
    for bullet in _unreleased_and_later():
        marks = MARK.findall(bullet)
        assert set(marks) <= ids, f"unknown upgrade named in: {bullet[:90]}"
        if INSTRUCTION.search(bullet) and not marks and "No profile upgrade:" not in bullet:
            loose.append(bullet[:100].replace("\n", " "))
    assert loose == [], ("CHANGELOG entries that tell existing users to act, with no "
                         f"`Profile upgrade: <id>` or `No profile upgrade:` reason: {loose}")


# ------------------------------------------------------------------ the instant runner

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, text=True,
                          capture_output=True, env=dict(os.environ, GIT_AUTHOR_NAME="t",
                          GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                          GIT_COMMITTER_EMAIL="t@example.com")).stdout


IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def test_an_instant_upgrade_commits_only_its_own_personal_files(tmp_path, monkeypatch):
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    repo = tmp_path / "repo"
    (repo / "documents" / "network").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "README.md").write_text("app\n")
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    monkeypatch.setattr(U, "ROOT", str(repo))
    good = U.Upgrade("prep-docs", "2026-10-15", "prep docs re-rendered", lambda: "stale",
                     "x", "instant", command=(sys.executable, "-c",
                     "open('documents/network/prep_a.md','w').write('new')"),
                     paths=("documents/network/*.md",))
    bad = U.Upgrade("strays", "2026-10-15", "a tool that writes outside its files", lambda: "x",
                    "x", "instant", command=(sys.executable, "-c",
                    "open('tools/x.py','w').write('1');open('documents/network/b.md','w').write('2')"),
                    paths=("documents/network/*.md",))
    notes = U.run_instant([(good, "stale"), (bad, "x")])
    assert notes[0].startswith("prep-docs: applied") and "outside its own files" in notes[1]
    log = _git(repo, "log", "--format=%s")
    assert "Profile upgrade: prep-docs" in log and "strays" not in log
    assert not (repo / "tools" / "x.py").exists()
    assert _git(repo, "status", "--porcelain") == ""


def test_instant_upgrades_wait_for_a_clean_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    (repo / "half_done.txt").write_text("x")
    monkeypatch.setattr(U, "ROOT", str(repo))
    assert "uncommitted" in U.run_instant([])[0]


def test_a_commit_that_fails_leaves_nothing_changed_and_says_so(tmp_path, monkeypatch):
    """A session with no git identity cannot commit. Reported as committed, the
    upgrade left the person's files changed and uncommitted. A refusing hook
    stands in for any reason a commit fails."""
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    repo = tmp_path / "repo"
    (repo / "documents" / "network").mkdir(parents=True)
    (repo / "README.md").write_text("app\n")
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "config", "core.hooksPath", str(tmp_path / "hooks"))
    (tmp_path / "hooks").mkdir()
    hook = tmp_path / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho refused >&2\nexit 1\n")
    hook.chmod(0o755)
    monkeypatch.setattr(U, "ROOT", str(repo))
    good = U.Upgrade("prep-docs", "2026-10-15", "prep docs re-rendered", lambda: "stale",
                     "x", "instant", command=(sys.executable, "-c",
                     "open('documents/network/prep_a.md','w').write('new')"),
                     paths=("documents/network/*.md",))
    notes = U.run_instant([(good, "stale")])
    assert notes == ["prep-docs: not applied (the commit failed: refused)"]
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "log", "--format=%s") == "init\n"
