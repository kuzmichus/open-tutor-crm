"""Набор иконок: полнота, свежесть и вес.

Иконки рисует не полный бандл Lucide (444 КБ на 2155 иконок), а набор
используемых — `app/static/icons.js`, собранный `scripts/build_icons.py`.
У такой экономии есть цена: иконка, которой нет в наборе, молча не
отрисуется — в консоли останется `console.warn`, а на странице будет
пустое место. Поэтому набор проверяется тестами, а не глазами:

* каждая иконка из разметки и из Python-контекста присутствует в наборе;
* файл на диске совпадает с тем, что собрал бы скрипт сейчас (забыли
  пересобрать после правки шаблона — тест краснеет и говорит, что делать);
* набор остаётся маленьким: возврат полного бандла — регрессия веса.
"""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
ICONS_JS = APP_DIR / "static" / "icons.js"
BASE_HTML = APP_DIR / "templates" / "base.html"
VENDOR = ROOT / "scripts" / "vendor" / "lucide.min.js"

# Полный бандл — 444 КБ. Порог с запасом: набор растёт вместе с разметкой,
# но вчетверо вырасти от добавления десятка иконок не может.
MAX_ICONS_JS_BYTES = 96 * 1024

# `scripts/` — не пакет: модуль сборки подключаем путём, чтобы тесты
# проверяли ровно ту логику, которой пользуется `build_icons.py`.
sys.path.insert(0, str(ROOT / "scripts"))
import build_icons  # noqa: E402


def _icons_in_bundle() -> dict:
    """Данные набора из готового файла: `var ICONS = {...};`."""
    source = ICONS_JS.read_text(encoding="utf-8")
    match = re.search(r"var ICONS = (\{.*?\});\n", source, re.S)
    assert match, "в app/static/icons.js нет объекта ICONS"
    return json.loads(match.group(1))


def _literal_icons() -> set[str]:
    """Иконки, записанные в разметке литералом `data-lucide="имя"`."""
    names: set[str] = set()
    for path in APP_DIR.rglob("*.html"):
        names.update(
            re.findall(r'data-lucide="([a-z0-9-]+)"', path.read_text(encoding="utf-8"))
        )
    return names


def test_bundle_has_every_literal_icon():
    """Каждая иконка из разметки есть в наборе.

    Литерал `data-lucide="x"` — самый частый источник; пропущенная здесь
    иконка видна пользователю как пустое место в кнопке.
    """
    bundle = _icons_in_bundle()
    missing = sorted(_literal_icons() - set(bundle))
    assert not missing, (
        "иконок нет в наборе: " + ", ".join(missing)
        + "\nПересоберите: uv run python scripts/build_icons.py"
    )


def test_bundle_has_dynamic_icons():
    """Иконки из Python-контекста тоже в наборе.

    Часть иконок приходит в шаблон выражением (`data-lucide="{{ row.icon }}"`):
    имя живёт в сервисе (`operations_feed`, `MESSENGER_ICONS`, табы рассылок).
    Такую иконку не видно в разметке, и именно её легче всего потерять.
    """
    bundle = _icons_in_bundle()
    exports = build_icons.vendor_exports(VENDOR.read_text(encoding="utf-8"))

    dynamic: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # `"icon": "arrow-down-left"` в словарях представления.
        dynamic.update(re.findall(r'"icon"\s*:\s*"([a-z0-9-]+)"', text))
        # Константы вида `MESSENGER_ICONS = {"telegram": "send"}`.
        for block in re.findall(r"_ICONS\s*=\s*\{(.*?)\}", text, re.S):
            dynamic.update(re.findall(r':\s*"([a-z0-9-]+)"', block))

    # Jinja-выражения: строки внутри `data-lucide="{{ ... }}"`.
    for path in APP_DIR.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for expr in re.findall(r'data-lucide="\{\{(.*?)\}\}"', text, re.S):
            dynamic.update(re.findall(r"'([a-z0-9-]+)'", expr))

    # `nav_link(...)` сайдбара: имя иконки — третий аргумент.
    sidebar = (APP_DIR / "templates" / "sidebar.html").read_text(encoding="utf-8")
    dynamic.update(
        re.findall(r"nav_link\('[a-z]+',\s*'[^']*',\s*'([a-z0-9-]+)'", sidebar)
    )

    dynamic = {n for n in dynamic if build_icons.pascal_name(n) in exports}
    missing = sorted(dynamic - set(bundle))
    assert not missing, (
        "динамических иконок нет в наборе: " + ", ".join(missing)
        + "\nПересоберите: uv run python scripts/build_icons.py"
    )


def test_bundle_is_fresh(tmp_path):
    """Файл на диске совпадает с текущим результатом сборки.

    Ловушка tree-shaking'а: добавили иконку в шаблон, но забыли пересобрать
    набор — код в репозитории выглядит правильным, а иконка на странице
    пустая. Тест пересобирает набор в памяти и сравнивает с файлом.
    """
    fresh = tmp_path / "icons.js"
    expected_count, _ = build_icons.build(output=fresh)
    on_disk = _icons_in_bundle()
    assert len(on_disk) == expected_count, (
        f"в файле {len(on_disk)} иконок, сборка даёт {expected_count}; "
        "пересоберите: uv run python scripts/build_icons.py"
    )
    assert fresh.read_text(encoding="utf-8") == ICONS_JS.read_text(encoding="utf-8"), (
        "app/static/icons.js устарел; пересоберите: "
        "uv run python scripts/build_icons.py"
    )


def test_bundle_stays_small():
    """Набор остаётся в разы меньше полного бандла.

    Ради этого всё и делалось: 444 КБ (107 КБ gzip) на 79 используемых
    иконках — 56% веса главной страницы.
    """
    size = ICONS_JS.stat().st_size
    assert size < MAX_ICONS_JS_BYTES, (
        f"app/static/icons.js вырос до {size / 1024:.0f} КБ — "
        "проверьте, не вернулся ли полный бандл"
    )
    assert size < VENDOR.stat().st_size / 4


def test_page_uses_subset_not_full_bundle():
    """Страница подключает набор, а не вендорный бандл.

    Вендорный файл живёт в `scripts/vendor/` как источник для сборки:
    он коммитится, но браузеру не отдаётся.
    """
    markup = BASE_HTML.read_text(encoding="utf-8")
    assert 'src="/static/icons.js"' in markup
    assert "lucide.min.js" not in markup

    # Вендорный бандл остаётся в репозитории: без него набор не пересобрать
    # и нельзя добавить иконку без сети.
    assert VENDOR.is_file()
    assert not (APP_DIR / "static" / "lucide.min.js").exists(), (
        "полный бандл не должен лежать в app/static: он отдаётся браузеру"
    )


@pytest.mark.parametrize(
    "name", ["x", "plus", "trash-2", "undo-2", "arrow-down-left", "square-check-big"]
)
def test_icon_names_with_digits_and_suffixes(name):
    """Имена с цифрами и составные имена маппятся правильно.

    `trash-2` → `Trash2`, а не `Trash-2`: обратное преобразование
    Pascal → kebab неоднозначно, и именно на нём набор молча терял иконки
    корзины и отмены операции.
    """
    assert name in _icons_in_bundle()
