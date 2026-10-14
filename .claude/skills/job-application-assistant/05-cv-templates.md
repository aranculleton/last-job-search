---
framework_version: 2.1.4
---

# Resume Templates and Tailoring Guide

<!-- SETUP: Profile statements and section ordering are personalized by running /setup -->

## Template: LaTeX moderncv (Banking Style)

All resumes use the moderncv LaTeX package with the "banking" style and "blue" color scheme.

**Output file:** `cv/<Prefix>_Resume_<ABBR>.tex`, where `<Prefix>` is `identity.file_prefix` in `profile/person.json`
**Compile with:** **lualatex** on MiKTeX/TeX Live. pdflatex often fails on modern MiKTeX installs with `fontawesome5` font-expansion errors; lualatex handles the same sources cleanly.
**Fact source:** the Source of Truth chain in `profile/01-candidate-profile.md` - the current
resume it names (under `documents/cv/`) first, then `profile/01-candidate-profile.md`,
then the Candidate Profile section of `profile/CLAUDE.md`. **Never `cv/main_example.tex`**: it is an
unpopulated upstream template whose bullets are `[YOUR_NAME]`-style placeholders, and reading it
contributes no facts. Previously generated `cv/<Prefix>_Resume_<ABBR>.tex` files may be read
for structure and phrasing, never as a source of claims.

## File naming (applies to every generated document)

Files are named the way a person names them, because the employer sees the filename on the
attachment. Never emit a machine-shaped name like
`main_harbour_freight_sr_demand_planning_analyst.tex`.

| Document | Pattern | Example |
|---|---|---|
| Resume | `<Prefix>_Resume_<Name>.tex` / `.pdf` | `<Prefix>_Resume_HarbourFreight.pdf` |
| Cover letter | `<Prefix>_Cover_Letter_<Name>.tex` / `.pdf` | `<Prefix>_Cover_Letter_HarbourFreight.pdf` |

**`<Name>` is not chosen by hand. `tools/doc_name.py` derives it**, and
`render_application.py` calls it, so a draft that supplies its own `abbr` only gets it if it
matches. Run `python3 tools/doc_name.py "<company>"` to see what a company resolves to.

The rule it implements: **a company writes its own name, and the filename uses it.**
`HarbourLink` keeps its capital L, `HxL` its lower-case x, `Brightwave` stays a word. A long
name is shortened on a word boundary after dropping trailing legal and generic words (`Inc`,
`Ltd`, `Group`, `Holdings`, `Software`, and the country names the profile adds):
`Harbour Freight Shipping Company` becomes `HarbourFreight`, `Quayside Holdings` becomes
`Quayside`.

The one override is `doc_name.KNOWN`, which is `ABBREVIATIONS` in `profile/employers.py`: an
abbreviation people genuinely say out loud (`FHB` for First Harbour Bank), or a company that
styles itself in capitals (`ACME`). Add to that table rather than
hand-naming a file.

**This used to ask for a 2-to-4 character UPPERCASE abbreviation, and that was wrong.** It is
right for a company that writes itself that way and wrong for every company that does not.
Applied to the rest it produces `<Prefix>_Resume_HARBOURFREIGHT.pdf` and `_QUAYSIDE.pdf`: not
abbreviations, just the company name shouted. A shouted name looks machine-generated, which is
the one thing a filename on an attachment must never do. `doc_name.is_shouty()` is the check, and
`tests/test_document_filenames.py` fails any unsent document still doing it.

**A document already sent keeps the name the employer received.** Renaming it would decouple
the record from what is in their ATS. Only unsent drafts are renamed.

Only when applying to two different roles at the same company, append a short role token in
PascalCase: `doc_name.suffix("Acme Bank", "ModelRisk")` gives `AcmeBank_ModelRisk`. Never put the
requisition number, the date, the role slug, or the word "tailored" in the filename.

**Collision check.** Before writing, glob `cv/<Prefix>_Resume_*` for the abbreviation. If
it is already taken by a *different* employer, extend to three or four characters until it is
unique (`Harbour Freight` and `Harlow Bank` both start `HA`, so `HARB` and `HARL`), and note the
collision in the report so the user is not confused by two similar names.

## Length - one page is the default

**The resume is one page.** At a few years of post-graduation experience a one-page
resume is the norm in many markets, and a
two-page resume invites the reader to wonder what is padding it. One page also forces the
per-posting selection this guide asks for.

**The two-page exception** exists and is narrow. Go to two pages only when *all three* hold:
the posting is senior or heavily technical, the extra page is filled with material that
speaks directly to the posting's stated requirements, and cutting to one page would drop a
stated requirement. When it is invoked, say so in the report and name what earned the second
page. Two pages that end a third of the way down page 2 is a failure, not an exception:
either it fits on one page or the second page is genuinely full.

