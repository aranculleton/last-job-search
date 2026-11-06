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


# The tab the page opened for itself, kept on this device (a tap's preview_start named it 7).
TAB = {"reading-tab": "7"}
TAB_DOC = {"meta/reading-tab": {"tab": 7}}


def _own_tab_only(calls):
    """Every call that loads or reads a page names the page's own tab: one with no tab goes to
    whatever the person has in front of them (the built-in-browser skill: omitting tabId targets
    the active tab), which is how "the browser opened to some random dudes page" (2026-11-06)."""
    return [c for c in calls if c["tool"] in ("navigate", "get_page_text", "read_page")
            and c["input"].get("tabId") != 7]


def test_with_no_tab_of_its_own_nothing_is_loaded_by_itself(run, queued):
    """The maintainer, 2026-11-06: opened, Claude's browser showed a contact's profile, unasked.
    With no tab of its own the page loads nothing and reads nothing by itself: the queue card
    says, once, where the reading happens and what one tap does, and that tap opens the tab and
    reads in it."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True)
    assert not r["errors"], r["errors"]
    assert r["browser"] == [], r["browser"]
    assert "reading-queue" in r["cards"] and "Press Read them once to open that tab" in r["todo"], r["todo"][:400]
    tapped = run("reading", html=html, seed=seed, signedIn=True, tap="read-them")
    opened = [c for c in tapped["browserAll"] if c["tool"] == "preview_start"]
    assert len(opened) == 1, tapped["browserAll"]
    assert _own_tab_only(tapped["browserAll"]) == [], tapped["browserAll"]
    assert len(_did(tapped, "reading.done")) == 3


def test_opened_in_the_app_and_signed_in_it_checks_by_itself_in_its_own_tab(run, page):
    """It looks first at its own tab as it stands, as text, and loads LinkedIn there only when
    that does not show the person signed in."""
    r = run("reading", html=page, signedIn=True, look=TAB)
    assert not r["errors"], r["errors"]
    tools = [c["tool"] for c in r["browser"]]
    assert tools[:3] == ["get_page_text", "navigate", "get_page_text"], tools
    assert r["browser"][1]["input"].get("url", "").startswith("https://www.linkedin.com/")
    assert _own_tab_only(r["browser"]) == [] and "preview_start" not in tools, r["browser"]
    assert r["state"]["ok"] is True and not r["state"].get("panel")


def test_signed_out_one_to_do_card_says_so_plainly(run, page):
    r = run("reading", html=page, signedIn=False, look=TAB)
    assert r["state"]["signedOut"] is True and not r["state"].get("panel"), r["state"]
    assert r["panel"] == "" and "reading-card" in r["cards"], (r["panel"], r["cards"])
    assert r["todo"].count("You're not signed in to LinkedIn in Claude's browser") == 1, r["todo"][:600]
    assert "in its own browser, in the Claude app on this computer" in r["todo"]


def test_signed_in_it_is_not_checked_again_on_this_device_for_a_week(run, page):
    """Each opening of the page loaded LinkedIn in Claude's browser to check, and the person
    had a tab to close every time (2026-10-30)."""
    import datetime as dt
    r = run("reading", html=page, signedIn=True, look=TAB)
    until = dt.datetime.fromisoformat(r["stored"]["okUntil"].replace("Z", "+00:00"))
    left = until - dt.datetime.fromisoformat(r["stored"]["now"].replace("Z", "+00:00"))   # the page's clock
    assert dt.timedelta(days=6) < left <= dt.timedelta(days=7), left
    again = run("reading", html=page, signedIn=True, look=dict(TAB, **{"reading-ok-until": "2099-01-01T00:00:00.000Z"}))
    assert again["browser"] == [] and again["state"]["ok"] is True and not again["errors"]


def test_signed_out_nothing_opens_by_itself_and_open_linkedin_opens_the_sign_in(run, page):
    """From 2026-10-30 the page opened LinkedIn's sign-in itself once a day, and that tab put
    Claude's browser in front of the person, where reading belongs in the background (the
    maintainer, 2026-11-04). Signed out, the panel says how; their tap on Open LinkedIn opens
    the sign-in, and says the tab can be closed."""
    r = run("reading", html=page, signedIn=False, tap="reading-open", look=TAB)
    assert not [c for c in r["browser"] if c["tool"] == "preview_start"], r["browser"]
    assert r["state"]["signedOut"] is True and "sign in" in r["todo"].lower()
    opened = [c for c in r["browserAll"] if c["tool"] == "preview_start"]
    assert len(opened) == 1 and opened[0]["input"]["url"] == "https://www.linkedin.com/login", r["browserAll"]
    assert "close that tab" in r["todo"], r["todo"][:600]
    assert not r["stored"]["okUntil"]


# ------------------------------------------------------------- once a day, out of the way
# Going from the pinned chat to another and back opens the page again, and each opening loaded
# LinkedIn in Claude's browser to check, though it had seen the person signed in five times
# that day (the maintainer, 2026-11-04, note 9). `noStorage`: this device's storage comes back
# empty, as the Claude app can hand it back, so only the search's own store remembers.

SAME_DAY, LATER, NEXT_DAY = "2026-10-25T09:00:00Z", "2026-10-25T15:00:00Z", "2026-10-26T09:00:00Z"


def test_switching_to_another_chat_and_back_never_checks_linkedin_again_that_day(run, page):
    r = run("reading", html=page, seed=TAB_DOC, signedIn=True, noStorage=True, clock=SAME_DAY,
            again=[{"clock": LATER, "backFrom": True},
                   {"clock": "2026-10-25T21:00:00Z", "apply": True, "backFrom": True}])
    assert [c["tool"] for c in r["browser"]][:3] == ["get_page_text", "navigate", "get_page_text"], r["browser"]
    assert _own_tab_only(r["browser"]) == [], r["browser"]
    for k in ("again0", "again1"):           # before a chat took the tap, and after
        assert r[k]["browser"] == [] and r[k]["state"]["ok"] is True and not r[k]["errors"], r[k]
    checks = [a for a in r["acts"] if a["action"] == "reader.checked"]
    assert len(checks) == 1 and checks[0]["value"]["ok"] is True, checks


def test_the_next_day_it_looks_once_more(run, page):
    r = run("reading", html=page, seed=TAB_DOC, signedIn=True, noStorage=True, clock=SAME_DAY,
            again=[{"clock": NEXT_DAY, "apply": True}])
    assert "navigate" in [c["tool"] for c in r["again0"]["browser"]], r["again0"]
    assert _own_tab_only(r["again0"]["browser"]) == [], r["again0"]
    assert r["again0"]["state"]["ok"] is True


def test_signed_out_today_coming_back_from_another_chat_loads_nothing(run, page):
    """Signed out at today's look, a later opening says so from the record and loads nothing:
    no second look and no sign-in tab of its own, whatever coming back fires."""
    r = run("reading", html=page, seed=TAB_DOC, signedIn=False, noStorage=True, clock=SAME_DAY,
            again=[{"clock": LATER, "backFrom": True}])
    # Its own tab read as text, as it stands: nothing loaded.
    assert [c["tool"] for c in r["again0"]["browser"] if c["tool"] != "get_page_text"] == [], r["again0"]["browser"]
    assert _own_tab_only(r["again0"]["browser"]) == [], r["again0"]["browser"]
    assert r["again0"]["state"]["signedOut"] is True and "reading-card" in r["again0"]["cards"]


def test_back_from_signing_in_the_kept_tab_is_read_as_it_stands(run, page):
    """The sign-in tab their tap opened is the one the page keeps: back from signing in there,
    the check reads it as it is, with nothing loaded again."""
    r = run("reading", html=page, signedIn=False, tap="reading-open", signInLater=True)
    calls = r["browserAll"]
    at = next(i for i, c in enumerate(calls) if c["tool"] == "preview_start")
    after = calls[at + 1:]
    assert after and after[0] == {"tool": "get_page_text", "input": {"tabId": 7}}, after
    assert not [c for c in after if c["tool"] == "navigate"], after
    assert r["state"]["ok"] is True


def test_outside_the_app_it_never_touches_the_browser(run, page):
    r = run("reading", html=page, inApp=False)
    assert r["browser"] == [] and not r["errors"]


def test_the_first_call_waits_for_the_allow_prompt_and_tries_once_more(run, page):
    """Live, the first call came back retryable while the app's allow prompt was open."""
    r = run("reading", html=page, signedIn=True, askFirst=True, look=TAB)
    assert [c["tool"] for c in r["browser"]][:4] == ["get_page_text", "get_page_text", "navigate", "get_page_text"], r["browser"]
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
    r = run("reading", html=html, seed=seed, signedIn=True, look=TAB)
    done = _did(r, "reading.done")
    assert len(done) == 3 and not _did(r, "reader.checked")
    assert _own_tab_only(r["browser"]) == [], r["browser"]
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
    r = run("reading", html=html, seed=seed, signedIn=True, slowSections=True, look=TAB)
    done = _did(r, "reading.done")
    assert len(done) == 3 and all(d["value"]["pages"] == ["profile", "experience", "education", "activity"] for d in done)


