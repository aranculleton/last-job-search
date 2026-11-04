#!/usr/bin/env python3
"""Which chat answers the person's page: one listener, with when it last answered.

A tap on the page writes the request into the page's database and rings: every chat that
watches the page is woken, each at the cost of its whole conversation. A chat that
publishes a page watches it by itself (code.claude.com/docs/en/artifacts, "Let Claude reply
to comments on its own"), so when every chat that ran `app.py start` published, one tap woke
the setup chat, each long chat from before 4.0 and every split screen at full size. Now one
chat answers the page, the listener, and every other chat neither publishes nor watches it.

The record is the page's own database, `meta/listener` (stored as `meta/listen`, page_db.STORE_DOC): {chat, title, kind, since,
answered_at, took_from}. It is shared at once by every chat and every device, so two chats
that start together cannot both become the listener: each claims it with a write that only
one can win (a create, refused when the document exists, or a write pinned to the version
read). Nothing about it is committed, so two chats never fight over it in a merge. Each
checkout keeps what it last saw in its own git folder (`ljs-listener.json`), never
committed, so a chat that knows another one answers starts with no read at all.

    python3 tools/app.py listen <dump> --chat ID [--listen] [--helper] [--hand ID]
    python3 tools/app.py republish <out dir>       the page's own code changed: queue it

`app.py start` prints the steps (`shape`): the listener keeps its watch on and checks in;
a chat that may become it asks the database; every other chat does neither and says
nothing about it. No chat is ever started for the page: a helper started for it had none
of the page's tools, published a spare page, and each lapse started another (2026-10-29).
When nobody answers, the page shows
"Claude isn't listening" with one link that opens a chat which becomes the listener
(`model_part`, `wake_url`).

A watch that Claude Code started by itself "can end after the artifact goes several hours
without activity"; publishing again or asking Claude to watch starts it again (the same
page). So the listener asks for its watch at every start. In a cloud chat a watch is a wake
subscription the artifact service holds (the ArtifactComments tool's own description).

Pure code, standard library only, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

DOC_COLLECTION, DOC_ID = "meta", "listener"
CACHE = "ljs-listener.json"            # in the git folder: what this checkout last saw
# Work or a tap waiting this long after the listener last answered: nobody is answering.
LAPSE_S = 10 * 60
HELPER_TITLE = "Job search helper"
# The helper's own name in their list of chats, and what it says when it starts: the one
# thing a person needs to know about it (the maintainer, 2026-10-29: "some quick way of
# explaining what it's for ... even if the user deletes it it's fine it'll start up again").
OLD_HELPER_TITLE = HELPER_TITLE + " (finishing up)"     # the helper a new one took the page from
HELPER_CHAT_TITLE = HELPER_TITLE      # short: what it is for is said, never in its name
# Said once in a chat that does not answer the page, the first time it starts (the
# maintainer, 2026-10-29: a heads-up about a new chat, "DO NOT MAKE THIS PERSIST").
SAY_OTHER_CHAT = ("Heads up: your page is looked after by {who}, so this chat leaves it alone. "
                  "Anything you do here is saved to the same place and shows on your page.")
# A new helper says the page's link at once, shows the page busy while it works, and ends
# with one short line. It once said a paragraph about what a helper is and posted the whole
# morning brief, the link nowhere near the start (the maintainer, 2026-11-04: the link
# first, then the work while the page shows it, then one line that it is ready).
SAY_HELPER = "Your job search helper is starting: {url}"
SAY_HELPER_READY = "Your job search helper is ready: {url}"
HELPER_BUSY = "Getting your page ready"
# What the page's "Wake Claude" link types for the person; they only press Send. Plain words
# (it is their message, in their list of chats: a command there broke the rule that a person
# is never shown one, the stranger audit, X-84); the app's hook knows the words and tells the
# chat to run WAKE_COMMAND, which makes it the listener: a new chat with nothing else to do,
# so it is the helper itself and starts no other.
WAKE_PROMPT = "Look after my job search page from now on."
WAKE_COMMAND = "python3 tools/app.py start --listen --helper"
REPUBLISH_TITLE = "Bringing your page up to date"
# All the person hears about their page after an update: one line. A chat that took an
# update (2026-10-26) asked whether to bring the page up, explained that a safety check had
# blocked its first try, offered the pin again and reported a timer running out; the person
# had asked for none of it.
# Each ends on the page's link (CLAUDE.md: "Your page is up to date: <its link>"): a chat
# said "Your page is being updated." with none, and the person asked for it twice
# (2026-10-30). `say()` fills it in.
SAY_UPDATED = "Your page is up to date: {url}"
SAY_UPDATING = "Your page is being updated: {url}"
SAY_NOT_UPDATED = "I couldn't update your page just now: {url}"
# Said once, when a page first goes up after setup (or a page published before without a
# word): what it is, in one line under 200 characters with its link (X-25).
SAY_FIRST_PAGE = ("Your job search has its own page now: {url}. What I find and draft, and "
                  "anything I need from you, shows there.")
SAY_NEW_ADDRESS = "Your page has a new address: {url}"
# A chat with the page's new code to put up takes the page from a listener quiet this long:
# a watch Claude Code started by itself can end after hours with nothing happening, and an
# update queued for a listener last heard from 12 hours before waited until the person asked
# in the chat whether it was happening (2026-10-30).
UPDATE_QUIET_S = 60 * 60
# A chat re-reads its whole history at every wake, so one answering the page for days grew
# dearer with every tap. Once it has answered for this long, at a quiet moment (nothing queued
# or running), it starts a fresh helper, which takes the page on its own start (the
# maintainer, 2026-10-30). Until the new one has taken it, the old one still answers: a fresh
# chat that never starts changes nothing.
RENEW_S = 20 * 3600
# A helper whose history has grown by more than this since its first turn answers slowly:
# one answering the page since three days before re-read some 535,000 tokens a step, and a
# one-line LinkedIn reply took minutes that a fresh chat does at once (the maintainer,
# 2026-11-03: "the entire app is so unnecessarily slow"). Past it, the helper hands over at
# its next quiet moment. Growth, not size: a fresh chat already starts near 100,000, and a
# size of 150,000 would have started a new helper about every hour (the release review).
RENEW_TOKENS = 200_000
# A fresh helper asked for and never come: asked for again after this long, while this chat
# still answers the page. It was a whole day, from the moment the call was printed, made or
# not (engine audit, 2026-11-03).
RENEW_RETRY_S = 2 * 3600
# How every page step after an update is done: at once, unasked, one command at a time (a
# chained command goes to the desktop app's safety check whole), with nothing left behind.
NO_ASK = ("Do it now, before anything else, and never ask the person first: bringing their "
          "page up to date after an update is always yes. Run each command on its own, never "
          "chained, and set no timer or reminder for any of it.")
# What start prints, as app_setup words it, so its publish steps can be told apart.
_NUM = re.compile(r"^(\d+)\. ")
_PUBLISH = ("The person's page is ", "Build the person's page", "Read the page first",
            "Publish it (Artifact")
_WATCH = "Publishing makes this chat watch the page"
_BEFORE = ("Setup carries on", "The page shows the updates", "Bring the page's data up to date",
           "Unless the update check above just did it")


# ------------------------------------------------------------------ who this chat is


def say(line: str, url: str) -> str:
    """One of the SAY_ lines with the page's link in it."""
    return line.format(url=url or "<the page's link>")


