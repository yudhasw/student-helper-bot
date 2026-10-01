"""Entry point FastAPI: wiring webhook Telegram, endpoint cron, dan lifecycle scheduler lokal.
Logika perintah bot ada di modul handlers_*; import di bawah mendaftarkan semua handler-nya."""

from contextlib import asynccontextmanager
from datetime import datetime

import telebot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Header, HTTPException, Request

from bot_instance import BOT_COMMANDS, WIB, bot, logger
from config import (
    CRON_SECRET,
    DIGEST_HOUR_WIB,
    DIGEST_MINUTE_WIB,
    ENABLE_LOCAL_SCHEDULER,
    TELEGRAM_WEBHOOK_SECRET,
)
from scheduler_jobs import send_daily_digest, send_due_reminders

# Import handler modules untuk efek sampingnya: mendaftarkan @bot.message_handler /
# @bot.callback_query_handler. Urutan import = urutan prioritas handler (yang filter-nya
# cocok duluan yang jalan, lihat _run_middlewares_and_handlers di pyTelegramBotAPI).
# Semua command spesifik (/task, /list, dst, termasuk /start & /versi di handlers_misc)
# harus terdaftar duluan, baru handlers_edit (filter "ada pending edit?" -- bisa
# nangkep teks apapun kalau didaftarkan kedahuluan), dan handlers_fallback paling
# akhir karena filter-nya selalu True (fallback "perintah tak dikenal").
import handlers_list  # noqa: F401
import handlers_task  # noqa: F401
import handlers_manage  # noqa: F401
import handlers_misc  # noqa: F401
import handlers_edit  # noqa: F401
import handlers_fallback  # noqa: F401

scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_my_commands(BOT_COMMANDS)

    if ENABLE_LOCAL_SCHEDULER:
        scheduler.add_job(
            send_daily_digest,
            "cron",
            hour=DIGEST_HOUR_WIB,
            minute=DIGEST_MINUTE_WIB,
            id="daily_digest",
        )
        scheduler.add_job(
            send_due_reminders,
            "interval",
            minutes=15,
            id="due_reminders",
        )
        scheduler.start()
        logger.info(
            "Local scheduler aktif: digest pagi jam %02d:%02d WIB",
            DIGEST_HOUR_WIB,
            DIGEST_MINUTE_WIB,
        )

    yield

    if ENABLE_LOCAL_SCHEDULER:
        scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"status": "Bot Helper berjalan!"}


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid secret token")

    data = await request.json()
    update = telebot.types.Update.de_json(data)
    await bot.process_new_updates([update])

    return {"status": "ok"}


@app.api_route("/internal/tick", methods=["GET", "POST"])
async def tick(authorization: str | None = Header(default=None)):
    """Dipanggil berkala (mis. cron-job.org tiap 15 menit) untuk digest & reminder."""
    if authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=403, detail="invalid cron secret")

    now = datetime.now(WIB)
    notified_chats = 0
    if now.hour == DIGEST_HOUR_WIB and now.minute < 15:
        notified_chats = await send_daily_digest()

    reminders_sent = await send_due_reminders()

    return {
        "checked": True,
        "notified_chats": notified_chats,
        "reminders_sent": reminders_sent,
    }
