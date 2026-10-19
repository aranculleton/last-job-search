"""tools/leak_scan.py: the last gate before anything reaches the public app.

The app's history is permanent, so the scan has to catch a person's data
without being told who the person is (the structural checks), catch the named
people and organizations it IS told about (the denylist), and never print a
denylist token, because CI logs of a public repo are public.

The leak-shaped strings below are assembled at run time ("real" + "@" ...), so
this file passes the very scan it tests: a literal would be flagged when the
app is built.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import leak_scan  # noqa: E402


def _tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            p.write_bytes(text)
        else:
            p.write_text(text, encoding="utf-8")
    return str(tmp_path)


def _scan(tree, tokens_text="", allow=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("LJS_LEAK_TOKENS", tokens_text)
    return leak_scan.scan(tree, leak_scan.load_tokens(None), leak_scan.load_allow(allow))


def test_a_clean_tree_passes(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"tools/a.py": "print('hello')\n",
                         "README.md": "Write to sam@example.com or call +44 7700 900123.\n"})
    assert _scan(t, monkeypatch=monkeypatch) == []


def test_a_personal_path_fails_whatever_it_holds(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"job_search_tracker.csv": "date,company\n",
                         "profile/person.json": "{}",
                         "cv/Sam_Example_Resume_ACME.tex": "x"})
    found = _scan(t, monkeypatch=monkeypatch)
    assert len(found) == 3 and all("personal path" in f for f in found)


def test_real_contact_details_fail_without_any_list(tmp_path, monkeypatch):
    email = "someone" + "@" + "realmail.net"
    phone = "+1 312" + " 555 2368"
    handle = "linkedin.com/in/" + "a-real-person-123"
    t = _tree(tmp_path, {"notes.md": f"Reach me at {email} or {phone}.\n{handle}\n"})
    kinds = sorted(f.split(": ", 1)[1] for f in _scan(t, monkeypatch=monkeypatch))
    assert kinds == ["LinkedIn profile", "email address", "phone number"]


def test_fiction_ranges_and_placeholders_pass(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"a.md": "+44 7700 900456, +1 555 0142, linkedin.com/in/your-profile, "
                                 "linkedin.com/in/morgan-ellis-example, you@example.org\n"})
    assert _scan(t, monkeypatch=monkeypatch) == []


def test_the_denylist_names_the_entry_never_the_token(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"tools/x.py": "# shipped on the Zorblax resume\n"})
    found = _scan(t, "# a comment line\nZorblax\n", monkeypatch=monkeypatch)
    assert found == ["tools/x.py:1: denylist entry 2"]
    assert "Zorblax" not in found[0]


def test_a_denylist_token_matches_whole_words_only(tmp_path, monkeypatch):
    # "Ruth" must not fire inside "truth"; "=AB" is case-sensitive.
    t = _tree(tmp_path, {"a.md": "We tell the truth. The ab element. ABC.\n"})
    assert _scan(t, "ruth\n=AB\n", monkeypatch=monkeypatch) == []
    t2 = _tree(tmp_path / "b", {"a.md": "Applied at AB.\n"})
    assert len(_scan(t2, "=AB\n", monkeypatch=monkeypatch)) == 1


def test_the_license_credit_is_the_one_allowed_mention(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"LICENSE": "MIT\n\nCopyright (c) 2026 Zorblax Quux\n",
                         "README.md": "Built by Zorblax Quux.\n"})
    found = _scan(t, "Zorblax Quux\n", monkeypatch=monkeypatch)
    assert found == ["README.md:1: denylist entry 1"]


def test_the_apps_own_url_is_not_a_leak_but_a_personal_repo_is(tmp_path, monkeypatch):
    owner = "".join(["ar", "ancull", "eton"])   # the app's owner, in pieces no denylist holds
    t = _tree(tmp_path, {"README.md": f"https://github.com/{owner}/last-job-search\n"
                                      f"https://github.com/{owner}/my-job-search\n"})
    found = _scan(t, owner + "\n", monkeypatch=monkeypatch)
    assert found == ["README.md:2: denylist entry 1"]


def test_an_unknown_binary_fails_and_a_vendored_font_passes(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"cover_letters/OpenFonts/fonts/x.ttf": b"\0\1binary",
                         "documents_scan.png": b"\x89PNG\0\0"})
    found = _scan(t, monkeypatch=monkeypatch)
    assert found == ["documents_scan.png: binary file that cannot be scanned and is not allowlisted"]


def test_the_cli_exits_one_on_a_finding(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"a.md": "real" + "@" + "person.org\n"})
    monkeypatch.setenv("LJS_LEAK_TOKENS", "")
    assert leak_scan.main([t]) == 1
    assert leak_scan.main([str(tmp_path / "nope")]) == 2


def test_a_name_broken_across_a_comment_line_is_still_caught(tmp_path, monkeypatch):
    t = _tree(tmp_path, {"tools/x.py": "# the next bullet in is a Zorblax\n#     Quux one\n",
                         "tools/y.py": "# Zorblax Quux on one line\n"})
    found = _scan(t, "Zorblax Quux\n", monkeypatch=monkeypatch)
    assert sorted(found) == ["tools/x.py:1: denylist entry 1 (across a line break)",
                             "tools/y.py:1: denylist entry 1"]


def test_a_name_in_a_filename_slug_or_handle_is_caught(tmp_path, monkeypatch):
    """`\\w` counts "_" as a letter, so "First_Last_CV.pdf" once passed with the
    name in it. Any separator, or none, between an entry's words still matches."""
    first, last = "Zorb" + "lax", "Qu" + "ux"
    shapes = [f"{first}_{last}_CV.pdf", f"{first.lower()}-{last.lower()}",
              f"{first}{last}", f"{first.lower()}.{last.lower()} wrote"]
    t = _tree(tmp_path, {f"f{i}.md": s + "\n" for i, s in enumerate(shapes)})
    assert len(_scan(t, f"{first} {last}", monkeypatch=monkeypatch)) == len(shapes)


