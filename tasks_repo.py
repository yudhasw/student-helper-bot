"""Akses ke tabel study_tasks & pending_tasks di Supabase, plus perhitungan tanggal/waktu terkait."""

import calendar as calendar_module
from datetime import datetime, timedelta

from bot_instance import WIB, supabase

MAX_NOTES_LENGTH = 1000


def today_str() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


def is_overdue(deadline: str | None) -> bool:
    return deadline is not None and deadline < today_str()


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


def is_within_current_week(deadline: str) -> bool:
    start, end = _date_range_for_scope("week", datetime.now(WIB))
    return start <= deadline <= end


def fetch_tasks(chat_id: int, scope: str | None) -> list[dict]:
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


def deadline_datetime(deadline_date: str, deadline_time: str | None) -> datetime:
    # Kalau jam deadline tidak diketahui, anggap akhir hari (23:59) sebagai fallback.
    hour, minute = map(int, (deadline_time or "23:59").split(":"))
    return datetime.strptime(deadline_date, "%Y-%m-%d").replace(
        hour=hour, minute=minute, tzinfo=WIB
    )


def compute_remind_at_offset(
    deadline_date: str, deadline_time: str | None, hours_before: int, minutes_before: int
) -> str:
    deadline_dt = deadline_datetime(deadline_date, deadline_time)
    remind_at = deadline_dt - timedelta(hours=hours_before, minutes=minutes_before)
    return remind_at.isoformat()


def finalize_task(
    chat_id: int,
    deadline_iso: str | None,
    deadline_time: str | None = None,
    remind_at_iso: str | None = None,
) -> str | None:
    """Terapkan deadline/reminder hasil alur kalender ke pending_tasks.

    Kalau pending_tasks.editing_task_id terisi, ini alur "ubah deadline" tugas
    yang sudah ada (dari /edit) -> UPDATE baris itu. Kalau tidak, ini alur
    /task biasa -> INSERT tugas baru.
    """
    pending = (
        supabase.table("pending_tasks")
        .select("task_name, editing_task_id")
        .eq("chat_id", chat_id)
        .execute()
    )
    if not pending.data:
        return None

    task_name = pending.data[0]["task_name"]
    editing_task_id = pending.data[0].get("editing_task_id")
    payload = {
        "deadline": deadline_iso,
        "deadline_time": deadline_time,
        "remind_at": remind_at_iso,
        "reminder_sent": False,
    }

    if editing_task_id:
        supabase.table("study_tasks").update(payload).eq("id", editing_task_id).execute()
    else:
        payload.update({"chat_id": chat_id, "task_name": task_name})
        supabase.table("study_tasks").insert(payload).execute()

    supabase.table("pending_tasks").delete().eq("chat_id", chat_id).execute()
    return task_name


def get_pending_edit(chat_id: int) -> dict | None:
    """Cek apakah chat ini sedang ditunggu balasan teksnya buat /edit (ubah nama/catatan)."""
    result = (
        supabase.table("pending_edits").select("task_id, field").eq("chat_id", chat_id).execute()
    )
    return result.data[0] if result.data else None


def start_pending_edit(chat_id: int, task_id: str, field: str) -> None:
    supabase.table("pending_edits").upsert(
        {"chat_id": chat_id, "task_id": task_id, "field": field}, on_conflict="chat_id"
    ).execute()


def clear_pending_edit(chat_id: int) -> None:
    supabase.table("pending_edits").delete().eq("chat_id", chat_id).execute()
