"""Morgan Ellis's skills. Fictional.

The shape every profile's skills.py takes. tools/skills_block.py reads NOT_HELD,
ITEMS, SECONDARY, PINNED and ANCHORS; tools/bridges.py reads BRIDGES. Categories
in ITEMS are lang, model, eng, bi and work (skills_block folds them onto three
printed lines). No ITEMS pattern may match a NOT_HELD one (a test checks).
"""

HELD = "held"
BRIDGE = "bridge"
GAP = "gap"

# name -> (how a posting spells it, why it is not held)
NOT_HELD = {
    "chartered credential": (r"\bCIPS\b|\bMCIPS\b|\bCILT\b|\bACCA\b|\bCIMA\b",
                             "a credential, not a skill: awarded by an examining body"),
    "SAP configuration": (r"\bSAP (?:configuration|ABAP)\b|\bABAP\b",
                          "has reported from SAP, never configured it"),
}

# (category, canonical item, regex that recognizes it in a free-form tools string)
ITEMS = [
    ("lang", "SQL", r"\bSQL\b(?!\s*Server)"),
    ("lang", "Python, pandas", r"\bPython\b|\bpandas\b"),
    ("lang", "Excel", r"(?-i:\bExcel\b)"),
    ("model", "demand forecasting", r"\bforecast\w*\b"),
    ("model", "inventory optimisation", r"\binventory (?:optimi[sz]ation|planning)\b|\bsafety stock\b"),
    ("model", "route optimisation", r"\broute (?:optimi[sz]ation|planning)\b|\brouting\b"),
    ("model", "A/B testing", r"\bA/B\b|\bexperiment\w*\b|\bpilot\b"),
    ("model", "statistics", r"\bstatistic\w*\b"),
    ("eng", "dbt", r"\bdbt\b"),
    ("eng", "data quality testing", r"\bdata[- ]quality\b"),
    ("eng", "Azure SQL", r"\bAzure SQL\b"),
    ("bi", "Power BI", r"\bpower\s?bi\b"),
    ("bi", "Tableau", r"\btableau\b"),
    ("work", "stakeholder reporting", r"\bstakeholder\w*\b"),
    ("work", "Jira", r"\bJira\b"),
]

# Held, but shown only when a posting names them.
SECONDARY = frozenset({"Tableau", "Azure SQL"})

# Nothing is pinned for this person.
PINNED = None

ANCHORS = ("SQL", "Python, pandas")

# The Skills block: one (line, heading) per rendered line, in page order, in
# the person's own words for their work. Categories in ITEMS that have no line
# of their own print on the line MERGE names.
LABELS = [
    ("lang", "Languages and modelling"),
    ("eng", "Data engineering and cloud"),
    ("bi", "BI, tooling and delivery"),
]
MERGE = {"model": "lang", "work": "bi"}
MAX_PER_LINE = {"lang": 7, "eng": 6, "bi": 5}

BRIDGES = [
    dict(asked="Power BI", pattern=r"\bpower\s?bi\b", verdict=HELD,
         have=["Power BI"], line="Power BI is the reporting tool I own day to day."),
    dict(asked="Tableau", pattern=r"\btableau\b", verdict=BRIDGE, strength="near",
         have=["Power BI", "Tableau"],
         line="I build in Power BI now and built client dashboards in Tableau before that."),
    dict(asked="SAP", pattern=r"\bSAP\b", verdict=BRIDGE, strength="mid",
         have=["SQL over the warehouse-management system"],
         line="I have reported from SAP extracts and the warehouse system behind them."),
    dict(asked="Chartered procurement", pattern=r"\bCIPS\b|\bMCIPS\b", verdict=GAP,
         strength="far", have=[], line="",
         note="A credential, not a skill. Do not claim it."),
]