## Selection, not accumulation

`profile/01-candidate-profile.md` deliberately holds far more than any one resume should show: an
"Additional detail available for tailoring" block under most roles, a Reserve Experience
section, and a skills list wider than one page can carry.

**Choose per posting. Never paste the profile wholesale.**

- Read the posting's requirements first, then pick the bullets that answer them. A bullet
  that hits a named requirement outranks a bullet that is merely impressive.
- The default bullets under each role are a starting point, not a fixed set. Swapping in an
  "Additional detail" bullet because it matches the posting better is the intended use.
- Skills sections are assembled per posting from what the posting asks for and the
  experience bullets already evidence. A tool the candidate has genuinely used but that the
  posting never mentions is usually the right cut on a one-page resume.
- Reserve Experience (a minor, off-theme role, for example) stays off unless the posting makes it
  load-bearing. When you include one, say why in the report.

## The resume never states a gap

No "not yet in my toolkit", no "would be learning", no hedged competency label, no
parenthetical apology. See rule 8 in `03-writing-style.md`. A skill the candidate lacks is
absent from the resume, and that absence is the whole of the honest signal. Concessions, if
any, live in the cover letter and are capped at one sentence there.

### Compile command

```bash
export TEXMFHOME="$PWD/texmf"   # vendored icon fonts, texmf/README.md
cd cv && lualatex -interaction=nonstopmode <Prefix>_Resume_<ABBR>.tex
```

Expected output: `Output written on <Prefix>_Resume_<ABBR>.pdf (1 page, ...)`. Any page count other than 1 is a failure that must be fixed before presenting to the user, unless the two-page exception below has been explicitly invoked.

## Document Structure

```latex
\documentclass[11pt,a4paper,sans]{moderncv}
\moderncvstyle{banking}
\moderncvcolor{blue}

% Force the name and section headings to render in moderncv blue (color1).
% Default banking leaves them black: moderncvstylebanking.sty's \colorlet
% copies (not aliases) the pre-scheme accent colour, so the name colours are
% frozen before \moderncvcolor runs. Re-let them after. \namefont is the hook
% every name-style macro routes through, so this also works on moderncv 2.3.1
% (Debian/Ubuntu apt), which has no \firstnamestyle/\lastnamestyle at all.
\renewcommand*{\namefont}{\fontsize{34}{36}\bfseries\upshape}
\colorlet{firstnamecolor}{color1}
\colorlet{lastnamecolor}{color1}
\colorlet{namecolor}{color1}
\renewcommand*{\sectionstyle}[1]{{\sectionfont\color{color1}#1}}

\usepackage[utf8]{inputenc}
% moderncv loads hyperref itself in an \AtEndPreamble hook, so \hypersetup
% must go in an \AtEndPreamble of our own: on moderncv < 2.4 a top-level
% \usepackage{hyperref} clashes with the class's own
% \RequirePackage[unicode]{hyperref}. From 2.4.0 the class passes its options
% through \PassOptionsToPackage instead, which is what removes that clash.
\AtEndPreamble{\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,
    urlcolor=blue,
    pdftitle={Morgan Ellis - CV},
    % Keep pdfpagemode=UseNone: this block runs after moderncv's own
    % \AtEndPreamble (moderncv.cls sets pdfpagemode there), so a FullScreen
    % value here would win and open every resume in fullscreen presentation mode.
    pdfpagemode=UseNone,
}}
\usepackage[scale=0.77]{geometry}
\usepackage{import}

% Personal data
\name{Morgan}{Ellis}
% If you have no address to list, DELETE this whole line. \address{}{}{} fails
% with "There's no line here to end" on every moderncv version.
\address{Manchester}{}{}
\phone[mobile]{+44 7700 900123}
\email{morgan.ellis@example.com}
\extrainfo{\href{https://www.linkedin.com/in/morgan-ellis-example}{LinkedIn}}

\begin{document}
\makecvtitle

% 1. Summary: 40-48 words, three lines, identity first ("Operations analyst with...")
% 2. Professional Experience: reverse-chronological, 12-14 bullets, allocated
%    per posting by tools/allocate.py (tenure x recency x relevance)
% 3. Skills: three labelled lines
% 4. Education: one line
% 5. Certifications: one line, separate section
% This order never changes. It moved three times across delivered batches
% and the reader should never have to hunt for a section.

\end{document}
```

### Color overrides

