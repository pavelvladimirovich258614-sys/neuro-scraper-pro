"""
User Handlers Module
Handles all user interactions, FSM states, and parsing logic
"""

import logging
import asyncio
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

import keyboards
import config
from database import db
from services.telethon_core import telethon_core
from utils.excel_generator import excel_generator, SmartExportResult

logger = logging.getLogger(__name__)

# Минимальный интервал между обновлениями прогресса (секунды) — из config
PROGRESS_UPDATE_INTERVAL = config.PROGRESS_UPDATE_INTERVAL

# Реестр пользователей с активным парсингом — не даём одному юзеру запускать
# два парсинга одновременно (иначе конкурируют за одну сессию и путают FSM).
_active_parsings: set = set()

router = Router()


# ===== ОБЩИЕ ХЕЛПЕРЫ ЗАВЕРШЕНИЯ ПАРСИНГА =====

async def _record_parsing(user_id: int, target_link: str, parse_type: str,
                          time_filter, result) -> None:
    """Списать лимит и записать парсинг в историю (общее для всех режимов)."""
    await db.decrease_limit(user_id)
    await db.add_parsing_history(
        user_id=user_id,
        target_link=target_link,
        parse_type=parse_type,
        time_filter=time_filter,
        users_found=len(result.users),
        admins_found=len(result.admins)
    )


async def _remaining_text(user_id: int) -> str:
    """Текст об остатке парсингов (пусто для премиума/безлимита)."""
    limit_info = await db.check_limit(user_id)
    if limit_info["is_premium"]:
        return ""
    return f"\n\n💎 Осталось парсингов: <b>{limit_info['remaining']}</b>"


# ===== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ =====

async def check_subscription(bot, user_id: int, skip_cache: bool = False) -> bool:
    """Проверяет подписку пользователя на обязательный канал.

    Делегирует в единую функцию is_user_subscribed (общий TTL-кэш + Telegram
    API + синхронизация БД), чтобы хендлеры и middleware использовали одну и ту
    же логику. skip_cache=True форсирует проверку через API (минуя кэш).
    """
    from middlewares.subscription_middleware import is_user_subscribed
    return await is_user_subscribed(bot, user_id, force=skip_cache)


# FSM States
class AddAccountStates(StatesGroup):
    """Состояния для добавления аккаунта"""
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()


class ParsingStates(StatesGroup):
    """Состояния для парсинга"""
    select_time_filter = State()
    select_session = State()
    enter_link = State()
    parsing = State()
    # Новые состояния для Advanced Features
    select_chat_mode = State()  # Выбор режима парсинга чата
    select_dialog = State()  # Выбор чата из "Мои чаты"
    parsing_settings = State()  # Настройки перед парсингом
    enter_limit = State()  # Ввод лимита вручную
    enter_custom_posts = State()  # Ввод количества постов (до 200)


class JoinChatStates(StatesGroup):
    """Состояния для вступления в чат"""
    enter_link = State()


# Команда /start с поддержкой реферальных ссылок
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start с Deep Linking для рефералов"""
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Проверяем реферальный аргумент (Deep Linking)
    referrer_id = None
    args = message.text.split()
    if len(args) > 1:
        try:
            potential_referrer = int(args[1])
            # Проверяем что реферер существует и это не сам пользователь
            if potential_referrer != user_id:
                referrer_user = await db.get_user(potential_referrer)
                if referrer_user:
                    referrer_id = potential_referrer
                    logger.info(f"User {user_id} came from referral link of {referrer_id}")
        except (ValueError, IndexError):
            pass

    # Создаем или обновляем пользователя в БД
    user = await db.get_user(user_id)
    is_new_user = False
    
    if not user:
        is_new_user = True
        await db.create_user(user_id, username, first_name, last_name, referrer_id)
        
        # Начисляем бонус рефереру если есть
        if referrer_id:
            bonus_added = await db.add_referral_bonus(referrer_id, user_id)
            if bonus_added:
                # Уведомляем реферера о новом приглашённом (с кнопкой меню!)
                try:
                    from aiogram import Bot
                    bot = message.bot
                    await bot.send_message(
                        referrer_id,
                        f"🎉 <b>По вашей ссылке пришёл друг!</b>\n\n"
                        f"Вам начислено <b>+{config.REFERRAL_BONUS} парсинга</b>!\n\n"
                        f"Продолжайте приглашать друзей для получения бонусов.\n\n"
                        f"👇 Нажмите кнопку ниже для продолжения:",
                        reply_markup=keyboards.get_main_menu(),  # Кнопка меню!
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify referrer {referrer_id}: {e}")
    else:
        await db.update_user_activity(user_id)

    # ===== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ =====
    is_subscribed = await check_subscription(message.bot, user_id)
    
    if not is_subscribed:
        # Пользователь НЕ подписан - показываем сообщение с просьбой подписаться
        user_name = first_name or username or "Пользователь"
        subscribe_text = f"""
👋 <b>{user_name}</b>, для того чтобы пользоваться ботом подпишись на канал

📢 Подпишитесь на наш канал, чтобы получить доступ ко всем функциям бота.
"""
        await message.answer(
            subscribe_text,
            reply_markup=keyboards.get_subscription_check_menu(),
            parse_mode="HTML"
        )
        return  # Прерываем выполнение, не показываем главное меню

    # ===== ПОЛЬЗОВАТЕЛЬ ПОДПИСАН - показываем главное меню =====
    welcome_text = f"""
👋 <b>Добро пожаловать в NeuroScraper Pro!</b>

🔥 <b>Профессиональный инструмент для парсинга аудитории Telegram</b>

<b>Возможности бота:</b>

📊 <b>Парсинг каналов</b> — комментаторы из постов
👥 <b>Парсинг чатов</b> — участники и активные
🔒 <b>Мои Чаты</b> — парсинг закрытых групп
📈 <b>Умная выгрузка</b> — 4 файла (админы, премиум, обычные, полный отчёт)

⏱ <b>Фильтры:</b> день / неделя / месяц / 3 месяца

🔐 <b>Многоаккаунтность</b> — добавляйте свои Telegram аккаунты

💎 <b>Ваш лимит:</b> {config.FREE_PARSING_LIMIT} бесплатных парсингов
👥 <b>Реферальная программа:</b> +{config.REFERRAL_BONUS} парсинга за друга!

Выберите действие в меню ниже:
"""

    await message.answer(
        welcome_text,
        reply_markup=keyboards.get_main_menu(),
        parse_mode="HTML"
    )


# ===== CALLBACK ДЛЯ ПРОВЕРКИ ПОДПИСКИ =====

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    """Обработчик кнопки 'Проверить подписку'"""
    user_id = callback.from_user.id
    
    # Очищаем кэш middleware для этого пользователя
    from middlewares.subscription_middleware import clear_subscription_cache
    clear_subscription_cache(user_id)
    
    # Проверяем подписку напрямую (skip_cache=True)
    is_subscribed = await check_subscription(callback.bot, user_id, skip_cache=True)
    
    if is_subscribed:
        # Пользователь подписан - показываем главное меню
        await callback.message.edit_text(
            f"""
👋 <b>Добро пожаловать в NeuroScraper Pro!</b>

🔥 <b>Профессиональный инструмент для парсинга аудитории Telegram</b>

<b>Возможности бота:</b>

📊 <b>Парсинг каналов</b> — комментаторы из постов
👥 <b>Парсинг чатов</b> — участники и активные
🔒 <b>Мои Чаты</b> — парсинг закрытых групп
📈 <b>Умная выгрузка</b> — 4 файла (админы, премиум, обычные, полный отчёт)

⏱ <b>Фильтры:</b> день / неделя / месяц / 3 месяца

