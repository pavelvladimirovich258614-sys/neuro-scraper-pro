"""
Subscription Check Middleware for NeuroScraper Pro Bot
Checks user subscription to required channel on every action
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject

import keyboards
from database import db

logger = logging.getLogger(__name__)

# Константы канала
CHANNEL_ID = keyboards.SUBSCRIPTION_CHANNEL_ID
CHANNEL_URL = keyboards.SUBSCRIPTION_CHANNEL_LINK

# In-memory кэш для оптимизации (TTL 10 секунд)
# Формат: {user_id: (is_subscribed, timestamp)}
_subscription_cache: Dict[int, tuple] = {}
CACHE_TTL = 10  # секунд


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки на канал при каждом действии.
    Если пользователь отписался — блокирует доступ и показывает сообщение.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any]
    ) -> Any:
        # Получаем user_id
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)
        
        user_id = user.id
        
        # Пропускаем callback проверки подписки (предотвращение цикла)
        if isinstance(event, CallbackQuery) and event.data == "check_subscription":
            return await handler(event, data)
        
        # Получаем bot из data
        bot: Bot = data.get('bot')
        if not bot:
            logger.warning("Bot not found in middleware data")
            return await handler(event, data)
        
        # Проверяем подписку (с кэшем для оптимизации)
        is_subscribed = await self._check_subscription_cached(bot, user_id)
        
        if is_subscribed:
            # Пользователь подписан — пропускаем к хендлеру
            return await handler(event, data)
        
        # Пользователь НЕ подписан — блокируем и показываем сообщение
        await self._show_unsubscribed_message(event, bot)
        
        # НЕ вызываем handler — блокируем действие
        return None

    async def _check_subscription_cached(self, bot: Bot, user_id: int) -> bool:
        """
        Проверяет подписку с использованием in-memory кэша.
        Кэш сбрасывается через CACHE_TTL секунд.
        """
        global _subscription_cache
        
        current_time = time.time()
        
        # Проверяем кэш
        if user_id in _subscription_cache:
            cached_result, cached_time = _subscription_cache[user_id]
            if current_time - cached_time < CACHE_TTL:
                return cached_result
        
        # Кэш устарел или отсутствует — проверяем через Telegram API
        is_subscribed = await self._check_subscription_api(bot, user_id)
        
        # Сохраняем в кэш
        _subscription_cache[user_id] = (is_subscribed, current_time)
        
        # Обновляем статус в БД
        if not is_subscribed:
            # Сбрасываем кэш подписки в базе
            await db.set_subscription_verified(user_id, False)
        
        return is_subscribed

    async def _check_subscription_api(self, bot: Bot, user_id: int) -> bool:
        """Проверяет подписку напрямую через Telegram API"""
        try:
            member = await bot.get_chat_member(CHANNEL_ID, user_id)
            is_subscribed = member.status in ['member', 'administrator', 'creator']
            return is_subscribed
        except Exception as e:
            logger.warning(f"Subscription check failed for user {user_id}: {e}")
            # При ошибке — считаем что подписан (чтобы не блокировать)
            return True

    async def _show_unsubscribed_message(
        self, 
        event: Union[Message, CallbackQuery],
        bot: Bot
    ):
        """Показывает сообщение об отписке"""
        text = (
            "❌ <b>Вы отписались от канала. Я всё вижу 👀</b>\n\n"
            "Подпишитесь на канал чтобы продолжить пользоваться ботом."
        )
        
        keyboard = keyboards.get_unsubscribed_menu()
        
        try:
            if isinstance(event, CallbackQuery):
                # Для callback — редактируем сообщение
                await event.message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                await event.answer("❌ Подпишитесь на канал!", show_alert=True)
            else:
                # Для обычного сообщения — отправляем новое
                await event.answer(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Error showing unsubscribed message: {e}")


def clear_subscription_cache(user_id: int = None):
    """
    Очистить кэш подписки.
    Если user_id указан — только для этого пользователя.
    Если None — очистить весь кэш.
    """
    global _subscription_cache
    if user_id is not None:
        _subscription_cache.pop(user_id, None)
    else:
        _subscription_cache.clear()
