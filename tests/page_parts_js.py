"""The page's own readers of a section or list in parts, run in node on what `app.py view`
writes: `joined` (a big section, view/part~<section>~<n>) and `fullList` (a whole list behind
"Show", view/list~<name>~<n>), taken word for word from the page's code given, so a test can
read the store as the page does, whether that code is this copy's or an older page's.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, "templates", "app", "app.js")

# The helpers the two readers call, as app.js defines them.
_HELPERS = """
const txt = (s) => (s === null || s === undefined ? "" : String(s));
const arr = (x) => (Array.isArray(x) ? x : []);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : {});
"""


def node() -> str:
    return shutil.which("node") or ""


def function(js: str, name: str) -> str:
    """The top-level function `name` of the page's code, whole: from its line to the first
    line after it that closes it at the same depth."""
    lines = js.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"  function {name}("))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "  }")
    return "\n".join(lines[start:end + 1])


def constant(js: str, name: str) -> str:
    """The top-level one-line `const <name> = ...;` of the page's code."""
    return next(ln for ln in js.split("\n") if ln.startswith(f"  const {name} = "))


def read(views: dict, sections=(), lists=(), js: str | None = None,
         linked: bool = False) -> dict:
    """{"sections": {name: what joined(name, head) gives, or None}, "lists": {name: what
    fullList(name) gives}} for `views` ({doc id: the document's fields}), on a fresh page
    (nothing kept from before), with `js` the page's code (this copy's app.js by default).
    `linked`: each section as the page draws it, whole or joined, with every item's links put
    back from the records kept apart (withLinks)."""
    if js is None:
        with open(APP_JS, encoding="utf-8") as fh:
            js = fh.read()
    take = ("for (const k of want.sections) { const v = S.views.get(k);"
            " const got = v ? joined(k, v) : undefined; out.sections[k] = got === undefined ? null : got; }")
    if linked:
        take = ("const m = {}; for (const k of want.sections) { const v = S.views.get(k);"
                " const got = !v ? undefined : v.data !== undefined ? v.data : joined(k, v);"
                " if (got !== undefined) m[k] = got; }"
                " const drawn = withLinks(m);"
                " for (const k of want.sections) out.sections[k] = drawn[k] === undefined ? null : drawn[k];")
    script = "\n".join([
        _HELPERS,
        "const given = JSON.parse(require('fs').readFileSync(0, 'utf8'));",
        "const S = {views: new Map(Object.entries(given.views))};",
        "const joinedKept = new Map();", "const fullKept = new Map();",
        function(js, "joined"), function(js, "fullList"),
        *((constant(js, "LINKED"), constant(js, "linkedKept"), function(js, "withLinks"))
          if linked else ()),
        "const want = given.want;",
        "const out = {sections: {}, lists: {}};",
        take,
        "for (const k of want.lists) out.lists[k] = fullList(k);",
        "process.stdout.write(JSON.stringify(out));"])
    given = {"views": views, "want": {"sections": list(sections), "lists": list(lists)}}
    got = subprocess.run([node(), "-e", script], input=json.dumps(given), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert got.returncode == 0, got.stderr
    return json.loads(got.stdout)
