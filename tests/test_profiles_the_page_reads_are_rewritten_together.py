"""Profiles the page reads cost one piece of Claude's work, and a read never loops.

The page reads LinkedIn by itself in the Claude desktop app: each person's profile, then their
Experience and Education pages, which show everything without scrolling (the profile alone
shows only its top card until it is scrolled, seen live 2026-10-29). The engine keeps each
read the way a computer chat keeps one, and:

- every profile read before Claude next runs goes on ONE rewrite, never one each (the
  maintainer, 2026-10-29: keep it cheap);
- a read with its Experience page loaded is never told to scroll;
- a read no second try would change comes off the queue; a sign-in page stays on it;
- the browser's own header above each page's text is not read as part of the profile;
- "I paste them" chosen on the page holds on every device: nothing is queued for the page.

Every name here is invented (tests/fixtures/linkedin_export/README.md).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_takes_the_linkedin_download_and_reads_linkedin import Page  # noqa: E402

VARGA, SMITH = "kestrel_mutual_varga", "kestrel_mutual_smith"


def _head(url):
    return f"Title: Someone | LinkedIn\nURL: {url}\nSource element: <main>\n---\n"


def _pages(name, title, url, roles=True):
    """A person's three pages as the page joins them, each under the browser's header."""
    exp = ("Experience\n" + (f"{title}\nKestrel Mutual · Full-time\nMar 2022 - Present · 3 yrs\n"
                             "Manchester, England, United Kingdom\n" if roles else ""))
    return (_head(url) + f"{name}\n· 2nd\n{title} at Kestrel Mutual\n"
            "Manchester, England, United Kingdom\n·\nContact info\nKestrel Mutual\n"
            "500+ connections\nMessage\nConnect\nMore\n\n"
            + _head(url + "details/experience/") + exp + "\n"
            + _head(url + "details/education/") + "Education\nUniversity of Leeds\n"
            "BSc Mathematics\n2012 - 2015\n")


@pytest.fixture
def page(tmp_path):
    p = Page(str(tmp_path))
    p.act("reader.checked", "linkedin-reader", value={"ok": True}, rev="")
    p.apply()
    p.written_back()
    return p


def _queue(page, *ids):
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                          "queue-page", *ids], env=page.env(), capture_output=True,
                         encoding="utf-8", cwd=ROOT)
    return out


def _waiting(page, cid):
    d = os.path.join(page.state, "documents", "network", cid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "draft.md"), "w", encoding="utf-8") as fh:
        fh.write("WAITS ON A READ: nothing was read about them.\n\nHi, I'd love to chat.\n")


def _work(got):
    return [e for b in got["batches"] for e in json.load(open(b, encoding="utf-8"))
            if e["collection"] == "work"]


def _queued(page):
    return json.loads(page.py("import reading, json; "
                              "print(json.dumps([q['contact'] for q in reading.page_queue()]))"))


def test_two_profiles_read_before_claude_runs_are_one_rewrite(page):
    assert _queue(page, VARGA, SMITH).returncode == 0
    for cid in (VARGA, SMITH):
        _waiting(page, cid)
    q = {x["contact"]: x for x in page.model()["linkedin"]["reading"]["queue"]}
    aids = [page.act("reading.done", q[cid]["id"], rev=q[cid]["rev"],
                     value={"text": _pages(name, "Analytics Lead",
                                           f"https://www.linkedin.com/in/{slug}/"),
                            "mode": "deep", "pages": ["profile", "experience", "education"]})
            for cid, name, slug in ((VARGA, "Tamsin Varga", "example-tamsin-varga"),
                                    (SMITH, "Robert Smith", "example-robert-smith"))]
    got = page.apply()
    assert got["ok"] == aids, [page.receipt(a)["note"] for a in aids]
    (w,) = _work(got)
    body = json.load(open(w["file_path"], encoding="utf-8"))
    assert body["kind"] == "network" and body["args"]["rewrite"] is True
    assert body["args"]["contacts"] == [VARGA, SMITH] and body["args"]["read"] == aids
    assert body["title"] == "Your notes to 2 people, on their profiles"
    assert _queued(page) == []
    kept = json.loads(page.py("import reading, json; r = reading.load('kestrel_mutual_varga'); "
                              "print(json.dumps([r['headline'], len(r['experience'])]))"))
    assert kept == ["Analytics Lead at Kestrel Mutual", 1]


def test_a_read_after_claude_has_taken_the_rewrite_starts_a_new_one(page):
    assert _queue(page, VARGA, SMITH).returncode == 0
    for cid in (VARGA, SMITH):
        _waiting(page, cid)
    q = {x["contact"]: x for x in page.model()["linkedin"]["reading"]["queue"]}
    a1 = page.act("reading.done", q[VARGA]["id"], rev=q[VARGA]["rev"],
                  value={"text": _pages("Tamsin Varga", "Analytics Lead",
                                        "https://www.linkedin.com/in/example-tamsin-varga/"),
                         "pages": ["profile", "experience"]})
    (w,) = _work(page.apply())
    body = json.load(open(w["file_path"], encoding="utf-8"))
    page.written_back()
    page.put("work", w["doc_id"], dict(body, status="running", claimed_by="cloud-1"), version=2)
    a2 = page.act("reading.done", q[SMITH]["id"], rev=q[SMITH]["rev"],
                  value={"text": _pages("Robert Smith", "Data Manager",
                                        "https://www.linkedin.com/in/example-robert-smith/"),
                         "pages": ["profile", "experience"]})
    got = page.apply()
    assert a2 in got["ok"], page.receipt(a2)["note"]
    (w2,) = _work(got)
    assert w2["doc_id"] != w["doc_id"]
    assert json.load(open(w2["file_path"], encoding="utf-8"))["args"]["contacts"] == [SMITH]
    assert a1 not in got["ok"]                       # applied once, in the first run


def test_a_read_with_its_experience_page_but_no_roles_is_kept(page):
    assert _queue(page, VARGA).returncode == 0
    (q,) = page.model()["linkedin"]["reading"]["queue"]
    aid = page.act("reading.done", q["id"], rev=q["rev"],
                   value={"text": _pages("Tamsin Varga", "Analytics Lead",
                                         "https://www.linkedin.com/in/example-tamsin-varga/",
                                         roles=False),
                          "pages": ["profile", "experience", "education"]})
    got = page.apply()
    assert got["ok"] == [aid], page.receipt(aid)["note"]
    assert _queued(page) == []


def test_a_sign_in_page_stays_on_the_queue_and_says_so_plainly(page):
    assert _queue(page, VARGA).returncode == 0
    (q,) = page.model()["linkedin"]["reading"]["queue"]
    text = (_head("https://www.linkedin.com/login") + "Sign in\nEmail or phone\nPassword\n"
            "Forgot password?\nNew to LinkedIn? Join now\n")
    aid = page.act("reading.done", q["id"], rev=q["rev"], value={"text": text})
    got = page.apply()
    assert aid not in got["ok"]
    note = page.receipt(aid)["note"]
    assert "sign-in page" in note and "reading.py" not in note and "--" not in note
    assert _queued(page) == [VARGA]


def test_a_read_no_second_try_would_change_leaves_the_queue(page):
    assert _queue(page, VARGA).returncode == 0
    (q,) = page.model()["linkedin"]["reading"]["queue"]
    net = os.path.join(page.profile, "networking.py")
    with open(net, encoding="utf-8") as fh:
        src = fh.read()
    with open(net, "w", encoding="utf-8") as fh:
        fh.write(src.replace('PROFILE_READS = "browser"', 'PROFILE_READS = "paste"'))
    aid = page.act("reading.done", q["id"], rev=q["rev"],
                   value={"text": _pages("Tamsin Varga", "Analytics Lead",
                                         "https://www.linkedin.com/in/example-tamsin-varga/"),
                          "pages": ["profile", "experience"]})
    got = page.apply()
    assert aid not in got["ok"]
    assert "paste" in page.receipt(aid)["note"]
    assert _queued(page) == []


def test_i_paste_them_on_the_page_holds_everywhere_and_comes_back(page):
    (s,) = [x for x in page.model()["settings"] if x["key"] == "profile_reads"]
    assert s["value"] == "browser" and [c[0] for c in s["choices"]] == ["browser", "paste"]
    aid = page.act("setting.set", s["id"], value={"value": "paste"}, rev=s["rev"])
    got = page.apply()
    assert got["ok"] == [aid], page.receipt(aid)
    with open(os.path.join(page.profile, "networking.py"), encoding="utf-8") as fh:
        assert 'PROFILE_READS = "paste"' in fh.read()
    page.written_back()
    rd = page.model()["linkedin"]["reading"]
    assert rd["setting"] == "paste" and rd["queue"] == []
    out = _queue(page, VARGA)
    assert out.returncode != 0 and "paste" in out.stdout and _queued(page) == []
    undo = page.receipt(aid)["undo"]
    (s,) = [x for x in page.model()["settings"] if x["key"] == "profile_reads"]
    back = page.act(undo["action"], s["id"], value=undo["value"], rev=s["rev"])
    assert page.apply()["ok"] == [back]
    assert page.model()["linkedin"]["reading"]["setting"] == "browser"
    assert _queue(page, VARGA).returncode == 0


def test_the_browsers_header_is_not_read_as_their_headline(page):
    got = json.loads(page.py(
        "import reading, json\n"
        f"t = {_pages('Tamsin Varga', 'Analytics Lead', 'https://www.linkedin.com/in/example-tamsin-varga/')!r}\n"
        "r = reading.parse(t, name='Tamsin Varga', company='Kestrel Mutual', source='browser')\n"
        "print(json.dumps([r['headline'], [e['employer'] for e in r['experience']], "
        "reading.has_experience(t)]))"))
    assert got == ["Analytics Lead at Kestrel Mutual", ["Kestrel Mutual"], True]


def test_their_recent_posts_are_kept_from_the_activity_page(page):
    """The page reads their activity page too (whole, with nothing to scroll): a post is the
    best one true thing a note can rest on."""
    url = "https://www.linkedin.com/in/example-tamsin-varga/"
    act = (_head(url + "recent-activity/all/") + "All activity\nPosts\nComments\n"
           "Tamsin Varga\nAnalytics Lead at Kestrel Mutual\n1w •\n"
           "We just opened two analyst roles on the pricing team.\n12 reactions\n")
    got = json.loads(page.py(
        "import reading, json\n"
        f"t = {(_pages('Tamsin Varga', 'Analytics Lead', url) + chr(10) + act)!r}\n"
        "r = reading.parse(t, name='Tamsin Varga', company='Kestrel Mutual', source='browser')\n"
        "print(json.dumps([i['kind'] + ': ' + i['text'] for i in r['items']]))"))
    assert got == ["post: We just opened two analyst roles on the pricing team."]
