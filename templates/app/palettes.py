#!/usr/bin/env python3
"""The page's colours: rose pine, dawn for light and the main flavour for dark, Rose the accent.

Every colour the page shows is a token defined here, and nowhere else: templates/app/app.css
only names tokens. tools/app_page.py writes css() into the page ahead of the stylesheet,
and tests/test_the_page_colours_pass_contrast.py checks every pair below against WCAG 2.2.

    python3 templates/app/palettes.py    # both palettes and their contrast, as a table

The person chose it (2026-10-25): "switch to rose pine please just to get it a tiny bit warmer
in light mode ... similar to claude colours ... and make it look sleek and dark in the dark
mode", light and dark only, following the device. Employer-facing documents keep their own
designs; this is the app's own look only.

Each role follows rose pine's own usage (the palette's README, "Roles", and the role pages of
rosepinetheme.com/palette, read 2026-10-25): base is the primary background, so it is the page
around the cards; surface is the low-contrast background atop base for panels, so it is every
card; overlay is the medium-contrast background for inputs and active tabs; text is the
high-contrast foreground, subtle the medium (labels) and muted the low (decoration only here);
highlight med is the selection background paired with text; highlight high and the low
foregrounds are for borders. The accents keep their meaning: love for errors, gold for
warnings, foam for information, iris for links and hints, pine for the terminal's green. Five
deviations follow from legibility and from the person:

  - Rose is the one accent in both looks, as a fill with near-black ink on it (main's base):
    6.2:1 on dawn's rose, 10.4:1 on main's. It is the rose pine colour nearest Claude's own
    #d97757: dawn's rose is 18.6 apart from it (CIE76), and for the dark look main's rose
    was chosen over its gold. Gold is a little nearer by that sum (34.0 against 38.3) only
    because it is more saturated; its hue is yellow (77 degrees in CIELAB, rose 24, Claude's
    44), it is rose pine's warning colour, which the page shows for anything overdue, and
    rose keeps one accent across both looks. Both pass with the same ink (10.8 and 10.4).
  - Dawn's rose is too light to be seen against dawn's own panes, so a mark that must be seen
    there (a progress bar, the selected tab, a link's underline, a chart's bar) is that rose
    moved toward main's base only as far as 3:1 needs (WCAG 1.4.11); in the dark it is the
    rose itself. Focus is iris in both, the hint colour.
  - Dawn's base is near-white and its surface white, as light as Claude's own page beside it:
    the maintainer found dawn too warm (2026-10-26) and then the page "unnecessarily dark"
    next to Claude (2026-10-29). Cards are drawn by their edge, not by a darker page. The
    accent stays rose; the tints are dawn's own.
  - Links are in the text colour with an underline in the accent: the person asked for no
    coloured link text, and the underline is what marks a link.
  - Where a dawn colour is too faint for text (subtle, love, gold, foam, iris), the text
    token is that colour moved toward main's base only as far as 4.5:1 needs (WCAG 1.4.3);
    in the dark, main's pine is moved toward text for the same reason. The pure colour stays
    in fills and tints. Each value says which.
  - Main has nothing darker than its base, so the depths inside a card (tracks, wells) and
    the bar of tabs are base too, and a box that sits on the page carries a border.

Sources:
  [P] rose pine, github.com/rose-pine/palette (MIT), the published package v4.0.1
      (dist/index.js and dist/css/rose-pine-media.css, whose media file pairs dawn for light
      with main for dark), in the roles above. The repository's palette.json gives dawn's
      text as #464261 where the package and its CSS give #575279; the package is what themes
      are built from, so #575279 is used.
  [D] Derived here, as the note says: no source beyond the colours it starts from.

Only the colours are taken. The page carries no logo or name of rose pine, Anthropic or
Claude in its own interface.
"""
from __future__ import annotations

import sys

