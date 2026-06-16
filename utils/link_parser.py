"""
Чистые функции разбора ссылок Telegram.

Вынесено из telethon_core, чтобы парсинг ссылок был тестируемым отдельно
от сетевых вызовов (именно в разборе ссылок жили баги «работает через раз»
для приватных постов t.me/c/<id>/<msg>).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PostLinkInfo:
    """Результат разбора ссылки на конкретный пост."""
    is_private: bool                 # True для t.me/c/<id>/<msg>
    message_id: int                  # ID сообщения/поста
    channel_id: Optional[int] = None  # для приватного канала (t.me/c/<id>)
    username: Optional[str] = None    # для публичного канала (@name)


def parse_post_link(link: str) -> PostLinkInfo:
    """Разобрать ссылку на пост канала.

    Поддерживаемые форматы:
      - https://t.me/channel_username/123
      - https://t.me/c/1234567890/123 (приватный канал по ID)
      - t.me/channel/123
      - с query-параметрами (?thread=...) — отбрасываются

    Raises:
        ValueError: если формат ссылки некорректен.
    """
    if not link or not link.strip():
        raise ValueError("Пустая ссылка")

    # Убираем схему и хвостовые слэши
    clean = link.strip().replace("https://", "").replace("http://", "").rstrip("/")
    parts = clean.split("/")

    # Минимум: t.me/channel/123 или t.me/c/id/123
    if len(parts) < 3:
        raise ValueError("Неверный формат ссылки. Используйте: t.me/channel/123")

    # Приватный канал: t.me/c/<id>/<msg>
    if parts[1] == "c":
        if len(parts) < 4:
            raise ValueError("Неверный формат приватной ссылки: t.me/c/<id>/<msg>")
        channel_id = int(parts[2])
        message_id = int(parts[3].split("?")[0])
        return PostLinkInfo(is_private=True, channel_id=channel_id, message_id=message_id)

    # Публичный канал: t.me/<username>/<msg>
    username = parts[1]
    message_id = int(parts[2].split("?")[0])
    return PostLinkInfo(is_private=False, username=username, message_id=message_id)
