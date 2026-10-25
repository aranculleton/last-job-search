#!/usr/bin/env bash
# Verify every rendered application in a drafts.json: the resume within the
# profile's page count (documents.resume_pages, default 1), a one-page letter, chronology,
# bullets per employer, clean text layer (pdftotext, and pypdf for run-together
# words), contact details, every line of the draft in the text layer in order (the
# round trip), the pinned skill, no parentheses in the skills block, no duplicated
# bullets. Then claims and letters.
#
#   tools/verify_batch.sh rounds/r1/drafts.json
#
# Exit 0 all pass, 1 a finding, 3 nothing failed but the spacing check was
# skipped because pypdf is unavailable (which is not a pass).
#
# Everything about the person (the filename prefix, the employers in resume
# order with their column codes and minimum bullets, the email and phone the
# text layer must carry, the pinned skill, the section headings, the document
# noun the market does not use) comes from the profile via tools/docpaths.py.
set -u
DRAFTS="$1"
# Per-run scratch. Fixed /tmp/vb_*.txt names let two batches verifying at once
# (several sessions can run in parallel) read each other's text layers and
# pass or fail the wrong application.
VB="$(mktemp -d)"; trap 'rm -rf "$VB"' EXIT
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_VARS="$(python3 "$ROOT/tools/docpaths.py" shell)" || { echo "verify_batch: cannot read the profile"; exit 1; }
eval "$PROFILE_VARS"
# The documents sit where the renderer wrote them: the checkout, or LJS_STATE's folder.
DOCS="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import person; print(person.state())' "$ROOT/tools")" || DOCS="$ROOT"
ABBRS=$(python3 -c "import json,sys; print(' '.join(a['abbr'] for a in json.load(open(sys.argv[1]))))" "$DRAFTS")
# A general resume has no letter (tools/general_resume.py): its letter checks are skipped.
GENERAL=$(python3 -c "import json,sys; print(' '.join(a['abbr'] for a in json.load(open(sys.argv[1], encoding='utf-8')) if a.get('general')))" "$DRAFTS")
is_general() { case " $GENERAL " in *" $1 "*) return 0 ;; esac; return 1; }
LETTER_ABBRS=$(for a in $ABBRS; do is_general "$a" || echo "$a"; done)
# One awk program per profile: which line opens which role, counted per role.
AWK_ROLES=$(python3 - "$ROLE_NAMES" "$H_EDUCATION" <<'PYX'
import json, re, sys
names, edu = json.loads(sys.argv[1]), sys.argv[2]
esc = lambda s: re.sub(r"([.\[\](){}*+?|^$\\/])", r"\\\1", s)
prog = " ".join(f'/^{esc(n)}/{{e="{i}"}}' for i, n in enumerate(names))
prog += f' /^{esc(edu)}/{{e=""}} /^ *•/{{n[e]++}} END{{printf "%s"'
prog += ',' + ",".join(f'n["{i}"]+0' for i in range(len(names)))
prog = prog.replace('"%s"', '"' + "/".join(["%d"] * len(names)) + '"') + "}"
print(prog)
PYX
)
fail=0; tb=0; n=0; readers=""; skipped=0
printf "%-9s %-4s %-4s %-14s %s\n" ABBR pgs blt "$ROLE_HEADER" flags
for a in $ABBRS; do
  R="$DOCS/cv/${PREFIX}_${NOUN_WORD}_$a.pdf"; C="$DOCS/cover_letters/${PREFIX}_Cover_Letter_$a.pdf"
  if is_general "$a"; then C=""; fi
  [ -f "$R" ] && { [ -z "$C" ] || [ -f "$C" ]; } || { echo "$a MISSING PDF"; fail=1; continue; }
  pdftotext -layout -enc UTF-8 "$R" $VB/vb_r.txt
  if [ -n "$C" ]; then pdftotext -layout -enc UTF-8 "$C" $VB/vb_c.txt; else : > $VB/vb_c.txt; fi
  tr '\n' ' ' < $VB/vb_r.txt | tr -s ' ' > $VB/vb_r1.txt
  p=""
  rp=$(pdfinfo "$R"|awk '/^Pages/{print $2}'); cp=-
  [ -z "$C" ] || cp=$(pdfinfo "$C"|awk '/^Pages/{print $2}')
  [ "$rp" -ge 1 ] 2>/dev/null && [ "$rp" -le "$RESUME_PAGES" ] || p="$p RESUME_${rp}p"
  [ -z "$C" ] || [ "$cp" = 1 ] || p="$p LETTER_${cp}p"
  ord=$(sed -n "/^$H_EXPERIENCE/,/^$H_EDUCATION/p" $VB/vb_r.txt | grep -oE "^($ROLE_ALT)" | tr '\n' '>')
  [ "$ord" = "$ROLE_ORDER" ] || p="$p CHRONO"
  grep -q 'Core Competencies' $VB/vb_r.txt && p="$p COMPETENCIES"
  # The section layout, read off the .tex where it is exact rather than off the
  # rendered text where a heading can wrap. Resumes written before the
  # generator carried Core Competencies with no Summary at all, and only
  # COMPETENCIES was ever checked, so a missing Summary, a merged "Education
  # and Certifications" and a wrong section order all passed.
  lay=$(python3 - "$DOCS/cv/${PREFIX}_${NOUN_WORD}_$a.tex" "$SECTIONS" <<'PYX'
import json, re, sys
want = json.loads(sys.argv[2])
secs = re.findall(r"\\section\{([^}]*)\}", open(sys.argv[1]).read())
out = []
if any(re.search(r"education.*certif|certif.*education", x, re.I) for x in secs):
    out.append("MERGED_EDU_CERT")
if not any(x.strip().lower() == want[0].lower() for x in secs):
    out.append("NO_SUMMARY")
if [x.strip() for x in secs] != want:
    out.append("SECTION_ORDER")
print(" ".join(out))
PYX
)
  [ -z "$lay" ] || p="$p $lay"
  grep -qE '—|–' $VB/vb_r.txt $VB/vb_c.txt && p="$p DASH"
  grep -qE 'cid:|�|::|MOBILE-ALT|Envelope' $VB/vb_r.txt && p="$p TEXTLAYER"
  # The letter's text layer too: a sign its font lacks prints as a replacement character,
  # and only the resume was ever read for one.
  grep -qE 'cid:|�' $VB/vb_c.txt && p="$p TEXTLAYER_LETTER"
  # pdftotext infers spaces from glyph positions, so every check here reads a PDF
  # whose text layer has none as if it were fine. pypdf does not infer them:
  # verify_pdf.py reads with pypdf first and fails words run together. A resume
  # built with LuaLaTeX and an OpenType font read in pypdf with its city and
  # phone number run together, and would have passed everything else here.
  # Which reader it used is said once at the end: only pypdf catches words run
  # together, and a fallback to pdftotext passed them without a word. So pypdf
  # is required; exit 3 means it is unavailable, the rest of the text-layer
  # check runs on pdftotext, and the batch says the spacing check was SKIPPED.
  vr=$(python3 "$ROOT/tools/verify_pdf.py" --require pypdf "$R" 2>&1); st=$?
  if [ "$st" -eq 3 ]; then skipped=1; vr=$(python3 "$ROOT/tools/verify_pdf.py" "$R" 2>&1) || p="$p SPACING_RESUME"
  elif [ "$st" -ne 0 ]; then p="$p SPACING_RESUME"; fi
  vc=""
  if [ -n "$C" ]; then
  vc=$(python3 "$ROOT/tools/verify_pdf.py" --require pypdf "$C" 2>&1); st=$?
  if [ "$st" -eq 3 ]; then skipped=1; vc=$(python3 "$ROOT/tools/verify_pdf.py" "$C" 2>&1) || p="$p SPACING_LETTER"
  elif [ "$st" -ne 0 ]; then p="$p SPACING_LETTER"; fi
  fi
  readers="$readers $(printf '%s\n%s\n' "$vr" "$vc" | grep -oE 'extractor: [a-z]+' | cut -d' ' -f2)"
  grep -qF -- "$EMAIL" $VB/vb_r1.txt && grep -qF -- "$PHONE" $VB/vb_r1.txt || p="$p CONTACT"
  # The round trip: every line the draft put on the page (contacts, headings, the summary,
  # each role's heading line and bullets, each skills line, education, certifications) must
  # be in the text layer, in order. A swallowed % or a glyph the font lacks passed every
  # check above; this names the line it broke.
  rt=$(python3 "$ROOT/tools/verify_pdf.py" "$R" --roundtrip "$DRAFTS" --abbr "$a" 2>&1) || p="$p ROUNDTRIP"
  [ -z "$PINNED" ] || grep -qF -- "$PINNED" $VB/vb_r1.txt || p="$p NO_PINNED_SKILL"
  # Skills sits between Professional Experience and Education; the old range
  # to /^Professional/ never closed and matched "(2018-2022)" under Education.
  # The ";" before "}" is BSD sed's (a Mac's): without it every run there printed an error.
  sed -n "/^$H_SKILLS/,/^$H_EDUCATION/{/^$H_EDUCATION/d;p;}" $VB/vb_r.txt | grep -q '[()]' && p="$p SKILLPARENS"
  [ -z "$BANNED_NOUNS" ] || ! grep -qiE "\\b($BANNED_NOUNS)\\b" $VB/vb_r.txt $VB/vb_c.txt || p="$p $BANNED_FLAG"
  # Six words in a row shared by two bullets (audit_letters.shared_runs, which also reads
  # each letter's bullets against the resume's), and a bullet on the page twice. Read in
  # Python, whole bullets: line by line through sed and cut, a Mac's reader, which puts
  # each mark on a line of its own, made every resume one with a repeated bullet.
  got=$(python3 - "$VB/vb_r.txt" "$H_EXPERIENCE" "$H_EDUCATION" "$ROOT/tools" <<'PYX'
import sys
sys.path.insert(0, sys.argv[4])
from audit_letters import duplicate_bullets, resume_bullets, shared_runs
bul = resume_bullets(open(sys.argv[1], encoding="utf-8", errors="replace").read(),
                     sys.argv[2], sys.argv[3])
print(len(shared_runs(bul)), len(duplicate_bullets(bul)))
PYX
)
  shared=${got%% *}; dups=${got##* }
  [ "$dups" = 0 ] || p="$p DUPBULLET"
  [ "$shared" = 0 ] || p="$p SHARED_PHRASE($shared)"
  cnt=$(awk "$AWK_ROLES" $VB/vb_r.txt)
  # A role the profile gives a verify_min must carry at least that many.
  for m in $ROLE_MINS; do
    i=${m%%:*}; rest=${m#*:}; min=${rest%%:*}; short=${rest#*:}
    got=$(echo "$cnt" | cut -d/ -f$((i+1)))
    [ "$got" -ge "$min" ] || p="$p ${short}_LT_${min}"
  done
  b=$(grep -cE '^ *•' $VB/vb_r.txt); tb=$((tb+b)); n=$((n+1))
  printf "%-9s %s/%s  %-4s %-14s %s\n" "$a" "$rp" "$cp" "$b" "$cnt" "$p"
  case " $p " in *" ROUNDTRIP "*) printf '%s\n' "$rt" | sed 's/^/          /' ;; esac
  [ -n "$p" ] && fail=1
done
[ "$n" -gt 0 ] && echo "mean bullets: $((tb/n))"
used=$(echo $readers | tr ' ' '\n' | sort -u | tr '\n' ' ' | sed 's/ $//')
case " $used " in
  *" pdftotext "*) echo "text layer read with: ${used:-nothing} (pdftotext fallback: words run together are NOT caught; pip3 install pypdf, or pip3 install --upgrade cffi if it is installed)" ;;
  *) echo "text layer read with: ${used:-nothing}" ;;
