"""The person's page, driven in a real browser against a fake of the viewer's capabilities.

After setup a person does everything on one private Claude page (tools/app_page.py renders
it). These tests open that page in Chromium through Playwright, which the Node runner in
tests/app_page/harness.js holds open for the whole module, with window.claude replaced by
tests/app_page/fake_claude.js. The fake keeps the db in the runner, so two tabs of one test
share it as two windows of the real page share one store, and a chat is simulated by
writing to it pinned to a version, as ArtifactData does.

What they cannot show is anything only a real viewer does: the consent prompts, the real
comment doorbell waking a chat, downloads landing on a phone. The page's App section lists
what works on the device it is opened on, for that.

Screenshots are written only when LJS_SHOTS names a folder.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "templates", "app"))
import app_page  # noqa: E402
import palettes  # noqa: E402

HARNESS = os.path.join(ROOT, "tests", "app_page", "harness.js")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json")
SHOTS = os.environ.get("LJS_SHOTS", "")
PHONE = {"width": 375, "height": 812}
WIDE = {"width": 1440, "height": 900}


def _rgb(name):
    h = palettes.PALETTES[name]["bg"][0].lstrip("#")  # name: "light" (dawn) or "dark" (main)
    return "rgb(%d, %d, %d)" % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------ the runner

class Runner:
    def __init__(self, proc):
        self.proc = proc
        self.lines = queue.Queue()
        self.n = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def first(self, timeout=60):
        line = self.lines.get(timeout=timeout)
        return json.loads(line) if line else {"ready": False, "error": "the runner exited"}

    def __call__(self, scenario, **args):
        self.n += 1
        self.proc.stdin.write(json.dumps({"id": self.n, "scenario": scenario, "args": args}) + "\n")
        self.proc.stdin.flush()
        line = self.lines.get(timeout=180)
        assert line, "the browser runner stopped"
        got = json.loads(line)
        assert got.get("ok"), got.get("error")
        return got["result"]


def _node_env():
    env = dict(os.environ)
    paths = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            out = subprocess.run([npm, "root", "-g"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30)
            if out.returncode == 0 and out.stdout.strip():
                paths.append(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    env["NODE_PATH"] = os.pathsep.join(paths)
    if SHOTS:
        env["LJS_SHOTS"] = SHOTS
    return env


@pytest.fixture(scope="module")
def run():
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node here, so no browser: the page's browser tests need Node and Playwright")
    env = _node_env()
    probe = subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
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


def _write(tmp, name, model):
    path = os.path.join(str(tmp), name + ".html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    return path


def _sample():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


EMPTY = {"model": 1, "made_at": "2026-10-25T08:00:00Z", "rev": "0",
         "person": {"first_name": "Morgan", "doc_noun": "CV", "time_zone": "Europe/London",
                    "repo": "morgan-example/job-search", "computer": True}}


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("page")
    big = _sample()
    rows = []
    companies = ["Harbourline Bank", "Larkspur Retail", "Copperleaf Pay", "Ellerwick Trust",
                 "Brackenridge Advisory", "Kestrel Mutual", "Fernhill Freight", "Quayside Foods"]
    for i in range(60):
        rows.append({"id": "r20-%d" % i, "rank": i + 1, "score": 90 - i // 2, "band": "good",
                     "company": companies[i % len(companies)], "title": "Analyst role %d" % (i + 1),
                     "place": "Manchester", "remote": "hybrid",
                     "pay": {"text": "not stated", "stated": False} if i % 3 else {"text": "GBP 40,000", "stated": True},
                     "deadline": None, "warm": None,
                     "apply": {"url": "https://example.com/jobs/%d" % i, "kind": "board", "checked_at": None, "status": "not_checked"},
                     "notes": [], "status": "new", "questions": ["Have you already applied?"], "rev": "b%d" % i})
    big["jobs"] = dict(big["jobs"], rows=rows, summary="Searched widely: 60 worth a look.")
    # A person with a long history: 40 live applications and 300 contacts, of whom a few are live.
    crowd = _sample()
    apps, people = [], []
    for i in range(60):
        live = i < 40
        apps.append({"company": companies[i % len(companies)], "role": "Analyst role %d" % (i + 1),
                     "applied_on": "2026-%02d-%02d" % (10 if live else 5, 1 + i % 20),
                     "status": ["applied", "interview", "offer", "applied"][i % 4] if live else ["rejected", "closed", "withdrawn"][i % 3],
                     "last": "2026-%02d-%02d" % (10 if live else 6, 1 + i % 20)})
    first = ["Juno", "Wren", "Tamsin", "Ash", "Ivo", "Sasha", "Marisol", "Rowan"]
    for i in range(300):
        if i < 12:
            st, last = ["in_conversation", "awaiting_reply", "call_booked"][i % 3], "2026-10-%02d" % (5 + i)
        else:
            st, last = ["awaiting_reply", "closed", "cold"][i % 3], "2026-0%d-%02d" % (3 + i % 4, 1 + i % 25)
        people.append({"id": "c%d" % i, "first_name": first[i % len(first)], "employer": companies[i % len(companies)],
                       "status": st, "last": last, "next_action": "Reply" if st == "in_conversation" else None,
                       "due": "2026-10-27" if st == "in_conversation" else None})
    crowd["done"] = dict(crowd["done"], applications=apps)
    crowd["applications"] = [dict(x, id="crowd-app-%d" % i, rev="ca%d" % i) for i, x in enumerate(apps)]
    crowd["people"] = people
    crowd["due"] = []
    kinds = _sample()
    kinds["settings"] = kinds["settings"] + [
        {"key": "computer_listen", "label": "Let this page reach Claude on your computer while it is open", "kind": "toggle", "value": False, "id": "setting-computer_listen", "rev": "stk1"},
        {"key": "brief_days", "label": "Days the brief arrives", "kind": "text", "value": "Monday and Thursday", "id": "setting-brief_days", "rev": "stk2"}]
    hostile = _sample()
    hostile["jobs"]["rows"][0]["title"] = "</script><script>window.__pwned=1</script><!-- Analyst"
    hostile["needs_you"][0]["title"] = "<img src=x onerror=window.__pwned=2>"
    # A referral in flight that has not yet led to a call: a cold application is still possible,
    # so the page asks before one goes.
    held = _sample()
    held["interviews"] = [i for i in held["interviews"] if i["id"] != "int-copperleaf-payments"]
    # A busy week (the maintainer, 2026-10-26): follow-ups to several people, two notes that
    # may have gone, the same warning on three messages, a question from an update, and
    # follow-ups hidden at employers turned down.
    busy = _sample()
    ppl = busy["people"][:3]
    nudge = next(d for d in busy["due"] if d["kind"] == "nudge")
    busy["due"] = [d for d in busy["due"] if d["kind"] != "nudge"] + [
        dict(nudge, id="due-nudge-%s" % p["id"], contact=p["id"], item=None, title="Follow up with %s at %s" % (p["first_name"], p["employer"]),
             context="Analyst at %s" % p["employer"], work={"kind": "follow_up", "id": "follow_up~%s" % p["id"], "args": {"contact": p["id"]}},
             rev="bn%d" % i) for i, p in enumerate(ppl)] + [
        {"id": "due-hidden", "kind": "hidden", "sub": "hidden", "title": "4 follow-ups at employers you turned down not shown",
         "context": "", "due": None, "company": "", "overdue_days": 0, "action": None, "item": None, "work": None,
         "done": None, "snooze": None, "rev": "bh"}]
    sent = next(n for n in busy["needs_you"] if n["id"].startswith("q-sent-"))
    busy["needs_you"] = busy["needs_you"] + [
        dict(sent, id="q-sent-%s" % ppl[1]["id"], title="Did your note to %s go?" % ppl[1]["first_name"],
             about={"company": ppl[1]["employer"], "contact": ppl[1]["id"]}, rev="bs1"),
        {"id": "q-upgrade-demo", "kind": "upgrade_ask", "title": "Turn on the new reading pace?", "body": "",
         "options": [{"label": "Yes", "action": "upgrade.answer", "value": "yes"}, {"label": "Not now", "action": "upgrade.answer", "value": "no"}],
         "about": {}, "rev": "bu"}]
    for m in busy["messages"][:3]:
        m["alerts"] = [{"id": "al-read-" + m["id"], "kind": "read_first", "level": 1, "text": "Written before their profile was read",
                        "why": "A note written before their profile was read can get them wrong.", "action": {}, "cost": {"state": 0}}]
    busy["done"] = dict(busy["done"], recent={"days": 30, "counts": {"applied": 1, "interviews": 0, "offers": 0, "replies": 2},
                                              "funnel": [{"stage": "applied", "n": 1}, {"stage": "interview", "n": 0}, {"stage": "offer", "n": 0}]})
    # Set up, with nothing found yet: every list says what will appear there.
    nothing = dict(EMPTY, setup={"state": "done", "steps": []})
    return {"sample": _write(tmp, "sample", _sample()), "empty": _write(tmp, "empty", EMPTY), "nothing": _write(tmp, "nothing", nothing), "held": _write(tmp, "held", held),
            "big": _write(tmp, "big", big), "hostile": _write(tmp, "hostile", hostile),
            "crowd": _write(tmp, "crowd", crowd), "kinds": _write(tmp, "kinds", kinds), "busy": _write(tmp, "busy", busy)}


def _clean(r):
    assert not r.get("errors"), r.get("errors")


# ------------------------------------------------------------------ first paint and who sees it

def test_the_owner_sees_the_page_and_anyone_else_sees_only_a_private_notice(run, pages):
    # The sample page was made on 25 October, and what is late is counted from the viewer's
    # clock: the page is opened on its own day, so the count does not change with the date.
    own = run("paint", html=pages["sample"], clock="2026-10-25T09:00:00Z")
    _clean(own)
    assert own["shellShown"] and not own["privateShown"] and not own["opening"]
    # It opens on the Brief, greeting the person by name (4.3).
    assert own["heading"] == "Good morning, Morgan" and own["cards"] >= 4
    assert own["brand"] == "Morgan’s job search"
    # One card, one thing (4.3): today's To do cards that still need the person, the number
    # To do's own summary leads with.
    assert own["title"] == "(11) Morgan’s job search", "four answers, the things due today or late, and the alerts, a card each"
    assert own["conn"] == "live" and own["pulse"].startswith("Connected.")
    assert own["overflow"]["sw"] <= own["overflow"]["cw"]
    for fake in ({"owner": False}, {"noClaude": True}, {"caps": []}):
        other = run("paint", html=pages["sample"], fake=fake)
        _clean(other)
        assert other["privateShown"] and not other["shellShown"], fake
        assert "This page is private" in other["bodyText"]
        for word in ("Harbourline", "Juno", "Morgan", "Looker", "To do"):
            assert word not in other["bodyText"], (fake, word)
        assert other["title"] == "Private page"
    no_app = run("paint", html=pages["sample"], fake={"noClaude": True})
    assert "open it in the Claude app" in no_app["bodyText"]


def test_nothing_personal_shows_until_the_owner_check_answers(run, pages):
    r = run("private_gate", html=pages["sample"])
    _clean(r)
    assert r["before"]["opening"] and not r["before"]["shell"]
    for word in ("Harbourline", "Juno", "Looker", "Morgan"):
        assert word not in r["before"]["text"], word
    assert r["after"]["shell"] and r["after"]["heading"] == "Good morning, Morgan"


def test_without_a_store_the_page_says_it_is_read_only(run, pages):
    r = run("paint", html=pages["sample"], fake={"caps": ["user"]})
    _clean(r)
    assert r["heading"] == "Good morning, Morgan" and r["conn"] == "readonly"
    assert r["pulse"].startswith("Read only here: this page cannot keep answers.")


# ------------------------------------------------------------------ every section, full and empty

# Drafts are a view of Jobs, the messages to send a view of Contacts, and the Brief greets the
# person by name (4.3).
LABELS = {"brief": "Good morning, Morgan", "todo": "To do", "jobs": "Jobs", "drafts": "Jobs", "drafts-messages": "Contacts",
          "contacts": "Contacts", "interviews": "Interviews", "progress": "Progress", "chat": "Chat", "settings": "Settings",
          "profile": "Your profile"}
JARGON = re.compile(r"\b(?:repository|repo|branch|worktree|commit|pull request|PR|git|json|database|db|artifact|webhook|"
                    r"session id|config\w*|null|undefined|NaN|your chat|cloud chat|computer chat|downloadable|applies)\b", re.I)
OLD_NAMES = re.compile(r"\b(?:Today|To send|Ready to send|Needs you|Ask|Talk|People)\b")


def test_every_section_full_shows_its_items_in_plain_words(run, pages):
    r = run("sections", html=pages["sample"], viewport=PHONE, shots="phone" if SHOTS else "")
    _clean(r)
    for sid, label in LABELS.items():
        got = r[sid]
        assert got["heading"] == label, (sid, got["heading"])
        assert got["overflow"]["sw"] <= got["overflow"]["cw"], sid
        assert not JARGON.search(got["text"]), (sid, JARGON.search(got["text"]).group(0))
        assert not re.search(r"\b\d+\.\d+\.\d+\b", got["text"]), (sid, "a version number")
        assert "—" not in got["text"] and "–" not in got["text"], sid
        heads = re.findall(r"^(?:To do here|Needs your answer|Due or late|Next 7 days|Later)$", got["text"], re.M)
        assert not OLD_NAMES.search(" ".join(heads)), sid
    for sid, n in {"todo": 8, "jobs": 3, "drafts": 2, "drafts-messages": 2, "contacts": 4, "interviews": 2, "progress": 10}.items():
        assert r[sid]["items"] >= n, (sid, r[sid]["items"])
    jobs = r["jobs"]["text"]
    assert "Pay not stated" in jobs, "a job with no pay says so and loses nothing"
    assert "£46,000 to £52,000" in jobs, "pay in the person's own money"
    assert "Before you apply: Juno at Larkspur Retail replied last week" in jobs
    assert "This posting has closed." in jobs and "41 left out by the search" in jobs
    assert "Tamsin has put your name forward at Copperleaf Pay" in jobs
    drafts = r["drafts"]["text"]
    assert "Two answers about Quayside Foods" in drafts, "a draft's question is on its card, ahead of its other notes"
    assert "Made for Tamsin, who asked for it." in drafts and "I sent it to Tamsin" in drafts
    assert "put your name forward here" not in drafts, "the referrer's own resume carries no hold"
    # Drafts are a view of Jobs: its switch, Found, Drafts and Applied (4.3).
    assert "Found" in drafts and "Applied" in drafts
    msgs = r["drafts-messages"]["text"]
    assert "First notes this week" in msgs and "3 notes ready. 3 sent this week of about 20." in msgs
    assert "LinkedIn InMail" in msgs and "Subject:" in msgs and "Copy subject" in msgs
    assert "Every application" in r["progress"]["text"] and "earlier, finished" in r["progress"]["text"]
    settings = r["settings"]["text"]
    assert "An update is waiting" in settings and "4.0.1" not in settings
    # How the app runs waits, folded, at the end (4.3).
    assert "How the app runs" in settings and "Auto" in settings and "Your profile" in settings


@pytest.mark.parametrize("viewport", [PHONE, WIDE])
def test_a_screen_shows_at_most_three_question_marks_before_scrolling(run, pages, viewport):
    # Each "?" explains one thing where it is asked about, and never crowds a screen (the
    # maintainer, 2026-10-29: "we're not spamming ? stuff are we now?").
    r = run("sections", html=pages["sample"], viewport=viewport)
    _clean(r)
    busy = {sid: (v["qsFirst"], v["qKeys"]) for sid, v in r.items() if isinstance(v, dict) and v.get("qsFirst", 0) > 3}
    assert not busy, busy
    tips = {sid: v["tips"] for sid, v in r.items() if isinstance(v, dict) and v.get("tips", 0) > 1}
    assert not tips, ("one tip a screen at most", tips)


@pytest.mark.parametrize("section", list(LABELS))
def test_every_control_on_every_screen_does_something_and_nothing_throws(run, pages, section):
    # Each control tapped on a fresh page (the maintainer, 2026-10-29: "I'm starting to doubt
    # even some of the buttons work"): it opens, sends, moves or changes something on screen,
    # nothing throws, and every link to another site has a real address.
    r = run("sweep", html=pages["sample"], viewport=PHONE, clock="2026-10-25T09:00:00Z", sections=[section])
    assert r["tapped"] == r["perSection"][section] or r["tapped"] == 80, r
    assert not r["errors"], r["errors"]
    assert not r["unclickable"], r["unclickable"]
    assert not r["dead"], ("a tap that did nothing", r["dead"])
    assert not r["badLinks"], r["badLinks"]


def test_every_section_empty_says_what_will_appear_and_offers_one_step(run, pages):
    r = run("sections", html=pages["nothing"], viewport=PHONE)
    _clean(r)
    expect = {"jobs": "No shortlist yet.", "drafts": "Nothing drafted yet.", "drafts-messages": "No messages to send.",
              "contacts": "Nobody here yet.", "interviews": "No interviews booked.", "progress": "Nothing counted yet."}
    for sid, title in expect.items():
        assert r[sid]["empty"] == [title], (sid, r[sid]["empty"])
        assert r[sid]["overflow"]["sw"] <= r[sid]["overflow"]["cw"], sid
    assert "Up to date" in r["settings"]["text"]


def test_a_first_run_offers_setup_everywhere_and_never_an_empty_list(run, pages):
    r = run("sections", html=pages["empty"], viewport=PHONE)
    _clean(r)
    assert "Set up your search" in r["todo"]["text"], "a first run is never an empty To do with nothing to press"
    assert "Start" in r["todo"]["text"]
    for sid in ("jobs", "drafts", "contacts", "interviews"):
        assert r[sid]["empty"] == ["Your search is not set up yet"], (sid, r[sid]["empty"])
        assert "Continue setting up" in r[sid]["text"], sid


def test_sixty_jobs_render_select_and_fit_a_phone(run, pages):
    r = run("big", html=pages["big"], viewport=PHONE)
    _clean(r)
    assert r["cards"] == 60, "every live job shows without a tap"
    assert r["search"], "a list over 25 gets a search box"
    assert r["bar"].startswith("60 selected") and "Draft 60" in r["bar"] and "Mark 60 as applied" in r["bar"]
    assert r["overflow"]["sw"] <= r["overflow"]["cw"]


def test_a_long_history_shows_every_live_thing_without_a_tap_and_folds_only_the_finished(run, pages):
    r = run("crowd", html=pages["crowd"], viewport=PHONE)
    _clean(r)
    assert r["progressRows"] == 40, "40 live applications, all shown"
    assert any(f.startswith("20 earlier, finished") for f in r["progressFold"])
    assert r["progressSearch"] and r["contactSearch"]
    assert r["contactDefault"] == 8 and not r["defaultChips"], \
        "Contacts opens on the 8 who need the person, with no filter left on (4.3)"
    assert any(f.startswith("292 more people, nothing owed to them now") for f in r["contactFold"]), r["contactFold"]
    assert r["searched"] >= 1 and r["searchFocus"] == "search", "typing in the search box keeps its focus"
    assert any("hidden by your filters" in f for f in r["hidden"])
    assert r["cleared"] == 8
    assert r["unfolded"] == 8 + 50, "the fold opens fifty at a time beyond the ones who need you"
    assert r["overflow"]["sw"] <= r["overflow"]["cw"]


def test_text_from_the_model_is_text_never_markup(run, pages):
    r = run("paint", html=pages["hostile"], hash="jobs")
    _clean(r)
    assert "</script><script>window.__pwned=1</script>" in r["bodyText"]
    r2 = run("paint", html=pages["hostile"], hash="todo")
    assert "<img src=x onerror=window.__pwned=2>" in r2["bodyText"]


def test_a_newer_view_document_replaces_its_section_without_a_republish(run, pages):
    r = run("view_overlay", html=pages["sample"])
    _clean(r)
    assert r["titles"] == ["Senior Research Analyst"]
    assert r["lede"].startswith("1 to look at"), r["lede"]


# ------------------------------------------------------------------ To do, alerts and suggestions

def test_to_do_groups_by_when_then_by_employer_in_the_order_things_are_done(run, pages):
    r = run("todo", html=pages["sample"])
    _clean(r)
    assert r["first"] == "Phone screen with Larkspur Retail", "the soonest interview within 14 days is the first card"
    # Five show first; a band split by the fold heads its rest again inside it (4.3).
    assert list(dict.fromkeys(b["band"] for b in r["bands"])) == ["Needs your answer", "Due or late", "Next 7 days", "Later"]
    for b in r["bands"]:
        for g in b["groups"]:
            assert g["employer"] is None or len(g["titles"]) >= 2, ("an employer heads only two or more", b["band"], g)
    answer = r["bands"][0]["groups"]
    assert answer[0]["employer"] == "Fernhill Freight" and len(answer[0]["titles"]) == 2, "one employer's two questions together"
    late = r["bands"][1]["groups"]
    assert late[0]["titles"][0].startswith("Follow up with Fernhill Freight"), "the late thing first"
    titles = [t for b in r["bands"] for g in b["groups"] for t in g["titles"]]
    assert "Prepare for the Larkspur Retail phone screen" not in titles, "the interview's own card is its prep, never a second card"
    assert "Thank-you note after your Harbourline Bank first interview" in titles
    assert r["dueButtons"]["Thank-you note after your Harbourline Bank first interview"][0] == "Draft the thank-you"
    assert r["dueButtons"]["Send your CV to Tamsin"][0] == "Choose the role"
    assert r["dueButtons"]["Reply to Juno at Larkspur Retail"][0] == "Draft a reply"
    assert all("Done" in b for b in r["dueButtons"].values()), "every due row can be marked done"
    assert titles.count("3 first notes ready to send") == 1, "a wave of first notes is one card"
    assert r["chips"] == 0, "no kind chips on To do"
    assert r["filled"] == 0 and r["answers"] >= 8, "a question never fills one of its answers"
    assert r["jobsQuestion"] and "Have you used Looker?" in r["jobsQuestion"], "Jobs asks its question on the role's own card"
    assert r["juno"]["state"] == "Replied: your turn" and "Draft a reply" in r["juno"]["buttons"], r["juno"]


def test_an_alert_is_a_line_with_one_button_and_a_suggestion_can_be_declined_for_good(run, pages):
    r = run("alerts", html=pages["sample"])
    _clean(r)
    assert [" ".join(x.split()) for x in r["closed"]] == ["Needs fixing: This posting has closed."]
    assert r["cost"] == [], "a free fix says no cost on the card"
    assert r["fixed"]["action"] == "job.dismiss" and r["fixed"]["item"] == "r12-5"
    assert r["suggest"] and " ".join(r["suggest"][0].split()).startswith("Suggestion: The posting asks for Tableau")
    assert r["checksFix"] == ["Make it again"], "a failed check is a To do card with its fix, while the draft asks its question"
    assert r["dismissed"]["action"] == "suggest.dismiss" and r["dismissed"]["value"] == {"kind": "near"}
    assert r["gone"] == 0 and any("not be suggested again" in t for t in r["toast"])
    assert r["back"] == 1, "No thanks can be undone"
    assert r["offSuggest"] == 0 and r["offAlerts"] >= 1, "Suggestions off hides suggestions, never alerts"


def test_a_referral_in_flight_asks_before_a_draft_or_an_application(run, pages):
    r = run("referral", html=pages["held"])
    _clean(r)
    assert any("Tamsin has put your name forward at Copperleaf Pay" in a for a in r["alert"])
    assert r["primary"] == ["Ask Tamsin first"]
    assert r["confirm"]["title"] == "Tamsin has put your name forward at Copperleaf Pay"
    assert "the referral can be lost" in r["confirm"]["intro"] and r["confirm"]["go"] == "Mark as applied anyway"
    assert r["afterNo"] == [], "Not now records nothing"
    assert r["draftConfirm"] == "Draft it anyway"
    assert r["draftSheet"].startswith("Draft this: Copperleaf Pay") and "Tamsin" in r["lead"]
    assert r["warmLink"] == "#contacts/larkspur_retail_castellan", "the warm note links to the person it names"


# ------------------------------------------------------------------ acting: saved, receipted, undone

def test_a_tap_is_saved_only_when_it_is_and_done_when_its_receipt_arrives(run, pages):
    r = run("action_receipt", html=pages["sample"])
    _clean(r)
    assert len(r["ids"]) == 1 and r["ids"][0] == "actions/act~msg-juno-1~msg.sent"
    doc = r["doc"]
    assert doc["item"] == "msg-juno-1" and doc["action"] == "msg.sent" and doc["rev_seen"] == "m1"
    assert doc["tab"] and doc["at"].endswith("Z")
    assert r["saved"].startswith("Saved. Claude will pick this up.")
    assert "Marked as sent: Juno" in r["toast"]
    assert r["focusAfter"]["inCard"], "focus stays with the item that changed"
    assert r["done"].startswith("Done.") and r["moved"] == 3, "once done it moves to Sent or skipped: three of four cards left"
    assert "Change back" in r["back"], "and where the chat left a way back, it can be changed back"
    assert r["refused"].startswith("Not done: this changed since you saw it.")
    assert "Answered differently on your phone." in r["refused"]


def test_a_failed_save_says_so_at_once_and_never_says_saved(run, pages):
    r = run("write_fail", html=pages["sample"])
    _clean(r)
    assert any(t.startswith("Not saved: Marked as sent: Juno") for t in r["toast"])
    assert any("Try again" in t for t in r["toast"])
    assert r["state"].startswith("Not saved.") and "Try again" in r["state"]
    assert r["alert"].startswith("Not saved") and "Saved." not in r["live"]


def test_undo_stays_on_the_item_until_claude_has_done_it(run, pages):
    r = run("undo", html=pages["sample"])
    _clean(r)
    assert r["before"] == ["actions/act~r12-1~job.dismiss"]
    assert r["marked"], "a role set aside stays in place, marked, until it is done"
    assert r["focus"] == "Undo", "focus moves to the item's Undo"
    assert r["undoShown"] == 1
    assert r["after"] == [], "Undo deletes the action before any chat applied it"
    assert "Pricing Analyst" in r["back"]
    assert r["reason"]["value"] == {"why": "pay"}, "a reason, if they give one, goes with the same action"
    assert r["during"] >= 1
    assert r["later"] == {"toast": 0, "item": 1}, "the toast goes; the item's Undo stays"
    assert r["kept"] == ["actions/act~r12-3~job.dismiss"]


def test_bulk_select_is_a_mode_and_marks_several_each_their_own_action(run, pages):
    r = run("bulk", html=pages["sample"])
    _clean(r)
    assert r["boxesBefore"] == 0, "no checkboxes until Select is tapped"
    assert r["mixed"] is True, "select all shows a mixed state for a partial selection"
    assert r["bar"].startswith("2 selected")
    assert r["confirm"] == "Tamsin has put your name forward at Copperleaf Pay"
    got = sorted((a["item"], a["action"]) for a in r["actions"])
    assert got == [("r12-1", "job.applied"), ("r12-3", "job.applied")]
    assert all(len(a["value"]["on"]) == 10 for a in r["actions"]), "the day it went, as the engine reads it"
    assert sorted(r["after"]) == ["Data Analyst, Payments", "Pricing Analyst"], "they stay in place, marked, until done"
    assert sorted(r["readyActions"]) == ["actions/act~app-ellerwick-insight~ready.applied", "actions/act~app-quayside-demand~ready.applied"]
    assert r["toastAboveBulk"] in (True, None), "a toast never covers the bulk bar"


def test_settings_save_once_the_person_settles_and_show_the_new_value(run, pages):
    r = run("settings", html=pages["kinds"], kinds=True)
    _clean(r)
    assert r["early"] == 0, "arrowing through a group does not save on the way"
    got = {(a["item"], json.dumps(a["value"])) for a in r["actions"]}
    assert ("setting-app_updates", '"when_asked"') in got
    assert ("setting-computer_listen", "true") in got
    assert ("setting-brief_days", '"Tuesday"') in got
    assert r["checked"] is True
    assert r["names"][0] == "An update is waiting", "an update waiting is the first row"
    # Then Your profile, a page of its own (4.3); then the search, the brief, the look; how
    # the app runs last, folded.
    assert r["names"][1].startswith("Your profile"), r["names"]
    look = r["names"].index("Look")
    assert r["names"][look:look + 2] == ["Look", "Size"]
    adv = r["names"].index("Where Claude works")
    assert adv > look and r["names"][adv:adv + 2] == ["Where Claude works", "Suggestions"], r["names"]


# ------------------------------------------------------------------ asking a chat for work

def test_draft_this_asks_its_questions_first_says_what_it_costs_and_rings_with_no_words(run, pages):
    r = run("draft", html=pages["sample"], shot="phone-draft" if SHOTS else "")
    _clean({"errors": r["pageErrors"]})
    assert r["open"] and r["focusInDialog"]
    assert r["legends"][0] == "Have you already applied for this role?"
    assert any("fixed term" in x for x in r["legends"])
    # The gauge's own words, then the time (4.3).
    assert "About 9 minutes." in r["cost"] and "Nothing is sent." in r["cost"]
    assert r["stillOpen"] and len(r["errors"]) == 2, "unanswered questions are named, nothing is asked of a chat"
    assert r["submitWhenApplied"] == "Mark as applied" and r["submitWhenNot"] == "Draft it", "the button says what it will do"
    assert r["closed"]
    w = r["work"]
    assert w["kind"] == "draft" and w["status"] == "queued" and w["to"] == "cloud"
    assert w["title"] == "CV and letter: Harbourline Bank, Pricing Analyst"
    assert w["args"]["already_applied"] == "no" and w["args"]["job"] == "r12-1"
    assert w["args"]["answers"] == [{"q": "Are you happy with a 12 month fixed term?", "a": "yes"}]
    assert [s["name"] for s in w["stages"]][0] == "Getting started" and all(s["est_s"] > 0 for s in w["stages"])
    rings = [c for c in r["calls"] if c["cap"] == "comments"]
    assert len(rings) == 1 and rings[0]["text"] == "[app] [work:draft~r12-1]"
    assert r["doorbell"]["ids"] == ["draft~r12-1"] and r["doorbell"]["thread"]
    assert r["chip"] == "Drafting", "a role being drafted stays in place, marked"
    assert "1 waiting" in r["pill"], "work just asked for is a pill in the header, waiting until a chat takes it"


def test_already_applied_is_recorded_and_nothing_is_drafted(run, pages):
    r = run("applied_first", html=pages["sample"])
    _clean(r)
    assert r["work"] == []
    assert [(a["item"], a["action"], a["value"]) for a in r["actions"]] == [("r12-1", "job.applied", {"on": "2026-10-20"})]


def test_two_windows_pressing_draft_at_once_make_one_job_and_one_ring(run, pages):
    r = run("two_tabs", html=pages["sample"])
    _clean(r)
    assert r["work"] == ["work/draft~r12-1"]
    assert r["rings"] == 1
    assert any("already on its way" in t for t in r["toasts"])
    assert r["tabs"][0] != r["tabs"][1], "each window has its own id for its actions"
    assert all(s and "1 waiting" in s for s in r["seen"]), r["seen"]
    assert r["actions"] == ["actions/act~msg-juno-1~msg.sent"]
    assert r["otherWindow"] == {"chip": ["Marked as sent"], "buttons": 0}, "the other window cannot tick it again"


def test_a_chat_beside_the_page_is_rung_from_the_click_itself(run, pages):
    r = run("room", html=pages["sample"])
    _clean(r)
    room = [c for c in r["calls"] if c["cap"] == "room"]
    assert len(room) == 1 and room[0]["active"] is True, "sendToClaudeSession runs inside the click"
    assert room[0]["opts"] == {"deliver": "send", "attachPresence": False}
    assert room[0]["data"]["work"] == "draft~r12-1"
    assert not [c for c in r["calls"] if c["cap"] == "comments"], "one ring, not two"
    assert r["work"] == ["work/draft~r12-1"]


def test_with_no_chat_listening_it_says_when_it_starts_and_offers_to_start_it_now(run, pages):
    r = run("no_listener", html=pages["sample"])
    _clean(r)
    assert r["calls"] == []
    assert any("not working on your search right now" in n for n in r["notes"])
    assert r["links"] and r["links"][0].startswith("https://claude.ai/code?prompt=")
    assert "repositories=morgan-example%2Fjob-search" in r["links"][0]
    assert r["work"]["status"] == "queued", "the request waits in the list whoever rings"


# ------------------------------------------------------------------ progress that costs nothing

def test_progress_moves_with_the_clock_marks_a_stall_and_tries_again(run, pages):
    r = run("progress", html=pages["sample"], shot="phone-work-done" if SHOTS else "")
    _clean(r)
    assert r["sheet"], "on a phone the work opens as a sheet"
    # One thing running is named in the pill (the maintainer, 2026-10-29: be clear what runs).
    assert "Finding jobs" in r["pill"]
    a0, a150 = r["at0"], r["at150"]
    # Stages of 60, 300 and 120 s; the second has just started, 60 of 480 s behind it.
    assert a0["now"] == 12
    assert a150["now"] == 43, "150 s into a 300 s stage: (60 + 150) / 480"
    assert "about" in a150["time"] and "left" in a150["time"]
    assert any(s.startswith("step-done") for s in a150["steps"]) and any(s.startswith("step-now") for s in a150["steps"])
    s2 = r["stage2"]
    assert s2["sentence"] == "Scoring 214 postings, 3 of 4 done", "one live sentence, in words"
    assert any("step-now:Now: Scoring" in s for s in s2["steps"])
    st = r["stalled"]
    assert st["status"] == "Stalled" and st["now"] == 97, "held below 100 until done"
    assert any("more than twice as long as usual" in w for w in st["warn"])
    assert "Try again" in st["buttons"] and "Stop" in st["buttons"]
    w = r["retried"]
    assert w["status"] == "queued" and w["attempt"] == 2 and w["stage"] == 0 and w["claimed_by"] is None
    assert len(r["rings"]) == 1 and r["rings"][0]["text"] == "[app] [work:search~1]"
    assert r["done"]["now"] == 100 and r["done"]["status"] == "Ready"


def test_two_stalls_at_once_read_as_the_plan_limit_offer_no_retry_and_pause_everything(run, pages):
    r = run("limit", html=pages["sample"])
    _clean(r)
    assert any("usage limit" in b and "nothing retries by itself" in b for b in r["banner"])
    assert "Try again" not in r["a"]["buttons"]
    assert r["paused"] == [True, True]


def test_stop_says_what_is_kept(run, pages):
    r = run("stop", html=pages["sample"])
    _clean(r)
    assert r["late"]["status"] == "Not picked up yet"
    assert "Ask Claude again" in r["rewake"]
    assert r["prefill"] and r["prefill"].startswith("https://claude.ai/code?prompt=")
    assert r["running"]["stop_asked"] is True and r["running"]["status"] == "running"
    assert r["runningCard"]["status"] == "Stopping after this step"
    assert "Stop" not in r["runningCard"]["buttons"]
    assert "Stop" in r["runningBefore"], "running work has a Stop button of its own"
    assert r["queued"]["status"] == "stopped" and r["queued"]["stop_asked"] is True
    assert r["queuedCard"]["sentence"] == "Stopped. Anything already saved is kept."


# ------------------------------------------------------------------ files, copying, chat

def test_both_files_download_in_one_tap_and_a_draft_with_none_asks_for_them(run, pages):
    r = run("downloads", html=pages["sample"])
    _clean(r)
    assert [s["filename"] for s in r["saves"]] == ["Morgan_Ellis_CV_Ellerwick.pdf", "Morgan_Ellis_Cover_Letter_Ellerwick.pdf"]
    assert all(s["blob"] and s["size"] > 100 for s in r["saves"])
    assert any("Saved." in n for n in r["note"])
    # Said once for every draft, above them, with one button (4.3).
    assert r["filesLine"] and r["filesLine"][0].startswith("1 application's files are not on this page yet.")
    assert not any(b.startswith(("Download", "Get both")) for b in r["askButtons"])
    assert r["primary"] == ["Make it again"]
    assert r["work"]["kind"] == "files" and r["work"]["args"]["files"] == ["Morgan_Ellis_CV_Quayside.pdf"]


def test_a_declined_save_says_so_and_keeps_the_button(run, pages):
    r = run("downloads", html=pages["sample"], fake={"downloadError": "declined"})
    assert any("Not saved: you said no." in n for n in r["note"])


def test_copy_is_the_first_step_then_i_sent_it_and_it_falls_back_to_selecting(run, pages):
    ok = run("copy", html=pages["sample"])
    _clean(ok)
    assert ok["before"] == {"copy": True, "sent": False}, "Copy is the filled button until it is done"
    assert ok["clip"].startswith("Hi Juno, thank you for coming back to me")
    assert ok["label"] == ["Copied"] and ok["sentFilled"], "then I sent it is"
    no = run("copy", html=pages["sample"], denied=True)
    _clean(no)
    assert any("The text is selected" in n or "Press and hold" in n for n in no["note"]), no["note"]
    assert no["selected"].startswith("Hi Juno")


def test_chat_is_one_box_and_quick_answers_read_the_page(run, pages):
    r = run("talk", html=pages["sample"], shot="phone-talk" if SHOTS else "")
    _clean(r)
    assert r["label"] == "Ask Claude anything" and r["placeholder"] == "Ask anything, or paste a screenshot of a message you got"
    assert "What is due this week?" in r["examples"] and "Someone sent me a job" in r["examples"]
    assert r["quick"][-1].startswith("Two things are due today")
    assert r["tools"] and r["tools"][0][0] == "read_section" and "Reply to Juno" in r["tools"][0][1]
    call = r["sampleCall"][0]
    assert call["tier"] == "quick" and call["tools"] == ["read_section", "find", "needs_chat"]
    assert call["last"] == {"role": "user", "content": "What is due today?"}
    assert call["first"].startswith("You are the quick helper on Morgan's job search page.")
    assert r["busy"] == "false" and not r["status"]


def test_a_question_the_page_cannot_answer_goes_to_claude_by_itself(run, pages):
    r = run("talk", html=pages["sample"], question="Can you check the employer's website?",
            sample={"toolCalls": [{"name": "needs_chat", "input": {"reason": "It needs the employer's own website"}}],
                    "reply": "Your cloud chat can look that up."})
    _clean(r)
    assert any("Claude is working on this" in t and "It needs the employer" not in t for t in r["quick"]), "Claude's own reasoning is never shown"
    assert not any("Your cloud chat can look that up." in t for t in r["quick"])
    sent = [w for w in r["work"] if w["kind"] == "talk"]
    assert len(sent) == 1 and sent[0]["to"] == "cloud"
    assert r["rings"] and all(t.startswith("[app] [work:talk~cloud-1~") for t in r["rings"])


def test_with_no_quick_answers_a_question_goes_to_claude_and_the_answer_comes_back(run, pages):
    r = run("chat_cloud", html=pages["sample"])
    _clean(r)
    assert [d["from"] for d in r["docs"]] == ["you"]
    assert r["docs"][0]["text"] == "Can you look at the careers page for Harbourline Bank?"
    talk = [w for p, w in r["work"] if p.startswith("work/talk~cloud-1~")]
    assert len(talk) == 1 and talk[0]["kind"] == "talk" and talk[0]["to"] == "cloud"
    assert r["rings"] and all(t.startswith("[app] [work:talk~cloud-1~") for t in r["rings"])
    assert not any("Harbourline" in t for t in r["rings"]), "the ring carries no words of the person's"
    assert r["waiting"]
    assert any("closes on 31 October" in t for t in r["shown"])
    assert "Claude" in "".join(r["who"]) and "Cloud" not in "".join(r["who"])


def test_work_goes_to_the_chat_that_answers_the_page_with_nothing_to_choose(run, pages):
    r = run("chat_computer", html=pages["sample"])
    _clean(r)
    # The maintainer, 2026-10-29: "even i dont know what changing these settings does".
    assert "Where long tasks run" not in r["legend"]
    assert not any("work_either" in k for k in r["settingKeys"])
    assert len(r["work"]) == 1 and r["work"][0]["to"] == "computer"
    assert any("This needs your computer: open Claude on it." in t for t in r["waiting"])
    on = run("chat_computer", html=pages["sample"], listening=True)
    _clean(on)
    assert not any("open Claude on it" in t for t in on["waiting"]) and on["rings"] >= 1


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_chat_opens_from_any_section_in_a_panel_with_the_same_thread(run, pages, vp):
    """The person, 2026-10-26: a window for chatting bottom right, "the exact same chat as in
    the window", so a question on any page needs no trip to Chat first."""
    r = run("chat_dock", html=pages["sample"], viewport=vp)
    _clean(r)
    if vp is PHONE:
        # One way into the chat on a phone, its tab: no floating button and no panel over it
        # (the maintainer, 2026-10-28).
        assert not r["fab"] and not r["dockBefore"]
        assert r["phone"]["hash"] == "#chat" and not r["phone"]["dock"]
        assert r["phone"]["value"] == "Help me reply to this message: " and r["phone"]["focus"] == "talk-text"
        return
    assert r["fab"] and r["fabName"] == "Chat with Claude" and not r["dockBefore"]
    o = r["open"]
    assert o["dock"] and not o["fab"] and o["role"] == "dialog" and o["name"] == "Chat"
    assert o["focus"] == "talk-text" and o["box"], "focus moves into the panel's box"
    assert o["msgs"][:2] == ["Is Harbourline Bank hiring analysts?", "Yes: two analyst roles opened there this week."]
    g = r["geo"]
    assert g["left"] >= 0 and g["right"] <= g["vw"] and g["top"] >= 0 and g["bottom"] <= g["vh"]
    if vp is PHONE:
        assert g["tabsTop"] is not None and g["bottom"] <= g["tabsTop"] + 1, "the tab bar stays uncovered"
        assert g["left"] == 0 and g["right"] == g["vw"], "a full-width sheet on a phone"
    else:
        assert g["right"] < g["vw"] and g["bottom"] < g["vh"], "a panel bottom right"
    assert not r["a11y"]["problems"] and r["a11y"]["checked"] > 0, r["a11y"]
    mine = [d for d in r["docs"] if d["from"] == "you" and d["text"] == "Can you check their careers page?"]
    assert len(mine) == 1 and mine[0]["work"].startswith("talk~cloud-1~"), "the panel sends as the Chat page sends"
    assert len(r["work"]) == 1 and r["work"][0]["to"] == "cloud"
    assert "Can you check their careers page?" in r["sent"]
    assert r["moved"]["dock"], "data arriving and another section leave it open"
    assert "Their careers page lists a Pricing Analyst role." in r["moved"]["msgs"]
    assert r["esc"] == {"dock": False, "fab": True, "focus": "chat-fab"}, r["esc"]
    assert r["got"]["label"] == "Got a message? Paste it or a screenshot"
    assert r["got"]["dock"] and r["got"]["focus"] == "talk-text" and r["got"]["value"] == "Help me reply to this message: "
    assert r["got"]["back"] == "got-msg", "Escape gives focus back to what opened it"
    c = r["chat"]
    assert c["hash"] == "#chat" and not c["dock"] and not c["fab"], c
    assert c["msgs"][:2] == o["msgs"][:2] and "Their careers page lists a Pricing Analyst role." in c["msgs"], "the same thread"
    assert c["focus"] == "talk-text" and c["value"] == "Help me reply to this message: ", "the same box and its words"


