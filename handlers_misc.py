"""Command dasar: /start, /help, /versi, dan fallback untuk perintah tak dikenal."""

from bot_instance import APP_VERSION, HELP_TEXT, bot


@bot.message_handler(commands=["start", "help"])
async def handle_start(message):
    await bot.reply_to(message, HELP_TEXT)


@bot.message_handler(commands=["versi"])
async def handle_versi(message):
    await bot.reply_to(message, f"Versi bot: {APP_VERSION}")


@bot.message_handler(func=lambda message: True)
async def handle_unknown(message):
    await bot.reply_to(message, f"Perintah: {message.text} tidak ditemukan")
