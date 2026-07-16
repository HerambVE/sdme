# Use a lightweight, official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (FFmpeg for media processing, NodeJS for YouTube Po-Token)
RUN apt-get update && apt-get install -y ffmpeg nodejs

# Copy requirements file
COPY requirements.txt .

# 1. FORCE CPU-ONLY PYTORCH INSTALLATION (Prevents 8GB CUDA Bloat)
RUN pip install --default-timeout=1000 --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 2. Install remaining application dependencies
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# 3. Pre-cache Whisper model weights during the build phase
RUN python -c "import whisper; whisper.load_model('base')"

# Copy the rest of the application source code into the container
COPY . .