# The one-pixel PNG the harness pastes (tests/app_page/harness.js, PNG).
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_a_pasted_screenshot_goes_with_the_message_as_its_id(run, pages):
    r = run("chat_pics", html=pages["sample"])
    _clean(r)
    assert r["add"] and r["placeholder"] == "Ask anything, or paste a screenshot of a message you got"
    assert r["intro"].startswith("Paste a screenshot or a link and say what you want: reply to someone, add a job someone sent you")
    # Three to do things, and one for help with the page itself (2026-10-28).
    assert r["starters"][0] == "Someone sent me a job" and len(r["starters"]) == 4, r["starters"]
    assert r["starters"][3] == "How does this page work?"
    assert [t["img"] for t in r["tray"]] == [True] and r["tray"][0]["loaded"], "the screenshot shows in the box"
    assert r["tray"][0]["state"].endswith("Ready to send") and r["tray"][0]["remove"] == "Remove"
    assert [(u["name"], u["type"]) for u in r["uploaded"]] == [("screenshot.png", "image/png")]
    assert r["typed"] == "", "a pasted picture is not pasted as words"
    assert r["note"] == "That kind of picture cannot be added. A PNG or JPEG screenshot works." and r["trayCount"] == 1
    sent = [d for d in r["docs"] if d.get("images")]
    assert len(sent) == 1 and sent[0]["text"] == "Help me reply to this"
    assert sent[0]["images"] == [{"id": r["uploaded"][0]["id"], "type": "image/png", "name": "screenshot.png", "bytes": len(PNG)}]
    assert len(r["work"]) == 1 and r["work"][0]["kind"] == "talk", "a picture always goes to a chat, which can read it"
    assert r["thread"] == [{"tag": "IMG", "alt": "Your picture"}] and "Help me reply to this" in r["texts"]
    assert r["trayAfter"] == 0


