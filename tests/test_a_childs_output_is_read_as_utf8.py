"""Every command's output is read as UTF-8, in the app and in its tests.

The app's own tools write UTF-8 whatever the computer (python_floor.utf8_stdio), and so do
git and Git Bash. Read in the computer's own code page, as text=True with no encoding reads
it, a path under a user folder named with "ë" came back as "Ã«" on Windows, and eight tests
failed when the suite ran from a copy under such a folder (2026-10-25). A read with no
encoding also hides its own failure: on Windows a byte the code page has no letter for
stops the reading thread, and the output comes back as None.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = ("run", "check_output", "Popen", "check_call", "call")


def _unread(folder):
    out = []
    for dp, dns, fns in os.walk(os.path.join(ROOT, folder)):
        dns[:] = [d for d in dns if d not in ("openroles", "__pycache__", "fixtures")]
        for fn in sorted(fns):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dp, fn)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in CALLS and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"):
                    continue
                kws = {k.arg: k.value for k in node.keywords if k.arg}
                text = kws.get("text") or kws.get("universal_newlines")
                if isinstance(text, ast.Constant) and text.value is True \
                        and "encoding" not in kws:
                    out.append(f"{os.path.relpath(path, ROOT).replace(os.sep, '/')}:{node.lineno}")
    return out


def test_every_command_the_app_runs_is_read_as_utf8():
    assert _unread("tools") + _unread("templates") == []


def test_every_command_the_tests_run_is_read_as_utf8():
    assert _unread("tests") == []
