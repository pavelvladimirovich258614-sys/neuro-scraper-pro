"""
Referral Handlers
Реферальная программа: меню, статистика, копирование ссылки.
Вынесено из user_handlers — изолированные leaf-хендлеры без FSM.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

import keyboards
import config
from database import db

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "show_referral")
async def show_referral_menu(callback: CallbackQuery):
    """Показать реферальное меню"""
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    # Получаем статистику рефералов
    ref_stats = await db.get_referral_stats(user_id)

    await callback.message.edit_text(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте <b>+{config.REFERRAL_BONUS} парсинга</b> за каждого!\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"• Приглашено: {ref_stats['invited_count']} чел.\n"
        f"• Заработано: +{ref_stats['total_bonus']} парсингов",
        reply_markup=keyboards.get_referral_menu(ref_link),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_stats")
async def show_ref_stats(callback: CallbackQuery):
    """Показать статистику рефералов"""
    user_id = callback.from_user.id
    ref_stats = await db.get_referral_stats(user_id)

    await callback.message.edit_text(
        f"📊 <b>Статистика рефералов</b>\n\n"
        f"👥 Приглашено друзей: <b>{ref_stats['invited_count']}</b>\n"
        f"🎁 Заработано парсингов: <b>+{ref_stats['total_bonus']}</b>\n\n"
        f"💡 За каждого нового друга вы получаете +{config.REFERRAL_BONUS} парсинга!",
        reply_markup=keyboards.get_back_button(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "copy_ref_link")
async def copy_ref_link(callback: CallbackQuery):
    """Показать ссылку для копирования"""
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    await callback.answer(
        f"Ссылка скопирована!",
        show_alert=False
    )

    # Отправляем ссылку отдельным сообщением для удобного копирования
    await callback.message.answer(
        f"📋 <b>Ваша реферальная ссылка:</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Нажмите на ссылку чтобы скопировать</i>",
        parse_mode="HTML"
    )
