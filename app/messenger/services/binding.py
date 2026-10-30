"""Привязка мессенджеров через диплинк бота: канал репетитора и ученики.

Репетитор нажимает «Подключить»: сервис генерирует одноразовый код и
глубокую ссылку на бота (`?start=<код>`) и сохраняет их в `tutor_params`.
Ту же ссылку — уже из карточки ученика — строит сервис приглашений
(`student_invites.py`), код приглашения живёт в строке
`StudentMessengerInvite`. Ученик (или репетитор) переходит по ссылке и
нажимает «Запустить» — мессенджер доставляет боту событие старта, и
общая проверка (`confirm_binding`) за одно чтение апдейтов находит все
ожидающие коды аккаунта: канал репетитора сохраняется в параметрах,
чат ученика — в его приглашении. Ручной ввод chat_id не нужен.

Один читатель потока — принципиально: у MAX апдейты читаются по общему
маркеру, два независимых читателя вытятивали бы их друг у друга.

Сетевые вызовы — только в `start_binding`, `start_invite` и
`confirm_binding` (действия пользователя и опрос незавершённой
привязки); рендер карточек читает параметры и от сети не зависит.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services import max_bot_api, telegram_bot_api
from app.messenger.services.errors import BotApiError
from app.messenger.services.messengers import (
    MESSENGER_ICONS,
    MESSENGER_LABELS,
    MESSENGER_LINK_TEMPLATES,
    SUPPORTED,
    token_key,
)
from app.messenger.services.welcome import send_welcome
from app.tutor.services.params import delete_param, get_param, set_param

# Одноразовый код: 32 символа base64url. Telegram ограничивает payload
# диплинка 64 символами, MAX — 128: с запасом влезает в оба.
CODE_BYTES = 24

# Общая подсказка для redirect-потока без JS: точный текст ошибки живёт
# только в ответе действия, через URL его не донести — показываем, куда
# идти чинить причину.
BINDING_FAILED_HINT = (
    "Не удалось начать привязку — проверьте, что токен бота указан "
    "на вкладке «Мессенджеры», и попробуйте ещё раз."
)


def bind_code_key(messenger: str) -> str:
    """Имя KV-параметра с ожидаемым кодом привязки (`telegram_bind_code`)."""
    return f"{messenger}_bind_code"


def bind_link_key(messenger: str) -> str:
    """Имя KV-параметра со сгенерированной диплинк-ссылкой привязки."""
    return f"{messenger}_bind_link"


def chat_id_key(messenger: str) -> str:
    """Имя KV-параметра с id привязанного чата (`telegram_chat_id`)."""
    return f"{messenger}_chat_id"


def chat_label_key(messenger: str) -> str:
    """Имя KV-параметра с подписью чата для карточки (`@username`/имя)."""
    return f"{messenger}_chat_label"


def marker_key(messenger: str) -> str:
    """Имя KV-параметра с маркером чтения апдейтов MAX."""
    return f"{messenger}_updates_marker"


def start_binding(db: Session, tutor_id: str, messenger: str) -> list[str]:
    """Готовит привязку: одноразовый код и диплинк сохраняются в параметры.

    Возвращает список ошибок; пустой — привязка «в процессе», карточка
    покажет ссылку. Ник бота берётся из сети (getMe / GET /me), поэтому
    неверный токен или недоступная сеть видны сразу.
    """
    if messenger not in SUPPORTED:
        label = MESSENGER_LABELS.get(messenger, messenger)
        return [f"Канал уведомлений для {label} ещё не поддерживается."]
    token = get_param(db, tutor_id, token_key(messenger))
    if not token:
        label = MESSENGER_LABELS[messenger]
        return [
            f"Сначала создайте бота и вставьте его токен на вкладке "
            f"«Мессенджеры» ({label})."
        ]

    try:
        bot = _BOT_NAME[messenger](token)
    except BotApiError as exc:
        return [str(exc)]

    code = secrets.token_urlsafe(CODE_BYTES)
    link = MESSENGER_LINK_TEMPLATES[messenger].format(bot=bot, code=code)
    set_param(db, tutor_id, bind_code_key(messenger), code)
    set_param(db, tutor_id, bind_link_key(messenger), link)
    if messenger == "max":
        ensure_max_marker(db, tutor_id, token)
    return []


def confirm_binding(db: Session, tutor_id: str, messenger: str) -> list[str]:
    """Проверяет все ожидающие коды аккаунта: канал репетитора и ученики.

    Апдейты читаются один раз (у MAX — по общему маркеру), и один проход
    матчит и код привязки канала, и непогашенные коды приглашений
    учеников: старты ученика и репетитора в одной пачке привязываются
    оба. Ничего не найдено — состояния просто остаются «в процессе»,
    ошибкой это не считается. Ошибки сети/API возвращаются списком.
    """
    if messenger not in SUPPORTED:
        return []
    token = get_param(db, tutor_id, token_key(messenger))
    if not token:
        return []
    tutor_code = get_param(db, tutor_id, bind_code_key(messenger))
    invites = _pending_invites(db, tutor_id, messenger)
    if not tutor_code and not invites:
        return []

    try:
        if messenger == "telegram":
            return _confirm_telegram(db, tutor_id, token, tutor_code, invites)
        return _confirm_max(db, tutor_id, token, tutor_code, invites)
    except BotApiError as exc:
        return [str(exc)]


def unbind_channel(db: Session, tutor_id: str, messenger: str) -> None:
    """Удаляет привязку канала вместе с незавершённой привязкой.

    Токен бота не трогается — он настраивается на вкладке «Мессенджеры».
    """
    for key in (
        chat_id_key(messenger),
        chat_label_key(messenger),
        bind_code_key(messenger),
        bind_link_key(messenger),
    ):
        delete_param(db, tutor_id, key)


def channels_block_context(
    db: Session,
    tutor_id: str,
    extra_errors: list[str] | None = None,
) -> dict:
    """Данные блока «Каналы уведомлений»: карточка на поддерживаемый
    мессенджер и список ошибок последнего действия.

    Рендер сетенезависим: читаются только параметры, сеть дёргают
    `start_binding`/`confirm_binding` по действиям пользователя.
    """
    channels = []
    for messenger in SUPPORTED:
        chat_id = get_param(db, tutor_id, chat_id_key(messenger))
        link = get_param(db, tutor_id, bind_link_key(messenger))
        # «В процессе» = код сгенерирован, чат ещё не привязан и токен на
        # месте: без токена проверять нечего, карточка честно возвращается
        # в «не подключён» (иначе поллинг зависал бы без обратной связи).
        token = get_param(db, tutor_id, token_key(messenger))
        channels.append({
            "messenger": messenger,
            "label": MESSENGER_LABELS[messenger],
            "icon": MESSENGER_ICONS[messenger],
            "bound": bool(chat_id),
            "chat_label": get_param(db, tutor_id, chat_label_key(messenger)) or "",
            "pending": chat_id is None and bool(link) and bool(token),
            "link": link or "",
        })
    return {"channels": channels, "errors": list(extra_errors or [])}


# ---------------------------------------------------------------------------
# Ники ботов, чтение потока апдейтов и поиск кодов — по мессенджеру;
# новый мессенджер добавляется записью в словари рядом с закрытыми
# списками. Словари — после функций: они ссылаются на определённые выше.
# ---------------------------------------------------------------------------


def bot_name(messenger: str, token: str) -> str:
    """Ник бота из сети (getMe / GET /me) — для построения диплинка."""
    return _BOT_NAME[messenger](token)


def ensure_max_marker(db: Session, tutor_id: str, token: str) -> None:
    """Фиксирует голову потока апдейтов MAX, если поток ещё не читался.

    Маркер общий у привязки канала и всех приглашений учеников: снапшот
    делается только при его отсутствии, иначе свежий снапшот перескочил
    бы события, относящиеся к ещё незавершённым кодам. Повторное чтение
    старых апдейтов безвредно — сравнение кодов точное.
    """
    if get_param(db, tutor_id, marker_key("max")) is not None:
        return
    _snapshot_max_marker(db, tutor_id, token)


def _confirm_telegram(
    db: Session,
    tutor_id: str,
    token: str,
    tutor_code: str | None,
    invites: dict[str, StudentMessengerInvite],
) -> list[str]:
    """Ищет `/start <код>` среди апдейтов бота: канал и учеников пакетно."""
    tutor_chat: tuple[str, str] | None = None
    invite_hits: list[tuple[StudentMessengerInvite, str, str]] = []
    for update in telegram_bot_api.pending_updates(token):
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        text = message.get("text") or ""
        payload = text[len("/start "):] if text.startswith("/start ") else ""
        if tutor_code and payload == tutor_code:
            tutor_chat = (str(chat_id), _telegram_label(chat))
        elif payload and payload in invites:
            invite_hits.append((invites[payload], str(chat_id), _telegram_label(chat)))

    errors = _apply_hits(db, tutor_id, "telegram", tutor_chat, invite_hits)
    return errors


def _confirm_max(
    db: Session,
    tutor_id: str,
    token: str,
    tutor_code: str | None,
    invites: dict[str, StudentMessengerInvite],
) -> list[str]:
    """Ищет `bot_started` с payload среди апдейтов бота MAX.

    Схема апдейта плоская: `payload`, `chat_id` и `user` лежат на верхнем
    уровне объекта (docs-api/objects/Update) — вложенного объекта
    `bot_started` нет, попытка прочитать payload изнутри оставляет код
    ненайденным, а апдейт потреблённым.

    Маркер чтения хранится в параметрах и общий для всех кодов аккаунта:
    без него API отдаёт только последнее обновление. `start_binding` и
    `start_invite` сразу фиксируют голову потока (`ensure_max_marker`),
    поэтому проверки читают инкрементально; маркер двигается, только
    когда просмотрено всё до него (чтение без маркера, вернувшее
    непустой список без попаданий, может скрывать более ранние апдейты).
    """
    raw_marker = get_param(db, tutor_id, marker_key("max"))
    try:
        marker = int(raw_marker) if raw_marker else None
    except ValueError:
        marker = None
    updates, next_marker = max_bot_api.fetch_updates(token, marker)

    tutor_chat: tuple[str, str] | None = None
    invite_hits: list[tuple[StudentMessengerInvite, str, str]] = []
    for update in updates:
        if update.get("update_type") != "bot_started":
            continue
        payload = update.get("payload") or ""
        user = update.get("user") or {}
        # Личный диалог в MAX адресуется chat_id, равным user_id: если
        # событие не принесло chat_id, привязываем диалог по пользователю.
        chat_id = update.get("chat_id") or user.get("user_id")
        if chat_id is None:
            continue
        if tutor_code and payload == tutor_code:
            tutor_chat = (str(chat_id), _max_label(user))
        elif payload and payload in invites:
            invite_hits.append((invites[payload], str(chat_id), _max_label(user)))

    # Пустой поток или инкрементальное чтение — всё просмотрено, голову
    # можно двигать. Без маркера и с непустым списком — нельзя: видели
    # только последнее обновление, впереди могли остаться непросмотренные.
    if next_marker is not None and (
        marker is not None or not updates or tutor_chat or invite_hits
    ):
        set_param(db, tutor_id, marker_key("max"), str(next_marker))

    return _apply_hits(db, tutor_id, "max", tutor_chat, invite_hits)


def _apply_hits(
    db: Session,
    tutor_id: str,
    messenger: str,
    tutor_chat: tuple[str, str] | None,
    invite_hits: list[tuple[StudentMessengerInvite, str, str]],
) -> list[str]:
    """Сохраняет найденные привязки и приветствует подключённые чаты.

    Приветствие — первая живая проверка канала: сбой отправки привязку
    не отменяет, но возвращается в блок, чтобы молчаливо не работающий
    канал не остался незамеченным.
    """
    errors: list[str] = []
    if tutor_chat is not None:
        chat_id, label = tutor_chat
        # Код и ссылка одноразовые: погашаются при первом попадании,
        # повторная проверка с тем же кодом ничего не привязывает.
        delete_param(db, tutor_id, bind_code_key(messenger))
        delete_param(db, tutor_id, bind_link_key(messenger))
        _save_channel(db, tutor_id, messenger, chat_id, label)
        errors.extend(send_welcome(db, tutor_id, messenger, chat_id))
    for row, chat_id, label in invite_hits:
        _save_invite(db, row, chat_id, label)
        errors.extend(send_welcome(db, tutor_id, messenger, chat_id))
    return errors


def _pending_invites(
    db: Session, tutor_id: str, messenger: str
) -> dict[str, StudentMessengerInvite]:
    """Приглашения учеников, ждущие «Запуска» бота: код → строка."""
    rows = db.scalars(
        select(StudentMessengerInvite).where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.messenger == messenger,
            StudentMessengerInvite.invite_code.is_not(None),
        )
    ).all()
    return {row.invite_code: row for row in rows}


def _save_invite(
    db: Session, row: StudentMessengerInvite, chat_id: str, label: str
) -> None:
    """Фиксирует подключение ученика: чат сохранён, приглашение погашено."""
    row.chat_id = chat_id
    row.chat_label = label or chat_id
    row.invite_code = None
    row.invite_link = None
    db.commit()


def _snapshot_max_marker(db: Session, tutor_id: str, token: str) -> None:
    """Фиксирует голову потока апдейтов MAX на момент вызова.

    Без маркера API отдаёт только последнее обновление: если первая
    проверка пошла бы без маркера, события между созданием кода и
    «Стартом» она не увидела бы. Обновления до создания кода заведомо
    не содержат его, поэтому пропускать их при снапшоте безопасно.
    """
    try:
        _updates, marker = max_bot_api.fetch_updates(token, None)
    except BotApiError:
        # Обрыв снапшота не отменяет привязку: проверки отработают по
        # «последнему обновлению», а пустой поток сохранит голову сам.
        return
    if marker is not None:
        set_param(db, tutor_id, marker_key("max"), str(marker))


def _save_channel(
    db: Session, tutor_id: str, messenger: str, chat_id: str, label: str
) -> None:
    """Сохраняет привязку: chat_id и подпись чата (без подписи — chat_id)."""
    set_param(db, tutor_id, chat_id_key(messenger), chat_id)
    set_param(db, tutor_id, chat_label_key(messenger), label or chat_id)


def _telegram_label(chat: dict) -> str:
    """Подпись чата Telegram: `@username`, иначе title или имя."""
    username = chat.get("username")
    if username:
        return f"@{username}"
    return chat.get("title") or chat.get("first_name") or ""


def _max_label(user: dict) -> str:
    """Подпись чата MAX: `@username`, иначе имя (`name`/`first_name`)."""
    username = user.get("username")
    if username:
        return f"@{username}"
    return user.get("name") or user.get("first_name") or ""


_BOT_NAME = {
    "telegram": telegram_bot_api.bot_username,
    "max": max_bot_api.bot_nickname,
}
