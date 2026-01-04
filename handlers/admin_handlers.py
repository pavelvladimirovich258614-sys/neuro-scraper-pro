"""
Admin Handlers Module
Handles admin commands and management functions
"""

import logging
import asyncio
import time
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound, TelegramBadRequest

import keyboards
import config
from database import db

logger = logging.getLogger(__name__)

router = Router()


class AdminStates(StatesGroup):
    """Состояния для админских действий"""
    waiting_for_user_id_premium = State()
    waiting_for_user_id_reset = State()
    waiting_for_user_id_revoke = State()
    waiting_for_user_id_add_admin = State()
    waiting_for_user_id_remove_admin = State()


class BroadcastStates(StatesGroup):
    """Состояния для рассылки"""
    waiting_for_ids = State()           # Ввод списка ID (для рассылки по ID)
    waiting_for_photo = State()         # Ожидание фото
    waiting_for_text = State()          # Ожидание текста
    waiting_for_button = State()        # Ожидание данных кнопки
    pin_step = State()                  # Шаг закрепления
    preview = State()                   # Предпросмотр
    editing_photo = State()             # Редактирование фото
    editing_text = State()              # Редактирование текста
    editing_button = State()            # Редактирование кнопки


async def is_admin(user_id: int) -> bool:
    """Проверка прав администратора (включая добавленных)"""
    return await db.is_bot_admin(user_id)


# Команда /admin
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return

    text = """
👑 <b>Админ-панель</b>

Добро пожаловать в панель управления!

Выберите действие:
"""

    await message.answer(
        text,
        reply_markup=keyboards.get_admin_menu(),
        parse_mode="HTML"
    )


# Выдача премиума
@router.callback_query(F.data == "admin_give_premium")
async def admin_give_premium_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса выдачи премиума"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    await callback.message.edit_text(
        "👤 <b>Выдача премиума</b>\n\n"
        "Отправьте ID пользователя:",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id_premium)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id_premium)
async def admin_give_premium_process(message: Message, state: FSMContext):
    """Обработка выдачи премиума"""
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой ID пользователя:",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    # Проверяем существование пользователя
    user = await db.get_user(target_user_id)
    if not user:
        # Создаем пользователя если не существует
        await db.create_user(target_user_id)

    # Выдаем премиум
    success = await db.set_premium(target_user_id, True)

    if success:
        await message.answer(
            f"✅ <b>Премиум выдан!</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n"
            f"Статус: Премиум активен",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при выдаче премиума",
            reply_markup=keyboards.get_admin_menu()
        )

    await state.clear()


# Сброс лимита
@router.callback_query(F.data == "admin_reset_limit")
async def admin_reset_limit_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса сброса лимита"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    await callback.message.edit_text(
        "🔄 <b>Сброс лимита</b>\n\n"
        "Отправьте ID пользователя:",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id_reset)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id_reset)
async def admin_reset_limit_process(message: Message, state: FSMContext):
    """Обработка сброса лимита"""
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой ID пользователя:",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    # Проверяем существование пользователя
    user = await db.get_user(target_user_id)
    if not user:
        await message.answer(
            "❌ Пользователь не найден в базе данных",
            reply_markup=keyboards.get_admin_menu()
        )
        await state.clear()
        return

    # Сбрасываем лимит
    success = await db.reset_limit(target_user_id)

    if success:
        await message.answer(
            f"✅ <b>Лимит сброшен!</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n"
            f"Парсингов доступно: {config.FREE_PARSING_LIMIT}",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при сбросе лимита",
            reply_markup=keyboards.get_admin_menu()
        )

    await state.clear()


# Отзыв премиума
@router.callback_query(F.data == "admin_revoke_premium")
async def admin_revoke_premium_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса отзыва премиума"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    await callback.message.edit_text(
        "📉 <b>Отзыв премиума</b>\n\n"
        "Отправьте ID пользователя, у которого нужно забрать премиум:",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id_revoke)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id_revoke)
async def admin_revoke_premium_process(message: Message, state: FSMContext):
    """Обработка отзыва премиума"""
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой ID пользователя:",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    # Проверяем существование пользователя
    user = await db.get_user(target_user_id)
    if not user:
        await message.answer(
            "❌ Пользователь не найден в базе данных",
            reply_markup=keyboards.get_admin_menu()
        )
        await state.clear()
        return

    # Забираем премиум
    success = await db.set_premium(target_user_id, False)

    if success:
        await message.answer(
            f"✅ <b>Премиум отозван!</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n"
            f"Статус: Обычный пользователь\n"
            f"Доступно парсингов: {max(0, config.FREE_PARSING_LIMIT - user['parsing_count'])}",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при отзыве премиума",
            reply_markup=keyboards.get_admin_menu()
        )

    await state.clear()


