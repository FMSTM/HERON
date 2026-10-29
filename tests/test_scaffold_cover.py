"""Заготовка `heron new` несёт обложку по умолчанию: check --strict без предупреждений."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from PIL import Image

from heron.cli import main
from heron.scaffold import create


@pytest.mark.parametrize("demo", [True, False])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_fresh_site_passes_strict_check(tmp_path: Path, lang: str, demo: bool) -> None:
    root = tmp_path / "s"
    create(root, name="S", languages=[lang], demo=demo)

    config = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    cover = root / config["seo"]["og_default_image"]
    assert cover.is_file()
    with Image.open(cover) as image:
        assert image.width >= 1200
        assert image.mode == "RGB"

    result = CliRunner().invoke(main, ["check", str(root), "--strict", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"] is True
    assert "pages_without_cover" not in result.output


@pytest.mark.parametrize("args", [["init"], ["init", "--force"]])
def test_init_keeps_users_own_cover(tmp_path: Path, args: list[str]) -> None:
    root = tmp_path / "s"
    create(root, name="S", languages=["ru"], demo=False)
    own = b"users own cover, not a png"
    (root / "media" / "cover.png").write_bytes(own)
    (root / "media" / "mine.png").write_bytes(b"x")
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())

    result = CliRunner().invoke(main, [args[0], str(root), *args[1:]])
    assert result.exit_code == 0, result.output

    assert (root / "media" / "cover.png").read_bytes() == own
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert [f for f in after if f not in before and f.startswith("media/")] == []


def test_init_does_not_add_cover_to_foreign_site(tmp_path: Path) -> None:
    root = tmp_path / "s"
    create(root, name="S", languages=["ru"], demo=False)
    (root / "media" / "cover.png").unlink()
    result = CliRunner().invoke(main, ["init", str(root)])
    assert result.exit_code == 0, result.output
    assert not (root / "media" / "cover.png").exists()
