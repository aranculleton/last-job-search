#!/usr/bin/env python3
"""Land a chat's work on master in one command, run in the background: the landing rule as code.

Every step of a chat re-reads its whole history, so steps are the cost. Landing took about
fourteen (save, commit, the check, fetch, merge, push, open the pull request, merge it,
unsubscribe, then a stash and a checkout of master), and chats ran the three-minute check in
the foreground (2026-11-03). Now a chat starts this with Bash `run_in_background`, at most
once a turn, after its answer is out, and makes only the GitHub calls it prints:

    python3 tools/land.py [--message "<what changed>"]
    python3 tools/land.py --after-merge

1. tools/save_state.py stages the person's files, and nothing of the app's is committed
   (tools/personal_paths.py is the line); a commit when anything is staged.
2. git fetch origin master, then git merge --no-edit origin/master, here, where the
   row-by-row driver merges the state files. A conflict: the merge is aborted, exit 2.
3. Nothing ahead of origin/master: "land: nothing to land", exit 0, and no check is run.
4. ./tools/ci_local.sh --quick. Not green: its failing lines, exit 1, nothing else
   changed (the work stays committed on this branch for the next chat).
5. git push -u origin HEAD, a network failure retried four times (2, 4, 8 and 16 s).
6. "land: ready <branch>", then the two GitHub calls to make (open the pull request, merge
   it) and --after-merge.

--after-merge: git fetch origin master; when this branch is on master now, it is reset to
master (git checkout -B <branch> origin/master), so the next piece of work starts current,
with no stash and no checkout of master; otherwise it says so and changes nothing.

Each git command is its own call, nothing is ever force-pushed, and everything printed is for
Claude, never the person (CLAUDE.md, "Saving"). Exit 0 landed or ready, 1 not green or not
merged yet, 2 stopped before the push (the line says why; nothing was pushed). The check can
be replaced, for the tests only, by `check=` or LJS_LAND_CHECK (a command line).
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DEFAULT_MESSAGE = "Save the search's work"
APP_REPO = "aranculleton/last-job-search"      # app_setup.APP_REPO, without its imports
WAITS = (2, 4, 8, 16)
# What a push or a fetch says when the network, not GitHub's answer, stopped it. A refusal
# (a rejected push, no permission) is never retried: it would be refused again.
NETWORK = re.compile(r"could not resolve|unable to access|timed? ?out|connection (?:reset|refused|"
                     r"closed|timed)|failed to connect|early eof|rpc failed|remote end hung up|"
                     r"\b50[234]\b|temporar|network is unreachable|tls|ssl|broken pipe", re.I)
REFUSED = re.compile(r"\b40[13]\b|rejected|denied|not allowed|protected branch|permission",
                     re.I)


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _said(r: subprocess.CompletedProcess) -> str:
    lines = (r.stderr.strip() or r.stdout.strip()).splitlines()
    return lines[-1].strip() if lines else "no words from git"


def _retried(root: str, *args: str, sleep=time.sleep, run=None) -> subprocess.CompletedProcess:
    """A git command that reaches GitHub, tried again after 2, 4, 8 and 16 s while the
    network is what stopped it."""
    run = run or _git
    r = run(root, *args)
    for wait in WAITS:
        text = r.stderr + r.stdout
        if r.returncode == 0 or REFUSED.search(text) or not NETWORK.search(text):
            return r
        sleep(wait)
        r = run(root, *args)
    return r


def branch(root: str) -> str:
    """The branch checked out, or "" on a detached HEAD."""
    r = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else ""


def _slug(root: str) -> tuple[str, str]:
    """(owner, repo) from origin's address, whatever its form (https, ssh, a cloud proxy)."""
    url = _git(root, "remote", "get-url", "origin").stdout.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = [p for p in re.split(r"[/:]", url) if p]
    return (parts[-2], parts[-1]) if len(parts) >= 2 else ("<owner>", "<repo>")


def _the_app(root: str) -> bool:
    """The public app's own checkout, told the way ci_local.sh tells it: origin ends in the
    app's address and there is no profile. Its changes land through its own CI."""
    if os.path.isfile(os.path.join(root, "profile", "person.json")):
        return False
    url = _git(root, "remote", "get-url", "origin").stdout.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.endswith(("/" + APP_REPO, ":" + APP_REPO))


def _check_command(root: str, check) -> list[str]:
    if check:
        return list(check)
    env = os.environ.get("LJS_LAND_CHECK", "").strip()
    if env:
        return shlex.split(env)
    shell = ""
    try:
        import local_path
        shell = local_path.bash()      # Git Bash on Windows, never WSL's launcher
    except Exception:  # noqa: BLE001
        pass
    return [shell or "bash", os.path.join("tools", "ci_local.sh"), "--quick"]


def failing(out: str) -> list[str]:
    """The lines that say what failed: each FAIL with the detail under it, then the summary."""
    lines = out.rstrip().splitlines()
    keep: list[str] = []
    for i, ln in enumerate(lines):
        if ln.rstrip().endswith("FAIL"):
            keep.append(ln)
            j = i + 1
            while j < len(lines) and lines[j].startswith("      "):
                keep.append(lines[j])
                j += 1
    tail = [ln for ln in lines[-6:] if ln not in keep]
    return (keep[:80] + tail) if keep else lines[-12:]


