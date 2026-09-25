"""Vercel cron function: send today's Google News headlines to a Telegram channel.

Vercel calls GET /api/news_alert once a day (see vercel.json). Needs these
environment variables, set in the Vercel dashboard (never in code):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import datetime
import email.utils
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler

PILLARS = {
    1: ("Content strategy and creator-economy insights",
        ["creator economy", "content marketing trends", "influencer marketing India"]),
    2: ("Behind-the-scenes of managing brands and artists",
        ["brand management social media", "artist management", "community management brands"]),
    3: ("MBA and business-learning journey",
        ["MBA India", "business school AI curriculum", "MBA career pivot"]),
    4: ("Personal reflections on career growth",
        ["career growth Gen Z", "future of work AI jobs", "creative careers"]),
}

FEED = "https://news.google.com/rss/search?q={q}+when:2d&hl=en-IN&gl=IN&ceid=IN:en"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
PER_QUERY = 2
MAX_LEN = 4000  # Telegram caps messages at 4096 characters


def fetch(query):
    url = FEED.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        source = item.findtext("source", "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        try:
            date = email.utils.parsedate_to_datetime(item.findtext("pubDate", "")).strftime("%d %b")
        except (TypeError, ValueError):
            date = ""
        items.append((title, source, date, item.findtext("link", "").strip()))
        if len(items) >= PER_QUERY:
            break
    return items


def todays_pillar(today):
    # Rotate 1 -> 2 -> 3 -> 4 by calendar day, so each day covers the next pillar.
    return today.toordinal() % len(PILLARS) + 1


def build_message(pillar, today):
    name, queries = PILLARS[pillar]
    lines, seen = [], set()
    for q in queries:
        try:
            results = fetch(q)
        except Exception:
            continue
        for title, source, date, link in results:
            if title in seen:
                continue
            seen.add(title)
            lines.append(f'• <a href="{html.escape(link)}">{html.escape(title)}</a> '
                         f'<i>({html.escape(source)}, {date})</i>')
    if not lines:
        return None
    msg = (f"<b>📰 News alert — {today.strftime('%d %b %Y')}</b>\n"
           f"<b>{html.escape(name)}</b>\n\n" + "\n\n".join(lines))
    return msg[:MAX_LEN]


def send(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp).get("ok", False), "sent"
    except urllib.error.HTTPError as exc:
        # Report Telegram's reason without echoing the URL, which contains the token.
        body = json.loads(exc.read() or b"{}")
        return False, f"Telegram error {exc.code}: {body.get('description', 'unknown')}"


class handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return self._reply(500, {"ok": False, "error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"})

        today = datetime.datetime.now(IST).date()
        pillar = todays_pillar(today)
        message = build_message(pillar, today)
        if message is None:
            return self._reply(502, {"ok": False, "error": "Google News returned no articles", "pillar": pillar})

        ok, detail = send(token, chat_id, message)
        self._reply(200 if ok else 502, {"ok": ok, "pillar": pillar, "detail": detail})
