#!/usr/bin/env python3
"""Bring the app's updates into a person's repo. Nothing is ever sent back.

A person's repo is made from the app with "Use this template", so the two share
files but not history. This fetches the app and merges its new commits:

    python3 tools/sync_app.py            # fetch the app, merge what is new
    python3 tools/sync_app.py --update   # the same whatever the setting below: the person said so
    python3 tools/sync_app.py --check    # how far behind, and any drift; changes nothing
    python3 tools/sync_app.py --adopt    # once, for the repo the app was first built from
    python3 tools/sync_app.py --if-stale # the day's first check: master, then the app; else nothing
    ... --on "<model>"                   # with any of them: the day's model check after the sync
    ... --tools "<browser,chrome,enable or none>"   # the place check, once in a chat

Updates arrive by themselves: that is the default, and what nearly everyone wants. A person
who would rather choose when has `"app_updates": "when_asked"` in profile/person.json (their
own setting, never the app's). Then a plain run and --if-stale only look: they fetch the
app read-only, change nothing of it, and when a newer version is waiting print one line for
the person, once for that version ("An update is waiting: <what it brings>. Say "update"
when you want it."). --update takes it, and only their word runs that.

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
  reported. A look (when_asked) reports drift and puts nothing back.
- A sync never takes a repo back to an older version than it holds: drift is
  measured against the newest app commit already here.
- Uncommitted changes stop it before anything happens. Anything the merge
  cannot settle aborts it and leaves the repo exactly as it was.
- In the app itself, a no-op.
- After every sync and every look, "up to date" included, it lists the profile upgrades
  this repo still needs and runs the instant ones (`tools/profile_upgrades.py`): those of
  the version it holds, so an update not yet taken brings none.

The first sync of a template-made repo has no common commit, so it merges with
--allow-unrelated-histories: identical files merge clean, and an app-owned file
that differs takes the app's version.

--if-stale is for a chat that carries on for days, which is how most people use it: the
start-of-session steps never run again in one, so updates would wait for a new chat that
never comes. It does what a session's first two steps do (bring master in, then sync)
unless they already ran today, which a stamp in the git directory records, and otherwise
prints one line and does nothing. Every successful sync and look writes that stamp.
`run_round.py` and `stage_picks.py` print a reminder when today's check has not run.

--adopt is for the one repo whose app-owned files ARE the app, the private repo
the app's first commit was built from. It checks that every app-owned file is
byte-identical to the app's, then records the app's history as merged without
changing a file (`git merge -s ours`), so later syncs bring only new app commits.

The app's address lives here, in an app-owned file, so a change to it reaches
everyone on their next sync. LJS_APP_URL overrides it (the tests point it at a
local repository).

Exit: 0 synced, looked or up to date, 1 stopped (uncommitted changes, a conflict, or
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
TAG = ""  # the release APP names, when it names one (follow())
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


# How long one git command may take. A fetch on a slow connection takes a while, but one
# that hangs (a sign-in window nobody sees, a network that never answers) must not hold the
# chat for ever; ten minutes is far beyond any fetch this repo has made.
GIT_TIMEOUT = 600
NO_GIT = ("sync_app: git is not installed on this computer, so nothing was changed. "
          "python3 tools/env_check.py says how to put it on.")


def _git_env() -> dict:
    """Git never stops to ask anyone anything: no password prompt in the terminal
    (GIT_TERMINAL_PROMPT, https://git-scm.com/docs/git#Documentation/git.txt-GITTERMINALPROMPT)
    and no sign-in window from Git Credential Manager, which Git for Windows ships
    (GCM_INTERACTIVE, https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/environment.md).
    A sync runs in the background of a chat, where a prompt is a hang."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env


def run_git(root: str, *args: str, check: bool = False,
            timeout: float = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """git -C root <args>, its output read as UTF-8 whatever the computer's own encoding
    (Windows reads cp1252 by default, and a CHANGELOG name with an accent stopped the sync
    after its commit), never prompting, never hanging. Missing git ends the run with one
    plain line from main(), not a traceback: here it is an ordinary failure (exit 127), so
    the helpers other tools call (stale(), behind_sync()) never stop them; a timeout is one
    too (exit 124)."""
    cmd = ["git", "-C", root, *args]
    try:
        r = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8",
                           errors="replace", env=_git_env(), timeout=timeout)
    except OSError:
        r = subprocess.CompletedProcess(cmd, 127, "", NO_GIT)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(cmd, 124, "", f"git {args[0] if args else ''} took "
                                        f"longer than {int(timeout)} seconds and was stopped")
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)
    return r


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_git(ROOT, *args, check=check)


def _git_error(r: subprocess.CompletedProcess) -> str:
    """git's own reason, in one line: its first "fatal:" or "error:" line, which says what
    went wrong (the last line of a failed fetch is only "and the repository exists.")."""
    lines = [ln.strip() for ln in (r.stderr or r.stdout or "").splitlines() if ln.strip()]
    said = next((ln for ln in lines if ln.lower().startswith(("fatal:", "error:"))),
                lines[-1] if lines else "no error text")
    return said[:200]


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


