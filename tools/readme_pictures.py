"""Name each README picture after its contents, so a new picture always has a new address.

On 2026-11-04 the maintainer tapped the Brief's picture in the README on GitHub's phone app and
it opened a picture two versions old: the file had kept one name across versions, so whatever
had been saved under that address was shown in its place. A name that carries the picture's
own hash changes whenever the picture does, and no cache can show an old one under it.

    python3 tools/readme_pictures.py shoot     take the four pictures afresh, then name them
    python3 tools/readme_pictures.py           after remaking any picture in docs/images by hand
    python3 tools/readme_pictures.py --check   exit 1 when a picture or the README is out of step

A remade picture is saved under its plain name (page-brief.png); this renames it to
page-brief-<8 hex>.png, removes the one it replaces and points the README at it.

`shoot` takes the README's four pictures of the sample page (tests/fixtures/
app_model_sample.json) with the page's browser harness (tests/app_page/harness.js, its
`shots` scenario), so no picture is taken by hand to a written spec again: the Brief at
1600x900 light and dark, the sample's running search on screen, light above a diagonal from
61% across the top to 44% across the bottom and dark below it; Contacts at 1600x1000 with no
work running; Coming up on a 390x844 phone; and the tour, seven screens at 1600x1000 with no
work running, in one shared palette of 96 colours, 1.6 seconds a frame, under 700 KB or not
written at all. Each is taken at twice its size (the phone at three times) and scaled down.
It needs Node with Playwright, and Pillow; it says how to install whichever is missing. The
pictures are drawn in this computer's own fonts: look at each before it is committed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


# ------------------------------------------------------------------ taking the pictures

BRIEF = "page-brief-light-dark.png"
CONTACTS = "page-contacts.png"
PHONE = "page-coming-up-phone.png"
TOUR = "page-demo.gif"
# The diagonal between the Brief's light and dark halves: how far across it starts at the top
# and ends at the bottom.
DIAGONAL = (0.61, 0.44)
TOUR_SCREENS = ("brief", "todo", "jobs", "contacts", "interviews", "chat", "settings")
TOUR_COLOURS = 96
TOUR_MS = 1600
TOUR_MAX = 700_000
SAMPLE = os.path.join("tests", "fixtures", "app_model_sample.json")
HARNESS = os.path.join("tests", "app_page", "harness.js")


def _shot(name, w, h, hash_, scale=2, look="light", work=True) -> dict:
    """One picture for the harness's `shots` scenario. `work`: the sample's running search
    and a queued draft in Claude's work, so the work pill shows; without it, none."""
    s = {"name": name, "viewport": {"width": w, "height": h}, "hash": hash_, "scale": scale,
         "scheme": look, "look": {"look": look}}
    if not work:
        s["seed"] = False
    return s


SHOTS = ([_shot("brief-light", 1600, 900, "brief"),
          _shot("brief-dark", 1600, 900, "brief", look="dark"),
          _shot("contacts", 1600, 1000, "contacts", work=False),
          _shot("phone", 390, 844, "interviews", scale=3)]
         + [_shot(f"tour-{i}-{screen}", 1600, 1000, screen, work=False)
            for i, screen in enumerate(TOUR_SCREENS)])


def _image_module():
    """The Image module of Pillow, or None with one plain line on how to install it."""
    try:
        from PIL import Image
        return Image
    except ImportError:
        print("readme_pictures: taking the pictures needs Pillow, which is not installed for "
              "this Python. Install it with: python3 -m pip install Pillow")
        return None


def fit(img, size):
    """`img` scaled to exactly `size`, in RGB."""
    from PIL import Image
    return img.convert("RGB").resize(size, Image.LANCZOS)


def compose_brief(light, dark, size=(1600, 900), diagonal=DIAGONAL):
    """The Brief light above a diagonal and dark below it, the same moment, at `size`: the
    cut is drawn at the size taken, so its edge is smooth once scaled down."""
    from PIL import Image, ImageDraw
    light, dark = light.convert("RGB"), dark.convert("RGB").resize(light.size)
    w, h = light.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (diagonal[0] * w, 0), (diagonal[1] * w, h), (0, h)],
                                 fill=255)
    return fit(Image.composite(light, dark, mask), size)


