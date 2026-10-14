"""Decide how many bullets each employer gets, and which ones, per posting.

Allocation used to be a fixed fill order: the current employer, then the one
before, three each until the page ran out, and the trimmer took from the end. So
a short role routinely carried three bullets while a role with the longest
tenure on the resume carried one. Nothing about that was a decision; it was
the order the pool happened to be written in.

Three things decide it now.

  Tenure. Two years somewhere is more of a career than one year elsewhere, and a
  reader weighing depth reads it that way. Entered as the square root of months,
  so it matters without swamping everything else.

  Recency. Recent work is better evidence of current ability. A mild factor, not
  a dominant one, or it would just reproduce the old ordering.

  Relevance. Every bullet is themed, every posting is scanned for theme cues,
  and an employer's relevance is the strength of its best bullets against this
  posting. This is what makes a warehouse-operations posting surface the
  inventory work and a procurement posting surface the supplier work, from the
  same profile.

Floors and caps keep the shape sane, and they are per role, in the profile's
roles.py: a role with real tenure keeps a floor, nobody takes more than its cap,
and a role can carry a lower cap unless the posting is its territory (a short
contract keeps one bullet unless the posting is about what it did).
"""
import functools, math, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bullet_library import LIB, THEMES, WEIGHT, CONFLICTS, NON_LEAD
import person

# The profile's roles, most recent first: months served, how recent (0 =
# current), and the bullets each gets at least and at most.
ROLES = person.module("roles").ROLES
TENURE = {r["employer"]: r["tenure_months"] for r in ROLES}
RECENCY_RANK = {r["employer"]: i for i, r in enumerate(ROLES)}
RECENCY_FACTOR = {0: 1.15, 1: 1.08, 2: 1.02, 3: 0.80}


def _recency(rank):
    """Every role older than the fourth weighs as the fourth."""
    return RECENCY_FACTOR.get(rank, RECENCY_FACTOR[max(RECENCY_FACTOR)])


FLOOR = {r["employer"]: r["floor"] for r in ROLES}
CAP = {r["employer"]: r["cap"] for r in ROLES}

