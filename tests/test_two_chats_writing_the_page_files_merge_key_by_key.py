"""Two chats writing the page's own files at once merge key by key, never stop on a line.

The 4.0 page added files two chats can both write: the answers given on the page
(profile/setup_answers.json), the page's address and the suggestions turned down
(profile/app.json), the person's settings (profile/person.json), their own Tweak buttons
(profile/tweaks.json) and the record of every tweak to one output (tweaks.json beside it).
Each is merged by tools/merge_state.py the way its writer uses it (JSON_FILES), and every
input here is made by that file's own writer, in a real git repo, merged by real git.

Every person, employer and page here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import app_actions  # noqa: E402
import app_alerts  # noqa: E402
import app_setup  # noqa: E402
import merge_state as M  # noqa: E402
import person  # noqa: E402
import told  # noqa: E402
import tweak  # noqa: E402

NOW = dt.datetime(2026, 10, 25, 17, 30, tzinfo=dt.timezone.utc)
PAGE = "https://claude.ai/artifact/an-invented-page"
OTHER_PAGE = "https://claude.ai/artifact/another-invented-page"
FILES = ("profile/app.json", "profile/setup_answers.json", "profile/person.json",
         "profile/tweaks.json", "documents/applications/oakmere_demand/tweaks.json",
         "documents/network/juno_castellan/tweaks.json")


# ------------------------------------------------------------------ a repo, two chats


class Repo:
    """A person's copy with the driver set up: `side()` checks out one chat's branch, and
    `commit(when)` saves what its writers wrote there at that moment."""

    def __init__(self, tmp_path, monkeypatch):
        self.root = str(tmp_path / "copy")
        os.makedirs(os.path.join(self.root, "tools"))
        for f in ("tools/merge_state.py", ".gitattributes"):
            shutil.copyfile(os.path.join(ROOT, f), os.path.join(self.root, f))
        self.profile = os.path.join(self.root, "profile")
        os.makedirs(self.profile)
        monkeypatch.setenv(person.ENV, self.profile)
        monkeypatch.setenv(person.STATE_ENV, self.root)
        person.reset()
        self.git("init", "-q", "-b", "master")
        M.install(self.root)

    def git(self, *args, when="2026-10-25T09:00:00Z"):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
                   GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        return subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)

    def commit(self, msg, when="2026-10-25T09:00:00Z"):
        self.git("add", "-A")
        r = self.git("commit", "-qm", msg, when=when)
        assert r.returncode == 0, r.stdout + r.stderr
        person.reset()

    def side(self, branch, new=False):
        r = self.git("checkout", "-q", *(["-b"] if new else []), branch)
        assert r.returncode == 0, r.stdout + r.stderr
        os.makedirs(self.profile, exist_ok=True)
        person.reset()

    def merge(self, branch="other"):
        return self.git("merge", "--no-edit", branch, when="2026-10-25T20:00:00Z")

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
            return fh.read()

    def unmerged(self):
        return self.git("diff", "--name-only", "--diff-filter=U").stdout.split()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    yield Repo(tmp_path, monkeypatch)
    person.reset()


def answer(step, value, at):
    """The page's answer to one setup step, applied by the app's own handler."""
    r = app_actions.Run("a", {"at": at, "value": value}, {"step": step}, {}, None, "chat",
                        "UTC", NOW)
    return app_actions._setup_answer(r)


def undo(step, before, at):
    r = app_actions.Run("u", {"at": at, "value": {"before": before}}, {"step": step}, {}, None,
                        "chat", "UTC", NOW)
    return app_actions._setup_restore(r)


def the_person(repo, **extra):
    data = {"identity": {"name": "Rowan Example", "country": "GB"}, "suggestions": "on",
            **extra}
    with open(os.path.join(repo.profile, "person.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def tweak_where(repo, slug="oakmere_demand"):
    folder = os.path.join(repo.root, "documents", "applications", slug)
    os.makedirs(folder, exist_ok=True)
    return {"output": "resume", "item": {"id": slug}, "folder": folder,
            "file": os.path.join(folder, "draft.json")}


def log_tweak(where, key, at, colour):
    """A tweak's record, kept the way tweak.apply keeps it."""
    data = tweak.log(where)
    data[key] = {"at": at, "output": where["output"], "changes": [{"p": "R5", "v": colour}],
                 "before_md5": "b" * 8, "result_md5": key[:8], "said": [f"colour {colour}"],
                 "checks": "verify_batch: clean"}
    tweak._save_log(where, data)


