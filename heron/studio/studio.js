"use strict";
// Студия HERON: вкладки «Страницы» и «Справка темы» рядом с конфигуратором («Сайт»).
// Всё, что студия показывает и пишет, считает сервер теми же функциями, что у
// `heron page add` и `heron category add`: здесь только форма и запросы к /api/studio/*.
// Ключ доступа - TOKEN из адреса (setup.js); язык интерфейса - L (setup.js).
(() => {
  const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;
  const SPECIAL = ["home", "404"];  // типы главной и 404: не тип страниц внутри категории
  const TT = {
    ru: {
      tab_site: "Сайт", tab_pages: "Страницы", tab_ref: "Справка темы",
      tab_site_h: "Настройки всего сайта: site.yaml - название, языки, разметка, публикация, тема.",
      tab_pages_h: "Категории и страницы на всех языках: создать, править, перенести.",
      tab_ref_h: "Что умеет тема: типы страниц, блоки с живыми примерами из демо, виды категорий.",
      tree: "Категории и страницы", new_page: "+ Страница", new_category: "+ Категория", check_site: "Проверить",
      new_page_h: "Новая страница сразу на всех языках сайта. Есть такая - откроется на правку.",
      new_category_h: "Категория - папка со своей страницей: заголовок, описание, вид списка страниц внутри. Вложенность любая.",
      check_site_h: "Та же проверка, что heron check в терминале: весь сайт, ничего не собирая.",
      tree_h: "Перетащите страницу или категорию на другую категорию (или на «В корень»), чтобы перенести: файлы переедут на всех языках, со старых адресов будет 301.",
      to_root: "В корень сайта", legend: "ru - файл есть · DE! - перевод не готов · зачёркнуто - файла нет",
      pick: "Выберите страницу слева или создайте новую.",
      page_word: "Страница", category_word: "Категория", home: "Главная", new: "новая", dirty: "не сохранено",
      save: "Сохранить", saving: "Сохраняю…", preview: "Посмотреть", revert: "Отменить правки", rename: "Переименовать",
      save_h: "Записывает файлы всех языков. Меняются только поля, которые вы правили: остальное в файлах остаётся байт в байт.",
      preview_h: "Собирает черновую версию сайта (как heron serve) и даёт ссылку на эту страницу.",
      revert_h: "Забыть несохранённые правки и показать файлы как на диске.",
      rename_h: "Новое имя файла и адреса. Файлы переедут на всех языках, со старого адреса будет 301.",
      rename_q: "Новое имя (латиница, цифры, дефисы):", move_q: "Перенести «{a}» в «{b}»? Файлы переедут на всех языках, со старых адресов будет 301.",
      main_lang: "основной язык", lang_new: "Файла этого языка ещё нет. Переведите поля ниже - или оставьте пустыми: тогда язык получит пометку «перевод не готов» (translation: pending) и в боевую сборку не попадёт, пока перевод не появится.",
      lang_absent: "Файла этого языка у страницы нет. Переведите поля ниже - файл появится с переводом. Оставите пустыми - файл не создаётся. «Пропустить язык» заведёт копию основного языка с пометкой «перевод не готов».",
      lang_skip: "Пропустить язык целиком (перевод не готов)",
      lang_pending: "Перевод не готов (translation: pending)",
      lang_pending_h: "Пометка в SEO-блоке файла языка. Черновая сборка показывает страницу с плашкой, боевая её на этом языке не публикует: нет в карте сайта, hreflang и меню. Снимите, когда перевод готов.",
      lang_only: "На этом языке - только поля с текстом. Остальное (тип, порядок, картинки, флаги) общее и правится на основном языке.",
      need_tr: "нужен перевод", from_main: "на основном языке: ",
      errors: "Не сохранится, пока не исправлено:", warnings: "Замечания (сохранить можно):",
      readonly: "только для чтения: ", default: "по умолчанию: ", default_from: " (из {x})", empty: "пусто",
      unset: "- не задано -", yes: "да", no: "нет", root: "- корень сайта -",
      add: "+ Добавить", remove: "Убрать", up: "↑", down: "↓", item: "Пункт",
      sections: "Блоки страницы", add_section: "+ Блок", remove_section: "Убрать блок",
      add_section_h: "Новый блок (секция «## Заголовок {#якорь}») на всех языках. На языках с готовым переводом блок появится с текстом основного языка и пометкой «перевод не готов».",
      remove_section_h: "Убирает блок вместе с заголовком на всех языках. Соседние блоки не трогаются.",
      section_ro: "Блоки этой страницы правятся в файле: ",
      sec_anchor: "Якорь блока (латиницей)", sec_anchor_h: "Имя блока: по нему тема ставит его на место, по нему же ссылка #якорь.",
      sec_heading: "Заголовок", sec_heading_h: "Текст после ## - его видит посетитель.", sec_kind: "Форма блока",
      sec_kind_h: "Как блок записан и как тема его рисует. Подробности и живые примеры - на вкладке «Справка темы».",
      sec_first: "Первый пункт - по нему движок узнает форму блока:", sec_suggested: "Блоки типа, которых нет на странице:",
      cancel: "Отмена", create: "Создать", ok: "Готово",
      d_page: "Новая страница", d_category: "Новая категория",
      d_name: "Имя (латиница, цифры, дефисы)", d_name_h: "Имя файла и часть адреса: about-agency → /about-agency/. Потом его можно переименовать.",
      d_category_in: "Категория", d_category_in_h: "Папка, в которой будет страница. Нет нужной - создайте категорию.",
      d_parent: "Внутри категории", d_type: "Тип страницы", d_type_h: "Каким шаблоном темы страница рисуется и какие блоки у неё есть.",
      d_children: "Тип страниц внутри", d_children_h: "Какой тип получат новые страницы в этой категории.",
      d_view: "Вид списка страниц", d_title: "Заголовок (можно потом)", d_title_h: "title страницы: строка в выдаче поисковика и на вкладке браузера.",
      d_bad_name: "Имя - латиница, цифры и дефисы: about-agency.",
      exists: "Уже есть - открыта на правку.", created_draft: "Заготовка открыта: файлы появятся после «Сохранить».",
      saved: "Сохранено", nothing: "Ничего не изменилось.", created: "Создано", written: "Записано", moved: "Перенесено",
      redirects: "301", site_yaml: "site.yaml: меню", pending_files: "перевод не готов", cats: "Создана категория",
      error: "Не сохранено", build_bad: "Черновая сборка не прошла", loading: "Загружаю…", check_ok: "Проверка пройдена", check_bad: "Проверка нашла ошибки",
      building: "Собираю черновую версию…", built: "Черновая версия собрана", open_page: "Открыть страницу",
      ref_load: "Собрать и показать", ref_reload: "Обновить", ref_lead: "Справка собирается из описания темы и её демо-страниц: каждый блок с живым примером и исходным markdown рядом.",
      leave: "Есть несохранённые правки. Уйти без сохранения?",
      upload: "Загрузить", upload_h: "Картинка ляжет в папку media/ сайта. Ширину и пропорции проверит та же проверка, что у heron check.",
      uploaded: "Загружено", limits_w: "от {w} px в ширину", limits_r: "пропорции {r}",
      schema_h: "Строки «свойство: значение» - уточнения разметки schema.org этой страницы поверх site.yaml.",
      lines_h: "Каждая строка - отдельный пункт.",
      no_key: "нет ключа",
      not_created: "файла нет - появится, если перевести поля или отметить «Пропустить язык»",
      implicit: "без _index.md", implicit_h: "Папка без своей страницы _index.md (так было в 0.2): сайт собирается, раздел работает. Откройте её и нажмите «Сохранить», чтобы завести категорию явно - то же, что heron category add. Заполните поля раздела на каждом языке, где в папке есть страницы: на языке, где раздел не переведён, прод не покажет и страниц внутри - студия спросит, прежде чем так записать.",
    },
    en: {
      tab_site: "Site", tab_pages: "Pages", tab_ref: "Theme reference",
      tab_site_h: "Settings of the whole site: site.yaml - name, languages, markup, publishing, theme.",
      tab_pages_h: "Categories and pages in every language: create, edit, move.",
      tab_ref_h: "What the theme can do: page types, blocks with live examples from the demo, category views.",
      tree: "Categories and pages", new_page: "+ Page", new_category: "+ Category", check_site: "Check",
      new_page_h: "A new page in every language of the site at once. If it exists, it opens for editing.",
      new_category_h: "A category is a folder with its own page: title, description, how the pages inside are listed. Any depth.",
      check_site_h: "The same check as heron check in the terminal: the whole site, nothing is built.",
      tree_h: "Drag a page or a category onto another category (or onto “To the root”) to move it: the files move in every language, the old addresses get a 301.",
      to_root: "To the site root", legend: "ru - file exists · DE! - translation not ready · struck through - no file",
      pick: "Pick a page on the left or create a new one.",
      page_word: "Page", category_word: "Category", home: "Home", new: "new", dirty: "not saved",
      save: "Save", saving: "Saving…", preview: "Preview", revert: "Discard edits", rename: "Rename",
      save_h: "Writes the files of every language. Only the fields you edited change: the rest of the files stays byte for byte.",
      preview_h: "Builds a draft of the site (as heron serve does) and gives a link to this page.",
      revert_h: "Forget the unsaved edits and show the files as they are on disk.",
      rename_h: "A new file name and address. The files move in every language, the old address gets a 301.",
      rename_q: "New name (latin letters, digits, hyphens):", move_q: "Move “{a}” to “{b}”? The files move in every language, the old addresses get a 301.",
      main_lang: "main language", lang_new: "There is no file in this language yet. Translate the fields below - or leave them empty: then the language gets the mark “translation not ready” (translation: pending) and stays out of the production build until the translation is there.",
      lang_absent: "The page has no file in this language. Translate the fields below - the file appears with the translation. Leave them empty - no file is created. “Skip the language” makes a copy of the main language marked “translation not ready”.",
      lang_skip: "Skip the whole language (translation not ready)",
      lang_pending: "Translation not ready (translation: pending)",
      lang_pending_h: "A mark in the SEO block of the language file. The draft build shows the page with a banner, the production build does not publish it in this language: not in the sitemap, hreflang or menu. Clear it when the translation is ready.",
      lang_only: "This language has only the fields with text. The rest (type, order, pictures, flags) is shared and edited in the main language.",
      need_tr: "needs translation", from_main: "in the main language: ",
      errors: "Will not save until fixed:", warnings: "Remarks (saving is fine):",
      readonly: "read only: ", default: "default: ", default_from: " (from {x})", empty: "empty",
      unset: "- not set -", yes: "yes", no: "no", root: "- site root -",
      add: "+ Add", remove: "Remove", up: "↑", down: "↓", item: "Item",
      sections: "Blocks of the page", add_section: "+ Block", remove_section: "Remove block",
      add_section_h: "A new block (a section “## Heading {#anchor}”) in every language. Languages with a ready translation get it with the main language text and the mark “translation not ready”.",
      remove_section_h: "Removes the block with its heading in every language. Neighbouring blocks stay as they are.",
      section_ro: "The blocks of this page are edited in the file: ",
      sec_anchor: "Block anchor (latin letters)", sec_anchor_h: "The name of the block: the theme places the block by it, a #anchor link uses it too.",
      sec_heading: "Heading", sec_heading_h: "The text after ## - the visitor sees it.", sec_kind: "Block form",
      sec_kind_h: "How the block is written and how the theme draws it. Details and live examples are on the Theme reference tab.",
      sec_first: "The first item - the engine recognises the block form by it:", sec_suggested: "Blocks of the type that the page lacks:",
      cancel: "Cancel", create: "Create", ok: "Done",
      d_page: "New page", d_category: "New category",
      d_name: "Name (latin letters, digits, hyphens)", d_name_h: "The file name and part of the address: about-agency → /about-agency/. You can rename it later.",
      d_category_in: "Category", d_category_in_h: "The folder the page goes into. No fitting one - create a category.",
      d_parent: "Inside the category", d_type: "Page type", d_type_h: "Which theme template draws the page and which blocks it has.",
      d_children: "Type of the pages inside", d_children_h: "The type new pages in this category get.",
      d_view: "How the pages are listed", d_title: "Title (can wait)", d_title_h: "The page title: the line in search results and on the browser tab.",
      d_bad_name: "The name is latin letters, digits and hyphens: about-agency.",
      exists: "Already exists - opened for editing.", created_draft: "A draft is open: the files appear after “Save”.",
      saved: "Saved", nothing: "Nothing changed.", created: "Created", written: "Written", moved: "Moved",
      redirects: "301", site_yaml: "site.yaml: menu", pending_files: "translation not ready", cats: "Category created",
      error: "Not saved", build_bad: "The draft build failed", loading: "Loading…", check_ok: "The check passed", check_bad: "The check found errors",
      building: "Building a draft…", built: "The draft is built", open_page: "Open the page",
      ref_load: "Build and show", ref_reload: "Refresh", ref_lead: "The reference is built from the theme description and its demo pages: every block with a live example and its markdown source side by side.",
      leave: "There are unsaved edits. Leave without saving?",
      upload: "Upload", upload_h: "The picture goes into the media/ folder of the site. Width and proportions are checked by the same check as heron check.",
      uploaded: "Uploaded", limits_w: "at least {w} px wide", limits_r: "proportions {r}",
      schema_h: "Lines “property: value” - refinements of the schema.org markup of this page over site.yaml.",
      lines_h: "Every line is a separate item.",
      no_key: "no key",
      not_created: "no file - it appears once you translate fields or tick “Skip the language”",
      implicit: "no _index.md", implicit_h: "A folder without its own page _index.md (as in 0.2): the site builds, the section works. Open it and press “Save” to make it a category explicitly - the same as heron category add. Fill in the section fields in every language with pages in the folder: where the section is not translated, prod does not show the pages inside either - the studio asks before writing it so.",
    },
  };
  const tr = (k, vars) => {
    let s = (TT[L] && TT[L][k]) || TT.en[k] || k;
    for (const [a, b] of Object.entries(vars || {})) s = s.split("{" + a + "}").join(String(b));
    return s;
  };
  const S = {
    tab: "site", tree: null, target: null, state: null, ans: {}, ops: [], key: null, skip: {},
    edit: null, seq: 0, timer: null, busy: false, refBuilt: false, help: new Set(), preview: null, loading: false,
    opening: 0, treeSeq: 0,
  };
  // Просмотр, справка темы и картинки - на своём порту (другой источник, origin): скрипты темы
  // там не дотягиваются ни до ключа, ни до /api. Ключ просмотра - только смотреть.
  // Порт - от адреса этой страницы, не от внутренних портов сервера: docker мог пробросить
  // их со сдвигом (-p 9000:8000 -p 9001:8001). Та же формула - у CSP (server.py, _shift).
  const pvOrigin = (loc, P) => {
    const seen = loc.port ? Number(loc.port) : (loc.protocol === "https:" ? 443 : 80);
    const studio = Number(P.studio || P.port - 1);
    let port = seen - studio + Number(P.port);
    if (!(port >= 1 && port <= 65535)) port = Number(P.port);
    return loc.protocol + "//" + loc.hostname + ":" + port;
  };
  const pv = (path) => {
    if (!S.preview) return "about:blank";
    const sep = path.includes("?") ? "&" : "?";
    return pvOrigin(location, S.preview) + path + sep + "k=" + encodeURIComponent(S.preview.key);
  };
  const SANDBOX = "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox";
  const dirty = () => Object.values(S.ans).some((v) => Object.keys(v).length) || S.ops.length > 0 || S.key !== null || Object.values(S.skip).some(Boolean);

  async function api(name, body, raw) {
    const opts = { method: "POST", headers: { "X-Heron-Token": TOKEN } };
    if (raw) { opts.body = raw; } else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify({ ...(body || {}), lang: L }); }
    const r = await fetch("/api/studio/" + name + (raw ? body : ""), opts);
    const j = await r.json().catch(() => ({ ok: false, error: String(r.status) }));
    return j;
  }
  const errLines = (j) => [j.error, j.hint].filter(Boolean);
  // Ошибки сборки - как в терминале: код, файл и строка, что случилось, что сделать.
  const buildLines = (j) => (j.errors || []).map((e) => (typeof e === "string" ? e
    : (e.code ? e.code + " " : "") + (e.path ? e.path + (e.line ? ":" + e.line : "") + ": " : "") + (e.message || "") + (e.hint ? " - " + e.hint : "")))
    .concat(errLines(j));

  // --- вкладки -------------------------------------------------------------------------
  function tabs() {
    const nav = h("nav", { class: "studio-tabs", "aria-label": "studio" }, h("div", { class: "in", role: "tablist" },
      ...["site", "pages", "ref"].map((name) => h("button", { type: "button", role: "tab", id: "tab-btn-" + name, title: tr("tab_" + name + "_h"), "aria-selected": String(S.tab === name), onclick: () => setTab(name) }, tr("tab_" + name)))));
    const old = $("nav.studio-tabs");
    if (old) old.replaceWith(nav); else $("header.top").after(nav);
  }
  function setTab(name) {
    if (S.tab === name) return;
    S.tab = name;
    document.body.dataset.tab = name;
    $("#tab-site").hidden = name !== "site";
    $("#tab-pages").hidden = name !== "pages";
    $("#tab-ref").hidden = name !== "ref";
    $("#save").classList.toggle("st-hidden", name !== "site");
    tabs();
    if (name === "pages") { if (!S.tree) loadTree(); else renderPages(); }
    if (name === "ref") renderRef();
    window.scrollTo(0, 0);
  }

  // --- подсказка и справка ---------------------------------------------------------------
  function qm(id, help, example) {
    if (!help && !example) return null;
    const open = S.help.has(id);
    const box = h("div", { class: "st-help", hidden: !open }, help || "", example ? h("pre", {}, example) : null);
    const btn = h("button", { type: "button", class: "st-qm", "aria-expanded": String(open), "aria-label": "?", title: "?", onclick: () => {
      const now = box.hidden; box.hidden = !now; btn.setAttribute("aria-expanded", String(now));
      if (now) S.help.add(id); else S.help.delete(id);
    } }, "?");
    return [btn, box];
  }
  function helpBtn(key) { return qm("ui:" + key, tr(key)); }

  // --- дерево --------------------------------------------------------------------------
  // Ответ на устаревший запрос дерева (пришёл новый) отбрасывается: дерево - от последнего.
  async function loadTree() {
    const seq = ++S.treeSeq;
    const j = await api("tree");
    if (seq !== S.treeSeq) return;
    if (!j.ok) { note("bad", tr("error"), errLines(j)); return; }
    S.tree = j;
    renderPages();
  }
  function nodeName(n) { return n.key === "" ? tr("home") : n.key.split("/").at(-1); }
  function nested() {
    const items = S.tree.items;
    const kids = {};
    for (const n of items) {
      const parent = n.key === "" ? null : (n.key.includes("/") ? n.key.slice(0, n.key.lastIndexOf("/")) : "");
      (kids[parent === null ? "#" : parent] = kids[parent === null ? "#" : parent] || []).push(n);
    }
    return kids;
  }
  function treeNode(n, kids) {
    const on = S.target && S.target.key === n.key && (S.target.kind === "category") === n.category;
    const langs = n.implicit ? h("span", { class: "st-langs" }, h("span", { class: "st-lang implicit" }, tr("implicit"))) : h("span", { class: "st-langs" }, ...S.tree.languages.map((code) => {
      const st = n.langs[code];
      return h("span", { class: "st-lang " + st, title: code + ": " + st }, st === "pending" ? code + "!" : code);
    }));
    const row = h("div", { class: "st-node" + (on ? " on" : "") + (n.implicit ? " implicit" : ""), role: "treeitem", "data-key": n.key, "data-kind": n.category ? "category" : "page", "data-implicit": n.implicit ? "true" : null, title: n.implicit ? tr("implicit_h") : (n.title || "") + " · " + (n.key || "/"),
      draggable: n.key !== "" ? "true" : null,
      onclick: () => choose({ kind: n.category ? "category" : "page", key: n.key }) },
      h("span", { class: "st-icon" }, n.category ? "▸" : "·"), h("span", { class: "st-name" }, nodeName(n) + (n.title && n.title !== nodeName(n) ? " - " + n.title : "")), langs);
    if (n.key !== "") row.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", JSON.stringify({ key: n.key, kind: n.category ? "category" : "page" })); });
    if (n.category || n.key === "") dropZone(row, n.category ? n.key : "");
    const li = h("li", {}, row);
    const sub = kids[n.key] && n.key !== "" ? kids[n.key] : null;
    if (sub && sub.length) li.append(h("ul", { class: "st-nodes", role: "group" }, ...sub.map((c) => treeNode(c, kids))));
    return li;
  }
  function dropZone(el, into) {
    el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drop"); });
    el.addEventListener("dragleave", () => el.classList.remove("drop"));
    el.addEventListener("drop", (e) => {
      e.preventDefault(); el.classList.remove("drop");
      let what; try { what = JSON.parse(e.dataTransfer.getData("text/plain")); } catch { return; }
      move(what, into);
    });
  }
  async function move(what, into) {
    const name = what.key.split("/").at(-1);
    const key = into ? into + "/" + name : name;
    if (key === what.key || (what.kind === "category" && (into + "/").startsWith(what.key + "/"))) return;
    if (!confirm(tr("move_q", { a: what.key, b: into || "/" }))) return;
    const body = { target: what, answers: { key } };
    let j = await api("save", body);
    // перенос в папку 0.2 заводит раздел попутно и может спрятать переведённые страницы:
    // тот же вопрос, что у «Сохранить»; отказ - ничего не записано и не перенесено
    if (j.ok && j.confirm) {
      if (!window.confirm(j.confirm.message)) return;
      j = await api("save", { ...body, confirm_pending: true });
    }
    if (!j.ok) { note("bad", tr("error"), errLines(j)); return; }
    report(j.saved);
    if (S.target && S.target.key === what.key && S.target.kind === what.kind) { S.target = j.state.target; S.state = j.state; }
    await loadTree();
  }
  function treePanel() {
    const kids = nested();
    const top = (kids["#"] || []).concat(kids[""] || []);
    const root = h("div", { class: "st-root" }, tr("to_root"));
    dropZone(root, "");
    return h("aside", { class: "st-panel st-tree", "aria-label": tr("tree") },
      h("div", { class: "st-row" }, h("h2", {}, tr("tree")), ...(helpBtn("tree_h") || [])),
      h("div", { class: "st-row" },
        h("button", { type: "button", class: "st-btn", id: "st-new-page", title: tr("new_page_h"), onclick: () => newDialog("page") }, tr("new_page")),
        h("button", { type: "button", class: "st-btn", id: "st-new-category", title: tr("new_category_h"), onclick: () => newDialog("category") }, tr("new_category")),
        h("button", { type: "button", class: "st-btn", id: "st-check", title: tr("check_site_h"), onclick: siteCheck }, tr("check_site"))),
      h("ul", { class: "st-nodes", role: "tree" }, ...top.map((n) => treeNode(n, kids))), root,
      h("div", { class: "st-legend" }, tr("legend")));
  }

  // --- открыть, проверить, записать -------------------------------------------------------
  function request() {
    const answers = {};
    for (const [code, values] of Object.entries(S.ans)) if (Object.keys(values).length) answers[code] = { ...values };
    for (const [code, skip] of Object.entries(S.skip)) if (skip) answers[code] = "pending";
    if (S.key !== null) answers.key = S.key;
    return { target: S.target, ops: S.ops, answers };
  }
  function reset() { S.ans = {}; S.ops = []; S.key = null; S.skip = {}; }
  // Пока форма грузится, её поля заперты: ввод не уходит ни в прежнюю страницу, ни в пустоту.
  // Язык вкладки (S.edit) остаётся прежним до ответа: правки не теряются молча.
  // Запросов open может быть несколько подряд (смена языка интерфейса шлёт дерево и open
  // дважды): у каждого свой номер, ответ на устаревший отбрасывается, а форму отпирает
  // только ответ последнего - уже после того, как форма нарисована по нему.
  function lock(on) { S.loading = on; paintLock(); }
  function paintLock() {
    const box = $("#st-editor"); if (!box) return;
    const on = S.loading;
    box.classList.toggle("st-loading", on);
    box.setAttribute("aria-busy", String(on));
    for (const el of box.querySelectorAll("input, textarea, select, button")) {
      if (on) { if (!el.dataset.locked) { el.dataset.locked = el.disabled ? "was" : "1"; el.disabled = true; } }
      else if (el.dataset.locked) { el.disabled = el.dataset.locked === "was"; delete el.dataset.locked; }
    }
  }
  // Запрос open под своим номером; null - пока он шёл, ушёл новый (тот и отопрёт форму).
  async function openRequest() {
    const seq = ++S.opening;
    lock(true);
    let j;
    try { j = await api("open", request()); } catch (err) { j = { ok: false, error: String(err) }; }
    return seq === S.opening ? j : null;
  }
  async function choose(target, keep) {
    if (!keep && dirty() && !confirm(tr("leave"))) return;
    const was = S.edit;
    S.target = target; if (!keep) reset();
    const j = await openRequest();
    if (!j) return;
    if (!j.ok) { lock(false); note("bad", tr("error"), errLines(j)); S.target = S.state ? S.state.target : null; return; }
    S.state = j.state; S.target = target;
    S.edit = keep && was && j.state.languages.includes(was) ? was : j.state.default_lang;
    renderPages();
    lock(false);
  }
  function changed() {
    clearTimeout(S.timer);
    renderBadges();
    S.timer = setTimeout(check, 350);
  }
  async function check() {
    const seq = ++S.seq;
    const j = await api("check", request());
    if (seq !== S.seq) return;
    if (!j.ok) { showIssues([[j.error, j.hint].filter(Boolean).join(" ")], []); return; }
    const before = signature(S.state), after = signature(j.state);
    S.state = j.state;
    if (before !== after) renderEditor(); else markIssues();
  }
  function signature(st) { return st ? Object.entries(st.fields).map(([c, list]) => c + ":" + list.map((f) => f.path + (f.editable ? "" : "!")).join(",")).join("|") + "|" + st.type : ""; }
  async function save() {
    if (!S.state || S.busy) return;
    clearTimeout(S.timer);
    S.busy = true; const btn = $("#st-save"); if (btn) { btn.disabled = true; btn.textContent = tr("saving"); }
    try {
      let j = await api("save", request());
      // новый блок снимет переведённые языки с публикации: спросить, назвав их
      if (j.ok && j.confirm) {
        if (!window.confirm(j.confirm.message)) return;
        j = await api("save", { ...request(), confirm_pending: true });
      }
      if (!j.ok) { note("bad", tr("error"), errLines(j)); return; }
      report(j.saved);
      reset(); S.state = j.state; S.target = j.state.target;
      await loadTree();
    } finally { S.busy = false; const b = $("#st-save"); if (b) { b.disabled = false; b.textContent = tr("save"); } }
  }
  function report(saved) {
    const lines = [];
    for (const k of saved.categories) lines.push(tr("cats") + ": " + k);
    for (const [a, b] of saved.moved) lines.push(tr("moved") + ": " + a + " → " + b);
    if (saved.created.length) lines.push(tr("created") + ": " + saved.created.map((r) => r + (saved.pending.includes(r) ? " (" + tr("pending_files") + ")" : "")).join(", "));
    if (saved.written.length) lines.push(tr("written") + ": " + saved.written.map((r) => r + (saved.pending.includes(r) ? " (" + tr("pending_files") + ")" : "")).join(", "));
    for (const [a, b] of saved.redirects) lines.push(tr("redirects") + ": " + a + " → " + b);
    if (saved.site_yaml) lines.push(tr("site_yaml"));
    note("ok", lines.length ? tr("saved") : tr("nothing"), lines);
  }

  // --- редактор ------------------------------------------------------------------------
  function renderPages() {
    const main = $("#tab-pages");
    if (!S.tree) { main.replaceChildren(h("p", { class: "st-empty" }, "…")); return; }
    main.replaceChildren(h("div", { class: "st-grid" }, treePanel(), h("section", { class: "st-panel st-editor", id: "st-editor" })));
    renderEditor();
  }
  function renderBadges() {
    const b = $("#st-dirty"); if (b) b.hidden = !dirty();
    for (const box of document.querySelectorAll(".st-field[data-path]")) box.classList.toggle("changed", !!(S.ans[S.edit] && box.dataset.path in S.ans[S.edit]));
  }
  function fieldsOf(code) { return (S.state.fields[code] || []); }
  function mainValue(path) { const f = fieldsOf(S.state.default_lang).find((x) => x.path === path); return f ? f.value : undefined; }
  function created(code) { return !S.state.files[code].exists; }
  function shown(f) {
    const mine = S.ans[S.edit] || {};
    if (f.path in mine) return mine[f.path];
    if (S.edit !== S.state.default_lang && created(S.edit)) return f.type === "list" ? [] : "";
    return f.value;
  }
  function put(path, value) {
    if (!S.state || !S.state.languages.includes(S.edit)) return;  // формы нет - писать некуда
    const mine = (S.ans[S.edit] = S.ans[S.edit] || {});
    const blank = value === null || value === "" || (Array.isArray(value) && !value.length);
    // новый файл языка: пустое поле - «не переведено», а не «стереть значение»
    if (blank && S.edit !== S.state.default_lang && created(S.edit)) delete mine[path];
    else mine[path] = value;
    changed();
  }
  function renderEditor() {
    const box = $("#st-editor"); if (!box) return;
    const st = S.state;
    if (!st || !S.target) { box.replaceChildren(h("p", { class: "st-empty" }, tr("pick"))); paintLock(); return; }
    if (!st.languages.includes(S.edit)) S.edit = st.default_lang;
    const cat = st.target.kind === "category";
    const title = (cat ? tr("category_word") : tr("page_word")) + " " + (st.target.key || "/");
    const head = h("div", { class: "st-head" },
      h("h2", {}, title, st.new ? h("span", { class: "st-badge new" }, tr("new")) : null, h("span", { class: "st-badge dirty", id: "st-dirty", hidden: !dirty() }, tr("dirty"))),
      h("div", { class: "st-row" },
        h("button", { type: "button", class: "st-btn primary", id: "st-save", title: tr("save_h"), onclick: save }, tr("save")),
        h("button", { type: "button", class: "st-btn", id: "st-preview", title: tr("preview_h"), onclick: preview }, tr("preview")),
        st.target.key ? h("button", { type: "button", class: "st-btn", id: "st-rename", title: tr("rename_h"), onclick: rename }, tr("rename")) : null,
        h("button", { type: "button", class: "st-btn", title: tr("revert_h"), onclick: () => choose(S.state.new ? S.target : S.state.target, false) }, tr("revert"))));
    const files = h("div", { class: "st-files" }, ...st.languages.map((code) => {
      const f = st.files[code];
      if (!f.exists && !f.planned) return h("div", { class: "muted" }, "  " + f.rel + " - " + tr("not_created"));
      return h("div", { class: f.pending ? "pending" : "" }, (f.exists ? "  " : "+ ") + f.rel + (f.pending ? " - " + tr("pending_files") : ""));
    }));
    const langtabs = h("div", { class: "st-langtabs", role: "tablist" }, ...st.languages.map((code) => h("button", {
      type: "button", role: "tab", "data-lang": code, class: st.files[code].pending ? "pending" : "", "aria-selected": String(code === S.edit),
      title: code === st.default_lang ? tr("main_lang") : (st.files[code].pending ? tr("lang_pending") : code),
      onclick: () => { S.edit = code; renderEditor(); } }, code.toUpperCase() + (code === st.default_lang ? " · " + tr("main_lang") : ""))));
    box.replaceChildren(head, files, langtabs, langNote(), h("div", { id: "st-issues" }), ...groupsOf());
    markIssues();
    paintLock();  // форма нарисована во время загрузки - заперта, как и прежняя
  }
  function langNote() {
    const st = S.state, code = S.edit;
    if (code === st.default_lang) return h("div");
    if (created(code)) {
      const cb = h("input", { type: "checkbox", id: "st-skip" });
      cb.checked = !!S.skip[code];
      cb.addEventListener("change", () => { S.skip[code] = cb.checked; changed(); });
      return h("div", { class: "st-note warn" }, h("p", {}, tr(st.new ? "lang_new" : "lang_absent")), h("label", { class: "check" }, cb, tr("lang_skip")), h("p", { class: "muted" }, tr("lang_only")));
    }
    const mine = S.ans[code] || {};
    const cb = h("input", { type: "checkbox", id: "st-pending" });
    cb.checked = "translation" in mine ? mine.translation === "pending" : st.files[code].pending;
    cb.addEventListener("change", () => put("translation", cb.checked ? "pending" : null));
    return h("div", { class: "st-note" + (cb.checked ? " warn" : "") }, h("div", { class: "st-row" }, h("label", { class: "check", title: tr("lang_pending_h") }, cb, tr("lang_pending")), ...(helpBtn("lang_pending_h") || [])), h("p", { class: "muted" }, tr("lang_only")));
  }
  function groupsOf() {
    const st = S.state, list = fieldsOf(S.edit);
    const out = [];
    for (const g of st.groups) {
      const items = list.filter((f) => f.group === g.name);
      if (g.name === "section") { out.push(sectionsBox(items, g.title)); continue; }
      if (!items.length) continue;
      out.push(h("div", { class: "st-group", "data-group": g.name }, h("h3", {}, g.title), h("div", { class: "st-fields" }, ...items.map(field))));
    }
    return out;
  }
  function sectionsBox(items, title) {
    const st = S.state, main = S.edit === st.default_lang;
    const by = new Map();
    for (const f of items) { if (!by.has(f.section)) by.set(f.section, []); by.get(f.section).push(f); }
    const boxes = [];
    for (const [id, fs] of by) {
      const present = fs.some((f) => f.present) || id === "intro";
      const meta = st.sections.present.find((s) => s.id === id);
      const kind = (meta && meta.kind) || fs[0].kind;
      const rm = main && id !== "intro" && meta && !st.sections.readonly ? h("button", { type: "button", class: "st-btn danger", title: tr("remove_section_h"), onclick: () => removeSection(id) }, tr("remove_section")) : null;
      boxes.push(h("div", { class: "st-section", "data-section": id },
        h("div", { class: "st-section-head" }, h("b", {}, h("code", {}, "#" + id), kind ? " · " + kind : "", present ? "" : " (" + tr("empty") + ")"), rm),
        h("div", { class: "st-fields" }, ...fs.map(field))));
    }
    const add = main && !st.sections.readonly ? h("div", { class: "st-row" }, h("button", { type: "button", class: "st-btn", id: "st-add-section", title: tr("add_section_h"), onclick: sectionDialog }, tr("add_section")), ...(helpBtn("add_section_h") || [])) : null;
    return h("div", { class: "st-group", "data-group": "section" }, h("h3", {}, title || tr("sections")),
      st.sections.readonly ? h("p", { class: "st-ro" }, tr("section_ro") + st.sections.readonly) : null, ...boxes, add);
  }

  // --- поле ----------------------------------------------------------------------------
  function label(f) {
    const text = f.hint || f.name;
    return h("div", { class: "st-label", title: f.hint || "" }, h("label", { for: "f-" + f.path }, text), h("code", {}, f.path.startsWith("sections.") ? f.name : f.path),
      f.required ? h("span", { class: "st-req" }, "*") : null, ...(qm(S.edit + ":" + f.path, f.help, f.example) || []));
  }
  function field(f) {
    const box = h("div", { class: "st-field", "data-path": f.path, "data-type": f.type });
    const lab = label(f);
    const help = lab.querySelector(".st-help"); if (help) help.remove();
    box.append(lab);
    if (help) box.append(help);
    const control = controlFor(f);
    box.append(control);
    if (!f.editable) box.append(h("div", { class: "st-ro" }, tr("readonly") + (f.readonly || "")));
    box.append(h("div", { class: "st-default", "data-default": "" }), h("div", { class: "st-main", "data-main": "" }), h("div", { class: "st-msg" }));
    if (S.ans[S.edit] && f.path in S.ans[S.edit]) box.classList.add("changed");
    return box;
  }
  const blankValue = (v) => v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length);
  // Умолчание и текст основного языка у полей - по последней проверке сервера.
  function refreshHints() {
    const list = fieldsOf(S.edit), mine = S.ans[S.edit] || {};
    for (const box of document.querySelectorAll("#st-editor .st-field[data-path]")) {
      const f = list.find((x) => x.path === box.dataset.path);
      if (!f) continue;
      const def = box.querySelector(":scope > [data-default]"), main = box.querySelector(":scope > [data-main]");
      if (def) def.textContent = !blankValue(f.default) && blankValue(f.value) ? tr("default") + human(f.default) + (f.default_from ? tr("default_from", { x: f.default_from }) : "") : "";
      if (!main) continue;
      const value = S.edit !== S.state.default_lang ? mainValue(f.path) : undefined;
      if (blankValue(value)) { main.textContent = ""; continue; }
      const todo = created(S.edit) && !(f.path in mine) && !S.skip[S.edit];
      main.className = todo ? "st-todo" : "st-default";
      main.textContent = (todo ? tr("need_tr") + " · " : "") + tr("from_main") + human(value).slice(0, 160);
    }
  }
  function note(kind, title, lines) {
    const el = $("#toast"); el.className = "toast" + (kind === "bad" ? " bad" : "");
    el.replaceChildren(h("button", { type: "button", "aria-label": "close", onclick: () => (el.style.display = "none") }, "×"), h("b", {}, title), lines && lines.length ? h("ul", {}, ...lines.map((x) => h("li", {}, x))) : "");
    el.style.display = "block";
  }
  function human(v) {
    if (v === true) return tr("yes"); if (v === false) return tr("no");
    if (Array.isArray(v)) return v.map((x) => (typeof x === "object" && x ? Object.values(x).join(" · ") : String(x))).join("; ");
    if (v && typeof v === "object") return Object.entries(v).map(([a, b]) => a + ": " + b).join("; ");
    return String(v);
  }
  function controlFor(f) {
    const value = shown(f);
    const off = !f.editable;
    const id = "f-" + f.path;
    const ph = S.edit !== S.state.default_lang && created(S.edit) ? human(mainValue(f.path) ?? "") : (f.default !== null && f.default !== undefined ? human(f.default) : "");
    if (f.type === "markdown") return textarea(id, value, off, ph, (v) => put(f.path, v));
    if (f.type === "number") return input(id, "number", value, off, ph, (v) => put(f.path, v === "" ? null : Number(v)));
    if (f.type === "date") return input(id, "date", value, off, "", (v) => put(f.path, v || null));
    if (f.type === "flag") return flag(id, f, value, off);
    if (f.type === "enum" || f.type === "ref") return choice(id, f, value, off);
    if (f.type === "image") return image(id, f, value, off, ph);
    if (f.type === "list") return listOf(f, value, off);
    if (f.type === "schema") return schema(id, f, value, off);
    return input(id, "text", value, off, ph, (v) => put(f.path, v));
  }
  function input(id, type, value, off, ph, on) {
    const el = h("input", { type, id, disabled: off, placeholder: ph || null });
    el.value = value === null || value === undefined ? "" : String(value);
    el.addEventListener("input", () => on(el.value));
    return el;
  }
  function textarea(id, value, off, ph, on) {
    const el = h("textarea", { id, disabled: off, placeholder: ph || null });
    el.value = value === null || value === undefined ? "" : String(value);
    el.rows = Math.min(12, Math.max(3, el.value.split("\n").length + 1));
    el.addEventListener("input", () => on(el.value));
    return el;
  }
  function flag(id, f, value, off) {
    const opts = f.where === "site.yaml" ? [["true", tr("yes")], ["false", tr("no")]] : [["", tr("unset")], ["true", tr("yes")], ["false", tr("no")]];
    const el = h("select", { id, disabled: off }, ...opts.map(([v, t]) => h("option", { value: v }, t)));
    el.value = value === true ? "true" : value === false ? "false" : "";
    el.addEventListener("change", () => put(f.path, el.value === "" ? null : el.value === "true"));
    return el;
  }
  function choice(id, f, value, off) {
    let values = (f.limits && f.limits.values) || [];
    if (f.name === "type") values = S.tree.types.map((t) => t.name);
    // тип страниц внутри: без главной и 404 - их даёт имя файла в корне языка, не категория
    if (f.name === "children_type") values = S.tree.types.map((t) => t.name).filter((t) => !SPECIAL.includes(t));
    const labels = {};
    for (const t of S.tree.types) labels[t.name] = t.hint;
    for (const o of f.fields || []) labels[o.name] = o.hint;
    let opts;
    if (f.type === "ref") {
      const self = S.state.target;
      const cats = S.tree.items.filter((n) => n.category && !(self.kind === "category" && (n.key === self.key || n.key.startsWith(self.key + "/"))));
      opts = [["", tr("root")], ...cats.map((n) => [n.key, n.key + (n.title ? " - " + n.title : "")])];
      if (S.key !== null) value = S.key.includes("/") ? S.key.slice(0, S.key.lastIndexOf("/")) : "";
    } else {
      opts = [["", tr("unset")], ...values.map((v) => [v, v + (labels[v] ? " - " + labels[v] : "")])];
    }
    const el = h("select", { id, disabled: off }, ...opts.map(([v, t]) => h("option", { value: v }, t)));
    el.value = value === null || value === undefined ? "" : String(value);
    if (f.type === "ref") el.addEventListener("change", () => { const name = S.state.target.key.split("/").at(-1); S.key = el.value ? el.value + "/" + name : name; if (S.key === S.state.key) S.key = null; changed(); });
    else el.addEventListener("change", () => put(f.path, el.value || null));
    return el;
  }
  function limitsText(limits) {
    const out = [];
    if (limits && limits.min_width) out.push(tr("limits_w", { w: limits.min_width }));
    if (limits && limits.ratio) out.push(tr("limits_r", { r: limits.ratio }));
    return out.join(", ");
  }
  function image(id, f, value, off, ph, on) {
    const write = on || ((v) => put(f.path, v || null));
    const el = input(id, "text", value, off, ph, (v) => { write(v); thumb(v); });
    const img = h("img", { alt: "", hidden: true });
    const thumb = (v) => { if (v && /^\/?media\//.test(v)) { img.src = pv("/_studio/" + v.replace(/^\//, "")); img.hidden = false; } else img.hidden = true; };
    thumb(value);
    img.addEventListener("error", () => { img.hidden = true; });
    const fileIn = h("input", { type: "file", accept: "image/*", disabled: off, "aria-label": tr("upload"), "data-upload": f.path });
    fileIn.addEventListener("change", async () => {
      const file = fileIn.files[0]; if (!file) return;
      const j = await api("upload", "?name=" + encodeURIComponent(file.name) + "&lang=" + L, file);
      if (!j.ok) { note("bad", tr("error"), errLines(j)); return; }
      // пока картинка грузилась, форму могли перерисовать: значение - в ответы, форму - заново
      el.value = j.path; write(j.path); thumb(j.path);
      if (!el.isConnected) renderEditor();
      note("ok", tr("uploaded"), [j.path + (j.width ? " · " + j.width + "×" + j.height + " px" : "")]);
    });
    const up = h("span", { class: "st-upload st-btn", title: tr("upload_h") }, tr("upload"), fileIn);
    const lim = limitsText(f.limits || f);
    return h("div", {}, h("div", { class: "st-image" }, img, el, off ? null : up), lim ? h("div", { class: "st-limits" }, lim) : null);
  }
  function schema(id, f, value, off) {
    const text = Object.entries(value || {}).map(([k, v]) => k + ": " + (typeof v === "object" ? JSON.stringify(v) : v)).join("\n");
    const el = textarea(id, text, off, "", (v) => {
      const out = {};
      for (const line of v.split("\n")) { const i = line.indexOf(":"); if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim(); }
      put(f.path, Object.keys(out).length ? out : null);
    });
    return h("div", {}, el, h("div", { class: "st-limits" }, tr("schema_h")));
  }
  // Список: пункты с полями блока (вопрос и ответ, термин и текст…) или строки.
  function listOf(f, value, off) {
    const rows = Array.isArray(value) ? JSON.parse(JSON.stringify(value)) : [];
    const subs = f.fields || null;
    const wrap = h("div", { class: "st-items", id: "f-" + f.path });
    const commit = () => put(f.path, JSON.parse(JSON.stringify(rows)));
    const draw = () => {
      wrap.replaceChildren(...rows.map((row, i) => {
        const bar = h("div", { class: "st-item-bar" }, h("span", {}, tr("item") + " " + (i + 1)), off ? null : h("span", {},
          h("button", { type: "button", "aria-label": tr("up"), disabled: i === 0, onclick: () => { [rows[i - 1], rows[i]] = [rows[i], rows[i - 1]]; commit(); draw(); } }, tr("up")), " ",
          h("button", { type: "button", "aria-label": tr("down"), disabled: i === rows.length - 1, onclick: () => { [rows[i + 1], rows[i]] = [rows[i], rows[i + 1]]; commit(); draw(); } }, tr("down")), " ",
          h("button", { type: "button", onclick: () => { rows.splice(i, 1); commit(); draw(); } }, tr("remove"))));
        const body = subs ? subs.map((s) => subField(f, s, row, i, off, commit)) : [subValue("f-" + f.path + "." + i, f.item || "markdown", row, off, (v) => { rows[i] = v; commit(); })];
        return h("div", { class: "st-item", "data-item": String(i) }, bar, ...body);
      }), off ? "" : h("button", { type: "button", class: "st-btn", "data-add": f.path, onclick: () => { rows.push(subs ? Object.fromEntries(subs.map((s) => [s.name, s.type === "list" ? [] : ""])) : ""); commit(); draw(); } }, tr("add")));
    };
    draw();
    return wrap;
  }
  function subField(f, s, row, i, off, commit) {
    const id = "f-" + f.path + "." + i + "." + s.name;
    const ctl = s.type === "image"
      ? image(id, { ...s, path: f.path + "." + i + "." + s.name, editable: !off, limits: s }, row[s.name] || "", off, "", (v) => { row[s.name] = v; commit(); })
      : subValue(id, s.type === "list" ? "lines" : s.type, row[s.name], off, (v) => { row[s.name] = v; commit(); });
    return h("div", { class: "st-field", "data-path": f.path + "." + i + "." + s.name },
      h("div", { class: "st-label", title: s.hint || "" }, h("label", { for: id }, s.hint || s.name), h("code", {}, s.name), s.required ? h("span", { class: "st-req" }, "*") : null, ...(qm(S.edit + ":" + f.path + ".*." + s.name, s.help, s.example) || [])),
      ctl, h("div", { class: "st-msg" }));
  }
  function subValue(id, type, value, off, on) {
    if (type === "lines") {
      const el = textarea(id, Array.isArray(value) ? value.join("\n") : (value || ""), off, "", (v) => on(v.split("\n").map((x) => x.trim()).filter(Boolean)));
      return h("div", {}, el, h("div", { class: "st-limits" }, tr("lines_h")));
    }
    if (type === "markdown") return textarea(id, value, off, "", on);
    return input(id, "text", value, off, "", on);
  }

  // --- замечания у полей -------------------------------------------------------------------
  function markIssues() {
    const st = S.state; if (!st) return;
    for (const box of document.querySelectorAll(".st-field")) { box.classList.remove("bad", "warn"); const m = box.querySelector(":scope > .st-msg"); if (m) m.replaceChildren(); }
    const list = st.issues[S.edit] || [];
    const loose = [];
    for (const issue of list) {
      let box = null, path = issue.path;
      while (path && !box) { box = document.querySelector('.st-field[data-path="' + CSS.escape(path) + '"]'); path = path.includes(".") ? path.slice(0, path.lastIndexOf(".")) : ""; }
      if (!box) { loose.push(issue); continue; }
      box.classList.add(issue.level === "error" ? "bad" : "warn");
      const m = box.querySelector(":scope > .st-msg");
      if (m) m.append(h("div", { class: "st-msg " + (issue.level === "error" ? "bad" : "warn") }, issue.message));
    }
    showIssues(st.errors, st.warnings);
    refreshHints();
    renderBadges();
  }
  function showIssues(errors, warnings) {
    const box = $("#st-issues"); if (!box) return;
    const parts = [];
    if (errors.length) parts.push(h("div", { class: "st-issues bad", role: "alert" }, h("b", {}, tr("errors")), h("ul", {}, ...errors.map((x) => h("li", {}, x)))));
    if (warnings.length) parts.push(h("details", { class: "st-issues warn" }, h("summary", {}, tr("warnings") + " " + warnings.length), h("ul", {}, ...warnings.map((x) => h("li", {}, x)))));
    box.replaceChildren(...parts);
  }

  // --- окна: новая страница, категория, блок -------------------------------------------------
  function dialog(title, body, onOk, okText) {
    const d = h("dialog", { class: "st-dialog", id: "st-dialog" });
    const err = h("p", { class: "err" });
    const ok = h("button", { type: "button", class: "st-btn primary", id: "st-dialog-ok" }, okText || tr("create"));
    ok.addEventListener("click", async () => { err.textContent = ""; const bad = await onOk(); if (bad) err.textContent = bad; else { d.close(); d.remove(); } });
    d.append(h("h3", {}, title), ...body, err, h("div", { class: "acts" }, h("button", { type: "button", class: "st-btn", onclick: () => { d.close(); d.remove(); } }, tr("cancel")), ok));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    const first = d.querySelector("input, select, textarea"); if (first) first.focus();
    return d;
  }
  function row(labelText, hintText, control) {
    return h("div", { class: "st-field" }, h("div", { class: "st-label", title: hintText || "" }, h("label", {}, labelText), ...(hintText ? qm("dlg:" + labelText, hintText) || [] : [])), control);
  }
  function select(options, value, attrs) {
    const el = h("select", attrs || {}, ...options.map(([v, t]) => h("option", { value: v }, t)));
    if (value !== undefined) el.value = value;
    return el;
  }
  function typeOptions() { return S.tree.types.map((t) => [t.name, t.name + (t.hint ? " - " + t.hint : "")]); }
  function catOptions() { return [["", tr("root")], ...S.tree.items.filter((n) => n.category).map((n) => [n.key, n.key + (n.title ? " - " + n.title : "")])]; }
  async function opened(target) {
    if (dirty() && !confirm(tr("leave"))) return;
    reset(); S.target = target;
    const j = await openRequest();
    if (!j) return null;
    if (!j.ok) { lock(false); return errLines(j).join(" "); }
    S.state = j.state; S.target = { ...target, key: j.state.target.key }; S.edit = j.state.default_lang;
    note("ok", j.state.new ? tr("created_draft") : tr("exists"), []);
    renderPages();
    lock(false);
    return null;
  }
  function childType(cat) {
    const node = S.tree.items.find((n) => n.category && n.key === cat);
    const kind = node ? S.tree.types.find((t) => t.name === node.type) : null;
    return (kind && kind.children_type) || S.tree.default_type.page;
  }
  function newDialog(kind) {
    const name = h("input", { type: "text", id: "st-d-name", autocomplete: "off", placeholder: kind === "page" ? "about-agency" : "services" });
    const cat = select(catOptions(), S.target && S.target.kind === "category" ? S.target.key : "", { id: "st-d-category" });
    const type = select(typeOptions(), kind === "page" ? childType(cat.value) : S.tree.default_type.category, { id: "st-d-type" });
    cat.addEventListener("change", () => { if (kind === "page") type.value = childType(cat.value); });
    const title = h("input", { type: "text", id: "st-d-title", autocomplete: "off" });
    const body = [h("div", { class: "st-fields" },
      row(tr("d_name"), tr("d_name_h"), name),
      row(kind === "page" ? tr("d_category_in") : tr("d_parent"), tr("d_category_in_h"), cat),
      row(tr("d_type"), tr("d_type_h"), type))];
    let children = null, view = null;
    if (kind === "category") {
      children = select([["", tr("unset")], ...typeOptions().filter(([t]) => !SPECIAL.includes(t))], "", { id: "st-d-children" });
      const views = () => { const t = S.tree.types.find((x) => x.name === type.value); return (t && t.views && t.views.options) || []; };
      view = select([["", tr("unset")]], "", { id: "st-d-view" });
      const fill = () => { view.replaceChildren(h("option", { value: "" }, tr("unset")), ...views().map((o) => h("option", { value: o.name }, o.name + (o.hint ? " - " + o.hint : "")))); };
      fill(); type.addEventListener("change", fill);
      const vt = S.tree.types.find((x) => x.name === type.value);
      body[0].append(row(tr("d_children"), tr("d_children_h"), children), row(tr("d_view"), vt && vt.views ? vt.views.help || vt.views.hint : "", view));
    }
    body[0].append(row(tr("d_title"), tr("d_title_h"), title));
    dialog(kind === "page" ? tr("d_page") : tr("d_category"), body, async () => {
      const parts = name.value.trim().replace(/^\/+|\/+$/g, "").split("/");
      if (!parts.every((p) => SLUG.test(p))) return tr("d_bad_name");
      const key = (cat.value ? cat.value + "/" : "") + parts.join("/");
      const target = { kind, key, type: type.value || null, title: title.value.trim() || null };
      if (kind === "category") { target.children_type = children.value || null; target.view = view.value || null; }
      return opened(target);
    });
  }
  function sectionDialog() {
    const st = S.state.sections;
    const anchor = h("input", { type: "text", id: "st-s-anchor", autocomplete: "off", placeholder: "faq" });
    const heading = h("input", { type: "text", id: "st-s-heading", autocomplete: "off" });
    const kinds = st.kinds;
    const kind = select(kinds.map((k) => [k.kind, k.kind + (k.hint ? " - " + k.hint : "")]), kinds.length ? kinds[0].kind : "", { id: "st-s-kind" });
    const extra = h("div", { class: "st-fields" });
    const values = {};
    const help = h("div");
    const fill = () => {
      const k = kinds.find((x) => x.kind === kind.value) || { fields: [] };
      for (const key of Object.keys(values)) delete values[key];
      const parts = [];
      if (k.auto && k.kind !== "prose") parts.push(h("p", { class: "muted" }, tr("sec_first")));
      for (const spec of k.fields) {
        if (!spec.required && !(k.auto && k.kind !== "prose")) continue;
        if (spec.type === "list") {
          const item = spec.fields ? Object.fromEntries(spec.fields.map((s) => [s.name, s.type === "list" ? [] : ""])) : "";
          values[spec.name] = [item];
          const fake = { path: "new." + spec.name, fields: spec.fields, item: spec.item, type: "list" };
          if (spec.fields) parts.push(h("div", { class: "st-item" }, ...spec.fields.map((s) => subField(fake, s, item, 0, false, () => {}))));
          else parts.push(row(spec.hint || spec.name, spec.help, subValue("st-s-" + spec.name, "lines", [], false, (v) => { values[spec.name] = v; })));
        } else {
          values[spec.name] = "";
          parts.push(row(spec.hint || spec.name, spec.help, subValue("st-s-" + spec.name, spec.type, "", false, (v) => { values[spec.name] = v; })));
        }
      }
      extra.replaceChildren(...parts);
      help.replaceChildren(...(qm("kind:" + k.kind, k.help, k.example) || []));
    };
    kind.addEventListener("change", fill);
    const suggested = st.suggested.length ? h("div", { class: "st-row" }, h("span", { class: "muted" }, tr("sec_suggested")), ...st.suggested.map((s) => h("button", { type: "button", class: "st-btn", title: s.hint || "", onclick: () => { anchor.value = s.id; if (s.kind && kinds.some((k) => k.kind === s.kind)) { kind.value = s.kind; fill(); } } }, s.id + (s.required ? " *" : "")))) : null;
    fill();
    dialog(tr("add_section"), [suggested, h("div", { class: "st-fields" }, row(tr("sec_anchor"), tr("sec_anchor_h"), anchor), row(tr("sec_heading"), tr("sec_heading_h"), heading), row(tr("sec_kind"), tr("sec_kind_h"), kind), help), extra], async () => {
      const a = anchor.value.trim();
      if (!SLUG.test(a)) return tr("d_bad_name");
      const clean = {};
      for (const [k, v] of Object.entries(values)) {
        if (Array.isArray(v)) { const items = v.filter((x) => (typeof x === "object" && x ? Object.values(x).join("").trim() : String(x).trim())); if (items.length) clean[k] = items; }
        else if (String(v).trim()) clean[k] = v;
      }
      const op = { op: "add_section", anchor: a, heading: heading.value.trim() || null, kind: kind.value || null, values: Object.keys(clean).length ? clean : null };
      S.ops.push(op);
      const j = await api("check", request());
      if (!j.ok) { S.ops.pop(); return errLines(j).join(" "); }
      S.state = j.state; renderEditor(); renderBadges();
      return null;
    }, tr("ok"));
  }
  function removeSection(id) {
    const added = S.ops.findIndex((o) => o.op === "add_section" && o.anchor === id);
    if (added >= 0) S.ops.splice(added, 1); else S.ops.push({ op: "remove_section", anchor: id });
    for (const code of Object.keys(S.ans)) for (const p of Object.keys(S.ans[code])) if (p.startsWith("sections." + id + ".")) delete S.ans[code][p];
    changed();
  }
  function rename() {
    const cur = S.key !== null ? S.key : S.state.target.key;
    const name = prompt(tr("rename_q"), cur.split("/").at(-1));
    if (name === null) return;
    if (!SLUG.test(name.trim())) { note("bad", tr("error"), [tr("d_bad_name")]); return; }
    const parent = cur.includes("/") ? cur.slice(0, cur.lastIndexOf("/")) + "/" : "";
    S.key = parent + name.trim();
    if (S.key === S.state.key) S.key = null;
    changed();
  }

  // --- проверка сайта, просмотр, справка темы ---------------------------------------------------
  async function siteCheck() {
    const btn = $("#st-check"); if (btn) btn.disabled = true;
    try {
      const j = await api("site-check");
      const lines = (j.errors || []).map((e) => (e.code ? e.code + " " : "") + (e.path ? e.path + (e.line ? ":" + e.line : "") + ": " : "") + e.message + (e.hint ? " - " + e.hint : ""))
        .concat((j.warnings || []).map((w) => (w.path ? w.path + ": " : "") + w.message));
      dialog(j.ok ? tr("check_ok") : tr("check_bad"), [h("ul", {}, ...lines.map((x) => h("li", {}, x)))], async () => null, tr("ok"));
    } finally { if (btn) btn.disabled = false; }
  }
  async function preview() {
    note("ok", tr("building"), []);
    const j = await api("preview", { target: S.state && !S.state.new ? S.state.target : null });
    if (!j.ok) { note("bad", tr("build_bad"), buildLines(j)); return; }
    const url = j.urls[S.edit] || j.urls[S.state.default_lang];
    S.refBuilt = true;
    const el = $("#toast"); el.className = "toast";
    el.replaceChildren(h("button", { type: "button", "aria-label": "close", onclick: () => (el.style.display = "none") }, "×"), h("b", {}, tr("built")),
      url ? h("p", { class: "st-links" }, h("a", { href: pv(url === "/" ? "/index.html" : url), target: "_blank", rel: "noopener noreferrer", id: "st-preview-link" }, tr("open_page"))) : null);
    el.style.display = "block";
  }
  async function renderRef(force) {
    const main = $("#tab-ref");
    const btn = h("button", { type: "button", class: "st-btn primary", id: "st-ref-build", onclick: () => renderRef(true) }, S.refBuilt ? tr("ref_reload") : tr("ref_load"));
    const frame = h("iframe", { class: "st-ref", title: tr("tab_ref"), id: "st-ref-frame", sandbox: SANDBOX, referrerpolicy: "no-referrer" });
    main.replaceChildren(h("div", { class: "st-row" }, h("p", { class: "lead" }, tr("ref_lead")), btn), frame);
    if (!S.refBuilt || force) {
      btn.disabled = true; btn.textContent = tr("building");
      const j = await api("preview", {});
      btn.disabled = false; btn.textContent = tr("ref_reload");
      if (!j.ok) { note("bad", tr("build_bad"), buildLines(j)); return; }
      S.refBuilt = true; S.ref = j.ref;
    }
    frame.src = pv((S.ref || "/_heron/theme/") + "?t=" + Date.now());
  }

  // --- запуск --------------------------------------------------------------------------
  // Язык интерфейса сменился (переключатель или настройки сайта прочитаны): подсказки темы -
  // на нём же, поэтому дерево и форма запрашиваются заново, правки остаются.
  let first = null;
  const ready = new Promise((resolve) => { first = resolve; setTimeout(resolve, 4000); });
  document.addEventListener("heron:lang", () => {
    first();
    tabs();
    if (S.tab === "pages" && S.tree) loadTree().then(() => S.target && choose(S.target, true));
    if (S.tab === "ref") renderRef();
  });
  document.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "s" && S.tab === "pages") { e.preventDefault(); save(); } });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
  async function start() {
    tabs();
    document.body.dataset.tab = "site";
    try {
      // С чего открыться - сразу, не дожидаясь настроек сайта: иначе 2-4 секунды видна
      // пустая вкладка «Сайт», а потом страница прыгает на «Страницы».
      const j = await api("start");
      if (!j.ok) return;
      S.preview = j.preview || null;
      const tab = j.tab || "site";
      if (tab !== "site") {
        setTab(tab);
        if (tab === "pages" && !S.tree) $("#tab-pages").replaceChildren(h("p", { class: "lead" }, tr("loading")));
      }
      await ready;
      if (j.target) {
        if (!S.tree) await loadTree();
        if (j.answers) { if (j.answers.key) S.key = j.answers.key; for (const [k, v] of Object.entries(j.answers)) if (k !== "key" && typeof v === "object") S.ans[k] = { ...v }; }
        await choose(j.target, true);
      }
    } catch (err) { /* без ключа страница конфигуратора сама объясняет, что делать */ }
  }
  window.HERON_STUDIO = S;
  window.HERON_PREVIEW_ORIGIN = pvOrigin;
  start();
})();
