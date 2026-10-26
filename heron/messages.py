"""Тексты командной строки на двух языках.

Язык сообщений — тот же, что язык пояснений в файлах сайта: флаг `--notes`,
затем `HERON_NOTES`, затем `build.notes` из `site.yaml`, затем английский.
Человек, который завёл сайт по-русски, и на экране читает по-русски.

Ключа нет в языке — берётся английский: сообщение на чужом языке лучше
падения на опечатке в словаре.
"""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        # --- находки init ---
        "found_site": "site.yaml: языки {languages}, тема {theme}",
        "found_content": "content/: {pages} страниц, языки: {langs}",
        "found_folder": "{folder}/ на месте",
        "none": "нет",
        "found": "нашёл",
        "created": "создал",
        "skipped": "оставил как есть: {count} файлов",
        "bad_notes": "язык пояснений {value!r}: есть ru и en",
        # --- сводка того, что разложено ---
        "plan_found": "В папке уже есть:",
        "plan_made": "Создано:",
        "plan_config": "конфиг: {files}",
        "plan_content": "контент {code}: {files}",
        "plan_home": "главная",
        "plan_404": "страница 404",
        "plan_theme": "тема: {count} файлов — theme.yaml, шаблоны, модули, стили",
        "plan_i18n": "строки интерфейса темы: {langs}",
        "plan_folders": "пустые папки: {folders}",
        "plan_notes": "записки heron-readme.md: {count} — что класть в каждую папку",
        "plan_other": "прочее: {files}",
        "plan_kept": "Не тронуто (уже было): {files}",
        "plan_kept_many": "Не тронуто (уже было): {count} файлов — список: --verbose",
        "plan_nothing": "Ничего создавать не понадобилось: всё уже на месте.",
        # --- new ---
        "new_title": "Новый сайт в папке {path}",
        "new_done": "Сайт создан: {path}",
        "init_done": "Папка {path} дополнена по site.yaml",
        "not_empty": (
            "Папка {path} не пуста, в ней есть: {files}\n"
            "  new создаёт сайт с нуля и чужие файлы не трогает. Служебные файлы git\n"
            "  ({service}) не мешают.\n"
            "  что сделать: если это уже папка сайта — `heron init {path}`, он дополнит\n"
            "  её недостающим и ничего не перезапишет. Иначе выберите пустую папку."
        ),
        "site_exists": (
            "В папке {path} уже есть сайт: site.yaml, языки {langs}.\n"
            "  new не нужен — он заводит сайт с нуля и готовую папку не трогает.\n"
            "  что сделать:\n"
            "    дополнить недостающим — `heron init {path}`\n"
            "    проверить и собрать — `heron check {path}`, `heron build {path}`\n"
            "    начать заново — уберите файлы сайта, оставив .git и .gitignore;\n"
            "    если они не закоммичены: `git clean -dn` покажет список, `git clean -d -f` удалит"
        ),
        "found_langs": "В content/ уже есть языки: {langs} — предложу их.",
        "no_questions": (
            "Вопросов не задаю: запуск без терминала. Значения — из флагов или по умолчанию.\n"
            "  Для опроса запустите в терминале; в докере — с ключом -it."
        ),
        # --- опрос ---
        "ask_intro": (
            "Несколько вопросов о сайте. Enter — принять значение в скобках.\n"
            "Всё это потом правится в site.yaml."
        ),
        "ask_name": "Название сайта",
        "ask_name_help": "как сайт называется для людей: в шапке, в <title>, в разметке",
        "ask_domain": "Домен",
        "ask_domain_help": (
            "без https:// и слешей, например example.com. Не знаете — Enter, останется заглушка"
        ),
        "ask_langs": "Языки сайта",
        "ask_langs_help": "коды через запятую: en или en, ru. Каждый язык — папка content/<код>/",
        "ask_default": "Основной язык",
        "ask_default_help": "отдаётся из корня (/about/), остальные — с префиксом (/ru/about/)",
        "ask_confirm": "Создать сайт?",
        "ask_summary": "Итого:",
        "ask_cancelled": "Отменено, ничего не создано.",
        "bad_domain": "домен пишется без схемы и пути: example.com",
        "bad_langs": "нужен хотя бы один код вида en, ru, en-gb; не подошло: {bad}",
        "bad_default": "основной язык должен быть в списке: {langs}",
        "placeholder": "заглушка — замените в site.yaml",
        # --- что дальше ---
        "next_title": "Что дальше:",
        "next_config": (
            "Настройте сайт анкетой: `heron setup {path}` — название, домен, кто вы, "
            "публикация. Или руками в {path}/site.yaml."
        ),
        "next_domain": (
            "Домен сейчас заглушка {domain} — впишите настоящий в анкете или в site.yaml."
        ),
        "next_home": "Главная — {files}: SEO-блок наверху (title, h1, description), ниже текст.",
        "next_page": "Новая страница: `heron page page about {path}`",
        "next_build": "Собрать: `heron build {path}` — результат в {path}/dist/",
        "next_check": "Проверить без сборки: `heron check {path}`",
        "next_langs": "Добавили язык в site.yaml — снова `heron init {path}`",
        "next_docker": (
            "В докере — те же команды после `docker run … ghcr.io/fmstm/heron:<тег>`;\n"
            "  путь к сайту — относительно текущей папки: `.`, если вы в ней."
        ),
        # --- page ---
        "page_done": "Создана страница: {path}",
        "page_next": "Заполните SEO-блок и секции, затем `heron build {root}`",
        # --- пути ---
        "no_path": "Папки {path} нет.",
        "no_site": (
            "В папке {path} нет site.yaml — это не папка сайта.\n"
            "  что сделать: создать сайт здесь — `heron new {path}`; дополнить\n"
            "  существующую папку — `heron init {path}`."
        ),
        "container_path": (
            "  почему: движок работает в контейнере и видит только папку,\n"
            "  смонтированную в /site, — это ваша текущая папка. Путь {path}\n"
            "  с вашего компьютера внутри контейнера не существует.\n"
            "  что сделать: передайте путь относительно текущей папки — `.`, если\n"
            "  вы в папке сайта, или имя вложенной папки."
        ),
        "path_hint": "  что сделать: проверьте путь; он считается от текущей папки.",
        # --- ошибки ---
        "error_head": "Ошибка {code}: {title}",
        "error_where": "  где: {where}",
        "error_what": "  подробно: {message}",
        "error_hint": "  что сделать: {hint}",
        "crash_head": "Движок споткнулся о непредвиденную ошибку: {kind}",
        "crash_text": "  {text}",
        "crash_hint": (
            "  что сделать: повторите с --debug, чтобы увидеть подробности, и пришлите\n"
            "  их разработчикам движка — это ошибка движка, а не вашего сайта."
        ),
        "denied": "Нет прав на запись: {path}",
        "denied_hint": (
            "  что сделать: в докере запускайте с --user $(id -u):$(id -g), иначе\n"
            "  файлы окажутся чужими; проверьте права на папку."
        ),
        # --- этапы сборки ---
        "step_config": "конфиг, тема и плагины",
        "step_content": "обход контента",
        "step_links": "связи, переводы и меню",
        "step_images": "картинки",
        "step_templates": "шаблоны",
        "step_generators": "карта сайта, robots и ленты",
        "step_slices": "нарезка картинок",
        "pool_fallback": (
            "пул процессов недоступен ({problem}): картинки режутся последовательно, "
            "результат тот же. Чтобы не видеть это, задайте --workers 1 или HERON_WORKERS=1"
        ),
        "step_write": "запись",
        "done": "готово",
        "done_config": "тема {theme}, языков {langs}",
        "done_pages": "страниц: {count}",
        "done_masters": "исходных картинок: {count}",
        "done_files": "файлов: {count}",
        # --- сборка и проверка ---
        "build_head": "HERON {version} · сборка {path} · окружение {env}",
        "check_head": "HERON {version} · проверка {path}",
        "build_failed": (
            "Сборка не выполнена: ошибок {count}. Папка сборки не тронута. "
            "Исправьте и соберите снова."
        ),
        "check_failed": "Проверка нашла ошибок: {count}. Сборка с ними не пройдёт.",
        "build_strict": (
            "Сборка остановлена: строгий режим (--strict или build.fail_on_warning), "
            "предупреждений {count}. Папка сборки не тронута — в ней прошлая удачная версия."
        ),
        "check_strict": (
            "Проверка: строгий режим (--strict или build.fail_on_warning), предупреждений {count}."
        ),
        "build_env": "окружение {env} · домен {domain} · {index} · {counters}",
        "finish_failed": (
            "Сайт записан и цел, но упало завершающее действие плагина "
            "(on_build_finished): {problem}"
        ),
        "index_closed": "индексация закрыта",
        "index_open": "ИНДЕКСАЦИЯ ОТКРЫТА",
        "counters_off": "счётчики выключены",
        "counters_on": "счётчики включены",
        "build_done": "Собрано файлов: {count} → {target}",
        "build_next": (
            "Посмотреть: `heron serve {path}` · боевая сборка: "
            "`heron build {path} --env prod --strict`"
        ),
        "check_done": "Ошибок нет. Собрать: `heron build {path}`",
    },
    "en": {
        "found_site": "site.yaml: languages {languages}, theme {theme}",
        "found_content": "content/: {pages} pages, languages: {langs}",
        "found_folder": "{folder}/ is in place",
        "none": "none",
        "found": "found",
        "created": "created",
        "skipped": "left as is: {count} files",
        "bad_notes": "notes language {value!r}: ru and en are available",
        "plan_found": "Already in the folder:",
        "plan_made": "Created:",
        "plan_config": "config: {files}",
        "plan_content": "content {code}: {files}",
        "plan_home": "home page",
        "plan_404": "404 page",
        "plan_theme": "theme: {count} files — theme.yaml, templates, modules, styles",
        "plan_i18n": "theme interface strings: {langs}",
        "plan_folders": "empty folders: {folders}",
        "plan_notes": "heron-readme.md notes: {count} — what goes into each folder",
        "plan_other": "other: {files}",
        "plan_kept": "Left untouched (already there): {files}",
        "plan_kept_many": "Left untouched (already there): {count} files — list: --verbose",
        "plan_nothing": "Nothing to create: everything is already in place.",
        "new_title": "New site in {path}",
        "new_done": "Site created: {path}",
        "init_done": "Folder {path} completed from site.yaml",
        "not_empty": (
            "Folder {path} is not empty, it contains: {files}\n"
            "  new builds a site from scratch and never touches other files. Git service\n"
            "  files ({service}) are fine.\n"
            "  what to do: if this is already a site folder, run `heron init {path}` —\n"
            "  it adds what is missing and overwrites nothing. Otherwise pick an empty folder."
        ),
        "site_exists": (
            "Folder {path} already has a site: site.yaml, languages {langs}.\n"
            "  new is not needed — it starts a site from scratch and leaves a ready folder alone.\n"
            "  what to do:\n"
            "    add what is missing — `heron init {path}`\n"
            "    check and build — `heron check {path}`, `heron build {path}`\n"
            "    start over — remove the site files, keeping .git and .gitignore;\n"
            "    if they are not committed: `git clean -dn` lists them, `git clean -d -f` removes"
        ),
        "found_langs": "content/ already has languages: {langs} — I will suggest them.",
        "no_questions": (
            "No questions asked: not running in a terminal. Values come from flags or defaults.\n"
            "  For the questionnaire run it in a terminal; with docker, add -it."
        ),
        "ask_intro": (
            "A few questions about the site. Enter accepts the value in brackets.\n"
            "Everything can be changed later in site.yaml."
        ),
        "ask_name": "Site name",
        "ask_name_help": "what people call the site: header, <title>, structured data",
        "ask_domain": "Domain",
        "ask_domain_help": (
            "no https:// and no slashes, e.g. example.com. Not sure — Enter keeps a placeholder"
        ),
        "ask_langs": "Site languages",
        "ask_langs_help": (
            "comma-separated codes: en or en, ru. Each language is a content/<code>/ folder"
        ),
        "ask_default": "Main language",
        "ask_default_help": "served from the root (/about/), the others with a prefix (/ru/about/)",
        "ask_confirm": "Create the site?",
        "ask_summary": "Summary:",
        "ask_cancelled": "Cancelled, nothing created.",
        "bad_domain": "a domain has no scheme and no path: example.com",
        "bad_langs": "need at least one code like en, ru, en-gb; not valid: {bad}",
        "bad_default": "the main language must be one of: {langs}",
        "placeholder": "placeholder — replace it in site.yaml",
        "next_title": "What next:",
        "next_config": (
            "Set the site up with the questionnaire: `heron setup {path}` — name, domain, "
            "who you are, publishing. Or by hand in {path}/site.yaml."
        ),
        "next_domain": (
            "The domain is a placeholder {domain} — put the real one in the questionnaire "
            "or in site.yaml."
        ),
        "next_home": "Home page — {files}: SEO block on top (title, h1, description), text below.",
        "next_page": "New page: `heron page page about {path}`",
        "next_build": "Build: `heron build {path}` — output in {path}/dist/",
        "next_check": "Check without building: `heron check {path}`",
        "next_langs": "Added a language to site.yaml — run `heron init {path}` again",
        "next_docker": (
            "With docker — the same commands after `docker run … ghcr.io/fmstm/heron:<tag>`;\n"
            "  the site path is relative to the current folder: `.` if you are in it."
        ),
        "page_done": "Page created: {path}",
        "page_next": "Fill in the SEO block and the sections, then `heron build {root}`",
        "no_path": "There is no folder {path}.",
        "no_site": (
            "Folder {path} has no site.yaml — it is not a site folder.\n"
            "  what to do: create a site here — `heron new {path}`; complete an\n"
            "  existing folder — `heron init {path}`."
        ),
        "container_path": (
            "  why: the engine runs in a container and sees only the folder mounted\n"
            "  at /site — your current folder. The path {path} from your computer\n"
            "  does not exist inside the container.\n"
            "  what to do: pass the path relative to the current folder — `.` if you\n"
            "  are in the site folder, or the name of a subfolder."
        ),
        "path_hint": "  what to do: check the path; it is relative to the current folder.",
        "error_head": "Error {code}: {title}",
        "error_where": "  where: {where}",
        "error_what": "  details: {message}",
        "error_hint": "  what to do: {hint}",
        "crash_head": "The engine hit an unexpected error: {kind}",
        "crash_text": "  {text}",
        "crash_hint": (
            "  what to do: run again with --debug to see the details and send them to\n"
            "  the engine developers — this is an engine bug, not a problem with your site."
        ),
        "denied": "No permission to write: {path}",
        "denied_hint": (
            "  what to do: with docker run with --user $(id -u):$(id -g), otherwise the\n"
            "  files end up owned by someone else; check the folder permissions."
        ),
        "step_config": "config, theme and plugins",
        "step_content": "reading content",
        "step_links": "links, translations and menus",
        "step_images": "images",
        "step_templates": "templates",
        "step_generators": "sitemap, robots and feeds",
        "step_slices": "image renditions",
        "pool_fallback": (
            "the process pool is unavailable ({problem}): images are cut one by one, "
            "the result is the same. To skip this, pass --workers 1 or set HERON_WORKERS=1"
        ),
        "step_write": "writing",
        "done": "done",
        "done_config": "theme {theme}, languages: {langs}",
        "done_pages": "{count} pages",
        "done_masters": "{count} source images",
        "done_files": "{count} files",
        "build_head": "HERON {version} · building {path} · environment {env}",
        "check_head": "HERON {version} · checking {path}",
        "build_failed": (
            "Build failed: {count} errors. The output folder is untouched. "
            "Fix them and build again."
        ),
        "check_failed": "Check found {count} errors. A build would fail on them.",
        "build_strict": (
            "Build stopped: strict mode (--strict or build.fail_on_warning), {count} warnings. "
            "The output folder is untouched — it still holds the last good build."
        ),
        "check_strict": "Check: strict mode (--strict or build.fail_on_warning), {count} warnings.",
        "build_env": "environment {env} · domain {domain} · {index} · {counters}",
        "finish_failed": (
            "The site is written and intact, but a plugin finishing step "
            "(on_build_finished) failed: {problem}"
        ),
        "index_closed": "indexing closed",
        "index_open": "INDEXING OPEN",
        "counters_off": "counters off",
        "counters_on": "counters on",
        "build_done": "Files written: {count} → {target}",
        "build_next": (
            "Preview: `heron serve {path}` · production build: "
            "`heron build {path} --env prod --strict`"
        ),
        "check_done": "No errors. Build: `heron build {path}`",
    },
}

