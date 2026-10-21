"""tools/personal_paths.py: the one line between a person's files and the app's.

The app builder, the app's CI guard and the sync tool all read it, so a path
it gets wrong is either published (a personal file called app-owned) or
overwritten by every sync (an app file called personal).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from personal_paths import is_personal, split  # noqa: E402


def test_state_files_are_personal():
    for p in ("job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
              "job_scraper/seen_jobs.json", "job_scraper/do_not_target.json",
              "company_research/acme.json", "upskill/report-2026.md"):
        assert is_personal(p), p


def test_the_profile_and_everything_under_it_is_personal():
    for p in ("profile/person.json", "profile/tests/test_x.py", "profile/a/b/c.md"):
        assert is_personal(p), p


def test_rendered_documents_are_personal_whatever_the_name():
    for p in ("cv/Sam_Example_Resume_ACME.tex", "cv/Sam_Example_Resume_ACME.pdf",
              "cv/Sam_Example_CV_ACME.pdf", "cv/anything_at_all.tex",
              "cover_letters/Sam_Example_Cover_Letter_ACME.tex"):
        assert is_personal(p), p


def test_documents_are_personal_but_their_scaffolding_ships():
    assert is_personal("documents/applications/acme/draft.json")
    assert is_personal("documents/briefs/2026-01-01.md")
    assert not is_personal("documents/README.md")
    assert not is_personal("documents/cv/.gitkeep")


def test_app_files_are_not_personal():
    for p in ("tools/person.py", "templates/resume_gen.py", "cv/main_example.tex",
              "cover_letters/cover.cls", "cover_letters/cover_example.tex",
              "profile.example/person.json", "CLAUDE.md", "tests/test_x.py",
              "company_research/.gitkeep", "job_scraper/.gitkeep"):
        assert not is_personal(p), p


def test_a_star_stays_inside_one_segment():
    # "company_research/*.json" must not reach into a subdirectory.
    assert is_personal("company_research/acme.json")
    assert not is_personal("company_research/schema/acme.json")
    assert not is_personal("cvx/a_Resume_b")


def test_the_document_folders_ship_only_the_apps_own_files():
    for p in ("cv/main_example.tex", "cover_letters/cover.cls",
              "cover_letters/cover_example.tex",
              "cover_letters/OpenFonts/fonts/raleway/Raleway-Medium.ttf"):
        assert not is_personal(p), p


def test_split_keeps_order_and_partitions():
    app, mine = split(["tools/a.py", "network_contacts.csv", "README.md"])
    assert app == ["tools/a.py", "README.md"] and mine == ["network_contacts.csv"]


def _git(cwd, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                           "user.email=t@example.com", *args], capture_output=True, text=True)


def test_local_checks_go_light_only_when_every_change_is_the_persons_own(tmp_path):
    """From a person's repo on 2026-10-21: `ci_local.sh --quick` took 2.5 minutes, twice, for
    changes to the contact book alone. It now skips the app's own suites when every change
    since master is theirs, and runs everything when anything of the app changed, or nothing."""
    import subprocess
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(repo))
    (repo / "tools").mkdir()
    (repo / "tools" / "run_round.py").write_text("x = 1\n")
    (repo / "network_contacts.csv").write_text("id\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "push", "-q", "origin", "HEAD:master")
    _git(repo, "fetch", "-q", "origin")

    def light():
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "personal_paths.py"),
                            "--only-personal-changed"], capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                           cwd=str(repo))
        return r.returncode == 0, r.stdout.split()

    import personal_paths
    assert personal_paths.changed(str(repo)) == []
    (repo / "network_contacts.csv").write_text("id\nc1\n")              # their contact book
    (repo / "documents").mkdir()
    (repo / "documents" / "note.md").write_text("new\n")                # untracked, theirs
    assert personal_paths.changed(str(repo)) == ["documents/note.md", "network_contacts.csv"]
    _git(repo, "commit", "-qam", "a contact")                            # committed counts too
    assert personal_paths.changed(str(repo)) == ["documents/note.md", "network_contacts.csv"]
    (repo / "tools" / "run_round.py").write_text("x = 2\n")             # and now the app's
    assert sorted(personal_paths.split(personal_paths.changed(str(repo)))[0]) == \
        ["tools/run_round.py"]
    assert personal_paths.changed(str(repo), base="origin/no-such") is None


def test_the_light_check_is_asked_of_the_repo_it_runs_in(tmp_path):
    """The flag reads the checkout ci_local.sh runs in: exit 0 for theirs alone, 1 for any
    app file, and 1 for no change at all (a check of master itself checks everything)."""
    import shutil
    import subprocess
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(repo))
    shutil.copytree(os.path.join(ROOT, "tools"), repo / "tools",
                    ignore=shutil.ignore_patterns("__pycache__", "openroles"))
    (repo / "network_contacts.csv").write_text("id\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "push", "-q", "origin", "HEAD:master")
    _git(repo, "fetch", "-q", "origin")

    def flag():
        return subprocess.run([sys.executable, "tools/personal_paths.py",
                               "--only-personal-changed"], capture_output=True, text=True,
                              cwd=str(repo), env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert flag().returncode == 1                                         # nothing changed
    (repo / "network_contacts.csv").write_text("id\nc1\n")
    got = flag()
    assert got.returncode == 0 and got.stdout.split() == ["network_contacts.csv"]
    (repo / "tools" / "bar.py").write_text("# changed\n")
    assert flag().returncode == 1