The `\renewcommand*` on `\namefont` and the three `\colorlet` lines in the preamble are required on lualatex+MiKTeX. Without them the name and section headings render in black even though `\moderncvcolor{blue}` is set, which looks inconsistent with the rest of the blue accent scheme (links, bullet markers, contact icons). The cause: `moderncvstylebanking.sty` defines the name colours with `\colorlet`, which *copies* the accent colour as it is before the scheme is applied, so the name colours are frozen to the pre-scheme value; re-assigning them with `\colorlet` after `\moderncvcolor{blue}` (as the preamble does) re-pins them to `color1`. `\namefont` is the shared hook every name-style macro routes through, so the block is version-agnostic - including moderncv 2.3.1 from Debian/Ubuntu apt, which has no `\firstnamestyle`/`\lastnamestyle` at all. Both names render bold; if you prefer regular weight, change `\bfseries` to `\mdseries` in the `\namefont` line (the weight now lives there, so it applies to the whole name). Don't drop the overrides - on most modern installs the defaults render visibly wrong.

### Spacing inside itemize lists (important)

**Do not place `\vspace{...}` between `\item` entries in an `itemize` list.** Even though the source looks symmetric, this pattern occasionally produces a noticeably oversized gap before a single item: the inter-item `\vspace` creates a paragraph break that interacts unpredictably with the list's internal `\itemsep`, so LaTeX renders one of the gaps wider than the rest. Remove the inter-item `\vspace` and let `itemize` use its native uniform spacing.

```latex
% WRONG - intermittently produces an oversized gap before one bullet
\begin{itemize}
\item \textbf{Foo}: ...
\vspace{1pt}
\item \textbf{Bar}: ...
\vspace{1pt}
\item \textbf{Baz}: ...
\end{itemize}

% RIGHT - uniform spacing using the list's native itemsep
\begin{itemize}
\item \textbf{Foo}: ...
\item \textbf{Bar}: ...
\item \textbf{Baz}: ...
\end{itemize}
```

Two related patterns are fine and should be kept:
- `\vspace{1pt}` immediately after `\section{...}` (between section heading and first item) - this is between the heading and the list, not between list items.
- `\vspace{3pt}` between top-level `\cventry` blocks in Professional Experience or Education - this gives breathing room between roles and renders consistently.

### Section headings must match the resume's language (important)

Section headings such as `\section{Core Competencies}`, `Professional Experience`, `Education`, `Languages`, `Publications`, `Honors and Awards`, `References` (and any others your template defines), plus the `Available upon request.` line under References, are all **literal English text baked into the template** - they do not translate themselves. Whenever the document language (see `Document language` in the candidate profile) is not English, translate every one of these too, whatever they are, not just the body prose - a resume with a fully localized profile statement and bullets sitting under untouched English section headers reads as sloppy and inconsistent, and it's an easy thing to forget precisely because the prose translation is the obvious, visible part of the job. Worked example for Spanish: `Competencias Clave`, `Experiencia Profesional`, `Educaci\'on`, `Idiomas`, `Publicaciones`, `Distinciones y Premios`, `Referencias`, `Disponibles a solicitud.` The same rule applies for any other target language - check this explicitly during the verification pass.

## Section-by-Section Tailoring

### Profile Statement / Elevator Pitch (Best Practice)
This is the most important section to customize. It appears right after `\makecvtitle`.

Write 5-7 lines that function as an "elevator pitch": a concise, compelling introduction explaining why you're qualified for *this specific role*. Focus on what the employer gains from hiring you.

When the role sits outside your home domain, **lead with the domain-transfer argument** - the one or two sentences connecting your background to their problem (e.g. wave physics to radar signal processing) belong in the profile statement's opening, not buried in the cover letter. It is the strongest card a domain-changer holds; play it first.

**Create 2-3 profile statement templates for your main role types:**

<!-- SETUP: These are populated based on your background -->
**For Demand Planning / Forecasting roles:**
> Operations analyst with seven years turning warehouse, transport and supplier data into forecasts that move stock. Built weekly demand-forecasting models in Python and SQL across 2,400 SKUs and six distribution centres at Brindle & Hart Logistics, cutting forecast error from 22% to 14% and freeing an estimated £1.1M of safety stock. Comfortable owning the whole path from raw warehouse feeds to the planners who act on the number. `[Tailor: name their product category and the planning horizon the posting asks for.]`

**For Analytics Engineer / Data Engineer roles:**
> Analytics engineer with seven years turning warehouse and supplier data into tested, trustworthy tables. Rebuilt the warehouse-management data feed at Brindle & Hart Logistics as scheduled dbt models with data-quality tests, ending a daily two-hour manual reconciliation, and automated the weekly stock-cover report at Oakmere Foods. Reports in Power BI for 30+ operations managers. `[Tailor: match their stack - dbt, Snowflake, Airflow - and name it explicitly.]`

**For Commercial / Experimentation Analyst roles:**
> Analyst with seven years running pilots and statistical analysis on operational decisions, including a replenishment-rules pilot across 12 stores against matched controls and a chilled-line shelf-life model that cut write-offs by 18% over two quarters, both at Oakmere Foods. Pairs the test design with the data work that makes the measurement trustworthy. `[Tailor: lead with their operational lever and the metric they care about.]`

