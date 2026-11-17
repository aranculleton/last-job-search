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
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import person  # noqa: E402

FILES = ("search.py", "networking.py", "boards.py", "employers.py")
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


def _comments(text: str) -> list[str]:
    """Every comment in `text`, in order, as written."""
    import io
    import tokenize
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def _same(a, b) -> bool:
    """Equal and of the same type, all the way down: True is not 1, nor 1.0 (`==` says so)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _in_place(src: str, n, value) -> str | None:
    """`src` with a dict setting changed entry by entry, so every comment on and between its
    entries stays where the person wrote it: `PORTALS = {"adzuna-search": False,  # why}` keeps
    its why when it is turned on. None where that cannot be done (not a dict both ways, an
    entry taken away, a key that is not plain text): the caller writes the line whole."""
    node = n.value
    if not (isinstance(node, ast.Dict) and isinstance(value, dict)):
        return None
    try:
        keys = [ast.literal_eval(k) if k is not None else None for k in node.keys]
        old = [ast.literal_eval(v) for v in node.values]
    except ValueError:
        return None
    if None in keys or any(k not in value for k in keys):
        return None
    data = src.encode("utf-8")
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def at(line, col):           # ast's offsets are a line and a byte within it
        return starts[line - 1] + col

    edits = [(at(v.lineno, v.col_offset), at(v.end_lineno, v.end_col_offset),
              _literal(value[k]).encode("utf-8"))
             for k, v, was in zip(keys, node.values, old) if not _same(value[k], was)]
    added = [k for k in value if k not in keys]
    if added:
        close = at(node.end_lineno, node.end_col_offset) - 1         # the closing brace
        last = at(node.values[-1].end_lineno, node.values[-1].end_col_offset) if keys else None
        between = data[last:close].decode("utf-8") if keys else ""
        comma = "," in re.sub(r"#[^\n]*", "", between)
        entries = [f"{_literal(k)}: {_literal(value[k])}" for k in added]
        line0 = starts[node.end_lineno - 1]
        if node.lineno != node.end_lineno and not data[line0:close].strip():
            # One entry a line, as the person wrote them, before the line with the brace.
            pad = " " * (node.keys[0].col_offset if keys else node.col_offset + 4)
            if keys and not comma:
                edits.append((last, last, b","))
            edits.append((line0, line0, "".join(f"{pad}{e},\n" for e in entries).encode("utf-8")))
        else:
            lead = "" if not keys else " " if comma else ", "
            edits.append((close, close, (lead + ", ".join(entries)).encode("utf-8")))
    for a, b, text in sorted(edits, key=lambda e: e[0], reverse=True):
        data = data[:a] + text + data[b:]
    out = data.decode("utf-8")
    try:
        got = _node(ast.parse(out), n.targets[0].id if isinstance(n, ast.Assign) else n.target.id)
        if got is None or not _same(ast.literal_eval(got.value), value):
            return None
    except (SyntaxError, ValueError):
        return None
    return out


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
    above = 0
    if n is not None:
        try:
            ast.literal_eval(n.value)
        except ValueError:
            raise Refused(f"{key} in {name} is written as code, not a plain value: change it "
                          "by hand") from None
        start, end = n.lineno - 1, n.end_lineno
        before = "".join(lines[start:end])
        out = _in_place(src, n, value)
        if out is None:
            # Every comment the old lines held is kept, above the new line: turning a job site
            # on put a bare line where the person's note said why it was off (the maintainer,
            # 2026-11-06).
            kept = _comments(before)
            if len(kept) == 1 and n.lineno == n.end_lineno:
                # One line with its note after it keeps it there: `X = 21  # why`.
                lines[start:end] = [f"{text}  {kept[0]}\n"]
                kept = []
            else:
                lines[start:end] = [c + "\n" for c in kept] + [text + "\n"]
            above = len(kept)
            out = "".join(lines)
    else:
        out = src.rstrip("\n") + ("\n\n" if src.strip() else "") + text + "\n"
    ast.parse(out)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    person.reset()
    out = {"file": name, "key": key, "before": before, "lapsed": _lapsed(name, key)}
    if above:
        out["above"] = above        # the comments moved above the line, which restore takes back
    return out


# ------------------------------------------------------------------ one entry of a list

def _container(n):
    """The literal holding a setting's entries: a list, set, tuple or dict, or one given to
    set() or frozenset(); None where it is written as other code."""
    node = n.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("set", "frozenset") and not node.keywords):
        if not node.args:
            return node
        node = node.args[0] if len(node.args) == 1 else None
    return node if isinstance(node, (ast.List, ast.Set, ast.Tuple, ast.Dict)) else None


def _byte_at(data: bytes):
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return lambda line, col: starts[line - 1] + col


def _read(name: str) -> tuple[str, str]:
    path = _path(name)
    with open(path, encoding="utf-8") as fh:
        return path, fh.read()


def _write(path: str, out: str) -> None:
    ast.parse(out)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    person.reset()


def drop_entries(name: str, key: str, drop) -> list[dict]:
    """Take each entry `drop(entry)` says yes to out of the list, set or dict `KEY` in
    profile/<name>, where it is written, so every other entry and every comment stays as the
    person wrote it (a dict's entry is asked about by its key). Returns what came out, each
    {"entry", "src"}: `src` its text as it was written, which `add_entries` puts back. A
    setting written as code is Refused, naming it; one not there drops nothing."""
    try:
        path, src = _read(name)
    except OSError:
        return []
    n = _node(ast.parse(src), key)
    if n is None:
        return []
    node = _container(n)
    if node is None:
        raise Refused(f"{key} in {name} is written as code, not a plain list: change it by hand")
    if isinstance(node, ast.Call):                   # set() with nothing in it
        return []
    data = src.encode("utf-8")
    at = _byte_at(data)
    items = (list(zip(node.keys, node.values)) if isinstance(node, ast.Dict)
             else [(e, e) for e in node.elts])
    gone, spans = [], []
    for first, last in items:
        if first is None:                            # a `**other` inside a dict
            continue
        try:
            entry = ast.literal_eval(first)
        except ValueError:
            continue
        if not drop(entry):
            continue
        a, b = at(first.lineno, first.col_offset), at(last.end_lineno, last.end_col_offset)
        gone.append({"entry": entry, "src": data[a:b].decode("utf-8")})
        # The comma after it goes with it, and the whole line where nothing else is on it.
        end = b
        while end < len(data) and data[end:end + 1] in (b" ", b"\t"):
            end += 1
        if data[end:end + 1] == b",":
            end += 1
            while end < len(data) and data[end:end + 1] in (b" ", b"\t"):
                end += 1
        else:
            # The last entry, with no comma after it: the comma before it goes instead, so
            # `["a", "b"]` is `["a"]`, never `["a", ]`.
            back = a
            while back > 0 and data[back - 1:back] in (b" ", b"\t"):
                back -= 1
            if data[back - 1:back] == b",":
                a, end = back - 1, b
        line0 = data.rfind(b"\n", 0, a) + 1
        eol = data.find(b"\n", end)
        eol = len(data) if eol < 0 else eol
        rest = data[end:eol].strip()
        if not data[line0:a].strip() and (not rest or rest.startswith(b"#")):
            a, end = line0, min(len(data), eol + 1)
        elif not rest:
            # Last on a line with others before it: no space is left at the line's end.
            while a > line0 and data[a - 1:a] in (b" ", b"\t"):
                a -= 1
        spans.append((a, end))
    if not gone:
        return []
    merged: list = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in reversed(merged):
        data = data[:a] + data[b:]
    # A line every entry of which came off goes too, inside the setting and nowhere else.
    top = data.rfind(b"\n", 0, at(node.lineno, node.col_offset)) + 1
    bottom = at(node.end_lineno, node.end_col_offset) - sum(b - a for a, b in merged)
    inside = b"".join(ln for ln in data[top:bottom].splitlines(keepends=True)
                      if ln.strip() or ln in (b"\n", b"\r\n") or not ln.endswith(b"\n"))
    out = (data[:top] + inside + data[bottom:]).decode("utf-8")
    if isinstance(node, ast.Set) and len(gone) == len(node.elts):
        # Every entry of a set gone: `{}` would be a dict, so it is written set().
        m = _node(ast.parse(out), key)
        inner = _container(m)
        if isinstance(inner, ast.Dict) and not inner.keys:
            b2 = out.encode("utf-8")
            at2 = _byte_at(b2)
            s, e = at2(inner.lineno, inner.col_offset), at2(inner.end_lineno, inner.end_col_offset)
            out = (b2[:s] + b"set()" + b2[e:]).decode("utf-8")
    _write(path, out)
    return gone


def add_entries(name: str, key: str, srcs, kind: str = "list") -> None:
    """Put entries back into the list, set or dict `KEY` in profile/<name>, each as the text
    `drop_entries` kept (`src`), before its closing bracket, one a line where the person wrote
    it one a line. A setting not there is written new, as `kind` (list, set or dict)."""
    srcs = [str(s) for s in srcs or () if str(s).strip()]
    if not srcs:
        return
    path = _path(name)
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        src = ""
    n = _node(ast.parse(src), key)
    if n is None:
        body = ", ".join(srcs)
        text = {"set": "{%s}", "dict": "{%s}"}.get(kind, "[%s]") % body
        _write(path, src.rstrip("\n") + ("\n\n" if src.strip() else "") + f"{key} = {text}\n")
        return
    node = _container(n)
    if node is None:
        raise Refused(f"{key} in {name} is written as code, not a plain list: change it by hand")
    data = src.encode("utf-8")
    at = _byte_at(data)
    if isinstance(node, ast.Call):                   # set(): written as a set of them
        a, b = at(node.lineno, node.col_offset), at(node.end_lineno, node.end_col_offset)
        _write(path, (data[:a] + ("{%s}" % ", ".join(srcs)).encode("utf-8") + data[b:])
               .decode("utf-8"))
        return
    elts = node.values if isinstance(node, ast.Dict) else node.elts
    close = at(node.end_lineno, node.end_col_offset) - 1          # the closing bracket
    last = at(elts[-1].end_lineno, elts[-1].end_col_offset) if elts else None
    between = data[last:close].decode("utf-8") if elts else ""
    comma = "," in re.sub(r"#[^\n]*", "", between)
    line0 = data.rfind(b"\n", 0, close) + 1
    edits = []
    if node.lineno != node.end_lineno and not data[line0:close].strip():
        first = node.keys[0] if isinstance(node, ast.Dict) and node.keys else (elts[0] if elts else None)
        pad = " " * (first.col_offset if first is not None else n.col_offset + 4)
        if elts and not comma:
            edits.append((last, last, b","))
        edits.append((line0, line0, "".join(f"{pad}{s},\n" for s in srcs).encode("utf-8")))
    else:
        lead = "" if not elts else " " if comma else ", "
        edits.append((close, close, (lead + ", ".join(srcs)).encode("utf-8")))
    for a, b, text in sorted(edits, key=lambda e: e[0], reverse=True):
        data = data[:a] + text + data[b:]
    _write(path, data.decode("utf-8"))


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
    # The comments set_line moved above the line go back inside what it replaced.
    above = int(record.get("above") or 0)
    if above and start >= above and all(x.lstrip().startswith("#") for x in lines[start - above:start]):
        start -= above
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
