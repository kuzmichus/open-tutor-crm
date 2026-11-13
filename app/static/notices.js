/**
 * OpenTutorCRM — плашки-предупреждения вверху кабинета (Alpine.data).
 *
 * Две фабрики:
 *
 * 1. `noticeBanner` — закрытие отдельной плашки (design D2 change'а
 *    unmarked-lessons). В localStorage хранятся ключи уже закрытых
 *    состояний. Ключ — состав не отмеченных уроков в плашке, его рендерит
 *    сервер (data-атрибут не нужен: ключ приходит аргументом фабрики).
 *    Пока состав не меняется, плашка остаётся скрытой; появился новый не
 *    отмеченный урок — ключ другой и напоминание возвращается. Урок
 *    отметили — сервер не рендерит баннер вовсе.
 *
 * 2. `noticeGroup` — сводная плашка «Требует внимания · N» для случая,
 *    когда предупреждений два и больше. Сервер о количестве плашек не
 *    знает: их подгружают независимые htmx-партиалы уже после отрисовки
 *    страницы, поэтому счётчик живёт на клиенте. Группа лишь считает
 *    видимые плашки и прячет их контейнер, а не сами плашки: так счётчик
 *    не ломается от собственной свёртки, а закрытая крестиком плашка
 *    (`x-show` ставит inline `display: none`) из счёта выпадает.
 *
 *    Видимость контейнера — не самостоятельное условие в шаблоне, а одно
 *    производное состояние `expanded` (шаблон спрашивает только его): при
 *    одной видимой плашке оно принудительно истинно — плашка показывается
 *    как есть, без сводки, — при двух и больше равно сохранённому
 *    предпочтению репетитора. Иначе после закрытия крестиком одной из двух
 *    плашек сводка исчезала бы, а контейнер оставался скрытым при
 *    `expanded = false`, и состояние компонента расходилось бы с экраном.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "opentutorcrm:notices-dismissed";
  /* История закрытых ключей ограничена: ключей без автозавершения (cron
     выключен) могло бы накапливаться неограниченно много. */
  var STORAGE_LIMIT = 50;

  /* Состояние сводки общее для всех страниц кабинета: репетитор раскрыл
     плашки на главной — они остаются раскрытыми и в других разделах,
     и после перезагрузки страницы. */
  var EXPANDED_KEY = "opentutorcrm:notices-expanded";

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

    Alpine.data("noticeGroup", function () {
      return {
        /* Выбор репетитора, сохранённый между страницами: раскрывать
           группу или держать её свёрнутой. */
        preference: false,
        /* Действительное состояние группы — единственное, что спрашивает
           шаблон. Отдельное поле, а не геттер: Alpine не отслеживает
           реактивность внутри геттеров, поэтому значение пересчитывается
           в recount() и toggle(). Начальное `true` совпадает с формулой
           при `count = 0` (плашек ещё нет — прятать нечего), пока
           `recount()` не подставит сохранённое предпочтение. */
        expanded: true,
        count: 0,
        observer: null,
        queued: false,

        init: function () {
          var self = this;
          try {
            self.preference = localStorage.getItem(EXPANDED_KEY) === "1";
          } catch (e) {
            /* localStorage недоступен (приватный режим) — сводка свёрнута. */
          }

          /* Первый пересчёт — после того, как Alpine разберёт вложенные
             `x-show`: к этому моменту у закрытых плашек уже стоит inline
             `display: none`, и они не попадут в счётчик. */
          this.$nextTick(function () {
            self.recount();
          });

          /* Плашки приходят htmx-свопами уже после отрисовки страницы, а
             крестик плашки меняет её видимость через `x-show`. Оба события
             видны как мутации поддерева: пересчитываем счётчик по ним. */
          this.observer = new MutationObserver(function () {
            self.scheduleRecount();
          });
          this.observer.observe(this.$el, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["style"],
          });
        },

        destroy: function () {
          if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
          }
        },

        /* Один пересчёт на пачку мутаций: своп партиала и инициализация
           Alpine на новых узлах дают сразу несколько записей. */
        scheduleRecount: function () {
          var self = this;
          if (this.queued) return;
          this.queued = true;
          queueMicrotask(function () {
            self.queued = false;
            self.recount();
          });
        },

        /* Считаем именно видимые плашки. Проверяем inline-стиль, а не
           `offsetParent`: собственное сворачивание группы прячет контейнер
           целиком, и по `offsetParent` все плашки разом «исчезли» бы из
           счёта.

           Здесь же синхронизируется `expanded` с тем, что видно на экране:
           одна плашка — группа раскрыта (по ТЗ она показывается как есть,
           без сводки), две и больше — действует сохранённое предпочтение.
           Без этого шаблон показывал бы оставшуюся плашку при
           `expanded = false`, и состояние компонента расходилось бы с
           экраном (замечание ревью №1). */
        recount: function () {
          var banners = this.$el.querySelectorAll(".notice-banner");
          var visible = 0;
          Array.prototype.forEach.call(banners, function (banner) {
            if (banner.style.display !== "none") visible += 1;
          });

          this.count = visible;
          this.expanded = visible < 2 || this.preference;
        },

        toggle: function () {
          /* Клик по «Показать/Свернуть» — явный выбор репетитора. */
          this.preference = !this.expanded;
          this.expanded = this.count < 2 || this.preference;
          try {
            localStorage.setItem(EXPANDED_KEY, this.preference ? "1" : "0");
          } catch (e) {
            /* noop */
          }
        },
      };
    });
  });
})();
