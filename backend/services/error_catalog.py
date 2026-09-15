"""HTTP error catalog for field-friendly diagnostics (RU copy).

API responses expose English keys (title/causes/solutions) while catalog
source strings stay Russian for operators.
"""
from __future__ import annotations

from typing import Any

DOCS_BASE = (
    "https://github.com/nmuravev/MuraveiVision-PRO/blob/main/docs/ERROR_REFERENCE.md"
)

# code → name → entry
ERROR_CATALOG: dict[int, dict[str, dict[str, Any]]] = {
    400: {
        "BAD_REQUEST": {
            "title_ru": "Неверный запрос",
            "keywords": ["bad request", "invalid", "неверн", "параметр", "body", "required"],
            "causes_ru": [
                "Отсутствует обязательный параметр",
                "Неверный формат данных",
                "Превышен лимит размера файла",
            ],
            "solutions_ru": [
                "Проверьте параметры запроса в документации API",
                "Убедитесь, что файл соответствует формату (mp4, jpg, pt)",
                "Размер файла не должен превышать допустимый лимит",
            ],
            "examples": [
                "POST /api/detections без body",
                "GET /api/media/frame без path",
            ],
        },
    },
    401: {
        "UNAUTHORIZED": {
            "title_ru": "Требуется авторизация",
            "keywords": ["unauthorized", "token", "pin", "login", "auth", "сесси"],
            "causes_ru": [
                "PIN не введён или неверный",
                "Сессия истекла или токен недействителен",
                "Запрос без заголовка Authorization",
            ],
            "solutions_ru": [
                "Введите PIN оператора (1234567) или инженера (0000000)",
                "Перезайдите в систему через TopBar",
                "Проверьте, что Bearer-токен передаётся в запросе",
            ],
            "examples": [
                "POST /api/seg/load без токена",
                "GET /api/system/hardware без Authorization",
            ],
        },
    },
    403: {
        "FORBIDDEN": {
            "title_ru": "Доступ запрещён",
            "keywords": ["forbidden", "role", "permission", "прав", "engineer", "master"],
            "causes_ru": [
                "Роль пользователя недостаточна для операции",
                "Операция доступна только инженеру/мастеру",
                "Попытка изменить защищённые настройки",
            ],
            "solutions_ru": [
                "Войдите как инженер (PIN 0000000) для системных действий",
                "Обратитесь к инженеру смены за выполнением операции",
                "Проверьте роль в TopBar (Оператор / Инженер)",
            ],
            "examples": [
                "PUT /api/system/detect-config как оператор",
                "Смена PIN без роли master",
            ],
        },
    },
    404: {
        "NOT_FOUND": {
            "title_ru": "Ресурс не найден",
            "keywords": [
                "not found",
                "file not found",
                "missing",
                "crop",
                "detection",
                "не найден",
                "model",
            ],
            "causes_ru": [
                "Видео удалено или перемещено из archive/",
                "Неверный путь к файлу",
                "Модель не найдена на диске / не загружена в VRAM",
                "Детекция или объект не существует в БД",
            ],
            "solutions_ru": [
                "Проверьте существование файла в archive/ (Медиапул → Обновить)",
                "Убедитесь, что путь указан правильно (без лишних спецсимволов)",
                "Загрузите seg-модель через Viewer → Сегментация → Загрузить",
                "Проверьте ID детекции в Inspector",
            ],
            "examples": [
                "GET /api/media/frame?path=missing.mp4",
                "POST /api/seg/infer без загруженной модели",
                "GET /api/detections/{id} для несуществующей записи",
            ],
        },
    },
    409: {
        "CONFLICT": {
            "title_ru": "Конфликт состояния",
            "keywords": ["conflict", "already", "busy", "locked", "занят"],
            "causes_ru": [
                "Ресурс уже занят другой операцией",
                "Повторный запуск при активном процессе",
                "Конфликт версий данных",
            ],
            "solutions_ru": [
                "Дождитесь завершения текущей операции",
                "Остановите конфликтный процесс и повторите",
                "Обновите UI (F5) и попробуйте снова",
            ],
            "examples": [
                "Параллельный train при уже идущем обучении",
                "Повторный POST /api/seg/load при loaded=true",
            ],
        },
    },
    422: {
        "VALIDATION_ERROR": {
            "title_ru": "Ошибка валидации",
            "keywords": ["validation", "pydantic", "field required", "type_error"],
            "causes_ru": [
                "Поле отсутствует или имеет неверный тип",
                "Значение вне допустимого диапазона",
                "Некорректный JSON в теле запроса",
            ],
            "solutions_ru": [
                "Сверьте тело запроса со схемой в docs/API.md",
                "Проверьте типы: числа, строки, boolean",
                "Исправьте обязательные поля и повторите запрос",
            ],
            "examples": [
                "POST /api/change-detection/analyze с пустым video_before",
                "Неверный тип time_window_sec",
            ],
        },
    },
    429: {
        "RATE_LIMITED": {
            "title_ru": "Слишком много запросов",
            "keywords": ["rate", "limit", "too many", "throttle"],
            "causes_ru": [
                "Превышен лимит частоты запросов",
                "Слишком частые вызовы inference/export",
            ],
            "solutions_ru": [
                "Подождите несколько секунд и повторите",
                "Снизьте частоту опроса API",
                "Не запускайте параллельно тяжёлые операции",
            ],
            "examples": ["Частые POST /api/detect/infer в цикле"],
        },
    },
    500: {
        "INTERNAL_ERROR": {
            "title_ru": "Внутренняя ошибка сервера",
            "keywords": ["internal", "traceback", "exception", "failed", "boom"],
            "causes_ru": [
                "Непредвиденная ошибка в коде backend",
                "Сбой зависимости (OpenCV, YOLO, БД)",
                "Повреждённый файл или кэш",
            ],
            "solutions_ru": [
                "Проверьте логи backend / DebugPanel",
                "Перезапустите сервер (Запустить.bat)",
                "Сообщите инженеру текст ошибки и время",
            ],
            "examples": [
                "Сбой извлечения кадра из битого mp4",
                "Необработанное исключение в сервисе",
            ],
        },
    },
    503: {
        "DA3_WEIGHTS_NOT_FOUND": {
            "title_ru": "Веса модели DA3 не найдены",
            "keywords": ["da3", "depth anything", "da3_weights_not_found", "safetensors", "sidecars/da3"],
            "causes_ru": [
                "Файлы весов da3_base.safetensors / da3_large.safetensors отсутствуют в папке sidecars/da3/",
                "Используется сборка Mini без нейросетевых весов плотной 3D-реконструкции",
            ],
            "solutions_ru": [
                "Скопируйте веса da3_base.safetensors (или da3_large.safetensors) в sidecars/da3/ из офлайн-пака FullKit",
                "Переключитесь на классический MVS бэкенд (AliceVision) в панели Flight3D",
                "Проверьте доступность весов через GET /api/system/hardware",
            ],
            "examples": [
                "POST /api/recon/train/start с preset=da3_dense_base при пустом каталоге sidecars/da3/",
            ],
        },
        "SERVICE_UNAVAILABLE": {
            "title_ru": "Сервис временно недоступен",
            "keywords": [
                "unavailable",
                "not loaded",
                "vram",
                "gpu",
                "busy",
                "overloaded",
                "модель",
            ],
            "causes_ru": [
                "Модель не загружена в VRAM",
                "Backend или GPU перегружены",
                "Внешний сервис (Ollama) недоступен",
                "Превышен лимит одновременных задач",
            ],
            "solutions_ru": [
                "Загрузите модель (POST /api/seg/load или кнопка «Загрузить»)",
                "Подождите 30 секунд и повторите запрос",
                "Проверьте GPU: GET /api/system/hardware",
                "Закройте другие приложения, использующие GPU",
            ],
            "examples": ["POST /api/seg/infer при loaded=false"],
        },
    },
}


