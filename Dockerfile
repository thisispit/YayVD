FROM python:3.9-slim

# Install FFmpeg, Chrome, and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    software-properties-common \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

# Set working directory
WORKDIR /app

# Create downloads directory with proper permissions
RUN mkdir -p /app/downloads && \
    chmod 777 /app/downloads

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Verify directories and permissions
RUN ls -la /app && \
    ls -la /app/downloads

# Environment variables
ENV PORT=8080
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV DOWNLOAD_FOLDER=/app/downloads
ENV CHROME_PATH=/usr/bin/google-chrome

# Expose port
EXPOSE 8080

# Command to run the application
CMD gunicorn --bind 0.0.0.0:$PORT src.app:app
