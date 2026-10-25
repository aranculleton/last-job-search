"""Turn a tailor's free-form tools string into a categorized, parseable skills block.

The tools field used to be whatever the drafting model typed: sometimes comma
separated, sometimes semicolons, sometimes \textbullet, with parenthetical
groups like "SQL (Snowflake, Teradata, Azure SQL)" that split apart wherever
the separator changed. Rendered as one wrapped paragraph under a bullet it read
as a wall of words, and an ATS parser saw fragments like "Redshift)" and
"Python (pandas" as separate skills.

So the tools string is no longer rendered. It is read as a set of *selections*
against a fixed inventory, and the block is rebuilt from the inventory. That
keeps the tailoring - only what the tailor chose appears - while guaranteeing
the same clean, categorized, left-aligned shape on every resume.

Within a category, items keep the order the tailor put them in, so whatever the
posting leads with still leads here.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import tex_escape  # noqa: E402

# What the candidate holds, from the profile's skills.py:
#   NOT_HELD   name -> (how a posting spells it, why it is not held). Never
#              selected onto a resume; a test asserts no ITEMS pattern matches
#              one, so re-adding an unheld skill fails the build rather than
#              reaching an employer. Omitting a skill is honest; claiming an
#              unheld one is not.
#   ITEMS      (category, canonical item, regex that recognizes it in a
#              free-form tools string): the only skills a resume may claim.
#   SECONDARY  held but weakest: sorted behind every primary skill, and shown
#              only when the posting names them.
#   PINNED     (category, item) always printed, or None.
#   ANCHORS    items that lead their line whatever the posting emphasises.
#   LABELS     (line, heading) for each rendered line, in page order: the
#              headings are the person's words for their own work.
#   MERGE      inventory category -> the line it prints on, where a profile
#              has more categories than lines.
#   MIN_PER_CATEGORY, MAX_PER_LINE   per line; default 1 and 6.
_P = person.module("skills")
NOT_HELD = _P.NOT_HELD
ITEMS = _P.ITEMS
SECONDARY = frozenset(getattr(_P, "SECONDARY", ()))
PINNED = getattr(_P, "PINNED", None)
ANCHORS = tuple(getattr(_P, "ANCHORS", ()))


# The lines and their headings are the person's. They were written here once,
# for a data analyst ("Languages and modelling", "Data engineering and cloud",
# "BI, tooling and delivery"), and the first person set up outside that field
# got their resume under those three headings, which the app could not have
# noticed and they would have sent. So a profile with no LABELS renders no
# Skills block at all: render() and lines() stop and say so.
#
# Three lines is the advice, not a rule here: five labelled lines cost the page
# two experience bullets, the wrong trade on a resume whose whole argument is
# what the candidate did. Put a bare tool beside the work it does ("Python"
# alone says nothing; "Python, demand forecasting" says the job).
LABELS = list(getattr(_P, "LABELS", ()))
MERGE = dict(getattr(_P, "MERGE", {}))
# A category that would render as one or two items is not worth a label line.
MIN_PER_CATEGORY = {cat: 1 for cat, _ in LABELS}
MIN_PER_CATEGORY.update(getattr(_P, "MIN_PER_CATEGORY", {}))
# Tight. At 9/7/7 the block rendered five to seven lines carrying ~28 items,
# which is a wall the recruiter skims past and page space the bullets should
# have. The tiering in _rank() puts the posting's own words first, so cutting
# the tail removes only what this employer never asked for.
MAX_PER_LINE = {cat: 6 for cat, _ in LABELS}
MAX_PER_LINE.update(getattr(_P, "MAX_PER_LINE", {}))


class NoHeadings(RuntimeError):
    """The profile names no Skills headings, so no Skills block can be printed."""


def _labels():
    if not LABELS:
        raise NoHeadings(
            "profile/skills.py sets no LABELS, the Skills block's headings: "
            "[(line, heading), ...] in page order, one per line, in the person's "
            "own words for their work. /setup --section documents writes them.")
    return LABELS


# Counted in RENDERED tokens, not inventory items: "Python, pandas, NumPy,
# scikit-learn" is one item but four things the reader's eye has to cross, so
# an 18-item cap was still printing 23 tokens over six lines.
MAX_TOKENS = 18


def _fold(found):
    """Map the five inventory categories onto the three rendered lines."""
    out = {}
    for cat, items in found.items():
        tgt = MERGE.get(cat, cat)
        out.setdefault(tgt, [])
        out[tgt] += [i for i in items if i not in out[tgt]]
    return out


def select(tools):
    """{line: [items]} for everything the tools string names, in the order the
    tailor first mentioned them, so a posting's headline stack leads its line."""
    found = {}
    for cat, item, pat in ITEMS:
        m = re.search(pat, tools, re.I)
        if m:
            found.setdefault(cat, []).append((m.start(), item))
    return _fold({c: [i for _, i in sorted(v)] for c, v in found.items()})


