"""Profile upgrades: a feature that needs something done on the person's side reaches
the people who set up before it existed.

/setup runs once. When the app added job-board research (profile/search.py
PORTAL_RESEARCH), every profile written before it never got any: rounds kept
searching LinkedIn and freehire only, however often the repo synced, and nothing
said so. The registry checks each person's repo for the trace each action
leaves, the sync lists what is missing, and these tests keep it honest:

- the example is always fully upgraded, and each upgrade is pending on a copy of
  it with that upgrade's trace taken out;
- a profile name added since the first release is covered by an upgrade or
  has a stated safe default;
- a CHANGELOG entry that tells existing users to do something names its upgrade;
- the sync lists the pending upgrades whether it merged anything or not, and an
  instant upgrade commits only the personal files it owns.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import portals  # noqa: E402
import profile_names  # noqa: E402
import profile_upgrades as U  # noqa: E402

EXAMPLE = os.path.join(ROOT, "profile.example")
# The day the example's conversations were last read as current (threads-gone-cold shipped):
# the fixture moves their dates on by as many days as the calendar has moved since.
EXAMPLE_DAY = dt.date(2026, 11, 10)


def _move_dates_on(path, days):
    """Every date in `path` moved `days` on, so the example reads as of the run."""
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    text = re.sub(r"\b(\d{4}-\d{2}-\d{2})\b", lambda m: (
        dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=days)).isoformat(), text)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A copy of the example profile, in use for the test."""
    d = tmp_path / "profile"
    shutil.copytree(EXAMPLE, d)
    # The example's nos are as recent as the run, so a calendar date never turns the suite
    # red: a no is asked again after REASK_DAYS, and that is tested on its own below.
    asked = d / "asked.json"
    if asked.exists():
        got = json.loads(asked.read_text(encoding="utf-8"))
        for rec in got.values():
            rec["no"] = dt.date.today().isoformat()
        asked.write_text(json.dumps(got), encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(d))
    # The example person's own state too: run in a person's repo, the checks read that
    # repo's tracker, rounds and process folders, and "the example is fully upgraded" went
    # red on their files.
    st = tmp_path / "example_state"
    shutil.copytree(os.path.join(EXAMPLE, "state"), st)
    # Its conversations are as recent as the run too: the one it shows waiting on a reply is
    # closed as gone cold GONE_COLD_DAYS after its note, so on a calendar three months on
    # "the example is fully upgraded" went red on the example's own thread (the clock moved
    # on, 2026-11-10). Closing them is tested in test_a_people_run_reaches_the_people_who_answer.
    moved = (dt.date.today() - EXAMPLE_DAY).days
    if moved > 0:
        for name in ("network_contacts.csv", "network_threads.csv"):
            _move_dates_on(st / name, moved)
    monkeypatch.setenv(person.STATE_ENV, str(st))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _drop(profile_dir, module, *names):
    """Take assignments of `names` out of profile/<module>.py, as an older profile lacks them."""
    path = profile_dir / f"{module}.py"
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    cut = set()
    for node in ast.parse(src).body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", None) in names for t in targets):
            cut.update(range(node.lineno - 1, node.end_lineno))
    assert cut, f"{names} not assigned in {module}.py"
    path.write_text("".join(ln for i, ln in enumerate(lines) if i not in cut), encoding="utf-8")
    person._modules.clear()


def _drop_key(profile_dir, dotted):
    path = profile_dir / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    node = data
    *parents, last = dotted.split(".")
    for part in parents:
        node = node[part]
    del node[last]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()


def _set_country(profile_dir, code):
    path = profile_dir / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["identity"]["country"] = code
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()


# ------------------------------------------------------------------ the registry

def test_every_upgrade_is_well_formed():
    ids = [u.id for u in U.REGISTRY]
    assert len(ids) == len(set(ids))
    for u in U.REGISTRY:
        assert re.fullmatch(r"[a-z][a-z0-9-]+", u.id), u.id
        dt.date.fromisoformat(u.added)
        assert u.cost in U.COSTS and u.gives and u.run, u.id
        if u.cost == "instant":
            assert u.command and u.paths, f"{u.id}: an instant upgrade names its command and paths"


def test_the_example_is_fully_upgraded(profile):
    assert [(u.id, why) for u, why in U.pending()] == []


@pytest.mark.parametrize("uid", [u.id for u in U.REGISTRY if u.names and not u.conditional])
def test_each_named_upgrade_is_pending_without_its_names(profile, uid):
    u = U.by_id(uid)
    by_module: dict = {}
    for full in u.names:
        if full.startswith("person.json:"):
            _drop_key(profile, full.split(":", 1)[1])
            continue
        module, name = full.split(".", 1)
        by_module.setdefault(module, []).append(name)
    for module, names in by_module.items():
        _drop(profile, module, *names)
    assert u.pending(), f"{uid} is not pending on a profile without {u.names}"


def test_every_conditional_upgrade_has_its_own_test():
    here = open(__file__, encoding="utf-8").read()
    for u in U.REGISTRY:
        if u.conditional:
            assert f'by_id("{u.id}")' in here, f"{u.id} is conditional and has no test of its own"


def test_a_brief_nobody_asked_about_its_phone_notification_asks_once(profile):
    """The brief's phone notification is off unless the person chose it (2026-11-04): a brief
    whose own run would send one, with no answer in person.json, is asked about once, and an
    answer either way ends it."""
    import brief
    _drop_key(profile, "brief_push")
    assert "no brief_push" in U.by_id("brief-push").pending()
    assert brief.push_wanted() is False
    assert brief.push_due({"lead": "One thing is due today."}) is False
    for answer, sends in (("off", False), ("on", True)):
        path = profile / "person.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["brief_push"] = answer
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        person._data.clear()
        assert U.by_id("brief-push").pending() == ""
        assert brief.push_due({"lead": "One thing is due today."}) is sends
    # A paused search sends nothing, chosen or not; a setup left waiting always reminds.
    assert brief.push_due({"paused": "2026-12-01"}) is False
    assert brief.push_due({"waiting": True}) is True


def test_a_brief_that_already_sent_a_push_keeps_sending_it(profile):
    """A copy whose brief pushed every morning before the notification became a choice
    (2026-11-04) has no brief_push, so the day it took the update its push stopped. Its own
    day records say a push was sent: it keeps it, written on for it with nobody asked, and
    only a copy whose brief never sent one is asked."""
    import brief
    _drop_key(profile, "brief_push")
    day = brief.brief_path("2026-11-03")
    os.makedirs(os.path.dirname(day), exist_ok=True)
    with open(day, "w", encoding="utf-8") as fh:
        fh.write("# Brief\n\nOne thing is due today.\n\n<!-- push: sent; chat: session_x -->\n")
    assert brief.push_wanted() is True
    assert brief.push_due({"lead": "One thing is due today."}) is True
    assert U.by_id("brief-push").pending() == ""            # never asked
    kept = U.by_id("brief-push-kept")
    assert kept.needs == "nobody" and kept.pending()
    assert brief.main(["keep-push"]) == 0
    person._data.clear()
    assert person.get("brief_push") == "on" and kept.pending() == ""
    # A push tried and not sent is no push the person had: asked, as a new copy is.
    _drop_key(profile, "brief_push")
    with open(day, "w", encoding="utf-8") as fh:
        fh.write("# Brief\n\n<!-- push: not sent; chat: session_x -->\n")
    assert brief.push_wanted() is False and U.by_id("brief-push").pending()


