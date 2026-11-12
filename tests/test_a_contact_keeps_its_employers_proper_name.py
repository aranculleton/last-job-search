"""A contact a people run adds keeps its employer's proper name, never the lower-case key.

Seen on the maintainer's page, 2026-11-12: the people the day's runs had just added read
"<first name> at <employer in lower case>" while the older ones read the employer's proper
name. The employer lists a run searches (employers.py TIER_1 and the rest) are written as
lower-case keys, `candidates.py employers` handed those on as the names to search, and the
contact book was written with them. Now every row a run adds carries the proper name: the
one LinkedIn showed on the person's card, else the spelling the person's own records use,
else the name written properly; and a one-off repair puts it back on rows already written
(Profile upgrade: `employer-names`). Invented people and employers only.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import state  # noqa: E402
from test_a_people_run_reaches_the_people_who_answer import (  # noqa: E402
    COLS, ENG_EMP, ENG_NET, _book, _check, _cli, _env, _p, _profile, _rows)

TODAY = datetime.date(2026, 11, 12)


def test_the_proper_name_is_the_one_shown_else_the_books_else_written_properly():
    book = [{"contact_id": "a", "name": "Ama Rhodes", "company": "Kestrel Mutual"},
            {"contact_id": "b", "name": "Bex Torrance", "company": "Kestrel Mutual"},
            {"contact_id": "c", "name": "Cy Wardle", "company": "kestrel mutual"}]
    assert state.employer_display("kestrel mutual", book) == "Kestrel Mutual"
    # What LinkedIn showed on their own card comes first.
    assert state.employer_display("qxb labs", book, also=["QXB Labs"]) == "QXB Labs"
    # Nothing known: written properly, a short name in capitals.
    assert state.employer_display("orchard & vane inc.", book) == "Orchard & Vane Inc."
    assert state.employer_display("qxb", book) == "QXB"
    # A name written with capitals is the person's own spelling, kept as it is.
    assert state.employer_display("deVane Analytics", book) == "deVane Analytics"
    # And every row added gets it.
    row, how = state.add_contact(book, "Ivo Marr", "kestrel mutual", TODAY)
    assert how == "added" and row["company"] == "Kestrel Mutual"
    assert row["company_key"] == state.company_key("Kestrel Mutual")


def test_a_people_run_adds_its_people_with_the_employers_proper_name(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [])
    # The run searched the employer by its lower-case key, as the employer list holds it.
    people = [_p("Ivo Marr", "Engineering Manager at Nimbus Cloud", "nimbus cloud"),
              _p("Tova Fenn", "Head of Engineering", "thornbury games")]
    _check(tmp_path, people, "--want", "2", "--add")
    by = {r["name"]: r["company"] for r in _rows(tmp_path)}
    assert by == {"Ivo Marr": "Nimbus Cloud", "Tova Fenn": "Thornbury Games"}
    # The employers it names to search next are named properly too.
    out = _cli(tmp_path, "employers", "--used", "Nimbus Cloud", ok=(0, 1))
    assert "thornbury games" not in out and "larkspur systems" not in out


def test_the_repair_restores_proper_names_on_rows_already_written(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "a", "name": "Ama Rhodes", "company": "Kestrel Mutual"},
        {"contact_id": "b", "name": "Bex Torrance", "company": "kestrel mutual"},
        {"contact_id": "c", "name": "Cy Wardle", "company": "orchard & vane inc."},
        {"contact_id": "d", "name": "Dee Hollis", "company": "Fernhill Freight"},
    ])
    env = _env(tmp_path)
    import profile_upgrades as U
    up = next(u for u in U.REGISTRY if u.id == "employer-names")
    assert up.cost == "instant" and "network_contacts.csv" in up.paths

    def pending():
        code = ("import sys; sys.path[:0] = ['tools', 'tools/network']; import profile_upgrades "
                "as U; print(json.dumps(next(u for u in U.REGISTRY if u.id == "
                "'employer-names').pending()))")
        r = subprocess.run([sys.executable, "-c", "import json; " + code], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr[-800:]
        return json.loads(r.stdout)

    assert "2 contact" in pending()
    r = subprocess.run([sys.executable, *up.command[1:]], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    by = {row["contact_id"]: row["company"] for row in _rows(tmp_path)}
    assert by == {"a": "Kestrel Mutual", "b": "Kestrel Mutual", "c": "Orchard & Vane Inc.",
                  "d": "Fernhill Freight"}
    assert pending() == ""
    with open(tmp_path / "state" / "network_contacts.csv", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh))[1]["name"] == "Bex Torrance"


def test_the_page_shows_the_display_column():
    with open(os.path.join(ROOT, "tools", "app_model.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert '"employer": str(c.get("company") or "")' in text
    assert '"employer": str(c.get("company_key")' not in text
    assert COLS
