"""Один скрипт HERON на сайт (E51.S10): `services.heron` - `l.js` хаба с `data-site`.

- `services.heron: hs_…` и `services.heron: {site, hub, env}` - одно и то же;
  хаб по умолчанию - https://hub.heron.software;
- тег `<script async src="<hub>/l.js" data-site data-lang>` перед `</head>` каждой
  страницы включённой сборки, кроме 404; CSP - хаб в script-src и connect-src;
- E047 на кривой номер, hub, имя окружения; пустой номер - выключен, сведение;
- заданы и `heron`, и `chat` в одной сборке - только `heron`, предупреждение;
  `chat` без `heron` работает как раньше;
- белая тема: при `services.heron` - плашка согласия и `data-heron` у site.js,
  выбор посетителя уходит в `heron.analytics.consent(true|false)`.
"""

from __future__ import annotations

import functools
import http.server
import os
import re
import threading
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import HeronService, SiteConfig
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.errors import Collector
from heron.modules import nginx, services
from heron.setup.server import preview_policy

SITE = "hs_01JDX8Q7M2K9V4T6R3N5P8W1ZC"
OTHER = "hs_0123456789ABCDEFGHJKMNPQRS"
CHAT = "hcw_DTTQXXFWX2X8F6XHB1RQXBRN8G"
DEV_HUB = "https://dev-hub.heron.software"
BASE = {
    "heron": ">=0.3,<0.4",
    "site": {"domain": "site.example", "theme": "main", "default_lang": "en", "languages": ["en"]},
}
LOADER = re.compile(r'<script async src="([^"]+/l\.js)" data-site="([^"]+)"[^>]*></script>')
CHAT_TAG = re.compile(r'<script async src="[^"]+/chat/l\.js"[^>]*></script>')


def _config(**block) -> SiteConfig:
    return SiteConfig.model_validate({**BASE, "services": block})


def _errors(config: SiteConfig) -> list:
    collector = Collector()
    services.verify(config, collector)
    return collector.errors


def _csp(conf: str) -> str:
    return re.search(r'Content-Security-Policy "([^"]+)"', conf).group(1)


# --- запись и проверка -----------------------------------------------------------------


def test_short_form_is_the_same_as_the_block():
    short = _config(heron=SITE).services.heron
    full = _config(heron={"site": SITE}).services.heron
    assert isinstance(short, HeronService) and short == full
    assert _errors(_config(heron=SITE)) == []


def test_default_hub_and_tag():
    active = services.active(_config(heron=SITE), "prod")
    assert [s.name for s in active] == ["heron"]
    assert services.HUB_HOST == "https://hub.heron.software"
    assert active[0].tag("de") == (
        f'<script async src="https://hub.heron.software/l.js" data-site="{SITE}" '
        'data-lang="de"></script>'
    )
    assert active[0].insert == "head-end"
    assert active[0].csp == {
        "script-src": ("https://hub.heron.software",),
        "connect-src": ("https://hub.heron.software",),
    }


@pytest.mark.parametrize(
    "block",
    [
        {"site": "hs_short"},
        {"site": "hs_01JDX8Q7M2K9V4T6R3N5P8W1ZI"},  # I не из base32 Крокфорда
        {"site": CHAT},  # ключ виджета чата - не номер сайта
        {"site": SITE, "hub": "http://dev-hub.heron.software"},
        {"site": SITE, "hub": "https://dev-hub.heron.software/l.js"},
        {"site": SITE, "hub": "https://*.heron.software"},
        {"hub": "https:"},  # номера нет, а хаб кривой - всё равно E047
        {"site": SITE, "env": ["Dev"]},
        {"site": SITE, "env": {"prod": {"site": "nope"}}},
    ],
)
def test_bad_block_is_e047_with_hint(block):
    errors = _errors(_config(heron=block))
    assert errors and {e.code for e in errors} == {"E047"}
    assert all(e.hint and e.path == "site.yaml" for e in errors)


def test_unknown_key_is_e011():
    with pytest.raises(Exception) as caught:
        _config(heron={"site": SITE, "widget": CHAT})
    assert "widget" in str(caught.value)


@pytest.mark.parametrize("block", ["", {}, {"site": ""}, {"site": None, "hub": DEV_HUB}])
def test_empty_number_means_off_not_an_error(block):
    config = _config(heron=block)
    assert _errors(config) == []
    assert services.active(config, "prod") == []
    collector = Collector()
    services.key_notes(config, "prod", collector)
    assert [n.message.key for n in collector.notes] == ["services_heron_no_key"]
    assert collector.warnings == []


def test_env_list_and_per_env_values():
    config = _config(
        heron={
            "site": SITE,
            "hub": DEV_HUB,
            "env": {"dev": None, "prod": {"site": OTHER, "hub": ""}},
        }
    )
    dev, prod = services.active(config, "dev"), services.active(config, "prod")
    assert LOADER.search(dev[0].tag("en")).groups() == (f"{DEV_HUB}/l.js", SITE)
    # пустой hub окружения значение блока не перебивает
    assert LOADER.search(prod[0].tag("en")).groups() == (f"{DEV_HUB}/l.js", OTHER)
    assert services.active(config, "stage") == []
    assert services.active(_config(heron={"site": SITE, "env": ["dev"]}), "prod") == []