def test_the_panel_takes_a_screenshot_too(run, pages):
    r = run("chat_pics", html=pages["sample"], hash="contacts", viewport=WIDE)
    _clean(r)
    assert r["add"] and [t["img"] for t in r["tray"]] == [True]
    assert any(d.get("images") for d in r["docs"]) and r["thread"] == [{"tag": "IMG", "alt": "Your picture"}]


def test_with_no_file_store_there_is_no_picture_button_and_no_promise_of_one(run, pages):
    r = run("chat_pics", html=pages["sample"], noAssets=True)
    _clean(r)
    assert not r["add"]
    assert r["placeholder"] == "Ask anything, or paste a message you got"
    assert "screenshot" not in r["intro"] and r["intro"].startswith("Paste a message or a link")


def test_practice_questions_run_on_the_page_as_an_interviewer(run, pages):
    r = run("mock", html=pages["sample"])
    _clean(r)
    assert r["heading"] == "Chat"
    assert r["msgs"][-1].startswith("First question")
    assert r["first"][0].startswith("You are a friendly, realistic interviewer for the role of Senior Supply Chain Analyst at Larkspur Retail")


# ------------------------------------------------------------------ layout, keyboard, history, time

@pytest.mark.parametrize("width", [320, 375, 1024, 1440])
def test_no_width_scrolls_sideways_and_each_has_its_navigation(run, pages, width):
    r = run("paint", html=pages["sample"], viewport={"width": width, "height": 800}, hash="jobs")
    _clean(r)
    assert r["overflow"]["sw"] <= r["overflow"]["cw"], r["overflow"]
    if width < 760:
        assert r["tabs"] and not r["side"] and not r["rail"]
    elif width < 1280:
        assert r["side"] and not r["tabs"] and not r["rail"]
    else:
        assert r["side"] and r["rail"] and not r["tabs"]


