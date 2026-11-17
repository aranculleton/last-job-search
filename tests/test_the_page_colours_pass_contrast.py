"""Every colour on the person's page passes WCAG 2.2 in both looks, and comes from one place.

The page is warm paper and charcoal with clay the one mark (templates/app/palettes.py, the
redesign of 2026-11-16), in a light look and a dark one that follow the device. Each pair the
page draws is checked here by the WCAG formula: 4.5:1 for text (1.4.3), 3:1 for borders, focus
rings, bars and marks that carry meaning (1.4.11). The stylesheet itself names tokens and
never a colour, so a colour cannot slip in somewhere the check does not look. The browser
tests render every section in both looks and check what is on screen as well.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "templates", "app"))
import palettes  # noqa: E402

CSS = os.path.join(ROOT, "templates", "app", "app.css")
JS = os.path.join(ROOT, "templates", "app", "app.js")
HEX = re.compile(r"^#[0-9a-f]{6}$")
# Keywords that are not a colour of the page's own: the system's colours in forced-colours
# mode, and the CSS words for none and for the current text colour.
SYSTEM = {"Canvas", "CanvasText", "ButtonText", "ButtonFace", "Highlight", "HighlightText", "GrayText", "LinkText"}
CLAUDE = "#d97757"   # Claude's own clay, which the mark is near in hue


def _lab(h):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in palettes._rgb(h))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    k = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
    return 116 * k[1] - 16, 500 * (k[0] - k[1]), 200 * (k[1] - k[2])


def _hue(h):
    import math
    _, a, b = _lab(h)
    return math.degrees(math.atan2(b, a)) % 360


def _apart(h1, h2):
    d = abs(_hue(h1) - _hue(h2)) % 360
    return min(d, 360 - d)


def test_every_pair_in_both_looks_reaches_its_ratio():
    assert palettes.check() == []
    assert set(palettes.PALETTES) == {"light", "dark"}, "light and dark only: no theme to pick"


def test_a_soft_pill_in_a_suggestion_box_is_lifted_off_the_box_and_its_words_read():
    """"Write to Juno" in a job's warm-route box had no edge and the box's own fill, 1.19:1 in the
    dark look (the review, 2026-11-05), and a 3:1 edge then made it the one outlined pill among
    the soft ones (the redesign's second round, 2026-11-17). One soft look now: a pill in a sunk
    box is the colour of what floats, lifted off the box in both looks and by the card's shadow
    in the light, with no edge; its words in the ink reach 4.5:1 on it, a pair the check holds,
    and they and its fill say it is a button (WCAG 1.4.11 asks no edge of a labelled button)."""
    with open(CSS, encoding="utf-8") as fh:
        css = fh.read()
    rule = re.search(r"\.card\.app\) \.suggest \.btn\.secondary \{([^}]*)\}", css)
    assert rule, "the soft pill in a card's suggestion box has its own rule"
    fill = re.search(r"background:\s*var\(--([a-z-]+)\)", rule.group(1))
    assert fill, rule.group(1)
    assert re.search(r"border-color:\s*transparent", rule.group(1)), ("no edge of its own", rule.group(1))
    assert re.search(r"box-shadow:\s*var\(--shadow-card\)", rule.group(1)), ("lifted by the card's shadow", rule.group(1))
    box = re.search(r"^\.suggest \{[^}]*background:\s*var\(--([a-z-]+)\)", css, re.M)
    assert box, "the suggestion box has its tint"
    for look, pal in palettes.PALETTES.items():
        f, b = pal[fill.group(1)][0], pal[box.group(1)][0]
        assert palettes.luminance(f) > palettes.luminance(b) and palettes.ratio(f, b) >= 1.1, (look, "lifted off the box", fill.group(1), box.group(1))
        assert palettes.ratio(pal["ink"][0], f) >= 4.5, (look, "its words")
    assert ("ink", fill.group(1), 4.5) in [(fg, bg, n) for fg, bg, n, _w in palettes.pairs()] or fill.group(1) in palettes.SURFACES


def test_a_chosen_state_is_never_its_fill_alone():
    """The chosen segment, the chosen place in the side menu and the phone's chosen tab were their
    fill alone, 1.1 to 1.3:1 from their neighbours (the accessibility review, 2026-11-17: WCAG
    1.4.11, and 1.4.1 in Icons only). The side menu's place and the phone's tab carry a ring that
    reaches 3:1 where it is drawn. The chosen segment's ring made it a second, outlined family
    (the redesign's second round, 2026-11-17), so it is told by its words as well as its thumb:
    the ink at 600 against the others' grey at 500, with no edge, its thumb lifted off its track
    in both looks, and Highlight in forced colours."""
    css = open(CSS, encoding="utf-8").read()
    seg = re.search(r"\.seg-opt\[aria-pressed=\"true\"\], \.seg-opt:has\(input:checked\) \{([^}]*)\}", css)
    pills = re.search(r"\.pills \.choice:has\(input:checked\) \{([^}]*border-color[^}]*)\}", css)
    base = {"seg": re.search(r"^\.seg-opt \{([^}]*)\}", css, re.M), "pills": re.search(r"^\.pills \.choice \{([^}]*)\}", css, re.M)}
    for name, chosen in (("seg", seg), ("pills", pills)):
        assert chosen and base[name], name
        on, off = chosen.group(1), base[name].group(1)
        assert "border-color: transparent" in on and "line-strong" not in on, (name, "no edge of its own", on)
        assert "color: var(--ink)" in on and "font-weight: 600" in on, (name, "its words in the ink at 600", on)
        assert "color: var(--muted)" in off and "font-weight: 500" in off, (name, "the others grey at 500", off)
        fill = re.search(r"background:\s*var\(--([a-z-]+)\)", on).group(1)
        for look, pal in palettes.PALETTES.items():
            assert palettes.ratio(pal[fill][0], pal["seg-track"][0]) >= 1.1, (look, name, "the thumb lifted off its track")
    assert re.search(r"\.seg-opt\[aria-pressed=\"true\"\], \.seg-opt:has\(input:checked\), \.pills \.choice:has\(input:checked\) \{ forced-color-adjust: none; background: Highlight", css), "forced colours"
    for sel in (r"\.side-list a\[aria-current=\"page\"\] \{", r"\.tab\[aria-current=\"page\"\] \.tab-ic \{"):
        rule = re.search(sel + r"([^}]*)\}", css)
        assert rule and "inset 0 0 0 1px var(--mark)" in rule.group(1), sel
    want = {("line-strong", "thumb"), ("mark", "accent-soft"), ("mark", "surface"), ("mark", "bg")}
    held = {(f, b) for f, b, n, _w in palettes.pairs() if n >= 3.0}
    assert want <= held, want - held
    # The words that tell it apart read on the thumb and on the track.
    words = {(f, b) for f, b, n, _w in palettes.pairs() if n >= 4.5}
    assert {("ink", "thumb"), ("muted", "seg-track"), ("ink", "seg-track")} <= words


def test_a_track_and_a_tip_on_the_page_never_vanish_into_it():
    """In the dark the sunk track sat on the page at 1.01:1: Jobs' "Applied" floated as loose words
    beside a lone thumb, the Brief's tip was a ghost and your resume's card the page's own colour
    (the redesign's second round, 2026-11-17). Their colour is the track's, a step off the page in
    both looks, and a soft button on it is the thumb's, lifted off it."""
    css = open(CSS, encoding="utf-8").read()
    for sel in (r"^\.segctl \{", r"^\.pills \.pill-row \{", r"^\.bp-tip \{", r"^\.pin-offer \{", r"^\.quiet-card \{"):
        rule = re.search(sel + r"([^}]*)\}", css, re.M)
        assert rule and "background: var(--seg-track)" in rule.group(1), sel
    for look, pal in palettes.PALETTES.items():
        assert palettes.ratio(pal["seg-track"][0], pal["bg"][0]) >= 1.05, (look, "the track off the page")
        assert palettes.ratio(pal["thumb"][0], pal["seg-track"][0]) >= 1.1, (look, "a button lifted off the track")
    assert re.search(r":is\(\.bp-tip, \.pin-offer, \.quiet-card\) :is\([^)]*\.btn\.secondary[^{]*\{ background: var\(--thumb\); border-color: transparent", css)


def test_the_ratios_are_computed_by_the_wcag_formula():
    assert round(palettes.ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(palettes.ratio("#777777", "#ffffff"), 2) == 4.48


def test_the_filled_button_is_the_text_colour_in_both_looks_and_the_strongest_thing_on_a_screen():
    """The filled button was purple ink in light and pink in dark (the redesign's review,
    2026-11-16): one look in both now, the text colour itself, with the most contrast on the
    page, so the one next step is what the eye lands on."""
    for name, p in palettes.PALETTES.items():
        assert p["accent"][0] == p["ink"][0], name
        assert palettes.ratio(p["accent-ink"][0], p["accent"][0]) >= 12, name
        assert p["link"][0] == p["ink"][0], (name, "a link is the text colour, underlined only inside a sentence")


def test_quiet_text_is_clearly_quieter_than_the_text_and_still_easy_to_read():
    """Titles, body and facts were one purple-grey, 1.34:1 apart, so nothing led (the redesign's
    review, 2026-11-16). Quiet text is at least twice as quiet as the text on a card, and still
    4.5:1 on every background it sits on (the pairs check holds that)."""
    for name, p in palettes.PALETTES.items():
        ink, muted, card = p["ink"][0], p["muted"][0], p["surface"][0]
        assert palettes.ratio(ink, card) / palettes.ratio(muted, card) >= 2, name
        assert palettes.ratio(ink, card) >= 14, (name, "body text well past 7:1, for long reading")


def test_clay_is_the_one_mark_near_claudes_colour_and_never_a_state():
    for name, p in palettes.PALETTES.items():
        mark = p["mark"][0]
        assert _apart(mark, CLAUDE) < 15, (name, "the mark is Claude's clay in hue")
        assert p["chart-a"][0] == mark
        for st in palettes.STATUSES:
            assert p[f"st-{st}"][0] != mark, (name, st, "a state never borrows the mark")
        assert palettes.ratio(p["mark-on"][0], mark) >= 4.5 and palettes.ratio(p["mark-ink"][0], p["surface"][0]) >= 4.5


def test_focus_is_a_colour_no_state_and_no_mark_uses():
    for name, p in palettes.PALETTES.items():
        f = p["focus"][0]
        assert _apart(f, p["mark"][0]) > 60, name
        for st in ("done", "failed", "overdue", "waiting"):
            assert _apart(f, p[f"st-{st}"][0]) > 30, (name, st)


def test_each_state_keeps_its_meaning_in_both_looks():
    """Green done, blue running, amber late, red failed, violet held; today and tomorrow keep
    their green and gold (the maintainer, 2026-11-02: never red for today)."""
    want = {"done": (120, 175), "running": (200, 260), "overdue": (60, 100), "failed": (15, 50), "held": (285, 320)}
    for name, p in palettes.PALETTES.items():
        for st, (lo, hi) in want.items():
            assert lo <= _hue(p[f"st-{st}"][0]) <= hi, (name, st, round(_hue(p[f"st-{st}"][0])))
    assert palettes.LIGHT["day-today"][0] == "#16a34a" and palettes.LIGHT["day-tomorrow"][0] == "#b7791f"
    assert palettes.DARK["day-today"][0] == "#4ade80" and palettes.DARK["day-tomorrow"][0] == "#facc15"


def test_the_light_page_is_near_white_paper_with_white_cards():
    """As light as Claude's own page beside it (the maintainer, 2026-10-29), and warm."""
    p = palettes.LIGHT
    assert p["surface"][0] == "#ffffff"
    assert all(int(p["bg"][0][i:i + 2], 16) >= 0xf5 for i in (1, 3, 5)), "the page is near-white"
    assert palettes.ratio(p["bg"][0], p["surface"][0]) < 1.08, "no darker page around the cards"
    r, g, b = palettes._rgb(p["bg"][0])
    assert r >= g >= b and r > b, "warm, never cool or violet"


def test_both_looks_name_the_same_tokens_and_every_state():
    keys = list(palettes.DAWN)
    for name, p in palettes.PALETTES.items():
        assert list(p) == keys, name
        for k, (v, why) in p.items():
            assert why.startswith("["), (name, k, "every colour says where it comes from")
            if k not in ("shadow", "shadow-card"):
                assert HEX.match(v), (name, k, v)
    for st in palettes.STATUSES:
        assert f"st-{st}" in keys and f"st-{st}-bg" in keys
    assert set(palettes.STATUSES) == {"done", "running", "waiting", "failed", "overdue", "held"}



def test_the_dark_look_is_never_pure_black_and_raises_cards_by_lightening_them():
    p = palettes.DARK
    assert p["bg"][0] != "#000000" and p["sunk"][0] != "#000000"
    lum = palettes.luminance
    # The depths are darker than the page, every card lighter, what floats lighter again.
    assert lum(p["sunk"][0]) <= lum(p["bg"][0]) < lum(p["surface"][0]) < lum(p["overlay"][0])
    assert p["shadow-card"][0] == "none", "in the dark a card's edge is its hairline, not a shadow"
    assert p["ink"][0] != "#ffffff", "no pure white text on the dark"


def test_the_stylesheet_names_tokens_and_never_a_colour():
    css = open(CSS, encoding="utf-8").read()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.search(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(", css)
    forced = css[css.index("@media (forced-colors: active)"):]
    forced = forced[:forced.index("\n}\n")]
    outside = css.replace(forced, "")
    named = re.findall(r":\s*([A-Za-z]+)\s*[;}]", outside)
    colourish = {"white", "black", "red", "green", "blue", "gray", "grey", "orange", "purple", "yellow"}
    assert not [n for n in named if n.lower() in colourish or n in SYSTEM], "system colours only in forced-colours mode"
    for word in re.findall(r"\b([A-Z][A-Za-z]+)\b", forced):
        assert word in SYSTEM or word in {"Text"}, word
    used = set(re.findall(r"var\(--([a-z0-9-]+)", css))
    defined = set(palettes.DAWN) | set(re.findall(r"--([a-z0-9-]+):", css))
    assert used <= defined, used - defined


def test_the_script_writes_no_colour_either():
    js = open(JS, encoding="utf-8").read()
    assert not re.search(r"['\"]#[0-9a-fA-F]{3,8}['\"]|\brgba?\(|\bhsla?\(", js)
    # Inline styles set sizes only, never a colour: a bar's width, and since 4.8 a weekly bar's
    # height (the chart drawn as boxes on a baseline, not a stretched picture).
    assert set(re.findall(r'style: "([^"]*)', js)) <= {"width:", "height:"}, "inline styles set sizes only"


def test_the_generated_css_follows_the_hosts_contract_and_the_persons_choice():
    css = palettes.css()
    first = css.index(":root {")
    assert css.index("--bg:", first) < css.index("@media"), "every token first on bare :root"
    assert ":root {\n  color-scheme: light dark;" in css
    assert ':root[data-theme="light"], :root[data-look="light"] { color-scheme: light; }' in css
    assert '@media (prefers-color-scheme: dark) {\n:root:not([data-theme="light"]):not([data-look="light"])' in css
    assert ':root[data-theme="dark"]:not([data-look="light"]), :root[data-look="dark"]' in css
    assert "data-palette" not in css, "no theme to pick"
    assert "::selection { background: var(--selection)" in css
