#!/usr/bin/env python3
"""The page's colours: warm paper and charcoal, with clay the one mark, in light and dark.

Every colour the page shows is a token defined here, and nowhere else: templates/app/app.css
only names tokens. tools/app_page.py writes css() into the page ahead of the stylesheet,
and tests/test_the_page_colours_pass_contrast.py checks every pair below against WCAG 2.2.

    python3 templates/app/palettes.py    # both palettes and their contrast, as a table

The redesign of 2026-11-16 (the maintainer: "its starting to look dated, not modern, and hard
to use or look at for a while ... feel free to change ANYTHING ... colours"). The rose pine
palette chosen on 2026-10-25 drew titles, body, links, focus and the filled button all in one
purple-grey (#575279), with its quiet text only 1.34:1 away from it, so nothing led the eye;
and its filled button was purple ink in light and pink in dark. The person had asked for
something "a tiny bit warmer ... similar to claude colours ... sleek and dark in the dark mode";
Claude's own look is warm paper and charcoal with a clay accent, not violet, so:

  - Text is warm charcoal on near-white paper in light (16.8:1 on a card) and warm off-white on
    near-black in dark (14.8:1), never pure black or white. Quiet text is a warm grey at least
    4.8:1 on every background it can sit on, 2.9 times quieter than the text in light.
  - The filled button is the text colour itself, the same in both looks (charcoal with white in
    light, off-white with charcoal in dark): calm, and the strongest thing on a screen.
  - Clay is the one mark: badges, the selected place's icon, progress, a score's ring, a link's
    hover. As a fill it carries white (light) or charcoal (dark); as text it is mark-ink.
  - Focus is blue, which no state and no mark uses, so a keyboard's ring is never mistaken for
    either.
  - States keep their meanings: green done, blue running or information, amber late, red
    failed or removing, warm grey waiting, violet held. Today and tomorrow keep their green and
    gold (the maintainer, 2026-11-02: never red for today).
  - Cards are white on paper with a hairline and, in light only, the faintest shadow; in the
    dark a card is a step lighter than the page and carries its hairline alone.

Sources: every value is derived here ([D]); the resume colours are the documents' own.
"""
from __future__ import annotations

import sys

# Each token: (value, where it comes from). Order is the order written into the CSS.
_DOCS = {
    "doc-black": "#000000", "doc-navy": "#1f3a5f", "doc-burgundy": "#7a1f3d", "doc-forest": "#22543c",
    "doc-teal": "#1d5c63", "doc-plum": "#4b2a6b", "doc-slate": "#2f4858", "doc-blue": "#3873b2",
}


def _docs() -> dict:
    return {k: (v, "[D] the colour a resume can take (templates/doc_style.py STYLES), shown as itself") for k, v in _DOCS.items()}


