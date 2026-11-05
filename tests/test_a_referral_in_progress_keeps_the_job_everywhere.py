"""A referral in progress keeps its employer's roles everywhere, by one rule.

The filter before scoring (prefilter.already_ruled_out) dropped every posting at an employer
where someone was referring the person, while the throttle kept them with a note not to
apply cold; a chat closed the referrer to get the role back, which was wrong (2026-11-05).
Both now call `throttle.employer_stops`: only a do-not-target entry drops a posting for its
employer, and a referral in progress keeps it, carrying `referral_note`. Invented people and
employers throughout.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402
import throttle  # noqa: E402

CONTACT_COLUMNS = ("contact_id", "name", "title", "company", "company_key", "status",
                   "next_action", "next_action_due")
THREAD_COLUMNS = ("contact_id", "date", "direction", "channel", "scenario", "summary",
                  "full_text")
POSTING = {"title": "Pricing Analyst", "company": "Quillon Bank",
           "url": "https://jobs.example/quillon/pricing", "priority": 80, "fit": 82}


def _write(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def _state(tmp_path):
    contacts, threads = tmp_path / "network_contacts.csv", tmp_path / "network_threads.csv"
    _write(contacts, CONTACT_COLUMNS, [
        {"contact_id": "quillon_bank_ferrand", "name": "Ottilie Ferrand",
         "title": "Head of Pricing", "company": "Quillon Bank", "company_key": "quillon bank",
         "status": "referral_in_progress",
         "next_action": "She put the person forward for the pricing team"}])
    # The referrer wrote again, so the log reads a reply owed: the stored status still holds.
    _write(threads, THREAD_COLUMNS, [
        {"contact_id": "quillon_bank_ferrand", "date": "2026-10-20", "direction": "out",
         "channel": "message", "scenario": "reply", "summary": "sent",
         "full_text": "Thank you, that would be great."},
        {"contact_id": "quillon_bank_ferrand", "date": "2026-10-22", "direction": "in",
         "channel": "message", "scenario": "", "summary": "They replied",
         "full_text": "I've passed your resume to the hiring manager."}])
    dnt = tmp_path / "do_not_target.json"
    dnt.write_text(json.dumps({"companies": []}), encoding="utf-8")
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    return str(contacts), str(threads), str(dnt), str(seen)


def test_the_filter_before_scoring_keeps_a_role_where_a_referral_is_in_progress(tmp_path):
    contacts, threads, dnt, seen = _state(tmp_path)
    holds = throttle.referral_holds(contacts)
    assert "quillon bank" in holds, holds
    check = prefilter.already_ruled_out(seen, today=None, contacts=contacts, threads=threads,
                                        do_not_target=dnt)
    assert check(dict(POSTING)) == ""


def test_the_throttle_keeps_it_too_and_says_never_to_apply_cold(tmp_path):
    contacts, _threads, _dnt, _seen = _state(tmp_path)
    kept, skipped = throttle.throttle([dict(POSTING)], {}, {}, {}, "2026-10-25",
                                      holds=throttle.referral_holds(contacts))
    assert skipped == [] and len(kept) == 1
    assert "Do not apply cold" in kept[0]["referral_note"]
    assert "Ottilie Ferrand" in kept[0]["referral_note"]


def test_one_rule_decides_for_both_and_only_do_not_target_drops_an_employer():
    holds = {"quillon bank": "referral in progress: Ottilie Ferrand"}
    blocked = {"brackwater mutual": "do not target: no analytics team here"}
    assert throttle.employer_stops("quillon bank", blocked, holds) == ""
    assert throttle.employer_stops("brackwater mutual", blocked, holds).startswith("do not target")
    assert throttle.referral_note("quillon bank", holds).startswith("referral in progress")
    with open(os.path.join(ROOT, "tools", "prefilter.py"), encoding="utf-8") as fh:
        assert "employer_stops(" in fh.read(), "the filter calls the throttle's own rule"
