# GrapesJS (вендоринг)

Локальная копия GrapesJS для визуального редактора лендинга
(`/tutor/landing/editor`). CDN не используется: файлы отдаются приложением
с `/static/dist/grapesjs/...` через `RevalidatingStaticFiles`.

## Версия

| | |
|---|---|
| Версия | **0.23.9** (актуальный стабильный релиз на момент вендоринга) |
| Дата вендоринга | 2026-11-08 |
| Источник | npm-пакет `grapesjs@0.23.9` (`npm pack grapesjs@0.23.9`) |
| Лицензия | **BSD-3-Clause** (файл `LICENSE` из дистрибутива, текст не изменён) |

> В постановке задачи лицензия названа MIT, но в дистрибутиве GrapesJS
> 0.23.9 она BSD-3-Clause. Сохранён фактический файл лицензии без подмены
> текста; условие «сохранить лицензию в файлах» выполнено.

## Файлы

| Файл | Назначение | SHA-256 |
|---|---|---|
| `grapes.min.js` | ядро редактора (UMD-сборка) | `559073c5114f8eb0f8cb788e64b2a204492eb6ecd3b720e3539341f3b2f2d7b9` |
| `grapes.min.css` | стили интерфейса и канваса | `fb55e939b3349c280d68c0617dc87e56baa3eab55ea56a1855db9f5efcc7268d` |
| `LICENSE` | текст лицензии из npm-пакета | `1a7603ac82661e3ec4f0ad015e37f68ab62c85c725f07659b81760edb459ff8d` |
| `i18n-ru.js` | русский словарь UI (собственный файл проекта) | — |
| `font-awesome/css/font-awesome.min.css` | иконки панелей GrapesJS | `799aeb25cc0373fdee0e1b1db7ad6c2f6a0e058dfadaa3379689f583213190bd` |
| `font-awesome/fonts/fontawesome-webfont.woff2` | шрифт иконок (основной формат) | `2adefcbc041e7d18fcf2d417879dc5a09997aa64d675b7a3c4b6ce33da13f3fe` |
| `font-awesome/fonts/fontawesome-webfont.woff` | шрифт иконок (запасной формат) | `ba0c59deb5450f5cb41b3f93609ee2d0d995415877ddfa223e8a8a7533474f07` |

Файлы `grapes.min.js` и `grapes.min.css` скопированы из пакета байт в байт
и не пересобираются. Версия видна в баннере начала `grapes.min.js`:
`/*! grapesjs - 0.23.9 */`.

## Иконки Font Awesome

Панели GrapesJS подписаны классами Font Awesome 4.7.0 (`fa fa-cog`,
`fa fa-eye`, `fa fa-bars`, …), зашитыми в ядро. Ядро по умолчанию само
вставляет в `<head>` ссылку на
`https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css`,
поэтому в редакторе (`app/landing/templates/landing/editor.html`) стили
подключены локальным тегом `<link>`, а автоподключение отключено опцией
`cssIcons: ''`.

Файлы взяты из npm-пакета `font-awesome@4.7.0` без изменений; в наборе
оставлены только CSS и два шрифтовых формата (`woff2` и `woff`), потому что
современные браузеры не запрашивают `eot`/`ttf`/`svg` при наличии `woff2`.
Лицензии — в `font-awesome/LICENSE.md` (шрифт SIL OFL 1.1, CSS MIT).

## Телеметрия

GrapesJS 0.23.9 по умолчанию отправляет `POST` на
`https://app.grapesjs.com/api/gjs/telemetry/collect`. Приложение работает без
внешних запросов, поэтому в init передаётся `telemetry: false`; встраивать
патч в `grapes.min.js` не нужно.

## Русская локаль

`i18n-ru.js` — обычный браузерный скрипт (без `import`/`export`), который
определяет `window.grapesjsI18nRu`. Структура ключей повторяет
`locale/en.js` из дистрибутива, значения переведены на русский. Локаль
включается при инициализации:

```js
grapesjs.init({
  i18n: {
    locale: 'ru',
    localeFallback: 'en',
    messages: { ru: window.grapesjsI18nRu },
  },
});
```

Незаведённые ключи молча берутся из английского набора (`localeFallback`).

## Обновление

1. `npm pack grapesjs@<версия>` и распаковать tarball.
2. Скопировать `package/dist/grapes.min.js`, `package/dist/css/grapes.min.css`
   и `package/LICENSE`.
3. Сверить структуру ключей с `package/locale/en.js` и обновить
   `i18n-ru.js` (не сокращая ключи).
4. Обновить версию, дату и контрольные суммы в этой таблице и в шапке
   `i18n-ru.js`.
5. Вручную проверить редактор: русские панели, сохранение, предпросмотр.

CDN (`unpkg`, `jsdelivr`, `cdn.*`) подключать нельзя — только эти файлы.
