"""tools/person.py: every fact about the candidate comes through one loader.

The rule that matters most is the negative one. With no profile, a tool must
stop and say "run /setup". It must never fall back to the example person,
because a stranger who skipped /setup would then send out a resume under a
fictional name, or have the example's market rules cut their search.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    d = tmp_path / "someone"
    d.mkdir()
    (d / "person.json").write_text(json.dumps(
        {"identity": {"name": "Sam Example", "email": "sam@example.com"}}), encoding="utf-8")
    (d / "bullets.py").write_text("LIB = {'Acme': {'ACME_1': 'Did a thing'}}\n", encoding="utf-8")
    (d / "notes.md").write_text("# Notes\n", encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(d))
    person.reset()
    yield d
    person.reset()


def test_a_missing_profile_says_run_setup(tmp_path, monkeypatch):
    monkeypatch.setenv(person.ENV, str(tmp_path / "nobody"))
    person.reset()
    with pytest.raises(person.NoProfile, match="run /setup"):
        person.directory()
    assert person.exists() is False


def test_there_is_no_fallback_to_the_example_person(tmp_path, monkeypatch):
    # Even with profile.example/ sitting in the repo, a missing profile raises.
    monkeypatch.setenv(person.ENV, str(tmp_path / "nobody"))
    person.reset()
    with pytest.raises(person.NoProfile):
        person.get("identity.name")
    with pytest.raises(person.NoProfile):
        person.module("bullets")


def test_the_default_is_profile_at_the_repo_root(monkeypatch):
    monkeypatch.delenv(person.ENV, raising=False)
    person.reset()
    if os.path.isdir(os.path.join(ROOT, "profile")):
        assert person.directory() == os.path.join(ROOT, "profile")
    else:
        with pytest.raises(person.NoProfile, match="run /setup"):
            person.directory()


def test_a_relative_env_path_is_relative_to_the_repo(monkeypatch):
    monkeypatch.setenv(person.ENV, "no-such-dir-here")
    person.reset()
    with pytest.raises(person.NoProfile) as e:
        person.directory()
    assert os.path.join(ROOT, "no-such-dir-here") in str(e.value)


def test_modules_load_by_path_not_as_a_package(profile_dir):
    mod = person.module("bullets")
    assert mod.LIB["Acme"]["ACME_1"] == "Did a thing"
    # `profile` is the stdlib profiler; loading by path must not shadow it.
    import profile as stdlib_profile
    assert hasattr(stdlib_profile, "Profile")
    assert person.module("bullets") is mod  # cached


def test_json_text_and_dotted_values(profile_dir):
    assert person.data("person")["identity"]["name"] == "Sam Example"
    assert person.get("identity.email") == "sam@example.com"
    assert person.get("identity.phone", None) is None
    with pytest.raises(KeyError):
        person.get("identity.phone")
    assert person.text("notes.md").startswith("# Notes")


def test_a_missing_file_in_a_present_profile_names_the_file(profile_dir):
    with pytest.raises(person.NoProfile, match="roles.py"):
        person.module("roles")


def test_the_cli_serves_shell_scripts(profile_dir):
    env = dict(os.environ, **{person.ENV: str(profile_dir)})
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "person.py"),
                          "get", "identity.email"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert out.returncode == 0 and out.stdout.strip() == "sam@example.com"
    env[person.ENV] = str(profile_dir / "gone")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "person.py"), "dir"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert out.returncode == 1 and "run /setup" in out.stderr


def test_state_lives_at_the_repo_root_unless_moved(tmp_path, monkeypatch):
    monkeypatch.delenv(person.STATE_ENV, raising=False)
    assert person.state("job_search_tracker.csv") == os.path.join(ROOT, "job_search_tracker.csv")
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path))
    assert person.state("network_contacts.csv") == str(tmp_path / "network_contacts.csv")