def test_rulings_on_a_bar_the_profile_never_set_are_lifted(profile):
    """X-18: the job round had every chat rule postings out as failing "the candidate's bar",
    one person's words, in profiles that state no bar at all."""
    seen = os.path.join(os.environ[person.STATE_ENV], "job_scraper", "seen_jobs.json")
    os.makedirs(os.path.dirname(seen), exist_ok=True)
    with open(seen, "w", encoding="utf-8") as fh:
        json.dump({"seen": {"https://jobs.example/1": {
            "status": "excluded", "company": "Harborview Home Goods", "title": "Analyst",
            "exclusion_reason": "candidate's bar: a regional retailer, none of the three"}}}, fh)
    assert "1 posting" in U.by_id("bar-unstated").pending()
    with open(profile / "employers.py", "a", encoding="utf-8") as fh:
        fh.write('\nTIER_1 = {"brindlecombe holdings"}\n')
    person._modules.clear()
    assert U.by_id("bar-unstated").pending() == ""


def test_a_bullet_theme_no_posting_word_matches(profile):
    path = profile / "bullets.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '{"forecasting", "modelling", "python", "sql", "commercial"}',
        '{"forecasting", "modelling", "python", "sql", "commercial", "ward_rounds"}', 1),
        encoding="utf-8")
    assert "ward_rounds" in U.by_id("bullet-themes").pending()


def test_public_holidays_are_researched_only_where_no_rules_cover_the_country(profile):
    import holidays
    holidays.for_year.cache_clear()
    assert U.by_id("public-holidays").pending() == ""                 # GB: the rules cover it
    _set_country(profile, "SA")
    assert "no public holidays on file for SA" in U.by_id("public-holidays").pending()
    path = profile / "search.py"
    year = __import__("datetime").date.today().year + 1
    path.write_text(path.read_text(encoding="utf-8")
                    + f'\nPUBLIC_HOLIDAYS = ("{year}-09-23",)\n', encoding="utf-8")
    person._modules.clear()
    assert U.by_id("public-holidays").pending() == ""


def test_the_working_week_is_asked_only_where_it_differs(profile):
    _drop(profile, "search", "WEEKEND") if "WEEKEND" in (profile / "search.py").read_text() else None
    assert U.by_id("market-week").pending() == ""            # GB: Saturday and Sunday is right
    _set_country(profile, "SA")
    assert "weekend" in U.by_id("market-week").pending()


def test_the_read_break_is_written_for_nobody_now(profile):
    # Written into a profile at the app's value, it read as the person's own setting, so no
    # later change to the pace could reach them (2026-10-22).
    path = profile / "networking.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        'PROFILE_READS = "paste"', 'PROFILE_READS = "browser"'), encoding="utf-8")
    person._modules.clear()
    assert U.by_id("read-break").pending() == ""


LIMITS_WRITTEN = ("\n# The break, in minutes, between bursts of browser reads.\n"
                  "PROFILE_READ_BREAK_MINUTES = (5, 12)\n"
                  "PROFILE_READS_PER_HOUR = 1000\n"
                  "PROFILE_READ_RAMP = (\n    5,\n    10,\n)\n"
                  "CONNECTIONS_PER_WEEK = 10000\n")


def test_the_reading_limits_the_app_removed_are_taken_out_of_the_profile(profile):
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import learned
    import reading
    path = profile / "networking.py"
    assert U.by_id("reading-limits-gone").pending() == ""      # none written
    assert U.by_id("read-break-freed").pending() == ""         # retired: this one does it
    path.write_text(path.read_text(encoding="utf-8").replace(
        'PROFILE_READS = "paste"', 'PROFILE_READS = "browser"') + LIMITS_WRITTEN,
        encoding="utf-8")
    person._modules.clear()
    why = U.by_id("reading-limits-gone").pending()
    assert "PROFILE_READS_PER_HOUR" in why and "CONNECTIONS_PER_WEEK" in why
    # One the person's own reaction recorded stays theirs.
    learned.record(area="other", said="I want ramps", rule="keep my ramp",
                   applied_to=("profile/networking.py PROFILE_READ_RAMP",))
    assert reading.drop_retired().startswith("took out")
    text = path.read_text(encoding="utf-8")
    for gone in ("PROFILE_READ_BREAK_MINUTES = (5, 12)", "PROFILE_READS_PER_HOUR",
                 "CONNECTIONS_PER_WEEK"):
        assert gone not in text, gone
    assert "PROFILE_READ_RAMP = (" in text and "    10,\n)" in text   # kept whole
    assert 'PROFILE_READS = "browser"' in text                         # nothing else touched
    compile(text, "networking.py", "exec")
    person._modules.clear()


def test_the_comment_written_over_a_removed_limit_goes_with_it(profile):
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import reading
    path = profile / "networking.py"
    path.write_text(path.read_text(encoding="utf-8")
                    + "\n# Reading, kept as it is.\nPROFILE_READS_PER_DAY = 80\nPROFILE_PASTE_TOP = 3\n"
                    + "\n# The break between bursts of browser reads. A shorter break raises\n"
                    + "# the risk to the account.\nPROFILE_READ_BREAK_MINUTES = (5, 12)\n",
                    encoding="utf-8")
    person._modules.clear()
    assert reading.drop_retired().startswith("took out")
    text = path.read_text(encoding="utf-8")
    assert "PROFILE_READ_BREAK_MINUTES" not in text and "shorter break" not in text
    # A comment heading a setting that stays is kept.
    assert "# Reading, kept as it is.\nPROFILE_PASTE_TOP = 3" in text
    compile(text, "networking.py", "exec")
    person._modules.clear()
    assert U.by_id("reading-limits-gone").pending() == ""
    assert reading.free_break().startswith("nothing to change")


def test_a_request_cap_the_app_never_reads_is_taken_out_of_linkedin_limits(profile):
    """connections_per_week and connections_per_day in LINKEDIN_LIMITS do nothing (the audit,
    2026-11-10, PD-10): pending while written, and the rest of the setting is kept."""
    assert U.by_id("linkedin-limits-ignored").pending() == ""        # none written
    path = profile / "networking.py"
    path.write_text(path.read_text(encoding="utf-8") + '\nLINKEDIN_LIMITS = {'
                    '"connections_per_week": 20, "inmail_credits_per_month": 15}\n',
                    encoding="utf-8")
    person._modules.clear()
    assert "1 request cap" in U.by_id("linkedin-limits-ignored").pending()


def test_a_contact_waiting_with_no_follow_up_date_gets_one(profile):
    # The example's one thread waiting on a reply carries its date already.
    assert U.by_id("follow-up-dates").pending() == ""
    # Its message moved to a week ago and its date taken off: dated by the calendar, the
    # example's own September thread would one day have ended (state.OLD_OWED_DAYS).
    st = os.environ[person.STATE_ENV]
    book, log = (os.path.join(st, n) for n in ("network_contacts.csv", "network_threads.csv"))
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    with open(book, encoding="utf-8") as fh:
        text = fh.read()
    with open(book, "w", encoding="utf-8") as fh:
        fh.write(re.sub(r"One nudge if no reply,\d{4}-\d{2}-\d{2}", ",", text))
    with open(log, encoding="utf-8") as fh:
        text = fh.read()
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(re.sub(r"fernhill_freight_halloway,\d{4}-\d{2}-\d{2},",
                        "fernhill_freight_halloway,%s," % week_ago, text))
    assert "1 contact(s) waiting on a reply have no follow-up date" in \
        U.by_id("follow-up-dates").pending()
    import subprocess
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "state.py"),
                    "follow-ups", "--write"], check=True, capture_output=True, env=os.environ)
    assert U.by_id("follow-up-dates").pending() == ""