esac
echo "=== claims ==="
# The pipeline's exit status is the last command's, so a failing check hid
# behind grep|head and the script said ALL PASS over letters carrying
# drafter notes. PIPESTATUS[0] is the checker's own status.
python3 "$ROOT/tools/check_claims.py" $(for a in $ABBRS; do echo "$DOCS/cv/${PREFIX}_${NOUN_WORD}_$a.tex"; is_general "$a" || echo "$DOCS/cover_letters/${PREFIX}_Cover_Letter_$a.tex"; done) 2>&1 | grep -E "^[0-9]+ error|ERROR" | head
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "CLAIMS: FAILURES ABOVE"; fail=1; }
echo "=== letters ==="
# `tail -1` printed only the count, so "FAILURES ABOVE" pointed at nothing that
# was above. The flagged letters are the output worth having.
python3 "$ROOT/tools/audit_letters.py" "$DRAFTS" | grep -E "^!!|letters clean"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "LETTERS: FAILURES ABOVE"; fail=1; }
echo "=== numbers ==="
# check_claims.py catches errors the grounding reviewer already found. It
# cannot catch a metric nobody has invented yet, and SECURITY.md ranks a
# fabricated claim reaching an employer as the worst thing this system can do.
# This is the general case for the kind of claim that can be checked
# mechanically: every number in the resume must exist in the profile.
#
# The letters are read from the drafts, not the .tex: a cover letter carries
# verified company facts ("a 40-year lease", "12,345 daily deliveries") which
# are not the candidate's claims about themselves, and only the draft knows
# which paragraph holds them. `--drafts` checks the summary, the opening, the
# bullets and the close, numbers written as words included, and allows the figures in p2
# and in the posting in the opening and the close (never in the summary or the bullets,
# which are the candidate's own work).
python3 "$ROOT/tools/check_numbers.py" --drafts "$DRAFTS" \
  $(for a in $ABBRS; do echo "$DOCS/cv/${PREFIX}_${NOUN_WORD}_$a.tex"; done)
