"""Тексты командной строки на двух языках.

Язык сообщений — тот же, что язык пояснений в файлах сайта: флаг `--notes`,
затем `HERON_NOTES`, затем `build.notes` из `site.yaml`, затем английский.
Человек, который завёл сайт по-русски, и на экране читает по-русски.

Ключа нет в языке — берётся английский: сообщение на чужом языке лучше
падения на опечатке в словаре.
"""

from __future__ import annotations

import os
import re
import string

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        # --- находки init ---
        "found_site": "site.yaml: языки {languages}, тема {theme}",
        "found_content": "content/: {pages} {pages:страница|страницы|страниц}, языки: {langs}",
        "found_folder": "{folder}/ на месте",
        "none": "нет",
        "found": "нашёл",
        "created": "создал",
        "skipped": "оставил как есть: {count} {count:файл|файла|файлов}",
        "bad_notes": "язык пояснений {value!r}: есть ru и en",
        "bad_notes_flag_hint": "в --notes нужно ru или en",
        "bad_notes_env_hint": "в переменной HERON_NOTES нужно ru или en; уберите её или поправьте",
        "bad_notes_site_hint": "в build.notes из site.yaml нужно ru или en",
        "site_not_utf8": "site.yaml не в кодировке UTF-8, папка не тронута",
        "site_not_utf8_hint": "пересохраните site.yaml в UTF-8; `heron check` покажет ту же ошибку",
        "site_not_block": "site.yaml: {value} - не блок ключей, папка не тронута",
        "site_not_block_hint": (
            "site.yaml - набор ключей (site:, theme:, build:); `heron check` покажет ту же ошибку"
        ),
        "site_languages_not_list": "site.languages: {value} - не список, папка не тронута",
        "site_languages_not_list_hint": (
            "языки списком, например languages: [ru, en]; `heron check` покажет ту же ошибку"
        ),
        "build_agents_write_failed": "не удалось записать build.agents: {value} в site.yaml",
        "build_agents_write_failed_hint": "впишите в блок build строку `agents: {value}` вручную",
        # --- сводка того, что разложено ---
        "plan_found": "В папке уже есть:",
        "plan_made": "Создано:",
        "plan_config": "конфиг: {files}",
        "plan_content": "контент {code}: {files}",
        "plan_home": "главная",
        "plan_404": "страница 404",
        "plan_theme": (
            "тема: {count} {count:файл|файла|файлов} - theme.yaml, шаблоны, модули, стили"
        ),
        "plan_i18n": "строки интерфейса темы: {langs}",
        "plan_folders": "пустые папки: {folders}",
        "plan_notes": "записки heron-readme.md: {count} - что класть в каждую папку",
        "plan_other": "прочее: {files}",
        "plan_kept": "Не тронуто (уже было): {files}",
        "plan_kept_many": (
            "Не тронуто (уже было): {count} {count:файл|файла|файлов} - список: --verbose"
        ),
        "plan_overwritten": "Перезаписано (--force):",
        "plan_nothing": "Ничего создавать не понадобилось: всё уже на месте.",
        # --- new ---
        "new_title": "Новый сайт в папке {path}",
        "new_done": "Сайт создан: {path}",
        "init_done": "Папка {path} дополнена по site.yaml",
        "not_empty": (
            "Папка {path} не пуста, в ней есть: {files}\n"
            "  new создаёт сайт с нуля и чужие файлы не трогает. Служебные файлы git\n"
            "  ({service}) не мешают.\n"
            "  что сделать: если это уже папка сайта - `heron init {path}`, он дополнит\n"
            "  её недостающим и ничего не перезапишет. Иначе выберите пустую папку."
        ),
        "site_exists": (
            "В папке {path} уже есть сайт: site.yaml, языки {langs}.\n"
            "  new не нужен - он заводит сайт с нуля и готовую папку не трогает.\n"
            "  что сделать:\n"
            "    дополнить недостающим - `heron init {path}`\n"
            "    проверить и собрать - `heron check {path}`, `heron build {path}`\n"
            "    начать заново - уберите файлы сайта, оставив .git и .gitignore;\n"
            "    если они не закоммичены: `git clean -dn` покажет список, `git clean -d -f` удалит"
        ),
        "found_langs": "В content/ уже есть языки: {langs} - предложу их.",
        "no_questions": (
            "Вопросов не задаю: запуск без терминала. Значения - из флагов или по умолчанию.\n"
            "  Для опроса запустите в терминале; в докере - с ключом -it."
        ),
        # --- опрос ---
        "ask_intro": (
            "Несколько вопросов о сайте. Enter - принять значение в скобках.\n"
            "Всё это потом правится в site.yaml."
        ),
        "ask_name": "Название сайта",
        "ask_name_help": "как сайт называется для людей: в шапке, в <title>, в разметке",
        "ask_domain": "Домен",
        "ask_domain_help": (
            "без https:// и слешей, например example.com. Не знаете - Enter, останется заглушка"
        ),
        "ask_langs": "Языки сайта",
        "ask_langs_help": "коды через запятую: en или en, ru. Каждый язык - папка content/<код>/",
        "ask_default": "Основной язык",
        "ask_default_help": "отдаётся из корня (/about/), остальные - с префиксом (/ru/about/)",
        "ask_confirm": "Создать сайт?",
        "ask_summary": "Итого:",
        "ask_cancelled": "Отменено, ничего не создано.",
        "bad_domain": "домен пишется без схемы и пути: example.com",
        "bad_langs": "нужен хотя бы один код вида en, ru, en-gb; не подошло: {bad}",
        "bad_default": "основной язык должен быть в списке: {langs}",
        "placeholder": "заглушка - замените в site.yaml",
        # --- что дальше ---
        "next_title": "Что дальше:",
        "next_config": (
            "Настройте сайт в конфигураторе: `heron setup {path}` - название, домен, кто вы, "
            "публикация. Или руками в {path}/site.yaml."
        ),
        "next_domain": (
            "Домен сейчас заглушка {domain} - впишите настоящий в конфигураторе или в site.yaml."
        ),
        "next_home": "Главная - {files}: SEO-блок наверху (title, h1, description), ниже текст.",
        "next_page": "Новая страница: `heron page page about {path}`",
        "next_build": "Собрать: `heron build {path}` - результат в {path}/dist/",
        "next_check": "Проверить без сборки: `heron check {path}`",
        "next_langs": "Добавили язык в site.yaml - снова `heron init {path}`",
        # --- page ---
        "page_done": "Создана страница: {path}",
        "page_next": "Заполните SEO-блок и секции, затем `heron build {root}`",
        # --- пути ---
        "no_path": "Папки {path} нет.",
        "no_site": (
            "В папке {path} нет site.yaml - это не папка сайта.\n"
            "  что сделать: создать сайт здесь - `heron new {path}`; дополнить\n"
            "  существующую папку - `heron init {path}`."
        ),
        "container_path": (
            "  почему: движок работает в контейнере и видит только папку,\n"
            "  смонтированную в /site: это ваша текущая папка. Путь {path}\n"
            "  с вашего компьютера внутри контейнера не существует.\n"
            "  что сделать: передайте путь относительно текущей папки - `.`, если\n"
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
            "  их разработчикам движка - это ошибка движка, а не вашего сайта."
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
            "предупреждений {count}. Папка сборки не тронута - в ней прошлая удачная версия."
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
        "found_content": "content/: {pages} {pages:page|pages}, languages: {langs}",
        "found_folder": "{folder}/ is in place",
        "none": "none",
        "found": "found",
        "created": "created",
        "skipped": "left as is: {count} {count:file|files}",
        "bad_notes": "notes language {value!r}: ru and en are available",
        "bad_notes_flag_hint": "--notes takes ru or en",
        "bad_notes_env_hint": "HERON_NOTES takes ru or en; unset it or fix it",
        "bad_notes_site_hint": "build.notes in site.yaml takes ru or en",
        "site_not_utf8": "site.yaml is not UTF-8, the folder is left alone",
        "site_not_utf8_hint": "save site.yaml as UTF-8; `heron check` shows the same error",
        "site_not_block": "site.yaml: {value} - not a block of keys, the folder is left alone",
        "site_not_block_hint": (
            "site.yaml is a set of keys (site:, theme:, build:); `heron check` shows the same error"
        ),
        "site_languages_not_list": "site.languages: {value} - not a list, the folder is left alone",
        "site_languages_not_list_hint": (
            "languages go in a list, e.g. languages: [ru, en]; `heron check` shows the same error"
        ),
        "build_agents_write_failed": "could not write build.agents: {value} to site.yaml",
        "build_agents_write_failed_hint": (
            "add the line `agents: {value}` to the build block by hand"
        ),
        "plan_found": "Already in the folder:",
        "plan_made": "Created:",
        "plan_config": "config: {files}",
        "plan_content": "content {code}: {files}",
        "plan_home": "home page",
        "plan_404": "404 page",
        "plan_theme": "theme: {count} {count:file|files} - theme.yaml, templates, modules, styles",
        "plan_i18n": "theme interface strings: {langs}",
        "plan_folders": "empty folders: {folders}",
        "plan_notes": "heron-readme.md notes: {count} - what goes into each folder",
        "plan_other": "other: {files}",
        "plan_kept": "Left untouched (already there): {files}",
        "plan_kept_many": (
            "Left untouched (already there): {count} {count:file|files} - list: --verbose"
        ),
        "plan_overwritten": "Overwritten (--force):",
        "plan_nothing": "Nothing to create: everything is already in place.",
        "new_title": "New site in {path}",
        "new_done": "Site created: {path}",
        "init_done": "Folder {path} completed from site.yaml",
        "not_empty": (
            "Folder {path} is not empty, it contains: {files}\n"
            "  new builds a site from scratch and never touches other files. Git service\n"
            "  files ({service}) are fine.\n"
            "  what to do: if this is already a site folder, run `heron init {path}` -\n"
            "  it adds what is missing and overwrites nothing. Otherwise pick an empty folder."
        ),
        "site_exists": (
            "Folder {path} already has a site: site.yaml, languages {langs}.\n"
            "  new is not needed - it starts a site from scratch and leaves a ready folder alone.\n"
            "  what to do:\n"
            "    add what is missing - `heron init {path}`\n"
            "    check and build - `heron check {path}`, `heron build {path}`\n"
            "    start over - remove the site files, keeping .git and .gitignore;\n"
            "    if they are not committed: `git clean -dn` lists them, `git clean -d -f` removes"
        ),
        "found_langs": "content/ already has languages: {langs} - I will suggest them.",
        "no_questions": (
            "No questions asked: not running in a terminal. Values come from flags or defaults.\n"
            "  For the questions run it in a terminal; with docker, add -it."
        ),
        "ask_intro": (
            "A few questions about the site. Enter accepts the value in brackets.\n"
            "Everything can be changed later in site.yaml."
        ),
        "ask_name": "Site name",
        "ask_name_help": "what people call the site: header, <title>, structured data",
        "ask_domain": "Domain",
        "ask_domain_help": (
            "no https:// and no slashes, e.g. example.com. Not sure - Enter keeps a placeholder"
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
        "placeholder": "placeholder - replace it in site.yaml",
        "next_title": "What next:",
        "next_config": (
            "Set the site up in the configurator: `heron setup {path}` - name, domain, "
            "who you are, publishing. Or by hand in {path}/site.yaml."
        ),
        "next_domain": (
            "The domain is a placeholder {domain} - put the real one in the configurator "
            "or in site.yaml."
        ),
        "next_home": "Home page - {files}: SEO block on top (title, h1, description), text below.",
        "next_page": "New page: `heron page page about {path}`",
        "next_build": "Build: `heron build {path}` - output in {path}/dist/",
        "next_check": "Check without building: `heron check {path}`",
        "next_langs": "Added a language to site.yaml - run `heron init {path}` again",
        "page_done": "Page created: {path}",
        "page_next": "Fill in the SEO block and the sections, then `heron build {root}`",
        "no_path": "There is no folder {path}.",
        "no_site": (
            "Folder {path} has no site.yaml - it is not a site folder.\n"
            "  what to do: create a site here - `heron new {path}`; complete an\n"
            "  existing folder - `heron init {path}`."
        ),
        "container_path": (
            "  why: the engine runs in a container and sees only the folder mounted\n"
            "  at /site - your current folder. The path {path} from your computer\n"
            "  does not exist inside the container.\n"
            "  what to do: pass the path relative to the current folder - `.` if you\n"
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
            "  the engine developers - this is an engine bug, not a problem with your site."
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
        "done_pages": "{count} {count:page|pages}",
        "done_masters": "{count} source {count:image|images}",
        "done_files": "{count} {count:file|files}",
        "build_head": "HERON {version} · building {path} · environment {env}",
        "check_head": "HERON {version} · checking {path}",
        "build_failed": (
            "Build failed: {count} {count:error|errors}. The output folder is untouched. "
            "Fix {count:it|them} and build again."
        ),
        "check_failed": (
            "Check found {count} {count:error|errors}. A build would fail on {count:it|them}."
        ),
        "build_strict": (
            "Build stopped: strict mode (--strict or build.fail_on_warning), "
            "{count} {count:warning|warnings}. "
            "The output folder is untouched - it still holds the last good build."
        ),
        "check_strict": (
            "Check: strict mode (--strict or build.fail_on_warning), "
            "{count} {count:warning|warnings}."
        ),
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
        "E036": "an image master cannot be read as an image",
        "E037": "the theme demo does not show every type, block or section view",
    },
}


def plural(count: int, forms: str) -> str:
    """Форма слова при числе: `файл|файла|файлов` — по-русски, `file|files` — по-английски.

    Три формы — русское правило (1, 21 файл; 2–4, 22 файла; 5–20, 11–14 файлов),
    две — английское (1 file, иначе files).
    """
    words = forms.split("|")
    count = abs(count)
    if len(words) == 2:
        return words[0] if count == 1 else words[1]
    if len(words) != 3:
        raise ValueError(f"plural forms: {forms!r}")
    if count % 10 == 1 and count % 100 != 11:
        return words[0]
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return words[1]
    return words[2]


class _Formatter(string.Formatter):
    """str.format с одним дополнением: `{n:файл|файла|файлов}` — слово при числе n."""

    def format_field(self, value: object, format_spec: str) -> str:
        if "|" in format_spec and isinstance(value, int) and not isinstance(value, bool):
            return plural(value, format_spec)
        return super().format_field(value, format_spec)


_FORMATTER = _Formatter()


# Склейка строк списка-поля: та же, что в heron/contracts/loader.py (E011).
LINES_JOIN = "\n    "


def _field(lang: str, value: object) -> object:
    """Значение поля к показу: Msg рендерится на lang, список и кортеж склеиваются."""
    if isinstance(value, Msg):
        return value.text(lang)
    if isinstance(value, (list, tuple)):
        return LINES_JOIN.join(str(_field(lang, item)) for item in value)
    return value


def say(lang: str, key: str, /, **fields: object) -> str:
    """Текст по ключу на языке lang; lang и key позиционные, поля с такими именами допустимы."""
    table = TEXT.get(lang, TEXT["en"])
    template = table.get(key) or TEXT["en"][key]
    values = {name: _field(lang, value) for name, value in fields.items()}
    return _FORMATTER.vformat(template, (), values)


class Msg(str):
    """Сообщение ядра: ключ и поля, текст при показе. Строка по умолчанию русская."""

    key: str
    fields: dict[str, object]

    def __new__(cls, key: str, /, **fields: object) -> Msg:
        obj = super().__new__(cls, say("ru", key, **fields))
        obj.key = key
        obj.fields = fields
        return obj

    def text(self, lang: str, /) -> str:
        return say(lang, self.key, **self.fields)

    def __reduce__(self) -> tuple[object, tuple[str, dict[str, object]]]:
        return (_make_msg, (self.key, self.fields))


def _make_msg(key: str, fields: dict[str, object]) -> Msg:
    return Msg(key, **fields)


class MsgError(ValueError):
    """ValueError валидатора с Msg в args[0]."""

    def __init__(self, key: str, /, **fields: object) -> None:
        super().__init__(Msg(key, **fields))


IMAGE = "ghcr.io/fmstm/heron"
# Команды, которым в Docker нужен терминал: спрашивают (new, init) или
# останавливаются по Ctrl+C (setup, serve). Последним двум ещё нужен порт.
_ASKS = {"new", "init", "setup", "serve"}
_PORT = {"setup", "serve"}
_COMMAND = re.compile(r"`heron ([^`]+)`")


def image() -> str:
    """Образ, в котором запущен движок: канал из HERON_CHANNEL, иначе prod."""
    channel = os.environ.get("HERON_CHANNEL", "").strip()
    release = re.fullmatch(r"v(\d+\.\d+\.\d+.*)", channel)
    if release:
        return f"{IMAGE}:{release.group(1)}"
    return f"{IMAGE}:{channel if channel in ('prod', 'beta', 'dev') else 'prod'}"


def docker_command(args: str) -> str:
    """`heron <args>` целиком для Docker: та же команда, готовая к копированию."""
    name = args.split(maxsplit=1)[0] if args.strip() else ""
    flags = " -it" if name in _ASKS else ""
    if name in _PORT:
        flags += " -p 127.0.0.1:8000:8000"
    return (
        f'docker run --rm{flags} -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" '
        f"{image()} {args}"
    )


def for_docker(text: str) -> str:
    """Подсказки `heron …` - полными командами Docker, каждая своей строкой.

    Команда длинная, поэтому стоит отдельно, без кавычек: строку целиком
    выделяют и копируют в терминал. Текст вокруг остаётся на своих строках.
    """
    if not _COMMAND.search(text):
        return text
    parts: list[str] = []
    pos = 0
    for match in _COMMAND.finditer(text):
        gap = text[pos : match.start()]
        # Между командами бывает только «, » или « · » - их не переносим.
        if gap.strip(" ,;·") or pos == 0:
            if pos == 0:
                parts.append(gap.rstrip())
            else:
                parts.append("\n    " + gap.strip().lstrip(",;·- "))
        parts.append("\n      " + docker_command(match.group(1)))
        pos = match.end()
    tail = text[pos:]
    if tail.strip(" ,;·.\n"):
        parts.append("\n    " + tail.strip().lstrip(",;·- "))
    return "".join(parts)


def rendered(value: str | None, lang: str) -> str | None:
    """Msg на языке lang; str и None как есть."""
    if isinstance(value, Msg):
        return value.text(lang)
    return value


def title(lang: str, code: str) -> str:
    """Название ошибки по коду на языке сообщений."""
    from heron.core.errors import ERRORS, SCHEMA_CODES

    ru = ERRORS.get(code) or SCHEMA_CODES.get(code, code)
    if lang == "ru":
        return ru
    return TITLES["en"].get(code) or ru


# --- serve ---------------------------------------------------------------------
TEXT["ru"].update(
    {
        "serve_built": "собрано: {count} {count:файл|файла|файлов}",
        "serve_warnings": "предупреждений: {count}",
        "serve_dist": "собрано в {dist}",
        "serve_open": "открыто: {url}  (Ctrl+C - выход)",
        "serve_container": (
            "HERON работает в контейнере: откройте адрес на своём компьютере. "
            "Порт {port} должен быть проброшен в docker run только на эту машину: "
            "-p 127.0.0.1:{port}:{port}"
        ),
        "serve_lan": (
            "просмотр открыт для всей сети: любой в ней увидит черновики "
            "по адресу этого компьютера и порту {port}"
        ),
        "serve_changed": "изменения ({files}) - пересобираю",
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
        "serve_built": "built: {count} {count:file|files}",
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
        "serve_changed": "changes ({files}) - rebuilding",
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
            "Конфигуратор открыт: {url}  - откройте адрес целиком, с ключом после «#». "
            "Ctrl+C - выход."
        ),
        "setup_done": "Настройки записаны.",
        "setup_written": "записано: {files}",
        "setup_created": "создано: {files}",
        "setup_removed": "убрано (способ публикации сменился): {files}",
        "setup_kept": "не тронуто, файл не от конфигуратора: {files}",
        "setup_backup": "прежняя версия: {file}",
        "setup_next": "Дальше: `heron serve {path}` - посмотреть сайт.",
        "setup_bad": "ответы не прошли проверку: {problem}",
        "setup_no_site": "В папке {path} нет site.yaml - здесь нет сайта, настраивать нечего.",
        "setup_no_site_hint": (
            "Перейдите в папку сайта (cd имя-сайта) и запустите setup там, "
            "или создайте сайт: `heron new имя-сайта`"
        ),
        "theme_done": "Тема {name} поставлена.",
        "theme_demo": (
            "демо темы разложено: {count} {count:страница|страницы|страниц}, всего файлов "
            "{files} (ваши файлы не тронуты):"
        ),
        "theme_demo_kept": (
            "оставлены как есть (у сайта уже есть такой файл): {count} {count:файл|файла|файлов}"
        ),
        "theme_pack_warning": "предупреждение: {warning}",
        "theme_https": "тему по ссылке берём только по https",
    }
)
TEXT["en"].update(
    {
        "setup_open": (
            "The configurator is open: {url}  - open the whole address, "
            "with the key after “#”. Ctrl+C to stop."
        ),
        "setup_done": "Settings written.",
        "setup_written": "written: {files}",
        "setup_created": "created: {files}",
        "setup_removed": "removed (the publishing way changed): {files}",
        "setup_kept": "left alone, not written by the configurator: {files}",
        "setup_backup": "previous version: {file}",
        "setup_next": "Next: `heron serve {path}` - look at the site.",
        "setup_bad": "the answers did not pass the check: {problem}",
        "setup_no_site": "There is no site.yaml in {path} - no site here, nothing to set up.",
        "setup_no_site_hint": (
            "Go to the site folder (cd site-name) and run setup there, "
            "or create a site: `heron new site-name`"
        ),
        "theme_done": "Theme {name} is in place.",
        "theme_demo": (
            "the theme demo placed: {count} {count:page|pages}, {files} {files:file|files} "
            "in all (your files untouched):"
        ),
        "theme_demo_kept": (
            "kept as they are (the site already has such a file): {count} {count:file|files}"
        ),
        "theme_pack_warning": "warning: {warning}",
        "theme_https": "a theme by link is taken over https only",
    }
)