def test_the_market_language_is_asked_only_outside_english_markets(profile):
    assert U.by_id("market-language").pending() == ""        # GB, English postings
    _set_country(profile, "DE")
    text = (profile / "search.py").read_text(encoding="utf-8")
    present = [n for n in ("INTERNAL_ONLY", "INTERNAL_ONLY_TITLE", "CANARY_QUERY")
               if re.search(rf"^{n}\b", text, re.M)]
    if present:
        _drop(profile, "search", *present)
    assert "INTERNAL_ONLY" in U.by_id("market-language").pending()


def test_a_letter_in_another_language_gets_its_own_greeting(profile):
    assert U.by_id("letter-language").pending() == ""
    path = profile / "person.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["documents"]["headings"] = {"summary": "Profil", "experience": "Berufserfahrung",
                                     "skills": "Kenntnisse", "education": "Ausbildung",
                                     "certifications": "Zertifikate"}
    data["documents"]["language"] = "de"         # setup writes it beside the headings
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    person._data.clear()
    assert U.by_id("letter-language").pending() == ""        # it set its own words
    _drop_key(profile, "documents.salutation_prefix")
    assert "Dear" in U.by_id("letter-language").pending()


def test_an_undated_look_at_the_boards_is_not_done(profile):
    path = profile / "search.py"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'"checked":\s*"[^"]*"', '"checked": ""', text), encoding="utf-8")
    person._modules.clear()
    assert "dated" in U.by_id("boards").pending()


def test_a_portal_built_before_the_contract_is_an_upgrade(profile, tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    for name, front in (("linkedin-search", ""), ("freehire-search", ""),
                        ("oldboard-search", ""), ("newboard-search", "contract: 1\n")):
        (skills / name / "cli" / "src").mkdir(parents=True)
        (skills / name / "cli" / "src" / "cli.ts").write_text("// cli\n")
        (skills / name / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n{front}---\n")
    monkeypatch.setattr(portals, "SKILLS", str(skills))
    why = U.by_id("portal-contract").pending()
    assert "oldboard-search" in why and "newboard-search" not in why


def test_a_portal_switched_on_that_no_longer_exists_is_an_upgrade(profile):
    path = profile / "search.py"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "PORTALS: dict[str, bool] = {}", 'PORTALS: dict[str, bool] = {"jobnet-search": True}'),
        encoding="utf-8")
    person._modules.clear()
    assert "jobnet-search" in U.by_id("missing-portal").pending()


def test_a_needed_setting_missing_from_an_older_profile_is_an_upgrade(profile):
    needed = sorted((m, n) for m, d in profile_names.collect().items()
                    for n, e in d.items() if e["required"] and (profile / f"{m}.py").exists())
    module, name = needed[0]
    _drop(profile, module, name)
    assert f"{module}.{name}" in U.by_id("required").pending()


