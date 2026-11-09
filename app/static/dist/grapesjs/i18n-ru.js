/*
 * Русская локаль GrapesJS для редактора лендинга.
 *
 * GrapesJS 0.23.9 (BSD-3-Clause, см. LICENSE рядом). Структура ключей
 * повторяет en-набор дистрибутива (`locale/en.js` пакета grapesjs@0.23.9):
 * ключи не переименовываются и не сокращаются, поэтому незаведённые
 * значения молча берутся из английского через `localeFallback: 'en'`.
 *
 * Файл — обычный браузерный скрипт (без import/export): подключается тегом
 * <script> после grapes.min.js и определяет window.grapesjsI18nRu.
 * В init передаётся:
 *
 *   i18n: {
 *     locale: 'ru',
 *     localeFallback: 'en',
 *     detectLocale: false,
 *     messages: { ru: window.grapesjsI18nRu },
 *   }
 *
 * `detectLocale: false` обязателен: иначе GrapesJS подменит локаль языком
 * браузера и английский интерфейс вернётся.
 */
(function (window) {
    'use strict';

    var traitInputAttr = {
        placeholder: 'Например, текст здесь',
    };

    window.grapesjsI18nRu = {
        assetManager: {
            addButton: 'Добавить изображение',
            inputPlh: 'http://путь/к/изображению.jpg',
            modalTitle: 'Выбрать изображение',
            uploadTitle: 'Перетащите файлы сюда или нажмите, чтобы загрузить',
        },

        // Ядро GrapesJS не содержит блоков: панель наполняет приложение
        // (`app/landing/services/blocks.py`), а подписи берутся отсюда по id
        // блока. Стандартные id (column2, text, image, …) сохранены — так
        // они переведутся, даже если блоки добавят плагином.
        blockManager: {
            labels: {
                // Секции лендинга в дизайне CRM — в порядке страницы.
                header: 'Шапка',
                hero: 'Обложка',
                price: 'Услуги и цены',
                about: 'Обо мне',
                education: 'Образование',
                reviews: 'Результаты и отзывы',
                steps: 'Как проходит обучение',
                faq: 'Частые вопросы',
                signup: 'Запись на пробное',
                contacts: 'Контакты',
                footer: 'Подвал',
                // Простые элементы.
                heading: 'Заголовок',
                text: 'Текст',
                image: 'Изображение',
                button: 'Кнопка',
                divider: 'Разделитель',
                // Раскладка.
                column1: '1 колонка',
                column2: '2 колонки',
                column3: '3 колонки',
                'column3-7': 'Колонки 3/7',
                link: 'Ссылка',
                video: 'Видео',
                map: 'Карта',
            },
            categories: {
                landing: 'Блоки лендинга',
                basic: 'Базовые',
                layout: 'Макет',
            },
        },

        canvas: {
            frameTitle: 'Холст редактора',
        },

        domComponents: {
            names: {
                '': 'Блок',
                wrapper: 'Тело',
                text: 'Текст',
                comment: 'Комментарий',
                image: 'Изображение',
                video: 'Видео',
                label: 'Метка',
                link: 'Ссылка',
                map: 'Карта',
                tfoot: 'Подвал таблицы',
                tbody: 'Тело таблицы',
                thead: 'Заголовок таблицы',
                table: 'Таблица',
                row: 'Строка таблицы',
                cell: 'Ячейка таблицы',
            },
        },

        deviceManager: {
            device: 'Устройство',
            devices: {
                desktop: 'Компьютер',
                tablet: 'Планшет',
                mobileLandscape: 'Телефон горизонтально',
                mobilePortrait: 'Телефон вертикально',
            },
        },

        panels: {
            buttons: {
                titles: {
                    preview: 'Предпросмотр',
                    fullscreen: 'Полный экран',
                    'sw-visibility': 'Показать компоненты',
                    'export-template': 'Показать код',
                    'open-sm': 'Открыть диспетчер стилей',
                    'open-tm': 'Настройки',
                    'open-layers': 'Открыть диспетчер слоёв',
                    'open-blocks': 'Открыть блоки',
                },
            },
        },

        selectorManager: {
            label: 'Классы',
            selected: 'Выбрано',
            emptyState: '- Состояние -',
            states: {
                hover: 'Наведение',
                active: 'Нажатие',
                'nth-of-type(2n)': 'Чётные/нечётные',
            },
        },

        styleManager: {
            empty: 'Выберите элемент, чтобы открыть диспетчер стилей',
            layer: 'Слой',
            fileButton: 'Изображения',
            sectors: {
                general: 'Общее',
                layout: 'Макет',
                typography: 'Текст',
                decorations: 'Оформление',
                extra: 'Дополнительно',
                flex: 'Flex',
                dimension: 'Размеры',
            },
            // Подписи составных свойств (Composite/Stack).
            properties: {
                // Основные свойства секций Style Manager. Без них GrapesJS
                // показывает английские подписи, собранные из имени свойства.
                display: 'Отображение',
                float: 'Обтекание',
                position: 'Позиционирование',
                top: 'Сверху',
                right: 'Справа',
                left: 'Слева',
                bottom: 'Снизу',
                'flex-direction': 'Направление',
                'flex-wrap': 'Перенос',
                'justify-content': 'По главной оси',
                'align-items': 'По поперечной',
                'align-content': 'Распределение',
                order: 'Порядок',
                'flex-basis': 'Базовый размер',
                'flex-grow': 'Рост',
                'flex-shrink': 'Сжатие',
                'align-self': 'Своё выравнивание',
                width: 'Ширина',
                height: 'Высота',
                'max-width': 'Макс. ширина',
                'min-height': 'Мин. высота',
                margin: 'Отступы снаружи',
                padding: 'Отступы внутри',
                'font-family': 'Шрифт',
                'font-size': 'Размер шрифта',
                'font-weight': 'Насыщенность',
                'letter-spacing': 'Интервал букв',
                color: 'Цвет',
                'line-height': 'Высота строки',
                'text-align': 'Выравнивание текста',
                'text-shadow': 'Тень текста',
                'background-color': 'Цвет фона',
                'border-radius': 'Скругление',
                border: 'Рамка',
                'box-shadow': 'Тень блока',
                background: 'Фон',
                opacity: 'Прозрачность',
                transition: 'Переходы',
                transform: 'Трансформация',
                'text-shadow-h': 'X',
                'text-shadow-v': 'Y',
                'text-shadow-blur': 'Размытие',
                'text-shadow-color': 'Цвет',
                'box-shadow-h': 'X',
                'box-shadow-v': 'Y',
                'box-shadow-blur': 'Размытие',
                'box-shadow-spread': 'Растяжение',
                'box-shadow-color': 'Цвет',
                'box-shadow-type': 'Тип',
                'margin-top-sub': 'Сверху',
                'margin-right-sub': 'Справа',
                'margin-bottom-sub': 'Снизу',
                'margin-left-sub': 'Слева',
                'padding-top-sub': 'Сверху',
                'padding-right-sub': 'Справа',
                'padding-bottom-sub': 'Снизу',
                'padding-left-sub': 'Слева',
                'border-width-sub': 'Толщина',
                'border-style-sub': 'Стиль',
                'border-color-sub': 'Цвет',
                'border-top-left-radius-sub': 'Сверху слева',
                'border-top-right-radius-sub': 'Сверху справа',
                'border-bottom-right-radius-sub': 'Снизу справа',
                'border-bottom-left-radius-sub': 'Снизу слева',
                'transform-rotate-x': 'Поворот X',
                'transform-rotate-y': 'Поворот Y',
                'transform-rotate-z': 'Поворот Z',
                'transform-scale-x': 'Масштаб X',
                'transform-scale-y': 'Масштаб Y',
                'transform-scale-z': 'Масштаб Z',
                'transition-property-sub': 'Свойство',
                'transition-duration-sub': 'Длительность',
                'transition-timing-function-sub': 'Функция времени',
                'background-image-sub': 'Изображение',
                'background-repeat-sub': 'Повтор',
                'background-position-sub': 'Позиция',
                'background-attachment-sub': 'Прикрепление',
                'background-size-sub': 'Размер',
            },
            // Значения выпадающих списков в свойствах стиля.
            options: {
                float: {
                    none: 'Нет',
                    left: 'Слева',
                    right: 'Справа',
                },
                display: {
                    block: 'Блок',
                    inline: 'Строчный',
                    'inline-block': 'Строчно-блочный',
                    flex: 'Flex',
                    none: 'Нет',
                },
                position: {
                    static: 'Обычное',
                    relative: 'Относительное',
                    absolute: 'Абсолютное',
                    fixed: 'Фиксированное',
                },
                'text-align': {
                    left: 'Слева',
                    center: 'По центру',
                    right: 'Справа',
                    justify: 'По ширине',
                },
                'font-weight': {
                    normal: 'Обычный',
                    bold: 'Жирный',
                },
                'background-repeat': {
                    repeat: 'Повторять',
                    'repeat-x': 'Повторять по X',
                    'repeat-y': 'Повторять по Y',
                    'no-repeat': 'Не повторять',
                },
                'background-size': {
                    auto: 'Авто',
                    cover: 'Заполнить',
                    contain: 'Вместить',
                },
            },
        },

        traitManager: {
            empty: 'Выберите элемент, чтобы открыть настройки компонента',
            label: 'Настройки компонента',
            categories: {},
            traits: {
                labels: {
                    id: 'Идентификатор',
                    alt: 'Альтернативный текст',
                    title: 'Подсказка',
                    href: 'Ссылка',
                    target: 'Открывать в',
                    name: 'Имя',
                    placeholder: 'Подсказка поля',
                    src: 'Источник',
                    type: 'Тип',
                },
                attributes: {
                    id: traitInputAttr,
                    alt: traitInputAttr,
                    title: traitInputAttr,
                    href: {
                        placeholder: 'Например, https://example.com',
                    },
                },
                options: {
                    target: {
                        false: 'Это окно',
                        _blank: 'Новое окно',
                    },
                },
            },
        },

        storageManager: {
            recover: 'Восстановить несохранённые изменения?',
        },

        codeManager: {
            title: 'Код',
            emptyState: 'Нет стилей для отображения',
            states: {
                html: 'HTML',
                css: 'CSS',
                js: 'JavaScript',
            },
        },
    };
})(window);
