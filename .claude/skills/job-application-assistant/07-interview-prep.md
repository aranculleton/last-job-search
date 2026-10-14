---
framework_version: 1.1.2
---

# Interview Preparation Guide

<!-- SETUP: STAR examples are personalized by running /setup based on your actual experience -->

## STAR Format

Structure answers as: **Situation** (context), **Task** (your responsibility), **Action** (what you did), **Result** (outcome).

Keep answers to 1-2 minutes. Be specific. End with what you learned or would do differently.

## Ready-Made STAR Examples

<!-- Worked examples for Morgan Ellis, the fictional example person in profile.example/;
/setup replaces them with the candidate's own, drawn from the resume. In a real set every
number appears on the resume; do not inflate any of them in the room. Where an interviewer
pushes for detail the resume does not carry, say what you actually remember and flag the rest
as approximate. -->

### 1. The forecast that freed safety stock (applied modelling)
**S:** Weekly demand forecasts for 2,400 SKUs across six distribution centres ran at a 22% error, and planners were covering the gap with extra safety stock.
**T:** Own a weekly forecast the planners would trust, from the raw warehouse data to the number they order against.
**A:** Rebuilt the forecasting models in Python and SQL with promotions and seasonality as explicit features, and tracked error by distribution centre so the planners could see where the number held.
**R:** Forecast error down from 22% to 14%, and an estimated £1.1M of safety stock released.
**Use for:** "Walk me through an end-to-end project", "How do you validate a forecast", "Tell me about a model you built", "How do you make a model actually get used"

### 2. Ending a daily manual reconciliation (initiative and automation)
**S:** Every morning someone spent two hours reconciling the warehouse-management data feed against the reports that depended on it, and nobody owned fixing it.
**T:** Remove the manual step rather than keep absorbing it.
**A:** Rebuilt the feed as scheduled dbt models with data-quality tests, so a bad load failed loudly instead of surfacing in a report.
**R:** The daily two-hour reconciliation ended.
**Use for:** "Tell me about a time you took initiative", "How do you improve a process", "Give an example of building something reusable", "How do you test data pipelines"

### 3. The route-consolidation model (commercial impact)
**S:** Regional deliveries were planned route by route, and vans were leaving partly empty.
**T:** Build a model the transport planning team would actually use, not one that only looked good in a deck.
**A:** Designed a route-consolidation model for regional deliveries, walked the planners through how it chose each consolidation, and adjusted its constraints to match how the depots really loaded vans.
**R:** 9% of weekly van miles removed, and the model adopted by the transport planning team across the North West.
**Use for:** "Tell me about commercial impact", "Describe presenting technical work to a non-technical audience", "How do you get a team to adopt your work", "Tell me about a model that changed an operational decision"

### 4. The replenishment-rules pilot (evidence before rollout)
**S:** Oakmere Foods had revised replenishment rules that planners were confident in, with no evidence yet that they improved availability.
**T:** Show whether the rules worked before they went chain-wide.
**A:** Designed a pilot in 12 stores against matched control stores, fixed the availability measure before the pilot started, and evaluated the result with the uncertainty stated.
**R:** A significant availability gain, and the rules went chain-wide.
**Use for:** "Tell me about a decision you backed with data", "How do you test something you cannot fully randomize", "Describe influencing without authority", "How do you handle a result people did not expect"

### 5. Replacing eleven spreadsheets with one dataset (stakeholders and trust)
**S:** Thirty-plus operations managers were working from eleven different spreadsheets for service levels, and the numbers disagreed.
**T:** Give them one definition of service level and one place to read it.
**A:** Built a governed dataset and the Power BI reporting on top of it, agreed the definitions with the managers one by one, and retired the spreadsheets as each team moved over.
**R:** One service-level view used by 30+ operations managers, in place of eleven spreadsheets.
**Use for:** "Tell me about managing stakeholders", "How do you handle conflicting numbers", "Describe getting people off a tool they like", "What does a single source of truth mean to you"

### 6. Chilled-line write-offs (statistical modelling for a commercial result)
**S:** Chilled lines were losing stock to expiry, and ordering rules took no account of shelf life.
**T:** Understand how shelf life and order patterns interacted, and turn it into a change the buyers could make.
**A:** Modelled shelf-life and order patterns for the chilled lines and gave the buyers specific order-quantity changes rather than a general finding.
**R:** Write-offs fell 18% over two quarters.
**Use for:** "Tell me about a time analysis changed a business result", "How do you turn a finding into an action", "Describe working with commercial teams", "Give an example of a measurable outcome"

<!-- Add more STAR examples as needed. Aim for 4-6 covering different competencies. -->

## Common Tough Questions

### "Why are you leaving Brindle & Hart Logistics?" / "Why are you looking?"
> I am not unhappy - the role has given me ownership of the forecasts from the warehouse data feed through to what the planners order. The move is about scope. I have taken demand forecasting about as far as one distribution network allows, and I want a larger or more varied planning problem, with a team that plans over a longer horizon than the week. `[CONFIRM: check this matches your actual reason before using it.]`