def is_the_app(root: str | None = None) -> bool:
    origin = run_git(root or ROOT, "remote", "get-url", "origin")
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
    # A cloud container may reach GitHub through a local proxy, whose address carries the
    # owner after a "git" segment: http://<the proxy's host and port>/git/<owner>/<repo>.
    m = re.match(r"^https?://[^/]+/(?:git/(?=[^/]+/[^/]+/))?([^/]+)/", _norm(url) + "/")
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
    return "master" if maintainers() else "stable"


def updates() -> str:
    """"auto" (the default) or "when_asked", from `"app_updates"` in profile/person.json.

    Updates arrive by themselves for everyone unless their own profile says they wait for
    their word: the maintainer asked for that in their own repos and nowhere else
    (2026-10-25). The app and the example person never set it."""
    try:
        with open(os.path.join(ROOT, "profile", "person.json"), encoding="utf-8") as fh:
            chosen = str(json.load(fh).get("app_updates") or "").strip().lower()
        if chosen == "when_asked":
            return chosen
    except (OSError, ValueError, AttributeError):
        pass
    return "auto"


def maintainers() -> bool:
    """Is this the app maintainer's own repo (its GitHub owner is the app's)? Only there
    is the sync's git detail and the maintainer's own news worth printing."""
    origin = git("remote", "get-url", "origin", check=False)
    mine = _owner(origin.stdout) if origin.returncode == 0 else ""
    return bool(mine) and mine == _owner(app_url())


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
    global APP, TAG
    APP, TAG = MASTER, ""
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
    APP, TAG = STABLE, tag
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


def installed() -> str | None:
    """The newest app commit this repo holds, or None if it never synced: the version its
    app-owned files should match. On releases that is usually the release it took, but a
    first sync takes master, which is newer than the release before it: measured against
    that release, every file changed since read as edited here, and the next sync put the
    person back to the older release and called it their edit (2026-10-25)."""
    base = merge_base()              # deepens a shallow clone until the last sync turns up
    if base is None:
        return None
    r = git("merge-base", "HEAD", MASTER, check=False)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else base


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


def drift(ref: str = "HEAD", app: str | None = None) -> tuple[list[str], list[str]]:
    """App-owned files at ref that differ from the app's at `app` (APP by default), and
    ones the app lacks."""
    mine = {p: v for p, v in _tree(ref).items() if not is_personal(p)}
    theirs = _tree(app or APP)
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


def _refused(r: subprocess.CompletedProcess) -> int:
    """Git would not start the merge at all (no MERGE_HEAD): most often a file here that is
    not saved yet sits where the update brings one. Carrying on put the app's file over
    theirs and committed a plain commit that recorded no merge (2026-10-25). Nothing has
    changed at this point, so the stop names their files and git's own reason."""
    said = (r.stderr or "") + "\n" + (r.stdout or "")
    paths = [ln.strip() for ln in said.splitlines() if ln.startswith("\t") and ln.strip()]
    if paths:
        print("sync_app: stopped, nothing changed. These files here are not saved yet, and "
              "the update brings a file of the same name: save them under another name or "
              "move them out of the way, then run this again:")
        for p in paths[:30]:
            print(f"  {p}")
        return 1
    print(f"sync_app: stopped, nothing changed. Git would not take the update: {_git_error(r)}")
    return 1


def _changelog(old: str) -> list[str]:
    diff = git("diff", old, "HEAD", "--", "CHANGELOG.md", check=False).stdout
    return [ln[1:] for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]


def headlines(lines: list[str], maintainer: bool = True) -> list[str]:
    """One line per new CHANGELOG entry, its bold headline, so a sync that brings a whole
    release names every change rather than the first entry's opening lines. Lines that
    start no entry (a heading, a reworded line inside an old entry) are left out; with no
    entry at all, the lines themselves. A headline that runs onto the next line is read
    whole: one printed as "**A contact who shares a first name with the app's" (2026-10-22).

    For anyone but the maintainer, an entry about the maintainer's own tools, or one headed
    by a tool's name, is left out: the chat passes these lines on, and a person was told
    about pull requests and a `--probe` option (2026-10-22)."""
    entries: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("- "):
            entries.append(s)
        elif entries and ln[:1].isspace() and s and not s.startswith(("#", "- ")):
            entries[-1] += " " + s
    out = []
    for e in entries:
        m = re.match(r"- \*\*(.+?)\*\*", e)
        head = " ".join((m.group(1) if m else e[2:]).split()).strip()
        if not maintainer and (head.startswith("`") or "maintainer" in e[:240].lower()):
            continue
        out.append(head)
    return out if entries else lines


def _stop_dirty(dirty: list[str]) -> int:
    print("sync_app: stopped, nothing changed. Commit or stash these first:")
    for ln in dirty[:20]:
        print(f"  {ln}")
    if not CLOUD:
        print("  If another chat works in this folder, these are its files: never commit or "
              "discard them from here. Give this chat a folder of its own instead: "
              "python3 tools/sync_app.py --worktree <a short name for this chat>")
    return 1


