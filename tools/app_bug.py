#!/usr/bin/env python3
"""An app bug met in the maintainer's own copy, filed on the app by itself, checked first.

    python3 tools/app_bug.py check <body file> --title "<what breaks>" [--key "<tool:function>"]
    python3 tools/app_bug.py check ... --hold           # this chat cannot reach the app's issues
    python3 tools/app_bug.py held                       # a cloud chat files what others held
    python3 tools/app_bug.py filed <key>...             # those now filed leave the folder
    python3 tools/app_bug.py wake                       # only for a bug that stops their search
    python3 tools/app_bug.py woken [--trigger <id>] [--none]   # the builder was poked (or not)
    python3 tools/app_bug.py window <the maintainer's copy>   # may the builder merge now?
    python3 tools/app_bug.py task --copy <owner/name>   # the builder's task, as create_trigger takes it

The maintainer asked (2026-11-11) never to carry the app's bugs between chats by hand again,
and never to hear of them in a chat: a chat in their own copy that meets one files it on the
app's public page as an issue labelled `from-copy`, says nothing, and carries on round it.
Filed issues queue, costing nothing more: the builder's one scheduled task ("App builder:
weekly fixes and release", automation/prompts/builder_week.md) runs every Wednesday at 23:15
UK time, just after the maintainer's weekly usage starts again, takes every open one, fixes
them and releases. Only a bug the person says stops their search pokes that task at once
(`wake`), once an hour at most from a copy.

The app is public, so nothing of the person's may reach it: the issue's words are scanned
first with the push gate's own checks (leak_scan against a denylist built from this copy by
tools/build_app.py --tokens-out, kept 12 hours and while this copy's newest commit stays the
same, then name_guard against the words the app carries), and only words that pass are
printed. Each issue carries a key (a short hash of its tool and function where given, else
of its title, the same however it is spaced or capitalised), so a bug met twice is one issue
with a comment, never two. The tool makes no network call: the chat makes one list call,
then one create or comment. A chat that cannot reach the app's issues (one on the
maintainer's computer) holds the checked issue in handoff/app_bugs/, saved like their other
files, and the next cloud chat's sync says so; it files them. The morning after the builder
runs, the maintainer's own brief says what it did (brief_line), and nothing else tells them.

A copy that is not the maintainer's never files one: its chats give the person the link the
app skill describes (.claude/skills/app/chat.md, "Something looks wrong"), which they choose
to press. This says so, and exits 2.

Exit 0 checked (the steps and the issue printed), 1 refused (what to reword is named, never
a private word), 2 not the maintainer's copy, 3 a usage error or a check that could not run.
`window` exits 0 when a merge may go now and 1 when it should wait.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LABEL = "from-copy"
FIXED = "fixed-unreleased"            # fixed on master; the release closes it
NEEDS = "needs-maintainer"            # the builder left it for the maintainer
BUILDER_TASK = "App builder: weekly fixes and release"
BUILDER_PROMPT = "automation/prompts/builder_week.md"
# Wednesdays at 23:15 UK time: the maintainer's weekly usage starts again at 23:00, and the
# release merges before 07:30 so their 07:56 brief takes it.
BUILDER_CRON = "CRON_TZ=Europe/London 15 23 * * 3"
TOKENS_HOURS = 12                     # the denylist is built again after this, as the push gate's is
WAKE_HOURS = 1                        # urgent bugs in a burst poke the builder once
WINDOW = (15, 20)                     # no merge from 15 minutes before to 20 after their tasks
STATE = "ljs-app-bug.json"
TOKENS = "ljs-app-bug-tokens"
APP_REF = "refs/remotes/app/master"
HELD = os.path.join("handoff", "app_bugs")   # checked issues a chat could not file itself
MARK = re.compile(r"<!-- app-bug: ([0-9a-f]{6,40}) -->")
GITHUB_TOOLS = "select:mcp__github__list_issues,mcp__github__issue_write,mcp__github__add_issue_comment"


# ------------------------------------------------------------------ where its records live

def _git(*args: str) -> subprocess.CompletedProcess:
    import sync_app
    return sync_app.run_git(ROOT, *args)


def _git_dir() -> str:
    """This copy's git folder: what is kept there is never committed, and the denylist is
    personal data."""
    got = _git("rev-parse", "--git-common-dir")
    base = got.stdout.strip() if got.returncode == 0 else ""
    if base and not os.path.isabs(base):
        base = os.path.join(ROOT, base)
    return base or tempfile.gettempdir()


def _load() -> dict:
    try:
        with open(os.path.join(_git_dir(), STATE), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    with open(os.path.join(_git_dir(), STATE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)


def _head() -> str:
    got = _git("rev-parse", "HEAD")
    return got.stdout.strip() if got.returncode == 0 else ""


# ------------------------------------------------------------------ the key

def normal(text: str, tool: bool = False) -> str:
    """`text` as the key reads it: one case, one space between words, no punctuation, and for
    a tool and function the same however it was written (tools/sync_app.py:follow,
    sync_app.follow and "sync_app.py follow()" are one)."""
    s = str(text or "").casefold()
    if tool:
        s = re.sub(r"^\s*(?:python3?\s+)?(?:\./)?", "", s)
        s = re.sub(r"(?<![\w])tools/", "", s).replace(".py", " ").replace(".sh", " ")
    return " ".join(re.sub(r"\W+", " ", s).split())


def key_of(title: str, key: str = "") -> str:
    """The issue's dedupe key: a short hash of the tool and function where given, else of
    the title."""
    seed = ("tool:" + normal(key, tool=True)) if normal(key, tool=True) else ("title:" + normal(title))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ the checks

def denylist(build=None) -> str:
    """The path of a denylist built from this copy (its profile, and the whole history of its
    tracker, contacts and messages, as the push gate's is), kept TOKENS_HOURS and while this
    copy's newest commit is the one it was built from."""
    import file_clock
    path = os.path.join(_git_dir(), TOKENS)
    stamp = path + ".head"
    head = _head()
    try:
        with open(stamp, encoding="utf-8") as fh:
            built_from = fh.read().strip()
        fresh = (os.path.getsize(path) > 0 and built_from == head
                 and file_clock.age(path) < TOKENS_HOURS * 3600)
    except OSError:
        fresh = False
    if fresh:
        return path
    run = build or (lambda out, tokens: subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "build_app.py"), out, "--tokens-out", tokens],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900))
    new = path + ".new"
    try:
        os.remove(new)
    except OSError:
        pass
    with tempfile.TemporaryDirectory(prefix="ljs-app-bug-") as out:
        run(os.path.join(out, "app"), new)
    # build_app exits 1 when the exported tree itself has a finding, after writing the list:
    # the list is what is wanted here, so a list written by this build is used either way.
    if not os.path.exists(new) or os.path.getsize(new) == 0:
        raise RuntimeError("the list of this copy's private words could not be built")
    os.replace(new, path)
    with open(stamp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "\n")
    return path


