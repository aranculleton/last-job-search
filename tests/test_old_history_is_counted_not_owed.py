"""Years of LinkedIn history are counted, not listed as owed today.

From a person's repo on 2026-10-23: the day their whole LinkedIn history came in, the due
list went from 24 overdue to 655. Every old conversation where the other side wrote last
read as a reply owed, every request never accepted as one to act on, and a resume asked
for in 2021 headed the list at 1,801 days late. Something owed more than
`state.OLD_OWED_DAYS` with nothing done is a thread that has ended: `state.owed` still
returns it, marked `old`, and /threads still shows it, but the due list counts it in one
line. Requests nobody accepted are one section, never people to write to. A date the person
put on a row keeps it live. Every name here is invented.
"""
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import open_actions  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 23)


def _c(cid, name, **kw):
    row = {k: "" for k in state.schema.CONTACT_COLUMNS}
    row.update({"contact_id": cid, "name": name, "company": "Kestrel Mutual"}, **kw)
    return row


def _m(cid, day, direction, text, **kw):
    return dict({"contact_id": cid, "date": day, "direction": direction, "channel": "message",
                 "scenario": "", "summary": text[:40], "full_text": text, "subject": ""}, **kw)


def _book():
    contacts = [_c("kestrel_ancient", "Rosalind Achterberg"), _c("kestrel_recent", "Tamsin Oyelaran"),
                _c("kestrel_dated", "Fenella Quarrie",
                   next_action="Answer once the Leeds role is posted", next_action_due="2026-10-20"),
                _c("kestrel_request", "Hal Okonedo"),
                _c("kestrel_resume_old", "Idris Corrie"), _c("kestrel_resume_new", "Rhian Pellow")]
    threads = [
        _m("kestrel_ancient", "2021-11-16", "out", "Hi Rosalind, good to meet you at the meetup."),
        _m("kestrel_ancient", "2021-11-17", "in", "Lovely to meet you too, let us keep in touch."),
        _m("kestrel_recent", "2026-10-18", "out", "Hi Tamsin, how is the pricing team set up?"),
        _m("kestrel_recent", "2026-10-20", "in", "Happy to talk, Thursday works."),
        _m("kestrel_dated", "2024-03-01", "in", "Shall we talk when the Leeds role is posted?"),
        dict(_m("kestrel_request", "2026-09-20", "out", ""), channel="connection",
             scenario="connection_request", summary="request, no note"),
        _m("kestrel_resume_old", "2021-06-01", "in", "Could you send me your resume?"),
        _m("kestrel_resume_new", "2026-10-15", "in", "Could you send me your resume?"),
    ]
    return contacts, threads


def test_owed_marks_what_has_waited_too_long_and_keeps_it():
    contacts, threads = _book()
    got = {i["contact_id"]: i for i in state.owed(contacts, threads, TODAY)}
    assert got["kestrel_ancient"]["kind"] == "reply" and got["kestrel_ancient"]["old"]
    assert not got["kestrel_recent"]["old"]
    assert not got["kestrel_dated"]["old"]          # the person's own date keeps it live
    assert got["kestrel_request"]["kind"] == "request_pending"
    assert not got["kestrel_request"]["old"]        # due 2026-10-11, twelve days ago


def test_the_due_list_counts_old_history_and_lists_what_is_live():
    contacts, threads = _book()
    out = open_actions.render_due(open_actions.due_items(contacts, threads, [], TODAY),
                                  TODAY.isoformat())
    head = out.splitlines()[0]
    assert head.startswith("2026-10-23: 3 overdue, 0 due today, 0 blocked by holds, 1 requests to "
                           f"withdraw, 2 owed over {state.OLD_OWED_DAYS} days set aside "
                           "(3 replies owed,"), head
    overdue = out.split("OVERDUE", 1)[1].split("\n\n", 1)[0]
    for live in ("Tamsin Oyelaran", "Fenella Quarrie", "Rhian Pellow"):
        assert live in overdue, live
    for gone in ("Rosalind Achterberg", "Idris Corrie", "Hal Okonedo"):
        assert gone not in overdue, gone
    asks = out.split("REQUESTS TO WITHDRAW (1)", 1)[1].split("\n\n", 1)[0]
    assert "state.py withdraw <contact_id>" in asks and "--all-due" in asks
    assert "Hal Okonedo" in asks
    assert "sent 2026-09-20" in asks
    assert f"SET ASIDE (2): owed more than {state.OLD_OWED_DAYS} days with nothing done" in out
    assert "Rosalind Achterberg" not in out and "Idris Corrie" not in out


