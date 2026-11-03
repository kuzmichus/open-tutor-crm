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

Про знак. Это «сквиркл» — квадрат 188×188 с непрерывными (не круговыми)
углами, залитый диагональным градиентом оранжевый → розовый. Внутри —
белое облако сообщения с розовым солнцем: кольцо, точка в центре и
восемь лучей с полукруглыми концами. Все числа ниже сняты с растра
(переход «белое/розовое — фон» по 50 % альфы) и подобраны минимизацией
расхождения с ним: для углов — кубическая кривая с параметрами `radius`
и `control`, ошибка аппроксимации < 0.3 px; для градиента — линейная
регрессия по фону, остаток ≤ 2 из 255 на канал.

Про SVG. Векторная версия — реконструкция по замерам исходника, а не
трассировка растра. Фон, облако и солнце описаны `path`: у сквиркла и
облака углы — кубические кривые с непрерывной кривизной, у лучей —
капсулы (отрезок с полукруглыми концами). Всё заливается `fill` с
`fill-rule: nonzero`, поэтому картинка не зависит от поддержки `stroke`
и одинаково масштабируется. Трассировка растра дала бы десятки
килобайт узлов и «дрожащие» края на 16 px.

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

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "vendor" / "favicon-source.png"
OUTPUT = ROOT / "app" / "static" / "favicons"

# Геометрия знака в системе координат исходника (200×200).
VIEWBOX = 200

# Фон: квадрат 5.7…194.3 с непрерывными углами. `radius` — вылет угла от
# края, `control` — смещение опорных точек кубической кривой (у круга было
# бы radius * 0.5523); 26.2/46 дают расхождение с растром < 0.3 px.
BACKGROUND = (5.7, 5.7, 188.6, 188.6)  # x, y, ширина, высота
BACKGROUND_RADIUS = 46.0
BACKGROUND_CONTROL = 26.2

# Облако сообщения: скруглённый прямоугольник плюс хвостик вниз-влево.
BUBBLE = (43.1, 43.1, 112.9, 88.0)  # x, y, ширина, высота
BUBBLE_RADIUS = 25.25
BUBBLE_CONTROL = 16.8
TAIL = ((74.2, 131.1), (93.4, 131.1), (68.0, 156.0))  # три вершины

# Солнце: кольцо (средняя линия + толщина), точка в центре и восемь лучей.
SUN_CENTER = (99.5, 87.0)
SUN_RING_RADIUS = 18.7
SUN_STROKE = 9.4
SUN_CORE_RADIUS = 6.2
SUN_RAY_INNER = 28.5  # центры полукруглых концов лучей
SUN_RAY_OUTER = 33.6
SUN_RAYS = 8

# Градиент фона: концы растяжки в углах знака (5.7, 5.7) и (194.3, 194.3).
GRADIENT_START = "#F97316"
GRADIENT_END = "#EC4899"

# Облако не чисто белое: с растра снимается (254, 248, 246).
BUBBLE_COLOR = "#FEF8F6"
# Солнце того же цвета, что и конец градиента.
ACCENT = "#EC4899"

APP_NAME = "OpenTutorCRM"
APP_DESCRIPTION = "CRM для репетитора: ученики, занятия, финансы и напоминания"

# `theme-color` — цвет верхней точки знака: адресная строка мобильного
# браузера выглядит продолжением иконки.
THEME_COLOR = "#F66838"


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


def _gradient(
    size: int, box: tuple[float, float, float, float] | None = None
) -> Image.Image:
    """Диагональный градиент знака: от левого верхнего угла к правому нижнему.

    `box` — прямоугольник исходника, на который ложится вся растяжка
    (по умолчанию — весь холст). За его пределами цвет продолжается
    крайним значением: так под знак подкладывается фон, когда прозрачные
    углы сквиркла надо чем-то залить.
    """
    x0, y0, x1, y1 = box or (0, 0, size - 1, size - 1)
    start = tuple(int(GRADIENT_START[i : i + 2], 16) for i in (1, 3, 5))
    end = tuple(int(GRADIENT_END[i : i + 2], 16) for i in (1, 3, 5))
    span = max(1e-6, (x1 - x0) + (y1 - y0))
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    scale = (size - 1) / (VIEWBOX - 1)
    for y in range(size):
        dy = y / scale - y0
        for x in range(size):
            t = ((x / scale - x0) + dy) / span
            t = min(1.0, max(0.0, t))
            pixels[x, y] = tuple(
                round(start[i] + (end[i] - start[i]) * t) for i in range(3)
            )
    return image


