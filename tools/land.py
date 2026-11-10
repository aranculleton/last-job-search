#!/usr/bin/env python3
"""Land a chat's work on master in one command, run in the background: the landing rule as code.

Every step of a chat re-reads its whole history, so steps are the cost. Landing took about
fourteen (save, commit, the check, fetch, merge, push, open the pull request, merge it,
unsubscribe, then a stash and a checkout of master), and chats ran the three-minute check in
the foreground (2026-11-03). Now a chat starts this with Bash `run_in_background`, at most
once a turn, after its answer is out, and makes only the GitHub calls it prints:

    python3 tools/land.py [--message "<what changed>"]
    python3 tools/land.py --detach [--message "<what changed>"]
    python3 tools/land.py --after-merge
    python3 tools/land.py --waiting
    python3 tools/land.py --keep [--message "<what changed>"]

--keep (a finished job chat asked by the chat that answers the page, tidy.py close): the work
saved and pushed to this chat's own branch in seconds, with no check, no merge and no pull
request, so the next landing anywhere brings it in.

--detach (the chat that answers the page, once per batch of its work): the same landing in a
process of its own, started from an ordinary foreground call that returns at once, so its end
wakes no chat. A background command re-invokes the chat when it exits, and the app's hook
held the turn again while a save still ran: each save cost the chat that answers the page a
turn or two of its whole history (the maintainer, 2026-11-05). It marks the landing as asked
for at once (WANTED_FILE, which the hook reads as a save in progress), opens the pull request
and merges it itself through GitHub's REST interface (`gh api`) where this computer can,
then moves the branch to master; it lands again once for work written while it ran, and a
second --detach while one runs only asks it to. What it could not do on GitHub is kept
(RESULT_FILE) and said once, in a line or two, by the next `app.py reads`.

1. tools/save_state.py stages the person's files, and nothing of the app's is committed
   (tools/personal_paths.py is the line); a commit when anything is staged.
2. git fetch origin master, then git merge --no-edit origin/master, here, with the
   row-by-row driver set first (a job's chat is a fresh clone that never ran the sync, and
   two appended tracker rows stranded its drafts: the stranger audit, 2026-11-03). A file
   the driver does not cover is settled, never left (merge_state.settle: neither side lost).
3. Every earlier chat's or run's work still waiting on GitHub (waiting(), fetched fresh) is
   brought in the same way, so it lands with this one: a job's chat, a brief and a chat
   kept open for days all bring it in, not only a new chat's start. A branch left behind
   (its own work more than STALE_DAYS older than master's later changes to the same files)
   is never brought in: one line says so, and it stays where it is. So is a branch whose
   own newest work is more than OLD_DAYS (7) old: named once to the person, in plain words.
   Files unsaved in this checkout itself and over a week old are saved (they are the files
   as they stand) and named once the same way. What a branch brought in never half-merges
   this chat's work (merge_in): a file this chat changed keeps this chat's whole copy, and
   an application this chat changed (its resume, letter and draft) keeps every file of it as
   this chat has it; the other chat's versions stay in the saved history.
4. Nothing ahead of origin/master: "land: nothing to land", exit 0, and no check is run.
5. This chat's branch pushed (as in 6), saying nothing, then ./tools/ci_local.sh --quick. Not
   green: its failing lines, exit 1. Pushed first, a chat whose time runs out mid-check, or
   a container that goes, leaves its work waiting on GitHub for the next landing: the
   "Finding jobs" chat timed out in its check and its shortlist was lost (2026-11-06). Work
   another landing took to master meanwhile is landed, with nothing to open (--after-merge).
   A landing whose every file changed since master is the person's own data (data_only: no
   app file, none of their code, not profile/person.json) runs no code checks, only a data
   check of those files (data_check), and lands at once.
6. git push -u origin HEAD, a network failure retried four times (2, 4, 8 and 16 s). In a
   chat on the person's computer (on_computer) the landing ends here, having checked only
   its data: no pull request and no merge from there (Claude's own safety check refused the
   merge), and the chat that answers the page in the cloud lands it with its next save.
7. "land: ready <branch>", then the two GitHub calls to make (open the pull request, merge
   it) and --after-merge.

Not green, or a merge that could not be settled, still pushes this chat's branch (the commit
before the merge, for a conflict), with no pull request, and says the work waits there: a
cloud container is gone when its chat ends, and work only committed in it was lost with it
(the release review, 2026-11-03). The next landing anywhere brings it in; --waiting lists
each, with how long it has waited. A branch outside claude/ and chat/ (a background agent's
worktree-...) is pushed under claude/, where the next landing looks.

Two things are for the person, said once and plainly: GitHub refusing the save (their
connection to Claude lapsed: the steps to connect it again), and a full disk.

--after-merge: git fetch origin master; when the commit this landing pushed is on master
now, the branch is reset to master (git checkout -B <branch> origin/master), so the next
piece of work starts current, with no stash and no checkout of master, and its copy on
GitHub is moved up to master with it (a fast-forward push), so nothing reads as unpushed. A
page update that took master since (app_setup.take_master) adds only a merge commit, which
is no reason to say "not merged"; newer work of the chat's own is kept, with master merged
into it, and merges that hold nothing master lacks are no newer work.

While it runs it holds a lock in the checkout's git folder, taken in one step (O_CREAT |
O_EXCL), and a page update takes no master meanwhile (app_setup.take_master); a git command
refused because another one holds git's own index.lock is tried again for a few seconds.
Saves queue: one landing at a time a checkout. A landing (or --detach) asked for while one
runs is recorded (WANTED_FILE) and taken by the running one before it lets go, or by the next,
so only one check ever runs and later work is never dropped.

Each git command is its own call, nothing is ever force-pushed, and everything printed is for
Claude, never the person (CLAUDE.md, "Saving"), but a line that says "tell the person". Exit
0 landed or ready, 1 not green or not
merged yet, 2 stopped before the push (the line says why, and whether the work waits on its
branch). The check can be replaced, for the tests only, by `check=` or LJS_LAND_CHECK (a
command line).
"""
from __future__ import annotations

import calendar
import contextlib
import io
import json
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
# A detached landing asked for and not finished: the hook reads it as a save in progress, from
# the moment it is asked for (a background landing took its lock a moment after the turn
# ended, and the hook held the turn for "unsaved" work in that moment).
WANTED_FILE = "ljs-landing.wanted"
RESULT_FILE = "ljs-land-result.json"   # what a detached landing could not do, for a chat
LOG_FILE = "ljs-landing.log"
DETACHED_ROUNDS = 3
LOCK_STALE_S = 30 * 60
LOCK_STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The branches a chat or a scheduled run works on: a cloud chat's and a run's (claude/...),
# a second chat's folder on a computer (sync_app.branch_name, chat/...), and a background
# agent's own worktree (Claude Code names its branch worktree-...), whose unlanded work was
# pushed where no later chat looked (the stranger audit, 2026-11-03, X-35). Any other branch
# is pushed under claude/ (_remote_name).
CHAT_BRANCHES = ("claude/", "chat/", "worktree-")
# A full disk names git's index.lock in git's own message ("index.lock write error. Out of
# diskspace"), and was reported as another command running, waited on and never said
# (the stranger audit, 2026-11-03, X-45).
DISK_FULL = re.compile(r"no space left|out of diskspace|disk quota exceeded|\bENOSPC\b", re.I)
# What the person hears, once, in these words. Plain, with one recommendation, and the steps
# for another company's screens only as claude_surfaces prints them, checked that day
# (CLAUDE.md, "Talking to the person").
REFUSED_SAY = ("Your work isn't being saved: GitHub stopped letting Claude save to your copy. "
               "Connecting it again fixes it, and everything after that is saved as usual.")
DISK_FULL_SAY = ("This chat's computer has run out of space, so your latest work couldn't be "
                 "saved here. Please start a new chat and ask it to carry on.")


def _git(root: str, *args: str, waits=LOCK_WAITS) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for wait in waits:
        err = r.stderr or ""
        if r.returncode == 0 or DISK_FULL.search(err) or not INDEX_LOCK.search(err):
            break
        time.sleep(wait)
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    return r


def _said(r: subprocess.CompletedProcess) -> str:
    """git's reason, in one line: the disk, another command's lock, a refusal or the network
    where git names one (a 403 is said in an earlier line than git's last), else its last."""
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    if DISK_FULL.search(text):
        return "the disk here is full"
    if INDEX_LOCK.search(r.stderr or ""):
        return "another git command was running here at the same time, for longer than it waited"
    lines = [ln.strip() for ln in (r.stderr.strip() or r.stdout.strip()).splitlines()
             if ln.strip()]
    for pat in (REFUSED, NETWORK):
        hit = next((ln for ln in lines if pat.search(ln)), "")
        if hit:
            return hit
    return lines[-1] if lines else "no words from git"


def _told(why: str) -> None:
    """The lines for a refused save or a full disk: for Claude, with the words for the
    person. Said by whatever landing hit it, so a copy whose connection lapsed is told at
    its first save, never left to lose every chat's work in silence (the stranger audit,
    2026-11-03, X-26)."""
    if why == "refused":
        print("land: Claude, GitHub refused this save, so nothing reaches the person's copy "
              "from any chat until they connect it again. Tell them once, in these words: "
              f"\"{REFUSED_SAY}\" Then give the steps python3 tools/claude_surfaces.py steps "
              "connect-github prints, after checking the page it names today. Their work "
              "stays committed in this chat until a save goes through.")
    elif why == "disk":
        print("land: Claude, the disk here is full. Delete this chat's own scratch files "
              "(never the person's) and land again. If it is still full, tell them once, in "
              f"these words: \"{DISK_FULL_SAY}\"")


# GitHub saying no to who is asking, not to what was sent: a push rejected because the branch
# moved is none of these.
NO_ACCESS = re.compile(r"\b40[13]\b|denied|permission|authenticat|could not read username|"
                       r"not authorized|repository not found", re.I)


def _trouble(r: subprocess.CompletedProcess) -> str:
    """"refused", "disk" or "" for a git command that failed."""
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    if DISK_FULL.search(text):
        return "disk"
    if r.returncode != 0 and NO_ACCESS.search(text):
        return "refused"
    return ""


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
    return _live(os.path.join(d, LOCK_FILE))


def lock_text(when: float | None = None, token: str = "") -> str:
    """The lock's one line: this process, when the landing last said it was alive (on its own
    clock), and the token of the run that holds it. A lock an older version wrote has no token
    and is read the same way."""
    return "%d %s%s\n" % (os.getpid(), time.strftime(LOCK_STAMP, time.gmtime(when)),
                          (" " + token) if token else "")


# The landing lock is taken in one step (os.open with O_CREAT | O_EXCL, which Windows has too):
# looking for it and then writing it let two landings started together both take it, and each
# ran its own check side by side (the maintainer's copy, 2026-11-06). _MINE: the tokens this
# process holds, by (git folder, thread); _RUN: where a detached run holds it for all its
# rounds, so the landing and the after-merge step inside it are that run's.
_MINE: dict = {}
_RUN: set = set()


def _lock_key(d: str) -> tuple[str, int]:
    import threading
    return (os.path.normcase(os.path.realpath(d)), threading.get_ident())


def _lock_words(p: str) -> list[str]:
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read().split()
    except OSError:
        return []