def test_keyboard_alone_reaches_and_works_everything_and_the_shortcuts_can_be_switched_off(run, pages):
    r = run("keyboard", html=pages["sample"])
    _clean(r)
    assert r["first"] == "Skip to the main content"
    assert r["afterSkip"] == "main"
    assert r["draftsFocus"] == "Contacts", "a section opened by keyboard puts focus on its heading"
    assert r["reachedDraft"]
    assert r["visibleFocus"] not in ("none", "")
    assert r["dialog"] and r["dialogGone"]
    assert r["backOn"] == "Draft this: Harbourline Bank, Pricing Analyst"
    assert r["help"] == "Keyboard shortcuts"
    assert r["afterGT"] == "To do" and r["afterGJ"] == "Jobs"
    assert r["cardFocus"] == "r12-1", "j moves to the first card: the best match by its number (4.3)"
    assert r["moreClosed"], "Esc closes a card's More"
    assert r["typed"] == ["gj", "Chat"], "typing in a box is never a shortcut"
    assert r["offStays"] == "Settings" and r["stored"] == "off"


def test_back_goes_back_inside_the_page_and_an_item_has_its_own_address(run, pages):
    r = run("history", html=pages["sample"])
    _clean(r)
    assert r["afterBack"] == "Jobs" and r["hash"] == "#jobs"
    assert r["item"] == {"focus": "copperleaf_pay_tamsin", "heading": "Contacts"}