def test_no_profile_means_nothing_to_upgrade(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(person.ENV, str(tmp_path / "nowhere"))
    person._modules.clear()
    assert U.main([]) == 0 and capsys.readouterr().out == ""


def test_statement_templates_scoring_and_role_headings_read_the_profile(profile):
    md = profile / "CLAUDE.md"
    md.write_text(md.read_text(encoding="utf-8").replace("## Profile statement templates",
                                                          "## Notes"), encoding="utf-8")
    assert U.by_id("statement-templates").pending()
    cp = profile / "01-candidate-profile.md"
    text = cp.read_text(encoding="utf-8")
    cp.write_text(re.sub(r"^(### [^\n]+?) - ", r"\1, ", text, count=1, flags=re.M), encoding="utf-8")
    assert U.by_id("role-headings").pending()


def test_a_field_the_scoring_vocabulary_was_not_written_for(profile):
    path = profile / "search.py"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^SCRAPE_QUERIES = \[", text, re.M)
    path.write_text(text[:m.end()] + '"registered nurse", ' + text[m.end():], encoding="utf-8")
    person._modules.clear()
    assert "registered nurse" in U.by_id("scoring-vocabulary").pending()


def test_the_round_line_says_what_claude_applies_and_what_needs_you(profile):
    _drop(profile, "search", "PORTAL_RESEARCH")
    _drop(profile, "networking", "LINKEDIN_PLAN")
    # Marked for Claude, never for the person: no id, no version, and the command is
    # Claude's to run, never to say.
    assert U.line() == ("Claude: improvements waiting: 1 you apply yourself; 1 short question "
                        "for the person (python3 tools/profile_upgrades.py lists them; never "
                        "say the command).")


# ------------------------------------------------------------------ nobody has to ask

def test_every_upgrade_says_how_urgent_it_is_and_who_it_needs():
    for u in U.REGISTRY:
        assert u.priority in (1, 2, 3, 4), u.id
        assert u.needs in ("nobody", "you"), u.id


def test_only_what_truly_needs_the_person_waits_for_them():
    """A list a person has to read and act on is a list nobody acts on. Adding to
    this set is a decision: the upgrade cannot be done from the profile and research."""
    assert {u.id for u in U.REGISTRY if u.needs == "you"} == {"unconfirmed-facts",
                                                                 "method-routines", "linkedin-plan",
                                                                 "learned-choices", "profile-reads",
                                                                 "connections-export",
                                                                 "profile-consistency",
                                                                 "message-texts",
                                                                 "voice-refresh",
                                                                 # Off unless they choose it, as
                                                                 # setting the brief up asks
                                                                 # (2026-11-04).
                                                                 "brief-push",
                                                                 # Their own setting, which a
                                                                 # test of theirs may read: asked,
                                                                 # never deleted (2026-11-11).
                                                                 "linkedin-limits-ignored",
                                                                 # Only they can give their own
                                                                 # profile (2026-10-21).
                                                                 "own-profile-review",
                                                                 # Only they hold their LinkedIn
                                                                 # download, where the computer's
                                                                 # own search finds none
                                                                 # (2026-10-23).
                                                                 "linkedin-history",
                                                                 # Only they can switch it on
                                                                 # in the Claude app on their
                                                                 # computer (2026-11-09).
                                                                 "computer-linkedin",
                                                                 # Their own setting, which an
                                                                 # older version may have written
                                                                 # the wrong way round: asked,
                                                                 # never changed unasked
                                                                 # (2026-11-11).
                                                                 "updates-choice"}
    # Nothing asks for their email: anything like an alert reaches them inside Claude
    # (the maintainer's instruction, 2026-10-22).
    assert not [u.id for u in U.REGISTRY
                if re.search(r"\b(?:inbox|gmail|e-?mails?)\b", u.ask or "", re.I)]
    # Reading in the chat's browser needs no question first, and the question that is
    # left (never asked: nothing makes it pending) carries no warning (2026-10-25).
    assert U.by_id("profile-reads").pending() == ""
    assert not re.search(r"\bterms\b|\brisk", U.by_id("profile-reads").ask)
    # Only the person can download their own connections; Claude never touches LinkedIn.
    assert U.by_id("connections-export").steps().endswith("Nothing is sent to anyone.")
    # Where they will mostly work is no longer asked of anyone set up before the question:
    # 4.0 recommends no chat on a computer (2026-10-25).
    assert U.by_id("work-place").pending() == "" and U.by_id("work-place").needs == "nobody"
    # Two answers to what a recruiter checks first: only the person knows which is true.
    assert "you pick the right one" in U.by_id("profile-consistency").ask
    # Their own notes are folded into the prep document for them, never asked about
    # (2026-10-28: "make these types of decisions for them").
    assert U.by_id("campaign-notes").needs == "nobody" and not U.by_id("campaign-notes").ask
    # Only they have the words they sent; nothing in the app can fetch them.
    assert "paste them in once" in U.by_id("message-texts").ask


def test_the_plan_is_most_urgent_first(profile):
    _drop(profile, "search", "PORTAL_RESEARCH")
    _drop(profile, "skills", "LABELS")
    ids = [p["id"] for p in U.plan()]
    assert ids == ["skills-headings", "boards"]
    assert U.plan()[0]["needs"] == "nobody" and U.plan()[0]["why"]


def test_check_answers_for_one_upgrade(profile, capsys):
    assert U.main(["--check", "boards"]) == 0 and capsys.readouterr().out.strip() == "done"
    _drop(profile, "search", "PORTAL_RESEARCH")
    assert U.main(["--check", "boards"]) == 1 and "PORTAL_RESEARCH" in capsys.readouterr().out


def test_an_unconfirmed_fact_is_asked_until_it_is_answered(profile):
    assert U.by_id("unconfirmed-facts").pending() == ""
    cp = profile / "01-candidate-profile.md"
    cp.write_text(cp.read_text(encoding="utf-8")
                  + "\n- Settled status expires: [CONFIRM: the expiry date on the share code]\n",
                  encoding="utf-8")
    (profile / "tests").mkdir(exist_ok=True)
    (profile / "tests" / "test_x.py").write_text('MARK = "[CONFIRM: not a fact]"\n')
    why = U.by_id("unconfirmed-facts").pending()
    assert why.startswith("1 fact in your profile only you can confirm: the expiry date")
    block = U.block(U.pending())
    assert "These need you" in block and "the expiry date on the share code" in block


def test_the_sync_block_splits_what_claude_does_from_what_needs_you(profile):
    _drop(profile, "search", "PORTAL_RESEARCH")
    _drop(profile, "networking", "LINKEDIN_PLAN")
    block = U.block(U.pending())
    alone, yours = block.split("These need you")
    assert "[boards]" in alone and "Claude applies these itself" in alone
    assert "[linkedin-plan]" in yours and "Premium" in yours


def test_the_sync_says_where_questions_go_as_start_does(profile):
    """Start told the page's helper its questions go on the page, as To do cards, never in
    its chat; the update's own output told it to ask them at the end of its reply (the
    maintainer's copy, 2026-11-05). Both now say the same."""
    import app_setup
    _drop(profile, "networking", "LINKEDIN_PLAN")
    block = U.block(U.pending())
    claude = block[block.index("  Claude: "):]
    assert "To do card" in block and "an answer there counts" in claude
    assert "The chat that answers the page asks none of them in its chat" in claude
    assert "At the end of your reply ask" not in claude
    assert "To do card" in app_setup.ASK_ON_PAGE and "none of them in this chat" in app_setup.ASK_ON_PAGE


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_a_session_applies_them_without_being_asked():
    # The step lives in RUNBOOK.md, "Start of a session", since 4.0 (docs/rule_map.json).
    runbook = _read("RUNBOOK.md")
    start = runbook[runbook.index("## Start of a session"):]
    step = start[start.index("5. **Profile upgrades"):start.index("In the app itself")]
    for must in ("run_in_background: true", 'isolation: "worktree"', "/upgrade",
                 "never offer them a list or wait for a yes", "at most three",
                 "undo it yourself"):
        assert must in step, must
    # The person hears what changed, never a commit or a command (2026-10-22).
    assert "git revert <sha>" not in step
    cmd = _read(".claude", "commands", "upgrade.md")
    for must in ("Never ask the person", "[CONFIRM:", "--check <id>", "Profile upgrade: <id>",
                 "git revert <sha>", "Never switch off a portal"):
        assert must in cmd, must


def test_every_scheduled_run_takes_the_apps_updates_first():
    """A person may not open a chat for days; the brief is what keeps their copy current."""
    common = _read("automation", "prompts", "_common.md")
    assert "python3 tools/sync_app.py --if-stale" in common and "/upgrade 20" in common
    assert common.index("sync_app.py --if-stale") < common.index("setup_env.sh")
    rnd = _read("automation", "prompts", "job_round.md")
    assert "_common.md` step 2" in rnd and "/upgrade 20" in rnd


def test_the_brief_never_searches():
    brief = _read("automation", "prompts", "morning_brief.md")
    assert "run_round" not in brief and "Never run a search here" in brief


# ------------------------------------------------------------------ the lints

def _names_now() -> set:
    out = {f"{m}.{n}" for m, d in profile_names.collect().items() for n in d}
    out |= {f"person.json:{k}" for k in profile_names.collect_person()}
    return out


def test_a_new_profile_name_is_an_upgrade_or_a_stated_safe_default():
    """Every name a tool reads that the first release did not: covered by an
    upgrade, or listed in SAFE_DEFAULTS with the reason. An older profile lacks
    every one of them, so each needs that decision."""
    with open(os.path.join(ROOT, "tools", "profile_names_baseline.txt"), encoding="utf-8") as fh:
        baseline = {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}
    covered = {n for u in U.REGISTRY for n in u.names} | set(U.SAFE_DEFAULTS)
    undecided = sorted(_names_now() - baseline - covered)
    assert undecided == [], ("profile names with no upgrade and no stated safe default "
                             f"(tools/profile_upgrades.py): {undecided}")


def test_safe_defaults_and_upgrade_names_are_real_names():
    now = _names_now()
    for n in list(U.SAFE_DEFAULTS) + [n for u in U.REGISTRY for n in u.names]:
        assert n in now, f"{n} is not read by any tool"
    assert all(len(r) > 20 for r in U.SAFE_DEFAULTS.values())


# A bullet that tells someone already set up to do something. Descriptions of
# what /setup does for a new person are not instructions.
INSTRUCTION = re.compile(r"\*\*If you|\bIf your\b|\bre-?run\b|\brun `|/setup --section|"
                         r"\bcopy\b[^.]*\binto your profile|\bput it back\b|\bbuild it again\b",
                         re.I)
MARK = re.compile(r"Profile upgrade: `([a-z0-9-]+)`")


def _unreleased_and_later():
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    head = text[text.index("## [Unreleased]"):text.index("## [3.0.0]")]
    return [b for b in re.split(r"\n(?=- \*\*)", head) if b.startswith("- **")]


def test_a_changelog_instruction_names_its_upgrade():
    ids = {u.id for u in U.REGISTRY}
    loose = []
    for bullet in _unreleased_and_later():
        marks = MARK.findall(bullet)
        assert set(marks) <= ids, f"unknown upgrade named in: {bullet[:90]}"
        if INSTRUCTION.search(bullet) and not marks and "No profile upgrade:" not in bullet:
            loose.append(bullet[:100].replace("\n", " "))
    assert loose == [], ("CHANGELOG entries that tell existing users to act, with no "
                         f"`Profile upgrade: <id>` or `No profile upgrade:` reason: {loose}")


# ------------------------------------------------------------------ the instant runner

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, text=True, encoding="utf-8", errors="replace",
                          capture_output=True, env=dict(os.environ, GIT_AUTHOR_NAME="t",
                          GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                          GIT_COMMITTER_EMAIL="t@example.com")).stdout


IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def test_an_instant_upgrade_commits_only_its_own_personal_files(tmp_path, monkeypatch):
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    repo = tmp_path / "repo"
    (repo / "documents" / "network").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "README.md").write_text("app\n")
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    monkeypatch.setattr(U, "ROOT", str(repo))
    good = U.Upgrade("prep-docs", "2026-10-15", "prep docs re-rendered", lambda: "stale",
                     "x", "instant", command=(sys.executable, "-c",
                     "open('documents/network/prep_a.md','w').write('new')"),
                     paths=("documents/network/*.md",))
    bad = U.Upgrade("strays", "2026-10-15", "a tool that writes outside its files", lambda: "x",
                    "x", "instant", command=(sys.executable, "-c",
                    "open('tools/x.py','w').write('1');open('documents/network/b.md','w').write('2')"),
                    paths=("documents/network/*.md",))
    notes = U.run_instant([(good, "stale"), (bad, "x")])
    assert notes[0].startswith("prep-docs: applied") and "outside its own files" in notes[1]
    log = _git(repo, "log", "--format=%s")
    assert "Profile upgrade: prep-docs" in log and "strays" not in log
    assert not (repo / "tools" / "x.py").exists()
    assert _git(repo, "status", "--porcelain") == ""


