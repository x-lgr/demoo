import html
import json
import logging
import os
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()

if not BOT_TOKEN or not ADMIN_ID_RAW:
    raise RuntimeError("Missing BOT_TOKEN or ADMIN_ID")

ADMIN_ID = int(ADMIN_ID_RAW)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("channel-link-bot")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# In-memory storage for Vercel
users_db = {}
config_db = {
    "link1": "https://t.me/+jSGMUUU4cA1hZGZl",
    "link2": "https://t.me/+DBLkMK_hnWozZGY1",
    "start_message": "Welcome!\n\nNiche 2 Demo Channels Ka Link dia Hua H Join \nKrke Demo Dekh Lo then Buy Krne K Lie Msg \nKro:- @fuckuwhorebitch\n\nProof Channel Link - https://t.me/+NY1J78w08-k0Y2U1"
}

def get_config(key: str, fallback: str = "") -> str:
    return config_db.get(key, fallback)

def set_config(key: str, value: str) -> None:
    config_db[key] = value
    logger.info(f"Config updated: {key}")

def upsert_user(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False
    
    is_new = user.id not in users_db
    users_db[user.id] = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "joined_at": datetime.now().isoformat()
    }
    logger.info(f"User {'new' if is_new else 'existing'}: {user.id}")
    return is_new

def get_all_user_ids() -> list:
    return list(users_db.keys())

def get_user_count() -> int:
    return len(users_db)

def extract_value(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""

def is_admin(message: Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID

def build_start_keyboard() -> InlineKeyboardMarkup:
    link1 = get_config("link1")
    link2 = get_config("link2")
    buttons = [[
        InlineKeyboardButton(text="📢 Channel 1 Join", url=link1),
        InlineKeyboardButton(text="📢 Channel 2 Join", url=link2),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def notify_admin_new_user(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    
    username = f"@{user.username}" if user.username else "No username"
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    text = (
        f"<b>✅ Naya Londa Fas Gaya Hai!</b>\n"
        f"Name: {full_name or 'Unknown'}\n"
        f"Username: {username}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Total: {get_user_count()}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    try:
        is_new = upsert_user(message)
        if is_new:
            await notify_admin_new_user(message)
        
        start_message = get_config("start_message")
        await message.answer(start_message, reply_markup=build_start_keyboard())
        logger.info(f"Start OK for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Start error: {e}")
        await message.answer("❌ Error, try again")

@dp.message(F.text.startswith("!add1"))
async def add1_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    value = extract_value(message.text or "")
    if not value:
        await message.reply("Usage: <code>!add1 https://t.me/channel</code>")
        return
    
    set_config("link1", value)
    await message.reply("✅ Channel 1 updated!")

@dp.message(F.text.startswith("!add2"))
async def add2_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    value = extract_value(message.text or "")
    if not value:
        await message.reply("Usage: <code>!add2 https://t.me/channel</code>")
        return
    
    set_config("link2", value)
    await message.reply("✅ Channel 2 updated!")

@dp.message(F.text.startswith("!addmsg"))
async def addmsg_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    value = extract_value(message.text or "")
    if not value:
        await message.reply("Usage: <code>!addmsg Your message here</code>")
        return
    
    set_config("start_message", value)
    await message.reply(f"✅ Start message updated!\n\n{value}")

@dp.message(F.text == "!showmsg")
async def showmsg_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    msg = get_config("start_message")
    await message.reply(f"📝 Current message:\n\n{msg}")

@dp.message(F.text.startswith("!broadcast"))
async def broadcast_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    broadcast_text = extract_value(message.text or "")
    if not broadcast_text:
        await message.reply("Usage: <code>!broadcast Your message</code>")
        return
    
    user_ids = get_all_user_ids()
    if not user_ids:
        await message.reply("No users yet.")
        return
    
    await message.reply(f"📡 Broadcasting to {len(user_ids)} users...")
    
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, broadcast_text)
            sent += 1
        except Exception:
            failed += 1
    
    await message.reply(f"✅ Done!\nSent: {sent}\nFailed: {failed}")

@dp.message(F.text == "!stats")
async def stats_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    await message.reply(
        f"📊 Stats:\n"
        f"Users: {get_user_count()}\n"
        f"Channel 1: {get_config('link1')}\n"
        f"Channel 2: {get_config('link2')}"
    )

@dp.message(F.text == "!help")
async def help_handler(message: Message) -> None:
    if not is_admin(message):
        return
    
    await message.reply(
        "🤖 <b>Commands:</b>\n\n"
        "!add1 [link] - Update channel 1\n"
        "!add2 [link] - Update channel 2\n"
        "!addmsg [msg] - Update start message\n"
        "!showmsg - Show current message\n"
        "!broadcast [msg] - Send to all users\n"
        "!stats - Show statistics\n"
        "!help - This menu"
    )

# Catch-all handler for debugging
@dp.message()
async def catch_all(message: Message) -> None:
    logger.info(f"Received: {message.text}")
    await message.answer("✅ Bot is online! Send /start to begin.")

# FastAPI app
app = FastAPI()

@app.post(f"/webhook/{BOT_TOKEN}")
async def webhook(request: Request) -> JSONResponse:
    """Telegram webhook endpoint"""
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
        logger.info("Update processed successfully")
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "telegram-channel-link-bot",
        "users": get_user_count()
    })

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "healthy"})
