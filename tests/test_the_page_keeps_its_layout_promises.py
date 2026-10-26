"""LAYOUT_SPEC section 7, a check for each line, on a phone and wide, light and dark.

Every section is measured once per model, width and theme (tests/app_page/harness.js,
S.layout), and each numbered line of the checklist is its own test over those numbers. The
models are the sample with every kind of item, a set-up search with nothing found yet, and a
first run. The sample's brief is dated the day before: on the morning it lands the brief is
the first block on To do by design, which line 2 does not allow for. Line 15 is settled by
people (five-second and first-click results), not by a test.

KNOWN holds what the page does not meet yet, each one named: the test fails on a new gap and
on a fixed one, so the list only ever shrinks by being taken out. Every person and employer
here is invented.
"""
from __future__ import annotations

import copy
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import EMPTY, _write  # noqa: E402

TWEAK_ITEM = "app-ellerwick-insight"
CLOCK = "2026-10-25T09:00:00Z"
BEGINNER = ("chat", "cloud", "repository", "branch", "config")
SIZES = {"phone": {"width": 375, "height": 812}, "wide": {"width": 1440, "height": 900}}
FIRST_LIMIT = {"phone": 270, "wide": 300}

# What the page does not meet yet: (line, section, what) and the widths it shows at, the same
# in both themes.
BOTH = {"phone", "wide"}
KNOWN = {
    # 8: an email note carries Copy subject beside Copy message and its Sent button.
    (8, "drafts-messages", "msg-priya-thanks"): BOTH, (8, "drafts-messages", "msg-noor-1"): BOTH,
    # 8: the LinkedIn download card shows its steps as buttons (and Choose its folder, wide).
    (8, "todo", "linkedin-export"): BOTH,
    # 9: two to-dos about one role both say Open in Jobs, named after the same title.
    (9, "todo", "Open in Jobs"): BOTH,
    # 9: two applications at one employer, each row named by the employer alone.
    (9, "progress", "Ellerwick Trust"): {"wide"},
}


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("layout")
    sample = copy.deepcopy(_sample())
    sample["brief"] = dict(sample["brief"], date="2026-10-24")
    return {"sample": _write(tmp, "sample", sample),
            "nothing": _write(tmp, "nothing", dict(EMPTY, setup={"state": "done", "steps": []})),
            "setup": _write(tmp, "setup", EMPTY)}


_MEASURED: dict = {}


def _measure(run, pages, model, vp, scheme):
    key = (model, vp, scheme)
    if key not in _MEASURED:
        full = model == "sample"
        got = run("layout", html=pages[model], viewport=SIZES[vp], scheme=scheme, fake={"canSend": "available"},
                  clock=CLOCK, sheets=full, big=full, tweakItem=TWEAK_ITEM)
        assert not got["errors"], got["errors"]
        _MEASURED[key] = got
    return _MEASURED[key]


@pytest.fixture(params=["phone", "wide"])
def vp(request):
    return request.param


@pytest.fixture(params=["light", "dark"])
def scheme(request):
    return request.param


@pytest.fixture
def layouts(run, pages, vp, scheme):
    return {m: _measure(run, pages, m, vp, scheme) for m in pages}


def _gaps(found, line, vp):
    """The gaps found on one line, less the ones KNOWN, and the KNOWN ones no longer there."""
    known = {k for k, at in KNOWN.items() if k[0] == line and vp in at}
    new = sorted(set(found) - known)
    gone = sorted(k for k in known if k not in found)
    return new, gone


def _sections(layouts):
    for model, got in layouts.items():
        for sec, v in got["sections"].items():
            yield model, sec, v, got["frames"][sec]


# ------------------------------------------------------------------ 1 to 4: the top of a screen


def test_1_every_sections_first_item_is_near_the_top(layouts, vp):
    late = [(m, s, v["first"]) for m, s, v, _ in _sections(layouts) if v["first"] is not None and v["first"] > FIRST_LIMIT[vp]]
    assert not late, late