def test_times_are_the_persons_own_with_the_zone_named_and_a_date_is_a_day(run, pages):
    away = run("zones", html=pages["sample"])
    _clean(away)
    assert any("London time" in w and "here" in w for w in away["whens"]), away["whens"]
    assert any("time not set" in w for w in away["whens"]), "a date with no time is a calendar day"
    home = run("zones", html=pages["sample"], timezoneId="Europe/London")
    assert not any("London time" in w for w in home["whens"])
    assert not any("Passed" in c for c in home["chips"])


def test_no_side_by_side_menu_and_a_second_column_closes_plainly(run, pages):
    r = run("split", html=pages["sample"], shot="wide-split" if SHOTS else "")
    _clean(r)
    assert r["menu"] == 0, "no Side by side menu"
    assert r["cols"] == 2 and r["headings"][:2] == ["Jobs", "Contacts"] and r["hash"] == "#jobs+contacts"
    assert r["after"] == 0, "Close the second column closes it"


def test_reduced_motion_stops_the_spinner_and_the_bar(run, pages):
    r = run("motion", html=pages["sample"])
    assert r["no-preference"]["spin"] == "turn"
    assert r["reduce"]["spin"] == "none"
    assert r["reduce"]["fill"] in ("0s", "0s, 0s")


def test_dark_mode_follows_the_viewer_and_the_hosts_choice_wins_both_ways(run, pages):
    r = run("theme", html=pages["sample"])
    assert r["light"]["bg"] == _rgb("light") and r["light"]["scheme"] in ("light", "light dark")
    assert r["dark"]["bg"] == _rgb("dark") and r["dark"]["scheme"] == "dark"
    assert r["light_flipped"] == _rgb("dark")
    assert r["dark_flipped"] == _rgb("light")


