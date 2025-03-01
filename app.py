from flask import Flask, render_template, request, send_file
import yt_dlp
import os
import logging
import requests
import random
import time
from urllib.parse import urlparse, parse_qs
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def extract_video_id(url):
    """Extract the video ID from a YouTube URL"""
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    parsed_url = urlparse(url)
    if 'youtube.com' in parsed_url.netloc:
        if '/watch' in parsed_url.path:
            return parse_qs(parsed_url.query).get('v', [''])[0]
        elif '/embed/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
        elif '/v/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
    
    return None

def get_available_formats(url):
    """Get available formats using yt-dlp with anti-blocking measures"""
    formats = []
    title = "YouTube Video"
    video_id = extract_video_id(url)
    
    if not video_id:
        return formats, title
        
    # Add standard formats as fallback
    formats = [
        {
            'format_id': 'best',
            'ext': 'mp4',
            'resolution': 'Highest Quality',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'Auto'
        },
        {
            'format_id': '22',
            'ext': 'mp4',
            'resolution': '720p',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'HD'
        },
        {
            'format_id': '18',
            'ext': 'mp4',
            'resolution': '360p',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'SD'
        }
    ]
    
    # Try to get real title
    try:
        # Use a public API to get title without triggering YouTube blocks
        api_url = f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'title' in data:
                title = data['title']
    except Exception as e:
        logger.error(f"Error getting title: {str(e)}")
    
    # Try with yt-dlp as a backup for format info
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'youtube_include_dash_manifest': False,
            'extract_flat': True,
            'skip_download': True,
            'http_headers': {
                'User-Agent': get_random_user_agent(),
                'Referer': 'https://www.google.com/'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'title' in info:
                title = info['title']
    except Exception as e:
        logger.error(f"Error with yt-dlp format extraction: {str(e)}")
    
    return formats, title

def download_video(url, format_id='best'):
    """Download video with multiple fallback mechanisms"""
    video_id = extract_video_id(url)
    if not video_id:
        return None
    
    # Try direct proxy download first
    try:
        # Use external service that downloads directly
        proxy_url = f"https://projectlounge.pw/ytdl/download?url=https://www.youtube.com/watch?v={video_id}&format={format_id if format_id != 'best' else 'mp4'}"
        headers = {'User-Agent': get_random_user_agent()}
        
        logger.info(f"Trying proxy download from {proxy_url}")
        response = requests.get(proxy_url, headers=headers, timeout=15, stream=True)
        
        if response.status_code == 200 and int(response.headers.get('Content-Length', 0)) > 10000:
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}_{format_id}.mp4")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                logger.info(f"Successfully downloaded via proxy to {file_path}")
                return file_path
    except Exception as e:
        logger.error(f"Proxy download error: {str(e)}")
    
    # Fallback to yt-dlp
    try:
        logger.info("Falling back to yt-dlp for download")
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{video_id}_{format_id}.%(ext)s'),
            'http_headers': {
                'User-Agent': get_random_user_agent(),
                'Referer': 'https://www.google.com/'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                downloaded_file = ydl.prepare_filename(info)
                if os.path.exists(downloaded_file):
                    logger.info(f"Successfully downloaded via yt-dlp to {downloaded_file}")
                    return downloaded_file
    except Exception as e:
        logger.error(f"yt-dlp download error: {str(e)}")
    
    return None

# Clean up old downloads periodically
@app.before_request
def cleanup_old_downloads():
    """Clean up old downloaded files to prevent disk space issues"""
    try:
        # Only run this cleanup occasionally (1 in 10 requests)
        if random.random() < 0.1 and os.path.exists(DOWNLOAD_FOLDER):
            current_time = time.time()
            # Clean files older than 1 hour
            for filename in os.listdir(DOWNLOAD_FOLDER):
                file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                # If file is older than 1 hour, remove it
                if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old file: {file_path}")
                    except:
                        pass
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy"}, 200

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            url = request.form.get('url', '').strip()
            if not url:
                return render_template('index.html', error="Please enter a URL")
            
            formats, title = get_available_formats(url)
            return render_template('index.html', formats=formats, video_title=title, url=url)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return render_template('index.html', error=str(e))
    
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    try:
        url = request.form.get('url')
        format_id = request.form.get('format', 'best')
        
        if not url:
            return render_template('index.html', error="Please provide a valid URL")
        
        downloaded_file = download_video(url, format_id)
        
        if downloaded_file and os.path.exists(downloaded_file):
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                mimetype='video/mp4'
            )
        
        return render_template('index.html', error="Failed to download video. YouTube may be blocking this request. Please try again with a different URL.")
        
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return render_template('index.html', error=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
