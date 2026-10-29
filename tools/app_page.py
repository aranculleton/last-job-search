#!/usr/bin/env python3
"""The person's page: one view model in, one HTML document out, ready to publish.

After setup the person does everything on one private Claude page (an Artifact): their
shortlist, documents, messages, follow-ups, interviews, the work running for them, their
settings, and a conversation with Claude. This renders that page from the view model
`tools/app.py model` builds (the contract's section 1) into ONE self-contained document:
the palettes, the stylesheet and the script inline, the model embedded as JSON in a script
tag, and nothing fetched from anywhere: no script, stylesheet or font, so the page shows in
the device's own type.

The page shows the embedded model at once, with no capability at all, and lights up its
live parts (the shared store, downloads, quick answers, ringing a chat) as the viewer's
capabilities resolve. Nothing on it sends or submits anything for the person.

    python3 tools/app_page.py <model.json> --out page.html     # the page to publish
    python3 tools/app_page.py <model.json> --out p.html --standalone
                                                # wrapped as the Artifact tool wraps it,
                                                # for a browser or a test
    python3 tools/app_page.py --capabilities    # what to publish it with, as JSON

The parts live in templates/app/ (page.html, app.css, app.js, and palettes.py, the one
place a colour is written) so each can be read and tested on its own. Python 3.9, standard
library only.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(ROOT, "templates", "app")
sys.path.insert(0, TEMPLATE_DIR)
import palettes  # noqa: E402
CONTRACT_VERSION = 1

# The small reset the Artifact tool's skeleton carries, repeated for a standalone copy so a
# browser or a test sees the page exactly as a viewer would.
_SKELETON_RESET = (
    ":root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);"
    "padding-bottom:env(safe-area-inset-bottom,0px)}"
    "body{margin:0;font:14px system-ui,-apple-system,sans-serif}"
    "img{max-width:100%}[hidden]{display:none!important}"
)


def capabilities() -> dict:
    """The capabilities the page is published with, exactly.

    db: owner-only, read and write, at the root, so a person the page is shared with reads
    nothing, and again on reach/, where each contact's address is kept for the owner; user: to know the owner; downloads: each document saved as a file; comments,
    full form: the doorbell that wakes a chat, rung in the tap; sample:
    quick answers on the page; assets: the documents' PDFs, uploaded by a chat and read
    back by the page, the LinkedIn download and a resume the person adds, and the pictures
    they add to the chat, which the chat that answers reads by id; mcp: Claude's
    own browser on the person's computer (host:claude_browser), which answers only when the
    page is open in the Claude desktop app, with the four tools reading a profile needs.
    """
    return {
        # addr/part~<n> (reach/<contact> before 4.3), each contact's LinkedIn address or email
        # for Open profile and Open in email, is named too, so it stays the owner's alone
        # whatever the root rule says.
        "db": {"rules": [{"path": "", "read": "owner", "write": "owner"},
                         {"path": "reach", "read": "owner", "write": "owner"},
                         {"path": "addr", "read": "owner", "write": "owner"}]},
        "user": {},
        "downloads": True,
        "comments": {},
        "sample": {},
        "assets": {},
        # Claude's own browser in the desktop app, for reading LinkedIn. The page wakes its
        # chat with the comment doorbell, rung in the tap: the "Claude Code Remote" connector
        # it used for a day could not even load on the maintainer's account, and asked on
        # every tap (live check, 2026-10-29).
        "mcp": {"servers": [{"server": "host:claude_browser",
                             "tools": ["navigate", "get_page_text", "read_page", "preview_start"]}]},
    }


def _read(name: str) -> str:
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def embed_json(model: dict) -> str:
    """The model as JSON that cannot end the script tag it sits in, or open a comment."""
    text = json.dumps(model, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return (text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def title_for(model: dict) -> str:
    first = str(((model.get("person") or {}).get("first_name") or "")).strip()
    return f"{first}\u2019s job search" if first else "Your job search"


def problems(model: object) -> list:
    """What in a model the page cannot use as given. The page still renders what it can."""
    if not isinstance(model, dict):
        return ["the model is not a JSON object"]
    out = []
    if model.get("model") != CONTRACT_VERSION:
        out.append(f"model is {model.get('model')!r}, the page reads version {CONTRACT_VERSION}")
    lists = ("needs_you", "ready", "messages", "due", "people", "interviews", "settings")
    for key in lists:
        if key in model and not isinstance(model[key], list):
            out.append(f"{key} is not a list")
    for key in ("app", "person", "jobs", "done", "brief"):
        if key in model and model[key] is not None and not isinstance(model[key], dict):
            out.append(f"{key} is not an object")
    jobs = model.get("jobs") or {}
    if isinstance(jobs, dict) and "rows" in jobs and not isinstance(jobs["rows"], list):
        out.append("jobs.rows is not a list")
    return out


def tables() -> dict:
    """The engine's own tables the page reads, so the two never drift: each kind of work's
    stages with their seconds (page_db.STAGES) and how much of Claude it takes
    (app_alerts.WORK_COST)."""
    import app_alerts
    import page_db
    return {"stages": {kind: [[name, secs] for _key, name, secs in rows]
                       for kind, rows in page_db.STAGES.items()},
            "work_cost": dict(app_alerts.WORK_COST)}


def compact_js(js: str) -> str:
    """The script without its comment-only lines, its block comments and its indentation.

    A chat reads the whole page before it publishes it, so every byte here is read on each
    republish (the maintainer, 2026-10-29: "every single process ... cheap"). Only what a
    browser never runs goes: app.js holds no template literal (tests/test_the_page_is_one_
    safe_document.py keeps it so), so no line can be inside a string that spans lines, and a
    line opening with // or /* is a comment wherever it sits. Code and line breaks stay as
    written, so automatic semicolons fall exactly where they did."""
    out, in_block = [], False
    for line in js.split("\n"):
        t = line.strip()
        if in_block:
            if "*/" in t:
                in_block = False
                rest = t.split("*/", 1)[1].strip()
                if rest:
                    out.append(rest)
            continue
        if not t or t.startswith("//"):
            continue
        if t.startswith("/*"):
            if "*/" not in t[2:]:
                in_block = True
                continue
            rest = t[2:].split("*/", 1)[1].strip()
            if rest:
                out.append(rest)
            continue
        out.append(t)
    return "\n".join(out)


def compact_css(css: str) -> str:
    """The stylesheet without comments, indentation or blank lines (see compact_js)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return "\n".join(t for t in (ln.strip() for ln in css.split("\n")) if t)


