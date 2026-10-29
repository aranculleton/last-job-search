"""Networking reads LinkedIn through the page itself, in the Claude desktop app's browser.

Before 4.3 the page asked the desktop browser for each tool's inputs, which it never gives
(describeTool rejects for every host: server, mcp.d.ts), so it sent navigate with no address
and read a blank tab, and the fake answered anything, so every test passed (2026-10-29).
Now the fake keeps the contract, and the page checks by itself when it opens in the app.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    return _write(tmp_path_factory.mktemp("reading"), "sample", _sample())


def test_opened_in_the_app_and_signed_in_it_checks_by_itself_with_an_address(run, page):
    r = run("reading", html=page, signedIn=True)
    assert not r["errors"], r["errors"]
    tools = [c["tool"] for c in r["browser"]]
    assert tools[:2] == ["navigate", "get_page_text"], tools
    assert r["browser"][0]["input"].get("url", "").startswith("https://www.linkedin.com/")
    assert r["state"]["ok"] is True and not r["state"]["panel"]


def test_signed_out_it_says_how_to_sign_in(run, page):
    r = run("reading", html=page, signedIn=False)
    assert r["state"]["signedOut"] is True and r["state"]["panel"] == "sign_in"
    assert "sign in" in r["panel"].lower()


def test_outside_the_app_it_never_touches_the_browser(run, page):
    r = run("reading", html=page, inApp=False)
    assert r["browser"] == [] and not r["errors"]


def test_the_first_call_waits_for_the_allow_prompt_and_tries_once_more(run, page):
    """Live, the first call came back retryable while the app's allow prompt was open."""
    r = run("reading", html=page, signedIn=True, askFirst=True)
    assert [c["tool"] for c in r["browser"]][:3] == ["navigate", "navigate", "get_page_text"]
    assert r["state"]["ok"] is True



@pytest.fixture(scope="module")
def queued(tmp_path_factory):
    """Reading already works and networking has queued three profiles, their addresses on file."""
    m = _sample()
    li = m.setdefault("linkedin", {})
    li["reading"] = {"id": "linkedin-reader", "page_reads": True, "ok": True, "checked_at": "2026-10-24T09:00:00Z",
                     "last_read_at": None, "reads": 0, "rev": "r0",
                     "queue": [{"id": f"read-c{n}", "contact": f"c{n}", "first_name": name, "employer": "Example Co",
                                "mode": "deep", "asked_on": "2026-10-25", "reach": f"reach/c{n}", "rev": f"q{n}"}
                               for n, name in ((1, "Ana"), (2, "Bea"), (3, "Cal"))]}
    seed = {f"reach/c{n}": {"linkedin": f"https://www.linkedin.com/in/example-person-{w}"}
            for n, w in ((1, "one"), (2, "two"), (3, "three"))}
    return _write(tmp_path_factory.mktemp("queued"), "queued", m), seed


def _did(r, action):
    return [a for a in r["acts"] if a["action"] == action]


def test_queued_profiles_are_read_by_themselves_each_on_three_pages(run, queued):
    """The profile shows only its top card until scrolled (seen live, 2026-10-29), so each
    person is read on their profile, then their Experience, Education and activity pages: no
    scrolling."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True)
    done = _did(r, "reading.done")
    assert len(done) == 3 and not _did(r, "reader.checked")
    for d in done:
        assert d["value"]["pages"] == ["profile", "experience", "education", "activity"], d["value"]
        assert "Data analyst at Example Co" in d["value"]["text"] and "\nExperience\n" in d["value"]["text"]
    went = [c["input"]["url"] for c in r["browser"] if c["tool"] == "navigate" and "/in/" in c["input"].get("url", "")]
    assert went[:4] == ["https://www.linkedin.com/in/example-person-one/",
                        "https://www.linkedin.com/in/example-person-one/details/experience/",
                        "https://www.linkedin.com/in/example-person-one/details/education/",
                        "https://www.linkedin.com/in/example-person-one/recent-activity/all/"], went
    assert not [c for c in r["browser"] if c["tool"] in ("computer", "scroll")]


def test_a_page_that_draws_late_is_read_once_more(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, slowSections=True)
    done = _did(r, "reading.done")
    assert len(done) == 3 and all(d["value"]["pages"] == ["profile", "experience", "education", "activity"] for d in done)


def test_one_tap_has_claude_write_every_note_from_them(run, queued):
    """Reading costs Claude nothing; the notes are one wake for the whole batch (the
    maintainer, 2026-10-29: keep it cheap), from the person's own tap, as the platform asks."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, canSend="available", write=True)
    ids = [a["id"] for a in r["acts"] if a["action"] == "reading.done"]
    assert len(ids) == 3 and "Read 3 profiles" in r["panel"] and "Write my notes" in r["panel"]
    (ring,) = r["rings"]
    assert ring["active"] is True and all(i in ring["text"] for i in ids), ring
    assert "reads-taken" not in r["cardsAfter"]


