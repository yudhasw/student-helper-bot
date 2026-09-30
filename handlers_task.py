"""Alur pembuatan tugas via /task: pilih tanggal (cal|) -> pilih jam deadline (dtime|)
-> pilih reminder (rem|) -> tersimpan ke study_tasks."""

from datetime import datetime

from bot_instance import WIB, bot, supabase
from formatting import save_task_text
from keyboards import (
    build_calendar_markup,
    build_deadline_time_markup,
    build_minute_markup,
    build_reminder_markup,
    build_time_markup,
)
from tasks_repo import compute_remind_at_offset, finalize_task


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

        await bot.reply_to(message, save_task_text(task_name, deadline_iso))
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
        task_name = finalize_task(chat_id, None)
        if task_name is None:
            await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
            return
        await bot.edit_message_text(
            save_task_text(task_name, None), chat_id, call.message.message_id
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
        f"Deadline: {deadline_iso}. Jam berapa deadline-nya?\n"
        "(format 24 jam: 07 = jam 7 pagi, 19 = jam 7 malam)",
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
        remind_at_iso = compute_remind_at_offset(deadline_iso, deadline_time, int(rest[0]), 0)
    elif action == "hour":
        remind_at_iso = compute_remind_at_offset(
            deadline_iso, deadline_time, int(rest[0]), int(rest[1])
        )
    else:
        await bot.answer_callback_query(call.id)
        return

    task_name = finalize_task(chat_id, deadline_iso, deadline_time, remind_at_iso)
    if task_name is None:
        await bot.answer_callback_query(call.id, "Sesi kedaluwarsa, kirim /task lagi.")
        return

    await bot.edit_message_text(
        save_task_text(task_name, deadline_iso, deadline_time, remind_at_iso),
        chat_id,
        call.message.message_id,
    )
    await bot.answer_callback_query(call.id)
