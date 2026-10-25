/**
 * OpenTutorCRM — баннер-напоминание о не отмеченных уроках (Alpine.data
 * `noticeBanner`).
 *
 * Закрытие плашки — клиентское (design D2 change'а unmarked-lessons):
 * в localStorage хранятся ключи уже закрытых состояний. Ключ — состав
 * не отмеченных уроков в плашке, его рендерит сервер (data-атрибут не
 * нужен: ключ приходит аргументом фабрики). Пока состав не меняется,
 * плашка остаётся скрытой; появился новый не отмеченный урок — ключ
 * другой и напоминание возвращается. Урок отметили — сервер не рендерит
 * баннер вовсе.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "opentutorcrm:notices-dismissed";
  /* История закрытых ключей ограничена: ключей без автозавершения (cron
     выключен) могло бы накапливаться неограниченно много. */
  var STORAGE_LIMIT = 50;

  document.addEventListener("alpine:init", function () {
    Alpine.data("noticeBanner", function (key) {
      return {
        key: key || "",
        open: true,

        init: function () {
          try {
            var dismissed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
            this.open = dismissed.indexOf(this.key) === -1;
          } catch (e) {
            /* localStorage недоступен (приватный режим) — плашка видна. */
          }
        },

        close: function () {
          this.open = false;
          try {
            var dismissed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
            if (dismissed.indexOf(this.key) === -1) {
              dismissed.push(this.key);
              localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify(dismissed.slice(-STORAGE_LIMIT))
              );
            }
          } catch (e) {
            /* noop */
          }
        },
      };
    });
  });
})();