**For Transport Planning / Logistics Network roles:**
> Operations analyst with direct transport-planning experience: a route-consolidation model that removed 9% of weekly van miles, the demand forecasts behind 2,400 SKUs, and the Power BI service-level reporting used by 30+ operations managers. A mathematics graduate who builds the model and the reporting that carries it to the planners. `[Tailor: name their network and the constraint they plan against.]`

Statements labeled *[Used for: <company>_<role>]* were extracted from archived application drafts by `/setup` Path A. They are **phrasing references, never fact sources**: when drafting from one, every factual claim still comes from `profile/01-candidate-profile.md` - a past tailored draft does not vouch for its own accuracy.

### Skills section (generator-enforced)

**There is no Core Competencies block.** It was a second summary that restated the
experience bullets four lines below it, and on a one-page resume it cost an employer block two
of its four bullets. The reader has the summary for positioning and the bullets for evidence.

**Section order is fixed: Summary, Professional Experience, Skills, Education,
Certifications.** That is the convention for a candidate with a few years' experience: the
reader takes the summary and goes straight to what they did; the skills block is a keyword
pass for the ATS and a stack check for the recruiter, and both read the whole page.
Skills-first is a career-changer layout. The order is enforced by a test and never moves.

The **Skills** section is three labelled lines, left aligned, comma separated, no parentheses: `Languages and modelling`, `Data engineering and
cloud`, `BI, tooling and delivery`. `tools/skills_block.py` builds it from the tailor's
selections against a fixed inventory and tops it up from what the page already claims.
The profile's pinned item (`PINNED` in `profile/skills.py`) always prints. Nothing is invented.

Use the posting's own term where it truthfully applies: ATS and skim readers match
literally, and "risk and account scoring" beside a posting that says "risk scoring" does
more than a paraphrase.

### Education
- Always include your highest degrees
- For senior roles, keep education brief (dates and titles only)
- Include thesis topics when relevant to the target role

#### In-progress qualifications must say so explicitly

**A bare year range is not enough.** An entry reading `2025–2026`, seen partway through 2026, looks like a *finished* degree, because a reader skimming a resume treats a closed range as closed. A profile statement that says "currently completing…" does not fix it: the education entry is where a reader checks the credential, so it has to stand on its own.

State completion inside the entry itself:

```latex
\item{\cventry{2025--2026}{[Degree], [Field]}{[Institution]}{[Location]}{}{\vspace{1pt}
In progress, expected [Month Year]. [Relevant topics]
}}
```

Any consistent form works: `In progress, expected <Month Year>.` / `Expected completion <Month Year>.` / a date field of `2025–present`.

Claiming a credential not yet held is a factual misstatement, and it is the kind discovered at transcript or reference check rather than at interview. It costs nothing to prevent. The same applies to in-progress certifications and courses.

**Check for agreement:** for a current student, the profile statement, the education entry, and any availability or right-to-work note must all give the same completion date. Contradiction between them is worse than any single version.

### Professional Experience
- Rewrite bullet points to emphasize aspects most relevant to the target role
- Use 4-6 bullets for most recent role, 3-4 for previous, 2-3 for older
- **Emphasize measurable results** where possible: "Reduced processing time by X%", "Model adopted by the team"

#### Check tenure against visible output

Before finalizing, look at each role the way a stranger will: **date span versus how much work is shown.** A two-year role represented by a single project reads as low output, whether or not that is fair. The reader cannot know what filled the time, so they guess, and the guess is unflattering.

This bites hardest on **career changers** (part of the tenure went into learning the new field), on **long-cycle work** (industrial deployment, clinical or regulatory projects, research - one delivery genuinely takes quarters), and on anyone whose employer kept them on a single account or product.

Three honest fixes, in order of preference:

1. **Surface more real work.** Ask what else the period contained. There are often real secondary projects, internal tooling, or support work that never reached the resume because it felt minor. Best fix when the material exists.
2. **Make the phases within the role explicit.** If the span genuinely had stages, say so - an initial period learning the domain or supporting the team, then ownership of the named work through to delivery. A phased arc reads as a growth curve; an undifferentiated multi-year block reads as stagnation.
3. **Name what made the cycle long.** Data collection from a live environment, validation with domain experts, deployment and iteration against real output. Reviewers who know the domain accept this immediately.

**Never** pad with invented projects, and **never** quietly shorten the employment dates so the ratio looks better. Both are discoverable, and both are worse than the perception problem being solved.

**Prepare the interview answer too.** If a long span against little visible output survives these fixes, the question is coming. The candidate needs a ready two-part answer - what actually filled the time, and what the outcome was - recorded in their interview prep rather than improvised in the room.

