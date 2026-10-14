"""The scheduled-task registry matches the prompt files, and the set-up is generic.

Each scheduled task's stored prompt is a stub that tells its chat to read a file
from master. A wrong path, a cron with no time zone or a mistyped id fails at
seven in the morning with nobody watching, so tools/routines.py checks the
registry, ci_local.sh runs it on a person's own, and this runs it on the
example's and on every shape it must accept or refuse.
"""
import copy
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(ROOT, "automation")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
import personal_paths  # noqa: E402
import routines  # noqa: E402

REG = json.load(open(person.path("routines.json"), encoding="utf-8"))
COMMON = open(os.path.join(AUTO, "prompts", "_common.md"), encoding="utf-8").read()
README = open(os.path.join(AUTO, "README.md"), encoding="utf-8").read()

# The older shape: every task into one shared chat, and a relay task for push.
# Registries written before `setup` existed look like this and must still pass.
OPS_RELAY = {
    "timezone": "Europe/London",
    "ops_session": {"id": "session_EXAMPLE", "title": "Scheduled tasks"},
    "stub": ("Scheduled run: {label}. Run `git fetch origin master`, then read "
             "`automation/prompts/_common.md` and `{prompt_file}` as they are on "
             "origin/master and follow them exactly. If either cannot be read, still "
             "deliver: call fire_trigger with trigger_id \"{relay_id}\" and text "
             "\"{Label} could not start: <the reason>\"."),
    "routines": [
        {"key": "relay", "name": "relay", "trigger_id": "trig_EXAMPLERELAY",
         "mode": "fresh_session", "cron": None, "notifications": {"push": True, "email": True},
         "prompt_file": "automation/prompts/relay.md"},
        {"key": "morning_brief", "name": "brief", "trigger_id": "trig_EXAMPLEBRIEF",
         "mode": "ops_session", "cron": "CRON_TZ=Europe/London 56 7 * * *",
         "prompt_file": "automation/prompts/morning_brief.md"},
    ],
}
SCREEN = {
    "setup": "routines_screen", "timezone": "America/Toronto",
    "routines": [
        {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": None,
         "cron": "CRON_TZ=America/Toronto 56 7 * * *", "notifications": {"push": True},
         "prompt_file": "automation/prompts/morning_brief.md"},
    ],
}


def test_the_example_registry_is_clean():
    assert routines.check(REG) == []


@pytest.mark.parametrize("reg", [OPS_RELAY, SCREEN], ids=["ops_relay", "routines_screen"])
def test_every_working_shape_is_accepted(reg):
    assert routines.check(reg) == []


def _broken(reg, **change):
    r = copy.deepcopy(reg)
    r["routines"][0].update(change)
    return routines.check(r)


@pytest.mark.parametrize("change,says", [
    ({"prompt_file": "automation/prompts/nope.md"}, "does not exist"),
    ({"trigger_id": "trig-bad id"}, "not well formed"),
    ({"trigger_id": "trig_EXAMPLEROUND"}, "share a trigger id"),
    ({"cron": "56 7 * * *"}, "CRON_TZ"),
    ({"cron": "CRON_TZ=America/Toronto 56 7 * * *"}, "CRON_TZ=Europe/London"),
    ({"chat": {"title": "x", "session_id": "sess 1"}}, "not well formed"),
    ({"key": "job_round"}, "unique `key`"),
])
def test_a_broken_registry_fails_with_the_reason(change, says):
    problems = _broken(REG, **change)
    assert any(says in p for p in problems), problems


def test_two_tasks_may_share_one_chat():
    """One chat to scroll is a choice a person may make."""
    assert _broken(REG, chat={"title": "Job search", "session_id": "session_EXAMPLEROUND"}) == []


def test_a_routines_screen_task_must_notify():
    problems = _broken(SCREEN, notifications={"push": False})
    assert any("notifications on" in p for p in problems), problems


def test_an_unknown_setup_is_refused():
    assert routines.check({**REG, "setup": "relay"})


def test_the_readme_stubs_are_what_the_tool_prints():
    """The prompts a person pastes are the ones the registry would produce."""
    for key in ("morning_brief", "job_round"):
        assert routines.stub(REG, key) in README, key
        assert routines.stub(REG, key) == routines.DEFAULT_STUB.format(
            label=key.replace("_", " "), prompt_file=f"automation/prompts/{key}.md")


def test_the_stub_cli_prints_a_tasks_prompt():
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"),
                        "stub", "job_round"], capture_output=True, text=True)
    assert p.returncode == 0 and "automation/prompts/job_round.md" in p.stdout


def test_the_final_reply_is_the_message():
    assert "Your final reply is the message" in COMMON
    assert "Always deliver" in COMMON
    # fire_trigger appears only in the paragraph for the older shared-chat set-up.
    paras = [p for p in COMMON.split("\n\n") if "fire_trigger" in p]
    assert paras and all("older ops set-up only" in p for p in paras), paras


def test_both_set_ups_are_written_down_step_by_step():
    for heading in ("### (a) One chat per briefing", "### (b) The Routines screen",
                    "### Test it, without fire_trigger"):
        assert heading in README, heading
    assert "run_once_at" in README and "do not archive, delete or rebuild" in README


REAL_ID = re.compile(r"\b(?:trig|session)_(?!EXAMPLE)[A-Za-z0-9]{6,}\b")


def id_hits(files, read):
    """Real-looking ids in the app's own files. A person's own files are where
    their ids live (profile/routines.json, notes under handoff/), so they are
    skipped: without that this failed in every person's repo after a sync, on
    exactly the files the ids are meant to be in."""
    hits = []
    for f in files:
        if "node_modules" in f or not f.endswith((".md", ".json", ".py", ".sh", ".yml", ".txt")):
            continue
        if personal_paths.is_personal(f):
            continue
        try:
            text = read(f)
        except (OSError, UnicodeDecodeError):
            continue
        hits += [f"{f}: {m.group(0)}" for m in REAL_ID.finditer(text)]
    return hits


def test_no_real_ids_or_private_repos_are_committed():
    """Ids and names belong in a person's registry, never in the app."""
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True).stdout.split()
    assert id_hits(files, lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read()) == []


def test_a_persons_own_files_are_skipped_and_the_apps_are_still_read():
    read = []
    files = ["profile/routines.json", "handoff/split/notes.md", "automation/README.md"]
    id_hits(files, lambda f: read.append(f) or "")
    assert read == ["automation/README.md"]


def test_no_em_dashes_in_anything_the_person_reads():
    for dp, _, fs in os.walk(AUTO):
        for f in fs:
            text = open(os.path.join(dp, f), encoding="utf-8").read()
            assert "—" not in text, f


def test_prompts_never_ask_for_history_rewriting_git():
    # Scheduled chats run in auto mode, whose permission check blocks these.
    # The first real brief (2026-10-05) stopped at `git checkout -B`.
    banned = ("checkout -B", "reset --hard", "--force", "force-with-lease", "rebase")
    for f in os.listdir(os.path.join(AUTO, "prompts")):
        text = open(os.path.join(AUTO, "prompts", f), encoding="utf-8").read()
        for b in banned:
            assert b not in text.replace("Never reset, rebase or force", ""), (f, b)
