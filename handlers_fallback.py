"""Fallback untuk pesan yang tidak cocok dengan handler manapun. Harus diimpor
paling akhir di main.py -- filter-nya selalu True, jadi dia "menelan" semua
pesan kalau didaftarkan lebih awal dari handler lain."""

from bot_instance import bot


@bot.message_handler(func=lambda message: True)
async def handle_unknown(message):
    await bot.reply_to(message, f"Perintah: {message.text} tidak ditemukan")
