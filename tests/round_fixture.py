"""A whole round on invented postings, with no network: the regression fixture.

A change made to make a round faster must not change which postings it finds,
their scores or their order. This is the proof. It holds one market's worth of
invented postings for the example person (profile.example/), answered the way each
source answers them:

- LinkedIn search cards, and their bodies from a stand-in detail CLI
- freehire results with their bodies inline
- an employer's Greenhouse board, through tools/offline_boards.py
- a person's own paced board whose search gives a teaser (`cityboard`), one whose
  postings may not be fetched (`nationalboard`), one gone quiet and one refusing

`scrape(out)` drives the real tools/scrape_wide.py main() over them, every request
answered here. `free_stages(kept, out)` runs the real tools/run_round.py
--from-scraped over a saved scrape, each stage its own process as in a round.
`summary(out)` is what is compared: every ranked and shortlisted posting by id,
with its scores, in order.

The saved scrape and the summary are in tests/fixtures/round/. When a change is
meant to alter what a round finds or how it scores, regenerate both and name the
difference in the pull request:

    python3 tests/round_fixture.py --regenerate

Every name and posting here is invented.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "round")
KEPT = os.path.join(FIXTURE, "kept.json")
GOLDEN = os.path.join(FIXTURE, "golden.json")
SCRAPE_GOLDEN = os.path.join(FIXTURE, "scrape.json")
TODAY = "2026-10-20"

MCR = "Manchester, England, United Kingdom"
SALFORD = "Salford, England, United Kingdom"
STOCKPORT = "Stockport, England, United Kingdom"
UK = "United Kingdom"

# --------------------------------------------------------------- the bodies

INTRO = ("{company} is hiring a {title} to join its analytics team in the North West. "
         "You will turn operational data into decisions the business acts on every week.")
DUTIES = {
    "sc": "You will own demand forecasting and inventory analytics for the network, working "
          "with operations and commercial teams on stock levels and replenishment.",
    "ops": "You will analyse operational performance across sites, build the weekly "
           "reporting pack and find where the process loses time.",
    "bi": "You will build Power BI dashboards for the leadership team and keep the reporting "
          "layer accurate and fast.",
    "fc": "You will build time-series forecasts of demand and explain the drivers to "
          "planners who rely on them.",
    "log": "You will analyse route planning, carrier performance and warehouse slotting for "
           "a logistics network.",
    "data": "You will answer questions from across the business with SQL and clear charts, "
            "and automate the reports people still build by hand.",
}
NEEDS = {
    "sql": "Strong SQL is required.",
    "py": "Python for analysis and automation is required.",
    "fc": "Experience with forecasting or time-series methods.",
    "sc": "A background in supply chain, logistics or inventory data.",
    "bi": "Experience with Power BI or Tableau for reporting.",
    "stk": "You will work with stakeholders across operations and finance, and present to "
           "cross-functional teams.",
    "spark": "Experience with Spark and Scala is required for our data platform.",
    "spark_soft": "PySpark would be a nice to have.",
}
WORK = {
    "hybrid": "Hybrid, three days a week in our Manchester office.",
    "remote": "Fully remote within the United Kingdom.",
    "site": "Based on site at our Stockport distribution centre.",
}


def body(company, title, duty, needs, pay="", years="", work="hybrid", extra=()):
    """A posting's text from its parts, in the order postings write them."""
    parts = [INTRO.format(company=company, title=title), DUTIES[duty],
             "What you will bring:\n" + "\n".join("- " + NEEDS[n] for n in needs)]
    if years:
        parts.append(f"{years} years of experience in an analytics role.")
    parts.extend(extra)
    if pay:
        parts.append(f"Salary: {pay}.")
    parts.append(WORK[work])
    return "\n\n".join(parts)


# A posting with more boilerplate than most: the requirements early, a long benefits
# and equal-opportunity tail after them. It is longer than any stage reads in full.
LONG_TAIL = ("We are an equal opportunity employer and welcome applications from everyone. "
             "Our benefits include a pension, private medical cover, a cycle to work scheme, "
             "an employee assistance programme and twenty-five days of annual leave. ") * 90

# --------------------------------------------------------------- the postings
#
# (source, request, card, body). The request is how the source was asked:
#   li:   (query, location, page, remote)      fh:   (query, page)
#   city: (query, location, page)              nat:  (query, page)
#   gh:   the Greenhouse board's token
LI = "https://www.linkedin.com/jobs/view/"