def this_chat(given: str = "") -> str:
    """This chat's id: the one given, else what Claude Code sets. A cloud chat's id
    (CLAUDE_CODE_REMOTE_SESSION_ID, in `cse_` form) is written in the `session_` form its
    link and create_session use (code.claude.com/docs/en/cloud-environments, "Link output
    back to the session"); a chat on a computer has CLAUDE_CODE_SESSION_ID
    (code.claude.com/docs/en/env-vars). "" when none is known. LJS_CHAT is for tests."""
    if given:
        return given
    env = os.environ
    for key in ("LJS_CHAT", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID"):
        v = str(env.get(key) or "").strip()
        if v:
            return re.sub(r"^cse_", "session_", v)
    v = str(env.get("CLAUDE_CODE_SESSION_ID") or "").strip()
    return f"local-{v}" if v else ""


def chat_kind() -> str:
    """"cloud" in a cloud chat (CLAUDE_CODE_REMOTE, documented), else "computer"."""
    return "cloud" if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true" else "computer"


# ------------------------------------------------------------------ what this checkout saw


def _cache_path() -> str:
    import person
    root = person.state()
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        d = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        d = ""
    return os.path.join(d, CACHE) if d else os.path.join(root, "." + CACHE)


def seen() -> dict:
    """What this checkout last saw: {"listener": {chat, title, kind, since, seen_at},
    "told": {chat: day}}. Empty when nothing was seen."""
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _replace(tmp: str, path: str) -> None:
    """os.replace, waiting out another chat's replace of the same file: Windows refuses a
    replace while the other is mid-way (PermissionError), where POSIX lets both through."""
    import time
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or i == 39:
                raise
            time.sleep(0.05)


def _save_seen(data: dict) -> None:
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"     # two chats in one folder each write whole files
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    _replace(tmp, path)


def _remember(listener: dict | None, now: dt.datetime, confirmed: bool = True) -> None:
    """Keep what this checkout saw. `confirmed` is False for a claim this chat has only
    sent: until a read of the page shows who won, it decides nothing for another chat."""
    got = seen()
    if listener and listener.get("chat"):
        got["listener"] = {k: listener.get(k) for k in ("chat", "title", "kind", "since",
                                                         "helper")}
        got["listener"].update(seen_at=_stamp(now), confirmed=confirmed)
    else:
        got.pop("listener", None)
    _save_seen(got)


def role(chat: str, listen: bool = False, url: str = "") -> str:
    """What start tells this chat: "first" (no page yet: it publishes and listens),
    "listener" (it answered last time this checkout looked), "claim" (ask the page: it
    listens only where nobody does, or when asked to), or "other"."""
    if not url:
        return "first"
    if listen:
        return "claim"
    got = seen().get("listener") or {}
    known = got.get("chat") or ""
    if chat and known == chat:
        return "listener"            # its check-in reads the page and corrects a lost claim
    if not known or not got.get("confirmed"):
        return "claim"               # nobody, or another chat's claim nobody has seen win
    # What this checkout saw is looked at again (the stranger audit, X-24): a session on a
    # computer seen over an hour ago has likely ended (its id is new every session), and a
    # cloud chat seen answering over a day ago may be archived or renewed since. Asking the
    # page is one read, and its check-in takes the page only from a chat that stopped.
    seen_at = _time(got.get("seen_at"))
    computer = got.get("kind") == "computer" or str(known).startswith("local-")
    if seen_at is None or (dt.datetime.now(dt.timezone.utc) - seen_at).total_seconds() > (
            UPDATE_QUIET_S if computer else RENEW_S):
        return "claim"
    return "other"


# ------------------------------------------------------------------ the database's answer


def _time(value):
    import app_model
    return app_model.parse_time(value)


def _stamp(t: dt.datetime) -> str:
    import app_model
    return app_model.stamp(t)


def record(db: dict) -> tuple[dict, int | None]:
    """(meta/listener's fields, its version) from a dump; ({}, None) when there is none."""
    doc = (db.get(DOC_COLLECTION) or {}).get(DOC_ID)
    return (dict(doc["data"]), doc["version"]) if doc else ({}, None)


def waiting_since(db: dict, now: dt.datetime | None = None) -> dt.datetime | None:
    """When the oldest thing still waiting for a chat was asked: a queued work item, or a
    tap with no receipt and no claim. None when nothing waits (or nothing was dumped)."""
    times = []
    for doc in (db.get("work") or {}).values():
        d = doc["data"]
        if str(d.get("status") or "") == "queued" and not d.get("stop_asked"):
            times.append(_time(d.get("asked_at")))
    receipts = db.get("receipts") or {}
    now = dt.datetime.now(dt.timezone.utc) if now is None else now
    for aid, doc in (db.get("actions") or {}).items():
        d = doc["data"]
        until = _time(d.get("claimed_until"))
        # A claim that ran out is no claim: the chat that made it stopped, and the tap still
        # waits (it never counted, so a listener that had gone was never judged gone).
        if aid not in receipts and not (d.get("claimed_by") and until is not None and until > now):
            times.append(_time(d.get("at")))
    times = [t for t in times if t is not None]
    return min(times) if times else None


def lapsed(rec: dict, db: dict, now: dt.datetime) -> bool:
    """Has the listener stopped answering? Something has waited LAPSE_S since it was asked
    and the listener has not answered since. A quiet listener with nothing waiting has not
    lapsed: a watch outlives a quiet week."""
    if not rec.get("chat"):
        return True
    since = waiting_since(db, now)
    if since is None or (now - since).total_seconds() < LAPSE_S:
        return False
    answered = _time(rec.get("answered_at")) or _time(rec.get("since"))
    return answered is None or answered < since


def quiet_s(rec: dict, db: dict, now: dt.datetime) -> float | None:
    """Seconds since the listener last showed it was there: its last answer, its claim, or
    its own heartbeat (beats). None when it never has."""
    times = [_time(rec.get("answered_at")), _time(rec.get("since"))]
    beat = (db.get("chats") or {}).get(rec.get("chat") or "")
    if beat:
        times.append(_time(beat["data"].get("seen_at")))
    times = [t for t in times if t is not None]
    return (now - max(times)).total_seconds() if times else None


def _ago(value, now: dt.datetime) -> str:
    t = _time(value)
    if t is None:
        return "never"
    s = max(0, int((now - t).total_seconds()))
    for size, word in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if s >= size:
            n = s // size
            return f"{n} {word}{'s' if n != 1 else ''} ago"
    return "just now"


def decide(db: dict, chat: str, out_dir: str, now: dt.datetime | None = None,
           listen: bool = False, helper: bool = False, title: str = "",
           hand_to: str = "", update: bool = False) -> dict:
    """Is this chat the page's listener? {"role": "listener" | "other", "lines": [...],
    "batches": [...], "record": the listener as this chat leaves it}.

    The chat named in meta/listener answers; this chat writes that it answered just now.
    With no record, or one whose chat stopped answering, or when the person asked this chat
    to look after the page (`listen`), it claims the record with a write only one chat can
    win. `hand_to` gives the page to another chat (the helper this one just started).
    `update`: this chat has the page's new code to put up, so a listener quiet for
    UPDATE_QUIET_S counts as gone, and this chat takes the page and publishes it itself."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    rec, version = record(db)
    w = page_db.Writes(out_dir)
    at = _stamp(now)
    lines: list[str] = []
    if not chat:
        return {"role": "other", "batches": [], "record": rec,
                "lines": ["listen: this chat's id is not known, so it cannot answer the page: "
                          "run this again with --chat <this chat's id> (in a cloud chat, "
                          "echo ${CLAUDE_CODE_REMOTE_SESSION_ID/#cse_/session_})"]}
    mine = rec.get("chat") == chat
    if hand_to:
        if not mine:
            return {"role": "other", "batches": [], "record": rec,
                    "lines": ["listen: this chat does not answer the page, so it has nothing "
                              "to hand over"]}
        new = {"chat": hand_to, "title": HELPER_TITLE, "kind": "cloud", "helper": True,
               "since": at, "answered_at": None, "took_from": chat}
        w.add("set", DOC_COLLECTION, DOC_ID, new, if_version=version)
        _remember(new, now, confirmed=False)
        return {"role": "other", "record": new, "batches": w.save("listen"),
                "lines": ["listen: the page is handed to the helper chat. Send the batch "
                          "below, then stop this chat's watch: ArtifactComments, action "
                          "watch, url <the page>, on: false."]}
    gone = lapsed(rec, db, now)
    # With the page's new code, a quiet listener is taken from, so an update never waits on a
    # chat that stopped (2026-10-30); but never a helper the app started that is only idle: it
    # answers when asked, and the chat the person opened for a question, which took it, is
    # one they close (the stranger audit, X-64). It is asked to republish instead, and taken
    # from once something waits on it unanswered (`lapsed`).
    if update and not gone and rec.get("chat") != chat and not (
            rec.get("helper") and rec.get("kind") == "cloud" and not helper):
        q = quiet_s(rec, db, now)
        gone = q is None or q >= UPDATE_QUIET_S
    # The chat setting the person up answers the page while setup goes on: a second chat that
    # took it then carried setup on beside it (the stranger audit, X-65).
    if not mine and rec.get("chat") and _setting_up(rec.get("chat")):
        _remember(rec, now)
        return {"role": "other", "batches": [], "record": rec,
                "lines": ["listen: the chat setting the person up answers the page until setup "
                          "is done; this chat neither publishes nor watches it, and says nothing "
                          "about it."]}
    # The cloud answers the page; a chat on the person's computer is for what only it can do
    # (the maintainer, 2026-10-29: "99% on the cloud, the computer for signed-in things").
    # So a computer chat never takes the page from a cloud chat that still answers it, even
    # when asked to look after it; only from one that has stopped, so the page is never left
    # with nobody.
    held = (not mine and chat_kind() == "computer" and rec.get("kind") == "cloud"
            and rec.get("chat") and not gone)
    take = not mine and not held and (listen or gone)
    if held:
        _remember(rec, now)
        return {"role": "other", "batches": [], "record": rec,
                "lines": ["listen: the cloud chat answers this page and keeps it; this chat on "
                          "the computer does only what needs the computer. Say nothing about "
                          "it to the person.",
                          "listen: if this chat watches the page from before (ArtifactComments, "
                          "action watch with no url, lists this chat's watches), stop that "
                          "watch: action watch, url <the page>, on: false."]}
    if mine:
        renew = renewal(rec, db, chat, now)
        if renew:
            lines.append(renew_line(renew))
        fresh = {"answered_at": at, "watching": True, **({"helper": True} if helper else {})}
        if version is None:
            # Read only under its 4.2 name (page_db.load): the new record is made, whole.
            w.add("set", DOC_COLLECTION, DOC_ID, dict(rec, **fresh))
        else:
            w.add("update", DOC_COLLECTION, DOC_ID, fresh, if_version=version)
        rec = dict(rec, **fresh)
        lines.append("listen: this chat answers the page. Send the batch below (it says this "
                     "chat answered just now). " + CHECK_IN_REFUSED)
        lines.append(WATCH_LINE)
    elif take:
        new = {"chat": chat, "title": title or (HELPER_CHAT_TITLE if helper else "Job search"),
               "kind": chat_kind(), "helper": bool(helper), "since": at, "answered_at": at,
               "watching": True, "took_from": rec.get("chat") or None,
               # Whether the chat it took from was one the app started: the tidy-up only ever
               # puts away such a chat, never one the person writes in (X-4).
               "took_from_helper": bool(rec.get("helper"))}
        w.add("set", DOC_COLLECTION, DOC_ID, new, if_version=version)
        lines.append("listen: this chat answers the page now. Send the batch below. "
                     + CHECK_IN_REFUSED)
        # A chat watches only a page it published or one it asks to watch: one that took the
        # page and never asked heard nothing, and the page went deaf after every renewal and
        # every Wake Claude (the stranger audit, X-6).
        lines.append(WATCH_LINE)
        if waiting_since(db, now) is not None:
            lines.append("listen: work waited while nobody answered: once the batch is sent, "
                         "do what a ring does (the app skill, step 1: read the page and run "
                         "python3 tools/app.py wake) so it starts now.")
        if rec.get("chat"):
            # Never archived from here: the chat it took from may still be writing the brief
            # or saving the morning's work. The tidy-up puts old helpers away, and keeps a
            # chat that is running or holds work not landed (X-27).
            lines.append("listen: the chat that answered before stops by itself: its next "
                         "check finds this one.")
        if helper and chat.startswith("session_"):
            # Named, never explained: the start said the one line the person hears.
            lines.append(f"listen: name this chat in their list: set_session_title "
                         f"(session_id {chat}, title \"{HELPER_CHAT_TITLE}\"), and say "
                         "nothing about it.")
        old = str(rec.get("chat") or "")
        if rec.get("helper") and old.startswith("session_") and old != chat:
            # Two chats called "Job search helper" side by side told nobody which was which:
            # the app's own old helper is renamed at once (never a chat the person writes in),
            # and the tidy-up is due again to archive it once its work is saved.
            lines.append(f"listen: name the chat that answered before, so the two can be told "
                         f"apart: set_session_title (session_id {old}, title "
                         f"\"{OLD_HELPER_TITLE}\"), and say nothing about it.")
        _remember(new, now, confirmed=False)
        return {"role": "listener", "lines": lines, "batches": w.save("listen"), "record": new}
    else:
        _remember(rec, now)
        return {"role": "other", "batches": [], "record": rec,
                "lines": [f"listen: another chat answers the page (it last answered "
                          f"{_ago(rec.get('answered_at') or rec.get('since'), now)}). This "
                          "chat neither publishes the page nor watches it, and says nothing "
                          "about that to the person.",
                          "listen: if this chat watches the page from before (ArtifactComments, "
                          "action watch with no url, lists this chat's watches), stop that "
                          "watch: action watch, url <the page>, on: false."]}
    _remember(rec, now)
    return {"role": "listener", "lines": lines, "batches": w.save("listen"), "record": rec}


# A refused check-in names the version the store holds. Most often another chat took the page;
# but a record whose own stamp was written wrong once was read back wrong by every chat, and
# "read again and run this once more" bounced on it for good (the maintainer, 4 November).
# The version the refusal names is kept (page_db.note_version), so the next read, here or in
# any new folder, is pinned to the store's own number, and the write that lands stamps the
# record right again.
CHECK_IN_REFUSED = ("If it is refused, keep the version the refusal names first: python3 "
                    "tools/app.py version <this folder> meta/listen <that version> (a number "
                    "stored wrong in the record is put right that way, never bounced on); then "
                    "read meta/listen again and run this once more: another chat that took the "
                    "page shows there.")


# What a chat that answers the page asks for at every check-in: its watch, so a tap wakes it.
WATCH_LINE = ("listen: keep this chat's watch on the page so a tap wakes it: ArtifactComments, "
              "action watch, url <the page> (asking again when it already watches does no harm).")


def _setting_up(chat: str) -> bool:
    """Is `chat` the one setting the person up, its setup still going?"""
    try:
        import app_setup
        mark = (app_setup.read_json(os.path.join(app_setup.profile_dir(), "place.json"), {})
                .get("setup") or {})
        return bool(mark.get("started") and not mark.get("finished")
                    and mark.get("chat") == chat)
    except Exception:  # noqa: BLE001  no profile: nobody is setting them up here
        return False


def renew_line(renew: dict) -> str:
    """What the listener does when its day is up: start its fresh helper, unasked, once this
    chat's own work is saved (a fresh helper started mid-brief took the page while the brief
    was still saving, the stranger audit, X-27)."""
    return ("listen: renew: this chat has answered the page for a day (or its history has "
            "grown long), and has no small job of its own in hand. Once this turn's work has "
            "landed (python3 tools/land.py says ready, or there was nothing to save), start "
            "its fresh helper, unasked and saying nothing to the person: create_session "
            + json.dumps(renew, ensure_ascii=False) +
            ". The new chat takes the page as it starts, and the work waiting with it; until "
            "then this one still answers, and its next check-in finds the new one and stops "
            "its watch.")


# What a chat that may not draw the page's screens says, once, and does instead.
VIEW_LEFT = ("view: another chat answers the page, so this chat leaves the page's screens to it "
             "and wrote nothing to them; its own work items and receipts are all it writes. "
             "Work this chat does for the person is its own once begun with python3 "
             "tools/app.py ask \"$D\" --kind <kind> --title \"<a few plain words>\" --here "
             "--chat <this chat's id> (the app skill, \"Work asked for in a chat\"), and then "
             "this draws the page. Say nothing about it to the person.")
# How long after its own job finished a job's chat still draws the page: it does so once, at
# its end, right after app.py done.
OWN_JOB_S = 60 * 60


def draws_screens(db: dict, chat: str, work: str = "",
                  now: dt.datetime | None = None) -> tuple[bool, str]:
    """Whether this chat writes the page's screens (`app.py view`), and what it says when not.

    Only the chat that answers the page draws them, with two exceptions that keep a page from
    going stale: a chat doing work of its own for the person (`work`, the job it was started
    for, or work it began with `ask --here`, still going or finished within OWN_JOB_S), which
    no chat can tell the listener about (a chat in the cloud cannot message another one), and
    any chat while nobody answers the page (the first publish). Small work an old helper took
    as the listener is not its own in this sense: it hands the page on with it. Every other
    chat, an old helper after a hand-over above all, writes only its own work items and
    receipts: during a hand-over the old and new helper both rewrote whole screens, and each
    update bounced off the other's (the maintainer, 4 November)."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    rec, _version = record(db)
    who = str(rec.get("chat") or "")
    mine = {c for c in (this_chat(""), this_chat(chat)) if c}
    if not who or who in mine:
        return True, ""
    # A chat that took the page in this wake, after the read: its own claim, kept in this
    # copy, is newer than the record the read holds. Never the other way: an old helper's
    # own record of itself is older than the one that took the page from it.
    took = seen().get("listener") or {}
    if str(took.get("chat") or "") in mine and str(took.get("since") or "") > \
            str(rec.get("since") or ""):
        return True, ""
    jobs = db.get("work") or {}
    own = [w for w in (work, _job_chat()) if w]
    if any(page_db.safe_id(w) in jobs for w in own):
        return True, ""
    for doc in jobs.values():
        d = doc.get("data") or {}
        if not d.get("in_chat") or str(d.get("claimed_by") or "") not in mine:
            continue
        if str(d.get("status") or "") in page_db.ACTIVE:
            return True, ""
        done = _time(d.get("finished_at"))
        if done is not None and (now - done).total_seconds() < OWN_JOB_S:
            return True, ""
    return False, VIEW_LEFT


