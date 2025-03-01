FROM python:3.9-slim

# Install FFmpeg, Chrome, and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    tzdata \
    locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

# Set locale and timezone
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# Set working directory
WORKDIR /app

# Create downloads directory with proper permissions
RUN mkdir -p /app/downloads && \
    chmod 777 /app/downloads

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and cookies
COPY . .
COPY cookies.txt /app/cookies.txt

# Verify FFmpeg and files
RUN ffmpeg -version && \
    ls -la /app/cookies.txt

# Environment variables
ENV PORT=8080
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV DOWNLOAD_FOLDER=/app/downloads
ENV CHROME_PATH=/usr/bin/google-chrome

# Expose port
EXPOSE 8080

# Command to run the application
CMD gunicorn --bind 0.0.0.0:$PORT src.app:app