# ------------------------------------------------------------------ dawn and main, every section, phone and wide

THEME_MATRIX = [(look, w) for look in ("light", "dark") for w in ("phone", "wide")]


@pytest.mark.parametrize("look,width", THEME_MATRIX)
def test_every_section_in_both_looks_passes_contrast_layout_and_targets(run, pages, look, width):
    r = run("a11y", html=pages["sample"], viewport=PHONE if width == "phone" else WIDE, targets=width == "phone", look={"look": look})
    _clean(r)
    assert r["applied"]["bg"] == _rgb(look), r["applied"]
    assert r["applied"]["scheme"] == look
    bad = {k: r[k]["problems"] for k in list(LABELS) + ["work", "dialog"] if r[k]["problems"]}
    assert bad == {}
    assert all(r[k]["checked"] > 0 for k in LABELS)
    assert {k: v for k, v in r["overflow"].items() if v["sw"] > v["cw"]} == {}
    assert {k: v for k, v in r["targets"].items() if v} == {}, "a control under 44px on a phone"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_following_the_device_every_control_has_a_name_and_all_text_has_contrast(run, pages, scheme):
    r = run("a11y", html=pages["sample"], scheme=scheme, viewport=PHONE)
    _clean(r)
    assert r["applied"]["bg"] == _rgb(scheme)
    bad = {k: r[k]["problems"] for k in list(LABELS) + ["work", "dialog"] if r[k]["problems"]}
    assert bad == {}


