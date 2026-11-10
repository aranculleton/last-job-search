"""A reply drafted in one chat stays on its person's card while that chat's save lands.

The maintainer, 2026-11-10: "A drafted reply doesn't show on the person's card until the save
lands. The reply is drafted and committed locally ... but the person's card in Contacts is
drawn from the main saved copy, which still has the old draft." The chat that drafted it drew
the page with the new draft; the page's helper, whose copy is master and lacks that commit,
then drew it again with the old one. Screens were judged only by the commit each copy shares
with master, so a copy holding work not landed yet looked no newer than master. Screens now
carry that copy's own newest commit too, and a chat whose copy lacks it leaves them as they
are for a while (app.py `holds_unlanded`), never for good.

The real path: `reply.py finish` saves each draft, `app.py view` draws the page from each
chat's copy, and the store keeps the real one's rules. Every person, employer and chat id is
invented (tests/app_state.py's small search).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

JUNO = "larkspur_retail_castellan"
OWN = "session_EXAMPLEOWNCHAT"          # the person's own chat, where the reply was drafted
OLD = "Thanks Juno, that is kind of you. Thursday afternoon suits me well."
NEW = "Thanks Juno, that is kind of you. Friday morning suits me better, if it works."


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def _git(path, *args):
    return subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c",
                           "user.email=t" + "@example.com", *args], capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout.strip()


def _commit(path, line):
    if not os.path.isdir(os.path.join(path, ".git")):
        _git(path, "init", "-q")
    with open(os.path.join(path, "a.txt"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", line)
    return _git(path, "rev-parse", "HEAD")


def _draft(ring, text):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reply.py"),
                        "finish", JUNO, "--draft-file", "-", "--today", "2026-10-25",
                        "--now", R.NOW], input=text + "\n", env=ring.env(),
                       capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def _view(ring, chat, now, base, head):
    """`app.py view` as `chat`, its copy based on master's `base` and at its own `head`, every
    batch sent: (what it printed, whether every batch was taken)."""
    import fake_db
    d = ring.dump(f"d-{chat}-{now[11:16].replace(':', '')}")
    got = json.loads(ring.run("view", os.path.join(d, "v"), "--dump", d, "--chat", chat,
                              "--now", now, LJS_PAGE_MIRROR=ring.mirror, LJS_BASIS_SHA=base,
                              LJS_HEAD_SHA=head))
    return got, all(fake_db.apply(ring.db, b) for b in got["batches"])


def _card_draft(ring):
    """The words the page shows under Juno: the message to them in the page's messages screen,
    the one their card in Contacts draws (app.js personDraft)."""
    with open(os.path.join(ring.db, "screen", "messages.json"), encoding="utf-8") as fh:
        msgs = json.load(fh)["data"]["data"]
    return next(m["body"] for m in msgs if m["contact"] == JUNO)


def test_a_reply_drafted_in_a_chat_is_never_drawn_over_by_a_copy_that_lacks_it(ring):
    master = _commit(ring.state, "master")
    # On master, the old draft; the helper draws the page from it.
    _draft(ring, OLD)
    got, ok = _view(ring, R.CHAT, "2026-10-25T18:00:00Z", master, master)
    assert ok, got
    assert _card_draft(ring) == OLD
    # The person's own chat drafts the new reply and commits it, not landed yet, then draws
    # the page: the new draft is on Juno's card.
    _draft(ring, NEW)
    theirs = _commit(ring.state, "the new reply, not landed")
    _git(ring.state, "reset", "-q", "--hard", master)    # the helper's copy is master
    got, ok = _view(ring, OWN, "2026-10-25T18:05:00Z", master, theirs)
    assert ok and _card_draft(ring) == NEW, got
    # The helper, whose copy is master and still holds the old draft, draws the page next: the
    # screen the new draft is on is left as it is.
    _draft(ring, OLD)
    got, ok = _view(ring, R.CHAT, "2026-10-25T18:10:00Z", master, master)
    assert ok and "messages" in (got.get("kept_newer") or []), got.get("kept_newer")
    assert _card_draft(ring) == NEW
    # Once the save lands the helper's copy has it, and draws every screen again.
    _git(ring.state, "merge", "-q", theirs)
    _draft(ring, NEW)
    got, ok = _view(ring, R.CHAT, "2026-10-25T18:15:00Z", theirs, theirs)
    assert ok and not got.get("kept_newer"), got.get("kept_newer")
    assert _card_draft(ring) == NEW


def test_a_save_that_never_lands_holds_the_page_only_for_a_while(ring):
    master = _commit(ring.state, "master")
    _draft(ring, NEW)
    got, ok = _view(ring, OWN, "2026-10-25T18:00:00Z", master, "f" * 40)
    assert ok and _card_draft(ring) == NEW, got
    # Their commit is never seen here: kept a while, then drawn again from this copy, so a
    # chat that ended without saving never stops the helper drawing the page for good.
    _draft(ring, OLD)
    got, _ok = _view(ring, R.CHAT, "2026-10-25T18:20:00Z", master, master)
    assert "messages" in (got.get("kept_newer") or [])
    got, ok = _view(ring, R.CHAT, "2026-10-25T18:31:00Z", master, master)
    assert ok and not got.get("kept_newer"), got.get("kept_newer")
    assert _card_draft(ring) == OLD
