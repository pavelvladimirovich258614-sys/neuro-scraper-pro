"""
Standalone Authentication Script for NeuroScraper Pro
Creates Telegram session file for the bot

Run this BEFORE starting the main bot to create system_session.
"""

import os
import sys
import asyncio
from pathlib import Path
from telethon import TelegramClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Session configuration
SESSIONS_DIR = "sessions"
SESSION_NAME = "system_session"
SESSION_PATH = os.path.join(SESSIONS_DIR, SESSION_NAME)


async def authorize():
    """Async authorization function"""
    print("=" * 60)
    print("       NeuroScraper Pro - Session Authorization Tool")
    print("=" * 60)
    print()

    # Validate environment variables
    if not API_ID or not API_HASH:
        print("ERROR: API_ID or API_HASH not found in .env file!")
        print()
        print("Please create .env file and add:")
        print("API_ID=your_api_id")
        print("API_HASH=your_api_hash")
        print()
        print("Get API_ID and API_HASH here:")
        print("https://my.telegram.org/apps")
        print()
        input("Press Enter to exit...")
        sys.exit(1)

    # Create sessions directory if it doesn't exist
    Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
    print(f"[OK] Directory '{SESSIONS_DIR}' checked/created")
    print()

    # Check if session already exists
    if os.path.exists(f"{SESSION_PATH}.session"):
        print(f"WARNING: Session already exists: {SESSION_PATH}.session")
        print()
        response = input("Do you want to create a new session? (yes/no): ").strip().lower()
        if response not in ["yes", "y", "da"]:
            print("Operation cancelled.")
            input("Press Enter to exit...")
            sys.exit(0)
        print()

    print("=" * 60)
    print("STARTING AUTHORIZATION")
    print("=" * 60)
    print()
    print("Telethon will ask you for:")
    print("1. Phone number (format: +7XXXXXXXXXX)")
    print("2. Confirmation code (will be sent to Telegram)")
    print("3. 2FA password (if you have two-factor authentication enabled)")
    print()
    print("Get ready to enter your data...")
    print()

    try:
        # Create Telethon client
        client = TelegramClient(
            SESSION_PATH,
            int(API_ID),
            API_HASH
        )

        print("Connecting to Telegram...")
        print()

        # Start client - this will prompt for phone, code, and password
        await client.start()

        print()
        print("=" * 60)
        print("SUCCESS! SESSION CREATED!")
        print("=" * 60)
        print()
        print(f"Session file: {SESSION_PATH}.session")
        print()
        print("Now you can run the main bot:")
        print("  - Double click on run_bot.bat")
        print("  - Or command: python main.py")
        print()

        # Disconnect client
        await client.disconnect()

    except KeyboardInterrupt:
        print()
        print("Authorization interrupted by user")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"ERROR during authorization: {e}")
        print()
        print("Possible causes:")
        print("  - Invalid API_ID or API_HASH")
        print("  - Invalid phone number")
        print("  - Invalid confirmation code")
        print("  - Internet connection problems")
        print()
        input("Press Enter to exit...")
        sys.exit(1)


def main():
    """Main entry point"""
    try:
        # Run async authorization
        asyncio.run(authorize())
    except KeyboardInterrupt:
        print()
        print("Operation cancelled")
        sys.exit(1)
    finally:
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
