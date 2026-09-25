"""One-time setup: open /api/setup in a browser after deploying to connect the bot.

Registers this deployment's /api/telegram endpoint as the bot's webhook and sets
the bot's command menu. Safe to open again at any time (e.g. after changing the token).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from telegram import telegram, webhook_secret  # noqa: E402

COMMANDS = [
    {"command": "news", "description": "Today's Google News headlines"},
    {"command": "help", "description": "What this bot can do"},
]


class handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return self._reply(500, {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set in Vercel"})
        # Use the stable production domain so Vercel's deployment protection doesn't block Telegram.
        host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or self.headers.get("Host")
        url = f"https://{host}/api/telegram"

        hook = telegram(token, "setWebhook", {
            "url": url,
            "secret_token": webhook_secret(token),
            "allowed_updates": ["message", "edited_message"],
            "drop_pending_updates": True,
        })
        telegram(token, "setMyCommands", {"commands": COMMANDS})
        me = telegram(token, "getMe", {}).get("result", {})
        info = telegram(token, "getWebhookInfo", {}).get("result", {})

        self._reply(200 if hook.get("ok") else 502, {
            "ok": bool(hook.get("ok")),
            "bot": f"@{me.get('username', '?')}",
            "webhook": info.get("url"),
            "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
            "last_error": info.get("last_error_message"),
            "next_step": "Open Telegram and send your bot a message." if hook.get("ok")
                         else "Check that TELEGRAM_BOT_TOKEN is correct, then reload this page.",
        })
