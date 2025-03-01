# YouTube Video Downloader

A simple, robust Flask-based YouTube video downloader application that uses multiple methods to extract and download videos from YouTube, handling various anti-scraping measures.

## Features

- Multiple fallback methods to bypass YouTube's restrictions
- Automatic quality selection
- User-friendly interface with Bootstrap styling
- Loading indicators for better user experience
- Error handling and logging
- Compatible with Render deployment

## Technologies Used

- Flask - Web framework
- yt-dlp - Advanced YouTube downloader library
- Gunicorn - WSGI HTTP Server
- Bootstrap - Front-end framework

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```

## Deployment on Render

This application is configured for deployment on Render with the included `render.yaml` file. Simply connect your repository to Render and it will automatically deploy the application.

## How It Works

The application uses multiple methods to extract and download videos from YouTube:

1. First attempts to download via a proxy service
2. Falls back to direct download using yt-dlp
3. Uses random user agents to avoid detection
4. Implements various error handling mechanisms

## Troubleshooting

If you encounter any issues:

- Try using different video URLs
- Check if YouTube has updated its anti-scraping measures
- Ensure all dependencies are correctly installed
- Check the logs for specific error messages
