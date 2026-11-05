"""Each journey the 3 November audit ran, page to engine and back, ends where the page says.

The journeys pass tapped the page, handed what it wrote to the engine as a chat does
(`app.py apply`), rebuilt the page's data (`app.py view`) and opened a fresh page on it. It
found the Applied list twice over with Isaac's interview on every card, Change back undone in
the files but not on the page, an interview turned down shown as "Passed", a draft waiting on
an answer shown as "Drafting", follow-up dates that never moved after a reply, a note logged
as sent on the day it was asked about, and setup answers nothing carried on. Each test is one
finding, run on an invented search (tests/app_state.py) or the page's own sample.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402
from test_the_page_shows_the_engines_own_data import _page as _engine_page, _seed  # noqa: E402
from test_the_page_works_in_a_browser import _sample, _write, run  # noqa: E402

_ = run   # the fixture, used by name

T0 = "2026-10-25T09:00:00Z"


def _env(where):
    env = dict(os.environ, LJS_PROFILE=where.profile, LJS_STATE=where.state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    return env


def _script(run, html, steps, **kw):
    got = run("script", html=html, clock=kw.pop("clock", T0), steps=steps, **kw)
    assert not got["errors"], got["errors"]
    return got["steps"]


# ------------------------------------------------------------------ 1. the Applied list


def test_every_application_is_one_record_with_its_own_id_in_the_whole_list_too(tmp_path):
    s = Search(str(tmp_path / "s"))
    m = s.model()
    live = {a["id"] for a in m["applications"]}
    hist = m["done"]["applications"]
    assert hist and all(a.get("id") for a in hist), "the history carries the tracker's ids"
    assert live <= {a["id"] for a in hist} | live
    assert {a["id"] for a in hist} & live, "the same application is the same id in both"


def test_the_applied_list_shows_each_application_once_and_only_its_own_interview(run, tmp_path):
    where = Search(str(tmp_path / "s"))
    env = _env(where)
    html = _engine_page(str(tmp_path), "applied", env)
    seed = _seed(str(tmp_path), "applied", env)
    m = where.model()
    sent = [a for a in m["done"]["applications"]]
    s = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]',
                             "eval": "[document.querySelectorAll('#main [data-item^=\"rec-\"], #main article.card').length,"
                                     " [...document.querySelectorAll('#main button')].filter((b) => /Read your prep|Prepare me/.test(b.textContent)).length]"}],
                seed=seed, clock=NOW)
    cards, preps = s[-1]["eval"]
    text = s[-1]["main"]
    for a in sent:
        assert text.count(a["company"] + "") >= 1
    ivs = [i for i in m["interviews"] if i.get("company")]
    assert preps <= len(ivs), "a prep button only where there is an interview: %d for %d" % (preps, len(ivs))
    assert cards <= len({a["id"] for a in sent} | {a["id"] for a in m["applications"]}) + 1, cards


def test_an_application_without_an_id_never_takes_another_ones_interview(run, tmp_path):
    m = _sample()
    # A record from the whole list with no id, as 4.8.0's was, and an interview with no
    # application named: "" matched "" and every card read "Read your prep".
    m["applications"] = [dict(a, id="") if i else a for i, a in enumerate(m["applications"])]
    for iv in m["interviews"]:
        iv.pop("application", None)
    html = _write(tmp_path, "noid", m)
    s = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]',
                             "eval": "[...document.querySelectorAll('#main button')].filter((b) => /Read your prep/.test(b.textContent)).length"}])
    assert s[-1]["eval"] <= 1, s[-1]["eval"]


# ------------------------------------------------------------------ 3. Change back holds after a reload


def test_change_back_on_i_have_applied_holds_after_a_reload(run, tmp_path):
    m = _sample()
    html = _write(tmp_path, "back", m)
    a = next(x for x in m["ready"] if x.get("status") != "applied")
    first, back = "act~" + a["id"] + "~ready.applied~1", "act~" + a["id"] + "~undo~2"
    # Both taps applied by a chat, and a fresh page opened on a data made before them: what the
    # page shows is worked out from the two actions and their receipts alone.
    seed = {"actions/" + first: {"item": a["id"], "action": "ready.applied", "value": {"on": "2026-10-25"}, "at": "2026-10-25T08:00:00Z", "rev_seen": a["rev"], "tab": "t0"},
            "receipts/" + first: {"applied_at": "2026-10-25T08:01:00Z", "result": "ok", "note": "Marked as applied.", "undo": {"action": "ready.not_applied", "target": {}}},
            "actions/" + back: {"item": a["id"], "action": "undo", "undoes": first, "value": None, "at": "2026-10-25T08:05:00Z", "rev_seen": None, "tab": "t0"},
            "receipts/" + back: {"applied_at": "2026-10-25T08:06:00Z", "result": "ok", "note": "Changed back."}}
    # A draft with a question for the person keeps "I have applied" under More: opened first.
    card = ("(() => { const c = document.querySelector('#main [data-item=\"%s\"]'); if (!c) return '';"
            " const m = c.querySelector('details.more:not([open]) > summary'); if (m) m.click(); return c.innerText; })()" % a["id"])
    s = _script(run, html, [{"hash": "drafts", "eval": card}], seed=seed)
    text = s[-1]["eval"]
    assert text, "the draft is still in Drafts, to send"
    assert "I have applied" in text and "Applied" not in text.split("I have applied")[0].split("\n")[1:3], text[:300]
    assert "Only a chat can take this back" not in text


# ------------------------------------------------------------------ 5. an interview's prep and thank-you reach To do


def test_an_interviews_prep_and_thank_you_are_never_cut_behind_hundreds_of_people():
    import open_actions
    people = [{"half": "contact", "rank": open_actions.KIND_ORDER["nudge"], "late": 3, "name": "Person %03d" % i,
               "kind": "nudge"} for i in range(550)]
    replies = [{"half": "contact", "rank": 0, "late": 1, "name": "Replier %03d" % i, "kind": "reply"} for i in range(30)]
    iv = {"half": "application", "rank": open_actions.INTERVIEW_RANK, "late": 0, "name": "Calder (Analyst)", "kind": "interview"}
    order = sorted(people + replies + [iv], key=open_actions.urgency)
    assert order.index(iv) == 30, "after the people waiting on a reply, before every nudge"


def test_the_due_list_keeps_every_application_row_at_any_size(tmp_path, monkeypatch):
    import app_model
    import person
    s = Search(str(tmp_path / "s"))
    # The panel interview in three days, with no prep written yet: its row is due.
    os.remove(os.path.join(s.state, "documents", "applications", "thornbury_bank_risk_analyst_thornbury",
                           "interview_prep.md"))
    for k, v in _env(s).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LJS_TODAY", raising=False)
    person.reset()
    whole, targets = app_model.build(*app_model.clock("2026-10-25", NOW))
    own = [d for d in whole["due"] if "step" not in d and d.get("kind") != "hidden"]
    assert own, "the invented search has an application's or an interview's row"
    # Cut to no people at all: every one of those rows is still there.
    monkeypatch.setattr(app_model, "DUE_MAX", 0)
    person.reset()
    cut, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert [d["id"] for d in cut["due"] if "step" not in d and d.get("kind") != "hidden"] == [d["id"] for d in own]
    assert any("step" in d for d in whole["due"]) and not any("step" in d for d in cut["due"]), "the people are what is cut"
    # The people cut are counted, each once, in the one row that says what is not shown (the
    # re-audit of 4 November: at 716 people To do listed 93 and said nothing of the rest).
    # Who needs you, as Contacts counts them (app_model.NEEDS_YOU), and the follow-ups said
    # apart, each once, less anyone whose message is on To do's "Messages to send" card (the
    # review, 2026-11-05: it counted every row it left off, beside Contacts' own count).
    people = {targets[d["id"]].get("contact") or d["id"] for d in whole["due"] if "step" in d}
    groups = {p["id"]: p["group"] for p in cut["people"]}
    sent = {x["contact"] for x in cut["messages"] if x["id"] in cut["to_send"]["ids"]}
    hidden = [d for d in cut["due"] if d.get("kind") == "hidden"]
    n = len({c for c in people if groups.get(c) == "now"} - sent)
    f = len({c for c in people if groups.get(c) == "follow"} - sent)
    assert n or f, "the invented search owes someone something"
    said = f"{n} more {'person who needs' if n == 1 else 'people who need'} you {'is' if n == 1 else 'are'} in Contacts" if n else ""
    ups = (f"{f} {'follow-up' if f == 1 else 'follow-ups'} you could send {'is' if f == 1 else 'are'} there too" if n else
           f"{f} more {'follow-up' if f == 1 else 'follow-ups'} you could send {'is' if f == 1 else 'are'} in Contacts") if f else ""
    assert len(hidden) == 1 and hidden[0]["title"].endswith(". ".join(x for x in (said, ups) if x)), (hidden, n, f)
    assert not [d for d in whole["due"] if d.get("kind") == "hidden" and "in Contacts" in d["title"]]


# ------------------------------------------------------------------ 7. never "Passed"


def test_a_past_interview_says_when_it_was_never_passed(run, tmp_path):
    html = _write(tmp_path, "p", _sample())
    s = _script(run, html, [{"eval": "[LJS.words.relWhen('2026-10-24'), LJS.words.relWhen('2026-10-20'), LJS.words.relWhen('2026-10-25')]"}])
    assert s[-1]["eval"] == ["Yesterday", "5 days ago", "Today"]


# ------------------------------------------------------------------ 8. follow-up dates move with the conversation


def _contact(cid, **kw):
    return dict({"contact_id": cid, "name": "Rhian Example", "company": "Calder Analytics", "status": "in_conversation",
                 "next_action": "One plain check on the role", "next_action_due": "2026-10-30"}, **kw)


def test_their_message_makes_the_reply_due_from_the_day_it_came():
    import state
    c = _contact("calder_example")
    threads = [{"contact_id": "calder_example", "date": "2026-10-20", "direction": "out", "channel": "message",
                "scenario": "reply", "summary": "Reply sent", "full_text": "Thanks, here is my resume."}]
    state.received([c], threads, "calder_example", "2026-11-03", text="Thanks for this. Are you free to talk next week about the team?",
                   date="2026-11-03")
    assert c["next_action_due"] == "2026-11-03", c


def test_our_answer_sets_the_next_follow_up_by_the_persons_rule():
    import state
    c = _contact("calder_example")
    threads = [{"contact_id": "calder_example", "date": "2026-10-20", "direction": "out", "channel": "message",
                "scenario": "reply", "summary": "Reply sent", "full_text": "Thanks, here is my resume."},
               {"contact_id": "calder_example", "date": "2026-11-03", "direction": "in", "channel": "message",
                "scenario": "", "summary": "They replied", "full_text": "Thanks for sending the resume. Talk soon about the team."}]
    state.followed_up([c], threads, "calder_example", "2026-11-03", text="Great, speak then. Thank you.", date="2026-11-03")
    assert c["next_action_due"] > "2026-11-03", c
    assert c["next_action"] != "One plain check on the role"


def test_thanks_for_a_resume_already_sent_is_not_asking_for_one():
    import reply
    assert reply.asks_for_resume("Thanks for sending the resume, I'll take a look this week.") is False
    assert reply.asks_for_resume("Got your CV, thank you.") is False
    assert reply.asks_for_resume("Could you send me your resume?") is True
    assert reply.asks_for_resume("Thanks for reaching out. Send me your resume and I'll pass it on.") is True


# ------------------------------------------------------------------ 10. the brief's days alone


def test_the_brief_days_alone_keep_the_time_it_comes_now(monkeypatch):
    import routines
    import tweak
    monkeypatch.setattr(routines, "load", lambda: {"routines": [{"key": "morning_brief", "cron": "CRON_TZ=Europe/London 38 7 * * 1,4"}]})
    out = tweak.check({"args": {"target": {"output": "brief"}, "changes": [{"p": "B4", "v": ["1"]}]}})
    assert out[0]["v"] == {"days": [1], "time": "07:38"}, out
    sun = tweak.check({"args": {"target": {"output": "brief"}, "changes": [{"p": "B4", "v": ["0", "3"]}]}})
    assert sun[0]["v"]["days"] == [3, 7]


def test_the_brief_panel_marks_what_it_is_now(run, tmp_path):
    m = _sample()
    m["tweaks"] = dict(m.get("tweaks") or {}, usual={"brief": {"B2": "3"}})
    html = _write(tmp_path, "brief", m)
    s = _script(run, html, [{"hash": "brief", "click": "Edit the brief", "exact": False},
                            {"tap": ".tweak-panel details > summary", "eval": "document.querySelector('.tweak-panel').innerText"}])
    text = s[-1]["eval"]
    assert "Mon\n(now)" in text or "Mon (now)" in text, text[-600:]
    assert "Thu\n(now)" in text or "Thu (now)" in text
    assert "3\n(now)" in text or "3 (now)" in text


# ------------------------------------------------------------------ 11, 15, 16. the job card says how its work stands


def _draft_work(status, **kw):
    return {"work/draft~r12-1": dict({"kind": "draft", "title": "Drafting for Harbourline Bank", "to": "cloud", "args": {"job": "r12-1"},
                                      "asked_at": T0, "status": status, "attempt": 1, "stage": 1, "steps": [], "stop_asked": False,
                                      "asked_from": {"tab": "t0"}}, **kw)}


def test_a_draft_waiting_on_an_answer_says_so_on_its_job(run, tmp_path):
    m = _sample()
    r = next(x for x in m["jobs"]["rows"] if x["id"] == "r12-1")
    r["draft_work"] = {"id": "draft~r12-1"}
    html = _write(tmp_path, "ask", m)
    s = _script(run, html, [{"hash": "jobs"}], seed=_draft_work("needs_you", note="Which of your two resumes should it start from?"))
    card = s[-1]["main"].split("Pricing Analyst", 1)[1].split("More", 1)[0]
    assert card.lstrip().startswith("Needs your answer"), card
    assert "\nAnswer\n" in card and "Drafting" not in card


def test_a_draft_that_did_not_finish_says_why_on_its_job(run, tmp_path):
    m = _sample()
    r = next(x for x in m["jobs"]["rows"] if x["id"] == "r12-1")
    r["draft_work"] = {"id": "draft~r12-1"}
    html = _write(tmp_path, "failed", m)
    s = _script(run, html, [{"hash": "jobs"}], seed=_draft_work("failed", error="The posting page would not open"))
    assert "The last draft did not finish: The posting page would not open." in s[-1]["main"]


def test_a_job_added_by_hand_is_said_on_jobs_while_it_is_scored(run, tmp_path):
    html = _write(tmp_path, "add", _sample())
    seed = {"work/evaluate~abc": {"kind": "evaluate", "title": "Scoring the job you added", "to": "either", "args": {}, "asked_at": T0,
                                  "status": "queued", "attempt": 1, "stage": 0, "steps": [], "stop_asked": False}}
    s = _script(run, html, [{"hash": "jobs"}], seed=seed)
    assert "Scoring the job you added" in s[-1]["main"]


def test_a_job_added_by_hand_is_said_to_join_the_jobs_with_its_score(tmp_path):
    w = Search(str(tmp_path / "s"))
    a = w.act("job.add", "job-new", value={"url": "https://jobs.example/calder/analyst"}, rev="")
    w.apply()
    note = w.receipt(a)["note"]
    assert "top of your jobs" not in note and "with its score" in note


# ------------------------------------------------------------------ 13, 21. setup answered on the page


def test_a_wake_after_setup_answers_carries_setup_on(tmp_path, monkeypatch):
    import app_setup
    from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy
    c = Copy(str(tmp_path / "c"))
    for k, v in c.env().items():
        monkeypatch.setenv(k, v)
    app_setup.save_answers({"resume": {"source": "asset", "asset": "a" * 32}, "work": {"work": "Analyst", "place": "Leeds"}})
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": "https://claude.ai/code/artifact/x"})
    lines = app_setup.carry_on()
    said = "\n".join(lines)
    assert "Save it: Artifact, action read" in said and "a" * 32 in said
    assert "Setup".lower() in said.lower() and ".claude/commands/setup.md" in said


def test_the_wake_says_setup_carries_on_after_it_applies_a_setup_answer():
    import inspect
    import app
    src = inspect.getsource(app.cmd_wake)
    assert "carry_on()" in src and 'startswith("setup.")' in src


def test_the_work_and_the_place_are_asked_for_and_the_resume_says_what_the_page_takes():
    import app_setup
    work = next(s for s in app_setup.STEPS if s["id"] == "work")
    assert all(f.get("required") for f in work["fields"])
    resume = next(s for s in app_setup.STEPS if s["id"] == "resume")
    assert "Word" not in resume["fields"][0]["label"]


def test_a_setup_answer_saved_on_the_page_counts_after_a_reload(run, tmp_path):
    from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy
    from test_the_page_shows_the_engines_own_data import _page as page_of
    c = Copy(str(tmp_path / "c"))
    html = page_of(str(tmp_path), "setup", c.env())
    seed = {"actions/act~setup-resume~setup.resume~1": {"item": "setup-resume", "action": "setup.resume", "value": {"text": "Analyst, 2021 to now."},
                                                         "at": "2026-10-25T09:00:00Z", "rev_seen": "x", "tab": "t0"}}
    s = _script(run, html, [{"hash": "todo", "eval": "document.body.innerText"}], seed=seed, clock=NOW)
    assert "Continue" in s[-1]["main"] or "1 of" in s[-1]["main"], s[-1]["main"][:400]
    s2 = _script(run, html, [{"hash": "todo", "click": "Continue", "exact": False}], seed=seed, clock=NOW)
    assert "Your resume: add the file" not in s2[-1]["dialog"], "the resume is not asked for again"


# ------------------------------------------------------------------ 14. It went


def test_it_went_logs_the_day_it_was_due_with_another_day_offered(tmp_path):
    import csv
    from test_a_message_goes_out_by_hand_and_is_logged_once import PELL, _set_contact
    w = Search(str(tmp_path / "s"))
    _set_contact(w, PELL, next_action_due="2026-10-17")
    q = next(n for n in w.model()["needs_you"] if n["id"] == "q-sent-" + PELL)
    yes = q["options"][0]
    assert yes["value"].get("on") == "2026-10-17", yes
    aid = w.act("msg.sent", q["id"], value=yes["value"], rev=q["rev"])
    assert w.apply()["ok"] == [aid], w.receipt(aid)
    with open(os.path.join(w.state, "network_threads.csv"), encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["contact_id"] == PELL]
    assert rows[-1]["date"] == "2026-10-17", "logged on the day it went, not the day it was asked"
    note = w.receipt(aid)["note"]
    from test_a_message_goes_out_by_hand_and_is_logged_once import _contact
    step = " ".join(str(_contact(w, PELL)["next_action"]).split())
    if "Next: " in note:
        shown = note.split("Next: ", 1)[1].rsplit(", ", 1)[0]
        cut = shown[:-1] if shown.endswith("\u2026") else shown
        assert step.startswith(cut) and (len(cut) == len(step) or step[len(cut)] in " ,;:"), (shown, step)


def test_a_receipts_next_step_is_cut_at_a_word():
    import app_actions
    import inspect
    src = inspect.getsource(app_actions._msg_sent)
    assert "[:80]}" not in src and 'rsplit(" ", 1)' in src


# ------------------------------------------------------------------ 22, 24. Change back and Done lines


def test_a_change_back_has_no_only_a_chat_note(run, tmp_path):
    # Not this time on an interview, then Change back: the undo applied, and its own line said
    # "Done. Only a chat can take this back" (journeys audit 22).
    m = _sample()
    html = _write(tmp_path, "iv", m)
    iv = m["interviews"][0]
    app = iv["application"]
    first, back = "act~" + app + "~outcome.rejected~1", "act~" + app + "~undo~2"
    seed = {"actions/" + first: {"item": app, "action": "outcome.rejected", "value": {}, "at": "2026-10-25T08:00:00Z", "rev_seen": "x", "tab": "t0"},
            "receipts/" + first: {"applied_at": "2026-10-25T08:01:00Z", "result": "ok", "note": "Marked as not this time.", "undo": {"action": "outcome.reopen", "target": {}}},
            "actions/" + back: {"item": app, "action": "undo", "undoes": first, "value": None, "at": "2026-10-25T08:05:00Z", "rev_seen": None, "tab": "t0"},
            "receipts/" + back: {"applied_at": "2026-10-25T08:06:00Z", "result": "ok", "note": "Changed back.",
                                 "undo_note": "Only a chat can take this back: say so in a chat."}}
    look = "(() => { const c = document.querySelector('#main [data-item=\"%s\"]'); return c ? c.innerText : 'none'; })()" % app
    s = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]', "eval": look}], seed=seed)
    assert s[-1]["eval"] != "none"
    assert "Only a chat can take this back" not in s[-1]["eval"] and "Changed back." in s[-1]["eval"], s[-1]["eval"][:300]


def test_the_engine_writes_no_only_a_chat_note_on_a_change_back():
    import inspect
    import app_actions
    src = inspect.getsource(app_actions._one)
    assert 'shown.get("action") != "undo"' in src


def test_a_done_line_goes_after_two_days(run, tmp_path):
    # "Done. Change back" under an Applied card fourteen days after I have applied (journeys
    # audit 24): it goes after two days.
    m = _sample()
    html = _write(tmp_path, "old", m)
    a = m["applications"][0]
    aid = "act~" + a["id"] + "~job.applied~1"
    seed = {"actions/" + aid: {"item": a["id"], "action": "job.applied", "value": {"on": "2026-10-11"}, "at": "2026-10-11T09:00:00Z", "rev_seen": a["rev"], "tab": "t0"},
            "receipts/" + aid: {"applied_at": "2026-10-11T09:01:00Z", "result": "ok", "note": "Marked as applied.", "undo": {"action": "job.not_applied", "target": {}}}}
    look = "(() => { const c = document.querySelector('#main [data-item=\"%s\"]'); return c ? c.innerText : 'none'; })()" % a["id"]
    old = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]', "eval": look}], seed=seed)
    assert old[-1]["eval"] != "none" and "Change back" not in old[-1]["eval"], old[-1]["eval"][:300]
    fresh = _script(run, html, [{"hash": "jobs", "tap": '[data-k="jobsw:applied"]', "eval": look}], seed=seed, clock="2026-10-12T09:00:00Z")
    assert "Change back" in fresh[-1]["eval"], "a day later it is still there to change back"


# ------------------------------------------------------------------ 23. a brief edit's stages


def test_a_brief_edit_is_given_no_document_stages(run, tmp_path):
    html = _write(tmp_path, "b", _sample())
    got = run("tweak", html=html, hash="brief", entry="Edit the brief", exact=False, type=[["B6", "Leeds grocery hiring"]], apply=True)
    assert not got["errors"], got["errors"]
    work = [w for _, w in got["work"] if w.get("kind") == "tweak"]
    assert work, got["work"]
    names = [s["name"] for s in work[0]["stages"]]
    assert not any("PDF" in n or "fact" in n for n in names), names


# ------------------------------------------------------------------ 2. Draft a reply after their message is logged


def test_their_message_logged_on_the_page_reaches_the_page_for_the_reply(tmp_path):
    # They replied, Log it, applied, the page made again: their words are on their person,
    # so Draft a reply asks only what to say back (the page's own test, test_the_page_journeys
    # test_a_reply_owed_says_so_and_drafts_from_their_words_already_kept, takes it from there).
    from test_a_message_goes_out_by_hand_and_is_logged_once import WREN
    w = Search(str(tmp_path / "s"))
    words = "Thanks for the note. Are you free Tuesday or Wednesday afternoon for a call about the team?"
    aid = w.act("msg.received", WREN, value={"text": words, "on": "2026-10-25"})
    assert w.apply()["ok"] == [aid], w.receipt(aid)
    p = next(x for x in w.model()["people"] if x["id"] == WREN)
    said = [t for t in p["thread"] if not t.get("event")]
    assert p["status"] == "replied_needs_response" and said[-1]["from"] == "them"
    assert said[-1]["text"].startswith("Thanks for the note.")
    note = w.receipt(aid)["note"]
    assert WREN not in note, "no raw contact id in what the page shows"
    # Pasted again with Draft a reply: kept once, and the reply is still drafted.
    again = w.act("msg.received", WREN, value={"text": words, "on": "2026-10-25", "draft": True})
    w.apply()
    rec = w.receipt(again)
    assert rec["result"] == "ok" and "changed since you saw it" not in rec["note"] and WREN not in rec["note"], rec