def _job_chat() -> str:
    try:
        import app_setup
        return app_setup.job_chat()
    except Exception:  # noqa: BLE001  no copy: no job
        return ""


def view_renewal(db: dict, chat: str, now: dt.datetime) -> list[str]:
    """The renewal line when a page update by the chat that answers the page finds its day
    or its size up: the morning brief runs in that chat and brings the page up to date, but
    the renewal was printed only at a check-in the brief never made, so one helper ran for
    days (2026-11-03). It writes nothing: `answered_at` says the chat took the work waiting,
    and a page update takes none (the release review). Only with the work queue in the dump,
    so a job still running is never handed over; and the chat is this session's own id
    whatever `--chat` says (the brief passes a word, not an id)."""
    chat = this_chat("") or this_chat(chat)
    rec, _ = record(db)
    if not chat or rec.get("chat") != chat or "work" not in db:
        return []
    renew = renewal(rec, db, chat, now)
    return [renew_line(renew)] if renew else []


def context_tokens() -> int:
    """How much this chat's history has grown since its first turn: its last turn's input
    less its first's, from the newest session file Claude Code keeps under ~/.claude/projects
    (CLAUDE_CONFIG_DIR where set). 0 when there is none or it cannot be read: then only the
    day decides."""
    root = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
                        "projects")
    try:
        files = [os.path.join(root, d, f) for d in os.listdir(root)
                 if os.path.isdir(os.path.join(root, d))
                 for f in os.listdir(os.path.join(root, d)) if f.endswith(".jsonl")]
        newest = max(files, key=os.path.getmtime) if files else ""
        if not newest:
            return 0
        size = os.path.getsize(newest)
        with open(newest, "rb") as fh:
            head = fh.read(min(size, 262144)).decode("utf-8", "replace")
            fh.seek(max(0, size - 262144))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return 0

    def used(lines):
        for line in lines:
            if '"usage"' not in line:
                continue
            try:
                u = json.loads(line)["message"]["usage"]
                return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens"))
            except (ValueError, KeyError, TypeError):
                continue
        return None
    last, first = used(reversed(tail.splitlines())), used(head.splitlines())
    return max(0, (last or 0) - (first or 0)) if last is not None else 0


