"""tools/sync_app.py: a person's repo takes the app's updates and never its own edits back.

Each test builds two throwaway repositories: an "app" with a few commits, and a
person's repo made from it the way "Use this template" makes one (the app's
files, a fresh history, then a profile and a tracker on top). LJS_APP_URL points
the tool at the local app, so nothing touches the network.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           PYTHONDONTWRITEBYTECODE="1")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, env=ENV, text=True, encoding="utf-8", errors="replace", capture_output=True, check=True).stdout


def write(repo, rel, text):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def commit(repo, msg):
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", msg)


def head(repo):
    return sh(repo, "git", "rev-parse", "HEAD").strip()


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def repos(tmp_path):
    app = str(tmp_path / "app")
    os.makedirs(app)
    sh(app, "git", "init", "-q", "-b", "master")
    for tool in ("sync_app.py", "personal_paths.py"):
        write(app, f"tools/{tool}", read(ROOT, f"tools/{tool}"))
    write(app, ".gitignore", "__pycache__/\n")
    write(app, "README.md", "v1\n")
    write(app, "tools/x.py", "a = 1\n")
    write(app, "CHANGELOG.md", "# Changelog\n")
    commit(app, "app v1")

    me = str(tmp_path / "me")
    shutil.copytree(app, me, ignore=shutil.ignore_patterns(".git"))
    sh(me, "git", "init", "-q", "-b", "master")
    sh(me, "git", "remote", "add", "origin", "https://github.com/someone/my-job-search")
    commit(me, "Initial commit")
    write(me, "profile/person.json", "{}\n")
    write(me, "job_search_tracker.csv", "date,company\n")
    commit(me, "set me up")
    return app, me


def run(me, app, *args):
    env = dict(ENV, LJS_APP_URL=app)
    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py"), *args],
                       cwd=me, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    return r.returncode, r.stdout + r.stderr


def test_the_first_sync_merges_a_template_made_repo(repos):
    app, me = repos
    write(app, "README.md", "v2\n")
    write(app, "CHANGELOG.md", "# Changelog\n- README is v2\n")
    commit(app, "app v2")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "README.md") == "v2\n"
    assert read(me, "job_search_tracker.csv") == "date,company\n"
    assert len(sh(me, "git", "log", "-1", "--format=%P").split()) == 2
    assert "README is v2" in out


def test_a_later_sync_brings_only_the_new_commits(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    write(app, "tools/x.py", "a = 2\n")
    commit(app, "app v3")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "tools/x.py") == "a = 2\n"
    assert "1 new commit" in out
    rc, out = run(me, app)
    assert rc == 0 and "up to date" in out


def test_check_reports_and_changes_nothing(repos):
    app, me = repos
    run(me, app)
    write(app, "tools/x.py", "a = 3\n")
    commit(app, "app v3")
    before = head(me)
    rc, out = run(me, app, "--check")
    assert rc == 0 and "1 app commit(s) to bring in" in out
    assert head(me) == before


def test_an_app_file_edited_here_is_put_back_and_named(repos):
    app, me = repos
    run(me, app)
    write(me, "README.md", "my edit\n")
    write(me, "tools/mine.py", "mine = True\n")
    commit(me, "local edits")
    rc, out = run(me, app, "--check")
    assert "drift: 1" in out and "README.md" in out
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "README.md") == "v1\n"
    assert "put back (edited here): README.md" in out
    assert read(me, "tools/mine.py") == "mine = True\n"       # an addition is kept
    assert "README.md" in sh(me, "git", "log", "-1", "--format=%B")


def test_a_conflict_on_an_app_file_takes_the_apps_version(repos):
    app, me = repos
    run(me, app)
    write(me, "tools/x.py", "a = 'mine'\n")
    commit(me, "local edit")
    write(app, "tools/x.py", "a = 'app'\n")
    commit(app, "app edit")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "tools/x.py") == "a = 'app'\n"


def test_an_app_that_carries_a_personal_path_is_refused(repos):
    app, me = repos
    write(app, "job_search_tracker.csv", "date,company\nleaked,row\n")
    commit(app, "broken app")
    before = head(me)
    rc, out = run(me, app)
    assert rc == 1 and "job_search_tracker.csv" in out
    assert head(me) == before
    assert read(me, "job_search_tracker.csv") == "date,company\n"


def test_uncommitted_changes_stop_it_first(repos):
    app, me = repos
    write(me, "README.md", "half done\n")
    rc, out = run(me, app)
    assert rc == 1 and "Commit or stash" in out
    assert read(me, "README.md") == "half done\n"


def test_in_the_app_itself_it_does_nothing(repos):
    app, me = repos
    sh(me, "git", "remote", "set-url", "origin", app)
    before = head(me)
    rc, out = run(me, app)
    assert rc == 0 and "the app itself" in out and head(me) == before


def test_an_unreachable_app_is_exit_two(repos, tmp_path):
    _, me = repos
    rc, out = run(me, str(tmp_path / "nowhere"))
    assert rc == 2 and "could not be reached" in out


def test_adopt_records_the_history_without_changing_a_file(tmp_path):
    # The repo the app was built from: its app-owned files are the app's exactly.
    me = str(tmp_path / "me")
    os.makedirs(me)
    sh(me, "git", "init", "-q", "-b", "master")
    sh(me, "git", "remote", "add", "origin", "https://github.com/someone/private")
    for tool in ("sync_app.py", "personal_paths.py"):
        write(me, f"tools/{tool}", read(ROOT, f"tools/{tool}"))
    write(me, ".gitignore", "__pycache__/\n")
    write(me, "README.md", "v1\n")
    write(me, "profile/person.json", "{}\n")
    commit(me, "years of history")
    app = str(tmp_path / "app")
    shutil.copytree(me, app, ignore=shutil.ignore_patterns(".git", "profile"))
    sh(app, "git", "init", "-q", "-b", "master")
    commit(app, "app tree")

    tree = sh(me, "git", "rev-parse", "HEAD^{tree}")
    rc, out = run(me, app, "--adopt")
    assert rc == 0, out
    assert sh(me, "git", "rev-parse", "HEAD^{tree}") == tree
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    rc, out = run(me, app)
    assert rc == 0 and read(me, "README.md") == "v2\n" and "1 new commit" in out


def test_adopt_refuses_when_a_file_differs(repos):
    app, me = repos
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    before = head(me)
    rc, out = run(me, app, "--adopt")
    assert rc == 1 and "README.md" in out and head(me) == before


def test_a_shallow_clone_finds_its_last_sync_instead_of_starting_over(repos, tmp_path):
    """Cloud sessions clone shallow. A last sync below the clone's depth looks like
    no sync at all, and treating it as one would re-merge the whole app."""
    app, me = repos
    run(me, app)
    for i in range(5):
        write(me, f"documents/note{i}.md", f"{i}\n")
        commit(me, f"work {i}")
    origin = str(tmp_path / "origin.git")
    sh(str(tmp_path), "git", "clone", "-q", "--bare", me, origin)
    shallow = str(tmp_path / "shallow")
    sh(str(tmp_path), "git", "clone", "-q", "--depth", "1", "file://" + origin, shallow)
    assert sh(shallow, "git", "rev-parse", "--is-shallow-repository").strip() == "true"
    write(app, "tools/x.py", "a = 9\n")
    commit(app, "app v4")
    rc, out = run(shallow, app)
    assert rc == 0, out
    assert "1 new commit" in out and read(shallow, "tools/x.py") == "a = 9\n"


# Job portals: the app ships the ones that work anywhere, and every other one
# under .agents/skills/ is the person's, built by /add-portal in their own repo.

def _add_app_portal(app, name):
    pp = read(app, "tools/personal_paths.py")
    anchor = '    ".agents/skills/freehire-search/**",\n'
    assert anchor in pp
    write(app, "tools/personal_paths.py",
          pp.replace(anchor, anchor + f'    ".agents/skills/{name}/**",\n'))
    write(app, f".agents/skills/{name}/SKILL.md", "---\nname: x\n---\n")


def test_a_persons_own_portal_is_theirs_and_never_drift(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    write(me, ".agents/skills/localboard-search/SKILL.md", "---\nname: localboard-search\n---\n")
    commit(me, "/add-portal")
    rc, out = run(me, app, "--check")
    assert "localboard" not in out, out
    write(app, "tools/x.py", "a = 9\n")
    commit(app, "app v9")
    rc, out = run(me, app)
    assert rc == 0, out
    assert os.path.exists(os.path.join(me, ".agents/skills/localboard-search/SKILL.md"))


def test_a_portal_the_app_starts_shipping_reaches_a_repo_on_the_old_rules(repos):
    """The person's sync judges incoming paths by their own personal_paths, which
    does not list the new portal yet; the app's own list is what lets it in."""
    app, me = repos
    assert run(me, app)[0] == 0
    _add_app_portal(app, "worldboard-search")
    commit(app, "ship a portal that works anywhere")
    rc, out = run(me, app)
    assert rc == 0, out
    assert os.path.exists(os.path.join(me, ".agents/skills/worldboard-search/SKILL.md"))