def _live(p: str) -> bool:
    """Is the lock at `p` a landing running now: its process alive and its stamp younger than
    LOCK_STALE_S (a landing killed part way leaves one behind)?"""
    try:
        with open(p, encoding="utf-8") as fh:
            words = fh.read().split()
        pid = int((words or ["0"])[0])
        # Its age on the clock that wrote it: the stamp the landing put in it. The file's own
        # time is the disk's clock, which a Python whose clock was moved never agrees with:
        # a landing read its own lock, a second old, as a month stale (the clock check,
        # 2026-11-04). A lock with no stamp is aged by the file.
        try:
            began = calendar.timegm(time.strptime(words[1], LOCK_STAMP))
        except (IndexError, ValueError):
            began = os.path.getmtime(p)
    except (OSError, ValueError):
        return False
    return time.time() - began < LOCK_STALE_S and (pid <= 0 or _alive(pid))


def _take_lock(root: str) -> str:
    """The landing lock, taken atomically: its token, or "" while another landing holds it.
    A stale one is moved aside under a name of this run's own and taken over; one found live
    after all (judged from an older reading) is put back. "-" where there is no git folder or
    the lock cannot be written: nothing to hold, as before."""
    import uuid
    d = git_dir(root)
    if not d:
        return "-"
    p = os.path.join(d, LOCK_FILE)
    for _ in range(3):
        token = uuid.uuid4().hex
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if _live(p):
                return ""
            aside = "%s.stale-%d-%s" % (p, os.getpid(), token[:8])
            try:
                os.rename(p, aside)
            except OSError:
                continue                    # another landing moved it first: try again
            if _live(aside):
                # Never over a third one: a link, or Windows' rename, never replaces a file.
                try:
                    os.link(aside, p)
                    os.remove(aside)
                except FileExistsError:
                    pass                    # a third landing holds it now: never over it
                except (OSError, AttributeError):
                    # No links here (some file systems): a rename, only while nothing is
                    # there, since on POSIX a rename replaces what it lands on.
                    if not os.path.exists(p):
                        try:
                            os.rename(aside, p)
                        except OSError:
                            pass
                return ""
            try:
                os.remove(aside)
            except OSError:
                pass
            continue
        except OSError:
            return "-"
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(lock_text(token=token))
        _MINE[_lock_key(d)] = token
        return token
    return ""


def _drop_lock(root: str, token: str) -> None:
    """Let the lock go, only where it is still this run's own."""
    d = git_dir(root)
    if not d or not token or token == "-":
        return
    _MINE.pop(_lock_key(d), None)
    _RUN.discard(_lock_key(d))
    p = os.path.join(d, LOCK_FILE)
    words = _lock_words(p)
    if len(words) >= 3 and words[2] == token:
        try:
            os.remove(p)
        except OSError:
            pass


def _restamp(p: str, pid: str, token: str) -> None:
    try:
        with open(p, "r+", encoding="utf-8", newline="\n") as fh:
            fh.write("%s %s %s\n" % (pid, time.strftime(LOCK_STAMP, time.gmtime()), token))
            fh.truncate()
    except OSError:
        pass


def _beat(root: str) -> None:
    """Say the landing is still alive: its stamp moved on, so a long check is never taken for
    a landing killed part way (LOCK_STALE_S) with a second one started beside it."""
    d = git_dir(root)
    token = _MINE.get(_lock_key(d)) if d else None
    if not token or token == "-":
        return
    p = os.path.join(d, LOCK_FILE)
    words = _lock_words(p)
    if len(words) >= 3 and words[2] == token:
        _restamp(p, words[0], token)


def _hand_over(root: str, token: str, pid) -> None:
    """The lock detach took, given to the process it started to hold it."""
    d = git_dir(root)
    if not d or not token or token == "-":
        return
    _MINE.pop(_lock_key(d), None)
    p = os.path.join(d, LOCK_FILE)
    words = _lock_words(p)
    # Only the lock this run took: the process started may have ended and let it go, and
    # another landing taken it, already.
    if len(words) >= 3 and words[2] == token:
        _restamp(p, str(pid if isinstance(pid, int) else 0), token)


def _adopt(root: str, token: str) -> str:
    """The lock detach took and handed to this process: its token, where it is still there."""
    d = git_dir(root)
    if not d or not token:
        return ""
    words = _lock_words(os.path.join(d, LOCK_FILE))
    if len(words) >= 3 and words[2] == token:
        _MINE[_lock_key(d)] = token
        _restamp(os.path.join(d, LOCK_FILE), str(os.getpid()), token)
        return token
    return ""


@contextlib.contextmanager
def _holding(root: str, pass_on: bool = True):
    """The landing's lock, for as long as it runs; False when another landing holds it. Inside
    a detached run, which holds it for all its rounds, it is that run's. With `pass_on`, a save
    asked for while it was held (by the after-merge step, a page update taking master) is
    started once it is let go: whoever holds the lock passes the queue on."""
    d = git_dir(root)
    if not d:
        yield True
        return
    if _lock_key(d) in _RUN:
        yield True
        return
    token = _take_lock(root)
    if not token:
        yield False
        return
    try:
        yield True
    finally:
        _drop_lock(root, token)
        if pass_on and _asked(root):
            _next(root)


def _next(root: str) -> None:
    """The landing a queued save waits for, started now (in a process of its own)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            detach(root, "")
    except Exception:  # noqa: BLE001  the request stays asked; the next landing takes it
        pass


def _ask(root: str, message: str = "") -> None:
    """A save asked for while one runs: kept (WANTED_FILE) for the running one, or the next."""
    d = git_dir(root)
    if not d:
        return
    try:
        with open(os.path.join(d, WANTED_FILE), encoding="utf-8") as fh:
            got = json.load(fh)
        had = str(got.get("message") or "") if isinstance(got, dict) else ""
    except (OSError, ValueError):
        had = ""
    both = "; ".join(m for m in dict.fromkeys((had, message or "")) if m.strip())
    _mark(root, WANTED_FILE, json.dumps({"message": both, "at": time.time()}) + "\n")


def _asked(root: str) -> bool:
    """A save asked for and not taken yet, however long ago (wanted() ages it for the hook)."""
    d = git_dir(root)
    return bool(d) and os.path.exists(os.path.join(d, WANTED_FILE))


def _take_ask(root: str) -> tuple[bool, str]:
    """(asked, its message), the request taken in one step: one asked a moment later is a new
    file, kept for the next round."""
    d = git_dir(root)
    if not d:
        return False, ""
    p = os.path.join(d, WANTED_FILE)
    taken = "%s.taken-%d" % (p, os.getpid())
    try:
        os.replace(p, taken)
    except OSError:
        return False, ""
    try:
        with open(taken, encoding="utf-8") as fh:
            got = json.load(fh)
        msg = str(got.get("message") or "") if isinstance(got, dict) else ""
    except (OSError, ValueError):
        msg = ""
    try:
        os.remove(taken)
    except OSError:
        pass
    return True, msg


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


CHECKED_ALREADY = "the same commit the last landing checked green and pushed\n"
BEAT_S = 60

# A save that changes only the person's own data (their tracker, threads, documents, state)
# cannot break the app's code, and ./tools/ci_local.sh --quick still made each one wait
# minutes, longer on a computer (the maintainer's copy, 2026-11-10). Such a save lands at once
# after a data check of the files it changes. Code of theirs is still checked in full: their
# settings modules and own tests (profile/*.py, profile/tests/), their portals (.agents/), and
# profile/person.json, which every page update reads (a person.json with no identity loaded,
# landed and broke every page update: the stranger audit, 2026-11-03, X-39).
_CODE = re.compile(r"\.(?:py|pyw|sh|bash|zsh|ps1|bat|cmd|js|mjs|cjs|ts|tsx)$", re.I)
_CHECKED_IN_FULL = ("profile/tests/", ".agents/")
_FULL_FILES = ("profile/person.json",)
_TEMPLATE = re.compile(r"\[YOUR_NAME\]|\[YOUR_EMAIL\]|\[YOUR_PRIMARY_SKILLS\]")
_TEMPLATE_FILES = ("profile/CLAUDE.md", "profile/01-candidate-profile.md")
_TEXT = (".json", ".csv", ".md", ".txt", ".tex", ".yml", ".yaml", ".html", ".log")
DATA_CHECKED = ("Checked here: only the person's own files changed (%d), so the app's checks "
                "were not needed; each file reads cleanly\n")


# A chat on the person's own computer: Claude Code sets CLAUDECODE in the commands it runs, and
# CLAUDE_CODE_REMOTE ("true") only in a cloud chat (as place.surface reads them). Its save ends
# at the push (_land): the chat that answers the page in the cloud does the merge.
COMPUTER_PUSHED = ("land: saved to GitHub on %s; the chat that answers the page in the cloud "
                   "brings it to master with its next save. Nothing to do, and nothing to say "
                   "about saving")


def on_computer(env=None) -> bool:
    """Is this a chat on the person's computer (not a cloud chat, not a script)?"""
    env = os.environ if env is None else env
    return bool(env.get("CLAUDECODE")) and \
        str(env.get("CLAUDE_CODE_REMOTE", "")).lower() != "true"


def data_only(root: str) -> list[str] | None:
    """The files this landing changes against master, when every one is the person's own
    data (tools/personal_paths.py, and none of it code); else None, and the full check runs."""
    r = _git(root, "diff", "--name-only", "--no-renames", "-z", "origin/master", "HEAD")
    if r.returncode != 0:
        return None
    paths = [p for p in (r.stdout or "").split("\0") if p]
    if not paths:
        return None
    try:
        import personal_paths
    except Exception:  # noqa: BLE001  unsure: the full check
        return None
    for p in paths:
        if (not personal_paths.is_personal(p) or _CODE.search(p) or p in _FULL_FILES
                or p.startswith(_CHECKED_IN_FULL)):
            return None
    return paths


def data_check(root: str, paths: list[str]) -> list[str]:
    """What is wrong with the person's changed files, read the way the tools read them: every
    JSON parses, every CSV reads (csv_store, no merge markers, every column named, the columns
    merge_state keys its rows by present), no text file holds git's conflict markers, and the
    profile is not a template again. [] when all is well."""
    try:
        import csv_store
    except Exception as e:  # noqa: BLE001
        return ["the data check could not start: %s" % e]
    try:
        import merge_state
        keys = merge_state.KEYS
    except Exception:  # noqa: BLE001
        keys = {}
    bad: list[str] = []
    for rel in paths:
        f = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(f) or not rel.lower().endswith(_TEXT):
            continue                                 # removed, or not text (a PDF)
        try:
            with open(f, "rb") as fh:
                text = csv_store.decode(fh.read())[0]
        except OSError as e:
            bad.append("%s: could not be read (%s)" % (rel, e))
            continue
        found = csv_store.conflict_marker(text)
        if found:
            bad.append("%s: git's conflict markers at line %d" % (rel, found[0]))
            continue
        low = rel.lower()
        if low.endswith(".json"):
            try:
                json.loads(text)
            except ValueError as e:
                bad.append("%s: not valid JSON (%s)" % (rel, e))
        elif low.endswith(".csv"):
            import csv
            rows = list(csv.reader(io.StringIO(text, newline="")))
            head = [h.strip() for h in (rows[0] if rows else [])]
            if rows and not all(head):
                bad.append("%s: a column with no name in its first line" % rel)
            need = keys.get(os.path.basename(rel)) or ()
            missing = [c for c in need if c not in head]
            if rows and missing:
                bad.append("%s: its %s column(s) are missing" % (rel, ", ".join(missing)))
            try:
                csv_store.read_rows(f)
            except Exception as e:  # noqa: BLE001
                bad.append("%s: could not be read as rows (%s)" % (rel, e))
        if rel in _TEMPLATE_FILES and _TEMPLATE.search(text):
            bad.append("%s reverted to template placeholders: the populated profile is lost"
                       % rel)
    return bad


