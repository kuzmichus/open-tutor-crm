# Spec Delta

## ADDED Requirements

### Requirement: Набор блоков лендинга в редакторе

`GET /tutor/landing/editor` SHALL передавать в шаблон набор блоков
GrapesJS: готовые секции лендинга, базовые элементы и раскладку. Набор
SHALL описываться сервисом `app/landing/services/blocks.py` и вшиваться в
страницу JSON-ом в `<script type="application/json"
id="landing-blocks">`. Редактор SHALL инициализировать GrapesJS с
`blockManager: { appendOnClick: true, blocks: <набор> }`, чтобы блок
добавлялся кликом.

Набор SHALL содержать:

- категорию «Блоки лендинга»: `header`, `hero`, `about`, `price`,
  `contacts`, `footer`;
- категорию «Базовые»: `heading`, `text`, `image`, `button`, `divider`;
- категорию «Макет»: `column2`, `column3`.

Секции SHALL использовать классы и CSS-переменные шаблона по умолчанию
(`.header`, `.hero`, `.section`, `.price`, `.contact-link`, `.footer`),
чтобы вставленный блок выглядел как остальная страница без новых правил
CSS. Ссылки CTA в блоках `hero` и `button` SHALL вести на публичную
страницу записи текущего репетитора (`/s/<tutor_id>`), адрес SHALL
подставлять сервер.

Подписи блоков и категорий SHALL задаваться в русской локали
(`app/static/dist/grapesjs/i18n-ru.js`) по id блока и категории; каждый
блок и каждая категория из набора MUST иметь подпись.

#### Scenario: Панель блоков
- **WHEN** репетитор открывает `/tutor/landing/editor`
- **THEN** страница содержит JSON набора блоков и инициализирует GrapesJS с `blockManager.appendOnClick: true`

#### Scenario: Вставка секции
- **WHEN** репетитор кликает блок «Обложка»
- **THEN** в канвас добавляется секция `.hero` с именем, предметом, CTA и подсказкой

#### Scenario: CTA ведёт на страницу записи
- **WHEN** вставлен блок «Обложка» или «Кнопка»
- **THEN** `href` ссылки равен `/s/<tutor_id>` этого репетитора

#### Scenario: Русские подписи
- **WHEN** открыта панель блоков
- **THEN** блоки и категории подписаны по-русски, английских подписей нет

### Requirement: Вставка изображения в редакторе

Блок «Изображение» SHALL добавлять компонент `<img>` без пустого
`src=""` и с маркером `data-landing-image`. После вставки редактор SHALL
снимать маркер и открывать Asset Manager с `types: ['image']`; выбранный
ассет SHALL записываться в `src` компонента, а загруженный через Asset
Manager файл — появляться в канвасе по абсолютной ссылке
`/landing-assets/<uuid>.<ext>`. Маркер `data-landing-image` MUST NOT
попадать в сохранённый HTML.

Двойной клик по любой картинке в канвасе SHALL открывать Asset Manager
штатным поведением GrapesJS.

#### Scenario: Вставка картинки
- **WHEN** репетитор кликает блок «Изображение»
- **THEN** открывается Asset Manager, после выбора ассета картинка появляется в канвасе

#### Scenario: Загрузка новой картинки
- **WHEN** в открытом Asset Manager репетитор загружает файл
- **THEN** файл сохраняется через `POST /tutor/landing/assets` и становится доступен для выбора

#### Scenario: Сохранение страницы
- **WHEN** репетитор сохраняет черновик с вставленной картинкой
- **THEN** в `draft.html` попадает `<img>` с абсолютной ссылкой `/landing-assets/…` и без атрибута `data-landing-image`

#### Scenario: Замена картинки
- **WHEN** репетитор дважды кликает по картинке в канвасе
- **THEN** открывается Asset Manager и выбранный ассет заменяет `src`
