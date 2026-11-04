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


# ------------------------------------------------------------------ the page in parts
#
# The page as one document was 0.7 to 1.6 MB, 95% of it the app's own script and stylesheet,
# and the Artifact tool has a chat read every file it did not write, whole, before it
# publishes it ("If Claude cannot read the file, it does not publish it"). So the first
# publish cost about 200,000 tokens, every republish the same again, and a chat whose window
# holds 200,000 could not publish at all (the stranger audit, 3 November, X-3). The parts
# shape fixes that at the cause: the page Claude publishes is a small document (who it is
# for, the engine's tables and the list of its code files), the search itself reaches it
# through its own store (`app.py view` writes every section there already), and the code is
# supporting files, one for each section of app.js and app.css, named by what they hold. A
# file the published page already holds is left out of the next publish, and the Artifact
# tool keeps it ("files it leaves out are kept"), so a republish reads the small page and only
# the files that changed, and a change to one section is one small file.

PART_MAX = 60 * 1024          # one Read of a few thousand tokens, far under its 256 KB limit
BATCH_MAX = 160 * 1024        # what one publish sends, so one agent reads it at a time
PAGE_MAX = 64 * 1024          # the small page, whatever the size of the search
_JS_HEAD = re.compile(r"^  // -{10,}\s*(.*)$")
_CSS_HEAD = re.compile(r"^/\* -{10,}\s*(.*?)(?:\*/)?\s*$")
_TOP_DECL = re.compile(r"^  (?:async function|function|const|let|class) ")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40].rstrip("-")) or "part"


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _sections(lines: list[str], head: "re.Pattern", first: str) -> list[tuple[str, list[str]]]:
    out, name, cur = [], first, []
    for ln in lines:
        m = head.match(ln)
        if m and cur:
            out.append((name, cur))
            cur = []
        if m:
            name = m.group(1) or "part"
        cur.append(ln)
    if cur:
        out.append((name, cur))
    return out


def _cut(lines: list[str], fits) -> list[list[str]]:
    """A section too big for one part, cut where a top-level declaration starts, so each
    piece is still whole statements and the same edit always lands in the same piece."""
    pieces, cur = [], []
    for ln in lines:
        if cur and _TOP_DECL.match(ln) and not fits(cur + [ln]):
            pieces.append(cur)
            cur = []
        cur.append(ln)
    if cur:
        pieces.append(cur)
    return pieces


def _named(kind: str, parts: list[tuple[str, str]], ext: str) -> list[tuple[str, str]]:
    out, used = [], {}
    for name, text in parts:
        slug = _slug(name)
        used[slug] = used.get(slug, 0) + 1
        if used[slug] > 1:
            slug = f"{slug}-{used[slug]}"
        out.append((f"code/{kind}/{slug}.{_hash(text)}.{ext}", text))
    return out


def js_parts() -> list[tuple[str, str]]:
    """app.js as classic scripts, in order, sharing one scope: the page's own closure opened
    out, so a top-level name in one is seen by the next (a classic script's const, let and
    function are the window's own scope), cut at its section headings."""
    lines = _read("app.js").split("\n")
    try:
        start = lines.index("(function () {")
        end = len(lines) - 1 - lines[::-1].index("})();")
    except ValueError as e:
        raise ValueError("app.js must open with (function () { and end with })();") from e
    body = [ln for ln in lines[start + 1:end] if ln.strip() != '"use strict";']
    parts = []
    for name, sec in _sections(body, _JS_HEAD, "start"):
        fits = lambda ls: len(compact_js("\n".join(ls)).encode("utf-8")) <= PART_MAX  # noqa: E731
        pieces = [sec] if fits(sec) else _cut(sec, fits)
        for i, piece in enumerate(pieces):
            text = compact_js("\n".join(piece))
            if text.strip():
                parts.append((name if i == 0 else f"{name} {i + 1}", '"use strict";\n' + text + "\n"))
    return _named("js", parts, "js")


def css_parts() -> list[tuple[str, str]]:
    """The palettes, then app.css cut at its section headings, in the order they cascade."""
    parts = [("palettes", palettes.css())]
    for name, sec in _sections(_read("app.css").split("\n"), _CSS_HEAD, "start"):
        text = compact_css("\n".join(sec))
        if text.strip():
            parts.append((name, text + "\n"))
    return _named("css", parts, "css")


def code_files() -> dict:
    """{published path: its text} for every code file the page in parts loads."""
    return dict(css_parts() + js_parts())


# The sections the page takes from its own store (app.py view writes each as view/<name>):
# the page in parts carries everything else, and these come from there.
def _from_store() -> set:
    import app_model
    return (set(app_model.SECTIONS) | {"people_count", "lists", "listener", "schedule"}) - {"person"}


def slim(model: dict) -> dict:
    """The model the page in parts embeds: who it is for and what the store never carries.
    With no `made_at`, the page takes every section its store holds (app.js recompute)."""
    keep = {k: v for k, v in model.items() if k not in _from_store() and k != "made_at"}
    keep["slim"] = True
    return keep


