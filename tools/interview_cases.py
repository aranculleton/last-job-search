#!/usr/bin/env python3
"""Practice cases for a case round, picked by the kind of employer, worked out loud.

A case round is not answered from the profile: the interviewer hands over a problem
(a depot ships late, a metric fell, a test came back) and listens to the person reason
through it, numbers said as they go. A prep that only listed "expect a case" left the
person to find one to practise on. This is a small library of them, each with:

  prompt    what the interviewer says, word for word
  steps     the reasoning, said out loud, one step a line, with the sums in them
  numbers   the few numbers the answer turns on, to say back at the end
  visual    the framework drawn in plain text, no wider than 40 characters, so it
            reads on a phone and can be sketched on paper in the room

Every number here is invented and round, for practice: none of it is a claim about the
person, and none of it is said as their own work.

    python3 tools/interview_cases.py list
    python3 tools/interview_cases.py show <id>
    python3 tools/interview_cases.py for "<employer kind, or any words for it>"

`cases_for(kind)` takes any words for the employer ("a logistics company", the pack's
employer type "consulting", the catalogue's "technology company") and matches them
loosely; words it cannot place get the general cases.
"""
from __future__ import annotations

import re
import sys

KEYS = ("id", "title", "type", "prompt", "steps", "numbers", "visual")
WIDTH = 40

