# Dockerfile
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir pyrogram tgcrypto

# Copy bot files
COPY . .

# Run the bot
CMD ["python", "multi_channel_bot.py"]
