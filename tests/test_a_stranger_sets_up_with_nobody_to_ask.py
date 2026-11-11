"""A stranger sets the app up alone: no line to its makers, maybe only a phone, maybe a fork.

The stranger audit of 3 November walked the app as someone with their own copy and nobody to
ask. What it found in setup, the docs and the cloud settings, each pinned here on the path a
stranger takes: a fork told to make itself private, which GitHub refuses; a cloud chat stopping
on approval boxes nobody saw; a fault that never reached the app's makers and a copy stuck for
days that nobody noticed; a setup stopped with every answer in, shown as finished; "that's all"
typed as a job; a reading card a phone could never act on; questions only ever asked on a page
the person never opens; the PDF tools' line offered once and with no way past a failed install;
a drafting skill granted bare Bash; docs describing a setup that no longer runs; the general
resume stopping on a heading; Team plans with no way through; a cloud block reported as
"UNCONFIRMED"; "Can you work in DE"; and a stopped setup told to answer questions it had.
Every person, employer and repository here is invented.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import types
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_setup  # noqa: E402
import app_state  # noqa: E402
import claude_surfaces  # noqa: E402
from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy  # noqa: E402
from test_the_page_works_in_a_browser import _sample, _write, run  # noqa: E402

_ = run   # the fixture, used by name

NOW = app_state.NOW
APP = os.path.join(ROOT, "tools", "app.py")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _gh(answer):
    """GitHub's tool as start meets it: one answer to `gh api repos/<o>/<n>`."""
    return lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout=answer + "\n", stderr="")


def _six(c: Copy, at="2026-10-25T09:0{n}:00Z"):
    """Every one of the six questions answered on the page, as a chat applies them."""
    answers = {"resume": {"source": "pasted", "file": "documents/cv/resume_pasted_1.txt"},
               "work": {"work": "Supply chain analyst", "place": "Leeds, UK"},
               "right_to_work": {"answer": "yes"}, "pay": {"least": {"amount": 32000}},
               "roles": {"roles": ["Supply chain analyst"]}, "avoid": {"avoid": "none"}}
    os.makedirs(c.profile, exist_ok=True)
    got = {k: dict(v, at=at.format(n=i)) for i, (k, v) in enumerate(answers.items())}
    with open(os.path.join(c.profile, "setup_answers.json"), "w", encoding="utf-8") as fh:
        json.dump(got, fh)


# ------------------------------------------------------------------ X-14 a fork


def test_a_fork_is_told_to_make_a_new_private_copy_never_to_make_itself_private(monkeypatch):
    import sync_app
    monkeypatch.delenv("LJS_COPY", raising=False)
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "last-job-search"))
    monkeypatch.setattr(sync_app, "is_the_app", lambda root=None: False)
    # GitHub: not private, and a fork ("You cannot change the visibility of a fork by itself").
    kind = app_setup.repo_kind(runner=_gh("false true"))
    assert kind["kind"] == "fork"
    assert app_setup.repo_kind(runner=_gh("false false"))["kind"] == "public"
    assert app_setup.repo_kind(runner=_gh("true false"))["kind"] == "private"
    monkeypatch.setattr(app_setup, "repo_kind", lambda runner=None: kind)
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: True)
    code, lines = app_setup.start(on="m", tools="none")
    said = "\n".join(lines)
    assert code == 1 and "a fork" in said and app_setup.FORK_SAY in said
    assert claude_surfaces.steps("make-copy")[1] in said
    assert "Change visibility" not in said and "Make this repository private" not in said
    # The update check runs first even here, so a stopped copy hears corrected words.
    assert "python3 tools/sync_app.py --on" in said
    # The page's card is the one that makes a copy, and nothing about the person is applied.
    monkeypatch.setenv("LJS_COPY", "fork")
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert any(q["id"] == "q-setup-copy" for q in m["needs_you"])
    assert not any(q["id"] == "q-setup-private" for q in m["needs_you"])


def test_the_registry_and_the_docs_warn_against_a_fork():
    assert "fork" in claude_surfaces.entry("make-private")["claim"].lower()
    assert "Never choose Fork" in " ".join(claude_surfaces.steps("make-copy"))
    readme = _read("README.md")
    start = readme[readme.index("## Get started"):]
    assert "Fork" in start[:start.index("## What it looks like")]
    assert "fork can't be made private" in _read("HELP.md")