CASES: tuple[dict, ...] = (
    # Operations: bottleneck, capacity, utilisation, backlog.
    {
        "id": "ops-bottleneck",
        "title": "Bottleneck: a depot that ships late",
        "type": "operations",
        "prompt": "A parcel depot runs three stations: picking, packing and labelling. "
                  "It has to send 1,200 orders in an 8-hour shift, and orders keep "
                  "shipping late. Where is the problem, and what would you do?",
        "steps": [
            "First the demand: 1,200 orders over 8 hours is 150 an hour that has to "
            "get through every station.",
            "Then each station's capacity. Picking is 4 people at 40 an hour, so 160. "
            "Packing is 3 people at 45, so 135. Labelling is one machine at 200.",
            "The slowest station sets the pace for the whole line, and packing at 135 "
            "is below the 150 needed, so packing is the bottleneck. I'd check that the "
            "queue of work actually piles up in front of packing.",
            "Sizing it: 15 orders short an hour, times 8 hours, is 120 orders a day "
            "carried over, which is the late shipping.",
            "Options: add a packer, which takes packing to 4 times 45, 180 an hour; run "
            "packing one hour longer, 135 times 9 is 1,215, just enough; or make packing "
            "10% faster, 3 people at about 50 is 150, with no room to spare.",
            "Then check where the bottleneck moves. With 4 packers, picking at 160 is "
            "the new limit, only 10 an hour above demand, so a busy day would hit it.",
            "I'd recommend the extra packer, then watch picking on peak days and measure "
            "orders shipped late each week to confirm it worked.",
        ],
        "numbers": ["Need 150 an hour", "Packing 135 an hour",
                    "120 orders a day carried over", "4 packers give 180 an hour"],
        "visual": "\n".join([
            "Station  per hour",
            "Pick     160 ################",
            "Pack     135 #############  <- limit",
            "Label    200 ####################",
            "Need     150 ###############",
        ]),
    },
    {
        "id": "ops-capacity",
        "title": "Capacity: how many people for next quarter",
        "type": "operations",
        "prompt": "A support team answers 6,000 calls a week with 24 agents. Volume "
                  "grows 25% next quarter. Each agent handles 10 calls an hour over 30 "
                  "productive hours a week. How many agents do we need?",
        "steps": [
            "I'd confirm the 30 hours already leaves out breaks and training, and that "
            "the time per call stays the same.",
            "Next quarter's demand: 6,000 times 1.25 is 7,500 calls a week.",
            "One agent's capacity: 10 calls an hour times 30 hours is 300 calls a week.",
            "The pure need is 7,500 divided by 300, so 25 agents.",
            "But nobody plans a team at 100% busy, or every spike becomes a queue. At "
            "an 85% target, 25 divided by 0.85 is 29.4, so 30 agents.",
            "We have 24, so that's 6 more. If hiring and training take 8 weeks, the "
            "hiring has to start now.",
            "Other levers before hiring all 6: 10% faster calls is 11 an hour, 330 a "
            "week, and 7,500 over 330 over 0.85 is about 27 agents; or self-service that "
            "takes 10% of the calls away.",
        ],
        "numbers": ["7,500 calls a week", "300 calls per agent a week",
                    "25 agents at 100%, 30 at 85%", "6 to hire"],
        "visual": "\n".join([
            "Demand    7,500 calls a week",
            "/ Rate      300 per agent",
            "= Need       25 agents",
            "/ 0.85   target busy level",
            "= Plan       30 agents",
            "- Have       24",
            "= Hire        6",
        ]),
    },
    {
        "id": "ops-utilisation",
        "title": "Utilisation: cut the fleet or not",
        "type": "operations",
        "prompt": "A delivery firm runs 50 vans. Finance says they're only 60% used "
                  "and wants to sell 10. Should they?",
        "steps": [
            "First what 60% means: 50 vans times 10 hours a day is 500 van-hours, and "
            "300 are spent on routes, so 60%.",
            "An average hides the peak, so I'd look by day. Say Monday and Friday "
            "mornings have 46 vans out, 92%, and midweek about 24.",
            "With 40 vans, the Monday and Friday peak of 46 is 6 vans short, two days a "
            "week.",
            "The saving: if a van costs about $1,000 a month all in, 10 vans is $10,000 "
            "a month, $120,000 a year.",
            "The cost of being short: renting 6 vans at $150 a day, on about 104 peak "
            "days a year, is about $94,000. So the real saving is only about $26,000, "
            "with the risk of late deliveries on the busiest days.",
            "A better route is to flatten the peak first: move some Monday deliveries "
            "to Tuesday with cheaper delivery slots, then cut.",
            "I'd recommend selling 4 vans now, which still covers the peak of 46, and "
            "deciding on the rest after the peak is flatter.",
        ],
        "numbers": ["60% average, 92% at peak", "Peak needs 46 vans",
                    "$120,000 saving before rentals", "About $26,000 after"],
        "visual": "\n".join([
            "Vans out at peak (of 50)",
            "Mon ####################### 46",
            "Tue ############ 24",
            "Wed ############ 24",
            "Thu ############# 26",
            "Fri ####################### 46",
            "Average 60%   Peak 92%",
        ]),
    },
    {
        "id": "ops-backlog",
        "title": "Backlog: clear it in 12 weeks",
        "type": "operations",
        "prompt": "A returns team has 4,000 cases waiting. 900 new cases arrive a week "
                  "and the team closes 800. Leadership wants the backlog gone in 12 "
                  "weeks. What's your plan?",
        "steps": [
            "First the direction: 900 in and 800 out means the backlog grows by 100 a "
            "week. Doing nothing makes it worse.",
            "How long a case waits: the backlog divided by what we close, 4,000 over "
            "800, is 5 weeks.",
            "To clear it in 12 weeks, the team has to close the 900 arriving plus "
            "4,000 over 12, about 333, so roughly 1,233 a week, 54% more than today.",
            "I'd look at why cases arrive before adding people. Say 15% of arrivals are "
            "repeats from mistakes, about 135 a week; halving those cuts arrivals to "
            "about 832, and the target to about 1,165.",
            "Then capacity: 10% overtime takes 800 to 880. The gap of about 285 a week, "
            "at 40 a week per temporary worker once trained, is about 7 people.",
            "Sort the queue too: quick cases first clears the count fast, but the oldest "
            "cases need a lane of their own so nobody waits for months.",
            "I'd track four numbers weekly: arrivals, closed, backlog, and the age of "
            "the oldest case.",
        ],
        "numbers": ["Grows 100 a week today", "5 weeks wait now",
                    "About 1,233 a week to clear in 12", "7 temporary workers"],
        "visual": "\n".join([
            " In 900 a week",
            "     |",
            "     v",
            "[ 4,000 waiting ]",
            "     |   wait = 4,000 / 800",
            "     v        = 5 weeks",
            " Out 800 a week",
            "Net: grows 100 a week",
        ]),
    },
    # Analytics and data: a metric that fell, a test readout, a forecast that missed.
    {
        "id": "data-metric-drop",
        "title": "Metric drop: weekly users down 8%",
        "type": "analytics",
        "prompt": "Weekly active users on our app fell 8% last week. Walk me through how "
                  "you'd find out why.",
        "steps": [
            "First, is it real? I'd check for a tracking change, a broken dashboard or an "
            "outage, and compare with a second source like server logs.",
            "Then the shape: a drop on one day points to a release, an outage or "
            "tracking; a slow slide points to the product or the market.",
            "Outside reasons: a holiday, the season. Say the same week last year fell "
            "only 1%, so the season doesn't explain 8%.",
            "Then split it: by platform, country, new and returning users. Say iOS is "
            "flat and Android is down 20%.",
            "Check it adds up: Android is 40% of users, and 40% times a 20% drop is "
            "8%, so Android explains the whole fall.",
            "Narrow it: the new Android version went out on Tuesday, and only users on "
            "it fell. Login success on it is 70%, against 97% on the old one.",
            "So: about 40,000 of 500,000 users lost, a login bug in one release. Fix or "
            "roll it back, add an alert on login success, and watch the recovery.",
        ],
        "numbers": ["8% of 500,000 is 40,000 users", "Android 40% of users, down 20%",
                    "Login success 70% against 97%"],
        "visual": "\n".join([
            "Weekly users -8%",
            " |-- Real? tracking, outage",
            " |-- Outside? season, holiday",
            " '-- Inside: split it",
            "      |-- iOS      flat",
            "      '-- Android  -20%",
            "           '-- new version",
            "               login 70%",
        ]),
    },
    {
        "id": "data-ab-readout",
        "title": "A/B test readout: ship the new button?",
        "type": "analytics",
        "prompt": "We tested a new checkout button. Control had 20,000 users converting "
                  "at 4.0%; the new button had 20,000 at 4.4%. The product manager wants "
                  "to ship. What do you tell them?",
        "steps": [
            "The lift is 0.4 points, which is 10% in relative terms.",
            "Is it more than noise? The standard error of the difference is about the "
            "square root of 0.042 times 0.958 times 2 over 20,000, which is about 0.2 "
            "points.",
            "So the z score is 0.4 over 0.2, which is 2.0, a p-value just under 5%. It "
            "only just passes.",
            "The 95% range is 0.4 plus or minus 1.96 times 0.2: from about 0 to 0.8 "
            "points. The true lift could be close to nothing.",
            "Checks before trusting it: the split really was 50-50, it ran full weeks, "
            "nobody stopped it early on a good day, and conversion was the metric "
            "chosen before it started.",
            "Guardrails: average order value and refunds. Say order value stayed at "
            "$50.",
            "Worth: 0.4 points on a million checkout visits a month at $50 is about "
            "$200,000 a month at the middle estimate. I'd ship it, since it's cheap to "
            "undo, but say plainly the range runs down to about zero.",
        ],
        "numbers": ["+0.4 points, +10%", "z = 2.0", "95% range 0 to 0.8 points",
                    "About $200,000 a month at the middle"],
        "visual": "\n".join([
            "         Users   Converted",
            "Control  20,000  4.0%",
            "New      20,000  4.4%",
            "Lift     +0.4 points (+10%)",
            "Error    about 0.2 points",
            "z        0.4 / 0.2 = 2.0",
            "95%      0.0 to +0.8 points",
        ]),
    },
    {
        "id": "data-forecast-error",
        "title": "Forecast error: the team stopped trusting it",
        "type": "analytics",
        "prompt": "Our demand forecast was 12% off last month and the operations team "
                  "has stopped using it. How would you find what's wrong and fix it?",
        "steps": [
            "First, which way it was off. Say we forecast 8,800 and sold 10,000: 1,200 "
            "under, 12% of what we sold.",
            "Then the last six months: -8, -10, -11, -9, -10 and -12%. Always under, "
            "averaging -10%. That's bias, not noise; noise would swing both ways.",
            "Bias means something real is missing from the model. I'd split the error "
            "by region and product.",
            "Say the older regions are within 2%, and a region opened this year is "
            "missing from the training data altogether, about 1,000 units a month.",
            "Fix: add the new region and a calendar of promotions, then test it on the "
            "last six months as if live. Say the average error falls from 10% to 3%.",
            "Win the team back: give a range, not one number, say 80% of months land "
            "within 5%, and share a weekly chart of forecast against actual.",
        ],
        "numbers": ["12% under last month", "-10% on average over six months",
                    "About 1,000 units a month missing", "10% error down to 3%"],
        "visual": "\n".join([
            "Error by month",
            "Jan  -8% ########",
            "Feb -10% ##########",
            "Mar -11% ###########",
            "Apr  -9% #########",
            "May -10% ##########",
            "Jun -12% ############",
            "Always under: bias, not noise",
        ]),
    },
    # Finance: a threshold to set, a rate that moved.
    {
        "id": "fin-fraud-threshold",
        "title": "Fraud threshold: block less or more",
        "type": "finance",
        "prompt": "A card issuer blocks any payment with a fraud score above 0.8. That "
                  "blocks 2,000 payments a day, 400 of them fraud, and customers are "
                  "complaining. Would you move the threshold?",
        "steps": [
            "First precision: 400 of 2,000 blocks are fraud, 20%. So 1,600 good "
            "customers a day are blocked.",
            "Put a cost on both mistakes. Say missed fraud loses $300 on average, and a "
            "wrong block costs about $10 in calls and annoyed customers.",
            "Today, with 500 frauds a day: 1,600 wrong blocks at $10 is $16,000, plus "
            "100 missed frauds at $300 is $30,000. $46,000 a day.",
            "At 0.9: 800 blocks, 340 fraud, 460 wrong, 160 missed. $4,600 plus $48,000 "
            "is $52,600. Worse.",
            "At 0.7: 4,000 blocks, 450 fraud, 3,550 wrong, 50 missed. $35,500 plus "
            "$15,000 is $50,500. Also worse.",
            "So 0.8 is about right. The better fix is the action, not the threshold: for "
            "scores from 0.8 to 0.9, send a text to confirm instead of blocking.",
            "If a text check costs $2 instead of $10, the wrong-block cost falls a lot. "
            "I'd test it on a share of customers and watch fraud losses and complaints.",
        ],
        "numbers": ["20% of blocks are fraud", "$46,000 a day at 0.8",
                    "$52,600 at 0.9, $50,500 at 0.7"],
        "visual": "\n".join([
            "Cut  Block Fraud Wrong Miss Cost",
            "0.7  4,000  450  3,550   50 $50.5k",
            "0.8  2,000  400  1,600  100 $46.0k",
            "0.9    800  340    460  160 $52.6k",
            "Wrong $10 each, missed $300",
        ]),
    },
    {
        "id": "fin-approval-rate",
        "title": "Approval rate: down from 60% to 50%",
        "type": "finance",
        "prompt": "A lender's approval rate on personal loans fell from 60% to 50% in a "
                  "month, with applications flat at 10,000. Why, and is it a problem?",
        "steps": [
            "First the definition: approved over applications decided, and whether the "
            "lending rules or the model changed this month.",
            "Say nothing changed in the rules. Then I'd split by where applications "
            "come from: direct, and through comparison sites.",
            "Direct approves 70% and comparison sites 30%, and neither rate moved.",
            "Last month: 7,500 direct at 70% is 5,250, plus 2,500 from comparison "
            "sites at 30% is 750. 6,000 approved, 60%.",
            "This month: 5,000 direct at 70% is 3,500, plus 5,000 at 30% is 1,500. "
            "5,000 approved, 50%.",
            "So it's the mix, not the decisions: half the applications now come from "
            "comparison sites. 1,000 fewer loans a month.",
            "Is it a problem? Not for credit quality. But I'd ask marketing why direct "
            "fell, and check what comparison-site applications cost per loan made.",
        ],
        "numbers": ["70% direct, 30% comparison sites, both unchanged",
                    "Mix went from 75/25 to 50/50", "1,000 fewer loans a month"],
        "visual": "\n".join([
            "          Before      After",
            "Direct  7,500 x 70%  5,000 x 70%",
            "Sites   2,500 x 30%  5,000 x 30%",
            "Approved 6,000 (60%) 5,000 (50%)",
            "Same rates, new mix",
        ]),
    },
    # General: any employer, consulting firms first.
    {
        "id": "gen-profit-decline",
        "title": "Profit down while sales grew",
        "type": "general",
        "prompt": "A coffee chain's revenue grew 5% this year, but profit fell 20%. "
                  "What happened?",
        "steps": [
            "Profit is revenue minus costs. Say revenue went from $100M to $105M and "
            "profit from $10M to $8M, so costs went from $90M to $97M, up about 8%.",
            "Split the costs: goods sold went 30 to 31.5, still 30% of revenue, so "
            "normal. Rent 25 to 25.5, small.",
            "Staff went from 35 to 40, up 14%. That's where the money went.",
            "Split staff: a 6% pay rise is about 2.1. The other 2.9 came from opening "
            "later in the evening.",
            "Did the evenings pay? Say evening sales brought in about $1M of the $5M "
            "growth, for $2.9M of staff. They lose about $1.9M.",
            "I'd recommend keeping evenings only where they cover their staff, which "
            "takes back most of the profit, and checking store by store.",
        ],
        "numbers": ["Costs up $7M on revenue up $5M", "Staff up 14%",
                    "Evenings: $1M sales for $2.9M staff"],
        "visual": "\n".join([
            "Profit = Revenue - Costs",
            "   10>8   100>105   90>97",
            "Costs ($M)",
            " Goods  30.0>31.5  same share",
            " Staff  35.0>40.0  +14%  <-",
            " Rent   25.0>25.5",
        ]),
    },
    {
        "id": "gen-market-sizing",
        "title": "Market sizing: home car chargers",
        "type": "general",
        "prompt": "How many home chargers for electric cars could be sold each year in "
                  "a country of 40 million people?",
        "steps": [
            "I'll go from households, since a charger is fitted to a home. 40 million "
            "people at 2.5 per home is 16 million households.",
            "Only homes with a driveway or garage can fit one; say 60%, so 9.6 million.",
            "People fit a charger when they get the car. Say a household buys a car "
            "every 8 years: 9.6 million over 8 is 1.2 million a year.",
            "Say 20% of those choose electric: 240,000 a year.",
            "Say 70% of them fit a charger: about 168,000 a year. At $1,000 each, about "
            "$170M.",
            "Sanity check from the other side: 2 million cars sold a year, 20% electric "
            "is 400,000, and about 40% of buyers fitting one at home is 160,000. Close.",
            "So about 170,000 a year, growing with the electric share, which is the "
            "number I'd test hardest.",
        ],
        "numbers": ["16 million households", "1.2 million car buyers a year",
                    "About 168,000 chargers, about $170M"],
        "visual": "\n".join([
            "40M people / 2.5 a home",
            " = 16M households",
            " x 60% with a driveway",
            " = 9.6M",
            " / 8 years between cars",
            " = 1.2M a year",
            " x 20% choose electric",
            " = 240k",
            " x 70% fit a charger",
            " = 168k a year (~$170M)",
        ]),
    },
    {
        "id": "gen-prioritisation",
        "title": "Prioritisation: five asks, one quarter",
        "type": "general",
        "prompt": "Five teams have each asked you for a piece of work, and you have 8 "
                  "weeks this quarter. How do you choose?",
        "steps": [
            "First the quarter's goal. Say it's keeping customers, so value means how "
            "much a piece of work helps that.",
            "Score each for value out of 10 and weeks of effort: a churn model 8 and 3; "
            "a pricing test 9 and 6; a data quality fix 6 and 2; a dashboard rebuild 4 "
            "and 5; an automated report 3 and 1.",
            "Value per week: data fix 3.0, report 3.0, churn model 2.7, pricing test "
            "1.5, dashboard 0.8.",
            "Fill the 8 weeks: data fix, churn model and report is 6 weeks for 17 "
            "points. The pricing test plus the data fix is 8 weeks for only 15.",
            "Check what depends on what: the churn model needs the data fix first, so "
            "that order holds.",
            "Keep the 2 spare weeks for what breaks, and tell the dashboard and pricing "
            "teams no for now, with when it could be next quarter.",
        ],
        "numbers": ["8 weeks to spend", "Data fix, churn model, report: 6 weeks, 17 points",
                    "Pricing test and data fix: 8 weeks, 15 points"],
        "visual": "\n".join([
            "Value",
            " high | Pricing  | Churn, Data",
            "      |          |",
            " low  | Dashbd   | Report",
            "      +----------+------------",
            "        slow       quick",
        ]),
    },
)

