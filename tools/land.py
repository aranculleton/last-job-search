#!/usr/bin/env python3
"""Land a chat's work on master in one command, run in the background: the landing rule as code.

Every step of a chat re-reads its whole history, so steps are the cost. Landing took about
fourteen (save, commit, the check, fetch, merge, push, open the pull request, merge it,
unsubscribe, then a stash and a checkout of master), and chats ran the three-minute check in
the foreground (2026-11-03). Now a chat starts this with Bash `run_in_background`, at most
once a turn, after its answer is out, and makes only the GitHub calls it prints:

    python3 tools/land.py [--message "<what changed>"]
    python3 tools/land.py --after-merge
    python3 tools/land.py --waiting

1. tools/save_state.py stages the person's files, and nothing of the app's is committed
   (tools/personal_paths.py is the line); a commit when anything is staged.
2. git fetch origin master, then git merge --no-edit origin/master, here, where the
   row-by-row driver merges the state files. A conflict: the merge is aborted, exit 2.
3. Nothing ahead of origin/master: "land: nothing to land", exit 0, and no check is run.
4. ./tools/ci_local.sh --quick. Not green: its failing lines, exit 1.
5. git push -u origin HEAD, a network failure retried four times (2, 4, 8 and 16 s).
6. "land: ready <branch>", then the two GitHub calls to make (open the pull request, merge
   it) and --after-merge.

Not green or a conflict still pushes this chat's branch (the commit before the merge, for a
conflict), with no pull request, and says the work waits there: a cloud container is gone
when its chat ends, and work only committed in it was lost with it (the release review,
2026-11-03). --waiting lists every such branch, for the next chat or run to bring in.

--after-merge: git fetch origin master; when the commit this landing pushed is on master
now, the branch is reset to master (git checkout -B <branch> origin/master), so the next
piece of work starts current, with no stash and no checkout of master. A page update that
took master since (app_setup.take_master) adds only a merge commit, which is no reason to
say "not merged"; newer work of the chat's own is kept, with master merged into it.

While it runs it holds a lock in the checkout's git folder, and a page update takes no
master meanwhile (app_setup.take_master); a git command refused because another one holds
git's own index.lock is tried again for a few seconds.

Each git command is its own call, nothing is ever force-pushed, and everything printed is for
Claude, never the person (CLAUDE.md, "Saving"). Exit 0 landed or ready, 1 not green or not
merged yet, 2 stopped before the push (the line says why, and whether the work waits on its
branch). The check can be replaced, for the tests only, by `check=` or LJS_LAND_CHECK (a
command line).
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
# Another git command running in this checkout at the same moment (a page update taking
# master, the update check) holds git's index.lock, and git refuses at once rather than
# waiting: the landing stopped with exit 2 and a line about removing a file (2026-11-03).
INDEX_LOCK = re.compile(r"index\.lock", re.I)
LOCK_WAITS = (0.5, 1, 2, 4)
# This landing's own marks, in the checkout's git folder, never committed: the lock a page
# update reads (app_setup.take_master skips taking master while it is held), and the commit
# the last landing pushed, which --after-merge looks for on master.
LOCK_FILE = "ljs-landing.lock"
PUSHED_FILE = "ljs-landed"
LOCK_STALE_S = 30 * 60
# The branches a chat or a scheduled run works on: a cloud chat's and a run's (claude/...)
# and a second chat's folder on a computer (sync_app.branch_name, chat/...).
CHAT_BRANCHES = ("claude/", "chat/")


def _git(root: str, *args: str, waits=LOCK_WAITS) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for wait in waits:
        if r.returncode == 0 or not INDEX_LOCK.search(r.stderr or ""):
            break
        time.sleep(wait)
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    return r


def _said(r: subprocess.CompletedProcess) -> str:
    if INDEX_LOCK.search(r.stderr or ""):
        return "another git command was running here at the same time, for longer than it waited"
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


def git_dir(root: str = ROOT) -> str:
    """This checkout's own git folder (a worktree has one of its own), or ""."""
    r = _git(root, "rev-parse", "--absolute-git-dir")
    return r.stdout.strip() if r.returncode == 0 else ""


def _alive(pid: int) -> bool:
    if os.name != "posix":
        return True                 # os.kill would end the process on Windows: age decides
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def landing(root: str = ROOT) -> bool:
    """Is a landing running in this checkout now: its lock there, its process alive, and
    younger than LOCK_STALE_S (a landing killed part way leaves one behind)."""
    d = git_dir(root)
    if not d:
        return False
    p = os.path.join(d, LOCK_FILE)
    try:
        age = time.time() - os.path.getmtime(p)
        with open(p, encoding="utf-8") as fh:
            pid = int((fh.read().split() or ["0"])[0])
    except (OSError, ValueError):
        return False
    return age < LOCK_STALE_S and (pid <= 0 or _alive(pid))


