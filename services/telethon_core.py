"""
Telethon Core Service
Handles all Telegram parsing operations using Telethon MTProto client
"""

import asyncio
import logging
import random
import functools
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Callable
from dataclasses import dataclass, field

from telethon import TelegramClient, errors, functions, types
from telethon.tl.types import User, Channel, Chat, Message
from telethon.errors import (
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    PasswordHashInvalidError,
    AuthKeyUnregisteredError,
    UserDeactivatedError,
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatAdminRequiredError
)
from telethon.errors.rpcerrorlist import AuthKeyError
from telethon.tl.functions.messages import ImportChatInviteRequest, GetDialogsRequest
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    ChannelParticipantsSearch,
    InputPeerEmpty,
    DialogFilter
)

import config

logger = logging.getLogger(__name__)

# Максимальное время ожидания FloodWait (секунды)
MAX_FLOOD_WAIT = 300  # 5 минут
# Количество попыток переподключения
MAX_RECONNECT_ATTEMPTS = 3


def handle_flood_wait(max_retries: int = 3):
    """
    Декоратор для автоматической обработки FloodWaitError.
    Ждёт указанное время и повторяет запрос.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except FloodWaitError as e:
                    wait_time = e.seconds
                    if wait_time > MAX_FLOOD_WAIT:
                        logger.warning(f"FloodWait {wait_time}s exceeds max {MAX_FLOOD_WAIT}s, aborting")
                        raise
                    logger.warning(f"FloodWait: sleeping {wait_time}s (attempt {retries + 1}/{max_retries})")
                    await asyncio.sleep(wait_time + 1)  # +1 для надёжности
                    retries += 1
            raise FloodWaitError(request=None, capture=wait_time)
        return wrapper
    return decorator


@dataclass
class ParsedUser:
    """Структура распарсенного пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    last_activity: Optional[datetime] = None
    message_count: int = 0
    is_bot: bool = False
    is_admin: bool = False
    phone: Optional[str] = None
    # Новые поля для Advanced Features
    bio: Optional[str] = None
    gender: Optional[str] = None  # 'M', 'F', 'неизвестно'
    is_premium: bool = False


@dataclass
class ParsingResult:
    """Результат парсинга"""
    users: List[ParsedUser] = field(default_factory=list)
    admins: List[ParsedUser] = field(default_factory=list)
    raw_messages: List[Dict[str, Any]] = field(default_factory=list)
    target_title: Optional[str] = None
    total_messages_scanned: int = 0
    parsing_time: float = 0.0
    errors: List[str] = field(default_factory=list)