ASIDE_ENV = "LJS_OWN_TESTS_ASIDE"     # ci_local.sh: a file of the person's tests to set aside
ASIDE_FILE = "ljs-own-tests-aside.txt"


def _node_id(root: str, name: str) -> str:
    """pytest's id of a test from the name its junit report gives ("profile.tests.test_x.
    TestA::test_b[1]" is "profile/tests/test_x.py::TestA::test_b[1]"), or ""."""
    if ".py::" in name:
        return name.replace("\\", "/")       # a check's own FAILED line gives the id itself
    dotted, _, test = name.rpartition("::")
    parts = dotted.split(".") if dotted else []
    for i in range(len(parts), 0, -1):
        path = "/".join(parts[:i]) + ".py"
        if os.path.isfile(os.path.join(root, *parts[:i]) + ".py"):
            return "::".join([path, *parts[i:], test])
    return ""


def _set_aside(root: str, names: list[str]) -> str:
    """The file the check reads to set these of the person's own tests aside, or ""."""
    ids = [n for n in (_node_id(root, x) for x in names) if n.startswith("profile/tests/")]
    d = git_dir(root)
    if not ids or not d:
        return ""
    p = os.path.join(d, ASIDE_FILE)
    try:
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(ids) + "\n")
    except OSError:
        return ""
    return p


# The longest a landing check may run. The lock is kept alive while it runs (_beat), so a
# check that hung would otherwise hold every save in the copy for ever; before the lock was
# kept alive it went stale after LOCK_STALE_S, and this keeps that bound (the release review,
# 2026-11-06).
CHECK_DEADLINE_S = LOCK_STALE_S
# Never "nothing was pushed": the branch went to GitHub before the check began (_send_early).
CHECK_STOPPED = ("land: the check ran past %d minute(s) and was stopped, so this is not on "
                 "master yet\n")


def _stop(p: subprocess.Popen) -> None:
    """End the check and what it started: its process group on POSIX, the process elsewhere."""
    try:
        if os.name == "posix":
            import signal
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
    except OSError:
        try:
            p.kill()
        except OSError:
            pass