# ------------------------------------------------------------------ X-7 approval boxes


def _allowed(command: str) -> bool:
    allow = json.loads(_read(".claude", "settings.json"))["permissions"]["allow"]
    for rule in (a[5:-1] for a in allow if a.startswith("Bash(") and a.endswith(")")):
        stem = rule[:-2] if rule.endswith(":*") else None
        if (stem and (command == stem or command.startswith(stem + " "))) or command == rule:
            return True
    return False


def test_the_first_command_of_every_chat_and_job_chat_needs_no_approval():
    assert _allowed('python3 tools/app.py start --on "claude-opus-5-5" --tools "none"')
    import app
    prompt = app.child_prompt({"work": "draft~r1", "kind": "draft", "title": "Drafting",
                               "args": {}},
                              "listener-1", "https://claude.ai/code/artifact/x", session=True)
    first = re.search(r"python3 tools/app\.py start [^,]*", prompt).group(0)
    assert _allowed(first.replace('"<your model>"', "m"))
    # Narrow: the app's own engine only, never landing, installs or a wider python.
    for other in ("python3 tools/land.py", "./tools/setup_env.sh", "python3 tools/evil.py",
                  "python3 -c 'print(1)'"):
        assert not _allowed(other), other
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "security_guards.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout


def test_a_cloud_chat_is_told_once_to_choose_auto(tmp_path, monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    c.run("published", "https://claude.ai/code/artifact/example-page")
    env = dict(c.env(), CLAUDE_CODE_REMOTE="true")
    monkeypatch.setattr(c, "env", lambda: env)
    card = next(q for q in c.model()["needs_you"] if q["id"] == "q-setup-auto")
    assert card["steps"] == claude_surfaces.steps("cloud-auto", page=True)[1:]
    assert "Auto" in " ".join(card["steps"])
    aid = c.act("setup.done", "q-setup-auto")
    assert c.apply()["ok"] == [aid]
    assert not [q for q in c.model()["needs_you"] if q["id"] == "q-setup-auto"]
    # With no page, the chat says it once, and `told` keeps it from being said again.
    d = Copy(str(tmp_path / "chat"), profile=True)
    d.run("published", "none")
    envd = dict(d.env(), CLAUDE_CODE_REMOTE="true")
    monkeypatch.setattr(d, "env", lambda: envd)
    said = d.run("start", "--on", "m", "--tools", "none")
    assert "told auto" in said and claude_surfaces.steps("cloud-auto")[1] in said
    d.run("told", "auto")
    assert "told auto" not in d.run("start", "--on", "m", "--tools", "none")


# ------------------------------------------------------------------ X-20 reaching the app's makers


def test_a_report_link_carries_what_failed_and_nothing_of_the_person():
    import report
    url = report.link(command="python3 tools/app.py view /tmp/Morgan Ellis/dump --now x",
                      error="KeyError", states=["page", "Morgan"], version="4.9.0")
    q = parse_qs(urlsplit(url).query)
    assert url.startswith(report.ISSUES + "?")
    body = q["body"][0] + q["title"][0]
    assert "tools/app.py view" in body and "KeyError" in body and "4.9.0" in body
    assert "never published" in body
    assert "Morgan" not in body and "/tmp" not in body and "--now" not in body
    # Anything not of the app's own shape is left out, never passed on.
    worse = report.link(command="cat ~/.ssh/id_rsa", error="Morgan Ellis wrote this")
    assert "ssh" not in worse and "Morgan" not in worse


def test_a_copy_stuck_for_days_is_told_once_with_the_link_and_the_page_shows_it(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    with open(os.path.join(c.profile, "place.json"), "w", encoding="utf-8") as fh:
        json.dump({"setup": {"started": "2026-10-20", "finished": "2026-10-20"}}, fh)
    said = c.run("start", "--on", "m", "--tools", "none")
    # The page was never made, five days and more, and this start publishes it: it is never
    # also said to be stuck, with the makers' link (the re-audit of 4 November).
    assert "page to publish" in said
    assert "stuck since" not in said and "told report-page" not in said
    # A chat with no pages, its setup stopped five days ago with every answer in: said once,
    # with the makers' link.
    e = Copy(str(tmp_path / "nopage"), profile=True)
    _six(e, at="2026-10-20T09:0{n}:00Z")
    e.run("published", "none", "--why", "no pages in this chat")
    said = e.run("start", "--on", "m", "--tools", "none")
    assert "stuck since 2026-10-20" in said and "told report-setup" in said
    assert "github.com/aranculleton/last-job-search/issues/new?" in said
    e.run("told", "report-setup")
    assert "told report-setup" not in e.run("start", "--on", "m", "--tools", "none")
    # A copy with a page shows the stuck state as a To do card with the link to open.
    d = Copy(str(tmp_path / "paged"), profile=True)
    _six(d, at="2026-10-20T09:0{n}:00Z")     # every answer in five days ago, then nothing
    d.run("published", "https://claude.ai/code/artifact/example-page")
    card = next(q for q in d.model()["needs_you"] if q["id"] == "q-setup-report-setup")
    assert card["open"]["url"].startswith("https://github.com/aranculleton/last-job-search/issues/new?")
    assert "nothing is sent" in card["body"]


def test_a_part_of_the_page_that_breaks_reaches_the_report_by_its_kind(run, tmp_path):
    m = _sample()
    html = _write(tmp_path, "fault", m)
    # One part throws while it is drawn, as a malformed item makes it (robustness audit 6).
    got = run("script", html=html, clock="2026-10-25T09:00:00Z", steps=[
        {"hash": "jobs", "eval": "(function () { const r = document.querySelector('#main'); "
                                 "return r ? 'ok' : ''; })()"},
        {"hash": "settings", "click": "Something looks wrong", "exact": False,
         "fake": {}, "eval": "(document.querySelector('#main [data-k=\"report-makers\"]') || {}).href || ''"}])
    body = parse_qs(urlsplit(got["steps"][-1]["eval"]).query)["body"][0]
    assert "Page version" in body
    js = _read("templates", "app", "app.js")
    guarded = js[js.index("function guarded(fn, fallback)"):]
    guarded = guarded[:guarded.index("\n  }\n")]
    assert "S.drawFault" in guarded and "e.name" in guarded
    report = js[js.index("function makersUrl(version"):]
    assert "S.drawFault" in report[:report.index("encodeURIComponent")]


# ------------------------------------------------------------------ X-29 a stalled setup


def test_a_setup_with_every_answer_in_says_it_is_running_then_stopped_with_carry_on(tmp_path):
    c = Copy(str(tmp_path))
    _six(c, at="2026-10-25T16:0{n}:00Z")
    s = c.model()["setup"]
    assert s["progress"]["done"] == 6 and s["next"] is None
    assert s["state"] == "searching" and s["stalled_hours"] == 6
    # Nothing written for hours: stopped, in words, with a Carry on the page can ring.
    _six(c, at="2026-10-24T09:0{n}:00Z")
    s = c.model()["setup"]
    assert s["state"] == "stopped" and "Carry on" in s["say"]
    aid = c.act("setup.carry_on", "setup", rev=s["rev"])
    assert c.apply()["ok"] == [aid]
    # A setup.* tap is what makes the woken chat print carry_on() (app.py wake).
    assert "carry on" in c.receipt(aid)["note"].lower() or "carries" in c.receipt(aid)["note"]


def _setup_model(state, made_at):
    m = _sample()
    steps = [{"id": f"setup-{sid}", "step": sid, "n": i + 1, "kind": "text", "question": q,
              "help": "", "fields": [], "options": [], "known_from": "your answer",
              "status": "done", "waiting": None, "skippable": False, "rev": f"s{i}"}
             for i, (sid, q) in enumerate(zip(app_setup.STEP_IDS, ["Your resume", "Work", "Visa",
                                                                   "Pay", "Roles", "Avoid"]))]
    m["made_at"] = made_at
    m["setup"] = {"state": state, "say": "", "id": "setup", "rev": "su1", "stalled_hours": 6,
                  "progress": {"done": 6, "total": 6, "label": "6 of 6"}, "next": None,
                  "steps": steps, "research": [{"topic": "boards", "label": "Job sites",
                                                "status": "waiting", "work": "research~boards"}],
                  "phases": []}
    return m


def test_a_stalled_setup_shows_stopped_with_one_carry_on_by_the_pages_own_clock(run, tmp_path):
    html = _write(tmp_path, "stalled", _setup_model("searching", "2026-10-25T08:00:00Z"))
    fresh = run("script", html=html, clock="2026-10-25T09:00:00Z", steps=[{"hash": "todo"}])
    assert "Your first shortlist" in fresh["steps"][0]["main"]
    assert "stopped part-way" not in fresh["steps"][0]["main"]
    got = run("script", html=html, clock="2026-10-27T09:00:00Z", steps=[
        {"hash": "todo"}, {"click": "Carry on", "exact": True}])
    main = got["steps"][0]["main"]
    assert "Your setup stopped part-way" in main and "6 short questions" not in main
    acts = [a for a in got["steps"][-1]["actions"] if a.get("action") == "setup.carry_on"]
    assert acts and acts[0]["item"] == "setup"


# ------------------------------------------------------------------ X-40 building a resume


def test_a_typed_thats_all_ends_the_jobs_and_the_last_question_is_asked(fresh):
    build = fresh.act("setup.build_resume", "setup-resume")
    assert fresh.apply()["ok"] == [build]
    job = fresh.act("setup.answer", "setup-history", value={"text": "Shift lead, Quayside Foods"})
    assert fresh.apply()["ok"] == [job]
    end = fresh.act("setup.answer", "setup-history", value={"text": "That's all."})
    assert fresh.apply()["ok"] == [end]
    h = fresh.answers()["history"]
    assert h["jobs"] == ["Shift lead, Quayside Foods"] and h["done"] is True
    steps = {s["step"]: s for s in fresh.model()["setup"]["steps"]}
    rest = steps["history_rest"]
    assert rest["status"] == "next" and "where you studied" in rest["question"]
    aid = fresh.act("setup.answer", "setup-history_rest",
                    value={"text": "BSc Logistics, 2016 to 2019; English and Portuguese"})
    assert fresh.apply()["ok"] == [aid]
    assert fresh.answers()["history_rest"]["text"].startswith("BSc Logistics")


@pytest.fixture
def fresh(tmp_path):
    return Copy(str(tmp_path))


def test_a_thats_all_saved_as_a_job_before_is_read_right_and_its_question_asked(tmp_path,
                                                                               monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    with open(os.path.join(c.profile, "setup_answers.json"), "w", encoding="utf-8") as fh:
        json.dump({"resume": {"source": "build"}, "history": {
            "jobs": ["Shift lead, Quayside Foods", "that's all"], "done": True}}, fh)
    monkeypatch.setenv("LJS_PROFILE", c.profile)
    monkeypatch.setenv("LJS_STATE", c.state)
    assert app_setup.answers()["history"]["jobs"] == ["Shift lead, Quayside Foods"]
    import profile_upgrades
    text = open(os.path.join(c.profile, "01-candidate-profile.md"), encoding="utf-8").read()
    with open(os.path.join(c.profile, "01-candidate-profile.md"), "w", encoding="utf-8") as fh:
        fh.write(re.sub(r"(?ms)^## Education.*?(?=^## |\Z)", "", text))
    found = profile_upgrades.unconfirmed()
    assert any(what == profile_upgrades.BUILT_REST for _, what in found)


# ------------------------------------------------------------------ X-53 reading on a phone


def test_a_phone_can_act_on_the_reading_card_and_a_held_note_is_not_offered(run, tmp_path):
    m = _sample()
    # A phone with no computer set up: the reading card offers what this page can do (with a
    # computer ready, Claude reads there by itself and the card has no button).
    m.setdefault("person", {})["computer"] = False
    m["linkedin"] = {"reading": {"queue": [{"id": "copperleaf_pay_ash", "first_name": "Ash"}]}}
    m["where"]["reading"] = {"state": "open_in_app"}
    m["settings"].append({"id": "setting-profile_reads", "key": "profile_reads",
                          "label": "Reading LinkedIn profiles", "kind": "choice",
                          "value": "browser", "choices": [["browser", "Claude reads them"],
                                                          ["paste", "I paste them"]],
                          "rev": "pr1"})
    # As the engine writes a held note: no wave of notes ready to send (app_model.messages).
    m["messages"][2].update(hold="Written before their profile was read: read it first",
                            wave=None, wave_label=None)
    html = _write(tmp_path, "phone", m)
    got = run("script", html=html, viewport={"width": 375, "height": 812},
              clock="2026-10-25T09:00:00Z",
              steps=[{"hash": "todo"}, {"click": "I'll paste them instead"},
                     {"hash": "contacts",
                      "eval": "[(document.querySelector('[data-k=\"held:msg-ash-1\"]') || {}).textContent || '',"
                              " !!document.querySelector('[data-k=\"copy:msgt-msg-ash-1\"]')]"}])
    acts = [a for a in got["steps"][1]["actions"] if a.get("action") == "setting.set"]
    assert acts and acts[0]["value"] == {"value": "paste"}
    # Not offered: its one line says why it waits (2026-11-07: "Not ready to send: waiting
    # for ..." and an alert under it said it twice), and it has no Copy.
    line, copy = got["steps"][-1]["eval"]
    assert "profile was read" in line and not copy, (line, copy)


# ------------------------------------------------------------------ X-55 questions in the chat


def test_the_days_first_chat_asks_the_questions_the_page_holds(tmp_path, monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    c.run("published", "https://claude.ai/code/artifact/example-page")
    for k in ("LJS_PROFILE", "LJS_STATE", "LJS_COPY"):
        monkeypatch.setenv(k, c.env()[k])
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: True)
    code, lines = app_setup.start(on="m", tools="none")
    said = "\n".join(lines)
    assert "These need you" in said and "at most three" in said
    assert "at most three" in _read(".claude", "commands", "upgrade.md").split("X-55")[1][:400]


# ------------------------------------------------------------------ X-59, X-60 the PDF tools' line


def test_the_pdf_tools_line_is_offered_whenever_a_cloud_chat_lacks_them(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_COPY", "private")
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("LJS_PROFILE", str(tmp_path / "profile"))
    state = str(tmp_path / "state")
    os.makedirs(state)
    subprocess.run(["git", "init", "-q", state], check=True)
    monkeypatch.setenv("LJS_STATE", state)
    monkeypatch.setattr(app_setup, "_tex", lambda: False)
    with open(os.path.join(app_setup._git_dir(), app_setup.JOB_SITES), "w", encoding="utf-8") as fh:
        json.dump({"checked": "2026-10-25", "blocked": []}, fh)     # job sites open
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    card = next(q for q in m["needs_you"] if q["id"] == "q-setup-setup-script")
    assert card["more"]["copy"] == app_setup.setup_script_line()
    # A chat that starts with the tools it never installed: the old line is replaced, once.
    monkeypatch.setattr(app_setup, "_tex", lambda: True)
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert any(q["id"] == "q-setup-setup-script-line" for q in m["needs_you"])
    open(os.path.join(app_setup._git_dir(), "ljs-setup-env"), "w").close()
    m, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert not any(q["id"].startswith("q-setup-setup-script") for q in m["needs_you"])


def test_the_pasted_line_never_stops_a_chat_from_starting():
    line = app_setup.setup_script_line()
    parts = [p.strip() for p in line.split(";") if p.strip()]
    assert len(parts) >= 3 and "&&" not in line
    for p in parts:
        assert p.endswith("|| true"), p
    # It still installs the same tools.
    for tool in ("texlive-luatex", "texlive-xetex", "poppler-utils", "pypdf", "cffi"):
        assert tool in line
    import local_path
    bash = local_path.bash()      # Git Bash on Windows, never the Linux layer's launcher
    if not bash:
        pytest.skip("no bash here to run the line in")
    r = subprocess.run([bash, "-c", line.replace("apt-get", "false").replace("pip3", "false")],
                       capture_output=True, timeout=30)
    assert r.returncode == 0


# ------------------------------------------------------------------ X-61 the drafting skill


def test_no_pre_approved_skill_grants_bare_bash_or_web_fetch(tmp_path, monkeypatch):
    import security_guards as G
    got = G._allowed_tools(type(G.ROOT)(os.path.join(ROOT, ".claude", "skills",
                                                     "job-application-assistant", "SKILL.md")))
    assert "Bash" not in got and "WebFetch" not in got
    assert all(not t.startswith("Bash(") or t.startswith("Bash(python3 tools/") for t in got)
    # The guard fails a widening, as it does in settings.json.
    root = tmp_path / "repo"
    (root / ".claude" / "skills" / "job-application-assistant").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text(json.dumps(
        {"permissions": {"allow": ["Skill(job-application-assistant)"]}}), encoding="utf-8")
    (root / ".claude" / "skills" / "job-application-assistant" / "SKILL.md").write_text(
        "---\nname: job-application-assistant\nallowed-tools: Read, Bash, WebFetch\n---\n",
        encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", root)
    monkeypatch.setattr(G, "errors", [])
    G.check_skill_tools()
    said = "\n".join(G.errors)
    assert "'Bash'" in said and "'WebFetch'" in said and "pre-approves" in said


# ------------------------------------------------------------------ X-67 the docs


def test_the_docs_describe_the_setup_that_runs_and_their_addresses_are_links():
    start = _read("START_HERE.md")
    assert "two short rounds" not in start and "It ends by opening your" not in start
    assert "six short questions" in start
    # "Open this link": an address GitHub shows as a link only with its https:// on.
    bare = re.compile(r"(?<![/\w.])(?:github\.com/(?:new|apps|aranculleton/last-job-search)|claude\.ai/(?:code|download))")
    for eid in ("make-copy", "connect-github"):
        for line in claude_surfaces.steps(eid):
            assert not bare.search(line), line
    assert "https://claude.ai/download" in start
    assert "START_HERE.md has you paste" not in _read("SETUP.md")
    setup = _read(".claude", "commands", "setup.md")
    assert "word for word without a page" in setup


# ------------------------------------------------------------------ X-73 the summary heading


def test_a_profile_with_no_summary_statement_is_an_upgrade_and_the_stop_names_the_heading(
        tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    app_state.profile_copy(str(profile))
    monkeypatch.setenv("LJS_PROFILE", str(profile))
    import profile_upgrades
    u = profile_upgrades.by_id("summary-statement")
    assert u.pending() == ""
    p = profile / "01-candidate-profile.md"
    p.write_text(re.sub(r"(?ms)^## Canonical Summary Statement.*?(?=^## )", "",
                        p.read_text(encoding="utf-8")), encoding="utf-8")
    assert "Canonical Summary Statement" in u.pending()
    import general_resume
    with pytest.raises(SystemExit) as e:
        general_resume.draft()
    assert "## Canonical Summary Statement" in str(e.value)
    assert "Canonical Summary Statement" in _read(".claude", "skills",
                                                 "job-application-assistant",
                                                 "setup-sections.md")


# ------------------------------------------------------------------ X-79 a work or team plan


def test_a_team_plan_has_its_way_through_github_and_the_network_setting():
    # The way past a setting an Owner holds: in HELP, and on the page's job-sites card.
    said = claude_surfaces.say("team-plan")
    assert "Owner of your Claude organization" in said
    assert "Owner of your Claude organization" in " ".join(
        claude_surfaces.steps("cloud-internet", page=True))
    assert "<!-- claude-surface: team-plan -->" in _read("HELP.md")
    claim = claude_surfaces.entry("team-plan")["claim"]
    assert "GitHub access is required" in claim and "New environment" in claim


# ------------------------------------------------------------------ X-80 a cloud block


def test_a_site_the_cloud_settings_refuse_is_said_as_that_with_the_fix(monkeypatch):
    import robots_check

    def refused(url, ua):
        raise RuntimeError("curl exit 56")
    monkeypatch.setattr(robots_check, "_fetch", refused)
    rc, msg = robots_check.gate("https://jobs.example-bank.ca/posting/123",
                                probe=lambda url: ("blocked", "proxy 403"))
    assert rc == 1 and "CLOUD SETTINGS" in msg
    assert "Network access to Full" in msg and "jobs.example-bank.ca" in msg
    rc, msg = robots_check.gate("https://jobs.example-bank.ca/posting/123",
                                probe=lambda url: ("unreachable", "x"))
    assert rc == 1 and msg.startswith("UNCONFIRMED")
    assert "Full is the setting" in claude_surfaces.entry("cloud-internet")["claim"]


# ------------------------------------------------------------------ X-82 the country


@pytest.mark.parametrize("place,want", [("Recife", "the country you work in"),
                                        ("Austin, TX", "the country you work in"),
                                        ("Toronto, ON", "the country you work in"),
                                        ("Leeds, UK", "the UK"), ("Lyon, France", "France"),
                                        ("Berlin, Germany", "Germany")])
def test_the_right_to_work_question_names_a_country_never_a_code_or_a_city(fresh, place, want):
    fresh.act("setup.answer", "setup-work", value={"work": "Analyst", "place": place})
    fresh.apply()
    q = fresh.step("right_to_work")["question"]
    assert f"Can you work in {want} without" in q, q


def test_a_profile_country_code_is_named(monkeypatch):
    import person
    monkeypatch.setattr(app_setup, "set_up", lambda: True)
    monkeypatch.setattr(app_setup, "answers", lambda: {})
    for code, want in (("DE", "Germany"), ("IN", "India"), ("BR", "Brazil"), ("GB", "the UK"),
                       ("ZZ", "the country you work in")):
        monkeypatch.setattr(person, "country", lambda c=code: c)
        assert app_setup._country() == want


# ------------------------------------------------------------------ X-83 coming back to a stopped setup


def test_coming_back_with_every_answer_in_carries_on_and_asks_nothing(tmp_path):
    c = Copy(str(tmp_path))
    _six(c, at="2026-10-20T09:0{n}:00Z")
    c.run("published", "https://claude.ai/code/artifact/example-page")
    said = c.run("start", "--on", "m", "--tools", "none")
    assert "Answer there, one question at a time" not in said
    assert "carry setup on now" in said
    assert app_setup.SAY_FINISHING.split(",")[0] in said or \
        app_setup.SAY_CARRYING_ON.split(",")[0] in said
    assert "published none" not in said      # a page is published: no "cannot publish" step


# ------------------------------------------------------------------ X-74 (group E's) a finished setup


def test_a_finished_setup_outside_the_built_in_holiday_rules_is_not_read_as_unfinished(tmp_path,
                                                                                      monkeypatch):
    """In 14 of the market tables' countries no rules hold the public holidays, so the
    public-holidays upgrade is still pending at the end of a complete setup: setup.md's
    Step 4 must name it beside brief-watch as allowed to stay, or that setup reads as
    unfinished (the stranger audit, X-74, group E)."""
    import shutil
    import holidays
    import person
    import profile_upgrades as U
    from test_profile_upgrades import _set_country
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv("LJS_PROFILE", str(d))
    person.reset()
    holidays.for_year.cache_clear()
    _set_country(d, "DE")
    u = U.by_id("public-holidays")
    assert "no public holidays on file for DE" in u.pending() and u.needs == "nobody"
    setup = _read(".claude", "commands", "setup.md")
    step4 = setup[setup.index("## Step 4"):setup.index("## Step 5")]
    rule = step4[step4.index("python3 tools/profile_upgrades.py"):]
    rule = rule[:rule.index("a step skipped")]
    assert "may stay" in rule and "`public-holidays`" in rule and "`brief-watch`" in rule


def test_a_stranger_is_told_what_each_setting_allows_and_one_count_of_questions():
    """Audit U-16 (2026-11-10): START_HERE.md asked a stranger to choose Auto and full network
    access with no word on what either allows; the desktop app that networking needs came only
    after setup; and setup was "six short questions" in one place and "A few" in another."""
    start = _read("START_HERE.md")
    head = start.split("## 1.", 1)[0]
    assert "desktop app" in head, "listed with what you need, before setup"
    auto = start.split("<!-- claude-surface: cloud-auto -->", 1)[0].rstrip().rsplit("\n\n", 1)[-1]
    assert "Auto lets Claude" in auto and "safety checks" in auto
    net = start.split("<!-- claude-surface: cloud-internet -->", 1)[0].rstrip().rsplit("\n\n", 1)[-1]
    assert "Full lets this chat open any" in net
    words = {6: "six"}
    assert f"{words[len(app_setup.STEPS)]} short questions" in start
    js = _read("templates", "app", "app.js")
    assert "A few short questions" not in js
    assert '" short questions, then Claude does the rest."' in js
