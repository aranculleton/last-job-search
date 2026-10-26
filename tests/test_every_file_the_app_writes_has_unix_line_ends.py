"""Every text file the app writes has plain line ends, on Windows as everywhere else.

The state files are marked `text eol=lf` (.gitattributes). Python on Windows writes "\r\n"
for every "\n" unless told otherwise, and git then shows a file saved with no change in it
as changed (2026-10-26: 28 failures on Windows, every merged JSON file " M" after a save).
So every open() for writing in the app's code says newline=, and one that writes "\n" says
newline="\n". The vendored openroles is its own project and is not read here.
"""
import ast
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_files  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _writes_without_newline():
    found = []
    for rel in repo_files.tracked(root=str(ROOT)):
        p = ROOT / rel
        if not (rel.startswith(("tools/", "templates/")) and rel.endswith(".py")) or "openroles" in p.parts:
            continue
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in
                    ("open", "fdopen", "NamedTemporaryFile")):
                continue
            mode = next((a.value for a in node.args[1:2] if isinstance(a, ast.Constant)), None)
            if getattr(node.func, "attr", "") == "NamedTemporaryFile" or getattr(node.func, "id", "") == "NamedTemporaryFile":
                mode = next((a.value for a in node.args[:1] if isinstance(a, ast.Constant)), mode)
            mode = next((k.value.value for k in node.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), mode)
            if not isinstance(mode, str) or "b" in mode or not set(mode) & set("wax"):
                continue
            if not any(k.arg == "newline" for k in node.keywords):
                found.append(f"{p.relative_to(ROOT)}:{node.lineno}")
    return found


def test_every_write_in_text_mode_says_its_line_ends():
    found = _writes_without_newline()
    assert not found, "these open a file to write with no newline=: " + ", ".join(found)