# What each kind of employer is likely to set as a case, in the order to practise them.
# A kind's own cases come first; the general ones always follow.
KINDS: dict[str, tuple[str, ...]] = {
    "operations": ("ops-bottleneck", "ops-capacity", "ops-utilisation", "ops-backlog"),
    "analytics": ("data-metric-drop", "data-ab-readout", "data-forecast-error"),
    "finance": ("fin-fraud-threshold", "fin-approval-rate", "data-forecast-error"),
    "consulting": ("gen-profit-decline", "ops-bottleneck", "ops-backlog",
                   "data-metric-drop"),
    "general": (),
}
GENERAL = ("gen-profit-decline", "gen-market-sizing", "gen-prioritisation")

# Words that place free text in a kind. The pack's employer types ("consulting", "bank",
# "public sector", "startup", "product") and the catalogue's words ("technology company",
# "software product", "professional services") are all here.
_WORDS: dict[str, re.Pattern] = {
    "operations": re.compile(
        r"\b(?:operations?|ops|supply chain|logistics?|manufactur\w*|warehous\w*|"
        r"distribution|fulfil+ment|transport\w*|delivery|retail\w*|public sector|"
        r"government|health ?care|hospital|utilit\w*|energy|airlines?|airport|"
        r"capacity|backlog|bottleneck|utili[sz]ation)\b", re.I),
    "analytics": re.compile(
        r"\b(?:data|analytics?|technology|tech|software|product|saas|platform|"
        r"marketplace|apps?|start-?up|scale-?up|media|streaming|e-?commerce|"
        r"consumer|growth|experiment\w*)\b", re.I),
    "finance": re.compile(
        r"\b(?:banks?|banking|fintech|lend\w*|loans?|credit|payments?|financial|"
        r"finance|insur\w*|asset manag\w*|risk|fraud|cards?)\b", re.I),
    "consulting": re.compile(
        r"\b(?:consult\w*|advisory|professional services|strategy)\b", re.I),
}

