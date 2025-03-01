FROM python:3.9-slim

# Install FFmpeg and locales
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version

# Set up locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen

# Set environment variables
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV TZ UTC

# Set timezone
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set working directory
WORKDIR /app

# Create downloads directory with proper permissions
RUN mkdir -p /app/downloads && \
    chmod 777 /app/downloads

# Install Python packages
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and cookie file
COPY . .
COPY youtube.com_cookies.txt /app/youtube.com_cookies.txt

# Verify FFmpeg and files
RUN ffmpeg -version && \
    ls -la /app/youtube.com_cookies.txt

# Environment variables
ENV PORT=8080
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV DOWNLOAD_FOLDER=/app/downloads

# Expose port
EXPOSE 8080

# Command to run the application
CMD gunicorn --bind 0.0.0.0:$PORT src.app:app
