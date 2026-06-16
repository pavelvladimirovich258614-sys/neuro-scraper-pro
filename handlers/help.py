"""
Help & Limit Handlers
Раздел помощи и информация о лимите пользователя.
Вынесено из user_handlers — это изолированные leaf-хендлеры без FSM.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

import keyboards
import config
from database import db

logger = logging.getLogger(__name__)

router = Router()


# Мой лимит
@router.callback_query(F.data == "my_limit")
async def show_limit(callback: CallbackQuery):
    """Показать информацию о лимите"""
    user_id = callback.from_user.id
    limit_info = await db.check_limit(user_id)
    ref_stats = await db.get_referral_stats(user_id)

    if limit_info["is_premium"]:
        text = """
💎 <b>Премиум подписка активна!</b>

У вас безлимитный доступ ко всем функциям бота.
"""
    else:
        remaining = limit_info["remaining"]
        text = f"""
📊 <b>Информация о вашем лимите:</b>

Осталось парсингов: <b>{remaining}</b> из {config.FREE_PARSING_LIMIT}

<b>Способы получить больше:</b>
💎 Купить премиум подписку
👥 Пригласить друга (+{config.REFERRAL_BONUS} парсинга)

<b>Ваши рефералы:</b>
• Приглашено: {ref_stats['invited_count']} чел.
• Заработано: +{ref_stats['total_bonus']} парсингов
"""

    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_back_button(),
        parse_mode="HTML"
    )
    await callback.answer()


# Помощь
@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Показать меню помощи"""
    await callback.message.edit_text(
        "❓ <b>Раздел помощи</b>\n\nВыберите интересующую тему:",
        reply_markup=keyboards.get_help_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "help_channels")
async def help_channels(callback: CallbackQuery):
    """Помощь по парсингу каналов"""
    text = """
📖 <b>Как парсить каналы</b>

<b>Что такое парсинг каналов?</b>
Это сбор активных пользователей из комментариев к постам в Telegram-каналах.

<b>Как это работает:</b>

1️⃣ Выберите "Парсинг каналов" в главном меню
2️⃣ Выберите временной фильтр (неделя/месяц/3 месяца)
3️⃣ Отправьте ссылку на канал (например: https://t.me/channel_name)
4️⃣ Дождитесь завершения парсинга
5️⃣ Получите два файла:
   • Excel с полной информацией
   • TXT со списком юзернеймов

<b>Что вы получите:</b>
• Список активных пользователей
• Юзернеймы и ID
• Дата последней активности
• Количество сообщений
• Отдельный список админов

<b>Примечание:</b>
Для парсинга публичных каналов используйте системную сессию.
"""
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_help_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "help_chats")
async def help_chats(callback: CallbackQuery):
    """Помощь по парсингу чатов"""
    text = """
📖 <b>Как парсить чаты</b>

<b>Что такое парсинг чатов?</b>
Это сбор активных участников из групповых чатов Telegram.

<b>Как это работает:</b>

1️⃣ Выберите "Парсинг чатов" в главном меню
2️⃣ Выберите временной фильтр
3️⃣ Отправьте ссылку на чат
4️⃣ Дождитесь завершения парсинга
5️⃣ Получите отчеты

<b>Типы чатов:</b>

<b>Публичные:</b>
Используйте системную сессию
Формат: https://t.me/chat_username

<b>Закрытые:</b>
Добавьте свой аккаунт, который состоит в чате
Используйте его для парсинга

<b>Что вы получите:</b>
• Активные участники за выбранный период
• Полная информация о каждом
• Список администраторов
• Статистика активности
"""
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_help_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "help_account")
async def help_account(callback: CallbackQuery):
    """Помощь по добавлению аккаунта"""
    text = """
📖 <b>Как добавить аккаунт</b>

<b>Зачем это нужно?</b>
Для парсинга закрытых чатов, где состоит ваш аккаунт.

<b>Пошаговая инструкция:</b>

1️⃣ Нажмите "Добавить аккаунт" в главном меню

2️⃣ Введите номер телефона в международном формате:
   Пример: +79991234567

3️⃣ Получите код от Telegram на этот номер

4️⃣ Введите код в бота (5 цифр)

5️⃣ Если включена 2FA:
   Введите пароль двухфакторной аутентификации

6️⃣ Готово! Аккаунт добавлен

<b>Безопасность:</b>
✅ Все сессии хранятся локально
✅ Данные не передаются третьим лицам
✅ Используется официальное API Telegram

<b>Управление аккаунтами:</b>
В разделе "Мои аккаунты" вы можете:
• Просмотреть добавленные аккаунты
• Удалить аккаунт
"""
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_help_menu(),
        parse_mode="HTML"
    )
    await callback.answer()
