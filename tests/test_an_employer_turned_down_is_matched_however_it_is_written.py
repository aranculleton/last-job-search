"""An employer turned down by name is turned down however its entry is written.

The bar looked a declined employer up by its key (company_key) in BAR_DECLINED as written, so
an entry a chat or the person wrote by hand in any other form matched nothing, and nothing
said so: "north-shore mutual" (the key has a space where the hyphen is), "acme insurance" (the
key drops the line of business: "acme"). The search's cut read the same list the same way
(run_round.declined_now), so those employers kept reaching Jobs. And a bilingual posting name,
"Acme Assurance et services financiers", keyed to the whole string and missed "acme" too.

Each entry is now read through the key, wherever the list is read, and the page's own writers
find, take off and put back an entry by its key, so one written by hand comes off Your rules
like one the page wrote. Invented employers only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
import person  # noqa: E402
import profile_set  # noqa: E402

TODAY = "2026-11-03"
WRITTEN = {"north-shore mutual": "candidate declined it 2026-11-01: \"not North-Shore\"",
           "acme insurance": "candidate declined it 2026-11-01: \"no Acme, any of it\"",
           "brindle & hart": "candidate declined it 2026-11-02: \"not them\""}


def _profile(tmp_path, monkeypatch, entries=WRITTEN) -> str:
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    monkeypatch.setenv("LJS_PROFILE", prof)
    person.reset()
    profile_set.set_line("search.py", "BAR_DECLINED", dict(entries))
    return prof


def _row(n, company):
    return {"title": "Data Analyst", "company": company, "date": "2026-10-30",
            "first_seen": "2026-10-30", "portal": "linkedin", "desc": "SQL and Python.",
            "location": "Manchester, England, United Kingdom",
            "url": f"https://jobs.example/{n}", "fit": 80, "priority": 80}


POSTED_AS = ("North-Shore Mutual", "Acme Insurance Company",
             "Acme Assurance et services financiers", "Brindle and Hart Ltd")


def test_the_bar_turns_each_down_however_the_entry_is_written(tmp_path, monkeypatch):
    """The bar a round, networking and the brief read (bar.py, its list read when it starts)."""
    prof = _profile(tmp_path, monkeypatch)
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bar.py"), *POSTED_AS],
                         capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert len(lines) == len(POSTED_AS), out.stdout
    for name, line in zip(POSTED_AS, lines):
        assert line.startswith(name) and " excluded " in line, line
    assert "not North-Shore" in lines[0] and "no Acme, any of it" in lines[2]


def test_the_search_leaves_each_out_as_it_cuts_and_as_the_page_reads_it(tmp_path, monkeypatch,
                                                                        judged):
    """The cut a search makes and the page's Found list read the list from the file, as it
    stands (run_round.declined_now): an entry written by hand cut nothing there either."""
    _profile(tmp_path, monkeypatch)
    import run_round
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    cut = run_round.hard_rules(14, TODAY, str(seen))
    page = run_round.page_rules(TODAY, seen=str(seen))
    for n, name in enumerate(POSTED_AS, 1):
        assert cut(_row(n, name)).startswith("candidate's bar:"), name
        assert page(_row(n, name)).startswith("candidate's bar:"), name
    assert cut(_row(9, "Kestrel Mutual")) == ""            # nobody else is touched


def test_an_entry_written_by_hand_comes_off_your_rules_and_goes_back(tmp_path, monkeypatch):
    """Your rules lists each employer once, by its key; its bin takes the entry off however it
    was written, and the undo puts it back. Turning the employer down again on the page finds
    it already there and writes no second entry."""
    _profile(tmp_path, monkeypatch, {"north-shore mutual": "candidate declined it 2026-11-01"})
    import app_actions
    import rules_view
    from test_left_out_jobs_are_read_by_rule_and_rules_can_change import _run
    rows = [r for r in rules_view.your_rules(person.today(), {}) if r["kind"] == "declined"]
    assert [r["drop"]["key"] for r in rows] == ["north shore mutual"], rows
    assert app_actions._decline_employer("North-Shore Mutual", "not for me", TODAY) == ""
    assert list(profile_set.get("search.py", "BAR_DECLINED")) == ["north-shore mutual"]
    got = app_actions._rule_drop(_run("rule.drop", {"kind": "your_rule", "id": rows[0]["id"],
                                                    "drop": rows[0]["drop"]}))
    assert profile_set.get("search.py", "BAR_DECLINED") == {}
    app_actions._rule_undrop(_run("rule.undrop", {}, got["undo"]["value"]))
    back = profile_set.get("search.py", "BAR_DECLINED")
    assert list(back) == ["north shore mutual"], back
    assert json.dumps(back["north shore mutual"]).find("2026-11-01") > 0
