# templates/

Two unrelated things share this directory, which is worth knowing before reading
further.

## `resume_gen.py` is the live generator, not a custom template

It holds the LaTeX that `tools/render_application.py` fills in for every resume and cover
letter this repo produces: the moderncv preamble with its ATS fixes, the `\cventry`
block, the skills and education tails, and the `cover.cls` letter body. It is imported,
not registered, and `/add-template` neither reads nor writes it.

It lives here rather than in `tools/` because it is content rather than logic: the
decisions in it are typographic and ATS-related (drop the FontAwesome contact icons,
because they extract as "MOBILE-ALT" directly in front of the phone number; force a rule
with depth under the name, because a name with no descenders lets a position-sorting
extractor read the name and the city below it as one word). Nothing about the person is
here either: the name, contact line, education, certifications and sign-off come from the
profile (`tools/person.py`), and bullet text lives only in the profile's `bullets.py`. A
second copy of the bullets in this file once kept a clause that had already been removed
from the library.

Everything below is about the other thing.

---

# Custom Templates

This folder holds user-registered templates (LaTeX, Typst, or any other toolchain with a declared compile command), managed by the `/add-template` command. The repo works out of the box with its stock templates (moderncv for resumes, `cover.cls` for cover letters). This folder only gets content when you register your own.

## Layout

```
templates/
├── cv/
│   └── <template-name>/
│       ├── template.<ext>  # Profile-agnostic skeleton ([PLACEHOLDER] tokens), e.g. template.tex or template.typ
│       ├── TEMPLATE.md      # Manifest: source extension, compile command, fonts, page limit, style rules, pitfalls
│       ├── *.cls / *.sty    # Custom class/style files, or Typst packages (if the template needs them)
│       └── fonts/           # Bundled font files (if not using system fonts)
└── cover_letters/
    └── <template-name>/
        └── (same layout)
```

## How it works

- `/add-template` interviews you for the template's instructions (source extension, compile command, fonts, style rules, page limit), stores the files here, and runs a mandatory test compile before registering anything.
- Activating a template adds a managed block to `05-cv-templates.md` or `06-cover-letter-templates.md`, which is what `/apply` reads when drafting and compiling. No other wiring is needed.
- `/add-template --list` shows registered templates; `/add-template --use <name>` switches; `/add-template --use default` reverts to the stock templates.

Templates are stored with `[PLACEHOLDER]` tokens instead of personal data, so they are safe to commit and share.