# Названия ошибок для заголовка сообщения. Подробность — в самой ошибке.
TITLES: dict[str, dict[str, str]] = {
    "en": {
        "E001": "broken YAML in the front matter",
        "E002": "no title, h1 or description, or a front matter field of the wrong type",
        "E003": "duplicate section id in a file",
        "E004": "two files produce the same URL",
        "E005": "invalid slug",
        "E006": "a link field points to a page that does not exist",
        "E007": "the image is not on disk",
        "E008": "the theme has no template for this page type",
        "E009": "redirect_from matches an existing URL",
        "E010": "the template uses a variable that does not exist",
        "E011": "site.yaml is not valid",
        "E012": "the engine version does not match heron: in site.yaml",
        "E013": "the theme is found neither locally nor among installed packages",
        "E014": "a plugin is not installed or failed to load",
        "E015": "raw HTML in markdown with build.allow_raw_html: false",
        "E016": "invalid section id",
        "E017": "production build without a single page",
        "E018": "the site resource folder is duplicated",
        "E019": "a local video has no poster",
        "E020": "schema.org markup cannot be built",
        "E021": "the default language is empty in production",
        "E022": "gone overlaps a page address or redirect_from",
        "E023": "the theme lists fields the engine does not know",
        "E024": "a path leaves the allowed folders",
        "E025": "a heading attribute is not allowed",
        "E026": "two sources produce the same output file",
        "E027": "two masters produce the same rendition names",
        "E028": "a language has no home page",
        "E029": "two files produce the same page key",
        "E030": "a source folder or file cannot be read",
        "E031": "the preview cannot take the address and port",
        "E032": "the theme cannot be installed: archive, catalog or check",
        "E035": "the cache or lock file cannot be created next to the build folder",
    },
}


