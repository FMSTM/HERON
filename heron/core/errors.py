"""Коды ошибок и предупреждений движка.

Разделение жёсткое: ошибка останавливает сборку, предупреждение попадает в отчёт.
Сообщение об ошибке обязано содержать путь к файлу, номер строки, что не так и что сделать.
Спецификация: docs/spec/21-engine.md, раздел 11.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ERRORS: dict[str, str] = {
    "E001": "битый YAML во фронтматтере",
    "E002": "нет title, h1 или description",
    "E003": "дубликат идентификатора секции в файле",
    "E004": "два файла дают один URL",
    "E005": "недопустимый слаг",
    "E006": "treats, procedures или related ссылается на несуществующую страницу",
    "E007": "картинки нет на диске",
    "E008": "у типа страницы нет шаблона в теме",
    "E009": "redirect_from совпадает с существующим URL",
    "E010": "обращение к несуществующей переменной в шаблоне",
    "E011": "site.yaml не проходит валидацию",
    "E012": "версия движка не удовлетворяет требованию heron из site.yaml",
    "E013": "тема не найдена ни локально, ни среди установленных пакетов",
    "E014": "плагин не установлен или упал при загрузке",
    "E015": "сырой HTML в markdown при build.allow_raw_html: false",
    "E016": "недопустимый идентификатор секции",
    "E017": "сборка прода без единой страницы",
    "E018": "папка ресурсов сайта задвоена",
    "E019": "у локального видео нет постера",
    "E020": "разметка schema.org не собирается",
}


@dataclass(slots=True)
class HeronError(Exception):
    """Ошибка, останавливающая сборку."""

    code: str
    message: str
    path: str | None = None
    line: int | None = None
    hint: str | None = None

    def __str__(self) -> str:
        where = self.path or "<неизвестный файл>"
        if self.line is not None:
            where = f"{where}:{self.line}"
        text = f"{self.code} {where}: {self.message}"
        if self.hint:
            text = f"{text}\n  что сделать: {self.hint}"
        return text


@dataclass(slots=True)
class Warning_:
    """Предупреждение. Не останавливает сборку, попадает в отчёт check.

    `kind` — вид предупреждения. Сводка группирует по нему, иначе сотня
    однотипных замечаний про переводы прячет десяток важных про файлы,
    которых нет на диске.
    """

    message: str
    path: str | None = None
    line: int | None = None
    kind: str = "прочее"


@dataclass(slots=True)
class Collector:
    """Копит ошибки и предупреждения, чтобы показать все сразу, а не по одной за прогон."""

    errors: list[HeronError] = field(default_factory=list)
    warnings: list[Warning_] = field(default_factory=list)

    def error(self, *args, **kwargs) -> None:
        self.errors.append(HeronError(*args, **kwargs))

    def warn(self, *args, **kwargs) -> None:
        self.warnings.append(Warning_(*args, **kwargs))

    @property
    def failed(self) -> bool:
        return bool(self.errors)
