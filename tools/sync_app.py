#!/usr/bin/env python3
"""Bring the app's updates into a person's repo. Nothing is ever sent back.

A person's repo is made from the app with "Use this template", so the two share
files but not history. This fetches the app and merges its new commits:

    python3 tools/sync_app.py            # fetch the app, merge what is new
    python3 tools/sync_app.py --check    # how far behind, and any drift; changes nothing
    python3 tools/sync_app.py --adopt    # once, for the repo the app was first built from
    python3 tools/sync_app.py --if-stale # the day's first check: master, then the app; else nothing
    ... --on "<model>"                   # with either: the day's model check after the sync
    ... --tools "<browser,chrome,enable or none>"   # the place check, once and then weekly

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

# A cloud session sets CLAUDE_CODE_REMOTE; anything else is a person's own computer.
CLOUD = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"

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


def headlines(lines: list[str]) -> list[str]:
    """One line per new CHANGELOG entry, its bold headline, so a sync that brings a whole
    release names every change rather than the first entry's opening lines. Lines that
    start no entry (a heading, a reworded line inside an old entry) are left out; with no
    entry at all, the lines themselves."""
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("- "):
            m = re.match(r"- \*\*(.+?)\*\*", s)
            out.append(m.group(1).strip() if m else s[2:])
    return out or lines


def sync() -> int:
    dirty = _dirty()
    if dirty:
        print("sync_app: stopped, nothing changed. Commit or stash these first:")
        for ln in dirty[:20]:
            print(f"  {ln}")
        if not CLOUD:
            print("  If another chat works in this folder, these are its files: never commit or "
                  "discard them from here. Give this chat a folder of its own instead: "
                  "python3 tools/sync_app.py --worktree <a short name for this chat>")
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
    title = (f"{SYNC_SUBJECT}: {n} new commit(s)" if behind
             else f"{SYNC_SUBJECT}: {len(restored)} app-owned file(s) put back")
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
    new = headlines(_changelog(old))
    if new:
        print("What changed, from the app's CHANGELOG:")
        for ln in new[:20]:
            print(f"  - {ln}")
        if len(new) > 20:
            print(f"  ... and {len(new) - 20} more (CHANGELOG.md)")
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
              "`python3 tools/sync_app.py --if-stale --on \"<this session's model>\"` first, then "
              "this again.", file=sys.stderr)


def rewritten(old: str, new: str) -> bool:
    """Did origin/master move to a commit that does not contain where it was: a history
    rewrite, which git fetch prints as "(forced update)"?"""
    return bool(old and new and old != new) and git(
        "merge-base", "--is-ancestor", old, new, check=False).returncode != 0


def after_rewrite(old: str) -> int:
    """origin/master was rewritten. Merging it into a checkout made before conflicts on
    hundreds of files, and a person had to warn the session in their own prompt. A branch
    holding nothing beyond the old master moves to the new one; a branch with commits of its
    own is left alone, with those commits named and the way to carry them across."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    mine = git("rev-list", "--reverse", "HEAD", "--not", old, "origin/master",
               check=False).stdout.split()
    if not mine:
        moved = (git("checkout", "-q", "-B", branch, "origin/master", check=False)
                 if branch and branch != "HEAD"
                 else git("checkout", "-q", "--detach", "origin/master", check=False))
        if moved.returncode:
            # Never "nothing was lost" when nothing moved: files in the way stop the checkout.
            in_way = [ln.strip() for ln in moved.stderr.splitlines() if ln.startswith(("\t", "  "))]
            return _abort("master's history was rewritten (a forced update), and moving this "
                          "branch onto the new master was refused: these files are in the way. "
                          "Commit or move them, then run the sync again:", in_way or
                          [moved.stderr.strip()[:300]])
        print("sync_app: master's history was rewritten (a forced update). This branch held "
              "nothing of its own, so it now starts from the new master; nothing was lost.")
        return 0
    print(f"sync_app: stopped, nothing changed. master's history was rewritten (a forced update), "
          f"and this branch has {len(mine)} commit(s) of its own. Do not merge: carry them onto "
          "the new master instead, then sync again:")
    print(f"  git switch -c {branch or 'work'}-rebased origin/master && git cherry-pick "
          + " ".join(c[:12] for c in mine))
    return 1


