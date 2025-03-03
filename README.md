# YAYVD - Yet Another YouTube Video Downloader

## Deployment to Railway

1. Fork this repository to your GitHub account
2. Create a new project on [Railway.app](https://railway.app)
3. Click on "Deploy from GitHub repo"
4. Select the forked repository
5. Railway will automatically detect the Python project and start the deployment
6. Once deployed, you can access your application through the provided Railway domain

## Environment Variables

No additional environment variables are required for basic deployment.

## Features

- Download YouTube videos in various formats and qualities
- Support for both video and audio-only downloads
- Clean and modern user interface
- Efficient caching system
- Automatic file cleanup

## Local Development

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python app.py`

## Tech Stack

- Flask
- yt-dlp
- Bootstrap 5
- Gunicorn (Production server)