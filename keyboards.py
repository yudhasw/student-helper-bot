"""Semua inline keyboard yang dipakai bot: kalender, pemilihan jam, reminder, dan task picker."""

import calendar as calendar_module

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

NAMA_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]

REMINDER_PRESETS = [
    ("1 jam sebelum", 1),
    ("3 jam sebelum", 3),
    ("1 hari sebelum", 24),
]

MINUTE_OPTIONS = [0, 15, 30, 45]


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


def build_time_markup(prefix: str) -> InlineKeyboardMarkup:
    """Grid jam 00-23. `prefix` menentukan tujuan callback (mis. 'dtime' atau 'rem')."""
    markup = InlineKeyboardMarkup(row_width=6)
    buttons = [
        InlineKeyboardButton(f"{h:02d}", callback_data=f"{prefix}|pickhour|{h}") for h in range(24)
    ]
    for i in range(0, 24, 6):
        markup.row(*buttons[i : i + 6])
    return markup


def build_minute_markup(prefix: str, hour: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=4)
    markup.row(
        *[
            InlineKeyboardButton(f"{hour:02d}:{m:02d}", callback_data=f"{prefix}|hour|{hour}|{m}")
            for m in MINUTE_OPTIONS
        ]
    )
    return markup


def build_deadline_time_markup() -> InlineKeyboardMarkup:
    markup = build_time_markup("dtime")
    markup.row(InlineKeyboardButton("Tidak tahu jam pastinya", callback_data="dtime|skip"))
    return markup


def build_reminder_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for label, hours in REMINDER_PRESETS:
        markup.add(InlineKeyboardButton(label, callback_data=f"rem|preset|{hours}"))
    markup.add(
        InlineKeyboardButton("Durasi custom sebelum deadline", callback_data="rem|customoffset")
    )
    markup.add(InlineKeyboardButton("Tanpa reminder khusus", callback_data="rem|none"))
    return markup


def build_delete_confirm_markup(task_id: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(
        InlineKeyboardButton("Ya, hapus", callback_data=f"del|confirm|{task_id}"),
        InlineKeyboardButton("Batal", callback_data="del|cancel"),
    )
    return markup


def _short_task_label(tugas: dict) -> str:
    name = tugas["task_name"]
    deadline = tugas["deadline"]
    if deadline:
        waktu = f" {tugas['deadline_time']}" if tugas.get("deadline_time") else ""
        label = f"{name} ({deadline[5:]}{waktu})"
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
