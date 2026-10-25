"""Every text file the app opens, and every command whose output it reads, names UTF-8.

Without an encoding Python uses the computer's own: UTF-8 on a Mac and on Linux, the code
page on Windows (cp1252 in English), so a file the app wrote on one read back wrong on the
other, and git's output with a name in it stopped the sync after its commit (2026-10-25).
UTF-8 mode in .claude/settings.json covers a chat; this covers the code, run any way.

Binary opens ("rb", "wb") are not text and are left alone. A command's output is read with
errors="replace": a byte that is not UTF-8 (an old commit, another program's message)
prints as a stand-in character instead of stopping the tool.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBPROCESS = {"run", "check_output", "Popen", "check_call", "call"}

# Call sites in files another part of this same change rewrites, so they were left for it
# rather than edited twice; each is the same one-line fix. The test below fails as soon as
# one is fixed, so the list can only shrink, and it is emptied when the change lands.
PENDING = {
    ("tools/audit_letters.py", "subprocess.run"): 1,
    ("tools/env_check.py", "subprocess.run"): 3,
    ("tools/fit_to_page.py", "subprocess.run"): 3,
    ("tools/hydrate.py", "open"): 2,
    ("tools/scrape_wide.py", "open"): 4,
}


def _files():
    out = [os.path.join(ROOT, "salary_lookup.py")]
    for top in ("tools", "templates"):
        for dp, dns, fns in os.walk(os.path.join(ROOT, top)):
            # openroles is vendored from its own project and never edited here.
            dns[:] = [d for d in dns if d not in ("__pycache__", "openroles", "node_modules")]
            out += [os.path.join(dp, f) for f in fns if f.endswith(".py")]
    return sorted(out)


def _kw(call, name):
    return next((k.value for k in call.keywords if k.arg == name), None)


def _mode(call, pos):
    m = _kw(call, "mode")
    if m is None and len(call.args) > pos:
        m = call.args[pos]
    if m is None:
        return "r"
    return m.value if isinstance(m, ast.Constant) and isinstance(m.value, str) else "?"


def _truthy(v):
    return isinstance(v, ast.Constant) and bool(v.value)


def missing(path):
    """[(line, what)] for every text open and text-mode command without an encoding."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or any(k.arg is None for k in n.keywords):
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if isinstance(f, ast.Name) and f.id == "open":
            if "b" not in _mode(n, 1) and _kw(n, "encoding") is None:
                out.append((n.lineno, "open"))
        elif name in ("read_text", "write_text"):
            if _kw(n, "encoding") is None and len(n.args) <= (1 if name == "write_text" else 0):
                out.append((n.lineno, name))
        if name in SUBPROCESS and (_truthy(_kw(n, "text")) or _truthy(_kw(n, "universal_newlines"))) \
                and _kw(n, "encoding") is None:
            out.append((n.lineno, f"subprocess.{name}"))
    return out


def test_every_text_open_and_command_output_names_utf8():
    found = {}
    for path in _files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for line, what in missing(path):
            found.setdefault((rel, what), []).append(line)
    new = {k: v for k, v in found.items() if len(v) > PENDING.get(k, 0)}
    assert not new, ("say encoding=\"utf-8\" (and errors=\"replace\" for a command's output): "
                     + "; ".join(f"{f}:{lines} {w}" for (f, w), lines in sorted(new.items())))
    fixed = {k for k in PENDING if len(found.get(k, ())) < PENDING[k]}
    assert not fixed, f"fixed, so take them off PENDING: {sorted(fixed)}"


def test_the_check_catches_what_it_is_for(tmp_path):
    p = tmp_path / "x.py"
    p.write_text('import subprocess\nopen("a")\nopen("b", "rb")\nopen("c", encoding="utf-8")\n'
                 'subprocess.run(["git"], text=True)\n'
                 'subprocess.run(["git"], text=True, encoding="utf-8", errors="replace")\n'
                 'import pathlib\npathlib.Path("d").read_text()\n', encoding="utf-8")
    assert missing(str(p)) == [(2, "open"), (5, "subprocess.run"), (8, "read_text")]