# --- heron и chat вместе ---------------------------------------------------------------


def _warnings(config: SiteConfig, env: str) -> list[str]:
    collector = Collector()
    services.conflict_warnings(config, env, collector)
    return [w.message.key for w in collector.warnings]


def test_heron_wins_over_chat_with_a_warning():
    config = _config(heron=SITE, chat={"widget": CHAT})
    assert [s.name for s in services.active(config, "prod")] == ["heron"]
    assert _warnings(config, "prod") == ["services_heron_over_chat"]
    assert _errors(config) == []
    csp = services.csp(config, "prod")
    assert csp["script-src"] == ["https://hub.heron.software"]


def test_chat_alone_still_works_without_a_warning():
    config = _config(chat={"widget": CHAT})
    assert [s.name for s in services.active(config, "prod")] == ["chat"]
    assert _warnings(config, "prod") == []


def test_no_conflict_when_envs_do_not_overlap():
    config = _config(heron={"site": SITE, "env": ["prod"]}, chat={"widget": CHAT, "env": ["dev"]})
    assert [s.name for s in services.active(config, "dev")] == ["chat"]
    assert [s.name for s in services.active(config, "prod")] == ["heron"]
    assert _warnings(config, "dev") == [] and _warnings(config, "prod") == []


def test_empty_heron_number_leaves_the_chat_on():
    config = _config(heron={"site": ""}, chat={"widget": CHAT})
    assert [s.name for s in services.active(config, "prod")] == ["chat"]
    assert _warnings(config, "prod") == []


def test_bad_chat_is_still_an_error_next_to_heron():
    errors = _errors(_config(heron=SITE, chat={"widget": "hcw_nope"}))
    assert [e.code for e in errors] == ["E047"]


# --- вставка и CSP ---------------------------------------------------------------------


def test_insert_goes_before_head_end_and_chat_before_body_end():
    heron = services.active(_config(heron=SITE), "prod")
    chat = services.active(_config(chat={"widget": CHAT}), "prod")
    page = "<html><head><title>x</title></head><body><p>b</p></body></html>"
    out = services.insert(page, "en", heron + chat)
    order = [out.index(part) for part in ("/l.js", "</head>", "/chat/l.js", "</body>")]
    assert order == sorted(order)
    # без </head> - туда же, куда body-end
    assert services.insert("<p>x</p></body>", "en", heron).endswith("</script>\n</body>")


def test_nginx_csp_has_the_hub_only_in_enabled_env():
    plain = _csp(nginx.generate(SiteConfig.model_validate(BASE))[nginx.NAME])
    config = _config(heron={"site": SITE, "hub": DEV_HUB, "env": ["dev"]})
    dev = _csp(nginx.generate(config, env="dev")[nginx.NAME])
    assert f"script-src 'self' {DEV_HUB};" in dev and f"connect-src 'self' {DEV_HUB};" in dev
    assert _csp(nginx.generate(config, env="prod")[nginx.NAME]) == plain
    for bad in ("*", "'unsafe-eval'", " https: ", " http:"):
        assert bad not in dev


def test_preview_policy_gets_the_hub():
    policy = preview_policy("http://localhost:8000", services.csp(_config(heron=SITE), "dev"))
    assert "script-src 'self' https://hub.heron.software;" in policy
    assert "connect-src 'self' https://hub.heron.software;" in policy


