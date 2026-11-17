"""The jobs already on the page are scored again when how jobs are scored changes.

After a person changed how jobs are scored (tiers, leverage, title families), nothing scored
again the jobs their page already listed: Jobs kept each earlier search's rows with the scores
they had when that search ran, for the whole time it carries them. A search keeps the posting
text of only the top 60 of its own working file, and nowhere a later chat can read, so
running a saved search's ranking again dropped every row its list held below those 60, with
no word that it had.

Now a search keeps the text of every job its list holds (documents/rounds/bodies/), and one
command, tools/rescore.py, scores again what the page lists: the newest search and the earlier
ones it carries, each row in its place. The update reaches an existing copy by itself: the
`jobs-rescored` profile upgrade is due whenever the scoring has changed since the page's jobs
were scored, the app's or the person's own, and the sync runs it. Invented employers only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
import person  # noqa: E402
import run_round  # noqa: E402
from lookup_score import norm  # noqa: E402
import repo_files  # noqa: E402

TODAY = "2026-11-10"
BODY = ("{company} prices freight for carriers across the North West. You will build demand "
        "forecasts in SQL and Python and present them to the stakeholders who set the rates "
        "each week. {extra}Salary: £50,000 - £58,000 per year. Hybrid, three days a week in "
        "our Manchester office. This is a permanent role in a team of six analysts who share "
        "the work and the weekly review with operations, and look after the rate cards.")
PENALTY = '''

# The person's own change to how jobs are scored, made after the searches ran.
OPP_LEVERAGE = [
    (re.compile(r"\\b(long hours|on[- ]call)\\b", re.I), -12,
     "long or unpredictable hours, which cost the person evenings"),
]
'''


def _row(n, company, day, extra="", score=70):
    return {"title": "Demand Forecasting Analyst", "company": company, "portal": "linkedin",
            "location": "Manchester, England, United Kingdom", "date": day, "first_seen": day,
            "url": f"https://jobs.example/{n}",
            "desc": BODY.format(company=company, extra=extra),
            "priority": score, "fit": score, "opportunity": score}


def _setup(tmp_path, monkeypatch):
    state, prof = tmp_path / "state", tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    app_state.profile_copy(str(prof))
    monkeypatch.setenv("LJS_STATE", str(state))
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    person.reset()
    return state, prof


def _save(state, name, rows, keep_text=True, folder=False):
    """A search saved as a round saves it: its list without the text, and (`keep_text`) the
    text of every job on it; with `folder`, the round's own working folder too, as a computer
    keeps it."""
    rounds = state / "documents" / "rounds"
    rounds.mkdir(parents=True, exist_ok=True)
    short = state / f"{name}_06.json"
    short.write_text(json.dumps(rows), encoding="utf-8")
    run_round.write_summary(str(short), str(rounds), name, show=0)
    if not keep_text:
        shutil.rmtree(rounds / "bodies", ignore_errors=True)
    if folder:
        work = state / "rounds" / name
        work.mkdir(parents=True)
        shutil.copy(short, work / "06_shortlist.json")
    short.unlink()


def _rescore(state, prof, *args):
    env = dict(os.environ, LJS_STATE=str(state), LJS_PROFILE=str(prof), PYTHONUTF8="1")
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "rescore.py"),
                           "--today", TODAY, *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=ROOT)


def _list(state, name):
    return json.loads((state / "documents" / "rounds" / f"{name}.json").read_text("utf-8"))


def test_a_search_keeps_the_text_of_every_job_its_list_holds(tmp_path, monkeypatch):
    """Rows taken further down after the hard rules are kept with their text, past the 60 a
    round's own folder keeps (run_round.trim)."""
    state, _prof = _setup(tmp_path, monkeypatch)
    rows = [_row(n, f"Firm {n}", "2026-11-08", score=200 - n) for n in range(1, 81)]
    short = tmp_path / "06_shortlist.json"
    short.write_text(json.dumps(rows), encoding="utf-8")
    rounds = state / "documents" / "rounds"
    path = run_round.write_summary(str(short), str(rounds), "r3", show=10,
                                   rules=lambda r: "" if int(r["url"].rsplit("/", 1)[1]) > 65
                                   else "screen: a cut the test makes")
    listed = json.loads(open(path, encoding="utf-8").read())
    assert [r["url"].rsplit("/", 1)[1] for r in listed] == [str(n) for n in range(66, 76)]
    kept = json.loads((rounds / "bodies" / "r3.json").read_text("utf-8"))
    assert set(kept["bodies"]) == {norm(r["url"]) for r in listed}
    assert kept["bodies"][norm("https://jobs.example/70")].startswith("Firm 70 prices freight")
    assert kept["scored_with"]
    assert sorted(p.name for p in rounds.glob("*.json")) == ["r3.json"]   # only summaries on top


