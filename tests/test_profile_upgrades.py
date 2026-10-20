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
    # The example's nos are as recent as the run, so a calendar date never turns the suite
    # red: a no is asked again after REASK_DAYS, and that is tested on its own below.
    asked = d / "asked.json"
    if asked.exists():
        got = json.loads(asked.read_text(encoding="utf-8"))
        for rec in got.values():
            rec["no"] = dt.date.today().isoformat()
        asked.write_text(json.dumps(got), encoding="utf-8")
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


def test_public_holidays_are_researched_only_where_no_rules_cover_the_country(profile):
    import holidays
    holidays.for_year.cache_clear()
    assert U.by_id("public-holidays").pending() == ""                 # GB: the rules cover it
    _set_country(profile, "SA")
    assert "no public holidays on file for SA" in U.by_id("public-holidays").pending()
    path = profile / "search.py"
    year = __import__("datetime").date.today().year + 1
    path.write_text(path.read_text(encoding="utf-8")
                    + f'\nPUBLIC_HOLIDAYS = ("{year}-09-23",)\n', encoding="utf-8")
    person._modules.clear()
    assert U.by_id("public-holidays").pending() == ""


def test_the_working_week_is_asked_only_where_it_differs(profile):
    _drop(profile, "search", "WEEKEND") if "WEEKEND" in (profile / "search.py").read_text() else None
    assert U.by_id("market-week").pending() == ""            # GB: Saturday and Sunday is right
    _set_country(profile, "SA")
    assert "weekend" in U.by_id("market-week").pending()


def test_the_read_break_is_written_only_for_someone_who_reads_in_their_browser(profile):
    assert U.by_id("read-break").pending() == ""             # the example pastes profiles
    path = profile / "networking.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        'PROFILE_READS = "paste"', 'PROFILE_READS = "browser"'), encoding="utf-8")
    person._modules.clear()
    assert "PROFILE_READ_BREAK_MINUTES" in U.by_id("read-break").pending()
    path.write_text(path.read_text(encoding="utf-8") + "\nPROFILE_READ_BREAK_MINUTES = (5, 12)\n",
                    encoding="utf-8")
    person._modules.clear()
    assert U.by_id("read-break").pending() == ""


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
    # Plain words only: an id or a version number reaches the person as jargon.
    assert U.line() == ("Improvements waiting: 1 Claude applies itself; 1 short question for "
                        "you (python3 tools/profile_upgrades.py).")


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
                                                                 "learned-choices", "profile-reads",
                                                                 "connections-export", "work-place",
                                                                 "profile-consistency",
                                                                 "campaign-notes", "message-texts",
                                                                 "voice-refresh"}
    assert "inbox" in U.by_id("job-alerts").ask
    # Consent to a risk to their own account names the risk.
    assert "terms forbid" in U.by_id("profile-reads").ask
    # Only the person can download their own connections; Claude never touches LinkedIn.
    assert U.by_id("connections-export").steps().endswith("Nothing is sent to anyone.")
    # Where they will mostly work is theirs to say; nothing in a profile answers it.
    assert "computer, or on your phone or the web" in U.by_id("work-place").ask
    # Two answers to what a recruiter checks first: only the person knows which is true.
    assert "you pick the right one" in U.by_id("profile-consistency").ask
    # Their own notes are folded into the prep document only on their yes.
    assert "Can I fold them into it" in U.by_id("campaign-notes").ask
    # Only they have the words they sent; nothing in the app can fetch them.
    assert "paste them in once" in U.by_id("message-texts").ask


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
    assert "[boards]" in alone and "Claude applies these itself" in alone
    assert "[job-alerts]" in yours and "inbox" in yours


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