### Handling Employment Gaps (Best Practice)
If there is a gap in your employment history:
- The gap should be explained matter-of-factly if needed
- Describe how professional development continued during the gap
- Frame as deliberate skill-building and career repositioning

### Publications
- Include Google Scholar link if applicable
- Select 3-4 most relevant publications (not always all of them)
- For non-academic roles, keep brief

### Evidence Links
Wherever the resume names a verifiable artifact - a public project, a hackathon entry, a publication - carry its link (`\href`) so a reader can verify the claim in one click. A resume whose strongest claims are checkable reads as more credible everywhere else too.

### Honors and Awards
- Keep format brief, one line each

### References
- List 2-4 references with name, title, company, and contact
- End with: "More references are available upon request."
- **Do not attach reference letters** - employers typically contact references directly

### LaTeX Special Characters (important)

Postings and profile data arrive as plain text; the resume is LaTeX. Escape these wherever they land in body text - company names, achievement bullets, skill lists:

| Character | Write | Typical trigger |
|---|---|---|
| `&` | `\&` | company names: Bang \& Olufsen, Brüel \& Kjær, H\&M |
| `%` | `\%` | quantified achievements: "cut latency by 40\%" |
| `$` | `\$` | salary and cost figures |
| `#` | `\#` | "ranked \#1", C\# |
| `_` | `\_` | file names, code identifiers |
| `~` | `\textasciitilde{}` | URLs, "approx. 5 years" tildes |
| `^` | `\textasciicircum{}` | version strings, math |

Two failure modes deserve special care:

- **`%` fails silently.** An unescaped `%` starts a LaTeX comment: the compile succeeds with zero errors, and everything after the `%` on that line vanishes from the PDF. `Cut inference latency by 40% and saved DKK 2M annually` renders as "Cut inference latency by 40" - the bullet keeps its impressive-looking fragment and loses the actual result. Quantified achievement bullets are exactly where the guidance steers you ("use numbers where possible"), so check every `%` in every bullet before compiling.
- **`&` fails loudly** inside `\cventry` (alignment-tab errors, `Missing } inserted`). The compile loop catches it, but escape employer names up front rather than debugging the compile.

Related trap: a bullet whose text begins with a literal `[` must be braced - `\item {[text]}` - or LaTeX parses the bracketed text as `\item`'s optional label and renders it clipped off the left page edge with a clean compile. The example resume's placeholder bullets are braced for exactly this reason.

## Compile-and-Inspect Loop (MANDATORY)

After writing the resume and before presenting to the user, always compile and visually inspect the PDF. Iterate until the layout is clean. Workflow:

1. Run `lualatex -interaction=nonstopmode <Prefix>_Resume_<ABBR>.tex` with `TEXMFHOME` set to the repo's `texmf/` (see `texmf/README.md`)
2. Check the output page count: must be exactly 1 (or exactly 2 where the exception is invoked)
3. Read the PDF via the Read tool and visually inspect both pages
4. Check for **orphaned entries**: a `\cventry` title line must never sit alone at the bottom of page 1 with its bullets on page 2

### Fixing common page-break problems

**Problem: entry title on page 1, bullets orphaned to page 2**
Add `\needspace{5\baselineskip}` immediately before the problematic `\cventry`:
```latex
\needspace{5\baselineskip}
\item{\cventry{YEAR--YEAR}{Role Title}{Organization}{Location}{}{...}}
```
Include `\usepackage{needspace}` in the preamble.

**Caveat - use `\needspace` before entries, never before `\section` headings.** A section-level `\needspace` pushes the entire section (heading plus content) to the next page whenever the request does not fit, stranding empty space above and typically *adding* a page instead of saving one. Apply it only to the individual `\cventry` that actually orphans, and only after a compile shows the orphan.

**Problem: one trailing section spills onto a second page (e.g., References alone)**
Add `\enlargethispage{2-3\baselineskip}` before a late section to stretch the page by a few lines. This is the standard LaTeX rescue for near-miss overflows. If it does not close the gap, cut instead.

**Problem: real content on a second page you did not intend**
Cut content, do not compress geometry or `\vspace`. See "Relevance-weighted cutting" below. On a one-page resume the usual culprits are a skills list that was pasted rather than selected, a fourth role that the posting does not need, or a profile statement running past four lines.

**Problem: the page finishes early and feels thin**
Restore the highest-relevance item previously cut, or promote an "Additional detail available for tailoring" bullet from `profile/01-candidate-profile.md` that hits a posting requirement. Do not pad with generic tooling.

## Layout rules the generator enforces (do not hand-edit around these)

`tools/render_application.py` and `templates/resume_gen.py` enforce the following.
They exist because each one shipped as a defect first.

**Experience is reverse-chronological, always.** Brindle & Hart Logistics, Oakmere Foods,
Saltmarsh Analytics. The renderer sorts by `CHRONO` regardless of the order the tailor wrote,
so a relevance-ordered draft cannot reach the page. Tailoring lives in the summary,
the competencies, and bullet selection.

