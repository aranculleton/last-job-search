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
    stages with their seconds (page_db.STAGES), how much of Claude it takes
    (app_alerts.WORK_COST), and a note's facts in few words (app_model.WHERE_UNKNOWN)."""
    import app_alerts
    import app_model
    import page_db
    # The resume drafted alone is `draft` work, not a kind of its own: its stages are an
    # estimate beside them, its own minutes beside "Draft the resume only", and as much of
    # Claude as any draft (page_db.RESUME_ONLY_STAGES).
    return {"stages": {kind: [[name, secs] for _key, name, secs in rows]
                       for kind, rows in page_db.STAGES.items()},
            "estimates": {page_db.RESUME_ONLY_KIND: [[name, secs] for _key, name, secs
                                                     in page_db.RESUME_ONLY_STAGES]},
            "work_cost": dict(app_alerts.WORK_COST,
                              **{page_db.RESUME_ONLY_KIND: app_alerts.WORK_COST["draft"]}),
            # A note's facts said in a few words, and in a sentence behind its "?".
            "facts": {"where_unknown": list(app_model.WHERE_UNKNOWN)}}


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
# the files that changed.
#
# What changes together decides where a part ends. A part was a whole section of app.js (up to
# 60 KB), so 310 characters changed in one function re-read 59 KB, and a release re-read 480 to
# 706 KB for about 150 KB of changed code (the efficiency audit, E-1). Cut where a size fell,
# one line added early in a section moved every boundary after it. So a section is cut between
# its top-level declarations, and a part ends after a declaration whose own name says so (about
# one in PART_AIM, by a hash of the name, never of the code), once it holds PART_MIN: an edit
# inside one function changes the one part that holds it, and an added or removed declaration
# moves no boundary past the next named one. PART_CAP keeps parts small where no name ends
# one. Over the app's last three releases this re-reads 271, 390 and 200 KB against 569, 689
# and 468 (sections), with some 220 files against 76 (the parts load in parallel, in order).
#
# Sharing the code once instead, each person's page copying it from a page the app publishes
# (Artifact `files` {artifact, path}), was weighed first and set aside: the source has to be
# one the person can open, and a page is private to its owner by default (a stranger's chat
# cannot open the maintainer's, least of all from another organization); the tool's own rule
# is that Claude never publishes a file it has not read, which a copy made on the server skips;
# and it would make a second place the page's code comes from, outside the person's copy.

PART_MAX = 60 * 1024          # one Read of a few thousand tokens, far under its 256 KB limit
PART_CAP = 16 * 1024          # a part grows past this only by one declaration bigger than it
PART_MIN = 2 * 1024           # never ends a part smaller than this
PART_AIM = 3                  # about one top-level declaration in three ends a part, by name
# A published page holds at most 511 files a version, and the parts grow with the page's code
# (417 KB of app.js on 26 October, about 1.2 MB and 216 files on 11 November): at about 3 MB
# every republish would be refused (the review of 2026-11-11, E-1). Past FILES_MAX code files,
# the build makes its parts bigger (PART_MIN and PART_CAP doubled, up to PART_MAX) until they
# fit. Every boundary moves when it does, so that publish sends the whole code once.
FILES_MAX = 300

# The page version from which the page's code joins a big section's or a whole list's parts by
# what each holds (the second audit, D6), found by its own words in build_versions so it holds
# when the versions are numbered again. A page published before it joins only parts that carry
# the head's own rev, so until it is republished a page update writes its parts that way
# (`joins_by_hold`): sent the new way, a fresh load showed big sections and every "Show" list
# blank for the minutes between an update and its republish (the review of 2026-11-11).
JOINS_BY_HOLD = "a part of a long section or list holds what it holds"


def joins_by_hold() -> bool:
    """Does the published page's code join parts by what each holds? True where no page is
    published (nothing reads them yet) or its version is that one or later."""
    try:
        import app_setup
        import build_versions
        if not app_setup.page_record().get("url"):
            return True
        since = next((v[0] for v in build_versions.METHODS["page"]["versions"]
                      if JOINS_BY_HOLD in v[3]), None)
        return since is None or int(build_versions.recorded().get("page") or 1) >= since
    except Exception:  # noqa: BLE001  no profile: nothing published reads them
        return True


