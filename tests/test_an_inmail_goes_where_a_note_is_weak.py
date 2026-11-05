"""A people search spends an InMail by itself, only where a connection note is weak.

The maintainer, 2026-11-05: a discovery run drafted connection notes for everyone, and an
InMail only when asked in words. On a plan with credits the run now decides in code
(tools/network/inmail_pick.py): a recruiter or a hiring leader at a target employer whom a
request would reach badly gets an InMail, within the credits left less one kept back and at
most two a run; never on a free plan. The draft card says why and what it spends, and one
quiet control switches that person to a connection note (the credit freed) and back. Once a
week a To do card asks for the balance LinkedIn shows. Every person here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import inmail_pick  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

PELL = "kestrel_mutual_ansgar"


def _p(cid, title, **kw):
    return {"contact_id": cid, "title": title, "company": "Kestrel Mutual", "target": True,
            "linkedin_url": "https://www.linkedin.com/in/example-person-" + cid.replace("_", "-"),
            "status": "not_contacted", **kw}


SASHA = _p("sasha", "Talent Acquisition Partner")              # a recruiter
ROBIN = _p("robin", "Data Analyst")                             # a peer
WREN = _p("wren", "Head of Claims Analytics")                   # a hiring leader


def test_a_free_plan_never_spends_an_inmail():
    assert inmail_pick.choose([SASHA, WREN], left=5, plan="free") == []
    assert not inmail_pick.plan_has_credits("free")


def test_premium_picks_the_recruiter_and_never_the_peer():
    got = inmail_pick.choose([ROBIN, SASHA], left=5, plan="premium")
    assert [g["contact_id"] for g in got] == ["sasha"]
    assert got[0]["why"] == "a recruiter at a target employer, and a request would wait"
    # A peer is a connection note whatever reaches them badly.
    assert inmail_pick.worth(ROBIN, {"connect": "missing", "degree": "3rd"}) == ""
    # Off the target list, a recruiter is a connection note too.
    assert inmail_pick.worth(dict(SASHA, target=False)) == ""


def test_a_strong_way_in_keeps_the_connection_note():
    # Already connected, a warm route, someone they both know, a request still pending.
    assert inmail_pick.worth(dict(SASHA, first_degree=True)) == ""
    assert inmail_pick.worth(dict(SASHA, route="alumni_school")) == ""
    assert inmail_pick.worth(SASHA, {"mutuals": ["Juno Castellan"]}) == ""
    assert inmail_pick.worth(SASHA, {"reach": "pending"}) == ""
    # No Connect on their page, or a request that sat three weeks: said as the reason.
    assert inmail_pick.worth(WREN, {"connect": "missing"}).endswith("their page offers no Connect")
    waited = dict(WREN, status="awaiting_reply", request_waiting_days=25)
    assert inmail_pick.worth(waited) == ("a hiring leader at a target employer, and your "
                                         "request has waited 25 days")


def test_the_budget_the_reserve_and_the_run_limit_hold():
    three = [SASHA, WREN, dict(SASHA, contact_id="sasha2")]
    # 2 left, 1 kept back: one InMail.
    assert len(inmail_pick.choose(three, left=2, plan="premium")) == 1
    # 1 left is the reserve itself: none.
    assert inmail_pick.choose(three, left=1, plan="premium") == []
    # InMails already drafted and waiting count against what is left.
    assert inmail_pick.choose(three, left=3, queued=2, plan="premium") == []
    # Plenty left: still at most two a run.
    assert len(inmail_pick.choose(three, left=15, plan="premium")) == inmail_pick.PER_RUN == 2


def test_the_card_says_why_and_what_it_spends():
    assert inmail_pick.card_line("a recruiter at a target employer, and a request would wait") \
        == "InMail (suggested): a recruiter at a target employer, and a request would wait"
    assert inmail_pick.credit_line(4) == "uses 1 of your 4 InMails"
    assert inmail_pick.credit_line(1) == "uses 1 of your 1 InMail"


# ------------------------------------------------------------------ on the page


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


INMAIL = ("Subject: Data analyst, ex-Larkspur Retail\n\nHi Pell, hope you're well. "
          + "I build forecasts for operations teams in Manchester. " * 8
          + "How is the claims analytics team set up?\n")


def _as_inmail(search):
    """Pell's draft made an InMail the run chose, the note kept beside it."""
    folder = os.path.join(search.state, "documents", "network", PELL)
    with open(os.path.join(folder, "draft.md"), encoding="utf-8") as fh:
        note = fh.read()
    with open(os.path.join(folder, "draft.md"), "w", encoding="utf-8") as fh:
        fh.write(INMAIL)
    with open(os.path.join(folder, "inmail.json"), "w", encoding="utf-8") as fh:
        json.dump({"why": "a hiring leader at a target employer, and a request would wait",
                   "on": "2026-10-25", "active": "inmail", "other": note,
                   "other_channel": "linkedin"}, fh)
    _set_channel(search, "inmail")
    return note


