"""What goes next on a thread follows the last message, read on every channel.

Seen on a person's page (2026-10-26): a drafted LinkedIn message opened "last year you kindly
offered to refer me ...", said "I've since moved to <the city>" and asked whether the offer
still stood. The person had written to that contact in August, saying they had moved and
asking about roles there, and nothing had come back. The draft read as if nobody had
written since the offer, and told them again what the August note had told them. Every
message drafted for someone whose last word was the person's own, unanswered, now follows
up on that message: the gate refuses one that does not (compose.thread_findings), and code
drafts one that does. Invented people and employers throughout.
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sys
import types
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import app_alerts  # noqa: E402
import compose  # noqa: E402
import followup_drafts  # noqa: E402
import person  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

CID = "kestrel_rook"
ANA = {"contact_id": CID, "name": "Ana Rook", "title": "Senior Data Analyst",
       "company": "Kestrel Mutual", "company_key": "kestrel mutual",
       "location": "Manchester, England, United Kingdom", "channel": "linkedin",
       "route": "alumni", "status": "awaiting_reply", "first_contacted": "2025-09-20"}
THREAD = [
    {"contact_id": CID, "date": "2025-09-20", "direction": "outbound", "channel": "linkedin",
     "scenario": "first_note", "summary": "first note",
     "full_text": "Hi Ana, we were both at Oakmere. How is the analytics team at Kestrel set up?"},
    # A year ago: their offer to refer.
    {"contact_id": CID, "date": "2025-10-02", "direction": "inbound", "channel": "linkedin",
     "scenario": "referral_offered", "summary": "offered to refer",
     "full_text": "Hi Morgan, good to hear from you. If you find a role on our careers page, "
                  "send it over and I'll happily refer you."},
    # August: the person's own note, by email this time, and no answer since.
    {"contact_id": CID, "date": "2026-08-24", "direction": "outbound", "channel": "email",
     "scenario": "", "summary": "update",
     "full_text": "Hi Ana, a quick update: I've moved to Manchester now and I'm looking at "
                  "data roles here. Is anything coming up at Kestrel?"},
]
# The shape of the draft the page showed.
IGNORES = ("Hi Ana, last year you kindly offered to refer me if I found a role on Kestrel's "
           "careers page. I've since moved to Manchester. If I send you a link to a data role "
           "there, would you still be open to referring me?")
FOLLOWS = ("Hi Ana, following up on my note from August. Last year you offered to refer me for "
           "a role at Kestrel: if I send you a link to a data job there, would you still be "
           "open to that?")


@pytest.fixture
def thread():
    """Ana and her thread in the tests' own state (conftest's copy of the example's), put
    back as it was afterwards."""
    files = {p: open(p, encoding="utf-8").read() for p in (state.CONTACTS_CSV, state.THREADS_CSV)}
    folder = os.path.dirname(reading.path(CID))
    for path, cols, rows in ((state.CONTACTS_CSV, schema.CONTACT_COLUMNS, [ANA]),
                             (state.THREADS_CSV, schema.THREAD_COLUMNS, THREAD)):
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
    reading.save(CID, {"name": "Ana Rook", "company": "Kestrel Mutual",
                       "headline": "Senior Data Analyst at Kestrel Mutual",
                       "location": ANA["location"],
                       "sources": [{"kind": "paste", "url": "", "date": "2026-08-20"}],
                       "items": [{"kind": "about", "text": "Pricing analytics at Kestrel."}]})
    try:
        yield
    finally:
        for p, text in files.items():
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        shutil.rmtree(folder, ignore_errors=True)


def _rules(found):
    return [getattr(v, "rule", None) or v[0] for v in found]


def test_a_draft_that_answers_the_old_offer_and_repeats_the_august_note_is_refused(thread):
    found = compose.validate(IGNORES, "nudge", contact=CID, today="2026-10-26")
    assert "ignores_your_last_message" in _rules(found)
    assert "repeats_your_last_message" in _rules(found)
    said = " ".join(v.text for v in found)
    assert "24 August 2026" in said and "Following up on my note from August" in said
    # The same on the doors a chat's draft goes through: the gate /reply runs ...
    got = followup_drafts.check([{"id": CID, "text": IGNORES, "kind": "nudge"}],
                                state.load_contacts(), state.load_threads(), "2026-10-26")
    assert not got[0]["ok"]
    # ... and the save that puts it on the page.
    note = os.path.join(os.path.dirname(reading.path(CID)), "note.txt")
    with open(note, "w", encoding="utf-8") as fh:
        fh.write(IGNORES)
    out = io.StringIO()
    with redirect_stdout(out):
        assert reading.main(["draft", CID, note]) == reading.EXIT["error"]
    assert "not saved" in out.getvalue() and "24 August 2026" in out.getvalue()
    assert not os.path.isfile(reading.draft_path(CID))
    # A composer handed the same words refuses them too.
    with pytest.raises(compose.Refused, match="24 August 2026"):
        compose.referral_ask("Ana", "last year you kindly offered to refer me if I found a "
                             "role on Kestrel's careers page", "the Data Analyst role at "
                             "Kestrel", "https://example.com/kestrel/data-analyst", thread=CID)


def test_a_draft_that_follows_up_on_the_august_note_passes(thread):
    rules = _rules(compose.validate(FOLLOWS, "nudge", contact=CID, today="2026-10-26"))
    assert "ignores_your_last_message" not in rules and "repeats_your_last_message" not in rules


def test_code_drafts_the_follow_up_to_the_august_note_and_never_repeats_it(thread):
    out = io.StringIO()
    with redirect_stdout(out):
        followup_drafts.main(["--contact", CID, "--today", "2026-09-04", "--json"])
    item = next(i for i in json.loads(out.getvalue()) if i["id"] == CID)
    draft = item["draft"]
    assert draft["status"] in ("ready", "check"), draft
    # The August note went by email: it is followed up as that.
    assert "following up on my email from August" in draft["text"]
    assert "moved" not in draft["text"].lower() and "last year" not in draft["text"].lower()
    assert compose.thread_findings(draft["text"], CID, today="2026-09-04") == []
    # What a chat writing it by hand is told, first.
    told = followup_drafts.context([CID], state.load_contacts(), state.load_threads(),
                                   "2026-10-26")
    assert "the last word is yours: your message of 2026-08-24 has no answer" in told
    assert "Following up on my note from August" in told


def test_a_follow_up_needs_a_message_of_the_persons_own_waiting():
    answered = THREAD + [{"contact_id": CID, "date": "2026-08-30", "direction": "inbound",
                          "channel": "email", "scenario": "", "summary": "replied",
                          "full_text": "Hi Morgan, nothing open right now, but I'll keep an eye out."}]
    assert compose.unanswered_ours(answered) is None
    assert compose.thread_findings(IGNORES, answered, today="2026-10-26") == []
    with pytest.raises(ValueError, match="nothing to follow up"):
        compose.follow_up("Ana", answered, "Kestrel has since posted a data role")
    assert compose.unanswered_ours(THREAD)["date"] == "2026-08-24"


def test_the_page_says_the_persons_own_note_is_waiting_before_asking_about_a_role():
    ctx = types.SimpleNamespace(contacts=[dict(ANA, status="in_conversation")],
                                live={CID: "in_conversation"}, by_contact={CID: THREAD})
    got = app_alerts._warm_suggest(ctx, "job-1", "Kestrel Mutual")
    assert "your message of 2026-08-24 has no answer yet: follow it up" in got["text"]
    assert person.state()  # the example's own state, never a person's


def test_a_waiting_draft_written_before_the_check_is_flagged_on_its_card(thread):
    """A draft already in its folder from before this check never passed it: the page's card
    says what is wrong in plain words, so it is not sent as it is (2026-10-26)."""
    import app_model
    said = [w["said"] for w in app_model.message_warnings(IGNORES, "follow_up", ANA)]
    assert any("your last message" in s for s in said), said
    assert not [w for w in app_model.message_warnings(FOLLOWS, "follow_up", ANA)
                if "your last message" in w["said"]]
