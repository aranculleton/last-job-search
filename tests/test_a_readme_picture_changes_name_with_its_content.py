"""A README picture is named after its own contents, so a new one never shows up as an old one.

On 2026-11-04 the Brief's picture in the README, tapped open in GitHub's phone app, showed a
picture two versions old: the file kept one name across versions and an old copy was served
under it. tools/readme_pictures.py names each picture after its hash; these hold it.
"""
from __future__ import annotations

import os

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
