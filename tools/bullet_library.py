"""Every bullet the profile supports, tagged so a posting can choose among them.

A generator that holds a handful of fixed bullets per employer turns out
near-identical resumes for very different postings: a trust and safety resume
and a pricing resume drawing on the same four strings come out as permutations
of each other, and the strongest results in the history never get a slot.

So the person's history lives in profile/bullets.py as a library: employer ->
bullet id -> (themes, weight, text). THEMES are what a posting is matched
against; WEIGHT is how strong the bullet is on its own when nothing matches.
Text is taken from the candidate profile and trimmed, never escalated. This
module reads it through tools/person.py and derives the lookup tables every
other tool uses.

Bullet ids are a persisted interface: committed draft.json files name them.
A renamed bullet keeps its old id as an alias in the profile (ALIASES), which
takes the target's text, themes and employer with weight 0, so an old draft
still renders and the alias is never chosen on its own.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

_P = person.module("bullets")

# employer -> bullet id -> (themes, weight, text)
LIB = _P.LIB
# Bullets that say the same thing; never render two from one group.
CONFLICT_GROUPS = _P.CONFLICT_GROUPS
# A bullet that opens an employer block must be something the candidate BUILT
# with a result. "Presented..." and "Supported..." lines are true and useful,
# but first under an employer they make the reader think that was the job.
NON_LEAD = set(_P.NON_LEAD)
ALIASES = dict(getattr(_P, "ALIASES", {}))
RENDER_ALIASES = dict(getattr(_P, "RENDER_ALIASES", {}))

TEXT = {k: v[2] for emp in LIB.values() for k, v in emp.items()}
for _a, _t in ALIASES.items():
    TEXT[_a] = TEXT[_t]
THEMES = {k: v[0] for emp in LIB.values() for k, v in emp.items()}
WEIGHT = {k: v[1] for emp in LIB.values() for k, v in emp.items()}
EMPLOYER = {k: emp for emp, bs in LIB.items() for k in bs}
for _a, _t in ALIASES.items():
    THEMES[_a] = THEMES[_t]
    WEIGHT[_a] = 0
    EMPLOYER[_a] = EMPLOYER[_t]

CONFLICTS = {}
for _g in CONFLICT_GROUPS:
    for _k in _g:
        CONFLICTS.setdefault(_k, set()).update(_g - {_k})
