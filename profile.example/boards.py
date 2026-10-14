"""Morgan Ellis's employer boards: whose jobs are read straight from their ATS. Fictional.

Empty on purpose. A real profile names employers here with the token their own
careers page reads, each verified first:

    python3 tools/ats_boards.py --add greenhouse <board>
    python3 tools/ats_boards.py --add workday https://<tenant>.wd3.myworkdayjobs.com/<Site>

BOARDS maps an employer to (provider, token); REFUSED to (provider, token, the
robots.txt rule that says no); PLACES is a regex of the places an ATS location
may name for a posting to be kept; WORKDAY_COUNTRY is (Workday's facet id, the
country's name) used to narrow a board before paging it.
"""

import re

BOARDS: dict[str, tuple[str, str]] = {}
REFUSED: dict[str, tuple[str, str, str]] = {}
PLACES = re.compile(
    r"\b(manchester|salford|stockport|trafford|leeds|liverpool|england|united kingdom|uk)\b",
    re.I)
WORKDAY_COUNTRY = ("", "united kingdom")