def sync() -> int:
    """The update: the app's waiting commits merged in. Every run takes it by default; where
    the person's profile says updates wait for their word, only --update does."""
    dirty = _dirty()
    if dirty:
        return _stop_dirty(dirty)
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
        r = git(*args, APP, check=False)
        if r.returncode and git("rev-parse", "-q", "--verify", "MERGE_HEAD",
                                check=False).returncode:
            return _refused(r)
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
    # with nothing to merge, deleted ones included. Put back to the app's version: the one
    # just merged, or with nothing to merge the one this repo already holds, never an older
    # release than that.
    ref = APP if behind else (installed() or APP)
    index = _index()
    restored = [p for p, v in _tree(ref).items()
                if not is_personal(p) and index.get(p) != v]
    for i in range(0, len(restored), 100):
        git("checkout", ref, "--", *restored[i:i + 100])
    if any(is_personal(p) for p in git("diff", "--cached", "--name-only").stdout.split()):
        return _abort("A personal path would change.", [
            p for p in git("diff", "--cached", "--name-only").stdout.split() if is_personal(p)])
    if not behind and not restored:
        _, extra = drift(app=ref)
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
    mine = maintainers()
    if behind and mine:
        print(git("diff", "--stat", "--stat-width=100", old, "HEAD").stdout.rstrip())
    for p in restored:
        print(f"  put back (edited here): {p}")
    # Nothing to tell someone who has not set up yet: their first sync's CHANGELOG is every
    # change the app ever made, twenty headlines about things they never used.
    new = (headlines(_changelog(old), maintainer=mine)
           if os.path.isdir(os.path.join(ROOT, "profile")) else [])
    if new:
        print("What changed (for the person, in one plain line):")
        for ln in new[:20]:
            print(f"  - {ln}")
        if len(new) > 20:
            print(f"  ... and {len(new) - 20} more (CHANGELOG.md)")
    # Commands and skills are read from disk each time they run; these are read once, when
    # a chat starts, so a chat kept open for days would go on following the old copy.
    for p in ("CLAUDE.md", "AGENTS.md"):
        if git("diff", "--quiet", old, "HEAD", "--", p, check=False).returncode:
            print(f"Claude: {p} changed. A chat that was already open is still following the "
                  f"copy it read when it started: read {p} again now, before going on.")
    return 0


STAMP = "ljs-last-sync"


def _git_dirs(root: str) -> tuple[str, str] | None:
    """(this checkout's own git folder, the folder every worktree of the repo shares), both
    absolute; the same folder in the repo's main checkout. None outside git."""
    r = run_git(root, "rev-parse", "--absolute-git-dir", "--git-common-dir")
    got = r.stdout.split("\n")
    if r.returncode or len(got) < 2 or not got[0].strip() or not got[1].strip():
        return None
    own, common = got[0].strip(), got[1].strip()
    return own, common if os.path.isabs(common) else os.path.normpath(os.path.join(root, common))


def _stamp_path(root: str | None = None) -> str | None:
    """Where this checkout keeps the day's check: its own git folder. Each worktree, a second
    chat on the same computer in a folder of its own, keeps its own record: one shared by all
    of them told a chat that had taken an update it was older than another chat's sync of
    the same update, and its own --if-stale that another chat's check was its own
    (2026-10-21). In the main checkout this is the folder every worktree shares, as before."""
    dirs = _git_dirs(root or ROOT)
    return os.path.join(dirs[0], STAMP) if dirs else None


def _stamp_line() -> str:
    p = _stamp_path()
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read().strip()
    except (OSError, TypeError):
        return ""


def last_checked() -> str:
    """The date (YYYY-MM-DD) of the last successful sync in this checkout, or "" if none."""
    got = _stamp_line().split()
    return got[0] if got else ""


def _day_line(now: datetime.datetime | None = None) -> str:
    """The day's check as written: the date, and the UTC offset of the clock it was read
    from ("2026-10-26 +1100"). In a cloud chat person.py sets the person's own zone, so
    profile_upgrades.py writes their date while sync_app's own process reads the cloud
    computer's UTC one; stamped with its offset, the day is read back by the clock that
    wrote it, whichever process asks (2026-10-25)."""
    now = now or datetime.datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %z").strip()


def _stale_day(line: str, now: datetime.datetime | None = None) -> bool:
    """Is the day in `line` (as _day_line writes it) earlier than today, by the clock it was
    written in? A date with no offset (an older copy wrote it) is read in this computer's
    own day."""
    got = line.split()
    if not got:
        return True
    now = now or datetime.datetime.now().astimezone()
    m = re.fullmatch(r"([+-])(\d\d)(\d\d)", got[1]) if len(got) > 1 else None
    if m:
        off = datetime.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
        today = now.astimezone(datetime.timezone(-off if m.group(1) == "-" else off)).date()
    else:
        today = now.astimezone().date() if now.tzinfo else now.date()
    return got[0] < today.isoformat()


def _record_check(root: str | None = None) -> None:
    """The day's check, recorded in the repo the sync ran in. Never in the app itself, which
    takes no updates: there the record only came from its own tests, written into the git
    folder every worktree shares, and told the other worktrees they were behind."""
    root = root or ROOT
    if is_the_app(root):
        return
    p = _stamp_path(root)
    if p:
        try:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(_day_line() + "\n")
            # The commit the sync left this checkout on, and the app commit it took: an
            # /upgrade worktree made from an older commit lists the wrong upgrades, and
            # `behind_sync()` says so instead.
            def g(*args):
                return run_git(root, *args).stdout.strip()
            head = g("rev-parse", "HEAD")
            app = g("rev-parse", "--verify", "-q", APP + "^{commit}")
            if app and run_git(root, "merge-base", "--is-ancestor", app, "HEAD").returncode:
                app = ""
            if head:
                with open(p + "-head", "w", encoding="utf-8") as fh:
                    fh.write(head + "\n" + (app + "\n" if app else ""))
        except OSError:
            pass


