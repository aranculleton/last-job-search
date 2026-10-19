# Sourced by setup_env.sh and ci_local.sh: the same directories tools/local_path.py
# adds for the Python tools, for the shell. A chat's shell on a Mac is not a login
# shell, so MacTeX's /Library/TeX/texbin and Bun's ~/.bun/bin are missing from it.
# Only directories that exist; TeX's and Bun's first, the package managers' last,
# so they never shadow a Python the person chose.
_ljs_first=""
for _d in "$HOME/.bun/bin" /Library/TeX/texbin "$HOME"/Library/TinyTeX/bin/* \
          "$HOME"/.TinyTeX/bin/* /usr/local/texlive/20*/bin/*; do
  [ -d "$_d" ] || continue
  case ":$PATH:" in *":$_d:"*) ;; *) _ljs_first="$_ljs_first$_d:" ;; esac
done
PATH="$_ljs_first$PATH"
for _d in /opt/homebrew/bin /usr/local/bin; do
  [ -d "$_d" ] || continue
  case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac
done
export PATH
unset _d _ljs_first
