"""Building the page's model took about 12 seconds on every page update in a person's copy
(the second audit of 2026-11-10, D8, profiled): an employer's name was looked for in a
posting or a name by one regular expression per name on the person's lists, made again on
every call once there were more names than Python keeps compiled (1.46 million lookups, 4,932
real compiles), and every PDF's pages were counted again on every build (264 of them, 3.8
seconds). A name is now looked for only where it could be, and a PDF's count is kept until
the file changes. Every employer and file here is invented.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import opportunity  # noqa: E402


def _old_names_in(c, names):
    for name in sorted(names, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", c):
            return name
    return None


def test_an_employer_name_is_looked_for_only_where_it_could_be(monkeypatch):
    names = {f"quillon {i} data" for i in range(2000)} | {"ace", "palace foods", "brackwater"}
    cases = [" palace foods ", " the palace ", " ace ", " brackwater insurance ",
             " quillon 77 data ", " quillon 1777 data ltd ", " nobody at all ", " xace "]
    for c in cases:
        assert opportunity._names_in(c, names) == _old_names_in(c, names), c
    searched = []
    real = re.search

    def counting(pattern, *a, **k):
        searched.append(pattern)
        return real(pattern, *a, **k)
    monkeypatch.setattr(re, "search", counting)
    for _ in range(50):
        opportunity._names_in(" nobody at all ", names)
    # Before: 2,003 expressions a call, more than Python keeps compiled, so each was made again.
    assert len(searched) == 0, len(searched)


def test_a_pdfs_pages_are_counted_once_until_it_changes(tmp_path, monkeypatch):
    import app_model
    import person
    import pdftext
    state = tmp_path / "copy"
    state.mkdir()
    subprocess.run(["git", "init", "-q", str(state)], check=True)
    monkeypatch.setenv(person.STATE_ENV if hasattr(person, "STATE_ENV") else "LJS_STATE",
                       str(state))
    pdf = state / "cv" / "Morgan_Resume.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 invented")
    counted = []
    monkeypatch.setattr(pdftext, "pages", lambda p: counted.append(p) or 2)
    app_model._PDF_PAGES.clear()
    assert app_model._pages(str(pdf)) == 2 and app_model._pages(str(pdf)) == 2
    app_model.save_pdf_pages()
    # The next build is another process: the count comes from the copy's git folder.
    app_model._PDF_PAGES.clear()
    assert app_model._pages(str(pdf)) == 2 and len(counted) == 1
    # A changed file is counted again.
    pdf.write_bytes(b"%PDF-1.4 invented, and longer")
    assert app_model._pages(str(pdf)) == 2 and len(counted) == 2


def test_a_build_works_out_each_employer_and_posting_once_and_keeps_nothing_after(
        monkeypatch, tmp_path):
    """Each job's employer was read against the person's lists twice and its posting's pay
    range twice, every one worked out from scratch (the second audit, D8: bar.verdict 6.9 s
    of a 12 s build). Within one build each is worked out once; outside a build nothing is
    kept, so an answer never outlives what it was read from, and a judgement made during a
    build is read at once (the review of 2026-11-11)."""
    import bar
    import remembered
    import text_screen
    tiers, pays = [], []
    real_tier, real_pay = opportunity._tier_of, text_screen.sentences
    monkeypatch.setattr(opportunity, "_tier_of", lambda c: tiers.append(c) or real_tier(c))
    monkeypatch.setattr(text_screen, "sentences", lambda t: pays.append(t) or real_pay(t))
    posting = "Salary GBP 55,000 to 65,000. Hybrid in Manchester. " * 20
    with remembered.build():
        first = [bar.verdict("Quillon Data", posting) for _ in range(5)]
        text_screen.salary_max(posting)
    assert len(set(first)) == 1
    assert len(tiers) == 2, tiers       # the raw name and its key, once for the build
    assert len(pays) == 1, len(pays)    # the posting's pay, once for both readers
    # Outside a build, every call reads afresh: a list changed since is read at once.
    monkeypatch.setattr(opportunity, "TIER_1", {"quillon data"})
    assert opportunity.tier("Quillon Data")[0] == 30
    monkeypatch.setattr(opportunity, "TIER_1", set())
    assert opportunity.tier("Quillon Data")[0] == 0
    # A judgement made during a build is read at once: the verdict is kept by the file's state.
    import person
    monkeypatch.setattr(bar, "_judged_path", lambda: str(tmp_path / "employers_judged.json"))
    monkeypatch.setattr(bar, "applies", lambda: True)
    monkeypatch.setattr(person, "today", lambda: __import__("datetime").date(2026, 10, 25))
    with remembered.build():
        before = bar.verdict("Brackwater Mutual 7")
        bar.judge("Brackwater Mutual 7", bar.PAY, "pays well, invented", today="2026-10-25")
        after = bar.verdict("Brackwater Mutual 7")
    assert before[0] != bar.PAY and after[0] == bar.PAY, (before, after)


def test_a_full_name_is_cut_by_a_pattern_of_only_the_names_a_text_could_hold():
    """A call prep was cut down by one pattern of every full name in the book, run over the
    whole prep: 51 preps took 4.1 to 4.4 s of a build (the second audit, D8). Only the names
    whose own words stand side by side in the text are looked for, with the same result."""
    import app_model
    rnd = __import__("random").Random(5)
    syl = ["ka", "lo", "mi", "ren", "tor", "vi", "sa", "be", "dun", "fa", "gil", "ho", "ix"]
    word = lambda: (rnd.choice(syl) + rnd.choice(syl) + rnd.choice(syl)).title()  # noqa: E731
    joined = f"{word()} {word()}-{word()}"
    pairs = [(f"{word()} {word()}", "") for _ in range(800)] + [("Ana", "A"), (joined, "")]
    pairs = [(full, first or full.split()[0]) for full, first in pairs]
    names = app_model.Names(pairs)
    old = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in sorted(
        names.first, key=len, reverse=True)) + r")(?!\w)", re.I)

    def whole(text):
        return old.sub(lambda m: names.first.get(m.group(0).casefold(), m.group(0)), text)
    picked = [full for full, _ in rnd.sample(pairs, 12)]
    texts = [" ".join(f"{p} said the team works on forecasting." for p in picked) * 20,
             f"{picked[0].upper()}, then {picked[1].lower()}; and {joined.lower()}.",
             "Nobody in the book is here.", ""]
    for t in texts:
        assert names.sub(t) == whole(t), t[:80]
    # The pattern run over the long text holds the dozen names in it, never all 800.
    assert max(len(k) for k in names.patterns) <= 12