def _li(n, title, company, location, date, req, text):
    return ("li", req, {"id": str(4000000100 + n), "title": title, "company": company,
                        "url": f"{LI}{4000000100 + n}", "location": location,
                        "date": date}, text)


POSTINGS = [
    _li(1, "Senior Supply Chain Analyst", "Kestrel Mutual", MCR, "2026-10-18",
        ("supply chain analyst", MCR, 1, False),
        body("Kestrel Mutual", "Senior Supply Chain Analyst", "sc",
             ["sql", "py", "fc", "sc", "bi", "stk"], pay="£50,000 - £58,000 per year",
             years="5+")),
    _li(2, "Data Analyst", "Oakmere Foods", SALFORD, "2026-10-15",
        ("data analyst", SALFORD, 1, False),
        body("Oakmere Foods", "Data Analyst", "data", ["sql", "bi", "stk"])),
    _li(3, "Demand Planning Analyst", "Brindle Hart Logistics", STOCKPORT, "2026-10-12",
        ("demand planning analyst", STOCKPORT, 1, False),
        body("Brindle Hart Logistics", "Demand Planning Analyst", "fc", ["fc", "sc", "sql"],
             pay="£42,000 - £46,000", work="site")),
    _li(4, "Inventory Analyst", "Larkspur Retail", MCR, "2026-10-16",
        ("inventory analyst", MCR, 1, False),
        body("Larkspur Retail", "Inventory Analyst", "sc", ["sql", "sc", "bi"],
             years="3+")),
    _li(5, "Operations Analyst", "Fernhill Freight", MCR, "2026-10-17",
        ("operations analyst", MCR, 1, False),
        body("Fernhill Freight", "Operations Analyst", "ops", ["sql", "py", "stk"],
             pay="£45,000 - £50,000")),
    _li(6, "Logistics Analyst", "Wrenfield Freight Ltd", "Trafford, England, United Kingdom",
        "2026-10-14", ("logistics analyst", MCR, 1, False),
        body("Wrenfield Freight", "Logistics Analyst", "log", ["sql", "sc", "py"])),
    _li(7, "Business Intelligence Analyst", "Saltmarsh Analytics", UK, "2026-10-13",
        ("business intelligence analyst", UK, 1, True),
        body("Saltmarsh Analytics", "Business Intelligence Analyst", "bi", ["sql", "bi"],
             work="remote")),
    _li(8, "Forecasting Analyst", "Quayside Foods", MCR, "2026-10-11",
        ("forecasting analyst", MCR, 1, False),
        body("Quayside Foods", "Forecasting Analyst", "fc", ["fc", "py", "sql"],
             years="4+")),
    _li(9, "Supply Chain Data Analyst", "Northgate", "Bolton, England, United Kingdom",
        "2026-10-10", ("supply chain analyst", MCR, 2, False),
        body("Northgate", "Supply Chain Data Analyst", "sc", ["sql", "sc", "spark"])),
    _li(10, "Lead Data Analyst", "Fenwick Lane Insurance", MCR, "2026-10-19",
        ("data analyst", MCR, 1, False),
        body("Fenwick Lane Insurance", "Lead Data Analyst", "data", ["sql", "py", "stk"],
             years="10+")),
    _li(11, "Head of Supply Chain Analytics", "Dovecote Systems", MCR, "2026-10-09",
        ("supply chain analyst", MCR, 1, False),
        body("Dovecote Systems", "Head of Supply Chain Analytics", "sc", ["sc", "stk"],
             years="12+")),
    _li(12, "Graduate Data Analyst", "Greyloch", SALFORD, "2026-10-15",
        ("data analyst", SALFORD, 2, False),
        body("Greyloch", "Graduate Data Analyst", "data", ["sql"], pay="£26,000 - £34,000")),
    _li(13, "Supply Chain Analyst", "Brackenhollow Mutual", "Leeds, England, United Kingdom",
        "2026-10-12", ("supply chain analyst", UK, 1, False),
        body("Brackenhollow Mutual", "Supply Chain Analyst", "sc", ["sql", "sc", "fc"])),
    _li(14, "Data Analyst", "Northvale Bank", MCR, "2026-10-16",
        ("data analyst", MCR, 2, False),
        body("Northvale Bank", "Data Analyst", "data", ["sql", "py"],
             extra=["Applicants must hold active SC clearance."])),
    _li(15, "Operations Analyst", "Bankside Freight", MCR, "2026-10-14",
        ("operations analyst", MCR, 2, False),
        body("Bankside Freight", "Operations Analyst", "ops", ["sql", "stk"],
             extra=["Fluency in Welsh is essential for this role."])),
    _li(16, "Inventory Analyst", "Dovecote Freight", STOCKPORT, "2026-10-13",
        ("inventory analyst", STOCKPORT, 1, False),
        body("Dovecote Freight", "Inventory Analyst", "sc", ["sql", "sc"],
             extra=["You must be ACCA qualified."])),
    _li(17, "Data Analyst", "Larkspur Casino Group", MCR, "2026-10-15",
        ("data analyst", MCR, 1, False),
        body("Larkspur Casino Group", "Data Analyst", "data", ["sql", "py"])),
    _li(19, "Data Analyst", "Acme Analytics", "London, England, United Kingdom", "2026-10-15",
        ("data analyst", UK, 1, False),
        body("Acme Analytics", "Data Analyst", "data", ["sql"])),
    _li(20, "Supply Chain Analyst", "Oakmere Foods", MCR, "2026-09-25",
        ("supply chain analyst", MCR, 2, False),
        body("Oakmere Foods", "Supply Chain Analyst", "sc", ["sql", "sc"])),
    _li(21, "Operations Analyst", "Kestrel Mutual", MCR, "2026-10-16",
        ("operations analyst", MCR, 1, False),
        body("Kestrel Mutual", "Operations Analyst", "ops", ["sql", "stk"],
             pay="£40,000 - £44,000")),
    _li(23, "Data Analyst", "Brindle Hart Logistics", SALFORD, "2026-10-18",
        ("data analyst", SALFORD, 1, False),
        body("Brindle Hart Logistics", "Data Analyst", "data", ["sql", "bi", "py"],
             years="2+")),
    _li(24, "Logistics Analyst", "Saltmarsh Analytics", STOCKPORT, "2026-10-08",
        ("logistics analyst", STOCKPORT, 1, False),
        body("Saltmarsh Analytics", "Logistics Analyst", "log", ["sc", "spark_soft", "sql"])),
    # The same LinkedIn posting under a second address, on the same page of results:
    # another subdomain and its slug.
    ("li", ("data analyst", SALFORD, 1, False),
     {"id": "4000000102", "title": "Data Analyst", "company": "Oakmere Foods",
      "url": "https://uk.linkedin.com/jobs/view/data-analyst-at-oakmere-foods-4000000102",
      "location": SALFORD, "date": "2026-10-15"}, None),

    # freehire: the body comes with the search result.
    ("fh", ("demand planning analyst", 1),
     {"id": 9101, "title": "Senior Demand Planning Analyst", "company": "Greyloch",
      "url": "https://jobs.example/freehire/9101", "location": MCR, "date": "2026-10-17"},
     body("Greyloch", "Senior Demand Planning Analyst", "fc", ["fc", "sql", "py", "sc"],
          pay="£52,000 - £60,000", years="5+") + "\n\n" + LONG_TAIL),
    ("fh", ("inventory analyst", 1),
     {"id": 9102, "title": "Inventory Analyst", "company": "Northgate",
      "url": "https://jobs.example/freehire/9102", "location": MCR, "date": "2026-10-08"},
     body("Northgate", "Inventory Analyst", "sc", ["sc", "sql"])),
    ("fh", ("business intelligence analyst", 1),
     {"id": 9103, "title": "Business Intelligence Analyst", "company": "Fenwick Lane Insurance",
      "url": "https://jobs.example/freehire/9103", "location": STOCKPORT, "date": "2026-10-12"},
     body("Fenwick Lane Insurance", "Business Intelligence Analyst", "bi", ["bi", "sql"],
          pay="£28,000 - £31,000")),
    ("fh", ("logistics analyst", 1),
     {"id": 9104, "title": "Logistics Analyst", "company": "Brindle Hart Logistics",
      "url": "https://jobs.example/freehire/9104", "location": MCR, "date": "2026-10-15"},
     body("Brindle Hart Logistics", "Logistics Analyst", "log", ["sc", "sql", "py", "stk"],
          pay="£44,000 - £49,000")),
    ("fh", ("forecasting analyst", 1),
     {"id": 9105, "title": "Forecasting Analyst", "company": "Oakmere Foods",
      "url": "https://jobs.example/freehire/9105", "location": SALFORD, "date": "2026-10-19"},
     body("Oakmere Foods", "Forecasting Analyst", "fc", ["fc", "py"],
          extra=["You will apply reinforcement learning to replenishment policy."])),
    ("fh", ("operations analyst", 1),
     {"id": 9106, "title": "Operations Analyst", "company": "Quayside Foods",
      "url": "https://jobs.example/freehire/9106", "location": MCR, "date": "2026-10-14"},
     body("Quayside Foods", "Operations Analyst", "ops", ["sql", "stk"],
          extra=["This vacancy is open to internal applicants only."])),
    # Another copy of LinkedIn's first posting, older and written differently.
    ("fh", ("supply chain analyst", 1),
     {"id": 9107, "title": "Senior Supply Chain Analyst", "company": "Kestrel Mutual",
      "url": "https://jobs.example/freehire/9107", "location": MCR, "date": "2026-10-09"},
     body("Kestrel Mutual", "Senior Supply Chain Analyst", "sc",
          ["sql", "py", "fc", "sc", "stk"], years="5+")),
    # The employer's own posting, which freehire found too: one address, two sources.
    # On page one: a search walks its pages only while they hold postings (scrape_wide
    # PageWalk), so nothing sits behind an empty page one, as on a real board.
    ("fh", ("logistics analyst", 1),
     {"id": 9108, "title": "Transport Planning Analyst", "company": "Wrenfield Freight Ltd",
      "url": "https://boards.greenhouse.io/wrenfield/jobs/7004", "location": MCR,
      "date": "2026-10-16"},
     body("Wrenfield Freight", "Transport Planning Analyst", "log", ["sql", "sc", "fc"],
          pay="£46,000 - £52,000")),

    # A person's own paced board: the search gives a teaser, the posting page the rest.
    ("city", ("supply chain analyst", MCR, 1),
     {"id": "c-301", "title": "Supply Chain Analyst", "company": "Bankside Freight",
      "url": "https://cityboard.example/jobs/301", "location": "Manchester",
      "date": "2026-10-17"},
     "Bankside Freight is looking for a Supply Chain Analyst with SQL and forecasting "
     "experience to improve stock flow across its Manchester sites."),
    ("city", ("data analyst", SALFORD, 1),
     {"id": "c-302", "title": "Data Analyst", "company": "Dovecote Systems",
      "url": "https://cityboard.example/jobs/302", "location": "Salford",
      "date": "2026-10-13"},
     "A Data Analyst to build Power BI reporting and SQL models for our operations team."),
    ("city", ("inventory analyst", MCR, 1),
     {"id": "c-303", "title": "Senior Inventory Analyst", "company": "Fenwick Lane Insurance",
      "url": "https://cityboard.example/jobs/303", "location": "Manchester",
      "date": "2026-10-18"},
     "Senior Inventory Analyst. Python, SQL and stakeholder skills; hybrid in Manchester."),

    # One whose posting pages may not be fetched: its search text is the body.
    ("nat", ("operations analyst", 1),
     {"id": "n-41", "title": "Operations Analyst", "company": "Northvale Bank",
      "url": "https://nationalboard.example/41", "location": STOCKPORT, "date": "2026-10-16"},
     body("Northvale Bank", "Operations Analyst", "ops", ["sql", "py", "bi", "stk"],
          pay="£47,000 - £53,000")),
    ("nat", ("data analyst", 1),
     {"id": "n-42", "title": "Risk Analyst", "company": "Thornbury Bank",
      "url": "https://example.com/jobs/9", "location": MCR, "date": "2026-10-15"},
     body("Thornbury Bank", "Risk Analyst", "data", ["sql", "py"])),
]

