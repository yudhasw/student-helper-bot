"""Alur /edit: ubah nama, deadline, atau catatan tugas yang sudah ada.

Ubah nama & catatan butuh teks bebas, bukan tombol. AsyncTeleBot tidak punya
register_next_step_handler (dan Vercel serverless juga tidak bisa simpan state
in-memory antar request), jadi status "sedang nunggu teks apa" disimpan ke
tabel pending_edits dan ditangkap lewat message handler biasa, sama seperti
pending_tasks dipakai untuk alur /task multi-step.
"""

from datetime import datetime

from bot_instance import WIB, bot, supabase
from formatting import format_task_detail
from keyboards import build_calendar_markup, build_edit_menu_markup, build_task_picker_markup
from tasks_repo import (
    MAX_NOTES_LENGTH,
    clear_pending_edit,
    fetch_tasks,
    get_pending_edit,
    start_pending_edit,
)


@bot.message_handler(commands=["edit"])
async def handle_edit(message):
    chat_id = message.chat.id
    daftar_tugas = fetch_tasks(chat_id, None)

    if not daftar_tugas:
        await bot.reply_to(message, "Tidak ada tugas yang bisa diedit.")
        return

    await bot.reply_to(
        message,
        "Pilih tugas yang mau diedit:",
        reply_markup=build_task_picker_markup(daftar_tugas, "edit"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit|"))
async def handle_edit_callback(call):
    _, action, *rest = call.data.split("|")
    chat_id = call.message.chat.id

    if action == "cancel":
        await bot.edit_message_text("Dibatalkan.", chat_id, call.message.message_id)
        await bot.answer_callback_query(call.id)
        return

    task_id = rest[0]
    result = supabase.table("study_tasks").select("*").eq("id", task_id).execute()
    if not result.data:
        await bot.answer_callback_query(call.id, "Tugas tidak ditemukan, mungkin sudah dihapus.")
        return
    tugas = result.data[0]

    if action == "pick":
        await bot.edit_message_text(
            f"Edit tugas '{tugas['task_name']}':",
            chat_id,
            call.message.message_id,
            reply_markup=build_edit_menu_markup(task_id),
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "detail":
        back_markup = build_edit_menu_markup(task_id)
        await bot.edit_message_text(
            format_task_detail(tugas),
            chat_id,
            call.message.message_id,
            reply_markup=back_markup,
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "renameprompt":
        start_pending_edit(chat_id, task_id, "task_name")
        await bot.send_message(chat_id, "Kirim nama baru untuk tugas ini:")
        await bot.answer_callback_query(call.id)
        return

    if action == "noteprompt":
        start_pending_edit(chat_id, task_id, "notes")
        await bot.send_message(
            chat_id,
            f"Kirim catatan baru untuk tugas ini (link, catatan panjang, dll, "
            f"maks {MAX_NOTES_LENGTH} karakter).\nKirim '-' untuk menghapus catatan.",
        )
        await bot.answer_callback_query(call.id)
        return

    if action == "deadline":
        supabase.table("pending_tasks").upsert(
            {"chat_id": chat_id, "task_name": tugas["task_name"], "editing_task_id": task_id},
            on_conflict="chat_id",
        ).execute()
        now = datetime.now(WIB)
        await bot.edit_message_text(
            f"Pilih deadline baru untuk '{tugas['task_name']}':",
            chat_id,
            call.message.message_id,
            reply_markup=build_calendar_markup(now.year, now.month),
        )
        await bot.answer_callback_query(call.id)
        return

    await bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda message: get_pending_edit(message.chat.id) is not None)
async def handle_edit_text_input(message):
    chat_id = message.chat.id
    pending = get_pending_edit(chat_id)
    task_id, field = pending["task_id"], pending["field"]
    clear_pending_edit(chat_id)

    text = (message.text or "").strip()

    if field == "task_name":
        if not text:
            await bot.reply_to(message, "Nama tidak boleh kosong. Tidak ada perubahan.")
            return
        supabase.table("study_tasks").update({"task_name": text}).eq("id", task_id).execute()
        await bot.reply_to(message, f"Nama tugas diubah jadi '{text}'.")
        return

    if field == "notes":
        if text == "-":
            supabase.table("study_tasks").update({"notes": None}).eq("id", task_id).execute()
            await bot.reply_to(message, "Catatan dihapus.")
            return
        if len(text) > MAX_NOTES_LENGTH:
            await bot.reply_to(
                message,
                f"Catatan kepanjangan ({len(text)} karakter, maks {MAX_NOTES_LENGTH}). "
                "Kirim /edit lagi lalu coba dengan catatan yang lebih pendek.",
            )
            return
        supabase.table("study_tasks").update({"notes": text}).eq("id", task_id).execute()
        await bot.reply_to(message, "Catatan tersimpan.")
        return
