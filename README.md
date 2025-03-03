# YouTube Video Downloader

## Prerequisites

- Python 3.x
- FFmpeg (Required for video processing)

### Installing FFmpeg

#### Windows
1. Download FFmpeg from https://ffmpeg.org/download.html
2. Add FFmpeg to your system PATH

#### Linux/Ubuntu
```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS
```bash
brew install ffmpeg
```

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

```bash
python app.py
```

The application will be available at http://localhost:5000

## Environment Variables

- `PORT`: Port number (default: 5000)
- `HTTP_PROXY` or `HTTPS_PROXY`: Proxy configuration (optional)

## Deployment on Railway

Add the following command to your Railway project's Settings > Build Command:

```bash
apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
```

This ensures FFmpeg is installed during the deployment process.