def say(lang: str, key: str, **fields: object) -> str:
    table = TEXT.get(lang, TEXT["en"])
    template = table.get(key) or TEXT["en"][key]
    return template.format(**fields)


def title(lang: str, code: str) -> str:
    """Название ошибки по коду на языке сообщений."""
    from heron.core.errors import ERRORS

    if lang == "ru":
        return ERRORS.get(code, code)
    return TITLES["en"].get(code) or ERRORS.get(code, code)


# --- serve ---------------------------------------------------------------------
TEXT["ru"].update(
    {
        "serve_built": "собрано: {count} файлов",
        "serve_warnings": "предупреждений: {count}",
        "serve_dist": "собрано в {dist}",
        "serve_open": "открыто: {url}  (Ctrl+C — выход)",
        "serve_container": (
            "HERON работает в контейнере: откройте адрес на своём компьютере. "
            "Порт {port} должен быть проброшен в docker run только на эту машину: "
            "-p 127.0.0.1:{port}:{port}"
        ),
        "serve_lan": (
            "просмотр открыт для всей сети: любой в ней увидит черновики "
            "по адресу этого компьютера и порту {port}"
        ),
        "serve_changed": "изменения ({files}) — пересобираю",
        "serve_more": " и ещё {count}",
        "serve_stopped": "остановлено",
        "serve_busy": "не удалось открыть просмотр на {host}:{port}: {problem}",
        "serve_busy_hint": (
            "порт занят другой программой или адрес не принадлежит машине: "
            "возьмите другой порт, например --port {next}, и в docker run -p {next}:{next}"
        ),
    }
)
TEXT["en"].update(
    {
        "serve_built": "built: {count} files",
        "serve_warnings": "warnings: {count}",
        "serve_dist": "built into {dist}",
        "serve_open": "open: {url}  (Ctrl+C to stop)",
        "serve_container": (
            "HERON runs in a container: open the address on your computer. "
            "Port {port} must be published in docker run to this machine only: "
            "-p 127.0.0.1:{port}:{port}"
        ),
        "serve_lan": (
            "the preview is open to the whole network: anyone on it sees the drafts "
            "at this computer's address and port {port}"
        ),
        "serve_changed": "changes ({files}) — rebuilding",
        "serve_more": " and {count} more",
        "serve_stopped": "stopped",
        "serve_busy": "cannot open the preview on {host}:{port}: {problem}",
        "serve_busy_hint": (
            "the port is used by another program or the address is not this machine's: "
            "take another port, for example --port {next}, and -p {next}:{next} in docker run"
        ),
    }
)


# --- setup и темы ----------------------------------------------------------------
TEXT["ru"].update(
    {
        "setup_open": (
            "Анкета открыта: {url}  — откройте адрес целиком, с ключом после «#». Ctrl+C — выход."
        ),
        "setup_done": "Настройки записаны.",
        "setup_written": "записано: {files}",
        "setup_created": "создано: {files}",
        "setup_removed": "убрано (способ публикации сменился): {files}",
        "setup_kept": "не тронуто, файл не от конфигуратора: {files}",
        "setup_backup": "прежняя версия: {file}",
        "setup_next": "Дальше: `heron serve {path}` — посмотреть сайт.",
        "setup_bad": "ответы не прошли проверку: {problem}",
        "setup_no_site": "В папке {path} нет site.yaml — здесь нет сайта, настраивать нечего.",
        "setup_no_site_hint": (
            "Перейдите в папку сайта (cd имя-сайта) и запустите setup там, "
            "или создайте сайт: heron new имя-сайта"
        ),
        "theme_done": "Тема {name} поставлена.",
        "theme_demo": "страниц-примеров темы добавлено: {count} (ваши страницы не тронуты)",
        "theme_https": "тему по ссылке берём только по https",
    }
)
TEXT["en"].update(
    {
        "setup_open": (
            "The questionnaire is open: {url}  — open the whole address, "
            "with the key after “#”. Ctrl+C to stop."
        ),
        "setup_done": "Settings written.",
        "setup_written": "written: {files}",
        "setup_created": "created: {files}",
        "setup_removed": "removed (the publishing way changed): {files}",
        "setup_kept": "left alone, not written by the configurator: {files}",
        "setup_backup": "previous version: {file}",
        "setup_next": "Next: `heron serve {path}` — look at the site.",
        "setup_bad": "the answers did not pass the check: {problem}",
        "setup_no_site": "There is no site.yaml in {path} — no site here, nothing to set up.",
        "setup_no_site_hint": (
            "Go to the site folder (cd site-name) and run setup there, "
            "or create a site: heron new site-name"
        ),
        "theme_done": "Theme {name} is in place.",
        "theme_demo": "theme example pages added: {count} (your pages untouched)",
        "theme_https": "a theme by link is taken over https only",
    }
)