def plain_state_endings(root: str | None = None) -> str:
    """Give the state files plain line endings once, in a commit of their own that changes no
    row, wherever .gitattributes asks for them and the committed copy still has CRLF. Without
    it the rule made every committed CRLF state file read as changed in a fresh checkout, and
    the next sync, which pulls master only into a clean folder, stopped (found by
    tools/rehearse_sync.py on a real repo, 2026-10-21). Returns the line to say, or ""."""
    root = root or ROOT

    def g(*args):
        return run_git(root, *args)
    paths = [ln.split(":")[0] for ln in g("check-attr", "eol", "--", *_STATE_FILES)
             .stdout.splitlines() if ln.rstrip().endswith(": eol: lf")]
    if not paths:
        return ""
    eol = g("ls-files", "--eol", "--", *paths).stdout.splitlines()
    need = [ln.split("\t", 1)[1] for ln in eol if "\t" in ln
            and ln.split()[0] in ("i/crlf", "i/mixed")]
    if not need or g("diff", "--quiet", "--", *need).returncode not in (0, 1):
        return ""
    # Their own uncommitted edits to these files stay theirs: never folded into this commit.
    if g("diff", "--quiet", "HEAD", "--", *need).returncode == 1 and \
            g("diff", "--quiet", "--ignore-cr-at-eol", "HEAD", "--", *need).returncode == 1:
        return ""
    g("add", "--renormalize", "--", *need)
    r = g("commit", "-q", "-m", "State files: plain line endings (no row changed)",
          "--", *need)
    if r.returncode:
        return ""
    return ("state files: %s given plain line endings, no row changed, so a chat that saves "
            "them with another program no longer changes every line" % ", ".join(need))


def lf_checkout(root: str | None = None) -> int:
    """Rewrite, from the repo, every file this checkout still holds with CRLF where the repo
    now asks for LF and the file has no change of its own. A Windows checkout made before
    .gitattributes said `* text=auto eol=lf` keeps CRLF in every file the update did not
    touch, and a CRLF shell script stops at its first line in bash; git calls them unchanged,
    so nothing else ever rewrites them. Returns how many it rewrote. Never raises."""
    root = root or ROOT
    try:
        out = run_git(root, "ls-files", "--eol", "-z").stdout
        need = []
        for rec in out.split("\0"):
            meta, _, path = rec.partition("\t")
            f = meta.split()
            if path and len(f) >= 3 and f[0] == "i/lf" and f[1] in ("w/crlf", "w/mixed") \
                    and "eol=lf" in meta:
                need.append(path)
        done = 0
        for i in range(0, len(need), 100):
            part = need[i:i + 100]
            if run_git(root, "diff", "--quiet", "--", *part).returncode:
                part = [p for p in part if not run_git(root, "diff", "--quiet", "--",
                                                       p).returncode]
            # Removed, then checked out: git skips writing a file it counts as up to date,
            # and these all are (checkout-index -f too, tried 2026-10-25).
            for path in part:
                try:
                    os.remove(os.path.join(root, path))
                except OSError:
                    pass
            if part and not run_git(root, "checkout", "--", *part).returncode:
                done += len(part)
        return done
    except Exception:  # noqa: BLE001  a tidy-up must never stop the sync it follows
        return 0


# The state files .gitattributes keeps with plain line endings.
_STATE_FILES = ("job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
                "job_scraper/seen_jobs.json", "documents/interview/question_bank.csv")


def _sync_records(root: str) -> list[tuple[float, str, str]]:
    """[(when, head, app commit)] for every sync recorded in this repo: this checkout's own
    when it has one, else every worktree's (a worktree made for /upgrade has none of its
    own), newest first."""
    own = _stamp_path(root)
    paths = [own + "-head"] if own and os.path.exists(own + "-head") else []
    if not paths:
        import glob
        dirs = _git_dirs(root)
        if dirs:
            paths = [os.path.join(dirs[1], STAMP + "-head")] + glob.glob(
                os.path.join(dirs[1], "worktrees", "*", STAMP + "-head"))
    out = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                got = fh.read().split()
            out.append((os.path.getmtime(path), got[0] if got else "",
                        got[1] if len(got) > 1 else ""))
        except OSError:
            continue
    return sorted((r for r in out if r[1]), reverse=True)


def behind_sync(root: str | None = None) -> str:
    """A plain line when this checkout is older than the last sync in this repo (a worktree
    made from a commit before it), else "". A checkout that took the same app commit in a
    sync of its own is not older. Never in the app itself. Never raises."""
    root = root or ROOT

    def g(*args):
        return run_git(root, *args)
    try:
        if is_the_app(root):
            return ""
        known = [(h, a) for _t, h, a in _sync_records(root)
                 if not g("cat-file", "-e", h + "^{commit}").returncode]
    except (OSError, TypeError):
        return ""
    if not known:
        return ""
    for head, app in known:
        if g("merge-base", "--is-ancestor", head, "HEAD").returncode != 1:
            return ""
        if app and not g("cat-file", "-e", app + "^{commit}").returncode and \
                g("merge-base", "--is-ancestor", app, "HEAD").returncode == 0:
            return ""
    return ("This checkout is older than the last update of this repo, so it would list the "
            "wrong changes. Update it first: git merge %s, then run this again." % known[0][0][:12])