# The employer board, read straight from Greenhouse.
GREENHOUSE = {"Wrenfield Freight Ltd": ("greenhouse", "wrenfield")}
GREENHOUSE_JOBS = [
    {"id": 7001, "title": "Supply Chain Analyst",
     "absolute_url": "https://boards.greenhouse.io/wrenfield/jobs/7001",
     "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-10-16",
     "content": "&lt;p&gt;Wrenfield Freight is hiring a Supply Chain Analyst.&lt;/p&gt;"
                "&lt;ul&gt;&lt;li&gt;Strong SQL and Python&lt;/li&gt;&lt;li&gt;Demand "
                "forecasting for our network&lt;/li&gt;&lt;li&gt;Power BI reporting for "
                "stakeholders&lt;/li&gt;&lt;/ul&gt;&lt;p&gt;Salary: £48,000 - £55,000.&lt;/p&gt;"},
    {"id": 7002, "title": "HGV Driver",
     "absolute_url": "https://boards.greenhouse.io/wrenfield/jobs/7002",
     "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-10-16",
     "content": "&lt;p&gt;Night trunking runs between our depots.&lt;/p&gt;"},
    {"id": 7003, "title": "Data Analyst",
     "absolute_url": "https://boards.greenhouse.io/wrenfield/jobs/7003",
     "location": {"name": "Remote - United Kingdom"}, "first_published": "2026-10-11",
     "content": "&lt;p&gt;A Data Analyst to automate reporting with SQL and Python.&lt;/p&gt;"},
    {"id": 7004, "title": "Transport Planning Analyst",
     "absolute_url": "https://boards.greenhouse.io/wrenfield/jobs/7004",
     "location": {"name": "Manchester, United Kingdom"}, "first_published": "2026-10-16",
     "content": "&lt;p&gt;Transport planning with SQL.&lt;/p&gt;"},
]