def unheld_requested(tools):
    """Skills the tools string asked for that the candidate does not hold.

    `select()` drops them silently, which is the right thing to put on the page
    and the wrong thing to tell the user: a posting that asks for Spark is a
    posting with a real gap, and the cover letter and the fit score both need to
    know. Returns {skill: reason} so the caller can say so out loud.
    """
    text = str(tools or "")
    return {name: why for name, (pat, why) in NOT_HELD.items()
            if re.search(pat, text, re.I)}


def _from_context(sel, context):
    """Top every line up from what the rest of the page already claims.

    The tools string is one line the drafting model wrote, and it forgets what
    the resume proves two inches higher: a resume can list no demand
    forecasting on its skills line while its first bullet describes forecasting
    demand. Nothing is invented. A skill is added
    only when the summary or a selected bullet already states it, so the block
    can never claim more than the page does.
    """
    if not context:
        return sel
    for cat, item, pat in ITEMS:
        line = MERGE.get(cat, cat)
        if item in sel.get(line, []):
            continue
        if re.search(pat, context, re.I):
            sel.setdefault(line, []).append(item)
    return sel


def _asked_for(posting):
    """Every inventory item this posting names, by its own pattern."""
    if not posting:
        return frozenset()
    return frozenset(item for _, item, pat in ITEMS if re.search(pat, posting, re.I))


# Words too general to say a posting asked for a skill, and the small words that join a
# phrase rather than build one.
_GENERIC = frozenset(
    "and or of for the a an to in on with at by from as data analysis analytics design "
    "testing management reporting model models modelling modeling tools tooling skills "
    "development engineering science business stakeholder stakeholders".split())
_LINKING = frozenset(
    "a an the of and or to in on for with at by from as is are be been our your their its "
    "this that these those we you they it culture".split())
_SUFFIXES = ("ations", "ation", "ings", "ing", "als", "al", "ed", "s")


def _stem(word):
    w = word.lower()
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _head_stems(item):
    """The head noun of each part of an inventory item, the last word that names the
    skill rather than a general one: "demand forecasting" is named by "forecasting",
    and "A/B testing and experiment design" by "experiment", since "testing" and
    "design" are too general to say which skill."""
    out = set()
    for part in re.split(r"\s+and\s+|,|/|\(|\)", item):
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z+#]*", part)
                 if len(w) > 2 and w.lower() not in _GENERIC]
        if words:
            out.add(_stem(words[-1]))
    return out


_WORD = re.compile(r"[A-Za-z][A-Za-z+#'-]*")


def _compound_named(items, posting):
    """The items the tailor listed that the posting names inside a compound phrase.

    An item's own pattern can deliberately skip a word on its own: "experimentation"
    alone is as often "a culture of experimentation" as the skill, so a profile's A/B
    testing pattern leaves it out. But "online experimentation" or "an experimentation
    platform" is the skill, and the tailor listing it in the tools field is the second
    reading that says so. Read here only to keep such an item from being trimmed as
    never asked for: every item is held, so nothing unheld can reach the page this way.
    """
    if not posting or not items:
        return frozenset()
    words = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(posting)]
    out = set()
    for item in items:
        stems = _head_stems(item)
        if not stems:
            continue
        for i, (w, _start, _end) in enumerate(words):
            if _stem(w) not in stems:
                continue
            for j in (i - 1, i + 1):
                if not 0 <= j < len(words):
                    continue
                a, b = (words[j], words[i]) if j < i else (words[i], words[j])
                between = posting[a[2]:b[1]]
                other = words[j][0].lower()
                if between.strip(" -") == "" and "\n" not in between and other not in _LINKING:
                    out.add(item)
                    break
            if item in out:
                break
    return frozenset(out)


