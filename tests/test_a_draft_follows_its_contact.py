"""A waiting draft follows what happens to its contact, so the page never offers one that
no longer fits.

Three ways a draft outlived its moment in the maintainer's own copy (2026-11-05): a contact
closed by hand (`state.py set --status closed`, or the next action cleared) kept the draft
on the page, where the page's own stop parks it; a draft written before a newer message of
theirs (one the LinkedIn download brought days late, asking for the resume) was still
offered as the reply; and a thank-you to "I'll keep you in mind" set a follow-up, due the
same day. Every person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

ANSGAR = "kestrel_mutual_ansgar"            # a first note waiting (tests/app_state.py)
LARKSPUR = "larkspur_retail_castellan"       # asked for the resume on 2026-09-12
FIRST_ACTION = "Send the first note; call 07700 900461 if needed"


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    s.tmp = tmp_path
    return s


def tool(search, script, *args):
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", *script.split("/")), *args],
                       env=env, capture_output=True, encoding="utf-8", errors="replace",
                       timeout=120, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def folder(search, cid):
    return os.path.join(search.state, "documents", "network", cid)


def offered(search, cid):
    return any(m.get("contact") == cid for m in search.model()["messages"])


def contact(search, cid):
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == cid)


def text_file(search, name, words):
    p = search.tmp / name
    p.write_text(words, encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ closed by hand


@pytest.mark.parametrize("how", [("--status", "closed"), ("--status", "gone_cold"),
                                 ("--next-action", "")])
def test_closing_by_hand_parks_the_draft_as_the_pages_stop_does(search, how):
    assert offered(search, ANSGAR)
    code, out = tool(search, "network/state.py", "set", ANSGAR, *how, "--today", "2026-10-25")
    assert code == 0, out
    assert not os.path.exists(os.path.join(folder(search, ANSGAR), "draft.md"))
    assert os.path.exists(os.path.join(folder(search, ANSGAR), "draft.not-needed.md")), \
        "kept, never deleted"
    assert "set aside" in out
    assert not offered(search, ANSGAR)


def test_putting_the_row_back_as_it_was_brings_the_draft_back_and_nothing_else_does(search):
    code, out = tool(search, "network/state.py", "set", ANSGAR, "--status", "closed",
                     "--next-action", "", "--today", "2026-10-25")
    assert code == 0, out
    # A new, different step later is not the undo: the old note stays parked.
    code, out = tool(search, "network/state.py", "set", ANSGAR, "--status", "not_contacted",
                     "--next-action", "Ask a mutual contact first", "--today", "2026-10-25")
    assert code == 0, out
    assert not os.path.exists(os.path.join(folder(search, ANSGAR), "draft.md"))
    # The row exactly as it was (what the page's undo writes) brings it back.
    code, out = tool(search, "network/state.py", "set", ANSGAR, "--status", "closed",
                     "--next-action", "", "--today", "2026-10-25")
    code, out = tool(search, "network/state.py", "set", ANSGAR, "--status", "not_contacted",
                     "--next-action", FIRST_ACTION, "--today", "2026-10-25")
    assert code == 0, out
    assert os.path.exists(os.path.join(folder(search, ANSGAR), "draft.md")), out
    assert offered(search, ANSGAR)


def test_the_pages_undo_still_brings_a_stopped_note_back(search):
    a = search.act("person.stop", ANSGAR, value={"why": "not the right person", "scope": "person"})
    assert search.apply()["ok"] == [a]
    assert not offered(search, ANSGAR)
    search.written_back()
    u = search.act("undo", undoes=a)
    assert search.apply()["ok"] == [u], search.receipt(u)
    assert offered(search, ANSGAR)


# ------------------------------------------------------------------ a newer message of theirs


def _draft_reply(search):
    code, out = tool(search, "network/reply.py", "finish", LARKSPUR, "--draft-file",
                     text_file(search, "reply.txt", "Thanks Juno, that is kind of you. I have "
                                                    "sent my CV to your email."),
                     "--today", "2026-10-25")
    assert code == 0, out
    assert offered(search, LARKSPUR)


def test_a_message_logged_after_the_draft_sets_it_aside(search):
    _draft_reply(search)
    code, out = tool(search, "network/state.py", "received", LARKSPUR, "--text-file",
                     text_file(search, "theirs.txt", "Hi Morgan, could you also send the "
                                                     "names of two referees?"),
                     "--date", "2026-10-25", "--today", "2026-10-25")
    assert code == 0, out
    assert not os.path.exists(os.path.join(folder(search, LARKSPUR), "draft.md"))
    assert os.path.exists(os.path.join(folder(search, LARKSPUR), "draft.older.md"))
    assert not offered(search, LARKSPUR)


def test_a_message_the_download_brings_late_is_one_the_draft_never_saw(search):
    """The download's message is dated before the draft was written: the draft still never
    saw it, and the page reads that from what the draft knew, not from any clock."""
    _draft_reply(search)
    path = os.path.join(search.state, "network_threads.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        cols = list(rows[0].keys())
    rows.append(dict.fromkeys(cols, "") | {
        "contact_id": LARKSPUR, "date": "2026-09-20", "direction": "inbound",
        "channel": "linkedin", "scenario": "send_resume", "summary": "replied",
        "full_text": "Hi Morgan, please send your resume to me directly."})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    assert os.path.exists(os.path.join(folder(search, LARKSPUR), "draft.md"))
    assert not offered(search, LARKSPUR), "a reply to their older message is never offered"


def test_the_download_sets_a_draft_aside_when_it_brings_a_newer_message(search):
    _draft_reply(search)
    script = (
        "import sys; sys.path[:0] = [%r, %r]\n"
        "from network import export, state as st\n"
        "threads, contacts = st.load_threads(st.THREADS_CSV), st.load_contacts(st.CONTACTS_CSV)\n"
        "row = {'contact_id': %r, 'date': '2026-09-20', 'direction': 'in',\n"
        "       'channel': 'message', 'scenario': '', 'summary': 'They replied (message)',\n"
        "       'full_text': 'Please send your resume to me directly.'}\n"
        "export.apply_history(threads, {'add': [row], 'fill': []}, contacts)\n"
        "st.save_threads(threads, st.THREADS_CSV)\n"
        % (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"), LARKSPUR))
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private")
    r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True,
                       encoding="utf-8", timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(os.path.join(folder(search, LARKSPUR), "draft.older.md"))
    assert not offered(search, LARKSPUR)


def test_an_older_gap_filled_in_the_log_leaves_the_draft_alone(search):
    _draft_reply(search)
    code, out = tool(search, "network/state.py", "received", LARKSPUR, "--text-file",
                     text_file(search, "old.txt", "Hi Morgan, thanks for connecting, speak soon."),
                     "--date", "2026-09-11", "--today", "2026-10-25")
    assert code == 0, out
    assert os.path.exists(os.path.join(folder(search, LARKSPUR), "draft.md"))
    assert offered(search, LARKSPUR)


# ------------------------------------------------------------------ a kind close


def _their_close(search, words):
    code, out = tool(search, "network/state.py", "received", LARKSPUR, "--text-file",
                     text_file(search, "close.txt", words), "--date", "2026-10-24",
                     "--today", "2026-10-24")
    assert code == 0, out


def test_a_thank_you_to_keep_you_in_mind_starts_no_chase(search):
    _their_close(search, "Hi Morgan, nothing open on my team right now, but I'll keep you "
                         "in mind if anything comes up.")
    code, out = tool(search, "network/state.py", "message", LARKSPUR, "--text-file",
                     text_file(search, "thanks.txt", "Thanks so much!"),
                     "--date", "2026-10-25", "--today", "2026-10-25")
    assert code == 0, out
    row = contact(search, LARKSPUR)
    assert row["next_action_due"] == "", row
    assert row["next_action"].startswith("Nothing owed (2026-10-25)"), row
    assert "Follow up" not in row["next_action"]
    # Weeks later, still nothing is owed them.
    code, out = tool(search, "network/state.py", "--today", "2026-12-01")
    assert code == 0, out
    assert "Juno Castellan (Larkspur Retail)" not in out, out


def test_a_thank_you_that_asks_something_still_waits_for_an_answer(search):
    _their_close(search, "Hi Morgan, nothing open on my team right now, but I'll keep you "
                         "in mind if anything comes up.")
    code, out = tool(search, "network/state.py", "message", LARKSPUR, "--text-file",
                     text_file(search, "ask.txt", "Thanks so much! Is there anyone else in "
                                                  "the team you would suggest I speak to?"),
                     "--date", "2026-10-25", "--today", "2026-10-25")
    assert code == 0, out
    row = contact(search, LARKSPUR)
    assert row["next_action_due"] and not row["next_action"].startswith("Nothing owed"), row
