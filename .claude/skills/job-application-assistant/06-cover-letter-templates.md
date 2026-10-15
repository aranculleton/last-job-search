---
framework_version: 2.1.4
---

# Cover Letter Templates and Tailoring Guide

## Template: Custom cover.cls (XeLaTeX)

Cover letters use a custom LaTeX document class (`cover.cls`) with Lato/Raleway fonts.

**Output file:** `cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex`, where `<Prefix>` is `identity.file_prefix` in `profile/person.json` (see the File naming table in `05-cv-templates.md`)
**Compile with:** XeLaTeX (cover.cls requires fontspec)
**Font directory:** `cover_letters/OpenFonts/fonts/`

### Compile command

```bash
cd cover_letters && xelatex -interaction=nonstopmode <Prefix>_Cover_Letter_<ABBR>.tex
```

Expected output: `Output written on <Prefix>_Cover_Letter_<ABBR>.pdf (1 page, ...)`. Any page count other than 1 is a failure that must be fixed before presenting to the user.

## Compile-and-Inspect Loop (MANDATORY)

After writing the cover letter and before presenting to the user, always compile and visually inspect the PDF. Iterate until the layout is clean:

1. Run `xelatex -interaction=nonstopmode <Prefix>_Cover_Letter_<ABBR>.tex`
2. Confirm page count is exactly 1 and compile succeeded
3. Read the PDF via the Read tool and visually check: signature fits at the bottom, no text cut off, bullet font matches body

### Known template pitfall: itemize inside `\lettercontent{}`

The `\lettercontent{}` macro appends `\\` to its argument. This breaks when the argument ends in `\end{itemize}` because `\\` has no line to break after the environment closes, producing `! LaTeX Error: There's no line here to end.` and no PDF output.

**Wrong (breaks compile):**
```latex
\lettercontent{Here is how my experience maps:
\begin{itemize}
    \item ...
\end{itemize}}
```

**Correct - close `\lettercontent{}` before the list and wrap the list in the matching Raleway-Medium font so typography stays consistent:**
```latex
\lettercontent{Here is how my experience maps:}

{\raggedright\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}\fontsize{11pt}{13pt}\selectfont
\begin{itemize}
    \item ...
\end{itemize}\par}
\vspace{6pt}

\lettercontent{[next paragraph]}
```

The font wrapper is mandatory - if you just move `\begin{itemize}` outside `\lettercontent{}` without the `\fontspec` block, bullets render in the default body font (Lato) and visually mismatch the rest of the letter.

## Document Structure

```latex
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Cover Letter - [Company], [Role]
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\documentclass[]{cover}
\usepackage{fancyhdr}

\pagestyle{fancy}
\fancyhf{}

\rfoot{Page \thepage \hspace{0pt}}
\thispagestyle{empty}
\renewcommand{\headrulewidth}{0pt}
\begin{document}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%     TITLE NAME
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
\namesection{}{\Huge{Morgan Ellis}}{  \href{mailto:morgan.ellis@example.com}{morgan.ellis@example.com} | +44 7700 900123 |  \urlstyle{same}\href{https://www.linkedin.com/in/morgan-ellis-example}{LinkedIn}
}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%     MAIN COVER LETTER CONTENT
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\currentdate{[the date, written out: March 4, 2026]}
\lettercontent{Dear [Name/Team],}

\lettercontent{[Opening paragraph - the strongest match to the posting, 2-3 sentences]}

\lettercontent{[Company paragraph - why this role, why this company specifically, one verified fact]}

\lettercontent{[Lead-in sentence introducing the bullet list]}

{\raggedright\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}\fontsize{11pt}{13pt}\selectfont
\begin{itemize}
    \item {[Concrete achievement/skill 1]}
    \item {[Concrete achievement/skill 2]}
    \item {[Concrete achievement/skill 3]}
\end{itemize}\par}

\lettercontent{[Closing paragraph - a sentence specific to this role, then the call to action]}

\begin{flushright}
% No trailing \\ inside \closing{} - cover.cls appends its own \\, and a
% doubled break triggers "! LaTeX Error: There's no line here to end."
\closing{Kind regards,}

\signature{Morgan Ellis}
\end{flushright}
\end{document}
```

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `\namesection{}{Name}{contact info}` | Header with name and contact |
| `\currentdate{date}` | Date field. Write the date out: `\today` is evaluated at compile time and re-dates the letter on every recompile |
| `\lettercontent{text}` | Body paragraph (adds spacing after) |
| `\closing{text}` | Closing line |
| `\signature{name}` | Printed name below signature |

## Tailoring Guidelines

### Salutation
- If you know the hiring manager's name: "Dear [First Last],"
- If you know the team: "Dear [Company] hiring team,"
- Generic: "Dear [Company]," (avoid "To whom it may concern")

### Length - shorter than one page, not merely within it

Fitting on one page is the floor, not the target. A letter that fills the page is a letter
the reader skims; a letter they finish is worth more than one that says more.

- **Word budget: 200-250 words** of body text, not counting LaTeX markup. Treat 250 as the
  ceiling, not the goal. Under 200 is fine when the matches are strong.
- **Four blocks maximum**: opening, one company paragraph, one bullet list of **3 bullets**,
  closing. A fifth block needs a reason you can state.
