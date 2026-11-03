"""Сообщения отрисовки страниц (core/render/env.py, core/render/pages.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "render_template_missing": "для типа страницы {type!r} нет шаблона {name}",
        "render_template_missing_hint": "создайте {name} в теме или задайте другой тип страницы",
        "render_template_syntax": "ошибка в шаблоне {name}, строка {line}: {detail}",
        "render_template_syntax_hint": "проверьте разметку Jinja в этой строке шаблона темы",
        "render_include_missing": "шаблон {name} ссылается на {missing!r}, а такого файла в теме нет",
        "render_include_missing_hint": (
            "пути в extends, include и import считаются от корня темы: templates/…, modules/…"
        ),
        "render_include_found_hint": "файл есть как {folder}/{missing} - пути считаются от корня темы",
        "render_sandbox": "шаблон {name} обращается к закрытому: {detail}",
        "render_sandbox_hint": (
            "шаблону доступны поля и вызовы из docs/ru/spec/21-engine.md §7; "
            "служебные атрибуты Python и изменение данных сайта закрыты"
        ),
        "render_undefined": "шаблон {name} обращается к тому, чего нет: {detail}",
        "render_theme_crash": "шаблон {name} упал при исполнении ({kind}): {detail}",
        "render_theme_crash_hint": "исправьте выражение в шаблоне темы; страница указана в пути",
        "render_undefined_hint": "опечатка в имени переменной или поле не заполнено во фронтматтере",
        "render_string_missing": "нет строки перевода {key!r} для языка {lang!r}",
        "render_module_missing": "тема вызывает модуль {name!r}, но {template} в ней нет",
        "render_module_missing_hint": "добавьте шаблон модуля или уберите вызов из шаблона типа",
        "render_i18n_symlink": "i18n/{lang}.yaml ведёт за пределы темы через ссылку",
        "render_symlink_hint": "положите сам файл в тему вместо ссылки на него",
        "render_i18n_key_type": (
            "ключ {key!r} прочитан как {type}, а не как строка - возьмите его в кавычки"
        ),
        "render_i18n_missing": "в теме нет строк интерфейса для языка {lang!r}",
        "render_template_symlink": "шаблон {template} ведёт за пределы темы через ссылку",
        "render_no_rendition": "нет нарезанного варианта {ratio} для {name}",
        "render_no_rendition_files": "нет файлов варианта {ratio} для {name}",
    },
    "en": {
        "render_template_missing": "there is no template {name} for page type {type!r}",
        "render_template_missing_hint": "create {name} in the theme or set another page type",
        "render_template_syntax": "error in template {name}, line {line}: {detail}",
        "render_template_syntax_hint": "check the Jinja markup on this line of the theme template",
        "render_include_missing": "template {name} refers to {missing!r}, but the theme has no such file",
        "render_include_missing_hint": (
            "paths in extends, include and import are counted from the theme root: "
            "templates/…, modules/…"
        ),
        "render_include_found_hint": "the file exists as {folder}/{missing}: paths are counted from the theme root",
        "render_sandbox": "template {name} accesses something forbidden: {detail}",
        "render_sandbox_hint": (
            "a template may use the fields and calls from docs/en/spec/21-engine.md §7; "
            "Python internals and changing site data are closed"
        ),
        "render_undefined": "template {name} refers to something that does not exist: {detail}",
        "render_theme_crash": "template {name} crashed while running ({kind}): {detail}",
        "render_theme_crash_hint": "fix the expression in the theme template; the page is given in the path",
        "render_undefined_hint": "a typo in the variable name or the field is empty in the front matter",
        "render_string_missing": "no translation string {key!r} for language {lang!r}",
        "render_module_missing": "the theme calls module {name!r}, but it has no {template}",
        "render_module_missing_hint": "add the module template or remove the call from the type template",
        "render_i18n_symlink": "i18n/{lang}.yaml leads outside the theme through a link",
        "render_symlink_hint": "put the file itself into the theme instead of a link to it",
        "render_i18n_key_type": "key {key!r} was read as {type}, not as a string: put it in quotes",
        "render_i18n_missing": "the theme has no interface strings for language {lang!r}",
        "render_template_symlink": "template {template} leads outside the theme through a link",
        "render_no_rendition": "no sliced variant {ratio} for {name}",
        "render_no_rendition_files": "no files of variant {ratio} for {name}",
    },
}