# --- комплект для агентов, docs, schema (20 §1, 21 §10, §12) -----------------------
TEXT["ru"].update(
    {
        # сводка new/init
        "kit_created": "инструкции для агентов: agents/, AGENTS.md — {code}, файлов {n}",
        "kit_updated": (
            "инструкции для агентов обновлены ({code}): заменено {updated}, добавлено {created}"
        ),
        "kit_in_place": "инструкции для агентов уже на месте — обновить: heron init --agents",
        "kit_off": (
            "инструкции для агентов не положены (build.agents: false) — "
            "включить: heron init --agents"
        ),
        "kit_skipped_edited": "правлен вами, не тронут: {files}",
        "kit_forced": "правлен вами — перезаписан (--force): {files}",
        "kit_current": "инструкции для агентов уже актуальны ({code})",
        "kit_bad_value": "build.agents: {value} — не понято, комплект не тронут",
        "kit_bad_value_hint": "допустимо true, kit или false; heron check покажет ту же ошибку",
        "kit_orphan": "нет в новом комплекте, оставлен: {files}",
        "kit_fallback": "без перевода на {want}, положены на {have}: файлов {n}",
        "kit_about_placeholder": "<о проекте: заполняет архитектор>",
        "kit_manifest_head": "# Манифест комплекта для агентов. Пишет движок, руками не правят.",
        "kit_manifest_damaged": "манифест agents/heron-kit.yaml не прочитан — переписан заново",
        # сведение check (21 §12)
        "kit_found": (
            "`agents/`: инструкции для агентов, движок {engine}, {code}; в сборку не входит"
        ),
        "kit_unreadable": (
            "`agents/`: инструкции для агентов, манифест не прочитан; в сборку не входит"
        ),
        "kit_outdated": "комплект от {kit}, движок {engine} — обновить: `heron init --agents`",
        "kit_disabled": "комплект отключён",
        "kit_missing": "комплекта нет — `heron init`",
        "agents_conflict": "--agents и --no-agents вместе не задаются: выберите одно",
        # heron docs
        "docs_start_with": "Начать с {path}",
        "docs_group_start": "Начало",
        "docs_group_roles": "Роли агентов",
        "docs_group_guide": "Гайды по порядку",
        "docs_group_spec": "Справочник",
        "docs_group_machine": "Для машин",
        "docs_exported": "Документация выложена в {target}: файлов {n}",
        "docs_not_found": "«{query}» в документации не нашлось.",
        "docs_no_template": "Образца {file!r} нет. Есть: {names}",
        "docs_no_topic": "Темы {name!r} нет. Оглавление: heron docs",
        "docs_all_langs": "--all-langs работает только вместе с --export <папка>",
        # heron schema
        "schema_exported": "Схемы записаны в {target}: {files}",
        "schema_one_kind": "Схема одна за раз: выберите один из флагов {flags}",
    }
)
TEXT["en"].update(
    {
        "kit_created": "agent instructions: agents/, AGENTS.md — {code}, {n} files",
        "kit_updated": "agent instructions updated ({code}): {updated} replaced, {created} added",
        "kit_in_place": "agent instructions already in place — update: heron init --agents",
        "kit_off": (
            "agent instructions not placed (build.agents: false) — enable: heron init --agents"
        ),
        "kit_skipped_edited": "edited by you, left as is: {files}",
        "kit_forced": "edited by you — overwritten (--force): {files}",
        "kit_current": "agent instructions already up to date ({code})",
        "kit_bad_value": "build.agents: {value} — not understood, the kit is left alone",
        "kit_bad_value_hint": "allowed: true, kit or false; heron check shows the same error",
        "kit_orphan": "not in the new kit, left in place: {files}",
        "kit_fallback": "no {want} translation yet, placed in {have}: {n} files",
        "kit_about_placeholder": "<about the project: the architect fills this in>",
        "kit_manifest_head": "# Agent kit manifest. Written by the engine, not edited by hand.",
        "kit_manifest_damaged": "agents/heron-kit.yaml could not be read — written anew",
        "kit_found": (
            "`agents/`: agent instructions, engine {engine}, {code}; not part of the build"
        ),
        "kit_unreadable": (
            "`agents/`: agent instructions, manifest unreadable; not part of the build"
        ),
        "kit_outdated": "kit from {kit}, engine {engine} — update: `heron init --agents`",
        "kit_disabled": "agent kit disabled",
        "kit_missing": "no agent kit — `heron init`",
        "agents_conflict": "--agents and --no-agents cannot be used together: pick one",
        # Пометка фолбэка — буквально как в 21 §10 на обоих языках: её ищут агенты и тесты.
        "docs_start_with": "Start with {path}",
        "docs_group_start": "Start",
        "docs_group_roles": "Agent roles",
        "docs_group_guide": "Guides in order",
        "docs_group_spec": "Reference",
        "docs_group_machine": "For machines",
        "docs_exported": "Documentation written to {target}: {n} files",
        "docs_not_found": "“{query}” is not in the documentation.",
        "docs_no_template": "There is no sample {file!r}. Available: {names}",
        "docs_no_topic": "There is no topic {name!r}. Contents: heron docs",
        "docs_all_langs": "--all-langs works only together with --export <folder>",
        "schema_exported": "Schemas written to {target}: {files}",
        "schema_one_kind": "One schema at a time: pick one of {flags}",
    }
)

# --- check: изменение данных в шаблонах темы (E033, 21 §7) ------------------------
# В подсказках двойные скобки: `say` подставляет поля через str.format.
TEXT["ru"].update(
    {
        "sandbox_mutation": (
            "{call} меняет данные на месте: шаблоны темы рендерятся в неизменяемой "
            "песочнице, и сборка на этом месте упадёт с E033"
        ),
        "sandbox_hint_add": (
            "стройте новый список вместо изменения: `{{% set xs = xs + [item] %}}`; "
            "накопление в цикле — через namespace: `{{% set acc = namespace(xs=[]) %}}` … "
            "`{{% set acc.xs = acc.xs + [item] %}}`; отбор — фильтры selectattr/rejectattr, "
            "без повторов — `unique(case_sensitive=True, attribute='url')`; "
            "рецепты: heron docs theme"
        ),
        "sandbox_hint_keys": (
            "стройте новый словарь вместо изменения: `{{% set d = dict(d, key=value) %}}`; "
            "в цикле — через namespace: `{{% set acc = namespace(d={{}}) %}}` … "
            "`{{% set acc.d = dict(acc.d, key=value) %}}`; рецепты: heron docs theme"
        ),
        "sandbox_hint_remove": (
            "уберите лишнее фильтром, а не из самого списка: `xs|reject('equalto', x)|list`, "
            "`xs|rejectattr('id', 'in', ['a', 'b'])|list`, срез `xs[1:]`; "
            "рецепты: heron docs theme"
        ),
        "sandbox_hint_order": (
            "порядок задают фильтры, а не сам список: `xs|sort(attribute='title')|list`, "
            "`xs|reverse|list`; рецепты: heron docs theme"
        ),
    }
)
TEXT["en"].update(
    {
        "sandbox_mutation": (
            "{call} changes data in place: theme templates render in an immutable "
            "sandbox, and the build fails here with E033"
        ),
        "sandbox_hint_add": (
            "build a new list instead of changing one: `{{% set xs = xs + [item] %}}`; "
            "to collect in a loop use a namespace: `{{% set acc = namespace(xs=[]) %}}` … "
            "`{{% set acc.xs = acc.xs + [item] %}}`; to pick items use selectattr/rejectattr, "
            "to drop repeats `unique(case_sensitive=True, attribute='url')`; "
            "recipes: heron docs theme"
        ),
        "sandbox_hint_keys": (
            "build a new dict instead of changing one: `{{% set d = dict(d, key=value) %}}`; "
            "in a loop use a namespace: `{{% set acc = namespace(d={{}}) %}}` … "
            "`{{% set acc.d = dict(acc.d, key=value) %}}`; recipes: heron docs theme"
        ),
        "sandbox_hint_remove": (
            "drop items with a filter, not from the list itself: "
            "`xs|reject('equalto', x)|list`, `xs|rejectattr('id', 'in', ['a', 'b'])|list`, "
            "a slice `xs[1:]`; recipes: heron docs theme"
        ),
        "sandbox_hint_order": (
            "set the order with filters, not on the list itself: "
            "`xs|sort(attribute='title')|list`, `xs|reverse|list`; recipes: heron docs theme"
        ),
    }
)
TITLES["en"].update(
    {
        "E033": "a theme template reaches what the sandbox closes",
        "E034": "a build file to check is empty, unreadable or not UTF-8",
    }
)