def test_a_no_is_for_now_never_for_ever(profile, monkeypatch):
    # A person disliked questions that were never asked again. A no comes back when what
    # the question offers has changed, saying what changed, or after REASK_DAYS, saying
    # when they said no; until then it stands.
    today = dt.date(2026, 10, 18)
    monkeypatch.setattr(U, "_mod", lambda name: (
        type("N", (), {"CONNECTIONS_EXPORT": "declined", "PROFILE_READS": "paste"}) if
        name == "networking" else None))
    (profile / "asked.json").unlink()
    u = U.by_id("connections-export")
    # A no from before this was kept: asked again once, with what changed.
    why = U.again(u.id, u.ask_version, u.changed, today)
    assert why.startswith("you said no before, and it has changed since: networking now finds")
    U.record_no(u.id, today)
    assert U.again(u.id, u.ask_version, u.changed, today) == ""
    assert U.again(u.id, u.ask_version, u.changed,
                   today + dt.timedelta(days=U.REASK_DAYS - 1)) == ""
    later = U.again(u.id, u.ask_version, u.changed, today + dt.timedelta(days=U.REASK_DAYS))
    assert later.startswith("you said no on 2026-10-18, 30 days ago")
    # A no from before this was kept, to a question that has not changed ("not now" to
    # job alerts three days earlier): held until REASK_DAYS after the question shipped,
    # never asked again the day the upgrade lands.
    a = U.by_id("job-alerts")
    assert a.ask_version == 1 and U.again(a.id, a.ask_version, a.changed, today) == ""
    added = dt.date.fromisoformat(a.added)
    assert U.again(a.id, a.ask_version, a.changed,
                   added + dt.timedelta(days=U.REASK_DAYS - 1)) == ""
    assert U.again(a.id, a.ask_version, a.changed,
                   added + dt.timedelta(days=U.REASK_DAYS)) == (
        "you said no before; it is asked once more in case that has changed")
    # The question changes: asked again at once, saying how.
    assert U.again(u.id, u.ask_version + 1, "something new", today).endswith("something new")
    # Every question a no can answer is re-askable, and says what it changed when it did.
    for uid in ("connections-export", "job-alerts", "profile-reads"):
        x = U.by_id(uid)
        assert x.needs == "you" and (x.ask_version == 1 or x.changed), uid
        assert "--no " + uid in x.run, uid
    assert not any("not asked again" in (x.ask or "") or "never asked again" in (x.run or "")
                   for x in U.REGISTRY)


def test_a_profile_line_telling_drafts_to_use_a_forbidden_phrase_is_found(profile):
    # A never-say left the profile's own instruction to use the phrase in place, so every
    # draft read both. Only a line that prescribes it counts.
    import learned
    learned.record("messages", "too casual", "never 'cheers'", never_say=["cheers"],
                   today="2026-10-18")
    (profile / "13-positioning.md").write_text(
        "Sign-off: the line is \"cheers\" in every note.\n"
        "Never write \"cheers\" to a recruiter.\n"
        "We said cheers at the leaving do.\n", encoding="utf-8")
    u = U.by_id("never-said")
    got = u.pending()
    assert "profile/13-positioning.md:1 ('cheers')" in got and u.needs == "nobody"
    assert ":2 " not in got and ":3 " not in got


# ------------------------------------------------------------------ asked short

# Words a person would not know, or would have to look up, in the first thing they are asked.
_JARGON = re.compile(r"\b(?:csv|export(?:ed)?|in bulk|upgrade|pending|version|round|method|"
                     r"inmail|python3?|profile/|\.py|\.json|ats)\b|[`/]", re.I)


def test_every_question_is_short_and_plain_with_its_detail_kept_for_a_yes():
    """A question is asked as one short plain question; the steps come only after a yes and
    the reason only after "why?". A paragraph pasted at someone is what nobody reads."""
    for u in U.REGISTRY:
        if u.needs != "you" or u.id == "unconfirmed-facts":   # its questions are the markers
            continue
        assert u.ask, u.id
        assert len(u.ask.split()) <= 40, (u.id, len(u.ask.split()))
        assert u.ask.rstrip().endswith("?"), u.id
        assert not _JARGON.search(u.ask), (u.id, _JARGON.search(u.ask).group(0))
        assert "\u2014" not in u.ask + u.why_ask
        if u.why_ask:
            assert u.why_ask.count(". ") == 0 and u.why_ask.endswith("."), u.id   # one sentence
        if u.steps:
            lines = u.steps().splitlines()
            assert 1 < len(lines) <= 5, (u.id, len(lines))
            assert not set(lines) & set(u.ask.splitlines())                       # kept apart
    steps = U.by_id("connections-export").steps().splitlines()
    assert steps[0].startswith("At the time of writing (checked ") and "official page: https://" in steps[0]
    assert steps[-1] == "I only read it. Nothing is sent to anyone."
    assert U.NO_REPLY == "No problem, I'll ask again in a month." and U.REASK_DAYS == 30


