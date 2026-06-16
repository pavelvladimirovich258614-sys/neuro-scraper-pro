"""
Keyboards module for NeuroScraper Pro Bot
Contains all inline keyboards for bot navigation
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List, Dict, Any
import config


# ===== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ =====

# Константы для проверки подписки
SUBSCRIPTION_CHANNEL_ID = -1002443306268
SUBSCRIPTION_CHANNEL_LINK = "https://t.me/Novopoltsev_Pavel"


def get_subscription_check_menu() -> InlineKeyboardMarkup:
    """Меню проверки подписки на канал"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Проверить подписку",
            callback_data="check_subscription"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📢 Подписаться",
            url=SUBSCRIPTION_CHANNEL_LINK
        )
    )
    return builder.as_markup()


def get_not_subscribed_menu() -> InlineKeyboardMarkup:
    """Меню когда пользователь не подписан"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📢 Подписаться",
            url=SUBSCRIPTION_CHANNEL_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Проверить снова",
            callback_data="check_subscription"
        )
    )
    return builder.as_markup()


def get_unsubscribed_menu() -> InlineKeyboardMarkup:
    """Меню когда пользователь ОТПИСАЛСЯ от канала (был подписан, но отписался)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📢 Подписаться",
            url=SUBSCRIPTION_CHANNEL_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Проверить подписку",
            callback_data="check_subscription"
        )
    )
    return builder.as_markup()


def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 Парсинг каналов",
            callback_data="channel_menu"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Парсинг чатов (группы)",
            callback_data="parse_chat"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить аккаунт",
            callback_data="add_account"
        ),
        InlineKeyboardButton(
            text="📱 Мои аккаунты",
            callback_data="my_accounts"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💎 Мой лимит",
            callback_data="my_limit"
        ),
        InlineKeyboardButton(
            text="👥 Рефералы",
            callback_data="show_referral"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❓ Помощь",
            callback_data="help"
        ),
        InlineKeyboardButton(
            text="💬 Поддержка",
            url=config.SUPPORT_LINK
        )
    )
    return builder.as_markup()


def get_channel_parsing_menu() -> InlineKeyboardMarkup:
    """Меню выбора режима парсинга каналов"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 Последние посты",
            callback_data="parse_channel_posts"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📌 Конкретный пост",
            callback_data="parse_channel_single"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_time_filter_menu() -> InlineKeyboardMarkup:
    """Меню выбора временного фильтра"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📅 За 1 день (24 часа)",
            callback_data="time_day"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 За неделю (7 дней)",
            callback_data="time_week"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 За месяц (30 дней)",
            callback_data="time_month"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 За 3 месяца (90 дней)",
            callback_data="time_3months"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="♾ За всё время (Макс 200)",
            callback_data="time_alltime"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_parsing_options_menu(parse_bio: bool = False, detect_gender: bool = False) -> InlineKeyboardMarkup:
    """Меню настроек перед вводом ссылки (toggles Bio/Gender)"""
    builder = InlineKeyboardBuilder()
    
    bio_icon = "✅" if parse_bio else "❌"
    gender_icon = "✅" if detect_gender else "❌"
    
    builder.row(
        InlineKeyboardButton(
            text=f"{bio_icon} Парсить Био",
            callback_data="toggle_bio"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{gender_icon} Определять Пол",
            callback_data="toggle_gender"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏁 Начать парсинг",
            callback_data="confirm_parsing_options"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_session_selection_menu(sessions: list) -> InlineKeyboardMarkup:
    """Меню выбора сессии для парсинга"""
    builder = InlineKeyboardBuilder()

    # Системная сессия (всегда доступна)
    builder.row(
        InlineKeyboardButton(
            text="🤖 Системная сессия",
            callback_data="session_system"
        )
    )

    # Сессии пользователя
    if sessions:
        for session in sessions:
            phone = session["phone_number"]
            session_name = session["session_name"]
            # Маскируем часть номера для безопасности
            masked_phone = phone[:4] + "***" + phone[-4:] if len(phone) > 8 else phone
            builder.row(
                InlineKeyboardButton(
                    text=f"📱 {masked_phone} (ваш аккаунт)",
                    callback_data=f"session_{session_name}"
                )
            )
    
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить аккаунт",
            callback_data="add_account"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🔙 Отмена",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка 'Назад'"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_cancel_button() -> InlineKeyboardMarkup:
    """Кнопка 'Отмена'"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="cancel"
        )
    )
    return builder.as_markup()


def get_limit_exceeded_menu() -> InlineKeyboardMarkup:
    """Меню при исчерпанном лимите"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💎 Купить подписку",
            url=config.SUPPORT_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_admin_menu() -> InlineKeyboardMarkup:
    """Админ-панель"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👤 Выдать премиум",
            callback_data="admin_give_premium"
        ),
        InlineKeyboardButton(
            text="📉 Забрать премиум",
            callback_data="admin_revoke_premium"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Сбросить лимит",
            callback_data="admin_reset_limit"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👑 Добавить админа",
            callback_data="admin_add_admin"
        ),
        InlineKeyboardButton(
            text="🚫 Убрать админа",
            callback_data="admin_remove_admin"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📋 Список админов",
            callback_data="admin_list_admins"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Общая статистика",
            callback_data="admin_stats"
        ),
        InlineKeyboardButton(
            text="📈 Пользователи",
            callback_data="admin_user_stats"
        )
    )
    # Кнопки рассылок
    builder.row(
        InlineKeyboardButton(
            text="📢 Массовая рассылка",
            callback_data="admin_broadcast_all"
        ),
        InlineKeyboardButton(
            text="🎯 Рассылка по ID",
            callback_data="admin_broadcast_ids"
        )
    )
    # Управление доступом к парсингу
    builder.row(
        InlineKeyboardButton(
            text="🔓 Открыть доступ всем",
            callback_data="admin_open_access"
        ),
        InlineKeyboardButton(
            text="🔒 Закрыть доступ",
            callback_data="admin_close_access"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_parsing_progress_menu() -> InlineKeyboardMarkup:
    """Меню во время парсинга"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⏸ Остановить",
            callback_data="stop_parsing"
        )
    )
    return builder.as_markup()