def _set_channel(search, channel):
    path = os.path.join(search.state, "network_contacts.csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["contact_id"] == PELL:
            r["channel"] = channel
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _channel(search):
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == PELL)["channel"]


def _draft(search):
    with open(os.path.join(search.state, "documents", "network", PELL, "draft.md"),
              encoding="utf-8") as fh:
        return fh.read()


def test_the_switch_goes_both_ways_and_frees_the_credit(search):
    note = _as_inmail(search)
    m = search.item(f"msg-{PELL}")
    assert m["channel"] == "inmail" and m["subject"] == "Data analyst, ex-Larkspur Retail"
    assert m["inmail"]["line"] == ("InMail (suggested): a hiring leader at a target employer, "
                                   "and a request would wait")
    assert m["inmail"]["credit"].startswith("uses 1 of your ")
    assert m["inmail"]["switch"] == {"to": "connection",
                                     "label": "Write a connection note instead"}

    aid = search.act("msg.channel", f"msg-{PELL}", value={"to": "connection"})
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    assert _draft(search) == note and _channel(search) == "linkedin"
    back = search.item(f"msg-{PELL}")
    assert back["channel"] == "linkedin_note" and not back["subject"]
    assert back["inmail"]["switch"] == {"to": "inmail", "label": "Send an InMail instead"}
    assert search.receipt(aid)["undo"]["action"] == "msg.channel"

    aid2 = search.act("msg.channel", f"msg-{PELL}", value={"to": "inmail"})
    got = search.apply()
    assert got["ok"] == [aid2], search.receipt(aid2)
    assert _draft(search) == INMAIL and _channel(search) == "inmail"


