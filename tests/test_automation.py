"""The routine registry (profile/routines.json) matches the prompt files it points at.

Each scheduled routine's stored prompt is a stub that tells the ops session to
read a file from master. A wrong path there fails at 07:56 with nobody
watching, so this checks it at CI time instead.
"""
import json
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(ROOT, "automation")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402

# The registry of the profile in use: the example person's under tests/, a real
# person's under their own run.
REG = json.load(open(person.path("routines.json"), encoding="utf-8"))
ROUTINES = {r["key"]: r for r in REG["routines"]}


def test_every_prompt_file_exists():
    for r in REG["routines"]:
        assert os.path.isfile(os.path.join(ROOT, r["prompt_file"])), r["prompt_file"]
    assert os.path.isfile(os.path.join(AUTO, "prompts", "_common.md"))


def test_keys_ids_and_names_are_unique():
    for field in ("key", "trigger_id", "name"):
        vals = [r[field] for r in REG["routines"]]
        assert len(vals) == len(set(vals)), field
    for r in REG["routines"]:
        assert re.fullmatch(r"trig_[A-Za-z0-9]+", r["trigger_id"]), r["trigger_id"]


def test_there_is_exactly_one_relay_and_it_notifies():
    relays = [r for r in REG["routines"] if r["mode"] == "fresh_session"]
    assert [r["key"] for r in relays] == ["relay"]
    assert relays[0]["notifications"] == {"push": True, "email": True}
    assert relays[0]["cron"] is None


def test_work_routines_run_in_the_ops_session_on_the_registrys_time():
    # The time zone is the person's (the registry's `timezone`); every work
    # routine's cron must say it, or it fires in UTC and the brief is late.
    tz = REG["timezone"]
    assert re.fullmatch(r"[A-Za-z]+(?:/[A-Za-z_]+)+", tz), tz
    assert re.fullmatch(r"session_[A-Za-z0-9]+", REG["ops_session"]["id"])
    work = [r for r in REG["routines"] if r["mode"] == "ops_session"]
    assert work, "no work routines"
    for r in work:
        assert r["cron"].startswith(f"CRON_TZ={tz} "), r["cron"]
        assert len(r["cron"].split()) == 6, r["cron"]


def test_the_stub_names_the_right_files_and_the_relay():
    relay_id = ROUTINES["relay"]["trigger_id"]
    for r in REG["routines"]:
        if r["mode"] != "ops_session":
            continue
        label = r["key"].replace("_", " ")
        stub = REG["stub"].format(label=label, Label=label.capitalize(),
                                  prompt_file=r["prompt_file"], relay_id=relay_id)
        assert r["prompt_file"] in stub and relay_id in stub
        assert "automation/prompts/_common.md" in stub


def test_common_rules_say_always_deliver_through_the_relay():
    common = open(os.path.join(AUTO, "prompts", "_common.md"), encoding="utf-8").read()
    assert "fire_trigger" in common and "routines.json" in common
    assert "Always deliver" in common


def test_no_em_dashes_in_anything_the_person_reads():
    for dp, _, fs in os.walk(AUTO):
        for f in fs:
            text = open(os.path.join(dp, f), encoding="utf-8").read()
            assert "—" not in text, f


def test_prompts_never_ask_for_history_rewriting_git():
    # The ops session runs in auto mode, whose permission check blocks these.
    # The first real brief (2026-10-05) stopped at `git checkout -B`.
    banned = ("checkout -B", "reset --hard", "--force", "force-with-lease", "rebase")
    for f in os.listdir(os.path.join(AUTO, "prompts")):
        text = open(os.path.join(AUTO, "prompts", f), encoding="utf-8").read()
        for b in banned:
            assert b not in text.replace("Never reset, rebase or force", ""), (f, b)
