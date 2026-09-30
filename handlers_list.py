"""Command untuk menampilkan tugas: /today, /overdue, /list [today|week|month]."""

from bot_instance import bot
from formatting import format_task_list
from tasks_repo import fetch_tasks

LIST_SCOPES = {"": None, "today": "today", "week": "week", "month": "month"}


@bot.message_handler(commands=["today"])
async def handle_today(message):
    daftar_tugas = fetch_tasks(message.chat.id, "today")
    await bot.reply_to(message, format_task_list(daftar_tugas, "today"))


@bot.message_handler(commands=["overdue"])
async def handle_overdue(message):
    daftar_tugas = fetch_tasks(message.chat.id, "overdue")
    await bot.reply_to(message, format_task_list(daftar_tugas, "overdue"))


@bot.message_handler(commands=["list"])
async def handle_list(message):
    arg = message.text[len("/list") :].strip().lower()

    if arg not in LIST_SCOPES:
        await bot.reply_to(
            message, "Format salah. Gunakan: /list, /list today, /list week, atau /list month"
        )
        return

    scope = LIST_SCOPES[arg]
    daftar_tugas = fetch_tasks(message.chat.id, scope)
    await bot.reply_to(message, format_task_list(daftar_tugas, scope))
