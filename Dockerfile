# Use Python slim image
FROM python:3.10-slim-bullseye

# Install system dependencies needed for media support (e.g., for video/image handling)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy all files
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Run the bot
CMD ["python3", "multi_channel_bot.py"]