def _app_ref() -> str:
    """The app's own master as this copy last fetched it, else HEAD: name_guard's words are
    the app's, never the copy's own (its profile carries every name the person wrote down)."""
    return APP_REF if _git("rev-parse", "--verify", "--quiet", APP_REF).returncode == 0 else "HEAD"


def findings(text: str, tokens_file: str, known: set | None = None) -> list[str]:
    """What in `text` the app must never carry: a word of this copy's (by its number in the
    denylist), an address, a phone number, a profile link, a full name the app has never
    carried, each by its line and never the words themselves. [] when it may be filed."""
    import leak_scan
    import name_guard
    with open(tokens_file, encoding="utf-8") as fh:
        tokens = leak_scan.tokens_from(fh.read().splitlines())
    with tempfile.TemporaryDirectory(prefix="ljs-app-bug-") as d:
        p = os.path.join(d, "issue.txt")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        out = list(leak_scan.scan_text([p], tokens))
    known = name_guard.vocabulary(_app_ref()) if known is None else known
    # By its line, never the name: a name the app never carried may be someone real.
    for n, line in enumerate(text.splitlines(), 1):
        if name_guard.names(line, known):
            out.append(f"issue.txt:{n}: a full name the app has never carried")
    return out


# ------------------------------------------------------------------ the issue

def _version() -> str:
    try:
        import release
        got = release.sections()
        return str(got[0]["version"]) if got else ""
    except Exception:  # noqa: BLE001  no CHANGELOG to read
        return ""


def _app_commit() -> str:
    """The newest commit of the app this copy holds, so the builder can tell a bug its fix
    has not reached yet from one the fix did not mend."""
    ref = _app_ref()
    if ref == "HEAD":
        return ""
    got = _git("merge-base", "HEAD", ref)
    return got.stdout.strip()[:12] if got.returncode == 0 else ""


def _where() -> str:
    try:
        import place
        return "a cloud chat" if place.in_cloud() else "a chat on a computer"
    except Exception:  # noqa: BLE001  either is fine to leave out
        return ""


