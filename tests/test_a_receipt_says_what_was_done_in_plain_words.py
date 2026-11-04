"""A receipt says what was done, in the person's words: never a refusal for a tap already done,
never "done" for nothing, never a command, never a sentence cut mid-word.

Engine audit 13 to 16 (2026-11-03), each test one finding's own steps, on invented people and
employers: a tap applied once whose receipt never landed came back refused and naming
`confirm.py`; an answer typed into a question broke the profile file it was written into; a
receipt cut its next step at 80 characters; and undo-only actions sent alone said "done".
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_actions  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _fresh_read(search, keep_ledger: bool):
    """The page read again into a new folder: the actions as they are, no receipts (the batch
    that carried them was never sent), and none of the old folder's ledger."""
    acts = os.path.join(search.dump, "actions")
    saved = {f: open(os.path.join(acts, f), encoding="utf-8").read() for f in os.listdir(acts)}
    shutil.rmtree(search.dump)
    os.makedirs(acts)
    for f, text in saved.items():
        with open(os.path.join(acts, f), "w", encoding="utf-8") as fh:
            fh.write(text)
    if not keep_ledger:                     # another copy: none of this one's kept receipts
        was = os.environ.get("LJS_STATE")
        os.environ["LJS_STATE"] = search.state
        try:
            kept = app_actions._kept_ledger_path()
        finally:
            os.environ["LJS_STATE"] = was if was is not None else ""
        assert kept and not kept.startswith(search.state)
        if os.path.exists(kept):
            os.remove(kept)


@pytest.mark.parametrize("same_copy", [True, False])
def test_i_have_applied_applied_again_from_a_new_read_is_done(search, same_copy):
    """Engine 13: `job.applied` on job-new, applied; the receipt's batch lost; the same action
    from a fresh read came back `conflict`, "the tracker already has ...; confirm that row:
    confirm.py applied ...". In the same copy the kept receipt goes again; in a new one the
    tracker's own row says it is recorded."""
    aid = search.act("job.applied", "job-new", rev="",
                     value={"company": "Wren Health", "role": "Planner", "on": "2026-10-21"})
    assert search.apply()["ok"] == [aid]
    _fresh_read(search, keep_ledger=same_copy)
    got = search.apply()
    note = search.receipt(aid)
    assert note["result"] == "ok", note
    assert "confirm.py" not in note["note"] and "tracker" not in note["note"]
    assert (aid in got["again"]) if same_copy else note["note"] == \
        "Already recorded: you applied to Wren Health."
    with open(os.path.join(search.state, "job_search_tracker.csv"), encoding="utf-8") as fh:
        assert sum("Wren Health" in line for line in fh) == 1


def test_an_answer_in_a_codes_place_never_breaks_the_file(tmp_path):
    """Engine 14: `MIN_PAY = [CONFIRM: your floor]` answered "yes" was written as
    `MIN_PAY = yes`, which compiles and then stops the file loading."""
    p = tmp_path / "search.py"
    p.write_text("# pay\nMIN_PAY = [CONFIRM: your floor]\nNOTE = \"[CONFIRM: a note]\"\n",
                 encoding="utf-8")
    t = {"what": "your floor"}
    assert app_actions._answer_in_place(str(p), t, "yes") is False
    assert "[CONFIRM: your floor]" in p.read_text(encoding="utf-8")
    assert app_actions._answer_in_place(str(p), t, "120,000") is True
    assert "MIN_PAY = 120000\n" in p.read_text(encoding="utf-8")
    # Inside words, any words.
    assert app_actions._answer_in_place(str(p), {"what": "a note"}, "only remote") is True
    assert 'NOTE = "only remote"' in p.read_text(encoding="utf-8")
    import runpy
    assert runpy.run_path(str(p))["MIN_PAY"] == 120000


def test_the_next_step_in_a_sent_receipt_is_whole_words(search):
    """Engine 15: "...follow up if no reply (1 of 2 sent; your rule: 14 days, at mos, Tuesday
    17 November." The receipt cut the contact's raw next step at 80 characters."""
    import test_a_message_goes_out_by_hand_and_is_logged_once as M
    (msg,) = search.model()["messages"]
    aid = search.act("msg.sent", msg["id"], value={"text": msg["body"]})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    note = search.receipt(aid)["note"]
    import app_model
    raw = M._contact(search, msg["contact"])["next_action"]
    step = note.split("Next:", 1)[1].rsplit(",", 1)[0].strip()
    assert step == app_model.short(app_model.plain_action(raw), 90), note
    # The audit's own line, in the page's words and whole.
    said = app_model.short(app_model.plain_action(
        "Follow up if no reply (1 of 2 sent; your rule: 14 days, at most 2 unanswered)"), 90)
    assert said == "Follow up if they don't reply (1 of 2 sent)"