def renewal(rec: dict, db: dict, chat: str, now: dt.datetime) -> dict | None:
    """The create_session call for a fresh helper, or None. Only a cloud chat answering the
    page for RENEW_S (or grown by RENEW_TOKENS), with no small work of its own in hand, and
    not asked for in the last RENEW_RETRY_S. Work waiting in the queue moves with the page:
    the new helper takes it. Waiting on it kept one helper answering for three days, against
    a day, while a draft sat queued (engine audit, 2026-11-03); a big job runs in a chat of
    its own, whichever chat claimed it."""
    import page_db
    if not chat or rec.get("chat") != chat or chat_kind() != "cloud":
        return None
    # Only a helper the app started is renewed: the chat the person published from, and
    # writes in, is theirs, and a helper started from it unasked archived it and took its
    # brief (the stranger audit, X-4).
    if not rec.get("helper"):
        return None
    since = _time(rec.get("since"))
    if since is None:
        return None
    big = context_tokens() >= RENEW_TOKENS
    if (now - since).total_seconds() < RENEW_S and not big:
        return None
    work = db.get("work") or {}
    for doc in work.values():
        d = doc["data"]
        if str(d.get("claimed_by") or "") == chat and \
                not page_db.WORK_KINDS.get(str(d.get("kind") or ""), {}).get("heavy") and \
                page_db._live_claim(d, now, work):
            return None
    got = seen()
    last = _time(got.get("renewed_at"))
    # This chat still answers the page, so a helper asked for that long ago never took it
    # (its create_session failed, or it never started): it is asked for again, not a day on.
    if last is not None and (now - last).total_seconds() < RENEW_RETRY_S:
        return None
    try:
        import app_setup
        owner, name = app_setup.origin()
    except Exception:  # noqa: BLE001  no address to start it from: stay as it is
        return None
    if not owner or not name:
        return None
    got["renewed_at"] = _stamp(now)
    _save_seen(got)
    # The page's data tools carried over (create_session's extra_allowed_tools keeps only what
    # this chat has pre-approved: ArtifactData and ArtifactComments, never Artifact), so the
    # fresh helper never stops on a prompt to write the page's data while the person is away
    # (2026-11-03); its republishes declare no capabilities once the page has them (X-8). The
    # prompt is the person's plain words, and the app's hook says what they mean (X-84).
    return {"title": HELPER_CHAT_TITLE, "prompt": WAKE_PROMPT,
            "source_url": f"https://github.com/{owner}/{name}",
            "extra_allowed_tools": ["ArtifactData", "ArtifactComments"]}


