"""Six words or more in a row copied from the posting into the summary or the letter is flagged.

Pasted posting text reads as spam to the person who wrote the posting, and it is the
cheapest keyword stuffing there is. `audit_letters.shared_runs` caught a letter repeating
the resume, but nothing pointed it at the posting. The letter audit now names each part
of the summary or the letter that copies a run of six words from the posting, the whole
copied stretch, unless the person's own words (the profile, the bullet library) carry it.

The posting and the letter are invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit_letters as AU  # noqa: E402
import untrusted  # noqa: E402

POSTING = ("Supply Chain Analyst. You will own weekly demand forecasting for our depots across "
           "the North West, and partner with transport planning to reduce van miles and improve "
           "on-time-in-full performance across the network.")


def _letter(**kw):
    return dict({
        "company": "Wrenfield Freight Ltd", "role": "Supply Chain Analyst", "posting": POSTING,
        "summary": "Operations analyst who forecasts demand by depot and has cut forecast error "
                   "from 22% to 14%.",
        "p1": "Chilled volumes swing by the week. At Brindle & Hart I forecast them by depot.",
        "p2": "Wrenfield moves goods across the North West for retailers.",
        "lead": "Where I would start:",
        "cl_bullets": [{"label": "Forecasting", "text": "Weekly models by depot, checked "
                        "against what shipped."}],
        "p4": "Thank you for reading.",
    }, **kw)


def test_a_letter_in_its_own_words_has_no_copy():
    assert AU.posting_copies(_letter()) == []


def test_a_copied_stretch_is_named_whole_with_where_it_sits():
    a = _letter(p4="I would partner with transport planning to reduce van miles from day one.",
                summary="Analyst who will own weekly demand forecasting for our depots across "
                        "the region.")
    assert AU.posting_copies(a) == [
        ("the resume summary", "will own weekly demand forecasting for our depots across the"),
        ("the close", "partner with transport planning to reduce van miles")]


def test_five_words_in_a_row_is_using_the_posting_term_not_copying():
    a = _letter(p1="At Brindle & Hart I owned weekly demand forecasting by depot.")
    assert AU.posting_copies(a) == []


def test_the_persons_own_words_are_never_a_copy():
    # The posting happens to use the bullet library's own phrase: it is still theirs.
    posting = "Experience with a route-consolidation model for regional deliveries is a plus."
    a = _letter(posting=posting, p1="At Brindle & Hart I designed a route-consolidation model "
                                    "for regional deliveries that removed 9% of van miles.")
    assert AU.posting_copies(a) == []
    # Without the library, the same words are a copy.
    assert AU.posting_copies(a, own=[]) == [
        ("the opening", "a route consolidation model for regional deliveries")]


def test_a_letter_bullet_is_read_too():
    a = _letter(cl_bullets=[{"label": "Service", "text": "improve on-time-in-full performance "
                             "across the network"}])
    assert AU.posting_copies(a) == [
        ("the Service bullet", "improve on time in full performance across the network")]


def test_the_audit_flags_it(monkeypatch):
    a = _letter(p4="I would partner with transport planning to reduce van miles from day one.")
    with mock.patch.object(AU, "pdf_text", lambda abbr: "Dear Wrenfield Freight hiring team,\n"):
        flags, _words = AU.audit(a)
    assert ('the close copies the posting word for word: "partner with transport planning to '
            'reduce van miles"; say it in your own words, using the posting\'s term once') in flags


def test_a_kept_draft_is_read_with_its_posting(tmp_path):
    # A kept draft.json names its posting, fenced in job_posting.md: the audit reads it.
    (tmp_path / "job_posting.md").write_text("# Posting\n\n" + untrusted.fence(POSTING),
                                             encoding="utf-8")
    a = _letter(p4="I would partner with transport planning to reduce van miles from day one.")
    del a["posting"]
    a["posting_from"] = "job_posting.md"
    path = tmp_path / "draft.json"
    path.write_text(json.dumps([a]), encoding="utf-8")
    # The PDF is not rendered, so the audit stops there; what it read is in the error.
    import fit_to_page
    apps, read_in = fit_to_page.load(str(path))
    assert read_in == {0} and AU.posting_copies(apps[0])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "audit_letters.py"), str(path)],
                       capture_output=True, text=True, cwd=ROOT,
                       env=dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example"),
                                LJS_STATE=str(tmp_path)))
    assert "no compiled letter" in r.stderr
