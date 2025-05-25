from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ChatJoinRequest
)
import json
import os
import logging

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- Global State ---
states = {}

# --- Load Config ---
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"admins": [], "channels": {}, "welcome_messages": {}, "users": []}, f)
    logger.info("Created new config file.")

with open(CONFIG_FILE) as f:
    config = json.load(f)
    logger.info("Loaded config.json")

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("Configuration saved.")

# --- Bot Credentials ---
api_id = 25480339
api_hash = "2dad95892b2ae39b059c53a7796b687f"
bot_token = "7687213948:AAGF3X6-qxtU3PqMxrjHZwLiucOdhZiM_a0"

app = Client("multi_channel_bot.py", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

def is_admin(user_id):
    return user_id in config["admins"]

# --- Join Request Handler ---
@app.on_chat_join_request()
async def accept_join_request(client, join_request: ChatJoinRequest):
    chat_id = str(join_request.chat.id)
    user = join_request.from_user
    logger.info(f"Join request from {user.id} in {chat_id}")

    if chat_id not in config["channels"]:
        logger.warning(f"Channel ID {chat_id} not registered")
        return

    await client.approve_chat_join_request(chat_id, user.id)
    logger.info(f"Approved join for user {user.id} in {chat_id}")

    msg_data = config["welcome_messages"].get(chat_id, {})
    caption = msg_data.get("text", "Welcome!")
    buttons = msg_data.get("buttons", [])
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]) if buttons else None

    try:
        media_type = msg_data.get("type")
        media_id = msg_data.get("media_id")
        if media_type == "photo":
            await client.send_photo(user.id, photo=media_id, caption=caption, reply_markup=markup)
        elif media_type == "video":
            await client.send_video(user.id, video=media_id, caption=caption, reply_markup=markup)
        else:
            await client.send_message(user.id, caption, reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to send welcome message to {user.id}: {e}")

    if user.id not in config["users"]:
        config["users"].append(user.id)
        save_config()
        logger.info(f"New user added: {user.id}")

# --- Register Channel ---
@app.on_message(filters.forwarded & filters.private)
async def register_channel(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    chat = message.forward_from_chat
    if not chat:
        await message.reply("Please forward a message from the channel.")
        return

    config["channels"][str(chat.id)] = chat.title
    save_config()
    await message.reply(f'Channel "{chat.title}" registered.')

# --- Admin Panel Command ---
@app.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message: Message):
    if not is_admin(message.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("Set Welcome", callback_data="set_welcome")],
        [InlineKeyboardButton("Stats", callback_data="stats")]
    ]
    await message.reply("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Callback Handler ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    data = callback_query.data

    if data == "set_welcome":
        await client.send_message(user_id, "Send the channel ID you want to set welcome message for:")
        states[user_id] = {"step": "awaiting_channel"}

    elif data == "stats":
        user_count = len(config["users"])
        channel_count = len(config["channels"])
        await client.send_message(user_id, f"Users: {user_count}\nChannels: {channel_count}")

# --- Admin Flow Handler ---
@app.on_message(filters.private)
async def handle_admin_states(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    state = states.get(user_id)
    if not state:
        return

    if state.get("step") == "awaiting_channel":
        states[user_id] = {"channel": message.text, "step": "awaiting_welcome"}
        await message.reply("Send the welcome message text or caption:")

    elif state.get("step") == "awaiting_welcome":
        states[user_id]["text"] = message.text
        states[user_id]["step"] = "awaiting_buttons"
        await message.reply("Send buttons (text=url), one per line. Send 'done' to skip.")

    elif state.get("step") == "awaiting_buttons":
        if message.text.lower() == "done":
            states[user_id]["buttons"] = []
        else:
            buttons = []
            for line in message.text.splitlines():
                if "=" in line:
                    text, url = line.split("=", 1)
                    buttons.append({"text": text.strip(), "url": url.strip()})
            states[user_id]["buttons"] = buttons
        states[user_id]["step"] = "awaiting_media"
        await message.reply("Send photo/video or 'skip' to finish.")

    elif state.get("step") == "awaiting_media":
        channel_id = states[user_id]["channel"]
        welcome_data = {
            "text": states[user_id]["text"],
            "buttons": states[user_id]["buttons"]
        }

        if message.text and message.text.lower() == "skip":
            pass
        elif message.photo:
            welcome_data["type"] = "photo"
            welcome_data["media_id"] = message.photo.file_id
        elif message.video:
            welcome_data["type"] = "video"
            welcome_data["media_id"] = message.video.file_id

        config["welcome_messages"][channel_id] = welcome_data
        save_config()
        await message.reply("✅ Welcome message set.")
        states.pop(user_id)

# --- Broadcast Handler ---
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    if not message.reply_to_message:
        await message.reply("❗Please reply to the message you want to broadcast.")
        return

    broadcast_msg = message.reply_to_message
    sent = failed = 0
    for uid in config["users"]:
        try:
            await client.copy_message(uid, broadcast_msg.chat.id, broadcast_msg.message_id)
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {uid}: {e}")
            failed += 1

    await message.reply(f"✅ Broadcast done.\nSent: {sent}\nFailed: {failed}")

# --- Start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id not in config["users"]:
        config["users"].append(user_id)
        save_config()
    if user_id not in config["admins"]:
        config["admins"].append(user_id)
        save_config()
    await message.reply_text("✅ Bot is running.\nUse /admin to open the panel.")

# --- Run the Bot ---
logger.info("Starting bot...")