def _standing_in(posting):
    """Held items that stand in for a tool the posting asks for and the person does not
    hold, from the same family (tools/bridges.py): Power BI for a Tableau posting, AWS
    for an Azure one. Left off, the resume showed neither, though the person does the
    same work in the one they hold. The tool asked for is never printed."""
    if not posting:
        return frozenset()
    try:
        import bridges
    except Exception:          # no profile to read: nothing stands in
        return frozenset()
    out = set()
    for a in bridges.assess(posting):
        if a.verdict == bridges.BRIDGE and bridges.strength_of(a.asked) == "near":
            for h in a.have:
                out.update(i for _, i, pat in ITEMS if i == h or re.search(pat, h, re.I))
    return frozenset(out)


def _from_posting(sel, posting):
    """Add a held skill this posting asks for by name.

    The posting used to be read for ranking only, never for adding, so a skill
    reached the page only if the tools string or a selected bullet happened to
    use that exact phrase. A posting could say "machine learning" three times
    while the profile held it, and the words never appeared in the Skills block
    because no bullet spelled them out.

    This cannot invent anything. `ITEMS` is the inventory: it is the list of
    what the resume is permitted to claim, and `NOT_HELD` is enforced against
    it by a test. An item here is held by definition, so the only question was
    ever whether to print it, and a posting naming it is the strongest possible
    reason to.

    The caps in `_final` are what keeps the block honest about length, and
    `_rank` has already put the posting's own words first, so what a
    posting-requested item displaces is something this employer never asked
    for.
    """
    if not posting:
        return sel
    standing = _standing_in(posting)
    for cat, item, pat in ITEMS:
        line = MERGE.get(cat, cat)
        if item in sel.get(line, []):
            continue
        if re.search(pat, posting, re.I) or item in standing:
            sel.setdefault(line, []).append(item)
    return sel


def _rank(sel, posting, context, company="", also_named=frozenset()):
    """Posting-named items first, then what the page's bullets evidence, then
    the tailor's remaining picks. Within each tier the tailor's order holds.

    A posting-named item that is in the inventory but on neither the tools
    string nor the page is ADDED at the front: every inventory item is a
    skill the profile holds, and a held skill the posting asks for by name is
    the one keyword an ATS pass must find. Guard: an item that is also the
    employer's name (a company named after a tool) is not a skill mention.
    """
    if not posting and not context:
        return {c: sorted(v, key=lambda i: (i not in ANCHORS, i in SECONDARY))
                for c, v in sel.items()}
    standing = _standing_in(posting)

    def tier(item):
        pat = next(p for c, i, p in ITEMS if i == item)
        # A secondary skill never outranks a primary one. The candidate's
        # secondary set is the weakest held, there to surface the role and meet
        # an ATS requirement; the primary set is the main skills. A resume that
        # leads on a secondary tool instead of its core work has buried the
        # argument.
        if item in ANCHORS:
            return -1 + ANCHORS.index(item) * 0.1
        secondary = item in SECONDARY
        named = (bool(posting and re.search(pat, posting, re.I)) or item in standing
                 or item in also_named)
        evidenced = bool(context and re.search(pat, context, re.I))
        # A flat +3 for a secondary put a posting-named secondary BELOW a
        # primary the posting never mentioned, and the per-line cap then cut it
        # before the trim could weigh it: a posting asking for a secondary
        # tool by name had it dropped for primaries it never mentioned.
        # Surfacing the role and meeting the ATS requirement is the
        # entire reason the secondary set exists, so a named secondary now
        # beats an unnamed primary.
        #
        # It still never leads. Every posting-named primary outranks it, which
        # is the rule that matters: a resume leading on Kubernetes instead of
        # demand forecasting has buried the argument.
        if named:
            return 1 if secondary else 0
        if evidenced:
            return 4 if secondary else 2
        return 5 if secondary else 3
    if posting:
        for cat, item, pat in ITEMS:
            line = MERGE.get(cat, cat)
            if item in sel.get(line, []):
                continue
            if company and re.search(pat, company, re.I):
                continue
            if re.search(pat, posting, re.I) or item in standing:
                sel.setdefault(line, []).append(item)
    # A secondary skill the posting never mentions has no business on the page:
    # it costs a line the primary skills should have and it invites a question
    # about the weakest thing on the resume.
    if posting:
        sel = {c: [i for i in v
                   if i not in SECONDARY or i in standing or i in also_named
                   or re.search(next(p for _, it, p in ITEMS if it == i), posting, re.I)]
               for c, v in sel.items()}
    return {c: sorted(v, key=tier) for c, v in sel.items()}


