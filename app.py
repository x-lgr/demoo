import asyncio
import json
import logging
import os
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
CONFIG_PATH = BASE_DIR / "config.json"
USERS_PATH = BASE_DIR / "users.json"

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


def write_json(path: Path, data: dict | list) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        write_json(path, default)
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in %s, resetting file", path.name)
        write_json(path, default)
        return default


def init_storage() -> None:
    defaults = {
        "link1": "https://t.me/example_channel_1",
        "link2": "https://t.me/example_channel_2",
        "start_message": (
            "Welcome!\n\nNeeche diye gaye buttons se channels join kar lo."
        ),
    }
    config_data = load_json(CONFIG_PATH, defaults.copy())
    updated = False
    for key, value in defaults.items():
        if key not in config_data:
            config_data[key] = value
            updated = True
    if updated:
        write_json(CONFIG_PATH, config_data)

    load_json(USERS_PATH, [])


def get_config(key: str, fallback: str = "") -> str:
    config_data = load_json(CONFIG_PATH, {})
    return str(config_data.get(key, fallback))


def set_config(key: str, value: str) -> None:
    config_data = load_json(CONFIG_PATH, {})
    config_data[key] = value
    write_json(CONFIG_PATH, config_data)


def upsert_user(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False

    users_data = load_json(USERS_PATH, [])
    user_id = int(user.id)
    existing_index = next(
        (index for index, item in enumerate(users_data) if item["user_id"] == user_id),
        None,
    )
    user_record = {
        "user_id": user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

    if existing_index is None:
        users_data.append(user_record)
        write_json(USERS_PATH, users_data)
        return True

    users_data[existing_index] = user_record
    write_json(USERS_PATH, users_data)
    return False


def get_all_user_ids() -> list[int]:
    users_data = load_json(USERS_PATH, [])
    return [int(item["user_id"]) for item in users_data]


def get_user_count() -> int:
    users_data = load_json(USERS_PATH, [])
    return len(users_data)


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


async def send_json_backup(caption: str) -> None:
    try:
        if USERS_PATH.exists():
            await bot.send_document(
                ADMIN_ID,
                FSInputFile(USERS_PATH),
                caption=caption,
            )
        if CONFIG_PATH.exists():
            await bot.send_document(
                ADMIN_ID,
                FSInputFile(CONFIG_PATH),
                caption="Current config backup.",
            )
    except Exception:
        logger.exception("Failed to send JSON backup to admin")


@dp.message(CommandStart())
@dp.message(F.text.regexp(r"(?i)^start$"))
async def start_handler(message: Message) -> None:
    is_new_user = upsert_user(message)
    if is_new_user:
        await notify_admin_new_user(message)
        total_users = get_user_count()
        if total_users % 10 == 0:
            await send_json_backup(
                f"JSON backup after {total_users} total users."
            )

    start_message = get_config("start_message")
    await message.answer(start_message, reply_markup=build_start_keyboard())


@dp.message(F.text.regexp(r"^!add1(\s+.+)?$"))
async def add1_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: <code>!add1 https://t.me/your_channel</code>")
        return

    set_config("link1", value)
    await message.reply("Channel 1 link updated.")


@dp.message(F.text.regexp(r"^!add2(\s+.+)?$"))
async def add2_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: <code>!add2 https://t.me/your_channel</code>")
        return

    set_config("link2", value)
    await message.reply("Channel 2 link updated.")


@dp.message(F.text.regexp(r"^!addmsg(\s+.+)?$"))
async def addmsg_handler(message: Message) -> None:
    if not is_admin(message):
        return

    value = extract_value(message.text or "")
    if not value:
        await message.reply("Use: <code>!addmsg your start message here</code>")
        return

    set_config("start_message", value)
    await message.reply("Start message updated.")


@dp.message(F.text.regexp(r"^!broadcast(\s+.+)?$"))
async def broadcast_handler(message: Message) -> None:
    if not is_admin(message):
        return

    broadcast_text = extract_value(message.text or "")
    if not broadcast_text:
        await message.reply("Use: <code>!broadcast your message</code>")
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
        "<code>!help</code>\n"
        "<code>!add1 https://t.me/your_channel</code>\n"
        "<code>!add2 https://t.me/your_channel</code>\n"
        "<code>!addmsg your start message here</code>\n"
        "<code>!broadcast your message</code>"
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global polling_task

    init_storage()
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