# The person's own boards, as their SKILL.md files say they may be called.
BOARDS = {
    "cityboard-search": {"enabled": "true", "contract": "1", "crawl-delay": "0.01",
                         "canary-query": "analyst"},
    "nationalboard-search": {"enabled": "true", "contract": "1", "crawl-delay": "0.01",
                             "location": "none", "detail": "false"},
    "quietboard-search": {"enabled": "true", "contract": "1", "crawl-delay": "0.01"},
    "lockedboard-search": {"enabled": "true", "contract": "1", "crawl-delay": "0.01"},
}
REFUSAL = "THROTTLED: redirecting searches to /sandbox (robots.txt disallows it); not followed."


def details() -> dict:
    """{LinkedIn id: what the detail CLI returns}."""
    out = {}
    for src, _req, card, text in POSTINGS:
        if src == "li" and text:
            out[card["id"]] = {"title": card["title"], "company": card["company"],
                               "description": text}
    return out


# --------------------------------------------------------------- the scrape

def _answer(skill: str, args: list) -> tuple[dict | None, str | None]:
    """What one portal's CLI prints for one search."""
    def flag(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    q, loc, page = flag("-q"), flag("-l"), int(flag("--page", "1"))
    remote = "--remote" in args
    if skill == "lockedboard-search":
        return None, "exit 1: " + REFUSAL
    if q in ("data", "analyst") and page == 1 and skill != "quietboard-search":
        # The health probe's broad word: any answer at all says the board works.
        return {"results": [{"id": "probe", "title": "Analyst", "company": "Probe",
                             "url": "https://probe.example/1", "location": UK,
                             "date": TODAY}]}, None
    results = []
    for src, req, card, text in POSTINGS:
        if src == "li" and skill == "linkedin-search" and req == (q, loc, page, remote):
            results.append(dict(card))
        elif src == "fh" and skill == "freehire-search" and req == (q, page):
            results.append({**card, "description": text})
        elif src == "city" and skill == "cityboard-search" and req == (q, loc, page):
            results.append({**card, "description": text})
        elif src == "nat" and skill == "nationalboard-search" and req == (q, page):
            results.append({**card, "description": text})
    return {"results": results}, None


def fake_run(cmd, timeout=90):
    """scrape_wide.run, answered from POSTINGS by the portal the command names."""
    skill = cmd[2].replace(os.sep, "/").split("/")[-4]
    return _answer(skill, cmd[4:])


def skills_dir(root: str) -> str:
    """The portals a round sees: the app's two and the person's own boards."""
    for name, front in [("linkedin-search", {"enabled": "true"}),
                        ("freehire-search", {"enabled": "true"}), *BOARDS.items()]:
        d = os.path.join(root, name, "cli", "dist")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "cli.mjs"), "w") as fh:
            fh.write("// stand-in build\n")
        lines = "\n".join(f"{k}: {v}" for k, v in front.items())
        with open(os.path.join(root, name, "SKILL.md"), "w") as fh:
            fh.write(f"---\nname: {name}\n{lines}\n---\n")
    return root


