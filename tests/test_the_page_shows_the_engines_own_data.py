"""The page, built by the engine itself from an invented search, shows what the engine says.

The other browser tests drive the page from a fixture written by hand
(tests/fixtures/app_model_sample.json). This one takes the example person's own search
(tests/app_state.py), runs `tools/app.py page` and `tools/app.py view` on it exactly as a chat
does, and reads the page back in a browser: setup one question at a time (CONTRACT 6.2), the
updates and their undo (6.3), what only the person can do (6.4), alerts and suggestions (6.5),
lists whose finished history waits in the database (6.7), the private copy in one tap (6.8),
and the links between things at one employer (6.9). Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_page  # noqa: E402
import app_setup  # noqa: E402
import app_state  # noqa: E402
from test_the_page_works_in_a_browser import HARNESS, Runner, _node_env  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW
PHONE = {"width": 375, "height": 812}


def _env(profile, state, copy):
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY=copy)
    env.pop("LJS_TODAY", None)
    return env


def _app(env, *args):
    r = subprocess.run([sys.executable, APP, *args], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _page(tmp, name, env):
    """`app.py page` as a chat runs it, served the way the host serves it."""
    out = os.path.join(tmp, name + ".artifact.html")
    _app(env, "page", "--now", NOW, "--out", out)
    with open(out, encoding="utf-8") as fh:
        body = fh.read()
    path = os.path.join(tmp, name + ".html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(body))
    return path


def _seed(tmp, name, env, now=NOW):
    """The view documents `app.py view` writes, as the page's database holds them."""
    out = os.path.join(tmp, name + "-view")
    _app(env, "view", out, "--now", now)
    seed = {}
    base = os.path.join(out, "files")
    for coll in ("screen", "meta"):
        d = os.path.join(base, coll)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else ():
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                # A body's file is named without "~" (page_db.body_name): the record's id is
                # read back with it restored.
                seed[coll + "/" + f[:-5].replace("@", "~").replace("=", ":")] = json.load(fh)
    return seed


def _csv_edit(path, fn):
    rows = app_state._csv_rows(path)
    cols = list(rows[0].keys())
    fn(rows, cols)
    app_state._save_csv(path, rows, cols)