def stale() -> bool:
    """True in a person's repo whose check has not run today. Never raises."""
    try:
        return not is_the_app() and _stale_day(_stamp_line())
    except Exception:  # a reminder must never break the tool that asked for it
        return False


# ------------------------------------------------------------ an update waiting
#
# For a repo whose person asked to choose when the app updates (`updates()` is
# "when_asked"): a plain run looks at the app and changes nothing; when a newer version is
# waiting it says so to the person in one line, once for that version, and `--update`
# takes it when they ask.
#
# What was said is kept in the git folder every worktree of this clone shares, never in a
# tracked file: it records what this computer's chats have told the person, and a tracked
# record would be a commit on every check that every chat then merges. A new cloud chat is
# a new clone, so it says a waiting version once more; the brief leaves the line out when
# its last message already said it (automation/prompts/_common.md).

SAID = "ljs-update-said"


def _said_path(root: str | None = None) -> str | None:
    dirs = _git_dirs(root or ROOT)
    return os.path.join(dirs[1], SAID) if dirs else None


def waiting() -> str:
    """The app commit an update would bring in, or "" when this repo already holds it."""
    if git("merge-base", "--is-ancestor", APP, "HEAD", check=False).returncode == 0:
        return ""
    return git("rev-parse", "--verify", "-q", APP + "^{commit}", check=False).stdout.strip()


def brings(base: str | None, maintainer: bool) -> str:
    """What the waiting update brings, in plain words: its first change, and how many more.
    Read from the CHANGELOG entries it adds, as an update's own "What changed" lines are."""
    # Never synced: the copy was made from the app, so its own CHANGELOG is where it starts.
    diff = git("diff", base or "HEAD", APP, "--", "CHANGELOG.md", check=False).stdout
    lines = [ln[1:] for ln in diff.splitlines()
             if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]
    heads = (headlines(lines, maintainer=maintainer)
             if any(ln.strip().startswith("- ") for ln in lines) else [])
    if not heads:
        return "small fixes and improvements"
    first = heads[0].rstrip(" .;:,")
    if len(first) > 140:
        first = first[:140].rsplit(" ", 1)[0].rstrip(" .;:,") + "..."
    more = len(heads) - 1
    return first + (f", and {more} more change{'' if more == 1 else 's'}" if more else "")


def waiting_line(base: str | None, maintainer: bool) -> str:
    """The one line the person hears about a waiting update."""
    return f'An update is waiting: {brings(base, maintainer)}. Say "update" when you want it.'


def say_waiting(sha: str, line: str, root: str | None = None) -> bool:
    """Print the line for the waiting version `sha`, unless this clone has said it already.
    True when it was printed. Never raises."""
    p = _said_path(root)
    try:
        with open(p, encoding="utf-8") as fh:
            if fh.read().split()[:1] == [sha]:
                return False
    except (OSError, TypeError, IndexError):
        pass
    print("Update waiting. Claude: tell the person this once, at the end of your reply, in "
          "these words; the app updates only when they say so:")
    print(f"  {line}")
    try:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
    except (OSError, TypeError):
        pass
    return True


def look() -> int:
    """A plain run and --if-stale where updates wait for the person's word: the app looked
    at and nothing of it taken. When a newer version is waiting, one line for the person,
    once for that version."""
    dirty = _dirty()
    if dirty:
        return _stop_dirty(dirty)   # the day's upkeep below commits; never over their work
    rc = check()
    sha = waiting()
    if sha:
        print(f"sync_app: the update waiting is {TAG or sha[:12]}; none of it was taken.")
    if sha and os.path.isdir(os.path.join(ROOT, "profile")):
        # Nothing for someone not set up yet: setting up takes the first update.
        say_waiting(sha, waiting_line(installed(), maintainers()))
    return rc


def nudge() -> None:
    """One line on stderr when today's check has not run; for the tools a day's work starts
    with. Nothing where updates wait for the person's word: their look says what is waiting,
    once, and a reminder to run it mid-task is not theirs to want."""
    if stale() and updates() == "auto":
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


def _driver() -> None:
    """The row-by-row merge for the state files, set before anything is merged. Config is
    not committed, so a fresh clone or a resumed cloud computer had none until its first
    full sync, and its first pull of master merged two chats' new rows as lines: a
    conflict (found 2026-10-25)."""
    try:
        import merge_state
        merge_state.install(ROOT)
    except Exception:  # noqa: BLE001  without the driver git merges lines, as it always did
        pass
    _identity()