@contextlib.contextmanager
def _holding(root: str):
    """The landing's lock, for as long as it runs; False when another landing holds it."""
    d = git_dir(root)
    if not d:
        yield True
        return
    if landing(root):
        yield False
        return
    p = os.path.join(d, LOCK_FILE)
    try:
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    except OSError:
        pass
    try:
        yield True
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def _record_pushed(root: str, name: str) -> None:
    d = git_dir(root)
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if d and head:
        try:
            with open(os.path.join(d, PUSHED_FILE), "w", encoding="utf-8", newline="\n") as fh:
                fh.write("%s %s\n" % (head, name))
        except OSError:
            pass


def pushed(root: str = ROOT) -> str:
    """The commit the last landing of this branch pushed, or ""."""
    d = git_dir(root)
    try:
        with open(os.path.join(d, PUSHED_FILE), encoding="utf-8") as fh:
            sha, _, name = fh.read().strip().partition(" ")
    except OSError:
        return ""
    return sha if sha and name.strip() == branch(root) else ""


def _forget_pushed(root: str) -> None:
    try:
        os.remove(os.path.join(git_dir(root), PUSHED_FILE))
    except OSError:
        pass


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
    for wait in (*LOCK_WAITS, None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = save_state.main([], root=root)
        if code == 0 or wait is None or not INDEX_LOCK.search(buf.getvalue()):
            break
        time.sleep(wait)
    if code != 0:
        if INDEX_LOCK.search(buf.getvalue()):
            return False, ("another git command was running here at the same time, for longer "
                           "than it waited")
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


def _own_branch(root: str) -> tuple[str, str]:
    """(branch, why not): the branch this chat's work is pushed to. A computer chat working
    on master or a detached HEAD gets a branch of its own, so the pull request has a head and
    nothing reaches master but through it."""
    name = branch(root)
    if name in ("", "master", "main"):
        name = time.strftime("claude/land-%Y%m%d-%H%M%S", time.gmtime())
        r = _git(root, "switch", "-q", "-c", name)
        if r.returncode != 0:
            return "", _said(r)
    return name, ""


def _wait_on_branch(root: str, head: str, sleep) -> None:
    """Not landed, but never lost: this chat's branch pushed with no pull request, so the
    next chat or run finds it (--waiting). A cloud container is gone when its chat ends, and
    work only committed there went with it (the release review, 2026-11-03)."""
    name, why = _own_branch(root)
    if name:
        r = _retried(root, "push", "-q", "-u", "origin", "HEAD", sleep=sleep)
        if r.returncode == 0:
            print("%s; the work waits on %s, pushed with no pull request: open none. The next "
                  "chat or run brings it in (python3 tools/land.py --waiting lists it) and lands "
                  "it" % (head, name))
            return
        why = _said(r)
    print("%s; nothing was pushed (%s), and the work stays committed here" % (head, why))


def waiting(root: str = ROOT) -> list[str]:
    """The branches on GitHub (origin/claude/..., origin/chat/...) whose work is not on master
    and is the person's alone: a landing that was not green or stopped on a conflict, a run
    that could not finish. Each is brought in with git merge --no-edit <it>, and lands with
    the work of whoever brings it in. A branch that changes any of the app's files is never
    listed: no landing commits one, so it is not a chat's work."""
    import personal_paths
    here = branch(root)
    r = _git(root, "for-each-ref", "--format=%(refname:short)", "--no-merged", "origin/master",
             *("refs/remotes/origin/" + p.rstrip("/") for p in CHAT_BRANCHES))
    out = []
    for ref in (x.strip() for x in r.stdout.splitlines() if x.strip()):
        if ref == "origin/" + here:
            continue
        d = _git(root, "diff", "--name-only", "-z", "origin/master..." + ref)
        files = [p for p in d.stdout.split("\0") if p]
        if d.returncode == 0 and files and all(personal_paths.is_personal(p) for p in files):
            out.append(ref)
    return out


def land(root: str = ROOT, message: str = "", check=None, sleep=time.sleep) -> int:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        print("land: not a git checkout; nothing was pushed")
        return 2
    if _the_app(root):
        print("land: this is the app itself, which lands through its own pull request and CI "
              "(MAINTAINING.md); nothing was pushed")
        return 2
    with _holding(root) as mine:
        if not mine:
            print("land: another landing is running in this checkout; nothing was pushed, and "
                  "the next turn's landing takes this work too")
            return 2
        return _land(root, message, check, sleep)


def _land(root: str, message: str, check, sleep) -> int:
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
            _wait_on_branch(root, "land: a conflict in %s" % ", ".join(conflicted), sleep)
        else:
            _wait_on_branch(root, "land: master could not be merged: %s" % _said(r), sleep)
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
        _wait_on_branch(root, "land: not green", sleep)
        for ln in failing(out):
            print(ln)
        return 1

    name, why = _own_branch(root)
    if not name:
        print("land: a branch could not be made: %s; nothing was pushed" % why)
        return 2
    r = _retried(root, "push", "-q", "-u", "origin", "HEAD", sleep=sleep)
    if r.returncode != 0:
        print("land: the push was refused: %s; nothing was pushed" % _said(r))
        return 2
    _record_pushed(root, name)

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
          'merge_method "merge"; in the same message, as a separate call, '
          'unsubscribe_pr_activity for it where this chat has that tool' % (owner, repo))
    print("  3. python3 tools/land.py --after-merge")
    print("  " + MERGE_REFUSED)
    print("  No GitHub tools in this chat (a computer of your own): gh pr create --base master "
          "--fill, then gh pr merge <number> --merge, each on its own line, then 3.")
    return 0