def first_claim(chat: str, out_dir: str, now: dt.datetime | None = None,
                title: str = "") -> dict:
    """The claim a chat makes right after the page's first publish: its database is empty,
    so the record is created, and a second chat's create is refused."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    w = page_db.Writes(out_dir)
    at = _stamp(now)
    new = {"chat": chat, "title": title or "Job search", "kind": chat_kind(), "helper": False,
           "since": at, "answered_at": at, "watching": True, "took_from": None}
    w.add("set", DOC_COLLECTION, DOC_ID, new)
    _remember(new, now, confirmed=False)
    return {"record": new, "batches": w.save("listen")}


# ------------------------------------------------------------------ republish


def page_version() -> int:
    import build_versions
    return build_versions.current("page")


def republish(out_dir: str, now: dt.datetime | None = None, version: int | None = None) -> dict:
    """The page's own code changed, and this chat does not answer the page: the request to
    republish it, for the listener, as one batch. Its id carries the page's version, so two
    chats asking for the same one make one request (the second create is refused)."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    v = version or page_version()
    wid = f"republish~v{v}"
    w = page_db.Writes(out_dir)
    w.add("set", "work", wid, {
        "kind": "republish", "title": REPUBLISH_TITLE, "to": "either",
        "args": {"version": v}, "asked_at": _stamp(now), "asked_from": {"tab": "chat"},
        "status": "queued", "priority": 1})
    return {"work": wid, "batches": w.save("republish")}


STAGES = [("build", "Building the new page", 20), ("publish", "Putting it up", 20)]


def next_republish(db: dict, chat: str, now: dt.datetime) -> dict | None:
    """The queued republish this chat should take: only the listener's, oldest first.
    `already` is True when the page is current, so the item is closed with nothing
    published (a republish reloads every open window)."""
    rec, _ = record(db)
    if not chat or rec.get("chat") != chat:
        return None
    queued = sorted((str(d["data"].get("asked_at") or ""), wid)
                    for wid, d in (db.get("work") or {}).items()
                    if d["data"].get("kind") == "republish"
                    and str(d["data"].get("status") or "") == "queued")
    if not queued:
        return None
    wid = queued[0][1]
    item = db["work"][wid]["data"]
    # The page's own "did not load fully" button (templates/app/guard.js): every code file
    # goes up again, the page current or not, unless it was published since it asked.
    whole = bool((item.get("args") or {}).get("whole"))
    try:
        import build_versions
        already = not build_versions.behind("page")
    except Exception:  # noqa: BLE001  no profile: publish it
        already = False
    if whole:
        import app_setup
        since = str(app_setup.page_record().get("published_at") or "")
        already = bool(since) and since > str(item.get("asked_at") or "")
    return {"work": wid, "version": db["work"][wid]["version"], "kind": "republish",
            "title": REPUBLISH_TITLE, "locks": [], "already": already, "whole": whole,
            "stages": [{"key": k, "name": n, "est_s": s} for k, n, s in STAGES]}


def close_republish(db: dict, out_dir: str, now: dt.datetime | None = None) -> dict:
    """Every republish request still open, closed: this chat has just put the page up, so
    none of them is waiting any more. One stayed "queued" after a chat published the page
    itself, and the page said an update was waiting until the person asked for the notice to
    go (2026-10-30). {"closed": [ids], "batches": [...]}."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    w = page_db.Writes(out_dir)
    closed = []
    for wid, d in sorted((db.get("work") or {}).items()):
        if d["data"].get("kind") != "republish" or \
                str(d["data"].get("status") or "") not in ("queued", "claimed", "running"):
            continue
        w.add("update", "work", wid, {"status": "done", "finished_at": _stamp(now),
                                       "result": {"summary": "Your page is up to date.",
                                                  "links": []}},
              if_version=d["version"])
        closed.append(wid)
    return {"closed": closed, "batches": w.save("published") if closed else []}


def without_republish(db: dict) -> dict:
    """The dump with republish requests left out, for a chat that may not take them."""
    out = dict(db)
    out["work"] = {k: v for k, v in (db.get("work") or {}).items()
                   if v["data"].get("kind") != "republish"}
    return out


# ------------------------------------------------------------------ what the page shows


def wake_url(repo: str = "") -> str:
    """The link the page shows when nobody answers: it opens a new chat on the person's
    copy with WAKE_PROMPT typed (claude.ai/code's documented pre-filled link, `prompt` and
    `repositories`); the chat is made only when they press Send."""
    url = "https://claude.ai/code?prompt=" + urllib.parse.quote(WAKE_PROMPT, safe="")
    return url + ("&repositories=" + urllib.parse.quote(repo, safe="") if repo else "")


def model_part(repo: str = "") -> dict:
    """What the page needs to show "Claude isn't listening": where the listener's record is
    (the page reads it live: `answered_at` is when it last answered), how long something may
    wait before nobody is answering, and the link that opens a chat which becomes the
    listener. No time is embedded, so the model's rev holds while nothing changed."""
    return {"doc": f"{DOC_COLLECTION}/{DOC_ID}", "answered": "answered_at",
            "quiet_after_s": LAPSE_S, "helper": HELPER_TITLE,
            "wake": {"label": "Wake Claude", "url": wake_url(repo), "prompt": WAKE_PROMPT}}


def privacy() -> str:
    """The page's footer line (claude_surfaces: page-share): true while the page is not
    shared, and saying what it holds."""
    import claude_surfaces
    return claude_surfaces.entry("page-share")["line"]


# ------------------------------------------------------------------ the pin


