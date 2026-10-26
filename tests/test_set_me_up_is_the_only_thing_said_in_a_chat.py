""""Set me up" is the only thing the person says in a chat: the rest is asked on their page.

`app.py start` is the one entry point for every state a copy can be in, and prints what the
chat does next; the model's `setup` section is /setup's questions as the page asks them,
one at a time, never asked twice; the answers reach the repo through `app.py apply`, and
/setup reads them from profile/setup_answers.json. What only the person can do outside the
page is a card with the registry's own steps. Every person, employer and repository here is
invented, and nothing reaches GitHub: a stand-in `gh` answers where one is needed.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_setup  # noqa: E402
import app_state  # noqa: E402
import claude_surfaces  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW


class Copy:
    """A person's copy in folders of its own: its profile (none yet, or a copy of the
    example's), its state, a dump of its page's database."""

    def __init__(self, root, profile=False, kind="private"):
        self.root = root
        self.state = os.path.join(root, "state")
        os.makedirs(self.state, exist_ok=True)
        self.profile = os.path.join(root, "profile")
        if profile:
            app_state.profile_copy(self.profile)
        self.dump = os.path.join(root, "dump")
        self.kind = kind
        self.path = os.environ.get("PATH", "")
        self.n = 0

    def env(self):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                   LJS_COPY=self.kind, PATH=self.path, GIT_AUTHOR_NAME="t",
                   GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com")
        for k in ("LJS_TODAY", "CLAUDE_CODE_REMOTE"):
            env.pop(k, None)
        return env

    def run(self, *args, ok=(0,)):
        r = subprocess.run([sys.executable, APP, *args], env=self.env(), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout

    def model(self):
        return json.loads(self.run("model", "--now", NOW))

    def step(self, sid):
        return next(s for s in self.model()["setup"]["steps"] if s["step"] == sid)

    def act(self, action, item, value=None, **extra):
        self.n += 1
        aid = f"act{self.n:02d}"
        rev = extra.pop("rev", None)
        if rev is None:
            m = self.model()
            items = m["setup"]["steps"] + m["needs_you"]
            if m["updates"].get("waiting"):
                items.append(m["updates"]["waiting"])
            items += m["updates"]["done"]
            rev = next((i["rev"] for i in items if i["id"] == item), "")
        doc = {"action": action, "item": item, "rev_seen": rev,
               "at": f"2026-10-25T17:{self.n:02d}:00Z", **extra}
        if value is not None:
            doc["value"] = value
        os.makedirs(os.path.join(self.dump, "actions"), exist_ok=True)
        with open(os.path.join(self.dump, "actions", aid + ".json"), "w", encoding="utf-8") as fh:
            json.dump(dict(doc, __version__=1), fh)
        return aid

    def apply(self, *extra):
        out = json.loads(self.run("apply", self.dump, "--chat", "cloud-1", "--now", NOW, *extra))
        # The receipts written back, as the next dump holds them.
        d = os.path.join(self.dump, "out", "files", "receipts")
        if os.path.isdir(d):
            os.makedirs(os.path.join(self.dump, "receipts"), exist_ok=True)
            for f in os.listdir(d):
                shutil.copy(os.path.join(d, f), os.path.join(self.dump, "receipts", f))
        return out

    def receipt(self, aid):
        with open(os.path.join(self.dump, "receipts", aid + ".json"), encoding="utf-8") as fh:
            return json.load(fh)

    def answers(self):
        try:
            with open(os.path.join(self.profile, "setup_answers.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            return {}

    def fake_gh(self, private=True):
        """A stand-in for GitHub's command: it records what it was asked, makes nothing."""
        bindir = os.path.join(self.root, "bin")
        os.makedirs(bindir, exist_ok=True)
        log = os.path.join(self.root, "gh_calls.txt")
        script = os.path.join(bindir, "gh")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n"
                     f'echo "$@" >> "{log}"\n'
                     'case "$1" in\n'
                     '  repo) echo "https://github.com/someone/my-job-search" ;;\n'
                     f'  api) echo "{"true" if private else "false"}" ;;\n'
                     "esac\n")
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        if os.name == "nt":
            # Windows runs no shell script by name: the same stand-in in Python, behind a
            # gh.cmd launcher, which is how a command is put on a Windows PATH.
            fake = os.path.join(bindir, "gh_fake.py")
            with open(fake, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("import sys\n"
                         f"open({log!r}, 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n"
                         "if sys.argv[1:2] == ['repo']:\n"
                         "    print('https://github.com/someone/my-job-search')\n"
                         "elif sys.argv[1:2] == ['api']:\n"
                         f"    print({'true' if private else 'false'!r})\n")
            with open(os.path.join(bindir, "gh.cmd"), "w", encoding="utf-8", newline="\r\n") as fh:
                fh.write(f'@"{sys.executable}" "{fake}" %*\n')
        self.path = bindir + os.pathsep + os.environ.get("PATH", "")
        return log


@pytest.fixture
def fresh(tmp_path):
    return Copy(str(tmp_path))


def test_a_copy_with_no_profile_gets_the_six_questions_one_at_a_time(fresh):
    m = fresh.model()
    assert app_model.check(m) == []
    s = m["setup"]
    assert s["state"] == "none" and s["next"] == "resume"
    assert s["progress"] == {"done": 0, "total": 6, "label": "1 of 6"}
    assert [x["step"] for x in s["steps"]] == list(app_setup.STEP_IDS)
    assert [x["kind"] for x in s["steps"]] == ["upload-or-paste", "text", "choice", "money",
                                                "multi", "text"]
    roles = next(x for x in s["steps"] if x["step"] == "roles")
    assert roles["status"] == "waiting" and roles["waiting"]
    # /setup's own target: under 400 words before the shortlist.
    words = sum(len((x["question"] + " " + x["help"]).split()) for x in s["steps"])
    assert words < app_setup.QUESTION_WORDS
    assert m["person"]["first_name"] == "" and m["jobs"]["rows"] == []
    assert [p["key"] for p in s["phases"]][:2] == ["copy", "questions"]


def test_an_answer_on_the_page_is_kept_and_never_asked_again(fresh):
    aid = fresh.act("setup.answer", "setup-work",
                    value={"work": "Supply chain analyst", "place": "Leeds, UK",
                           "ignored": "not a field"})
    assert fresh.apply()["ok"] == [aid]
    got = fresh.answers()["work"]
    assert got["work"] == "Supply chain analyst" and got["place"] == "Leeds, UK"
    assert "ignored" not in got
    step = fresh.step("work")
    assert step["status"] == "done" and step["known_from"] == "your answer"
    assert [f["value"] for f in step["fields"]] == ["Supply chain analyst", "Leeds, UK"]
    rtw = fresh.step("right_to_work")
    assert "Can you work in UK without" in rtw["question"]
    assert fresh.model()["setup"]["progress"]["label"] == "2 of 6"
    # Taken back: as it was before.
    undo = fresh.act("undo", "", undoes=aid, rev="")
    assert fresh.apply()["ok"] == [undo]
    assert "work" not in fresh.answers()
    assert fresh.step("work")["status"] == "next" or fresh.step("work")["status"] == "later"


def test_a_pasted_resume_goes_into_the_copy_and_leaves_the_page(fresh):
    aid = fresh.act("setup.resume", "setup-resume",
                    value={"text": "Morgan Ellis\nOperations Analyst, Fernhill Freight, 2021 to now"})
    got = fresh.apply()
    assert got["ok"] == [aid]
    saved = fresh.answers()["resume"]
    assert saved["source"] == "pasted" and saved["file"].startswith("documents/cv/resume_pasted_")
    with open(os.path.join(fresh.state, *saved["file"].split("/")), encoding="utf-8") as fh:
        assert "Fernhill Freight" in fh.read()
    with open(got["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    scrub = next(e for e in batch if e["collection"] == "actions")
    assert scrub["doc_id"] == aid and scrub["if_version"] == 1
    with open(scrub["file_path"], encoding="utf-8") as fh:
        assert json.load(fh) == {"value": {"text": {"__delete__": True}}}
    receipt = json.dumps(fresh.receipt(aid))
    assert "Fernhill" not in receipt
    assert fresh.step("resume")["status"] == "done"


def test_a_claimed_resume_leaves_the_page_with_the_claim(fresh):
    aid = fresh.act("setup.resume", "setup-resume", value={"text": "Morgan Ellis, analyst"})
    claimed = json.loads(fresh.run("apply", fresh.dump, "--chat", "c1", "--claim", "--now", NOW))
    with open(claimed["batches"][0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        body = json.load(fh)
    assert entry["doc_id"] == aid and body["value"] == {"text": {"__delete__": True}}


def test_a_resume_file_added_on_the_page_is_saved_then_taken_off_it(fresh):
    aid = fresh.act("setup.resume", "setup-resume", value={"asset": "a" * 32, "name": "cv.pdf"})
    assert fresh.apply()["ok"] == [aid]
    os.makedirs(fresh.profile, exist_ok=True)
    with open(os.path.join(fresh.profile, "app.json"), "w", encoding="utf-8") as fh:
        json.dump({"url": "https://claude.ai/code/artifact/example"}, fh)
    said = fresh.run("start", "--on", "test", "--tools", "none")
    assert "path " + "a" * 32 in said and "resume-saved" in said and "delete" in said
    f = os.path.join(fresh.state, "documents", "cv", "cv.pdf")
    os.makedirs(os.path.dirname(f))
    with open(f, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    fresh.run("resume-saved", f, "--asset", "a" * 32)
    got = fresh.answers()["resume"]
    assert got["file"] == "documents/cv/cv.pdf" and "asset" not in got
    assert "resume-saved" not in fresh.run("start", "--on", "test", "--tools", "none")


def test_building_a_resume_asks_one_job_at_a_time_on_the_page(fresh):
    aid = fresh.act("setup.build_resume", "setup-resume")
    assert fresh.apply()["ok"] == [aid]
    s = fresh.model()["setup"]
    assert [x["step"] for x in s["steps"]][:2] == ["resume", "history"]
    hist = s["steps"][1]
    assert hist["status"] == "next" and "newest job first" in hist["question"]
    assert "microphone" not in hist["question"] and "paste" not in hist["question"].lower()
    job = fresh.act("setup.answer", "setup-history",
                    value={"text": "Shift lead, Quayside Foods, Leeds, 2022 to now"})
    assert fresh.apply()["ok"] == [job]
    assert fresh.answers()["history"]["jobs"] == ["Shift lead, Quayside Foods, Leeds, 2022 to now"]
    assert "job before that" in fresh.step("history")["question"]
    end = fresh.act("setup.answer", "setup-history", value={"done": True})
    assert fresh.apply()["ok"] == [end]
    assert fresh.step("history")["status"] == "done"


def test_roles_are_asked_once_claude_has_proposed_them(fresh):
    fresh.run("propose", "Demand planning analyst", "Supply chain analyst")
    roles = fresh.step("roles")
    assert roles["status"] in ("next", "later") and roles["waiting"] is None
    assert [c[0] for c in roles["fields"][0]["choices"]] == ["Demand planning analyst",
                                                              "Supply chain analyst"]


def test_a_half_done_setup_is_prefilled_from_the_profile(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    with open(os.path.join(c.profile, "place.json"), "w", encoding="utf-8") as fh:
        json.dump({"works_on": "computer", "setup": {"started": "2026-10-24", "chat": "x"}}, fh)
    s = c.model()["setup"]
    assert s["state"] != "done"
    by = {x["step"]: x for x in s["steps"]}
    assert by["work"]["status"] == "done" and by["work"]["known_from"] == "your profile"
    assert by["work"]["fields"][1]["value"] == "Manchester, UK"
    assert by["pay"]["status"] == "done"
    assert s["progress"]["done"] == len(app_setup.STEP_IDS)


def test_a_finished_or_old_profile_is_never_set_up_again(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    s = c.model()["setup"]
    assert s["state"] == "done" and s["steps"] == []


def test_what_only_the_person_can_do_is_a_card_with_the_registrys_own_steps(tmp_path,
                                                                            monkeypatch):
    monkeypatch.setenv("LJS_COPY", "private")
    state = str(tmp_path / "state")
    os.makedirs(state)
    subprocess.run(["git", "init", "-q", state], check=True)
    monkeypatch.setenv("LJS_STATE", state)
    monkeypatch.setenv("LJS_PROFILE", str(tmp_path / "profile"))
    gitdir = app_setup._git_dir()
    with open(os.path.join(gitdir, app_setup.JOB_SITES), "w", encoding="utf-8") as fh:
        json.dump({"checked": "2026-10-25", "blocked": ["LinkedIn", "freehire"]}, fh)
    m, targets = app_model.build(*app_model.clock("2026-10-25", NOW))
    card = next(q for q in m["needs_you"] if q["id"] == "q-setup-job-sites")
    assert card["kind"] == "setup"
    # The registry's own steps, in their page wording (CAPABILITY_MAP G17: no "this chat").
    assert card["steps"] == claude_surfaces.steps("cloud-internet", page=True)[1:]
    assert card["link"] == claude_surfaces.official(claude_surfaces.entry("cloud-internet"))
    assert "LinkedIn" in card["body"] and card["checked"]
    assert [o["action"] for o in card["options"]] == ["setup.done"]
    # While they are in those settings: the one line that makes every new chat start faster.
    assert card["more"]["steps"] == claude_surfaces.steps("cloud-setup-script", page=True)[1:]
    assert card["more"]["copy"].startswith("apt-get update")
    # Once a later check finds the sites reachable, the card goes by itself.
    with open(os.path.join(gitdir, app_setup.JOB_SITES), "w", encoding="utf-8") as fh:
        json.dump({"checked": "2026-10-26", "blocked": []}, fh)
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert not [q for q in m["needs_you"] if q["id"] == "q-setup-job-sites"]
    monkeypatch.setenv("LJS_COPY", "app")
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    copy = next(q for q in m["needs_you"] if q["id"] == "q-setup-copy")
    assert copy["steps"] == claude_surfaces.steps("make-copy")[1:]
    # One tap opens GitHub's form filled in, Private chosen; the registry's step carries the
    # same link, so the card and the words never disagree.
    assert copy["open"]["url"] == app_setup.COPY_LINK and "visibility=private" in app_setup.COPY_LINK
    assert app_setup.COPY_LINK[len("https://"):] in claude_surfaces.steps("make-copy")[1]
    assert [o["action"] for o in copy["options"]] == ["setup.make_copy", "setup.done"]


# ------------------------------------------------------------------ start, in every state


def test_start_on_a_new_private_copy_publishes_the_page_and_asks_nothing_in_the_chat(fresh):
    said = fresh.run("start", "--on", "test", "--tools", "none")
    assert said.startswith("app start: setting up")
    assert "python3 tools/app.py page --out" in said and "published <the url" in said
    assert "Answer there, one question at a time" in said
    assert "published none" in said        # the chat path, where no page can be published


def test_start_on_the_app_itself_writes_nothing_and_makes_a_private_copy_first(tmp_path):
    c = Copy(str(tmp_path), kind="app")
    said = c.run("start", "--on", "test", "--tools", "none", ok=(1,))
    assert said.startswith("app start: this is the app itself")
    assert "--private (never --public)" in said
    assert claude_surfaces.steps("make-copy")[1] in said
    assert not os.path.exists(c.profile)
    # Nothing the person answered is applied here: it waits for their private copy.
    aid = c.act("setup.answer", "setup-work", value={"work": "Analyst", "place": "Leeds"})
    got = c.apply()
    assert got["waiting"] == [aid] and got["ok"] == []
    assert not os.path.exists(c.profile)


def test_making_the_copy_from_the_page_is_always_private(tmp_path):
    c = Copy(str(tmp_path), kind="app")
    log = c.fake_gh(private=True)
    aid = c.act("setup.make_copy", "q-setup-copy")
    assert c.apply()["ok"] == [aid]
    with open(log, encoding="utf-8") as fh:
        calls = fh.read()
    assert "repo create my-job-search --template aranculleton/last-job-search --private" in calls
    assert "--public" not in calls and "api repos/someone/my-job-search" in calls
    assert "https://github.com/someone/my-job-search" in c.receipt(aid)["note"]


def test_a_copy_github_says_is_public_is_refused_not_changed(tmp_path):
    c = Copy(str(tmp_path), kind="app")
    c.fake_gh(private=False)
    aid = c.act("setup.make_copy", "q-setup-copy")
    c.apply()
    assert c.receipt(aid)["result"] == "conflict"
    p = Copy(str(tmp_path / "pub"), kind="public")
    said = p.run("start", "--on", "test", "--tools", "none", ok=(1,))
    assert "public" in said and "never change that yourself" in said


def test_start_while_another_chat_sets_them_up_starts_nothing(tmp_path, monkeypatch):
    import place
    monkeypatch.setattr(app_setup, "repo_kind", lambda runner=None: {"kind": "private",
                                                                     "owner": "", "name": ""})
    monkeypatch.setattr(app_setup, "_setup_state", lambda: {"state": "going",
                                                            "say": place.STILL_GOING})
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: False)
    code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert code == 0 and "Start nothing" in said and place.STILL_GOING in said
    assert "publish" not in said.lower()


def test_start_on_a_set_up_copy_with_its_page_current_refreshes_only_the_data(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    c.run("published", "https://claude.ai/code/artifact/example-page")
    with open(os.path.join(c.profile, "app.json"), encoding="utf-8") as fh:
        assert json.load(fh)["url"] == "https://claude.ai/code/artifact/example-page"
    with open(os.path.join(c.profile, "build_versions.json"), encoding="utf-8") as fh:
        assert "page" in json.load(fh)
    said = c.run("start", "--on", "test", "--tools", "none")
    assert said.startswith("app start: set up") and "app.py page" not in said
    assert "python3 tools/app.py view" in said


def test_a_chat_that_cannot_publish_sets_up_in_the_chat_and_is_not_asked_again(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    env_line = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_upgrades.py")],
                              env=c.env(), capture_output=True, encoding="utf-8", timeout=300)
    assert "page is not published yet" in env_line.stdout
    c.run("published", "none")
    again = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_upgrades.py")],
                           env=c.env(), capture_output=True, encoding="utf-8", timeout=300)
    assert "page" not in again.stdout
    assert "app.py page" not in c.run("start", "--on", "test", "--tools", "none")


# ------------------------------------------------------------------ updates on the page


def _repo_with_an_upgrade(c: Copy) -> str:
    def git(*args):
        return subprocess.run(["git", "-C", c.state, "-c", "user.name=t",
                               "-c", "user.email=t@example.com", *args],
                              capture_output=True, encoding="utf-8", check=True).stdout
    git("init", "-q")
    with open(os.path.join(c.state, "job_search_tracker.csv"), "w", encoding="utf-8") as fh:
        fh.write("date,company\n")
    git("add", "-A")
    git("commit", "-q", "-m", "set me up")
    with open(os.path.join(c.state, "notes.md"), "w", encoding="utf-8") as fh:
        fh.write("a better board search\n")
    git("add", "-A")
    git("commit", "-q", "-m", "Profile upgrade: method-boards\n\nYour job sites were "
        "searched for again, the current way")
    return git("rev-parse", "HEAD").strip()


def test_an_upgrade_is_shown_in_plain_words_and_can_be_taken_back(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    sha = _repo_with_an_upgrade(c)
    u = c.model()["updates"]
    done = u["done"][0]
    assert done["id"] == "upg-" + sha[:10] and done["undo"] == "upgrade.undo"
    assert done["line"] == "Your job sites were searched for again, the current way."
    aid = c.act("upgrade.undo", done["id"])
    assert c.apply()["ok"] == [aid]
    assert not os.path.exists(os.path.join(c.state, "notes.md"))
    after = c.model()["updates"]["done"][0]
    assert after["undone"] is True and after["undo"] is None
    # And put back: the undo of the undo.
    redo = c.act("undo", "", undoes=aid, rev="")
    assert c.apply()["ok"] == [redo]
    assert os.path.exists(os.path.join(c.state, "notes.md"))


def test_update_now_queues_the_update_for_a_chat(tmp_path):
    import app_actions
    import page_db
    w = page_db.Writes(str(tmp_path / "out"))
    run = app_actions.Run("a1", {"at": NOW}, {"kind": "update", "sha": "b" * 40}, {}, w,
                          "c1", "UTC", app_model.parse_time(NOW))
    got = app_actions._app_update_now(run)
    assert got["undo"]["action"] == "work.stop"
    entry = w.entries[0]
    assert entry["collection"] == "work" and entry["doc_id"] == "update~" + "b" * 12
    with open(entry["file_path"], encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["kind"] == "update" and doc["status"] == "queued"