def get_my_accounts_menu(sessions: list) -> InlineKeyboardMarkup:
    """Меню 'Мои аккаунты' со списком аккаунтов"""
    builder = InlineKeyboardBuilder()
    
    # Кнопка добавления аккаунта
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить аккаунт",
            callback_data="add_account"
        )
    )
    
    # Кнопка вступления в чат (если есть аккаунты)
    if sessions:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Вступить в чат/канал",
                callback_data="join_chat_menu"
            )
        )
    
    # Список аккаунтов пользователя
    for session in sessions:
        phone = session["phone_number"]
        session_name = session["session_name"]
        builder.row(
            InlineKeyboardButton(
                text=f"📱 {phone}",
                callback_data=f"view_account_{session_name}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_join_chat_session_menu(sessions: list) -> InlineKeyboardMarkup:
    """Меню выбора аккаунта для вступления в чат"""
    builder = InlineKeyboardBuilder()
    
    for session in sessions:
        phone = session["phone_number"]
        session_name = session["session_name"]
        masked_phone = phone[:4] + "***" + phone[-4:] if len(phone) > 8 else phone
        builder.row(
            InlineKeyboardButton(
                text=f"📱 {masked_phone}",
                callback_data=f"join_with_{session_name}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="my_accounts"
        )
    )
    return builder.as_markup()


def get_account_actions_menu(session_name: str, phone: str) -> InlineKeyboardMarkup:
    """Меню действий с конкретным аккаунтом"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить аккаунт",
            callback_data=f"delete_session_{session_name}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 К списку аккаунтов",
            callback_data="my_accounts"
        )
    )
    return builder.as_markup()


def get_confirm_delete_menu(session_name: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления аккаунта"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=f"confirm_delete_{session_name}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="my_accounts"
        )
    )
    return builder.as_markup()


def get_help_menu() -> InlineKeyboardMarkup:
    """Меню помощи"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📖 Как парсить каналы",
            callback_data="help_channels"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📖 Как парсить чаты",
            callback_data="help_chats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📖 Как добавить аккаунт",
            callback_data="help_account"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Связаться с поддержкой",
            url=config.SUPPORT_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


# ===== НОВЫЕ РЕЖИМЫ ПАРСИНГА ЧАТОВ (Feature 1) =====

def get_chat_parsing_mode_menu() -> InlineKeyboardMarkup:
    """Меню выбора режима парсинга чатов"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👥 Участники (из списка)",
            callback_data="chat_mode_members"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Активные (кто писал)",
            callback_data="chat_mode_active"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔒 Мои Чаты",
            callback_data="chat_mode_dialogs"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_dialogs_menu(dialogs: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Меню выбора чата из списка диалогов пользователя"""
    builder = InlineKeyboardBuilder()
    
    for dialog in dialogs[:20]:  # Максимум 20 чатов
        title = dialog.get("title", "Без названия")
        chat_id = dialog.get("id")
        # Обрезаем длинные названия
        if len(title) > 30:
            title = title[:27] + "..."
        
        builder.row(
            InlineKeyboardButton(
                text=f"💬 {title}",
                callback_data=f"dialog_{chat_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="parse_chat"
        )
    )
    return builder.as_markup()


# ===== НАСТРОЙКИ ПАРСИНГА (Feature 2) =====

def get_parsing_settings_menu(
    parse_bio: bool = False,
    detect_gender: bool = False,
    limit: int = 200
) -> InlineKeyboardMarkup:
    """Меню настроек перед парсингом"""
    builder = InlineKeyboardBuilder()
    
    # Переключатель Био
    bio_status = "✅ ВКЛ" if parse_bio else "❌ ВЫКЛ"
    builder.row(
        InlineKeyboardButton(
            text=f"🔘 Парсить Био: {bio_status}",
            callback_data="toggle_bio"
        )
    )
    
    # Переключатель Пола
    gender_status = "✅ ВКЛ" if detect_gender else "❌ ВЫКЛ"
    builder.row(
        InlineKeyboardButton(
            text=f"🔘 Определять Пол: {gender_status}",
            callback_data="toggle_gender"
        )
    )
    
    # Лимит
    limit_text = f"📊 Лимит: {limit}" if limit < 200 else "📊 Лимит: Макс (200)"
    builder.row(
        InlineKeyboardButton(
            text=limit_text,
            callback_data="set_limit"
        )
    )
    
    # Кнопка начала парсинга
    builder.row(
        InlineKeyboardButton(
            text="🚀 Начать парсинг",
            callback_data="start_parsing_with_settings"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_limit_input_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура для ввода лимита"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="♾ За все время (Макс 200)")
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_remove_keyboard():
    """Убрать Reply-клавиатуру"""
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()


# ===== РЕФЕРАЛЬНАЯ СИСТЕМА (Feature 4) =====

def get_referral_menu(ref_link: str) -> InlineKeyboardMarkup:
    """Меню реферальной программы"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📋 Скопировать ссылку",
            callback_data="copy_ref_link"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Моя статистика",
            callback_data="ref_stats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


def get_limit_exceeded_menu_v2() -> InlineKeyboardMarkup:
    """Обновлённое меню при исчерпанном лимите с реферальной ссылкой"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💎 Купить подписку",
            url=config.SUPPORT_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Пригласить друга (+2 парсинга)",
            callback_data="show_referral"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Поддержка",
            url=config.SUPPORT_LINK
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


# ===== ВЫБОР ДЛЯ СКРЫТЫХ УЧАСТНИКОВ =====

def get_hidden_members_menu() -> InlineKeyboardMarkup:
    """Меню когда участники чата скрыты"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💬 Спарсить активных (кто писал)",
            callback_data="parse_active_instead"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_main"
        )
    )
    return builder.as_markup()


# ===== КЛАВИАТУРЫ РАССЫЛКИ (Admin Broadcast) =====

def get_broadcast_photo_menu() -> InlineKeyboardMarkup:
    """Меню для шага 'Картинка' в рассылке"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⏭ Пропустить",
            callback_data="broadcast_skip_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_photo_edit_menu() -> InlineKeyboardMarkup:
    """Меню после загрузки фото"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➡️ Далее",
            callback_data="broadcast_photo_next"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Заменить фото",
            callback_data="broadcast_replace_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить фото",
            callback_data="broadcast_delete_photo"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_text_menu() -> InlineKeyboardMarkup:
    """Меню для шага 'Текст' в рассылке"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_text_edit_menu() -> InlineKeyboardMarkup:
    """Меню после ввода текста"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➡️ Далее",
            callback_data="broadcast_text_next"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Редактировать текст",
            callback_data="broadcast_edit_text"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_button_menu() -> InlineKeyboardMarkup:
    """Меню для шага 'URL-кнопка' в рассылке"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить кнопку",
            callback_data="broadcast_add_button"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⏭ Пропустить",
            callback_data="broadcast_skip_button"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_button_input_menu() -> InlineKeyboardMarkup:
    """Меню для ввода данных кнопки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="broadcast_button_back"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_button_edit_menu() -> InlineKeyboardMarkup:
    """Меню после добавления кнопки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➡️ Далее",
            callback_data="broadcast_button_next"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Изменить кнопку",
            callback_data="broadcast_add_button"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить кнопку",
            callback_data="broadcast_delete_button"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_pin_menu(pin_enabled: bool = False) -> InlineKeyboardMarkup:
    """Меню для шага 'Закрепление' в рассылке (Toggle)"""
    builder = InlineKeyboardBuilder()
    pin_status = "✅" if pin_enabled else "❌"
    builder.row(
        InlineKeyboardButton(
            text=f"📌 Закрепить: {pin_status}",
            callback_data="broadcast_toggle_pin"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="➡️ Далее (Предпросмотр)",
            callback_data="broadcast_preview"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_preview_menu() -> InlineKeyboardMarkup:
    """Меню предпросмотра перед отправкой"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🚀 Отправить",
            callback_data="broadcast_send"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Редактировать",
            callback_data="broadcast_edit"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="broadcast_cancel"
        )
    )
    return builder.as_markup()


def get_broadcast_edit_menu() -> InlineKeyboardMarkup:
    """Меню выбора что редактировать"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🖼 Картинка",
            callback_data="broadcast_edit_photo_step"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📝 Текст",
            callback_data="broadcast_edit_text_step"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔘 Кнопка",
            callback_data="broadcast_edit_button_step"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📌 Закрепление",
            callback_data="broadcast_edit_pin_step"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 К предпросмотру",
            callback_data="broadcast_preview"
        )
    )
    return builder.as_markup()


def get_broadcast_url_button(text: str, url: str) -> InlineKeyboardMarkup:
    """Создать клавиатуру с URL-кнопкой для рассылки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=text,
            url=url
        )
    )
    return builder.as_markup()


def get_broadcast_confirm_cancel_menu() -> InlineKeyboardMarkup:
    """Подтверждение отмены рассылки"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, отменить",
            callback_data="broadcast_confirm_cancel"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Вернуться",
            callback_data="broadcast_preview"
        )
    )
    return builder.as_markup()
