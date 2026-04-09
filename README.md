# Telegram Channel Link Bot

Simple Telegram bot with:

- `/start` or `start`
- Admin-only `!add1`
- Admin-only `!add2`
- Admin-only `!addmsg`
- Admin-only `!broadcast`
- Admin-only `!help`
- User backup notification in admin chat
- Automatic SQLite DB backup to admin after every 10 new users
- Render-friendly web service with health endpoint

## Setup

1. Create a Telegram bot with BotFather and get the token.
2. Copy `.env.example` to `.env`.
3. Fill:

```env
BOT_TOKEN=your_bot_token
ADMIN_ID=your_telegram_user_id
PORT=10000
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Run:

```bash
python app.py
```

## Python Version

Use Python `3.11`. This project is pinned with `runtime.txt` for Render compatibility.

## Commands

User:

- `/start`
- `start`

Admin only:

- `!help`
- `!add1 https://t.me/your_channel_1`
- `!add2 https://t.me/your_channel_2`
- `!addmsg Welcome message here`
- `!broadcast Hello everyone`

## Render

- Create a new Web Service.
- Use the included `render.yaml` or set:
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `python app.py`
- Add env vars:
  - `BOT_TOKEN`
  - `ADMIN_ID`
  - `PORT=10000`

## Notes

- Links and start message are stored in `bot_data.db`.
- Every new user is backed up to the admin chat.
- Every 10 total users, the full `bot_data.db` file is sent to the admin chat.
- If Render restarts and local DB clears, admin chat still keeps user backup messages.
