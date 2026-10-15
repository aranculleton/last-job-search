# Vendored: openroles

This folder is a copy of [openroles](https://github.com/aranculleton/openroles), the
employer-board reader that started life as `tools/ats_boards.py` and is now its own open
source library. `tools/ats_boards.py` reads every board through it and keeps the search's
own rules (where the person can work, which titles, which bodies are worth a request).

It is vendored, not installed, so a round needs nothing that a container does not
already have. **Do not edit it here.** Change openroles upstream, then copy its
`src/openroles/` over this folder (leaving out `py.typed`) and update the version below.

Version: 0.1.0 (upstream commit 7aa3bba)
