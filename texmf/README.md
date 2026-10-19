# texmf: the two icon packages the resume needs

moderncv loads `fontawesome5` and `academicons` for its contact-line icons. In
TeX Live both ship only in `texlive-fonts-extra`, a 1.7 GB package of which the
documents used 1.5 MB. Every fresh container downloaded all of it. These files
are copied unchanged from TeX Live 2023 (Debian `texlive-fonts-extra
2023.20240207-1`) in its own TDS layout, so the install drops that package.

| Package | Version | Licence |
|---|---|---|
| fontawesome5 (Marcel Krüger) | 5.15.4 | LaTeX code LPPL 1.3c; Font Awesome Free fonts SIL OFL 1.1 |
| academicons (Diogo A. B. Fernandes) | 1.9.1 | LaTeX code LPPL 1.3c; font SIL OFL 1.1 |

Both licences permit redistributing unmodified copies. Do not edit these files;
replace the directory from a newer TeX Live instead.

## How it is found

kpathsea searches `TEXMFHOME`. `tools/fit_to_page.py` sets it to this directory
for every compile (`tex_env()`), and so do `tools/ci_local.sh` and CI. For a
compile by hand:

```bash
export TEXMFHOME="$PWD/texmf"     # from the repo root
cd cv && lualatex <Prefix>_Resume_<ABBR>.tex
```

Nothing links `~/texmf` (kpathsea's default `TEXMFHOME`) to this directory, on purpose:
with two copies of the app on one computer, two worktrees for two chats, each would take
the one link from the other. A compile by hand sets the variable as above, and a
`~/texmf` that is already there is left as it is.

The cover letter needs none of this: `cover.cls` loads its fonts from
`cover_letters/OpenFonts/` by path.