THEME_CUES = {
 # Pricing, packaging and monetization work IS experiment work: a pricing team
 # tests plans, bundles and upgrade paths the same way a growth team tests a
 # funnel. Without these cues a "Pricing Analyst, Monetization" posting scored
 # zero on experimentation, so the strongest experiment bullet on the resume
 # lost to a bullet about collating data for a weekly business review.
 "experimentation": ["a/b test", "ab test", "experiment", "split test", "hypothesis",
                     "significance", "incrementality", "holdout",
                     "packaging", "bundle", "plan mix", "upgrade path",
                     "price test", "willingness to pay", "test and learn",
                     "optimi[sz]ation of pricing", "conversion rate"],
 "retention":     ["retention", "churn", "lifetime value", "ltv", "cohort", "repeat"],
 "growth":        ["growth", "acquisition", "activation", "funnel", "conversion", "engagement"],
 "product":       ["product analytics", "product team", "user behaviour", "user behavior",
                   "feature", "roadmap", "product manager", "customer behaviour",
                   "customer behavior", "customer segment", "segments"],
 "pricing":       ["pricing", "price", "revenue management", "elasticity", "margin",
                   "monetization", "monetisation", "yield"],
 "forecasting":   ["forecast", "time series", "time-series", "demand", "regression", "predictive"],
 "risk":          ["risk", "fraud", "credit", "default", "delinquen", "aml",
                   "financial crime", "underwriting", "exposure"],
 "modelling":     ["model", "machine learning", "scikit", "statistical model"],
 "pipeline":      ["pipeline", "etl", "elt", "airflow", "ingestion", "orchestration"],
 "quality":       ["data quality", "validation", "qa", "unit test", "accuracy",
                   "great expectations", "data integrity"],
 "governance":    ["governance", "audit", "compliance", "controls", "internal control",
                   "regulat", "policy", "lineage", "stewardship"],
 "bi":            ["power bi", "tableau", "dashboard", "business intelligence", "looker", "qlik"],
 "reporting":     ["reporting", "report"],
 "stakeholder":   ["stakeholder", "business partner", "senior leader", "executive",
                   "present to", "influence"],
 "cloud":         ["aws", "azure", "gcp", "snowflake", "databricks", "redshift", "cloud"],
 "sql":           ["sql", "query", "warehouse"],
 "python":        ["python", "pandas", "numpy"],
 "analytics_eng": ["analytics engineer", "dbt", "data model", "semantic layer",
                   "transformation", "medallion"],
 "migration":     ["migration", "migrate", "legacy", "moderniz", "cutover"],
 "platform":      ["platform", "internal tool", "framework", "standardiz", "reusable"],
 "devops":        ["ci/cd", "github actions", "version control", "devops", "git"],
 "ai":            ["llm", "genai", "generative", "agentic", "copilot", "foundation model"],
 "api":           ["api", "rest", "swagger", "integration"],
 "consumer":      ["consumer", "customer", "member", "subscriber", "end user", "b2c"],
 "scale":         ["large scale", "millions", "billions", "high volume", "big data", "petabyte"],
 "segmentation":  ["segment", "persona", "audience", "targeting"],
 "startup":       ["startup", "start-up", "seed", "series a", "series b", "fast-paced",
                   "0 to 1", "scrappy"],
 "fintech":       ["fintech", "bank", "payment", "lending", "financial services",
                   "wealth", "crypto", "insur"],
 "commercial":    ["commercial", "revenue", "p&l", "profit", "gtm", "go-to-market", "sales"],
 "statistics":    ["statistic", "confidence interval", "power analysis", "bayesian",
                   "causal", "inference"],
 "rigour":        ["rigor", "rigour", "peer review", "reproduc", "documented"],
 # Troubleshooting is incident work: a support or SRE-adjacent posting asks for
 # it in these words and never says "monitoring", so without them a support
 # engineering posting took an experiment bullet over the alerting bullet, the
 # one line that answers it.
 "monitoring":    ["monitor", "alert", "observability", "incident", "on-call",
                   "troubleshoot", "debug", "root cause"],
 "reliability":   ["reliability", "uptime", "sla", "downtime", "resilien"],
 "documentation": ["documentation", "confluence", "runbook", "specification"],
 "mentoring":     ["mentor", "coach", "junior", "guide the team", "knowledge sharing"],
 "automation":    ["automat", "manual effort", "efficiency", "self-serve", "self-service"],
 "compliance":    ["compliance", "gdpr", "privacy", "safeguard", "trust and safety",
                   "child", "age verification"],
 "public_sector": ["public sector", "government", "healthcare", "nhs", "municipal", "citizen"],
 "finance":       ["finance", "financial", "accounting", "treasury", "investment"],
 "consulting":    ["consult", "client", "engagement", "advisory"],
 "delivery":      ["end to end", "end-to-end", "ownership", "cross-functional", "deliver"],
 "marketing":     ["marketing", "campaign", "email", "crm", "lifecycle"],
 "engineering":   ["engineer", "software", "production"],
}

# Cues are matched at a word boundary. Substring matching scored "seamless"
# as AML, "digital" as git, "capital" as an API, "laws" as AWS, "accredited"
# as credit and "delta" as ELT. A cue is a prefix ("forecast" covers
# forecasting) unless it is in WHOLE_WORD, where a suffix changes the meaning.
WHOLE_WORD = {"aws", "gcp", "aml", "sla", "api", "git", "etl", "elt", "ltv", "qa", "rest",
              "seed", "gtm", "crm", "llm", "nhs", "sales", "default", "series a",
              "series b", "0 to 1", "controls", "credit"}

# The themes above are a data analyst's, because that is who the app was built
# for. A nurse's or a carpenter's bullets carry themes this list has never heard
# of, and a theme with no cue scores nothing on any posting, so the allocator
# falls back on bare weight and every resume comes out the same. A profile adds
# its own in profile/bullets.py: THEME_CUES (theme -> cues, adding a theme or
# replacing one's cues) and CUE_WHOLE_WORD (cues a suffix would change).
_B = person.module("bullets")
THEME_CUES.update(getattr(_B, "THEME_CUES", {}))
WHOLE_WORD |= set(getattr(_B, "CUE_WHOLE_WORD", ()))
CUE_RE = {theme: [re.compile(r"\b" + re.escape(c) + (r"\b" if c in WHOLE_WORD else ""))
                  for c in cues]
          for theme, cues in THEME_CUES.items()}

