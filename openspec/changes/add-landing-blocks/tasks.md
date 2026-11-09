# Tasks

## 1. Набор блоков

- [x] 1.1 `app/landing/services/blocks.py`: `landing_blocks(cta_url)` с
  секциями лендинга (`header`, `hero`, `about`, `price`, `contacts`,
  `footer`), базовыми блоками (`heading`, `text`, `image`, `button`,
  `divider`) и раскладкой (`column2`, `column3`).
- [x] 1.2 Категории `landing`, `basic`, `layout`; CTA ведёт на
  `/s/<tutor_id>`.
- [x] 1.3 Блок «Изображение» без `src=""`, с маркером
  `data-landing-image`.

## 2. Вьюха и шаблон редактора

- [x] 2.1 `views/editor.py`: передать `blocks` в контекст шаблона,
  адрес CTA — из `public_page_url(tutor.id)`.
- [x] 2.2 `templates/landing/editor.html`: JSON `landing-blocks`,
  `blockManager: { appendOnClick: true, blocks }`.
- [x] 2.3 Обработчик `component:add`: снять маркер `data-landing-image`
  и открыть Asset Manager с `types: ['image']`; выбранный ассет пишется
  в `src`.

## 3. Локаль

- [x] 3.1 `i18n-ru.js`: подписи новых блоков и категория
  «Блоки лендинга».

## 4. Тесты

- [x] 4.1 `tests/test_landing_blocks.py`: состав и категории набора,
  CTA на страницу репетитора, блок изображения, отсутствие отступов в
  HTML блоков.
- [x] 4.2 Встраивание в редактор: JSON блоков, `appendOnClick`,
  обработчик выбора картинки, CTA владельца.
- [x] 4.3 Подписи каждого блока и категории в русской локали.

## 5. Документация

- [x] 5.1 `README.md`: блоки и вставка изображений в разделе «Лендинг».
- [x] 5.2 `CHANGELOG.md`: запись в `[Unreleased] → Добавлено`.
- [x] 5.3 Спека `landing-page`: требования набора блоков и вставки
  изображений; delta в `openspec/changes/add-landing-blocks/`.

## 6. Проверка

- [x] 6.1 `uv run pytest tests/test_landing_*.py -q`.
- [x] 6.2 `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/`.
- [x] 6.3 Ручная проверка в браузере: панель блоков, вставка секций,
  вставка изображения и сохранение.

## 7. Исправления по итогам ручной проверки

- [x] 7.1 Маркер `data-landing-image` проверяется по наличию ключа, а не
  по истинности значения: атрибут без значения приходит пустой строкой,
  и прежняя проверка не открывала Asset Manager.
- [x] 7.2 Отмена выбора в Asset Manager удаляет пустой `<img>`: иначе
  служебная data-URI-заглушка GrapesJS попадала в сохранённый черновик.
- [x] 7.3 Тесты на оба случая в `tests/test_landing_blocks.py`.

