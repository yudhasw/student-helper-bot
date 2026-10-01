"""Format teks yang ditampilkan ke user: daftar tugas dan konfirmasi penyimpanan."""

from datetime import datetime

from bot_instance import WIB
from tasks_repo import is_overdue, is_within_current_week

NAMA_HARI_LENGKAP = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

SCOPE_JUDUL = {
    None: "tugas yang belum selesai",
    "today": "tugas hari ini",
    "week": "tugas minggu ini",
    "month": "tugas bulan ini",
    "overdue": "tugas yang sudah lewat deadline",
}


def format_deadline_short(deadline: str | None, deadline_time: str | None) -> str:
    if not deadline:
        return "-"

    if is_within_current_week(deadline):
        hari = NAMA_HARI_LENGKAP[datetime.strptime(deadline, "%Y-%m-%d").weekday()]
        short = hari
    else:
        short = deadline[5:]  # "YYYY-MM-DD" -> "MM-DD"

    return f"{short} {deadline_time}" if deadline_time else short


def _format_task_line(i: int, tugas: dict, scope: str | None) -> str:
    if scope == "today":
        return f"{i}. {tugas['task_name']}"
    deadline = format_deadline_short(tugas["deadline"], tugas.get("deadline_time"))
    return f"{i}. {tugas['task_name']} - {deadline}"


def format_task_list(daftar_tugas: list[dict], scope: str | None) -> str:
    if not daftar_tugas:
        return f"Bebas tugas! Tidak ada {SCOPE_JUDUL[scope]}."

    if scope == "overdue":
        lines = [f"Ini {SCOPE_JUDUL[scope]}:"]
        lines += [_format_task_line(i, t, scope) for i, t in enumerate(daftar_tugas, start=1)]
        return "\n".join(lines)

    non_overdue = [t for t in daftar_tugas if not is_overdue(t["deadline"])]
    overdue = [t for t in daftar_tugas if is_overdue(t["deadline"])]

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


def save_task_text(
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
