"""The public app is checked for the maintainer's names from the maintainer's own repo.

CI could check names only through a secret someone rebuilt and pasted in by hand, and it
fell behind. tools/app_watch.py needs neither: in the repo whose owner is the app's, every
sync scans what is new in the app (each unmerged branch's files, commit messages, pull
request text) against the denylist built from that repo. Elsewhere it does nothing.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import app_watch  # noqa: E402
import build_app  # noqa: E402


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                           "user.email=t@example.com", *a], check=True, capture_output=True,
                          text=True).stdout


def _setup(tmp_path, monkeypatch, body="All fine here.\n"):
    app = tmp_path / "example-owner" / "app"
    app.mkdir(parents=True)
    _git(app, "init", "-q", "-b", "master")
    (app / "README.md").write_text(body)
    _git(app, "add", "-A")
    _git(app, "commit", "-qm", "Merge pull request #7 from example-owner/topic")
    mine = tmp_path / "mine"
    (mine / "profile").mkdir(parents=True)
    _git(mine, "init", "-q")
    _git(mine, "remote", "add", "origin", str(tmp_path / "example-owner" / "my-search"))
    monkeypatch.setenv("LJS_APP_URL", str(app))
    monkeypatch.setattr(app_watch, "ROOT", str(mine))
    monkeypatch.setattr(build_app, "denylist", lambda: ["Zorblax Quux"])
    monkeypatch.setattr(app_watch, "_pull_requests", lambda since: ([], ""))
    return app, mine


def test_only_the_maintainers_repo_is_checked(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert app_watch.is_maintainers()
    monkeypatch.setenv("LJS_APP_URL", "https://github.com/someone-else/last-job-search")
    assert not app_watch.is_maintainers()
    assert app_watch.main([]) == 0                      # says nothing, does nothing


def test_a_name_in_the_app_is_found_and_said_first(tmp_path, monkeypatch, capsys):
    app, _ = _setup(tmp_path, monkeypatch, "Thanks to Zorblax Quux for the idea.\n")
    assert app_watch.main([]) == 1
    out = capsys.readouterr().out
    assert out.startswith("APP LEAK: 1 match(es) in the public app's files, all of them 'Zorblax Quux'.")
    assert "change nothing in the app without them" in out
    assert "README.md" not in out and "app_watch.py --all" in out
    # --all is where every match is, with where it is.
    assert app_watch.main(["--all"]) == 1
    assert "README.md:1" in capsys.readouterr().out


def test_many_matches_of_one_entry_are_one_line_and_all_listed_with_all(tmp_path, monkeypatch,
                                                                        capsys):
    body = "".join(f"line {n}: thanks Zorblax Quux\n" for n in range(64))
    _setup(tmp_path, monkeypatch, body)
    assert app_watch.main([]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("APP LEAK: 64 match(es) in the public app's files, all of "
                             "them 'Zorblax Quux'.")
    assert len(out) == 2                    # the line for the person, and where the rest is
    assert app_watch.main(["--all"]) == 1
    listed = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("  - ")]
    assert len(listed) == 64                # every one, where it stopped at forty


def test_the_headline_counts_each_entry():
    found = (["README.md:%d: denylist entry 3 (Hi Wren)" % n for n in range(3)]
             + ["NOTES.md:1: email address someone@example.org",
                "docs/a.md:2: personal path (tools/personal_paths.py)"])
    line = app_watch.headline(found)
    assert line.startswith("5 matches in the public app's files, of 3 entries: 'Hi Wren' (3)")
    assert "email address someone@example.org (1)" in line
    mixed = app_watch.headline(["branch master: README.md:1: denylist entry 1 (Hi Wren)",
                                "commit 0123456789ab message: messages:1: denylist entry 1 "
                                "(Hi Wren)"])
    assert mixed == ("2 match(es) in the public app (1 in files, 1 in commit messages), all of "
                     "them 'Hi Wren'")


def test_clean_says_so_once_and_the_next_look_reads_only_what_is_new(tmp_path, monkeypatch, capsys):
    app, _ = _setup(tmp_path, monkeypatch)
    assert app_watch.main([]) == 0
    assert capsys.readouterr().out.startswith("App watch: clean (1 branch(es), 1 new file")
    assert app_watch.main([]) == 0
    assert "0 new file version(s), 0 commit message(s)" in capsys.readouterr().out
    # A commit message with a name in it is found, the owner in a merge line never is.
    (app / "NOTES.md").write_text("x\n")
    _git(app, "add", "-A")
    _git(app, "commit", "-qm", "Thanks Zorblax Quux")
    assert app_watch.main([]) == 1
    assert "commit messages" in capsys.readouterr().out


def test_a_pull_request_description_is_checked(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(app_watch, "_pull_requests", lambda since: (
        [{"number": 9, "title": "Fix", "body": "Found by Zorblax Quux", "updated_at": "2026-10-19"}], ""))
    findings, _ = app_watch.watch()
    assert findings == ["pull request #9: denylist entry 1 (Zorblax Quux)"]


def _pages(monkeypatch, prs):
    """GitHub's pull request list, newest update first, a page at a time."""
    import io
    import json
    import urllib.parse
    asked = []

    def urlopen(req, timeout=15):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)
        page, per = int(q["page"][0]), int(q["per_page"][0])
        asked.append(page)
        return io.BytesIO(json.dumps(prs[(page - 1) * per:page * per]).encode())
    monkeypatch.setattr(app_watch.urllib.request, "urlopen", urlopen)
    return asked


def _prs(n):
    return [{"number": i, "title": "t", "body": "b",
             "updated_at": f"2026-10-{1 + i // 10:02d}T00:00:{i % 60:02d}Z"}
            for i in range(n, 0, -1)]


def test_every_pull_request_is_read_not_only_the_newest_fifty(monkeypatch):
    # One page of fifty was read, so --all checked fifty and called it everything.
    asked = _pages(monkeypatch, _prs(230))
    got, unread = app_watch._pull_requests("")
    assert (len(got), unread, asked) == (230, "", [1, 2, 3, 4, 5])


def test_a_look_reads_back_only_to_the_last_one_it_read(monkeypatch):
    prs = _prs(230)
    asked = _pages(monkeypatch, prs)
    since = prs[149]["updated_at"]                     # 150 changed since the last look
    got, unread = app_watch._pull_requests(since)
    assert (len(got), unread, asked) == (149, "", [1, 2, 3])


def test_a_page_that_cannot_be_read_moves_no_mark(monkeypatch):
    def down(req, timeout=15):
        raise OSError("unreachable")
    monkeypatch.setattr(app_watch.urllib.request, "urlopen", down)
    assert app_watch._pull_requests("") == ([], "pull request text not checked (OSError)")


def test_the_sync_runs_it_after_every_successful_sync(sync_steps):
    # Run the sync and read what it did, rather than search its source for the call.
    rc, steps = sync_steps()
    assert rc == 0
    assert steps.index("sync") < steps.index("_record_check") < steps.index("app_watch")
    rc, steps = sync_steps(sync_rc=1)
    assert rc == 1 and "app_watch" not in steps and "_record_check" not in steps