### "Do you have the right to work here, and will you need sponsorship?"
> Answer both plainly, exactly as the work-authorization facts in `profile/01-candidate-profile.md` record them. Where the profile says no sponsorship is required, the second is a plain no, with no caveat. `[PLACEHOLDER: only if the candidate's status has an expiry date, add the expiry answer here: state the date plainly and say what the plan is, because evasiveness reads worse than the status itself. Delete this note otherwise.]` `[CONFIRM: check the facts against the profile before any interview.]`

### "Walk me through your career - why these moves?"
> Each role took on more of the chain than the last: a graduate year forecasting footfall for retail clients at Saltmarsh Analytics, then in-house at Oakmere Foods owning the measurement on stock and suppliers, then Brindle & Hart Logistics owning the forecasts and the data feed behind them. What I am looking for now is a larger planning problem to own. Say it in one breath and move on.

### "What were you doing between [date] and [date]?" (use only if the profile has a gap)
> `[PLACEHOLDER: two sentences stating what the period actually contained, drawn from 01-candidate-profile.md. Delete this question if there is no gap.]`
>
> **Delivery notes.** Say it in two sentences and stop; a gap sounds like a problem only if you narrate it like one. Land the strongest true fact plainly and do not oversell it. Mention a minor job only if asked what it was, and never put it on the resume or claim it as professional experience. If pressed, be matter-of-fact.

### "You don't have [specific skill/experience]."
> Name the gap plainly, then bridge to the nearest real thing and say what you are doing about it. Worked examples: no SAP configuration, but I have reported from SAP extracts and the warehouse-management system behind them. No Airflow, but I have run scheduled dbt models with data-quality tests in production. No people management, but I have owned reporting used by 30+ operations managers and moved them off eleven spreadsheets. No experience in your specific sector, but I changed sector between each of my roles, and each time I learned the commercial mechanics fast enough to be useful in the first month. Never claim the skill.

### "Where do you see yourself in 5 years?"
> Leading the planning analytics for a network end to end - the forecasts, the data feeds behind them and the relationship with the planners who act on the output - with a small team around it. I would rather go deep on planning than broad across many analytics topics.

### "What's your biggest weakness?"
> I tend to polish a forecast before showing it to the people who will use it, which delays the feedback that would have improved it. At Brindle & Hart I now share a rough weekly version early and agree the error measure with the planners before I tune anything. It costs a little pride at the start and saves rework later, but I still have to push myself to show work early. `[CONFIRM: check this matches your actual experience before using it.]`

### "Why this company specifically?"
> Customize per company. Must reference: specific projects, company values, market position, or team structure. Never give a generic answer.

## Questions You Should Ask Interviewers

### About the Role
- "What does a typical week look like in this role?"
- "What would success look like in the first 6 months?"
- "What's the biggest challenge the team is facing right now?"

### About the Team
- "How big is the team, and how do you divide work?"
- "What does the development/project lifecycle look like, from idea to production?"
- "How do you onboard new team members?"

### About Tech & Growth
- "What's your current tech stack for [relevant area]?"
- "Is there room to grow into more architectural or strategic decisions?"
- "How does the team stay current with new tools and methods?"

### About Culture (use these to prevent disappointment)
- "How would you describe the team culture?"
- "What does professional development look like here?"
- "Is there flexibility for remote/hybrid work?"
- "What's the balance between development/new projects and maintenance work?"
- "How would you describe the leadership style in this team?"
- "What do people who thrive here have in common?"

## Phone/Video Interview Tips
- Have STAR examples written out (use this file)
- Keep a glass of water nearby
- Smile when speaking (it changes your tone)
- Ask for clarification if a question is vague
- It's OK to take 5 seconds to think before answering
- End with: "Is there anything else you'd like to know about my background?"

## After the Application (Best Practice)

### Follow-Up Etiquette
- **Don't call to "stand out"** or to learn more about the role post-submission - this risks a negative impression
- If the employer specified a timeline, respect it and wait
- If no timeline was given and significant time has passed (2+ weeks), a brief call to ask about status is acceptable
- If you have genuinely new, relevant information to share, a short follow-up is fine

### Thank-You Notes
- When you receive any update (interview invitation, rejection, or status update), send a brief thank-you message
- Express appreciation for their time and the process
- Keep it short (2-3 sentences)

## Roleplay Guidelines
When the user asks for interview practice:
1. Ask which role/company to simulate
2. Start with easy warm-up questions ("Tell me about yourself")
3. Progress to role-specific technical questions
4. Include 1-2 behavioral questions using the competencies from the job posting
5. End with a tough question or curveball
6. After each answer, give brief feedback: what worked, what to sharpen
7. Suggest which STAR example would work best for each question
