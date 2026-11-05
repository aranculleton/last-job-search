"""The workflow and the audit hash one research file to one value.

The drafter copies `research_hash` from its prompt, which the workflow computes
(.claude/workflows/draft-applications.js, researchHash), and the code audit hashes
research_<slug>.json again (tools/draft_audit.py research_hash) to show the F ids name the
facts on file. The maintainer, 2026-11-05: the two did not match on the same file, so
assemble held back a draft both audits had passed. Text of every kind hashed alike (key
order, whitespace, escaped or raw unicode, line ends); a field that was not text did not: an
empty caution list was " | caution: " in the script and nothing in Python, 1.0 was "1" in one
and "1.0" in the other, true was "true" and "True". Both now read a field the same way
(draft_pack.fact_text, factText). Run with node, which CI has; invented facts throughout.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402

WORKFLOW = os.path.join(ROOT, ".claude", "workflows", "draft-applications.js")
PROBE = ("const fs = require('fs');"
         "const src = fs.readFileSync(process.argv[1], 'utf8').replace(/^export const meta/m, 'const meta');"
         "const body = src.split('// ------------------------------------------------------------------ research')[0];"
         "const f = new Function('args', body + '; return {researchHash, factLines};');"
         "const r = f({today: 'd', round_dir: '/r', picks: []});"
         "const out = process.argv.slice(2).map(p => {"
         "  const res = JSON.parse(fs.readFileSync(p, 'utf8'));"
         "  try { return {hash: r.researchHash(res), lines: r.factLines(res)}; }"
         "  catch (e) { return {hash: 'error', lines: String(e)}; } });"
         "console.log(JSON.stringify(out))")

FACT = {"claim": "Opened a depot in Leeds", "quote": "our new Leeds depot", "url":
        "https://kestrel.example/news"}
CASES = {
    "plain": {"facts": [FACT, dict(FACT, claim="Grew 12% in 2025", caution="a press release")]},
    "accents and quotes": {"facts": [{"claim": "Zoë’s café — “naïve” déjà vu",
                                      "quote": 'it said "always"', "url": "https://x.example/é"}]},
    "beyond the basic plane": {"facts": [{"claim": "grew 😀 fast, 日本語", "quote": "𝔘𝔫𝔦", "url": "u"}]},
    "a lone surrogate": {"facts": [{"claim": "cut \ud83d in half", "quote": "q", "url": "u"}]},
    "line ends in the text": {"facts": [{"claim": "one\r\ntwo\nthree\r", "quote": "q\r\n",
                                         "url": "u", "caution": "c\r\n"}]},
    "nothing set": {"facts": [{"claim": None, "quote": None, "url": None, "caution": None,
                               "read": None}, {}]},
    "numbers": {"facts": [{"claim": 1.0, "quote": 12, "url": -3, "caution": 2.5},
                          {"claim": 2 ** 60, "quote": 0, "url": "u", "caution": 0}]},
    "lists": {"facts": [dict(FACT, caution=[]), dict(FACT, caution=["a press release", "", 7]),
                        dict(FACT, quote=["two", "parts"])]},
    "true and false": {"facts": [{"claim": True, "quote": False, "url": "u", "caution": True}]},
    "objects": {"facts": [dict(FACT, caution={"why": "old"}, claim={"text": "x"})]},
    "unread and junk": {"facts": [dict(FACT, read=False), "junk", None, [1], 5, dict(FACT, read=True)]},
    "no facts": {"team_context": "the claims team"},
    "facts not a list": {"facts": {"claim": "x"}},
}
# The same object written every way a file can hold it.
WRITERS = {
    "raw, indented": lambda o: json.dumps(o, ensure_ascii=False, indent=1),
    "escaped, one line": lambda o: json.dumps(o, ensure_ascii=True),
    "keys reversed, CRLF": lambda o: json.dumps(_reversed(o), ensure_ascii=False,
                                                indent=2).replace("\n", "\r\n"),
}


def _reversed(o):
    if isinstance(o, dict):
        return {k: _reversed(o[k]) for k in reversed(list(o))}
    if isinstance(o, list):
        return [_reversed(x) for x in o]
    return o


def test_both_hash_every_file_alike(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    paths, want = [], []
    for name, obj in CASES.items():
        for how, write in WRITERS.items():
            try:
                data = write(obj).encode("utf-8")
            except UnicodeEncodeError:
                continue           # no UTF-8 file can hold a lone surrogate unescaped
            p = tmp_path / f"{len(paths):02d}.json"
            p.write_bytes(data)
            research = draft_audit._read_json(str(p))
            paths.append(str(p))
            want.append((f"{name} / {how}", draft_audit.research_hash(research),
                         draft_pack.research_lines(research)))
    got = json.loads(subprocess.run(["node", "-e", PROBE, WORKFLOW, *paths], capture_output=True,
                                    text=True, encoding="utf-8", errors="surrogatepass",
                                    check=True).stdout)
    assert len(got) == len(want) > 30
    for (case, py_hash, py_lines), js in zip(want, got):
        assert js["lines"] == py_lines, case
        assert js["hash"] == py_hash, case


def test_text_reads_as_it_always_did():
    # A fact of text hashes as before, so no draft written against one is held back.
    research = {"facts": [FACT, dict(FACT, caution="a press release", read=False)]}
    assert draft_pack.research_lines(research) == (
        'F1: Opened a depot in Leeds | quote: "our new Leeds depot" | https://kestrel.example/news\n'
        'F2: Opened a depot in Leeds | quote: "our new Leeds depot" | https://kestrel.example/news'
        " | caution: a press release" + draft_pack.UNREAD)
    assert draft_pack.fact_text(["a", "", 3, 2.5, None]) == "a; 3"
