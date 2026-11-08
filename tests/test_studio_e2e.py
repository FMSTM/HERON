"""Студия в настоящем браузере (ST8): Chromium через Playwright.

Сценарий новичка на сайте ru/en/de: открыть студию по адресу с ключом, поправить
одно поле страницы (в файле меняется только эта строка, остальные языки - байт в
байт), создать страницу на трёх языках с пропущенным de (пометка перевода),
загрузить картинку в media/, открыть справку темы. Консоль браузера чиста: CSP
`script-src 'self'` ничего не блокирует, ошибок скриптов нет.

Браузер ведёт tests/studio_e2e_driver.py отдельным процессом - тем Python, у
которого есть Playwright. Нет Playwright или Chromium - тест пропускается.
Снимки экрана - в папку из HERON_E2E_SHOTS, если она задана.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.scaffold import create
from heron.setup import server
from tests.test_setup_access import _free_port, _stop

DRIVER = Path(__file__).with_name("studio_e2e_driver.py")
LANGS = ["ru", "en", "de"]


def _python() -> str | None:
    """Интерпретатор с Playwright: HERON_E2E_PYTHON, тот же, что у тестов, иначе системный."""
    candidates = [
        os.environ.get("HERON_E2E_PYTHON"),
        sys.executable,
        shutil.which("python3"),
        shutil.which("python3", path=os.defpath),
        "/usr/local/bin/python3",
    ]
    for candidate in dict.fromkeys(candidates):
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run(
            [candidate, "-c", "import playwright.sync_api"], capture_output=True, check=False
        )
        if probe.returncode == 0:
            return candidate
    return None


def _front(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def test_studio_in_a_browser(tmp_path, monkeypatch):
    python = _python()
    if python is None:
        pytest.skip("нет Playwright для Python: e2e студии пропущен")
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "site"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    before = {lang: (root / "content" / lang / "blocks.md").read_bytes() for lang in LANGS}
    picture = tmp_path / "team.png"
    Image.new("RGB", (1600, 900), (40, 90, 160)).save(picture)

    port = _free_port()
    box: dict[str, str] = {}
    ready = threading.Event()

    def on_ready(token: str) -> None:
        box["token"] = token
        ready.set()

    thread = threading.Thread(
        target=server.run,
        args=(root, "127.0.0.1", port),
        kwargs={"on_ready": on_ready, "start": {"tab": "pages"}},
        daemon=True,
    )
    thread.start()
    assert ready.wait(10)
    shots = os.environ.get("HERON_E2E_SHOTS", "")
    try:
        done = subprocess.run(
            [python, str(DRIVER), f"http://localhost:{port}/#{box['token']}", str(picture), shots],
            capture_output=True,
            text=True,
            timeout=540,
            check=False,
        )
    finally:
        _stop(port, box["token"], thread)
    if done.returncode == 77:
        pytest.skip("Chromium для Playwright не запускается: e2e студии пропущен")
    assert done.returncode == 0, done.stdout + done.stderr
    result = json.loads(done.stdout.strip().splitlines()[-1])

    # консоль чиста: ни ошибок скриптов, ни отказов CSP. Предупреждение Chromium про
    # allow-scripts + allow-same-origin относится к рамке своего источника; рамка студии -
    # другой источник (порт просмотра), снять с себя песочницу ей нечем.
    console = [m for m in result["console"] if "can escape its sandboxing" not in m]
    assert console == [], console

    # 1. правка одного поля: в файле поменялась только строка title, другие языки те же
    old = before["ru"].decode("utf-8").splitlines(keepends=True)
    new = (root / "content" / "ru" / "blocks.md").read_text("utf-8").splitlines(keepends=True)
    assert len(old) == len(new)
    changed = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
    assert len(changed) == 1 and changed[0][0].startswith("title:"), changed
    assert "правка из студии" in changed[0][1]
    for lang in LANGS[1:]:
        assert (root / "content" / lang / "blocks.md").read_bytes() == before[lang]
    assert "content/ru/blocks.md" in result["edit"]

    # 2. страница на трёх языках: de пропущен - пометка, en переведён - без неё
    made = [root / "content" / lang / "about-team.md" for lang in LANGS]
    assert all(path.is_file() for path in made), result["create"]
    assert _front(made[1])["h1"] == "About the team"
    assert _front(made[1]).get("translation") is None
    assert _front(made[2])["translation"] == "pending"
    assert _front(made[0]).get("translation") is None

    # 3. картинка легла в media/, обложка и подпись записаны в основной язык
    assert (root / "media" / "team.png").is_file()
    data = _front(made[0])
    assert data["image"] == "media/team.png" and data["image_alt"] == "Команда за работой"
    assert "content/ru/about-team.md" in result["upload"]


# Скрипт темы, который пытается украсть ключ студии и записать страницу (приёмка 0.3.0,
# блокер 2). Студия - на порту P, просмотр со скриптами темы - на P + 1.
ATTACK = (Path(__file__).parent / "fixtures" / "studio_attack.js").read_text("utf-8")


def test_theme_script_in_the_preview_cannot_reach_the_studio(tmp_path, monkeypatch):
    python = _python()
    if python is None:
        pytest.skip("нет Playwright для Python: e2e студии пропущен")
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "site"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    script = root / "theme" / "assets" / "site.js"
    script.write_text(script.read_text("utf-8") + ATTACK, encoding="utf-8")
    before = {lang: (root / "content" / lang / "blocks.md").read_bytes() for lang in LANGS}

    port = _free_port()
    box: dict[str, str] = {}
    ready = threading.Event()

    def on_ready(token: str) -> None:
        box["token"] = token
        ready.set()

    thread = threading.Thread(
        target=server.run,
        args=(root, "127.0.0.1", port),
        kwargs={"on_ready": on_ready, "start": {"tab": "pages"}},
        daemon=True,
    )
    thread.start()
    assert ready.wait(10)
    try:
        done = subprocess.run(
            [python, str(DRIVER), "attack", f"http://localhost:{port}/#{box['token']}"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    finally:
        _stop(port, box["token"], thread)
    if done.returncode == 77:
        pytest.skip("Chromium для Playwright не запускается: e2e студии пропущен")
    assert done.returncode == 0, done.stdout + done.stderr
    result = json.loads(done.stdout.strip().splitlines()[-1])
    # файлы не тронуты: ни одной записи из скрипта темы
    for lang in LANGS:
        assert (root / "content" / lang / "blocks.md").read_bytes() == before[lang]
    # скрипт темы отработал, но ключа не увидел и наверх не ушёл
    probe = " ".join(result["frames"])
    assert "probe" in probe, result
    assert box["token"] not in probe and "save:200" not in probe, result
    assert "hash-blocked" in probe and "top-blocked" in probe, result
    assert result["top"].split("#")[0] == result["address"].split("#")[0]
    # ключ убран из адресной строки сразу после чтения
    assert "#" not in result["address"] and box["token"] not in result["top"]
    # рамка - другой источник и в песочнице без выхода наверх
    assert all(url.startswith(f"http://localhost:{port + 1}/") for url in result["frame_urls"])
    assert result["sandbox"] and "allow-top-navigation" not in result["sandbox"][0]
