/**
 * OpenTutorCRM — компоненты уроков (Alpine.js): селект цели и модалка формы.
 *
 * Поле «ученик/группа» формы урока: серверный список выбора —
 * lookup-эндпоинты модуля lesson отдают фрагмент
 * `lesson/_lookup_options.html` в контейнер опций (в отличие от общего
 * виджета `picker.js`, где варианты лежат в `data-options`). Поле
 * открывается сразу по клику (запрос с пустым `q` — весь список),
 * ввод фильтрует его с debounce, в конце списка — разделитель и пункт
 * создания; мини-форма подменяет поле, ответ сервера применяется
 * событием `lesson-target-created` (паттерн `groups.js`).
 *
 * Подключается только на странице уроков и строго до `alpine.min.js`.
 */
(function () {
  "use strict";

  var SEARCH_DELAY = 250; /* мс: пауза перед фильтрующим запросом */

  /* «07» — ввод времени слотов панели расписания. */
  function pad2(value) {
    return (value < 10 ? "0" : "") + value;
  }

  function parseJson(value, fallback) {
    try {
      return JSON.parse(value || "");
    } catch (e) {
      return fallback;
    }
  }

  /* Ответ мини-формы: Alpine не может подхватить JSON из htmx-свопа сам,
     поэтому данные лежат в `data-`атрибутах фрагмента, а обработчик
     `htmx:afterSwap` передаёт их полю селекта (как в groups.js). */
  function readTargetUpdate(el) {
    if (!el || el.id.indexOf("lesson-target-update-") !== 0) return null;
    return {
      kind: el.id.slice("lesson-target-update-".length),
      selected: parseJson(el.dataset.selected, null),
      error: el.dataset.error || "",
    };
  }

  window.lessonTarget = function (options) {
    options = options || {};
    return {
      kind: options.kind || "student",
      lookupUrl: "",
      createUrl: "",
      optionsId: "",
      updateId: "",
      selectedId: "",
      selectedName: "",
      listOpen: false,
      miniOpen: false,
      miniError: "",
      query: "",
      searchTimer: null,

      /* Конфиг поля — в `data-config` корня (JSON, как `data-members`). */
      init: function () {
        var config = parseJson(this.$root.dataset.config, {}) || {};
        this.kind = config.kind || this.kind;
        this.lookupUrl = config.lookupUrl || "";
        this.createUrl = config.createUrl || "";
        this.optionsId = config.optionsId || "";
        this.updateId = config.updateId || "";
        this.selectedId = config.selectedId || "";
        this.selectedName = config.selectedName || "";
      },

      /* Список — накладной поповер (`dropdown.js`): раскрытие не двигает
         поля формы и не обрезается прокручиваемым телом модалки. */
      positionList: function () {
        if (!this.listOpen) return;
        if (window.openDropdown) {
          window.openDropdown(this.$refs.input, this.$refs.list);
        }
      },

      /* Список открывается сразу по клику/фокусу: запрос с пустым
         `q` возвращает весь список выбора — ввод ждать не нужно. */
      openList: function () {
        this.listOpen = true;
        this.refresh();
        var self = this;
        this.$nextTick(function () {
          self.positionList();
        });
      },

      closeList: function () {
        this.listOpen = false;
        if (window.closeDropdown) window.closeDropdown(this.$refs.list);
      },

      /* Ввод фильтрует открытый список, не закрывая его. */
      onInput: function (value) {
        this.query = value;
        this.listOpen = true;
        var self = this;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(function () {
          self.refresh();
        }, SEARCH_DELAY);
      },

      /* Подменяет только контейнер опций: разделитель и пункт создания
         остаются на месте. */
      refresh: function () {
        if (!window.htmx || !this.lookupUrl || !this.optionsId) return;
        window.htmx.ajax("GET", this.lookupUrl, {
          target: "#" + this.optionsId,
          swap: "innerHTML",
          values: { q: this.query },
        });
      },

      /* Клик по серверной опции: `data-id` / `data-name` с фрагмента. */
      choose: function (target) {
        var option =
          target && target.closest ? target.closest("[data-id]") : null;
        if (!option) return;
        this.applySelection(
          option.getAttribute("data-id"),
          option.getAttribute("data-name") || ""
        );
      },

      /* Enter выбирает первый видимый вариант и не отправляет форму. */
      enterChoose: function () {
        if (!this.listOpen) return;
        var container = document.getElementById(this.optionsId);
        var option = container && container.querySelector("[data-id]");
        if (option) this.choose(option);
      },

      applySelection: function (id, name) {
        this.selectedId = id;
        this.selectedName = name;
        this.query = "";
        this.closeList();
      },

      /* --- Мини-формы создания (D7) --- */

      openMiniForm: function () {
        this.closeList();
        this.miniError = "";
        this.miniOpen = true;
        var self = this;
        this.$nextTick(function () {
          var first =
            self.kind === "student" ? self.$refs.miniFirst : self.$refs.miniName;
          if (first) first.focus();
        });
      },

      /* «Отменить»: поле возвращается без изменений, ничего не создаётся. */
      cancelMiniForm: function () {
        this.miniOpen = false;
        this.miniError = "";
        this.clearMiniFields();
      },

      clearMiniFields: function () {
        ["miniFirst", "miniLast", "miniPhone", "miniName", "miniPrice"].forEach(
          function (ref) {
            if (this.$refs[ref]) this.$refs[ref].value = "";
          },
          this
        );
      },

      /* Обязательное поле проверяется здесь и заново на сервере:
         нативный `required` не работает для кнопки вне `<form>`. */
      submitMiniForm: function () {
        var required =
          this.kind === "student" ? this.$refs.miniFirst : this.$refs.miniName;
        var message =
          this.kind === "student"
            ? "Укажите имя ученика."
            : "Укажите название группы.";
        var value = required ? required.value.trim() : "";
        if (!value) {
          this.miniError = message;
          if (required) required.focus();
          return;
        }

        var values;
        if (this.kind === "student") {
          values = {
            first_name: value,
            last_name: this.$refs.miniLast ? this.$refs.miniLast.value : "",
            phone: this.$refs.miniPhone ? this.$refs.miniPhone.value : "",
          };
        } else {
          values = {
            name: value,
            price: this.$refs.miniPrice ? this.$refs.miniPrice.value : "",
          };
        }
        window.htmx.ajax("POST", this.createUrl, {
          target: "#" + this.updateId,
          swap: "outerHTML",
          values: values,
        });
      },

      /* Ответ мини-формы: выбранная запись закрывает её, ошибка — нет. */
      applyTargetUpdate: function (payload) {
        if (!payload) return;
        if (payload.error) {
          this.miniError = payload.error;
          return;
        }
        if (payload.selected && payload.selected.id) {
          this.applySelection(payload.selected.id, payload.selected.name || "");
          this.miniOpen = false;
          this.miniError = "";
          this.clearMiniFields();
        }
      },

      /* Событие `lesson-target-created` обрабатывается только своим видом:
         поля ученика и группы в форме могут существовать одновременно. */
      onTargetCreated: function (detail) {
        if (!detail || detail.kind !== this.kind) return;
        this.applyTargetUpdate(detail);
      },
    };
  };

  /* Модалка формы урока (создание и редактирование): вкладки «Урок» и
     «ДЗ» (панели — два отдельных `<form>`, переключение по `activeTab`;
     в создании вкладка «ДЗ» disabled и остаётся неактивной), тип урока
     (переключает цель и скрывает оплату у группового), поле «Начало»
     (подсказка об окончании, минуты по умолчанию 00), панель
     расписания серии с пресетами «До даты» и двухшаговое удаление.
     Цена проведённого урока блокируется на сервере (`price_locked` —
     readonly-поле), Alpine-состояния для неё нет. */
  window.lessonForm = function () {
    return {
      open: true,
      activeTab: "lesson", /* активная вкладка: 'lesson' | 'hw' */
      type: "individual",
      repeat: false,
      slots: [], /* [{weekday: 0..6, start: "HH:MM", end: "HH:MM"}] */
      /* Блок «Присутствие» (design D6): участники с отметками приходят
         из `data-config` (attendance_participants контекста формы). */
      attendance: [], /* [{student_id, name, present, reason}] */
      startsAt: "",      /* «Начало»: "YYYY-MM-DDTHH:MM" */
      durationMin: 60,   /* «Длительность» в минутах */
      startPrefill: "",  /* значение, подставленное при открытии пикера */
      startTouched: false, /* пользователь сам менял поле (не только мы) */
      confirmingDelete: false,
      confirmingSeriesDelete: false,

      /* Конфиг — в `data-config` корня (JSON), как у lessonTarget. */
      init: function () {
        var config = parseJson(this.$root.dataset.config, {}) || {};
        if (config.type) this.type = config.type;
        if (Array.isArray(config.attendance)) this.attendance = config.attendance;
        var startsEl = document.getElementById("lesson-starts-at");
        var durationEl = document.getElementById("lesson-duration");
        if (startsEl && startsEl.value) this.startsAt = startsEl.value;
        if (durationEl) {
          var duration = parseInt(durationEl.value, 10);
          if (!isNaN(duration)) this.durationMin = duration;
        }
      },

      close: function () {
        this.open = false;
      },

      /* «Начало» — источник для подсказки об окончании, для предзаполнения
         слотов и для блокировки «Повторять урок»: серия без времени бессмысленна. */
      onStartInput: function (value) {
        this.startTouched = true;
        this.startsAt = value;
        if (!value && this.repeat) {
          this.repeat = false;
          this.slots = [];
        }
      },

      onDurationChange: function (value) {
        var duration = parseInt(value, 10);
        this.durationMin = isNaN(duration) ? 60 : duration;
      },

      /* Пустое поле: при открытии пикера подставляем сегодняшнюю дату с
         текущим часом и минутами 00 — иначе Chrome предлагает текущее
         время с текущими минутами. Пользователь может оставить это
         значение, лишь изменив поле (тогда срабатывает `input`); если
         поле так и не трогали, при уходе фокуса возвращаем пустоту —
         поле обязательное и не должно заполняться само. */
      onStartFocus: function () {
        if (this.startsAt) return;
        this.startTouched = false;
        var now = new Date();
        this.startPrefill =
          now.getFullYear() + "-" + pad2(now.getMonth() + 1) + "-" +
          pad2(now.getDate()) + "T" + pad2(now.getHours()) + ":00";
        this.startsAt = this.startPrefill;
        var el = document.getElementById("lesson-starts-at");
        if (el) el.value = this.startPrefill;
      },

      onStartBlur: function () {
        if (!this.startPrefill) return;
        if (!this.startTouched) {
          var el = document.getElementById("lesson-starts-at");
          if (el) el.value = "";
          this.startsAt = "";
        }
        this.startPrefill = "";
      },

      /* Подсказка «Урок закончится в ЧЧ:ММ» под полем «Начало». */
      endTimeLabel: function () {
        if (!this.startsAt) return "";
        var start = new Date(this.startsAt); /* "YYYY-MM-DDTHH:MM" — локальное время */
        if (isNaN(start.getTime())) return "";
        var end = new Date(start.getTime() + this.durationMin * 60000);
        return pad2(end.getHours()) + ":" + pad2(end.getMinutes());
      },

      /* Включение «Повторять урок» предзаполняет панель из полей
         «Начало» и «Длительность» (спека: «Панель при открытии SHALL
         предзаполняться»); «Добавить время» добавляет такой же слот. */
      onRepeatChange: function () {
        if (this.repeat && this.slots.length === 0) this.prefillSlot();
      },

      addSlot: function () {
        this.prefillSlot();
      },

      prefillSlot: function () {
        if (!this.startsAt) return;
        var start = new Date(this.startsAt);
        if (isNaN(start.getTime())) return;
        var end = new Date(start.getTime() + this.durationMin * 60000);
        this.slots.push({
          /* JS: воскресенье = 0; в слотах — пн = 0 … вс = 6 (решение D1). */
          weekday: (start.getDay() + 6) % 7,
          start: pad2(start.getHours()) + ":" + pad2(start.getMinutes()),
          end: pad2(end.getHours()) + ":" + pad2(end.getMinutes()),
        });
      },

      removeSlot: function (index) {
        this.slots.splice(index, 1);
      },

      /* Слоты формы — JSON-список объектов D1 одним скрытым полем. */
      slotsValue: function () {
        return JSON.stringify(
          this.slots.map(function (slot) {
            return {
              weekday: slot.weekday,
              start_time: slot.start,
              end_time: slot.end,
            };
          })
        );
      },

      /* --- Блок «Присутствие» (design D6) --- */

      cameCount: function () {
        return this.attendance.filter(function (member) {
          return member.present;
        }).length;
      },

      /* Счётчик «Пришли N из M» в шапке блока. */
      cameLabel: function () {
        return "Пришли " + this.cameCount() + " из " + this.attendance.length;
      },

      /* Причина обязательна у каждого отсутствовавшего (CHECK в БД),
         поэтому по умолчанию — «Без причины». */
      onPresentChange: function (member) {
        if (member.present) {
          member.reason = "";
        } else if (!member.reason) {
          member.reason = "no_reason";
        }
      },

      allCame: function () {
        this.attendance.forEach(function (member) {
          member.present = true;
          member.reason = "";
        });
      },

      noneCame: function () {
        this.attendance.forEach(function (member) {
          member.present = false;
          if (!member.reason) member.reason = "no_reason";
        });
      },

      /* Отметки формы — JSON-список {student_id, present, reason} одним
         скрытым полем; сервер валидирует состав и причины (design D7). */
      attendanceValue: function () {
        return JSON.stringify(
          this.attendance.map(function (member) {
            return {
              student_id: member.student_id,
              present: !!member.present,
              reason: member.present ? null : member.reason || "no_reason",
            };
          })
        );
      },

      /* Чип пресета «До даты» (значения — из настроек календаря
         репетитора): подставляет дату в поле «Дата окончания»; поле
         остаётся обычным input — выбранное можно поправить вручную. */
      setUntil: function (value) {
        var el = document.getElementById("lesson-until");
        if (el) el.value = value;
      },
    };
  };

  document.addEventListener("alpine:init", function () {
    Alpine.data("lessonTarget", window.lessonTarget);
    Alpine.data("lessonForm", window.lessonForm);
  });

  /* Успех сохранения ДЗ (design D8): кнопка «Сохранить ДЗ» живёт в
     зафиксированном футере модалки, вне свопаемой панели, поэтому сервер
     помечает успех атрибутом `data-hw-saved="1"` на форме панели; здесь
     переводим футерную кнопку в зелёное неактивное состояние «Успешно
     сохранено», через пару секунд возвращаем обычный вид. Таймер висит
     на кнопке футера: футер свопом не подменяется, узел остаётся живым. */
  var HW_SUCCESS_MS = 2000;
  var HW_IDLE_LABEL = "Сохранить ДЗ";

  function flashHwSave() {
    var panel = document.getElementById("homework-panel");
    if (!panel || panel.getAttribute("data-hw-saved") !== "1") return;
    var button = document.querySelector("[data-hw-save]");
    if (!button) return;
    button.disabled = true;
    button.classList.remove("btn--primary");
    button.classList.add("btn--success");
    button.textContent = "Успешно сохранено";
    setTimeout(function () {
      if (!button.isConnected) return;
      button.disabled = false;
      button.classList.remove("btn--success");
      button.classList.add("btn--primary");
      button.textContent = HW_IDLE_LABEL;
    }, HW_SUCCESS_MS);
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    // `event.target` — подменённый элемент; `detail.elt` — то же значение
    // в htmx 1.x, берём его как запасной вариант.
    var swapped = (event.detail && event.detail.elt) || event.target;
    var payload = readTargetUpdate(swapped);
    if (payload) {
      document.dispatchEvent(
        new CustomEvent("lesson-target-created", { detail: payload, bubbles: true })
      );
    }
    flashHwSave();
    syncBulkSelection();
    if (typeof window.renderIcons === "function") window.renderIcons();
  });

  /* ------------------------------------------------------------------------
     Массовая отметка уроков проведёнными (change lessons-table-scale).

     Выбор строк — клиентское состояние, но не источник истины: сервер
     всё равно отбирает уроки по `tutor_id` и статусу, поэтому подделанный
     id в форме не даёт ни доступа, ни второго списания.

     Делегированные обработчики на документе, а не на таблице: таблица
     подменяется htmx-свопом после каждого фильтра, и подписки на её узлы
     умирали бы вместе с ней.
     ---------------------------------------------------------------------- */

  function selectableBoxes() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-lesson-select]:not([disabled])")
    );
  }

  function selectAllBox() {
    return document.querySelector("[data-lessons-select-all]");
  }

  /* Кнопка и подпись отражают выбор: без выбранных строк действие
     недоступно, а подпись говорит, сколько уроков уйдёт в «Проведён». */
  function syncBulkSelection() {
    var boxes = selectableBoxes();
    var checked = boxes.filter(function (box) { return box.checked; });
    var button = document.querySelector("[data-lessons-complete]");
    var hint = document.querySelector("[data-lessons-selection-hint]");
    var all = selectAllBox();

    if (button) button.disabled = checked.length === 0;
    if (hint) {
      hint.textContent = checked.length
        ? "Выбрано: " + checked.length + " — отметить проведёнными"
        : "Отметьте уроки, которые уже прошли";
    }
    if (all) {
      all.checked = boxes.length > 0 && checked.length === boxes.length;
      /* Промежуточное состояние: часть строк выбрана. Без него чекбокс
         «выбрать все» выглядел бы просто выключенным. */
      all.indeterminate = checked.length > 0 && checked.length < boxes.length;
    }
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (!target || !target.matches) return;

    if (target.matches("[data-lessons-select-all]")) {
      selectableBoxes().forEach(function (box) {
        box.checked = target.checked;
      });
      syncBulkSelection();
      return;
    }
    if (target.matches("[data-lesson-select]")) syncBulkSelection();
  });

  /* Клик по чекбоксу не должен открывать модалку: строка ловит клик
     целиком (`hx-get` на `<tr>`). Гасится не здесь, а фильтром триггера
     строки (`hx-trigger="click[!event.target.closest('.lessons-select-hit')]"`):
     обработчик htmx висит на самой строке, и `stopPropagation` с
     `document` в фазе всплытия приходил уже после неё — модалка успевала
     открыться. Проверено в браузере. */

  /* Список перерисован — выбора больше нет: строки другие. */
  document.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (target && target.id === "lessons-table") syncBulkSelection();
  });

  syncBulkSelection();
})();
