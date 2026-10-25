# Tasks

## 1. Модель и миграция

- [x] 1.1 Написать `app/tutor/models/tutor_settings.py`: одна строка на репетитора (PK = FK `tutors.id`, `ON DELETE CASCADE`); булевы переключатели, `reminder_offsets` (JSON), `digest_time`, `low_balance_threshold`, `default_lesson_duration`, `default_lesson_price`, `quarter1_end`…`quarter4_end`; константы дефолтов и `REMINDER_OFFSETS` рядом с моделью; зарегистрировать в `app/models.py`
- [x] 1.2 Миграция Alembic (autogenerate, таблица `tutor_settings`) и применение `uv run alembic upgrade head`

## 2. Сервисы

- [x] 2.1 Написать `app/tutor/services/settings.py`: `get_settings` (строка или объект дефолтов) и `save_settings` (ленивый upsert) — без FastAPI
- [x] 2.2 Написать `app/tutor/services/profile_form.py`: разбор и валидация личных данных (имя обязательно, ставка — число, опыт — строка)
- [x] 2.3 Написать `app/tutor/services/security_form.py`: email (`is_valid_email`, уникальность без своего текущего), пароль — только парой «новый + совпадающий повтор»
- [x] 2.4 Написать `app/tutor/services/notifications_form.py`: тогглы из формы, оффсеты напоминаний — только из `REMINDER_OFFSETS`, время сводки `ЧЧ:ММ`, порог — целое ≥ 0
- [x] 2.5 Написать `app/tutor/services/calendar_form.py`: зона — проверка по `available_timezones`, четверти — ММ-ДД по regex, длительность — из `LESSON_DURATIONS` (источник — модуль lesson), стоимость — целое ≥ 0

## 3. Маршруты и шаблоны

- [x] 3.1 Переписать `app/tutor/views/profile.py`: GET с выбором вкладки (`?tab=`), контекст `tutor` + `settings` + `tab` + `saved` + формы активной вкладки; сессия на удалённого репетитора — `LoginRequired`
- [x] 3.2 Написать POST-роуты `profile_save.py`, `profile_security.py`, `profile_notifications.py`, `profile_calendar.py` (ошибка — ре-рендер вкладки, успех — 303 на `?tab=…&saved=1`); подключить в `app/tutor/views/__init__.py`
- [x] 3.3 Переписать `app/tutor/templates/tutor/profile.html` по референсу: «← Назад», заголовок «Настройки», таббар четырёх вкладок, партиалы `_tab_profile.html`, `_tab_security.html`, `_tab_notifications.html`, `_tab_calendar.html`
- [x] 3.4 Переключатель `.switch` (трек+ползунок на чекбоксе), строки настроек `.switch-row`, сетки форм и плашка сохранения — плоскими BEM-селекторами в `app/static/styles.css`, цвета только токенами
- [x] 3.5 Страница доступна из строки пользователя в футере сайдбара (ссылка `/tutor/profile` уже была); пункт меню «Настройки» остаётся за `/tutor/settings` (мессенджеры — параллельный change)

## 4. Тесты и документация

- [x] 4.1 Переписать `tests/test_profile.py`: вкладки и выбор по `?tab=`, редирект без сессии, изоляция (чужие данные и настройки не видны и не меняются), сохранение всех четырёх форм (успех и ошибки: пустое имя, занятый email, несовпадение паролей, неверный формат четверти, оффсет вне набора), дефолты уведомлений, вход по новому email/паролю
- [x] 4.2 Прогнать `uv run pytest` — все тесты зелёные, включая CSS-проверку новых классов
- [x] 4.3 Обновить `README.md` (страница настроек с четырьмя вкладками) и перенести change в архив после приёмки