def test_a_kept_choice_and_a_no_come_back_on_the_same_day_count():
    import learned
    assert learned.REOFFER_DAYS == U.REASK_DAYS


def test_the_sync_block_shows_no_id_or_version_outside_its_brackets(profile):
    (profile / "build_versions.json").unlink(missing_ok=True)
    _drop(profile, "search", "PORTAL_RESEARCH", "JOB_ALERT_QUERY")
    block = U.block(U.pending())
    said = [re.sub(r"\s*\[[a-z0-9-]+\]$", "", ln) for ln in block.splitlines()
            if ln.startswith("    - ")]
    assert said and not any(re.search(r"\bversion \d|\bmethod-|\bupgrade\b", s) for s in said)


def test_a_story_with_no_use_for_line_is_tagged_in_the_background(profile):
    # An interview pack matches a story to a question by its `Use for:` line; a profile set
    # up before that line existed has stories no question can reach.
    u = U.by_id("interview-tags")
    assert u.needs == "nobody" and u.pending() == ""
    f = profile / "07-interview-prep.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## STAR: an untagged one\n"
                 "- **Situation:** s.\n- **Task:** t.\n- **Action:** a.\n- **Result:** r.\n",
                 encoding="utf-8")
    assert u.pending().startswith("1 STAR story in profile/07-interview-prep.md")
    assert "An untagged one" in u.pending()


def _process_state(tmp_path, monkeypatch):
    """A state root holding one hiring process with no application, as 3.7.0 registered it:
    its folder and outcome.md, and no job_posting.md. Invented employer and contact."""
    import csv
    import outreach
    import record_drafts
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    row = {k: "" for k in record_drafts.HEADER}
    row.update(date="2026-10-19", company="Calder & Rook Consulting", role="Operations Analyst",
               status="interview", channel="referral", source="contact:calder_rook_vance",
               notes="process, no portal application: led by Ivo Vance")
    with open(st / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=record_drafts.HEADER)
        w.writeheader()
        w.writerow(row)
    folder = outreach.app_folder(row["company"], row["role"])
    os.makedirs(folder)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome: Calder & Rook Consulting - Operations Analyst\n")
    return st, folder


def test_a_process_folder_with_no_posting_is_given_one(profile, tmp_path, monkeypatch):
    _st, folder = _process_state(tmp_path, monkeypatch)
    assert "1 hiring process folder(s) with no job_posting.md" in \
        U.by_id("process-postings").pending()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"),
                        "postings"], cwd=ROOT, env=os.environ, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = open(os.path.join(folder, "job_posting.md"), encoding="utf-8").read()
    assert "not held yet" in text and "--posting" in text
    assert U.by_id("process-postings").pending() == ""


def test_hand_kept_notes_for_a_process_are_offered_once_to_fold_in(profile, tmp_path,
                                                                    monkeypatch):
    st, folder = _process_state(tmp_path, monkeypatch)
    assert U.by_id("campaign-notes").pending() == ""            # nothing kept by hand
    net = st / "documents" / "network"
    net.mkdir(parents=True)
    (net / "calder_rook_campaign.md").write_text("Say I am based in Manchester.\n",
                                                  encoding="utf-8")
    (net / "open_actions.md").write_text("Everything owed.\n", encoding="utf-8")   # not theirs
    why = U.by_id("campaign-notes").pending()
    assert "documents/network/calder_rook_campaign.md" in why and "open_actions" not in why
    # Folded in: the process's document says so in its Notes, and it is not asked again.
    with open(os.path.join(folder, "interview_prep.md"), "w", encoding="utf-8") as fh:
        fh.write("## Notes\n\n- Folded in from documents/network/calder_rook_campaign.md on "
                 "2026-10-20.\n")
    assert U.by_id("campaign-notes").pending() == ""


