/**
 * OpenTutorCRM — обратная связь при остановленной отправке формы.
 *
 * Проблема. Поля кабинета обязательные (`required`), а отправляет форму
 * htmx. Когда браузерная валидация не пропускает отправку, до сервера
 * запрос не доходит — значит и серверный блок `.error[role=alert]` не
 * приходит: его не у кого просить. Со стороны это выглядит так: человек
 * нажал «Сохранить», модалка осталась открытой, ничего не произошло и
 * никто ничего не сказал.
 *
 * Хуже в форме с вкладками: невалидное поле может лежать в скрытой панели.
 * Браузер в этом случае вообще не может показать пузырёк — он пишет в
 * консоль «An invalid form control … is not focusable» и молчит.
 *
 * Три сценария, поэтому три обработчика:
 *   1. `invalid` на полях (событие не всплывает — слушаем в фазе
 *      перехвата). Приходит и тогда, когда отправку заблокировал сам
 *      браузер, то есть до htmx. Помечаем поля `aria-invalid`, показываем
 *      сводку и раскрываем вкладку с первым невалидным полем.
 *   2. `htmx:validation:halted` — случай вкладок с `hx-include`: своя
 *      форма валидна, а невалидное поле приехало из соседней, и htmx
 *      останавливает запрос сам.
 *   3. `input` / `change` / `htmx:beforeRequest` — снимаем устаревшее:
 *      как только человек начал править поле, старая сводка врёт.
 *
 * Почему один общий модуль, а не метод в каждой Alpine-фабрике: форм с
 * обязательными полями больше десятка (ученик, группа, урок, окно, счёт,
 * расход, задача, настройки), и все они ходят через один и тот же htmx.
 * Домен здесь ни при чём — это поведение веб-слоя.
 */