def _git(state, *args):
    return subprocess.run(["git", "-C", state, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          capture_output=True, encoding="utf-8", check=True).stdout


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("engine"))
    out = {}
    # The example search as the engine tests hold it.
    small = app_state.small(os.path.join(tmp, "small"))
    env = _env(app_state.EXAMPLE, small, "private")
    out["small"] = (_page(tmp, "small", env), _seed(tmp, "small", env))
    # A new private copy with nothing set up yet.
    fresh = os.path.join(tmp, "fresh")
    os.makedirs(fresh)
    out["fresh"] = (_page(tmp, "fresh", _env(os.path.join(tmp, "fresh-profile"), fresh, "private")), {})
    # The public app itself: nothing can be kept until the private copy exists.
    pub = os.path.join(tmp, "app")
    os.makedirs(pub)
    subprocess.run(["git", "init", "-q", pub], check=True)
    out["app"] = (_page(tmp, "app", _env(os.path.join(tmp, "app-profile"), pub, "app")), {})
    # A lived-in search: a referral in flight, a closing date tomorrow, a tool asked for that
    # the resume leaves out, a call to confirm, an improvement made for them, job sites this
    # chat cannot reach, and an update waiting on the app.
    st = app_state.small(os.path.join(tmp, "rich"))
    prof = app_state.profile_copy(os.path.join(tmp, "rich-profile"))

    def contacts(rows, cols):
        for r in rows:
            if r["contact_id"] == "fernhill_freight_halloway":
                r.update(status="referral_in_progress", next_action="Wait for the recruiter to call")
        rows.append(dict.fromkeys(cols, "") | {
            "contact_id": "wren_health_orme", "name": "Tam Orme", "company": "Wren Health",
            "company_key": "wren health", "route": "alumni_school", "status": "call_booked",
            "next_action": "Confirm the call time", "next_action_due": "2026-10-24"})
    _csv_edit(os.path.join(st, "network_contacts.csv"), contacts)
    rp = os.path.join(st, "documents", "rounds", "r9.json")
    with open(rp, encoding="utf-8") as fh:
        rows = json.load(fh)
    rows[0]["deadline"] = "2026-10-26"
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    # A chat stopped a draft because the role is not one they can take, and ruled it out by
    # the rules (2026-10-30): it leaves the list like one the person binned.
    sp = os.path.join(st, "job_scraper", "seen_jobs.json")
    with open(sp, encoding="utf-8") as fh:
        seen = json.load(fh)
    book = seen.get("seen", seen) if isinstance(seen, dict) else {}
    book[rows[1]["url"]] = {"url": rows[1]["url"], "title": rows[1]["title"], "company": rows[1]["company"],
                            "status": "excluded", "basis": "rules", "exclusion_reason": "location: US only",
                            "excluded_date": "2026-10-24"}
    with open(sp, "w", encoding="utf-8") as fh:
        json.dump(seen, fh)
    out["ruled"] = (rows[1]["title"], rows[1]["company"])
    kf = os.path.join(st, "documents", "applications", "kestrel_mutual_claims_forecasting_analyst_kestrel")
    with open(os.path.join(kf, "job_posting.md"), "w", encoding="utf-8") as fh:
        fh.write("# Claims Forecasting Analyst\n\nYou will build Looker dashboards and forecasts in Python and SQL.\n")
    with open(os.path.join(st, "cv", "Morgan_Ellis_CV_Kestrel.tex"), "w", encoding="utf-8") as fh:
        fh.write("\\cvitem{Tools}{Python, SQL, Excel}\n")
    _git(st, "init", "-q")
    _git(st, "add", "-A")
    _git(st, "commit", "-q", "-m", "set me up")
    with open(os.path.join(st, "notes.md"), "w", encoding="utf-8") as fh:
        fh.write("a better board search\n")
    _git(st, "add", "-A")
    _git(st, "commit", "-q", "-m", "Profile upgrade: method-boards\n\nYour job sites were searched for again, the current way")
    with open(os.path.join(_git(st, "rev-parse", "--absolute-git-dir").strip(), app_setup.JOB_SITES), "w", encoding="utf-8") as fh:
        json.dump({"checked": "2026-10-25", "blocked": ["LinkedIn", "freehire"]}, fh)
    with open(os.path.join(prof, "person.json"), encoding="utf-8") as fh:
        pj = json.load(fh)
    pj["app_updates"] = "when_asked"
    with open(os.path.join(prof, "person.json"), "w", encoding="utf-8") as fh:
        json.dump(pj, fh, indent=1)
    import app_model
    import sync_app
    with pytest.MonkeyPatch.context() as mp:
        for k, v in _env(prof, st, "private").items():
            mp.setenv(k, v)
        mp.delenv("LJS_TODAY", raising=False)
        # A newer app is there to take: the stand-in for a fetch of the public app.
        mp.setattr(sync_app, "waiting", lambda *a, **k: "c" * 40)
        mp.setattr(sync_app, "waiting_line", lambda *a, **k: "A newer version is ready: 4.0.0.")
        mp.setattr(app_setup, "_app_changelog", lambda *a, **k: "## 4.0.0 (2026-10-26)\n\n- The page.\n")
        mp.setattr(app_setup, "is_migration", lambda *a, **k: True)
        model, _ = app_model.build(*app_model.clock("2026-10-25", NOW))
    assert app_model.check(model) == []
    path = os.path.join(tmp, "rich.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    out["rich"] = (path, {})
    out["models"] = {"rich": model}
    return out


@pytest.fixture(scope="module")
def run():
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node here, so no browser: the page's browser tests need Node and Playwright")
    env = _node_env()
    probe = subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True,
                           text=True, encoding="utf-8")
    if probe.returncode:
        pytest.skip("Playwright for Node is not installed here")
    proc = subprocess.Popen([node, HARNESS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)
    r = Runner(proc)
    hello = r.first()
    if not hello.get("ready"):
        proc.kill()
        pytest.skip("Chromium would not start: " + str(hello.get("error", ""))[:200])
    yield r
    proc.stdin.close()
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()


def _go(run, built, name, **kw):
    html, seed = built[name]
    got = run("engine", html=html, seed=seed, viewport=kw.pop("viewport", PHONE), **kw)
    assert not got["errors"], got["errors"]
    return got


# ------------------------------------------------------------------ the example search


def test_every_section_shows_the_engines_items_in_plain_words(run, built):
    got = _go(run, built, "small", hashes=["todo", "jobs", "drafts", "contacts", "interviews", "progress"])
    t = got["texts"]
    assert "Panel interview with Thornbury Bank" in t["todo"] and "Did you apply to Dovecote Freight?" in t["todo"]
    assert "Reply to Juno at Larkspur Retail" in t["todo"] and "Not made yet" in t["todo"]
    assert "Brindle Hart Logistics · Manchester (hybrid)\n" in t["jobs"], "hybrid is said once"
    assert "Juno at Larkspur Retail replied to you" in t["jobs"] and "Write to Juno" in t["jobs"]
    assert "Uses some of your Claude allowance, about" in t["jobs"], "a suggestion's cost is the amount and its real time"
    assert "Checked" in t["drafts"], "the check that passed is one word, its detail behind ?"
    fern = t["drafts"].split("Operations Analyst", 1)[1].split("Claims Forecasting Analyst", 1)[0]
    assert "Get the files" not in fern, "a file not made yet is not offered"
    assert "Replied: your turn" in t["contacts"], "every status the contact book holds has words"
    assert "Panel interview: Thornbury Bank" in t["interviews"]    # Coming up, by day (4.6)
    assert "1 earlier, finished: Show" in t["progress"]


def test_finished_history_opens_from_the_database_and_related_things_link(run, built):
    got = _go(run, built, "small", steps=[
        {"hash": "progress", "click": "Show", "read": "#main"},
        {"hash": "jobs", "more": "r9-2", "read": '[data-item="r9-2"]'},
    ])
    assert "Quayside Foods" in got["after"][0]["text"], "the rest of the list comes from view/list~applications~1"
    rel = got["after"][1]["text"]
    assert "Also at Kestrel Mutual" in rel and "your draft" in rel and "the note to Pell" in rel


@pytest.fixture(scope="module")
def many(built, tmp_path_factory):
    """The example search's page, and the view documents a far longer search writes an hour
    later: its jobs section is too big for one database document, so it goes in parts."""
    tmp = str(tmp_path_factory.mktemp("many"))
    state = app_state.many_jobs(os.path.join(tmp, "state"), n=400)
    seed = _seed(tmp, "many", _env(app_state.EXAMPLE, state, "private"), now="2026-10-25T19:00:00Z")
    return built["small"][0], seed


def test_a_jobs_section_in_parts_reaches_the_page_whole(run, many):
    html, seed = many
    assert "data" not in seed["screen/jobs"] and seed["screen/jobs"]["in_parts"] >= 2
    cards = '#main [data-card][data-item^="r9-"]'
    got = run("engine", html=html, seed=seed, viewport=PHONE,
              steps=[{"hash": "jobs", "count": cards, "read": "#main"}])
    assert not got["errors"], got["errors"]
    shown = got["after"][0]
    assert shown["count"] == 400, "every role the search found is on the page"
    assert "Forecasting Analyst 0" in shown["text"] and "Forecasting Analyst 399" in shown["text"]
    # A part not there yet (a write still arriving) is never read as the section: the page
    # keeps the jobs it already had.
    partial = {k: v for k, v in seed.items() if k != "screen/part~jobs~2"}
    got = run("engine", html=html, seed=partial, viewport=PHONE,
              steps=[{"hash": "jobs", "count": cards, "read": "#main"}])
    assert not got["errors"], got["errors"]
    assert "Forecasting Analyst 0" not in got["after"][0]["text"]
    assert got["after"][0]["count"] < 10
    assert "Brindle Hart Logistics" in got["after"][0]["text"]


# ------------------------------------------------------------------ setup and the private copy


def test_a_new_copy_asks_its_first_question_and_keeps_the_resume_it_is_given(run, built):
    got = _go(run, built, "fresh", hashes=["todo"], fake={"canSend": "available"}, steps=[
        {"hash": "todo", "click": "Start", "read": "dialog"},
        {"file": "my resume.pdf"},
    ])
    t = got["texts"]["todo"]
    assert "Set up your search" in t and "Start" in t
    assert "So far:" not in t, "nothing to count yet"
    screen = got["after"][0]["dialog"]
    assert "Your resume: add the file, or paste it." in screen and "Question 1 of 6" in screen
    for answer in ("Add my resume", "Paste it", "Build one with me"):
        assert answer in screen, answer
    (up,) = got["assets"]
    (a,) = [x for x in got["actions"] if x["action"] == "setup.resume"]
    assert a["item"] == "setup-resume" and a["value"] == {"asset": up["id"]} and a["rev_seen"]
    assert any(c.startswith("[app] [act:act~setup-resume~setup.resume") for c in got["rings"]), "a setup answer wakes a chat"


def test_an_answer_goes_to_the_engine_as_the_steps_own_fields(run, built):
    got = _go(run, built, "fresh", steps=[
        {"hash": "todo", "click": "Start"},
        {"click": "Paste it", "fill": {"Paste your resume here": "Analyst, 2019 to now."}},
        {"click": "Save it"},
    ])
    (a,) = [x for x in got["actions"] if x["action"] == "setup.resume"]
    assert a["value"] == {"text": "Analyst, 2019 to now."}
    assert "Claude is reading your answer." in got["after"][-1]["text"] or "Question 2 of 6" in got["after"][-1]["dialog"]


def test_on_the_app_itself_the_private_copy_comes_first_in_one_tap(run, built):
    got = _go(run, built, "app", hashes=["todo"], steps=[{"hash": "todo", "more": "q-setup-copy", "read": '[data-item="q-setup-copy"]'}])
    t = got["texts"]["todo"]
    assert "To make your own private copy" in t and "Make my private copy" in t
    assert "Your resume: add the file" not in t, "nothing can be kept before the copy exists"
    card = got["after"][0]["text"]
    assert "Open this link, signed in to GitHub" in card and "1. Open" not in card, "the steps are a list, numbered once"


def test_the_private_copy_link_is_githubs_own_form_with_private_chosen(run, built):
    html, _ = built["app"]
    with open(html, encoding="utf-8") as fh:
        body = fh.read()
    assert app_setup.COPY_LINK.replace("&", "\\u0026") in body or app_setup.COPY_LINK in body


# ------------------------------------------------------------------ a lived-in search


def test_one_card_an_item_however_many_things_are_wrong_and_no_button_twice(run, built):
    got = _go(run, built, "rich", hashes=["todo", "drafts"])
    todo, drafts = got["texts"]["todo"], got["texts"]["drafts"]
    assert todo.count("Operations Analyst") == 1, "the referral and the missing files are one card"
    assert "Wren has put your name forward at Fernhill Freight" in todo and "Not made yet" in todo
    assert "has put your name forward here: ask before" not in drafts, "the engine's alert says it once"
    assert "The posting asks for Looker; you have Power BI" in drafts
    assert "Confirm the call time" in todo or "Tam" in todo


def test_what_only_the_person_can_do_shows_the_registrys_steps_and_the_line_to_copy(run, built):
    got = _go(run, built, "rich", steps=[{"hash": "todo", "more": "q-setup-job-sites", "read": '[data-item="q-setup-job-sites"]'}])
    card = got["after"][0]["text"]
    assert "To let Claude reach job sites" in card and "Set Network access to Full" in card
    assert "apt-get update" in card and "Copy the line" in card
    assert "\n1. " not in card


def test_an_update_waiting_can_be_taken_and_an_improvement_made_is_said_not_undone(run, built):
    """Since 2026-10-30 an improvement has no Undo: taking one back reversed work later
    changes stood on, and the next update made it again. Anything unwanted is said in Chat."""
    model = built["models"]["rich"]
    got = _go(run, built, "rich", hashes=["settings"], steps=[
        {"hash": "settings", "click": "Update now"},
        {"hash": "settings", "open": "info-sum:news", "read": "#main"},
    ])
    t = got["texts"]["settings"]
    assert "A newer version is ready: 4.0.0." in t and "It starts once the work running now has finished." in t
    assert "Your job sites were searched for again, the current way." in got["after"][1]["text"], "What's new opens to what was done"
    by = {a["action"]: a for a in got["actions"]}
    assert by["app.update_now"]["item"] == "update-now" and by["app.update_now"]["rev_seen"] == model["updates"]["waiting"]["rev"]
    assert "upgrade.undo" not in by and "Undo this change" not in got["after"][1]["text"]
    assert "Say so in Chat and Claude puts it right." in got["after"][1]["text"]


def test_done_on_a_dated_action_is_sent_with_the_rev_it_was_seen_at(run, built):
    model = built["models"]["rich"]
    due = next(d for d in model["due"] if d["done"])
    got = _go(run, built, "rich", steps=[{"hash": "todo", "click": "Done: " + due["title"], "exact": True}])
    (a,) = [x for x in got["actions"] if x["action"] == "due.done"]
    assert a["item"] == due["id"] and a["rev_seen"] == due["rev"]


def test_an_alerts_own_action_carries_the_items_rev(run, built):
    model = built["models"]["rich"]
    pell = next(m for m in model["messages"])
    assert pell is not None
    got = _go(run, built, "rich", steps=[{"hash": "jobs", "click": "No thanks"}])
    (a,) = [x for x in got["actions"] if x["action"] == "suggest.dismiss"]
    job = next(r for r in model["jobs"]["rows"] if r.get("suggest"))
    assert a["item"] == job["suggest"]["id"] and a["rev_seen"] == job["suggest"]["rev"]


def test_a_job_a_chat_ruled_out_leaves_the_list(built):
    title, company = built["ruled"]
    rows = [r for r in built["models"]["rich"]["jobs"]["rows"] if r["title"] == title and r["company"] == company]
    assert rows and all(r["status"] == "dismissed" for r in rows), rows
