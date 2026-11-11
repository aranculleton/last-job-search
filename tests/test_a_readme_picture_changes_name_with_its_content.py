"""A README picture is named after its own contents, so a new one never shows up as an old one.

On 2026-11-04 the Brief's picture in the README, tapped open in GitHub's phone app, showed a
picture two versions old: the file kept one name across versions and an old copy was served
under it. tools/readme_pictures.py names each picture after its hash; these hold it.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

from tools import readme_pictures as rp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _repo(tmp_path, pictures: dict[str, bytes], readme: str):
    folder = tmp_path / "docs" / "images"
    folder.mkdir(parents=True)
    for name, data in pictures.items():
        (folder / name).write_bytes(data)
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    return str(tmp_path)


def test_the_apps_own_pictures_are_named_after_themselves():
    assert rp.problems(ROOT) == []


def test_a_remade_picture_gets_a_new_name_and_the_readme_follows(tmp_path):
    root = _repo(tmp_path, {"page-brief.png": b"first"},
                 '<img src="docs/images/page-brief.png" width="720">\n')
    assert rp.problems(root)
    rp.rename(root)
    first = os.listdir(os.path.join(root, "docs", "images"))
    assert len(first) == 1 and first[0].startswith("page-brief-") and first[0] != "page-brief.png"
    assert f"docs/images/{first[0]}" in open(os.path.join(root, "README.md")).read()
    assert rp.problems(root) == []

    # Remade under its plain name: the old one goes, the new one gets a different address.
    with open(os.path.join(root, "docs", "images", "page-brief.png"), "wb") as fh:
        fh.write(b"second")
    rp.rename(root)
    second = os.listdir(os.path.join(root, "docs", "images"))
    assert len(second) == 1 and second[0] != first[0]
    text = open(os.path.join(root, "README.md")).read()
    assert f"docs/images/{second[0]}" in text and first[0] not in text
    assert rp.problems(root) == []


def test_a_picture_changed_in_place_is_caught(tmp_path):
    root = _repo(tmp_path, {"page-demo.gif": b"tour"}, "![tour](docs/images/page-demo.gif)\n")
    rp.rename(root)
    (name,) = os.listdir(os.path.join(root, "docs", "images"))
    with open(os.path.join(root, "docs", "images", name), "wb") as fh:
        fh.write(b"a newer tour")
    assert any("should be named" in p for p in rp.problems(root))


def test_a_missing_or_unused_picture_is_caught(tmp_path):
    root = _repo(tmp_path, {"spare-0badc0de.png": b"x"}, '<img src="docs/images/gone-12345678.png">\n')
    found = rp.problems(root)
    assert any("gone-12345678.png, which is not there" in p for p in found)
    assert any("is in no README line" in p for p in found)


# ------------------------------------------------------------------ taking them (shoot)

# The four pictures were taken by hand to a ten-line description of sizes and a diagonal (the
# release audit, 2026-11-11). `readme_pictures.py shoot` takes them with the page's browser
# harness and composes them; what needs no browser is held here, on pictures made in the test.


def _gif_tables(data: bytes) -> tuple[bool, int]:
    """(whether the GIF has one colour table for all its frames, how many frames carry their
    own), read from the file's blocks."""
    flags = data[10]
    at = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    own = 0
    while at < len(data) and data[at] != 0x3B:
        if data[at] == 0x21:                                   # an extension: skip its blocks
            at += 2
        else:                                                  # a frame
            f = data[at + 9]
            own += bool(f & 0x80)
            at += 10 + (3 * 2 ** ((f & 7) + 1) if f & 0x80 else 0) + 1
        while data[at]:
            at += data[at] + 1
        at += 1
    return bool(flags & 0x80), own


def _flat(Image, colour, size):
    return Image.new("RGB", size, colour)


def _screens(Image, size=(1600, 1000)):
    """Seven made-up screens: a pale page with a coloured band and a block that moves."""
    from PIL import ImageDraw
    out = []
    for i in range(7):
        im = Image.new("RGB", size, (246, 244, 240))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, size[0] // 8, size[1]], fill=(60 + 20 * i, 50, 90))
        d.rectangle([300 + 80 * i, 200, 700 + 80 * i, 500], fill=(230, 120 + 10 * i, 110))
        out.append(im)
    return out


def test_the_brief_is_light_above_the_diagonal_and_dark_below_it():
    Image = pytest.importorskip("PIL.Image")
    light = _flat(Image, (255, 255, 255), (3200, 1800))
    dark = _flat(Image, (0, 0, 0), (3200, 1800))
    out = rp.compose_brief(light, dark, (1600, 900))
    assert out.size == (1600, 900) and out.mode == "RGB"
    white, black = (255, 255, 255), (0, 0, 0)
    # From 61% across the top (976 of 1600) to 44% across the bottom (704).
    for (x, y), want in {(960, 1): white, (992, 1): black, (688, 898): white, (720, 898): black,
                         (824, 450): white, (856, 450): black, (5, 5): white,
                         (1595, 895): black, (1595, 5): black, (5, 895): white}.items():
        assert out.getpixel((x, y)) == want, (x, y, out.getpixel((x, y)))
    # The cut is drawn at the size taken, so it is smooth once scaled: grey at the edge.
    assert 0 < out.getpixel((840, 450))[0] < 255


