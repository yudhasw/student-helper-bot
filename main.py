import calendar as calendar_module
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Header, HTTPException, Request
from supabase import Client, create_client
from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    CRON_SECRET,
    DIGEST_HOUR_WIB,
    DIGEST_MINUTE_WIB,
    ENABLE_LOCAL_SCHEDULER,
    SUPABASE_KEY,
    SUPABASE_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WEBHOOK_SECRET,
)

logger = logging.getLogger("student_helper.scheduler")

BOT_COMMANDS = [
    BotCommand("start", "Mulai pakai bot"),
    BotCommand("help", "Lihat daftar perintah"),
    BotCommand("task", "Tambah tugas: /task <nama> (pilih tanggal di kalender)"),
    BotCommand("list", "Lihat tugas: /list, /list today, /list week, /list month"),
    BotCommand("today", "Lihat tugas dengan deadline hari ini"),
    BotCommand("done", "Tandai tugas selesai: /done <nomor>"),
    BotCommand("del", "Hapus tugas: /del <nomor>"),
]

HELP_TEXT = "Daftar perintah:\n" + "\n".join(
    f"/{c.command} - {c.description}" for c in BOT_COMMANDS
)


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
bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

WIB = ZoneInfo("Asia/Jakarta")


def today_str() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


NAMA_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def build_calendar_markup(year: int, month: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=7)

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)
    nama_bulan = calendar_module.month_name[month]

    markup.row(
        InlineKeyboardButton("<", callback_data=f"cal|nav|{prev_year}-{prev_month:02d}"),
        InlineKeyboardButton(f"{nama_bulan} {year}", callback_data="cal|ignore"),
        InlineKeyboardButton(">", callback_data=f"cal|nav|{next_year}-{next_month:02d}"),
    )
    markup.row(*[InlineKeyboardButton(h, callback_data="cal|ignore") for h in NAMA_HARI])

    for week in calendar_module.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal|ignore"))
            else:
                tanggal = f"{year:04d}-{month:02d}-{day:02d}"
                row.append(InlineKeyboardButton(str(day), callback_data=f"cal|pick|{tanggal}"))
        markup.row(*row)

    markup.row(InlineKeyboardButton("Tanpa deadline", callback_data="cal|skip"))
    return markup


@app.get("/")
def read_root():
    return {"status": "Bot Helper berjalan!"}


@bot.message_handler(commands=["start", "help"])
async def handle_start(message):
    await bot.reply_to(message, HELP_TEXT)


SCOPE_JUDUL = {
    None: "tugas yang belum selesai",
    "today": "tugas hari ini",
    "week": "tugas minggu ini",
    "month": "tugas bulan ini",
}


def _date_range_for_scope(scope: str, now: datetime) -> tuple[str, str]:
    if scope == "today":
        d = now.strftime("%Y-%m-%d")
        return d, d
    if scope == "week":
        start = now - timedelta(days=now.weekday())  # Senin
        end = start + timedelta(days=6)  # Minggu
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if scope == "month":
        start = now.replace(day=1)
        last_day = calendar_module.monthrange(now.year, now.month)[1]
        end = now.replace(day=last_day)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    raise ValueError(f"scope tidak dikenal: {scope}")


def _fetch_tasks(chat_id: int, scope: str | None) -> list[dict]:
    query = (
        supabase.table("study_tasks")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("is_completed", False)
    )

    if scope is None:
        query = query.order("created_at")
    else:
        start, end = _date_range_for_scope(scope, datetime.now(WIB))
        query = query.gte("deadline", start).lte("deadline", end).order("deadline")

    return query.execute().data


def _format_task_list(daftar_tugas: list[dict], scope: str | None) -> str:
    if not daftar_tugas:
        return f"Bebas tugas! Tidak ada {SCOPE_JUDUL[scope]}."

    reply_text = f"Ini {SCOPE_JUDUL[scope]}:\n"
    for i, tugas in enumerate(daftar_tugas, start=1):
        if scope == "today":
            reply_text += f"{i}. {tugas['task_name']}\n"
        else:
            deadline = tugas["deadline"] or "-"
            reply_text += f"{i}. {tugas['task_name']} - {deadline}\n"

    return reply_text


@bot.message_handler(commands=["today"])
async def handle_today(message):
    daftar_tugas = _fetch_tasks(message.chat.id, "today")
    await bot.reply_to(message, _format_task_list(daftar_tugas, "today"))


@bot.message_handler(commands=["list"])
async def handle_list(message):
    arg = message.text[len("/list") :].strip().lower()
    scope = {"": None, "today": "today", "week": "week", "month": "month"}.get(arg)

    if scope is None and arg != "":
        await bot.reply_to(
            message, "Format salah. Gunakan: /list, /list today, /list week, atau /list month"
        )
        return

    daftar_tugas = _fetch_tasks(message.chat.id, scope)
    await bot.reply_to(message, _format_task_list(daftar_tugas, scope))


def _save_task_text(task_name: str, deadline_iso: str | None) -> str:
    if deadline_iso:
        return f"Sukses! Tugas '{task_name}' dengan deadline {deadline_iso} berhasil disimpan."
    return f"Sukses! Tugas '{task_name}' (tanpa deadline) berhasil disimpan."


