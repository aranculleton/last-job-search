# /html-report - Generate Application Tracker Dashboard

Generate a self-contained HTML dashboard from `job_search_tracker.csv` and the application archives under `documents/applications/`. The output is a single `.html` file - no server, no dependencies - that can be opened directly in a browser.

## Step 0: Parse Arguments

- No argument → output to `reports/application-dashboard.html`
- A path argument (e.g. `/html-report ~/Desktop/report.html`) → use that path

Create `reports/` if it does not exist.

---

## Step 1: Collect Data

Read in parallel:

1. **`job_search_tracker.csv`** - the primary source. Parse every row into a record with fields:
   `date`, `company`, `sector`, `role`, `role_type`, `channel`, `status`, `contact_person`, `fit_rating`, `notes`, `cv_file`, `cover_letter_file`, `source`, `deadline`

   Rows a confirmation wrote (`tools/confirm.py`, `followups.py --close-quiet`) also carry `applied_on`, `confirmed_by` and `confirmed_at`, which join the end of the header the first time one is written; a row without them reads them as empty.
   Rows written before `deadline` existed have thirteen fields and no fourteenth value. Treat the missing field as empty - never drop the row, and never infer a deadline from its `date`.

2. **`documents/applications/*/outcome.md`** - for each resolved application, read the outcome file to get the exact interview stages reached (the checkboxes) and any notes. Merge this into the matching tracker row by company+role fuzzy match (lowercase, ignore punctuation). If an archive exists for a row but there is no match, attach it as extra context anyway.

Status normalisation - map tracker values to six canonical buckets before computing stats:
- `drafted` → **Drafted** (documents written by `/apply`, not yet submitted)
- `applied` → **Active** (resume submitted, no further signal)
- `interview` → **Interview**
- `offer` → **Offer**
- `hired` → **Hired**
- `rejected` / `no_response` / `no response` / `offer_declined` / `offer declined` / `withdrawn` → **Rejected/Closed**
- anything else → **Rejected/Closed**, and name the unrecognised value once in the status breakdown - matching is case-insensitive

   The bucket map tolerates the legacy space spellings on read so nothing written before
   the canonical forms were locked drops out of the stats; the **Tracker status vocabulary**
   in `/outcome` is the authoritative set.

---

## Step 2: Compute Summary Stats

From the normalised data compute:

**Drafted rows are excluded from every statistic below** - they were never submitted. Report the Drafted count on its own, and include it only in the status breakdown.

