"""What the person wants from a search is kept in one record, with their words, the day and
whether it cuts or only ranks, and every part of the search reads it.

From the job search audit (issue 313, its redesign; issue 307; issue 327, part 1): the person's
wants lived in a dozen settings, each read on its own, so one spoken "no" was carried into
several of them by hand and a missed one went on working against them. Now the employers and
kinds of employer turned down, and the employers wanted with their lift, are kept in
profile/wants.json; the bar and the tier lifts are compiled from it, with anything still
written the old way; what is searched by name and whose job sites are read are checked against
it; and an existing install's settings move into it by themselves, every verdict the same.
Invented employers and kinds only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
import person  # noqa: E402
import profile_set  # noqa: E402

TODAY = "2026-11-17"
EMPLOYERS = '''
TIER_1 = {"wexford capital", "kestrel mutual"}
TIER_2 = {  # major brands
    "oakmere foods",  # a grocer with a strong pay band
    "Brindle Bank",
}
YC_AND_BACKED = {"vintry labs", "oakmere foods"}
TIER_3 = {"saltmarsh analytics", "harbourline pension plan"}
NOT_TECH = {"northwind pensions": "pension fund", "harbourline pension plan": "pension fund",
            "kestrel mutual": "insurer", "oakmere foods": "grocer"}
'''
# Written by hand over months, as one person's was: a legal form, a second entry for the same
# employer, a reason in no particular form, and a kind written in the plural.
DECLINED = {"Kestrel Mutual Ltd": "candidate declined it 2026-11-01: \"not Kestrel\"",
            "kestrel mutual": "a second entry for it, never read",
            "Harrow Bank": "turned down in a chat, 2026-11-10: \"no Harrow\""}
SECTORS = {"Pension Funds": "turned down in a chat, 2026-11-09: \"no pension funds\""}
NAMES = ["Kestrel Mutual", "Kestrel Mutual plc", "Harrow Bank", "Harrow Bank Group",
         "Northwind Pensions", "Harbourline Pension Plan", "Wexford Capital", "Oakmere Foods",
         "Vintry Labs", "Saltmarsh Analytics", "Brindle Bank", "Quorlan Media"]
DECIDES = """
import json, sys
sys.path.insert(0, "tools")
import bar, opportunity, run_round, wants
names = json.loads(sys.argv[1])
print(json.dumps({
    "verdict": {n: list(bar.verdict(n)) for n in names},
    "by_name": {n: bar.excluded_by_name(n) for n in names},
    "tier": {n: list(opportunity.tier(n)) for n in names},
    "sets": {s: sorted(getattr(opportunity, s)) for s in ("TIER_1", "TIER_2", "YC_AND_BACKED",
                                                         "TIER_3")},
    "declined": run_round.declined_now(), "kinds": wants.sectors_out(),
    "out_fn": {n: wants.out_fn()(n) for n in names}}, sort_keys=True))
