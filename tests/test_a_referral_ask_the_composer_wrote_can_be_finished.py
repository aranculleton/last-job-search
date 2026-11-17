"""A referral ask the app's own composer wrote is finished by `reply.py finish`, by one limit.

`compose.referral_ask()` allowed 90 words (`KIND_LIMITS["referral_ask"]`), while `reply.py
finish` checked the same message as a follow-up whenever the person's own message was the
last in the thread, as it is after "Thanks, I'll let you know when one comes up": 280
characters. The composer's ask with its link ran to about 380, so a referral ask the app
itself built could never be saved as the contact's draft without being cut by hand
(issue 315). Now finish checks a referral ask as one, with the kind's own limit, the
composer's: from the page's work (`args.kind: referral_ask`), from `--referral-ask`, or from
the ask's own shape (the posting's link alone on its last line, after the ask). And the
default close is shorter, so the usual ask is short as well.

Ana and her offer are tests/test_a_follow_up_follows_the_last_message.py's, in a search of
its own (tests/app_state.py). Every person and employer is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import compose  # noqa: E402
import schema  # noqa: E402
from test_a_follow_up_follows_the_last_message import ANA, CID, THREAD  # noqa: E402
from test_a_reply_takes_two_commands import put, run, write  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402

DAY = "2026-09-04"
ROLE = "Senior Pricing and Underwriting Analytics Analyst role at Kestrel Mutual"
LINK = ("https://jobs.example/kestrel-mutual/careers/manchester/"
        "senior-pricing-and-underwriting-analytics-analyst-20260901")
LINE = ("The Senior Pricing and Underwriting Analytics Analyst role at Kestrel Mutual is the "
        "pricing work we talked about, in your team's city")
CONTEXT = "following up on my note from August: the role you offered to refer me for has opened"
COMPOSE = ("import sys\n"
           "sys.path[:0] = [%r, %r]\n"
           "import compose\n"
           "sys.stdout.write(compose.referral_ask('Ana Rook', %r, %r, %r, thread=%r, line=%r))"
           % (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
              CONTEXT, ROLE, LINK, CID, LINE))


@pytest.fixture
def search(tmp_path):
    """The invented search, with Ana: she offered to refer the person a year ago, and the
    person's own note of August is the last message, unanswered."""
    s = Search(str(tmp_path))
    for name, rows in (("network_contacts.csv", [ANA]), ("network_threads.csv", THREAD)):
        path = os.path.join(s.state, name)
        with open(path, encoding="utf-8") as fh:
            head = next(csv.reader(fh))
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=head, extrasaction="ignore")
            for r in rows:
                w.writerow({c: r.get(c, "") for c in head})
    s.tmp = tmp_path
    return s


def _ask(search) -> str:
    code, out = run(search, "-c", COMPOSE)
    assert code == 0, out
    return out


def _draft(search) -> str:
    with open(os.path.join(search.state, "documents", "network", CID, "draft.md"),
              encoding="utf-8") as fh:
        return fh.read()


def test_the_composers_referral_ask_is_finished_and_saved(search):
    ask = _ask(search)
    # Longer than a follow-up may be, inside the referral ask's own limit.
    assert len(ask) > schema.LIMITS["nudge_chars"], len(ask)
    assert len(ask.split()) <= compose.KIND_LIMITS["referral_ask"]["words"][1]
    code, out = run(search, "tools/network/reply.py", "finish", CID, "--draft-file", "-",
                    "--today", DAY, given=ask)
    assert code == 0, out
    assert "too_long" not in out and "check: passed" in out, out
    assert _draft(search) == ask.strip() + "\n"


def test_the_finish_check_holds_a_referral_ask_to_the_composers_limit(search):
    high = compose.KIND_LIMITS["referral_ask"]["words"][1]
    long = ("Hi Ana, " + CONTEXT + ". " + LINE + ". "
            + " ".join(["It sits with the claims pricing models I have built for years."] * 8)
            + " Would you be comfortable referring me for it?\n\n" + LINK)
    assert len(long.split()) > high
    code, out = run(search, "tools/network/reply.py", "finish", CID, "--draft-file", "-",
                    "--referral-ask", "--today", DAY, given=long)
    assert code == 1 and f"limit {high}" in out, out
    assert f"limit {schema.LIMITS['nudge_chars']}" not in out, out


def test_the_pages_referral_ask_is_checked_as_one(search):
    # Written by hand without the link on its own line: the page's work says what it is.
    ask = _ask(search).replace("\n\n", " ")
    assert len(ask) > schema.LIMITS["nudge_chars"]
    wid = f"reply~{CID}~ref"
    put(search, "work", wid, {"kind": "reply", "title": "Draft the referral ask", "to": "cloud",
                              "args": {"contact": CID, "kind": "referral_ask", "role": ROLE,
                                       "url": LINK},
                              "status": "running", "stage": 1}, 3)
    code, out = run(search, "tools/network/reply.py", "finish", CID, "--draft-file",
                    write(search, "ask.txt", ask), "--work", wid, "--dump", search.dump,
                    "--kind", "cloud", "--now", NOW, "--today", DAY)
    assert code == 0, out
    assert "too_long" not in out, out
    got = json.loads(out[out.index("{"):])
    assert got["batches"], got


def test_the_default_close_is_one_short_sentence_of_offer():
    close = compose.REFERRAL_CLOSE.replace("{noun}", compose.NOUN)
    assert "Would you be comfortable referring me for it?" in close
    assert "a couple of lines you can forward" not in close
    assert len(close) <= 110, len(close)
