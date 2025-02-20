# YayVD
### Yet Another YouTube Video Downloader

A minimal, modern web interface for downloading YouTube videos built with Flask and yt-dlp. Features a clean dark mode UI and supports multiple video quality options.

![YouTube Downloader Screenshot](screenshot.png)

## Features

- 🎨 Clean, minimal dark mode interface
- 📱 Fully responsive design (mobile-friendly)
- 🎥 Multiple video quality options
- ⚡ Fast downloads using yt-dlp
- 🔒 No ads, no tracking, open source
- 📦 Automatic file cleanup
- 🎯 Simple one-click downloads

## Installation

### Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/thisispit/YayVD.git
```

```bash
cd youtube-downloader
```

2. Install dependencies:
### Install Flask

```bash
pip install Flask
```
### Install yt_dlp
```bash
pip install yt-dlp
```

### Install FFmpeg
#### Windows
```bash
winget install Ffmpeg
```

#### Linux
For Debian/Ubuntu:
```bash
sudo apt update && sudo apt install ffmpeg
```
For Fedora:
```bash
sudo dnf install ffmpeg
```
For Arch:
```bash
sudo pacman -S ffmpeg
```

#### Mac
```bash
brew install ffmpeg
```

3. Run the application:

```bash
python downloader.py
```

4. Open your browser and navigate to:

```
http://127.0.0.1:5000
```

## Free Hosting Options

### 1. Render
1. Create account on [Render](https://render.com)
2. Create new Web Service
3. Connect your GitHub repository
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `gunicorn downloader:app`
6. Deploy

### 2. Pythonanywhere
1. Create account on [PythonAnywhere](https://www.pythonanywhere.com)
2. Go to Web tab
3. Create new web app
4. Choose Flask
5. Clone your repository
6. Set WSGI configuration file:
```python
from downloader import app as application
```
7. Install requirements using bash console:
```bash
pip3 install --user -r requirements.txt
```
8. Reload web app

### 3. Railway
1. Create account on [Railway](https://railway.app)
2. Create new project
3. Deploy from GitHub repository
4. Add Python template
5. Set start command: `gunicorn downloader:app`
6. Deploy

Note: Some free hosts might have limitations on file size or processing time. Choose based on your needs.