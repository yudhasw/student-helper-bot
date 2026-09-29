import calendar as calendar_module
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
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

with open(Path(__file__).parent / "VERSION") as _f:
    APP_VERSION = _f.read().strip()

BOT_COMMANDS = [
    BotCommand("start", "Mulai pakai bot"),
    BotCommand("help", "Lihat daftar perintah"),
    BotCommand("task", "Tambah tugas: /task <nama> (pilih tanggal di kalender)"),
    BotCommand("list", "Lihat tugas: /list, /list today, /list week, /list month"),
    BotCommand("today", "Lihat tugas dengan deadline hari ini"),
    BotCommand("overdue", "Lihat tugas yang sudah lewat deadline"),
    BotCommand("done", "Tandai tugas selesai (pilih dari daftar)"),
    BotCommand("del", "Hapus tugas (pilih dari daftar)"),
    BotCommand("versi", "Lihat versi bot saat ini"),
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


REMINDER_PRESETS = [
    ("1 jam sebelum", 1),
    ("3 jam sebelum", 3),
    ("1 hari sebelum", 24),
]


def build_reminder_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for label, hours in REMINDER_PRESETS:
        markup.add(InlineKeyboardButton(label, callback_data=f"rem|preset|{hours}"))
    markup.add(InlineKeyboardButton("Durasi custom sebelum deadline", callback_data="rem|customoffset"))
    markup.add(InlineKeyboardButton("Tanpa reminder khusus", callback_data="rem|none"))
    return markup


def build_time_markup(prefix: str) -> InlineKeyboardMarkup:
    """Grid jam 00-23. `prefix` menentukan tujuan callback (mis. 'dtime' atau 'rem')."""
    markup = InlineKeyboardMarkup(row_width=6)
    buttons = [
        InlineKeyboardButton(f"{h:02d}", callback_data=f"{prefix}|pickhour|{h}") for h in range(24)
    ]
    for i in range(0, 24, 6):
        markup.row(*buttons[i : i + 6])
    return markup


def build_deadline_time_markup() -> InlineKeyboardMarkup:
    markup = build_time_markup("dtime")
    markup.row(InlineKeyboardButton("Tidak tahu jam pastinya", callback_data="dtime|skip"))
    return markup


MINUTE_OPTIONS = [0, 15, 30, 45]


def build_minute_markup(prefix: str, hour: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=4)
    markup.row(
        *[
            InlineKeyboardButton(f"{hour:02d}:{m:02d}", callback_data=f"{prefix}|hour|{hour}|{m}")
            for m in MINUTE_OPTIONS
        ]
    )
    return markup


@app.get("/")
def read_root():
    return {"status": "Bot Helper berjalan!"}


@bot.message_handler(commands=["start", "help"])
async def handle_start(message):
    await bot.reply_to(message, HELP_TEXT)


@bot.message_handler(commands=["versi"])
async def handle_versi(message):
    await bot.reply_to(message, f"Versi bot: {APP_VERSION}")


SCOPE_JUDUL = {
    None: "tugas yang belum selesai",
    "today": "tugas hari ini",
    "week": "tugas minggu ini",
    "month": "tugas bulan ini",
    "overdue": "tugas yang sudah lewat deadline",
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

    if scope == "overdue":
        query = query.lt("deadline", today_str()).not_.is_("deadline", "null")
    elif scope is not None:
        start, end = _date_range_for_scope(scope, datetime.now(WIB))
        query = query.gte("deadline", start).lte("deadline", end)

    query = query.order("deadline", nullsfirst=False)

    return query.execute().data


def _is_overdue(deadline: str | None) -> bool:
    return deadline is not None and deadline < today_str()


def _format_deadline_short(deadline: str | None, deadline_time: str | None) -> str:
    if not deadline:
        return "-"
    short = deadline[5:]  # "YYYY-MM-DD" -> "MM-DD"
    return f"{short} {deadline_time}" if deadline_time else short


def _format_task_line(i: int, tugas: dict, scope: str | None) -> str:
    if scope == "today":
        return f"{i}. {tugas['task_name']}"
    deadline = _format_deadline_short(tugas["deadline"], tugas.get("deadline_time"))
    return f"{i}. {tugas['task_name']} - {deadline}"


def _format_task_list(daftar_tugas: list[dict], scope: str | None) -> str:
    if not daftar_tugas:
        return f"Bebas tugas! Tidak ada {SCOPE_JUDUL[scope]}."

    if scope == "overdue":
        lines = [f"Ini {SCOPE_JUDUL[scope]}:"]
        lines += [_format_task_line(i, t, scope) for i, t in enumerate(daftar_tugas, start=1)]
        return "\n".join(lines)

    non_overdue = [t for t in daftar_tugas if not _is_overdue(t["deadline"])]
    overdue = [t for t in daftar_tugas if _is_overdue(t["deadline"])]

    lines: list[str] = []
    if non_overdue:
        lines.append(f"Ini {SCOPE_JUDUL[scope]}:")
        lines += [_format_task_line(i, t, scope) for i, t in enumerate(non_overdue, start=1)]

    if overdue:
        if lines:
            lines.append("")
        lines.append("⚠️ Overdue:")
        lines += [_format_task_line(i, t, scope) for i, t in enumerate(overdue, start=1)]

    return "\n".join(lines)


@bot.message_handler(commands=["today"])
async def handle_today(message):
    daftar_tugas = _fetch_tasks(message.chat.id, "today")
    await bot.reply_to(message, _format_task_list(daftar_tugas, "today"))


@bot.message_handler(commands=["overdue"])
async def handle_overdue(message):
    daftar_tugas = _fetch_tasks(message.chat.id, "overdue")
    await bot.reply_to(message, _format_task_list(daftar_tugas, "overdue"))


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


def _save_task_text(
    task_name: str,
    deadline_iso: str | None,
    deadline_time: str | None = None,
    remind_at_iso: str | None = None,
) -> str:
    if deadline_iso:
        deadline_display = f"{deadline_iso} {deadline_time}" if deadline_time else deadline_iso
        text = f"Sukses! Tugas '{task_name}' dengan deadline {deadline_display} berhasil disimpan."
    else:
        text = f"Sukses! Tugas '{task_name}' (tanpa deadline) berhasil disimpan."

    if remind_at_iso:
        remind_wib = datetime.fromisoformat(remind_at_iso).astimezone(WIB)
        text += f"\n⏰ Reminder diatur: {remind_wib.strftime('%Y-%m-%d %H:%M')} WIB"

    return text


def _deadline_datetime(deadline_date: str, deadline_time: str | None) -> datetime:
    # Kalau jam deadline tidak diketahui, anggap akhir hari (23:59) sebagai fallback.
    hour, minute = map(int, (deadline_time or "23:59").split(":"))
    return datetime.strptime(deadline_date, "%Y-%m-%d").replace(
        hour=hour, minute=minute, tzinfo=WIB
    )


def _compute_remind_at_offset(
    deadline_date: str, deadline_time: str | None, hours_before: int, minutes_before: int
) -> str:
    deadline_dt = _deadline_datetime(deadline_date, deadline_time)
    remind_at = deadline_dt - timedelta(hours=hours_before, minutes=minutes_before)
    return remind_at.isoformat()


def _finalize_task(
    chat_id: int,
    deadline_iso: str | None,
    deadline_time: str | None = None,
    remind_at_iso: str | None = None,
) -> str | None:
    pending = (
        supabase.table("pending_tasks").select("task_name").eq("chat_id", chat_id).execute()
    )
    if not pending.data:
        return None

    task_name = pending.data[0]["task_name"]
    supabase.table("study_tasks").insert(
        {
            "chat_id": chat_id,
            "task_name": task_name,
            "deadline": deadline_iso,
            "deadline_time": deadline_time,
            "remind_at": remind_at_iso,
        }
    ).execute()
    supabase.table("pending_tasks").delete().eq("chat_id", chat_id).execute()
    return task_name


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

    if action == "skip":
        task_name = _finalize_task(chat_id, None)
        if task_name is None:
            await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
            return
        await bot.edit_message_text(
            _save_task_text(task_name, None), chat_id, call.message.message_id
        )
        await bot.answer_callback_query(call.id)
        return

    # action == "pick": simpan tanggal ke pending, lanjut ke pemilihan jam deadline.
    deadline_iso = rest[0]
    result = (
        supabase.table("pending_tasks")
        .update({"deadline": deadline_iso})
        .eq("chat_id", chat_id)
        .execute()
    )
    if not result.data:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    await bot.edit_message_text(
        f"Deadline: {deadline_iso}. Jam berapa deadline-nya?",
        chat_id,
        call.message.message_id,
        reply_markup=build_deadline_time_markup(),
    )
    await bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dtime|"))
async def handle_deadline_time_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action == "pickhour":
        hour = int(rest[0])
        await bot.edit_message_reply_markup(
            chat_id, call.message.message_id, reply_markup=build_minute_markup("dtime", hour)
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "hour":
        deadline_time = f"{int(rest[0]):02d}:{int(rest[1]):02d}"
    elif action == "skip":
        deadline_time = None
    else:
        await bot.answer_callback_query(call.id)
        return

    result = (
        supabase.table("pending_tasks")
        .update({"deadline_time": deadline_time})
        .eq("chat_id", chat_id)
        .execute()
    )
    if not result.data:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    deadline_iso = result.data[0]["deadline"]
    deadline_display = f"{deadline_iso} {deadline_time}" if deadline_time else deadline_iso
    await bot.edit_message_text(
        f"Deadline: {deadline_display}. Mau diingatkan berapa lama sebelumnya?",
        chat_id,
        call.message.message_id,
        reply_markup=build_reminder_markup(),
    )
    await bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("rem|"))
async def handle_reminder_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action == "customoffset":
        await bot.edit_message_reply_markup(
            chat_id, call.message.message_id, reply_markup=build_time_markup("rem")
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "pickhour":
        hour = int(rest[0])
        await bot.edit_message_reply_markup(
            chat_id, call.message.message_id, reply_markup=build_minute_markup("rem", hour)
        )
        await bot.answer_callback_query(call.id)
        return

    pending = (
        supabase.table("pending_tasks")
        .select("task_name, deadline, deadline_time")
        .eq("chat_id", chat_id)
        .execute()
    )
    if not pending.data:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    deadline_iso = pending.data[0]["deadline"]
    deadline_time = pending.data[0]["deadline_time"]

    if action == "none":
        remind_at_iso = None
    elif action == "preset":
        remind_at_iso = _compute_remind_at_offset(deadline_iso, deadline_time, int(rest[0]), 0)
    elif action == "hour":
        remind_at_iso = _compute_remind_at_offset(
            deadline_iso, deadline_time, int(rest[0]), int(rest[1])
        )
    else:
        await bot.answer_callback_query(call.id)
        return

    task_name = _finalize_task(chat_id, deadline_iso, deadline_time, remind_at_iso)
    if task_name is None:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    await bot.edit_message_text(
        _save_task_text(task_name, deadline_iso, deadline_time, remind_at_iso),
        chat_id,
        call.message.message_id,
    )
    await bot.answer_callback_query(call.id)


def _short_task_label(tugas: dict) -> str:
    name = tugas["task_name"]
    deadline = tugas["deadline"]
    if deadline:
        label = f"{name} ({deadline[5:]}{' ' + tugas['deadline_time'] if tugas.get('deadline_time') else ''})"
    else:
        label = name
    return label if len(label) <= 60 else label[:57] + "..."


def build_task_picker_markup(daftar_tugas: list[dict], prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for tugas in daftar_tugas:
        markup.add(
            InlineKeyboardButton(
                _short_task_label(tugas), callback_data=f"{prefix}|pick|{tugas['id']}"
            )
        )
    return markup


@bot.message_handler(commands=["done"])
async def handle_done(message):
    chat_id = message.chat.id
    daftar_tugas = _fetch_tasks(chat_id, None)

    if not daftar_tugas:
        await bot.reply_to(message, "Tidak ada tugas yang bisa ditandai selesai.")
        return

    await bot.reply_to(
        message,
        "Pilih tugas yang mau ditandai selesai:",
        reply_markup=build_task_picker_markup(daftar_tugas, "done"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("done|"))
async def handle_done_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action != "pick":
        await bot.answer_callback_query(call.id)
        return

    task_id = int(rest[0])
    result = supabase.table("study_tasks").select("task_name").eq("id", task_id).execute()
    if not result.data:
        await bot.answer_callback_query(call.id, "Tugas tidak ditemukan, mungkin sudah dihapus.")
        return

    task_name = result.data[0]["task_name"]
    supabase.table("study_tasks").update({"is_completed": True}).eq("id", task_id).execute()

    await bot.edit_message_text(
        f"🎉 Mantap! Tugas '{task_name}' berhasil diselesaikan.", chat_id, call.message.message_id
    )
    await bot.answer_callback_query(call.id)


@bot.message_handler(commands=["del"])
async def handle_del(message):
    chat_id = message.chat.id
    daftar_tugas = _fetch_tasks(chat_id, None)

    if not daftar_tugas:
        await bot.reply_to(message, "Tidak ada tugas yang bisa dihapus.")
        return

    await bot.reply_to(
        message,
        "Pilih tugas yang mau dihapus:",
        reply_markup=build_task_picker_markup(daftar_tugas, "del"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("del|"))
async def handle_del_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action == "pick":
        task_id = int(rest[0])
        result = supabase.table("study_tasks").select("task_name").eq("id", task_id).execute()
        if not result.data:
            await bot.answer_callback_query(call.id, "Tugas tidak ditemukan, mungkin sudah dihapus.")
            return

        task_name = result.data[0]["task_name"]
        confirm_markup = InlineKeyboardMarkup(row_width=2)
        confirm_markup.row(
            InlineKeyboardButton("Ya, hapus", callback_data=f"del|confirm|{task_id}"),
            InlineKeyboardButton("Batal", callback_data="del|cancel"),
        )
        await bot.edit_message_text(
            f"Hapus tugas '{task_name}'?",
            chat_id,
            call.message.message_id,
            reply_markup=confirm_markup,
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "confirm":
        task_id = int(rest[0])
        result = supabase.table("study_tasks").select("task_name").eq("id", task_id).execute()
        task_name = result.data[0]["task_name"] if result.data else "tugas ini"
        supabase.table("study_tasks").delete().eq("id", task_id).execute()
        await bot.edit_message_text(
            f"Tugas '{task_name}' berhasil dihapus.", chat_id, call.message.message_id
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "cancel":
        await bot.edit_message_text("Dibatalkan.", chat_id, call.message.message_id)
        await bot.answer_callback_query(call.id)
        return

    await bot.answer_callback_query(call.id)


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


async def send_due_reminders() -> int:
    """Kirim reminder untuk tugas yang remind_at-nya sudah lewat dan belum dikirim."""
    now_utc = datetime.now(ZoneInfo("UTC")).isoformat()
    response = (
        supabase.table("study_tasks")
        .select("id, chat_id, task_name, deadline, deadline_time")
        .lte("remind_at", now_utc)
        .eq("reminder_sent", False)
        .eq("is_completed", False)
        .execute()
    )

    count = 0
    for tugas in response.data:
        if tugas["deadline"]:
            waktu = f" {tugas['deadline_time']}" if tugas.get("deadline_time") else ""
            deadline_text = f" (deadline: {tugas['deadline']}{waktu})"
        else:
            deadline_text = ""
        try:
            await bot.send_message(
                tugas["chat_id"], f"⏰ Pengingat: '{tugas['task_name']}'{deadline_text}"
            )
            supabase.table("study_tasks").update({"reminder_sent": True}).eq(
                "id", tugas["id"]
            ).execute()
            count += 1
        except Exception:
            logger.exception("Gagal mengirim reminder untuk task id=%s", tugas["id"])

    logger.info("Reminder terkirim ke %d tugas", count)
    return count


@app.api_route("/internal/tick", methods=["GET", "POST"])
async def tick(authorization: str | None = Header(default=None)):
    """Dipanggil berkala (mis. GitHub Actions tiap 15 menit) untuk digest & reminder."""
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


def countTugas(chat_id):
    response = (
        supabase.table("study_tasks")
        .select("*", count="exact")
        .eq("chat_id", chat_id)
        .eq("is_completed", False)
        .execute()
    )
    return response.count