def tour_gif(frames, size=(1600, 1000), colours=TOUR_COLOURS, ms=TOUR_MS) -> bytes:
    """The tour as a GIF: every frame scaled to `size` and drawn in one palette of `colours`
    shared by all, `ms` a frame, looping."""
    from PIL import Image
    frames = [fit(f, size) for f in frames]
    # The palette from all the frames at once, so a colour on one screen is the same on all.
    thumb = (size[0] // 4, size[1] // 4)
    sheet = Image.new("RGB", (thumb[0], thumb[1] * len(frames)))
    for i, f in enumerate(frames):
        sheet.paste(f.resize(thumb, Image.LANCZOS), (0, i * thumb[1]))
    palette = sheet.quantize(colors=colours)
    none = Image.Dither.NONE if hasattr(Image, "Dither") else Image.NONE
    drawn = [f.quantize(palette=palette, dither=none) for f in frames]
    buf = io.BytesIO()
    # Given the palette, the file holds it once, for every frame; without it, Pillow wrote
    # the same colours again before six of the seven frames.
    drawn[0].save(buf, format="GIF", save_all=True, append_images=drawn[1:], duration=ms,
                  loop=0, optimize=False, disposal=1,
                  palette=bytes(palette.getpalette()[:colours * 3]))
    return buf.getvalue()


def _node_env() -> dict:
    env = dict(os.environ)
    paths = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            out = subprocess.run([npm, "root", "-g"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=60)
            if out.returncode == 0 and out.stdout.strip():
                paths.append(out.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    env["NODE_PATH"] = os.pathsep.join(paths)
    return env


def take(root: str = ROOT) -> dict:
    """{shot name: picture} for every one in SHOTS, from the sample page in a real browser.
    Raises SystemExit with one plain line when Node or Playwright is missing, or the browser
    fails twice."""
    node = shutil.which("node")
    env = _node_env()
    if not node or subprocess.run([node, "-e", "require('playwright')"], env=env,
                                  capture_output=True).returncode:
        raise SystemExit("readme_pictures: taking the pictures needs Node and Playwright with "
                         "its Chromium. Install them with: npm install -g playwright, then "
                         "npx playwright install chromium")
    sys.path[:0] = [os.path.join(root, "tools"), os.path.join(root, "templates", "app")]
    import app_page
    with open(os.path.join(root, SAMPLE), encoding="utf-8") as fh:
        model = json.load(fh)
    with tempfile.TemporaryDirectory(prefix="ljs-readme-") as tmp:
        html = os.path.join(tmp, "sample.html")
        with open(html, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(app_page.standalone(app_page.render(model)))
        env["LJS_SHOTS"] = os.path.join(tmp, "shots")
        ask = json.dumps({"id": 1, "scenario": "shots", "args": {"html": html, "list": SHOTS}})
        # Twice at most: Chromium on a busy computer once failed one screenshot of the eleven
        # ("Unable to capture screenshot") and took them all on the next run.
        for attempt in (1, 2):
            try:
                r = subprocess.run([node, os.path.join(root, HARNESS)], input=ask + "\n",
                                   env=env, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=900)
            except subprocess.TimeoutExpired:
                raise SystemExit("readme_pictures: the browser took over 15 minutes and was "
                                 "stopped, so nothing was changed.") from None
            answers = [json.loads(ln) for ln in r.stdout.splitlines() if ln.startswith("{")]
            got = next((a for a in answers if a.get("id") == 1), None)
            if got and got.get("ok"):
                break
            why = (got or {}).get("error") or next(
                (a.get("error") for a in answers if a.get("ready") is False), "") or r.stderr
            why = str(why).strip().splitlines()[0][:300] if str(why).strip() else ""
            if attempt == 2:
                raise SystemExit("readme_pictures: the browser could not take the pictures, so "
                                 "nothing was changed." + (f" It said: {why}" if why else ""))
        from PIL import Image
        out = {}
        for s, path in zip(SHOTS, got["result"]):
            with Image.open(path) as im:
                out[s["name"]] = im.convert("RGB")
        return out


def shoot(root: str = ROOT, taker=take) -> int:
    """Take the four pictures, compose them, save each under its plain name in docs/images
    and name them after themselves. 0 when done; 1, changing nothing, with one plain line
    when something is missing or the tour is too big."""
    if _image_module() is None:
        return 1
    try:
        got = taker(root)
    except SystemExit as e:
        print(e.code if isinstance(e.code, str) else "readme_pictures: nothing was changed.")
        return 1
    made = {BRIEF: compose_brief(got["brief-light"], got["brief-dark"], (1600, 900)),
            CONTACTS: fit(got["contacts"], (1600, 1000)),
            PHONE: fit(got["phone"], (780, 1688))}
    tour = tour_gif([got[f"tour-{i}-{screen}"] for i, screen in enumerate(TOUR_SCREENS)])
    if len(tour) >= TOUR_MAX:
        print(f"readme_pictures: the tour came to {len(tour) // 1000} KB, over the "
              f"{TOUR_MAX // 1000} KB a README picture may be, so no picture was changed.")
        return 1
    folder = os.path.join(root, IMAGES)
    os.makedirs(folder, exist_ok=True)
    before = {name for name, _stem, h, _ext in _pictures(root) if h}
    for name, img in made.items():
        img.save(os.path.join(folder, name), format="PNG", optimize=True)
    with open(os.path.join(folder, TOUR), "wb") as fh:
        fh.write(tour)
    moved = rename(root)
    changed = [n for n in (BRIEF, CONTACTS, PHONE, TOUR) if moved.get(n) not in before]
    for name in changed:
        print(f"readme_pictures: {name} is new, as {moved[name]}")
    print(f"readme_pictures: {len(changed)} of the 4 pictures changed. Look at each before it "
          f"is committed: no banner, no error, invented names only.")
    return 0


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="readme_pictures.py", description=(
        "Name each README picture in docs/images after its contents and point the README at "
        "it. Run it after remaking a picture saved under its plain name, or say `shoot` to "
        "take the four pictures afresh from the sample page first."))
    ap.add_argument("what", nargs="?", choices=["shoot"],
                    help="shoot: take the four pictures from the sample page, then name them")
    ap.add_argument("--check", action="store_true",
                    help="change nothing; exit 1 when a picture or the README is out of step")
    args = ap.parse_args(argv)
    if args.what == "shoot":
        return shoot()
    if args.check:
        found = problems()
        print("\n".join(found) if found else "readme_pictures: every picture is named after itself")
        return 1 if found else 0
    for old, new in rename().items():
        print(f"readme_pictures: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