🔐 <b>Многоаккаунтность</b> — добавляйте свои Telegram аккаунты

💎 <b>Ваш лимит:</b> {config.FREE_PARSING_LIMIT} бесплатных парсингов
👥 <b>Реферальная программа:</b> +{config.REFERRAL_BONUS} парсинга за друга!

Выберите действие в меню ниже:
""",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
        await callback.answer("✅ Подписка подтверждена!")
    else:
        # Пользователь НЕ подписан
        await callback.message.edit_text(
            "❌ <b>К сожалению вы не подписаны на канал</b>\n\n"
            "Подпишитесь на канал и нажмите кнопку проверки снова.",
            reply_markup=keyboards.get_not_subscribed_menu(),
            parse_mode="HTML"
        )
        await callback.answer("❌ Вы не подписаны на канал", show_alert=True)


# Главное меню
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=keyboards.get_main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# ===== ДОБАВЛЕНИЕ АККАУНТА =====

@router.callback_query(F.data == "add_account")
async def start_add_account(callback: CallbackQuery, state: FSMContext):
    """Начало процесса добавления аккаунта"""
    text = """
➕ <b>Добавление аккаунта</b>

Отправьте номер телефона в международном формате.

<b>Примеры:</b>
• +79991234567
• +380501234567
• +77051234567

