"""
Глобальная конфигурация тестов.
Подставляем тестовые переменные окружения ДО импорта config
(config падает при их отсутствии).
"""

import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test-hash")
os.environ.setdefault("ADMIN_ID", "999999")