**So are hiring processes with no application** - rows whose `notes` say `process, no portal application` (a referral that led to a recruiter's call, registered by `tools/interview_pack.py process`). Nothing was submitted, so they are not applications sent and do not belong in the funnel or the rates; report them on their own ("Processes with no application: N"), with their stages, and in the status breakdown.

- **Total applications**
- **By status bucket:** count per bucket
- **By sector and by channel, as rates with their n:** run `python3 tools/what_works.py rates --by sector` and `python3 tools/what_works.py rates --by channel` (JSON). Each group is `reached` of `decided`: the applications with a result, counted the way `what_works.py brief search` counts them, so the dashboard and the brief never disagree. A count per channel ("12 portal, 3 referral") says nothing about which one works; a rate does, with the number it rests on beside it. A group with `enough` false (under `min_group` decided) is shown with its n and the words "too few to compare", never ranked against the others. Say once how many applications are `waiting` (sent, no answer yet): they are in no rate.
- **By year/season:** group by the day the application went, `applied_on`, and by `date` on a row without it (a row from before that column, or a draft); either may be a year like `2025` or a full date
- **Funnel rates:** what % progressed past resume screen (reached Interview or beyond). Compute stage-reached from history, not current status: an application counts as having reached a stage when its current status implies it **or** its merged `outcome.md` stage checkboxes (Step 1.2) show the stage was reached - a `rejected` row whose outcome file ticks an interview stage reached Interview, and a `hired` row reached every stage before Hired. Current status alone structurally undercounts every earlier stage: a finished search would read as though nobody ever interviewed.
- **Rejection rate:** true rejections (`rejected`, `no_response`) ÷ applications with a final outcome. `offer_declined` (the candidate turned the offer down - a success) and `withdrawn` (candidate-initiated) are not rejections and stay out of the numerator; Interview and Offer rows are still unresolved, so they stay out of the denominator along with Active. The Rejected/Closed status *bucket* still groups all closed rows for the doughnut - the rate just must not reuse the bucket blindly.

---

## Step 3: Generate the HTML

Write a single self-contained HTML file. All CSS is inline in a `<style>` block. All JS is inline in a `<script>` block. Draw the doughnut and bar charts as hand-generated inline SVG - no Chart.js, no CDN, no external dependencies of any kind. The report must render fully offline on every open.

**Escaping (required):** HTML-escape every CSV/outcome-file value (`&` `<` `>` `"` `'`) before interpolating it into the page - this includes table cells, `title` attributes on truncated notes, and any text placed inside SVG (`<text>` labels, chart tooltips). Notes and company names copied from job postings routinely contain these characters; unescaped, they break the layout or inject markup into a page the user opens routinely.

### Layout

```
┌────────────────────────────────────────────────────┐
│  🔍 Job Search Dashboard           Generated: DATE │
├──────┬──────┬──────┬──────┬──────┬──────┬──────────┤
│Sent  │Draft │Active│Inter-│Offer │Hired │Rejected/ │  ← stat cards
│  N   │  N   │  N   │view N│  N   │  N   │Closed  N │
├──────┴──────┴──────┴──────┴──────┴──────┴──────────┤
│  Status breakdown (doughnut)  │  By sector (bar)   │  ← charts row
├────────────────────────────────────────────────────┤
│  By channel (bar)  │  Funnel (horizontal bar)      │  ← charts row
├────────────────────────────────────────────────────┤
│  By year or season (bar)                           │  ← charts row
├────────────────────────────────────────────────────┤
│  Applications  [Status ▾] [Sector ▾] [🔍 ...]      │  ← table with filters
│  date │ company │ sector │ role │ status │ ...     │
│  ...                                               │
└────────────────────────────────────────────────────┘
```

### Design spec

- **Colour palette:** CSS custom properties. Status colours:
  - Drafted: `#64748b` (slate)
  - Active: `#3b82f6` (blue)
  - Interview: `#f59e0b` (amber)
  - Offer: `#8b5cf6` (purple)
  - Hired: `#22c55e` (green)
  - Rejected/Closed: `#ef4444` (red)
- **Font:** system-ui stack, no web fonts
- **Stat cards:** white background, subtle shadow, large bold number, label below, left border in status colour
- **Charts:** contained in a 2-column grid on wide screens, stacked on narrow
- **Table:**
  - Alternating row shading
  - Status column uses a coloured pill/badge
  - `source` column renders as a hyperlink if the value is a URL (starts with `http`)
  - Empty cells render as ` - `
  - Client-side filter: a text search input filters rows across company + role + sector; the status and sector dropdowns filter independently; all three combine (AND)
  - Rows are sorted newest-first by default (by `date` descending, then alphabetically by company)
- **Responsive:** usable at 900px+, not broken below that
- **Footer:** "Generated by Claude Code · last-job-search · {ISO date}"

### Charts (inline SVG)

1. **Status doughnut** - slices for each status bucket, colours from the palette above
2. **By sector bar** (horizontal) - the interview rate per sector from Step 2's `rates --by sector`, each bar labelled with its n (`3 of 11, 27%`), groups ordered by `decided`, most first; a group with `enough` false drawn in a muted colour and labelled "too few to compare"
3. **By channel bar** - the same, per channel, from `rates --by channel` (`/apply` writes `portal` for a posting from a job portal). Never a bare count: a bar's length is a rate, and its label carries the n
4. **Application funnel** (horizontal bar) - Applied → Interview → Offer → Hired, each bar = count reaching that stage, derived per Step 2's funnel rule (current status **plus** the merged `outcome.md` stage checkboxes), so a candidate who interviewed and was later rejected still counts in the Interview bar
5. **By year or season bar** - applications per group from Step 2's year/season grouping, oldest first

Build each chart as a hand-written `<svg>` element: compute bar lengths/doughnut arc angles from the stats in Step 2 and emit the `<rect>`/`<path>`/`<circle>` and `<text>` elements directly - no charting library, no `<canvas>`. Each `<svg>` has `role="img"` and an `aria-label` summarizing the chart (e.g. "Status breakdown: 3 Active, 2 Interview, 1 Offer"; "By channel: referral 3 of 5 reached interview, portal 2 of 21"). Wrap each in a `<div class="chart-card">` with an `<h3>` title above. Remember to escape any label/value text drawn into `<text>` nodes per the escaping rule above.

### Table: columns to include

`Date` · `Deadline` · `Company` · `Role` · `Sector` · `Channel` · `Status` · `Notes` (truncated to 80 chars with `title` tooltip for full text) · `Source` (link or ` - `)

Columns with only empty values across all rows may be omitted.

---

## Step 4: Write and Confirm

Write the complete HTML to the output path using the Write tool.

Then put it where they can open it, in this order:

1. **Where the chat has the Artifact tool**, publish the same file as a private artifact and give its link: an artifact is a page "published from your session to a private URL on claude.ai", opened in any browser and updated in place when the dashboard is made again ([artifacts](https://code.claude.com/docs/en/artifacts)), so it opens on a phone or a computer alike. It stays private unless they share it. A later `/html-report` finds it (the tool's own list of their artifacts) and updates it at the same address rather than making a second.
2. **Also send the file** with the session's file-sending tool (SendUserFile or its equivalent, `display: "attach"`), so they can keep it: in a cloud session the person has no browser pointed at this container, and a path is not something they can open. With neither tool (a chat on their computer with no file-sending tool), write its full path as plain text: the desktop app opens a path written in the chat when it is clicked.

Then present:

> **Dashboard:** <the artifact's link, or "sent above">, and kept at `<output path>`
>
> **Summary:**
> - Applications sent: N · drafted, not yet sent: N
> - Active: N · Interview: N · Hired: N · Rejected/Closed: N
> - Funnel: N% progressed past resume screen
>
> Re-run `/html-report` any time after adding new entries via `/apply` or `/outcome` to refresh the dashboard.

---

## Design Principles

- **Self-contained.** One file, fully offline - charts are inline SVG, no CDN or external requests of any kind.
- **Data-only.** This command reads and renders; it never writes to the tracker or archive.
- **Idempotent.** Re-running overwrites the previous report at the same path - no accumulation.
- **Graceful on sparse data.** With only a few rows (as now), charts render correctly for small N; the table is the primary value. Do not suppress charts just because N is small.
- **No fabrication.** Every number in the report comes directly from the CSV or outcome files. Do not infer or estimate missing fields.