# --- отчёт check и build, сводка ошибок и предупреждений (heron/core/report.py) ----
TEXT["ru"].update(
    {
        "report_pages": "Страниц — {count} ({by_lang})",
        "report_types": "Типы — {by_type}",
        "report_untranslated": "Не переведено:",
        "report_missing": "Тема ждёт секцию, а в файле её нет:",
        "report_missing_line": "  {section:12} — {count} страниц: {shown}",
        "report_format": "Формат секции не тот, которого ждёт тема (это не ошибка):",
        "report_format_line": "  {source}: {section} — ждали {want}, пришло {got}",
        "report_format_fix": (
            "  как исправить: если по смыслу это форма из «ждали» — задайте её "
            "классом в якоре секции: `## Заголовок {{#якорь .checklist}}`; если права "
            "разметка — поменяйте форму в `uses` типа в theme.yaml: `якорь:форма`"
        ),
        "report_nameless": "В меню, но без короткого имени — покажется имя файла:",
        "report_unused_sections": "Секции, которых тема не использует (опечатка в якоре?):",
        "report_unused_modules": "Модули темы, которые не зовёт ни один шаблон: {names}",
        "report_broken": "Ссылки в никуда:",
        "report_orphans": "На эти страницы никто не ссылается: {urls}",
        "report_schema": "Разметка schema.org — {by_kind}",
        "report_unused_media": "Файлы в media, которых никто не ждёт — {count}:",
        "report_static_media": "В static лежит контент — его место в media:",
        "report_uneven": "Поле есть не у всех элементов списка (шаблон обязан это учесть):",
        "report_uneven_line": "  {owner}: {where} — {field} у {have} из {total}",
        "report_list": "список",
        "report_nginx_ok": "nginx -t на собранном конфиге: прошёл",
        "report_manual_dates": (
            "Ручная дата updated у {manual} из {total} страниц перекрывает "
            "updated_from: {mode} — у этих страниц дата из {mode} не берётся. "
            "Где дата должна обновляться сама, уберите updated из фронтматтера."
        ),
        "report_notes_missing": "Без пояснительной записки (это не ошибка): {folders}",
        "report_root": "корень",
        "summary_warnings": "Предупреждений — {count}:",
        "summary_more": "    … и ещё {count}",
        "summary_full": "  полный список: {path}",
        "summary_unknown_file": "<неизвестный файл>",
    }
)
TEXT["en"].update(
    {
        "report_pages": "Pages — {count} ({by_lang})",
        "report_types": "Types — {by_type}",
        "report_untranslated": "Not translated:",
        "report_missing": "The theme expects a section the file does not have:",
        "report_missing_line": "  {section:12} — {count} pages: {shown}",
        "report_format": "A section is not in the form the theme expects (not an error):",
        "report_format_line": "  {source}: {section} — expected {want}, got {got}",
        "report_format_fix": (
            "  how to fix: if by meaning it is the expected form, set it with a class "
            "in the section anchor: `## Heading {{#anchor .checklist}}`; if the markup is "
            "right, change the form in the type's `uses` in theme.yaml: `anchor:form`"
        ),
        "report_nameless": "In the menu without a short name — the file name will show:",
        "report_unused_sections": "Sections the theme does not use (a typo in the anchor?):",
        "report_unused_modules": "Theme modules no template calls: {names}",
        "report_broken": "Links to nowhere:",
        "report_orphans": "No page links to these: {urls}",
        "report_schema": "schema.org markup — {by_kind}",
        "report_unused_media": "Files in media nothing expects — {count}:",
        "report_static_media": "Content sits in static — it belongs in media:",
        "report_uneven": "A field only some list items have (the template must allow for it):",
        "report_uneven_line": "  {owner}: {where} — {field} in {have} of {total}",
        "report_list": "list",
        "report_nginx_ok": "nginx -t on the built config: passed",
        "report_manual_dates": (
            "A manual updated date on {manual} of {total} pages overrides "
            "updated_from: {mode} — these pages do not take the date from {mode}. "
            "Where the date should update by itself, remove updated from the front matter."
        ),
        "report_notes_missing": "No explanatory note (not an error): {folders}",
        "report_root": "root",
        "summary_warnings": "Warnings — {count}:",
        "summary_more": "    … and {count} more",
        "summary_full": "  full list: {path}",
        "summary_unknown_file": "<unknown file>",
    }
)

# Язык комплекта для агентов в сводке init (20 §1, 21 §10).
TEXT["ru"].update(
    {
        "kit_lang_changed": "язык комплекта сменился: {old} → {new} (build.notes)",
        "kit_lang_kept": (
            "комплект оставлен на {kit}, build.notes — {notes}: "
            "сменить язык комплекта — heron init --agents"
        ),
    }
)
TEXT["en"].update(
    {
        "kit_lang_changed": "kit language changed: {old} → {new} (build.notes)",
        "kit_lang_kept": (
            "the kit stays in {kit}, build.notes is {notes}: "
            "to switch the kit language — heron init --agents"
        ),
    }
)

# E024 общего писателя (write_files): на месте папки не папка. Писатель не знает
# языка вызывающего, поэтому печатает оба текста подряд (E13.S1.T17).
TEXT["ru"].update(
    {
        "write_dangling": (
            "на месте папки символическая ссылка, которая никуда не ведёт — записать в неё нельзя"
        ),
        "write_not_folder": "на месте папки файл или ссылка не на папку — записать в неё нельзя",
        "write_folder_hint": "уберите ссылку или файл либо назовите другую папку",
    }
)
TEXT["en"].update(
    {
        "write_dangling": (
            "a symbolic link that leads nowhere stands where a folder should be — "
            "nothing can be written into it"
        ),
        "write_not_folder": (
            "a file or a link to something other than a folder stands where a folder "
            "should be — nothing can be written into it"
        ),
        "write_folder_hint": "remove the link or the file, or name another folder",
    }
)

# Виды предупреждений (Warning_.kind) — ключи группировки, по-русски в коде;
# на экран они идут на языке сообщений. Нет вида в таблице — как есть.
KINDS: dict[str, dict[str, str]] = {
    "en": {
        "картинки": "images",
        "связи": "relations",
        "ссылки": "links",
        "меню": "menu",
        "переводы": "translations",
        "языки": "languages",
        "прочее": "other",
        "нет перевода": "not translated",
        "даты": "dates",
        "контент": "content",
    },
}


def kind(lang: str, name: str) -> str:
    """Вид предупреждения на языке сообщений."""
    return KINDS.get(lang, {}).get(name, name)