def _identity() -> None:
    """A name for this copy's own commits where git has none. A new computer's git has no
    user.name or user.email until someone sets them, and every commit and merge then fails
    ("Author identity unknown"): the sync read that as "master does not merge cleanly".
    Set in this copy alone, never for the whole computer: their GitHub name and GitHub's
    private address for it (`<id>+<login>@users.noreply.github.com`, docs.github.com,
    "Setting your commit email address"), from gh when it is signed in, else the owner in
    the copy's GitHub address."""
    if git("config", "user.email", check=False).stdout.strip():
        return
    name = email = ""
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", '[.id, .login, .name // ""] | @tsv'],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15, stdin=subprocess.DEVNULL)
        parts = r.stdout.strip().split("\t") if r.returncode == 0 else []
        if len(parts) >= 2 and parts[0].isdigit() and parts[1]:
            email = f"{parts[0]}+{parts[1]}@users.noreply.github.com"
            name = (parts[2] if len(parts) > 2 else "").strip() or parts[1]
    except (OSError, subprocess.SubprocessError):
        pass
    if not email:
        url = git("remote", "get-url", "origin", check=False).stdout.strip()
        m = re.search(r"github\.com[:/]+([A-Za-z0-9-]+)/", url)
        owner = m.group(1) if m else "job-search"
        name, email = owner, f"{owner}@users.noreply.github.com"
    if not git("config", "user.name", check=False).stdout.strip():
        git("config", "user.name", name, check=False)
    git("config", "user.email", email, check=False)


def pull_master() -> int:
    """A session's first step: bring in what other chats merged to master."""
    _driver()
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


def own_folder() -> str:
    """The first thing a chat on the person's computer is told, while it is still in their
    main folder: make one of its own. Two chats in one folder switch branches under each
    other and fight over git's index, and the second one is usually opened before anyone
    thinks of it, so this is said before any work starts rather than when it goes wrong.
    "" in the cloud, where every chat has its own container, and in a folder already made
    for a chat."""
    if CLOUD:
        return ""
    here = git("rev-parse", "--absolute-git-dir", check=False).stdout.strip()
    common = git("rev-parse", "--git-common-dir", check=False).stdout.strip()
    if not here or not common:
        return ""
    if not os.path.isabs(common):
        common = os.path.join(ROOT, common)
    if os.path.realpath(here) != os.path.realpath(common):
        return ""                                   # a worktree: this chat's own folder
    return ("sync_app: this chat is in your main folder. Before any work, give it a folder of "
            "its own: python3 tools/sync_app.py --worktree <a short name for this chat>, then "
            "run every command there. Two chats in one folder switch branches under each "
            "other.")


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


# Where a chat's own folder goes: inside this one, where Claude Code makes its own
# worktrees. A folder beside the repo (../<repo>-<name>, until 2026-10-25) is outside the
# project, and Claude Code puts a chat that `cd`s there back where it started ("Shell cwd
# was reset", https://code.claude.com/docs/en/tools-reference#bash-tool-behavior), so
# "work there" could not be done. Under .claude/worktrees/ a `cd` stays, EnterWorktree
# enters without asking (https://code.claude.com/docs/en/worktrees), and .gitignore keeps
# it out of the main folder's changes.
WORKTREES = os.path.join(".claude", "worktrees")


def _quoted(path: str) -> str:
    """A path as a shell reads it: quoted when it has a space, a quote or a backslash
    (a Windows path printed bare broke on "My Documents" and lost every backslash)."""
    if re.fullmatch(r"[\w@%+=:,./-]+", path):
        return path
    return "'" + path.replace("'", "'\\''") + "'"


def worktree(name: str) -> int:
    """A folder of this chat's own: .claude/worktrees/<name>, on a new branch from master.

    Two chats on one computer shared one folder, with the other chat's branch checked
    out: a branch switch by one changes the other's files under it, and they fight over
    git's index. Each local chat works in its own worktree and removes it when its pull
    request lands (`git worktree remove <folder>`, from the main folder). Files git does not
    carry (the connections export) are read from the main folder (person.local_state).

    When master cannot be fetched (no network, no sign-in yet) the folder is made from the
    master this computer last fetched, saying so with git's own words, rather than not at
    all: a second chat with no folder of its own is the thing this exists to prevent."""
    _driver()
    start = "origin/master"
    r = git("fetch", "-q", "origin", "master", check=False)
    if r.returncode:
        why = _git_error(r)
        if git("rev-parse", "-q", "--verify", "refs/remotes/origin/master",
               check=False).returncode:
            print(f"sync_app: master could not be fetched ({why}), and this computer has no "
                  "copy of it yet, so no folder was made.")
            return 1
        print(f"sync_app: master could not be fetched ({why}); the folder starts from the "
              "copy this computer fetched last, and the next sync brings it up to date.")
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-") or "chat"
    parent = os.path.join(ROOT, WORKTREES)
    folder = os.path.join(parent, slug)
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(parent, f"{slug}-{n}")
    branch = branch_name(slug)
    os.makedirs(parent, exist_ok=True)
    r = git("worktree", "add", "-q", "-b", branch, folder, start, check=False)
    if r.returncode:
        print(f"sync_app: no worktree made: {(r.stderr or r.stdout).strip()[:200]}")
        return 1
    print(f"sync_app: this chat's own folder is {_quoted(folder)}, on branch {branch}, from "
          "master. Work there from now on (cd into it: it is inside this folder, so the chat "
          "stays there); when its pull request lands, from this main folder: "
          f"git worktree remove {_quoted(folder)}")
    return 0