def test_every_form_of_a_recorded_name_and_company_is_an_entry():
    import build_app
    forms = build_app.name_forms("Xiu Mei (Sally) Ho, PhD")
    assert forms[:3] == ["Xiu Mei (Sally) Ho", "Xiu Mei Ho", "Sally Ho"]
    assert "Mei Ho" in forms                   # somebody who goes by a middle name
    assert build_app.given_names("Xiu Mei (Sally) Ho, PhD") == ["Xiu", "Mei", "Sally"]
    assert build_app.name_forms("Tomasz Kowal MBA") == ["Tomasz Kowal"]
    assert build_app.given_names("Tomasz Kowal MBA") == ["Tomasz"]
    assert build_app.company_forms("Harbour Freight Company Inc.") == [
        "Harbour Freight Company Inc.", "Harbour Freight"]


def test_a_phone_number_is_an_entry_in_the_forms_it_is_written_anywhere():
    import build_app
    assert build_app.phone_forms("+1 312 555 0142") == ["312", "555 0142", "5550142", "0142"]
    au = "+61" + " 400 111 222"            # assembled, so this file passes the scan it tests
    assert build_app.phone_forms(au) == ["400 111 222", "0400 111 222"]
    assert build_app.phone_forms("0400 111 222") == ["0400 111 222"]
    assert build_app.phone_forms("020 7946 0011") == ["020 7946 0011"]
    # never a short group on its own: it would match everywhere
    assert all(len(f.replace(" ", "")) >= 4 for f in build_app.phone_forms("+44 7700 900123"))


def test_git_mode_scans_what_would_be_committed_and_nothing_else(tmp_path, monkeypatch):
    """Ignored build output can never be pushed; a new, unignored file can."""
    import subprocess
    t = _tree(tmp_path, {".gitignore": "*.pdf\n", "README.md": "clean\n",
                         "build.pdf": "Zorblax Quux\n", "new_notes.md": "Zorblax Quux\n"})
    subprocess.run(["git", "init", "-q", t], check=True)
    subprocess.run(["git", "-C", t, "add", "README.md", ".gitignore"], check=True)
    monkeypatch.setenv("LJS_LEAK_TOKENS", "Zorblax Quux")
    found = leak_scan.scan(t, leak_scan.load_tokens(None), leak_scan.load_allow(None), git=True)
    assert [f.split(":")[0] for f in found] == ["new_notes.md"]


def test_the_denylist_remembers_a_row_taken_out_of_the_state_files(tmp_path):
    """A draft never sent was scrubbed from a tracker, and a denylist built from today's
    file alone forgot the employer it named, while the repo's history still held it."""
    import subprocess
    import build_app

    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c",
                        "user.email=t@example.com", *a], check=True, capture_output=True)
    git("init", "-q")
    tracker = tmp_path / "job_search_tracker.csv"
    tracker.write_text("company,role\nFernhill Freight,Analyst\nLarkspur Retail,Analyst\n")
    git("add", "-A")
    git("commit", "-qm", "two drafts")
    tracker.write_text("company,role\nLarkspur Retail,Analyst\n")
    git("commit", "-qam", "one scrubbed")
    assert [r["company"] for r in build_app._csv(str(tracker))] == ["Larkspur Retail"]
    ever = {r["company"] for r in build_app._csv_ever(str(tracker))}
    assert ever == {"Fernhill Freight", "Larkspur Retail"}
    # Every state file the denylist reads, it reads with its history.
    src = open(os.path.join(ROOT, "tools", "build_app.py"), encoding="utf-8").read()
    body = src[src.index("def denylist("):src.index("def main(")]
    assert "_csv(person.state(" not in body and body.count("_csv_ever(person.state(") == 4


def test_a_tool_family_entry_is_set_aside_and_nothing_else_in_the_file(tmp_path, monkeypatch):
    # The families of interchangeable tools name software. A product that shares a word
    # with a denylisted employer is not a leak there; the same word anywhere else is.
    t = tmp_path / "tools"
    t.mkdir()
    (t / "bridges.py").write_text('FAMILIES = [("store", ("Zorblax", r"\\bzorblax\\b")),]\n'
                                  "# Zorblax asked for this\n", encoding="utf-8")
    found = _scan(str(tmp_path), "Zorblax\n", monkeypatch=monkeypatch)
    assert found == ["tools/bridges.py:2: denylist entry 1"]