**Bullets that say the same thing never both render.** `CONFLICTS` in the renderer
holds the redundant pairs: `BH_FORECAST` and `BH_FORECAST_SHORT` state the same result at two
lengths, and a resume that carried both would print the same 22% to 14% forecast-error figure
twice in consecutive lines. Conflict is symmetric; the tailor's first choice wins.

**Bullets are for achievements only.** Education, Certifications and Technical Skills
render as left-aligned labelled lines, not `itemize` entries. Bulleting a skills
inventory flattens the distinction between what the candidate did and what they can use, and it is
what made the block read as a wall.

**The skills block is rebuilt, never printed.** `tools/skills_block.py` reads the
tailor's free-form tools string as a set of *selections* against a fixed inventory and
re-renders it in five labelled categories. The old free-form string mixed commas,
semicolons and `\textbullet` separators, so parenthetical groups split apart and an
ATS parser saw fragments like `Tableau)` and `Python (pandas` as separate skills.
The block is also topped up from the rest of the page: anything the summary, a
competency or a selected bullet already states may appear on the skills line, which
keeps a planning resume from omitting forecasting. Nothing is invented; the
block can never claim more than the page does. The profile's `PINNED` item always prints.

**Six parser fixes from an ATS audit, all in the template.** A labelled
`Summary` heading (heading-anchored parsers drop text before the first heading). Employer
and location in one `\cventry` cell ("Brindle & Hart Logistics, Manchester"): the two-cell row made
pdfminer read the location before the employer on most entries and pypdf glue them.
A depth rule under the 30pt name, because a name with no descenders ("Jane Smith") lets layout
extractors read "Jane SmithManchester". A text bullet from the body font instead of the
FontAwesome circle, whose metrics inserted blank lines mid-bullet. `A\kern0pt WS` wherever
AWS is written, because pypdf reads the A-W kern pair as a word gap. The LinkedIn URL as
literal text, not only a link annotation. Dates as "Mar 2022 - Aug 2024" with spaced hyphen.

**No fontawesome contact icons.** The glyphs extract into the text layer as their own
names, `MOBILE-ALT` and `Envelope`, immediately before the phone number and email,
where a parser reading the contact block takes them as part of the value. The symbol
macros are redefined empty.

**Bullets are allocated per posting, from the whole profile.** `tools/bullet_library.py`
holds every bullet the profile supports (read from `profile/bullets.py`), each themed.
`tools/allocate.py` scans the posting for theme cues and decides who gets how many and which:
tenure (two years at Oakmere Foods outweighs one at Saltmarsh Analytics), recency, and how
strongly each employer's best bullets answer this posting. Floors and caps are per role, in
`profile/roles.py`: Brindle & Hart Logistics and Oakmere Foods never drop below two; nobody
exceeds four; Saltmarsh Analytics gets one, or two on a consulting or delivery posting. A
forecasting posting surfaces the demand-forecasting models and the footfall forecasts; a
pipeline posting surfaces the dbt feed rebuild and its data-quality tests; a BI posting
surfaces the Power BI service-level reporting and the supplier segmentation.
Same profile, different page. Ties break on the bullet's own strength, so a quantified result beats an unquantified
one whenever the theme match is close.

**The summary has a floor as well as a ceiling: 36 to 52 words.** cap_summary drops whole
sentences to fit the budget, so a 50-word summary whose first sentence was 16 words rendered
as a 16-word stub. Below the floor the next sentence is
kept and cut at a clause boundary instead of dropped.

**The skills block is capped at 18 rendered tokens, not 18 items.** "Python, pandas, NumPy,
scikit-learn" is one inventory item but four things the eye crosses, so a per-line cap alone
printed 28 tokens over six lines. It now fits four rendered lines. Because `_rank()` puts the
posting's own vocabulary first, the cap only ever removes what this employer did not ask for.

**A cover-letter bullet label is separated from its sentence by a colon.** Without it the page
read "Forecasting models Weekly demand forecasts across 2,400 SKUs". Bold itself is
safe: it is a font weight, and pypdf, pdftotext and pdfminer all extract it as plain text with
no markup characters, so it costs nothing with an ATS and helps a human skim.

**An employer block never opens with a reporting or upkeep bullet.** "Owned the Power BI
service-level reporting..." and "Automated the weekly stock-cover report..." are true and
useful, but as the first line under an employer they tell the reader that was the job.
`NON_LEAD` in `profile/bullets.py` lists them; the allocator puts the strongest lead-eligible
bullet first and keeps score order after that.

**A short stint takes fewer bullets than the cap, unless the posting is its territory**
(`cap_unless` in `profile/roles.py`). Left alone it fills whatever the longer-tenured employers
leave and takes the most space on every page.