def render(model: dict) -> str:
    """The page, as the Artifact tool publishes it: content only, no doctype or head."""
    css = compact_css(_read("app.css"))
    colours = palettes.css()
    js = compact_js(_read("app.js"))
    page = _read("page.html")
    if "</style" in css.lower() or "</style" in colours.lower():
        raise ValueError("the stylesheets must not contain a closing style tag")
    if "</script" in js.lower():
        raise ValueError("app.js must not contain a closing script tag")
    fill = {"TITLE": html.escape(title_for(model), quote=False), "PALETTES": colours, "CSS": css,
            "JS": js, "MODEL": embed_json(model), "TABLES": embed_json(tables())}
    # One pass over the template: what a value holds is never read as a placeholder.
    return re.sub(r"\{\{(TITLE|PALETTES|CSS|JS|MODEL|TABLES)\}\}", lambda m: fill[m.group(1)], page)


def standalone(page: str) -> str:
    """The page wrapped the way the Artifact tool wraps it, for a browser or a test."""
    return ("<!doctype html><html><head><meta charset=utf8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            f"<style>{_SKELETON_RESET}</style></head><body>{page}</body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the person's page from a view model.")
    ap.add_argument("model", nargs="?", help="the view model JSON (tools/app.py model)")
    ap.add_argument("--out", help="where to write the page (default: print it)")
    ap.add_argument("--standalone", action="store_true", help="wrap it as the Artifact tool does")
    ap.add_argument("--capabilities", action="store_true", help="print the capabilities to publish with")
    a = ap.parse_args(argv)
    if a.capabilities:
        print(json.dumps(capabilities(), indent=2))
        return 0
    if not a.model:
        ap.print_usage(sys.stderr)
        return 2
    try:
        with open(a.model, encoding="utf-8") as fh:
            model = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"app_page: cannot read {a.model}: {e}", file=sys.stderr)
        return 2
    for p in problems(model):
        print(f"app_page: {p}", file=sys.stderr)
    if not isinstance(model, dict):
        return 2
    page = render(model)
    if a.standalone:
        page = standalone(page)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page)
        print(f"app_page: wrote {a.out} ({len(page.encode('utf-8')) // 1024} KB)")
    else:
        sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