def test_instant_upgrades_wait_for_a_clean_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    (repo / "half_done.txt").write_text("x")
    monkeypatch.setattr(U, "ROOT", str(repo))
    assert "uncommitted" in U.run_instant([])[0]


def test_a_commit_that_fails_leaves_nothing_changed_and_says_so(tmp_path, monkeypatch):
    """A session with no git identity cannot commit. Reported as committed, the
    upgrade left the person's files changed and uncommitted. A refusing hook
    stands in for any reason a commit fails."""
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    repo = tmp_path / "repo"
    (repo / "documents" / "network").mkdir(parents=True)
    (repo / "README.md").write_text("app\n")
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "config", "core.hooksPath", str(tmp_path / "hooks"))
    (tmp_path / "hooks").mkdir()
    hook = tmp_path / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho refused >&2\nexit 1\n")
    hook.chmod(0o755)
    monkeypatch.setattr(U, "ROOT", str(repo))
    good = U.Upgrade("prep-docs", "2026-10-15", "prep docs re-rendered", lambda: "stale",
                     "x", "instant", command=(sys.executable, "-c",
                     "open('documents/network/prep_a.md','w').write('new')"),
                     paths=("documents/network/*.md",))
    notes = U.run_instant([(good, "stale")])
    assert notes == ["prep-docs: not applied (the commit failed: refused)"]
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "log", "--format=%s") == "init\n"


def test_a_no_is_for_now_never_for_ever(profile, monkeypatch):
    # A person disliked questions that were never asked again. A no comes back when what
    # the question offers has changed, saying what changed, or after REASK_DAYS, saying
    # when they said no; until then it stands.
    today = dt.date(2026, 10, 18)
    monkeypatch.setattr(U, "_mod", lambda name: (
        type("N", (), {"CONNECTIONS_EXPORT": "declined", "PROFILE_READS": "paste"}) if
        name == "networking" else None))
    (profile / "asked.json").unlink()
    u = U.by_id("connections-export")
    # A no from before this was kept: asked again once, with what changed.
    why = U.again(u.id, u.ask_version, u.changed, today)
    assert why.startswith("you said no before, and it has changed since: networking now finds")
    U.record_no(u.id, today)
    assert U.again(u.id, u.ask_version, u.changed, today) == ""
    assert U.again(u.id, u.ask_version, u.changed,
                   today + dt.timedelta(days=U.REASK_DAYS - 1)) == ""
    later = U.again(u.id, u.ask_version, u.changed, today + dt.timedelta(days=U.REASK_DAYS))
    assert later.startswith("you said no on 2026-10-18, 30 days ago")
    # A no from before this was kept, to a question that has not changed: held until
    # REASK_DAYS after the question shipped, never asked again the day the upgrade lands.
    a = U.by_id("own-profile-review")
    assert a.ask_version == 1 and U.again(a.id, a.ask_version, a.changed, today) == ""
    added = dt.date.fromisoformat(a.added)
    assert U.again(a.id, a.ask_version, a.changed,
                   added + dt.timedelta(days=U.REASK_DAYS - 1)) == ""
    assert U.again(a.id, a.ask_version, a.changed,
                   added + dt.timedelta(days=U.REASK_DAYS)) == (
        "you said no before; it is asked once more in case that has changed")
    # The question changes: asked again at once, saying how.
    assert U.again(u.id, u.ask_version + 1, "something new", today).endswith("something new")
    # Every question a no can answer is re-askable, and says what it changed when it did.
    for uid in ("connections-export", "own-profile-review", "profile-reads"):
        x = U.by_id(uid)
        assert x.needs == "you" and (x.ask_version == 1 or x.changed), uid
        assert "--no " + uid in x.run, uid
    assert not any("not asked again" in (x.ask or "") or "never asked again" in (x.run or "")
                   for x in U.REGISTRY)


def test_a_profile_line_telling_drafts_to_use_a_forbidden_phrase_is_found(profile):
    # A never-say left the profile's own instruction to use the phrase in place, so every
    # draft read both. Only a line that prescribes it counts.
    import learned
    learned.record("messages", "too casual", "never 'cheers'", never_say=["cheers"],
                   today="2026-10-18")
    (profile / "13-positioning.md").write_text(
        "Sign-off: the line is \"cheers\" in every note.\n"
        "Never write \"cheers\" to a recruiter.\n"
        "We said cheers at the leaving do.\n", encoding="utf-8")
    u = U.by_id("never-said")
    got = u.pending()
    assert "profile/13-positioning.md:1 ('cheers')" in got and u.needs == "nobody"
    assert ":2 " not in got and ":3 " not in got


# ------------------------------------------------------------------ asked short

# Words a person would not know, or would have to look up, in the first thing they are asked.
_JARGON = re.compile(r"\b(?:csv|export(?:ed)?|in bulk|upgrade|pending|version|round|method|"
                     r"inmail|python3?|profile/|\.py|\.json|ats)\b|[`/]", re.I)


def test_every_question_is_short_and_plain_with_its_detail_kept_for_a_yes():
    """A question is asked as one short plain question; the steps come only after a yes and
    the reason only after "why?". A paragraph pasted at someone is what nobody reads."""
    for u in U.REGISTRY:
        if u.needs != "you" or u.id == "unconfirmed-facts":   # its questions are the markers
            continue
        assert u.ask, u.id
        assert len(u.ask.split()) <= 40, (u.id, len(u.ask.split()))
        assert u.ask.rstrip().endswith("?"), u.id
        assert not _JARGON.search(u.ask), (u.id, _JARGON.search(u.ask).group(0))
        assert "\u2014" not in u.ask + u.why_ask
        if u.why_ask:
            assert u.why_ask.count(". ") == 0 and u.why_ask.endswith("."), u.id   # one sentence
        if u.steps:
            lines = u.steps().splitlines()
            assert 1 < len(lines) <= 5, (u.id, len(lines))
            assert not set(lines) & set(u.ask.splitlines())                       # kept apart
    steps = U.by_id("connections-export").steps().splitlines()
    assert steps[0] == "To get your list of LinkedIn connections:" and "https://" not in steps[0]
    assert steps[-1] == "I only read it. Nothing is sent to anyone."
    assert U.NO_REPLY == "No problem, I'll ask again in a month." and U.REASK_DAYS == 30


def test_a_kept_choice_and_a_no_come_back_on_the_same_day_count():
    import learned
    assert learned.REOFFER_DAYS == U.REASK_DAYS


def test_the_sync_block_shows_no_id_or_version_outside_its_brackets(profile):
    (profile / "build_versions.json").unlink(missing_ok=True)
    _drop(profile, "search", "PORTAL_RESEARCH")
    _drop(profile, "networking", "LINKEDIN_PLAN")
    block = U.block(U.pending())
    said = [re.sub(r"\s*\[[a-z0-9-]+\]$", "", ln) for ln in block.splitlines()
            if ln.startswith("    - ")]
    assert said and not any(re.search(r"\bversion \d|\bmethod-|\bupgrade\b", s) for s in said)


