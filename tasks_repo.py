"""Akses ke tabel study_tasks & pending_tasks di Supabase, plus perhitungan tanggal/waktu terkait."""

import calendar as calendar_module
from datetime import datetime, timedelta

from bot_instance import WIB, supabase


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
    """Pindahkan tugas dari pending_tasks (state sementara /task) ke study_tasks."""
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