def test_one_tap_has_claude_write_every_note_from_them(run, queued):
    """Reading costs Claude nothing; the notes are one wake for the whole batch (the
    maintainer, 2026-10-29: keep it cheap), from the person's own tap, as the platform asks."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, canSend="available", write=True, look=TAB)
    ids = [a["id"] for a in r["acts"] if a["action"] == "reading.done"]
    assert len(ids) == 3 and "Read 3 profiles" in r["panel"] and "Write my notes" in r["panel"]
    (ring,) = r["rings"]
    assert ring["active"] is True and all(i in ring["text"] for i in ids), ring
    assert "reads-taken" not in r["cardsAfter"]


def test_without_the_tap_the_notes_wait_on_one_card(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, canSend="available", look=TAB)
    assert "reads-taken" in r["cards"] and "reading-queue" not in r["cards"]
    assert "3 profiles read" in r["todo"]


def test_a_profile_read_today_is_not_read_again_at_the_next_opening(run, queued):
    """A chat refused one read (their page did not load). Every opening read them again, so
    their profile opened in Claude's browser at each switch back to the page; now it is read
    again tomorrow, or at once with Read them, which the queue card still offers."""
    html, seed = queued
    r = run("reading", html=html, seed=dict(seed, **TAB_DOC), signedIn=True, noStorage=True, clock=SAME_DAY,
            again=[{"clock": LATER, "refuse": ["read-c2"], "backFrom": True}, {"clock": NEXT_DAY}])
    assert len(_did(r, "reading.done")) >= 3
    first = [c for c in r["again0"]["browser"] if "/in/" in c["input"].get("url", "")]
    assert first == [], first
    assert "reading-queue" in r["again0"]["cards"], r["again0"]["cards"]
    went = [c["input"]["url"] for c in r["again1"]["browser"] if "/in/" in c["input"].get("url", "")]
    assert went and all("example-person-two" in u for u in went), went


def _profiles(calls):
    return [c["input"]["url"] for c in calls if c["tool"] == "navigate" and "/in/" in c["input"].get("url", "")]


# "That day" is the person's own day (their time zone, todayIso), whatever the device's clock
# says: the hold went by the device's own date, so a device 14 hours ahead of the person or 10
# behind held a different day from the one the day's reads were counted on (4.11.0's far time
# zone runs). Each is run on the device's zone and on both far ones, on every runner.
DEVICE_ZONES = [None, "Pacific/Kiritimati", "Pacific/Honolulu"]


@pytest.mark.parametrize("device", DEVICE_ZONES)
def test_its_tab_closed_mid_read_nothing_loads_by_itself_and_one_card_says_what_to_do(run, queued, device):
    """The maintainer, 2026-11-05, over several versions: back on the pinned page, "Reading
    someone's profile, 0 of 4" and their LinkedIn opened in Claude's browser, which they closed at
    once, every time. Closing it closes the page's own tab: nothing loads by itself again, at any
    opening, that day or the next, and never in the tab in front of them (2026-11-06); the queue
    card says once what one tap does."""
    html, seed = queued
    r = run("reading", html=html, seed=dict(seed, **TAB_DOC), signedIn=True, closeOnProfile=True, noStorage=True,
            clock=SAME_DAY, timezoneId=device, again=[{"clock": LATER, "backFrom": True}, {"clock": NEXT_DAY}])
    assert not _did(r, "reading.done"), _did(r, "reading.done")
    assert _profiles(r["browser"]) and _own_tab_only(r["browserAll"]) == [], r["browserAll"]
    for k in ("again0", "again1"):
        assert r[k]["browser"] == [], r[k]["browser"]
        assert "reading-queue" in r[k]["cards"], r[k]["cards"]


@pytest.mark.parametrize("device", DEVICE_ZONES)
def test_a_run_left_unfinished_tries_again_by_itself_two_hours_on(run, queued, device):
    """Never left waiting on the person (2026-11-06): a run an opening left unfinished holds the
    automatic reads for two hours, then they go again by themselves, in the page's own tab."""
    html, seed = queued
    seed = dict(seed, **TAB_DOC, **{"meta/reads": {"day": "2026-10-25", "running": True, "cut": False,
                                                   "at": "2026-10-25T06:30:00.000Z"}})
    r = run("reading", html=html, seed=seed, signedIn=True, clock=SAME_DAY, timezoneId=device)
    assert len(_did(r, "reading.done")) == 3 and _own_tab_only(r["browser"]) == [], r["browser"]