# ------------------------------------------------------------------ different keys


def test_answers_two_chats_gave_to_different_steps_are_both_kept(repo):
    """Neither chat had answered anything before: both create the file, and git hands the
    driver an empty ancestor."""
    with open(os.path.join(repo.root, "README"), "w", encoding="utf-8") as fh:
        fh.write("a copy\n")
    repo.commit("base")
    repo.side("other", new=True)
    answer("pay", {"now": "38000", "least": "40000"}, "2026-10-25T17:01:00Z")
    repo.commit("pay on the cloud chat")
    repo.side("master")
    answer("work", {"work": "Supply chain analyst", "place": "Leeds, UK"}, "2026-10-25T17:02:00Z")
    answer("roles", {"roles": ["Demand planner", "Supply analyst"]}, "2026-10-25T17:03:00Z")
    repo.commit("work and roles on the computer chat")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(repo.read("profile/setup_answers.json"))
    assert set(got) == {"pay", "work", "roles"}
    assert got["pay"]["least"] == "40000" and got["work"]["place"] == "Leeds, UK"
    assert got["roles"]["roles"] == ["Demand planner", "Supply analyst"]
    # Written as its writer writes it: saving it again changes no line.
    app_setup.save_answers(app_setup.answers())
    assert repo.git("status", "--porcelain").stdout == ""


def test_the_pages_address_and_a_suggestion_turned_down_meet_cleanly(repo):
    app_alerts.dismiss("ready~oakmere", "ready", dt.date(2026, 10, 20))
    repo.commit("base")
    repo.side("other", new=True)
    app_setup.record_page(PAGE, chat="cloud-1", now=NOW)
    repo.commit("published")
    repo.side("master")
    app_alerts.dismiss("jobs~fernhill", "jobs", dt.date(2026, 10, 25))
    repo.commit("no thanks")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(repo.read("profile/app.json"))
    assert got["url"] == PAGE and got["by"] == "cloud-1"
    assert set(got["suggest_no"]) == {"ready~oakmere", "jobs~fernhill"}
    assert set(app_alerts.dismissed()) == {"ready~oakmere", "jobs~fernhill"}


def test_a_setting_and_a_place_an_employer_heard_meet_cleanly(repo):
    the_person(repo)
    repo.commit("base")
    repo.side("other", new=True)
    told.record("Oakmere Foods", "Leeds")
    repo.commit("told")
    repo.side("master")
    app_actions._save_person_json("suggestions", "urgent")
    repo.commit("setting")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(repo.read("profile/person.json"))
    assert got["suggestions"] == "urgent"
    assert got["identity"]["places_told"] == {"Oakmere Foods": "Leeds"}
    assert got["identity"]["name"] == "Rowan Example"
    app_actions._save_person_json("suggestions", "urgent")      # its writer's format
    assert repo.git("status", "--porcelain").stdout == ""


# ------------------------------------------------------------------ the same key


def test_one_answer_both_chats_changed_takes_the_one_given_later(repo):
    """The answer's own time decides, not when each chat saved: here the chat that saved
    last holds the earlier answer."""
    answer("work", {"work": "Analyst", "place": "Leeds, UK"}, "2026-10-25T16:00:00Z")
    repo.commit("base")
    repo.side("other", new=True)
    answer("work", {"work": "Demand planner", "place": "York, UK"}, "2026-10-25T17:01:00Z")
    repo.commit("an earlier answer, saved last", when="2026-10-25T19:00:00Z")
    repo.side("master")
    answer("work", {"work": "Supply chain analyst", "place": "Hull, UK"}, "2026-10-25T17:05:00Z")
    repo.commit("the later answer, saved first", when="2026-10-25T18:00:00Z")
    r = repo.merge()
    said = r.stdout + r.stderr
    assert r.returncode == 0, said
    got = json.loads(repo.read("profile/setup_answers.json"))["work"]
    assert got == {"work": "Supply chain analyst", "place": "Hull, UK",
                   "at": "2026-10-25T17:05:00Z"}
    assert "kept 'Supply chain analyst', the later change" in said
    assert "2026-10-25T17:05:00Z" in said and "the other side had 'Demand planner'" in said
    assert "Claude: tell the person in plain words" in said
    # And the other way round: the later answer is kept whichever side holds it.
    repo.git("reset", "-q", "--hard", "HEAD~1")
    repo.side("other")
    r = repo.merge("master")
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(repo.read("profile/setup_answers.json"))["work"]["place"] == "Hull, UK"