def abandoned(before: str, now: str) -> str:
    """A commit this checkout is built on that origin/master no longer contains, or "".

    That is what a history rewrite leaves behind, however it was fetched: by this sync, or
    by hand before it, and then perhaps fast-forwarded again. Every value origin/master has
    held is in its reflog; one this branch contains and the new master does not is the old
    history. A branch already on the new master contains none of them."""
    # The reflog file itself: each line holds the value before and after one update, and
    # the value before the first update (the one a fresh clone started from) is in no
    # entry `git reflog` prints.
    log = git("rev-parse", "--git-path", "logs/refs/remotes/origin/master",
              check=False).stdout.strip()
    try:
        with open(log if os.path.isabs(log) else os.path.join(ROOT, log), encoding="utf-8",
                  errors="replace") as fh:
            values = [h for line in fh.readlines()[-200:] for h in line.split()[:2]]
    except OSError:
        values = []
    seen = [before] + values[::-1]
    for old in dict.fromkeys(h for h in seen if h and h != now):
        if rewritten(old, now) and git("merge-base", "--is-ancestor", old, "HEAD",
                                       check=False).returncode == 0:
            return old
    return ""


def pull_master() -> int:
    """A session's first step: bring in what other chats merged to master."""
    before = git("rev-parse", "-q", "--verify", "refs/remotes/origin/master", check=False).stdout.strip()
    if git("fetch", "-q", "origin", "master", check=False).returncode:
        print("sync_app: master could not be fetched; carrying on with the app check.")
        return 0
    now = git("rev-parse", "-q", "--verify", "refs/remotes/origin/master", check=False).stdout.strip()
    old = abandoned(before, now)
    if old:
        return after_rewrite(old)
    if git("merge-base", "--is-ancestor", "origin/master", "HEAD", check=False).returncode == 0:
        return 0
    dirty = _dirty()
    if dirty:
        print("sync_app: stopped, nothing changed. There are uncommitted changes, so master "
              "was not merged in; commit them (or set them aside), then run this again:")
        for line in dirty[:20]:
            print("  " + line)
        return 1
    if git("merge", "-q", "--no-edit", "origin/master", check=False).returncode:
        git("merge", "--abort", check=False)
        print("sync_app: stopped, nothing changed. master does not merge cleanly into this "
              "branch: run `git merge origin/master` and settle it (CLAUDE.md says how).")
        return 1
    print("sync_app: brought in master (what other chats merged).")
    return 0


def branch_name(name: str, today: datetime.date | None = None) -> str:
    """chat/<name>-<date>, with -2, -3 and on when that branch is already here or on
    origin: a stale local branch with the day's name already existed once."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "chat").lower()).strip("-") or "chat"
    base = f"chat/{slug}-{(today or datetime.date.today()).strftime('%Y%m%d')}"
    taken = set(git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                    "refs/remotes/origin", check=False).stdout.split())
    taken |= {t.split("/", 1)[1] for t in list(taken) if t.startswith("origin/")}
    out, n = base, 1
    while out in taken:
        n += 1
        out = f"{base}-{n}"
    return out


def worktree(name: str) -> int:
    """A folder of this chat's own: ../<repo>-<name>, on a new branch from origin/master.

    Two chats on one computer shared one folder, with the other chat's branch checked
    out: a branch switch by one changes the other's files under it, and they fight over
    git's index. Each local chat works in its own worktree and removes it when its pull
    request lands (`git worktree remove <folder>`). Files git does not carry (the
    connections export) are read from the main folder (person.local_state)."""
    if git("fetch", "-q", "origin", "master", check=False).returncode:
        print("sync_app: master could not be fetched; no worktree made.")
        return 1
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-") or "chat"
    folder = os.path.join(os.path.dirname(ROOT), f"{os.path.basename(ROOT)}-{slug}")
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(os.path.dirname(ROOT), f"{os.path.basename(ROOT)}-{slug}-{n}")
    branch = branch_name(slug)
    r = git("worktree", "add", "-q", "-b", branch, folder, "origin/master", check=False)
    if r.returncode:
        print(f"sync_app: no worktree made: {(r.stderr or r.stdout).strip()[:200]}")
        return 1
    print(f"sync_app: this chat's own folder is {folder}, on branch {branch}, from master. "
          "Work there from now on (every command run in it); when its pull request lands: "
          f"git worktree remove {folder}")
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
    mode.add_argument("--own-tests", action="store_true",
                      help="which of the person's own tests fail on this tree, and what to do")
    mode.add_argument("--own-test-risks", action="store_true",
                      help="the person's own tests that reach into private parts of the app")
    mode.add_argument("--pull", action="store_true",
                      help="a session's first step: bring in master, and never merge a "
                           "rewritten one")
    mode.add_argument("--worktree", metavar="NAME",
                      help="a folder of this chat's own, beside the repo, on a new branch from "
                           "master: for a second chat on the same computer")
    ap.add_argument("--on", default="", metavar="MODEL",
                    help="the model this session runs on: the day's work is checked against it")
    ap.add_argument("--tools", default=None, metavar="LIST",
                    help="the browser tools this chat has (browser, chrome, chrome-off, enable, "
                         "none): the place check says what to do, once and then weekly")
    a = ap.parse_args(argv)
    if a.own_tests:
        failures = own_test_failures()
        text = own_tests_report(failures or [])
        print(text or ("Your own tests pass on this tree." if failures == [] else
                       "Your own tests could not be run."))
        risk = own_test_risks_report(own_test_risks())
        if risk:
            print(risk)
        return 1 if failures else 0
    if a.own_test_risks:
        risk = own_test_risks_report(own_test_risks())
        if risk:
            print(risk)
        return 0
    if a.worktree:
        return worktree(a.worktree)
    if a.pull:
        return pull_master()
    if is_the_app():
        print("sync_app: this is the app itself; nothing to sync.")
        return 0
    if a.if_stale:
        if not stale():
            print("sync_app: already checked today.")
            place_check(a.tools)    # a new chat on a day already checked still hears it once
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
    before = git("rev-parse", "HEAD", check=False).stdout.strip()
    rc = sync()
    if rc == 0:
        _record_check()
        if git("rev-parse", "HEAD", check=False).stdout.strip() != before:
            own_tests()
        app_watch()
        upgrades("--after-sync")
        model_check(a.on)
        place_check(a.tools)
    return rc


# A failure that names a part of the app no longer there: the test pinned how the app
# was built, not what it does for the person.
_GONE = (re.compile(r"AttributeError: module '([\w.]+)' has no attribute '(\w+)'"),
         re.compile(r"ImportError: cannot import name '(\w+)' from '([\w.]+)'"),
         re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'"),
         # mock.patch's own wording for a name that is not there to patch
         re.compile(r"AttributeError: <module '([\w.]+)' from [^>]*> does not have the attribute '(\w+)'"))


def _app_module(root: str, name: str) -> bool:
    """Is `name` one of the app's modules (tools/<name>.py, or a package there)?"""
    path = os.path.join(root, "tools", *name.split("."))
    return os.path.isfile(path + ".py") or os.path.isdir(path) or name.split(".")[0] == "openroles"


