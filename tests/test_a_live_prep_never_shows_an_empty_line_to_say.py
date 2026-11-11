"""A live prep never shows "Say first" over empty lines.

The night before an interview (2026-11-11), a person's prep opened on "Open with" and "Say
first" with blank bullets under them: every line of what to say first was empty. The words
file had said each line's words under another name than "t", the merge read "t" alone and
kept "", and no check looked for a line with no words, so it was kept as fit to show and every
rebuild after kept the blanks.

Now the words are read however a chat writes them (plain words, or under "t", "text", "line"
or "say"), a line with no words is refused in plain words when it is written and left out
when a saved prep holds one, the page never draws one, and a chat can write only the missing
lines again with `live --fill`, every other word of the prep kept as it was. Every person,
employer and role here is invented: the example person and the made-up application
`tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_live as L  # noqa: E402
from test_an_interview_has_a_live_prep import _fill, _words  # noqa: E402
from test_interview_pack import COMPANY, ROLE, _ctx, app  # noqa: E402,F401

pytestmark = pytest.mark.usefixtures("app")

OPENING = ("Thanks for making the time, and I'm glad to be talking about the planning work at "
           "Fernhill Freight.")
THREAD = ("The thread through my work is turning messy forecasts into numbers planners trust, and "
          "the clearest case is the safety stock we freed.")


def _said(base):
    """The words Claude writes for `base`, the problem it adds to a technical part under "new"."""
    words = _words(base)
    ids = {q["id"] for q in base["questions"]}
    words["new"] = [dict(q) for q in _fill(base)["questions"] if q["id"] not in ids]
    words["questions"] = {k: v for k, v in words["questions"].items() if k in ids}
    return words


def _cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))


def test_lines_to_say_written_as_text_or_as_plain_words_reach_the_prep():
    ctx = _ctx()
    base = L.merge(L.build(ctx), None)
    words = _said(base)
    first = base["questions"][0]["id"]
    # One part's lines under "text", another's as plain words: the shapes a chat has written.
    words["parts"][base["parts"][0]["id"]]["say"] = [{"text": OPENING, "prompts": []},
                                                     {"text": THREAD, "prompts": [first]}]
    words["parts"][base["parts"][1]["id"]]["say"] = [OPENING, THREAD]
    doc = L.merge(L.build(ctx), L.words_into(base, words))
    for p in doc["parts"][:2]:
        assert [b["t"] for b in p["say"]] == [OPENING, THREAD], p["say"]
    assert doc["parts"][0]["say"][1]["prompts"] == [first]
    assert not any("no words" in why for _w, why in L.problems(doc, ctx))


def test_a_line_written_with_no_words_is_refused_in_plain_words():
    base = L.merge(L.build(_ctx()), None)
    pid = base["parts"][0]["id"]
    for say in ([{"t": "", "prompts": []}], [{"prompts": [base["questions"][0]["id"]]}], ["  "]):
        words = _said(base)
        words["parts"][pid]["say"] = say
        with pytest.raises(ValueError) as got:
            L.words_into(base, words)
        assert "no words" in str(got.value) and "Traceback" not in str(got.value)
    words = _said(base)
    words["parts"][pid]["say"] = OPENING
    with pytest.raises(ValueError) as got:
        L.words_into(base, words)
    assert "a list of lines" in str(got.value)


def test_a_prep_saved_with_empty_lines_shows_none_of_them():
    ctx = _ctx()
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found, found
    saved = json.load(open(path, encoding="utf-8"))
    # As a prep made before the fix was kept: the first part's lines all empty, no line to end on.
    saved["parts"][0]["say"] = [{"t": "", "prompts": []} for _ in range(3)]
    saved["parts"][0]["bridge"] = ""
    page = L.for_page(saved)
    assert page["parts"][0]["say"] == []
    assert all(b["t"] for p in page["parts"] for b in p["say"])
    assert [b["t"] for b in page["parts"][1]["say"]] == [b["t"] for b in saved["parts"][1]["say"]]
    # A rebuild never brings them back as lines, and its check says the part needs its words.
    again = L.merge(L.build(ctx), saved)
    assert again["parts"][0]["say"] == []
    title = again["parts"][0]["title"]
    assert any(where == '"%s"' % title and why.startswith("nothing to say first yet")
               for where, why in L.problems(again, ctx))
    # An empty line handed to the check straight is named, never passed.
    raw = copy.deepcopy(again)
    raw["parts"][1]["say"].append({"t": "", "prompts": []})
    assert any("it has no words" in why for _w, why in L.problems(raw, ctx))


def test_only_the_missing_lines_are_written_again_and_the_rest_of_the_prep_stays(tmp_path):
    # The path a chat takes for a prep saved with empty lines: a words file holding only each
    # part's lines to say first, then live --fill --write; every other word stays as it was.
    built = tmp_path / "live.json"
    assert _cli("live", COMPANY, "--role", ROLE, "--out", str(built)).returncode == 0
    wf = tmp_path / "words.json"
    wf.write_text(json.dumps(_words(json.loads(built.read_text(encoding="utf-8")))), encoding="utf-8")
    ok = _cli("live", COMPANY, "--role", ROLE, "--fill", str(wf), "--write")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    path = L.path_for(_ctx()["folder"])
    saved = json.load(open(path, encoding="utf-8"))
    for p in saved["parts"]:
        p["say"] = [{"t": "", "prompts": []}, {"t": "", "prompts": []}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(saved, fh, ensure_ascii=False, indent=1)
    check = _cli("live-check", COMPANY, "--role", ROLE)
    assert check.returncode == 1 and "nothing to say first yet" in check.stdout, check.stdout
    first = saved["questions"][0]["id"]
    words = {"parts": {p["id"]: {"say": [{"t": OPENING, "prompts": []},
                                         {"t": THREAD, "prompts": [first]}]}
                       for p in saved["parts"]}}
    wf = tmp_path / "say.json"
    wf.write_text(json.dumps(words), encoding="utf-8")
    ok = _cli("live", COMPANY, "--role", ROLE, "--fill", str(wf), "--write")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    kept = L.load(os.path.dirname(path))
    assert kept and kept["checked"]["problems"] == 0
    assert all([b["t"] for b in p["say"]] == [OPENING, THREAD] for p in kept["parts"])
    for key in ("questions", "stories", "ask", "terms", "private", "known"):
        assert kept[key] == saved[key], key
    assert [(p["id"], p["kind"], p["title"], p["bridge"], p["follow"]) for p in kept["parts"]] == \
        [(p["id"], p["kind"], p["title"], p["bridge"], p["follow"]) for p in saved["parts"]]


# ------------------------------------------------------------------ the page

@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


def test_the_page_draws_no_empty_bullet_and_no_empty_open_with(run, tmp_path):
    from test_the_live_prep_on_the_page import IV, OPEN, _go, _model
    from test_the_page_journeys import PHONE
    m = _model()
    live = next(iv for iv in m["interviews"] if iv["id"] == IV)["live"]
    # A page model carrying a prep's empty lines straight, as one saved before the fix would.
    live["parts"][0]["say"] = [{"t": "", "prompts": []}, {"t": "  ", "prompts": []}, {"prompts": []}]
    live["parts"][0]["bridge"] = ""
    live["parts"][1]["say"].insert(0, {"t": "", "prompts": []})
    look = ("(() => { const d = document.querySelector('dialog.detail');"
            " const parts = [...d.querySelectorAll('.lp-part[data-lpp]')];"
            " return {empty: [...d.querySelectorAll('.lp-beat')].filter((li) => !li.textContent.trim()).length,"
            " beats: d.querySelectorAll('.lp-beat').length,"
            " firstSay: !!parts[0].querySelector('.lp-narr'),"
            " glance: d.querySelector('.lp-glance').textContent}; })()")
    got = _go(run, tmp_path, m, [dict(OPEN, eval=look)], PHONE)
    at = got["after"][0]["eval"]
    assert at["empty"] == 0 and at["beats"] > 0, at
    assert not at["firstSay"], "a part with no words to say first shows no Say first box"
    assert "Open with" not in at["glance"] and "Before you start" not in at["glance"], at["glance"]