"""


def _profile(tmp_path, monkeypatch, declined=None, sectors=None) -> str:
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", str(state))
    person.reset()
    with open(os.path.join(prof, "employers.py"), "a", encoding="utf-8") as fh:
        fh.write(EMPLOYERS)
    person.reset()
    if declined:
        profile_set.set_line("search.py", "BAR_DECLINED", dict(declined))
    if sectors:
        profile_set.set_line("search.py", "BAR_SECTORS_OUT", dict(sectors))
    return prof


def _run(prof, tmp_path, *argv) -> subprocess.CompletedProcess:
    env = dict(os.environ, LJS_PROFILE=prof, LJS_STATE=str(tmp_path / "state"), PYTHONUTF8="1")
    return subprocess.run([sys.executable, *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=ROOT)


def _decides(prof, tmp_path) -> dict:
    """Everything the settings decide, read by a fresh process, as a round reads them."""
    got = _run(prof, tmp_path, "-c", DECIDES, json.dumps(NAMES))
    assert got.returncode == 0, got.stdout + got.stderr
    return json.loads(got.stdout)


def _files(prof) -> dict:
    out = {}
    for n in ("search.py", "employers.py", "wants.json"):
        p = os.path.join(prof, n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                out[n] = fh.read()
    return out


# ------------------------------------------------------------------ an existing install

def test_the_old_settings_move_into_one_record_and_every_verdict_is_as_before(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, DECLINED, SECTORS)
    before = _decides(prof, tmp_path)
    assert before["verdict"]["Harrow Bank Group"][0] == "excluded"
    assert before["tier"]["Wexford Capital"][0] == 30
    import profile_upgrades
    up = profile_upgrades.by_id("wants-moved")
    assert up.cost == "instant" and up.needs == "nobody"
    assert up.pending().startswith("12 of your settings on employers you want or turned down")
    got = _run(prof, tmp_path, *up.command[1:])
    assert got.returncode == 0, got.stdout + got.stderr
    person.reset()
    assert up.pending() == ""
    # Every verdict, lift, reason and list the same, read the way every stage reads them.
    assert _decides(prof, tmp_path) == before

    # One record, with the person's words and the day each was said; the settings stay, empty.
    with open(os.path.join(prof, "wants.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    harrow = rec["employers"]["Harrow Bank"]
    assert (harrow["want"], harrow["hard"], harrow["said"], harrow["date"]) == (
        "out", True, "no Harrow", "2026-11-10")
    assert rec["employers"]["Kestrel Mutual Ltd"]["date"] == "2026-11-01"
    assert rec["kinds"]["pension fund"]["said"] == "no pension funds"
    oak = rec["employers"]["oakmere foods"]
    assert (oak["want"], oak["hard"], oak["tiers"]) == ("in", False, ["TIER_2", "YC_AND_BACKED"])
    assert oak["said"] == "a grocer with a strong pay band"       # its note went with it
    assert profile_set.get("search.py", "BAR_DECLINED") == {}
    assert profile_set.get("search.py", "BAR_SECTORS_OUT") == {}
    for s in ("TIER_1", "TIER_2", "YC_AND_BACKED", "TIER_3"):
        assert profile_set.get("employers.py", s) == set(), s
    assert "NOT_TECH" in _files(prof)["employers.py"]

    # Safe to run again: nothing moves, nothing changes.
    kept = _files(prof)
    got = _run(prof, tmp_path, *up.command[1:])
    assert got.returncode == 0 and "nothing is left to move" in got.stdout, got.stdout
    assert _files(prof) == kept


def test_a_move_that_would_change_what_the_settings_decide_puts_every_file_back(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, DECLINED, SECTORS)
    kept = _files(prof)
    import wants
    seen = iter([("before",), ("after",)])
    monkeypatch.setattr(wants, "_effect", lambda: next(seen))
    with pytest.raises(wants.Refused) as e:
        wants.move(TODAY)
    assert "nothing was moved" in str(e.value)
    person.reset()
    assert _files(prof) == kept and "wants.json" not in kept


def test_a_setting_written_as_code_is_read_with_the_record_and_left_where_it_is(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, DECLINED)
    path = os.path.join(prof, "employers.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace('TIER_3 = {"saltmarsh analytics", "harbourline pension plan"}',
                              'TIER_3 = {"saltmarsh analytics"} | {"harbourline pension plan"}'))
    person.reset()
    before = _decides(prof, tmp_path)
    import wants
    assert "TIER_3" not in wants.to_move()
    assert wants.move(TODAY)["moved"]
    person.reset()
    assert _decides(prof, tmp_path) == before
    assert wants.to_move() == {}
    assert '{"saltmarsh analytics"} | {"harbourline pension plan"}' in _files(prof)["employers.py"]


# ------------------------------------------------------------------ said once, read everywhere

def test_a_no_said_once_is_kept_in_the_record_and_every_stage_cuts_by_it(tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch)
    got = _run(prof, tmp_path, os.path.join("tools", "wants.py"), "decline", "Harrow Bank",
               "--said", "not Harrow, ever", "--today", TODAY)
    assert got.returncode == 0, got.stdout + got.stderr
    person.reset()
    assert profile_set.get("search.py", "BAR_DECLINED") is profile_set.MISSING
    decides = _decides(prof, tmp_path)
    assert decides["verdict"]["Harrow Bank Group"] == [
        "excluded", "turned down in a chat, 2026-11-17: \"not Harrow, ever\""]
    assert decides["out_fn"]["Harrow Bank"]
    # The round's own cut, read as it stands when the list is cut.
    import run_round
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    cut = run_round.hard_rules(14, TODAY, str(seen))
    row = {"title": "Data Analyst", "company": "Harrow Bank", "date": TODAY,
           "first_seen": TODAY, "desc": "SQL.", "location": "Manchester, England, United Kingdom",
           "url": "https://jobs.example/1", "fit": 80, "priority": 80}
    assert "not Harrow, ever" in cut(row)
    assert cut(dict(row, company="Oakmere Foods", url="https://jobs.example/2")) == ""
    got = _run(prof, tmp_path, os.path.join("tools", "wants.py"), "show")
    assert "no Harrow Bank: not Harrow, ever (2026-11-17)" in got.stdout, got.stdout


def test_a_yes_said_once_lifts_every_job_there_and_is_taken_back_the_same_way(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, DECLINED)
    wants_py = os.path.join("tools", "wants.py")
    got = _run(prof, tmp_path, wants_py, "want", "Quorlan Media", "--tier", "2", "--said",
               "they pay well and finish at five", "--today", TODAY)
    assert got.returncode == 0 and "lifted +20" in got.stdout, got.stdout + got.stderr
    decides = _decides(prof, tmp_path)
    assert decides["tier"]["Quorlan Media"][0] == 20
    assert decides["verdict"]["Quorlan Media"][0] == "prestige"
    with open(os.path.join(prof, "wants.json"), encoding="utf-8") as fh:
        entry = json.load(fh)["employers"]["quorlan media"]
    assert entry["said"] == "they pay well and finish at five" and entry["date"] == TODAY
    # A yes to an employer turned down is refused, naming how to take the no back.
    got = _run(prof, tmp_path, wants_py, "want", "Harrow Bank", "--tier", "1")
    assert got.returncode == 2 and "undecline" in got.stdout, got.stdout
    got = _run(prof, tmp_path, wants_py, "unwant", "Quorlan Media")
    assert got.returncode == 0 and "no longer lifted" in got.stdout, got.stdout
    assert _decides(prof, tmp_path)["tier"]["Quorlan Media"][0] == 0


def test_a_lift_the_record_keeps_for_an_employer_turned_down_is_named_tidied_and_put_back(
        tmp_path, monkeypatch):
    """Moved, an employer both lifted and turned down keeps both, as it decided before; the
    check names the lift, turning it down again takes it off, and taking the no back restores
    it."""
    prof = _profile(tmp_path, monkeypatch)
    import wants
    wants.move(TODAY)
    person.reset()
    assert wants.drift() == []
    wants.decline("Kestrel Mutual", "no insurers", TODAY)
    with open(os.path.join(prof, "wants.json"), encoding="utf-8") as fh:
        k = json.load(fh)["employers"]["kestrel mutual"]
    assert k["want"] == "out" and "tiers" not in k
    assert wants.drift() == []
    wants.undecline("Kestrel Mutual")
    with open(os.path.join(prof, "wants.json"), encoding="utf-8") as fh:
        k = json.load(fh)["employers"]["kestrel mutual"]
    assert k["want"] == "in" and k["tiers"] == ["TIER_1"]
    # A lift left on a "no" (a merge of two chats) is named, and tidy takes it off.
    rec = wants.load()
    rec["employers"]["harrow bank"] = {"want": "out", "hard": True, "why": "no Harrow",
                                       "said": "no Harrow", "date": TODAY, "by": "chat",
                                       "tiers": ["TIER_2"]}
    wants._save(rec)
    found = wants.drift()
    assert [(f["file"], f["setting"], f["entry"]) for f in found] == [
        ("profile/wants.json", "TIER_2", "harrow bank")]
    wants.tidy()
    assert wants.drift() == [] and "tiers" not in wants.load()["employers"]["harrow bank"]


def test_two_chats_each_turning_one_employer_down_keep_both(tmp_path):
    """The record merges key by key between two chats (merge_state), so neither "no" is lost."""
    import merge_state
    base = {"employers": {}, "kinds": {}}
    ours = {"employers": {"harrow bank": {"want": "out", "hard": True, "why": "no Harrow",
                                          "said": "no Harrow", "date": TODAY, "by": "chat"}},
            "kinds": {}}
    theirs = {"employers": {"quorlan media": {"want": "out", "hard": True, "why": "no Quorlan",
                                              "said": "no Quorlan", "date": TODAY,
                                              "by": "page"}},
              "kinds": {}}
    paths = []
    for name, data in (("o", base), ("a", ours), ("b", theirs)):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(str(p))
    code = merge_state.main([*paths, "profile/wants.json"])
    assert code == 0
    got = json.loads(open(paths[1], encoding="utf-8").read())
    assert set(got["employers"]) == {"harrow bank", "quorlan media"}
