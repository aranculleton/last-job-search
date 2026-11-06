"""A follow-up drafted and passed by its check is in the page's Messages, in the same step.

Seen on a person's page (2026-11-04): follow-ups and replies written in a chat and passed with
`followup_drafts.py check --pack` went only into the day's pack and the work item, while
Messages reads the draft waiting for each person (documents/network/<id>/draft.md). The chat
wrote each draft.md by hand to get them shown; To do kept offering to draft them again, and
the person queued nineteen a second time. `reply.py finish`, the command that does put a draft
where Messages shows it, refused every follow-up to someone who had never written back, as a
reply with nothing to reply to. Now the code that passes a draft puts it there: one draft
waiting per person, never a second store.

The example person's own contact book (profile.example/state), in the tests' own copy, and one
invented application added to it for the test.
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import app_model  # noqa: E402
import followup_drafts  # noqa: E402
import person  # noqa: E402
import reading  # noqa: E402
import reply  # noqa: E402

DAY = "2026-10-25"
NOW = "2026-10-25T09:00:00Z"
# The example's own: our note of 21 September, unanswered, a follow-up owed.
WREN = "fernhill_freight_halloway"
def _opens_on_our_note(text):
    """Opens on our own note by its month, in one of the openers a batch varies between
    (compose.FOLLOW_UP_OPENERS, 2026-11-06)."""
    import compose
    return any(text.startswith("Hi Wren, %s. " % o.format(word="note", when=" from September"))
               for o in compose.FOLLOW_UP_OPENERS)


TEXT = ("Hi Wren, following up on my note from September. What is your team working on at the "
        "moment, and what do you look for in people joining?")
APP_ROW = {"date": "2026-10-10", "company": "Quayside Foods", "sector": "Grocery",
           "role": "Demand Planner", "role_type": "data", "channel": "company site",
           "status": "applied", "contact_person": "Wren Castellan", "fit_rating": "70",
           "notes": "example row", "source": "https://example.com/jobs/9"}


@pytest.fixture
def clean():
    """Whatever this test drafts, packs or adds is taken away again: the state is shared by
    every test in this worker."""
    tracker = person.state("job_search_tracker.csv")
    kept = open(tracker, encoding="utf-8").read()
    folder = person.state("documents", "network")
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    try:
        yield
    finally:
        with open(tracker, "w", encoding="utf-8", newline="") as fh:
            fh.write(kept)
        if os.path.isdir(folder):
            for name in set(os.listdir(folder)) - before:
                p = os.path.join(folder, name)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


def _run(argv) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = followup_drafts.main(argv)
    return code, out.getvalue()


def _messages():
    model, _ = app_model.build(*app_model.clock(DAY, NOW), only={"messages", "due"})
    return model


def _waiting(cid) -> str:
    with open(reading.draft_path(cid), encoding="utf-8") as fh:
        return reading.note_body(fh.read()).strip()


def test_a_follow_up_passed_by_its_check_is_in_messages_in_the_same_step(clean, tmp_path):
    f = tmp_path / "drafts.json"
    f.write_text(json.dumps([{"id": WREN, "text": TEXT}]), encoding="utf-8")
    code, out = _run(["check", str(f), "--pack", "--today", DAY])
    assert code == 0 and "PASS " + WREN in out, out
    assert _waiting(WREN) == TEXT, "the draft waiting for them is the one that passed"
    model = _messages()
    msg = next((m for m in model["messages"] if m["contact"] == WREN), None)
    assert msg is not None and msg["body"] == TEXT and msg["type"] == "follow_up", model["messages"]
    # Their To do row is about the same person, so the page opens this draft from it.
    assert any(d.get("item") == WREN and d["kind"] in ("nudge", "follow_up") for d in model["due"]), model["due"]
    # A draft the check refuses is never put there.
    f.write_text(json.dumps([{"id": WREN, "text": "Hi Wren, just checking in on my last note."}]),
                 encoding="utf-8")
    code, _ = _run(["check", str(f), "--today", DAY])
    assert code == 1 and _waiting(WREN) == TEXT


def test_code_drafts_reach_messages_and_never_write_over_the_one_waiting(clean):
    code, _ = _run(["--pack", "--today", DAY])
    assert code == 0
    drafted = _waiting(WREN)
    assert _opens_on_our_note(drafted), drafted
    assert any(m["contact"] == WREN and m["body"] == drafted for m in _messages()["messages"])
    # The person changed it on the page: the next run checks theirs and keeps it.
    with open(reading.draft_path(WREN), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(TEXT + "\n")
    _run(["--pack", "--today", DAY])
    assert _waiting(WREN) == TEXT
    # A first note still waiting on a read is /network's, never written over; but Wren has
    # been written to already, so one marked so is left from before the conversation, and
    # the follow-up takes its place (the maintainer's copy, 2026-11-05: a follow-up's draft
    # opened on WAITS ON A READ). The first-note case is pinned in
    # test_pasted_profiles_and_unread_drafts.py.
    with open(reading.draft_path(WREN), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(reading.WAITS_ON_A_READ + ": nothing was read.\n\nHi Wren, a note.\n")
    assert reading.talked_with(WREN)
    assert followup_drafts.keep([(WREN, TEXT)]) == [WREN]
    assert _waiting(WREN) == TEXT and not reading.marked(WREN)


def test_the_brief_puts_each_follow_up_it_drafts_in_messages(clean, tmp_path, monkeypatch):
    import brief
    import datetime as dt
    # The brief writes to its profile too (the routines it keeps): a copy of the example's,
    # and its own briefs folder taken away afterwards.
    shutil.copytree(os.path.join(ROOT, "profile.example"), tmp_path / "profile")
    monkeypatch.setenv("LJS_PROFILE", str(tmp_path / "profile"))
    person.reset()
    briefs = person.state("documents", "briefs")
    had = set(os.listdir(briefs)) if os.path.isdir(briefs) else None
    try:
        b = brief.gather(dt.date.fromisoformat(DAY), write=True)
    finally:
        monkeypatch.undo()
        person.reset()
        if had is None:
            shutil.rmtree(briefs, ignore_errors=True)
        else:
            for name in set(os.listdir(briefs)) - had:
                os.remove(os.path.join(briefs, name))
    assert b["pack"], "the day's pack is written"
    assert _opens_on_our_note(_waiting(WREN)), _waiting(WREN)


def test_finish_saves_a_follow_up_to_someone_who_never_wrote_back(clean, tmp_path):
    f = tmp_path / "draft.txt"
    f.write_text(TEXT, encoding="utf-8")
    out = io.StringIO()
    with redirect_stdout(out):
        code = reply.finish([WREN, "--draft-file", str(f), "--today", DAY])
    assert code == 0, out.getvalue()
    assert "nothing_to_reply_to" not in out.getvalue()
    assert _waiting(WREN) == TEXT


def test_an_applications_follow_up_passed_by_its_check_is_in_messages(clean, tmp_path):
    tracker = person.state("job_search_tracker.csv")
    with open(tracker, encoding="utf-8") as fh:
        cols = next(csv.reader(fh))
    with open(tracker, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=cols).writerow({c: APP_ROW.get(c, "") for c in cols})
    items, contacts, threads, tracker_rows = followup_drafts.load(DAY)
    got = followup_drafts.drafts(items, contacts, threads, tracker_rows, DAY)
    app = next(i for i in got if i.get("half") == "application" and "Quayside" in i.get("who", ""))
    text = ("Hi Wren, I applied for the Demand Planner role on 10 October and wanted to ask whether "
            "there is any news on it. I'm still very interested in the role.")
    f = tmp_path / "drafts.json"
    f.write_text(json.dumps([{"id": app["id"], "text": text}]), encoding="utf-8")
    code, out = _run(["check", str(f), "--today", DAY])         # no --pack asked for
    assert code == 0, out
    model = _messages()
    msg = next((m for m in model["messages"] if m.get("application")), None)
    assert msg is not None and msg["body"] == text, model["messages"]
    due = next(d for d in model["due"] if (d.get("work") or {}).get("args", {}).get("application"))
    assert due["work"]["args"]["application"] == msg["application"], (due, msg)