- **Bullets are one sentence each.** Two sentences in a bullet means the second one is
  usually the resume repeating itself. Cut it.
- **The page should end visibly short of the signature block.** White space above the
  signature reads as confidence. A letter whose last line crowds the closing reads as a
  candidate who could not decide what to leave out.
- **Never restate the posting's requirements back to the reader** before answering them.
  "Your posting asks for X, and I have X" is two clauses where one will do: assert X.
- **Never repeat a resume bullet near-verbatim.** The reader has both documents. A sentence
  that appears in each is a wasted sentence in the letter, which is the shorter document and
  the one where every line has to earn its place.

**How to cut, in order:** the sentence restating the posting; the second sentence of any
bullet; any bullet duplicating the resume; adjectives and scene-setting; the third bullet, if the first two carry the case.
Never cut the company-specific paragraph to make room, and never cut a concession you have
decided is warranted, since a half-made concession is worse than none.
- When adding company-specific content, trim other content to compensate rather than adding net length

### Line Spacing
- Add `\usepackage{setspace}` and `\setstretch{1.0}` if the letter is long and needs to fit on one page
- Use `\vspace{.5cm}` between major sections for readability (only if space permits)

### Bullet Lists
- Place `\begin{itemize}...\end{itemize}` **outside** a `\lettercontent{}` block (see "Known template pitfall" above), wrapped in the matching Raleway-Medium `\fontspec` so the bullet font matches the body
- Three bullets, each profile evidence tied to a stated requirement
- **No bold, no italics, anywhere in a cover letter.** No `\textbf`, no `\textit`, no
  `\emph`, no `\bfseries`, no `\underline`. A letter is prose a person reads top to
  bottom, and typographic emphasis in it reads as a deck or a marketing email rather than
  a letter. It is also what makes a batch of letters look
  machine-assembled: the same bold labels scattered across the set.
- Start each bullet with a plain label followed by a colon, or with an action verb. The
  label carries the structure on its own; it does not need weight.
  `\item Forecasting models: weekly demand forecasts across 2,400 SKUs.`
- A bullet whose text begins with a literal `[` must be braced: `\item {[text]}`. Unbraced, LaTeX parses `[text]` as `\item`'s optional label and renders it off the left page edge, missing from the PDF text layer entirely

### LaTeX Special Characters
Escape these wherever they appear in body text:
- Ampersand: `\&` (company names: Brüel \& Kjær, H\&M) - unescaped, the compile fails loudly
- Percent: `\%` ("grew revenue 30\%") - unescaped, it does **not** fail: everything after the `%` on that line is silently eaten as a LaTeX comment
- Dollar: `\$`, hash: `\#`, underscore: `\_`
- Tilde: `\textasciitilde{}`, caret: `\textasciicircum{}`, backslash: `\textbackslash{}`

## What the letter is for

The letter exists to make the reader want to interview the candidate. Every paragraph should
be doing that work. Read `03-writing-style.md` rule 8 before drafting, and apply it here:

- **Open on the strongest match**, not on an assertion of adjacency and not on the job title.
  The first substantive thing on the page is something the candidate has built or delivered
  that the posting asks for.
- **Give the middle to evidence.** Bullets carry concrete outcomes with numbers, each tied to
  something the posting names.
- **At most one concession, in at most one sentence**, and only for a stated hard requirement
  the reader will notice anyway (a mandatory named tool, a years bar, a required credential).
  Nice-to-haves and "would be an asset" items get nothing.
- **Never build a paragraph around a shortfall**, and never let the last thing before the
  closing be what the candidate cannot do. If a concession is needed, put it mid-letter,
  inside a sentence that finishes on capability.
- **Count them before you compile.** More than one gap sentence in a one-page letter means
  the letter is arguing the employer's case for them. Cut back to one, or to none.

A useful test: strike every sentence about what the candidate lacks. If the remaining letter
is weaker, the concessions were doing real work. If it is stronger, they were not.

## Checklist Before Finalizing
- [ ] No em-dashes (use commas or periods instead)
- [ ] Spelling follows the profile's variant (`documents.spelling` in `profile/person.json`) throughout (rule 7)
- [ ] Uses the profile's noun for the document (`documents.noun`), never one of `documents.banned_nouns`
- [ ] At most one gap sentence, mid-letter, never in the closing (rule 8)
- [ ] Filename follows `<Prefix>_Cover_Letter_<ABBR>`
- [ ] No cliches or empty filler
- [ ] Every claim backed by specific example
- [ ] Forward-looking framing: focuses on tasks you'll solve, not just past duties
- [ ] Motivation section references this specific company's mission/values
- [ ] Company name and role are correct throughout
- [ ] Date is current
- [ ] Fits on one page with visible white space above the signature block
- [ ] Body text is 200-250 words, four blocks maximum, bullets one sentence each
- [ ] Document language is the profile's spelling variant by default, switched only where rule 7 in `03-writing-style.md` allows, never mixed
- [ ] Salutation is appropriate (named person if possible)
- [ ] Headline is engaging and specific, not generic

## Submission Guidelines (Best Practice)
- Submit only the documents the employer requests
- Export as PDF to preserve formatting
- Name files per the File naming table in `05-cv-templates.md`
- Follow all employer instructions regarding anonymity or specific materials
