"""A ruling rests on something, and stops blocking when that something changes."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import exclude  # noqa: E402
import throttle  # noqa: E402

URL = "https://boards.example.com/oakmere/jobs/123"


def _seen(tmp_path):
    return str(tmp_path / "seen_jobs.json")


def test_a_ruling_under_the_current_rules_blocks(tmp_path):
    path = _seen(tmp_path)
    exclude.add(URL, "triage knockout: requires a chartered accountancy licence",
                "Finance Analyst", "Oakmere Foods", path=path)
    entries = json.load(open(path))["seen"]
    urls, _ = throttle.ruled_out(entries)
    assert any("chartered" in why for why in urls.values())


def test_a_ruling_lapses_when_its_rules_change(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "language gate: Welsh essential", "Data Analyst", "Oakmere Foods", path=path)
    monkeypatch.setattr(exclude, "rules_fingerprint", lambda: "changed00000")
    urls, pairs = throttle.ruled_out(json.load(open(path))["seen"])
    assert urls == {} and pairs == {}


def test_the_persons_own_ruling_holds_until_they_lift_it(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "Morgan: no more food manufacturers", "Data Analyst", "Oakmere Foods",
                basis="person", path=path)
    monkeypatch.setattr(exclude, "rules_fingerprint", lambda: "changed00000")
    assert throttle.ruled_out(json.load(open(path))["seen"])[0]       # rules changed, still holds
    assert len(exclude.lift("food manufacturers", "Morgan would consider them now", path=path)) == 1
    assert throttle.ruled_out(json.load(open(path))["seen"])[0] == {}


def test_the_fingerprint_moves_only_with_a_gate():
    before = exclude.rules_fingerprint()
    s = exclude.person.module("search")
    old = list(s.SCRAPE_QUERIES)
    try:
        s.SCRAPE_QUERIES.append("an extra query")              # not a gate
        assert exclude.rules_fingerprint() == before
    finally:
        s.SCRAPE_QUERIES[:] = old
    langs = s.LANGUAGES_HELD
    try:
        s.LANGUAGES_HELD = langs + ("welsh",)                   # a gate
        assert exclude.rules_fingerprint() != before
    finally:
        s.LANGUAGES_HELD = langs


def test_a_ruling_needs_a_reason(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        exclude.add(URL, "  ", path=_seen(tmp_path))


def test_older_rulings_are_reviewed_once_then_stamped_or_lifted(tmp_path):
    path = _seen(tmp_path)
    json.dump({"seen": {
        "a": {"status": "excluded", "exclusion_reason": "language gate: Welsh essential",
              "title": "Data Analyst", "company": "Oakmere Foods", "url": "a"},
        "b": {"status": "excluded", "exclusion_reason": "stated salary below the floor",
              "title": "Analyst", "company": "Saltmarsh Analytics", "url": "b"},
        "c": {"status": "skipped", "skip_reason": "same-employer duplicate", "url": "c"},
        "d": {"status": "excluded", "exclusion_reason": "posting closed", "url": "d"},
    }}, open(path, "w"))
    groups = exclude.review(path)
    assert [g for g, _, _ in groups] == ["language gate"]      # salary already lapses; the rest are not rulings
    assert exclude.stamp("language gate", "rules", path=path) == 1
    assert exclude.review(path) == []
    entry = json.load(open(path))["seen"]["a"]
    assert entry["basis"] == "rules" and entry["rules"] == exclude.rules_fingerprint()


def test_a_better_screen_never_lifts_the_persons_own_call(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL, "Morgan: not a fit at 40/100, no more food manufacturers",
                "Data Analyst", "Oakmere Foods", basis="person", today="2026-01-01", path=path)
    monkeypatch.setattr(throttle, "rescreen_since", lambda: "2026-06-01")   # a re-run screen since
    assert throttle.ruled_out(json.load(open(path))["seen"])[0]           # still holds


# ---------------------------------------------------------------- one part at a time

def _move_pay_threshold(monkeypatch):
    """The triage card's pay row says a different number; nothing else changes."""
    real = exclude._doc
    monkeypatch.setattr(exclude, "_doc", lambda name: real(name).replace(b"42,000", b"40,000")
                        if name == exclude.RULE_DOCS[0] else real(name))