class TelethonCore:
    """Ядро для работы с Telethon и парсинга"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.active_sessions: Dict[str, bool] = {}

    def get_smart_session(self, user_id: int) -> Tuple[str, bool]:
        """
        Умный выбор сессии: приоритет пользовательской над системной.
        
        Returns: (session_name, is_user_session)
        - session_name: имя сессии для использования
        - is_user_session: True если это пользовательская сессия
        """
        sessions_dir = config.SESSIONS_DIR
        user_prefix = f"user_{user_id}_"
        
        logger.debug(f"[SmartSession] Looking for sessions with prefix: {user_prefix}")
        logger.debug(f"[SmartSession] Sessions dir: {sessions_dir}")
        
        # Ищем любую сессию пользователя в папке sessions
        for session_file in sessions_dir.glob(f"{user_prefix}*.session"):
            session_name = session_file.stem  # без .session
            logger.info(f"[SmartSession] ✅ Found USER session: {session_name}")
            return session_name, True
        
        # Пользовательской сессии нет - используем системную
        logger.info(f"[SmartSession] ⚠️ No user session for {user_id}, using SYSTEM session")
        return config.SYSTEM_SESSION_NAME, False

    async def create_client(
        self,
        session_name: str,
        phone: Optional[str] = None
    ) -> TelegramClient:
        """Создать и инициализировать клиента Telethon"""
        session_path = config.SESSIONS_DIR / f"{session_name}.session"

        client = TelegramClient(
            str(session_path),
            config.API_ID,
            config.API_HASH,
            device_model=config.DEVICE_MODEL,
            system_version=config.SYSTEM_VERSION,
            app_version=config.APP_VERSION
        )

        self.clients[session_name] = client
        return client

    async def send_code(self, phone: str, session_name: str) -> Tuple[bool, str, Any]:
        """
        Отправить код авторизации на номер телефона
        Returns: (success, message, phone_code_hash)

        Специальные коды:
        - "ALREADY_AUTHORIZED" - сессия уже авторизована, можно использовать
        """
        try:
            client = await self.create_client(session_name, phone)
            await client.connect()

            if await client.is_user_authorized():
                # Сессия уже авторизована - можно использовать без ввода кода
                logger.info(f"Session already authorized for {phone}, reusing")
                await client.disconnect()
                return True, "ALREADY_AUTHORIZED", None

            # Отправляем код
            sent_code = await client.send_code_request(phone)
            phone_code_hash = sent_code.phone_code_hash

            logger.info(f"Code sent to {phone}")
            return True, "Код отправлен", phone_code_hash

        except PhoneNumberInvalidError:
            return False, "Неверный формат номера телефона. Используйте формат: +79991234567", None
        except FloodWaitError as e:
            wait_time = e.seconds
            return False, f"Слишком много попыток. Подождите {wait_time} секунд", None
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            return False, f"Ошибка отправки кода: {str(e)}", None

    async def sign_in(
        self,
        phone: str,
        code: str,
        phone_code_hash: str,
        session_name: str,
        password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Авторизация с кодом (и опционально с паролем 2FA)
        Returns: (success, message)
        """
        try:
            client = self.clients.get(session_name)
            if not client:
                return False, "Сессия не найдена. Начните авторизацию заново"

            # КРИТИЧНО: Жёсткая проверка и восстановление соединения перед ЛЮБОЙ операцией
            # Это исправляет ошибку "Cannot send requests while disconnected"
            for attempt in range(MAX_RECONNECT_ATTEMPTS):
                if not client.is_connected():
                    try:
                        logger.info(f"[SignIn] Reconnecting client (attempt {attempt + 1})...")
                        await client.connect()
                        logger.info(f"[SignIn] Client reconnected successfully")
                        break
                    except Exception as e:
                        logger.error(f"[SignIn] Failed to reconnect (attempt {attempt + 1}): {e}")
                        if attempt == MAX_RECONNECT_ATTEMPTS - 1:
                            return False, "Потеряно соединение. Попробуйте заново"
                        await asyncio.sleep(1)
                else:
                    break

            # Если передан пароль - это повторный вызов для 2FA
            if password:
                # КРИТИЧНО: Повторная проверка соединения перед 2FA
                if not client.is_connected():
                    logger.info(f"[SignIn 2FA] Client disconnected, reconnecting...")
                    await client.connect()

                try:
                    await client.sign_in(password=password)
                    self.active_sessions[session_name] = True
                    logger.info(f"Successfully signed in with 2FA: {phone}")
                    return True, "Авторизация с 2FA успешна!"
                except PasswordHashInvalidError:
                    return False, "Неверный пароль 2FA. Попробуйте ещё раз"
                finally:
                    await client.disconnect()

            # Первичная авторизация с кодом
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                self.active_sessions[session_name] = True
                logger.info(f"Successfully signed in: {phone}")
                await client.disconnect()
                return True, "Авторизация успешна!"

            except SessionPasswordNeededError:
                # Требуется 2FA пароль - НЕ отключаем клиента!
                logger.info(f"2FA required for {phone}")
                return False, "NEED_2FA"

        except PhoneCodeInvalidError:
            return False, "Неверный код. Попробуйте еще раз"
        except PhoneCodeExpiredError:
            logger.warning(f"Phone code expired for {phone}")
            return False, "CODE_EXPIRED"
        except PasswordHashInvalidError:
            return False, "Неверный пароль 2FA"
        except FloodWaitError as e:
            return False, f"Слишком много попыток. Подождите {e.seconds} секунд"
        except Exception as e:
            logger.error(f"Error signing in: {e}")
            return False, f"Ошибка авторизации: {str(e)}"

    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        """Получить активного клиента по имени сессии с автоматическим переподключением"""
        session_path = config.SESSIONS_DIR / f"{session_name}.session"
        
        logger.info(f"[GetClient] Requesting client for session: {session_name}")
        logger.info(f"[GetClient] Session path: {session_path}")
        logger.info(f"[GetClient] Session exists: {session_path.exists()}")

        if not session_path.exists():
            logger.error(f"[GetClient] ❌ Session file NOT FOUND: {session_path}")
            return None

        client = await self.create_client(session_name)
        logger.info(f"[GetClient] Client created for: {session_name}")

        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                if not client.is_connected():
                    await client.connect()

                if not await client.is_user_authorized():
                    logger.error(f"Session not authorized: {session_name}")
                    await client.disconnect()
                    return None

                return client

            except (OSError, ConnectionError) as e:
                logger.warning(f"Connection failed (attempt {attempt + 1}/{MAX_RECONNECT_ATTEMPTS}): {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1, 2, 4 sec
                continue
            except (AuthKeyUnregisteredError, UserDeactivatedError, AuthKeyError) as e:
                logger.error(f"Session invalidated: {e}")
                await client.disconnect()
                return None
            except Exception as e:
                logger.error(f"Error getting client: {e}")
                if client:
                    await client.disconnect()
                return None

        logger.error(f"Failed to connect after {MAX_RECONNECT_ATTEMPTS} attempts")
        return None
    
    async def ensure_connected(self, client: TelegramClient) -> bool:
        """Проверить и восстановить соединение если нужно"""
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                if client.is_connected():
                    return True
                await client.connect()
                return True
            except (OSError, ConnectionError) as e:
                logger.warning(f"Reconnect attempt {attempt + 1}: {e}")
                await asyncio.sleep(2 ** attempt)
        return False

    async def get_client_with_fallback(self, session_name: str) -> Tuple[Optional[TelegramClient], str]:
        """
        Получить клиента с fallback на системную сессию.
        
        Returns: (client, actual_session_name)
        - Если user session не авторизована, пробует system session
        """
        # Пробуем основную сессию
        client = await self.get_client(session_name)
        if client:
            logger.info(f"[Fallback] Using requested session: {session_name}")
            return client, session_name
        
        # Fallback на системную сессию
        if session_name != config.SYSTEM_SESSION_NAME:
            logger.warning(f"[Fallback] Session {session_name} failed, trying SYSTEM session")
            client = await self.get_client(config.SYSTEM_SESSION_NAME)
            if client:
                logger.info(f"[Fallback] Using SYSTEM session as fallback")
                return client, config.SYSTEM_SESSION_NAME
        
        logger.error(f"[Fallback] All sessions failed!")
        return None, session_name

    async def parse_channel_comments(
        self,
        session_name: str,
        channel_link: str,
        time_filter_days: Optional[int] = None,
        max_posts: int = 50,
        parse_bio: bool = False,
        detect_gender: bool = False,
        progress_callback=None
    ) -> ParsingResult:
        """
        Парсинг комментариев из канала
        """
        result = ParsingResult()
        client = None
        start_time = datetime.now()

        try:
            client, actual_session = await self.get_client_with_fallback(session_name)
            if not client:
                result.errors.append("Не удалось подключиться. Переподключите аккаунт.")
                return result

            # Получаем канал
            try:
                entity = await client.get_entity(channel_link)
                result.target_title = getattr(entity, 'title', channel_link)
            except Exception as e:
                result.errors.append(f"Не удалось найти канал: {str(e)}")
                return result

            logger.info(f"Parsing channel: {result.target_title}")

            # Время фильтра
            cutoff_date = None
            if time_filter_days:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_filter_days)

            users_dict: Dict[int, ParsedUser] = {}
            admins_dict: Dict[int, ParsedUser] = {}
            posts_scanned = 0

            # Получаем администраторов канала
            try:
                admins = await self._get_channel_admins(client, entity)
                for admin in admins:
                    admins_dict[admin.user_id] = admin
                    admin.is_admin = True
            except Exception as e:
                logger.warning(f"Could not fetch admins: {e}")

            # ОПТИМИЗАЦИЯ: Батчинг - обрабатываем сообщения пачками
            BATCH_SIZE = 50
            batch_count = 0

            # Итерируемся по постам канала
            async for message in client.iter_messages(entity, limit=max_posts):
                posts_scanned += 1

                # Проверяем временной фильтр
                if cutoff_date and message.date < cutoff_date:
                    logger.info(f"Reached cutoff date at post {posts_scanned}")
                    break

                # Собираем комментарии к посту
                if message.replies and message.replies.replies > 0:
                    try:
                        comment_batch = 0

                        async for comment in client.iter_messages(
                            entity,
                            reply_to=message.id,
                            limit=None
                        ):
                            comment_batch += 1

                            # Проверяем временной фильтр для комментария
                            if cutoff_date and comment.date < cutoff_date:
                                continue

                            if comment.sender:
                                user = await self._process_user(
                                    comment.sender,
                                    comment.date,
                                    users_dict
                                )

                                if user and not user.is_bot:
                                    # Определяем пол если включено
                                    if detect_gender and not user.gender:
                                        user.gender = self._detect_gender(user.first_name)

                                    # Получаем био если включено
                                    if parse_bio and not user.bio:
                                        user.bio = await self._get_user_bio(client, user.user_id)
                                        await asyncio.sleep(random.uniform(0.3, 0.8))

                                    # Сохраняем raw данные
                                    result.raw_messages.append({
                                        "user_id": user.user_id,
                                        "username": user.username,
                                        "text": comment.text[:200] if comment.text else "",
                                        "date": comment.date.isoformat(),
                                        "message_link": f"https://t.me/{entity.username}/{message.id}?thread={comment.id}" if hasattr(entity, 'username') and entity.username else ""
                                    })

                            # БАТЧИНГ: пауза только после каждых N комментариев
                            if comment_batch >= BATCH_SIZE:
                                await asyncio.sleep(random.uniform(0.3, 0.6))
                                comment_batch = 0

                    except errors.MsgIdInvalidError:
                        logger.warning(f"Invalid message ID for replies: {message.id}")
                    except FloodWaitError as e:
                        # Автоматическое ожидание FloodWait с уведомлением
                        if e.seconds <= MAX_FLOOD_WAIT:
                            logger.warning(f"FloodWait in comments: waiting {e.seconds}s")
                            if progress_callback:
                                await progress_callback(
                                    posts_scanned, max_posts, len(users_dict),
                                    status=f"⏳ Пауза {e.seconds}с (защита от бана)"
                                )
                            await asyncio.sleep(e.seconds + 1)
                        else:
                            raise
                    except Exception as e:
                        logger.error(f"Error fetching comments for post {message.id}: {e}")

                batch_count += 1

                # Прогресс callback
                if progress_callback:
                    await progress_callback(posts_scanned, max_posts, len(users_dict))

                # БАТЧИНГ: пауза только после каждых N постов
                if batch_count >= BATCH_SIZE:
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    batch_count = 0

            # Финальная обработка
            result.users = list(users_dict.values())
            result.admins = list(admins_dict.values())
            result.total_messages_scanned = posts_scanned

            logger.info(f"Parsing completed. Found {len(result.users)} users, {len(result.admins)} admins")

        except FloodWaitError as e:
            # FloodWait на уровне канала - ждём и продолжаем с сохранённым прогрессом
            if e.seconds <= MAX_FLOOD_WAIT:
                logger.warning(f"FloodWait at channel level: waiting {e.seconds}s, keeping partial results")
                await asyncio.sleep(e.seconds + 1)
                # Сохраняем частичные результаты
                result.users = list(users_dict.values()) if 'users_dict' in dir() else []
                result.admins = list(admins_dict.values()) if 'admins_dict' in dir() else []
                result.errors.append(f"Парсинг частично завершён (FloodWait {e.seconds}с)")
            else:
                error_msg = f"FloodWait слишком долгий: {e.seconds} секунд"
                result.errors.append(error_msg)
                logger.warning(error_msg)
        except Exception as e:
            error_msg = f"Ошибка парсинга: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                await client.disconnect()

            result.parsing_time = (datetime.now() - start_time).total_seconds()

        return result

    async def parse_single_post(
        self,
        session_name: str,
        post_link: str,
        time_filter_days: Optional[int] = None,  # ИГНОРИРУЕТСЯ для single post
        parse_bio: bool = False,
        detect_gender: bool = False,
        progress_callback=None
    ) -> ParsingResult:
        """
        Парсинг комментариев к одному конкретному посту.

        Поддерживаемые форматы ссылок:
        - https://t.me/channel_username/123 (публичный)
        - https://t.me/c/1234567890/123 (приватный по ID)
        - t.me/channel/123

        ВАЖНО: time_filter_days игнорируется - парсим ВСЕ комментарии к посту!
        """
        result = ParsingResult()
        client = None
        start_time = datetime.now()

        try:
            client, actual_session = await self.get_client_with_fallback(session_name)
            if not client:
                result.errors.append("Не удалось подключиться. Переподключите аккаунт.")
                return result

            # Улучшенный парсер ссылки на пост
            # Поддержка форматов:
            # - https://t.me/channel_username/123
            # - https://t.me/c/1234567890/123 (приватный канал по ID)
            # - t.me/channel/123
            try:
                # Убираем https:// и http://
                clean_link = post_link.replace("https://", "").replace("http://", "").rstrip("/")
                parts = clean_link.split("/")

                logger.info(f"[SinglePost] Parsing link: {post_link} -> parts: {parts}")

                # Минимум должно быть: t.me/channel/123 или t.me/c/id/123
                if len(parts) < 3:
                    result.errors.append("Неверный формат ссылки. Используйте: t.me/channel/123")
                    return result

                entity = None
                message_id = None

                # Формат: t.me/c/1234567890/123 (приватный канал)
                if parts[1] == "c" and len(parts) >= 4:
                    channel_id = int(parts[2])
                    message_id = int(parts[3].split("?")[0])  # Убираем query params
                    # Для приватных каналов нужен специальный формат ID
                    # Telegram использует -100 + channel_id для супергрупп/каналов
                    full_channel_id = int(f"-100{channel_id}")
                    logger.info(f"[SinglePost] Private channel ID: {channel_id} -> {full_channel_id}, msg: {message_id}")
                    entity = await client.get_entity(full_channel_id)

                # Формат: t.me/channel_username/123 (публичный канал)
                else:
                    channel_username = parts[1]
                    message_id = int(parts[2].split("?")[0])  # Убираем query params
                    logger.info(f"[SinglePost] Public channel: @{channel_username}, msg: {message_id}")
                    entity = await client.get_entity(channel_username)

                result.target_title = getattr(entity, 'title', str(entity.id))

                # Получаем конкретное сообщение
                message = await client.get_messages(entity, ids=message_id)
                if not message:
                    result.errors.append(f"Пост с ID {message_id} не найден")
                    return result

                logger.info(f"[SinglePost] Message found: {message.id}, replies: {message.replies}")

            except ValueError as ve:
                result.errors.append(f"Неверный формат ID в ссылке: {str(ve)}")
                return result
            except Exception as e:
                result.errors.append(f"Не удалось получить пост: {str(e)}")
                logger.error(f"[SinglePost] Error getting post: {e}")
                return result

            logger.info(f"Parsing single post from: {result.target_title} (msg ID: {message_id})")

            # ВАЖНО: Для режима single post ИГНОРИРУЕМ фильтр даты!
            # Мы парсим ВСЕ комментарии к конкретному посту
            cutoff_date = None  # Всегда None для single post

            users_dict: Dict[int, ParsedUser] = {}
            admins_dict: Dict[int, ParsedUser] = {}
            comments_scanned = 0

            # Получаем администраторов канала
            try:
                admins = await self._get_channel_admins(client, entity)
                for admin in admins:
                    admins_dict[admin.user_id] = admin
                    admin.is_admin = True
            except Exception as e:
                logger.warning(f"Could not fetch admins: {e}")

            # Собираем комментарии к посту
            if message.replies and message.replies.replies > 0:
                try:
                    # Батчинг: собираем комментарии пачками без delay после каждого
                    batch_count = 0
                    BATCH_SIZE = 50

                    async for comment in client.iter_messages(
                        entity,
                        reply_to=message.id,
                        limit=None
                    ):
                        comments_scanned += 1
                        batch_count += 1

                        # НЕ проверяем cutoff_date - парсим ВСЕ комментарии к посту!

                        if comment.sender:
                            user = await self._process_user(
                                comment.sender,
                                comment.date,
                                users_dict
                            )

                            if user and not user.is_bot:
                                # Определяем пол если включено
                                if detect_gender and not user.gender:
                                    user.gender = self._detect_gender(user.first_name)

                                # Получаем био если включено (медленная операция!)
                                if parse_bio and not user.bio:
                                    user.bio = await self._get_user_bio(client, user.user_id)
                                    await asyncio.sleep(random.uniform(0.3, 0.8))

                                # Сохраняем raw данные
                                result.raw_messages.append({
                                    "user_id": user.user_id,
                                    "username": user.username,
                                    "text": comment.text[:200] if comment.text else "",
                                    "date": comment.date.isoformat(),
                                    "message_link": f"https://t.me/{entity.username}/{message.id}?thread={comment.id}" if hasattr(entity, 'username') and entity.username else ""
                                })

                        # БАТЧИНГ: пауза только после каждых N сообщений
                        if batch_count >= BATCH_SIZE:
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            batch_count = 0

                        # Прогресс callback
                        if progress_callback and comments_scanned % 10 == 0:
                            await progress_callback(comments_scanned, message.replies.replies, len(users_dict))

                except errors.MsgIdInvalidError:
                    result.errors.append("Неверный ID сообщения")
                    logger.warning(f"Invalid message ID for replies: {message.id}")
                except Exception as e:
                    error_msg = f"Ошибка при сборе комментариев: {str(e)}"
                    result.errors.append(error_msg)
                    logger.error(error_msg)
            else:
                result.errors.append("У этого поста нет комментариев")

            # Финальная обработка
            result.users = list(users_dict.values())
            result.admins = list(admins_dict.values())
            result.total_messages_scanned = comments_scanned

            logger.info(f"Single post parsing completed. Found {len(result.users)} users, {len(result.admins)} admins")

        except FloodWaitError as e:
            error_msg = f"FloodWait: необходимо подождать {e.seconds} секунд"
            result.errors.append(error_msg)
            logger.warning(error_msg)
        except Exception as e:
            error_msg = f"Ошибка парсинга: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                await client.disconnect()

            result.parsing_time = (datetime.now() - start_time).total_seconds()

        return result

    async def parse_chat_members(
        self,
        session_name: str,
        chat_link: str,
        time_filter_days: Optional[int] = None,
        max_messages: int = 1000,
        parse_bio: bool = False,
        detect_gender: bool = False,
        progress_callback=None
    ) -> ParsingResult:
        """
        Парсинг участников чата по активности в сообщениях
        """
        result = ParsingResult()
        client = None
        start_time = datetime.now()

        try:
            client, actual_session = await self.get_client_with_fallback(session_name)
            if not client:
                result.errors.append("Не удалось подключиться. Переподключите аккаунт.")
                return result

            # Получаем чат
            try:
                entity = await client.get_entity(chat_link)
                result.target_title = getattr(entity, 'title', chat_link)
            except Exception as e:
                result.errors.append(f"Не удалось найти чат: {str(e)}")
                return result

            logger.info(f"Parsing chat: {result.target_title}")

            # Время фильтра
            cutoff_date = None
            if time_filter_days:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_filter_days)

            users_dict: Dict[int, ParsedUser] = {}
            admins_dict: Dict[int, ParsedUser] = {}
            messages_scanned = 0

            # Получаем администраторов
            try:
                admins = await self._get_chat_admins(client, entity)
                for admin in admins:
                    admins_dict[admin.user_id] = admin
                    admin.is_admin = True
            except Exception as e:
                logger.warning(f"Could not fetch admins: {e}")

            # ОПТИМИЗАЦИЯ: Батчинг - обрабатываем сообщения пачками
            BATCH_SIZE = 50
            batch_count = 0

            # Итерируемся по сообщениям
            async for message in client.iter_messages(entity, limit=max_messages):
                messages_scanned += 1
                batch_count += 1

                # Проверяем временной фильтр
                if cutoff_date and message.date < cutoff_date:
                    logger.info(f"Reached cutoff date at message {messages_scanned}")
                    break

                if message.sender:
                    user = await self._process_user(
                        message.sender,
                        message.date,
                        users_dict
                    )

                    if user and not user.is_bot:
                        # Определяем пол если включено
                        if detect_gender and not user.gender:
                            user.gender = self._detect_gender(user.first_name)

                        # Получаем био если включено
                        if parse_bio and not user.bio:
                            user.bio = await self._get_user_bio(client, user.user_id)
                            await asyncio.sleep(random.uniform(0.3, 0.8))

                        # Сохраняем raw данные
                        result.raw_messages.append({
                            "user_id": user.user_id,
                            "username": user.username,
                            "text": message.text[:200] if message.text else "",
                            "date": message.date.isoformat(),
                            "message_link": f"https://t.me/c/{str(entity.id)[4:]}/{message.id}" if hasattr(entity, 'id') else ""
                        })

                # Прогресс callback каждые 20 сообщений
                if progress_callback and messages_scanned % 20 == 0:
                    await progress_callback(messages_scanned, max_messages, len(users_dict))

                # БАТЧИНГ: пауза только после каждых N сообщений
                if batch_count >= BATCH_SIZE:
                    await asyncio.sleep(random.uniform(0.3, 0.6))
                    batch_count = 0

            # Финальная обработка
            result.users = list(users_dict.values())
            result.admins = list(admins_dict.values())
            result.total_messages_scanned = messages_scanned

            logger.info(f"Parsing completed. Found {len(result.users)} users, {len(result.admins)} admins")

        except FloodWaitError as e:
            error_msg = f"FloodWait: необходимо подождать {e.seconds} секунд"
            result.errors.append(error_msg)
            logger.warning(error_msg)
        except Exception as e:
            error_msg = f"Ошибка парсинга: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                await client.disconnect()

            result.parsing_time = (datetime.now() - start_time).total_seconds()

        return result

    async def _process_user(
        self,
        sender: User,
        message_date: datetime,
        users_dict: Dict[int, ParsedUser]
    ) -> Optional[ParsedUser]:
        """Обработка пользователя из сообщения"""
        if not isinstance(sender, User):
            return None

        # Пропускаем ботов (если не админ ID)
        if sender.bot and sender.id != config.ADMIN_ID:
            return None

        # Скрываем админа из результатов
        if sender.id == config.ADMIN_ID:
            return None

        user_id = sender.id

        if user_id in users_dict:
            # Обновляем существующего пользователя
            user = users_dict[user_id]
            user.message_count += 1
            # Обновляем last_activity если сообщение новее
            if user.last_activity is None or message_date > user.last_activity:
                user.last_activity = message_date
        else:
            # Создаем нового пользователя
            user = ParsedUser(
                user_id=user_id,
                username=sender.username,
                first_name=sender.first_name,
                last_name=sender.last_name,
                last_activity=message_date,
                message_count=1,
                is_bot=sender.bot,
                phone=sender.phone
            )
            users_dict[user_id] = user

        return user

    async def _get_channel_admins(
        self,
        client: TelegramClient,
        channel
    ) -> List[ParsedUser]:
        """Получить список администраторов канала"""
        admins = []
        try:
            participants = await client.get_participants(
                channel,
                filter=types.ChannelParticipantsAdmins
            )

            for participant in participants:
                if isinstance(participant, User) and not participant.bot:
                    # Скрываем админа
                    if participant.id == config.ADMIN_ID:
                        continue

                    admin = ParsedUser(
                        user_id=participant.id,
                        username=participant.username,
                        first_name=participant.first_name,
                        last_name=participant.last_name,
                        is_admin=True,
                        is_bot=participant.bot,
                        phone=participant.phone
                    )
                    admins.append(admin)

        except Exception as e:
            logger.error(f"Error getting channel admins: {e}")

        return admins

    async def _get_chat_admins(
        self,
        client: TelegramClient,
        chat
    ) -> List[ParsedUser]:
        """Получить список администраторов чата"""
        admins = []
        try:
            # Для обычных чатов
            if isinstance(chat, Chat):
                full_chat = await client(functions.messages.GetFullChatRequest(chat.id))
                for participant in full_chat.full_chat.participants.participants:
                    if hasattr(participant, 'user_id'):
                        user = await client.get_entity(participant.user_id)
                        if isinstance(user, User) and not user.bot:
                            # Скрываем админа
                            if user.id == config.ADMIN_ID:
                                continue

                            admin = ParsedUser(
                                user_id=user.id,
                                username=user.username,
                                first_name=user.first_name,
                                last_name=user.last_name,
                                is_admin=True,
                                is_bot=user.bot,
                                phone=user.phone
                            )
                            admins.append(admin)

            # Для супергрупп/каналов
            else:
                return await self._get_channel_admins(client, chat)

        except Exception as e:
            logger.error(f"Error getting chat admins: {e}")

        return admins

    async def _random_delay(self, multiplier: float = 1.0):
        """
        Случайная задержка для антидетекта.
        multiplier увеличивает задержку при интенсивном парсинге.
        """
        base_delay = random.uniform(config.PARSING_DELAY_MIN, config.PARSING_DELAY_MAX)
        delay = base_delay * multiplier
        await asyncio.sleep(delay)
    
    async def _adaptive_delay(self, requests_count: int):
        """
        Адаптивная задержка: увеличивается с количеством запросов.
        Помогает избежать FloodWait при долгом парсинге.
        """
        # Увеличиваем множитель каждые 100 запросов
        multiplier = 1.0 + (requests_count // 100) * 0.2
        multiplier = min(multiplier, 3.0)  # Максимум x3
        await self._random_delay(multiplier)

    async def join_chat(
        self,
        session_name: str,
        chat_link: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Вступить в группу/канал по ссылке.
        
        Поддерживаемые форматы:
        - https://t.me/channel_name (публичный)
        - https://t.me/+ABC123xyz (приватная ссылка)
        - https://t.me/joinchat/ABC123xyz (старый формат)
        - @channel_name
        
        Returns: (success, message, chat_title)
        """
        client = None
        try:
            client = await self.get_client(session_name)
            if not client:
                return False, "Не удалось подключиться к аккаунту", None
            
            chat_link = chat_link.strip()
            chat_title = None
            
            # Определяем тип ссылки
            if "/+" in chat_link or "/joinchat/" in chat_link:
                # Приватная ссылка-приглашение
                # Извлекаем хэш из ссылки
                if "/+" in chat_link:
                    invite_hash = chat_link.split("/+")[-1].split("?")[0].strip()
                else:
                    invite_hash = chat_link.split("/joinchat/")[-1].split("?")[0].strip()
                
                logger.info(f"Joining private chat with hash: {invite_hash[:8]}...")
                
                try:
                    result = await client(ImportChatInviteRequest(invite_hash))
                    chat_title = getattr(result.chats[0], 'title', 'Чат')
                    logger.info(f"Successfully joined: {chat_title}")
                    return True, f"Успешно вступили в чат!", chat_title
                    
                except UserAlreadyParticipantError:
                    # Уже состоим - получаем название
                    try:
                        entity = await client.get_entity(chat_link)
                        chat_title = getattr(entity, 'title', 'Чат')
                    except:
                        pass
                    return True, "Вы уже состоите в этом чате", chat_title
                    
            else:
                # Публичный канал/группа
                if chat_link.startswith("@"):
                    username = chat_link[1:]
                elif "t.me/" in chat_link:
                    username = chat_link.split("t.me/")[-1].split("?")[0].split("/")[0].strip()
                else:
                    username = chat_link
                
                logger.info(f"Joining public channel: @{username}")
                
                try:
                    entity = await client.get_entity(username)
                    chat_title = getattr(entity, 'title', username)
                    
                    await client(JoinChannelRequest(entity))
                    logger.info(f"Successfully joined: {chat_title}")
                    return True, f"Успешно вступили в канал!", chat_title
                    
                except UserAlreadyParticipantError:
                    return True, "Вы уже состоите в этом канале", chat_title
                    
        except InviteHashExpiredError:
            return False, "Ссылка-приглашение устарела или недействительна", None
        except InviteHashInvalidError:
            return False, "Неверная ссылка-приглашение", None
        except ChannelPrivateError:
            return False, "Канал приватный. Используйте ссылку-приглашение", None
        except UserBannedInChannelError:
            return False, "Аккаунт заблокирован в этом чате/канале", None
        except FloodWaitError as e:
            return False, f"Слишком много попыток. Подождите {e.seconds} секунд", None
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error joining chat: {e}")
            
            # Обработка запроса на вступление (канал требует одобрения)
            if "successfully requested to join" in error_str.lower():
                return True, "✅ Заявка на вступление отправлена!\n\nОжидайте одобрения от администраторов.", chat_title
            
            return False, f"Ошибка: {error_str}", None
        finally:
            if client:
                await client.disconnect()

    async def check_session_exists(self, session_name: str) -> bool:
        """Проверить существование файла сессии"""
        session_path = config.SESSIONS_DIR / f"{session_name}.session"
        return session_path.exists()

    async def delete_session(self, session_name: str) -> bool:
        """Удалить файл сессии"""
        try:
            session_path = config.SESSIONS_DIR / f"{session_name}.session"
            if session_path.exists():
                session_path.unlink()
                logger.info(f"Session deleted: {session_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    # ===== НОВЫЕ МЕТОДЫ ДЛЯ ADVANCED FEATURES =====
    
    async def get_user_dialogs(
        self,
        session_name: str,
        limit: int = 20
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Получить список диалогов (чатов/групп) пользователя.
        Для функции "Мои Чаты".
        Returns: (success, message, dialogs_list)
        """
        client = None
        dialogs_list = []
        
        try:
            client = await self.get_client(session_name)
            if not client:
                return False, "Не удалось подключиться к аккаунту", []
            
            # Получаем диалоги
            async for dialog in client.iter_dialogs(limit=limit):
                # Фильтруем только группы и супергруппы
                if dialog.is_group or dialog.is_channel:
                    dialogs_list.append({
                        "id": dialog.id,
                        "title": dialog.title or "Без названия",
                        "is_group": dialog.is_group,
                        "is_channel": dialog.is_channel,
                        "unread_count": dialog.unread_count
                    })
            
            logger.info(f"Found {len(dialogs_list)} dialogs for session {session_name}")
            return True, "OK", dialogs_list
            
        except Exception as e:
            logger.error(f"Error getting dialogs: {e}")
            return False, str(e), []
        finally:
            if client:
                await client.disconnect()
    
    async def parse_chat_participants(
        self,
        session_name: str,
        chat_link: str,
        max_users: int = 200,
        parse_bio: bool = False,
        detect_gender: bool = False,
        progress_callback=None
    ) -> ParsingResult:
        """
        Парсинг участников чата через GetParticipantsRequest.
        Собирает всех участников группы, не только активных.
        """
        result = ParsingResult()
        client = None
        start_time = datetime.now()
        
        try:
            client, actual_session = await self.get_client_with_fallback(session_name)
            if not client:
                result.errors.append("Не удалось подключиться. Переподключите аккаунт.")
                return result
            
            # Получаем чат
            try:
                entity = await client.get_entity(chat_link)
                result.target_title = getattr(entity, 'title', chat_link)
            except Exception as e:
                result.errors.append(f"Не удалось найти чат: {str(e)}")
                return result
            
            logger.info(f"Parsing participants of: {result.target_title}")
            
            users_dict: Dict[int, ParsedUser] = {}
            admins_dict: Dict[int, ParsedUser] = {}
            
            # Сначала получаем админов
            try:
                admins = await self._get_channel_admins(client, entity)
                for admin in admins:
                    admins_dict[admin.user_id] = admin
                    admin.is_admin = True
            except Exception as e:
                logger.warning(f"Could not fetch admins: {e}")
            
            # Пробуем получить участников через iter_participants (без offset)
            try:
                users_fetched = 0
                
                # iter_participants сам управляет пагинацией
                async for participant in client.iter_participants(entity, limit=max_users):
                    try:
                        if not isinstance(participant, User) or participant.bot:
                            continue
                        if participant.id == config.ADMIN_ID:
                            continue
                        
                        user = ParsedUser(
                            user_id=participant.id,
                            username=participant.username,
                            first_name=participant.first_name,
                            last_name=participant.last_name,
                            is_bot=participant.bot,
                            is_premium=getattr(participant, 'premium', False) or False,
                            is_admin=participant.id in admins_dict
                        )
                        
                        # Определяем пол если включено
                        if detect_gender:
                            user.gender = self._detect_gender(participant.first_name)
                        
                        # Получаем био если включено (медленная операция!)
                        if parse_bio:
                            user.bio = await self._get_user_bio(client, participant.id)
                            await asyncio.sleep(random.uniform(0.5, 1.5))
                        
                        users_dict[participant.id] = user
                        users_fetched += 1
                        
                        # Прогресс каждые 10 пользователей
                        if progress_callback and users_fetched % 10 == 0:
                            await progress_callback(users_fetched, max_users, len(users_dict))
                        
                        await self._random_delay(0.3)  # Меньшая задержка для iter
                        
                    except FloodWaitError as e:
                        if e.seconds <= MAX_FLOOD_WAIT:
                            logger.warning(f"FloodWait: waiting {e.seconds}s")
                            if progress_callback:
                                await progress_callback(
                                    users_fetched, max_users, len(users_dict),
                                    status=f"⏳ Пауза {e.seconds}с"
                                )
                            await asyncio.sleep(e.seconds + 1)
                        else:
                            raise
                
            except errors.ChatAdminRequiredError:
                result.errors.append("HIDDEN_MEMBERS")
                logger.warning("Chat participants are hidden by admins")
                return result
            except Exception as e:
                if "CHAT_ADMIN_REQUIRED" in str(e) or "participants are hidden" in str(e).lower():
                    result.errors.append("HIDDEN_MEMBERS")
                    return result
                raise
            
            result.users = list(users_dict.values())
            result.admins = list(admins_dict.values())
            result.total_messages_scanned = len(users_dict)
            
            logger.info(f"Participants parsing completed. Found {len(result.users)} users")
            
        except Exception as e:
            error_msg = f"Ошибка парсинга участников: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                await client.disconnect()
            result.parsing_time = (datetime.now() - start_time).total_seconds()
        
        return result
    
    async def parse_chat_by_id(
        self,
        session_name: str,
        chat_id: int,
        max_messages: int = 200,
        parse_bio: bool = False,
        detect_gender: bool = False,
        progress_callback=None
    ) -> ParsingResult:
        """
        Парсинг чата по ID (для функции "Мои Чаты").
        """
        result = ParsingResult()
        client = None
        start_time = datetime.now()
        
        try:
            client, actual_session = await self.get_client_with_fallback(session_name)
            if not client:
                result.errors.append("Не удалось подключиться. Переподключите аккаунт.")
                return result
            
            # Получаем чат по ID
            try:
                entity = await client.get_entity(chat_id)
                result.target_title = getattr(entity, 'title', str(chat_id))
            except Exception as e:
                result.errors.append(f"Не удалось найти чат: {str(e)}")
                return result
            
            logger.info(f"Parsing chat by ID: {result.target_title}")
            
            users_dict: Dict[int, ParsedUser] = {}
            admins_dict: Dict[int, ParsedUser] = {}
            messages_scanned = 0
            
            # Получаем администраторов
            try:
                admins = await self._get_chat_admins(client, entity)
                for admin in admins:
                    admins_dict[admin.user_id] = admin
                    admin.is_admin = True
            except Exception as e:
                logger.warning(f"Could not fetch admins: {e}")
            
            # Итерируемся по сообщениям
            async for message in client.iter_messages(entity, limit=max_messages):
                messages_scanned += 1
                
                if message.sender:
                    user = await self._process_user_extended(
                        client,
                        message.sender,
                        message.date,
                        users_dict,
                        parse_bio=parse_bio,
                        detect_gender=detect_gender
                    )
                    
                    if user and not user.is_bot:
                        result.raw_messages.append({
                            "user_id": user.user_id,
                            "username": user.username,
                            "text": message.text[:200] if message.text else "",
                            "date": message.date.isoformat()
                        })
                
                if progress_callback and messages_scanned % 20 == 0:
                    await progress_callback(messages_scanned, max_messages, len(users_dict))
                
                # Увеличенная задержка если парсим био
                if parse_bio:
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                else:
                    await self._random_delay()
            
            result.users = list(users_dict.values())
            result.admins = list(admins_dict.values())
            result.total_messages_scanned = messages_scanned
            
            logger.info(f"Chat parsing completed. Found {len(result.users)} users")
            
        except Exception as e:
            error_msg = f"Ошибка парсинга: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        finally:
            if client:
                await client.disconnect()
            result.parsing_time = (datetime.now() - start_time).total_seconds()
        
        return result
    
    async def _process_user_extended(
        self,
        client: TelegramClient,
        sender: User,
        message_date: datetime,
        users_dict: Dict[int, ParsedUser],
        parse_bio: bool = False,
        detect_gender: bool = False
    ) -> Optional[ParsedUser]:
        """Расширенная обработка пользователя с био и полом"""
        if not isinstance(sender, User):
            return None
        
        if sender.bot and sender.id != config.ADMIN_ID:
            return None
        
        if sender.id == config.ADMIN_ID:
            return None
        
        user_id = sender.id
        
        if user_id in users_dict:
            user = users_dict[user_id]
            user.message_count += 1
            if user.last_activity is None or message_date > user.last_activity:
                user.last_activity = message_date
        else:
            user = ParsedUser(
                user_id=user_id,
                username=sender.username,
                first_name=sender.first_name,
                last_name=sender.last_name,
                last_activity=message_date,
                message_count=1,
                is_bot=sender.bot,
                phone=sender.phone,
                is_premium=getattr(sender, 'premium', False) or False
            )
            
            # Определяем пол
            if detect_gender:
                user.gender = self._detect_gender(sender.first_name)
            
            # Получаем био (медленно!)
            if parse_bio:
                user.bio = await self._get_user_bio(client, user_id)
            
            users_dict[user_id] = user
        
        return user
    
    async def _get_user_bio(self, client: TelegramClient, user_id: int) -> Optional[str]:
        """Получить био пользователя через GetFullUserRequest"""
        try:
            full_user = await client(GetFullUserRequest(user_id))
            if full_user and full_user.full_user:
                return full_user.full_user.about
        except FloodWaitError as e:
            logger.warning(f"FloodWait getting bio: {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 30))
        except Exception as e:
            logger.debug(f"Could not get bio for {user_id}: {e}")
        return None
    
    def _detect_gender(self, first_name: Optional[str]) -> str:
        """
        Определить пол по имени (эвристика).
        Основано на окончаниях русских имён.
        """
        if not first_name:
            return "неизвестно"
        
        name = first_name.strip().lower()
        
        # Женские окончания
        female_endings = ('а', 'я', 'ия', 'ья', 'ея')
        # Исключения (мужские имена на а/я)
        male_exceptions = (
            'никита', 'илья', 'данила', 'кузьма', 'фома', 'лука', 
            'савва', 'миша', 'саша', 'вова', 'дима', 'женя', 'валя',
            'костя', 'коля', 'сережа', 'серёжа', 'паша', 'гоша',
            'лёша', 'леша', 'вася', 'петя', 'ваня', 'толя', 'боря',
            'alikhan', 'mustafa', 'nikita', 'ilya'
        )
        # Явно женские имена
        female_names = (
            'мария', 'анна', 'елена', 'ольга', 'наталья', 'татьяна',
            'ирина', 'светлана', 'екатерина', 'марина', 'алина',
            'юлия', 'виктория', 'дарья', 'полина', 'анастасия',
            'ксения', 'валерия', 'кристина', 'диана', 'арина',
            'софия', 'вероника', 'маргарита', 'алёна', 'алена',
            'eva', 'anna', 'maria', 'elena', 'olga', 'natalia'
        )
        # Явно мужские имена
        male_names = (
            'александр', 'сергей', 'андрей', 'алексей', 'дмитрий',
            'максим', 'иван', 'михаил', 'артём', 'артем', 'даниил',
            'кирилл', 'николай', 'егор', 'матвей', 'роман', 'владимир',
            'павел', 'арсений', 'тимофей', 'марк', 'денис', 'антон',
            'alex', 'sergey', 'andrey', 'dmitry', 'maxim', 'ivan',
            'michael', 'kirill', 'roman', 'pavel', 'denis', 'anton'
        )
        
        # Проверяем явные списки
        if name in female_names:
            return "F"
        if name in male_names or name in male_exceptions:
            return "M"
        
        # Проверяем окончания
        if name.endswith(female_endings) and name not in male_exceptions:
            return "F"
        
        return "M"  # По умолчанию мужской (большинство без окончания)


# Глобальный экземпляр
telethon_core = TelethonCore()