def test_each_picture_is_scaled_to_its_own_size():
    Image = pytest.importorskip("PIL.Image")
    assert rp.fit(_flat(Image, (1, 2, 3), (3200, 2000)), (1600, 1000)).size == (1600, 1000)
    phone = rp.fit(Image.new("RGBA", (1170, 2532), (9, 9, 9, 255)), (780, 1688))
    assert phone.size == (780, 1688) and phone.mode == "RGB"
    assert [s["scale"] for s in rp.SHOTS if s["name"] == "phone"] == [3]
    assert all(s["scale"] == 2 for s in rp.SHOTS if s["name"] != "phone")
    # The Brief shows the sample's running search; Contacts and the tour show no work.
    seeded = {s["name"]: s.get("seed", True) is not False for s in rp.SHOTS}
    assert seeded["brief-light"] and seeded["brief-dark"] and not seeded["contacts"]
    assert [s["hash"] for s in rp.SHOTS if s["name"].startswith("tour-")] == [
        "brief", "todo", "jobs", "contacts", "interviews", "chat", "settings"]


def test_the_tour_is_seven_screens_in_one_palette_a_frame_every_1_6_seconds():
    Image = pytest.importorskip("PIL.Image")
    data = rp.tour_gif([im.resize((3200, 2000)) for im in _screens(Image)])
    assert len(data) < rp.TOUR_MAX
    gif = Image.open(io.BytesIO(data))
    assert gif.size == (1600, 1000) and gif.n_frames == 7 and gif.info.get("loop") == 0
    used = set()
    for i in range(7):
        gif.seek(i)
        assert gif.info["duration"] == 1600
        used |= {c for _, c in gif.convert("RGB").getcolors(maxcolors=1 << 16)}
    assert len(used) <= 96
    assert _gif_tables(data) == (True, 0)        # one palette, written once, for every frame


def _shoot_repo(tmp_path):
    root = _repo(tmp_path, {"page-brief-light-dark-0badc0de.png": b"a",
                            "page-contacts-0badc0de.png": b"b",
                            "page-coming-up-phone-0badc0de.png": b"c",
                            "page-demo-0badc0de.gif": b"d"},
                 '<img src="docs/images/page-brief-light-dark-0badc0de.png">\n'
                 '<img src="docs/images/page-demo-0badc0de.gif">\n'
                 '<img src="docs/images/page-contacts-0badc0de.png">\n'
                 '<img src="docs/images/page-coming-up-phone-0badc0de.png">\n')
    return root


def _taken(Image, tour):
    shots = {"brief-light": _flat(Image, (250, 250, 250), (3200, 1800)),
             "brief-dark": _flat(Image, (20, 20, 30), (3200, 1800)),
             "contacts": _flat(Image, (240, 240, 240), (3200, 2000)),
             "phone": _flat(Image, (245, 245, 245), (1170, 2532))}
    shots.update({f"tour-{i}-{s}": tour[i] for i, s in enumerate(rp.TOUR_SCREENS)})
    return lambda root: shots


def test_shoot_saves_the_four_pictures_named_after_themselves_or_refuses_a_tour_too_big(
        tmp_path, capsys):
    Image = pytest.importorskip("PIL.Image")
    root = _shoot_repo(tmp_path / "big")
    folder = os.path.join(root, "docs", "images")
    before = {n: open(os.path.join(folder, n), "rb").read() for n in os.listdir(folder)}
    readme = open(os.path.join(root, "README.md")).read()
    noise = [Image.effect_noise((1600, 1000), 120).convert("RGB") for _ in range(7)]
    assert rp.shoot(root, taker=_taken(Image, noise)) == 1
    said = capsys.readouterr().out
    assert "over the 700 KB a README picture may be, so no picture was changed" in said
    assert {n: open(os.path.join(folder, n), "rb").read() for n in os.listdir(folder)} == before
    assert open(os.path.join(root, "README.md")).read() == readme

    root = _shoot_repo(tmp_path / "fine")
    assert rp.shoot(root, taker=_taken(Image, _screens(Image))) == 0
    assert "4 of the 4 pictures changed" in capsys.readouterr().out
    assert rp.problems(root) == []
    sizes = {}
    for name in os.listdir(os.path.join(root, "docs", "images")):
        assert "0badc0de" not in name
        with Image.open(os.path.join(root, "docs", "images", name)) as im:
            sizes[rp.NAME.match(name)["stem"]] = im.size
    assert sizes == {"page-brief-light-dark": (1600, 900), "page-contacts": (1600, 1000),
                     "page-coming-up-phone": (780, 1688), "page-demo": (1600, 1000)}


def test_shoot_says_how_to_get_what_it_needs(tmp_path, monkeypatch, capsys):
    root = _shoot_repo(tmp_path)
    monkeypatch.setitem(sys.modules, "PIL", None)
    assert rp.shoot(root, taker=lambda r: pytest.fail("no picture without Pillow")) == 1
    assert "python3 -m pip install Pillow" in capsys.readouterr().out
    monkeypatch.setattr(rp.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as no_node:
        rp.take(root)
    assert "npm install -g playwright" in str(no_node.value.code)
    assert sorted(os.listdir(os.path.join(root, "docs", "images"))) == [
        "page-brief-light-dark-0badc0de.png", "page-coming-up-phone-0badc0de.png",
        "page-contacts-0badc0de.png", "page-demo-0badc0de.gif"]
