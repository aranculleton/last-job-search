"""Name each README picture after its contents, so a new picture always has a new address.

On 2026-11-04 the maintainer tapped the Brief's picture in the README on GitHub's phone app and
it opened a picture two versions old: the file had kept one name across versions, so whatever
had been saved under that address was shown in its place. A name that carries the picture's
own hash changes whenever the picture does, and no cache can show an old one under it.

    python3 tools/readme_pictures.py           after remaking any picture in docs/images
    python3 tools/readme_pictures.py --check   exit 1 when a picture or the README is out of step

A remade picture is saved under its plain name (page-brief.png); this renames it to
page-brief-<8 hex>.png, removes the one it replaces and points the README at it.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join("docs", "images")
NAME = re.compile(r"^(?P<stem>.+?)(?:-(?P<hash>[0-9a-f]{8}))?\.(?P<ext>png|gif|jpg|jpeg|webp)$")
SRC = re.compile(r"docs/images/(?P<file>[A-Za-z0-9._-]+)")


def _hash(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:8]


def _pictures(root: str) -> list[tuple[str, str, str | None, str]]:
    folder = os.path.join(root, IMAGES)
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        m = NAME.match(name)
        if m:
            out.append((name, m["stem"], m["hash"], m["ext"]))
    return out


def problems(root: str = ROOT) -> list[str]:
    folder = os.path.join(root, IMAGES)
    found = []
    names = set()
    for name, stem, h, ext in _pictures(root):
        names.add(name)
        actual = _hash(os.path.join(folder, name))
        if h != actual:
            found.append(f"{IMAGES}/{name} should be named {stem}-{actual}.{ext}")
    with open(os.path.join(root, "README.md"), encoding="utf-8") as fh:
        named = set(m["file"] for m in SRC.finditer(fh.read()))
    found += [f"README.md names docs/images/{n}, which is not there" for n in sorted(named - names)]
    found += [f"{IMAGES}/{n} is in no README line" for n in sorted(names - named)]
    if found:
        found.append("Run: python3 tools/readme_pictures.py")
    return found


def rename(root: str = ROOT) -> dict[str, str]:
    """Rename every picture to carry its hash, drop the one each replaces, rewrite the README.
    Returns {old name: new name} for every name that changed."""
    folder = os.path.join(root, IMAGES)
    by_stem: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    for name, stem, h, ext in _pictures(root):
        by_stem.setdefault((stem, ext), []).append((name, h))
    moved: dict[str, str] = {}
    for (stem, ext), files in by_stem.items():
        fresh = [n for n, h in files if h is None]
        if len(files) > 1 and len(fresh) != 1:
            raise SystemExit(f"readme_pictures: more than one {stem}.{ext} and none of them new; "
                             f"keep one: {', '.join(n for n, _ in files)}")
        keep = fresh[0] if fresh else files[0][0]
        wanted = f"{stem}-{_hash(os.path.join(folder, keep))}.{ext}"
        for name, _ in files:
            if name != keep:
                os.remove(os.path.join(folder, name))
                moved[name] = wanted
        if keep != wanted:
            os.replace(os.path.join(folder, keep), os.path.join(folder, wanted))
            moved[keep] = wanted
    readme = os.path.join(root, "README.md")
    with open(readme, encoding="utf-8") as fh:
        text = fh.read()
    new = SRC.sub(lambda m: "docs/images/" + moved.get(m["file"], m["file"]), text)
    if new != text:
        with open(readme, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
    return moved


def main(argv: list[str]) -> int:
    if "--check" in argv:
        found = problems()
        print("\n".join(found) if found else "readme_pictures: every picture is named after itself")
        return 1 if found else 0
    for old, new in rename().items():
        print(f"readme_pictures: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
