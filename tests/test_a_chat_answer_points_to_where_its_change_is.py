"""A Chat answer that changed something is a line and a button to the exact card, never a paste.

The maintainer, 2026-11-10: an answer in the page's Chat pasted the whole result (a drafted
reply, a note, a list) or said "it's in Contacts", and the person had to go and find it. Now
each command that writes a record the page shows notes where it is (tools/touched.py), and
`app.py done` turns what its work wrote into the answer's buttons by itself: "Updated in
Contacts" opening that person's card, "Updated in Jobs", "Ready in Jobs" for a draft, "Ready in
Coming up", "Updated in Your profile", "Running in Claude's work". At most four, then "and N
more". An answer that changed nothing has none. Every person and employer is invented:
tests/app_state.py's search.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import touched  # noqa: E402
from test_a_reply_takes_two_commands import LARKSPUR, batch, put, run, write  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
KESTREL_DRAFT = "app-kestrel_mutual_claims_forecasting_analyst"
THORNBURY_IV = "int-thornbury_bank_risk_analyst"
DRAFT = ("Thanks Juno, that is kind of you. I have sent my CV to your email, and I am free "
         "for a call on Thursday afternoon if that suits the team.")


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    s.tmp = tmp_path
    return s


def talk(search, wid="talk~cloud-c1~m1", thread="cloud-c1"):
    put(search, "work", wid, {"kind": "talk", "title": "Answer: a question", "to": "cloud",
                              "args": {"thread": thread, "message": wid.rsplit("~", 1)[-1]},
                              "status": "running", "stage": 1}, 3)
    return wid


def done(search, wid, answer, *extra):
    code, out = run(search, APP, "done", search.dump, "--work", wid, "--summary",
                    "Answered in your chat.", "--reply-file", write(search, "answer.txt", answer),
                    "--kind", "cloud", "--now", NOW, *extra)
    return code, out


def said(out):
    """The thread's new message and the work item's update, from the finish's batch."""
    got = batch(json.loads(out[out.index("{"):])["batches"][0])
    msg = next(e for e in got if e["collection"].startswith("talk/"))
    work = next(e for e in got if e["collection"] == "work")
    return msg["body"], work["body"]


# ------------------------------------------------------------------ the buttons, in code


@pytest.mark.parametrize("section, item, label, to", [
    ("contacts", LARKSPUR, "Updated in Contacts", "page:contacts/" + LARKSPUR),
    ("jobs", "r9-2", "Updated in Jobs", "page:jobs/r9-2"),
    ("drafts", KESTREL_DRAFT, "Ready in Jobs", "page:drafts/" + KESTREL_DRAFT),
    ("interviews", THORNBURY_IV, "Ready in Coming up", "page:interviews/" + THORNBURY_IV),
    ("you", "skills", "Updated in Your profile", "page:you/skills"),
    ("work", "search~20261025T1700-ab12", "Running in Claude's work",
     "page:work/search~20261025T1700-ab12"),
])
def test_each_kind_of_change_is_its_own_button_with_the_pages_own_words(section, item, label, to):
    assert touched.buttons([(section, item)]) == [{"label": label, "to": to}]
    assert touched.parse(to) == (section, [item])


def test_nothing_changed_is_no_button_two_are_two_and_five_are_four_and_one_more():
    assert touched.buttons([]) == []
    two = touched.buttons([("contacts", "a"), ("drafts", "app-b")])
    assert [b["label"] for b in two] == ["Updated in Contacts", "Ready in Jobs"]
    five = touched.buttons([("contacts", c) for c in "abcde"])
    assert [b["label"] for b in five] == ["Updated in Contacts"] * 4 + ["and 1 more"], five
    assert five[-1]["to"] == "page:contacts"                 # the busiest place opens
    # Twenty jobs a search found are one button, each marked, never four and "and 16 more";
    # the same change twice is one.
    jobs = touched.buttons([("jobs", f"r9-{n}") for n in (1, 2, 3)] + [("jobs", "r9-1")])
    assert jobs == [{"label": "Updated in Jobs", "to": "page:jobs/r9-1,r9-2,r9-3"}]
    with pytest.raises(ValueError):
        touched.clean("inbox", "x")


def test_a_change_asked_with_a_pencil_lands_where_its_card_is():
    assert touched.tweak_place({"output": "message", "id": "msg-1", "contact": LARKSPUR}) == \
        ("contacts", LARKSPUR)
    assert touched.tweak_place({"output": "resume", "id": KESTREL_DRAFT}) == \
        ("drafts", KESTREL_DRAFT)
    assert touched.tweak_place({"output": "prep", "id": THORNBURY_IV}) == \
        ("interviews", THORNBURY_IV)
    assert touched.tweak_place({"output": "jobs"}) == ("jobs", "")
    assert touched.tweak_place({"output": "brief"}) is None


def test_a_draft_and_an_interview_are_named_as_the_page_names_them(search, monkeypatch):
    monkeypatch.setenv("LJS_STATE", search.state)
    monkeypatch.setenv("LJS_PROFILE", search.profile)
    assert touched.draft_ids([("Kestrel Mutual", "Claims Forecasting Analyst")]) == \
        [KESTREL_DRAFT]
    assert touched.interview_id("app-thornbury_bank_risk_analyst") == THORNBURY_IV


# ------------------------------------------------------------------ done makes them by itself