# --- справка команд: --help на языке пояснений (E15.S1.T3, 21 §10) ----------------
# Ключи help_* читает heron/cli.py при показе справки: язык выбирается до разбора
# аргументов (--notes, затем HERON_NOTES, затем build.notes из ./site.yaml, иначе en).
# help_mv_* — подписи значений в строке использования (ПУТЬ / PATH). Фигурных скобок
# в этих текстах нет: say() пропускает их через str.format.
TEXT["ru"].update(
    {
        "help_main": (
            "HERON — файловый движок сайтов.\n\n"
            "Язык справки и сообщений: --notes ru|en, иначе HERON_NOTES, иначе "
            "build.notes из site.yaml текущей папки, иначе en."
        ),
        "help_new": (
            "Создать сайт с нуля: в новой папке или в текущей (`.`).\n\n"
            "В терминале задаёт вопросы: язык пояснений, название, домен, языки "
            "сайта, основной язык. Без терминала (агент, CI, docker без -it) не "
            "спрашивает: значения из флагов или по умолчанию.\n\n"
            "Папка может быть под git: .git, .gitignore, README и прочее служебное "
            "не мешают. Кладёт и инструкции для агентов на языке пояснений: agents/ "
            "и корневые указатели на них (сборка их не видит); --no-agents — без них."
        ),
        "help_init": (
            "Дополнить папку недостающим по тому, что написано в site.yaml.\n\n"
            "Ничего не перезаписывает без --force. Нет site.yaml — значит, сайт "
            "только заводится: в терминале те же вопросы, что у `new`, языки по "
            "умолчанию — папки, которые уже лежат в content/. Язык пояснений: "
            "--notes, иначе HERON_NOTES, иначе build.notes из site.yaml, иначе en.\n\n"
            "Инструкции для агентов (agents/, AGENTS.md): без флагов — только "
            "недостающие файлы, если build.agents не `false`; --agents — обновление "
            "по манифесту; --no-agents — не класть и записать `build.agents: false` "
            "(21 §10)."
        ),
        "help_check": "Проверить контент и конфиг, ничего не собирая.",
        "help_build": "Собрать сайт в dist/ или в указанную папку.",
        "help_serve": "Локальный просмотр с пересборкой при изменениях.",
        "help_setup": (
            "Конфигуратор: анкета, которая пишет site.yaml, сценарий для CI и скрипты.\n\n"
            "Без флагов открывает анкету в браузере (адрес — на экране). С --answers "
            "применяет ответы из файла — те же поля и та же проверка."
        ),
        "help_schema": (
            "JSON Schema контрактов этой версии: для редактора, агента и CI (21 §10).\n\n"
            "\b\n"
            "heron schema                  site.yaml\n"
            "heron schema --frontmatter    фронтматтер страницы\n"
            "heron schema --errors         реестр кодов ошибок\n"
            "heron schema --export папка   все пять файлов"
        ),
        "help_recipe": (
            "Рецепт образа nginx для собранного сайта (Dockerfile) этой версии HERON; "
            "комментарии в нём — на языке пояснений.\n\n"
            "`heron recipe > /tmp/Dockerfile && docker build -f /tmp/Dockerfile dist` "
            "— образ сайта без клона HERON и без Dockerfile в папке сайта."
        ),
        "help_theme": (
            "Темы: поставить по имени, ссылке или архиву, показать каталог, упаковать свою."
        ),
        "help_theme_get": (
            "Поставить тему: starter, имя из каталога, https-ссылка или файл архива.\n\n"
            "Прежняя тема уезжает в .heron-cache/setup/. Демонстрационные страницы "
            "темы ложатся только туда, где страницы нет: страницы сайта не "
            "перезаписываются."
        ),
        "help_theme_list": "Каталог тем HERON.",
        "help_theme_pack": (
            "Упаковать тему сайта вместе с его контентом — демо-страницами для heron theme get."
        ),
        "help_page": "Заготовка страницы со всеми секциями своего типа.",
        "help_docs": (
            "Документация этой версии движка: оглавление, тема, поиск, выгрузка (21 §10).\n\n"
            "Нет файла на нужном языке — печатается файл другого языка с пометкой "
            "первой строкой.\n\n"
            "\b\n"
            "heron docs                        оглавление\n"
            "heron docs kit                    с чего начинать агенту\n"
            "heron docs template page.md       образец файла\n"
            "heron docs --search E023          поиск по всей документации\n"
            "heron docs --export .heron-docs   папкой, со ссылками между файлами\n"
            "heron docs --lang en engine       тема на английском"
        ),
        # параметры
        "help_opt_help": "Показать эту справку и выйти.",
        "help_opt_version": "Показать версию и выйти.",
        "help_opt_debug": "Показать трейсбек непредвиденной ошибки. То же — HERON_DEBUG=1.",
        "help_opt_notes": (
            "Язык комментариев в файлах сайта, справки и сообщений на экране: ru или en. "
            "Иначе HERON_NOTES, иначе build.notes из site.yaml, иначе en."
        ),
        "help_opt_verbose": "Перечислить каждый созданный файл.",
        "help_opt_name": "Название сайта.",
        "help_opt_domain": "Домен без схемы: example.com.",
        "help_opt_langs": "Языки через запятую, первый — основной: en или en,ru.",
        "help_opt_yes": "Не задавать вопросов: флаги и значения по умолчанию.",
        "help_opt_no_agents": (
            "Не класть инструкции для агентов (agents/, AGENTS.md) и запомнить это: "
            "`build.agents: false`."
        ),
        "help_opt_force": "Перезаписывать существующие файлы.",
        "help_opt_agents": (
            "Только инструкции для агентов: обновить по манифесту agents/heron-kit.yaml — "
            "нетронутые заменить, правленые оставить и назвать (--force — заменить и их)."
        ),
        "help_opt_strict": "Считать предупреждения ошибками.",
        "help_opt_drafts": "Включить страницы с `published: false`.",
        "help_opt_json": "Ошибки и предупреждения в JSON — для агента и CI.",
        "help_opt_out": "Куда собирать.",
        "help_opt_env": (
            "Окружение сборки: `prod` открывает индексацию и счётчики, всё прочее — нет."
        ),
        "help_opt_workers": (
            "Процессов на нарезку; 0 — по ядрам, 1 — без пула. "
            "Сильнее HERON_WORKERS и build.workers."
        ),
        "help_opt_port": "Порт.",
        "help_opt_host": (
            "Где слушать. По умолчанию 127.0.0.1, а в образе HERON — 0.0.0.0, "
            "чтобы проброшенный порт открывался снаружи контейнера."
        ),
        "help_opt_serve_drafts": "Показывать черновики (`published: false`); по умолчанию да.",
        "help_opt_answers": (
            "Ответы анкеты из YAML или JSON без браузера (агент, CI). «-» — из stdin."
        ),
        "help_opt_dump": "Напечатать записанные ответы в YAML и выйти.",
        "help_opt_setup_host": "Где слушать: как у heron serve.",
        "help_opt_schema_site": "site.yaml (по умолчанию).",
        "help_opt_schema_theme": "theme.yaml.",
        "help_opt_schema_frontmatter": "Фронтматтер страницы.",
        "help_opt_schema_setup": "Ответы анкеты heron setup.",
        "help_opt_schema_errors": "Реестр кодов ошибок.",
        "help_opt_schema_export": "Записать все пять файлов в папку.",
        "help_opt_pack_out": "Файл архива; по умолчанию dist/theme.tar.gz.",
        "help_opt_page_lang": "Язык страницы. По умолчанию основной язык сайта.",
        "help_opt_folder": "Папка внутри языкового дерева.",
        "help_opt_docs_lang": (
            "Язык документации. Иначе --notes, HERON_NOTES, build.notes из site.yaml "
            "текущей папки, иначе en."
        ),
        "help_opt_search": "Найти в документации.",
        "help_opt_docs_export": (
            "Выложить документацию в папку — то же, что сайт получает в agents/."
        ),
        "help_opt_all_langs": "С --export: оба языка, папки ru/ и en/ (для сайта движка).",
        # подписи значений
        "help_mv_options": "[ПАРАМЕТРЫ]",
        "help_mv_command": "КОМАНДА [АРГУМЕНТЫ]...",
        "help_mv_path": "ПУТЬ",
        "help_mv_codes": "КОДЫ",
        "help_mv_code": "КОД",
        "help_mv_name": "НАЗВАНИЕ",
        "help_mv_domain": "ДОМЕН",
        "help_mv_folder": "ПАПКА",
        "help_mv_file": "ФАЙЛ",
        "help_mv_env": "ИМЯ",
        "help_mv_n": "N",
        "help_mv_port": "ПОРТ",
        "help_mv_host": "АДРЕС",
        "help_mv_source": "ИСТОЧНИК",
        "help_mv_type": "ТИП",
        "help_mv_slug": "СЛАГ",
        "help_mv_text": "ТЕКСТ",
        "help_mv_topic": "ТЕМА",
    }
)
TEXT["en"].update(
    {
        "help_main": (
            "HERON — a file-based site engine.\n\n"
            "Language of help and messages: --notes ru|en, else HERON_NOTES, else "
            "build.notes from site.yaml in the current folder, else en."
        ),
        "help_new": (
            "Create a site from scratch: in a new folder or in the current one (`.`).\n\n"
            "In a terminal it asks questions: notes language, name, domain, site "
            "languages, main language. Without a terminal (an agent, CI, docker without "
            "-it) it asks nothing: values come from flags or defaults.\n\n"
            "The folder may be under git: .git, .gitignore, README and other service "
            "files are fine. It also places agent instructions in the notes language: "
            "agents/ and root pointers to them (the build does not see them); "
            "--no-agents skips them."
        ),
        "help_init": (
            "Complete the folder with what is missing, by what site.yaml says.\n\n"
            "Overwrites nothing without --force. No site.yaml means the site is only "
            "being started: in a terminal the same questions as `new`, the default "
            "languages are the folders already in content/. Notes language: --notes, "
            "else HERON_NOTES, else build.notes from site.yaml, else en.\n\n"
            "Agent instructions (agents/, AGENTS.md): without flags only the missing "
            "files, unless build.agents is `false`; --agents updates by the manifest; "
            "--no-agents places nothing and writes `build.agents: false` (21 §10)."
        ),
        "help_check": "Check the content and the config without building anything.",
        "help_build": "Build the site into dist/ or into the given folder.",
        "help_serve": "Local preview that rebuilds on changes.",
        "help_setup": (
            "The configurator: a questionnaire that writes site.yaml, the CI workflow "
            "and scripts.\n\n"
            "Without flags it opens the questionnaire in a browser (the address is on "
            "screen). With --answers it applies answers from a file — the same fields "
            "and the same check."
        ),
        "help_schema": (
            "JSON Schema of this version's contracts (21 §10): for an editor, an agent "
            "and CI.\n\n"
            "\b\n"
            "heron schema                  site.yaml\n"
            "heron schema --frontmatter    page front matter\n"
            "heron schema --errors         error code registry\n"
            "heron schema --export folder  all five files"
        ),
        "help_recipe": (
            "The nginx image recipe for a built site (Dockerfile) of this HERON version; "
            "its comments are in the notes language.\n\n"
            "`heron recipe > /tmp/Dockerfile && docker build -f /tmp/Dockerfile dist` "
            "— a site image without a HERON clone and without a Dockerfile in the site folder."
        ),
        "help_theme": "Themes: install by name, link or archive, show the catalog, pack your own.",
        "help_theme_get": (
            "Install a theme: starter, a name from the catalog, an https link or an "
            "archive file.\n\n"
            "The previous theme moves to .heron-cache/setup/. The theme's demo pages go "
            "only where there is no page yet: the site's pages are not overwritten."
        ),
        "help_theme_list": "The HERON theme catalog.",
        "help_theme_pack": (
            "Pack the site's theme together with its content — demo pages for heron theme get."
        ),
        "help_page": "A page draft with every section of its type.",
        "help_docs": (
            "Documentation of this engine version (21 §10): contents, topic, search, "
            "export.\n\n"
            "No file in the language asked for — the file in the other language is "
            "printed, with a notice on the first line.\n\n"
            "\b\n"
            "heron docs                        contents\n"
            "heron docs kit                    where an agent starts\n"
            "heron docs template page.md       a sample file\n"
            "heron docs --search E023          search all the documentation\n"
            "heron docs --export .heron-docs   as a folder, with links between files\n"
            "heron docs --lang en engine       a topic in English"
        ),
        "help_opt_help": "Show this message and exit.",
        "help_opt_version": "Show the version and exit.",
        "help_opt_debug": "Show the traceback of an unexpected error. Same as HERON_DEBUG=1.",
        "help_opt_notes": (
            "Language of comments in site files, of help and of on-screen messages: "
            "ru or en. Else HERON_NOTES, else build.notes from site.yaml, else en."
        ),
        "help_opt_verbose": "List every created file.",
        "help_opt_name": "Site name.",
        "help_opt_domain": "Domain without a scheme: example.com.",
        "help_opt_langs": "Languages, comma-separated, the first is the main one: en or en,ru.",
        "help_opt_yes": "Ask no questions: flags and defaults.",
        "help_opt_no_agents": (
            "Do not place agent instructions (agents/, AGENTS.md) and remember it: "
            "`build.agents: false`."
        ),
        "help_opt_force": "Overwrite existing files.",
        "help_opt_agents": (
            "Agent instructions only: update by the manifest agents/heron-kit.yaml — "
            "replace untouched files, keep and name edited ones (--force replaces them too)."
        ),
        "help_opt_strict": "Treat warnings as errors.",
        "help_opt_drafts": "Include pages with `published: false`.",
        "help_opt_json": "Errors and warnings as JSON — for an agent and CI.",
        "help_opt_out": "Where to build.",
        "help_opt_env": (
            "Build environment: `prod` opens indexing and counters, anything else does not."
        ),
        "help_opt_workers": (
            "Processes for image renditions; 0 — one per core, 1 — no pool. "
            "Overrides HERON_WORKERS and build.workers."
        ),
        "help_opt_port": "Port.",
        "help_opt_host": (
            "Where to listen. 127.0.0.1 by default, and 0.0.0.0 in the HERON image, "
            "so that the published port opens from outside the container."
        ),
        "help_opt_serve_drafts": "Show drafts (`published: false`); on by default.",
        "help_opt_answers": (
            "Questionnaire answers from YAML or JSON without a browser (an agent, CI). "
            "“-” reads stdin."
        ),
        "help_opt_dump": "Print the saved answers as YAML and exit.",
        "help_opt_setup_host": "Where to listen: as for heron serve.",
        "help_opt_schema_site": "site.yaml (the default).",
        "help_opt_schema_theme": "theme.yaml.",
        "help_opt_schema_frontmatter": "Page front matter.",
        "help_opt_schema_setup": "Answers of the heron setup questionnaire.",
        "help_opt_schema_errors": "Error code registry.",
        "help_opt_schema_export": "Write all five files into a folder.",
        "help_opt_pack_out": "Archive file; dist/theme.tar.gz by default.",
        "help_opt_page_lang": "Page language. The site's main language by default.",
        "help_opt_folder": "A folder inside the language tree.",
        "help_opt_docs_lang": (
            "Documentation language. Else --notes, HERON_NOTES, build.notes from "
            "site.yaml in the current folder, else en."
        ),
        "help_opt_search": "Search the documentation.",
        "help_opt_docs_export": (
            "Write the documentation into a folder — the same that a site gets in agents/."
        ),
        "help_opt_all_langs": (
            "With --export: both languages, folders ru/ and en/ (for the engine's site)."
        ),
        "help_mv_options": "[OPTIONS]",
        "help_mv_command": "COMMAND [ARGS]...",
        "help_mv_path": "PATH",
        "help_mv_codes": "CODES",
        "help_mv_code": "CODE",
        "help_mv_name": "NAME",
        "help_mv_domain": "DOMAIN",
        "help_mv_folder": "FOLDER",
        "help_mv_file": "FILE",
        "help_mv_env": "NAME",
        "help_mv_n": "N",
        "help_mv_port": "PORT",
        "help_mv_host": "HOST",
        "help_mv_source": "SOURCE",
        "help_mv_type": "TYPE",
        "help_mv_slug": "SLUG",
        "help_mv_text": "TEXT",
        "help_mv_topic": "TOPIC",
    }
)