# Text every posting carries that says nothing about the job: EEO statements,
# benefits, accommodation and contact lines, reporting lines, and phrases where
# a cue word means something else ("by default", "privacy policy", "operating
# model"). Each of these moved a score on a real posting; "email us at" made a
# BI role a marketing role and "time off policy" made it a governance one.
# Stripped before scoring. Sentence-level, so the rest of the posting is
# untouched.
NOISE_SENTENCE = re.compile(
    r"[^.\n]*\b(?:equal[- ]opportunit|accommodat|without regard to|protected (?:ground|class|"
    r"characteristic)|discriminat|diversity|inclusion|inclusive|underrepresented|encourage "
    r"applications|members of groups|rrsp|401\(?k|dental|vision care|paid time off|vacation|"
    r"parental leave|well-being|wellbeing|wellness|best workplaces|great place to work|"
    r"privacy (?:policy|notice|statement)|email us|contact us)"
    r"[^.\n]*[.\n]?", re.I)
NOISE_PHRASE = re.compile(
    r"\breport(?:s|ing)? to\b[^.\n]*|\bby default\b|\btake control of\b|\[email protected\]|"
    r"\b(?:operating|business|role|delivery|engagement|working|commercial|service|"
    r"support|hybrid|remote) model\b|\S+@\S+\.\w+|"
    r"\b(?:privacy|time[- ]off|vacation|leave|pto) polic(?:y|ies)\b", re.I)


def strip_boilerplate(posting):
    """Remove the text that is on every posting and describes no job."""
    p = NOISE_SENTENCE.sub(" ", posting or "")
    return NOISE_PHRASE.sub(" ", p)


# How much a fully matched theme is worth against WEIGHT (6-10). At 3.0, four
# weak theme matches let "audited every dashboard" (no number) outscore a
# measured A/B-test result on a governance posting. A number is evidence; a theme
# match is a hint. The hint should reorder among comparable bullets, not
# overturn a strong one.
THEME_BONUS = 2.5
RELEVANCE_PULL = 0.9  # how hard relevance is allowed to move the employer split


def _theme_scores(posting):
    """0-1 per theme, from how many distinct cues the posting uses."""
    p = strip_boilerplate(posting).lower()
    out = {}
    for theme, pats in CUE_RE.items():
        hits = sum(1 for r in pats if r.search(p))
        if hits:
            out[theme] = min(1.0, hits / 3.0)
    return out


# Every caller passes the same posting text, and there are four of them:
# `bullet_scores`, `caps_for`, `allocate` through both of those, and `explain`.
# So rendering one application scanned the posting with every cue pattern three
# times over, and `fit_to_page` does that again on each trim-and-recompile
# round. It is pure over the text, so it caches.
#
# The cache is keyed on the posting itself rather than an id, because a caller
# that reads the same file twice gets two equal strings and should get one scan.
# Bounded, because a round can hold a thousand postings in memory at once and an
# unbounded cache on full posting bodies is how a batch runs out of RAM.
@functools.lru_cache(maxsize=256)
def _theme_scores_cached(posting):
    return _theme_scores(posting)


def theme_scores(posting):
    """0-1 per theme, from how many distinct cues the posting uses.

    The returned dict is a fresh copy: callers treat it as theirs, and one of
    them (`caps_for`) reads it alongside a `dict(CAP)` it does mutate, so
    handing out the cached object would make a future edit there corrupt every
    later call.
    """
    return dict(_theme_scores_cached(posting))


def bullet_scores(posting):
    ts = theme_scores(posting)
    return {b: WEIGHT[b] + THEME_BONUS * sum(ts.get(t, 0.0) for t in THEMES[b])
            for b in THEMES}


# How far relevance must beat representativeness to take an employer's ONLY line.
#
# A bullet's WEIGHT is how well it represents the job; its score adds
# THEME_BONUS per matched theme on top. When an employer gets several bullets
# those two pull together and the page reads fine either way. When an employer
# gets exactly one, that line is doing two jobs at once: it is the evidence AND
# it is the only description of what the role was. Losing the second job is how
# a planning role at a distributor goes out represented, in full, by a line
# about building dashboards for leadership. True, the weakest claim on the
# page, last line of the resume, and it makes the job title above it look like
# a misprint.
#
# That happened on a noticeable share of one-bullet allocations when it was
# measured, and the margins said why: most turned on half a point, a fifth of
# a single theme match, against a 2-point gap in how well the bullet describes
# the job. So the override threshold is one whole theme match. A
# posting that is genuinely about reporting and automation still takes the
# reporting bullet; a posting that merely mentions a dashboard does not.
SOLE_MARGIN = THEME_BONUS


