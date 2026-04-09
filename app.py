import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot_data.db"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in environment")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID missing in environment")

ADMIN_ID = int(ADMIN_ID_RAW)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("channel-link-bot")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
polling_task: Optional[asyncio.Task] = None


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()

    defaults = {
        "link1": "https://t.me/example_channel_1",
        "link2": "https://t.me/example_channel_2",
        "start_message": (
            "Welcome!\n\nNeeche diye gaye buttons se channels join kar lo."
        ),
    }
    for key, value in defaults.items():
        set_config(key, value, only_if_missing=True)


def get_config(key: str, fallback: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else fallback


def set_config(key: str, value: str, only_if_missing: bool = False) -> None:
    with get_connection() as conn:
        if only_if_missing:
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, value),
            )
        else:
            conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
        conn.commit()


def upsert_user(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user.id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name
            """,
            (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
            ),
        )
        conn.commit()
    return existing is None


def get_all_user_ids() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [int(row["user_id"]) for row in rows]


def get_user_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"]) if row else 0


def extract_value(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def build_start_keyboard() -> InlineKeyboardMarkup:
    link1 = get_config("link1")
    link2 = get_config("link2")
    buttons = [
        [
            InlineKeyboardButton(text="Channel 1 Join", url=link1),
            InlineKeyboardButton(text="Channel 2 Join", url=link2),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def notify_admin_new_user(message: Message) -> None:
    user = message.from_user
    if not user:
        return

    username = f"@{user.username}" if user.username else "No username"
    full_name = " ".join(
        part for part in [user.first_name, user.last_name] if part
    ).strip()
    text = (
        "<b>New user backup</b>\n"
        f"Name: {full_name or 'Unknown'}\n"
        f"Username: {username}\n"
        f"User ID: <code>{user.id}</code>"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        logger.exception("Failed to send backup info to admin")


async def send_database_backup(caption: str) -> None:
    if not DB_PATH.exists():
        return

    try:
        backup_file = FSInputFile(DB_PATH)
        await bot.send_document(ADMIN_ID, backup_file, caption=caption)
    except Exception:
        logger.exception("Failed to send database backup to admin")


@dp.message(CommandStart())
@dp.message(F.text.regexp(r"(?i)^start$"))
async def start_handler(message: Message) -> None:
    is_new_user = upsert_user(message)
    if is_new_user:
        await notify_admin_new_user(message)
        total_users = get_user_count()
        if total_users % 10 == 0:
            await send_database_backup(
                f"Database backup after {total_users} total users."
            )

    start_message = get_config("start_message")
    await message.answer(start_message, reply_markup=build_start_keyboard())


@dp.message(F.text.regexp(r"^!add1(\s+.+)?$"))
async def add1_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: !add1 https://t.me/your_channel")
        return

    set_config("link1", value)
    await message.reply("Channel 1 link updated.")


@dp.message(F.text.regexp(r"^!add2(\s+.+)?$"))
async def add2_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: !add2 https://t.me/your_channel")
        return

    set_config("link2", value)
    await message.reply("Channel 2 link updated.")


@dp.message(F.text.regexp(r"^!addmsg(\s+.+)?$"))
async def addmsg_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: !addmsg your start message here")
        return

    set_config("start_message", value)
    await message.reply("Start message updated.")


@dp.message(F.text.regexp(r"^!broadcast(\s+.+)?$"))
async def broadcast_handler(message: Message) -> None:
    if not is_admin(message):
        return

    broadcast_text = extract_value(message.text or "")
    if not broadcast_text:
        await message.reply("Use: !broadcast your message")
        return

    user_ids = get_all_user_ids()
    if not user_ids:
        await message.reply("No users saved yet.")
        return

    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, broadcast_text)
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Broadcast failed for user_id=%s", user_id)

    await message.reply(f"Broadcast complete.\nSent: {sent}\nFailed: {failed}")


@dp.message(Command("help"))
@dp.message(F.text.regexp(r"^!help$"))
async def help_handler(message: Message) -> None:
    if not is_admin(message):
        return

    await message.reply(
        "Admin commands:\n"
        "!help\n"
        "!add1 <link>\n"
        "!add2 <link>\n"
        "!addmsg <message>\n"
        "!broadcast <message>"
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global polling_task

    init_db()
    polling_task = asyncio.create_task(dp.start_polling(bot))
    logger.info("Bot polling started")

    try:
        yield
    finally:
        if polling_task:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        logger.info("Bot polling stopped")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "telegram-channel-link-bot",
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "healthy"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=PORT)