# Служебные строки click для ru: каталог в духе gettext — исходная строка click
# (msgid) → перевод с теми же полями. heron/cli.py подставляет его вместо
# gettext в модулях click на время запуска; для en строки click как есть.
# Строка `heron, version …` не переводится: её разбирают скрипты и CI.
CLICK_RU: dict[str, str] = {
    "Usage:": "Использование:",
    "Options": "Параметры",
    "Commands": "Команды",
    "Positional arguments": "Аргументы",
    "Show this message and exit.": "Показать эту справку и выйти.",
    "Show the version and exit.": "Показать версию и выйти.",
    "default: {default}": "по умолчанию: {default}",
    "required": "обязательно",
    "env var: {var}": "переменная окружения: {var}",
    "(dynamic)": "(вычисляется)",
    "deprecated": "устарело",
    "Error: {message}": "Ошибка: {message}",
    "Try '{command} {option}' for help.": "Справка: '{command} {option}'.",
    "Invalid value for {param_hint}: {message}": "неверное значение {param_hint}: {message}",
    "Invalid value: {message}": "неверное значение: {message}",
    "Missing argument": "не хватает аргумента",
    "Missing option": "не хватает параметра",
    "Missing parameter": "не хватает значения",
    "Missing {param_type}": "не хватает значения: {param_type}",
    "Missing parameter: {param_name}": "не хватает значения: {param_name}",
    "No such option {name!r}.": "нет такого параметра {name!r}.",
    "No such command {name!r}.": "нет такой команды {name!r}.",
    "Did you mean {possibility}?": "Может быть, {possibility}?",
    "(Did you mean one of: {possibilities}?)": "(может быть, одно из: {possibilities}?)",
    "Got unexpected extra argument ({args})": "лишний аргумент ({args})",
    "Got unexpected extra arguments ({args})": "лишние аргументы ({args})",
    "Missing command.": "не указана команда.",
    "Aborted!": "Прервано.",
    "Option {name!r} does not take a value.": "параметр {name!r} не принимает значения.",
    "Option {name!r} requires an argument.": "параметру {name!r} нужно значение.",
    "Option {name!r} requires {nargs} arguments.": "параметру {name!r} нужно значений: {nargs}.",
    "Argument {name!r} takes {nargs} values.": "аргумент {name!r} принимает значений: {nargs}.",
    "Value must be an iterable.": "нужен список значений.",
    "Takes {nargs} values but 1 was given.": "нужно значений: {nargs}, передано: 1.",
    "Takes {nargs} values but {len} were given.": "нужно значений: {nargs}, передано: {len}.",
    "{value!r} is not {choice}.": "{value!r} — не {choice}.",
    "{value!r} is not one of {choices}.": "{value!r} — не из списка: {choices}.",
    "Choose from:\n\t{choices}": "Выберите из:\n\t{choices}",
    "{value} is not in the range {range}.": "{value} — вне диапазона {range}.",
    "{value!r} is not a valid {number_type}.": "{value!r} — не число.",
    "{value!r} is not a valid boolean. Recognized values: {states}": (
        "{value!r} — не да или нет. Подходят: {states}"
    ),
    "{value!r} is not a valid UUID.": "{value!r} — не UUID.",
    "{value!r} does not match the format {format}.": "{value!r} не подходит под формат {format}.",
    "{value!r} does not match the formats {formats}.": (
        "{value!r} не подходит ни под один формат: {formats}."
    ),
    "{len_type} values are required, but {len_value} was given.": (
        "нужно значений: {len_type}, передано: {len_value}."
    ),
    "{len_type} values are required, but {len_value} were given.": (
        "нужно значений: {len_type}, передано: {len_value}."
    ),
    "{name} {filename!r} does not exist.": "путь {filename!r} не существует.",
    "{name} {filename!r} is a file.": "путь {filename!r} — файл, а нужна папка.",
    "{name} {filename!r} is a directory.": "путь {filename!r} — папка, а нужен файл.",
    "{name} {filename!r} is not readable.": "путь {filename!r} не читается.",
    "{name} {filename!r} is not writable.": "путь {filename!r} закрыт для записи.",
    "{name} {filename!r} is not executable.": "путь {filename!r} не запускается.",
    "Could not open file {filename!r}: {message}": "не открывается файл {filename!r}: {message}",
    "unknown error": "неизвестная ошибка",
    "Error: invalid input": "Ошибка: ответ не понят",
    "Error: The two entered values do not match.": "Ошибка: два ответа не совпадают.",
    "Repeat for confirmation": "Повторите для подтверждения",
    "Press any key to continue...": "Нажмите любую клавишу...",
    "Do you want to continue?": "Продолжить?",
    "Confirm the action without prompting.": "Подтвердить без вопроса.",
}

