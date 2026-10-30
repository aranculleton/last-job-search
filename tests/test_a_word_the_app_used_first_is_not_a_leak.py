"""A denylist entry the app's own text used before the person recorded it is set aside.

The denylist takes every employer in the tracker, and two whose names are ordinary words
in the app's own commands and tests failed every check in the maintainer's repo
(2026-10-24), while ALLOWED_ORGANIZATIONS had been growing by hand, one such name at a
time. A word the app used before the person
wrote it down cannot have come from them. The app is read as it stood before the entry
was recorded, never as it stands now, so a leak that reached the app afterwards cannot
excuse itself.
"""
import calendar
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_app  # noqa: E402
import person  # noqa: E402


def _ts(day):
    return float(calendar.timegm(time.strptime(day, "%Y-%m-%d")))


def _git(cwd, *a, day=None):
    env = dict(os.environ)
    if day:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"{day}T12:00:00Z"
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                           "user.email=t@example.com", *a], check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env).stdout.strip()


def _commit(repo, files, day):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"on {day}", day=day)
    return _git(repo, "rev-parse", "HEAD")


def _app(tmp_path):
    """An app whose command said "Batch-Lanternfish" from January, and whose test named
    Quayside Foods only from March."""
    app = tmp_path / "app"
    app.mkdir()
    _git(app, "init", "-q", "-b", "master")
    first = _commit(app, {".claude/commands/rank.md": "Batch-Lanternfish the postings.\n"},
                    "2026-01-10")
    later = _commit(app, {"tests/test_x.py": "# Quayside Foods replied\n"}, "2026-03-10")
    return app, first, later


def test_a_word_the_app_used_before_it_was_recorded_is_set_aside(tmp_path):
    app, first, _ = _app(tmp_path)
    when = {"=Lanternfish": _ts("2026-02-01"), "=Quayside Foods": _ts("2026-02-01")}
    got = build_app.set_aside(when, when, ref="master", root=str(app))
    # The app carried the first before February; the second reached it in March, after
    # the person recorded it, and may be the leak itself.
    assert got == {"=Lanternfish": first[:12]}


def test_the_app_is_read_as_it_stood_when_the_entry_was_recorded(tmp_path):
    app, first, later = _app(tmp_path)
    # Recorded after the app's test named it: the app had it first.
    assert build_app.set_aside(["=Quayside Foods"], {"=Quayside Foods": _ts("2026-04-01")},
                               ref="master", root=str(app)) == {"=Quayside Foods": later[:12]}
    # Recorded before the app had any of it: nothing to set aside.
    assert build_app.set_aside(["=Lanternfish"], {"=Lanternfish": _ts("2025-12-01")},
                               ref="master", root=str(app)) == {}


def test_an_entry_with_no_date_is_never_set_aside(tmp_path):
    """The person's own name, employers and schools, everyone a run named, and
    profile/leak_tokens.txt carry no date, and a match on them is always a leak."""
    app, _, _ = _app(tmp_path)
    assert build_app.set_aside(["=Lanternfish"], {"=Lanternfish": None},
                               ref="master", root=str(app)) == {}


