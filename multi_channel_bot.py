from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ChatJoinRequest
)
import json
import os
import logging

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

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
api_id = 19662976
api_hash = "97cfb26df0a49ab11fa482a5bf660019"
bot_token = "7897472040:AAFb-61va2ltLckzDDoBMozbzYU7MgvtiEQ"

app = Client("multi_channel_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

def is_admin(user_id):
    return user_id in config["admins"]

# --- Handle Join Requests ---
@app.on_chat_join_request()
def accept_join_request(client, join_request: ChatJoinRequest):
    chat_id = str(join_request.chat.id)
    user = join_request.from_user
    logger.info(f"Join request from {user.id} in {chat_id}")

    if chat_id not in config["channels"]:
        logger.warning(f"Channel ID {chat_id} not registered")
        return

    client.approve_chat_join_request(chat_id, user.id)
    logger.info(f"Approved join for user {user.id} in {chat_id}")

    msg_data = config["welcome_messages"].get(chat_id, {})
    text = msg_data.get("text", "Welcome!")
    buttons = msg_data.get("buttons", [])
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]) if buttons else None

    try:
        client.send_message(user.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to send welcome message to {user.id}: {e}")

    if user.id not in config["users"]:
        config["users"].append(user.id)
        save_config()
        logger.info(f"New user added to list: {user.id}")

# --- Register Channel by Forward ---
@app.on_message(filters.forwarded & filters.private)
def register_channel(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    chat = message.forward_from_chat
    if not chat:
        message.reply("Please forward a message from the channel.")
        return

    config["channels"][str(chat.id)] = chat.title
    save_config()
    logger.info(f"Channel registered by {user_id}: {chat.title}")
    message.reply(f'Channel "{chat.title}" registered.')

# --- Admin Panel ---
@app.on_message(filters.command("admin") & filters.private)
def admin_panel(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    keyboard = [
        [InlineKeyboardButton("Set Welcome", callback_data="set_welcome")],
        [InlineKeyboardButton("Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("Stats", callback_data="stats")]
    ]
    message.reply("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Handle Callback Queries ---
states = {}

@app.on_callback_query()
def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    if callback_query.data == "set_welcome":
        client.send_message(user_id, "Send the channel ID you want to set welcome message for:")
        states[user_id] = "awaiting_channel_for_welcome"
        logger.info(f"{user_id} is setting a welcome message")

    elif callback_query.data == "broadcast":
        client.send_message(user_id, "Send the message you want to broadcast:")
        states[user_id] = "awaiting_broadcast"
        logger.info(f"{user_id} is preparing a broadcast")

    elif callback_query.data == "stats":
        user_count = len(config["users"])
        channel_count = len(config["channels"])
        client.send_message(user_id, f"Users: {user_count}\nChannels: {channel_count}")
        logger.info(f"{user_id} requested stats")

# --- Handle Responses to Admin State ---
@app.on_message(filters.private)
def state_responses(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    state = states.get(user_id)

    if state == "awaiting_channel_for_welcome":
        states[user_id] = {"channel": message.text}
        message.reply("Now send the welcome message text:")
        logger.info(f"{user_id} set channel to {message.text}")

    elif state and isinstance(state, dict) and "channel" in state and "text" not in state:
        states[user_id]["text"] = message.text
        message.reply("Now send buttons (format: text=url, one per line). Send 'done' to finish.")
        logger.info(f"{user_id} set welcome text")

    elif state and isinstance(state, dict) and "text" in state:
        buttons = []
        lines = message.text.splitlines()
        for line in lines:
            if "=" in line:
                text, url = line.split("=", 1)
                buttons.append({"text": text.strip(), "url": url.strip()})
        channel_id = states[user_id]["channel"]
        config["welcome_messages"][channel_id] = {
            "text": states[user_id]["text"],
            "buttons": buttons
        }
        save_config()
        message.reply("Welcome message set.")
        logger.info(f"{user_id} set welcome message for {channel_id}")
        states.pop(user_id, None)

    elif state == "awaiting_broadcast":
        sent = 0
        for uid in config["users"]:
            try:
                client.copy_message(uid, message.chat.id, message.message_id)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to {uid}: {e}")
        message.reply(f"Broadcast sent to {sent} users.")
        logger.info(f"{user_id} broadcasted to {sent} users")
        states.pop(user_id, None)

# --- Start Command ---
@app.on_message(filters.command("start") & filters.private)
def start(client, message: Message):
    user_id = message.from_user.id
    if user_id not in config["admins"]:
        config["admins"].append(user_id)
        save_config()
        logger.info(f"New admin added via /start: {user_id}")
    message.reply("Bot is running. Use /admin to open the panel.")
    logger.info(f"{user_id} used /start")

# --- Run the Bot ---
logger.info("Starting bot...")
app.run()