def _detail_text(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in item.get("loc", ()) if x != "body")
                msg = item.get("msg") or item.get("message") or ""
                parts.append(f"{loc}: {msg}".strip(": "))
            else:
                parts.append(str(item))
        return "; ".join(p for p in parts if p) or "Ошибка валидации запроса"
    return str(detail)


def get_error_details(code: int, detail: Any = None) -> dict[str, Any]:
    """Return catalog entry enriched with stable API field names."""
    catalog = ERROR_CATALOG.get(int(code), {})
    text = _detail_text(detail).lower()

    chosen_name: str | None = None
    chosen: dict[str, Any] | None = None
    if catalog and text:
        for name, info in catalog.items():
            needles = [name.lower(), *(str(k).lower() for k in info.get("keywords", []))]
            if any(n and n in text for n in needles):
                chosen_name, chosen = name, info
                break

    if chosen is None:
        if catalog:
            chosen_name = next(iter(catalog))
            chosen = catalog[chosen_name]
        else:
            chosen_name = "UNKNOWN"
            chosen = {
                "title_ru": "Неизвестная ошибка",
                "causes_ru": ["Код ответа не описан в справочнике"],
                "solutions_ru": [
                    "Откройте docs/ERROR_REFERENCE.md",
                    "Проверьте логи backend",
                ],
                "examples": [],
            }

    return {
        "name": chosen_name,
        "title_ru": chosen.get("title_ru", "Ошибка"),
        "causes_ru": list(chosen.get("causes_ru", [])),
        "solutions_ru": list(chosen.get("solutions_ru", [])),
        "examples": list(chosen.get("examples", [])),
    }


def build_error_payload(status_code: int, detail: Any = None) -> dict[str, Any]:
    """FastAPI-compatible body: keep ``detail``, add structured ``error``."""
    info = get_error_details(status_code, detail)
    message = _detail_text(detail)
    return {
        "detail": detail if detail is not None else info["title_ru"],
        "error": {
            "code": int(status_code),
            "name": info["name"],
            "title": info["title_ru"],
            "message": message or info["title_ru"],
            "causes": info["causes_ru"],
            "solutions": info["solutions_ru"],
            "examples": info["examples"],
            "docs_url": f"{DOCS_BASE}#{int(status_code)}",
        },
    }
