"""Every colour on the person's page passes WCAG 2.2 in both looks, and comes from one place.

The page is rose pine (templates/app/palettes.py): dawn for light and the main flavour for
dark, with rose as the one accent, each role as rose pine's own usage gives it. Each pair the
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
# Rose pine's own colours (github.com/rose-pine/palette, the published package v4.0.1,
# dist/index.js, read 2026-10-25).
DAWN = {"base": "#faf4ed", "surface": "#fffaf3", "overlay": "#f2e9e1", "muted": "#9893a5", "subtle": "#797593",
        "text": "#575279", "love": "#b4637a", "gold": "#ea9d34", "rose": "#d7827e", "pine": "#286983",
        "foam": "#56949f", "iris": "#907aa9", "highlight_low": "#f4ede8", "highlight_med": "#dfdad9",
        "highlight_high": "#cecacd"}
MAIN = {"base": "#191724", "surface": "#1f1d2e", "overlay": "#26233a", "muted": "#6e6a86", "subtle": "#908caa",
        "text": "#e0def4", "love": "#eb6f92", "gold": "#f6c177", "rose": "#ebbcba", "pine": "#31748f",
        "foam": "#9ccfd8", "iris": "#c4a7e7", "highlight_low": "#21202e", "highlight_med": "#403d52",
        "highlight_high": "#524f67"}
CLAUDE = "#d97757"


def test_every_pair_in_both_looks_reaches_its_ratio():
    assert palettes.check() == []
    assert set(palettes.PALETTES) == {"light", "dark"}, "light and dark only: no theme to pick"


def test_the_ratios_are_computed_by_the_wcag_formula():
    assert round(palettes.ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(palettes.ratio("#777777", "#ffffff"), 2) == 4.48


def test_rose_is_a_fill_with_near_black_ink_and_its_marks_are_shaded_only_where_dawn_needs_it():
    dawn, main = palettes.DAWN, palettes.MAIN
    assert dawn["accent"][0] == DAWN["rose"] and main["accent"][0] == MAIN["rose"], "the fill is rose itself, never a brown"
    for p in (dawn, main):
        assert p["accent-ink"][0] == MAIN["base"]
        assert palettes.ratio(p["accent-ink"][0], p["accent"][0]) >= 4.5
    # Dawn's rose cannot be a mark on dawn's own panes, nor carry light text: hence the shade,
    # and only as far as 3:1 needs.
    assert palettes.ratio(DAWN["rose"], DAWN["overlay"]) < 3 and palettes.ratio(DAWN["surface"], DAWN["rose"]) < 4.5
    assert dawn["mark"][0] == "#bc7371" and 3 <= palettes.ratio(dawn["mark"][0], dawn["sunk"][0]) < 3.1
    assert main["mark"][0] == MAIN["rose"]
    assert dawn["link"][0] == dawn["ink"][0] and main["link"][0] == main["ink"][0], "links are the text colour, underlined"
    assert dawn["focus"][0] == DAWN["iris"] and main["focus"][0] == MAIN["iris"]


def test_the_dark_accent_is_the_rose_pine_colour_that_reads_as_claudes_and_is_not_the_warning_colour():
    """Rose over gold for the dark look: nearer Claude's colour in hue, the same accent as
    the light look, and gold is rose pine's warning colour, which the page shows as overdue."""
    import math

    def lab(h):
        def f(v):
            v /= 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = (f(v) for v in palettes._rgb(h))
        x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
        k = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
        return 116 * k[1] - 16, 500 * (k[0] - k[1]), 200 * (k[1] - k[2])

    def hue(h):
        _, a, b = lab(h)
        return math.degrees(math.atan2(b, a))

    assert abs(hue(MAIN["rose"]) - hue(CLAUDE)) < abs(hue(MAIN["gold"]) - hue(CLAUDE))
    assert palettes.MAIN["st-overdue"][0] == MAIN["gold"], "gold already means late"
    assert math.dist(lab(DAWN["rose"]), lab(CLAUDE)) < 20, "dawn's rose is near Claude's own colour"


def test_both_looks_name_the_same_tokens_and_every_state():
    keys = list(palettes.DAWN)
    for name, p in palettes.PALETTES.items():
        assert list(p) == keys, name
        for k, (v, why) in p.items():
            assert why.startswith("["), (name, k, "every colour says where it comes from")
            if k != "shadow":
                assert HEX.match(v), (name, k, v)
    for st in palettes.STATUSES:
        assert f"st-{st}" in keys and f"st-{st}-bg" in keys
    assert set(palettes.STATUSES) == {"done", "running", "waiting", "failed", "overdue", "held"}


def test_the_colours_are_rose_pines_own_where_they_are_used_in_its_roles():
    for name, flavour in (("light", DAWN), ("dark", MAIN)):
        p = palettes.PALETTES[name]
        for k, (v, why) in p.items():
            if why.startswith("[P]"):
                assert v in flavour.values() or v == MAIN["base"], (name, k, v)
        assert p["bg"][0] == flavour["base"] and p["surface"][0] == flavour["surface"]
        assert p["sunk"][0] in (flavour["overlay"], flavour["base"])
        assert p["ink"][0] == flavour["text"] and p["line"][0] == flavour["highlight_med"]
        assert p["selection"][0] == flavour["highlight_med"], "rose pine pairs a selection with text"
        assert p["line-strong"][0] in (flavour["subtle"], flavour["muted"])
    assert palettes.MAIN["muted"][0] == MAIN["subtle"], "quiet text is subtle, never muted, which is too faint"
    # Status colours keep rose pine's meanings: love for errors, gold for warnings, foam for
    # information, iris for hints, pine for done.
    assert palettes.MAIN["st-failed"][0] == MAIN["love"] and palettes.MAIN["st-overdue"][0] == MAIN["gold"]
    assert palettes.MAIN["st-running"][0] == MAIN["foam"] and palettes.MAIN["st-held"][0] == MAIN["iris"]
    assert palettes.DAWN["st-done"][0] == DAWN["pine"]
    for st, src in (("failed", "love"), ("overdue", "gold"), ("running", "foam"), ("held", "iris")):
        assert DAWN[src] in palettes.DAWN[f"st-{st}"][1], (st, "a dawn status names the colour it is shaded from")
    assert MAIN["pine"] in palettes.MAIN["st-done"][1]


def test_the_dark_look_is_never_pure_black_and_raises_cards_by_lightening_them():
    p = palettes.MAIN
    assert p["bg"][0] != "#000000" and p["sunk"][0] != "#000000"
    lum = palettes.luminance
    # Main has nothing darker than its base: the depths are base, the page is base, and
    # every card is lighter.
    assert lum(p["sunk"][0]) <= lum(p["bg"][0]) < lum(p["surface"][0]) < lum(p["raised"][0])
    assert p["shadow"][0] == "none", "in the dark, edges are borders, not shadows"
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
    assert set(re.findall(r'style: "([^"]*)', js)) == {"width:"}, "inline styles set widths only"


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
