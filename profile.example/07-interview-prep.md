# Interview preparation: Morgan Ellis (example)

Fictional. A real profile keeps the person's own STAR stories and hard-question
answers here; the app's `07-interview-prep.md` holds the method. Every number below is
in `01-candidate-profile.md`. Each story ends on a `Use for:` line, the questions it
answers, which is how `/interview` matches a story to a likely question.

## STAR: the forecast that freed safety stock
- **Situation:** forecast error at 22% across 2,400 SKUs and six distribution centres, and planners covering the gap with extra safety stock.
- **Task:** a weekly demand forecast the planners would trust.
- **Action:** rebuilt it in Python and SQL with promotions and seasonality as features, and tracked error by distribution centre so the planners could see where it held.
- **Result:** error down to 14%, about £1.1M of safety stock released.
- **Use for:** "Walk me through a project end to end", "Tell me about a model you built", "How do you validate a forecast", "Tell me about your biggest impact"

## STAR: ending a daily reconciliation
- **Situation:** every morning someone spent two hours reconciling the warehouse-management data feed against the reports built on it.
- **Task:** remove the manual step rather than keep absorbing it.
- **Action:** rebuilt the feed as dbt models with data-quality tests, so a bad load failed loudly instead of surfacing in a report.
- **Result:** the daily two-hour reconciliation ended.
- **Use for:** "Tell me about a time you took initiative", "How do you improve a process", "How do you test data pipelines", "Tell me about data quality"

## STAR: one report in place of eleven spreadsheets
- **Situation:** 30+ operations managers read service levels from eleven spreadsheets, and the numbers disagreed.
- **Task:** one definition of service level and one place to read it.
- **Action:** built the Power BI service-level reporting, agreed the definitions with the managers, and retired the spreadsheets as each team moved over.
- **Result:** one report used by 30+ operations managers, in place of eleven spreadsheets.
- **Use for:** "Tell me about managing stakeholders", "How do you handle conflicting numbers", "Tell me about getting people to adopt your work", "Tell me about reporting and dashboards"

## STAR: chilled-line write-offs
- **Situation:** at Oakmere Foods, chilled lines were losing stock to expiry, and ordering took no account of shelf life.
- **Task:** turn how shelf life and order patterns interact into a change the buyers could make.
- **Action:** modelled shelf-life and order patterns for the chilled lines and gave the buyers specific order changes rather than a general finding.
- **Result:** write-offs fell 18% over two quarters.
- **Use for:** "Tell me about a time analysis changed a business result", "How do you turn a finding into an action", "Tell me about working with commercial teams"

## Hard questions

### "Why are you looking?"
> The move is about scope. I have taken demand forecasting about as far as one distribution network allows at Brindle & Hart Logistics, and I want a larger planning problem to own.

### "Do you need sponsorship?"
> No. I have settled status in the UK, so I need no sponsorship, now or later.

### "What is your notice period?"
> One month.
