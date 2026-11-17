"""What a person turned down is followed by every part of the search, from one command.

From one evening of one person's search (issue 307): a "no" to a whole sector became about 40
employer names written by hand into BAR_DECLINED, and the lists that lift or search an
employer were edited by hand beside it, some of them missed. After every edit the tier sets
still lifted four employers the person had turned down, one of their own job sites was read
every round, and a round started before the edits asked six declined employers' boards for
jobs the bar then cut. Nothing checked one setting against another.

Now one command turns an employer, or a kind of employer, down everywhere at once (the
page's turn-down goes through it too), refusing a form the bar would never match; a kind is
one rule on what the employer is; a round asks nothing of what is turned down and says what
it searches with first; a check names every line still searching or lifting something turned
down; and an existing install is put right by a profile upgrade that touches nothing else.
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
TIER_2 = {  # major brands
    "kestrel mutual",
    "northwind pensions",  # a pension fund
    "oakmere foods",
}
TIER_3 = {"saltmarsh analytics", "harbourline pension plan"}
NOT_TECH = {"northwind pensions": "pension fund", "harbourline pension plan": "pension fund",
            "kestrel mutual": "insurer", "oakmere foods": "grocer"}
'''
BOARDS = '''BOARDS: dict[str, tuple[str, str]] = {
    "Kestrel Mutual": ("workday", "kestrel.wd3/Careers"),  # checked
    "Oakmere Foods": ("greenhouse", "oakmere"),
}'''


def _profile(tmp_path, monkeypatch, declined=None, sectors=None, extra_search="") -> str:
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", str(state))
    person.reset()
    with open(os.path.join(prof, "employers.py"), "a", encoding="utf-8") as fh:
        fh.write(EMPLOYERS)
    path = os.path.join(prof, "boards.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("BOARDS: dict[str, tuple[str, str]] = {}", BOARDS))
    path = os.path.join(prof, "search.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("SCRAPE_EMPLOYERS = []",
                        'SCRAPE_EMPLOYERS = ["Kestrel Mutual", "Oakmere Foods", '
                        '"Harbourline Pension Plan"]')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + extra_search)
    person.reset()
    if declined is not None:
        profile_set.set_line("search.py", "BAR_DECLINED", dict(declined))
    if sectors is not None:
        profile_set.set_line("search.py", "BAR_SECTORS_OUT", dict(sectors))
    return prof


def _env(prof, state=None) -> dict:
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    if state:
        env["LJS_STATE"] = state
    return env


def _run(prof, *argv, state=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=_env(prof, state), cwd=ROOT)


def _read(prof, name) -> str:
    with open(os.path.join(prof, name), encoding="utf-8") as fh:
        return fh.read()


HAND = {"kestrel mutual": "candidate declined it 2026-11-01: \"not Kestrel\""}


def _declined() -> dict:
    """The employers turned down, as the record of what the person wants holds them (issue 327):
    the one place a "no" is written now."""
    import wants
    return wants.held_declined()


def _kinds() -> dict:
    import wants
    return wants.held_kinds()


def _was(text: str, setting: str):
    """A setting's value in a profile file's text as it was."""
    import ast
    n = profile_set._node(ast.parse(text), setting)
    return ast.literal_eval(n.value)


# ------------------------------------------------------------------ a round asks for nothing turned down

def test_a_round_asks_no_declined_employer_by_name_nor_reads_its_own_job_site(tmp_path,
                                                                              monkeypatch):
    _profile(tmp_path, monkeypatch, declined=HAND)
    import ats_boards
    import scrape_wide
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", ["Kestrel Mutual", "Oakmere Foods"])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_QUERIES", ["data analyst"])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_LOCATIONS", ["United Kingdom"])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_REMOTE", [])
    asked = [t[1] for t in scrape_wide.build_tasks({"linkedin-search": True}, 1)]
    assert "Oakmere Foods data analyst" in asked
    assert not any("Kestrel" in q for q in asked), asked
    named = [t[1] for t in scrape_wide.named_tasks({"linkedin-search": True}, 1,
                                                   ["Kestrel Mutual", "Oakmere Foods"])]
    assert named and not any("Kestrel" in q for q in named), named

    monkeypatch.setattr(ats_boards, "BOARDS", {"Kestrel Mutual": ("workday", "k.wd3/C"),
                                               "Oakmere Foods": ("greenhouse", "oakmere")})
    read = {}

    def fetch_all(boards=None, notes=None, today=None, **_):
        read.update(boards if boards is not None else ats_boards.BOARDS)
        return [], {}
    monkeypatch.setattr(ats_boards, "fetch_all", fetch_all)
    scrape_wide._employer_boards(None)
    assert set(read) == {"Oakmere Foods"}, read


def test_a_whole_scrape_reads_no_declined_employers_job_site_and_counts_it_in_none(
        tmp_path, monkeypatch):
    """The scrape itself, from its own command: the declined employer's board is never asked,
    and the count of boards the search says it read leaves it out."""
    _profile(tmp_path, monkeypatch, declined=HAND)
    import ats_boards
    import portals
    import scrape_wide
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(portals, "SKILLS", str(tmp_path / "skills"))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["planner"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(ats_boards, "BOARDS", {"Kestrel Mutual": ("workday", "k.wd3/C"),
                                               "Oakmere Foods": ("greenhouse", "oakmere")})
    asked = {}

    def fetch_all(boards=None, notes=None, today=None, report=None, **_):
        asked.update(boards if boards is not None else ats_boards.BOARDS)
        return [], {"Oakmere Foods": "resolved, but nothing matching the location filter"}
    monkeypatch.setattr(ats_boards, "fetch_all", fetch_all)
    portals.cli.cache_clear()
    out = tmp_path / "00_scrape"
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--today", TODAY,
                                      "--skip-canary", "--workers", "2"])
    try:
        scrape_wide.main()
    finally:
        portals.cli.cache_clear()
    assert set(asked) == {"Oakmere Foods"}, asked
    assert json.load(open(out / "sources.json", encoding="utf-8"))["boards"]["boards"] == 1


# ------------------------------------------------------------------ a kind turned down is one rule

def test_a_kind_turned_down_cuts_every_employer_of_that_kind_by_one_rule(tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch,
                    sectors={"pension funds": "turned down in a chat, 2026-11-17: \"no pension "
                                              "funds\""})
    got = _run(prof, os.path.join("tools", "bar.py"), "Northwind Pensions",
               "Harbourline Pension Plan", "Oakmere Foods")
    lines = got.stdout.splitlines()
    assert got.returncode == 0 and len(lines) == 3, got.stdout + got.stderr
    assert " excluded " in lines[0] and "pension fund" in lines[0], lines[0]
    assert " excluded " in lines[1], lines[1]
    assert " excluded " not in lines[2], lines[2]
    # An employer the catalogue does not hold, by its own posting saying what it is; a posting
    # naming the kind as its clients is about the clients.
    code = ("import bar\n"
            "print(bar.verdict('Brackwater Trust', 'Brackwater Trust is one of the largest "
            "pension funds in the north.')[0])\n"
            "print(bar.verdict('Quayside Analytics', 'We build models for pension funds and "
            "banks.')[0])\n")
    got = _run(prof, "-c", "import sys; sys.path.insert(0, 'tools')\n" + code)
    assert got.stdout.split() == ["excluded", "none"], got.stdout + got.stderr


def test_a_kind_turned_down_while_a_round_runs_is_cut_by_its_list(tmp_path, monkeypatch):
    """The cut reads the setting as it stands when the list is cut, as it does for employers
    turned down by name: the bar keeps the copy read when the round started."""
    _profile(tmp_path, monkeypatch, sectors={"pension fund": "turned down in a chat"})
    import run_round
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    cut = run_round.hard_rules(14, TODAY, str(seen))
    row = {"title": "Data Analyst", "company": "Northwind Pensions", "date": TODAY,
           "first_seen": TODAY, "desc": "SQL.", "location": "Manchester, England, United Kingdom",
           "url": "https://jobs.example/1", "fit": 80, "priority": 80}
    assert cut(row).startswith("candidate's bar: a kind of employer you turned down (pension "
                               "fund)"), cut(row)
    assert cut(dict(row, company="Oakmere Foods", url="https://jobs.example/2")) == ""


# ------------------------------------------------------------------ one writer, every setting

def test_one_command_turns_an_employer_down_everywhere_and_undo_puts_every_part_back(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch)
    before = {n: _read(prof, n) for n in ("employers.py", "boards.py", "search.py")}
    got = _run(prof, os.path.join("tools", "wants.py"), "decline", "Kestrel Mutual",
               "--said", "not Kestrel, ever", "--today", TODAY, state=str(tmp_path / "state"))
    assert got.returncode == 0, got.stdout + got.stderr
    person.reset()
    assert _declined() == {
        "kestrel mutual": "turned down in a chat, 2026-11-17: \"not Kestrel, ever\""}
    # Kept in the one record, with the person's words and the day; never in the old setting.
    import wants
    assert wants.load()["employers"]["kestrel mutual"]["said"] == "not Kestrel, ever"
    assert profile_set.get("search.py", "BAR_DECLINED") is profile_set.MISSING
    assert "kestrel mutual" not in profile_set.get("search.py", "SCRAPE_EMPLOYERS")
    assert "Kestrel Mutual" not in profile_set.get("search.py", "SCRAPE_EMPLOYERS")
    assert "Kestrel Mutual" not in profile_set.get("boards.py", "BOARDS")
    employers = _read(prof, "employers.py")
    assert "kestrel mutual\"," not in employers.split("NOT_TECH")[0]
    # Every other entry and every comment stays where the person wrote it.
    assert "# major brands" in employers and "# a pension fund" in employers
    assert "Oakmere Foods" in profile_set.get("boards.py", "BOARDS")
    assert "# checked" not in _read(prof, "boards.py")       # its own line went with it
    notes = _read(prof, "CLAUDE.md")
    deal = notes.split("### Deal-breakers", 1)[1].split("\n## ", 1)[0]
    assert "No roles at Kestrel Mutual" in deal and "not Kestrel, ever" in deal
    got = _run(prof, os.path.join("tools", "wants.py"), "check", state=str(tmp_path / "state"))
    assert got.returncode == 0, got.stdout

    got = _run(prof, os.path.join("tools", "wants.py"), "undecline", "Kestrel Mutual",
               state=str(tmp_path / "state"))
    assert got.returncode == 0, got.stdout + got.stderr
    person.reset()
    assert _declined() == {}
    for name, setting in (("employers.py", "TIER_2"), ("boards.py", "BOARDS"),
                          ("search.py", "SCRAPE_EMPLOYERS")):
        assert set(profile_set.get(name, setting)) == set(
            _was(before[name], setting)), name
    assert "# major brands" in _read(prof, "employers.py")
    assert "No roles at Kestrel Mutual" not in _read(prof, "CLAUDE.md")


def test_the_pages_turn_down_goes_through_the_same_command(tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch)
    import app_actions
    k = app_actions._decline_employer("Kestrel Mutual", "no more roles from them", TODAY)
    assert k == "kestrel mutual"
    person.reset()
    assert _declined() == {
        "kestrel mutual": "turned down on the page, 2026-11-17: no more roles from them"}
    assert "Kestrel Mutual" not in profile_set.get("boards.py", "BOARDS")
    assert "\"kestrel mutual\"," not in _read(prof, "employers.py").split("NOT_TECH")[0]
    app_actions._undecline(k)
    person.reset()
    assert "Kestrel Mutual" in profile_set.get("boards.py", "BOARDS")
    assert "\"kestrel mutual\"," in _read(prof, "employers.py").split("NOT_TECH")[0]


def test_a_kind_turned_down_takes_its_employers_off_the_lists_and_comes_off_your_rules(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch)
    import app_actions
    import rules_view
    import wants
    from test_left_out_jobs_are_read_by_rule_and_rules_can_change import _run as act
    got = wants.sector_out("Pension Funds", "no pension funds", TODAY)
    assert got["kind"] == "pension fund" and got["added"]
    assert got["covers"] == ["harbourline pension plan", "northwind pensions"]
    person.reset()
    assert _kinds() == {
        "pension fund": "turned down in a chat, 2026-11-17: \"no pension funds\""}
    assert "Harbourline Pension Plan" not in profile_set.get("search.py", "SCRAPE_EMPLOYERS")
    employers = _read(prof, "employers.py").split("NOT_TECH")[0]
    assert "northwind pensions" not in employers and "harbourline" not in employers
    assert "Kestrel Mutual" in profile_set.get("search.py", "SCRAPE_EMPLOYERS")
    rows = [r for r in rules_view.your_rules(person.today(), {})
            if (r.get("drop") or {}).get("kind") == "sector_out"]
    assert [r["sentence"] for r in rows] == ["No roles at any pension fund: \"no pension "
                                             "funds\"."], rows
    done = app_actions._rule_drop(act("rule.drop", {"kind": "your_rule", "id": rows[0]["id"],
                                                    "drop": rows[0]["drop"]}))
    person.reset()
    assert _kinds() == {}
    assert "northwind pensions" in _read(prof, "employers.py").split("NOT_TECH")[0]
    app_actions._rule_undrop(act("rule.undrop", {}, done["undo"]["value"]))
    person.reset()
    assert list(_kinds()) == ["pension fund"]
    assert "northwind pensions" not in _read(prof, "employers.py").split("NOT_TECH")[0]


@pytest.mark.parametrize("said, why", [
    ("MBB", "group"), ("Pension funds", "kind"), ("Kestrel Mutual, Oakmere Foods", "more than one"),
    ("kestrel.*", "pattern"), ("Ltd", "no employer"),
])
def test_a_form_the_bar_would_never_match_is_refused(tmp_path, monkeypatch, said, why):
    _profile(tmp_path, monkeypatch)
    import wants
    with pytest.raises(wants.Refused) as e:
        wants.decline(said, "no", TODAY)
    assert why in str(e.value) or (why == "no employer" and "employer" in str(e.value)), e.value
    assert profile_set.get("search.py", "BAR_DECLINED") is profile_set.MISSING
    assert _declined() == {}


def test_a_name_with_its_legal_form_is_one_employer_and_a_kind_named_as_an_employer_is_refused(
        tmp_path, monkeypatch):
    _profile(tmp_path, monkeypatch)
    import wants
    assert wants.decline("Brackwater Trust, Inc.", "no", TODAY)["added"]
    with pytest.raises(wants.Refused) as e:
        wants.sector_out("Kestrel Mutual", "no", TODAY)
    assert "an employer, not a kind" in str(e.value)


def test_a_posting_employer_turned_down_on_the_page_is_one_employer_whatever_its_commas(
        tmp_path, monkeypatch):
    """The page passes the posting's own employer: a firm named with a comma is one firm, and
    a name written two ways is one employer in a chat too."""
    _profile(tmp_path, monkeypatch)
    import app_actions
    import wants
    assert app_actions._decline_employer("Smith, Jones and Partners", "no more roles from them",
                                         TODAY)
    assert wants.decline("Brackwater Assurance / Brackwater Insurance", "no", TODAY)["added"]
    assert len(_declined()) == 2


# ------------------------------------------------------------------ the check

LIFT = '''
OPP_LEVERAGE = [
    (re.compile(r"\\b(supply chain|logistics)\\b", re.I), 10, "logistics work"),
    (re.compile(r"\\b(kestrel mutual|brindle)\\b", re.I), 12, "names worth a lift"),
    (re.compile(r"\\b(pension)\\w*", re.I), 8, "pensions experience", "employer"),
]
'''


def test_the_check_names_every_line_still_searching_or_lifting_what_was_turned_down(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, declined=HAND, sectors={"pension fund": "no"},
                    extra_search=LIFT)
    got = _run(prof, os.path.join("tools", "wants.py"), "check", state=str(tmp_path / "state"))
    assert got.returncode == 1, got.stdout
    out = got.stdout
    for where in ("profile/search.py line", "SCRAPE_EMPLOYERS: 'Kestrel Mutual'",
                  "SCRAPE_EMPLOYERS: 'Harbourline Pension Plan",
                  "profile/boards.py line 20, BOARDS: 'Kestrel Mutual'",
                  "TIER_2: 'kestrel mutual' is lifted +20",
                  "TIER_2: 'northwind pensions'", "TIER_3: 'harbourline pension plan'",
                  "OPP_LEVERAGE: 'names worth a lift' lifts kestrel mutual +12 by name",
                  "OPP_LEVERAGE: 'pensions experience' lifts every pension fund +8"):
        assert where in out, (where, out)
    assert "logistics work" not in out and "oakmere" not in out.lower()
    # The page's own check fails on it too, naming the same lines.
    (tmp_path / "model.json").write_text("{}", encoding="utf-8")
    got = _run(prof, os.path.join("tools", "app.py"), "check", "--model",
               str(tmp_path / "model.json"), state=str(tmp_path / "state"))
    assert "still search or lift what you turned down" in got.stdout, got.stdout + got.stderr
    assert "TIER_2: 'kestrel mutual'" in got.stdout and got.returncode == 1


def test_the_local_ci_runs_the_check_on_the_persons_files():
    with open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8") as fh:
        text = fh.read()
    person_part = text.split("if [ -f profile/person.json ]; then\n  PYTHONDONTWRITEBYTECODE=1",
                             1)[1]
    assert "tools/wants.py check" in person_part.split("\nfi\n", 1)[0]


# ------------------------------------------------------------------ an existing install

def test_an_existing_install_is_put_right_by_an_upgrade_touching_only_what_was_turned_down(
        tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, declined=HAND, extra_search=LIFT)
    import profile_upgrades
    up = next(u for u in profile_upgrades.REGISTRY if u.id == "declined-tidied")
    assert up.cost == "instant" and up.needs == "nobody"
    assert up.command == ("python3", "tools/wants.py", "tidy")
    assert "Kestrel Mutual" in up.pending()
    got = _run(prof, *up.command[1:], state=str(tmp_path / "state"))
    assert got.returncode == 0, got.stdout + got.stderr
    person.reset()
    assert up.pending() == ""
    assert profile_set.get("search.py", "SCRAPE_EMPLOYERS") == ["Oakmere Foods",
                                                                "Harbourline Pension Plan"]
    assert list(profile_set.get("boards.py", "BOARDS")) == ["Oakmere Foods"]
    tiers = _read(prof, "employers.py").split("NOT_TECH")[0]
    assert "kestrel mutual" not in tiers
    for kept in ("northwind pensions", "oakmere foods", "saltmarsh analytics",
                 "harbourline pension plan"):
        assert kept in tiers, kept
    # A lift written as a pattern is code: named, never edited.
    assert "names worth a lift" in got.stdout and "by hand" in got.stdout
    assert "kestrel mutual|brindle" in _read(prof, "search.py")


# ------------------------------------------------------------------ what a round searches with

def _round(tmp_path, monkeypatch, capsys, name):
    import run_round
    monkeypatch.setattr(run_round, "run", lambda cmd, log, deadline=None, ok=(0,): 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]", encoding="utf-8")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(tmp_path / name), "--from-scraped", str(scraped),
        "--seen", str(seen), "--summary-dir", str(tmp_path / "summ"), "--today", TODAY,
        "--pages", "1"])
    run_round.main()
    return capsys.readouterr().out, (tmp_path / name / "round.log").read_text(encoding="utf-8")


def test_a_round_says_what_it_searches_with_and_what_changed_since_the_last(
        tmp_path, monkeypatch, capsys):
    prof = _profile(tmp_path, monkeypatch, extra_search="\nJOB_AGE_DAYS = 10\n")
    said, log = _round(tmp_path, monkeypatch, capsys, "r1")
    head = said.split("searching with:", 1)[1]
    assert "window: 10 days (your setting)" in head
    assert "places: Manchester, Salford, Stockport and United Kingdom" in head
    assert "kinds of employer out: a sector the candidate will not work in" in head
    assert "employers turned down by name: 0" in head
    assert "since the last search: no record of one yet" in head
    assert "searching with:" in log
    # Turned down meanwhile, by hand, and missed on the lists: the next round says so first.
    profile_set.set_line("search.py", "BAR_DECLINED", HAND)
    said, _ = _round(tmp_path, monkeypatch, capsys, "r2")
    head = said.split("searching with:", 1)[1]
    assert "since the last search (r1, 2026-11-17): employers out: added kestrel mutual" in head
    assert ("turned down, so not asked for this round: searches by name for Kestrel Mutual; "
            "the job sites of Kestrel Mutual") in head
    assert "setting(s) still name what you turned down" in head
    with open(os.path.join(str(tmp_path / "state"), "documents", "rounds", "searched",
                           "with.json"), encoding="utf-8") as fh:
        assert set(json.load(fh)) == {"r1", "r2"}
    assert prof


def test_the_persons_own_list_tidy_is_said_and_left_as_it_is(tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, extra_search="\nJOB_AGE_DAYS = 10\n")
    with open(os.path.join(prof, "clear_old_jobs.py"), "w", encoding="utf-8") as fh:
        fh.write('"""Set aside every job on the list found more than a week ago."""\n')
    person.put("brief.before", ["profile/clear_old_jobs.py"])
    import wants
    lines = wants.header("window: 10 days (your setting)", 10, keep=False)
    assert any("your own step profile/clear_old_jobs.py: \"Set aside every job on the list "
               "found more than a week ago.\" (its own setting, left as it is)" in ln
               for ln in lines), lines


def test_every_window_reads_the_persons_own_unless_a_search_is_given_one(tmp_path, monkeypatch):
    prof = _profile(tmp_path, monkeypatch, extra_search="\nJOB_AGE_DAYS = 10\n")
    import prefilter
    assert prefilter.own_window() == 10
    rows = [{"title": t, "company": "Oakmere Foods", "date": d,
             "location": "Manchester, England, United Kingdom", "url": f"https://jobs.example/{d}"}
            for t, d in (("Data Analyst", "2026-11-12"), ("Supply Chain Analyst", "2026-11-05"))]
    src = tmp_path / "in.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    out = tmp_path / "out.json"
    got = _run(prof, os.path.join("tools", "prefilter.py"), str(src), "--out", str(out),
               "--today", TODAY, state=str(tmp_path / "state"))
    assert got.returncode == 0, got.stdout + got.stderr
    kept = [r["date"] for r in json.loads(out.read_text(encoding="utf-8"))]
    assert kept == ["2026-11-12"], kept           # 12 days old is past the person's 10
    got = _run(prof, os.path.join("tools", "prefilter.py"), str(src), "--out", str(out),
               "--today", TODAY, "--jobage", "14", state=str(tmp_path / "state"))
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 2
