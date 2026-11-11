"""A big job's prompt as its chat sees it once it has run the prompt's own `app.py job` line.

The prompt a chat is started with for one big job is short (app.child_prompt): its steps are
printed by `python3 tools/app.py job ...` in the job's chat, so the chat answering the page
types a few hundred characters into create_session, not seven thousand (the efficiency audit,
E-8). A test that reads what the job's chat is told reads both.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import shlex
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

JOB_LINE = re.compile(r"python3 tools/app\.py job ([^,\n]*)")


def followed(prompt: str) -> str:
    """`prompt` and, after it, the steps its `app.py job` line prints."""
    import app
    m = JOB_LINE.search(prompt)
    assert m, f"no `app.py job` line in the prompt: {prompt}"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert app.main(["job"] + shlex.split(m.group(1).replace(app.PARENT, "PARENT"))) == 0
    return prompt + "\n" + out.getvalue()