**A short stint's tools never populate the skills line on their own** (`skills_context` in
`profile/roles.py`). A graduate year of Tableau dashboards is not a stack. If the posting asks
for it by name, the posting tier adds it.

**A held skill the posting names by name is added to the skills line even when nothing else
lists it.** Every inventory item in `skills_block.py` is profile-supported, and a named
keyword is the one thing an ATS pass must find. The employer's own name is never a skill
(Docker, Inc does not put Docker on the page).

**The summary names every employer in page order:** "seven years across Brindle & Hart
Logistics, Oakmere Foods and Saltmarsh Analytics". Naming some and hiding others reads as
evasive.

**The summary is three lines.** 40-48 words, identity first: "Operations and planning
analyst with a mathematics degree and seven years across...". Not "Data professional with a
background in". The renderer caps at 48 words at the last sentence boundary.

**The fit loop grows as well as trims.** `tools/fit_to_page.py` used to only remove
content, so a resume that overshot by one line and got trimmed stayed a bullet short
of a full page permanently. It now adds bullets back and keeps any that still fit.

---

## ATS Parseability

Most employers run resumes through an ATS before a human sees them, and the ATS reads the PDF's embedded **text layer**, not the rendered page. A resume can pass visual inspection and still extract as garbage. After the layout passes the compile-and-inspect loop, verify the text layer:

```bash
python tools/verify_pdf.py cv/<Prefix>_Resume_<ABBR>.pdf --dump-text cv/<Prefix>_Resume_<ABBR>.txt
```

Extraction tries **pypdf** first (`pip install pypdf`, BSD license), then Poppler `pdftotext`. If a fallback still uses `pdftotext -layout`, it must also pass `-enc UTF-8`: Xpdf-based builds default to Latin-1, which makes every non-ASCII character in a perfectly good resume read back as a replacement character. If neither extractor is available, skip the mechanical check with a warning and rely on the visual PDF read for keyword coverage.

What to check in the extraction:

- **Contact details as literal text.** The stock template's fontawesome contact icons extract as glyph names (`MOBILE-ALT`, `Envelope`) - harmless noise, because the actual address and number are printed beside them. The failure mode is a contact detail carried *only* by an icon or a hyperlink (like the `LinkedIn` link text, whose URL is not in the text layer): invisible to an ATS. The email address must always appear as printed text.
- **No garbled output.** `(cid:NNN)` markers or `�` characters mean a font is embedded without a Unicode mapping - an ATS sees the same garbage. This shows up with unusual fonts in custom templates, not with the stock moderncv setup under lualatex.
- **Reading order.** The stock banking style is single-column, so extraction order matches visual order. Custom templates (via `/add-template`) with sidebars or multi-column layouts can interleave unrelated lines; if extraction order is scrambled, the user is trading ATS compatibility for looks and should be told.
- **Keyword coverage.** Match the posting's required/preferred terms against the extracted text, in the posting's language. Prefer the posting's exact term over a synonym when it is truthfully applicable - ATS matching is often literal. Never add a keyword the profile does not support.

### Date fields must be ASCII ranges (a known ATS import failure)

This one is worth knowing about because it fails **silently**. A resume that passes every other check in this section - clean extraction, no `(cid:)` markers, contact details intact, correct reading order - can still have its dates dropped on import. In a Workday resume import, a resume built from this template can lose the end date of a short contract role and fail to import **any** education entry at all, forcing manual re-entry. Nothing about the PDF or its text layer looks wrong.

Two independent causes, both easy to avoid:

1. **`--` in a `\cventry` date renders as an en-dash (U+2013), not a hyphen.** LaTeX ligatures `--` (two ASCII hyphens, U+002D) into a single en-dash glyph, so `2016--2024` reaches the PDF text layer as `2016<U+2013>2024`. Many parsers split date ranges only on an ASCII hyphen and see no range at all. Write the date argument with a **single hyphen**:

   ```latex
   \item{\cventry{2016-2024}{Role Title}{Organization}{Location}{}{...}}   % parses
   \item{\cventry{2016--2024}{Role Title}{Organization}{Location}{}{...}}  % en-dash, may not
   ```

   This applies to the **date argument only**. Keep `--` everywhere it is typographically correct in prose, for example a numeric range like `EUR 600k--1M`.

2. **A bare single year gives the parser no end date.** A short contract, mandate or internship written as `\cventry{2016}` imports as a start date with nothing to close it. Use an explicit range, with months where the role ran under a year:

   ```latex
   \item{\cventry{Mar 2016 - Jul 2016}{Contract Role}{Client}{Location}{}{...}}
   ```

   Where a genuine range exists, use it even when a single year would be factually accurate - a degree written `1995` is true but imports worse than `1992-1995`. Do not invent a start date you do not have; a lone graduation year is fine, just expect it to be typed in by hand.

