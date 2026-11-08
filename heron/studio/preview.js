"use strict";
// Просмотр студии: ключ просмотра (?k=) - из адресной строки сразу после открытия.
// Сервер поставил по нему cookie, дальше страница ходит с ней; ключ в адресе остался бы
// в истории, в закладке и в скопированной ссылке. Файл подключает порт просмотра
// (heron/setup/server.py), встроенных скриптов нет: политика script-src 'self'.
(() => {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("k")) return;
    url.searchParams.delete("k");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  } catch (err) { /* без истории (about:blank, запрет песочницы) - адрес остаётся как есть */ }
})();
