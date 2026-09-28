"""
Throttle Middleware — защита от двойных нажатий инлайн-кнопок.

Если пользователь дважды быстро нажал одну и ту же кнопку (один и тот же
callback_data в пределах окна), второй вызов гасится: спиннер на кнопке
снимается, но хендлер не запускается повторно. Предотвращает двойные
действия (двойные сообщения/редактирования), не мешая нормальным нажатиям.
"""

import time
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)

# Окно подавления повторного идентичного нажатия (секунды)
THROTTLE_WINDOW = 0.7


class CallbackThrottleMiddleware(BaseMiddleware):
    """Гасит повторные идентичные callback'и в пределах окна."""

    # Максимальный размер кэша: при превышении чистим устаревшие записи
    MAX_CACHE_SIZE = 10000

    def __init__(self):
        # {user_id: (last_callback_data, last_timestamp)}
        self._last: Dict[int, tuple] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            now = time.time()
            last = self._last.get(user_id)

            if last and last[0] == event.data and (now - last[1]) < THROTTLE_WINDOW:
                # Дубликат — гасим спиннер и не пускаем к хендлеру
                try:
                    await event.answer()
                except Exception:
                    pass
                return None

            self._last[user_id] = (event.data, now)

            # Не даём кэшу расти бесконечно
            if len(self._last) > self.MAX_CACHE_SIZE:
                self._cleanup(now)

        return await handler(event, data)

    def _cleanup(self, now: float) -> None:
        """Удалить записи, чьё окно подавления давно истекло."""
        self._last = {
            uid: entry
            for uid, entry in self._last.items()
            if (now - entry[1]) < THROTTLE_WINDOW * 10
        }
        # Если всё ещё слишком много (массовый трафик) — просто сбрасываем
        if len(self._last) > self.MAX_CACHE_SIZE:
            self._last.clear()