# --- комплект для агентов, docs, schema (20 §1, 21 §10, §12) -----------------------
TEXT["ru"].update(
    {
        # сводка new/init
        "kit_created": "инструкции для агентов: agents/, AGENTS.md - {code}, файлов {n}",
        "kit_updated": (
            "инструкции для агентов обновлены ({code}): заменено {updated}, добавлено {created}"
        ),
        "kit_in_place": "инструкции для агентов уже на месте - обновить: `heron init --agents`",
        "kit_off": (
            "инструкции для агентов не положены (build.agents: false) - "
            "включить: `heron init --agents`"
        ),
        "kit_skipped_edited": "правлен вами, не тронут: {files}",
        "kit_forced": "правлен вами - перезаписан (--force): {files}",
        "kit_current": "инструкции для агентов уже актуальны ({code})",
        "kit_bad_value": "build.agents: {value} - не понято, комплект не тронут",
        "kit_bad_value_hint": "допустимо true, kit или false; `heron check` покажет ту же ошибку",
        "build_not_block": "build: {value} - не блок ключей, папка не тронута",
        "build_not_block_hint": (
            "build - блок ключей с отступом (notes: ru, agents: true); "
            "`heron check` покажет ту же ошибку"
        ),
        "kit_orphan": "нет в новом комплекте, оставлен: {files}",
        "kit_fallback": "без перевода на {want}, положены на {have}: файлов {n}",
        "kit_about_placeholder": "<о проекте: заполняет архитектор>",
        "kit_manifest_head": "# Манифест комплекта для агентов. Пишет движок, руками не правят.",
        "kit_manifest_damaged": "манифест agents/heron-kit.yaml не прочитан - переписан заново",
        # сведение check (21 §12)
        "kit_found": (
            "`agents/`: инструкции для агентов, движок {engine}, {code}; в сборку не входит"
        ),
        "kit_unreadable": (
            "`agents/`: инструкции для агентов, манифест не прочитан; в сборку не входит"
        ),
        "kit_outdated": "комплект от {kit}, движок {engine} - обновить: `heron init --agents`",
        "kit_disabled": "комплект отключён",
        "kit_missing": "комплекта нет - `heron init`",
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
        "docs_no_topic": "Темы {name!r} нет. Оглавление: `heron docs`",
        "docs_all_langs": "--all-langs работает только вместе с --export <папка>",
        # heron schema
        "schema_exported": "Схемы записаны в {target}: {files}",
        "schema_one_kind": "Схема одна за раз: выберите один из флагов {flags}",
    }
)
TEXT["en"].update(
    {
        "kit_created": "agent instructions: agents/, AGENTS.md - {code}, {n} {n:file|files}",
        "kit_updated": "agent instructions updated ({code}): {updated} replaced, {created} added",
        "kit_in_place": "agent instructions already in place - update: `heron init --agents`",
        "kit_off": (
            "agent instructions not placed (build.agents: false) - enable: `heron init --agents`"
        ),
        "kit_skipped_edited": "edited by you, left as is: {files}",
        "kit_forced": "edited by you - overwritten (--force): {files}",
        "kit_current": "agent instructions already up to date ({code})",
        "kit_bad_value": "build.agents: {value} - not understood, the kit is left alone",
        "kit_bad_value_hint": "allowed: true, kit or false; `heron check` shows the same error",
        "build_not_block": "build: {value} - not a block of keys, the folder is left alone",
        "build_not_block_hint": (
            "build is an indented block of keys (notes: en, agents: true); "
            "`heron check` shows the same error"
        ),
        "kit_orphan": "not in the new kit, left in place: {files}",
        "kit_fallback": "no {want} translation yet, placed in {have}: {n} {n:file|files}",
        "kit_about_placeholder": "<about the project: the architect fills this in>",
        "kit_manifest_head": "# Agent kit manifest. Written by the engine, not edited by hand.",
        "kit_manifest_damaged": "agents/heron-kit.yaml could not be read - written anew",
        "kit_found": (
            "`agents/`: agent instructions, engine {engine}, {code}; not part of the build"
        ),
        "kit_unreadable": (
            "`agents/`: agent instructions, manifest unreadable; not part of the build"
        ),
        "kit_outdated": "kit from {kit}, engine {engine} - update: `heron init --agents`",
        "kit_disabled": "agent kit disabled",
        "kit_missing": "no agent kit - `heron init`",
        "agents_conflict": "--agents and --no-agents cannot be used together: pick one",
        # Пометка фолбэка — буквально как в 21 §10 на обоих языках: её ищут агенты и тесты.
        "docs_start_with": "Start with {path}",
        "docs_group_start": "Start",
        "docs_group_roles": "Agent roles",
        "docs_group_guide": "Guides in order",
        "docs_group_spec": "Reference",
        "docs_group_machine": "For machines",
        "docs_exported": "Documentation written to {target}: {n} {n:file|files}",
        "docs_not_found": "“{query}” is not in the documentation.",
        "docs_no_template": "There is no sample {file!r}. Available: {names}",
        "docs_no_topic": "There is no topic {name!r}. Contents: `heron docs`",
        "docs_all_langs": "--all-langs works only together with --export <folder>",
        "schema_exported": "Schemas written to {target}: {files}",
        "schema_one_kind": "One schema at a time: pick one of {flags}",
    }
)