def test_the_hosts_own_appearance_wins_over_the_device_and_the_persons_choice_wins_over_both(run, pages):
    host_dark = run("a11y", html=pages["sample"], viewport=PHONE, hostTheme="dark", scheme="light")
    _clean(host_dark)
    assert host_dark["applied"]["bg"] == _rgb("dark")
    assert {k: host_dark[k]["problems"] for k in list(LABELS) + ["work", "dialog"] if host_dark[k]["problems"]} == {}
    host_light = run("paint", html=pages["sample"], scheme="dark", fake={}, hostTheme="light")
    assert host_light["bg"] == _rgb("light")
    chosen = run("paint", html=pages["sample"], scheme="light", hostTheme="dark", look={"look": "light"})
    assert chosen["bg"] == _rgb("light"), "the person's Light on this page wins over the app's Dark"


def test_light_or_dark_is_chosen_in_settings_kept_for_this_viewer_and_followed_by_other_windows(run, pages):
    r = run("picker", html=pages["sample"])
    _clean(r)
    assert r["before"] == _rgb("light")
    # The look, then this device's size (2026-10-29).
    assert r["legends"] == ["Look", "Size"] and r["choices"] == ["Auto", "Light", "Dark", "Smaller", "Standard", "Larger"]
    assert r["after"] == {"bg": _rgb("dark"), "look": "dark", "stored": "dark", "scheme": "dark"}
    assert r["actions"] == [], "a look is the viewer's own: nothing is asked of a chat"
    assert r["otherWindow"]["bg"] == _rgb("dark") and "dark" in r["otherWindow"]["checked"]
    assert r["reloaded"]["bg"] == _rgb("dark") and "dark" in r["reloaded"]["checked"]
    assert r["back"] == {"bg": _rgb("light"), "look": None, "stored": None}


def test_the_chosen_look_is_set_before_the_first_paint(run, pages):
    r = run("first_paint_look", html=pages["sample"])
    _clean(r)
    assert r["look"] == "dark" and r["bg"] == _rgb("dark")
    order = r["paint"]
    # Nothing exists to paint, not even a stylesheet, until the chosen look is on the root.
    assert "attr" in order and "style" in order and "content" in order, order
    assert order["attr"] < order["style"] < order["content"], order


def test_with_storage_refused_the_page_follows_the_device_and_still_switches(run, pages):
    r = run("no_storage", html=pages["sample"])
    _clean(r)
    assert r["heading"] == "Settings"
    assert r["bg"] == _rgb("dark"), "a dark device, nothing stored: main"
    assert r["after"] == _rgb("light")


# ------------------------------------------------------------------ the phone, by the stylesheet alone

def test_the_phone_and_wide_layouts_come_from_the_stylesheet_with_no_script(run, pages):
    r = run("no_js_layout", html=pages["sample"])
    phone, wide = r["phone"], r["wide"]
    assert phone["shellHidden"], "with no script nothing of the person's shows"
    assert phone["opening"] == "none", "and the page does not pretend to be opening"
    assert phone["side"]["display"] == "none" and phone["rail"]["display"] == "none"
    assert phone["tabs"]["position"] == "fixed" and phone["tabs"]["display"] != "none"
    assert phone["cols"] == 1 and phone["sw"] <= phone["cw"]
    assert wide["side"]["display"] == "flex" and wide["rail"]["display"] == "block" and wide["tabs"]["display"] == "none"
    assert wide["cols"] == 3
    assert phone["noscript"], "with no script the page says it needs one"


def test_a_phones_safe_areas_are_kept_clear(run, pages):
    r = run("safe_area", html=pages["sample"])
    p, land = r["portrait"], r["landscape"]
    _clean(p)
    _clean(land)
    assert p["rootPadTop"] == 47 or p["topTop"] == "47px", "content starts below the status bar"
    assert p["tabsPadBottom"] == 34 and p["tabsBottom"] == p["vh"], "the bottom bar sits on the edge, clear of the home indicator"
    assert p["shellPadBottom"] >= p["tabsHeight"], "the last thing on the page scrolls clear of the bottom bar"
    assert p["topTop"] == "47px", "the header, with running work, pins below the status bar"
    assert land["bodyLeft"] == 47 and land["bodyRight"] == 47, "the side gutter clears a notch in landscape"
    assert p["sw"] <= p["cw"] and land["sw"] <= land["cw"]


def test_windows_high_contrast_keeps_buttons_focus_and_progress_visible(run, pages):
    r = run("forced", html=pages["sample"])
    _clean(r)
    assert r["button"]["border"].startswith("solid") and r["quiet"]["border"].startswith("solid")
    assert r["bar"]["border"].startswith("solid")
    assert r["fill"]["bg"] not in ("rgba(0, 0, 0, 0)", "transparent") and r["fillWidth"] > 0
    assert r["focus"]["outline"] == "solid"


def test_more_contrast_turns_secondary_text_to_the_body_ink(run, pages):
    r = run("more_contrast", html=pages["sample"])
    assert r["no-preference"]["lede"] != r["no-preference"]["ink"]
    assert r["more"]["lede"] == r["more"]["ink"]


def test_what_was_opened_selected_and_typed_outlives_live_updates_and_a_reload(run, pages):
    r = run("persist", html=pages["sample"])
    _clean(r)
    assert r["stillOpen"] is True and "Finding jobs" in r["pill"]
    assert r["selection"] > 100, "a live update never wipes a selection"
    assert r["afterReload"] == "Half a thought about Harbourline"
    assert r["otherTab"] == "", "a draft belongs to the window it was typed in"


def test_the_accessibility_sweep_finds_what_it_is_meant_to(run, pages):
    r = run("a11y_selftest", html=pages["sample"])
    found = " | ".join(r["problems"])
    assert "no name: button" in found and "contrast" in found and "duplicate id: brand" in found