def _gone(root: str, message: str) -> str:
    """"module.name" when a failure names a part of the app the update removed, else ""."""
    for n, rx in enumerate(_GONE):
        m = rx.search(message or "")
        if not m:
            continue
        module, name = ((m.group(2), m.group(1)) if n == 1 else
                        (m.group(1), "") if n == 2 else (m.group(1), m.group(2)))
        if _app_module(root, module) or (n == 2 and module.split(".")[0] == "openroles"):
            return f"{module}.{name}" if name else module
    return ""


def own_test_failures(root: str | None = None) -> list[tuple[str, str]] | None:
    """[(test, failure message)] for the person's own tests (profile/tests) that fail on
    this tree, or None when there are none to run or they could not be run."""
    import tempfile
    import xml.etree.ElementTree as ET
    root = root or ROOT
    tests = os.path.join(root, "profile", "tests")
    if not os.path.isdir(tests):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.xml")
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "--tb=no", f"--junitxml={report}", tests], cwd=root, text=True,
                               capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 1 or not os.path.isfile(report):   # 0 clean; 5 none collected
            return [] if r.returncode in (0, 5) else None
        out = []
        for case in ET.parse(report).iter("testcase"):
            bad = case.find("failure")
            if bad is None:
                bad = case.find("error")
            if bad is not None:
                name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
                out.append((name, bad.get("message") or (bad.text or "")[:300]))
        return out


# What the person is asked before any of their own tests is deleted, in words for someone
# who has never seen a test, with the answer recommended. "Retire 57 tests?" was answerable
# by a developer and nobody else.
ASK_TIDY = ("Some self-checks in your setup are out of date after this update. Clear them "
            "out? Nothing about your job search changes.")
ASK_ANSWERS = ("Yes (recommended)", "Not now")
TIDY_MEANS = ("They check that your setup works. A few were written for the old version, so "
              "they now fail even though nothing is wrong. Clearing them out deletes those and "
              "updates the rest. Your profile, applications, contacts and documents are not "
              "touched.")
TIDY_YES = "Done: your setup is on the new version."
TIDY_NO = ("No problem. Your setup stays on the version before until you say yes, and "
           "nothing breaks meanwhile.")


