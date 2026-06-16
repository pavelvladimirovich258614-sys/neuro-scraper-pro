# ParsingService - Руководство по использованию

## Что было создано

Файл `services/parsing_service.py` - сервисный слой для бизнес-логики парсинга.

## Основные преимущества

### ✅ Разделение ответственности
- **Handlers** - только UI-логика (показ меню, обработка нажатий, сообщения)
- **ParsingService** - бизнес-логика (проверка лимитов, выбор сессии, запуск парсинга)
- **TelethonCore** - низкоуровневая работа с Telegram API

### ✅ Типизация
Все классы и методы полностью типизированы с использованием `typing`:

```python
from typing import Optional, List, Dict, Any, Callable, Tuple

@dataclass
class LimitCheckResult:
    has_limit: bool
    remaining: int
    is_premium: bool
    message: Optional[str] = None
```

### ✅ Тестируемость
Теперь бизнес-логику можно тестировать независимо от UI.

## Структура классов

### LimitCheckResult
Результат проверки лимитов пользователя.

```python
@dataclass
class LimitCheckResult:
    has_limit: bool  # Может ли пользователь парсить
    remaining: int   # Оставшееся количество (-1 для безлимита)
    is_premium: bool # Премиум статус
    message: Optional[str] = None  # Дополнительное сообщение
```

### SessionSelection
Результат выбора сессии.

```python
@dataclass
class SessionSelection:
    session_name: str      # Имя выбранной сессии
    is_user_session: bool   # True - пользовательская, False - системная
    info_message: str       # Сообщение для пользователя
```

### ParsingRequest
Данные запроса на парсинг.

```python
@dataclass
class ParsingRequest:
    user_id: int
    link: str
    parse_type: str  # "channel_posts", "channel_single", "chat_active", "chat_participants"
    time_filter: Optional[str] = None
    time_days: Optional[int] = None
    session_name: Optional[str] = None
    is_user_session: bool = False
    parse_bio: bool = False
    detect_gender: bool = False
    max_posts: int = 50
    max_users: int = 200
    chat_mode: str = "active"
    custom_posts_count: Optional[int] = None
```

### ParsingSummary
Сводка завершенного парсинга.

```python
@dataclass
class ParsingSummary:
    users_count: int
    admins_count: int
    premium_count: int
    messages_scanned: int
    parsing_time: float
    target_title: str
    excel_path: Path
    txt_path: Path
```

## Инициализация

В `main.py`:

```python
from services import init_parsing_service, get_parsing_service
from database import db
from services.telethon_core import telethon_core

async def on_startup():
    # ... другой код ...

    # Инициализация сервисного слоя
    init_parsing_service(db, telethon_core)
    logger.info("Parsing service initialized")
```

## Использование в Handlers

### Пример 1: Проверка лимитов

```python
from services import get_parsing_service
from aiogram.types import CallbackQuery

@router.callback_query(F.data == "parse_channel_posts")
async def start_parse_channel_posts(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    service = get_parsing_service()

    # Проверяем лимит
    can_parse, error_msg = await service.can_parse(user_id)

    if not can_parse:
        await callback.message.edit_text(
            error_msg,
            reply_markup=keyboards.get_limit_exceeded_menu_v2(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Продолжаем парсинг...
```

### Пример 2: Выбор сессии

```python
from services import get_parsing_service

@router.callback_query(F.data.startswith("time_"))
async def select_time_filter(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    service = get_parsing_service()

    # Выбираем сессию
    session = service.select_session(user_id)

    await state.update_data(
        session_name=session.session_name,
        is_user_session=session.is_user_session
    )

    await callback.message.edit_text(
        f"🎯 <b>Сессия:</b> {session.info_message}",
        parse_mode="HTML"
    )
```

### Пример 3: Выполнение парсинга

```python
from services import get_parsing_service, ParsingRequest
from aiogram.types import CallbackQuery
import time

@router.callback_query(F.data == "confirm_parsing")
async def execute_parsing(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    service = get_parsing_service()

    data = await state.get_data()

    # Создаем запрос
    request = service.create_parsing_request(
        user_id=user_id,
        link=data['link'],
        parse_type=data['parse_type'],
        time_filter=data.get('time_filter'),
        time_days=data.get('time_days'),
        session_name=data.get('session_name'),
        parse_bio=data.get('parse_bio', False),
        detect_gender=data.get('detect_gender', False),
        max_posts=data.get('max_posts', 50)
    )

    progress_msg = await callback.message.edit_text("🚀 Парсинг...")

    # Progress callback
    async def progress_callback(scanned, total, users_found, status: str = None):
        await progress_msg.edit_text(
            f"🚀 <b>Парсинг...</b>\n\n"
            f"📊 Сканировано: {scanned}\n"
            f"👥 Найдено: {users_found}"
        )

    # Выполняем парсинг
    result = await service.execute_parsing(request, progress_callback)

    # Проверяем ошибки
    if result.errors:
        error_text = "\n".join(result.errors)
        await progress_msg.edit_text(f"❌ Ошибка:\n{error_text}")
        return

    # Уменьшаем лимит
    await service.decrease_limit(user_id)

    # Сохраняем историю
    await service.save_parsing_history(
        user_id=user_id,
        target_link=request.link,
        parse_type=request.parse_type,
        time_filter=request.time_filter,
        users_found=len(result.users),
        admins_found=len(result.admins)
    )

    # Генерируем отчеты...
    # ...
```

