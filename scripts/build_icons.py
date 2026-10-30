"""Сборка локального набора иконок из вендорного бандла Lucide.

Зачем скрипт. Полный `lucide.min.js` — 444 КБ (107 КБ gzip) на 2155 иконок,
а в разметке проекта используется около сотни. В браузер уходит
`app/static/icons.js` — те же иконки, но только нужные: данные (~19 КБ) плюс
маленький рантайм, который рисует `<i data-lucide>` в SVG (всего ~24 КБ).

Почему не «взять из npm и не вырезать вручную». Вендорный бандл лежит в
`scripts/vendor/lucide.min.js` и коммитится как есть: он источник данных для
сборки, а не файл, отдаваемый браузеру. Поэтому добавить иконку можно без
сети: имя попало в разметку или в Python — запустили скрипт, и оно в наборе.
Если иконки нет в самом бандле (например, опечатка), скрипт падает со
списком неизвестных имён, а не собирает молча пустой набор.

Запуск: `uv run python scripts/build_icons.py`
Проверка свежести набора — `tests/test_icons_bundle.py` (пересобирает
набор в памяти и сравнивает с файлом на диске).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "scripts" / "vendor" / "lucide.min.js"
APP_DIR = ROOT / "app"
OUTPUT = APP_DIR / "static" / "icons.js"

# Экспорт бандла: `a.PascalName=переменная` (алиасы вида `a.Trash2=La`
# указывают на ту же переменную — для нас это просто ещё одно имя).
_EXPORT_RE = re.compile(r"a\.([A-Za-z][A-Za-z0-9]*)=([A-Za-z_$][\w$]*)(?=[,;])")

# Строковые литералы в разметке и коде: имя иконки — kebab-case.
_DQ_RE = re.compile(r'"([a-z0-9][a-z0-9-]{0,40})"')
_SQ_RE = re.compile(r"'([a-z0-9][a-z0-9-]{0,40})'")

_SCAN_SUFFIXES = {".html", ".py", ".js"}


def pascal_name(kebab: str) -> str:
    """`arrow-down-left` → `ArrowDownLeft` — алгоритм Lucide как есть.

    Ключи бандла — PascalCase, и `createIcons` переводит в них имя из
    `data-lucide` именно так: разбить по `-`/`_`/пробелу, первую часть
    в нижний регистр, каждую следующую — с заглавной, затем поднять
    первую букву. Обратное преобразование (Pascal → kebab) неоднозначно:
    `Trash2` — это `trash-2`, а `Grid2x2` — `grid-2x2`, и правило «вставить
    дефис перед каждой заглавной» давало `trash2` и `grid2x2`. Поэтому
    имена не угадываются, а проверяются этим же прямым алгоритмом.
    """
    out = ""
    upper = False
    for ch in kebab:
        if ch in "-_" or ch <= " ":
            upper = bool(out)
            continue
        if not out:
            out += ch.lower()
        else:
            out += ch.upper() if upper else ch
        upper = False
    return out[:1].upper() + out[1:]


def vendor_exports(source: str) -> dict[str, str]:
    """Экспорты бандла: `ArrowDownLeft` → переменная с данными иконки."""
    exports: dict[str, str] = {}
    for export, variable in _EXPORT_RE.findall(source):
        exports.setdefault(export, variable)
    return exports


def used_icon_names(exports: dict[str, str]) -> list[str]:
    """Имена иконок (`data-lucide`), встречающиеся в коде проекта.

    Сканируются все строковые литералы `app/**/*.html|py|js`: иконка
    приходит в разметку не только литералом `data-lucide="x"`, но и из
    Python-словарей (`"icon": ...`), констант (`MESSENGER_ICONS`) и
    Jinja-выражений (`data-lucide="{{ row.icon }}"`). Проверять только
    литералы в атрибуте — значит молча потерять половину набора, поэтому
    фильтр один: литерал, который Lucide превращает в существующий экспорт.

    Лишние совпадения (например, слово `filter` в тексте) стоят несколько
    байт данных и ничего не ломают — это дешевле, чем пропущенная иконка.
    """
    found: set[str] = set()
    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        if path == OUTPUT:
            continue
        text = path.read_text(encoding="utf-8")
        for literal in _DQ_RE.findall(text) + _SQ_RE.findall(text):
            if pascal_name(literal) in exports:
                found.add(literal)
    return sorted(found)


def _js_value_to_json(text: str, where: str) -> str:
    """Объект/массив из минифицированного JS → JSON.

    Данные иконки выглядят как `[["path",{d:"M18 6 6 18"}]]`: ключи без
    кавычек, поэтому `json.loads` их не примет. Конвертер посимвольный и
    знает про строки — иначе двоеточие внутри `d:"…"` приняли бы за ключ.
    """
    out: list[str] = []
    stack: list[str] = []
    expect_key = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            body: list[str] = []
            while j < len(text):
                if text[j] == "\\":
                    body.append(text[j : j + 2])
                    j += 2
                    continue
                if text[j] == ch:
                    break
                body.append(text[j])
                j += 1
            else:
                raise ValueError(f"{where}: незакрытая строка")
            out.append('"' + "".join(body) + '"')
            i = j + 1
            continue
        if ch == "{":
            stack.append("obj")
            out.append(ch)
            expect_key = True
        elif ch == "[":
            stack.append("arr")
            out.append(ch)
            expect_key = False
        elif ch in "}]":
            stack.pop()
            out.append(ch)
            expect_key = False
        elif ch == ",":
            out.append(ch)
            expect_key = bool(stack) and stack[-1] == "obj"
        elif expect_key and (ch.isalpha() or ch in "_$"):
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            out.append('"' + text[i:j] + '"')
            i = j
            expect_key = False
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _extract_array(source: str, variable: str) -> str | None:
    """Тело массива `переменная=[...]` с балансировкой скобок вне строк."""
    match = re.search(rf"(?<![\w$.]){re.escape(variable)}=\[", source)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    quote: str | None = None
    i = start
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    return None


def collect_icons(source: str, names: list[str]) -> dict[str, list]:
    """Данные иконок; ключ — имя из `data-lucide` (kebab-case).

    Ключом служит именно то, что стоит в разметке: рантайм ищет иконку по
    этому имени, и расхождение в регистр или дефис давало бы пустой SVG
    без единой ошибки в консоли.
    """
    exports = vendor_exports(source)
    icons: dict[str, list] = {}
    unknown: list[str] = []
    for name in names:
        variable = exports.get(pascal_name(name))
        if variable is None:
            unknown.append(name)
            continue
        body = _extract_array(source, variable)
        if body is None:
            unknown.append(f"{name} (нет массива {variable})")
            continue
        try:
            icons[name] = json.loads(_js_value_to_json(body, name))
        except ValueError as exc:  # pragma: no cover - защита от смены формата
            unknown.append(f"{name}: {exc}")
    if unknown:
        raise SystemExit(
            "Не найдены иконки Lucide: " + ", ".join(unknown)
            + "\nПроверьте имена (kebab-case) или обновите "
            "scripts/vendor/lucide.min.js."
        )
    return icons


# Рантайм: повторяет контракт Lucide (`createIcons`, `data-lucide`, слияние
# атрибутов), но без таблицы всех иконок. Ключи набора — имена из разметки
# (`arrow-down-left`), их и ищет `render`.
_RUNTIME = """
/* Набор иконок OpenTutorCRM — СГЕНЕРИРОВАННЫЙ файл.
   Собран `scripts/build_icons.py` из `scripts/vendor/lucide.min.js` (v__VERSION__).
   Руками не правится: добавьте иконку в разметку и пересоберите набор. */
