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

  /* Части локального момента педагога из `data-now` на #calendar-swap.

     Разбираем строку ISO компонентами, а не через `new Date()`: `getHours()`
     отдал бы час в зоне устройства, и предзаполнение снова разошлось бы с
     сервером (design.md D7). Значение приходит уже в зоне педагога, поэтому
     `getFullYear/getMonth/...` не нужны. Если атрибута нет или строка кривая —
     падаем на часы устройства (как раньше), чтобы разметка не ломалась. */
  function serverNowParts() {
    var root = document.getElementById("calendar-swap");
    var raw = root ? (root.getAttribute("data-now") || "") : "";
    var match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(raw);
    if (!match) {
      var now = new Date();
      return {
        year: now.getFullYear(),
        month: now.getMonth() + 1,
        day: now.getDate(),
        hours: now.getHours(),
        minutes: now.getMinutes()
      };
    }
    return {
      year: parseInt(match[1], 10),
      month: parseInt(match[2], 10),
      day: parseInt(match[3], 10),
      hours: parseInt(match[4], 10),
      minutes: parseInt(match[5], 10)
    };
  }

  /* «2026-10-19» — сегодняшняя дата педагога в формате ISO. */
  function todayIso() {
    var parts = serverNowParts();
    var m = parts.month;
    var d = parts.day;
    return (
      parts.year +
      "-" +
      (m < 10 ? "0" : "") + m +
      "-" +
      (d < 10 ? "0" : "") + d
    );
  }

  /* «Успешно сохранено» панели недоступности (design.md D8): сервер отдаёт
     кнопку зелёной и неактивной, через пару секунд возвращаем ей обычный
     вид и надпись «Добавить» — иначе панель нельзя было бы использовать
     повторно без перезагрузки. Таймер вешаем на узел, пришедший свопом:
     следующее сохранение подменяет кнопку, и таймер старого узла уже ни на
     что не влияет (тот же приём, что у кнопки «Сохранить ДЗ»). */
  var UN_SUCCESS_MS = 2000;
  var UN_IDLE_LABEL = "Добавить";

  function restoreUnavailabilityButton(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var buttons = scope.querySelectorAll("[data-un-save]");
    Array.prototype.forEach.call(buttons, function (button) {
      if (!button.disabled) return;
      setTimeout(function () {
        if (!button.isConnected) return;
        button.disabled = false;
        button.classList.remove("btn--success");
        button.classList.add("btn--primary");
        button.textContent = UN_IDLE_LABEL;
      }, UN_SUCCESS_MS);
    });
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    restoreUnavailabilityButton(event.target);
  });

  document.addEventListener("alpine:init", function () {
    /* Панель «Отпуск и выходные» (спека tutor-unavailability): переключение
       режима «Период» / «Постоянный выходной». `template x-if` в шаблоне
       убирает поля другого режима из DOM, поэтому в запрос уходят только
       поля выбранного режима. Панель открывается в #modal уже отрисованной,
       поэтому `open` сразу true — закрытие гасит её и опустошает контейнер
       через htmx (следующий hx-get отрисует панель заново). */
    Alpine.data("unavailabilityPanel", function (initialMode) {
      return {
        open: true,
        mode: initialMode === "weekday" ? "weekday" : "period",

        close: function () {
          this.open = false;
          var modal = document.getElementById("modal");
          if (modal) modal.innerHTML = "";
        },
      };
    });

    Alpine.data("calendarGrid", function () {
      return {
        /* Подсказка времени четверти: текст и позиция чипа в сетке. */
        hoverTime: null,
        hoverX: 0,
        hoverY: 0,

        /* Адрес формы создания урока — из `data-lesson-new` корня
           (design.md D9): её открывают клик по четверти и «Добавить». */
        lessonNewUrl: "/tutor/lessons/new",
        /* Подавитель клика после drag (design.md D7): браузер эмитит click
           после pointerup, и без флага перенос открывал бы форму урока. */
        _suppressClick: false,
        /* Выпадающий список «Цвет», меню быстрого добавления «⋮» и тост
           подтверждений. */
        colorOpen: false,
        moreOpen: false,
        toast: { open: false, text: "" },
        /* Показ публичной ссылки, когда буфер обмена недоступен: адрес
           остаётся в поле, пока пользователь не скопирует его вручную
           (спека calendar, «Буфер обмена недоступен»). */
        linkFallback: { open: false, url: "" },
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
          /* День с отметкой недоступности: спрашиваем подтверждение, но
             форму не блокируем (спека calendar, «Клик по отмеченному дню»).
             Причину читаем из `data-unavailable` — её посчитал сервер,
             математики в JS нет (design.md D5). Подтверждение передаётся
             в форму как `ack_unavailable=1`: сервер проверит снова, но
             второй раз уже не спросит (D5, п. 4). */
          var day = el.closest(".cal-day");
          var reason = this.unavailableReason(day);
          if (reason && !window.confirm(this.unavailableQuestion(reason))) {
            return;
          }
          this.openLessonForm(data.date, data.time, reason ? "1" : "");
        },

        /* Причина недоступности дня из `data-unavailable` ("" — день доступен). */
        unavailableReason: function (day) {
          if (!day || !day.getAttribute) return "";
          return (day.getAttribute("data-unavailable") || "").trim();
        },

        /* Текст подтверждения — тот же, что в серверном баннере формы. */
        unavailableQuestion: function (reason) {
          return (
            "День отмечен как недоступный: " + reason + ". " +
            "Всё равно поставить урок?"
          );
        },

        /* Форма создания урока в контейнере #modal: `?starts_at=` заполняет
           «Начало» (спека lesson-management «Префилл из календаря»), а
           `?ack_unavailable=1` говорит серверу, что подтверждение уже
           получено. Запрос шлёт htmx — форма со страницы Уроков сама
           закрывается по `lesson-saved` (design.md D6/D9). */
        openLessonForm: function (date, time, ack) {
          var url = this.lessonNewUrl;
          if (!date || !time) return;
          var query = "?starts_at=" + date + "T" + time;
          if (ack) query += "&ack_unavailable=" + ack;
          window.htmx.ajax("GET", url + query, {
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
          /* Момент с сервера (`data-now`), а не часы устройства (design.md D7). */
          var parts = serverNowParts();
          var minutes = parts.hours * 60 + parts.minutes;
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
           Меню быстрого добавления «⋮» (спека calendar): повторный клик,
           клик вне меню и Escape закрывают меню — сам toggleMore и
           атрибуты разметки (@click.outside, @keydown.escape.window).
           ------------------------------------------------------------------ */
        toggleMore: function () {
          this.moreOpen = !this.moreOpen;
        },

        closeMore: function () {
          this.moreOpen = false;
        },

        /* ------------------------------------------------------------------
           Демо-слой удалён: окна и записи живут в БД. Окно открывается
           серверным диалогом `slot/_dialog.html` (hx-get из пункта меню и
           с карточки окна), запись приходит с публичной страницы. Клиент
           больше не создаёт карточки и не рисует диалогов сам.
           ------------------------------------------------------------------ */

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

        /* ------------------------------------------------------------------
           «Ссылка на окна»: копирование публичного адреса недели (design D7).
           ------------------------------------------------------------------ */

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

        /* База публичной ссылки из корня: `/s/<tutor_id>`.
           Корень (`#calendar-swap`) htmx не подменяет, поэтому `data-public-url`
           переживает листание недель; понедельник берётся из видимой сетки. */
        publicBase: function () {
          var root = this.$root;
          return (root.dataset && root.dataset.publicUrl) || "";
        },

        /* Публичный адрес просматриваемой недели: `/s/<tutor_id>?start=<пн>`.

           Неделя — из первой колонки сетки, а не из корня: htmx при листании
           обновляет только область, `data-*` корня остаются от прошлой недели.
           Режим раскраски в публичную ссылку не входит — ученику он не нужен
           и в его интерфейсе ничего не меняет. */
        publicWeekUrl: function () {
          var base = this.publicBase();
          if (!base) return "";
          var start = this.currentStart();
          return location.origin + base + (start ? "?start=" + start : "");
        },

        /* Кнопка «Ссылка на окна»: копирует публичную ссылку недели.
           Буфер обмена доступен не всегда (http, права, старый браузер) —
           тогда ссылка показывается в поле рядом, чтобы её можно было
           скопировать вручную (спека calendar, «Буфер обмена недоступен»).
           Тост подтверждает только успешное копирование: обещать
           «скопировано», когда в буфере пусто, — хуже, чем не обещать. */
        copyWeekLink: function () {
          var self = this;
          var url = this.publicWeekUrl();
          if (!url) return;

          var showFallback = function () {
            self.linkFallback.url = url;
            self.linkFallback.open = true;
            self.$nextTick(function () {
              var field = self.$refs.linkField;
              if (field) {
                field.focus();
                field.select();
              }
            });
          };

          if (!navigator.clipboard || !navigator.clipboard.writeText) {
            showFallback();
            return;
          }
          navigator.clipboard.writeText(url).then(
            function () {
              self.linkFallback.open = false;
              self.showToast("Ссылка на окна скопирована");
            },
            showFallback
          );
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

          /* Отметка недоступности: подтверждаем до любой правки DOM — при
             отказе карточка остаётся в исходном дне и с прежним временем
             (спека lesson-management, «Отказ от переноса»). Причину дал
             сервер в `data-unavailable`: математики в JS нет (design.md D5). */
          var reason = this.unavailableReason(day);
          if (reason && !window.confirm(this.unavailableQuestion(reason))) {
            return;
          }

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
             нужна лишь чтобы не мигало до ответа. `ack` передаётся, когда
             подтверждение в отмеченном дне уже получено. */
          this.moveLesson(card, newMin, reason ? "1" : "");
        },

        /* Сохранить новое время урока; демо-слоты и события без id урока
           на сервер не уходят (design.md D8). `ack` — признак того, что
           пользователь подтвердил постановку в отмеченный день: сервер
           проверит снова, но предупреждение повторно не покажет. */
        moveLesson: function (card, startMin, ack) {
          var lessonId = card.getAttribute("data-lesson-id") || "";
          if (!lessonId || !window.htmx) return;
          /* Клик, который браузер эмитит после pointerup, не должен
             открывать форму редактирования (design.md D7). */
          this._suppressClick = true;
          var values = {
            date: card.getAttribute("data-date"),
            time: formatClock(startMin),
          };
          if (ack) values.ack_unavailable = ack;
          window.htmx.ajax("POST", "/tutor/lessons/" + lessonId + "/move", {
            values: values,
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