# Статистика
@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Показать статистику бота"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    stats = await db.get_stats()

    text = f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
• Всего: {stats['total_users']}
• Премиум: {stats['premium_users']}
• Обычных: {stats['total_users'] - stats['premium_users']}

📈 <b>Парсинг:</b>
• Всего парсингов: {stats['total_parsings']}
• Пользователей найдено: {stats['total_users_found']}

💎 <b>Лимиты:</b>
• Бесплатных парсингов: {config.FREE_PARSING_LIMIT}
"""

    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_admin_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# Статистика пользователей
@router.callback_query(F.data == "admin_user_stats")
async def admin_user_stats(callback: CallbackQuery):
    """Показать детальную статистику по пользователям"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    await callback.answer("⏳ Формирую статистику...")

    user_stats = await db.get_user_statistics()

    if not user_stats:
        await callback.message.answer(
            "ℹ️ Пользователей пока нет",
            reply_markup=keyboards.get_admin_menu()
        )
        return

    # Формируем текстовое сообщение
    text = "📈 <b>Статистика пользователей</b>\n\n"
    text += f"<b>Всего пользователей:</b> {len(user_stats)}\n\n"

    # Ограничиваем до 20 пользователей в сообщении
    display_users = user_stats[:20]

    for idx, user in enumerate(display_users, 1):
        username = f"@{user['username']}" if user['username'] else "Нет username"
        first_name = user['first_name'] or "Нет имени"
        premium_badge = " 💎" if user['is_premium'] else ""

        text += f"{idx}. <b>{first_name}</b> {premium_badge}\n"
        text += f"   ID: <code>{user['user_id']}</code>\n"
        text += f"   Username: {username}\n"
        text += f"   Регистрация: {user['registered_at'][:10]}\n"
        text += f"   Дней в боте: {user['days_in_bot']}\n"
        text += f"   Парсингов: {user['parsing_count']}\n"
        text += f"   Последняя активность: {user['last_activity'][:10]}\n\n"

    if len(user_stats) > 20:
        text += f"<i>Показаны первые 20 из {len(user_stats)} пользователей</i>\n"

    # Отправляем как новое сообщение (если текст слишком длинный для edit)
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboards.get_admin_menu()
    )


# Команда для получения своего ID (полезно для пользователей)
@router.message(Command("id"))
async def cmd_get_id(message: Message):
    """Получить свой ID"""
    user_id = message.from_user.id
    username = message.from_user.username or "Не установлен"

    text = f"""
ℹ️ <b>Ваша информация:</b>

ID: <code>{user_id}</code>
Username: @{username}
Имя: {message.from_user.first_name or ""}
"""

    await message.answer(text, parse_mode="HTML")


# Команда для помощи (доступна всем)
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать помощь"""
    text = """
❓ <b>Справка по командам</b>

/start - Главное меню
/id - Получить свой ID
/help - Эта справка

<b>Основные функции:</b>

📊 Парсинг каналов - сбор активных пользователей из комментариев
👥 Парсинг чатов - сбор участников из групповых чатов
➕ Добавить аккаунт - для парсинга закрытых чатов
💎 Мой лимит - проверить доступные парсинги

<b>Поддержка:</b>
Если у вас возникли вопросы, обратитесь в поддержку через главное меню.
"""

    await message.answer(
        text,
        reply_markup=keyboards.get_main_menu(),
        parse_mode="HTML"
    )


# ===== УПРАВЛЕНИЕ АДМИНАМИ БОТА =====

@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса добавления админа"""
    # Только главный админ может добавлять других админов
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("❌ Только главный админ может добавлять админов", show_alert=True)
        return

    await callback.message.edit_text(
        "👑 <b>Добавление админа бота</b>\n\n"
        "Отправьте Telegram ID пользователя, которого хотите сделать админом:\n\n"
        "<i>Пользователь сможет управлять премиумом, сбрасывать лимиты и просматривать статистику.</i>",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id_add_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id_add_admin)
async def admin_add_admin_process(message: Message, state: FSMContext):
    """Обработка добавления админа"""
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой ID пользователя:",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    if target_user_id == config.ADMIN_ID:
        await message.answer(
            "ℹ️ Этот пользователь уже является главным админом",
            reply_markup=keyboards.get_admin_menu()
        )
        await state.clear()
        return

    # Проверяем, не админ ли уже
    if await db.is_bot_admin(target_user_id):
        await message.answer(
            "ℹ️ Этот пользователь уже является админом бота",
            reply_markup=keyboards.get_admin_menu()
        )
        await state.clear()
        return

    # Добавляем админа
    success = await db.add_bot_admin(target_user_id, message.from_user.id)

    if success:
        await message.answer(
            f"✅ <b>Админ добавлен!</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n\n"
            f"Теперь этот пользователь может использовать /admin",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при добавлении админа",
            reply_markup=keyboards.get_admin_menu()
        )

    await state.clear()


