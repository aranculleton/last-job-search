#!/usr/bin/env python3
"""Rehearse an update on copies of a person's repo, the way their chats will take it.

    python3 tools/rehearse_sync.py <their repo> [--ref origin/master] [--app HEAD]
                                   [--no-ci] [--keep]

Every update so far reached a person's chats and came straight back with bugs: a sync
that stopped on something, an upgrade that crashed, an everyday command that no longer
ran, two chats that took the same update and collided. This plays it all out first, on
throwaway copies, with nothing sent anywhere and nothing in either repository changed:

1. A copy of the app at `--app` stands in for the app on GitHub, with that commit as its
   newest release, so a repo on releases and one on master both take it.
2. A copy of their repo at `--ref` stands in for their GitHub repo.
3. A cloud chat: a fresh clone syncs with its own copy of tools/sync_app.py (the one they
   have now), exactly as a chat starts. Where their profile says updates wait for their word
   (`"app_updates": "when_asked"`), that first run is a look that must take nothing and say
   the waiting update once, and `--update` then takes it, as when they say "update".
4. A chat on their computer: another clone makes its own folder (`--worktree`) and does
   the same there, at the same time, from the same starting point.
5. Each chat then runs the everyday commands (the due list, the contact book, the call
   preps, the interview packs, the upgrades plan, their own tests, and the local CI unless
   `--no-ci`), and a crash or an unexpected exit code fails the rehearsal.
6. The cloud chat lands its work first; the computer chat then takes master, as its next
   sync would, and the merge must go through with no conflict.

Exit 0 when every step passed, 1 when something failed (each named, with its output),
2 when the copies could not be made.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The release tag the candidate is given in the stand-in app: newer than any real one.
CANDIDATE_TAG = "v999.0.0"
# What a crash looks like in a command's output, whatever its exit code.
_CRASH = re.compile(r"^Traceback \(most recent call last\):|^\w*Error: |^KeyError|"
                    r"^panicked at ", re.M)


def _run(cmd, cwd, env=None, timeout=1800):
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
               else (e.stdout or "")) + "\n[timed out]"
        code = -1
    return code, out, time.time() - t


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


class Rehearsal:
    def __init__(self):
        self.steps = []          # (chat, step, ok, seconds, tail of output)

    def check(self, chat, step, cmd, cwd, env, ok_codes=(0,), timeout=1800):
        code, out, secs = _run(cmd, cwd, env, timeout)
        crashed = bool(_CRASH.search(out))
        ok = code in ok_codes and not crashed
        why = "" if ok else ("crashed" if crashed else f"exit {code}")
        self.steps.append((chat, step, ok, secs, why, out))
        return ok, out

    def note(self, chat, step, ok, out="", why=""):
        self.steps.append((chat, step, ok, 0.0, why, out))

    def report(self) -> str:
        lines = []
        failed = [s for s in self.steps if not s[2]]
        for chat, step, ok, secs, why, _out in self.steps:
            lines.append(f"  {'PASS' if ok else 'FAIL'}  {chat:<9} {step:<44} {secs:6.1f}s"
                         + (f"  ({why})" if why else ""))
        for chat, step, _ok, _secs, why, out in failed:
            tail = "\n".join(out.strip().splitlines()[-25:])
            lines.append(f"\n--- {chat}: {step} ({why})\n{tail}")
        head = (f"Rehearsal: {len(self.steps) - len(failed)} passed, {len(failed)} failed"
                + (": the update is safe to send." if not failed else
                   ". Fix these before the update reaches anyone."))
        return "\n".join([head] + lines)


def _env(cloud: bool, app_url: str, home: str) -> dict:
    env = dict(os.environ)
    for k in ("LJS_PROFILE", "LJS_STATE", "CLAUDE_CODE_REMOTE", "GIT_DIR", "GIT_WORK_TREE"):
        env.pop(k, None)
    env.update(LJS_APP_URL=app_url, PYTHONDONTWRITEBYTECODE="1", HOME=home,
               GIT_TERMINAL_PROMPT="0", GIT_AUTHOR_NAME="rehearsal",
               GIT_AUTHOR_EMAIL="rehearsal@example.com", GIT_COMMITTER_NAME="rehearsal",
               GIT_COMMITTER_EMAIL="rehearsal@example.com")
    if cloud:
        env["CLAUDE_CODE_REMOTE"] = "true"
    return env


def _live_interviews(root: str) -> list[tuple[str, str]]:
    path = os.path.join(root, "job_search_tracker.csv")
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return [(r.get("company", ""), r.get("role", "")) for r in csv.DictReader(fh)
                    if str(r.get("status", "")).strip().lower() == "interview"
                    and r.get("company")][:6]
    except OSError:
        return []


def everyday(reh: Rehearsal, chat: str, root: str, env: dict, ci: bool) -> None:
    """The commands a person's chats run on an ordinary day, after the update."""
    py = sys.executable
    reh.check(chat, "upgrades plan", [py, "tools/profile_upgrades.py", "--plan"], root, env,
              ok_codes=(0,))
    reh.check(chat, "what is due today", [py, "tools/open_actions.py", "--due"], root, env)
    reh.check(chat, "contact book and what is owed", [py, "tools/network/state.py"], root, env)
    reh.check(chat, "application follow-ups", [py, "tools/followups.py"], root, env)
    reh.check(chat, "scheduled tasks registry", [py, "tools/routines.py", "check"], root, env,
              ok_codes=(0, 1))
    reh.check(chat, "portals the next round searches", [py, "tools/portals.py"], root, env)
    reh.check(chat, "places told to employers", [py, "tools/told.py"], root, env)
    reh.check(chat, "profile consistency", [py, "tools/profile_consistency.py"], root, env,
              ok_codes=(0, 1))
    reh.check(chat, "what works (search)", [py, "tools/what_works.py", "brief", "search"],
              root, env)
    reh.check(chat, "learned rules (messages)", [py, "tools/learned.py", "brief", "messages"],
              root, env)
    reh.check(chat, "reading limits", [py, "tools/network/reading.py", "limits"], root, env)
    reh.check(chat, "call preps a release rebuilds",
              [py, "tools/network/prep.py", "--stale-only", "--dry-run"], root, env)
    for company, role in _live_interviews(root):
        reh.check(chat, f"interview pack: {company[:24]}",
                  [py, "tools/interview_pack.py", "pack", company, "--role", role], root, env)
        reh.check(chat, f"interview check: {company[:23]}",
                  [py, "tools/interview_pack.py", "check", company, "--role", role], root, env,
                  ok_codes=(0, 1))
    if os.path.isdir(os.path.join(root, "profile", "tests")):
        reh.check(chat, "their own tests", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                            "profile/tests"], root, env, ok_codes=(0, 5))
    if ci:
        reh.check(chat, "local CI (quick)", ["./tools/ci_local.sh", "--quick"], root, env,
                  timeout=3600)
    status = _git("status", "--porcelain", cwd=root).stdout.strip()
    reh.note(chat, "the everyday commands left no stray files", not status, status,
             "" if not status else "files changed or left behind")


