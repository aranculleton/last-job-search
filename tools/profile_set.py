#!/usr/bin/env python3
"""One setting in the person's profile, written the way they would by hand, and taken back.

The page's Tweak panel and its "Keep this for next time" change the person's settings:
a line in profile/search.py, networking.py or boards.py (`NAME = value`), or a key in
person.json (`documents.design`, `brief.news`). Each was edited by hand, or by one writer
for one setting (app_actions._set_plan for LINKEDIN_PLAN). This is that writer for any
of them, with the same rules: the value is a plain literal (text, a number, a list or a
dict of them) and is read back to check it parses; a setting of the screening rules
(exclude.GATE_NAMES) says how many earlier rulings it lapsed; every write returns what
was there before, so `restore` puts it back exactly.

    python3 tools/profile_set.py get search.py SCRAPE_PAGES
    python3 tools/profile_set.py set search.py SCRAPE_PAGES 3
    python3 tools/profile_set.py json documents.style navy
"""
from __future__ import annotations

import ast
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import person  # noqa: E402

FILES = ("search.py", "networking.py", "boards.py")
MISSING = {"missing": True}


class Refused(ValueError):
    """A setting that cannot be written as asked, said in plain words."""


def _source(value) -> str:
    """A value as a profile file writes it: double-quoted text, as the files are written."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_source(v) for v in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(_source(v) for v in value) + ("," if len(value) == 1 else "") + ")"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_source(k)}: {_source(v)}" for k, v in value.items()) + "}"
    return repr(value)


def _literal(value):
    """The value, if it is a plain literal a profile file may hold."""
    try:
        text = _source(value)
        back = ast.literal_eval(text)
    except (ValueError, SyntaxError) as e:
        raise Refused(f"that is not a value a setting can hold: {e}") from e
    if back != value:
        raise Refused("that value does not read back as itself")
    return text


def _path(name: str) -> str:
    if name not in FILES:
        raise Refused(f"settings live in {', '.join(FILES)}, not {name}")
    return person.path(name)


def _node(tree, key: str):
    for n in tree.body:
        targets = n.targets if isinstance(n, ast.Assign) else [n.target] \
            if isinstance(n, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == key for t in targets):
            return n
    return None


def get(name: str, key: str):
    """The setting's value as the file has it, or MISSING; one that is not a plain literal
    (a pattern, an expression) is None and cannot be written here."""
    path = _path(name)
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return MISSING
    n = _node(ast.parse(src), key)
    if n is None:
        return MISSING
    try:
        return ast.literal_eval(n.value)
    except ValueError:
        return None


def set_line(name: str, key: str, value) -> dict:
    """Write `KEY = value` into profile/<name>, in place of the line or lines it was, or at
    the end. Returns {"file", "key", "before"}: the text of the lines it replaced, or None
    when the setting was not there."""
    path = _path(name)
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        src = ""
    text = f"{key} = {_literal(value)}"
    tree = ast.parse(src)
    n = _node(tree, key)
    lines = src.splitlines(keepends=True)
    before = None
    if n is not None:
        try:
            ast.literal_eval(n.value)
        except ValueError:
            raise Refused(f"{key} in {name} is written as code, not a plain value: change it "
                          "by hand") from None
        start, end = n.lineno - 1, n.end_lineno
        before = "".join(lines[start:end])
        lines[start:end] = [text + "\n"]
        out = "".join(lines)
    else:
        out = src.rstrip("\n") + ("\n\n" if src.strip() else "") + text + "\n"
    ast.parse(out)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    person.reset()
    return {"file": name, "key": key, "before": before, "lapsed": _lapsed(name, key)}


def restore(record: dict) -> None:
    """Put back what set_line replaced: the very lines, or no line at all."""
    path = _path(record["file"])
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    n = _node(tree, record["key"])
    if n is None:
        return
    lines = src.splitlines(keepends=True)
    start, end = n.lineno - 1, n.end_lineno
    lines[start:end] = [record["before"]] if record.get("before") else []
    out = "".join(lines)
    ast.parse(out)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    person.reset()


def _lapsed(name: str, key: str) -> int | None:
    """How many earlier rulings rest on this setting, now looked at again, for a setting of
    the screening rules; None for any other."""
    if name != "search.py":
        return None
    try:
        import exclude
        if key not in exclude.GATE_NAMES:
            return None
        return sum(len(es) for _g, es in exclude.lapsed())
    except Exception:  # noqa: BLE001
        return None


def get_json(key):
    """A person.json value by dotted key (or a list of keys), MISSING when it is not set."""
    path = person.path("person.json")
    with open(path, encoding="utf-8") as fh:
        here = json.load(fh)
    for p in (key if isinstance(key, list) else key.split(".")):
        if not isinstance(here, dict) or p not in here:
            return MISSING
        here = here[p]
    return here


def set_json(key, value) -> dict:
    """One dotted key in person.json ("brief.news", "documents.design"), or a list of keys
    for a name with a dot in it; None removes it. Returns {"json", "key", "before"}
    (MISSING when it was not set)."""
    if value is not None:
        _literal(value)
    before = person.put(key, person.REMOVE if value is None else value)
    return {"json": True, "key": key, "before": MISSING if before is person.MISSING else before}


def undo(record: dict) -> None:
    """Take back a set_line or set_json."""
    if record.get("json"):
        before = record.get("before")
        set_json(record["key"], None if before == MISSING or before is None else before)
    else:
        restore(record)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 3 and argv[0] == "get":
        print(json.dumps(get(argv[1], argv[2])))
        return 0
    if len(argv) >= 4 and argv[0] == "set":
        try:
            value = json.loads(argv[3])
        except ValueError:
            value = argv[3]
        print(json.dumps(set_line(argv[1], argv[2], value)))
        return 0
    if len(argv) >= 3 and argv[0] == "json":
        try:
            value = json.loads(argv[2])
        except ValueError:
            value = argv[2]
        print(json.dumps(set_json(argv[1], value)))
        return 0
    print(__doc__.strip().split("\n\n")[-1])
    return 2


if __name__ == "__main__":
    sys.exit(main())
