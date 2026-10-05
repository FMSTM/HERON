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
            "Папка {path} не пуста: в ней есть {files}.\n"
            "  new создаёт сайт с нуля и чужие файлы не трогает. Служебные файлы git\n"
            "  ({service}) не мешают.\n"
            "  что сделать: если это уже папка сайта — `heron init {path}`, он дополнит\n"
            "  её недостающим и ничего не перезапишет. Иначе выберите пустую папку."
        ),
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
        "next_config": "Проверьте {path}/site.yaml: домен, название, меню (nav.main), счётчики.",
        "next_domain": "Домен сейчас заглушка {domain} — впишите настоящий в site.yaml.",
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
        "step_write": "запись",
        "done": "готово",
        "done_config": "тема {theme}, языков {langs}",
        "done_pages": "страниц: {count}",
        "done_masters": "исходных картинок: {count}",
        "done_files": "файлов: {count}",
        # --- сборка и проверка ---
        "build_head": "HERON {version} · сборка {path} · окружение {env}",
        "check_head": "HERON {version} · проверка {path}",
        "build_failed": "Сборка не выполнена: ошибок {count}. Исправьте их и соберите снова.",
        "check_failed": "Проверка нашла ошибок: {count}. Сборка с ними не пройдёт.",
        "build_strict": (
            "Сборка остановлена: --strict, предупреждений {count}. Без --strict она прошла бы."
        ),
        "check_strict": "Проверка: --strict, предупреждений {count} — в проде это ошибки.",
        "build_env": "окружение {env} · домен {domain} · {index} · {counters}",
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
            "Folder {path} is not empty: it has {files}.\n"
            "  new builds a site from scratch and never touches other files. Git service\n"
            "  files ({service}) are fine.\n"
            "  what to do: if this is already a site folder, run `heron init {path}` —\n"
            "  it adds what is missing and overwrites nothing. Otherwise pick an empty folder."
        ),
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
        "next_config": "Check {path}/site.yaml: domain, name, menu (nav.main), counters.",
        "next_domain": "The domain is a placeholder {domain} — put the real one into site.yaml.",
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
        "step_write": "writing",
        "done": "done",
        "done_config": "theme {theme}, languages: {langs}",
        "done_pages": "{count} pages",
        "done_masters": "{count} source images",
        "done_files": "{count} files",
        "build_head": "HERON {version} · building {path} · environment {env}",
        "check_head": "HERON {version} · checking {path}",
        "build_failed": "Build failed: {count} errors. Fix them and build again.",
        "check_failed": "Check found {count} errors. A build would fail on them.",
        "build_strict": (
            "Build stopped: --strict, {count} warnings. Without --strict it would pass."
        ),
        "check_strict": "Check: --strict, {count} warnings — in production these are errors.",
        "build_env": "environment {env} · domain {domain} · {index} · {counters}",
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