def test_no_switch_to_an_inmail_without_a_credit_to_spend(search):
    _as_inmail(search)
    search.act("msg.channel", f"msg-{PELL}", value={"to": "connection"})
    search.apply()
    search.written_back()
    rev = search.item(f"msg-{PELL}")["rev"]
    # LinkedIn shows none left: the InMail is not offered, and a tap is refused.
    with open(os.path.join(search.state, "documents", "network", ".inmail_credits.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"balance": 0, "date": "2026-10-25", "inmails": [], "refunds": []}, fh)
    assert search.item(f"msg-{PELL}")["inmail"] is None
    aid = search.act("msg.channel", f"msg-{PELL}", value={"to": "inmail"}, rev=rev)
    got = search.apply()
    assert aid not in got["ok"]
    assert "no InMails left" in search.receipt(aid)["note"]
    assert _channel(search) == "linkedin"


def test_the_weekly_balance_question_shows_once_and_not_again_for_a_week(search):
    ask = search.item(inmail_pick.ASK_ID)
    assert ask["title"] == "How many InMails does LinkedIn show you have left?"
    assert [o["action"] for o in ask["options"]] == ["inmail.credits"] * 2
    assert ask["options"][0]["input"] == "number"
    assert len(ask["steps"]["lines"]) == 3 and ask["steps"]["label"] == "Where do I find it?"

    aid = search.act("inmail.credits", inmail_pick.ASK_ID, value=4)
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    with open(os.path.join(search.state, "documents", "network", ".inmail_credits.json"),
              encoding="utf-8") as fh:
        assert json.load(fh)["balance"] == 4
    ids = [n["id"] for n in search.model()["needs_you"]]
    assert inmail_pick.ASK_ID not in ids
    # Six days on, still answered; a week on, asked again.
    six = json.loads(search.run("model", "--now", "2026-10-31T18:00:00Z"))["needs_you"]
    week = json.loads(search.run("model", "--now", "2026-11-01T18:00:00Z"))["needs_you"]
    assert inmail_pick.ASK_ID not in [n["id"] for n in six]
    assert inmail_pick.ASK_ID in [n["id"] for n in week]


def test_not_this_week_puts_the_question_off_and_keeps_the_balance(search):
    aid = search.act("inmail.credits", inmail_pick.ASK_ID, value=3)
    search.apply()
    search.written_back()
    week = json.loads(search.run("model", "--now", "2026-11-02T18:00:00Z"))
    ask = next(n for n in week["needs_you"] if n["id"] == inmail_pick.ASK_ID)
    assert aid
    later = search.act("inmail.credits", inmail_pick.ASK_ID, value="later", rev=ask["rev"])
    got = search.apply("--now", "2026-11-02T18:00:00Z")
    assert later in got["ok"], search.receipt(later)
    with open(os.path.join(search.state, "documents", "network", ".inmail_credits.json"),
              encoding="utf-8") as fh:
        kept = json.load(fh)
    assert kept["balance"] == 3 and kept["skipped"]


def test_a_free_plan_is_never_asked(search):
    path = os.path.join(search.profile, "networking.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace('LINKEDIN_PLAN = "premium"', 'LINKEDIN_PLAN = "free"'))
    assert inmail_pick.ASK_ID not in [n["id"] for n in search.model()["needs_you"]]


def _cli(search, *args, text=None):
    import subprocess
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state, LJS_COPY="private")
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", *args[:1]),
                           *args[1:]], env=env, input=text, capture_output=True,
                          encoding="utf-8", timeout=120)


def test_the_run_saves_the_inmail_only_after_their_window_is_checked_and_keeps_the_note(search):
    note = _draft(search)
    short = ("Subject: Data analyst, ex-Larkspur Retail\n\nHi Pell, hope you are well. I build "
             "forecasts for operations teams in Manchester, and I would like to hear how hiring "
             "for the claims analytics team works.\n\nThanks, Morgan\n")
    # Not checked yet: refused, and the note and its channel are as they were.
    got = _cli(search, "inmail_pick.py", "use", PELL, "-", "--card-only", text=short)
    assert got.returncode != 0 and "message window" in got.stdout
    assert _draft(search) == note and _channel(search) != "inmail"
    _cli(search, "reading.py", "message-check", PELL, "credits", "--by-hand")
    got = _cli(search, "inmail_pick.py", "use", PELL, "-", "--card-only", text=short)
    assert got.returncode == 0, got.stdout + got.stderr
    assert _channel(search) == "inmail" and "Subject: Data analyst" in _draft(search)
    got = _cli(search, "inmail_pick.py", "switch", PELL, "connection")
    assert got.returncode == 0 and _draft(search) == note and _channel(search) == "connection"


def test_an_inmail_asked_for_in_words_still_shows_as_one(search):
    """The way before: the person asks for an InMail, the chat drafts it on their row's
    channel. No run chose it, so no reason and no switch; its subject, body and credit show."""
    with open(os.path.join(search.state, "documents", "network", PELL, "draft.md"), "w",
              encoding="utf-8") as fh:
        fh.write(INMAIL)
    _set_channel(search, "inmail")
    m = search.item(f"msg-{PELL}")
    assert m["channel"] == "inmail" and m["subject"] and m["body"].startswith("Hi Pell")
    assert m["inmail"] == {"line": None, "credit": "uses 1 of your 5 InMails", "switch": None}
