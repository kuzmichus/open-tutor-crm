"""Сборка набора favicon из вендорного исходника.

Зачем скрипт. Браузеру нужен не один файл, а десяток: `.ico` для старых
вкладок и закладок, PNG 16/32 для панели закладок и поисковой выдачи,
`apple-touch-icon` для «Добавить на экран Домой» в iOS, PNG 192/512 и
maskable-вариант для установки как PWA-приложения, SVG для резких
иконок на Retina. Держать это руками — значит рано или поздно получить
набор из разных версий знака. Поэтому все размеры выводятся из одного
исходника `scripts/vendor/favicon-source.png` (вендорный файл, браузеру
не отдаётся — как `scripts/vendor/lucide.min.js` у иконок интерфейса).

Про исходник. Он 200×200 — это предел, который дал дизайнер. 512 px
получается апскейлом (LANCZOS): на вкладке и в списке приложений это
незаметно, но для идеальной PWA-иконки нужен исходник ≥512 — тогда
достаточно заменить `favicon-source.png` и перегенерировать набор,
код скрипта менять не придётся.

Про SVG. Векторная версия — реконструкция по замерам исходника, а не
трассировка растра: круг r=94 с диагональным градиентом, три белых
эллипса (rx=62.5, ry=28, штрих 9.5) под 0/60/120° и белый центр r=21.5.
Параметры подобраны минимизацией расхождения с растром по маске белого.
Пересборка SVG из скрипта не нужна — он пишется здесь же, чтобы все
файлы набора появлялись одной командой.

Почему не ImageMagick. У `convert` на этой машине SVG рендерит встроенный
MSVG-рендерер: `linearGradient` он теряет и заливает фигуру чёрным,
поэтому растеризовать SVG для проверки бессмысленно. Совпадение
векторной версии с исходником проверяется глазами в браузере.

Запуск: `uv run --with pillow python scripts/build_favicons.py`
(Pillow — не зависимость проекта: скрипт нужен раз в жизни знака,
тащить его в `pyproject.toml` и образ незачем).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "vendor" / "favicon-source.png"
OUTPUT = ROOT / "app" / "static" / "favicons"

# Геометрия знака в системе координат исходника (200×200).
VIEWBOX = 200
CIRCLE_R = 94
ELLIPSE_RX = 62.5
ELLIPSE_RY = 28
ELLIPSE_STROKE = 9.5
ELLIPSE_ANGLES = (0, 60, 120)
CORE_R = 21.5

# Градиент фона: сэмплы исходника по диагонали круга, крайние точки
# экстраполированы на (6, 6) и (194, 194).
GRADIENT_START = "#11A3E9"
GRADIENT_END = "#895EF6"

# Цвет акцента для `theme-color` и `mask-icon`: сэмпл исходника в точке
# (100, 20) — верх круга.
THEME_COLOR = "#3290ED"

APP_NAME = "OpenTutorCRM"
APP_DESCRIPTION = "CRM для репетитора: ученики, занятия, финансы и напоминания"

# Порог «белое против фона» для маски знака: у белого min(r, g, b) = 255,
# у синего и фиолетового градиента — 17…94. Растяжка 110…235 сохраняет
# сглаженные края растра как полупрозрачность.
_MASK_LOW = 110
_MASK_HIGH = 235


def _load_source() -> Image.Image:
    """Исходник как RGBA; падаем, если файла нет или он не того размера."""
    if not SOURCE.is_file():
        raise SystemExit(f"Нет исходника знака: {SOURCE}")
    image = Image.open(SOURCE)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    if image.size != (VIEWBOX, VIEWBOX):
        raise SystemExit(
            f"Исходник должен быть {VIEWBOX}×{VIEWBOX}, а он {image.size[0]}×{image.size[1]}"
        )
    return image


def _resize(image: Image.Image, size: int) -> Image.Image:
    """Уменьшение LANCZOS: единственный фильтр без «звона» на краях знака."""
    return image.resize((size, size), Image.LANCZOS)


def _on_white(image: Image.Image) -> Image.Image:
    """Свести прозрачность на белый.

    iOS не поддерживает прозрачность в `apple-touch-icon` и заливает её
    чёрным — иконка на домашнем экране становится чёрным квадратом.
    """
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    background.alpha_composite(image)
    return background.convert("RGB")


def _mark_mask(image: Image.Image) -> Image.Image:
    """Маска белого знака: 255 — знак, 0 — фон.

    Нужна только для maskable-иконки: там знак переносится на градиент
    без прозрачности и в safe zone, а значит его надо отрезать от
    исходного круга.
    """
    mask = Image.new("L", image.size, 0)
    src = image.load()
    dst = mask.load()
    span = _MASK_HIGH - _MASK_LOW
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            r, g, b, a = src[x, y]
            value = (min(r, g, b) - _MASK_LOW) * 255 / span
            dst[x, y] = max(0, min(255, round(value * a / 255)))
    return mask


def _gradient(size: int) -> Image.Image:
    """Диагональный градиент знака: от левого верхнего угла к правому нижнему."""
    start = tuple(int(GRADIENT_START[i : i + 2], 16) for i in (1, 3, 5))
    end = tuple(int(GRADIENT_END[i : i + 2], 16) for i in (1, 3, 5))
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    span = 2 * (size - 1)
    for y in range(size):
        for x in range(size):
            t = (x + y) / span
            pixels[x, y] = tuple(
                round(start[i] + (end[i] - start[i]) * t) for i in range(3)
            )
    return image


def _maskable(source: Image.Image, size: int = 512) -> Image.Image:
    """PWA-иконка `purpose: maskable`: знак в safe zone ~80%, фон без альфы.

    Android обрезает maskable-иконку по своей форме (круг, «сквиркл»,
    суперэллипс) и оставляет видимой только центральную область. Поэтому
    знак занимает 80% холста, а фон залит тем же градиентом: при обрезке
    по любому контуру не остаётся прозрачных углов.
    """
    inner = round(size * 0.8)
    canvas = _gradient(size)
    mark = Image.new("RGB", (inner, inner), (255, 255, 255))
    offset = (size - inner) // 2
    canvas.paste(mark, (offset, offset), _mark_mask(_resize(source, inner)))
    return canvas


def _ellipse_path(cx: float, cy: float, rx: float, ry: float, angle: float, clockwise: bool) -> str:
    """Эллипс одним контуром: две дуги между концами большой оси.

    `clockwise` задаёт направление обхода — оно нужно, чтобы `fill-rule:
    nonzero` складывал кольца и центр в объединение, а не вычитал их.
    """
    a = math.radians(angle)
    dx, dy = rx * math.cos(a), rx * math.sin(a)
    sweep = 1 if clockwise else 0
    x0, y0 = cx + dx, cy + dy
    x1, y1 = cx - dx, cy - dy
    return (
        f"M{x0:g} {y0:g}"
        f"A{rx:g} {ry:g} {angle:g} 1 {sweep} {x1:g} {y1:g}"
        f"A{rx:g} {ry:g} {angle:g} 1 {sweep} {x0:g} {y0:g}Z"
    )


def _circle_path(cx: float, cy: float, r: float) -> str:
    return (
        f"M{cx + r:g} {cy:g}"
        f"A{r:g} {r:g} 0 1 1 {cx - r:g} {cy:g}"
        f"A{r:g} {r:g} 0 1 1 {cx + r:g} {cy:g}Z"
    )


def _mark_path() -> str:
    """Один path знака: три кольца (внешний и внутренний контур) и центр.

    Кольцо — это не «обводка»: контур внешнего эллипса обходится по
    часовой, внутреннего — против. При `nonzero` полоса между ними
    получает заливку, а середина кольца остаётся пустой.
    """
    half = ELLIPSE_STROKE / 2
    parts: list[str] = []
    for angle in ELLIPSE_ANGLES:
        parts.append(_ellipse_path(100, 100, ELLIPSE_RX + half, ELLIPSE_RY + half, angle, True))
        parts.append(_ellipse_path(100, 100, ELLIPSE_RX - half, ELLIPSE_RY - half, angle, False))
    parts.append(_circle_path(100, 100, CORE_R))
    return "".join(parts)


def _favicon_svg() -> str:
    """Цветная векторная иконка: резкая на Retina, вес — единицы килобайт."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" width="{VIEWBOX}" height="{VIEWBOX}" role="img" aria-label="{APP_NAME}">
  <title>{APP_NAME}</title>
  <defs>
    <linearGradient id="brand" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{GRADIENT_START}"/>
      <stop offset="1" stop-color="{GRADIENT_END}"/>
    </linearGradient>
  </defs>
  <circle cx="100" cy="100" r="{CIRCLE_R}" fill="url(#brand)"/>
  <path fill="#FFFFFF" fill-rule="nonzero" d="{_mark_path()}"/>
