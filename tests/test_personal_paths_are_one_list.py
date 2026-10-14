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
