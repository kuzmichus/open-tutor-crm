/**
 * OpenTutorCRM — список выбора человека из готового JSON (Alpine.js).
 *
 * Один виджет на два поля: «Добавить контакт» в форме ученика и
 * «Добавить ученика» в форме группы. Сервер отдаёт варианты в
 * `data-options` (`[{id, ...}, ...]`), виджет открывает список сразу по
 * клику (без ожидания ввода), фильтрует его по вводу и отдаёт выбранный
 * вариант домену через `choose`: ученики добавляют строку контакта, группы —
 * участника состава. Подписи и действия домены рисуют сами — разметка
 * списка общая (`app/templates/_person_picker.html`).
 *
 * Подключается до `students.js`, `groups.js` и `alpine.min.js`: фабрики
 * страниц собирают состояние через `createPersonPicker`.
 */
(function () {
  "use strict";

  /* Сколько вариантов показывать за раз: учеников и контактов у репетитора
     десятки, ограничение держит выпадающий список компактным. Остальное —
     поисковой строкой, в конце списка видно, сколько вариантов не показано. */
  var DEFAULT_LIMIT = 8;

  /* Телефоны и классы сравниваем по цифрам, когда в запросе их набралось
     достаточно: иначе «555» не нашло бы «+7 555 111-22-33». */
  var DIGITS_IN_QUERY = 3;

  function parseJson(value, fallback) {
    try {
      return JSON.parse(value || "");
    } catch (e) {
      return fallback;
    }
  }

  function digitsOf(value) {
    return String(value).replace(/\D/g, "");
  }

  /* Совпадение варианта с запросом: подстрока без учёта регистра по
     выбранным полям (имя, класс, телефон, email) либо по цифрам. */
  function itemMatches(item, query, fields) {
    var text = query.toLowerCase();
    var digits = digitsOf(query);
    var keys = fields && fields.length ? fields : Object.keys(item);

    for (var i = 0; i < keys.length; i++) {
      var value = item[keys[i]];
      if (value === null || value === undefined) continue;
      var raw = String(value);
      if (raw.toLowerCase().indexOf(text) !== -1) return true;
      if (digits.length >= DIGITS_IN_QUERY && digitsOf(raw).indexOf(digits) !== -1) {
        return true;
      }
    }
    return false;
  }

  /* Состояние списка выбора. Конфиг:
     - limit — сколько вариантов показывать (по умолчанию 8);
     - searchFields — поля варианта для поиска (по умолчанию все строковые);
     - exclude — функция без аргументов, возвращает `{id: true}` уже
       выбранных: они не предлагаются повторно;
     - choose — что сделать с выбранным вариантом (строка/участник);
     - onEnter — Enter без совпадений (например, «создать новый контакт»). */
  window.createPersonPicker = function (config) {
    config = config || {};
    var limit = config.limit || DEFAULT_LIMIT;
    var fields = config.searchFields || null;

    return {
      /* Список открыт. Открывается сразу по клику/фокусу — варианты видны,
         не дожидаясь начала ввода. Имя `listOpen`, а не `open`: виджет может
         жить внутри компонента модалки, у которой `open` — видимость окна. */
      listOpen: false,
      query: "",
      active: -1,
      all: [],

      /* `source` — элемент с `data-options`; по умолчанию корень компонента
         (поле контакта) либо первый такой элемент внутри него (форма группы,
         где поле живёт в общем компоненте модалки). */
      initPicker: function (source) {
        var root = source || this.$root;
        if (!root || !root.dataset || !root.dataset.options) {
          root = (this.$root && this.$root.querySelector("[data-options]")) || root;
        }
        this.all = parseJson(root && root.dataset ? root.dataset.options : "[]", []);
        if (!Array.isArray(this.all)) this.all = [];
      },

      /* Уже выбранные исключаются: повторный выбор создал бы дубль. */
      get matches() {
        var query = this.query.trim();
        var excluded = config.exclude ? config.exclude.call(this) : null;
        var list = this.all;

        if (excluded) {
          list = list.filter(function (item) {
            return !excluded[item.id];
          });
        }
        if (!query) return list;
        return list.filter(function (item) {
          return itemMatches(item, query, fields);
        });
      },

      get shown() {
        return this.matches.slice(0, limit);
      },

      get hiddenCount() {
        return Math.max(this.matches.length - limit, 0);
      },

      /* Лимит участников группы. У поля контактов лимита нет — домен
         переопределяет геттер при сборке компонента (см. groups.js). */
      get isFull() {
        return false;
      },

      openList: function () {
        this.listOpen = true;
      },

      closeList: function () {
        this.listOpen = false;
        this.active = -1;
      },

      onInput: function (value) {
        this.query = value;
        this.listOpen = true;
        this.active = -1;
      },

      choose: function (item) {
        if (!item) return;
        if (config.choose) config.choose.call(this, item);
        this.reset();
      },

      reset: function () {
        this.query = "";
        this.active = -1;
        this.listOpen = false;
        if (this.$refs.input) this.$refs.input.value = "";
      },

      onKeydown: function (event) {
        var key = event.key;

        if (key === "Escape") {
          // Escape сначала закрывает список, а не модалку целиком.
          if (this.listOpen) {
            event.preventDefault();
            event.stopPropagation();
            this.closeList();
          }
          return;
        }

        if (key === "ArrowDown" || key === "ArrowUp") {
          event.preventDefault();
          if (!this.listOpen) {
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
          // Enter в текстовом поле отправил бы форму — гасим всегда.
          event.preventDefault();
          var hasQuery = this.query.trim() !== "";
          if (hasQuery && this.listOpen && this.matches.length) {
            this.choose(
              this.active >= 0 && this.active < this.shown.length
                ? this.shown[this.active]
                : this.matches[0]
            );
            return;
          }
          if (config.onEnter) config.onEnter.call(this);
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
  };

  /* Дополняет состояние списка методами домена. Свойства копируются вместе
     с геттерами: Alpine должен видеть `isFull`/`hiddenCount` как свойства,
     а не как значения, посчитанные один раз при сборке компонента. */
  window.mergePersonPicker = function (picker, extra) {
    Object.keys(extra).forEach(function (key) {
      Object.defineProperty(
        picker,
        key,
        Object.getOwnPropertyDescriptor(extra, key)
      );
    });
    return picker;
  };
})();