def check() -> int:
    base = installed()
    if git("merge-base", "--is-ancestor", APP, "HEAD", check=False).returncode == 0:
        print("sync_app: up to date with the app.")
    elif base is None:
        print("sync_app: never synced. The first update merges the app as unrelated history.")
    else:
        n = git("rev-list", "--count", f"HEAD..{APP}").stdout.strip()
        print(f"sync_app: {n} app commit(s) to bring in.")
    changed, extra = drift(app=base)
    if base is not None:
        # Behind is not drift: only files edited here since the last sync count.
        mine = set(git("diff", "--name-only", "--no-renames", base, "HEAD").stdout.split())
        changed = [p for p in changed if p in mine]
    print(f"  drift: {len(changed)} app-owned file(s) edited here"
          + (" (the next update puts them back): " + ", ".join(changed[:8]) if changed else ""))
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



def _utf8_stdio() -> None:
    """The terminal in UTF-8 whatever the computer's code page (python_floor.utf8_stdio): a
    name with "Ł" in it stopped this on a cp1252 Windows terminal. Never raises."""
    try:
        import python_floor
        python_floor.utf8_stdio()
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str]) -> int:
    _utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report only; change nothing")
    mode.add_argument("--update", action="store_true",
                      help="take the waiting update, whatever the setting: the person said so")
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
                      help="a folder of this chat's own, inside this one, on a new branch from "
                           "master: for a second chat on the same computer")
    ap.add_argument("--on", default="", metavar="MODEL",
                    help="the model this session runs on: the day's work is checked against it")
    ap.add_argument("--tools", default=None, metavar="LIST",
                    help="the browser tools this chat has (browser, chrome, chrome-off, enable, "
                         "none): the place check says what to do, once in a chat")
    a = ap.parse_args(argv)
    if run_git(ROOT, "--version").returncode == 127:
        print(NO_GIT)
        return 1
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
    if (a.pull or a.if_stale) and not is_the_app():
        hint = own_folder()
        if hint:
            print(hint)
    if a.pull:
        return pull_master()
    if is_the_app():
        print("sync_app: this is the app itself; nothing to sync.")
        return 0
    if a.if_stale:
        if not stale():
            print("sync_app: already checked today.")
            # A new chat on a day already checked still hears these: each chat runs on its
            # own cloud computer, so blocked job sites are checked for every chat.
            network_check()
            place_check(a.tools)
            return 0
        if _dirty():
            return _stop_dirty(_dirty())  # changing nothing
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
    # Updates arrive by themselves, unless the person's own profile says they wait for their
    # word: then only --update takes one and every other run looks and changes nothing.
    rc = sync() if a.update or updates() == "auto" else look()
    if rc == 0:
        _record_check()
        if git("rev-parse", "HEAD", check=False).stdout.strip() != before:
            own_tests()
        app_watch()
        network_check()
        said = plain_state_endings()
        if said:
            print("sync_app: " + said)
        n = lf_checkout()
        if n:
            print(f"sync_app: {n} file(s) on this computer given plain line endings, as the "
                  "app now keeps them; nothing in them changed")
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
            # No compiled copies left in profile/tests/__pycache__ to be committed.
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "--tb=no", f"--junitxml={report}", tests], cwd=root, text=True,
                               capture_output=True, timeout=300,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                               encoding="utf-8", errors="replace")
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


# The most the person hears about their own checks after an update: they are Claude's to
# keep in line, never a question.
OWN_CHECKS_SAID = "Your setup's own checks are up to date with the new version."


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
    # For Claude, never the person: a chat passed "Your own tests: 2 now fail" on to someone
    # who had never seen a test (2026-10-22).
    lines = [f"Claude, not for the person: their own tests, {len(failures)} now fail after "
             "this update."]
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
                     + ". Bring each in line with the CHANGELOG; where the change itself looks "
                     "wrong, bring the test in line all the same and note the app bug the way the "
                     "profile says.")
    # Nothing here is the person's to do or to answer: a chat told them "I'll flag those for
    # you to update yourself" (2026-10-22), and the maintainer's word is that the app does
    # everything with no input from them.
    lines.append("Claude: do it now, in this turn, with no question to the person: rewrite, "
                 "retire and bring in line as above, run them again, and commit with the "
                 "rest of this sync's work, naming each test in the commit (a revert brings "
                 "any back). Tell the person nothing about it beyond one plain line at most: "
                 f"\"{OWN_CHECKS_SAID}\"")
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
            found += _source_reads(root, tree)
            if found:
                out[os.path.relpath(path, root)] = sorted(set(found))
    return out


def _source_reads(root: str, tree) -> list[str]:
    """"the source of tools/<file>" for each app file a test reads as text: an
    `open(...)`, `.read_text()` or `.read_bytes()` whose path names one. A test that asserts
    what the code says rather than what it does breaks on any rewrite that keeps the
    behaviour: one read scrape_wide.py looking for "except Exception" around the boards."""
    import ast
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        reads = ((isinstance(f, ast.Attribute) and f.attr in ("read_text", "read_bytes", "open"))
                 or (isinstance(f, ast.Name) and f.id == "open"))
        if not reads:
            continue
        words = [c.value for c in ast.walk(node) if isinstance(c, ast.Constant)
                 and isinstance(c.value, str)]
        for w in words:
            if not w.endswith(".py"):
                continue
            rel = w.replace("\\", "/")
            rel = rel if rel.startswith("tools/") else "tools/" + rel.rsplit("/", 1)[-1]
            if os.path.isfile(os.path.join(root, *rel.split("/"))) and (
                    w.startswith("tools/") or "tools" in words):
                out.append(f"the source of {rel}")
    return out


