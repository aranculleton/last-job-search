#!/usr/bin/env python3
"""Bring the app's updates into a person's repo. Nothing is ever sent back.

A person's repo is made from the app with "Use this template", so the two share
files but not history. This fetches the app and merges its new commits:

    python3 tools/sync_app.py            # fetch the app, merge what is new
    python3 tools/sync_app.py --check    # how far behind, and any drift; changes nothing
    python3 tools/sync_app.py --adopt    # once, for the repo the app was first built from
    python3 tools/sync_app.py --if-stale # the day's first check: master, then the app; else nothing

The rules, enforced here rather than remembered:

- The app owns every path `tools/personal_paths.py` does not call personal; the
  person owns the rest. A personal path is never touched. If the app's commits
  would change one (they cannot unless the app itself is broken), nothing is
  merged and the paths are listed.
- An app-owned file edited in this repo ("drift") is put back to the app's
  version, and every file put back is named, in the output and in the commit.
  App changes are made in the app and arrive here; an edit made here would be
  overwritten by the app's next change to that file anyway, silently, so it is
  overwritten now, loudly. A file the app does not have is left alone and
  reported.
- Uncommitted changes stop it before anything happens. Anything the merge
  cannot settle aborts it and leaves the repo exactly as it was.
- In the app itself, a no-op.
- After every sync, "up to date" included, it lists the profile upgrades this
  repo still needs and runs the instant ones (`tools/profile_upgrades.py`).

The first sync of a template-made repo has no common commit, so it merges with
--allow-unrelated-histories: identical files merge clean, and an app-owned file
that differs takes the app's version.

--if-stale is for a chat that carries on for days, which is how most people use it: the
start-of-session steps never run again in one, so updates would wait for a new chat that
never comes. It does what a session's first two steps do (bring master in, then sync)
unless they already ran today, which a stamp in the git directory records, and otherwise
prints one line and does nothing. Every successful sync writes that stamp.
`run_round.py` and `stage_picks.py` print a reminder when today's check has not run.

--adopt is for the one repo whose app-owned files ARE the app, the private repo
the app's first commit was built from. It checks that every app-owned file is
byte-identical to the app's, then records the app's history as merged without
changing a file (`git merge -s ours`), so later syncs bring only new app commits.

The app's address lives here, in an app-owned file, so a change to it reaches
everyone on their next sync. LJS_APP_URL overrides it (the tests point it at a
local repository).

Exit: 0 synced or up to date, 1 stopped (uncommitted changes, a conflict, or
--adopt found a difference), 2 the app could not be reached.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from personal_paths import _regex  # noqa: E402
from personal_paths import is_personal as _personal_here  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_URL = "https://github.com/aranculleton/last-job-search"
REMOTE = "app"
BRANCH = "master"
APP = f"{REMOTE}/{BRANCH}"
MASTER = APP
STABLE = f"{REMOTE}/stable"
RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


# The app's own portals, as the app lists them. Every other portal under
# .agents/skills/ is the person's (tools/personal_paths.py), and a sync judges
# what comes in by the rules this repo already has, so a portal the app started
# shipping after the last sync would read as the app touching a personal path
# and stop the sync. Reading the app's list of its own portals lets it through.
# Only `.agents/skills/<name>/**` entries are taken: the app can claim a portal
# folder this way and nothing else, never the profile or the state. A portal the
# person built under the same name as a new one of the app's is replaced by the
# app's (a conflict on an app-owned path takes the app's version).
_PORTAL_ENTRY = re.compile(r"\.agents/skills/[a-z0-9][a-z0-9-]*/\*\*\Z")
_APP_PORTALS: list[re.Pattern] = []


def is_personal(path: str) -> bool:
    """personal_paths.is_personal, less any portal the app now ships."""
    if any(r.match(path.replace(os.sep, "/")) for r in _APP_PORTALS):
        return False
    return _personal_here(path)


def app_portals() -> list[str]:
    """The `.agents/skills/<name>/**` entries in the app's APP_EXCEPTIONS. Read
    as data, never run."""
    r = git("show", f"{APP}:tools/personal_paths.py", check=False)
    if r.returncode != 0:
        return []
    try:
        tree = ast.parse(r.stdout)
    except SyntaxError:
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "APP_EXCEPTIONS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return []
            return [g for g in value if isinstance(g, str) and _PORTAL_ENTRY.match(g)]
    return []


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], text=True, capture_output=True, check=check)


def _norm(url: str) -> str:
    u = url.strip().rstrip("/")
    scp = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", u)      # user@host:owner/repo, the ssh form
    if scp:
        u = f"https://{scp.group(1)}/{scp.group(2)}"
    if u.endswith(".git"):
        u = u[:-4]
    return u.lower()


def app_url() -> str:
    return os.environ.get("LJS_APP_URL") or APP_URL


def is_the_app() -> bool:
    origin = git("remote", "get-url", "origin", check=False)
    return origin.returncode == 0 and _norm(origin.stdout) == _norm(app_url())


def fetch() -> str | None:
    """Point the `app` remote at the app and fetch it. The error, or None."""
    url = app_url()
    have = git("remote", "get-url", REMOTE, check=False)
    if have.returncode != 0:
        git("remote", "add", REMOTE, url)
    elif have.stdout.strip() != url:
        git("remote", "set-url", REMOTE, url)
    r = git("fetch", "--quiet", "--no-tags", REMOTE, BRANCH, check=False)
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["no error text"])[-1]
        return f"the app could not be reached at {url}: {last}"
    return None


# ------------------------------------------------------------------ channels
#
# Two channels. "master" takes every change the day it merges; it is for the
# app's maintainer, whose own copy is where a change is tried first. "stable"
# takes only what the maintainer has released (the newest vX.Y.Z tag), so one
# bad merge does not reach everyone at once. A repo whose GitHub owner is the
# app's is the maintainer's and follows master; everyone else follows stable.
# `"app_channel"` in profile/person.json overrides either way.

def _owner(url: str) -> str:
    m = re.match(r"^https?://[^/]+/([^/]+)/", _norm(url) + "/")
    return m.group(1) if m else ""


def channel() -> str:
    """"master" or "stable", for this repo."""
    try:
        with open(os.path.join(ROOT, "profile", "person.json"), encoding="utf-8") as fh:
            chosen = str(json.load(fh).get("app_channel") or "").strip().lower()
        if chosen in ("master", "stable"):
            return chosen
    except (OSError, ValueError, AttributeError):
        pass
    origin = git("remote", "get-url", "origin", check=False)
    mine = _owner(origin.stdout) if origin.returncode == 0 else ""
    return "master" if mine and mine == _owner(app_url()) else "stable"


def newest_release() -> str | None:
    """The app's newest vX.Y.Z tag, by version number, or None if it has none."""
    r = git("ls-remote", "--tags", "--refs", REMOTE, "v*", check=False)
    tags = []
    for line in r.stdout.splitlines() if r.returncode == 0 else []:
        name = line.split("refs/tags/", 1)[-1].strip()
        m = RELEASE.match(name)
        if m:
            tags.append((tuple(int(x) for x in m.groups()), name))
    return max(tags)[1] if tags else None