def test_a_change_to_how_jobs_are_scored_scores_the_page_again(tmp_path, monkeypatch):
    state, prof = _setup(tmp_path, monkeypatch)
    _save(state, "r1", [_row(1, "Quillon Freight", "2026-11-04", "Expect long hours. "),
                        _row(2, "Saltmere Freight", "2026-11-04")])
    _save(state, "r2", [_row(3, "Larkspur Freight", "2026-11-09"),
                        _row(4, "Fernhill Freight", "2026-11-09", "The role is on call. ")])
    first = _rescore(state, prof)
    assert first.returncode == 0, first.stderr
    assert _rescore(state, prof, "--check").returncode == 0      # nothing changed since
    before = {r["url"]: r for name in ("r1", "r2") for r in _list(state, name)}

    with open(prof / "search.py", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(PENALTY)
    due = _rescore(state, prof, "--check")
    assert due.returncode == 1 and due.stdout.strip(), due.stdout
    got = _rescore(state, prof)
    assert got.returncode == 0, got.stderr
    after = {name: _list(state, name) for name in ("r1", "r2")}
    # Each row stays in its place, the newest search's and the carried one's alike.
    assert [r["url"] for r in after["r1"]] == ["https://jobs.example/1", "https://jobs.example/2"]
    assert [r["url"] for r in after["r2"]] == ["https://jobs.example/3", "https://jobs.example/4"]
    now = {r["url"]: r for rows in after.values() for r in rows}
    for n in (1, 4):                                             # the penalty bites
        u = f"https://jobs.example/{n}"
        assert now[u]["opportunity"] == before[u]["opportunity"] - 12, (before[u], now[u])
        assert now[u]["priority"] < before[u]["priority"]
    for n in (2, 3):                                             # the rest are as they were
        u = f"https://jobs.example/{n}"
        assert {k: now[u][k] for k in ("opportunity", "fit", "priority")} == \
            {k: before[u][k] for k in ("opportunity", "fit", "priority")}
    assert _rescore(state, prof, "--check").returncode == 0


def test_the_update_scores_an_existing_copys_page_by_itself(tmp_path, monkeypatch):
    """A copy from before this update kept no text: a search's own folder on the computer is
    read for it, a job whose text is nowhere keeps its score and is said, and the upgrade the
    sync runs touches nothing but the saved searches."""
    state, prof = _setup(tmp_path, monkeypatch)
    _save(state, "r2", [_row(5, "Larkspur Freight", "2026-11-09", score=11),
                        _row(6, "Brackenhollow Freight", "2026-11-09", score=12)],
          keep_text=False, folder=True)
    # The round's own folder lost one row's text (it was below the 60 it keeps).
    work = state / "rounds" / "r2" / "06_shortlist.json"
    work.write_text(json.dumps(json.loads(work.read_text("utf-8"))[:1]), encoding="utf-8")
    import profile_upgrades
    up = profile_upgrades.by_id("jobs-rescored")
    assert up.cost == "instant" and up.needs == "nobody" and up.command
    before = {p: p.stat().st_mtime_ns for p in repo_files.files("**/*", root=state)}
    assert up.pending(), "an existing copy's page is due to be scored again"
    env = dict(os.environ, LJS_STATE=str(state), LJS_PROFILE=str(prof), PYTHONUTF8="1")
    run = subprocess.run([sys.executable if up.command[0] == "python3" else up.command[0],
                          *up.command[1:]], capture_output=True, text=True, encoding="utf-8",
                         env=env, cwd=ROOT)
    assert run.returncode == 0, run.stderr
    assert "1 " in run.stdout and "--fetch" in run.stdout, run.stdout
    rows = {r["url"]: r for r in _list(state, "r2")}
    assert rows["https://jobs.example/5"]["fit"] != 11               # scored again
    assert rows["https://jobs.example/6"]["fit"] == 12               # no text anywhere: as it was
    changed = sorted(os.path.relpath(p, state).replace(os.sep, "/") for p in repo_files.files("**/*", root=state)
                     if before.get(p) != p.stat().st_mtime_ns)
    assert changed == ["documents/rounds/bodies/r2.json", "documents/rounds/r2.json"], changed
    person.reset()
    assert up.pending() == ""


def test_two_chats_that_kept_text_for_one_search_merge_without_asking(tmp_path, monkeypatch):
    """Two chats can score the page again at once after an update: the text each kept for one
    search is kept from both, job by job, written as its writer writes it, and the scoring
    each recorded settles quietly, since the page is scored again wherever it is not today's."""
    import merge_state
    _setup(tmp_path, monkeypatch)
    import rescore
    where = str(tmp_path / "rounds")

    def kept(*ns, scored_with):
        rescore.keep(where, "r4", [_row(n, f"Firm {n}", "2026-11-09") for n in ns],
                     scored_with=scored_with)
        with open(rescore.bodies_path("r4", where), encoding="utf-8") as fh:
            return fh.read()
    base = kept(7, scored_with="aaaa")
    ours = kept(7, 8, scored_with="bbbb")
    os.remove(rescore.bodies_path("r4", where))
    theirs = kept(7, 9, scored_with="cccc")
    settled, noted = [], []
    text, problems = merge_state.merge(base, ours, theirs, "documents/rounds/bodies/r4.json",
                                       settled=settled, noted=noted)
    assert problems == [] and settled == [], (problems, settled)
    got = json.loads(text)
    assert set(got["bodies"]) == {norm(f"https://jobs.example/{n}") for n in (7, 8, 9)}
    assert got["scored_with"] == "bbbb"
    assert text == json.dumps(got, indent=1, ensure_ascii=False) + "\n"