def _on_gradient(image: Image.Image) -> Image.Image:
    """Свести прозрачные углы на продолжение градиента.

    iOS не поддерживает прозрачность в `apple-touch-icon` и заливает её
    чёрным — иконка на домашнем экране становится чёрным квадратом.
    Заливать белым тоже нельзя: сквиркл скруглён, и в углах остались бы
    белые клинья. Поэтому прозрачное заменяется тем же градиентом:
    иконка получается «в обрез», а скругление iOS рисует сам.
    """
    x, y, w, h = BACKGROUND
    background = _gradient(image.size[0], box=(x, y, x + w, y + h))
    return Image.alpha_composite(background.convert("RGBA"), image).convert("RGB")


def _mark_mask(size: int) -> Image.Image:
    """Маска знака для maskable-иконки: облако с хвостиком, без фона.

    Нужна только для maskable: там знак переносится на градиент без
    прозрачности и в safe zone, а значит его надо отрезать от фона
    сквиркла. Контур строится по той же геометрии, что и SVG. Рисуем в
    четырёхкратном размере и уменьшаем LANCZOS: у `ImageDraw` нет
    сглаживания, иначе край облака на 512 px был бы зубчатым.
    """
    scale = 4
    big = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(big)
    k = size * scale / VIEWBOX
    x, y, w, h = BUBBLE
    draw.rounded_rectangle(
        (x * k, y * k, (x + w) * k, (y + h) * k),
        radius=BUBBLE_RADIUS * k,
        fill=255,
    )
    draw.polygon([(px * k, py * k) for px, py in TAIL], fill=255)
    return big.resize((size, size), Image.LANCZOS)


def _maskable(source: Image.Image, size: int = 512) -> Image.Image:
    """PWA-иконка `purpose: maskable`: знак в safe zone ~80%, фон без альфы.

    Android обрезает maskable-иконку по своей форме (круг, «сквиркл»,
    суперэллипс) и оставляет видимой только центральную область. Поэтому
    облако занимает 80% холста, а фон залит тем же градиентом: при обрезке
    по любому контуру не остаётся прозрачных углов.
    """
    inner = round(size * 0.8)
    canvas = _gradient(size)
    mark = _resize(source, inner)
    offset = (size - inner) // 2
    canvas.paste(mark, (offset, offset), _mark_mask(inner))
    return canvas


def _rounded_rect_path(
    x: float, y: float, w: float, h: float, radius: float, control: float
) -> str:
    """Скруглённый прямоугольник одним контуром с непрерывными углами.

    Угол — кубическая кривая от конца одной стороны до начала другой;
    `control` задаёт смещение опорных точек вдоль сторон. У круга оно
    равно radius * 0.5523, у знака — больше, поэтому угол «мягче»: именно
    так выглядит сквиркл в исходнике.
    """
    x1, y1 = x + w, y + h
    r, a = radius, control
    return (
        f"M{x + r:g} {y:g}"
        f"H{x1 - r:g}"
        f"C{x1 - r + a:g} {y:g} {x1:g} {y + r - a:g} {x1:g} {y + r:g}"
        f"V{y1 - r:g}"
        f"C{x1:g} {y1 - r + a:g} {x1 - r + a:g} {y1:g} {x1 - r:g} {y1:g}"
        f"H{x + r:g}"
        f"C{x + r - a:g} {y1:g} {x:g} {y1 - r + a:g} {x:g} {y1 - r:g}"
        f"V{y + r:g}"
        f"C{x:g} {y + r - a:g} {x + r - a:g} {y:g} {x + r:g} {y:g}Z"
    )