# --- check: изменение данных в шаблонах темы (E033, 21 §7) ------------------------
# В подсказках двойные скобки: `say` подставляет поля через str.format.
TEXT["ru"].update(
    {
        "theme_inline_script": (
            "инлайн-скрипт в строке {line} заблокирует CSP сайта (script-src 'self'): "
            "вынесите код в файл темы, см. docs guide/04-theme"
        ),
        "sandbox_mutation": (
            "{call} меняет данные на месте: шаблоны темы рендерятся в неизменяемой "
            "песочнице, и сборка на этом месте упадёт с E033"
        ),
        "sandbox_hint_add": (
            "стройте новый список вместо изменения: `{{% set xs = xs + [item] %}}`; "
            "накопление в цикле - через namespace: `{{% set acc = namespace(xs=[]) %}}` … "
            "`{{% set acc.xs = acc.xs + [item] %}}`; отбор - фильтры selectattr/rejectattr, "
            "без повторов - `unique(case_sensitive=True, attribute='url')`; "
            "рецепты: `heron docs theme`"
        ),
        "sandbox_hint_keys": (
            "стройте новый словарь вместо изменения: `{{% set d = dict(d, key=value) %}}`; "
            "в цикле - через namespace: `{{% set acc = namespace(d={{}}) %}}` … "
            "`{{% set acc.d = dict(acc.d, key=value) %}}`; рецепты: `heron docs theme`"
        ),
        "sandbox_hint_remove": (
            "уберите лишнее фильтром, а не из самого списка: `xs|reject('equalto', x)|list`, "
            "`xs|rejectattr('id', 'in', ['a', 'b'])|list`, срез `xs[1:]`; "
            "рецепты: `heron docs theme`"
        ),
        "sandbox_hint_order": (
            "порядок задают фильтры, а не сам список: `xs|sort(attribute='title')|list`, "
            "`xs|reverse|list`; рецепты: `heron docs theme`"
        ),
    }
)
TEXT["en"].update(
    {
        "theme_inline_script": (
            "the inline script on line {line} will be blocked by the site CSP (script-src 'self'): "
            "move the code to a theme file, see docs guide/04-theme"
        ),
        "sandbox_mutation": (
            "{call} changes data in place: theme templates render in an immutable "
            "sandbox, and the build fails here with E033"
        ),
        "sandbox_hint_add": (
            "build a new list instead of changing one: `{{% set xs = xs + [item] %}}`; "
            "to collect in a loop use a namespace: `{{% set acc = namespace(xs=[]) %}}` … "
            "`{{% set acc.xs = acc.xs + [item] %}}`; to pick items use selectattr/rejectattr, "
            "to drop repeats `unique(case_sensitive=True, attribute='url')`; "
            "recipes: `heron docs theme`"
        ),
        "sandbox_hint_keys": (
            "build a new dict instead of changing one: `{{% set d = dict(d, key=value) %}}`; "
            "in a loop use a namespace: `{{% set acc = namespace(d={{}}) %}}` … "
            "`{{% set acc.d = dict(acc.d, key=value) %}}`; recipes: `heron docs theme`"
        ),
        "sandbox_hint_remove": (
            "drop items with a filter, not from the list itself: "
            "`xs|reject('equalto', x)|list`, `xs|rejectattr('id', 'in', ['a', 'b'])|list`, "
            "a slice `xs[1:]`; recipes: `heron docs theme`"
        ),
        "sandbox_hint_order": (
            "set the order with filters, not on the list itself: "
            "`xs|sort(attribute='title')|list`, `xs|reverse|list`; recipes: `heron docs theme`"
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
        "report_pages": "Страниц - {count} ({by_lang})",
        "report_types": "Типы - {by_type}",
        "report_untranslated": "Не переведено:",
        "report_missing": "Тема ждёт секцию, а в файле её нет:",
        "report_missing_line": (
            "  {section:12} - {count} {count:страница|страницы|страниц}: {shown}"
        ),
        "report_format": "Формат секции не тот, которого ждёт тема (это не ошибка):",
        "report_format_line": "  {source}: {section} - ждали {want}, пришло {got}",
        "report_format_fix": (
            "  как исправить: если по смыслу это форма из «ждали» - задайте её "
            "классом в якоре секции: `## Заголовок {{#якорь .checklist}}`; если права "
            "разметка - поменяйте форму в `uses` типа в theme.yaml: `якорь:форма`"
        ),
        "report_nameless": "В меню, но без короткого имени - покажется имя файла:",
        "report_unused_sections": "Секции, которых тема не использует (опечатка в якоре?):",
        "report_unused_modules": "Модули темы, которые не зовёт ни один шаблон: {names}",
        "report_broken": "Ссылки в никуда:",
        "report_orphans": "На эти страницы никто не ссылается: {urls}",
        "report_schema": "Разметка schema.org - {by_kind}",
        "report_unused_media": "Файлы в media, которых никто не ждёт - {count}:",
        "report_static_media": "В static лежит контент - его место в media:",
        "report_uneven": "Поле есть не у всех элементов списка (шаблон обязан это учесть):",
        "report_uneven_line": "  {owner}: {where} - {field} у {have} из {total}",
        "report_list": "список",
        "report_nginx_ok": "nginx -t на собранном конфиге: прошёл",
        "report_manual_dates": (
            "Ручная дата updated у {manual} из {total} {total:страницы|страниц|страниц} "
            "перекрывает updated_from: {mode} - у этих страниц дата из {mode} не берётся. "
            "Где дата должна обновляться сама, уберите updated из фронтматтера."
        ),
        "report_notes_missing": "Без пояснительной записки (это не ошибка): {folders}",
        "report_root": "корень",
        "summary_warnings": "Предупреждений - {count}:",
        "summary_more": "    … и ещё {count}",
        "summary_full": "  полный список: {path}",
        "summary_unknown_file": "<неизвестный файл>",
    }
)
TEXT["en"].update(
    {
        "report_pages": "Pages - {count} ({by_lang})",
        "report_types": "Types - {by_type}",
        "report_untranslated": "Not translated:",
        "report_missing": "The theme expects a section the file does not have:",
        "report_missing_line": "  {section:12} - {count} {count:page|pages}: {shown}",
        "report_format": "A section is not in the form the theme expects (not an error):",
        "report_format_line": "  {source}: {section} - expected {want}, got {got}",
        "report_format_fix": (
            "  how to fix: if by meaning it is the expected form, set it with a class "
            "in the section anchor: `## Heading {{#anchor .checklist}}`; if the markup is "
            "right, change the form in the type's `uses` in theme.yaml: `anchor:form`"
        ),
        "report_nameless": "In the menu without a short name - the file name will show:",
        "report_unused_sections": "Sections the theme does not use (a typo in the anchor?):",
        "report_unused_modules": "Theme modules no template calls: {names}",
        "report_broken": "Links to nowhere:",
        "report_orphans": "No page links to these: {urls}",
        "report_schema": "schema.org markup - {by_kind}",
        "report_unused_media": "Files in media nothing expects - {count}:",
        "report_static_media": "Content sits in static - it belongs in media:",
        "report_uneven": "A field only some list items have (the template must allow for it):",
        "report_uneven_line": "  {owner}: {where} - {field} in {have} of {total}",
        "report_list": "list",
        "report_nginx_ok": "nginx -t on the built config: passed",
        "report_manual_dates": (
            "A manual updated date on {manual} of {total} {total:page|pages} overrides "
            "updated_from: {mode} - these pages do not take the date from {mode}. "
            "Where the date should update by itself, remove updated from the front matter."
        ),
        "report_notes_missing": "No explanatory note (not an error): {folders}",
        "report_root": "root",
        "summary_warnings": "Warnings - {count}:",
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
            "комплект оставлен на {kit}, build.notes - {notes}: "
            "сменить язык комплекта - `heron init --agents`"
        ),
    }
)
TEXT["en"].update(
    {
        "kit_lang_changed": "kit language changed: {old} → {new} (build.notes)",
        "kit_lang_kept": (
            "the kit stays in {kit}, build.notes is {notes}: "
            "to switch the kit language - `heron init --agents`"
        ),
    }
)