def test_a_story_with_no_use_for_line_is_tagged_in_the_background(profile):
    # An interview pack matches a story to a question by its `Use for:` line; a profile set
    # up before that line existed has stories no question can reach.
    u = U.by_id("interview-tags")
    assert u.needs == "nobody" and u.pending() == ""
    f = profile / "07-interview-prep.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## STAR: an untagged one\n"
                 "- **Situation:** s.\n- **Task:** t.\n- **Action:** a.\n- **Result:** r.\n",
                 encoding="utf-8")
    assert u.pending().startswith("1 STAR story in profile/07-interview-prep.md")
    assert "An untagged one" in u.pending()


def _process_state(tmp_path, monkeypatch):
    """A state root holding one hiring process with no application, as 3.7.0 registered it:
    its folder and outcome.md, and no job_posting.md. Invented employer and contact."""
    import csv
    import outreach
    import record_drafts
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    row = {k: "" for k in record_drafts.HEADER}
    row.update(date="2026-10-19", company="Calder & Rook Consulting", role="Operations Analyst",
               status="interview", channel="referral", source="contact:calder_rook_vance",
               notes="process, no portal application: led by Ivo Vance")
    with open(st / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=record_drafts.HEADER)
        w.writeheader()
        w.writerow(row)
    folder = outreach.app_folder(row["company"], row["role"])
    os.makedirs(folder)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome: Calder & Rook Consulting - Operations Analyst\n")
    return st, folder


def test_a_process_folder_with_no_posting_is_given_one(profile, tmp_path, monkeypatch):
    _st, folder = _process_state(tmp_path, monkeypatch)
    assert "1 hiring process folder(s) with no job_posting.md" in \
        U.by_id("process-postings").pending()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"),
                        "postings"], cwd=ROOT, env=os.environ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    text = open(os.path.join(folder, "job_posting.md"), encoding="utf-8").read()
    assert "not held yet" in text and "--posting" in text
    assert U.by_id("process-postings").pending() == ""


def test_one_application_in_two_folders_is_made_one(profile, tmp_path, monkeypatch):
    """verify_batch.py kept an application's checks in a folder named without the
    abbreviation its note and documents were filed under. Invented employer."""
    st = tmp_path / "state"
    base = st / "documents" / "applications"
    (base / "ternmoor_foods_planner").mkdir(parents=True)
    (base / "ternmoor_foods_planner_tm").mkdir()
    (base / "ternmoor_foods_planner" / "verify.json").write_text(
        json.dumps({"at": "2026-10-20T09:00:00Z", "abbr": "TM", "flags": []}), encoding="utf-8")
    (base / "ternmoor_foods_planner_tm" / "draft.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv(person.STATE_ENV, str(st))
    assert "1 application(s) kept in two folders" in U.by_id("one-folder-each").pending()
    # "python3" is the command as a chat runs it; on Windows there is no such program, so
    # the test runs it with this Python (WinError 2 on the Windows check, 2026-10-29).
    cmd = list(U.by_id("one-folder-each").command)
    cmd[0] = sys.executable if cmd[0] == "python3" else cmd[0]
    r = subprocess.run(cmd, cwd=ROOT, env=os.environ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    assert sorted(os.listdir(base)) == ["ternmoor_foods_planner_tm"]
    assert (base / "ternmoor_foods_planner_tm" / "verify.json").is_file()
    assert U.by_id("one-folder-each").pending() == ""


def test_hand_kept_notes_for_a_process_are_offered_once_to_fold_in(profile, tmp_path,
                                                                    monkeypatch):
    st, folder = _process_state(tmp_path, monkeypatch)
    assert U.by_id("campaign-notes").pending() == ""            # nothing kept by hand
    net = st / "documents" / "network"
    net.mkdir(parents=True)
    (net / "calder_rook_campaign.md").write_text("Say I am based in Manchester.\n",
                                                  encoding="utf-8")
    (net / "open_actions.md").write_text("Everything owed.\n", encoding="utf-8")   # not theirs
    why = U.by_id("campaign-notes").pending()
    assert "documents/network/calder_rook_campaign.md" in why and "open_actions" not in why
    # Folded in: the process's document says so in its Notes, and it is not asked again.
    with open(os.path.join(folder, "interview_prep.md"), "w", encoding="utf-8") as fh:
        fh.write("## Notes\n\n- Folded in from documents/network/calder_rook_campaign.md on "
                 "2026-10-20.\n")
    assert U.by_id("campaign-notes").pending() == ""


def test_own_tests_reading_the_apps_code_or_pinning_changed_behaviour_are_kept_in_line(
        tmp_path, monkeypatch):
    import sync_app
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "round_step.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    tests = repo / "profile" / "tests"
    tests.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.setattr(U, "ROOT", str(repo))
    # Their own tests are the ones of the profile in use: this repo's.
    monkeypatch.setenv(person.ENV, str(repo / "profile"))
    person.reset()
    assert U.by_id("own-tests").pending() == ""                 # nothing of theirs at risk
    (tests / "test_reads.py").write_text(
        "import os\nROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))\n"
        "def test_it():\n"
        "    src = open(os.path.join(ROOT, 'tools', 'round_step.py')).read()\n"
        "    assert 'return 1' in src\n", encoding="utf-8")
    why = U.by_id("own-tests").pending()
    assert "read the app's code as text" in why and "test_reads.py" in why
    # Rewritten to run the code and check what it does: nothing left to do.
    (tests / "test_reads.py").write_text(
        "import round_step\ndef test_it():\n    assert round_step.run() == 1\n", encoding="utf-8")
    assert U.by_id("own-tests").pending() == ""
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qm", "tests"], check=True)
    # The sync found one checking behaviour the update changed: it is brought in line.
    sync_app.record_own_tests(str(repo), [("test_reads::test_it", "AssertionError: 2 != 1")])
    assert "check what an update changed: test_reads::test_it" in U.by_id("own-tests").pending()
    # One that used a part the update removed is the sync's question to the person, not this.
    sync_app.record_own_tests(str(repo), [(
        "test_reads::test_it", "AttributeError: module 'round_step' has no attribute 'gone'")])
    assert U.by_id("own-tests").pending() == ""
    # Tests that could not run at all are not run again on every look: the record says so.
    sync_app.record_own_tests(str(repo), [("test_reads::test_it", "AssertionError: 2 != 1")])
    (tests / "test_reads.py").write_text("import nothing_called_this\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qam", "broken"], check=True)
    ran = []
    monkeypatch.setattr(sync_app, "own_test_failures",
                        lambda root, only=None: ran.append(1))            # None: could not run
    for _ in range(3):
        U.by_id("own-tests").pending()
    assert len(ran) == 1 and sync_app.own_tests_record(str(repo))["could_not_run"]


def test_reading_files_that_change_on_every_read_are_moved_out_of_the_repo(profile, tmp_path,
                                                                           monkeypatch):
    st = tmp_path / "state"
    (st / "documents" / "network").mkdir(parents=True)
    monkeypatch.setenv(person.STATE_ENV, str(st))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    assert U.by_id("runtime-files").pending() == ""
    (st / "documents" / "network" / ".shortlist.json").write_text(
        '{"date": "2026-10-20", "ids": ["bo_venn"]}', encoding="utf-8")
    assert "1 reading file(s) in documents/network" in U.by_id("runtime-files").pending()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                        "move-runtime"], cwd=ROOT, env=os.environ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    assert U.by_id("runtime-files").pending() == ""
    assert '"bo_venn"' in open(tmp_path / "ledger" / "reading-ledger.json").read()


