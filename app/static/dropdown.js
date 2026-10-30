/**
 * OpenTutorCRM — выпадающий список поверх вёрстки.
 *
 * Списки выбора (общий пикер `_person_picker.html`, селект цели урока,
 * селект часового пояса) не должны раздвигать форму: раскрытый список
 * накладывается на следующие поля, как обычный поповер.
 *
 * Абсолютного позиционирования мало: списки живут внутри прокручиваемого
 * тела модалки (`.modal-body { overflow-y: auto }`), и абсолютный потомок
 * обрезался бы её нижней границей. Поэтому рабочий режим — `position: fixed`
 * под полем; `fixed` не обрезается предками с `overflow`, если у них нет
 * `transform`/`perspective`/`filter` (в модалках проекта их нет).
 *
 * API:
 *   window.openDropdown(anchor, list)   — показать список у поля;
 *   window.closeDropdown(list)          — список скрыт, отслеживание снять;
 *   window.repositionDropdown(list)     — пересчитать позицию (список вырос).
 *
 * Позиция пересчитывается при прокрутке и изменении размера окна, а также
 * после htmx-свопа: список цели урока подгружает варианты уже открытым.
 */
(function () {
  "use strict";

  var GAP = 6;          /* зазор между полем и списком, px */
  var EDGE = 8;         /* минимальный отступ от краёв экрана, px */
  var MIN_HEIGHT = 120; /* ниже этого список не ужимаем, px */
  var MAX_HEIGHT = 260; /* совпадает с `max-height` в styles.css */

  /* Открытые списки: [{anchor, list}]. Закрытые снимаются сразу, чтобы
     прокрутка не пересчитывала невидимые элементы. */
  var active = [];
  var frame = 0;

  function stateOf(list) {
    for (var i = 0; i < active.length; i++) {
      if (active[i].list === list) return active[i];
    }
    return null;
  }

  function viewportWidth() {
    return document.documentElement.clientWidth || window.innerWidth;
  }

  function viewportHeight() {
    return document.documentElement.clientHeight || window.innerHeight;
  }

  function resetStyles(list) {
    list.style.position = "";
    list.style.top = "";
    list.style.left = "";
    list.style.right = "";
    list.style.width = "";
    list.style.maxHeight = "";
    list.style.visibility = "";
  }

  function place(state) {
    var anchor = state.anchor;
    var list = state.list;

    /* Модалку или поле убрали из DOM, пока список был открыт. */
    if (!anchor || !list || !anchor.isConnected || !list.isConnected) {
      return;
    }

    var rect = anchor.getBoundingClientRect();
    var vw = viewportWidth();
    var vh = viewportHeight();

    /* Ширина — как у поля, но не шире экрана. */
    var width = Math.min(rect.width, vw - EDGE * 2);
    list.style.position = "fixed";
    list.style.right = "auto";
    list.style.width = Math.max(width, 0) + "px";
    list.style.left =
      Math.max(EDGE, Math.min(rect.left, vw - width - EDGE)) + "px";

    /* Поле уехало за пределы экрана — не оставляем список висеть. */
    if (rect.bottom < 0 || rect.top > vh) {
      list.style.visibility = "hidden";
      return;
    }
    list.style.visibility = "";

    var below = vh - rect.bottom - GAP - EDGE;
    var above = rect.top - GAP - EDGE;

    /* Список не должен вылезать за экран: высоту ограничиваем свободным
       местом с той стороны, куда он раскроется. */
    list.style.maxHeight =
      Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, Math.max(below, above))) + "px";

    var height = list.offsetHeight;

    /* Снизу места меньше, чем сверху, — раскрываем вверх, к полю. */
    if (height > below && above > below) {
      list.style.top = Math.max(EDGE, rect.top - GAP - height) + "px";
    } else {
      list.style.top = rect.bottom + GAP + "px";
    }
  }

  /* Пересчёт — не чаще кадра: прокрутка шлёт события пачками. */
  function schedule() {
    if (!active.length || frame) return;
    frame = window.requestAnimationFrame(function () {
      frame = 0;
      active = active.filter(function (state) {
        return state.anchor.isConnected && state.list.isConnected;
      });
      active.forEach(place);
    });
  }

  window.openDropdown = function (anchor, list) {
    if (!anchor || !list) return;
    var state = stateOf(list);
    if (state) {
      state.anchor = anchor;
    } else {
      active.push({ anchor: anchor, list: list });
    }
    /* Первый замер — сразу: список уже показан Alpine (`x-show`). */
    place(stateOf(list));
  };

  window.closeDropdown = function (list) {
    if (!list) return;
    active = active.filter(function (state) {
      return state.list !== list;
    });
    resetStyles(list);
  };

  window.repositionDropdown = function (list) {
    var state = stateOf(list);
    if (state) place(state);
  };

  window.addEventListener("scroll", schedule, true);
  window.addEventListener("resize", schedule);
  /* Варианты цели урока приходят htmx-свопом уже в открытый список:
     после свопа высота другая — позицию надо пересчитать. */
  document.addEventListener("htmx:afterSettle", schedule);
})();