def test_2_at_most_three_blocks_above_the_first_item_and_no_here(layouts):
    bad = []
    for m, s, v, _ in _sections(layouts):
        other = [b for b in v["blocks"] if not re.search(r"\b(summary|controls|active-filters)\b", b)]
        if other or len(v["blocks"]) > 3 or v["here"] or v["activeFilters"]:
            bad.append((m, s, v["blocks"], v["here"], v["activeFilters"]))
    assert not bad, bad


def test_3_one_plain_summary_first_under_the_title(layouts):
    bad = []
    for m, s, v, _ in _sections(layouts):
        text = v["summaries"][0] if v["summaries"] else ""
        sentences = [x for x in re.split(r"(?<=[.!?])\s*(?=[A-Z])", text) if x]
        jargon = [w for w in BEGINNER if re.search(r"\b%s\b" % w, text, re.I)]
        if len(v["summaries"]) != 1 or not text or not v["summaryFirst"] or max(map(len, sentences)) > 90 or jargon:
            bad.append((m, s, v["summaries"], v["summaryFirst"], jargon))
    assert not bad, bad


def test_4_the_control_row_is_one_row_with_no_sideways_scroll(layouts):
    bad = [(m, s, c) for m, s, v, _ in _sections(layouts) for c in v["controls"] if c["spread"] > 4 or c["scroll"] > 0]
    assert not bad, bad


# ------------------------------------------------------------------ 5 to 7: the frame


def test_5_the_top_bar_is_small_and_the_pill_gives_way_to_the_rail(layouts, vp):
    bad = []
    for m, s, _, f in _sections(layouts):
        if vp == "phone" and (f["topH"] > 56 or set(f["topKids"]) - {"brand", "screen", "conn", "conn-btn", "pill", "gear"}):
            bad.append((m, s, f["topH"], f["topKids"]))
        if vp == "wide" and f["rail"] and f["pill"]:
            bad.append((m, s, "pill beside the rail"))
    assert not bad, bad


def test_6_five_tabs_and_only_to_do_shows_a_number_the_summary_shares(layouts, vp):
    bad = []
    for m, s, _, f in _sections(layouts):
        if vp == "phone" and f["tabs"] != 5:
            bad.append((m, s, "tabs", f["tabs"]))
        if [b for b in f["badges"] if not b["where"].startswith("To do")] or f["navNumbers"]:
            bad.append((m, s, f["badges"], f["navNumbers"]))
    assert not bad, bad
    for m, got in layouts.items():
        badges = got["frames"]["todo"]["badges"]
        if badges:
            first = re.search(r"\d+", got["sections"]["todo"]["summaries"][0])
            assert first and first.group(0) == re.search(r"\d+", badges[0]["text"]).group(0), (m, badges, got["sections"]["todo"]["summaries"])


def test_7_at_most_one_primary_button_and_no_answer_is_primary(layouts):
    bad = [(m, s, v["primary"], v["qPrimary"]) for m, s, v, _ in _sections(layouts) if v["primary"] > 1 or v["qPrimary"]]
    assert not bad, bad


# ------------------------------------------------------------------ 8 to 12: cards, names, type


def test_8_a_closed_card_has_one_state_one_alert_two_buttons_one_link_and_more(layouts, vp):
    found = set()
    for _, s, v, _ in _sections(layouts):
        for c in v["cards"]:
            if c["states"] > 1 or c["alerts"] + c["suggests"] > 1 or c["buttons"] > 2 or c["links"] > 1 or c["more"] > 1:
                found.add((8, s, c["item"]))
    new, gone = _gaps(found, 8, vp)
    assert not new, ("cards over the anatomy", new)
    assert not gone, ("met now: take these out of KNOWN", gone)


