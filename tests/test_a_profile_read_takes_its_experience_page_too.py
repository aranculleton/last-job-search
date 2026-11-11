"""A profile read gets their Experience in one read on LinkedIn's newer layout.

On 2026-11-09 the extractor returned no sections on every profile a computer chat read:
LinkedIn's newer layout leaves Experience off the profile page altogether, on the profile's
own Experience page, and the read said to scroll the same page for ever. Now the extractor
gives the address of that page when the profile has no Experience, a second result read
from it is merged with the first into one read, and the older layout (Experience on the
profile) reads as before. Not tried on a live LinkedIn page: these pages are made up, in
the shape the report described. Every person here is invented.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import reading  # noqa: E402
import state  # noqa: E402

PROFILE = "https://www.linkedin.com/in/example-tamsin/"
TOP = ["Tamsin Oyelaran", "Head of Demand Forecasting at Fernhill Freight",
       "Leeds, England, United Kingdom", "Contact info"]
NEW_LAYOUT = TOP + ["Activity", "Tamsin reposted this", "About",
                    "I run forecasting for a chilled-freight network.", "Education",
                    "University of Leeds", "2014 - 2017"]
EXPERIENCE_PAGE = ["Experience", "Head of Demand Forecasting", "Fernhill Freight · Full-time",
                   "Jan 2023 - Present", "Senior Analyst", "Oakmere Foods",
                   "2018 - 2022"]
OLD_LAYOUT = TOP + ["About", "I run forecasting for a chilled-freight network.",
                    "Experience", "Head of Demand Forecasting", "Fernhill Freight",
                    "Jan 2023 - Present", "Education", "University of Leeds", "2014 - 2017"]


def _run(tmp_path, lines, href):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed here")
    harness = tmp_path / "run.js"
    harness.write_text(
        "const main = {innerText: %s, querySelector: () => null, querySelectorAll: () => []};\n"
        "global.document = {querySelector: s => s === 'main' ? main : null,\n"
        "  getElementById: () => null, body: main, title: 't'};\n"
        "global.location = {href: %s};\n"
        "console.log(eval(%s));\n" % (json.dumps("\n".join(lines)), json.dumps(href),
                                      json.dumps(reading.EXTRACTOR)), encoding="utf-8")
    out = subprocess.run([node, str(harness)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60).stdout
    return out.strip()


def test_the_extractor_names_the_experience_page_and_reads_it_there(tmp_path):
    main = json.loads(_run(tmp_path, NEW_LAYOUT, PROFILE))
    assert [s["heading"] for s in main["sections"]] == ["About", "Education"]
    assert main["experience_page"] == PROFILE + "details/experience/"
    exp = json.loads(_run(tmp_path, EXPERIENCE_PAGE, PROFILE + "details/experience/"))
    assert exp["page"] == "experience" and "experience_page" not in exp
    assert [s["heading"] for s in exp["sections"]] == ["Experience"]
    # The older layout: Experience on the profile, nothing more to load.
    old = json.loads(_run(tmp_path, OLD_LAYOUT, PROFILE))
    assert "experience_page" not in old
    assert [s["heading"] for s in old["sections"]] == ["About", "Experience", "Education"]


def test_two_results_one_after_the_other_are_one_read(tmp_path):
    main = _run(tmp_path, NEW_LAYOUT, PROFILE)
    exp = _run(tmp_path, EXPERIENCE_PAGE, PROFILE + "details/experience/")
    merged = json.loads(reading.extract_json(main + "\n" + exp))
    assert [s["heading"] for s in merged["sections"]] == ["About", "Education", "Experience"]
    assert "experience_page" not in merged and merged["top"].startswith("Tamsin")
    r = reading.parse(reading.from_extract(json.dumps(merged)), name="Tamsin Oyelaran",
                      company="Fernhill Freight", source="browser")
    assert r["current"] == "Fernhill Freight"
    assert reading.has_experience(reading.from_extract(json.dumps(merged)))


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts = str(tmp_path / "contacts.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", str(tmp_path / "threads.csv"))
    real_load, real_save = state.load_contacts, state.save_contacts
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_load(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_save(rows, path))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    state.save_contacts([{"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran",
                          "company": "Fernhill Freight", "status": "not_contacted",
                          "linkedin_url": PROFILE,
                          "location": "Leeds, England, United Kingdom"}])
    reading.shortlist(["fernhill_oyelaran"], contacts=state.load_contacts())
    return tmp_path


def test_read_sends_the_chat_to_the_experience_page_then_takes_both(book, tmp_path, capsys):
    main = _run(tmp_path, NEW_LAYOUT, PROFILE)
    page = tmp_path / "one.txt"
    page.write_text(main, encoding="utf-8")
    assert reading.main(["read", "fernhill_oyelaran", str(page), "--source", "browser"]) \
        == reading.EXIT["scroll"]
    out = capsys.readouterr().out
    assert PROFILE + "details/experience/" in out and "together" in out
    assert reading.load("fernhill_oyelaran") is None
    page.write_text(main + "\n" + _run(tmp_path, EXPERIENCE_PAGE,
                                       PROFILE + "details/experience/"), encoding="utf-8")
    assert reading.main(["read", "fernhill_oyelaran", str(page), "--source", "browser"]) == 0
    got = reading.load("fernhill_oyelaran")
    assert got["current"] == "Fernhill Freight"


def test_the_next_step_names_both_pages():
    line = reading._go_line("deep", PROFILE)
    assert PROFILE + "details/experience/" in line and "one read" in line
