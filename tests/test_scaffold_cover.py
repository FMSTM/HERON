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