@contextlib.contextmanager
def patched(names: dict):
    """Set module attributes for the block, then put them back."""
    saved = [(mod, attr, getattr(mod, attr)) for (mod, attr) in names]
    try:
        for (mod, attr), value in names.items():
            setattr(mod, attr, value)
        yield
    finally:
        for mod, attr, value in saved:
            setattr(mod, attr, value)


def scrape(out: str, extra=(), run=None) -> tuple[int, str]:
    """The real scrape stage over POSTINGS, into `out`. (exit code, what it printed).
    `run` stands in for every portal request (fake_run, unless a test wraps it)."""
    sys.path.insert(0, TOOLS)
    import ats_boards
    import portals
    import scrape_wide
    from offline_boards import offline
    work = tempfile.mkdtemp(prefix="round_fixture_")
    saved_env = {k: os.environ.pop(k, None) for k in ("LINKEDIN_CLI", "FREEHIRE_CLI")}
    portals.cli.cache_clear()
    argv = ["scrape_wide.py", "--out", out, "--pages", "2", "--workers", "4",
            "--max-requests", "200", "--today", TODAY, "--jobage", "14", *extra]
    said = io.StringIO()
    try:
        with patched({(portals, "SKILLS"): skills_dir(os.path.join(work, "skills")),
                      (scrape_wide, "run"): run or fake_run,
                      (scrape_wide, "CLOUD"): False,
                      (scrape_wide, "SWEEP_STATE"): os.path.join(work, "cursor.json"),
                      (scrape_wide, "PORTAL_LOCATIONS"): {},
                      (ats_boards, "BOARDS"): dict(GREENHOUSE),
                      (sys, "argv"): argv}), \
                offline({"boards-api.greenhouse.io/v1/boards/wrenfield/jobs":
                         {"jobs": GREENHOUSE_JOBS}}), \
                contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            code = scrape_wide.main()
    finally:
        portals.cli.cache_clear()
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(work, ignore_errors=True)
    return code, said.getvalue()


