"""Command dasar: /start, /help, /versi."""

from bot_instance import APP_VERSION, HELP_TEXT, bot


@bot.message_handler(commands=["start", "help"])
async def handle_start(message):
    await bot.reply_to(message, HELP_TEXT)


@bot.message_handler(commands=["versi"])
async def handle_versi(message):
    await bot.reply_to(message, f"Versi bot: {APP_VERSION}")