def _waits(root: str) -> bool:
    """Does this copy wait for the person's word to update: their profile asks for it, and
    their copy of the sync knows how (an older one has no --update)?"""
    import json
    try:
        with open(os.path.join(root, "tools", "sync_app.py"), encoding="utf-8") as fh:
            knows = '"--update"' in fh.read()
        with open(os.path.join(root, "profile", "person.json"), encoding="utf-8") as fh:
            chosen = str(json.load(fh).get("app_updates") or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return False
    return knows and chosen == "when_asked"


def take_update(reh: Rehearsal, chat: str, root: str, env: dict, sha: str) -> None:
    """The update, as a chat takes it. By default the plain run takes it. Where the person
    asked to choose when, the plain run is a look, as every session starts: it must take
    none of the update and say it is waiting once, a second look says nothing more, and
    `--update` takes it, as when they say "update"."""
    py = sys.executable
    base = [py, "tools/sync_app.py", "--on", "rehearsal", "--tools", "none"]
    asks = _waits(root)
    if asks:
        ok, out = reh.check(chat, "look at the app", base, root, env)
        # A look may save the person's own records (the place check notes a new computer);
        # what it must never do is bring the app's update in.
        took = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=root).returncode == 0
        reh.note(chat, "the look took none of the update", ok and not took, out,
                 "" if not took else "the look merged the update")
        said = out.count("An update is waiting")
        reh.note(chat, "the waiting update said once", said == 1, out,
                 "" if said == 1 else f"said {said} times")
        ok, again = reh.check(chat, "a second look says nothing more", base, root, env)
        reh.note(chat, "said once, not twice", "An update is waiting" not in again, again,
                 "" if "An update is waiting" not in again else "said again")
    reh.check(chat, "take the update", base[:2] + (["--update"] if asks else []) + base[2:],
              root, env)


