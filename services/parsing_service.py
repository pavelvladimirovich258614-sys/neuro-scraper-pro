"""
Parsing Service Module
Business logic layer for parsing operations with limit checking and session management
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple

from database import Database
from services.telethon_core import TelethonCore, ParsedUser, ParsingResult
import config

logger = logging.getLogger(__name__)


@dataclass
class LimitCheckResult:
    """Result of limit checking"""
    has_limit: bool  # User can parse
    remaining: int  # Remaining attempts (-1 for unlimited)
    is_premium: bool  # User has premium
    message: Optional[str] = None  # Additional message (e.g., error)


@dataclass
class SessionSelection:
    """Result of session selection"""
    session_name: str  # Name of selected session
    is_user_session: bool  # True if user's session, False if system
    info_message: str  # User-friendly message about session


@dataclass
class ParsingRequest:
    """Request data for parsing operation"""
    user_id: int
    link: str
    parse_type: str  # "channel_posts", "channel_single", "chat_members", "chat_participants"
    time_filter: Optional[str] = None  # "day", "week", "month", "3months", "alltime"
    time_days: Optional[int] = None
    session_name: Optional[str] = None
    is_user_session: bool = False
    parse_bio: bool = False
    detect_gender: bool = False
    max_posts: int = 50
    max_users: int = 200
    chat_mode: str = "active"  # "active" or "members"
    custom_posts_count: Optional[int] = None


@dataclass
class ParsingSummary:
    """Summary of completed parsing"""
    users_count: int
    admins_count: int
    premium_count: int
    messages_scanned: int
    parsing_time: float
    target_title: str
    excel_path: Path
    txt_path: Path


class ParsingService:
    """
    Service layer for parsing operations.
    Handles business logic: limit checking, session selection, parsing execution.
    Separates concerns from handlers (UI) and telethon_core (low-level parsing).
    """

    def __init__(self, db: Database, telethon_core: TelethonCore):
        self.db = db
        self.telethon = telethon_core

    # ===== LIMIT MANAGEMENT =====

    async def check_limit(self, user_id: int) -> LimitCheckResult:
        """
        Check if user has available parsing attempts.

        Args:
            user_id: Telegram user ID

        Returns:
            LimitCheckResult with limit status and remaining count
        """
        limit_info = await self.db.check_limit(user_id)

        return LimitCheckResult(
            has_limit=limit_info["has_limit"],
            remaining=limit_info["remaining"],
            is_premium=limit_info["is_premium"]
        )

    async def can_parse(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if user can perform parsing.

        Args:
            user_id: Telegram user ID

        Returns:
            Tuple of (can_parse: bool, error_message: Optional[str])
        """
        limit_result = await self.check_limit(user_id)

        if not limit_result.has_limit:
            message = (
                f"❌ <b>Лимит исчерпан ({config.FREE_PARSING_LIMIT}/{config.FREE_PARSING_LIMIT})</b>\n\n"
                "Ваши бесплатные парсинги закончились.\n\n"
                f"💡 <b>Способы получить больше:</b>\n"
                "• Купить подписку\n"
                f"• Пригласить друга (+{config.REFERRAL_BONUS} парсинга)"
            )
            return False, message

        return True, None

    async def decrease_limit(self, user_id: int) -> bool:
        """
        Decrease user's parsing limit by 1.

        Args:
            user_id: Telegram user ID

        Returns:
            True if limit was decreased, False if no limit available
        """
        return await self.db.decrease_limit(user_id)

    # ===== SESSION MANAGEMENT =====

    def select_session(self, user_id: int, prefer_user_session: bool = True) -> SessionSelection:
        """
        Smart session selection based on user ID and preferences.

        Args:
            user_id: Telegram user ID
            prefer_user_session: If True, prioritize user sessions over system

        Returns:
            SessionSelection with chosen session and info message
        """
        session_name, is_user_session = self.telethon.get_smart_session(user_id)

        if is_user_session:
            info_message = "✅ Используется ваш аккаунт (доступ к приватным чатам)"
        else:
            info_message = "⚠️ Используется системный аккаунт (только публичные)"

        return SessionSelection(
            session_name=session_name,
            is_user_session=is_user_session,
            info_message=info_message
        )

    # ===== PARSING EXECUTION =====

    async def parse_channel_posts(
        self,
        request: ParsingRequest,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Parse recent posts from a channel.

        Args:
            request: Parsing request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data
        """
        return await self.telethon.parse_channel_comments(
            session_name=request.session_name,
            channel_link=request.link,
            time_filter_days=request.time_days,
            max_posts=request.max_posts,
            parse_bio=request.parse_bio,
            detect_gender=request.detect_gender,
            progress_callback=progress_callback
        )

    async def parse_channel_single(
        self,
        request: ParsingRequest,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Parse a specific post from a channel.

        Args:
            request: Parsing request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data
        """
        return await self.telethon.parse_single_post(
            session_name=request.session_name,
            post_link=request.link,
            time_filter_days=request.time_days,
            parse_bio=request.parse_bio,
            detect_gender=request.detect_gender,
            progress_callback=progress_callback
        )

    async def parse_chat_active_members(
        self,
        request: ParsingRequest,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Parse active members from a chat (by messages).

        Args:
            request: Parsing request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data
        """
        return await self.telethon.parse_chat_members(
            session_name=request.session_name,
            chat_link=request.link,
            time_filter_days=request.time_days,
            parse_bio=request.parse_bio,
            detect_gender=request.detect_gender,
            progress_callback=progress_callback
        )

    async def parse_chat_participants(
        self,
        request: ParsingRequest,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Parse all participants from a chat (GetParticipantsRequest).

        Args:
            request: Parsing request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data
        """
        return await self.telethon.parse_chat_participants(
            session_name=request.session_name,
            chat_link=request.link,
            max_users=request.max_users,
            parse_bio=request.parse_bio,
            detect_gender=request.detect_gender,
            progress_callback=progress_callback
        )

    async def parse_chat_by_id(
        self,
        request: ParsingRequest,
        chat_id: int,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Parse chat by ID (for "My Chats" feature).

        Args:
            request: Parsing request parameters
            chat_id: Telegram chat ID
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data
        """
        return await self.telethon.parse_chat_by_id(
            session_name=request.session_name,
            chat_id=chat_id,
            max_messages=request.max_posts,
            time_filter_days=request.time_days,
            parse_bio=request.parse_bio,
            detect_gender=request.detect_gender,
            progress_callback=progress_callback
        )

    async def execute_parsing(
        self,
        request: ParsingRequest,
        progress_callback: Optional[Callable[[int, int, int, Optional[str]], None]] = None
    ) -> ParsingResult:
        """
        Execute parsing based on request type.

        Args:
            request: Parsing request parameters
            progress_callback: Optional callback for progress updates

        Returns:
            ParsingResult with parsed data

        Raises:
            ValueError: If parse_type is invalid
        """
        logger.info(f"[ParsingService] Executing parse_type={request.parse_type} for user={request.user_id}")

        if request.parse_type == "channel_posts":
            return await self.parse_channel_posts(request, progress_callback)
        elif request.parse_type == "channel_single":
            return await self.parse_channel_single(request, progress_callback)
        elif request.parse_type == "chat_active":
            return await self.parse_chat_active_members(request, progress_callback)
        elif request.parse_type == "chat_participants":
            return await self.parse_chat_participants(request, progress_callback)
        elif request.parse_type == "chat_by_id":
            if not hasattr(request, 'chat_id'):
                raise ValueError("chat_id is required for parse_type='chat_by_id'")
            return await self.parse_chat_by_id(
                request, request.chat_id, progress_callback
            )
        else:
            raise ValueError(f"Invalid parse_type: {request.parse_type}")

    # ===== PARSING HISTORY =====

    async def save_parsing_history(
        self,
        user_id: int,
        target_link: str,
        parse_type: str,
        time_filter: Optional[str],
        users_found: int,
        admins_found: int
    ) -> bool:
        """
        Save parsing operation to history.

        Args:
            user_id: Telegram user ID
            target_link: Link or ID of target
            parse_type: Type of parsing performed
            time_filter: Time filter used (if any)
            users_found: Number of users found
            admins_found: Number of admins found

        Returns:
            True if saved successfully
        """
        return await self.db.add_parsing_history(
            user_id=user_id,
            target_link=target_link,
            parse_type=parse_type,
            time_filter=time_filter,
            users_found=users_found,
            admins_found=admins_found
        )

    # ===== VALIDATION =====

    @staticmethod
    def validate_link(link: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Telegram link format.

        Args:
            link: Link to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not link.strip():
            return False, "Ссылка не может быть пустой"

        valid_prefixes = [
            "https://t.me/",
            "http://t.me/",
            "@",
            "t.me/",
            "https://telegram.me/",
            "http://telegram.me/"
        ]

        if not any(link.startswith(prefix) for prefix in valid_prefixes):
            return False, (
                "⚠️ <b>Неверный формат ссылки</b>\n\n"
                "Отправьте ссылку в одном из форматов:\n"
                "• https://t.me/channel_name\n"
                "• @channel_name"
            )

        return True, None

    @staticmethod
    def validate_time_filter(time_key: str) -> Tuple[bool, Optional[int]]:
        """
        Validate and convert time filter key to days.

        Args:
            time_key: Time filter key ("day", "week", "month", "3months", "alltime")

        Returns:
            Tuple of (is_valid, time_days)
        """
        if time_key == "alltime":
            return True, None

        time_days = config.TIME_FILTERS.get(time_key)

        if time_days is None:
            return False, None

        return True, time_days

    @staticmethod
    def get_time_days_from_filter(time_key: str) -> Optional[int]:
        """
        Get number of days from time filter key.

        Args:
            time_key: Time filter key

        Returns:
            Number of days or None for "alltime"
        """
        if time_key == "alltime":
            return None
        return config.TIME_FILTERS.get(time_key)

    # ===== UTILITIES =====

    def create_parsing_request(
        self,
        user_id: int,
        link: str,
        parse_type: str,
        **kwargs
    ) -> ParsingRequest:
        """
        Create a ParsingRequest object from parameters.

        Args:
            user_id: Telegram user ID
            link: Target link
            parse_type: Type of parsing
            **kwargs: Additional request parameters

        Returns:
            ParsingRequest object
        """
        return ParsingRequest(
            user_id=user_id,
            link=link,
            parse_type=parse_type,
            **kwargs
        )


# ===== GLOBAL SERVICE INSTANCE =====

# This will be initialized in main.py and imported in handlers
parsing_service: Optional[ParsingService] = None


def init_parsing_service(db: Database, telethon_core: TelethonCore) -> ParsingService:
    """
    Initialize the global parsing service instance.

    Args:
        db: Database instance
        telethon_core: TelethonCore instance

    Returns:
        Initialized ParsingService instance
    """
    global parsing_service
    parsing_service = ParsingService(db, telethon_core)
    logger.info("ParsingService initialized")
    return parsing_service


def get_parsing_service() -> ParsingService:
    """
    Get the global parsing service instance.

    Returns:
        ParsingService instance

    Raises:
        RuntimeError: If service is not initialized
    """
    if parsing_service is None:
        raise RuntimeError("ParsingService not initialized. Call init_parsing_service() first.")
    return parsing_service