LIGHT = {
    "bg": ("#f9f8f5", "[D] warm paper, near-white (the maintainer, 2026-10-29): the page around the cards"),
    "surface": ("#ffffff", "[D] white: every card, its edge drawn by line"),
    "overlay": ("#ffffff", "[D] white: what floats, a sheet, a menu, the Chat panel"),
    "sunk": ("#f2f0eb", "[D] paper a step deeper: wells, tracks, a segmented control's track"),
    "raised": ("#efece6", "[D] a secondary button's fill"),
    "raised-hover": ("#e9e5de", "[D] a secondary button, hovered: quiet text 4.5:1 on it (the accessibility review, 2026-11-17)"),
    "tile": ("#f2f0eb", "[D] a number's tile on the Brief: the well's paper, a step under the card"),
    "today-wash": ("#f8ebe4", "[D] the Brief's Today: clay at 12% on white, as the selected place"),
    # A person's initial sits on one of six soft fills, picked by their id, so one person is
    # one colour on every screen (the redesign's second round, 2026-11-17: Marisol was blue on
    # the Brief and clay in Contacts, and every Contacts avatar the same clay). Low in chroma
    # and none a state's own tint, so a colour never reads as where someone stands.
    "avatar-1": ("#f3e4da", "[D] sand clay: an initial's fill, ink over 13:1 on each of the six"),
    "avatar-2": ("#e2ebe0", "[D] sage: an initial's fill"),
    "avatar-3": ("#dfe7ed", "[D] mist: an initial's fill"),
    "avatar-4": ("#efe6cf", "[D] wheat: an initial's fill"),
    "avatar-5": ("#eee2e2", "[D] rose stone: an initial's fill"),
    "avatar-6": ("#e6e3dc", "[D] stone: an initial's fill"),
    "ink": ("#1f1d1a", "[D] warm charcoal: all text that matters, 16.8:1 on a card"),
    "muted": ("#6b665e", "[D] warm grey: facts, times, labels, 4.8:1 at worst"),
    "line": ("#e7e3dc", "[D] a hairline: a card's edge, a row's divider, decoration only"),
    "line-strong": ("#8c867c", "[D] an input's, a switch's or a checkbox's edge, 3:1 on paper and card"),
    "accent": ("#1f1d1a", "[D] the filled button is the text colour, with white on it, 16.8:1"),
    "accent-hover": ("#3a3631", "[D] the filled button, hovered: white on it, 12:1"),
    "accent-ink": ("#ffffff", "[D] white on the filled button"),
    "accent-soft": ("#f8ebe4", "[D] clay at 12% on white: the selected place, the Today card's wash"),
    "mark": ("#b4532f", "[D] clay: badges, the selected icon, progress, a score's ring, 4.4:1 at worst"),
    "mark-on": ("#ffffff", "[D] white on a clay fill, 5:1"),
    "mark-ink": ("#a34a29", "[D] clay as text, 5:1 at worst"),
    "link": ("#1f1d1a", "[D] a link is the text colour, underlined only inside a sentence"),
    "link-line": ("#8c867c", "[D] a link's underline inside a sentence: the control edge, 3:1 on paper and card"),
    "focus": ("#2563eb", "[D] blue, which no state uses: a keyboard's ring, 4.4:1 at worst"),
    "danger": ("#b42318", "[D] a removal's confirming fill, white on it 6.6:1"),
    "danger-ink": ("#ffffff", "[D] white on the removal fill"),
    "chart-a": ("#b4532f", "[D] the mark"),
    "chart-b": ("#1d6589", "[D] the running blue"),
    "st-done": ("#1f7a4d", "[D] green"),
    "st-done-bg": ("#e5f3ea", "[D] green's tint"),
    "st-running": ("#1d6589", "[D] blue: running, information"),
    "st-running-bg": ("#e3f0f5", "[D] blue's tint"),
    "st-waiting": ("#5f5a52", "[D] warm grey: waiting"),
    "st-waiting-bg": ("#f0ede8", "[D] warm grey's tint"),
    "st-failed": ("#b42318", "[D] red: failed"),
    "st-failed-bg": ("#fde9e6", "[D] red's tint"),
    "st-overdue": ("#875700", "[D] amber: late"),
    "st-overdue-bg": ("#fbefd6", "[D] amber's tint"),
    "st-held": ("#6b4fa0", "[D] violet: on hold"),
    "st-held-bg": ("#efe9f7", "[D] violet's tint"),
    "toast-bg": ("#1f1d1a", "[D] charcoal: a message sits in inverse"),
    "toast-ink": ("#f7f6f3", "[D] paper on charcoal"),
    "toast-hover": ("#3a3631", "[D] a message's button, hovered"),
    "selection": ("#f3d9cc", "[D] clay's tint: selected text"),
    "thumb": ("#ffffff", "[D] the chosen segment of a segmented control, the card colour on its sunk track, ringed in line-strong (3.2:1 on the track)"),
    "scrim": ("#141312", "[D] the shade behind a sheet, drawn at 45% (app.css): the page steps back and only the sheet, its ink 16.8:1 on overlay, is read"),
    "shadow": ("0 12px 32px rgb(31 29 26 / 0.14), 0 2px 6px rgb(31 29 26 / 0.06)", "[D] what floats: a sheet, a menu, the Chat panel"),
    "shadow-card": ("0 1px 2px rgb(31 29 26 / 0.05)", "[D] a card's faintest lift, light only"),
    **_docs(),
    # Today and tomorrow on the strip and Coming up: seen at a glance, never red (the
    # maintainer, 2026-11-02: red "promotes alarmism", pine and iris were too faint).
    "day-today": ("#16a34a", "[D] a clear green for today, 3.3:1 on surface"),
    "day-tomorrow": ("#b7791f", "[D] a clear gold for tomorrow, 3.6:1 on surface"),
}
DARK = {
    "bg": ("#141312", "[D] warm near-black: the page, never pure black"),
    "surface": ("#1d1c1a", "[D] a card, a step lighter than the page"),
    "overlay": ("#252321", "[D] what floats, a step lighter again"),
    "sunk": ("#131211", "[D] the depths inside a card"),
    "raised": ("#2a2825", "[D] a secondary button's fill"),
    "raised-hover": ("#34322e", "[D] a secondary button, hovered"),
    "tile": ("#2a2825", "[D] a number's tile on the Brief, raised: the depths vanished into a dark card"),
    "today-wash": ("#1d1c1a", "[D] the Brief's Today: a card like the rest under its clay strip, never a brown block"),
    "avatar-1": ("#3d2b22", "[D] sand clay, deepened: an initial's fill, ink over 11:1 on each of the six"),
    "avatar-2": ("#26332a", "[D] sage, deepened"),
    "avatar-3": ("#24303a", "[D] mist, deepened"),
    "avatar-4": ("#383020", "[D] wheat, deepened"),
    "avatar-5": ("#3a2a2c", "[D] rose stone, deepened"),
    "avatar-6": ("#302e2a", "[D] stone, deepened"),
    "ink": ("#f2efe9", "[D] warm off-white, never pure white: 14.8:1 on a card"),
    "muted": ("#a9a39a", "[D] warm grey: 5.5:1 at worst"),
    "line": ("#2e2c29", "[D] a hairline"),
    "line-strong": ("#807a71", "[D] an input's, a switch's or a checkbox's edge, 4:1 on a card, 3:1 on the soft clay and a hovered button (2026-11-17)"),
    "accent": ("#f2efe9", "[D] the filled button is the text colour, with charcoal on it"),
    "accent-hover": ("#ffffff", "[D] the filled button, hovered"),
    "accent-ink": ("#1a1917", "[D] charcoal on the filled button, 15.3:1"),
    "accent-soft": ("#3a2922", "[D] clay at 16% on a card: the selected place"),
    "mark": ("#e48a6b", "[D] clay, lifted for the dark: 5.4:1 at worst"),
    "mark-on": ("#1a1917", "[D] charcoal on a clay fill, 6.8:1"),
    "mark-ink": ("#f0a68b", "[D] clay as text, 6.9:1 at worst"),
    "link": ("#f2efe9", "[D] a link is the text colour"),
    "link-line": ("#807a71", "[D] a link's underline inside a sentence: the control edge, 4:1 on a card, 3.2:1 on the soft clay"),
    "focus": ("#8ab4ff", "[D] blue: a keyboard's ring, 6.6:1 at worst"),
    "danger": ("#ff8f84", "[D] a removal's confirming fill, charcoal on it"),
    "danger-ink": ("#1a1917", "[D] charcoal on the removal fill"),
    "chart-a": ("#e48a6b", "[D] the mark"),
    "chart-b": ("#7fc6e2", "[D] the running blue"),
    "st-done": ("#6fd39b", "[D] green"),
    "st-done-bg": ("#18301f", "[D] green's tint"),
    "st-running": ("#7fc6e2", "[D] blue"),
    "st-running-bg": ("#162b35", "[D] blue's tint"),
    "st-waiting": ("#b8b2a8", "[D] warm grey"),
    "st-waiting-bg": ("#2a2825", "[D] warm grey's tint"),
    "st-failed": ("#ff8f84", "[D] red"),
    "st-failed-bg": ("#3b1d1b", "[D] red's tint"),
    "st-overdue": ("#f2c25c", "[D] amber"),
    "st-overdue-bg": ("#352a12", "[D] amber's tint"),
    "st-held": ("#c9aef2", "[D] violet"),
    "st-held-bg": ("#2c2440", "[D] violet's tint"),
    "toast-bg": ("#f2efe9", "[D] inverse"),
    "toast-ink": ("#1a1917", "[D] charcoal"),
    "toast-hover": ("#d9d4cc", "[D] a message's button, hovered"),
    "selection": ("#4a3328", "[D] clay's tint: selected text"),
    "thumb": ("#34322e", "[D] the chosen segment, lifted off its track, ringed in line-strong (3:1 on it, 4.4:1 on the track)"),
    "scrim": ("#000000", "[D] the shade behind a sheet, drawn at 45%: the page darkens and the sheet, a step lighter with its shadow, stands out"),
    "shadow": ("0 16px 40px rgb(0 0 0 / 0.55)", "[D] what floats"),
    "shadow-card": ("none", "[D] a card in the dark carries its hairline alone"),
    **_docs(),
    "day-today": ("#4ade80", "[D] a bright green for today, 9.5:1 on surface"),
    "day-tomorrow": ("#facc15", "[D] a bright yellow for tomorrow, 10.8:1 on surface"),
}
# The names the tests and older notes use for the two looks.
DAWN, MAIN = LIGHT, DARK

