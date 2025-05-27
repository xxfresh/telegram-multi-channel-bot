from pyrogram import Client, filters
from pyrogram.filters import command, private, user
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ChatJoinRequest
)
from pymongo import MongoClient
import logging

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
mongo_client = MongoClient("mongodb+srv://mystery:exelexa2237887@cluster0.epdqu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # Adjust connection string as needed
db = mongo_client["telegram_bot"]
config_collection = db["config"]

# Initialize MongoDB collections if they don't exist
if "config" not in db.list_collection_names():
    config_collection.insert_one({
        "admins": [],
        "channels": {},
        "welcome_messages": {},
        "users": []
    })
    logger.info("Initialized MongoDB config collection.")

# --- Global State ---
states = {}

# --- Helper Functions ---
def get_config():
    return config_collection.find_one({})

def save_config(config_data):
    config_collection.update_one({}, {"$set": config_data}, upsert=True)
    logger.info("Configuration saved to MongoDB.")

def is_admin(user_id):
    config = get_config()
    return user_id in config.get("admins", [])

# --- Bot Credentials ---
api_id = 25480339
api_hash = "2dad95892b2ae39b059c53a7796b687f"
bot_token = "7687213948:AAGF3X6-qxtU3PqMxrjHZwLiucOdhZiM_a0"

app = Client("multi_channel_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# --- Join Request Handler ---
@app.on_chat_join_request()
async def accept_join_request(client, join_request: ChatJoinRequest):
    chat_id = str(join_request.chat.id)
    user = join_request.from_user
    logger.info(f"Join request from {user.id} in {chat_id}")

    config = get_config()
    if chat_id not in config.get("channels", {}):
        logger.warning(f"Channel ID {chat_id} not registered")
        return

    await client.approve_chat_join_request(chat_id, user.id)
    logger.info(f"Approved join for user {user.id} in {chat_id}")

    msg_data = config.get("welcome_messages", {}).get(chat_id, {})
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

    if user.id not in config.get("users", []):
        config["users"].append(user.id)
        save_config(config)
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

    config = get_config()
    config["channels"][str(chat.id)] = chat.title
    save_config(config)
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
        config = get_config()
        user_count = len(config.get("users", []))
        channel_count = len(config.get("channels", {}))
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

    config = get_config()
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
        save_config(config)
        await message.reply("✅ Welcome message set.")
        states.pop(user_id)

# --- Broadcast Handler ---
@app.on_message(filters.command("broadcast") & filters.private & filters.reply)
async def broadcast_command(client, message: Message):
    user_id = message.from_user.id

    # Check admin
    config = get_config()
    if user_id not in config.get("admins", []):
        return await message.reply("❌ You are not authorized.")

    # Check if it's a reply
    if not message.reply_to_message:
        return await message.reply("⚠️ Please reply to a message (text/photo/video) to broadcast.")

    broadcast_msg = message.reply_to_message
    sent = failed = 0

    # Loop through users
    for uid in config.get("users", []):
        try:
            await client.copy_message(chat_id=uid, from_chat_id=broadcast_msg.chat.id, message_id=broadcast_msg.message_id)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"❌ Failed to send to {uid}: {e}")

    print(f"✅ Broadcast finished — Sent: {sent}, Failed: {failed}")
    await message.reply(f"✅ Broadcast complete\n📬 Sent: {sent}\n❌ Failed: {failed}")

# --- Start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    config = get_config()
    if user_id not in config.get("users", []):
        config["users"].append(user_id)
    if user_id not in config.get("admins", []):
        config["admins"].append(user_id)
    save_config(config)
    await message.reply_text("✅ Bot is running.\nUse /admin to open the panel.")

# --- Run the Bot ---
logger.info("Starting bot...")
app.run()