def test_messages_that_drew_replies_without_their_words_are_never_asked_for(profile, tmp_path,
                                                                            monkeypatch):
    import schema
    import state
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update(contact_id="larkspur_castellan", name="Juno Castellan", company="Larkspur",
               status="in_conversation")
    state.save_contacts([row], str(st / "network_contacts.csv"))
    out = {"contact_id": "larkspur_castellan", "date": "2026-09-01", "direction": "out",
           "channel": "inmail", "scenario": "first_message", "summary": "approach",
           "full_text": ""}
    back = {"contact_id": "larkspur_castellan", "date": "2026-09-01", "direction": "in",
            "channel": "inmail", "scenario": "reply", "summary": "replied",
            "full_text": "Thanks, let's talk."}
    state.save_threads([out, back], str(st / "network_threads.csv"))
    # The LinkedIn download brings the words; nobody is asked to paste them (2026-10-28).
    assert U.by_id("message-texts").pending() == ""
    state.save_threads([dict(out, full_text="Hi Juno, hope you're well."), back],
                       str(st / "network_threads.csv"))
    assert U.by_id("message-texts").pending() == ""


def test_a_saved_voice_in_the_old_stiff_wording_is_offered_a_rewrite(profile, monkeypatch):
    net = profile / "networking.py"
    text = net.read_text(encoding="utf-8")
    assert U.by_id("voice-refresh").pending() == ""          # the example's own voice
    net.write_text(text.replace(
        'ASK = "Would you have 15 minutes for a few questions sometime"',
        'ASK = "I would love to hear how your team works"'), encoding="utf-8")
    assert "ASK in profile/networking.py" in U.by_id("voice-refresh").pending()
    assert "rewrite them the way you write" in U.by_id("voice-refresh").ask


def test_a_checkout_older_than_the_sync_says_so_and_never_lists_or_crashes(
        profile, tmp_path, monkeypatch, capsys):
    """From a real repo on 2026-10-21: an /upgrade worktree made from a commit before the
    sync listed the wrong upgrades, and `--check` on one it did not know raised KeyError."""
    import sync_app
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              check=True).stdout.strip()
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    for n in ("1", "2"):
        (repo / "f").write_text(n)
        run("add", "f")
        run("commit", "-qm", n)
    stamp = tmp_path / "ljs-last-sync"
    monkeypatch.setattr(sync_app, "ROOT", str(repo))
    monkeypatch.setattr(U, "ROOT", str(repo))      # the checkout --plan runs in
    monkeypatch.setattr(sync_app, "_stamp_path", lambda root=None: str(stamp))
    sync_app._record_check()                       # the sync left the repo on commit 2
    assert sync_app.behind_sync() == ""
    run("checkout", "-q", "HEAD~1")                # a worktree made from before it
    assert "older than the last update" in sync_app.behind_sync()
    assert U.main(["--plan"]) == 2 and "git merge" in capsys.readouterr().out
    assert U.main(["--check", "boards"]) == 2
    capsys.readouterr()
    run("checkout", "-q", "-")
    assert U.main(["--check", "no-such-change"]) == 2
    assert "no change called 'no-such-change'" in capsys.readouterr().out


def test_the_example_is_judged_on_its_own_files_never_the_repo_it_runs_in(
        profile, tmp_path, monkeypatch):
    """From a real repo on 2026-10-21: run there, "the example is fully upgraded" counted the
    person's own tests (one read the app's code as text) and went red."""
    repo = tmp_path / "theirs"
    tests = repo / "profile" / "tests"
    tests.mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "tools" / "round_step.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (tests / "test_reads.py").write_text(
        "import os\nROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))\n"
        "def test_it():\n"
        "    assert 'return 1' in open(os.path.join(ROOT, 'tools', 'round_step.py')).read()\n",
        encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.setattr(U, "ROOT", str(repo))
    assert U.by_id("own-tests").pending() == ""
    assert [(u.id, why) for u, why in U.pending()] == []
    assert os.path.isfile(person.state("job_search_tracker.csv"))


def test_a_name_read_through_a_one_argument_getter_is_listed():
    # network/reply.py reads HOME_COUNTRY, HOME_ADJECTIVE and HOME_CITY through
    # `def _w(name): ... getattr(_NET, name, "")`. Only two-argument wrappers were read,
    # so HOME_ADJECTIVE, read nowhere else, was missing from every check of a profile.
    import profile_names
    names = profile_names.collect()["networking"]
    assert any(w.startswith("tools/network/reply.py:") for w in names["HOME_ADJECTIVE"]["where"])
    assert not names["HOME_ADJECTIVE"]["required"]