def render_parts(model: dict, built: str | None = None) -> tuple[str, dict]:
    """(the small page, {published path: text}) for the page in parts. `built` is the moment
    it was built (the model's own `made_at` unless given), which the page carries."""
    css, js = css_parts(), js_parts()
    page = _read("page.html")
    # The guard first, inline: a code file that does not arrive or throws while the page
    # starts is said in one line with one button that asks for the whole page again
    # (templates/app/guard.js), and the last line tells it every file has run. It carries
    # when the page was built: a republish goes up in batches, each with this page, so a
    # file missing minutes after the build is one still on its way, not a page that failed.
    when = str(built or (model.get("made_at") if isinstance(model, dict) else "") or "")
    stamp = f' data-built="{html.escape(when)}"' if when else ""
    guard = f"<script{stamp}>\n{compact_js(_read('guard.js')).strip()}\n</script>\n"
    links = guard + "\n".join(f'<link rel="stylesheet" href="{p}">' for p, _ in css)
    scripts = "\n".join(f'<script src="{p}"></script>' for p, _ in js) + \
        "\n<script>window.__ljsGuard && window.__ljsGuard.end();</script>"
    for old, new in (("<style>\n{{PALETTES}}\n</style>\n<style>\n{{CSS}}\n</style>", links),
                     ("<script>\n{{JS}}\n</script>", scripts)):
        if old not in page:
            raise ValueError(f"page.html no longer holds {old.splitlines()[1]} as the parts expect")
        page = page.replace(old, new)
    fill = {"TITLE": html.escape(title_for(model), quote=False), "MODEL": embed_json(slim(model)),
            "TABLES": embed_json(tables())}
    page = re.sub(r"\{\{(TITLE|MODEL|TABLES)\}\}", lambda m: fill[m.group(1)], page)
    return page, dict(css + js)


def write_parts(model: dict, out_dir: str) -> dict:
    """Write the page in parts under `out_dir` (page.html, code/...). {"page": its path,
    "files": {published path: local path}, "sizes": {published path: bytes}}."""
    page, files = render_parts(model)
    os.makedirs(out_dir, exist_ok=True)
    out = {"page": os.path.join(out_dir, "page.html"), "files": {}, "sizes": {}}
    with open(out["page"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    out["sizes"]["page.html"] = len(page.encode("utf-8"))
    for rel, text in files.items():
        path = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        out["files"][rel] = path
        out["sizes"][rel] = len(text.encode("utf-8"))
    return out


def caps_hash() -> str:
    """What the page's capabilities are, as one short word: a publish passes them only when
    the published page was declared with others (or none were recorded), since a redeploy
    that leaves them out keeps them, and one that declares them asks the person first."""
    return _hash(json.dumps(capabilities(), sort_keys=True))


def on_page(listing: str) -> dict:
    """{published path: bytes} for each code file a listing of the published page names
    (Artifact, action list, scope files: `- "code/js/x.1a2b3c4d5e.js"  text/javascript
    1234 bytes`, as the host printed it on 2026-11-04). A path with no size is None."""
    out: dict = {}
    for m in re.finditer(r'"?(code/[A-Za-z0-9._/-]+\.(?:js|css))"?(?:[ \t]+\S+[ \t]+(\d+) bytes)?',
                         listing):
        out[m.group(1)] = int(m.group(2)) if m.group(2) else None
    return out


def plan(built: dict, held: list | None, caps: str = "", url: str = "",
         listed: dict | None = None, whole: bool = False) -> dict:
    """What to publish: {"new": [paths the page lacks], "gone": [paths it holds and no longer
    loads], "missing": [paths it should hold and does not], "batches": [[paths], ...],
    "capabilities": bool}. `held` is what the published page holds (profile/app.json
    `code`), None for a page never published in parts. `listed` is what the host says it
    holds (on_page), which wins over the record: a file the record names and the host lacks,
    or holds at another size, goes up again. `whole`: every code file goes up again."""
    have = set(held or [])
    missing: list = []
    if listed is not None:
        sizes = built["sizes"]
        good = {p for p, n in listed.items() if n is None or n == sizes.get(p, n)}
        missing = sorted(p for p in built["files"] if p in have and p not in good)
        have = good
    new = [p for p in built["files"] if whole or p not in have]
    gone = sorted((set(listed) if listed is not None else have) - set(built["files"])) if url else []
    batches: list[list[str]] = [[]]
    size = built["sizes"]["page.html"]
    for p in new:
        if batches[-1] and size + built["sizes"][p] > BATCH_MAX:
            batches.append([])
            size = built["sizes"]["page.html"]
        batches[-1].append(p)
        size += built["sizes"][p]
    return {"new": new, "gone": gone, "missing": missing, "batches": batches,
            "capabilities": not url or caps != caps_hash()}


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
