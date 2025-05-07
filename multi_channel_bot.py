# multi_channel_bot.py

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ChatJoinRequest
)
import json
import os

CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"admins": [], "channels": {}, "welcome_messages": {}, "users": []}, f)

with open(CONFIG_FILE) as f:
    config = json.load(f)

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

api_id = 123456  # REPLACE
api_hash = "your_api_hash"  # REPLACE
bot_token = "your_bot_token"  # REPLACE

app = Client("multi_channel_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

def is_admin(user_id):
    return user_id in config["admins"]

@app.on_chat_join_request()
def accept_join_request(client, join_request: ChatJoinRequest):
    chat_id = str(join_request.chat.id)
    user = join_request.from_user
    if chat_id not in config["channels"]:
        return
    client.approve_chat_join_request(chat_id, user.id)

    msg_data = config["welcome_messages"].get(chat_id, {})
    text = msg_data.get("text", "Welcome!")
    buttons = msg_data.get("buttons", [])
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]) if buttons else None
    client.send_message(user.id, text, reply_markup=markup)

    if user.id not in config["users"]:
        config["users"].append(user.id)
        save_config()

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
    message.reply(f"Channel "{chat.title}" registered.")

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

from pyrogram.handlers import MessageHandler
states = {}

@app.on_callback_query()
def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    if callback_query.data == "set_welcome":
        client.send_message(user_id, "Send the channel ID you want to set welcome message for:")
        states[user_id] = "awaiting_channel_for_welcome"

    elif callback_query.data == "broadcast":
        client.send_message(user_id, "Send the message you want to broadcast:")
        states[user_id] = "awaiting_broadcast"

    elif callback_query.data == "stats":
        user_count = len(config["users"])
        channel_count = len(config["channels"])
        client.send_message(user_id, f"Users: {user_count}\nChannels: {channel_count}")

@app.on_message(filters.private)
def state_responses(client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    state = states.get(user_id)

    if state == "awaiting_channel_for_welcome":
        states[user_id] = {"channel": message.text}
        message.reply("Now send the welcome message text:")

    elif state and isinstance(state, dict) and "channel" in state and "text" not in state:
        states[user_id]["text"] = message.text
        message.reply("Now send buttons (format: text=url, one per line). Send 'done' to finish.")

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
        states.pop(user_id, None)

    elif state == "awaiting_broadcast":
        for uid in config["users"]:
            try:
                client.copy_message(uid, message.chat.id, message.message_id)
            except:
                continue
        message.reply("Broadcast sent.")
        states.pop(user_id, None)

@app.on_message(filters.command("start") & filters.private)
def start(client, message: Message):
    user_id = message.from_user.id
    if user_id not in config["admins"]:
        config["admins"].append(user_id)
        save_config()
    message.reply("Bot is running. Use /admin to open the panel.")

app.run()
