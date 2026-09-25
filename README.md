# Telegram News Alert

A daily Vercel cron job that pulls recent Google News headlines for one content pillar and posts them to a Telegram channel. The pillars rotate daily, 1 → 2 → 3 → 4:

1. Content strategy and creator-economy insights
2. Behind-the-scenes of managing brands and artists
3. MBA and business-learning journey
4. Personal reflections on career growth

It uses only the Python standard library, and Google News RSS needs no API key.

## Schedule

`30 3 * * *` UTC is **9:00 AM IST**. On Vercel's Hobby plan, a cron job can fire at any point within its scheduled hour, so the alert arrives between roughly 9:00 and 10:00 AM IST.

## Environment variables (set in Vercel → Project → Settings → Environment Variables)

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | `@yourchannel` or the `-100…` ID of a private channel |
| `CRON_SECRET` | Any long random string, e.g. the output of `openssl rand -hex 32` |

Vercel sends `CRON_SECRET` with each cron call. Any other request to the endpoint gets a `401`. The bot must be an admin of the channel with permission to post.

## Test it

Vercel → Project → **Settings → Cron Jobs** → **Run** next to `/api/news_alert`. Then check the function logs for the JSON result.

Never commit a `.env` file. It is listed in `.gitignore`.