PALETTES = {"light": LIGHT, "dark": DARK}
LOOKS = (("auto", "Match my device"), ("light", "Light"), ("dark", "Dark"))

# The pairs the page draws, and the ratio each must reach (WCAG 2.2: 1.4.3 text 4.5:1,
# 1.4.11 non-text 3:1). Large text never appears in a colour that body text does not.
SURFACES = ("bg", "surface", "sunk", "overlay")
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
            ("chart-b", "sunk", 3.0, "a slow bar on its track"), ("mark", "sunk", 3.0, "progress on its track"),
            ("day-today", "surface", 3.0, "today's dots"), ("day-today", "bg", 3.0, "today's mark on Coming up"),
            ("day-tomorrow", "surface", 3.0, "tomorrow's dots"), ("day-tomorrow", "bg", 3.0, "tomorrow's mark on Coming up")]
    # Quiet text and the clay as text wherever they can sit, and the ring on a button.
    for s in ("raised", "accent-soft"):
        out += [("muted", s, 4.5, "secondary text on " + s), ("focus", s, 3.0, "focus ring on " + s)]
    out += [("mark-ink", s, 4.5, "clay as text") for s in SURFACES + ("accent-soft",)]
    out += [("mark-on", "mark", 4.5, "text on a clay fill"), ("mark", "raised", 3.0, "a mark on a button"),
            ("danger-ink", "danger", 4.5, "text on the removal fill"), ("ink", "overlay", 4.5, "text on what floats"),
            ("line-strong", "sunk", 3.0, "a chosen segment's ring on its track"),
            # The pairs the selected states and the soft clay draw (the accessibility review,
            # 2026-11-17): a ring that says which is chosen, words on a hovered button.
            ("ink", "thumb", 4.5, "the chosen segment's words"), ("line-strong", "thumb", 3.0, "the chosen segment's ring"),
            ("muted", "thumb", 4.5, "a count on the chosen segment"),
            ("mark", "accent-soft", 3.0, "the chosen place's ring"), ("muted", "raised-hover", 4.5, "quiet words on a hovered button"),
            ("line-strong", "accent-soft", 3.0, "a control's edge on the soft clay"), ("link-line", "accent-soft", 3.0, "a link's underline on the soft clay"),
            ("line-strong", "overlay", 3.0, "a field's edge in a sheet"), ("ink", "surface", 4.5, "a soft pill's words in a sunk box")]
    # The Brief's own grounds: a number's tile, and Today under its strip.
    for s in ("tile", "today-wash"):
        out += [("ink", s, 4.5, "body text on " + s), ("muted", s, 4.5, "secondary text on " + s), ("mark-ink", s, 4.5, "clay as text on " + s),
                ("focus", s, 3.0, "focus ring on " + s)]
    # A person's initial on its fill, wherever an avatar is drawn.
    out += [("ink", f"avatar-{n}", 4.5, "an initial on its avatar") for n in range(1, 7)]
    for st in STATUSES:
        out += [(f"st-{st}", f"st-{st}-bg", 4.5, f"{st}: a status word on its tint"), ("muted", f"st-{st}-bg", 4.5, f"secondary text on {st}'s tint")]
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
    dark = _block(DARK, "dark")
    return "\n".join([
        "/* The palettes: generated by templates/app/palettes.py, with each colour's source. */",
        ":root {\n  color-scheme: light dark;\n" + _block(LIGHT) + "\n}",
        ':root[data-theme="light"], :root[data-look="light"] { color-scheme: light; }',
        '@media (prefers-color-scheme: dark) {\n:root:not([data-theme="light"]):not([data-look="light"]) {\n' + dark + "\n}\n}",
        ':root[data-theme="dark"]:not([data-look="light"]), :root[data-look="dark"] {\n' + dark + "\n}",
        # The scrim's token where the backdrop inherits it, else the same warm near-black.
        "dialog::backdrop { background: var(--scrim, #141312); opacity: 0.45; }  /* [D] the scrim, in both */",
        "::selection { background: var(--selection); color: var(--ink); }",
    ])


def table() -> str:
    """Both palettes as a table, with the lowest ratio among the pairs each token is in."""
    keys = list(LIGHT)
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
