"""A better way of doing any part of the build reaches every repo that has the old result.

The maintainer set up on the first release and kept two weak job boards for days after
the app learned to research and build the boards that serve a person's market: nothing
told his profile the method had improved, and he could not know to ask. The same was true
of every prep document, unsent draft and exclusion the older code had made. These tests
make that impossible to forget:

- every app file is either part of a versioned method or listed with the reason it keeps
  nothing, so a new file cannot slip past;
- a method's text cannot change without a new version saying what changed and whether
  what an older version made should be made again;
- a repo behind on a re-run version gets a `method-<name>` upgrade, which /upgrade or the
  sync applies with no one asking, or the round applies by itself;
- a repo on the first release's sync is told to run the upgrades by the CHANGELOG lines
  its sync prints.
"""
from __future__ import annotations

import csv
import fnmatch
import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_versions as B  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import throttle  # noqa: E402
from personal_paths import is_personal  # noqa: E402
from tests import repo_files  # noqa: E402

SETUP = os.path.join(ROOT, B.SETUP)
SETUP_METHODS = [n for n, m in B.METHODS.items() if m.get("setup")]


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    state = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv(person.STATE_ENV, str(state))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _app_files() -> list[str]:
    names = repo_files.tracked(root=ROOT)
    if not names:
        pytest.skip("not a git checkout")
    return [f for f in names if not is_personal(f) and os.path.isfile(os.path.join(ROOT, f))]


# ------------------------------------------------------------------ nothing slips past

def test_every_app_file_is_in_a_method_or_says_why_it_keeps_nothing():
    owned = {f for name in B.METHODS for f in B.files(name)} | {B.SETUP}
    loose = [f for f in _app_files()
             if f not in owned and not any(fnmatch.fnmatch(f, g) for g in B.KEEPS_NOTHING)]
    assert loose == [], (
        "app files in no method of tools/build_versions.py and not in its KEEPS_NOTHING. "
        "If what the file does is kept in a person's repo (a profile value, a document, a "
        "record), add it to that method's files and a version; otherwise add it to "
        "KEEPS_NOTHING with the reason:\n  " + "\n  ".join(loose))


def test_every_keeps_nothing_entry_still_names_a_file():
    files = _app_files()
    dead = [g for g in B.KEEPS_NOTHING if not any(fnmatch.fnmatch(f, g) for f in files)]
    assert dead == [], dead


def test_every_method_file_exists_and_no_file_is_both():
    for name in B.METHODS:
        got = B.files(name)
        assert got or B.METHODS[name].get("setup"), name
        for f in got:
            assert os.path.isfile(os.path.join(ROOT, f)), f"{name}: {f}"
            both = [g for g in B.KEEPS_NOTHING if fnmatch.fnmatch(f, g)]
            assert not both, f"{f} is in {name} and in KEEPS_NOTHING {both}"


# ------------------------------------------------------------------ no change unversioned

def test_no_method_changes_without_a_version_saying_what_changed():
    stale = []
    for name, m in B.METHODS.items():
        now = B.fingerprint(name)
        if now != m["fingerprint"]:
            stale.append(
                f"{name}: add ({B.current(name) + 1}, \"<today>\", <rerun>, \"<what changed>\") "
                f"to its versions in tools/build_versions.py, rerun True if what an older "
                f"version made should be made again, False for wording; set its fingerprint "
                f"to {now!r}; record it in profile.example/{B.RECORD}")
    assert stale == [], "\n".join(stale)


def test_every_instruction_that_writes_the_profile_is_in_a_section():
    lines = open(SETUP, encoding="utf-8").read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## Step 1"))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("## Step 4"))
    inside, loose = None, []
    for n in range(start, end):
        ln = lines[n]
        m = re.match(r"^<!-- section: ([a-z-]+) -->", ln)
        if m:
            inside = m.group(1)
            continue
        if ln.startswith("<!-- /section -->"):
            inside = None
            continue
        if inside is None and (ln.startswith("- **") or ln.startswith("### ")):
            loose.append(f"{B.SETUP}:{n + 1}: {ln[:60]}")
    assert loose == [], "instructions in no section:\n" + "\n".join(loose)
    assert lines[start + 1].startswith("<!-- section: ")


def test_every_marked_section_is_a_setup_method_and_every_one_is_marked():
    marked = set(B.regions())
    assert marked <= set(SETUP_METHODS) | {B.NOT_VERSIONED}, marked - set(SETUP_METHODS)
    assert set(SETUP_METHODS) <= marked
    for name in SETUP_METHODS:
        assert B.METHODS[name]["run"] == f"/setup --section {name}"


def test_versions_count_up_from_the_first_release_and_say_who_redoes_them():
    for name, m in B.METHODS.items():
        nums = [v[0] for v in m["versions"]]
        assert nums == list(range(1, len(nums) + 1)), name
        assert m["versions"][0][1] == B.FIRST_RELEASE
        for _, day, rerun, what in m["versions"]:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and isinstance(rerun, bool) and what
        assert m["by"] in ("upgrade", "instant", "round", "network", "you"), name
        assert m["gives"] and m["run"] and m["priority"] in (1, 2, 3, 4), name
        assert m.get("applies") is None or m["applies"] in B.APPLIES, name
        if m["by"] == "instant":
            assert m["command"] and m["paths"], name
        if m["by"] == "you":
            assert m.get("ask"), name


def test_the_example_holds_every_current_version():
    data = json.load(open(os.path.join(ROOT, "profile.example", B.RECORD), encoding="utf-8"))
    assert {k: v["version"] for k, v in data.items()} == {n: B.current(n) for n in B.METHODS}


# ------------------------------------------------------------------ it reaches them

