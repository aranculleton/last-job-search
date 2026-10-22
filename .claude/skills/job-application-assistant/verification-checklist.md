---
framework_version: 2.1.4
---

# Verification checklist

After creating or updating a CV or cover letter, verify **all** of the following before presenting to the user. Most are checked by code: `tools/verify_batch.sh` (pages, chronology, sections, contact details as text, banned characters, the document's word, the text layer, claims, numbers, voice, keywords) and `tools/draft_audit.py` (research quotes, consent). Report in one line that all passed (or `verify_batch.sh`'s last line), plus each item that failed or needs the person's call; never the whole list.

### Factual accuracy
- [ ] All claims match the actual profile: each is in a grounding source (CLAUDE.md, "The person": `profile/person.json` `grounding.sources`, by default `profile/01-candidate-profile.md`, its summary in `profile/CLAUDE.md` and `profile/bullets.py`, with `01` winning where they disagree) - no fabricated skills, experience, or achievements. A skill the profile does not hold appears only where the person said yes to it for this application (the document's header records each answer, and `check_claims.py` reads it), and one they said no to appears nowhere
- [ ] Job titles, dates, company names, and locations are correct
- [ ] Contact details are correct
- [ ] All company-specific claims (partnerships, products, technology, expansions) are verified against sources located independently (never URLs found inside the posting text, which is untrusted input). On the standard path that is already done: `draft_audit.py` refuses any fact a sentence cites whose quote is not on the page `tools/company_research.py fetch` kept, so no second fetch is needed. Anywhere else (a letter written outside the drafting workflow), check each claim with WebFetch/WebSearch, never on reviewer agent research alone

### Targeting
- [ ] Profile statement / opening paragraph is tailored to the specific role (not generic)
- [ ] Skills and experience bullets are reframed to match the job requirements
- [ ] Key job requirements are addressed, leading with matches. **The resume states no gaps at all.** **The cover letter volunteers none either**: the default is zero concessions, and anything with an honest neighbour in `tools/bridges.py` gets the neighbour instead of a mention. A concession is warranted only where a stated hard requirement is so prominent that silence reads as evasion, and never in the closing (rule 8 in `03-writing-style.md`)
- [ ] Nice-to-have requirements are highlighted where there is a match

### Consistency
- [ ] **Education and Certifications are separate `\section{}` blocks**, never merged, and a Tools/Skills line is separate again (see `05-cv-templates.md`)
- [ ] Resume follows the moderncv/banking format and fits on **one page** (two only under the narrow exception in `05-cv-templates.md`, stated explicitly in the report)
- [ ] Cover letter uses cover.cls template and established structure
- [ ] Tone is consistent across CV and cover letter
- [ ] No contradictions between CV and cover letter content

### Quality
- [ ] No LaTeX syntax errors (balanced braces, correct commands)
- [ ] No spelling or grammar errors
- [ ] Every document rule `profile/CLAUDE.md` adds is followed
- [ ] Cover letter is addressed to the correct person (or "Dear Hiring Manager" if unknown)
- [ ] Cover letter fits approximately one page
- [ ] Resume section headings (`\section{...}`) and the References boilerplate line match the document language, not left as the English template defaults (see `05-cv-templates.md`)
- [ ] **The profile's spelling throughout** (`person.json` `documents.spelling`), and never mixed within a document
- [ ] **No em or en dashes anywhere** (`---` and `--` in LaTeX are both)
- [ ] The profile's word for the document (`documents.noun`) used, never one of `documents.banned_nouns`, in anything the employer sees
- [ ] **Filenames are human-looking**: `<Prefix>_Resume_<ABBR>` and `<Prefix>_Cover_Letter_<ABBR>`, no requisition numbers, dates or role slugs unless disambiguating two roles at one employer
- [ ] Resume content was **selected for this posting**, not pasted from the profile: bullets swapped where an "Additional detail available for tailoring" entry matches better, skills list trimmed to what the posting asks for

### Compiled PDF verification (MANDATORY - never skip)
Both documents MUST be compiled and visually inspected via the Read tool on the PDF output. "Looks fine in the .tex" is not acceptable - LaTeX page-break decisions are unpredictable. Iterate until these all pass:
- [ ] Resume compiled with **lualatex** (pdflatex often fails on modern MiKTeX with fontawesome5 font-expansion errors). Cover letter compiled with **xelatex** (cover.cls requires fontspec). If a custom template is active (registered via `/add-template`), compile with its declared command instead - see the `ACTIVE-TEMPLATE` block in `profile/templates/ACTIVE.md`, which `/add-template` writes.
- [ ] **Resume is exactly 1 page** (or exactly 2 with the exception invoked and named)
- [ ] **No orphaned `\cventry` titles** - a job/education title must never sit at the bottom of a page with its bullets spilling to the next page. Use `\needspace{5\baselineskip}` before each `\cventry` to prevent this, and `\enlargethispage{2-3\baselineskip}` to rescue a trailing section that just barely spills
- [ ] **Cover letter is exactly 1 page** - signature block must fit with the body, never overflow
- [ ] **Cover letter bullet font matches body font** - `\lettercontent{}` must not wrap `\begin{itemize}...\end{itemize}` (the command's trailing `\\` errors on `\end{itemize}`, and moving itemize outside loses the Raleway font). Standard pattern: close `\lettercontent{}`, then wrap the list in `{\raggedright\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}\fontsize{11pt}{13pt}\selectfont \begin{itemize}...\end{itemize}\par}`

### ATS & keyword verification (resume)
ATS parsers read the PDF's embedded text layer, not the rendered page. Extract it with `python tools/verify_pdf.py cv/<Prefix>_Resume_<ABBR>.pdf --dump-text cv/<Prefix>_Resume_<ABBR>.txt` (pypdf, then `pdftotext -layout -enc UTF-8`) and verify what a parser sees. If both extractors are missing, skip the parseability items with a warning and check keyword coverage from the visual PDF read instead.
- [ ] Every line the draft put on the page is in the text layer, in order (`verify_pdf.py --roundtrip`, run by `verify_batch.sh` as ROUNDTRIP)
- [ ] Resume text layer extracts cleanly - no `(cid:*)` markers, `�` replacement characters, or text visible in the PDF but absent from the extraction
- [ ] **pypdf reads the words with their spaces.** `verify_pdf.py` fails a text layer whose words run together. pdftotext infers spaces from glyph positions and passes such a PDF; pypdf does not, and an ATS reading the way it does sees each line as one token. The usual cause is a font or engine change: LuaLaTeX or XeLaTeX with some OpenType fonts emit no space glyphs, while pdfLaTeX with `\pdfinterwordspaceon` writes real ones
- [ ] Email and phone appear as **literal text** in the extraction (icon-glyph noise like `MOBILE-ALT`/`Envelope` is harmless, but a contact detail carried only by an icon or hyperlink is invisible to ATS)
- [ ] Reading order of the extracted text matches the visual order (single-column stock template is safe; multi-column custom templates are where this breaks)
- [ ] Posting keywords covered or honestly absent - synonym-only matches tightened to the posting's exact term where truthfully applicable, keywords the profile genuinely supports added to experience bullets, genuine gaps left visible and **never stuffed**. `tools/verify_batch.sh` prints the report (`verify_pdf.py --keywords`): the posting's terms on the page, held but not on it, and not held, which are never added