def own_tests_report(failures: list[tuple[str, str]], root: str | None = None) -> str:
    """What the sync says about the person's own tests the update broke, or ""."""
    if not failures:
        return ""
    root = root or ROOT
    gone: dict[str, int] = {}
    changed = []
    for name, message in failures:
        part = _gone(root, message)
        if part:
            gone[part] = gone.get(part, 0) + 1
        else:
            changed.append(name)
    lines = [f"Your own tests: {len(failures)} now fail after this update."]
    if gone:
        n = sum(gone.values())
        parts = ", ".join(f"{k} ({v})" for k, v in sorted(gone.items(), key=lambda x: -x[1])[:6])
        lines.append(f"  {n} use parts of the app this update removed: {parts}. What they checked "
                     "moved, and the app's own tests cover the app's behaviour. Rewrite each that "
                     "pins the person's own data through the app's public names (a job board "
                     "through tools/offline_boards.py), and retire the rest.")
    if changed:
        lines.append(f"  {len(changed)} check behaviour the update changed: "
                     + "; ".join(changed[:6]) + (f"; and {len(changed) - 6} more" if len(changed) > 6 else "")
                     + ". Bring each in line with the CHANGELOG, or report it to the app if the "
                     "change looks wrong.")
    if gone:
        lines.append("Claude: they are the person's files, so ask before deleting any. Ask "
                     f"once, in these words: \"{ASK_TIDY}\" Offer two answers, "
                     f"\"{ASK_ANSWERS[0]}\" first and \"{ASK_ANSWERS[1]}\" (as buttons where "
                     f"you can). If they ask what it means: \"{TIDY_MEANS}\" On yes, clear them "
                     f"out and say \"{TIDY_YES}\" On no, say \"{TIDY_NO}\" Either way, name in "
                     "the PR which you deleted and which you rewrote.")
    else:
        lines.append("Claude: none needs deleting, so there is nothing to ask the person: bring "
                     "each in line, and name them in the PR.")
    lines.append("`python3 tools/sync_app.py --own-tests` says this again at any time.")
    return "\n".join(lines)


def own_test_risks(root: str | None = None) -> dict[str, list[str]]:
    """{test file: ["module._name", ...]} for the person's own tests that reach into a
    private part of the app: a name starting with an underscore on one of the app's
    modules, imported, read, or patched by name. They pass today and break the day the
    app changes that part, which is what 3.5.0 did to dozens of them at once."""
    import ast
    root = root or ROOT
    tests = os.path.join(root, "profile", "tests")
    out: dict[str, list[str]] = {}
    if not os.path.isdir(tests):
        return out

    def private(name: str) -> bool:
        return name.startswith("_") and not name.startswith("__")

    for base, _dirs, files in os.walk(tests):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(base, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (OSError, SyntaxError, ValueError):
                continue
            alias: dict[str, str] = {}
            found: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if _app_module(root, a.name):
                            alias[(a.asname or a.name).split(".")[0]] = a.name
                            if any(private(part) for part in a.name.split(".")):
                                found.append(a.name)
                elif isinstance(node, ast.ImportFrom) and node.module and _app_module(root, node.module):
                    for a in node.names:
                        if private(a.name) or any(private(p) for p in node.module.split(".")):
                            found.append(f"{node.module}.{a.name}")
                        elif _app_module(root, f"{node.module}.{a.name}"):
                            alias[a.asname or a.name] = f"{node.module}.{a.name}"
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id in alias and private(node.attr)):
                    found.append(f"{alias[node.value.id]}.{node.attr}")
                elif isinstance(node, ast.Call):
                    args = node.args
                    # mock.patch("module._name") and mock.patch.object(module, "_name")
                    if (args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)
                            and "." in args[0].value):
                        mod, _, name = args[0].value.rpartition(".")
                        if _app_module(root, mod) and private(name):
                            found.append(args[0].value)
                    if (len(args) > 1 and isinstance(args[0], ast.Name) and args[0].id in alias
                            and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str)
                            and private(args[1].value)):
                        found.append(f"{alias[args[0].id]}.{args[1].value}")
            if found:
                out[os.path.relpath(path, root)] = sorted(set(found))
    return out


def own_test_risks_report(risks: dict[str, list[str]]) -> str:
    """One note for the person's tests that will break when the app changes a private part."""
    if not risks:
        return ""
    names = sorted({n for v in risks.values() for n in v})
    return (f"Note: {len(risks)} of your own test file(s) reach into private parts of the app "
            f"({', '.join(names[:5])}{', ...' if len(names) > 5 else ''}): they pass now and break "
            "when the app changes those parts. Claude: when next working in these files, move them "
            "onto public names (a job board through tools/offline_boards.py), keeping every "
            "assertion: " + "; ".join(sorted(risks)[:4]) + ("; ..." if len(risks) > 4 else ""))