class _W:
    def __init__(self):
        self.entries = []

    def add(self, *a, **k):
        self.entries.append(a)

    def drop(self, *a):
        return False


def _run(action, target, value=None):
    act = {"action": action, "at": NOW, "value": value if value is not None else {}}
    return app_actions.Run("a1", act, target, {"work": {}}, _W(), "cloud-1", "UTC",
                           dt.datetime(2026, 10, 25, 18, tzinfo=dt.timezone.utc))


def test_an_undo_sent_alone_never_says_it_was_done(monkeypatch):
    """Engine 16: `due.undo` with no `due.done` before it said "Due again: Kamal.";
    `outcome.undo` with nothing to restore said "Taken back: it is as it was.";
    `interview.unrework` on nothing said ok; a consent for work not in the read named the
    read; `referral.ended` with no reason said "is over (over)"; a bare number was logged as
    the words that went."""
    with pytest.raises(app_actions.Refused, match="nothing to bring back"):
        app_actions._due_undo(_run("due.undo", {"kind": "due", "contact": "c1"}))
    with pytest.raises(app_actions.Refused, match="nothing to take back"):
        app_actions._outcome_undo(_run("outcome.undo", {"kind": "application",
                                                         "company": "Wren Health"}))
    import interview_pack
    monkeypatch.setattr(interview_pack, "remove_rework", lambda *a, **k: False)
    with pytest.raises(app_actions.Refused, match="nothing changed"):
        app_actions._unrework(_run("interview.unrework", {"kind": "interview",
                                                          "company": "Wren Health"}))
    with pytest.raises(app_actions.Refused) as gone:
        app_actions._consent(_run("consent.yes", {"kind": "work", "id": "draft~x"},
                                  {"skill": "Kafka"}), "yes")
    assert str(gone.value) == "That is no longer on your page: look again."
    monkeypatch.setattr(app_actions, "_set_contact", lambda *a, **k: {})
    monkeypatch.setattr(app_actions, "_first", lambda cid: "Kit")
    got = app_actions._referral_ended(_run("referral.ended", {"kind": "person", "contact": "c1"}))
    assert got["note"] == "The referral through Kit is over. The hold there is lifted."
    assert "text" not in app_actions.value_of({"action": "msg.sent", "value": 12345})
    assert app_actions.value_of({"action": "msg.sent", "value": "Thanks!"})["text"] == "Thanks!"
    json.dumps(got)


def test_taps_on_different_items_build_the_page_once(search, monkeypatch):
    """Engine 17: every tap rebuilt the page's sections before the next, so fifteen taps built
    them fifteen times, seconds a tap. Taps on different jobs now share one build; a second
    tap on a job this run already changed reads it afresh."""
    import app_model
    import person
    rows = [r for r in search.model()["jobs"]["rows"] if r["id"].startswith("r9-")][:3]
    assert len(rows) == 3
    for r in rows:
        search.act("job.dismiss", r["id"], value={"why": "too far to travel"}, rev=r["rev"])
    again = search.act("job.dismiss", rows[0]["id"], value={"why": "too far"}, rev=rows[0]["rev"])
    monkeypatch.setenv("LJS_STATE", search.state)
    monkeypatch.setenv(person.ENV, search.profile)
    monkeypatch.setenv("LJS_COPY", "private")
    person.reset()
    built = []
    real = app_model.build
    monkeypatch.setattr(app_model, "build",
                        lambda *a, **k: built.append(sorted(k.get("only") or ())) or real(*a, **k))
    got = app_actions.apply_dir(search.dump, "cloud-1",
                                dt.datetime(2026, 10, 25, 18, tzinfo=dt.timezone.utc))
    person.reset()
    # The fourth taps a job an earlier tap in the same batch changed: it reads the job afresh
    # and is applied, never bounced as changed (the maintainer's note 6, 2026-11-04).
    assert len(got["ok"]) == 4 and again in got["ok"], got
    assert built.count(["jobs"]) == 2, built        # once for the three, once for the fourth
