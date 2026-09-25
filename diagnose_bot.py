#!/usr/bin/env python3
"""Check a Telegram bot end to end and explain how to fix anything broken.

Run it and paste the token when asked (input is hidden and never printed):
    python3 diagnose_bot.py

It checks the token, the webhook, which chats/channels the bot can see,
whether it is an admin of your channel, and can send a test news alert
and a test Gemini reply. Anything that sends a message asks first.
"""

import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

TOKEN = ""


def clean(text):
    return str(text).replace(TOKEN, "<token>") if TOKEN else str(text)


def api(method, params=None):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(params or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return {"ok": False, "description": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "description": clean(exc)}


def ok(msg):
    print(f"  ✅ {msg}")


def bad(msg, fix=None):
    print(f"  ❌ {msg}")
    if fix:
        print(f"     → Fix: {fix}")


def ask(question):
    while True:
        answer = input(f"\n{question} Type y or n: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        # Something else was typed or pasted here, often a key meant for the next (hidden) prompt.
        print("\033[1A\033[2K", end="")  # erase the echoed line from the screen
        print("  ⚠️  That wasn't y or n. If you pasted a key or token here, it was visible on screen: "
              "create a new one to be safe.\n     Answer y or n first. You'll get a hidden prompt for the key next.")


def wait_for_chats(seconds=120):
    """Long-poll Telegram while the user adds the bot to the channel."""
    chats, deadline = {}, time.time() + seconds
    offset = None
    while time.time() < deadline and not any(c["type"] == "channel" for c in chats.values()):
        left = int(deadline - time.time())
        print(f"\r  ⏳ Waiting for the bot to be added / a channel post… {left:3d}s left ", end="", flush=True)
        params = {"timeout": min(20, max(1, left)),
                  "allowed_updates": ["message", "channel_post", "my_chat_member"]}
        if offset:
            params["offset"] = offset
        for upd in api("getUpdates", params).get("result", []):
            offset = upd["update_id"] + 1
            for key in ("message", "channel_post", "my_chat_member"):
                chat = (upd.get(key) or {}).get("chat")
                if chat:
                    chats[chat["id"]] = chat
    print()
    return chats


def main():
    global TOKEN
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or getpass.getpass("Paste the bot token (hidden): ").strip()
    if not TOKEN:
        sys.exit("No token entered.")

    print("\n1. Token")
    me = api("getMe")
    if not me.get("ok"):
        bad(f"Telegram rejected the token: {me.get('description')}",
            "Copy the token again from @BotFather (/mybots → your bot → API Token).")
        return
    bot = me["result"]
    ok(f"Token works: @{bot['username']} (id {bot['id']})")

    print("\n2. Webhook")
    hook = api("getWebhookInfo").get("result", {})
    if hook.get("url"):
        print(f"  ℹ️  Webhook is set to: {hook['url']}")
        print(f"     Pending messages: {hook.get('pending_update_count', 0)}")
        if hook.get("last_error_message"):
            bad(f"Telegram's last delivery error: {hook['last_error_message']}",
                "The server at that URL is failing or unreachable. That's why the bot doesn't reply.")
        else:
            ok("No delivery errors reported.")
    else:
        print("  ℹ️  No webhook set. Nothing is receiving messages, so the bot can't reply until one is set "
              "(open /api/setup on the Vercel deployment).")

    print("\n3. Chats the bot can see")
    print("   (Post any message in your channel first so it shows up here.)")
    chats = {}
    if hook.get("url"):
        print("  ℹ️  Skipped: getUpdates doesn't work while a webhook is set.")
        if ask("Temporarily remove the webhook so this check can run? (You'll re-add it with /api/setup)"):
            api("deleteWebhook", {"drop_pending_updates": False})
            hook = {}
    if not hook.get("url"):
        updates = api("getUpdates", {"timeout": 0, "allowed_updates": [
            "message", "channel_post", "my_chat_member"]})
        for upd in updates.get("result", []):
            for key in ("message", "channel_post", "my_chat_member"):
                chat = (upd.get(key) or {}).get("chat")
                if chat:
                    chats[chat["id"]] = chat
        if not any(c["type"] == "channel" for c in chats.values()):
            print(f"  ℹ️  No channel yet. Do this now, while the script waits:\n"
                  f"     1. Open your channel → tap its name → Administrators → Add Admin\n"
                  f"     2. Search @{bot['username']}, turn on 'Post messages', save\n"
                  f"     3. Post any message in the channel")
            chats.update(wait_for_chats())
        if chats:
            for chat in chats.values():
                ok(f"{chat['type']}: '{chat.get('title') or chat.get('username') or chat.get('first_name')}' "
                   f"→ TELEGRAM_CHAT_ID = {chat['id']}")
        else:
            bad("The bot hasn't seen any chats or channels yet.",
                "Add the bot to the channel as an admin, post a message in the channel, then run this again.")

    print("\n4. Channel access")
    channel_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    channels = [c for c in chats.values() if c["type"] == "channel"]
    if not channel_id and len(channels) == 1:
        channel_id = str(channels[0]["id"])
    while not channel_id:
        channel_id = input("  Channel ID to test (e.g. -100… or @publicname), or Enter to skip: ").strip()
        if not channel_id:
            break
        if "t.me/" in channel_id:
            bad("That's an invite link, not a channel ID. Telegram's API can't open invite links.",
                "Add the bot as a channel admin and post a message, then run this script again. "
                "It will find the ID (starting -100) for you in step 3.")
            channel_id = ""
            break
    if channel_id:
        member = api("getChatMember", {"chat_id": channel_id, "user_id": bot["id"]})
        if not member.get("ok"):
            bad(f"Can't access chat {channel_id}: {member.get('description')}",
                "Add the bot to the channel (Channel → Administrators → Add Admin → search the bot).")
        else:
            m = member["result"]
            if m["status"] == "creator" or (m["status"] == "administrator" and m.get("can_post_messages", True)):
                ok(f"Bot is {m['status']} of {channel_id} and can post.")
            else:
                bad(f"Bot's status in the channel is '{m['status']}', so it can't post.",
                    "Make it an admin with the 'Post messages' permission.")
            if ask(f"Send a test news alert to {channel_id} now?"):
                from news_alert import IST, build_message, todays_pillar
                import datetime
                today = datetime.datetime.now(IST).date()
                msg = build_message(todays_pillar(today), today) or "Test message from diagnose_bot.py"
                sent = api("sendMessage", {"chat_id": channel_id, "text": msg, "parse_mode": "HTML",
                                           "disable_web_page_preview": True})
                if sent.get("ok"):
                    ok("Test alert sent. Check the channel.")
                else:
                    bad(f"Send failed: {sent.get('description')}")

    print("\n5. Gemini (chatbot replies)")
    if ask("Test a Gemini reply? (you'll paste the Gemini API key, hidden)"):
        key = getpass.getpass("  Paste GEMINI_API_KEY (hidden): ").strip()
        os.environ["GEMINI_API_KEY"] = key
        import telegram as bot_code
        orig_print = __builtins__.print
        errors = []
        bot_code.print = lambda *a, **k: errors.append(" ".join(map(str, a)).replace(key, "<key>"))
        answer = bot_code.ask_gemini(input("  Question to ask (Enter for a default): ").strip()
                                     or "Can I use niacinamide with vitamin C?")
        info_notes = ("unavailable; using", "trimmed")
        for note in errors:
            if any(n in note for n in info_notes):
                print(f"  ℹ️  {note}")
        errors = [e for e in errors if not any(n in e for n in info_notes)]
        if errors:
            bad(errors[0], "Check the key in Google AI Studio, or set GEMINI_MODEL to a model your key can use.")
        elif answer.startswith("Sorry"):
            bad("Gemini didn't return an answer.")
        else:
            ok(f"Gemini replied (model: {bot_code._model_cache.get('model')}):")
            orig_print("     " + answer.replace("\n", "\n     "))

    print("\nDone. Copy everything above (it contains no secrets) back to Claude if anything failed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