# In the repository's .git, never committed: the sync commit the person's own tests last
# ran on, so they run once for each update whichever copy of this file brought it.
OWN_TESTS_MARK = "ljs_own_tests_ran_on"
SYNC_SUBJECT = "Sync from the app"


def _git_out(root: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _mark_path(root: str) -> str:
    gd = _git_out(root, "rev-parse", "--git-dir")
    return os.path.join(root, gd, OWN_TESTS_MARK) if gd and not os.path.isabs(gd) else (
        os.path.join(gd, OWN_TESTS_MARK) if gd else "")


def own_tests(root: str | None = None) -> None:
    """After an update lands, the person's own tests (profile/tests), which may have pinned
    how the app worked before: each that now fails is named with why, never left for the
    next ci_local.sh run to find. A person's copy of an old discovery test asserted the
    old search shape for days after the app changed it, and when 3.5.0 moved the employer
    boards into openroles, the maintainer's own tests failed by the dozen on names it
    removed and the sync said nothing, because the copy of this file that ran the sync
    predated the check."""
    root = root or ROOT
    text = own_tests_report(own_test_failures(root) or [], root)
    if text:
        print(text)
    mark = _mark_path(root)
    if mark:
        try:
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(_git_out(root, "rev-parse", "HEAD"))
        except OSError:
            pass


def own_tests_after_sync(root: str | None = None) -> None:
    """The own-tests check for a sync whose copy of this file is older than the check:
    `profile_upgrades.py --after-sync` is always the copy the sync just brought in, so it
    calls this, and it runs once for the sync commit at HEAD."""
    root = root or ROOT
    if not _git_out(root, "log", "-1", "--format=%s").startswith(SYNC_SUBJECT):
        return
    mark = _mark_path(root)
    head = _git_out(root, "rev-parse", "HEAD")
    try:
        with open(mark, encoding="utf-8") as fh:
            if fh.read().strip() == head:
                return
    except OSError:
        pass
    own_tests(root)


def app_watch() -> None:
    """In the maintainer's own repo only: the public app checked for this repo's names
    (tools/app_watch.py), once a day with the sync. Anyone else's repo prints nothing.
    A finding goes first in the reply; it never changes the sync's exit code."""
    script = os.path.join(ROOT, "tools", "app_watch.py")
    if not os.path.isfile(script):
        return
    try:
        r = subprocess.run([sys.executable, script], cwd=ROOT, text=True,
                           capture_output=True, timeout=300)
        if (r.stdout or "").strip():
            print(r.stdout.rstrip())
    except (OSError, subprocess.TimeoutExpired):
        print("App watch: did not finish in five minutes; the next sync tries again.")


def place_check(tools: str | None) -> None:
    """Is this chat the right place for what the person set up (tools/place.py)?

    Said once, then weekly while it applies, whatever chat it is: run as its own process from the file
    the merge just brought in, like the model check, so it reaches a chat whose
    instructions were loaded before it existed. Never changes a setting.
    """
    script = os.path.join(ROOT, "tools", "place.py")
    if not os.path.isfile(script) or not os.path.isdir(os.path.join(ROOT, "profile")):
        return
    argv = [sys.executable, script, "check", "--once"]
    if tools is not None:
        argv += ["--tools", tools]
    try:
        r = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60)
        out = (r.stdout or "").strip()
        if out and not out.startswith("place: this chat is the right place"):
            print(out)
    except (OSError, subprocess.TimeoutExpired):
        pass


def model_check(on: str) -> None:
    """The day's model check (tools/model_guide.py), once a day with the day's sync.

    A script cannot see which model a session runs on, and a line in CLAUDE.md asking
    for the check was skipped, so it rides on the command every session runs. Run as
    its own process, from the file the merge just brought in, like the upgrades.
    """
    script = os.path.join(ROOT, "tools", "model_guide.py")
    if not os.path.isfile(script):
        return
    if not on.strip():
        print('Model check: Claude, add --on "<the model this session runs on>" to this '
              "command and the day's work is checked against it.")
        return
    try:
        r = subprocess.run([sys.executable, script, "--on", on], cwd=ROOT, text=True,
                           capture_output=True, timeout=60)
        if (r.stdout or "").strip():
            print(r.stdout.rstrip())
    except (OSError, subprocess.TimeoutExpired):
        pass


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
