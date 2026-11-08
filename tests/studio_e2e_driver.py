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
from pathlib import Path

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


def remap(url: str) -> int:
    """Студия по адресу с другими портами (как `docker run -p 9000:8000 -p 9001:8001`).

    Открывает справку темы. Печатает адреса рамок, заголовок справки, источник
    просмотра, который посчитала страница, и сообщения консоли (отказы CSP там же).
    """
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
        page = browser.new_context().new_page()
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(url)
        page.wait_for_selector("#tab-btn-ref", timeout=30000)
        page.click("#tab-btn-ref")
        page.wait_for_selector('#st-ref-frame[src*="_heron/theme"]', timeout=60000)
        heading = ""
        try:
            heading = page.frame_locator("#st-ref-frame").locator("h1").inner_text(timeout=30000)
        except Exception:  # noqa: BLE001 - рамка не загрузилась: тест скажет, что видел
            heading = ""
        page.wait_for_timeout(500)
        result = {
            "heading": heading,
            "frame_src": page.evaluate(
                "() => [...document.querySelectorAll('iframe')].map((f) => f.src)"
            ),
            "origin": page.evaluate(
                "() => window.HERON_PREVIEW_ORIGIN(location, window.HERON_STUDIO.preview)"
            ),
            "fallback": page.evaluate(
                "() => window.HERON_PREVIEW_ORIGIN("
                "{protocol: 'http:', hostname: 'localhost', port: ''}, "
                "window.HERON_STUDIO.preview)"
            ),
            "console": console,
        }
        browser.close()
    print(json.dumps(result))
    return 0


def race(url: str) -> int:
    """Ввод, пока форма грузится заново (переключили язык интерфейса), и ключ просмотра.

    Ответы `open` держатся и отпускаются по одному, устаревший первым. Печатает: заперта
    ли форма, пока не пришёл ответ последнего запроса (и после устаревшего), язык
    вкладки (`S.edit`) в это время, ответы после ввода, текст итога записи, адрес
    вкладки просмотра, открытой из итога «Посмотреть», и сообщения консоли.
    """
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
        page.goto(url)
        page.wait_for_selector('.st-node[data-key="blocks"]', timeout=30000)
        page.click('.st-node[data-key="blocks"]')
        page.wait_for_selector('[id="f-h1"]')
        page.wait_for_timeout(500)

        # Ответы open держатся, пока драйвер их не отпустит: порядок ответов задан, а не
        # случаен. Смена языка интерфейса шлёт дерево и open дважды - второй запрос
        # open уходит, пока первый ещё висит.
        held: list = []
        page.route("**/api/studio/open", lambda route: held.append(route))

        def wait_held(count: int) -> None:
            for _ in range(200):
                if len(held) >= count:
                    return
                page.wait_for_timeout(50)
            raise AssertionError(f"open requests held: {len(held)}, wanted {count}")

        def release(route) -> None:
            with page.expect_response("**/api/studio/open"):
                route.continue_()
            page.wait_for_timeout(300)  # ответ разобран и форма (если надо) нарисована

        def state() -> dict:
            return page.evaluate(
                "() => ({locked: document.getElementById('f-h1').disabled,"
                " loading: window.HERON_STUDIO.loading, edit: window.HERON_STUDIO.edit})"
            )

        page.click("header >> text=EN")  # heron:lang: форма открывается заново
        wait_held(1)
        if len(held) < 2:
            # второй heron:lang - как от загрузки настроек сайта сразу после щелчка
            page.evaluate("() => document.dispatchEvent(new Event('heron:lang'))")
        wait_held(2)
        page.wait_for_timeout(300)  # ответы дерева пришли: форма нарисована заново
        during = [state()]
        release(held[0])  # первый, устаревший ответ: форма всё ещё заперта
        during.append(state())
        locked = all(item["locked"] for item in during)
        edit = during[-1]["edit"]
        for route in held[1:]:
            release(route)
        page.unroute("**/api/studio/open")
        after = state()
        if after["locked"] or after["loading"]:
            raise AssertionError(f"the form stays locked after the last answer: {after}")
        page.fill('[id="f-h1"]', "Набрано во время загрузки")
        answers = page.evaluate("() => JSON.stringify(window.HERON_STUDIO.ans)")
        page.click("#st-save")
        page.wait_for_selector("#toast li", state="visible", timeout=30000)
        saved = page.inner_text("#toast")
        page.click("#toast button")
        page.click("#st-preview")
        page.wait_for_selector("#st-preview-link", timeout=60000)
        with context.expect_page() as popup:
            page.click("#st-preview-link")
        view = popup.value
        view.wait_for_load_state("load")
        view.wait_for_timeout(500)
        result = {
            "locked": locked,
            "during": during,
            "edit": edit,
            "answers": answers,
            "saved": saved,
            "preview": view.url,
            "preview_title": view.title(),
            "console": console,
        }
        browser.close()
    print(json.dumps(result))
    return 0