# The page version from which the page's code puts each item's links to the rest at its
# employer back on the item from the records kept apart (app_lists.links_docs; issue 254),
# found by its own words in build_versions. A page published before it shows no links on an
# item read from the database without them, so until then a page update writes them on the
# items, as before.
LINKS_APART = "each item's links to the rest at its employer are kept apart"


def reads_links_apart(held: int = 0) -> bool:
    """Does the published page's code put the links kept apart back on the items? True where no
    page is published, or its version is that one or later: as this copy recorded it, or as the
    page's own record says (`held`, meta/now `page`), where another chat published it since."""
    try:
        import app_setup
        import build_versions
        if not app_setup.page_record().get("url"):
            return True
        since = next((v[0] for v in build_versions.METHODS["page"]["versions"]
                      if LINKS_APART in v[3]), None)
        have = max(int(build_versions.recorded().get("page") or 1), int(held or 0))
        return since is not None and have >= since
    except Exception:  # noqa: BLE001  no profile: nothing published reads them
        return True


BATCH_MAX = 160 * 1024        # what one publish sends, so one agent reads it at a time
PAGE_MAX = 64 * 1024          # the small page, whatever the size of the search
_JS_HEAD = re.compile(r"^  // -{10,}\s*(.*)$")
_CSS_HEAD = re.compile(r"^/\* -{10,}\s*(.*?)(?:\*/)?\s*$")
_TOP_DECL = re.compile(r"^  (?:async function|function|const|let|class) ")
_DECL_NAME = re.compile(r"^  (?:async function|function|const|let|class)\s+([A-Za-z0-9_$]+)")


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


def _declarations(lines: list[str]) -> list[list[str]]:
    """A section's lines, one list for each top-level declaration (the section's own head and
    anything before its first declaration go with that first one)."""
    out, cur = [], []
    for ln in lines:
        if cur and _TOP_DECL.match(ln):
            out.append(cur)
            cur = []
        cur.append(ln)
    if cur:
        out.append(cur)
    return out


def _ends_part(first_line: str) -> str:
    """The declaration's name where it ends a part (about one in PART_AIM, by the name's own
    hash, so the same declaration always does), else ""."""
    import hashlib
    m = _DECL_NAME.match(first_line)
    if not m:
        return ""
    return m.group(1) if int(hashlib.md5(m.group(1).encode("utf-8")).hexdigest(), 16) \
        % PART_AIM == 0 else ""


_WORD = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_FUNC = re.compile(r"^  (?:async )?function\s+([A-Za-z0-9_$]+)")


def _safe_ends(decls: list[list[str]], texts: list[str]) -> list[bool]:
    """After which declarations a part may end. A function declaration is there from the
    start of its own script, so code that runs while the page loads (a const or a statement,
    as `const S = {model: readModel(), ...}`) may call one written after it in its section;
    in the next script it is not there yet. So a part never ends between such code and any
    function it reaches, directly or through other functions of its section. Read from the
    words alone, so it can only end parts less often than it might."""
    owner = {}
    for i, decl in enumerate(decls):
        m = _FUNC.match(decl[0]) if decl else None
        if m:
            owner[m.group(1)] = i
    words = [set(_WORD.findall(t)) for t in texts]
    reach = [0] * len(decls)
    for i, decl in enumerate(decls):
        if decl and _FUNC.match(decl[0]):
            continue                       # runs only when called
        seen, todo, far = set(), [w for w in words[i] if w in owner], i
        while todo:
            w = todo.pop()
            if w in seen:
                continue
            seen.add(w)
            far = max(far, owner[w])
            todo += [x for x in words[owner[w]] if x in owner and x not in seen]
        reach[i] = far
    out, most = [], -1
    for i in range(len(decls)):
        most = max(most, reach[i])
        out.append(most <= i)
    return out