</svg>
"""


def _pinned_tab_svg() -> str:
    """Монохромный силуэт для `rel="mask-icon"` (Safari, закреплённые вкладки).

    Safari берёт из файла только форму и красит её в `color` из разметки,
    поэтому фон-круг здесь не рисуется: он превратил бы иконку в сплошную
    заливку. Остаётся знак — тот же path, что и в `favicon.svg`.
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" width="{VIEWBOX}" height="{VIEWBOX}">
  <path fill="currentColor" fill-rule="nonzero" d="{_mark_path()}"/>
</svg>
"""


def _manifest() -> str:
    """PWA-манифест: имя, цвета и иконки для установки на домашний экран.

    `src` — абсолютные пути `/static/favicons/...`: манифест отдаётся с
    того же хоста, а относительные пути от `/static/favicons/` читались бы
    как `/static/...` только по совпадению — лучше не полагаться.
    """
    manifest = {
        "name": APP_NAME,
        "short_name": APP_NAME,
        "description": APP_DESCRIPTION,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#FFFFFF",
        "theme_color": THEME_COLOR,
        "icons": [
            {
                "src": "/static/favicons/android-chrome-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/favicons/android-chrome-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/favicons/android-chrome-maskable-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def build(output: Path = OUTPUT) -> list[Path]:
    """Пишет набор в `output` и возвращает список созданных файлов."""
    source = _load_source()
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def save_png(name: str, image: Image.Image) -> None:
        path = output / name
        image.save(path, format="PNG", optimize=True)
        written.append(path)

    # Мультиразмерный ICO: 16 — вкладка, 32 — панель закладок и Windows,
    # 48 — ярлык на рабочем столе. Pillow уменьшает из исходника сам.
    ico = output / "favicon.ico"
    source.save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    written.append(ico)

    save_png("favicon-16x16.png", _resize(source, 16))
    save_png("favicon-32x32.png", _resize(source, 32))
    save_png("apple-touch-icon.png", _on_white(_resize(source, 180)))
    save_png("android-chrome-192x192.png", _resize(source, 192))
    save_png("android-chrome-512x512.png", _resize(source, 512))
    save_png("android-chrome-maskable-512x512.png", _maskable(source, 512))

    for name, content in (
        ("favicon.svg", _favicon_svg()),
        ("safari-pinned-tab.svg", _pinned_tab_svg()),
        ("site.webmanifest", _manifest()),
    ):
        path = output / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written


def main() -> int:
    written = build()
    total = sum(path.stat().st_size for path in written)
    print(f"файлов: {len(written)}; app/static/favicons: {total / 1024:.1f} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