def test_the_app_carries_an_entry_only_the_way_the_scan_would_find_it(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    _git(app, "init", "-q", "-b", "master")
    _commit(app, {"a.md": "lanternfish, lower case\n", "b.md": "Lanternfishery\n"},
            "2026-01-10")
    when = {"=Lanternfish": _ts("2026-02-01")}
    # Case-sensitive, and a whole word: neither file is the employer's name.
    assert build_app.set_aside(when, when, ref="master", root=str(app)) == {}


def test_no_copy_of_the_app_sets_nothing_aside(tmp_path):
    app, _, _ = _app(tmp_path)
    when = {"=Lanternfish": _ts("2026-02-01")}
    assert build_app.set_aside(when, when, ref="refs/remotes/app/master",
                               root=str(app)) == {}


def test_the_scan_reports_only_what_is_left(tmp_path):
    app, first, _ = _app(tmp_path)
    tree = tmp_path / "tree"
    (tree / "docs").mkdir(parents=True)
    (tree / "docs" / "a.md").write_text("Batch-Lanternfish the postings.\nQuayside Foods\n")
    when = {"=Lanternfish": _ts("2026-02-01"), "=Quayside Foods": _ts("2026-02-01")}
    findings, aside = build_app.check(str(tree), when, ref="master", root=str(app))
    assert findings == ["docs/a.md:2: denylist entry 2"]
    assert aside == {"=Lanternfish": first[:12]}


def test_a_word_found_only_in_the_apps_own_files_is_still_set_aside(tmp_path, monkeypatch):
    """A file exactly as the app has it is left out of the findings, and an entry found only
    there was then never set aside: it stayed on the list the push gate scans the app with,
    and every push failed on files it never touched (an employer that is also an ordinary
    word, 2026-10-30). The rule is the same: only what the app carried before it was
    recorded is set aside, and nothing else leaves the list."""
    import personal_paths
    app, first, _ = _app(tmp_path)
    tree = tmp_path / "tree"
    (tree / "docs").mkdir(parents=True)
    (tree / "docs" / "a.md").write_text("Batch-Lanternfish the postings.\nQuayside Foods\n")
    monkeypatch.setattr(personal_paths, "same_as_the_app", lambda root: {"docs/a.md"})
    when = {"=Lanternfish": _ts("2026-02-01"), "=Quayside Foods": _ts("2026-02-01")}
    findings, aside = build_app.check(str(tree), when, ref="master", root=str(app))
    assert findings == [], "the app's own file is not a finding"
    assert aside == {"=Lanternfish": first[:12]}, "set aside by the history, as anywhere else"
    assert "=Quayside Foods" not in aside, "reached the app after it was recorded: stays listed"


def test_the_build_says_what_it_set_aside_and_keeps_it_off_the_list_it_writes(
        tmp_path, monkeypatch, capsys):
    app, first, _ = _app(tmp_path)

    def export(out_dir):
        os.makedirs(out_dir)
        with open(os.path.join(out_dir, "rank.md"), "w") as fh:
            fh.write("Batch-Lanternfish the postings.\n")
        return []
    monkeypatch.setattr(build_app, "export", export)
    monkeypatch.setattr(build_app, "recorded", lambda: {
        "=Lanternfish": _ts("2026-02-01"), "=Quayside Foods": _ts("2026-02-01")})
    monkeypatch.setattr(build_app, "ROOT", str(app))
    monkeypatch.setattr(build_app, "RELEASED", "master")
    out = tmp_path / "out"
    assert build_app.main([str(out), "--tokens-out", str(tmp_path / "tokens")]) == 0
    said = capsys.readouterr().out
    assert (f"set aside 1 entry the app already carried before this repo recorded them: "
            f"'Lanternfish' (app {first[:12]})") in said
    assert "leak scan clean (1 denylist entries)" in said
    assert (tmp_path / "tokens").read_text() == "=Quayside Foods\n"


def test_a_leak_with_no_copy_of_the_app_to_compare_says_so(tmp_path, monkeypatch, capsys):
    app, _, _ = _app(tmp_path)

    def export(out_dir):
        os.makedirs(out_dir)
        with open(os.path.join(out_dir, "rank.md"), "w") as fh:
            fh.write("Batch-Lanternfish the postings.\n")
        return []
    monkeypatch.setattr(build_app, "export", export)
    monkeypatch.setattr(build_app, "recorded", lambda: {"=Lanternfish": _ts("2026-02-01")})
    monkeypatch.setattr(build_app, "ROOT", str(app))
    monkeypatch.setattr(build_app, "RELEASED", "refs/remotes/app/master")
    assert build_app.main([str(tmp_path / "out")]) == 1
    out = capsys.readouterr()
    assert "rank.md:1: denylist entry 1" in out.out
    assert "no copy of the app's master here to compare with" in out.out
    assert "LEAK SCAN FAILED" in out.err


def test_each_row_is_dated_by_the_commit_that_first_held_it(tmp_path, monkeypatch):
    repo = tmp_path
    _git(repo, "init", "-q")
    _commit(repo, {"job_search_tracker.csv": "company,role,notes\nQuayside Foods,Analyst,\n"},
            "2026-02-01")
    _commit(repo, {"job_search_tracker.csv": "company,role,notes\nQuayside Foods,Analyst,chased\n"
                                             "Larkspur Retail,Analyst,\n"}, "2026-03-01")
    (repo / "job_search_tracker.csv").write_text(
        "company,role,notes\nQuayside Foods,Analyst,chased\nLarkspur Retail,Analyst,\n"
        "Saltmarsh Mills,Analyst,\n")
    dated = {(r["company"], r["notes"]): w
             for r, w in build_app._csv_dated(str(repo / "job_search_tracker.csv"))}
    assert dated[("Quayside Foods", "")] == _ts("2026-02-01") + 12 * 3600
    assert dated[("Quayside Foods", "chased")] == _ts("2026-03-01") + 12 * 3600
    assert dated[("Larkspur Retail", "")] == _ts("2026-03-01") + 12 * 3600
    # Only the working copy holds it: added after the newest copy that did not.
    assert dated[("Saltmarsh Mills", "")] == _ts("2026-03-01") + 12 * 3600
    monkeypatch.setenv(person.STATE_ENV, str(repo))
    when = build_app.recorded()
    # An employer is as old as the first row that named it, whatever changed in it since.
    assert when["=Quayside Foods"] == _ts("2026-02-01") + 12 * 3600
    assert when["=Saltmarsh Mills"] == _ts("2026-03-01") + 12 * 3600
    # The person's own name has no date: it is never set aside.
    assert when[person.get("identity")["name"]] is None
    assert list(when) == build_app.denylist()


def test_a_shallow_clone_never_dates_a_row_later_than_it_can_see(tmp_path):
    """A cloud chat's clone stops at a depth. A row it first sees at its oldest commit
    may be months older, and a date too late reads the app as it stood too late."""
    full = tmp_path / "full"
    full.mkdir()
    _git(full, "init", "-q", "-b", "master")
    _commit(full, {"job_search_tracker.csv": "company,role\nQuayside Foods,Analyst\n"},
            "2026-02-01")
    _commit(full, {"README.md": "x\n"}, "2026-03-01")
    _commit(full, {"job_search_tracker.csv": "company,role\nQuayside Foods,Analyst\n"
                                             "Larkspur Retail,Analyst\n"}, "2026-04-01")
    cut = tmp_path / "cut"
    subprocess.run(["git", "clone", "-q", "--depth", "2", f"file://{full}", str(cut)],
                   check=True, capture_output=True)
    dated = {r["company"]: w for r, w in build_app._csv_dated(str(cut / "job_search_tracker.csv"))}
    assert dated == {"Quayside Foods": None,                       # first seen at the cut
                     "Larkspur Retail": _ts("2026-04-01") + 12 * 3600}


def test_a_rewritten_commit_keeps_the_day_the_row_was_written(tmp_path):
    """A cherry-pick or a rebase gives a commit today's date and keeps the day it was
    written as its author date. Dated by the first, a row recorded in February read
    the app as it stood in April, with a March leak in it, and the leak was excused."""
    app, _, _ = _app(tmp_path)                       # Quayside Foods reached it in March
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _commit(repo, {"README.md": "x\n"}, "2026-01-05")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, {"job_search_tracker.csv": "company,role\nQuayside Foods,Analyst\n"},
            "2026-02-01")
    _git(repo, "checkout", "-q", "master")
    env = dict(os.environ, GIT_COMMITTER_DATE="2026-04-01T12:00:00Z")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "cherry-pick", "side"], check=True, capture_output=True, env=env)
    _git(repo, "branch", "-q", "-D", "side")
    (row, w), = build_app._csv_dated(str(repo / "job_search_tracker.csv"))
    assert w == _ts("2026-02-01") + 12 * 3600
    assert build_app.set_aside(["=Quayside Foods"], {"=Quayside Foods": w},
                               ref="master", root=str(app)) == {}