def own_test_risks_report(risks: dict[str, list[str]]) -> str:
    """One note for the person's tests that will break when the app changes a private part."""
    if not risks:
        return ""
    names = sorted({n for v in risks.values() for n in v})
    return (f"Note: {len(risks)} of your own test file(s) reach into private parts of the app "
            f"or read its source as text ({', '.join(names[:5])}"
            f"{', ...' if len(names) > 5 else ''}): they pass now and break when the app changes "
            "those parts. Claude: when next working in these files, move them onto public names "
            "and what the code does (a job board through tools/offline_boards.py), keeping every "
            "assertion: " + "; ".join(sorted(risks)[:4]) + ("; ..." if len(risks) > 4 else ""))


# In the repository's .git, never committed: the sync commit the person's own tests last
# ran on, so they run once for each update whichever copy of this file brought it.
OWN_TESTS_MARK = "ljs_own_tests_ran_on"
SYNC_SUBJECT = "Sync from the app"


def _git_out(root: str, *args: str) -> str:
    r = run_git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def _mark_path(root: str) -> str:
    gd = _git_out(root, "rev-parse", "--git-dir")
    return os.path.join(root, gd, OWN_TESTS_MARK) if gd and not os.path.isabs(gd) else (
        os.path.join(gd, OWN_TESTS_MARK) if gd else "")


OWN_TESTS_RECORD = "ljs_own_tests.json"


def tests_tree(root: str) -> str:
    """The committed tree of profile/tests: a record is current while this is unchanged."""
    return _git_out(root, "rev-parse", "HEAD:profile/tests")


def record_own_tests(root: str, failures) -> None:
    """What the last run of the person's own tests found, for the own-tests upgrade: each
    failing test, its message, and the removed part of the app it names, if any."""
    mark = _mark_path(root)
    if not mark:
        return
    if failures is None:
        # The tests could not run (pytest missing, or a file that does not import): what
        # the last run found stands, stamped with this tree so the upgrade's check does
        # not run the whole suite again every time it looks.
        got = own_tests_record(root) or {}
        out = {"tree": tests_tree(root), "failures": got.get("failures") or [],
               "could_not_run": True}
    else:
        out = {"tree": tests_tree(root),
               "failures": [[n, (m or "")[:300], _gone(root, m)] for n, m in failures]}
    try:
        with open(os.path.join(os.path.dirname(mark), OWN_TESTS_RECORD), "w",
                  encoding="utf-8") as fh:
            json.dump(out, fh)
    except OSError:
        pass


def own_tests_record(root: str) -> dict | None:
    mark = _mark_path(root)
    if not mark:
        return None
    try:
        with open(os.path.join(os.path.dirname(mark), OWN_TESTS_RECORD), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def own_tests(root: str | None = None) -> None:
    """After an update lands, the person's own tests (profile/tests), which may have pinned
    how the app worked before: each that now fails is named with why, never left for the
    next ci_local.sh run to find. A person's copy of an old discovery test asserted the
    old search shape for days after the app changed it, and when 3.5.0 moved the employer
    boards into openroles, the maintainer's own tests failed by the dozen on names it
    removed and the sync said nothing, because the copy of this file that ran the sync
    predated the check."""
    root = root or ROOT
    failures = own_test_failures(root)
    record_own_tests(root, failures)
    text = own_tests_report(failures or [], root)
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
                           capture_output=True, timeout=300, encoding="utf-8", errors="replace")
        if (r.stdout or "").strip():
            print(r.stdout.rstrip())
    except (OSError, subprocess.TimeoutExpired):
        print("App watch: did not finish in five minutes; the next sync tries again.")


def network_check() -> None:
    """In a cloud chat, the job sites its cloud settings block, checked with the day's sync.

    A chat whose cloud settings reach only a few websites searched the web instead, said
    nothing about why, and showed jobs that had closed months before as leads
    (2026-10-22). Nobody may be left with a tool that does not work without knowing: the
    first thing they hear is the fix, every day until it is made."""
    if not CLOUD:
        return
    script = os.path.join(ROOT, "tools", "env_check.py")
    if not os.path.isfile(script) or not os.path.isdir(os.path.join(ROOT, "profile")):
        return
    try:
        r = subprocess.run([sys.executable, script, "--say"], cwd=ROOT, text=True,
                           capture_output=True, timeout=120, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return
    out = (r.stdout or "").strip()
    if out:
        print("Job sites blocked. Claude: before anything else, tell the person this, in these "
              "words, and run no search until they say it is done:")
        print("\n".join("  " + ln for ln in out.splitlines()))
        for ln in (r.stderr or "").splitlines():
            if ln.startswith("[claude_surfaces:"):      # the steps are old: yours, never said
                print("Claude, not for them: " + ln)


def place_check(tools: str | None) -> None:
    """Is this chat the right place for what the person set up (tools/place.py)?

    Said once in a chat, whatever chat it is: run as its own process from the file
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
        r = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=60,
                           encoding="utf-8", errors="replace")
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
                           capture_output=True, timeout=60, encoding="utf-8", errors="replace")
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
                           cwd=ROOT, text=True, capture_output=True, timeout=600,
                           encoding="utf-8", errors="replace")
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