# E024 общего писателя (write_files): на месте папки не папка, на месте файла
# ссылка или папка. Язык - от вызывающего (--notes, HERON_NOTES, build.notes),
# текст целиком на одном языке (E13.S1.T17, E13.S1.T19).
TEXT["ru"].update(
    {
        "write_dangling": (
            "на месте папки символическая ссылка, которая никуда не ведёт - записать в неё нельзя"
        ),
        "write_not_folder": "на месте папки файл или ссылка не на папку - записать в неё нельзя",
        "write_folder_hint": "уберите ссылку или файл либо назовите другую папку",
        "write_not_file": "на месте файла ссылка или папка - запись через неё не делается",
        "write_not_file_hint": "уберите или переименуйте её и повторите команду",
    }
)
TEXT["en"].update(
    {
        "write_dangling": (
            "a symbolic link that leads nowhere stands where a folder should be - "
            "nothing can be written into it"
        ),
        "write_not_folder": (
            "a file or a link to something other than a folder stands where a folder "
            "should be - nothing can be written into it"
        ),
        "write_folder_hint": "remove the link or the file, or name another folder",
        "write_not_file": (
            "a link or a folder stands where a file should be - nothing is written through it"
        ),
        "write_not_file_hint": "remove or rename it and run the command again",
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
        "редиректы": "redirects",
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
            "HERON - файловый движок сайтов.\n\n"
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
            "и корневые указатели на них (сборка их не видит); --no-agents - без них."
        ),
        "help_init": (
            "Дополнить папку недостающим по тому, что написано в site.yaml.\n\n"
            "Ничего не перезаписывает без --force. Нет site.yaml - значит, сайт "
            "только заводится: в терминале те же вопросы, что у `new`, языки по "
            "умолчанию - папки, которые уже лежат в content/. Язык пояснений: "
            "--notes, иначе HERON_NOTES, иначе build.notes из site.yaml, иначе en.\n\n"
            "Инструкции для агентов (agents/, AGENTS.md): без флагов - только "
            "недостающие файлы, если build.agents не `false`; --agents - обновление "
            "по манифесту; --no-agents - не класть и записать `build.agents: false` "
            "(21 §10)."
        ),
        "help_check": "Проверить контент и конфиг, ничего не собирая.",
        "help_build": "Собрать сайт в dist/ или в указанную папку.",
        "help_serve": "Локальный просмотр с пересборкой при изменениях.",
        "help_setup": (
            "Конфигуратор: страница в браузере, которая пишет site.yaml, сценарий для CI "
            "и скрипты.\n\n"
            "Без флагов открывает конфигуратор в браузере (адрес - на экране). С --answers "
            "применяет ответы из файла - те же поля и та же проверка."
        ),
        "help_schema": (
            "JSON Schema контрактов этой версии: для редактора, агента и CI (21 §10).\n\n"
            "\b\n"
            "heron schema                  site.yaml\n"
            "heron schema --frontmatter    фронтматтер страницы\n"
            "heron schema --errors         реестр кодов ошибок\n"
            "heron schema --describe       вывод heron describe --json\n"
            "heron schema --export папка   все шесть файлов"
        ),
        "help_recipe": (
            "Рецепт образа nginx для собранного сайта (Dockerfile) этой версии HERON; "
            "комментарии в нём - на языке пояснений.\n\n"
            "`heron recipe > /tmp/Dockerfile && docker build -f /tmp/Dockerfile dist` "
            "- образ сайта без клона HERON и без Dockerfile в папке сайта."
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
            "Упаковать тему сайта вместе с его контентом - демо-страницами для heron theme get. "
            "Демо должно показать каждый тип, блок и вид раздела темы, иначе E037."
        ),
        "help_page": "Заготовка страницы со всеми секциями своего типа.",
        "help_describe": (
            "Описание темы сайта: типы страниц и их секции, поля каждого блока, виды "
            "категорий, служебные поля страницы и подсказки к ним.\n\n"
            "Без имени - всё коротко; с именем типа или блока - он один, с подробной "
            "справкой и примером markdown. Значения по умолчанию - из site.yaml.\n\n"
            "\b\n"
            "heron describe              всё описание\n"
            "heron describe faq          один блок или тип\n"
            "heron describe --json       для агента и программ"
        ),
        "help_opt_describe_json": ("Одним JSON-объектом: форма - heron schema --describe."),
        "help_opt_describe_lang": (
            "Язык подсказок: ru, en или другой язык темы. По умолчанию язык пояснений."
        ),
        "help_docs": (
            "Документация этой версии движка: оглавление, тема, поиск, выгрузка (21 §10).\n\n"
            "Нет файла на нужном языке - печатается файл другого языка с пометкой "
            "первой строкой.\n\n"
            "\b\n"
            "heron docs                        оглавление\n"
            "heron docs kit                    с чего начинать агенту\n"
            "heron docs template page.md       образец файла\n"
            "heron docs theme-ref .            справка темы сайта: блоки, примеры, markdown\n"
            "heron docs --search E023          поиск по всей документации\n"
            "heron docs --export .heron-docs   папкой, со ссылками между файлами\n"
            "heron docs --lang en engine       тема на английском"
        ),
        # параметры
        "help_opt_help": "Показать эту справку и выйти.",
        "help_opt_version": "Показать версию и выйти.",
        "help_opt_debug": "Показать трейсбек непредвиденной ошибки. То же - HERON_DEBUG=1.",
        "help_opt_notes": (
            "Язык комментариев в файлах сайта, справки и сообщений на экране: ru или en. "
            "Иначе HERON_NOTES, иначе build.notes из site.yaml, иначе en."
        ),
        "help_opt_verbose": "Перечислить каждый созданный файл.",
        "help_opt_name": "Название сайта.",
        "help_opt_domain": "Домен без схемы: example.com.",
        "help_opt_langs": "Языки через запятую, первый - основной: en или en,ru.",
        "help_opt_yes": "Не задавать вопросов: флаги и значения по умолчанию.",
        "help_opt_no_agents": (
            "Не класть инструкции для агентов (agents/, AGENTS.md) и запомнить это: "
            "`build.agents: false`."
        ),
        "help_opt_force": "Перезаписывать существующие файлы.",
        "help_opt_agents": (
            "Только инструкции для агентов: обновить по манифесту agents/heron-kit.yaml - "
            "нетронутые заменить, правленые оставить и назвать (--force - заменить и их)."
        ),
        "help_opt_strict": "Считать предупреждения ошибками.",
        "help_opt_drafts": "Включить страницы с `published: false`.",
        "help_opt_json": "Ошибки и предупреждения в JSON - для агента и CI.",
        "help_opt_check_theme": (
            "Проверить сайт как демо темы: у каждого типа есть демо-страница, каждый блок "
            "и вид раздела показан (так же проверяет `heron theme pack`)."
        ),
        "help_opt_old_urls": (
            "Файл со старыми адресами (по строке на адрес или выгрузка из поисковой консоли): "
            "каждый должен вести на страницу, в redirect_from или в раздел «удалено»."
        ),
        "help_opt_out": "Куда собирать.",
        "help_opt_env": (
            "Окружение сборки: `prod` открывает индексацию и счётчики, всё прочее - нет."
        ),
        "help_opt_workers": (
            "Процессов на нарезку; 0 - по ядрам, 1 - без пула. "
            "Сильнее HERON_WORKERS и build.workers."
        ),
        "help_opt_port": "Порт.",
        "help_opt_host": (
            "Где слушать. По умолчанию 127.0.0.1, а в образе HERON - 0.0.0.0, "
            "чтобы проброшенный порт открывался снаружи контейнера."
        ),
        "help_opt_serve_drafts": "Показывать черновики (`published: false`); по умолчанию да.",
        "help_opt_answers": (
            "Ответы конфигуратора из YAML или JSON без браузера (агент, CI). «-» - из stdin."
        ),
        "help_opt_dump": "Напечатать записанные ответы в YAML и выйти.",
        "help_opt_setup_host": "Где слушать: как у heron serve.",
        "help_opt_schema_site": "site.yaml (по умолчанию).",
        "help_opt_schema_theme": "theme.yaml.",
        "help_opt_schema_frontmatter": "Фронтматтер страницы.",
        "help_opt_schema_setup": "Ответы конфигуратора heron setup.",
        "help_opt_schema_errors": "Реестр кодов ошибок.",
        "help_opt_schema_export": "Записать все шесть файлов в папку.",
        "help_opt_schema_describe": "Вывод heron describe --json.",
        "help_opt_schema_lang": (
            "Язык описаний в схемах. Иначе --notes, HERON_NOTES, build.notes из site.yaml "
            "текущей папки, иначе en."
        ),
        "help_opt_pack_out": "Файл архива; по умолчанию dist/theme.tar.gz.",
        "help_opt_page_lang": "Язык страницы. По умолчанию основной язык сайта.",
        "help_opt_folder": "Папка внутри языкового дерева.",
        "help_opt_docs_lang": (
            "Язык документации. Иначе --notes, HERON_NOTES, build.notes из site.yaml "
            "текущей папки, иначе en."
        ),
        "help_opt_search": "Найти в документации.",
        "help_opt_docs_export": (
            "Выложить документацию в папку - то же, что сайт получает в agents/."
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
        "help_opt_env_check": (
            "Окружение проверки: `prod` включает строгость prod (находки разметки - ошибки). "
            "Без флага - SITE_ENV, затем `dev`."
        ),
        "help_opt_allow_schema": (
            "Разово пропустить находку разметки, ключ SCH00N:<файл>:<путь>; можно повторять."
        ),
        "help_mv_key": "КЛЮЧ",
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
            "HERON - a file-based site engine.\n\n"
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
            "The configurator: a browser page that writes site.yaml, the CI workflow "
            "and scripts.\n\n"
            "Without flags it opens the configurator in a browser (the address is on "
            "screen). With --answers it applies answers from a file - the same fields "
            "and the same check."
        ),
        "help_schema": (
            "JSON Schema of this version's contracts (21 §10): for an editor, an agent "
            "and CI.\n\n"
            "\b\n"
            "heron schema                  site.yaml\n"
            "heron schema --frontmatter    page front matter\n"
            "heron schema --errors         error code registry\n"
            "heron schema --describe       the output of heron describe --json\n"
            "heron schema --export folder  all six files"
        ),
        "help_recipe": (
            "The nginx image recipe for a built site (Dockerfile) of this HERON version; "
            "its comments are in the notes language.\n\n"
            "`heron recipe > /tmp/Dockerfile && docker build -f /tmp/Dockerfile dist` "
            "- a site image without a HERON clone and without a Dockerfile in the site folder."
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
            "Pack the site's theme together with its content - demo pages for heron theme get. "
            "The demo must show every type, block and section view of the theme, otherwise E037."
        ),
        "help_page": "A page draft with every section of its type.",
        "help_describe": (
            "The description of the site theme: page types and their sections, the fields "
            "of every block, category views, the service fields of a page and their hints.\n\n"
            "Without a name - everything in short; with the name of a type or a block - only "
            "it, with full help and a markdown example. Defaults come from site.yaml.\n\n"
            "\b\n"
            "heron describe              the whole description\n"
            "heron describe faq          one block or type\n"
            "heron describe --json       for an agent and programs"
        ),
        "help_opt_describe_json": "One JSON object: its form is heron schema --describe.",
        "help_opt_describe_lang": (
            "The language of hints: ru, en or another language of the theme. "
            "The notes language by default."
        ),
        "help_docs": (
            "Documentation of this engine version (21 §10): contents, topic, search, "
            "export.\n\n"
            "No file in the language asked for - the file in the other language is "
            "printed, with a notice on the first line.\n\n"
            "\b\n"
            "heron docs                        contents\n"
            "heron docs kit                    where an agent starts\n"
            "heron docs template page.md       a sample file\n"
            "heron docs theme-ref .            the theme reference: blocks, examples, markdown\n"
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
            "Agent instructions only: update by the manifest agents/heron-kit.yaml - "
            "replace untouched files, keep and name edited ones (--force replaces them too)."
        ),
        "help_opt_strict": "Treat warnings as errors.",
        "help_opt_drafts": "Include pages with `published: false`.",
        "help_opt_json": "Errors and warnings as JSON - for an agent and CI.",
        "help_opt_check_theme": (
            "Check the site as the demo of its theme: every type has a demo page, every block "
            "and section view is shown (the same check as `heron theme pack`)."
        ),
        "help_opt_old_urls": (
            "File with old URLs (one per line or a Search Console CSV): each must lead to a "
            "page, a redirect_from or gone."
        ),
        "help_opt_out": "Where to build.",
        "help_opt_env": (
            "Build environment: `prod` opens indexing and counters, anything else does not."
        ),
        "help_opt_workers": (
            "Processes for image renditions; 0 - one per core, 1 - no pool. "
            "Overrides HERON_WORKERS and build.workers."
        ),
        "help_opt_port": "Port.",
        "help_opt_host": (
            "Where to listen. 127.0.0.1 by default, and 0.0.0.0 in the HERON image, "
            "so that the published port opens from outside the container."
        ),
        "help_opt_serve_drafts": "Show drafts (`published: false`); on by default.",
        "help_opt_answers": (
            "Configurator answers from YAML or JSON without a browser (an agent, CI). "
            "“-” reads stdin."
        ),
        "help_opt_dump": "Print the saved answers as YAML and exit.",
        "help_opt_setup_host": "Where to listen: as for heron serve.",
        "help_opt_schema_site": "site.yaml (the default).",
        "help_opt_schema_theme": "theme.yaml.",
        "help_opt_schema_frontmatter": "Page front matter.",
        "help_opt_schema_setup": "Answers of the heron setup configurator.",
        "help_opt_schema_errors": "Error code registry.",
        "help_opt_schema_export": "Write all six files into a folder.",
        "help_opt_schema_describe": "The output of heron describe --json.",
        "help_opt_schema_lang": (
            "Language of the descriptions in the schemas. Else --notes, HERON_NOTES, "
            "build.notes from site.yaml in the current folder, else en."
        ),
        "help_opt_pack_out": "Archive file; dist/theme.tar.gz by default.",
        "help_opt_page_lang": "Page language. The site's main language by default.",
        "help_opt_folder": "A folder inside the language tree.",
        "help_opt_docs_lang": (
            "Documentation language. Else --notes, HERON_NOTES, build.notes from "
            "site.yaml in the current folder, else en."
        ),
        "help_opt_search": "Search the documentation.",
        "help_opt_docs_export": (
            "Write the documentation into a folder - the same that a site gets in agents/."
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
        "help_opt_env_check": (
            "Check environment: `prod` applies prod strictness (markup findings are errors). "
            "Without the flag - SITE_ENV, then dev."
        ),
        "help_opt_allow_schema": (
            "Skip a markup finding once, key SCH00N:<file>:<path>; may be repeated."
        ),
        "help_mv_key": "KEY",
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
    "{value!r} is not {choice}.": "{value!r} - не {choice}.",
    "{value!r} is not one of {choices}.": "{value!r} - не из списка: {choices}.",
    "Choose from:\n\t{choices}": "Выберите из:\n\t{choices}",
    "{value} is not in the range {range}.": "{value} - вне диапазона {range}.",
    "{value!r} is not a valid {number_type}.": "{value!r} - не число.",
    "{value!r} is not a valid boolean. Recognized values: {states}": (
        "{value!r} - не да или нет. Подходят: {states}"
    ),
    "{value!r} is not a valid UUID.": "{value!r} - не UUID.",
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
    "{name} {filename!r} is a file.": "путь {filename!r} - файл, а нужна папка.",
    "{name} {filename!r} is a directory.": "путь {filename!r} - папка, а нужен файл.",
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
        "# Контекст сборки - уже собранная папка out/<сайт>-<окружение>, а не папка\n"
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
        "# nginx 1.30.6 (stable, 2026-10-14; njs 1.0.2) - закрывает все опубликованные\n"
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
        "# отказ в правах - контейнер падает сразу после старта.\n",
        "# Permissions come with the files, and nginx does not run as root: a folder\n"
        "# closed to others on the build machine turns into a 403 for the whole site\n"
        "# inside the image. So readability is set here instead of relying on the\n"
        "# umask of whoever built it.\n"
        "#\n"
        "# The config owner is changed for a reason: the image start script edits\n"
        "# default.conf in place (ipv6, resolvers) and gets a permission error on a\n"
        "# file it does not own - the container dies right after the start.\n",
    ),
    (
        'echo "нет $conf - пересоберите сайт движком 0.1.0 или новее"',
        'echo "no $conf - rebuild the site with HERON 0.1.0 or newer"',
    ),
    (
        "# Проверка конфига идёт под тем же пользователем, под которым потом работает\n"
        "# сервер. Под root она врёт дважды: не видит отказов в правах и оставляет за\n"
        "# собой /tmp/nginx.pid, в который рабочий процесс потом не может писать -\n"
        "# контейнер падает на старте с «permission denied».\n",
        "# The config is checked as the same user the server later runs as. As root\n"
        "# the check lies twice: it does not see permission errors and leaves\n"
        "# /tmp/nginx.pid behind, which the worker process then cannot write to -\n"
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

# --- проверка разметки schema.org: коды SCH001-SCH006 (21 §11) ---
# Тексты - из контракта этапа E17.S2 (docs/architecture/schema-mvp.md).
# detail и hint форматирует проверка (E17.S2.T4), строки отчёта - heron/core/report.py.
TITLES["en"].update(
    {
        "SCH001": "the schema.org type does not exist in the vocabulary",
        "SCH002": "the property does not belong to this type",
        "SCH003": "the value is not a member of the enumeration",
        "SCH004": "the value type does not fit the property",
        "SCH005": "the type or property is superseded",
        "SCH006": "an image from the markup is missing from the build",
    }
)

TEXT["ru"].update(
    {
        "sch001_detail": "тип {value!r} не найден в словаре schema.org {release}",
        "sch001_hint": "проверьте написание; похожие: {suggest}",
        "sch002_detail": "у типа {types} нет свойства {prop!r}",
        "sch002_hint": (
            "свойство бывает у типов: {domain}; уберите его или смените тип. "
            "Похожие свойства: {suggest}"
        ),
        "sch003_detail": "{prop}: {value!r} не входит в перечисление {enum}",
        "sch003_hint": "допустимые значения (первые 10): {members}",
        "sch004_detail": "{prop}: получено {got}, ожидается {expected}",
        "sch004_hint": "впишите значение ожидаемого типа",
        "sch005_detail": "{value!r} устарело в schema.org {release}",
        "sch005_hint": "замените на {replacement}",
        "sch006_detail": "{prop}: {url} - файла нет в сборке",
        "sch006_hint": (
            "положите файл в media/ и сошлитесь на него, или уберите адрес из разметки"
        ),
        "schema_head": (
            "Разметка schema.org (словарь {release}): узлов {nodes}, находок {n} "
            "({errors} {errors:ошибка|ошибки|ошибок}, "
            "{warnings} {warnings:предупреждение|предупреждения|предупреждений})"
        ),
        "schema_finding": "  {code} {file}:{path} - {detail} (страниц: {pages})",
        "schema_key": "    ключ исключения: {finding}",
        "schema_exceptions_head": "Исключения разметки: {n}",
        "schema_exception_site": "  {finding} - причина: «{reason}», до {until} ({source})",
        "schema_exception_flag": "{finding} - разово (--allow-schema)",
        "schema_unused": (
            "Лишнее исключение: {finding} - ничего не ловит, уберите его (из "
            "schema_exceptions или флага --allow-schema)"
        ),
        "schema_expired": (
            "Исключение просрочено: {finding} - срок {until} истёк, находка снова в силе"
        ),
        "schema_pending": "Свойства из раздела pending: {props} (сведение)",
        "schema_reason_missing": "Для исключения из проверки разметки нужна причина",
        "schema_exception_twice": "Одно и то же исключение перечислено дважды: {finding}",
        "schema_key_bad": "Неверный ключ исключения: {finding} (ожидается SCH00N:<файл>:<путь>)",
    }
)

TEXT["en"].update(
    {
        "sch001_detail": "type {value!r} is not in schema.org vocabulary {release}",
        "sch001_hint": "check the spelling; similar: {suggest}",
        "sch002_detail": "type {types} has no property {prop!r}",
        "sch002_hint": (
            "the property belongs to: {domain}; remove it or change the type. "
            "Similar properties: {suggest}"
        ),
        "sch003_detail": "{prop}: {value!r} is not a member of {enum}",
        "sch003_hint": "allowed values (first 10): {members}",
        "sch004_detail": "{prop}: got {got}, expected {expected}",
        "sch004_hint": "use a value of the expected type",
        "sch005_detail": "{value!r} is superseded in schema.org {release}",
        "sch005_hint": "replace it with {replacement}",
        "sch006_detail": "{prop}: {url} - the file is not in the build",
        "sch006_hint": (
            "put the file into media/ and reference it, or remove the address from the markup"
        ),
        "schema_head": (
            "schema.org markup (vocabulary {release}): {nodes} nodes, {n} findings "
            "({errors} {errors:error|errors}, {warnings} {warnings:warning|warnings})"
        ),
        "schema_finding": "  {code} {file}:{path} - {detail} (pages: {pages})",
        "schema_key": "    exception key: {finding}",
        "schema_exceptions_head": "Markup exceptions: {n}",
        "schema_exception_site": '  {finding} - reason: "{reason}", until {until} ({source})',
        "schema_exception_flag": "{finding} - one-off (--allow-schema)",
        "schema_unused": (
            "Unused exception: {finding} - matches nothing, remove it (from schema_exceptions "
            "or the --allow-schema flag)"
        ),
        "schema_expired": (
            "Expired exception: {finding} - {until} has passed, the finding applies again"
        ),
        "schema_pending": "Properties from the pending area: {props} (info)",
        "schema_reason_missing": "A schema exception needs a reason",
        "schema_exception_twice": "The same schema exception is listed twice: {finding}",
        "schema_key_bad": "Invalid schema exception key: {finding} (expected SCH00N:<file>:<path>)",
    }
)


# --- служебные поля страницы: подсказки словаря движка (heron/contracts/fields.py) ---
# hint - одна строка для наведения, help - что это, на что влияет на сайте и в поиске,
# хороший пример, частые ошибки. Тексты идут через say(): фигурные скобки удвоены.
TEXT["ru"].update(
    {
        "field_group_seo": "Поиск: заголовок и описание",
        "field_group_address": "Адрес и тип",
        "field_group_menu": "Меню и порядок",
        "field_group_cover": "Обложка",
        "field_group_social": "Соцсети и мессенджеры",
        "field_group_publishing": "Публикация",
        "field_group_section": "Блок страницы",
        "field_title_hint": "Заголовок в выдаче поисковика и на вкладке браузера, до 60 знаков",
        "field_title_help": (
            "Строка, которую человек видит в результатах поиска и на вкладке браузера. "
            "Тема дописывает к ней хвост сайта (seo.title_suffix в site.yaml), поэтому "
            "название сайта сюда не пишут.\n"
            "В поиске это главный текст ссылки: по нему решают, открывать ли страницу.\n"
            "Хорошо: «Как начать сайт за десять минут» - о чём страница, словами того, кто ищет.\n"
            "Частые ошибки: длиннее 60 знаков (поисковик обрежет), одинаковый title у разных "
            "страниц, title слово в слово как h1."
        ),
        "field_h1_hint": "Заголовок на самой странице - для того, кто её уже открыл",
        "field_h1_help": (
            "Крупный заголовок вверху страницы. Его читает человек, который уже пришёл, "
            "поэтому он может быть короче и живее title.\n"
            "Поисковики тоже его читают: h1 подтверждает, что страница о том же, что "
            "обещал title.\n"
            "Хорошо: title «Как начать сайт за десять минут», h1 «Десять минут до своего сайта».\n"
            "Частые ошибки: h1 копирует title, h1 «Главная» или «Страница», два h1 на странице."
        ),
        "field_description_hint": "Описание в выдаче под заголовком, до 155 знаков",
        "field_description_help": (
            "Пара предложений под заголовком в результатах поиска и в карточке страницы "
            "в разделе сайта. Поисковик может заменить его куском текста, но хорошее "
            "описание берёт чаще.\n"
            "Хорошо: «Одна команда создаёт сайт, дальше вы пишете текст в редакторе. "
            "Без баз данных и панелей.» - что человек получит.\n"
            "Частые ошибки: длиннее 155 знаков, повтор title, список ключевых слов через запятую."
        ),
        "field_slug_hint": "Часть адреса страницы латиницей; без него - имя файла",
        "field_slug_help": (
            "Последняя часть адреса: /guides/start/ у страницы со slug start. Пустое поле - "
            "адрес по имени файла. У каждого языка свой файл, поэтому и адрес на языке "
            "свой: /ru/nachalo/ и /en/start/.\n"
            "В поиске короткий понятный адрес выглядит надёжнее и попадает в выдачу.\n"
            "Хорошо: start, prices, how-to-order - латиница, цифры, дефис.\n"
            "Частые ошибки: смена адреса без redirect_from со старого (ссылки и позиции "
            "в поиске теряются), заглавные буквы и пробелы."
        ),
        "field_category_hint": "Категория - папка в content/, в которой лежит страница",
        "field_category_help": (
            "Раздел сайта, к которому относится страница: папка внутри content/<язык>/. "
            "Страница папки - её _index.md, она показывает страницы внутри. Пусто - "
            "страница в корне сайта.\n"
            "Категория входит в адрес (/guides/start/) и в хлебные крошки, а поисковик "
            "по ним понимает структуру сайта.\n"
            "Хорошо: guides для инструкций, а не одна общая папка pages.\n"
            "Частые ошибки: перенос страницы в другую папку без redirect_from со старого адреса."
        ),
        "field_type_hint": "Тип страницы - каким шаблоном темы она рисуется",
        "field_type_help": (
            "Тип выбирает шаблон темы и набор блоков. Без поля страница получает тип "
            "страниц своей категории (children_type), иначе основной тип темы.\n"
            "От типа зависит и разметка schema.org, которую тема ставит странице.\n"
            "Частая ошибка: тип, которого нет в теме, - сборка остановится с E008 и "
            "назовёт типы, которые есть."
        ),
        "field_children_type_hint": "Только у страницы категории: тип страниц внутри неё",
        "field_children_type_help": (
            "Пишется в _index.md папки. Все страницы этой папки без своего поля type "
            "получают этот тип: не нужно повторять его в каждом файле.\n"
            "Хорошо: children_type: page у раздела инструкций.\n"
            "Частая ошибка: поле в обычной странице, а не в _index.md - там оно ничего не делает."
        ),
        "field_menu_hint": "Показывать страницу в главном меню сайта",
        "field_menu_help": (
            "Главное меню - список nav.main в site.yaml, одно меню на все языки: адрес "
            "страницы или её ключ. Порядок в меню - порядок этого списка.\n"
            "Меню видно на каждой странице, поэтому в нём пять-семь самых нужных пунктов.\n"
            "Частые ошибки: двадцать пунктов, страница в меню, но с noindex или published: false."
        ),
        "field_nav_title_hint": "Короткое имя в меню и хлебных крошках; без него - h1",
        "field_nav_title_help": (
            "Короткое слово вместо длинного h1 там, где мало места: в меню, хлебных "
            "крошках, переключателе языков.\n"
            "Хорошо: h1 «Десять минут до своего сайта», nav_title «Начало».\n"
            "Частая ошибка: nav_title длиннее трёх слов - меню переносится на вторую строку."
        ),
        "field_order_hint": "Место в разделе и в связях: меньше - выше, по умолчанию 999",
        "field_order_help": (
            "Порядок страниц в карточках категории и в списках связей, по возрастанию. "
            "Порядок меню задаёт nav.main в site.yaml, не это поле.\n"
            "Хорошо: 10, 20, 30 - с шагом, чтобы потом вставить страницу между."
        ),
        "field_image_hint": "Обложка страницы - картинка из media/, от 1200 px в ширину",
        "field_image_help": (
            "Главная картинка страницы: превью в карточке раздела, обложка для поисковиков "
            "и соцсетей. Без неё движок берёт og_image, затем первую картинку текста, "
            "затем seo.og_default_image из site.yaml.\n"
            "В поиске: от 1200 px в ширину Google показывает крупное превью.\n"
            "Хорошо: непрозрачная фотография или иллюстрация по теме страницы.\n"
            "Частые ошибки: логотип вместо обложки, картинка уже 1200 px, прозрачный PNG."
        ),
        "field_image_alt_hint": (
            "Подпись обложки: что на картинке, для поиска и тех, кто её не видит"
        ),
        "field_image_alt_help": (
            "Текст alt. Его читают программы экранного доступа и поиск по картинкам. "
            "Нужен, если задана обложка.\n"
            "Хорошо: «Папка сайта в текстовом редакторе».\n"
            "Частые ошибки: «картинка», «фото1», повтор title."
        ),
        "field_og_image_hint": "Картинка для соцсетей и мессенджеров; без неё - обложка",
        "field_og_image_help": (
            "Что показывают соцсети и мессенджеры, когда ссылкой на страницу делятся. "
            "Пусто - обложка страницы, затем seo.og_default_image из site.yaml.\n"
            "Хорошо: 1200 x 630 px, крупный текст или понятный кадр.\n"
            "Частые ошибки: мелкий текст на картинке, картинка с важным по краям (её обрежут)."
        ),
        "field_og_title_hint": "Заголовок превью в соцсетях; без него - title",
        "field_og_title_help": (
            "Заголовок карточки ссылки в соцсетях и мессенджерах. Обычно не нужен: "
            "берётся title. Задайте, если для соцсетей нужен другой тон."
        ),
        "field_og_description_hint": "Описание превью в соцсетях; без него - description",
        "field_og_description_help": (
            "Текст под заголовком карточки ссылки. Обычно не нужен: берётся description."
        ),
        "field_noindex_hint": "Закрыть страницу от поисковиков и убрать из карты сайта",
        "field_noindex_help": (
            "Страница собирается и открывается по ссылке, но поисковикам велено её не "
            "показывать, и в sitemap её нет.\n"
            "Хорошо: страница «спасибо за заявку», служебные страницы.\n"
            "Частая ошибка: noindex на странице, которая стоит в меню, - её ищут и не находят."
        ),
        "field_published_hint": "Собирать ли страницу: false - черновик, на сайт не попадает",
        "field_published_help": (
            "published: false - страница не собирается; увидеть её можно в heron serve "
            "или с флагом --drafts.\n"
            "Частая ошибка: ссылка на черновик с других страниц - проверка сообщит о "
            "битой ссылке."
        ),
        "field_date_hint": "Дата публикации, ГГГГ-ММ-ДД",
        "field_date_help": (
            "Когда страница вышла. Её показывают тема и разметка статей, по ней "
            "сортируется лента.\n"
            "Хорошо: 2026-11-08.\n"
            "Частая ошибка: дата в будущем - сборка предупредит."
        ),
        "field_updated_hint": "Дата последней правки, ГГГГ-ММ-ДД; без неё - по build.updated_from",
        "field_updated_help": (
            "Когда страницу меняли по существу. Уходит в карту сайта (lastmod) и в "
            "разметку: поисковик чаще перечитывает свежие страницы. Без поля дату "
            "берёт движок, если в site.yaml build.updated_from: git или file.\n"
            "Частая ошибка: дата правки раньше даты публикации."
        ),
        "field_redirect_from_hint": "Старые адреса страницы - с них будет 301 сюда",
        "field_redirect_from_help": (
            "Список путей от корня: /old-address/. Движок ставит с них постоянное "
            "перенаправление 301, и поисковик переносит позиции на новый адрес.\n"
            "Хорошо: каждый раз, когда меняется slug или категория.\n"
            "Частая ошибка: адрес, который занят другой страницей, - ошибка E009."
        ),
        "field_heading_hint": "Заголовок блока на странице - текст после ##",
        "field_heading_help": (
            "Заголовок второго уровня: «## Как начать {{#start}}». Тема показывает его над "
            "блоком, поисковик по заголовкам понимает, о чём части страницы.\n"
            "Хорошо: вопрос или действие словами посетителя.\n"
            "Частые ошибки: заголовок «Блок 1», заголовок без якоря - тогда блока нет."
        ),
        "field_anchor_hint": "Якорь блока латиницей в фигурных скобках: {{#start}}",
        "field_anchor_help": (
            "Имя блока: по нему тема ставит блок на место, а ссылка /page/#start ведёт "
            "прямо к нему. После решётки можно назвать класс формы: {{#photos .gallery}}.\n"
            "Хорошо: start, faq, prices - строчная латиница, цифры, дефис.\n"
            "Частые ошибки: два одинаковых якоря в файле (ошибка E003), кириллица в якоре "
            "(ошибка E016)."
        ),
    }
)
TEXT["en"].update(
    {
        "field_group_seo": "Search: title and description",
        "field_group_address": "Address and type",
        "field_group_menu": "Menu and order",
        "field_group_cover": "Cover",
        "field_group_social": "Social networks and messengers",
        "field_group_publishing": "Publishing",
        "field_group_section": "Block of a page",
        "field_title_hint": (
            "The title in search results and on the browser tab, up to 60 characters"
        ),
        "field_title_help": (
            "The line a person sees in search results and on the browser tab. The theme "
            "appends the site suffix to it (seo.title_suffix in site.yaml), so the name of "
            "the site does not go here.\n"
            "In search it is the main text of the link: people decide by it whether to open "
            "the page.\n"
            'Good: "How to start a site in ten minutes" - what the page is about, in the '
            "words of the person searching.\n"
            "Common mistakes: longer than 60 characters (search engines cut it), the same "
            "title on different pages, title word for word equal to h1."
        ),
        "field_h1_hint": "The heading on the page itself - for someone who has already opened it",
        "field_h1_help": (
            "The large heading at the top of the page. It is read by a person who has "
            "already arrived, so it can be shorter and livelier than title.\n"
            "Search engines read it too: h1 confirms the page is about what title promised.\n"
            'Good: title "How to start a site in ten minutes", h1 "Ten minutes to your own site".\n'
            'Common mistakes: h1 copies title, h1 "Home" or "Page", two h1 on a page.'
        ),
        "field_description_hint": "The description under the title in search, up to 155 characters",
        "field_description_help": (
            "A couple of sentences under the title in search results and on the card of the "
            "page in a section of the site. Search engines may replace it with a piece of "
            "text, but they take a good description more often.\n"
            'Good: "One command creates a site, then you write text in an editor. No '
            'databases and no panels." - what a person gets.\n'
            "Common mistakes: longer than 155 characters, a repeat of title, a list of "
            "keywords separated by commas."
        ),
        "field_slug_hint": (
            "The part of the page address in Latin letters; without it - the file name"
        ),
        "field_slug_help": (
            "The last part of the address: /guides/start/ for a page with the slug start. "
            "An empty field means the address follows the file name. Every language has "
            "its own file, so its own address too: /ru/nachalo/ and /en/start/.\n"
            "In search a short clear address looks more trustworthy and shows in results.\n"
            "Good: start, prices, how-to-order - Latin letters, digits, hyphen.\n"
            "Common mistakes: changing the address without redirect_from from the old one "
            "(links and search positions are lost), capital letters and spaces."
        ),
        "field_category_hint": "The category - the folder in content/ that holds the page",
        "field_category_help": (
            "The section of the site the page belongs to: a folder inside content/<lang>/. "
            "The page of the folder is its _index.md, it shows the pages inside. Empty - "
            "the page is at the root of the site.\n"
            "The category is part of the address (/guides/start/) and of the breadcrumbs, "
            "and search engines learn the structure of the site from them.\n"
            "Good: guides for instructions, not one common folder pages.\n"
            "A common mistake: moving a page to another folder without redirect_from from "
            "the old address."
        ),
        "field_type_hint": "The page type - which theme template draws it",
        "field_type_help": (
            "The type picks the theme template and the set of blocks. Without the field a "
            "page gets the page type of its category (children_type), otherwise the main "
            "type of the theme.\n"
            "The schema.org markup the theme gives a page depends on the type too.\n"
            "A common mistake: a type the theme does not have - the build stops with E008 "
            "and names the types there are."
        ),
        "field_children_type_hint": "Only on a category page: the type of the pages inside it",
        "field_children_type_help": (
            "Written in the _index.md of a folder. All pages of that folder without their "
            "own type field get this type: there is no need to repeat it in every file.\n"
            "Good: children_type: page for a section of instructions.\n"
            "A common mistake: the field in an ordinary page, not in _index.md - there it "
            "does nothing."
        ),
        "field_menu_hint": "Show the page in the main menu of the site",
        "field_menu_help": (
            "The main menu is the list nav.main in site.yaml, one menu for all languages: "
            "the address of a page or its key. The order of the menu is the order of the list.\n"
            "The menu is visible on every page, so it holds the five to seven most needed items.\n"
            "Common mistakes: twenty items, a page in the menu but with noindex or "
            "published: false."
        ),
        "field_nav_title_hint": "A short name in the menu and breadcrumbs; without it - h1",
        "field_nav_title_help": (
            "A short word instead of a long h1 where there is little room: in the menu, the "
            "breadcrumbs, the language switcher.\n"
            'Good: h1 "Ten minutes to your own site", nav_title "Start".\n'
            "A common mistake: a nav_title longer than three words - the menu wraps to a "
            "second line."
        ),
        "field_order_hint": (
            "The place in a section and in relations: lower is higher, 999 by default"
        ),
        "field_order_help": (
            "The order of pages in the cards of a category and in relation lists, ascending. "
            "The order of the menu is set by nav.main in site.yaml, not by this field.\n"
            "Good: 10, 20, 30 - with gaps, to insert a page in between later."
        ),
        "field_image_hint": "The cover of the page - a picture from media/, 1200 px wide or more",
        "field_image_help": (
            "The main picture of the page: the preview on the card of a section, the cover "
            "for search engines and social networks. Without it the engine takes og_image, "
            "then the first picture of the text, then seo.og_default_image from site.yaml.\n"
            "In search: from 1200 px wide Google shows a large preview.\n"
            "Good: an opaque photo or illustration on the subject of the page.\n"
            "Common mistakes: a logo instead of a cover, a picture narrower than 1200 px, "
            "a transparent PNG."
        ),
        "field_image_alt_hint": (
            "The caption of the cover: what is in the picture, "
            "for search and people who cannot see it"
        ),
        "field_image_alt_help": (
            "The alt text. Screen readers and image search read it. It is needed when a "
            "cover is set.\n"
            'Good: "The folder of a site in a text editor".\n'
            'Common mistakes: "picture", "photo1", a repeat of title.'
        ),
        "field_og_image_hint": (
            "The picture for social networks and messengers; without it - the cover"
        ),
        "field_og_image_help": (
            "What social networks and messengers show when someone shares a link to the "
            "page. Empty - the cover of the page, then seo.og_default_image from site.yaml.\n"
            "Good: 1200 x 630 px, large text or a clear shot.\n"
            "Common mistakes: small text on the picture, important parts at the edges "
            "(they get cut off)."
        ),
        "field_og_title_hint": "The title of the preview in social networks; without it - title",
        "field_og_title_help": (
            "The title of the link card in social networks and messengers. Usually not "
            "needed: title is taken. Set it if social networks need a different tone."
        ),
        "field_og_description_hint": (
            "The description of the preview in social networks; without it - description"
        ),
        "field_og_description_help": (
            "The text under the title of the link card. Usually not needed: description is taken."
        ),
        "field_noindex_hint": "Hide the page from search engines and drop it from the sitemap",
        "field_noindex_help": (
            "The page is built and opens by a link, but search engines are told not to show "
            "it, and it is not in the sitemap.\n"
            'Good: a "thank you for your request" page, service pages.\n'
            "A common mistake: noindex on a page that is in the menu - people search for it "
            "and do not find it."
        ),
        "field_published_hint": (
            "Whether to build the page: false - a draft, it does not reach the site"
        ),
        "field_published_help": (
            "published: false - the page is not built; you can see it in heron serve or with "
            "the --drafts flag.\n"
            "A common mistake: links to a draft from other pages - the check reports a "
            "broken link."
        ),
        "field_date_hint": "The publication date, YYYY-MM-DD",
        "field_date_help": (
            "When the page came out. The theme and the markup of articles show it, the feed "
            "is sorted by it.\n"
            "Good: 2026-11-08.\n"
            "A common mistake: a date in the future - the build warns."
        ),
        "field_updated_hint": (
            "The date of the last edit, YYYY-MM-DD; without it - by build.updated_from"
        ),
        "field_updated_help": (
            "When the page was changed in substance. It goes into the sitemap (lastmod) and "
            "into the markup: search engines reread fresh pages more often. Without the "
            "field the engine takes the date if site.yaml has build.updated_from: git or file.\n"
            "A common mistake: an edit date earlier than the publication date."
        ),
        "field_redirect_from_hint": "Old addresses of the page - they get a 301 to here",
        "field_redirect_from_help": (
            "A list of paths from the root: /old-address/. The engine sets a permanent 301 "
            "redirect from them, and search engines move the positions to the new address.\n"
            "Good: every time the slug or the category changes.\n"
            "A common mistake: an address taken by another page - error E009."
        ),
        "field_heading_hint": "The heading of the block on the page - the text after ##",
        "field_heading_help": (
            'A second-level heading: "## How to start {{#start}}". The theme shows it above the '
            "block, search engines learn from headings what the parts of the page are about.\n"
            "Good: a question or an action in the words of a visitor.\n"
            'Common mistakes: the heading "Block 1", a heading without an anchor - then '
            "there is no block."
        ),
        "field_anchor_hint": "The anchor of the block in Latin letters in curly braces: {{#start}}",
        "field_anchor_help": (
            "The name of the block: the theme puts the block in place by it, and the link "
            "/page/#start leads straight to it. After the hash you can name the class of a "
            "form: {{#photos .gallery}}.\n"
            "Good: start, faq, prices - lowercase Latin letters, digits, hyphen.\n"
            "Common mistakes: two equal anchors in a file (error E003), Cyrillic in an "
            "anchor (error E016)."
        ),
    }
)

# --- heron describe: контракт темы и служебные поля (21 §10) -----------------------
TEXT["ru"].update(
    {
        "describe_unknown": (
            "{name}: такого типа страниц и модуля в теме нет\n  типы: {types}\n  модули: {modules}"
        ),
        "describe_unknown_hint": "без имени `heron describe` покажет всё описание темы",
        "describe_bad_lang": "--lang {lang}: нужен код языка вида ru, en или pt-br",
        "describe_head": "Тема {theme} «{title}» {version} · подсказки: {langs}",
        "describe_site": "Сайт: языки {langs}, основной {default} · описание на языке {lang}",
        "describe_not_described": (
            "Тема не описала поля блоков (fields в theme.yaml): опросник и студия покажут "
            "только служебные поля. Как описать - `heron docs theme`, «Поля блоков и подсказки»."
        ),
        "describe_service_head": "Служебные поля (описывает движок, у любой темы одинаковые)",
        "describe_types_head": "Типы страниц и их секции по порядку (* - обязательно)",
        "describe_modules_head": "Блоки (модули темы) и их поля",
        "describe_any": "любые блоки",
        "describe_children": "страницы внутри категории этого типа: {type}",
        "describe_views": "виды категории (ключ {key}): {views}",
        "describe_by_default": " (по умолчанию)",
        "describe_page_module": "модуль страницы, заполнять нечего",
        "describe_example": "как это выглядит в markdown:",
        "describe_more": (
            "Подробно о типе или блоке, с примерами - `heron describe <имя>`, "
            "для агента и программ - `heron describe --json`"
        ),
        "describe_md": "в markdown: {place}",
        "describe_default": "если не заполнить: {value}",
        "describe_from_file_name": "по имени файла",
        "describe_from_category_children_type": "тип страниц категории (children_type), иначе page",
        "describe_from_h1": "h1",
        "describe_from_cover_chain": (
            "og_image, затем первая картинка текста, затем seo.og_default_image"
        ),
        "describe_from_title": "title",
        "describe_from_description": "description",
        "describe_from_site": "из site.yaml: {path}",
        "describe_of": "пункты: {item}",
        "describe_max_length": "до {n} {n:знака|знаков|знаков}",
        "describe_min_items": "от {n} {n:пункта|пунктов|пунктов}",
        "describe_min_width": "от {n} px в ширину",
        "describe_type_text": "текст",
        "describe_type_markdown": "markdown",
        "describe_type_list": "список",
        "describe_type_image": "картинка",
        "describe_type_link": "ссылка",
        "describe_type_number": "число",
        "describe_type_date": "дата",
        "describe_type_enum": "выбор из списка",
        "describe_type_ref": "ссылка на страницу",
        "describe_type_flag": "да или нет",
        "describe_md_body": "всё содержимое блока",
        "describe_md_first_paragraph": "первый абзац вводного блока",
        "describe_md_second_paragraph": "второй абзац вводного блока",
        "describe_md_lead": "абзацы перед списком, таблицей или группами",
        "describe_md_quote": "цитата «> …»",
        "describe_md_items": "пункты списка «- …»",
        "describe_md_numbered": "пункты нумерованного списка «1. …»",
        "describe_md_bold": "жирный зачин пункта «**Термин.**»",
        "describe_md_tag": "метка «[МЕТКА]» в начале жирного зачина",
        "describe_md_text": "текст пункта после зачина",
        "describe_md_more": "продолжение пункта с отступом: код, второй абзац",
        "describe_md_groups": "группы «### Заголовок» с содержимым",
        "describe_md_heading": "текст заголовка «###»",
        "describe_md_heading_id": "якорь «{{#id}}» в заголовке «###»",
        "describe_md_content": "всё под заголовком группы",
        "describe_md_pairs": "строки «ключ | значение»",
        "describe_md_key": "левая часть строки, до «|»",
        "describe_md_value": "правая часть строки, после «|»",
        "describe_md_table_head": "шапка таблицы",
        "describe_md_table_rows": "строки таблицы после «|---|»",
        "describe_md_cells": "ячейки строки таблицы",
        "describe_md_image": "путь картинки «![подпись](путь)»",
        "describe_md_alt": "подпись картинки в квадратных скобках",
    }
)
TEXT["en"].update(
    {
        "describe_unknown": (
            "{name}: the theme has no such page type or module\n"
            "  types: {types}\n"
            "  modules: {modules}"
        ),
        "describe_unknown_hint": "without a name `heron describe` shows the whole theme",
        "describe_bad_lang": "--lang {lang}: a language code like ru, en or pt-br is needed",
        "describe_head": 'Theme {theme} "{title}" {version} · hints: {langs}',
        "describe_site": "Site: languages {langs}, main {default} · described in {lang}",
        "describe_not_described": (
            "The theme has not described the fields of its blocks (fields in theme.yaml): "
            "the questionnaire and the studio will show only the service fields. How to "
            'describe them - `heron docs theme`, "Block fields and hints".'
        ),
        "describe_service_head": "Service fields (described by the engine, the same for any theme)",
        "describe_types_head": "Page types and their sections in order (* - required)",
        "describe_modules_head": "Blocks (theme modules) and their fields",
        "describe_any": "any blocks",
        "describe_children": "pages inside a category of this type: {type}",
        "describe_views": "category views (key {key}): {views}",
        "describe_by_default": " (default)",
        "describe_page_module": "a page module, nothing to fill in",
        "describe_example": "what it looks like in markdown:",
        "describe_more": (
            "A type or a block in detail, with examples - `heron describe <name>`, "
            "for an agent and programs - `heron describe --json`"
        ),
        "describe_md": "in markdown: {place}",
        "describe_default": "if left empty: {value}",
        "describe_from_file_name": "the file name",
        "describe_from_category_children_type": (
            "the page type of the category (children_type), otherwise page"
        ),
        "describe_from_h1": "h1",
        "describe_from_cover_chain": (
            "og_image, then the first picture of the text, then seo.og_default_image"
        ),
        "describe_from_title": "title",
        "describe_from_description": "description",
        "describe_from_site": "from site.yaml: {path}",
        "describe_of": "items: {item}",
        "describe_max_length": "up to {n} {n:character|characters}",
        "describe_min_items": "at least {n} {n:item|items}",
        "describe_min_width": "{n} px wide or more",
        "describe_type_text": "text",
        "describe_type_markdown": "markdown",
        "describe_type_list": "list",
        "describe_type_image": "image",
        "describe_type_link": "link",
        "describe_type_number": "number",
        "describe_type_date": "date",
        "describe_type_enum": "choice from a list",
        "describe_type_ref": "link to a page",
        "describe_type_flag": "yes or no",
        "describe_md_body": "the whole content of the block",
        "describe_md_first_paragraph": "the first paragraph of the intro",
        "describe_md_second_paragraph": "the second paragraph of the intro",
        "describe_md_lead": "paragraphs before the list, the table or the groups",
        "describe_md_quote": 'a quote "> …"',
        "describe_md_items": 'items of a "- …" list',
        "describe_md_numbered": 'items of a numbered "1. …" list',
        "describe_md_bold": 'the bold start of an item "**Term.**"',
        "describe_md_tag": 'a tag "[TAG]" at the start of the bold start',
        "describe_md_text": "the text of an item after the start",
        "describe_md_more": "the indented rest of an item: code, a second paragraph",
        "describe_md_groups": 'groups "### Heading" with content',
        "describe_md_heading": 'the text of a "###" heading',
        "describe_md_heading_id": 'the anchor "{{#id}}" in a "###" heading',
        "describe_md_content": "everything under the heading of a group",
        "describe_md_pairs": '"key | value" lines',
        "describe_md_key": 'the left part of a line, before "|"',
        "describe_md_value": 'the right part of a line, after "|"',
        "describe_md_table_head": "the header of a table",
        "describe_md_table_rows": 'the rows of a table after "|---|"',
        "describe_md_cells": "the cells of a table row",
        "describe_md_image": 'the path of a picture "![caption](path)"',
        "describe_md_alt": "the caption of a picture in square brackets",
    }
)


# --- словарь по группам: heron/texts/<группа>.py (E15.S2) ---------------------------
def _load_groups() -> None:
    from heron.texts import load

    for lang, table in load().items():
        TEXT.setdefault(lang, {}).update(table)


_load_groups()