def pin_asked() -> bool:
    """Was the pin ever offered? Offered is enough: the offer is made at most once, answered
    or not (profile/app.json `pin`, kept with the rest of the person's state)."""
    import app_setup
    pin = app_setup.page_record().get("pin") or {}
    return bool(pin.get("asked") or pin.get("offered"))


def record_pin(answer: str, today: dt.date | None = None) -> str:
    """Their answer to "pin it?": profile/app.json `pin`. "later" is the page's Not now:
    each one is kept, so `pin_due` can ask again after a while and then stop."""
    if answer not in ("yes", "no", "later"):
        raise ValueError("the answer is yes, no or later")
    day = (today or dt.date.today()).isoformat()
    if answer == "later":
        import app_setup
        later = list((app_setup.page_record().get("pin") or {}).get("later") or [])
        return _write_pin(later=sorted(set(later + [day])))
    return _write_pin(asked=day, answer=answer)


# The page's own offer, asked again only after a while and only a few times: the chat's
# offer was once ever, and most people who missed it never found Settings (the maintainer,
# 2026-10-30: "make it more prominent ... during setup ... and for existing installs ...
# not permanently just be smart about it", and "don't pester the user").
PIN_AGAIN_DAYS = 30
PIN_ASKS = 3


def pin_due(today: dt.date | None = None) -> bool:
    """Should the page offer the pin now? Never once it is pinned. A no in the chat or a Not
    now on the page each count as one answer; after one, it is asked again a month later,
    and after `PIN_ASKS` of them, never (the button in Settings stays)."""
    import app_setup
    pin = app_setup.page_record().get("pin") or {}
    if pin.get("answer") == "yes":
        return False
    said = [str(d) for d in (pin.get("later") or []) if d]
    if pin.get("answer") == "no" and pin.get("asked"):
        said.append(str(pin["asked"]))
    if len(said) >= PIN_ASKS:
        return False
    if not said:
        return True
    try:
        last = dt.date.fromisoformat(max(said)[:10])
    except ValueError:
        return True
    return (today or dt.date.today()) >= last + dt.timedelta(days=PIN_AGAIN_DAYS)


def record_pin_offered(today: dt.date | None = None) -> str:
    """The pin was offered (its line printed): it is never offered again, whether or not
    the person answered or the chat recorded their answer."""
    return _write_pin(offered=(today or dt.date.today()).isoformat())


