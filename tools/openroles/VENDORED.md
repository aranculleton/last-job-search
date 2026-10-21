# Vendored: openroles

This folder is a copy of [openroles](https://github.com/aranculleton/openroles), the
employer-board reader that grew out of `tools/ats_boards.py` and is now its own open source
library. It is the app's one reader of employer boards: `tools/ats_boards.py` reads every
board through it and `--find` finds them with it, `tools/robots_check.py` uses its robots.txt
parser, `tools/prefilter.py` its Workday address parser and its list of systems, and
`tools/env_check.py` asks it which hosts a person's boards need. None of those keeps a copy.

It is vendored, not installed, so nothing new needs installing. **Do not edit it here.**
Change openroles upstream, then copy its `src/openroles/` over this folder (leaving out
`py.typed`) and update the version below.

Version: 0.3.0 (upstream commit ee32290)
