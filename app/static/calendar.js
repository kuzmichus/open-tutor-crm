/**
 * OpenTutorCRM — клиентская интерактивность недельного календаря.
 *
 * Alpine-компонент `calendarGrid` монтируется на области `#calendar-swap`
 * (design.md D6): hover четвертей часа, форма урока в `#modal`, диалог
 * «Новый слот», диалог записи на слот, drag занятий. Сервер рендерит сетку
 * и карточки (SSR), JS только читает данные ячеек из `data-*` и меняет
 * DOM — без сетевых запросов (кроме открытия формы урока через htmx).
 *
 * Подключается на странице календаря до `alpine.min.js` (через
 * `{% block head %}` в base.html): подписка на `alpine:init` должна
 * сработать раньше, чем Alpine начнёт обход DOM — тот же паттерн, что
 * у `students.js` и `combobox.js`.
 *
 * Слушатели вешаются на постоянный корень `#calendar-swap`, а не на сетку:
 * htmx при листании недель меняет только содержимое корня, поэтому
 * привязки переживают подмену области.
 */
(function () {
  "use strict";

  /* Минуты от 6:00 — границы таймлайна (см. services/presentation.py). */
  var GRID_START_MIN = 6 * 60;
  var GRID_END_MIN = 23 * 60;
  var STEP_MIN = 15;               /* снап к четверти часа */
  var DRAG_THRESHOLD_PX = 5;       /* дальше — драг, ближе — обычный клик */
  /* Форма урока со страницы Уроков — единственная точка создания урока
     на календаре (design.md D9): клик по четверти и «Добавить» открывают
     её в контейнере #modal с предзаполненным «Началом». */
  var LESSON_NEW_URL = "/tutor/lessons/new";
  /* Ключ localStorage: выбранный режим раскраски переживает перезагрузку
     и листание недель (design.md D5). */
  var COLOR_STORAGE_KEY = "opentutorcrm:calendar-color";
  /* «14:00» → 840; кривое значение → null. */
  function parseClock(value) {
    var match = /^(\d{2}):(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
  }

  /* 840 → «14:00» — тот же формат, что рендерит сервер. */
  function formatClock(minutes) {
    var clamped = Math.max(GRID_START_MIN, Math.min(minutes, GRID_END_MIN));
    var h = Math.floor(clamped / 60);
    var m = clamped % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }

  /* Округление до ближайшей четверти часа: 16:37 → 16:30 (спека о снапе). */
  function snapToQuarter(minutes) {
    return Math.round(minutes / STEP_MIN) * STEP_MIN;
  }

  /* «2026-10-19» — сегодняшняя дата клиента в формате ISO. */
  function todayIso() {
    var now = new Date();
    var m = now.getMonth() + 1;
    var d = now.getDate();
    return (
      now.getFullYear() +
      "-" +
      (m < 10 ? "0" : "") + m +
      "-" +
      (d < 10 ? "0" : "") + d
    );
  }

  document.addEventListener("alpine:init", function () {
    Alpine.data("calendarGrid", function () {
      return {
        /* Подсказка времени четверти: текст и позиция чипа в сетке. */
        hoverTime: null,
        hoverX: 0,
        hoverY: 0,

        /* Модалка «Новый слот»: редактируемые дата/время из slotForm
           (design.md D1). Формы создания урока здесь больше нет — её
           открывает настоящая форма урока в #modal (design.md D9). */
        modal: { open: false, duration: 40 },
        /* Адрес формы создания урока — из `data-lesson-new` корня
           (design.md D9): её открывают клик по четверти и «Добавить». */
        lessonNewUrl: "/tutor/lessons/new",
        /* Поля диалога создания слота: дата и время (спека slot-booking). */
        slotForm: { date: "", time: "" },
        /* Диалог «Новый отпуск»: открыт/дата начала/дата конца — только DOM
           (спека vacation-creation, design.md D2). */
        vacationForm: { open: false, start: "", end: "" },
        /* Диалог записи: открыт/имя/контакт; _bookingSlot — DOM-узел
           карточки конкретного слота, а не индекс в массиве (design.md D6). */
        booking: { open: false, name: "", contact: "" },
        _bookingSlot: null,
        /* Подавитель клика после drag (design.md D7): браузер эмитит click
           после pointerup, и без флага перенос открывал бы форму урока. */
        _suppressClick: false,
        /* Выпадающий список «Цвет», меню быстрого добавления «⋮» и тост
           подтверждений демо-режима. */
        colorOpen: false,
        moreOpen: false,
        toast: { open: false, text: "" },
        /* Активный режим раскраски (design.md D5): сервер рендерит его из
           `?color=`, выбор пользователя переживает перезагрузку в
           localStorage. */
        colorMode: "target",

        init: function () {
          var root = this.$root;
          var self = this;
          root.addEventListener("pointerover", function (event) {
            self.onSlotHover(event);
          });
          root.addEventListener("pointerout", function (event) {
            self.onSlotLeave(event);
          });
          root.addEventListener("pointerdown", function (event) {
            self.onEventPointerDown(event);
          });
          /* Клики по карточкам слотов — делегированием на корне: карточки
             создаются на клиенте и подменяются при листании недель. */
          root.addEventListener("click", function (event) {
            self.onAreaClick(event);
          });
          /* Подавление клика после drag (design.md D7): браузер эмитит
             click после pointerup, и htmx открыл бы форму редактирования.
             Capture-фаза на постоянном корне срабатывает раньше
             слушателей htmx на самой карточке, поэтому
             `stopImmediatePropagation` гасит событие до них. */
          root.addEventListener("click", function (event) {
            self.onSuppressedClick(event);
          }, true);
          /* Корень не подменяется при листании недель, поэтому его hx-get
             (подписка на lesson-saved) надо держать на видимой неделе —
             иначе сохранение урока вернуло бы первую открытую неделю
             (design.md D6). htmx читает hx-get в момент запроса. Заодно
             возвращаем `color` в адреса только что отрисованной панели
             (design.md D5). */
          root.addEventListener("htmx:afterSwap", function () {
            self.applyColorMode();
          });
          /* Адрес формы создания урока — из разметки (design.md D9). */
          if (root.dataset && root.dataset.lessonNew) {
            this.lessonNewUrl = root.dataset.lessonNew;
          }
          /* Режим раскраски: сервер отрендерил активный (`?color=`), но
             выбор пользователя важнее — localStorage помнит его между
             открытиями (design.md D5). Если режим из хранилища отличается
             от серверного, перерисовываем область с нужным параметром. */
          if (root.dataset && root.dataset.colorMode) {
            this.colorMode = root.dataset.colorMode;
          }
          var stored = this.readColorMode();
          if (stored && stored !== this.colorMode) {
            this.colorMode = stored;
            this.reloadWeek();
          } else {
            this.applyColorMode();
          }
        },

        /* Сохранённый режим раскраски; null — выбора ещё не было. */
        readColorMode: function () {
          try {
            return window.localStorage.getItem(COLOR_STORAGE_KEY);
          } catch (e) {
            /* приватный режим/запрет хранилища — работаем без запоминания */
            return null;
          }
        },

        /* Запомнить режим раскраски в браузере (design.md D5). */
        storeColorMode: function () {
          try {
            window.localStorage.setItem(COLOR_STORAGE_KEY, this.colorMode);
          } catch (e) {
            /* хранилище недоступно — выбор живёт до перезагрузки */
          }
        },

        /* Переключение режима: состояние + localStorage + запрос недели с
           `?color=` (раскраску считает сервер — design.md D5). */
        setColorMode: function (mode) {
          if (mode !== "target" && mode !== "status") return;
          this.colorOpen = false;
          if (mode === this.colorMode) return;
          this.colorMode = mode;
          this.storeColorMode();
          this.applyColorMode();
          this.reloadWeek();
        },

        /* Подставить активный режим в адреса htmx: листание недель и
           подписка `lesson-saved` должны нести `color`, иначе смена режима
           потеряется на первом же клике (design.md D5). */
        applyColorMode: function () {
          var root = this.$root;
          var links = root.querySelectorAll('[hx-get^="/tutor/calendar"]');
          for (var i = 0; i < links.length; i++) {
            links[i].setAttribute(
              "hx-get", this.withColor(links[i].getAttribute("hx-get"))
            );
          }
          this.syncWeekParam();
        },

        /* Адрес календаря с активным режимом раскраски. */
        withColor: function (url) {
          if (!url) return url;
          var clean = url.replace(/([?&])color=[^&]*&?/g, "$1").replace(/[?&]$/, "");
          var glue = clean.indexOf("?") === -1 ? "?" : "&";
          return clean + glue + "color=" + this.colorMode;
        },

        /* Перерисовать текущую неделю с сервера (после смены режима). */
        reloadWeek: function () {
          if (!window.htmx) return;
          window.htmx.ajax("GET", this.withColor(this.weekPath()), {
            target: "#calendar-swap",
            swap: "innerHTML",
          });
        },

        /* Путь текущей недели без origin — для htmx-запросов. */
        weekPath: function () {
          var start = this.currentStart();
          return "/tutor/calendar" + (start ? "?start=" + start : "");
        },

        /* Данные четверти из `data-*` ячейки: дата, время начала/конца. */
        slotData: function (el) {
          var start = el.getAttribute("data-start") || "";
          return {
            date: start.slice(0, 10),
            startMin: parseClock(start.slice(11, 16)),
            time: start.slice(11, 16),
            endMin: parseClock((el.getAttribute("data-end") || "").slice(11, 16)),
          };
        },

        /* Наведение на четверть: подсвечиваем её время (6:00, 6:15…). */
        onSlotHover: function (event) {
          var slot = event.target.closest && event.target.closest(".cal-slot");
          if (!slot) return;
          var grid = this.$root.querySelector(".cal-grid");
          if (!grid) return;
          var slotRect = slot.getBoundingClientRect();
          var gridRect = grid.getBoundingClientRect();
          this.hoverTime = this.slotData(slot).time;
          this.hoverX = slotRect.left - gridRect.left;
          this.hoverY = slotRect.top - gridRect.top;
        },

        /* Уход курсора: гасим чип (переход на соседнюю четверть
           перехватит следующий pointerover). */
        onSlotLeave: function (event) {
          var slot = event.target.closest && event.target.closest(".cal-slot");
          if (!slot) return;
          var to = event.relatedTarget;
          if (to && to.closest && to.closest(".cal-slot")) return;
          this.hoverTime = null;
        },

        /* Клик по пустой четверти: форма создания урока с предзаполненным
           «Началом» этой четверти (спека «Клик по четверти открывает форму
           создания урока», design.md D9). */
        openSlot: function (el) {
          var data = this.slotData(el);
          if (!data.date || data.startMin === null) return;
          /* Клик в колонке дня с «Отпуском» не открывает форму урока
             (спека vacation-creation): покрывает и клиентские блоки, и
             серверную демо-заглушку — иначе клик утекал бы в четверть
             под блоком с pointer-events: none (design.md D5). */
          var day = el.closest(".cal-day");
          if (day && day.querySelector(".cal-vacation")) return;
          this.openLessonForm(data.date, data.time);
        },

        /* Форма создания урока в контейнере #modal: `?starts_at=` заполняет
           «Начало» (спека lesson-management «Префилл из календаря»). Запрос
           шлёт htmx — форма со страницы Уроков сама закрывается по
           `lesson-saved` (design.md D6/D9). */
        openLessonForm: function (date, time) {
          var url = this.lessonNewUrl;
          if (!date || !time) return;
          window.htmx.ajax("GET", url + "?starts_at=" + date + "T" + time, {
            target: "#modal",
            swap: "innerHTML",
          });
        },

        /* Общий префилл «ближайшей даты/времени» для кнопок «Добавить» и
           «Добавить слот»: сегодня (если неделя содержит сегодняшний день,
           иначе первый день сетки) и ближайшая будущая четверть часа. */
        prefillMoment: function () {
          var days = this.$root.querySelectorAll(".cal-day[data-date]");
          var date = days.length ? days[0].getAttribute("data-date") : todayIso();
          for (var i = 0; i < days.length; i++) {
            if (days[i].getAttribute("data-date") === todayIso()) {
              date = todayIso();
              break;
            }
          }
          var now = new Date();
          var minutes = now.getHours() * 60 + now.getMinutes();
          minutes = snapToQuarter(minutes) + STEP_MIN;   /* ближайшая будущая */
          return { date: date, time: formatClock(minutes) };
        },

        /* Кнопка «Добавить» и мобильная FAB: без привязки к четверти —
           общий префилл «ближайшая будущая четверть» и форма создания
           урока со страницы Уроков (design.md D9). */
        openForm: function () {
          var moment = this.prefillMoment();
          this.openLessonForm(moment.date, moment.time);
        },

        /* ------------------------------------------------------------------
           Меню быстрого добавления «⋮» (спека vacation-creation): повторный
           клик, клик вне меню и Escape закрывают меню — сам toggleMore и
           атрибуты разметки (@click.outside, @keydown.escape.window).
           ------------------------------------------------------------------ */
        toggleMore: function () {
          this.moreOpen = !this.moreOpen;
        },

        closeMore: function () {
          this.moreOpen = false;
        },

        /* Кнопка «Добавить слот» (пункт меню): модалка «Новый слот» с общим
           префиллом даты/времени и кнопкой «Создать» (design.md D1/D2).
           Выбор пункта сначала закрывает меню. */
        openSlotDialog: function () {
          this.closeMore();
          var moment = this.prefillMoment();
          this.slotForm.date = moment.date;
          this.slotForm.time = moment.time;
          this.modal.duration = 40;
          this.modal.open = true;
        },

        closeModal: function () {
          this.modal.open = false;
        },

        /* Демо-создание слота: карточка добавляется только в DOM, ноль
           сетевых запросов; время нормализуется к границе четверти часа
           (snapToQuarter), конец зажимается по границе 23:00 (design.md D2).
           Слот переживает закрытие диалога и исчезает при листании недели —
           подмена #calendar-swap забирает карточку (design.md D6). */
        createSlot: function () {
          var day = this.$root.querySelector(
            '.cal-day[data-date="' + this.slotForm.date + '"]'
          );
          if (!day) return;

          var startMin = parseClock(this.slotForm.time);
          if (startMin === null) return;
          startMin = snapToQuarter(startMin);
          startMin = Math.max(GRID_START_MIN, Math.min(startMin, GRID_END_MIN - STEP_MIN));
          var duration = Math.max(STEP_MIN, parseInt(this.modal.duration, 10) || 40);
          duration = Math.min(duration, GRID_END_MIN - startMin);  /* конец — 23:00 */

          var card = this.renderCard({
            kind: "slot",
            startMin: startMin,
            duration: duration,
          });
          card.setAttribute("data-date", this.slotForm.date);
          day.appendChild(card);
          this.layoutDay(day);
          this.closeModal();
        },

        /* ------------------------------------------------------------------
           Диалог «Новый отпуск» (спека vacation-creation, design.md D2/D3):
           диапазон дат без времени и ученика, префилл общей ближайшей
           видимой датой (однодневный отпуск по умолчанию), закрытие —
           «Отмена», Escape и backdrop.
           ------------------------------------------------------------------ */

        /* Открытие: пункт меню «Добавить отпуск» сначала закрывает меню,
           обе даты = ближайшая видимая (сегодня в неделе, иначе первая). */
        openVacationDialog: function () {
          this.closeMore();
          var moment = this.prefillMoment();
          this.vacationForm.start = moment.date;
          this.vacationForm.end = moment.date;
          this.vacationForm.open = true;
        },

        /* Закрытие: окно закрывается, поля сбрасываются — сетка не меняется. */
        closeVacation: function () {
          this.vacationForm.open = false;
          this.vacationForm.start = "";
          this.vacationForm.end = "";
        },

        /* Демо-создание отпуска: пересечение диапазона с data-date колонок
           сетки; блок «Отпуск» вставляется первым ребёнком дня — под
           карточки занятий (design.md D4). Дни вне видимой недели
           игнорируются, блоки переживают закрытие диалога и исчезают при
           листании недели; ноль сетевых запросов.
           end < start — defensive-отказ (нативная валидация уже не
           пускает такую отправку): блоки не создаются, окно открыто. */
        createVacation: function (event) {
          event.preventDefault();
          var start = this.vacationForm.start;
          var end = this.vacationForm.end;
          if (!start || !end || end < start) return;
          var days = this.$root.querySelectorAll(".cal-day[data-date]");
          for (var i = 0; i < days.length; i++) {
            var iso = days[i].getAttribute("data-date");
            if (iso < start || iso > end) continue;
            var block = document.createElement("div");
            block.className = "cal-vacation";
            block.textContent = "Отпуск";
            days[i].insertBefore(block, days[i].firstChild);
          }
          this.closeVacation();
        },

        /* Рендер карточки из общего шаблона: позиция/высота — в часах от
           6:00, как у серверных уроков (services/presentation.py).
           kind: "lesson" (по умолчанию) — карточка занятия; "slot" —
           карточка слота: класс cal-event--slot, подпись состояния
           «Свободен · запись по ссылке» и кнопка «Записаться» только у
           свободного (спека slot-booking, design.md D3).

           Разметка та же, что у серверной карточки: имя цели отдельной
           строкой, цена и время — во второй (`cal-event__meta`). */
        renderCard: function (data) {
          var source = document.getElementById("cal-event-template");
          var card = source.content.firstElementChild.cloneNode(true);
          var price = card.querySelector(".cal-event__price");
          if (data.kind === "slot") {
            card.className = "cal-event cal-event--slot";
            /* Подпись состояния вместо имени ученика. */
            var state = document.createElement("span");
            state.className = "cal-event__state";
            state.textContent = "Свободен · запись по ссылке";
            card.replaceChild(state, card.querySelector(".cal-event__title"));
            /* Кнопка записи — только у свободного слота; у занятого
               (cal-event--booked) её в DOM нет вовсе (design.md D4). */
            if (!data.booked) {
              var book = document.createElement("button");
              book.type = "button";
              book.className = "cal-event__book";
              book.textContent = "Записаться";
              card.appendChild(book);
            } else {
              card.classList.add("cal-event--booked");
              card.querySelector(".cal-event__state").textContent =
                "Занят: " + data.bookedBy;
            }
            /* У слота цены нет — второй строкой остаётся только время. */
            if (price) price.remove();
          } else {
            card.className = "cal-event";
            card.querySelector(".cal-event__title").textContent = data.title;
            if (price) price.textContent = data.priceLabel || "";
          }
          card.querySelector(".cal-event__time").textContent =
            formatClock(data.startMin) + " – " + formatClock(data.startMin + data.duration);
          card.style.setProperty("--top", ((data.startMin - GRID_START_MIN) / 60).toString());
          card.style.setProperty("--dur", (data.duration / 60).toString());
          card.style.setProperty("--accent", data.color || "#3b82f6");
          card.setAttribute("data-student", data.kind === "slot" ? "" : data.title);
          card.setAttribute("data-start-min", String(data.startMin));
          card.setAttribute("data-duration-min", String(data.duration));
          if (data.kind !== "slot") {
            this.setCardTitle(card, data.startMin, data.duration);
          }
          if (data.isGroup) {
            var tag = document.createElement("span");
            tag.className = "cal-event__tag";
            tag.textContent = "Группа";
            card.appendChild(tag);
          }
          return card;
        },

        /* Всплывающая подсказка карточки: имя цели, цена (если задана) и
           интервал времени — тот же текст, что у серверной карточки.
           Нужна потому, что в коротком уроке вторая строка скрыта
           контейнерным запросом (styles.css), и цена со временем читаются
           хотя бы в подсказке. После drag время меняется, поэтому подсказка
           пересобирается из уже обновлённых данных карточки. */
        setCardTitle: function (card, startMin, duration) {
          var name = card.querySelector(".cal-event__title");
          var price = card.querySelector(".cal-event__price");
          var parts = [];
          if (name && name.textContent.trim()) parts.push(name.textContent.trim());
          if (price && price.textContent.trim()) parts.push(price.textContent.trim());
          parts.push(
            formatClock(startMin) + " – " + formatClock(startMin + duration)
          );
          card.setAttribute("title", parts.join(" · "));
        },

        /* Раскладка наложения в столбце дня — та же логика, что на сервере
           (services/presentation.py layout_events): цепочка пересекающихся
           карточек делит ширину поровну, поэтому слот поверх демо-занятия
           не перекрывает его — видны обе карточки (спека «Слот поверх
           существующего занятия»). Вызывается после добавления слота. */
        layoutDay: function (day) {
          var cards = day.querySelectorAll(".cal-event");
          var items = [];
          for (var i = 0; i < cards.length; i++) {
            var start = parseInt(cards[i].getAttribute("data-start-min"), 10);
            var dur = parseInt(cards[i].getAttribute("data-duration-min"), 10);
            if (isNaN(start) || isNaN(dur)) continue;
            items.push({ card: cards[i], start: start, end: start + dur });
          }
          items.sort(function (a, b) {
            return a.start - b.start || a.end - b.end;
          });

          var cluster = [];
          var clusterEnd = null;
          var flush = function () {
            var total = cluster.length;
            for (var j = 0; j < total; j++) {
              cluster[j].card.style.setProperty("--left", (j * 100) / total + "%");
              cluster[j].card.style.setProperty("--width", 100 / total + "%");
            }
            cluster = [];
          };
          for (var k = 0; k < items.length; k++) {
            var item = items[k];
            if (cluster.length && clusterEnd !== null && item.start >= clusterEnd) {
              flush();
              clusterEnd = null;
            }
            cluster.push(item);
            clusterEnd = clusterEnd === null ? item.end : Math.max(clusterEnd, item.end);
          }
          if (cluster.length) flush();
        },

        /* ------------------------------------------------------------------
           Диалог записи на слот (спека slot-booking): открытие — только от
           карточки cal-event--slot без cal-event--booked, подтверждение
           помечает слот занятым. Всё в DOM, без сетевых запросов
           (design.md D4).
           ------------------------------------------------------------------ */

        /* Клик по карточке слота или её кнопке «Записаться» — диалог
           записи, а НЕ форма создания урока (спека «Клик по карточке
           слота»). Клики по карточкам уроков игнорируются. */
        onAreaClick: function (event) {
          if (!event.target.closest) return;
          var card = event.target.closest(".cal-event--slot");
          if (!card || !this.$root.contains(card)) return;
          event.stopPropagation();
          this.openBooking(card);
        },

        /* Клик после переноса гасится в capture-фазе (design.md D7):
           htmx слушает click на самой карточке и открыл бы форму
           редактирования. Флаг ставит `moveLesson`, снимает — следующий
           обычный жест или этот же обработчик. */
        onSuppressedClick: function (event) {
          if (!this._suppressClick) return;
          this._suppressClick = false;
          var card = event.target.closest && event.target.closest(".cal-event");
          if (!card || !this.$root.contains(card)) return;
          event.stopImmediatePropagation();
          event.preventDefault();
        },

        /* Открыть диалог записи: только свободный слот (без --booked);
           занятая карточка и чужой элемент игнорируются. */
        openBooking: function (el) {
          var card = el && el.closest ? el.closest(".cal-event--slot") : null;
          if (!card || !this.$root.contains(card)) return;
          if (card.classList.contains("cal-event--booked")) return;
          this._bookingSlot = card;
          this.booking.open = true;
        },

        /* Отмена/закрытие: слот остаётся свободным, поля сбрасываются. */
        closeBooking: function () {
          this.booking.open = false;
          this.booking.name = "";
          this.booking.contact = "";
          this._bookingSlot = null;
        },

        /* Подтверждение записи: preventDefault останавливает нативную
           отправку формы, required-поля не пропускают пустые значения.
           На карточку пишутся data-booked-by/data-contact, подпись
           «Занят: <имя>», класс cal-event--booked, контакт — в title;
           кнопка «Записаться» удаляется из DOM — повторная запись
           невозможна (design.md D4). */
        confirmBooking: function (event) {
          event.preventDefault();
          var card = this._bookingSlot;
          if (
            card &&
            card.classList.contains("cal-event--slot") &&
            !card.classList.contains("cal-event--booked")
          ) {
            var name = this.booking.name;
            card.classList.add("cal-event--booked");
            card.setAttribute("data-booked-by", name);
            card.setAttribute("data-contact", this.booking.contact);
            /* Контакт в title занятой карточки: репетитору есть как связаться. */
            card.setAttribute("title", name + " · " + this.booking.contact);
            var state = card.querySelector(".cal-event__state");
            if (state) state.textContent = "Занят: " + name;
            var book = card.querySelector(".cal-event__book");
            if (book && book.parentNode) book.parentNode.removeChild(book);
          }
          this.closeBooking();
        },

        /* ------------------------------------------------------------------
           Кнопки-заглушки панели (спека «Кнопки-заглушки ведут без битых
           ссылок»): без маршрутов на несуществующее, всё локально.
           ------------------------------------------------------------------ */

        /* Ссылка на текущую неделю: понедельник берётся из сетки, а не из
           корня — htmx при листании обновляет только область, корень со
           своими data-* остаётся от прошлой недели. Ссылка несёт активный
           режим раскраски, чтобы он открывался у получателя (design.md D5). */
        weekLink: function () {
          return location.origin + this.withColor(this.weekPath());
        },

        /* Понедельник видимой недели — из первой колонки сетки. */
        currentStart: function () {
          var day = this.$root.querySelector(".cal-day[data-date]");
          return day ? day.getAttribute("data-date") : "";
        },

        /* Подписка `lesson-saved` живёт на корне, который htmx не подменяет:
           после листания недели его hx-get надо перевести на видимую
           неделю, иначе сохранение урока вернёт старую (design.md D6).
           Режим раскраски в адресе сохраняется — перерисовка после
           сохранения не должна сбрасывать выбор (design.md D5). */
        syncWeekParam: function () {
          var start = this.currentStart();
          if (start) {
            this.$root.setAttribute("hx-get", this.withColor(this.weekPath()));
          }
        },

        /* «Ссылка на окна»: копирует ссылку и подтверждает тостом «демо».
           Без буфера обмена тост всё равно показывается — страница не
           ломается. */
        copyWeekLink: function () {
          var url = this.weekLink();
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).catch(function () {
              /* буфер недоступен (http/права) — тост уже показан */
            });
          }
          this.showToast("Демо: ссылка на неделю скопирована");
        },

        /* Тост подтверждений: сам гаснет, повторный вызов перезапускает. */
        showToast: function (text) {
          var self = this;
          this.toast.text = text;
          this.toast.open = true;
          clearTimeout(this._toastTimer);
          this._toastTimer = setTimeout(function () {
            self.toast.open = false;
          }, 2500);
        },

        /* ------------------------------------------------------------------
           Drag занятий (Pointer Events, design.md D5): порог 5 px отделяет
           клик от драга, дальше — setPointerCapture, transform на каждое
           движение (без ре-рендера), подсветка целевой четверти и снап к
           15 минутам при отпускании. Только DOM, без сетевых запросов.

           Ручной сценарий проверки в браузере (зафиксирован в tasks.md):
           перенос карточки среды в пятницу на 16:30; отпускание в 16:37
           округляется до 16:30.
           ------------------------------------------------------------------ */
        onEventPointerDown: function (event) {
          if (!event.target.closest) return;
          /* Слоты исключены из перетаскивания (спека slot-booking, вне
             объёма): жест по карточке .cal-event--slot не начинается,
             поэтому клик по кнопке «Записаться» никогда не
             интерпретируется как drag (design.md D3). Проведённый урок
             переносить нельзя (design.md D8) — карточка помечена
             `data-completed` и жест не начинается. */
          var slotCard = event.target.closest(".cal-event--slot");
          var card = event.target.closest(".cal-event");
          if (slotCard || !card || !this.$root.contains(card) || this._drag) return;
          if (card.hasAttribute("data-completed")) return;
          /* Новый жест снимает подавитель клика от прошлого переноса. */
          this._suppressClick = false;
          /* Слушатели жеста висят на document, а не на карточке: пока
             pointer capture не установлен, быстрый первый pointermove
             может пройти мимо карточки (курсор уже в другой колонке) —
             с document такой жест не теряется. */
          var self = this;
          this._drag = {
            card: card,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            moved: false,
            originMin: parseInt(card.getAttribute("data-start-min"), 10),
            duration: parseInt(card.getAttribute("data-duration-min"), 10) || 40,
            onMove: function (e) {
              self.onDragMove(e);
            },
            onUp: function (e) {
              self.onDragEnd(e);
            },
            onCancel: function (e) {
              self.onDragEnd(e, true);
            },
          };
          document.addEventListener("pointermove", this._drag.onMove);
          document.addEventListener("pointerup", this._drag.onUp);
          document.addEventListener("pointercancel", this._drag.onCancel);
        },

        onDragMove: function (event) {
          var drag = this._drag;
          if (!drag || event.pointerId !== drag.pointerId) return;
          var dx = event.clientX - drag.startX;
          var dy = event.clientY - drag.startY;
          if (!drag.moved) {
            /* Ниже порога — это ещё клик, ничего не делаем. */
            if (Math.sqrt(dx * dx + dy * dy) < DRAG_THRESHOLD_PX) return;
            drag.moved = true;
            drag.card.classList.add("cal-event--dragging");
            /* Все дальнейшие pointer-события идут в карточку, даже когда
               курсор уходит за её пределы или в другую колонку дня. */
            try {
              drag.card.setPointerCapture(drag.pointerId);
            } catch (e) {
              /* захват недоступен — драг работает через координаты */
            }
          }
          drag.card.style.transform =
            "translate(" + dx + "px, " + dy + "px)";
          this.highlightDropTarget(event.clientX, event.clientY);
        },

        onDragEnd: function (event, cancelled) {
          var drag = this._drag;
          this._drag = null;
          if (!drag) return;
          var card = drag.card;
          document.removeEventListener("pointermove", drag.onMove);
          document.removeEventListener("pointerup", drag.onUp);
          document.removeEventListener("pointercancel", drag.onCancel);
          this.clearDropHighlight();
          card.classList.remove("cal-event--dragging");
          card.style.transform = "";

          if (!drag.moved || cancelled || drag.originMin === null) return;

          /* День под курсором в момент отпускания. */
          var under = this.elementUnder(event.clientX, event.clientY, card);
          var day = under && under.closest && under.closest(".cal-day");
          /* Отпустили вне сетки — без изменений. */
          if (!day) return;

          /* Снап к четверти часа: начало берётся от слота под курсором
             (слот16:30 →16:30, курсор16:37 — тот же слот →16:30), а без
             слота (карточка другого урока под курсором) — геометрия дня
             с округлением вниз до границы четверти. Затем зажим в границы
             таймлайна. */
          var hourH = this.hourHeight();
          if (!hourH) return;
          var slot = under && under.closest && under.closest(".cal-slot");
          var slotMin = slot ? parseClock((slot.getAttribute("data-start") || "").slice(11, 16)) : null;
          var dayRect = day.getBoundingClientRect();
          var cursorMin = GRID_START_MIN + ((event.clientY - dayRect.top) / hourH) * 60;
          var newMin =
            slotMin !== null
              ? slotMin
              : Math.floor(cursorMin / STEP_MIN) * STEP_MIN;
          newMin = Math.max(
            GRID_START_MIN,
            Math.min(newMin, GRID_END_MIN - drag.duration)
          );

          card.setAttribute("data-date", day.getAttribute("data-date"));
          day.appendChild(card);          /* в конец — поверх слотов */
          card.setAttribute("data-start-min", String(newMin));
          card.style.setProperty("--top", ((newMin - GRID_START_MIN) / 60).toString());
          card.querySelector(".cal-event__time").textContent =
            formatClock(newMin) + " – " + formatClock(newMin + drag.duration);
          /* Подсказка содержит время — после переноса пересобираем её,
             иначе в ней остался бы старый интервал. */
          this.setCardTitle(card, newMin, drag.duration);

          /* Перенос сохраняется на сервере (design.md D8): только начало,
             остальные поля не трогаются. Ответ несёт `lesson-saved`, и
             подписка на корне перерисовывает неделю — DOM-правка выше
             нужна лишь чтобы не мигало до ответа. */
          this.moveLesson(card, newMin);
        },

        /* Сохранить новое время урока; демо-слоты и события без id урока
           на сервер не уходят (design.md D8). */
        moveLesson: function (card, startMin) {
          var lessonId = card.getAttribute("data-lesson-id") || "";
          if (!lessonId || !window.htmx) return;
          /* Клик, который браузер эмитит после pointerup, не должен
             открывать форму редактирования (design.md D7). */
          this._suppressClick = true;
          window.htmx.ajax("POST", "/tutor/lessons/" + lessonId + "/move", {
            values: {
              date: card.getAttribute("data-date"),
              time: formatClock(startMin),
            },
            swap: "none",
          });
        },

        /* Подсветка целевой четверти: перетаскиваемая карточка следует за
           курсором и мешала бы elementFromPoint — прячем её от hit-теста
           на время вызова (inline-правило сильнее CSS-класса). В
           onDragEnd сессия драга уже закрыта, поэтому карточка передаётся
           явно. */
        elementUnder: function (x, y, card) {
          if (!card) {
            var drag = this._drag;
            card = drag && drag.card;
          }
          if (card) card.style.pointerEvents = "none";
          var under = document.elementFromPoint(x, y);
          if (card) card.style.pointerEvents = "";
          return under;
        },

        highlightDropTarget: function (x, y) {
          var under = this.elementUnder(x, y);
          var slot = under && under.closest && under.closest(".cal-slot");
          if (this._dropSlot === slot) return;
          this.clearDropHighlight();
          if (slot) {
            slot.classList.add("cal-slot--drop");
            this._dropSlot = slot;
          }
        },

        clearDropHighlight: function () {
          if (this._dropSlot) {
            this._dropSlot.classList.remove("cal-slot--drop");
            this._dropSlot = null;
          }
        },

        /* Высота часовой строки сетки: --cal-hour-h из styles.css. */
        hourHeight: function () {
          var day = this.$root.querySelector(".cal-day");
          if (!day) return 0;
          return (
            parseFloat(
              getComputedStyle(day).getPropertyValue("--cal-hour-h")
            ) || 0
          );
        },
      };
    });
  });
})();
