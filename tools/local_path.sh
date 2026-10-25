# Sourced by setup_env.sh and ci_local.sh: the same directories tools/local_path.py
# adds for the Python tools, for the shell. A chat's shell on a Mac is not a login
# shell, so MacTeX's /Library/TeX/texbin and Bun's ~/.bun/bin are missing from it, and
# what tools/env_check.py --fix installs into the person's own folders (TinyTeX, gh) is
# on no shell's PATH until a new one starts. Only directories that exist; TeX's, Bun's
# and gh's own first, the general ones last, so they never shadow a Python the person
# chose.
_ljs_first=""
for _d in "$HOME/.bun/bin" /Library/TeX/texbin "$HOME"/Library/TinyTeX/bin/* \
          "$HOME"/.TinyTeX/bin/* /usr/local/texlive/20*/bin/*; do
  [ -d "$_d" ] || continue
  case ":$PATH:" in *":$_d:"*) ;; *) _ljs_first="$_ljs_first$_d:" ;; esac
done
# Git Bash on Windows: the same folders local_path.py adds there, in its own path form.
if command -v cygpath >/dev/null 2>&1 && [ -n "${LOCALAPPDATA:-}" ]; then
  _la=$(cygpath -u "$LOCALAPPDATA"); _ad=$(cygpath -u "${APPDATA:-$LOCALAPPDATA}")
  _pd=$(cygpath -u "${ProgramData:-C:\ProgramData}")
  for _d in "$_ad/TinyTeX/bin/windows" "$_pd/TinyTeX/bin/windows" \
            "$_la/Programs/MiKTeX/miktex/bin/x64" "/c/Program Files/MiKTeX/miktex/bin/x64" \
            "$_la/Programs/gh/bin" "$_la/Programs/PortableGit/cmd"; do
    [ -d "$_d" ] || continue
    case ":$PATH:" in *":$_d:"*) ;; *) _ljs_first="$_ljs_first$_d:" ;; esac
  done
  unset _la _ad _pd
fi
PATH="$_ljs_first$PATH"
for _d in "$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
  [ -d "$_d" ] || continue
  case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac
done
export PATH
unset _d _ljs_first
