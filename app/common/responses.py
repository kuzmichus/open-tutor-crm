"""Ответ «диалог закрыт» для действий в модалке (HTMX + `HX-Trigger`).

Диалог окна (`slot/_dialog.html`) и его формы живут в `#modal` и целятся в
`#slot-dialog` с `hx-swap="outerHTML"`: ошибка возвращает сам диалог с
сообщением, поэтому подмена нужна. Успех же возвращает **пустое тело** —
диалог закрывается подпиской на `slot-saved`.

Пустое тело с `outerHTML` давало `htmx:swapError` и ошибку в консоли
(«Cannot read properties of null (reading 'firstChild')»): событие
`slot-saved` htmx рассылает ДО подмены, обработчик закрывает диалог и
очищает `#modal`, а подмена идёт в уже отсоединённый узел. Найдено в
браузере при прогоне сценария задачи 9.2.

`HX-Reswap: none` говорит htmx не трогать DOM: закрытие уже сделал
обработчик события, а подменять пустоту нечем. Заголовок живёт здесь, а не
в сервисах: это знание про HTTP, а сервисы по правилу AGENTS.md про
FastAPI не знают.
"""

from fastapi.responses import HTMLResponse

def dialog_closed(event: str = "slot-saved") -> HTMLResponse:
    """Пустой ответ «диалог закрыт»: событие для страницы, без подмены DOM."""
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": event, "HX-Reswap": "none"},
    )