# heron recipe по-английски (F16, E15.S1.T3): Dockerfile.site пишется по-русски, для en
# комментарии и сообщение echo заменяются целыми кусками (кусок файла, замена);
# инструкции Dockerfile не меняются. Поменяли комментарий в Dockerfile.site —
# поменяйте кусок здесь: tests/test_cli_help_lang.py ищет кириллицу в en-рецепте.
RECIPE_EN: tuple[tuple[str, str], ...] = (
    (
        "# Образ готового сайта: nginx и статика, больше ничего.\n"
        "#\n"
        "# Контекст сборки — уже собранная папка out/<сайт>-<окружение>, а не папка\n"
        "# контента. Так в образ физически не может попасть ни .git, ни исходники\n"
        "# картинок, ни макеты, и движка в работающем контейнере нет: в сети не\n"
        "# должно стоять ничего, что умеет читать файлы сайта и запускать плагины.\n"
        "#\n"
        "# Собирается через scripts/site.sh <сайт> image <окружение>.\n",
        "# The image of a built site: nginx and static files, nothing else.\n"
        "#\n"
        "# The build context is the already built folder out/<site>-<environment>,\n"
        "# not the content folder. This way neither .git nor source images nor\n"
        "# mockups can physically get into the image, and there is no engine in the\n"
        "# running container: nothing that can read the site files and run plugins\n"
        "# should face the network.\n"
        "#\n"
        "# Built with scripts/site.sh <site> image <environment>.\n",
    ),
    (
        "# nginx 1.30.6 (stable, 2026-10-14; njs 1.0.2) — закрывает все опубликованные\n"
        "# на дату advisories nginx.org, включая CVE-2026-15176, -93479, -95101,\n"
        "# -97629, -97205 (исправлены в 1.30.6) и -90439 (1.30.5). Прибит по digest\n"
        "# индекса образа: тег мог бы уехать под ногами. Обновляется отдельным\n"
        "# коммитом после сверки https://nginx.org/en/security_advisories.html.\n",
        "# nginx 1.30.6 (stable, 2026-10-14; njs 1.0.2) closes every nginx.org advisory\n"
        "# published by that date, including CVE-2026-15176, -93479, -95101, -97629,\n"
        "# -97205 (fixed in 1.30.6) and -90439 (1.30.5). Pinned by the image index\n"
        "# digest: a tag could move underfoot. Updated in a separate commit after\n"
        "# checking https://nginx.org/en/security_advisories.html.\n",
    ),
    (
        "# Конфиг nginx приезжает вместе со статикой: движок собирает его под языки\n"
        "# этого сайта. Руками написанный список языков разошёлся бы с содержимым\n"
        "# папки в первый же раз, когда сменят основной язык.\n"
        "#\n"
        "# Зачем он вообще: у образа по умолчанию не задан error_page, поэтому на\n"
        "# несуществующий адрес отдаётся встроенная страница nginx, а нарисованную\n"
        "# темой 404 не видит никто. Код ответа остаётся 404: заглушка с кодом 200\n"
        "# попадает в индекс и плодит дубли.\n",
        "# The nginx config comes together with the static files: the engine builds\n"
        "# it for this site's languages. A hand-written list of languages would drift\n"
        "# from the folder the first time the main language changes.\n"
        "#\n"
        "# Why it is needed at all: the image has no error_page by default, so a\n"
        "# missing address gets the built-in nginx page and nobody sees the 404 drawn\n"
        "# by the theme. The response code stays 404: a stub with code 200 gets into\n"
        "# the index and breeds duplicates.\n",
    ),
    (
        "# Права приезжают вместе с файлами, а nginx работает не под root: папка,\n"
        "# закрытая от чужих на машине сборки, внутри образа превращается в 403 на\n"
        "# весь сайт. Поэтому читаемость выставляем здесь, а не надеемся на умаск\n"
        "# того, кто собирал.\n"
        "#\n"
        "# Владельца конфига меняем не для красоты: стартовый скрипт образа правит\n"
        "# default.conf на месте (ipv6, резолверы), и от чужого файла он получает\n"
        "# отказ в правах — контейнер падает сразу после старта.\n",
        "# Permissions come with the files, and nginx does not run as root: a folder\n"
        "# closed to others on the build machine turns into a 403 for the whole site\n"
        "# inside the image. So readability is set here instead of relying on the\n"
        "# umask of whoever built it.\n"
        "#\n"
        "# The config owner is changed for a reason: the image start script edits\n"
        "# default.conf in place (ipv6, resolvers) and gets a permission error on a\n"
        "# file it does not own — the container dies right after the start.\n",
    ),
    (
        'echo "нет $conf — пересоберите сайт движком 0.1.0 или новее"',
        'echo "no $conf — rebuild the site with HERON 0.1.0 or newer"',
    ),
    (
        "# Проверка конфига идёт под тем же пользователем, под которым потом работает\n"
        "# сервер. Под root она врёт дважды: не видит отказов в правах и оставляет за\n"
        "# собой /tmp/nginx.pid, в который рабочий процесс потом не может писать —\n"
        "# контейнер падает на старте с «permission denied».\n",
        "# The config is checked as the same user the server later runs as. As root\n"
        "# the check lies twice: it does not see permission errors and leaves\n"
        "# /tmp/nginx.pid behind, which the worker process then cannot write to —\n"
        "# the container dies at the start with “permission denied”.\n",
    ),
)


# --- heron docs: пометки языка (21 §10) ---
# Пометка — на языке запрошенной темы: en-читатель должен её прочесть.
# have — язык файла, который печатается; want — запрошенный язык.
TEXT["ru"].update(
    {
        "docs_fallback": "[{have}: перевода на {want} пока нет]",
        "docs_stale": "[{want}: перевод отстаёт от {have}]",
        "docs_toc_other": "(откроется на {have})",
    }
)

TEXT["en"].update(
    {
        "docs_fallback": "[{have}: no English translation yet]",
        "docs_stale": "[{want}: the translation lags behind {have}]",
        "docs_toc_other": "(opens in {have})",
    }
)