def test_both_chats_giving_the_same_answer_is_no_conflict(repo):
    answer("pay", {"now": "38000", "least": "40000"}, "2026-10-25T16:00:00Z")
    repo.commit("base")
    repo.side("other", new=True)
    told_twice = {"roles": ["Demand planner"]}
    answer("roles", told_twice, "2026-10-25T17:01:00Z")
    repo.commit("theirs")
    repo.side("master")
    answer("roles", told_twice, "2026-10-25T17:01:00Z")
    repo.commit("ours")
    r = repo.merge()
    assert r.returncode == 0 and "merge_state:" not in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_setting_both_chats_changed_takes_the_later_saved_one(repo):
    """person.json dates nothing it holds, so each chat's own history says which came later,
    as it does for a row of the tracker."""
    the_person(repo)
    repo.commit("base")
    repo.side("other", new=True)
    app_actions._save_person_json("suggestions", "off")
    repo.commit("off", when="2026-10-25T15:00:00Z")
    repo.side("master")
    app_actions._save_person_json("suggestions", "urgent")
    repo.commit("urgent", when="2026-10-25T11:00:00Z")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(repo.read("profile/person.json"))["suggestions"] == "off"
    assert "kept 'off', the later change" in r.stdout + r.stderr


def test_the_same_tweak_recorded_by_two_chats_keeps_the_later_run(repo):
    where = tweak_where(repo)
    log_tweak(where, "k1aaaaaaaa", "2026-10-25T10:00:00Z", "navy")
    repo.commit("base")
    repo.side("other", new=True)
    log_tweak(tweak_where(repo), "k2bbbbbbbb", "2026-10-25T17:01:00Z", "teal")
    repo.commit("theirs", when="2026-10-25T19:00:00Z")
    repo.side("master")
    log_tweak(tweak_where(repo), "k2bbbbbbbb", "2026-10-25T17:09:00Z", "plum")
    repo.commit("ours", when="2026-10-25T18:00:00Z")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = tweak.log(where)
    assert set(got) == {"k1aaaaaaaa", "k2bbbbbbbb"}
    assert got["k2bbbbbbbb"]["at"] == "2026-10-25T17:09:00Z"
    assert got["k2bbbbbbbb"]["said"] == ["colour plum"]


# ------------------------------------------------------------------ lists only added to


def test_jobs_told_a_job_at_a_time_on_two_chats_are_all_kept_once(repo):
    answer("history", {"text": "Planner at Quayside Foods, 2022 to now"}, "2026-10-25T16:00:00Z")
    repo.commit("base")
    repo.side("other", new=True)
    answer("history", {"text": "Analyst at Larkspur Retail, 2019 to 2022"},
           "2026-10-25T17:01:00Z")
    answer("history", {"text": "Intern at Lanternfish, 2018"}, "2026-10-25T17:02:00Z")
    repo.commit("theirs")
    repo.side("master")
    answer("history", {"text": "Analyst at Larkspur Retail, 2019 to 2022"},
           "2026-10-25T17:03:00Z")
    answer("history", {"text": "Clerk at Fernhill Freight, 2017"}, "2026-10-25T17:04:00Z")
    repo.commit("ours")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = app_setup.answers()["history"]
    assert got["jobs"] == ["Planner at Quayside Foods, 2022 to now",
                           "Analyst at Larkspur Retail, 2019 to 2022",
                           "Clerk at Fernhill Freight, 2017", "Intern at Lanternfish, 2018"]
    assert got["at"] == "2026-10-25T17:04:00Z"


def test_buttons_and_tweak_records_two_chats_added_are_all_kept(repo):
    tweak.add_button({"output": "letter", "label": "Warmer", "text": "a little warmer"},
                     dt.date(2026, 10, 20))
    where = tweak_where(repo, "juno_castellan")
    log_tweak(where, "k0cccccccc", "2026-10-25T10:00:00Z", "navy")
    repo.commit("base")
    repo.side("other", new=True)
    tweak.add_button({"output": "resume", "label": "Shorter", "text": "one line shorter"},
                     dt.date(2026, 10, 25))
    log_tweak(tweak_where(repo, "juno_castellan"), "k1dddddddd", "2026-10-25T17:01:00Z", "teal")
    repo.commit("theirs")
    repo.side("master")
    tweak.add_button({"output": "message", "label": "Brief", "text": "keep it brief"},
                     dt.date(2026, 10, 25))
    log_tweak(tweak_where(repo, "juno_castellan"), "k2eeeeeeee", "2026-10-25T17:02:00Z", "plum")
    repo.commit("ours")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    assert [b["label"] for b in tweak.buttons()] == ["Warmer", "Brief", "Shorter"]
    assert set(tweak.log(where)) == {"k0cccccccc", "k1dddddddd", "k2eeeeeeee"}
    tweak._save_log(where, tweak.log(where))                    # its writer's format
    assert repo.git("status", "--porcelain").stdout == ""