@pytest.mark.parametrize("device", DEVICE_ZONES)
def test_an_opening_that_went_mid_read_holds_them_and_read_them_still_reads(run, queued, device):
    """The page left while a read ran (its run never finished): the next opening that day loads
    no profile by itself, and the person's own Read them still reads at once."""
    html, seed = queued
    seed = dict(seed, **TAB_DOC, **{"meta/reads": {"day": "2026-10-25", "running": True, "cut": False,
                                                   "at": "2026-10-25T08:30:00.000Z"}})
    r = run("reading", html=html, seed=seed, signedIn=True, clock=SAME_DAY, tap="read-them",
            timezoneId=device)
    assert _profiles(r["browser"]) == [], r["browser"]
    assert len(_did(r, "reading.done")) == 3 and _profiles(r["browserAll"]), r["acts"]


def test_signed_out_half_way_it_stops_and_never_saves_the_sign_in_page(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, signOutAfter=1, look=TAB)
    assert len(_did(r, "reading.done")) == 1
    told = _did(r, "reader.checked")
    assert told and told[-1]["value"]["ok"] is False and r["state"]["signedOut"] is True
    assert "You're not signed in to LinkedIn in Claude's browser" in r["todo"]


def test_a_security_check_stops_reading_and_is_never_called_signed_out(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, check=1, look=TAB)
    assert len(_did(r, "reading.done")) == 1
    assert "LinkedIn wants to check it's you" in r["todo"] and not r["state"].get("signedOut")


def test_a_refusal_is_never_called_signed_out(run, queued):
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=True, declined=True, look=TAB)
    assert not _did(r, "reading.done")
    assert r["state"].get("panel") != "sign_in" and not r["state"].get("signedOut") and "not allowed" in r["line"]


def test_back_from_signing_in_it_checks_again_and_reads_by_itself(run, queued):
    """Signed out, the person signs in in Claude's browser and comes back: no button to press."""
    html, seed = queued
    r = run("reading", html=html, seed=seed, signedIn=False, signInLater=True, look=TAB)
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
