# Multi-Channel Telegram Bot

This bot automatically accepts join requests in multiple channels and sends a welcome message with inline buttons.

## Features
- Accepts join requests in registered channels
- Sends welcome messages (admin-configurable)
- Supports inline button links
- Admin panel: broadcast, statistics, and welcome setup
- Handles media-rich broadcasts (images, videos, etc.)

## Setup

1. **Replace** `api_id`, `api_hash`, and `bot_token` in `multi_channel_bot.py`
2. **Build Docker image**:
   ```bash
   docker build -t telegram-multi-bot .
   ```
3. **Run the bot**:
   ```bash
   docker run -d telegram-multi-bot
   ```

## Credits
Built by [@xxfresh](https://t.me/xxfresh)
