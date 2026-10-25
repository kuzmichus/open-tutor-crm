/**
 * OpenTutorCRM — состояние диалогов счёта ученика.
 *
 * Диалоги платежа, возврата и счёта за период живут во втором слое модалок
 * (`#modal-payment`, design D10): карточка ученика остаётся в `#modal` со
 * своими несохранёнными полями, а счёт открывается поверх неё.
 *
 * Здесь только клиентское состояние: открыт ли диалог и как его закрыть.
 * Все числа, остаток к возврату и текст счёта считает сервер — в браузере
 * нет ни одной денежной формулы.
 *
 * Подключается на страницах учеников до `alpine.min.js`: подписка на
 * `alpine:init` должна сработать раньше, чем Alpine начнёт обход DOM (тот
 * же паттерн, что у `students.js`).
 */
(function () {
  "use strict";

  /* Занят ли верхний слой модалок: в `#modal-payment` есть дети — значит
     поверх карточки ученика открыт диалог счёта. Нужно нижнему слою:
     Escape должен закрывать только верхний диалог, иначе одно нажатие
     закрывало бы сразу оба (design D10). */
  function stackedOpen() {
    var stack = document.getElementById("modal-payment");
    return !!(stack && stack.children.length > 0);
  }

  /* Общее поведение диалога счёта: приходит свопом уже открытым, закрытие
     гасит его и опустошает свой контейнер — следующий hx-get отрисует
     заново.

     Закрытие по событию сохранения подписано в шаблоне
     (`@payment-saved.window="close()"`), а не здесь: событие приходит на
     `body` уже после ответа, и диалог должен успеть отдать его панели
     платежей. */
  function dialogState(containerId) {
    return {
      open: true,

      close: function () {
        /* Устаревший компонент не трогает контейнер: Alpine снимает
           слушатели с удалённого узла отложенно, и подписка на событие
           уже выброшенного диалога успевает сработать после подмены
           (та же ловушка, что у `slotDialog`). */
        if (!this.$root.isConnected) return;
        this.open = false;
        var container = document.getElementById(containerId);
        if (container) container.innerHTML = "";
      },
    };
  }

  document.addEventListener("alpine:init", function () {
    Alpine.data("paymentDialog", function () {
      return dialogState("modal-payment");
    });

    /* Поле выбора ученика в диалоге «Доход» страницы финансов: список —
       общий `createPersonPicker` (picker.js), домен — только запомнить
       выбранного ученика для скрытого `student_id`. Исходные значения
       приходят в data-атрибутах: повторная отрисовка с ошибкой не
       сбрасывает выбор. */
    Alpine.data("incomeStudentPicker", function () {
      return window.mergePersonPicker(
        window.createPersonPicker({
          searchFields: ["name", "meta"],
          choose: function (item) {
            this.studentId = item.id;
            this.studentName = item.name;
          },
        }),
        {
          studentId: "",
          studentName: "",

          init: function () {
            this.studentId = this.$root.dataset.initialId || "";
            this.studentName = this.$root.dataset.initialName || "";
            this.initPicker();
          },

          clearStudent: function () {
            this.studentId = "";
            this.studentName = "";
          },
        }
      );
    });

    Alpine.data("refundDialog", function () {
      return dialogState("modal-payment");
    });

    /* Диалог «Расход» страницы финансов: отдельный контейнер
       `#modal-expense` — он независим от `#modal-payment`, поэтому
       открытие «Расхода» не затирает незакрытый диалог «Дохода».
       Закрытие по `expense-saved` подписано в шаблоне диалога. */
    Alpine.data("expenseDialog", function () {
      return dialogState("modal-expense");
    });

    Alpine.data("invoiceDialog", function () {
      var state = dialogState("modal-payment");
      state.toastOpen = false;
      state.toastText = "";

      /* Копирование готового текста счёта: текст собран сервером и лежит
         в `data-invoice-text`, браузер его только передаёт в буфер — ни
         одна сумма в JS не считается (design D13). */
      state.copyInvoice = function (el) {
        var self = this;
        var text = el.getAttribute("data-invoice-text") || "";

        function done() {
          self.toastText = "Текст счёта скопирован";
          self.toastOpen = true;
          clearTimeout(self._toastTimer);
          self._toastTimer = setTimeout(function () {
            self.toastOpen = false;
          }, 2500);
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done);
        } else {
          done();
        }
      };

      return state;
    });

    /* Признак занятого верхнего слоя доступен и из других фабрик
       (`students.js`): нижняя модалка спрашивает его перед закрытием. */
    window.paymentsStackedOpen = stackedOpen;
  });
})();
