#!/usr/bin/env bash
# Set Telegram webhook ke URL deployment saat ini.
# Pakai: TELEGRAM_BOT_TOKEN=xxx APP_URL=https://student-helper-bot.vercel.app ./scripts/set_webhook.sh
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?wajib diisi}"
: "${APP_URL:?wajib diisi, tanpa trailing slash}"

# Hilangkan trailing slash kalau ada, biar tidak double slash saat digabung.
APP_URL="${APP_URL%/}"

curl -sf -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${APP_URL}/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"

echo
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
