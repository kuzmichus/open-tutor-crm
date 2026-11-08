/**
 * Клиентская подмена кнопок входа на опубликованном лендинге.
 *
 * Серверная выдача страницы остаётся чистым статическим файлом: на
 * `DOMContentLoaded` скрипт спрашивает публичный `/auth/status` и для
 * каждого элемента `[data-auth]` с активной ролью меняет текст и ссылку.
 * Без элемента, без сессии или при сбое запроса — молчаливый no-op, и
 * остаются обычные ссылки на страницы входа.
 */
(function () {
    "use strict";

    var ROLES = {
        student: { text: "В кабинет", href: "/student" },
        parent: { text: "В кабинет", href: "/parent" },
        tutor: { text: "кабинет", href: "/tutor/" }
    };

    function applyStatus(status) {
        if (!status) {
            return;
        }

        var elements = document.querySelectorAll("[data-auth]");
        for (var i = 0; i < elements.length; i += 1) {
            var element = elements[i];
            var role = element.getAttribute("data-auth");
            var target = ROLES[role];

            if (target && status[role] === true) {
                element.textContent = target.text;
                element.setAttribute("href", target.href);
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        fetch("/auth/status", { credentials: "same-origin" })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(applyStatus)
            .catch(function () {});
    });
})();
