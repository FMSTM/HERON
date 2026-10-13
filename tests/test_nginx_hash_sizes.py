"""Размеры хэшей карт nginx считает движок, а не процессор.

По умолчанию map_hash_bucket_size равен кэш-линии процессора — обычно 64
байта. Длинный кириллический адрес из redirect_from (2 байта на букву) в
такую корзину не помещается, и nginx не стартует: «could not build
map_hash, you should increase map_hash_bucket_size: 64». В образе с другой
сборкой nginx тот же конфиг работал — запустится он или нет, решало железо.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from heron.core import build as pipeline
from heron.modules import nginx
from heron.scaffold import create


def cyrillic(size: int) -> str:
    """Ключ ровно `size` байт: «/» и кириллица по 2 байта."""
    key = "/" + "ж" * ((size - 1) // 2)
    return key + "a" * (size - len(key.encode("utf-8")))


@pytest.mark.parametrize(("size", "bucket"), [(30, 64), (72, 128), (150, 256)])
def test_bucket_follows_the_longest_key(size, bucket):
    keys = [cyrillic(size), "/short/"]
    assert len(cyrillic(size).encode("utf-8")) == size
    found = nginx.hash_sizes(keys)
    assert found.bucket == bucket
    assert found.longest == size


def test_key_near_the_border_gets_the_next_bucket():
    # 8 + 2 + 44 → 56 → +8 = 64: впритык к 64, берём 128
    assert nginx.hash_sizes([cyrillic(44)]).bucket == 128


def test_max_size_grows_with_the_number_of_keys():
    assert nginx.hash_sizes(["/a/"] * 10).max_size == 2048
    assert nginx.hash_sizes(["/a/"] * 1500).max_size == 4096


def site_with_redirects(tmp_path: Path, mode: str | None = None) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    olds = [f"/{'старая-страница-с-длинным-адресом-' * 2}{index}/" for index in range(40)]
    (root / "content" / "en" / "about.md").write_text(
        "---\ntitle: A\nh1: A\ndescription: D\nredirect_from:\n"
        + "".join(f"  - {old}\n" for old in olds)
        + "---\n\nText.\n",
        encoding="utf-8",
    )
    if mode:
        path = root / "site.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["nginx"] = {"hash_sizes": mode}
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


def test_directives_stand_before_the_first_map(tmp_path):
    root = site_with_redirects(tmp_path)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert conf.index("map_hash_bucket_size") < conf.index("map $uri")
    assert conf.index("map_hash_max_size") < conf.index("server {")
    assert "# HERON: самый длинный ключ карт" in conf
    assert "map_hash_bucket_size 256;" in conf


def test_report_shows_the_numbers(tmp_path):
    root = site_with_redirects(tmp_path)
    result = pipeline.run(root)
    text = result.report.render()
    assert "map_hash_bucket_size 256" in text
    assert "самый длинный ключ" in text


def test_off_writes_nothing_and_says_what_the_host_needs(tmp_path):
    root = site_with_redirects(tmp_path, mode="off")
    result = pipeline.run(root)
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert "map_hash_bucket_size" not in conf
    assert "проверьте nginx.conf хоста" in result.report.render()
    assert "≥ 256" in result.report.render()


def test_site_without_maps_gets_no_directives(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    pipeline.run(root)
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert "map_hash" not in conf


@pytest.mark.skipif(shutil.which("nginx") is None, reason="нет nginx в PATH")
def test_real_nginx_accepts_the_config(tmp_path):
    """На машине с кэш-линией 64 без директив этот конфиг не стартует."""
    root = site_with_redirects(tmp_path)
    result = pipeline.run(root)
    assert result.report.nginx_test is not None
    passed, output = result.report.nginx_test
    assert passed, output

    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    stripped = "\n".join(line for line in conf.splitlines() if not line.startswith("map_hash"))
    passed, output = nginx.check(stripped)
    if not passed:  # процессор с кэш-линией 64: ровно та поломка, что в задаче
        assert "map_hash_bucket_size" in output