def issue(title: str, body: str, key: str, version: str = "", commit: str = "",
          where: str = "") -> dict:
    """The issue as GitHub's issue tool takes it (method create), with the comment to add
    instead where an open one carries the same key."""
    import app_setup
    owner, name = app_setup.APP_REPO.rstrip("/").split("/")[-2:]
    body = MARK.sub("", str(body or "")).strip()
    said = f"version {version or 'not known'}" + (f", app commit {commit}" if commit else "") \
        + (f", from {where}" if where else "")
    foot = f"Filed by itself from the maintainer's own copy ({said})."
    return {"owner": owner, "repo": name, "title": " ".join(str(title).split()),
            "labels": [LABEL], "key": key,
            "body": f"{body}\n\n---\n{foot}\n<!-- app-bug: {key} -->",
            "comment": f"Seen again ({said}).\n\n{body}"}


# ------------------------------------------------------------------ waking the builder

def _fire(trig: str) -> str:
    if trig:
        return (f"fire_trigger with trigger_id {trig} (not found: list_triggers, fire the one "
                f"named \"{BUILDER_TASK}\", then python3 tools/app_bug.py woken --trigger <its "
                "id>)")
    return (f"list_triggers, fire the one named \"{BUILDER_TASK}\", then python3 "
            "tools/app_bug.py woken --trigger <its id>")


def wake(now: float | None = None) -> str:
    """The step that pokes the builder at once, for a bug the person said stops their search,
    or why there is none. The poke is claimed here, so urgent bugs in a burst poke it once;
    the run lists every open issue again before it stops, so it takes those too."""
    now = time.time() if now is None else now
    state = _load()
    last = float(state.get("woken") or 0)
    if last and now - last < WAKE_HOURS * 3600:
        return ("app_bug: nothing to poke: the builder was poked from this copy within the "
                "hour, and takes this one too before it stops.")
    state["woken"] = now
    _save(state)
    return ("app_bug: poke the builder now: " + _fire(state.get("builder") or "") + ". No such "
            "task, or no scheduled-task tools in this chat: python3 tools/app_bug.py woken "
            "--none, and the bug waits for Wednesday's run.")


def woken(trigger: str = "", now: float | None = None, none: bool = False) -> str:
    """The builder was poked from this copy now; its task id, where given, is kept for the
    next poke. With `none`, nothing could be poked: the claim `wake` made is let go, so the
    next urgent bug pokes it."""
    if trigger and not re.fullmatch(r"trig_[A-Za-z0-9_-]{4,80}", trigger):
        raise ValueError(f"{trigger!r} is not a scheduled task's id (trig_...)")
    state = _load()
    if trigger:
        state["builder"] = trigger
    state["woken"] = 0 if none else (time.time() if now is None else now)
    _save(state)
    return str(state.get("builder") or "")


# ------------------------------------------------------------------ the builder's own needs

