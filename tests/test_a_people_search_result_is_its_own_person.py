"""Each person a people search shows is one result, as themselves, and one a read ruled out
stays out until something new is known about them.

Two causes of the people run that stopped at 8 of the 20 asked for (2026-11-12):

- #259: the list extractor paired each profile link with the card it sits in, so a card's
  "<name> is a mutual connection" line came back as a second result, carrying the card's
  own name and headline: the contact book could take the mutual connection in as a recruiter
  at that employer. Each card is one result now, from its own name link, the whole card's
  text with it, and a mutual connection's link is never a result.
- #260: a person a profile read ruled out (`reading.py skip`) was reopened by a later check
  of the same search results ("an earlier run closed them, not you") and chosen again ahead
  of people never looked at. A read's ruling holds until something new is known about them
  (a new headline or employer); only a close by a list rule (the employer's limit of people
  waiting) is checked again by today's rules.

Made-up people and employers only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import reading  # noqa: E402
from test_a_people_run_reaches_the_people_who_answer import (  # noqa: E402
    ENG_EMP, ENG_NET, _book, _check, _json, _names, _p, _profile, _rows)

# A people search's results as LinkedIn draws them now: each card a block of its own, its
# name link first, and on some a line naming a mutual connection with their own link.
PAGE = """<html><body><main><div class="results">
<div class="card"><div class="top"><a href="https://www.linkedin.com/in/jory-pellam-example/?mini=1">
<span>Jory Pellam</span></a><div>2nd</div><div>Technical Recruiter @ Acme Data</div></div>
<div>Toronto, Ontario, Canada</div>
<div class="insight"><img alt=""><span><a href="https://www.linkedin.com/in/sam-lee-example">Sam
Lee</a> is a mutual connection</span></div><button>Connect</button></div>
<div class="card"><div class="top"><a href="https://www.linkedin.com/in/kit-ames-example">
<span>Kit Ames</span></a><div>2nd</div><div>Talent Partner, Data @ Acme Data</div></div>
<div>Mississauga, Ontario, Canada</div>
<div class="insight"><span><a href="https://www.linkedin.com/in/sam-lee-example">Sam Lee</a>,
<a href="https://www.linkedin.com/in/ana-rook-example">Ana Rook</a> and 2 other mutual
connections</span></div><button>Message</button></div>
<div class="card"><div class="top"><a href="https://www.linkedin.com/in/sam-lee-example">
<span>Sam Lee</span></a><div>1st</div><div>Analytics Manager @ Fernhill Freight</div></div>
<div>Toronto, Ontario, Canada</div><button>Message</button></div>
</div></main></body></html>"""

# The layout the extractor was first built on: each card an item of a list.
LIST_PAGE = """<html><body><main><ul>
<li><a href="https://www.linkedin.com/in/juno-castellan-example"><span>Juno Castellan</span></a>
<div>2nd</div><div>Senior Data Scientist at Larkspur</div><div>Leeds, England</div>
<div><a href="https://www.linkedin.com/in/wren-allard-example">Wren Allard</a> is a mutual
connection</div><button>Connect</button></li>
<li><a href="https://www.linkedin.com/in/bo-venn-example"><span>Bo Venn</span></a>
<div>3rd+</div><div>IT Support Specialist at Larkspur</div><div>Leeds, England</div>
<button>Follow</button></li>
</ul></main></body></html>"""


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
    return env


RUN = """
const fs = require("fs"); const {chromium} = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.setContent(fs.readFileSync(process.argv[1], "utf8"));
  console.log(await p.evaluate(fs.readFileSync(process.argv[2], "utf8")));
  await b.close();
})().catch((e) => { console.error(String(e)); process.exit(3); });
"""


def _extract(tmp_path, html: str) -> list:
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node here, so no browser to run the extractor in")
    env = _node_env()
    if subprocess.run([node, "-e", "require('playwright')"], env=env,
                      capture_output=True).returncode:
        pytest.skip("Playwright for Node is not installed here")
    page, js = tmp_path / "page.html", tmp_path / "extract.js"
    page.write_text(html, encoding="utf-8")
    js.write_text(reading.LIST_EXTRACTOR, encoding="utf-8")
    got = subprocess.run([node, "-e", RUN, str(page), str(js)], env=env, capture_output=True,
                         text=True, encoding="utf-8", timeout=120)
    if got.returncode == 3 and "Executable doesn't exist" in got.stderr:
        pytest.skip("Chromium is not installed for Playwright here")
    assert got.returncode == 0, got.stderr[-800:]
    return json.loads(got.stdout)["cards"]


# ------------------------------------------------------------------ #259


def test_a_mutual_connection_is_never_a_result_of_its_own(tmp_path):
    cards = _extract(tmp_path, PAGE)
    by = {c["url"]: c for c in cards}
    assert list(by) == ["https://www.linkedin.com/in/jory-pellam-example",
                        "https://www.linkedin.com/in/kit-ames-example",
                        "https://www.linkedin.com/in/sam-lee-example"]
    # Each result is the whole card it is about, its place and its button with it.
    jo = by["https://www.linkedin.com/in/jory-pellam-example"]
    assert jo["text"].startswith("Jory Pellam") and "Toronto" in jo["text"]
    assert jo["buttons"] == ["Connect"]
    # Sam Lee is a result once, as himself, never with someone else's card.
    sam = by["https://www.linkedin.com/in/sam-lee-example"]
    assert sam["text"].startswith("Sam Lee") and "Fernhill Freight" in sam["text"]
    assert "ana-rook" not in json.dumps(cards)
    people = reading.people_page(reading.from_list_extract(json.dumps({"cards": cards})),
                                 "Acme Data")
    assert {p["name"]: p["linkedin_url"] for p in people}["Jory Pellam"] == \
        "https://www.linkedin.com/in/jory-pellam-example"


def test_cards_that_are_list_items_read_as_before(tmp_path):
    cards = _extract(tmp_path, LIST_PAGE)
    assert [c["url"] for c in cards] == ["https://www.linkedin.com/in/juno-castellan-example",
                                         "https://www.linkedin.com/in/bo-venn-example"]
    assert cards[0]["buttons"] == ["Connect"] and "Leeds" in cards[0]["text"]


def test_the_extractor_still_only_reads():
    for verb in ("click(", "scroll", ".value =", "dispatchEvent", "submit(", "focus("):
        assert verb not in reading.LIST_EXTRACTOR


# ------------------------------------------------------------------ #260


def test_a_read_that_ruled_someone_out_holds_on_the_same_results(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "nimbus_fenn", "name": "Tova Fenn", "company": "Nimbus Cloud",
         "title": "Technical Recruiter", "status": "closed",
         "linkedin_url": "https://www.linkedin.com/in/tova-fenn-example",
         "outcome": "skipped after a read 2026-11-12: hires warehouse staff only, not "
                    "engineers"}])
    same = [_p("Tova Fenn", "Technical Recruiter", "Nimbus Cloud"),
            _p("Ivo Marr", "Engineering Manager", "Nimbus Cloud")]
    got = _json(tmp_path, same, "--want", "2")
    assert _names(got["chosen"]) == ["Ivo Marr"]
    why = {o["name"]: o["why"] for o in got["out"]}["Tova Fenn"]
    assert "hires warehouse staff only" in why and "nothing new" in why
    text = _check(tmp_path, same, "--want", "2", "--add")
    assert "opened again" not in text
    assert {r["contact_id"]: r for r in _rows(tmp_path)}["nimbus_fenn"]["status"] == "closed"


def test_something_new_about_them_is_checked_again(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "nimbus_fenn", "name": "Tova Fenn", "company": "Nimbus Cloud",
         "title": "Technical Recruiter", "status": "closed",
         "linkedin_url": "https://www.linkedin.com/in/tova-fenn-example",
         "outcome": "skipped after a read 2026-11-12: hires warehouse staff only, not "
                    "engineers"}])
    moved = [_p("Tova Fenn", "Technical Recruiter, Engineering | Hiring", "Nimbus Cloud")]
    got = _json(tmp_path, moved, "--want", "1")
    assert _names(got["chosen"]) == ["Tova Fenn"]
    assert any("checked again" in w for w in got["chosen"][0]["warn"])


def test_a_close_by_a_list_rule_is_checked_again_by_todays_rules(tmp_path):
    _profile(tmp_path, ENG_NET, ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "nimbus_fenn", "name": "Tova Fenn", "company": "Nimbus Cloud",
         "title": "Technical Recruiter", "status": "closed",
         "linkedin_url": "https://www.linkedin.com/in/tova-fenn-example",
         "outcome": "skipped after a read 2026-11-01: two already waiting there"}])
    got = _json(tmp_path, [_p("Tova Fenn", "Technical Recruiter", "Nimbus Cloud")],
                "--want", "1")
    assert _names(got["chosen"]) == ["Tova Fenn"]