def test_own_tests_reading_the_apps_code_or_pinning_changed_behaviour_are_kept_in_line(
        tmp_path, monkeypatch):
    import sync_app
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "round_step.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    tests = repo / "profile" / "tests"
    tests.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.setattr(U, "ROOT", str(repo))
    assert U.by_id("own-tests").pending() == ""                 # nothing of theirs at risk
    (tests / "test_reads.py").write_text(
        "import os\nROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))\n"
        "def test_it():\n"
        "    src = open(os.path.join(ROOT, 'tools', 'round_step.py')).read()\n"
        "    assert 'return 1' in src\n", encoding="utf-8")
    why = U.by_id("own-tests").pending()
    assert "read the app's code as text" in why and "test_reads.py" in why
    # Rewritten to run the code and check what it does: nothing left to do.
    (tests / "test_reads.py").write_text(
        "import round_step\ndef test_it():\n    assert round_step.run() == 1\n", encoding="utf-8")
    assert U.by_id("own-tests").pending() == ""
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qm", "tests"], check=True)
    # The sync found one checking behaviour the update changed: it is brought in line.
    sync_app.record_own_tests(str(repo), [("test_reads::test_it", "AssertionError: 2 != 1")])
    assert "check what an update changed: test_reads::test_it" in U.by_id("own-tests").pending()
    # One that used a part the update removed is the sync's question to the person, not this.
    sync_app.record_own_tests(str(repo), [(
        "test_reads::test_it", "AttributeError: module 'round_step' has no attribute 'gone'")])
    assert U.by_id("own-tests").pending() == ""


def test_reading_files_that_change_on_every_read_are_moved_out_of_the_repo(profile, tmp_path,
                                                                           monkeypatch):
    st = tmp_path / "state"
    (st / "documents" / "network").mkdir(parents=True)
    monkeypatch.setenv(person.STATE_ENV, str(st))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    assert U.by_id("runtime-files").pending() == ""
    (st / "documents" / "network" / ".shortlist.json").write_text(
        '{"date": "2026-10-20", "ids": ["bo_venn"]}', encoding="utf-8")
    assert "1 reading file(s) in documents/network" in U.by_id("runtime-files").pending()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                        "move-runtime"], cwd=ROOT, env=os.environ, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert U.by_id("runtime-files").pending() == ""
    assert '"bo_venn"' in open(tmp_path / "ledger" / "reading-ledger.json").read()


def test_messages_that_drew_replies_without_their_words_are_asked_for_once(profile, tmp_path,
                                                                            monkeypatch):
    import schema
    import state
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update(contact_id="larkspur_castellan", name="Juno Castellan", company="Larkspur",
               status="in_conversation")
    state.save_contacts([row], str(st / "network_contacts.csv"))
    out = {"contact_id": "larkspur_castellan", "date": "2026-09-01", "direction": "out",
           "channel": "inmail", "scenario": "first_message", "summary": "approach",
           "full_text": ""}
    back = {"contact_id": "larkspur_castellan", "date": "2026-09-01", "direction": "in",
            "channel": "inmail", "scenario": "reply", "summary": "replied",
            "full_text": "Thanks, let's talk."}
    state.save_threads([out, back], str(st / "network_threads.csv"))
    assert "1 message(s) that drew a reply" in U.by_id("message-texts").pending()
    state.save_threads([dict(out, full_text="Hi Juno, hope you're well."), back],
                       str(st / "network_threads.csv"))
    assert U.by_id("message-texts").pending() == ""


def test_a_saved_voice_in_the_old_stiff_wording_is_offered_a_rewrite(profile, monkeypatch):
    net = profile / "networking.py"
    text = net.read_text(encoding="utf-8")
    assert U.by_id("voice-refresh").pending() == ""          # the example's own voice
    net.write_text(text.replace(
        'ASK = "Would you have 15 minutes for a few questions sometime"',
        'ASK = "I would love to hear how your team works"'), encoding="utf-8")
    assert "ASK in profile/networking.py" in U.by_id("voice-refresh").pending()
    assert "rewrite them the way you write" in U.by_id("voice-refresh").ask