<i>Убедитесь, что номер указан правильно!</i>
"""
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AddAccountStates.waiting_for_phone)
    await callback.answer()


@router.message(AddAccountStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка введенного телефона"""
    phone = message.text.strip()
    user_id = message.from_user.id

    # Валидация номера
    if not phone.startswith('+') or len(phone) < 10:
        await message.answer(
            "❌ Неверный формат номера!\n\nИспользуйте формат: +79991234567",
            reply_markup=keyboards.get_cancel_button()
        )
        return

    # Генерируем имя сессии
    session_name = f"user_{user_id}_{phone.replace('+', '')}"

    # Отправляем код (показываем статус)
    wait_msg = await message.answer("⏳ Отправляем код...")

    success, msg, phone_code_hash = await telethon_core.send_code(phone, session_name)

    if not success:
        # Редактируем сообщение вместо удаления+создания
        await wait_msg.edit_text(
            f"❌ <b>Ошибка:</b> {msg}",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return

    # Проверяем на специальный код "ALREADY_AUTHORIZED"
    if msg == "ALREADY_AUTHORIZED":
        # Сессия уже авторизована - сохраняем и завершаем
        await db.save_user_session(user_id, phone, session_name)
        await wait_msg.edit_text(
            f"✅ <b>Аккаунт успешно добавлен!</b>\n\n"
            f"📞 Номер: <code>{phone}</code>\n\n"
            f"Сессия была восстановлена из кэша.\n"
            f"Теперь вы можете использовать этот аккаунт для парсинга.",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Сохраняем данные в FSM (включая ID сообщения для удаления)
    await state.update_data(
        phone=phone,
        session_name=session_name,
        phone_code_hash=phone_code_hash,
        last_auth_msg_id=wait_msg.message_id  # Для очистки
    )

    # Редактируем wait_msg вместо создания нового
    await wait_msg.edit_text(
        f"✅ <b>Код отправлен!</b>\n\n"
        f"📞 Номер: <code>{phone}</code>\n\n"
        f"📨 Telegram отправил вам код подтверждения.\n"
        f"Проверьте:\n"
        f"  • Сообщения от Telegram\n"
        f"  • Приложение Telegram на телефоне\n"
        f"  • SMS (если включено)\n\n"
        f"<b>Введите 5-значный код:</b>\n"
        f"<i>Например: 12345</i>",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(AddAccountStates.waiting_for_code)


@router.message(AddAccountStates.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    """Обработка кода авторизации"""
    code = message.text.strip().replace('-', '').replace(' ', '')

    # Удаляем сообщение пользователя с кодом (безопасность)
    try:
        await message.delete()
    except Exception:
        pass

    # Проверяем что код похож на валидный
    if not code.isdigit() or len(code) < 4 or len(code) > 6:
        await message.answer(
            "❌ <b>Неверный формат кода!</b>\n\n"
            "Код должен состоять из 5 цифр.\n"
            "Введите код ещё раз:",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return

    data = await state.get_data()

    phone = data['phone']
    session_name = data['session_name']
    phone_code_hash = data['phone_code_hash']

    wait_msg = await message.answer("⏳ Проверяем код...")

    success, msg = await telethon_core.sign_in(
        phone,
        code,
        phone_code_hash,
        session_name
    )

    # Требуется 2FA
    if msg == "NEED_2FA":
        # Редактируем сообщение вместо удаления
        await wait_msg.edit_text(
            "🔐 <b>Требуется пароль 2FA</b>\n\n"
            "У вас включена двухфакторная аутентификация.\n\n"
            "<b>Введите облачный пароль:</b>\n"
            "<i>(тот, который вы установили в настройках Telegram)</i>",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        await state.set_state(AddAccountStates.waiting_for_2fa)
        return

    # Код устарел - автоматически запрашиваем новый
    if msg == "CODE_EXPIRED":
        logger.info(f"Code expired for {phone}, requesting new code...")
        success_resend, msg_resend, new_hash = await telethon_core.send_code(phone, session_name)
        
        if success_resend and new_hash:
            # Обновляем hash в состоянии
            await state.update_data(phone_code_hash=new_hash)
            await wait_msg.edit_text(
                "⏰ <b>Код устарел!</b>\n\n"
                "📨 Новый код отправлен на ваш Telegram.\n\n"
                "<b>Введите новый код:</b>",
                reply_markup=keyboards.get_cancel_button(),
                parse_mode="HTML"
            )
        elif msg_resend == "ALREADY_AUTHORIZED":
            # Сессия уже авторизована
            await db.save_user_session(message.from_user.id, phone, session_name)
            await wait_msg.edit_text(
                f"✅ <b>Аккаунт успешно добавлен!</b>\n\n"
                f"📞 Номер: <code>{phone}</code>\n\n"
                f"Сессия была восстановлена.",
                reply_markup=keyboards.get_main_menu(),
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await wait_msg.edit_text(
                f"❌ <b>Код устарел</b>\n\n"
                f"Не удалось запросить новый код: {msg_resend}\n\n"
                f"Нажмите <b>Отмена</b> и начните заново.",
                reply_markup=keyboards.get_cancel_button(),
                parse_mode="HTML"
            )
        return

    if not success:
        # Редактируем сообщение вместо удаления
        await wait_msg.edit_text(
            f"❌ <b>Ошибка:</b> {msg}\n\n"
            f"Попробуйте ввести код ещё раз.\n"
            f"Если код устарел, нажмите <b>Отмена</b> и начните заново.",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return

    # Успешная авторизация
    user_id = message.from_user.id
    await db.save_user_session(user_id, phone, session_name)

    # Редактируем финальное сообщение
    await wait_msg.edit_text(
        f"✅ <b>Аккаунт успешно добавлен!</b>\n\n"
        f"📞 Номер: <code>{phone}</code>\n\n"
        f"Теперь вы можете использовать этот аккаунт для парсинга закрытых чатов, "
        f"в которых состоит этот аккаунт.",
        reply_markup=keyboards.get_main_menu(),
        parse_mode="HTML"
    )
    await state.clear()


@router.message(AddAccountStates.waiting_for_2fa)
async def process_2fa(message: Message, state: FSMContext):
    """Обработка пароля 2FA"""
    password = message.text.strip()
    data = await state.get_data()

    phone = data['phone']
    session_name = data['session_name']
    phone_code_hash = data['phone_code_hash']

    # Удаляем сообщение с паролем (безопасность!)
    try:
        await message.delete()
    except Exception:
        pass

    wait_msg = await message.answer("⏳ Проверяем пароль...")

    # Повторная попытка входа с паролем
    success, msg = await telethon_core.sign_in(
        phone,
        "",  # Код уже был использован
        phone_code_hash,
        session_name,
        password=password
    )

    if not success:
        # Редактируем сообщение вместо удаления
        await wait_msg.edit_text(
            f"❌ <b>Ошибка:</b> {msg}\n\n"
            f"Попробуйте ввести пароль еще раз:",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return

    # Успешная авторизация
    user_id = message.from_user.id
    await db.save_user_session(user_id, phone, session_name)

    # Редактируем финальное сообщение
    await wait_msg.edit_text(
        f"✅ <b>Аккаунт успешно добавлен!</b>\n\n"
        f"📞 Номер: <code>{phone}</code>\n\n"
        f"Теперь вы можете использовать этот аккаунт для парсинга.",
        reply_markup=keyboards.get_main_menu(),
        parse_mode="HTML"
    )
    await state.clear()


# Мои аккаунты
@router.callback_query(F.data == "my_accounts")
async def show_my_accounts(callback: CallbackQuery):
    """Показать список аккаунтов пользователя"""
    user_id = callback.from_user.id
    sessions = await db.get_user_sessions(user_id)

    if not sessions:
        text = """
📱 <b>Мои аккаунты</b>

У вас пока нет добавленных аккаунтов.

<b>Зачем добавлять аккаунт?</b>
Для парсинга закрытых чатов, в которых состоит ваш аккаунт.

Нажмите кнопку ниже, чтобы добавить аккаунт:
"""
    else:
        text = f"📱 <b>Ваши аккаунты ({len(sessions)}):</b>\n\n"
        for idx, session in enumerate(sessions, 1):
            text += f"  {idx}. <code>{session['phone_number']}</code>\n"

        text += "\n<i>Нажмите на номер для управления</i>"

    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_my_accounts_menu(sessions),
        parse_mode="HTML"
    )
    await callback.answer()


# Просмотр конкретного аккаунта
@router.callback_query(F.data.startswith("view_account_"))
async def view_account(callback: CallbackQuery):
    """Просмотр информации об аккаунте"""
    session_name = callback.data.replace("view_account_", "")
    user_id = callback.from_user.id
    
    # Получаем сессии пользователя
    sessions = await db.get_user_sessions(user_id)
    session_info = None
    for s in sessions:
        if s["session_name"] == session_name:
            session_info = s
            break
    
    if not session_info:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    phone = session_info["phone_number"]
    created = session_info.get("created_at", "N/A")
    
    text = f"""
📱 <b>Информация об аккаунте</b>

📞 Номер: <code>{phone}</code>
📅 Добавлен: {created[:10] if created != "N/A" else "N/A"}
✅ Статус: Активен

<b>Действия:</b>
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_account_actions_menu(session_name, phone),
        parse_mode="HTML"
    )
    await callback.answer()


# Удаление аккаунта - запрос подтверждения
@router.callback_query(F.data.startswith("delete_session_"))
async def delete_session_confirm(callback: CallbackQuery):
    """Запрос подтверждения удаления аккаунта"""
    session_name = callback.data.replace("delete_session_", "")
    user_id = callback.from_user.id
    
    # Получаем информацию о сессии
    sessions = await db.get_user_sessions(user_id)
    phone = "неизвестно"
    for s in sessions:
        if s["session_name"] == session_name:
            phone = s["phone_number"]
            break
    
    text = f"""
⚠️ <b>Подтверждение удаления</b>

Вы уверены, что хотите удалить аккаунт?

📞 Номер: <code>{phone}</code>

<b>Внимание:</b> После удаления для повторного добавления потребуется заново ввести код из Telegram.
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.get_confirm_delete_menu(session_name),
        parse_mode="HTML"
    )
    await callback.answer()


# Подтверждение удаления аккаунта
@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_session(callback: CallbackQuery):
    """Удалить аккаунт после подтверждения"""
    session_name = callback.data.replace("confirm_delete_", "")
    user_id = callback.from_user.id
    
    # Удаляем сессию из БД
    await db.deactivate_session(session_name)
    
    # Удаляем файл сессии
    await telethon_core.delete_session(session_name)
    
    await callback.message.edit_text(
        "✅ <b>Аккаунт успешно удалён!</b>\n\n"
        "Теперь вы можете добавить его заново при необходимости.",
        parse_mode="HTML"
    )
    
    # Показываем обновлённый список
    sessions = await db.get_user_sessions(user_id)
    await callback.message.answer(
        "📱 <b>Мои аккаунты</b>",
        reply_markup=keyboards.get_my_accounts_menu(sessions),
        parse_mode="HTML"
    )
    await callback.answer()


# ===== ВСТУПЛЕНИЕ В ЧАТ/КАНАЛ =====

@router.callback_query(F.data == "join_chat_menu")
async def join_chat_menu(callback: CallbackQuery, state: FSMContext):
    """Меню вступления в чат - выбор аккаунта"""
    user_id = callback.from_user.id
    sessions = await db.get_user_sessions(user_id)
    
    if not sessions:
        await callback.answer("❌ Сначала добавьте аккаунт!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔗 <b>Вступление в чат/канал</b>\n\n"
        "Выберите аккаунт, с которого нужно вступить:\n\n"
        "<i>Этот аккаунт автоматически присоединится к указанной группе/каналу по ссылке.</i>",
        reply_markup=keyboards.get_join_chat_session_menu(sessions),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("join_with_"))
async def join_with_account(callback: CallbackQuery, state: FSMContext):
    """Выбран аккаунт для вступления"""
    session_name = callback.data.replace("join_with_", "")
    
    await state.update_data(join_session_name=session_name)
    
    await callback.message.edit_text(
        "🔗 <b>Отправьте ссылку на чат/канал</b>\n\n"
        "<b>Поддерживаемые форматы:</b>\n"
        "• https://t.me/channel_name — публичный\n"
        "• https://t.me/+ABC123xyz — приватный\n"
        "• https://t.me/joinchat/ABC123 — старый формат\n"
        "• @channel_name\n\n"
        "<i>Аккаунт автоматически вступит в указанный чат.</i>",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(JoinChatStates.enter_link)
    await callback.answer()


@router.message(JoinChatStates.enter_link)
async def process_join_link(message: Message, state: FSMContext):
    """Обработка ссылки для вступления"""
    link = message.text.strip()
    data = await state.get_data()
    session_name = data.get("join_session_name")
    
    if not session_name:
        await message.answer(
            "❌ Ошибка: аккаунт не выбран. Начните заново.",
            reply_markup=keyboards.get_main_menu()
        )
        await state.clear()
        return
    
    # Валидация ссылки
    if not any(x in link for x in ["t.me/", "@"]):
        await message.answer(
            "❌ <b>Неверный формат ссылки!</b>\n\n"
            "Отправьте корректную ссылку на чат/канал.",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return
    
    wait_msg = await message.answer("⏳ Вступаем в чат...")
    
    success, msg, chat_title = await telethon_core.join_chat(session_name, link)
    
    await wait_msg.delete()
    
    if success:
        title_text = f"\n📌 Название: <b>{chat_title}</b>" if chat_title else ""
        await message.answer(
            f"✅ <b>{msg}</b>{title_text}\n\n"
            f"Теперь вы можете парсить этот чат, выбрав этот аккаунт.",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ <b>Не удалось вступить</b>\n\n{msg}",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
    
    await state.clear()


# ===== ПАРСИНГ КАНАЛОВ =====

@router.callback_query(F.data == "channel_menu")
async def show_channel_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню выбора режима парсинга каналов"""
    await callback.message.edit_text(
        "📊 <b>Парсинг каналов</b>\n\n"
        "Выберите режим парсинга:",
        reply_markup=keyboards.get_channel_parsing_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "parse_channel_posts")
async def start_parse_channel_posts(callback: CallbackQuery, state: FSMContext):
    """Начало парсинга последних постов канала"""
    user_id = callback.from_user.id

    # СТРОГАЯ проверка лимита
    limit_info = await db.check_limit(user_id)
    if not limit_info["has_limit"]:
        await callback.message.edit_text(
            f"❌ <b>Лимит исчерпан ({config.FREE_PARSING_LIMIT}/{config.FREE_PARSING_LIMIT})</b>\n\n"
            "Ваши бесплатные парсинги закончились.\n\n"
            "💡 <b>Способы получить больше:</b>\n"
            "• Купить подписку\n"
            f"• Пригласить друга (+{config.REFERRAL_BONUS} парсинга)",
            reply_markup=keyboards.get_limit_exceeded_menu_v2(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await state.update_data(parse_type="channel_posts", parsing_mode="multiple")
    await callback.message.edit_text(
        "📊 <b>Парсинг последних постов</b>\n\n"
        "Выберите временной фильтр активности:",
        reply_markup=keyboards.get_time_filter_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "parse_channel_single")
async def start_parse_channel_single(callback: CallbackQuery, state: FSMContext):
    """Начало парсинга конкретного поста"""
    user_id = callback.from_user.id

    # СТРОГАЯ проверка лимита
    limit_info = await db.check_limit(user_id)
    if not limit_info["has_limit"]:
        await callback.message.edit_text(
            f"❌ <b>Лимит исчерпан ({config.FREE_PARSING_LIMIT}/{config.FREE_PARSING_LIMIT})</b>\n\n"
            "Ваши бесплатные парсинги закончились.\n\n"
            "💡 <b>Способы получить больше:</b>\n"
            "• Купить подписку\n"
            f"• Пригласить друга (+{config.REFERRAL_BONUS} парсинга)",
            reply_markup=keyboards.get_limit_exceeded_menu_v2(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await state.update_data(parse_type="channel_single", parsing_mode="single")
    await callback.message.edit_text(
        "📌 <b>Парсинг конкретного поста</b>\n\n"
        "Выберите временной фильтр активности:",
        reply_markup=keyboards.get_time_filter_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# ===== ПАРСИНГ ЧАТОВ (Обновлённый с новыми режимами) =====

@router.callback_query(F.data == "parse_chat")
async def start_parse_chat(callback: CallbackQuery, state: FSMContext):
    """Начало парсинга чата - показываем выбор режима"""
    user_id = callback.from_user.id

    # СТРОГАЯ проверка лимита
    limit_info = await db.check_limit(user_id)
    if not limit_info["has_limit"]:
        await callback.message.edit_text(
            f"❌ <b>Лимит исчерпан ({config.FREE_PARSING_LIMIT}/{config.FREE_PARSING_LIMIT})</b>\n\n"
            "Ваши бесплатные парсинги закончились.\n\n"
            "💡 <b>Способы получить больше:</b>\n"
            "• Купить подписку\n"
            f"• Пригласить друга (+{config.REFERRAL_BONUS} парсинга)",
            reply_markup=keyboards.get_limit_exceeded_menu_v2(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await state.update_data(parse_type="chat")
    await callback.message.edit_text(
        "👥 <b>Парсинг чатов (группы)</b>\n\n"
        "Выберите режим парсинга:\n\n"
        "👥 <b>Участники (список)</b> — полный список членов группы\n"
        "<i>⚠️ Может быть скрыт настройками чата</i>\n\n"
        "💬 <b>Активные (кто писал)</b> — те, кто отправлял сообщения\n"
        "<i>✅ Работает всегда, если есть доступ к чату</i>\n\n"
        "🔒 <b>Мои Чаты</b> — выбрать из ваших групп",
        reply_markup=keyboards.get_chat_parsing_mode_menu(),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.select_chat_mode)
    await callback.answer()


# Выбор режима "Парсить Участников"
@router.callback_query(F.data == "chat_mode_members", ParsingStates.select_chat_mode)
async def chat_mode_members(callback: CallbackQuery, state: FSMContext):
    """Режим парсинга участников группы"""
    await state.update_data(chat_mode="members")
    await callback.message.edit_text(
        "👥 <b>Парсинг участников</b>\n\n"
        "Выберите временной фильтр:",
        reply_markup=keyboards.get_time_filter_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# Выбор режима "Парсить Активных"
@router.callback_query(F.data == "chat_mode_active", ParsingStates.select_chat_mode)
async def chat_mode_active(callback: CallbackQuery, state: FSMContext):
    """Режим парсинга активных пользователей"""
    await state.update_data(chat_mode="active")
    await callback.message.edit_text(
        "💬 <b>Парсинг активных</b>\n\n"
        "Выберите временной фильтр:",
        reply_markup=keyboards.get_time_filter_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


# Выбор режима "Мои Чаты"
@router.callback_query(F.data == "chat_mode_dialogs", ParsingStates.select_chat_mode)
async def chat_mode_dialogs(callback: CallbackQuery, state: FSMContext):
    """Режим выбора из своих чатов"""
    user_id = callback.from_user.id
    
    # Получаем сессии пользователя
    sessions = await db.get_user_sessions(user_id)
    
    if not sessions:
        await callback.message.edit_text(
            "❌ <b>Нет добавленных аккаунтов</b>\n\n"
            "Для использования функции «Мои Чаты» нужно добавить свой Telegram аккаунт.\n\n"
            "Нажмите «Добавить аккаунт» в главном меню.",
            reply_markup=keyboards.get_back_button(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Используем первую активную сессию
    session_name = sessions[0]["session_name"]
    await state.update_data(session_name=session_name, chat_mode="dialogs")
    
    wait_msg = await callback.message.edit_text(
        "⏳ Загружаем список ваших чатов...",
        parse_mode="HTML"
    )
    
    # Получаем диалоги
    success, msg, dialogs = await telethon_core.get_user_dialogs(session_name, limit=20)
    
    if not success or not dialogs:
        await callback.message.edit_text(
            f"❌ <b>Не удалось загрузить чаты</b>\n\n{msg}",
            reply_markup=keyboards.get_back_button(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    await state.update_data(dialogs=dialogs)
    
    await callback.message.edit_text(
        "🔒 <b>Ваши чаты</b>\n\n"
        "Выберите чат для парсинга:",
        reply_markup=keyboards.get_dialogs_menu(dialogs),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.select_dialog)
    await callback.answer()


# Выбор конкретного диалога
@router.callback_query(F.data.startswith("dialog_"), ParsingStates.select_dialog)
async def select_dialog_for_parsing(callback: CallbackQuery, state: FSMContext):
    """Выбран конкретный чат из списка диалогов"""
    chat_id = int(callback.data.replace("dialog_", ""))
    
    data = await state.get_data()
    dialogs = data.get("dialogs", [])
    
    # Находим название чата
    chat_title = "Чат"
    for dialog in dialogs:
        if dialog.get("id") == chat_id:
            chat_title = dialog.get("title", "Чат")
            break
    
    await state.update_data(
        selected_chat_id=chat_id,
        selected_chat_title=chat_title,
        # Настройки по умолчанию
        parse_bio=False,
        detect_gender=False,
        parse_limit=200
    )
    
    # Показываем меню настроек парсинга
    await callback.message.edit_text(
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"📌 Чат: <b>{chat_title}</b>\n\n"
        f"Настройте параметры и нажмите «Начать»:",
        reply_markup=keyboards.get_parsing_settings_menu(
            parse_bio=False,
            detect_gender=False,
            limit=200
        ),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.parsing_settings)
    await callback.answer()


# Переключатели настроек
@router.callback_query(F.data == "toggle_bio", ParsingStates.parsing_settings)
async def toggle_bio_setting(callback: CallbackQuery, state: FSMContext):
    """Переключить парсинг био"""
    data = await state.get_data()
    current = data.get("parse_bio", False)
    new_value = not current
    await state.update_data(parse_bio=new_value)
    
    chat_title = data.get("selected_chat_title", "Чат")
    
    # Предупреждение о скорости
    warning = ""
    if new_value:
        warning = "\n\n⚠️ <i>Парсинг био замедляет процесс (задержки 0.5-1.5 сек)</i>"
    
    await callback.message.edit_text(
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"📌 Чат: <b>{chat_title}</b>{warning}\n\n"
        f"Настройте параметры и нажмите «Начать»:",
        reply_markup=keyboards.get_parsing_settings_menu(
            parse_bio=new_value,
            detect_gender=data.get("detect_gender", False),
            limit=data.get("parse_limit", 200)
        ),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_gender", ParsingStates.parsing_settings)
async def toggle_gender_setting(callback: CallbackQuery, state: FSMContext):
    """Переключить определение пола"""
    data = await state.get_data()
    current = data.get("detect_gender", False)
    new_value = not current
    await state.update_data(detect_gender=new_value)
    
    chat_title = data.get("selected_chat_title", "Чат")
    
    await callback.message.edit_text(
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"📌 Чат: <b>{chat_title}</b>\n\n"
        f"Настройте параметры и нажмите «Начать»:",
        reply_markup=keyboards.get_parsing_settings_menu(
            parse_bio=data.get("parse_bio", False),
            detect_gender=new_value,
            limit=data.get("parse_limit", 200)
        ),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "set_limit", ParsingStates.parsing_settings)
async def set_limit_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос ввода лимита"""
    await callback.message.edit_text(
        "📊 <b>Установка лимита</b>\n\n"
        "Введите количество последних постов для парсинга\n"
        "(любое число от 1 до 200):\n\n"
        "Или нажмите кнопку ниже для максимума.",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "👇 Введите число или нажмите кнопку:",
        reply_markup=keyboards.get_limit_input_keyboard()
    )
    
    await state.set_state(ParsingStates.enter_limit)
    await callback.answer()


@router.message(ParsingStates.enter_limit)
async def process_limit_input(message: Message, state: FSMContext):
    """Обработка ввода лимита"""
    text = message.text.strip()
    
    # Проверяем кнопку "За всё время"
    if "♾" in text or "Макс 200" in text or "все время" in text.lower():
        limit = 200
    else:
        try:
            limit = int(text)
            if limit <= 0 or limit > 200:
                await message.answer(
                    "⚠️ Ошибка: Введите число от 1 до 200.",
                    reply_markup=keyboards.get_limit_input_keyboard()
                )
                return
        except ValueError:
            await message.answer(
                "⚠️ Ошибка: Введите число от 1 до 200.",
                reply_markup=keyboards.get_limit_input_keyboard()
            )
            return
    
    await state.update_data(parse_limit=limit)
    
    # Убираем reply клавиатуру
    await message.answer(
        f"✅ Лимит установлен: {limit}",
        reply_markup=keyboards.get_remove_keyboard()
    )
    
    # Возвращаемся к настройкам
    data = await state.get_data()
    chat_title = data.get("selected_chat_title", "Чат")
    
    await message.answer(
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"📌 Чат: <b>{chat_title}</b>\n\n"
        f"Настройте параметры и нажмите «Начать»:",
        reply_markup=keyboards.get_parsing_settings_menu(
            parse_bio=data.get("parse_bio", False),
            detect_gender=data.get("detect_gender", False),
            limit=limit
        ),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.parsing_settings)


# Начать парсинг с настройками (для "Мои Чаты")
@router.callback_query(F.data == "start_parsing_with_settings", ParsingStates.parsing_settings)
async def start_parsing_with_settings(callback: CallbackQuery, state: FSMContext):
    """Запуск парсинга с выбранными настройками (только для 'Мои Чаты')"""
    user_id = callback.from_user.id
    data = await state.get_data()
    
    chat_id = data.get("selected_chat_id")
    session_name = data.get("session_name")
    parse_bio = data.get("parse_bio", False)
    detect_gender = data.get("detect_gender", False)
    parse_limit = data.get("parse_limit", 200)
    
    # Проверяем наличие данных для "Мои Чаты" flow
    if not chat_id:
        # Может быть это обычный flow с link - перенаправляем
        link = data.get("link")
        if link:
            logger.warning(f"[start_parsing_with_settings] Redirecting to start_parsing, link found: {link}")
            # Вызываем правильный хэндлер напрямую
            await start_parsing(callback, state)
            return
        
        await callback.message.edit_text(
            "❌ Ошибка: сессия истекла. Начните заново из главного меню.",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
        await state.clear()
        await callback.answer()
        return
    
    if not session_name:
        # Пробуем получить сессию автоматически
        session_name, _ = telethon_core.get_smart_session(user_id)
        await state.update_data(session_name=session_name)

    # Guard: не запускаем второй параллельный парсинг для того же пользователя
    if user_id in _active_parsings:
        await callback.answer(
            "⏳ У вас уже идёт парсинг. Дождитесь его завершения.",
            show_alert=True
        )
        return

    _active_parsings.add(user_id)
    # Индикатор очереди: если сессия занята другим парсингом — предупреждаем
    if telethon_core.is_session_busy(session_name):
        prep_text = (
            "⏳ <b>В очереди...</b>\n\n"
            "Эта сессия сейчас занята другим парсингом. "
            "Ваш запустится автоматически, как только освободится."
        )
    else:
        prep_text = "🚀 <b>Начинаем парсинг...</b>\n\n⏳ Подготовка..."
    progress_msg = await callback.message.edit_text(prep_text, parse_mode="HTML")

    last_update_time = [0.0]
    last_text = [""]

    async def progress_callback(scanned, total, users_found, status: str = None):
        current_time = time.time()
        if current_time - last_update_time[0] < PROGRESS_UPDATE_INTERVAL:
            return
        
        status_line = f"\n\n⚠️ {status}" if status else ""
        new_text = (
            f"🚀 <b>Парсинг в процессе...</b>\n\n"
            f"📊 Просканировано: {scanned}\n"
            f"👥 Найдено пользователей: {users_found}"
            f"{status_line}\n\n"
            f"⏳ Пожалуйста, подождите..."
        )
        
        if new_text == last_text[0]:
            return
        
        try:
            await progress_msg.edit_text(new_text, parse_mode="HTML")
            last_update_time[0] = current_time
            last_text[0] = new_text
        except Exception:
            pass
    
    try:
        # Парсим чат по ID
        result = await telethon_core.parse_chat_by_id(
            session_name=session_name,
            chat_id=chat_id,
            max_messages=parse_limit,
            parse_bio=parse_bio,
            detect_gender=detect_gender,
            progress_callback=progress_callback
        )
        
        if result.errors:
            error_text = "\n".join(result.errors)
            await progress_msg.edit_text(
                f"❌ <b>Ошибка парсинга:</b>\n\n{error_text}",
                reply_markup=keyboards.get_main_menu(),
                parse_mode="HTML"
            )
            await state.clear()
            await callback.answer()
            return
        
        # Генерируем умную выгрузку (4 файла)
        await progress_msg.edit_text("📝 Создаём отчёты...", parse_mode="HTML")
        
        export_result = excel_generator.generate_smart_export(
            result,
            parse_type="chat_dialogs",
            time_filter=None,
            include_bio=parse_bio,
            include_gender=detect_gender
        )
        
        # Списываем лимит и пишем историю
        await _record_parsing(user_id, f"dialog:{chat_id}", "chat_dialogs", None, result)

        # Отправляем файлы
        await progress_msg.edit_text("📤 Отправляем файлы...", parse_mode="HTML")
        
        # Отправляем все 4 файла
        for file_path in export_result.all_paths():
            if file_path and file_path.exists():
                caption = ""
                if "admins" in file_path.name:
                    caption = "👑 <b>Администраторы</b>"
                elif "premium" in file_path.name:
                    caption = "💎 <b>Premium пользователи</b>"
                elif "regular" in file_path.name:
                    caption = "👥 <b>Обычные пользователи</b>"
                elif "full_report" in file_path.name:
                    caption = "📊 <b>Полный отчёт</b>"
                
                await callback.message.answer_document(
                    FSInputFile(file_path),
                    caption=caption,
                    parse_mode="HTML"
                )
        
        # Итоговое сообщение
        remaining_text = await _remaining_text(user_id)

        premium_count = len([u for u in result.users if u.is_premium])
        
        await progress_msg.edit_text(
            f"✅ <b>Парсинг завершён!</b>\n\n"
            f"🎯 Цель: {result.target_title}\n"
            f"👥 Пользователей: {len(result.users)}\n"
            f"👑 Администраторов: {len(result.admins)}\n"
            f"💎 Premium: {premium_count}\n"
            f"⏱ Время: {round(result.parsing_time, 2)} сек"
            f"{remaining_text}",
            parse_mode="HTML"
        )
        
        await callback.message.answer(
            "🏠 <b>Главное меню</b>\n\nВыберите следующее действие:",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
        
        # Удаляем файлы
        export_result.cleanup()
        
    except Exception as e:
        logger.error(f"Parsing error: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ <b>Ошибка:</b> {str(e)}",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
    finally:
        # Снимаем флаг активного парсинга в любом случае
        _active_parsings.discard(user_id)

    await state.clear()
    await callback.answer()


# Обработчик скрытых участников - переключение на парсинг активных
@router.callback_query(F.data == "parse_active_instead")
async def parse_active_instead(callback: CallbackQuery, state: FSMContext):
    """Переключиться на парсинг активных вместо участников"""
    data = await state.get_data()
    link = data.get("link")
    
    if link:
        # Если ссылка уже есть - сразу парсим активных
        await state.update_data(chat_mode="active")
        await callback.message.edit_text(
            "💬 <b>Переключаемся на парсинг активных...</b>\n\n"
            "Выберите временной фильтр:",
            reply_markup=keyboards.get_time_filter_menu(),
            parse_mode="HTML"
        )
    else:
        # Если ссылки нет - запрашиваем
        await state.update_data(chat_mode="active")
        await callback.message.edit_text(
            "💬 <b>Парсинг активных</b>\n\n"
            "Выберите временной фильтр:",
            reply_markup=keyboards.get_time_filter_menu(),
            parse_mode="HTML"
        )
    await callback.answer()


# Выбор временного фильтра
@router.callback_query(F.data.startswith("time_"))
async def select_time_filter(callback: CallbackQuery, state: FSMContext):
    """Выбор временного фильтра -> переход к выбору аккаунта"""
    time_key = callback.data.split("_", 1)[1]
    
    # Обработка "За всё время" - запрос количества постов
    if time_key == "alltime":
        await state.update_data(time_filter="alltime", time_days=None)
        await callback.message.edit_text(
            "♾ <b>Парсинг за всё время</b>\n\n"
            "Введите количество последних постов для парсинга (не более 200).\n\n"
            "⚠️ <i>Учитывайте, что сервисные сообщения тоже считаются!</i>",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        await state.set_state(ParsingStates.enter_custom_posts)
        await callback.answer()
        return
    
    time_days = config.TIME_FILTERS.get(time_key)

    await state.update_data(
        time_filter=time_key,
        time_days=time_days
    )

    user_id = callback.from_user.id
    
    # 🧠 Smart Session Selection - автоматический выбор лучшей сессии
    session_name, is_user_session = telethon_core.get_smart_session(user_id)
    
    # Сохраняем сессию и инициализируем опции
    await state.update_data(
        session_name=session_name,
        is_user_session=is_user_session,
        parse_bio=False,
        detect_gender=False
    )
    
    # Информируем пользователя какая сессия будет использована
    if is_user_session:
        session_info = "✅ Используется ваш аккаунт (доступ к приватным чатам)"
    else:
        session_info = "⚠️ Используется системный аккаунт (только публичные)"
    
    data = await state.get_data()
    parse_type = data.get("parse_type", "channel_posts")
    
    # ШАГ 2: Запрос ссылки (ПЕРЕД настройками!)
    if parse_type == "channel_posts":
        link_prompt = (
            "🔗 <b>Отправьте ссылку на канал</b>\n\n"
            "Бот спарсит последние посты и соберёт комментаторов.\n\n"
            "<b>Примеры:</b>\n"
            "• https://t.me/channel_name\n"
            "• @channel_name\n\n"
            f"🕵️ {session_info}"
        )
    elif parse_type == "channel_single":
        link_prompt = (
            "🔗 <b>Отправьте ссылку на конкретный пост</b>\n\n"
            "<b>Формат:</b> https://t.me/channel_name/123\n\n"
            f"🕵️ {session_info}"
        )
    else:
        link_prompt = (
            "🔗 <b>Отправьте ссылку на чат</b>\n\n"
            "<b>Примеры:</b>\n"
            "• https://t.me/chat_name\n"
            "• @chat_name\n\n"
            f"🕵️ {session_info}"
        )
    
    await callback.message.edit_text(
        link_prompt,
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.enter_link)
    await callback.answer()


# Обработка ввода количества постов (для "За всё время")
@router.message(ParsingStates.enter_custom_posts)
async def process_custom_posts(message: Message, state: FSMContext):
    """Обработка ввода количества постов"""
    text = message.text.strip()

    # Валидация
    if not text.isdigit():
        await message.answer(
            "⚠️ Введите число от 1 до 200.",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return

    count = int(text)

    # Автоматическое ограничение до 200 с предупреждением
    warning_msg = ""
    if count > 200:
        warning_msg = f"\n\n⚠️ <i>Лимит ограничен 200 сообщениями. Ваш ввод ({count}) сокращён до 200.</i>"
        count = 200
    elif count < 1:
        await message.answer(
            "⚠️ <b>Минимум 1 пост.</b>\n\nВведите число от 1 до 200.",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return
    
    # Сохраняем max_posts
    await state.update_data(max_posts=count)

    user_id = message.from_user.id

    # 🧠 Smart Session Selection - автоматический выбор лучшей сессии
    session_name, is_user_session = telethon_core.get_smart_session(user_id)

    await state.update_data(
        session_name=session_name,
        is_user_session=is_user_session,
        parse_bio=False,
        detect_gender=False
    )

    # Информируем пользователя какая сессия будет использована
    if is_user_session:
        session_info = "✅ Используется ваш аккаунт (доступ к приватным чатам)"
    else:
        session_info = "⚠️ Используется системный аккаунт (только публичные)"

    data = await state.get_data()
    parse_type = data.get("parse_type", "channel_posts")

    # ШАГ 2: Запрос ссылки (ПЕРЕД настройками!)
    await message.answer(
        f"✅ Будет спарсено до <b>{count}</b> постов.{warning_msg}\n\n"
        "🔗 <b>Теперь отправьте ссылку на канал</b>\n\n"
        "<b>Примеры:</b>\n"
        "• https://t.me/channel_name\n"
        "• @channel_name\n\n"
        f"🕵️ {session_info}",
        reply_markup=keyboards.get_cancel_button(),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.enter_link)


# Выбор сессии для парсинга
@router.callback_query(F.data.startswith("session_"), ParsingStates.select_session)
async def select_session(callback: CallbackQuery, state: FSMContext):
    """Выбор сессии для парсинга -> показываем опции Bio/Gender"""
    session_key = callback.data.replace("session_", "")
    
    if session_key == "system":
        session_name = config.SYSTEM_SESSION_NAME
    else:
        session_name = session_key
    
    # Инициализируем опции парсинга (по умолчанию выключены)
    await state.update_data(
        session_name=session_name,
        parse_bio=False,
        detect_gender=False
    )
    
    data = await state.get_data()
    parse_type = data.get("parse_type", "channel_posts")

    # Показываем меню настроек перед парсингом
    await callback.message.edit_text(
        "⚙️ <b>Настройки парсинга</b>\n\n"
        "Выберите дополнительные опции:\n\n"
        "📝 <b>Парсить Био</b> — собирать описание профиля (медленнее)\n"
        "👤 <b>Определять Пол</b> — определение по имени",
        reply_markup=keyboards.get_parsing_options_menu(False, False),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.parsing_settings)
    await callback.answer()


# Вспомогательная функция для формирования текста настроек
def _get_settings_text(link: str, is_user_session: bool, parse_bio: bool) -> str:
    """Формирует текст меню настроек"""
    session_info = "✅ Ваш аккаунт" if is_user_session else "⚠️ Системный"
    bio_warning = "\n\n⚠️ <i>Парсинг био увеличивает время работы!</i>" if parse_bio else ""
    
    return (
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"🎯 <b>Цель:</b> <code>{link}</code>\n"
        f"🕵️ <b>Сессия:</b> {session_info}\n\n"
        f"Выберите опции:"
        f"{bio_warning}"
    )


# Toggle: Парсить Био
@router.callback_query(F.data == "toggle_bio", ParsingStates.parsing_settings)
async def toggle_bio(callback: CallbackQuery, state: FSMContext):
    """Переключить опцию парсинга био"""
    data = await state.get_data()
    parse_bio = not data.get("parse_bio", False)
    detect_gender = data.get("detect_gender", False)
    link = data.get("link", "—")
    is_user_session = data.get("is_user_session", False)
    
    await state.update_data(parse_bio=parse_bio)
    
    await callback.message.edit_text(
        _get_settings_text(link, is_user_session, parse_bio),
        reply_markup=keyboards.get_parsing_options_menu(parse_bio, detect_gender),
        parse_mode="HTML"
    )
    await callback.answer()


# Toggle: Определять Пол
@router.callback_query(F.data == "toggle_gender", ParsingStates.parsing_settings)
async def toggle_gender(callback: CallbackQuery, state: FSMContext):
    """Переключить опцию определения пола"""
    data = await state.get_data()
    parse_bio = data.get("parse_bio", False)
    detect_gender = not data.get("detect_gender", False)
    link = data.get("link", "—")
    is_user_session = data.get("is_user_session", False)
    
    await state.update_data(detect_gender=detect_gender)
    
    await callback.message.edit_text(
        _get_settings_text(link, is_user_session, parse_bio),
        reply_markup=keyboards.get_parsing_options_menu(parse_bio, detect_gender),
        parse_mode="HTML"
    )
    await callback.answer()


# Ввод ссылки для парсинга -> показываем настройки
@router.message(ParsingStates.enter_link)
async def process_link_input(message: Message, state: FSMContext):
    """ШАГ 3: Получение ссылки -> переход к настройкам"""
    link = message.text.strip()
    
    # Базовая валидация ссылки
    if not link.startswith(("https://t.me/", "http://t.me/", "@", "t.me/")):
        await message.answer(
            "⚠️ <b>Неверный формат ссылки</b>\n\n"
            "Отправьте ссылку в одном из форматов:\n"
            "• https://t.me/channel_name\n"
            "• @channel_name",
            reply_markup=keyboards.get_cancel_button(),
            parse_mode="HTML"
        )
        return
    
    # Сохраняем ссылку
    await state.update_data(link=link)
    
    data = await state.get_data()
    is_user_session = data.get("is_user_session", False)
    parse_bio = data.get("parse_bio", False)
    detect_gender = data.get("detect_gender", False)
    
    # Информация о сессии
    if is_user_session:
        session_info = "✅ Используется ваш аккаунт"
    else:
        session_info = "⚠️ Используется системный аккаунт"
    
    # ШАГ 4: Показываем настройки с целевой ссылкой
    await message.answer(
        f"⚙️ <b>Настройки парсинга</b>\n\n"
        f"🎯 <b>Цель:</b> <code>{link}</code>\n"
        f"🕵️ <b>Сессия:</b> {session_info}\n\n"
        "Выберите дополнительные опции:",
        reply_markup=keyboards.get_parsing_options_menu(parse_bio, detect_gender),
        parse_mode="HTML"
    )
    await state.set_state(ParsingStates.parsing_settings)


# ШАГ 5: Запуск парсинга по кнопке "Начать"
@router.callback_query(F.data == "confirm_parsing_options", ParsingStates.parsing_settings)
async def start_parsing(callback: CallbackQuery, state: FSMContext):
    """Запуск парсинга после подтверждения настроек"""
    user_id = callback.from_user.id
    data = await state.get_data()
    
    link = data.get("link")
    if not link:
        await callback.message.edit_text(
            "❌ Ссылка не найдена. Начните заново.",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
        await state.clear()
        await callback.answer()
        return
    
    # Guard: не запускаем второй параллельный парсинг для того же пользователя
    if user_id in _active_parsings:
        await callback.answer(
            "⏳ У вас уже идёт парсинг. Дождитесь его завершения.",
            show_alert=True
        )
        return

    parse_type = data.get("parse_type", "channel_posts")
    time_filter = data.get("time_filter")
    time_days = data.get("time_days")
    session_name = data.get("session_name", config.SYSTEM_SESSION_NAME)
    is_user_session = data.get("is_user_session", False)
    parse_bio = data.get("parse_bio", False)
    detect_gender = data.get("detect_gender", False)
    max_posts = data.get("max_posts", 50)

    logger.debug(
        f"[StartParsing] user={user_id} session={session_name} "
        f"is_user={is_user_session} type={parse_type} link={link}"
    )

    _active_parsings.add(user_id)
    # Индикатор очереди: если сессия занята другим парсингом — предупреждаем
    if telethon_core.is_session_busy(session_name):
        prep_text = (
            "⏳ <b>В очереди...</b>\n\n"
            "Эта сессия сейчас занята другим парсингом. "
            "Ваш запустится автоматически, как только освободится."
        )
    else:
        prep_text = "🚀 <b>Начинаем парсинг...</b>\n\n⏳ Подготовка..."
    progress_msg = await callback.message.edit_text(prep_text, parse_mode="HTML")
    await callback.answer()

    # Состояние для throttling обновлений прогресса
    last_update_time = [0.0]
    last_text = [""]

    async def progress_callback(scanned, total, users_found, status: str = None):
        current_time = time.time()
        if current_time - last_update_time[0] < PROGRESS_UPDATE_INTERVAL:
            return
        
        status_line = f"\n\n⚠️ {status}" if status else ""
        new_text = (
            f"🚀 <b>Парсинг в процессе...</b>\n\n"
            f"📊 Просканировано: {scanned}\n"
            f"👥 Найдено пользователей: {users_found}"
            f"{status_line}\n\n"
            f"⏳ Пожалуйста, подождите..."
        )
        
        if new_text == last_text[0]:
            return
        
        try:
            await progress_msg.edit_text(new_text, parse_mode="HTML")
            last_update_time[0] = current_time
            last_text[0] = new_text
        except TelegramRetryAfter as e:
            logger.warning(f"Progress update rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Progress update failed: {e}")
        except Exception as e:
            logger.debug(f"Progress update error: {e}")

    try:
        if parse_type == "channel_posts":
            # Парсинг последних постов канала
            result = await telethon_core.parse_channel_comments(
                session_name=session_name,
                channel_link=link,
                time_filter_days=time_days,
                max_posts=max_posts,
                parse_bio=parse_bio,
                detect_gender=detect_gender,
                progress_callback=progress_callback
            )
        elif parse_type == "channel_single":
            # Парсинг конкретного поста
            result = await telethon_core.parse_single_post(
                session_name=session_name,
                post_link=link,
                time_filter_days=time_days,
                parse_bio=parse_bio,
                detect_gender=detect_gender,
                progress_callback=progress_callback
            )
        else:
            # Парсинг чата - проверяем режим (members/active)
            chat_mode = data.get("chat_mode", "active")
            
            if chat_mode == "members":
                # Парсинг участников (GetParticipantsRequest)
                result = await telethon_core.parse_chat_participants(
                    session_name=session_name,
                    chat_link=link,
                    max_users=200,
                    parse_bio=parse_bio,
                    detect_gender=detect_gender,
                    progress_callback=progress_callback
                )
            else:
                # Парсинг активных (по сообщениям)
                result = await telethon_core.parse_chat_members(
                    session_name=session_name,
                    chat_link=link,
                    time_filter_days=time_days,
                    parse_bio=parse_bio,
                    detect_gender=detect_gender,
                    progress_callback=progress_callback
                )

        # Проверка на ошибки
        if result.errors:
            error_text = "\n".join(result.errors)
            
            # Проверяем на скрытых участников
            if "HIDDEN_MEMBERS" in error_text:
                await progress_msg.edit_text(
                    "🔒 <b>Список участников скрыт настройками чата</b>\n\n"
                    "Администраторы этого чата скрыли список членов группы.\n\n"
                    "💡 <b>Решение:</b>\n"
                    "Попробуйте режим <b>«Парсить Активных (по переписке)»</b> — "
                    "он соберёт всех, кто писал сообщения в чат.\n\n"
                    "👇 Нажмите кнопку ниже:",
                    reply_markup=keyboards.get_hidden_members_menu(),
                    parse_mode="HTML"
                )
                # Сохраняем ссылку для повторного парсинга
                await state.update_data(link=link, chat_mode="active")
                return
            
            # Проверяем на типичные ошибки и даём понятные советы
            is_user_session = data.get("is_user_session", False)
            
            if "not part of" in error_text or "Join the group" in error_text or "ChannelPrivate" in error_text:
                if is_user_session:
                    # У пользователя есть аккаунт, но он не состоит в чате
                    await progress_msg.edit_text(
                        "❌ <b>Нет доступа к чату</b>\n\n"
                        "Ваш подключённый аккаунт не состоит в этом чате/группе.\n\n"
                        "<b>Решение:</b>\n"
                        "1️⃣ Вступите в этот чат с вашего аккаунта\n"
                        "2️⃣ Повторите попытку парсинга",
                        reply_markup=keyboards.get_main_menu(),
                        parse_mode="HTML"
                    )
                else:
                    # Системная сессия не имеет доступа
                    await progress_msg.edit_text(
                        "❌ <b>Нет доступа к чату</b>\n\n"
                        "Это приватный чат/канал. Системная сессия не имеет к нему доступа.\n\n"
                        "<b>Решение:</b>\n"
                        "1️⃣ Нажмите <b>➕ Добавить аккаунт</b> в главном меню\n"
                        "2️⃣ Добавьте аккаунт, который состоит в этом чате\n"
                        "3️⃣ Повторите попытку — бот автоматически использует ваш аккаунт",
                        reply_markup=keyboards.get_main_menu(),
                        parse_mode="HTML"
                    )
            elif "Cannot find any entity" in error_text or "No user has" in error_text:
                await progress_msg.edit_text(
                    "❌ <b>Чат/канал не найден</b>\n\n"
                    "Проверьте правильность ссылки.\n\n"
                    "<b>Правильные форматы:</b>\n"
                    "• https://t.me/channel_name\n"
                    "• https://t.me/+ABC123xyz\n"
                    "• @channel_name",
                    reply_markup=keyboards.get_main_menu(),
                    parse_mode="HTML"
                )
            else:
                await progress_msg.edit_text(
                    f"❌ <b>Ошибка парсинга:</b>\n\n{error_text}",
                    reply_markup=keyboards.get_main_menu(),
                    parse_mode="HTML"
                )
            await state.clear()
            return

        # Генерируем отчеты
        await progress_msg.edit_text(
            "📝 Создаем отчеты...",
            parse_mode="HTML"
        )

        excel_path, txt_path = excel_generator.generate_reports(
            result,
            parse_type,
            time_filter
        )

        if not excel_path or not txt_path:
            await progress_msg.edit_text(
                "❌ Ошибка при создании отчетов",
                reply_markup=keyboards.get_main_menu(),
                parse_mode="HTML"
            )
            await state.clear()
            return

        # Списываем лимит и пишем историю
        await _record_parsing(user_id, link, parse_type, time_filter, result)

        # Отправляем файлы
        await progress_msg.edit_text(
            "📤 Отправляем файлы...",
            parse_mode="HTML"
        )

        # Excel
        await callback.message.answer_document(
            FSInputFile(excel_path),
            caption=f"📊 <b>Excel отчет</b>\n\n"
                    f"Найдено пользователей: {len(result.users)}\n"
                    f"Администраторов: {len(result.admins)}",
            parse_mode="HTML"
        )

        # TXT
        await callback.message.answer_document(
            FSInputFile(txt_path),
            caption="📝 <b>Список юзернеймов</b>\n\n<i>👑 Админы в самом верху файла!</i>",
            parse_mode="HTML"
        )

        # Итоговое сообщение
        remaining_text = await _remaining_text(user_id)

        await progress_msg.edit_text(
            f"✅ <b>Парсинг завершен!</b>\n\n"
            f"🎯 Цель: {result.target_title}\n"
            f"👥 Пользователей: {len(result.users)}\n"
            f"👑 Администраторов: {len(result.admins)}\n"
            f"📨 Сообщений просканировано: {result.total_messages_scanned}\n"
            f"⏱ Время: {round(result.parsing_time, 2)} сек"
            f"{remaining_text}",
            parse_mode="HTML"
        )
        
        # Отправляем главное меню отдельным сообщением
        await callback.message.answer(
            "🏠 <b>Главное меню</b>\n\nВыберите следующее действие:",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )

        # Удаляем файлы
        try:
            excel_path.unlink()
            txt_path.unlink()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Parsing error: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ <b>Ошибка:</b> {str(e)}",
            reply_markup=keyboards.get_main_menu(),
            parse_mode="HTML"
        )
    finally:
        # Снимаем флаг активного парсинга в любом случае
        _active_parsings.discard(user_id)

    await state.clear()


# Отмена
@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено",
        reply_markup=keyboards.get_main_menu()
    )
    await callback.answer()


# Команда /cancel — выход из любого FSM-сценария
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Сбросить текущий сценарий и вернуться в меню."""
    await state.clear()
    await message.answer(
        "❌ Действие отменено. Вы в главном меню.",
        reply_markup=keyboards.get_main_menu()
    )