**Add this to the step 5d checks**: after extracting the text layer, confirm every experience entry shows a start *and* an end separated by an ASCII hyphen. Because the failure is silent and invisible in the PDF, the candidate otherwise discovers it only while filling in the application form.

## Page Budget - Hard 1-Page Limit

The resume **must** fit on exactly 1 page when compiled (see the two-page exception above). Use these content limits as a guide:

| Section | Max budget on one page |
|---------|-----------|
| Profile statement | 3-4 lines |
| Skills | 3-4 grouped lines, selected per posting |
| Most recent role | 3-4 bullets |
| Previous role | 2-3 bullets |
| Older roles | 1-2 bullets, one line each |
| **Education** | its own section, 1 entry, 1-2 lines |
| **Certifications** | its own section, 1-3 lines |
| References | omit on a one-page resume, or a single line |

### Education and Certifications are separate sections. Never merge them.

They answer different questions. Education is a fixed credential a reader checks once;
certifications are current, dated, and say what the candidate has been doing lately. Running
them together as `\section{Education and Certifications}` buries the certifications inside a
line about a degree, which is where a skim-reader stops looking. It also makes the
in-progress rule harder to satisfy, because a scheduled certification needs to be visibly
scheduled rather than tucked behind a semicolon.

Use two sections, in this order:

```latex
\section{Education}
\vspace{1pt}
\begin{itemize}
\item{\cventry{2016-2019}{BSc Mathematics}{University of Leeds}{Leeds}{}{}}
\end{itemize}

\section{Certifications}
\vspace{1pt}
\begin{itemize}
\item{Microsoft Certified: Power BI Data Analyst Associate (2024)}
\item{[Certification in progress], scheduled [Month Year]}
\end{itemize}
```

A **Tools** or **Skills** line is a third thing again and never belongs under either heading.
If the page will not carry three separate headings, cut content per the relevance-weighted
rules below rather than merging the sections back together.

Interests, Publications, Awards, Presentations and Volunteering are **optional** and are the
first things to cut. Include one only where the posting or the employer makes it useful.

**If in doubt, cut rather than squeeze.** Reducing `\vspace` or geometry scale to force-fit content makes the resume look cramped, and a cramped one-pager reads worse than a clean two-pager.

## Relevance-weighted cutting (the right way to shrink a resume)

**Cut by signal, not by section.** Static priority lists ("remove oldest education first, then shorten the earliest role...") are wrong when a relevant "lower-priority" item is competing with an irrelevant "higher-priority" item. An older-role bullet that speaks directly to the posting is worth more than a recent-role bullet that does not.

For every candidate line, score three things:

1. **Relevance to THIS posting** - does the line hit a named tool, keyword, or stated responsibility in the job ad?
2. **Uniqueness** - is it the only place this claim appears, or is it duplicated elsewhere in the resume?
3. **Narrative load** - does the cover letter depend on it? If cutting the line would force you to rewrite a cover-letter paragraph, it is load-bearing.

Cut the lowest-total-score line first, regardless of which section it sits in.

### Practical order of cuts (easiest → last resort)

1. **Redundancy.** If an achievement appears in both Core Competencies AND a role bullet, the Core Competencies version is usually the cleaner cut (the experience bullet is more concrete evidence).
2. **Profile-statement fluff.** A sentence that just restates what Publications or Skills will show. ("Peer-reviewed publications on X..." is already a Publications entry - profile can claim it once and stop.)
3. **Low-relevance experience bullets.** A bullet about work that does not touch posting keywords, wherever it sits. This cuts across sections before touching the structural list.
4. **Low-relevance supporting content.** An older-role bullet that does not speak to the target role. A certification that does not touch the posting's stack. A language entry that can be condensed to one line.
5. **Low-relevance publications.** Keep 1-2 publications that best match the posting. Cut the rest before touching experience bullets.
6. **Last-resort structural cuts.** Oldest education entry, tightening an older role to 2 bullets, collapsing Certifications into a single line. These only happen if the relevance-weighted cuts above have already been exhausted.

### Pitfalls to avoid

- Do not mechanically cut from the bottom of a static section list without checking relevance. "Cut the oldest role first" is wrong if that role is literally about the skill the posting asks for.
- Do not cut the one concrete example the cover letter leans on. Relevance is measured against the cover letter you wrote, not just the job posting - interviewers will have read both.
- Do not cut to fit if the fit is borderline (2.02 pages). Prefer `\enlargethispage{2-3\baselineskip}` on a late section for near-misses; reserve content cuts for genuine overflow (content on page 3 that is more than a single trailing section).

## Recommended Section Order

Superseded by "Section order is fixed" above: Summary, Professional Experience, Skills,
Education, Certifications. It does not vary by role type, and there is no Core
Competencies block.