def test_without_the_tap_the_notes_wait_on_one_card(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, canSend="available")
    assert "reads-taken" in r["cards"] and "reading-queue" not in r["cards"]
    assert "3 profiles read" in r["todo"]


def test_signed_out_half_way_it_stops_and_never_saves_the_sign_in_page(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, signOutAfter=1)
    assert len(_did(r, "reading.done")) == 1
    told = _did(r, "reader.checked")
    assert told and told[-1]["value"]["ok"] is False and r["state"]["panel"] == "sign_in"


def test_a_security_check_stops_reading_and_is_never_called_signed_out(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, check=1)
    assert len(_did(r, "reading.done")) == 1
    assert r["state"]["panel"] == "check" and not r["state"].get("signedOut")


def test_a_refusal_is_never_called_signed_out(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, declined=True)
    assert not _did(r, "reading.done")
    assert r["state"].get("panel") != "sign_in" and not r["state"].get("signedOut") and "not allowed" in r["line"]


def test_back_from_signing_in_it_checks_again_and_reads_by_itself(run, queued):
    """Signed out, the person signs in in Claude's browser and comes back: no button to press."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=False, signInLater=True)
    assert r["state"]["ok"] is True and r["state"].get("panel") == "done"
    assert len(_did(r, "reading.done")) == 3 and "Write my notes" in r["panel"]


def _with(reading=None, settings=None):
    m = _sample()
    li = m.setdefault("linkedin", {})
    li["reading"] = dict({"id": "linkedin-reader", "page_reads": True, "ok": True, "rev": "r0", "setting": "browser",
                          "queue": [{"id": "read-c1", "contact": "c1", "first_name": "Ana", "employer": "Example Co",
                                     "mode": "deep", "asked_on": "2026-10-25", "reach": "reach/c1", "rev": "q1"}]},
                         **(reading or {}))
    if settings is not None:
        m["settings"] = settings
    return m


SEED = {"reach/c1": {"linkedin": "https://www.linkedin.com/in/example-person-one"}}


def test_i_paste_them_reads_nothing_and_asks_nothing(run, tmp_path):
    html = _write(tmp_path, "paste", _with({"setting": "paste", "queue": []}))
    r = run("reading", html=html, seed=SEED, signedIn=True)
    assert r["browser"] == [] and not r["errors"]
    assert "reading-card" not in r["cards"] and "reading-queue" not in r["cards"]


def test_paused_by_linkedin_it_reads_nothing_until_tomorrow(run, tmp_path):
    html = _write(tmp_path, "paused", _with({"paused": True, "paused_until": "2999-01-01"}))
    r = run("reading", html=html, seed=SEED, signedIn=True)
    assert not _did(r, "reading.done") and not [c for c in r["browser"] if "/in/" in c["input"].get("url", "")]
    assert "until tomorrow" in r["todo"]


def test_the_bins_never_is_the_setting_so_it_holds_on_every_device(run, tmp_path):
    setting = {"id": "setting-profile_reads", "key": "profile_reads", "label": "Reading LinkedIn profiles",
               "kind": "choice", "value": "browser", "rev": "s1",
               "choices": [["browser", "Claude reads them"], ["paste", "I paste them"]]}
    m = _with({"ok": None, "page_reads": False, "queue": []}, settings=[setting])
    html = _write(tmp_path, "bin", m)
    r = run("reading", html=html, seed=SEED, signedIn=False, bin="never")
    (s,) = [a for a in r["acts"] if a["action"] == "setting.set"]
    assert s["item"] == "setting-profile_reads" and s["value"] == "paste"
