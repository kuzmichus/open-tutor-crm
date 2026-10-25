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

  /* Имена вкладок карточки ученика: `?tab=` из адреса принимается только
     из этого списка, иначе открылся бы пустой таб (design D9/D12). */
  var TAB_NAMES = ["general", "payments", "settings"];

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
    /* Вид списка: выбор хранится в localStorage и переживает перезагрузку.
       `deleted` — состояние кнопки «Удалённые»: она не добавляет нового
       параметра запроса, а двигает селект статуса на «В архиве» и триггерит
       `change` формы — фильтр остаётся делом сервера (design D5 change'а
       student-list-reference). Начальное значение читается из селекта,
       который отрисовал сервер. */
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
        deleted: false,
        init: function () {
          var select = document.getElementById("students-status");
          this.deleted = !!select && select.value === "archived";
        },
        setView: function (value) {
          this.view = value;
          try {
            localStorage.setItem(VIEW_KEY, value);
          } catch (e) {
            /* noop */
          }
        },
        toggleDeleted: function () {
          var select = document.getElementById("students-status");
          if (!select) return;
          this.deleted = !this.deleted;
          select.value = this.deleted ? "archived" : "";
          var form = document.getElementById("students-filters");
          if (form && window.htmx) window.htmx.trigger(form, "change");
        },
      };
    });

    /* Модалка «Доступ ученика»: генерация пароля. Валидация и сохранение —
       на сервере (`credentials.py`); здесь только удобная кнопка
       «Сгенерировать» из референса. Алфавит без похожих символов
       (0/O, 1/l/I) — пароль можно надиктовать по телефону; тот же принцип,
       что у серверного генератора в `credentials.py`. */
    Alpine.data("studentAccess", function () {
      var CHARS =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
      return {
        open: true,
        generate: function () {
          var input = this.$refs.password;
          if (!input) return;
          var crypto = window.crypto || window.msCrypto;
          var value = "";
          if (crypto && crypto.getRandomValues) {
            var bytes = new Uint8Array(12);
            crypto.getRandomValues(bytes);
            for (var i = 0; i < bytes.length; i++) {
              /* Отбор с отсечением (rejection sampling): байты выше
                 последнего кратного длины алфавита отбрасываются, иначе
                 первые символы алфавита выпадали бы чуть чаще. */
              while (bytes[i] >= 248) {
                crypto.getRandomValues(bytes.subarray(i, i + 1));
              }
              value += CHARS[bytes[i] % CHARS.length];
            }
          } else {
            for (var j = 0; j < 12; j++) {
              value += CHARS[Math.floor(Math.random() * CHARS.length)];
            }
          }
          input.value = value;
        },
        close: function () {
          this.open = false;
        },
      };
    });

    /* Модалка формы: подтип ученика, строки контактов, закрытие. */
    Alpine.data("studentForm", function (initialKind, initialTab) {
      return {
        open: true,
        kind: initialKind === "adult" ? "adult" : "child",
        /* Вкладки модалки: «Общее» — поля, «Платежи» — счёт ученика,
           «Настройки» — напоминания. Панели скрываются через x-show,
           поэтому несохранённые правки «Общего» доживают до сохранения,
           а не пропадают при клике на «Платежи» (design D9).

           `initialTab` приходит из адреса (`?tab=payments`): по нему
           карточка открывается сразу на счёте. Неизвестное значение
           игнорируется — вкладка по умолчанию «Общее». */
        tab: TAB_NAMES.indexOf(initialTab) === -1 ? "general" : initialTab,
        /* Валидация браузера не может показать подсказку у поля в скрытой
           вкладке, поэтому перед отправкой ищем первое невалидное поле
           и переключаемся на вкладку, где оно живёт. */
        revealInvalidField: function (event) {
          var invalid = event.target.querySelector(":invalid");
          if (!invalid) return;
          var panel = invalid.closest("[data-tab-panel]");
          if (panel) this.tab = panel.dataset.tabPanel;
        },
        /* Та же проблема, но для соседней формы: каждая форма вкладки
           добирает поля другой через `hx-include`, и htmx валидирует их
           сам. Своя форма при этом валидна (пустое имя лежит в «Общем»),
           поэтому браузер не показывает ничего, а htmx молча останавливает
           запрос событием `htmx:validation:halted` — со стороны это
           выглядит как «кнопка не работает». Переключаем вкладку на первое
           невалидное поле и повторяем подсказку, когда панель уже видна. */
        init: function () {
          var self = this;
          this._onValidationHalted = function (event) {
            var errors = (event.detail && event.detail.errors) || [];
            var invalid = errors.length ? errors[0].elt : null;
            if (!invalid) return;
            var panel = invalid.closest("[data-tab-panel]");
            if (panel && panel.dataset.tabPanel) {
              self.tab = panel.dataset.tabPanel;
            }
            /* Панель показывается через x-show — эффект Alpine применится
               в микрозадаче, поэтому подсказку просим следующим тиком. */
            setTimeout(function () {
              try {
                if (typeof invalid.reportValidity === "function") {
                  invalid.reportValidity();
                }
              } catch (error) {
                /* Скрытое поле могло исчезнуть из DOM — подсказка не нужна. */
              }
            }, 0);
          };
          document.addEventListener(
            "htmx:validation:halted",
            this._onValidationHalted
          );
        },
        destroy: function () {
          document.removeEventListener(
            "htmx:validation:halted",
            this._onValidationHalted
          );
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
       и раскрывает его форму (строка в шаблоне создаётся с `open=true`).

       Виджет списка — общий `createPersonPicker` (`picker.js`): то же поле
       в форме группы выглядит и ведёт себя так же. Здесь — только домен:
       какие контакты исключить и что сделать с выбранным. */
    Alpine.data("contactAdd", function () {
      return window.mergePersonPicker(
        window.createPersonPicker({
          searchFields: ["full_name", "phone", "email"],
          /* Контакты, уже привязанные к открытой форме (по hidden-полю
             `contact_id`): их повторный выбор добавил бы дубль строки. */
          exclude: function () {
            var linked = {};
            var ids = document.querySelectorAll(
              "[data-contact-row] input[data-field=\"contact_id\"]"
            );
            for (var i = 0; i < ids.length; i++) {
              if (ids[i].value) linked[ids[i].value] = true;
            }
            return linked;
          },
          choose: function (item) {
            appendContactRow({
              contact_id: item.id,
              full_name: item.full_name,
              phone: item.phone,
              email: item.email,
            });
          },
          /* Enter без совпадений — создать новый контакт с введённым ФИО. */
          onEnter: function () {
            var name = this.query.trim();
            if (!name) return;
            appendContactRow({ full_name: name });
            this.reset();
          },
        }),
        {
          init: function () {
            this.initPicker();
          },
        }
      );
    });
  });
})();
