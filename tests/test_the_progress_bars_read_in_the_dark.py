"""The Brief's weekly bars keep their colour in the dark look.

The maintainer, 2026-11-05: the progress panel was "oddly grey and dark like the text and
bars". Past weeks were drawn at 55% opacity, so the rose blended into the dark surface as a
dull grey. Each past week's bar, blended at the opacity the page draws it, must still stand
3:1 against the panel in both looks, as the palette promises for chart bars.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "templates", "app"))

import palettes  # noqa: E402


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _lum(c):
    return sum(w * (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4) for w, x in zip((0.2126, 0.7152, 0.0722), c))


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_a_past_weeks_bar_stands_out_from_its_panel_in_both_looks():
    css = open(os.path.join(ROOT, "templates", "app", "app.css"), encoding="utf-8").read()
    rule = re.search(r"\.bp-spark \.bp-bar \{[^}]*\}", css).group(0)
    alpha = float(re.search(r"opacity:\s*([0-9.]+)", rule).group(1))
    token = re.search(r"background:\s*var\(--([a-z-]+)\)", rule).group(1)
    for look, pal in palettes.PALETTES.items():
        bar, surface = _rgb(pal[token][0]), _rgb(pal["surface"][0])
        seen = [alpha * b + (1 - alpha) * s for b, s in zip(bar, surface)]
        assert _ratio(seen, surface) >= 3.0, (look, alpha, round(_ratio(seen, surface), 2))


def test_the_menus_words_are_centred_on_their_icons_and_news_links_read_as_text():
    # The maintainer, 2026-11-06: the menu's words sat a little above the icons' middle, and the
    # news sources' underlines were the accent's colour; both read as the text's own now.
    css = open(os.path.join(ROOT, "templates", "app", "app.css"), encoding="utf-8").read()
    assert re.search(r"\.side-label \{[^}]*text-box: trim-both cap alphabetic", css)
    news = re.search(r"\.bp-news a \{[^}]*\}", css).group(0)
    assert "currentColor" in news and "1px" in news