# Two chats landing at once: each merges master here, with the row-by-row driver, but
# GitHub's own merge has no driver, so the second pull request comes back not mergeable
# (the release review, 2026-11-03). Landing again merges the first one's work here.
MERGE_REFUSED = ("merge refused (not mergeable, or master moved on): run python3 tools/land.py "
                 "again (it merges master here, with the driver, and pushes the same branch), "
                 "then merge the same pull request again")


def _clean_merges(root: str) -> bool:
    """Every commit on this branch that master does not have is a merge that adds nothing of
    its own: its tree is what merging its two parents gives (a page update taking master,
    app_setup.take_master). False where it cannot be told (a git older than 2.38)."""
    if _git(root, "rev-list", "--no-merges", "origin/master..HEAD").stdout.strip():
        return False
    for m in _git(root, "rev-list", "--merges", "origin/master..HEAD").stdout.split():
        parents = _git(root, "rev-list", "--parents", "-n", "1", m).stdout.split()[1:]
        if len(parents) != 2:
            return False
        r = _git(root, "merge-tree", "--write-tree", *parents)
        tree = (r.stdout.splitlines() or [""])[0].strip()
        if r.returncode != 0 or tree != _git(root, "rev-parse", m + "^{tree}").stdout.strip():
            return False
    return True


def after_merge(root: str = ROOT, sleep=time.sleep) -> int:
    with _holding(root) as mine:
        if not mine:
            print("land: a landing is running in this checkout; nothing changed. Run "
                  "--after-merge again once it ends")
            return 2
        return _after_merge(root, sleep)


def _after_merge(root: str, sleep) -> int:
    r = _retried(root, "fetch", "-q", "origin", "master", sleep=sleep)
    if r.returncode != 0:
        print("land: master could not be fetched: %s; nothing changed" % _said(r))
        return 2

    def on(ref: str) -> bool:
        return _git(root, "merge-base", "--is-ancestor", ref, "origin/master").returncode == 0

    # The commit this landing pushed, not HEAD: a page update that took master since
    # (app_setup.take_master) put a merge commit on top, and the branch was never reset.
    sent = pushed(root)
    if not on("HEAD") and not (sent and on(sent)):
        print("land: this work is not on master yet (its pull request is not merged); "
              "nothing changed")
        return 1
    name = branch(root)
    if not on("HEAD") and not _clean_merges(root):
        # Newer work of this chat's own since the push: kept, with master taken into it, for
        # the next landing.
        r = _git(root, "merge", "--no-edit", "origin/master")
        if r.returncode != 0:
            if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
                _git(root, "merge", "--abort")
            print("land: landed, but master could not be merged into this branch's newer work: "
                  "%s; nothing changed, and the next landing merges it" % _said(r))
            return 2
        _forget_pushed(root)
        print("land: landed; %s holds newer work of its own, with master merged in, for the "
              "next landing" % (name or "this chat"))
        return 0
    if name:
        r = _git(root, "checkout", "-q", "--no-track", "-B", name, "origin/master")
    else:
        r = _git(root, "checkout", "-q", "--detach", "origin/master")
    if r.returncode != 0:
        print("land: on master, but this branch could not be moved to it: %s; nothing changed"
              % _said(r))
        return 2
    _forget_pushed(root)
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
    if "--waiting" in argv:
        found = waiting(root)
        if not found:
            print("land: nothing waiting")
            return 0
        print("land: work not on master yet, waiting on: %s" % ", ".join(found))
        print("  bring in each: git merge --no-edit <it>, each its own command; one that stops "
              "on a conflict: git merge --abort, and leave it. Then land as usual: this "
              "landing takes it to master")
        return 0
    message = ""
    if "--message" in argv:
        i = argv.index("--message")
        if i + 1 >= len(argv):
            print("usage: python3 tools/land.py [--message \"<what changed>\"] | --after-merge "
                  "| --waiting")
            return 2
        message = argv[i + 1]
    elif any(a.startswith("--message=") for a in argv):
        message = next(a for a in argv if a.startswith("--message="))[len("--message="):]
    return land(root, message, check=check, sleep=sleep)


if __name__ == "__main__":
    sys.exit(main())
