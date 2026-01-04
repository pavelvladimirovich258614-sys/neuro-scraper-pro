# Пошаговая инструкция по установке и запуску

## Шаг 1: Установка Python

Убедитесь, что у вас установлен Python 3.11 или выше.

### Windows

1. Скачайте Python с [python.org](https://www.python.org/downloads/)
2. При установке обязательно отметьте "Add Python to PATH"
3. Проверьте установку:

```bash
python --version
```

### Linux

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### Mac

```bash
brew install python@3.11
```

## Шаг 2: Получение API ключей

### Telegram Bot Token

1. Откройте Telegram
2. Найдите [@BotFather](https://t.me/BotFather)
3. Отправьте команду `/newbot`
4. Следуйте инструкциям:
   - Введите имя бота (например: "NeuroScraper Pro Bot")
   - Введите username бота (должен заканчиваться на `bot`, например: `neuroscraperpro_bot`)
5. Скопируйте полученный **BOT_TOKEN**

Пример токена: `8505061974:AAHH9uL4s_npxHhHMsZLmrQT-GafhVuiWhU`

### API_ID и API_HASH

1. Перейдите на [https://my.telegram.org](https://my.telegram.org)
2. Войдите, используя свой номер телефона
3. Нажмите "API development tools"
4. Заполните форму:
   - **App title**: NeuroScraper Pro
   - **Short name**: neuroscraper
   - **Platform**: Desktop
   - **Description**: Audience parser bot
5. Нажмите "Create application"
6. Скопируйте:
   - **api_id** (число, например: 18726283)
   - **api_hash** (строка, например: bce69cfec5a71df87a3b64508bf1918e)

### Ваш Telegram ID (ADMIN_ID)

1. Найдите [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте ему любое сообщение
3. Скопируйте ваш **ID** (число, например: 1831192124)

## Шаг 3: Настройка проекта

### 1. Откройте папку проекта

```bash
cd "NeuroScraper Pro"
```

### 2. Создайте файл .env

**Windows:**

```bash
copy .env.example .env
notepad .env
```

**Linux/Mac:**

```bash
cp .env.example .env
nano .env
```

### 3. Заполните .env файл

Откройте `.env` и замените значения на ваши:

```env
# Telegram Bot Configuration
BOT_TOKEN=ВАШ_БОТ_ТОКЕН_СЮДА

# Admin Configuration
ADMIN_ID=ВАШ_TELEGRAM_ID_СЮДА

# Telethon API Credentials
API_ID=ВАШ_API_ID_СЮДА
API_HASH=ВАШ_API_HASH_СЮДА

# Support Link
SUPPORT_LINK=https://t.me/NeuroCash_Support_Bot

# Database
DATABASE_PATH=database.db

# Session Storage
SESSIONS_DIR=sessions
```

**Пример заполненного .env:**

```env
BOT_TOKEN=8505061974:AAHH9uL4s_npxHhHMsZLmrQT-GafhVuiWhU
ADMIN_ID=1831192124
API_ID=18726283
API_HASH=bce69cfec5a71df87a3b64508bf1918e
SUPPORT_LINK=https://t.me/NeuroCash_Support_Bot
DATABASE_PATH=database.db
SESSIONS_DIR=sessions
```

Сохраните файл.

## Шаг 4: Первый запуск

### Windows

Просто дважды кликните на файл:

```
run.bat
```

Скрипт автоматически:
- Создаст виртуальное окружение
- Установит все зависимости
- Запустит бота

### Linux/Mac

Дайте права на выполнение и запустите:

```bash
chmod +x run.sh
./run.sh
```

### Ручная установка (опционально)

Если автоматический запуск не работает:

```bash
# Создать виртуальное окружение
python -m venv venv

# Активировать (Windows)
venv\Scripts\activate

# Активировать (Linux/Mac)
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Запустить бота
python main.py
```

## Шаг 5: Проверка работы

После запуска вы должны увидеть:

```
2025-01-10 12:00:00 - __main__ - INFO - Starting NeuroScraper Pro Bot...
2025-01-10 12:00:00 - __main__ - INFO - Database initialized
2025-01-10 12:00:00 - __main__ - INFO - Directories created
2025-01-10 12:00:00 - __main__ - INFO - Bot started successfully!
2025-01-10 12:00:00 - __main__ - INFO - Starting polling...
```

## Шаг 6: Тестирование бота

1. Откройте Telegram
2. Найдите вашего бота по username (который вы указали при создании)
3. Нажмите "Start" или отправьте `/start`
4. Вы должны увидеть приветственное сообщение с меню

## Возможные проблемы

### "BOT_TOKEN не найден в переменных окружения"

- Убедитесь, что файл `.env` создан в корневой папке проекта
- Проверьте правильность названий переменных (должны быть ЗАГЛАВНЫМИ)
- Убедитесь, что нет пробелов вокруг знака `=`

### "Python не найден"

- Убедитесь, что Python установлен и добавлен в PATH
- Попробуйте использовать `python3` вместо `python`

### "ModuleNotFoundError"

- Убедитесь, что виртуальное окружение активировано
- Переустановите зависимости: `pip install -r requirements.txt`

### Бот не отвечает

- Проверьте правильность BOT_TOKEN
- Убедитесь, что бот запущен и в консоли нет ошибок
- Проверьте интернет-соединение

## Остановка бота

Нажмите `Ctrl+C` в консоли для корректной остановки бота.

## Следующие шаги

После успешного запуска:

1. Проверьте работу всех команд (`/start`, `/help`, `/id`)
2. Попробуйте добавить тестовый аккаунт
3. Выполните тестовый парсинг на небольшом публичном канале
4. Настройте автозапуск бота (опционально)

## Автозапуск при старте системы (опционально)

### Windows (Task Scheduler)

1. Откройте "Планировщик заданий"
2. Создайте новое задание
3. Триггер: При входе в систему
4. Действие: Запустить программу `run.bat`

### Linux (systemd)

Создайте файл `/etc/systemd/system/neuroscraper.service`:

```ini
[Unit]
Description=NeuroScraper Pro Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/NeuroScraper Pro
ExecStart=/path/to/NeuroScraper Pro/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Активируйте:

```bash
sudo systemctl enable neuroscraper
sudo systemctl start neuroscraper
```

## Поддержка

Если у вас возникли проблемы:

1. Проверьте логи в файле `bot.log`
2. Убедитесь, что все зависимости установлены
3. Проверьте правильность всех токенов и ключей
4. Обратитесь в поддержку через Telegram

---

**Удачного использования NeuroScraper Pro!**
