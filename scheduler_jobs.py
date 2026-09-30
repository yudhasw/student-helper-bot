"""Job berkala: digest pagi dan pengiriman reminder per-tugas. Dipanggil oleh /internal/tick
dan (kalau ENABLE_LOCAL_SCHEDULER) oleh APScheduler saat dev lokal."""

from datetime import datetime
from zoneinfo import ZoneInfo

from bot_instance import bot, logger, supabase
from tasks_repo import today_str


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
