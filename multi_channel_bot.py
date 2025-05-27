from pyrogram import Client, filters
import asyncio
from pyrogram.filters import command, private, user
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, ChatJoinRequest
)
from pymongo import MongoClient
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

mongo_client = MongoClient("mongodb+srv://mystery:exelexa2237887@cluster0.epdqu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") 
db = mongo_client["telegram_bot"]
config_collection = db["config"]

if "config" not in db.list_collection_names():
    config_collection.insert_one({
        "admins": [],
        "channels": {},
        "welcome_messages": {},
        "users": []
    })
    logger.info("Initialized MongoDB config collection.")

states = {}

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

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    logger.info(f"/start command received from user_id={user_id}")

    try:
        config = get_config()
        if user_id not in config.get("users", []):
            config["users"].append(user_id)
        if user_id not in config.get("admins", []):
            config["admins"].append(user_id)
        save_config(config)
        await message.reply_text("✅ Bot is running.\nUse /admin to open the panel.")

    except Exception as e:
        logger.error(f"Exception in /start handler for user_id={user_id}: {e}")

@app.on_message(filters.command("broadcast") & filters.private & filters.reply)
async def broadcast_command(client: Client, message: Message):
    user_id = message.from_user.id
    config = config_collection.find_one({})
    
    if user_id not in config.get("admins", []):
        await message.reply("❌ You are not authorized to use this command.")
        logger.warning(f"Unauthorized broadcast attempt by user {user_id}")
        return
        
    broadcast_msg = message.reply_to_message
    logger.info(f"Replied message details: ID={getattr(broadcast_msg, 'id', None)}, Type={getattr(broadcast_msg, '_', None)}, Service={getattr(broadcast_msg, 'service', None)}, Chat={getattr(broadcast_msg.chat, 'id', None) if broadcast_msg else None}")
    
    if not broadcast_msg or not hasattr(broadcast_msg, "id"):
        await message.reply("⚠️ Please reply to a valid message (text, photo, or video) to broadcast.")
        logger.warning(f"Broadcast by {user_id} failed: Invalid or missing reply message, broadcast_msg={broadcast_msg}")
        return
        
    if getattr(broadcast_msg, "service", None):
        await message.reply("⚠️ Cannot broadcast service messages (e.g., user joined/left). Please reply to a text, photo, or video message.")
        logger.warning(f"Broadcast by {user_id} failed: Replied to a service message")
        return
        
    users = config.get("users", [])
    if not users:
        await message.reply("⚠️ No users found to broadcast to.")
        logger.info("Broadcast aborted: No users in config")
        return

    total_users = len(users)
    sent = 0
    failed = 0
    progress_message = await message.reply("📢 Broadcast started...\n\nSent: 0\nFailed: 0\nProgress: 0%")
    logger.info(f"Broadcast started by {user_id}, total users: {total_users}")
    for i, uid in enumerate(users, 1):
        try:
            await client.copy_message(
                chat_id=uid,
                from_chat_id=broadcast_msg.chat.id,
                message_id=broadcast_msg.id
            )
            sent += 1
            logger.info(f"Successfully sent broadcast to user {uid}")
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send broadcast to user {uid}: {str(e)}")
            
        if i % 5 == 0 or i == total_users:
            progress = (i / total_users) * 100
            await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_message.id,
                text=f"📢 Broadcast in progress...\nSent: {sent}\nFailed: {failed}\nProgress: {progress:.1f}%"
            )
            logger.debug(f"Progress update: Sent={sent}, Failed={failed}, Progress={progress:.1f}%")

        await asyncio.sleep(0.1)
        
    final_message = f"✅ Broadcast complete\n📬 Sent: {sent}\n❌ Failed: {failed}\nProgress: 100%"
    await client.edit_message_text(
        chat_id=message.chat.id,
        message_id=progress_message.id,
        text=final_message
    )
    logger.info(f"Broadcast by {user_id} completed: Sent={sent}, Failed={failed}")
        
@app.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message: Message):
    if not is_admin(message.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("Set Welcome", callback_data="set_welcome")],
        [InlineKeyboardButton("Stats", callback_data="stats")]
    ]
    await message.reply("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

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

logger.info("Starting bot...")
if __name__ == "__main__":
    app.run()
