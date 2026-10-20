"""Темы: стартовая, свой архив, недоверчивая распаковка, демо без перезаписи.

Спецификация: docs/spec/21-engine.md, «heron theme».
"""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core.errors import HeronError
from heron.scaffold import create
from heron.themes import install, pack


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en", "de"])
    return root


def _tar(entries: dict[str, bytes]) -> bytes:
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return blob.getvalue()


def test_starter_theme_with_demo_on_every_language(site: Path):
    (site / "content" / "en" / "index.md").write_text("mine", encoding="utf-8")
    result = install(site, "starter", languages=["en", "de"])
    assert result.name == "starter"
    assert (site / "theme" / "modules" / "tabs.html").is_file()
    assert (site / "content" / "de" / "forms.md").is_file()
    # своя страница не тронута, прежняя тема — в резервной копии
    assert (site / "content" / "en" / "index.md").read_text(encoding="utf-8") == "mine"
    assert result.backup.startswith(".heron-cache/setup/theme.")


def test_pack_and_get_roundtrip(site: Path, tmp_path: Path):
    archive = pack(site, tmp_path / "t.tar.gz")
    other = tmp_path / "other"
    create(other, name="Other", languages=["fr"])
    result = install(other, "file", str(archive), languages=["fr"])
    assert (other / "theme" / "theme.yaml").is_file()
    assert result.name


@pytest.mark.parametrize(
    "entries, problem",
    [
        ({"../evil": b"x"}, "leaves"),
        ({"theme/plugins/x.html": b"x"}, "build code"),
        ({"theme/run.sh": b"x"}, "scripts"),
        ({"readme.txt": b"x"}, "no theme/"),
    ],
)
def test_archive_is_checked(site: Path, tmp_path: Path, entries, problem):
    path = tmp_path / "bad.tgz"
    path.write_bytes(_tar(entries))
    with pytest.raises(HeronError, match=problem):
        install(site, "file", str(path))
    assert (site / "theme" / "theme.yaml").is_file()  # тема сайта цела


def test_zip_with_symlink_is_refused(site: Path, tmp_path: Path):
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        info = zipfile.ZipInfo("theme/link")
        info.external_attr = (0o120777) << 16
        archive.writestr(info, "/etc/passwd")
    path = tmp_path / "link.zip"
    path.write_bytes(blob.getvalue())
    with pytest.raises(HeronError, match="link"):
        install(site, "file", str(path))


def test_checksum_from_link_is_verified(site: Path, monkeypatch):
    from heron import themes

    blob = _tar({"theme/theme.yaml": b"name: x\n"})
    monkeypatch.setattr(themes, "_download", lambda url: blob)
    with pytest.raises(HeronError, match="checksum"):
        install(site, "url", "https://example.com/t.tgz#sha256=" + "0" * 64)


def test_cli_theme_get_starter(site: Path):
    done = CliRunner().invoke(main, ["theme", "get", "starter", str(site)])
    assert done.exit_code == 0, done.output
    assert "theme: starter" in (site / "site.yaml").read_text(encoding="utf-8")