def lost_lang(url: str) -> int:
    """Вкладка «Сайт»: основного языка нет в языках сайта - предложение дописать его.

    Печатает: видно ли предложение и его текст, языки и основной язык до и после
    кнопки «Добавить», осталось ли предложение, текст итога записи и консоль.
    """
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
        page = browser.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(url)
        page.wait_for_selector("#lang-lost", timeout=30000)
        langs = "() => [...document.querySelectorAll('.chips .chip')].map((c) => c.textContent)"
        before = {
            "offer": page.inner_text("#lang-lost"),
            "chips": page.evaluate(langs),
            "main": page.input_value('[id="site.default_lang"]'),
        }
        page.click("#lang-lost-add")
        page.wait_for_selector("#lang-lost", state="detached", timeout=10000)
        after = {
            "chips": page.evaluate(langs),
            "main": page.input_value('[id="site.default_lang"]'),
        }
        page.click("#save")
        page.wait_for_selector("#toast li", state="visible", timeout=60000)
        result = {
            "before": before,
            "after": after,
            "saved": page.inner_text("#toast"),
            "console": console,
        }
        browser.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0


def move_into(url: str, root: str) -> int:
    """Перетаскивание страницы в папку 0.2: вопрос о страницах, которые выпадут из prod.

    Первый раз вопрос отклоняется (ничего не записано, итога переноса нет), второй -
    принимается. Печатает тексты вопросов, итоги и консоль браузера.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return SKIP
    console: list[str] = []
    asked: list[str] = []
    with sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception:  # noqa: BLE001 - браузера нет или он не запускается
            return SKIP
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        refuse = {"on": True}

        def dialog(d) -> None:
            asked.append(d.message)
            # вопрос «перенести?» - да; вопрос о страницах из prod - как скажет сценарий
            if "prod" in d.message and refuse["on"]:
                d.dismiss()
            else:
                d.accept()

        page.on("dialog", dialog)
        page.goto(url)
        source = '.st-node[data-key="about"]'
        folder = '.st-node[data-key="services"]'
        page.wait_for_selector(folder, timeout=30000)
        page.drag_and_drop(source, folder)
        page.wait_for_timeout(1500)
        first = {
            "asked": list(asked),
            "toast": page.inner_text("#toast") if page.is_visible("#toast") else "",
            "about": page.locator(source).count(),
            # файлы сайта сразу после отказа: запись не должна была ничего тронуть
            "files": sorted(
                p.relative_to(root).as_posix() for p in Path(root, "content").rglob("*.md")
            ),
        }
        refuse["on"] = False
        asked.clear()
        page.drag_and_drop(source, folder)
        page.wait_for_selector("#toast li", state="visible", timeout=30000)
        page.wait_for_timeout(500)
        second = {"asked": list(asked), "toast": page.inner_text("#toast")}
        browser.close()
    print(json.dumps({"first": first, "second": second, "console": console}))
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
    if sys.argv[1] == "remap":
        sys.exit(remap(sys.argv[2]))
    if sys.argv[1] == "race":
        sys.exit(race(sys.argv[2]))
    if sys.argv[1] == "lost_lang":
        sys.exit(lost_lang(sys.argv[2]))
    if sys.argv[1] == "move_into":
        sys.exit(move_into(sys.argv[2], sys.argv[3]))
    sys.exit(main(*sys.argv[1:4]))
