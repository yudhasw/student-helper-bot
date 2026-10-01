import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from supabase import Client, create_client
from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand

from config import SUPABASE_KEY, SUPABASE_URL, TELEGRAM_BOT_TOKEN

logger = logging.getLogger("student_helper.scheduler")

WIB = ZoneInfo("Asia/Jakarta")

with open(Path(__file__).parent / "VERSION") as _f:
    APP_VERSION = _f.read().strip()

bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BOT_COMMANDS = [
    BotCommand("start", "Mulai pakai bot"),
    BotCommand("help", "Lihat daftar perintah"),
    BotCommand("task", "Tambah tugas: /task <nama> (pilih tanggal di kalender)"),
    BotCommand("list", "Lihat tugas: /list, /list today, /list week, /list month"),
    BotCommand("today", "Lihat tugas dengan deadline hari ini"),
    BotCommand("overdue", "Lihat tugas yang sudah lewat deadline"),
    BotCommand("done", "Tandai tugas selesai (pilih dari daftar)"),
    BotCommand("del", "Hapus tugas (pilih dari daftar)"),
    BotCommand("edit", "Ubah nama/deadline/catatan tugas (pilih dari daftar)"),
    BotCommand("versi", "Lihat versi bot saat ini"),
]

HELP_TEXT = "Daftar perintah:\n" + "\n".join(
    f"/{c.command} - {c.description}" for c in BOT_COMMANDS
)
