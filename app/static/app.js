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
  function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }

  var saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (e) {
    /* localStorage может быть недоступен (приватный режим) — используем light */
  }
  if (saved === "dark" || saved === "light") applyTheme(saved);

  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var isDark = document.documentElement.classList.toggle("dark");
      try {
        localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
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
