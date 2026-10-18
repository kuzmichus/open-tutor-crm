/**
 * OpenTutorCRM — состояние страниц учеников (Alpine.js).
 *
 * Здесь только клиентское состояние: вид сетка/список, панель фильтров,
 * модалка формы, строки контактов и поле добавления контакта. Серверной
 * логики нет — данные приходят готовым HTML, а сохранение идёт через htmx.
 *
 * Файл общий для страницы списка и карточки ученика: карточка тоже открывает
 * модалку редактирования в `#modal`, поэтому фабрики не могут жить в
 * `index.html` — иначе на карточке Alpine не найдёт `studentForm`.
 *
 * Подключается до `alpine.min.js`, поэтому подписка на `alpine:init`
 * срабатывает раньше, чем Alpine начнёт обход DOM.
 */
(function () {
  "use strict";

  var VIEW_KEY = "opentutorcrm:students-view";

  /* Формат телефона `+7 555 555-55-55` — то же правило, что на сервере
     (`app/student/services/phone.py`), иначе значение «переписывалось» бы
     при сохранении. Возвращает "" для пустого ввода; значения, не похожие на
     телефон (буквы, `доб. 12`, больше 11 цифр, чужой код страны), оставляет
     как ввели — молча терять часть ввода нельзя. */
  var PHONE_CHARS = /^[0-9+\-()\s.]+$/;

  function formatPhoneValue(value) {
    var raw = String(value || "").trim();
    if (!raw) return "";
    if (!PHONE_CHARS.test(raw)) return raw;

    var digits = raw.replace(/\D/g, "");
    // Пользователь ещё набирает префикс (`+`, `(`) — не подставляем `+7`
    // раньше времени, иначе при вводе `+7 ...` получится `+7 7 ...`.
    if (!digits) return raw;
    if (digits.length > 11) return raw;

    var national;
    if (digits[0] === "7" || digits[0] === "8") {
      national = digits.slice(1);
    } else if (digits.length === 11) {
      return raw; // чужой код страны — формат не навязываем
    } else {
      national = digits;
    }

    var result = "+7";
    if (national.slice(0, 3)) result += " " + national.slice(0, 3);
    if (national.slice(3, 6)) result += " " + national.slice(3, 6);
    if (national.slice(6, 8)) result += "-" + national.slice(6, 8);
    if (national.slice(8, 10)) result += "-" + national.slice(8, 10);
    return result;
  }

  /* Похоже ли значение на телефон, который можно переформатировать.
     Если нет (буквы, `доб. 12`, больше 11 цифр, чужой код страны) — поле
     не трогаем вообще: ни значение, ни позицию курсора. */
  function isFormattablePhone(raw) {
    if (!PHONE_CHARS.test(raw)) return false;
    var digits = raw.replace(/\D/g, "");
    if (!digits) return false;
    if (digits.length > 11) return false;
    if (digits.length === 11 && digits[0] !== "7" && digits[0] !== "8") return false;
    return true;
  }

  /* Форматирует поле на месте, сохраняя позицию курсора по числу цифр:
     иначе при наборе в середине номера курсор прыгал бы в конец. */
  function formatPhoneInput(input) {
    var raw = input.value;
    if (!isFormattablePhone(raw)) return;
    // Пробел по краям — признак незаконченного ввода (например, пользователь
    // начал печатать «доб. 12»). Переформатирование срезало бы его и увело
    // курсор в середину строки.
    if (raw !== raw.trim()) return;

    var caret = input.selectionStart === null ? raw.length : input.selectionStart;
    var digitsBeforeCaret = raw.slice(0, caret).replace(/\D/g, "").length;
    var allDigits = raw.replace(/\D/g, "");
    var countryConsumed = allDigits.length > 0 && "78".indexOf(allDigits[0]) !== -1;
    var nationalBefore = Math.max(digitsBeforeCaret - (countryConsumed ? 1 : 0), 0);

    var formatted = formatPhoneValue(raw);
    if (formatted === raw) return;
    input.value = formatted;

    // Курсор — сразу после того же количества цифр номера (после "+7").
    if (nationalBefore === 0) {
      input.setSelectionRange(2, 2);
      return;
    }
    var seen = 0;
    for (var i = 2; i < formatted.length; i++) {
      if (/\d/.test(formatted[i])) {
        seen += 1;
        if (seen === nationalBefore) {
          input.setSelectionRange(i + 1, i + 1);
          return;
        }
      }
    }
    input.setSelectionRange(formatted.length, formatted.length);
  }

  /* Делегированный обработчик: поля с `data-phone-mask` форматируются по мере
     ввода, включая строки контактов, добавленные Alpine после загрузки
     страницы. Делегирование надёжнее, чем `@input` на каждом поле: htmx
     вставляет форму заново, и привязки пришлось бы навешивать повторно.

     Тот же обработчик синхронизирует строку-сводку контакта (ФИО · роль ·
     телефон): он вызывается после маски, поэтому в сводку попадает уже
     отформатированный телефон. */
  function syncContactSummary(input) {
    var field = input.getAttribute && input.getAttribute("data-field");
    if (!field || field === "contact_id") return;
    var row = input.closest && input.closest("[data-contact-row]");
    if (!row) return;
    var summary = row.querySelector('[data-summary="' + field + '"]');
    if (summary) summary.textContent = input.value.trim();
  }

  document.addEventListener("input", function (event) {
    var input = event.target;
    if (!input || !input.matches) return;
    if (input.matches("[data-phone-mask]")) {
      formatPhoneInput(input);
    }
    syncContactSummary(input);
  });

  /* Добавляет строку контакта из инертного шаблона `#contact-row-template`
     с очередным индексом полей. Индексы не переиспользуются, чтобы имена
     полей оставались уникальными; полностью пустая строка сервером
     пропускается при сохранении.

     `fields` — значения полей нового контакта, ключи совпадают с
     `data-field` (и с `data-summary` для строки-сводки). Строка создаётся
     раскрытой (см. `open=true` в шаблоне) и получает фокус в поле ФИО. */
  function appendContactRow(fields) {
    var template = document.getElementById("contact-row-template");
    var rows = document.querySelector(".contact-rows");
    if (!template || !rows) return null;
    var counter = document.querySelector('input[name="contact_rows"]');
    var index = parseInt((counter && counter.value) || "0", 10);
    var holder = document.createElement("div");
    holder.innerHTML = template.innerHTML.split("__index__").join(String(index));
    var row = holder.firstElementChild;
    if (!row) return null;

    // Заглушка «контактов пока нет» уходит вместе с первым добавлением.
    var empty = rows.querySelector(".contact-rows__empty");
    if (empty) empty.remove();

    Object.keys(fields || {}).forEach(function (key) {
      var input = row.querySelector('[data-field="' + key + '"]');
      if (input) input.value = fields[key] || "";
      var summary = row.querySelector('[data-summary="' + key + '"]');
      if (summary) summary.textContent = (fields[key] || "").trim();
    });

    rows.appendChild(row);
    if (counter) counter.value = String(index + 1);

    // Иконки новой строки (стрелка, корзина) отрисовываются повторно.
    if (typeof window.renderIcons === "function") window.renderIcons();

    var name = row.querySelector('[data-field="full_name"]');
    if (name) {
      name.focus();
      name.setSelectionRange(name.value.length, name.value.length);
      row.scrollIntoView({ block: "nearest" });
    }
    return row;
  }

  document.addEventListener("alpine:init", function () {
    /* Вид списка: выбор хранится в localStorage и переживает перезагрузку. */
    Alpine.data("studentsPage", function () {
      var saved = "grid";
      try {
        saved = localStorage.getItem(VIEW_KEY) || "grid";
      } catch (e) {
        /* приватный режим: остаётся вид по умолчанию */
      }
      return {
        view: saved,
        filtersOpen: false,
        setView: function (value) {
          this.view = value;
          try {
            localStorage.setItem(VIEW_KEY, value);
          } catch (e) {
            /* noop */
          }
        },
      };
    });

    /* Модалка формы: подтип ученика, строки контактов, закрытие. */
    Alpine.data("studentForm", function (initialKind) {
      return {
        open: true,
        kind: initialKind === "adult" ? "adult" : "child",
        /* Вкладки модалки: «Общее» — поля, «Платежи» — заглушка,
           «Настройки» — напоминания. Панели скрываются через x-show,
           поэтому поля всех вкладок остаются в DOM и попадают в POST. */
        tab: "general",
        /* Валидация браузера не может показать подсказку у поля в скрытой
           вкладке, поэтому перед отправкой ищем первое невалидное поле
           и переключаемся на вкладку, где оно живёт. */
        revealInvalidField: function (event) {
          var invalid = event.target.querySelector(":invalid");
          if (!invalid) return;
          var panel = invalid.closest("[data-tab-panel]");
          if (panel) this.tab = panel.dataset.tabPanel;
        },
        close: function () {
          this.open = false;
        },
        /* Живое форматирование телефона делает делегированный обработчик
           внизу файла (`data-phone-mask`), поэтому здесь метода нет:
           он работал бы только для полей, отрисованных вместе с формой. */
        /* Новая строка контакта добавляется модулем `appendContactRow`
           (выше): кнопки «Добавить контакт» больше нет — контакты
           добавляются через поле поиска `contactAdd`. */
        useContact: function (el) {
          var row = el.closest(".contact-row");
          if (!row) return;
          /* Пишем и в поле, и в строку-сводку: привязанного события `input`
             тут нет, сводка обновляется из него напрямую. */
          var set = function (field, value) {
            var input = row.querySelector('[data-field="' + field + '"]');
            if (input) input.value = value || "";
            var summary = row.querySelector('[data-summary="' + field + '"]');
            if (summary) summary.textContent = (value || "").trim();
          };
          set("contact_id", el.dataset.contactId);
          set("full_name", el.dataset.contactName);
          set("phone", el.dataset.contactPhone);
          set("email", el.dataset.contactEmail);
          var box = el.closest(".contact-suggestion");
          if (box) box.innerHTML = '<p class="contact-hint">Контакт выбран.</p>';
        },
        dismissSuggestion: function (el) {
          var box = el.closest(".contact-suggestion");
          if (box) box.innerHTML = '<p class="contact-hint">Будет создан новый контакт.</p>';
        },
        removeRow: function (el) {
          var row = el.closest(".contact-row");
          if (row) row.remove();
        },
      };
    });

    /* Поле добавления контакта: список из `data-options` (контакты
       репетитора) фильтруется по ФИО/телефону/email по мере ввода,
       Enter без совпадений создаёт новый контакт через `appendContactRow`
       и раскрывает его форму (строка в шаблоне создаётся с `open=true`). */
    Alpine.data("contactAdd", function () {
      /* Сколько контактов показывать за раз: контактов у репетитора
         десятки, ограничение держит выпадающий список компактным. */
      var OPTION_LIMIT = 8;

      return {
        open: false,
        query: "",
        active: -1,
        all: [],

        init: function () {
          try {
            this.all = JSON.parse(this.$root.dataset.options || "[]");
          } catch (e) {
            this.all = [];
          }
        },

        /* Контакты, уже привязанные к открытой форме (по hidden-полю
           `contact_id`): их повторный выбор добавил бы дубль строки. */
        linkedIds: function () {
          var linked = {};
          var ids = document.querySelectorAll(
            "[data-contact-row] input[data-field=\"contact_id\"]"
          );
          for (var i = 0; i < ids.length; i++) {
            if (ids[i].value) linked[ids[i].value] = true;
          }
          return linked;
        },

        /* Фильтр по подстроке без учёта регистра: ФИО и email целиком,
           телефон — по цифрам (набор без форматирования). */
        get matches() {
          var query = this.query.trim().toLowerCase();
          if (!query) return [];
          var digits = query.replace(/\D/g, "");
          var linked = this.linkedIds();
          return this.all.filter(function (item) {
            if (linked[item.id]) return false;
            if (item.full_name.toLowerCase().indexOf(query) !== -1) return true;
            if ((item.email || "").toLowerCase().indexOf(query) !== -1) return true;
            if (
              digits.length >= 3 &&
              (item.phone || "").replace(/\D/g, "").indexOf(digits) !== -1
            ) {
              return true;
            }
            return false;
          });
        },

        get shown() {
          return this.matches.slice(0, OPTION_LIMIT);
        },

        get hiddenCount() {
          return Math.max(this.matches.length - OPTION_LIMIT, 0);
        },

        openList: function () {
          // Список выпадает при начале ввода, а не при одном фокусе.
          if (this.query.trim()) this.open = true;
        },

        closeList: function () {
          this.open = false;
          this.active = -1;
        },

        onInput: function (value) {
          this.query = value;
          this.open = value.trim() !== "";
          this.active = -1;
        },

        choose: function (item) {
          appendContactRow({
            contact_id: item.id,
            full_name: item.full_name,
            phone: item.phone,
            email: item.email,
          });
          this.reset();
        },

        createNew: function () {
          var name = this.query.trim();
          if (!name) return;
          appendContactRow({ full_name: name });
          this.reset();
        },

        reset: function () {
          this.query = "";
          this.active = -1;
          this.open = false;
          if (this.$refs.input) this.$refs.input.value = "";
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
            if (!this.query.trim()) return;
            if (!this.open) {
              this.open = true;
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
            if (!this.query.trim()) return;
            // Список открыт и что-то нашлось — выбираем подсвеченный или
            // первый вариант; иначе (нет совпадений, список закрыт Escape)
            // создаём новый контакт с введённым ФИО.
            if (this.open && this.matches.length) {
              this.choose(
                this.active >= 0 && this.active < this.shown.length
                  ? this.shown[this.active]
                  : this.matches[0]
              );
            } else {
              this.createNew();
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
