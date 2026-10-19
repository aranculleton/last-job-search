"""A person's own tests, checked against each update, and told why one fails.

When 3.5.0 moved the employer boards into openroles, the maintainer's own tests failed by
the dozen on names the release removed. The sync said nothing: the copy of sync_app.py
that ran it predated the check. Nobody had run those tests against the release before it
shipped, either. Invented people and employers only.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import sync_app  # noqa: E402

GONE = "AttributeError: module 'ats_boards' has no attribute '_ROBOTS'"
MOCKED = ("AttributeError: <module 'ats_boards' from '/x/tools/ats_boards.py'> does not have "
          "the attribute '_request'")


def test_a_failure_on_a_removed_name_is_told_apart_from_a_behaviour_change():
    text = sync_app.own_tests_report([
        ("mine::test_robots", GONE), ("mine::test_more_robots", GONE),
        ("mine::test_patched", MOCKED),
        ("mine::test_old_shape", "AssertionError: 'Fernhill' != 'Acme'")], ROOT)
    first, removed, changed, ask, again = text.splitlines()
    assert first == "Your own tests: 4 now fail after this update."
    assert "3 use parts of the app this update removed: ats_boards._ROBOTS (2), ats_boards._request (1)" in removed
    assert "tools/offline_boards.py" in removed
    assert changed.startswith("  1 check behaviour the update changed: mine::test_old_shape")
    assert "Ask once, in these words" in ask
    assert "--own-tests" in again
    assert sync_app.own_tests_report([], ROOT) == ""


def test_the_person_is_asked_in_words_that_need_no_idea_what_a_test_is():
    text = sync_app.own_tests_report([("mine::test_robots", GONE)] * 3, ROOT)
    for words in (sync_app.ASK_TIDY, *sync_app.ASK_ANSWERS, sync_app.TIDY_MEANS,
                  sync_app.TIDY_YES, sync_app.TIDY_NO):
        assert f'"{words}"' in text
    assert sync_app.ASK_ANSWERS[0] == "Yes (recommended)"
    assert text.index(sync_app.ASK_ANSWERS[0]) < text.index(sync_app.ASK_ANSWERS[1])
    said = " ".join([sync_app.ASK_TIDY, *sync_app.ASK_ANSWERS, sync_app.TIDY_MEANS,
                     sync_app.TIDY_YES, sync_app.TIDY_NO]).lower()
    for jargon in ("test", "tests", "retire", "pytest", "ci", "assert", "module", "private", "repo"):
        assert jargon not in said.replace(".", " ").replace(",", " ").split(), jargon
    assert len(sync_app.ASK_TIDY.split()) <= 25
    assert "profile, applications, contacts and documents are not touched" in said


def test_nothing_is_asked_when_nothing_needs_deleting():
    text = sync_app.own_tests_report([("mine::test_old_shape", "AssertionError: 1 != 2")], ROOT)
    assert sync_app.ASK_TIDY not in text
    assert "nothing to ask the person" in text


def test_a_name_the_person_owns_is_not_called_the_apps():
    assert sync_app._gone(ROOT, "AttributeError: module 'my_own_helper' has no attribute 'x'") == ""
    assert sync_app._gone(ROOT, "ImportError: cannot import name 'gone' from 'prefilter'") == "prefilter.gone"
    assert sync_app._gone(ROOT, "ModuleNotFoundError: No module named 'openroles.old'") == "openroles.old"


def _repo(tmp_path, subject):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    tests = tmp_path / "profile" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_mine.py").write_text("def test_pinned():\n    assert 1 == 2\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", subject], check=True)


def test_the_check_runs_once_for_each_sync_whichever_copy_ran_it(tmp_path, capsys):
    _repo(tmp_path, "Sync from the app: 3 new commit(s)")
    sync_app.own_tests_after_sync(str(tmp_path))
    assert "Your own tests: 1 now fail" in capsys.readouterr().out
    sync_app.own_tests_after_sync(str(tmp_path))          # the same sync: not again
    assert capsys.readouterr().out == ""


def test_a_commit_that_is_not_a_sync_runs_nothing(tmp_path, capsys):
    _repo(tmp_path, "The person's own work")
    sync_app.own_tests_after_sync(str(tmp_path))
    assert capsys.readouterr().out == ""


def test_the_offline_seam_answers_and_puts_everything_back():
    from offline_boards import offline
    from openroles import _http
    before = _http.request
    with offline(routes={"acme.example/jobs": {"jobs": []}},
                 robots={"acme.example": (200, "User-agent: *\nDisallow: /\n")}) as web:
        assert _http.request("https://acme.example/jobs") == ({"jobs": []}, None)
        assert _http.request("https://other.example/") == (None, "HTTP 404")
        assert _http.robots_txt("acme.example")[0] == 200 and _http.robots_txt("x.example") == (404, "")
        assert [u for u, _ in web.calls] == ["https://acme.example/jobs", "https://other.example/"]
    assert _http.request is before


def test_a_persons_tests_are_tried_on_a_tree_before_it_ships(tmp_path, monkeypatch, capsys):
    import try_personal_tests
    person, app = tmp_path / "person", tmp_path / "app"
    _repo(person, "their work")
    subprocess.run(["git", "init", "-q", str(app)], check=True)
    (app / "tools").mkdir()
    (app / "tools" / "placeholder.py").write_text("")
    subprocess.run(["git", "-C", str(app), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(app), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "app"], check=True)
    monkeypatch.setattr(try_personal_tests, "HERE", str(app))
    assert try_personal_tests.main([str(person), "--ref", "HEAD"]) == 1
    assert "Your own tests: 1 now fail" in capsys.readouterr().out
    assert subprocess.run(["git", "-C", str(person), "status", "--porcelain"],
                          capture_output=True, text=True).stdout == ""      # nothing changed there


def test_a_test_reaching_into_private_parts_is_noted_before_it_breaks(tmp_path):
    tests = tmp_path / "profile" / "tests"
    tests.mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ats_boards.py").write_text("")
    (tmp_path / "tools" / "fit.py").write_text("")
    (tests / "test_reaching.py").write_text(
        "from unittest import mock\nimport ats_boards as A\nfrom fit import _core_points, score\n"
        "def test_a():\n    A._ROBOTS.clear()\n    A.FETCH\n"
        "    with mock.patch('ats_boards._request'), mock.patch.object(A, '_get'):\n        pass\n")
    (tests / "test_public.py").write_text("import ats_boards\ndef test_b():\n    ats_boards.FETCH\n")
    risks = sync_app.own_test_risks(str(tmp_path))
    assert risks == {os.path.join("profile", "tests", "test_reaching.py"): [
        "ats_boards._ROBOTS", "ats_boards._get", "ats_boards._request", "fit._core_points"]}
    note = sync_app.own_test_risks_report(risks)
    assert note.startswith("Note: 1 of your own test file(s) reach into private parts of the app")
    assert "tools/offline_boards.py" in note and "keeping every assertion" in note
    assert sync_app.own_test_risks_report({}) == ""


def test_the_error_itself_says_what_a_removed_private_name_means():
    import ats_boards
    try:
        _ = ats_boards._ROBOTS
    except AttributeError as e:
        text = str(e)
    assert text.startswith("module 'ats_boards' has no attribute '_ROBOTS'")
    assert "tools/offline_boards.py" in text and "--own-tests" in text
    assert sync_app._gone(ROOT, f"AttributeError: {text}") == "ats_boards._ROBOTS"


def test_ci_says_what_to_do_when_a_persons_own_tests_fail():
    ci = open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8").read()
    # "$PY": the person's own Python for this repo where there is one, else python3.
    assert '"$PY" tools/sync_app.py --own-tests' in ci
    assert '"$PY" tools/sync_app.py --own-test-risks' in ci
