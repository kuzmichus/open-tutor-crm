/* Фабрики страницы «Коммуникации» (/tutor/mailings).

   mailingsPage — состояние формы рассылки: выбор учеников (чекбоксы
   партиала списка), текст сообщения, выбранный шаблон. Фабрика живёт на
   форме, общей для обеих колонок: партиалы списка и композера
   перерисовываются независимо (фильтры, отправка, обновление селекта
   шаблонов), а ввод не теряется. Сброс после успешной отправки — по
   событию `mailing-sent` (шлёт POST /tutor/mailings/send, слушатель на
   форме в mailing/_compose.html).

   mailingsDialog — модалки шаблонов (список, сохранение, правка): открыты
   с момента вставки в #modal, close() очищает контейнер (паттерн
   tasks.js). */

document.addEventListener("alpine:init", function () {
  Alpine.data("mailingsPage", function () {
    return {
      selected: [],
      text: "",
      chosenTemplate: "",

      init() {
        // Начальный текст кладёт сервер (ответ отправки с ошибкой формы):
        // читаем из data-атрибута формы, чтобы не экранировать в JS-коде.
        var initial = this.$root.dataset.text || "";
        if (initial) this.text = initial;
      },

      // Согласование дательного падежа: 1 пользователю, 11 пользователей,
      // 21 пользователю — но 2/5/22 пользователям.
      recipientsCountLabel: function (count) {
        var ending =
          count % 10 === 1 && count % 100 !== 11
            ? "пользователю"
            : "пользователям";
        return "Будет отправлено " + count + " " + ending;
      },

      // Подставляет текст выбранного шаблона. Текст берём из data-атрибута
      // опции (его рендерит сервер вместе со списком) — состояние фабрики
      // не может устареть после перерисовки селекта.
      applyTemplate: function () {
        if (!this.chosenTemplate) return;
        var select = this.$refs.templateSelect;
        var option =
          select && select.selectedOptions ? select.selectedOptions[0] : null;
        if (option && option.dataset.text) this.text = option.dataset.text;
        // Селект возвращается к подписи «Шаблон»: подстановка одноразовая.
        this.chosenTemplate = "";
      },

      // Вставляет подстановку в позицию курсора (или в конец, если поле
      // не в фокусе). Кнопки гасят mousedown, поэтому фокус и каретка
      // текстового поля не теряются между нажатием и кликом.
      insertToken: function (token) {
        var el = this.$refs.textArea;
        var value = this.text || "";
        var focused = el && el === document.activeElement;
        var start = focused ? el.selectionStart : value.length;
        var end = focused ? el.selectionEnd : value.length;
        this.text = value.slice(0, start) + token + value.slice(end);
        var caret = start + token.length;
        this.$nextTick(function () {
          if (!el) return;
          el.focus();
          el.setSelectionRange(caret, caret);
        });
      },
    };
  });

  Alpine.data("mailingsDialog", function () {
    return {
      open: true,
      close: function () {
        if (!this.$root.isConnected) return; // узел уже вынут из DOM
        this.open = false;
        var modal = document.getElementById("modal");
        if (modal) modal.innerHTML = "";
      },
    };
  });
});
