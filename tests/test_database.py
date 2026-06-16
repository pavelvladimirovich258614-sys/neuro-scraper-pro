"""Тесты слоя БД: лимиты, рефералы, доступ и конкурентная запись.

Конкурентный тест подтверждает фикс 1.1 (единое соединение): десятки
параллельных записей не дают 'database is locked'.
"""

import asyncio
import pytest
import pytest_asyncio

import config
from database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Свежая БД на временном файле для каждого теста."""
    database = Database(tmp_path / "test.db")
    await database.init_db()
    yield database
    await database.close()


# ===== ЛИМИТЫ =====
# По умолчанию бот бесплатный (доступ открыт), поэтому для проверки механики
# лимитов в этих тестах доступ явно закрывается.

async def test_new_user_gets_free_limit(db):
    await db.set_access_open(False)
    info = await db.check_limit(12345)
    assert info["has_limit"] is True
    assert info["remaining"] == config.FREE_PARSING_LIMIT
    assert info["is_premium"] is False


async def test_decrease_limit_until_exhausted(db):
    await db.set_access_open(False)
    uid = 555
    await db.create_user(uid)
    for _ in range(config.FREE_PARSING_LIMIT):
        assert await db.decrease_limit(uid) is True
    # Лимит исчерпан
    info = await db.check_limit(uid)
    assert info["has_limit"] is False
    assert info["remaining"] == 0
    assert await db.decrease_limit(uid) is False


async def test_premium_user_unlimited(db):
    uid = 777
    await db.create_user(uid)
    await db.set_premium(uid, True)
    info = await db.check_limit(uid)
    assert info["is_premium"] is True
    assert info["remaining"] == -1
    # decrease не уменьшает счётчик премиума
    assert await db.decrease_limit(uid) is True


async def test_admin_unlimited(db):
    info = await db.check_limit(config.ADMIN_ID)
    assert info["is_premium"] is True
    assert info["remaining"] == -1


async def test_reset_limit(db):
    await db.set_access_open(False)
    uid = 888
    await db.create_user(uid)
    await db.decrease_limit(uid)
    await db.reset_limit(uid)
    info = await db.check_limit(uid)
    assert info["remaining"] == config.FREE_PARSING_LIMIT


# ===== ГЛОБАЛЬНЫЙ ДОСТУП =====

async def test_access_open_by_default(db):
    # Бот бесплатный: без явной настройки доступ открыт
    assert await db.is_access_open() is True


async def test_access_can_be_closed(db):
    await db.set_access_open(False)
    assert await db.is_access_open() is False


async def test_access_open_makes_unlimited(db):
    await db.set_access_open(True)
    assert await db.is_access_open() is True
    # Любой пользователь становится безлимитным
    info = await db.check_limit(424242)
    assert info["has_limit"] is True
    assert info["remaining"] == -1


# ===== РЕФЕРАЛЫ =====

async def test_referral_bonus_idempotent(db):
    await db.set_access_open(False)
    referrer, invited = 100, 200
    await db.create_user(referrer)
    # Исчерпываем лимит реферера, чтобы увидеть эффект бонуса
    for _ in range(config.FREE_PARSING_LIMIT):
        await db.decrease_limit(referrer)
    await db.create_user(invited, referrer_id=referrer)

    assert await db.add_referral_bonus(referrer, invited) is True
    # Повторное начисление за того же приглашённого — отклонено
    assert await db.add_referral_bonus(referrer, invited) is False

    # У реферера появились попытки (parsing_count уменьшился на REFERRAL_BONUS)
    info = await db.check_limit(referrer)
    assert info["remaining"] == min(config.REFERRAL_BONUS, config.FREE_PARSING_LIMIT)


async def test_referral_stats(db):
    referrer = 300
    await db.create_user(referrer)
    await db.create_user(301, referrer_id=referrer)
    await db.create_user(302, referrer_id=referrer)
    stats = await db.get_referral_stats(referrer)
    assert stats["invited_count"] == 2
    assert stats["total_bonus"] == 2 * config.REFERRAL_BONUS


# ===== КОНКУРЕНТНОСТЬ (фикс 1.1) =====

async def test_concurrent_writes_no_lock(db):
    uid = 42
    await db.create_user(uid)
    await db.set_premium(uid, True)  # премиум — decrease не блокируется лимитом

    async def worker(i):
        await db.decrease_limit(uid)
        await db.add_parsing_history(uid, f"link{i}", "channel", "week", i, 0)
        await db.update_user_activity(uid)
        return await db.check_limit(uid)

    results = await asyncio.gather(*[worker(i) for i in range(30)], return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"Конкурентные записи дали ошибки: {errors}"

    stats = await db.get_stats()
    assert stats["total_parsings"] == 30


# ===== АДМИНЫ БОТА =====

async def test_bot_admin_management(db):
    assert await db.is_bot_admin(config.ADMIN_ID) is True  # главный админ
    assert await db.is_bot_admin(5050) is False
    await db.add_bot_admin(5050, added_by=config.ADMIN_ID)
    assert await db.is_bot_admin(5050) is True
    await db.remove_bot_admin(5050)
    assert await db.is_bot_admin(5050) is False
