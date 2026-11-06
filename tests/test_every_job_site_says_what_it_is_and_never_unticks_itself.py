"""Settings, Job sites: every site by its plain name, with a line saying what it is; a site that
needs a key says "Needs a free key" with the steps to get one; no tick flips back unsaid.

The maintainer, 2026-11-06: "Adzuna (listed as 'api.adzuna.com') looks ticked and then unticks
itself after I leave, because it needs a key. A site that needs a key says 'Needs a free key'
with the steps to get one; no tick on the page ever flips back without saying why; every site
has a plain name and a one-line note."

Every board, address and employer here is invented, Adzuna's name aside.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
import app_state  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample  # noqa: E402

CLOCK = "2026-10-25T09:30:00Z"


def _skill(root, name, front, heading="", src=None):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    lines = "\n".join(f"{k}: {v}" for k, v in front.items())
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(f"---\nname: {name}\n{lines}\n---\n\n{heading}\n")
    for f, text in (src or {}).items():
        os.makedirs(os.path.join(d, "cli", "src"), exist_ok=True)
        with open(os.path.join(d, "cli", "src", f), "w", encoding="utf-8") as fh:
            fh.write(text)


# A portal /add-portal built before a site's key had a line of its own: its CLI names the key.
ADZUNA_CLI = """
const id = process.env.ADZUNA_APP_ID;
const key = process.env["ADZUNA_APP_KEY"];
const proxy = process.env.HTTPS_PROXY;
if (!id || !key) { console.error(JSON.stringify({error: "set ADZUNA_APP_ID and ADZUNA_APP_KEY", code: "MISSING_CREDENTIALS"})); process.exit(1); }
"""


@pytest.fixture
def sites(tmp_path, monkeypatch):
    root = str(tmp_path / "skills")
    _skill(root, "linkedin-search", {"enabled": "true"}, "# LinkedIn Search Skill")
    _skill(root, "freehire-search", {"enabled": "true"}, "# freehire Search Skill")
    _skill(root, "adzuna-search", {"enabled": "true", "contract": "1", "url": "https://api.adzuna.com/v1/api/jobs"},
           "# Adzuna Search Skill", {"cli.ts": ADZUNA_CLI})
    _skill(root, "cityboard-search", {"enabled": "true", "contract": "1", "url": "https://www.cityboard-example.test"},
           "# City Board Job Search")
    _skill(root, "harbourjobs-search", {"enabled": "false", "url": "https://api.harbourjobs-example.test",
                                        "label": "Harbour Jobs", "note": "Jobs on the coast, posted by employers.",
                                        "key-env": "HARBOURJOBS_API_TOKEN", "key-url": "https://harbourjobs-example.test/keys",
                                        "key-free": "true"})
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    state = app_state.small(str(tmp_path / "state"))
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", state)
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "HARBOURJOBS_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    import portals
    monkeypatch.setattr(portals, "SKILLS", root)
    return root


def _model_sites():
    import app_model
    targets: dict = {}
    s = app_model._search(types.SimpleNamespace(seen={}, today=dt.date(2026, 10, 25)), targets)
    return {p["name"]: p for p in s["portals"]}, targets


# ------------------------------------------------------------------ the model: names, notes, keys

def test_every_site_has_a_plain_name_and_a_one_line_note(sites):
    got, targets = _model_sites()
    assert set(got) == {"linkedin-search", "freehire-search", "adzuna-search", "cityboard-search", "harbourjobs-search"}
    names = {k: p["label"] for k, p in got.items()}
    assert names == {"linkedin-search": "LinkedIn", "freehire-search": "Freehire", "adzuna-search": "Adzuna",
                     "cityboard-search": "City Board", "harbourjobs-search": "Harbour Jobs"}, names
    for name, p in got.items():
        label = p["label"]
        # Never an address ("api.adzuna.com") nor a folder ("adzuna-search").
        assert "." not in label and "/" not in label and not label.endswith("-search") and label[:1].isupper(), label
        assert p["note"].strip() and "\n" not in p["note"] and len(p["note"]) <= 120, p
        assert "robots" not in p["note"].lower() and "crawler" not in p["note"].lower()
        # Each site is its own item, so a tap on one is never stale because another changed.
        assert targets[p["id"]] == {"kind": "search", "site": name, "rev": p["rev"]}
    assert got["adzuna-search"]["note"].startswith("Jobs gathered from many sites")
    assert got["harbourjobs-search"]["note"] == "Jobs on the coast, posted by employers."


def test_a_site_with_no_key_says_needs_a_free_key_with_numbered_steps(sites, monkeypatch):
    got, _ = _model_sites()
    adz = got["adzuna-search"]["key"]
    assert adz and adz["free"] is True, got["adzuna-search"]
    steps = adz["steps"]
    assert steps[0].startswith("Open developer.adzuna.com/signup") and "Personal job search" in " ".join(steps)
    # One action a line, plain words, ending with how the key reaches the app: in a chat.
    assert all(s.strip() and "\n" not in s and len(s) < 200 for s in steps)
    assert steps[-1].startswith("In a chat with Claude, say \"I have my Adzuna key\"")
    for word in ("environment", "variable", "export", "API_", "repository", "config"):
        assert word not in " ".join(steps), word
    own = got["harbourjobs-search"]["key"]
    assert own["free"] is True and own["steps"][0] == "Open harbourjobs-example.test/keys and sign up for a free key."
    for name in ("linkedin-search", "freehire-search", "cityboard-search"):
        assert got[name]["key"] is None, name
    # With the key on this computer, the site is an ordinary tick again.
    monkeypatch.setenv("ADZUNA_APP_ID", "an-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "a-key")
    got, _ = _model_sites()
    assert got["adzuna-search"]["key"] is None and got["harbourjobs-search"]["key"]


def test_turning_on_a_site_with_no_key_is_refused_in_plain_words(sites):
    import app_actions
    act = {"action": "search.set", "item": "site-adzuna", "at": "2026-10-25T09:00:00Z",
           "value": {"what": "sites", "name": "adzuna-search", "on": True}}
    run = app_actions.Run("a1", act, {"kind": "search", "site": "adzuna-search"}, {}, None, "cloud-1",
                          "Europe/London", dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc))
    with pytest.raises(app_actions.Refused) as e:
        app_actions._search_set(run)
    assert str(e.value) == "Adzuna needs a free key before it can be searched. Open it for the steps to get one."


def test_a_tap_on_one_site_is_never_refused_because_another_changed(tmp_path):
    search = Search(str(tmp_path))
    first = {p["id"]: p for p in search.model()["search"]["portals"]}
    assert {"site-freehire", "site-linkedin"} <= set(first)
    off = search.act("search.set", "site-freehire", rev=first["site-freehire"]["rev"],
                     value={"what": "sites", "name": "freehire-search", "on": False})
    got = search.apply(); assert got["ok"] == [off], (got, search.receipt(off))
    search.written_back()
    # Tapped on the page as it was before the first was applied: its own rev has not moved.
    on = search.act("search.set", "site-linkedin", rev=first["site-linkedin"]["rev"],
                    value={"what": "sites", "name": "linkedin-search", "on": True})
    assert search.apply()["ok"] == [on], search.receipt(on)
    now = {p["name"]: p["on"] for p in search.model()["search"]["portals"]}
    assert now["freehire-search"] is False and now["linkedin-search"] is True


# ------------------------------------------------------------------ the page

@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


STEPS = ["Open developer.adzuna.com/signup.", "Fill in a username, your email and a password.",
         "In a chat with Claude, say \"I have my Adzuna key\". Claude shows you the safe place for it, and the site is searched from then on."]


def _model():
    m = _sample()
    m["search"] = dict(m["search"], portals=[
        {"id": "site-adzuna", "name": "adzuna-search", "label": "Adzuna", "note": "Jobs gathered from many sites in the UK and over a dozen other countries.",
         "on": True, "key": {"free": True, "steps": STEPS}, "rev": "rs-adz"},
        {"id": "site-freehire", "name": "freehire-search", "label": "Freehire", "note": "A free board that gathers jobs from many sites.",
         "on": True, "key": None, "rev": "rs-fh"},
        {"id": "site-linkedin", "name": "linkedin-search", "label": "LinkedIn", "note": "LinkedIn's own job search, in every country.",
         "on": True, "key": None, "rev": "rs-li"}])
    return m


def _go(run, tmp_path, steps, vp):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(_model())))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={}, fake={"canSend": "available"}, clock=CLOCK)
    assert not got["errors"], got["errors"]
    return got


ROW = '[data-k="det:info:search-portals"]'
CHECKED = "document.getElementById('portal-freehire-search').checked"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_site_needing_a_key_shows_its_steps_and_has_no_tick(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:search-portals", "read": ROW,
         "count": ROW + ' [data-item="site-adzuna"] input[type="checkbox"]'},
        {"open": "site-key-sum:portal-adzuna-search", "read": '[data-item="site-adzuna"]',
         "count": '[data-k="site-steps:portal-adzuna-search"] > li'},
    ], vp)
    row = got["after"][0]
    assert row["count"] == 0, "no box that could be ticked"
    assert "Job sites" in row["text"] and "2 searched" in row["text"], row["text"]
    for words in ("Adzuna", "Needs a free key", "Jobs gathered from many sites", "Freehire", "A free board", "LinkedIn"):
        assert words in row["text"], (words, row["text"])
    assert "api.adzuna.com" not in row["text"] and "adzuna-search" not in row["text"]
    opened = got["after"][1]
    assert opened["count"] == len(STEPS) and "To get one:" in opened["text"] and "I have my Adzuna key" in opened["text"], opened


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_refused_tick_says_why_where_it_was_and_shows_the_true_state(run, tmp_path, vp):
    why = "Freehire could not be changed: the search is running. Try again once it has finished."
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:search-portals", "eval": CHECKED},
        {"click": "Freehire", "role": "switch", "eval": CHECKED},
        {"receipts": True, "refuse": why},
        # A few seconds on, as a refusal arrives: the page holds a live redraw for a moment
        # after a control was used.
        {"tick": 3000, "read": '[data-item="site-freehire"]', "eval": CHECKED},
    ], vp)
    assert got["after"][0]["eval"] is True
    assert got["after"][1]["eval"] is False, "the tap shows while it is on its way"
    (tap,) = [a for a in got["actions"] if a["action"] == "search.set"]
    assert tap["item"] == "site-freehire" and tap["rev_seen"] == "rs-fh", tap
    assert tap["value"] == {"what": "sites", "name": "freehire-search", "on": False}, tap
    after = got["after"][3]
    assert after["eval"] is True, ("refused, the tick is back as the engine holds it", after["text"])
    assert "Not done: " + why in after["text"], after["text"]
