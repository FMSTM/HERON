"""Студия в браузере (ST8): запросы /api/studio/* и функции heron.studio.

Студия - форма поверх ядра правки: те же `open_entity`, `apply_answers`,
`problems` и `save`, что у `heron page add`. Здесь проверяется, что каждое
действие студии пишет те же файлы, что CLI, без потерь, и что граница доступа
та же, что у конфигуратора: ключ в заголовке; просмотр - на своём порту со своим ключом.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from PIL import Image

from heron import studio
from heron.cli import main
from heron.core.errors import HeronError
from heron.scaffold import create
from tests.test_setup_access import _start, _stop

LANGS = ["ru", "en", "de"]
PAGE = {"kind": "page", "key": "blocks"}


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".heron-cache" not in p.parts
    }


def front(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (40, 90, 160)).save(out, "PNG")
    return out.getvalue()


# --- дерево и форма ---------------------------------------------------------------------


def test_tree_lists_every_language_types_and_pending(site):
    path = site / "content" / "de" / "blocks.md"
    path.write_text(path.read_text("utf-8").replace("---\n", "---\ntranslation: pending\n", 1))
    data = studio.tree(site, "ru")
    assert data["languages"] == LANGS and data["default_lang"] == "ru"
    blocks = next(item for item in data["items"] if item["key"] == "blocks")
    assert blocks["langs"] == {"ru": "ok", "en": "ok", "de": "pending"}
    assert {t["name"] for t in data["types"]} >= {"page", "home"}
    assert data["default_type"]["page"] == "page"


def test_open_gives_the_same_fields_as_the_console_with_hints(site):
    from heron.edit import entity as ops

    state = studio.check(site, {"target": PAGE}, "ru")
    ctx = ops.context(site, "ru")
    same = [f.path for f in ops.fields_of(ops.open_entity(ctx, "blocks"), "ru")]
    assert [f["path"] for f in state["fields"]["ru"]] == same
    title = next(f for f in state["fields"]["ru"] if f["path"] == "title")
    assert title["hint"] and title["help"] and title["required"]
    # на остальных языках - только поля с текстом
    assert {f["path"] for f in state["fields"]["en"]} < set(same)
    assert "type" not in {f["path"] for f in state["fields"]["en"]}
    # у de своего текста демо нет: копия английского с пометкой «перевод не готов»
    assert state["files"]["de"] == {"rel": "content/de/blocks.md", "exists": True, "pending": True}
    assert [g["name"] for g in state["groups"]][0] == "seo"
    kinds = {k["kind"]: k for k in state["sections"]["kinds"]}
    assert kinds["faq"]["auto"] and kinds["tabs"]["class"] == "tabs"
    assert "children" not in {k["module"] for k in state["sections"]["kinds"]}


def test_readonly_field_shows_its_reason(site):
    path = site / "content" / "ru" / "blocks.md"
    text = path.read_text("utf-8").replace("---\n", "---\nbroken: [\n", 1)
    path.write_text(text, encoding="utf-8")
    state = studio.check(site, {"target": PAGE}, "ru")
    title = next(f for f in state["fields"]["ru"] if f["path"] == "title")
    assert title["editable"] is False and "YAML" in title["readonly"]


# --- создание на всех языках --------------------------------------------------------------


def test_new_page_is_a_draft_until_save_then_all_languages(site):
    target = {"kind": "page", "key": "about-team", "title": "О команде"}
    state = studio.check(site, {"target": target}, "ru")
    assert state["new"] and not any(f["exists"] for f in state["files"].values())
    assert not (site / "content" / "ru" / "about-team.md").exists()
    request = {
        "target": target,
        "answers": {
            "ru": {
                "title": "О команде и о том, как мы работаем",
                "h1": "О команде",
                "description": "Кто делает сайты и как с нами работать.",
                "sections.intro.text": "Мы делаем сайты.",
            },
            "en": {
                "title": "About the team and how we work",
                "h1": "About the team",
                "description": "Who makes the sites and how to work with us.",
                "sections.intro.text": "We make sites.",
            },
            "de": "pending",
        },
    }
    out = studio.save(site, request, "ru")
    made = [f"content/{lang}/about-team.md" for lang in LANGS]
    assert out["saved"]["created"] == made
    assert out["saved"]["pending"] == ["content/de/about-team.md"]
    assert front(site / made[1]).get("translation") is None
    assert front(site / made[2])["translation"] == "pending"
    assert front(site / made[1])["h1"] == "About the team"
    assert out["state"]["new"] is False and out["state"]["files"]["de"]["pending"]


def test_existing_key_opens_for_editing_not_creation(site):
    state = studio.check(site, {"target": {"kind": "page", "key": "blocks", "type": "home"}}, "ru")
    assert state["new"] is False and state["type"] == "page"


def test_new_category_in_every_language_with_view(site):
    target = {"kind": "category", "key": "services", "view": "list", "title": "Услуги"}
    out = studio.save(site, {"target": target}, "ru")
    assert out["saved"]["created"] == [f"content/{lang}/services/_index.md" for lang in LANGS]
    data = front(site / "content" / "ru" / "services" / "_index.md")
    assert data["view"] == "list" and data["children_type"] == "page"
    assert out["saved"]["pending"] == [f"content/{lang}/services/_index.md" for lang in LANGS[1:]]


def test_page_in_a_missing_category_creates_the_category_too(site):
    out = studio.save(site, {"target": {"kind": "page", "key": "services/roofing"}}, "ru")
    assert out["saved"]["categories"] == ["services"]
    assert (site / "content" / "de" / "services" / "_index.md").is_file()


# --- правка без потерь -----------------------------------------------------------------------


def test_edit_changes_only_that_field_byte_for_byte(site):
    before = snapshot(site)
    request = {"target": PAGE, "answers": {"ru": {"title": "Блоки страницы - новое имя"}}}
    out = studio.save(site, request, "ru")
    assert out["saved"]["written"] == ["content/ru/blocks.md"]
    after = snapshot(site)
    changed = [rel for rel in after if after[rel] != before.get(rel)]
    assert changed == ["content/ru/blocks.md"]
    old = before["content/ru/blocks.md"].decode().splitlines()
    new = after["content/ru/blocks.md"].decode().splitlines()
    diff = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
    assert diff == [(next(x for x in old if x.startswith("title:")), new[old.index(diff[0][0])])]
    assert 'title: "Блоки страницы - новое имя"' in diff[0][1] or "новое имя" in diff[0][1]


def test_open_and_save_without_edits_writes_nothing(site):
    before = snapshot(site)
    out = studio.save(site, {"target": PAGE, "answers": {}}, "ru")
    assert out["saved"]["written"] == [] and out["saved"]["created"] == []
    assert snapshot(site) == before


def test_errors_stop_the_save_and_touch_nothing(site):
    before = snapshot(site)
    with pytest.raises(HeronError) as caught:
        studio.save(site, {"target": PAGE, "answers": {"ru": {"title": ""}}}, "ru")
    assert caught.value.code == "E039"
    assert snapshot(site) == before
    state = studio.check(site, {"target": PAGE, "answers": {"ru": {"title": ""}}}, "ru")
    assert state["errors"] and any(i["path"] == "title" for i in state["issues"]["ru"])


def test_translation_mark_toggles_on_an_existing_language(site):
    request = {"target": PAGE, "answers": {"de": {"translation": "pending"}}}
    studio.save(site, request, "ru")
    assert front(site / "content" / "de" / "blocks.md")["translation"] == "pending"
    studio.save(site, {"target": PAGE, "answers": {"de": {"translation": None}}}, "ru")
    assert "translation" not in front(site / "content" / "de" / "blocks.md")


# --- секции -------------------------------------------------------------------------------------

FAQ = {
    "op": "add_section",
    "anchor": "questions",
    "heading": "Вопросы",
    "kind": "faq",
    "values": {"items": [{"q": "Сколько это стоит?", "a": "Зависит от объёма."}]},
}


def test_add_section_on_every_language_marks_ready_translations(site):
    asked = studio.save(site, {"target": PAGE, "ops": [FAQ]}, "ru")
    assert asked["confirm"]["langs"] == ["en"]  # de уже не опубликован
    out = studio.save(site, {"target": PAGE, "ops": [FAQ], "confirm_pending": True}, "ru")
    assert sorted(out["saved"]["written"]) == sorted(f"content/{c}/blocks.md" for c in LANGS)
    for lang in LANGS:
        text = (site / "content" / lang / "blocks.md").read_text("utf-8")
        assert "## Вопросы {#questions}" in text and "### Сколько это стоит?" in text
    assert front(site / "content" / "en" / "blocks.md")["translation"] == "pending"
    assert "translation" not in front(site / "content" / "ru" / "blocks.md")
    present = {s["id"]: s["kind"] for s in out["state"]["sections"]["present"]}
    assert present["questions"] == "faq"


def test_section_by_content_needs_its_first_item(site):
    bad = {**FAQ, "values": None}
    with pytest.raises(HeronError) as caught:
        studio.check(site, {"target": PAGE, "ops": [bad]}, "ru")
    assert caught.value.code == "E039"


def test_remove_section_everywhere_keeps_the_rest(site):
    before = {lang: (site / "content" / lang / "blocks.md").read_text("utf-8") for lang in LANGS}
    studio.save(site, {"target": PAGE, "ops": [{"op": "remove_section", "anchor": "quote"}]}, "ru")
    for lang in LANGS:
        text = (site / "content" / lang / "blocks.md").read_text("utf-8")
        assert "{#quote}" not in text and "{#gallery" in text
        assert len(text) < len(before[lang])


# --- перенос и меню --------------------------------------------------------------------------


def test_move_keeps_old_addresses_and_menu_with_comments(site):
    studio.save(site, {"target": {"kind": "category", "key": "guides"}}, "ru")
    yaml_before = (site / "site.yaml").read_text("utf-8")
    comments = [line for line in yaml_before.splitlines() if line.lstrip().startswith("#")]
    out = studio.save(site, {"target": PAGE, "answers": {"key": "guides/blocks"}}, "ru")
    assert (site / "content" / "ru" / "guides" / "blocks.md").is_file()
    assert not (site / "content" / "ru" / "blocks.md").exists()
    assert ["/blocks/", "/guides/blocks/"] in out["saved"]["redirects"]
    assert front(site / "content" / "en" / "guides" / "blocks.md")["redirect_from"] == [
        "/en/blocks/"
    ]
    text = (site / "site.yaml").read_text("utf-8")
    assert "guides/blocks" in yaml.safe_load(text)["nav"]["main"]
    assert [line for line in text.splitlines() if line.lstrip().startswith("#")] == comments


def test_menu_flag_goes_to_site_yaml_with_comments(site):
    studio.save(site, {"target": {"kind": "page", "key": "about-team"}}, "ru")
    before = (site / "site.yaml").read_text("utf-8")
    out = studio.save(
        site,
        {"target": {"kind": "page", "key": "about-team"}, "answers": {"ru": {"menu": True}}},
        "ru",
    )
    assert out["saved"]["site_yaml"] is True
    after = (site / "site.yaml").read_text("utf-8")
    assert "about-team" in yaml.safe_load(after)["nav"]["main"]
    keep = [line for line in before.splitlines() if line.lstrip().startswith("#")]
    assert [line for line in after.splitlines() if line.lstrip().startswith("#")] == keep


# --- картинки ------------------------------------------------------------------------------


def test_upload_puts_a_picture_into_media_only(site):
    out = studio.upload(site, "Фото команды 2026.PNG", png(1600, 900))
    assert out["path"] == "media/2026.png" and (out["width"], out["height"]) == (1600, 900)
    again = studio.upload(site, "Фото команды 2026.PNG", png(1600, 900))
    assert again["path"] == "media/2026.png" and again["reused"]
    other = studio.upload(site, "2026.png", png(800, 800))
    assert other["path"] == "media/2026-2.png"
    assert studio.upload(site, "x.jpeg", _jpeg())["path"] == "media/x.jpg"


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (10, 10)).save(out, "JPEG")
    return out.getvalue()


@pytest.mark.parametrize(
    "name, data",
    [
        ("notes.txt", b"hello"),
        ("../../evil.png", b"not a png"),
        ("fake.png", b"\x89PNG not really"),
        ("type.png", None),  # JPEG под именем PNG
        ("bad.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),
        ("on.svg", b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"></svg>'),
        ("empty.png", b""),
    ],
)
def test_upload_refuses_what_is_not_a_picture(site, name, data):
    before = snapshot(site)
    with pytest.raises(HeronError) as caught:
        studio.upload(site, name, _jpeg() if data is None else data)
    assert caught.value.code == "E039"
    assert snapshot(site) == before


def test_upload_size_is_limited(site, monkeypatch):
    monkeypatch.setattr(studio, "MAX_IMAGE", 100)
    with pytest.raises(HeronError):
        studio.upload(site, "big.png", png(200, 200))


def test_uploaded_picture_is_checked_by_width_like_check(site):
    out = studio.upload(site, "narrow.png", png(400, 400))
    request = {
        "target": PAGE,
        "answers": {"ru": {"image": out["path"], "image_alt": "Команда"}},
    }
    state = studio.check(site, request, "ru")
    found = [i for i in state["issues"]["ru"] if i["path"] == "image"]
    assert found and "400" in found[0]["message"] and found[0]["level"] == "warning"


def test_media_file_only_serves_pictures_from_media(site):
    studio.upload(site, "pic.png", png(20, 20))
    assert studio.media_file(site, "media/pic.png") is not None
    assert studio.media_file(site, "site.yaml") is None
    assert studio.media_file(site, "media/../site.yaml") is None


# --- сервер: ключ, cookie, CSP -------------------------------------------------------------


def _req(base, path, data=None, token="", raw=None, cookie="", host=""):
    # Host - как у браузера: имя и порт из адреса (порт студии считается от него)
    headers = {"Host": host or "localhost:" + base.rsplit(":", 1)[1]}
    if token:
        headers["X-Heron-Token"] = token
    if cookie:
        headers["Cookie"] = cookie
    body = raw
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


@pytest.fixture
def served(site):
    port, token, thread = _start(site, "127.0.0.1")
    try:
        yield f"http://127.0.0.1:{port}", token, site
    finally:
        _stop(port, token, thread)


def test_page_has_no_inline_scripts_and_strict_csp(served):
    base, _token, _site = served
    status, body, headers = _req(base, "/")
    page = body.decode()
    assert status == 200
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page) is None
    assert re.search(r"\son[a-z]+\s*=", page) is None
    csp = headers["Content-Security-Policy"]
    assert "script-src 'self';" in csp and "unsafe-inline" not in csp.split("script-src")[1][:20]
    assert "frame-ancestors 'none'" in csp
    for asset in ("/_studio/setup.js", "/_studio/studio.js", "/_studio/studio.css"):
        status, body, headers = _req(base, asset)
        assert status == 200 and body, asset


def test_studio_api_needs_the_key(served):
    base, token, site = served
    before = snapshot(site)
    request = {"target": PAGE, "answers": {"ru": {"title": "Взлом"}}}
    for path in ("/api/studio/tree", "/api/studio/save", "/api/studio/open", "/api/session"):
        assert _req(base, path, data=request)[0] == 403
        assert _req(base, path, data=request, token="wrong")[0] == 403
    assert _req(base, "/api/studio/upload?name=a.png", raw=png(10, 10))[0] == 403
    assert snapshot(site) == before
    status, body, _ = _req(base, "/api/studio/tree", data={}, token=token)
    assert status == 200 and json.loads(body)["languages"] == LANGS


def test_studio_api_saves_and_reports_errors_in_the_page_language(served):
    base, token, site = served
    request = {"target": PAGE, "answers": {"ru": {"title": ""}}, "lang": "en"}
    status, body, _ = _req(base, "/api/studio/save", data=request, token=token)
    payload = json.loads(body)
    assert status == 400 and payload["code"] == "E039"
    assert not re.search(r"[А-Яа-я]", payload["hint"])
    request = {"target": PAGE, "answers": {"ru": {"h1": "Блоки и формы"}}, "lang": "ru"}
    status, body, _ = _req(base, "/api/studio/save", data=request, token=token)
    assert status == 200 and json.loads(body)["saved"]["written"] == ["content/ru/blocks.md"]
    status, body, _ = _req(base, "/api/studio/upload?name=pic.png", raw=png(1300, 700), token=token)
    assert status == 200 and json.loads(body)["path"] == "media/pic.png"
    assert (site / "media" / "pic.png").is_file()


def _preview_info(base, token):
    status, body, _ = _req(base, "/api/studio/start", data={}, token=token)
    assert status == 200
    return json.loads(body)["preview"]


def test_preview_media_and_ref_live_on_their_own_port(served):
    """Приёмка 0.3.0, блокер 2: скрипты темы - на другом источнике, без ключа API."""
    base, token, site = served
    studio.upload(site, "pic.png", png(20, 20))
    info = _preview_info(base, token)
    port = int(base.rsplit(":", 1)[1])
    assert info["port"] == port + 1 and info["key"] != token
    other = f"http://127.0.0.1:{info['port']}"
    # порт студии больше не отдаёт ни просмотр, ни картинки, ни cookie с ключом
    assert _req(base, "/_studio/media/pic.png")[0] == 404
    assert _req(base, "/api/session", data={}, token=token)[0] == 404
    # порт просмотра: без ключа просмотра - 403, ключ API там не действует
    assert _req(other, "/_studio/media/pic.png")[0] == 403
    assert _req(other, f"/_studio/media/pic.png?k={token}")[0] == 403
    status, body, headers = _req(other, f"/_studio/media/pic.png?k={info['key']}")
    assert status == 200 and body.startswith(b"\x89PNG")
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "heron-preview=" in cookie
    pair = cookie.split(";", 1)[0]
    assert token not in cookie
    assert _req(other, "/_studio/media/pic.png", cookie="heron-preview=wrong")[0] == 403
    status, body, _ = _req(base, "/api/studio/preview", data={"target": PAGE}, token=token)
    data = json.loads(body)
    assert status == 200 and data["ok"], data
    assert data["urls"]["ru"] == "/blocks/" and data["urls"]["en"] == "/en/blocks/"
    assert _req(base, data["ref"])[0] == 404
    assert _req(other, data["ref"])[0] == 403
    status, body, headers = _req(other, data["ref"], cookie=pair)
    assert status == 200 and b"<h1>" in body
    # в рамку - только студии; сама студия пускает рамки и картинки только с порта просмотра
    assert f"frame-ancestors http://localhost:{port}" in headers["Content-Security-Policy"]
    studio_csp = _req(base, "/")[2]["Content-Security-Policy"]
    assert f"frame-src http://localhost:{info['port']};" in studio_csp
    assert "frame-src 'self'" not in studio_csp
    status, body, _ = _req(other, "/blocks/", cookie=pair)
    assert status == 200 and "Блоки".encode() in body
    assert _req(other, "/../../site.yaml", cookie=pair)[0] == 404
    # писать на порту просмотра нечем: POST не принимается, файлы те же
    before = snapshot(site)
    request = {"target": PAGE, "answers": {"ru": {"title": "Взлом"}}}
    status = _req(other, "/api/studio/save", data=request, token=token, cookie=pair)[0]
    assert status >= 400
    assert snapshot(site) == before


def test_site_check_is_heron_check(served):
    base, token, _site = served
    status, body, _ = _req(base, "/api/studio/site-check", data={}, token=token)
    data = json.loads(body)
    assert status == 200 and data["ok"] is True and isinstance(data["warnings"], list)


def test_start_tells_the_page_where_to_open(site):
    import threading

    from heron.setup import server
    from tests.test_setup_access import _free_port

    port = _free_port()
    box = {}
    ready = threading.Event()

    def on_ready(token):
        box["token"] = token
        ready.set()

    start = {"tab": "pages", "target": {"kind": "category", "key": "services"}}
    thread = threading.Thread(
        target=server.run,
        args=(site, "127.0.0.1", port),
        kwargs={"on_ready": on_ready, "start": start},
        daemon=True,
    )
    thread.start()
    assert ready.wait(10)
    base = f"http://127.0.0.1:{port}"
    try:
        status, body, _ = _req(base, "/api/studio/start", data={}, token=box["token"])
        data = json.loads(body)
        assert status == 200 and data["tab"] == "pages" and data["target"]["key"] == "services"
    finally:
        _stop(port, box["token"], thread)


# --- команды -------------------------------------------------------------------------------


def _capture(monkeypatch):
    from heron.setup import server

    seen = {}

    def fake(root, host, port, on_ready=None, start=None, preview_port=None):
        seen.update(root=root, host=host, port=port, start=start, preview_port=preview_port)
        on_ready("KEY")

    monkeypatch.setattr(server, "run", fake)
    return seen


def test_studio_command_opens_the_pages_tab(site, monkeypatch):
    seen = _capture(monkeypatch)
    result = CliRunner().invoke(main, ["studio", str(site), "--port", "8124"])
    assert result.exit_code == 0, result.output
    assert seen["start"] == {"tab": "pages"} and seen["port"] == 8124
    assert seen["host"] == "127.0.0.1"
    assert "#KEY" in result.output


def test_category_add_web_opens_a_new_category_with_its_options(site, monkeypatch):
    seen = _capture(monkeypatch)
    args = ["category", "add", "services/roofing", str(site), "--web", "--view", "list"]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    target = seen["start"]["target"]
    assert target["kind"] == "category" and target["key"] == "services/roofing"
    assert target["view"] == "list"
    assert not (site / "content" / "ru" / "services").exists()


def test_page_add_web_with_category_moves_an_existing_page(site, monkeypatch):
    seen = _capture(monkeypatch)
    args = ["page", "add", "blocks", str(site), "--web", "--category", "guides"]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert seen["start"]["target"]["key"] == "blocks"
    assert seen["start"]["answers"] == {"key": "guides/blocks"}


def test_docker_hint_for_the_studio_publishes_the_port(monkeypatch):
    from heron import messages

    monkeypatch.setenv("HERON_CHANNEL", "beta")
    for args in ("studio", "page add about --web", "category add services --web"):
        command = messages.docker_command(args)
        assert " -it " in command and "-p 127.0.0.1:8000:8000" in command, command
        assert "-p 127.0.0.1:8001:8001" in command, command
    assert "-p 127.0.0.1" not in messages.docker_command("page add about --answers a.yaml")
    assert "-p 127.0.0.1:8000:8000" in messages.docker_command("setup")
    assert "-p 127.0.0.1:8001:8001" in messages.docker_command("setup")
    serve = messages.docker_command("serve")
    assert "-p 127.0.0.1:8000:8000" in serve and "8001" not in serve


# --- порт просмотра: --preview-port, адреса и CSP при пробросе портов со сдвигом --------------


@pytest.mark.parametrize(
    ("args", "port", "preview"),
    [
        (["studio"], 8000, 8001),
        (["studio", "--port", "8124"], 8124, 8125),
        (["studio", "--port", "8124", "--preview-port", "9300"], 8124, 9300),
        (["studio", "--preview-port=8500"], 8000, 8500),
        (["setup", "--preview-port", "9301"], 8000, 9301),
        (["page", "add", "about", "--web", "--preview-port", "9302"], 8000, 9302),
        (["category", "add", "services", "--web", "--port", "7000"], 7000, 7001),
        (["category", "add", "services", "--web", "--preview-port", "9303"], 8000, 9303),
    ],
)
def test_preview_port_flag_reaches_the_server(site, monkeypatch, args, port, preview):
    seen = _capture(monkeypatch)
    result = CliRunner().invoke(main, [*args[:1], *args[1:], str(site)])
    assert result.exit_code == 0, result.output
    assert seen["port"] == port and seen["preview_port"] == preview
    # одна ссылка - на студию с ключом; про просмотр - что он откроется сам
    assert f":{port}/#KEY" in result.output
    assert f"(порт {preview})" in result.output and "ничего делать не нужно" in result.output


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["--port", "8124", "--preview-port", "8124"], "--preview-port 8124"),
        (["--port", "65535"], "--preview-port"),
        (["--preview-port", "0"], "--preview-port"),
        (["--preview-port", "70000"], "--preview-port"),
    ],
)
def test_preview_port_is_validated_before_the_server_starts(site, monkeypatch, args, needle):
    seen = _capture(monkeypatch)
    result = CliRunner().invoke(main, ["studio", *args, str(site)])
    assert result.exit_code != 0, result.output
    assert needle in result.output, result.output
    assert seen == {}  # сервер не поднимался


def test_preview_port_for():
    from heron.setup import server

    assert server.preview_port_for(8000, None) == 8001
    assert server.preview_port_for(8000, 9100) == 9100
    for port, preview in ((8000, 8000), (65535, None)):
        with pytest.raises(HeronError) as caught:
            server.preview_port_for(port, preview)
        assert "--preview-port" in str(caught.value.message) + str(caught.value.hint)


def test_busy_preview_port_names_the_flag(tmp_path):
    import socket

    from heron.setup import server
    from tests.test_setup_access import _free_port, _site

    root = _site(tmp_path)
    port = _free_port()
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", port + 1))
        busy.listen(1)
        with pytest.raises(HeronError) as caught:
            server.run(root, "127.0.0.1", port, on_ready=lambda token: None)
    error = caught.value
    assert error.code == "E031" and str(port + 1) in str(error.message)
    assert "--preview-port" in str(error.hint)
    # студийный порт свободен снова: сервер закрыл то, что успел открыть
    with socket.socket() as again:
        again.bind(("127.0.0.1", port))


def test_container_hint_publishes_the_chosen_ports(site, monkeypatch):
    monkeypatch.setenv("HERON_IN_CONTAINER", "1")
    seen = _capture(monkeypatch)
    args = ["studio", "--port", "9000", "--preview-port", "9005", str(site)]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert seen["port"] == 9000 and seen["preview_port"] == 9005
    assert "-p 127.0.0.1:9000:9000 -p 127.0.0.1:9005:9005" in result.output


def test_docker_hint_follows_port_flags(monkeypatch):
    from heron import messages

    monkeypatch.setenv("HERON_CHANNEL", "beta")
    command = messages.docker_command("studio --port 9000")
    assert "-p 127.0.0.1:9000:9000 -p 127.0.0.1:9001:9001" in command, command
    command = messages.docker_command("setup --port 9000 --preview-port 9100")
    assert "-p 127.0.0.1:9000:9000 -p 127.0.0.1:9100:9100" in command, command
    command = messages.docker_command("page add about --web --preview-port=9200")
    assert "-p 127.0.0.1:8000:8000 -p 127.0.0.1:9200:9200" in command, command
    assert "8001" not in command
    serve = messages.docker_command("serve --port 9000")
    assert "-p 127.0.0.1:9000:9000" in serve and "9001" not in serve


def test_start_gives_both_inner_ports(served):
    base, token, _site = served
    info = _preview_info(base, token)
    port = int(base.rsplit(":", 1)[1])
    assert info["studio"] == port and info["port"] == port + 1


def test_csp_follows_the_port_the_browser_used(served):
    """`-p 9000:8000 -p 9001:8001`: браузер пришёл на 9000 - CSP называет 9001, не 8001."""
    base, token, _site = served
    port = int(base.rsplit(":", 1)[1])
    info = _preview_info(base, token)
    outer = 9000 if port not in (9000, 9001) else 7000
    shift = info["port"] - port
    studio_csp = _req(base, "/", host=f"localhost:{outer}")[2]["Content-Security-Policy"]
    assert f"frame-src http://localhost:{outer + shift};" in studio_csp, studio_csp
    assert f"img-src 'self' data: blob: http://localhost:{outer + shift};" in studio_csp
    assert f":{info['port']}" not in studio_csp
    other = f"http://127.0.0.1:{info['port']}"
    headers = _req(other, "/x", host=f"localhost:{outer + shift}")[2]
    assert f"frame-ancestors http://localhost:{outer}" in headers["Content-Security-Policy"]
    # адрес без порта (80/443): те же сдвиги, что считает страница
    bare = _req(base, "/", host="127.0.0.1")[2]["Content-Security-Policy"]
    assert f"http://127.0.0.1:{80 + shift} https://127.0.0.1:{443 + shift}" in bare, bare
    # IPv6 с портом
    v6 = _req(base, "/", host=f"[::1]:{outer}")[2]["Content-Security-Policy"]
    assert f"frame-src http://[::1]:{outer + shift};" in v6, v6
    # чужое имя - не в политику (такой запрос и так получит 403)
    foreign = _req(base, "/", host=f"evil.test:{outer}")[2]["Content-Security-Policy"]
    assert "evil.test" not in foreign


# --- SVG: разбор XML, а не поиск по тексту (приёмка 0.3.0, баг 10) ---------------------------

SVG_NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


@pytest.mark.parametrize(
    "body",
    [
        b"<svg/onload=alert(1)>",
        b"<svg onload=alert(1)>",
        f'<svg {SVG_NS}><a href="java&#x73;cript:alert(1)"><text>x</text></a></svg>'.encode(),
        f'<svg {SVG_NS}><a xlink:href=" jav&#9;ascript:alert(1)"/></svg>'.encode(),
        f'<svg {SVG_NS}><rect ONCLICK="alert(1)"/></svg>'.encode(),
        f"<svg {SVG_NS}><script>alert(1)</script></svg>".encode(),
        f"<svg {SVG_NS}><foreignObject><div/></foreignObject></svg>".encode(),
        f'<svg {SVG_NS}><image href="https://example.com/x.png"/></svg>'.encode(),
        f'<svg {SVG_NS}><use href="data:image/svg+xml,&lt;svg/&gt;"/></svg>'.encode(),
        f'<svg {SVG_NS}><set attributeName="onmouseover" to="alert(1)"/></svg>'.encode(),
        f'<svg {SVG_NS}><animate attributeName="href" values="javascript:x"/></svg>'.encode(),
        f"<svg {SVG_NS}><style>@import url(https://example.com/x.css);</style></svg>".encode(),
        b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
    ],
)
def test_dangerous_svg_is_refused(site, body):
    with pytest.raises(HeronError) as caught:
        studio.upload(site, "logo.svg", body)
    assert caught.value.code == "E039"
    assert not (site / "media" / "logo.svg").exists()


def test_plain_svg_with_local_links_is_taken(site):
    body = f'<svg {SVG_NS} viewBox="0 0 2 2"><rect id="a" width="1" fill="#123"/>'
    body += '<use href="#a"/><use xlink:href="#a"/></svg>'
    assert studio.upload(site, "logo.svg", body.encode())["path"] == "media/logo.svg"
