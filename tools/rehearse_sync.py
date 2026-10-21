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
   have now), exactly as a chat starts.
4. A chat on their computer: another clone makes its own folder (`--worktree`) and syncs
   there, at the same time, from the same starting point.
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
                           timeout=timeout)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes)
               else (e.stdout or "")) + "\n[timed out]"
        code = -1
    return code, out, time.time() - t


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


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


def rehearse(repo: str, ref: str, app_ref: str, ci: bool, keep: bool) -> int:
    tmp = tempfile.mkdtemp(prefix="ljs_rehearse_")
    reh = Rehearsal()
    try:
        app, origin = os.path.join(tmp, "app"), os.path.join(tmp, "origin.git")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        sha = _git("rev-parse", app_ref, cwd=HERE).stdout.strip()
        if not sha:
            print(f"rehearse_sync: {app_ref} is not a commit of this app")
            return 2
        for cmd, cwd in ((["git", "clone", "-q", "--no-local", HERE, app], tmp),
                         (["git", "checkout", "-q", "-B", "master", sha], app),
                         (["git", "tag", "-f", CANDIDATE_TAG, sha], app),
                         (["git", "clone", "-q", "--bare", "--no-local", repo, origin], tmp)):
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            if r.returncode:
                print(f"rehearse_sync: could not make the copies: {' '.join(cmd[:3])}: "
                      f"{(r.stderr or r.stdout).strip()[:300]}")
                return 2
        start = _git("rev-parse", ref, cwd=repo).stdout.strip()
        if not start or _git("update-ref", "refs/heads/master", start, cwd=origin).returncode:
            print(f"rehearse_sync: {ref} is not a commit of {repo}")
            return 2
        cloud, local = os.path.join(tmp, "cloud"), os.path.join(tmp, "theirs")
        for d in (cloud, local):
            _git("clone", "-q", origin, d, cwd=tmp)
        envs = {"cloud": _env(True, app, home), "computer": _env(False, app, home)}
        py = sys.executable

        # The cloud chat: a fresh clone, its own copy of the sync, as a chat starts.
        ok, _ = reh.check("cloud", "pull master", [py, "tools/sync_app.py", "--pull"], cloud,
                          envs["cloud"])
        ok, out = reh.check("cloud", "take the update", [py, "tools/sync_app.py", "--on",
                                                         "rehearsal", "--tools", "none"],
                            cloud, envs["cloud"])
        merged = _git("merge-base", "--is-ancestor", sha, "HEAD", cwd=cloud).returncode == 0
        reh.note("cloud", "the update is merged", merged,
                 _git("log", "-1", "--format=%s", cwd=cloud).stdout, "" if merged else
                 "the app commit is not in the chat's history")

        # The chat on their computer: its own folder, from the same start, at the same time.
        ok, out = reh.check("computer", "a folder of its own",
                            [py, "tools/sync_app.py", "--worktree", "rehearsal"], local,
                            envs["computer"])
        m = re.search(r"own folder is (\S+), on branch", out)
        wt = m.group(1).rstrip(",") if m else ""
        if wt and os.path.isdir(wt):
            reh.check("computer", "take the update", [py, "tools/sync_app.py", "--on",
                                                      "rehearsal", "--tools", "none"],
                      wt, envs["computer"])
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
        if keep:
            print(f"\nThe copies are kept in {tmp}")
        return 0 if all(s[2] for s in reh.steps) else 1
    finally:
        if not keep:
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
