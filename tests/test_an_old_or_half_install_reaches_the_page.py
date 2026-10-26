"""An install on an old release, or half made, reaches the page with nothing of theirs lost.

A rehearsal on throwaway copies. The stand-in for the app on GitHub is this tree as it
stands; the person's copy is the app at an old release, made the way "Use this template"
makes one, with the example person's profile and state in it. The copy's own (old)
tools/sync_app.py takes the update, exactly as a chat whose CLAUDE.md predates the page
would run it; then `app.py start` must lead to the page, and every file of the person's must
be byte for byte what it was, except what an upgrade's own commit is meant to change.

Half-made copies go the same way: app files and no profile, a profile without person.json,
a setup marked started in another chat that has stopped. Nothing here touches the network:
the app is a local folder (LJS_APP_URL), the copy's GitHub a bare repository on disk, and
LJS_COPY says the copy is private, as GitHub would.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import personal_paths  # noqa: E402
import repo_files  # noqa: E402

# The oldest release a copy can still be on, one from the middle, and the newest.
RELEASES = ("v3.1.0", "v3.6.0", "v3.13.0")
CANDIDATE = "v999.0.0"
IDENTITY = {"GIT_AUTHOR_NAME": "rehearsal", "GIT_AUTHOR_EMAIL": "rehearsal@example.com",
            "GIT_COMMITTER_NAME": "rehearsal", "GIT_COMMITTER_EMAIL": "rehearsal@example.com"}
# What an upgrade or the sync commits on the person's files, on purpose: an upgrade, the
# sync's line-ending fix (no row changed), and the place check noting a chat it saw.
OWN_COMMITS = ("Profile upgrade:", "State files: plain line endings", "Place:")


def git(cwd, *args, env=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, encoding="utf-8",
                       errors="replace", env=dict(os.environ, **IDENTITY, **(env or {})))
    if check and r.returncode:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def _have_releases() -> bool:
    return all(git(ROOT, "rev-parse", "--verify", "-q", t + "^{commit}", check=False).strip()
               for t in RELEASES)


pytestmark = pytest.mark.skipif(not _have_releases(),
                                reason="this checkout has no release tags to start from")


def stand_in_app(tmp) -> tuple[str, str]:
    """The app as this tree stands, committed in a repository of its own, tagged as the
    newest release so a copy that follows releases takes it too. It sits under an owner of
    its own, as on GitHub, so the copy is not mistaken for the maintainer's."""
    app = os.path.join(tmp, "app-owner", "last-job-search")
    for rel in sorted(set(repo_files.tracked(root=ROOT, new=True))):
        src = os.path.join(ROOT, rel)
        if not os.path.isfile(src) or personal_paths.is_personal(rel):
            continue
        dst = os.path.join(app, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    git(app, "init", "-q", "-b", "master")
    git(app, "add", "-A", "-f")      # tracked files the app's own ignore rules cover, too
    git(app, "commit", "-q", "-m", "app candidate")
    git(app, "tag", CANDIDATE)
    return app, git(app, "rev-parse", "HEAD").strip()


def _extract(tag: str, dest: str) -> None:
    data = subprocess.run(["git", "archive", "--format=tar", tag], cwd=ROOT,
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        # Our own `git archive`; the safe filter where this Python has it (3.9.17 and on).
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def persons_copy(tmp, name: str, tag: str | None, profile: str = "example",
                 tree: str = "") -> str:
    """The person's copy, as "Use this template" makes it: the app's files at `tag` (or the
    files of `tree`) in a fresh history, then their profile and state on top, pushed to a
    bare repository standing in for their private copy on GitHub."""
    me = os.path.join(tmp, name)
    os.makedirs(me)
    if tag:
        _extract(tag, me)
    else:
        for rel in repo_files.tracked(root=tree, app_only=False):
            os.makedirs(os.path.dirname(os.path.join(me, rel)), exist_ok=True)
            shutil.copy2(os.path.join(tree, rel), os.path.join(me, rel))
    origin = os.path.join(tmp, "the-person", name + ".git")
    os.makedirs(os.path.dirname(origin), exist_ok=True)
    git(tmp, "init", "-q", "--bare", "-b", "master", origin)
    git(me, "init", "-q", "-b", "master")
    git(me, "remote", "add", "origin", origin)
    git(me, "add", "-A", "-f")       # every file the template holds, as GitHub copies it
    git(me, "commit", "-q", "-m", "Initial commit")
    if profile == "example":
        shutil.copytree(os.path.join(me, "profile.example"), os.path.join(me, "profile"),
                        ignore=shutil.ignore_patterns("state", "tests"))
        state = os.path.join(me, "profile.example", "state")
        for dp, _dn, fns in os.walk(state):
            for f in fns:
                if f == "README.md":
                    continue
                rel = os.path.relpath(os.path.join(dp, f), state)
                os.makedirs(os.path.dirname(os.path.join(me, rel)) or me, exist_ok=True)
                shutil.copy2(os.path.join(dp, f), os.path.join(me, rel))
        git(me, "add", "-A")
        git(me, "add", "-f", "job_search_tracker.csv", "network_contacts.csv",
            "network_threads.csv", "job_scraper")
        git(me, "commit", "-q", "-m", "set me up")
    git(me, "push", "-q", "origin", "master")
    return me


def env_for(tmp, app) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("LJS_PROFILE", "LJS_STATE", "CLAUDE_CODE_REMOTE", "LJS_TODAY",
                        "GIT_DIR", "GIT_WORK_TREE")}
    home = os.path.join(tmp, "home")
    os.makedirs(home, exist_ok=True)
    env.update(IDENTITY, LJS_APP_URL=app, HOME=home, LJS_COPY="private",
               PYTHONDONTWRITEBYTECODE="1", GIT_TERMINAL_PROMPT="0")
    return env


def run(me, env, *args, timeout=600):
    r = subprocess.run([sys.executable, *args], cwd=me, env=env, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def theirs(me) -> dict:
    """{repo path: sha256} for every file of the person's in the copy."""
    out = {}
    for rel in repo_files.tracked(root=me, app_only=False):
        if personal_paths.is_personal(rel) and os.path.isfile(os.path.join(me, rel)):
            with open(os.path.join(me, rel), "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


def meant_to_change(me, since: str) -> set:
    """The person's files an upgrade or the sync changed on purpose, in commits of their own."""
    out = set()
    log = git(me, "log", "--format=%x1e%H%x1f%s", "--name-only", f"{since}..HEAD")
    for rec in log.split("\x1e"):
        head, _, names = rec.partition("\n")
        if "\x1f" in head and head.split("\x1f", 1)[1].startswith(OWN_COMMITS):
            out.update(n for n in names.split("\n") if n)
    return out


@pytest.mark.parametrize("tag", RELEASES)
def test_an_install_on_an_old_release_takes_the_update_and_reaches_the_page(tmp_path, tag):
    tmp = str(tmp_path)
    app, app_sha = stand_in_app(tmp)
    me = persons_copy(tmp, "me", tag)
    env = env_for(tmp, app)
    start = git(me, "rev-parse", "HEAD").strip()
    before = theirs(me)
    assert before, "the copy holds the person's files"

    # The chat runs its own, old copy of the sync, as its old instructions say.
    code, said = run(me, env, "tools/sync_app.py")
    said_sync = said
    assert code == 0, said
    assert subprocess.run(["git", "merge-base", "--is-ancestor", app_sha, "HEAD"],
                          cwd=me).returncode == 0, "the update is in the copy's history"
    assert git(me, "status", "--porcelain") == "", "the sync left nothing uncommitted"
    # The new post-sync list, run by the old sync, tells the chat about the page.
    assert "python3 tools/app.py start" in said, said[-2000:]

    code, said = run(me, env, "tools/app.py", "start", "--on", "rehearsal", "--tools", "none")
    assert code == 0, said
    assert said.startswith("app start: set up"), said
    assert "python3 tools/app.py page --out" in said and "published <the url" in said
    code, said = run(me, env, "tools/app.py", "check")
    assert code == 0, said

    # Nothing of theirs lost or changed, but what an upgrade's own commit is meant to change.
    after = theirs(me)
    meant = meant_to_change(me, start)
    lost = sorted(set(before) - set(after))
    changed = sorted(p for p in before if p in after and before[p] != after[p] and p not in meant)
    assert not lost, lost
    assert not changed, changed
    if "profile/place.json" in meant:          # the place check adds what it saw, never removes
        with open(os.path.join(me, "profile", "place.json"), encoding="utf-8") as fh:
            now = json.load(fh)
        old = json.loads(git(me, "show", f"{start}:profile/place.json"))
        assert all(now.get(k) == v for k, v in old.items()), (old, now)
    assert "APP LEAK" not in said_sync, "a person's copy is never taken for the maintainer's"

    # Published: the next start and the next sync say nothing more about it.
    code, said = run(me, env, "tools/app.py", "published",
                     "https://claude.ai/code/artifact/rehearsal-page")
    assert code == 0, said
    code, said = run(me, env, "tools/app.py", "start", "--on", "rehearsal", "--tools", "none")
    assert code == 0 and "app.py page --out" not in said, said
    code, said = run(me, env, "tools/profile_upgrades.py")
    assert "app.py start" not in said, said


def _current_copy(tmp_path, name, profile):
    tmp = str(tmp_path)
    app, _ = stand_in_app(tmp)
    me = persons_copy(tmp, name, None, profile=profile, tree=app)
    return me, env_for(tmp, app)


def _model(me, env) -> dict:
    code, out = run(me, env, "tools/app.py", "model")
    assert code == 0, out
    return json.loads(out)


def test_a_copy_with_the_apps_files_and_no_profile_starts_setup_on_the_page(tmp_path):
    me, env = _current_copy(tmp_path, "fresh", profile="")
    assert not os.path.exists(os.path.join(me, "profile"))
    m = _model(me, env)
    assert m["setup"]["state"] == "none" and m["setup"]["next"] == "resume"
    code, said = run(me, env, "tools/app.py", "start", "--on", "rehearsal", "--tools", "none")
    assert code == 0 and said.startswith("app start: setting up"), said
    assert not os.path.exists(os.path.join(me, "profile")), "start writes nothing of theirs"


def test_a_profile_without_person_json_carries_on_from_what_is_written(tmp_path):
    me, env = _current_copy(tmp_path, "partial", profile="")
    os.makedirs(os.path.join(me, "profile"))
    with open(os.path.join(me, "profile", "01-candidate-profile.md"), "w", encoding="utf-8") as fh:
        fh.write("# Candidate profile\n\n### Analyst - Fernhill Freight (2021 to now), Leeds\n")
    m = _model(me, env)
    assert m["setup"]["state"] == "partial"
    code, said = run(me, env, "tools/app.py", "start", "--on", "rehearsal", "--tools", "none")
    assert code == 0 and "Setup carries on from where it is" in said, said


def test_a_setup_another_chat_started_and_left_is_carried_on(tmp_path):
    me, env = _current_copy(tmp_path, "stopped", profile="example")
    with open(os.path.join(me, "profile", "place.json"), encoding="utf-8") as fh:
        place = json.load(fh)
    place["setup"] = {"started": "2026-10-20", "chat": "another-chat"}
    with open(os.path.join(me, "profile", "place.json"), "w", encoding="utf-8") as fh:
        json.dump(place, fh, indent=2)
    git(me, "add", "-A")
    git(me, "commit", "-q", "-m", "setup part-way", env={"GIT_COMMITTER_DATE": "2026-10-20T10:00:00",
                                                        "GIT_AUTHOR_DATE": "2026-10-20T10:00:00"})
    m = _model(me, env)
    assert m["setup"]["state"] == "stopped"
    code, said = run(me, env, "tools/app.py", "start", "--on", "rehearsal", "--tools", "none")
    assert code == 0 and said.startswith("app start: setup stopped"), said
    assert "Setup carries on" in said and "Start nothing" not in said