def start_commit(repo: str, ref: str, origin: str) -> tuple[str, str]:
    """(the commit of the person's repo the rehearsal starts from, made the master of the
    bare copy `origin`, or "", and a plain line to say). The bare copy holds only the repo's
    branches, so a start held only by origin/master (a cloud checkout on no branch, a local
    master behind it) was "not a commit" of a repo that had it (2026-10-21): it is fetched
    by its hash."""
    sha = _git("rev-parse", "--verify", "-q", ref + "^{commit}", cwd=repo).stdout.strip()
    if not sha:
        app = _git("rev-parse", "--verify", "-q", ref + "^{commit}", cwd=HERE).stdout.strip()
        if app:
            return "", (f"{ref} is a commit of the app, not of {repo}: the app commit to "
                        f"rehearse goes in --app, and --ref names where their repo starts")
        return "", f"{ref} is not a commit of {repo}: name one of its branches or commits"
    said = ""
    if _git("cat-file", "-e", sha + "^{commit}", cwd=origin).returncode:
        r = _git("-c", "protocol.version=2", "fetch", "-q", "--no-tags", "--upload-pack",
                 "git -c uploadpack.allowAnySHA1InWant=true upload-pack", repo, sha, cwd=origin)
        if r.returncode or _git("cat-file", "-e", sha + "^{commit}", cwd=origin).returncode:
            return "", (f"{ref} ({sha[:12]}) is in {repo} but could not be copied: "
                        f"{(r.stderr or r.stdout).strip()[:200]}")
        said = f"{ref} ({sha[:12]}) is on no branch of {repo}: copied by its commit"
    if _git("update-ref", "refs/heads/master", sha, cwd=origin).returncode:
        return "", f"{ref} ({sha[:12]}) could not be made the copy's master"
    # A clone checks out the branch the copy's HEAD names, which a bare clone takes from the
    # repo it copied: whatever branch that checkout was on, not --ref (2026-10-25, a
    # rehearsal ran a scratch branch's tests). Master, which now holds --ref, it is.
    if _git("symbolic-ref", "HEAD", "refs/heads/master", cwd=origin).returncode:
        return "", f"the copy of {repo} could not be pointed at {ref} ({sha[:12]})"
    return sha, said


def folder_said(out: str) -> str:
    """The folder `sync_app.py --worktree` said it made, or "". It quotes a path with a
    space, which a bare run of non-spaces cut at the space and read as no folder at all."""
    import shlex
    m = re.search(r"own folder is ('(?:[^']|'\\'')*'|\S+), on branch", out)
    if not m:
        return ""
    try:
        got = shlex.split(m.group(1))
    except ValueError:
        return ""
    return got[0].rstrip(",") if got else ""


def copy_app(here: str, app: str, sha: str) -> str:
    """Clone the app at `here` into `app` with `sha` checked out as master, or say why not.

    A clone copies branches alone, so the commit a release rehearses (the new master, held
    by origin/master after a PR merges) was "not a tree" in the copy: fetched by its commit
    when the clone lacks it, as start_commit fetches the person's."""
    r = _git("clone", "-q", "--no-local", here, app, cwd=os.path.dirname(app))
    if r.returncode:
        return f"git clone: {(r.stderr or r.stdout).strip()[:300]}"
    if _git("cat-file", "-e", sha + "^{commit}", cwd=app).returncode:
        r = _git("-c", "protocol.version=2", "fetch", "-q", "--no-tags", "--upload-pack",
                 "git -c uploadpack.allowAnySHA1InWant=true upload-pack", here, sha, cwd=app)
        if r.returncode or _git("cat-file", "-e", sha + "^{commit}", cwd=app).returncode:
            return f"{sha[:12]} could not be copied from {here}: {(r.stderr or r.stdout).strip()[:200]}"
    r = _git("checkout", "-q", "-B", "master", sha, cwd=app)
    return "" if not r.returncode else f"git checkout: {(r.stderr or r.stdout).strip()[:300]}"