def test_what_the_commands_wrote_becomes_the_answers_buttons(search):
    wid = talk(search)
    # A contact added, a job added, an interview booked, and work started: each by its own
    # command, each noted by it, none named to `done`.
    code, out = run(search, "tools/network/state.py", "add", "Ada Example", "--company",
                    "Harbourline Insurance", "--today", "2026-10-25")
    assert code == 0, out
    cid = out.split(" added as ", 1)[1].split(".", 1)[0]
    job = write(search, "job.json", json.dumps({"title": "Pricing Analyst", "company":
                                                "Harbourline Insurance", "url":
                                                "https://jobs.example.com/harbourline/42",
                                                "fit": 81}))
    code, out = run(search, "tools/added_jobs.py", "add", job)
    assert code == 0, out
    n = out.split("added-", 1)[1].split(" ", 1)[0]
    code, out = run(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--date",
                    "2026-10-28", "--time", "14:00", "--today", "2026-10-25")
    assert code == 0, out
    code, out = run(search, APP, "ask", search.dump, "--kind", "search", "--title",
                    "Find jobs", "--now", NOW)
    assert code == 0, out
    search_work = json.loads(out)["work"]
    code, out = done(search, wid, "Added Ada, the Harbourline job and your Thornbury interview, "
                                  "and started a search.")
    assert code == 0, out
    msg, work = said(out)
    want = [{"label": "Updated in Contacts", "to": "page:contacts/" + cid},
            {"label": "Updated in Jobs", "to": "page:jobs/added-" + n},
            {"label": "Ready in Coming up", "to": "page:interviews/" + THORNBURY_IV},
            {"label": "Running in Claude's work", "to": "page:work/" + search_work}]
    assert msg["go"] == want, msg
    assert work["result"]["go"] == want
    # Taken: the next answer of this chat starts with nothing of these.
    wid2 = talk(search, "talk~cloud-c1~m2")
    code, out = done(search, wid2, "Your next interview is on Wednesday at 2pm.")
    assert code == 0, out
    msg, work = said(out)
    assert "go" not in msg and "go" not in work["result"], (msg, work)


def test_a_change_no_command_noted_is_named_and_a_page_link_is_a_button(search):
    wid = talk(search)
    code, out = done(search, wid, "Your skills now list dbt.", "--touched", "you:skills",
                     "--link", "Your draft=page:drafts/" + KESTREL_DRAFT,
                     "--link", "The posting=https://jobs.example.com/kestrel/7")
    assert code == 0, out
    msg, work = said(out)
    assert msg["go"] == [{"label": "Ready in Jobs", "to": "page:drafts/" + KESTREL_DRAFT},
                         {"label": "Updated in Your profile", "to": "page:you/skills"}]
    assert work["result"]["links"] == [{"label": "The posting",
                                        "url": "https://jobs.example.com/kestrel/7"}]
    code, out = done(search, talk(search, "talk~cloud-c1~m3"), "Done.", "--touched", "inbox:1")
    assert code == 2 and "not a place on the page" in out, out


def test_an_answer_that_pastes_what_its_card_holds_is_refused_unless_asked_for(search):
    wid = talk(search)
    long = "Here is your note to Ada, ready to copy: " + " ".join(["word"] * 70)
    code, out = done(search, wid, long, "--touched", "contacts:" + LARKSPUR)
    assert code == 2 and "--in-thread" in out, out
    code, out = done(search, wid, long, "--touched", "contacts:" + LARKSPUR, "--in-thread")
    assert code == 0, out
    msg, _work = said(out)
    assert msg["text"] == long and msg["go"][0]["label"] == "Updated in Contacts"


def test_an_answer_that_changed_nothing_has_no_button(search):
    wid = talk(search)
    code, out = done(search, wid, "Yes: the panel at Thornbury Bank is on Wednesday at 2pm.")
    assert code == 0, out
    msg, work = said(out)
    assert "go" not in msg and "go" not in work["result"], (msg, work)


# ------------------------------------------------------------------ a reply from a screenshot


def _reply(search, *extra):
    wid = talk(search, "talk~cloud-c9~m1", "cloud-c9")
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", "-",
                    "--work", wid, "--dump", search.dump, "--kind", "cloud", "--now", NOW,
                    "--today", "2026-10-25", *extra, given=DRAFT + "\n")
    assert code == 0, out
    return said(out)[0]


def test_a_reply_drafted_from_a_screenshot_is_a_line_and_its_button_not_the_draft(search):
    msg = _reply(search)
    shown = msg["text"] + " " + " ".join(b["label"] for b in msg["go"])
    assert len(shown.split()) < 30 and shown.endswith("Updated in Contacts"), shown
    assert "Thanks Juno" not in msg["text"], msg["text"]
    assert msg["go"] == [{"label": "Updated in Contacts", "to": "page:contacts/" + LARKSPUR}]
    # The draft is on Juno's card, with its Copy.
    with open(os.path.join(search.state, "documents", "network", LARKSPUR, "draft.md"),
              encoding="utf-8") as fh:
        assert fh.read().strip() == DRAFT


def test_every_buttons_words_are_plain():
    from test_a_beginner_is_told_in_plain_words import _plain
    for label in [b["label"] for b in touched.buttons([(s, "x") for s in touched.SECTIONS]
                                                       + [("contacts", "y")])]:
        _plain(label)
        assert "page:" not in label and "/" not in label and "_" not in label, label


def test_asked_to_see_it_in_the_thread_the_draft_goes_there_too(search):
    msg = _reply(search, "--in-thread")
    assert DRAFT in msg["text"], msg["text"]
    assert msg["go"] == [{"label": "Updated in Contacts", "to": "page:contacts/" + LARKSPUR}]