# ------------------------------------------------------------------ taken away on one side


def test_a_suggestion_offered_again_on_one_chat_stays_offered(repo):
    app_alerts.dismiss("ready~oakmere", "ready", dt.date(2026, 10, 20))
    app_alerts.dismiss("jobs~fernhill", "jobs", dt.date(2026, 10, 21))
    repo.commit("base")
    repo.side("other", new=True)
    app_alerts.dismiss("people~larkspur", "people", dt.date(2026, 10, 25))
    app_setup.record_page(PAGE, chat="cloud-1", now=NOW)
    repo.commit("theirs")
    repo.side("master")
    app_alerts.undismiss("ready~oakmere")
    repo.commit("offered again")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    assert set(app_alerts.dismissed()) == {"jobs~fernhill", "people~larkspur"}
    assert app_setup.page_record()["url"] == PAGE


def test_a_job_taken_back_on_one_chat_stays_out_while_the_other_adds_one(repo):
    """An undo puts the step back as it was, with its older time: that time says nothing of
    when the undo was made, so each chat's own history settles the step's time."""
    answer("history", {"text": "Planner at Quayside Foods"}, "2026-10-25T16:00:00Z")
    before = app_setup.answers()["history"]
    answer("history", {"text": "A job typed by mistake"}, "2026-10-25T16:05:00Z")
    repo.commit("base")
    repo.side("other", new=True)
    answer("history", {"text": "Analyst at Larkspur Retail"}, "2026-10-25T17:01:00Z")
    repo.commit("theirs", when="2026-10-25T17:02:00Z")
    repo.side("master")
    undo("history", before, "2026-10-25T17:10:00Z")
    repo.commit("taken back", when="2026-10-25T17:11:00Z")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    got = app_setup.answers()["history"]
    assert got["jobs"] == ["Planner at Quayside Foods", "Analyst at Larkspur Retail"]


def test_a_button_one_chat_took_off_stays_off(repo):
    for label, day in (("Warmer", 18), ("Plainer", 19)):
        tweak.add_button({"output": "letter", "label": label, "text": label.lower() + " please"},
                         dt.date(2026, 10, day))
    repo.commit("base")
    repo.side("other", new=True)
    tweak.add_button({"output": "resume", "label": "Shorter", "text": "shorter please"},
                     dt.date(2026, 10, 25))
    repo.commit("theirs")
    repo.side("master")
    # A third letter button: the oldest of the kind goes.
    tweak.add_button({"output": "letter", "label": "Bolder", "text": "bolder please"},
                     dt.date(2026, 10, 25))
    repo.commit("ours")
    r = repo.merge()
    assert r.returncode == 0, r.stdout + r.stderr
    assert [b["label"] for b in tweak.buttons()] == ["Plainer", "Bolder", "Shorter"]


# ------------------------------------------------------------------ nothing says which


def test_a_setting_changed_two_ways_at_one_moment_stops_the_merge_for_a_person(repo):
    the_person(repo)
    repo.commit("base")
    repo.side("other", new=True)
    app_actions._save_person_json("suggestions", "off")
    told.record("Oakmere Foods", "Leeds")
    repo.commit("theirs", when="2026-10-25T15:00:00Z")
    repo.side("master")
    app_actions._save_person_json("suggestions", "urgent")
    repo.commit("ours", when="2026-10-25T15:00:00Z")
    r = repo.merge()
    said = r.stdout + r.stderr
    assert r.returncode != 0, said
    assert repo.unmerged() == ["profile/person.json"]
    assert "suggestions" in said and "'urgent'" in said and "'off'" in said
    assert "the later change" not in said
    got = json.loads(repo.read("profile/person.json"))          # still JSON, for a person
    assert got["suggestions"] == "urgent"
    assert got["identity"]["places_told"] == {"Oakmere Foods": "Leeds"}