def rehearse(repo: str, ref: str, app_ref: str, ci: bool, keep: bool) -> int:
    tmp = tempfile.mkdtemp(prefix="ljs_rehearse_")
    reh = Rehearsal()
    try:
        app, origin = os.path.join(tmp, "app"), os.path.join(tmp, "origin.git")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        # --verify: plain rev-parse echoes a name it cannot find, which read as a commit.
        sha = _git("rev-parse", "--verify", "-q", app_ref + "^{commit}", cwd=HERE).stdout.strip()
        if not sha:
            print(f"rehearse_sync: {app_ref} is not a commit of this app")
            return 2
        failed = copy_app(HERE, app, sha)
        for cmd, cwd in (() if failed else
                         ((["git", "tag", "-f", CANDIDATE_TAG, sha], app),
                          (["git", "clone", "-q", "--bare", "--no-local", repo, origin], tmp))):
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode:
                failed = f"{' '.join(cmd[:3])}: {(r.stderr or r.stdout).strip()[:300]}"
                break
        if failed:
            print(f"rehearse_sync: could not make the copies: {failed}")
            return 2
        start, said = start_commit(repo, ref, origin)
        if not start:
            print(f"rehearse_sync: {said}")
            return 2
        if said:
            print(f"rehearse_sync: {said}")
        cloud, local = os.path.join(tmp, "cloud"), os.path.join(tmp, "theirs")
        for d in (cloud, local):
            _git("clone", "-q", origin, d, cwd=tmp)
        envs = {"cloud": _env(True, app, home), "computer": _env(False, app, home)}
        py = sys.executable

        # The cloud chat: a fresh clone, its own copy of the sync, as a chat starts.
        ok, _ = reh.check("cloud", "pull master", [py, "tools/sync_app.py", "--pull"], cloud,
                          envs["cloud"])
        take_update(reh, "cloud", cloud, envs["cloud"], sha)
        merged = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=cloud).returncode == 0
        reh.note("cloud", "the update is merged", merged,
                 _git("log", "-1", "--format=%s", cwd=cloud).stdout, "" if merged else
                 "the app commit is not in the chat's history")

        # The chat on their computer: its own folder, from the same start, at the same time.
        ok, out = reh.check("computer", "a folder of its own",
                            [py, "tools/sync_app.py", "--worktree", "rehearsal"], local,
                            envs["computer"])
        wt = folder_said(out)
        if wt and os.path.isdir(wt):
            take_update(reh, "computer", wt, envs["computer"], sha)
        else:
            reh.note("computer", "take the update", False, out, "no folder was made")

        everyday(reh, "cloud", cloud, envs["cloud"], ci)
        if wt and os.path.isdir(wt):
            everyday(reh, "computer", wt, envs["computer"], ci)

        # The cloud chat lands first; the computer chat then takes master, as its next sync
        # would: the merge must go through with no conflict.
        r = _git("push", "-q", "origin", "HEAD:master", cwd=cloud)
        reh.note("cloud", "land on master", r.returncode == 0, r.stderr,
                 "" if r.returncode == 0 else "push refused")
        if wt and os.path.isdir(wt):
            reh.check("computer", "take master after the cloud chat landed",
                      [py, "tools/sync_app.py", "--pull"], wt, envs["computer"])
            left = _git("diff", "--name-only", "--diff-filter=U", cwd=wt).stdout.strip()
            reh.note("computer", "no conflict with the cloud chat's update", not left, left,
                     "" if not left else "conflicted")
            r = _git("push", "-q", "origin", "HEAD:master", cwd=wt)
            reh.note("computer", "land on master after it", r.returncode == 0, r.stderr,
                     "" if r.returncode == 0 else "push refused")
        print(reh.report())
        return 0 if all(s[2] for s in reh.steps) else 1
    finally:
        # Said however the run ended: a run that stopped early kept its copies in silence.
        if keep:
            print(f"\nThe copies are kept in {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo", help="the person's repository, read only")
    ap.add_argument("--ref", default="origin/master", help="their commit to start from")
    ap.add_argument("--app", default="HEAD", help="the app commit to rehearse")
    ap.add_argument("--no-ci", action="store_true", help="skip the local CI in each chat")
    ap.add_argument("--keep", action="store_true", help="keep the copies to look at")
    a = ap.parse_args(argv)
    if not os.path.isdir(os.path.join(a.repo, ".git")) and not os.path.isfile(
            os.path.join(a.repo, ".git")):
        print(f"rehearse_sync: {a.repo} is not a git repository")
        return 2
    return rehearse(os.path.abspath(a.repo), a.ref, a.app, not a.no_ci, a.keep)


if __name__ == "__main__":
    raise SystemExit(main())
