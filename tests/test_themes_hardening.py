"""Загрузчик тем: перенаправления и пределы распаковки (аудит SEC-06).

Каждое перенаправление проверяется заново (https, хост из списка, предел
числа); распаковка считает реально прочитанные байты, а не заголовок,
ограничивает число записей и не пускает `..`, абсолютные пути и ссылки.
"""

from __future__ import annotations

import io
import tarfile
import urllib.request
import zipfile

import pytest

from heron import themes
from heron.core.errors import HeronError


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _tar(add) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        add(archive)
    return buffer.getvalue()


def _file(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


# --- перенаправления --------------------------------------------------------------------------


def _handler(url: str = "https://themes.example.org/t.zip") -> themes._Redirects:
    return themes._Redirects(themes._allowed_hosts(url))


@pytest.mark.parametrize(
    "target",
    [
        "http://themes.example.org/t.zip",
        "file:///etc/passwd",
        "https://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1/t.zip",
        "https://evil.example.net/t.zip",
        "ftp://themes.example.org/t.zip",
    ],
)
def test_redirect_to_other_scheme_or_host_is_refused(target):
    request = urllib.request.Request("https://themes.example.org/t.zip")
    with pytest.raises(HeronError) as raised:
        _handler().redirect_request(request, None, 302, "Found", {}, target)
    assert raised.value.code == "E032"
    assert "redirect" in raised.value.message.text("en")


def test_redirect_to_the_same_host_or_github_is_allowed():
    request = urllib.request.Request("https://themes.example.org/t.zip")
    for target in (
        "https://themes.example.org/v2/t.zip",
        "https://codeload.github.com/o/r/zip/refs/tags/v1",
        "/relative/t.zip",
    ):
        new = _handler().redirect_request(request, None, 302, "Found", {}, target)
        assert new is not None and new.full_url.startswith("https://")


def test_extra_hosts_come_from_the_environment(monkeypatch):
    monkeypatch.setenv(themes.HOSTS_ENV, "cdn.example.net, mirror.example.com")
    allowed = themes._allowed_hosts("https://themes.example.org/t.zip")
    assert {"cdn.example.net", "mirror.example.com", "themes.example.org"} <= allowed


def test_redirect_chain_is_limited():
    request = urllib.request.Request("https://themes.example.org/t.zip")
    request.redirect_dict = {f"https://themes.example.org/{i}": 1 for i in range(10)}
    headers = {"location": "https://themes.example.org/next"}
    with pytest.raises(HeronError) as raised:
        _handler().http_error_302(request, io.BytesIO(), 302, "Found", headers)
    assert str(themes.MAX_REDIRECTS) in raised.value.message.text("en")


def test_download_uses_the_checking_opener(monkeypatch):
    seen: list[set[str]] = []

    class Opener:
        def open(self, *_args, **_kwargs):
            raise HeronError(code="E032", message="stop")

    def opener(url):
        seen.append(themes._allowed_hosts(url))
        return Opener()

    monkeypatch.setattr(themes, "_opener", opener)
    with pytest.raises(HeronError):
        themes._download("https://themes.example.org/t.zip")
    assert seen and "themes.example.org" in seen[0]


# --- распаковка -------------------------------------------------------------------------------


def test_real_bytes_are_limited_not_the_header(monkeypatch):
    monkeypatch.setattr(themes, "MAX_FILE", 64)
    blob = _zip({"theme/theme.yaml": b"x" * 32})
    assert themes._members(blob)[0][1] == b"x" * 32

    # заголовок говорит «маленький», а данных больше: чтение всё равно ограничено
    forged = bytearray(_zip({"theme/big.css": b"y" * 1000}))
    real = (1000).to_bytes(4, "little")
    forged = forged.replace(real, (10).to_bytes(4, "little"))
    with pytest.raises(HeronError) as raised:
        themes._members(bytes(forged))
    assert raised.value.code == "E032"


def test_total_size_is_counted_from_read_bytes(monkeypatch):
    monkeypatch.setattr(themes, "MAX_TOTAL", 100)
    blob = _zip({f"theme/{i}.css": b"z" * 40 for i in range(3)})
    with pytest.raises(HeronError) as raised:
        themes._members(blob)
    assert "too large" in raised.value.message.text("en")


def test_number_of_entries_is_limited(monkeypatch):
    monkeypatch.setattr(themes, "MAX_ENTRIES", 3)
    blob = _zip({f"theme/{i}.css": b"a" for i in range(5)})
    with pytest.raises(HeronError):
        themes._members(blob)


def test_tar_entries_are_limited_too(monkeypatch):
    monkeypatch.setattr(themes, "MAX_FILE", 8)

    def add(archive):
        _file(archive, "theme/big.css", b"b" * 100)

    with pytest.raises(HeronError) as raised:
        themes._members(_tar(add))
    assert "larger than" in raised.value.message.text("en")


@pytest.mark.parametrize(
    "name", ["../evil.css", "theme/../../evil.css", "/etc/evil.css", "C:/evil.css"]
)
def test_paths_leaving_the_archive_are_refused(name):
    def add(archive):
        _file(archive, name, b"x")

    with pytest.raises(HeronError) as raised:
        themes._members(_tar(add))
    assert "leaves" in raised.value.message.text("en")


def test_symlinks_are_refused_in_tar_and_zip():
    def add(archive):
        link = tarfile.TarInfo("theme/link.css")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)

    with pytest.raises(HeronError) as raised:
        themes._members(_tar(add))
    assert "link" in raised.value.message.text("en")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("theme/link.css")
        info.external_attr = (0o120777 << 16) | 0
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(HeronError) as raised:
        themes._members(buffer.getvalue())
    assert "link" in raised.value.message.text("en")
