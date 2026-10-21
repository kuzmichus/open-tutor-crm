/**
 * OpenTutorCRM — минимальный JS.
 * Только: мобильный off-canvas сайдбар, переключение темы, инициализация Lucide.
 */
(function () {
  "use strict";

  var THEME_KEY = "opentutorcrm:theme";
  var SIDEBAR_KEY = "opentutorcrm:sidebar-collapsed";
  var sidebar = document.querySelector(".sidebar");
  var overlay = document.querySelector(".overlay");
  var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  var desktop = window.matchMedia("(min-width: 1024px)");

  /* --- Тема ------------------------------------------------------------- */
  /* Переключатель — два сегмента (светлая/тёмная) с явным значением в
     `data-theme-toggle`. Источник истины для подсветки — класс .dark на
     <html>: CSS красит активный сегмент сам, поэтому состояние не зависит
     от порядка инициализации скриптов. Здесь только синхронизируем
     aria-pressed и запоминаем выбор. */
  function applyTheme(theme) {
    var isDark = theme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute(
        "aria-pressed",
        btn.getAttribute("data-theme-toggle") === theme ? "true" : "false"
      );
    });
  }

  var saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (e) {
    /* localStorage может быть недоступен (приватный режим) — используем light */
  }
  applyTheme(saved === "dark" ? "dark" : "light");

  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var theme = btn.getAttribute("data-theme-toggle") === "dark" ? "dark" : "light";
      applyTheme(theme);
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch (e) {
        /* noop */
      }
    });
  });

  /* --- Мобильный off-canvas --------------------------------------------- */
  function setSidebarOpen(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("is-open", open);
    if (overlay) overlay.classList.toggle("is-visible", open);
    document.body.style.overflow = open ? "hidden" : "";
  }

  document.querySelectorAll("[data-sidebar-open]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setSidebarOpen(true);
    });
  });

  if (overlay) {
    overlay.addEventListener("click", function () {
      setSidebarOpen(false);
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setSidebarOpen(false);
  });

  document.querySelectorAll(".sidebar a[href]").forEach(function (link) {
    link.addEventListener("click", function () {
      setSidebarOpen(false);
    });
  });

  /* --- Сворачивание сайдбара (десктоп) ---------------------------------- */
  function applyCollapsed(collapsed) {
    // Источник истины — класс на <html>: от него зависят и сайдбар, и отступ .main.
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
    if (sidebarToggle) {
      sidebarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      sidebarToggle.setAttribute(
        "aria-label",
        collapsed ? "Развернуть сайдбар" : "Свернуть сайдбар"
      );
    }
  }

  // Класс мог быть уже поставлен бутстрап-скриптом в <head>.
  var collapsed = document.documentElement.classList.contains("sidebar-collapsed");
  applyCollapsed(collapsed);

  function setCollapsed(value) {
    collapsed = value;
    applyCollapsed(collapsed);
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch (e) {
      /* noop */
    }
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      // На мобиле «язычок» закрывает off-canvas, на десктопе — сворачивает.
      if (desktop.matches) {
        setCollapsed(!collapsed);
      } else {
        setSidebarOpen(false);
      }
    });
  }

  /* --- HTMX: не переносить атрибуты при свопе ---------------------------- */
  /* htmx по умолчанию «устаканивает» class/style/width/height: после свопа
     он копирует их со старого элемента на новый с тем же id. Видимостью в
     проекте управляет Alpine (`x-show`), и перенос затирал выставленный им
     `style="display: none"`: на календаре меню «Цвет» и «⋮» после подмены
     недели оставались открытыми, а `x-show` больше не скрывал их, потому
     что менял только состояние. Список пуст — атрибуты остаются такими,
     какими их отрендерил сервер. */
  if (window.htmx) window.htmx.config.attributesToSettle = [];

  /* --- Lucide ----------------------------------------------------------- */
  /* Отрисовка иконок повторяется после каждого htmx-свопа: модалка формы и
     карточки приходят по сети уже после первого обхода страницы, и их иконки
     (<i data-lucide>) иначе остались бы пустыми. Тот же хелпер вызывает
     students.js при добавлении строки контакта (`window.renderIcons`). */
  function renderIcons() {
    if (typeof lucide === "undefined") return;
    lucide.createIcons({ attrs: { "stroke-width": 2 } });
  }
  window.renderIcons = renderIcons;
  renderIcons();
  document.addEventListener("htmx:afterSwap", renderIcons);
})();