def test_the_app_cannot_claim_anything_but_a_portal_that_way(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    pp = read(app, "tools/personal_paths.py")
    anchor = '    ".agents/skills/freehire-search/**",\n'
    write(app, "tools/personal_paths.py", pp.replace(anchor, anchor + '    "job_search_tracker.csv",\n'))
    write(app, "job_search_tracker.csv", "date,company\nleaked,row\n")
    commit(app, "broken app")
    before = head(me)
    rc, out = run(me, app)
    assert rc == 1 and "job_search_tracker.csv" in out
    assert head(me) == before


# Profile upgrades: the sync ends by listing what this repo still needs, from the
# registry the merge just brought in, whether it merged anything or not.

STUB = ('import sys\n'
        'if "--after-sync" in sys.argv or len(sys.argv) == 1:\n'
        '    print("Profile upgrades pending (1):\\n  boards  run: /setup --section boards")\n')


def test_the_sync_lists_pending_upgrades_after_merging_and_when_up_to_date(repos):
    app, me = repos
    write(app, "tools/profile_upgrades.py", STUB)
    commit(app, "app ships the registry")
    rc, out = run(me, app)
    assert rc == 0 and "Profile upgrades pending (1)" in out, out
    rc, out = run(me, app)
    assert rc == 0 and "up to date" in out and "Profile upgrades pending (1)" in out, out
    rc, out = run(me, app, "--check")
    assert rc == 0 and "Profile upgrades pending (1)" in out, out


def test_a_broken_registry_never_changes_the_syncs_answer(repos):
    app, me = repos
    write(app, "tools/profile_upgrades.py", "raise SystemExit(3)\n")
    commit(app, "a broken registry")
    rc, out = run(me, app)
    assert rc == 0 and "profile upgrades: the check exited 3" in out, out


# ------------------------------------------------------- a chat that runs for days

def _with_local_origin(me, tmp_path):
    """Point the person's origin at a local bare copy, so master can be fetched offline."""
    origin = str(tmp_path / "origin.git")
    sh(str(tmp_path), "git", "clone", "-q", "--bare", me, origin)
    sh(me, "git", "remote", "set-url", "origin", origin)
    return origin


def _stamp(me):
    p = os.path.join(me, ".git", "ljs-last-sync")
    return read(me, ".git/ljs-last-sync").strip() if os.path.exists(p) else ""


def test_if_stale_syncs_once_a_day_and_then_does_nothing(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0, out
    assert read(me, "README.md") == "v2\n"
    assert _stamp(me) != ""
    before = head(me)
    write(app, "README.md", "v3\n")
    commit(app, "app v3")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0 and "already checked today" in out
    assert head(me) == before and read(me, "README.md") == "v2\n"


def test_a_check_from_an_earlier_day_runs_again(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    assert run(me, app)[0] == 0
    write(me, ".git/ljs-last-sync", "2000-01-01\n")
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0, out
    assert read(me, "README.md") == "v2\n"
    assert _stamp(me) > "2000-01-01"


def test_if_stale_brings_in_master_first(repos, tmp_path):
    app, me = repos
    origin = _with_local_origin(me, tmp_path)
    other = str(tmp_path / "other-chat")
    sh(str(tmp_path), "git", "clone", "-q", origin, other)
    write(other, "job_search_tracker.csv", "date,company\n2026-10-15,Brindle & Hart Logistics\n")
    commit(other, "another chat applied somewhere")
    sh(other, "git", "push", "-q", "origin", "master")
    sh(me, "git", "switch", "-q", "-c", "claude/this-chat")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0, out
    assert "brought in master" in out
    assert "Brindle & Hart Logistics" in read(me, "job_search_tracker.csv")


def test_if_stale_with_uncommitted_work_stops_and_records_nothing(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    write(me, "job_search_tracker.csv", "date,company\nunsaved\n")
    rc, out = run(me, app, "--if-stale")
    assert rc == 1 and "Commit or stash" in out
    assert _stamp(me) == ""


def test_the_reminder_shows_only_when_todays_check_has_not_run(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    probe = [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'tools'); import sync_app; sync_app.nudge()"]
    env = dict(ENV, LJS_APP_URL=app)
    first = subprocess.run(probe, cwd=me, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    assert "has not been checked for updates today" in first.stderr
    assert run(me, app)[0] == 0
    after = subprocess.run(probe, cwd=me, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    assert after.stderr == ""
    sh(app, "git", "remote", "add", "origin", app)  # the app is the repo whose origin is the app
    in_app = subprocess.run(probe, cwd=app, env=dict(ENV, LJS_APP_URL=app),
                            text=True, encoding="utf-8", errors="replace", capture_output=True)
    assert in_app.stderr == ""


def test_a_changed_claude_md_tells_an_open_chat_to_read_it_again(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    write(app, "tools/x.py", "a = 2\n")
    commit(app, "code only")
    rc, out = run(me, app)
    assert rc == 0 and "read CLAUDE.md again" not in out
    write(app, "CLAUDE.md", "# Rules, v2\n")
    commit(app, "new rules")
    rc, out = run(me, app)
    assert rc == 0 and "CLAUDE.md changed" in out and "read CLAUDE.md again now" in out


def test_the_tools_a_day_without_a_search_starts_with_carry_the_reminder():
    # Someone who only networks, or only asks what they owe, never runs a round.
    for rel in ("tools/run_round.py", "tools/stage_picks.py", "tools/open_actions.py",
                "tools/followups.py", "tools/network/state.py"):
        assert "sync_app.nudge()" in read(ROOT, rel), rel


def test_stable_takes_releases_and_never_goes_backwards(repos):
    app, me = repos
    sh(app, "git", "tag", "v1.0.0")
    rc, out = run(me, app)  # first sync: master, whatever the channel
    assert rc == 0 and "first sync" in out
    write(app, "README.md", "v2, not released\n")
    commit(app, "after the release")
    rc, out = run(me, app)
    assert rc == 0 and "releases, newest v1.0.0" in out
    assert read(me, "README.md") == "v1\n"  # what is not released does not arrive
    sh(app, "git", "tag", "v1.1.0")
    sh(app, "git", "tag", "v1.0.9", "HEAD~1")  # an older version number, tagged later
    rc, out = run(me, app)
    assert rc == 0 and "newest v1.1.0" in out and read(me, "README.md") == "v2, not released\n"


def test_a_first_sync_newer_than_the_newest_release_is_never_put_back(repos):
    # A first sync takes master, newer than the release before it. The next sync follows
    # releases, and measured against that older release every file changed since read as
    # "edited here" and was put back: the person went back a version, told it was their edit.
    app, me = repos
    sh(app, "git", "tag", "v1.0.0")
    write(app, "README.md", "v2, after the release\n")
    commit(app, "after the release")
    rc, out = run(me, app)
    assert rc == 0 and "first sync" in out and read(me, "README.md") == "v2, after the release\n"
    rc, out = run(me, app)
    assert rc == 0 and "releases, newest v1.0.0" in out, out
    assert "put back" not in out and "up to date" in out, out
    assert read(me, "README.md") == "v2, after the release\n"
    rc, out = run(me, app, "--check")
    assert rc == 0 and "drift: 0 app-owned file(s)" in out, out
    write(me, "tools/x.py", "a = 'edited here'\n")
    commit(me, "an app file edited here")
    rc, out = run(me, app)
    assert rc == 0 and "put back (edited here): tools/x.py" in out, out
    assert read(me, "tools/x.py") == "a = 1\n" and read(me, "README.md") == "v2, after the release\n"


def test_master_for_the_maintainer_or_when_chosen(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    sh(app, "git", "tag", "v1.0.0")
    write(app, "README.md", "v2\n")
    commit(app, "unreleased")
    write(me, "profile/person.json", '{"app_channel": "master"}\n')
    commit(me, "choose master")
    rc, out = run(me, app)
    assert rc == 0 and "app's master" in out and read(me, "README.md") == "v2\n"
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app as s
    assert s._owner("https://github.com/Someone/my-job-search.git") == "someone"


def test_no_release_yet_means_master(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    write(app, "README.md", "v2\n")
    commit(app, "more")
    rc, out = run(me, app)
    assert rc == 0 and "no release yet" in out and read(me, "README.md") == "v2\n"


def test_a_release_names_every_change_not_its_first_lines():
    # A sync that brought a whole release printed the first 12 raw lines of new CHANGELOG
    # text: the first entry's opening, and nothing about the rest. Every entry is named.
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    lines = ["## [Unreleased]", "### Added",
             "- **Rounds read Kestrel Mutual's board.** It names", "  its source.",
             "- **A no is for now.** It is asked again", "  after 90 days.",
             "  reworded line inside an older entry",
             "- A plain entry with no headline"]
    assert sync_app.headlines(lines) == [
        "Rounds read Kestrel Mutual's board.", "A no is for now.",
        "A plain entry with no headline"]
    assert sync_app.headlines(["  only a reworded line"]) == ["  only a reworded line"]


def test_what_changed_is_said_whole_and_only_what_is_theirs():
    # A headline running onto a second line was printed cut, bold marks and all; and
    # everyone was told the maintainer's news and a tool's options, which their chat passed
    # on to them (2026-10-22).
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    lines = ["- **A contact named like one of the app's examples no longer blocks",
             "  merges** (the maintainer's own repo only). More text.",
             "- **`ats_boards.py --probe` reads the boards side by side**, as a round does.",
             "- **Nothing asks for your email.** The round is your alert."]
    assert sync_app.headlines(lines) == [
        "A contact named like one of the app's examples no longer blocks merges",
        "`ats_boards.py --probe` reads the boards side by side",
        "Nothing asks for your email."]
    assert sync_app.headlines(lines, maintainer=False) == ["Nothing asks for your email."]


def test_a_persons_own_test_the_update_broke_is_named(tmp_path, monkeypatch, capsys):
    # A person's copy of an old test asserted the old search shape for days after the app
    # changed it, and nothing said so until ci_local.sh failed on something else.
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    tests = tmp_path / "profile" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_mine.py").write_text("def test_old_shape():\n    assert 1 == 2\n\n"
                                        "def test_still_true():\n    assert True\n")
    monkeypatch.setattr(sync_app, "ROOT", str(tmp_path))
    sync_app.own_tests()
    out = capsys.readouterr().out
    assert out.startswith("Claude, not for the person: their own tests, 1 now fail after this update")
    assert "test_old_shape" in out and "test_still_true" not in out
    (tests / "test_mine.py").write_text("def test_still_true():\n    assert True\n")
    sync_app.own_tests()
    assert capsys.readouterr().out == ""


# ------------------------------------------- updates that wait for the person's own word
#
# Updates arrive by themselves for everyone: every test above. A person who would rather
# choose when sets "app_updates": "when_asked" in their own profile (the maintainer did, in
# their own repos, 2026-10-25). Then a plain run and --if-stale only look, and --update
# takes the update when they say so.

def _when_asked(me, **more):
    person = dict({"app_updates": "when_asked"}, **more)
    write(me, "profile/person.json", json.dumps(person) + "\n")
    commit(me, "updates wait for my word")


def _release(app, entry, readme):
    write(app, "README.md", readme)
    write(app, "CHANGELOG.md", read(app, "CHANGELOG.md") + f"- **{entry}**\n  More words.\n")
    commit(app, entry)


def test_by_default_a_plain_run_and_if_stale_take_the_update(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    assert run(me, app)[0] == 0
    _release(app, "Interview packs open with where the process stands", "v2\n")
    write(me, ".git/ljs-last-sync", "2000-01-01\n")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0 and read(me, "README.md") == "v2\n", out
    assert "What changed" in out and "An update is waiting" not in out


def test_when_asked_a_look_changes_nothing_and_says_a_waiting_version_once(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    _when_asked(me)
    before = head(me)
    _release(app, "Interview packs open with where the process stands", "v2\n")
    rc, out = run(me, app)
    assert rc == 0, out
    assert head(me) == before and read(me, "README.md") == "v1\n"
    assert sh(me, "git", "status", "--porcelain").strip() == ""
    line = ('An update is waiting: Interview packs open with where the process stands. '
            'Say "update" when you want it.')
    assert out.count(line) == 1, out
    assert "What changed" not in out
    # Never a command: the update is the person's word, and nothing printed asks for it.
    assert "--update" not in out and "python3" not in out, out
    rc, out = run(me, app, "--on", "a model", "--tools", "none")
    assert rc == 0 and "An update is waiting" not in out, out
    assert head(me) == before
    # A newer version is a new line, once.
    _release(app, "A reply to a recruiter names the role", "v3\n")
    rc, out = run(me, app)
    assert rc == 0 and out.count("An update is waiting") == 1, out
    assert "Interview packs open with where the process stands, and 1 more change." in out
    assert head(me) == before


def test_when_asked_if_stale_looks_once_a_day_and_never_takes_the_update(repos, tmp_path):
    app, me = repos
    _with_local_origin(me, tmp_path)
    assert run(me, app)[0] == 0
    _when_asked(me)
    sh(me, "git", "push", "-q", "origin", "master")
    write(me, ".git/ljs-last-sync", "2000-01-01\n")
    before = head(me)
    _release(app, "Interview packs open with where the process stands", "v2\n")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0, out
    assert head(me) == before and read(me, "README.md") == "v1\n"
    assert "An update is waiting" in out and _stamp(me) > "2000-01-01"
    _release(app, "A reply to a recruiter names the role", "v3\n")
    rc, out = run(me, app, "--if-stale")
    assert rc == 0 and "already checked today" in out and "An update is waiting" not in out
    assert head(me) == before and read(me, "README.md") == "v1\n"


def test_update_takes_it_with_what_changed_and_the_upgrades(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    _when_asked(me)
    write(app, "tools/profile_upgrades.py", STUB)
    _release(app, "Interview packs open with where the process stands", "v2\n")
    rc, out = run(me, app)
    assert rc == 0 and "An update is waiting" in out, out
    # Upgrades come with the version that brings them, never before it is taken.
    assert "Profile upgrades pending" not in out, out
    rc, out = run(me, app, "--update")
    assert rc == 0, out
    assert read(me, "README.md") == "v2\n"
    assert "What changed" in out and "Interview packs open with where the process stands" in out
    assert "Profile upgrades pending (1)" in out, out
    rc, out = run(me, app)
    assert rc == 0 and "up to date" in out and "An update is waiting" not in out, out
    # The version taken: its upgrades still apply themselves on every look.
    assert "Profile upgrades pending (1)" in out, out


def test_when_asked_a_look_reports_an_edited_app_file_and_puts_nothing_back(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    _when_asked(me)
    write(me, "tools/x.py", "a = 'edited here'\n")
    commit(me, "an app file edited here")
    rc, out = run(me, app)
    assert rc == 0 and "drift: 1 app-owned file(s) edited here" in out, out
    assert read(me, "tools/x.py") == "a = 'edited here'\n"
    rc, out = run(me, app, "--update")
    assert rc == 0 and "put back (edited here): tools/x.py" in out, out


def test_when_asked_on_the_apps_master_waits_for_their_word_too(repos):
    # The maintainer's own repo follows master and asked for this; the same rule holds there.
    app, me = repos
    assert run(me, app)[0] == 0
    _when_asked(me, app_channel="master")
    before = head(me)
    write(app, "README.md", "v2\n")
    commit(app, "unreleased")
    rc, out = run(me, app)
    assert rc == 0 and "app's master" in out and "An update is waiting" in out, out
    assert head(me) == before and read(me, "README.md") == "v1\n"


def test_when_asked_the_tools_remind_nobody_to_check(repos, tmp_path):
    app, me = repos
    _when_asked(me)
    probe = [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'tools'); import sync_app; sync_app.nudge()"]
    r = subprocess.run(probe, cwd=me, env=dict(ENV, LJS_APP_URL=app), text=True, encoding="utf-8", errors="replace",
                       capture_output=True)
    assert r.stderr == ""


def test_the_setting_is_the_persons_never_the_apps():
    for rel in ("profile.example/person.json",):
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            assert "app_updates" not in read(ROOT, rel), rel


def test_a_merge_git_refuses_stops_and_keeps_their_unsaved_file(repos):
    """The app adds a file where the person has one not saved yet (a portal built and not
    committed, under a name the app later ships). Git refuses the merge; the sync used to
    carry on regardless, put the app's file over theirs and commit a one-parent commit that
    recorded no merge, so the next sync brought the same commit again."""
    app, me = repos
    assert run(me, app)[0] == 0
    write(app, "tools/newthing.py", 'print("the app version")\n')
    commit(app, "app adds newthing")
    write(me, "tools/newthing.py", "MY OWN UNSAVED WORK\n")
    before = head(me)
    rc, out = run(me, app)
    assert rc == 1, out
    assert "stopped, nothing changed" in out
    assert "tools/newthing.py" in out
    assert read(me, "tools/newthing.py") == "MY OWN UNSAVED WORK\n"
    assert head(me) == before
    assert sh(me, "git", "status", "--porcelain") == "?? tools/newthing.py\n"
    # Once it is moved out of the way, the update is a real merge.
    os.remove(os.path.join(me, "tools", "newthing.py"))
    rc, out = run(me, app)
    assert rc == 0, out
    assert len(sh(me, "git", "log", "-1", "--format=%P").split()) == 2


def test_the_days_check_is_kept_by_one_clock_whoever_writes_it():
    """In a cloud chat person.py sets the person's own zone, so the stamp written last (by
    profile_upgrades.py --after-sync) was their date, and sync_app's own --if-stale compared
    it with the cloud computer's UTC date: east of UTC the next morning's check was skipped,
    west of it every evening ran the whole sync again (found 2026-10-25). The stamp now
    carries the offset it was written in, and is read back by that same clock."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import datetime as dt
    import sync_app
    sydney, toronto, utc = (dt.timezone(dt.timedelta(hours=h)) for h in (11, -4, 0))
    # East: written at 05:05 on 26 Oct in Sydney (18:05 UTC on the 25th).
    line = sync_app._day_line(dt.datetime(2026, 10, 26, 5, 5, tzinfo=sydney))
    assert line.split()[0] == "2026-10-26"
    # 09:00 on 27 Oct in Sydney is still 26 Oct in UTC: the person's new day, so it runs.
    assert sync_app._stale_day(line, dt.datetime(2026, 10, 26, 22, 0, tzinfo=utc))
    # Later the same Sydney day it does not.
    assert not sync_app._stale_day(line, dt.datetime(2026, 10, 26, 6, 0, tzinfo=utc))
    # West: written at 21:00 on 25 Oct in Toronto (01:00 UTC on the 26th); an hour later
    # it is still their 25th, so nothing runs again.
    line = sync_app._day_line(dt.datetime(2026, 10, 25, 21, 0, tzinfo=toronto))
    assert not sync_app._stale_day(line, dt.datetime(2026, 10, 26, 2, 0, tzinfo=utc))
    assert sync_app._stale_day(line, dt.datetime(2026, 10, 26, 13, 0, tzinfo=utc))
    # A stamp from before this change (a date alone) is read in this computer's own day.
    assert sync_app._stale_day("2000-01-01", None)
    assert not sync_app._stale_day(dt.date.today().isoformat(), None)
    assert sync_app._stale_day("", None)