def test_a_row_not_yet_committed_reads_the_app_from_before_the_files_last_commit(tmp_path):
    """Dated "now", a row still only in the working copy read the app as it stands
    today, so a leak merged an hour ago excused itself."""
    app, _, _ = _app(tmp_path)                       # Quayside Foods reached it in March
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _commit(repo, {"job_search_tracker.csv": "company,role\nLarkspur Retail,Analyst\n"},
            "2026-02-01")
    (repo / "job_search_tracker.csv").write_text(
        "company,role\nLarkspur Retail,Analyst\nQuayside Foods,Analyst\n")
    when = {r["company"]: w for r, w in build_app._csv_dated(str(repo / "job_search_tracker.csv"))}
    assert when["Quayside Foods"] == _ts("2026-02-01") + 12 * 3600
    assert build_app.set_aside(["=Quayside Foods"], {"=Quayside Foods": when["Quayside Foods"]},
                               ref="master", root=str(app)) == {}
    # And a file with no history at all dates nothing.
    other = tmp_path / "loose"
    other.mkdir()
    (other / "job_search_tracker.csv").write_text("company,role\nQuayside Foods,Analyst\n")
    assert [w for _, w in build_app._csv_dated(str(other / "job_search_tracker.csv"))] == [None]


def test_a_commit_dated_out_of_order_names_no_copy_from_after_the_leak(tmp_path):
    """Searched by date, the newest commit dated before the record was a later commit
    with its clock wrong, which already held the leak. The app is walked in order."""
    app = tmp_path / "app"
    app.mkdir()
    _git(app, "init", "-q", "-b", "master")
    first = _commit(app, {"a.md": "nothing yet\n"}, "2026-01-10")
    _commit(app, {"b.md": "Quayside Foods replied\n"}, "2026-03-01")          # the leak
    _commit(app, {"c.md": "later\n"}, "2026-01-20")                          # clock wrong
    when = {"=Quayside Foods": _ts("2026-02-01")}
    assert build_app.set_aside(when, when, ref="master", root=str(app)) == {}
    assert first


def test_the_allowed_organizations_list_is_closed():
    """It grew one employer at a time, each the day one failed a check. A tracker
    employer the app's text already used is now set aside with no name written down, so
    a name added here is that list starting again."""
    assert build_app.ALLOWED_ORGANIZATIONS == {
        "Anthropic", "LinkedIn", "GitHub", "eBay", "Docker",
        "Google", "Microsoft", "Apple", "IBM", "Oracle"}