def _circle_path(cx: float, cy: float, r: float, clockwise: bool = True) -> str:
    """Окружность одним контуром из двух полудуг.

    `clockwise` задаёт направление обхода: при `fill-rule: nonzero`
    внешнее кольцо и внутреннее должны идти в разные стороны, иначе
    середина кольца останется залитой.
    """
    sweep = 1 if clockwise else 0
    return (
        f"M{cx + r:g} {cy:g}"
        f"A{r:g} {r:g} 0 1 {sweep} {cx - r:g} {cy:g}"
        f"A{r:g} {r:g} 0 1 {sweep} {cx + r:g} {cy:g}Z"
    )


def _capsule_path(
    x1: float, y1: float, x2: float, y2: float, radius: float
) -> str:
    """Капсула — луч солнца: отрезок с полукруглыми концами, одним контуром."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * radius, dx / length * radius
    return (
        f"M{x1 - nx:g} {y1 - ny:g}"
        f"L{x2 - nx:g} {y2 - ny:g}"
        f"A{radius:g} {radius:g} 0 0 1 {x2 + nx:g} {y2 + ny:g}"
        f"L{x1 + nx:g} {y1 + ny:g}"
        f"A{radius:g} {radius:g} 0 0 1 {x1 - nx:g} {y1 - ny:g}Z"
    )


def _background_path() -> str:
    return _rounded_rect_path(*BACKGROUND, BACKGROUND_RADIUS, BACKGROUND_CONTROL)


def _bubble_path() -> str:
    """Облако: скруглённый прямоугольник и хвостик отдельными подконтурами.

    Хвостик начинается на нижней кромке облака и заканчивается остриём
    ниже и левее — как в исходнике. Оба подконтура идут по часовой,
    поэтому при `nonzero` складываются в одну фигуру без шва.
    """
    parts = [_rounded_rect_path(*BUBBLE, BUBBLE_RADIUS, BUBBLE_CONTROL)]
    (ax, ay), (bx, by), (cx, cy) = TAIL
    parts.append(f"M{ax:g} {ay:g}L{bx:g} {by:g}L{cx:g} {cy:g}Z")
    return "".join(parts)


def _sun_path() -> str:
    """Солнце: кольцо (внешний и внутренний контур), точка и восемь лучей."""
    cx, cy = SUN_CENTER
    half = SUN_STROKE / 2
    parts = [
        _circle_path(cx, cy, SUN_RING_RADIUS + half),
        _circle_path(cx, cy, SUN_RING_RADIUS - half, clockwise=False),
        _circle_path(cx, cy, SUN_CORE_RADIUS),
    ]
    for index in range(SUN_RAYS):
        angle = 2 * math.pi * index / SUN_RAYS
        cos, sin = math.cos(angle), math.sin(angle)
        parts.append(
            _capsule_path(
                cx + SUN_RAY_INNER * cos,
                cy + SUN_RAY_INNER * sin,
                cx + SUN_RAY_OUTER * cos,
                cy + SUN_RAY_OUTER * sin,
                half,
            )
        )
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
  <path fill="url(#brand)" d="{_background_path()}"/>
  <path fill="{BUBBLE_COLOR}" fill-rule="nonzero" d="{_bubble_path()}"/>
  <path fill="{ACCENT}" fill-rule="nonzero" d="{_sun_path()}"/>
</svg>
"""


def _pinned_tab_svg() -> str:
    """Монохромный силуэт для `rel="mask-icon"` (Safari, закреплённые вкладки).

    Safari берёт из файла только форму и красит её в `color` из разметки,
    поэтому фона-сквиркла здесь нет: он превратил бы иконку в сплошную
    заливку. Остаётся солнце — тот же path, что и в `favicon.svg`: на
    вкладке в 16 px кольцо с лучами читается, а облако вокруг него — нет.
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" width="{VIEWBOX}" height="{VIEWBOX}">
  <path fill="currentColor" fill-rule="nonzero" d="{_sun_path()}"/>
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
    save_png("apple-touch-icon.png", _resize(_on_gradient(source), 180))
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