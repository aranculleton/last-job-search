"""Every system openroles reads is read by a round, with nothing listed twice.

The board reader is openroles; this app keeps only what is the search's own: the places
a person can work, which bodies are worth a request, and which pages are already ruled
out. Invented boards only, and the network is replaced with canned answers.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import record_drafts  # noqa: E402
from openroles.providers import READERS  # noqa: E402

HOME = "Manchester, England, United Kingdom"     # the example person's city


def test_every_system_openroles_reads_is_read_and_applied_to_online():
    assert set(ats_boards.FETCH) == set(READERS) == set(record_drafts.EMPLOYER_BOARDS)
    assert {"personio", "rippling", "careersite"} <= set(ats_boards.FETCH)


def test_a_personio_board_is_judged_at_its_places(boards_web):
    boards_web.routes["acme.jobs.personio.de/xml"] = ("""<?xml version="1.0"?><workzag-jobs>
      <position><id>1</id><office>Manchester</office><name>Data Analyst</name></position>
      <position><id>2</id><office>Berlin</office><name>Data Analyst</name></position>
    </workzag-jobs>""", None)
    rows, err = ats_boards.FETCH["personio"]("Acme", "acme")
    assert err is None and [r["id"] for r in rows] == ["ps-1"]
    assert rows[0]["portal"] == "personio" and rows[0]["company"] == "Acme"


def _rippling(boards_web, titles):
    base = "api.rippling.com/platform/api/ats/v2/board/acme/jobs"
    boards_web.routes[base + "?"] = {"items": [
        {"id": f"r{n}", "name": t, "url": f"https://ats.rippling.com/acme/jobs/r{n}",
         "locations": [{"name": "Manchester", "city": "Manchester", "country": "United Kingdom"}]}
        for n, t in enumerate(titles)], "totalPages": 1}
    for n, t in enumerate(titles):
        boards_web.routes[f"{base}/r{n}"] = {"uuid": f"r{n}", "name": t,
                                              "description": {"role": "<p>Model demand.</p>"}}


def test_a_body_is_asked_for_only_where_the_free_gates_pass(boards_web):
    _rippling(boards_web, ["Data Analyst", "Head Chef"])
    rows, _ = ats_boards.FETCH["rippling"]("Acme", "acme")
    asked = [u for u, _ in boards_web.calls if "/jobs/r" in u]
    assert asked == ["https://api.rippling.com/platform/api/ats/v2/board/acme/jobs/r0"]
    by_title = {r["title"]: r["desc"] for r in rows}
    assert "Model demand." in by_title["Data Analyst"]
    assert by_title.get("Head Chef") is None          # emitted without a body, or not at all


def test_a_careers_site_skips_what_the_search_already_ruled_out(boards_web, monkeypatch):
    host = "careers.acme.example"
    boards_web.robots[host] = (200, "User-agent: *\nAllow: /\n")
    boards_web.routes[f"{host}/sitemap.xml"] = (f"""<urlset>
      <url><loc>https://{host}/job/1/data-analyst</loc><lastmod>2026-10-02</lastmod></url>
      <url><loc>https://{host}/job/2/data-analyst</loc><lastmod>2026-10-01</lastmod></url>
    </urlset>""", None)
    page = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Data Analyst",'
            ' "jobLocation": {"address": {"addressLocality": "Manchester"}}}</script>')
    boards_web.routes["/job/1/"] = (page, None)
    boards_web.routes["/job/2/"] = (page, None)
    rows, note = ats_boards.careersite("Acme", host, queries=["data analyst"],
                                       skip=lambda url: "/job/1/" in url)
    assert [r["url"] for r in rows] == [f"https://{host}/job/2/data-analyst"] and note is None
    assert not any("/job/1/" in u for u, _ in boards_web.calls)


def test_a_probe_reads_a_board_once_and_a_careers_site_not_at_all(boards_web, monkeypatch):
    _rippling(boards_web, ["Data Analyst"])
    host = "careers.acme.example"
    boards_web.robots[host] = (200, "User-agent: *\nAllow: /\n")
    boards_web.routes[f"{host}/sitemap.xml"] = (
        f"<urlset><url><loc>https://{host}/job/1/data-analyst</loc></url></urlset>", None)
    monkeypatch.setattr(ats_boards, "REFUSED", {})
    monkeypatch.setattr(ats_boards, "REFUSED_PROVIDERS", {})
    out = ats_boards.probe({"Acme": ("rippling", "acme"), "Acme Careers": ("careersite", host)})
    assert out == {"Acme": "1 open, 1 in range", "Acme Careers": "1 job pages listed"}
    assert not any("/jobs/r0" in u or "/job/1/" in u for u, _ in boards_web.calls)


def _two_careers_sites(boards_web):
    page = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Data Analyst",'
            ' "jobLocation": {"address": {"addressLocality": "Manchester"}}}</script>')
    boards = {}
    for name in ("acme", "brindle"):
        host = f"careers.{name}.example"
        boards_web.robots[host] = (200, "User-agent: *\nAllow: /\n")
        boards_web.routes[f"{host}/sitemap.xml"] = (
            f"<urlset><url><loc>https://{host}/job/1/data-analyst</loc></url></urlset>", None)
        boards[name.title() + " Careers"] = ("careersite", host)
    boards_web.routes["/job/1/"] = (page, None)
    return boards


def test_a_round_reads_its_own_rulings_once_for_every_careers_site(boards_web, monkeypatch,
                                                                   tmp_path):
    # The skip was built for each careers-site employer from the repo's seen file, so a
    # round's own --seen was never read and its --no-seen-read ("judge everything again")
    # still skipped every page it had once ruled out.
    import json
    import prefilter
    boards = _two_careers_sites(boards_web)
    seen = tmp_path / "seen_jobs.json"
    url = "https://careers.acme.example/job/1/data-analyst"
    seen.write_text(json.dumps({"seen": {url: {
        "url": url, "title": "Data Analyst", "company": "Acme Careers", "status": "excluded",
        "basis": "person", "exclusion_reason": "not a company I want to work for",
        "excluded_date": "2026-10-01"}}}))
    built = []
    real = prefilter.already_ruled_out
    monkeypatch.setattr(prefilter, "already_ruled_out",
                        lambda *a, **k: built.append(a) or real(*a, **k))
    rows, _ = ats_boards.fetch_all(boards, seen=str(seen))
    assert sorted(r["url"] for r in rows) == ["https://careers.brindle.example/job/1/data-analyst"]
    assert len(built) == 1 and built[0][0] == str(seen)
    rows, _ = ats_boards.fetch_all(boards, seen=str(seen), keep_ruled_out=True)
    assert len(rows) == 2