@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса удаления админа"""
    # Только главный админ может удалять админов
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("❌ Только главный админ может удалять админов", show_alert=True)
        return

    await callback.message.edit_text(
        "🚫 <b>Удаление админа бота</b>\n\n"
        "Отправьте Telegram ID админа, которого хотите удалить:\n\n"
        "<i>Главного админа удалить нельзя.</i>",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_user_id_remove_admin)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id_remove_admin)
async def admin_remove_admin_process(message: Message, state: FSMContext):
    """Обработка удаления админа"""
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите числовой ID пользователя:",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    if target_user_id == config.ADMIN_ID:
        await message.answer(
            "❌ Нельзя удалить главного админа!",
            reply_markup=keyboards.get_admin_menu()
        )
        await state.clear()
        return

    # Удаляем админа
    success = await db.remove_bot_admin(target_user_id)

    if success:
        await message.answer(
            f"✅ <b>Админ удалён!</b>\n\n"
            f"User ID: <code>{target_user_id}</code>\n\n"
            f"Пользователь больше не имеет доступа к админ-панели.",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ Ошибка при удалении админа",
            reply_markup=keyboards.get_admin_menu()
        )

    await state.clear()


@router.callback_query(F.data == "admin_list_admins")
async def admin_list_admins(callback: CallbackQuery):
    """Показать список админов бота"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    admins = await db.get_bot_admins()

    text = "📋 <b>Список админов бота:</b>\n\n"

    for idx, admin in enumerate(admins, 1):
        user_id = admin["user_id"]

        if admin["is_main"]:
            badge = "👑 Главный"
        else:
            badge = "⭐️ Админ"

        # Пробуем получить username из БД пользователей
        user_info = await db.get_user(user_id)
        if user_info and user_info.get("username"):
            username = f"@{user_info['username']}"
        else:
            username = "username не известен"

        text += f"{idx}. {badge}\n"
        text += f"   ID: <code>{user_id}</code>\n"
        text += f"   {username}\n\n"

    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_admin_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# ===== УПРАВЛЕНИЕ ГЛОБАЛЬНЫМ ДОСТУПОМ К ПАРСИНГУ =====