(function () {
  "use strict";

  var SUMMARY_ATTR = "data-form-feedback";
  var SUMMARY_PREFIX = "form-feedback-summary";
  /* Сколько ждём остальные `invalid`: браузер шлёт их по одному на каждое
     невалидное поле подряд, и сводка должна собрать все, а не первую. */
  var COLLECT_DELAY = 0;

  var pending = new WeakMap();
  var timers = new WeakMap();
  var summarySeq = 0;

  function isVisible(element) {
    return !!element && element.getClientRects().length > 0;
  }

  /* Диалог, в котором лежит форма: сводка и пометки живут в рамках одного
     слоя, а не одной формы. Форм в модалке несколько (вкладки ученика —
     отдельные `<form>`), и сообщение, оставшееся в скрытой панели, человек
     не увидит. Вне диалога (страница целиком) область — сама форма. */
  function scopeOf(form) {
    return form.closest("[role='dialog']") || form;
  }

  /* Куда положить сводку: в тело панели, где лежит первое видимое
     невалидное поле. В модалке ученика у каждой вкладки своё тело, и только
     в нём сообщение попадает в прокручиваемую область рядом с полем. */
  function summaryHost(form, target) {
    var body = (target && target.closest(".modal-body")) || form.querySelector(".modal-body");
    return body || form;
  }

  function summaryFor(host, scope) {
    var existing = scope.querySelector("[" + SUMMARY_ATTR + "]");
    if (existing) {
      /* Сводка уже есть — переезжает в новую панель, а не дублируется. */
      if (existing.parentNode !== host) host.insertBefore(existing, host.firstChild);
      return existing;
    }

    var summary = document.createElement("div");
    summary.className = "error";
    summary.setAttribute("role", "alert");
    summary.setAttribute(SUMMARY_ATTR, "");
    /* Идентификатор свой у каждого слоя: вложенные модалки живут в одном
       документе, и общий id сломал бы `aria-describedby`. */
    summary.id = SUMMARY_PREFIX + "-" + (summarySeq += 1);
    summary.appendChild(document.createElement("ul"));
    host.insertBefore(summary, host.firstChild);
    return summary;
  }

  function markInvalid(field) {
    if (!field || !field.setAttribute) return;
    field.setAttribute("aria-invalid", "true");
  }

  /* Ссылка на сводку ставится после её создания: id известен только тогда. */
  function linkSummary(field, summaryId) {
    if (!field || !field.setAttribute || !summaryId) return;
    var described = (field.getAttribute("aria-describedby") || "").split(/\s+/);
    if (described.indexOf(summaryId) === -1) {
      described.push(summaryId);
      field.setAttribute("aria-describedby", described.join(" ").trim());
    }
  }

  function clearFeedback(form) {
    var scope = scopeOf(form);
    var summary = scope.querySelector("[" + SUMMARY_ATTR + "]");
    var summaryId = summary ? summary.id : null;
    if (summary) summary.remove();

    Array.prototype.forEach.call(
      scope.querySelectorAll("[aria-invalid='true']"),
      function (field) {
        field.removeAttribute("aria-invalid");
        if (!summaryId) return;
        var kept = (field.getAttribute("aria-describedby") || "")
          .split(/\s+/)
          .filter(function (id) {
            return id && id !== summaryId;
          })
          .join(" ");
        if (kept) field.setAttribute("aria-describedby", kept);
        else field.removeAttribute("aria-describedby");
      }
    );
  }

  /* Первое поле, до которого человек реально может дотянуться: у формы с
     вкладками невалидное поле вполне может лежать в скрытой панели —
     фокус туда уводить нельзя, пока панель не раскрыта. */
  function firstReachable(errors) {
    for (var index = 0; index < errors.length; index += 1) {
      if (isVisible(errors[index].elt)) return errors[index].elt;
    }
    return null;
  }

  /* Панель раскрывается тем же табом, что её открывает: у `[data-tab-panel]`
     есть `aria-labelledby` на кнопку вкладки — так устроены и форма ученика
     (три отдельных `<form>`), и форма группы (одна форма на пять панелей).
     Клик чистый: Alpine меняет только `tab`, содержимое панелей не
     перезагружается. Возвращает true, если вкладку пришлось переключить. */
  function revealPanel(field) {
    var panel = field.closest("[data-tab-panel]");
    if (!panel || isVisible(field)) return false;
    var tabId = panel.getAttribute("aria-labelledby");
    var tab = tabId ? document.getElementById(tabId) : null;
    if (!tab || tab.getAttribute("role") !== "tab") return false;
    tab.click();
    return true;
  }

  function showFeedback(form, errors) {
    /* Одинаковые сообщения не дублируем: у двух пустых полей браузер
       скажет одно и то же, и список из двух одинаковых строк читается
       как сбой, а не как две проблемы. */
    var messages = [];
    var seen = {};
    errors.forEach(function (error) {
      var message = (error.message || "").trim();
      if (!message || seen[message]) return;
      seen[message] = true;
      messages.push(message);
    });

    errors.forEach(function (error) {
      markInvalid(error.elt);
    });

    /* Сначала вкладка, потом сводка и фокус: раскрытие применяется
       Alpine'ом в микрозадаче, поэтому всё остальное — следующим тиком. */
    errors.some(function (error) {
      return revealPanel(error.elt);
    });

    setTimeout(function () {
      var target = firstReachable(errors);
      var summary = null;

      if (messages.length) {
        summary = summaryFor(summaryHost(form, target), scopeOf(form));
        var list = summary.querySelector("ul");
        list.textContent = "";
        messages.forEach(function (message) {
          var item = document.createElement("li");
          item.textContent = message;
          list.appendChild(item);
        });
        errors.forEach(function (error) {
          linkSummary(error.elt, summary.id);
        });
      }

      if (!target) {
        /* Все невалидные поля остались в скрытых панелях: показать сводку
           всё равно нужно, иначе нажатие «Сохранить» снова останется
           без ответа. */
        if (summary) summary.scrollIntoView({ block: "nearest" });
        return;
      }

      setTimeout(function () {
        if (!isVisible(target)) return;
        try {
          target.focus({ preventScroll: false });
        } catch (error) {
          /* Поле исчезло из DOM (своп) — фокус уже не нужен. */
        }
        if (summary) summary.scrollIntoView({ block: "nearest" });
      }, 0);
    }, COLLECT_DELAY);
  }

  /* Браузер шлёт `invalid` по одному на каждое невалидное поле, поэтому
     копим их и показываем сводку одним заходом. */
  function collect(form, error) {
    var errors = pending.get(form) || [];
    if (error.elt && errors.some(function (item) { return item.elt === error.elt; })) {
      return;
    }
    errors.push(error);
    pending.set(form, errors);

    if (timers.has(form)) return;
    timers.set(
      form,
      setTimeout(function () {
        timers.delete(form);
        var collected = pending.get(form) || [];
        pending.delete(form);
        if (collected.length) showFeedback(form, collected);
      }, COLLECT_DELAY)
    );
  }

  /* `invalid` не всплывает — только перехват на документе его поймает. */
  document.addEventListener(
    "invalid",
    function (event) {
      var field = event.target;
      var form = field && field.form;
      if (!form) return;
      markInvalid(field);
      collect(form, {
        elt: field,
        message: field.validationMessage || "",
      });
    },
    true
  );

  document.addEventListener("htmx:validation:halted", function (event) {
    var detail = event.detail || {};
    var elt = detail.elt;
    /* htmx кладёт в detail элемент, на котором сорвалась отправка: для
       формы это она сама, для кнопки — сама кнопка. Нужна именно форма:
       сводка живёт в ней. */
    var form = elt && (elt.tagName === "FORM" ? elt : elt.closest("form"));
    var errors = detail.errors || [];
    if (!form || !errors.length) return;
    errors.forEach(function (error) {
      markInvalid(error.elt);
    });
    showFeedback(form, errors);
  });

  /* Сводка живёт до следующей попытки: как только человек поправил поле
     или запрос всё-таки ушёл, старое сообщение врёт. `input` слушаем в
     фазе перехвата — из некоторых полей он не всплывает одинаково во всех
     браузерах. */
  function clearFor(target) {
    var form = target && target.closest && target.closest("form");
    if (!form) return;
    pending.delete(form);
    var timer = timers.get(form);
    if (timer) {
      clearTimeout(timer);
      timers.delete(form);
    }
    clearFeedback(form);
  }

  document.addEventListener(
    "input",
    function (event) {
      clearFor(event.target);
    },
    true
  );
  document.addEventListener("change", function (event) {
    clearFor(event.target);
  });
  document.addEventListener("htmx:beforeRequest", function (event) {
    var elt = event.detail && event.detail.elt;
    clearFor(elt);
  });
})();