def _write_pin(**fields) -> str:
    import app_setup
    got = app_setup.page_record()
    got["pin"] = dict(got.get("pin") or {}, **fields)
    path = os.path.join(app_setup.profile_dir(), app_setup.PAGE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    _replace(tmp, path)
    return path


def pin_line(url: str, n: int | None = None) -> str:
    """The once-only offer to pin the page (claude_surfaces: find-page)."""
    import claude_surfaces
    ask = claude_surfaces.entry("find-page")["ask"]
    head = f"{n}. " if n is not None else ""
    return (f"{head}Ask the person once, in these words: \"{ask}\" On a yes: Artifact, action "
            f"pin, url {url}. Either way, then python3 tools/app.py pinned yes|no. It is "
            "offered this once and never again: never mention pinning otherwise.")


# ------------------------------------------------------------------ start's steps


def _check_in(chat: str, url: str, claim: bool, listen: bool, helper: bool,
              update: bool = False) -> str:
    flags = (" --listen" if listen else "") + (" --helper" if helper else "") + \
        (" --update" if update else "")
    if claim:
        return (f"Ask the page which chat answers it, before publishing anything: ArtifactData "
                f"query (url {url}, collection meta) and query (collection work, where "
                "status == queued), both with out_dir <your scratchpad>/listen; "
                f"then python3 tools/app.py listen <your scratchpad>/listen --chat "
                f"{chat or '<this chat id>'}{flags}, and send the batch it prints. It makes "
                "this chat the listener only where none answers, or where the person asked "
                "this chat to look after the page; otherwise this chat neither publishes nor "
                "watches the page, and says nothing about either.")
    return (f"This chat answers the person's page. Keep its watch on: ArtifactComments, action "
            f"watch, url {url} (a watch that started by itself can end after hours with no "
            "activity; asking for one starts it again). Then check in: ArtifactData query (url "
            f"{url}, collection meta, out_dir <your scratchpad>/listen), "
            f"python3 tools/app.py listen <your scratchpad>/listen --chat {chat}{flags}, and "
            "send the batch it prints. If it says another chat answers the page now, stop "
            "this chat's watch (watch, url, on: false) and publish nothing.")


def _numbered(line: str) -> tuple[str, str] | None:
    m = _NUM.match(line)
    return (m.group(1), line[m.end():]) if m else None


def shape(code: int, lines: list[str], chat: str = "", listen: bool = False,
          helper: bool = False, on: str = "", work: str = "") -> list[str]:
    """start's lines, with what this chat does about the page: the listener publishes and
    watches, a chat that may become it asks the page first, any other chat does neither.
    `work` is a chat the listener started for one big job (`app.py next`): it does that job
    and nothing about the page."""
    if code != 0 or len(lines) < 2:
        return lines
    import app_setup
    url = app_setup.page_record().get("url", "") or ""
    who = "work" if work and url else role(chat, listen, url)
    steps = list(lines[2:])
    text = [(_numbered(ln) or ("", None))[1] for ln in steps]
    found = [i for i, t in enumerate(text) if t is not None and t.startswith(_PUBLISH)]
    watch = [i for i, t in enumerate(text) if t is not None and t.startswith(_WATCH)]
    publish = [text[i] for i in found]
    behind = bool(found) and bool(url)
    at = (found or watch or [None])[0]
    gone = set(found) | set(watch)
    keep = [(text[i] is not None, text[i] if text[i] is not None else ln)
            for i, ln in enumerate(steps) if i not in gone]
    if at is None:
        at = next((i for i, (step, t) in enumerate(keep) if step and t.startswith(_BEFORE)),
                  len(keep))
    else:
        at = sum(1 for i in range(at) if i not in gone)
    add: list[str] = []
    if who == "work":
        add.append(f"This chat does one job for the page ({work}) and nothing else about it: "
                   "it never publishes, watches or answers the page, and never writes its "
                   "view. Carry on with what started it.")
    elif who == "first":
        if publish:
            add = publish + ["Publishing makes this chat watch the page, which makes it the "
                             "page's listener: the one chat a tap on the page wakes. The "
                             "published step records that and prints one batch to send."]
    elif who == "other":
        got = seen()
        told = got.get("told") or {}
        if (chat or "?") not in told:
            who = "your Job search helper chat" if (got.get("listener") or {}).get("helper") \
                else "another of your chats"
            add.append("Another chat answers the person's page. This chat neither publishes it "
                       "nor watches it. Tell the person once, at the end of this reply, as it "
                       f"is: \"{SAY_OTHER_CHAT.format(who=who)}\" Never again in this chat. If "
                       "it watches the page from before (ArtifactComments, action watch with no "
                       "url, lists this chat's watches), stop that watch: action watch, url "
                       f"{url}, on: false.")
            told[chat or "?"] = dt.date.today().isoformat()
            got["told"] = dict(sorted(told.items(), key=lambda kv: kv[1])[-50:])
            _save_seen(got)
        if behind:
            add.append("The page's own code changed. " + _update_check(url, chat))
            add += [f"If that left this chat as the listener: {p[:1].lower()}{p[1:]}"
                    for p in publish]
            add.append("Otherwise: " + _ask_listener(url))
    else:
        add.append(_check_in(chat, url, who == "claim", listen, helper, update=bool(publish)))
        if helper:
            add.append(helper_busy(chat, url))
        if publish:
            add += [f"If that left this chat as the listener: {p[:1].lower()}{p[1:]}"
                    for p in publish]
            add.append("Otherwise: " + _ask_listener(url))
        # The pin is offered by the publish step alone (`published_lines`), which records it.
        try:
            import routines
            if routines.calls():
                add.append("The page asked for a change to the brief's schedule: python3 "
                           "tools/routines.py calls prints each scheduled-task call; make "
                           "it, then python3 tools/routines.py called <its n>.")
        except Exception:  # noqa: BLE001  no profile yet, or no registry
            pass
    keep[at:at] = [(True, a) for a in add]
    if helper and who in ("claim", "listener"):
        # The link once, first, in the helper's own line: the page's introduction would say it
        # a second time, in a paragraph.
        keep = [(step, t) for step, t in keep if not (step and t.startswith(_INTRO))]
        keep = [(True, helper_first(url))] + keep + [(True, helper_last(chat, url))]
    out, n = [], 0
    for step, t in keep:
        if step:
            n += 1
            out.append(f"{n}. {t}")
        else:
            out.append(t)
    return lines[:2] + out


def introduced() -> bool:
    """Was the person ever told what their page is? Told once (profile/app.json
    `introduced`), or they answered about it (the pin), or setup said it ("Your setup is on
    your page")."""
    import app_setup
    rec = app_setup.page_record()
    return bool(rec.get("introduced") or (rec.get("pin") or {}).get("answer"))


def mark_introduced(today: dt.date | None = None) -> None:
    import app_setup
    got = app_setup.page_record()
    if got.get("url") and not got.get("introduced"):
        got["introduced"] = (today or dt.date.today()).isoformat()
        try:
            app_setup.write_json(os.path.join(app_setup.profile_dir(), app_setup.PAGE), got)
        except OSError:
            pass


def helper_first(url: str) -> str:
    """A new helper's first words: the page's link, at once (the maintainer, 2026-11-04)."""
    return ("Say this to the person at once, before any other step, as it is: "
            f"\"{say(SAY_HELPER, url)}\" Then nothing about this chat or its work until the "
            "last step.")


def helper_busy(chat: str, url: str) -> str:
    """While a new helper works, the page says so (the chat's heartbeat, `app.py busy`)."""
    return ("Once the check-in is accepted, show on the page that this chat is at work: "
            f"ArtifactData query (url {url}, collection beats, out_dir <your scratchpad>/beats), "
            f"then python3 tools/app.py busy <your scratchpad>/beats \"{HELPER_BUSY}\" --chat "
            f"{chat or '<this chat id>'}, and send the batch it prints. Do the rest, and any "
            "brief or job the check-in brings, while the page shows it.")


def helper_last(chat: str, url: str) -> str:
    """A new helper's last words: one line that it is ready, never the brief or a paragraph
    about what it is (the maintainer, 2026-11-04)."""
    return ("When all of this start's work is done (any brief or job the check-in brought "
            "included, and the page brought up to date): python3 tools/app.py busy <your "
            f"scratchpad>/beats --done --chat {chat or '<this chat id>'}, and send its batch "
            "(refused: read beats again and run it once more). Then say only this, as it is: "
            f"\"{say(SAY_HELPER_READY, url)}\" Nothing else in this reply: never the brief, its "
            "news or its replies, and never what this chat is for; the page holds them. If the "
            "check-in said another chat answers the page, say nothing more.")


_INTRO = "Tell the person once, at the start of your reply, in these words"


def intro_line(url: str) -> str:
    """The once-only line that tells the person what their page is (X-25, the chat-only
    review's S1): a page published and never named was a page they never knew they had."""
    return f"{_INTRO}, before anything else about the page: \"{say(SAY_FIRST_PAGE, url)}\""


def published_lines(url: str, chat: str, first: bool, out_dir: str,
                    now: dt.datetime | None = None, replaced: bool = False) -> list[str]:
    """What `app.py published` says after a publish: the first publish (or a fresh page in
    place of one that could no longer be published to) makes this chat the listener, its
    record created on the page; the person is told once what the page is, or its new
    address; and the pin is offered once."""
    import app_setup
    out = []
    if (first or replaced) and chat:
        got = first_claim(chat, out_dir, now)
        out.append("app: this chat is the page's listener now: send this batch (ArtifactData "
                   f"batch, url {url}): " + " ".join(got["batches"]))
    if replaced:
        out.append("app: tell the person this one line, once: "
                   f"\"{say(SAY_NEW_ADDRESS, url)}\"")
        mark_introduced()
    elif not introduced():
        # During setup its own line says it ("Your setup is on your page: <link>"): one line,
        # never two that each say "nothing more" (the chat-only review).
        if app_setup.set_up() and app_setup._finished():
            out.append("app: " + intro_line(url))
        mark_introduced()
    if not pin_asked():
        out.append("app: " + pin_line(url))
        try:
            record_pin_offered()
        except OSError:
            pass
    try:
        import routines
        if first and routines.remind_due():
            # Nothing else is scheduled before setup's last step: a stranger who answered
            # nothing in the first sitting was never contacted again (X-23).
            out.append("app: setup waits on the page: python3 tools/routines.py remind, and make "
                       "the call it prints (one reminder tomorrow, in this chat), asking nothing "
                       "and saying nothing about it")
    except Exception:  # noqa: BLE001  never breaks the publish
        pass
    return out


# ------------------------------------------------------------------ after an update


def _ask_listener(url: str) -> str:
    """Another chat answers the page and has been heard from lately: ask it, and say so."""
    return ("python3 tools/app.py republish <your scratchpad>/republish, then send the batch it "
            f"prints (ArtifactData batch, url {url}); refused means the request is there "
            "already. Do not wait for it: the page shows its progress. Tell the person this "
            f"one line, and nothing else about the page or the update: "
            f"\"{say(SAY_UPDATING, url)}\"")


def _update_check(url: str, chat: str) -> str:
    """Which chat puts the update up: this one, unless another answers the page and has been
    heard from within UPDATE_QUIET_S. Start's own check-in, where it printed one, is this
    same step, so it is done once (it was asked for twice, 2026-10-30)."""
    return ("Which chat answers the page: if python3 tools/app.py start printed a step that asks "
            "the page this, that step is this one: do it once, adding --update to its listen "
            f"command. Otherwise: ArtifactData query (url {url}, collection meta) and query "
            "(collection beats), both with out_dir <your scratchpad>/listen, then python3 "
            "tools/app.py listen <your scratchpad>/listen --chat "
            f"{chat or '<this chat id>'} --update, and send the batch it prints. With --update "
            "this chat takes the page from a chat quiet for an hour or more, so an update "
            "never waits on a chat that has stopped.")


def _publish_now(url: str, n: int) -> list[str]:
    """The republish itself, numbered from `n`: build and publish what changed, keep, one line.
    The build prints the publishes (`parts_plan`): only the small files the page lacks."""
    return [f"{n}. python3 tools/app.py page --out-dir <your scratchpad>/page --url {url}, then "
            "do the read and the list of the page's files it asks for first, then make exactly "
            "the publishes it prints, reading each file a publish names whole first (each "
            "is small; the code the page already holds is left out and kept). If a publish is "
            f"refused, read the page again and publish once more (Artifact, action read, url "
            f"{url}, then the same publish; refused again only as the same content sent "
            "unchanged, send it once more as it is: the build is the whole page, so nothing on "
            "the live page is lost). If the read says the page is not there or not this person's, build a new one "
            f"({REBUILD}) and publish that instead, then use its new url below. Only if a "
            f"publish is refused twice: python3 tools/app.py published {url}, then tell the "
            f"person this one line and stop: \"{say(SAY_NOT_UPDATED, url)}\"",
            f"{n + 1}. ArtifactData query (url {url}, collection work, where kind == republish, "
            f"out_dir <your scratchpad>/published), then python3 tools/app.py published {url} "
            "--parts <your scratchpad>/page --dump <your scratchpad>/published, and do what it "
            "prints: it keeps which files the page holds and closes any request for this update "
            "still waiting on the page.",
            f"{n + 2}. Tell the person this one line, and nothing else about the page or the "
            f"update: \"{say(SAY_UPDATED, url)}\""]


# A page whose address cannot be published to any more (deleted, or another account's):
# built afresh, published as a new page, and its new address kept and said once (X-44).
REBUILD = "python3 tools/app.py page --out-dir <your scratchpad>/page, with no --url"
# A chat whose window holds this many tokens or fewer gives each publish after the first to
# an agent of its own, so no one context reads every file of a first publish.
SMALL_WINDOW = 200_000


def parts_plan(built: dict, url: str = "", listing: str | None = None,
               whole: bool = False) -> list[str]:
    """What `app.py page --out-dir` prints: the publishes that put the page in parts up, read
    file by file. A page already published (a url) is first read and its files listed, and
    the build is run again with that list (`--on-page`): only the files the page lacks go up,
    so a file the record says it holds and the host does not (a publish cut short, a file
    lost) goes up again, and every file the publish replaces or takes off is one this chat
    has seen listed, as the Artifact tool asks. `whole` (the page's own "did not load fully"
    button, templates/app/guard.js): every code file goes up again. Its capabilities are
    declared only when they changed, since a publish that declares them asks the person
    first (code.claude.com/docs/en/artifacts, "When Claude Code asks before publishing") and
    one that leaves them out keeps them (the artifact-capabilities skill)."""
    import app_page
    import app_setup
    rec = app_setup.page_record()
    same = bool(url) and url == rec.get("url")
    sizes = built["sizes"]
    folder = os.path.dirname(built["page"])

    def kb(n: int) -> int:
        return max(1, round(n / 1024))
    if url and listing is None:
        again = (f"python3 tools/app.py page --out-dir {folder} --url {url}"
                 + (" --whole" if whole else "") + " --on-page - <<'EOF'")
        return [f"app: the page is built in parts: {built['page']} ({kb(sizes['page.html'])} KB) "
                f"and {len(built['files'])} small code files beside it. First see what the "
                "published page holds, so only what it lacks goes up:",
                f"1. Artifact, action read, url {url} (the small page: the tool asks for a read "
                "before a publish to a page this chat did not publish).",
                f"2. Artifact, action list, scope files, url {url}.",
                f"3. {again}, then every line that list printed, exactly as it came, then a line "
                "EOF; and make exactly the publishes that prints, in order."]
    listed = app_page.on_page(listing) if listing is not None else None
    got = app_page.plan(built, rec.get("code") if same else None,
                        str(rec.get("caps") or "") if same else "", url, listed=listed, whole=whole)
    new_kb = kb(sum(sizes[p] for p in got["new"])) if got["new"] else 0
    out = [f"app: the page is built in parts: {built['page']} ({kb(sizes['page.html'])} KB) and "
           f"{len(built['files'])} small code files beside it, {len(got['new'])} of them to "
           f"put up ({new_kb} KB). Read each file a publish names whole, just before "
           "that publish; every one is small. A code file the page already holds is left out, "
           "and the page keeps it."]
    if got["missing"]:
        out.append(f"app: {len(got['missing'])} code files the page should hold are not on it "
                   "as they were built; they go up again below.")
    caps = (", with the capabilities python3 tools/app_page.py --capabilities prints"
            if got["capabilities"] else ", with no capabilities (the page keeps its own)")
    first_at = f"url {url}" if url else "icon briefcase"
    later = f"url {url}" if url else "url <the url the first publish gave>"
    n = 1
    for i, batch in enumerate(got["batches"]):
        files: dict = {p: built["files"][p] for p in batch}
        if i == 0:
            files.update({p: None for p in got["gone"]})
        tail = f", files {json.dumps(files, ensure_ascii=False)}" if files else ""
        out.append(f"{n}. Artifact, action publish, file_path {built['page']}, "
                   f"{first_at + caps if i == 0 else later}{tail}")
        n += 1
    if len(got["batches"]) > 1:
        out.append(f"Where this chat's window holds {SMALL_WINDOW:,} tokens or fewer, give each "
                   "publish after the first to an agent of its own (Agent tool), one after "
                   "another, each told: \"Read each file this publish names whole, then Artifact, "
                   f"action read, {later}, then make exactly this publish: <the step>\". So no "
                   "one chat reads every file.")
    return out


def after_update(landed: bool = False, chat: str = "") -> list[str]:
    """What this chat does about the person's page once an update is in: the day's sync,
    `sync_app.py --if-stale`, or `--update` when the person said "update". The page's own
    code changed: republish it now (the listener does; any other chat asks the listener, at
    once). Only its data could have changed (`landed`): `app.py view`. Never a question, and
    one line to the person. [] when there is no page yet (start publishes the first one) or
    nothing changed for it."""
    import app_setup
    url = str(app_setup.page_record().get("url") or "")
    if not url or not app_setup.set_up():
        return []
    behind = not app_setup._page_current()
    if not behind and not landed:
        return []
    chat = this_chat(chat)
    who = role(chat, False, url)
    if not behind:
        return [f"Claude: an update just landed. Bring the person's page up to date now. {NO_ASK}",
                "1. ArtifactData query, once for each of the collections screen, meta and addr "
                f"(url {url}, out_dir <your scratchpad>/page-data, limit 1000).",
                "2. python3 tools/app.py view <your scratchpad>/page-writes --dump <your "
                "scratchpad>/page-data" + (f" --chat {chat}" if chat else ""),
                f"3. Send each batch it prints, in order (ArtifactData batch, url {url}). If one "
                "is refused, do steps 1 to 3 once more; only if it is refused again, tell the "
                f"person this one line and stop: \"{say(SAY_NOT_UPDATED, url)}\"",
                "4. Tell the person this one line, and nothing else about the page or the "
                f"update: \"{say(SAY_UPDATED, url)}\""]
    head = f"Claude: the update changed the person's page itself. {NO_ASK}"
    if who == "listener":
        return [head + " Republish it:"] + _publish_now(url, 1)
    # Any other chat checks first: one heard from lately puts it up; a quiet one never holds
    # it, and this chat publishes it itself.
    return [head + " Republish it:",
            "1. " + _update_check(url, chat),
            "2. If it says another chat answers the page: " + _ask_listener(url) +
            " Then stop here."] + _publish_now(url, 3)

