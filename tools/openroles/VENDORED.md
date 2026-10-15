# Vendored: openroles

This folder is a copy of [openroles](https://github.com/aranculleton/openroles), the
employer-board reader that grew out of `tools/ats_boards.py` and is now its own open source
library. `tools/ats_boards.py --find` uses it to find an employer's board from a name or a
careers page; a round's reading is still `ats_boards.py`'s own.

It is vendored, not installed, so nothing new needs installing. **Do not edit it here.**
Change openroles upstream, then copy its `src/openroles/` over this folder (leaving out
`py.typed`) and update the version below.

Version: 0.1.0 (upstream commit 7aa3bba)