def by_address(rows: list) -> list:
    """Rows in an order that does not depend on which request finished first."""
    return sorted(rows, key=lambda r: (r.get("url") or "", r.get("portal") or ""))


def scrape_summary(out: str) -> dict:
    """What the scrape dropped and what its health probe found. What it kept is
    tests/fixtures/round/kept.json itself, compared by address."""
    with open(os.path.join(out, "dropped.json"), encoding="utf-8") as fh:
        dropped = by_address(json.load(fh))
    health = os.path.join(out, "00_portal_health.json")
    return {"dropped": dropped,
            "health": json.load(open(health, encoding="utf-8")) if os.path.exists(health) else None}


# --------------------------------------------------------------- the free stages

DETAIL_CLI = r"""
import { readFileSync } from "node:fs";
const [, , cmd, id] = process.argv;
const map = JSON.parse(readFileSync(process.env.ROUND_FIXTURE_DETAILS, "utf8"));
const delays = JSON.parse(process.env.ROUND_FIXTURE_DELAYS || "{}");
const d = map[id];
const wait = Number(delays[id] || 0);
const answer = () => {
  if (cmd !== "detail" || !d) {
    process.stderr.write(JSON.stringify({ error: `no posting ${id}` }) + "\n");
    process.exit(1);
  }
  process.stdout.write(JSON.stringify(d));
};
if (wait) setTimeout(answer, wait); else answer();
"""


def state_copy(root: str) -> str:
    """A fresh copy of the example person's state, so no other test's writes reach it."""
    dest = os.path.join(root, "state")
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), dest, dirs_exist_ok=True)
    return dest


