"""
NeuroScraper Pro - Main Entry Point
Professional Telegram Audience Parser Bot
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime, time as dt_time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import db
from handlers import user_handlers, admin_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# Глобальная переменная для фоновых задач
_background_tasks: set = set()


async def daily_backup_task():
    """Фоновая задача для ежедневного бэкапа БД в 03:00"""
    from datetime import timedelta
    
    while True:
        try:
            now = datetime.now()
            # Следующий запуск в 03:00
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run = next_run + timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"Next backup scheduled in {wait_seconds / 3600:.1f} hours")
            await asyncio.sleep(wait_seconds)
            
            # Выполняем бэкап
            backup_path = await db.backup_database()
            if backup_path:
                logger.info(f"Daily backup completed: {backup_path}")
            else:
                logger.error("Daily backup failed!")
        except asyncio.CancelledError:
            logger.info("Backup task cancelled")
            break
        except Exception as e:
            logger.error(f"Backup task error: {e}")
            await asyncio.sleep(3600)  # Подождать час при ошибке


async def on_startup():
    """Действия при запуске бота"""
    logger.info("Starting NeuroScraper Pro Bot...")

    # Инициализация базы данных
    await db.init_db()
    logger.info("Database initialized")

    # Создание директорий
    config.SESSIONS_DIR.mkdir(exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    Path("backups").mkdir(exist_ok=True)
    logger.info("Directories created")
    
    # Запуск фоновой задачи бэкапа
    backup_task = asyncio.create_task(daily_backup_task())
    _background_tasks.add(backup_task)
    backup_task.add_done_callback(_background_tasks.discard)

    logger.info("Bot started successfully!")


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("Shutting down NeuroScraper Pro Bot...")
    
    # Отменяем фоновые задачи
    for task in _background_tasks:
        task.cancel()
    
    # Закрываем соединение с БД
    await db.close()
    
    logger.info("Bot stopped")


async def main():
    """Главная функция запуска бота"""

    # Создание бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    # FSM хранилище
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация роутеров (admin первый - приоритет для админских команд)
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # Регистрация startup/shutdown функций
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Запуск бота
    try:
        logger.info("Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except Exception as e:
        logger.error(f"Error during polling: {e}", exc_info=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
