# Meera LinkedIn AI: Telegram bot

A Telegram bot on Vercel with two jobs:

1. **Chatbot** (`/api/telegram`): replies to every message in the voice of Meera Pillai, founder of Skinstinct, using Google Gemini. `/news` returns today's headlines and `/help` explains the bot.
2. **Daily news alert** (`/api/news_alert`): a Vercel cron job that posts recent Google News headlines for one content pillar to a Telegram channel. The pillars rotate daily, 1 → 2 → 3 → 4:
   1. Content strategy and creator-economy insights
   2. Behind-the-scenes of managing brands and artists
   3. MBA and business-learning journey
   4. Personal reflections on career growth

It uses only the Python standard library. Google News RSS needs no API key.

## Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Needed for | Value |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | both | Token from @BotFather |
| `GEMINI_API_KEY` | chatbot | Key from Google AI Studio |
| `TELEGRAM_CHAT_ID` | news alert | `@yourchannel` or the `-100…` ID of a private channel (the bot must be a channel admin) |
| `GEMINI_MODEL` | optional | Defaults to `gemini-2.5-flash` |

After adding or changing a variable, redeploy (Deployments → ⋯ → Redeploy).

## Connect the bot (once)

After the first deploy, open `https://<your-project>.vercel.app/api/setup` in a browser. It registers the webhook with Telegram and sets the command menu. It should show `"ok": true`. Open it again whenever you change the bot token.

## Schedule

`30 3 * * *` UTC is **9:00 AM IST**. On Vercel's Hobby plan, the alert can arrive at any point in that hour.

## Test

- Chatbot: message the bot in Telegram.
- News alert: Vercel → Project → **Settings → Cron Jobs** → **Run**.
- Problems: check Vercel → Project → **Logs**. Open `/api/setup` again to see Telegram's `last_error`.

Never commit a `.env` file. It is listed in `.gitignore`.
