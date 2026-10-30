/**
 * OpenTutorCRM — состояние диалога задачи и поля «Ученики» (Alpine.js).
 *
 * Здесь только клиентское состояние: открыт ли диалог, какие ученики уже
 * привязаны к задаче и подтверждение удаления. Данные приходят готовым
 * HTML и JSON в `data-`атрибутах, сохранение идёт через htmx; ни одной
 * бизнес-проверки в браузере нет — форма, этап и срок проверяет сервер.
 *
 * Поле «Привязать к ученику» — общий виджет `createPersonPicker`
 * (`picker.js`): то же поле используется в форме группы («Добавить
 * ученика»), поэтому список открывается по клику и выглядит одинаково.
 * Компонент поля — отдельный (`taskStudents`), а не часть модалки: методы
 * виджета ищут `data-options` в своей Alpine-области, и внутри модалки
 * они нашли бы чужие данные.
 *
 * Перетаскивание карточек между колонками доски — делегированные
 * HTML5 drag-события (см. блок DnD ниже): drop отправляет тот же
 * POST-маршрут этапа, что и меню карточки, поэтому порядок и момент
 * завершения считает сервер.
 *
 * Подключается только на странице задач и строго до `alpine.min.js`:
 * подписка на `alpine:init` должна сработать раньше обхода DOM.
 */
(function () {
  "use strict";

  function parseJson(value, fallback) {
    try {
      return JSON.parse(value || "");
    } catch (e) {
      return fallback;
    }
  }

  document.addEventListener("alpine:init", function () {
    /* Диалог задачи: приходит свопом уже открытым, закрытие гасит его и
       опустошает контейнер — следующий hx-get отрисует заново.

       Проверка `isConnected` обязательна: Alpine снимает слушатели с
       удалённого узла отложенно, и подписка уже выброшенного диалога
       успевает сработать на событии, которое htmx рассылает после
       подмены (та же ловушка, что у `slotDialog`). */
    Alpine.data("taskForm", function () {
      return {
        open: true,
        confirmingDelete: false,

        close: function () {
          if (!this.$root.isConnected) return;
          this.open = false;
          var modal = document.getElementById("modal");
          if (modal) modal.innerHTML = "";
        },
      };
    });

    /* Поле «Ученики» задачи: выбранные строки + общий список выбора.
       Уже выбранные исключаются из вариантов — повторный выбор создал бы
       дубль, а сервер отклонил бы форму. */
    Alpine.data("taskStudents", function () {
      return window.mergePersonPicker(
        window.createPersonPicker({
          searchFields: ["name"],
          exclude: function () {
            var chosen = {};
            this.selected.forEach(function (student) {
              chosen[student.id] = true;
            });
            return chosen;
          },
          choose: function (item) {
            this.addStudent(item);
          },
        }),
        {
          selected: [],

          init: function () {
            var rows = parseJson(this.$root.dataset.selected, []);
            this.selected = Array.isArray(rows) ? rows : [];
            this.initPicker();
          },

          addStudent: function (item) {
            if (!item || !item.id) return;
            var exists = this.selected.some(function (student) {
              return student.id === item.id;
            });
            if (exists) return;
            this.selected.push({ id: item.id, name: item.name });
          },

          removeStudent: function (student) {
            this.selected = this.selected.filter(function (item) {
              return item.id !== student.id;
            });
          },
        }
      );
    });
  });

  /* Перетаскивание карточек между колонками доски (HTML5 DnD).

     Слушатели висят на document один раз: доску перерисовывает htmx-
     партиал, и подписки на сами карточки пришлось бы восстанавливать
     после каждого свопа — делегирование переживает любой рендер.

     Drop не вводит нового серверного пути: он шлёт тот же POST
     `/{id}/stage`, что и меню карточки (`htmx.ajax`), поэтому момент
     завершения и порядок карточек остаются делом сервера. В браузере
     ни сортировки, ни бизнес-правил нет.

     На тач-экранах HTML5 DnD не срабатывает: там этап меняют через
     меню карточки, и оно остаётся единственным путём на телефоне. */
  var DRAGGING_CARD = "task-card--dragging";
  var DROP_COLUMN = "task-column__body--drop";

  /* Карточка, которую тащат сейчас. Флаг отличает перетаскивание своей
     карточки от чужого drag (выделенный текст) — на чужой доска не
     реагирует ни подсветкой, ни приёмом drop. */
  var draggingCard = null;

  function dropColumn(node) {
    return node && node.closest ? node.closest(".task-column__body") : null;
  }

  document.addEventListener("dragstart", function (event) {
    var card = event.target.closest ? event.target.closest(".task-card") : null;
    if (!card) return;
    draggingCard = card;
    event.dataTransfer.effectAllowed = "move";
    /* text/plain обязателен: Firefox не начинает drag без данных. */
    event.dataTransfer.setData("text/plain", card.dataset.taskId || "");
    /* Класс — в следующем кадре: иначе полупрозрачная карточка попала
       бы в снимок перетаскивания, который браузер снимает сразу. */
    requestAnimationFrame(function () {
      if (draggingCard === card) card.classList.add(DRAGGING_CARD);
    });
  });

  document.addEventListener("dragend", function () {
    draggingCard = null;
    var card = document.querySelector("." + DRAGGING_CARD);
    if (card) card.classList.remove(DRAGGING_CARD);
    Array.prototype.forEach.call(
      document.querySelectorAll("." + DROP_COLUMN),
      function (column) {
        column.classList.remove(DROP_COLUMN);
      }
    );
  });

  document.addEventListener("dragover", function (event) {
    if (!draggingCard) return;
    var column = dropColumn(event.target);
    if (!column) return;
    /* Без preventDefault браузер не выпустит событие drop. */
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    if (!column.classList.contains(DROP_COLUMN)) {
      column.classList.add(DROP_COLUMN);
    }
  });

  document.addEventListener("dragleave", function (event) {
    var column = dropColumn(event.target);
    /* Подсветку снимаем, только когда курсор покинул колонку целиком:
       переход между её карточками тоже шлёт dragleave (relatedTarget —
       элемент внутри колонки). */
    if (column && !column.contains(event.relatedTarget)) {
      column.classList.remove(DROP_COLUMN);
    }
  });

  document.addEventListener("drop", function (event) {
    if (!draggingCard) return;
    var column = dropColumn(event.target);
    if (!column) return;
    event.preventDefault();
    column.classList.remove(DROP_COLUMN);

    /* Брос в свою же колонку — не перенос: порядок внутри колонки
       считает сервер по сроку, карточки перетаскиванием не сортируются. */
    if (draggingCard.closest(".task-column__body") === column) return;

    var taskId = draggingCard.dataset.taskId;
    draggingCard = null;
    if (!taskId || !window.htmx) return;
    window.htmx.ajax(
      "POST",
      "/tutor/tasks/" + taskId + "/stage",
      { values: { stage: column.dataset.stage || "" }, swap: "none" }
    );
  });
})();
