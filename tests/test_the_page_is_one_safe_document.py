"""The person's page is one self-contained document, safe to publish, made by code alone.

tools/app_page.py renders the view model into the page the person's chat publishes as a
private Claude page. It must be exactly what the Artifact tool expects (content with its
own title near the top, no doctype or head of its own), carry everything inline, load no
script, stylesheet or font from anywhere, and embed the model so that no text in it can
end the script tag it sits in. The capabilities it is published with are
fixed here too, so the store stays readable and writable by its owner alone.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import app_page  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json")
PARTS = [os.path.join(ROOT, "templates", "app", n) for n in ("page.html", "app.css", "app.js", "palettes.py")]
sys.path.insert(0, os.path.join(ROOT, "templates", "app"))
import palettes  # noqa: E402


def _model():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _embedded(page):
    m = re.search(r'<script type="application/json" id="ljs-model">(.*?)</script>', page, re.S)
    assert m, "the model is embedded in its own script tag"
    return json.loads(m.group(1))


def test_the_capabilities_are_exactly_these():
    assert app_page.capabilities() == {
        # reach/<contact> (each contact's address for Open profile) is the owner's alone,
        # named as well as covered by the root (the maintainer's decision, 2026-10-25).
        "db": {"rules": [{"path": "", "read": "owner", "write": "owner"},
                         {"path": "reach", "read": "owner", "write": "owner"}]},
        "user": {},
        "downloads": True,
        "comments": {},
        "room": {},
        "sample": {},
        "assets": {},
        # Claude's own browser, in the desktop app only, with only the tools a reading needs.
        "mcp": {"servers": [{"server": "host:claude_browser",
                             "tools": ["navigate", "get_page_text", "read_page", "preview_start"]},
                            # The page wakes the chat that answers it (the maintainer, 2026-10-28).
                            {"server": "Claude Code Remote", "tools": ["send_message", "list_environments", "create_session"]}]},
    }


def test_the_page_is_content_with_its_title_first_and_no_skeleton_of_its_own():
    page = app_page.render(_model())
    assert page.startswith("<title>Morgan’s job search</title>")
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in page[:400]
    head = page.lower()
    for tag in ("<!doctype", "<html", "<head", "<body"):
        assert not re.search(re.escape(tag) + r"[\s>]", head), tag
    assert app_page.title_for({}) == "Your job search"
    assert app_page.title_for({"person": {"first_name": "<b>Ana</b>"}}) == "<b>Ana</b>’s job search"
    assert app_page.render({"model": 1, "person": {"first_name": "<b>Ana</b>"}}).startswith("<title>&lt;b&gt;Ana&lt;/b&gt;’s job search</title>")


def test_everything_is_inline_and_nothing_comes_from_outside():
    page = app_page.render(_model())
    assert not re.search(r"<script[^>]+src=", page, re.I), "no script from anywhere"
    assert not re.search(r"<link\b", page, re.I), "no stylesheet or font from anywhere"
    assert not re.search(r"@import|@font-face|url\(\s*['\"]?https?:", page, re.I), "no font or image fetched by a stylesheet"
    assert "fonts.googleapis" not in page and "fonts.gstatic" not in page
    assert not re.search(r"\bimport\s*\(|\bfetch\(\s*['\"]https?:", page), "nothing fetched from another site"
    assert len(page.encode("utf-8")) < 1024 * 1024


def test_the_model_round_trips_and_cannot_end_its_script_tag():
    model = _model()
    model["jobs"]["rows"][0]["title"] = "</script><script>alert(1)</script><!-- &  "
    page = app_page.render(model)
    assert _embedded(page) == model
    body = re.search(r'id="ljs-model">(.*?)</script>', page, re.S).group(1)
    assert "<" not in body and ">" not in body and "&" not in body
    own = open(PARTS[0], encoding="utf-8").read().count("</script>")
    assert page.count("</script>") == own == 4, "the model's own text adds no closing tag (the model, the engine tables, the page, its start)"


def test_a_placeholder_in_the_model_stays_text():
    model = _model()
    model["person"]["first_name"] = "{{CSS}}"
    model["needs_you"][0]["title"] = "{{JS}} {{MODEL}}"
    page = app_page.render(model)
    assert page.startswith("<title>{{CSS}}’s job search</title>")
    assert _embedded(page)["needs_you"][0]["title"] == "{{JS}} {{MODEL}}"


def test_standalone_wraps_it_the_way_the_artifact_tool_does():
    page = app_page.render(_model())
    full = app_page.standalone(page)
    assert full.startswith("<!doctype html><html><head><meta charset=utf8>")
    assert "viewport-fit=cover" in full and "[hidden]{display:none!important}" in full
    assert full.endswith("</body></html>") and page in full


def test_the_parts_follow_the_page_contract():
    css = open(PARTS[1], encoding="utf-8").read()
    js = open(PARTS[2], encoding="utf-8").read()
    # Colour tokens (written by palettes.py): light on bare :root, dark for the system setting
    # and for an explicit choice, on the root the host marks.
    colours = palettes.css()
    assert re.search(r":root \{\n  color-scheme: light dark;\n  --bg:", colours)
    assert '@media (prefers-color-scheme: dark) {\n:root:not([data-theme="light"])' in colours
    assert ':root[data-theme="dark"]' in colours
    assert "color-scheme: dark" in colours and re.search(r"body \{[^}]*background: var\(--bg\)", css)
    assert colours in app_page.render(_model()), "the palettes are in the page, ahead of the stylesheet"
    assert app_page.render(_model()).index("--bg:") < app_page.render(_model()).index("*, *::before")
    assert "padding-left: max(16px, env(safe-area-inset-left, 0px))" in css
    assert "padding-right: max(16px, env(safe-area-inset-right, 0px))" in css
    assert "@media (prefers-reduced-motion: reduce)" in css and ":focus-visible" in css
    assert "@media (prefers-contrast: more)" in css and "@media (forced-colors: active)" in css
    # Browser storage only inside try/catch, and nothing the person sees is an alert or a print.
    assert "localStorage" not in js.replace("window.localStorage", "")
    assert "function store(kind)" in js and "try { return kind" in js
    for banned in ("alert(", "confirm(", "prompt(", "window.print", ".innerHTML", "document.write"):
        assert banned not in js, banned
    assert "</script" not in js.lower() and "</style" not in css.lower()


def test_no_part_has_a_dash_of_the_kind_the_app_never_writes():
    for path in PARTS + [os.path.join(ROOT, "tools", "app_page.py"), FIXTURE]:
        text = open(path, encoding="utf-8").read()
        assert "—" not in text and "–" not in text, path


def test_a_model_of_the_wrong_shape_is_named_and_still_rendered():
    assert app_page.problems([]) == ["the model is not a JSON object"]
    got = app_page.problems({"model": 2, "ready": {}, "jobs": {"rows": "x"}, "person": []})
    assert "model is 2, the page reads version 1" in got
    assert "ready is not a list" in got and "jobs.rows is not a list" in got and "person is not an object" in got
    assert app_page.problems(_model()) == []
    assert "<title>Your job search</title>" in app_page.render({})


def test_the_command_writes_the_page_and_prints_the_capabilities(tmp_path):
    out = tmp_path / "page.html"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_page.py"), FIXTURE, "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert out.read_text(encoding="utf-8") == app_page.render(_model())
    caps = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_page.py"), "--capabilities"],
                          capture_output=True, text=True, encoding="utf-8")
    assert json.loads(caps.stdout) == app_page.capabilities()
    bad = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_page.py"), str(tmp_path / "missing.json")],
                         capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 2 and "cannot read" in bad.stderr


def test_the_fixture_is_the_contract_shape_with_invented_people_only():
    m = _model()
    for key in ("model", "made_at", "rev", "app", "person", "needs_you", "jobs", "ready", "messages",
                "due", "people", "interviews", "done", "settings", "brief"):
        assert key in m, key
    # A contact is a first name and an employer: no email, phone or profile address.
    text = json.dumps(m)
    assert "@" not in text and "linkedin.com/in/" not in text and not re.search(r"\+\d{2} ?\d{3}", text)
    assert {p["first_name"] for p in m["people"]} <= {"Juno", "Wren", "Tamsin", "Ash", "Ivo", "Sasha", "Marisol", "Bea", "Kit", "Rafe", "Noor", "Odile", "Pia"}
    # One person, one employer: the warm notes, the alerts and the contact book agree.
    at = {p["first_name"]: p["employer"] for p in m["people"]}
    assert len(at) == len(m["people"])
    for r in m["jobs"]["rows"]:
        for who, where in at.items():
            for text in [r.get("warm") or ""] + [a["text"] for a in r.get("alerts") or []]:
                if text.startswith(who + " "):
                    assert where in text, (who, text)