def test_a_follow_up_date_the_app_wrote_is_not_the_persons_own():
    contacts = [_c("kestrel_waiting", "Corwin Haldane", status="awaiting_reply",
                   next_action="Follow up if no reply (1 of 2 sent; your rule: 14 days, at most "
                               "2 with no reply)", next_action_due="2026-08-15")]
    threads = [_m("kestrel_waiting", "2026-08-01", "out", "Hi Corwin, how is the team set up?")]
    assert not state.dated_by_person(contacts[0], threads)
    (item,) = state.owed(contacts, threads, TODAY)
    assert item["old"]


def test_nothing_old_and_no_requests_leaves_the_first_line_as_it_was():
    contacts, threads = _book()
    keep = {"kestrel_recent"}
    out = open_actions.render_due(
        open_actions.due_items([c for c in contacts if c["contact_id"] in keep],
                               [t for t in threads if t["contact_id"] in keep], [], TODAY),
        TODAY.isoformat())
    assert out.splitlines()[0] == ("2026-10-23: 1 overdue, 0 due today, 0 blocked by holds "
                                   "(1 replies owed, 0 first messages queued, "
                                   "0 application follow-ups with no recipient)")
    assert "REQUESTS TO WITHDRAW" not in out and "SET ASIDE" not in out


def test_threads_still_lists_an_old_one_and_says_why_the_brief_does_not(tmp_path, capsys):
    contacts, threads = _book()
    c, t = str(tmp_path / "c.csv"), str(tmp_path / "t.csv")
    state.save_contacts(contacts, c)
    state.save_threads(threads, t)
    state.main(["--contacts", c, "--threads", t, "--tracker", str(tmp_path / "none.csv"),
                "--today", TODAY.isoformat()])
    line = next(ln for ln in capsys.readouterr().out.splitlines() if "Rosalind Achterberg" in ln)
    assert f"owed over {state.OLD_OWED_DAYS} days" in line


def test_a_thread_that_ended_long_ago_is_not_dated_and_an_app_date_on_one_is_set_aside():
    # Two messages unanswered in 2021: the app's own "close it" date on it is history, and
    # writing follow-up dates leaves such a thread alone rather than dating it 2021.
    contacts = [_c("kestrel_ended", "Corwin Haldane", status="awaiting_reply")]
    threads = [_m("kestrel_ended", "2021-03-01", "out", "Hi Corwin, how is the team set up?"),
               _m("kestrel_ended", "2021-03-12", "out", "Hi Corwin, one more thought on it.",
                  scenario="nudge")]
    assert state.write_follow_ups(contacts, threads, TODAY) == []
    assert contacts[0]["next_action_due"] == ""
    # What the app would have written on it in 2021: its own words and its own date.
    contacts[0]["next_action"], contacts[0]["next_action_due"] = \
        state.follow_up_plan(contacts[0], threads)
    (item,) = state.owed(contacts, threads, TODAY)
    assert item["kind"] == "action_due" and item["old"]
    out = open_actions.render_due(open_actions.due_items(contacts, threads, [], TODAY),
                                  TODAY.isoformat())
    assert "Corwin Haldane" not in out and "1 owed over" in out.splitlines()[0]


