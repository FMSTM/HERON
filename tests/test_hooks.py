"""Реестр точек расширения."""

import pytest

from heron.core.hooks import Hooks


def test_known_hook_registers_and_calls():
    hooks = Hooks()
    seen = []
    hooks.on("on_page_parsed", lambda page: seen.append(page))
    hooks.call("on_page_parsed", "страница")
    assert seen == ["страница"]


def test_handlers_run_in_order_of_registration():
    hooks = Hooks()
    order = []
    hooks.on("on_config", lambda: order.append(1))
    hooks.on("on_config", lambda: order.append(2))
    hooks.call("on_config")
    assert order == [1, 2]


def test_unknown_hook_is_refused():
    with pytest.raises(ValueError, match="неизвестный хук"):
        Hooks().on("on_whatever", lambda: None)


def test_block_hooks_are_open_ended():
    hooks = Hooks()
    hooks.on("block:price-table", lambda section: {"rows": []})
    assert hooks.block("price-table") is not None
    assert hooks.block("нет-такого") is None


def test_calling_nobody_is_not_an_error():
    assert Hooks().call("on_build_finished") == []


def test_filters_and_globals():
    hooks = Hooks()
    hooks.filter("money", str)
    hooks.add_global("year", 2026)
    assert hooks.filters["money"](1) == "1"
    assert hooks.globals["year"] == 2026