# --- сборка ----------------------------------------------------------------------------


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    monkeypatch.delenv("SITE_ANALYTICS", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    return tmp_path / "demo"


def _set_services(root: Path, block: dict) -> None:
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["services"] = block
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _pages(dist: Path) -> dict[str, str]:
    return {
        page.relative_to(dist).as_posix(): page.read_text(encoding="utf-8")
        for page in dist.rglob("*.html")
        if not page.relative_to(dist).as_posix().startswith("_heron")
    }


def test_build_puts_one_tag_into_head_of_every_page(site, tmp_path):
    _set_services(site, {"heron": SITE})
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert not built.failed, [str(e) for e in built.collector.errors]
    pages = _pages(tmp_path / "d")
    regular = {
        rel: text for rel, text in pages.items() if not (rel.startswith("404") or "/404" in rel)
    }
    assert regular
    for rel, text in regular.items():
        found = LOADER.findall(text)
        assert found == [("https://hub.heron.software/l.js", SITE)], rel
        head = text[: text.lower().index("</head>")]
        assert "/l.js" in head, rel
        assert not CHAT_TAG.search(text)
    for rel, text in pages.items():
        if rel not in regular:
            assert not LOADER.search(text), rel
    csp = _csp((tmp_path / "d" / ".heron-nginx.conf").read_text("utf-8"))
    assert "script-src 'self' https://hub.heron.software" in csp


def test_build_with_both_warns_and_skips_the_chat(site, tmp_path):
    _set_services(site, {"heron": {"site": SITE}, "chat": {"widget": CHAT}})
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert not built.failed, [str(e) for e in built.collector.errors]
    assert [w.message.key for w in built.collector.warnings if hasattr(w.message, "key")].count(
        "services_heron_over_chat"
    ) == 1
    text = (tmp_path / "d" / "index.html").read_text("utf-8")
    assert LOADER.search(text) and not CHAT_TAG.search(text)
    check = CliRunner().invoke(main, ["check", str(site), "--env", "prod", "--notes", "en"])
    assert "only the HERON script is connected" in check.output, check.output


def test_old_chat_setting_builds_as_before(site, tmp_path):
    _set_services(site, {"chat": {"widget": CHAT}})
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert not built.failed, [str(e) for e in built.collector.errors]
    text = (tmp_path / "d" / "index.html").read_text("utf-8")
    assert CHAT_TAG.search(text) and not LOADER.search(text)
    assert not any(
        getattr(w.message, "key", None) == "services_heron_over_chat"
        for w in built.collector.warnings
    )


def test_starter_theme_shows_consent_banner_for_heron(site, tmp_path):
    # дев-сборка: счётчиков нет (env.analytics выключен), плашка - только ради heron
    off = pipeline.run(site, dist=tmp_path / "off", env=BuildEnv.resolve("dev"))
    assert not off.failed, [str(e) for e in off.collector.errors]
    plain = (tmp_path / "off" / "index.html").read_text("utf-8")
    assert "data-consent" not in plain and "data-heron" not in plain
    _set_services(site, {"heron": SITE})
    on = pipeline.run(site, dist=tmp_path / "on", env=BuildEnv.resolve("dev"))
    assert not on.failed, [str(e) for e in on.collector.errors]
    text = (tmp_path / "on" / "index.html").read_text("utf-8")
    assert "data-consent " in text and "data-consent-open" in text
    assert 'data-heron="1"' in text
    script = next((tmp_path / "on" / "assets").glob("site*.js")).read_text("utf-8")
    assert "heron.analytics" in script or "h.analytics.consent" in script


def test_theme_sees_heron_flag(site, tmp_path):
    base = site / "theme" / "base.html"
    text = base.read_text(encoding="utf-8")
    marker = "<!--heron:{{ services.heron.enabled }}:{{ services.chat.enabled }}-->"
    base.write_text(text.replace("</body>", marker + "</body>"), encoding="utf-8")
    _set_services(site, {"heron": SITE, "chat": {"widget": CHAT}})
    built = pipeline.run(site, dist=tmp_path / "d")
    assert not built.failed, [str(e) for e in built.collector.errors]
    assert "<!--heron:True:False-->" in (tmp_path / "d" / "index.html").read_text("utf-8")


# --- согласие в браузере ---------------------------------------------------------------

# Подмена l.js: как настоящий загрузчик, ставит window.heron и шлёт heron:ready;
# вызовы consent записываются в window.__consent.
FAKE_LOADER = """
window.__consent = window.__consent || [];
window.heron = { _l: 1, analytics: { consent: function (v) {
  window.__consent.push(v);
  try { localStorage.setItem('heron:c', v ? '1' : '0'); } catch (e) {}
} } };
document.dispatchEvent(new CustomEvent('heron:ready', { detail: {} }));
"""


def _sync_api():
    if os.environ.get("HERON_REQUIRE_BROWSER"):
        import playwright.sync_api as sync_api

        return sync_api
    return pytest.importorskip("playwright.sync_api")


@pytest.mark.browser
def test_browser_banner_passes_consent_to_heron(site, tmp_path):
    sync_api = _sync_api()
    _set_services(site, {"heron": SITE})
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert not built.failed, [str(e) for e in built.collector.errors]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "d"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"

    def intercept(route):
        url = route.request.url
        if url == "https://hub.heron.software/l.js":
            route.fulfill(status=200, content_type="text/javascript", body=FAKE_LOADER)
        elif url.startswith(base):
            route.continue_()
        else:
            route.abort()

    try:
        with sync_api.sync_playwright() as play:
            browser = play.chromium.launch()
            try:
                context = browser.new_context()
                context.route("**/*", intercept)
                page = context.new_page()
                page.goto(base, wait_until="networkidle")
                assert page.locator("[data-consent]").is_visible()
                assert page.evaluate("window.__consent") == []
                page.click("[data-consent-accept]")
                assert page.evaluate("window.__consent") == [True]
                # следующая страница: выбор уже у l.js - повторно не шлётся
                page.reload(wait_until="networkidle")
                assert page.evaluate("window.__consent") == []
                page.click("[data-consent-open]")
                page.click("[data-consent-decline]")
                assert page.evaluate("window.__consent") == [False]
                context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