def test_a_profile_from_the_first_release_redoes_what_got_better(profile):
    (profile / B.RECORD).unlink()
    pending = {u.id for u, _ in U.pending()}
    rerun = {f"method-{n}" for n in SETUP_METHODS
             if any(v[2] for v in B.METHODS[n]["versions"][1:])}
    assert rerun and rerun <= pending
    why = U.by_id("method-boards").pending()
    # Said as what is better now, never as version numbers: this line reaches the person.
    assert why.startswith("made the older way; now ") and "version" not in why


def test_a_profile_made_after_a_version_is_not_asked_to_redo_it(profile, monkeypatch):
    (profile / B.RECORD).unlink()
    monkeypatch.setattr(B, "_born", lambda: "2026-10-16")
    assert B.behind("boards") == []
    assert U.by_id("method-boards").pending() == ""
    monkeypatch.setattr(B, "_born", lambda: "2026-10-15")      # same day: redo, to be safe
    assert B.behind("boards")


def test_recording_settles_it(profile):
    (profile / B.RECORD).unlink()
    B.record(["boards"], today="2026-10-20")
    assert U.by_id("method-boards").pending() == ""
    assert U.by_id("method-search").pending()
    data = json.load(open(profile / B.RECORD, encoding="utf-8"))
    assert data["boards"] == {"version": B.current("boards"), "date": "2026-10-20"}


def test_a_wording_change_costs_nobody_a_rerun(profile, monkeypatch):
    n = B.current("boards")
    m = dict(B.METHODS["boards"])
    m["versions"] = m["versions"] + ((n + 1, "2026-11-01", False, "wording"),)
    monkeypatch.setitem(B.METHODS, "boards", m)
    assert B.behind("boards") == []                          # a wording version asks nothing
    m["versions"] = m["versions"] + ((n + 2, "2026-12-01", True, "a better board search"),)
    assert [v[0] for v in B.behind("boards")] == [n + 2]
    assert "a better board search" in U.by_id("method-boards").pending()


def test_a_method_with_nothing_made_has_nothing_to_redo(profile, monkeypatch):
    m = dict(B.METHODS["interview"])
    m["versions"] = m["versions"] + ((B.current("interview") + 1, "2026-11-01", True,
                                      "a better pack"),)
    monkeypatch.setitem(B.METHODS, "interview", m)
    tracker = person.state("job_search_tracker.csv")
    rows = list(csv.DictReader(open(tracker, encoding="utf-8", newline="")))
    for r in rows:
        r["status"] = "rejected"
    with open(tracker, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert B.behind("interview") and not B.applies("interview")
    assert U.by_id("method-interview").pending() == ""
    rows[0]["status"] = "interview"
    with open(tracker, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert "a better pack" in U.by_id("method-interview").pending()


def test_an_instant_method_is_redone_by_the_sync_and_recorded(profile):
    u = U.by_id("method-prep-docs")
    assert u.cost == "instant" and u.needs == "nobody"
    assert u.command == ("python3", "tools/build_versions.py", "redo", "prep-docs")
    assert f"profile/{B.RECORD}" in u.paths and "documents/network/*" in u.paths


def test_screening_is_redone_by_every_round_with_no_upgrade(monkeypatch):
    assert "method-screening" not in {u.id for u in U.REGISTRY}
    entries = {"https://example.com/a": {"title": "Analyst", "company": "Acme",
                                         "status": "excluded", "first_seen": "2026-09-01",
                                         "exclusion_reason": "eligibility gate: citizenship"},
               "https://example.com/b": {"title": "Planner", "company": "Acme",
                                         "status": "excluded", "first_seen": "2026-09-01",
                                         "exclusion_reason": "posting closed"}}
    urls, _ = throttle.ruled_out(entries)
    assert len(urls) == 2                                    # no re-run version: both block
    m = dict(B.METHODS["screening"])
    m["versions"] = m["versions"] + ((2, "2026-11-01", True, "a better screen"),)
    monkeypatch.setitem(B.METHODS, "screening", m)
    urls, _ = throttle.ruled_out(entries)
    assert list(urls) == [throttle.norm("https://example.com/b")]   # a fact still blocks
    entries["https://example.com/a"]["excluded_date"] = "2026-11-02"
    urls, _ = throttle.ruled_out(entries)
    assert len(urls) == 2                                    # decided by the new screen


def test_upgrade_and_setup_record_what_they_redid():
    cmd = open(os.path.join(ROOT, ".claude", "commands", "upgrade.md"), encoding="utf-8").read()
    assert "python3 tools/build_versions.py record <name>" in cmd
    setup = open(SETUP, encoding="utf-8").read()
    assert "python3 tools/build_versions.py record --setup" in setup
    assert "python3 tools/build_versions.py record <section>" in setup


# ------------------------------------------------------------------ old repos hear of it

def test_a_first_release_sync_prints_the_line_that_starts_the_upgrades():
    """The first release's sync_app prints the first 12 non-empty lines a sync adds to
    the CHANGELOG, and runs nothing. Lines added at the very top come first, so the
    instruction sits above every entry and stays there however many entries follow."""
    lines = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read().splitlines()
    assert lines[0] == "# Changelog"
    top = [ln for ln in lines[1:] if ln.strip()][:12]
    first = "\n".join(top)
    assert "python3 tools/profile_upgrades.py --after-sync" in first
    assert first.lstrip().startswith("> **Claude")


def test_the_listing_tells_the_session_what_to_do(profile):
    (profile / B.RECORD).unlink()
    text = U.block(U.pending())
    assert "Claude: start a background agent now that follows .claude/commands/upgrade.md" in text
    assert "at most three" in text
