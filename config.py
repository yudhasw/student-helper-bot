import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
TELEGRAM_WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"].strip()

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_KEY"].strip()

CRON_SECRET = os.environ["CRON_SECRET"].strip()

# Hanya untuk dev lokal: jalankan digest pagi lewat APScheduler di dalam proses
# uvicorn (karena proses lokal selalu hidup). Di Vercel, JANGAN set ini —
# cron.vercel.json yang memanggil /internal/tick dari luar.
ENABLE_LOCAL_SCHEDULER = os.getenv("ENABLE_LOCAL_SCHEDULER", "false").strip().lower() == "true"
DIGEST_HOUR_WIB = int(os.getenv("DIGEST_HOUR_WIB", "7"))
DIGEST_MINUTE_WIB = int(os.getenv("DIGEST_MINUTE_WIB", "0"))