def _request(cid, day):
    return dict(_m(cid, day, "out", ""), channel="connection", scenario="connection_request",
                summary="request, no note")


def test_a_request_is_never_set_aside_and_all_due_records_only_what_is_listed(tmp_path):
    # Found in review: --all-due recorded a request the list had set aside and one the
    # person had put on hold, closing both while the invitations still stood on LinkedIn.
    contacts = [_c("kestrel_recent_ask", "Hal Okonedo"), _c("kestrel_old_ask", "Idris Corrie"),
                _c("kestrel_held_ask", "Rhian Pellow",
                   next_action="HOLD until 2026-12-01: waiting on an introduction",
                   next_action_due="2026-10-01")]
    threads = [_request("kestrel_recent_ask", "2026-09-20"),
               _request("kestrel_old_ask", "2026-07-01"),
               _request("kestrel_held_ask", "2026-09-01")]
    got = {i["contact_id"]: i for i in state.owed(contacts, threads, TODAY)}
    assert not got["kestrel_old_ask"]["old"]       # still counts against LinkedIn's limit
    out = open_actions.render_due(open_actions.due_items(contacts, threads, [], TODAY),
                                  TODAY.isoformat())
    asks = out.split("REQUESTS TO WITHDRAW (2)", 1)[1].split("\n\n", 1)[0]
    assert "Hal Okonedo" in asks and "Idris Corrie" in asks and "Rhian Pellow" not in asks
    assert "SET ASIDE" not in out
    c, t = str(tmp_path / "c.csv"), str(tmp_path / "t.csv")
    state.save_contacts(contacts, c)
    state.save_threads(threads, t)
    assert state.main(["withdraw", "--all-due", "--contacts", c, "--threads", t,
                       "--today", TODAY.isoformat()]) == 0
    closed = {r["contact_id"] for r in state.load_contacts(c) if r["status"] == "closed"}
    assert closed == {"kestrel_recent_ask", "kestrel_old_ask"}


def test_a_date_the_person_puts_on_brings_an_old_one_back():
    # Found in review: a date beside no words (state.py set <id> --due <date>), or beside the
    # app's own words on a day the app would never have written, is the person's.
    contacts, threads = _book()
    ancient = contacts[0]
    ancient["next_action_due"] = "2026-10-25"
    assert state.dated_by_person(ancient)
    assert not next(i for i in state.owed(contacts, threads, TODAY)
                    if i["contact_id"] == "kestrel_ancient")["old"]
    waiting = _c("kestrel_waiting", "Corwin Haldane", status="awaiting_reply",
                 next_action="One nudge if no reply", next_action_due="2026-10-25")
    log = [_m("kestrel_waiting", "2026-07-01", "out", "Hi Corwin, how is the team set up?")]
    assert state.dated_by_person(waiting, log)
    app_date = state.add_business_days(datetime.date(2026, 7, 1), 6).isoformat()
    assert not state.dated_by_person(dict(waiting, next_action_due=app_date), log)


def test_a_resume_made_for_an_old_ask_is_something_done(tmp_path):
    # Found in review: a resume made yesterday for someone who asked in July was set aside
    # as owed with nothing done.
    contacts = [_c("kestrel_resume_old", "Idris Corrie")]
    threads = [_m("kestrel_resume_old", "2026-07-01", "in", "Could you send me your resume?")]
    tracker = [{"date": "2026-10-22", "company": "Kestrel Mutual", "role": "Pricing Analyst",
                "status": "drafted", "notes": "made for Idris Corrie (kestrel_resume_old)",
                "cv_file": "cv/Morgan_Ellis_Resume_KM.tex"}]
    items = open_actions.due_items(contacts, threads, tracker, TODAY)
    owed_cv = [i for i in items if i["contact_id"] == "kestrel_resume_old"]
    assert owed_cv and not any(i.get("old") for i in owed_cv)
    assert f"{state.noun()} owed to Idris Corrie" in " ".join(i["what"] for i in owed_cv)
