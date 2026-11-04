"""A job the person sets aside while a search runs never comes back on its shortlist.

The helper chat's report of 2 November: a search running while the person set jobs aside
on the page listed them again, and `--show N` counted them toward N with nothing taken in
their place. The shortlist is cut with the rulings read as they stand when it is cut, the
next row taken for each one passed over; the person's own Set asides hold even when a round
looks again at what a rule decided (--no-seen-read); and a Set aside still waiting on the
page, not yet applied, is read from a page dump (`--dump`) when the round is cut again at
its end. Invented employers only.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import exclude  # noqa: E402
import run_round  # noqa: E402
from test_a_shortlist_of_n_is_refilled import TODAY, _row  # noqa: E402

ROWS = [_row(1, "Fernhill Freight"), _row(2, "Larkspur Retail"), _row(3, "Kestrel Mutual"),
        _row(4, "Brackenhollow Foods"), _row(5, "Quillon Data")]


def _companies(summ, name="r1"):
    return [r["company"] for r in json.loads((summ / f"{name}.json").read_text("utf-8"))]


def _round(tmp_path, monkeypatch, during=None, *extra):
    """run_round.main() with every stage stubbed: the ranked shortlist is ROWS, and
    `during(seen)` runs once the ranking is done and before the cut, as a Set aside
    applied on the page while the round ran."""
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")

    def stage(cmd, log, deadline=None, ok=(0,)):
        if os.path.basename(cmd[1]) == "throttle.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ROWS, fh)
            if during:
                during(str(seen))

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd: 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    summ = tmp_path / "summ"
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                      "--from-scraped", str(scraped), "--seen", str(seen),
                                      "--summary-dir", str(summ), "--today", TODAY,
                                      "--jobage", "14", "--pages", "1", *extra])
    run_round.main()
    return summ, seen


def _set_aside(url, company):
    def write(seen):
        exclude.add(url, "not for me (said on the page)", "Data Analyst", company,
                    basis="person", today=TODAY, path=seen)
    return write


def test_a_set_aside_applied_while_the_round_ran_is_passed_over_and_the_list_topped_up(
        tmp_path, monkeypatch, judged):
    """Already so in this build (run_round.main makes hard_rules when it cuts the shortlist):
    held here so it stays so."""
    summ, _ = _round(tmp_path, monkeypatch, _set_aside("https://jobs.example/1", "Fernhill Freight"),
                     "--show", "3")
    assert _companies(summ) == ["Larkspur Retail", "Kestrel Mutual", "Brackenhollow Foods"]


def test_no_more_roles_from_an_employer_said_while_the_round_ran_is_passed_over(
        tmp_path, monkeypatch, judged):
    """The bar keeps the profile it read when the round started; the cut reads the employers
    turned down by name as they stand when it cuts."""
    import app_state
    import profile_set
    from company_key import key as company_key
    monkeypatch.setenv("LJS_PROFILE", app_state.profile_copy(str(tmp_path / "profile")))

    def decline(_seen):
        have = dict(profile_set.get("search.py", "BAR_DECLINED") or {})
        have[company_key("Larkspur Retail")] = "turned down on the page, 2026-11-03: not for me"
        profile_set.set_line("search.py", "BAR_DECLINED", have)

    summ, _ = _round(tmp_path, monkeypatch, decline, "--show", "3")
    assert _companies(summ) == ["Fernhill Freight", "Kestrel Mutual", "Brackenhollow Foods"]


def test_the_persons_own_set_aside_holds_when_a_round_looks_again_at_the_rules(
        tmp_path, monkeypatch, judged):
    summ, _ = _round(tmp_path, monkeypatch, _set_aside("https://jobs.example/2", "Larkspur Retail"),
                     "--show", "3", "--no-seen-read")
    assert _companies(summ) == ["Fernhill Freight", "Kestrel Mutual", "Brackenhollow Foods"]


def _dump(tmp_path, *docs):
    """A page dump: `docs` as (collection, id, fields)."""
    d = tmp_path / "dump"
    for coll, doc_id, fields in docs:
        (d / coll).mkdir(parents=True, exist_ok=True)
        (d / coll / (doc_id.replace("~", "@") + ".json")).write_text(
            json.dumps(dict(fields, _v=1)), encoding="utf-8")
    return str(d)


def _tap(n, company, item, aid, minute, action="job.dismiss", **more):
    rev = app_model.job_rev(f"https://jobs.example/{n}", company, "Data Analyst", "new")
    return ("actions", aid, dict({"action": action, "item": item, "rev_seen": rev,
                                  "at": f"2026-11-03T10:{minute:02d}:00Z", "tab": "t1"}, **more))


def test_a_set_aside_still_waiting_on_the_page_is_passed_over_when_the_round_is_cut_again(
        tmp_path, monkeypatch, judged, capsys):
    summ, seen = _round(tmp_path, monkeypatch, None, "--show", "3")
    assert _companies(summ) == ["Fernhill Freight", "Larkspur Retail", "Kestrel Mutual"]
    # Set aside on the page while it ran, under an id from the round before: not applied yet.
    dump = _dump(tmp_path, _tap(2, "Larkspur Retail", "r0-7", "act~a", 1),
                 _tap(1, "Fernhill Freight", "r1-1", "act~b", 2),
                 ("receipts", "act~b", {"result": "ok"}),          # applied: seen holds it
                 _tap(3, "Kestrel Mutual", "r1-3", "act~c", 3),
                 ("actions", "act~d", {"action": "undo", "undoes": "act~c", "item": "r1-3",
                                       "at": "2026-11-03T10:04:00Z", "tab": "t1"}))
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"), "--recut",
                                      "--show", "3", "--seen", str(seen), "--summary-dir",
                                      str(summ), "--today", TODAY, "--jobage", "14",
                                      "--dump", dump])
    assert run_round.main() == 0
    # Larkspur's tap waits: passed over. Fernhill's was applied (its ruling is in the seen
    # file once applied, not in this test's), Kestrel's was taken back: both stay.
    assert _companies(summ) == ["Fernhill Freight", "Kestrel Mutual", "Brackenhollow Foods"]
    assert "Larkspur Retail (set aside on your page)" in capsys.readouterr().out
