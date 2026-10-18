/**
 * OpenTutorCRM — селект с поиском (combobox) на Alpine.js.
 *
 * Универсальный виджет, не привязанный к домену. Разметка: корень `.combobox`
 * содержит текстовое поле (с `name` — его значение уходит в форму как есть)
 * и список вариантов в атрибуте `data-options` — JSON-массив
 * `[{value, label}, ...]`, который готовит сервер.
 *
 * Поведение: список открывается при фокусе, ввод фильтрует его по подстроке
 * (имя зоны и подпись смещения), выбор — кликом или Enter. Свободный ввод
 * разрешён: сервер принимает то, что напечатал пользователь, как и раньше,
 * когда поле было обычным текстовым.
 *
 * Подключается до `alpine.min.js`, как и `students.js`: подписка на
 * `alpine:init` должна сработать раньше, чем Alpine начнёт обход DOM.
 */
(function () {
  "use strict";

  /* Сколько вариантов показывать за раз: полный список — сотни строк
     (часовые зоны), DOM должен оставаться лёгким. Остальное — поисковой
     строкой, в конце списка видно, сколько вариантов не показано. */
  var OPTION_LIMIT = 60;

  document.addEventListener("alpine:init", function () {
    Alpine.data("combobox", function () {
      return {
        open: false,
        query: "",
        all: [],
        active: -1,

        init: function () {
          try {
            this.all = JSON.parse(this.$root.dataset.options || "[]");
          } catch (e) {
            this.all = [];
          }
          // Поле могло прийти с сохранённым значением (редактирование) —
          // берём его, чтобы фильтр и подсветка знали текущий выбор.
          var input = this.$root.querySelector("input");
          this.query = input ? input.value : "";
        },

        /* Фильтр по подстроке без учёта регистра: по имени зоны
           (`Europe/Moscow`) и по смещению (`+03`). */
        get matches() {
          var query = this.query.trim().toLowerCase();
          if (!query) return this.all;
          return this.all.filter(function (item) {
            return (
              item.value.toLowerCase().indexOf(query) !== -1 ||
              item.label.toLowerCase().indexOf(query) !== -1
            );
          });
        },

        get shown() {
          return this.matches.slice(0, OPTION_LIMIT);
        },

        get hiddenCount() {
          return Math.max(this.matches.length - OPTION_LIMIT, 0);
        },

        openList: function () {
          this.open = true;
        },

        closeList: function () {
          this.open = false;
          this.active = -1;
        },

        onInput: function (value) {
          this.query = value;
          this.open = true;
          this.active = -1;
        },

        choose: function (item) {
          this.query = item.value;
          // Значение пишем в поле напрямую: двусторонней привязки тут нет,
          // чтобы Alpine не перезаписывал value при каждой перерисовке и не
          // уводил курсор.
          if (this.$refs.input) this.$refs.input.value = item.value;
          this.closeList();
        },

        clear: function () {
          this.query = "";
          if (this.$refs.input) this.$refs.input.value = "";
          this.openList();
          if (this.$refs.input) this.$refs.input.focus();
        },

        onKeydown: function (event) {
          var key = event.key;

          if (key === "Escape") {
            // Escape сначала закрывает список, а не модалку целиком.
            if (this.open) {
              event.preventDefault();
              event.stopPropagation();
              this.closeList();
            }
            return;
          }

          if (key === "ArrowDown" || key === "ArrowUp") {
            event.preventDefault();
            if (!this.open) {
              this.openList();
              this.active = this.shown.length ? 0 : -1;
              this.scrollActiveIntoView();
              return;
            }
            if (!this.shown.length) return;
            var step = key === "ArrowDown" ? 1 : -1;
            var next = this.active + step;
            if (next < 0) next = this.shown.length - 1;
            if (next > this.shown.length - 1) next = 0;
            this.active = next;
            this.scrollActiveIntoView();
            return;
          }

          if (key === "Enter") {
            // Пока список открыт, Enter выбирает вариант, а не отправляет
            // форму.
            if (!this.open) return;
            event.preventDefault();
            if (this.active >= 0 && this.active < this.shown.length) {
              this.choose(this.shown[this.active]);
            } else {
              this.closeList();
            }
            return;
          }

          if (key === "Tab") this.closeList();
        },

        scrollActiveIntoView: function () {
          var list = this.$refs.list;
          if (!list) return;
          var item = list.querySelector('[aria-selected="true"]');
          if (item && item.scrollIntoView) item.scrollIntoView({ block: "nearest" });
        },
      };
    });
  });
})();