def _consent_line(name):
    """(line, held item it follows) for a skill the person said yes to: beside the held
    tool it stands next to (tools/bridges.py), else at the end of the last line."""
    try:
        import bridges
        beside = bridges.held_beside(name)
    except Exception:          # no profile to read: no neighbour
        beside = []
    for h in beside:
        for cat, item, pat in ITEMS:
            if item == h or re.search(pat, h, re.I):
                return MERGE.get(cat, cat), item
    return _labels()[-1][0], None


def _yes(consented):
    return list(dict.fromkeys(str(c).strip() for c in consented or () if str(c).strip()))


def _final(tools, context, posting="", company="", consented=()):
    """Tailor's picks first, context top-ups after, capped per line, the
    profile's pinned item guaranteed. The cap keeps the tooling line to one
    rendered line: uncapped, it wraps onto a second with Jira and Confluence,
    which nobody hiring for the role was going to read."""
    picked = select(tools)
    # Listed by the tailor and named by the posting in a phrase its pattern skips: asked for.
    compound = _compound_named([i for v in picked.values() for i in v], posting)
    sel = _from_context(dict(picked), context)
    sel = _from_posting(sel, posting)
    sel = _rank(sel, posting, context, company, compound)
    # The employer's own name is not a skill mention wherever it appears: a
    # summary praising a tool company's product would otherwise add that tool
    # to the stack. Only the tailor naming it on the tools string keeps it.
    if company:
        own = {item for _, item, pat in ITEMS if re.search(pat, company, re.I)}
        sel = {c: [i for i in v if i not in own or i in picked.get(c, [])] for c, v in sel.items()}
    # What the person said yes to claiming for this posting (tools/stage_picks.py consent):
    # printed as the posting spells it, beside the held tool it sits next to, and never
    # trimmed. Only their yes puts a skill the profile does not hold on the page.
    yes = _yes(consented)
    for name in yes:
        if any(name.casefold() == i.casefold() for v in sel.values() for i in v):
            continue
        line, after = _consent_line(name)
        items = sel.setdefault(line, [])
        items.insert(items.index(after) + 1 if after in items else len(items), name)
    keep = set(ANCHORS) | set(yes)
    # The per-line cap, taking the item this employer never asked for rather
    # than whatever happens to be last. A blind head-slice ran before the
    # token trim below could weigh anything, so two postings each asking for
    # two named tools lost them here, while tools neither posting mentions
    # stayed.
    asked_here = _asked_for(posting) | set(yes) | compound

    def _trim_line(items, cap):
        items = list(items)
        while len(items) > cap:
            drop = max((i for i in range(len(items)) if items[i] not in keep),
                       key=lambda i: (items[i] not in asked_here, i), default=None)
            if drop is None:
                break
            items.pop(drop)
        return items

    sel = {c: _trim_line(v, MAX_PER_LINE.get(c, 6)) for c, v in sel.items()}

    # Overall cap, counted in RENDERED tokens rather than inventory items:
    # "Python, pandas, NumPy, scikit-learn" is one item but four things the
    # eye has to cross, so a per-line cap alone still printed 23 tokens over
    # six lines. Trim the longest line until the block fits. _rank() has
    # already put the posting's own words first, so what goes is what this
    # employer never asked for.
    def _tokens(cat):
        return sum(i.count(",") + 1 for i in sel.get(cat, []))

    # What goes is the item this employer never asked for, wherever it sits.
    #
    # A trim of the tail of whatever line is longest is a length rule wearing a
    # relevance rule's clothes. It would drop "machine learning", which a
    # posting names three times, off the end of the modelling line while
    # keeping two engineering tools the posting never mentions at all. Same
    # block length, worse keyword coverage, and the terms most likely to be
    # screened on are the ones that go.
    def _weakest():
        cands = [(cat, i) for cat in sel for i in range(len(sel[cat]))
                 if sel[cat][i] not in keep
                 and len(sel[cat]) > MIN_PER_CATEGORY.get(cat, 1)]
        if not cands:
            return None
        # Not asked for beats asked for; then the longest line; then the tail.
        return max(cands, key=lambda ci: (sel[ci[0]][ci[1]] not in asked_here,
                                          _tokens(ci[0]), ci[1]))

    while sum(_tokens(c) for c in sel) > MAX_TOKENS:
        weakest = _weakest()
        if weakest is None:
            break
        cat, i = weakest
        sel[cat].pop(i)

    if not PINNED:
        return sel
    line, item = PINNED
    if item not in sel.get(line, []):
        sel.setdefault(line, [])
        if len(sel[line]) >= MAX_PER_LINE.get(line, 6):
            last = [i for i in range(len(sel[line])) if sel[line][i] not in yes]
            if last:
                sel[line].pop(last[-1])
        sel[line].append(item)
    return sel