def window(copy: str, now: dt.datetime | None = None) -> tuple[int, str]:
    """(minutes to wait, which task) before a merge may go: none from WINDOW[0] minutes before
    to WINDOW[1] after the cron of any task of the maintainer's that is not paused (their brief
    takes master). (0, "") when a merge may go now."""
    import routines
    try:
        with open(os.path.join(copy, "profile", "routines.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError):
        return 0, ""
    now = now or dt.datetime.now(dt.timezone.utc)
    wait, which = 0, ""
    for r in reg.get("routines") or []:
        if not isinstance(r, dict) or r.get("paused") or r.get("enabled") is False:
            continue
        c = routines.read_cron(r.get("cron") or "")
        if not c or not c["days"]:
            continue
        try:
            from zoneinfo import ZoneInfo
            zone = ZoneInfo(c["zone"])
        except Exception:  # noqa: BLE001  a zone this computer does not know: read as UTC
            zone = dt.timezone.utc
        here = now.astimezone(zone)
        h, m = (int(x) for x in c["time"].split(":"))
        for back in (-1, 0, 1):
            day = here.date() + dt.timedelta(days=back)
            if (day.weekday() + 1) % 7 not in c["days"]:
                continue
            at = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=zone)
            start, end = at - dt.timedelta(minutes=WINDOW[0]), at + dt.timedelta(minutes=WINDOW[1])
            if start <= here < end:
                left = math.ceil((end - here).total_seconds() / 60)
                if left > wait:
                    wait, which = left, f"{r.get('name') or r.get('key') or 'a task'} at {c['time']}"
    return wait, which


def task(copy: str) -> dict:
    """The builder's scheduled task, as create_trigger takes it: weekly, a fresh chat each run,
    poked at once only for a bug that stops the search. Its prompt is a stub that
    reads the builder's instructions from the app's master, so a change to what it does is a
    pull request, never an edit to the task; `copy` (the maintainer's own, owner/name) is in
    the task alone, never in the app."""
    import app_setup
    copy = str(copy or "").strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", copy) or copy.lower() == app_setup.APP_REPO:
        raise ValueError("--copy is the maintainer's own copy as owner/name, never the app")
    app = app_setup.APP_REPO
    prompt = (f"Scheduled run: weekly app builder. You work on the public app github.com/{app}, with "
              f"the maintainer's own copy github.com/{copy} beside it, read-only. Where either "
              f"is not checked out here, attach it (add_repo: the app with access push, the copy "
              f"with access read) and clone it as that tool says. Then, in the app, run `git "
              f"fetch origin master`, read {BUILDER_PROMPT} as it is on origin/master (`git show "
              f"origin/master:{BUILDER_PROMPT}`) and follow it exactly. If anything here cannot "
              "be had, reply with one line saying which and why, and stop.")
    return {"name": BUILDER_TASK, "cron_expression": BUILDER_CRON,
            "create_new_session_on_fire": True, "initiation": "human_request",
            "notifications": {}, "prompt": prompt}


# ------------------------------------------------------------------ what the builder did, in the brief

REPORT_LABEL = "builder-report"       # the one issue whose body the builder rewrites each run
ISSUES_API = "https://api.github.com/repos/{repo}/issues?state=open&labels={label}&per_page=30"


def _get(url: str):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "last-job-search-brief/1",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:      # a public page: no token
        return json.loads(r.read().decode("utf-8"))


def brief_line(today: dt.date, get=None) -> str:
    """For the maintainer's own brief, once, the morning after the weekly builder ran: what it
    did in one line (the dated first line of its report issue, which it rewrites each run),
    with each issue that needs their decision by its link. "" in anyone else's copy, on any
    other day, once said, or where GitHub cannot be read. Two reads of public pages; no issue's
    own words are ever carried, only its number and address."""
    import sync_app
    if not sync_app.maintainers():
        return ""
    import app_setup
    get = get or _get
    try:
        reports = get(ISSUES_API.format(repo=app_setup.APP_REPO, label=REPORT_LABEL))
        first = (str((reports[0] if reports else {}).get("body") or "").strip().splitlines()
                 or [""])[0].strip()
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}): (.{3,200})", first)
        if not m or not 0 <= (today - dt.date.fromisoformat(m.group(1))).days <= 1:
            return ""
        state = _load()
        if state.get("brief_said") == first:
            return ""
        needs = get(ISSUES_API.format(repo=app_setup.APP_REPO, label=NEEDS))
    except Exception:  # noqa: BLE001  GitHub not reached: the next brief says it
        return ""
    links = [f"#{i['number']} {i['html_url']}" for i in needs or []
             if isinstance(i, dict) and i.get("number") and i.get("html_url")
             and "pull_request" not in i][:8]
    state["brief_said"] = first
    _save(state)
    return ("The app's weekly builder: " + m.group(2).rstrip(".") + "."
            + (" Needs your decision: " + ", ".join(links) + "." if links else ""))


# ------------------------------------------------------------------ held for a chat that can file

def _held_dir() -> str:
    """Where a chat that cannot reach the app's issues (a chat on a computer, or a cloud chat
    refused) leaves a checked issue: a folder of the person's (personal_paths `handoff/**`),
    saved and landed like their other files, so the next cloud chat in the copy files it."""
    return os.path.join(ROOT, HELD)