def test_moving_one_threshold_lapses_only_the_rulings_on_it(tmp_path, monkeypatch):
    # A one-number change to the pay blocker used to lapse every ruling on the rules,
    # language and eligibility rulings included, because they shared one fingerprint.
    path = _seen(tmp_path)
    exclude.add(URL + "1", "triage knockout: blocker 2, Welsh essential", "Data Analyst",
                "Oakmere Foods", path=path)
    exclude.add(URL + "2", "triage knockout: blocker 5, whole range below £42,000", "Analyst",
                "Saltmarsh Analytics", path=path)
    exclude.add(URL + "3", "a role the profile reads as a different job", "Engineer",
                "Brindle & Hart Logistics", path=path)
    exclude.add(URL + "4", "on-site in Leeds only", "Analyst", "Oakmere Foods",
                rests_on=["triage #4"], path=path)
    _move_pay_threshold(monkeypatch)
    urls, _ = throttle.ruled_out(json.load(open(path))["seen"])
    blocked = {u[-1] for u in urls}
    assert blocked == {"1", "4"}           # Welsh and location stand; pay and the unnamed lapse


def test_lapsed_names_what_changed_and_restamp_keeps_what_still_holds(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    exclude.add(URL + "2", "triage knockout: blocker 5, whole range below £42,000", "Analyst",
                "Saltmarsh Analytics", path=path)
    exclude.add(URL + "3", "a role the profile reads as a different job", "Engineer",
                "Brindle & Hart Logistics", path=path)
    _move_pay_threshold(monkeypatch)
    groups = dict(exclude.lapsed(path))
    (pay, changed), = groups["triage knockout"]
    assert changed == ["triage #5"]
    (_, whole), = groups["a role the profile reads as a different job"]
    assert whole is None
    # Still true under the new number? Not for the pay ruling: its own part moved.
    assert exclude.restamp("blocker 5", ["triage #5"], path=path) == 0
    assert exclude.restamp("different job", ["triage #3"], path=path) == 1
    assert set(dict(exclude.lapsed(path))) == {"triage knockout"}
    urls, _ = throttle.ruled_out(json.load(open(path))["seen"])
    assert {u[-1] for u in urls} == {"3"}


def test_the_screens_own_wording_names_its_setting():
    assert exclude.cited("Tier 1 pre-filter: title: title names no analytics work") == [
        "search.py POSITIVE", "search.py NEGATIVE"]
    assert exclude.cited("Tier 1 mechanical pre-filter (tools/prefilter.py): location: "
                         "on-site outside the North West (york)") == ["search.py LOCATION"]
    assert "search.py LANGUAGE_GATE" in exclude.cited(
        'free text screen: Welsh stated as a requirement: "Welsh essential"')
    # Prose names nothing, and a part that is not in the rules names nothing either.
    assert exclude.cited("not the kind of role that fits") == []
    assert exclude.cited("blocker 99: something long gone") == []


def test_unnamed_rulings_are_named_once_and_never_asked_again(tmp_path):
    path = _seen(tmp_path)
    fp = exclude.rules_fingerprint()
    json.dump({"seen": {
        "a": {"status": "excluded", "basis": "rules", "rules": fp, "url": "a",
              "exclusion_reason": "triage knockout: blocker 1, SC clearance required"},
        "b": {"status": "excluded", "basis": "rules", "rules": fp, "url": "b",
              "exclusion_reason": "a different job family"},
    }}, open(path, "w"))
    assert sum(len(es) for _, es in exclude.unnamed(path)) == 2
    assert exclude.cite(path) == 1
    assert exclude.restamp("different job family", ["all"], path=path) == 1
    assert exclude.unnamed(path) == []
    exclude.add(URL, "another job family entirely", path=path)     # new rulings say, too
    assert exclude.unnamed(path) == []


def test_the_fingerprint_is_the_one_every_ruling_was_stamped_with():
    # Splitting the rules into parts must not move the whole fingerprint, or every
    # ruling stamped before it would lapse at once.
    import hashlib
    h = hashlib.sha256()
    for name in exclude.RULE_DOCS:
        h.update(name.encode())
        if exclude.person.exists(name):
            h.update(open(exclude.person.path(name), "rb").read())
    s = exclude.person.module("search")
    for name in exclude.GATE_NAMES:
        h.update(f"{name}={exclude._stable(getattr(s, name, None))}".encode())
    assert exclude.rules_fingerprint() == h.hexdigest()[:12]


# ---------------------------------------------------------------- the file itself

def test_a_ruling_rewrites_only_its_own_lines(tmp_path):
    # exclude.py wrote seen_jobs.json at indent 1 while the throttle and the merge write
    # indent 2, so one stamp rewrote the whole file: a 124k-line diff two chats then had
    # to merge.
    import difflib
    path = _seen(tmp_path)
    seen = {f"https://boards.example.com/{i}": {"url": f"https://boards.example.com/{i}",
                                                 "title": "Analyst", "status": "new"}
            for i in range(200)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"seen": seen}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    before = open(path).read().splitlines()
    exclude.add("https://boards.example.com/7", "triage knockout: blocker 2, Welsh essential",
                path=path)
    after = open(path).read().splitlines()
    changed = [l for l in difflib.unified_diff(before, after, lineterm="", n=0)
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert 0 < len(changed) < 20, len(changed)


def test_one_of_several_identical_reasons_is_picked_by_its_address(tmp_path):
    path = _seen(tmp_path)
    for i in range(3):
        exclude.add(f"{URL}/{i}", "French-language posting", basis="person", path=path)
    lifted = exclude.lift(urls=[f"{URL}/1"], path=path)
    assert [e["url"] for e in lifted] == [f"{URL}/1"]
    assert len(exclude.lift("french-language", urls=[f"{URL}/2"], path=path)) == 1
    import pytest
    with pytest.raises(ValueError):
        exclude.lift("", path=path)            # neither words nor an address: nothing named


# ---------------------------------------------------------------- the screen's own words

# Postings the example's screen cuts, one per kind of cut, written by the screen itself.
_SCREEN_CUTS = {
    "eligibility": "You must hold British nationality as a condition of employment.",
    "internal only": "This vacancy is open to current employees only.",
    "another language": "Fluency in Spanish is essential for this role.",
    "the gated language": "Fluency in Welsh is essential.",
    "pay": "The salary range is £28,000 - £31,000.",
    "residence": "Candidates must be based in the United States.",
    "designation": "Membership of CIPS is mandatory; ACCA required.",
}


def _screen_reason(desc):
    import text_screen
    cuts = text_screen.screen({"title": "Data Analyst", "desc": desc})["cuts"]
    assert cuts, desc
    return "; ".join(cuts)


def test_every_cut_the_screen_writes_names_the_settings_it_rests_on():
    # Eligibility, internal-only and another-language cuts named nothing: the reader
    # kept its own copy of the screen's words, and read only the languages the profile
    # gates, and a setting the profile left unset was no part at all. They rested on the
    # whole rules and lapsed on any change to them, so the next round paid to fetch and
    # screen every one again.
    want = {"eligibility": "search.py ELIGIBILITY", "internal only": "search.py INTERNAL_ONLY",
            "another language": "search.py LANGUAGES_HELD",
            "the gated language": "search.py LANGUAGE_GATE", "pay": "search.py SALARY_CUT_BELOW",
            "residence": "search.py LOCATION", "designation": "search.py DESIGNATION"}
    for kind, desc in _SCREEN_CUTS.items():
        assert want[kind] in exclude.cited(_screen_reason(desc)), kind


def test_a_screen_ruling_outlives_a_change_to_another_part(tmp_path, monkeypatch):
    path = _seen(tmp_path)
    for i, (kind, desc) in enumerate(_SCREEN_CUTS.items()):
        if kind != "pay":
            exclude.add(URL + str(i), _screen_reason(desc), "Data Analyst", "Oakmere Foods",
                        path=path)
    entries = json.load(open(path))["seen"]
    assert all(e["rests_on"] != exclude.ALL for e in entries.values())
    s = exclude.person.module("search")
    monkeypatch.setattr(s, "SALARY_CUT_BELOW", s.SALARY_CUT_BELOW + 1000, raising=False)
    urls, _ = throttle.ruled_out(entries)
    assert len(urls) == len(entries)


def test_a_ruling_on_an_unset_setting_lapses_when_the_person_sets_it(tmp_path, monkeypatch):
    import re
    path = _seen(tmp_path)
    exclude.add(URL, _screen_reason(_SCREEN_CUTS["internal only"]), "Data Analyst",
                "Oakmere Foods", path=path)
    s = exclude.person.module("search")
    monkeypatch.setattr(s, "INTERNAL_ONLY", re.compile(r"\binternal only\b", re.I), raising=False)
    urls, _ = throttle.ruled_out(json.load(open(path))["seen"])
    assert urls == {}


def test_a_pay_ruling_is_read_back_in_any_currency(monkeypatch):
    import text_screen
    for mark in ("C$", "CA$", "A$", "R$", "kr ", "£"):
        # A market that writes its money this way, as the screen is built for it.
        values, labelled = text_screen.money_parser(mark.strip(), "")
        monkeypatch.setattr(text_screen, "money_values", values)
        monkeypatch.setattr(text_screen, "labelled_value", labelled)
        monkeypatch.setattr(text_screen, "CUR", mark)
        reason = _screen_reason(_SCREEN_CUTS["pay"].replace("£", mark))
        assert throttle.range_top(reason) == 31_000, reason
        # Under the cut line, it still cuts: read as no figure, it was released as stale.
        assert not throttle.is_stale_exclusion(reason), reason
    for reason, top in (("range tops out at CA$28,000", 28_000), ("salary up to A$28,000", 28_000),
                        ("range R$20,000 - R$28,000", 28_000), ("tops out at kr 28 000", 28_000)):
        assert throttle.range_top(reason) == top, reason