def test_the_check_for_unconfirmed_facts_lists_every_one(profile, monkeypatch, capsys):
    """/upgrade's step says `--check unconfirmed-facts` lists every [CONFIRM: ...] in the
    profile; it printed the count, three of them and "..." (2026-10-25)."""
    cp = profile / "01-candidate-profile.md"
    asks = [f"the start date of role {n}" for n in range(1, 6)]
    cp.write_text(cp.read_text(encoding="utf-8")
                  + "".join(f"\n- Role {n}: [CONFIRM: {a}]" for n, a in enumerate(asks, 1)) + "\n",
                  encoding="utf-8")
    monkeypatch.setattr(U, "_personal_repo", lambda: False)
    assert U.main(["--check", "unconfirmed-facts"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("5 facts in your profile only you can confirm")
    assert all(f"  - {a} (" in out for a in asks), out


def test_a_tailored_resume_never_saved_is_made_again_from_its_draft(profile):
    """X-22's healing (the stranger audit, 2026-11-03): resumes named in the person's own word
    (Lebenslauf) were never saved, and went with their chats; their drafts were kept. The
    first update after the fix finds each one the tracker names and no copy holds, and makes
    it again from its saved draft."""
    state = os.environ[person.STATE_ENV]
    u = U.by_id("documents-saved")
    assert u.pending() == "" and u.needs == "nobody"
    with open(os.path.join(state, "job_search_tracker.csv"), "a", encoding="utf-8") as fh:
        fh.write("2026-11-02,Acme Logistik,Logistics,Analyst,data,company site,drafted,,70,,"
                 "cv/Jonas_Brandt_Lebenslauf_ACME.tex,"
                 "cover_letters/Jonas_Brandt_Cover_Letter_ACME.tex,,\n")
    assert u.pending() == ""                           # no saved draft: nothing to make
    folder = os.path.join(state, "documents", "applications", "acme_analyst")
    os.makedirs(folder)
    with open(os.path.join(folder, "draft.json"), "w", encoding="utf-8") as fh:
        json.dump({"abbr": "ACME", "company": "Acme Logistik"}, fh)
    assert "acme_analyst" in u.pending() and U.documents_lost() == ["acme_analyst"]
    assert "fit_to_page.py documents/applications/<folder>/draft.json" in u.run
    for rel in ("cv/Jonas_Brandt_Lebenslauf_ACME.tex",
                "cover_letters/Jonas_Brandt_Cover_Letter_ACME.tex"):
        os.makedirs(os.path.join(state, os.path.dirname(rel)), exist_ok=True)
        open(os.path.join(state, rel), "w").close()
    assert u.pending() == ""


def test_a_general_resume_made_before_its_draft_was_kept_is_made_again(profile):
    """4.13 keeps the general resume's draft beside its PDF, so its pencil can change its
    bullets (the maintainer, 2026-11-06). One made before has no pencil until it is made
    again, which Claude does with no one asking; no general resume, nothing to do."""
    import general_resume
    state = os.environ[person.STATE_ENV]
    u = U.by_id("general-resume-draft")
    assert u.needs == "nobody" and "stage_picks.py general" in u.run
    pdf, _txt = general_resume.keep_paths()
    for name in os.listdir(os.path.dirname(pdf)) if os.path.isdir(os.path.dirname(pdf)) else ():
        if name.endswith("_current.pdf"):
            os.remove(os.path.join(os.path.dirname(pdf), name))
    assert u.pending() == ""                              # no general resume: nothing to make
    os.makedirs(os.path.dirname(pdf), exist_ok=True)
    open(pdf, "wb").close()
    assert "pencil" in u.pending()
    path = os.path.join(state, *general_resume.DRAFT_DIR, "draft.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([{"general": True}], fh)
    assert u.pending() == ""


def test_a_person_with_a_computer_is_offered_its_linkedin_stage_once(profile):
    """The computer side is new in this release (2026-11-09): someone who works on a computer
    gets its setup as one card, until `computer.py ready` dates it in place.json; someone
    with no computer is never asked."""
    u = U.by_id("computer-linkedin")
    assert u.needs == "you" and u.ask and "computer.py ready" in u.run
    path = profile / "place.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert u.pending() == ""                       # the example's computer is set up
    path.write_text(json.dumps({k: v for k, v in rec.items()
                                if not k.startswith("computer_")}), encoding="utf-8")
    assert "not set up" in u.pending()
    path.write_text(json.dumps({"works_on": "phone"}), encoding="utf-8")
    assert u.pending() == ""                       # a career changer with no laptop


def test_the_records_upgrades_wait_only_on_what_they_put_right(profile):
    """readings-linked and records-agree (the review of NW-23, NW-28 and NW-32, 2026-11-11)
    are pending only for a person whose records hold what they put right: the example's do
    not. tests/test_the_records_are_checked_by_themselves.py makes each pending and done."""
    assert U.by_id("readings-linked").pending() == ""
    assert U.by_id("records-agree").pending() == ""


def test_a_rule_about_updates_written_the_wrong_way_round_is_asked_about_once(profile):
    """Audit SV-1 and PD-5's app side (2026-11-11): "App updates come by themselves; never ask
    him again" was written as when_asked. The upgrade reads the newest such rule again with
    today's reader and asks where the setting says otherwise; never where they agree."""
    import learned
    person.reset()
    said = "App updates come by themselves; never ask him again"
    learned.record("other", said, said, today="2026-11-10")
    assert U.by_id("updates-choice").pending() == ""
    person.put(["app_updates"], "when_asked")             # as the old reader wrote it
    person.reset()
    got = U.by_id("updates-choice").pending()
    assert "by themselves" in got and "only when you say" in got, got
    person.put(["app_updates"], "auto")                   # answered
    person.reset()
    assert U.by_id("updates-choice").pending() == ""


def test_roles_set_aside_with_no_day_are_dated_from_the_update(profile, tmp_path):
    """A role the person set aside held for good before set-asides had an end; one with no day
    of its own would come back on the first search after the update, with every other, or be
    counted from a day long gone. set-asides-dated gives each its months from the update day,
    and leaves one dated, one in words that say for good, and a rule's own, alone."""
    st = os.environ[person.STATE_ENV]
    seen = os.path.join(st, "job_scraper", "seen_jobs.json")
    data = json.load(open(seen, encoding="utf-8")) if os.path.exists(seen) else {"seen": {}}
    base = {"basis": "person", "status": "excluded", "title": "Analyst",
            "company": "Quillfield Foods"}
    data.setdefault("seen", {}).update({
        "jobs.example.com/a": dict(base, url="https://jobs.example.com/a",
                                   exclusion_reason="not for me", first_seen="2025-12-01"),
        "jobs.example.com/b": dict(base, url="https://jobs.example.com/b",
                                   exclusion_reason="not this team"),
        "jobs.example.com/c": dict(base, url="https://jobs.example.com/c",
                                   exclusion_reason="never", first_seen="2025-12-01"),
        "jobs.example.com/d": dict(base, url="https://jobs.example.com/d",
                                   exclusion_reason="the pay", excluded_date="2026-10-01"),
        "jobs.example.com/e": dict(base, url="https://jobs.example.com/e", basis="rules",
                                   exclusion_reason="place: outside your places"),
    })
    with open(seen, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    up = U.by_id("set-asides-dated")
    assert up.cost == "instant" and up.needs == "nobody"
    assert up.pending() == "2 role(s) you set aside have no day to count from"
    # As the app runs it (run_instant): "python3" is this Python, which Windows names otherwise.
    r = subprocess.run([sys.executable, *up.command[1:]], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ))
    assert r.returncode == 0, r.stderr[-600:]
    assert up.pending() == ""
    got = json.load(open(seen, encoding="utf-8"))["seen"]
    import exclude
    today = person.today()
    for k in ("jobs.example.com/a", "jobs.example.com/b"):
        assert got[k]["held_from"] == today.isoformat(), got[k]
        assert exclude.set_aside_until(got[k]) == today + dt.timedelta(
            days=exclude.set_aside_days())
        assert exclude.set_aside_on(got[k]) is None          # never said as the day set aside
    for k in ("jobs.example.com/c", "jobs.example.com/d", "jobs.example.com/e"):
        assert "held_from" not in got[k], got[k]


def test_notes_set_aside_on_the_page_before_they_had_an_end_are_dated_from_the_update(profile):
    """A first note set aside on the page "for now" set its person aside for good. Those set
    aside before the update are each offered again about six months from it (notes-aside-dated);
    one the person said never to, or one set aside in a chat, is left as it was."""
    import csv
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import exclude
    import schema
    import state
    book = os.path.join(os.environ[person.STATE_ENV], "network_contacts.csv")
    rows = list(csv.DictReader(open(book, encoding="utf-8")))
    base = {k: "" for k in schema.CONTACT_COLUMNS}
    rows += [dict(base, contact_id="ormsby_varga", name="Ottilie Varga", company="Ormsby Retail",
                  status="dropped", outcome="dropped 2026-05-01: not now, said on the page"),
             dict(base, contact_id="ormsby_quill", name="Ansel Quill", company="Ormsby Retail",
                  status="dropped", outcome="dropped 2026-05-01: never"),
             dict(base, contact_id="ormsby_hale", name="Tamsin Hale", company="Ormsby Retail",
                  status="dropped", outcome="dropped 2026-05-01: she moved to a competitor")]
    with open(book, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    up = U.by_id("notes-aside-dated")
    assert up.cost == "instant" and up.needs == "nobody"
    assert up.pending() == "1 note(s) you set aside for now have no day to come back"
    # As the app runs it (run_instant): "python3" is this Python, which Windows names otherwise.
    r = subprocess.run([sys.executable, *up.command[1:]], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ))
    assert r.returncode == 0, r.stderr[-600:]
    assert up.pending() == ""
    got = {c["contact_id"]: c for c in state.load_contacts(book)}
    until = person.today() + dt.timedelta(days=exclude.set_aside_days())
    assert state.dropped_until(got["ormsby_varga"]) == until, got["ormsby_varga"]["outcome"]
    assert got["ormsby_varga"]["outcome"].endswith("not now, said on the page")
    assert state.dropped_until(got["ormsby_quill"]) is None
    assert state.dropped_until(got["ormsby_hale"]) is None