@bot.message_handler(commands=["task"])
async def handle_task(message):
    chat_id = message.chat.id
    raw_input = message.text[len("/task") :].strip()

    if not raw_input:
        await bot.reply_to(
            message,
            "Format salah. Contoh: /task Makalah AI (lalu pilih tanggal di kalender)\n"
            "atau langsung: /task Makalah AI | 2026-09-25",
        )
        return

    if "|" in raw_input:
        parts = raw_input.split("|")
        task_name = parts[0].strip()
        deadline_iso = parts[1].strip()

        supabase.table("study_tasks").insert(
            {"chat_id": chat_id, "task_name": task_name, "deadline": deadline_iso}
        ).execute()

        await bot.reply_to(message, _save_task_text(task_name, deadline_iso))
        return

    task_name = raw_input
    supabase.table("pending_tasks").upsert(
        {"chat_id": chat_id, "task_name": task_name}, on_conflict="chat_id"
    ).execute()

    now = datetime.now(WIB)
    await bot.reply_to(
        message,
        f"Pilih deadline untuk '{task_name}':",
        reply_markup=build_calendar_markup(now.year, now.month),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("cal|"))
async def handle_calendar_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action == "ignore":
        await bot.answer_callback_query(call.id)
        return

    if action == "nav":
        year, month = map(int, rest[0].split("-"))
        await bot.edit_message_reply_markup(
            chat_id,
            call.message.message_id,
            reply_markup=build_calendar_markup(year, month),
        )
        await bot.answer_callback_query(call.id)
        return

    pending = (
        supabase.table("pending_tasks").select("task_name").eq("chat_id", chat_id).execute()
    )
    if not pending.data:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    task_name = pending.data[0]["task_name"]
    deadline_iso = None if action == "skip" else rest[0]

    supabase.table("study_tasks").insert(
        {"chat_id": chat_id, "task_name": task_name, "deadline": deadline_iso}
    ).execute()
    supabase.table("pending_tasks").delete().eq("chat_id", chat_id).execute()

    await bot.edit_message_text(
        _save_task_text(task_name, deadline_iso), chat_id, call.message.message_id
    )
    await bot.answer_callback_query(call.id)


async def _find_task_by_number(chat_id: int, nomor_tugas: int):
    response = (
        supabase.table("study_tasks")
        .select("id, created_at, task_name")
        .eq("chat_id", chat_id)
        .eq("is_completed", False)
        .order("created_at")
        .execute()
    )
    daftar_tugas = response.data

    if nomor_tugas < 1 or nomor_tugas > len(daftar_tugas):
        return None

    return daftar_tugas[nomor_tugas - 1]


@bot.message_handler(commands=["done"])
async def handle_done(message):
    chat_id = message.chat.id
    raw_input = message.text[len("/done") :].strip()

    if not raw_input.isdigit():
        await bot.reply_to(message, "Format salah. Contoh: /done 1")
        return

    nomor_tugas = int(raw_input)
    tugas_terpilih = await _find_task_by_number(chat_id, nomor_tugas)

    if tugas_terpilih is None:
        await bot.reply_to(
            message, f"Tugas nomor {nomor_tugas} tidak ditemukan. Cek lagi dengan /list."
        )
        return

    supabase.table("study_tasks").update({"is_completed": True}).eq(
        "id", tugas_terpilih["id"]
    ).execute()

    await bot.reply_to(
        message, f"🎉 Mantap! Tugas '{tugas_terpilih['task_name']}' berhasil diselesaikan."
    )


@bot.message_handler(commands=["del"])
async def handle_del(message):
    chat_id = message.chat.id
    raw_input = message.text[len("/del") :].strip()

    if not raw_input.isdigit():
        await bot.reply_to(message, "Format salah. Contoh: /del 1")
        return

    nomor_tugas = int(raw_input)
    tugas_terpilih = await _find_task_by_number(chat_id, nomor_tugas)

    if tugas_terpilih is None:
        await bot.reply_to(
            message, f"Tugas nomor {nomor_tugas} tidak ditemukan. Cek lagi dengan /list."
        )
        return

    supabase.table("study_tasks").delete().eq("id", tugas_terpilih["id"]).execute()

    await bot.reply_to(message, f"Tugas '{tugas_terpilih['task_name']}' berhasil dihapus.")


@bot.message_handler(func=lambda message: True)
async def handle_unknown(message):
    await bot.reply_to(message, f"Perintah: {message.text} tidak ditemukan")


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


async def send_daily_digest() -> int:
    """Kirim digest tugas hari ini ke semua chat yang punya tugas jatuh tempo."""
    response = (
        supabase.table("study_tasks")
        .select("chat_id, task_name")
        .eq("deadline", today_str())
        .eq("is_completed", False)
        .execute()
    )

    tugas_per_chat: dict[int, list[str]] = {}
    for tugas in response.data:
        tugas_per_chat.setdefault(tugas["chat_id"], []).append(tugas["task_name"])

    for chat_id, daftar_nama in tugas_per_chat.items():
        lines = "\n".join(f"{i}. {nama}" for i, nama in enumerate(daftar_nama, start=1))
        reply_text = f"📅 Reminder tugas hari ini:\n{lines}"
        try:
            await bot.send_message(chat_id, reply_text)
        except Exception:
            logger.exception("Gagal mengirim digest ke chat_id=%s", chat_id)

    logger.info("Digest terkirim ke %d chat", len(tugas_per_chat))
    return len(tugas_per_chat)


@app.api_route("/internal/tick", methods=["GET", "POST"])
async def tick(authorization: str | None = Header(default=None)):
    """Dipanggil oleh Vercel Cron / cron eksternal untuk mengirim digest harian."""
    if authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=403, detail="invalid cron secret")

    notified_chats = await send_daily_digest()
    return {"checked": True, "notified_chats": notified_chats}


def countTugas(chat_id):
    response = (
        supabase.table("study_tasks")
        .select("*", count="exact")
        .eq("chat_id", chat_id)
        .eq("is_completed", False)
        .execute()
    )
    return response.count
