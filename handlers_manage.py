"""Menandai selesai / menghapus tugas lewat pilihan tombol (bukan nomor manual),
supaya tidak bergantung pada urutan tampilan /list."""

from bot_instance import bot, supabase
from keyboards import build_delete_confirm_markup, build_task_picker_markup
from tasks_repo import fetch_tasks


@bot.message_handler(commands=["done"])
async def handle_done(message):
    chat_id = message.chat.id
    daftar_tugas = fetch_tasks(chat_id, None)

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
    daftar_tugas = fetch_tasks(chat_id, None)

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
            await bot.answer_callback_query(
                call.id, "Tugas tidak ditemukan, mungkin sudah dihapus."
            )
            return

        task_name = result.data[0]["task_name"]
        await bot.edit_message_text(
            f"Hapus tugas '{task_name}'?",
            chat_id,
            call.message.message_id,
            reply_markup=build_delete_confirm_markup(task_id),
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