def test_9_no_two_controls_share_a_name_and_no_item_shows_twice(layouts, vp):
    found = {(9, s, n) for _, s, v, _ in _sections(layouts) for n in v["dupNames"]}
    twice = [(m, s, v["dupItems"]) for m, s, v, _ in _sections(layouts) if v["dupItems"]]
    assert not twice, twice
    new, gone = _gaps(found, 9, vp)
    assert not new, ("controls sharing a name", new)
    assert not gone, ("met now: take these out of KNOWN", gone)


def test_10_a_first_screen_keeps_to_seven_type_styles_three_weights_three_tones(layouts):
    bad = [(m, s, v["pairs"], v["weights"], v["tones"]) for m, s, v, _ in _sections(layouts)
           if len(v["pairs"]) > 7 or set(v["weights"]) - {"400", "600", "700"} or len(v["tones"]) > 3]
    assert not bad, bad


def test_11_spacing_keeps_to_the_scale(vp, scheme):
    # The same stylesheet at every width and theme; asked of each so the line reads like the rest.
    with open(os.path.join(ROOT, "templates", "app", "app.css"), encoding="utf-8") as fh:
        css = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
    scale = {0, 2, 4, 8, 12, 16, 20, 24, 32, 44}
    tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", css))
    bad = []
    for prop, val in re.findall(r"(?:^|[;{\s])(gap|row-gap|column-gap|padding(?:-[a-z-]+)?|margin(?:-[a-z-]+)?)\s*:\s*([^;}]+)", css):
        for px in re.findall(r"(-?\d*\.?\d+)px", val):
            if abs(float(px)) not in scale:
                bad.append((prop, val.strip()))
        for name in re.findall(r"var\((--[\w-]+)", val):
            if name == "--tabs-h":
                continue  # the tab bar's own height, kept clear of, not a space between things
            got = re.fullmatch(r"\s*(\d+)px\s*", tokens.get(name, ""))
            if not got or int(got.group(1)) not in scale:
                bad.append((prop, name, tokens.get(name)))
    assert not bad, bad


def test_12_an_empty_list_says_one_short_thing_with_one_button(layouts):
    bad = []
    for m, s, v, _ in _sections(layouts):
        if len(v["empties"]) > 1:
            bad.append((m, s, "empties", len(v["empties"])))
        bad += [(m, s, e) for e in v["empties"] if e["buttons"] > 1 or e["words"] > 25]
    assert not bad, bad
    assert any(v["empties"] for m, s, v, _ in _sections(layouts) if m == "nothing"), "the empty model shows no empty state"


# ------------------------------------------------------------------ 13 and 14: sheets and big text


def test_13_sheets_sit_at_the_bottom_with_close_on_top_and_give_focus_back(layouts, vp):
    sheets = layouts["sample"]["sheets"]
    if vp == "wide":
        # Wide, the Tweak panel takes the rail rather than a sheet; the Filter and Work sheets
        # still close from their top row and give focus back.
        sheets = {k: m for k, m in sheets.items() if k in ("filter", "work") and m}
    else:
        assert set(sheets) >= {"filter", "tweak", "work"} and all(sheets[k] for k in ("filter", "tweak", "work")), sheets
    bad = []
    for kind, m in sheets.items():
        if kind == "filterAt":
            continue
        phone = vp == "phone"
        if (phone and (m["bottom"] < m["vh"] - 2 or m["h"] > 0.85 * m["vh"])) or not m["close"] or m["closeRow"] > 48 or not m["focusBack"]:
            bad.append((kind, m))
    assert not bad, bad


def test_14_at_double_text_nothing_scrolls_sideways_or_is_cut(layouts):
    bad = []
    for s, b in layouts["sample"]["big"].items():
        if b["overflow"] > 0 or b["clipped"] or any(r["spread"] > 4 or r["scroll"] > 0 for r in b["rows"]):
            bad.append((s, b))
    assert layouts["sample"]["big"], "nothing was measured at double text"
    assert not bad, bad


def test_15_is_settled_by_people_not_a_test():
    pytest.skip("Five-second and first-click results are recorded in NOTES.md by people before a release (LAYOUT_SPEC 6).")