### Пример 4: Валидация

```python
from services import get_parsing_service

@router.message()
async def process_link(message: Message, state: FSMContext):
    service = get_parsing_service()
    link = message.text.strip()

    # Валидация ссылки
    is_valid, error_msg = service.validate_link(link)

    if not is_valid:
        await message.answer(error_msg, parse_mode="HTML")
        return

    # Продолжаем...
```

## Методы ParsingService

### Проверка лимитов

```python
async def check_limit(user_id: int) -> LimitCheckResult
    """Проверить лимит пользователя"""

async def can_parse(user_id: int) -> Tuple[bool, Optional[str]]
    """Может ли пользователь парсить"""

async def decrease_limit(user_id: int) -> bool
    """Уменьшить лимит на 1"""
```

### Управление сессиями

```python
def select_session(user_id: int, prefer_user_session: bool = True) -> SessionSelection
    """Выбрать подходящую сессию"""
```

### Выполнение парсинга

```python
async def parse_channel_posts(request, progress_callback) -> ParsingResult
async def parse_channel_single(request, progress_callback) -> ParsingResult
async def parse_chat_active_members(request, progress_callback) -> ParsingResult
async def parse_chat_participants(request, progress_callback) -> ParsingResult
async def parse_chat_by_id(request, chat_id, progress_callback) -> ParsingResult

async def execute_parsing(request, progress_callback) -> ParsingResult
    """Универсальный метод для всех типов парсинга"""
```

### История

```python
async def save_parsing_history(
    user_id, target_link, parse_type,
    time_filter, users_found, admins_found
) -> bool
    """Сохранить операцию в историю"""
```

### Валидация

```python
@staticmethod
def validate_link(link: str) -> Tuple[bool, Optional[str]]
    """Валидировать ссылку"""

@staticmethod
def validate_time_filter(time_key: str) -> Tuple[bool, Optional[int]]
    """Валидировать временной фильтр"""

@staticmethod
def get_time_days_from_filter(time_key: str) -> Optional[int]
    """Получить количество дней из фильтра"""
```

### Утилиты

```python
def create_parsing_request(user_id, link, parse_type, **kwargs) -> ParsingRequest
    """Создать объект запроса из параметров"""
```

## Преимущества рефакторинга

### До (в хендлерах):
```python
# Проверка лимита (дублируется в каждом хендлере)
limit_info = await db.check_limit(user_id)
if not limit_info["has_limit"]:
    await callback.message.edit_text("...")
    return

# Выбор сессии (нетипизированный dict)
session_name, is_user_session = telethon_core.get_smart_session(user_id)

# Парсинг (прямой вызов telethon)
result = await telethon_core.parse_channel_comments(...)

# Уменьшение лимита (прямой вызов db)
await db.decrease_limit(user_id)
```

### После (через сервис):
```python
service = get_parsing_service()

# Проверка лимита (типизированная)
can_parse, error_msg = await service.can_parse(user_id)
if not can_parse:
    await callback.message.edit_text(error_msg)
    return

# Выбор сессии (типизированная)
session = service.select_session(user_id)

# Создание запроса (типизированный)
request = service.create_parsing_request(
    user_id=user_id,
    link=link,
    parse_type=parse_type
)

# Выполнение (типизированная)
result = await service.execute_parsing(request, progress_callback)

# Уменьшение лимита (типизированная)
await service.decrease_limit(user_id)
```

## Следующие шаги

1. **Интегрировать в handlers** - Заменить прямые вызовы `db` и `telethon_core` на методы `ParsingService`
2. **Добавить тесты** - Создать unit-тесты для бизнес-логики
3. **Добавить логирование** - Улучшить логирование в сервисном слое
4. **Обработка ошибок** - Добавить кастомные исключения для разных сценариев

---

**Создано:** 2025-01-29
**Автор:** Clawdbot AI Assistant