def hold(got: dict) -> str:
    """Keep a checked issue for the next chat that can file it."""
    os.makedirs(_held_dir(), exist_ok=True)
    path = os.path.join(_held_dir(), f"{got['key']}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({k: got[k] for k in ("title", "body", "key")}, fh, indent=1)
    return path


def held() -> list[dict]:
    """The checked issues waiting for a chat that can file them, oldest first."""
    out = []
    try:
        names = sorted(os.listdir(_held_dir()), key=lambda n: os.path.getmtime(
            os.path.join(_held_dir(), n)))
    except OSError:
        return []
    for n in names:
        try:
            with open(os.path.join(_held_dir(), n), encoding="utf-8") as fh:
                got = json.load(fh)
            if isinstance(got, dict) and MARK.search(str(got.get("body") or "")):
                out.append(got)
        except (OSError, ValueError):
            continue
    return out


def filed(keys: list[str]) -> list[str]:
    """The held issues these keys name, filed: taken out of the folder."""
    gone = []
    for k in keys:
        path = os.path.join(_held_dir(), f"{k}.json")
        if re.fullmatch(r"[0-9a-f]{6,40}", k) and os.path.isfile(path):
            os.remove(path)
            gone.append(k)
    return gone


def held_line() -> str:
    """One line for the start of a cloud chat in the maintainer's own copy when checked issues
    wait there to be filed, else "". Nothing for anyone else, and nothing on a computer, which
    held them for want of the app's issues."""
    try:
        if not any(n.endswith(".json") for n in os.listdir(_held_dir())):
            return ""
        import place
        import sync_app
        if not place.in_cloud() or not sync_app.maintainers():
            return ""
    except Exception:  # noqa: BLE001  no folder, no git: nothing waits
        return ""
    return ("app_bug: app bugs another chat checked wait to be filed for the app: python3 "
            "tools/app_bug.py held, and do the steps it prints, said to nobody.")


# ------------------------------------------------------------------ the command

def vet(title: str, body: str, key: str = "", build=None, known: set | None = None) -> dict | None:
    """The issue, checked; None (with what to reword printed) when it may not be filed."""
    k = key_of(title, key)
    got = issue(title, body, k, _version(), _app_commit(), _where())
    # Everything that would be posted but the key, a hash of words checked here; the comment
    # is the body again under a line the footer already holds.
    found = findings(got["title"] + "\n\n" + MARK.sub("", got["body"]), denylist(build), known)
    if found:
        print("app_bug: nothing filed. The issue would carry something of this copy's; reword "
              "these lines without any name, employer, place, address or message of theirs, "
              "then check it again:")
        for f in found:
            print(f"  {f}")
        return None
    return got


def steps(issues: list[dict], keys_done: bool = False) -> str:
    """What the chat does to file `issues`: one list call, then a comment or a new issue each."""
    import app_setup
    o, r = app_setup.APP_REPO.split("/")
    lines = [
        "File it now and say nothing about it: the maintainer asked never to hear of app bugs "
        "in a chat. Then carry on round the bug.",
        f"0. This chat's GitHub tools cannot reach the app yet: in a cloud chat, attach it first "
        f"(add_repo, owner {o}, repo {r}, access push); deferred, load them in one call "
        f"(ToolSearch \"{GITHUB_TOOLS}\"). No GitHub tools at all (a chat on a computer), or "
        + ("still refused: leave them held and stop here." if keys_done else
           "still refused: python3 tools/app_bug.py check <the same file> --title <the same> "
           "--key <the same> --hold, and stop here: the next cloud chat files it."),
        f"1. One call: GitHub's list_issues (owner {o}, repo {r}, state OPEN, labels "
        f"[\"{LABEL}\"]).",
        f"2. Each issue below: an open one whose body holds its <!-- app-bug: <key> --> line is "
        f"the same bug, so add its comment to that one (add_issue_comment), and where that one "
        f"is labelled {FIXED} also set its labels to [\"{LABEL}\"] (issue_write, method "
        "update), since it came back. Otherwise create it (issue_write, method create) with its "
        "title, labels and body. Exactly as printed: nothing added after this check.",
        "3. Nothing to wake: it waits, with the week's other bugs, for the builder's run on "
        "Wednesday night. Only where the person has said this bug stops their search: python3 "
        "tools/app_bug.py wake, and do what it prints.",
    ]
    if keys_done:
        lines.append("4. Once each is filed: python3 tools/app_bug.py filed "
                     + " ".join(i["key"] for i in issues) + ", then save as usual.")
    for i in issues:
        lines += ["", f"title: {i['title']}", f"labels: [\"{LABEL}\"]", "body:", i["body"], "",
                  "comment:", i["comment"]]
    return "\n".join(lines)


def check(body_file: str, title: str, key: str = "", build=None, known: set | None = None,
          keep: bool = False) -> int:
    try:
        with open(body_file, encoding="utf-8") as fh:
            body = fh.read()
    except OSError as e:
        print(f"app_bug: cannot read {body_file}: {e}")
        return 3
    if not str(title).strip() or not MARK.sub("", body).strip():
        print("app_bug: say what breaks in the title, and in the body what happened, the "
              "input that shows it, the tool and function, and the evidence.")
        return 3
    try:
        got = vet(title, body, key, build, known)
    except Exception as e:  # noqa: BLE001  a check that could not run files nothing
        print(f"app_bug: nothing filed: {e}")
        return 3
    if got is None:
        return 1
    if keep:
        hold(got)
        print("app_bug: checked and held for the next cloud chat in this copy, which files it. "
              "Say nothing about it, save as usual, and carry on round the bug.")
        return 0
    print(f"app_bug: checked (key {got['key']}). " + steps([got]))
    return 0


def file_held(build=None, known: set | None = None) -> int:
    """The issues another chat checked and held, checked again here (this copy's list of
    private words may have grown since) and printed with the steps that file them."""
    ready = []
    for h in held():
        body = h["body"].split("\n\n---\nFiled by itself", 1)[0]
        try:
            got = vet(h["title"], body, "", build, known)
        except Exception as e:  # noqa: BLE001  a check that could not run files nothing
            print(f"app_bug: nothing filed: {e}")
            return 3
        if got is None:
            print(f"app_bug: held issue {h['key']} stays held: reword it in "
                  f"{os.path.join(HELD, h['key'] + '.json')}, or take it out.")
            continue
        got["key"] = h["key"]
        got["body"] = MARK.sub(f"<!-- app-bug: {h['key']} -->", got["body"])
        ready.append(got)
    if not ready:
        print("app_bug: nothing held to file.")
        return 0
    print(f"app_bug: {len(ready)} held, checked again. " + steps(ready, keys_done=True))
    return 0


def main(argv=None, build=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="scan an app bug's words and print the steps that file it")
    c.add_argument("body", help="a file holding what happened, the input that shows it, the "
                                "tool and function, and the evidence")
    c.add_argument("--title", required=True, help="what breaks, in a few words")
    c.add_argument("--key", default="", help="the failing tool and function (tools/x.py:f), "
                                             "which keys the issue where known")
    c.add_argument("--hold", action="store_true", help="this chat cannot reach the app's issues: "
                                                       "keep it for the next cloud chat")
    sub.add_parser("held", help="the issues other chats held, checked again, with the steps")
    f = sub.add_parser("filed", help="held issues now filed: take them out")
    f.add_argument("keys", nargs="+")
    sub.add_parser("wake", help="poke the builder at once: only for a bug that stops the search")
    w = sub.add_parser("woken", help="the builder was poked now; keep its task id if given")
    w.add_argument("--trigger", default="")
    w.add_argument("--none", action="store_true", help="nothing could be poked: the next urgent bug pokes it")
    m = sub.add_parser("window", help="may the builder merge now, clear of the maintainer's tasks")
    m.add_argument("copy", help="the maintainer's own copy, checked out")
    t = sub.add_parser("task", help="the builder's scheduled task, as create_trigger takes it")
    t.add_argument("--copy", required=True, help="the maintainer's own copy, as owner/name")
    a = ap.parse_args(argv)
    if a.cmd == "window":
        wait, which = window(a.copy)
        print(f"app_bug: wait {wait} minutes: the maintainer's {which} takes master; merge then."
              if wait else "app_bug: clear of the maintainer's tasks: merge now.")
        return 1 if wait else 0
    if a.cmd == "task":
        try:
            print(json.dumps(task(a.copy), indent=1))
        except ValueError as e:
            print(f"app_bug: {e}")
            return 3
        return 0
    import sync_app
    if not sync_app.maintainers():
        print("app_bug: this copy is not the app maintainer's, so it files nothing itself. Give "
              "the person the link the app skill describes (.claude/skills/app/chat.md, "
              "\"Something looks wrong\"), once, which they choose to press.")
        return 2
    if a.cmd == "wake":
        print(wake())
        return 0
    if a.cmd == "woken":
        try:
            kept = woken(a.trigger, none=a.none)
            print("app_bug: nothing poked; the next urgent bug pokes the builder." if a.none
                  else "app_bug: noted that the builder was poked" + (f" ({kept})" if kept else "")
                  + ".")
        except ValueError as e:
            print(f"app_bug: {e}")
            return 3
        return 0
    if a.cmd == "held":
        return file_held(build=build)
    if a.cmd == "filed":
        gone = filed(a.keys)
        print(f"app_bug: {len(gone)} held issue(s) taken out as filed; save as usual.")
        return 0
    return check(a.body, a.title, a.key, build=build, keep=a.hold)


if __name__ == "__main__":
    sys.exit(main())
