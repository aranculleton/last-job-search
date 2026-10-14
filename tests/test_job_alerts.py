"""LinkedIn job alerts reach a round, read by id and filled from the posting page.

Every message below is invented, in the shapes a LinkedIn alert email takes
(an HTML body with tracked links, and a plain-text one). No real alert email was
available when this was written, which is why the reader takes nothing from the
email but the job id: the title, employer, location and body all come from the
posting page, the same one the round's hydrate step already reads.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import job_alerts  # noqa: E402
import scrape_wide  # noqa: E402

HTML = """
<table><tr><td>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc%3D%3D&amp;refId=1234567890123&amp;lipi=urn">
  Demand Planning Analyst</a> Wrenfield Freight &middot; Manchester
</td></tr><tr><td>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=again">View job</a>
<a href="https://www.linkedin.com/jobs/view/supply-chain-analyst-at-oakmere-4098765432?refId=x">Supply Chain Analyst</a>
<a href="https://www.linkedin.com/company/1234567890/">Company page</a>
<a href="https://www.linkedin.com/comm/jobs/search/?keywords=analyst&amp;geoId=101165590">See all jobs</a>
</td></tr></table>
"""
TEXT = """Your job alert for supply chain analyst in Manchester
Inventory Analyst
Thornbury Logistics - Salford
View job: https://www.linkedin.com/comm/jobs/view/4011112222/?trackingId=x
Unsubscribe: https://www.linkedin.com/comm/psettings/email-unsubscribe?id=99999999999
"""


def test_the_ids_come_from_job_links_only():
    assert job_alerts.job_ids(HTML) == ["4012345678", "4098765432"]
    assert job_alerts.job_ids(TEXT) == ["4011112222"]
    assert job_alerts.job_ids("") == []


def test_a_posting_in_two_alerts_keeps_the_earlier_date():
    found = job_alerts.collect([{"id": "m2", "date": "2026-10-13", "body": HTML},
                                {"id": "m1", "date": "2026-10-11T07:02:00", "body": HTML + TEXT}])
    assert found == {"4012345678": "2026-10-11", "4098765432": "2026-10-11",
                     "4011112222": "2026-10-11"}


def _page(jid):
    pages = {
        "4012345678": {"title": "Demand Planning Analyst", "company": "Wrenfield Freight",
                       "location": "Manchester, England, United Kingdom",
                       "description": "The whole posting. Requirements: SQL.", "isActive": True},
        "4098765432": {"title": "Supply Chain Analyst", "company": "Oakmere",
                       "location": "Manchester", "description": "Body.", "isActive": False},
        "4011112222": {"title": "(untitled)", "isActive": True},
    }
    return (pages[jid], None) if jid in pages else (None, "detail exit 1: Job not found")


def test_each_posting_is_filled_from_its_own_page():
    found = {"4012345678": "2026-10-11", "4098765432": "2026-10-11",
             "4011112222": "2026-10-12", "4000000000": "2026-10-12"}
    rows, left = job_alerts.fill(found, fetch=_page, pause=0)
    assert [r["id"] for r in rows] == ["4012345678"]
    r = rows[0]
    assert r["title"] == "Demand Planning Analyst" and r["company"] == "Wrenfield Freight"
    assert r["url"] == "https://www.linkedin.com/jobs/view/4012345678"
    assert (r["portal"], r["date"], r["source"]) == ("linkedin", "2026-10-11", "job alert")
    assert r["desc"].startswith("The whole posting")
    assert left["4098765432"].startswith("closed")
    assert "no title" in left["4011112222"]
    assert "Job not found" in left["4000000000"]


def test_nothing_is_fetched_when_the_person_turned_linkedin_off(tmp_path, monkeypatch):
    msgs = tmp_path / "m.json"
    msgs.write_text(json.dumps([{"id": "m", "date": "2026-10-12", "body": TEXT}]))
    monkeypatch.setattr(job_alerts.portals, "is_enabled", lambda name: False)
    monkeypatch.setattr(job_alerts, "detail", lambda *a: pytest.fail("LinkedIn was asked"))
    out = tmp_path / "a.json"
    assert job_alerts.main([str(msgs), "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == []


def test_the_query_is_the_persons_and_off_unless_they_set_it(monkeypatch):
    class S:
        JOB_ALERT_QUERY = "from:alerts@example.com"
    monkeypatch.setattr(job_alerts.person, "module", lambda name: S)
    assert job_alerts.query(8) == "from:alerts@example.com newer_than:8d"
    monkeypatch.setattr(job_alerts.person, "module", lambda name: object())
    assert job_alerts.query(8) == ""


def test_a_posting_the_search_also_found_is_kept_once():
    seen = {"https://www.linkedin.com/jobs/view/demand-planning-analyst-at-wrenfield-4012345678":
            {"id": "4012345678", "portal": "linkedin", "url": "x"}}
    alerts = [{"id": "4012345678", "url": "https://www.linkedin.com/jobs/view/4012345678",
               "portal": "linkedin"},
              {"id": "4011112222", "url": "https://www.linkedin.com/jobs/view/4011112222",
               "portal": "linkedin"},
              {"id": "4011112222", "url": "https://www.linkedin.com/jobs/view/4011112222",
               "portal": "linkedin"}]
    assert scrape_wide.merge_alerts(seen, alerts) == 1
    assert "https://www.linkedin.com/jobs/view/4011112222" in seen and len(seen) == 2


def test_a_number_in_the_slug_is_not_the_id():
    assert job_alerts.job_ids(
        "https://www.linkedin.com/jobs/view/analyst-2024000-programme-4012345678?refId=1") == ["4012345678"]


@pytest.mark.parametrize("raw,want", [
    ("2026-10-11T07:02:00Z", "2026-10-11"),
    ("Tue, 13 Oct 2026 07:02:11 +0000", "2026-10-13"),
    ("1792134000000", "2026-10-16"),
    ("not a date", ""),
    ("", ""),
])
def test_email_dates_of_every_shape_become_a_day(raw, want):
    assert job_alerts.day(raw) == want


def test_a_message_with_no_date_never_hides_a_real_one():
    body = "https://www.linkedin.com/comm/jobs/view/4012345678/"
    assert job_alerts.collect([{"date": "", "body": body},
                               {"date": "2026-10-12", "body": body}]) == {"4012345678": "2026-10-12"}


def test_a_posting_with_no_employer_is_left_out():
    rows, left = job_alerts.fill({"4012345678": "2026-10-11"}, pause=0,
                                 fetch=lambda jid: ({"title": "Analyst", "company": "",
                                                     "isActive": True}, None))
    assert rows == [] and "no employer" in left["4012345678"]


def test_the_inbox_is_not_searched_when_linkedin_is_off(monkeypatch, capsys):
    class S:
        JOB_ALERT_QUERY = "from:alerts@example.com"
    monkeypatch.setattr(job_alerts.person, "module", lambda name: S)
    monkeypatch.setattr(job_alerts.portals, "is_enabled", lambda name: False)
    assert job_alerts.main(["--query"]) == 1
    assert "from:" not in capsys.readouterr().out


def test_every_fetch_failing_is_a_failed_step(tmp_path, monkeypatch):
    msgs = tmp_path / "m.json"
    msgs.write_text(json.dumps([{"id": "m", "date": "2026-10-12", "body": TEXT}]))
    monkeypatch.setattr(job_alerts.portals, "is_enabled", lambda name: True)
    monkeypatch.setattr(job_alerts, "detail", lambda jid: (None, "detail exit 1: blocked"))
    monkeypatch.setattr(job_alerts, "fill",
                        lambda found, **k: ([], {j: "detail exit 1: blocked" for j in found}))
    assert job_alerts.main([str(msgs), "--out", str(tmp_path / "a.json")]) == 1