# On a tie, the narrower kind wins: "a fintech start-up" is finance before it is analytics.
_TIES = ("finance", "consulting", "operations", "analytics")

_BY_ID = {c["id"]: c for c in CASES}


def kinds() -> list[str]:
    """Every kind of employer the library has cases for, the fallback last."""
    return list(KINDS)


def kind_of(kind: str | None) -> str:
    """The kind these words name: a kind's own name, else the one whose words they match
    most (the earlier kind on a tie), else "general"."""
    said = " ".join(str(kind or "").lower().replace("_", " ").replace("-", " ").split())
    if said in KINDS:
        return said
    hits = {k: len(rx.findall(said)) for k, rx in _WORDS.items()}
    best = max(hits.values(), default=0)
    return next((k for k in _TIES if hits[k] == best), "general") if best else "general"


def _copy(case: dict) -> dict:
    return {k: (list(case[k]) if isinstance(case[k], list) else case[k]) for k in KEYS}


def case(case_id: str) -> dict | None:
    """One case by its id, or None."""
    found = _BY_ID.get(str(case_id or "").strip().lower())
    return _copy(found) if found else None


def cases_for(kind: str) -> list[dict]:
    """The cases to practise for this kind of employer, any words for it: its own first,
    then the general ones, each once."""
    ids = KINDS[kind_of(kind)] + GENERAL
    seen: list[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return [_copy(_BY_ID[i]) for i in seen]


def render(c: dict) -> str:
    """One case as it is read before saying it out loud."""
    out = [c["title"], "", "They say: " + c["prompt"], "", "Out loud:"]
    out += ["%d. %s" % (n, s) for n, s in enumerate(c["steps"], 1)]
    out += ["", "The numbers to land:"] + ["- " + n for n in c["numbers"]]
    out += ["", "Sketch:", c["visual"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    if cmd == "list" and len(args) == 1:
        for c in CASES:
            print("%-20s %-11s %s" % (c["id"], c["type"], c["title"]))
        return 0
    if cmd == "show" and len(args) == 2:
        c = case(args[1])
        if not c:
            print("No practice case called %r. See them all with: python3 "
                  "tools/interview_cases.py list" % args[1], file=sys.stderr)
            return 1
        print(render(c))
        return 0
    if cmd == "for" and len(args) >= 2:
        words = " ".join(args[1:])
        print("Cases to practise for %s (%s):" % (words, kind_of(words)))
        for c in cases_for(words):
            print("%-20s %s" % (c["id"], c["title"]))
        return 0
    print(__doc__.split("    python3")[0].strip().splitlines()[0], file=sys.stderr)
    print("Use: python3 tools/interview_cases.py list | show <id> | for <kind>",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
