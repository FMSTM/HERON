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
    assert (site / "content" / "de" / "blocks.md").is_file()
    # своя страница не тронута, прежняя тема — в резервной копии
    assert (site / "content" / "en" / "index.md").read_text(encoding="utf-8") == "mine"
    assert result.backup.startswith(".heron-cache/setup/theme.")


def test_pack_and_get_roundtrip(site: Path, tmp_path: Path):
    archive = pack(site, tmp_path / "t.tar.gz")
    other = tmp_path / "other"
    create(other, name="Other", languages=["fr"])
    result = install(other, "file", archive=archive, languages=["fr"])
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
        install(site, "file", archive=path)
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
        install(site, "file", archive=path)


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


def _damaged() -> dict[str, bytes]:
    good = _tar({"theme/theme.yaml": b"name: x\n" + b"y" * 20000})
    return {
        "zip header only": b"PK\x03\x04" + b"\x00" * 100,
        "truncated tar.gz": good[: len(good) // 2],
        "corrupt gzip body": good[:20] + bytes(b ^ 0xFF for b in good[20:60]) + good[60:],
    }


@pytest.mark.parametrize("kind", ["zip header only", "truncated tar.gz", "corrupt gzip body"])
def test_damaged_archive_is_e032(kind: str):
    from heron import themes

    with pytest.raises(HeronError) as exc:
        themes._members(_damaged()[kind])
    assert exc.value.code == "E032"
    if kind != "corrupt gzip body":  # заголовок битый — «не архив темы», тоже E032
        assert "damaged or truncated" in str(exc.value)


def test_install_of_damaged_zip_is_e032_and_theme_stays(site: Path, tmp_path: Path):
    path = tmp_path / "bad.zip"
    path.write_bytes(_damaged()["zip header only"])
    with pytest.raises(HeronError) as exc:
        install(site, "file", archive=path)
    assert exc.value.code == "E032"
    assert (site / "theme" / "theme.yaml").is_file()


def test_damaged_zip_member_data_is_e032():
    from heron import themes

    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("theme/theme.yaml", "name: x\n" * 5000)
    raw = bytearray(blob.getvalue())
    for i in range(40, 80):  # внутри сжатых данных первого файла
        raw[i] ^= 0xFF
    with pytest.raises(HeronError) as exc:
        themes._members(bytes(raw))
    assert exc.value.code == "E032"


def test_file_value_outside_site_is_refused(site: Path, tmp_path: Path):
    archive = pack(site, tmp_path / "out" / "t.tar.gz")
    before = (site / "theme" / "theme.yaml").read_bytes()
    with pytest.raises(HeronError) as raised:
        install(site, "file", str(archive))
    assert raised.value.code == "E024"
    assert (site / "theme" / "theme.yaml").read_bytes() == before
    assert not list((site / ".heron-cache").glob("setup/theme.*"))  # резервной копии нет


def test_file_value_dotdot_and_symlink_are_refused(site: Path, tmp_path: Path):
    archive = pack(site, tmp_path / "out" / "t.tar.gz")
    with pytest.raises(HeronError) as raised:
        install(site, "file", "../out/t.tar.gz")
    assert raised.value.code == "E024"
    (site / "themes").mkdir()
    (site / "themes" / "link.tar.gz").symlink_to(archive)
    with pytest.raises(HeronError) as raised:
        install(site, "file", "themes/link.tar.gz")
    assert raised.value.code == "E024"


def test_file_value_inside_site_installs(site: Path, tmp_path: Path):
    pack(site, site / "themes" / "t.tar.gz")
    other = tmp_path / "other"
    create(other, name="Other", languages=["fr"])
    (other / "themes").mkdir()
    (other / "themes" / "t.tar.gz").write_bytes((site / "themes" / "t.tar.gz").read_bytes())
    assert install(other, "file", "themes/t.tar.gz", languages=["fr"]).name


def test_theme_get_accepts_absolute_and_cwd_relative(site: Path, tmp_path: Path, monkeypatch):
    archive = pack(site, tmp_path / "out" / "t.tar.gz")
    other = tmp_path / "other"
    create(other, name="Other", languages=["fr"])
    runner = CliRunner()
    result = runner.invoke(main, ["theme", "get", str(archive), str(other)])
    assert result.exit_code == 0, result.output
    third = tmp_path / "third"
    create(third, name="Third", languages=["fr"])
    monkeypatch.chdir(archive.parent)
    result = runner.invoke(main, ["theme", "get", "t.tar.gz", str(third)])
    assert result.exit_code == 0, result.output