(function (global) {
  "use strict";

  var DEFAULTS = {
    xmlns: "http://www.w3.org/2000/svg",
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": 2,
    "stroke-linecap": "round",
    "stroke-linejoin": "round"
  };

  /* Ключи набора — ровно то, что стоит в `data-lucide` (kebab-case).
     У Lucide ключи PascalCase (`ArrowDownLeft`) и имя переводится в него
     на лету; здесь перевод не нужен, а расхождение в одну букву давало бы
     пустую иконку без ошибки. */
  var ICONS = __ICONS__;

  /* Узел SVG из описания `["path", {d: "…"}]` с вложенными детьми. */
  function createNode(spec) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", spec[0]);
    var attrs = spec[1] || {};
    Object.keys(attrs).forEach(function (key) {
      el.setAttribute(key, String(attrs[key]));
    });
    (spec[2] || []).forEach(function (child) {
      el.appendChild(createNode(child));
    });
    return el;
  }

  function classNames(value) {
    if (typeof value === "string") return value.split(" ");
    if (!value || !value.class) return [];
    if (typeof value.class === "string") return value.class.split(" ");
    return Array.isArray(value.class) ? value.class : [];
  }

  function unique(values) {
    return values
      .filter(function (item, index, all) {
        return !!item && item.trim() !== "" && all.indexOf(item) === index;
      })
      .join(" ")
      .trim();
  }

  /* Если у иконки есть aria-атрибут, role или title — она не декоративная,
     и `aria-hidden` не ставим: иначе скринридер потеряет подпись, которую
     дал автор разметки. */
  function hasAccessibleName(attrs) {
    for (var key in attrs) {
      if (key.indexOf("aria-") === 0 || key === "role" || key === "title") {
        return true;
      }
    }
    return false;
  }

  function render(el, name, extraAttrs) {
    var data = ICONS[name];
    if (!data) {
      console.warn("[icons] нет иконки: " + name);
      return;
    }

    var own = {};
    for (var i = 0; i < el.attributes.length; i++) {
      own[el.attributes[i].name] = el.attributes[i].value;
    }

    var attrs = Object.assign({}, DEFAULTS, { "data-lucide": name });
    if (!hasAccessibleName(own)) attrs["aria-hidden"] = "true";
    Object.assign(attrs, extraAttrs || {}, own);

    var classes = unique(
      ["lucide", "lucide-" + name].concat(classNames(own), classNames(extraAttrs))
    );
    if (classes) attrs.class = classes;

    el.parentNode.replaceChild(createNode(["svg", attrs, data]), el);
  }

  function createIcons(options) {
    options = options || {};
    var icons = options.icons || ICONS;
    var nameAttr = options.nameAttr || "data-lucide";
    var root = options.root || document;

    if (!Object.keys(icons).length) {
      throw new Error("Пустой набор иконок: пересоберите scripts/build_icons.py");
    }

    Array.prototype.forEach.call(
      root.querySelectorAll("[" + nameAttr + "]"),
      function (el) {
        render(el, el.getAttribute(nameAttr), options.attrs);
      }
    );
  }

  global.lucide = { createIcons: createIcons, icons: ICONS };
})(typeof globalThis !== "undefined" ? globalThis : this);
"""


def build(output: Path = OUTPUT) -> tuple[int, int]:
    """Собирает набор и пишет `output`. Возвращает (иконок, байт)."""
    if not VENDOR.is_file():
        raise SystemExit(f"Нет вендорного бандла: {VENDOR}")

    source = VENDOR.read_text(encoding="utf-8")
    version_match = re.search(r"@license lucide v([\d.]+)", source)
    version = version_match.group(1) if version_match else "?"

    names = used_icon_names(vendor_exports(source))
    icons = collect_icons(source, names)

    payload = json.dumps(icons, ensure_ascii=False, separators=(",", ":"))
    script = _RUNTIME.replace("__ICONS__", payload).replace("__VERSION__", version)
    output.write_text(script, encoding="utf-8")
    return len(icons), len(script.encode("utf-8"))


def main() -> int:
    count, size = build()
    print(f"иконок: {count}; app/static/icons.js: {size / 1024:.1f} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
