"""Telegram webhook: replies to messages in Meera Pillai's voice using Gemini.

Telegram POSTs every message to /api/telegram (registered once via /api/setup).
Needs these environment variables, set in the Vercel dashboard (never in code):
    TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
Optional:
    GEMINI_MODEL (default gemini-2.5-flash)
"""

import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from _persona import SYSTEM_PROMPT  # noqa: E402
from news_alert import IST, build_message, todays_pillar  # noqa: E402

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_LEN = 4000

WELCOME = ("Hi, I'm Meera, founder of Skinstinct. Ask me about an ingredient, a label claim, "
           "pH, layering, or anything about how skincare formulations actually work.\n\n"
           "Type /news for today's headlines.")


def webhook_secret(token):
    # Derived from the bot token, so there's no extra secret to manage. /api/setup registers
    # the same value with Telegram, and Telegram sends it back on every webhook call.
    return hashlib.sha256(("webhook:" + token).encode()).hexdigest()[:48]


def ask_gemini(question):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return "The bot isn't fully set up yet: GEMINI_API_KEY is missing."
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 800},
    }
    req = urllib.request.Request(
        GEMINI_URL.format(model=model),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"Gemini error {exc.code}: {exc.read()[:500]!r}")
        return "Sorry, I couldn't answer that just now. Please try again in a minute."
    except Exception as exc:
        print(f"Gemini request failed: {exc}")
        return "Sorry, I couldn't answer that just now. Please try again in a minute."

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError):
        print(f"Unexpected Gemini response: {json.dumps(data)[:500]}")
        text = ""
    # Telegram gets plain text, so strip any markdown emphasis Gemini adds anyway.
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    return text or "I don't have a good answer to that one. Could you rephrase it?"


def telegram(token, method, params):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        # Log Telegram's reason without the URL, which contains the token.
        print(f"Telegram {method} error {exc.code}: {exc.read()[:300]!r}")
        return {"ok": False}


def reply_to(message):
    text = (message.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    if command in ("/start", "/help"):
        return WELCOME, None
    if command == "/news":
        today = datetime.datetime.now(IST).date()
        news = build_message(todays_pillar(today), today)
        return (news or "Google News didn't return any articles just now. Try again later."), "HTML"
    if not text:
        return "I can only read text messages for now.", None
    return ask_gemini(text)[:MAX_LEN], None


class handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, {"ok": True, "info": "Telegram webhook. Telegram sends messages here via POST."})

    def do_POST(self):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return self._reply(500, {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"})
        sent = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(sent, webhook_secret(token)):
            return self._reply(401, {"ok": False, "error": "unauthorized"})

        length = int(self.headers.get("Content-Length") or 0)
        try:
            update = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._reply(200, {"ok": True})

        message = update.get("message") or update.get("edited_message")
        # Always answer Telegram with 200, or it keeps retrying the same update.
        if not message or message.get("from", {}).get("is_bot"):
            return self._reply(200, {"ok": True})

        chat_id = message["chat"]["id"]
        telegram(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
        text, parse_mode = reply_to(message)
        params = {"chat_id": chat_id, "text": text, "reply_to_message_id": message["message_id"],
                  "disable_web_page_preview": True}
        if parse_mode:
            params["parse_mode"] = parse_mode
        telegram(token, "sendMessage", params)
        self._reply(200, {"ok": True})