# Each token: (value, where it comes from). Order is the order written into the CSS.
DAWN = {
    "bg": ("#faf9f7", "[D] near-white with a trace of dawn's warmth, as light as Claude's own page beside it (the maintainer, 2026-10-29: the old base was \"unnecessarily dark\"): the page around the cards"),
    "surface": ("#ffffff", "[D] white: a panel atop base, every card, its edge drawn by line"),
    "sunk": ("#f3f1ee", "[D] dawn overlay with most of its warmth taken out: the depths, tracks and wells"),
    "raised": ("#ebe8e6", "[D] dawn highlight med lightened halfway to base: buttons and chips"),
    "raised-hover": ("#dfdad9", "[P] dawn highlight med: a button, hovered"),
    "ink": ("#575279", "[P] dawn text"),
    "muted": ("#6b6688", "[D] dawn subtle moved 42% toward text: labels, 4.5:1 on overlay"),
    "line": ("#dfdad9", "[P] dawn highlight med: the edge of a card, decoration only"),
    "line-strong": ("#797593", "[P] dawn subtle: a control's border, 4:1 on base and surface"),
    "accent": ("#575279", "[P] dawn text: a filled button is the page's own ink, with white on it, 7.3:1 (the maintainer, 2026-10-29: the peach with dark text was hard to read, and a deeper rose looked worse); rose stays for marks"),
    "accent-hover": ("#433e60", "[D] the ink fill a step deeper: white on it, 10:1"),
    "accent-ink": ("#ffffff", "[D] white on the ink fill, 7.3:1"),
    "accent-soft": ("#f9e7e0", "[D] dawn rose 16% on surface"),
    "mark": ("#c27674", "[D] dawn rose moved 11% toward main base: 3:1 on the depths, for bars and marks"),
    "link": ("#575279", "[P] dawn text: a link is the text colour, underlined"),
    "link-line": ("#c27674", "[D] the mark: a link's underline"),
    "focus": ("#907aa9", "[P] dawn iris: links and hints, 3.2:1 on overlay"),
    "chart-a": ("#c27674", "[D] the mark"),
    "chart-b": ("#286983", "[P] dawn pine: 5.1:1 on overlay"),
    "st-done": ("#286983", "[P] dawn pine"),
    "st-done-bg": ("#dde3e1", "[D] pine 16% on surface"),
    "st-running": ("#446e7a", "[D] dawn foam #56949f 30% toward main base"),
    "st-running-bg": ("#e4eae6", "[D] foam 16% on surface"),
    "st-waiting": ("#6b6688", "[D] the muted label colour"),
    "st-waiting-bg": ("#f2e9e1", "[P] dawn overlay"),
    "st-failed": ("#935368", "[D] dawn love #b4637a 21% toward main base"),
    "st-failed-bg": ("#f3e2e0", "[D] love 16% on surface"),
    "st-overdue": ("#8c612d", "[D] dawn gold #ea9d34 45% toward main base"),
    "st-overdue-bg": ("#fcebd4", "[D] gold 16% on surface"),
    "st-held": ("#726188", "[D] dawn iris #907aa9 25% toward main base"),
    "st-held-bg": ("#ede6e7", "[D] iris 16% on surface"),
    "toast-bg": ("#575279", "[P] dawn text: a message sits in inverse"),
    "toast-ink": ("#fffaf3", "[P] dawn surface"),
    "toast-hover": ("#75708f", "[D] surface 18% on text"),
    "selection": ("#dfdad9", "[P] dawn highlight med: the selection, paired with text"),
    "shadow": ("0 1px 2px rgb(87 82 121 / 0.08), 0 4px 16px rgb(87 82 121 / 0.08)", "[D] text, faint"),
    "doc-black": ("#000000", "[D] the black a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-navy": ("#1f3a5f", "[D] the navy a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-burgundy": ("#7a1f3d", "[D] the burgundy a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-forest": ("#22543c", "[D] the forest a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-teal": ("#1d5c63", "[D] the teal a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-plum": ("#4b2a6b", "[D] the plum a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-slate": ("#2f4858", "[D] the slate a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-blue": ("#3873b2", "[D] the blue a resume can take (templates/doc_style.py STYLES), shown as itself"),
}
MAIN = {
    "bg": ("#191724", "[P] main base: the primary background, the page around the cards"),
    "surface": ("#1f1d2e", "[P] main surface: a panel atop base, every card"),
    "sunk": ("#191724", "[P] main base: the depths inside a card, and the bar of tabs"),
    "raised": ("#26233a", "[P] main overlay: buttons and chips"),
    "raised-hover": ("#403d52", "[P] main highlight med"),
    "ink": ("#e0def4", "[P] main text"),
    "muted": ("#908caa", "[P] main subtle: labels"),
    "line": ("#403d52", "[P] main highlight med: the edge of a card, decoration only"),
    "line-strong": ("#6e6a86", "[P] main muted: a control's border, 3.2:1 on surface"),
    "accent": ("#ebbcba", "[P] main rose: a filled button, with near-black ink on it"),
    "accent-hover": ("#e9c1c3", "[D] main rose 15% toward text"),
    "accent-ink": ("#191724", "[P] main base: near-black ink on rose, 10.4:1"),
    "accent-soft": ("#403644", "[D] main rose 16% on surface"),
    "mark": ("#ebbcba", "[P] main rose: bars and marks"),
    "link": ("#e0def4", "[P] main text: a link is the text colour, underlined"),
    "link-line": ("#ebbcba", "[P] main rose: a link's underline"),
    "focus": ("#c4a7e7", "[P] main iris: links and hints"),
    "chart-a": ("#ebbcba", "[P] main rose"),
    "chart-b": ("#9ccfd8", "[P] main foam"),
    "st-done": ("#6b97b0", "[D] main pine #31748f moved 33% toward text, for 4.5:1"),
    "st-done-bg": ("#222b3e", "[D] pine 16% on surface"),
    "st-running": ("#9ccfd8", "[P] main foam"),
    "st-running-bg": ("#333949", "[D] foam 16% on surface"),
    "st-waiting": ("#908caa", "[P] main subtle"),
    "st-waiting-bg": ("#26233a", "[P] main overlay"),
    "st-failed": ("#eb6f92", "[P] main love"),
    "st-failed-bg": ("#3c293d", "[D] love 14% on surface"),
    "st-overdue": ("#f6c177", "[P] main gold"),
    "st-overdue-bg": ("#41373a", "[D] gold 16% on surface"),
    "st-held": ("#c4a7e7", "[P] main iris"),
    "st-held-bg": ("#39334c", "[D] iris 16% on surface"),
    "toast-bg": ("#e0def4", "[P] main text: inverse"),
    "toast-ink": ("#191724", "[P] main base"),
    "toast-hover": ("#c2c0d5", "[D] base 15% on text"),
    "selection": ("#403d52", "[P] main highlight med: the selection, paired with text"),
    "shadow": ("none", "[D] borders carry the edges in the dark, not shadows"),
    "doc-black": ("#000000", "[D] the black a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-navy": ("#1f3a5f", "[D] the navy a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-burgundy": ("#7a1f3d", "[D] the burgundy a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-forest": ("#22543c", "[D] the forest a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-teal": ("#1d5c63", "[D] the teal a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-plum": ("#4b2a6b", "[D] the plum a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-slate": ("#2f4858", "[D] the slate a resume can take (templates/doc_style.py STYLES), shown as itself"),
    "doc-blue": ("#3873b2", "[D] the blue a resume can take (templates/doc_style.py STYLES), shown as itself"),
}

PALETTES = {"light": DAWN, "dark": MAIN}
LOOKS = (("auto", "Match my device"), ("light", "Light"), ("dark", "Dark"))

# The pairs the page draws, and the ratio each must reach (WCAG 2.2: 1.4.3 text 4.5:1,
# 1.4.11 non-text 3:1). Large text never appears in a colour that body text does not.
SURFACES = ("bg", "surface", "sunk")
STATUSES = ("done", "running", "waiting", "failed", "overdue", "held")


def pairs() -> list:
    """(foreground, background, minimum, what it is) for every pair the page draws."""
    out = []
    for s in SURFACES:
        out += [("ink", s, 4.5, "body text"), ("muted", s, 4.5, "secondary text"), ("link", s, 4.5, "links")]
        out += [("focus", s, 3.0, "focus ring"), ("mark", s, 3.0, "bars, the selected tab, a link's underline")]
    out += [("ink", "raised", 4.5, "a button or chip"), ("ink", "raised-hover", 4.5, "a button, hovered"),
            ("line-strong", "bg", 3.0, "input and control borders"), ("line-strong", "surface", 3.0, "input and control borders"),
            ("link-line", "surface", 3.0, "a link's underline"), ("link-line", "bg", 3.0, "a link's underline"),
            ("ink", "accent-soft", 4.5, "the current section in the list"), ("accent-ink", "accent", 4.5, "text on a filled button"),
            ("accent-ink", "accent-hover", 4.5, "text on a filled button, hovered"), ("surface", "ink", 4.5, "a pressed filter"),
            ("toast-ink", "toast-bg", 4.5, "a message"), ("toast-ink", "toast-hover", 4.5, "a message's button, hovered"),
            ("ink", "selection", 4.5, "selected text"),
            ("chart-a", "surface", 3.0, "chart bars"), ("chart-b", "surface", 3.0, "chart bars"), ("chart-a", "sunk", 3.0, "a bar on its track"),
            ("chart-b", "sunk", 3.0, "a slow bar on its track"), ("mark", "sunk", 3.0, "progress on its track")]
    for st in STATUSES:
        out += [(f"st-{st}", f"st-{st}-bg", 4.5, f"{st}: a status word on its tint")]
        out += [(f"st-{st}", s, 4.5, f"{st}: a status line") for s in SURFACES]
    return out


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h: str) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def check() -> list:
    """Every pair, in both palettes, that falls short: empty when all pass."""
    bad = []
    for name, p in PALETTES.items():
        for fg, bg, need, what in pairs():
            r = ratio(p[fg][0], p[bg][0])
            if r < need:
                bad.append(f"{name}: {fg} on {bg} is {r:.2f}, needs {need} ({what})")
    return bad


def _block(p: dict, scheme: str | None = None) -> str:
    lines = [f"  --{k}: {v};  /* {why} */" for k, (v, why) in p.items()]
    if scheme:
        lines.append(f"  color-scheme: {scheme};")
    return "\n".join(lines)


def css() -> str:
    """The palettes as the page's first stylesheet.

    The host's own contract: every token first on bare :root (dawn), redefined for a dark
    device under prefers-color-scheme guarded by :not([data-theme="light"]), and again under
    :root[data-theme="dark"], so the Claude app's own appearance choice wins over the
    device. The person's choice on the page (data-look, kept on their device) wins over
    both. The order matters where two rules are equally specific.
    """
    dark = _block(MAIN, "dark")
    return "\n".join([
        "/* The palettes: generated by templates/app/palettes.py, with each colour's source. */",
        ":root {\n  color-scheme: light dark;\n" + _block(DAWN) + "\n}",
        ':root[data-theme="light"], :root[data-look="light"] { color-scheme: light; }',
        '@media (prefers-color-scheme: dark) {\n:root:not([data-theme="light"]):not([data-look="light"]) {\n' + dark + "\n}\n}",
        ':root[data-theme="dark"]:not([data-look="light"]), :root[data-look="dark"] {\n' + dark + "\n}",
        "dialog::backdrop { background: rgb(25 23 36 / 0.55); }  /* [D] main base as a scrim, in both */",
        "::selection { background: var(--selection); color: var(--ink); }",
    ])


def table() -> str:
    """Both palettes as a table, with the lowest ratio among the pairs each token is in."""
    keys = list(DAWN)
    rows = ["| token | " + " | ".join(PALETTES) + " |", "|---" * (len(PALETTES) + 1) + "|"]
    for k in keys:
        cells = []
        for p in PALETTES.values():
            v = p[k][0]
            low = [ratio(p[fg][0], p[bg][0]) for fg, bg, _, _ in pairs() if k in (fg, bg)]
            cells.append(v + (f" ({min(low):.2f})" if low and v.startswith("#") else ""))
        rows.append(f"| {k} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())
    problems = check()
    print("\n".join(problems) if problems else "\nEvery pair passes.")
    sys.exit(1 if problems else 0)
