#!/bin/sh
# The batch check, by the name every instruction and every chat has used for it:
#
#   tools/verify_batch.sh rounds/r1/drafts.json
#
# The checks themselves are tools/verify_batch.py, which reads the PDFs with pypdf, so
# nothing beyond the app's own Python packages is needed (it was bash over Poppler's
# pdftotext, which a Mac has only through Homebrew and Windows only through winget).
# Exit codes are its own: 0 all pass, 1 a finding, 3 the spacing check was skipped.
# tools/py.sh finds a Python 3.9+ on any computer (python3, python, or py -3).
here=$(cd "$(dirname "$0")" && pwd)
if [ -f "$here/py.sh" ]; then
  exec sh "$here/py.sh" "$here/verify_batch.py" "$@"
fi
exec python3 "$here/verify_batch.py" "$@"
