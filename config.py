"""
Configuration module for NeuroScraper Pro Bot
Loads environment variables and provides application settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).parent

# Telegram Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

# Admin Configuration
ADMIN_ID = int(os.getenv("ADMIN_ID", "1831192124"))

# Telethon API Credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

if not API_ID or not API_HASH:
    raise ValueError("API_ID и API_HASH должны быть установлены в переменных окружения")

# Support Link
SUPPORT_LINK = os.getenv("SUPPORT_LINK", "https://t.me/NeuroCash_Support_Bot")

# Database Configuration
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "database.db")

# Session Storage
SESSIONS_DIR = BASE_DIR / os.getenv("SESSIONS_DIR", "sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

# User Limits
FREE_PARSING_LIMIT = 3  # Бесплатных парсингов для новых пользователей
REFERRAL_BONUS = 2  # Бонус за приглашённого друга

# Parsing Configuration
PARSING_DELAY_MIN = 0.5  # Minimum delay between requests (seconds)
PARSING_DELAY_MAX = 2.0  # Maximum delay between requests (seconds)

# Time filters (days)
TIME_FILTERS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "3months": 90
}

# Telethon Client Settings
DEVICE_MODEL = "Desktop"
SYSTEM_VERSION = "Windows 10"
APP_VERSION = "1.0"

# System session (for admin/public parsing)
SYSTEM_SESSION_NAME = "system_session"
SYSTEM_SESSION_PATH = SESSIONS_DIR / f"{SYSTEM_SESSION_NAME}.session"
