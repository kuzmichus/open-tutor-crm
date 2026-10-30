/**
 * OpenTutorCRM — фокус-ловушка модальных диалогов.
 *
 * Все диалоги приходят htmx-свопом в контейнеры `#modal`, `#modal-lesson`,
 * `#modal-payment`, `#modal-expense` и закрываются Alpine'ом, который
 * просто очищает контейнер. Поэтому ловушка живёт не в компоненте каждой
 * формы, а здесь — одним наблюдателем за DOM: она работает и для диалогов,
 * которых ещё нет на странице, и для вложенных слоёв (счёт поверх карточки
 * ученика, design D10).
 *
 * Зачем это нужно. `role="dialog"` + `aria-modal="true"` — обещание
 * ассистивным технологиям, что за пределами диалога ничего нет. Без
 * изоляции фона обещание ложное: первый же Tab уводил из открытой формы
 * в карточки учеников под оверлеем, а скринридер продолжал читать страницу.
 *
 * Что делает модуль:
 *   1. находит верхний открытый диалог (по z-index слоя, затем по порядку
 *      в документе — так вложенный слой всегда выигрывает у нижнего);
 *   2. делает `inert` всё, что лежит рядом с диалогом на каждом уровне
 *      вложенности: и соседние модалки, и содержимое страницы, и сайдбар;
 *   3. зацикливает Tab/Shift+Tab внутри диалога;
 *   4. запоминает элемент, с которого диалог открыли, и возвращает на него
 *      фокус после закрытия.
 */
(function () {
  "use strict";

  var FOCUSABLE = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled]):not([type='hidden'])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");

  /* Элементы, которым мы сами поставили `inert`. Список, а не атрибут
     `[inert]` в селекторе: на странице могут быть свои inert-элементы
     (например, отключённый блок), и снимать чужое нельзя. */
  var inerted = [];
  var activeDialog = null;
  var returnFocusTo = null;

  function isVisible(element) {
    /* `offsetParent` не годится: у `position: fixed` он всегда null.
       Есть ли у элемента хоть один прямоугольник — вопрос без подвоха. */
    return element.getClientRects().length > 0;
  }

  function layerZIndex(dialog) {
    var layer = dialog.closest(".modal-root");
    if (!layer) return 0;
    var value = parseInt(window.getComputedStyle(layer).zIndex, 10);
    return isNaN(value) ? 0 : value;
  }

  /* Верхний слой: наибольший z-index, при равенстве — последний в DOM.
     Диалоги стека объявлены после `#modal`, поэтому порядок совпадает
     с порядком открытия. */
  function topDialog() {
    var dialogs = document.querySelectorAll(".modal-content[role='dialog']");
    var best = null;
    var bestZ = -Infinity;
    Array.prototype.forEach.call(dialogs, function (dialog) {
      if (!isVisible(dialog)) return;
      var z = layerZIndex(dialog);
      if (z >= bestZ) {
        bestZ = z;
        best = dialog;
      }
    });
    return best;
  }

  function focusables(dialog) {
    return Array.prototype.filter.call(
      dialog.querySelectorAll(FOCUSABLE),
      function (element) {
        return isVisible(element) && element.tabIndex !== -1;
      }
    );
  }

  function markInert(element) {
    if (!element || element.hasAttribute("inert")) return;
    element.setAttribute("inert", "");
    inerted.push(element);
  }

  function clearInert() {
    inerted.forEach(function (element) {
      element.removeAttribute("inert");
    });
    inerted = [];
  }

  /* Изоляция фона по цепочке предков: на каждом уровне всё, что не ведёт
     к диалогу, становится inert. Именно по цепочке, а не только по детям
     `body`: контейнер `#modal` лежит внутри `.main`, и если гасить лишь
     соседей body, карточки учеников внутри `.main` останутся доступны —
     это и был исходный дефект. */
  function isolate(dialog) {
    clearInert();
    var node = dialog;
    while (node && node !== document.body && node.parentElement) {
      var parent = node.parentElement;
      Array.prototype.forEach.call(parent.children, function (sibling) {
        if (sibling !== node) markInert(sibling);
      });
      node = parent;
    }
  }

  function activate(dialog) {
    activeDialog = dialog;
    if (!dialog.hasAttribute("tabindex")) dialog.setAttribute("tabindex", "-1");
    isolate(dialog);

    /* Фокус уже внутри (сервер поставил `autofocus`, или пользователь
       кликнул по полю) — не перебиваем: иначе каретка прыгнет из поля,
       в которое человек только что попал. */
    if (dialog.contains(document.activeElement)) return;

    var autofocus = dialog.querySelector("[autofocus]");
    var target = autofocus || focusables(dialog)[0] || dialog;
    if (target && typeof target.focus === "function") {
      /* preventScroll: диалог уже по центру, а прокрутка к первому полю
         дёргала бы страницу под оверлеем. */
      target.focus({ preventScroll: true });
    }
  }

  function deactivate() {
    activeDialog = null;
    clearInert();
    var target = returnFocusTo;
    returnFocusTo = null;
    if (target && target.isConnected && typeof target.focus === "function") {
      target.focus({ preventScroll: true });
    }
  }

  function sync() {
    var dialog = topDialog();
    if (dialog === activeDialog) return;
    if (dialog) {
      /* Запоминаем точку возврата только при первом открытии: при
         переключении между слоями фокус возвращается туда же, откуда
         всё началось. */
      if (!activeDialog) returnFocusTo = document.activeElement;
      activate(dialog);
    } else {
      deactivate();
    }
  }

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Tab" || !activeDialog) return;
    var items = focusables(activeDialog);
    if (!items.length) {
      event.preventDefault();
      activeDialog.focus({ preventScroll: true });
      return;
    }
    var first = items[0];
    var last = items[items.length - 1];
    var current = document.activeElement;

    /* Фокус вне диалога (успел уйти до изоляции) — возвращаем внутрь. */
    if (!activeDialog.contains(current)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus({ preventScroll: true });
      return;
    }
    if (event.shiftKey && current === first) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!event.shiftKey && current === last) {
      event.preventDefault();
      first.focus({ preventScroll: true });
    }
  });

  /* Наблюдаем за всем документом: диалоги появляются свопом htmx в разные
     контейнеры и исчезают очисткой контейнера — единого события на оба
     случая нет. `subtree` обязателен, иначе подмена внутри `#modal` не
     видна. */
  new MutationObserver(sync).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style"],
  });

  document.addEventListener("htmx:afterSwap", sync);
  document.addEventListener("DOMContentLoaded", sync);
  sync();
})();