def free_stages(kept: str, out: str, work: str, delays: dict | None = None,
                workers: int = 4) -> subprocess.CompletedProcess:
    """tools/run_round.py --from-scraped over a saved scrape, offline, writing nothing
    into the repo or the state the other tests share."""
    state = state_copy(work)
    cli = os.path.join(work, "linkedin_detail.mjs")
    with open(cli, "w") as fh:
        fh.write(DETAIL_CLI)
    detail_map = os.path.join(work, "details.json")
    with open(detail_map, "w", encoding="utf-8") as fh:
        json.dump(details(), fh)
    env = dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example"),
               LJS_STATE=state, LINKEDIN_CLI=cli, ROUND_FIXTURE_DETAILS=detail_map,
               ROUND_FIXTURE_DELAYS=json.dumps(delays or {}), LJS_RESCREEN="off",
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("FREEHIRE_CLI", None)
    seen = os.path.join(state, "job_scraper", "seen_jobs.json")
    tracker = os.path.join(state, "job_search_tracker.csv")
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, "run_round.py"), "--from-scraped", kept,
         "--out", out, "--today", TODAY, "--workers", str(workers), "--keep-intermediates",
         "--no-seen-write", "--seen", seen, "--tracker", tracker,
         "--summary-dir", os.path.join(work, "summary")],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


# What is compared: who is ranked and shortlisted, their scores and their order, and
# what the screen cut and why. Bodies and reasons in full would make every wording
# change a fixture change; these are the decisions.
RANKED = ("id", "url", "fit", "opportunity", "priority", "priority_exact")
SHORT = RANKED + ("bar", "warm_route_note", "outreach_pending_note", "throttle_override_note",
                  "drafted_note")


def summary(out: str) -> dict:
    def load(name):
        with open(os.path.join(out, name), encoding="utf-8") as fh:
            return json.load(fh)

    def pick(rows, keys):
        return [{k: r.get(k) for k in keys if r.get(k) is not None} for r in rows]
    screened = load("03_screened_all.json")
    return {
        "prefiltered": [r.get("url") for r in load("01_prefiltered.json")],
        "cut": sorted([r.get("url"), r.get("cuts")] for r in screened
                      if r.get("text_screen") == "cut"),
        "ranked": pick(load("05_ranked.json"), RANKED),
        "shortlist": pick(load("06_shortlist.json"), SHORT),
        "skipped": sorted([r.get("url"), str(r.get("throttle_reason") or r.get("skip_reason")
                                              or r.get("reason") or "")[:60]]
                          for r in load("06_skipped.json")),
    }


def regenerate() -> None:
    os.makedirs(FIXTURE, exist_ok=True)
    work = tempfile.mkdtemp(prefix="round_fixture_regen_")
    try:
        out = os.path.join(work, "scrape")
        code, said = scrape(out)
        print(said[-3000:])
        with open(SCRAPE_GOLDEN, "w", encoding="utf-8") as fh:
            json.dump({"exit": code, **scrape_summary(out)}, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        # The saved scrape keeps its order while what it holds is unchanged: the order
        # rows land in is the order the requests finished, and a new order alone would
        # be a fixture change that is no change at all.
        # A posting already saved keeps its place; a new one goes at the end.
        with open(os.path.join(out, "kept.json"), encoding="utf-8") as fh:
            fresh = json.load(fh)
        try:
            with open(KEPT, encoding="utf-8") as fh:
                old = [(r.get("url"), r.get("portal")) for r in json.load(fh)]
        except (OSError, ValueError):
            old = []
        place = {k: i for i, k in enumerate(old)}
        fresh.sort(key=lambda r: place.get((r.get("url"), r.get("portal")), len(place)))
        with open(KEPT, "w", encoding="utf-8") as fh:
            json.dump(fresh, fh, indent=1)
        r = free_stages(KEPT, os.path.join(work, "r1"), work)
        print(r.stdout[-3000:], r.stderr[-3000:])
        r.check_returncode() if r.returncode not in (0, 2) else None
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(summary(os.path.join(work, "r1")), fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {os.path.relpath(KEPT, ROOT)}, {os.path.relpath(SCRAPE_GOLDEN, ROOT)} "
          f"and {os.path.relpath(GOLDEN, ROOT)}")


if __name__ == "__main__":
    if sys.argv[1:] != ["--regenerate"]:
        sys.exit("usage: python3 tests/round_fixture.py --regenerate")
    os.environ.setdefault("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    _state = tempfile.mkdtemp(prefix="round_fixture_state_")
    os.environ["LJS_STATE"] = state_copy(_state)
    os.environ["LJS_RESCREEN"] = "off"
    try:
        regenerate()
    finally:
        shutil.rmtree(_state, ignore_errors=True)