# A skill the person said yes to is the posting's spelling, not an inventory item
# written for LaTeX, and a heading is the person's words: both are escaped on the way out,
# by the one copy of that rule (tools/tex_escape.py). "BI & delivery" printed "BI delivery".


def coverage(posting, page, consented=()):
    """What the posting names, against the page: {"on_page": [...], "held_not_placed": [...],
    "not_held": [(name, its held neighbour or "")]}. A report, never an edit: nothing here
    adds anything to a resume, and a skill the profile does not hold is listed as not held,
    never as one to add. A skill the person said yes to for this application counts as
    theirs. `page` is the resume's text layer, which is what a parser reads."""
    posting, page = str(posting or ""), str(page or "")
    yes = {y.casefold() for y in _yes(consented)}
    on, off, asked = [], [], set()
    for _cat, item, pat in ITEMS:
        if not re.search(pat, posting, re.I):
            continue
        asked.add(item.casefold())
        target = on if re.search(pat, page, re.I) else off
        if item not in on + off:
            target.append(item)
    on += [y for y in _yes(consented) if re.search(re.escape(y), page, re.I) and y not in on]
    # Named as the posting writes it ("CIPS"), each place in the posting once: the profile's
    # NOT_HELD and its BRIDGES can both know the same term.
    unheld, spans = [], []
    for name, (pat, _why) in NOT_HELD.items():
        m = re.search(pat, posting, re.I)
        if m and name.casefold() not in yes:
            unheld.append((m.group(0), ""))
            spans.append(m.span())
    try:
        import bridges
        assessed, entries = bridges.assess(posting), {e["asked"]: e for e in bridges.MAP}
    except Exception:          # no profile to read: no bridges
        assessed, entries = [], {}
    named = {n.casefold() for n, _h in unheld}
    for a in assessed:
        if a.verdict == "held" or a.asked.casefold() in yes | named:
            continue
        if any(re.search(pat, a.asked, re.I) for _c, item, pat in ITEMS
               if item.casefold() in asked):
            continue           # the inventory holds it: counted above
        m = re.search(entries[a.asked]["pattern"], posting, re.I) if a.asked in entries else None
        if m and any(m.start() < e and s < m.end() for s, e in spans):
            continue           # the same words, already named
        unheld.append((a.asked, ", ".join(a.have) if a.verdict == "bridge" else ""))
        named.add(a.asked.casefold())
    return {"on_page": on, "held_not_placed": off, "not_held": unheld}


def coverage_lines(report) -> list:
    """The coverage report as plain lines."""
    out = []
    if report["on_page"]:
        out.append("on the page (%d): %s" % (len(report["on_page"]), "; ".join(report["on_page"])))
    if report["held_not_placed"]:
        out.append("held but not on the page (%d): %s. Yours to add where it is true, if there "
                   "is room" % (len(report["held_not_placed"]),
                                "; ".join(report["held_not_placed"])))
    if report["not_held"]:
        out.append("not held, so never added (%d): %s" % (len(report["not_held"]), "; ".join(
            "%s (the nearest you hold: %s)" % (n, h) if h else n for n, h in report["not_held"])))
    return out or ["the posting names nothing the profile's skills list knows"]


def render(tools, context="", posting="", company="", consented=()):
    """LaTeX for the Skills block."""
    sel = _final(tools, context, posting, company, consented)
    yes = set(_yes(consented))

    def tex(i):
        return tex_escape.text(i) if i in yes else i
    return "\n".join("\\blockline{%s}{%s}" % (tex_escape.text(label),
                                              ", ".join(tex(i) for i in sel[cat]))
                     for cat, label in _labels()
                     if len(sel.get(cat, [])) >= MIN_PER_CATEGORY.get(cat, 1))


def lines(tools, context="", posting="", company="", consented=()):
    """Plain-text preview, for tests and for measuring the page budget."""
    sel = _final(tools, context, posting, company, consented)
    return [f"{label}: {', '.join(sel[cat])}" for cat, label in _labels() if sel.get(cat)]
