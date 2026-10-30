"""Отдача статики с обязательной ревалидацией (ETag) — без эвристического кэша.

StaticFiles по умолчанию не выставляет `Cache-Control`, и браузер применяет
эвристику («10% от возраста файла»): JS может считаться свежим часами. Для
htmx-приложения это ловушка: страница не перезагружается неделями (только
частичные свопы), и после обновления `app/static/*.js` открытая вкладка
продолжала работать со старым скриптом — новый блок формы рендерился
сервером, а его Alpine-состояние молча не заводилось (список участников
«Присутствия» был пуст).

`no-cache` означает «хранить, но сверять»: при каждом показе браузер
спрашивает ETag — без изменений приходит 304 (дёшево), при изменении —
свежий файл. Долгоживущая вкладка избавляется от устаревшего кода после
первой же перезагрузки страницы.
"""

from starlette.staticfiles import StaticFiles


class RevalidatingStaticFiles(StaticFiles):
    """StaticFiles c `Cache-Control: no-cache` у всех отдаённых файлов."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response
