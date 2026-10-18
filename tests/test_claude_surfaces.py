"""What the app says about the Claude app lives in one registry, dated and sourced.

The Claude app's screens move, and a sentence about them written into a doc goes stale
with nobody noticing: a place check once told people to "click the Code tab". These
pin the registry's shape, the one way a path is written, the staleness warning, the
maintainer's watch (run here against invented pages, never the network), the drift
tripwire that fails a doc stating a surface outside the registry, and the docs' blocks
matching the registry word for word.
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import claude_surfaces as C  # noqa: E402

REG = C.load()
STATUSES = {"documented", "skill only", "observed"}


def test_every_entry_says_what_it_rests_on_and_when_it_was_checked():
    ids = [e["id"] for e in REG["entries"]]
    assert len(ids) == len(set(ids))
    for e in REG["entries"]:
        assert set(e) >= {"id", "claim", "sources", "status", "verified_on", "verified_against",
                          "ui_sensitive"}, e["id"]
        datetime.date.fromisoformat(e["verified_on"])
        assert e["status"] in STATUSES and isinstance(e["ui_sensitive"], bool)
        assert e["sources"] and all(s["url"] and s["quote"] for s in e["sources"])
        # An entry that only a skill or an observation backs says so in its claim or its
        # check, so nobody reads it as documented.
        if not any(s["url"].startswith("http") for s in e["sources"]):
            assert e["status"] != "documented" or "observed" in e["verified_against"]
    assert int(REG["stale_after_days"]) == 60


def test_a_path_is_a_destination_at_the_time_of_writing_with_its_official_page():
    for e in REG["entries"]:
        for field in ("goal", "how"):
            assert not C.BANNED.search(e.get(field, "")), (e["id"], field)
        if e.get("how"):
            said = C.say(e["id"], name="my-job-search", owner="example-owner")
            assert "At the time of writing: " in said and "(official page: https://" in said
            assert "{" not in said                                # every placeholder filled
            if e.get("goal"):
                assert said.startswith(e["goal"][:1].upper() + e["goal"][1:])
    assert C.say("local-chat", goal=False).startswith("At the time of writing:")
    # "Find" names a screen only when it sends someone looking, never in their own words.
    assert C.BANNED.search("find the setting") and not C.BANNED.search('say "find me people"')


def test_an_old_entry_warns_every_time_it_is_used_and_never_fails_a_check():
    e = C.entry("local-chat")
    then = datetime.date.fromisoformat(e["verified_on"])
    assert C.warning(e, then + datetime.timedelta(days=60)) == ""
    w = C.warning(e, then + datetime.timedelta(days=61))
    assert "re-check https://code.claude.com/docs/en/desktop-quickstart" in w
    assert w.startswith("[claude_surfaces:")                   # for Claude, never said
    assert [x["id"] for x, _ in C.stale(today=then + datetime.timedelta(days=400))] \
        == [x["id"] for x in REG["entries"]]
    assert C.main(["check"]) == 0                              # never blocks anyone's CI


def test_the_watch_finds_a_moved_quote_a_new_release_and_an_old_entry():
    reg = {"stale_after_days": 60, "checked_version": "2.1.302",
           "release_notes": "https://example.test/changelog",
           "entries": [{"id": "a", "verified_on": "2026-10-18", "ui_sensitive": True,
                        "sources": [{"url": "https://example.test/a", "quote": "Select Local for your machine"},
                                    {"url": "skill:x", "quote": "never fetched"}]},
                       {"id": "b", "verified_on": "2026-01-01", "ui_sensitive": False,
                        "sources": [{"url": "https://example.test/b", "quote": "gone now"}]}]}
    pages = {"https://example.test/a": "<p>Select <b>Local</b> for your machine</p>",
             "https://example.test/b": "<p>Something else</p>",
             "https://example.test/changelog": "listen on 127.0.0.1 On this page 2.1.310 2.1.302"}
    fetched = []

    def fetch(url):
        fetched.append(url)
        return pages[url]
    found = C.watch(reg, fetch=fetch, today=datetime.date(2026, 10, 20))
    why = {f"{i}: {w}" for i, w in found}
    assert not any(w.startswith("a: the quote") for w in why)   # tags and spacing ignored
    assert any(w.startswith("b: the quote is no longer on") for w in why)
    assert any(w.startswith("b: checked 2026-01-01") for w in why)
    assert any("Claude Code 2.1.310 is out" in w and "review the paths in a" in w for w in why)
    assert "skill:x" not in fetched                             # only official pages


def _app_files():
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    keep = []
    for n in names:
        if n.startswith(("tests/", "CHANGELOG")) or n in ("tools/claude_surfaces.json",
                                                            "tools/claude_surfaces.py"):
            continue
        p = ROOT / n
        if p.suffix in (".md", ".py", ".sh", ".json", ".yml", ".txt") and p.is_file():
            keep.append(n)
    return keep


def test_no_doc_or_tool_states_a_surface_outside_the_registry():
    # The vocabulary is the tripwire: the names of screens and the claims that move when
    # the product does. A person's doc carries them only inside a block the registry
    # renders; Claude's own instructions point at an entry by id instead.
    found = []
    for n in _app_files():
        text = (ROOT / n).read_text(encoding="utf-8", errors="replace")
        spans = [(m.start(), m.end()) for m in C.BLOCK.finditer(text)] if n in C.DOCS else []
        for phrase, at in C.mentions(text):
            if not any(a <= at < b for a, b in spans):
                found.append(f"{n}:{text.count(chr(10), 0, at) + 1}: {phrase!r}")
    assert found == [], "\n".join(found)


def test_every_block_in_the_docs_is_the_registry_word_for_word():
    stale = []
    for rel in C.DOCS:
        p = ROOT / rel
        if not p.is_file():
            continue
        for eid, indent, written in C.blocks(p.read_text(encoding="utf-8")):
            C.entry(eid.split()[0])                             # names a real entry
            if written != C.block(eid, indent):
                stale.append(f"{rel}: {eid}")
    assert stale == [], f"run python3 tools/claude_surfaces.py sync-docs: {stale}"


def test_the_watch_runs_in_the_app_only_and_reports_without_changing_anything():
    wf = (ROOT / ".github/workflows/claude-surfaces-watch.yml").read_text(encoding="utf-8")
    assert "if: github.repository == 'aranculleton/last-job-search'" in wf
    assert "claude_surfaces.py watch --strict" in wf and "timeout-minutes:" in wf
    assert re.search(r"permissions:\s*\n\s*contents: read\s*\n\s*issues: write", wf)
    assert "git push" not in wf and "git commit" not in wf
