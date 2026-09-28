"""
SQLite-backed FSM storage для aiogram 3.

Заменяет MemoryStorage, который терял все незавершённые сценарии при
перезапуске бота (пользователь застревал на «введите код»). Состояние и
данные FSM хранятся в отдельном SQLite-файле и переживают рестарт.

Использует собственное соединение и asyncio.Lock — изолировано от основной
базы данных бота, чтобы не конкурировать за её единое соединение.
"""

import json
import asyncio
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

logger = logging.getLogger(__name__)


# TTL FSM-состояний (сек): пользователь, не завершивший сценарий за это
# время, вернётся в чистое состояние при следующем взаимодействии.
FSM_TTL = 24 * 3600


class SQLiteStorage(BaseStorage):
    """Персистентное хранилище FSM на SQLite с TTL состояний."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        """Лениво создать и настроить соединение + таблицу."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path, timeout=30.0)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA busy_timeout=30000")
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm (
                    key TEXT PRIMARY KEY,
                    state TEXT,
                    data TEXT,
                    updated_at REAL
                )
            """)
            # Миграция старой таблицы без updated_at
            try:
                await self._conn.execute("ALTER TABLE fsm ADD COLUMN updated_at REAL")
            except Exception:
                pass  # колонка уже есть
            # Чистим просроченные состояния при старте (TTL)
            await self._conn.execute(
                "DELETE FROM fsm WHERE updated_at IS NOT NULL AND updated_at < ?",
                (time.time() - FSM_TTL,)
            )
            await self._conn.commit()
        return self._conn

    @staticmethod
    def _build_key(key: StorageKey) -> str:
        """Собрать строковый ключ из StorageKey."""
        return (
            f"{key.bot_id}:{key.chat_id}:{key.user_id}:"
            f"{key.thread_id}:{key.business_connection_id}:{key.destiny}"
        )

    @staticmethod
    def _resolve_state(state: Optional[Union[str, State]]) -> Optional[str]:
        """Привести state к строке (или None)."""
        if state is None:
            return None
        if isinstance(state, State):
            return state.state
        return str(state)

    async def set_state(self, key: StorageKey, state: Optional[Union[str, State]] = None) -> None:
        s = self._resolve_state(state)
        skey = self._build_key(key)
        async with self._lock:
            conn = await self._get_conn()
            # UPSERT: сохраняем state, не затирая существующие data
            await conn.execute(
                """
                INSERT INTO fsm (key, state, data, updated_at) VALUES (?, ?, NULL, ?)
                ON CONFLICT(key) DO UPDATE SET state = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (skey, s, time.time()),
            )
            await conn.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        skey = self._build_key(key)
        async with self._lock:
            conn = await self._get_conn()
            async with conn.execute(
                "SELECT state, updated_at FROM fsm WHERE key = ?", (skey,)
            ) as cur:
                row = await cur.fetchone()
                if row and row[1] is not None and (time.time() - row[1]) > FSM_TTL:
                    return None  # состояние просрочено — считаем отсутствующим
                return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        skey = self._build_key(key)
        payload = json.dumps(data, ensure_ascii=False) if data else None
        async with self._lock:
            conn = await self._get_conn()
            await conn.execute(
                """
                INSERT INTO fsm (key, state, data, updated_at) VALUES (?, NULL, ?, ?)
                ON CONFLICT(key) DO UPDATE SET data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (skey, payload, time.time()),
            )
            await conn.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        skey = self._build_key(key)
        async with self._lock:
            conn = await self._get_conn()
            async with conn.execute(
                "SELECT data, updated_at FROM fsm WHERE key = ?", (skey,)
            ) as cur:
                row = await cur.fetchone()
                if row and row[1] is not None and (time.time() - row[1]) > FSM_TTL:
                    return {}  # данные просрочены — начинаем сценарий заново
        if not row or not row[0]:
            return {}
        try:
            return json.loads(row[0])
        except json.JSONDecodeError as e:
            logger.warning(f"FSM data corrupted for {skey}: {e}")
            return {}

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
