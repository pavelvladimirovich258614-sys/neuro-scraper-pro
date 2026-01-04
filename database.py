"""
Database module for NeuroScraper Pro Bot
Manages user data, parsing limits, and session tracking
"""

import aiosqlite
import logging
import shutil
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

import config

logger = logging.getLogger(__name__)


class Database:
    """Database manager for user data and limits with connection pooling"""

    # Timeout для SQLite соединений (секунды) - критично для многопользовательского доступа
    DB_TIMEOUT = 30.0

    def __init__(self, db_path: Path = config.DATABASE_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _setup_connection(self, conn: aiosqlite.Connection):
        """Настройка соединения с WAL mode и оптимизациями"""
        conn.row_factory = aiosqlite.Row
        # WAL mode - критично для concurrent access
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        # Дополнительные оптимизации для concurrent access
        await conn.execute("PRAGMA busy_timeout=30000")  # 30 секунд ожидание блокировки
        await conn.execute("PRAGMA synchronous=NORMAL")  # Баланс скорости и надёжности

    @asynccontextmanager
    async def get_connection(self):
        """Получить переиспользуемое соединение с блокировкой"""
        async with self._lock:
            if self._connection is None:
                self._connection = await aiosqlite.connect(
                    self.db_path,
                    timeout=self.DB_TIMEOUT
                )
                await self._setup_connection(self._connection)
            yield self._connection
    
    async def close(self):
        """Закрыть соединение при завершении работы"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def init_db(self):
        """Initialize database tables"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            # Инициализируем WAL mode сразу при создании БД
            await self._setup_connection(db)
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    parsing_count INTEGER DEFAULT 0,
                    is_premium BOOLEAN DEFAULT 0,
                    referrer_id INTEGER DEFAULT NULL,
                    referral_bonus_given BOOLEAN DEFAULT 0,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Миграция: добавляем поля referrer_id и referral_bonus_given если их нет
            try:
                await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL")
            except:
                pass  # Колонка уже существует
            try:
                await db.execute("ALTER TABLE users ADD COLUMN referral_bonus_given BOOLEAN DEFAULT 0")
            except:
                pass  # Колонка уже существует
            
            # Миграция: добавляем поле subscription_verified для кэширования проверки подписки
            try:
                await db.execute("ALTER TABLE users ADD COLUMN subscription_verified BOOLEAN DEFAULT 0")
            except:
                pass  # Колонка уже существует

            # User sessions table (for Telethon accounts)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    session_name TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Parsing history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS parsing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_link TEXT NOT NULL,
                    parse_type TEXT NOT NULL,
                    time_filter TEXT,
                    users_found INTEGER DEFAULT 0,
                    admins_found INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Bot admins table (для управления админами бота)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Bot settings table (for global flags like access control)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Индексы для ускорения запросов
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_parsing_history_user_id ON parsing_history(user_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_parsing_history_created ON parsing_history(created_at)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id, is_active)
            """)

            await db.commit()
            logger.info("Database initialized with indexes")

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user data by ID"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None

    async def create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        referrer_id: Optional[int] = None
    ) -> bool:
        """Create new user in database"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, referrer_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, username, first_name, last_name, referrer_id))
                await db.commit()
                logger.info(f"New user created: {user_id}, referrer: {referrer_id}")
                return True
        except aiosqlite.IntegrityError:
            logger.warning(f"User {user_id} already exists")
            return False

    async def update_user_activity(self, user_id: int):
        """Update user's last activity timestamp"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            await db.execute("""
                UPDATE users
                SET last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()

    async def check_limit(self, user_id: int) -> Dict[str, Any]:
        """
        Check if user has available parsing attempts
        Returns: {"has_limit": bool, "remaining": int, "is_premium": bool}
        """
        # Check global access flag first - if open, all users have unlimited access
        if await self.is_access_open():
            return {
                "has_limit": True,
                "remaining": -1,  # -1 means unlimited
                "is_premium": True  # Treat as premium for UI purposes
            }

        user = await self.get_user(user_id)

        if not user:
            # Create new user
            await self.create_user(user_id)
            return {
                "has_limit": True,
                "remaining": config.FREE_PARSING_LIMIT,
                "is_premium": False
            }

        # Admin always has unlimited access
        if user_id == config.ADMIN_ID:
            return {
                "has_limit": True,
                "remaining": -1,  # -1 означает безлимит
                "is_premium": True
            }

        is_premium = bool(user["is_premium"])
        parsing_count = user["parsing_count"]
        remaining = max(0, config.FREE_PARSING_LIMIT - parsing_count)

        has_limit = is_premium or remaining > 0

        return {
            "has_limit": has_limit,
            "remaining": -1 if is_premium else remaining,
            "is_premium": is_premium
        }

    async def decrease_limit(self, user_id: int) -> bool:
        """
        Decrease user's parsing limit by 1
        Returns: True if limit was decreased, False if no limit available
        """
        limit_info = await self.check_limit(user_id)

        if not limit_info["has_limit"]:
            return False

        # Don't decrease for premium users
        if limit_info["is_premium"]:
            return True

        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            await db.execute("""
                UPDATE users
                SET parsing_count = parsing_count + 1,
                    last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()

        logger.info(f"Parsing count increased for user {user_id}")
        return True

    async def set_premium(self, user_id: int, is_premium: bool = True) -> bool:
        """Set user premium status"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    UPDATE users
                    SET is_premium = ?
                    WHERE user_id = ?
                """, (1 if is_premium else 0, user_id))
                await db.commit()
                logger.info(f"Premium status set to {is_premium} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error setting premium status: {e}")
            return False

    async def reset_limit(self, user_id: int) -> bool:
        """Reset user's parsing count to 0"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    UPDATE users
                    SET parsing_count = 0
                    WHERE user_id = ?
                """, (user_id,))
                await db.commit()
                logger.info(f"Parsing limit reset for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error resetting limit: {e}")
            return False

    async def save_user_session(
        self,
        user_id: int,
        phone_number: str,
        session_name: str
    ) -> bool:
        """Save user's Telethon session info (with retry on database lock)"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                    await self._setup_connection(db)
                    
                    # Сначала проверяем, есть ли деактивированная сессия
                    async with db.execute(
                        "SELECT is_active FROM user_sessions WHERE session_name = ?",
                        (session_name,)
                    ) as cursor:
                        existing = await cursor.fetchone()

                    if existing is not None:
                        # Сессия существует - реактивируем её
                        await db.execute("""
                            UPDATE user_sessions
                            SET is_active = 1, user_id = ?, phone_number = ?
                            WHERE session_name = ?
                        """, (user_id, phone_number, session_name))
                        await db.commit()
                        logger.info(f"Session reactivated for user {user_id}: {phone_number}")
                        return True
                    else:
                        # Новая сессия - создаём
                        await db.execute("""
                            INSERT INTO user_sessions (user_id, phone_number, session_name)
                            VALUES (?, ?, ?)
                        """, (user_id, phone_number, session_name))
                        await db.commit()
                        logger.info(f"Session saved for user {user_id}: {phone_number}")
                        return True

            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 0.5  # 0.5s, 1.0s, 1.5s
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Database error after {attempt + 1} attempts: {e}")
                return False
            except Exception as e:
                logger.error(f"Error saving session: {e}")
                return False
        
        return False

    async def get_user_sessions(self, user_id: int) -> list:
        """Get all active sessions for user"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM user_sessions
                WHERE user_id = ? AND is_active = 1
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def deactivate_session(self, session_name: str) -> bool:
        """Deactivate a session"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    UPDATE user_sessions
                    SET is_active = 0
                    WHERE session_name = ?
                """, (session_name,))
                await db.commit()
                logger.info(f"Session deactivated: {session_name}")
                return True
        except Exception as e:
            logger.error(f"Error deactivating session: {e}")
            return False

    async def add_parsing_history(
        self,
        user_id: int,
        target_link: str,
        parse_type: str,
        time_filter: Optional[str] = None,
        users_found: int = 0,
        admins_found: int = 0
    ):
        """Add parsing record to history"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            await db.execute("""
                INSERT INTO parsing_history
                (user_id, target_link, parse_type, time_filter, users_found, admins_found)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, target_link, parse_type, time_filter, users_found, admins_found))
            await db.commit()

    async def get_stats(self) -> Dict[str, int]:
        """Get overall bot statistics"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            # Total users
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            # Premium users
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cursor:
                premium_users = (await cursor.fetchone())[0]

            # Total parsings
            async with db.execute("SELECT COUNT(*) FROM parsing_history") as cursor:
                total_parsings = (await cursor.fetchone())[0]

            # Total users found
            async with db.execute("SELECT SUM(users_found) FROM parsing_history") as cursor:
                total_users_found = (await cursor.fetchone())[0] or 0

            return {
                "total_users": total_users,
                "premium_users": premium_users,
                "total_parsings": total_parsings,
                "total_users_found": total_users_found
            }

    async def get_user_statistics(self) -> list[Dict[str, Any]]:
        """
        Get detailed statistics for all users
        Returns list with: user_id, username, joined_date, days_in_bot, total_parses, is_premium
        """
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT
                    user_id,
                    username,
                    first_name,
                    last_name,
                    registered_at,
                    parsing_count,
                    is_premium,
                    last_activity,
                    CAST((julianday('now') - julianday(registered_at)) AS INTEGER) as days_in_bot
                FROM users
                ORDER BY registered_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


    # ===== УПРАВЛЕНИЕ АДМИНАМИ БОТА =====
    
    async def add_bot_admin(self, user_id: int, added_by: int) -> bool:
        """Добавить админа бота"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO bot_admins (user_id, added_by)
                    VALUES (?, ?)
                """, (user_id, added_by))
                await db.commit()
                logger.info(f"Bot admin added: {user_id} by {added_by}")
                return True
        except Exception as e:
            logger.error(f"Error adding bot admin: {e}")
            return False
    
    async def remove_bot_admin(self, user_id: int) -> bool:
        """Удалить админа бота"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    DELETE FROM bot_admins WHERE user_id = ?
                """, (user_id,))
                await db.commit()
                logger.info(f"Bot admin removed: {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing bot admin: {e}")
            return False
    
    async def is_bot_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь админом бота"""
        # Главный админ из конфига всегда админ
        if user_id == config.ADMIN_ID:
            return True
        
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            async with db.execute(
                "SELECT 1 FROM bot_admins WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                return await cursor.fetchone() is not None
    
    async def get_bot_admins(self) -> list[Dict[str, Any]]:
        """Получить список всех админов бота"""
        admins = []
        
        # Добавляем главного админа
        admins.append({
            "user_id": config.ADMIN_ID,
            "added_by": None,
            "added_at": "Главный админ",
            "is_main": True
        })
        
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT user_id, added_by, added_at FROM bot_admins
                ORDER BY added_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    if row["user_id"] != config.ADMIN_ID:
                        admins.append({
                            "user_id": row["user_id"],
                            "added_by": row["added_by"],
                            "added_at": row["added_at"],
                            "is_main": False
                        })
        
        return admins

    # ===== УПРАВЛЕНИЕ ГЛОБАЛЬНЫМ ДОСТУПОМ =====

    async def set_access_open(self, status: bool) -> bool:
        """Set global access open/closed flag"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                    VALUES ('is_access_open', ?, CURRENT_TIMESTAMP)
                """, ('1' if status else '0',))
                await db.commit()
                logger.info(f"Global access set to: {'OPEN' if status else 'CLOSED'}")
                return True
        except Exception as e:
            logger.error(f"Error setting access status: {e}")
            return False

    async def is_access_open(self) -> bool:
        """Check if global access is open for all users"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                async with db.execute(
                    "SELECT value FROM bot_settings WHERE key = 'is_access_open'"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0] == '1'
                    return False  # Default: access is closed (3 trial parsings)
        except Exception as e:
            logger.error(f"Error checking access status: {e}")
            return False  # Default to closed on error

    # ===== КЭШИРОВАНИЕ ПРОВЕРКИ ПОДПИСКИ =====
    
    async def is_subscription_verified(self, user_id: int) -> bool:
        """Проверить, подтверждена ли подписка пользователя (кэш)"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                async with db.execute(
                    "SELECT subscription_verified FROM users WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return bool(row[0])
                    return False
        except Exception as e:
            logger.error(f"Error checking subscription status: {e}")
            return False
    
    async def set_subscription_verified(self, user_id: int, verified: bool = True) -> bool:
        """Сохранить статус подтверждения подписки в БД"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    UPDATE users
                    SET subscription_verified = ?
                    WHERE user_id = ?
                """, (1 if verified else 0, user_id))
                await db.commit()
                logger.info(f"Subscription verified status set to {verified} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error setting subscription status: {e}")
            return False

    # ===== РЕФЕРАЛЬНАЯ СИСТЕМА =====
    
    async def add_referral_bonus(self, referrer_id: int, new_user_id: int) -> bool:
        """
        Начислить бонус пригласившему пользователю.
        Вызывается когда новый пользователь регистрируется по реф. ссылке.
        Returns: True если бонус начислен
        """
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                # Проверяем что бонус ещё не был начислен за этого юзера
                async with db.execute(
                    "SELECT referral_bonus_given FROM users WHERE user_id = ?",
                    (new_user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        logger.info(f"Referral bonus already given for user {new_user_id}")
                        return False
                
                # Начисляем бонус рефереру (уменьшаем parsing_count, что увеличивает remaining)
                # parsing_count - это использованные парсинги, уменьшаем чтобы увеличить остаток
                await db.execute("""
                    UPDATE users
                    SET parsing_count = MAX(0, parsing_count - ?)
                    WHERE user_id = ?
                """, (config.REFERRAL_BONUS, referrer_id))
                
                # Отмечаем что бонус за этого юзера уже выдан
                await db.execute("""
                    UPDATE users
                    SET referral_bonus_given = 1
                    WHERE user_id = ?
                """, (new_user_id,))
                
                await db.commit()
                logger.info(f"Referral bonus +{config.REFERRAL_BONUS} given to user {referrer_id} for inviting {new_user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error adding referral bonus: {e}")
            return False
    
    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику рефералов пользователя"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            # Количество приглашённых
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
                (user_id,)
            ) as cursor:
                invited_count = (await cursor.fetchone())[0]
            
            # Общий заработанный бонус
            total_bonus = invited_count * config.REFERRAL_BONUS
            
            return {
                "invited_count": invited_count,
                "total_bonus": total_bonus
            }
    
    async def add_parsing_attempts(self, user_id: int, amount: int) -> bool:
        """Добавить попытки парсинга пользователю (уменьшить parsing_count)"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
                await db.execute("""
                    UPDATE users
                    SET parsing_count = MAX(0, parsing_count - ?)
                    WHERE user_id = ?
                """, (amount, user_id))
                await db.commit()
                logger.info(f"Added {amount} parsing attempts to user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding parsing attempts: {e}")
            return False

    async def backup_database(self, backup_dir: Path = None) -> Optional[Path]:
        """
        Создать бэкап базы данных.
        Вызывайте раз в сутки через scheduler.
        """
        try:
            if backup_dir is None:
                backup_dir = config.BASE_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"database_backup_{timestamp}.db"
            
            # Используем SQLite backup API для консистентного бэкапа
            async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as source:
                async with aiosqlite.connect(backup_path) as dest:
                    await source.backup(dest)
            
            logger.info(f"Database backup created: {backup_path}")
            
            # Удаляем старые бэкапы (старше 7 дней)
            await self._cleanup_old_backups(backup_dir, days=7)
            
            return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None
    
    async def _cleanup_old_backups(self, backup_dir: Path, days: int = 7):
        """Удалить бэкапы старше N дней"""
        cutoff = datetime.now().timestamp() - (days * 86400)
        for backup_file in backup_dir.glob("database_backup_*.db"):
            if backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                logger.info(f"Old backup removed: {backup_file}")

    # ===== РАССЫЛКИ =====

    async def get_all_user_ids(self) -> list[int]:
        """Получить список всех user_id из базы данных"""
        async with aiosqlite.connect(self.db_path, timeout=self.DB_TIMEOUT) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]


# Global database instance
db = Database()