def follow() -> str:
    """Point APP at what this repo's channel takes, and say which.

    stable takes the newest release, with two exceptions that both take master:
    the app has no release yet, and a first sync, where the repo was made from
    a snapshot of master and a release older than that snapshot would put
    app-owned files back. Once synced, a release older than what this repo
    already holds is an ancestor of it, so stable never goes backwards.
    """
    global APP
    APP = MASTER
    if channel() == "master":
        return "following the app's master (every change, the day it merges)"
    tag = newest_release()
    if not tag:
        return "following the app's master: it has no release yet"
    if merge_base() is None:
        return "following the app's master for this first sync; releases after this"
    r = git("fetch", "--quiet", "--no-tags", REMOTE,
            f"+refs/tags/{tag}:refs/remotes/{REMOTE}/release-tag", check=False)
    sha = git("rev-parse", f"refs/remotes/{REMOTE}/release-tag^{{commit}}", check=False)
    if r.returncode != 0 or sha.returncode != 0:
        return f"following the app's master: release {tag} could not be fetched"
    git("update-ref", f"refs/remotes/{STABLE}", sha.stdout.strip())
    APP = STABLE
    return f"following the app's releases, newest {tag}"


def _shallow() -> bool:
    return git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def merge_base() -> str | None:
    """The last app commit this repo merged, or None if it never has.

    A cloud session's clone is shallow, and the last sync can sit below its
    depth, which looks exactly like never having synced. Treating that as a
    first sync would re-merge the whole app as unrelated history, so the clone
    is deepened until the base turns up or the history runs out.
    """
    for _ in range(6):
        r = git("merge-base", "HEAD", APP, check=False)
        if r.returncode == 0:
            return r.stdout.strip()
        if not _shallow():
            return None
        git("fetch", "--quiet", "--deepen=500", "origin", check=False)
    if _shallow():
        git("fetch", "--quiet", "--unshallow", "origin", check=False)
    r = git("merge-base", "HEAD", APP, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def _tree(ref: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob) for every file at ref."""
    out = {}
    for line in git("ls-tree", "-r", "--full-tree", ref).stdout.splitlines():
        meta, path = line.split("\t", 1)
        mode, _, sha = meta.split()
        out[path] = (mode, sha)
    return out


def _index() -> dict[str, tuple[str, str]]:
    """path -> (mode, blob) for every file in the index (a merge in progress included)."""
    out = {}
    for line in git("ls-files", "-s").stdout.splitlines():
        meta, path = line.split("\t", 1)
        mode, sha, _ = meta.split()
        out[path] = (mode, sha)
    return out


def drift(ref: str = "HEAD") -> tuple[list[str], list[str]]:
    """App-owned files at ref that differ from the app's, and ones the app lacks."""
    mine = {p: v for p, v in _tree(ref).items() if not is_personal(p)}
    theirs = _tree(APP)
    changed = sorted(p for p, v in theirs.items() if mine.get(p) != v and not is_personal(p))
    extra = sorted(p for p in mine if p not in theirs)
    return changed, extra


def _dirty() -> list[str]:
    return git("status", "--porcelain", "--untracked-files=no").stdout.splitlines()


def _abort(why: str, paths: list[str]) -> int:
    git("merge", "--abort", check=False)
    print(f"sync_app: stopped, nothing changed. {why}")
    for p in paths[:30]:
        print(f"  {p}")
    if len(paths) > 30:
        print(f"  ... and {len(paths) - 30} more")
    return 1


def _changelog(old: str) -> list[str]:
    diff = git("diff", old, "HEAD", "--", "CHANGELOG.md", check=False).stdout
    return [ln[1:] for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]


def sync() -> int:
    dirty = _dirty()
    if dirty:
        print("sync_app: stopped, nothing changed. Commit or stash these first:")
        for ln in dirty[:20]:
            print(f"  {ln}")
        return 1
    base = merge_base()
    old = git("rev-parse", "HEAD").stdout.strip()
    behind = git("merge-base", "--is-ancestor", APP, "HEAD", check=False).returncode != 0
    if behind:
        incoming = (git("diff", "--name-only", "--no-renames", base, APP).stdout.split()
                    if base else git("ls-tree", "-r", "--name-only", "--full-tree", APP).stdout.split())
        bad = [p for p in incoming if is_personal(p)]
        if bad:
            print("sync_app: stopped, nothing changed. The app's commits touch personal paths, "
                  "which the app must never carry:")
            for p in bad[:30]:
                print(f"  {p}")
            return 1
        args = ["merge", "--no-ff", "--no-commit"]
        if base is None:
            args.append("--allow-unrelated-histories")
        git(*args, APP, check=False)
        conflicted = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        if any(is_personal(p) for p in conflicted):
            return _abort("A personal path conflicted:", [p for p in conflicted if is_personal(p)])
        theirs = _tree(APP)
        for p in conflicted:
            if p in theirs:
                git("checkout", APP, "--", p)
            else:
                git("rm", "-q", "--", p)
    # Drift: app-owned files that still differ from the app's, after the merge or
    # with nothing to merge, deleted ones included. Put back to the app's version.
    index = _index()
    restored = [p for p, v in _tree(APP).items()
                if not is_personal(p) and index.get(p) != v]
    for i in range(0, len(restored), 100):
        git("checkout", APP, "--", *restored[i:i + 100])
    if any(is_personal(p) for p in git("diff", "--cached", "--name-only").stdout.split()):
        return _abort("A personal path would change.", [
            p for p in git("diff", "--cached", "--name-only").stdout.split() if is_personal(p)])
    if not behind and not restored:
        _, extra = drift()
        print("sync_app: up to date with the app.")
        if extra:
            print(f"  {len(extra)} app-owned file(s) here that the app does not have (kept): "
                  + ", ".join(extra[:5]) + (" ..." if len(extra) > 5 else ""))
        return 0
    n = int(git("rev-list", "--count", f"{old}..{APP}").stdout.strip() or 0) if behind else 0
    title = (f"Sync from the app: {n} new commit(s)" if behind
             else f"Sync from the app: {len(restored)} app-owned file(s) put back")
    body = ""
    if restored:
        body = ("App-owned files edited here, put back to the app's version:\n"
                + "\n".join(f"- {p}" for p in restored))
    cmd = ["commit", "-q", "-m", title] + (["-m", body] if body else [])
    r = git(*cmd, check=False)
    if r.returncode != 0:
        return _abort("The commit failed: " + (r.stderr.strip() or r.stdout.strip()), [])
    print(f"sync_app: {title.split(': ', 1)[1]}.")
    if behind:
        print(git("diff", "--stat", "--stat-width=100", old, "HEAD").stdout.rstrip())
    for p in restored:
        print(f"  put back (edited here): {p}")
    new = _changelog(old)
    if new:
        print("What changed, from the app's CHANGELOG:")
        for ln in new[:12]:
            print(f"  {ln}")
    # Commands and skills are read from disk each time they run; these are read once, when
    # a chat starts, so a chat kept open for days would go on following the old copy.
    for p in ("CLAUDE.md", "AGENTS.md"):
        if git("diff", "--quiet", old, "HEAD", "--", p, check=False).returncode:
            print(f"{p} changed. A chat that was already open is still following the copy it "
                  f"read when it started: read {p} again now, before going on.")
    return 0


STAMP = "ljs-last-sync"


def _stamp_path() -> str | None:
    r = git("rev-parse", "--git-common-dir", check=False)
    d = r.stdout.strip()
    if r.returncode or not d:
        return None
    return os.path.join(d if os.path.isabs(d) else os.path.join(ROOT, d), STAMP)


def last_checked() -> str:
    """The date (YYYY-MM-DD) of the last successful sync here, or "" if none."""
    p = _stamp_path()
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read().strip()
    except (OSError, TypeError):
        return ""


def _record_check() -> None:
    p = _stamp_path()
    if p:
        try:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(datetime.date.today().isoformat() + "\n")
        except OSError:
            pass


def stale() -> bool:
    """True in a person's repo whose check has not run today. Never raises."""
    try:
        return not is_the_app() and last_checked() < datetime.date.today().isoformat()
    except Exception:  # a reminder must never break the tool that asked for it
        return False


def nudge() -> None:
    """One line on stderr when today's check has not run; for the tools a day's work starts with."""
    if stale():
        print("note: the app has not been checked for updates today. Run "
              "`python3 tools/sync_app.py --if-stale` first, then this again.", file=sys.stderr)


def pull_master() -> int:
    """A session's first step: bring in what other chats merged to master."""
    if git("fetch", "-q", "origin", "master", check=False).returncode:
        print("sync_app: master could not be fetched; carrying on with the app check.")
        return 0
    if git("merge-base", "--is-ancestor", "origin/master", "HEAD", check=False).returncode == 0:
        return 0
    if git("merge", "-q", "--no-edit", "origin/master", check=False).returncode:
        git("merge", "--abort", check=False)
        print("sync_app: stopped, nothing changed. master does not merge cleanly into this "
              "branch: run `git merge origin/master` and settle it (CLAUDE.md says how).")
        return 1
    print("sync_app: brought in master (what other chats merged).")
    return 0


def check() -> int:
    base = merge_base()
    if git("merge-base", "--is-ancestor", APP, "HEAD", check=False).returncode == 0:
        print("sync_app: up to date with the app.")
    elif base is None:
        print("sync_app: never synced. The first sync merges the app as unrelated history.")
    else:
        n = git("rev-list", "--count", f"HEAD..{APP}").stdout.strip()
        print(f"sync_app: {n} app commit(s) to bring in.")
    changed, extra = drift()
    if base is not None:
        # Behind is not drift: only files edited here since the last sync count.
        mine = set(git("diff", "--name-only", "--no-renames", base, "HEAD").stdout.split())
        changed = [p for p in changed if p in mine]
    print(f"  drift: {len(changed)} app-owned file(s) edited here"
          + (" (the next sync puts them back): " + ", ".join(changed[:8]) if changed else ""))
    if extra:
        print(f"  {len(extra)} app-owned file(s) here that the app does not have (kept)")
    return 0


def adopt() -> int:
    if merge_base() is not None:
        print("sync_app: already connected to the app; use a plain sync.")
        return 0
    changed, extra = drift()
    if changed or extra:
        print("sync_app: stopped, nothing changed. --adopt needs every app-owned file "
              "identical to the app's, and these are not:")
        for p in changed[:20]:
            print(f"  differs or missing here: {p}")
        for p in extra[:20]:
            print(f"  only here: {p}")
        return 1
    before = git("rev-parse", "HEAD^{tree}").stdout.strip()
    r = git("merge", "-q", "--allow-unrelated-histories", "-s", "ours", "-m",
            "Connect to the app: its history recorded as merged, no file changed", APP, check=False)
    if r.returncode != 0:
        return _abort("The merge failed: " + r.stderr.strip(), [])
    if git("rev-parse", "HEAD^{tree}").stdout.strip() != before:
        print("sync_app: the adopt merge changed the tree, which it must not; undo it with "
              "`git reset --hard HEAD^` before anything else.")
        return 1
    print("sync_app: connected. Every app-owned file was already the app's; from now on a "
          "sync brings only the app's new commits.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report only; change nothing")
    mode.add_argument("--adopt", action="store_true",
                      help="once, for the repo the app was built from")
    mode.add_argument("--if-stale", action="store_true",
                      help="master, then the app, unless today's check already ran")
    a = ap.parse_args(argv)
    if is_the_app():
        print("sync_app: this is the app itself; nothing to sync.")
        return 0
    if a.if_stale:
        if not stale():
            print("sync_app: already checked today.")
            return 0
        if _dirty():
            return sync()  # prints what is uncommitted and stops, changing nothing
        rc = pull_master()
        if rc:
            return rc
    err = fetch()
    if err:
        print(f"sync_app: {err}")
        return 2
    if not a.adopt:  # adopting compares against master, whatever the channel
        print(f"sync_app: {follow()}.")
    _APP_PORTALS[:] = [_regex(g) for g in app_portals()]
    if a.check:
        rc = check()
        upgrades("--list")
        return rc
    if a.adopt:
        return adopt()
    rc = sync()
    if rc == 0:
        _record_check()
        upgrades("--after-sync")
    return rc


def upgrades(mode: str) -> None:
    """The profile upgrades this repo still needs (tools/profile_upgrades.py).

    Run as its own process, from the file the merge just brought in: this
    sync_app is the copy that was on disk before the merge, so the registry it
    could import would be the old one. After a sync the instant upgrades run and
    commit on their own; a check only lists. Never changes the exit code: a
    pending upgrade must not block anything.
    """
    script = os.path.join(ROOT, "tools", "profile_upgrades.py")
    if not os.path.isfile(script):
        return
    try:
        r = subprocess.run([sys.executable, script] + ([] if mode == "--list" else [mode]),
                           cwd=ROOT, text=True, capture_output=True, timeout=600)
        out = (r.stdout or "").rstrip()
        if out:
            print(out)
        if r.returncode:
            print(f"profile upgrades: the check exited {r.returncode}: "
                  + ((r.stderr or "").strip().splitlines() or ["no error text"])[-1])
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"profile upgrades: could not be checked ({type(e).__name__})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
