# Tasks

## 1. Сервис дашборда (`tutor`)

- [x] 1.1 Написать строки дашборда: `app/tutor/services/dashboard_lesson.py` (урок дня: границы aware UTC, имя, подпись, статус) и `app/tutor/services/dashboard_payment.py` (платёж: операция ORM-строкой — сумму выводит `signed_money` из finance)
- [x] 1.2 Написать `app/tutor/services/dashboard.py`: `today_lessons` (окно `local_day_bounds` в зоне педагога, JOIN ученика и группы — изоляция как в календаре), `active_students_count`, `month_income` (только `paid`-платежи месяца), `month_hours` (завершённые уроки месяца, округление к полным часам с половиной вверх), `recent_payments` (последние 5 оплаченных), `dashboard_context` — счётчик «Запланировано» из той же выборки дня, без второго запроса
- [x] 1.3 Написать `app/tutor/services/presentation.py`: `time_range` («23:30 - 00:30», конец без прижимания к 23:59), `payment_date` («21 окт.»), `month_caption` («За октябрь»); зарегистрировать в `app/templating.py` после создания `templates` (порядок критичен — иначе циклический импорт)

## 2. Маршруты и шаблоны

- [x] 2.1 Переписать `app/tutor/views/home.py`: доступ через `Depends(require_tutor_id)`, контекст из `dashboard_context`; сессия на удалённого репетитора — `LoginRequired`
- [x] 2.2 Создать `app/tutor/views/profile.py` (`GET /tutor/profile`) и `app/tutor/templates/tutor/profile.html`: карточка профиля с главной переезжает сюда без изменений; подключить роутер в `app/tutor/views/__init__.py`
- [x] 2.3 Переписать `app/tutor/templates/tutor/home.html` по референсу: шапка с кнопкой «Обновить», `stat-grid` из четырёх карточек (иконки lucide в тинтовых кружках), `home-grid` со списками «Расписание на сегодня» и «Недавние платежи», пустые состояния, таб-бар
- [x] 2.4 Добавить в `app/static/styles.css` токены `--stat-*` (светлая и тёмная темы) и блок дашборда (`stat-grid`, `stat-card`, `home-grid`, `home-panel`, `home-row`, `home-empty`) плоскими BEM-селекторами; добавить модуль tutor в `tests/test_css_styles.py`

## 3. Тесты и спека

- [x] 3.1 Переписать `tests/test_home.py`: значения четырёх карточек (учёт периода и статусов), расписание с предметом и интервалом, урок через полночь, платежи (свежий выше старого, ожидающий не показан), изоляция, пустые состояния; даты строятся от «сейчас», не от фиксированного месяца
- [x] 3.2 Перенести профильные тесты в `tests/test_profile.py` (свои данные, необязательные поля, чужие данные скрыты, пароль не рендерится); удалить из `tests/test_index.py` тесты заглушки «Hello world» и часов на главной
- [x] 3.3 Написать `openspec/specs/tutor-dashboard/spec.md` (принятая спека) и обновить README: главная — дашборд, профиль — `/tutor/profile`