def _skips(out: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s+(.+?)\s+SKIP\s+\(", out, re.M)]


def _stage(root: str) -> tuple[bool, str]:
    """save_state, then nothing of the app's left in the index. (ok, what went wrong)."""
    import personal_paths
    import save_state
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = save_state.main([], root=root)
    if code != 0:
        said = buf.getvalue().strip().splitlines()
        return False, said[-1] if said else "save_state.py failed"
    staged = [p for p in _git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    apps = [p for p in staged if not personal_paths.is_personal(p)]
    if apps:
        r = _git(root, "reset", "-q", "--", *apps)
        if r.returncode != 0:
            return False, _said(r)
        print("land: left out %d file(s) of the app's, never committed from here: %s"
              % (len(apps), ", ".join(apps[:8]) + (" ..." if len(apps) > 8 else "")))
    return True, ""


def land(root: str = ROOT, message: str = "", check=None, sleep=time.sleep) -> int:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        print("land: not a git checkout; nothing was pushed")
        return 2
    if _the_app(root):
        print("land: this is the app itself, which lands through its own pull request and CI "
              "(MAINTAINING.md); nothing was pushed")
        return 2
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        print("land: a merge is already under way here; finish it or abort it first. "
              "Nothing was pushed")
        return 2

    ok, why = _stage(root)
    if not ok:
        print("land: saving stopped: %s; nothing was pushed" % why)
        return 2
    if _git(root, "diff", "--cached", "--quiet").returncode != 0:
        r = _git(root, "commit", "-q", "-m", message.strip() or DEFAULT_MESSAGE)
        if r.returncode != 0:
            print("land: the commit was refused: %s; nothing was pushed" % _said(r))
            return 2

    r = _retried(root, "fetch", "-q", "origin", "master", sleep=sleep)
    if r.returncode != 0:
        print("land: master could not be fetched: %s; nothing was pushed" % _said(r))
        return 2
    r = _git(root, "merge", "--no-edit", "origin/master")
    if r.returncode != 0:
        conflicted = [p for p in _git(root, "diff", "--name-only", "--diff-filter=U").stdout
                      .splitlines() if p]
        if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
            _git(root, "merge", "--abort")
        if conflicted:
            print("land: a conflict in %s; nothing was pushed" % ", ".join(conflicted))
        else:
            print("land: master could not be merged: %s; nothing was pushed" % _said(r))
        return 2

    ahead = _git(root, "rev-list", "--count", "origin/master..HEAD").stdout.strip()
    if ahead in ("", "0"):
        print("land: nothing to land")
        return 0

    cmd = _check_command(root, check)
    c = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = c.stdout + c.stderr
    if c.returncode != 0:
        print("land: not green; nothing was pushed, and the work stays committed here")
        for ln in failing(out):
            print(ln)
        return 1

    name = branch(root)
    if name in ("", "master", "main"):
        # A computer chat working on master or a detached HEAD: a branch of its own, so the
        # pull request has a head and nothing reaches master but through it.
        name = time.strftime("claude/land-%Y%m%d-%H%M%S", time.gmtime())
        r = _git(root, "switch", "-q", "-c", name)
        if r.returncode != 0:
            print("land: a branch could not be made: %s; nothing was pushed" % _said(r))
            return 2
    r = _retried(root, "push", "-q", "-u", "origin", "HEAD", sleep=sleep)
    if r.returncode != 0:
        print("land: the push was refused: %s; nothing was pushed" % _said(r))
        return 2

    owner, repo = _slug(root)
    title = (message.strip().splitlines() or [DEFAULT_MESSAGE])[0][:70]
    skipped = _skips(out)
    body = ("Checked here with ./tools/ci_local.sh --quick: green" +
            ("; skipped: " + ", ".join(skipped) if skipped else "") + ".")
    print("land: ready %s (%s commit(s) ahead of master)" % (name, ahead))
    print("land: next, each its own call, and nothing said to the person:")
    print('  1. create_pull_request: owner "%s", repo "%s", head "%s", base "master", '
          'title "%s", body "%s"' % (owner, repo, name, title.replace('"', "'"), body))
    print('  2. merge_pull_request: owner "%s", repo "%s", pullNumber <the number 1 gave>, '
          'merge_method "merge"' % (owner, repo))
    print("  3. python3 tools/land.py --after-merge")
    print("  No GitHub tools in this chat (a computer of your own): gh pr create --base master "
          "--fill, then gh pr merge <number> --merge, each on its own line, then 3.")
    return 0


def after_merge(root: str = ROOT, sleep=time.sleep) -> int:
    r = _retried(root, "fetch", "-q", "origin", "master", sleep=sleep)
    if r.returncode != 0:
        print("land: master could not be fetched: %s; nothing changed" % _said(r))
        return 2
    if _git(root, "merge-base", "--is-ancestor", "HEAD", "origin/master").returncode != 0:
        print("land: this work is not on master yet (its pull request is not merged); "
              "nothing changed")
        return 1
    name = branch(root)
    if name:
        r = _git(root, "checkout", "-q", "--no-track", "-B", name, "origin/master")
    else:
        r = _git(root, "checkout", "-q", "--detach", "origin/master")
    if r.returncode != 0:
        print("land: on master, but this branch could not be moved to it: %s; nothing changed"
              % _said(r))
        return 2
    print("land: landed; %s starts from master now" % (name or "this chat"))
    return 0


def _utf8_stdio() -> None:
    try:
        import python_floor
        python_floor.utf8_stdio()
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None, root: str = ROOT, check=None, sleep=time.sleep) -> int:
    _utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return 0
    if "--after-merge" in argv:
        return after_merge(root, sleep=sleep)
    message = ""
    if "--message" in argv:
        i = argv.index("--message")
        if i + 1 >= len(argv):
            print("usage: python3 tools/land.py [--message \"<what changed>\"] | --after-merge")
            return 2
        message = argv[i + 1]
    elif any(a.startswith("--message=") for a in argv):
        message = next(a for a in argv if a.startswith("--message="))[len("--message="):]
    return land(root, message, check=check, sleep=sleep)


if __name__ == "__main__":
    sys.exit(main())
