# The person this search is for: Morgan Ellis (example)

Fictional. The app's own tests run against this profile, and it shows the shape a
real `profile/CLAUDE.md` takes: the summary the root CLAUDE.md imports, and every
rule that is the person's rather than the app's. `01-candidate-profile.md`, beside
this file, is the source of truth for every fact below.

## Candidate Profile

### Identity
- **Name:** Morgan Ellis (they/them)
- **Location:** Manchester, UK. Hybrid in Greater Manchester, remote in the UK; Leeds,
  Liverpool and Sheffield considered.
- **Languages:** English (native).
- **Document language:** British English. The document is a **CV**, never a resume.
- **Right to work:** UK settled status (EU Settlement Scheme). No sponsorship required, now
  or in future. Not a British citizen.

### Professional Experience
- **Senior Operations Analyst** (Mar 2023 - Present), Brindle & Hart Logistics, Manchester
- **Supply Chain Data Analyst** (Sep 2020 - Feb 2023), Oakmere Foods, Leeds
- **Graduate Analyst** (Sep 2019 - Aug 2020), Saltmarsh Analytics, Manchester

### Technical Skills
- **Primary:** SQL, Python (pandas, statsmodels), demand forecasting, inventory analytics
- **Secondary:** dbt, Power BI, Tableau, Excel, Git

### Target Sectors
- Logistics and third-party logistics, grocery and retail supply chain, manufacturing.

### Deal-breakers
- Roles requiring relocation outside the North West of England, other than remote UK roles
- Roles requiring British nationality or a security clearance (settled status is neither)
- Roles requiring Welsh as a job condition
- Gambling and tobacco employers

## Profile statement templates
`/apply` drafts the CV summary from these, tailored per posting; every claim in them is in
`01-candidate-profile.md`.

**Demand planning and forecasting roles:**
> Operations analyst with seven years turning warehouse, transport and supplier data into forecasts that move stock. Built weekly demand-forecasting models in Python and SQL across 2,400 SKUs and six distribution centres at Brindle & Hart Logistics, cutting forecast error from 22% to 14% and freeing an estimated £1.1M of safety stock. `[Tailor: their product category and planning horizon.]`

**Transport planning and logistics network roles:**
> Operations analyst with direct transport-planning experience: a route-consolidation model that removed 9% of weekly van miles, the demand forecasts behind 2,400 SKUs, and the Power BI service-level reporting used by 30+ operations managers. `[Tailor: their network and the constraint they plan against.]`

## Document rules that are Morgan's
- British spelling throughout (`documents.spelling` is `british`); the document is a CV.
- Dates as "14 October 2026".

## This search's automation
- None set up. `profile/routines.json` is a placeholder.
