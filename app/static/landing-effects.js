/**
 * Клиентские эффекты опубликованного лендинга: тема, проявление секций
 * при скролле, доступность аккордеона FAQ.
 *
 * Тег этого скрипта — гарантия сервера (`app/landing/services/draft_render.py`):
 * редактор GrapesJS вырезает скрипты из тела, и при сохранении тег
 * возвращается, как и у `/static/landing-auth.js`. Без `defer`: скрипт
 * обязан поставить тему на `<html>` до первой отрисовки, иначе тёмная
 * тема мигает светлой. Скрипт — no-op без разметки под него: секция,
 * удалённая из страницы в редакторе, ничего от него не ждёт.
 */
(function () {
    "use strict";

    var root = document.documentElement;
    var THEME_KEY = "landing-theme";

    function storedTheme() {
        // localStorage недоступен в приватных режимах: тема просто не
        // сохраняется, страница не должна падать.
        try {
            return localStorage.getItem(THEME_KEY);
        } catch (error) {
            return null;
        }
    }

    function saveTheme(value) {
        try {
            localStorage.setItem(THEME_KEY, value);
        } catch (error) {
            /* Нет доступа к хранилищу — выбор живёт до перезагрузки. */
        }
    }

    // Тема. Значение всегда материализуется на `<html>`, даже когда выбор
    // совпадает с системной: CSS переключателя (какая иконка видна) и
    // `color-scheme` читают только `data-theme`. Сохранённый выбор сильнее
    // системной темы и перезаписывает её; сам по себе выбор не пишется —
    // пока пользователь не нажал кнопку, тема следует за системой.
    var theme = storedTheme();
    if (theme !== "light" && theme !== "dark") {
        theme =
            window.matchMedia &&
            window.matchMedia("(prefers-color-scheme: dark)").matches
                ? "dark"
                : "light";
    }
    root.setAttribute("data-theme", theme);

    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-theme-toggle]");
        if (!button) {
            return;
        }
        theme = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", theme);
        saveTheme(theme);
    });

    // Проявление секций. Скрытое состояние включается только классом
    // `reveal-init` на `<html>`: без скрипта (он не загрузился) или без
    // IntersectionObserver страница остаётся полностью видимой. Скрипт
    // стоит в конце `<body>` без defer, поэтому класс ставится до первой
    // отрисовки и «прыжка» скрытых секций не видно.
    var reducedMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reducedMotion && "IntersectionObserver" in window) {
        root.classList.add("reveal-init");
        var observer = new IntersectionObserver(
            function (entries) {
                for (var i = 0; i < entries.length; i += 1) {
                    if (entries[i].isIntersecting) {
                        entries[i].target.classList.add("is-visible");
                        observer.unobserve(entries[i].target);
                    }
                }
            },
            { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
        );
        var sections = document.querySelectorAll("[data-reveal]");
        for (var j = 0; j < sections.length; j += 1) {
            observer.observe(sections[j]);
        }
    }

    // FAQ-аккордеон. `<details>`/`<summary>` доступны с клавиатуры сами по
    // себе; `aria-expanded` синхронизируется вручную, потому что скринридер
    // читает кнопку (`summary`), а не состояние родительского `details`.
    // Событие `toggle` приходит на `details`, не на `summary`.
    var disclosures = document.querySelectorAll("details");
    function syncExpanded(details) {
        var summary = details.querySelector("summary");
        if (summary) {
            summary.setAttribute(
                "aria-expanded",
                details.open ? "true" : "false"
            );
        }
    }
    for (var k = 0; k < disclosures.length; k += 1) {
        syncExpanded(disclosures[k]);
        disclosures[k].addEventListener("toggle", function () {
            syncExpanded(this);
        });
    }
})();