# ------------------------------------------------------------------ what a person meets on a screen

BUDGET = {"chrome": 12, "filled": 1, "card_controls": 4, "card_words": 30}


@pytest.mark.parametrize("viewport,scheme", [(PHONE, "light"), (WIDE, "dark")])
def test_every_screen_keeps_to_the_simplicity_budgets(run, pages, viewport, scheme):
    r = run("budget", html=pages["sample"], viewport=viewport, scheme=scheme)
    _clean(r)
    for sid in LABELS:
        got = r[sid]
        assert got["chrome"] <= BUDGET["chrome"], (sid, "words of header and footer", got["chrome"])
        assert got["filled"] <= BUDGET["filled"], (sid, "filled buttons in view", got["filled"])
        for c in got["cards"]:
            # An icon tool on the card's row (Tweak's pencil, a job's bin: the maintainer,
            # 2026-10-26) is not one of its actions, as an answer is not, nor its "?" (the
            # maintainer, 2026-10-29: "just explainers or ?"), nor a person's name that opens them (the maintainer, 2026-10-29: "why cant i click
            # his name").
            others = c["controls"] - c["answers"] - c.get("icons", 0) - c.get("names", 0)
            if not c["alerts"]:
                assert others <= BUDGET["card_controls"], (sid, c)
            assert c["filled"] <= 1, (sid, c)
        quiet = sorted(c["words"] for c in got["cards"] if not c["alerts"])
        if quiet:
            assert quiet[len(quiet) // 2] <= BUDGET["card_words"], (sid, "words on a typical closed card", quiet)


def test_screenshots_of_to_do_jobs_and_drafts_light_and_dark_phone_and_wide(run, pages):
    if not SHOTS:
        pytest.skip("set LJS_SHOTS to a folder to write the screenshots")
    shots = []
    for look in ("light", "dark"):
        for width, vp in (("phone", PHONE), ("wide", WIDE)):
            for sec in ("todo", "jobs", "drafts"):
                shots.append({"name": f"{sec}-{look}-{width}", "dir": "after", "viewport": vp, "hash": sec, "look": {"look": look}})
    files = run("shots", html=pages["sample"], list=shots)
    assert len(files) == 12 and all(os.path.isfile(f) for f in files)


def test_screenshots_for_a_person_to_judge(run, pages):
    if not SHOTS:
        pytest.skip("set LJS_SHOTS to a folder to write the screenshots")
    files = run("shots", html=pages["sample"], list=[
        {"name": "phone-messages", "viewport": PHONE, "hash": "drafts-messages"},
        {"name": "phone-contacts", "viewport": PHONE, "hash": "contacts"},
        {"name": "phone-interviews", "viewport": PHONE, "hash": "interviews"},
        {"name": "phone-progress", "viewport": PHONE, "hash": "progress", "full": True},
        {"name": "phone-chat", "viewport": PHONE, "hash": "chat"},
        {"name": "phone-settings", "viewport": PHONE, "hash": "settings", "full": True},
        {"name": "phone-work-sheet", "viewport": PHONE, "hash": "work"},
        {"name": "phone-job-more", "viewport": PHONE, "hash": "jobs", "more": "r12-1"},
        {"name": "phone-dark-todo-full", "viewport": PHONE, "hash": "todo", "look": {"look": "dark"}, "full": True},
        {"name": "phone-320-todo", "viewport": {"width": 320, "height": 700}, "hash": "todo"},
        {"name": "wide-split", "viewport": WIDE, "hash": "jobs+contacts"},
        {"name": "wide-dark-chat", "viewport": WIDE, "hash": "chat", "look": {"look": "dark"}},
    ])
    first = run("shots", html=pages["empty"], list=[{"name": "phone-first-run", "viewport": PHONE, "hash": "todo", "seed": False}])
    assert all(os.path.isfile(f) for f in files + first)


# ------------------------------------------------------------------ a busy week, calmly (2026-10-26)

def test_a_busy_week_is_a_few_checklists_not_a_card_each(run, pages):
    r = run("busy", html=pages["busy"])
    _clean(r)
    follow = r["groups"]["grp:follow:now"]
    assert follow["title"] == "Follow up with 3 people" and len(follow["rows"]) == 3, follow
    assert all(row["buttons"][:1] == ["Draft"] for row in follow["rows"]), follow
    assert "Draft all 3" in follow["actions"], "one button drafts them all"
    sent = r["groups"]["grp:sent"]
    assert sent["title"].startswith("Did these notes go?") and len(sent["rows"]) == 2 and "They all went" in sent["actions"]
    warn = [g for k, g in r["groups"].items() if k.startswith("grp:read_first")]
    assert len(warn) == 1 and warn[0]["title"].startswith("Written before their profile was read"), r["groups"]
    assert "4 follow-ups at employers you turned down not shown." in r["hidden"]
    assert "Nudge" not in r["text"], "a follow-up is called a follow-up"
    assert "Turn on the new reading pace?" not in r["text"], "questions from updates wait in Settings"
    assert "Turn on the new reading pace?" in r["settings"]
    # Drafts are inside Jobs (4.3): the quiet counts are on Jobs and Interviews.
    assert r["counts"].get("jobs") and r["counts"].get("interviews"), r["counts"]
    assert r["progress"]["recent"].startswith("In the last 30 days: 1 applied, 2 replies")
    assert r["progress"]["all"].startswith("Since you started:")
    assert r["bin"]["title"] == "Not for you?" and "No more roles from Harbourline Bank" in r["bin"]["options"]
    assert r["gauge"] >= 1, "a cost is a gauge of bars, its words on hover"


# ------------------------------------------------------------------ waking Claude, by itself (2026-10-28)

def test_the_page_wakes_its_helper_chat_by_itself_and_never_starts_a_chat(run, pages):
    r = run("wake", html=pages["sample"])
    _clean(r)
    sent = [c for c in r["mcp"] if c["tool"] == "send_message"]
    assert sent and sent[0]["server"] == "Claude Code Remote" and sent[0]["input"]["session_id"] == "session_EXAMPLEHELPER"
    assert "[app] [work:draft~r12-1]" in sent[0]["input"]["message"]
    assert r["wakeCard"] == 0, "no Wake Claude card while the page can wake it"
    # The helper cannot be reached: the page starts no chat of its own (2026-10-29: a new
    # chat per task was the complaint, and starting chats was blocked for some accounts).
    gone = run("wake", html=pages["sample"], fail=["send_message"])
    _clean(gone)
    assert {c["tool"] for c in gone["mcp"]} == {"send_message"}
    assert gone["wakeCard"] == 1, "the one card that says Claude is not listening, with its way to wake it"


# ------------------------------------------------------------------ your profile (2026-10-28)

def test_the_profile_is_filled_in_and_changed_on_the_page_one_work_item_each(run, pages):
    r = run("you", html=pages["sample"])
    _clean(r)
    assert r["card"] == ["Finish your profile"]
    assert r["sheet"] == ["What you did at Saltmarsh Analytics"]
    got = {(w["args"]["part"], w["args"]["change"]): w["args"] for w in r["works"]}
    assert got[("job", "edit")]["text"] == "Built the weekly stock report for 40 stores."
    assert got[("job", "edit")]["was"]["employer"] == "Saltmarsh Analytics"
    # SQL is already on the profile, so only Looker is added.
    assert got[("skills", "edit")]["add"] == ["Looker"] and got[("skills", "edit")]["remove"] == ["Power BI"]
    assert got[("job", "remove")]["was"]["title"] == "Graduate Analyst"
    assert len(r["works"]) == 3


def test_the_tour_walks_each_section_skips_and_opens_one_part_from_its_title(run, pages):
    r = run("tour", html=pages["sample"])
    _clean(r)
    assert r["card"] == ["New here? A one-minute tour"]
    assert r["first"] == ["Brief (1 of 7)"]
    assert r["second"]["title"] == ["To do (2 of 7)"] and r["second"]["hash"] == "#todo", "each step opens its section"
    assert r["closed"] == 0 and r["cardAfter"] == 0, "skipped, and never offered again on this device"
    assert r["part"]["title"] == ["How Contacts works"]
    assert "Next part: Interviews" in r["part"]["buttons"] and "Close" in r["part"]["buttons"]
