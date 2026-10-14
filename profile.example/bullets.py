"""Morgan Ellis's work history as resume bullets. Fictional throughout.

The shape every profile's bullets.py takes, read by tools/bullet_library.py:
employer -> bullet id -> (themes, weight, text). THEMES come from the keys of
tools/allocate.py THEME_CUES; WEIGHT is 6 to 10, how strong the bullet is when
nothing in a posting matches it; text is LaTeX (escape %, $, &, #, _).
"""

LIB = {
 "Brindle & Hart Logistics": {
  "BH_FORECAST": (
    {"forecasting", "modelling", "python", "sql", "commercial"}, 10,
    r"Built weekly demand-forecasting models in Python and SQL across 2,400 SKUs and 6 "
    r"distribution centres, cutting forecast error from 22\% to 14\% and freeing an "
    r"estimated \pounds{}1.1M of safety stock"),
  "BH_FORECAST_SHORT": (
    {"forecasting", "python"}, 7,
    r"Built weekly demand forecasts across 2,400 SKUs, cutting forecast error from 22\% "
    r"to 14\%"),
  "BH_ROUTING": (
    {"modelling", "automation", "python", "commercial"}, 9,
    r"Designed a route-consolidation model for regional deliveries that removed 9\% of "
    r"weekly van miles, adopted by the transport planning team across the North West"),
  "BH_PIPE": (
    {"pipeline", "sql", "quality", "automation", "reliability"}, 8,
    r"Rebuilt the warehouse-management data feed as scheduled dbt models with data-quality "
    r"tests, ending a daily two-hour manual reconciliation"),
  "BH_REPORT": (
    {"reporting", "bi", "stakeholder"}, 6,
    r"Owned the Power BI service-level reporting used by 30+ operations managers, "
    r"replacing eleven spreadsheets with one governed dataset"),
 },
 "Oakmere Foods": {
  "OF_WASTE": (
    {"modelling", "statistics", "sql", "commercial", "forecasting"}, 9,
    r"Modelled shelf-life and order patterns for chilled lines, informing order-quantity "
    r"changes that reduced write-offs by 18\% over two quarters"),
  "OF_SUPPLIER": (
    {"segmentation", "sql", "stakeholder", "reporting"}, 8,
    r"Segmented 140 suppliers by on-time-in-full performance and cost to serve, giving "
    r"procurement a ranked list for quarterly reviews"),
  "OF_AB": (
    {"experimentation", "statistics", "commercial"}, 7,
    r"Designed and evaluated a pilot of revised replenishment rules in 12 stores against "
    r"matched controls, which went chain-wide after a significant availability gain"),
  "OF_AUTOMATE": (
    {"automation", "python", "reporting"}, 6,
    r"Automated the weekly stock-cover report in Python, saving the planning team about "
    r"four hours a week"),
 },
 "Saltmarsh Analytics": {
  "SALT_FORECAST": (
    {"forecasting", "consulting", "delivery"}, 7,
    r"Delivered footfall forecasts for three retail clients as part of a graduate "
    r"consulting team, presenting results to client operations leads"),
  "SALT_DASH": (
    {"bi", "consulting", "reporting"}, 6,
    r"Built client-facing Tableau dashboards for a regional bus operator's punctuality "
    r"data"),
 },
}

# Bullets that say the same thing; never render two from one group.
CONFLICT_GROUPS = [
    {"BH_FORECAST", "BH_FORECAST_SHORT"},
]

# May appear, never first under an employer.
NON_LEAD = {"BH_REPORT", "OF_AUTOMATE", "SALT_DASH"}

ALIASES = {}
RENDER_ALIASES = {}
