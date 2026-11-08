"""Браузер для e2e студии (tests/test_studio_e2e.py): Chromium через Playwright.

Запускается отдельным процессом тем интерпретатором Python, у которого есть
Playwright (у тестов его может не быть). Аргументы: адрес студии с ключом, файл
картинки для загрузки, папка для снимков экрана (или пусто). Печатает одну
строку JSON: сообщения консоли и ошибки страницы. Нет браузера - код выхода 77,
тест пропускается.
"""

from __future__ import annotations

import json
import sys

SKIP = 77


def attack(url: str) -> int:
    """Скрипт темы в рамке справки пробует украсть ключ и записать страницу (PWNED).

    Печатает адрес вкладки студии до и после попытки, песочницу рамки, адреса рамок
    и заголовки их страниц: скрипт темы пишет в заголовок, что ему удалось.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return SKIP
    with sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception:  # noqa: BLE001 - браузера нет или он не запускается
            return SKIP
        page = browser.new_context().new_page()
        page.goto(url)
        page.wait_for_selector("#tab-btn-ref", timeout=30000)
        address = page.url
        page.click("#tab-btn-ref")
        page.wait_for_selector('#st-ref-frame[src*="_heron/theme"]', timeout=60000)
        inside = page.frame_locator("#st-ref-frame")
        inside.locator("h1").wait_for(timeout=30000)
        # из справки - на страницу сайта, где работает скрипт темы (как переход по ссылке).
        # Студия может перерисовать рамку (язык страницы прочитан позже) - тогда ещё раз.
        for _ in range(4):
            try:
                ref = next(f for f in page.frames if f != page.main_frame)
                ref.goto(ref.url.split("/_heron/")[0].split("/blocks/")[0] + "/blocks/")
                ref.wait_for_function("() => document.title.startsWith('probe')", timeout=15000)
                break
            except Exception:  # noqa: BLE001 - рамку перерисовали, пробуем снова
                continue
        page.wait_for_timeout(1000)
        frames = [f for f in page.frames if f != page.main_frame]
        result = {
            "address": address,
            "top": page.url,
            "sandbox": page.evaluate(
                "() => [...document.querySelectorAll('iframe')]"
                ".map((f) => f.getAttribute('sandbox'))"
            ),
            "frames": [f.title() for f in frames],
            "frame_urls": [f.url for f in frames],
        }
        browser.close()
    print(json.dumps(result))
    return 0


def main(url: str, picture: str, shots: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return SKIP
    console: list[str] = []
    with sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception:  # noqa: BLE001 - браузера нет или он не запускается
            return SKIP
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.on("dialog", lambda d: d.accept())

        def shot(name: str) -> None:
            if shots:
                page.screenshot(path=f"{shots}/st8-{name}.png")

        def saved() -> str:
            page.wait_for_selector("#toast li", state="visible", timeout=30000)
            text = page.inner_text("#toast")
            page.click("#toast button")
            return text

        page.goto(url)
        page.wait_for_selector('.st-node[data-key="blocks"]', timeout=30000)

        # 1. правка одного поля существующей страницы
        page.click('.st-node[data-key="blocks"]')
        page.wait_for_selector('[id="f-title"]')
        page.fill('[id="f-title"]', "Блоки страницы - правка из студии")
        page.wait_for_selector('.st-field[data-path="title"].changed')
        shot("edit")
        page.click("#st-save")
        edit = saved()

        # 2. новая страница на трёх языках: en переведён, de пропущен
        page.click("#st-new-page")
        page.fill("#st-d-name", "about-team")
        page.fill("#st-d-title", "О команде и о том, как мы работаем")
        page.click("#st-dialog-ok")
        page.wait_for_selector(".st-badge.new")
        page.fill('[id="f-h1"]', "О команде")
        page.fill('[id="f-description"]', "Кто делает сайты и как с нами работать.")
        page.fill('[id="f-sections.intro.text"]', "Мы делаем сайты.")
        page.click('.st-langtabs button[data-lang="en"]')
        page.fill('[id="f-title"]', "About the team and how we work")
        page.fill('[id="f-h1"]', "About the team")
        page.fill('[id="f-description"]', "Who makes the sites and how to work with us.")
        page.fill('[id="f-sections.intro.text"]', "We make sites.")
        page.click('.st-langtabs button[data-lang="de"]')
        page.check("#st-skip")
        shot("create")
        page.click("#st-save")
        create = saved()

        # 3. картинка в media/ и подпись к ней
        page.wait_for_selector('.st-node[data-key="about-team"]')
        page.click('.st-node[data-key="about-team"]')
        page.wait_for_selector('input[data-upload="image"]')
        page.set_input_files('input[data-upload="image"]', picture)
        saved()  # сообщение о загрузке: файл и его размер
        page.wait_for_selector('.st-field[data-path="image"].changed')
        page.fill('[id="f-image_alt"]', "Команда за работой")
        page.wait_for_selector('.st-field[data-path="image"] .st-image img:not([hidden])')
        page.locator('.st-field[data-path="image"]').scroll_into_view_if_needed()
        shot("upload")
        page.click("#st-save")
        upload = saved()

        # 4. справка темы - та же страница, что /_heron/theme/ черновой сборки
        page.click("#tab-btn-ref")
        page.wait_for_selector('#st-ref-frame[src*="_heron/theme"]', timeout=60000)
        page.frame_locator("#st-ref-frame").locator("h1").wait_for(timeout=30000)
        shot("ref")
        browser.close()
    print(json.dumps({"console": console, "edit": edit, "create": create, "upload": upload}))
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "attack":
        sys.exit(attack(sys.argv[2]))
    sys.exit(main(*sys.argv[1:4]))
