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


def test_a_soft_pills_edge_in_a_suggestion_box_reaches_3_to_1_on_the_box():
    """"Write to Juno" in a job's warm-route box had no edge (border-color transparent), 1.19:1
    against the box in the dark look (the review, 2026-11-05): its edge is a token that reaches
    3:1 on the box's tint in both looks, and that pair is one the check holds."""
    with open(CSS, encoding="utf-8") as fh:
        css = fh.read()
    rule = re.search(r"\.card\.app\) \.suggest \.btn\.secondary \{([^}]*)\}", css)
    assert rule, "the soft pill in a card's suggestion box has its own rule"
    edge = re.search(r"border-color:\s*var\(--([a-z-]+)\)", rule.group(1))
    assert edge, rule.group(1)
    box = re.search(r"^\.suggest \{[^}]*background:\s*var\(--([a-z-]+)\)", css, re.M)
    assert box, "the suggestion box has its tint"
    for look, pal in palettes.PALETTES.items():
        assert palettes.ratio(pal[edge.group(1)][0], pal[box.group(1)][0]) >= 3.0, (look, edge.group(1), box.group(1))
    assert (edge.group(1), box.group(1), 3.0) in [(f, b, n) for f, b, n, _w in palettes.pairs()]


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