def _cut(lines: list[str], part_min: int = PART_MIN,
         part_cap: int = PART_CAP) -> list[list[str]]:
    """A section cut into parts between its top-level declarations, each part ending after a
    declaration whose name ends one (_ends_part) once it holds `part_min`, or before a
    declaration that would take it past `part_cap`, wherever a part may end (_safe_ends): every
    piece is whole statements, and the same edit always lands in the same piece."""
    decls = _declarations(lines)
    texts = [compact_js("\n".join(d)) for d in decls]
    safe = _safe_ends(decls, texts)
    pieces, cur, size = [], [], 0
    for i, decl in enumerate(decls):
        n = len(texts[i].encode("utf-8")) + 1
        if cur and size + n > part_cap and (i == 0 or safe[i - 1]):
            pieces.append(cur)
            cur, size = [], 0
        cur += decl
        size += n
        if size >= part_min and safe[i] and _ends_part(decl[0]):
            pieces.append(cur)
            cur, size = [], 0
    if cur:
        pieces.append(cur)
    return pieces


def _piece_name(section: str, piece: list[str], first: bool) -> str:
    """A part's name: its section's, and after the first, the declaration it opens with, so a
    part keeps its name while its code is unchanged, wherever it falls in the section."""
    head = _slug(section)[:24].rstrip("-")
    if first:
        return head
    m = _DECL_NAME.match(next((ln for ln in piece if _TOP_DECL.match(ln)), ""))
    return f"{head} {m.group(1) if m else 'part'}"


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
    sections = _sections(body, _JS_HEAD, "start")
    room = FILES_MAX - len(css_parts())
    part_min, part_cap = PART_MIN, PART_CAP
    while True:
        parts = []
        for name, sec in sections:
            for piece in _cut(sec, part_min, part_cap):
                text = compact_js("\n".join(piece))
                if not text.strip():
                    continue
                # Grown past FILES_MAX: a section's last part under part_min joins the next
                # section's first, so many small sections are not a file each.
                if part_min > PART_MIN and parts and _size(parts[-1][1]) < part_min and \
                        _size(parts[-1][1]) + _size(text) <= part_cap:
                    parts[-1] = (parts[-1][0], parts[-1][1] + "\n" + text, name)
                    continue
                parts.append((_piece_name(name, piece, not parts or parts[-1][2] != name),
                              text, name))
        if len(parts) <= room or part_min >= PART_MAX:
            break
        # More files than a version may hold with the rest: bigger parts (FILES_MAX), the
        # smallest a part may end at as well as the biggest, both up to PART_MAX: a cap at
        # its most with the floor still low left 280 parts of a page four times today's.
        part_min, part_cap = min(part_min * 2, PART_MAX), min(part_cap * 2, PART_MAX)
    return _named("js", [(n, '"use strict";\n' + t + "\n") for n, t, _sec in parts], "js")


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def css_parts() -> list[tuple[str, str]]:
    """The palettes, then app.css cut at its section headings, in the order they cascade."""
    parts = [("palettes", palettes.css())]
    for name, sec in _sections(_read("app.css").split("\n"), _CSS_HEAD, "start"):
        text = compact_css("\n".join(sec))
        if text.strip():
            parts.append((name, text + "\n"))
    return _named("css", parts, "css")


# The sections the page takes from its own store (app.py view writes each as view/<name>):
# the page in parts carries everything else, and these come from there.
def _from_store() -> set:
    import app_model
    return (set(app_model.SECTIONS) | {"people_count", "coming_up", "lists", "listener",
                                       "schedule"}) - {"person"}


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
    # The page is read once, before the first publish, and named again, unchanged, by every
    # publish after it: it counts in the first alone (it was read in all nine of a first
    # publish, E-1).
    batches: list[list[str]] = [[]]
    size = built["sizes"]["page.html"]
    for p in new:
        if batches[-1] and size + built["sizes"][p] > BATCH_MAX:
            batches.append([])
            size = 0
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
