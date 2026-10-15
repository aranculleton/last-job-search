"""A posting stays out only for a verdict on the posting, and an internal posting never comes in.

`throttle.ruled_out()` decides which seen_jobs.json entries block a posting for good.
It treated as permanent every skip the throttle writes back, though the throttle
derives each of them afresh every run from live state:

- a referral hold kept blocking every posting it had touched after the referral had
  converted or lapsed (in one repo, 59 postings at one employer for a month);
- a do-not-target entry stopped suppressing at its review date, and its skips did not;
- older rounds' queue decisions ("not scored this round", "never read by a model")
  blocked postings nobody had judged;
- an `excluded` entry citing the company throttle blocked, though a `skipped` one did not.

And a Workday requisition on the employer's internal site surfaced at fit 98: it was
absent from the employer's external site, so nobody outside could apply.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402
import throttle  # noqa: E402

URL = "https://example.com/jobs/%d"


def _seen(reason, status="skipped", n=1, **extra):
    return {URL % n: dict({"title": "Planner %d" % n, "company": "Acme", "url": URL % n,
                           "first_seen": "2026-09-01", "status": status,
                           ("skip_reason" if status == "skipped" else "exclusion_reason"): reason},
                          **extra)}


def _blocks(entries):
    urls, pairs = throttle.ruled_out(entries)
    return bool(urls or pairs)


def test_a_lapsed_referral_hold_no_longer_blocks():
    reason = ("referral in progress: Sam Reed, Head of Planning has put the candidate's name "
              "forward here. Do not apply cold; it would collide with the referral.")
    assert not _blocks(_seen(reason))


def test_a_live_referral_hold_still_skips_through_the_throttle():
    row = {"title": "Planner", "company": "Acme", "url": URL % 1, "priority": 80}
    hold = {"acme": "referral in progress: Sam Reed has put the candidate's name forward here."}
    kept, skipped = throttle.throttle([row], {}, {}, {}, "2026-10-15", holds=hold)
    assert not kept and skipped[0]["skip_reason"].startswith("referral in progress")


def test_the_prefilter_applies_a_live_hold_before_hydrate(tmp_path, monkeypatch):
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    monkeypatch.setattr(throttle, "referral_holds",
                        lambda *a, **k: {"acme": "referral in progress: Sam Reed"})
    monkeypatch.setattr(throttle, "load_do_not_target", lambda *a, **k: {})
    check = prefilter.already_ruled_out(str(seen))
    assert check({"company": "Acme Ltd", "title": "Planner", "url": URL % 9}).startswith(
        "referral in progress")
    assert check({"company": "Other Co", "title": "Planner", "url": URL % 9}) == ""


def test_an_expired_do_not_target_skip_no_longer_blocks():
    reason = ("do not target: only a sales office here (recorded 2026-01-01, review after "
              "2026-07-01)")
    assert not _blocks(_seen(reason))


def test_a_queue_decision_never_blocks():
    for reason in ("passed the prefilter; ranked below the affinity cut this round and never "
                   "read by a model",
                   "survived the screen; not scored this round (queue priority)",
                   "survived the screen; ranked too low to score"):
        assert not _blocks(_seen(reason)), reason


def test_an_excluded_company_throttle_entry_does_not_block():
    for reason in ("company throttle: an application is already open at this employer",
                   "same-employer duplicate: Planner scored higher this run"):
        assert not _blocks(_seen(reason, status="excluded")), reason


def test_a_real_verdict_still_blocks():
    assert _blocks(_seen("eligibility gate: citizenship stated as a condition",
                         status="excluded"))
    assert _blocks(_seen("posting closed"))


# ------------------------------------------------------------------ internal Workday sites

def _decide(url):
    job = {"title": "Senior Supply Chain Analyst", "company": "Acme",
           "location": "Manchester, England, United Kingdom", "url": url}
    return prefilter.decide(job)


def test_a_posting_on_an_internal_workday_site_is_dropped_with_its_reason():
    ok, why = _decide("https://acme.wd3.myworkdayjobs.com/Privileged/job/Manchester/"
                      "Senior-Supply-Chain-Analyst_R0012345")
    assert not ok and why == "eligibility: internal Workday site (Privileged)"
    ok, _ = _decide("https://acme.wd5.myworkdayjobs.com/en-US/Privileged/job/Manchester/"
                    "Senior-Supply-Chain-Analyst_R0012345")
    assert not ok


def test_workday_itself_is_not_a_reason_to_drop():
    for url in ("https://acme.wd3.myworkdayjobs.com/External/job/Manchester/"
                "Senior-Supply-Chain-Analyst_R0012345",
                "https://acme.wd3.myworkdayjobs.com/en-US/AcmeCareers/job/Manchester/"
                "Senior-Supply-Chain-Analyst_R0012345",
                "https://example.com/Privileged/job/Senior-Supply-Chain-Analyst"):
        ok, why = _decide(url)
        assert ok, (url, why)