[ "$?" -eq 0 ] || { echo "NUMBERS: FAILURES ABOVE"; fail=1; }
echo "=== keywords (a report: nothing here fails the batch or changes a document) ==="
# What the posting names against what the page carries: on it, held but not on it, and
# not held. A skill the profile does not hold is listed as not held, never as one to add.
for a in $ABBRS; do
  python3 "$ROOT/tools/verify_pdf.py" "$DOCS/cv/${PREFIX}_${NOUN_WORD}_$a.pdf" \
    --keywords "$DRAFTS" --abbr "$a" 2>&1 | sed "s/^/$a: /"
done
echo "=== voice ==="
# The anti-cliche rules lived only in 03-writing-style.md, which means they were
# followed at whatever rate they were followed at and nothing measured it. A
# recruiter who has read forty applications this week spots a generated letter
# in one sentence, and an outreach note that reads as generated gets no reply.
# Soft findings are a smell and do not fail the batch; hard ones do.
if [ -n "$LETTER_ABBRS" ]; then
python3 "$ROOT/tools/voice_check.py" --soft-ok \
  $(for a in $LETTER_ABBRS; do echo "$DOCS/cover_letters/${PREFIX}_Cover_Letter_$a.tex"; done)
[ "$?" -eq 0 ] || { echo "VOICE: FAILURES ABOVE"; fail=1; }
else
echo "no letters: a general resume"
fi
if [ "$skipped" = 1 ]; then
  echo "=== SPACING CHECK SKIPPED ==="
  echo "pypdf is not available, so words run together were NOT checked on any document."
  echo "pip3 install pypdf (or pip3 install --upgrade cffi if it is installed) and run this again."
fi
[ $fail -eq 0 ] || { echo "BATCH: FAILURES ABOVE"; exit 1; }
[ "$skipped" = 0 ] || { echo "BATCH: NOT ALL PASS, the spacing check was SKIPPED"; exit 3; }
echo "BATCH: ALL PASS"