@router.callback_query(F.data == "admin_open_access")
async def admin_open_access(callback: CallbackQuery):
    """Открыть доступ к парсингу для всех пользователей"""
    user_id = callback.from_user.id
    
    if not await is_admin(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    success = await db.set_access_open(True)
    
    if success:
        await callback.answer("✅ Доступ открыт для всех пользователей!", show_alert=True)
        await callback.message.edit_text(
            "🔓 <b>Доступ ОТКРЫТ</b>\n\n"
            "Теперь все пользователи имеют неограниченный доступ к парсингу.\n\n"
            "Чтобы вернуть ограничения (3 пробных парсинга), нажмите «Закрыть доступ».",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)


@router.callback_query(F.data == "admin_close_access")
async def admin_close_access(callback: CallbackQuery):
    """Закрыть доступ — вернуть логику с 3 пробными парсингами"""
    user_id = callback.from_user.id
    
    if not await is_admin(user_id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    success = await db.set_access_open(False)
    
    if success:
        await callback.answer("🔒 Доступ закрыт!", show_alert=True)
        await callback.message.edit_text(
            "🔒 <b>Доступ ЗАКРЫТ</b>\n\n"
            f"Новые пользователи получают только {config.FREE_PARSING_LIMIT} пробных парсингов.\n"
            "Премиум-пользователи сохраняют неограниченный доступ.\n\n"
            "Чтобы открыть доступ для всех, нажмите «Открыть доступ всем».",
            reply_markup=keyboards.get_admin_menu(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)


# ===== МОДУЛЬ РАССЫЛОК (Broadcast Module) =====

def get_default_broadcast_data() -> dict:
    """Получить данные рассылки по умолчанию"""
    return {
        "mode": None,           # "all" или "ids"
        "target_ids": [],       # Список ID для рассылки
        "photo_id": None,       # file_id фото
        "text": None,           # Текст сообщения
        "button_text": None,    # Текст кнопки
        "button_url": None,     # URL кнопки
        "pin_enabled": False,   # Закреплять сообщение
    }


# --- Начало рассылки ---

@router.callback_query(F.data == "admin_broadcast_all")
async def admin_broadcast_all_start(callback: CallbackQuery, state: FSMContext):
    """Начало массовой рассылки по всем пользователям"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    # Получаем количество пользователей
    all_users = await db.get_all_user_ids()
    user_count = len(all_users)

    # Инициализируем данные рассылки
    broadcast_data = get_default_broadcast_data()
    broadcast_data["mode"] = "all"
    broadcast_data["target_ids"] = all_users
    await state.update_data(broadcast=broadcast_data)

    await callback.message.edit_text(
        f"📢 <b>Массовая рассылка</b>\n\n"
        f"Получателей: <b>{user_count}</b> пользователей\n\n"
        f"<b>Шаг 1/4: Картинка</b>\n"
        f"Отправьте фото или нажмите «Пропустить»:",
        reply_markup=keyboards.get_broadcast_photo_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_photo)
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast_ids")
async def admin_broadcast_ids_start(callback: CallbackQuery, state: FSMContext):
    """Начало рассылки по конкретным ID"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    # Инициализируем данные рассылки
    broadcast_data = get_default_broadcast_data()
    broadcast_data["mode"] = "ids"
    await state.update_data(broadcast=broadcast_data)

    await callback.message.edit_text(
        "🎯 <b>Рассылка по ID</b>\n\n"
        "Отправьте список Telegram ID пользователей.\n\n"
        "<i>Можно через пробел, запятую или с новой строки:</i>\n"
        "<code>123456789 987654321</code>\n"
        "<code>123456789, 987654321</code>\n"
        "<code>123456789\n987654321</code>",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_ids)
    await callback.answer()


@router.message(BroadcastStates.waiting_for_ids)
async def process_broadcast_ids(message: Message, state: FSMContext):
    """Обработка списка ID для рассылки"""
    # Парсим ID из текста (через пробел, запятую или новую строку)
    text = message.text.strip()
    # Разделяем по пробелам, запятым и переносам строки
    raw_ids = re.split(r'[\s,\n]+', text)

    valid_ids = []
    invalid_entries = []

    for raw_id in raw_ids:
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            user_id = int(raw_id)
            if user_id > 0:
                valid_ids.append(user_id)
            else:
                invalid_entries.append(raw_id)
        except ValueError:
            invalid_entries.append(raw_id)

    if not valid_ids:
        await message.answer(
            "❌ Не найдено ни одного валидного ID.\n\n"
            "Введите числовые Telegram ID:",
            reply_markup=keyboards.get_broadcast_text_menu()
        )
        return

    # Обновляем данные
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["target_ids"] = valid_ids
    await state.update_data(broadcast=broadcast_data)

    warning_text = ""
    if invalid_entries:
        warning_text = f"\n⚠️ Пропущено некорректных значений: {len(invalid_entries)}"

    await message.answer(
        f"🎯 <b>Рассылка по ID</b>\n\n"
        f"Получателей: <b>{len(valid_ids)}</b>{warning_text}\n\n"
        f"<b>Шаг 1/4: Картинка</b>\n"
        f"Отправьте фото или нажмите «Пропустить»:",
        reply_markup=keyboards.get_broadcast_photo_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_photo)


# --- Шаг 1: Фото ---

@router.message(BroadcastStates.waiting_for_photo, F.photo)
async def process_broadcast_photo(message: Message, state: FSMContext):
    """Обработка фото для рассылки"""
    # Берём фото максимального размера
    photo_id = message.photo[-1].file_id

    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["photo_id"] = photo_id
    await state.update_data(broadcast=broadcast_data)

    await message.answer(
        "✅ Фото загружено!\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_broadcast_photo_edit_menu()
    )


@router.message(BroadcastStates.editing_photo, F.photo)
async def process_broadcast_photo_edit(message: Message, state: FSMContext):
    """Обработка замены фото"""
    photo_id = message.photo[-1].file_id

    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["photo_id"] = photo_id
    await state.update_data(broadcast=broadcast_data)

    await message.answer(
        "✅ Фото заменено!\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_broadcast_photo_edit_menu()
    )
    await state.set_state(BroadcastStates.waiting_for_photo)


@router.callback_query(F.data == "broadcast_skip_photo")
async def broadcast_skip_photo(callback: CallbackQuery, state: FSMContext):
    """Пропуск шага с фото"""
    await callback.message.edit_text(
        "📝 <b>Шаг 2/4: Текст сообщения</b>\n\n"
        "Отправьте текст рассылки.\n\n"
        "<i>Поддерживается HTML-форматирование:</i>\n"
        "<code>&lt;b&gt;жирный&lt;/b&gt;</code>\n"
        "<code>&lt;i&gt;курсив&lt;/i&gt;</code>\n"
        "<code>&lt;a href=\"URL\"&gt;ссылка&lt;/a&gt;</code>",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_text)
    await callback.answer()


@router.callback_query(F.data == "broadcast_photo_next")
async def broadcast_photo_next(callback: CallbackQuery, state: FSMContext):
    """Переход к шагу текста после фото"""
    await callback.message.edit_text(
        "📝 <b>Шаг 2/4: Текст сообщения</b>\n\n"
        "Отправьте текст рассылки.\n\n"
        "<i>Поддерживается HTML-форматирование:</i>\n"
        "<code>&lt;b&gt;жирный&lt;/b&gt;</code>\n"
        "<code>&lt;i&gt;курсив&lt;/i&gt;</code>\n"
        "<code>&lt;a href=\"URL\"&gt;ссылка&lt;/a&gt;</code>",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_text)
    await callback.answer()


@router.callback_query(F.data == "broadcast_replace_photo")
async def broadcast_replace_photo(callback: CallbackQuery, state: FSMContext):
    """Замена фото"""
    await callback.message.edit_text(
        "🖼 <b>Замена фото</b>\n\n"
        "Отправьте новое фото:",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.editing_photo)
    await callback.answer()


@router.callback_query(F.data == "broadcast_delete_photo")
async def broadcast_delete_photo(callback: CallbackQuery, state: FSMContext):
    """Удаление фото"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["photo_id"] = None
    await state.update_data(broadcast=broadcast_data)

    await callback.message.edit_text(
        "🗑 Фото удалено.\n\n"
        "<b>Шаг 1/4: Картинка</b>\n"
        "Отправьте фото или нажмите «Пропустить»:",
        reply_markup=keyboards.get_broadcast_photo_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_photo)
    await callback.answer()


# --- Шаг 2: Текст ---

@router.message(BroadcastStates.waiting_for_text, F.text)
async def process_broadcast_text(message: Message, state: FSMContext):
    """Обработка текста рассылки"""
    logger.info(f"[BROADCAST] Received text from user {message.from_user.id}: {message.text[:50]}...")
    text = message.text

    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["text"] = text
    await state.update_data(broadcast=broadcast_data)

    await message.answer(
        f"✅ Текст сохранён!\n\n"
        f"<b>Предпросмотр текста:</b>\n"
        f"─────────────────\n"
        f"{text}\n"
        f"─────────────────\n\n"
        f"Выберите действие:",
        reply_markup=keyboards.get_broadcast_text_edit_menu(),
        parse_mode="HTML"
    )


@router.message(BroadcastStates.editing_text, F.text)
async def process_broadcast_text_edit(message: Message, state: FSMContext):
    """Обработка редактирования текста"""
    text = message.text

    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["text"] = text
    await state.update_data(broadcast=broadcast_data)

    await message.answer(
        f"✅ Текст обновлён!\n\n"
        f"<b>Предпросмотр текста:</b>\n"
        f"─────────────────\n"
        f"{text}\n"
        f"─────────────────\n\n"
        f"Выберите действие:",
        reply_markup=keyboards.get_broadcast_text_edit_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_text)


@router.callback_query(F.data == "broadcast_edit_text")
async def broadcast_edit_text(callback: CallbackQuery, state: FSMContext):
    """Редактирование текста"""
    await callback.message.edit_text(
        "✏️ <b>Редактирование текста</b>\n\n"
        "Отправьте новый текст рассылки:",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.editing_text)
    await callback.answer()


@router.callback_query(F.data == "broadcast_text_next")
async def broadcast_text_next(callback: CallbackQuery, state: FSMContext):
    """Переход к шагу кнопки после текста"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    button_info = ""
    if broadcast_data.get("button_text") and broadcast_data.get("button_url"):
        button_info = f"\n\nТекущая кнопка: [{broadcast_data['button_text']}]({broadcast_data['button_url']})"

    await callback.message.edit_text(
        f"🔘 <b>Шаг 3/4: URL-кнопка</b>\n\n"
        f"Хотите добавить кнопку со ссылкой под сообщением?{button_info}",
        reply_markup=keyboards.get_broadcast_button_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_button)
    await callback.answer()


# --- Шаг 3: Кнопка ---

@router.callback_query(F.data == "broadcast_add_button")
async def broadcast_add_button(callback: CallbackQuery, state: FSMContext):
    """Добавление кнопки"""
    await callback.message.edit_text(
        "🔘 <b>Добавление URL-кнопки</b>\n\n"
        "Отправьте данные кнопки в формате:\n"
        "<code>Текст кнопки | https://ссылка.com</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>Наш канал | https://t.me/channel</code>",
        reply_markup=keyboards.get_broadcast_button_input_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_button)
    await callback.answer()


@router.message(BroadcastStates.waiting_for_button, F.text)
async def process_broadcast_button(message: Message, state: FSMContext):
    """Обработка данных кнопки"""
    text = message.text.strip()

    # Парсим формат "Текст | URL"
    if "|" not in text:
        await message.answer(
            "❌ Неверный формат!\n\n"
            "Используйте формат:\n"
            "<code>Текст кнопки | https://ссылка.com</code>",
            reply_markup=keyboards.get_broadcast_button_input_menu(),
            parse_mode="HTML"
        )
        return

    parts = text.split("|", 1)
    button_text = parts[0].strip()
    button_url = parts[1].strip()

    # Валидация URL
    if not button_url.startswith(("http://", "https://", "tg://")):
        await message.answer(
            "❌ Неверный URL!\n\n"
            "URL должен начинаться с <code>http://</code>, <code>https://</code> или <code>tg://</code>",
            reply_markup=keyboards.get_broadcast_button_input_menu(),
            parse_mode="HTML"
        )
        return

    if not button_text:
        await message.answer(
            "❌ Текст кнопки не может быть пустым!",
            reply_markup=keyboards.get_broadcast_button_input_menu()
        )
        return

    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["button_text"] = button_text
    broadcast_data["button_url"] = button_url
    await state.update_data(broadcast=broadcast_data)

    await message.answer(
        f"✅ Кнопка добавлена!\n\n"
        f"<b>Текст:</b> {button_text}\n"
        f"<b>Ссылка:</b> {button_url}\n\n"
        f"Выберите действие:",
        reply_markup=keyboards.get_broadcast_button_edit_menu(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "broadcast_button_back")
async def broadcast_button_back(callback: CallbackQuery, state: FSMContext):
    """Назад к меню кнопки"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    button_info = ""
    if broadcast_data.get("button_text") and broadcast_data.get("button_url"):
        button_info = f"\n\nТекущая кнопка: [{broadcast_data['button_text']}]({broadcast_data['button_url']})"

    await callback.message.edit_text(
        f"🔘 <b>Шаг 3/4: URL-кнопка</b>\n\n"
        f"Хотите добавить кнопку со ссылкой под сообщением?{button_info}",
        reply_markup=keyboards.get_broadcast_button_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_skip_button")
async def broadcast_skip_button(callback: CallbackQuery, state: FSMContext):
    """Пропуск шага с кнопкой"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    pin_enabled = broadcast_data.get("pin_enabled", False)

    await callback.message.edit_text(
        "📌 <b>Шаг 4/4: Закрепление</b>\n\n"
        "Закрепить сообщение в чате у получателей?\n"
        "<i>(Старое закреплённое сообщение будет откреплено)</i>",
        reply_markup=keyboards.get_broadcast_pin_menu(pin_enabled),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.pin_step)
    await callback.answer()


@router.callback_query(F.data == "broadcast_button_next")
async def broadcast_button_next(callback: CallbackQuery, state: FSMContext):
    """Переход к шагу закрепления"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    pin_enabled = broadcast_data.get("pin_enabled", False)

    await callback.message.edit_text(
        "📌 <b>Шаг 4/4: Закрепление</b>\n\n"
        "Закрепить сообщение в чате у получателей?\n"
        "<i>(Старое закреплённое сообщение будет откреплено)</i>",
        reply_markup=keyboards.get_broadcast_pin_menu(pin_enabled),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.pin_step)
    await callback.answer()


@router.callback_query(F.data == "broadcast_delete_button")
async def broadcast_delete_button(callback: CallbackQuery, state: FSMContext):
    """Удаление кнопки"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    broadcast_data["button_text"] = None
    broadcast_data["button_url"] = None
    await state.update_data(broadcast=broadcast_data)

    await callback.message.edit_text(
        "🗑 Кнопка удалена.\n\n"
        "🔘 <b>Шаг 3/4: URL-кнопка</b>\n\n"
        "Хотите добавить кнопку со ссылкой под сообщением?",
        reply_markup=keyboards.get_broadcast_button_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Шаг 4: Закрепление (Toggle) ---

@router.callback_query(F.data == "broadcast_toggle_pin")
async def broadcast_toggle_pin(callback: CallbackQuery, state: FSMContext):
    """Переключение режима закрепления"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    # Переключаем состояние
    broadcast_data["pin_enabled"] = not broadcast_data.get("pin_enabled", False)
    await state.update_data(broadcast=broadcast_data)

    pin_enabled = broadcast_data["pin_enabled"]
    status_text = "включено ✅" if pin_enabled else "выключено ❌"

    await callback.message.edit_text(
        f"📌 <b>Шаг 4/4: Закрепление</b>\n\n"
        f"Закрепление: <b>{status_text}</b>\n\n"
        f"Закрепить сообщение в чате у получателей?\n"
        f"<i>(Старое закреплённое сообщение будет откреплено)</i>",
        reply_markup=keyboards.get_broadcast_pin_menu(pin_enabled),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Предпросмотр ---

@router.callback_query(F.data == "broadcast_preview")
async def broadcast_preview(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Показать предпросмотр рассылки"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    # Проверяем наличие текста
    if not broadcast_data.get("text"):
        await callback.answer("❌ Текст сообщения обязателен!", show_alert=True)
        return

    await state.set_state(BroadcastStates.preview)

    # Формируем информацию о рассылке
    mode_text = "всем пользователям" if broadcast_data.get("mode") == "all" else "по списку ID"
    recipients_count = len(broadcast_data.get("target_ids", []))
    pin_status = "✅ Да" if broadcast_data.get("pin_enabled") else "❌ Нет"

    info_text = (
        f"👁 <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>\n\n"
        f"📤 Режим: {mode_text}\n"
        f"👥 Получателей: {recipients_count}\n"
        f"📌 Закрепить: {pin_status}\n"
        f"─────────────────\n"
        f"<i>Ниже — сообщение как его увидят пользователи:</i>"
    )

    await callback.message.edit_text(info_text, parse_mode="HTML")

    # Формируем клавиатуру с URL-кнопкой если есть
    reply_markup = None
    if broadcast_data.get("button_text") and broadcast_data.get("button_url"):
        reply_markup = keyboards.get_broadcast_url_button(
            broadcast_data["button_text"],
            broadcast_data["button_url"]
        )

    # Отправляем предпросмотр сообщения
    try:
        if broadcast_data.get("photo_id"):
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=broadcast_data["photo_id"],
                caption=broadcast_data["text"],
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=broadcast_data["text"],
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка при формировании предпросмотра:\n<code>{e}</code>\n\n"
            f"Проверьте правильность HTML-разметки.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Отправляем меню действий
    await callback.message.answer(
        "─────────────────\n"
        "👆 <b>Так выглядит ваше сообщение</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_broadcast_preview_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# --- Редактирование из предпросмотра ---

@router.callback_query(F.data == "broadcast_edit")
async def broadcast_edit(callback: CallbackQuery, state: FSMContext):
    """Меню выбора что редактировать"""
    await callback.message.edit_text(
        "✏️ <b>Редактирование рассылки</b>\n\n"
        "Что вы хотите изменить?",
        reply_markup=keyboards.get_broadcast_edit_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_edit_photo_step")
async def broadcast_edit_photo_step(callback: CallbackQuery, state: FSMContext):
    """Редактирование фото из меню редактирования"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    if broadcast_data.get("photo_id"):
        await callback.message.edit_text(
            "🖼 <b>Редактирование картинки</b>\n\n"
            "Текущее фото загружено.\n"
            "Выберите действие:",
            reply_markup=keyboards.get_broadcast_photo_edit_menu(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "🖼 <b>Картинка</b>\n\n"
            "Отправьте фото или нажмите «Пропустить»:",
            reply_markup=keyboards.get_broadcast_photo_menu()
        )

    await state.set_state(BroadcastStates.waiting_for_photo)
    await callback.answer()


@router.callback_query(F.data == "broadcast_edit_text_step")
async def broadcast_edit_text_step(callback: CallbackQuery, state: FSMContext):
    """Редактирование текста из меню редактирования"""
    await callback.message.edit_text(
        "📝 <b>Редактирование текста</b>\n\n"
        "Отправьте новый текст рассылки:",
        reply_markup=keyboards.get_broadcast_text_menu(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.editing_text)
    await callback.answer()


@router.callback_query(F.data == "broadcast_edit_button_step")
async def broadcast_edit_button_step(callback: CallbackQuery, state: FSMContext):
    """Редактирование кнопки из меню редактирования"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    if broadcast_data.get("button_text") and broadcast_data.get("button_url"):
        await callback.message.edit_text(
            f"🔘 <b>Редактирование кнопки</b>\n\n"
            f"Текущая кнопка:\n"
            f"<b>Текст:</b> {broadcast_data['button_text']}\n"
            f"<b>Ссылка:</b> {broadcast_data['button_url']}\n\n"
            f"Выберите действие:",
            reply_markup=keyboards.get_broadcast_button_edit_menu(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "🔘 <b>URL-кнопка</b>\n\n"
            "Хотите добавить кнопку со ссылкой под сообщением?",
            reply_markup=keyboards.get_broadcast_button_menu(),
            parse_mode="HTML"
        )

    await state.set_state(BroadcastStates.waiting_for_button)
    await callback.answer()


@router.callback_query(F.data == "broadcast_edit_pin_step")
async def broadcast_edit_pin_step(callback: CallbackQuery, state: FSMContext):
    """Редактирование закрепления из меню редактирования"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())
    pin_enabled = broadcast_data.get("pin_enabled", False)

    await callback.message.edit_text(
        "📌 <b>Закрепление</b>\n\n"
        "Закрепить сообщение в чате у получателей?",
        reply_markup=keyboards.get_broadcast_pin_menu(pin_enabled),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.pin_step)
    await callback.answer()


# --- Отмена рассылки ---

@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await callback.message.edit_text(
        "❓ <b>Отменить рассылку?</b>\n\n"
        "Все введённые данные будут потеряны.",
        reply_markup=keyboards.get_broadcast_confirm_cancel_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_confirm_cancel")
async def broadcast_confirm_cancel(callback: CallbackQuery, state: FSMContext):
    """Подтверждение отмены рассылки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена.\n\n"
        "Возвращаю в админ-панель.",
        reply_markup=keyboards.get_admin_menu()
    )
    await callback.answer()


# --- Отправка рассылки ---

@router.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Начало отправки рассылки"""
    data = await state.get_data()
    broadcast_data = data.get("broadcast", get_default_broadcast_data())

    target_ids = broadcast_data.get("target_ids", [])
    if not target_ids:
        await callback.answer("❌ Нет получателей!", show_alert=True)
        return

    text = broadcast_data.get("text")
    if not text:
        await callback.answer("❌ Текст сообщения обязателен!", show_alert=True)
        return

    await callback.answer("🚀 Запускаю рассылку...")

    # Отправляем сообщение о начале
    status_msg = await callback.message.edit_text(
        f"🚀 <b>Рассылка запущена!</b>\n\n"
        f"👥 Получателей: {len(target_ids)}\n"
        f"⏳ Прогресс: 0/{len(target_ids)} (0%)",
        parse_mode="HTML"
    )

    # Формируем клавиатуру
    reply_markup = None
    if broadcast_data.get("button_text") and broadcast_data.get("button_url"):
        reply_markup = keyboards.get_broadcast_url_button(
            broadcast_data["button_text"],
            broadcast_data["button_url"]
        )

    # Статистика
    success_count = 0
    blocked_count = 0
    error_count = 0
    start_time = time.time()

    # Получаем данные для отправки
    photo_id = broadcast_data.get("photo_id")
    pin_enabled = broadcast_data.get("pin_enabled", False)

    # Отправка с anti-flood
    for idx, user_id in enumerate(target_ids, 1):
        try:
            # Отправляем сообщение
            if photo_id:
                sent_msg = await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            else:
                sent_msg = await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )

            # Закрепляем если нужно
            if pin_enabled:
                try:
                    await bot.pin_chat_message(
                        chat_id=user_id,
                        message_id=sent_msg.message_id,
                        disable_notification=True
                    )
                except Exception:
                    pass  # Игнорируем ошибки закрепления

            success_count += 1

        except TelegramForbiddenError:
            # Бот заблокирован пользователем
            blocked_count += 1
        except TelegramNotFound:
            # Чат/пользователь не найден
            blocked_count += 1
        except TelegramBadRequest as e:
            # Другие ошибки Telegram API
            error_count += 1
            logger.warning(f"Broadcast error for user {user_id}: {e}")
        except Exception as e:
            error_count += 1
            logger.error(f"Unexpected broadcast error for user {user_id}: {e}")

        # Anti-flood delay
        await asyncio.sleep(0.05)

        # Обновляем прогресс каждые 10 сообщений или в конце
        if idx % 10 == 0 or idx == len(target_ids):
            progress_percent = int((idx / len(target_ids)) * 100)
            try:
                await status_msg.edit_text(
                    f"🚀 <b>Рассылка в процессе...</b>\n\n"
                    f"👥 Получателей: {len(target_ids)}\n"
                    f"⏳ Прогресс: {idx}/{len(target_ids)} ({progress_percent}%)\n\n"
                    f"✅ Успешно: {success_count}\n"
                    f"🚫 Заблокировали: {blocked_count}\n"
                    f"⚠️ Ошибки: {error_count}",
                    parse_mode="HTML"
                )
            except Exception:
                pass  # Игнорируем ошибки обновления статуса

    # Расчёт времени
    elapsed_time = round(time.time() - start_time, 1)

    # Финальный отчёт
    await status_msg.edit_text(
        f"📊 <b>Рассылка завершена!</b>\n\n"
        f"✅ Успешно доставлено: {success_count}\n"
        f"🚫 Бот заблокирован: {blocked_count}\n"
        f"⚠️ Ошибки: {error_count}\n"
        f"⏱ Время выполнения: {elapsed_time} сек",
        reply_markup=keyboards.get_admin_menu(),
        parse_mode="HTML"
    )

    # Очищаем состояние
    await state.clear()

    logger.info(
        f"Broadcast completed: success={success_count}, blocked={blocked_count}, "
        f"errors={error_count}, time={elapsed_time}s"
    )
