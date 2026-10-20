/**
 * OpenTutorCRM — состояние форм групп (Alpine.js).
 *
 * Здесь только клиентское состояние: строки состава формы, список выбора
 * «Добавить ученика...», мини-форма создания ученика и подтверждение
 * удаления. Серверной логики нет — данные приходят готовым HTML и JSON
 * в `data-options`, сохранение идёт через htmx.
 *
 * Само поле выбора — общий виджет `createPersonPicker` (`picker.js`): то же
 * поле используется в форме ученика («Добавить контакт»), поэтому выглядит и
 * ведёт себя одинаково. Здесь — только правила группы: кто предлагается и
 * что делает выбор.
 *
 * Подключается только на странице групп и строго до `alpine.min.js`:
 * подписка на `alpine:init` должна сработать раньше обхода DOM (решение D5).
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

  /* Разбор ответа мини-формы: Alpine не может «подхватить» JSON из htmx-свопа
     сам, поэтому данные лежат в `data-`атрибутах фрагмента, а обработчик
     `htmx:afterSwap` передаёт их в активный компонент. */
  function readMemberUpdate(el) {
    if (!el || el.id !== "group-members-update") return null;
    return {
      member: parseJson(el.dataset.member, null),
      options: parseJson(el.dataset.options, []),
      error: el.dataset.error || "",
    };
  }

  /* Общее состояние блока состава: модалка создания и вкладка «Настройки»
     используют один и тот же компонент (задачи 4.4–4.6, 5.4).

     Поле «Добавить ученика» — общий виджет `createPersonPicker` (picker.js):
     список открывается сразу по клику, без ожидания ввода, и выглядит так же,
     как «Добавить контакт» в форме ученика. Здесь — только домен группы. */
  function memberFormState() {
    return window.mergePersonPicker(
      window.createPersonPicker({
        searchFields: ["name", "grade"],
        /* Уже выбранные исключаются: повторный выбор создал бы дубль. */
        exclude: function () {
          var chosen = {};
          this.members.forEach(function (member) {
            chosen[member.id] = true;
          });
          return chosen;
        },
        choose: function (item) {
          this.addMember(item);
        },
      }),
      {
        /* Текущий состав формы — из `data-members` (JSON экранируется
           шаблоном) либо пустой у формы создания. */
        members: [],
        /* id, убранных кнопкой «Убрать»: уходят скрытым полем
           `removed_members`, чтобы сервер исключил их из группы (D4). */
        removed: [],
        maxMembers: 10,

        /* Мини-форма создания ученика (D9). */
        miniOpen: false,
        miniError: "",

        initMembers: function () {
          this.members = parseJson(this.$root.dataset.members, []);
          if (!Array.isArray(this.members)) this.members = [];
          var root = this.$root.querySelector(".group-members");
          if (!root) return;
          this.initPicker(root);
          var max = parseInt(root.dataset.maxMembers || "10", 10);
          this.maxMembers = isNaN(max) ? 10 : max;
        },

        get isFull() {
          return this.members.length >= this.maxMembers;
        },

        get removedIds() {
          return this.removed.join(",");
        },

        addMember: function (item) {
          if (!item || this.isFull) return;
          var exists = this.members.some(function (member) {
            return member.id === item.id;
          });
          if (exists) return;
          this.members.push({
            id: item.id,
            name: item.name,
            grade: item.grade,
            joined: "",
            price: "",
          });
          // Вернувшийся в состав участник больше не «убран».
          this.removed = this.removed.filter(function (id) {
            return id !== item.id;
          });
        },

        removeMember: function (member) {
          this.members = this.members.filter(function (item) {
            return item.id !== member.id;
          });
          if (this.removed.indexOf(member.id) === -1) {
            this.removed.push(member.id);
          }
        },

        /* --- Мини-форма создания ученика (D9) --- */

        openMiniForm: function () {
          if (this.isFull) return;
          this.listOpen = false;
          this.miniError = "";
          this.miniOpen = true;
          var self = this;
          this.$nextTick(function () {
            if (self.$refs.miniFirst) self.$refs.miniFirst.focus();
          });
        },

        cancelMiniForm: function () {
          this.miniOpen = false;
          this.miniError = "";
          this.clearMiniFields();
          this.reset();
        },

        clearMiniFields: function () {
          ["miniFirst", "miniLast", "miniPhone"].forEach(function (ref) {
            if (this.$refs[ref]) this.$refs[ref].value = "";
          }, this);
        },

        /* Обязательность имени проверяется здесь и заново на сервере:
           нативная проверка `required` не работает для кнопки вне `<form>`. */
        submitMiniForm: function () {
          var first = this.$refs.miniFirst;
          var name = first ? first.value.trim() : "";
          if (!name) {
            this.miniError = "Укажите имя ученика.";
            if (first) first.focus();
            return;
          }
          if (this.isFull) {
            this.miniError = "В группе уже " + this.maxMembers + " участников.";
            return;
          }

          window.htmx.ajax("POST", "/tutor/groups/students", {
            source: this.$root,
            target: "#group-members-update",
            swap: "outerHTML",
            values: {
              first_name: name,
              last_name: this.$refs.miniLast ? this.$refs.miniLast.value : "",
              phone: this.$refs.miniPhone ? this.$refs.miniPhone.value : "",
            },
          });
        },

        /* Ответ мини-формы пришёл: строка участника и новые опции. */
        applyMemberUpdate: function (payload) {
          if (!payload) return;
          if (payload.error) {
            this.miniError = payload.error;
            return;
          }
          if (payload.member && payload.member.id) {
            this.members.push(payload.member);
            this.all = payload.options || [];
          }
          this.miniOpen = false;
          this.miniError = "";
          this.clearMiniFields();
          this.reset();
        },
      }
    );
  }

  /* Собирает компонент из общего состояния состава и собственных методов. */
  function withMemberForm(extra) {
    return window.mergePersonPicker(memberFormState(), extra);
  }

  document.addEventListener("alpine:init", function () {
    /* Модалка «Новая группа»: только состав и закрытие. */
    Alpine.data("groupForm", function () {
      return withMemberForm({
        open: true,
        init: function () {
          this.initMembers();
        },
        close: function () {
          this.open = false;
        },
      });
    });

    /* Модалка управления: вкладки и двухшаговое подтверждение удаления. */
    Alpine.data("groupManage", function (initialTab) {
      return withMemberForm({
        open: true,
        tab: initialTab || "general",
        confirmingDelete: false,
        init: function () {
          this.initMembers();
        },
        close: function () {
          this.open = false;
        },
      });
    });
  });

  /* После подмены фрагмента мини-формы передаём данные активной форме
     событием: Alpine слушает его на корне модалки
     (`@group-member-created.window`). Так не нужны внутренности Alpine. */
  document.addEventListener("htmx:afterSwap", function (event) {
    // `event.target` — подменённый элемент; `detail.elt` — то же значение
    // в htmx 1.x, берём его как запасной вариант.
    var swapped = (event.detail && event.detail.elt) || event.target;
    var payload = readMemberUpdate(swapped);
    if (!payload) return;
    document.dispatchEvent(
      new CustomEvent("group-member-created", { detail: payload, bubbles: true })
    );
    if (typeof window.renderIcons === "function") window.renderIcons();
  });
})();