def _run_check(root: str, cmd: list[str], aside: str = "") -> tuple[int, str]:
    """The landing check: (its exit code, what it printed). The lock's stamp is moved on each
    minute it runs, so a long check is never taken for a landing killed part way, and past
    CHECK_DEADLINE_S it is stopped and counts as not green. `aside`: the file naming the
    person's own tests an update broke, which the check sets aside."""
    env = dict(os.environ)
    env.pop(ASIDE_ENV, None)
    if aside:
        env[ASIDE_ENV] = aside
    # A process group of its own, so a stop ends pytest's workers with it.
    kw = {"start_new_session": True} if os.name == "posix" else \
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    try:
        p = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace",
                             stdin=subprocess.DEVNULL, env=env, **kw)
    except OSError as e:
        return 1, "the check could not start: %s\n" % e
    out = err = ""
    until = time.monotonic() + CHECK_DEADLINE_S
    while True:
        left = until - time.monotonic()
        if left <= 0:
            _stop(p)
            try:
                out, err = p.communicate(timeout=30)
            except (subprocess.TimeoutExpired, ValueError):
                out, err = "", ""
            return 1, (out or "") + (err or "") + CHECK_STOPPED % max(1, CHECK_DEADLINE_S // 60)
        try:
            out, err = p.communicate(timeout=min(BEAT_S, left))
            break
        except subprocess.TimeoutExpired:
            _beat(root)
    return p.returncode, (out or "") + (err or "")


def _own_tests_owed(root: str) -> list[str]:
    """The person's own tests an update broke that are not brought in line yet, before the
    landing's check runs: those the last run recorded (sync_app.own_tests_owed, run again
    only when something they check changed), and, where this landing carries an update their
    tests were never run against (a chat that took it elsewhere, a fresh computer with no
    record), a run of them now. [] where there are none, or it cannot be told."""
    if not os.path.isdir(os.path.join(root, "profile", "tests")):
        return []
    try:
        import sync_app
        owed = sync_app.own_tests_owed(root)
        if owed:
            return owed
        rec = sync_app.own_tests_record(root) or {}
        app = sync_app.app_tree(root)
        if not app or rec.get("app") == app:
            return []
        # No update in this landing: the app's code is master's own, and the check runs them.
        if _git(root, "rev-parse", "origin/master:tools").stdout.strip() == app:
            return []
        failures = sync_app.own_test_failures(root)
        sync_app.record_own_tests(root, failures)
        return [str(n) for n, _m in failures or []]
    except Exception:  # noqa: BLE001  unsure: the check itself says
        return []


def _recorded_failures(root: str) -> list[tuple[str, str]]:
    """[(test, message)] the record of the person's own tests holds as failing now."""
    try:
        import sync_app
        rec = sync_app.own_tests_record(root) or {}
    except Exception:  # noqa: BLE001
        return []
    return [(str(f[0]), str(f[1]) if len(f) > 1 else "") for f in rec.get("failures") or []
            if f]


def _work_since_push(root: str) -> bool:
    """Anything a queued save would add: files no commit holds, or commits since the last
    push."""
    try:
        import save_state
        if save_state.unsaved(root):
            return True
    except Exception:  # noqa: BLE001  unsure: land, which finds out
        return True
    sent = pushed(root)
    return bool(sent) and _git(root, "rev-parse", "HEAD").stdout.strip() != sent


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


# What a landing says when only the person's own tests stop it, after an update changed what
# they check (ci_local.sh prints the own-tests report only then).
OWN_TESTS_HEAD = ("land: not saved to master yet: only the person's own tests fail, after an "
                  "update changed what they check")
OWN_TESTS_DO = ("land: Claude, do this now, before any other work: bring their own tests in "
                "line as python3 tools/sync_app.py --own-tests says (RUNBOOK.md, \"Your own tests "
                "fail after an update\"), run it again until it says they pass, commit them, and "
                "land again: the finished work is kept and lands with them. Nothing to ask the "
                "person. Every command that starts work says this first until they pass.")
_OWN_CHECK = re.compile(r"^\s+(?:pytest \(profile/tests, on this person\)|\S.*, profile/tests)"
                        r"\s+FAIL\s*$")
_FAILED = re.compile(r"^\s*FAILED (profile/tests/\S+?)(?: - (.*))?$", re.M)


def own_tests_only(out: str) -> list | None:
    """[(test, message)] when the check failed only on the person's own tests (profile/tests)
    and an update is what they fail on (the check's own-tests report says so); else None."""
    fails = [ln for ln in out.splitlines() if ln.rstrip().endswith("FAIL")]
    if not fails or not all(_OWN_CHECK.match(ln) for ln in fails):
        return None
    if "their own tests," not in out or "now fail after this update" not in out:
        return None
    return [(m.group(1), (m.group(2) or "").strip()) for m in _FAILED.finditer(out)]


def _record_own(root: str, failures) -> None:
    """The person's own tests as this landing's check found them, kept where every command
    that starts work reads them (sync_app.own_tests_step)."""
    try:
        import sync_app
        sync_app.record_own_tests(root, failures)
    except Exception:  # noqa: BLE001  the landing's own lines still say it
        pass


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
        if code in (0, save_state.LEFT_OUT) or wait is None \
                or DISK_FULL.search(buf.getvalue()) or not INDEX_LOCK.search(buf.getvalue()):
            break
        time.sleep(wait)
    # What the save says to tell the person reaches the landing's own lines (what git would
    # not take, an older version's copies it could not decide): swallowed with the rest of
    # its words, they never reached the person.
    for ln in buf.getvalue().splitlines():
        if ln.startswith("save_state: ") and TELL.search(ln) and not NOTHING_TO_TELL.search(ln):
            print("land: " + ln[len("save_state: "):])
    if code != 0 and code != save_state.LEFT_OUT:
        if DISK_FULL.search(buf.getvalue()):
            return False, "the disk here is full"
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


TELL = re.compile(r"\btell the person\b", re.I)
NOTHING_TO_TELL = re.compile(r"\bnothing to tell the person\b", re.I)


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


def _remote_name(name: str) -> str:
    """Where on GitHub a branch is pushed: as it is when the next landing looks there
    (CHAT_BRANCHES), else under claude/."""
    return name if name.startswith(CHAT_BRANCHES) else "claude/" + name


def _push(root: str, name: str, sleep) -> tuple[str, subprocess.CompletedProcess]:
    """(the name on GitHub, git's answer): this chat's branch pushed, never forced."""
    there = _remote_name(name)
    if there == name:
        return there, _retried(root, "push", "-q", "-u", "origin", "HEAD", sleep=sleep)
    return there, _retried(root, "push", "-q", "-u", "origin", "HEAD:refs/heads/" + there,
                           sleep=sleep)


def _send_early(root: str, sleep) -> None:
    """This chat's branch pushed before the long check, never forced and saying nothing: a
    chat whose time ran out mid-check, or a container that went, left its work on no branch
    at all, and its shortlist was lost with it (the "Finding jobs" chat, 2026-11-06). Pushed,
    it waits on GitHub for the next landing anywhere (waiting()). A push that fails here is
    tried again after the check, which says what went wrong."""
    name, _why = _own_branch(root)
    if name:
        _push(root, name, sleep)


def _taken_meanwhile(root: str, sleep) -> bool:
    """Did another chat's landing take this work to master while the check ran (it waited on
    GitHub from _send_early)? Then there is no pull request to open: it is landed."""
    if _retried(root, "fetch", "-q", "origin", "master", sleep=sleep).returncode != 0:
        return False
    if _git(root, "rev-list", "--count", "origin/master..HEAD").stdout.strip() != "0":
        return False
    print("land: another chat's landing took this work to master while the check ran, so "
          "there is no pull request to open")
    return True


def _wait_on_branch(root: str, head: str, sleep) -> None:
    """Not landed, but never lost: this chat's branch pushed with no pull request, so the
    next landing anywhere brings it in (waiting()). A cloud container is gone when its chat
    ends, and work only committed there went with it (the release review, 2026-11-03)."""
    name, why = _own_branch(root)
    if name:
        there, r = _push(root, name, sleep)
        if r.returncode == 0:
            print("%s; the work waits on %s, pushed with no pull request: open none. The next "
                  "landing, in this chat or any other, brings it in and lands it. Nothing about "
                  "it is said to the person" % (head, there))
            return
        why = _said(r)
        print("%s; nothing was pushed (%s), and the work stays committed here" % (head, why))
        _told(_trouble(r))
        return
    print("%s; nothing was pushed (%s), and the work stays committed here" % (head, why))


def _app_side(root: str, ref: str) -> list[str]:
    """The app commits a branch's own update merges brought in: the other parent of each
    "Sync from the app" merge on it that master lacks."""
    out = []
    for m in _git(root, "rev-list", "--merges", "origin/master.." + ref).stdout.split():
        if _git(root, "log", "-1", "--format=%s", m).stdout.startswith("Sync from the app"):
            out += _git(root, "rev-parse", m + "^@").stdout.split()[1:]
    return out


def _own(root: str, ref: str) -> tuple[list[str], int] | None:
    """(the files a branch's own commits changed, when the newest of them was made, in
    seconds): not master's, and not the app's that its update brought in (a chat that took an
    update and then could not land was never listed, and its work was lost: the stranger
    audit, 2026-11-03, X-31). None when git cannot say."""
    r = _git(root, "log", "--no-merges", "--format=%x01%ct %s", "--name-only", "-z",
             "origin/master.." + ref, "--not", *_app_side(root, ref),
             *(["--remotes=app"] if _git(root, "rev-parse", "-q", "--verify",
                                         "refs/remotes/app/master").returncode == 0 else []))
    if r.returncode != 0:
        return None
    files, skip, newest = [], False, 0
    for part in r.stdout.replace("\n", "\0").split("\0"):
        if part.startswith("\x01"):
            when, _, subject = part[1:].partition(" ")
            # A sync's own "put back" commit restores the app's files: the app's, not theirs.
            skip = subject.startswith("Sync from the app")
            if not skip and when.isdigit():
                newest = max(newest, int(when))
            continue
        if part and not skip:
            files.append(part)
    return list(dict.fromkeys(files)), newest


def _own_files(root: str, ref: str) -> list[str] | None:
    got = _own(root, ref)
    return None if got is None else got[0]


# A branch left behind: master has changed, since the branch last met it, files of the
# person's that the branch's own commits change too, and the newest of those changes came
# more than STALE_DAYS after the branch's own newest work. Bringing it in sets copies that
# much older against newer ones: a branch left nine days earlier, brought in by a landing,
# put its abandoned page record back over the one in use and left copies and questions
# beside a dozen of the person's files (a report from a person's copy, 2026-11-04). A branch
# a landing left a few hours ago, or an old one whose files master never changed since, is
# brought in as before (X-30): every landing tries it, and the daily brief lands at least
# once a day, so work still off master STALE_DAYS on was left, not waiting. It is never
# deleted, only left where it is.
STALE_DAYS = 3
# And a branch whose own newest work is older than OLD_DAYS is left whatever master changed:
# 19-day-old work from a chat that could not save was brought in by a landing and swept
# files and copies into the person's folders (the maintainer, 2026-11-04). A week: a landing
# runs every day, so work still off master after a week was kept out by something (a check
# not green, a save GitHub refused), is likely out of date, and the person should know
# before it comes back. It is named once, in plain words; it stays on GitHub.
OLD_DAYS = 7
NAMED_FILE = "ljs-left-named"


def _left_behind(root: str, ref: str, own: tuple[list[str], int]) -> tuple[int, list[str]]:
    """(days, files) for a branch left behind, else (0, [])."""
    files, mine = set(own[0]), own[1]
    # A file the driver merges row by row keeps both chats' rows: master changing it later
    # never puts an older copy over a newer one, so it never leaves a branch behind.
    files -= _row_merged(root, files)
    if not files or not mine:
        return 0, []
    r = _git(root, "log", "--no-merges", "--format=%x01%ct", "--name-only", "-z",
             ref + "..origin/master")
    if r.returncode != 0:
        return 0, []
    newest: dict[str, int] = {}
    when = 0
    for part in r.stdout.replace("\n", "\0").split("\0"):
        if part.startswith("\x01"):
            when = int(part[1:]) if part[1:].isdigit() else 0
        elif part in files and when > newest.get(part, 0):
            newest[part] = when
    late = sorted(f for f, t in newest.items() if t - mine > STALE_DAYS * 86400)
    if not late:
        return 0, []
    return int((max(newest[f] for f in late) - mine) // 86400), late


def _chat_branches(root: str) -> tuple[list[str], dict[str, tuple[int, list[str]]]]:
    """(waiting, left behind): every chat's branch on GitHub off master whose own commits
    change only the person's files, each either waiting for the next landing or left behind
    ({ref: (days, files)})."""
    import personal_paths
    here = branch(root)
    r = _git(root, "for-each-ref", "--format=%(refname:short)", "--no-merged", "origin/master",
             *("refs/remotes/origin/" + (p if p.endswith("/") else p + "*")
               for p in CHAT_BRANCHES))
    out, left = [], {}
    for ref in (x.strip() for x in r.stdout.splitlines() if x.strip()):
        if ref in ("origin/" + here, "origin/" + _remote_name(here)):
            continue
        own = _own(root, ref)
        if not own or not own[0] or not all(personal_paths.is_personal(p) for p in own[0]):
            continue
        days, files = _left_behind(root, ref, own)
        if not files and own[1] and time.time() - own[1] > OLD_DAYS * 86400:
            days, files = int((time.time() - own[1]) // 86400), []
            left[ref] = (days, files)
        elif files:
            left[ref] = (days, files)
        else:
            out.append(ref)
    return out, left


def waiting(root: str = ROOT) -> list[str]:
    """The branches on GitHub (origin/claude/..., origin/chat/..., origin/worktree-...) whose
    work is not on master and is the person's: a landing that was not green or stopped on a
    conflict, a run that could not finish. Each is brought in by the next landing and lands
    with its work. A branch whose own commits change any of the app's files is never listed:
    no landing commits one, so it is not a chat's work; an update the branch took from the app
    is the app's, never its own. A branch left behind (left_behind) is not listed either."""
    return _chat_branches(root)[0]


def left_behind(root: str = ROOT) -> dict[str, tuple[int, list[str]]]:
    """{branch: (days, files)} for each chat's branch left behind (STALE_DAYS): never brought
    in by a landing, never deleted."""
    return _chat_branches(root)[1]


SAID_ONCE = "profile/said_once.json"


def _said_key(ref: str, tip: str) -> str:
    return "left-branch:%s@%s" % (ref, tip[:12])


def _named_once(root: str, ref: str) -> bool:
    """True the first time a branch (at its present commit) is named to the person. Kept in
    the person's own said-once record (profile/said_once.json, committed with this landing
    and merged by the later day), so a fresh container does not say it again: kept in .git,
    it was said again in every new cloud container. The .git record older versions kept is
    still read."""
    tip = _git(root, "rev-parse", ref).stdout.strip()
    if not tip:
        return False
    try:
        with open(os.path.join(git_dir(root), NAMED_FILE), encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    if isinstance(old, dict) and old.get(ref) == tip:
        return False
    path = os.path.join(root, *SAID_ONCE.split("/"))
    if not os.path.isdir(os.path.dirname(path)):
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            said = json.load(fh)
    except (OSError, ValueError):
        said = {}
    said = said if isinstance(said, dict) else {}
    if _said_key(ref, tip) in said:
        return False
    try:
        import person
        day = person.today().isoformat()
    except Exception:  # noqa: BLE001 - no profile to read the day from: this computer's
        day = time.strftime("%Y-%m-%d")
    said[_said_key(ref, tip)] = day
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(said, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass
    return True


def _commit_said(root: str) -> None:
    """Commit the said-once record when this landing added to it, so it lands with the work."""
    if _git(root, "status", "--porcelain", "--", SAID_ONCE).stdout.strip():
        _git(root, "add", "--", SAID_ONCE)
        _git(root, "commit", "-q", "-m", "What the person was told once", "--", SAID_ONCE)


def old_line(root: str, ref: str, days: int, consume: bool = True) -> str:
    """The line for a branch left for its age: what to tell the person, once."""
    if consume and not _named_once(root, ref):
        return "left %s as it is (still %d days old; the person was told)" % (ref, days)
    return ("left %s as it is: its work is %d days old, past the %d a landing brings in by "
            "itself. It stays on GitHub, never deleted. Tell the person once: \"Some work "
            "from an earlier chat, %d days ago, was never saved into your search. I have "
            "left it out in case it is out of date; say 'bring it in' if you want it.\" To "
            "bring it in when they ask: git merge %s" % (ref, days, OLD_DAYS, days, ref))


def _lacks(root: str, ref: str) -> list[str]:
    """The files a branch's own commits wrote that master does not have at all."""
    own = _own(root, ref)
    return [p for p in (own[0] if own else [])
            if _git(root, "cat-file", "-e", "%s:%s" % (ref, p)).returncode == 0
            and _git(root, "cat-file", "-e", "origin/master:" + p).returncode != 0]


def _some(paths: list[str]) -> str:
    return ", ".join(paths[:4]) + (" and %d more" % (len(paths) - 4) if len(paths) > 4 else "")


def left_line(ref: str, days: int, files: list[str], root: str = "",
              consume: bool = True) -> str:
    """The one line a landing says of a branch left behind, for Claude. Where the branch
    holds work master has none of, the person is told once: dropped whole and unsaid, a
    chat's new work was lost to them with no word."""
    if not files:
        return old_line(root or ROOT, ref, days, consume)
    root = root or ROOT
    line = ("left %s as it is: its own work is %d days older than master's later changes to the "
            "same files (%s), so bringing it in would put older copies over newer ones. It stays "
            "on GitHub, never deleted" % (ref, days, _some(files)))
    lacking = _lacks(root, ref)
    if not lacking:
        return line + "; nothing to tell the person"
    if consume and not _named_once(root, ref):
        return line + "; it also holds %s, which master lacks (the person was told)" % (
            _some(lacking))
    return (line + ". It also holds %s, which master lacks. Tell the person once: \"Some work "
            "from an earlier chat was never saved into your search, and part of it is older "
            "than what you have now, so I have left it out. Say 'bring it in' if you want it.\" "
            "To bring it in when they ask: git merge %s" % (_some(lacking), ref))


def fetch_waiting(root: str = ROOT) -> bool:
    """Every chat's branch as GitHub has it now: a chat's refs were only as fresh as its
    clone, and a long-kept chat never saw a branch pushed after it started (the stranger
    audit, 2026-11-03, X-34). Best effort; False where it could not be fetched."""
    spec = ["+refs/heads/%s*:refs/remotes/origin/%s*" % (p, p) for p in CHAT_BRANCHES]
    return _git(root, "fetch", "-q", "origin", "+refs/heads/master:refs/remotes/origin/master",
                *spec).returncode == 0


def ages(root: str, refs: list[str]) -> dict[str, int]:
    """{ref: whole days since its newest commit}."""
    now = time.time()
    out = {}
    for ref in refs:
        t = _git(root, "log", "-1", "--format=%ct", ref).stdout.strip()
        out[ref] = int((now - int(t)) // 86400) if t.isdigit() else 0
    return out


def unpushed(root: str = ROOT) -> int:
    """Commits here that no branch on GitHub holds, as this checkout last saw them."""
    r = _git(root, "rev-list", "--count", "HEAD", "--not", "--remotes=origin")
    return int(r.stdout.strip() or 0) if r.returncode == 0 and r.stdout.strip().isdigit() else 0


SAVE_HOLDS_A_DAY = 3
SAVE_HELD = "ljs-save-held.json"


def save_due(root: str = ROOT, chat: str = "", today: str = "") -> list[str]:
    """What the app's hook holds a turn for (tools/learned.py): the person's files no commit
    holds and commits no branch on GitHub holds, in a person's own copy, while no landing
    runs. A chat that skipped its once-a-turn landing lost quick edits and taps with its
    computer, and nobody was told (the stranger audit, 2026-11-03, X-62). Counts the hold:
    [] once this chat was held SAVE_HOLDS_A_DAY times today, or where the count cannot be
    kept (a hold that cannot be counted could never let go). Never raises."""
    try:
        top = _git(root, "rev-parse", "--show-toplevel").stdout.strip()
        if not top or os.path.realpath(top) != os.path.realpath(root) or _the_app(root) \
                or not os.path.isfile(os.path.join(root, "profile", "person.json")) \
                or landing(root) or wanted(root):
            return []
        import save_state
        files = save_state.unsaved(root)
        n = unpushed(root)
        if not files and not n:
            return []
        path = os.path.join(git_dir(root), SAVE_HELD)
        try:
            with open(path, encoding="utf-8") as fh:
                held = json.load(fh)
        except (OSError, ValueError):
            held = {}
        held = held if isinstance(held, dict) else {}
        day = today or time.strftime("%Y-%m-%d")
        rec = held.get(chat) if isinstance(held.get(chat), dict) else {}
        count = int(rec.get("n") or 0) if rec.get("day") == day else 0
        if count >= SAVE_HOLDS_A_DAY:
            return []
        held[chat] = {"day": day, "n": count + 1}
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(held, fh)
        return files[:5] + (["%d commit(s) not on GitHub" % n] if n else [])
    except Exception:  # noqa: BLE001  a hook must never break the chat
        return []


STRANDED_DAYS = 1


def stranded(root: str = ROOT, fetch: bool = False) -> dict[str, int]:
    """{branch: days} for the person's work that has waited off master a day or more: past
    the landings that would have brought it in, so something keeps it out (a check that is
    not green, a save GitHub refuses). Read by the start and said once (X-30)."""
    if fetch:
        fetch_waiting(root)
    got = ages(root, waiting(root))
    return {r: d for r, d in got.items() if d >= STRANDED_DAYS}


def _driver(root: str) -> None:
    """The row-by-row merge, set before anything is merged here: config is never committed,
    and a fresh clone (every job's chat) had none (X-2)."""
    try:
        import merge_state
        merge_state.install(root)
    except Exception:  # noqa: BLE001  git merges lines, as it would have
        pass


# An application's documents are made together, from one draft: its resume and its letter
# (cv/ and cover_letters/, the .tex and the .pdf made from it) and, in its folder, the draft
# they were rendered from and what was made with it. Merged file by file, line by line, an
# older chat's bullets came back into a newer resume's .tex beside a .pdf made without them,
# and that chat's draft.json and letters came in with no word (the maintainer, 2026-11-04).
# So an application both sides changed comes whole from one side: this chat's, when it is
# another chat's branch being brought in and this chat changed it; else the side that changed
# it last. The posting, the interview prep, the outcome and the person's own answers in the
# folder are not made from the draft, and merge as any other file.
APP_FOLDER = "documents/applications/"
APP_DOCS = ("cv/", "cover_letters/")
MADE = ("draft.json", "drafts.json", "cost.json", "verify.json", "tweaks.json", "outreach.md",
        "screening_answers.md")
MADE_EXT = (".tex", ".pdf")
_DOC_ABBR = re.compile(r"_(?:Resume|CV|Cover_Letter)_([A-Za-z0-9_]+)$")
# The order made since 2026-11-06, <Prefix>_<ABBR>_<kind>: the kind last.
_DOC_KIND_LAST = re.compile(r"^(.+?)_(?:Resume|CV|Cover_Letter)$")
_KINDS = ("Resume", "CV", "Cover_Letter")


def _doc_abbr(stem: str) -> str:
    """The abbreviation in a resume or letter's name, in either order. The profile's own
    prefix and noun tell where the abbreviation starts (docpaths.doc_abbr); without a
    profile, the name before its kind word stands for it, the same for both documents."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import docpaths
        got = docpaths.doc_abbr(stem)
        if got:
            return got
    except Exception:  # noqa: BLE001  no profile here: the plain reading below
        pass
    m = _DOC_ABBR.search(stem) or _DOC_KIND_LAST.search(stem)
    return m.group(1) if m else ""


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _draft(root: str, rev: str, folder: str) -> dict:
    """The draft an application's folder holds at `rev` ({} when none can be read)."""
    r = _git(root, "show", "%s:%s%s/draft.json" % (rev, APP_FOLDER, folder))
    try:
        d = json.loads(r.stdout) if r.returncode == 0 else {}
    except ValueError:
        return {}
    if isinstance(d, list):
        d = d[0] if d and isinstance(d[0], dict) else {}
    return d if isinstance(d, dict) else {}


def units(root: str, paths, revs: tuple[str, ...]) -> tuple[dict[str, str], dict[str, str]]:
    """({path: application}, {application: its employer, where a draft names it}) for each of
    `paths` that is one of an application's made documents. A resume and a letter are known
    by the abbreviation their names end in, which the application's draft.json names (read at
    each of `revs`); a folder with no draft is known by its name."""
    import personal_paths
    paths = [p for p in paths if personal_paths.is_personal(p)]

    def folder_of(p: str) -> tuple[str, str]:
        rest = p[len(APP_FOLDER):] if p.startswith(APP_FOLDER) else ""
        f, _, name = rest.partition("/")
        return (f, name) if f and name and "/" not in name else ("", "")

    drafts: dict[str, dict] = {}

    def draft(f: str) -> dict:
        if f not in drafts:
            drafts[f] = next((d for d in (_draft(root, rev, f) for rev in revs) if d), {})
        return drafts[f]

    for p in paths:
        if folder_of(p)[0]:
            draft(folder_of(p)[0])
    named = sorted({str(d.get("abbr") or "") for d in drafts.values()} - {""}, key=len,
                   reverse=True)
    out: dict[str, str] = {}
    for p in paths:
        top, _, name = p.partition("/")
        if top + "/" not in APP_DOCS or "/" in name or not name:
            continue
        stem = name.split(".", 1)[0]
        abbr = next((a for a in named if stem.endswith("_" + a)
                     or any(stem.endswith("_%s_%s" % (a, k)) for k in _KINDS)), "")
        out[p] = _key(abbr or _doc_abbr(stem)) or "doc:" + stem
    docs = set(out.values())
    homes: dict[str, str] = {}
    for p in paths:
        f, name = folder_of(p)
        if not f or (name not in MADE and not name.endswith(MADE_EXT)):
            continue
        out[p] = (_key(draft(f).get("abbr")) or
                  next((k for k in docs if f == k or f.endswith("_" + k)), "") or "folder:" + f)
        homes.setdefault(out[p], f)
    # A resume and a letter whose folder neither side changed: their folder, for the employer.
    if docs - set(homes):
        listed = _git(root, "ls-tree", "--name-only", "HEAD", APP_FOLDER).stdout.splitlines()
        for k in docs - set(homes):
            hit = [f[len(APP_FOLDER):] for f in listed
                   if f[len(APP_FOLDER):] == k or f.endswith("_" + k)]
            if len(hit) == 1:
                homes[k] = hit[0]
    employer = {k: str(draft(f).get("company") or "") for k, f in homes.items()}
    return out, {k: v for k, v in employer.items() if v}


def _changed(root: str, a: str, b: str) -> list[str]:
    r = _git(root, "diff", "--name-only", "--no-renames", "-z", a, b)
    return [p for p in r.stdout.split("\0") if p] if r.returncode == 0 else []


def _row_merged(root: str, paths) -> set[str]:
    """The paths the row-by-row driver merges (.gitattributes merge=ljs-state): both chats'
    rows are kept there, so neither side's whole file is ever taken over the other's."""
    paths = list(paths)
    if not paths:
        return set()
    r = _git(root, "check-attr", "-z", "merge", "--", *paths)
    parts = r.stdout.split("\0")
    return {parts[i] for i in range(0, len(parts) - 2, 3) if parts[i + 2] == "ljs-state"}


def _last(root: str, rng: str, paths) -> int:
    got = _git(root, "log", "-1", "--format=%ct", rng, "--", *paths).stdout.strip()
    return int(got) if got.isdigit() else 0


def _held(root: str, ref: str, mine, sweep: bool = True) -> tuple[dict[str, str], list[str]]:
    """({path: the side whose whole copy is kept, "HEAD" or ref}, lines for Claude) for a
    merge of `ref` into HEAD, decided before git merges a line of it.

    - An application both sides changed: every made document of it from one side (units):
      this chat's where `mine` (the files this chat's own commits changed) names one of its
      files, else the side that changed it last; this side on a tie. Master's merge is given
      `mine` too: given none, a tweak this chat had not landed yet was dropped for master's
      later copy with no word. Where this chat's copy is not the one kept, the person is told.
    - With `mine` and `sweep` (another chat's branch being brought in), a file outside any
      application that this chat changed and the branch changed too: this chat's whole file,
      never a line merge of the two. The person's own profile is the exception (what they
      told either chat is kept, and a clash is settled with them asked: merge_state.settle),
      and so is a state file the driver merges row by row, where both chats' rows are kept.
      Master's merge (no `sweep`) merges such a file line by line, and only a real clash
      takes one side whole (merge_state.settle, the other kept in its spare folder)."""
    base = _git(root, "merge-base", "HEAD", ref).stdout.strip()
    if not base:
        return {}, []
    ours, theirs = _changed(root, base, "HEAD"), _changed(root, base, ref)
    if not theirs:
        return {}, []
    mine = set(mine or ())
    unit, employer = units(root, set(ours) | set(theirs), ("HEAD", ref))
    held: dict[str, str] = {}
    said: list[str] = []
    for app in sorted({unit[p] for p in theirs if p in unit}):
        here = [p for p in ours if unit.get(p) == app]
        there = [p for p in theirs if unit.get(p) == app]
        if not here:
            continue
        everything = sorted(set(here) | set(there))
        ours_too = any(p in mine for p in here)
        if ours_too:
            side = "HEAD"
        elif _last(root, base + ".." + ref, there) > _last(root, base + "..HEAD", here):
            side = ref
        else:
            side = "HEAD"
        for p in everything:
            held[p] = side
        if ours_too:
            who = employer.get(app)
            line = ("%s: an application both chats changed; this chat's is kept whole (%s), and "
                    "none of %s's files for it came in (they stay in the saved history)"
                    % (app, ", ".join(everything), ref))
            # Only a document they would see: a check's own record changing is no news.
            if any(not p.endswith(("/cost.json", "/verify.json")) for p in there):
                line += (". Tell the person once: \"Another of your chats had also changed "
                         "your %s; the one you have now is kept, and the other is saved in "
                         "case you want it back.\"" % (("application to " + who) if who
                                                       else "application"))
            said.append(line)
        else:
            line = ("%s: an application both sides changed; the later one is kept, every "
                    "file of it from %s (%s)" % (app, "this side" if side == "HEAD" else ref,
                                                 ", ".join(everything)))
            # This chat's copy of a document they would see is not the one kept: said.
            if side != "HEAD" and any(not p.endswith(("/cost.json", "/verify.json"))
                                      for p in here):
                who = employer.get(app)
                line += (". Tell the person once: \"Two of your chats changed your %s at the "
                         "same time; the newer one is kept, and the other is saved in case you "
                         "want it back.\"" % (("application to " + who) if who
                                              else "application"))
            said.append(line)
    if mine and sweep:
        row = _row_merged(root, theirs)
        whole = sorted(p for p in theirs if p in mine and p not in held and p not in row
                       and not p.startswith("profile/"))
        for p in whole:
            held[p] = "HEAD"
        if whole:
            said.append("this chat's whole copy kept of %d file(s) %s also changed (%s), with "
                        "nothing of the other's merged into it; the other's stay in the saved "
                        "history" % (len(whole), ref, ", ".join(whole)))
    return held, said


def _take(root: str, path: str, side: str) -> bool:
    """`path` as `side` has it, in the merge under way: its copy, or gone where it has none."""
    if _git(root, "cat-file", "-e", "%s:%s" % (side, path)).returncode == 0:
        return _git(root, "checkout", side, "--", path).returncode == 0
    r = _git(root, "rm", "-q", "-f", "--ignore-unmatch", "--", path)
    full = os.path.join(root, path)
    if os.path.isfile(full):
        os.remove(full)
    return r.returncode == 0


# A search's committed files, by its round's name (run_round.py ROUND_NAME): its summary
# (documents/rounds/<name>.json) and its left-out list (filtered/<name>.json), which names
# the round inside it. Two job chats are two fresh clones, and each named its search r43
# (the maintainer's copy, 2026-11-06): merged, the driver made one list of the two, or one
# was kept over the other.
ROUND_FILE = re.compile(r"^documents/rounds/(?:filtered/)?r(\d+)((?:_round\d+)?)\.json$")
_ROUND_SAYS = re.compile(r'("round"\s*:\s*")r\d+((?:_round\d+)?")')


def _round_blobs(root: str, rev: str) -> dict[str, str]:
    """{path: blob} of every round file `rev` holds, or {} where it holds none."""
    r = _git(root, "ls-tree", "-r", rev, "--", "documents/rounds/")
    out = {}
    for ln in r.stdout.splitlines() if r.returncode == 0 else []:
        meta, _, path = ln.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and ROUND_FILE.match(path):
            out[path] = parts[2]
    return out


def _round_numbers(root: str, *maps: dict) -> set[int]:
    """Every round number named anywhere this landing can see: the revisions read, and here
    the summaries and the round folders this copy has on disk."""
    nums = {int(ROUND_FILE.match(p).group(1)) for m in maps for p in m}
    for folder in (os.path.join(root, "documents", "rounds"), os.path.join(root, "rounds")):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        nums |= {int(m.group(1)) for n in names
                 for m in [re.match(r"^r(\d+)(?:_round\d+)?(?:\.json)?$", n)] if m}
    return nums


def _summaries(blobs: dict[str, str], num: int) -> dict[str, str]:
    return {p: b for p, b in blobs.items() if "/filtered/" not in p
            and int(ROUND_FILE.match(p).group(1)) == num}


def _round_clash(root: str, ref: str) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """([(side renamed, side kept, path, new path)], lines for Claude) for a merge of `ref`
    into HEAD: each round number both sides gave a different search since they parted. The
    one master holds keeps its name (master's own merge renames this chat's); else this
    chat's keeps it and the one brought in takes the next free number. The same search met
    twice (one summary on both sides) is never renamed."""
    base = _git(root, "merge-base", "HEAD", ref).stdout.strip()
    if not base:
        return [], []
    was, ours, theirs = (_round_blobs(root, r) for r in (base, "HEAD", ref))
    master = _round_blobs(root, "origin/master") if ref != "origin/master" else theirs
    added = {side: {p: b for p, b in got.items() if p not in was}
             for side, got in (("HEAD", ours), (ref, theirs))}
    nums = sorted({int(ROUND_FILE.match(p).group(1)) for p in added["HEAD"]} &
                  {int(ROUND_FILE.match(p).group(1)) for p in added[ref]})
    taken = _round_numbers(root, was, ours, theirs, master)
    moves: list[tuple[str, str, str, str]] = []
    said: list[str] = []
    for n in nums:
        mine, other = _summaries(added["HEAD"], n), _summaries(added[ref], n)
        if not mine or not other or mine == other:
            continue
        held = _summaries(master, n)
        side = "HEAD" if ref == "origin/master" or (held and held == other) else ref
        keep = ref if side == "HEAD" else "HEAD"
        new = max(taken, default=0) + 1
        taken.add(new)
        for p in sorted(added[side]):
            m = ROUND_FILE.match(p)
            if int(m.group(1)) == n:
                moves.append((side, keep, p, p.replace("r%d%s.json" % (n, m.group(2)),
                                                       "r%d%s.json" % (new, m.group(2)))))
        said.append("two searches were both named r%d; the one %s is r%d now, and both are "
                    "kept. Nothing to say about it" % (
                        n, "this chat made" if side == "HEAD" else "from " + ref, new))
    return moves, said


def _move_rounds(root: str, moves) -> None:
    """Each renamed search, in the merge under way: its files under their new names (the name
    inside its left-out list too), and the old names as the side kept has them."""
    for side, keep, old, new in moves:
        text = _git(root, "cat-file", "blob", "%s:%s" % (side, old)).stdout
        if "/filtered/" in old:
            name = os.path.splitext(os.path.basename(new))[0]
            text = _ROUND_SAYS.sub(lambda m, name=name: m.group(1) + name + '"', text, count=1)
        full = os.path.join(root, new)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        _git(root, "add", "-f", "--", new)
        _take(root, old, keep)


def _move_round_folders(root: str, moves) -> None:
    """This chat's own round folders (never saved: rounds/<name>) renamed with their search,
    and the name its round.log gives, which page_db.search_run reads."""
    seen = set()
    for side, _keep, old, new in moves:
        if side != "HEAD" or "/filtered/" in old:
            continue
        a, b = (os.path.splitext(os.path.basename(p))[0] for p in (old, new))
        if a in seen:
            continue
        seen.add(a)
        src, dst = os.path.join(root, "rounds", a), os.path.join(root, "rounds", b)
        if not os.path.isdir(src) or os.path.exists(dst):
            continue
        try:
            os.rename(src, dst)
            log = os.path.join(dst, "round.log")
            if os.path.isfile(log):
                with open(log, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                with open(log, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(re.sub(r"(?m)^round: %s\s*$" % re.escape(a), "round: " + b, text))
        except OSError:
            pass


def merge_in(root: str, ref: str, mine=None, sweep: bool = True) -> tuple[bool, list[str]]:
    """git merge --no-edit <ref>, with every conflicted file of the person's settled
    (merge_state.settle) and the merge committed. (merged, lines for Claude). Not merged: the
    merge is aborted and nothing has changed.

    An application both sides changed comes whole from one side, this chat's where `mine`
    (the files this chat's own commits changed) names one of its files; and with `sweep`
    (another chat's branch being brought in) a file this chat changed keeps this chat's
    whole copy (_held): a line merge of the two is never made under a line that says one was
    kept. The side not kept of each such file is kept in the spare folder here
    (merge_state.SPARE_DIR) as well as in the saved history."""
    import merge_state
    _driver(root)
    held, told = _held(root, ref, mine, sweep)
    # Two searches under one name: one renamed, neither merged into the other (_round_clash).
    moves, named = _round_clash(root, ref)
    for _side, _keep, p, _new in moves:
        held.pop(p, None)
    told = told + named
    if not held and not moves:
        r = _git(root, "merge", "--no-edit", ref)
        if r.returncode == 0:
            return True, []
    else:
        r = _git(root, "merge", "--no-edit", "--no-commit", "--no-ff", ref)
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0:
        if r.returncode == 0:
            return True, []
        return False, ["%s could not be merged: %s" % (ref, _said(r))]
    for p, side in sorted(held.items()):
        lost = _git(root, "rev-parse", "-q", "--verify",
                    "%s:%s" % (ref if side == "HEAD" else "HEAD", p)).stdout.strip()
        kept = _git(root, "rev-parse", "-q", "--verify", "%s:%s" % (side, p)).stdout.strip()
        if lost and lost != kept:
            try:
                merge_state._spare(root, p, lost)
            except OSError:
                pass
    bad = [p for p, side in sorted(held.items()) if not _take(root, p, side)]
    _move_rounds(root, moves)
    done, left = merge_state.settle(root)
    left = bad + left
    still = [p for p in _git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
             if p]
    if not left and not still:
        c = _git(root, "commit", "--no-edit", "-q")
        if c.returncode == 0:
            _move_round_folders(root, moves)
            return True, told + ["two chats changed the same file at once (%s): %s" % (ref, d)
                                 for d in done]
        left = ["the commit: " + _said(c)]
    _git(root, "merge", "--abort")
    return False, ["a conflict in %s" % ", ".join(left or still)]


def land(root: str = ROOT, message: str = "", check=None, sleep=time.sleep) -> int:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        print("land: not a git checkout; nothing was pushed")
        return 2
    if _the_app(root):
        print("land: this is the app itself, which lands through its own pull request and CI "
              "(MAINTAINING.md); nothing was pushed")
        return 2
    with _holding(root, pass_on=False) as mine:
        if not mine:
            # Queued, never run beside it: the running one takes it before it lets go, or the
            # next one does (two checks side by side each took over ten minutes, 2026-11-06).
            _ask(root, message)
            print("land: another landing is running in this checkout; it saves this work too "
                  "when it ends. Nothing to do or say")
            return 0
        code = _land(root, message, check, sleep)
        # A save asked for while this ran (another chat, a tap): taken here, one at a time,
        # while this still holds the lock. A detached run takes its own between rounds.
        d = git_dir(root)
        inside = bool(d) and _lock_key(d) in _RUN
        n = 0
        while not inside and code == 0 and n < QUEUED_ROUNDS and _asked(root):
            n += 1
            _asked_too, msg = _take_ask(root)
            if not _work_since_push(root):
                continue
            print("land: work asked for while this ran is saved too; where steps follow, they "
                  "replace any above")
            code = _land(root, msg or message, check, sleep)
    if not inside and _asked(root):
        # Asked in the moment this one let go, or while it ran and it stopped short: another
        # chat was told its work is saved too, so the next one is started for it now, whatever
        # this one's own end (its result kept for a chat in RESULT_FILE).
        _next(root)
    # Work written while this ran (a second turn, a quick tap) was in no commit, and nothing
    # started a landing for it once this one ended (the stranger audit, 2026-11-03, X-62).
    try:
        import save_state
        later = save_state.unsaved(root)
    except Exception:  # noqa: BLE001
        later = []
    if later:
        print("land: %d file(s) of the person's were written while this ran and are not saved "
              "yet (%s): once this landing's calls are made, run python3 tools/land.py again, "
              "in the background" % (len(later), ", ".join(later[:4]) +
                                     (" ..." if len(later) > 4 else "")))
    return code


def _land(root: str, message: str, check, sleep) -> int:
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        print("land: a merge is already under way here; finish it or abort it first. "
              "Nothing was pushed")
        return 2

    try:
        import save_state
        old = save_state.old_unsaved(root)
    except Exception:  # noqa: BLE001
        old = []
    if old:
        print("land: %d file(s) here were last written over %d days ago and never saved (%s); "
              "they are the files as they stand now, so they are saved, and nothing older is "
              "put over anything newer. Tell the person once: \"Some of your work from over "
              "a week ago had not been saved; it is now.\"" % (len(old), save_state.OLD_DAYS,
                                                               ", ".join(old[:3])))
    ok, why = _stage(root)
    if not ok:
        print("land: saving stopped: %s; nothing was pushed" % why)
        _told("disk" if DISK_FULL.search(why) or why == "the disk here is full" else "")
        return 2
    if _git(root, "diff", "--cached", "--quiet").returncode != 0:
        r = _git(root, "commit", "-q", "-m", message.strip() or DEFAULT_MESSAGE)
        if r.returncode != 0:
            print("land: the commit was refused: %s; nothing was pushed" % _said(r))
            _told(_trouble(r))
            return 2

    r = _retried(root, "fetch", "-q", "origin", "master", sleep=sleep)
    if r.returncode != 0:
        print("land: master could not be fetched: %s; nothing was pushed" % _said(r))
        _told(_trouble(r))
        return 2
    # An application this chat changed keeps this chat's copy over master's too (_held).
    own = _own(root, "HEAD")
    ok, said = merge_in(root, "origin/master", mine=set(own[0]) if own else None, sweep=False)
    for ln in said if ok else []:
        print("land: " + ln)
    if not ok:
        _wait_on_branch(root, "land: " + (said[0] if said else "master could not be merged"),
                        sleep)
        return 2
    # Whatever earlier chats and runs left waiting comes in with this landing (X-34).
    if fetch_waiting(root):
        refs, left = _chat_branches(root)
        for ref, (days, files) in left.items():
            print("land: " + left_line(ref, days, files, root))
        # What this chat changed itself keeps this chat's whole copy over theirs (_held).
        own = _own(root, "HEAD") if refs else None
        mine = set(own[0]) if own else set()
        for ref in refs:
            ok, said = merge_in(root, ref, mine=mine)
            if ok:
                print("land: brought in work that waited on %s" % ref)
            for ln in said:
                print("land: " + ln if ok else "land: left %s as it is: %s" % (ref, ln))
        _commit_said(root)

    ahead =_git(root, "rev-list", "--count", "origin/master..HEAD").stdout.strip()
    if ahead in ("", "0"):
        print("land: nothing to land")
        return 0

    # The person's own tests an update broke, not in line yet: set aside for this save, never
    # holding it, and their bringing in line queued for a background step that needs nobody
    # (the own-tests improvement). A job's chat that was told to fix them first missed the
    # line, and its finished work was stuck behind five tests an update changed (the
    # maintainer's copy, 2026-11-06). Any other failure still stops the save.
    owed = _own_tests_owed(root)
    aside = _set_aside(root, owed)
    if owed:
        queued = False
        try:
            import profile_upgrades
            queued = profile_upgrades.queue_own_tests(root)
        except Exception:  # noqa: BLE001  the landing goes on; the next sync lists it
            pass
        print("land: %d of the person's own tests an update changed are set aside for this "
              "save%s; nothing to say about it" % (
                  len(owed), "; bringing them in line is queued for the background"
                  if queued else ""))
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    mine_only = None if check or os.environ.get("LJS_LAND_CHECK", "").strip() else \
        data_only(root)
    computer = on_computer()
    if head and head == pushed(root):
        # Exactly what the last landing checked green and pushed: never checked again (a save
        # queued behind another, with nothing new, ran a second ten-minute check).
        rc, out = 0, CHECKED_ALREADY
    elif computer and not check:
        # A chat on the person's computer checks nothing but its data: the chat that answers
        # the page in the cloud brings the branch in and checks it as it lands (on_computer).
        bad = data_check(root, mine_only) if mine_only else []
        rc = 1 if bad else 0
        out = "".join("  %s  FAIL\n" % b for b in bad)
    elif mine_only:
        # Only the person's own data: read cleanly, then landed at once (data_only).
        bad = data_check(root, mine_only)
        rc = 1 if bad else 0
        out = "".join("  %s  FAIL\n" % b for b in bad) if bad else \
            DATA_CHECKED % len(mine_only)
    else:
        _send_early(root, sleep)
        rc, out = _run_check(root, _check_command(root, check), aside)
        if _taken_meanwhile(root, sleep):
            return _after_merge(root, sleep)
    if rc != 0:
        own = own_tests_only(out)
        if own:
            # More of their own tests the update broke than the record knew (a run on another
            # computer, a test that fails only beside another): set aside with the rest, the
            # bringing in line queued, and checked once more, never held for them.
            known = _recorded_failures(root)
            names = [n for n, _m in own if n not in {k for k, _ in known}]
            _record_own(root, known + [(n, m) for n, m in own if n in names])
            aside = _set_aside(root, [k for k, _ in known] + names)
            try:
                import profile_upgrades
                profile_upgrades.queue_own_tests(root)
            except Exception:  # noqa: BLE001
                pass
            rc, out = _run_check(root, _check_command(root, check), aside)
            own = own_tests_only(out) if rc != 0 else None
            if rc == 0:
                print("land: %d more of the person's own tests an update changed are set aside "
                      "for this save; nothing to say about it" % len(names))
    if rc != 0:
        if own is not None:
            # Only the person's own tests, which an update changed what they check: said as
            # that, with the step, never as a generic failure (a person's copy, 2026-11-05:
            # two finished jobs could not be saved and nothing said why). The work is kept.
            _record_own(root, own or [("profile/tests", "")])
            _wait_on_branch(root, OWN_TESTS_HEAD, sleep)
            print(OWN_TESTS_DO)
            for ln in failing(out):
                print(ln)
            return 1
        _wait_on_branch(root, "land: not green", sleep)
        for ln in failing(out):
            print(ln)
        return 1
    if not aside and re.search(r"^\s+pytest \(profile/tests, on this person\)\s+PASS", out,
                               re.M):
        _record_own(root, [])             # they pass now: no command says the step again

    name, why = _own_branch(root)
    if not name:
        print("land: a branch could not be made: %s; nothing was pushed" % why)
        return 2
    there, r = _push(root, name, sleep)
    if r.returncode != 0:
        print("land: the push was refused: %s; nothing was pushed" % _said(r))
        _told(_trouble(r))
        return 2
    _record_pushed(root, name)
    if computer:
        # Never a pull request from the person's computer: Claude's own safety check there
        # refused the merge ("merge without review") at the last step of a save, twice in one
        # evening (the maintainer's computer, 2026-11-10). The work waits on its branch, and
        # the chat that answers the page in the cloud brings it to master with its next save
        # (every landing brings in what waits: waiting()).
        READY.clear()
        print(COMPUTER_PUSHED % there)
        return 0

    owner, repo = _slug(root)
    title = (message.strip().splitlines() or [DEFAULT_MESSAGE])[0][:70]
    skipped = _skips(out)
    body = (out.strip().rstrip(".") if mine_only and out.startswith("Checked here: only") else
            "Checked here with ./tools/ci_local.sh --quick: green" +
            ("; skipped: " + ", ".join(skipped) if skipped else "")) + "."
    READY.clear()
    READY.update({"owner": owner, "repo": repo, "head": there, "title": title, "body": body})
    print("land: ready %s (%s commit(s) ahead of master)" % (there, ahead))
    print("land: next, each its own call, and nothing said to the person:")
    print('  1. create_pull_request: owner "%s", repo "%s", head "%s", base "master", '
          'title "%s", body "%s"' % (owner, repo, there, title.replace('"', "'"), body))
    # A cloud chat is subscribed to each pull request it opens, and every save then woke it
    # twice more, "subscribed" and "merged": a dozen saves in 20 minutes (the maintainer's
    # copy, 2026-11-06). Unsubscribed at once, before the merge can send its event.
    print('  1b. at once, before anything else: unsubscribe_pr_activity: owner "%s", repo "%s", '
          'pullNumber <the number 1 gave>, where this chat has that tool' % (owner, repo))
    print('  2. merge_pull_request: owner "%s", repo "%s", pullNumber <the number 1 gave>, '
          'merge_method "merge"' % (owner, repo))
    print("  3. python3 tools/land.py --after-merge")
    print("  " + MERGE_REFUSED)
    # Plain REST calls: `gh pr create` and `gh pr merge` are refused in a cloud chat, and
    # these went through (2026-11-05).
    print("  No GitHub tools in this chat: each on its own line, then 3:")
    print("    " + rest_create(owner, repo, there, title, body))
    print("    " + rest_merge(owner, repo))
    return 0


def keep(root: str = ROOT, message: str = "", sleep=time.sleep) -> int:
    """--keep: this chat's work saved and pushed to its own branch, with no check, no merge
    and no pull request, in seconds: what a finished job chat whose work never reached GitHub
    is asked to do (tidy.py close). The next landing anywhere brings it in (waiting())."""
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        print("land: not a git checkout; nothing was pushed")
        return 2
    if _the_app(root):
        print("land: this is the app itself, which lands through its own pull request and CI "
              "(MAINTAINING.md); nothing was pushed")
        return 2
    with _holding(root, pass_on=False) as mine:
        if not mine:
            _ask(root, message)
            print("land: another landing is running in this checkout; it saves this work too "
                  "when it ends. Nothing to do or say")
            return 0
        return _keep(root, message, sleep)


def _keep(root: str, message: str, sleep) -> int:
    """keep's own steps, under a lock the caller holds: staged, committed, pushed to this
    chat's branch."""
    ok, why = _stage(root)
    if not ok:
        print("land: saving stopped: %s; nothing was pushed" % why)
        return 2
    if _git(root, "diff", "--cached", "--quiet").returncode != 0:
        r = _git(root, "commit", "-q", "-m", message.strip() or DEFAULT_MESSAGE)
        if r.returncode != 0:
            print("land: the commit was refused: %s; nothing was pushed" % _said(r))
            return 2
    _retried(root, "fetch", "-q", "origin", "master", sleep=sleep)
    if _git(root, "rev-list", "--count", "origin/master..HEAD").stdout.strip() in ("", "0"):
        print("land: nothing to keep: this copy holds no work master lacks")
        return 0
    _wait_on_branch(root, "land: kept, not checked", sleep)
    name = _remote_name(branch(root))
    there = _git(root, "rev-parse", "-q", "--verify", "refs/remotes/origin/" + name)
    return 0 if there.stdout.strip() == _git(root, "rev-parse", "HEAD").stdout.strip() else 2


def rest_create(owner: str, repo: str, head: str, title: str, body: str) -> str:
    """The pull request opened by GitHub's REST interface through gh, with the real owner and
    repo: the one form a cloud chat lets through when it has no GitHub tools."""
    return "gh api -X POST repos/%s/%s/pulls -f title=%s -f head=%s -f base=master -f body=%s" % (
        owner, repo, shlex.quote(title), shlex.quote(head), shlex.quote(body))


def rest_merge(owner: str, repo: str, number: str = "<the number it gave>") -> str:
    return "gh api -X PUT repos/%s/%s/pulls/%s/merge -f merge_method=merge" % (owner, repo, number)


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
        ok, said = merge_in(root, "origin/master")
        if not ok:
            print("land: landed, but master could not be merged into this branch's newer work: "
                  "%s; nothing changed, and the next landing merges it"
                  % (said[0] if said else "no words from git"))
            return 2
        for ln in said:
            print("land: " + ln)
        # "Newer work" that, master merged in, holds nothing master lacks (merges that
        # _clean_merges could not tell clean, as on a git before 2.38): no work of its own,
        # so it starts from master like any other, and is never left commits ahead of GitHub.
        if _git(root, "rev-parse", "HEAD^{tree}").stdout.strip() != \
                _git(root, "rev-parse", "origin/master^{tree}").stdout.strip():
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
    if name:
        _level(root, name, sleep)
    print("land: landed; %s starts from master now" % (name or "this chat"))
    return 0


def _level(root: str, name: str, sleep) -> None:
    """GitHub's copy of this branch moved up to master with it, a plain fast-forward (its
    work is on master, so master holds the copy's commit). Left at the commit the landing
    pushed, the branch stood one merge commit (master's own) ahead of its copy on GitHub, and
    a check for unpushed work held the chat for it until it was pushed by hand (a live
    session, 2026-11-05). Never forced; where it cannot be moved, one line says so."""
    there = _remote_name(name)
    if _git(root, "rev-parse", "-q", "--verify", "refs/remotes/origin/" + there).stdout.strip() \
            == _git(root, "rev-parse", "HEAD").stdout.strip():
        return
    _where, r = _push(root, name, sleep)
    if r.returncode != 0:
        print("land: GitHub's copy of %s stays where the landing pushed it (%s); nothing is "
              "lost, and the next landing moves it" % (there, _said(r)))
        _told(_trouble(r))


READY: dict = {}            # what the last landing pushed, for its pull request


def wanted(root: str = ROOT) -> bool:
    """Is a detached landing asked for and not finished (its mark younger than
    LOCK_STALE_S)?"""
    d = git_dir(root)
    p = os.path.join(d, WANTED_FILE) if d else ""
    if not p:
        return False
    # Aged on the clock that wrote it, its own "at", as the lock is (landing): the file's
    # time is the disk's clock, and on a clock moved a month on, a mark a second old read as
    # stale, so the hook held the turn the background save was already taking (4.11.0's
    # clock-moved-on runs). A mark with no stamp is aged by the file.
    try:
        with open(p, encoding="utf-8") as fh:
            began = float(json.loads(fh.read() or "{}").get("at"))
    except (OSError, ValueError, TypeError, AttributeError):
        try:
            began = os.path.getmtime(p)
        except OSError:
            return False
    age = time.time() - began
    if age >= LOCK_STALE_S:
        return False
    # Owned only while a landing is alive to take it (or for the moment one takes to start):
    # a save queued behind one that then stopped, or behind an older version's landing that
    # never reads the queue, sat here unowned while the hook held nobody for it, and the work
    # could go with the chat's computer (the release review, 2026-11-06).
    return age < WANTED_GRACE_S or landing(root)


WANTED_GRACE_S = 60


def _mark(root: str, name: str, text: str = "") -> str:
    d = git_dir(root)
    if not d:
        return ""
    p = os.path.join(d, name)
    try:
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text or lock_text())
    except OSError:
        return ""
    return p


def _unmark(root: str, name: str) -> None:
    d = git_dir(root)
    if d:
        try:
            os.remove(os.path.join(d, name))
        except OSError:
            pass


def detach(root: str = ROOT, message: str = "", popen=subprocess.Popen) -> int:
    """Start the landing in a process of its own and return at once: one line, nothing to
    wait for. A landing already running is only asked to land again once it ends: the lock is
    taken here, in one step, and handed to the process started, so two asked together never
    start two (each started its own, and each ran the check, 2026-11-06)."""
    if _the_app(root):
        print("land: this is the app itself, which lands through its own pull request and CI "
              "(MAINTAINING.md); nothing was pushed")
        return 2
    _ask(root, message)
    token = _take_lock(root)
    if not token:
        print("land: saving in the background (one already running saves this too).")
        return 0
    d = git_dir(root)
    log = os.path.join(d, LOG_FILE) if d else os.devnull
    try:
        out = open(log, "w", encoding="utf-8", newline="\n")
    except OSError:
        out = subprocess.DEVNULL
    kw = {"start_new_session": True} if os.name == "posix" else \
        {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0)
         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    try:
        child = popen([sys.executable, os.path.abspath(__file__), "--run-detached", "--message",
                       message, "--lock", token], cwd=root, stdin=subprocess.DEVNULL,
                      stdout=out, stderr=subprocess.STDOUT, close_fds=True, **kw)
    except OSError as e:
        _drop_lock(root, token)
        _unmark(root, WANTED_FILE)
        print("land: the background save could not start (%s): run python3 tools/land.py in "
              "the background instead" % e)
        return 2
    _hand_over(root, token, getattr(child, "pid", 0))
    print("land: saving in the background; nothing to wait for or say.")
    return 0


def _gh_api(root: str, args: list[str], run=subprocess.run) -> tuple[int, dict | list | None, str]:
    """gh api, its JSON answer: (exit code, the answer or None, what it said)."""
    try:
        r = run(["gh", "api", *args], cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, None, str(e)
    try:
        got = json.loads(r.stdout) if (r.stdout or "").strip() else None
    except ValueError:
        got = None
    return r.returncode, got, " ".join(((r.stderr or "") + " " + (r.stdout or "")).split())[:240]


def finish_on_github(root: str, ready: dict, run=subprocess.run, which=None) -> tuple[bool, str]:
    """Open the pull request for what the landing pushed and merge it, through GitHub's REST
    interface (gh api), as the chat's own calls would. (True, "") when it is on master."""
    import shutil as _shutil
    if not (which or _shutil.which)("gh"):
        return False, "gh is not on this computer"
    o, r = ready["owner"], ready["repo"]
    code, got, said = _gh_api(root, ["-X", "POST", f"repos/{o}/{r}/pulls", "-f",
                                     f"title={ready['title']}", "-f", f"head={ready['head']}",
                                     "-f", "base=master", "-f", f"body={ready['body']}"], run)
    number = got.get("number") if isinstance(got, dict) else None
    if not number:
        # Opened already by an earlier landing of the same branch.
        code, got, said2 = _gh_api(root, [f"repos/{o}/{r}/pulls?head={o}:{ready['head']}"
                                          "&state=open"], run)
        number = got[0].get("number") if isinstance(got, list) and got and             isinstance(got[0], dict) else None
        if not number:
            return False, "the pull request could not be opened: " + (said or said2)
    code, got, said = _gh_api(root, ["-X", "PUT", f"repos/{o}/{r}/pulls/{number}/merge", "-f",
                                     "merge_method=merge"], run)
    if code != 0 or not (isinstance(got, dict) and got.get("merged")):
        return False, f"pull request {number} could not be merged: {said}"
    return True, str(number)


def _keep_result(root: str, lines: list[str]) -> None:
    d = git_dir(root)
    if not d:
        return
    p = os.path.join(d, RESULT_FILE)
    if not lines:
        try:
            os.remove(p)
        except OSError:
            pass
        return
    try:
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"at": time.time(), "lines": lines}, fh, indent=1)
            fh.write("\n")
    except OSError:
        pass


def github_waiting(root: str = ROOT) -> str:
    """What the last detached landing could not do (the GitHub calls, or a line for the
    person), said once, then forgotten: the next landing tries again by itself."""
    d = git_dir(root)
    p = os.path.join(d, RESULT_FILE) if d else ""
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
        os.remove(p)
    except (OSError, ValueError):
        return ""
    lines = [str(x) for x in (got.get("lines") if isinstance(got, dict) else None) or []]
    if not lines:
        return ""
    return "land: the last save in the background left this to do, once:\n" + "\n".join(lines)


def run_detached(root: str = ROOT, message: str = "", check=None, sleep=time.sleep,
                 land_fn=None, finish=None, token: str = "") -> int:
    """The detached landing itself: land, then the pull request and its merge on GitHub, then
    the branch moved to master, all under one lock (the one detach took and handed over, or
    taken here); again for every save asked for while it ran, and for work written while it
    ran (DETACHED_ROUNDS of those at most). A save asked for during its last round is never
    dropped: past QUEUED_ROUNDS it is left asked and the next landing is started for it.
    Everything it prints goes to its log; what a chat must still do goes to RESULT_FILE."""
    land_fn = land_fn or land
    finish = finish or finish_on_github
    token = _adopt(root, token) or _take_lock(root)
    if not token:
        print("land: another landing is running in this checkout; it saves this too")
        return 0
    d = git_dir(root)
    if d:
        _RUN.add(_lock_key(d))
    try:
        _settle(root, sleep, message)
        code = _rounds(root, message, check, sleep, land_fn, finish)
    finally:
        _drop_lock(root, token)
    if _asked(root):
        _next(root)            # asked after the last round it would take: the next one, now
    return code


QUEUED_ROUNDS = 12
# A save in the background asked for within SETTLE_S of the last one that landed waits out
# the rest of it, holding the lock, so every tap meanwhile is queued for it and one pull
# request takes them all: a dozen saves in 20 minutes opened a dozen, each waking the chat
# that answers the page twice (the maintainer's copy, 2026-11-06). The first save of a
# quiet spell goes at once.
SETTLE_S = 5 * 60
LANDED_FILE = "ljs-landed-at"


def _landed_at(root: str) -> float:
    d = git_dir(root)
    try:
        with open(os.path.join(d, LANDED_FILE), encoding="utf-8") as fh:
            return float(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


def _mark_landed(root: str) -> None:
    d = git_dir(root)
    if not d:
        return
    try:
        with open(os.path.join(d, LANDED_FILE), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("%f\n" % time.time())
    except OSError:
        pass


def _answers_page(root: str) -> bool:
    """Is this chat the one that answers the page, by this checkout's own record of it
    (app_listen's cache in the git folder)? A job's chat, or any chat about to end, is not."""
    try:
        import app_listen
        me = app_listen.this_chat()
        with open(os.path.join(git_dir(root), "ljs-listener.json"), encoding="utf-8") as fh:
            rec = (json.load(fh) or {}).get("listener") or {}
    except Exception:  # noqa: BLE001  unsure: never wait
        return False
    return bool(me) and str(rec.get("chat") or "") == me


def _settle(root: str, sleep, message: str = "") -> None:
    """Wait out what is left of SETTLE_S since the last landing, the lock kept alive: only
    in the chat that answers the page, and only once its work is committed and pushed to its
    own branch (_keep), so the wait delays the pull request, never the work's safety."""
    left = SETTLE_S - (time.time() - _landed_at(root))
    if left <= 0 or not _answers_page(root):
        return
    with contextlib.redirect_stdout(io.StringIO()):
        _keep(root, message, sleep)
    while left > 0:
        step = min(left, BEAT_S)
        sleep(step)
        _beat(root)
        left -= step


def _rounds(root: str, message: str, check, sleep, land_fn, finish) -> int:
    code, written, n = 0, 0, 0
    while n < QUEUED_ROUNDS:
        n += 1
        if n > 1:
            _settle(root, sleep, message)  # what was asked meanwhile goes in one pull request
        _asked_too, msg = _take_ask(root)
        message = msg or message
        _beat(root)
        READY.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = land_fn(root, message, check=check, sleep=sleep)
        said = buf.getvalue()
        sys.stdout.write(said)
        keep = [ln for ln in said.splitlines()
                if "tell the person" in ln.lower() or "Tell the person" in ln
                or REFUSED_SAY in ln or DISK_FULL_SAY in ln]
        if code == 0 and READY:
            ok, why = finish(root, dict(READY))
            if ok:
                _mark_landed(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    after_merge(root, sleep=sleep)
            else:
                at = said.find("land: next")
                keep = keep + ["land: GitHub's part could not be done here (%s); make these "
                               "calls:" % why] + \
                    [ln for ln in said[at:].splitlines()[1:] if ln.strip()]
        _keep_result(root, keep)
        if _asked(root):
            continue                   # a save asked for while this round ran: always taken
        if "were written while this ran" in said and written < DETACHED_ROUNDS - 1:
            written += 1
            continue
        break
    return code


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
    if "--keep" in argv:
        msg = argv[argv.index("--message") + 1] if "--message" in argv and \
            argv.index("--message") + 1 < len(argv) else ""
        return keep(root, msg, sleep=sleep)
    if "--detach" in argv or "--run-detached" in argv:
        msg = ""
        if "--message" in argv and argv.index("--message") + 1 < len(argv):
            msg = argv[argv.index("--message") + 1]
        if "--run-detached" in argv:
            # The lock detach took for this process; started by an older version, none.
            token = ""
            if "--lock" in argv and argv.index("--lock") + 1 < len(argv):
                token = argv[argv.index("--lock") + 1]
            return run_detached(root, msg, check=check, sleep=sleep, token=token)
        return detach(root, msg)
    if "--waiting" in argv:
        fetch_waiting(root)
        refs, left = _chat_branches(root)
        for ref, (days, files) in left.items():
            print("land: " + left_line(ref, days, files, root, consume=False))
        found = ages(root, refs)
        if not found:
            print("land: nothing waiting")
            return 0
        print("land: work not on master yet, waiting on: %s" % ", ".join(
            "%s (%s)" % (r, "today" if d == 0 else "%d day%s" % (d, "" if d == 1 else "s"))
            for r, d in found.items()))
        print("  the next landing brings each in (python3 tools/land.py, in the background) and "
              "takes it to master, settling a file two chats changed without losing either side")
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
