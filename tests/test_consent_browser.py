"""Счётчики белой темы — только после согласия: проверка в настоящем браузере.

Сайт собирается как прод со всеми тремя счётчиками и отдаётся локальным
HTTP-сервером. Запросы к счётчикам перехватываются и записываются, в сеть
ничего не уходит. Проверяется: до выбора — ни одного запроса и ни одного
скрипта; отказ — ни одного и после перезагрузки; согласие — все три, и на
следующей загрузке без плашки.
"""

from __future__ import annotations

import functools
import http.server
import os
import threading
from pathlib import Path

import pytest
import yaml

from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create

COUNTERS = ("googletagmanager.com/gtm.js", "googletagmanager.com/gtag/js", "mc.yandex.ru/metrika")


def _sync_api():
    if os.environ.get("HERON_REQUIRE_BROWSER"):
        import playwright.sync_api as sync_api

        return sync_api
    return pytest.importorskip("playwright.sync_api")


def _built(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    data = yaml.safe_load((root / "site.yaml").read_text("utf-8"))
    data["analytics"] = {"ga4": "G-TEST000001", "gtm": "GTM-TEST001", "metrika": 10000001}
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [e.message for e in result.collector.errors]
    return root / "dist"


def test_counters_absent_from_html_before_consent(tmp_path):
    html = (_built(tmp_path) / "index.html").read_text("utf-8")
    assert '<script async src="https://www.googletagmanager' not in html
    assert "data-consent" in html and "G-TEST000001" in html  # номер — данными


def test_browser_consent_gates_counters(tmp_path):
    sync_api = _sync_api()
    dist = _built(tmp_path)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(dist))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    seen: list[str] = []

    def intercept(route):
        url = route.request.url
        if any(part in url for part in COUNTERS):
            seen.append(url)
            route.fulfill(status=200, content_type="text/javascript", body="")
        elif url.startswith(base):
            route.continue_()
        else:
            route.abort()

    def scripts(page) -> int:
        return page.evaluate(
            "[...document.scripts].filter(s => /googletagmanager|mc\\.yandex/.test(s.src)).length"
        )

    try:
        with sync_api.sync_playwright() as play:
            browser = play.chromium.launch()
            try:
                # отказ
                context = browser.new_context()
                context.route("**/*", intercept)
                page = context.new_page()
                page.goto(base, wait_until="networkidle")
                assert page.locator("[data-consent]").is_visible()
                assert seen == [] and scripts(page) == 0
                page.click("[data-consent-decline]")
                assert not page.locator("[data-consent]").is_visible()
                page.reload(wait_until="networkidle")
                assert not page.locator("[data-consent]").is_visible()
                assert seen == [] and scripts(page) == 0
                # передумать можно из подвала
                page.click("[data-consent-open]")
                assert page.locator("[data-consent]").is_visible()
                context.close()

                # согласие
                context = browser.new_context()
                context.route("**/*", intercept)
                page = context.new_page()
                page.goto(base, wait_until="networkidle")
                assert seen == []
                page.click("[data-consent-accept]")
                page.wait_for_load_state("networkidle")
                assert not page.locator("[data-consent]").is_visible()
                assert all(any(part in url for url in seen) for part in COUNTERS), seen
                assert scripts(page) == 3
                seen.clear()
                page.reload(wait_until="networkidle")
                assert not page.locator("[data-consent]").is_visible()
                assert all(any(part in url for url in seen) for part in COUNTERS), seen
                assert "id=G-TEST000001" in " ".join(seen)
                context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
