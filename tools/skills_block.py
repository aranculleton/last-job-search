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
_P = person.module("skills")
NOT_HELD = _P.NOT_HELD
ITEMS = _P.ITEMS
SECONDARY = frozenset(getattr(_P, "SECONDARY", ()))
PINNED = getattr(_P, "PINNED", None)
ANCHORS = tuple(getattr(_P, "ANCHORS", ()))


# Three lines. Five labelled lines cost the page two experience bullets, the
# wrong trade on a resume whose whole argument is what the candidate did.
# Languages sit with modelling because "Python" alone says nothing and
# "Python, demand forecasting, inventory analytics" says the job; BI sits with
# delivery because both are how the work reaches a stakeholder.
LABELS = [
    ("lang",  "Languages and modelling"),
    ("eng",   "Data engineering and cloud"),
    ("bi",    "BI, tooling and delivery"),
]

# Five categories cost five lines. These fold into three without losing an item.
MERGE = {"model": "lang", "work": "bi"}

# A category that would render as one or two items is not worth a label line.
MIN_PER_CATEGORY = {"lang": 1, "eng": 1, "bi": 1}
# Tight. At 9/7/7 the block rendered five to seven lines carrying ~28 items,
# which is a wall the recruiter skims past and page space the bullets should
# have. The tiering in _rank() puts the posting's own words first, so cutting
# the tail removes only what this employer never asked for.
MAX_PER_LINE = {"lang": 7, "eng": 6, "bi": 5}
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
    for cat, item, pat in ITEMS:
        line = MERGE.get(cat, cat)
        if item in sel.get(line, []):
            continue
        if re.search(pat, posting, re.I):
            sel.setdefault(line, []).append(item)
    return sel


def _pin(sel):
    if not PINNED:
        return sel
    line, item = PINNED
    if item not in sel.get(line, []):
        sel.setdefault(line, []).append(item)
    return sel


def _rank(sel, posting, context, company=""):
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
        named = bool(posting and re.search(pat, posting, re.I))
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
            if re.search(pat, posting, re.I):
                sel.setdefault(line, []).append(item)
    # A secondary skill the posting never mentions has no business on the page:
    # it costs a line the primary skills should have and it invites a question
    # about the weakest thing on the resume.
    if posting:
        sel = {c: [i for i in v
                   if i not in SECONDARY
                   or re.search(next(p for _, it, p in ITEMS if it == i), posting, re.I)]
               for c, v in sel.items()}
    return {c: sorted(v, key=tier) for c, v in sel.items()}


def _final(tools, context, posting="", company=""):
    """Tailor's picks first, context top-ups after, capped per line, the
    profile's pinned item guaranteed. The cap keeps the tooling line to one
    rendered line: uncapped, it wraps onto a second with Jira and Confluence,
    which nobody hiring for the role was going to read."""
    picked = select(tools)
    sel = _from_context(dict(picked), context)
    sel = _from_posting(sel, posting)
    sel = _rank(sel, posting, context, company)
    # The employer's own name is not a skill mention wherever it appears: a
    # summary praising a tool company's product would otherwise add that tool
    # to the stack. Only the tailor naming it on the tools string keeps it.
    if company:
        own = {item for _, item, pat in ITEMS if re.search(pat, company, re.I)}
        sel = {c: [i for i in v if i not in own or i in picked.get(c, [])] for c, v in sel.items()}
    # The per-line cap, taking the item this employer never asked for rather
    # than whatever happens to be last. A blind head-slice ran before the
    # token trim below could weigh anything, so two postings each asking for
    # two named tools lost them here, while tools neither posting mentions
    # stayed.
    asked_here = _asked_for(posting)

    def _trim_line(items, cap):
        items = list(items)
        while len(items) > cap:
            drop = max((i for i in range(len(items)) if items[i] not in ANCHORS),
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
                 if sel[cat][i] not in ANCHORS
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
        if len(sel[line]) >= MAX_PER_LINE[line]:
            sel[line] = sel[line][:-1]
        sel[line].append(item)
    return sel


def render(tools, context="", posting="", company=""):
    """LaTeX for the Skills block."""
    sel = _final(tools, context, posting, company)
    return "\n".join("\\blockline{%s}{%s}" % (label, ", ".join(sel[cat]))
                     for cat, label in LABELS
                     if len(sel.get(cat, [])) >= MIN_PER_CATEGORY[cat])


def lines(tools, context="", posting="", company=""):
    """Plain-text preview, for tests and for measuring the page budget."""
    sel = _final(tools, context, posting, company)
    return [f"{label}: {', '.join(sel[cat])}" for cat, label in LABELS if sel.get(cat)]
