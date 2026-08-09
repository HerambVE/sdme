# Use a lightweight, official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files and restrict thread memory arenas
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV VECLIB_MAXIMUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1


# Install system dependencies (FFmpeg for media processing, NodeJS for YouTube Po-Token)
RUN apt-get update && apt-get install -y ffmpeg nodejs

# Copy requirements file
COPY requirements.txt .

# 1. FORCE CPU-ONLY PYTORCH INSTALLATION (Prevents 8GB CUDA Bloat)
RUN pip install --default-timeout=1000 --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 2. Install remaining application dependencies
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# 3. Install latest nightly yt-dlp build (done at build time, not at runtime)
RUN pip install --default-timeout=1000 --no-cache-dir --pre yt-dlp


# 3. Pre-cache Whisper model weights during the build phase
RUN python -c "import whisper; whisper.load_model('base')"

# Copy the rest of the application source code into the container
COPY . .

# Grant execution permissions to entrypoint script
RUN chmod +x entrypoint.sh

# Expose port (Render automatically maps $PORT)
EXPOSE 8000

CMD ["./entrypoint.sh"]