def _pick(employer, n, scores, taken):
    """Top n bullets for one employer, honouring conflicts and what is taken."""
    if n == 1:
        pool = [b for b in LIB[employer] if b not in taken]
        if not pool:
            return []
        # Conflicts cannot bind on a single pick: they block sibling bullets
        # inside one employer's set, and there are no siblings here. That holds
        # only while no conflict pair crosses employers, which is true of the
        # library and is true by accident rather than by construction, so it is
        # pinned in tests/test_a_sole_bullet_describes_the_job.py rather than
        # left as a comment nobody rechecks.
        sharpest = max(pool, key=lambda k: (scores[k], WEIGHT[k]))
        truest = max(pool, key=lambda k: (WEIGHT[k], scores[k]))
        return [sharpest if scores[sharpest] - scores[truest] >= SOLE_MARGIN
                else truest]
    out, blocked = [], set()
    for b in sorted(LIB[employer], key=lambda k: (-scores[k], -WEIGHT[k])):
        if len(out) >= n:
            break
        if b in blocked or b in taken:
            continue
        out.append(b)
        blocked |= CONFLICTS.get(b, set())
    # Strongest lead-eligible bullet first; everything else keeps score order.
    return sorted(out, key=lambda k: (k in NON_LEAD, -scores[k], -WEIGHT[k]))


def caps_for(posting):
    """Each role's cap for this posting.

    A role's `cap_unless` in the profile lowers its cap unless the posting is
    its territory: a short contract keeps one bullet unless the posting is
    genuinely about what it did, and a current role that would otherwise fill
    whatever the others left keeps fewer unless the posting is squarely its
    kind of work.
    """
    ts = theme_scores(posting)
    caps = dict(CAP)
    for r in ROLES:
        cu = r.get("cap_unless")
        if cu and max(ts.get(t, 0) for t in cu["themes"]) < cu["at_least"]:
            caps[r["employer"]] = cu["cap"]
    return caps


def allocate(posting, budget=11):
    """Return {employer: [bullet ids]} in reverse-chronological employer order."""
    scores = bullet_scores(posting)
    caps = caps_for(posting)

    # An employer is as relevant as its three strongest bullets for this posting.
    rel = {}
    for e in LIB:
        top = sorted((scores[b] for b in LIB[e]), reverse=True)[:3]
        rel[e] = sum(top) / len(top)
    lo, hi = min(rel.values()), max(rel.values())
    span = (hi - lo) or 1.0

    weight = {}
    for e in LIB:
        tenure = math.sqrt(TENURE[e])
        recency = _recency(RECENCY_RANK[e])
        relevance = 1.0 + RELEVANCE_PULL * ((rel[e] - lo) / span)
        weight[e] = tenure * recency * relevance

    # Floors first, then hand out what is left by weight, respecting caps.
    alloc = dict(FLOOR)
    left = budget - sum(alloc.values())
    while left > 0:
        opts = [e for e in LIB if alloc[e] < caps[e]]
        if not opts:
            # Every employer is at its cap for this posting; the page gets
            # fewer bullets than asked. Say so rather than return short silently.
            print(f"allocate: budget {budget} not reachable under caps {caps}; "
                  f"allocating {sum(alloc.values())}", file=sys.stderr)
            break
        # Award to whoever is furthest below their weighted share.
        total_w = sum(weight[e] for e in opts)
        pick = max(opts, key=lambda e: weight[e] / total_w - alloc[e] / budget)
        alloc[pick] += 1
        left -= 1

    taken, out = set(), {}
    for e in sorted(LIB, key=lambda e: RECENCY_RANK[e]):
        picks = _pick(e, alloc[e], scores, taken)
        taken.update(picks)
        out[e] = picks
    return out


def explain(posting, budget=11):
    scores = bullet_scores(posting)
    a = allocate(posting, budget)
    ts = sorted(theme_scores(posting).items(), key=lambda x: -x[1])[:8]
    return dict(themes=[t for t, _ in ts],
                alloc={e: len(v) for e, v in a.items()},
                picks={e: [(b, round(scores[b], 1)) for b in v] for e, v in a.items()})


def uncued_themes():
    """Themes the profile's bullets carry that no cue matches.

    Such a theme adds nothing to any posting's score, so a bullet tagged only
    with it is chosen on weight alone. /setup runs this after writing
    bullets.py; every name it returns needs cues in THEME_CUES there.
    """
    return sorted({t for ts in THEMES.values() for t in ts} - set(CUE_RE))


if __name__ == "__main__":
    missing = uncued_themes()
    for t in missing:
        print(f"no cues for theme {t!r}: add it to THEME_CUES in profile/bullets.py")
    sys.exit(1 if missing else 0)