def test_an_answer_changed_two_ways_with_the_same_time_stops_the_merge(repo):
    answer("work", {"work": "Analyst", "place": "Leeds, UK"}, "2026-10-25T16:00:00Z")
    repo.commit("base")
    repo.side("other", new=True)
    answer("work", {"work": "Analyst", "place": "York, UK"}, "2026-10-25T17:01:00Z")
    repo.commit("theirs", when="2026-10-25T17:30:00Z")
    repo.side("master")
    answer("work", {"work": "Analyst", "place": "Hull, UK"}, "2026-10-25T17:01:00Z")
    repo.commit("ours", when="2026-10-25T17:30:00Z")
    r = repo.merge()
    assert r.returncode != 0, r.stdout + r.stderr
    assert repo.unmerged() == ["profile/setup_answers.json"]
    assert "work/place" in r.stdout + r.stderr


# ------------------------------------------------------------------ the rules, without git


def test_a_key_either_side_added_inside_a_record_is_kept():
    base = {"resume": {"source": "build", "at": "2026-10-25T16:00:00Z"}}
    ours = {"resume": {"source": "asset", "asset": "a1", "at": "2026-10-25T17:00:00Z"}}
    theirs = {"resume": {"source": "pasted", "file": "documents/cv/r.txt",
                         "at": "2026-10-25T17:05:00Z"}}
    settled = []
    text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                             "profile/setup_answers.json", settled=settled)
    assert not problems
    got = json.loads(text)["resume"]
    assert got["source"] == "pasted" and got["at"] == "2026-10-25T17:05:00Z"
    assert got["asset"] == "a1" and got["file"] == "documents/cv/r.txt"
    assert any("kept 'pasted'" in s and "'asset'" in s for s in settled)


def test_an_answer_given_again_later_holds_even_where_it_is_the_first_answer_again():
    """The later answer is the person's word for every field it holds, also one they gave
    as before while the other chat changed it earlier."""
    base = {"work": {"work": "Analyst", "place": "Leeds, UK", "at": "2026-10-25T16:00:00Z"}}
    earlier = {"work": {"work": "Planner", "place": "York, UK", "at": "2026-10-25T17:01:00Z"}}
    later = {"work": {"work": "Analyst", "place": "Hull, UK", "at": "2026-10-25T17:05:00Z"}}
    for ours, theirs in ((later, earlier), (earlier, later)):
        settled = []
        text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                                 "profile/setup_answers.json", settled=settled)
        assert not problems
        assert json.loads(text)["work"] == later["work"]
        assert any("work/work" in s and "'Planner'" in s and "written later" in s
                   for s in settled)


def test_a_date_that_went_back_says_nothing_and_history_decides():
    base = {"pay": {"least": "45000", "at": "2026-10-25T16:00:00Z"}}
    restored = {"pay": {"least": "40000", "at": "2026-10-25T15:00:00Z"}}     # an undo
    newer = {"pay": {"least": "42000", "at": "2026-10-25T17:00:00Z"}}
    _text, problems = M.merge(json.dumps(base), json.dumps(restored), json.dumps(newer),
                              "profile/setup_answers.json")
    assert problems and any("pay/least" in p for p in problems)
    text, problems = M.merge(json.dumps(base), json.dumps(restored), json.dumps(newer),
                             "profile/setup_answers.json", later=lambda p, o, t: "ours")
    assert not problems and json.loads(text)["pay"]["least"] == "40000"


def test_a_step_one_chat_took_back_and_the_other_answered_again_is_left_for_a_person():
    base = {"work": {"work": "Analyst", "at": "2026-10-25T16:00:00Z"}}
    ours = {}
    theirs = {"work": {"work": "Planner", "at": "2026-10-25T17:00:00Z"}}
    _text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                              "profile/setup_answers.json")
    assert problems == ["work (removed on one side, changed on the other)"]


def test_each_file_is_merged_by_where_it_sits():
    assert M.json_rules("profile/tweaks.json")["lists"] == {"buttons": ("id",)}
    out = M.json_rules("documents/applications/oakmere_demand/tweaks.json")
    assert out["stamps"] == ("at",) and out["sort"] == "all" and out["indent"] == 1
    assert M.json_rules("documents/applications/a/b/tweaks.json") == M._JSON_DEFAULT
    assert M.json_rules("profile/learned.json")["lists"] == M.LIST_KEYS["learned.json"]
    assert M.json_rules("tweaks.json")["lists"] is None


def test_every_page_file_is_wired_to_the_driver():
    r = subprocess.run(["git", "-C", ROOT, "check-attr", "merge", "--", *FILES],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert [ln.rsplit(": ", 1)[-1] for ln in r.stdout.splitlines()] == ["ljs-state"] * len(FILES)
